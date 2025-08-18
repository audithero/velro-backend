#!/usr/bin/env python3
"""
Initialize Optimized Cache System for Velro Authorization

This script sets up and initializes the high-performance L1 memory cache
system for the Velro authorization service to achieve <5ms access times
and >95% cache hit rates.

Usage:
    python scripts/initialize_optimized_cache_system.py [--config production|development]
"""

import asyncio
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.optimized_cache_manager import (
    OptimizedCacheManager, 
    OptimizedCacheConfig,
    start_cache_manager,
    get_cache_manager
)
from services.authorization_service import authorization_service
from database import get_database

logger = logging.getLogger(__name__)


def get_production_cache_config() -> OptimizedCacheConfig:
    """Get production-optimized cache configuration."""
    return OptimizedCacheConfig(
        # Memory configuration for production
        max_size_mb=256,  # 256MB for production workloads
        max_entries=50000,  # Support up to 50k cached authorization entries
        
        # Aggressive performance targets
        target_access_time_ms=3.0,  # <3ms for production
        target_hit_rate_percent=97.0,  # >97% hit rate target
        
        # TTL configuration optimized for authorization patterns
        default_ttl_seconds=300,  # 5 minutes default
        max_ttl_seconds=1800,     # 30 minutes maximum
        auth_ttl_seconds=600,     # 10 minutes for auth data
        uuid_validation_ttl_seconds=3600,  # 1 hour for UUID validation
        
        # Eviction and cleanup for high-load production
        cleanup_interval_seconds=30,  # Cleanup every 30 seconds
        eviction_batch_size=200,     # Larger batches for efficiency
        
        # Memory optimization enabled
        compression_enabled=True,
        compression_threshold_bytes=512,  # Compress entries >512 bytes
        
        # Cache warming enabled for production
        warming_enabled=True,
        warming_batch_size=100,
        preload_auth_data=True
    )


def get_development_cache_config() -> OptimizedCacheConfig:
    """Get development-friendly cache configuration."""
    return OptimizedCacheConfig(
        # Smaller memory footprint for development
        max_size_mb=64,    # 64MB for development
        max_entries=10000, # 10k entries for development
        
        # Relaxed performance targets
        target_access_time_ms=5.0,   # <5ms for development
        target_hit_rate_percent=95.0, # >95% hit rate target
        
        # TTL configuration
        default_ttl_seconds=180,     # 3 minutes default
        max_ttl_seconds=900,         # 15 minutes maximum
        auth_ttl_seconds=300,        # 5 minutes for auth data
        uuid_validation_ttl_seconds=1800,  # 30 minutes for UUID validation
        
        # More frequent cleanup for development debugging
        cleanup_interval_seconds=60,  # Cleanup every minute
        eviction_batch_size=50,       # Smaller batches
        
        # Compression disabled for easier debugging
        compression_enabled=False,
        
        # Cache warming disabled for faster startup
        warming_enabled=False,
        preload_auth_data=False
    )


async def validate_database_connection():
    """Validate database connection is available."""
    try:
        db = await get_database()
        test_result = await db.execute_query(
            table="users",
            operation="select",
            filters={},
            limit=1,
            use_service_key=True
        )
        logger.info("✅ Database connection validated")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


async def warm_authorization_cache(cache_manager: OptimizedCacheManager, sample_size: int = 100):
    """Warm the authorization cache with frequently accessed data."""
    try:
        db = await get_database()
        
        logger.info(f"🔥 Starting cache warming with {sample_size} samples...")
        
        # Get active users for cache warming
        active_users = await db.execute_query(
            table="users",
            operation="select",
            filters={
                "is_active": True,
                "last_active_at__gte": "now() - interval '24 hours'"
            },
            fields=["id", "email", "created_at"],
            limit=sample_size,
            order_by="last_active_at DESC",
            use_service_key=True
        )
        
        warmed_profiles = 0
        warmed_generations = 0
        warmed_validations = 0
        
        for user in active_users:
            user_id = user['id']
            
            # Warm user profile data
            try:
                cache_manager.set_user_profile(
                    user_id,
                    {
                        'id': user_id,
                        'email': user['email'],
                        'is_active': True,
                        'created_at': user['created_at'],
                        'cached_at': datetime.utcnow().isoformat()
                    },
                    ttl=cache_manager.config.auth_ttl_seconds
                )
                warmed_profiles += 1
                
            except Exception as e:
                logger.debug(f"Failed to warm profile for user {user_id}: {e}")
            
            # Warm recent generations for this user
            try:
                recent_generations = await db.execute_query(
                    table="generations",
                    operation="select",
                    filters={
                        "user_id": user_id,
                        "status": "completed",
                        "created_at__gte": "now() - interval '7 days'"
                    },
                    fields=["id", "user_id", "status", "created_at"],
                    limit=5,
                    order_by="created_at DESC",
                    use_service_key=True
                )
                
                for gen in recent_generations:
                    gen_id = gen['id']
                    
                    # Cache generation access permissions (owner has full access)
                    permissions_data = {
                        'user_id': user_id,
                        'generation_id': gen_id,
                        'granted': True,
                        'can_view': True,
                        'can_edit': True,
                        'can_delete': True,
                        'can_download': True,
                        'can_share': True,
                        'access_method': 'DIRECT_OWNERSHIP',
                        'security_level': 'AUTHENTICATED',
                        'cached_at': datetime.utcnow().isoformat()
                    }
                    
                    cache_manager.set_generation_access(
                        gen_id, 
                        user_id, 
                        permissions_data,
                        ttl=cache_manager.config.auth_ttl_seconds
                    )
                    warmed_generations += 1
                    
                    # Warm UUID validation for this generation
                    cache_manager.set_uuid_validation(
                        gen_id,
                        'GENERATION_ACCESS', 
                        gen_id  # Validated UUID
                    )
                    warmed_validations += 1
                    
            except Exception as e:
                logger.debug(f"Failed to warm generations for user {user_id}: {e}")
        
        logger.info(f"✅ Cache warming completed:")
        logger.info(f"   📄 User profiles warmed: {warmed_profiles}")
        logger.info(f"   🎨 Generation permissions warmed: {warmed_generations}")
        logger.info(f"   🔍 UUID validations warmed: {warmed_validations}")
        
        return {
            'profiles_warmed': warmed_profiles,
            'generations_warmed': warmed_generations,
            'validations_warmed': warmed_validations
        }
        
    except Exception as e:
        logger.error(f"❌ Cache warming failed: {e}")
        return {
            'profiles_warmed': 0,
            'generations_warmed': 0,
            'validations_warmed': 0
        }


async def run_cache_performance_test(cache_manager: OptimizedCacheManager, iterations: int = 1000):
    """Run performance test to validate cache performance targets."""
    logger.info(f"🧪 Running cache performance test with {iterations} iterations...")
    
    # Test data
    test_user_id = "test-user-12345"
    test_gen_id = "test-gen-67890"
    test_uuid = "550e8400-e29b-41d4-a716-446655440000"
    
    test_profile = {
        'id': test_user_id,
        'email': 'test@example.com',
        'is_active': True,
        'test_data': True
    }
    
    test_permissions = {
        'user_id': test_user_id,
        'generation_id': test_gen_id,
        'granted': True,
        'can_view': True,
        'can_edit': False,
        'access_method': 'PUBLIC_ACCESS'
    }
    
    # Warm up the cache
    cache_manager.set_user_profile(test_user_id, test_profile)
    cache_manager.set_generation_access(test_gen_id, test_user_id, test_permissions)
    cache_manager.set_uuid_validation(test_uuid, 'GENERATION_ACCESS', test_uuid)
    
    # Performance test
    import time
    total_time = 0
    successful_operations = 0
    cache_hits = 0
    
    for i in range(iterations):
        start_time = time.time()
        
        try:
            # Test user profile access
            profile_result, profile_hit = cache_manager.get_user_profile(test_user_id)
            
            # Test generation access
            gen_result, gen_hit = cache_manager.get_generation_access(test_gen_id, test_user_id)
            
            # Test UUID validation
            uuid_result, uuid_hit = cache_manager.get_uuid_validation(test_uuid, 'GENERATION_ACCESS')
            
            operation_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            total_time += operation_time
            
            if profile_result and gen_result and uuid_result:
                successful_operations += 1
            
            if profile_hit and gen_hit and uuid_hit:
                cache_hits += 1
                
        except Exception as e:
            logger.debug(f"Performance test iteration {i} failed: {e}")
    
    # Calculate metrics
    avg_response_time = total_time / iterations if iterations > 0 else 0
    success_rate = (successful_operations / iterations) * 100 if iterations > 0 else 0
    cache_hit_rate = (cache_hits / iterations) * 100 if iterations > 0 else 0
    
    # Get cache statistics
    cache_stats = cache_manager.get_stats()
    
    logger.info("📊 Performance Test Results:")
    logger.info(f"   ⏱️  Average response time: {avg_response_time:.2f}ms (target: <{cache_manager.config.target_access_time_ms}ms)")
    logger.info(f"   🎯 Cache hit rate: {cache_hit_rate:.1f}% (target: >{cache_manager.config.target_hit_rate_percent}%)")
    logger.info(f"   ✅ Success rate: {success_rate:.1f}%")
    logger.info(f"   🗃️  Cache entries: {cache_stats['total_entries']}")
    logger.info(f"   💾 Cache size: {cache_stats['total_size_mb']:.2f}MB")
    
    # Performance target validation
    meets_response_time = avg_response_time <= cache_manager.config.target_access_time_ms
    meets_hit_rate = cache_hit_rate >= cache_manager.config.target_hit_rate_percent
    
    if meets_response_time and meets_hit_rate:
        logger.info("🎉 All performance targets met!")
    else:
        if not meets_response_time:
            logger.warning(f"⚠️  Response time target missed: {avg_response_time:.2f}ms > {cache_manager.config.target_access_time_ms}ms")
        if not meets_hit_rate:
            logger.warning(f"⚠️  Hit rate target missed: {cache_hit_rate:.1f}% < {cache_manager.config.target_hit_rate_percent}%")
    
    return {
        'avg_response_time_ms': avg_response_time,
        'cache_hit_rate_percent': cache_hit_rate,
        'success_rate_percent': success_rate,
        'meets_targets': meets_response_time and meets_hit_rate,
        'cache_stats': cache_stats
    }


async def initialize_optimized_cache_system(config_type: str = 'development'):
    """Initialize the complete optimized cache system."""
    logger.info(f"🚀 Initializing Optimized Cache System ({config_type} configuration)")
    
    # Step 1: Validate database connection
    if not await validate_database_connection():
        logger.error("❌ Cannot proceed without database connection")
        return False
    
    # Step 2: Get appropriate configuration
    if config_type == 'production':
        cache_config = get_production_cache_config()
    else:
        cache_config = get_development_cache_config()
    
    logger.info(f"📋 Cache Configuration:")
    logger.info(f"   💾 Max memory: {cache_config.max_size_mb}MB")
    logger.info(f"   📦 Max entries: {cache_config.max_entries:,}")
    logger.info(f"   ⏱️  Target access time: <{cache_config.target_access_time_ms}ms")
    logger.info(f"   🎯 Target hit rate: >{cache_config.target_hit_rate_percent}%")
    logger.info(f"   🔥 Cache warming: {'enabled' if cache_config.warming_enabled else 'disabled'}")
    
    # Step 3: Initialize cache manager
    try:
        cache_manager = await start_cache_manager(cache_config)
        logger.info("✅ Cache manager initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize cache manager: {e}")
        return False
    
    # Step 4: Warm cache if enabled
    warming_results = {'profiles_warmed': 0, 'generations_warmed': 0, 'validations_warmed': 0}
    if cache_config.warming_enabled:
        warming_results = await warm_authorization_cache(
            cache_manager, 
            sample_size=cache_config.warming_batch_size
        )
    
    # Step 5: Run performance test
    test_results = await run_cache_performance_test(cache_manager, iterations=500)
    
    # Step 6: Display final status
    logger.info("=" * 60)
    logger.info("🎉 OPTIMIZED CACHE SYSTEM INITIALIZATION COMPLETE")
    logger.info("=" * 60)
    
    logger.info("📈 System Status:")
    logger.info(f"   🎯 Performance targets met: {'✅ YES' if test_results['meets_targets'] else '❌ NO'}")
    logger.info(f"   ⏱️  Average response time: {test_results['avg_response_time_ms']:.2f}ms")
    logger.info(f"   📊 Cache hit rate: {test_results['cache_hit_rate_percent']:.1f}%")
    logger.info(f"   💾 Cache memory usage: {test_results['cache_stats']['total_size_mb']:.2f}MB")
    
    if cache_config.warming_enabled:
        logger.info("🔥 Cache Warming Results:")
        logger.info(f"   👤 User profiles: {warming_results['profiles_warmed']}")
        logger.info(f"   🎨 Generation permissions: {warming_results['generations_warmed']}")
        logger.info(f"   🔍 UUID validations: {warming_results['validations_warmed']}")
    
    logger.info("🔧 Integration Notes:")
    logger.info("   • Import: from utils.optimized_cache_manager import get_cache_manager")
    logger.info("   • Usage: cache_manager = get_cache_manager()")
    logger.info("   • Methods: get_user_profile(), get_generation_access(), set_*(), etc.")
    logger.info("   • Monitoring: cache_manager.get_stats() for performance metrics")
    
    return True


async def main():
    """Main entry point for cache system initialization."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Initialize Velro Optimized Cache System')
    parser.add_argument(
        '--config',
        choices=['production', 'development'],
        default='development',
        help='Cache configuration profile to use'
    )
    parser.add_argument(
        '--test-only',
        action='store_true',
        help='Run performance test only (skip initialization)'
    )
    
    args = parser.parse_args()
    
    try:
        if args.test_only:
            # Just run performance test with existing cache
            cache_manager = get_cache_manager()
            await cache_manager.start()
            await run_cache_performance_test(cache_manager)
        else:
            # Full initialization
            success = await initialize_optimized_cache_system(args.config)
            if not success:
                sys.exit(1)
        
        logger.info("🎉 Cache system ready for high-performance authorization operations!")
        
    except KeyboardInterrupt:
        logger.info("🛑 Initialization interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())