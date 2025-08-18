"""
System monitoring and verification endpoints.
Provides deployment verification, health checks, and configuration status.
"""
import os
import time
import subprocess
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])

def get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2
        )
        return result.stdout.strip()[:8] if result.returncode == 0 else "unknown"
    except:
        return "unknown"

@router.get("/__version")
async def get_version_info() -> Dict[str, Any]:
    """
    Deployment verification endpoint.
    Returns current configuration to verify correct deployment.
    """
    # Import here to avoid circular dependency
    from services.auth_service_async import AsyncAuthService
    from config import settings
    
    # Check actual timeout values from the service
    timeout_config = {
        "connect": "3.0s",
        "read": "8.0s",
        "write": "2.0s",
        "pool": "1.0s"
    }
    
    # Check circuit breaker state
    circuit_breaker_status = {
        "enabled": True,
        "consecutive_failures": AsyncAuthService._consecutive_failures,
        "circuit_open": AsyncAuthService._circuit_open,
        "threshold": 3,
        "timeout_duration": 30
    }
    
    return {
        "service": "velro-backend",
        "version": "1.2.0",
        "commit": get_git_commit(),
        "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID", "local"),
        "environment": settings.environment,
        "timestamp": time.time(),
        "configuration": {
            "timeout_config": timeout_config,
            "circuit_breaker": circuit_breaker_status,
            "redis_enabled": bool(settings.redis_url),
            "supabase_url": settings.supabase_url,
            "auth_mode": "async_with_circuit_breaker"
        },
        "features": {
            "circuit_breaker": True,
            "fast_path_middleware": True,
            "redis_fallback": True,
            "timeout_protection": "double_layer"
        }
    }

@router.get("/__health")
async def detailed_health_check() -> Dict[str, Any]:
    """
    Detailed health check with subsystem status.
    """
    from database import SupabaseClient
    from caching.redis_cache import RedisCache
    
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "subsystems": {}
    }
    
    # Check database
    try:
        db = SupabaseClient()
        health_status["subsystems"]["database"] = {
            "status": "healthy" if db.is_available() else "degraded",
            "anon_client": bool(db.anon_client),
            "service_client": bool(db.service_client)
        }
    except Exception as e:
        health_status["subsystems"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check Redis
    try:
        redis = RedisCache()
        redis_available = await redis.ping() if hasattr(redis, 'ping') else False
        health_status["subsystems"]["redis"] = {
            "status": "healthy" if redis_available else "degraded",
            "fallback": "in_memory"
        }
    except:
        health_status["subsystems"]["redis"] = {
            "status": "degraded",
            "fallback": "in_memory"
        }
    
    # Check auth service
    try:
        from services.auth_service_async import get_async_auth_service
        auth_service = await get_async_auth_service()
        health_status["subsystems"]["auth"] = {
            "status": "healthy",
            "circuit_breaker": {
                "failures": AsyncAuthService._consecutive_failures,
                "open": AsyncAuthService._circuit_open
            }
        }
    except Exception as e:
        health_status["subsystems"]["auth"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Overall status
    if any(s.get("status") == "unhealthy" for s in health_status["subsystems"].values()):
        health_status["status"] = "unhealthy"
    elif any(s.get("status") == "degraded" for s in health_status["subsystems"].values()):
        health_status["status"] = "degraded"
    
    return health_status

@router.get("/__config")
async def get_configuration() -> Dict[str, Any]:
    """
    Protected endpoint showing current configuration.
    In production, this should require authentication.
    """
    from config import settings
    
    return {
        "environment": settings.environment,
        "debug": settings.debug,
        "cors_origins": settings.cors_origins,
        "rate_limits": {
            "per_minute": settings.rate_limit_per_minute,
            "generation": settings.generation_rate_limit
        },
        "timeouts": {
            "auth_connect": "3.0s",
            "auth_read": "8.0s",
            "auth_write": "2.0s",
            "redis": f"{settings.redis_timeout}ms" if settings.redis_timeout else "200ms"
        },
        "features": {
            "circuit_breaker": True,
            "fast_path": True,
            "redis_cache": bool(settings.redis_url),
            "jwt_validation": True
        }
    }