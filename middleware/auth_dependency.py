"""
Production Authentication Dependency
Provides secure JWT-based authentication for all protected endpoints.
Replaces emergency auth mode with OWASP-compliant security.
"""

import logging
from typing import Optional
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from utils.jwt_security import verify_supabase_jwt, JWTSecurityError
from services.auth_service_async import AsyncAuthService as AuthService
from database import SupabaseClient
from models.user import UserResponse

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)

class AuthenticationError(Exception):
    """Authentication-related errors."""
    pass

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserResponse:
    """
    Production authentication dependency.
    Validates JWT tokens and returns authenticated user.
    
    Args:
        request: FastAPI request object
        credentials: Bearer token credentials
        
    Returns:
        Authenticated user object
        
    Raises:
        HTTPException: If authentication fails
    """
    # Check for Authorization header
    if not credentials:
        logger.warning("🚫 [AUTH] No authorization header provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    if not token:
        logger.warning("🚫 [AUTH] Empty token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        # Log request details for security monitoring
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")
        
        logger.info(f"🔍 [AUTH] Authentication attempt from {client_ip}")
        
        # Validate JWT token using production security service
        verified_payload = verify_supabase_jwt(token)
        user_id = verified_payload.get('user_id')
        
        if not user_id:
            logger.error("❌ [AUTH] No user_id in JWT payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        logger.info(f"✅ [AUTH] JWT validation successful for user {user_id}")
        
        # Get user from database
        db_client = SupabaseClient()
        auth_service = AuthService(db_client)
        
        user = await auth_service.get_user_by_id(user_id)
        
        if not user:
            # User exists in JWT but not in database - create basic profile
            logger.info(f"🔄 [AUTH] Creating user profile for {user_id}")
            
            from uuid import UUID
            from datetime import datetime, timezone
            
            user = UserResponse(
                id=UUID(user_id),
                email=verified_payload.get('email', ''),
                display_name=verified_payload.get('user_metadata', {}).get('display_name', ''),
                avatar_url=verified_payload.get('user_metadata', {}).get('avatar_url'),
                credits_balance=100,  # Default credits
                role=verified_payload.get('app_metadata', {}).get('role', 'viewer'),
                created_at=datetime.now(timezone.utc)
            )
            
            # Try to sync to database
            try:
                await auth_service.sync_user_profile(user)
                logger.info(f"✅ [AUTH] User profile synced to database")
            except Exception as sync_error:
                logger.warning(f"⚠️ [AUTH] User sync failed: {sync_error}")
                # Continue with in-memory user object
        
        # Add user to request state for other middleware/endpoints
        request.state.user = user
        
        logger.debug(f"✅ [AUTH] Authentication successful for {user.email}")
        return user
        
    except JWTSecurityError as e:
        logger.warning(f"🚫 [AUTH] JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"❌ [AUTH] Authentication error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable"
        )

async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserResponse]:
    """
    Optional authentication dependency.
    Returns user if authenticated, None if not authenticated.
    Does not raise exceptions for missing/invalid tokens.
    
    Args:
        request: FastAPI request object
        credentials: Bearer token credentials
        
    Returns:
        Authenticated user object or None
    """
    try:
        return await get_current_user(request, credentials)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            # Authentication failed, but that's OK for optional auth
            return None
        else:
            # Re-raise other HTTP exceptions (like 500 errors)
            raise
    except Exception:
        # For optional auth, return None on any error
        return None

async def require_admin_user(
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """
    Admin authorization dependency.
    Requires authenticated user with admin role.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Admin user object
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.role not in ['admin', 'super_admin']:
        logger.warning(f"🚫 [AUTH] Access denied for user {current_user.id}: role={current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    logger.info(f"✅ [AUTH] Admin access granted for {current_user.email}")
    return current_user

async def require_pro_user(
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """
    Pro user authorization dependency.
    Requires authenticated user with pro or admin role.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Pro/admin user object
        
    Raises:
        HTTPException: If user is not pro/admin
    """
    if current_user.role not in ['pro', 'admin', 'super_admin']:
        logger.warning(f"🚫 [AUTH] Pro access denied for user {current_user.id}: role={current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required"
        )
    
    return current_user

# Health check for authentication system
async def auth_health_check() -> dict:
    """Check authentication system health."""
    try:
        # Test JWT security service
        from utils.jwt_security import jwt_health_check
        jwt_health = await jwt_health_check()
        
        # Test database connection
        db_client = SupabaseClient()
        db_health = db_client.is_available()
        
        return {
            "status": "healthy" if jwt_health["status"] == "healthy" and db_health else "unhealthy",
            "jwt_security": jwt_health,
            "database_connection": "available" if db_health else "unavailable"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }