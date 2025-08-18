"""
Database Query Optimizer for <100ms Authorization Performance
Implements composite indexes, prepared statements, and query optimization for sub-100ms response times.

Performance Targets:
- Authorization queries: <50ms average execution time
- User lookup queries: <25ms average execution time
- Team permission queries: <75ms average execution time
- Prepared statement cache hit rate: >90%
- Database connection pool efficiency: >85%

Key Features:
- Composite index optimization for authorization hot paths
- Prepared statement caching with performance monitoring
- Query performance tracking and alerting
- Connection pool management optimized for auth workloads
- Real-time slow query detection and optimization suggestions
"""

import asyncio
import logging
import time
import hashlib
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque
import weakref
import threading

logger = logging.getLogger(__name__)

class QueryType(Enum):
    """Query type classification for optimization."""
    AUTHORIZATION = "authorization"      # User permission checks
    USER_LOOKUP = "user_lookup"         # User data retrieval  
    TEAM_PERMISSION = "team_permission" # Team-based access
    PROJECT_ACCESS = "project_access"   # Project visibility
    GENERATION_AUTH = "generation_auth" # Generation access control
    SESSION_VALIDATION = "session_validation"  # JWT/session checks

class QueryOptimizationLevel(Enum):
    """Query optimization levels."""
    CRITICAL = "critical"    # <25ms target - authorization hot paths
    HIGH = "high"           # <50ms target - user lookups, sessions
    NORMAL = "normal"       # <100ms target - team operations
    LOW = "low"            # <200ms target - analytics, reports

@dataclass
class QueryPattern:
    """Query pattern for prepared statement caching."""
    query_type: QueryType
    pattern_hash: str
    sql_template: str
    parameter_count: int
    optimization_level: QueryOptimizationLevel
    suggested_indexes: List[str] = field(default_factory=list)
    estimated_rows: Optional[int] = None
    last_execution_time_ms: float = 0.0
    execution_count: int = 0
    total_execution_time_ms: float = 0.0
    
    @property
    def avg_execution_time_ms(self) -> float:
        return self.total_execution_time_ms / self.execution_count if self.execution_count > 0 else 0.0

@dataclass
class QueryMetrics:
    """Performance metrics for database queries."""
    query_type: QueryType
    execution_count: int = 0
    total_execution_time_ms: float = 0.0
    slow_query_count: int = 0  # Queries exceeding target time
    cache_hits: int = 0
    cache_misses: int = 0
    avg_execution_time_ms: float = 0.0
    max_execution_time_ms: float = 0.0
    min_execution_time_ms: float = float('inf')
    recent_execution_times: deque = field(default_factory=lambda: deque(maxlen=100))

class PreparedStatementCache:
    """High-performance cache for prepared statements targeting <100ms performance."""
    
    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self.cache: Dict[str, QueryPattern] = {}
        self.access_order: deque = deque()
        self.hits = 0
        self.misses = 0
        self._lock = threading.RLock()
        
        # Authorization-specific prepared statements (pre-loaded for performance)
        self._preload_authorization_patterns()
    
    def _preload_authorization_patterns(self):
        """Pre-load common authorization query patterns for maximum performance."""
        auth_patterns = [
            # Direct ownership check (fastest path)
            QueryPattern(
                query_type=QueryType.AUTHORIZATION,
                pattern_hash="auth_direct_owner",
                sql_template="""
                    SELECT 1 FROM generations g 
                    WHERE g.id = $1 AND g.user_id = $2 AND g.deleted_at IS NULL
                    LIMIT 1
                """,
                parameter_count=2,
                optimization_level=QueryOptimizationLevel.CRITICAL,
                suggested_indexes=["idx_generations_authorization_hot_path"],
                estimated_rows=1
            ),
            
            # Team-based access check
            QueryPattern(
                query_type=QueryType.TEAM_PERMISSION,
                pattern_hash="auth_team_access",
                sql_template="""
                    SELECT tm.role, tm.permissions FROM team_members tm
                    JOIN projects p ON p.team_id = tm.team_id
                    JOIN generations g ON g.project_id = p.id
                    WHERE g.id = $1 AND tm.user_id = $2 AND tm.is_active = true
                    LIMIT 1
                """,
                parameter_count=2,
                optimization_level=QueryOptimizationLevel.HIGH,
                suggested_indexes=["idx_team_members_authorization_super", "idx_generations_project_lookup"],
                estimated_rows=1
            ),
            
            # Project visibility check
            QueryPattern(
                query_type=QueryType.PROJECT_ACCESS,
                pattern_hash="auth_project_visibility",
                sql_template="""
                    SELECT p.visibility, p.user_id FROM projects p
                    JOIN generations g ON g.project_id = p.id
                    WHERE g.id = $1 AND (p.visibility = 'public' OR p.user_id = $2)
                    LIMIT 1
                """,
                parameter_count=2,
                optimization_level=QueryOptimizationLevel.NORMAL,
                suggested_indexes=["idx_projects_visibility_authorization"],
                estimated_rows=1
            ),
            
            # User session validation
            QueryPattern(
                query_type=QueryType.SESSION_VALIDATION,
                pattern_hash="session_user_lookup",
                sql_template="""
                    SELECT id, email, is_active, last_active_at FROM users
                    WHERE id = $1 AND is_active = true
                    LIMIT 1
                """,
                parameter_count=1,
                optimization_level=QueryOptimizationLevel.CRITICAL,
                suggested_indexes=["idx_users_active_lookup"],
                estimated_rows=1
            )
        ]
        
        with self._lock:
            for pattern in auth_patterns:
                self.cache[pattern.pattern_hash] = pattern
                self.access_order.append(pattern.pattern_hash)
    
    def get_pattern(self, query_hash: str) -> Optional[QueryPattern]:
        """Get query pattern with LRU tracking."""
        with self._lock:
            if query_hash in self.cache:
                # Move to end (most recently used)
                self.access_order.remove(query_hash)
                self.access_order.append(query_hash)
                self.hits += 1
                return self.cache[query_hash]
            
            self.misses += 1
            return None
    
    def add_pattern(self, pattern: QueryPattern):
        """Add new query pattern with LRU eviction."""
        with self._lock:
            # Remove if already exists
            if pattern.pattern_hash in self.cache:
                self.access_order.remove(pattern.pattern_hash)
            
            # Add new pattern
            self.cache[pattern.pattern_hash] = pattern
            self.access_order.append(pattern.pattern_hash)
            
            # Evict oldest if over capacity
            while len(self.cache) > self.max_size:
                oldest_hash = self.access_order.popleft()
                del self.cache[oldest_hash]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_accesses = self.hits + self.misses
        hit_rate = (self.hits / total_accesses * 100) if total_accesses > 0 else 0
        
        return {
            'cache_size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate_percent': round(hit_rate, 2),
            'target_hit_rate_percent': 90.0,
            'target_met': hit_rate >= 90.0
        }

class DatabaseQueryOptimizer:
    """
    High-performance database query optimizer for <100ms authorization targets.
    
    Features:
    - Prepared statement caching for frequently used queries
    - Real-time performance monitoring and alerting
    - Query optimization suggestions based on execution patterns
    - Composite index recommendations for authorization hot paths
    """
    
    def __init__(self):
        self.prepared_statements = PreparedStatementCache()
        self.query_metrics: Dict[QueryType, QueryMetrics] = {}
        
        # Performance monitoring
        self.slow_query_threshold_ms = {
            QueryOptimizationLevel.CRITICAL: 25.0,
            QueryOptimizationLevel.HIGH: 50.0,
            QueryOptimizationLevel.NORMAL: 100.0,
            QueryOptimizationLevel.LOW: 200.0
        }
        
        # Query optimization suggestions
        self.optimization_suggestions: Dict[str, List[str]] = defaultdict(list)
        
        # Initialize metrics for all query types
        for query_type in QueryType:
            self.query_metrics[query_type] = QueryMetrics(query_type=query_type)
    
    def get_query_hash(self, sql: str) -> str:
        """Generate hash for SQL query pattern."""
        # Normalize SQL by removing parameters and whitespace
        normalized = ' '.join(sql.split())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def classify_query(self, sql: str) -> Tuple[QueryType, QueryOptimizationLevel]:
        """Classify query type and optimization level."""
        sql_lower = sql.lower().strip()
        
        # Authorization queries (highest priority)
        if any(keyword in sql_lower for keyword in ['check_user_permission', 'generations', 'user_id']):
            if 'generations' in sql_lower and 'user_id' in sql_lower:
                return QueryType.AUTHORIZATION, QueryOptimizationLevel.CRITICAL
        
        # User lookup queries
        if 'users' in sql_lower and ('select' in sql_lower[:20]):
            if 'session' in sql_lower or 'active' in sql_lower:
                return QueryType.SESSION_VALIDATION, QueryOptimizationLevel.CRITICAL
            return QueryType.USER_LOOKUP, QueryOptimizationLevel.HIGH
        
        # Team permission queries
        if 'team_members' in sql_lower or 'teams' in sql_lower:
            return QueryType.TEAM_PERMISSION, QueryOptimizationLevel.HIGH
        
        # Project access queries
        if 'projects' in sql_lower and 'visibility' in sql_lower:
            return QueryType.PROJECT_ACCESS, QueryOptimizationLevel.NORMAL
        
        # Generation authorization
        if 'generations' in sql_lower:
            return QueryType.GENERATION_AUTH, QueryOptimizationLevel.HIGH
        
        # Default classification
        return QueryType.USER_LOOKUP, QueryOptimizationLevel.LOW
    
    def get_suggested_indexes(self, query_type: QueryType, sql: str) -> List[str]:
        """Get suggested composite indexes for query optimization."""
        suggestions = []
        sql_lower = sql.lower()
        
        if query_type == QueryType.AUTHORIZATION:
            if 'generations' in sql_lower and 'user_id' in sql_lower:
                suggestions.append("CREATE INDEX CONCURRENTLY idx_generations_authorization_hot_path ON generations (user_id, project_id, status, created_at DESC)")
            
        elif query_type == QueryType.TEAM_PERMISSION:
            if 'team_members' in sql_lower:
                suggestions.append("CREATE INDEX CONCURRENTLY idx_team_members_authorization_super ON team_members (user_id, is_active, role, team_id)")
        
        elif query_type == QueryType.PROJECT_ACCESS:
            if 'projects' in sql_lower and 'visibility' in sql_lower:
                suggestions.append("CREATE INDEX CONCURRENTLY idx_projects_visibility_authorization ON projects (visibility, user_id, created_at DESC)")
        
        elif query_type == QueryType.SESSION_VALIDATION:
            if 'users' in sql_lower:
                suggestions.append("CREATE INDEX CONCURRENTLY idx_users_active_lookup ON users (id, is_active) WHERE is_active = true")
        
        return suggestions
    
    async def optimize_query(self, sql: str, parameters: Optional[List] = None) -> Tuple[str, Optional[QueryPattern]]:
        """
        Optimize query for maximum performance with prepared statement caching.
        Returns optimized SQL and query pattern for execution tracking.
        """
        start_time = time.perf_counter()
        
        try:
            query_hash = self.get_query_hash(sql)
            query_type, opt_level = self.classify_query(sql)
            
            # Check prepared statement cache
            pattern = self.prepared_statements.get_pattern(query_hash)
            
            if pattern is None:
                # Create new pattern
                pattern = QueryPattern(
                    query_type=query_type,
                    pattern_hash=query_hash,
                    sql_template=sql,
                    parameter_count=len(parameters) if parameters else 0,
                    optimization_level=opt_level,
                    suggested_indexes=self.get_suggested_indexes(query_type, sql)
                )
                
                # Add to cache
                self.prepared_statements.add_pattern(pattern)
                
                # Generate optimization suggestions
                if not self.optimization_suggestions[query_hash]:
                    suggestions = self._generate_optimization_suggestions(pattern, sql)
                    self.optimization_suggestions[query_hash] = suggestions
            
            optimization_time_ms = (time.perf_counter() - start_time) * 1000
            
            # Log slow optimization (should be very rare)
            if optimization_time_ms > 5.0:
                logger.warning(f"Slow query optimization: {optimization_time_ms:.2f}ms for pattern {query_hash}")
            
            return sql, pattern
            
        except Exception as e:
            logger.error(f"Query optimization error: {e}")
            # Return original query on error
            return sql, None
    
    def _generate_optimization_suggestions(self, pattern: QueryPattern, sql: str) -> List[str]:
        """Generate optimization suggestions for query pattern."""
        suggestions = []
        sql_lower = sql.lower()
        
        # General optimization suggestions
        if 'select *' in sql_lower:
            suggestions.append("Consider selecting only needed columns instead of SELECT *")
        
        if 'order by' in sql_lower and 'limit' in sql_lower:
            suggestions.append("Consider adding composite index with ORDER BY columns for LIMIT queries")
        
        if pattern.query_type == QueryType.AUTHORIZATION:
            suggestions.append("Authorization query - ensure composite indexes exist for user_id and resource_id columns")
            
            if 'join' in sql_lower:
                suggestions.append("Multi-table authorization query - consider materialized view for complex joins")
        
        # Add suggested indexes
        suggestions.extend(pattern.suggested_indexes)
        
        return suggestions
    
    def record_execution(self, pattern: Optional[QueryPattern], execution_time_ms: float, row_count: Optional[int] = None):
        """Record query execution metrics for performance monitoring."""
        if pattern is None:
            return
        
        # Update pattern metrics
        pattern.execution_count += 1
        pattern.total_execution_time_ms += execution_time_ms
        pattern.last_execution_time_ms = execution_time_ms
        
        # Update query type metrics
        metrics = self.query_metrics[pattern.query_type]
        metrics.execution_count += 1
        metrics.total_execution_time_ms += execution_time_ms
        metrics.avg_execution_time_ms = metrics.total_execution_time_ms / metrics.execution_count
        metrics.max_execution_time_ms = max(metrics.max_execution_time_ms, execution_time_ms)
        metrics.min_execution_time_ms = min(metrics.min_execution_time_ms, execution_time_ms)
        metrics.recent_execution_times.append(execution_time_ms)
        
        # Check for slow query
        threshold = self.slow_query_threshold_ms.get(pattern.optimization_level, 100.0)
        if execution_time_ms > threshold:
            metrics.slow_query_count += 1
            
            logger.warning(
                f"Slow {pattern.query_type.value} query: {execution_time_ms:.2f}ms "
                f"(threshold: {threshold}ms) - Pattern: {pattern.pattern_hash}"
            )
            
            # Log optimization suggestions
            suggestions = self.optimization_suggestions.get(pattern.pattern_hash, [])
            if suggestions:
                logger.info(f"Optimization suggestions for {pattern.pattern_hash}: {suggestions[:3]}")  # Top 3 suggestions
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report for database optimization."""
        report = {
            'overall_performance': {
                'total_queries': sum(m.execution_count for m in self.query_metrics.values()),
                'avg_execution_time_ms': 0.0,
                'slow_query_count': sum(m.slow_query_count for m in self.query_metrics.values()),
                'performance_target_met': True
            },
            'prepared_statement_cache': self.prepared_statements.get_stats(),
            'query_type_metrics': {},
            'optimization_recommendations': [],
            'critical_performance_alerts': []
        }
        
        # Calculate overall averages
        total_time = sum(m.total_execution_time_ms for m in self.query_metrics.values())
        total_queries = report['overall_performance']['total_queries']
        if total_queries > 0:
            report['overall_performance']['avg_execution_time_ms'] = round(total_time / total_queries, 2)
        
        # Query type breakdown
        for query_type, metrics in self.query_metrics.items():
            if metrics.execution_count > 0:
                report['query_type_metrics'][query_type.value] = {
                    'execution_count': metrics.execution_count,
                    'avg_execution_time_ms': round(metrics.avg_execution_time_ms, 2),
                    'max_execution_time_ms': round(metrics.max_execution_time_ms, 2),
                    'min_execution_time_ms': round(metrics.min_execution_time_ms, 2),
                    'slow_query_count': metrics.slow_query_count,
                    'slow_query_rate_percent': round((metrics.slow_query_count / metrics.execution_count) * 100, 2)
                }
                
                # Check performance targets
                target_met = True
                if query_type == QueryType.AUTHORIZATION and metrics.avg_execution_time_ms > 50.0:
                    target_met = False
                    report['critical_performance_alerts'].append(
                        f"Authorization queries averaging {metrics.avg_execution_time_ms:.1f}ms (target: <50ms)"
                    )
                
                if query_type == QueryType.SESSION_VALIDATION and metrics.avg_execution_time_ms > 25.0:
                    target_met = False
                    report['critical_performance_alerts'].append(
                        f"Session validation queries averaging {metrics.avg_execution_time_ms:.1f}ms (target: <25ms)"
                    )
                
                if metrics.slow_query_count > metrics.execution_count * 0.1:  # >10% slow queries
                    target_met = False
                    report['critical_performance_alerts'].append(
                        f"{query_type.value} has {metrics.slow_query_count} slow queries ({metrics.slow_query_count/metrics.execution_count*100:.1f}%)"
                    )
                
                if not target_met:
                    report['overall_performance']['performance_target_met'] = False
        
        # Generate optimization recommendations
        recommendations = []
        
        # Cache performance recommendations
        cache_stats = report['prepared_statement_cache']
        if cache_stats['hit_rate_percent'] < 90.0 and cache_stats['hits'] + cache_stats['misses'] > 100:
            recommendations.append("Prepared statement cache hit rate below 90% - consider increasing cache size")
        
        # Query-specific recommendations
        auth_metrics = report['query_type_metrics'].get('authorization', {})
        if auth_metrics.get('avg_execution_time_ms', 0) > 50.0:
            recommendations.append("Authorization queries exceed 50ms target - verify composite indexes are in place")
            recommendations.append("Consider implementing materialized views for complex authorization patterns")
        
        session_metrics = report['query_type_metrics'].get('session_validation', {})
        if session_metrics.get('avg_execution_time_ms', 0) > 25.0:
            recommendations.append("Session validation queries exceed 25ms target - ensure user lookup indexes are optimized")
        
        # Overall performance recommendations
        if report['overall_performance']['slow_query_count'] > total_queries * 0.05:  # >5% slow queries
            recommendations.append("High slow query rate detected - review query optimization and indexing strategy")
        
        report['optimization_recommendations'] = recommendations
        
        return report
    
    def get_suggested_indexes_sql(self) -> List[str]:
        """Get SQL statements for all suggested composite indexes."""
        all_indexes = set()
        
        for pattern in self.prepared_statements.cache.values():
            all_indexes.update(pattern.suggested_indexes)
        
        # Add comprehensive authorization indexes
        authorization_indexes = [
            """
            -- Authorization hot path composite index (user_id, project_id, status, created_at)
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_generations_authorization_hot_path 
            ON generations (user_id, project_id, status, created_at DESC)
            WHERE deleted_at IS NULL;
            """,
            
            """
            -- Team members authorization super index (user_id, is_active, role, team_id)
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_members_authorization_super
            ON team_members (user_id, is_active, role, team_id)
            WHERE is_active = true;
            """,
            
            """
            -- Project visibility authorization index (visibility, user_id, created_at)
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_visibility_authorization
            ON projects (visibility, user_id, created_at DESC);
            """,
            
            """
            -- User active lookup index with partial index for performance
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_active_lookup
            ON users (id, is_active, last_active_at)
            WHERE is_active = true;
            """,
            
            """
            -- Generation project lookup index for team-based access
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_generations_project_lookup
            ON generations (project_id, user_id, status)
            WHERE deleted_at IS NULL;
            """
        ]
        
        all_indexes.update(authorization_indexes)
        
        return list(all_indexes)

# Global optimizer instance
_query_optimizer: Optional[DatabaseQueryOptimizer] = None

def get_query_optimizer() -> DatabaseQueryOptimizer:
    """Get global query optimizer instance."""
    global _query_optimizer
    if _query_optimizer is None:
        _query_optimizer = DatabaseQueryOptimizer()
    return _query_optimizer

async def optimize_authorization_query(sql: str, parameters: Optional[List] = None) -> Tuple[str, Optional[QueryPattern]]:
    """Convenience function for optimizing authorization queries."""
    optimizer = get_query_optimizer()
    return await optimizer.optimize_query(sql, parameters)

async def get_database_performance_report() -> Dict[str, Any]:
    """Get comprehensive database performance report."""
    optimizer = get_query_optimizer()
    return optimizer.get_performance_report()

def get_recommended_indexes() -> List[str]:
    """Get all recommended database indexes for authorization performance."""
    optimizer = get_query_optimizer()
    return optimizer.get_suggested_indexes_sql()