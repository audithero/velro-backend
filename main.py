"""
Recovery main.py with binary-search middleware configuration.
Uses environment variables to enable/disable middleware layers for debugging.
"""
import os
import sys
import time
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================

# Binary search flags
BYPASS_ALL_MIDDLEWARE = os.getenv("BYPASS_ALL_MIDDLEWARE", "false").lower() == "true"
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
DISABLE_HEAVY_MIDDLEWARE = os.getenv("DISABLE_HEAVY_MIDDLEWARE", "true").lower() == "true"
CATCH_ALL_EXCEPTIONS = os.getenv("CATCH_ALL_EXCEPTIONS", "true").lower() == "true"
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "false").lower() == "true"
DEBUG_ENDPOINTS = os.getenv("DEBUG_ENDPOINTS", "true").lower() == "true"

# Service info
SERVICE_NAME = os.getenv("SERVICE_NAME", "velro-backend-recovery")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.1.5-recovery")
ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "development"))
IS_PRODUCTION = ENVIRONMENT == "production"
PORT = int(os.getenv("PORT", "8000"))

# Feature flags
USE_SUPABASE_AUTH = os.getenv("USE_SUPABASE_AUTH", "true").lower() == "true"

# Log configuration
logger.info("=" * 60)
logger.info(f"🚀 Starting {SERVICE_NAME} v{SERVICE_VERSION}")
logger.info(f"📍 Environment: {ENVIRONMENT}")
logger.info(f"🔧 Configuration:")
logger.info(f"  - BYPASS_ALL_MIDDLEWARE: {BYPASS_ALL_MIDDLEWARE}")
logger.info(f"  - RATE_LIMIT_ENABLED: {RATE_LIMIT_ENABLED}")
logger.info(f"  - DISABLE_HEAVY_MIDDLEWARE: {DISABLE_HEAVY_MIDDLEWARE}")
logger.info(f"  - CATCH_ALL_EXCEPTIONS: {CATCH_ALL_EXCEPTIONS}")
logger.info(f"  - AUTH_ENABLED: {AUTH_ENABLED}")
logger.info(f"  - DEPLOYMENT_MODE: {DEPLOYMENT_MODE}")
logger.info(f"  - DEBUG_ENDPOINTS: {DEBUG_ENDPOINTS}")
logger.info(f"  - USE_SUPABASE_AUTH: {USE_SUPABASE_AUTH}")
logger.info("=" * 60)


# =============================================================================
# LIFESPAN MANAGEMENT
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("🚀 [STARTUP] Beginning application startup...")
    
    # Initialize database with async context
    # This is CRITICAL for generation service to work properly
    try:
        from database import initialize_database_async
        start_time = time.time()
        db_init_success = await initialize_database_async()
        init_time_ms = (time.time() - start_time) * 1000
        
        if db_init_success:
            logger.info(f"✅ [STARTUP] Database async context fully initialized in {init_time_ms:.2f}ms")
        else:
            logger.warning(f"⚠️ [STARTUP] Database initialized with degraded performance in {init_time_ms:.2f}ms")
    except Exception as e:
        logger.error(f"❌ [STARTUP] Database initialization failed: {e}")
        # Don't fail startup - auth can still work without this
    
    # Initialize auth service
    try:
        from services.auth_service_async import get_async_auth_service
        await get_async_auth_service()
        logger.info("✅ [STARTUP] Auth service initialized")
    except Exception as e:
        logger.error(f"❌ [STARTUP] Auth service initialization failed: {e}")
    
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


# =============================================================================
# CREATE FASTAPI APP
# =============================================================================

app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="Velro Backend API - Recovery Mode",
    lifespan=lifespan,
    docs_url="/docs" if not IS_PRODUCTION or DEBUG_ENDPOINTS else None,
    redoc_url="/redoc" if not IS_PRODUCTION or DEBUG_ENDPOINTS else None,
)


# =============================================================================
# CORE HEALTH ENDPOINTS (Always available)
# =============================================================================

@app.get("/health")
async def health():
    """Simple health check - must always work."""
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/__health")
async def dunder_health():
    """Alternative health check."""
    return {"status": "healthy", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/api/v1/health/config")
async def health_config():
    """Get health configuration status."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "environment": ENVIRONMENT,
        "supabase": {
            "configured": bool(os.getenv("SUPABASE_URL")),
            "auth_enabled": USE_SUPABASE_AUTH
        },
        "features": {
            "auth_enabled": AUTH_ENABLED,
            "rate_limit_enabled": RATE_LIMIT_ENABLED,
            "deployment_mode": DEPLOYMENT_MODE
        }
    }


# =============================================================================
# MIDDLEWARE CONFIGURATION (Order matters - last added = outermost)
# =============================================================================

if not BYPASS_ALL_MIDDLEWARE:
    logger.info("🔧 [MIDDLEWARE] Loading middleware stack...")
    
    # 1. GZip compression (innermost, optional)
    if not DISABLE_HEAVY_MIDDLEWARE:
        try:
            app.add_middleware(GZipMiddleware, minimum_size=1000)
            logger.info("✅ [MW] GZip compression added")
        except Exception as e:
            logger.error(f"❌ [MW] GZip failed: {e}")
    
    # 2. Auth middleware (if enabled)
    if AUTH_ENABLED:
        try:
            from middleware.auth_refactored import AuthMiddleware
            # Comprehensive list of public endpoints that don't require authentication
            public_paths = [
                # Health & diagnostic endpoints
                "/health", "/__health", "/__version", "/__diag", "/__config",
                "/api/v1/health", "/_ping", "/baseline",
                
                # Documentation endpoints
                "/docs", "/redoc", "/openapi.json",
                
                # Authentication endpoints (must be public for login/register)
                "/api/v1/auth/login",
                "/api/v1/auth/register", 
                "/api/v1/auth/refresh",
                "/api/v1/auth/health",
                "/api/v1/auth",  # Include base auth path
                
                # Public model endpoints
                "/api/v1/generations/models/supported",
                "/api/v1/models",  # Models router base path
                
                # Debug endpoints (if enabled)
                "/debug",
                
                # Performance endpoints (public for monitoring)
                "/api/v1/performance/metrics",
                "/api/v1/performance/health"
            ]
            app.add_middleware(AuthMiddleware, public_paths=public_paths)
            logger.info("✅ [MW] Auth middleware added with comprehensive public paths")
        except Exception as e:
            logger.error(f"❌ [MW] Auth failed: {e}")
            # Try fallback auth
            try:
                from middleware.auth import AuthMiddleware as FallbackAuth
                app.add_middleware(FallbackAuth)
                logger.info("✅ [MW] Fallback auth added")
            except Exception as e2:
                logger.error(f"❌ [MW] Fallback auth also failed: {e2}")
    
    # 3. Rate limiting (if enabled)
    if RATE_LIMIT_ENABLED:
        try:
            from middleware.rate_limiter_safe import RateLimiterMiddleware
            redis_url = os.getenv("REDIS_URL", "")
            app.add_middleware(
                RateLimiterMiddleware,
                redis_url=redis_url,
                default_limit="100/minute"
            )
            logger.info(f"✅ [MW] Rate limiter added (Redis: {bool(redis_url)})")
        except Exception as e:
            logger.error(f"❌ [MW] Rate limiter failed: {e}")
    
    # 4. Global error handler (ensures CORS on errors)
    if CATCH_ALL_EXCEPTIONS:
        try:
            from middleware.global_error_handler import GlobalErrorMiddleware
            app.add_middleware(GlobalErrorMiddleware)
            logger.info("✅ [MW] Global error handler added")
        except Exception as e:
            logger.error(f"❌ [MW] Global error handler failed: {e}")
    
    # 5. Request ID and timing middleware
    try:
        from middleware.request_tracking import RequestTrackingMiddleware
        app.add_middleware(RequestTrackingMiddleware)
        logger.info("✅ [MW] Request tracking added")
    except Exception as e:
        logger.warning(f"⚠️ [MW] Request tracking not available: {e}")
        # Fallback: minimal request ID middleware
        from starlette.middleware.base import BaseHTTPMiddleware
        import uuid
        
        class MinimalRequestIDMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
                request.state.request_id = request_id
                response = await call_next(request)
                response.headers["X-Request-ID"] = request_id
                return response
        
        app.add_middleware(MinimalRequestIDMiddleware)
        logger.info("✅ [MW] Minimal request ID added")

else:
    logger.warning("🚨 [MIDDLEWARE] BYPASS MODE - Only CORS will be loaded")


# =============================================================================
# CORS MIDDLEWARE (ALWAYS LAST/OUTERMOST)
# =============================================================================

# Parse CORS origins
CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "")
if CORS_ORIGINS_ENV:
    try:
        import json
        CORS_ORIGINS = json.loads(CORS_ORIGINS_ENV)
    except:
        CORS_ORIGINS = CORS_ORIGINS_ENV.split(",") if "," in CORS_ORIGINS_ENV else [CORS_ORIGINS_ENV]
else:
    CORS_ORIGINS = [
        "https://velro-frontend-production.up.railway.app",
        "https://velro-003-frontend-production.up.railway.app",
        "https://velro-kong-gateway-production.up.railway.app",
        "https://velro-kong-gateway-latest-production.up.railway.app",
        "https://velro.ai",
        "https://www.velro.ai",
        "http://localhost:3000",
        "http://localhost:3001"
    ]

# Add CORS middleware (MUST be last = outermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400
)
logger.info(f"✅ [MW] CORS added with {len(CORS_ORIGINS)} origins")


# =============================================================================
# REGISTER ROUTERS
# =============================================================================

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
        # Create fallback ping endpoint for critical routes
        @app.get(f"{prefix}/_ping")
        async def fallback_ping():
            return {"ok": True, "service": tag.lower(), "fallback": True}
        return False


# Register debug router (if enabled)
if DEBUG_ENDPOINTS:
    try:
        from routers.debug_endpoints import router as debug_router
        app.include_router(debug_router, prefix="/debug", tags=["debug"])
        logger.info("✅ [ROUTER] Debug endpoints registered")
    except Exception as e:
        logger.warning(f"⚠️ [ROUTER] Debug endpoints failed: {e}")

# Register application routers
logger.info("📦 [ROUTERS] Registering application routers...")

# Choose auth router based on feature flag
auth_module = "auth_supabase" if USE_SUPABASE_AUTH else "auth"
if USE_SUPABASE_AUTH:
    logger.info("🔐 [AUTH] Using Supabase auth router")
else:
    logger.info("🔐 [AUTH] Using legacy auth router")

routers_config = [
    (auth_module, "/api/v1/auth", "Authentication"),
    ("credits", "/api/v1/credits", "Credits"),
    ("user", "/api/v1/user", "User"),  # Added user router
    ("projects", "/api/v1/projects", "Projects"),
    ("generations", "/api/v1/generations", "Generations"),
    ("generations_async", "/api/v1/generations/async", "Async Generations"),  # Fixed prefix conflict
    ("models", "/api/v1/models", "Models"),
    ("storage", "/api/v1/storage", "Storage"),
]

registered_count = 0
for module, prefix, tag in routers_config:
    if register_router_safe(app, module, prefix, tag):
        registered_count += 1

logger.info(f"📊 [ROUTERS] {registered_count}/{len(routers_config)} routers registered")

# CRITICAL FIX: Also mount generations router at /generations for frontend compatibility
try:
    from routers.generations import router as generations_router
    app.include_router(generations_router, prefix="/generations", tags=["Generations-Direct"])
    logger.info("✅ [ROUTER] Generations also mounted at /generations for frontend compatibility")
except Exception as e:
    logger.warning(f"⚠️ [ROUTER] Could not mount generations at /generations: {e}")


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with CORS headers."""
    request_id = getattr(request.state, "request_id", "unknown")
    origin = request.headers.get("Origin", "")
    
    response = JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": request_id,
            "status_code": exc.status_code
        }
    )
    
    # Ensure CORS headers
    if origin and origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions with CORS headers."""
    request_id = getattr(request.state, "request_id", "unknown")
    origin = request.headers.get("Origin", "")
    
    logger.exception(f"[{request_id}] Unhandled exception: {exc}")
    
    response = JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
            "error": "internal_server_error"
        }
    )
    
    # Ensure CORS headers
    if origin and origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    
    response.headers["X-Request-ID"] = request_id
    return response


# =============================================================================
# STARTUP VALIDATION
# =============================================================================

@app.on_event("startup")
async def startup_validation():
    """Validate critical configuration on startup."""
    logger.info("🔍 [STARTUP] Validating configuration...")
    
    # Check critical environment variables
    critical_vars = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_ANON_KEY": os.getenv("SUPABASE_ANON_KEY"),
    }
    
    # Add appropriate JWT secret based on auth mode
    if USE_SUPABASE_AUTH:
        critical_vars["SUPABASE_JWT_SECRET"] = os.getenv("SUPABASE_JWT_SECRET")
    else:
        critical_vars["JWT_SECRET"] = os.getenv("JWT_SECRET")
    
    missing = [k for k, v in critical_vars.items() if not v]
    if missing and IS_PRODUCTION:
        logger.error(f"❌ [STARTUP] Missing critical variables: {missing}")
    
    logger.info("🎉 [STARTUP] Application ready!")
    logger.info(f"📊 [STARTUP] Middleware status:")
    logger.info(f"  - CORS: ✅ Enabled")
    logger.info(f"  - Auth: {'✅ Enabled' if AUTH_ENABLED else '❌ Disabled'}")
    logger.info(f"  - Rate Limit: {'✅ Enabled' if RATE_LIMIT_ENABLED else '❌ Disabled'}")
    logger.info(f"  - Error Handler: {'✅ Enabled' if CATCH_ALL_EXCEPTIONS else '❌ Disabled'}")
    logger.info(f"  - Heavy MW: {'❌ Disabled' if DISABLE_HEAVY_MIDDLEWARE else '✅ Enabled'}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )