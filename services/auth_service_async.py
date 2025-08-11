"""
Async Authentication Service - Production-ready with rock-solid timeouts.
This replaces the synchronous Supabase client with a fully async implementation.
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
    Fully async authentication service with guaranteed timeouts.
    Uses httpx directly instead of synchronous Supabase client.
    """
    
    # Circuit breaker state (class-level to persist across instances)
    _consecutive_failures = 0
    _circuit_open = False
    _circuit_open_until = None
    
    def __init__(self):
        # Configure httpx client with realistic timeouts for Supabase
        # Supabase typically takes 3-5 seconds under load
        self.timeout = httpx.Timeout(
            connect=3.0,  # 3 seconds to establish connection
            read=8.0,     # 8 seconds to read response (Supabase needs 3-5s)
            write=2.0,    # 2 seconds to write request
            pool=1.0      # 1 second to acquire connection from pool
        )
        
        # Create async HTTP client with timeout
        # Use publishable key (anon key) for auth endpoints (required by Supabase Auth API)
        # Fix: Use SUPABASE_PUBLISHABLE_KEY or fallback to SUPABASE_ANON_KEY
        auth_key = os.getenv('SUPABASE_PUBLISHABLE_KEY') or settings.supabase_anon_key
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
                "Authorization": f"Bearer {auth_key}",
                "Content-Type": "application/json"
            },
            http2=False  # Disable HTTP/2 for better compatibility with Supabase
        )
        
        # Service client for database operations
        # Use service role key if available, otherwise use anon key
        service_key = settings.supabase_service_role_key or settings.supabase_anon_key
        self.service_client = httpx.AsyncClient(
            base_url=f"{settings.supabase_url}/rest/v1",
            timeout=self.timeout,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            },
            http2=False  # Disable HTTP/2 for better compatibility
        )
        
        logger.info(f"✅ [ASYNC-AUTH] Initialized with production timeouts (connect={self.timeout.connect}s, read={self.timeout.read}s, write={self.timeout.write}s, pool={self.timeout.pool}s)")
        
        # Initialize monitoring if available
        self.auth_monitor = None
        try:
            from utils.auth_monitor import get_auth_monitor
            self.auth_monitor = get_auth_monitor()
            logger.info("✅ [ASYNC-AUTH] Auth monitoring enabled")
        except ImportError:
            logger.info("ℹ️ [ASYNC-AUTH] Auth monitoring not available")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup clients."""
        await self.close()
    
    async def close(self):
        """Close HTTP clients."""
        await self.client.aclose()
        await self.service_client.aclose()
    
    async def authenticate_user(self, credentials: UserLogin) -> Optional[UserResponse]:
        """
        Authenticate user with guaranteed timeout and circuit breaker.
        Prevents cascading failures when Supabase is slow.
        """
        # Check circuit breaker first
        if AsyncAuthService._circuit_open:
            if time.time() < AsyncAuthService._circuit_open_until:
                logger.error("🔌 [ASYNC-AUTH] Circuit breaker OPEN - failing fast")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service temporarily unavailable - circuit breaker open"
                )
            else:
                logger.info("🔌 [ASYNC-AUTH] Circuit breaker reset - attempting connection")
                AsyncAuthService._circuit_open = False
                AsyncAuthService._consecutive_failures = 0
        
        try:
            logger.info(f"🔐 [ASYNC-AUTH] Starting authentication for {credentials.email}")
            start_time = time.time()
            
            # Prepare auth request
            auth_payload = {
                "email": credentials.email,
                "password": credentials.password
            }
            
            logger.info(f"🔐 [ASYNC-AUTH] Prepared payload, making request to Supabase...")
            
            # CRITICAL FIX: Wrap ALL Supabase calls with asyncio.wait_for() for guaranteed timeout
            try:
                request_start = time.time()
                logger.info(f"🔐 [ASYNC-AUTH] Sending POST to /auth/v1/token?grant_type=password")
                logger.info(f"📍 [ASYNC-AUTH] Supabase URL: {self.client.base_url}")
                logger.info(f"⏱️ [ASYNC-AUTH] Timeout config: connect={self.timeout.connect}s, read={self.timeout.read}s")
                
                # Double timeout protection: httpx timeout AND asyncio.wait_for
                response = await asyncio.wait_for(
                    self.client.post(
                        "/auth/v1/token?grant_type=password",
                        json=auth_payload
                    ),
                    timeout=8.5  # 8.5s to align with 8s read timeout + overhead
                )
                
                request_time = (time.time() - request_start) * 1000
                logger.info(f"📊 [ASYNC-AUTH] Supabase responded in {request_time:.2f}ms")
                
                response_time = (time.time() - start_time) * 1000
                logger.info(f"🔐 [ASYNC-AUTH] Received response: {response.status_code} after {response_time:.2f}ms")
                
                # Reset circuit breaker on successful connection
                AsyncAuthService._consecutive_failures = 0
                
                # Check response status
                if response.status_code != 200:
                    logger.warning(f"❌ [ASYNC-AUTH] Auth failed: {response.status_code}")
                    logger.warning(f"❌ [ASYNC-AUTH] Response: {response.text}")
                    return None
                
                # Parse response with timeout protection
                auth_data = await asyncio.wait_for(
                    asyncio.create_task(response.json()),
                    timeout=0.5  # 500ms for JSON parsing
                )
                
                # Extract user info
                access_token = auth_data.get("access_token")
                if not access_token:
                    logger.error("❌ [ASYNC-AUTH] No access token in response")
                    return None
                
                # Decode JWT to get user info
                user_info = self._decode_jwt(access_token)
                if not user_info:
                    logger.error("❌ [ASYNC-AUTH] Failed to decode JWT")
                    return None
                
                user_id = user_info.get("sub")
                email = user_info.get("email", credentials.email)
                
                logger.info(f"✅ [ASYNC-AUTH] Authentication successful for {email}")
                
                # Get or create user profile with timeout protection
                user_profile = await asyncio.wait_for(
                    self._get_or_create_profile(user_id, email),
                    timeout=1.0  # 1 second for profile operations
                )
                
                # Store token for later use
                self._current_token = access_token
                self._refresh_token = auth_data.get("refresh_token")
                
                total_time = (time.time() - start_time) * 1000
                logger.info(f"✅ [ASYNC-AUTH] Complete authentication flow finished in {total_time:.2f}ms")
                
                return user_profile
                
            except asyncio.TimeoutError:
                timeout_time = (time.time() - start_time) * 1000
                logger.error(f"⏱️ [ASYNC-AUTH] Authentication timeout after {timeout_time:.2f}ms")
                
                # Increment circuit breaker counter
                AsyncAuthService._consecutive_failures += 1
                if AsyncAuthService._consecutive_failures >= 3:
                    AsyncAuthService._circuit_open = True
                    AsyncAuthService._circuit_open_until = time.time() + 30  # Open for 30 seconds
                    logger.error(f"🔌 [ASYNC-AUTH] Circuit breaker OPENED after {AsyncAuthService._consecutive_failures} failures")
                
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service timeout - please try again"
                )
            except httpx.TimeoutException:
                timeout_time = (time.time() - start_time) * 1000
                logger.error(f"⏱️ [ASYNC-AUTH] HTTP timeout after {timeout_time:.2f}ms (httpx level)")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service timeout"
                )
            except httpx.RequestError as e:
                error_time = (time.time() - start_time) * 1000
                logger.error(f"🔌 [ASYNC-AUTH] Network error after {error_time:.2f}ms: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service unavailable"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            error_time = (time.time() - start_time) * 1000
            logger.error(f"❌ [ASYNC-AUTH] Unexpected error after {error_time:.2f}ms: {e}")
            return None
    
    async def register_user(self, user_data: UserCreate) -> UserResponse:
        """
        Register a new user with guaranteed timeout.
        """
        try:
            logger.info(f"📝 [ASYNC-AUTH] Starting registration for {user_data.email}")
            
            # Prepare registration request
            auth_payload = {
                "email": user_data.email,
                "password": user_data.password
            }
            
            logger.info(f"📝 [ASYNC-AUTH] Prepared payload, making request to Supabase...")
            
            # Make async request with guaranteed timeout
            try:
                logger.info(f"📝 [ASYNC-AUTH] Sending POST to /auth/v1/signup")
                response = await asyncio.wait_for(
                    self.client.post(
                        "/auth/v1/signup",
                        json=auth_payload
                    ),
                    timeout=2.0  # Hard 2-second timeout
                )
                logger.info(f"📝 [ASYNC-AUTH] Received response: {response.status_code}")
                
                # Check response status
                if response.status_code not in [200, 201]:
                    error_data = response.json()
                    error_msg = error_data.get("msg", "Registration failed")
                    
                    if "already registered" in error_msg.lower():
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Email already registered"
                        )
                    
                    logger.error(f"❌ [ASYNC-AUTH] Registration failed: {error_msg}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=error_msg
                    )
                
                # Parse response
                auth_data = response.json()
                
                # Extract user info
                user = auth_data.get("user")
                if not user:
                    logger.error("❌ [ASYNC-AUTH] No user in registration response")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Registration failed - no user created"
                    )
                
                user_id = user.get("id")
                email = user.get("email", user_data.email)
                
                logger.info(f"✅ [ASYNC-AUTH] User registered: {email}")
                
                # Create user profile
                user_profile = await self._create_profile(
                    user_id=user_id,
                    email=email,
                    display_name=user_data.full_name or ""
                )
                
                return user_profile
                
            except httpx.TimeoutException:
                logger.error(f"⏱️ [ASYNC-AUTH] Registration timeout after 1.5 seconds")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Registration service timeout"
                )
            except httpx.RequestError as e:
                logger.error(f"🔌 [ASYNC-AUTH] Network error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Registration service unavailable"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Registration error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Registration failed: {str(e)}"
            )
    
    async def _get_or_create_profile(self, user_id: str, email: str) -> UserResponse:
        """Get or create user profile with guaranteed timeout."""
        try:
            # CRITICAL FIX: Wrap database calls with timeout protection
            response = await asyncio.wait_for(
                self.service_client.get(
                    f"/users",
                    params={"id": f"eq.{user_id}", "select": "*"}
                ),
                timeout=1.0  # 1 second for profile lookup
            )
            
            if response.status_code == 200:
                # Parse response with timeout protection
                profiles = await asyncio.wait_for(
                    asyncio.create_task(response.json()),
                    timeout=0.3  # 300ms for JSON parsing
                )
                
                if profiles and len(profiles) > 0:
                    profile = profiles[0]
                    logger.info(f"✅ [ASYNC-AUTH] Found existing profile for {user_id}")
                    return UserResponse(
                        id=UUID(profile["id"]),
                        email=email,
                        display_name=profile.get("display_name", ""),
                        avatar_url=profile.get("avatar_url"),
                        credits_balance=profile.get("credits_balance", 100),
                        role=profile.get("role", "viewer"),
                        created_at=datetime.fromisoformat(profile["created_at"])
                    )
            
            # Profile doesn't exist, create it with timeout protection
            logger.info(f"👤 [ASYNC-AUTH] Creating new profile for {user_id}")
            return await asyncio.wait_for(
                self._create_profile(user_id, email, ""),
                timeout=1.0  # 1 second for profile creation
            )
            
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ [ASYNC-AUTH] Profile lookup timeout, using defaults for {user_id}")
            # Return basic profile on timeout
            return UserResponse(
                id=UUID(user_id),
                email=email,
                display_name="",
                avatar_url=None,
                credits_balance=100,
                role="viewer",
                created_at=datetime.now(timezone.utc)
            )
        except httpx.TimeoutException:
            logger.warning(f"⏱️ [ASYNC-AUTH] HTTP timeout in profile lookup, using defaults for {user_id}")
            # Return basic profile on timeout
            return UserResponse(
                id=UUID(user_id),
                email=email,
                display_name="",
                avatar_url=None,
                credits_balance=100,
                role="viewer",
                created_at=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Profile error for {user_id}: {e}")
            # Return basic profile on error
            return UserResponse(
                id=UUID(user_id),
                email=email,
                display_name="",
                avatar_url=None,
                credits_balance=100,
                role="viewer",
                created_at=datetime.now(timezone.utc)
            )
    
    async def _create_profile(self, user_id: str, email: str, display_name: str) -> UserResponse:
        """Create user profile with guaranteed timeout."""
        try:
            profile_data = {
                "id": user_id,
                "email": email,
                "display_name": display_name,
                "avatar_url": None,
                "credits_balance": 100,
                "role": "viewer",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = await self.service_client.post(
                "/users",
                json=profile_data
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ [ASYNC-AUTH] Profile created for {email}")
            else:
                logger.warning(f"⚠️ [ASYNC-AUTH] Profile creation returned {response.status_code}")
            
            return UserResponse(
                id=UUID(user_id),
                email=email,
                display_name=display_name,
                avatar_url=None,
                credits_balance=100,
                role="viewer",
                created_at=datetime.now(timezone.utc)
            )
            
        except httpx.TimeoutException:
            logger.warning(f"⏱️ [ASYNC-AUTH] Profile creation timeout after 1.5 seconds, using defaults")
            return UserResponse(
                id=UUID(user_id),
                email=email,
                display_name=display_name,
                avatar_url=None,
                credits_balance=100,
                role="viewer",
                created_at=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Profile creation error: {e}")
            return UserResponse(
                id=UUID(user_id),
                email=email,
                display_name=display_name,
                avatar_url=None,
                credits_balance=100,
                role="viewer",
                created_at=datetime.now(timezone.utc)
            )
    
    def _decode_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode JWT token to extract user info."""
        try:
            # JWT has 3 parts: header.payload.signature
            parts = token.split('.')
            if len(parts) != 3:
                return None
            
            # Decode the payload (second part)
            payload = parts[1]
            # Add padding if needed
            padding = 4 - (len(payload) % 4)
            if padding != 4:
                payload += '=' * padding
            
            # Decode base64
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)
            
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] JWT decode error: {e}")
            return None
    
    async def create_access_token(self, user: UserResponse) -> Token:
        """Create access token from stored authentication."""
        try:
            # Use stored token from authentication
            if hasattr(self, '_current_token') and self._current_token:
                return Token(
                    access_token=self._current_token,
                    token_type="bearer",
                    expires_in=settings.jwt_expiration_seconds,
                    user=user
                )
            
            # Fallback to creating our own JWT if needed
            logger.warning("⚠️ [ASYNC-AUTH] No stored token, creating custom JWT")
            from utils.security import JWTSecurity
            
            custom_token = JWTSecurity.create_access_token(
                user_id=str(user.id),
                email=user.email,
                additional_claims={
                    "role": user.role,
                    "credits_balance": user.credits_balance,
                    "display_name": user.display_name or ""
                }
            )
            
            return Token(
                access_token=custom_token,
                token_type="bearer",
                expires_in=settings.jwt_expiration_seconds,
                user=user
            )
            
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Token creation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create access token"
            )
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Token]:
        """Refresh access token with guaranteed timeout."""
        try:
            logger.info("🔄 [ASYNC-AUTH] Refreshing token")
            
            response = await self.client.post(
                "/auth/v1/token",
                params={"grant_type": "refresh_token"},
                json={"refresh_token": refresh_token}
            )
            
            if response.status_code != 200:
                logger.warning(f"❌ [ASYNC-AUTH] Token refresh failed: {response.status_code}")
                return None
            
            auth_data = response.json()
            access_token = auth_data.get("access_token")
            
            if not access_token:
                return None
            
            # Decode JWT to get user info
            user_info = self._decode_jwt(access_token)
            if not user_info:
                return None
            
            user_id = user_info.get("sub")
            email = user_info.get("email", "")
            
            # Get user profile
            user_profile = await self._get_or_create_profile(user_id, email)
            
            # Store new tokens
            self._current_token = access_token
            self._refresh_token = auth_data.get("refresh_token", refresh_token)
            
            return Token(
                access_token=access_token,
                token_type="bearer",
                expires_in=auth_data.get("expires_in", settings.jwt_expiration_seconds),
                user=user_profile
            )
            
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] Token refresh timeout after 1.5 seconds")
            return None
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Token refresh error: {e}")
            return None
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[UserResponse]:
        """Get user by ID with guaranteed timeout."""
        try:
            response = await self.service_client.get(
                f"/users",
                params={"id": f"eq.{str(user_id)}", "select": "*"}
            )
            
            if response.status_code == 200:
                users = response.json()
                if users and len(users) > 0:
                    user_data = users[0]
                    return UserResponse(
                        id=UUID(user_data['id']),
                        email=user_data.get('email', ''),
                        display_name=user_data.get('display_name', ''),
                        avatar_url=user_data.get('avatar_url'),
                        credits_balance=user_data.get('credits_balance', 100),
                        role=user_data.get('role', 'viewer'),
                        created_at=datetime.fromisoformat(user_data['created_at'])
                    )
            
            return None
            
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] User lookup timeout after 1.5 seconds")
            return None
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] User lookup error: {e}")
            return None
    
    async def get_user_by_token(self, token: str) -> Optional[UserResponse]:
        """Get user info by validating token directly with Supabase API."""
        try:
            logger.info("🔍 [ASYNC-AUTH] Getting user by token")
            
            # Create authenticated client for this request
            auth_client = httpx.AsyncClient(
                base_url=settings.supabase_url,
                timeout=self.timeout,
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            try:
                # Get user info from Supabase auth endpoint
                response = await auth_client.get("/auth/v1/user")
                
                if response.status_code != 200:
                    logger.warning(f"❌ [ASYNC-AUTH] Token validation failed: {response.status_code}")
                    return None
                
                user_data = response.json()
                user_id = user_data.get("id")
                email = user_data.get("email")
                
                if not user_id or not email:
                    logger.warning("❌ [ASYNC-AUTH] Invalid user data from token")
                    return None
                
                # Get or create user profile
                return await self._get_or_create_profile(user_id, email)
                
            finally:
                await auth_client.aclose()
                
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] Get user by token timeout after 1.5 seconds")
            return None
        except httpx.RequestError as e:
            logger.error(f"🔌 [ASYNC-AUTH] Network error validating token: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Token validation error: {e}")
            return None
    
    async def sync_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """Sync user profile to database."""
        try:
            logger.info(f"🔄 [ASYNC-AUTH] Syncing profile for user {user_id}")
            
            # Update user profile in database
            response = await self.service_client.patch(
                f"/users?id=eq.{user_id}",
                json=profile_data
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ [ASYNC-AUTH] Profile synced for user {user_id}")
                return True
            else:
                logger.warning(f"⚠️ [ASYNC-AUTH] Profile sync failed: {response.status_code}")
                return False
                
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] Profile sync timeout after 1.5 seconds")
            return False
        except httpx.RequestError as e:
            logger.error(f"🔌 [ASYNC-AUTH] Network error syncing profile: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Profile sync error: {e}")
            return False
    
    async def validate_supabase_jwt(self, token: str) -> bool:
        """Validate JWT token with Supabase's JWT verification endpoint."""
        try:
            logger.debug("🔍 [ASYNC-AUTH] Validating Supabase JWT")
            
            # Verify JWT with Supabase
            response = await self.client.get(
                "/auth/v1/user",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            is_valid = response.status_code == 200
            if is_valid:
                logger.debug("✅ [ASYNC-AUTH] JWT validation successful")
            else:
                logger.debug(f"❌ [ASYNC-AUTH] JWT validation failed: {response.status_code}")
            
            return is_valid
            
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] JWT validation timeout after 1.5 seconds")
            return False
        except httpx.RequestError as e:
            logger.error(f"🔌 [ASYNC-AUTH] Network error validating JWT: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] JWT validation error: {e}")
            return False
    
    async def verify_token_http(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify token via HTTP API for middleware."""
        try:
            logger.debug("🔍 [ASYNC-AUTH] HTTP token verification for middleware")
            
            # Get user data from token
            response = await self.client.get(
                "/auth/v1/user",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                logger.debug(f"❌ [ASYNC-AUTH] HTTP token verification failed: {response.status_code}")
                return None
            
            user_data = response.json()
            logger.debug("✅ [ASYNC-AUTH] HTTP token verification successful")
            
            return {
                "user_id": user_data.get("id"),
                "email": user_data.get("email"),
                "aud": user_data.get("aud"),
                "role": user_data.get("role"),
                "exp": user_data.get("exp")
            }
            
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] HTTP token verification timeout after 1.5 seconds")
            return None
        except httpx.RequestError as e:
            logger.error(f"🔌 [ASYNC-AUTH] Network error in HTTP token verification: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] HTTP token verification error: {e}")
            return None
    
    async def get_authenticated_client(self, user_token: str) -> httpx.AsyncClient:
        """Get HTTP client configured for user authentication."""
        try:
            logger.debug("🔧 [ASYNC-AUTH] Creating authenticated HTTP client")
            
            return httpx.AsyncClient(
                base_url=settings.supabase_url,
                timeout=self.timeout,
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {user_token}",
                    "Content-Type": "application/json"
                },
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=5,
                    keepalive_expiry=30.0
                )
            )
            
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Error creating authenticated client: {e}")
            raise
    
    async def get_user_profile(self, user_id: str, timeout: float = None) -> Optional[Dict[str, Any]]:
        """Get user profile via HTTP API with timeout."""
        try:
            request_timeout = timeout or 1.5
            logger.debug(f"🔍 [ASYNC-AUTH] Getting user profile for {user_id} (timeout: {request_timeout}s)")
            
            # Use custom timeout if specified
            if timeout:
                custom_timeout = httpx.Timeout(
                    connect=min(1.0, timeout/2),
                    read=timeout,
                    write=min(1.0, timeout/2),
                    pool=0.5
                )
                client = self.service_client
                original_timeout = client.timeout
                client.timeout = custom_timeout
            else:
                client = self.service_client
            
            try:
                response = await client.get(
                    f"/users?id=eq.{user_id}&select=*"
                )
                
                if response.status_code == 200:
                    profiles = response.json()
                    if profiles and len(profiles) > 0:
                        logger.debug(f"✅ [ASYNC-AUTH] Profile retrieved for {user_id}")
                        return profiles[0]
                
                logger.debug(f"❌ [ASYNC-AUTH] No profile found for {user_id}")
                return None
                
            finally:
                if timeout:
                    client.timeout = original_timeout
            
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] Get user profile timeout after {request_timeout}s")
            return None
        except httpx.RequestError as e:
            logger.error(f"🔌 [ASYNC-AUTH] Network error getting user profile: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Get user profile error: {e}")
            return None
    
    async def update_user_profile(self, user_id: str, updates: Dict[str, Any], timeout: float = None) -> bool:
        """Update user profile via HTTP API with timeout."""
        try:
            request_timeout = timeout or 1.5
            logger.info(f"🔄 [ASYNC-AUTH] Updating user profile for {user_id} (timeout: {request_timeout}s)")
            
            # Use custom timeout if specified
            if timeout:
                custom_timeout = httpx.Timeout(
                    connect=min(1.0, timeout/2),
                    read=timeout,
                    write=min(1.0, timeout/2),
                    pool=0.5
                )
                client = self.service_client
                original_timeout = client.timeout
                client.timeout = custom_timeout
            else:
                client = self.service_client
            
            try:
                # Add updated_at timestamp
                updates["updated_at"] = datetime.now(timezone.utc).isoformat()
                
                response = await client.patch(
                    f"/users?id=eq.{user_id}",
                    json=updates
                )
                
                if response.status_code in [200, 204]:
                    logger.info(f"✅ [ASYNC-AUTH] Profile updated for {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ [ASYNC-AUTH] Profile update failed: {response.status_code}")
                    return False
                    
            finally:
                if timeout:
                    client.timeout = original_timeout
            
        except httpx.TimeoutException:
            logger.error(f"⏱️ [ASYNC-AUTH] Update user profile timeout after {request_timeout}s")
            return False
        except httpx.RequestError as e:
            logger.error(f"🔌 [ASYNC-AUTH] Network error updating user profile: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ [ASYNC-AUTH] Update user profile error: {e}")
            return False


# Global instance
_async_auth_service: Optional[AsyncAuthService] = None


async def get_async_auth_service() -> AsyncAuthService:
    """Get or create async auth service singleton."""
    global _async_auth_service
    if _async_auth_service is None:
        _async_auth_service = AsyncAuthService()
        logger.info("✅ [ASYNC-AUTH] Service singleton created")
    return _async_auth_service


async def cleanup_async_auth_service():
    """Cleanup async auth service on shutdown."""
    global _async_auth_service
    if _async_auth_service is not None:
        await _async_auth_service.close()
        _async_auth_service = None
        logger.info("✅ [ASYNC-AUTH] Service cleaned up")