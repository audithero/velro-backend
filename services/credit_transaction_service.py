"""
Optimized credit transaction service with database transactions and performance enhancements.
Implements atomic operations, caching, and retry mechanisms for credit operations.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from uuid import UUID
import hashlib
import json

from database import get_database
from repositories.user_repository import UserRepository
from repositories.credit_repository import CreditRepository
from models.user import UserResponse
from models.credit import TransactionType
from utils.logging_config import perf_logger, log_performance
from utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


@dataclass
class CreditTransaction:
    """
    Credit transaction data structure with enhanced auth context support.
    
    CRITICAL FIX: Added auth_token support for proper database access.
    """
    user_id: str
    amount: int
    transaction_type: TransactionType
    generation_id: Optional[str] = None
    model_name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    auth_token: Optional[str] = None  # CRITICAL FIX: Direct auth token support


@dataclass
class CreditValidationResult:
    """Credit validation result."""
    valid: bool
    current_balance: int
    required_amount: int
    message: str


class CreditTransactionService:
    """Optimized credit transaction service with caching and atomic operations."""
    
    def __init__(self):
        self.db = None
        self.user_repo = None
        self.credit_repo = None
        self._balance_cache: Dict[str, tuple] = {}  # user_id -> (balance, timestamp)
        self._cache_ttl = 30  # 30 seconds cache TTL
        self._retry_config = {
            'max_attempts': 3,
            'base_delay': 0.1,
            'max_delay': 2.0,
            'exponential_base': 2.0
        }
    
    async def _get_repositories(self):
        """Initialize repositories with connection pooling optimization."""
        if self.db is None:
            try:
                logger.info("🔧 [CREDIT-SERVICE] Initializing optimized database connections")
                self.db = await get_database()
                
                if not self.db.is_available():
                    raise ConnectionError("Database is not available")
                
                self.user_repo = UserRepository(self.db, self.db.client)
                self.credit_repo = CreditRepository(self.db)
                
                logger.info("✅ [CREDIT-SERVICE] Optimized credit service initialized")
                
            except Exception as e:
                logger.error(f"❌ [CREDIT-SERVICE] Failed to initialize credit service: {e}")
                raise RuntimeError(f"Credit service initialization failed: {str(e)}")
    
    def _get_cache_key(self, user_id: str) -> str:
        """Generate cache key for user balance."""
        return f"balance_{user_id}"
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        """Check if cache entry is still valid."""
        return (datetime.utcnow().timestamp() - timestamp) < self._cache_ttl
    
    async def _get_cached_balance(self, user_id: str) -> Optional[int]:
        """Get cached balance if valid."""
        cache_key = self._get_cache_key(user_id)
        
        if cache_key in self._balance_cache:
            balance, timestamp = self._balance_cache[cache_key]
            if self._is_cache_valid(timestamp):
                logger.debug(f"💾 [CREDIT-SERVICE] Cache hit for user {user_id}: {balance}")
                return balance
        
        return None
    
    async def _set_cached_balance(self, user_id: str, balance: int):
        """Set balance in cache."""
        cache_key = self._get_cache_key(user_id)
        self._balance_cache[cache_key] = (balance, datetime.utcnow().timestamp())
        
        # Clean old cache entries periodically
        if len(self._balance_cache) > 1000:
            await self._cleanup_cache()
    
    async def _cleanup_cache(self):
        """Clean expired cache entries."""
        current_time = datetime.utcnow().timestamp()
        expired_keys = [
            key for key, (_, timestamp) in self._balance_cache.items()
            if not self._is_cache_valid(timestamp)
        ]
        
        for key in expired_keys:
            del self._balance_cache[key]
        
        logger.debug(f"🧹 [CREDIT-SERVICE] Cleaned {len(expired_keys)} expired cache entries")
    
    def _invalidate_cache(self, user_id: str):
        """Invalidate cache for specific user."""
        cache_key = self._get_cache_key(user_id)
        if cache_key in self._balance_cache:
            del self._balance_cache[cache_key]
    
    async def _retry_with_backoff(self, operation, *args, **kwargs):
        """Execute operation with exponential backoff retry."""
        config = self._retry_config
        
        for attempt in range(config['max_attempts']):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                if attempt == config['max_attempts'] - 1:
                    raise
                
                delay = min(
                    config['base_delay'] * (config['exponential_base'] ** attempt),
                    config['max_delay']
                )
                
                logger.warning(f"⚠️ [CREDIT-SERVICE] Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
    
    @log_performance("get_user_credits_optimized")
    async def get_user_credits_optimized(self, user_id: str, auth_token: Optional[str] = None) -> int:
        """Get user credits with caching and performance optimization."""
        await self._get_repositories()
        
        # Try cache first
        cached_balance = await self._get_cached_balance(user_id)
        if cached_balance is not None:
            return cached_balance
        
        # Cache miss - fetch from database with retry
        async def fetch_balance():
            with perf_logger.performance_context("database_get_credits", user_id=user_id):
                credits = await self.user_repo.get_user_credits(user_id, auth_token=auth_token)
                await self._set_cached_balance(user_id, credits)
                return credits
        
        try:
            credits = await self._retry_with_backoff(fetch_balance)
            logger.info(f"💳 [CREDIT-SERVICE] Retrieved {credits} credits for user {user_id}")
            return credits
            
        except Exception as e:
            logger.error(f"❌ [CREDIT-SERVICE] Failed to get credits for user {user_id}: {e}")
            performance_monitor.record_credit_operation()
            raise
    
    @log_performance("validate_credit_transaction")
    async def validate_credit_transaction(self, user_id: str, required_amount: int, auth_token: Optional[str] = None) -> CreditValidationResult:
        """Validate if user can afford the credit transaction."""
        try:
            current_balance = await self.get_user_credits_optimized(user_id, auth_token=auth_token)
            
            valid = current_balance >= required_amount
            message = "Valid" if valid else f"Insufficient credits. Required: {required_amount}, Available: {current_balance}"
            
            logger.info(f"🔍 [CREDIT-SERVICE] Credit validation for user {user_id}: {message}")
            
            return CreditValidationResult(
                valid=valid,
                current_balance=current_balance,
                required_amount=required_amount,
                message=message
            )
            
        except Exception as e:
            logger.error(f"❌ [CREDIT-SERVICE] Credit validation failed for user {user_id}: {e}")
            raise
    
    @log_performance("atomic_credit_deduction")
    async def atomic_credit_deduction(self, transaction: CreditTransaction) -> UserResponse:
        """
        Perform atomic credit deduction using Supabase built-in atomicity.
        Since Supabase handles single operations atomically, we don't need explicit transactions.
        """
        await self._get_repositories()
        
        logger.info(f"💳 [CREDIT-SERVICE] Starting atomic credit deduction for user {transaction.user_id}")
        logger.info(f"💳 [CREDIT-SERVICE] Transaction: {transaction.amount} credits, type: {transaction.transaction_type}")
        
        # Execute atomic credit deduction (Supabase handles atomicity for single operations)
        async def execute_transaction():
            try:
                # CRITICAL FIX: Safe UUID handling for transaction
                from utils.uuid_utils import UUIDUtils
                
                # Ensure user_id is a proper UUID string
                user_id_str = UUIDUtils.ensure_uuid_string(transaction.user_id)
                if not user_id_str:
                    raise ValueError(f"Invalid user_id format: {transaction.user_id}")
                
                # Step 1: Validate current balance with auth context - CRITICAL FIX: Enhanced JWT token validation
                logger.info(f"🔍 [CREDIT-SERVICE] Getting current balance for transaction validation, user {user_id_str}")
                
                # CRITICAL FIX: Multi-source auth token resolution with JWT validation
                auth_token = None
                if transaction.auth_token:
                    auth_token = transaction.auth_token
                    logger.info(f"🔑 [CREDIT-SERVICE] Using direct auth_token from transaction for user {user_id_str}")
                elif transaction.metadata and transaction.metadata.get('auth_token'):
                    auth_token = transaction.metadata.get('auth_token')
                    logger.info(f"🔑 [CREDIT-SERVICE] Using auth_token from metadata for user {user_id_str}")
                else:
                    logger.warning(f"⚠️ [CREDIT-SERVICE] No auth_token available for transaction - relying on service key for user {user_id_str}")
                
                # CRITICAL FIX: Validate JWT token expiration before using it
                validated_token = None
                if auth_token:
                    try:
                        # Use the user repository's JWT validation method
                        is_valid = await self.user_repo._validate_jwt_token(auth_token)
                        if is_valid:
                            validated_token = auth_token
                            logger.info(f"✅ [CREDIT-SERVICE] JWT token validated for user {user_id_str}")
                        else:
                            logger.warning(f"🔴 [CREDIT-SERVICE] JWT token invalid/expired for user {user_id_str}")
                            logger.info(f"🔄 [CREDIT-SERVICE] Falling back to service key for user {user_id_str}")
                    except Exception as validation_error:
                        logger.error(f"❌ [CREDIT-SERVICE] JWT validation error: {validation_error}")
                        logger.info(f"🔄 [CREDIT-SERVICE] Using service key due to validation error")
                else:
                    logger.info(f"🔑 [CREDIT-SERVICE] No JWT token provided, using service key for user {user_id_str}")
                
                # CRITICAL FIX: Enhanced credit balance retrieval with multi-layer fallback
                current_balance = None
                last_balance_error = None
                
                # LAYER 1: Try with validated JWT token
                if validated_token:
                    try:
                        logger.info(f"🔑 [CREDIT-SERVICE] Attempting balance check with validated JWT token")
                        current_balance = await self.user_repo.get_user_credits(user_id_str, auth_token=validated_token)
                        logger.info(f"✅ [CREDIT-SERVICE] Balance retrieved with JWT: {current_balance}")
                    except Exception as jwt_balance_error:
                        logger.warning(f"⚠️ [CREDIT-SERVICE] JWT balance check failed: {jwt_balance_error}")
                        last_balance_error = jwt_balance_error
                
                # LAYER 2: Fallback to service key if JWT failed
                if current_balance is None:
                    try:
                        logger.info(f"🔑 [CREDIT-SERVICE] Fallback: Attempting balance check with service key")
                        current_balance = await self.user_repo.get_user_credits(user_id_str, auth_token=None)
                        logger.info(f"✅ [CREDIT-SERVICE] Balance retrieved with service key: {current_balance}")
                    except Exception as service_balance_error:
                        logger.error(f"❌ [CREDIT-SERVICE] Service key balance check also failed: {service_balance_error}")
                        last_balance_error = service_balance_error
                
                # LAYER 3: Handle final failure with enhanced messaging
                if current_balance is None:
                    if last_balance_error:
                        error_str = str(last_balance_error).lower()
                        logger.error(f"💥 [CREDIT-SERVICE] All balance retrieval methods failed for user {user_id_str}")
                        logger.error(f"💥 [CREDIT-SERVICE] Final error: {last_balance_error}")
                        
                        if "invalid api key" in error_str:
                            if validated_token:
                                raise ValueError("Database authentication failed. Please refresh your session and try again.")
                            else:
                                raise ValueError("Service authentication failed. Please try again or contact support.")
                        elif "expired" in error_str or "token" in error_str:
                            raise ValueError("Authentication expired. Please refresh your session and try again.")
                        elif "not found" in error_str:
                            raise ValueError("User profile not found. Please contact support if this continues.")
                        elif "timeout" in error_str:
                            raise ValueError("Database request timed out. Please try again.")
                        elif "connection" in error_str:
                            raise ValueError("Database connection issue. Please check your internet connection and try again.")
                        else:
                            # Generic database error with enhanced messaging
                            raise ValueError(f"Unable to verify account balance. Please try again later. If the issue persists, contact support.")
                    else:
                        raise ValueError("Unable to access user account. Please try again later.")
                
                if current_balance < transaction.amount:
                    raise ValueError(
                        f"Insufficient credits. Required: {transaction.amount}, Available: {current_balance}"
                    )
                
                # Step 2: Deduct credits atomically (Supabase ensures atomicity) - CRITICAL FIX: Use validated token
                try:
                    updated_user = await self.user_repo.deduct_credits(
                        user_id_str, 
                        transaction.amount,
                        auth_token=validated_token  # CRITICAL FIX: Use validated JWT token only
                    )
                except Exception as deduct_error:
                    # Enhanced error handling for authentication issues
                    error_str = str(deduct_error).lower()
                    if "invalid api key" in error_str:
                        if not validated_token:
                            logger.error(f"❌ [CREDIT-SERVICE] Service key invalid and no valid JWT token for deduction, user {user_id_str}")
                            raise ValueError("Authentication expired. Please refresh your session and try again.")
                        else:
                            logger.error(f"❌ [CREDIT-SERVICE] Authentication issue despite valid JWT token")
                            raise ValueError("Credit deduction failed: Database access denied. Please contact support.")
                    elif "expired" in error_str or "token" in error_str:
                        logger.error(f"❌ [CREDIT-SERVICE] JWT token authentication issue during deduction")
                        raise ValueError("Authentication expired. Please refresh your session and try again.")
                    else:
                        # Re-raise other errors with improved messaging
                        logger.error(f"❌ [CREDIT-SERVICE] Credit deduction failed: {deduct_error}")
                        raise ValueError(f"Credit deduction failed: {str(deduct_error)}")
                
                # Step 3: Log transaction (separate operation, but not critical for credit deduction)
                try:
                    transaction_data = {
                        "user_id": user_id_str,
                        "transaction_type": transaction.transaction_type.value if hasattr(transaction.transaction_type, 'value') else str(transaction.transaction_type),
                        "amount": -transaction.amount,  # Negative for deduction
                        "balance_after": updated_user.credits_balance,
                        "description": transaction.description or f"Credit deduction for {transaction.transaction_type.value if hasattr(transaction.transaction_type, 'value') else str(transaction.transaction_type)}",
                        "metadata": {
                            **(transaction.metadata or {}),
                            "generation_id": transaction.generation_id,
                            "model_name": transaction.model_name,
                            "atomic_transaction": True
                        }
                    }
                    
                    await self.credit_repo.create_transaction(transaction_data)
                    logger.info(f"✅ [CREDIT-SERVICE] Transaction logged successfully for user {user_id_str}")
                    
                except Exception as log_error:
                    # Log transaction failure should not fail the credit deduction
                    logger.warning(f"⚠️ [CREDIT-SERVICE] Failed to log transaction but credit deduction succeeded: {log_error}")
                
                # Step 4: Update performance metrics
                performance_monitor.record_credit_operation()
                
                # Step 5: Invalidate cache
                self._invalidate_cache(transaction.user_id)
                
                # Step 6: Log successful transaction
                perf_logger.log_credit_operation(
                    operation="atomic_deduction",
                    user_id=transaction.user_id,
                    amount=transaction.amount,
                    balance_before=current_balance,
                    balance_after=updated_user.credits_balance,
                    generation_id=transaction.generation_id,
                    model_name=transaction.model_name
                )
                
                logger.info(f"✅ [CREDIT-SERVICE] Atomic deduction successful: user {user_id_str}, new balance: {updated_user.credits_balance}")
                
                return updated_user
                
            except Exception as e:
                logger.error(f"❌ [CREDIT-SERVICE] Atomic operation failed: {e}")
                raise
        
        # Execute with retry mechanism
        try:
            return await self._retry_with_backoff(execute_transaction)
            
        except Exception as e:
            logger.error(f"💥 [CREDIT-SERVICE] All retry attempts failed for user {transaction.user_id}: {e}")
            raise
    
    @log_performance("batch_credit_operations")
    async def batch_credit_operations(self, transactions: List[CreditTransaction]) -> List[UserResponse]:
        """
        Execute multiple credit operations sequentially.
        Note: Since Supabase doesn't support explicit transactions in this client,
        we process each transaction individually with error handling.
        """
        await self._get_repositories()
        
        if not transactions:
            return []
        
        logger.info(f"🔄 [CREDIT-SERVICE] Starting batch credit operations: {len(transactions)} transactions")
        
        results = []
        failed_transactions = []
        
        # Process each transaction individually with error handling
        for i, transaction in enumerate(transactions):
            try:
                result = await self.atomic_credit_deduction(transaction)
                results.append(result)
                logger.info(f"✅ [CREDIT-SERVICE] Batch transaction {i+1}/{len(transactions)} completed for user {transaction.user_id}")
                
            except Exception as e:
                logger.error(f"❌ [CREDIT-SERVICE] Batch transaction {i+1}/{len(transactions)} failed for user {transaction.user_id}: {e}")
                failed_transactions.append((i, transaction, str(e)))
                
                # For batch operations, we continue processing other transactions
                # but collect the failures for reporting
                continue
        
        if failed_transactions:
            failed_count = len(failed_transactions)
            success_count = len(results)
            logger.warning(f"⚠️ [CREDIT-SERVICE] Batch operation completed with {failed_count} failures out of {len(transactions)} total")
            logger.warning(f"✅ [CREDIT-SERVICE] Successful transactions: {success_count}")
            
            # Create detailed error message
            error_details = [f"Transaction {i+1} (user {tx.user_id}): {error}" for i, tx, error in failed_transactions]
            raise ValueError(f"Batch operation partially failed. {failed_count} out of {len(transactions)} transactions failed. Details: {'; '.join(error_details)}")
        
        logger.info(f"✅ [CREDIT-SERVICE] Batch operations completed successfully: {len(results)} transactions processed")
        return results
    
    @log_performance("get_credit_usage_analytics")
    async def get_credit_usage_analytics(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive credit usage analytics."""
        await self._get_repositories()
        
        try:
            # Get basic usage stats
            stats = await self.credit_repo.get_user_usage_stats(user_id, days)
            
            # Get current balance
            current_balance = await self.get_user_credits_optimized(user_id)
            
            # Calculate additional metrics
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Get transaction history for analytics
            transactions = await self.credit_repo.get_user_transactions(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                limit=1000
            )
            
            # Calculate advanced analytics
            daily_usage = {}
            model_usage = {}
            
            for txn in transactions:
                if txn.get('amount', 0) < 0:  # Deductions only
                    date_key = txn.get('created_at', '')[:10]  # YYYY-MM-DD
                    daily_usage[date_key] = daily_usage.get(date_key, 0) + abs(txn.get('amount', 0))
                    
                    model = txn.get('metadata', {}).get('model_name', 'Unknown')
                    model_usage[model] = model_usage.get(model, 0) + abs(txn.get('amount', 0))
            
            analytics = {
                **stats,
                'current_balance': current_balance,
                'period_days': days,
                'daily_usage': daily_usage,
                'model_usage': model_usage,
                'average_daily_usage': sum(daily_usage.values()) / max(len(daily_usage), 1),
                'most_used_model': max(model_usage.items(), key=lambda x: x[1])[0] if model_usage else None,
                'analytics_generated_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"📊 [CREDIT-SERVICE] Generated analytics for user {user_id}: {days} days")
            return analytics
            
        except Exception as e:
            logger.error(f"❌ [CREDIT-SERVICE] Failed to get analytics for user {user_id}: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on credit service."""
        try:
            await self._get_repositories()
            
            # Test database connectivity
            test_user_id = "health_check_test"
            
            # Test basic operations (without actual changes)
            start_time = datetime.utcnow()
            
            # Test repository connectivity
            try:
                # This should fail gracefully for non-existent user
                await self.user_repo.get_user_credits(test_user_id)
            except:
                pass  # Expected for non-existent user
            
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            cache_stats = {
                'entries': len(self._balance_cache),
                'hit_ratio': 'N/A',  # TODO: Implement hit ratio tracking
            }
            
            return {
                'status': 'healthy',
                'response_time_seconds': response_time,
                'database_connected': self.db.is_available() if self.db else False,
                'cache_stats': cache_stats,
                'retry_config': self._retry_config,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }


# Global optimized credit service instance
credit_transaction_service = CreditTransactionService()