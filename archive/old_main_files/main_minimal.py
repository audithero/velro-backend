"""
Minimal FastAPI app for isolating the CORS/500 error issue.
This app has ONLY CORS middleware and basic endpoints.
"""
import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create minimal app
app = FastAPI(
    title="Velro API - Minimal Test",
    version="0.0.1",
    description="Minimal app for debugging"
)

# Get CORS origins from environment
cors_origins_env = os.getenv("CORS_ORIGINS", '["*"]')
try:
    allowed_origins = json.loads(cors_origins_env)
except:
    allowed_origins = ["*"]

logger.info(f"🔧 CORS origins: {allowed_origins}")

# Add ONLY CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

logger.info("✅ CORS middleware added")

# Exception handlers to ensure JSON responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

# Basic endpoints
@app.get("/")
async def root():
    """Root endpoint - no dependencies."""
    return {"message": "Minimal app is running", "timestamp": time.time()}

@app.get("/health")
async def health():
    """Health check - no dependencies."""
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/api/v1/test/ping")
async def ping():
    """Test ping - no dependencies."""
    return {"ok": True, "service": "minimal", "timestamp": time.time()}

@app.get("/api/v1/test/error/{code}")
async def test_error(code: int):
    """Test error responses."""
    if code == 401:
        raise HTTPException(status_code=401, detail="Test unauthorized")
    elif code == 404:
        raise HTTPException(status_code=404, detail="Test not found")
    elif code == 500:
        raise Exception("Test server error")
    return {"code": code}

@app.get("/api/v1/test/cors")
async def test_cors(request: Request):
    """Test CORS configuration."""
    origin = request.headers.get("origin", "no-origin")
    return {
        "request_origin": origin,
        "allowed_origins": allowed_origins,
        "cors_configured": True
    }

# Now test adding a simple router
from fastapi import APIRouter

test_router = APIRouter(prefix="/api/v1/test-router", tags=["Test"])

@test_router.get("/ping")
async def router_ping():
    """Router ping endpoint."""
    return {"ok": True, "from": "router", "timestamp": time.time()}

@test_router.get("/protected")
async def router_protected():
    """Simulated protected endpoint."""
    # In real app, this would check auth
    raise HTTPException(status_code=401, detail="Not authenticated")

# Register the router
try:
    app.include_router(test_router)
    logger.info("✅ Test router registered")
except Exception as e:
    logger.error(f"❌ Failed to register router: {e}")

# Log all routes
logger.info("📍 Registered routes:")
for route in app.routes:
    if hasattr(route, 'path'):
        logger.info(f"  - {route.path}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)