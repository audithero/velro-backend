"""
Optimized Async Authentication Service with circuit breaker and cancelable timeouts.
"""
import os
import asyncio
import httpx
import json
import base64
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException, status

from models.user import UserCreate, UserResponse, UserLogin, Token
from config import settings
import logging

logger = logging.getLogger(__name__)


class AsyncAuthService:
    """
    Auth hot path with:
      - Cancelable timeouts (asyncio.wait_for)
      - Circuit breaker (3 fails -> 30s open)
      - HTTP/1.1 fallback (for proxy compatibility)
      - Fast login (skip profile lookups)
      - Detailed timing breadcrumbs
    """
    
    def __init__(self):
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL") or settings.supabase_url
        # CRITICAL FIX: Use SUPABASE_ANON_KEY instead of SUPABASE_PUBLISHABLE_KEY
        self.anon_key = os.getenv("SUPABASE_ANON_KEY") or settings.supabase_anon_key
        
        # Feature flags
        self.fast_login = os.getenv("AUTH_FAST_LOGIN", "true").lower() in ("true", "1", "yes")
        self.http1_fallback = os.getenv("AUTH_HTTP1_FALLBACK", "true").lower() in ("true", "1", "yes")
        
        # Aggressive timeouts for fast auth response
        connect_timeout = float(os.getenv("AUTH_CONNECT_TIMEOUT", "1.0"))  # 1s connect
        read_timeout = float(os.getenv("AUTH_READ_TIMEOUT", "2.0"))  # 2s read
        write_timeout = float(os.getenv("AUTH_WRITE_TIMEOUT", "1.0"))  # 1s write
        pool_timeout = float(os.getenv("AUTH_POOL_TIMEOUT", "0.5"))  # 0.5s pool
        
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout
        )
        
        # Create HTTP client with connection pooling and keep-alive
        self.client = httpx.AsyncClient(
            base_url=self.supabase_url,
            timeout=self.timeout,
            http2=False,  # Force HTTP/1.1 for better proxy compatibility
            limits=httpx.Limits(
                max_connections=10,  # Reduce to avoid connection overhead
                max_keepalive_connections=5,  # Keep fewer connections alive
                keepalive_expiry=60.0  # Keep connections alive longer
            ),
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
                "Connection": "keep-alive"  # Explicit keep-alive
            },
            transport=httpx.AsyncHTTPTransport(
                retries=0,  # No automatic retries
                http2=False  # Force HTTP/1.1 at transport level too
            )
        )
        
        # Circuit breaker configuration
        self._fails = 0
        self._circuit_open_until = 0.0
        self._circuit_window = float(os.getenv("AUTH_CB_OPEN_SECONDS", "30"))
        self._cb_threshold = int(os.getenv("AUTH_CB_THRESHOLD", "3"))
        
        # Outer guard timeouts (hard ceiling)
        self.outer_timeout = float(os.getenv("AUTH_OUTER_TIMEOUT_SECONDS", "3"))  # 3s hard limit
        self.inner_timeout = float(os.getenv("AUTH_INNER_TIMEOUT_SECONDS", "2.5"))  # 2.5s inner
        
        logger.info(
            f"✅ [ASYNC-AUTH] Initialized: fast_login={self.fast_login}, "
            f"http1={self.http1_fallback}, timeouts=(connect={connect_timeout}s, "
            f"read={read_timeout}s), circuit_breaker=({self._cb_threshold} fails -> {self._circuit_window}s open)"
        )
        
        # Start background warmup
        asyncio.create_task(self._warmup_connection())
    
    async def _warmup_connection(self):
        """Warm up the connection pool on startup."""
        try:
            # Quick auth settings check to prime DNS/TLS
            response = await self.client.get("/auth/v1/settings")
            logger.info(f"🔥 [ASYNC-AUTH] Connection warmup: status={response.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ [ASYNC-AUTH] Warmup failed: {e}")
    
    def _circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        return time.time() < self._circuit_open_until
    
    def _trip_circuit(self):
        """Open the circuit breaker."""
        self._circuit_open_until = time.time() + self._circuit_window
        logger.error(f"🔌 [ASYNC-AUTH] Circuit breaker OPENED for {self._circuit_window}s")
    
    def _reset_circuit(self):
        """Reset circuit breaker on success."""
        if self._fails > 0:
            logger.info("🔌 [ASYNC-AUTH] Circuit breaker reset")
        self._fails = 0
        self._circuit_open_until = 0.0
    
    async def _supabase_password_grant(self, email: str, password: str) -> Dict[str, Any]:
        """
        Single call to Supabase password grant endpoint.
        This is the critical hot path - must be fast.
        """
        start_time = time.perf_counter()
        timing_breakdown = {}
        
        # Phase 1: Request preparation
        t1 = time.perf_counter()
        url = "/auth/v1/token?grant_type=password"
        payload = {"email": email, "password": password}
        timing_breakdown['request_prep_ms'] = (time.perf_counter() - t1) * 1000
        
        # Phase 2: HTTP POST request
        t2 = time.perf_counter()
        try:
            response = await self.client.post(url, json=payload)
            timing_breakdown['http_post_ms'] = (time.perf_counter() - t2) * 1000
        except Exception as e:
            timing_breakdown['http_post_ms'] = (time.perf_counter() - t2) * 1000
            timing_breakdown['error'] = str(e)
            logger.error(f"🚨 [SUPABASE-GRANT] HTTP POST failed after {timing_breakdown['http_post_ms']:.2f}ms: {e}")
            raise
        
        # Phase 3: Response processing
        t3 = time.perf_counter()
        
        if response.status_code == 400:
            # Check for invalid credentials
            try:
                error_data = response.json()
                if "invalid_grant" in str(error_data):
                    timing_breakdown['response_processing_ms'] = (time.perf_counter() - t3) * 1000
                    timing_breakdown['total_ms'] = (time.perf_counter() - start_time) * 1000
                    logger.info(f"🔐 [SUPABASE-GRANT] Invalid credentials detected: {timing_breakdown}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid email or password"
                    )
            except (ValueError, KeyError) as e:
                logger.warning(f"⚠️ [SUPABASE-GRANT] Failed to parse error response: {e}")
        
        try:
            response.raise_for_status()
            response_data = response.json()
            timing_breakdown['response_processing_ms'] = (time.perf_counter() - t3) * 1000
        except Exception as e:
            timing_breakdown['response_processing_ms'] = (time.perf_counter() - t3) * 1000
            timing_breakdown['error'] = str(e)
            logger.error(f"🚨 [SUPABASE-GRANT] Response processing failed: {e}")
            raise
        
        timing_breakdown['total_ms'] = (time.perf_counter() - start_time) * 1000
        
        logger.info(f"✅ [SUPABASE-GRANT] Password grant completed: {timing_breakdown}")
        return response_data
    
    async def authenticate_user(self, credentials: UserLogin) -> Optional[UserResponse]:
        """
        Authenticate user with cancelable timeouts and circuit breaker.
        Returns UserResponse or None.
        """
        start_time = time.perf_counter()
        request_id = f"{int(time.time() * 1000) % 100000:05d}"  # Short ID for logs
        
        # DETAILED TIMING BREAKDOWN
        detailed_timing = {
            'request_id': request_id,
            'start_timestamp': time.time(),
            'phases': {}
        }
        
        # Phase 0: Circuit breaker check
        t_circuit = time.perf_counter()
        if self._circuit_open():
            detailed_timing['phases']['circuit_check_ms'] = (time.perf_counter() - t_circuit) * 1000
            detailed_timing['total_ms'] = (time.perf_counter() - start_time) * 1000
            logger.warning(f"🔌 [AUTH-{request_id}] Circuit open - rejecting immediately: {detailed_timing}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable"
            )
        detailed_timing['phases']['circuit_check_ms'] = (time.perf_counter() - t_circuit) * 1000
        
        email = credentials.email
        phase = "init"
        phase_times = {}
        
        try:
            # Inner auth task with proper timeout
            async def do_auth():
                nonlocal phase, phase_times, detailed_timing
                
                # Phase 1: Supabase password grant
                phase = "password_grant"
                t0 = time.perf_counter()
                
                logger.info(f"🔄 [AUTH-{request_id}] Starting password grant phase at {(t0 - start_time) * 1000:.2f}ms")
                
                # Use wait_for for cancelable timeout
                try:
                    auth_data = await asyncio.wait_for(
                        self._supabase_password_grant(email, credentials.password),
                        timeout=self.inner_timeout
                    )
                    phase_times['password_grant_ms'] = (time.perf_counter() - t0) * 1000
                    detailed_timing['phases']['password_grant_ms'] = phase_times['password_grant_ms']
                    
                    logger.info(f"✅ [AUTH-{request_id}] Password grant completed in {phase_times['password_grant_ms']:.2f}ms")
                except asyncio.TimeoutError as e:
                    phase_times['password_grant_timeout_ms'] = (time.perf_counter() - t0) * 1000
                    detailed_timing['phases']['password_grant_timeout_ms'] = phase_times['password_grant_timeout_ms']
                    logger.error(f"⏱️ [AUTH-{request_id}] Password grant TIMEOUT after {phase_times['password_grant_timeout_ms']:.2f}ms (limit: {self.inner_timeout}s)")
                    raise
                except Exception as e:
                    phase_times['password_grant_error_ms'] = (time.perf_counter() - t0) * 1000
                    detailed_timing['phases']['password_grant_error_ms'] = phase_times['password_grant_error_ms']
                    logger.error(f"🚨 [AUTH-{request_id}] Password grant ERROR after {phase_times['password_grant_error_ms']:.2f}ms: {e}")
                    raise
                
                # Phase 1.5: Token extraction
                t_extract = time.perf_counter()
                
                access_token = auth_data.get("access_token")
                refresh_token = auth_data.get("refresh_token")
                
                if not access_token:
                    detailed_timing['phases']['token_extraction_error_ms'] = (time.perf_counter() - t_extract) * 1000
                    logger.error(f"🚨 [AUTH-{request_id}] No access token in response: {auth_data}")
                    raise ValueError("No access token in response")
                
                # Store tokens for later use
                self._current_token = access_token
                self._refresh_token = refresh_token
                
                detailed_timing['phases']['token_extraction_ms'] = (time.perf_counter() - t_extract) * 1000
                logger.info(f"🔑 [AUTH-{request_id}] Token extraction completed in {detailed_timing['phases']['token_extraction_ms']:.2f}ms")
                
                # Phase 2: User profile (skip in fast mode)
                if self.fast_login:
                    phase = "fast_response"
                    t_fast = time.perf_counter()
                    
                    logger.info(f"⚡ [AUTH-{request_id}] Fast login enabled - skipping profile fetch")
                    
                    # Extract user ID from token or response
                    t_user_extract = time.perf_counter()
                    user_info = auth_data.get("user", {})
                    if user_info and user_info.get("id"):
                        user_id = user_info.get("id")
                        user_email = user_info.get("email", email)
                        detailed_timing['phases']['user_info_from_response_ms'] = (time.perf_counter() - t_user_extract) * 1000
                    else:
                        # Decode JWT to get user ID
                        try:
                            t_jwt = time.perf_counter()
                            parts = access_token.split('.')
                            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                            user_id = payload.get("sub")
                            user_email = payload.get("email", email)
                            detailed_timing['phases']['jwt_decode_ms'] = (time.perf_counter() - t_jwt) * 1000
                            logger.info(f"🔓 [AUTH-{request_id}] JWT decoded in {detailed_timing['phases']['jwt_decode_ms']:.2f}ms")
                        except Exception as e:
                            detailed_timing['phases']['jwt_decode_error_ms'] = (time.perf_counter() - t_jwt) * 1000
                            logger.warning(f"⚠️ [AUTH-{request_id}] JWT decode failed: {e}")
                            user_id = "unknown"
                            user_email = email
                    
                    detailed_timing['phases']['user_extraction_ms'] = (time.perf_counter() - t_user_extract) * 1000
                    
                    # Create user response object
                    t_create_response = time.perf_counter()
                    user_response = UserResponse(
                        id=UUID(user_id) if user_id != "unknown" else UUID("00000000-0000-0000-0000-000000000000"),
                        email=user_email,
                        display_name="",
                        avatar_url=None,
                        credits_balance=100,
                        role="viewer",
                        created_at=datetime.now(timezone.utc)
                    )
                    detailed_timing['phases']['create_response_ms'] = (time.perf_counter() - t_create_response) * 1000
                    detailed_timing['phases']['fast_response_total_ms'] = (time.perf_counter() - t_fast) * 1000
                    
                    logger.info(f"⚡ [AUTH-{request_id}] Fast response created in {detailed_timing['phases']['fast_response_total_ms']:.2f}ms")
                    return user_response
                
                # Non-fast path: fetch user profile (optional, lightweight)
                phase = "fetch_profile"
                t1 = time.perf_counter()
                try:
                    user_resp = await asyncio.wait_for(
                        self.client.get(
                            "/auth/v1/user",
                            headers={"Authorization": f"Bearer {access_token}"}
                        ),
                        timeout=2.0  # Quick timeout for profile
                    )
                    
                    if user_resp.is_success:
                        user_data = user_resp.json()
                        phase_times['profile_fetch_ms'] = (time.perf_counter() - t1) * 1000
                    else:
                        user_data = None
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"⚠️ [AUTH-{request_id}] Profile fetch failed: {e}")
                    user_data = None
                
                # Build user response
                if user_data:
                    return UserResponse(
                        id=UUID(user_data.get("id", "00000000-0000-0000-0000-000000000000")),
                        email=user_data.get("email", email),
                        display_name=user_data.get("user_metadata", {}).get("display_name", ""),
                        avatar_url=user_data.get("user_metadata", {}).get("avatar_url"),
                        credits_balance=100,
                        role="viewer",
                        created_at=datetime.now(timezone.utc)
                    )
                else:
                    # Fallback to minimal response
                    return UserResponse(
                        id=UUID("00000000-0000-0000-0000-000000000000"),
                        email=email,
                        display_name="",
                        avatar_url=None,
                        credits_balance=100,
                        role="viewer",
                        created_at=datetime.now(timezone.utc)
                    )
            
            # Execute with outer timeout
            phase = "outer_wait"
            t_outer = time.perf_counter()
            
            try:
                result = await asyncio.wait_for(do_auth(), timeout=self.outer_timeout)
                detailed_timing['phases']['outer_wait_ms'] = (time.perf_counter() - t_outer) * 1000
            except asyncio.TimeoutError:
                detailed_timing['phases']['outer_timeout_ms'] = (time.perf_counter() - t_outer) * 1000
                detailed_timing['total_ms'] = (time.perf_counter() - start_time) * 1000
                logger.error(f"⏱️ [AUTH-{request_id}] OUTER TIMEOUT after {detailed_timing['total_ms']:.2f}ms (limit: {self.outer_timeout}s): {detailed_timing}")
                raise
            
            # Success - reset circuit breaker
            t_circuit_reset = time.perf_counter()
            self._reset_circuit()
            detailed_timing['phases']['circuit_reset_ms'] = (time.perf_counter() - t_circuit_reset) * 1000
            
            # Log timing
            total_ms = (time.perf_counter() - start_time) * 1000
            phase_times['total_ms'] = total_ms
            detailed_timing['total_ms'] = total_ms
            detailed_timing['success'] = True
            
            logger.info(
                f"✅ [AUTH-{request_id}] SUCCESS in {total_ms:.1f}ms "
                f"(fast={self.fast_login}) DETAILED_TIMING: {json.dumps(detailed_timing, indent=2)}"
            )
            
            return result
            
        except asyncio.TimeoutError:
            # Timeout - increment failures
            self._fails += 1
            if self._fails >= self._cb_threshold:
                self._trip_circuit()
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            detailed_timing['total_ms'] = elapsed_ms
            detailed_timing['timeout_phase'] = phase
            detailed_timing['error'] = 'timeout'
            
            logger.error(
                f"⏱️ [AUTH-{request_id}] TIMEOUT at phase={phase} after {elapsed_ms:.1f}ms "
                f"(inner={self.inner_timeout}s, outer={self.outer_timeout}s) DETAILED_TIMING: {json.dumps(detailed_timing, indent=2)}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service timeout"
            )
            
        except HTTPException:
            # Known HTTP errors - pass through
            self._fails += 1
            if self._fails >= self._cb_threshold:
                self._trip_circuit()
            raise
            
        except Exception as e:
            # Unexpected errors
            self._fails += 1
            if self._fails >= self._cb_threshold:
                self._trip_circuit()
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            detailed_timing['total_ms'] = elapsed_ms
            detailed_timing['error_phase'] = phase
            detailed_timing['error'] = str(e)
            detailed_timing['error_type'] = type(e).__name__
            
            logger.exception(
                f"💥 [AUTH-{request_id}] ERROR at phase={phase} after {elapsed_ms:.1f}ms: {e} "
                f"DETAILED_TIMING: {json.dumps(detailed_timing, indent=2)}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication error"
            )
    
    async def verify_token(self, token: str) -> bool:
        """Verify JWT token validity - placeholder implementation."""
        try:
            # Quick JWT structure validation
            parts = token.split('.')
            if len(parts) != 3:
                return False
            
            # In a real implementation, this would validate signature and expiry
            # For now, just check it's a properly formatted JWT
            import json
            import base64
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
            return bool(payload.get('sub'))  # Has subject claim
        except Exception:
            return False
    
    async def create_access_token(self, user: UserResponse) -> Token:
        """Create access token response using stored session."""
        if hasattr(self, '_current_token') and self._current_token:
            return Token(
                access_token=self._current_token,
                token_type="bearer",
                expires_in=3600,
                user=user
            )
        
        # Fallback
        logger.warning("⚠️ [ASYNC-AUTH] No stored token - using placeholder")
        return Token(
            access_token=f"placeholder_{user.id}",
            token_type="bearer",
            expires_in=3600,
            user=user
        )
    
    async def test_direct_supabase_auth(self, email: str = "test@example.com", password: str = "test123456"):
        """
        Test direct Supabase auth call for performance isolation.
        This bypasses all our logic to see raw Supabase performance.
        """
        logger.info(f"🧪 [TEST-DIRECT-AUTH] Starting direct auth test")
        
        start = time.perf_counter()
        timing = {}
        
        try:
            # Phase 1: DNS/Connection setup
            t1 = time.perf_counter()
            
            # Use a fresh client to simulate worst case
            test_client = httpx.AsyncClient(
                base_url=self.supabase_url,
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=2.0),
                headers={"apikey": self.anon_key, "Content-Type": "application/json"}
            )
            timing['client_setup_ms'] = (time.perf_counter() - t1) * 1000
            
            # Phase 2: Direct auth call
            t2 = time.perf_counter()
            response = await test_client.post(
                "/auth/v1/token?grant_type=password",
                json={"email": email, "password": password}
            )
            timing['auth_call_ms'] = (time.perf_counter() - t2) * 1000
            
            # Phase 3: Response processing
            t3 = time.perf_counter()
            status = response.status_code
            if response.is_success:
                data = response.json()
                has_token = bool(data.get('access_token'))
            else:
                has_token = False
                data = None
            timing['response_proc_ms'] = (time.perf_counter() - t3) * 1000
            
            await test_client.aclose()
            
        except Exception as e:
            timing['error'] = str(e)
            status = 0
            has_token = False
            data = None
        
        timing['total_ms'] = (time.perf_counter() - start) * 1000
        
        result = {
            'status_code': status,
            'has_access_token': has_token,
            'timing': timing,
            'baseline_performance': timing['total_ms']
        }
        
        logger.info(f"🧪 [TEST-DIRECT-AUTH] Result: {json.dumps(result, indent=2)}")
        return result
    
    async def get_authenticated_client(self, user_token: str):
        """
        Create a Supabase client authenticated with the user's JWT.
        This allows RLS (Row Level Security) to apply to all operations.
        
        Args:
            user_token: The JWT token from the user's session
            
        Returns:
            Supabase client configured with user's JWT for RLS enforcement
            
        Raises:
            ValueError: If token is invalid or missing
        """
        if not user_token or not isinstance(user_token, str):
            raise ValueError("Missing or invalid user token")
        
        from supabase import create_client
        import jwt
        
        try:
            # Create a new Supabase client with the user's JWT
            # This ensures RLS policies are enforced for this user
            
            # Create client with anon key first
            client = create_client(
                self.supabase_url,
                self.anon_key
            )
            
            # Override the auth header for RLS
            # The Supabase Python client uses httpx internally
            client.postgrest.auth(user_token)
            
            logger.info(f"✅ [ASYNC-AUTH] Created authenticated Supabase client for user")
            return client
            
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Failed to create authenticated client: {e}")
            raise RuntimeError(f"Failed to create authenticated Supabase client: {e}")
    
    async def verify_token_http(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify token for HTTP requests (compatibility method).
        This is an alias for verify_token to maintain backward compatibility.
        """
        return await self.verify_token(token)
    
    async def cleanup(self):
        """Cleanup resources."""
        if hasattr(self, 'client'):
            await self.client.aclose()
            logger.info("✅ [ASYNC-AUTH] Client closed")


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
                logger.info("✅ [ASYNC-AUTH] Singleton created")
    
    return _service_instance


async def cleanup_async_auth_service():
    """Cleanup singleton service."""
    global _service_instance
    
    if _service_instance:
        await _service_instance.cleanup()
        _service_instance = None
        logger.info("✅ [ASYNC-AUTH] Singleton cleaned up")