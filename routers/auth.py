"""
Authentication router for user login, registration, and token management.
Following CLAUDE.md: Router layer with comprehensive rate limiting and security.
"""
import time
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from models.user import (
    UserLogin, UserCreate, UserResponse, UserUpdate, Token, 
    PasswordReset, PasswordResetConfirm, TokenRefresh
)
from middleware.auth import get_current_user
from middleware.rate_limiting import auth_limit, limit, api_limit
from services.auth_service import AuthService
from repositories.user_repository import UserRepository
from config import settings
import logging

router = APIRouter(tags=["authentication"])
security = HTTPBearer()
logger = logging.getLogger(__name__)


@router.get("/ping")
async def auth_ping():
    """
    Ultra-fast auth ping endpoint for connection testing.
    
    Performance characteristics:
    - No database connections
    - No Redis connections  
    - No authentication required
    - Bypasses heavy middleware via fastpath
    - Target: <100ms response time
    - Ideal: <50ms response time
    """
    return {
        "status": "ok", 
        "service": "auth",
        "timestamp": time.time(),
        "fastpath": True,
        "performance": "optimized"
    }


@router.get("/diag")
async def auth_diagnostics():
    """
    Diagnostic endpoint for auth configuration debugging.
    Returns masked key information and timeout configuration.
    """
    import os
    import httpx
    
    # Get key values
    publishable_key = os.getenv('SUPABASE_PUBLISHABLE_KEY', '')
    anon_key = os.getenv('SUPABASE_ANON_KEY', '')
    service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    
    # Mask keys for security
    def mask_key(key: str) -> str:
        if not key:
            return "NOT_SET"
        if len(key) < 20:
            return "INVALID_LENGTH"
        # Check if it's a JWT (has 3 parts separated by dots)
        parts = key.split('.')
        if len(parts) == 3:
            return f"JWT_{key[:10]}...{key[-10:]}"
        else:
            return f"KEY_{key[:10]}...{key[-10:]}"
    
    return {
        "status": "diagnostic",
        "keys": {
            "publishable_key": mask_key(publishable_key),
            "anon_key": mask_key(anon_key),
            "service_key": mask_key(service_key),
            "key_type_used": "publishable" if publishable_key else "anon"
        },
        "timeout_config": {
            "connect": "3.0s",
            "read": "8.0s",
            "write": "2.0s",
            "pool": "1.0s",
            "asyncio_wrap": "8.5s"
        },
        "http_config": {
            "http2": False,
            "max_connections": 100,
            "keepalive_connections": 20
        },
        "supabase_url": os.getenv('SUPABASE_URL', 'NOT_SET')
    }


@router.post("/validate")
async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Fast token validation endpoint.
    Returns quickly if token is valid, raises 401 if not.
    """
    try:
        from services.auth_service_async import get_async_auth_service
        auth_service = await get_async_auth_service()
        
        # Quick token validation
        is_valid = await auth_service.verify_token(credentials.credentials)
        if is_valid:
            return {"valid": True, "timestamp": time.time()}
        else:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(status_code=401, detail="Token validation failed")


@router.post("/login", response_model=Token)
@limit("5/minute")  # Strict rate limit for login attempts
async def login(credentials: UserLogin, request: Request):
    """
    User login endpoint with rate limiting protection.
    
    Rate limit: 5 attempts per minute per IP/user to prevent brute force attacks.
    """
    try:
        import time
        start_time = time.time()
        
        # CRITICAL FIX: Use cached database client to avoid connection overhead
        from database import get_database
        db_client = await get_database()
        
        init_time = time.time()
        logger.info(f"[AUTH-PERF] DB client initialized in {(init_time - start_time)*1000:.2f}ms")
        
        auth_service = AuthService(db_client)
        service_time = time.time()
        logger.info(f"[AUTH-PERF] Auth service created in {(service_time - init_time)*1000:.2f}ms")
        
        # Authenticate user with timeout protection
        import asyncio
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("User-Agent", "unknown")
            user = await asyncio.wait_for(
                auth_service.authenticate_user(credentials, client_ip, user_agent),
                timeout=15.0  # 15 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("[AUTH-PERF] Authentication timed out after 15 seconds")
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Authentication request timed out. Please try again."
            )
        
        auth_time = time.time()
        logger.info(f"[AUTH-PERF] User authenticated in {(auth_time - service_time)*1000:.2f}ms")
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Create access token with timeout protection
        try:
            token = await asyncio.wait_for(
                auth_service.create_access_token(user),
                timeout=5.0  # 5 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("[AUTH-PERF] Token creation timed out after 5 seconds")
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Token creation timed out. Please try again."
            )
        
        total_time = time.time()
        logger.info(f"[AUTH-PERF] Total login time: {(total_time - start_time)*1000:.2f}ms")
        
        return token
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log failed login attempt for security monitoring
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Login failed from {client_ip} for email: {credentials.email} - Error: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}" if settings.debug else "Login failed"
        )


@router.post("/register", response_model=Token)
@limit("3/minute")  # Even stricter limit for registrations
async def register(user_data: UserCreate, request: Request):
    """
    User registration endpoint with rate limiting protection.
    
    Rate limit: 3 registrations per minute per IP to prevent spam accounts.
    Returns access token upon successful registration.
    """
    try:
        import time
        start_time = time.time()
        
        # CRITICAL FIX: Use singleton database client to eliminate per-request creation
        from database import get_database
        db_client = await get_database()
        
        init_time = time.time()
        logger.info(f"[AUTH-PERF] DB client initialized in {(init_time - start_time)*1000:.2f}ms")
        
        auth_service = AuthService(db_client)
        
        # Register new user with timeout protection
        import asyncio
        try:
            user = await asyncio.wait_for(
                auth_service.register_user(user_data),
                timeout=10.0  # 10 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("[AUTH-PERF] Registration timed out after 10 seconds")
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Registration request timed out. Please try again."
            )
        
        register_time = time.time()
        logger.info(f"[AUTH-PERF] User registered in {(register_time - init_time)*1000:.2f}ms")
        
        # Create access token for the new user
        try:
            token = await asyncio.wait_for(
                auth_service.create_access_token(user),
                timeout=5.0  # 5 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("[AUTH-PERF] Token creation timed out after 5 seconds")
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Token creation timed out. Please try again."
            )
        
        total_time = time.time()
        logger.info(f"[AUTH-PERF] Total registration time: {(total_time - start_time)*1000:.2f}ms")
        
        return token
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log registration attempt for monitoring
        client_ip = request.client.host if request.client else "unknown"
        logger.error(f"Registration failed from {client_ip} for email: {user_data.email} - Error: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}" if settings.debug else "Registration failed"
        )


@router.get("/me", response_model=UserResponse)
@api_limit()  # Standard API rate limit
async def get_current_user_info(request: Request, current_user: UserResponse = Depends(get_current_user)):
    """
    Get current authenticated user information.
    
    Requires valid JWT token. Rate limited to prevent abuse.
    """
    return current_user


@router.get("/debug-auth")
@api_limit()  # Standard API rate limit  
async def debug_auth_middleware(request: Request):
    """
    Debug endpoint to test middleware authentication without dependencies.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔍 [DEBUG-AUTH] Request state user: {getattr(request.state, 'user', 'NOT_SET')}")
    logger.info(f"🔍 [DEBUG-AUTH] Request state user_id: {getattr(request.state, 'user_id', 'NOT_SET')}")
    logger.info(f"🔍 [DEBUG-AUTH] Auth header: {request.headers.get('Authorization', 'NOT_SET')}")
    
    if hasattr(request.state, 'user') and request.state.user:
        user = request.state.user
        return {
            "status": "authenticated",
            "user_id": str(user.id),
            "email": user.email,
            "message": "Middleware authentication successful"
        }
    else:
        return {
            "status": "not_authenticated", 
            "message": "Middleware did not set user state",
            "auth_header_present": bool(request.headers.get('Authorization')),
            "request_path": str(request.url.path)
        }


@router.post("/refresh", response_model=Token)
@limit("10/minute")  # Allow more frequent token refreshes
async def refresh_token(
    refresh_data: TokenRefresh,
    request: Request
):
    """
    Refresh JWT access token using refresh token.
    
    Rate limit: 10 refreshes per minute per user to prevent abuse while allowing normal usage.
    """
    try:
        import time
        start_time = time.time()
        
        # CRITICAL FIX: Use singleton database client
        from database import get_database
        db_client = await get_database()
        
        init_time = time.time()
        logger.info(f"[AUTH-PERF] DB client initialized in {(init_time - start_time)*1000:.2f}ms")
        
        auth_service = AuthService(db_client)
        
        # Refresh access token with timeout protection
        import asyncio
        try:
            token = await asyncio.wait_for(
                auth_service.refresh_access_token(refresh_data.refresh_token),
                timeout=10.0  # 10 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("[AUTH-PERF] Token refresh timed out after 10 seconds")
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Token refresh timed out. Please try again."
            )
        
        total_time = time.time()
        logger.info(f"[AUTH-PERF] Total refresh time: {(total_time - start_time)*1000:.2f}ms")
        
        return token
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log failed refresh attempt
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed token refresh from {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/password-reset")
@limit("2/minute")  # Very strict limit for password reset requests
async def request_password_reset(
    reset_request: PasswordReset,
    request: Request
):
    """
    Request password reset email.
    
    Rate limit: 2 requests per minute per IP to prevent email spam.
    """
    try:
        import time
        start_time = time.time()
        
        # CRITICAL FIX: Use singleton database client
        from database import get_database
        db_client = await get_database()
        
        init_time = time.time()
        logger.info(f"[AUTH-PERF] DB client initialized in {(init_time - start_time)*1000:.2f}ms")
        
        auth_service = AuthService(db_client)
        
        # Check if we're in development mode with invalid Supabase keys
        if settings.development_mode and not db_client.is_available():
            client_ip = request.client.host if request.client else "unknown"
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Mock password reset requested from {client_ip} for email: {reset_request.email}")
            return {
                "message": "Password reset email sent (development mode)",
                "email": reset_request.email
            }
        
        # Use Supabase Auth password reset
        result = db_client.client.auth.reset_password_email(reset_request.email)
        
        # Log password reset attempt for security monitoring
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Password reset email sent from {client_ip} for email: {reset_request.email}")
        
        return {
            "message": "Password reset email sent if account exists",
            "email": reset_request.email
        }
        
    except Exception as e:
        # Log password reset attempt
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Password reset failed from {client_ip} for email: {reset_request.email} - Error: {e}")
        
        # Always return success message for security (don't reveal if email exists)
        return {
            "message": "Password reset email sent if account exists",
            "email": reset_request.email
        }


@router.post("/password-reset-confirm")
@limit("5/minute")  # Reasonable limit for password reset confirmation
async def confirm_password_reset(
    reset_data: PasswordResetConfirm,
    request: Request
):
    """
    Confirm password reset with token and new password.
    
    Rate limit: 5 attempts per minute to prevent token brute force.
    """
    try:
        import time
        start_time = time.time()
        
        # CRITICAL FIX: Use singleton database client
        from database import get_database
        db_client = await get_database()
        
        init_time = time.time()
        logger.info(f"[AUTH-PERF] DB client initialized in {(init_time - start_time)*1000:.2f}ms")
        
        auth_service = AuthService(db_client)
        
        # Check if we're in development mode with invalid Supabase keys
        if settings.development_mode and not db_client.is_available():
            client_ip = request.client.host if request.client else "unknown"
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Mock password reset confirmation from {client_ip}")
            return {
                "message": "Password reset successful (development mode)"
            }
        
        # Use Supabase Auth to confirm password reset
        # Note: In Supabase, this typically happens via the auth UI/email flow
        # For API-based reset, we'd need to verify the token and update the password
        try:
            # Verify the reset token and update password using Supabase Admin API
            # This requires implementing proper token verification
            
            # For now, return guidance for proper implementation
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Password reset confirmation requires client-side implementation with Supabase Auth UI"
            )
            
        except Exception as supabase_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token or password reset failed"
            )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log password reset confirmation attempt
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Password reset confirmation error from {client_ip}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset confirmation failed"
        )


@router.post("/logout")
@api_limit()  # Standard rate limit
async def logout(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Logout current user session.
    
    Invalidates the current session/token if session management is implemented.
    """
    try:
        # TODO: Implement logout logic (if needed for session management)
        # For stateless JWT, this might just return success
        # For session-based auth, invalidate the session
        
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"User {current_user.id} logged out from {client_ip}")
        
        return {
            "message": "Logout successful",
            "timestamp": int(time.time())
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.get("/security-info")
@api_limit()  # Standard rate limit
async def get_security_info(request: Request):
    """
    Get authentication security information and rate limits.
    
    Provides information about rate limits and security measures for transparency.
    """
    return {
        "rate_limits": {
            "login": "5 attempts per minute",
            "register": "3 attempts per minute", 
            "refresh": "10 attempts per minute",
            "password_reset": "2 requests per minute",
            "password_reset_confirm": "5 attempts per minute"
        },
        "security_features": [
            "JWT authentication",
            "Rate limiting",
            "Input validation",
            "Password strength requirements",
            "Email validation",
            "Request logging"
        ],
        "password_requirements": {
            "min_length": 8,
            "max_length": 128,
            "required": ["letters", "numbers"],
            "forbidden": ["common_passwords", "personal_info"]
        }
    }


@router.put("/profile", response_model=UserResponse)
@api_limit()  # Standard API rate limit
async def update_profile(
    user_data: UserUpdate,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Update user profile information.
    
    Allows updating display_name and avatar_url.
    Rate limit: Standard API rate limiting.
    """
    try:
        import time
        start_time = time.time()
        
        # CRITICAL FIX: Use singleton database client
        from database import get_database
        db_client = await get_database()
        
        init_time = time.time()
        logger.info(f"[AUTH-PERF] DB client initialized in {(init_time - start_time)*1000:.2f}ms")
        
        user_repository = UserRepository(db_client)
        
        # Update user profile with timeout protection
        import asyncio
        try:
            updated_user = await asyncio.wait_for(
                user_repository.update_user_profile(
                    user_id=current_user.id,
                    update_data=user_data
                ),
                timeout=10.0  # 10 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("[AUTH-PERF] Profile update timed out after 10 seconds")
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Profile update timed out. Please try again."
            )
        
        total_time = time.time()
        logger.info(f"[AUTH-PERF] Total profile update time: {(total_time - start_time)*1000:.2f}ms")
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Log profile update for security monitoring
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Profile updated from {client_ip} for user: {current_user.id}")
        
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        # Log error for debugging
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Profile update failed from {client_ip} for user {current_user.id}: {str(e)}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update failed"
        )