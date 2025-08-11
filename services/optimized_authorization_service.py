"""
Optimized Authorization Service Integration
Production-ready UUID authorization system with enterprise-scale performance.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID
import json

from utils.db_connection_pool import get_pool_manager, PoolType
from utils.performance_monitor import performance_monitor
from lib.services.authorization_service import authorizationService
from models.user import User
from models.project import Project
from models.generation import Generation

logger = logging.getLogger(__name__)

class OptimizedAuthorizationService:
    """
    Enterprise-grade authorization service with performance optimization.
    Integrates database connection pooling, caching, and monitoring.
    """
    
    def __init__(self):
        self.pool_manager = None
        self.cache_enabled = True
        self.monitoring_enabled = True
        
    async def initialize(self, database_url: str):
        """Initialize the optimized authorization service"""
        logger.info("Initializing optimized authorization service...")
        
        # Initialize connection pool manager
        self.pool_manager = await get_pool_manager(database_url)
        
        # Start performance monitoring
        if self.monitoring_enabled:
            await performance_monitor.start_monitoring(interval_seconds=30)
        
        # Apply database optimizations
        await self._apply_database_optimizations()
        
        logger.info("Optimized authorization service initialized successfully")
        
    async def _apply_database_optimizations(self):
        """Apply database performance optimizations"""
        try:
            async with self.pool_manager.get_write_connection() as conn:
                # Run the performance optimization migration
                logger.info("Applying database performance optimizations...")
                
                # Check if optimizations are already applied
                result = await conn.fetchrow("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'authorization_cache'
                    )
                """)
                
                if not result['exists']:
                    # Apply the migration
                    migration_path = "/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend/migrations/012_performance_optimization_authorization.sql"
                    
                    with open(migration_path, 'r') as f:
                        migration_sql = f.read()
                    
                    await conn.execute(migration_sql)
                    logger.info("Database performance optimizations applied successfully")
                else:
                    logger.info("Database performance optimizations already applied")
                    
        except Exception as e:
            logger.error(f"Failed to apply database optimizations: {e}")
            
    async def check_user_permission_optimized(
        self, 
        user_id: str, 
        resource_type: str, 
        resource_id: str, 
        permission_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        High-performance permission check with monitoring and caching.
        """
        start_time = time.perf_counter()
        
        try:
            # Use optimized database function
            result = await self.pool_manager.check_user_permission(
                user_id, resource_type, resource_id, permission_type
            )
            
            # Record performance metrics
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            performance_monitor.record_permission_check(
                execution_time_ms, 
                cache_hit=result.get('decision_factors', [None])[0] == 'cache_hit',
                success=result.get('access_granted', False)
            )
            
            # Add additional context if needed
            if context:
                result['context'] = context
                
            return {
                'access_granted': result.get('access_granted', False),
                'effective_role': result.get('effective_role', 'none'),
                'decision_factors': result.get('decision_factors', []),
                'execution_time_ms': execution_time_ms,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            # Record failure metrics
            performance_monitor.record_permission_check(
                execution_time_ms, 
                cache_hit=False, 
                success=False
            )
            
            logger.error(f"Permission check failed: {e}")
            
            return {
                'access_granted': False,
                'effective_role': 'none',
                'decision_factors': ['error'],
                'error': str(e),
                'execution_time_ms': execution_time_ms,
                'timestamp': datetime.now().isoformat()
            }
    
    async def batch_permission_check(
        self,
        user_id: str,
        permission_requests: List[Dict[str, str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch permission checking for multiple resources.
        Optimized for high throughput scenarios.
        """
        start_time = time.perf_counter()
        results = {}
        
        try:
            # Process requests in parallel batches
            batch_size = 10
            batches = [
                permission_requests[i:i + batch_size] 
                for i in range(0, len(permission_requests), batch_size)
            ]
            
            for batch in batches:
                tasks = []
                for req in batch:
                    task = self.check_user_permission_optimized(
                        user_id,
                        req['resource_type'],
                        req['resource_id'], 
                        req['permission_type']
                    )
                    tasks.append(task)
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, result in enumerate(batch_results):
                    request_key = f"{batch[i]['resource_type']}:{batch[i]['resource_id']}"
                    
                    if isinstance(result, Exception):
                        results[request_key] = {
                            'access_granted': False,
                            'error': str(result)
                        }
                    else:
                        results[request_key] = result
            
            total_time_ms = (time.perf_counter() - start_time) * 1000
            
            logger.info(f"Batch permission check completed: {len(permission_requests)} requests in {total_time_ms:.1f}ms")
            
            return results
            
        except Exception as e:
            logger.error(f"Batch permission check failed: {e}")
            
            # Return error for all requests
            return {
                f"{req['resource_type']}:{req['resource_id']}": {
                    'access_granted': False,
                    'error': str(e)
                }
                for req in permission_requests
            }
    
    async def get_user_permissions_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive user permissions summary.
        Optimized for admin dashboards and user management.
        """
        start_time = time.perf_counter()
        
        try:
            async with self.pool_manager.get_read_connection() as conn:
                # Get user teams and roles
                user_teams = await conn.fetch("""
                    SELECT t.id, t.name, tm.role, tm.joined_at
                    FROM teams t
                    JOIN team_members tm ON tm.team_id = t.id
                    WHERE tm.user_id = $1 AND tm.is_active = true
                """, user_id)
                
                # Get user projects access
                user_projects = await conn.fetch("""
                    SELECT p.id, p.name, p.visibility, 
                           CASE WHEN p.user_id = $1 THEN 'owner' ELSE 'viewer' END as role
                    FROM projects p
                    WHERE p.user_id = $1 
                    OR p.visibility = 'public'
                    OR (p.visibility = 'team-only' AND EXISTS (
                        SELECT 1 FROM project_teams pt 
                        JOIN team_members tm ON tm.team_id = pt.team_id
                        WHERE pt.project_id = p.id AND tm.user_id = $1 AND tm.is_active = true
                    ))
                    ORDER BY p.created_at DESC
                    LIMIT 50
                """, user_id)
                
                # Get user generations access
                user_generations = await conn.fetch("""
                    SELECT g.id, g.status, g.created_at, p.name as project_name
                    FROM generations g
                    LEFT JOIN projects p ON p.id = g.project_id
                    WHERE g.user_id = $1
                    ORDER BY g.created_at DESC
                    LIMIT 100
                """, user_id)
                
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                
                return {
                    'user_id': user_id,
                    'teams': [dict(team) for team in user_teams],
                    'projects_access': [dict(project) for project in user_projects],
                    'recent_generations': [dict(gen) for gen in user_generations],
                    'summary': {
                        'team_count': len(user_teams),
                        'projects_accessible': len(user_projects),
                        'generations_created': len(user_generations)
                    },
                    'execution_time_ms': execution_time_ms,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to get user permissions summary: {e}")
            return {
                'user_id': user_id,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def validate_media_access(
        self, 
        user_id: str, 
        generation_id: str, 
        media_type: str = 'image'
    ) -> Dict[str, Any]:
        """
        Validate and provide secure media access with URL generation.
        Optimized for high-throughput media serving.
        """
        start_time = time.perf_counter()
        
        try:
            # Check generation access permission
            permission_result = await self.check_user_permission_optimized(
                user_id, 'generation', generation_id, 'read'
            )
            
            if not permission_result['access_granted']:
                return {
                    'access_granted': False,
                    'reason': 'Insufficient permissions',
                    'execution_time_ms': (time.perf_counter() - start_time) * 1000
                }
            
            # Get generation details and media URLs
            async with self.pool_manager.get_read_connection() as conn:
                generation = await conn.fetchrow("""
                    SELECT g.id, g.output_urls, g.status, g.user_id,
                           p.visibility, p.name as project_name
                    FROM generations g
                    LEFT JOIN projects p ON p.id = g.project_id
                    WHERE g.id = $1
                """, generation_id)
                
                if not generation:
                    return {
                        'access_granted': False,
                        'reason': 'Generation not found',
                        'execution_time_ms': (time.perf_counter() - start_time) * 1000
                    }
                
                if generation['status'] != 'completed' or not generation['output_urls']:
                    return {
                        'access_granted': False,
                        'reason': 'Media not available',
                        'execution_time_ms': (time.perf_counter() - start_time) * 1000
                    }
            
            # Generate secure URLs (in production, these would be signed URLs)
            secure_urls = []
            for i, url in enumerate(generation['output_urls']):
                secure_urls.append({
                    'url': url,
                    'media_type': media_type,
                    'index': i,
                    'expires_at': (datetime.now() + timedelta(hours=1)).isoformat()
                })
            
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            return {
                'access_granted': True,
                'generation_id': generation_id,
                'secure_urls': secure_urls,
                'project_name': generation['project_name'],
                'execution_time_ms': execution_time_ms,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Media access validation failed: {e}")
            return {
                'access_granted': False,
                'reason': str(e),
                'execution_time_ms': (time.perf_counter() - start_time) * 1000
            }
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics for the authorization system."""
        try:
            dashboard = await performance_monitor.get_authorization_dashboard()
            
            # Add connection pool metrics
            if self.pool_manager:
                pool_metrics = await self.pool_manager.get_all_metrics()
                dashboard['connection_pools'] = {
                    pool_type.value: {
                        'total_connections': metrics.total_connections,
                        'active_connections': metrics.active_connections,
                        'avg_query_time_ms': metrics.avg_query_time_ms
                    }
                    for pool_type, metrics in pool_metrics.items()
                }
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def invalidate_user_cache(self, user_id: str) -> Dict[str, Any]:
        """Invalidate all cache entries for a specific user."""
        try:
            start_time = time.perf_counter()
            
            # Invalidate authorization cache
            async with self.pool_manager.get_write_connection() as conn:
                deleted_count = await conn.fetchval("""
                    SELECT invalidate_authorization_cache($1, NULL, NULL)
                """, user_id)
            
            # Also invalidate the frontend authorization service cache
            await authorizationService.invalidateUserCache(user_id)
            
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            logger.info(f"Invalidated cache for user {user_id}: {deleted_count} entries")
            
            return {
                'success': True,
                'user_id': user_id,
                'invalidated_entries': deleted_count,
                'execution_time_ms': execution_time_ms,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to invalidate user cache: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def run_performance_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive performance diagnostics."""
        try:
            diagnostics = {
                'timestamp': datetime.now().isoformat(),
                'database_health': {},
                'cache_health': {},
                'connection_pools': {},
                'performance_metrics': {},
                'recommendations': []
            }
            
            # Database health check
            async with self.pool_manager.get_read_connection() as conn:
                # Check database connectivity and performance
                db_start = time.perf_counter()
                db_result = await conn.fetchrow("SELECT 1 as test, NOW() as timestamp")
                db_time_ms = (time.perf_counter() - db_start) * 1000
                
                diagnostics['database_health'] = {
                    'connected': bool(db_result),
                    'response_time_ms': db_time_ms,
                    'timestamp': db_result['timestamp'].isoformat() if db_result else None
                }
                
                # Check authorization cache health
                cache_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_entries,
                        COUNT(*) FILTER (WHERE expires_at > NOW()) as valid_entries,
                        AVG(hit_count) as avg_hit_count
                    FROM authorization_cache
                """)
                
                if cache_stats:
                    diagnostics['cache_health'] = {
                        'total_entries': cache_stats['total_entries'],
                        'valid_entries': cache_stats['valid_entries'],
                        'avg_hit_count': float(cache_stats['avg_hit_count'] or 0)
                    }
                
                # Get recent performance metrics
                perf_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_queries,
                        AVG(execution_time_ms) as avg_time,
                        MAX(execution_time_ms) as max_time,
                        COUNT(*) FILTER (WHERE slow_query_threshold_exceeded) as slow_queries
                    FROM query_performance_metrics
                    WHERE created_at >= NOW() - INTERVAL '1 hour'
                """)
                
                if perf_stats:
                    diagnostics['performance_metrics'] = {
                        'total_queries_last_hour': perf_stats['total_queries'],
                        'avg_response_time_ms': float(perf_stats['avg_time'] or 0),
                        'max_response_time_ms': float(perf_stats['max_time'] or 0),
                        'slow_queries': perf_stats['slow_queries']
                    }
            
            # Connection pool health
            if self.pool_manager:
                pool_metrics = await self.pool_manager.get_all_metrics()
                diagnostics['connection_pools'] = {
                    pool_type.value: {
                        'total_connections': metrics.total_connections,
                        'active_connections': metrics.active_connections,
                        'peak_connections': metrics.peak_connections,
                        'avg_query_time_ms': metrics.avg_query_time_ms,
                        'connection_errors': metrics.connection_errors
                    }
                    for pool_type, metrics in pool_metrics.items()
                }
            
            # Generate recommendations
            recommendations = []
            
            if diagnostics['database_health']['response_time_ms'] > 100:
                recommendations.append("Database response time is high - consider optimizing queries or scaling database")
                
            cache_health = diagnostics.get('cache_health', {})
            if cache_health.get('valid_entries', 0) < cache_health.get('total_entries', 1) * 0.8:
                recommendations.append("High cache expiration rate - consider increasing TTL values")
                
            perf_metrics = diagnostics.get('performance_metrics', {})
            if perf_metrics.get('slow_queries', 0) > perf_metrics.get('total_queries_last_hour', 1) * 0.1:
                recommendations.append("High slow query rate detected - review and optimize database queries")
                
            diagnostics['recommendations'] = recommendations if recommendations else ["System performance is optimal"]
            
            return diagnostics
            
        except Exception as e:
            logger.error(f"Performance diagnostics failed: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def shutdown(self):
        """Graceful shutdown of the authorization service."""
        logger.info("Shutting down optimized authorization service...")
        
        # Stop performance monitoring
        if self.monitoring_enabled:
            await performance_monitor.stop_monitoring()
        
        # Close connection pool
        if self.pool_manager:
            await self.pool_manager.close_all()
        
        logger.info("Optimized authorization service shutdown complete")

# Global optimized authorization service instance
_optimized_auth_service: Optional[OptimizedAuthorizationService] = None

async def get_optimized_authorization_service(database_url: str) -> OptimizedAuthorizationService:
    """Get global optimized authorization service instance."""
    global _optimized_auth_service
    
    if _optimized_auth_service is None:
        _optimized_auth_service = OptimizedAuthorizationService()
        await _optimized_auth_service.initialize(database_url)
    
    return _optimized_auth_service

async def shutdown_optimized_authorization_service():
    """Shutdown global optimized authorization service."""
    global _optimized_auth_service
    
    if _optimized_auth_service:
        await _optimized_auth_service.shutdown()
        _optimized_auth_service = None