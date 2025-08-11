"""
Advanced Token Management System
Production-ready token refresh automation with secure storage and session management.
Enterprise-grade security with comprehensive monitoring and audit logging.
"""
import os
import logging
import hashlib
import json
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from uuid import UUID
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
from contextlib import asynccontextmanager
from fastapi import HTTPException, status

# CRITICAL FIX: Safe import of redis async
try:
    import redis.asyncio as aioredis
    AIOREDIS_AVAILABLE = True
except ImportError:
    AIOREDIS_AVAILABLE = False
    aioredis = None

from config import settings
from models.user import Token, UserResponse
from utils.cache_manager import get_cache_manager, CacheLevel
from database import SupabaseClient

logger = logging.getLogger(__name__)

@dataclass
class TokenMetadata:
    """Token metadata for tracking and auditing."""
    user_id: str
    created_at: datetime
    expires_at: datetime
    refresh_count: int = 0
    last_refreshed: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_fingerprint: Optional[str] = None
    is_revoked: bool = False
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None


class SecureTokenStorage:
    """Encrypted token storage with Redis backend."""
    
    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        self.redis_client = None
        self.cache_manager = get_cache_manager()
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for token storage."""
        key_path = os.path.join(os.getcwd(), '.token_encryption_key')
        
        if os.path.exists(key_path) and not settings.debug:
            with open(key_path, 'rb') as f:
                return f.read()
        
        # Generate new key
        key = Fernet.generate_key()
        
        # Save key securely in production
        if settings.is_production():
            # In production, use environment variable or secure key management
            env_key = os.getenv('TOKEN_ENCRYPTION_KEY')
            if env_key:
                return env_key.encode()
            else:
                logger.warning("⚠️ [TOKEN-MANAGER] No TOKEN_ENCRYPTION_KEY found in production")
        
        # Save to file for development
        with open(key_path, 'wb') as f:
            f.write(key)
        
        logger.info(f"🔐 [TOKEN-MANAGER] Generated new encryption key")
        return key
    
    async def _get_redis_client(self):
        """Get Redis client for token storage."""
        if not AIOREDIS_AVAILABLE:
            logger.warning("⚠️ [TOKEN-MANAGER] aioredis not available, using fallback storage")
            return None
            
        if self.redis_client is None:
            try:
                redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
                self.redis_client = aioredis.from_url(redis_url, decode_responses=True)
                await self.redis_client.ping()
                logger.info("✅ [TOKEN-MANAGER] Redis connected for token storage")
            except Exception as e:
                logger.warning(f"⚠️ [TOKEN-MANAGER] Redis unavailable, using memory cache: {e}")
                self.redis_client = None
        
        return self.redis_client
    
    async def store_token(self, token_id: str, token_data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Store encrypted token data."""
        try:
            # Encrypt token data
            encrypted_data = self.cipher_suite.encrypt(json.dumps(token_data).encode())
            
            # Try Redis first
            redis_client = await self._get_redis_client()
            if redis_client:
                await redis_client.setex(f"token:{token_id}", ttl, encrypted_data.decode())
                logger.debug(f"💾 [TOKEN-MANAGER] Token stored in Redis: {token_id}")
                return True
            
            # Fallback to cache manager
            await self.cache_manager.set(
                f"token:{token_id}",
                encrypted_data.decode(),
                CacheLevel.L2_PERSISTENT,
                ttl=ttl
            )
            logger.debug(f"💾 [TOKEN-MANAGER] Token stored in cache: {token_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Failed to store token {token_id}: {e}")
            return False
    
    async def retrieve_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt token data."""
        try:
            encrypted_data = None
            
            # Try Redis first
            redis_client = await self._get_redis_client()
            if redis_client:
                encrypted_data = await redis_client.get(f"token:{token_id}")
                if encrypted_data:
                    logger.debug(f"🔍 [TOKEN-MANAGER] Token retrieved from Redis: {token_id}")
            
            # Fallback to cache manager
            if not encrypted_data:
                encrypted_data = await self.cache_manager.get(f"token:{token_id}", CacheLevel.L2_PERSISTENT)
                if encrypted_data:
                    logger.debug(f"🔍 [TOKEN-MANAGER] Token retrieved from cache: {token_id}")
            
            if not encrypted_data:
                return None
            
            # Decrypt token data
            decrypted_data = self.cipher_suite.decrypt(encrypted_data.encode())
            return json.loads(decrypted_data.decode())
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Failed to retrieve token {token_id}: {e}")
            return None
    
    async def delete_token(self, token_id: str) -> bool:
        """Delete token from storage."""
        try:
            # Try Redis first
            redis_client = await self._get_redis_client()
            if redis_client:
                await redis_client.delete(f"token:{token_id}")
                logger.debug(f"🗑️ [TOKEN-MANAGER] Token deleted from Redis: {token_id}")
            
            # Also delete from cache
            await self.cache_manager.delete(f"token:{token_id}")
            logger.debug(f"🗑️ [TOKEN-MANAGER] Token deleted from cache: {token_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Failed to delete token {token_id}: {e}")
            return False


class TokenRefreshManager:
    """Automated token refresh management with proactive renewal."""
    
    def __init__(self):
        self.storage = SecureTokenStorage()
        self.auth_service = None
        self.refresh_tasks: Dict[str, asyncio.Task] = {}
        self.cache_manager = get_cache_manager()
    
    def get_auth_service(self):
        """Get or create auth service instance."""
        if self.auth_service is None:
            # Import here to avoid circular imports
            from services.auth_service import AuthService
            db_client = SupabaseClient()
            self.auth_service = AuthService(db_client)
        return self.auth_service
    
    async def register_token(
        self,
        token: Token,
        user: UserResponse,
        refresh_token: Optional[str] = None,
        metadata: Optional[TokenMetadata] = None
    ) -> str:
        """Register token for automatic refresh management."""
        try:
            token_id = self._generate_token_id(token.access_token)
            
            # Create metadata
            if metadata is None:
                metadata = TokenMetadata(
                    user_id=str(user.id),
                    created_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=token.expires_in)
                )
            
            # Store token data
            token_data = {
                'access_token': token.access_token,
                'refresh_token': refresh_token,
                'user_id': str(user.id),
                'user_data': user.dict() if hasattr(user, 'dict') else user.__dict__,  # Fix: Use Pydantic dict() method
                'metadata': asdict(metadata),
                'token_type': token.token_type,
                'expires_in': token.expires_in
            }
            
            await self.storage.store_token(token_id, token_data, ttl=token.expires_in)
            
            # Schedule automatic refresh
            if refresh_token and token.expires_in > 300:  # Only if expires in more than 5 minutes
                await self._schedule_refresh(token_id, token.expires_in - 300)  # Refresh 5 minutes before expiry
            
            logger.info(f"✅ [TOKEN-MANAGER] Token registered for user {user.id}: {token_id}")
            return token_id
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Failed to register token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token registration failed"
            )
    
    async def refresh_token_proactive(self, token_id: str) -> Optional[Token]:
        """Proactively refresh token before expiration."""
        try:
            token_data = await self.storage.retrieve_token(token_id)
            if not token_data:
                logger.warning(f"⚠️ [TOKEN-MANAGER] Token not found for refresh: {token_id}")
                return None
            
            refresh_token = token_data.get('refresh_token')
            if not refresh_token:
                logger.warning(f"⚠️ [TOKEN-MANAGER] No refresh token available: {token_id}")
                return None
            
            # Perform token refresh
            auth_service = self.get_auth_service()
            new_token = await auth_service.refresh_access_token(refresh_token)
            
            if new_token:
                # Update stored token data
                user_data = token_data.get('user_data', {})
                user = UserResponse(**user_data)
                
                # Update metadata
                metadata_dict = token_data.get('metadata', {})
                metadata = TokenMetadata(**metadata_dict)
                metadata.refresh_count += 1
                metadata.last_refreshed = datetime.now(timezone.utc)
                
                # Re-register with new token
                new_token_id = await self.register_token(new_token, user, refresh_token, metadata)
                
                # Clean up old token
                await self.storage.delete_token(token_id)
                
                logger.info(f"✅ [TOKEN-MANAGER] Token refreshed proactively: {token_id} -> {new_token_id}")
                return new_token
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Proactive token refresh failed for {token_id}: {e}")
        
        return None
    
    async def _schedule_refresh(self, token_id: str, delay_seconds: int):
        """Schedule automatic token refresh."""
        async def refresh_task():
            try:
                await asyncio.sleep(delay_seconds)
                await self.refresh_token_proactive(token_id)
            except asyncio.CancelledError:
                logger.info(f"🔄 [TOKEN-MANAGER] Refresh task cancelled for {token_id}")
            except Exception as e:
                logger.error(f"❌ [TOKEN-MANAGER] Scheduled refresh failed for {token_id}: {e}")
            finally:
                # Clean up task reference
                self.refresh_tasks.pop(token_id, None)
        
        # Cancel existing task if any
        if token_id in self.refresh_tasks:
            self.refresh_tasks[token_id].cancel()
        
        # Schedule new task
        task = asyncio.create_task(refresh_task())
        self.refresh_tasks[token_id] = task
        
        logger.debug(f"⏰ [TOKEN-MANAGER] Scheduled refresh for {token_id} in {delay_seconds} seconds")
    
    def _generate_token_id(self, access_token: str) -> str:
        """Generate unique token ID from access token."""
        return hashlib.sha256(access_token.encode()).hexdigest()[:16]
    
    async def get_token_status(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get token status and metadata."""
        try:
            token_data = await self.storage.retrieve_token(token_id)
            if not token_data:
                return None
            
            metadata = TokenMetadata(**token_data.get('metadata', {}))
            
            return {
                'token_id': token_id,
                'user_id': token_data.get('user_id'),
                'created_at': metadata.created_at.isoformat(),
                'expires_at': metadata.expires_at.isoformat(),
                'refresh_count': metadata.refresh_count,
                'last_refreshed': metadata.last_refreshed.isoformat() if metadata.last_refreshed else None,
                'is_revoked': metadata.is_revoked,
                'has_scheduled_refresh': token_id in self.refresh_tasks,
                'time_to_expiry': (metadata.expires_at - datetime.now(timezone.utc)).total_seconds()
            }
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Failed to get token status {token_id}: {e}")
            return None
    
    async def revoke_token(self, token_id: str, reason: str = "user_requested") -> bool:
        """Revoke token and cancel scheduled refreshes."""
        try:
            # Cancel scheduled refresh
            if token_id in self.refresh_tasks:
                self.refresh_tasks[token_id].cancel()
                del self.refresh_tasks[token_id]
            
            # Update token metadata
            token_data = await self.storage.retrieve_token(token_id)
            if token_data:
                metadata = TokenMetadata(**token_data.get('metadata', {}))
                metadata.is_revoked = True
                metadata.revoked_at = datetime.now(timezone.utc)
                metadata.revocation_reason = reason
                
                token_data['metadata'] = asdict(metadata)
                
                # Store updated data with short TTL
                await self.storage.store_token(token_id, token_data, ttl=3600)
            
            logger.info(f"🚫 [TOKEN-MANAGER] Token revoked: {token_id} (reason: {reason})")
            return True
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Failed to revoke token {token_id}: {e}")
            return False
    
    async def cleanup_expired_tokens(self):
        """Clean up expired tokens and cancelled tasks."""
        try:
            # Clean up cancelled tasks
            cancelled_tasks = [token_id for token_id, task in self.refresh_tasks.items() if task.cancelled()]
            for token_id in cancelled_tasks:
                del self.refresh_tasks[token_id]
            
            if cancelled_tasks:
                logger.info(f"🧹 [TOKEN-MANAGER] Cleaned up {len(cancelled_tasks)} cancelled refresh tasks")
            
        except Exception as e:
            logger.error(f"❌ [TOKEN-MANAGER] Cleanup failed: {e}")


# Global token manager instance
_token_manager: Optional[TokenRefreshManager] = None

def get_token_manager() -> TokenRefreshManager:
    """Get global token manager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenRefreshManager()
    return _token_manager


class SessionTimeoutManager:
    """Manage session timeouts with graceful user experience."""
    
    def __init__(self):
        self.cache_manager = get_cache_manager()
        self.default_timeout = settings.jwt_expiration_seconds or 3600  # 1 hour default
        self.warning_threshold = 300  # 5 minutes warning
    
    async def track_user_activity(self, user_id: str, activity_type: str = "api_request"):
        """Track user activity to extend session."""
        try:
            activity_key = f"user_activity:{user_id}"
            activity_data = {
                'last_activity': datetime.now(timezone.utc).isoformat(),
                'activity_type': activity_type,
                'session_extended_count': 0
            }
            
            # Get existing activity data
            existing_data = await self.cache_manager.get(activity_key, CacheLevel.L1_MEMORY)
            if existing_data:
                activity_data['session_extended_count'] = existing_data.get('session_extended_count', 0)
            
            # Store activity with session timeout
            await self.cache_manager.set(
                activity_key,
                activity_data,
                CacheLevel.L1_MEMORY,
                ttl=self.default_timeout
            )
            
            logger.debug(f"📊 [SESSION-MANAGER] Activity tracked for user {user_id}: {activity_type}")
            
        except Exception as e:
            logger.error(f"❌ [SESSION-MANAGER] Failed to track activity for user {user_id}: {e}")
    
    async def check_session_timeout(self, user_id: str) -> Dict[str, Any]:
        """Check if user session is approaching timeout."""
        try:
            activity_key = f"user_activity:{user_id}"
            activity_data = await self.cache_manager.get(activity_key, CacheLevel.L1_MEMORY)
            
            if not activity_data:
                return {
                    'status': 'expired',
                    'message': 'Session has expired',
                    'requires_reauth': True
                }
            
            last_activity = datetime.fromisoformat(activity_data['last_activity'])
            time_since_activity = (datetime.now(timezone.utc) - last_activity).total_seconds()
            time_remaining = self.default_timeout - time_since_activity
            
            if time_remaining <= 0:
                return {
                    'status': 'expired',
                    'message': 'Session has expired',
                    'requires_reauth': True
                }
            elif time_remaining <= self.warning_threshold:
                return {
                    'status': 'warning',
                    'message': f'Session expires in {int(time_remaining)} seconds',
                    'time_remaining': int(time_remaining),
                    'requires_reauth': False,
                    'can_extend': True
                }
            else:
                return {
                    'status': 'active',
                    'message': 'Session is active',
                    'time_remaining': int(time_remaining),
                    'requires_reauth': False
                }
                
        except Exception as e:
            logger.error(f"❌ [SESSION-MANAGER] Failed to check session timeout for user {user_id}: {e}")
            return {
                'status': 'error',
                'message': 'Unable to check session status',
                'requires_reauth': True
            }
    
    async def extend_session(self, user_id: str, extension_seconds: int = None) -> bool:
        """Extend user session."""
        try:
            if extension_seconds is None:
                extension_seconds = self.default_timeout
            
            activity_key = f"user_activity:{user_id}"
            activity_data = await self.cache_manager.get(activity_key, CacheLevel.L1_MEMORY)
            
            if activity_data:
                activity_data['session_extended_count'] += 1
                activity_data['last_activity'] = datetime.now(timezone.utc).isoformat()
                
                await self.cache_manager.set(
                    activity_key,
                    activity_data,
                    CacheLevel.L1_MEMORY,
                    ttl=extension_seconds
                )
                
                logger.info(f"⏰ [SESSION-MANAGER] Session extended for user {user_id} by {extension_seconds} seconds")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ [SESSION-MANAGER] Failed to extend session for user {user_id}: {e}")
            return False


# Global session manager instance
_session_manager: Optional[SessionTimeoutManager] = None

def get_session_manager() -> SessionTimeoutManager:
    """Get global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionTimeoutManager()
    return _session_manager