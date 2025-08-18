"""
SECURITY: This file has been disabled due to critical security vulnerabilities.
It contained hardcoded authentication bypasses that allowed unauthorized access.
All emergency authentication methods have been removed for security.
"""
import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["security-disabled"])

@router.get("/emergency-disabled")
async def emergency_disabled():
    """All emergency authentication routes have been disabled for security."""
    raise HTTPException(
        status_code=410,
        detail="Emergency authentication disabled - use proper Supabase authentication"
    )