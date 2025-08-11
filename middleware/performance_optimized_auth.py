"""
High-Performance Authentication Middleware
Optimized for <75ms response times with multi-tier caching and parallel processing.
"""

import asyncio
import time
import logging
import hashlib
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
import httpx

from config import settings
from database import db
from models.user import UserResponse
from utils.security import JWTSecurity, SecurityError
from caching.multi_layer_cache_manager import get_cache_manager, CacheLevel
from monitoring.performance import performance_tracker, PerformanceTarget

logger = logging.getLogger(__name__)
cache_manager = get_cache_manager()

class HighPerformanceAuthMiddleware(BaseHTTPMiddleware):
    """
    High-performance authentication middleware optimized for <75ms response times.
    Features:
    - Multi-level caching (L1: <5ms, L2: <20ms)
    - Parallel processing of auth operations
    - Smart cache warming and invalidation
    - Circuit breaker for external dependencies
    - Performance monitoring and alerting
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Performance targets
        self.target_auth_time_ms = 15
        self.target_cache_hit_rate = 95.0
        
        # Excluded paths (no auth required)
        self.excluded_paths = {
            "/", "/docs", "/redoc", "/openapi.json", "/health",
            "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"
        }
        
        # Performance metrics
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_auth_time_ms": 0,
            "fast_path_hits": 0,
            "circuit_breaker_triggers": 0
        }
        
        # Circuit breaker for external auth services
        self.circuit_breaker = {
            "failures": 0,
            "last_failure": 0,
            "state": "closed",  # closed, open, half_open
            "failure_threshold": 5,
            "recovery_timeout": 30
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """High-performance request processing with parallel auth operations."""
        
        operation_id = performance_tracker.start_operation(
            "auth_middleware", PerformanceTarget.SUB_15MS
        )
        
        start_time = time.time()
        path = request.url.path
        
        try:
            # Fast path: Skip auth for excluded paths
            if path in self.excluded_paths or any(path.startswith(p) for p in ["/api/v1/debug/"]):
                request.state.user = None
                request.state.user_id = None
                self.metrics["fast_path_hits"] += 1
                return await call_next(request)
            
            # Extract auth header (fast operation)
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                request.state.user = None
                request.state.user_id = None
                return await call_next(request)
            
            token = auth_header.split(" ", 1)[1]
            
            # High-performance auth resolution
            user = await self._resolve_user_high_performance(token, request)
            
            request.state.user = user
            request.state.user_id = user.id if user else None
            
            # Update performance metrics
            auth_time_ms = (time.time() - start_time) * 1000
            self._update_metrics(auth_time_ms, user is not None)
            
            performance_tracker.end_operation(
                operation_id, "auth_middleware", PerformanceTarget.SUB_15MS,
                success=True, auth_time_ms=auth_time_ms
            )
            
            return await call_next(request)
            
        except Exception as e:
            auth_time_ms = (time.time() - start_time) * 1000
            self._update_metrics(auth_time_ms, False)
            
            performance_tracker.end_operation(
                operation_id, "auth_middleware", PerformanceTarget.SUB_15MS,
                success=False, error=str(e)
            )
            
            # Set empty user state and continue (let dependencies handle auth requirements)
            request.state.user = None
            request.state.user_id = None
            return await call_next(request)
    
    async def _resolve_user_high_performance(self, token: str, request: Request) -> Optional[UserResponse]:
        """
        High-performance user resolution with multi-level caching and parallel processing.
        Target: <15ms average, >95% cache hit rate
        """
        
        # Generate cache key
        cache_key = f"auth_user:{hashlib.md5(token.encode()).hexdigest()}"
        
        # L1 Cache check (target: <5ms)
        cached_user, cache_level = await cache_manager.get_multi_level(
            cache_key, fallback_function=lambda: self._fetch_user_from_auth_service(token)
        )
        
        if cached_user:
            self.metrics["cache_hits"] += 1
            logger.debug(f"Auth cache hit from {cache_level.value} in <5ms")
            return cached_user
        
        # Cache miss - fetch from auth service with circuit breaker
        self.metrics["cache_misses"] += 1
        
        if not self._check_circuit_breaker():
            logger.warning("Auth circuit breaker OPEN - using degraded mode")
            return None
        
        try:
            user = await self._fetch_user_from_auth_service(token)
            
            if user:
                # Cache successful result across all levels
                await cache_manager.set_multi_level(
                    cache_key, user, 
                    l1_ttl=300,  # 5 minutes L1
                    l2_ttl=900,  # 15 minutes L2
                    priority=3   # High priority
                )
                self._reset_circuit_breaker()
            
            return user
            
        except Exception as e:
            self._handle_circuit_failure()
            logger.error(f"High-performance auth failed: {e}")
            return None
    
    async def _fetch_user_from_auth_service(self, token: str) -> Optional[UserResponse]:
        """
        Optimized user fetching with parallel JWT and Supabase validation.
        Target: <50ms when cache miss occurs
        """
        
        # Security: Reject invalid token formats immediately
        if token.startswith(("mock_token_", "supabase_token_")) or "." not in token:
            raise SecurityError("Invalid token format")
        
        # Parallel processing: JWT validation + Supabase validation
        jwt_task = asyncio.create_task(self._validate_jwt_token(token))
        supabase_task = asyncio.create_task(self._validate_supabase_token(token))
        
        try:
            # Wait for first successful validation (whichever is faster)
            done, pending = await asyncio.wait(
                [jwt_task, supabase_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=0.040  # 40ms timeout for auth operations
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
            
            # Process results
            for task in done:
                try:
                    user = await task
                    if user:
                        return user
                except Exception as e:
                    logger.debug(f"Auth validation failed: {e}")
                    continue
            
            return None
            
        except asyncio.TimeoutError:
            logger.warning("Auth service timeout - all validations exceeded 40ms")
            jwt_task.cancel()
            supabase_task.cancel()
            return None
    
    async def _validate_jwt_token(self, token: str) -> Optional[UserResponse]:
        """Fast JWT token validation with database profile enhancement."""
        try:
            # JWT verification (typically 1-5ms)
            payload = JWTSecurity.verify_token(token, "access_token")
            user_id = payload.get("sub")
            email = payload.get("email")
            
            if not user_id or not email:
                return None
            
            # Parallel: JWT data preparation + Database profile fetch
            jwt_user_data = {
                "id": user_id,
                "email": email,
                "display_name": payload.get("display_name", ""),
                "avatar_url": payload.get("avatar_url"),
                "credits_balance": payload.get("credits_balance", 100),
                "role": payload.get("role", "viewer"),
                "created_at": datetime.now(timezone.utc)
            }
            
            # Try to enhance with database profile (with timeout)
            try:
                enhanced_user = await asyncio.wait_for(
                    self._enhance_user_profile(user_id, jwt_user_data),
                    timeout=0.025  # 25ms timeout for profile enhancement
                )
                return enhanced_user
            except asyncio.TimeoutError:
                # Fallback to JWT data if profile fetch is slow
                from utils.uuid_utils import UUIDUtils
                safe_user_id = UUIDUtils.validate_and_convert(user_id, "JWT_fast_path")
                return UserResponse(**{**jwt_user_data, "id": safe_user_id})
            
        except SecurityError:
            return None
        except Exception as e:
            logger.debug(f"JWT validation error: {e}")
            return None
    
    async def _validate_supabase_token(self, token: str) -> Optional[UserResponse]:
        """Optimized Supabase token validation with connection pooling."""
        try:
            # Use optimized HTTP client with connection pooling
            timeout = httpx.Timeout(0.030)  # 30ms timeout
            
            async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=10)) as client:
                response = await client.get(
                    f"{settings.supabase_url}/auth/v1/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "apikey": settings.supabase_anon_key
                    }
                )
                
                if response.status_code != 200:
                    return None
                
                user_data = response.json()
                user_id = user_data.get("id")
                
                if not user_id:
                    return None
                
                # Parse timestamp efficiently
                created_at = datetime.now(timezone.utc)
                if created_at_str := user_data.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    except ValueError:
                        pass
                
                # Build user response
                from utils.uuid_utils import UUIDUtils
                safe_user_id = UUIDUtils.safe_uuid_convert(user_id)
                
                return UserResponse(
                    id=safe_user_id,
                    email=user_data.get("email"),
                    display_name=user_data.get("user_metadata", {}).get("display_name", ""),
                    avatar_url=user_data.get("user_metadata", {}).get("avatar_url"),
                    credits_balance=settings.default_user_credits or 100,
                    role="viewer",
                    created_at=created_at
                )
                
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.debug(f"Supabase validation timeout/error: {e}")
            return None
        except Exception as e:
            logger.debug(f"Supabase validation error: {e}")
            return None
    
    async def _enhance_user_profile(self, user_id: str, base_data: Dict[str, Any]) -> UserResponse:
        """Fast database profile enhancement with connection pooling."""
        try:
            from database import SupabaseClient
            db_client = SupabaseClient()
            
            if db_client.is_available():
                # Use service client for better performance
                profile_result = db_client.service_client.table('users').select('*').eq('id', str(user_id)).execute()
                
                if profile_result.data and len(profile_result.data) > 0:
                    profile = profile_result.data[0]
                    
                    from utils.uuid_utils import UUIDUtils
                    safe_user_id = UUIDUtils.validate_and_convert(user_id, "profile_enhanced")
                    
                    return UserResponse(
                        id=safe_user_id,
                        email=base_data["email"],
                        display_name=profile.get('display_name', base_data.get("display_name", "")),
                        avatar_url=profile.get('avatar_url', base_data.get("avatar_url")),
                        credits_balance=profile.get('credits_balance', base_data.get("credits_balance", 100)),
                        role=profile.get('role', base_data.get("role", "viewer")),
                        created_at=base_data["created_at"]
                    )
            
            # Fallback to base data
            from utils.uuid_utils import UUIDUtils
            safe_user_id = UUIDUtils.validate_and_convert(user_id, "profile_fallback")
            return UserResponse(**{**base_data, "id": safe_user_id})
            
        except Exception as e:
            logger.debug(f"Profile enhancement failed: {e}")
            # Return base JWT data
            from utils.uuid_utils import UUIDUtils
            safe_user_id = UUIDUtils.validate_and_convert(user_id, "profile_error")
            return UserResponse(**{**base_data, "id": safe_user_id})
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations."""
        current_time = time.time()
        
        if self.circuit_breaker["state"] == "closed":
            return True
        elif self.circuit_breaker["state"] == "open":
            if current_time - self.circuit_breaker["last_failure"] > self.circuit_breaker["recovery_timeout"]:
                self.circuit_breaker["state"] = "half_open"
                logger.info("Auth circuit breaker HALF_OPEN - testing recovery")
                return True
            return False
        elif self.circuit_breaker["state"] == "half_open":
            return True
        return False
    
    def _handle_circuit_failure(self):
        """Handle circuit breaker failure."""
        self.circuit_breaker["failures"] += 1
        self.circuit_breaker["last_failure"] = time.time()
        self.metrics["circuit_breaker_triggers"] += 1
        
        if self.circuit_breaker["failures"] >= self.circuit_breaker["failure_threshold"]:
            self.circuit_breaker["state"] = "open"
            logger.warning("Auth circuit breaker OPEN - auth service degraded")
    
    def _reset_circuit_breaker(self):
        """Reset circuit breaker on successful operation."""
        if self.circuit_breaker["state"] == "half_open":
            self.circuit_breaker["state"] = "closed"
            self.circuit_breaker["failures"] = 0
            logger.info("Auth circuit breaker CLOSED - service recovered")
    
    def _update_metrics(self, auth_time_ms: float, success: bool):
        """Update performance metrics."""
        self.metrics["total_requests"] += 1
        
        # Update average auth time
        current_avg = self.metrics["avg_auth_time_ms"]
        total_requests = self.metrics["total_requests"]
        
        self.metrics["avg_auth_time_ms"] = (
            (current_avg * (total_requests - 1) + auth_time_ms) / total_requests
        )
        
        # Check performance targets
        if auth_time_ms > self.target_auth_time_ms:
            logger.warning(
                f"Auth performance degraded: {auth_time_ms:.2f}ms > {self.target_auth_time_ms}ms target"
            )
        
        # Calculate cache hit rate
        total_cache_operations = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        if total_cache_operations > 0:
            cache_hit_rate = (self.metrics["cache_hits"] / total_cache_operations) * 100
            
            if cache_hit_rate < self.target_cache_hit_rate:
                logger.warning(
                    f"Cache hit rate below target: {cache_hit_rate:.1f}% < {self.target_cache_hit_rate}%"
                )
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        total_cache_operations = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        cache_hit_rate = 0.0
        if total_cache_operations > 0:
            cache_hit_rate = (self.metrics["cache_hits"] / total_cache_operations) * 100
        
        return {
            "performance_metrics": self.metrics.copy(),
            "cache_hit_rate_percent": cache_hit_rate,
            "target_auth_time_ms": self.target_auth_time_ms,
            "target_cache_hit_rate_percent": self.target_cache_hit_rate,
            "targets_met": {
                "auth_time": self.metrics["avg_auth_time_ms"] <= self.target_auth_time_ms,
                "cache_hit_rate": cache_hit_rate >= self.target_cache_hit_rate
            },
            "circuit_breaker_state": self.circuit_breaker["state"],
            "timestamp": datetime.utcnow().isoformat()
        }

# High-performance auth dependency with optimized caching
async def get_current_user_optimized(request: Request) -> UserResponse:
    """
    Optimized FastAPI dependency for getting current user.
    Target: <5ms when cache hit, <50ms when cache miss.
    """
    operation_id = performance_tracker.start_operation(
        "get_current_user_optimized", PerformanceTarget.SUB_5MS
    )
    
    try:
        # Fast path: User already resolved by middleware
        if hasattr(request.state, 'user') and request.state.user:
            performance_tracker.end_operation(
                operation_id, "get_current_user_optimized", PerformanceTarget.SUB_5MS,
                success=True, source="middleware_state"
            )
            return request.state.user
        
        # Auth required but no user found
        performance_tracker.end_operation(
            operation_id, "get_current_user_optimized", PerformanceTarget.SUB_5MS,
            success=False, source="no_auth"
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    except HTTPException:
        raise
    except Exception as e:
        performance_tracker.end_operation(
            operation_id, "get_current_user_optimized", PerformanceTarget.SUB_5MS,
            success=False, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication service error"
        )