"""
Refactored main.py with modular middleware and proper bootstrap sequence.
Following the middleware refactor plan for stability and observability.
"""
import os
import sys
import time
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import configuration
from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Log startup configuration
logger.info("=" * 60)
logger.info(f"🚀 Starting {settings.SERVICE_NAME} v{settings.SERVICE_VERSION}")
logger.info(f"📍 Environment: {settings.ENVIRONMENT}")
logger.info(f"🔧 Bypass mode: {settings.BYPASS_MIDDLEWARE or settings.BYPASS_ALL_MIDDLEWARE}")
logger.info("=" * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("🚀 [STARTUP] Beginning application startup...")
    
    # Initialize database
    try:
        from database import db
        logger.info("✅ [STARTUP] Database singleton initialized")
    except Exception as e:
        logger.error(f"❌ [STARTUP] Database initialization failed: {e}")
    
    # Log middleware configuration
    logger.info("📋 [STARTUP] Middleware configuration:")
    for key, value in settings.get_middleware_status().items():
        logger.info(f"  - {key}: {value}")
    
    yield
    
    # Shutdown
    logger.info("👋 [SHUTDOWN] Beginning graceful shutdown...")
    
    # Cleanup auth service
    try:
        from services.auth_service_async import cleanup_async_auth_service
        await cleanup_async_auth_service()
        logger.info("✅ [SHUTDOWN] Auth service cleaned up")
    except Exception as e:
        logger.warning(f"⚠️ [SHUTDOWN] Auth cleanup error: {e}")


# Create FastAPI app
app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.SERVICE_VERSION,
    description="Velro Backend API - Refactored with stable middleware",
    lifespan=lifespan,
    docs_url="/docs" if not settings.IS_PRODUCTION else None,
    redoc_url="/redoc" if not settings.IS_PRODUCTION else None,
)


# ============================================================================
# STEP 1: CORE ROUTES (Must work even in bypass mode)
# ============================================================================

@app.get("/__health")
async def health_check():
    """Zero-dependency health check."""
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/__version")
async def version_info():
    """Service version and environment info."""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "environment": settings.ENVIRONMENT,
        "railway_deployment": settings.RAILWAY_DEPLOYMENT_ID,
        "timestamp": time.time(),
    }


@app.get("/__config")
async def config_info():
    """Safe configuration info (no secrets)."""
    return settings.get_safe_config()


@app.get("/__diag/request")
async def diagnose_request(request: Request):
    """Diagnostic endpoint showing request details."""
    return {
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "client": {
            "host": request.client.host if request.client else None,
            "port": request.client.port if request.client else None,
        },
        "middleware_status": settings.get_middleware_status(),
        "request_id": getattr(request.state, "request_id", None),
        "user_id": getattr(request.state, "user_id", None),
    }


@app.get("/__diag/routes")
async def diagnose_routes():
    """List all registered routes."""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else [],
                "name": getattr(route, "name", "unknown"),
            })
    return {
        "total": len(routes),
        "routes": routes,
    }


@app.get("/__diag/middleware")
async def diagnose_middleware():
    """Show middleware configuration and status."""
    return {
        "bypass_active": settings.BYPASS_MIDDLEWARE or settings.BYPASS_ALL_MIDDLEWARE,
        "configuration": settings.get_middleware_status(),
        "redis_available": settings.REDIS_ENABLED,
        "fastlane_paths": settings.FASTLANE_PATHS,
    }


# ============================================================================
# STEP 2: EXCEPTION HANDLERS (Ensure JSON responses with proper headers)
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": request_id,
            "error": "http_error",
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(StarletteHTTPException)
async def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle Starlette HTTP exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": request_id,
            "error": "http_error",
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors."""
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "request_id": request_id,
            "error": "validation_error",
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"[{request_id}] Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
            "error": "internal_error",
        },
        headers={"X-Request-ID": request_id},
    )


# ============================================================================
# STEP 3: MIDDLEWARE BOOTSTRAP (Conditional based on settings)
# ============================================================================

if settings.BYPASS_MIDDLEWARE or settings.BYPASS_ALL_MIDDLEWARE:
    # Emergency bypass mode - only minimal logger and CORS
    logger.warning("🚨 [MIDDLEWARE] BYPASS MODE ACTIVE - Only minimal middleware loaded")
    
    # Add minimal logger
    from middleware.minimal_logger import MinimalLoggerMiddleware
    app.add_middleware(MinimalLoggerMiddleware)
    logger.info("✅ [MW] Minimal logger added")
    
else:
    # Normal mode - add middleware based on settings
    logger.info("🔧 [MIDDLEWARE] Loading middleware stack...")
    
    # 1. Trusted hosts (if enabled and in production)
    if settings.ENABLE_TRUSTED_HOSTS and settings.IS_PRODUCTION:
        try:
            app.add_middleware(
                TrustedHostMiddleware,
                allowed_hosts=settings.ALLOWED_HOSTS
            )
            logger.info(f"✅ [MW] TrustedHost: {len(settings.ALLOWED_HOSTS)} hosts")
        except Exception as e:
            logger.error(f"❌ [MW] TrustedHost failed: {e}")
    
    # 2. Minimal logger (always)
    try:
        from middleware.minimal_logger import MinimalLoggerMiddleware
        app.add_middleware(MinimalLoggerMiddleware)
        logger.info("✅ [MW] Minimal logger added")
    except Exception as e:
        logger.error(f"❌ [MW] Logger failed: {e}")
    
    # 3. Auth middleware (if enabled)
    if settings.ENABLE_AUTH:
        try:
            from middleware.auth_refactored import AuthMiddleware
            public_paths = ["/health", "/__health", "/__version", "/__diag", "/__config"]
            public_paths.extend(settings.FASTLANE_PATHS)
            app.add_middleware(AuthMiddleware, public_paths=public_paths)
            logger.info("✅ [MW] Auth middleware added")
        except Exception as e:
            logger.error(f"❌ [MW] Auth failed: {e}")
    
    # 4. Rate limiter (if enabled)
    if settings.ENABLE_RATE_LIMIT:
        try:
            from middleware.rate_limiter_safe import RateLimiterMiddleware
            app.add_middleware(
                RateLimiterMiddleware,
                redis_url=settings.REDIS_URL,
                default_limit=settings.RATE_LIMIT_DEFAULT
            )
            logger.info(f"✅ [MW] Rate limiter added (Redis: {settings.REDIS_ENABLED})")
        except Exception as e:
            logger.error(f"❌ [MW] Rate limiter failed: {e}")
    
    # 5. GZip compression (if enabled)
    if settings.ENABLE_GZIP:
        try:
            app.add_middleware(GZipMiddleware, minimum_size=1000)
            logger.info("✅ [MW] GZip compression added")
        except Exception as e:
            logger.error(f"❌ [MW] GZip failed: {e}")

# CRITICAL: Add CORS last so it's outermost
from middleware.cors_handler import add_cors_middleware
add_cors_middleware(app)


# ============================================================================
# STEP 4: REGISTER APPLICATION ROUTERS (Guarded)
# ============================================================================

def register_router_safe(app: FastAPI, module_path: str, prefix: str, tag: str):
    """Safely register a router with error handling."""
    try:
        module = __import__(f"routers.{module_path}", fromlist=["router"])
        router = getattr(module, "router")
        app.include_router(router, prefix=prefix, tags=[tag])
        logger.info(f"✅ [ROUTER] {tag} registered at {prefix}")
        return True
    except Exception as e:
        logger.error(f"❌ [ROUTER] {tag} failed: {e}")
        # Create fallback endpoints for critical routes
        if module_path == "credits":
            @app.get(f"{prefix}/_ping")
            async def credits_ping_fallback():
                return {"ok": True, "service": "credits", "fallback": True}
        elif module_path == "projects":
            @app.get(f"{prefix}/_ping")
            async def projects_ping_fallback():
                return {"ok": True, "service": "projects", "fallback": True}
        return False


# Register routers
logger.info("📦 [ROUTERS] Registering application routers...")

routers_config = [
    ("auth", "/api/v1/auth", "Authentication"),
    ("credits", "/api/v1/credits", "Credits"),
    ("projects", "/api/v1/projects", "Projects"),
    ("generations", "/api/v1/generations", "Generations"),
    ("models", "/api/v1/models", "Models"),
    ("storage", "/api/v1/storage", "Storage"),
]

registered_count = 0
for module, prefix, tag in routers_config:
    if register_router_safe(app, module, prefix, tag):
        registered_count += 1

logger.info(f"📊 [ROUTERS] {registered_count}/{len(routers_config)} routers registered successfully")


# ============================================================================
# STEP 5: STARTUP VALIDATION
# ============================================================================

@app.on_event("startup")
async def startup_validation():
    """Validate critical routes are registered."""
    critical_paths = [
        "/__health",
        "/__version",
        "/api/v1/credits/_ping",
        "/api/v1/projects/_ping",
    ]
    
    registered_paths = []
    for route in app.routes:
        if hasattr(route, "path"):
            registered_paths.append(route.path)
    
    logger.info("🔍 [STARTUP] Validating critical routes...")
    for path in critical_paths:
        if path in registered_paths:
            logger.info(f"  ✅ {path}")
        else:
            logger.warning(f"  ⚠️ {path} not found!")
    
    logger.info(f"📊 [STARTUP] Total routes: {len(registered_paths)}")
    logger.info("🎉 [STARTUP] Application ready!")


# ============================================================================
# Entry point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )