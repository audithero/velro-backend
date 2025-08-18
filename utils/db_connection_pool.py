"""
High-Performance Database Connection Pool for Authorization System
Enterprise-grade connection pooling with monitoring and failover capabilities.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import asyncpg
import json
from enum import Enum
import psutil
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

class PoolType(Enum):
    """Pool types for different workloads"""
    AUTHORIZATION = "authorization"
    READ = "read"  
    WRITE = "write"
    ANALYTICS = "analytics"

@dataclass
class ConnectionPoolConfig:
    """Configuration for database connection pools"""
    pool_name: str
    min_connections: int = 5
    max_connections: int = 20
    connection_timeout_ms: int = 30000
    idle_timeout_ms: int = 600000  # 10 minutes
    max_lifetime_ms: int = 3600000  # 1 hour
    health_check_interval_ms: int = 30000  # 30 seconds
    retry_attempts: int = 3
    retry_delay_ms: int = 1000
    enable_monitoring: bool = True
    enable_query_logging: bool = False
    slow_query_threshold_ms: int = 100
    
@dataclass
class PoolMetrics:
    """Performance metrics for connection pool"""
    pool_name: str
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    connections_created: int = 0
    connections_closed: int = 0
    connection_errors: int = 0
    queries_executed: int = 0
    slow_queries: int = 0
    avg_query_time_ms: float = 0.0
    total_query_time_ms: float = 0.0
    peak_connections: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    
class ConnectionWrapper:
    """Wrapper for database connections with monitoring"""
    
    def __init__(self, connection: asyncpg.Connection, pool_name: str, created_at: datetime):
        self.connection = connection
        self.pool_name = pool_name
        self.created_at = created_at
        self.last_used = datetime.now()
        self.query_count = 0
        self.total_query_time_ms = 0.0
        self.is_healthy = True
        self._lock = asyncio.Lock()
        
    async def execute_with_monitoring(self, query: str, *args, **kwargs) -> Any:
        """Execute query with performance monitoring"""
        start_time = time.perf_counter()
        
        try:
            async with self._lock:
                result = await self.connection.execute(query, *args, **kwargs)
                
            execution_time = (time.perf_counter() - start_time) * 1000
            self.query_count += 1
            self.total_query_time_ms += execution_time
            self.last_used = datetime.now()
            
            # Log to performance monitoring
            await self._log_query_performance(query, execution_time, len(str(result)) if result else 0)
            
            return result
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            await self._log_query_error(query, execution_time, str(e))
            raise
            
    async def fetch_with_monitoring(self, query: str, *args, **kwargs) -> List[asyncpg.Record]:
        """Fetch query with performance monitoring"""
        start_time = time.perf_counter()
        
        try:
            async with self._lock:
                result = await self.connection.fetch(query, *args, **kwargs)
                
            execution_time = (time.perf_counter() - start_time) * 1000
            self.query_count += 1
            self.total_query_time_ms += execution_time
            self.last_used = datetime.now()
            
            # Log to performance monitoring
            await self._log_query_performance(query, execution_time, len(result))
            
            return result
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            await self._log_query_error(query, execution_time, str(e))
            raise
            
    async def fetchrow_with_monitoring(self, query: str, *args, **kwargs) -> Optional[asyncpg.Record]:
        """Fetch single row with performance monitoring"""
        start_time = time.perf_counter()
        
        try:
            async with self._lock:
                result = await self.connection.fetchrow(query, *args, **kwargs)
                
            execution_time = (time.perf_counter() - start_time) * 1000
            self.query_count += 1
            self.total_query_time_ms += execution_time
            self.last_used = datetime.now()
            
            # Log to performance monitoring
            await self._log_query_performance(query, execution_time, 1 if result else 0)
            
            return result
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            await self._log_query_error(query, execution_time, str(e))
            raise
            
    async def _log_query_performance(self, query: str, execution_time_ms: float, rows_returned: int):
        """Log query performance metrics"""
        try:
            query_type = self._classify_query(query)
            
            # Use the optimized logging function from our migration
            await self.connection.execute("""
                SELECT log_authorization_query_performance($1, NULL, $2, NULL, $3)
            """, query_type, execution_time_ms, rows_returned)
            
        except Exception as e:
            logger.warning(f"Failed to log query performance: {e}")
            
    async def _log_query_error(self, query: str, execution_time_ms: float, error: str):
        """Log query error"""
        logger.error(f"Query failed in {execution_time_ms:.2f}ms: {error[:200]}")
        
    def _classify_query(self, query: str) -> str:
        """Classify query type for monitoring"""
        query_lower = query.lower().strip()
        
        if 'check_user_permission' in query_lower:
            return 'permission_check'
        elif query_lower.startswith('select') and 'team_members' in query_lower:
            return 'team_lookup'
        elif query_lower.startswith('select') and 'projects' in query_lower:
            return 'project_access'
        elif query_lower.startswith('select') and 'generations' in query_lower:
            return 'generation_access'
        elif query_lower.startswith('select'):
            return 'read_query'
        elif query_lower.startswith(('insert', 'update', 'delete')):
            return 'write_query'
        else:
            return 'other_query'
            
    async def is_connection_healthy(self) -> bool:
        """Check if connection is healthy"""
        try:
            await asyncio.wait_for(
                self.connection.execute('SELECT 1'),
                timeout=5.0
            )
            self.is_healthy = True
            return True
        except Exception:
            self.is_healthy = False
            return False
            
    def should_retire(self, max_lifetime_ms: int) -> bool:
        """Check if connection should be retired"""
        age_ms = (datetime.now() - self.created_at).total_seconds() * 1000
        return age_ms > max_lifetime_ms

class HighPerformanceConnectionPool:
    """Enterprise-grade connection pool with monitoring and failover"""
    
    def __init__(self, database_url: str, config: ConnectionPoolConfig):
        self.database_url = database_url
        self.config = config
        self.connections: List[ConnectionWrapper] = []
        self.available_connections: asyncio.Queue = asyncio.Queue()
        self.metrics = PoolMetrics(pool_name=config.pool_name)
        self._lock = asyncio.Lock()
        self._shutdown = False
        self._health_check_task = None
        self._metrics_task = None
        
        # Connection lifecycle tracking
        self.connection_lifecycle: Dict[str, Dict] = defaultdict(dict)
        
        # Event callbacks
        self.on_connection_created: Optional[Callable] = None
        self.on_connection_closed: Optional[Callable] = None
        self.on_slow_query: Optional[Callable] = None
        
    async def initialize(self):
        """Initialize the connection pool"""
        logger.info(f"Initializing connection pool '{self.config.pool_name}'")
        
        # Create minimum connections
        for _ in range(self.config.min_connections):
            await self._create_connection()
            
        # Start background tasks
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._metrics_task = asyncio.create_task(self._metrics_collection_loop())
        
        logger.info(f"Connection pool '{self.config.pool_name}' initialized with {len(self.connections)} connections")
        
    async def _create_connection(self) -> ConnectionWrapper:
        """Create a new database connection"""
        try:
            connection = await asyncpg.connect(
                self.database_url,
                timeout=self.config.connection_timeout_ms / 1000,
                server_settings={
                    'application_name': f'velro_{self.config.pool_name}_pool',
                    'statement_timeout': str(self.config.connection_timeout_ms),
                }
            )
            
            wrapper = ConnectionWrapper(connection, self.config.pool_name, datetime.now())
            
            async with self._lock:
                self.connections.append(wrapper)
                self.metrics.connections_created += 1
                self.metrics.total_connections = len(self.connections)
                self.metrics.peak_connections = max(self.metrics.peak_connections, self.metrics.total_connections)
                
            await self.available_connections.put(wrapper)
            
            if self.on_connection_created:
                await self.on_connection_created(wrapper)
                
            logger.debug(f"Created new connection for pool '{self.config.pool_name}'")
            return wrapper
            
        except Exception as e:
            self.metrics.connection_errors += 1
            logger.error(f"Failed to create connection for pool '{self.config.pool_name}': {e}")
            raise
            
    async def _close_connection(self, wrapper: ConnectionWrapper):
        """Close a database connection"""
        try:
            await wrapper.connection.close()
            
            async with self._lock:
                if wrapper in self.connections:
                    self.connections.remove(wrapper)
                    self.metrics.connections_closed += 1
                    self.metrics.total_connections = len(self.connections)
                    
            if self.on_connection_closed:
                await self.on_connection_closed(wrapper)
                
            logger.debug(f"Closed connection for pool '{self.config.pool_name}'")
            
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
            
    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool with automatic return"""
        connection = None
        start_time = time.perf_counter()
        
        try:
            # Try to get an available connection
            connection = await asyncio.wait_for(
                self.available_connections.get(),
                timeout=self.config.connection_timeout_ms / 1000
            )
            
            # Check if connection is still healthy
            if not await connection.is_connection_healthy():
                await self._close_connection(connection)
                connection = await self._create_connection()
                
            # Update metrics
            self.metrics.active_connections += 1
            
            yield connection
            
        except asyncio.TimeoutError:
            # Try to create new connection if under max limit
            async with self._lock:
                if len(self.connections) < self.config.max_connections:
                    connection = await self._create_connection()
                else:
                    raise Exception(f"Connection pool '{self.config.pool_name}' exhausted")
                    
            self.metrics.active_connections += 1
            yield connection
            
        finally:
            if connection:
                # Update metrics
                self.metrics.active_connections -= 1
                
                # Check if connection should be retired
                if connection.should_retire(self.config.max_lifetime_ms):
                    await self._close_connection(connection)
                    # Create replacement if below minimum
                    if len(self.connections) < self.config.min_connections:
                        await self._create_connection()
                else:
                    # Return to pool
                    await self.available_connections.put(connection)
                    
    async def execute(self, query: str, *args, **kwargs) -> Any:
        """Execute query using pool connection"""
        async with self.get_connection() as conn:
            return await conn.execute_with_monitoring(query, *args, **kwargs)
            
    async def fetch(self, query: str, *args, **kwargs) -> List[asyncpg.Record]:
        """Fetch query using pool connection"""
        async with self.get_connection() as conn:
            return await conn.fetch_with_monitoring(query, *args, **kwargs)
            
    async def fetchrow(self, query: str, *args, **kwargs) -> Optional[asyncpg.Record]:
        """Fetch single row using pool connection"""
        async with self.get_connection() as conn:
            return await conn.fetchrow_with_monitoring(query, *args, **kwargs)
            
    async def _health_check_loop(self):
        """Background health check for connections"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.health_check_interval_ms / 1000)
                
                unhealthy_connections = []
                
                # Check all connections
                async with self._lock:
                    for conn in self.connections[:]:  # Copy list to avoid modification during iteration
                        if not await conn.is_connection_healthy():
                            unhealthy_connections.append(conn)
                            
                # Close unhealthy connections
                for conn in unhealthy_connections:
                    await self._close_connection(conn)
                    
                # Ensure minimum connections
                while len(self.connections) < self.config.min_connections:
                    await self._create_connection()
                    
            except Exception as e:
                logger.error(f"Health check error for pool '{self.config.pool_name}': {e}")
                
    async def _metrics_collection_loop(self):
        """Background metrics collection"""
        while not self._shutdown:
            try:
                await asyncio.sleep(60)  # Collect metrics every minute
                
                # Update metrics
                async with self._lock:
                    self.metrics.idle_connections = self.available_connections.qsize()
                    self.metrics.last_updated = datetime.now()
                    
                    # Calculate average query time
                    total_queries = sum(conn.query_count for conn in self.connections)
                    total_time = sum(conn.total_query_time_ms for conn in self.connections)
                    
                    if total_queries > 0:
                        self.metrics.avg_query_time_ms = total_time / total_queries
                        self.metrics.queries_executed = total_queries
                        self.metrics.total_query_time_ms = total_time
                        
                logger.debug(f"Pool '{self.config.pool_name}' metrics: "
                           f"Total={self.metrics.total_connections}, "
                           f"Active={self.metrics.active_connections}, "
                           f"Idle={self.metrics.idle_connections}, "
                           f"AvgQueryTime={self.metrics.avg_query_time_ms:.2f}ms")
                           
            except Exception as e:
                logger.error(f"Metrics collection error for pool '{self.config.pool_name}': {e}")
                
    async def get_metrics(self) -> PoolMetrics:
        """Get current pool metrics"""
        async with self._lock:
            return self.metrics
            
    async def close(self):
        """Close the connection pool"""
        logger.info(f"Closing connection pool '{self.config.pool_name}'")
        self._shutdown = True
        
        # Cancel background tasks
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()
            
        # Close all connections
        async with self._lock:
            for conn in self.connections[:]:
                await self._close_connection(conn)
                
        logger.info(f"Connection pool '{self.config.pool_name}' closed")

class ConnectionPoolManager:
    """Manager for multiple connection pools"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pools: Dict[PoolType, HighPerformanceConnectionPool] = {}
        self.configs: Dict[PoolType, ConnectionPoolConfig] = {}
        self._shutdown = False
        
    async def initialize_pools(self):
        """Initialize all connection pools"""
        
        # Authorization pool - optimized for frequent permission checks
        auth_config = ConnectionPoolConfig(
            pool_name="authorization",
            min_connections=10,
            max_connections=50,
            connection_timeout_ms=5000,
            idle_timeout_ms=300000,  # 5 minutes
            health_check_interval_ms=15000,  # 15 seconds
            slow_query_threshold_ms=50  # Very strict for auth queries
        )
        
        # Read pool - optimized for data retrieval
        read_config = ConnectionPoolConfig(
            pool_name="read",
            min_connections=5,
            max_connections=25,
            connection_timeout_ms=10000,
            idle_timeout_ms=600000,  # 10 minutes
            slow_query_threshold_ms=200
        )
        
        # Write pool - optimized for data modification
        write_config = ConnectionPoolConfig(
            pool_name="write",
            min_connections=3,
            max_connections=15,
            connection_timeout_ms=15000,
            idle_timeout_ms=300000,  # 5 minutes
            slow_query_threshold_ms=500
        )
        
        # Initialize pools
        for pool_type, config in [
            (PoolType.AUTHORIZATION, auth_config),
            (PoolType.READ, read_config),
            (PoolType.WRITE, write_config)
        ]:
            pool = HighPerformanceConnectionPool(self.database_url, config)
            await pool.initialize()
            
            self.pools[pool_type] = pool
            self.configs[pool_type] = config
            
        logger.info("All connection pools initialized successfully")
        
    def get_pool(self, pool_type: PoolType) -> HighPerformanceConnectionPool:
        """Get a specific connection pool"""
        if pool_type not in self.pools:
            raise ValueError(f"Pool type {pool_type} not initialized")
        return self.pools[pool_type]
        
    async def get_authorization_connection(self):
        """Get connection optimized for authorization queries"""
        return self.pools[PoolType.AUTHORIZATION].get_connection()
        
    async def get_read_connection(self):
        """Get connection optimized for read queries"""
        return self.pools[PoolType.READ].get_connection()
        
    async def get_write_connection(self):
        """Get connection optimized for write queries"""
        return self.pools[PoolType.WRITE].get_connection()
        
    async def check_user_permission(self, user_id: str, resource_type: str, resource_id: str, permission_type: str) -> Dict:
        """High-performance permission check using authorization pool"""
        async with self.get_authorization_connection() as conn:
            result = await conn.fetchrow_with_monitoring("""
                SELECT access_granted, effective_role, decision_factors
                FROM check_user_permission_optimized($1, $2, $3, $4)
            """, user_id, resource_type, resource_id, permission_type)
            
            if result:
                return {
                    'access_granted': result['access_granted'],
                    'effective_role': result['effective_role'],
                    'decision_factors': result['decision_factors']
                }
            return {'access_granted': False, 'effective_role': 'none', 'decision_factors': ['error']}
            
    async def get_all_metrics(self) -> Dict[str, PoolMetrics]:
        """Get metrics from all pools"""
        metrics = {}
        for pool_type, pool in self.pools.items():
            metrics[pool_type.value] = await pool.get_metrics()
        return metrics
        
    async def close_all(self):
        """Close all connection pools"""
        logger.info("Closing all connection pools")
        self._shutdown = True
        
        for pool in self.pools.values():
            await pool.close()
            
        logger.info("All connection pools closed")

# Global connection pool manager instance
_pool_manager: Optional[ConnectionPoolManager] = None

async def get_pool_manager(database_url: str) -> ConnectionPoolManager:
    """Get global connection pool manager instance"""
    global _pool_manager
    
    if _pool_manager is None:
        _pool_manager = ConnectionPoolManager(database_url)
        await _pool_manager.initialize_pools()
        
    return _pool_manager

async def close_pool_manager():
    """Close global connection pool manager"""
    global _pool_manager
    
    if _pool_manager:
        await _pool_manager.close_all()
        _pool_manager = None