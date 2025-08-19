"""
Minimal Velro Backend API - Railway Compatible
Simplified router registration to bypass TimeoutError conflicts.
"""
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time
import os

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Velro API",
    description="AI-powered creative platform backend API",
    version="1.1.2",
    redirect_slashes=True
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://localhost:3002",
        "https://velro-frontend-production.up.railway.app",
        "https://velro-003-frontend-production.up.railway.app",
        "https://velro.ai",
        "https://www.velro.ai"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Basic endpoints
@app.get("/")
async def root():
    return {
        "message": "Velro API - AI-powered creative platform",
        "version": "1.1.2", 
        "status": "operational",
        "timestamp": time.time(),
        "api_endpoints": {
            "auth": "/api/v1/auth",
            "projects": "/api/v1/projects", 
            "generations": "/api/v1/generations",
            "models": "/api/v1/models",
            "credits": "/api/v1/credits",
            "storage": "/api/v1/storage"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "timestamp": time.time(),
        "version": "1.1.2",
        "environment": os.getenv("RAILWAY_ENVIRONMENT", "production")
    }

# Direct router registration without imports
logger.info("🚀 Starting Velro API server...")

# Auth router - direct definition to bypass import issues
from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

auth_router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
security = HTTPBearer()

@auth_router.post("/login")
async def login():
    """Temporary auth endpoint while fixing import issues"""
    return {"message": "Auth system temporarily unavailable - fixing import conflicts", "status": "maintenance"}

@auth_router.post("/register") 
async def register():
    """Temporary auth endpoint while fixing import issues"""
    return {"message": "Auth system temporarily unavailable - fixing import conflicts", "status": "maintenance"}

@auth_router.get("/me")
async def get_me():
    """Temporary auth endpoint while fixing import issues"""
    return {"message": "Auth system temporarily unavailable - fixing import conflicts", "status": "maintenance"}

@auth_router.get("/security-info")
async def security_info():
    """Auth security information"""
    return {
        "rate_limits": {
            "login": "5 attempts per minute",
            "register": "3 attempts per minute"
        },
        "status": "maintenance_mode",
        "message": "Resolving TimeoutError import conflicts"
    }

# Register auth router
app.include_router(auth_router)
logger.info("✅ Minimal auth router registered")

# Add simple project endpoint
projects_router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])

@projects_router.get("/")
async def list_projects():
    return {"message": "Projects endpoint active", "projects": []}

@projects_router.post("/")  
async def create_project():
    return {"message": "Project creation endpoint active"}

app.include_router(projects_router)
logger.info("✅ Minimal projects router registered")

logger.info("🎉 Minimal Velro API server ready!")

# For Railway deployment
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main_minimal:app", host="0.0.0.0", port=port, log_level="info")