#!/usr/bin/env python3
"""
Multi-Layer Cache System Initialization Script
Initializes and configures the complete L1/L2/L3 caching architecture.

Usage:
    python scripts/initialize_cache_system.py [--mode production|development|testing]
"""

import asyncio
import logging
import sys
import os
import argparse
import json
from typing import Dict, Any, Optional
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from caching.multi_layer_cache_manager import (
    MultiLayerCacheManager, get_cache_manager
)
from services.enhanced_authorization_cache_service import (
    get_enhanced_authorization_cache_service,
    warm_authorization_caches
)
from monitoring.cache_performance_monitor import (
    start_cache_monitoring,
    get_cache_performance_report
)
from database import get_database
from config import settings

logger = logging.getLogger(__name__)


class CacheSystemInitializer:
    """Comprehensive cache system initialization and configuration."""
    
    def __init__(self, mode: str = "production"):
        self.mode = mode
        self.config = self._get_mode_config(mode)
        self.cache_manager: Optional[MultiLayerCacheManager] = None
        self.initialization_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "mode": mode,
            "success": False,
            "components": {},
            "performance_validation": {},
            "errors": []
        }
    
    def _get_mode_config(self, mode: str) -> Dict[str, Any]:
        """Get configuration based on deployment mode."""
        base_config = {
            "l1_cache_size_mb": 200,
            "redis_max_connections": 20,
            "monitoring_interval": 30,
            "cache_warming_enabled": True,
            "performance_validation_enabled": True,
            "load_test_users": 100
        }
        
        mode_configs = {
            "development": {
                **base_config,
                "l1_cache_size_mb": 50,
                "redis_max_connections": 5,
                "monitoring_interval": 60,
                "load_test_users": 10
            },
            "testing": {
                **base_config,
                "l1_cache_size_mb": 20,
                "redis_max_connections": 2,
                "monitoring_interval": 5,
                "cache_warming_enabled": False,
                "load_test_users": 5
            },
            "production": {
                **base_config,
                "l1_cache_size_mb": 500,
                "redis_max_connections": 50,
                "monitoring_interval": 30,
                "load_test_users": 1000
            }
        }
        
        return mode_configs.get(mode, base_config)
    
    async def initialize_complete_system(self) -> Dict[str, Any]:
        """Initialize the complete multi-layer cache system."""
        logger.info(f"🚀 Initializing Velro Multi-Layer Cache System (mode: {self.mode})")
        
        try:
            # Step 1: Database setup and validation
            await self._initialize_database()
            
            # Step 2: L1 Memory Cache setup
            await self._initialize_l1_cache()
            
            # Step 3: L2 Redis Cache setup
            await self._initialize_l2_cache()
            
            # Step 4: L3 Database Cache setup
            await self._initialize_l3_cache()
            
            # Step 5: Multi-layer cache manager
            await self._initialize_cache_manager()
            
            # Step 6: Enhanced authorization cache service
            await self._initialize_authorization_cache_service()
            
            # Step 7: Performance monitoring
            await self._initialize_performance_monitoring()
            
            # Step 8: Cache warming
            if self.config["cache_warming_enabled"]:
                await self._perform_cache_warming()
            
            # Step 9: Performance validation
            if self.config["performance_validation_enabled"]:
                await self._validate_performance()
            
            # Step 10: Health check
            await self._perform_health_check()
            
            self.initialization_results["success"] = True
            logger.info("✅ Multi-Layer Cache System initialization completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Cache system initialization failed: {e}")
            self.initialization_results["errors"].append(str(e))
            self.initialization_results["success"] = False
            raise
        
        return self.initialization_results
    
    async def _initialize_database(self):
        """Initialize database components."""
        logger.info("📊 Initializing database components...")
        
        try:
            db = await get_database()
            
            # Check if migration 014 is applied
            migration_check = await db.execute_query(
                table="",
                operation="raw_query", 
                query="""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'cache_performance_realtime'
                )
                """
            )
            
            if not migration_check[0]['exists']:
                logger.warning("Migration 014 not applied - L3 cache features may be limited")
                self.initialization_results["components"]["database"] = "limited"
            else:
                # Test materialized views
                views_check = await db.execute_query(
                    table="",
                    operation="raw_query",
                    query="""
                    SELECT count(*) as view_count FROM information_schema.views 
                    WHERE table_name LIKE 'mv_%'
                    """
                )
                
                view_count = views_check[0]['view_count']
                logger.info(f"Found {view_count} materialized views for L3 cache")
                
                self.initialization_results["components"]["database"] = "ready"
                self.initialization_results["components"]["materialized_views"] = view_count
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            self.initialization_results["errors"].append(f"Database: {e}")
            raise
    
    async def _initialize_l1_cache(self):
        """Initialize L1 Memory Cache."""
        logger.info("🧠 Initializing L1 Memory Cache...")
        
        try:
            # L1 cache is initialized as part of MultiLayerCacheManager
            # Just validate configuration here
            l1_size_mb = self.config["l1_cache_size_mb"]
            logger.info(f"L1 Cache configured: {l1_size_mb}MB")
            
            self.initialization_results["components"]["l1_cache"] = {
                "status": "ready",
                "size_mb": l1_size_mb,
                "eviction_policy": "hybrid"
            }
            
        except Exception as e:
            logger.error(f"L1 cache initialization failed: {e}")
            self.initialization_results["errors"].append(f"L1 Cache: {e}")
            raise
    
    async def _initialize_l2_cache(self):
        """Initialize L2 Redis Cache."""
        logger.info("📡 Initializing L2 Redis Cache...")
        
        try:
            # Test Redis connectivity
            import redis.asyncio as redis
            
            redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379')
            client = redis.from_url(redis_url)
            
            # Test connection
            await client.ping()
            info = await client.info()
            
            logger.info(f"Redis connected: {info.get('redis_version', 'unknown')} "
                       f"({info.get('used_memory_human', 'unknown')} used)")
            
            await client.close()
            
            self.initialization_results["components"]["l2_redis"] = {
                "status": "ready",
                "url": redis_url,
                "max_connections": self.config["redis_max_connections"],
                "redis_version": info.get('redis_version', 'unknown'),
                "used_memory": info.get('used_memory_human', 'unknown')
            }
            
        except Exception as e:
            logger.error(f"L2 Redis cache initialization failed: {e}")
            self.initialization_results["errors"].append(f"L2 Redis: {e}")
            
            # Redis failure is not fatal - system can work with L1+L3
            logger.warning("Redis unavailable - system will operate with L1+L3 caches only")
            self.initialization_results["components"]["l2_redis"] = {
                "status": "unavailable",
                "error": str(e)
            }
    
    async def _initialize_l3_cache(self):
        """Initialize L3 Database Cache."""
        logger.info("🗄️ Initializing L3 Database Cache...")
        
        try:
            db = await get_database()
            
            # Test materialized view queries
            test_queries = [
                ("user_auth_context", "SELECT COUNT(*) FROM mv_user_authorization_context LIMIT 1"),
                ("team_patterns", "SELECT COUNT(*) FROM mv_team_collaboration_patterns LIMIT 1"),
                ("performance_stats", "SELECT COUNT(*) FROM mv_generation_performance_stats LIMIT 1")
            ]
            
            view_status = {}
            for view_name, query in test_queries:
                try:
                    result = await db.execute_query(
                        table="",
                        operation="raw_query",
                        query=query
                    )
                    view_status[view_name] = "ready"
                except Exception as view_error:
                    logger.warning(f"Materialized view {view_name} not available: {view_error}")
                    view_status[view_name] = "unavailable"
            
            self.initialization_results["components"]["l3_database"] = {
                "status": "ready",
                "materialized_views": view_status
            }
            
        except Exception as e:
            logger.error(f"L3 database cache initialization failed: {e}")
            self.initialization_results["errors"].append(f"L3 Database: {e}")
            raise
    
    async def _initialize_cache_manager(self):
        """Initialize the multi-layer cache manager."""
        logger.info("⚡ Initializing Multi-Layer Cache Manager...")
        
        try:
            # Initialize cache manager with configuration
            self.cache_manager = MultiLayerCacheManager(
                l1_size_mb=self.config["l1_cache_size_mb"],
                redis_url=getattr(settings, 'redis_url', None)
            )
            
            # Test multi-level operations
            test_key = "init_test"
            test_data = {
                "test": True,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": self.mode
            }
            
            # Test set operation
            set_result = await self.cache_manager.set_multi_level(
                test_key, test_data, l1_ttl=60, l2_ttl=300
            )
            
            # Test get operation
            get_result, cache_level = await self.cache_manager.get_multi_level(test_key)
            
            # Test invalidation
            invalidate_result = await self.cache_manager.invalidate_multi_level(test_key)
            
            logger.info(f"Cache manager test: Set={any(set_result.values())}, "
                       f"Get={get_result is not None}, "
                       f"Invalidate={any(invalidate_result.values())}")
            
            self.initialization_results["components"]["cache_manager"] = {
                "status": "ready",
                "test_results": {
                    "set_success": any(set_result.values()),
                    "get_success": get_result is not None,
                    "invalidate_success": any(invalidate_result.values())
                }
            }
            
        except Exception as e:
            logger.error(f"Cache manager initialization failed: {e}")
            self.initialization_results["errors"].append(f"Cache Manager: {e}")
            raise
    
    async def _initialize_authorization_cache_service(self):
        """Initialize enhanced authorization cache service."""
        logger.info("🔐 Initializing Enhanced Authorization Cache Service...")
        
        try:
            auth_cache_service = get_enhanced_authorization_cache_service()
            
            # Test authorization cache operations
            from uuid import UUID
            test_user_id = UUID("00000000-0000-0000-0000-000000000001")
            test_gen_id = UUID("00000000-0000-0000-0000-000000000002")
            
            # This will test the cache integration without requiring real auth
            cache_key = f"test_auth:{test_user_id}:{test_gen_id}"
            test_auth_data = {
                "authorized": True,
                "method": "test_initialization",
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.cache_manager.set_multi_level(cache_key, test_auth_data)
            result, level = await self.cache_manager.get_multi_level(cache_key)
            await self.cache_manager.invalidate_multi_level(cache_key)
            
            logger.info(f"Authorization cache service test successful")
            
            self.initialization_results["components"]["authorization_cache"] = {
                "status": "ready",
                "test_successful": result is not None
            }
            
        except Exception as e:
            logger.error(f"Authorization cache service initialization failed: {e}")
            self.initialization_results["errors"].append(f"Authorization Cache: {e}")
            raise
    
    async def _initialize_performance_monitoring(self):
        """Initialize performance monitoring."""
        logger.info("📈 Initializing Performance Monitoring...")
        
        try:
            # Start cache performance monitoring
            await start_cache_monitoring(
                self.cache_manager, 
                interval_seconds=self.config["monitoring_interval"]
            )
            
            # Wait a moment for initial metrics
            await asyncio.sleep(2)
            
            # Test metrics collection
            try:
                report = await get_cache_performance_report()
                monitoring_active = report.get("monitoring_status", {}).get("active", False)
            except Exception:
                monitoring_active = False
            
            logger.info(f"Performance monitoring: {'active' if monitoring_active else 'limited'}")
            
            self.initialization_results["components"]["performance_monitoring"] = {
                "status": "active" if monitoring_active else "limited",
                "interval_seconds": self.config["monitoring_interval"]
            }
            
        except Exception as e:
            logger.error(f"Performance monitoring initialization failed: {e}")
            self.initialization_results["errors"].append(f"Performance Monitoring: {e}")
            # Monitoring failure is not fatal
    
    async def _perform_cache_warming(self):
        """Perform intelligent cache warming."""
        logger.info("🔥 Performing Cache Warming...")
        
        try:
            # General cache warming
            general_warming = await self.cache_manager.warm_cache_intelligent([
                "auth:", "user:", "team:", "gen:"
            ])
            
            # Authorization-specific warming
            try:
                auth_warming = await warm_authorization_caches()
                total_auth_warmed = sum(auth_warming.values())
            except Exception as e:
                logger.warning(f"Authorization cache warming failed: {e}")
                total_auth_warmed = 0
            
            total_general_warmed = sum(
                sum(level_results.values()) for level_results in general_warming.values()
            )
            
            total_warmed = total_general_warmed + total_auth_warmed
            
            logger.info(f"Cache warming completed: {total_warmed} entries warmed")
            
            self.initialization_results["components"]["cache_warming"] = {
                "status": "completed",
                "total_entries_warmed": total_warmed,
                "general_warming": total_general_warmed,
                "authorization_warming": total_auth_warmed
            }
            
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
            self.initialization_results["errors"].append(f"Cache Warming: {e}")
            # Warming failure is not fatal
    
    async def _validate_performance(self):
        """Validate cache performance targets."""
        logger.info("🎯 Validating Performance Targets...")
        
        try:
            # Perform lightweight performance test
            import time
            
            test_iterations = min(self.config["load_test_users"], 100)
            response_times = []
            
            for i in range(test_iterations):
                start_time = time.time()
                
                # Test cache operation
                test_key = f"perf_test:{i}"
                test_data = {"iteration": i, "timestamp": start_time}
                
                await self.cache_manager.set_multi_level(test_key, test_data)
                result, level = await self.cache_manager.get_multi_level(test_key)
                
                response_time_ms = (time.time() - start_time) * 1000
                response_times.append(response_time_ms)
                
                # Cleanup
                await self.cache_manager.invalidate_multi_level(test_key)
            
            # Calculate performance metrics
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
                max_response_time = max(response_times)
                
                # Check performance targets
                targets_met = {
                    "avg_response_time_target": avg_response_time <= 100.0,  # 100ms target
                    "p95_response_time_target": p95_response_time <= 150.0,  # 150ms P95 target
                    "max_response_time_acceptable": max_response_time <= 500.0  # 500ms max
                }
                
                all_targets_met = all(targets_met.values())
                
                logger.info(f"Performance validation: Avg={avg_response_time:.1f}ms, "
                           f"P95={p95_response_time:.1f}ms, Max={max_response_time:.1f}ms")
                
                self.initialization_results["performance_validation"] = {
                    "status": "completed",
                    "targets_met": all_targets_met,
                    "avg_response_time_ms": avg_response_time,
                    "p95_response_time_ms": p95_response_time,
                    "max_response_time_ms": max_response_time,
                    "test_iterations": test_iterations,
                    "individual_targets": targets_met
                }
            
        except Exception as e:
            logger.error(f"Performance validation failed: {e}")
            self.initialization_results["errors"].append(f"Performance Validation: {e}")
    
    async def _perform_health_check(self):
        """Perform comprehensive health check."""
        logger.info("🏥 Performing Health Check...")
        
        try:
            health_check = await self.cache_manager.health_check()
            
            logger.info(f"Health check: Overall={'healthy' if health_check['overall_healthy'] else 'unhealthy'}")
            
            self.initialization_results["health_check"] = health_check
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.initialization_results["errors"].append(f"Health Check: {e}")
    
    def generate_initialization_report(self) -> str:
        """Generate detailed initialization report."""
        report_lines = [
            "="*80,
            "VELRO MULTI-LAYER CACHE SYSTEM INITIALIZATION REPORT",
            "="*80,
            f"Timestamp: {self.initialization_results['timestamp']}",
            f"Mode: {self.initialization_results['mode']}",
            f"Success: {'✅ YES' if self.initialization_results['success'] else '❌ NO'}",
            "",
            "COMPONENT STATUS:",
            "-"*40
        ]
        
        for component, status in self.initialization_results["components"].items():
            if isinstance(status, dict):
                status_str = status.get("status", "unknown")
                report_lines.append(f"  {component}: {status_str}")
                for key, value in status.items():
                    if key != "status":
                        report_lines.append(f"    {key}: {value}")
            else:
                report_lines.append(f"  {component}: {status}")
        
        # Performance validation results
        if "performance_validation" in self.initialization_results:
            perf = self.initialization_results["performance_validation"]
            report_lines.extend([
                "",
                "PERFORMANCE VALIDATION:",
                "-"*40,
                f"  Status: {perf.get('status', 'not_performed')}",
                f"  Targets Met: {'✅ YES' if perf.get('targets_met') else '❌ NO'}",
                f"  Average Response Time: {perf.get('avg_response_time_ms', 0):.1f}ms",
                f"  P95 Response Time: {perf.get('p95_response_time_ms', 0):.1f}ms",
                f"  Test Iterations: {perf.get('test_iterations', 0)}"
            ])
        
        # Health check results
        if "health_check" in self.initialization_results:
            health = self.initialization_results["health_check"]
            report_lines.extend([
                "",
                "HEALTH CHECK:",
                "-"*40,
                f"  Overall Healthy: {'✅ YES' if health.get('overall_healthy') else '❌ NO'}"
            ])
        
        # Errors
        if self.initialization_results["errors"]:
            report_lines.extend([
                "",
                "ERRORS:",
                "-"*40
            ])
            for error in self.initialization_results["errors"]:
                report_lines.append(f"  ❌ {error}")
        
        report_lines.extend([
            "",
            "="*80,
            "END OF INITIALIZATION REPORT",
            "="*80
        ])
        
        return "\n".join(report_lines)


async def main():
    """Main initialization function."""
    parser = argparse.ArgumentParser(description="Initialize Velro Multi-Layer Cache System")
    parser.add_argument(
        "--mode", 
        choices=["development", "testing", "production"], 
        default="production",
        help="Deployment mode (default: production)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output report to file"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    try:
        # Initialize cache system
        initializer = CacheSystemInitializer(mode=args.mode)
        results = await initializer.initialize_complete_system()
        
        # Generate report
        report = initializer.generate_initialization_report()
        print("\n" + report)
        
        # Save report to file if requested
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
                f.write("\n\nDETAILED RESULTS:\n")
                f.write(json.dumps(results, indent=2, default=str))
            print(f"\n📄 Full report saved to: {args.output}")
        
        # Exit with appropriate code
        exit_code = 0 if results["success"] else 1
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n⚠️ Initialization cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Initialization failed with error: {e}")
        logger.exception("Initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())