"""
Debug router for diagnostic endpoints.
Only enabled in non-production or with DEBUG_ENDPOINTS=true.
"""
import os
import sys
import platform
import time
from typing import Dict, Any, List
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/debug", tags=["debug"])


def get_safe_env() -> Dict[str, str]:
    """Get environment variables with sensitive data redacted."""
    sensitive_patterns = [
        "KEY", "SECRET", "PASSWORD", "TOKEN", "CREDENTIAL",
        "API", "DATABASE_URL", "REDIS_URL"
    ]
    
    safe_env = {}
    for key, value in os.environ.items():
        is_sensitive = any(pattern in key.upper() for pattern in sensitive_patterns)
        if is_sensitive and value:
            # Show first 4 chars and length
            safe_env[key] = f"{value[:4]}...({len(value)} chars)"
        else:
            safe_env[key] = value
    
    return safe_env


@router.get("/request-info")
async def request_info(request: Request) -> JSONResponse:
    """
    Diagnostic endpoint showing:
    - Request headers
    - Active middleware
    - Python/system info
    - CORS configuration
    - Environment variables (redacted)
    """
    
    # Get middleware stack
    middleware_stack = []
    try:
        for middleware in request.app.user_middleware:
            middleware_stack.append({
                "class": middleware.cls.__name__ if hasattr(middleware, 'cls') else str(middleware),
                "options": str(middleware.options) if hasattr(middleware, 'options') else {}
            })
    except Exception as e:
        middleware_stack = [{"error": str(e)}]
    
    # Get CORS configuration
    cors_config = {
        "origins": os.getenv("CORS_ORIGINS", "not set"),
        "allow_credentials": os.getenv("ALLOW_CREDENTIALS", "true"),
        "bypass_all_middleware": os.getenv("BYPASS_ALL_MIDDLEWARE", "false"),
        "rate_limit_enabled": os.getenv("RATE_LIMIT_ENABLED", "true"),
        "disable_heavy_middleware": os.getenv("DISABLE_HEAVY_MIDDLEWARE", "false"),
        "catch_all_exceptions": os.getenv("CATCH_ALL_EXCEPTIONS", "true")
    }
    
    # System info
    system_info = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python_implementation": platform.python_implementation(),
        "node": platform.node()
    }
    
    # Request info
    request_info = {
        "method": request.method,
        "url": str(request.url),
        "client": f"{request.client.host}:{request.client.port}" if request.client else "unknown",
        "headers": dict(request.headers),
        "path_params": request.path_params,
        "query_params": dict(request.query_params),
        "request_id": getattr(request.state, "request_id", "not set"),
        "user_id": getattr(request.state, "user_id", "not set")
    }
    
    # Build response
    response_data = {
        "timestamp": time.time(),
        "request": request_info,
        "middleware_stack": middleware_stack,
        "cors_config": cors_config,
        "system": system_info,
        "environment": get_safe_env(),
        "feature_flags": {
            "bypass_all_middleware": os.getenv("BYPASS_ALL_MIDDLEWARE", "false") == "true",
            "rate_limit_enabled": os.getenv("RATE_LIMIT_ENABLED", "true") == "true",
            "disable_heavy_middleware": os.getenv("DISABLE_HEAVY_MIDDLEWARE", "false") == "true",
            "catch_all_exceptions": os.getenv("CATCH_ALL_EXCEPTIONS", "true") == "true",
            "auth_enabled": os.getenv("ENABLE_AUTH", "true") == "true",
            "deployment_mode": os.getenv("DEPLOYMENT_MODE", "false") == "true"
        }
    }
    
    return JSONResponse(content=response_data)


@router.get("/health-detailed")
async def health_detailed(request: Request) -> JSONResponse:
    """
    Detailed health check with component status.
    """
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "components": {}
    }
    
    # Check database
    try:
        from database import db
        # Simple query to check connection
        await db.fetch_one("SELECT 1")
        health_status["components"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # Check Redis
    try:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            import redis.asyncio as redis
            r = redis.from_url(redis_url)
            await r.ping()
            await r.close()
            health_status["components"]["redis"] = {"status": "healthy"}
        else:
            health_status["components"]["redis"] = {"status": "not_configured"}
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check Supabase
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        if supabase_url:
            health_status["components"]["supabase"] = {
                "status": "configured",
                "url": supabase_url.split('.')[0] + ".***"  # Partial URL for security
            }
        else:
            health_status["components"]["supabase"] = {"status": "not_configured"}
    except Exception as e:
        health_status["components"]["supabase"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check auth
    try:
        from services.auth_service_async import get_async_auth_service
        auth_service = await get_async_auth_service()
        health_status["components"]["auth_service"] = {"status": "initialized"}
    except Exception as e:
        health_status["components"]["auth_service"] = {
            "status": "failed",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    return JSONResponse(content=health_status)


@router.post("/echo")
async def echo(request: Request) -> JSONResponse:
    """
    Echo endpoint for testing - returns request details.
    """
    try:
        body = await request.json()
    except:
        body = None
    
    return JSONResponse(content={
        "headers": dict(request.headers),
        "method": request.method,
        "url": str(request.url),
        "body": body,
        "query_params": dict(request.query_params),
        "client": f"{request.client.host}:{request.client.port}" if request.client else None,
        "request_id": getattr(request.state, "request_id", None),
        "timestamp": time.time()
    })


@router.get("/timing-test")
async def timing_test(request: Request) -> JSONResponse:
    """
    Test endpoint with Server-Timing headers.
    """
    import asyncio
    
    start = time.perf_counter()
    timings = []
    
    # Simulate middleware timing
    await asyncio.sleep(0.01)  # 10ms
    timings.append(f"mw_cors;dur=10")
    
    await asyncio.sleep(0.02)  # 20ms  
    timings.append(f"mw_auth;dur=20")
    
    await asyncio.sleep(0.05)  # 50ms
    timings.append(f"router;dur=50")
    
    await asyncio.sleep(0.03)  # 30ms
    timings.append(f"db;dur=30")
    
    total = (time.perf_counter() - start) * 1000
    timings.append(f"total;dur={total:.2f}")
    
    response = JSONResponse(content={
        "message": "Timing test complete",
        "total_ms": f"{total:.2f}"
    })
    
    response.headers["Server-Timing"] = ", ".join(timings)
    return response