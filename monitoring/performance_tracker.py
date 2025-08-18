"""
Comprehensive Performance Tracking System for PRD Compliance Monitoring

This module provides real-time performance tracking and validation against PRD targets:
- Authentication: <50ms target
- Authorization: <75ms target  
- Cache hit rates: >95% target
- Database queries: Real-time monitoring
- Concurrent user tracking with performance impact analysis

Features:
- Real-time metrics collection with thread-safe operations
- PRD compliance tracking and alerting
- Performance grading system (A-F grades)
- Multi-layer cache monitoring (L1, L2, L3)
- Statistical analysis (P50, P95, P99 percentiles)
- Time window analysis (1min, 5min, 1hour)
- Integration with existing monitoring systems
- RESTful API endpoints for metrics access
- Actionable performance recommendations
"""

import asyncio
import threading
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from enum import Enum
import logging
import json
import weakref
from functools import wraps
import traceback

# Configure logging
logger = logging.getLogger(__name__)


class PerformanceGrade(Enum):
    """Performance grades based on PRD compliance."""
    A = "A"  # Exceeds targets by >20%
    B = "B"  # Meets targets within 10%
    C = "C"  # Close to targets (within 25%)
    D = "D"  # Below targets but functional
    F = "F"  # Critical performance issues


class AlertLevel(Enum):
    """Alert severity levels for performance monitoring."""
    SUCCESS = "success"      # Meeting or exceeding targets
    INFO = "info"           # Minor deviations
    WARNING = "warning"     # 1.5x target violations
    CRITICAL = "critical"   # 2x target violations
    EMERGENCY = "emergency" # System degradation


class MetricType(Enum):
    """Types of performance metrics tracked."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CACHE_L1 = "cache_l1"
    CACHE_L2 = "cache_l2"
    CACHE_L3 = "cache_l3"
    DATABASE_QUERY = "database_query"
    DATABASE_CONNECTION = "database_connection"
    CONCURRENT_USERS = "concurrent_users"
    API_RESPONSE = "api_response"


class TimeWindow(Enum):
    """Time windows for performance analysis."""
    ONE_MINUTE = "1min"
    FIVE_MINUTES = "5min"
    ONE_HOUR = "1hour"
    ONE_DAY = "1day"


@dataclass
class PRDTarget:
    """PRD performance target configuration."""
    metric_type: MetricType
    target_value: float
    target_unit: str
    warning_threshold: float  # 1.5x multiplier
    critical_threshold: float  # 2.0x multiplier
    description: str
    grade_excellent: float  # A grade threshold
    grade_good: float      # B grade threshold
    grade_acceptable: float # C grade threshold
    grade_poor: float      # D grade threshold


@dataclass
class PerformanceMetric:
    """Individual performance measurement."""
    timestamp: float
    metric_type: MetricType
    operation_name: str
    value: float
    unit: str
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    
    @property
    def age_seconds(self) -> float:
        """Get age of metric in seconds."""
        return time.time() - self.timestamp


@dataclass
class PerformanceAlert:
    """Performance alert with detailed context."""
    alert_id: str
    level: AlertLevel
    metric_type: MetricType
    message: str
    current_value: float
    target_value: float
    threshold_exceeded: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution_time: Optional[float] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Get alert duration in seconds."""
        if self.resolution_time:
            return self.resolution_time - self.timestamp
        return time.time() - self.timestamp


@dataclass
class PerformanceStats:
    """Statistical analysis of performance metrics."""
    count: int
    mean: float
    median: float
    min_val: float
    max_val: float
    std_dev: float
    p50: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None
    success_rate: float = 100.0
    grade: PerformanceGrade = PerformanceGrade.C
    target_compliance: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['grade'] = self.grade.value
        return result


class PerformanceTimeWindow:
    """Thread-safe time window for performance metrics."""
    
    def __init__(self, window_duration: timedelta, max_samples: int = 10000):
        self.window_duration = window_duration
        self.max_samples = max_samples
        self.metrics: deque = deque(maxlen=max_samples)
        self._lock = threading.RLock()
    
    def add_metric(self, metric: PerformanceMetric):
        """Add metric to the time window."""
        with self._lock:
            # Remove expired metrics
            cutoff_time = time.time() - self.window_duration.total_seconds()
            while self.metrics and self.metrics[0].timestamp < cutoff_time:
                self.metrics.popleft()
            
            self.metrics.append(metric)
    
    def get_metrics(self, since: Optional[float] = None) -> List[PerformanceMetric]:
        """Get metrics from the window, optionally filtered by time."""
        with self._lock:
            if since is None:
                return list(self.metrics)
            return [m for m in self.metrics if m.timestamp >= since]
    
    def calculate_stats(self, target: Optional[PRDTarget] = None) -> PerformanceStats:
        """Calculate comprehensive statistics for the window."""
        with self._lock:
            if not self.metrics:
                return PerformanceStats(
                    count=0, mean=0, median=0, min_val=0, max_val=0, 
                    std_dev=0, grade=PerformanceGrade.F
                )
            
            values = [m.value for m in self.metrics]
            successes = [m for m in self.metrics if m.success]
            
            stats = PerformanceStats(
                count=len(values),
                mean=statistics.mean(values),
                median=statistics.median(values),
                min_val=min(values),
                max_val=max(values),
                std_dev=statistics.stdev(values) if len(values) > 1 else 0,
                success_rate=(len(successes) / len(values)) * 100
            )
            
            # Calculate percentiles for sufficient sample size
            if len(values) >= 10:
                sorted_values = sorted(values)
                stats.p50 = statistics.median(sorted_values)
                if len(values) >= 20:
                    stats.p95 = sorted_values[int(0.95 * len(values))]
                if len(values) >= 100:
                    stats.p99 = sorted_values[int(0.99 * len(values))]
            
            # Calculate grade and target compliance
            if target:
                stats.target_compliance = self._calculate_compliance(stats.mean, target)
                stats.grade = self._calculate_grade(stats.mean, target)
            
            return stats
    
    def _calculate_compliance(self, value: float, target: PRDTarget) -> float:
        """Calculate percentage compliance with target."""
        if target.target_value == 0:
            return 100.0 if value == 0 else 0.0
        
        if target.metric_type.value.startswith('cache'):
            # For cache hit rates, higher is better
            return min(100.0, (value / target.target_value) * 100)
        else:
            # For response times, lower is better
            return max(0.0, (1 - (value - target.target_value) / target.target_value) * 100)
    
    def _calculate_grade(self, value: float, target: PRDTarget) -> PerformanceGrade:
        """Calculate performance grade based on target thresholds."""
        if target.metric_type.value.startswith('cache'):
            # For cache hit rates, higher is better
            if value >= target.grade_excellent:
                return PerformanceGrade.A
            elif value >= target.grade_good:
                return PerformanceGrade.B
            elif value >= target.grade_acceptable:
                return PerformanceGrade.C
            elif value >= target.grade_poor:
                return PerformanceGrade.D
            else:
                return PerformanceGrade.F
        else:
            # For response times, lower is better
            if value <= target.grade_excellent:
                return PerformanceGrade.A
            elif value <= target.grade_good:
                return PerformanceGrade.B
            elif value <= target.grade_acceptable:
                return PerformanceGrade.C
            elif value <= target.grade_poor:
                return PerformanceGrade.D
            else:
                return PerformanceGrade.F


class PerformanceTracker:
    """
    Comprehensive performance tracking system for PRD compliance.
    
    Tracks all critical performance metrics:
    - Authentication response times (<50ms target)
    - Authorization response times (<75ms target)  
    - Cache hit rates L1/L2/L3 (>95% target)
    - Database query performance
    - Concurrent user impact on performance
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._active = True
        
        # Initialize PRD targets
        self.prd_targets = self._initialize_prd_targets()
        
        # Time windows for different analysis periods
        self.time_windows = {
            TimeWindow.ONE_MINUTE: {
                metric_type: PerformanceTimeWindow(timedelta(minutes=1))
                for metric_type in MetricType
            },
            TimeWindow.FIVE_MINUTES: {
                metric_type: PerformanceTimeWindow(timedelta(minutes=5))
                for metric_type in MetricType
            },
            TimeWindow.ONE_HOUR: {
                metric_type: PerformanceTimeWindow(timedelta(hours=1))
                for metric_type in MetricType
            },
            TimeWindow.ONE_DAY: {
                metric_type: PerformanceTimeWindow(timedelta(days=1))
                for metric_type in MetricType
            }
        }
        
        # Alert management
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.alert_callbacks: List[callable] = []
        
        # Concurrent user tracking
        self.concurrent_users = 0
        self.concurrent_user_history: deque = deque(maxlen=1000)
        
        # Performance trends
        self.trend_analysis: Dict[MetricType, List[float]] = defaultdict(list)
        
        # Background monitoring task
        self.monitoring_task: Optional[asyncio.Task] = None
        
        logger.info("Performance tracker initialized with PRD targets")
    
    def _initialize_prd_targets(self) -> Dict[MetricType, PRDTarget]:
        """Initialize PRD performance targets."""
        return {
            MetricType.AUTHENTICATION: PRDTarget(
                metric_type=MetricType.AUTHENTICATION,
                target_value=50.0,  # <50ms
                target_unit="ms",
                warning_threshold=75.0,  # 1.5x
                critical_threshold=100.0,  # 2.0x
                description="Authentication response time",
                grade_excellent=30.0,
                grade_good=40.0,
                grade_acceptable=50.0,
                grade_poor=75.0
            ),
            MetricType.AUTHORIZATION: PRDTarget(
                metric_type=MetricType.AUTHORIZATION,
                target_value=75.0,  # <75ms
                target_unit="ms",
                warning_threshold=112.5,  # 1.5x
                critical_threshold=150.0,  # 2.0x
                description="Authorization response time",
                grade_excellent=50.0,
                grade_good=60.0,
                grade_acceptable=75.0,
                grade_poor=100.0
            ),
            MetricType.CACHE_L1: PRDTarget(
                metric_type=MetricType.CACHE_L1,
                target_value=95.0,  # >95%
                target_unit="%",
                warning_threshold=90.0,  # Below 90%
                critical_threshold=85.0,  # Below 85%
                description="L1 cache hit rate",
                grade_excellent=98.0,
                grade_good=96.0,
                grade_acceptable=95.0,
                grade_poor=90.0
            ),
            MetricType.CACHE_L2: PRDTarget(
                metric_type=MetricType.CACHE_L2,
                target_value=95.0,  # >95%
                target_unit="%",
                warning_threshold=90.0,
                critical_threshold=85.0,
                description="L2 cache hit rate",
                grade_excellent=97.0,
                grade_good=95.0,
                grade_acceptable=93.0,
                grade_poor=88.0
            ),
            MetricType.CACHE_L3: PRDTarget(
                metric_type=MetricType.CACHE_L3,
                target_value=95.0,  # >95%
                target_unit="%",
                warning_threshold=90.0,
                critical_threshold=85.0,
                description="L3 cache hit rate",
                grade_excellent=96.0,
                grade_good=94.0,
                grade_acceptable=92.0,
                grade_poor=87.0
            ),
            MetricType.DATABASE_QUERY: PRDTarget(
                metric_type=MetricType.DATABASE_QUERY,
                target_value=25.0,  # <25ms for auth queries
                target_unit="ms",
                warning_threshold=37.5,  # 1.5x
                critical_threshold=50.0,  # 2.0x
                description="Database query response time",
                grade_excellent=15.0,
                grade_good=20.0,
                grade_acceptable=25.0,
                grade_poor=35.0
            ),
            MetricType.API_RESPONSE: PRDTarget(
                metric_type=MetricType.API_RESPONSE,
                target_value=100.0,  # <100ms overall
                target_unit="ms",
                warning_threshold=150.0,  # 1.5x
                critical_threshold=200.0,  # 2.0x
                description="Overall API response time",
                grade_excellent=60.0,
                grade_good=80.0,
                grade_acceptable=100.0,
                grade_poor=150.0
            )
        }
    
    def record_metric(self, 
                     metric_type: MetricType, 
                     operation_name: str,
                     value: float,
                     unit: str = "",
                     success: bool = True,
                     user_id: Optional[str] = None,
                     endpoint: Optional[str] = None,
                     **metadata) -> None:
        """
        Record a performance metric.
        
        Args:
            metric_type: Type of metric being recorded
            operation_name: Name of the operation (e.g., 'jwt_validation', 'user_auth')
            value: Metric value (response time in ms, hit rate in %, etc.)
            unit: Unit of measurement
            success: Whether the operation succeeded
            user_id: Optional user identifier
            endpoint: Optional API endpoint
            **metadata: Additional metadata
        """
        if not self._active:
            return
        
        metric = PerformanceMetric(
            timestamp=time.time(),
            metric_type=metric_type,
            operation_name=operation_name,
            value=value,
            unit=unit,
            success=success,
            user_id=user_id,
            endpoint=endpoint,
            metadata=metadata
        )
        
        # Add to all time windows
        for window_dict in self.time_windows.values():
            if metric_type in window_dict:
                window_dict[metric_type].add_metric(metric)
        
        # Check for target violations and trigger alerts
        self._check_performance_targets(metric)
        
        # Update trend analysis
        with self._lock:
            self.trend_analysis[metric_type].append(value)
            # Keep only last 100 values for trend analysis
            if len(self.trend_analysis[metric_type]) > 100:
                self.trend_analysis[metric_type] = self.trend_analysis[metric_type][-100:]
    
    def record_concurrent_users(self, user_count: int) -> None:
        """Record current concurrent user count."""
        with self._lock:
            self.concurrent_users = user_count
            self.concurrent_user_history.append({
                'timestamp': time.time(),
                'count': user_count
            })
    
    def _check_performance_targets(self, metric: PerformanceMetric) -> None:
        """Check metric against PRD targets and generate alerts if needed."""
        target = self.prd_targets.get(metric.metric_type)
        if not target:
            return
        
        alert_triggered = False
        
        # Determine if target is violated
        if metric.metric_type.value.startswith('cache'):
            # For cache metrics, lower values are worse
            if metric.value < target.critical_threshold:
                self._trigger_alert(metric, target, AlertLevel.CRITICAL)
                alert_triggered = True
            elif metric.value < target.warning_threshold:
                self._trigger_alert(metric, target, AlertLevel.WARNING)
                alert_triggered = True
        else:
            # For response time metrics, higher values are worse
            if metric.value > target.critical_threshold:
                self._trigger_alert(metric, target, AlertLevel.CRITICAL)
                alert_triggered = True
            elif metric.value > target.warning_threshold:
                self._trigger_alert(metric, target, AlertLevel.WARNING)
                alert_triggered = True
        
        # If no alert was triggered and metric is good, resolve existing alerts
        if not alert_triggered:
            self._resolve_alerts_for_metric_type(metric.metric_type)
    
    def _trigger_alert(self, metric: PerformanceMetric, target: PRDTarget, level: AlertLevel) -> None:
        """Trigger a performance alert."""
        alert_id = f"{metric.metric_type.value}_{level.value}"
        
        # Don't create duplicate alerts
        if alert_id in self.active_alerts:
            return
        
        if metric.metric_type.value.startswith('cache'):
            threshold_exceeded = target.target_value - metric.value
            message = (f"{target.description} is {metric.value:.1f}% "
                      f"(target: >{target.target_value}%, "
                      f"below target by {threshold_exceeded:.1f}%)")
        else:
            threshold_exceeded = metric.value - target.target_value
            message = (f"{target.description} is {metric.value:.1f}{target.target_unit} "
                      f"(target: <{target.target_value}{target.target_unit}, "
                      f"over target by {threshold_exceeded:.1f}{target.target_unit})")
        
        alert = PerformanceAlert(
            alert_id=alert_id,
            level=level,
            metric_type=metric.metric_type,
            message=message,
            current_value=metric.value,
            target_value=target.target_value,
            threshold_exceeded=threshold_exceeded,
            timestamp=time.time(),
            metadata={
                'operation_name': metric.operation_name,
                'endpoint': metric.endpoint,
                'user_id': metric.user_id,
                **metric.metadata
            }
        )
        
        with self._lock:
            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)
        
        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
        
        # Log alert
        log_level = logging.CRITICAL if level == AlertLevel.CRITICAL else logging.WARNING
        logger.log(log_level, f"Performance Alert [{level.value.upper()}]: {message}")
    
    def _resolve_alerts_for_metric_type(self, metric_type: MetricType) -> None:
        """Resolve active alerts for a metric type when performance improves."""
        with self._lock:
            alerts_to_resolve = [
                alert_id for alert_id, alert in self.active_alerts.items()
                if alert.metric_type == metric_type
            ]
            
            for alert_id in alerts_to_resolve:
                alert = self.active_alerts[alert_id]
                alert.resolved = True
                alert.resolution_time = time.time()
                del self.active_alerts[alert_id]
                logger.info(f"Performance alert resolved: {alert_id}")
    
    def add_alert_callback(self, callback: callable) -> None:
        """Add callback function for alert notifications."""
        self.alert_callbacks.append(callback)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics for /api/v1/performance/metrics endpoint."""
        with self._lock:
            metrics_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'concurrent_users': self.concurrent_users,
                'metrics_by_type': {},
                'overall_grade': self._calculate_overall_grade(),
                'prd_compliance': self._calculate_prd_compliance(),
                'active_alerts_count': len(self.active_alerts)
            }
            
            # Get 5-minute window stats for each metric type
            for metric_type in MetricType:
                window = self.time_windows[TimeWindow.FIVE_MINUTES][metric_type]
                target = self.prd_targets.get(metric_type)
                stats = window.calculate_stats(target)
                
                metrics_data['metrics_by_type'][metric_type.value] = {
                    'current_stats': stats.to_dict(),
                    'target': {
                        'value': target.target_value,
                        'unit': target.target_unit,
                        'description': target.description
                    } if target else None,
                    'recent_values': [
                        {'timestamp': m.timestamp, 'value': m.value}
                        for m in window.get_metrics()[-10:]  # Last 10 values
                    ]
                }
            
            return metrics_data
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get system health data for /api/v1/performance/health endpoint."""
        with self._lock:
            health_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'overall_status': 'healthy',
                'component_health': {},
                'active_alerts': [
                    {
                        'id': alert.alert_id,
                        'level': alert.level.value,
                        'message': alert.message,
                        'duration_seconds': alert.duration_seconds,
                        'metric_type': alert.metric_type.value
                    }
                    for alert in self.active_alerts.values()
                ],
                'performance_summary': {
                    'authentication_grade': 'C',
                    'authorization_grade': 'C',
                    'cache_performance_grade': 'C',
                    'database_performance_grade': 'C',
                    'overall_grade': 'C'
                }
            }
            
            # Determine overall status based on alerts
            critical_alerts = [a for a in self.active_alerts.values() if a.level == AlertLevel.CRITICAL]
            warning_alerts = [a for a in self.active_alerts.values() if a.level == AlertLevel.WARNING]
            
            if critical_alerts:
                health_data['overall_status'] = 'critical'
            elif len(warning_alerts) > 3:
                health_data['overall_status'] = 'degraded'
            elif warning_alerts:
                health_data['overall_status'] = 'warning'
            
            # Component health assessment
            for metric_type in [MetricType.AUTHENTICATION, MetricType.AUTHORIZATION, 
                              MetricType.CACHE_L1, MetricType.DATABASE_QUERY]:
                window = self.time_windows[TimeWindow.ONE_MINUTE][metric_type]
                target = self.prd_targets.get(metric_type)
                stats = window.calculate_stats(target)
                
                # Component status based on recent performance
                if stats.count > 0:
                    component_status = 'healthy'
                    if any(alert.metric_type == metric_type and alert.level == AlertLevel.CRITICAL 
                           for alert in self.active_alerts.values()):
                        component_status = 'critical'
                    elif any(alert.metric_type == metric_type and alert.level == AlertLevel.WARNING 
                             for alert in self.active_alerts.values()):
                        component_status = 'warning'
                    
                    health_data['component_health'][metric_type.value] = {
                        'status': component_status,
                        'grade': stats.grade.value,
                        'target_compliance': stats.target_compliance,
                        'recent_average': stats.mean,
                        'success_rate': stats.success_rate
                    }
                    
                    # Update performance summary grades
                    if metric_type == MetricType.AUTHENTICATION:
                        health_data['performance_summary']['authentication_grade'] = stats.grade.value
                    elif metric_type == MetricType.AUTHORIZATION:
                        health_data['performance_summary']['authorization_grade'] = stats.grade.value
                    elif metric_type in [MetricType.CACHE_L1, MetricType.CACHE_L2, MetricType.CACHE_L3]:
                        health_data['performance_summary']['cache_performance_grade'] = stats.grade.value
                    elif metric_type == MetricType.DATABASE_QUERY:
                        health_data['performance_summary']['database_performance_grade'] = stats.grade.value
            
            health_data['performance_summary']['overall_grade'] = self._calculate_overall_grade().value
            
            return health_data
    
    def get_detailed_report(self) -> Dict[str, Any]:
        """Get detailed performance report for /api/v1/performance/report endpoint."""
        with self._lock:
            report = {
                'timestamp': datetime.utcnow().isoformat(),
                'report_period': '1 hour',
                'executive_summary': self._generate_executive_summary(),
                'prd_compliance_analysis': self._generate_prd_compliance_analysis(),
                'performance_trends': self._generate_trend_analysis(),
                'detailed_metrics': self._generate_detailed_metrics(),
                'concurrent_user_impact': self._analyze_concurrent_user_impact(),
                'recommendations': self._generate_recommendations(),
                'alert_summary': self._generate_alert_summary()
            }
            
            return report
    
    def _calculate_overall_grade(self) -> PerformanceGrade:
        """Calculate overall performance grade."""
        grades = []
        
        for metric_type in [MetricType.AUTHENTICATION, MetricType.AUTHORIZATION, 
                          MetricType.CACHE_L1, MetricType.DATABASE_QUERY]:
            window = self.time_windows[TimeWindow.FIVE_MINUTES][metric_type]
            target = self.prd_targets.get(metric_type)
            stats = window.calculate_stats(target)
            if stats.count > 0:
                grades.append(stats.grade)
        
        if not grades:
            return PerformanceGrade.C
        
        # Calculate weighted average grade
        grade_values = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
        avg_grade = sum(grade_values[g.value] for g in grades) / len(grades)
        
        if avg_grade >= 3.5:
            return PerformanceGrade.A
        elif avg_grade >= 2.5:
            return PerformanceGrade.B
        elif avg_grade >= 1.5:
            return PerformanceGrade.C
        elif avg_grade >= 0.5:
            return PerformanceGrade.D
        else:
            return PerformanceGrade.F
    
    def _calculate_prd_compliance(self) -> Dict[str, float]:
        """Calculate PRD compliance percentages."""
        compliance = {}
        
        for metric_type, target in self.prd_targets.items():
            window = self.time_windows[TimeWindow.ONE_HOUR][metric_type]
            stats = window.calculate_stats(target)
            compliance[metric_type.value] = stats.target_compliance
        
        return compliance
    
    def _generate_executive_summary(self) -> Dict[str, Any]:
        """Generate executive summary for performance report."""
        overall_grade = self._calculate_overall_grade()
        compliance = self._calculate_prd_compliance()
        
        critical_issues = len([a for a in self.active_alerts.values() if a.level == AlertLevel.CRITICAL])
        warning_issues = len([a for a in self.active_alerts.values() if a.level == AlertLevel.WARNING])
        
        avg_compliance = sum(compliance.values()) / len(compliance) if compliance else 0
        
        summary = {
            'overall_performance_grade': overall_grade.value,
            'prd_compliance_average': round(avg_compliance, 1),
            'critical_issues': critical_issues,
            'warning_issues': warning_issues,
            'status_description': self._get_status_description(overall_grade, critical_issues, warning_issues),
            'key_achievements': [],
            'areas_for_improvement': []
        }
        
        # Identify achievements and improvements needed
        for metric_type, compliance_pct in compliance.items():
            if compliance_pct >= 100:
                summary['key_achievements'].append(f"{metric_type}: Exceeding PRD targets ({compliance_pct:.1f}%)")
            elif compliance_pct < 80:
                summary['areas_for_improvement'].append(f"{metric_type}: Below target ({compliance_pct:.1f}%)")
        
        return summary
    
    def _get_status_description(self, grade: PerformanceGrade, critical: int, warnings: int) -> str:
        """Get human-readable status description."""
        if critical > 0:
            return f"Critical performance issues detected. Grade {grade.value} with {critical} critical alerts."
        elif warnings > 2:
            return f"Multiple performance warnings. Grade {grade.value} with {warnings} warning alerts."
        elif grade == PerformanceGrade.A:
            return "Excellent performance. All systems operating above PRD targets."
        elif grade == PerformanceGrade.B:
            return "Good performance. Systems meeting PRD targets with room for optimization."
        elif grade == PerformanceGrade.C:
            return "Acceptable performance. Some areas approaching PRD limits."
        elif grade == PerformanceGrade.D:
            return "Below-target performance. Immediate optimization recommended."
        else:
            return "Poor performance. Critical optimization required."
    
    def _generate_prd_compliance_analysis(self) -> Dict[str, Any]:
        """Generate detailed PRD compliance analysis."""
        analysis = {
            'compliance_by_metric': {},
            'trending': {},
            'violations_24h': {},
            'improvement_opportunities': []
        }
        
        for metric_type, target in self.prd_targets.items():
            # Current compliance
            window = self.time_windows[TimeWindow.ONE_HOUR][metric_type]
            stats = window.calculate_stats(target)
            
            analysis['compliance_by_metric'][metric_type.value] = {
                'current_compliance_pct': stats.target_compliance,
                'target_value': target.target_value,
                'current_average': stats.mean,
                'grade': stats.grade.value,
                'sample_count': stats.count
            }
            
            # Trend analysis
            recent_trend = self.trend_analysis.get(metric_type, [])
            if len(recent_trend) >= 10:
                early_avg = sum(recent_trend[:10]) / 10
                recent_avg = sum(recent_trend[-10:]) / 10
                trend_direction = "improving" if recent_avg < early_avg else "degrading"
                trend_magnitude = abs(recent_avg - early_avg)
                
                analysis['trending'][metric_type.value] = {
                    'direction': trend_direction,
                    'magnitude': trend_magnitude,
                    'confidence': 'high' if len(recent_trend) >= 50 else 'medium'
                }
        
        return analysis
    
    def _generate_trend_analysis(self) -> Dict[str, Any]:
        """Generate performance trend analysis."""
        trends = {}
        
        for metric_type, values in self.trend_analysis.items():
            if len(values) >= 20:  # Need sufficient data for trend analysis
                # Simple linear trend
                x = list(range(len(values)))
                y = values
                
                # Calculate correlation coefficient for trend strength
                if len(values) > 1:
                    from scipy.stats import pearsonr
                    try:
                        correlation, _ = pearsonr(x, y)
                        trend_strength = abs(correlation)
                        trend_direction = "improving" if correlation < 0 else "degrading"
                        if metric_type.value.startswith('cache'):
                            trend_direction = "improving" if correlation > 0 else "degrading"
                    except:
                        trend_strength = 0
                        trend_direction = "stable"
                    
                    trends[metric_type.value] = {
                        'direction': trend_direction,
                        'strength': trend_strength,
                        'recent_values': values[-10:],
                        'data_points': len(values)
                    }
        
        return trends
    
    def _generate_detailed_metrics(self) -> Dict[str, Any]:
        """Generate detailed metrics breakdown."""
        detailed = {}
        
        for window_type in [TimeWindow.ONE_MINUTE, TimeWindow.FIVE_MINUTES, TimeWindow.ONE_HOUR]:
            detailed[window_type.value] = {}
            
            for metric_type in MetricType:
                window = self.time_windows[window_type][metric_type]
                target = self.prd_targets.get(metric_type)
                stats = window.calculate_stats(target)
                
                if stats.count > 0:
                    detailed[window_type.value][metric_type.value] = stats.to_dict()
        
        return detailed
    
    def _analyze_concurrent_user_impact(self) -> Dict[str, Any]:
        """Analyze impact of concurrent users on performance."""
        impact_analysis = {
            'current_concurrent_users': self.concurrent_users,
            'user_count_correlation': {},
            'performance_degradation_thresholds': {},
            'scaling_recommendations': []
        }
        
        # Analyze correlation between user count and performance
        if len(self.concurrent_user_history) >= 10:
            user_counts = [h['count'] for h in list(self.concurrent_user_history)[-50:]]
            
            for metric_type in [MetricType.AUTHENTICATION, MetricType.AUTHORIZATION, MetricType.API_RESPONSE]:
                window = self.time_windows[TimeWindow.ONE_HOUR][metric_type]
                recent_metrics = window.get_metrics()
                
                if len(recent_metrics) >= 10:
                    # Simplified correlation analysis
                    avg_response_time = sum(m.value for m in recent_metrics[-10:]) / 10
                    avg_users = sum(user_counts[-10:]) / 10 if len(user_counts) >= 10 else self.concurrent_users
                    
                    impact_analysis['user_count_correlation'][metric_type.value] = {
                        'current_users': self.concurrent_users,
                        'avg_response_time': avg_response_time,
                        'estimated_per_user_impact': avg_response_time / max(avg_users, 1) if avg_users > 0 else 0
                    }
        
        return impact_analysis
    
    def _generate_recommendations(self) -> List[Dict[str, Any]]:
        """Generate actionable performance recommendations."""
        recommendations = []
        
        # Analyze each metric type and generate specific recommendations
        for metric_type, target in self.prd_targets.items():
            window = self.time_windows[TimeWindow.ONE_HOUR][metric_type]
            stats = window.calculate_stats(target)
            
            if stats.count == 0:
                continue
            
            # Authentication recommendations
            if metric_type == MetricType.AUTHENTICATION and stats.target_compliance < 90:
                recommendations.append({
                    'priority': 'high' if stats.target_compliance < 70 else 'medium',
                    'category': 'authentication',
                    'issue': f'Authentication averaging {stats.mean:.1f}ms (target: <{target.target_value}ms)',
                    'recommendations': [
                        'Implement JWT token caching to reduce validation overhead',
                        'Optimize database queries for user lookup',
                        'Consider connection pooling for authentication service',
                        'Enable L1 cache for user session data'
                    ],
                    'expected_improvement': f'Could reduce response time by 30-50%',
                    'implementation_effort': 'medium'
                })
            
            # Authorization recommendations
            if metric_type == MetricType.AUTHORIZATION and stats.target_compliance < 90:
                recommendations.append({
                    'priority': 'high' if stats.target_compliance < 70 else 'medium',
                    'category': 'authorization',
                    'issue': f'Authorization averaging {stats.mean:.1f}ms (target: <{target.target_value}ms)',
                    'recommendations': [
                        'Implement authorization result caching',
                        'Optimize UUID validation and lookup',
                        'Use database materialized views for permissions',
                        'Implement L2 cache for authorization decisions'
                    ],
                    'expected_improvement': f'Could reduce response time by 40-60%',
                    'implementation_effort': 'high'
                })
            
            # Cache recommendations
            if metric_type.value.startswith('cache') and stats.target_compliance < 90:
                cache_level = metric_type.value.split('_')[1].upper()
                recommendations.append({
                    'priority': 'high' if stats.target_compliance < 80 else 'medium',
                    'category': 'caching',
                    'issue': f'{cache_level} cache hit rate {stats.mean:.1f}% (target: >{target.target_value}%)',
                    'recommendations': [
                        f'Implement intelligent cache warming for {cache_level}',
                        f'Optimize {cache_level} cache key design',
                        f'Increase {cache_level} cache size if memory permits',
                        f'Review {cache_level} cache TTL settings'
                    ],
                    'expected_improvement': f'Could improve hit rate by 10-20%',
                    'implementation_effort': 'medium'
                })
            
            # Database recommendations
            if metric_type == MetricType.DATABASE_QUERY and stats.target_compliance < 90:
                recommendations.append({
                    'priority': 'critical' if stats.target_compliance < 60 else 'high',
                    'category': 'database',
                    'issue': f'Database queries averaging {stats.mean:.1f}ms (target: <{target.target_value}ms)',
                    'recommendations': [
                        'Add missing database indexes for authorization queries',
                        'Implement query result caching',
                        'Optimize connection pool settings',
                        'Consider database query optimization'
                    ],
                    'expected_improvement': f'Could reduce query time by 50-70%',
                    'implementation_effort': 'high'
                })
        
        # System-level recommendations based on concurrent users
        if self.concurrent_users > 100:
            recommendations.append({
                'priority': 'medium',
                'category': 'scalability',
                'issue': f'High concurrent user load ({self.concurrent_users} users)',
                'recommendations': [
                    'Consider horizontal scaling of authentication service',
                    'Implement connection pooling optimization',
                    'Add load balancing for authorization endpoints',
                    'Monitor resource utilization for scaling triggers'
                ],
                'expected_improvement': 'Maintains performance under high load',
                'implementation_effort': 'high'
            })
        
        return recommendations
    
    def _generate_alert_summary(self) -> Dict[str, Any]:
        """Generate alert summary for the report."""
        with self._lock:
            active_by_level = defaultdict(int)
            active_by_type = defaultdict(int)
            
            for alert in self.active_alerts.values():
                active_by_level[alert.level.value] += 1
                active_by_type[alert.metric_type.value] += 1
            
            recent_resolved = [
                alert for alert in self.alert_history
                if alert.resolved and alert.resolution_time 
                and (time.time() - alert.resolution_time) < 3600  # Last hour
            ]
            
            return {
                'active_alerts': {
                    'total': len(self.active_alerts),
                    'by_level': dict(active_by_level),
                    'by_type': dict(active_by_type)
                },
                'resolved_alerts_1h': len(recent_resolved),
                'alert_resolution_time_avg': (
                    sum(alert.duration_seconds for alert in recent_resolved) / len(recent_resolved)
                    if recent_resolved else 0
                ),
                'most_frequent_alert_types': dict(active_by_type)
            }
    
    async def start_monitoring(self):
        """Start background monitoring tasks."""
        if self.monitoring_task is None or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("Performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop background monitoring tasks."""
        self._active = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Performance monitoring stopped")
    
    async def _monitoring_loop(self):
        """Background monitoring loop for trend analysis and cleanup."""
        while self._active:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                # Update trend analysis
                self._update_trend_analysis()
                
                # Cleanup old data
                self._cleanup_old_data()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(60)
    
    def _update_trend_analysis(self):
        """Update trend analysis with current data."""
        # This method would perform more sophisticated trend analysis
        # For now, it's a placeholder for future enhancements
        pass
    
    def _cleanup_old_data(self):
        """Clean up old performance data."""
        with self._lock:
            # Remove old concurrent user history (keep last 1000 entries)
            while len(self.concurrent_user_history) > 1000:
                self.concurrent_user_history.popleft()
            
            # Remove old resolved alerts from history
            cutoff_time = time.time() - (24 * 3600)  # 24 hours
            while (self.alert_history and 
                   self.alert_history[0].timestamp < cutoff_time and
                   self.alert_history[0].resolved):
                self.alert_history.popleft()


# Global performance tracker instance
_performance_tracker: Optional[PerformanceTracker] = None
_tracker_lock = threading.Lock()


def get_performance_tracker() -> PerformanceTracker:
    """Get global performance tracker instance (thread-safe singleton)."""
    global _performance_tracker
    
    if _performance_tracker is None:
        with _tracker_lock:
            if _performance_tracker is None:
                _performance_tracker = PerformanceTracker()
    
    return _performance_tracker


# Context managers for easy performance tracking
class track_performance:
    """Context manager for automatic performance tracking."""
    
    def __init__(self, metric_type: MetricType, operation_name: str, 
                 user_id: Optional[str] = None, endpoint: Optional[str] = None, **metadata):
        self.metric_type = metric_type
        self.operation_name = operation_name
        self.user_id = user_id
        self.endpoint = endpoint
        self.metadata = metadata
        self.start_time = None
        self.tracker = get_performance_tracker()
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        success = exc_type is None
        
        self.tracker.record_metric(
            metric_type=self.metric_type,
            operation_name=self.operation_name,
            value=duration_ms,
            unit="ms",
            success=success,
            user_id=self.user_id,
            endpoint=self.endpoint,
            **self.metadata
        )


# Convenience functions for common tracking scenarios
def track_authentication(operation_name: str, user_id: Optional[str] = None, **metadata):
    """Track authentication operation performance."""
    return track_performance(MetricType.AUTHENTICATION, operation_name, user_id=user_id, **metadata)


def track_authorization(operation_name: str, user_id: Optional[str] = None, **metadata):
    """Track authorization operation performance."""
    return track_performance(MetricType.AUTHORIZATION, operation_name, user_id=user_id, **metadata)


def track_database_query(query_name: str, **metadata):
    """Track database query performance."""
    return track_performance(MetricType.DATABASE_QUERY, query_name, **metadata)


def track_cache_operation(cache_level: str, operation: str, **metadata):
    """Track cache operation performance."""
    cache_type_map = {
        'L1': MetricType.CACHE_L1,
        'L2': MetricType.CACHE_L2,
        'L3': MetricType.CACHE_L3
    }
    metric_type = cache_type_map.get(cache_level.upper(), MetricType.CACHE_L1)
    return track_performance(metric_type, operation, **metadata)


# Performance tracking decorator
def monitor_performance(metric_type: MetricType, operation_name: Optional[str] = None):
    """Decorator for automatic performance monitoring."""
    def decorator(func):
        op_name = operation_name or f"{func.__module__}.{func.__name__}"
        
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with track_performance(metric_type, op_name):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with track_performance(metric_type, op_name):
                    return func(*args, **kwargs)
            return sync_wrapper
    
    return decorator


if __name__ == "__main__":
    # Example usage and testing
    import asyncio
    
    async def example_usage():
        tracker = get_performance_tracker()
        
        # Start monitoring
        await tracker.start_monitoring()
        
        # Simulate some metrics
        tracker.record_metric(MetricType.AUTHENTICATION, "jwt_validation", 45.2, "ms")
        tracker.record_metric(MetricType.AUTHORIZATION, "user_permissions", 67.8, "ms")
        tracker.record_metric(MetricType.CACHE_L1, "user_cache_hit", 96.5, "%")
        tracker.record_metric(MetricType.DATABASE_QUERY, "user_lookup", 23.1, "ms")
        
        # Record concurrent users
        tracker.record_concurrent_users(150)
        
        # Get metrics
        current_metrics = tracker.get_current_metrics()
        health_data = tracker.get_system_health()
        detailed_report = tracker.get_detailed_report()
        
        print("Current Metrics:", json.dumps(current_metrics, indent=2))
        print("Health Data:", json.dumps(health_data, indent=2))
        print("Detailed Report:", json.dumps(detailed_report, indent=2))
        
        # Stop monitoring
        await tracker.stop_monitoring()
    
    # Run example
    # asyncio.run(example_usage())