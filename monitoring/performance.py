"""
Real-time performance monitoring system for sub-100ms authorization targets.
Provides response time tracking, concurrency monitoring, and automated alerts.
"""

import time
import threading
import asyncio
import statistics
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum
import uuid
import psutil
import resource

from monitoring.metrics import metrics_collector
from monitoring.logger import performance_logger

class PerformanceTarget(Enum):
    """Performance target classifications."""
    SUB_10MS = 0.01      # Critical operations
    SUB_50MS = 0.05      # Fast operations
    SUB_100MS = 0.1      # Standard target
    SUB_500MS = 0.5      # Acceptable
    SUB_1S = 1.0         # Slow but functional


@dataclass
class PerformanceMetric:
    """Individual performance measurement."""
    operation_id: str
    operation_name: str
    start_time: float
    end_time: float
    duration_ms: float
    target: PerformanceTarget
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def exceeded_target(self) -> bool:
        """Check if operation exceeded its performance target."""
        return self.duration_ms > (self.target.value * 1000)
    
    @property
    def performance_ratio(self) -> float:
        """Calculate performance ratio (actual/target)."""
        return self.duration_ms / (self.target.value * 1000)


@dataclass
class PerformanceWindow:
    """Rolling window of performance metrics."""
    window_size: int
    measurements: deque = field(default_factory=deque)
    
    def add_measurement(self, metric: PerformanceMetric):
        """Add measurement to the window."""
        self.measurements.append(metric)
        if len(self.measurements) > self.window_size:
            self.measurements.popleft()
    
    def get_statistics(self) -> Dict[str, float]:
        """Calculate statistics for the current window."""
        if not self.measurements:
            return {}
        
        durations = [m.duration_ms for m in self.measurements]
        target_violations = sum(1 for m in self.measurements if m.exceeded_target)
        
        return {
            'count': len(durations),
            'avg_ms': statistics.mean(durations),
            'median_ms': statistics.median(durations),
            'min_ms': min(durations),
            'max_ms': max(durations),
            'p95_ms': statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else max(durations),
            'p99_ms': statistics.quantiles(durations, n=100)[98] if len(durations) >= 100 else max(durations),
            'target_violations': target_violations,
            'violation_rate': (target_violations / len(durations)) * 100,
            'success_rate': (sum(1 for m in self.measurements if m.success) / len(durations)) * 100
        }


class PerformanceTracker:
    """
    Comprehensive performance tracking system with real-time monitoring.
    Tracks response times, identifies bottlenecks, and triggers alerts.
    """
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.windows: Dict[str, PerformanceWindow] = defaultdict(
            lambda: PerformanceWindow(window_size)
        )
        self.global_window = PerformanceWindow(window_size * 5)  # Larger global window
        
        # Active operations tracking
        self.active_operations: Dict[str, float] = {}
        self.operations_lock = threading.Lock()
        
        # Performance alerts
        self.alert_thresholds = {
            'violation_rate_threshold': 10.0,  # 10% violation rate
            'avg_response_time_threshold': 100.0,  # 100ms average
            'p95_threshold': 200.0,  # 200ms P95
            'concurrent_operations_threshold': 1000  # 1000 concurrent ops
        }
        
        # Statistics
        self.stats_lock = threading.Lock()
        self.operation_counts: Dict[str, int] = defaultdict(int)
        self.total_operations = 0
        
        # System resource monitoring
        self.system_stats = {
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'active_connections': 0,
            'disk_io_read_mb': 0.0,
            'disk_io_write_mb': 0.0
        }
        
        # Background monitoring thread
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._system_monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
    
    def start_operation(self, operation_name: str, 
                       target: PerformanceTarget = PerformanceTarget.SUB_100MS) -> str:
        """Start tracking a performance-critical operation."""
        operation_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        
        with self.operations_lock:
            self.active_operations[operation_id] = start_time
            self.operation_counts[operation_name] += 1
            self.total_operations += 1
        
        return operation_id
    
    def end_operation(self, operation_id: str, operation_name: str, 
                     target: PerformanceTarget = PerformanceTarget.SUB_100MS,
                     success: bool = True, **metadata) -> PerformanceMetric:
        """End tracking an operation and record performance metrics."""
        end_time = time.perf_counter()
        
        with self.operations_lock:
            start_time = self.active_operations.pop(operation_id, end_time)
        
        duration_seconds = end_time - start_time
        duration_ms = duration_seconds * 1000
        
        metric = PerformanceMetric(
            operation_id=operation_id,
            operation_name=operation_name,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            target=target,
            success=success,
            metadata=metadata
        )
        
        # Record in windows
        self.windows[operation_name].add_measurement(metric)
        self.global_window.add_measurement(metric)
        
        # Record in metrics collector
        metrics_collector.performance_metrics.record_request(
            method=metadata.get('method', 'unknown'),
            endpoint=metadata.get('endpoint', operation_name),
            status_code=metadata.get('status_code', 200),
            duration_seconds=duration_seconds
        )
        
        # Log performance event
        if metric.exceeded_target:
            performance_logger.warning(
                f"Performance target exceeded: {operation_name} took {duration_ms:.2f}ms (target: {target.value * 1000}ms)",
                operation_name=operation_name,
                duration_ms=duration_ms,
                target_ms=target.value * 1000,
                performance_ratio=metric.performance_ratio,
                **metadata
            )
        else:
            performance_logger.info(
                f"Operation completed: {operation_name} - {duration_ms:.2f}ms",
                operation_name=operation_name,
                duration_ms=duration_ms,
                target_ms=target.value * 1000,
                **metadata
            )
        
        # Check for alerts
        self._check_performance_alerts(operation_name, metric)
        
        return metric
    
    def measure_operation(self, operation_name: str, 
                         target: PerformanceTarget = PerformanceTarget.SUB_100MS):
        """Decorator for measuring operation performance."""
        def decorator(func):
            if asyncio.iscoroutinefunction(func):
                async def async_wrapper(*args, **kwargs):
                    operation_id = self.start_operation(operation_name, target)
                    start_time = time.perf_counter()
                    success = True
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except Exception as e:
                        success = False
                        raise
                    finally:
                        self.end_operation(
                            operation_id, operation_name, target, success,
                            function_name=func.__name__,
                            execution_time=time.perf_counter() - start_time
                        )
                return async_wrapper
            else:
                def sync_wrapper(*args, **kwargs):
                    operation_id = self.start_operation(operation_name, target)
                    start_time = time.perf_counter()
                    success = True
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except Exception as e:
                        success = False
                        raise
                    finally:
                        self.end_operation(
                            operation_id, operation_name, target, success,
                            function_name=func.__name__,
                            execution_time=time.perf_counter() - start_time
                        )
                return sync_wrapper
        return decorator
    
    def get_operation_statistics(self, operation_name: str) -> Optional[Dict[str, Any]]:
        """Get performance statistics for a specific operation."""
        if operation_name not in self.windows:
            return None
        
        window_stats = self.windows[operation_name].get_statistics()
        if not window_stats:
            return None
        
        with self.stats_lock:
            operation_count = self.operation_counts[operation_name]
        
        return {
            'operation_name': operation_name,
            'total_executions': operation_count,
            'window_size': len(self.windows[operation_name].measurements),
            **window_stats,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def get_global_statistics(self) -> Dict[str, Any]:
        """Get global performance statistics across all operations."""
        global_stats = self.global_window.get_statistics()
        
        with self.operations_lock:
            concurrent_operations = len(self.active_operations)
        
        with self.stats_lock:
            total_ops = self.total_operations
            operation_breakdown = dict(self.operation_counts)
        
        return {
            'global_performance': global_stats,
            'total_operations': total_ops,
            'concurrent_operations': concurrent_operations,
            'operation_breakdown': operation_breakdown,
            'system_resources': self.system_stats.copy(),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def get_slow_operations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the slowest recent operations."""
        all_metrics = []
        
        for window in self.windows.values():
            all_metrics.extend(window.measurements)
        
        # Sort by duration and get slowest
        all_metrics.sort(key=lambda m: m.duration_ms, reverse=True)
        
        return [
            {
                'operation_name': metric.operation_name,
                'duration_ms': metric.duration_ms,
                'target_ms': metric.target.value * 1000,
                'performance_ratio': metric.performance_ratio,
                'timestamp': datetime.fromtimestamp(metric.start_time).isoformat(),
                'metadata': metric.metadata
            }
            for metric in all_metrics[:limit]
        ]
    
    def _check_performance_alerts(self, operation_name: str, metric: PerformanceMetric):
        """Check if performance alerts should be triggered."""
        window_stats = self.windows[operation_name].get_statistics()
        
        if not window_stats or window_stats['count'] < 10:  # Need minimum samples
            return
        
        alerts = []
        
        # Check violation rate
        if window_stats['violation_rate'] > self.alert_thresholds['violation_rate_threshold']:
            alerts.append({
                'type': 'high_violation_rate',
                'value': window_stats['violation_rate'],
                'threshold': self.alert_thresholds['violation_rate_threshold'],
                'operation': operation_name
            })
        
        # Check average response time
        if window_stats['avg_ms'] > self.alert_thresholds['avg_response_time_threshold']:
            alerts.append({
                'type': 'high_average_response_time',
                'value': window_stats['avg_ms'],
                'threshold': self.alert_thresholds['avg_response_time_threshold'],
                'operation': operation_name
            })
        
        # Check P95 response time
        if window_stats['p95_ms'] > self.alert_thresholds['p95_threshold']:
            alerts.append({
                'type': 'high_p95_response_time',
                'value': window_stats['p95_ms'],
                'threshold': self.alert_thresholds['p95_threshold'],
                'operation': operation_name
            })
        
        # Log alerts
        for alert in alerts:
            performance_logger.error(
                f"PERFORMANCE ALERT: {alert['type']} for {operation_name}",
                alert_type=alert['type'],
                alert_value=alert['value'],
                alert_threshold=alert['threshold'],
                operation_name=operation_name,
                window_stats=window_stats
            )
    
    def _system_monitoring_loop(self):
        """Background thread for system resource monitoring."""
        while self.monitoring_active:
            try:
                # CPU and memory usage
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                
                # Disk I/O
                disk_io = psutil.disk_io_counters()
                disk_read_mb = disk_io.read_bytes / (1024 * 1024) if disk_io else 0
                disk_write_mb = disk_io.write_bytes / (1024 * 1024) if disk_io else 0
                
                # Network connections (approximate)
                connections = len(psutil.net_connections(kind='inet'))
                
                # Update system stats
                self.system_stats.update({
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_gb': memory.used / (1024**3),
                    'active_connections': connections,
                    'disk_io_read_mb': disk_read_mb,
                    'disk_io_write_mb': disk_write_mb
                })
                
                # Update metrics collector
                metrics_collector.performance_metrics.update_system_metrics(
                    memory.used, cpu_percent
                )
                
                # Check system-level alerts
                if cpu_percent > 80:
                    performance_logger.warning(
                        f"High CPU usage: {cpu_percent}%",
                        cpu_percent=cpu_percent,
                        alert_type="high_cpu"
                    )
                
                if memory.percent > 85:
                    performance_logger.warning(
                        f"High memory usage: {memory.percent}%",
                        memory_percent=memory.percent,
                        memory_used_gb=memory.used / (1024**3),
                        alert_type="high_memory"
                    )
                
                # Check concurrent operations
                with self.operations_lock:
                    concurrent_ops = len(self.active_operations)
                
                if concurrent_ops > self.alert_thresholds['concurrent_operations_threshold']:
                    performance_logger.warning(
                        f"High concurrent operations: {concurrent_ops}",
                        concurrent_operations=concurrent_ops,
                        threshold=self.alert_thresholds['concurrent_operations_threshold'],
                        alert_type="high_concurrency"
                    )
                
                time.sleep(30)  # Monitor every 30 seconds
                
            except Exception as e:
                performance_logger.error(
                    f"System monitoring error: {e}",
                    exception=e
                )
                time.sleep(60)  # Wait longer on error
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self.monitoring_active = False
        if self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)


class ResponseTimeMonitor:
    """
    Specialized monitor for HTTP response time tracking.
    Provides detailed analysis of request performance patterns.
    """
    
    def __init__(self):
        self.endpoint_windows: Dict[str, PerformanceWindow] = defaultdict(
            lambda: PerformanceWindow(500)
        )
        self.status_code_windows: Dict[int, PerformanceWindow] = defaultdict(
            lambda: PerformanceWindow(200)
        )
        self.lock = threading.Lock()
    
    def record_request(self, method: str, endpoint: str, status_code: int,
                      duration_ms: float, user_id: Optional[str] = None,
                      **metadata):
        """Record HTTP request performance."""
        
        # Determine target based on endpoint
        target = PerformanceTarget.SUB_100MS
        if 'auth' in endpoint.lower():
            target = PerformanceTarget.SUB_50MS  # Auth should be faster
        elif 'generation' in endpoint.lower():
            target = PerformanceTarget.SUB_500MS  # Generation can be slower
        
        metric = PerformanceMetric(
            operation_id=str(uuid.uuid4()),
            operation_name=f"{method} {endpoint}",
            start_time=time.perf_counter() - (duration_ms / 1000),
            end_time=time.perf_counter(),
            duration_ms=duration_ms,
            target=target,
            success=200 <= status_code < 400,
            metadata={
                'method': method,
                'endpoint': endpoint,
                'status_code': status_code,
                'user_id': user_id,
                **metadata
            }
        )
        
        with self.lock:
            endpoint_key = f"{method} {endpoint}"
            self.endpoint_windows[endpoint_key].add_measurement(metric)
            self.status_code_windows[status_code].add_measurement(metric)
    
    def get_endpoint_statistics(self, method: str, endpoint: str) -> Dict[str, Any]:
        """Get statistics for a specific endpoint."""
        endpoint_key = f"{method} {endpoint}"
        with self.lock:
            if endpoint_key not in self.endpoint_windows:
                return {}
            return self.endpoint_windows[endpoint_key].get_statistics()
    
    def get_slowest_endpoints(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the slowest endpoints by average response time."""
        endpoint_stats = []
        
        with self.lock:
            for endpoint, window in self.endpoint_windows.items():
                stats = window.get_statistics()
                if stats and stats['count'] >= 5:  # Minimum sample size
                    endpoint_stats.append({
                        'endpoint': endpoint,
                        'avg_response_time_ms': stats['avg_ms'],
                        'p95_response_time_ms': stats['p95_ms'],
                        'request_count': stats['count'],
                        'violation_rate': stats['violation_rate']
                    })
        
        return sorted(endpoint_stats, key=lambda x: x['avg_response_time_ms'], reverse=True)[:limit]


class ConcurrencyMonitor:
    """
    Monitor for tracking concurrent operations and system capacity.
    Helps identify concurrency bottlenecks and scaling needs.
    """
    
    def __init__(self, capacity_warning_threshold: int = 8000,
                 capacity_critical_threshold: int = 10000):
        self.capacity_warning = capacity_warning_threshold
        self.capacity_critical = capacity_critical_threshold
        
        self.active_operations: Dict[str, Dict[str, Any]] = {}
        self.operation_history: deque = deque(maxlen=10000)
        self.lock = threading.Lock()
        
        # Concurrency statistics
        self.max_concurrent = 0
        self.total_operations = 0
        self.current_concurrent = 0
    
    def start_operation(self, operation_type: str, user_id: Optional[str] = None,
                       **metadata) -> str:
        """Start tracking a concurrent operation."""
        operation_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        
        operation_data = {
            'type': operation_type,
            'user_id': user_id,
            'start_time': start_time,
            'metadata': metadata
        }
        
        with self.lock:
            self.active_operations[operation_id] = operation_data
            self.current_concurrent = len(self.active_operations)
            self.max_concurrent = max(self.max_concurrent, self.current_concurrent)
            self.total_operations += 1
        
        # Check capacity alerts
        self._check_capacity_alerts()
        
        return operation_id
    
    def end_operation(self, operation_id: str):
        """End tracking a concurrent operation."""
        end_time = time.perf_counter()
        
        with self.lock:
            if operation_id in self.active_operations:
                operation_data = self.active_operations.pop(operation_id)
                duration = end_time - operation_data['start_time']
                
                # Add to history
                self.operation_history.append({
                    'operation_id': operation_id,
                    'type': operation_data['type'],
                    'user_id': operation_data['user_id'],
                    'duration_seconds': duration,
                    'start_time': operation_data['start_time'],
                    'end_time': end_time,
                    'metadata': operation_data['metadata']
                })
                
                self.current_concurrent = len(self.active_operations)
    
    def _check_capacity_alerts(self):
        """Check if capacity alerts should be triggered."""
        current = self.current_concurrent
        
        if current >= self.capacity_critical:
            performance_logger.critical(
                f"CRITICAL: Concurrent operations at {current} (critical threshold: {self.capacity_critical})",
                concurrent_operations=current,
                threshold=self.capacity_critical,
                alert_type="capacity_critical"
            )
        elif current >= self.capacity_warning:
            performance_logger.warning(
                f"WARNING: Concurrent operations at {current} (warning threshold: {self.capacity_warning})",
                concurrent_operations=current,
                threshold=self.capacity_warning,
                alert_type="capacity_warning"
            )
    
    def get_concurrency_statistics(self) -> Dict[str, Any]:
        """Get concurrency statistics."""
        with self.lock:
            active_ops = len(self.active_operations)
            operation_types = defaultdict(int)
            
            for op_data in self.active_operations.values():
                operation_types[op_data['type']] += 1
            
            return {
                'current_concurrent_operations': active_ops,
                'max_concurrent_operations': self.max_concurrent,
                'total_operations_processed': self.total_operations,
                'capacity_utilization_percent': (active_ops / self.capacity_critical) * 100,
                'active_operation_types': dict(operation_types),
                'capacity_warning_threshold': self.capacity_warning,
                'capacity_critical_threshold': self.capacity_critical,
                'timestamp': datetime.utcnow().isoformat()
            }


# Global performance tracking instances
performance_tracker = PerformanceTracker()
response_time_monitor = ResponseTimeMonitor()
concurrency_monitor = ConcurrencyMonitor()