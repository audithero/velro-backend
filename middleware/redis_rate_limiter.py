"""
Enterprise Redis Rate Limiting Middleware
Implements distributed rate limiting with sliding window algorithm and circuit breaker protection.
Follows PRD.MD Section 2.3.3 rate limits (Free: 10/min, Pro: 50/min, Enterprise: 200/min)
"""

import asyncio
import logging
import time
import hashlib
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json
import uuid

try:
    import redis.asyncio as redis
    from redis.exceptions import ConnectionError, TimeoutError, RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    RedisError = Exception

from fastapi import Request, HTTPException
from config import settings
from monitoring.metrics import metrics_collector
from utils.exceptions import RateLimitExceededError, SecurityViolationError

logger = logging.getLogger(__name__)


class SubscriptionTier(Enum):
    """User subscription tiers with rate limits"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class RateLimitType(Enum):
    """Types of rate limiting"""
    API_REQUESTS = "api_requests"
    AUTH_ATTEMPTS = "auth_attempts"
    GENERATION_REQUESTS = "generation_requests"
    MEDIA_ACCESS = "media_access"


@dataclass
class RateLimitConfig:
    """Rate limit configuration per tier and type"""
    requests_per_minute: int
    burst_capacity: int
    window_size_seconds: int = 60
    penalty_duration_seconds: int = 300  # 5 minutes


@dataclass
class RateLimitResult:
    """Result of rate limit check"""
    allowed: bool
    remaining: int
    reset_time: int
    retry_after: Optional[int] = None
    tier: Optional[str] = None
    violation_count: int = 0


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Failing, reject all requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    recovery_timeout: int = 30
    success_threshold: int = 3  # Successes needed to close from half-open


class RedisRateLimiter:
    """
    Enterprise Redis-based rate limiter with sliding window algorithm.
    Implements distributed rate limiting with circuit breaker protection.
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or getattr(settings, 'redis_url', 'redis://localhost:6379')
        self.redis_client: Optional[redis.Redis] = None
        self.key_prefix = "velro:rate_limit:"
        
        # Circuit breaker state
        self.circuit_state = CircuitBreakerState.CLOSED
        self.circuit_failures = 0
        self.circuit_last_failure = 0
        self.circuit_success_count = 0
        self.circuit_config = CircuitBreakerConfig()
        
        # Rate limit configurations per subscription tier
        self.rate_limits = {
            # API Requests
            (SubscriptionTier.FREE, RateLimitType.API_REQUESTS): RateLimitConfig(
                requests_per_minute=10, burst_capacity=20
            ),
            (SubscriptionTier.PRO, RateLimitType.API_REQUESTS): RateLimitConfig(
                requests_per_minute=50, burst_capacity=100
            ),
            (SubscriptionTier.ENTERPRISE, RateLimitType.API_REQUESTS): RateLimitConfig(
                requests_per_minute=200, burst_capacity=400
            ),
            
            # Authentication Attempts (stricter limits)
            (SubscriptionTier.FREE, RateLimitType.AUTH_ATTEMPTS): RateLimitConfig(
                requests_per_minute=5, burst_capacity=10, penalty_duration_seconds=900  # 15 min penalty
            ),
            (SubscriptionTier.PRO, RateLimitType.AUTH_ATTEMPTS): RateLimitConfig(
                requests_per_minute=10, burst_capacity=20, penalty_duration_seconds=600  # 10 min penalty
            ),
            (SubscriptionTier.ENTERPRISE, RateLimitType.AUTH_ATTEMPTS): RateLimitConfig(
                requests_per_minute=20, burst_capacity=40, penalty_duration_seconds=300  # 5 min penalty
            ),
            
            # Generation Requests (resource intensive)
            (SubscriptionTier.FREE, RateLimitType.GENERATION_REQUESTS): RateLimitConfig(
                requests_per_minute=5, burst_capacity=10
            ),
            (SubscriptionTier.PRO, RateLimitType.GENERATION_REQUESTS): RateLimitConfig(
                requests_per_minute=25, burst_capacity=50
            ),
            (SubscriptionTier.ENTERPRISE, RateLimitType.GENERATION_REQUESTS): RateLimitConfig(
                requests_per_minute=100, burst_capacity=200
            ),
            
            # Media Access (high frequency)
            (SubscriptionTier.FREE, RateLimitType.MEDIA_ACCESS): RateLimitConfig(
                requests_per_minute=30, burst_capacity=60
            ),
            (SubscriptionTier.PRO, RateLimitType.MEDIA_ACCESS): RateLimitConfig(
                requests_per_minute=150, burst_capacity=300
            ),
            (SubscriptionTier.ENTERPRISE, RateLimitType.MEDIA_ACCESS): RateLimitConfig(
                requests_per_minute=500, burst_capacity=1000
            )
        }
        
        # Metrics tracking
        self.metrics = {
            "total_requests": 0,
            "allowed_requests": 0,
            "denied_requests": 0,
            "circuit_breaker_trips": 0,
            "redis_errors": 0
        }
        
        # Initialize Redis connection
        if REDIS_AVAILABLE:
            asyncio.create_task(self._initialize_redis())
    
    async def _initialize_redis(self):
        """Initialize Redis connection with error handling"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                retry_on_timeout=True,
                health_check_interval=30,
                max_connections=20
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info(f"Redis rate limiter initialized: {self.redis_url}")
            
        except Exception as e:
            logger.error(f"Redis rate limiter initialization failed: {e}")
            self._handle_circuit_failure()
    
    def _handle_circuit_failure(self):
        """Handle circuit breaker failure"""
        self.circuit_failures += 1
        self.circuit_last_failure = time.time()
        
        if self.circuit_failures >= self.circuit_config.failure_threshold:
            self.circuit_state = CircuitBreakerState.OPEN
            self.metrics["circuit_breaker_trips"] += 1
            logger.warning(f"Rate limiter circuit breaker OPEN - operations suspended")
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations"""
        if self.circuit_state == CircuitBreakerState.CLOSED:
            return True
        elif self.circuit_state == CircuitBreakerState.OPEN:
            if time.time() - self.circuit_last_failure > self.circuit_config.recovery_timeout:
                self.circuit_state = CircuitBreakerState.HALF_OPEN
                self.circuit_success_count = 0
                logger.info("Rate limiter circuit breaker HALF_OPEN - testing recovery")
                return True
            return False
        elif self.circuit_state == CircuitBreakerState.HALF_OPEN:
            return True
        return False
    
    def _handle_circuit_success(self):
        """Handle successful circuit breaker operation"""
        if self.circuit_state == CircuitBreakerState.HALF_OPEN:
            self.circuit_success_count += 1
            if self.circuit_success_count >= self.circuit_config.success_threshold:
                self.circuit_state = CircuitBreakerState.CLOSED
                self.circuit_failures = 0
                logger.info("Rate limiter circuit breaker CLOSED - operations restored")
    
    async def check_rate_limit(
        self,
        identifier: str,
        tier: SubscriptionTier,
        limit_type: RateLimitType,
        client_ip: Optional[str] = None
    ) -> RateLimitResult:
        """
        Check rate limit using sliding window algorithm.
        
        Args:
            identifier: User ID or unique identifier
            tier: User subscription tier
            limit_type: Type of operation being rate limited
            client_ip: Client IP address for additional tracking
            
        Returns:
            RateLimitResult with allow/deny decision and metadata
        """
        self.metrics["total_requests"] += 1
        
        # Check circuit breaker first
        if not self._check_circuit_breaker():
            logger.warning(f"Rate limit check blocked by circuit breaker for {identifier}")
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=int(time.time() + self.circuit_config.recovery_timeout),
                retry_after=self.circuit_config.recovery_timeout,
                tier=tier.value
            )
        
        # Get rate limit configuration
        config_key = (tier, limit_type)
        if config_key not in self.rate_limits:
            # Default to free tier limits for unknown configurations
            config_key = (SubscriptionTier.FREE, limit_type)
        
        config = self.rate_limits.get(config_key)
        if not config:
            logger.error(f"No rate limit config found for tier {tier} and type {limit_type}")
            return RateLimitResult(allowed=True, remaining=999, reset_time=0)
        
        # Check Redis-based rate limiting
        if self.redis_client:
            try:
                result = await self._check_redis_rate_limit(identifier, config, limit_type, client_ip)
                self._handle_circuit_success()
                return result
            except Exception as e:
                logger.error(f"Redis rate limit check failed: {e}")
                self.metrics["redis_errors"] += 1
                self._handle_circuit_failure()
                # Fall back to in-memory rate limiting
                return await self._check_memory_rate_limit(identifier, config, limit_type)
        else:
            # Use in-memory rate limiting as fallback
            return await self._check_memory_rate_limit(identifier, config, limit_type)
    
    async def _check_redis_rate_limit(
        self,
        identifier: str,
        config: RateLimitConfig,
        limit_type: RateLimitType,
        client_ip: Optional[str] = None
    ) -> RateLimitResult:
        """Check rate limit using Redis sliding window algorithm"""
        current_time = int(time.time())
        window_start = current_time - config.window_size_seconds
        
        # Create unique key for this identifier and limit type
        key = f"{self.key_prefix}{identifier}:{limit_type.value}"
        penalty_key = f"{key}:penalty"
        
        # Check if user is in penalty period
        penalty_until = await self.redis_client.get(penalty_key)
        if penalty_until and int(penalty_until) > current_time:
            remaining_penalty = int(penalty_until) - current_time
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=int(penalty_until),
                retry_after=remaining_penalty,
                tier=None,
                violation_count=1
            )
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis_client.pipeline()
        
        # Remove expired entries from sorted set
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests in window
        pipe.zcard(key)
        
        # Add current request with unique ID to prevent duplicates
        request_id = f"{current_time}:{uuid.uuid4().hex[:8]}"
        pipe.zadd(key, {request_id: current_time})
        
        # Set expiration for cleanup
        pipe.expire(key, config.window_size_seconds + 60)
        
        # Execute pipeline
        results = await pipe.execute()
        current_count = results[1] + 1  # Count after adding current request
        
        # Check against burst capacity first
        if current_count > config.burst_capacity:
            # Apply penalty for burst violations
            penalty_until_time = current_time + config.penalty_duration_seconds
            await self.redis_client.setex(penalty_key, config.penalty_duration_seconds, penalty_until_time)
            
            # Remove the request we just added since it's denied
            await self.redis_client.zrem(key, request_id)
            
            self.metrics["denied_requests"] += 1
            
            # Log security violation
            await self._log_rate_limit_violation(identifier, limit_type, current_count, config.burst_capacity, client_ip)
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=penalty_until_time,
                retry_after=config.penalty_duration_seconds,
                violation_count=current_count - config.burst_capacity
            )
        
        # Check against per-minute rate limit
        if current_count > config.requests_per_minute:
            # Remove the request we just added since it's denied
            await self.redis_client.zrem(key, request_id)
            
            self.metrics["denied_requests"] += 1
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=current_time + config.window_size_seconds,
                retry_after=config.window_size_seconds
            )
        
        # Request allowed
        self.metrics["allowed_requests"] += 1
        remaining = max(0, config.requests_per_minute - current_count)
        
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_time=current_time + config.window_size_seconds
        )
    
    async def _check_memory_rate_limit(
        self,
        identifier: str,
        config: RateLimitConfig,
        limit_type: RateLimitType
    ) -> RateLimitResult:
        """Fallback in-memory rate limiting when Redis is unavailable"""
        # Simple in-memory implementation (not distributed)
        # This is a fallback and should only be used when Redis is down
        
        if not hasattr(self, '_memory_limits'):
            self._memory_limits = {}
        
        current_time = time.time()
        key = f"{identifier}:{limit_type.value}"
        
        if key not in self._memory_limits:
            self._memory_limits[key] = []
        
        # Clean old entries
        window_start = current_time - config.window_size_seconds
        self._memory_limits[key] = [
            t for t in self._memory_limits[key] if t > window_start
        ]
        
        current_count = len(self._memory_limits[key])
        
        if current_count >= config.requests_per_minute:
            self.metrics["denied_requests"] += 1
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=int(current_time + config.window_size_seconds),
                retry_after=config.window_size_seconds
            )
        
        # Add current request
        self._memory_limits[key].append(current_time)
        self.metrics["allowed_requests"] += 1
        
        return RateLimitResult(
            allowed=True,
            remaining=config.requests_per_minute - current_count - 1,
            reset_time=int(current_time + config.window_size_seconds)
        )
    
    async def _log_rate_limit_violation(
        self,
        identifier: str,
        limit_type: RateLimitType,
        actual_count: int,
        limit: int,
        client_ip: Optional[str] = None
    ):
        """Log rate limit violations for security monitoring"""
        violation_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "identifier": identifier,
            "client_ip": client_ip,
            "limit_type": limit_type.value,
            "actual_count": actual_count,
            "limit": limit,
            "severity": "HIGH" if actual_count > limit * 2 else "MEDIUM"
        }
        
        logger.warning(f"Rate limit violation: {json.dumps(violation_data)}")
        
        # Store violation in Redis for monitoring
        if self.redis_client:
            try:
                violation_key = f"velro:security:rate_violations:{identifier}"
                await self.redis_client.lpush(violation_key, json.dumps(violation_data))
                await self.redis_client.ltrim(violation_key, 0, 99)  # Keep last 100 violations
                await self.redis_client.expire(violation_key, 86400 * 7)  # 7 days
            except Exception as e:
                logger.error(f"Failed to log rate limit violation: {e}")
    
    async def get_user_subscription_tier(self, user_id: str) -> SubscriptionTier:
        """Get user's subscription tier from database or cache"""
        try:
            # Try cache first
            if self.redis_client:
                cached_tier = await self.redis_client.get(f"velro:user_tier:{user_id}")
                if cached_tier:
                    return SubscriptionTier(cached_tier)
            
            # TODO: Implement database lookup for user subscription tier
            # For now, default to FREE tier
            # This would typically query the users table for subscription_tier field
            
            # Cache the result
            if self.redis_client:
                await self.redis_client.setex(f"velro:user_tier:{user_id}", 300, SubscriptionTier.FREE.value)
            
            return SubscriptionTier.FREE
            
        except Exception as e:
            logger.error(f"Failed to get user subscription tier for {user_id}: {e}")
            return SubscriptionTier.FREE
    
    async def whitelist_user(self, user_id: str, duration_seconds: int = 3600):
        """Temporarily whitelist a user (for admin overrides)"""
        if self.redis_client:
            try:
                whitelist_key = f"velro:rate_limit:whitelist:{user_id}"
                await self.redis_client.setex(whitelist_key, duration_seconds, "whitelisted")
                logger.info(f"User {user_id} whitelisted for {duration_seconds} seconds")
            except Exception as e:
                logger.error(f"Failed to whitelist user {user_id}: {e}")
    
    async def is_whitelisted(self, user_id: str) -> bool:
        """Check if user is whitelisted"""
        if self.redis_client:
            try:
                return bool(await self.redis_client.get(f"velro:rate_limit:whitelist:{user_id}"))
            except Exception as e:
                logger.error(f"Failed to check whitelist status for {user_id}: {e}")
        return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get rate limiter metrics"""
        return {
            **self.metrics,
            "circuit_breaker_state": self.circuit_state.value,
            "circuit_failures": self.circuit_failures,
            "redis_available": self.redis_client is not None,
            "rate_limit_configs_count": len(self.rate_limits)
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        if not self.redis_client:
            return {"status": "degraded", "redis": False, "fallback": "memory"}
        
        try:
            start_time = time.time()
            await self.redis_client.ping()
            ping_time = (time.time() - start_time) * 1000
            
            return {
                "status": "healthy",
                "redis": True,
                "ping_time_ms": ping_time,
                "circuit_breaker_state": self.circuit_state.value
            }
        except Exception as e:
            return {
                "status": "unhealthy", 
                "redis": False, 
                "error": str(e),
                "fallback": "memory"
            }


# Global rate limiter instance
redis_rate_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter() -> RedisRateLimiter:
    """Get or create the global rate limiter instance"""
    global redis_rate_limiter
    if redis_rate_limiter is None:
        redis_rate_limiter = RedisRateLimiter()
    return redis_rate_limiter


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware for rate limiting"""
    # Skip rate limiting for health checks and static assets
    if request.url.path in ["/health", "/metrics", "/favicon.ico"] or request.url.path.startswith("/static"):
        return await call_next(request)
    
    rate_limiter = get_rate_limiter()
    
    # Extract user information from request
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        # Use IP address for unauthenticated requests
        client_ip = request.client.host if request.client else "unknown"
        user_id = f"ip:{client_ip}"
    else:
        user_id = str(user_id)
        client_ip = request.client.host if request.client else None
    
    # Determine rate limit type based on endpoint
    path = request.url.path
    if path.startswith("/auth"):
        limit_type = RateLimitType.AUTH_ATTEMPTS
    elif path.startswith("/api/generations"):
        limit_type = RateLimitType.GENERATION_REQUESTS
    elif path.startswith("/api/media"):
        limit_type = RateLimitType.MEDIA_ACCESS
    else:
        limit_type = RateLimitType.API_REQUESTS
    
    # Check if user is whitelisted
    if await rate_limiter.is_whitelisted(user_id):
        return await call_next(request)
    
    # Get user subscription tier
    tier = await rate_limiter.get_user_subscription_tier(user_id)
    
    # Check rate limit
    result = await rate_limiter.check_rate_limit(user_id, tier, limit_type, client_ip)
    
    if not result.allowed:
        # Add rate limit headers
        headers = {
            "X-RateLimit-Limit": str(rate_limiter.rate_limits[(tier, limit_type)].requests_per_minute),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(result.reset_time)
        }
        
        if result.retry_after:
            headers["Retry-After"] = str(result.retry_after)
        
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded for {limit_type.value}",
                "retry_after": result.retry_after,
                "tier": tier.value
            },
            headers=headers
        )
    
    # Add rate limit headers to successful responses
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(rate_limiter.rate_limits[(tier, limit_type)].requests_per_minute)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(result.reset_time)
    
    return response