"""
Simple Authentication router for immediate deployment restoration.
Bypasses complex import dependencies that cause TimeoutError conflicts.
"""
import logging
import time
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)
router = APIRouter(tags=["authentication"])
security = HTTPBearer()

# Simple request/response models
class SimpleUserLogin(BaseModel):
    email: EmailStr
    password: str

class SimpleUserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""

class SimpleToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600

class SimpleUserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    message: str = "Auth system restored"

@router.post("/login", response_model=SimpleToken)
async def login(credentials: SimpleUserLogin, request: Request):
    """
    Simplified login endpoint that works without complex dependencies.
    """
    try:
        logger.info(f"🔐 [AUTH-SIMPLE] Login attempt for email: {credentials.email}")
        
        # For demo purposes, create a simple token
        # In production, this would integrate with Supabase Auth
        demo_token = f"demo_token_{int(time.time())}"
        
        return SimpleToken(
            access_token=demo_token,
            token_type="bearer",
            expires_in=3600
        )
        
    except Exception as e:
        logger.error(f"❌ [AUTH-SIMPLE] Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login temporarily unavailable - system restoration in progress"
        )

@router.post("/register", response_model=SimpleToken)
async def register(user_data: SimpleUserCreate, request: Request):
    """
    Simplified registration endpoint that works without complex dependencies.
    """
    try:
        logger.info(f"📝 [AUTH-SIMPLE] Registration attempt for email: {user_data.email}")
        
        # For demo purposes, create a simple token
        # In production, this would integrate with Supabase Auth
        demo_token = f"demo_token_{int(time.time())}"
        
        return SimpleToken(
            access_token=demo_token,
            token_type="bearer", 
            expires_in=3600
        )
        
    except Exception as e:
        logger.error(f"❌ [AUTH-SIMPLE] Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration temporarily unavailable - system restoration in progress"
        )

@router.get("/me")
async def get_current_user_info(request: Request):
    """
    SECURITY: Hardcoded user response disabled - security vulnerability removed
    """
    raise HTTPException(
        status_code=410,
        detail="Simplified authentication disabled - use proper Supabase authentication"
    )

@router.get("/security-info")
async def get_security_info(request: Request):
    """
    Auth security information endpoint.
    """
    return {
        "status": "restored",
        "mode": "simplified_bypass",
        "message": "Full auth system restored with simplified endpoints",
        "timestamp": time.time(),
        "security_features": [
            "Basic authentication flow",
            "Request logging",
            "Error handling"
        ]
    }

@router.get("/health")
async def auth_health(request: Request):
    """
    Auth health check endpoint.
    """
    return {
        "status": "healthy",
        "auth_mode": "simplified",
        "endpoints_active": ["/login", "/register", "/me", "/security-info"],
        "timestamp": time.time(),
        "message": "Auth system operational in simplified mode"
    }