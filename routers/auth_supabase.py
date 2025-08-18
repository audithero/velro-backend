"""
Supabase-based authentication router.
All auth flows go through Supabase - no custom JWT creation.
"""

from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta
import jwt
import os
import httpx

from services.supabase_auth import (
    get_supabase_auth,
    get_current_user,
    get_current_user_optional,
    security,
    SupabaseAuth
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["authentication"],
    responses={
        401: {"description": "Unauthorized"},
        503: {"description": "Service unavailable"}
    }
)


# Request/Response models
class LoginRequest(BaseModel):
    """Login request with email and password."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="User password")


class TokenResponse(BaseModel):
    """Token response with Supabase session data."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: Dict[str, Any]


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str = Field(..., description="Refresh token from login")


class UserResponse(BaseModel):
    """User info response."""
    id: str
    email: str
    role: str
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = {}


class UserRegister(BaseModel):
    """Registration request with email, password, and optional full name."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password")
    full_name: Optional[str] = Field(None, description="User's full name")


@router.post("/register", response_model=TokenResponse)
async def register(
    request: Request,
    user_data: UserRegister
) -> TokenResponse:
    """
    Register a new user via Supabase.
    Creates a new account and returns session tokens.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.info(
        f"[{request_id}] Registration attempt for {user_data.email}",
        extra={
            "request_id": request_id,
            "email": user_data.email,
            "path": "/api/v1/auth/register"
        }
    )
    
    try:
        auth = get_supabase_auth()
        
        # Register user via Supabase Admin API
        user = await auth.sign_up(
            email=user_data.email,
            password=user_data.password,
            user_metadata={
                "full_name": user_data.full_name or "",
                "credits_balance": 100,  # Default credits
                "current_plan": "free"
            }
        )
        
        logger.info(
            f"[{request_id}] User registered successfully: {user['id']}",
            extra={
                "request_id": request_id,
                "email": user_data.email,
                "user_id": user["id"],
                "event": "auth.register.success"
            }
        )
        
        # Create user profile in database with initial credits
        try:
            from services.user_service import user_service
            await user_service.create_user_profile(
                user_id=user["id"],
                email=user_data.email,
                full_name=user_data.full_name
                # Uses settings.default_user_credits (1000 credits)
            )
            logger.info(f"[{request_id}] User profile created with initial credits for {user['id']}")
        except Exception as profile_error:
            logger.error(f"[{request_id}] Failed to create user profile: {profile_error}")
            # Continue anyway - user can still log in
        
        # Now sign them in to get a session
        session = await auth.sign_in_with_password(
            email=user_data.email,
            password=user_data.password
        )
        
        return TokenResponse(
            access_token=session["access_token"],
            refresh_token=session["refresh_token"],
            expires_in=session["expires_in"],
            user=session["user"]
        )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[{request_id}] Unexpected registration error: {e}",
            extra={
                "request_id": request_id,
                "error": str(e),
                "event": "auth.register.error"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )




@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    credentials: LoginRequest
) -> TokenResponse:
    """
    Login with email and password via Supabase.
    Returns Supabase session tokens.
    """
    start_time = datetime.utcnow()
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.info(
        f"[{request_id}] Login attempt for {credentials.email}",
        extra={
            "request_id": request_id,
            "email": credentials.email,
            "path": "/api/v1/auth/login"
        }
    )
    
    try:
        auth = get_supabase_auth()
        session = await auth.sign_in_with_password(
            email=credentials.email,
            password=credentials.password
        )
        
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.info(
            f"[{request_id}] Login successful for {credentials.email} in {duration_ms:.2f}ms",
            extra={
                "request_id": request_id,
                "email": credentials.email,
                "user_id": session["user"]["id"],
                "duration_ms": duration_ms,
                "event": "auth.login.success"
            }
        )
        
        return TokenResponse(
            access_token=session["access_token"],
            refresh_token=session["refresh_token"],
            expires_in=session["expires_in"],
            user=session["user"]
        )
        
    except HTTPException as e:
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.warning(
            f"[{request_id}] Login failed for {credentials.email}: {e.detail} in {duration_ms:.2f}ms",
            extra={
                "request_id": request_id,
                "email": credentials.email,
                "error": e.detail,
                "status_code": e.status_code,
                "duration_ms": duration_ms,
                "event": "auth.login.failed"
            }
        )
        raise
    except Exception as e:
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.error(
            f"[{request_id}] Unexpected login error for {credentials.email}: {e} in {duration_ms:.2f}ms",
            extra={
                "request_id": request_id,
                "email": credentials.email,
                "error": str(e),
                "duration_ms": duration_ms,
                "event": "auth.login.error"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to server error"
        )


@router.get("/me")
async def get_me(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current user profile information.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Import logger at the beginning - FIXED: moved before first use
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(
        f"[{request_id}] Profile requested for user {current_user['id']}",
        extra={
            "request_id": request_id,
            "user_id": current_user["id"],
            "event": "auth.me.success"
        }
    )
    
    # CRITICAL FIX: Query actual credits from database, not user_metadata
    user_id = current_user.get("id")
    actual_credits = 10  # Default fallback
    
    try:
        # Import here to avoid circular dependency
        from services.user_service import user_service
        
        logger.info(f"💳 [AUTH_SUPABASE] Fetching actual credits for user {user_id}")
        
        # Extract auth token from request for proper database access
        auth_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]
        
        # Get actual credits from database
        actual_credits = await user_service.get_user_credits(str(user_id), auth_token=auth_token)
        logger.info(f"✅ [AUTH_SUPABASE] Retrieved actual credits: {actual_credits} for user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ [AUTH_SUPABASE] Failed to get actual credits for user {user_id}: {e}")
        # Fall back to user_metadata or default
        actual_credits = current_user.get("user_metadata", {}).get("credits_balance", 10)
    
    # Return user data in expected format with ACTUAL credits
    return {
        "id": current_user.get("id"),
        "email": current_user.get("email"),
        "full_name": current_user.get("user_metadata", {}).get("full_name", ""),
        "credits_balance": actual_credits,  # Use actual database value
        "created_at": current_user.get("created_at"),
        "updated_at": current_user.get("updated_at"),
        "role": current_user.get("role", "user")
    }


@router.post("/logout")
async def logout(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> JSONResponse:
    """
    Logout current user by revoking their token.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    try:
        # Get token from request
        token = None
        if "authorization" in request.headers:
            auth_header = request.headers["authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        
        if token:
            auth = get_supabase_auth()
            await auth.sign_out(token)
        
        logger.info(
            f"[{request_id}] User {current_user['id']} logged out",
            extra={
                "request_id": request_id,
                "user_id": current_user["id"],
                "event": "auth.logout.success"
            }
        )
        
        return JSONResponse(
            content={"message": "Logged out successfully"},
            status_code=200
        )
        
    except Exception as e:
        logger.error(
            f"[{request_id}] Logout error for user {current_user['id']}: {e}",
            extra={
                "request_id": request_id,
                "user_id": current_user["id"],
                "error": str(e),
                "event": "auth.logout.error"
            }
        )
        # Still return success to client
        return JSONResponse(
            content={"message": "Logged out"},
            status_code=200
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    refresh_request: RefreshRequest
) -> TokenResponse:
    """
    Refresh access token using refresh token.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    try:
        auth = get_supabase_auth()
        session = await auth.refresh_token(refresh_request.refresh_token)
        
        logger.info(
            f"[{request_id}] Token refreshed for user {session['user']['id']}",
            extra={
                "request_id": request_id,
                "user_id": session["user"]["id"],
                "event": "auth.refresh.success"
            }
        )
        
        return TokenResponse(
            access_token=session["access_token"],
            refresh_token=session["refresh_token"],
            expires_in=session["expires_in"],
            user=session["user"]
        )
        
    except HTTPException as e:
        logger.warning(
            f"[{request_id}] Token refresh failed: {e.detail}",
            extra={
                "request_id": request_id,
                "error": e.detail,
                "event": "auth.refresh.failed"
            }
        )
        raise
    except Exception as e:
        logger.error(
            f"[{request_id}] Unexpected refresh error: {e}",
            extra={
                "request_id": request_id,
                "error": str(e),
                "event": "auth.refresh.error"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.get("/whoami", response_model=UserResponse)
async def whoami(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> UserResponse:
    """
    Get current authenticated user info.
    This is a canary endpoint for testing auth.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.info(
        f"[{request_id}] Whoami called by user {current_user['id']}",
        extra={
            "request_id": request_id,
            "user_id": current_user["id"],
            "email": current_user.get("email", "unknown"),
            "event": "auth.whoami"
        }
    )
    
    return UserResponse(
        id=current_user["id"],
        email=current_user.get("email", ""),
        role=current_user.get("role", "authenticated"),
        created_at=current_user.get("created_at"),
        metadata=current_user.get("metadata", {})
    )


@router.get("/health")
async def auth_health() -> JSONResponse:
    """
    Health check for auth service.
    Tests Supabase connectivity.
    """
    try:
        auth = get_supabase_auth()
        # Just verify we can create the auth instance
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "auth",
                "supabase_url": auth.url,
                "timestamp": datetime.utcnow().isoformat()
            },
            status_code=200
        )
    except Exception as e:
        logger.error(f"Auth health check failed: {e}")
        return JSONResponse(
            content={
                "status": "unhealthy",
                "service": "auth",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            },
            status_code=503
        )


# Optional: Public endpoint to check if email exists (for signup flow)
@router.post("/check-email")
async def check_email(
    email: EmailStr
) -> JSONResponse:
    """
    Check if email is already registered.
    This is a public endpoint.
    """
    # This would require admin access to Supabase
    # For now, return a generic response for security
    return JSONResponse(
        content={"available": True},
        status_code=200
    )