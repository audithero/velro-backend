"""
User Repository with Service Account JWT
=========================================
Clean implementation using service account JWT that respects RLS policies.
No fallback logic - secure and maintainable.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID
import asyncio
from functools import lru_cache

from supabase import Client, create_client
from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

class ServiceAccountClient:
    """
    Manages Supabase client with service account JWT authentication.
    """
    
    def __init__(self, supabase_url: str, service_jwt: str):
        """
        Initialize service account client.
        
        Args:
            supabase_url: Supabase project URL
            service_jwt: Long-lived JWT for service account
        """
        self.supabase_url = supabase_url
        self.service_jwt = service_jwt
        self._client: Optional[Client] = None
        self._initialized = False
        
    @property
    def client(self) -> Client:
        """Get or create Supabase client with service JWT."""
        if not self._client or not self._initialized:
            self._client = create_client(
                self.supabase_url,
                self.service_jwt,  # Use service JWT instead of anon key
                options={
                    "auto_refresh_token": False,  # No refresh needed for long-lived token
                    "persist_session": False,
                    "flow_type": "implicit"
                }
            )
            self._initialized = True
            logger.info("Service account client initialized with JWT")
        return self._client
    
    async def verify_connection(self) -> bool:
        """Verify service account can connect and has proper permissions."""
        try:
            # Test query to verify connection and permissions
            response = self.client.table("users").select("id").limit(1).execute()
            logger.info("Service account connection verified")
            return True
        except Exception as e:
            logger.error(f"Service account connection failed: {e}")
            return False

class UserRepositoryServiceAccount:
    """
    User Repository using service account JWT.
    Clean implementation without fallback logic.
    """
    
    def __init__(self, supabase_url: str, service_jwt: str):
        """
        Initialize repository with service account credentials.
        
        Args:
            supabase_url: Supabase project URL
            service_jwt: Service account JWT from environment
        """
        self.service_client = ServiceAccountClient(supabase_url, service_jwt)
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutes cache
        
    @property
    def client(self) -> Client:
        """Get Supabase client."""
        return self.service_client.client
    
    async def initialize(self) -> bool:
        """Initialize and verify service account connection."""
        return await self.service_client.verify_connection()
    
    # ==================== User Management ====================
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by ID using service account.
        
        Args:
            user_id: User UUID
            
        Returns:
            User dict or None if not found
        """
        try:
            # Check cache first
            cache_key = f"user:{user_id}"
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if (datetime.now(timezone.utc) - cached['timestamp']).seconds < self._cache_ttl:
                    logger.debug(f"Cache hit for user {user_id}")
                    return cached['data']
            
            # Query database with service account
            response = self.client.table("users").select("*").eq("id", user_id).single().execute()
            
            if response.data:
                # Update cache
                self._cache[cache_key] = {
                    'data': response.data,
                    'timestamp': datetime.now(timezone.utc)
                }
                return response.data
            
            logger.warning(f"User {user_id} not found")
            return None
            
        except APIError as e:
            if "No rows found" in str(e):
                logger.info(f"User {user_id} does not exist")
                return None
            logger.error(f"Database error getting user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting user {user_id}: {e}")
            raise
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email using service account.
        
        Args:
            email: User email address
            
        Returns:
            User dict or None if not found
        """
        try:
            response = self.client.table("users").select("*").eq("email", email).single().execute()
            
            if response.data:
                return response.data
            
            return None
            
        except APIError as e:
            if "No rows found" in str(e):
                logger.info(f"User with email {email} does not exist")
                return None
            logger.error(f"Database error getting user by email: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting user by email: {e}")
            raise
    
    async def create_user(self, user_id: str, email: str, full_name: str) -> Dict[str, Any]:
        """
        Create new user profile using service account.
        
        Args:
            user_id: User UUID from auth
            email: User email
            full_name: User's full name
            
        Returns:
            Created user dict
        """
        try:
            user_data = {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "display_name": full_name,  # Set display_name same as full_name initially
                "credits_balance": 10,  # Default starting credits
                "role": "user",  # Default role
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = self.client.table("users").insert(user_data).execute()
            
            if response.data:
                logger.info(f"Created user profile for {user_id}")
                return response.data[0]
            
            raise Exception("Failed to create user profile")
            
        except Exception as e:
            logger.error(f"Error creating user profile: {e}")
            raise
    
    # ==================== Credit Management ====================
    
    async def get_user_credits(self, user_id: str) -> Dict[str, int]:
        """
        Get user's credit balance using service account.
        
        Args:
            user_id: User UUID
            
        Returns:
            Dict with credit balance info
        """
        try:
            user = await self.get_user_by_id(user_id)
            
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # Calculate total purchased and used from transactions
            transactions = self.client.table("credit_transactions")\
                .select("amount, transaction_type")\
                .eq("user_id", user_id)\
                .execute()
            
            total_purchased = 0
            total_used = 0
            
            if transactions.data:
                for tx in transactions.data:
                    if tx['amount'] > 0:
                        total_purchased += tx['amount']
                    else:
                        total_used += abs(tx['amount'])
            
            return {
                "credits_balance": user.get('credits_balance', 0),
                "total_credits_purchased": total_purchased,
                "total_credits_used": total_used
            }
            
        except Exception as e:
            logger.error(f"Error getting credits for user {user_id}: {e}")
            raise
    
    async def update_credits_balance(
        self,
        user_id: str,
        amount: int,
        transaction_type: str,
        description: str
    ) -> Dict[str, int]:
        """
        Update user's credit balance using service account.
        
        Args:
            user_id: User UUID
            amount: Credit amount (positive for add, negative for deduct)
            transaction_type: Type of transaction
            description: Transaction description
            
        Returns:
            Updated credit balance dict
        """
        try:
            # Get current balance
            user = await self.get_user_by_id(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            current_balance = user.get('credits_balance', 0)
            
            # Calculate new balance
            new_balance = current_balance + amount
            if new_balance < 0:
                raise ValueError("Insufficient credits")
            
            # Update user record
            update_response = self.client.table("users")\
                .update({
                    "credits_balance": new_balance,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })\
                .eq("id", user_id)\
                .execute()
            
            if not update_response.data:
                raise Exception("Failed to update credits")
            
            # Record transaction
            await self._record_transaction(
                user_id=user_id,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                balance_after=new_balance
            )
            
            # Clear cache
            cache_key = f"user:{user_id}"
            if cache_key in self._cache:
                del self._cache[cache_key]
            
            logger.info(f"Updated credits for user {user_id}: {amount} ({transaction_type})")
            
            # Get updated totals
            credits_info = await self.get_user_credits(user_id)
            return credits_info
            
        except Exception as e:
            logger.error(f"Error updating credits for user {user_id}: {e}")
            raise
    
    async def deduct_credits(self, user_id: str, amount: int, description: str) -> bool:
        """
        Deduct credits from user's balance.
        
        Args:
            user_id: User UUID
            amount: Amount to deduct (positive number)
            description: Reason for deduction
            
        Returns:
            True if successful, False if insufficient credits
        """
        try:
            await self.update_credits_balance(
                user_id=user_id,
                amount=-abs(amount),  # Ensure negative
                transaction_type="usage",
                description=description
            )
            return True
        except ValueError as e:
            if "Insufficient credits" in str(e):
                logger.warning(f"Insufficient credits for user {user_id}")
                return False
            raise
    
    async def _record_transaction(
        self,
        user_id: str,
        amount: int,
        transaction_type: str,
        description: str,
        balance_after: int
    ) -> None:
        """
        Record a credit transaction.
        
        Args:
            user_id: User UUID
            amount: Transaction amount
            transaction_type: Type of transaction
            description: Transaction description
            balance_after: Balance after transaction
        """
        try:
            transaction_data = {
                "user_id": user_id,
                "amount": amount,
                "transaction_type": transaction_type,
                "description": description,
                "balance_after": balance_after,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            self.client.table("credit_transactions").insert(transaction_data).execute()
            logger.debug(f"Recorded transaction for user {user_id}: {amount} credits")
            
        except Exception as e:
            logger.error(f"Error recording transaction: {e}")
            # Don't raise - transaction recording is not critical
    
    # ==================== Batch Operations ====================
    
    async def get_users_batch(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get multiple users in a single query.
        
        Args:
            user_ids: List of user UUIDs
            
        Returns:
            List of user dicts
        """
        try:
            response = self.client.table("users")\
                .select("*")\
                .in_("id", user_ids)\
                .execute()
            
            if response.data:
                return response.data
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting users batch: {e}")
            raise
    
    async def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all users with pagination.
        
        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip
            
        Returns:
            List of user dicts
        """
        try:
            response = self.client.table("users")\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .offset(offset)\
                .execute()
            
            if response.data:
                return response.data
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            raise
    
    # ==================== Health Check ====================
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on repository and service account.
        
        Returns:
            Health status dictionary
        """
        try:
            # Test database connection
            start_time = datetime.now(timezone.utc)
            connected = await self.service_client.verify_connection()
            latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Get service account info
            service_response = self.client.table("users")\
                .select("id, email, credits_balance")\
                .eq("id", "a0000000-0000-0000-0000-000000000001")\
                .single()\
                .execute()
            
            service_account = service_response.data if service_response.data else None
            
            return {
                "status": "healthy" if connected else "unhealthy",
                "connected": connected,
                "latency_ms": round(latency_ms, 2),
                "service_account": {
                    "exists": service_account is not None,
                    "id": service_account.get("id") if service_account else None,
                    "email": service_account.get("email") if service_account else None,
                    "credits": service_account.get("credits_balance") if service_account else None
                },
                "cache_size": len(self._cache),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }