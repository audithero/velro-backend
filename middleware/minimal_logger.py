"""
Minimal request logger middleware.
Adds request ID, logs basic info, tracks timing.
"""
import time
import uuid
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class MinimalLoggerMiddleware(BaseHTTPMiddleware):
    """Minimal logging middleware that always runs."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Track timing
        start_time = time.time()
        
        # Log request
        logger.info(
            f"[{request_id}] → {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Add request ID to response
            response.headers["X-Request-ID"] = request_id
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log response
            logger.info(
                f"[{request_id}] ← {response.status_code} "
                f"in {duration_ms:.2f}ms"
            )
            
            # Add timing header
            response.headers["Server-Timing"] = f"total;dur={duration_ms:.2f}"
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[{request_id}] ✗ Error after {duration_ms:.2f}ms: {e}"
            )
            raise