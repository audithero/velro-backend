"""
Public router for endpoints that don't require authentication.
"""
import os
import time
from fastapi import APIRouter

router = APIRouter(tags=["public"])


@router.get("/flags")
async def get_flags():
    """
    Public endpoint to expose feature flags and configuration.
    No authentication required - for monitoring and debugging.
    """
    return {
        "timestamp": time.time(),
        "auth": {
            "fast_login": os.getenv("AUTH_FAST_LOGIN", "true"),
            "http1_fallback": os.getenv("AUTH_HTTP1_FALLBACK", "true"),
            "circuit_breaker_enabled": True,
            "fastlane_middleware": True
        },
        "timeouts": {
            "outer_timeout_s": float(os.getenv("AUTH_OUTER_TIMEOUT_SECONDS", "10")),
            "inner_timeout_s": float(os.getenv("AUTH_INNER_TIMEOUT_SECONDS", "8")),
            "connect_timeout_s": float(os.getenv("AUTH_CONNECT_TIMEOUT", "3.0")),
            "read_timeout_s": float(os.getenv("AUTH_READ_TIMEOUT", "8.0"))
        },
        "circuit_breaker": {
            "threshold": int(os.getenv("AUTH_CB_THRESHOLD", "3")),
            "open_seconds": float(os.getenv("AUTH_CB_OPEN_SECONDS", "30"))
        },
        "performance": {
            "target_p95_ms": 1500,
            "current_phase": "A",
            "optimizations_enabled": [
                "fastlane_middleware",
                "cancelable_timeouts",
                "circuit_breaker",
                "http1_fallback",
                "fast_login_mode"
            ]
        }
    }


@router.get("/health/auth")
async def auth_health_check():
    """
    Lightweight auth service health check.
    Returns quickly with minimal processing.
    """
    return {
        "status": "healthy",
        "service": "auth",
        "timestamp": time.time(),
        "fast_path": True
    }