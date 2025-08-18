"""
PHASE 2: Enterprise Connection Pool Manager with 6 Specialized Pools
PRD Requirement: Support 10,000+ concurrent users with 200+ total connections
Implements 6 specialized pools with health monitoring, failover, and performance optimization.
"""

import asyncio
import logging
import time
import threading
from typing import Dict, List, Optional, Any, AsyncContextManager, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from contextlib import asynccontextmanager
import psutil
import json
from concurrent.futures import ThreadPoolExecutor
from collections import deque, defaultdict

from config import settings

logger = logging.getLogger(__name__)


class SpecializedPoolType(Enum):
    """6 Specialized connection pool types as per PRD requirements."""
    AUTH = "auth_pool"           # Auth operations: 10-50 connections
    READ = "read_pool"           # Read queries: 20-75 connections  
    WRITE = "write_pool"         # Write operations: 5-25 connections
    ANALYTICS = "analytics_pool" # Analytics queries: 5-20 connections
    ADMIN = "admin_pool"         # Admin operations: 2-10 connections
    BATCH = "batch_pool"         # Batch operations: 5-30 connections


class PoolHealth(Enum):
    """Pool health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"
    RECOVERING = "recovering"


class QueryType(Enum):
    """Query classification for routing optimization."""
    AUTH_LOGIN = "auth_login"
    AUTH_VERIFY = "auth_verify"
    AUTH_PERMISSIONS = "auth_permissions"
    READ_USER_DATA = "read_user_data"
    READ_PROJECT_DATA = "read_project_data"
    READ_ANALYTICS = "read_analytics"
    WRITE_CREATE = "write_create"
    WRITE_UPDATE = "write_update"
    WRITE_DELETE = "write_delete"
    ANALYTICS_AGGREGATE = "analytics_aggregate"
    ANALYTICS_REPORT = "analytics_report"
    ADMIN_CONFIG = "admin_config"
    ADMIN_MAINTENANCE = "admin_maintenance"
    BATCH_PROCESS = "batch_process"
    BATCH_IMPORT = "batch_import"


@dataclass
class PoolConfiguration:
    """Configuration for specialized connection pools."""
    pool_type: SpecializedPoolType
    min_connections: int
    max_connections: int
    connection_timeout: float = 30.0
    query_timeout: float = 60.0
    idle_timeout: float = 300.0
    max_lifetime: float = 3600.0
    health_check_interval: int = 30
    failover_threshold: int = 3
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_time: int = 60
    enable_prepared_statements: bool = True
    enable_connection_validation: bool = True
    enable_performance_monitoring: bool = True
    max_query_history: int = 1000
    slow_query_threshold_ms: float = 100.0


@dataclass
class PoolMetrics:
    """Comprehensive metrics for pool monitoring."""
    pool_name: str
    pool_type: SpecializedPoolType
    
    # Connection metrics
    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    max_connections: int = 0
    connection_utilization_percent: float = 0.0
    
    # Performance metrics
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    slow_queries: int = 0
    avg_query_time_ms: float = 0.0
    min_query_time_ms: float = 0.0
    max_query_time_ms: float = 0.0
    p95_query_time_ms: float = 0.0
    
    # Health metrics
    health_status: PoolHealth = PoolHealth.HEALTHY
    last_health_check: datetime = field(default_factory=datetime.utcnow)
    consecutive_failures: int = 0
    circuit_breaker_open: bool = False
    circuit_breaker_failures: int = 0
    
    # System metrics
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    
    # Error metrics
    connection_errors: int = 0
    timeout_errors: int = 0
    pool_exhaustion_events: int = 0
    
    # Throughput metrics
    queries_per_second: float = 0.0
    peak_qps: float = 0.0
    
    last_updated: datetime = field(default_factory=datetime.utcnow)


class SpecializedConnectionPool:
    """
    Specialized connection pool optimized for specific workload types.
    Implements health monitoring, circuit breaker, and performance optimization.
    """
    
    def __init__(self, config: PoolConfiguration, database_url: str):
        self.config = config
        self.database_url = database_url
        self.pool_name = f"velro_{config.pool_type.value}"
        
        # Pool state
        self.pool = None
        self.is_initialized = False
        self.is_closed = False
        
        # Metrics and monitoring
        self.metrics = PoolMetrics(
            pool_name=self.pool_name,
            pool_type=config.pool_type,
            max_connections=config.max_connections
        )
        
        # Performance tracking
        self.query_history = deque(maxlen=config.max_query_history)
        self.query_times = deque(maxlen=1000)
        self.connection_lease_times = {}
        
        # Health monitoring
        self.last_health_check = time.time()
        self.health_check_lock = threading.Lock()
        
        # Circuit breaker
        self.circuit_breaker_last_failure = 0
        self.circuit_breaker_half_open_time = 0
        
        # Failover system
        self.backup_pools = []
        self.failover_active = False
        
        # Locks for thread safety
        self.metrics_lock = threading.RLock()
        self.pool_lock = threading.RLock()
        
        logger.info(f"🏗️ Initialized {self.pool_name} pool config: {config.min_connections}-{config.max_connections} connections")
    
    async def initialize(self) -> None:
        """Initialize the specialized connection pool."""
        if self.is_initialized:
            return
            
        try:
            with self.pool_lock:
                if self.is_initialized:
                    return
                
                logger.info(f"🔄 Initializing {self.pool_name}...")
                
                # Import asyncpg here to avoid circular imports
                import asyncpg
                
                # Get specialized pool configuration
                pool_config = self._get_specialized_pool_config()
                
                # Create connection pool
                self.pool = await asyncpg.create_pool(
                    dsn=self.database_url,
                    min_size=self.config.min_connections,
                    max_size=self.config.max_connections,
                    command_timeout=self.config.query_timeout,
                    setup=self._setup_connection,
                    init=self._init_connection,
                    **pool_config
                )
                
                # Warm up the pool
                await self._warm_up_pool()
                
                # Start health monitoring
                asyncio.create_task(self._health_monitor_loop())
                
                # Start metrics collection
                asyncio.create_task(self._metrics_collection_loop())
                
                self.is_initialized = True
                self.metrics.health_status = PoolHealth.HEALTHY
                
                logger.info(f"✅ {self.pool_name} initialized successfully")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize {self.pool_name}: {e}")
            self.metrics.health_status = PoolHealth.UNAVAILABLE
            raise
    
    def _get_specialized_pool_config(self) -> Dict[str, Any]:
        """Get configuration optimized for specific pool type."""
        base_config = {
            "max_inactive_connection_lifetime": self.config.max_lifetime,
            "max_queries": 50000,  # Queries per connection before recycling
            "max_cached_statement_lifetime": 300,  # 5 minutes
        }
        
        # Specialized configurations per pool type
        if self.config.pool_type == SpecializedPoolType.AUTH:
            # Auth pool: Fast, frequent queries with low latency requirements
            base_config.update({
                "server_settings": {
                    "application_name": f"{self.pool_name}_auth",
                    "statement_timeout": "15s",  # Quick auth queries
                    "idle_in_transaction_session_timeout": "30s",
                    "work_mem": "4MB",  # Small working memory for simple auth queries
                    "shared_preload_libraries": "pg_stat_statements",
                    "tcp_keepalives_idle": "120",
                    "tcp_keepalives_interval": "15",
                    "tcp_keepalives_count": "3"
                }
            })
            
        elif self.config.pool_type == SpecializedPoolType.READ:
            # Read pool: Complex queries, larger working memory
            base_config.update({
                "server_settings": {
                    "application_name": f"{self.pool_name}_read",
                    "statement_timeout": "60s",
                    "work_mem": "16MB",  # Larger memory for complex reads
                    "effective_cache_size": "512MB",
                    "random_page_cost": "1.1",  # SSD optimization
                    "seq_page_cost": "1.0",
                    "enable_hashjoin": "on",
                    "enable_mergejoin": "on"
                }
            })
            
        elif self.config.pool_type == SpecializedPoolType.WRITE:
            # Write pool: ACID compliance, durability focus
            base_config.update({
                "server_settings": {
                    "application_name": f"{self.pool_name}_write",
                    "statement_timeout": "120s",
                    "synchronous_commit": "on",
                    "wal_level": "replica",
                    "fsync": "on",
                    "full_page_writes": "on",
                    "checkpoint_completion_target": "0.9",
                    "work_mem": "8MB"
                }
            })
            
        elif self.config.pool_type == SpecializedPoolType.ANALYTICS:
            # Analytics pool: Large queries, high memory
            base_config.update({
                "server_settings": {
                    "application_name": f"{self.pool_name}_analytics",
                    "statement_timeout": "300s",  # 5 minutes for complex analytics
                    "work_mem": "64MB",  # Large memory for analytics
                    "maintenance_work_mem": "128MB",
                    "effective_cache_size": "1GB",
                    "enable_seqscan": "on",  # Allow sequential scans for analytics
                    "enable_hashagg": "on",
                    "hash_mem_multiplier": "2.0"
                }
            })
            
        elif self.config.pool_type == SpecializedPoolType.ADMIN:
            # Admin pool: DDL operations, maintenance
            base_config.update({
                "server_settings": {
                    "application_name": f"{self.pool_name}_admin",
                    "statement_timeout": "600s",  # 10 minutes for admin operations
                    "lock_timeout": "30s",
                    "maintenance_work_mem": "256MB",
                    "work_mem": "32MB",
                    "enable_seqscan": "on",
                    "log_statement": "ddl"
                }
            })
            
        elif self.config.pool_type == SpecializedPoolType.BATCH:
            # Batch pool: Bulk operations, high throughput
            base_config.update({
                "server_settings": {
                    "application_name": f"{self.pool_name}_batch",
                    "statement_timeout": "1800s",  # 30 minutes for batch operations
                    "work_mem": "32MB",
                    "maintenance_work_mem": "128MB",
                    "checkpoint_completion_target": "0.7",
                    "synchronous_commit": "off",  # Performance over durability for batch
                    "wal_buffers": "16MB",
                    "commit_delay": "100000"  # 100ms commit delay for batching
                }
            })
        
        return base_config
    
    async def _setup_connection(self, connection) -> None:
        """Setup connection with pool-specific optimizations."""
        # Set connection-level settings
        await connection.execute(f"SET application_name = '{self.pool_name}'")
        
        # Pool-specific setup
        if self.config.pool_type == SpecializedPoolType.AUTH:
            # Optimize for fast auth queries
            await connection.execute("SET enable_indexscan = on")
            await connection.execute("SET enable_bitmapscan = on")
            await connection.execute("SET enable_hashjoin = off")  # Prefer nested loops for small auth tables
            
        elif self.config.pool_type == SpecializedPoolType.READ:
            # Optimize for complex read queries
            await connection.execute("SET enable_seqscan = off")  # Prefer indexes for reads
            await connection.execute("SET enable_indexonlyscan = on")
            await connection.execute("SET enable_hashjoin = on")
            
        elif self.config.pool_type == SpecializedPoolType.ANALYTICS:
            # Optimize for analytics workload
            await connection.execute("SET enable_seqscan = on")  # Allow seq scans
            await connection.execute("SET enable_hashagg = on")
            await connection.execute("SET enable_sort = on")
    
    async def _init_connection(self, connection) -> None:
        """Initialize connection with custom settings."""
        # Set up UUID handling
        await connection.set_type_codec(
            'uuid',
            encoder=str,
            decoder=str,
            schema='pg_catalog'
        )
        
        # Set up JSON handling
        await connection.set_type_codec(
            'json',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
        
        await connection.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
    
    async def _warm_up_pool(self) -> None:
        """Pre-warm the connection pool."""
        try:
            warm_up_count = min(self.config.min_connections, 3)
            connections = []
            
            for _ in range(warm_up_count):
                conn = await self.pool.acquire()
                # Test connection with pool-appropriate query
                if self.config.pool_type == SpecializedPoolType.AUTH:
                    await conn.execute("SELECT 1 as auth_test")
                elif self.config.pool_type == SpecializedPoolType.ANALYTICS:
                    await conn.execute("SELECT COUNT(*) as analytics_test FROM information_schema.tables")
                else:
                    await conn.execute("SELECT 1 as pool_test")
                connections.append(conn)
            
            # Release all connections
            for conn in connections:
                await self.pool.release(conn)
            
            logger.info(f"🔥 Pre-warmed {warm_up_count} connections for {self.pool_name}")
            
        except Exception as e:
            logger.warning(f"⚠️ Pool warm-up failed for {self.pool_name}: {e}")
    
    @asynccontextmanager
    async def acquire_connection(self, timeout: Optional[float] = None) -> AsyncContextManager:
        """Acquire a connection with comprehensive monitoring."""
        if not self.is_initialized:
            await self.initialize()
        
        if self._is_circuit_breaker_open():
            raise Exception(f"Circuit breaker open for {self.pool_name}")
        
        connection = None
        start_time = time.time()
        connection_id = None
        
        try:
            # Acquire connection with timeout
            connection = await self.pool.acquire(
                timeout=timeout or self.config.connection_timeout
            )
            connection_id = id(connection)
            
            # Track connection lease
            self.connection_lease_times[connection_id] = start_time
            
            # Update metrics
            with self.metrics_lock:
                self.metrics.active_connections += 1
                self._update_connection_metrics()
            
            yield connection
            
        except asyncio.TimeoutError:
            with self.metrics_lock:
                self.metrics.timeout_errors += 1
                self.metrics.pool_exhaustion_events += 1
            self._handle_circuit_breaker_failure()
            raise Exception(f"Connection timeout for {self.pool_name} after {timeout or self.config.connection_timeout}s")
            
        except Exception as e:
            with self.metrics_lock:
                self.metrics.connection_errors += 1
            self._handle_circuit_breaker_failure()
            logger.error(f"❌ Connection acquisition failed for {self.pool_name}: {e}")
            raise
            
        finally:
            if connection:
                try:
                    # Calculate connection usage time
                    if connection_id in self.connection_lease_times:
                        usage_time = time.time() - self.connection_lease_times[connection_id]
                        del self.connection_lease_times[connection_id]
                        
                        # Check for connection leaks
                        if usage_time > 300:  # 5 minutes
                            logger.warning(f"🔍 Long connection lease detected in {self.pool_name}: {usage_time:.2f}s")
                    
                    await self.pool.release(connection)
                    
                    # Update metrics
                    with self.metrics_lock:
                        self.metrics.active_connections = max(0, self.metrics.active_connections - 1)
                        self._update_connection_metrics()
                    
                except Exception as e:
                    logger.error(f"❌ Error releasing connection in {self.pool_name}: {e}")
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open."""
        if not self.metrics.circuit_breaker_open:
            return False
        
        # Check if recovery time has passed
        if time.time() - self.circuit_breaker_last_failure > self.config.circuit_breaker_recovery_time:
            # Enter half-open state
            if self.circuit_breaker_half_open_time == 0:
                self.circuit_breaker_half_open_time = time.time()
                self.metrics.health_status = PoolHealth.RECOVERING
                logger.info(f"🔄 Circuit breaker entering half-open state for {self.pool_name}")
                return False
            
            # If we've been in half-open for 30 seconds without failures, close circuit breaker
            if time.time() - self.circuit_breaker_half_open_time > 30:
                self._reset_circuit_breaker()
                return False
        
        return True
    
    def _handle_circuit_breaker_failure(self) -> None:
        """Handle circuit breaker failure."""
        with self.metrics_lock:
            self.metrics.circuit_breaker_failures += 1
            self.circuit_breaker_last_failure = time.time()
            self.circuit_breaker_half_open_time = 0
            
            if self.metrics.circuit_breaker_failures >= self.config.circuit_breaker_threshold:
                self.metrics.circuit_breaker_open = True
                self.metrics.health_status = PoolHealth.CRITICAL
                logger.warning(f"🚨 Circuit breaker opened for {self.pool_name} (failures: {self.metrics.circuit_breaker_failures})")
    
    def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker to closed state."""
        with self.metrics_lock:
            self.metrics.circuit_breaker_open = False
            self.metrics.circuit_breaker_failures = 0
            self.circuit_breaker_last_failure = 0
            self.circuit_breaker_half_open_time = 0
            self.metrics.health_status = PoolHealth.HEALTHY
            logger.info(f"✅ Circuit breaker reset for {self.pool_name}")
    
    def _update_connection_metrics(self) -> None:
        """Update connection-related metrics."""
        if self.pool:
            total_size = getattr(self.pool, '_maxsize', self.config.max_connections)
            self.metrics.total_connections = total_size
            self.metrics.idle_connections = total_size - self.metrics.active_connections
            self.metrics.connection_utilization_percent = (
                (self.metrics.active_connections / total_size * 100) if total_size > 0 else 0
            )
    
    async def execute_query(
        self, 
        query: str, 
        *args, 
        timeout: Optional[float] = None,
        query_type: Optional[QueryType] = None
    ) -> Any:
        """Execute query with comprehensive monitoring and optimization."""
        start_time = time.time()
        query_hash = hash(query[:200])  # First 200 chars for identification
        
        try:
            async with self.acquire_connection(timeout=timeout) as conn:
                # Execute query with timeout
                if self.config.enable_prepared_statements:
                    result = await conn.fetch(
                        query, *args, 
                        timeout=timeout or self.config.query_timeout
                    )
                else:
                    result = await conn.fetch(query, *args)
                
                # Track successful query
                execution_time = time.time() - start_time
                self._track_query_performance(query, execution_time, True, query_type)
                
                return result
                
        except Exception as e:
            execution_time = time.time() - start_time
            self._track_query_performance(query, execution_time, False, query_type)
            logger.error(f"❌ Query execution failed in {self.pool_name}: {e}")
            raise
    
    def _track_query_performance(
        self, 
        query: str, 
        execution_time: float, 
        success: bool,
        query_type: Optional[QueryType] = None
    ) -> None:
        """Track query performance metrics."""
        execution_time_ms = execution_time * 1000
        
        with self.metrics_lock:
            # Update query counts
            self.metrics.total_queries += 1
            if success:
                self.metrics.successful_queries += 1
            else:
                self.metrics.failed_queries += 1
            
            # Track slow queries
            if execution_time_ms > self.config.slow_query_threshold_ms:
                self.metrics.slow_queries += 1
                logger.warning(f"🐌 Slow query in {self.pool_name}: {execution_time_ms:.2f}ms")
            
            # Update timing metrics
            self.query_times.append(execution_time_ms)
            
            # Calculate percentiles and averages
            if len(self.query_times) > 0:
                sorted_times = sorted(self.query_times)
                self.metrics.avg_query_time_ms = sum(sorted_times) / len(sorted_times)
                self.metrics.min_query_time_ms = min(sorted_times)
                self.metrics.max_query_time_ms = max(sorted_times)
                
                # Calculate P95
                p95_index = int(len(sorted_times) * 0.95)
                if p95_index < len(sorted_times):
                    self.metrics.p95_query_time_ms = sorted_times[p95_index]
            
            # Store query history
            self.query_history.append({
                'timestamp': time.time(),
                'query_hash': hash(query[:100]),
                'execution_time_ms': execution_time_ms,
                'success': success,
                'query_type': query_type.value if query_type else 'unknown'
            })
            
            self.metrics.last_updated = datetime.utcnow()
    
    async def _health_monitor_loop(self) -> None:
        """Continuous health monitoring loop."""
        while not self.is_closed:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Health monitoring error for {self.pool_name}: {e}")
    
    async def _perform_health_check(self) -> None:
        """Comprehensive health check."""
        start_time = time.time()
        
        try:
            # Test connection and query
            async with self.acquire_connection(timeout=5.0) as conn:
                await conn.execute("SELECT 1 as health_check")
            
            health_check_time = (time.time() - start_time) * 1000
            
            with self.metrics_lock:
                # Reset consecutive failures on successful health check
                self.metrics.consecutive_failures = 0
                
                # Determine health status based on performance
                if health_check_time > 5000:  # 5 seconds
                    self.metrics.health_status = PoolHealth.CRITICAL
                elif health_check_time > 1000:  # 1 second
                    self.metrics.health_status = PoolHealth.DEGRADED
                elif self.metrics.circuit_breaker_open:
                    self.metrics.health_status = PoolHealth.CRITICAL
                else:
                    self.metrics.health_status = PoolHealth.HEALTHY
                
                self.metrics.last_health_check = datetime.utcnow()
            
            self.last_health_check = time.time()
            
        except Exception as e:
            with self.metrics_lock:
                self.metrics.consecutive_failures += 1
                
                if self.metrics.consecutive_failures >= self.config.failover_threshold:
                    self.metrics.health_status = PoolHealth.UNAVAILABLE
                else:
                    self.metrics.health_status = PoolHealth.CRITICAL
                
            logger.error(f"❌ Health check failed for {self.pool_name}: {e}")
    
    async def _metrics_collection_loop(self) -> None:
        """Collect system and performance metrics."""
        while not self.is_closed:
            try:
                await asyncio.sleep(60)  # Collect metrics every minute
                await self._collect_system_metrics()
                await self._calculate_throughput_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Metrics collection error for {self.pool_name}: {e}")
    
    async def _collect_system_metrics(self) -> None:
        """Collect system resource metrics."""
        try:
            process = psutil.Process()
            
            with self.metrics_lock:
                self.metrics.cpu_usage_percent = process.cpu_percent()
                self.metrics.memory_usage_mb = process.memory_info().rss / 1024 / 1024
                
                # Update connection metrics
                self._update_connection_metrics()
                
        except Exception as e:
            logger.error(f"❌ System metrics collection failed for {self.pool_name}: {e}")
    
    async def _calculate_throughput_metrics(self) -> None:
        """Calculate throughput and performance metrics."""
        try:
            with self.metrics_lock:
                # Calculate QPS (queries per second)
                current_time = time.time()
                recent_queries = [
                    q for q in self.query_history 
                    if current_time - q['timestamp'] <= 60  # Last minute
                ]
                
                self.metrics.queries_per_second = len(recent_queries) / 60.0
                
                # Update peak QPS
                if self.metrics.queries_per_second > self.metrics.peak_qps:
                    self.metrics.peak_qps = self.metrics.queries_per_second
                
        except Exception as e:
            logger.error(f"❌ Throughput calculation failed for {self.pool_name}: {e}")
    
    async def get_detailed_metrics(self) -> Dict[str, Any]:
        """Get comprehensive pool metrics."""
        with self.metrics_lock:
            # Calculate additional metrics
            success_rate = (
                (self.metrics.successful_queries / max(self.metrics.total_queries, 1)) * 100
                if self.metrics.total_queries > 0 else 100.0
            )
            
            slow_query_rate = (
                (self.metrics.slow_queries / max(self.metrics.total_queries, 1)) * 100
                if self.metrics.total_queries > 0 else 0.0
            )
            
            return {
                "pool_name": self.pool_name,
                "pool_type": self.config.pool_type.value,
                "health_status": self.metrics.health_status.value,
                "last_health_check": self.metrics.last_health_check.isoformat(),
                
                # Connection metrics
                "connections": {
                    "active": self.metrics.active_connections,
                    "idle": self.metrics.idle_connections,
                    "total": self.metrics.total_connections,
                    "max": self.metrics.max_connections,
                    "utilization_percent": round(self.metrics.connection_utilization_percent, 2),
                    "min_configured": self.config.min_connections,
                    "max_configured": self.config.max_connections
                },
                
                # Performance metrics
                "performance": {
                    "total_queries": self.metrics.total_queries,
                    "successful_queries": self.metrics.successful_queries,
                    "failed_queries": self.metrics.failed_queries,
                    "success_rate_percent": round(success_rate, 2),
                    "queries_per_second": round(self.metrics.queries_per_second, 2),
                    "peak_qps": round(self.metrics.peak_qps, 2),
                    
                    # Timing metrics
                    "avg_query_time_ms": round(self.metrics.avg_query_time_ms, 2),
                    "min_query_time_ms": round(self.metrics.min_query_time_ms, 2),
                    "max_query_time_ms": round(self.metrics.max_query_time_ms, 2),
                    "p95_query_time_ms": round(self.metrics.p95_query_time_ms, 2),
                    
                    # Slow queries
                    "slow_queries": self.metrics.slow_queries,
                    "slow_query_rate_percent": round(slow_query_rate, 2),
                    "slow_query_threshold_ms": self.config.slow_query_threshold_ms
                },
                
                # Error metrics
                "errors": {
                    "connection_errors": self.metrics.connection_errors,
                    "timeout_errors": self.metrics.timeout_errors,
                    "pool_exhaustion_events": self.metrics.pool_exhaustion_events,
                    "consecutive_failures": self.metrics.consecutive_failures,
                    "circuit_breaker_open": self.metrics.circuit_breaker_open,
                    "circuit_breaker_failures": self.metrics.circuit_breaker_failures
                },
                
                # System metrics
                "system": {
                    "cpu_usage_percent": round(self.metrics.cpu_usage_percent, 2),
                    "memory_usage_mb": round(self.metrics.memory_usage_mb, 2)
                },
                
                # Configuration
                "configuration": {
                    "connection_timeout": self.config.connection_timeout,
                    "query_timeout": self.config.query_timeout,
                    "health_check_interval": self.config.health_check_interval,
                    "circuit_breaker_threshold": self.config.circuit_breaker_threshold,
                    "enable_prepared_statements": self.config.enable_prepared_statements
                },
                
                "last_updated": self.metrics.last_updated.isoformat()
            }
    
    async def close(self) -> None:
        """Close the connection pool gracefully."""
        if self.is_closed:
            return
            
        try:
            self.is_closed = True
            
            if self.pool:
                await self.pool.close()
                logger.info(f"✅ Closed {self.pool_name}")
            
        except Exception as e:
            logger.error(f"❌ Error closing {self.pool_name}: {e}")


class EnterpriseConnectionPoolManager:
    """
    PHASE 2: Enterprise Connection Pool Manager
    Manages 6 specialized connection pools with health monitoring, failover, and performance optimization.
    Supports 10,000+ concurrent users with 200+ total connections as per PRD requirements.
    """
    
    def __init__(self):
        self.pools: Dict[SpecializedPoolType, SpecializedConnectionPool] = {}
        self.pool_configs = self._get_default_pool_configurations()
        self.is_initialized = False
        self.monitoring_task = None
        self.performance_task = None
        
        # Failover configuration
        self.failover_enabled = True
        self.failover_pools = {
            SpecializedPoolType.AUTH: [SpecializedPoolType.READ],
            SpecializedPoolType.READ: [SpecializedPoolType.AUTH],
            SpecializedPoolType.WRITE: [SpecializedPoolType.BATCH],
            SpecializedPoolType.ANALYTICS: [SpecializedPoolType.READ],
            SpecializedPoolType.ADMIN: [SpecializedPoolType.READ],
            SpecializedPoolType.BATCH: [SpecializedPoolType.WRITE]
        }
        
        # Query routing rules
        self.query_routing_rules = self._setup_query_routing_rules()
        
        # Performance targets (PRD requirements)
        self.performance_targets = {
            "total_connections": 200,  # 200+ total connections
            "auth_pool_max_latency_ms": 50,     # Auth queries < 50ms
            "read_pool_max_latency_ms": 200,    # Read queries < 200ms
            "write_pool_max_latency_ms": 500,   # Write queries < 500ms
            "overall_success_rate": 99.9,       # 99.9% success rate
            "max_connection_utilization": 80,    # Max 80% utilization
        }
        
        logger.info("🏗️ Enterprise Connection Pool Manager initialized")
    
    def _get_default_pool_configurations(self) -> Dict[SpecializedPoolType, PoolConfiguration]:
        """Get default configurations for all 6 specialized pools."""
        return {
            # Auth Pool: High frequency, low latency (10-50 connections)
            SpecializedPoolType.AUTH: PoolConfiguration(
                pool_type=SpecializedPoolType.AUTH,
                min_connections=10,
                max_connections=50,
                connection_timeout=15.0,
                query_timeout=30.0,
                idle_timeout=120.0,
                health_check_interval=15,
                slow_query_threshold_ms=50.0,
                circuit_breaker_threshold=3
            ),
            
            # Read Pool: Complex queries, moderate latency (20-75 connections)
            SpecializedPoolType.READ: PoolConfiguration(
                pool_type=SpecializedPoolType.READ,
                min_connections=20,
                max_connections=75,
                connection_timeout=30.0,
                query_timeout=60.0,
                idle_timeout=300.0,
                health_check_interval=30,
                slow_query_threshold_ms=200.0,
                circuit_breaker_threshold=5
            ),
            
            # Write Pool: ACID compliance, durability (5-25 connections)
            SpecializedPoolType.WRITE: PoolConfiguration(
                pool_type=SpecializedPoolType.WRITE,
                min_connections=5,
                max_connections=25,
                connection_timeout=45.0,
                query_timeout=120.0,
                idle_timeout=600.0,
                health_check_interval=30,
                slow_query_threshold_ms=500.0,
                circuit_breaker_threshold=3
            ),
            
            # Analytics Pool: Heavy queries, high memory (5-20 connections)
            SpecializedPoolType.ANALYTICS: PoolConfiguration(
                pool_type=SpecializedPoolType.ANALYTICS,
                min_connections=5,
                max_connections=20,
                connection_timeout=60.0,
                query_timeout=300.0,
                idle_timeout=900.0,
                health_check_interval=60,
                slow_query_threshold_ms=1000.0,
                circuit_breaker_threshold=5
            ),
            
            # Admin Pool: DDL operations, maintenance (2-10 connections)
            SpecializedPoolType.ADMIN: PoolConfiguration(
                pool_type=SpecializedPoolType.ADMIN,
                min_connections=2,
                max_connections=10,
                connection_timeout=120.0,
                query_timeout=600.0,
                idle_timeout=1800.0,
                health_check_interval=120,
                slow_query_threshold_ms=2000.0,
                circuit_breaker_threshold=2
            ),
            
            # Batch Pool: Bulk operations, high throughput (5-30 connections)
            SpecializedPoolType.BATCH: PoolConfiguration(
                pool_type=SpecializedPoolType.BATCH,
                min_connections=5,
                max_connections=30,
                connection_timeout=90.0,
                query_timeout=1800.0,
                idle_timeout=1200.0,
                health_check_interval=60,
                slow_query_threshold_ms=5000.0,
                circuit_breaker_threshold=5
            )
        }
    
    def _setup_query_routing_rules(self) -> Dict[QueryType, SpecializedPoolType]:
        """Setup intelligent query routing rules."""
        return {
            # Auth queries → Auth pool
            QueryType.AUTH_LOGIN: SpecializedPoolType.AUTH,
            QueryType.AUTH_VERIFY: SpecializedPoolType.AUTH,
            QueryType.AUTH_PERMISSIONS: SpecializedPoolType.AUTH,
            
            # Read queries → Read pool
            QueryType.READ_USER_DATA: SpecializedPoolType.READ,
            QueryType.READ_PROJECT_DATA: SpecializedPoolType.READ,
            QueryType.READ_ANALYTICS: SpecializedPoolType.ANALYTICS,
            
            # Write queries → Write pool
            QueryType.WRITE_CREATE: SpecializedPoolType.WRITE,
            QueryType.WRITE_UPDATE: SpecializedPoolType.WRITE,
            QueryType.WRITE_DELETE: SpecializedPoolType.WRITE,
            
            # Analytics queries → Analytics pool
            QueryType.ANALYTICS_AGGREGATE: SpecializedPoolType.ANALYTICS,
            QueryType.ANALYTICS_REPORT: SpecializedPoolType.ANALYTICS,
            
            # Admin queries → Admin pool
            QueryType.ADMIN_CONFIG: SpecializedPoolType.ADMIN,
            QueryType.ADMIN_MAINTENANCE: SpecializedPoolType.ADMIN,
            
            # Batch queries → Batch pool
            QueryType.BATCH_PROCESS: SpecializedPoolType.BATCH,
            QueryType.BATCH_IMPORT: SpecializedPoolType.BATCH,
        }
    
    async def initialize(self, database_url: Optional[str] = None) -> None:
        """Initialize all 6 specialized connection pools."""
        if self.is_initialized:
            return
        
        try:
            logger.info("🚀 Initializing Enterprise Connection Pool Manager...")
            
            # Use provided URL or get from settings
            db_url = database_url or getattr(settings, 'database_url', None)
            if not db_url:
                # Fallback to Supabase URL construction
                db_url = f"postgresql://postgres:[PASSWORD]@{settings.supabase_url.replace('https://', '').replace('http://', '')}/postgres"
            
            # Initialize all 6 specialized pools
            for pool_type, config in self.pool_configs.items():
                logger.info(f"🔄 Initializing {pool_type.value} pool ({config.min_connections}-{config.max_connections} connections)...")
                
                pool = SpecializedConnectionPool(config, db_url)
                await pool.initialize()
                self.pools[pool_type] = pool
                
                logger.info(f"✅ {pool_type.value} pool initialized")
            
            # Start monitoring tasks
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            self.performance_task = asyncio.create_task(self._performance_monitoring_loop())
            
            self.is_initialized = True
            
            # Log initialization summary
            total_min = sum(config.min_connections for config in self.pool_configs.values())
            total_max = sum(config.max_connections for config in self.pool_configs.values())
            
            logger.info(f"🎉 Enterprise Connection Pool Manager initialized successfully!")
            logger.info(f"📊 Total connection capacity: {total_min}-{total_max} connections")
            logger.info(f"🎯 Performance targets: {self.performance_targets}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Enterprise Connection Pool Manager: {e}")
            raise
    
    def get_pool_for_query_type(self, query_type: QueryType) -> SpecializedConnectionPool:
        """Get the optimal pool for a specific query type."""
        pool_type = self.query_routing_rules.get(query_type, SpecializedPoolType.READ)
        pool = self.pools.get(pool_type)
        
        if not pool or pool.metrics.health_status == PoolHealth.UNAVAILABLE:
            # Failover to backup pool
            if self.failover_enabled:
                backup_pool_types = self.failover_pools.get(pool_type, [])
                for backup_type in backup_pool_types:
                    backup_pool = self.pools.get(backup_type)
                    if backup_pool and backup_pool.metrics.health_status in [PoolHealth.HEALTHY, PoolHealth.DEGRADED]:
                        logger.warning(f"⚠️ Failing over from {pool_type.value} to {backup_type.value}")
                        return backup_pool
            
            # If no healthy backup, return the original pool (it may recover)
            if pool:
                return pool
            else:
                raise Exception(f"Pool {pool_type.value} not found")
        
        return pool
    
    def get_pool_by_type(self, pool_type: SpecializedPoolType) -> Optional[SpecializedConnectionPool]:
        """Get pool by type directly."""
        return self.pools.get(pool_type)
    
    @asynccontextmanager
    async def acquire_connection(
        self, 
        pool_type: SpecializedPoolType, 
        timeout: Optional[float] = None
    ) -> AsyncContextManager:
        """Acquire connection from specific pool type."""
        if not self.is_initialized:
            await self.initialize()
        
        pool = self.get_pool_by_type(pool_type)
        if not pool:
            raise Exception(f"Pool {pool_type.value} not found")
        
        async with pool.acquire_connection(timeout=timeout) as conn:
            yield conn
    
    @asynccontextmanager 
    async def acquire_connection_for_query(
        self, 
        query_type: QueryType, 
        timeout: Optional[float] = None
    ) -> AsyncContextManager:
        """Acquire connection optimized for specific query type."""
        if not self.is_initialized:
            await self.initialize()
        
        pool = self.get_pool_for_query_type(query_type)
        async with pool.acquire_connection(timeout=timeout) as conn:
            yield conn
    
    async def execute_query(
        self,
        query: str,
        *args,
        pool_type: Optional[SpecializedPoolType] = None,
        query_type: Optional[QueryType] = None,
        timeout: Optional[float] = None
    ) -> Any:
        """Execute query using optimal pool routing."""
        if not self.is_initialized:
            await self.initialize()
        
        # Determine pool to use
        if pool_type:
            pool = self.get_pool_by_type(pool_type)
        elif query_type:
            pool = self.get_pool_for_query_type(query_type)
        else:
            # Default to read pool for unclassified queries
            pool = self.get_pool_by_type(SpecializedPoolType.READ)
        
        if not pool:
            raise Exception("No suitable pool found for query")
        
        return await pool.execute_query(query, *args, timeout=timeout, query_type=query_type)
    
    # Convenience methods for different pool types
    async def execute_auth_query(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """Execute authentication query."""
        return await self.execute_query(
            query, *args, 
            pool_type=SpecializedPoolType.AUTH, 
            query_type=QueryType.AUTH_VERIFY,
            timeout=timeout
        )
    
    async def execute_read_query(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """Execute read query."""
        return await self.execute_query(
            query, *args, 
            pool_type=SpecializedPoolType.READ,
            query_type=QueryType.READ_USER_DATA,
            timeout=timeout
        )
    
    async def execute_write_query(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """Execute write query."""
        return await self.execute_query(
            query, *args, 
            pool_type=SpecializedPoolType.WRITE,
            query_type=QueryType.WRITE_UPDATE,
            timeout=timeout
        )
    
    async def execute_analytics_query(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """Execute analytics query."""
        return await self.execute_query(
            query, *args, 
            pool_type=SpecializedPoolType.ANALYTICS,
            query_type=QueryType.ANALYTICS_AGGREGATE,
            timeout=timeout
        )
    
    async def execute_admin_query(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """Execute admin query."""
        return await self.execute_query(
            query, *args, 
            pool_type=SpecializedPoolType.ADMIN,
            query_type=QueryType.ADMIN_MAINTENANCE,
            timeout=timeout
        )
    
    async def execute_batch_query(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """Execute batch query."""
        return await self.execute_query(
            query, *args, 
            pool_type=SpecializedPoolType.BATCH,
            query_type=QueryType.BATCH_PROCESS,
            timeout=timeout
        )
    
    async def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for all pools."""
        if not self.is_initialized:
            return {"status": "not_initialized"}
        
        pool_metrics = {}
        total_connections = 0
        total_active = 0
        total_queries = 0
        healthy_pools = 0
        
        # Collect metrics from all pools
        for pool_type, pool in self.pools.items():
            metrics = await pool.get_detailed_metrics()
            pool_metrics[pool_type.value] = metrics
            
            # Aggregate totals
            total_connections += metrics['connections']['total']
            total_active += metrics['connections']['active']
            total_queries += metrics['performance']['total_queries']
            
            if metrics['health_status'] == 'healthy':
                healthy_pools += 1
        
        # Calculate overall health
        overall_health = "healthy" if healthy_pools == len(self.pools) else (
            "degraded" if healthy_pools >= len(self.pools) // 2 else "critical"
        )
        
        # Performance target compliance
        target_compliance = await self._check_performance_targets()
        
        return {
            "status": "initialized",
            "overall_health": overall_health,
            "summary": {
                "total_pools": len(self.pools),
                "healthy_pools": healthy_pools,
                "total_connections": total_connections,
                "active_connections": total_active,
                "connection_utilization_percent": round((total_active / total_connections * 100) if total_connections > 0 else 0, 2),
                "total_queries_executed": total_queries,
            },
            "performance_targets": self.performance_targets,
            "target_compliance": target_compliance,
            "pools": pool_metrics,
            "failover_configuration": {
                "enabled": self.failover_enabled,
                "failover_mappings": {k.value: [v.value for v in values] for k, values in self.failover_pools.items()}
            },
            "query_routing": {k.value: v.value for k, v in self.query_routing_rules.items()},
            "last_updated": datetime.utcnow().isoformat()
        }
    
    async def _check_performance_targets(self) -> Dict[str, Any]:
        """Check compliance with performance targets."""
        compliance = {}
        
        try:
            # Check total connections
            total_connections = sum(pool.metrics.total_connections for pool in self.pools.values())
            compliance['total_connections'] = {
                'target': self.performance_targets['total_connections'],
                'current': total_connections,
                'compliant': total_connections >= self.performance_targets['total_connections']
            }
            
            # Check auth pool latency
            auth_pool = self.pools.get(SpecializedPoolType.AUTH)
            if auth_pool:
                compliance['auth_pool_latency'] = {
                    'target_ms': self.performance_targets['auth_pool_max_latency_ms'],
                    'current_ms': round(auth_pool.metrics.avg_query_time_ms, 2),
                    'compliant': auth_pool.metrics.avg_query_time_ms <= self.performance_targets['auth_pool_max_latency_ms']
                }
            
            # Check read pool latency  
            read_pool = self.pools.get(SpecializedPoolType.READ)
            if read_pool:
                compliance['read_pool_latency'] = {
                    'target_ms': self.performance_targets['read_pool_max_latency_ms'],
                    'current_ms': round(read_pool.metrics.avg_query_time_ms, 2),
                    'compliant': read_pool.metrics.avg_query_time_ms <= self.performance_targets['read_pool_max_latency_ms']
                }
            
            # Check overall success rate
            total_queries = sum(pool.metrics.total_queries for pool in self.pools.values())
            successful_queries = sum(pool.metrics.successful_queries for pool in self.pools.values())
            success_rate = (successful_queries / max(total_queries, 1)) * 100
            
            compliance['success_rate'] = {
                'target_percent': self.performance_targets['overall_success_rate'],
                'current_percent': round(success_rate, 3),
                'compliant': success_rate >= self.performance_targets['overall_success_rate']
            }
            
            # Check connection utilization
            total_active = sum(pool.metrics.active_connections for pool in self.pools.values())
            utilization = (total_active / max(total_connections, 1)) * 100
            
            compliance['connection_utilization'] = {
                'target_percent': self.performance_targets['max_connection_utilization'],
                'current_percent': round(utilization, 2),
                'compliant': utilization <= self.performance_targets['max_connection_utilization']
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking performance targets: {e}")
            compliance['error'] = str(e)
        
        return compliance
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while True:
            try:
                await asyncio.sleep(120)  # Monitor every 2 minutes
                await self._log_pool_health()
                await self._check_failover_conditions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {e}")
    
    async def _performance_monitoring_loop(self) -> None:
        """Performance monitoring and optimization loop."""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._analyze_performance_trends()
                await self._suggest_optimizations()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Performance monitoring error: {e}")
    
    async def _log_pool_health(self) -> None:
        """Log health status of all pools."""
        try:
            unhealthy_pools = []
            for pool_type, pool in self.pools.items():
                if pool.metrics.health_status != PoolHealth.HEALTHY:
                    unhealthy_pools.append(f"{pool_type.value}: {pool.metrics.health_status.value}")
            
            if unhealthy_pools:
                logger.warning(f"⚠️ Unhealthy pools detected: {', '.join(unhealthy_pools)}")
            else:
                logger.info("✅ All connection pools healthy")
                
        except Exception as e:
            logger.error(f"❌ Error logging pool health: {e}")
    
    async def _check_failover_conditions(self) -> None:
        """Check if failover conditions are met."""
        try:
            for pool_type, pool in self.pools.items():
                if pool.metrics.health_status == PoolHealth.UNAVAILABLE:
                    logger.error(f"🚨 Pool {pool_type.value} is unavailable - failover activated")
                elif pool.metrics.connection_utilization_percent > 90:
                    logger.warning(f"⚠️ High utilization in {pool_type.value}: {pool.metrics.connection_utilization_percent:.1f}%")
                    
        except Exception as e:
            logger.error(f"❌ Error checking failover conditions: {e}")
    
    async def _analyze_performance_trends(self) -> None:
        """Analyze performance trends and patterns."""
        try:
            for pool_type, pool in self.pools.items():
                metrics = await pool.get_detailed_metrics()
                
                # Check for performance degradation
                if metrics['performance']['slow_query_rate_percent'] > 10:
                    logger.warning(f"⚠️ High slow query rate in {pool_type.value}: {metrics['performance']['slow_query_rate_percent']:.1f}%")
                
                # Check for connection leaks
                if metrics['connections']['utilization_percent'] > 80:
                    logger.warning(f"⚠️ High connection utilization in {pool_type.value}: {metrics['connections']['utilization_percent']:.1f}%")
                    
        except Exception as e:
            logger.error(f"❌ Error analyzing performance trends: {e}")
    
    async def _suggest_optimizations(self) -> None:
        """Suggest pool optimizations based on usage patterns."""
        try:
            suggestions = []
            
            for pool_type, pool in self.pools.items():
                # Check if pool needs scaling
                if pool.metrics.connection_utilization_percent > 85:
                    suggestions.append(f"Consider increasing max connections for {pool_type.value} pool")
                
                # Check for underutilized pools
                if pool.metrics.connection_utilization_percent < 20:
                    suggestions.append(f"Consider reducing min connections for {pool_type.value} pool")
                
                # Check query performance
                if pool.metrics.avg_query_time_ms > pool.config.slow_query_threshold_ms * 2:
                    suggestions.append(f"Consider query optimization for {pool_type.value} pool")
            
            if suggestions:
                logger.info(f"💡 Pool optimization suggestions: {'; '.join(suggestions)}")
                
        except Exception as e:
            logger.error(f"❌ Error generating optimization suggestions: {e}")
    
    async def close_all_pools(self) -> None:
        """Close all pools gracefully."""
        try:
            logger.info("🔄 Shutting down Enterprise Connection Pool Manager...")
            
            # Cancel monitoring tasks
            if self.monitoring_task:
                self.monitoring_task.cancel()
            if self.performance_task:
                self.performance_task.cancel()
            
            # Close all pools
            for pool_type, pool in self.pools.items():
                try:
                    await pool.close()
                except Exception as e:
                    logger.error(f"❌ Error closing {pool_type.value} pool: {e}")
            
            self.pools.clear()
            self.is_initialized = False
            
            logger.info("✅ Enterprise Connection Pool Manager shutdown complete")
            
        except Exception as e:
            logger.error(f"❌ Error during pool manager shutdown: {e}")


# Global instance
enterprise_pool_manager = EnterpriseConnectionPoolManager()


# Convenience functions for easy access
async def get_auth_connection():
    """Get connection optimized for auth operations."""
    async with enterprise_pool_manager.acquire_connection(SpecializedPoolType.AUTH) as conn:
        yield conn


async def get_read_connection():
    """Get connection optimized for read operations."""
    async with enterprise_pool_manager.acquire_connection(SpecializedPoolType.READ) as conn:
        yield conn


async def get_write_connection():
    """Get connection optimized for write operations."""
    async with enterprise_pool_manager.acquire_connection(SpecializedPoolType.WRITE) as conn:
        yield conn


async def get_analytics_connection():
    """Get connection optimized for analytics operations."""
    async with enterprise_pool_manager.acquire_connection(SpecializedPoolType.ANALYTICS) as conn:
        yield conn


async def get_admin_connection():
    """Get connection optimized for admin operations."""
    async with enterprise_pool_manager.acquire_connection(SpecializedPoolType.ADMIN) as conn:
        yield conn


async def get_batch_connection():
    """Get connection optimized for batch operations."""
    async with enterprise_pool_manager.acquire_connection(SpecializedPoolType.BATCH) as conn:
        yield conn


# Query execution convenience functions
async def execute_auth_query(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute authentication query with optimal routing."""
    return await enterprise_pool_manager.execute_auth_query(query, *args, timeout=timeout)


async def execute_read_query(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute read query with optimal routing."""
    return await enterprise_pool_manager.execute_read_query(query, *args, timeout=timeout)


async def execute_write_query(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute write query with optimal routing."""
    return await enterprise_pool_manager.execute_write_query(query, *args, timeout=timeout)


async def execute_analytics_query(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute analytics query with optimal routing."""
    return await enterprise_pool_manager.execute_analytics_query(query, *args, timeout=timeout)


async def execute_admin_query(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute admin query with optimal routing."""
    return await enterprise_pool_manager.execute_admin_query(query, *args, timeout=timeout)


async def execute_batch_query(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute batch query with optimal routing."""
    return await enterprise_pool_manager.execute_batch_query(query, *args, timeout=timeout)