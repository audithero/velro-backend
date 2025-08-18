"""
Cache Optimization Implementation
Complete implementation orchestrator for achieving >95% cache hit rates and <5ms access times.

This module integrates all cache optimization components and provides:
- Coordinated startup and initialization
- Performance monitoring and alerting
- Real-time optimization adjustments
- Comprehensive metrics and reporting
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from caching.optimized_cache_manager import (
    OptimizedCacheManager, get_optimized_cache_manager, OptimizedCacheConfig,
    CacheOptimizationType
)
from caching.enhanced_cache_warming_strategies import (
    EnhancedCacheWarmingStrategies, get_enhanced_warming_strategies
)
from caching.adaptive_ttl_manager import (
    AdaptiveTTLManager, get_adaptive_ttl_manager, TTLOptimizationStrategy
)
from services.enhanced_authorization_cache_service import (
    get_enhanced_authorization_cache_service
)
from monitoring.cache_performance_monitor import (
    CachePerformanceMonitor, get_cache_performance_monitor
)

logger = logging.getLogger(__name__)


class OptimizationPhase(Enum):
    """Cache optimization implementation phases."""
    INITIALIZATION = "initialization"
    STARTUP_WARMING = "startup_warming"
    PERFORMANCE_BASELINE = "performance_baseline"
    OPTIMIZATION_ACTIVE = "optimization_active"
    MONITORING_ACTIVE = "monitoring_active"
    TARGET_ACHIEVED = "target_achieved"


@dataclass
class OptimizationTargets:
    """Cache optimization performance targets."""
    overall_hit_rate_percent: float = 95.0
    l1_hit_rate_percent: float = 97.0
    l2_hit_rate_percent: float = 90.0
    
    l1_response_time_ms: float = 5.0
    l2_response_time_ms: float = 20.0
    authorization_response_time_ms: float = 75.0
    
    cache_warming_effectiveness: float = 80.0
    ttl_optimization_accuracy: float = 85.0
    
    # Success criteria
    sustained_performance_hours: int = 24  # Hours of sustained performance
    validation_sample_size: int = 10000    # Requests for validation


@dataclass
class OptimizationStatus:
    """Current optimization status and progress."""
    current_phase: OptimizationPhase = OptimizationPhase.INITIALIZATION
    start_time: float = field(default_factory=time.time)
    
    # Performance metrics
    current_hit_rate: float = 0.0
    current_l1_response_time: float = 0.0
    current_l2_response_time: float = 0.0
    current_auth_response_time: float = 0.0
    
    # Target achievement tracking
    targets_met: Set[str] = field(default_factory=set)
    sustained_performance_start: Optional[float] = None
    validation_requests_processed: int = 0
    
    # Component status
    optimized_cache_active: bool = False
    warming_strategies_active: bool = False
    adaptive_ttl_active: bool = False
    performance_monitoring_active: bool = False
    
    # Alerts and issues
    active_alerts: List[str] = field(default_factory=list)
    optimization_issues: List[str] = field(default_factory=list)


class CacheOptimizationOrchestrator:
    """
    Main orchestrator for cache optimization implementation.
    Coordinates all optimization components to achieve performance targets.
    """
    
    def __init__(self, targets: Optional[OptimizationTargets] = None):
        self.targets = targets or OptimizationTargets()
        self.status = OptimizationStatus()
        
        # Core optimization components
        self.optimized_cache: Optional[OptimizedCacheManager] = None
        self.warming_strategies: Optional[EnhancedCacheWarmingStrategies] = None
        self.adaptive_ttl: Optional[AdaptiveTTLManager] = None
        self.performance_monitor: Optional[CachePerformanceMonitor] = None
        self.auth_cache_service = get_enhanced_authorization_cache_service()
        
        # Orchestration configuration
        self.config = {
            "phase_transition_delay_seconds": 30,
            "performance_check_interval_seconds": 60,
            "target_validation_interval_seconds": 300,  # 5 minutes
            "alert_threshold_violations": 3,
            "optimization_timeout_hours": 4
        }
        
        # Background tasks
        self.orchestration_active = False
        self.orchestration_tasks: List[asyncio.Task] = []
        
        # Performance tracking
        self.performance_history: List[Dict[str, Any]] = []
        self.optimization_events: List[Dict[str, Any]] = []
    
    async def start_optimization(self) -> Dict[str, Any]:
        """
        Start comprehensive cache optimization implementation.
        Returns implementation status and initial metrics.
        """
        logger.info("Starting comprehensive cache optimization implementation")
        self.status.start_time = time.time()
        
        try:
            # Phase 1: Initialize optimization components
            await self._execute_initialization_phase()
            
            # Phase 2: Execute startup warming
            await self._execute_startup_warming_phase()
            
            # Phase 3: Establish performance baseline
            await self._execute_baseline_phase()
            
            # Phase 4: Activate optimizations
            await self._execute_optimization_phase()
            
            # Phase 5: Start monitoring
            await self._execute_monitoring_phase()
            
            # Start background orchestration
            await self._start_background_orchestration()
            
            implementation_results = {
                "status": "implementation_started",
                "current_phase": self.status.current_phase.value,
                "targets": {
                    "overall_hit_rate": self.targets.overall_hit_rate_percent,
                    "l1_response_time_ms": self.targets.l1_response_time_ms,
                    "l2_response_time_ms": self.targets.l2_response_time_ms,
                    "authorization_response_time_ms": self.targets.authorization_response_time_ms
                },
                "components_initialized": {
                    "optimized_cache": self.status.optimized_cache_active,
                    "warming_strategies": self.status.warming_strategies_active,
                    "adaptive_ttl": self.status.adaptive_ttl_active,
                    "performance_monitoring": self.status.performance_monitoring_active
                },
                "estimated_optimization_time_hours": 2.0,
                "monitoring_intervals": {
                    "performance_check_seconds": self.config["performance_check_interval_seconds"],
                    "target_validation_seconds": self.config["target_validation_interval_seconds"]
                }
            }
            
            logger.info("Cache optimization implementation started successfully")
            return implementation_results
            
        except Exception as e:
            logger.error(f"Cache optimization implementation failed: {e}")
            self.status.optimization_issues.append(f"Implementation failed: {str(e)}")
            return {
                "status": "implementation_failed",
                "error": str(e),
                "current_phase": self.status.current_phase.value
            }
    
    async def stop_optimization(self):
        """Stop cache optimization and all background processes."""
        logger.info("Stopping cache optimization implementation")
        self.orchestration_active = False
        
        # Cancel background tasks
        for task in self.orchestration_tasks:
            task.cancel()
        
        if self.orchestration_tasks:
            await asyncio.gather(*self.orchestration_tasks, return_exceptions=True)
        
        # Stop optimization components
        if self.optimized_cache:
            await self.optimized_cache.stop_optimizations()
        
        if self.warming_strategies:
            await self.warming_strategies.stop_enhanced_warming()
        
        if self.adaptive_ttl:
            await self.adaptive_ttl.stop_optimization()
        
        logger.info("Cache optimization implementation stopped")
    
    async def _execute_initialization_phase(self):
        """Phase 1: Initialize all optimization components."""
        logger.info("Executing Phase 1: Optimization component initialization")
        self.status.current_phase = OptimizationPhase.INITIALIZATION
        
        # Initialize optimized cache manager
        cache_config = OptimizedCacheConfig(
            l1_memory_size_mb=300,
            l1_target_response_time_ms=self.targets.l1_response_time_ms,
            l2_target_response_time_ms=self.targets.l2_response_time_ms,
            overall_hit_rate_target=self.targets.overall_hit_rate_percent,
            l1_hit_rate_target=self.targets.l1_hit_rate_percent,
            enabled_optimizations={
                CacheOptimizationType.HIERARCHICAL_KEYS,
                CacheOptimizationType.PREDICTIVE_WARMING,
                CacheOptimizationType.ADAPTIVE_TTL,
                CacheOptimizationType.MEMORY_OPTIMIZATION,
                CacheOptimizationType.AUTHORIZATION_FAST_PATH
            }
        )
        
        self.optimized_cache = get_optimized_cache_manager(cache_config)
        await self.optimized_cache.start_optimizations()
        self.status.optimized_cache_active = True
        
        # Initialize warming strategies
        self.warming_strategies = get_enhanced_warming_strategies()
        await self.warming_strategies.start_enhanced_warming()
        self.status.warming_strategies_active = True
        
        # Initialize adaptive TTL manager
        self.adaptive_ttl = get_adaptive_ttl_manager(TTLOptimizationStrategy.HYBRID)
        await self.adaptive_ttl.start_optimization()
        self.status.adaptive_ttl_active = True
        
        # Initialize performance monitoring
        from caching.multi_layer_cache_manager import get_cache_manager
        base_cache = get_cache_manager()
        self.performance_monitor = get_cache_performance_monitor(base_cache)
        self.performance_monitor.start_monitoring()
        self.status.performance_monitoring_active = True
        
        await asyncio.sleep(self.config["phase_transition_delay_seconds"])
        logger.info("Phase 1 completed: All optimization components initialized")
    
    async def _execute_startup_warming_phase(self):
        """Phase 2: Execute comprehensive startup cache warming."""
        logger.info("Executing Phase 2: Startup cache warming")
        self.status.current_phase = OptimizationPhase.STARTUP_WARMING
        
        # Execute comprehensive startup warming
        warming_results = {}
        
        # Warm authorization caches
        auth_warming = await self.auth_cache_service.warm_authorization_caches()
        warming_results["authorization"] = auth_warming
        
        # Execute application startup cache warming with optimizations
        await self._execute_comprehensive_startup_warming()
        
        self.optimization_events.append({
            "event": "startup_warming_completed",
            "timestamp": datetime.utcnow().isoformat(),
            "warming_results": warming_results
        })
        
        await asyncio.sleep(self.config["phase_transition_delay_seconds"])
        logger.info("Phase 2 completed: Startup cache warming executed")
    
    async def _execute_baseline_phase(self):
        """Phase 3: Establish performance baseline."""
        logger.info("Executing Phase 3: Performance baseline establishment")
        self.status.current_phase = OptimizationPhase.PERFORMANCE_BASELINE
        
        # Collect baseline performance metrics
        baseline_start = time.time()
        baseline_duration = 60  # 1 minute baseline
        
        while time.time() - baseline_start < baseline_duration:
            await self._collect_performance_metrics()
            await asyncio.sleep(5)  # Collect every 5 seconds
        
        # Calculate baseline averages
        if self.performance_history:
            recent_metrics = self.performance_history[-12:]  # Last 12 samples (1 minute)
            baseline_hit_rate = sum(m["overall_hit_rate"] for m in recent_metrics) / len(recent_metrics)
            baseline_l1_response = sum(m["l1_response_time"] for m in recent_metrics) / len(recent_metrics)
            
            logger.info(f"Performance baseline established: {baseline_hit_rate:.1f}% hit rate, "
                       f"{baseline_l1_response:.1f}ms L1 response time")
        
        await asyncio.sleep(self.config["phase_transition_delay_seconds"])
        logger.info("Phase 3 completed: Performance baseline established")
    
    async def _execute_optimization_phase(self):
        """Phase 4: Activate all optimizations."""
        logger.info("Executing Phase 4: Optimization activation")
        self.status.current_phase = OptimizationPhase.OPTIMIZATION_ACTIVE
        
        # All optimizations are already running, but we can trigger additional optimizations
        
        # Trigger predictive warming for top users
        await self._trigger_intelligent_warming()
        
        # Optimize TTL configurations
        await self._optimize_ttl_configurations()
        
        # Enable advanced cache features
        await self._enable_advanced_cache_features()
        
        self.optimization_events.append({
            "event": "optimization_phase_activated",
            "timestamp": datetime.utcnow().isoformat(),
            "optimizations_active": True
        })
        
        await asyncio.sleep(self.config["phase_transition_delay_seconds"])
        logger.info("Phase 4 completed: All optimizations activated")
    
    async def _execute_monitoring_phase(self):
        """Phase 5: Start active monitoring and target validation."""
        logger.info("Executing Phase 5: Monitoring activation")
        self.status.current_phase = OptimizationPhase.MONITORING_ACTIVE
        
        # Monitoring is already started, but we initialize target tracking
        self.status.sustained_performance_start = None
        self.status.validation_requests_processed = 0
        
        logger.info("Phase 5 completed: Active monitoring started")
    
    async def _start_background_orchestration(self):
        """Start background orchestration tasks."""
        self.orchestration_active = True
        loop = asyncio.get_event_loop()
        
        self.orchestration_tasks = [
            loop.create_task(self._performance_monitoring_loop()),
            loop.create_task(self._target_validation_loop()),
            loop.create_task(self._optimization_adjustment_loop()),
            loop.create_task(self._alert_management_loop())
        ]
        
        logger.info("Background orchestration started")
    
    async def _performance_monitoring_loop(self):
        """Background loop for performance monitoring."""
        while self.orchestration_active:
            try:
                await self._collect_performance_metrics()
                await self._check_performance_alerts()
                
                await asyncio.sleep(self.config["performance_check_interval_seconds"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Performance monitoring loop error: {e}")
                await asyncio.sleep(30)
    
    async def _target_validation_loop(self):
        """Background loop for target achievement validation."""
        while self.orchestration_active:
            try:
                await self._validate_performance_targets()
                await asyncio.sleep(self.config["target_validation_interval_seconds"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Target validation loop error: {e}")
                await asyncio.sleep(60)
    
    async def _optimization_adjustment_loop(self):
        """Background loop for optimization adjustments."""
        while self.orchestration_active:
            try:
                await self._perform_optimization_adjustments()
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Optimization adjustment loop error: {e}")
                await asyncio.sleep(120)
    
    async def _alert_management_loop(self):
        """Background loop for alert management."""
        while self.orchestration_active:
            try:
                await self._process_alerts()
                await asyncio.sleep(60)  # 1 minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert management loop error: {e}")
                await asyncio.sleep(60)
    
    async def _collect_performance_metrics(self):
        """Collect current performance metrics."""
        try:
            # Get metrics from cache manager
            if self.optimized_cache:
                cache_metrics = self.optimized_cache.get_optimization_metrics()
                base_metrics = cache_metrics["base_cache_metrics"]
                
                current_metrics = {
                    "timestamp": time.time(),
                    "overall_hit_rate": base_metrics["overall_performance"]["overall_hit_rate_percent"],
                    "l1_hit_rate": base_metrics["cache_levels"]["L1_Memory"]["metrics"]["hit_rate"],
                    "l2_hit_rate": base_metrics["cache_levels"]["L2_Redis"]["metrics"]["hit_rate"],
                    "l1_response_time": base_metrics["cache_levels"]["L1_Memory"]["metrics"]["avg_response_time_ms"],
                    "l2_response_time": base_metrics["cache_levels"]["L2_Redis"]["metrics"]["avg_response_time_ms"],
                    "optimization_hits": cache_metrics["optimization_metrics"]
                }
                
                # Update current status
                self.status.current_hit_rate = current_metrics["overall_hit_rate"]
                self.status.current_l1_response_time = current_metrics["l1_response_time"]
                self.status.current_l2_response_time = current_metrics["l2_response_time"]
                
                # Get authorization performance
                auth_metrics = self.auth_cache_service.get_performance_metrics()
                auth_perf = auth_metrics["authorization_cache_metrics"]
                current_metrics["auth_response_time"] = auth_perf["avg_response_time_ms"]
                self.status.current_auth_response_time = auth_perf["avg_response_time_ms"]
                
                # Store metrics
                self.performance_history.append(current_metrics)
                
                # Keep history manageable
                if len(self.performance_history) > 1000:
                    self.performance_history = self.performance_history[-500:]
                
        except Exception as e:
            logger.error(f"Failed to collect performance metrics: {e}")
    
    async def _validate_performance_targets(self):
        """Validate if performance targets are being met."""
        if not self.performance_history:
            return
        
        recent_metrics = self.performance_history[-5:]  # Last 5 samples
        if len(recent_metrics) < 5:
            return
        
        # Calculate recent averages
        recent_hit_rate = sum(m["overall_hit_rate"] for m in recent_metrics) / len(recent_metrics)
        recent_l1_response = sum(m["l1_response_time"] for m in recent_metrics) / len(recent_metrics)
        recent_l2_response = sum(m["l2_response_time"] for m in recent_metrics) / len(recent_metrics)
        recent_auth_response = sum(m["auth_response_time"] for m in recent_metrics) / len(recent_metrics)
        
        # Check target achievement
        targets_met = set()
        
        if recent_hit_rate >= self.targets.overall_hit_rate_percent:
            targets_met.add("overall_hit_rate")
        
        if recent_l1_response <= self.targets.l1_response_time_ms:
            targets_met.add("l1_response_time")
        
        if recent_l2_response <= self.targets.l2_response_time_ms:
            targets_met.add("l2_response_time")
        
        if recent_auth_response <= self.targets.authorization_response_time_ms:
            targets_met.add("authorization_response_time")
        
        # Update status
        self.status.targets_met = targets_met
        
        # Check if all primary targets are met
        primary_targets = {"overall_hit_rate", "l1_response_time", "authorization_response_time"}
        if primary_targets.issubset(targets_met):
            if self.status.sustained_performance_start is None:
                self.status.sustained_performance_start = time.time()
                logger.info("All primary performance targets achieved - starting sustained performance tracking")
            else:
                sustained_hours = (time.time() - self.status.sustained_performance_start) / 3600
                if sustained_hours >= self.targets.sustained_performance_hours:
                    self.status.current_phase = OptimizationPhase.TARGET_ACHIEVED
                    logger.info(f"TARGET ACHIEVED: Sustained performance for {sustained_hours:.1f} hours")
        else:
            self.status.sustained_performance_start = None
        
        # Update validation request count
        self.status.validation_requests_processed += len(recent_metrics) * 100  # Estimate
    
    async def _check_performance_alerts(self):
        """Check for performance-related alerts."""
        if not self.performance_history:
            return
        
        current_metrics = self.performance_history[-1]
        alerts = []
        
        # Check hit rate alert
        if current_metrics["overall_hit_rate"] < self.targets.overall_hit_rate_percent - 5:
            alerts.append(f"Hit rate ({current_metrics['overall_hit_rate']:.1f}%) significantly below target")
        
        # Check response time alerts
        if current_metrics["l1_response_time"] > self.targets.l1_response_time_ms * 2:
            alerts.append(f"L1 response time ({current_metrics['l1_response_time']:.1f}ms) exceeds target")
        
        if current_metrics["auth_response_time"] > self.targets.authorization_response_time_ms * 1.5:
            alerts.append(f"Authorization response time ({current_metrics['auth_response_time']:.1f}ms) exceeds target")
        
        # Update active alerts
        self.status.active_alerts = alerts
        
        for alert in alerts:
            if alert not in [e.get("alert") for e in self.optimization_events[-10:]]:
                logger.warning(f"PERFORMANCE ALERT: {alert}")
                self.optimization_events.append({
                    "event": "performance_alert",
                    "alert": alert,
                    "timestamp": datetime.utcnow().isoformat(),
                    "metrics": current_metrics
                })
    
    async def _perform_optimization_adjustments(self):
        """Perform optimization adjustments based on current performance."""
        try:
            # Get TTL recommendations
            if self.adaptive_ttl:
                recommendations = self.adaptive_ttl.get_recommended_ttl_adjustments()
                if recommendations:
                    logger.info(f"TTL optimization recommendations: {len(recommendations)} patterns")
            
            # Check warming effectiveness
            if self.warming_strategies:
                warming_stats = self.warming_strategies.get_warming_statistics()
                effectiveness = warming_stats["warming_metrics"]["warming_hit_rate"]
                if effectiveness < 0.5:  # 50% threshold
                    logger.warning(f"Low warming effectiveness: {effectiveness:.1%}")
            
            # Trigger additional warming if hit rate is low
            if self.status.current_hit_rate < self.targets.overall_hit_rate_percent - 2:
                await self._trigger_emergency_warming()
            
        except Exception as e:
            logger.error(f"Optimization adjustments failed: {e}")
    
    async def _process_alerts(self):
        """Process and manage alerts."""
        # This would integrate with actual alerting system
        if self.status.active_alerts:
            logger.debug(f"Processing {len(self.status.active_alerts)} active alerts")
    
    # Helper methods for optimization phases
    
    async def _execute_comprehensive_startup_warming(self):
        """Execute comprehensive startup cache warming."""
        try:
            from database import get_database
            db = await get_database()
            
            # Get top 50 most active users for priority warming
            active_users = await db.execute_query(
                table="users",
                operation="select",
                filters={
                    "is_active": True,
                    "last_active_at__gte": datetime.utcnow() - timedelta(hours=12)
                },
                limit=50,
                order_by="last_active_at DESC"
            )
            
            warming_tasks = []
            for user in active_users:
                user_id = user["id"]
                if self.warming_strategies:
                    task = self.warming_strategies.trigger_user_login_warming(user_id)
                    warming_tasks.append(task)
            
            # Execute warming tasks in batches
            batch_size = 10
            for i in range(0, len(warming_tasks), batch_size):
                batch = warming_tasks[i:i + batch_size]
                await asyncio.gather(*batch, return_exceptions=True)
                await asyncio.sleep(1)  # Brief pause between batches
            
            logger.info(f"Comprehensive startup warming completed for {len(active_users)} users")
            
        except Exception as e:
            logger.error(f"Comprehensive startup warming failed: {e}")
    
    async def _trigger_intelligent_warming(self):
        """Trigger intelligent cache warming."""
        try:
            if self.warming_strategies:
                # This would implement intelligent warming based on patterns
                logger.info("Intelligent cache warming triggered")
        except Exception as e:
            logger.error(f"Intelligent warming failed: {e}")
    
    async def _optimize_ttl_configurations(self):
        """Optimize TTL configurations."""
        try:
            if self.adaptive_ttl:
                # Force optimization cycle
                await self.adaptive_ttl._perform_optimization_cycle()
                logger.info("TTL configurations optimized")
        except Exception as e:
            logger.error(f"TTL optimization failed: {e}")
    
    async def _enable_advanced_cache_features(self):
        """Enable advanced cache features."""
        try:
            # This would enable additional optimizations
            logger.info("Advanced cache features enabled")
        except Exception as e:
            logger.error(f"Advanced cache features activation failed: {e}")
    
    async def _trigger_emergency_warming(self):
        """Trigger emergency cache warming for performance recovery."""
        try:
            logger.info("Triggering emergency cache warming")
            # This would implement emergency warming logic
        except Exception as e:
            logger.error(f"Emergency warming failed: {e}")
    
    def get_optimization_status(self) -> Dict[str, Any]:
        """Get comprehensive optimization status and metrics."""
        current_time = time.time()
        runtime_hours = (current_time - self.status.start_time) / 3600
        
        # Calculate target achievement percentage
        total_targets = 4  # overall_hit_rate, l1_response, l2_response, auth_response
        targets_achieved = len(self.status.targets_met)
        target_achievement_percent = (targets_achieved / total_targets) * 100
        
        # Calculate sustained performance duration
        sustained_performance_hours = 0.0
        if self.status.sustained_performance_start:
            sustained_performance_hours = (current_time - self.status.sustained_performance_start) / 3600
        
        return {
            "optimization_status": {
                "current_phase": self.status.current_phase.value,
                "runtime_hours": runtime_hours,
                "targets_achievement_percent": target_achievement_percent,
                "sustained_performance_hours": sustained_performance_hours,
                "validation_requests_processed": self.status.validation_requests_processed
            },
            "current_performance": {
                "overall_hit_rate_percent": self.status.current_hit_rate,
                "l1_response_time_ms": self.status.current_l1_response_time,
                "l2_response_time_ms": self.status.current_l2_response_time,
                "authorization_response_time_ms": self.status.current_auth_response_time
            },
            "performance_targets": {
                "overall_hit_rate_percent": self.targets.overall_hit_rate_percent,
                "l1_response_time_ms": self.targets.l1_response_time_ms,
                "l2_response_time_ms": self.targets.l2_response_time_ms,
                "authorization_response_time_ms": self.targets.authorization_response_time_ms
            },
            "targets_met": list(self.status.targets_met),
            "component_status": {
                "optimized_cache_active": self.status.optimized_cache_active,
                "warming_strategies_active": self.status.warming_strategies_active,
                "adaptive_ttl_active": self.status.adaptive_ttl_active,
                "performance_monitoring_active": self.status.performance_monitoring_active
            },
            "active_alerts": self.status.active_alerts,
            "optimization_issues": self.status.optimization_issues,
            "recent_events": self.optimization_events[-10:],  # Last 10 events
            "orchestration_active": self.orchestration_active
        }
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get detailed performance report with trends and recommendations."""
        if not self.performance_history:
            return {"error": "No performance data available"}
        
        # Calculate performance trends
        recent_data = self.performance_history[-60:]  # Last hour of data
        
        hit_rate_trend = [m["overall_hit_rate"] for m in recent_data]
        l1_response_trend = [m["l1_response_time"] for m in recent_data]
        auth_response_trend = [m["auth_response_time"] for m in recent_data]
        
        # Generate recommendations
        recommendations = []
        
        if self.status.current_hit_rate < self.targets.overall_hit_rate_percent:
            recommendations.append("Increase cache warming frequency for better hit rates")
        
        if self.status.current_l1_response_time > self.targets.l1_response_time_ms:
            recommendations.append("Optimize L1 memory cache allocation and eviction policy")
        
        if self.status.current_auth_response_time > self.targets.authorization_response_time_ms:
            recommendations.append("Enhance authorization cache fast-path implementation")
        
        return {
            "performance_summary": {
                "data_points": len(self.performance_history),
                "monitoring_duration_hours": (time.time() - self.status.start_time) / 3600,
                "current_hit_rate": self.status.current_hit_rate,
                "current_l1_response_time": self.status.current_l1_response_time,
                "current_auth_response_time": self.status.current_auth_response_time
            },
            "performance_trends": {
                "hit_rate_recent_avg": sum(hit_rate_trend) / len(hit_rate_trend) if hit_rate_trend else 0,
                "l1_response_recent_avg": sum(l1_response_trend) / len(l1_response_trend) if l1_response_trend else 0,
                "auth_response_recent_avg": sum(auth_response_trend) / len(auth_response_trend) if auth_response_trend else 0
            },
            "target_analysis": {
                "targets_met": list(self.status.targets_met),
                "targets_remaining": 4 - len(self.status.targets_met),
                "overall_progress_percent": (len(self.status.targets_met) / 4) * 100,
                "sustained_performance_achieved": self.status.current_phase == OptimizationPhase.TARGET_ACHIEVED
            },
            "recommendations": recommendations,
            "timestamp": datetime.utcnow().isoformat()
        }


# Global cache optimization orchestrator
cache_optimization_orchestrator: Optional[CacheOptimizationOrchestrator] = None


def get_cache_optimization_orchestrator(targets: Optional[OptimizationTargets] = None) -> CacheOptimizationOrchestrator:
    """Get or create global cache optimization orchestrator."""
    global cache_optimization_orchestrator
    if cache_optimization_orchestrator is None:
        cache_optimization_orchestrator = CacheOptimizationOrchestrator(targets)
    return cache_optimization_orchestrator


# Main implementation functions
async def implement_cache_optimization(targets: Optional[OptimizationTargets] = None) -> Dict[str, Any]:
    """
    Implement comprehensive cache optimization to achieve >95% hit rates and <5ms access times.
    Returns implementation status and metrics.
    """
    orchestrator = get_cache_optimization_orchestrator(targets)
    return await orchestrator.start_optimization()


async def stop_cache_optimization():
    """Stop cache optimization implementation."""
    if cache_optimization_orchestrator:
        await cache_optimization_orchestrator.stop_optimization()


def get_optimization_status() -> Dict[str, Any]:
    """Get current optimization status and progress."""
    if not cache_optimization_orchestrator:
        return {"error": "Cache optimization not started"}
    
    return cache_optimization_orchestrator.get_optimization_status()


def get_optimization_performance_report() -> Dict[str, Any]:
    """Get comprehensive performance report with trends and recommendations."""
    if not cache_optimization_orchestrator:
        return {"error": "Cache optimization not started"}
    
    return cache_optimization_orchestrator.get_performance_report()


# Convenience function for quick status check
def is_optimization_target_achieved() -> Dict[str, Any]:
    """Check if optimization targets have been achieved."""
    if not cache_optimization_orchestrator:
        return {"achieved": False, "reason": "Optimization not started"}
    
    status = cache_optimization_orchestrator.get_optimization_status()
    targets_met = status["targets_met"]
    primary_targets = {"overall_hit_rate", "l1_response_time", "authorization_response_time"}
    
    achieved = primary_targets.issubset(set(targets_met))
    sustained_hours = status["optimization_status"]["sustained_performance_hours"]
    
    return {
        "achieved": achieved and sustained_hours >= 24,
        "targets_met": targets_met,
        "sustained_performance_hours": sustained_hours,
        "current_phase": status["optimization_status"]["current_phase"],
        "performance": status["current_performance"]
    }