"""
Optimized Cache Manager for >95% Hit Rates and <5ms Access Times
High-performance cache implementation with enhanced key patterns, warming strategies,
and performance optimizations specifically designed for Velro AI Platform.

Key Features:
- Hierarchical cache key patterns for efficient lookups
- Intelligent warming based on user behavior patterns
- Adaptive TTL with access frequency optimization
- Enhanced authorization caching integration
- Sub-5ms L1 cache access times
- >95% target cache hit rates
"""

import asyncio
import logging
import time
import json
import hashlib
from typing import Dict, Any, Optional, List, Tuple, Set, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
from enum import Enum
from uuid import UUID
import threading
import weakref
from contextlib import asynccontextmanager

from caching.multi_layer_cache_manager import (
    MultiLayerCacheManager, get_cache_manager, CacheLevel, CacheOperation
)
from caching.cache_key_manager import (
    CacheKeyManager, get_cache_key_manager, KeyType, AccessPattern,
    generate_auth_key, generate_session_key
)
from caching.intelligent_cache_warming_service import (
    IntelligentCacheWarmingService, WarmingPriority, WarmingStrategy,
    get_intelligent_warming_service
)
from monitoring.cache_performance_monitor import (
    CachePerformanceMonitor, get_cache_performance_monitor
)
from database import get_database

logger = logging.getLogger(__name__)


class CacheOptimizationType(Enum):
    """Types of cache optimizations available."""
    HIERARCHICAL_KEYS = "hierarchical_keys"
    PREDICTIVE_WARMING = "predictive_warming"
    ADAPTIVE_TTL = "adaptive_ttl"
    MEMORY_OPTIMIZATION = "memory_optimization"
    AUTHORIZATION_FAST_PATH = "authorization_fast_path"


@dataclass
class OptimizedCacheConfig:
    """Configuration for optimized cache manager."""
    # L1 Memory Cache
    l1_memory_size_mb: int = 300  # Increased from 200MB
    l1_compression_threshold_bytes: int = 1024
    l1_serialization_method: str = "pickle"  # pickle, json, msgpack
    
    # Performance targets
    l1_target_response_time_ms: float = 5.0
    l2_target_response_time_ms: float = 20.0
    authorization_target_response_time_ms: float = 75.0
    
    # Hit rate targets  
    overall_hit_rate_target: float = 95.0
    l1_hit_rate_target: float = 97.0
    l2_hit_rate_target: float = 90.0
    
    # Warming configuration
    startup_warming_enabled: bool = True
    predictive_warming_enabled: bool = True
    behavior_learning_enabled: bool = True
    
    # Optimization features
    enabled_optimizations: Set[CacheOptimizationType] = field(default_factory=lambda: {
        CacheOptimizationType.HIERARCHICAL_KEYS,
        CacheOptimizationType.PREDICTIVE_WARMING,
        CacheOptimizationType.ADAPTIVE_TTL,
        CacheOptimizationType.MEMORY_OPTIMIZATION,
        CacheOptimizationType.AUTHORIZATION_FAST_PATH
    })


@dataclass  
class UserAccessContext:
    """User access context for cache optimization."""
    user_id: str
    session_type: str
    recent_resources: List[str] = field(default_factory=list)
    access_frequency: float = 0.0
    last_access: float = 0.0
    predicted_next_access: Optional[float] = None
    hot_resources: Set[str] = field(default_factory=set)


class OptimizedCacheManager:
    """
    Optimized cache manager designed to achieve >95% hit rates and <5ms access times.
    Integrates with existing multi-layer cache infrastructure while adding performance optimizations.
    """
    
    def __init__(self, config: Optional[OptimizedCacheConfig] = None):
        self.config = config or OptimizedCacheConfig()
        
        # Core cache components  
        self.base_cache_manager = get_cache_manager()
        self.key_manager = get_cache_key_manager()
        self.warming_service = get_intelligent_warming_service()
        self.performance_monitor = get_cache_performance_monitor(self.base_cache_manager)
        
        # Optimization-specific components
        self.user_contexts: Dict[str, UserAccessContext] = {}
        self.hot_keys_cache: OrderedDict = OrderedDict()  # Fast access for hot data
        self.authorization_cache: Dict[str, Dict[str, Any]] = {}  # Dedicated auth cache
        
        # Performance tracking
        self.optimization_metrics = {
            "hierarchical_key_hits": 0,
            "predictive_warm_hits": 0,
            "fast_path_auth_hits": 0,
            "memory_optimization_saves": 0,
            "adaptive_ttl_adjustments": 0
        }
        
        # Background optimization tasks
        self.optimization_active = False
        self.optimization_tasks: List[asyncio.Task] = []
        
        # Thread safety for hot keys
        self.hot_keys_lock = threading.RLock()
        
    async def start_optimizations(self):
        """Start all cache optimization processes."""
        if self.optimization_active:
            logger.warning("Cache optimizations already active")
            return
            
        self.optimization_active = True
        logger.info("Starting optimized cache manager")
        
        # Start base warming service if not already running
        await self.warming_service.start_warming_service()
        
        # Start optimization-specific background tasks
        loop = asyncio.get_event_loop()
        
        if CacheOptimizationType.PREDICTIVE_WARMING in self.config.enabled_optimizations:
            self.optimization_tasks.append(
                loop.create_task(self._predictive_optimization_loop())
            )
            
        if CacheOptimizationType.ADAPTIVE_TTL in self.config.enabled_optimizations:
            self.optimization_tasks.append(
                loop.create_task(self._adaptive_ttl_optimization_loop())
            )
            
        if CacheOptimizationType.MEMORY_OPTIMIZATION in self.config.enabled_optimizations:
            self.optimization_tasks.append(
                loop.create_task(self._memory_optimization_loop())
            )
        
        # Execute startup optimizations
        await self._execute_startup_optimizations()
        
        logger.info("Optimized cache manager started successfully")
    
    async def stop_optimizations(self):
        """Stop all cache optimization processes."""
        self.optimization_active = False
        
        # Cancel optimization tasks
        for task in self.optimization_tasks:
            task.cancel()
        
        if self.optimization_tasks:
            await asyncio.gather(*self.optimization_tasks, return_exceptions=True)
        
        logger.info("Optimized cache manager stopped")
    
    async def get_cached_with_optimization(self, key: str, fallback_function: Optional[Callable] = None,
                                         user_context: Optional[UserAccessContext] = None) -> Tuple[Any, CacheLevel, Dict[str, Any]]:
        """
        Get cached value with all optimizations applied.
        Returns (value, cache_level, optimization_metadata).
        """
        start_time = time.time()
        optimization_metadata = {
            "optimizations_applied": [],
            "cache_path": [],
            "performance_ms": 0.0
        }
        
        try:
            # 1. Check authorization fast path
            if (CacheOptimizationType.AUTHORIZATION_FAST_PATH in self.config.enabled_optimizations and
                self._is_authorization_key(key)):
                auth_result = await self._get_authorization_fast_path(key, user_context)
                if auth_result is not None:
                    optimization_metadata["optimizations_applied"].append("authorization_fast_path")
                    optimization_metadata["cache_path"].append("auth_fast_path")
                    self.optimization_metrics["fast_path_auth_hits"] += 1
                    return auth_result, CacheLevel.L1_MEMORY, optimization_metadata
            
            # 2. Check hot keys cache for ultra-fast access
            with self.hot_keys_lock:
                if key in self.hot_keys_cache:
                    value = self.hot_keys_cache[key]
                    # Move to end (most recently used)
                    self.hot_keys_cache.move_to_end(key)
                    optimization_metadata["optimizations_applied"].append("hot_keys_cache")
                    optimization_metadata["cache_path"].append("hot_keys")
                    return value, CacheLevel.L1_MEMORY, optimization_metadata
            
            # 3. Use hierarchical key optimization
            optimized_key = key
            if CacheOptimizationType.HIERARCHICAL_KEYS in self.config.enabled_optimizations:
                optimized_key = self._optimize_cache_key(key, user_context)
                if optimized_key != key:
                    optimization_metadata["optimizations_applied"].append("hierarchical_keys")
                    self.optimization_metrics["hierarchical_key_hits"] += 1
            
            # 4. Get from multi-level cache with enhanced fallback
            async def enhanced_fallback():
                if fallback_function:
                    result = await fallback_function()
                    # Add to hot keys if this is a frequent access pattern
                    if self._should_add_to_hot_keys(optimized_key, user_context):
                        await self._add_to_hot_keys(optimized_key, result)
                        optimization_metadata["optimizations_applied"].append("hot_keys_promotion")
                    return result
                return None
            
            value, cache_level = await self.base_cache_manager.get_multi_level(
                optimized_key, enhanced_fallback
            )
            
            optimization_metadata["cache_path"].append(cache_level.value if cache_level else "miss")
            
            # 5. Update user access context for future optimizations
            if user_context and value is not None:
                self._update_user_context(user_context, key, cache_level)
            
            # 6. Trigger predictive warming if cache miss
            if (value is None and 
                CacheOptimizationType.PREDICTIVE_WARMING in self.config.enabled_optimizations and
                user_context):
                await self._trigger_predictive_warming(user_context, key)
                optimization_metadata["optimizations_applied"].append("predictive_warming_triggered")
            
            return value, cache_level or CacheLevel.L3_DATABASE, optimization_metadata
        
        finally:
            optimization_metadata["performance_ms"] = (time.time() - start_time) * 1000
    
    async def set_cached_with_optimization(self, key: str, value: Any, 
                                         user_context: Optional[UserAccessContext] = None,
                                         priority: int = 1) -> Dict[str, Any]:
        """Set cached value with optimizations applied."""
        optimization_metadata = {
            "optimizations_applied": [],
            "cache_levels_set": [],
            "ttl_optimized": False
        }
        
        # 1. Optimize cache key
        optimized_key = key
        if CacheOptimizationType.HIERARCHICAL_KEYS in self.config.enabled_optimizations:
            optimized_key = self._optimize_cache_key(key, user_context)
            if optimized_key != key:
                optimization_metadata["optimizations_applied"].append("hierarchical_keys")
        
        # 2. Calculate optimized TTL
        l1_ttl = 300  # Default
        l2_ttl = 900  # Default
        
        if CacheOptimizationType.ADAPTIVE_TTL in self.config.enabled_optimizations:
            l1_ttl, l2_ttl = self._calculate_adaptive_ttl(optimized_key, user_context)
            optimization_metadata["ttl_optimized"] = True
            optimization_metadata["optimizations_applied"].append("adaptive_ttl")
            self.optimization_metrics["adaptive_ttl_adjustments"] += 1
        
        # 3. Set in multi-level cache
        cache_results = await self.base_cache_manager.set_multi_level(
            optimized_key, value,
            l1_ttl=l1_ttl, l2_ttl=l2_ttl,
            priority=priority,
            tags=self._generate_cache_tags(key, user_context)
        )
        
        optimization_metadata["cache_levels_set"] = [
            level for level, success in cache_results.items() if success
        ]
        
        # 4. Add to hot keys cache if high priority
        if (priority >= 3 and 
            CacheOptimizationType.MEMORY_OPTIMIZATION in self.config.enabled_optimizations):
            await self._add_to_hot_keys(optimized_key, value)
            optimization_metadata["optimizations_applied"].append("hot_keys_addition")
        
        # 5. Update authorization fast path cache
        if (CacheOptimizationType.AUTHORIZATION_FAST_PATH in self.config.enabled_optimizations and
            self._is_authorization_key(key)):
            await self._update_authorization_fast_path(key, value)
            optimization_metadata["optimizations_applied"].append("authorization_fast_path_update")
        
        return optimization_metadata
    
    async def invalidate_with_optimization(self, pattern: str, 
                                         user_context: Optional[UserAccessContext] = None) -> Dict[str, Any]:
        """Invalidate cache entries with optimization-aware invalidation."""
        invalidation_results = {
            "multi_level_results": {},
            "hot_keys_invalidated": 0,
            "auth_cache_invalidated": 0
        }
        
        # 1. Invalidate from multi-level cache
        invalidation_results["multi_level_results"] = await self.base_cache_manager.invalidate_pattern(pattern)
        
        # 2. Invalidate from hot keys cache
        with self.hot_keys_lock:
            keys_to_remove = [key for key in self.hot_keys_cache.keys() 
                            if self._matches_pattern(key, pattern)]
            for key in keys_to_remove:
                del self.hot_keys_cache[key]
                invalidation_results["hot_keys_invalidated"] += 1
        
        # 3. Invalidate authorization fast path cache
        if self._is_authorization_pattern(pattern):
            auth_keys_to_remove = [key for key in self.authorization_cache.keys()
                                 if self._matches_pattern(key, pattern)]
            for key in auth_keys_to_remove:
                del self.authorization_cache[key]
                invalidation_results["auth_cache_invalidated"] += 1
        
        return invalidation_results
    
    # Optimization Implementation Methods
    
    def _optimize_cache_key(self, key: str, user_context: Optional[UserAccessContext]) -> str:
        """Optimize cache key using hierarchical patterns."""
        # Example: auth:user:123:gen:456:read -> auth:user:123:role:owner:gen:456:read
        if key.startswith("auth:") and user_context:
            parts = key.split(":")
            if len(parts) >= 5:
                # Insert role information for better cache segmentation
                user_role = self._get_user_primary_role(user_context.user_id)
                optimized_key = f"{parts[0]}:user:{user_context.user_id}:role:{user_role}:" + ":".join(parts[3:])
                return optimized_key
        
        return key
    
    def _calculate_adaptive_ttl(self, key: str, user_context: Optional[UserAccessContext]) -> Tuple[int, int]:
        """Calculate adaptive TTL based on access patterns."""
        base_l1_ttl = 300
        base_l2_ttl = 900
        
        # Adjust based on key type
        if key.startswith("auth:"):
            # Authorization data - stable for longer
            base_l1_ttl = 600
            base_l2_ttl = 1800
        elif key.startswith("session:"):
            # Session data - medium volatility
            base_l1_ttl = 300
            base_l2_ttl = 900
        elif key.startswith("gen:"):
            # Generation data - more dynamic
            base_l1_ttl = 180
            base_l2_ttl = 600
        
        # Adjust based on user access patterns
        if user_context:
            access_multiplier = min(2.0, max(0.5, user_context.access_frequency / 10.0))
            base_l1_ttl = int(base_l1_ttl * access_multiplier)
            base_l2_ttl = int(base_l2_ttl * access_multiplier)
        
        return base_l1_ttl, base_l2_ttl
    
    def _should_add_to_hot_keys(self, key: str, user_context: Optional[UserAccessContext]) -> bool:
        """Determine if key should be added to hot keys cache."""
        if not user_context:
            return False
        
        # Add to hot keys if high access frequency or critical authorization
        return (user_context.access_frequency > 50.0 or  # High frequency user
                key.startswith("auth:") or                # Authorization data
                key in user_context.hot_resources)        # User-specific hot resources
    
    async def _add_to_hot_keys(self, key: str, value: Any):
        """Add entry to hot keys cache with size management."""
        with self.hot_keys_lock:
            # Limit hot keys cache size
            max_hot_keys = 1000
            if len(self.hot_keys_cache) >= max_hot_keys:
                # Remove least recently used
                self.hot_keys_cache.popitem(last=False)
            
            self.hot_keys_cache[key] = value
    
    def _is_authorization_key(self, key: str) -> bool:
        """Check if key is authorization-related."""
        return key.startswith("auth:") or "authorization" in key.lower()
    
    def _is_authorization_pattern(self, pattern: str) -> bool:
        """Check if pattern matches authorization keys."""
        return pattern.startswith("auth:") or "authorization" in pattern.lower()
    
    async def _get_authorization_fast_path(self, key: str, user_context: Optional[UserAccessContext]) -> Optional[Any]:
        """Get authorization data from fast path cache."""
        if key in self.authorization_cache:
            auth_data = self.authorization_cache[key]
            # Check if not expired
            if auth_data.get("expires_at", 0) > time.time():
                return auth_data["value"]
            else:
                del self.authorization_cache[key]
        return None
    
    async def _update_authorization_fast_path(self, key: str, value: Any):
        """Update authorization fast path cache."""
        # Keep fast path cache size manageable
        max_auth_cache = 500
        if len(self.authorization_cache) >= max_auth_cache:
            # Remove oldest entries
            oldest_key = min(self.authorization_cache.keys(), 
                           key=lambda k: self.authorization_cache[k].get("cached_at", 0))
            del self.authorization_cache[oldest_key]
        
        self.authorization_cache[key] = {
            "value": value,
            "cached_at": time.time(),
            "expires_at": time.time() + 600  # 10 minute fast path cache
        }
    
    def _update_user_context(self, user_context: UserAccessContext, key: str, cache_level: CacheLevel):
        """Update user access context for optimization learning."""
        user_context.last_access = time.time()
        
        # Track recent resources
        resource = key.split(":")[1] if ":" in key else key
        if resource not in user_context.recent_resources:
            user_context.recent_resources.append(resource)
            if len(user_context.recent_resources) > 20:
                user_context.recent_resources.pop(0)
        
        # Update hot resources based on cache level (L1 hits indicate hot data)
        if cache_level == CacheLevel.L1_MEMORY:
            user_context.hot_resources.add(key)
        
        # Limit hot resources size
        if len(user_context.hot_resources) > 50:
            user_context.hot_resources.pop()
    
    def _get_user_primary_role(self, user_id: str) -> str:
        """Get user's primary role for cache key optimization."""
        # This would integrate with actual user management system
        # For now, return a default role
        return "member"
    
    def _generate_cache_tags(self, key: str, user_context: Optional[UserAccessContext]) -> Set[str]:
        """Generate cache tags for efficient invalidation."""
        tags = set()
        
        if user_context:
            tags.add(f"user:{user_context.user_id}")
        
        if key.startswith("auth:"):
            tags.add("authorization")
        elif key.startswith("gen:"):
            tags.add("generation")
        elif key.startswith("team:"):
            tags.add("team")
        
        return tags
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches invalidation pattern."""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    async def _execute_startup_optimizations(self):
        """Execute startup cache optimizations."""
        if not self.config.startup_warming_enabled:
            return
            
        logger.info("Executing startup cache optimizations")
        
        try:
            # Warm critical authorization patterns
            await self._warm_critical_authorization_data()
            
            # Warm active user sessions
            await self._warm_active_user_sessions()
            
            # Warm recent generation metadata
            await self._warm_recent_generation_metadata()
            
            logger.info("Startup cache optimizations completed")
            
        except Exception as e:
            logger.error(f"Startup cache optimization failed: {e}")
    
    async def _warm_critical_authorization_data(self):
        """Warm critical authorization data at startup."""
        try:
            db = await get_database()
            
            # Get top 100 most active users
            active_users = await db.execute_query(
                table="users",
                operation="select",
                filters={
                    "is_active": True,
                    "last_active_at__gte": datetime.utcnow() - timedelta(hours=24)
                },
                limit=100,
                order_by="last_active_at DESC"
            )
            
            for user in active_users:
                user_id = user["id"]
                user_context = UserAccessContext(
                    user_id=user_id,
                    session_type="startup_warm",
                    access_frequency=100.0  # High frequency for startup warming
                )
                
                # Warm user authorization context
                auth_key = f"auth:user:{user_id}:context"
                auth_data = {
                    "user_id": user_id,
                    "is_active": user["is_active"],
                    "roles": ["member"],  # Would be fetched from actual role system
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                await self.set_cached_with_optimization(
                    auth_key, auth_data, user_context, priority=3
                )
            
            logger.info(f"Warmed authorization data for {len(active_users)} users")
            
        except Exception as e:
            logger.error(f"Failed to warm authorization data: {e}")
    
    async def _warm_active_user_sessions(self):
        """Warm active user session data."""
        try:
            db = await get_database()
            
            recent_users = await db.execute_query(
                table="users", 
                operation="select",
                filters={
                    "is_active": True,
                    "last_active_at__gte": datetime.utcnow() - timedelta(hours=4)
                },
                limit=200,
                order_by="last_active_at DESC"
            )
            
            for user in recent_users:
                user_id = user["id"]
                session_key = f"session:user:{user_id}:active"
                session_data = {
                    "user_id": user_id,
                    "email": user["email"],
                    "session_start": time.time(),
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                user_context = UserAccessContext(
                    user_id=user_id,
                    session_type="active",
                    access_frequency=75.0
                )
                
                await self.set_cached_with_optimization(
                    session_key, session_data, user_context, priority=2
                )
            
            logger.info(f"Warmed session data for {len(recent_users)} users")
            
        except Exception as e:
            logger.error(f"Failed to warm session data: {e}")
    
    async def _warm_recent_generation_metadata(self):
        """Warm recent generation metadata."""
        try:
            db = await get_database()
            
            recent_generations = await db.execute_query(
                table="generations",
                operation="select", 
                filters={
                    "status": "completed",
                    "created_at__gte": datetime.utcnow() - timedelta(hours=48)
                },
                limit=500,
                order_by="created_at DESC"
            )
            
            for gen in recent_generations:
                gen_id = gen["id"]
                user_id = gen["user_id"]
                
                gen_key = f"gen:{gen_id}:metadata"
                gen_data = {
                    "generation_id": gen_id,
                    "user_id": user_id,
                    "status": gen["status"],
                    "created_at": gen["created_at"],
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                user_context = UserAccessContext(
                    user_id=user_id,
                    session_type="generation_access",
                    access_frequency=50.0
                )
                
                await self.set_cached_with_optimization(
                    gen_key, gen_data, user_context, priority=2
                )
            
            logger.info(f"Warmed generation metadata for {len(recent_generations)} generations")
            
        except Exception as e:
            logger.error(f"Failed to warm generation metadata: {e}")
    
    # Background optimization loops
    
    async def _predictive_optimization_loop(self):
        """Background loop for predictive cache optimization."""
        while self.optimization_active:
            try:
                # Analyze user access patterns and predict future needs
                for user_id, context in self.user_contexts.items():
                    if context.predicted_next_access and context.predicted_next_access <= time.time() + 300:
                        # Predicted access within 5 minutes - warm cache
                        await self._warm_predicted_user_resources(context)
                
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Predictive optimization loop error: {e}")
                await asyncio.sleep(60)
    
    async def _adaptive_ttl_optimization_loop(self):
        """Background loop for adaptive TTL optimization."""
        while self.optimization_active:
            try:
                # Analyze cache performance and adjust TTL strategies
                cache_metrics = self.base_cache_manager.get_comprehensive_metrics()
                
                # If hit rate is low, increase TTL values
                if cache_metrics["overall_performance"]["overall_hit_rate_percent"] < 90.0:
                    logger.info("Low hit rate detected - optimizing TTL strategies")
                    # TTL optimization logic would go here
                
                await asyncio.sleep(600)  # 10 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Adaptive TTL optimization loop error: {e}")
                await asyncio.sleep(120)
    
    async def _memory_optimization_loop(self):
        """Background loop for memory optimization."""
        while self.optimization_active:
            try:
                # Optimize memory usage in hot keys cache
                with self.hot_keys_lock:
                    if len(self.hot_keys_cache) > 800:  # Keep cache size optimal
                        # Remove least recently used items
                        for _ in range(100):
                            if self.hot_keys_cache:
                                self.hot_keys_cache.popitem(last=False)
                        self.optimization_metrics["memory_optimization_saves"] += 100
                
                # Clean up expired authorization cache entries
                current_time = time.time()
                expired_keys = [
                    key for key, data in self.authorization_cache.items()
                    if data.get("expires_at", 0) <= current_time
                ]
                for key in expired_keys:
                    del self.authorization_cache[key]
                
                await asyncio.sleep(180)  # 3 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Memory optimization loop error: {e}")
                await asyncio.sleep(60)
    
    async def _trigger_predictive_warming(self, user_context: UserAccessContext, missed_key: str):
        """Trigger predictive warming based on cache miss patterns."""
        # Analyze what other resources this user might need
        similar_resources = self._predict_similar_resources(user_context, missed_key)
        
        for resource_key in similar_resources:
            # Add warming task for predicted resource
            await self.warming_service.add_warming_task(
                priority=WarmingPriority.LOW,
                strategy=WarmingStrategy.PREDICTIVE,
                key_type=KeyType.GENERATION_METADATA,  # Would be determined dynamically
                cache_key=resource_key,
                data_fetcher=lambda: self._fetch_resource_data(resource_key),
                tags={"predictive", f"user:{user_context.user_id}"}
            )
        
        self.optimization_metrics["predictive_warm_hits"] += len(similar_resources)
    
    async def _warm_predicted_user_resources(self, user_context: UserAccessContext):
        """Warm resources predicted for user access."""
        for resource in user_context.hot_resources:
            # Check if already cached
            cached_value, _ = await self.base_cache_manager.get_multi_level(resource)
            if cached_value is None:
                # Not cached - add warming task
                await self.warming_service.add_warming_task(
                    priority=WarmingPriority.MEDIUM,
                    strategy=WarmingStrategy.PREDICTIVE, 
                    key_type=KeyType.USER_PROFILE,
                    cache_key=resource,
                    data_fetcher=lambda: self._fetch_resource_data(resource)
                )
    
    def _predict_similar_resources(self, user_context: UserAccessContext, missed_key: str) -> List[str]:
        """Predict similar resources user might access based on patterns."""
        similar_resources = []
        
        # Example: if user missed generation metadata, they might access image data
        if "gen:" in missed_key and "metadata" in missed_key:
            gen_id = missed_key.split(":")[1]
            similar_resources.extend([
                f"gen:{gen_id}:image_url",
                f"gen:{gen_id}:settings",
                f"auth:user:{user_context.user_id}:gen:{gen_id}:read"
            ])
        
        return similar_resources[:5]  # Limit predictions
    
    async def _fetch_resource_data(self, resource_key: str) -> Optional[Any]:
        """Fetch resource data for cache warming."""
        # This would integrate with actual data fetching services
        # For now, return placeholder data
        return {
            "resource_key": resource_key,
            "fetched_at": datetime.utcnow().isoformat(),
            "data": f"warmed_data_for_{resource_key}"
        }
    
    def get_optimization_metrics(self) -> Dict[str, Any]:
        """Get comprehensive optimization metrics."""
        base_metrics = self.base_cache_manager.get_comprehensive_metrics()
        
        return {
            "optimization_metrics": self.optimization_metrics,
            "hot_keys_count": len(self.hot_keys_cache),
            "auth_cache_count": len(self.authorization_cache),
            "user_contexts_tracked": len(self.user_contexts),
            "enabled_optimizations": [opt.value for opt in self.config.enabled_optimizations],
            "performance_targets": {
                "l1_target_ms": self.config.l1_target_response_time_ms,
                "l2_target_ms": self.config.l2_target_response_time_ms,
                "overall_hit_rate_target": self.config.overall_hit_rate_target,
                "l1_hit_rate_target": self.config.l1_hit_rate_target
            },
            "base_cache_metrics": base_metrics
        }


# Global optimized cache manager instance
optimized_cache_manager: Optional[OptimizedCacheManager] = None


def get_optimized_cache_manager(config: Optional[OptimizedCacheConfig] = None) -> OptimizedCacheManager:
    """Get or create global optimized cache manager."""
    global optimized_cache_manager
    if optimized_cache_manager is None:
        optimized_cache_manager = OptimizedCacheManager(config)
    return optimized_cache_manager


# Context manager for optimized cache operations
@asynccontextmanager
async def optimized_cache_context(user_id: str, session_type: str = "default"):
    """Context manager for optimized cache operations with user context."""
    cache_manager = get_optimized_cache_manager()
    
    # Create or get user context
    if user_id not in cache_manager.user_contexts:
        cache_manager.user_contexts[user_id] = UserAccessContext(
            user_id=user_id,
            session_type=session_type,
            access_frequency=1.0,
            last_access=time.time()
        )
    
    user_context = cache_manager.user_contexts[user_id]
    user_context.access_frequency += 1.0
    user_context.last_access = time.time()
    
    try:
        yield cache_manager, user_context
    finally:
        # Update context after operations
        pass


# Convenience functions for optimized cache operations
async def get_cached_optimized(key: str, fallback_function: Optional[Callable] = None,
                              user_id: Optional[str] = None) -> Tuple[Any, CacheLevel]:
    """Get cached value with all optimizations applied."""
    cache_manager = get_optimized_cache_manager()
    
    user_context = None
    if user_id:
        if user_id not in cache_manager.user_contexts:
            cache_manager.user_contexts[user_id] = UserAccessContext(
                user_id=user_id,
                session_type="api_call"
            )
        user_context = cache_manager.user_contexts[user_id]
    
    value, cache_level, _ = await cache_manager.get_cached_with_optimization(
        key, fallback_function, user_context
    )
    
    return value, cache_level


async def set_cached_optimized(key: str, value: Any, user_id: Optional[str] = None,
                              priority: int = 1) -> Dict[str, Any]:
    """Set cached value with optimizations applied."""
    cache_manager = get_optimized_cache_manager()
    
    user_context = None
    if user_id:
        if user_id not in cache_manager.user_contexts:
            cache_manager.user_contexts[user_id] = UserAccessContext(
                user_id=user_id,
                session_type="api_call"
            )
        user_context = cache_manager.user_contexts[user_id]
    
    return await cache_manager.set_cached_with_optimization(
        key, value, user_context, priority
    )


async def start_optimized_caching():
    """Start optimized cache manager."""
    cache_manager = get_optimized_cache_manager()
    await cache_manager.start_optimizations()


async def stop_optimized_caching():
    """Stop optimized cache manager."""
    if optimized_cache_manager:
        await optimized_cache_manager.stop_optimizations()


def get_cache_optimization_report() -> Dict[str, Any]:
    """Get comprehensive cache optimization report."""
    if not optimized_cache_manager:
        return {"error": "Optimized cache manager not initialized"}
    
    return optimized_cache_manager.get_optimization_metrics()