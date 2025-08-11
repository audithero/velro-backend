"""
Production Rate Limiting Middleware with Redis Integration
Implements tier-based rate limiting with Redis backend and in-memory fallback.
Follows OWASP security guidelines and PRD specifications.
"""

import time
import json
import asyncio
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timezone
from collections import defaultdict
from threading import Lock

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError
import logging

from config import settings

logger = logging.getLogger(__name__)

# Import testing configuration with production-safe fallbacks
try:
    from testing_config import (
        is_testing_mode, 
        get_test_rate_limits, 
        should_bypass_rate_limiting,
        is_e2e_testing_enabled
    )
    
    if is_testing_mode():
        logger.warning("⚠️ [RATE-LIMITER] Testing mode active: Checking for increased rate limits")
    if is_e2e_testing_enabled():
        logger.warning("⚠️ [RATE-LIMITER] E2E testing enabled: Rate limit bypass available")
        
except ImportError as e:
    logger.warning(f"⚠️ [RATE-LIMITER] Testing config import failed: {e}")
    # Production-safe fallback functions
    def is_testing_mode():
        return False
    def get_test_rate_limits():
        return None  
    def should_bypass_rate_limiting(request):
        return False
    def is_e2e_testing_enabled():
        return False

# Production-safe rate limit tiers (uses test limits only when explicitly enabled)
_test_limits = get_test_rate_limits()
RATE_LIMIT_TIERS = _test_limits if _test_limits is not None else {
    "free": {
        "requests_per_minute": 100,  # Significantly increased for auth endpoints  
        "requests_per_hour": 1000,   # Increased from 300
        "concurrent_requests": 10    # Increased from 5
    },
    "pro": {
        "requests_per_minute": 300,  # Increased from 100
        "requests_per_hour": 5000,   # Increased from 2000
        "concurrent_requests": 50     # Increased from 20
    },
    "enterprise": {
        "requests_per_minute": 1000,   # Increased from 500
        "requests_per_hour": 20000,   # Increased from 10000
        "concurrent_requests": 200     # Increased from 100
    }
}

# Log the active rate limit configuration
if _test_limits is not None:
    logger.info("🧪 [RATE-LIMITER] Using increased rate limits for testing")
else:
    logger.info("🔒 [RATE-LIMITER] Using production rate limits")

class ProductionRateLimiter:
    """
    Production rate limiter with Redis backend and in-memory fallback.
    Implements sliding window rate limiting with proper error handling and timeout protection.
    """
    
    def __init__(self):
        # Redis setup
        self.redis_client = None
        self.redis_available = False
        self.redis_timeout = 0.2  # 200ms timeout for Redis operations - increased to prevent connection resets
        
        # Initialize Redis connection if configured with fallback protection
        if hasattr(settings, 'redis_url') and settings.redis_url:
            try:
                # CRITICAL FIX: Enhanced Redis configuration to prevent "Connection reset by peer" errors
                self.redis_client = redis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=1.0,   # Increased for stability
                    socket_timeout=0.5,           # Increased socket timeout to prevent resets
                    socket_keepalive=True,        # Enable keepalive
                    socket_keepalive_options={},  # Use system defaults
                    retry_on_timeout=True,        # Retry on timeout for reliability
                    retry_on_error=[ConnectionError, TimeoutError],  # Retry on connection errors
                    max_connections=20,           # Reduced to prevent connection exhaustion
                    decode_responses=True,
                    health_check_interval=30,     # More frequent health checks
                    connection_pool_kwargs={
                        'max_connections': 20,
                        'retry_on_timeout': True,
                        'socket_keepalive': True,
                        'socket_keepalive_options': {}
                    }
                )
                
                # Test the connection immediately to catch configuration issues
                asyncio.create_task(self._test_redis_connection())
                
                self.redis_available = True
                logger.info("✅ Rate limiter: Redis backend enabled with enhanced connection stability")
            except Exception as e:
                logger.warning(f"⚠️ Rate limiter: Redis configuration failed, using in-memory fallback: {e}")
                self.redis_client = None
                self.redis_available = False
        else:
            logger.info("📝 Rate limiter: No Redis URL configured, using in-memory backend")
        
        # In-memory fallback storage (thread-safe)
        self.requests = defaultdict(list)  # client_id -> list of request timestamps
        self.concurrent = defaultdict(int)  # client_id -> current concurrent requests
        self.lock = Lock()
        
        # Performance metrics
        self._redis_hits = 0
        self._redis_misses = 0
        self._memory_fallbacks = 0
        self._redis_timeouts = 0
        self._redis_errors = 0
        self._avg_redis_time = 0.0
        self._total_redis_operations = 0
    
    async def _test_redis_connection(self):
        """Test Redis connection on startup to catch issues early."""
        try:
            if self.redis_client:
                await asyncio.wait_for(self.redis_client.ping(), timeout=2.0)
                logger.info("✅ Rate limiter: Redis connection test successful")
        except Exception as e:
            logger.warning(f"⚠️ Rate limiter: Redis connection test failed: {e}")
            self.redis_available = False
    
    async def _timeout_wrapper(self, operation, *args, **kwargs):
        """Wrapper to add timeout protection to Redis operations."""
        start_time = time.time()
        try:
            result = await asyncio.wait_for(operation(*args, **kwargs), timeout=self.redis_timeout)
            operation_time = time.time() - start_time
            
            # Update performance metrics
            self._total_redis_operations += 1
            self._avg_redis_time = (
                (self._avg_redis_time * (self._total_redis_operations - 1) + operation_time) 
                / self._total_redis_operations
            )
            
            # Log slow operations
            if operation_time > 0.05:  # 50ms threshold
                logger.warning(f"Slow Redis operation: {operation_time:.3f}s")
            
            return result
            
        except asyncio.TimeoutError:
            self._redis_timeouts += 1
            operation_time = time.time() - start_time
            logger.warning(f"Redis operation timed out after {operation_time:.3f}s, falling back to memory")
            raise
        except Exception as e:
            self._redis_errors += 1
            operation_time = time.time() - start_time
            logger.error(f"Redis operation failed after {operation_time:.3f}s: {e}")
            raise
    
    async def is_allowed(self, client_id: str, tier: str = "free") -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed based on rate limits.
        Uses Redis if available with timeout protection, falls back to in-memory storage.
        Returns (allowed, headers_dict)
        """
        if self.redis_available and self.redis_client:
            try:
                return await self._is_allowed_redis(client_id, tier)
            except (asyncio.TimeoutError, RedisError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Redis rate limiting failed ({type(e).__name__}), using fallback: {e}")
                self._memory_fallbacks += 1
                # Temporarily disable Redis to avoid repeated failures
                self.redis_available = False
                return self._is_allowed_memory(client_id, tier)
        else:
            return self._is_allowed_memory(client_id, tier)
    
    async def _is_allowed_redis(self, client_id: str, tier: str) -> Tuple[bool, Dict[str, Any]]:
        """Redis-based rate limiting with sliding window and timeout protection."""
        current_time = time.time()
        limits = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["free"])
        
        # Redis keys for different windows
        minute_key = f"rate_limit:minute:{client_id}"
        hour_key = f"rate_limit:hour:{client_id}"
        
        # Use Redis pipeline for atomic operations with timeout protection
        async def _execute_redis_pipeline():
            pipe = self.redis_client.pipeline()
            
            # Sliding window implementation
            # Remove old entries and count current
            cutoff_minute = current_time - 60
            cutoff_hour = current_time - 3600
            
            # Clean and count minute window
            pipe.zremrangebyscore(minute_key, 0, cutoff_minute)
            pipe.zcard(minute_key)
            pipe.zadd(minute_key, {str(current_time): current_time})
            pipe.expire(minute_key, 60)
            
            # Clean and count hour window  
            pipe.zremrangebyscore(hour_key, 0, cutoff_hour)
            pipe.zcard(hour_key)
            pipe.zadd(hour_key, {str(current_time): current_time})
            pipe.expire(hour_key, 3600)
            
            return await pipe.execute()
        
        try:
            # Execute pipeline with timeout protection
            results = await self._timeout_wrapper(_execute_redis_pipeline)
            
            requests_last_minute = results[1]  # Count after cleanup
            requests_last_hour = results[5]   # Count after cleanup
            
            # Check limits (subtract 1 because we just added the current request)
            if requests_last_minute > limits["requests_per_minute"]:
                # Remove the request we just added since it's rejected (with timeout)
                await self._timeout_wrapper(self.redis_client.zrem, minute_key, str(current_time))
                await self._timeout_wrapper(self.redis_client.zrem, hour_key, str(current_time))
                
                return False, self._get_headers(
                    limits["requests_per_minute"],
                    0,
                    int(current_time + 60)
                )
            
            if requests_last_hour > limits["requests_per_hour"]:
                # Remove the request we just added since it's rejected (with timeout)
                await self._timeout_wrapper(self.redis_client.zrem, minute_key, str(current_time))
                await self._timeout_wrapper(self.redis_client.zrem, hour_key, str(current_time))
                
                return False, self._get_headers(
                    limits["requests_per_hour"],
                    0,
                    int(current_time + 3600)
                )
            
            # Calculate remaining
            remaining_minute = limits["requests_per_minute"] - requests_last_minute
            remaining_hour = limits["requests_per_hour"] - requests_last_hour
            remaining = min(remaining_minute, remaining_hour)
            
            reset_time = int(current_time + 60)
            
            self._redis_hits += 1
            return True, self._get_headers(
                limits["requests_per_minute"],
                max(0, remaining),
                reset_time
            )
            
        except Exception as e:
            # All errors are already logged in _timeout_wrapper
            raise  # Re-raise so the calling function can handle the fallback
    
    def _is_allowed_memory(self, client_id: str, tier: str) -> Tuple[bool, Dict[str, Any]]:
        """In-memory rate limiting (thread-safe fallback)."""
        with self.lock:
            current_time = time.time()
            limits = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["free"])
            
            # Clean old requests (older than 1 hour)
            cutoff_hour = current_time - 3600
            cutoff_minute = current_time - 60
            
            if client_id in self.requests:
                self.requests[client_id] = [
                    req_time for req_time in self.requests[client_id] 
                    if req_time > cutoff_hour
                ]
            
            # Count requests in different windows
            requests_last_minute = sum(
                1 for req_time in self.requests[client_id] 
                if req_time > cutoff_minute
            )
            requests_last_hour = len(self.requests[client_id])
            
            # Check limits
            if requests_last_minute >= limits["requests_per_minute"]:
                return False, self._get_headers(
                    limits["requests_per_minute"], 
                    0, 
                    int(cutoff_minute + 60)
                )
            
            if requests_last_hour >= limits["requests_per_hour"]:
                return False, self._get_headers(
                    limits["requests_per_hour"], 
                    0, 
                    int(cutoff_hour + 3600)
                )
            
            # Record this request
            self.requests[client_id].append(current_time)
            
            # Calculate remaining
            remaining_minute = limits["requests_per_minute"] - requests_last_minute - 1
            remaining_hour = limits["requests_per_hour"] - requests_last_hour - 1
            remaining = min(remaining_minute, remaining_hour)
            
            # Reset time is when the oldest request in the window expires
            reset_time = int(current_time + 60)
            
            return True, self._get_headers(
                limits["requests_per_minute"], 
                max(0, remaining), 
                reset_time
            )
    
    def _get_headers(self, limit: int, remaining: int, reset: int) -> Dict[str, str]:
        """Generate rate limit headers"""
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(reset)
        }
    
    async def increment_concurrent(self, client_id: str, tier: str = "free") -> bool:
        """Check and increment concurrent requests with timeout protection"""
        if self.redis_available and self.redis_client:
            try:
                return await self._increment_concurrent_redis(client_id, tier)
            except (asyncio.TimeoutError, RedisError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Redis concurrent tracking failed ({type(e).__name__}), using fallback: {e}")
                self._memory_fallbacks += 1
                # Temporarily disable Redis to avoid repeated failures
                self.redis_available = False
                return self._increment_concurrent_memory(client_id, tier)
        else:
            return self._increment_concurrent_memory(client_id, tier)
    
    async def _increment_concurrent_redis(self, client_id: str, tier: str) -> bool:
        """Redis-based concurrent request tracking with timeout protection"""
        limits = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["free"])
        concurrent_key = f"concurrent:{client_id}"
        
        # Simplified atomic increment with timeout protection (avoiding watch/multi for better performance)
        async def _atomic_increment():
            # Use EVAL script for atomic check-and-increment
            lua_script = """
            local key = KEYS[1]
            local limit = tonumber(ARGV[1])
            local expiry = tonumber(ARGV[2])
            
            local current = redis.call('GET', key)
            local current_count = current and tonumber(current) or 0
            
            if current_count >= limit then
                return 0  -- Limit exceeded
            else
                redis.call('INCR', key)
                redis.call('EXPIRE', key, expiry)
                return 1  -- Success
            end
            """
            return await self.redis_client.eval(
                lua_script, 1, concurrent_key, 
                limits["concurrent_requests"], 300  # 5 minute expiration
            )
        
        result = await self._timeout_wrapper(_atomic_increment)
        return bool(result)
    
    def _increment_concurrent_memory(self, client_id: str, tier: str) -> bool:
        """Memory-based concurrent request tracking"""
        with self.lock:
            limits = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["free"])
            if self.concurrent[client_id] >= limits["concurrent_requests"]:
                return False
            self.concurrent[client_id] += 1
            return True
    
    async def decrement_concurrent(self, client_id: str):
        """Decrement concurrent requests with timeout protection"""
        if self.redis_available and self.redis_client:
            try:
                await self._decrement_concurrent_redis(client_id)
            except (asyncio.TimeoutError, RedisError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Redis concurrent decrement failed ({type(e).__name__}), using fallback: {e}")
                self._memory_fallbacks += 1
                # Note: We don't disable Redis here to avoid inconsistency, just log the error
                self._decrement_concurrent_memory(client_id)
        else:
            self._decrement_concurrent_memory(client_id)
    
    async def _decrement_concurrent_redis(self, client_id: str):
        """Redis-based concurrent request decrement with timeout protection"""
        concurrent_key = f"concurrent:{client_id}"
        
        async def _atomic_decrement():
            # Use EVAL script for atomic check-and-decrement
            lua_script = """
            local key = KEYS[1]
            local current = redis.call('GET', key)
            
            if current and tonumber(current) > 0 then
                redis.call('DECR', key)
                return 1
            end
            return 0
            """
            return await self.redis_client.eval(lua_script, 1, concurrent_key)
        
        await self._timeout_wrapper(_atomic_decrement)
    
    def _decrement_concurrent_memory(self, client_id: str):
        """Memory-based concurrent request decrement"""
        with self.lock:
            if client_id in self.concurrent and self.concurrent[client_id] > 0:
                self.concurrent[client_id] -= 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive rate limiter performance metrics"""
        return {
            "redis_available": self.redis_available,
            "redis_hits": self._redis_hits,
            "redis_misses": self._redis_misses,
            "memory_fallbacks": self._memory_fallbacks,
            "redis_timeouts": self._redis_timeouts,
            "redis_errors": self._redis_errors,
            "total_redis_operations": self._total_redis_operations,
            "avg_redis_time_ms": round(self._avg_redis_time * 1000, 2),
            "backend": "redis" if self.redis_available else "memory",
            "timeout_protection_enabled": True,
            "timeout_threshold_ms": int(self.redis_timeout * 1000)
        }
    
    async def health_check_redis(self) -> bool:
        """Periodic Redis health check to re-enable Redis when it recovers"""
        if not self.redis_available and self.redis_client:
            try:
                await self._timeout_wrapper(self.redis_client.ping)
                self.redis_available = True
                logger.info("✅ Rate limiter: Redis connection recovered")
                return True
            except Exception as e:
                logger.debug(f"Redis health check failed: {e}")
                return False
        return self.redis_available


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Production rate limiting middleware with proper headers"""
    
    def __init__(self, app, **kwargs):
        super().__init__(app)
        self.rate_limiter = ProductionRateLimiter()
        
        # Fastpath rate limiting (in-memory only, no Redis)
        self._fastpath_requests = defaultdict(list)  # client_id -> list of timestamps
        self._fastpath_lock = Lock()
        
    async def dispatch(self, request: Request, call_next):
        # PERFORMANCE: Skip heavy rate limiting for fastpath endpoints
        from middleware.utils import is_fastpath, log_middleware_skip
        if is_fastpath(request):
            log_middleware_skip(request, "rate_limiting", "fastpath_light_limits")
            # Apply very light rate limiting for fastpath (just prevent abuse)
            client_id = self._get_client_id(request)
            # Simple in-memory rate check without Redis (much faster)
            if not await self._fastpath_rate_check(client_id):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded", "error": "rate_limit_exceeded"}
                )
            return await call_next(request)
        
        # Skip rate limiting for health checks and metrics
        if request.url.path in ["/health", "/metrics", "/api/health"]:
            return await call_next(request)
        
        # Check if rate limiting should be bypassed for testing (production-safe)
        if should_bypass_rate_limiting(request):
            logger.debug(f"🧪 [RATE-LIMITER] Rate limiting bypassed for test request: {request.url.path}")
            return await call_next(request)
        
        # Periodic Redis health check (every ~100 requests)
        if self.rate_limiter._total_redis_operations % 100 == 0:
            asyncio.create_task(self.rate_limiter.health_check_redis())
        
        start_time = time.time()
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Get user tier (default to free)
        tier = self._get_user_tier(request)
        
        try:
            # Check rate limits with timeout protection
            allowed, headers = await self.rate_limiter.is_allowed(client_id, tier)
            
            rate_limit_time = time.time() - start_time
            if rate_limit_time > 0.05:  # Log if rate limiting takes more than 50ms
                logger.warning(f"Rate limit check took {rate_limit_time:.3f}s for client {client_id}")
            
            if not allowed:
                logger.warning(f"Rate limit exceeded for client {client_id}")
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Rate limit exceeded. Please try again later.",
                        "error": "rate_limit_exceeded"
                    }
                )
                # Add rate limit headers
                for key, value in headers.items():
                    response.headers[key] = value
                return response
            
            # Check concurrent requests with timeout protection
            if not await self.rate_limiter.increment_concurrent(client_id, tier):
                logger.warning(f"Concurrent request limit exceeded for client {client_id}")
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Too many concurrent requests. Please try again.",
                        "error": "concurrent_limit_exceeded"
                    }
                )
                # Add rate limit headers
                for key, value in headers.items():
                    response.headers[key] = value
                return response
            
            try:
                # Process request
                response = await call_next(request)
                
                # Add rate limit headers to successful responses
                for key, value in headers.items():
                    response.headers[key] = value
                
                return response
                
            finally:
                # Always decrement concurrent count (with timeout protection)
                await self.rate_limiter.decrement_concurrent(client_id)
                
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"Rate limiting middleware error after {total_time:.3f}s: {e}")
            # If rate limiting fails completely, allow the request to proceed but log the failure
            logger.warning(f"Rate limiting bypassed due to error for client {client_id}")
            return await call_next(request)
    
    async def _fastpath_rate_check(self, client_id: str) -> bool:
        """
        Lightweight rate limiting for fastpath endpoints.
        Uses only in-memory storage, no Redis. Much faster but less persistent.
        Limits: 100 requests per minute for fastpath endpoints.
        """
        with self._fastpath_lock:
            current_time = time.time()
            
            # Clean old requests (older than 1 minute)
            cutoff_time = current_time - 60
            if client_id in self._fastpath_requests:
                self._fastpath_requests[client_id] = [
                    req_time for req_time in self._fastpath_requests[client_id] 
                    if req_time > cutoff_time
                ]
            
            # Check if under limit (500 requests per minute for fastpath - increased for auth stability)
            if len(self._fastpath_requests[client_id]) >= 500:
                return False
            
            # Record this request
            self._fastpath_requests[client_id].append(current_time)
            return True
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request"""
        # Try to get from headers first (for authenticated users)
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"
        
        # Use X-Client-ID header if present
        client_id = request.headers.get("X-Client-ID")
        if client_id:
            return f"client:{client_id}"
        
        # Fallback to IP address
        if request.client:
            return f"ip:{request.client.host}"
        
        return "unknown"
    
    def _get_user_tier(self, request: Request) -> str:
        """Get user tier from request context"""
        # Check if user is authenticated and has a tier
        if hasattr(request.state, "user") and request.state.user:
            user = request.state.user
            if hasattr(user, "tier"):
                return user.tier
            elif hasattr(user, "plan"):
                return user.plan
        
        # Default to free tier
        return "free"


def create_rate_limit_middleware(app):
    """Factory function to create rate limiting middleware"""
    return RateLimitMiddleware(app)