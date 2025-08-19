"""
Baseline FastAPI service to validate Railway/Kong edge behavior.
This minimal app ONLY has CORS + health + echo - no auth, no DB, no Redis.
Used to prove the platform can serve CORS correctly.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import sys
import os

app = FastAPI(title="baseline-cors-check", version="1.0.0")

# CORS configuration
ALLOWED_ORIGINS = [
    "https://velro-frontend-production.up.railway.app",
    "https://velro-003-frontend-production.up.railway.app", 
    "https://velro-kong-gateway-production.up.railway.app",
    "https://velro-kong-gateway-latest-production.up.railway.app",
    "https://velro.ai",
    "https://www.velro.ai",
    "http://localhost:3000",
    "http://localhost:3001"
]

# Add CORS middleware (MUST be last/outermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "baseline-cors-check",
        "status": "ok",
        "timestamp": time.time(),
        "python_version": sys.version
    }


@app.get("/health")
async def health():
    """Simple health check."""
    return {
        "status": "ok",
        "service": "baseline",
        "timestamp": time.time()
    }


@app.post("/echo")
async def echo(request: Request):
    """Echo endpoint - returns request details."""
    try:
        body = await request.json()
    except:
        body = None
    
    return {
        "headers": dict(request.headers),
        "body": body,
        "method": request.method,
        "url": str(request.url),
        "client": f"{request.client.host}:{request.client.port}" if request.client else None,
        "timestamp": time.time()
    }


@app.options("/echo")
async def echo_options():
    """Explicit OPTIONS handler for echo endpoint."""
    return {"message": "CORS preflight OK"}


@app.get("/cors-test")
async def cors_test(request: Request):
    """Test CORS configuration."""
    origin = request.headers.get("origin", "no-origin")
    return {
        "received_origin": origin,
        "allowed_origins": ALLOWED_ORIGINS,
        "cors_should_work": origin in ALLOWED_ORIGINS,
        "timestamp": time.time()
    }


@app.get("/env")
async def env_info():
    """Environment information (safe vars only)."""
    safe_env = {}
    for key, value in os.environ.items():
        if any(x in key.upper() for x in ["KEY", "SECRET", "PASSWORD", "TOKEN"]):
            safe_env[key] = "***REDACTED***"
        else:
            safe_env[key] = value
    
    return {
        "railway_environment": os.getenv("RAILWAY_ENVIRONMENT", "unknown"),
        "port": os.getenv("PORT", "8000"),
        "python_version": sys.version,
        "env_vars": safe_env
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)