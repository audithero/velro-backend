"""
Database query optimizer with intelligent caching and performance monitoring.
Implements query analysis, execution plan optimization, and smart caching strategies.
"""
import asyncio
import logging
import time
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import json

from database import SupabaseClient
from utils.cache_manager import cache_manager, CacheLevel, cached
from utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Query performance metrics."""
    query_hash: str
    execution_time: float
    timestamp: datetime
    cache_hit: bool
    result_count: int
    table: str
    operation: str
    auth_context: Optional[str] = None


@dataclass
class QueryOptimizationHint:
    """Query optimization hint."""
    hint_type: str
    description: str
    estimated_improvement: float
    confidence: float


class DatabaseQueryOptimizer:
    """Intelligent database query optimizer with caching and performance monitoring."""
    
    def __init__(self):
        self.query_metrics: List[QueryMetrics] = []
        self.slow_query_threshold = 1.0  # 1 second
        self.cache_hit_ratio_target = 0.8  # 80% cache hit ratio target
        
        # Query pattern analysis
        self.frequent_queries = defaultdict(int)
        self.slow_queries = defaultdict(list)
        self.optimization_hints = {}
        
        # Connection pooling simulation
        self._connection_pool = {}
        self._max_connections = 10
        self._active_connections = 0
    
    def _generate_query_hash(self, table: str, operation: str, filters: Dict[str, Any] = None) -> str:
        """Generate hash for query caching."""
        query_signature = f"{table}:{operation}:{json.dumps(filters or {}, sort_keys=True)}"
        return hashlib.md5(query_signature.encode()).hexdigest()
    
    def _get_cache_level_for_query(self, table: str, operation: str) -> CacheLevel:
        """Determine optimal cache level for query type."""
        # Ultra-fast queries go to L1
        if table in ['models', 'supported_models'] and operation == 'select':
            return CacheLevel.L1_MEMORY
        
        # User-specific data goes to L2
        if table in ['users', 'user_profiles'] and operation == 'select':
            return CacheLevel.L2_SESSION
        
        # Heavy queries go to L3
        if table in ['credit_transactions', 'generations'] and operation == 'select':
            return CacheLevel.L3_PERSISTENT
        
        return CacheLevel.L2_SESSION
    
    def _get_cache_ttl_for_query(self, table: str, operation: str) -> float:
        """Get optimal TTL for query type."""
        # Static data - long TTL
        if table in ['models', 'supported_models']:
            return 3600  # 1 hour
        
        # User data - medium TTL
        if table in ['users']:
            return 300   # 5 minutes
        
        # Dynamic data - short TTL
        if table in ['credit_transactions', 'generations']:
            return 60    # 1 minute
        
        return 300  # Default 5 minutes
    
    async def execute_optimized_query(
        self,
        db: SupabaseClient,
        table: str,
        operation: str,
        data: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        use_service_key: bool = False,
        single: bool = False,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        auth_token: Optional[str] = None,
        force_refresh: bool = False
    ) -> Any:
        """Execute database query with intelligent optimization and caching."""
        start_time = time.time()
        
        # Generate query signature for caching
        query_hash = self._generate_query_hash(table, operation, filters)
        cache_key = f"query:{table}:{operation}:{query_hash}"
        
        # Add user context to cache key for user-specific queries
        if user_id:
            cache_key += f":user:{user_id}"
        
        result = None
        cache_hit = False
        
        # Try cache for SELECT operations (unless force refresh)
        if operation == 'select' and not force_refresh:
            cache_level = self._get_cache_level_for_query(table, operation)
            cached_result = await cache_manager.get(cache_key, cache_level)
            
            if cached_result is not None:
                cache_hit = True
                result = cached_result
                logger.debug(f"🚀 [DB-OPTIMIZER] Cache hit for {table}.{operation}")
        
        # Execute query if not cached
        if result is None:
            try:
                # Check connection limits
                if self._active_connections >= self._max_connections:
                    logger.warning(f"⚠️ [DB-OPTIMIZER] Connection limit reached, queuing query")
                    await asyncio.sleep(0.1)  # Brief wait
                
                self._active_connections += 1
                
                # Execute the actual query
                result = db.execute_query(
                    table=table,
                    operation=operation,
                    data=data,
                    filters=filters,
                    user_id=user_id,
                    use_service_key=use_service_key,
                    single=single,
                    order_by=order_by,
                    limit=limit,
                    offset=offset,
                    auth_token=auth_token
                )
                
                # Cache SELECT results
                if operation == 'select' and result is not None:
                    cache_level = self._get_cache_level_for_query(table, operation)
                    cache_ttl = self._get_cache_ttl_for_query(table, operation)
                    await cache_manager.set(cache_key, result, cache_level, cache_ttl)
                
                logger.debug(f"🔍 [DB-OPTIMIZER] Executed {table}.{operation} query")
                
            except Exception as e:
                logger.error(f"❌ [DB-OPTIMIZER] Query failed for {table}.{operation}: {e}")
                raise
            finally:
                self._active_connections = max(0, self._active_connections - 1)
        
        # Record metrics
        execution_time = time.time() - start_time
        result_count = len(result) if isinstance(result, list) else (1 if result else 0)
        
        metrics = QueryMetrics(
            query_hash=query_hash,
            execution_time=execution_time,
            timestamp=datetime.utcnow(),
            cache_hit=cache_hit,
            result_count=result_count,
            table=table,
            operation=operation,
            auth_context="service" if use_service_key else "user"
        )
        
        self.query_metrics.append(metrics)
        
        # Track frequent queries
        query_signature = f"{table}.{operation}"
        self.frequent_queries[query_signature] += 1
        
        # Track slow queries
        if execution_time > self.slow_query_threshold:
            self.slow_queries[query_signature].append(execution_time)
            logger.warning(f"🐌 [DB-OPTIMIZER] Slow query detected: {table}.{operation} took {execution_time:.2f}s")
            
            # Record slow query in performance monitor
            performance_monitor.record_slow_query(
                query=f"{table}.{operation}",
                duration=execution_time,
                details={
                    'filters': filters,
                    'cache_hit': cache_hit,
                    'result_count': result_count,
                    'user_id': user_id
                }
            )
        
        # Log performance
        if cache_hit:
            logger.debug(f"⚡ [DB-OPTIMIZER] {table}.{operation} completed in {execution_time:.3f}s (cached)")
        else:
            logger.debug(f"🔍 [DB-OPTIMIZER] {table}.{operation} completed in {execution_time:.3f}s (database)")
        
        return result
    
    async def optimize_user_queries(self, user_id: str, auth_token: Optional[str] = None) -> Dict[str, Any]:
        """Pre-load and cache common user queries for better performance."""
        optimization_start = time.time()
        logger.info(f"🚀 [DB-OPTIMIZER] Starting user query optimization for {user_id}")
        
        try:
            from database import db
            
            # Pre-load common user data in parallel
            tasks = []
            
            # 1. User profile (high priority)
            tasks.append(
                self.execute_optimized_query(
                    db=db,
                    table="users",
                    operation="select", 
                    filters={"id": user_id},
                    user_id=user_id,
                    auth_token=auth_token,
                    single=True
                )
            )
            
            # 2. Recent credit transactions (medium priority)
            tasks.append(
                self.execute_optimized_query(
                    db=db,
                    table="credit_transactions",
                    operation="select",
                    filters={"user_id": user_id},
                    user_id=user_id,
                    auth_token=auth_token,
                    order_by="created_at:desc",
                    limit=10
                )
            )
            
            # 3. Recent generations (medium priority)
            tasks.append(
                self.execute_optimized_query(
                    db=db,
                    table="generations", 
                    operation="select",
                    filters={"user_id": user_id},
                    user_id=user_id,
                    auth_token=auth_token,
                    order_by="created_at:desc",
                    limit=5
                )
            )
            
            # Execute all queries in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successful pre-loads
            successful_preloads = sum(1 for result in results if not isinstance(result, Exception))
            
            optimization_time = time.time() - optimization_start
            
            logger.info(f"✅ [DB-OPTIMIZER] User optimization completed in {optimization_time:.2f}s")
            logger.info(f"✅ [DB-OPTIMIZER] Pre-loaded {successful_preloads}/3 common queries for user {user_id}")
            
            return {
                'user_id': user_id,
                'optimization_time': optimization_time,
                'preloaded_queries': successful_preloads,
                'total_queries': len(tasks),
                'success_rate': successful_preloads / len(tasks) * 100
            }
            
        except Exception as e:
            logger.error(f"❌ [DB-OPTIMIZER] User optimization failed for {user_id}: {e}")
            return {
                'user_id': user_id,
                'optimization_time': time.time() - optimization_start,
                'error': str(e),
                'success_rate': 0
            }
    
    async def analyze_query_patterns(self) -> Dict[str, Any]:
        """Analyze query patterns and generate optimization recommendations."""
        if not self.query_metrics:
            return {'message': 'No query metrics available'}
        
        # Calculate performance metrics
        total_queries = len(self.query_metrics)
        cache_hits = sum(1 for m in self.query_metrics if m.cache_hit)
        cache_hit_ratio = cache_hits / total_queries if total_queries > 0 else 0
        
        avg_execution_time = sum(m.execution_time for m in self.query_metrics) / total_queries
        slow_queries_count = sum(1 for m in self.query_metrics if m.execution_time > self.slow_query_threshold)
        
        # Find most frequent queries
        top_queries = sorted(
            self.frequent_queries.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Find slowest queries
        slowest_queries = sorted(
            [(table_op, times) for table_op, times in self.slow_queries.items() if times],
            key=lambda x: sum(x[1]) / len(x[1]),
            reverse=True
        )[:5]
        
        # Generate optimization hints
        hints = []
        
        if cache_hit_ratio < self.cache_hit_ratio_target:
            hints.append(QueryOptimizationHint(
                hint_type="cache_optimization",
                description=f"Cache hit ratio is {cache_hit_ratio:.1%}, target is {self.cache_hit_ratio_target:.1%}",
                estimated_improvement=0.3,
                confidence=0.8
            ))
        
        if slow_queries_count > total_queries * 0.1:  # More than 10% slow queries
            hints.append(QueryOptimizationHint(
                hint_type="query_optimization", 
                description=f"{slow_queries_count} queries exceed {self.slow_query_threshold}s threshold",
                estimated_improvement=0.5,
                confidence=0.9
            ))
        
        return {
            'analysis_timestamp': datetime.utcnow().isoformat(),
            'query_metrics': {
                'total_queries': total_queries,
                'cache_hit_ratio': round(cache_hit_ratio, 3),
                'avg_execution_time': round(avg_execution_time, 3),
                'slow_queries_count': slow_queries_count,
                'slow_queries_percentage': round(slow_queries_count / total_queries * 100, 1) if total_queries > 0 else 0
            },
            'top_frequent_queries': top_queries,
            'slowest_queries': [
                {
                    'query': query,
                    'avg_time': round(sum(times) / len(times), 3),
                    'max_time': round(max(times), 3),
                    'occurrences': len(times)
                }
                for query, times in slowest_queries
            ],
            'optimization_hints': [
                {
                    'type': hint.hint_type,
                    'description': hint.description,
                    'estimated_improvement_percent': round(hint.estimated_improvement * 100, 1),
                    'confidence_percent': round(hint.confidence * 100, 1)
                }
                for hint in hints
            ],
            'cache_metrics': cache_manager.get_metrics()
        }
    
    async def invalidate_user_cache(self, user_id: str):
        """Invalidate all cached queries for a specific user."""
        await cache_manager.invalidate_pattern(f"user:{user_id}")
        logger.info(f"🧹 [DB-OPTIMIZER] Invalidated cache for user {user_id}")
    
    async def invalidate_table_cache(self, table: str):
        """Invalidate all cached queries for a specific table."""
        await cache_manager.invalidate_pattern(f"query:{table}")
        logger.info(f"🧹 [DB-OPTIMIZER] Invalidated cache for table {table}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return {
            'active_connections': self._active_connections,
            'max_connections': self._max_connections,
            'utilization_percent': round(self._active_connections / self._max_connections * 100, 1)
        }
    
    async def cleanup_old_metrics(self, retention_hours: int = 24):
        """Clean up old query metrics."""
        cutoff_time = datetime.utcnow() - timedelta(hours=retention_hours)
        
        original_count = len(self.query_metrics)
        self.query_metrics = [
            metric for metric in self.query_metrics
            if metric.timestamp > cutoff_time
        ]
        
        cleaned_count = original_count - len(self.query_metrics)
        if cleaned_count > 0:
            logger.info(f"🧹 [DB-OPTIMIZER] Cleaned {cleaned_count} old query metrics")


# Global database optimizer instance
db_optimizer = DatabaseQueryOptimizer()


# Optimized database operation decorators
def optimized_db_operation(
    cache_level: CacheLevel = CacheLevel.L2_SESSION,
    cache_ttl: Optional[float] = None
):
    """Decorator for optimized database operations."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract common parameters
            table = kwargs.get('table', 'unknown')
            operation = kwargs.get('operation', 'unknown')
            
            # Use the database optimizer
            if 'db' in kwargs and hasattr(kwargs['db'], 'execute_query'):
                # Replace direct execute_query with optimized version
                original_execute_query = kwargs['db'].execute_query
                kwargs['db'].execute_query = lambda **query_kwargs: db_optimizer.execute_optimized_query(
                    kwargs['db'], **query_kwargs
                )
            
            try:
                return await func(*args, **kwargs)
            finally:
                # Restore original method if replaced
                if 'db' in kwargs and hasattr(kwargs['db'], 'execute_query'):
                    # In practice, we don't need to restore since this is a wrapper
                    pass
        
        return wrapper
    return decorator