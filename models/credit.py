"""
Credit model schemas for credit transactions and balance management.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class TransactionType(str, Enum):
    """Transaction type enum."""
    PURCHASE = "purchase"
    USAGE = "usage"
    GENERATION_USAGE = "generation_usage"
    REFUND = "refund"
    BONUS = "bonus"
    REFERRAL = "referral"


class TransactionStatus(str, Enum):
    """Transaction status enum."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CreditTransactionBase(BaseModel):
    """Base credit transaction model."""
    amount: int = Field(..., description="Credit amount (positive for credits added, negative for usage)")
    transaction_type: TransactionType
    description: str = Field(..., max_length=200)
    metadata: Dict[str, Any] = {}


class CreditTransactionCreate(CreditTransactionBase):
    """Credit transaction creation model."""
    related_generation_id: Optional[UUID] = None
    stripe_payment_intent_id: Optional[str] = None


class CreditTransactionResponse(CreditTransactionBase):
    """Credit transaction response model."""
    id: UUID
    user_id: UUID
    status: Optional[TransactionStatus] = TransactionStatus.COMPLETED  # Optional - DB doesn't have status column
    balance_after: int
    generation_id: Optional[UUID] = None  # Match DB column name
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class CreditBalanceResponse(BaseModel):
    """Credit balance response model."""
    current_balance: int
    total_earned: int
    total_spent: int
    pending_transactions: int


class CreditPurchaseRequest(BaseModel):
    """Credit purchase request model."""
    credit_amount: int = Field(..., gt=0, description="Number of credits to purchase")
    payment_method_id: str = Field(..., description="Stripe payment method ID")


class CreditPurchaseResponse(BaseModel):
    """Credit purchase response model."""
    transaction_id: UUID
    amount_purchased: int
    total_cost_usd: float
    stripe_payment_intent_id: str
    status: TransactionStatus


class CreditUsageStats(BaseModel):
    """Credit usage statistics model."""
    current_balance: int
    period_days: int
    total_spent: int
    total_purchased: int
    generation_count: int
    transaction_count: int


class TransactionListResponse(BaseModel):
    """Paginated transaction list response."""
    items: List[CreditTransactionResponse]
    total: int
    page: int
    per_page: int
    pages: int