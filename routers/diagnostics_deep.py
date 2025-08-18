"""
Deep diagnostic router for debugging CORS and request handling issues.
This router provides detailed information about the request, environment, and middleware stack.
"""
import sys
import os
import time
import json
import inspect
import traceback
from typing import Dict, Any, List
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import platform

router = APIRouter(prefix="/api/v1/diagnostic", tags=["Deep Diagnostics"])


@router.get("/request-info")
async def get_request_info(request: Request):
    """Show everything about the incoming request."""
    return {
        "timestamp": time.time(),
        "request": {
            "method": request.method,
            "url": str(request.url),
            "base_url": str(request.base_url),
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
            "path_params": dict(request.path_params),
            "client": {
                "host": request.client.host if request.client else None,
                "port": request.client.port if request.client else None,
            },
            "scope_type": request.scope.get("type"),
            "scope_scheme": request.scope.get("scheme"),
            "scope_root_path": request.scope.get("root_path"),
            "scope_server": request.scope.get("server"),
        }
    }


@router.get("/environment")
async def get_environment_info():
    """Show environment and configuration details."""
    # Get environment variables (exclude secrets)
    safe_env = {}
    for key, value in os.environ.items():
        if any(secret in key.upper() for secret in ["SECRET", "KEY", "PASSWORD", "TOKEN"]):
            safe_env[key] = f"***{value[-4:]}" if len(value) > 4 else "***"
        else:
            safe_env[key] = value
    
    return {
        "timestamp": time.time(),
        "python": {
            "version": sys.version,
            "version_info": sys.version_info._asdict() if hasattr(sys.version_info, '_asdict') else str(sys.version_info),
            "executable": sys.executable,
            "path": sys.path,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_implementation": platform.python_implementation(),
        },
        "process": {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "uid": os.getuid() if hasattr(os, 'getuid') else None,
            "gid": os.getgid() if hasattr(os, 'getgid') else None,
        },
        "environment": safe_env,
        "railway_specific": {
            "railway_environment": os.getenv("RAILWAY_ENVIRONMENT"),
            "railway_deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID"),
            "railway_service_name": os.getenv("RAILWAY_SERVICE_NAME"),
            "railway_project_id": os.getenv("RAILWAY_PROJECT_ID"),
            "railway_replica_id": os.getenv("RAILWAY_REPLICA_ID"),
            "port": os.getenv("PORT"),
        }
    }


@router.get("/middleware-stack")
async def get_middleware_stack(request: Request):
    """Show the middleware stack and configuration."""
    # Can't import app from main due to circular import
    # Instead, use request.app to get the app instance
    app = request.app
    
    middleware_info = []
    
    # Get middleware stack
    for middleware in app.middleware:
        try:
            mw_info = {
                "class": middleware.__class__.__name__,
                "module": middleware.__class__.__module__,
            }
            
            # Try to get middleware configuration
            if hasattr(middleware, 'kwargs'):
                mw_info["config"] = str(middleware.kwargs)
            elif hasattr(middleware, 'options'):
                mw_info["config"] = str(middleware.options)
                
            middleware_info.append(mw_info)
        except Exception as e:
            middleware_info.append({
                "class": str(middleware),
                "error": str(e)
            })
    
    # Get app configuration
    app_info = {
        "title": app.title,
        "version": app.version,
        "debug": app.debug,
        "routes_count": len(app.routes),
        "exception_handlers": list(app.exception_handlers.keys()),
    }
    
    return {
        "timestamp": time.time(),
        "middleware_stack": middleware_info,
        "middleware_count": len(middleware_info),
        "app_info": app_info,
    }


@router.get("/cors-test")
async def test_cors_configuration(request: Request):
    """Test CORS configuration and show what headers would be added."""
    origin = request.headers.get("origin", "no-origin-header")
    
    # Get CORS configuration from environment
    cors_origins_env = os.getenv("CORS_ORIGINS", "[]")
    
    # Try to parse CORS origins
    cors_origins = []
    try:
        cors_origins = json.loads(cors_origins_env)
    except:
        # Try CSV format
        cors_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    
    # Check if origin is allowed
    origin_allowed = origin in cors_origins or "*" in cors_origins
    
    return {
        "timestamp": time.time(),
        "request_origin": origin,
        "configured_origins": cors_origins,
        "origin_allowed": origin_allowed,
        "cors_env_var": cors_origins_env,
        "expected_headers": {
            "Access-Control-Allow-Origin": origin if origin_allowed else None,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
    }


@router.get("/trace-request")
async def trace_request_flow(request: Request):
    """Trace the request through all layers with timing."""
    trace_points = []
    start_time = time.time()
    
    # Record entry point
    trace_points.append({
        "point": "router_entry",
        "timestamp": time.time() - start_time,
        "headers": dict(request.headers),
    })
    
    # Try to access various services to see where failures occur
    results = {}
    
    # Test 1: Can we import middleware?
    try:
        from middleware.auth import get_current_user
        results["import_auth_middleware"] = "success"
    except Exception as e:
        results["import_auth_middleware"] = f"failed: {str(e)}"
    
    # Test 2: Can we import services?
    try:
        from services.user_service import user_service
        results["import_user_service"] = "success"
    except Exception as e:
        results["import_user_service"] = f"failed: {str(e)}"
    
    # Test 3: Can we access database?
    try:
        from database import SupabaseClient
        client = SupabaseClient()
        results["database_client_creation"] = "success"
        results["database_available"] = client.is_available()
    except Exception as e:
        results["database_client_creation"] = f"failed: {str(e)}"
    
    # Test 4: Check Redis
    try:
        redis_url = os.getenv("REDIS_URL")
        results["redis_url_present"] = bool(redis_url)
        if redis_url:
            from redis import Redis
            redis_client = Redis.from_url(redis_url, socket_connect_timeout=1)
            redis_client.ping()
            results["redis_connection"] = "success"
    except Exception as e:
        results["redis_connection"] = f"failed: {str(e)}"
    
    trace_points.append({
        "point": "tests_complete",
        "timestamp": time.time() - start_time,
        "results": results,
    })
    
    return {
        "total_time_ms": (time.time() - start_time) * 1000,
        "trace_points": trace_points,
        "test_results": results,
    }


@router.get("/error-test/{error_code}")
async def test_error_response(error_code: int, request: Request):
    """Test how different error codes are handled."""
    origin = request.headers.get("origin", "no-origin-header")
    
    if error_code == 401:
        raise HTTPException(status_code=401, detail="Test unauthorized error")
    elif error_code == 403:
        raise HTTPException(status_code=403, detail="Test forbidden error")
    elif error_code == 404:
        raise HTTPException(status_code=404, detail="Test not found error")
    elif error_code == 422:
        raise HTTPException(status_code=422, detail="Test validation error")
    elif error_code == 500:
        raise Exception("Test internal server error")
    else:
        return {
            "message": f"No error raised for code {error_code}",
            "origin_header": origin,
        }


@router.get("/working-endpoint")
async def working_endpoint():
    """A simple endpoint that should always work."""
    return {"status": "ok", "timestamp": time.time()}


@router.get("/auth-required-endpoint")
async def auth_required_endpoint(request: Request):
    """An endpoint that requires authentication to test auth flow."""
    from middleware.auth import get_current_user
    from fastapi import Depends
    
    # This will trigger auth middleware
    try:
        # Try to get the auth dependency
        auth_header = request.headers.get("authorization", "")
        return {
            "auth_header_present": bool(auth_header),
            "auth_header_length": len(auth_header),
            "message": "If you see this, the endpoint was reached",
        }
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


@router.options("/cors-preflight-test")
async def cors_preflight_test():
    """Test OPTIONS preflight handling."""
    return {"message": "OPTIONS request handled"}


@router.get("/response-header-test")
async def response_header_test(response: Response):
    """Test if we can manually set response headers."""
    response.headers["X-Custom-Header"] = "test-value"
    response.headers["Access-Control-Allow-Origin"] = "manual-origin-test"
    return {
        "message": "Response headers manually set",
        "headers_set": {
            "X-Custom-Header": "test-value",
            "Access-Control-Allow-Origin": "manual-origin-test"
        }
    }


@router.get("/find-breaking-point")
async def find_breaking_point(request: Request):
    """Try to identify exactly where things break."""
    results = []
    
    # Step 1: Basic request info
    results.append({
        "step": "basic_request",
        "success": True,
        "data": {
            "method": request.method,
            "path": str(request.url.path),
            "headers_count": len(request.headers),
        }
    })
    
    # Step 2: Check imports
    try:
        import fastapi
        import starlette
        results.append({
            "step": "import_frameworks",
            "success": True,
            "data": {
                "fastapi_version": fastapi.__version__,
                "starlette_version": starlette.__version__,
            }
        })
    except Exception as e:
        results.append({
            "step": "import_frameworks",
            "success": False,
            "error": str(e)
        })
    
    # Step 3: Check middleware imports
    middleware_imports = [
        "middleware.auth",
        "middleware.production_rate_limiter",
        "middleware.access_control",
        "middleware.ssrf_protection",
    ]
    
    for mw in middleware_imports:
        try:
            __import__(mw)
            results.append({
                "step": f"import_{mw}",
                "success": True,
            })
        except Exception as e:
            results.append({
                "step": f"import_{mw}",
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
    
    # Step 4: Check router imports
    router_imports = [
        "routers.auth",
        "routers.credits", 
        "routers.projects",
        "routers.generations",
    ]
    
    for rt in router_imports:
        try:
            __import__(rt)
            results.append({
                "step": f"import_{rt}",
                "success": True,
            })
        except Exception as e:
            results.append({
                "step": f"import_{rt}",
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
    
    # Step 5: Check if we can create a response
    try:
        test_response = JSONResponse(
            content={"test": "response"},
            headers={"X-Test": "header"}
        )
        results.append({
            "step": "create_json_response",
            "success": True,
        })
    except Exception as e:
        results.append({
            "step": "create_json_response",
            "success": False,
            "error": str(e)
        })
    
    # Find the first failure
    first_failure = next((r for r in results if not r.get("success")), None)
    
    return {
        "all_results": results,
        "first_failure": first_failure,
        "total_steps": len(results),
        "successful_steps": sum(1 for r in results if r.get("success")),
    }