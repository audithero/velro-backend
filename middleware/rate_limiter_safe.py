"""
Safe rate limiter with Redis fallback to in-memory or noop.
Never breaks the request path.
"""
import time
import logging
from typing import Dict, Optional
from collections import defaultdict
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from fastapi.responses import JSONResponse
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with graceful degradation."""
    
    def __init__(self, app: ASGIApp, redis_url: str = None, default_limit: str = "100/minute"):
        super().__init__(app)
        self.redis_url = redis_url
        self.redis_client = None
        self.default_limit = self._parse_limit(default_limit)
        self.memory_store: Dict[str, list] = defaultdict(list)
        self.backend_type = "noop"
        
        # Try to initialize Redis
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                self.backend_type = "redis"
                logger.info("✅ [RateLimit] Using Redis backend")
            except Exception as e:
                logger.warning(f"⚠️ [RateLimit] Redis init failed, using memory: {e}")
                self.backend_type = "memory"
        else:
            logger.info("ℹ️ [RateLimit] No Redis URL, using memory backend")
            self.backend_type = "memory"
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        request_id = getattr(request.state, "request_id", "unknown")
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/__health", "/__version"]:
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Check rate limit
        allowed, remaining, reset_time = await self._check_rate_limit(client_id)
        
        if not allowed:
            logger.warning(f"[{request_id}] Rate limit exceeded for {client_id}")
            return self._rate_limit_response(request_id, remaining, reset_time)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.default_limit[0])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_time))
        
        return response
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Prefer user ID if authenticated
        if hasattr(request.state, "user_id") and request.state.user_id:
            return f"user:{request.state.user_id}"
        
        # Fall back to IP
        if request.client:
            return f"ip:{request.client.host}"
        
        return "unknown"
    
    async def _check_rate_limit(self, client_id: str) -> tuple[bool, int, float]:
        """Check if client has exceeded rate limit."""
        limit, window = self.default_limit
        now = time.time()
        
        if self.backend_type == "noop":
            # No rate limiting
            return True, limit, now + window
        
        elif self.backend_type == "redis":
            try:
                return await self._check_redis(client_id, limit, window)
            except Exception as e:
                logger.error(f"Redis error, falling back to memory: {e}")
                self.backend_type = "memory"
                # Fall through to memory
        
        # Memory backend
        return self._check_memory(client_id, limit, window, now)
    
    async def _check_redis(self, client_id: str, limit: int, window: int) -> tuple[bool, int, float]:
        """Check rate limit using Redis."""
        key = f"rate_limit:{client_id}"
        now = time.time()
        window_start = now - window
        
        # Remove old entries
        await self.redis_client.zremrangebyscore(key, 0, window_start)
        
        # Count requests in window
        count = await self.redis_client.zcard(key)
        
        if count >= limit:
            # Get oldest entry to determine reset time
            oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
            reset_time = oldest[0][1] + window if oldest else now + window
            return False, 0, reset_time
        
        # Add current request
        await self.redis_client.zadd(key, {str(now): now})
        await self.redis_client.expire(key, window)
        
        return True, limit - count - 1, now + window
    
    def _check_memory(self, client_id: str, limit: int, window: int, now: float) -> tuple[bool, int, float]:
        """Check rate limit using in-memory store."""
        window_start = now - window
        
        # Clean old entries
        self.memory_store[client_id] = [
            ts for ts in self.memory_store[client_id] if ts > window_start
        ]
        
        # Check limit
        count = len(self.memory_store[client_id])
        if count >= limit:
            reset_time = self.memory_store[client_id][0] + window
            return False, 0, reset_time
        
        # Add current request
        self.memory_store[client_id].append(now)
        
        return True, limit - count - 1, now + window
    
    def _parse_limit(self, limit_str: str) -> tuple[int, int]:
        """Parse limit string like '100/minute' to (count, seconds)."""
        try:
            count, period = limit_str.split("/")
            count = int(count)
            
            periods = {
                "second": 1,
                "minute": 60,
                "hour": 3600,
                "day": 86400,
            }
            
            # Handle plural
            period = period.rstrip("s")
            seconds = periods.get(period, 60)
            
            return count, seconds
        except:
            return 100, 60  # Default: 100 per minute
    
    def _rate_limit_response(self, request_id: str, remaining: int, reset_time: float) -> Response:
        """Return 429 Too Many Requests response."""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded",
                "request_id": request_id,
                "error": "rate_limit_exceeded",
            },
            headers={
                "X-Request-ID": request_id,
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(reset_time)),
                "Retry-After": str(int(reset_time - time.time())),
            }
        )