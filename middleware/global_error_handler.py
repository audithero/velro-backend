"""
Global error handler middleware that ensures ALL responses have CORS headers and JSON format.
This must be added AFTER CORSMiddleware but BEFORE all other middleware.
"""
import json
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class GlobalErrorMiddleware(BaseHTTPMiddleware):
    """
    Ensures every error response includes:
    - JSON body
    - Access-Control-Allow-Origin header
    - Vary: Origin header
    - X-Request-ID for tracing
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or propagate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Track timing
        start_time = time.perf_counter()
        
        try:
            # Call the next middleware/route
            response = await call_next(request)
            
            # Add request ID to response
            response.headers["X-Request-ID"] = request_id
            
            # Ensure CORS headers on error responses
            origin = request.headers.get("Origin", "")
            if origin and response.status_code >= 400:
                # Check if CORS headers are missing
                if "access-control-allow-origin" not in response.headers:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                    response.headers["Vary"] = "Origin"
            
            # Add timing header
            elapsed = (time.perf_counter() - start_time) * 1000
            response.headers["X-Response-Time"] = f"{elapsed:.2f}ms"
            
            return response
            
        except Exception as e:
            # Log the error with request ID
            logger.exception(f"[{request_id}] Unhandled exception in {request.url.path}: {e}")
            
            # Get origin for CORS
            origin = request.headers.get("Origin", "")
            
            # Create error response
            error_detail = {
                "error": "internal_server_error",
                "detail": str(e) if logger.level <= logging.DEBUG else "Internal server error",
                "request_id": request_id,
                "path": str(request.url.path),
                "method": request.method,
                "timestamp": time.time()
            }
            
            # Create JSON response
            response = JSONResponse(
                content=error_detail,
                status_code=500
            )
            
            # Add CORS headers
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"
            
            # Add diagnostic headers
            response.headers["X-Request-ID"] = request_id
            elapsed = (time.perf_counter() - start_time) * 1000
            response.headers["X-Response-Time"] = f"{elapsed:.2f}ms"
            response.headers["X-Error-Handler"] = "global"
            
            return response