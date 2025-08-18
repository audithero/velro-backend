"""
Production-ready connection pool wrapper for Supabase
Implements actual connection pooling to fix the 0% concurrent request success rate
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class ProductionConnectionPool:
    """
    Production connection pool manager for Supabase operations.
    Uses httpx connection pooling for better concurrent handling.
    """
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.pool_config = {
            "max_connections": int(os.getenv("DATABASE_MAX_CONNECTIONS", "50")),
            "max_keepalive_connections": int(os.getenv("DATABASE_MIN_CONNECTIONS", "10")),
            "keepalive_expiry": 300,  # 5 minutes
            "timeout": httpx.Timeout(30.0, connect=10.0)
        }
        self.is_initialized = False
        
    async def initialize(self):
        """Initialize the connection pool."""
        if self.is_initialized:
            return
            
        try:
            # Create httpx client with connection pooling
            limits = httpx.Limits(
                max_connections=self.pool_config["max_connections"],
                max_keepalive_connections=self.pool_config["max_keepalive_connections"]
            )
            
            self.client = httpx.AsyncClient(
                limits=limits,
                timeout=self.pool_config["timeout"],
                http2=False,  # Disabled HTTP/2 as h2 package not installed
                follow_redirects=True
            )
            
            self.is_initialized = True
            logger.info(f"✅ Connection pool initialized with {self.pool_config['max_connections']} max connections")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize connection pool: {e}")
            raise
    
    async def close(self):
        """Close the connection pool."""
        if self.client:
            await self.client.aclose()
            self.is_initialized = False
            logger.info("Connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool."""
        if not self.is_initialized:
            await self.initialize()
        
        try:
            yield self.client
        except Exception as e:
            logger.error(f"Connection error: {e}")
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with automatic retry logic."""
        async with self.get_connection() as conn:
            return await func(conn, *args, **kwargs)

# Global pool instance
_pool: Optional[ProductionConnectionPool] = None

def get_pool() -> ProductionConnectionPool:
    """Get or create the global connection pool."""
    global _pool
    if _pool is None:
        _pool = ProductionConnectionPool()
    return _pool

async def initialize_pool():
    """Initialize the global connection pool."""
    pool = get_pool()
    await pool.initialize()
    return pool

async def close_pool():
    """Close the global connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None