"""
Database Connection Pool Manager
PRD Compliant - Section 5.4.7 Performance Optimization
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import asyncpg
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)

@dataclass
class PoolStatistics:
    """Connection pool statistics for monitoring."""
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    waiting_queries: int = 0
    total_queries: int = 0
    failed_queries: int = 0
    avg_query_time: float = 0.0
    peak_connections: int = 0
    last_health_check: Optional[datetime] = None
    
class DatabaseConnectionPool:
    """
    Enterprise-grade database connection pool manager.
    Implements connection pooling, circuit breaking, and performance monitoring.
    """
    
    def __init__(self, config_path: str = "config/database_pooling.json"):
        """Initialize connection pool with configuration."""
        self.config = self._load_config(config_path)
        self.pool: Optional[asyncpg.Pool] = None
        self.stats = PoolStatistics()
        self._circuit_breaker_open = False
        self._circuit_breaker_failures = 0
        self._last_failure_time: Optional[datetime] = None
        
    def _load_config(self, config_path: str) -> Dict:
        """Load pool configuration from file."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self._get_default_config()
            
    def _get_default_config(self) -> Dict:
        """Get default configuration if config file not found."""
        return {
            "connection_pool": {
                "min_size": 10,
                "max_size": 50,
                "max_idle_time": 300,
                "connection_timeout": 30
            },
            "performance": {
                "statement_cache_size": 100,
                "prepared_statements": True
            },
            "resilience": {
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 5,
                "circuit_breaker_timeout": 60
            }
        }
        
    async def initialize(self, dsn: str) -> None:
        """Initialize the connection pool."""
        logger.info("Initializing database connection pool...")
        
        pool_config = self.config["connection_pool"]
        
        try:
            self.pool = await asyncpg.create_pool(
                dsn,
                min_size=pool_config["min_size"],
                max_size=pool_config["max_size"],
                max_inactive_connection_lifetime=pool_config.get("max_idle_time", 300),
                timeout=pool_config.get("connection_timeout", 30),
                command_timeout=60,
                # Performance optimizations
                server_settings={
                    'jit': 'off',  # Disable JIT for consistent performance
                    'statement_timeout': '30s',
                    'idle_in_transaction_session_timeout': '60s'
                }
            )
            
            logger.info(f"✅ Connection pool initialized with {pool_config['min_size']}-{pool_config['max_size']} connections")
            
            # Start monitoring tasks
            asyncio.create_task(self._monitor_pool_health())
            asyncio.create_task(self._cleanup_idle_connections())
            
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
            
    async def _monitor_pool_health(self) -> None:
        """Monitor pool health and collect statistics."""
        while True:
            try:
                if self.pool:
                    # Update statistics
                    self.stats.total_connections = self.pool.get_size()
                    self.stats.idle_connections = self.pool.get_idle_size()
                    self.stats.active_connections = self.stats.total_connections - self.stats.idle_connections
                    
                    # Track peak connections
                    if self.stats.active_connections > self.stats.peak_connections:
                        self.stats.peak_connections = self.stats.active_connections
                        
                    # Health check
                    async with self.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                        self.stats.last_health_check = datetime.utcnow()
                        
                    # Log statistics
                    if self.stats.total_queries % 100 == 0:  # Log every 100 queries
                        logger.info(f"Pool stats: {self.stats.active_connections}/{self.stats.total_connections} active, "
                                  f"{self.stats.total_queries} total queries, "
                                  f"{self.stats.failed_queries} failures")
                        
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                
            await asyncio.sleep(30)  # Check every 30 seconds
            
    async def _cleanup_idle_connections(self) -> None:
        """Clean up idle connections periodically."""
        while True:
            try:
                if self.pool and self.stats.idle_connections > self.config["connection_pool"]["min_size"]:
                    # Close excess idle connections
                    await self.pool.expire_connections()
                    logger.debug("Cleaned up idle connections")
                    
            except Exception as e:
                logger.error(f"Idle connection cleanup failed: {e}")
                
            await asyncio.sleep(300)  # Clean up every 5 minutes
            
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool with circuit breaker."""
        if self._circuit_breaker_open:
            if self._should_attempt_reset():
                self._circuit_breaker_open = False
                self._circuit_breaker_failures = 0
                logger.info("Circuit breaker reset, attempting connection")
            else:
                raise ConnectionError("Circuit breaker is open")
                
        start_time = datetime.utcnow()
        
        try:
            async with self.pool.acquire() as conn:
                # Track statistics
                self.stats.total_queries += 1
                
                yield conn
                
                # Update average query time
                query_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                self.stats.avg_query_time = (
                    (self.stats.avg_query_time * (self.stats.total_queries - 1) + query_time) 
                    / self.stats.total_queries
                )
                
        except Exception as e:
            self.stats.failed_queries += 1
            self._handle_connection_failure(e)
            raise
            
    def _handle_connection_failure(self, error: Exception) -> None:
        """Handle connection failures and manage circuit breaker."""
        self._circuit_breaker_failures += 1
        self._last_failure_time = datetime.utcnow()
        
        threshold = self.config["resilience"]["circuit_breaker_threshold"]
        
        if self._circuit_breaker_failures >= threshold:
            self._circuit_breaker_open = True
            logger.error(f"Circuit breaker opened after {threshold} failures")
            
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset."""
        if not self._last_failure_time:
            return True
            
        timeout = self.config["resilience"]["circuit_breaker_timeout"]
        elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
        
        return elapsed >= timeout
        
    async def execute_query(self, query: str, *args, timeout: float = None) -> Any:
        """Execute a query with connection pooling and monitoring."""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)
            
    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
        """Execute multiple queries in a batch."""
        async with self.acquire() as conn:
            await conn.executemany(query, args_list)
            
    def get_statistics(self) -> Dict:
        """Get current pool statistics."""
        return {
            "total_connections": self.stats.total_connections,
            "active_connections": self.stats.active_connections,
            "idle_connections": self.stats.idle_connections,
            "total_queries": self.stats.total_queries,
            "failed_queries": self.stats.failed_queries,
            "failure_rate": (self.stats.failed_queries / max(self.stats.total_queries, 1)) * 100,
            "avg_query_time_ms": self.stats.avg_query_time,
            "peak_connections": self.stats.peak_connections,
            "circuit_breaker_open": self._circuit_breaker_open,
            "last_health_check": self.stats.last_health_check.isoformat() if self.stats.last_health_check else None
        }
        
    async def close(self) -> None:
        """Close the connection pool gracefully."""
        if self.pool:
            await self.pool.close()
            logger.info("Connection pool closed")
            
# Global pool instance
_connection_pool: Optional[DatabaseConnectionPool] = None

async def get_connection_pool() -> DatabaseConnectionPool:
    """Get or create the global connection pool instance."""
    global _connection_pool
    
    if _connection_pool is None:
        _connection_pool = DatabaseConnectionPool()
        
        # Get database URL from environment
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL not configured")
            
        await _connection_pool.initialize(database_url)
        
    return _connection_pool
