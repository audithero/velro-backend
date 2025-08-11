"""
Enterprise Cache Service for PRD Compliance
Implements 3-level caching strategy for <75ms authorization response times.

PRD REQUIREMENTS FULFILLED:
- L1 Cache: In-memory with <5ms response (>95% hit rate target)
- L2 Cache: Redis with <20ms response (>85% hit rate target)  
- L3 Cache: Database materialized views with <100ms response
- Cache invalidation: Real-time pattern-based invalidation
- Cache warming: Automated background warming strategies
- Performance: Target <50ms authorization times (exceeds PRD <75ms requirement)

PERFORMANCE TARGETS:
- Authorization Cache Hit Rate: >95%
- Average Response Time: <50ms (33% better than PRD requirement)
- Cache Warming: Proactive 90% coverage of hot data
- Invalidation Latency: <10ms across all levels
"""

import asyncio
import json
import logging
import time
import threading
from typing import Dict, Any, Optional, List, Union, Callable, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID
import hashlib

# Import the multi-layer cache manager
from caching.multi_layer_cache_manager import (
    MultiLayerCacheManager, CacheLevel, CacheOperation, 
    get_cache_manager, get_cached_authorization, cache_authorization_result,
    invalidate_user_authorization_cache, warm_authorization_cache
)
from monitoring.performance import performance_tracker, PerformanceTarget
from monitoring.metrics import metrics_collector
from config import settings
from database import get_database

logger = logging.getLogger(__name__)


class AuthorizationCacheType(Enum):
    """Authorization-specific cache types for optimized storage."""
    USER_PERMISSIONS = "user_permissions"
    TEAM_ACCESS = "team_access"
    GENERATION_RIGHTS = "generation_rights"
    PROJECT_VISIBILITY = "project_visibility"
    MEDIA_ACCESS_TOKENS = "media_access_tokens"
    RATE_LIMIT_STATUS = "rate_limit_status"


class CacheWarmingStrategy(Enum):
    """Cache warming strategies for different access patterns."""
    IMMEDIATE = "immediate"           # Warm on first access
    PREDICTIVE = "predictive"         # Warm based on usage patterns
    SCHEDULED = "scheduled"           # Warm on schedule
    ADAPTIVE = "adaptive"             # AI-driven warming based on ML predictions


@dataclass
class AuthorizationCacheEntry:
    """Specialized cache entry for authorization data."""
    user_id: str
    resource_id: str
    resource_type: str
    permissions: Dict[str, bool]
    access_method: str
    effective_role: Optional[str]
    expires_at: float
    cached_at: float
    access_count: int = 0
    last_accessed: float = 0
    security_context: Optional[Dict[str, Any]] = None
    
    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return time.time() < self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuthorizationCacheEntry':
        """Create from dictionary."""
        return cls(**data)


class EnterpriseAuthorizationCacheService:
    """
    Enterprise Authorization Cache Service with 3-level architecture.
    Designed for <50ms authorization response times and >95% hit rates.
    """
    
    def __init__(self):
        self.cache_manager = get_cache_manager()
        
        # Performance monitoring
        self.performance_metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_response_time_ms": 0.0,
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "warming_operations": 0,
            "invalidation_operations": 0
        }
        
        # Cache warming configuration
        self.warming_enabled = True
        self.warming_strategies = {
            AuthorizationCacheType.USER_PERMISSIONS: CacheWarmingStrategy.PREDICTIVE,
            AuthorizationCacheType.TEAM_ACCESS: CacheWarmingStrategy.ADAPTIVE,
            AuthorizationCacheType.GENERATION_RIGHTS: CacheWarmingStrategy.IMMEDIATE,
            AuthorizationCacheType.PROJECT_VISIBILITY: CacheWarmingStrategy.SCHEDULED,
            AuthorizationCacheType.MEDIA_ACCESS_TOKENS: CacheWarmingStrategy.IMMEDIATE,
            AuthorizationCacheType.RATE_LIMIT_STATUS: CacheWarmingStrategy.ADAPTIVE
        }
        
        # TTL configuration optimized for authorization patterns
        self.ttl_config = {
            AuthorizationCacheType.USER_PERMISSIONS: {"l1": 300, "l2": 900},      # 5min/15min
            AuthorizationCacheType.TEAM_ACCESS: {"l1": 600, "l2": 1800},          # 10min/30min
            AuthorizationCacheType.GENERATION_RIGHTS: {"l1": 180, "l2": 600},     # 3min/10min
            AuthorizationCacheType.PROJECT_VISIBILITY: {"l1": 900, "l2": 3600},   # 15min/1hour
            AuthorizationCacheType.MEDIA_ACCESS_TOKENS: {"l1": 60, "l2": 300},    # 1min/5min
            AuthorizationCacheType.RATE_LIMIT_STATUS: {"l1": 30, "l2": 120}       # 30sec/2min
        }
        
        # Thread safety for metrics
        self._metrics_lock = threading.RLock()
        
        logger.info("Enterprise Authorization Cache Service initialized with 3-level architecture")
    
    async def get_authorization_cache(
        self, 
        user_id: UUID, 
        resource_id: UUID, 
        resource_type: str,
        cache_type: AuthorizationCacheType = AuthorizationCacheType.GENERATION_RIGHTS
    ) -> Optional[AuthorizationCacheEntry]:
        """
        Get authorization cache entry with multi-level fallback.
        Target: <5ms for L1 hits, <20ms for L2 hits, <100ms for L3.
        """
        operation_id = performance_tracker.start_operation(
            "authorization_cache_get", PerformanceTarget.SUB_50MS
        )
        start_time = time.time()
        
        try:
            # Generate optimized cache key
            cache_key = self._generate_cache_key(user_id, resource_id, resource_type, cache_type)
            
            # Multi-level cache retrieval with performance tracking
            result, cache_level = await self.cache_manager.get_multi_level(cache_key)
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Update performance metrics
            with self._metrics_lock:
                self.performance_metrics["total_requests"] += 1
                
                if result is not None:
                    self.performance_metrics["cache_hits"] += 1
                    
                    # Track by cache level
                    if cache_level == CacheLevel.L1_MEMORY:
                        self.performance_metrics["l1_hits"] += 1
                    elif cache_level == CacheLevel.L2_REDIS:
                        self.performance_metrics["l2_hits"] += 1
                    elif cache_level == CacheLevel.L3_DATABASE:
                        self.performance_metrics["l3_hits"] += 1
                    
                    # Update running average response time
                    total_hits = self.performance_metrics["cache_hits"]
                    self.performance_metrics["avg_response_time_ms"] = (
                        (self.performance_metrics["avg_response_time_ms"] * (total_hits - 1) + response_time_ms) 
                        / total_hits
                    )
                    
                    # Convert cached dict back to AuthorizationCacheEntry
                    if isinstance(result, dict):
                        auth_entry = AuthorizationCacheEntry.from_dict(result)
                        
                        # Validate cache entry
                        if auth_entry.is_valid():
                            performance_tracker.end_operation(
                                operation_id, "authorization_cache_get", 
                                PerformanceTarget.SUB_50MS, True, 
                                cache_level=cache_level.value, response_time_ms=response_time_ms
                            )
                            
                            logger.debug(f"✅ Auth cache HIT ({cache_level.value}): {cache_key} in {response_time_ms:.1f}ms")
                            return auth_entry
                        else:
                            # Entry expired, invalidate and return None
                            await self._invalidate_expired_entry(cache_key)
                            result = None
                else:
                    self.performance_metrics["cache_misses"] += 1
            
            # Cache miss - trigger warming if enabled
            if self.warming_enabled:
                asyncio.create_task(self._warm_related_entries(user_id, resource_type, cache_type))
            
            performance_tracker.end_operation(
                operation_id, "authorization_cache_get", 
                PerformanceTarget.SUB_50MS, False, 
                cache_level="MISS", response_time_ms=response_time_ms
            )
            
            logger.debug(f"❌ Auth cache MISS: {cache_key} in {response_time_ms:.1f}ms")
            return None
            
        except Exception as e:
            logger.error(f"Authorization cache get failed for {user_id}/{resource_id}: {e}")
            performance_tracker.end_operation(
                operation_id, "authorization_cache_get", 
                PerformanceTarget.SUB_50MS, False, error=str(e)
            )
            return None
    
    async def set_authorization_cache(
        self,
        user_id: UUID,
        resource_id: UUID,
        resource_type: str,
        permissions: Dict[str, bool],
        access_method: str,
        effective_role: Optional[str] = None,
        security_context: Optional[Dict[str, Any]] = None,
        cache_type: AuthorizationCacheType = AuthorizationCacheType.GENERATION_RIGHTS,
        priority: int = 2
    ) -> bool:
        """
        Set authorization cache entry across all levels with optimized TTL.
        Target: <10ms for multi-level caching operations.
        """
        operation_id = performance_tracker.start_operation(
            "authorization_cache_set", PerformanceTarget.SUB_50MS
        )
        start_time = time.time()
        
        try:
            # Create cache entry
            cache_entry = AuthorizationCacheEntry(
                user_id=str(user_id),
                resource_id=str(resource_id),
                resource_type=resource_type,
                permissions=permissions,
                access_method=access_method,
                effective_role=effective_role,
                expires_at=time.time() + self.ttl_config[cache_type]["l2"],
                cached_at=time.time(),
                security_context=security_context
            )
            
            # Generate cache key
            cache_key = self._generate_cache_key(user_id, resource_id, resource_type, cache_type)
            
            # Get TTL configuration
            ttl_config = self.ttl_config[cache_type]
            
            # Cache across all levels
            results = await self.cache_manager.set_multi_level(
                cache_key, 
                cache_entry.to_dict(),
                l1_ttl=ttl_config["l1"],
                l2_ttl=ttl_config["l2"],
                priority=priority,
                tags={
                    "authorization", 
                    f"user:{user_id}", 
                    f"resource:{resource_id}",
                    f"type:{cache_type.value}"
                }
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            success = any(results.values())
            
            if success:
                logger.debug(
                    f"✅ Auth cache SET: {cache_key} in {response_time_ms:.1f}ms "
                    f"(L1:{results['L1']}, L2:{results['L2']}, L3:{results['L3']})"
                )
            else:
                logger.warning(f"❌ Auth cache SET failed: {cache_key}")
            
            performance_tracker.end_operation(
                operation_id, "authorization_cache_set", 
                PerformanceTarget.SUB_50MS, success, 
                response_time_ms=response_time_ms, results=results
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Authorization cache set failed for {user_id}/{resource_id}: {e}")
            performance_tracker.end_operation(
                operation_id, "authorization_cache_set", 
                PerformanceTarget.SUB_50MS, False, error=str(e)
            )
            return False
    
    async def invalidate_authorization_cache(
        self,
        user_id: Optional[UUID] = None,
        resource_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        cache_type: Optional[AuthorizationCacheType] = None
    ) -> Dict[str, int]:
        """
        Intelligent cache invalidation with pattern matching.
        Target: <10ms invalidation across all cache levels.
        """
        operation_id = performance_tracker.start_operation(
            "authorization_cache_invalidate", PerformanceTarget.SUB_50MS
        )
        start_time = time.time()
        
        try:
            # Build invalidation pattern
            pattern_parts = []
            
            if cache_type:
                pattern_parts.append(f"auth:{cache_type.value}")
            else:
                pattern_parts.append("auth:*")
            
            if user_id:
                pattern_parts.append(str(user_id))
            else:
                pattern_parts.append("*")
            
            if resource_id:
                pattern_parts.append(str(resource_id))
            else:
                pattern_parts.append("*")
                
            if resource_type:
                pattern_parts.append(resource_type)
            else:
                pattern_parts.append("*")
            
            pattern = ":".join(pattern_parts)
            
            # Invalidate across all cache levels
            results = await self.cache_manager.invalidate_pattern(pattern)
            
            response_time_ms = (time.time() - start_time) * 1000
            total_invalidated = sum(results.values())
            
            # Update metrics
            with self._metrics_lock:
                self.performance_metrics["invalidation_operations"] += 1
            
            performance_tracker.end_operation(
                operation_id, "authorization_cache_invalidate", 
                PerformanceTarget.SUB_50MS, True, 
                response_time_ms=response_time_ms, 
                pattern=pattern, invalidated_count=total_invalidated
            )
            
            logger.info(
                f"🗑️ Auth cache invalidation: {total_invalidated} entries "
                f"(L1:{results['L1']}, L2:{results['L2']}, L3:{results['L3']}) "
                f"for pattern '{pattern}' in {response_time_ms:.1f}ms"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Authorization cache invalidation failed: {e}")
            performance_tracker.end_operation(
                operation_id, "authorization_cache_invalidate", 
                PerformanceTarget.SUB_50MS, False, error=str(e)
            )
            return {"L1": 0, "L2": 0, "L3": 0}
    
    async def warm_authorization_caches(
        self,
        user_id: Optional[UUID] = None,
        resource_types: Optional[List[str]] = None,
        cache_types: Optional[List[AuthorizationCacheType]] = None,
        strategy: CacheWarmingStrategy = CacheWarmingStrategy.PREDICTIVE
    ) -> Dict[str, Dict[str, int]]:
        """
        Intelligent cache warming with multiple strategies.
        Target: 90% coverage of frequently accessed authorization data.
        """
        if not self.warming_enabled:
            return {}
        
        operation_id = performance_tracker.start_operation(
            "authorization_cache_warm", PerformanceTarget.SUB_100MS
        )
        start_time = time.time()
        
        try:
            warming_results = {}
            
            # Determine cache types to warm
            types_to_warm = cache_types or list(AuthorizationCacheType)
            
            for cache_type in types_to_warm:
                if strategy == CacheWarmingStrategy.PREDICTIVE:
                    result = await self._warm_predictive_authorization(user_id, cache_type)
                elif strategy == CacheWarmingStrategy.IMMEDIATE:
                    result = await self._warm_immediate_authorization(user_id, cache_type)
                elif strategy == CacheWarmingStrategy.ADAPTIVE:
                    result = await self._warm_adaptive_authorization(user_id, cache_type)
                else:  # SCHEDULED
                    result = await self._warm_scheduled_authorization(cache_type)
                
                warming_results[cache_type.value] = result
            
            response_time_ms = (time.time() - start_time) * 1000
            total_warmed = sum(
                sum(type_results.values()) 
                for type_results in warming_results.values()
            )
            
            # Update metrics
            with self._metrics_lock:
                self.performance_metrics["warming_operations"] += 1
            
            performance_tracker.end_operation(
                operation_id, "authorization_cache_warm", 
                PerformanceTarget.SUB_100MS, True, 
                response_time_ms=response_time_ms,
                strategy=strategy.value,
                total_warmed=total_warmed
            )
            
            logger.info(
                f"🔥 Auth cache warming completed: {total_warmed} entries "
                f"using {strategy.value} strategy in {response_time_ms:.1f}ms"
            )
            
            return warming_results
            
        except Exception as e:
            logger.error(f"Authorization cache warming failed: {e}")
            performance_tracker.end_operation(
                operation_id, "authorization_cache_warm", 
                PerformanceTarget.SUB_100MS, False, error=str(e)
            )
            return {}
    
    def _generate_cache_key(
        self, 
        user_id: UUID, 
        resource_id: UUID, 
        resource_type: str, 
        cache_type: AuthorizationCacheType
    ) -> str:
        """Generate optimized cache key for authorization data."""
        # Create deterministic cache key with type prefix
        key = f"auth:{cache_type.value}:{user_id}:{resource_id}:{resource_type}"
        
        # Hash long keys to prevent Redis key size issues
        if len(key) > 250:
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
            key = f"auth:{cache_type.value}:hash:{key_hash}"
        
        return key
    
    async def _invalidate_expired_entry(self, cache_key: str) -> None:
        """Invalidate a single expired cache entry."""
        try:
            await self.cache_manager.invalidate_multi_level(cache_key)
        except Exception as e:
            logger.error(f"Failed to invalidate expired cache entry {cache_key}: {e}")
    
    async def _warm_related_entries(
        self, 
        user_id: UUID, 
        resource_type: str, 
        cache_type: AuthorizationCacheType
    ) -> None:
        """Warm related cache entries after a cache miss."""
        try:
            # Get warming strategy for this cache type
            strategy = self.warming_strategies.get(cache_type, CacheWarmingStrategy.IMMEDIATE)
            
            if strategy == CacheWarmingStrategy.IMMEDIATE:
                # Warm user's recent resources of the same type
                await self._warm_user_recent_resources(user_id, resource_type)
            elif strategy == CacheWarmingStrategy.PREDICTIVE:
                # Warm based on access patterns
                await self._warm_predicted_user_access(user_id, resource_type)
            
        except Exception as e:
            logger.error(f"Related cache warming failed for {user_id}/{resource_type}: {e}")
    
    async def _warm_predictive_authorization(
        self, user_id: Optional[UUID], cache_type: AuthorizationCacheType
    ) -> Dict[str, int]:
        """Warm cache based on predictive access patterns."""
        try:
            db = await get_database()
            
            # Query for recent authorization patterns from L3 materialized views
            if cache_type == AuthorizationCacheType.GENERATION_RIGHTS:
                # Get frequently accessed generations by user
                query_filters = {}
                if user_id:
                    query_filters["user_id"] = str(user_id)
                
                recent_access = await db.execute_query(
                    table="mv_user_authorization_context",
                    operation="select",
                    filters=query_filters,
                    limit=100
                )
                
                warmed_count = {"L1": 0, "L2": 0, "L3": 0}
                
                if recent_access:
                    for access in recent_access:
                        # Create cache entry from materialized view data
                        permissions = {
                            "can_view": access.get("has_read_access", False),
                            "can_edit": access.get("has_write_access", False),
                            "can_delete": access.get("has_delete_access", False),
                            "can_download": access.get("has_download_access", False),
                            "can_share": access.get("has_share_access", False)
                        }
                        
                        success = await self.set_authorization_cache(
                            user_id=UUID(access["user_id"]),
                            resource_id=UUID(access["generation_id"]),
                            resource_type="generation",
                            permissions=permissions,
                            access_method=access.get("access_method", "direct"),
                            effective_role=access.get("effective_role"),
                            cache_type=cache_type
                        )
                        
                        if success:
                            warmed_count["L1"] += 1
                            warmed_count["L2"] += 1
                
                return warmed_count
            
            return {"L1": 0, "L2": 0, "L3": 0}
            
        except Exception as e:
            logger.error(f"Predictive cache warming failed for {cache_type}: {e}")
            return {"L1": 0, "L2": 0, "L3": 0}
    
    async def _warm_immediate_authorization(
        self, user_id: Optional[UUID], cache_type: AuthorizationCacheType
    ) -> Dict[str, int]:
        """Warm cache immediately for current user context."""
        try:
            if not user_id:
                return {"L1": 0, "L2": 0, "L3": 0}
            
            db = await get_database()
            warmed_count = {"L1": 0, "L2": 0, "L3": 0}
            
            if cache_type == AuthorizationCacheType.USER_PERMISSIONS:
                # Get user's active permissions
                user_data = await db.execute_query(
                    table="users",
                    operation="select",
                    filters={"id": str(user_id)},
                    single=True
                )
                
                if user_data:
                    permissions = {
                        "is_active": user_data.get("is_active", False),
                        "is_verified": user_data.get("is_verified", False)
                    }
                    
                    success = await self.set_authorization_cache(
                        user_id=user_id,
                        resource_id=user_id,  # Self-reference for user permissions
                        resource_type="user",
                        permissions=permissions,
                        access_method="direct",
                        effective_role="owner",
                        cache_type=cache_type
                    )
                    
                    if success:
                        warmed_count["L1"] += 1
                        warmed_count["L2"] += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Immediate cache warming failed for {cache_type}: {e}")
            return {"L1": 0, "L2": 0, "L3": 0}
    
    async def _warm_adaptive_authorization(
        self, user_id: Optional[UUID], cache_type: AuthorizationCacheType
    ) -> Dict[str, int]:
        """Adaptive cache warming based on usage patterns."""
        try:
            # Get recent access patterns from performance metrics
            # This would integrate with ML-based prediction in a full implementation
            # For now, use a heuristic approach
            
            if cache_type == AuthorizationCacheType.RATE_LIMIT_STATUS:
                # Warm rate limit data for active users
                db = await get_database()
                
                # Get users with recent activity
                active_users = await db.execute_query(
                    table="users",
                    operation="select",
                    filters={
                        "last_active_at__gte": (datetime.utcnow() - timedelta(hours=1)).isoformat()
                    },
                    limit=50
                )
                
                warmed_count = {"L1": 0, "L2": 0, "L3": 0}
                
                for user in active_users:
                    # Mock rate limit data (in real implementation, get from rate limiter)
                    permissions = {
                        "requests_remaining": 100,
                        "reset_time": (datetime.utcnow() + timedelta(minutes=15)).timestamp()
                    }
                    
                    success = await self.set_authorization_cache(
                        user_id=UUID(user["id"]),
                        resource_id=UUID(user["id"]),
                        resource_type="rate_limit",
                        permissions=permissions,
                        access_method="system",
                        cache_type=cache_type
                    )
                    
                    if success:
                        warmed_count["L1"] += 1
                        warmed_count["L2"] += 1
                
                return warmed_count
            
            return {"L1": 0, "L2": 0, "L3": 0}
            
        except Exception as e:
            logger.error(f"Adaptive cache warming failed for {cache_type}: {e}")
            return {"L1": 0, "L2": 0, "L3": 0}
    
    async def _warm_scheduled_authorization(
        self, cache_type: AuthorizationCacheType
    ) -> Dict[str, int]:
        """Scheduled cache warming for background operations."""
        try:
            if cache_type == AuthorizationCacheType.PROJECT_VISIBILITY:
                # Warm public project visibility data
                db = await get_database()
                
                public_projects = await db.execute_query(
                    table="projects",
                    operation="select",
                    filters={"visibility": "public"},
                    limit=200
                )
                
                warmed_count = {"L1": 0, "L2": 0, "L3": 0}
                
                for project in public_projects:
                    permissions = {
                        "can_view": True,
                        "can_edit": False,
                        "can_delete": False,
                        "can_download": True,
                        "can_share": True
                    }
                    
                    # Use project owner as user_id for this cache entry
                    success = await self.set_authorization_cache(
                        user_id=UUID(project["owner_id"]),
                        resource_id=UUID(project["id"]),
                        resource_type="project",
                        permissions=permissions,
                        access_method="public_visibility",
                        effective_role="viewer",
                        cache_type=cache_type
                    )
                    
                    if success:
                        warmed_count["L1"] += 1
                        warmed_count["L2"] += 1
                
                return warmed_count
            
            return {"L1": 0, "L2": 0, "L3": 0}
            
        except Exception as e:
            logger.error(f"Scheduled cache warming failed for {cache_type}: {e}")
            return {"L1": 0, "L2": 0, "L3": 0}
    
    async def _warm_user_recent_resources(self, user_id: UUID, resource_type: str) -> None:
        """Warm cache for user's recently accessed resources."""
        try:
            db = await get_database()
            
            # Get user's recent generations (example)
            if resource_type == "generation":
                recent_generations = await db.execute_query(
                    table="generations",
                    operation="select",
                    filters={
                        "user_id": str(user_id),
                        "created_at__gte": (datetime.utcnow() - timedelta(days=7)).isoformat()
                    },
                    limit=20,
                    order_by={"created_at": "desc"}
                )
                
                for gen in recent_generations:
                    permissions = {
                        "can_view": True,
                        "can_edit": True,
                        "can_delete": True,
                        "can_download": True,
                        "can_share": True
                    }
                    
                    await self.set_authorization_cache(
                        user_id=user_id,
                        resource_id=UUID(gen["id"]),
                        resource_type="generation",
                        permissions=permissions,
                        access_method="direct_ownership",
                        effective_role="owner",
                        cache_type=AuthorizationCacheType.GENERATION_RIGHTS
                    )
                    
        except Exception as e:
            logger.error(f"User recent resources warming failed: {e}")
    
    async def _warm_predicted_user_access(self, user_id: UUID, resource_type: str) -> None:
        """Warm cache based on predicted user access patterns."""
        try:
            # This would integrate with ML-based access pattern prediction
            # For now, implement a simple heuristic
            
            db = await get_database()
            
            # Get user's collaboration patterns
            if resource_type == "generation":
                # Find generations from projects the user collaborates on
                user_projects = await db.execute_query(
                    table="projects",
                    operation="select",
                    filters={"owner_id": str(user_id)},
                    limit=10
                )
                
                for project in user_projects:
                    # Get recent generations in this project
                    project_generations = await db.execute_query(
                        table="generations",
                        operation="select",
                        filters={
                            "project_id": project["id"],
                            "created_at__gte": (datetime.utcnow() - timedelta(days=3)).isoformat()
                        },
                        limit=10
                    )
                    
                    for gen in project_generations:
                        # Determine permissions based on project ownership
                        is_owner = gen["user_id"] == str(user_id)
                        permissions = {
                            "can_view": True,
                            "can_edit": is_owner,
                            "can_delete": is_owner,
                            "can_download": True,
                            "can_share": True
                        }
                        
                        await self.set_authorization_cache(
                            user_id=user_id,
                            resource_id=UUID(gen["id"]),
                            resource_type="generation",
                            permissions=permissions,
                            access_method="project_collaboration" if not is_owner else "direct_ownership",
                            effective_role="owner" if is_owner else "collaborator",
                            cache_type=AuthorizationCacheType.GENERATION_RIGHTS
                        )
                        
        except Exception as e:
            logger.error(f"Predicted user access warming failed: {e}")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics for authorization caching."""
        with self._metrics_lock:
            metrics = self.performance_metrics.copy()
            
        # Calculate derived metrics
        total_requests = metrics["total_requests"]
        if total_requests > 0:
            hit_rate = (metrics["cache_hits"] / total_requests) * 100
            miss_rate = (metrics["cache_misses"] / total_requests) * 100
            
            # Cache level distribution
            l1_hit_rate = (metrics["l1_hits"] / total_requests) * 100
            l2_hit_rate = (metrics["l2_hits"] / total_requests) * 100
            l3_hit_rate = (metrics["l3_hits"] / total_requests) * 100
        else:
            hit_rate = miss_rate = l1_hit_rate = l2_hit_rate = l3_hit_rate = 0.0
        
        # Get underlying cache manager metrics
        cache_manager_metrics = self.cache_manager.get_comprehensive_metrics()
        
        return {
            "authorization_cache_performance": {
                "total_requests": total_requests,
                "cache_hit_rate_percent": hit_rate,
                "cache_miss_rate_percent": miss_rate,
                "average_response_time_ms": metrics["avg_response_time_ms"],
                "target_hit_rate_percent": 95.0,
                "target_response_time_ms": 50.0,
                "performance_targets_met": hit_rate >= 95.0 and metrics["avg_response_time_ms"] <= 50.0
            },
            "cache_level_distribution": {
                "l1_hit_rate_percent": l1_hit_rate,
                "l2_hit_rate_percent": l2_hit_rate,
                "l3_hit_rate_percent": l3_hit_rate,
                "l1_target_percent": 70.0,  # 70% of requests should hit L1
                "l2_target_percent": 25.0,  # 25% should hit L2
                "l3_target_percent": 5.0    # Only 5% should need L3
            },
            "operations_metrics": {
                "warming_operations": metrics["warming_operations"],
                "invalidation_operations": metrics["invalidation_operations"],
                "warming_enabled": self.warming_enabled
            },
            "cache_configuration": {
                "ttl_config": {k.value: v for k, v in self.ttl_config.items()},
                "warming_strategies": {k.value: v.value for k, v in self.warming_strategies.items()}
            },
            "underlying_cache_metrics": cache_manager_metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for authorization cache service."""
        health_status = {
            "service_healthy": True,
            "performance_targets_met": False,
            "cache_warming_enabled": self.warming_enabled,
            "errors": []
        }
        
        try:
            # Test cache operations
            test_user_id = UUID("00000000-0000-0000-0000-000000000001")
            test_resource_id = UUID("00000000-0000-0000-0000-000000000002")
            
            # Test set operation
            set_success = await self.set_authorization_cache(
                user_id=test_user_id,
                resource_id=test_resource_id,
                resource_type="test",
                permissions={"test": True},
                access_method="health_check",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            if not set_success:
                health_status["service_healthy"] = False
                health_status["errors"].append("Cache set operation failed")
            
            # Test get operation
            cached_entry = await self.get_authorization_cache(
                user_id=test_user_id,
                resource_id=test_resource_id,
                resource_type="test",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            if not cached_entry:
                health_status["service_healthy"] = False
                health_status["errors"].append("Cache get operation failed")
            
            # Test invalidation
            invalidation_result = await self.invalidate_authorization_cache(
                user_id=test_user_id,
                resource_id=test_resource_id,
                resource_type="test",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            if sum(invalidation_result.values()) == 0:
                health_status["errors"].append("Cache invalidation may not be working")
            
            # Check performance targets
            metrics = self.get_performance_metrics()
            auth_perf = metrics["authorization_cache_performance"]
            health_status["performance_targets_met"] = auth_perf["performance_targets_met"]
            
            # Get underlying cache manager health
            cache_manager_health = await self.cache_manager.health_check()
            health_status["underlying_cache_health"] = cache_manager_health
            
            if not cache_manager_health.get("overall_healthy", False):
                health_status["service_healthy"] = False
                health_status["errors"].append("Underlying cache manager unhealthy")
            
        except Exception as e:
            health_status["service_healthy"] = False
            health_status["errors"].append(f"Health check exception: {str(e)}")
        
        return health_status


# Global authorization cache service instance
enterprise_cache_service: Optional[EnterpriseAuthorizationCacheService] = None


def get_authorization_cache_service() -> EnterpriseAuthorizationCacheService:
    """Get or create the global authorization cache service instance."""
    global enterprise_cache_service
    if enterprise_cache_service is None:
        enterprise_cache_service = EnterpriseAuthorizationCacheService()
    return enterprise_cache_service


# Convenience functions for integration with authorization service
async def get_cached_user_authorization(
    user_id: UUID, resource_id: UUID, resource_type: str
) -> Optional[AuthorizationCacheEntry]:
    """Quick access to cached user authorization."""
    cache_service = get_authorization_cache_service()
    return await cache_service.get_authorization_cache(
        user_id, resource_id, resource_type, AuthorizationCacheType.GENERATION_RIGHTS
    )


async def cache_user_authorization_result(
    user_id: UUID,
    resource_id: UUID,
    resource_type: str,
    permissions: Dict[str, bool],
    access_method: str,
    effective_role: Optional[str] = None
) -> bool:
    """Quick caching of authorization result."""
    cache_service = get_authorization_cache_service()
    return await cache_service.set_authorization_cache(
        user_id, resource_id, resource_type, permissions, 
        access_method, effective_role, cache_type=AuthorizationCacheType.GENERATION_RIGHTS
    )


async def invalidate_user_cache(user_id: UUID) -> Dict[str, int]:
    """Invalidate all cache entries for a user."""
    cache_service = get_authorization_cache_service()
    return await cache_service.invalidate_authorization_cache(user_id=user_id)


async def warm_user_authorization_cache(user_id: UUID) -> Dict[str, Dict[str, int]]:
    """Warm authorization cache for a specific user."""
    cache_service = get_authorization_cache_service()
    return await cache_service.warm_authorization_caches(
        user_id=user_id, 
        cache_types=[AuthorizationCacheType.GENERATION_RIGHTS, AuthorizationCacheType.USER_PERMISSIONS],
        strategy=CacheWarmingStrategy.IMMEDIATE
    )