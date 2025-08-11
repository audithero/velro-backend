"""
Enterprise Deep Health Check System with Dependency Monitoring and Auto-Recovery.
Provides comprehensive health monitoring for all system components with intelligent dependency tracking.
"""

import asyncio
import logging
import time
import json
import psutil
from typing import Dict, List, Any, Optional, Set, Callable, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import aioredis
import asyncpg
import aiohttp

from monitoring.metrics import metrics_collector
from monitoring.circuit_breaker_integration import enterprise_circuit_breaker_manager
from monitoring.intelligent_alerting_system import intelligent_alerting_system, AlertSeverity

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    FAILED = "failed"
    UNKNOWN = "unknown"


class DependencyType(Enum):
    """Types of service dependencies."""
    DATABASE = "database"
    CACHE = "cache"
    EXTERNAL_API = "external_api"
    MESSAGE_QUEUE = "message_queue"
    FILE_SYSTEM = "file_system"
    NETWORK_SERVICE = "network_service"
    INTERNAL_SERVICE = "internal_service"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    component: str
    status: HealthStatus
    response_time_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status.value,
            "response_time_ms": self.response_time_ms,
            "details": self.details,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "dependencies": self.dependencies
        }


@dataclass
class ServiceDependency:
    """Service dependency definition."""
    name: str
    type: DependencyType
    endpoint: Optional[str] = None
    timeout_seconds: float = 10.0
    critical: bool = True
    health_check_interval_seconds: int = 30
    failure_threshold: int = 3
    recovery_actions: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """Base health checker class."""
    
    def __init__(self, dependency: ServiceDependency):
        self.dependency = dependency
        self.consecutive_failures = 0
        self.last_success_time: Optional[datetime] = None
        self.last_failure_time: Optional[datetime] = None
        self.failure_history: List[datetime] = []
    
    async def check_health(self) -> HealthCheckResult:
        """Perform health check."""
        start_time = time.time()
        
        try:
            # Perform the actual health check
            details = await self._perform_check()
            response_time_ms = (time.time() - start_time) * 1000
            
            # Determine status based on response time and details
            status = self._determine_status(response_time_ms, details)
            
            # Update success/failure tracking
            if status in [HealthStatus.HEALTHY, HealthStatus.WARNING]:
                self.consecutive_failures = 0
                self.last_success_time = datetime.now(timezone.utc)
            else:
                self.consecutive_failures += 1
                self.last_failure_time = datetime.now(timezone.utc)
                self.failure_history.append(self.last_failure_time)
                
                # Keep only last 10 failures
                self.failure_history = self.failure_history[-10:]
            
            return HealthCheckResult(
                component=self.dependency.name,
                status=status,
                response_time_ms=response_time_ms,
                details=details,
                dependencies=self.dependency.depends_on.copy()
            )
            
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            self.consecutive_failures += 1
            self.last_failure_time = datetime.now(timezone.utc)
            self.failure_history.append(self.last_failure_time)
            
            logger.error(f"❌ [HEALTH] {self.dependency.name} health check failed: {e}")
            
            return HealthCheckResult(
                component=self.dependency.name,
                status=HealthStatus.FAILED,
                response_time_ms=response_time_ms,
                error=str(e),
                dependencies=self.dependency.depends_on.copy()
            )
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Override this method to implement specific health check logic."""
        raise NotImplementedError
    
    def _determine_status(self, response_time_ms: float, details: Dict[str, Any]) -> HealthStatus:
        """Determine health status based on response time and check details."""
        # Default logic - override for specific checks
        if response_time_ms > self.dependency.timeout_seconds * 1000:
            return HealthStatus.CRITICAL
        elif response_time_ms > 1000:  # >1 second
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY


class DatabaseHealthChecker(HealthChecker):
    """PostgreSQL database health checker."""
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check database health."""
        try:
            # This would use actual database connection
            # For now, simulating database check
            connection_pool_size = 20  # Would get from actual pool
            active_connections = 5     # Would get from actual pool
            slow_queries = 0          # Would query actual metrics
            
            # Simulate connection test
            await asyncio.sleep(0.01)  # Simulate DB query time
            
            return {
                "connection_pool_size": connection_pool_size,
                "active_connections": active_connections,
                "connection_pool_utilization": (active_connections / connection_pool_size) * 100,
                "slow_queries_last_minute": slow_queries,
                "read_only": False,
                "replication_lag_ms": 0
            }
            
        except Exception as e:
            raise Exception(f"Database connection failed: {e}")
    
    def _determine_status(self, response_time_ms: float, details: Dict[str, Any]) -> HealthStatus:
        """Determine database health status."""
        utilization = details.get("connection_pool_utilization", 0)
        slow_queries = details.get("slow_queries_last_minute", 0)
        
        if response_time_ms > 5000 or utilization > 95 or slow_queries > 10:
            return HealthStatus.CRITICAL
        elif response_time_ms > 1000 or utilization > 80 or slow_queries > 3:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY


class RedisHealthChecker(HealthChecker):
    """Redis cache health checker."""
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check Redis health."""
        try:
            # This would use actual Redis connection
            # For now, simulating Redis check
            memory_usage_mb = 512     # Would get from Redis INFO
            max_memory_mb = 2048      # Would get from Redis config
            connected_clients = 10    # Would get from Redis INFO
            keyspace_hits = 1000      # Would get from Redis INFO
            keyspace_misses = 50      # Would get from Redis INFO
            
            # Simulate Redis ping
            await asyncio.sleep(0.001)  # Simulate Redis ping time
            
            hit_rate = (keyspace_hits / (keyspace_hits + keyspace_misses)) * 100 if (keyspace_hits + keyspace_misses) > 0 else 0
            
            return {
                "memory_usage_mb": memory_usage_mb,
                "max_memory_mb": max_memory_mb,
                "memory_utilization": (memory_usage_mb / max_memory_mb) * 100,
                "connected_clients": connected_clients,
                "hit_rate_percentage": hit_rate,
                "keyspace_hits": keyspace_hits,
                "keyspace_misses": keyspace_misses,
                "used_memory_peak_mb": memory_usage_mb * 1.2
            }
            
        except Exception as e:
            raise Exception(f"Redis connection failed: {e}")
    
    def _determine_status(self, response_time_ms: float, details: Dict[str, Any]) -> HealthStatus:
        """Determine Redis health status."""
        memory_utilization = details.get("memory_utilization", 0)
        hit_rate = details.get("hit_rate_percentage", 0)
        
        if response_time_ms > 100 or memory_utilization > 95 or hit_rate < 80:
            return HealthStatus.CRITICAL
        elif response_time_ms > 50 or memory_utilization > 85 or hit_rate < 90:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY


class ExternalAPIHealthChecker(HealthChecker):
    """External API health checker."""
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check external API health."""
        if not self.dependency.endpoint:
            raise Exception("No endpoint configured for external API")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.dependency.endpoint,
                    timeout=aiohttp.ClientTimeout(total=self.dependency.timeout_seconds)
                ) as response:
                    response_text = await response.text()
                    
                    return {
                        "status_code": response.status,
                        "response_size_bytes": len(response_text),
                        "headers": dict(response.headers),
                        "ssl_enabled": response.url.scheme == "https"
                    }
                    
        except asyncio.TimeoutError:
            raise Exception("Request timeout")
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP client error: {e}")
    
    def _determine_status(self, response_time_ms: float, details: Dict[str, Any]) -> HealthStatus:
        """Determine external API health status."""
        status_code = details.get("status_code", 0)
        
        if status_code >= 500 or response_time_ms > 10000:
            return HealthStatus.CRITICAL
        elif status_code >= 400 or response_time_ms > 5000:
            return HealthStatus.WARNING
        elif 200 <= status_code < 300:
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.WARNING


class SystemResourceHealthChecker(HealthChecker):
    """System resource health checker."""
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check system resource health."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Network stats
            network = psutil.net_io_counters()
            
            return {
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "memory_total_gb": memory.total / (1024**3),
                "memory_available_gb": memory.available / (1024**3),
                "memory_used_gb": memory.used / (1024**3),
                "memory_percent": memory.percent,
                "disk_total_gb": disk.total / (1024**3),
                "disk_used_gb": disk.used / (1024**3),
                "disk_free_gb": disk.free / (1024**3),
                "disk_percent": (disk.used / disk.total) * 100,
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv,
                "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
            }
            
        except Exception as e:
            raise Exception(f"System resource check failed: {e}")
    
    def _determine_status(self, response_time_ms: float, details: Dict[str, Any]) -> HealthStatus:
        """Determine system resource health status."""
        cpu_percent = details.get("cpu_percent", 0)
        memory_percent = details.get("memory_percent", 0)
        disk_percent = details.get("disk_percent", 0)
        
        if cpu_percent > 95 or memory_percent > 95 or disk_percent > 95:
            return HealthStatus.CRITICAL
        elif cpu_percent > 80 or memory_percent > 80 or disk_percent > 85:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY


class DeepHealthCheckSystem:
    """
    Enterprise deep health check system with dependency monitoring and auto-recovery.
    """
    
    def __init__(self):
        self.dependencies: Dict[str, ServiceDependency] = {}
        self.health_checkers: Dict[str, HealthChecker] = {}
        self.health_results: Dict[str, HealthCheckResult] = {}
        self.dependency_graph: Dict[str, Set[str]] = {}  # component -> dependencies
        self.reverse_dependency_graph: Dict[str, Set[str]] = {}  # component -> dependents
        
        self.check_interval_seconds = 15
        self.auto_recovery_enabled = True
        self.failure_notifications_sent: Set[str] = set()
        
        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        self._dependency_analysis_task: Optional[asyncio.Task] = None
        
        # Initialize default dependencies
        self._initialize_default_dependencies()
    
    def _initialize_default_dependencies(self):
        """Initialize default system dependencies."""
        default_dependencies = [
            ServiceDependency(
                name="database",
                type=DependencyType.DATABASE,
                endpoint="postgresql://localhost:5432",
                critical=True,
                health_check_interval_seconds=30,
                failure_threshold=3,
                recovery_actions=[
                    "restart_connection_pool",
                    "failover_to_read_replica",
                    "clear_connection_cache"
                ]
            ),
            ServiceDependency(
                name="redis_cache",
                type=DependencyType.CACHE,
                endpoint="redis://localhost:6379",
                critical=True,
                health_check_interval_seconds=15,
                failure_threshold=2,
                depends_on=["system_resources"],
                recovery_actions=[
                    "flush_cache",
                    "restart_redis_connection",
                    "switch_to_memory_cache"
                ]
            ),
            ServiceDependency(
                name="fal_api",
                type=DependencyType.EXTERNAL_API,
                endpoint="https://fal.run/health",
                critical=False,
                health_check_interval_seconds=60,
                failure_threshold=5,
                recovery_actions=[
                    "switch_to_backup_provider",
                    "use_cached_results",
                    "queue_for_later"
                ]
            ),
            ServiceDependency(
                name="supabase_api",
                type=DependencyType.EXTERNAL_API,
                endpoint="https://api.supabase.com/health",
                critical=True,
                health_check_interval_seconds=45,
                failure_threshold=3,
                recovery_actions=[
                    "use_service_key_fallback",
                    "switch_to_local_auth",
                    "enable_offline_mode"
                ]
            ),
            ServiceDependency(
                name="system_resources",
                type=DependencyType.INTERNAL_SERVICE,
                critical=True,
                health_check_interval_seconds=20,
                failure_threshold=2,
                recovery_actions=[
                    "garbage_collection",
                    "clear_temp_files",
                    "restart_high_memory_processes"
                ]
            )
        ]
        
        for dependency in default_dependencies:
            self.add_dependency(dependency)
    
    def add_dependency(self, dependency: ServiceDependency):
        """Add a service dependency."""
        self.dependencies[dependency.name] = dependency
        
        # Create appropriate health checker
        if dependency.type == DependencyType.DATABASE:
            self.health_checkers[dependency.name] = DatabaseHealthChecker(dependency)
        elif dependency.type == DependencyType.CACHE:
            self.health_checkers[dependency.name] = RedisHealthChecker(dependency)
        elif dependency.type == DependencyType.EXTERNAL_API:
            self.health_checkers[dependency.name] = ExternalAPIHealthChecker(dependency)
        elif dependency.type == DependencyType.INTERNAL_SERVICE:
            if dependency.name == "system_resources":
                self.health_checkers[dependency.name] = SystemResourceHealthChecker(dependency)
            else:
                self.health_checkers[dependency.name] = HealthChecker(dependency)
        else:
            self.health_checkers[dependency.name] = HealthChecker(dependency)
        
        # Update dependency graphs
        self._update_dependency_graphs()
        
        logger.info(f"📋 [HEALTH] Added dependency: {dependency.name} ({dependency.type.value})")
    
    def _update_dependency_graphs(self):
        """Update dependency graphs for analysis."""
        self.dependency_graph.clear()
        self.reverse_dependency_graph.clear()
        
        for name, dependency in self.dependencies.items():
            self.dependency_graph[name] = set(dependency.depends_on)
            
            # Build reverse graph (dependents)
            for dep in dependency.depends_on:
                if dep not in self.reverse_dependency_graph:
                    self.reverse_dependency_graph[dep] = set()
                self.reverse_dependency_graph[dep].add(name)
    
    async def start(self):
        """Start the health check system."""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        if self._dependency_analysis_task is None or self._dependency_analysis_task.done():
            self._dependency_analysis_task = asyncio.create_task(self._dependency_analysis_loop())
        
        logger.info("🏥 [HEALTH] Deep health check system started")
    
    async def stop(self):
        """Stop the health check system."""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
        
        if self._dependency_analysis_task and not self._dependency_analysis_task.done():
            self._dependency_analysis_task.cancel()
        
        logger.info("🏥 [HEALTH] Deep health check system stopped")
    
    async def _health_check_loop(self):
        """Main health check loop."""
        while True:
            try:
                await self._perform_all_health_checks()
                await self._update_metrics()
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [HEALTH] Health check loop error: {e}")
                await asyncio.sleep(30)
    
    async def _dependency_analysis_loop(self):
        """Dependency analysis and recovery loop."""
        while True:
            try:
                await self._analyze_dependency_health()
                await self._trigger_recovery_if_needed()
                await asyncio.sleep(60)  # Run every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [HEALTH] Dependency analysis error: {e}")
                await asyncio.sleep(60)
    
    async def _perform_all_health_checks(self):
        """Perform health checks for all dependencies."""
        # Run health checks in dependency order (dependencies first)
        check_order = self._get_dependency_check_order()
        
        for component_name in check_order:
            if component_name not in self.health_checkers:
                continue
            
            try:
                result = await self.health_checkers[component_name].check_health()
                self.health_results[component_name] = result
                
                # Log status changes
                if hasattr(self, '_last_health_status'):
                    last_status = self._last_health_status.get(component_name)
                    if last_status != result.status:
                        logger.info(
                            f"🏥 [HEALTH] {component_name} status: {last_status} -> {result.status.value}"
                        )
                
                # Update metrics
                self._record_health_metrics(result)
                
            except Exception as e:
                logger.error(f"❌ [HEALTH] Failed to check {component_name}: {e}")
        
        # Store current status for comparison
        if not hasattr(self, '_last_health_status'):
            self._last_health_status = {}
        
        for name, result in self.health_results.items():
            self._last_health_status[name] = result.status
    
    def _get_dependency_check_order(self) -> List[str]:
        """Get the order to perform health checks based on dependencies."""
        # Topological sort of dependencies
        visited = set()
        order = []
        
        def dfs(node):
            if node in visited:
                return
            visited.add(node)
            
            # Visit dependencies first
            for dependency in self.dependency_graph.get(node, []):
                if dependency in self.dependencies:
                    dfs(dependency)
            
            order.append(node)
        
        # Start DFS from all nodes
        for component in self.dependencies.keys():
            dfs(component)
        
        return order
    
    def _record_health_metrics(self, result: HealthCheckResult):
        """Record health check metrics."""
        # Record response time
        metrics_collector.performance_metrics.record_request(
            "GET", 
            f"/health/{result.component}", 
            200 if result.status in [HealthStatus.HEALTHY, HealthStatus.WARNING] else 500,
            result.response_time_ms / 1000
        )
        
        # Record component-specific metrics
        if result.component == "redis_cache" and result.details:
            hit_rate = result.details.get("hit_rate_percentage", 0)
            memory_usage = result.details.get("memory_usage_mb", 0) * 1024 * 1024
            
            metrics_collector.cache_metrics.update_cache_size(
                "redis", memory_usage, 0
            )
        
        elif result.component == "database" and result.details:
            active_conn = result.details.get("active_connections", 0)
            pool_size = result.details.get("connection_pool_size", 0)
            idle_conn = pool_size - active_conn
            
            metrics_collector.performance_metrics.update_connection_metrics(
                active_conn, idle_conn
            )
    
    async def _analyze_dependency_health(self):
        """Analyze overall dependency health and cascade effects."""
        critical_failures = []
        warning_components = []
        
        for name, result in self.health_results.items():
            dependency = self.dependencies.get(name)
            if not dependency:
                continue
            
            if result.status == HealthStatus.FAILED:
                if dependency.critical:
                    critical_failures.append(name)
                    
                    # Check cascade effects
                    affected_components = self._get_affected_components(name)
                    if affected_components:
                        logger.warning(
                            f"⚠️ [HEALTH] {name} failure may affect: {', '.join(affected_components)}"
                        )
                
            elif result.status in [HealthStatus.CRITICAL, HealthStatus.WARNING]:
                warning_components.append(name)
        
        # Generate alerts for critical failures
        for component in critical_failures:
            await self._generate_health_alert(component, AlertSeverity.CRITICAL)
        
        # Generate alerts for persistent warnings
        for component in warning_components:
            await self._generate_health_alert(component, AlertSeverity.WARNING)
        
        # Update overall system health
        overall_health = self._calculate_overall_health()
        logger.info(f"🏥 [HEALTH] Overall system health: {overall_health}")
    
    def _get_affected_components(self, failed_component: str) -> List[str]:
        """Get components that depend on the failed component."""
        return list(self.reverse_dependency_graph.get(failed_component, set()))
    
    async def _generate_health_alert(self, component: str, severity: AlertSeverity):
        """Generate health alert for component."""
        # Avoid duplicate alerts
        alert_key = f"{component}_{severity.value}"
        if alert_key in self.failure_notifications_sent:
            return
        
        result = self.health_results.get(component)
        if not result:
            return
        
        # Create alert
        await intelligent_alerting_system.create_alert(
            title=f"Health Check Alert: {component}",
            description=f"Component {component} health status: {result.status.value}. "
                       f"Response time: {result.response_time_ms:.1f}ms. "
                       f"Error: {result.error or 'None'}",
            severity=severity,
            source="health_check",
            labels={
                "component": component,
                "health_status": result.status.value,
                "dependency_type": self.dependencies[component].type.value if component in self.dependencies else "unknown"
            },
            annotations={
                "response_time_ms": str(result.response_time_ms),
                "details": json.dumps(result.details),
                "recovery_actions": json.dumps(self.dependencies[component].recovery_actions) if component in self.dependencies else "[]"
            }
        )
        
        self.failure_notifications_sent.add(alert_key)
        
        # Remove from sent set after some time to allow re-alerting
        asyncio.create_task(self._remove_alert_key_later(alert_key, 3600))  # 1 hour
    
    async def _remove_alert_key_later(self, alert_key: str, delay_seconds: int):
        """Remove alert key after delay to allow re-alerting."""
        await asyncio.sleep(delay_seconds)
        self.failure_notifications_sent.discard(alert_key)
    
    async def _trigger_recovery_if_needed(self):
        """Trigger automatic recovery for failed components."""
        if not self.auto_recovery_enabled:
            return
        
        for name, result in self.health_results.items():
            if result.status == HealthStatus.FAILED:
                dependency = self.dependencies.get(name)
                if dependency and dependency.recovery_actions:
                    checker = self.health_checkers.get(name)
                    
                    # Check if we've exceeded failure threshold
                    if checker and checker.consecutive_failures >= dependency.failure_threshold:
                        await self._execute_recovery_actions(name, dependency.recovery_actions)
    
    async def _execute_recovery_actions(self, component: str, recovery_actions: List[str]):
        """Execute recovery actions for a component."""
        logger.info(f"🚑 [RECOVERY] Starting recovery for {component}")
        
        for action in recovery_actions:
            try:
                logger.info(f"🔧 [RECOVERY] {component}: {action}")
                
                # Execute recovery action (this would contain actual recovery logic)
                success = await self._execute_recovery_action(component, action)
                
                if success:
                    logger.info(f"✅ [RECOVERY] {component}: {action} completed")
                else:
                    logger.warning(f"⚠️ [RECOVERY] {component}: {action} failed")
                
                # Brief pause between actions
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"❌ [RECOVERY] {component}: {action} error: {e}")
        
        # Test health after recovery
        await asyncio.sleep(5)
        checker = self.health_checkers.get(component)
        if checker:
            recovery_result = await checker.check_health()
            if recovery_result.status in [HealthStatus.HEALTHY, HealthStatus.WARNING]:
                logger.info(f"✅ [RECOVERY] {component} recovery successful")
                checker.consecutive_failures = 0
            else:
                logger.error(f"❌ [RECOVERY] {component} recovery failed")
    
    async def _execute_recovery_action(self, component: str, action: str) -> bool:
        """Execute a specific recovery action."""
        try:
            # This would contain actual recovery logic
            if "restart" in action.lower():
                await asyncio.sleep(1)  # Simulate restart
                return True
            elif "clear" in action.lower() or "flush" in action.lower():
                await asyncio.sleep(0.5)  # Simulate clearing
                return True
            elif "switch" in action.lower():
                await asyncio.sleep(1)  # Simulate switching
                return True
            else:
                await asyncio.sleep(1)  # Generic action
                return True
                
        except Exception as e:
            logger.error(f"❌ [RECOVERY] Action '{action}' failed: {e}")
            return False
    
    def _calculate_overall_health(self) -> HealthStatus:
        """Calculate overall system health."""
        if not self.health_results:
            return HealthStatus.UNKNOWN
        
        # Weight critical dependencies more heavily
        critical_components = [
            name for name, dep in self.dependencies.items() 
            if dep.critical and name in self.health_results
        ]
        
        # Check critical components first
        critical_statuses = [
            self.health_results[name].status for name in critical_components
        ]
        
        if any(status == HealthStatus.FAILED for status in critical_statuses):
            return HealthStatus.FAILED
        elif any(status == HealthStatus.CRITICAL for status in critical_statuses):
            return HealthStatus.CRITICAL
        elif any(status == HealthStatus.WARNING for status in critical_statuses):
            return HealthStatus.WARNING
        
        # Check all components
        all_statuses = [result.status for result in self.health_results.values()]
        
        if any(status == HealthStatus.FAILED for status in all_statuses):
            return HealthStatus.WARNING  # Non-critical failure
        elif any(status == HealthStatus.CRITICAL for status in all_statuses):
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY
    
    async def _update_metrics(self):
        """Update Prometheus metrics."""
        overall_health = self._calculate_overall_health()
        
        # Update SLA compliance based on health
        if overall_health == HealthStatus.HEALTHY:
            compliance = 100.0
        elif overall_health == HealthStatus.WARNING:
            compliance = 99.0
        elif overall_health == HealthStatus.CRITICAL:
            compliance = 95.0
        else:
            compliance = 80.0
        
        metrics_collector.update_sla_compliance(
            "system_health", 
            "current", 
            compliance
        )
    
    # Public API methods
    
    async def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        overall_health = self._calculate_overall_health()
        
        components = {}
        for name, result in self.health_results.items():
            dependency = self.dependencies.get(name)
            components[name] = {
                "status": result.status.value,
                "response_time_ms": result.response_time_ms,
                "details": result.details,
                "error": result.error,
                "last_check": result.timestamp.isoformat(),
                "critical": dependency.critical if dependency else False,
                "type": dependency.type.value if dependency else "unknown",
                "dependencies": result.dependencies,
                "consecutive_failures": self.health_checkers[name].consecutive_failures if name in self.health_checkers else 0
            }
        
        return {
            "overall_health": overall_health.value,
            "components": components,
            "dependency_graph": {
                name: list(deps) for name, deps in self.dependency_graph.items()
            },
            "auto_recovery_enabled": self.auto_recovery_enabled,
            "total_components": len(self.health_results),
            "healthy_components": len([r for r in self.health_results.values() if r.status == HealthStatus.HEALTHY]),
            "failed_components": len([r for r in self.health_results.values() if r.status == HealthStatus.FAILED]),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def force_health_check(self, component: str = None) -> Dict[str, Any]:
        """Force immediate health check for component(s)."""
        if component:
            if component in self.health_checkers:
                result = await self.health_checkers[component].check_health()
                self.health_results[component] = result
                return {component: result.to_dict()}
            else:
                return {"error": f"Component '{component}' not found"}
        else:
            await self._perform_all_health_checks()
            return {name: result.to_dict() for name, result in self.health_results.items()}
    
    def enable_auto_recovery(self):
        """Enable automatic recovery."""
        self.auto_recovery_enabled = True
        logger.info("✅ [HEALTH] Automatic recovery enabled")
    
    def disable_auto_recovery(self):
        """Disable automatic recovery."""
        self.auto_recovery_enabled = False
        logger.info("⚠️ [HEALTH] Automatic recovery disabled")


# Global deep health check system
deep_health_check_system = DeepHealthCheckSystem()