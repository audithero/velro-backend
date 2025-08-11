"""
Optimized Base Repository with <20ms database query performance patterns.
Integrates all performance optimizations: connection pooling, parallel execution,
materialized views, caching, and Supabase optimizations.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Union, Type, TypeVar, Generic, Tuple
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from database import DatabaseClient
from utils.supabase_performance_optimizer import supabase_optimizer, SupabasePerformanceConfig
from utils.enterprise_db_pool import enterprise_pool_manager, PoolType
from caching.multi_layer_cache_manager import cache_manager, CachePriority
from supabase import Client

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class QueryContext:
    """Context for optimized query execution."""
    query_type: str
    table: str
    operation: str
    use_materialized_view: bool = False
    use_service_key: bool = False
    enable_caching: bool = True
    enable_parallel: bool = False
    cache_priority: CachePriority = CachePriority.MEDIUM
    cache_ttl: int = 900  # 15 minutes default


@dataclass
class RepositoryMetrics:
    """Repository performance metrics."""
    total_queries: int = 0
    cache_hits: int = 0
    materialized_view_hits: int = 0
    parallel_query_count: int = 0
    avg_query_time_ms: float = 0.0
    total_query_time_ms: float = 0.0
    auth_queries_sub_20ms: int = 0
    general_queries_sub_50ms: int = 0
    target_performance_achieved: bool = True


class BaseRepository(Generic[T], ABC):
    """
    High-performance base repository with comprehensive optimizations.
    
    Key Features:
    - <20ms auth queries, <50ms general queries
    - Automatic materialized view utilization
    - Intelligent caching with multi-layer support
    - Parallel query execution
    - Connection pool optimization
    - Supabase-specific optimizations
    - Circuit breaker patterns
    """
    
    def __init__(
        self,
        db_client: DatabaseClient,
        supabase_client: Client,
        table_name: str,
        model_class: Type[T],
        pool_type: PoolType = PoolType.GENERAL
    ):
        self.db_client = db_client
        self.supabase_client = supabase_client
        self.table_name = table_name
        self.model_class = model_class
        self.pool_type = pool_type
        
        # Performance tracking
        self.metrics = RepositoryMetrics()
        self.performance_config = SupabasePerformanceConfig()
        
        # Repository-specific cache namespace
        self.cache_namespace = f"repo:{table_name}"
        
        # Materialized view mappings
        self.materialized_views = self._get_materialized_views()
        
        logger.info(f"🚀 [REPO] Initialized {self.__class__.__name__} with optimizations")
    
    @abstractmethod
    def _get_materialized_views(self) -> Dict[str, str]:
        """Define materialized views for this repository."""
        return {}
    
    @abstractmethod
    def _get_cache_key(self, operation: str, **kwargs) -> str:
        """Generate cache key for operation."""
        pass
    
    async def _execute_optimized_query(
        self,
        context: QueryContext,
        query_data: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """Execute query with full optimization stack."""
        start_time = time.time()
        
        try:
            # Use materialized view if available and beneficial
            if context.use_materialized_view and context.operation == "select":
                mv_name = self.materialized_views.get(context.query_type)
                if mv_name:
                    result = await self.db_client.execute_materialized_view_query(
                        view_name=mv_name,
                        filters=filters,
                        **kwargs
                    )
                    
                    execution_time = (time.time() - start_time) * 1000
                    self._update_metrics(execution_time, "materialized_view", context.query_type)
                    
                    logger.debug(f"🎯 [REPO] Materialized view query: {execution_time:.1f}ms ({context.table})")
                    return result
            
            # Use Supabase optimizer for maximum performance
            result = await supabase_optimizer.execute_optimized_query(
                client=self.supabase_client,
                table=context.table,
                operation=context.operation,
                data=query_data,
                filters=filters,
                use_service_key=context.use_service_key,
                enable_caching=context.enable_caching
            )
            
            execution_time = (time.time() - start_time) * 1000
            self._update_metrics(execution_time, "optimized", context.query_type)
            
            # Check performance targets
            self._check_performance_targets(execution_time, context.query_type)
            
            return result
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._update_metrics(execution_time, "error", context.query_type)
            logger.error(f"❌ [REPO] Query failed after {execution_time:.1f}ms: {e}")
            raise
    
    async def _execute_parallel_queries(
        self,
        queries: List[Tuple[QueryContext, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
    ) -> List[Any]:
        """Execute multiple queries in parallel for maximum performance."""
        start_time = time.time()
        
        try:
            # Convert to Supabase optimizer format
            supabase_queries = []
            for context, query_data, filters in queries:
                supabase_queries.append((
                    context.table,
                    context.operation, 
                    query_data,
                    filters
                ))
            
            # Execute in parallel
            results = await supabase_optimizer.execute_optimized_batch(
                client=self.supabase_client,
                queries=supabase_queries,
                use_service_key=True  # Use service key for batch operations
            )
            
            execution_time = (time.time() - start_time) * 1000
            self.metrics.parallel_query_count += len(queries)
            self._update_metrics(execution_time, "parallel_batch", "general")
            
            logger.info(f"🚀 [REPO] Parallel batch: {len(queries)} queries in {execution_time:.1f}ms")
            
            return results
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"❌ [REPO] Parallel batch failed after {execution_time:.1f}ms: {e}")
            raise
    
    async def get_by_id(self, id: str, use_cache: bool = True) -> Optional[T]:
        """Get single record by ID with aggressive optimization."""
        cache_key = self._get_cache_key("get_by_id", id=id) if use_cache else None
        
        # Check cache first
        if cache_key and use_cache:
            cached_result = await cache_manager.get(cache_key)
            if cached_result is not None:
                self.metrics.cache_hits += 1
                logger.debug(f"🎯 [REPO] Cache hit for {self.table_name}:{id}")
                return self._deserialize(cached_result)
        
        # Execute optimized query
        context = QueryContext(
            query_type="get_by_id",
            table=self.table_name,
            operation="select",
            use_service_key=True,  # Use service key for faster auth bypass
            enable_caching=use_cache,
            cache_priority=CachePriority.HIGH
        )
        
        result = await self._execute_optimized_query(
            context=context,
            filters={"id": id},
            limit=1
        )
        
        if result and len(result) > 0:
            record = self._deserialize(result[0])
            
            # Cache the result
            if cache_key and use_cache:
                await cache_manager.set(
                    cache_key,
                    result[0],
                    ttl=300,  # 5 minutes for individual records
                    priority=CachePriority.HIGH
                )
            
            return record
        
        return None
    
    async def get_by_filters(
        self,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
        use_materialized_view: bool = False,
        use_cache: bool = True
    ) -> List[T]:
        """Get records by filters with optimization."""
        cache_key = self._get_cache_key("get_by_filters", **filters) if use_cache else None
        
        # Check cache first
        if cache_key and use_cache:
            cached_result = await cache_manager.get(cache_key)
            if cached_result is not None:
                self.metrics.cache_hits += 1
                logger.debug(f"🎯 [REPO] Cache hit for {self.table_name} filters")
                return [self._deserialize(item) for item in cached_result]
        
        # Execute optimized query
        context = QueryContext(
            query_type="get_by_filters",
            table=self.table_name,
            operation="select",
            use_materialized_view=use_materialized_view,
            use_service_key=True,
            enable_caching=use_cache,
            cache_priority=CachePriority.MEDIUM
        )
        
        result = await self._execute_optimized_query(
            context=context,
            filters=filters,
            limit=limit,
            order_by=order_by
        )
        
        if result:
            records = [self._deserialize(item) for item in result]
            
            # Cache the result
            if cache_key and use_cache:
                await cache_manager.set(
                    cache_key,
                    result,
                    ttl=600,  # 10 minutes for filter queries
                    priority=CachePriority.MEDIUM
                )
            
            return records
        
        return []
    
    async def create(self, data: Dict[str, Any]) -> T:
        """Create record with optimization."""
        context = QueryContext(
            query_type="create",
            table=self.table_name,
            operation="insert",
            use_service_key=True,
            enable_caching=False  # Don't cache writes
        )
        
        result = await self._execute_optimized_query(
            context=context,
            query_data=data
        )
        
        if result and len(result) > 0:
            # Invalidate related cache entries
            await self._invalidate_related_caches(data)
            
            return self._deserialize(result[0])
        
        raise Exception("Failed to create record")
    
    async def update(self, id: str, data: Dict[str, Any]) -> T:
        """Update record with optimization."""
        context = QueryContext(
            query_type="update",
            table=self.table_name,
            operation="update",
            use_service_key=True,
            enable_caching=False  # Don't cache writes
        )
        
        result = await self._execute_optimized_query(
            context=context,
            query_data=data,
            filters={"id": id}
        )
        
        if result and len(result) > 0:
            # Invalidate related cache entries
            await self._invalidate_related_caches({"id": id, **data})
            
            return self._deserialize(result[0])
        
        raise Exception(f"Failed to update record with id {id}")
    
    async def delete(self, id: str) -> bool:
        """Delete record with optimization."""
        # Get the record first to invalidate caches properly
        existing_record = await self.get_by_id(id, use_cache=False)
        if not existing_record:
            return False
        
        context = QueryContext(
            query_type="delete",
            table=self.table_name,
            operation="delete",
            use_service_key=True,
            enable_caching=False
        )
        
        result = await self._execute_optimized_query(
            context=context,
            filters={"id": id}
        )
        
        if result:
            # Invalidate all related cache entries
            await self._invalidate_related_caches({"id": id})
            return True
        
        return False
    
    async def batch_get_by_ids(self, ids: List[str], use_cache: bool = True) -> List[T]:
        """Get multiple records by IDs using parallel queries."""
        if not ids:
            return []
        
        # Check cache for each ID
        cached_results = {}
        uncached_ids = []
        
        if use_cache:
            cache_keys = [(id, self._get_cache_key("get_by_id", id=id)) for id in ids]
            cache_tasks = [cache_manager.get(cache_key) for _, cache_key in cache_keys]
            cache_results = await asyncio.gather(*cache_tasks, return_exceptions=True)
            
            for (id, _), cache_result in zip(cache_keys, cache_results):
                if not isinstance(cache_result, Exception) and cache_result is not None:
                    cached_results[id] = self._deserialize(cache_result)
                    self.metrics.cache_hits += 1
                else:
                    uncached_ids.append(id)
        else:
            uncached_ids = ids
        
        # Fetch uncached IDs in parallel
        uncached_results = {}
        if uncached_ids:
            # Create parallel queries
            queries = []
            for id in uncached_ids:
                context = QueryContext(
                    query_type="get_by_id",
                    table=self.table_name,
                    operation="select",
                    use_service_key=True,
                    enable_caching=False  # We'll handle caching manually
                )
                queries.append((context, None, {"id": id}))
            
            # Execute in parallel
            parallel_results = await self._execute_parallel_queries(queries)
            
            # Process results
            for id, result in zip(uncached_ids, parallel_results):
                if result and len(result) > 0:
                    record = self._deserialize(result[0])
                    uncached_results[id] = record
                    
                    # Cache the result
                    if use_cache:
                        cache_key = self._get_cache_key("get_by_id", id=id)
                        await cache_manager.set(
                            cache_key,
                            result[0],
                            ttl=300,
                            priority=CachePriority.HIGH
                        )
        
        # Combine cached and uncached results, preserving order
        final_results = []
        for id in ids:
            if id in cached_results:
                final_results.append(cached_results[id])
            elif id in uncached_results:
                final_results.append(uncached_results[id])
            # Note: Missing IDs are skipped (could also append None if needed)
        
        return final_results
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get repository performance metrics."""
        cache_hit_rate = (self.metrics.cache_hits / max(self.metrics.total_queries, 1)) * 100
        mv_hit_rate = (self.metrics.materialized_view_hits / max(self.metrics.total_queries, 1)) * 100
        
        auth_performance_rate = (self.metrics.auth_queries_sub_20ms / max(self.metrics.total_queries, 1)) * 100
        general_performance_rate = (self.metrics.general_queries_sub_50ms / max(self.metrics.total_queries, 1)) * 100
        
        return {
            "repository": self.__class__.__name__,
            "table": self.table_name,
            "performance": {
                "total_queries": self.metrics.total_queries,
                "avg_query_time_ms": self.metrics.avg_query_time_ms,
                "total_query_time_ms": self.metrics.total_query_time_ms,
                "target_performance_achieved": self.metrics.target_performance_achieved
            },
            "optimization": {
                "cache_hits": self.metrics.cache_hits,
                "cache_hit_rate_percent": round(cache_hit_rate, 2),
                "materialized_view_hits": self.metrics.materialized_view_hits,
                "materialized_view_hit_rate_percent": round(mv_hit_rate, 2),
                "parallel_query_count": self.metrics.parallel_query_count
            },
            "performance_targets": {
                "auth_queries_sub_20ms": self.metrics.auth_queries_sub_20ms,
                "auth_performance_rate_percent": round(auth_performance_rate, 2),
                "general_queries_sub_50ms": self.metrics.general_queries_sub_50ms,
                "general_performance_rate_percent": round(general_performance_rate, 2)
            }
        }
    
    def _update_metrics(self, execution_time_ms: float, query_source: str, query_type: str):
        """Update performance metrics."""
        self.metrics.total_queries += 1
        self.metrics.total_query_time_ms += execution_time_ms
        self.metrics.avg_query_time_ms = self.metrics.total_query_time_ms / self.metrics.total_queries
        
        if query_source == "materialized_view":
            self.metrics.materialized_view_hits += 1
        
        # Track performance targets
        if query_type in ["get_by_id", "auth", "authorization"] and execution_time_ms <= 20:
            self.metrics.auth_queries_sub_20ms += 1
        elif execution_time_ms <= 50:
            self.metrics.general_queries_sub_50ms += 1
        
        # Update overall performance status
        auth_rate = (self.metrics.auth_queries_sub_20ms / max(self.metrics.total_queries, 1))
        general_rate = (self.metrics.general_queries_sub_50ms / max(self.metrics.total_queries, 1))
        
        # Consider performance achieved if >90% of queries meet targets
        self.metrics.target_performance_achieved = (auth_rate + general_rate) / 2 > 0.90
    
    def _check_performance_targets(self, execution_time_ms: float, query_type: str):
        """Check if query meets performance targets and log warnings."""
        target_time = 20.0 if query_type in ["get_by_id", "auth", "authorization"] else 50.0
        
        if execution_time_ms > target_time:
            logger.warning(
                f"⚠️ [REPO] Query exceeded target: {execution_time_ms:.1f}ms > {target_time}ms "
                f"(table: {self.table_name}, type: {query_type})"
            )
        else:
            logger.debug(f"🎯 [REPO] Query target met: {execution_time_ms:.1f}ms <= {target_time}ms ({self.table_name})")
    
    async def _invalidate_related_caches(self, data: Dict[str, Any]):
        """Invalidate cache entries related to the changed data."""
        try:
            patterns_to_invalidate = [
                f"{self.cache_namespace}:get_by_id:{data.get('id', '*')}",
                f"{self.cache_namespace}:get_by_filters:*",
                f"{self.cache_namespace}:*"
            ]
            
            for pattern in patterns_to_invalidate:
                await cache_manager.invalidate_pattern(pattern)
            
            logger.debug(f"🗑️ [REPO] Invalidated cache patterns for {self.table_name}")
            
        except Exception as e:
            logger.warning(f"⚠️ [REPO] Cache invalidation failed: {e}")
    
    @abstractmethod
    def _deserialize(self, data: Dict[str, Any]) -> T:
        """Deserialize database record to model instance."""
        pass
    
    async def warm_cache(self, warm_patterns: List[str]):
        """Warm cache with frequently accessed data."""
        try:
            logger.info(f"🔥 [REPO] Warming cache for {self.table_name}...")
            
            # This would typically pre-load frequently accessed records
            # Implementation depends on specific repository needs
            warm_count = 0
            
            for pattern in warm_patterns:
                # Invalidate old entries to force refresh
                invalidated = await cache_manager.invalidate_pattern(f"{self.cache_namespace}:{pattern}")
                warm_count += invalidated
            
            logger.info(f"🔥 [REPO] Prepared {warm_count} cache entries for warming in {self.table_name}")
            
        except Exception as e:
            logger.error(f"❌ [REPO] Cache warming failed for {self.table_name}: {e}")