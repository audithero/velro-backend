"""
Redis health check endpoints for monitoring and debugging.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import time
import asyncio

from utils.redis_connection_test import test_redis_connection
from caching.redis_cache import get_authorization_cache, get_user_session_cache, get_permission_cache
from config import settings

router = APIRouter(prefix="/api/v1/redis", tags=["Redis Health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def redis_health_check() -> Dict[str, Any]:
    """Comprehensive Redis health check."""
    try:
        logger.info("🔍 [REDIS-HEALTH] Starting Redis health check")
        
        # Test Redis connection using our test utility
        connection_test = await asyncio.get_event_loop().run_in_executor(
            None, test_redis_connection, settings.redis_url
        )
        
        # Test cache instances
        cache_tests = {}
        
        # Test authorization cache
        try:
            auth_cache = get_authorization_cache()
            auth_health = await asyncio.get_event_loop().run_in_executor(
                None, auth_cache.health_check
            )
            cache_tests["authorization_cache"] = auth_health
        except Exception as e:
            cache_tests["authorization_cache"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Test user session cache
        try:
            session_cache = get_user_session_cache()
            session_health = await asyncio.get_event_loop().run_in_executor(
                None, session_cache.health_check
            )
            cache_tests["user_session_cache"] = session_health
        except Exception as e:
            cache_tests["user_session_cache"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Test permission cache
        try:
            perm_cache = get_permission_cache()
            perm_health = await asyncio.get_event_loop().run_in_executor(
                None, perm_cache.health_check
            )
            cache_tests["permission_cache"] = perm_health
        except Exception as e:
            cache_tests["permission_cache"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Overall health status
        redis_healthy = connection_test.get("overall_success", False)
        caches_healthy = all(
            test.get("status") in ["healthy", "degraded"] 
            for test in cache_tests.values()
        )
        
        overall_status = "healthy" if (redis_healthy and caches_healthy) else (
            "degraded" if caches_healthy else "unhealthy"
        )
        
        result = {
            "status": overall_status,
            "timestamp": time.time(),
            "redis_url": settings.redis_url,
            "redis_connection_test": connection_test,
            "cache_tests": cache_tests,
            "summary": {
                "redis_available": redis_healthy,
                "caches_functional": caches_healthy,
                "memory_fallback_active": not redis_healthy
            }
        }
        
        logger.info(f"✅ [REDIS-HEALTH] Health check completed: {overall_status}")
        return result
        
    except Exception as e:
        logger.error(f"❌ [REDIS-HEALTH] Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Redis health check failed: {str(e)}")


@router.get("/connection-test")
async def redis_connection_test() -> Dict[str, Any]:
    """Detailed Redis connection test."""
    try:
        logger.info("🔍 [REDIS-TEST] Running connection test")
        
        result = await asyncio.get_event_loop().run_in_executor(
            None, test_redis_connection, settings.redis_url
        )
        
        return {
            "status": "success",
            "timestamp": time.time(),
            "test_results": result
        }
        
    except Exception as e:
        logger.error(f"❌ [REDIS-TEST] Connection test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.get("/stats")
async def redis_stats() -> Dict[str, Any]:
    """Get Redis cache statistics."""
    try:
        logger.info("📊 [REDIS-STATS] Collecting cache statistics")
        
        # Get stats from all cache instances
        cache_stats = {}
        
        try:
            auth_cache = get_authorization_cache()
            cache_stats["authorization_cache"] = await asyncio.get_event_loop().run_in_executor(
                None, auth_cache.get_stats
            )
        except Exception as e:
            cache_stats["authorization_cache"] = {"error": str(e)}
        
        try:
            session_cache = get_user_session_cache()
            cache_stats["user_session_cache"] = await asyncio.get_event_loop().run_in_executor(
                None, session_cache.get_stats
            )
        except Exception as e:
            cache_stats["user_session_cache"] = {"error": str(e)}
        
        try:
            perm_cache = get_permission_cache()
            cache_stats["permission_cache"] = await asyncio.get_event_loop().run_in_executor(
                None, perm_cache.get_stats
            )
        except Exception as e:
            cache_stats["permission_cache"] = {"error": str(e)}
        
        # Calculate aggregate statistics
        total_hits = sum(
            stats.get("operations", {}).get("hits", 0)
            for stats in cache_stats.values()
            if isinstance(stats, dict) and "error" not in stats
        )
        
        total_misses = sum(
            stats.get("operations", {}).get("misses", 0)
            for stats in cache_stats.values()
            if isinstance(stats, dict) and "error" not in stats
        )
        
        total_memory_entries = sum(
            stats.get("memory_cache_entries", 0)
            for stats in cache_stats.values()
            if isinstance(stats, dict) and "error" not in stats
        )
        
        overall_hit_rate = (
            (total_hits / (total_hits + total_misses) * 100) 
            if (total_hits + total_misses) > 0 else 0
        )
        
        result = {
            "status": "success",
            "timestamp": time.time(),
            "redis_url": settings.redis_url,
            "cache_stats": cache_stats,
            "aggregate_stats": {
                "total_hits": total_hits,
                "total_misses": total_misses,
                "total_memory_entries": total_memory_entries,
                "overall_hit_rate_percent": round(overall_hit_rate, 2)
            }
        }
        
        logger.info(f"📊 [REDIS-STATS] Statistics collected: {overall_hit_rate:.1f}% hit rate")
        return result
        
    except Exception as e:
        logger.error(f"❌ [REDIS-STATS] Stats collection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stats collection failed: {str(e)}")


@router.post("/clear-cache")
async def clear_redis_cache() -> Dict[str, Any]:
    """Clear all Redis caches (use with caution)."""
    try:
        logger.info("🧹 [REDIS-CLEAR] Clearing all caches")
        
        results = {}
        
        # Clear authorization cache
        try:
            auth_cache = get_authorization_cache()
            auth_cleared = await asyncio.get_event_loop().run_in_executor(
                None, auth_cache.clear_all
            )
            results["authorization_cache"] = {"success": auth_cleared}
        except Exception as e:
            results["authorization_cache"] = {"success": False, "error": str(e)}
        
        # Clear user session cache
        try:
            session_cache = get_user_session_cache()
            session_cleared = await asyncio.get_event_loop().run_in_executor(
                None, session_cache.clear_all
            )
            results["user_session_cache"] = {"success": session_cleared}
        except Exception as e:
            results["user_session_cache"] = {"success": False, "error": str(e)}
        
        # Clear permission cache
        try:
            perm_cache = get_permission_cache()
            perm_cleared = await asyncio.get_event_loop().run_in_executor(
                None, perm_cache.clear_all
            )
            results["permission_cache"] = {"success": perm_cleared}
        except Exception as e:
            results["permission_cache"] = {"success": False, "error": str(e)}
        
        success_count = sum(1 for r in results.values() if r.get("success"))
        total_count = len(results)
        
        logger.info(f"🧹 [REDIS-CLEAR] Cache clear complete: {success_count}/{total_count} succeeded")
        
        return {
            "status": "success" if success_count == total_count else "partial",
            "timestamp": time.time(),
            "results": results,
            "summary": {
                "cleared_caches": success_count,
                "total_caches": total_count
            }
        }
        
    except Exception as e:
        logger.error(f"❌ [REDIS-CLEAR] Cache clear failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@router.get("/config")
async def redis_config() -> Dict[str, Any]:
    """Get Redis configuration information."""
    return {
        "status": "success",
        "timestamp": time.time(),
        "config": {
            "redis_url": settings.redis_url,
            "redis_max_connections": settings.redis_max_connections,
            "redis_timeout": settings.redis_timeout,
            "cache_default_ttl": settings.cache_default_ttl,
            "cache_auth_ttl": settings.cache_auth_ttl,
            "cache_max_size": settings.cache_max_size,
            "cache_l1_size_mb": settings.cache_l1_size_mb,
            "cache_l2_enabled": settings.cache_l2_enabled
        }
    }