"""
Authentication middleware for JWT token verification with Supabase.
Following CLAUDE.md: JWT verification, proper error handling.
"""
import logging
import hashlib
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status, Request, Response, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
import httpx
import os

from config import settings
from database import db
from models.user import UserResponse
from utils.security import JWTSecurity, SecurityError
from utils.cache_manager import get_cache_manager, CacheLevel
from services.auth_service_async import get_async_auth_service, AsyncAuthService

logger = logging.getLogger(__name__)

# Initialize cache manager
cache_manager = get_cache_manager()

# Security scheme for dependency injection  
security = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware for Supabase integration."""
    
    def __init__(self, app):
        super().__init__(app)
        # Import testing config for public endpoints with production-safe defaults
        try:
            from testing_config import get_public_endpoints, is_testing_mode, is_e2e_testing_enabled
            # Always use the production-safe public endpoints function
            self.excluded_paths = get_public_endpoints()
            
            if is_testing_mode():
                logger.warning("⚠️ [AUTH-MIDDLEWARE] Testing mode active: Extended public endpoints")
            if is_e2e_testing_enabled():
                logger.warning("⚠️ [AUTH-MIDDLEWARE] E2E testing enabled: Additional test endpoints available")
                
        except ImportError as e:
            logger.warning(f"⚠️ [AUTH-MIDDLEWARE] Testing config import failed: {e}")
            # Fail-safe: use minimal default excluded paths
            self.excluded_paths = self._get_default_excluded_paths()
    
    def _get_default_excluded_paths(self):
        return {
            "/", 
            "/docs", 
            "/redoc", 
            "/openapi.json",
            "/health",
            "/api/v1/health",
            "/api/v1/health/status",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
            "/api/v1/auth/health",
            "/api/v1/auth/security-info",
            "/api/v1/auth/ping",
            "/api/v1/auth/diag",
            "/api/v1/auth/__fastlane_flags",
            "/api/v1/public/flags",
            "/api/v1/public/health/auth",
            "/api/v1/generations/models/supported",  # Public models endpoint
            "/generations/models/supported",  # Public models endpoint (without /api/v1 prefix)
            "/api/v1/debug/database",  # Debug endpoints
            "/api/v1/debug/user/",  # Debug user lookup (prefix)
            "/api/v1/debug/token/",  # Debug token validation (prefix)
            "/api/v1/performance/metrics",
            "/api/v1/performance/health"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add user context if authenticated - Railway optimized."""
        
        path = request.url.path
        method = request.method
        
        # Skip auth for excluded paths (fast path)
        if path in self.excluded_paths or any(path.startswith(prefix) for prefix in ["/api/v1/debug/", "/api/v1/e2e/"]):
            request.state.user = None
            request.state.user_id = None
            return await call_next(request)
        
        # Extract and validate Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            request.state.user = None
            request.state.user_id = None
        else:
            token = auth_header.split(" ", 1)[1]
            
            try:
                user = await self._verify_token(token)
                request.state.user = user
                request.state.user_id = user.id
            except Exception as e:
                # Silent fail - let dependencies handle auth requirements
                logger.debug(f"Token validation failed for {method} {path}: {e}")
                request.state.user = None
                request.state.user_id = None
        
        return await call_next(request)
    
    async def _verify_token(self, token: str) -> UserResponse:
        """Verify JWT token with Supabase and return user - Railway optimized with caching."""
        try:
            # Check cache first for token validation (short TTL for security)
            cache_key = f"auth_token:{hashlib.md5(token.encode()).hexdigest()}"
            cached_user = await cache_manager.get(cache_key, CacheLevel.L1_MEMORY)
            if cached_user is not None:
                logger.debug("🚀 [AUTH-MIDDLEWARE] Cache hit for token validation")
                return cached_user
            
            # SECURITY: Mock tokens completely disabled - security vulnerability removed
            if token.startswith("mock_token_"):
                logger.error(f"🚨 [SECURITY-VIOLATION] Mock token rejected - authentication bypass disabled")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed - invalid token format"
                )
            
            # SECURITY: Custom token format completely disabled - security vulnerability removed
            if token.startswith("supabase_token_"):
                logger.error(f"🚨 [SECURITY-VIOLATION] Custom token format rejected - authentication bypass disabled")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed - invalid token format"
                )
            
            # === SECURITY ENHANCED - Supabase JWT Token Verification ===
            # Check if we should use Supabase auth
            use_supabase = os.getenv("USE_SUPABASE_AUTH", "false").lower() == "true"
            
            if use_supabase:
                # Use Supabase JWT verification
                try:
                    from services.supabase_auth import get_supabase_auth
                    auth_service = get_supabase_auth()
                    payload = auth_service.verify_jwt(token)
                    user_id = payload.get("sub")
                    email = payload.get("email")
                except Exception as e:
                    logger.debug(f"Supabase JWT verification failed: {e}")
                    # Fall through to try standard JWT
                    payload = None
                    user_id = None
                    email = None
            else:
                # Use standard JWT verification for backward compatibility
                try:
                    payload = JWTSecurity.verify_token(token, "access_token")
                    user_id = payload.get("sub")
                    email = payload.get("email")
                except Exception:
                    payload = None
                    user_id = None
                    email = None
            
            if user_id and email:
                logger.info(f"✅ [AUTH-MIDDLEWARE] JWT token verification successful for user {user_id}")
                
                # Get enhanced profile from database - ASYNC OPTIMIZED
                try:
                    from database import SupabaseClient
                    db_client = SupabaseClient()
                    
                    if db_client.is_available():
                        # PERFORMANCE FIX: Use async database operations with timeout
                        profile_result = await db_client.execute_query_async(
                            table='users',
                            operation='select',
                            filters={'id': str(user_id)},
                            use_service_key=True,
                            single=True,
                            timeout=2.0  # 2 second timeout for profile lookup
                        )
                        
                        if profile_result:
                            profile = profile_result
                            
                            from utils.uuid_utils import UUIDUtils
                            safe_user_id = UUIDUtils.validate_and_convert(user_id, "JWT_profile_lookup")
                            return UserResponse(
                                id=safe_user_id,
                                email=email,
                                display_name=profile.get('display_name', ''),
                                avatar_url=profile.get('avatar_url'),
                                credits_balance=profile.get('credits_balance', 100),
                                role=profile.get('role', 'viewer'),
                                created_at=datetime.now(timezone.utc)
                            )
                except Exception as db_error:
                    logger.warning(f"⚠️ [AUTH-MIDDLEWARE] Database profile fetch failed, using JWT data: {db_error}")
                
                # Fallback to JWT data
                from utils.uuid_utils import UUIDUtils
                safe_user_id = UUIDUtils.validate_and_convert(user_id, "JWT_fallback")
                return UserResponse(
                    id=safe_user_id,
                    email=email,
                    display_name=payload.get('display_name', '') if payload else '',
                    avatar_url=payload.get('avatar_url') if payload else None,
                    credits_balance=payload.get('credits_balance', settings.default_user_credits or 100) if payload else 100,
                    role=payload.get('role', 'viewer') if payload else 'viewer',
                    created_at=datetime.now(timezone.utc)
                )
            
            # === Fallback: Use AsyncAuthService for token verification ===
            logger.info(f"🔍 [AUTH-MIDDLEWARE] Using AsyncAuthService for token verification")
            
            try:
                # Get async auth service
                auth_service = await get_async_auth_service()
                
                # Verify token via HTTP API
                token_data = await auth_service.verify_token_http(token)
                
                if not token_data:
                    logger.error(f"❌ [AUTH-MIDDLEWARE] AsyncAuthService token verification failed")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired token"
                    )
                
                user_id = token_data.get("user_id")
                email = token_data.get("email")
                
                if not user_id or not email:
                    logger.error(f"❌ [AUTH-MIDDLEWARE] Invalid token data - missing user ID or email")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token payload"
                    )
                
                logger.info(f"✅ [AUTH-MIDDLEWARE] AsyncAuthService token verification successful for user {user_id}")
                
                # Try to get enhanced profile from database via AsyncAuthService
                try:
                    profile = await auth_service.get_user_profile(user_id, timeout=2.0)
                    
                    if profile:
                        logger.info(f"✅ [AUTH-MIDDLEWARE] Enhanced profile found for user {user_id}")
                        
                        from utils.uuid_utils import UUIDUtils
                        safe_user_id = UUIDUtils.safe_uuid_convert(user_id) if isinstance(user_id, str) else user_id
                        
                        # Parse created_at timestamp
                        created_at = datetime.now(timezone.utc)
                        if profile.get('created_at'):
                            try:
                                created_at_str = profile['created_at']
                                if created_at_str.endswith('Z'):
                                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                                else:
                                    created_at = datetime.fromisoformat(created_at_str)
                            except ValueError as date_error:
                                logger.warning(f"⚠️ [AUTH-MIDDLEWARE] Date parsing failed: {date_error}, using current time")
                        
                        user_response = UserResponse(
                            id=safe_user_id,
                            email=email,
                            display_name=profile.get('display_name', ''),
                            avatar_url=profile.get('avatar_url'),
                            credits_balance=profile.get('credits_balance', 100),
                            role=profile.get('role', 'viewer'),
                            created_at=created_at
                        )
                        return await self._cache_user_response(token, user_response)
                        
                except Exception as e:
                    logger.warning(f"⚠️ [AUTH-MIDDLEWARE] Profile fetch via AsyncAuthService failed: {e}")
                
                # Fallback to basic user data from token
                logger.info(f"✅ [AUTH-MIDDLEWARE] Using basic token data for user {user_id}")
                from utils.uuid_utils import UUIDUtils
                safe_user_id = UUIDUtils.safe_uuid_convert(user_id) if isinstance(user_id, str) else user_id
                user_response = UserResponse(
                    id=safe_user_id,
                    email=email,
                    display_name="",
                    avatar_url=None,
                    credits_balance=settings.default_user_credits or 100,
                    role="viewer",
                    created_at=datetime.now(timezone.utc)
                )
                return await self._cache_user_response(token, user_response)
                
            except httpx.TimeoutException:
                logger.error(f"❌ [AUTH-MIDDLEWARE] AsyncAuthService timeout")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service timeout"
                )
            except httpx.RequestError as e:
                logger.error(f"❌ [AUTH-MIDDLEWARE] AsyncAuthService request error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service error"
                )
                
        except HTTPException:
            raise
        except SecurityError as e:
            logger.warning(f"Security error in token verification: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed"
            )
        except Exception as e:
            logger.error(f"Unexpected error in token verification: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication service error"
            )
    
    async def _cache_user_response(self, token: str, user: UserResponse) -> UserResponse:
        """Cache user response for performance optimization."""
        try:
            cache_key = f"auth_token:{hashlib.md5(token.encode()).hexdigest()}"
            # Cache for 60 seconds (short TTL for security)
            await cache_manager.set(cache_key, user, CacheLevel.L1_MEMORY, ttl=60)
            logger.debug("💾 [AUTH-MIDDLEWARE] Cached user authentication")
        except Exception as e:
            logger.warning(f"⚠️ [AUTH-MIDDLEWARE] Failed to cache user auth: {e}")
        return user


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserResponse:
    """
    FastAPI dependency to get current authenticated user.
    Raises 401 if user is not authenticated.
    Production-ready version with optimized middleware state handling.
    """
    logger.info(f"🔍 [AUTH-DEPENDENCY] get_current_user called for {request.url.path}")
    
    # Primary: Try to get user from request state (set by middleware)
    if hasattr(request.state, 'user') and request.state.user:
        user_data = request.state.user
        # Handle both dict and UserResponse object formats
        if isinstance(user_data, dict):
            user_id = user_data.get("id", user_data.get("sub"))
            logger.info(f"✅ [AUTH-DEPENDENCY] User dict found in request state: {user_id}")
            # Convert dict to UserResponse
            from utils.uuid_utils import UUIDUtils
            safe_user_id = UUIDUtils.safe_uuid_convert(user_id) if isinstance(user_id, str) else user_id
            return UserResponse(
                id=safe_user_id,
                email=user_data.get("email", ""),
                display_name=user_data.get("display_name", ""),
                avatar_url=user_data.get("avatar_url"),
                credits_balance=user_data.get("credits_balance", getattr(settings, "default_user_credits", 100)),
                role=user_data.get("role", "authenticated"),
                created_at=datetime.now(timezone.utc)
            )
        else:
            # It's already a UserResponse object
            logger.info(f"✅ [AUTH-DEPENDENCY] User object found in request state: {user_data.id}")
            return user_data
    
    # Secondary: Check if user is in state but None (middleware processed but auth failed)
    if hasattr(request.state, 'user'):
        logger.error(f"❌ [AUTH-DEPENDENCY] User is None in request state - middleware auth failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Tertiary: If not in state, verify token manually (fallback for edge cases)
    if not credentials or not credentials.credentials:
        logger.error(f"❌ [AUTH-DEPENDENCY] No credentials provided and no user in state")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Manual token verification as fallback - use JWT verification directly
    logger.warning(f"⚠️ [AUTH-DEPENDENCY] Falling back to manual JWT token verification")
    try:
        # Use JWTSecurity to verify token directly (already imported at top)
        from utils.uuid_utils import UUIDUtils
        
        payload = JWTSecurity.verify_token(credentials.credentials, "access_token")
        user_id = payload.get("sub")
        email = payload.get("email")
        
        if not user_id or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        safe_user_id = UUIDUtils.safe_uuid_convert(user_id) if isinstance(user_id, str) else user_id
        user = UserResponse(
            id=safe_user_id,
            email=email,
            display_name=payload.get('display_name', ''),
            avatar_url=payload.get('avatar_url'),
            credits_balance=payload.get('credits_balance', getattr(settings, "default_user_credits", 100)),
            role=payload.get('role', 'viewer'),
            created_at=datetime.now(timezone.utc)
        )
        
        if not user:
            logger.error(f"❌ [AUTH-DEPENDENCY] Manual token verification failed - no user found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"✅ [AUTH-DEPENDENCY] Manual token verification successful for {safe_user_id}")
        
        # Set user in request state for consistency
        request.state.user = user
        request.state.user_id = safe_user_id
        
        return user
        
    except SecurityError as e:
        # JWT verification failed (invalid token, expired, etc.)
        logger.error(f"❌ [AUTH-DEPENDENCY] JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Any other error during token verification
        logger.error(f"❌ [AUTH-DEPENDENCY] Manual token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserResponse]:
    """
    FastAPI dependency to get current user (optional).
    Returns None if user is not authenticated.
    Production-ready version with optimized error handling.
    """
    logger.info(f"🔍 [AUTH-DEPENDENCY] get_current_user_optional called for {request.url.path}")
    
    # Quick check: if user is already in state (from middleware), return it
    if hasattr(request.state, 'user'):
        if request.state.user:
            logger.info(f"✅ [AUTH-DEPENDENCY] Optional auth successful from state for {request.state.user.id}")
            return request.state.user
        else:
            logger.info(f"ℹ️ [AUTH-DEPENDENCY] Optional auth - user is None in state (expected)")
            return None
    
    # Otherwise, try full authentication flow
    try:
        user = await get_current_user(request, credentials)
        logger.info(f"✅ [AUTH-DEPENDENCY] Optional auth successful for {user.id}")
        return user
    except HTTPException as e:
        logger.info(f"ℹ️ [AUTH-DEPENDENCY] Optional auth failed (expected): {e.detail}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ [AUTH-DEPENDENCY] Unexpected error in optional auth: {e}")
        return None


async def get_user_id(request: Request) -> str:
    """Get current user ID from request state."""
    if not hasattr(request.state, 'user_id') or not request.state.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return request.state.user_id


def require_credits(min_credits: int):
    """Dependency factory to check if user has enough credits."""
    async def check_credits(user: UserResponse = Depends(get_current_user)):
        if user.credits_balance < min_credits:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient credits. Required: {min_credits}, Available: {user.credits_balance}"
            )
        return user
    return check_credits


def require_auth(required_role: Optional[str] = None, required_permissions: Optional[List[str]] = None):
    """
    Dependency factory for requiring authentication with optional role/permission checks.
    
    Args:
        required_role: Minimum role required (e.g., "admin", "editor")
        required_permissions: List of required permissions
    
    Returns:
        Dependency function that validates authentication and authorization
    """
    async def auth_dependency(user: UserResponse = Depends(get_current_user)):
        # User is already authenticated by get_current_user
        
        # Check role requirements if specified
        if required_role:
            role_hierarchy = {
                "viewer": 0,
                "editor": 1,
                "admin": 2,
                "owner": 3
            }
            
            user_role_level = role_hierarchy.get(user.role, 0)
            required_role_level = role_hierarchy.get(required_role, 999)
            
            if user_role_level < required_role_level:
                logger.warning(f"User {user.id} has insufficient role: {user.role} < {required_role}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Required role: {required_role}"
                )
        
        # Check permission requirements if specified
        if required_permissions:
            # For now, basic permission check based on role
            # This can be extended with a proper permission system later
            user_permissions = []
            if user.role in ["admin", "owner"]:
                user_permissions = ["read", "write", "delete", "manage_users", "manage_teams"]
            elif user.role == "editor":
                user_permissions = ["read", "write"]
            elif user.role == "viewer":
                user_permissions = ["read"]
            
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                logger.warning(f"User {user.id} missing permissions: {missing_permissions}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing permissions: {', '.join(missing_permissions)}"
                )
        
        return user
    
    return auth_dependency


async def get_user_supabase_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Get an authenticated Supabase client for the current user.
    This client enforces RLS (Row Level Security) policies.
    
    In production, this requires a valid JWT token.
    For development, USE_SERVICE_CLIENT_FALLBACK=true can bypass this (NOT for production).
    """
    
    # Check for service client fallback (development only)
    use_fallback = os.getenv("USE_SERVICE_CLIENT_FALLBACK", "false").lower() == "true"
    environment = os.getenv("ENVIRONMENT", "production")
    
    if not credentials:
        # No token provided - check if fallback is allowed
        if use_fallback and environment != "production":
            logger.warning("⚠️ [AUTH-MIDDLEWARE] No token provided, using service client fallback (DEV ONLY)")
            return db.service_client
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # SECURITY: Mock tokens completely disabled - security vulnerability removed
    if credentials.credentials.startswith("mock_token_"):
        logger.error(f"🚨 [SECURITY-VIOLATION] Mock token rejected in client creation")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed - invalid token format"
        )
    
    # SECURITY: Custom token format completely disabled - security vulnerability removed
    if credentials.credentials.startswith("supabase_token_"):
        logger.error(f"🚨 [SECURITY-VIOLATION] Custom token format rejected in client creation")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed - invalid token format"
        )
    
    token = credentials.credentials
    
    try:
        # Get async auth service
        auth_service = await get_async_auth_service()
        
        # Get authenticated Supabase client configured for user with RLS
        authenticated_client = await auth_service.get_authenticated_client(token)
        
        logger.info(f"✅ [AUTH-MIDDLEWARE] Authenticated Supabase client created with RLS for user")
        return authenticated_client
        
    except ValueError as e:
        # Invalid token format
        logger.error(f"❌ [AUTH-MIDDLEWARE] Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e}"
        )
    except RuntimeError as e:
        # Failed to create client
        logger.error(f"❌ [AUTH-MIDDLEWARE] Failed to create authenticated client: {e}")
        
        # Check if fallback is allowed for development
        if use_fallback and environment != "production":
            logger.warning("⚠️ [AUTH-MIDDLEWARE] Falling back to service client (DEV ONLY)")
            return db.service_client
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable"
        )
    except Exception as e:
        logger.error(f"❌ [AUTH-MIDDLEWARE] Unexpected error creating authenticated client: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Client creation failed"
        )