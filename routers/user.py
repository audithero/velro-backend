"""
User profile and account management router.
Provides endpoints for user profile, credits, and account information.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any
import logging

from middleware.auth import get_current_user
from services.user_service import UserService
from models.user import UserResponse

router = APIRouter(tags=["user"])
logger = logging.getLogger(__name__)


async def get_user_service() -> UserService:
    """Dependency to get UserService instance."""
    return UserService()


@router.get("/profile")
async def get_user_profile(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """Get the current user's profile information."""
    try:
        user_id = str(current_user.id)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID not found in token"
            )
        
        # Get auth token from request state
        auth_token = getattr(request.state, "auth_token", None)
        
        # Get user profile from service
        user_service = UserService()
        
        try:
            profile = await user_service.get_user_profile(user_id)
            return profile
        except Exception as e:
            logger.warning(f"Failed to get profile from database: {e}")
            # Return basic profile from UserResponse if database lookup fails
            return {
                "id": user_id,
                "email": current_user.email,
                "full_name": getattr(current_user, 'full_name', None),
                "role": current_user.role,
                "created_at": getattr(current_user, 'created_at', None),
                "avatar_url": getattr(current_user, 'avatar_url', None),
                "metadata": {},
                "credits_balance": current_user.credits_balance
            }
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )


@router.get("/credits")
async def get_user_credits(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """Get the current user's credit balance."""
    try:
        user_id = str(current_user.id)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID not found in token"
            )
        
        # Get auth token from request state
        auth_token = getattr(request.state, "auth_token", None)
        
        # Get credits from service
        user_service = UserService()
        
        try:
            credits = await user_service.get_user_credits(user_id, auth_token=auth_token)
            return {
                "user_id": user_id,
                "credits_balance": credits if credits is not None else 0,
                "currency": "credits"
            }
        except Exception as e:
            logger.warning(f"Failed to get credits from database: {e}")
            # Return default credits if database lookup fails
            return {
                "user_id": user_id,
                "credits_balance": 0,
                "currency": "credits"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get user credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user credits"
        )


@router.put("/profile")
async def update_user_profile(
    profile_data: Dict[str, Any],
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """Update the current user's profile information."""
    try:
        user_id = str(current_user.id)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID not found in token"
            )
        
        # Get auth token from request state
        auth_token = getattr(request.state, "auth_token", None)
        
        # Update profile via service
        user_service = UserService()
        updated_profile = await user_service.update_user_profile(user_id, profile_data)
        
        return updated_profile
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile"
        )


@router.get("/info")
async def get_user_info(
    current_user: UserResponse = Depends(get_current_user)
):
    """Get basic user information (lightweight endpoint)."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role,
        "authenticated": True
    }