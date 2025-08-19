"""
Diagnostics router with wrapped imports for better error handling.
"""
from fastapi import APIRouter
import logging
import traceback

router = APIRouter(prefix="/api/v1/diagnostics", tags=["Diagnostics"])
logger = logging.getLogger(__name__)

@router.get("/ping")
def diag_ping():
    """Simple ping endpoint to verify diagnostics router is loaded."""
    return {"status": "ok", "message": "Diagnostics router is working"}

@router.get("/models")
def diag_models():
    """Diagnose models service configuration with wrapped imports."""
    out = {"imports": {}, "errors": [], "env": {}}
    
    # Test basic imports
    try:
        import os
        out["imports"]["os"] = True
        out["env"]["FAL_KEY"] = bool(os.getenv("FAL_KEY"))
        out["env"]["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "unknown")
    except Exception as e:
        out["errors"].append(f"os import error: {e}\n{traceback.format_exc()}")
    
    # Test models.fal_config import
    try:
        import importlib.util
        spec = importlib.util.find_spec("models.fal_config")
        if spec is None:
            out["imports"]["models.fal_config"] = False
            out["errors"].append("models.fal_config module not found in Python path")
        else:
            out["imports"]["models.fal_config_found"] = True
            try:
                from models.fal_config import get_all_models, FALModelType
                out["imports"]["models.fal_config"] = True
                try:
                    models = get_all_models()
                    out["models_len"] = len(models)
                    out["sample_models"] = list(models.keys())[:3] if models else []
                except Exception as e:
                    out["errors"].append(f"get_all_models() error: {e}\n{traceback.format_exc()}")
            except Exception as e:
                out["imports"]["models.fal_config"] = False
                out["errors"].append(f"models.fal_config import error: {e}\n{traceback.format_exc()}")
    except Exception as e:
        out["errors"].append(f"importlib error: {e}\n{traceback.format_exc()}")
    
    # Test services.fal_service import (if exists)
    try:
        spec = importlib.util.find_spec("services.fal_service")
        if spec:
            try:
                from services.fal_service import fal_service
                out["imports"]["services.fal_service"] = True
                try:
                    models = fal_service.get_supported_models()
                    out["fal_service_models"] = len(models) if models else 0
                except Exception as e:
                    out["errors"].append(f"fal_service.get_supported_models error: {e}\n{traceback.format_exc()}")
            except Exception as e:
                out["imports"]["services.fal_service"] = False
                out["errors"].append(f"services.fal_service import error: {e}\n{traceback.format_exc()}")
        else:
            out["imports"]["services.fal_service"] = "not_found"
    except Exception as e:
        out["errors"].append(f"services check error: {e}\n{traceback.format_exc()}")
    
    if out["errors"]:
        logger.error("DIAG MODELS ERRORS:\n" + "\n----\n".join(out["errors"]))
    
    return out

@router.get("/auth")
async def diag_auth():
    """Diagnose auth service configuration with wrapped imports."""
    out = {"imports": {}, "errors": []}
    
    try:
        from services.auth_service_async import get_async_auth_service
        out["imports"]["auth_service_async"] = True
        
        try:
            svc = await get_async_auth_service()
            out["service_initialized"] = True
            out["has_get_client"] = hasattr(svc, "get_authenticated_client")
        except Exception as e:
            out["service_initialized"] = False
            out["errors"].append(f"get_async_auth_service() error: {e}\n{traceback.format_exc()}")
            
    except Exception as e:
        out["imports"]["auth_service_async"] = False
        out["errors"].append(f"auth_service_async import error: {e}\n{traceback.format_exc()}")
    
    if out["errors"]:
        logger.error("DIAG AUTH ERRORS:\n" + "\n----\n".join(out["errors"]))
    
    return out

@router.get("/env")
def diag_env():
    """Check critical environment variables (masked for security)."""
    import os
    critical_vars = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY", 
        "SUPABASE_SERVICE_ROLE_KEY",
        "JWT_SECRET",
        "FAL_KEY",
        "CORS_ORIGINS",
        "ENVIRONMENT",
        "DATABASE_URL",
        "PYTHONPATH"
    ]
    
    out = {}
    for var in critical_vars:
        val = os.getenv(var)
        if val:
            # Mask sensitive values
            if "KEY" in var or "SECRET" in var or "PASSWORD" in var:
                out[var] = f"***{val[-4:]}" if len(val) > 4 else "****"
            else:
                out[var] = val[:50] + "..." if len(val) > 50 else val
        else:
            out[var] = None
    
    return {"environment": out}

@router.get("/echo-error")
def echo_error():
    """Test endpoint to verify global exception handler and CORS on 500s."""
    raise RuntimeError("intentional test error for diagnostics")