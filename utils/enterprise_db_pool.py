"""
Enterprise Database Connection Pool Manager
Implements enterprise-grade connection pooling with health monitoring,
performance optimization, and automated maintenance as specified in UUID Validation Standards.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, AsyncContextManager, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from contextlib import asynccontextmanager
import psutil
import asyncpg
from asyncpg import Pool, Connection

from database import get_database
from utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class PoolType(Enum):
    """Database pool types for different workloads."""
    AUTHORIZATION = "authorization"      # Optimized for authorization queries
    READ_HEAVY = "read_heavy"           # Optimized for read operations  
    WRITE_HEAVY = "write_heavy"         # Optimized for write operations
    GENERAL = "general"                 # General purpose pool
    MAINTENANCE = "maintenance"         # Long-running maintenance operations


class PoolHealth(Enum):
    """Pool health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


@dataclass
class PoolConfig:
    """Database pool configuration."""
    pool_name: str
    database_url: str
    pool_type: PoolType
    min_connections: int = 5
    max_connections: int = 20
    connection_timeout: float = 30.0
    idle_timeout: float = 600.0
    max_lifetime: float = 3600.0
    query_timeout: float = 30.0
    statement_timeout: float = 60.0
    health_check_interval: int = 30
    prepared_statement_cache_size: int = 100
    enable_statement_pooling: bool = True
    enable_query_caching: bool = True
    max_prepared_statements: int = 50
    connection_validation_query: str = "SELECT 1"
    leak_detection_threshold: float = 60.0


@dataclass 
class PoolMetrics:
    """Pool performance metrics."""
    pool_name: str
    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    connections_created_total: int = 0
    connections_destroyed_total: int = 0
    connection_creation_time_ms: float = 0.0
    connection_usage_time_ms: float = 0.0
    queries_executed_total: int = 0
    slow_queries_total: int = 0
    connection_errors_total: int = 0
    pool_exhaustion_events: int = 0
    health_status: PoolHealth = PoolHealth.HEALTHY
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)


class EnterpriseConnectionPool:
    """
    Enterprise connection pool with advanced features:
    - Connection health monitoring
    - Performance optimization for different workloads
    - Automatic connection lifecycle management
    - Query performance tracking
    - Circuit breaker pattern
    """
    
    def __init__(self, config: PoolConfig):
        self.config = config
        self.pool: Optional[Pool] = None
        self.metrics = PoolMetrics(pool_name=config.pool_name)
        self.circuit_breaker_open = False
        self.circuit_breaker_failures = 0
        self.circuit_breaker_last_failure = 0
        self.max_circuit_failures = 5
        self.circuit_recovery_timeout = 30
        
        # Performance tracking
        self.query_performance_history: List[Tuple[float, str]] = []
        self.connection_lease_times: Dict[int, float] = {}
        
        # Health monitoring
        self.last_health_check = time.time()
        self.consecutive_health_failures = 0
        
    async def initialize(self) -> None:
        """Initialize the connection pool with optimized settings."""
        try:
            logger.info(f"🔄 Initializing {self.config.pool_name} ({self.config.pool_type.value})")
            
            # Configure pool based on workload type
            pool_kwargs = await self._get_optimized_pool_config()
            
            self.pool = await asyncpg.create_pool(
                dsn=self.config.database_url,
                min_size=self.config.min_connections,
                max_size=self.config.max_connections,
                **pool_kwargs
            )
            
            # Warm up the pool
            await self._warm_up_pool()
            
            # Start health monitoring
            asyncio.create_task(self._health_monitor_loop())
            
            logger.info(f"✅ {self.config.pool_name} initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize {self.config.pool_name}: {e}")
            self.metrics.health_status = PoolHealth.UNAVAILABLE
            raise
    
    async def _get_optimized_pool_config(self) -> Dict[str, Any]:
        """Get optimized pool configuration based on pool type."""
        base_config = {
            "command_timeout": self.config.query_timeout,
            "setup": self._setup_connection,
            "init": self._init_connection
        }
        
        # Workload-specific optimizations
        if self.config.pool_type == PoolType.AUTHORIZATION:
            base_config.update({
                "server_settings": {
                    "application_name": f"velro_auth_pool_{self.config.pool_name}",
                    "statement_timeout": "30s",  # Fast authorization queries
                    "idle_in_transaction_session_timeout": "60s",
                    "tcp_keepalives_idle": "300",
                    "tcp_keepalives_interval": "30",
                    "tcp_keepalives_count": "3"
                }
            })
        elif self.config.pool_type == PoolType.READ_HEAVY:
            base_config.update({
                "server_settings": {
                    "application_name": f"velro_read_pool_{self.config.pool_name}",
                    "statement_timeout": "60s",
                    "work_mem": "16MB",  # More memory for complex reads
                    "effective_cache_size": "256MB",
                    "random_page_cost": "1.1"  # Assume SSD storage
                }
            })
        elif self.config.pool_type == PoolType.WRITE_HEAVY:
            base_config.update({
                "server_settings": {
                    "application_name": f"velro_write_pool_{self.config.pool_name}",
                    "statement_timeout": "120s",
                    "synchronous_commit": "on",
                    "wal_level": "replica",
                    "checkpoint_timeout": "5min"
                }
            })
        
        return base_config
    
    async def _setup_connection(self, connection: Connection) -> None:
        """Setup connection with pool-specific optimizations."""
        # Configure prepared statement cache
        if self.config.enable_statement_pooling:
            await connection.execute(f"SET max_prepared_transactions = {self.config.max_prepared_statements}")
        
        # Set query timeout
        await connection.execute(f"SET statement_timeout = '{int(self.config.statement_timeout * 1000)}ms'")
        
        # Pool-type specific setup
        if self.config.pool_type == PoolType.AUTHORIZATION:
            # Optimize for fast authorization queries
            await connection.execute("SET work_mem = '4MB'")
            await connection.execute("SET effective_cache_size = '128MB'")
            await connection.execute("SET random_page_cost = 1.1")
        elif self.config.pool_type == PoolType.READ_HEAVY:
            # Optimize for complex read queries
            await connection.execute("SET work_mem = '16MB'")
            await connection.execute("SET effective_cache_size = '512MB'")
            await connection.execute("SET enable_seqscan = off")  # Prefer indexes
    
    async def _init_connection(self, connection: Connection) -> None:
        """Initialize connection with custom types and extensions."""
        # Set up UUID type handling
        await connection.set_type_codec(
            'uuid',
            encoder=str,
            decoder=lambda x: str(x),
            schema='pg_catalog'
        )
        
        # Enable performance monitoring
        await connection.execute("SET log_statement_stats = on")
        await connection.execute("SET log_duration = on")
    
    async def _warm_up_pool(self) -> None:
        """Warm up the pool with initial connections."""
        try:
            connections = []
            warm_up_count = min(self.config.min_connections, 3)
            
            for _ in range(warm_up_count):
                conn = await self.pool.acquire()
                # Run a simple query to establish the connection
                await conn.execute(self.config.connection_validation_query)
                connections.append(conn)
            
            # Release all connections
            for conn in connections:
                await self.pool.release(conn)
            
            logger.info(f"🔥 Warmed up {warm_up_count} connections for {self.config.pool_name}")
            
        except Exception as e:
            logger.warning(f"⚠️ Pool warm-up failed for {self.config.pool_name}: {e}")
    
    @asynccontextmanager
    async def acquire_connection(self) -> AsyncContextManager[Connection]:
        """Acquire a connection with performance monitoring."""
        if self.circuit_breaker_open:
            if time.time() - self.circuit_breaker_last_failure > self.circuit_recovery_timeout:
                self.circuit_breaker_open = False
                self.circuit_breaker_failures = 0
                logger.info(f"🔄 Circuit breaker reset for {self.config.pool_name}")
            else:
                raise Exception(f"Circuit breaker open for {self.config.pool_name}")
        
        connection = None
        start_time = time.time()
        
        try:
            connection = await self.pool.acquire(timeout=self.config.connection_timeout)
            connection_id = id(connection)
            self.connection_lease_times[connection_id] = start_time
            
            # Update metrics
            self.metrics.active_connections += 1
            self.metrics.connections_created_total += 1
            
            yield connection
            
        except asyncio.TimeoutError:
            self.metrics.pool_exhaustion_events += 1
            self._handle_circuit_breaker_failure()
            raise Exception(f"Connection timeout for pool {self.config.pool_name}")
            
        except Exception as e:
            self.metrics.connection_errors_total += 1
            self._handle_circuit_breaker_failure()
            logger.error(f"❌ Connection acquisition failed for {self.config.pool_name}: {e}")
            raise
            
        finally:
            if connection:
                try:
                    connection_id = id(connection)
                    if connection_id in self.connection_lease_times:
                        usage_time = time.time() - self.connection_lease_times[connection_id]
                        self.metrics.connection_usage_time_ms = usage_time * 1000
                        del self.connection_lease_times[connection_id]
                        
                        # Check for connection leaks
                        if usage_time > self.config.leak_detection_threshold:
                            logger.warning(f"🔍 Potential connection leak detected in {self.config.pool_name}: {usage_time}s")
                    
                    await self.pool.release(connection)
                    self.metrics.active_connections -= 1
                    
                except Exception as e:
                    logger.error(f"❌ Error releasing connection in {self.config.pool_name}: {e}")
    
    def _handle_circuit_breaker_failure(self) -> None:
        """Handle circuit breaker failures."""
        self.circuit_breaker_failures += 1
        self.circuit_breaker_last_failure = time.time()
        
        if self.circuit_breaker_failures >= self.max_circuit_failures:
            self.circuit_breaker_open = True
            self.metrics.health_status = PoolHealth.CRITICAL
            logger.warning(f"🚨 Circuit breaker opened for {self.config.pool_name}")
    
    async def execute_query(
        self, 
        query: str, 
        *args, 
        timeout: Optional[float] = None,
        prepared: bool = True
    ) -> Any:
        """Execute a query with performance monitoring."""
        start_time = time.time()
        
        try:
            async with self.acquire_connection() as conn:
                if prepared and self.config.enable_statement_pooling:
                    result = await conn.fetch(query, *args, timeout=timeout or self.config.query_timeout)
                else:
                    result = await conn.fetch(query, *args)
                
                # Track query performance
                execution_time = time.time() - start_time
                self._track_query_performance(query, execution_time)
                
                self.metrics.queries_executed_total += 1
                return result
                
        except Exception as e:
            execution_time = time.time() - start_time
            self._track_query_performance(query, execution_time, error=True)
            logger.error(f"❌ Query execution failed in {self.config.pool_name}: {e}")
            raise
    
    def _track_query_performance(self, query: str, execution_time: float, error: bool = False) -> None:
        """Track query performance for optimization."""
        # Store recent performance data (keep last 1000 queries)
        self.query_performance_history.append((execution_time, query[:100]))  # Truncate query for storage
        if len(self.query_performance_history) > 1000:
            self.query_performance_history.pop(0)
        
        # Track slow queries
        if execution_time > 0.1:  # 100ms threshold
            self.metrics.slow_queries_total += 1
        
        # Update average response time
        if self.metrics.queries_executed_total > 0:
            self.metrics.connection_usage_time_ms = (
                (self.metrics.connection_usage_time_ms * (self.metrics.queries_executed_total - 1) + execution_time * 1000) /
                self.metrics.queries_executed_total
            )
    
    async def _health_monitor_loop(self) -> None:
        """Continuous health monitoring loop."""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Health monitoring error for {self.config.pool_name}: {e}")
    
    async def _perform_health_check(self) -> None:
        """Perform comprehensive health check."""
        try:
            start_time = time.time()
            
            # Test connection
            async with self.acquire_connection() as conn:
                await conn.execute(self.config.connection_validation_query)
            
            health_check_time = time.time() - start_time
            
            # Update metrics
            self.metrics.total_connections = len(self.pool._holders) if self.pool else 0
            self.metrics.idle_connections = self.metrics.total_connections - self.metrics.active_connections
            self.metrics.last_updated = datetime.utcnow()
            
            # System resource monitoring
            process = psutil.Process()
            self.metrics.cpu_usage_percent = process.cpu_percent()
            self.metrics.memory_usage_mb = process.memory_info().rss / 1024 / 1024
            
            # Determine health status
            if health_check_time > 1.0:  # 1 second threshold
                self.metrics.health_status = PoolHealth.DEGRADED
                self.consecutive_health_failures += 1
            elif self.circuit_breaker_open:
                self.metrics.health_status = PoolHealth.CRITICAL
            else:
                self.metrics.health_status = PoolHealth.HEALTHY
                self.consecutive_health_failures = 0
            
            # Log health status if degraded
            if self.metrics.health_status != PoolHealth.HEALTHY:
                logger.warning(f"⚠️ Pool {self.config.pool_name} health: {self.metrics.health_status.value}")
            
        except Exception as e:
            self.consecutive_health_failures += 1
            self.metrics.health_status = PoolHealth.CRITICAL
            logger.error(f"❌ Health check failed for {self.config.pool_name}: {e}")
            
            if self.consecutive_health_failures >= 3:
                self.metrics.health_status = PoolHealth.UNAVAILABLE
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        recent_queries = self.query_performance_history[-100:] if self.query_performance_history else []
        
        return {
            "pool_name": self.config.pool_name,
            "pool_type": self.config.pool_type.value,
            "health_status": self.metrics.health_status.value,
            "connections": {
                "active": self.metrics.active_connections,
                "idle": self.metrics.idle_connections,
                "total": self.metrics.total_connections,
                "max": self.config.max_connections,
                "utilization_percent": (self.metrics.active_connections / self.config.max_connections * 100) if self.config.max_connections > 0 else 0
            },
            "performance": {
                "queries_executed": self.metrics.queries_executed_total,
                "slow_queries": self.metrics.slow_queries_total,
                "slow_query_percent": (self.metrics.slow_queries_total / max(self.metrics.queries_executed_total, 1)) * 100,
                "avg_query_time_ms": self.metrics.connection_usage_time_ms,
                "avg_connection_usage_ms": self.metrics.connection_usage_time_ms
            },
            "errors": {
                "connection_errors": self.metrics.connection_errors_total,
                "pool_exhaustion_events": self.metrics.pool_exhaustion_events,
                "circuit_breaker_failures": self.circuit_breaker_failures,
                "circuit_breaker_open": self.circuit_breaker_open
            },
            "resources": {
                "cpu_usage_percent": self.metrics.cpu_usage_percent,
                "memory_usage_mb": self.metrics.memory_usage_mb
            },
            "recent_query_times": [q[0] for q in recent_queries[-10:]]  # Last 10 query times
        }
    
    async def close(self) -> None:
        """Close the connection pool gracefully."""
        if self.pool:
            try:
                await self.pool.close()
                logger.info(f"✅ Closed connection pool {self.config.pool_name}")
            except Exception as e:
                logger.error(f"❌ Error closing pool {self.config.pool_name}: {e}")


class EnterpriseConnectionPoolManager:
    """
    Manager for multiple enterprise connection pools with:
    - Automatic pool creation and management
    - Health monitoring across all pools
    - Performance optimization recommendations
    - Automated maintenance and cleanup
    """
    
    def __init__(self):
        self.pools: Dict[str, EnterpriseConnectionPool] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        
    async def initialize_pools(self) -> None:
        """Initialize all pools from database configuration."""
        try:
            db = await get_database()
            
            # Get pool configurations
            pool_configs = await db.execute_query(
                table="connection_pool_config",
                operation="select",
                filters={"enabled": True},
                order_by="pool_name"
            )
            
            for config_data in pool_configs:
                config = PoolConfig(
                    pool_name=config_data["pool_name"],
                    database_url=config_data.get("database_url_template", ""),  # Should be set from environment
                    pool_type=PoolType(config_data.get("pool_type", "general")),
                    min_connections=config_data["min_connections"],
                    max_connections=config_data["max_connections"],
                    connection_timeout=config_data["connection_timeout_ms"] / 1000,
                    idle_timeout=config_data["idle_timeout_ms"] / 1000,
                    max_lifetime=config_data["max_lifetime_ms"] / 1000,
                    query_timeout=config_data["query_timeout_ms"] / 1000,
                    statement_timeout=config_data["statement_timeout_ms"] / 1000,
                    health_check_interval=config_data["health_check_interval_ms"] // 1000,
                    prepared_statement_cache_size=config_data["prepared_statement_cache_size"],
                    enable_statement_pooling=config_data["enable_statement_pooling"],
                    enable_query_caching=config_data["enable_query_caching"],
                    max_prepared_statements=config_data["max_prepared_statements"]
                )
                
                # Create and initialize pool
                pool = EnterpriseConnectionPool(config)
                await pool.initialize()
                self.pools[config.pool_name] = pool
            
            # Start monitoring
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            logger.info(f"✅ Initialized {len(self.pools)} enterprise connection pools")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize connection pools: {e}")
            raise
    
    def get_pool(self, pool_name: str) -> Optional[EnterpriseConnectionPool]:
        """Get a specific connection pool."""
        return self.pools.get(pool_name)
    
    async def execute_with_pool(
        self, 
        pool_name: str,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> Any:
        """Execute a query using a specific pool."""
        pool = self.get_pool(pool_name)
        if not pool:
            raise Exception(f"Pool '{pool_name}' not found")
        
        return await pool.execute_query(query, *args, timeout=timeout)
    
    @asynccontextmanager
    async def acquire_from_pool(self, pool_name: str) -> AsyncContextManager[Connection]:
        """Acquire a connection from a specific pool."""
        pool = self.get_pool(pool_name)
        if not pool:
            raise Exception(f"Pool '{pool_name}' not found")
        
        async with pool.acquire_connection() as conn:
            yield conn
    
    async def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get performance metrics for all pools."""
        metrics = {}
        for pool_name, pool in self.pools.items():
            metrics[pool_name] = await pool.get_performance_stats()
        return metrics
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary."""
        total_pools = len(self.pools)
        healthy_pools = sum(1 for pool in self.pools.values() if pool.metrics.health_status == PoolHealth.HEALTHY)
        degraded_pools = sum(1 for pool in self.pools.values() if pool.metrics.health_status == PoolHealth.DEGRADED)
        critical_pools = sum(1 for pool in self.pools.values() if pool.metrics.health_status == PoolHealth.CRITICAL)
        unavailable_pools = sum(1 for pool in self.pools.values() if pool.metrics.health_status == PoolHealth.UNAVAILABLE)
        
        total_connections = sum(pool.metrics.total_connections for pool in self.pools.values())
        active_connections = sum(pool.metrics.active_connections for pool in self.pools.values())
        
        return {
            "overall_health": "healthy" if critical_pools == 0 and unavailable_pools == 0 else ("degraded" if critical_pools < total_pools // 2 else "critical"),
            "pools": {
                "total": total_pools,
                "healthy": healthy_pools,
                "degraded": degraded_pools,
                "critical": critical_pools,
                "unavailable": unavailable_pools
            },
            "connections": {
                "total": total_connections,
                "active": active_connections,
                "utilization_percent": (active_connections / total_connections * 100) if total_connections > 0 else 0
            },
            "last_updated": datetime.utcnow().isoformat()
        }
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop for all pools."""
        while True:
            try:
                await asyncio.sleep(60)  # Monitor every minute
                await self._log_performance_metrics()
                await self._check_pool_optimization_opportunities()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Pool monitoring error: {e}")
    
    async def _log_performance_metrics(self) -> None:
        """Log performance metrics to database."""
        try:
            db = await get_database()
            
            for pool_name, pool in self.pools.items():
                await db.execute_query(
                    table="connection_pool_health",
                    operation="insert",
                    data={
                        "pool_name": pool_name,
                        "active_connections": pool.metrics.active_connections,
                        "idle_connections": pool.metrics.idle_connections,
                        "total_connections": pool.metrics.total_connections,
                        "connections_created_total": pool.metrics.connections_created_total,
                        "connections_destroyed_total": pool.metrics.connections_destroyed_total,
                        "connection_creation_time_ms": pool.metrics.connection_creation_time_ms,
                        "connection_usage_time_ms": pool.metrics.connection_usage_time_ms,
                        "queries_executed_total": pool.metrics.queries_executed_total,
                        "slow_queries_total": pool.metrics.slow_queries_total,
                        "connection_errors_total": pool.metrics.connection_errors_total,
                        "pool_exhaustion_events": pool.metrics.pool_exhaustion_events,
                        "health_status": pool.metrics.health_status.value,
                        "cpu_usage_percent": pool.metrics.cpu_usage_percent,
                        "memory_usage_mb": pool.metrics.memory_usage_mb
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Failed to log pool metrics: {e}")
    
    async def _check_pool_optimization_opportunities(self) -> None:
        """Check for pool optimization opportunities."""
        for pool_name, pool in self.pools.items():
            stats = await pool.get_performance_stats()
            
            # High utilization warning
            if stats["connections"]["utilization_percent"] > 80:
                logger.warning(f"⚠️ High connection utilization in {pool_name}: {stats['connections']['utilization_percent']:.1f}%")
            
            # Slow query warning
            if stats["performance"]["slow_query_percent"] > 10:
                logger.warning(f"⚠️ High slow query rate in {pool_name}: {stats['performance']['slow_query_percent']:.1f}%")
            
            # Pool exhaustion warning
            if pool.metrics.pool_exhaustion_events > 0:
                logger.warning(f"⚠️ Pool exhaustion events in {pool_name}: {pool.metrics.pool_exhaustion_events}")
    
    async def close_all_pools(self) -> None:
        """Close all connection pools gracefully."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        for pool_name, pool in self.pools.items():
            try:
                await pool.close()
            except Exception as e:
                logger.error(f"❌ Error closing pool {pool_name}: {e}")
        
        self.pools.clear()
        logger.info("✅ All connection pools closed")


# Global instance
enterprise_pool_manager = EnterpriseConnectionPoolManager()


# Convenience functions for common operations
async def get_authorization_connection():
    """Get a connection optimized for authorization queries."""
    return enterprise_pool_manager.acquire_from_pool("authorization_pool_primary")


async def get_read_connection():
    """Get a connection optimized for read operations."""
    return enterprise_pool_manager.acquire_from_pool("read_pool_primary")


async def get_write_connection():
    """Get a connection optimized for write operations."""
    return enterprise_pool_manager.acquire_from_pool("write_pool_primary")


async def execute_authorization_query(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute an authorization query with optimal performance."""
    return await enterprise_pool_manager.execute_with_pool(
        "authorization_pool_primary", query, *args, timeout=timeout
    )