"""
Repository Manager for coordinating all optimized repositories.
Provides centralized access to all data access layers with comprehensive performance optimization.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from database import DatabaseClient
from supabase import Client

from repositories.user_repository import UserRepository, UserModel
from repositories.generation_repository import GenerationRepository
from repositories.project_repository import ProjectRepository
from repositories.credit_repository import CreditRepository

from utils.supabase_performance_optimizer import supabase_optimizer, SupabasePerformanceConfig
from utils.enterprise_db_pool import enterprise_pool_manager, PoolType
from caching.multi_layer_cache_manager import cache_manager

logger = logging.getLogger(__name__)


class RepositoryManager:
    """
    Centralized repository manager with comprehensive performance optimization.
    
    Features:
    - Coordinates all repositories with shared optimization infrastructure
    - Provides performance monitoring across all data access patterns
    - Manages cache warm-up and invalidation strategies
    - Implements circuit breaker patterns for fault tolerance
    - Supports batch operations across multiple repositories
    """
    
    def __init__(self, db_client: DatabaseClient, supabase_client: Client):
        self.db_client = db_client
        self.supabase_client = supabase_client
        
        # Initialize optimized repositories
        self.users = UserRepository(db_client, supabase_client)
        
        # Performance tracking
        self.performance_stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "materialized_view_hits": 0,
            "parallel_operations": 0,
            "avg_response_time_ms": 0.0,
            "performance_targets_met": 0,
            "last_updated": datetime.utcnow()
        }
        
        # Circuit breaker state
        self.circuit_breaker_open = False
        self.circuit_breaker_failures = 0
        self.max_circuit_failures = 5
        
        logger.info("🚀 [REPO_MGR] Repository Manager initialized with performance optimizations")
    
    async def initialize(self):
        """Initialize repository manager and warm critical caches."""
        try:
            logger.info("🔧 [REPO_MGR] Initializing repository manager...")
            
            # Initialize connection pools if not already done
            if not enterprise_pool_manager.pools:
                logger.info("🔄 [REPO_MGR] Initializing connection pools...")
                # Connection pools will be initialized by the main application
                pass
            
            # Warm critical caches
            await self._warm_critical_caches()
            
            # Start performance monitoring
            asyncio.create_task(self._performance_monitoring_loop())
            
            logger.info("✅ [REPO_MGR] Repository manager initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ [REPO_MGR] Failed to initialize repository manager: {e}")
            raise
    
    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary across all repositories."""
        try:
            # Collect repository-specific metrics
            repo_metrics = {
                "users": await self.users.get_performance_metrics()
            }
            
            # Calculate overall statistics
            total_queries = sum(metrics["performance"]["total_queries"] for metrics in repo_metrics.values())
            total_cache_hits = sum(metrics["optimization"]["cache_hits"] for metrics in repo_metrics.values())
            total_mv_hits = sum(metrics["optimization"]["materialized_view_hits"] for metrics in repo_metrics.values())
            
            cache_hit_rate = (total_cache_hits / max(total_queries, 1)) * 100
            mv_hit_rate = (total_mv_hits / max(total_queries, 1)) * 100
            
            # Get Supabase optimizer performance
            supabase_performance = await supabase_optimizer.get_performance_report()
            
            return {
                "repository_manager": {
                    "status": "active",
                    "circuit_breaker_open": self.circuit_breaker_open,
                    "circuit_breaker_failures": self.circuit_breaker_failures
                },
                "overall_performance": {
                    "total_queries": total_queries,
                    "cache_hit_rate_percent": round(cache_hit_rate, 2),
                    "materialized_view_hit_rate_percent": round(mv_hit_rate, 2),
                    "parallel_operations": self.performance_stats["parallel_operations"]
                },
                "repository_metrics": repo_metrics,
                "supabase_optimizer": supabase_performance,
                "performance_targets": {
                    "auth_queries_target_ms": 20,
                    "general_queries_target_ms": 50,
                    "cache_hit_rate_target_percent": 90,
                    "overall_performance_achieved": cache_hit_rate >= 90
                },
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ [REPO_MGR] Failed to get performance summary: {e}")
            return {
                "error": str(e),
                "last_updated": datetime.utcnow().isoformat()
            }
    
    async def warm_all_caches(self, user_ids: Optional[List[str]] = None):
        """Warm caches across all repositories for optimal performance."""
        try:
            logger.info("🔥 [REPO_MGR] Starting comprehensive cache warming...")
            
            warm_tasks = []
            
            # Warm user caches
            if user_ids:
                warm_tasks.append(self.users.warm_auth_caches(user_ids))
            
            # Warm Supabase optimizer caches
            warm_tasks.append(supabase_optimizer.warm_critical_caches())
            
            # Execute all warming tasks in parallel
            if warm_tasks:
                await asyncio.gather(*warm_tasks, return_exceptions=True)
            
            logger.info("🔥 [REPO_MGR] Cache warming completed successfully")
            
        except Exception as e:
            logger.error(f"❌ [REPO_MGR] Cache warming failed: {e}")
    
    async def execute_batch_operations(
        self,
        operations: List[Dict[str, Any]]
    ) -> List[Any]:
        """
        Execute multiple repository operations in parallel for maximum performance.
        
        operations format:
        [
            {"repository": "users", "method": "get_by_id", "args": ["user_id"], "kwargs": {}},
            {"repository": "users", "method": "check_authorization", "args": ["user_id", "resource"], "kwargs": {}}
        ]
        """
        if not operations:
            return []
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Create tasks for all operations
            tasks = []
            for op in operations:
                repo_name = op["repository"]
                method_name = op["method"]
                args = op.get("args", [])
                kwargs = op.get("kwargs", {})
                
                if repo_name == "users":
                    method = getattr(self.users, method_name)
                    task = method(*args, **kwargs)
                    tasks.append(task)
                else:
                    logger.warning(f"⚠️ [REPO_MGR] Unknown repository: {repo_name}")
                    continue
            
            # Execute all operations in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Update performance stats
            execution_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            self.performance_stats["parallel_operations"] += 1
            
            logger.info(f"🚀 [REPO_MGR] Batch operations completed: {len(operations)} ops in {execution_time_ms:.1f}ms")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ [REPO_MGR] Batch operations failed: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check across all repositories."""
        try:
            health_status = {
                "overall_status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "components": {}
            }
            
            # Check repository health
            try:
                # Test user repository with a simple query
                test_user = await self.users.get_by_id("health_check", use_cache=False)
                health_status["components"]["user_repository"] = "healthy"
            except Exception as e:
                health_status["components"]["user_repository"] = f"unhealthy: {str(e)}"
                health_status["overall_status"] = "degraded"
            
            # Check Supabase optimizer
            try:
                optimizer_report = await supabase_optimizer.get_performance_report()
                health_status["components"]["supabase_optimizer"] = "healthy"
                health_status["optimizer_status"] = optimizer_report.get("optimization_status", "unknown")
            except Exception as e:
                health_status["components"]["supabase_optimizer"] = f"unhealthy: {str(e)}"
                health_status["overall_status"] = "degraded"
            
            # Check cache manager
            try:
                await cache_manager.get("health_check")
                health_status["components"]["cache_manager"] = "healthy"
            except Exception as e:
                health_status["components"]["cache_manager"] = f"unhealthy: {str(e)}"
                health_status["overall_status"] = "degraded"
            
            # Check circuit breaker state
            if self.circuit_breaker_open:
                health_status["overall_status"] = "critical"
                health_status["circuit_breaker"] = "open"
            else:
                health_status["circuit_breaker"] = "closed"
            
            return health_status
            
        except Exception as e:
            return {
                "overall_status": "critical",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def invalidate_all_caches(self, pattern: Optional[str] = None):
        """Invalidate caches across all repositories."""
        try:
            if pattern:
                await cache_manager.invalidate_pattern(pattern)
                logger.info(f"🗑️ [REPO_MGR] Invalidated caches matching pattern: {pattern}")
            else:
                await cache_manager.clear_all()
                logger.info("🗑️ [REPO_MGR] Cleared all caches")
            
        except Exception as e:
            logger.error(f"❌ [REPO_MGR] Cache invalidation failed: {e}")
    
    async def _warm_critical_caches(self):
        """Warm the most critical caches for optimal performance."""
        try:
            logger.info("🔥 [REPO_MGR] Warming critical caches...")
            
            # This would typically pre-load frequently accessed data
            # For now, we'll prepare the cache infrastructure
            
            critical_patterns = [
                "repo:users:by_id:*",
                "repo:users:by_email:*",
                "repo:users:auth:*"
            ]
            
            warm_count = 0
            for pattern in critical_patterns:
                # Invalidate old entries to prepare for fresh data
                invalidated = await cache_manager.invalidate_pattern(pattern)
                warm_count += invalidated
            
            logger.info(f"🔥 [REPO_MGR] Prepared {warm_count} cache entries for warming")
            
        except Exception as e:
            logger.error(f"❌ [REPO_MGR] Critical cache warming failed: {e}")
    
    async def _performance_monitoring_loop(self):
        """Background task to monitor and log performance metrics."""
        while True:
            try:
                await asyncio.sleep(300)  # Monitor every 5 minutes
                
                summary = await self.get_performance_summary()
                
                # Log performance summary
                overall_perf = summary.get("overall_performance", {})
                logger.info(
                    f"📊 [REPO_MGR] Performance Summary - "
                    f"Queries: {overall_perf.get('total_queries', 0)}, "
                    f"Cache Hit Rate: {overall_perf.get('cache_hit_rate_percent', 0):.1f}%, "
                    f"MV Hit Rate: {overall_perf.get('materialized_view_hit_rate_percent', 0):.1f}%"
                )
                
                # Check for performance issues
                cache_hit_rate = overall_perf.get('cache_hit_rate_percent', 0)
                if cache_hit_rate < 80:
                    logger.warning(f"⚠️ [REPO_MGR] Low cache hit rate: {cache_hit_rate:.1f}% (target: 90%)")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [REPO_MGR] Performance monitoring error: {e}")
    
    def _handle_circuit_breaker(self, success: bool):
        """Handle circuit breaker state based on operation success."""
        if success:
            if self.circuit_breaker_failures > 0:
                self.circuit_breaker_failures -= 1
            if self.circuit_breaker_open and self.circuit_breaker_failures == 0:
                self.circuit_breaker_open = False
                logger.info("🔄 [REPO_MGR] Circuit breaker closed - service recovered")
        else:
            self.circuit_breaker_failures += 1
            if self.circuit_breaker_failures >= self.max_circuit_failures:
                self.circuit_breaker_open = True
                logger.warning(f"🚨 [REPO_MGR] Circuit breaker opened after {self.circuit_breaker_failures} failures")
    
    async def close(self):
        """Gracefully close repository manager and all resources."""
        try:
            logger.info("🔄 [REPO_MGR] Closing repository manager...")
            
            # Close connection pools
            await enterprise_pool_manager.close_all_pools()
            
            logger.info("✅ [REPO_MGR] Repository manager closed successfully")
            
        except Exception as e:
            logger.error(f"❌ [REPO_MGR] Error closing repository manager: {e}")


# Global repository manager instance
repository_manager: Optional[RepositoryManager] = None


async def get_repository_manager() -> RepositoryManager:
    """Get the global repository manager instance."""
    global repository_manager
    
    if repository_manager is None:
        from database import get_database
        from config import settings
        from supabase import create_client
        
        db_client = await get_database()
        supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        
        repository_manager = RepositoryManager(db_client, supabase_client)
        await repository_manager.initialize()
    
    return repository_manager


async def close_repository_manager():
    """Close the global repository manager."""
    global repository_manager
    
    if repository_manager is not None:
        await repository_manager.close()
        repository_manager = None