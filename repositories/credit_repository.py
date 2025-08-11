"""
Credit transaction repository for tracking credit usage.
Following CLAUDE.md: Pure database layer, no business logic.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
import logging

from database import SupabaseClient
from models.credit import CreditTransactionCreate, CreditTransactionResponse

logger = logging.getLogger(__name__)


class CreditRepository:
    """Repository for credit transaction database operations."""
    
    def __init__(self, db_client: SupabaseClient):
        self.db = db_client
    
    async def create_transaction(self, transaction_data: Dict[str, Any]) -> CreditTransactionResponse:
        """Create a new credit transaction record."""
        try:
            result = self.db.execute_query(
                "credit_transactions",
                "insert",
                data=transaction_data,
                use_service_key=True,  # For accurate logging
                single=True  # Return single record instead of list
            )
            return CreditTransactionResponse(**result)
        except Exception as e:
            logger.error(f"Failed to create credit transaction: {e}")
            raise
    
    async def get_user_transactions(
        self, 
        user_id: str, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[CreditTransactionResponse]:
        """Get credit transactions for a user."""
        try:
            # This would need custom query implementation
            # For now, using basic select with filters
            result = self.db.execute_query(
                "credit_transactions",
                "select",
                filters={"user_id": str(user_id)},  # Ensure user_id is string for JSON serialization
                use_service_key=True  # Use service key to bypass RLS for transaction lookups
            )
            
            # Sort by created_at desc and apply pagination
            sorted_result = sorted(result, key=lambda x: x["created_at"], reverse=True)
            paginated_result = sorted_result[offset:offset + limit]
            
            return [CreditTransactionResponse(**tx) for tx in paginated_result]
        except Exception as e:
            logger.error(f"Failed to get transactions for user {user_id}: {e}")
            raise
    
    async def get_transaction_by_id(self, transaction_id: str) -> Optional[CreditTransactionResponse]:
        """Get a specific credit transaction by ID."""
        try:
            result = self.db.execute_query(
                "credit_transactions",
                "select",
                filters={"id": transaction_id},
                use_service_key=True  # Use service key to bypass RLS for transaction lookups
            )
            if result:
                return CreditTransactionResponse(**result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to get transaction {transaction_id}: {e}")
            raise
    
    async def get_user_usage_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get user's credit usage statistics for the specified period."""
        try:
            # This would typically use a more complex query or RPC function
            # For now, implementing basic stats calculation
            result = self.db.execute_query(
                "credit_transactions",
                "select",
                filters={"user_id": str(user_id)},  # Ensure user_id is string for JSON serialization
                use_service_key=True  # Use service key to bypass RLS for transaction lookups
            )
            
            # Filter by date range and calculate stats
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            recent_transactions = [
                tx for tx in result 
                if datetime.fromisoformat(tx["created_at"].replace('Z', '+00:00')) >= cutoff_date
            ]
            
            total_spent = sum(
                abs(tx["amount"]) for tx in recent_transactions 
                if tx["transaction_type"] in ["usage", "generation_usage"]
            )
            
            total_purchased = sum(
                tx["amount"] for tx in recent_transactions 
                if tx["transaction_type"] == "purchase"
            )
            
            generation_count = len([
                tx for tx in recent_transactions 
                if tx["transaction_type"] in ["usage", "generation_usage"]
            ])
            
            return {
                "period_days": days,
                "total_spent": total_spent,
                "total_purchased": total_purchased,
                "generation_count": generation_count,
                "transaction_count": len(recent_transactions)
            }
        except Exception as e:
            logger.error(f"Failed to get usage stats for user {user_id}: {e}")
            raise
    
    async def log_generation_usage(
        self, 
        user_id: str, 
        generation_id: str,
        credits_used: int,
        balance_after: int,
        model_name: str
    ) -> CreditTransactionResponse:
        """Log credit usage for a generation."""
        try:
            transaction_data = {
                "user_id": user_id,
                "generation_id": generation_id,
                "transaction_type": "generation_usage",
                "amount": -credits_used,  # Negative for usage
                "balance_after": balance_after,
                "description": f"Generation using {model_name}",
                "metadata": {
                    "model_name": model_name,
                    "generation_id": generation_id
                }
            }
            return await self.create_transaction(transaction_data)
        except Exception as e:
            logger.error(f"Failed to log generation usage: {e}")
            raise
    
    async def log_credit_purchase(
        self, 
        user_id: str,
        credits_purchased: int,
        balance_after: int,
        payment_method: str,
        payment_id: Optional[str] = None
    ) -> CreditTransactionResponse:
        """Log credit purchase."""
        try:
            transaction_data = {
                "user_id": user_id,
                "transaction_type": "purchase",
                "amount": credits_purchased,
                "balance_after": balance_after,
                "description": f"Credit purchase via {payment_method}",
                "metadata": {
                    "payment_method": payment_method,
                    "payment_id": payment_id
                }
            }
            return await self.create_transaction(transaction_data)
        except Exception as e:
            logger.error(f"Failed to log credit purchase: {e}")
            raise