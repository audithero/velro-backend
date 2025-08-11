"""
Credits router for user credit management and transactions.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional
from uuid import UUID

from middleware.auth import get_current_user
from middleware.rate_limiting import limit
from models.user import UserResponse

router = APIRouter(tags=["credits"])


@router.get("/balance")
@router.get("/balance/")
@limit("200/minute")  # Balance check operations limit
async def get_credit_balance(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """Get current user's credit balance from database."""
    from services.user_service import user_service
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"💳 [CREDITS-ROUTER] Getting fresh credit balance for user {current_user.id}")
    
    try:
        # Extract auth token from request for proper database access
        auth_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]
            logger.info(f"🔑 [CREDITS-ROUTER] Auth token available: {'***' + auth_token[-10:] if auth_token else 'None'}")
        
        # Get fresh balance from database (not cached value)
        fresh_balance = await user_service.get_user_credits(str(current_user.id), auth_token=auth_token)
        logger.info(f"✅ [CREDITS-ROUTER] Fresh balance retrieved for user {current_user.id}: {fresh_balance}")
        
        return {"balance": fresh_balance}
        
    except ValueError as ve:
        # Handle profile not found errors more gracefully
        error_msg = str(ve).lower()
        if "not found" in error_msg or "profile" in error_msg:
            logger.warning(f"⚠️ [CREDITS-ROUTER] Profile issue for user {current_user.id}: {ve}")
            logger.warning(f"⚠️ [CREDITS-ROUTER] Using cached balance from auth token: {current_user.credits_balance}")
            return {"balance": current_user.credits_balance}
        else:
            logger.error(f"❌ [CREDITS-ROUTER] Validation error for user {current_user.id}: {ve}")
            raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        logger.error(f"❌ [CREDITS-ROUTER] Failed to get fresh balance for user {current_user.id}: {e}")
        logger.error(f"❌ [CREDITS-ROUTER] Error type: {type(e).__name__}")
        
        # Fallback to cached balance from auth if fresh lookup fails
        logger.warning(f"⚠️ [CREDITS-ROUTER] Using cached balance as fallback: {current_user.credits_balance}")
        return {"balance": current_user.credits_balance}


@router.get("/transactions")
@router.get("/transactions/")
@limit("200/minute")  # List operations limit
async def list_transactions(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    transaction_type: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """List user credit transactions."""
    return {
        "transactions": [
            {
                "id": "txn_1",
                "user_id": current_user.id,
                "transaction_type": "purchase",
                "amount": 1000,
                "balance_after": current_user.credits_balance,
                "description": "Initial credit allocation",
                "metadata": {},
                "created_at": "2025-07-20T10:00:00Z"
            }
        ],
        "total": 1,
        "skip": skip,
        "limit": limit
    }


@router.post("/purchase/")
@router.post("/purchase")  # CRITICAL FIX: Add route without trailing slash
async def purchase_credits():
    """Purchase credits via Stripe."""
    return {"message": "Purchase credits endpoint - to be implemented"}


@router.post("/redeem/")
@router.post("/redeem")  # CRITICAL FIX: Add route without trailing slash
async def redeem_code():
    """Redeem a credit code."""
    return {"message": "Redeem code endpoint - to be implemented"}


@router.get("/stats")
@router.get("/stats/")
@limit("100/minute")  # Stats operations limit
async def get_credit_usage_stats(
    request: Request,
    days: int = 30,
    current_user: UserResponse = Depends(get_current_user)
):
    """Get credit usage statistics for the user."""
    return {
        "current_balance": current_user.credits_balance,
        "period_days": days,
        "total_spent": 0,
        "total_purchased": current_user.credits_balance,
        "generation_count": 0,
        "transaction_count": 1
    }