"""
Redis configuration and connection management.
Optimized for performance with connection pooling.
"""
import os
import redis.asyncio as redis
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class RedisManager:
    """Manage Redis connections with proper pooling."""
    
    _instance: Optional['RedisManager'] = None
    _redis_client: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_client(self) -> Optional[redis.Redis]:
        """Get Redis client with connection pooling."""
        if self._redis_client is None:
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                logger.warning("Redis URL not configured - caching disabled")
                return None
            
            try:
                # Create connection pool
                pool = redis.ConnectionPool.from_url(
                    redis_url,
                    max_connections=50,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                
                self._redis_client = redis.Redis(
                    connection_pool=pool,
                    decode_responses=True
                )
                
                # Test connection
                await self._redis_client.ping()
                logger.info("✅ Redis connected successfully")
                
            except Exception as e:
                logger.error(f"❌ Redis connection failed: {e}")
                self._redis_client = None
                
        return self._redis_client
    
    async def close(self):
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None

# Global instance
redis_manager = RedisManager()

async def get_redis() -> Optional[redis.Redis]:
    """Get Redis client for dependency injection."""
    return await redis_manager.get_client()