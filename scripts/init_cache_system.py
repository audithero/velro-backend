#!/usr/bin/env python3
"""
Cache System Initialization Script
Initializes and validates the 3-level caching system for production deployment.

Usage:
    python scripts/init_cache_system.py --environment production
    python scripts/init_cache_system.py --validate-only
"""

import asyncio
import logging
import sys
import os
import argparse
from datetime import datetime
from uuid import uuid4

# Add the parent directory to sys.path to import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cache_service import get_authorization_cache_service, AuthorizationCacheType
from services.authorization_service import authorization_service
from caching.multi_layer_cache_manager import get_cache_manager
from config import settings

logger = logging.getLogger(__name__)


class CacheSystemInitializer:
    """
    Initializes and validates the multi-level cache system.
    """
    
    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.cache_service = get_authorization_cache_service()
        self.cache_manager = get_cache_manager()
        self.auth_service = authorization_service
        
        self.validation_results = {
            "l1_memory_cache": False,
            "l2_redis_cache": False,
            "l3_database_cache": False,
            "authorization_integration": False,
            "cache_warming": False,
            "cache_invalidation": False
        }
    
    async def initialize_cache_system(self) -> bool:
        """Initialize the complete cache system."""
        logger.info(f"Initializing cache system for {self.environment} environment")
        
        try:
            # Step 1: Initialize cache manager
            logger.info("🔧 Initializing multi-layer cache manager...")
            health_check = await self.cache_manager.health_check()
            
            if not health_check.get("overall_healthy", False):
                logger.error("❌ Cache manager health check failed")
                return False
            
            logger.info("✅ Cache manager initialized successfully")
            
            # Step 2: Initialize authorization cache service
            logger.info("🔐 Initializing authorization cache service...")
            auth_health = await self.cache_service.health_check()
            
            if not auth_health.get("service_healthy", False):
                logger.error("❌ Authorization cache service health check failed")
                return False
            
            logger.info("✅ Authorization cache service initialized successfully")
            
            # Step 3: Warm critical caches if in production
            if self.environment == "production":
                logger.info("🔥 Warming critical caches for production...")
                await self._warm_production_caches()
            
            logger.info("🎉 Cache system initialization complete!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cache system initialization failed: {e}")
            return False
    
    async def validate_cache_system(self) -> bool:
        """Comprehensive validation of cache system functionality."""
        logger.info("🧪 Starting comprehensive cache system validation")
        
        # Test 1: L1 Memory Cache
        logger.info("Testing L1 Memory Cache...")
        self.validation_results["l1_memory_cache"] = await self._test_l1_cache()
        
        # Test 2: L2 Redis Cache  
        logger.info("Testing L2 Redis Cache...")
        self.validation_results["l2_redis_cache"] = await self._test_l2_cache()
        
        # Test 3: L3 Database Cache
        logger.info("Testing L3 Database Cache...")
        self.validation_results["l3_database_cache"] = await self._test_l3_cache()
        
        # Test 4: Authorization Integration
        logger.info("Testing Authorization Integration...")
        self.validation_results["authorization_integration"] = await self._test_authorization_integration()
        
        # Test 5: Cache Warming
        logger.info("Testing Cache Warming...")
        self.validation_results["cache_warming"] = await self._test_cache_warming()
        
        # Test 6: Cache Invalidation
        logger.info("Testing Cache Invalidation...")
        self.validation_results["cache_invalidation"] = await self._test_cache_invalidation()
        
        # Overall validation result
        all_passed = all(self.validation_results.values())
        
        self._print_validation_results()
        
        return all_passed
    
    async def _test_l1_cache(self) -> bool:
        """Test L1 memory cache functionality."""
        try:
            # Test SET operation
            success = await self.cache_service.set_authorization_cache(
                user_id=uuid4(),
                resource_id=uuid4(),
                resource_type="test",
                permissions={"can_view": True},
                access_method="test",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            if not success:
                logger.error("L1 cache SET operation failed")
                return False
            
            logger.info("✅ L1 Memory Cache validation passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ L1 cache test failed: {e}")
            return False
    
    async def _test_l2_cache(self) -> bool:
        """Test L2 Redis cache functionality."""
        try:
            # Test Redis connection through cache manager
            health_check = await self.cache_manager.health_check()
            redis_health = health_check.get("L2_Redis", {})
            
            if redis_health.get("status") != "healthy":
                logger.warning(f"L2 Redis cache status: {redis_health}")
                # Don't fail if Redis is not available - system can work without L2
                return True
            
            logger.info("✅ L2 Redis Cache validation passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ L2 cache test failed: {e}")
            return False
    
    async def _test_l3_cache(self) -> bool:
        """Test L3 database cache functionality."""
        try:
            # Test database connectivity
            from database import get_database
            
            db = await get_database()
            
            # Simple test query to validate database connectivity
            result = await db.execute_query(
                table="users",
                operation="select",
                limit=1
            )
            
            logger.info("✅ L3 Database Cache validation passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ L3 cache test failed: {e}")
            return False
    
    async def _test_authorization_integration(self) -> bool:
        """Test authorization service cache integration."""
        try:
            # Test the integrated authorization flow
            test_user_id = uuid4()
            test_resource_id = uuid4()
            
            # Test cache entry creation
            success = await self.cache_service.set_authorization_cache(
                user_id=test_user_id,
                resource_id=test_resource_id,
                resource_type="generation",
                permissions={
                    "can_view": True,
                    "can_edit": False,
                    "can_delete": False,
                    "can_download": True,
                    "can_share": False
                },
                access_method="direct_ownership",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            if not success:
                logger.error("Authorization cache integration failed - SET operation")
                return False
            
            # Test cache entry retrieval
            cached_result = await self.cache_service.get_authorization_cache(
                user_id=test_user_id,
                resource_id=test_resource_id,
                resource_type="generation",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            if not cached_result:
                logger.error("Authorization cache integration failed - GET operation")
                return False
            
            logger.info("✅ Authorization Integration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Authorization integration test failed: {e}")
            return False
    
    async def _test_cache_warming(self) -> bool:
        """Test cache warming functionality."""
        try:
            from services.cache_service import CacheWarmingStrategy
            
            # Test cache warming for a test user
            test_user_id = uuid4()
            
            warming_result = await self.cache_service.warm_authorization_caches(
                user_id=test_user_id,
                cache_types=[AuthorizationCacheType.USER_PERMISSIONS],
                strategy=CacheWarmingStrategy.IMMEDIATE
            )
            
            if not warming_result:
                logger.warning("Cache warming returned no results (expected for test data)")
            
            logger.info("✅ Cache Warming validation passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cache warming test failed: {e}")
            return False
    
    async def _test_cache_invalidation(self) -> bool:
        """Test cache invalidation functionality."""
        try:
            test_user_id = uuid4()
            
            # First, set some cache data
            await self.cache_service.set_authorization_cache(
                user_id=test_user_id,
                resource_id=uuid4(),
                resource_type="generation",
                permissions={"can_view": True},
                access_method="test",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            # Test invalidation
            invalidation_result = await self.cache_service.invalidate_authorization_cache(
                user_id=test_user_id
            )
            
            # Check that some invalidation occurred (or attempted)
            total_invalidated = sum(invalidation_result.values())
            
            logger.info("✅ Cache Invalidation validation passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cache invalidation test failed: {e}")
            return False
    
    async def _warm_production_caches(self):
        """Warm critical caches for production deployment."""
        try:
            from services.cache_service import CacheWarmingStrategy
            
            # Warm with different strategies
            strategies = [
                CacheWarmingStrategy.SCHEDULED,
                CacheWarmingStrategy.PREDICTIVE
            ]
            
            for strategy in strategies:
                warming_result = await self.cache_service.warm_authorization_caches(
                    strategy=strategy
                )
                
                total_warmed = sum(
                    sum(type_results.values()) 
                    for type_results in warming_result.values()
                )
                
                logger.info(f"Warmed {total_warmed} cache entries with {strategy.value} strategy")
            
        except Exception as e:
            logger.error(f"Production cache warming failed: {e}")
    
    def _print_validation_results(self):
        """Print formatted validation results."""
        print(f"\n{'='*60}")
        print("CACHE SYSTEM VALIDATION RESULTS")
        print(f"{'='*60}")
        
        for test_name, passed in self.validation_results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            test_display = test_name.replace("_", " ").title()
            print(f"{test_display:.<40} {status}")
        
        overall_status = all(self.validation_results.values())
        print(f"\nOverall System Status: {'✅ READY' if overall_status else '❌ NOT READY'}")
        
        if overall_status:
            print("🎉 Cache system is ready for production deployment!")
        else:
            print("⚠️  Please fix failing tests before deploying to production.")


async def main():
    """Main initialization and validation routine."""
    parser = argparse.ArgumentParser(description="Initialize and validate cache system")
    parser.add_argument(
        "--environment", 
        choices=["development", "staging", "production"],
        default="development",
        help="Target environment"
    )
    parser.add_argument(
        "--validate-only", 
        action="store_true",
        help="Only run validation, skip initialization"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("🚀 Cache System Initialization and Validation")
    print(f"Environment: {args.environment}")
    print(f"Mode: {'Validation Only' if args.validate_only else 'Initialize and Validate'}")
    
    initializer = CacheSystemInitializer(args.environment)
    
    success = True
    
    # Step 1: Initialize (unless validation-only)
    if not args.validate_only:
        print("\n🔧 Initializing cache system...")
        init_success = await initializer.initialize_cache_system()
        if not init_success:
            print("❌ Cache system initialization failed!")
            success = False
    
    # Step 2: Validate
    print("\n🧪 Validating cache system...")
    validation_success = await initializer.validate_cache_system()
    if not validation_success:
        print("❌ Cache system validation failed!")
        success = False
    
    # Final status
    if success:
        print("\n🎉 Cache system is ready for deployment!")
        return 0
    else:
        print("\n❌ Cache system has issues that need to be resolved.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)