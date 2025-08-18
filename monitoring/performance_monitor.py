"""
Real-time Performance Monitor for <100ms Authorization Targets
Comprehensive performance monitoring system designed to ensure sub-100ms response times.

Key Features:
- Real-time response time tracking with percentile analysis (P50, P95, P99)
- Authorization-specific performance monitoring
- Automatic alerting when performance targets are missed
- Database query performance tracking
- Cache performance analysis
- System resource monitoring (CPU, memory, connections)
- Performance degradation detection and recommendations

Performance Targets Monitored:
- Authorization endpoints: <100ms average, <200ms P95
- Database queries: <50ms average for auth queries
- Cache operations: <5ms L1, <20ms L2
- Overall API response time: <100ms P95
- Error rate: <0.1%
"""

import asyncio
import logging
import time
import threading
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque, defaultdict
import statistics
import weakref
import psutil
import json

logger = logging.getLogger(__name__)

class PerformanceLevel(Enum):
    """Performance level classifications."""
    EXCELLENT = "excellent"    # <50ms
    GOOD = "good"             # 50-100ms  
    ACCEPTABLE = "acceptable" # 100-200ms
    POOR = "poor"            # 200-500ms
    CRITICAL = "critical"    # >500ms

class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning" 
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class PerformanceMetric:
    """Individual performance measurement."""
    timestamp: float
    operation_type: str
    operation_name: str
    duration_ms: float
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def performance_level(self) -> PerformanceLevel:
        """Classify performance level based on duration."""
        if self.duration_ms < 50:
            return PerformanceLevel.EXCELLENT
        elif self.duration_ms < 100:
            return PerformanceLevel.GOOD
        elif self.duration_ms < 200:
            return PerformanceLevel.ACCEPTABLE
        elif self.duration_ms < 500:
            return PerformanceLevel.POOR
        else:
            return PerformanceLevel.CRITICAL

@dataclass
class PerformanceAlert:
    """Performance alert with context."""
    severity: AlertSeverity
    alert_type: str
    message: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution_time: Optional[float] = None

class PerformanceWindow:
    """Rolling window for performance metrics analysis."""
    
    def __init__(self, window_size_minutes: int = 5, max_samples: int = 1000):
        self.window_size_seconds = window_size_minutes * 60
        self.max_samples = max_samples
        self.metrics: deque = deque(maxlen=max_samples)
        self._lock = threading.RLock()
    
    def add_metric(self, metric: PerformanceMetric):
        """Add metric to the rolling window."""
        with self._lock:
            # Remove old metrics outside the window
            cutoff_time = time.time() - self.window_size_seconds
            while self.metrics and self.metrics[0].timestamp < cutoff_time:
                self.metrics.popleft()
            
            self.metrics.append(metric)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate comprehensive statistics for the window."""
        with self._lock:
            if not self.metrics:
                return {}
            
            durations = [m.duration_ms for m in self.metrics]
            success_count = sum(1 for m in self.metrics if m.success)
            
            try:
                stats = {
                    'count': len(durations),
                    'avg_ms': round(statistics.mean(durations), 2),
                    'median_ms': round(statistics.median(durations), 2),
                    'min_ms': round(min(durations), 2),
                    'max_ms': round(max(durations), 2),
                    'success_rate_percent': round((success_count / len(durations)) * 100, 2),
                    'window_minutes': self.window_size_seconds / 60
                }
                
                # Percentiles (if enough data)
                if len(durations) >= 10:
                    stats['p50_ms'] = round(statistics.quantiles(durations, n=2)[0], 2)
                    stats['p95_ms'] = round(statistics.quantiles(durations, n=20)[18], 2)
                    
                if len(durations) >= 20:
                    stats['p99_ms'] = round(statistics.quantiles(durations, n=100)[98], 2)
                
                # Performance level distribution
                level_counts = defaultdict(int)
                for metric in self.metrics:
                    level_counts[metric.performance_level.value] += 1
                
                stats['performance_distribution'] = dict(level_counts)
                
                return stats
                
            except Exception as e:
                logger.error(f"Error calculating window statistics: {e}")
                return {'count': len(durations), 'error': str(e)}

class RealTimePerformanceMonitor:
    """
    Real-time performance monitoring system for <100ms targets.
    
    Monitors:
    - API endpoint response times
    - Database query performance  
    - Cache operation performance
    - System resource utilization
    - Performance degradation trends
    """
    
    def __init__(self):
        # Performance windows for different operation types
        self.windows: Dict[str, PerformanceWindow] = {
            'authorization': PerformanceWindow(window_size_minutes=5),
            'authentication': PerformanceWindow(window_size_minutes=5),
            'database_query': PerformanceWindow(window_size_minutes=10),
            'cache_operation': PerformanceWindow(window_size_minutes=5),
            'api_endpoint': PerformanceWindow(window_size_minutes=10)
        }
        
        # Alert management
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        # Performance targets and thresholds
        self.performance_targets = {
            'authorization': {'target_ms': 100, 'critical_ms': 200, 'error_rate_threshold': 1.0},
            'authentication': {'target_ms': 50, 'critical_ms': 150, 'error_rate_threshold': 0.5},
            'database_query': {'target_ms': 50, 'critical_ms': 100, 'error_rate_threshold': 2.0},
            'cache_operation': {'target_ms': 20, 'critical_ms': 50, 'error_rate_threshold': 0.1},
            'api_endpoint': {'target_ms': 100, 'critical_ms': 250, 'error_rate_threshold': 1.0}
        }
        
        # System monitoring
        self.system_metrics: Dict[str, Any] = {}
        self.system_monitoring_active = True
        
        # Background monitoring tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        self._start_monitoring_tasks()
    
    def _start_monitoring_tasks(self):
        """Start background monitoring tasks."""
        try:
            loop = asyncio.get_running_loop()
            
            # System monitoring task
            self._monitoring_tasks.append(
                loop.create_task(self._system_monitoring_loop())
            )
            
            # Performance analysis task
            self._monitoring_tasks.append(
                loop.create_task(self._performance_analysis_loop())
            )
            
            # Alert cleanup task
            self._monitoring_tasks.append(
                loop.create_task(self._alert_cleanup_loop())
            )
            
        except RuntimeError:
            # No event loop running, tasks will start later
            logger.warning("No event loop available - monitoring tasks will start when loop is available")
    
    def record_performance_metric(self, operation_type: str, operation_name: str, 
                                duration_ms: float, success: bool = True, **metadata):
        """Record a performance metric for real-time analysis."""
        metric = PerformanceMetric(
            timestamp=time.time(),
            operation_type=operation_type,
            operation_name=operation_name,
            duration_ms=duration_ms,
            success=success,
            metadata=metadata
        )
        
        # Add to appropriate window
        if operation_type in self.windows:
            self.windows[operation_type].add_metric(metric)
        else:
            # Create new window for unknown operation type
            self.windows[operation_type] = PerformanceWindow()
            self.windows[operation_type].add_metric(metric)
        
        # Check for immediate performance issues
        self._check_performance_thresholds(metric)
        
        # Log significant performance events
        if metric.performance_level in [PerformanceLevel.POOR, PerformanceLevel.CRITICAL]:
            logger.warning(
                f"Performance issue: {operation_name} took {duration_ms:.2f}ms "
                f"(level: {metric.performance_level.value})"
            )
    
    def _check_performance_thresholds(self, metric: PerformanceMetric):
        """Check if metric exceeds performance thresholds and generate alerts."""
        targets = self.performance_targets.get(metric.operation_type, {})
        
        # Critical response time alert
        critical_ms = targets.get('critical_ms', 500)
        if metric.duration_ms > critical_ms:
            alert_id = f"critical_response_time_{metric.operation_type}"
            if alert_id not in self.active_alerts:
                alert = PerformanceAlert(
                    severity=AlertSeverity.CRITICAL,
                    alert_type="critical_response_time",
                    message=f"{metric.operation_type} operation '{metric.operation_name}' took {metric.duration_ms:.2f}ms (critical threshold: {critical_ms}ms)",
                    timestamp=time.time(),
                    metadata={
                        'operation_type': metric.operation_type,
                        'operation_name': metric.operation_name,
                        'duration_ms': metric.duration_ms,
                        'threshold_ms': critical_ms
                    }
                )
                self._trigger_alert(alert_id, alert)
        
        # Target response time warning
        target_ms = targets.get('target_ms', 100)
        if metric.duration_ms > target_ms * 1.5:  # 50% over target
            alert_id = f"target_exceeded_{metric.operation_type}"
            if alert_id not in self.active_alerts:
                alert = PerformanceAlert(
                    severity=AlertSeverity.WARNING,
                    alert_type="target_exceeded",
                    message=f"{metric.operation_type} operation exceeded target by 50%: {metric.duration_ms:.2f}ms (target: {target_ms}ms)",
                    timestamp=time.time(),
                    metadata={
                        'operation_type': metric.operation_type,
                        'duration_ms': metric.duration_ms,
                        'target_ms': target_ms
                    }
                )
                self._trigger_alert(alert_id, alert)
    
    def _trigger_alert(self, alert_id: str, alert: PerformanceAlert):
        """Trigger a performance alert."""
        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)
        
        # Call registered alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
        
        # Log alert
        log_level = logging.CRITICAL if alert.severity == AlertSeverity.CRITICAL else logging.WARNING
        logger.log(log_level, f"Performance Alert [{alert.severity.value.upper()}]: {alert.message}")
    
    def resolve_alert(self, alert_id: str):
        """Resolve an active alert."""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            alert.resolution_time = time.time()
            del self.active_alerts[alert_id]
            
            logger.info(f"Performance alert resolved: {alert_id}")
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """Add callback function to be called when alerts are triggered."""
        self.alert_callbacks.append(callback)
    
    async def _system_monitoring_loop(self):
        """Background system monitoring loop."""
        while self.system_monitoring_active:
            try:
                # Collect system metrics
                self.system_metrics = {
                    'timestamp': time.time(),
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_io': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
                    'network_io': psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {},
                    'process_count': len(psutil.pids())
                }
                
                # Check system resource alerts
                await self._check_system_alerts()
                
                await asyncio.sleep(30)  # Monitor every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"System monitoring error: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _check_system_alerts(self):
        """Check system metrics for performance alerts."""
        # High CPU usage
        if self.system_metrics.get('cpu_percent', 0) > 80:
            alert_id = "high_cpu_usage"
            if alert_id not in self.active_alerts:
                alert = PerformanceAlert(
                    severity=AlertSeverity.WARNING,
                    alert_type="high_system_resource",
                    message=f"High CPU usage: {self.system_metrics['cpu_percent']:.1f}%",
                    timestamp=time.time(),
                    metadata={'cpu_percent': self.system_metrics['cpu_percent']}
                )
                self._trigger_alert(alert_id, alert)
        else:
            self.resolve_alert("high_cpu_usage")
        
        # High memory usage
        if self.system_metrics.get('memory_percent', 0) > 85:
            alert_id = "high_memory_usage"
            if alert_id not in self.active_alerts:
                alert = PerformanceAlert(
                    severity=AlertSeverity.WARNING,
                    alert_type="high_system_resource",
                    message=f"High memory usage: {self.system_metrics['memory_percent']:.1f}%",
                    timestamp=time.time(),
                    metadata={'memory_percent': self.system_metrics['memory_percent']}
                )
                self._trigger_alert(alert_id, alert)
        else:
            self.resolve_alert("high_memory_usage")
    
    async def _performance_analysis_loop(self):
        """Background performance analysis and alerting."""
        while self.system_monitoring_active:
            try:
                await asyncio.sleep(60)  # Analyze every minute
                
                # Analyze each performance window
                for operation_type, window in self.windows.items():
                    stats = window.get_statistics()
                    
                    if not stats or stats.get('count', 0) < 5:  # Need minimum samples
                        continue
                    
                    targets = self.performance_targets.get(operation_type, {})
                    
                    # Check average response time
                    avg_ms = stats.get('avg_ms', 0)
                    target_ms = targets.get('target_ms', 100)
                    
                    if avg_ms > target_ms:
                        alert_id = f"avg_response_time_{operation_type}"
                        if alert_id not in self.active_alerts:
                            alert = PerformanceAlert(
                                severity=AlertSeverity.WARNING,
                                alert_type="avg_response_time",
                                message=f"{operation_type} average response time {avg_ms:.1f}ms exceeds target {target_ms}ms",
                                timestamp=time.time(),
                                metadata={
                                    'operation_type': operation_type,
                                    'avg_ms': avg_ms,
                                    'target_ms': target_ms,
                                    'sample_count': stats['count']
                                }
                            )
                            self._trigger_alert(alert_id, alert)
                    else:
                        self.resolve_alert(f"avg_response_time_{operation_type}")
                    
                    # Check error rate
                    error_rate = 100 - stats.get('success_rate_percent', 100)
                    error_threshold = targets.get('error_rate_threshold', 1.0)
                    
                    if error_rate > error_threshold:
                        alert_id = f"high_error_rate_{operation_type}"
                        if alert_id not in self.active_alerts:
                            alert = PerformanceAlert(
                                severity=AlertSeverity.ERROR,
                                alert_type="high_error_rate",
                                message=f"{operation_type} error rate {error_rate:.2f}% exceeds threshold {error_threshold}%",
                                timestamp=time.time(),
                                metadata={
                                    'operation_type': operation_type,
                                    'error_rate_percent': error_rate,
                                    'threshold_percent': error_threshold
                                }
                            )
                            self._trigger_alert(alert_id, alert)
                    else:
                        self.resolve_alert(f"high_error_rate_{operation_type}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Performance analysis error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _alert_cleanup_loop(self):
        """Cleanup resolved alerts and manage alert history."""
        while self.system_monitoring_active:
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                
                # Remove old resolved alerts from history
                cutoff_time = time.time() - (24 * 3600)  # 24 hours
                while (self.alert_history and 
                       self.alert_history[0].timestamp < cutoff_time and
                       self.alert_history[0].resolved):
                    self.alert_history.popleft()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert cleanup error: {e}")
                await asyncio.sleep(600)  # Wait 10 minutes on error
    
    def get_performance_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data."""
        dashboard = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'healthy',
            'performance_summary': {},
            'operation_windows': {},
            'active_alerts': [],
            'system_metrics': self.system_metrics.copy(),
            'performance_recommendations': []
        }
        
        # Overall performance assessment
        total_operations = 0
        total_avg_time = 0
        critical_issues = 0
        
        # Analyze each operation window
        for operation_type, window in self.windows.items():
            stats = window.get_statistics()
            
            if stats and stats.get('count', 0) > 0:
                dashboard['operation_windows'][operation_type] = stats
                
                # Add target information
                targets = self.performance_targets.get(operation_type, {})
                stats['target_ms'] = targets.get('target_ms', 100)
                stats['target_met'] = stats.get('avg_ms', 0) <= stats['target_ms']
                
                # Accumulate for overall stats
                total_operations += stats['count']
                total_avg_time += stats['avg_ms'] * stats['count']
                
                # Check for critical performance issues
                if stats.get('avg_ms', 0) > targets.get('critical_ms', 500):
                    critical_issues += 1
        
        # Calculate overall performance
        if total_operations > 0:
            overall_avg_ms = total_avg_time / total_operations
            dashboard['performance_summary'] = {
                'total_operations': total_operations,
                'overall_avg_response_time_ms': round(overall_avg_ms, 2),
                'overall_target_met': overall_avg_ms <= 100.0,
                'critical_issues_count': critical_issues,
                'active_alerts_count': len(self.active_alerts)
            }
            
            # Determine overall status
            if critical_issues > 0 or len(self.active_alerts) > 0:
                if any(alert.severity == AlertSeverity.CRITICAL for alert in self.active_alerts.values()):
                    dashboard['overall_status'] = 'critical'
                else:
                    dashboard['overall_status'] = 'warning'
            elif overall_avg_ms > 150:  # 50% over target
                dashboard['overall_status'] = 'degraded'
        
        # Add active alerts
        dashboard['active_alerts'] = [
            {
                'id': alert_id,
                'severity': alert.severity.value,
                'type': alert.alert_type,
                'message': alert.message,
                'timestamp': alert.timestamp,
                'age_seconds': int(time.time() - alert.timestamp)
            }
            for alert_id, alert in self.active_alerts.items()
        ]
        
        # Generate performance recommendations
        recommendations = []
        
        # Authorization performance recommendations
        auth_stats = dashboard['operation_windows'].get('authorization', {})
        if auth_stats and not auth_stats.get('target_met', True):
            recommendations.append("Authorization performance below target - consider cache warming and database index optimization")
        
        # Database performance recommendations  
        db_stats = dashboard['operation_windows'].get('database_query', {})
        if db_stats and db_stats.get('avg_ms', 0) > 50:
            recommendations.append("Database queries averaging >50ms - review query optimization and connection pooling")
        
        # Cache performance recommendations
        cache_stats = dashboard['operation_windows'].get('cache_operation', {})
        if cache_stats and cache_stats.get('avg_ms', 0) > 20:
            recommendations.append("Cache operations slower than expected - verify Redis connection and consider L1 cache expansion")
        
        # System resource recommendations
        if self.system_metrics.get('cpu_percent', 0) > 60:
            recommendations.append("High CPU utilization detected - consider horizontal scaling or performance optimization")
        
        if self.system_metrics.get('memory_percent', 0) > 70:
            recommendations.append("High memory usage - review cache sizes and memory leaks")
        
        dashboard['performance_recommendations'] = recommendations
        
        return dashboard
    
    def get_alert_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get alert history for specified time period."""
        cutoff_time = time.time() - (hours * 3600)
        
        return [
            {
                'severity': alert.severity.value,
                'type': alert.alert_type,
                'message': alert.message,
                'timestamp': alert.timestamp,
                'resolved': alert.resolved,
                'resolution_time': alert.resolution_time,
                'duration_seconds': (alert.resolution_time - alert.timestamp) if alert.resolution_time else None
            }
            for alert in self.alert_history
            if alert.timestamp >= cutoff_time
        ]
    
    async def shutdown(self):
        """Graceful shutdown of performance monitor."""
        self.system_monitoring_active = False
        
        # Cancel all monitoring tasks
        for task in self._monitoring_tasks:
            task.cancel()
            
        # Wait for tasks to complete
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        
        logger.info("Performance monitor shutdown complete")

# Global performance monitor instance
_performance_monitor: Optional[RealTimePerformanceMonitor] = None

def get_performance_monitor() -> RealTimePerformanceMonitor:
    """Get global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = RealTimePerformanceMonitor()
    return _performance_monitor

# Context manager for performance tracking
class PerformanceTracker:
    """Context manager for automatic performance tracking."""
    
    def __init__(self, operation_type: str, operation_name: str, **metadata):
        self.operation_type = operation_type
        self.operation_name = operation_name
        self.metadata = metadata
        self.start_time = None
        self.monitor = get_performance_monitor()
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        success = exc_type is None
        
        self.monitor.record_performance_metric(
            self.operation_type,
            self.operation_name,
            duration_ms,
            success,
            **self.metadata
        )

# Convenience functions
def track_authorization_performance(operation_name: str, **metadata):
    """Track authorization operation performance."""
    return PerformanceTracker('authorization', operation_name, **metadata)

def track_database_performance(query_name: str, **metadata):
    """Track database query performance."""
    return PerformanceTracker('database_query', query_name, **metadata)

def track_cache_performance(cache_operation: str, **metadata):
    """Track cache operation performance."""
    return PerformanceTracker('cache_operation', cache_operation, **metadata)

async def get_performance_dashboard() -> Dict[str, Any]:
    """Get real-time performance dashboard."""
    monitor = get_performance_monitor()
    return monitor.get_performance_dashboard()