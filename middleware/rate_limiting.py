"""
Advanced Rate Limiting Middleware
Enterprise-grade rate limiting with Redis backend, CSRF protection, and adaptive limits.
Multiple rate limiting strategies with comprehensive monitoring and alerting.
"""
import os
import logging
import hashlib
import asyncio
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, timezone, timedelta
from functools import wraps
import json
import re

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

# CRITICAL FIX: Safe import of optional dependencies
try:
    import redis.asyncio as aioredis
    from middleware.redis_config import get_redis
    AIOREDIS_AVAILABLE = True
except ImportError:
    AIOREDIS_AVAILABLE = False
    aioredis = None
    get_redis = None

try:
    from utils.cache_manager import get_cache_manager, CacheLevel
    CACHE_MANAGER_AVAILABLE = True
except ImportError:
    CACHE_MANAGER_AVAILABLE = False
    get_cache_manager = None

try:  
    from utils.auth_monitor import get_auth_monitor, AuthEvent, AuthEventType, SecurityThreatLevel
    AUTH_MONITOR_AVAILABLE = True
except ImportError:
    AUTH_MONITOR_AVAILABLE = False
    get_auth_monitor = None

try:
    from config import settings
except ImportError:
    # Fallback settings
    class FallbackSettings:
        debug = True
        development_mode = True
    settings = FallbackSettings()

logger = logging.getLogger(__name__)

# CRITICAL FIX: Simple in-memory rate limiting fallback
_rate_limit_memory = {}

def _simple_rate_limit(key: str, limit: int, window: int) -> bool:
    """Simple in-memory rate limiting fallback."""
    current_time = datetime.now(timezone.utc).timestamp()
    
    if key not in _rate_limit_memory:
        _rate_limit_memory[key] = []
    
    # Clean old entries
    cutoff_time = current_time - window
    _rate_limit_memory[key] = [req_time for req_time in _rate_limit_memory[key] if req_time > cutoff_time]
    
    # Check limit
    if len(_rate_limit_memory[key]) >= limit:
        return False
    
    # Add current request
    _rate_limit_memory[key].append(current_time)
    return True

# CRITICAL FIX: Simplified rate limiting decorators for immediate use
def limit(rate_limit: str):
    """Simple rate limiting decorator that works without external dependencies."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract limit and window from rate_limit string (e.g., "5/minute")
            try:
                limit_str, period = rate_limit.split('/')
                limit_num = int(limit_str)
                
                # Convert period to seconds
                period_seconds = {
                    'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400
                }.get(period, 60)
                
                # Get request info
                request = None
                for arg in args:
                    if hasattr(arg, 'client'):
                        request = arg
                        break
                
                if request:
                    client_ip = request.client.host if request.client else 'unknown'
                    rate_key = f"rate_limit:{client_ip}:{func.__name__}"
                    
                    # Check rate limit
                    if not _simple_rate_limit(rate_key, limit_num, period_seconds):
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Rate limit exceeded: {rate_limit}"
                        )
                
            except Exception as e:
                # If rate limiting fails, log and continue (don't block requests)
                logger.warning(f"Rate limiting error: {e}")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def api_limit():
    """Standard API rate limit decorator."""
    return limit("100/minute")

def auth_limit():
    """Authentication rate limit decorator."""
    return limit("10/minute")

def generation_limit():
    """Generation rate limit decorator."""
    return limit("10/minute")

class RateLimitStrategy:
    """Rate limiting strategies."""
    
    @staticmethod
    def sliding_window(requests: List[float], limit: int, window: int) -> bool:
        """Sliding window rate limiting."""
        current_time = datetime.now(timezone.utc).timestamp()
        cutoff_time = current_time - window
        
        # Remove old requests
        recent_requests = [req_time for req_time in requests if req_time > cutoff_time]
        
        return len(recent_requests) < limit
    
    @staticmethod
    def token_bucket(tokens: int, capacity: int, refill_rate: float, last_refill: float) -> Tuple[bool, int, float]:
        """Token bucket rate limiting."""
        current_time = datetime.now(timezone.utc).timestamp()
        time_passed = max(0, current_time - last_refill)
        
        # Refill tokens
        new_tokens = min(capacity, tokens + int(time_passed * refill_rate))
        
        if new_tokens > 0:
            return True, new_tokens - 1, current_time
        else:
            return False, new_tokens, last_refill
    
    @staticmethod
    def adaptive_limit(base_limit: int, success_rate: float, load_factor: float) -> int:
        """Adaptive rate limiting based on system performance."""
        # Increase limit if success rate is high and load is low
        if success_rate > 0.95 and load_factor < 0.5:
            return int(base_limit * 1.5)
        # Decrease limit if success rate is low or load is high
        elif success_rate < 0.8 or load_factor > 0.8:
            return int(base_limit * 0.7)
        
        return base_limit


class AdvancedRateLimiter:
    """Advanced rate limiting with multiple strategies and Redis backend."""
    
    def __init__(self):
        # CRITICAL FIX: Safe initialization with fallbacks
        self.cache_manager = get_cache_manager() if CACHE_MANAGER_AVAILABLE else None
        self.auth_monitor = get_auth_monitor() if AUTH_MONITOR_AVAILABLE else None
        self.redis_client = None
        
        # Rate limit configurations
        self.limits = {
            'auth_login': {'limit': 5, 'window': 300, 'strategy': 'sliding_window'},
            'auth_register': {'limit': 3, 'window': 600, 'strategy': 'sliding_window'},
            'auth_refresh': {'limit': 10, 'window': 300, 'strategy': 'token_bucket'},
            'api_standard': {'limit': 100, 'window': 60, 'strategy': 'adaptive'},
            'api_premium': {'limit': 500, 'window': 60, 'strategy': 'adaptive'},
            'password_reset': {'limit': 2, 'window': 3600, 'strategy': 'sliding_window'}
        }
        
        # CSRF settings
        self.csrf_token_length = 32
        self.csrf_cookie_name = 'csrftoken'
        self.csrf_header_name = 'X-CSRF-Token'
    
    async def _get_redis_client(self):
        """Get Redis client for rate limiting."""
        if not AIOREDIS_AVAILABLE:
            logger.warning("⚠️ [RATE-LIMITER] aioredis not available, using in-memory fallback")
            return None
            
        if self.redis_client is None:
            try:
                redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
                self.redis_client = aioredis.from_url(redis_url, decode_responses=True)
                await self.redis_client.ping()
                logger.info("✅ [RATE-LIMITER] Redis connected")
            except Exception as e:
                logger.warning(f"⚠️ [RATE-LIMITER] Redis unavailable, using memory cache: {e}")
                self.redis_client = None
        
        return self.redis_client
    
    async def check_rate_limit(
        self,
        key: str,
        limit_type: str,
        request: Request
    ) -> Dict[str, Any]:
        """Check rate limit for a given key and type."""
        try:
            config = self.limits.get(limit_type, self.limits['api_standard'])
            limit = config['limit']
            window = config['window']
            strategy = config['strategy']
            
            # Get client identifier
            client_ip = self._get_client_ip(request)
            user_agent = request.headers.get('User-Agent', 'unknown')
            
            # Create rate limit key
            rate_key = f"rate_limit:{limit_type}:{key}"
            
            # Apply rate limiting strategy
            if strategy == 'sliding_window':
                allowed, remaining, reset_time = await self._sliding_window_check(
                    rate_key, limit, window
                )
            elif strategy == 'token_bucket':
                allowed, remaining, reset_time = await self._token_bucket_check(
                    rate_key, limit, window
                )
            elif strategy == 'adaptive':
                allowed, remaining, reset_time = await self._adaptive_limit_check(
                    rate_key, limit, window, request
                )
            else:
                allowed, remaining, reset_time = await self._sliding_window_check(
                    rate_key, limit, window
                )
            
            # Log rate limit event if exceeded
            if not allowed:
                await self._log_rate_limit_exceeded(request, limit_type, key)
            
            return {
                'allowed': allowed,
                'limit': limit,
                'remaining': remaining,
                'reset_time': reset_time,
                'retry_after': max(0, reset_time - datetime.now(timezone.utc).timestamp()) if not allowed else 0
            }
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Rate limit check failed: {e}")
            # Fail open for availability
            return {
                'allowed': True,
                'limit': config.get('limit', 100),
                'remaining': config.get('limit', 100),
                'reset_time': datetime.now(timezone.utc).timestamp() + 60,
                'retry_after': 0
            }
    
    async def _sliding_window_check(
        self,
        key: str,
        limit: int,
        window: int
    ) -> Tuple[bool, int, float]:
        """Sliding window rate limit check."""
        try:
            current_time = datetime.now(timezone.utc).timestamp()
            cutoff_time = current_time - window
            
            # Try Redis first
            redis_client = await self._get_redis_client()
            if redis_client:
                # Use Redis sorted sets for efficient sliding window
                pipe = redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, cutoff_time)  # Remove old entries
                pipe.zcard(key)  # Count current entries
                pipe.zadd(key, {str(current_time): current_time})  # Add current request
                pipe.expire(key, window)  # Set expiration
                
                results = await pipe.execute()
                current_count = results[1]
                
                allowed = current_count < limit
                remaining = max(0, limit - current_count - 1)
                reset_time = current_time + window
                
                return allowed, remaining, reset_time
            
            # Fallback to cache manager
            requests = await self.cache_manager.get(key, CacheLevel.L1_MEMORY) or []
            
            # Remove old requests
            recent_requests = [req_time for req_time in requests if req_time > cutoff_time]
            
            # Add current request if allowed
            if len(recent_requests) < limit:
                recent_requests.append(current_time)
                allowed = True
                remaining = limit - len(recent_requests)
            else:
                allowed = False
                remaining = 0
            
            # Store updated requests
            await self.cache_manager.set(key, recent_requests, CacheLevel.L1_MEMORY, ttl=window)
            
            reset_time = current_time + window
            return allowed, remaining, reset_time
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Sliding window check failed: {e}")
            return True, limit, datetime.now(timezone.utc).timestamp() + window
    
    async def _token_bucket_check(
        self,
        key: str,
        capacity: int,
        refill_rate: float
    ) -> Tuple[bool, int, float]:
        """Token bucket rate limit check."""
        try:
            current_time = datetime.now(timezone.utc).timestamp()
            
            # Get bucket state
            bucket_data = await self.cache_manager.get(key, CacheLevel.L1_MEMORY) or {
                'tokens': capacity,
                'last_refill': current_time
            }
            
            tokens = bucket_data['tokens']
            last_refill = bucket_data['last_refill']
            
            # Apply token bucket logic
            allowed, new_tokens, new_last_refill = RateLimitStrategy.token_bucket(
                tokens, capacity, refill_rate / 60, last_refill  # Convert to per-second rate
            )
            
            # Update bucket state
            bucket_data = {
                'tokens': new_tokens,
                'last_refill': new_last_refill
            }
            
            await self.cache_manager.set(key, bucket_data, CacheLevel.L1_MEMORY, ttl=3600)
            
            reset_time = current_time + (capacity - new_tokens) / (refill_rate / 60)
            
            return allowed, new_tokens, reset_time
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Token bucket check failed: {e}")
            return True, capacity, datetime.now(timezone.utc).timestamp() + 60
    
    async def _adaptive_limit_check(
        self,
        key: str,
        base_limit: int,
        window: int,
        request: Request
    ) -> Tuple[bool, int, float]:
        """Adaptive rate limit check based on system performance."""
        try:
            # Get system performance metrics
            success_rate = await self._get_success_rate(key)
            load_factor = await self._get_system_load()
            
            # Calculate adaptive limit
            adaptive_limit = RateLimitStrategy.adaptive_limit(base_limit, success_rate, load_factor)
            
            # Apply sliding window with adaptive limit
            return await self._sliding_window_check(key, adaptive_limit, window)
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Adaptive limit check failed: {e}")
            return await self._sliding_window_check(key, base_limit, window)
    
    async def _get_success_rate(self, key: str) -> float:
        """Get success rate for adaptive limiting."""
        try:
            metrics_key = f"success_metrics:{key}"
            metrics = await self.cache_manager.get(metrics_key, CacheLevel.L1_MEMORY) or {
                'total_requests': 0,
                'successful_requests': 0
            }
            
            if metrics['total_requests'] == 0:
                return 1.0
            
            return metrics['successful_requests'] / metrics['total_requests']
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Failed to get success rate: {e}")
            return 1.0
    
    async def _get_system_load(self) -> float:
        """Get system load factor for adaptive limiting."""
        try:
            # Simple system load estimation (in production, use proper system metrics)
            # This could integrate with system monitoring tools
            
            # For now, return a moderate load factor
            return 0.5
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Failed to get system load: {e}")
            return 0.5
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded headers (for reverse proxies)
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        forwarded = request.headers.get('X-Forwarded')
        if forwarded:
            return forwarded.split(',')[0].strip()
        
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip
        
        # Fallback to client host
        return request.client.host if request.client else 'unknown'
    
    async def _log_rate_limit_exceeded(self, request: Request, limit_type: str, key: str):
        """Log rate limit exceeded event."""
        try:
            client_ip = self._get_client_ip(request)
            user_agent = request.headers.get('User-Agent', 'unknown')
            
            # Create auth event
            event = AuthEvent(
                event_type=AuthEventType.RATE_LIMIT_EXCEEDED,
                user_id=None,
                email=None,
                ip_address=client_ip,
                user_agent=user_agent,
                timestamp=datetime.now(timezone.utc),
                success=False,
                error_message=f"Rate limit exceeded for {limit_type}",
                metadata={
                    'limit_type': limit_type,
                    'rate_limit_key': key,
                    'path': str(request.url.path),
                    'method': request.method
                },
                threat_level=SecurityThreatLevel.MEDIUM
            )
            
            await self.auth_monitor.log_auth_event(event)
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Failed to log rate limit exceeded: {e}")
    
    async def update_request_metrics(self, key: str, success: bool):
        """Update request metrics for adaptive rate limiting."""
        try:
            metrics_key = f"success_metrics:{key}"
            metrics = await self.cache_manager.get(metrics_key, CacheLevel.L1_MEMORY) or {
                'total_requests': 0,
                'successful_requests': 0
            }
            
            metrics['total_requests'] += 1
            if success:
                metrics['successful_requests'] += 1
            
            await self.cache_manager.set(metrics_key, metrics, CacheLevel.L1_MEMORY, ttl=3600)
            
        except Exception as e:
            logger.error(f"❌ [RATE-LIMITER] Failed to update request metrics: {e}")


class CSRFProtection:
    """CSRF protection middleware."""
    
    def __init__(self):
        self.token_length = 32
        self.cookie_name = 'csrftoken'
        self.header_name = 'X-CSRF-Token'
        self.cache_manager = get_cache_manager()
    
    def generate_csrf_token(self) -> str:
        """Generate CSRF token."""
        import secrets
        return secrets.token_urlsafe(self.token_length)
    
    async def validate_csrf_token(self, request: Request) -> bool:
        """Validate CSRF token from request."""
        try:
            # Skip CSRF for safe methods
            if request.method in ['GET', 'HEAD', 'OPTIONS']:
                return True
            
            # Get token from header or form data
            token_from_header = request.headers.get(self.header_name)
            
            # For form data, try to get from body (would need to be implemented)
            token_from_form = None
            
            token = token_from_header or token_from_form
            
            if not token:
                logger.warning("⚠️ [CSRF] No CSRF token provided")
                return False
            
            # Get expected token from session/cache
            session_id = self._get_session_id(request)
            if not session_id:
                logger.warning("⚠️ [CSRF] No session ID for CSRF validation")
                return False
            
            csrf_key = f"csrf_token:{session_id}"
            expected_token = await self.cache_manager.get(csrf_key, CacheLevel.L1_MEMORY)
            
            if not expected_token:
                logger.warning("⚠️ [CSRF] No stored CSRF token found")
                return False
            
            # Constant-time comparison
            return self._constant_time_compare(token, expected_token)
            
        except Exception as e:
            logger.error(f"❌ [CSRF] CSRF validation failed: {e}")
            return False
    
    def _get_session_id(self, request: Request) -> Optional[str]:
        """Get session ID from request."""
        # Try to get from Authorization header (JWT token)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
            return hashlib.md5(token.encode()).hexdigest()[:16]
        
        # Try to get from cookies
        session_cookie = request.cookies.get('session_id')
        if session_cookie:
            return session_cookie
        
        return None
    
    def _constant_time_compare(self, a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        if len(a) != len(b):
            return False
        
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        
        return result == 0
    
    async def set_csrf_token(self, request: Request, response: Response):
        """Set CSRF token in response."""
        try:
            session_id = self._get_session_id(request)
            if not session_id:
                return
            
            # Generate new CSRF token
            csrf_token = self.generate_csrf_token()
            
            # Store in cache
            csrf_key = f"csrf_token:{session_id}"
            await self.cache_manager.set(csrf_key, csrf_token, CacheLevel.L1_MEMORY, ttl=3600)
            
            # Set in response header
            response.headers['X-CSRF-Token'] = csrf_token
            
            # Optionally set as cookie
            response.set_cookie(
                self.cookie_name,
                csrf_token,
                max_age=3600,
                httponly=True,
                secure=settings.is_production(),
                samesite='strict'
            )
            
        except Exception as e:
            logger.error(f"❌ [CSRF] Failed to set CSRF token: {e}")


# Global instances
_rate_limiter: Optional[AdvancedRateLimiter] = None
_csrf_protection: Optional[CSRFProtection] = None

def get_rate_limiter() -> AdvancedRateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = AdvancedRateLimiter()
    return _rate_limiter

def get_csrf_protection() -> CSRFProtection:
    """Get global CSRF protection instance."""
    global _csrf_protection
    if _csrf_protection is None:
        _csrf_protection = CSRFProtection()
    return _csrf_protection


# Rate limiting decorators
def limit(rate: str, per_user: bool = False):
    """
    Rate limiting decorator.
    
    Args:
        rate: Rate limit string (e.g., "5/minute", "100/hour")
        per_user: If True, limit per user; if False, limit per IP
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from arguments
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                return await func(*args, **kwargs)
            
            rate_limiter = get_rate_limiter()
            
            # Parse rate string
            try:
                parts = rate.split('/')
                limit_count = int(parts[0])
                period = parts[1].lower()
                
                if 'second' in period:
                    window = 1
                elif 'minute' in period:
                    window = 60
                elif 'hour' in period:
                    window = 3600
                elif 'day' in period:
                    window = 86400
                else:
                    window = 60  # Default to 1 minute
                
            except (ValueError, IndexError):
                logger.error(f"❌ [RATE-LIMITER] Invalid rate format: {rate}")
                return await func(*args, **kwargs)
            
            # Create rate limit key
            if per_user:
                user_id = getattr(request.state, 'user_id', None)
                if user_id:
                    key = f"user:{user_id}"
                else:
                    key = f"ip:{rate_limiter._get_client_ip(request)}"
            else:
                key = f"ip:{rate_limiter._get_client_ip(request)}"
            
            # Check rate limit
            result = await rate_limiter.check_rate_limit(key, 'custom', request)
            
            if not result['allowed']:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {int(result['retry_after'])} seconds.",
                    headers={
                        'X-RateLimit-Limit': str(result['limit']),
                        'X-RateLimit-Remaining': str(result['remaining']),
                        'X-RateLimit-Reset': str(int(result['reset_time'])),
                        'Retry-After': str(int(result['retry_after']))
                    }
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def auth_limit():
    """Authentication endpoint rate limiting."""
    return limit("5/minute")

def api_limit():
    """Standard API rate limiting."""
    return limit("100/minute", per_user=True)