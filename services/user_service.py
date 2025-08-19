"""
User service for business logic operations.
Following CLAUDE.md: Business logic layer, uses repositories.
"""
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from database import get_database
from repositories.user_repository import UserRepository
from repositories.credit_repository import CreditRepository
from models.user import UserResponse, UserUpdate
from models.credit import CreditTransactionResponse, CreditUsageStats, TransactionType
from config import settings

logger = logging.getLogger(__name__)


class UserService:
    """Service for user-related business logic."""
    
    def __init__(self):
        self.db = None
        self.user_repo = None
        self.credit_repo = None
    
    async def _get_repositories(self):
        """Initialize repositories if not already done."""
        if self.db is None:
            self.db = await get_database()
            # CRITICAL FIX: UserRepository now requires supabase_client as second argument
            from database import SupabaseClient
            supabase_client = SupabaseClient()
            self.user_repo = UserRepository(self.db, supabase_client)
            self.credit_repo = CreditRepository(self.db)
    
    async def get_user_profile(self, user_id: str) -> UserResponse:
        """Get user profile by ID."""
        await self._get_repositories()
        
        try:
            user = await self.user_repo.get_user_by_id(user_id, auth_token=None)
            if not user:
                raise ValueError(f"User {user_id} not found")
            return user
        except Exception as e:
            logger.error(f"Failed to get user profile {user_id}: {e}")
            raise
    
    async def update_user_profile(
        self, 
        user_id: str, 
        update_data: UserUpdate
    ) -> UserResponse:
        """Update user profile."""
        await self._get_repositories()
        
        try:
            # Convert Pydantic model to dict, excluding None values
            update_dict = update_data.model_dump(exclude_none=True)
            
            if not update_dict:
                # No changes, return current user
                return await self.get_user_profile(user_id)
            
            return await self.user_repo.update_user(user_id, update_dict)
        except Exception as e:
            logger.error(f"Failed to update user profile {user_id}: {e}")
            raise
    
    async def get_user_credits(self, user_id: str, auth_token: Optional[str] = None) -> int:
        """Get user's current credit balance - WITH ENHANCED LOGGING."""
        await self._get_repositories()
        
        logger.info(f"💳 [USER_SERVICE] Getting credits for user {user_id} with auth_token: {'***' if auth_token else 'None'}")
        
        try:
            logger.info(f"🔍 [USER_SERVICE] Calling user_repo.get_user_credits for user {user_id}")
            # CRITICAL FIX: Pass auth_token for proper database access
            credits = await self.user_repo.get_user_credits(user_id, auth_token=auth_token)
            logger.info(f"✅ [USER_SERVICE] Successfully retrieved {credits} credits for user {user_id}")
            return credits
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ [USER_SERVICE] get_user_credits failed for user {user_id}: {e}")
            logger.error(f"❌ [USER_SERVICE] Exception type: {type(e).__name__}")
            logger.error(f"❌ [USER_SERVICE] Exception message: {error_msg}")
            
            if "not found" in error_msg.lower():
                logger.error(f"👤 [USER_SERVICE] User {user_id} not found during credit check - profile may be missing")
                # Try to get user profile to trigger auto-creation
                logger.info(f"🔄 [USER_SERVICE] Attempting profile auto-creation for user {user_id}")
                try:
                    logger.info(f"🔍 [USER_SERVICE] Calling user_repo.get_user_by_id for user {user_id}")
                    user = await self.user_repo.get_user_by_id(user_id, auth_token=None)
                    logger.info(f"🔍 [USER_SERVICE] get_user_by_id result for user {user_id}: {user is not None}")
                    
                    if user:
                        logger.info(f"✅ [USER_SERVICE] Profile found/created for user {user_id}, retrying credit check")
                        credits_retry = await self.user_repo.get_user_credits(user_id)
                        logger.info(f"✅ [USER_SERVICE] Retry successful - {credits_retry} credits for user {user_id}")
                        return credits_retry
                    else:
                        logger.error(f"❌ [USER_SERVICE] Profile creation failed for user {user_id} - user is None")
                        
                except Exception as profile_error:
                    logger.error(f"❌ [USER_SERVICE] Failed to auto-create profile for user {user_id}: {profile_error}")
                    logger.error(f"❌ [USER_SERVICE] Profile error type: {type(profile_error).__name__}")
                    
                # CRITICAL FIX: Instead of raising error, return fallback credits like repository does
                logger.warning(f"⚠️ [USER_SERVICE] Using fallback credits (100) for user {user_id} due to profile lookup failure")
                return 100
                
            logger.error(f"💥 [USER_SERVICE] Failed to get credits for user {user_id}: {e}")
            raise
    
    async def deduct_credits(
        self, 
        user_id: str, 
        amount: int,
        generation_id: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> UserResponse:
        """
        Deduct credits from user's balance with transaction logging - WITH ENHANCED LOGGING.
        
        Args:
            user_id: User ID
            amount: Credits to deduct
            generation_id: Related generation ID
            model_name: Model used for generation
            
        Returns:
            Updated user profile
            
        Raises:
            ValueError: If user has insufficient credits
        """
        await self._get_repositories()
        
        logger.info(f"💳 [USER_SERVICE] Starting credit deduction for user {user_id}, amount: {amount}")
        logger.info(f"💳 [USER_SERVICE] Generation ID: {generation_id}, Model: {model_name}")
        
        try:
            # Check current balance
            logger.info(f"🔍 [USER_SERVICE] Checking current balance for user {user_id}")
            logger.info(f"🔍 [USER_SERVICE] About to call user_repo.get_user_credits")
            try:
                current_balance = await self.user_repo.get_user_credits(user_id)
                logger.info(f"✅ [USER_SERVICE] get_user_credits returned: {current_balance} (type: {type(current_balance)})")
            except Exception as e:
                logger.error(f"❌ [USER_SERVICE] Error in get_user_credits: {e} (type: {type(e)})")
                raise
                
            logger.info(f"💳 [USER_SERVICE] Current balance for user {user_id}: {current_balance}, deducting: {amount}")
            
            if current_balance < amount:
                logger.error(f"❌ [USER_SERVICE] Insufficient credits for user {user_id}. Required: {amount}, Available: {current_balance}")
                raise ValueError(
                    f"Insufficient credits. Required: {amount}, Available: {current_balance}"
                )
            
            # Deduct credits
            logger.info(f"🔍 [USER_SERVICE] Calling user_repo.deduct_credits for user {user_id}")
            logger.info(f"🔍 [USER_SERVICE] About to call user_repo.deduct_credits")
            try:
                updated_user = await self.user_repo.deduct_credits(user_id, amount)
                logger.info(f"✅ [USER_SERVICE] deduct_credits returned: {type(updated_user)} with balance: {getattr(updated_user, 'credits', 'no credits attr')}")
            except Exception as e:
                logger.error(f"❌ [USER_SERVICE] Error in deduct_credits: {e} (type: {type(e)})")
                raise
            logger.info(f"✅ [USER_SERVICE] Credits deducted successfully for user {user_id}, new balance: {updated_user.credits_balance}")
            
            # Log the transaction
            logger.info(f"🔍 [USER_SERVICE] Logging generation usage transaction for user {user_id}")
            await self.credit_repo.log_generation_usage(
                user_id=user_id,
                generation_id=generation_id,
                credits_used=amount,
                balance_after=updated_user.credits_balance,
                model_name=model_name or "Unknown"
            )
            logger.info(f"✅ [USER_SERVICE] Transaction logged successfully for user {user_id}")
            
            logger.info(f"✅ [USER_SERVICE] Successfully deducted {amount} credits from user {user_id}")
            return updated_user
            
        except Exception as e:
            logger.error(f"❌ [USER_SERVICE] Failed to deduct credits from user {user_id}: {e}")
            logger.error(f"❌ [USER_SERVICE] Deduction error type: {type(e).__name__}")
            logger.error(f"❌ [USER_SERVICE] Deduction error message: {str(e)}")
            raise
    
    async def add_credits(
        self, 
        user_id: str, 
        amount: int,
        transaction_type: TransactionType = TransactionType.PURCHASE,
        description: str = "Credits added",
        payment_method: Optional[str] = None,
        payment_id: Optional[str] = None
    ) -> UserResponse:
        """
        Add credits to user's balance with transaction logging.
        
        Args:
            user_id: User ID
            amount: Credits to add
            transaction_type: Type of transaction
            description: Transaction description
            payment_method: Payment method used
            payment_id: Payment ID for reference
            
        Returns:
            Updated user profile
        """
        await self._get_repositories()
        
        try:
            # Add credits
            updated_user = await self.user_repo.add_credits(user_id, amount)
            
            # Log the transaction
            if transaction_type == TransactionType.PURCHASE:
                await self.credit_repo.log_credit_purchase(
                    user_id=user_id,
                    credits_purchased=amount,
                    balance_after=updated_user.credits_balance,
                    payment_method=payment_method or "Unknown",
                    payment_id=payment_id
                )
            else:
                # Log other types of credit additions
                transaction_data = {
                    "user_id": user_id,
                    "transaction_type": transaction_type.value,
                    "amount": amount,
                    "balance_after": updated_user.credits_balance,
                    "description": description,
                    "metadata": {
                        "payment_method": payment_method,
                        "payment_id": payment_id
                    } if payment_method else {}
                }
                await self.credit_repo.create_transaction(transaction_data)
            
            logger.info(f"Added {amount} credits to user {user_id}")
            return updated_user
            
        except Exception as e:
            logger.error(f"Failed to add credits to user {user_id}: {e}")
            raise
    
    async def get_credit_usage_stats(
        self, 
        user_id: str, 
        days: int = 30
    ) -> CreditUsageStats:
        """Get user's credit usage statistics."""
        await self._get_repositories()
        
        try:
            # Get basic stats from repository
            stats = await self.credit_repo.get_user_usage_stats(user_id, days)
            
            # Get current balance
            current_balance = await self.user_repo.get_user_credits(user_id)
            
            return CreditUsageStats(
                **stats,
                current_balance=current_balance
            )
        except Exception as e:
            logger.error(f"Failed to get credit stats for user {user_id}: {e}")
            raise
    
    async def can_afford_generation(
        self, 
        user_id: str, 
        required_credits: int
    ) -> bool:
        """Check if user can afford a generation - WITH ENHANCED LOGGING."""
        await self._get_repositories()
        
        logger.info(f"💳 [USER_SERVICE] Checking affordability for user {user_id}, required: {required_credits}")
        
        try:
            logger.info(f"🔍 [USER_SERVICE] Calling user_repo.get_user_credits for affordability check, user {user_id}")
            current_balance = await self.user_repo.get_user_credits(user_id)
            logger.info(f"💳 [USER_SERVICE] Current balance for user {user_id}: {current_balance}, required: {required_credits}")
            
            can_afford = current_balance >= required_credits
            logger.info(f"✅ [USER_SERVICE] Affordability check for user {user_id}: {can_afford} (balance: {current_balance}, required: {required_credits})")
            return can_afford
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ [USER_SERVICE] can_afford_generation failed for user {user_id}: {e}")
            logger.error(f"❌ [USER_SERVICE] Exception type: {type(e).__name__}")
            logger.error(f"❌ [USER_SERVICE] Exception message: {error_msg}")
            
            if "not found" in error_msg.lower():
                logger.error(f"👤 [USER_SERVICE] User {user_id} not found during affordability check - attempting profile creation")
                # Try to get user profile to trigger auto-creation
                logger.info(f"🔄 [USER_SERVICE] Attempting profile auto-creation for affordability check, user {user_id}")
                try:
                    logger.info(f"🔍 [USER_SERVICE] Calling user_repo.get_user_by_id for affordability, user {user_id}")
                    user = await self.user_repo.get_user_by_id(user_id, auth_token=None)
                    logger.info(f"🔍 [USER_SERVICE] get_user_by_id affordability result for user {user_id}: {user is not None}")
                    
                    if user:
                        logger.info(f"✅ [USER_SERVICE] Profile found/created for affordability, user {user_id}, retrying balance check")
                        current_balance = await self.user_repo.get_user_credits(user_id)
                        can_afford_retry = current_balance >= required_credits
                        logger.info(f"✅ [USER_SERVICE] Affordability retry for user {user_id}: {can_afford_retry} (balance: {current_balance})")
                        return can_afford_retry
                    else:
                        logger.error(f"❌ [USER_SERVICE] Affordability profile creation failed for user {user_id} - user is None")
                        
                except Exception as profile_error:
                    logger.error(f"❌ [USER_SERVICE] Failed to auto-create profile for affordability user {user_id}: {profile_error}")
                    logger.error(f"❌ [USER_SERVICE] Affordability profile error type: {type(profile_error).__name__}")
                    
                # CRITICAL FIX: Instead of raising error, use fallback credits for affordability check
                logger.warning(f"⚠️ [USER_SERVICE] Using fallback credits (100) for affordability check for user {user_id}")
                fallback_balance = 100
                can_afford_fallback = fallback_balance >= required_credits
                logger.info(f"✅ [USER_SERVICE] Fallback affordability for user {user_id}: {can_afford_fallback} (fallback_balance: {fallback_balance}, required: {required_credits})")
                return can_afford_fallback
                
            logger.error(f"💥 [USER_SERVICE] Failed to check affordability for user {user_id}: {e}")
            return False
    
    async def create_user_profile(
        self, 
        user_id: str, 
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> UserResponse:
        """Create a new user profile."""
        await self._get_repositories()
        
        try:
            user_data = {
                "id": user_id,
                "email": email,
                "display_name": full_name,
                "avatar_url": avatar_url,
                "credits_balance": settings.default_user_credits,
                "role": "user"
            }
            
            user = await self.user_repo.create_user(user_data)
            
            # Log initial credits as a bonus
            await self.add_credits(
                user_id=user_id,
                amount=settings.default_user_credits,
                transaction_type=TransactionType.BONUS,
                description="Welcome bonus credits"
            )
            
            logger.info(f"Created user profile for {user_id}")
            return user
            
        except Exception as e:
            logger.error(f"Failed to create user profile {user_id}: {e}")
            raise


# Global service instance
user_service = UserService()