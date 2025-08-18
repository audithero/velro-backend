"""
Adaptive TTL Manager
Dynamic TTL optimization based on access patterns, data volatility, and performance metrics.

Features:
- Data type-specific TTL strategies
- Access frequency-based TTL adjustment
- Performance-driven TTL optimization
- Cache hit rate feedback loop
- Real-time TTL monitoring and adjustment
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional, List, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import Enum
import statistics

from caching.cache_key_manager import KeyType, AccessPattern
from monitoring.cache_performance_monitor import CachePerformanceMonitor

logger = logging.getLogger(__name__)


class TTLOptimizationStrategy(Enum):
    """TTL optimization strategies."""
    STATIC = "static"                    # Fixed TTL values
    ACCESS_FREQUENCY = "access_frequency"  # Based on access frequency
    PERFORMANCE_DRIVEN = "performance_driven"  # Based on cache performance
    HYBRID = "hybrid"                    # Combination of strategies
    MACHINE_LEARNING = "ml"              # ML-based prediction (future)


class DataVolatility(Enum):
    """Data volatility levels for TTL calculation."""
    VERY_HIGH = "very_high"     # Changes every few seconds (session data)
    HIGH = "high"               # Changes every few minutes (generation status)
    MEDIUM = "medium"           # Changes hourly/daily (user preferences)
    LOW = "low"                 # Changes weekly/monthly (user profile)
    VERY_LOW = "very_low"       # Rarely changes (system config)


@dataclass
class TTLConfiguration:
    """Enhanced TTL configuration with optimization metadata."""
    l1_ttl: int                         # L1 Memory cache TTL (seconds)
    l2_ttl: int                         # L2 Redis cache TTL (seconds)
    l3_ttl: Optional[int] = None        # L3 Database cache TTL (seconds)
    
    # Optimization metadata
    data_volatility: DataVolatility = DataVolatility.MEDIUM
    min_ttl: int = 60                   # Minimum TTL (1 minute)
    max_ttl: int = 7200                 # Maximum TTL (2 hours)
    adjustment_factor: float = 1.0       # TTL adjustment multiplier
    
    # Performance tracking
    hit_rate_threshold: float = 0.9      # Hit rate threshold for adjustments
    access_frequency_threshold: float = 10.0  # Accesses per minute threshold
    last_adjusted: float = 0.0           # Last adjustment timestamp
    adjustment_count: int = 0            # Number of adjustments made


@dataclass
class CacheKeyAnalytics:
    """Analytics data for cache key performance."""
    key_pattern: str
    access_count: int = 0
    hit_count: int = 0
    miss_count: int = 0
    access_times: deque = field(default_factory=lambda: deque(maxlen=100))
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    last_access: float = 0.0
    data_changes_detected: int = 0
    optimal_ttl_calculated: Optional[int] = None
    
    @property
    def hit_rate(self) -> float:
        """Calculate hit rate for this key pattern."""
        total_requests = self.hit_count + self.miss_count
        return (self.hit_count / total_requests) if total_requests > 0 else 0.0
    
    @property
    def access_frequency(self) -> float:
        """Calculate access frequency (accesses per minute)."""
        if len(self.access_times) < 2:
            return 0.0
        
        time_window = self.access_times[-1] - self.access_times[0]
        if time_window <= 0:
            return 0.0
        
        return (len(self.access_times) / time_window) * 60.0
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        return statistics.mean(self.response_times) if self.response_times else 0.0


class AdaptiveTTLManager:
    """
    Adaptive TTL manager that dynamically optimizes cache TTL values based on
    access patterns, performance metrics, and data volatility.
    """
    
    def __init__(self, optimization_strategy: TTLOptimizationStrategy = TTLOptimizationStrategy.HYBRID):
        self.optimization_strategy = optimization_strategy
        
        # TTL configurations by key type and pattern
        self.ttl_configurations: Dict[str, TTLConfiguration] = {}
        self.key_analytics: Dict[str, CacheKeyAnalytics] = {}
        
        # Default TTL configurations for different data types
        self._initialize_default_ttl_configurations()
        
        # Optimization parameters
        self.optimization_config = {
            "min_samples_for_optimization": 10,
            "optimization_interval_seconds": 300,  # 5 minutes
            "hit_rate_target": 0.95,
            "response_time_target_ms": 100.0,
            "adjustment_sensitivity": 0.1,  # How aggressively to adjust TTL
            "performance_window_minutes": 30  # Time window for performance analysis
        }
        
        # Performance tracking
        self.optimization_metrics = {
            "total_adjustments": 0,
            "successful_optimizations": 0,
            "performance_improvements": 0,
            "keys_optimized": 0
        }
        
        # Background optimization
        self.optimization_active = False
        self.optimization_task: Optional[asyncio.Task] = None
    
    def _initialize_default_ttl_configurations(self):
        """Initialize default TTL configurations for different data types."""
        
        # Authorization data - high priority, medium volatility
        self.ttl_configurations["auth:*"] = TTLConfiguration(
            l1_ttl=600,    # 10 minutes
            l2_ttl=1800,   # 30 minutes
            l3_ttl=3600,   # 1 hour
            data_volatility=DataVolatility.MEDIUM,
            min_ttl=300,   # 5 minutes
            max_ttl=7200,  # 2 hours
            hit_rate_threshold=0.95
        )
        
        # User session data - high priority, high volatility
        self.ttl_configurations["session:*"] = TTLConfiguration(
            l1_ttl=300,    # 5 minutes
            l2_ttl=900,    # 15 minutes
            l3_ttl=1800,   # 30 minutes
            data_volatility=DataVolatility.HIGH,
            min_ttl=120,   # 2 minutes
            max_ttl=3600,  # 1 hour
            hit_rate_threshold=0.90
        )
        
        # User profile data - medium priority, low volatility
        self.ttl_configurations["user:*"] = TTLConfiguration(
            l1_ttl=1800,   # 30 minutes
            l2_ttl=7200,   # 2 hours
            l3_ttl=14400,  # 4 hours
            data_volatility=DataVolatility.LOW,
            min_ttl=600,   # 10 minutes
            max_ttl=28800, # 8 hours
            hit_rate_threshold=0.95
        )
        
        # Generation metadata - medium priority, medium volatility
        self.ttl_configurations["gen:*"] = TTLConfiguration(
            l1_ttl=600,    # 10 minutes
            l2_ttl=1800,   # 30 minutes
            l3_ttl=3600,   # 1 hour
            data_volatility=DataVolatility.MEDIUM,
            min_ttl=180,   # 3 minutes
            max_ttl=7200,  # 2 hours
            hit_rate_threshold=0.90
        )
        
        # Team data - medium priority, low volatility
        self.ttl_configurations["team:*"] = TTLConfiguration(
            l1_ttl=1200,   # 20 minutes
            l2_ttl=3600,   # 1 hour
            l3_ttl=7200,   # 2 hours
            data_volatility=DataVolatility.LOW,
            min_ttl=600,   # 10 minutes
            max_ttl=14400, # 4 hours
            hit_rate_threshold=0.95
        )
        
        # System configuration - low priority, very low volatility
        self.ttl_configurations["config:*"] = TTLConfiguration(
            l1_ttl=3600,   # 1 hour
            l2_ttl=14400,  # 4 hours
            l3_ttl=28800,  # 8 hours
            data_volatility=DataVolatility.VERY_LOW,
            min_ttl=1800,  # 30 minutes
            max_ttl=86400, # 24 hours
            hit_rate_threshold=0.98
        )
    
    def get_optimal_ttl(self, cache_key: str, key_type: Optional[KeyType] = None,
                       access_pattern: Optional[AccessPattern] = None) -> TTLConfiguration:
        """
        Get optimal TTL configuration for a cache key based on patterns and analytics.
        """
        # Find matching configuration pattern
        config = self._find_matching_ttl_configuration(cache_key)
        
        if not config:
            # Use default configuration
            config = TTLConfiguration(l1_ttl=300, l2_ttl=900, l3_ttl=1800)
        
        # Apply optimization adjustments if available
        if self.optimization_strategy != TTLOptimizationStrategy.STATIC:
            config = self._apply_optimization_adjustments(cache_key, config, key_type, access_pattern)
        
        return config
    
    def _find_matching_ttl_configuration(self, cache_key: str) -> Optional[TTLConfiguration]:
        """Find TTL configuration matching the cache key pattern."""
        import fnmatch
        
        for pattern, config in self.ttl_configurations.items():
            if fnmatch.fnmatch(cache_key, pattern):
                return config
        
        return None
    
    def _apply_optimization_adjustments(self, cache_key: str, base_config: TTLConfiguration,
                                      key_type: Optional[KeyType], 
                                      access_pattern: Optional[AccessPattern]) -> TTLConfiguration:
        """Apply optimization adjustments to base TTL configuration."""
        
        # Get key pattern for analytics
        key_pattern = self._extract_key_pattern(cache_key)
        analytics = self.key_analytics.get(key_pattern)
        
        if not analytics or analytics.access_count < self.optimization_config["min_samples_for_optimization"]:
            return base_config
        
        # Calculate adjustment factors based on strategy
        adjustment_factors = self._calculate_adjustment_factors(analytics, base_config)
        
        # Apply adjustments
        optimized_config = TTLConfiguration(
            l1_ttl=max(base_config.min_ttl, min(base_config.max_ttl, 
                      int(base_config.l1_ttl * adjustment_factors["l1"]))),
            l2_ttl=max(base_config.min_ttl, min(base_config.max_ttl,
                      int(base_config.l2_ttl * adjustment_factors["l2"]))),
            l3_ttl=base_config.l3_ttl,
            data_volatility=base_config.data_volatility,
            min_ttl=base_config.min_ttl,
            max_ttl=base_config.max_ttl,
            adjustment_factor=max(adjustment_factors["l1"], adjustment_factors["l2"]),
            hit_rate_threshold=base_config.hit_rate_threshold,
            last_adjusted=time.time(),
            adjustment_count=base_config.adjustment_count + 1
        )
        
        # Update base configuration if this is a significant improvement
        if self._is_significant_improvement(base_config, optimized_config, analytics):
            self.ttl_configurations[key_pattern] = optimized_config
            self.optimization_metrics["successful_optimizations"] += 1
        
        return optimized_config
    
    def _calculate_adjustment_factors(self, analytics: CacheKeyAnalytics, 
                                    config: TTLConfiguration) -> Dict[str, float]:
        """Calculate TTL adjustment factors based on analytics and strategy."""
        factors = {"l1": 1.0, "l2": 1.0}
        
        if self.optimization_strategy in [TTLOptimizationStrategy.ACCESS_FREQUENCY, TTLOptimizationStrategy.HYBRID]:
            # Adjust based on access frequency
            frequency_factor = self._calculate_frequency_adjustment_factor(analytics)
            factors["l1"] *= frequency_factor
            factors["l2"] *= frequency_factor
        
        if self.optimization_strategy in [TTLOptimizationStrategy.PERFORMANCE_DRIVEN, TTLOptimizationStrategy.HYBRID]:
            # Adjust based on hit rate performance
            performance_factor = self._calculate_performance_adjustment_factor(analytics, config)
            factors["l1"] *= performance_factor
            factors["l2"] *= performance_factor
        
        # Apply sensitivity limits
        sensitivity = self.optimization_config["adjustment_sensitivity"]
        for key in factors:
            factors[key] = max(1.0 - sensitivity, min(1.0 + sensitivity, factors[key]))
        
        return factors
    
    def _calculate_frequency_adjustment_factor(self, analytics: CacheKeyAnalytics) -> float:
        """Calculate adjustment factor based on access frequency."""
        frequency = analytics.access_frequency
        
        if frequency > 100:  # Very high frequency
            return 1.3  # Increase TTL significantly
        elif frequency > 50:  # High frequency
            return 1.2
        elif frequency > 10:  # Medium frequency
            return 1.1
        elif frequency > 1:   # Low frequency
            return 0.9
        else:                 # Very low frequency
            return 0.8  # Decrease TTL
    
    def _calculate_performance_adjustment_factor(self, analytics: CacheKeyAnalytics,
                                               config: TTLConfiguration) -> float:
        """Calculate adjustment factor based on performance metrics."""
        hit_rate = analytics.hit_rate
        target_hit_rate = config.hit_rate_threshold
        
        if hit_rate >= target_hit_rate:
            # Good performance - can potentially increase TTL
            performance_ratio = hit_rate / target_hit_rate
            return min(1.2, 1.0 + (performance_ratio - 1.0))
        else:
            # Poor performance - should decrease TTL for fresher data
            performance_ratio = hit_rate / target_hit_rate
            return max(0.8, performance_ratio)
    
    def _is_significant_improvement(self, base_config: TTLConfiguration,
                                  optimized_config: TTLConfiguration,
                                  analytics: CacheKeyAnalytics) -> bool:
        """Determine if optimized configuration represents significant improvement."""
        
        # Check if adjustment factor is significant
        if abs(optimized_config.adjustment_factor - 1.0) < 0.05:
            return False
        
        # Check if hit rate is above threshold
        if analytics.hit_rate < base_config.hit_rate_threshold * 0.9:
            return False
        
        # Check if we're not adjusting too frequently
        if (time.time() - base_config.last_adjusted) < 3600:  # 1 hour
            return False
        
        return True
    
    def record_cache_access(self, cache_key: str, hit: bool, response_time_ms: float):
        """Record cache access for analytics and optimization."""
        key_pattern = self._extract_key_pattern(cache_key)
        
        if key_pattern not in self.key_analytics:
            self.key_analytics[key_pattern] = CacheKeyAnalytics(key_pattern=key_pattern)
        
        analytics = self.key_analytics[key_pattern]
        analytics.access_count += 1
        analytics.last_access = time.time()
        analytics.access_times.append(time.time())
        analytics.response_times.append(response_time_ms)
        
        if hit:
            analytics.hit_count += 1
        else:
            analytics.miss_count += 1
    
    def record_data_change(self, cache_key: str):
        """Record data change detection for TTL optimization."""
        key_pattern = self._extract_key_pattern(cache_key)
        
        if key_pattern in self.key_analytics:
            self.key_analytics[key_pattern].data_changes_detected += 1
    
    def _extract_key_pattern(self, cache_key: str) -> str:
        """Extract pattern from cache key for analytics grouping."""
        parts = cache_key.split(":")
        if len(parts) >= 2:
            return f"{parts[0]}:*"
        return cache_key
    
    async def start_optimization(self):
        """Start background TTL optimization process."""
        if self.optimization_active:
            logger.warning("TTL optimization already active")
            return
        
        self.optimization_active = True
        logger.info("Starting adaptive TTL optimization")
        
        loop = asyncio.get_event_loop()
        self.optimization_task = loop.create_task(self._optimization_loop())
    
    async def stop_optimization(self):
        """Stop background TTL optimization process."""
        self.optimization_active = False
        
        if self.optimization_task:
            self.optimization_task.cancel()
            try:
                await self.optimization_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Adaptive TTL optimization stopped")
    
    async def _optimization_loop(self):
        """Background optimization loop."""
        while self.optimization_active:
            try:
                await self._perform_optimization_cycle()
                await asyncio.sleep(self.optimization_config["optimization_interval_seconds"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TTL optimization loop error: {e}")
                await asyncio.sleep(60)
    
    async def _perform_optimization_cycle(self):
        """Perform one cycle of TTL optimization."""
        try:
            optimized_patterns = 0
            current_time = time.time()
            
            for key_pattern, analytics in self.key_analytics.items():
                if analytics.access_count < self.optimization_config["min_samples_for_optimization"]:
                    continue
                
                # Check if pattern needs optimization
                if self._should_optimize_pattern(analytics, current_time):
                    await self._optimize_pattern_ttl(key_pattern, analytics)
                    optimized_patterns += 1
            
            if optimized_patterns > 0:
                logger.info(f"TTL optimization cycle completed: {optimized_patterns} patterns optimized")
                self.optimization_metrics["keys_optimized"] += optimized_patterns
            
        except Exception as e:
            logger.error(f"TTL optimization cycle failed: {e}")
    
    def _should_optimize_pattern(self, analytics: CacheKeyAnalytics, current_time: float) -> bool:
        """Determine if a key pattern should be optimized."""
        # Check if there's enough recent activity
        if current_time - analytics.last_access > 3600:  # 1 hour
            return False
        
        # Check if hit rate is below target
        config = self.ttl_configurations.get(analytics.key_pattern)
        if config and analytics.hit_rate < config.hit_rate_threshold:
            return True
        
        # Check if access pattern has changed significantly
        if analytics.access_frequency > self.optimization_config["hit_rate_target"] * 20:
            return True
        
        return False
    
    async def _optimize_pattern_ttl(self, key_pattern: str, analytics: CacheKeyAnalytics):
        """Optimize TTL for a specific key pattern."""
        try:
            # Calculate optimal TTL based on analytics
            optimal_ttl = self._calculate_optimal_ttl(analytics)
            
            if optimal_ttl and key_pattern in self.ttl_configurations:
                config = self.ttl_configurations[key_pattern]
                
                # Update configuration if significantly different
                if abs(optimal_ttl - config.l1_ttl) > config.l1_ttl * 0.1:  # 10% difference
                    config.l1_ttl = max(config.min_ttl, min(config.max_ttl, optimal_ttl))
                    config.l2_ttl = max(config.min_ttl, min(config.max_ttl, optimal_ttl * 2))
                    config.last_adjusted = time.time()
                    config.adjustment_count += 1
                    
                    analytics.optimal_ttl_calculated = optimal_ttl
                    
                    logger.debug(f"Optimized TTL for pattern {key_pattern}: {optimal_ttl}s")
                    self.optimization_metrics["total_adjustments"] += 1
        
        except Exception as e:
            logger.error(f"Failed to optimize TTL for pattern {key_pattern}: {e}")
    
    def _calculate_optimal_ttl(self, analytics: CacheKeyAnalytics) -> Optional[int]:
        """Calculate optimal TTL based on access patterns and performance."""
        try:
            # Base TTL calculation on access frequency
            frequency = analytics.access_frequency
            
            if frequency <= 0:
                return None
            
            # Calculate base TTL (time between accesses * multiplier)
            base_ttl = max(60, int(60 / frequency))  # At least 1 minute
            
            # Adjust based on hit rate
            hit_rate_adjustment = 1.0
            if analytics.hit_rate > 0:
                hit_rate_adjustment = min(2.0, 1.0 + (analytics.hit_rate - 0.5))
            
            # Adjust based on response time
            response_time_adjustment = 1.0
            if analytics.avg_response_time > 0:
                # Faster response times can support shorter TTL
                if analytics.avg_response_time < 50:  # Very fast
                    response_time_adjustment = 0.8
                elif analytics.avg_response_time > 200:  # Slow
                    response_time_adjustment = 1.3
            
            optimal_ttl = int(base_ttl * hit_rate_adjustment * response_time_adjustment)
            return max(60, min(7200, optimal_ttl))  # Between 1 minute and 2 hours
            
        except Exception as e:
            logger.error(f"Failed to calculate optimal TTL: {e}")
            return None
    
    def get_ttl_analytics(self) -> Dict[str, Any]:
        """Get comprehensive TTL analytics and optimization metrics."""
        analytics_summary = {}
        
        for pattern, analytics in self.key_analytics.items():
            analytics_summary[pattern] = {
                "access_count": analytics.access_count,
                "hit_rate": analytics.hit_rate,
                "access_frequency": analytics.access_frequency,
                "avg_response_time": analytics.avg_response_time,
                "data_changes_detected": analytics.data_changes_detected,
                "optimal_ttl_calculated": analytics.optimal_ttl_calculated,
                "last_access": analytics.last_access
            }
        
        return {
            "optimization_strategy": self.optimization_strategy.value,
            "optimization_metrics": self.optimization_metrics,
            "key_analytics": analytics_summary,
            "total_patterns_tracked": len(self.key_analytics),
            "total_configurations": len(self.ttl_configurations),
            "optimization_active": self.optimization_active,
            "optimization_config": self.optimization_config
        }
    
    def get_recommended_ttl_adjustments(self) -> Dict[str, Dict[str, Any]]:
        """Get recommended TTL adjustments for manual review."""
        recommendations = {}
        
        for pattern, analytics in self.key_analytics.items():
            if analytics.access_count < 10:
                continue
            
            config = self.ttl_configurations.get(pattern)
            if not config:
                continue
            
            optimal_ttl = self._calculate_optimal_ttl(analytics)
            if optimal_ttl and abs(optimal_ttl - config.l1_ttl) > config.l1_ttl * 0.2:
                recommendations[pattern] = {
                    "current_l1_ttl": config.l1_ttl,
                    "current_l2_ttl": config.l2_ttl,
                    "recommended_l1_ttl": optimal_ttl,
                    "recommended_l2_ttl": optimal_ttl * 2,
                    "reason": self._generate_recommendation_reason(analytics, config),
                    "confidence": self._calculate_recommendation_confidence(analytics),
                    "analytics": {
                        "hit_rate": analytics.hit_rate,
                        "access_frequency": analytics.access_frequency,
                        "avg_response_time": analytics.avg_response_time
                    }
                }
        
        return recommendations
    
    def _generate_recommendation_reason(self, analytics: CacheKeyAnalytics,
                                      config: TTLConfiguration) -> str:
        """Generate human-readable reason for TTL recommendation."""
        reasons = []
        
        if analytics.hit_rate < config.hit_rate_threshold:
            reasons.append(f"Hit rate ({analytics.hit_rate:.1%}) below target ({config.hit_rate_threshold:.1%})")
        
        if analytics.access_frequency > 50:
            reasons.append("High access frequency detected")
        elif analytics.access_frequency < 1:
            reasons.append("Low access frequency detected")
        
        if analytics.avg_response_time > 100:
            reasons.append("High response times detected")
        
        return "; ".join(reasons) if reasons else "Performance optimization opportunity"
    
    def _calculate_recommendation_confidence(self, analytics: CacheKeyAnalytics) -> float:
        """Calculate confidence score for TTL recommendation."""
        confidence = 0.0
        
        # Sample size confidence
        if analytics.access_count > 100:
            confidence += 0.4
        elif analytics.access_count > 50:
            confidence += 0.3
        elif analytics.access_count > 10:
            confidence += 0.2
        
        # Consistency confidence
        if len(analytics.response_times) > 10:
            response_time_consistency = 1.0 - (statistics.stdev(analytics.response_times) / 
                                             max(1, statistics.mean(analytics.response_times)))
            confidence += min(0.3, response_time_consistency * 0.3)
        
        # Recent activity confidence
        if time.time() - analytics.last_access < 3600:  # Last hour
            confidence += 0.3
        
        return min(1.0, confidence)


# Global adaptive TTL manager instance
adaptive_ttl_manager: Optional[AdaptiveTTLManager] = None


def get_adaptive_ttl_manager(strategy: TTLOptimizationStrategy = TTLOptimizationStrategy.HYBRID) -> AdaptiveTTLManager:
    """Get or create global adaptive TTL manager."""
    global adaptive_ttl_manager
    if adaptive_ttl_manager is None:
        adaptive_ttl_manager = AdaptiveTTLManager(strategy)
    return adaptive_ttl_manager


# Convenience functions
async def start_ttl_optimization():
    """Start adaptive TTL optimization."""
    manager = get_adaptive_ttl_manager()
    await manager.start_optimization()


async def stop_ttl_optimization():
    """Stop adaptive TTL optimization."""
    if adaptive_ttl_manager:
        await adaptive_ttl_manager.stop_optimization()


def get_optimal_ttl_for_key(cache_key: str) -> TTLConfiguration:
    """Get optimal TTL configuration for a cache key."""
    manager = get_adaptive_ttl_manager()
    return manager.get_optimal_ttl(cache_key)


def record_cache_performance(cache_key: str, hit: bool, response_time_ms: float):
    """Record cache performance for TTL optimization."""
    if adaptive_ttl_manager:
        adaptive_ttl_manager.record_cache_access(cache_key, hit, response_time_ms)


def get_ttl_optimization_report() -> Dict[str, Any]:
    """Get comprehensive TTL optimization report."""
    if not adaptive_ttl_manager:
        return {"error": "Adaptive TTL manager not initialized"}
    
    return adaptive_ttl_manager.get_ttl_analytics()


def get_ttl_recommendations() -> Dict[str, Dict[str, Any]]:
    """Get recommended TTL adjustments for manual review."""
    if not adaptive_ttl_manager:
        return {"error": "Adaptive TTL manager not initialized"}
    
    return adaptive_ttl_manager.get_recommended_ttl_adjustments()