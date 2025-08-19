#!/usr/bin/env python3
"""
CRITICAL ROUTER FIX V2 - Alternative approach for router registration failure
This creates a completely new main.py with simplified router registration
"""

ALTERNATIVE_MAIN_PY = '''"""
EMERGENCY ALTERNATIVE MAIN.PY - Simplified router registration
Root cause: Complex middleware stack may be interfering with router registration
"""
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time
import os

# Import routers directly
from routers import auth, generations, projects, models, credits, storage, style_stacks

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app with minimal configuration
app = FastAPI(
    title="Velro API",
    description="AI-powered creative platform backend API",
    version="1.1.2",
    redirect_slashes=True
)

# MINIMAL CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://localhost:3002",
        "https://velro-frontend-production.up.railway.app",
        "https://velro.ai",
        "https://www.velro.ai"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# Basic endpoints
@app.get("/")
async def root():
    return {
        "message": "Velro API - AI-powered creative platform",
        "version": "1.1.2",
        "status": "operational",
        "api_endpoints": {
            "projects": "/api/v1/projects",
            "auth": "/api/v1/auth",
            "generations": "/api/v1/generations",
            "models": "/api/v1/models",
            "credits": "/api/v1/credits"
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": time.time()}

# DIRECT ROUTER REGISTRATION - No complex middleware interference
print("🔧 EMERGENCY: Registering routers directly...")

try:
    app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
    print("✅ Auth router registered")
except Exception as e:
    print(f"❌ Auth router failed: {e}")

try:
    app.include_router(projects.router, prefix="/api/v1", tags=["Projects"])
    print("✅ Projects router registered")
except Exception as e:
    print(f"❌ Projects router failed: {e}")

try:
    app.include_router(generations.router, prefix="/api/v1", tags=["Generations"])
    print("✅ Generations router registered")
except Exception as e:
    print(f"❌ Generations router failed: {e}")

try:
    app.include_router(models.router, prefix="/api/v1", tags=["AI Models"])
    print("✅ Models router registered")
except Exception as e:
    print(f"❌ Models router failed: {e}")

try:
    app.include_router(credits.router, prefix="/api/v1", tags=["Credits"])
    print("✅ Credits router registered")
except Exception as e:
    print(f"❌ Credits router failed: {e}")

try:
    app.include_router(storage.router, prefix="/api/v1", tags=["Storage"])
    print("✅ Storage router registered")
except Exception as e:
    print(f"❌ Storage router failed: {e}")

try:
    app.include_router(style_stacks.router, prefix="/api/v1", tags=["Style Stacks"])
    print("✅ Style Stacks router registered")
except Exception as e:
    print(f"❌ Style Stacks router failed: {e}")

print("🚀 EMERGENCY ROUTER REGISTRATION COMPLETE")

# Test endpoint to verify routers are working
@app.get("/api/test")
async def test_api():
    return {"message": "API routing is working", "timestamp": time.time()}
'''

def create_backup_and_replace():
    """Create backup of current main.py and replace with emergency version."""
    import shutil
    
    # Create backup
    shutil.copy("main.py", "main.py.backup.emergency")
    print("✅ Created backup: main.py.backup.emergency")
    
    # Write emergency version
    with open("main_emergency.py", "w") as f:
        f.write(ALTERNATIVE_MAIN_PY)
    print("✅ Created emergency main: main_emergency.py")
    
    print("🚨 EMERGENCY DEPLOYMENT OPTIONS:")
    print("1. Test emergency main locally: uvicorn main_emergency:app --host 0.0.0.0 --port 8000")
    print("2. Replace main.py: mv main_emergency.py main.py")
    print("3. Restore backup: mv main.py.backup.emergency main.py")
    
if __name__ == "__main__":
    create_backup_and_replace()