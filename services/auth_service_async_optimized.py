"""
Optimized Async Authentication Service with precise phase timing.
"""
import os
import asyncio
import httpx
import json
import base64
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import HTTPException, status

from models.user import UserCreate, UserResponse, UserLogin, Token, User
from config import settings
import uuid
import logging

logger = logging.getLogger(__name__)


class AsyncAuthService:
    """
    Fully async authentication service with phase timing and guaranteed timeouts.
    """
    
    # Circuit breaker state
    _consecutive_failures = 0
    _circuit_open = False
    _circuit_open_until = None
    
    def __init__(self):
        # HTTP/1.1 fallback support
        use_http1 = os.getenv("HTTP1_FALLBACK", "true").lower() in ("1", "true", "yes")
        
        # Configure httpx client with configurable timeouts
        supabase_timeout = float(os.getenv("AUTH_SUPABASE_TIMEOUT", "5.0"))
        self.timeout = httpx.Timeout(
            connect=3.0,
            read=supabase_timeout,
            write=2.0,
            pool=1.0
        )
        
        # Create async HTTP client
        auth_key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or settings.supabase_anon_key
        self.client = httpx.AsyncClient(
            base_url=settings.supabase_url,
            timeout=self.timeout,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0
            ),
            headers={
                "apikey": auth_key,
                "Content-Type": "application/json",
            },
            transport=httpx.AsyncHTTPTransport(retries=0),
            http2=not use_http1  # Use HTTP/1.1 if fallback enabled
        )
        
        # Service client for database operations (if needed)
        service_key = os.getenv("SUPABASE_SECRET_KEY") or settings.supabase_service_role_key
        if service_key:
            self.service_client = httpx.AsyncClient(
                base_url=f"{settings.supabase_url}/rest/v1",
                timeout=self.timeout,
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                },
                transport=httpx.AsyncHTTPTransport(retries=0),
                http2=not use_http1
            )
        else:
            self.service_client = None
            logger.warning("⚠️ [ASYNC-AUTH] No service key - profile operations disabled")
        
        logger.info(f"✅ [ASYNC-AUTH] Initialized (timeout={supabase_timeout}s, http1={use_http1})")
        
        # Start background probe
        asyncio.create_task(self._startup_probe())
    
    async def _startup_probe(self):
        """Quick probe to warm up connections."""
        try:
            # Quick auth settings check
            response = await self.client.get("/auth/v1/settings")
            logger.info(f"🔎 [ASYNC-AUTH] Startup probe: auth={response.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ [ASYNC-AUTH] Startup probe failed: {e}")
    
    async def authenticate_user(self, credentials: UserLogin) -> Optional[UserResponse]:
        """
        Authenticate user with precise phase timing.
        """
        # Timing configuration
        timing_enabled = os.getenv("AUTH_TIMING_ENABLED", "true").lower() in ("1", "true", "yes")
        request_id = str(uuid.uuid4())[:8]
        phase_times = {}
        
        t0 = time.perf_counter()
        
        try:
            # Phase A: Circuit breaker & validation
            t_phase = time.perf_counter()
            
            # Check circuit breaker
            if AsyncAuthService._circuit_open:
                if AsyncAuthService._circuit_open_until and time.time() < AsyncAuthService._circuit_open_until:
                    logger.warning(f"🔌 [ASYNC-AUTH] Circuit breaker OPEN (req:{request_id})")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Authentication service temporarily unavailable"
                    )
                else:
                    # Reset circuit breaker
                    AsyncAuthService._circuit_open = False
                    AsyncAuthService._consecutive_failures = 0
                    logger.info("🔌 [ASYNC-AUTH] Circuit breaker reset")
            
            phase_times['a_ms'] = (time.perf_counter() - t_phase) * 1000
            
            # Phase B: Supabase authentication call
            t_phase = time.perf_counter()
            
            auth_payload = {
                "email": credentials.email,
                "password": credentials.password
            }
            
            supabase_timeout = float(os.getenv("AUTH_SUPABASE_TIMEOUT", "5.0"))
            
            # Create cancellable task
            auth_task = asyncio.create_task(
                self.client.post(
                    "/auth/v1/token?grant_type=password",
                    json=auth_payload
                )
            )
            
            try:
                response = await asyncio.wait_for(auth_task, timeout=supabase_timeout)
            except asyncio.TimeoutError:
                auth_task.cancel()
                # Try to await cancellation
                try:
                    await auth_task
                except asyncio.CancelledError:
                    pass
                
                phase_times['b_ms'] = (time.perf_counter() - t_phase) * 1000
                
                # Update circuit breaker
                AsyncAuthService._consecutive_failures += 1
                if AsyncAuthService._consecutive_failures >= 3:
                    AsyncAuthService._circuit_open = True
                    AsyncAuthService._circuit_open_until = time.time() + 30
                    logger.error(f"🔌 [ASYNC-AUTH] Circuit breaker opened after {AsyncAuthService._consecutive_failures} failures")
                
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service timeout"
                )
            
            phase_times['b_ms'] = (time.perf_counter() - t_phase) * 1000
            
            # Reset circuit breaker on success
            AsyncAuthService._consecutive_failures = 0
            
            # Check response
            if response.status_code == 400:
                error_data = response.json()
                if "invalid_grant" in str(error_data):
                    logger.warning(f"🚫 [ASYNC-AUTH] Invalid credentials for {credentials.email}")
                    return None
            
            if response.status_code != 200:
                logger.error(f"❌ [ASYNC-AUTH] Auth failed: {response.status_code}")
                return None
            
            # Phase C: Token parsing & JWT processing
            t_phase = time.perf_counter()
            
            auth_data = response.json()
            access_token = auth_data.get("access_token")
            
            if not access_token:
                logger.error("❌ [ASYNC-AUTH] No access token")
                return None
            
            # Extract user info
            user_info = auth_data.get("user", {})
            if not user_info or not user_info.get("id"):
                # Try to decode JWT
                try:
                    parts = access_token.split('.')
                    payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                    user_id = payload.get("sub")
                    email = payload.get("email", credentials.email)
                except Exception as e:
                    logger.error(f"❌ [ASYNC-AUTH] JWT decode failed: {e}")
                    return None
            else:
                user_id = user_info.get("id")
                email = user_info.get("email", credentials.email)
            
            phase_times['c_ms'] = (time.perf_counter() - t_phase) * 1000
            
            # Phase D: Profile operations (skippable)
            t_phase = time.perf_counter()
            
            fast_login = os.getenv("AUTH_FAST_LOGIN", "true").lower() in ("1", "true", "yes")
            
            if fast_login:
                # Skip all profile operations
                logger.info(f"⚡ [ASYNC-AUTH] Fast login - skipping profile (req:{request_id})")
                user_profile = UserResponse(
                    id=UUID(user_id),
                    email=email,
                    display_name="",
                    avatar_url=None,
                    credits_balance=100,
                    role="viewer",
                    created_at=datetime.now(timezone.utc)
                )
            else:
                # Fetch profile (with timeout)
                if self.service_client:
                    try:
                        profile_response = await asyncio.wait_for(
                            self.service_client.get(
                                f"/users",
                                params={"id": f"eq.{user_id}", "select": "*"}
                            ),
                            timeout=1.0
                        )
                        
                        if profile_response.status_code == 200:
                            profiles = profile_response.json()
                            if profiles and len(profiles) > 0:
                                profile = profiles[0]
                                user_profile = UserResponse(
                                    id=UUID(profile["id"]),
                                    email=email,
                                    display_name=profile.get("display_name", ""),
                                    avatar_url=profile.get("avatar_url"),
                                    credits_balance=profile.get("credits_balance", 100),
                                    role=profile.get("role", "viewer"),
                                    created_at=datetime.fromisoformat(profile["created_at"])
                                )
                            else:
                                # Create minimal profile
                                user_profile = UserResponse(
                                    id=UUID(user_id),
                                    email=email,
                                    display_name="",
                                    avatar_url=None,
                                    credits_balance=100,
                                    role="viewer",
                                    created_at=datetime.now(timezone.utc)
                                )
                        else:
                            # Profile fetch failed, use minimal
                            user_profile = UserResponse(
                                id=UUID(user_id),
                                email=email,
                                display_name="",
                                avatar_url=None,
                                credits_balance=100,
                                role="viewer",
                                created_at=datetime.now(timezone.utc)
                            )
                    except asyncio.TimeoutError:
                        logger.warning("⏱️ [ASYNC-AUTH] Profile fetch timeout - using minimal")
                        user_profile = UserResponse(
                            id=UUID(user_id),
                            email=email,
                            display_name="",
                            avatar_url=None,
                            credits_balance=100,
                            role="viewer",
                            created_at=datetime.now(timezone.utc)
                        )
                else:
                    # No service client, use minimal
                    user_profile = UserResponse(
                        id=UUID(user_id),
                        email=email,
                        display_name="",
                        avatar_url=None,
                        credits_balance=100,
                        role="viewer",
                        created_at=datetime.now(timezone.utc)
                    )
            
            phase_times['d_ms'] = (time.perf_counter() - t_phase) * 1000
            
            # Phase E: Response preparation
            t_phase = time.perf_counter()
            
            # Store tokens for later use
            self._current_token = access_token
            self._refresh_token = auth_data.get("refresh_token")
            
            phase_times['e_ms'] = (time.perf_counter() - t_phase) * 1000
            
            # Total time
            total_time = (time.perf_counter() - t0) * 1000
            phase_times['total_ms'] = total_time
            
            # Emit timing log
            if timing_enabled:
                timing_log = {
                    "tag": "AUTH_TIMING",
                    "request_id": request_id,
                    "email": credentials.email[:3] + "***",  # Partial email for privacy
                    "phases": phase_times,
                    "fast_login": fast_login,
                    "http1": os.getenv("HTTP1_FALLBACK", "true").lower() in ("1", "true", "yes")
                }
                logger.info(f"📊 [AUTH_TIMING] {json.dumps(timing_log)}")
            
            logger.info(f"✅ [ASYNC-AUTH] Auth complete in {total_time:.1f}ms (req:{request_id})")
            
            return user_profile
            
        except HTTPException:
            raise
        except Exception as e:
            error_time = (time.perf_counter() - t0) * 1000
            logger.error(f"❌ [ASYNC-AUTH] Error after {error_time:.1f}ms: {e}")
            return None
    
    async def create_access_token(self, user: UserResponse) -> Token:
        """Create access token using stored session."""
        if hasattr(self, '_current_token') and self._current_token:
            return Token(
                access_token=self._current_token,
                token_type="bearer",
                expires_in=3600,
                user=user
            )
        
        # Fallback - should not happen in normal flow
        logger.warning("⚠️ [ASYNC-AUTH] No stored token - using placeholder")
        return Token(
            access_token=f"placeholder_{user.id}",
            token_type="bearer",
            expires_in=3600,
            user=user
        )
    
    async def cleanup(self):
        """Cleanup resources."""
        if hasattr(self, 'client'):
            await self.client.aclose()
        if hasattr(self, 'service_client') and self.service_client:
            await self.service_client.aclose()


# Singleton instance management
_service_instance: Optional[AsyncAuthService] = None
_service_lock = asyncio.Lock()


async def get_async_auth_service() -> AsyncAuthService:
    """Get singleton async auth service."""
    global _service_instance
    
    if _service_instance is None:
        async with _service_lock:
            if _service_instance is None:
                _service_instance = AsyncAuthService()
                logger.info("✅ [ASYNC-AUTH] Service singleton created")
    
    return _service_instance


async def cleanup_async_auth_service():
    """Cleanup singleton service."""
    global _service_instance
    
    if _service_instance:
        await _service_instance.cleanup()
        _service_instance = None
        logger.info("✅ [ASYNC-AUTH] Service cleaned up")