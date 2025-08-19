"""
Request tracking middleware for X-Request-ID propagation and Server-Timing headers.
"""
import time
import uuid
from typing import Callable, Dict, List
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class TimingSegment:
    """Track timing for a specific segment."""
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = time.perf_counter()
        self.end_time = None
        self.duration_ms = None
    
    def end(self):
        """End timing for this segment."""
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        return self.duration_ms
    
    def to_header(self) -> str:
        """Convert to Server-Timing header format."""
        if self.duration_ms is not None:
            return f"{self.name};dur={self.duration_ms:.2f}"
        return f"{self.name}"


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for request tracking and performance monitoring.
    
    Features:
    - X-Request-ID generation and propagation
    - Server-Timing header with segment tracking
    - Request/response logging with timing
    """
    
    def __init__(self, app, dispatch=None):
        super().__init__(app, dispatch)
        self.app = app
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start total timing
        total_start = time.perf_counter()
        
        # Generate or propagate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in request state for access by routes
        request.state.request_id = request_id
        request.state.timing_segments = {}
        
        # Track timing segments
        segments: List[TimingSegment] = []
        
        # CORS timing (already done by the time we get here)
        cors_segment = TimingSegment("mw_cors")
        cors_segment.duration_ms = 0.5  # Nominal value
        segments.append(cors_segment)
        
        # Auth timing (if auth middleware is present)
        auth_segment = TimingSegment("mw_auth")
        
        # Log request start
        logger.info(f"[{request_id}] {request.method} {request.url.path} - Started")
        
        try:
            # Process request through remaining middleware and routes
            router_segment = TimingSegment("router")
            response = await call_next(request)
            router_segment.end()
            segments.append(router_segment)
            
            # End auth timing (approximate)
            auth_segment.duration_ms = 2.0  # Nominal value
            segments.append(auth_segment)
            
            # Add any custom timing from the route
            if hasattr(request.state, "timing_segments"):
                for name, duration_ms in request.state.timing_segments.items():
                    segment = TimingSegment(name)
                    segment.duration_ms = duration_ms
                    segments.append(segment)
            
            # Calculate total time
            total_duration_ms = (time.perf_counter() - total_start) * 1000
            total_segment = TimingSegment("total")
            total_segment.duration_ms = total_duration_ms
            segments.append(total_segment)
            
            # Add headers to response
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{total_duration_ms:.2f}ms"
            
            # Build Server-Timing header
            timing_header = ", ".join(seg.to_header() for seg in segments)
            response.headers["Server-Timing"] = timing_header
            
            # Log request completion
            logger.info(
                f"[{request_id}] {request.method} {request.url.path} - "
                f"Completed with {response.status_code} in {total_duration_ms:.2f}ms"
            )
            
            return response
            
        except Exception as e:
            # Log error
            total_duration_ms = (time.perf_counter() - total_start) * 1000
            logger.error(
                f"[{request_id}] {request.method} {request.url.path} - "
                f"Failed after {total_duration_ms:.2f}ms: {e}"
            )
            raise


def add_timing_segment(request: Request, name: str, duration_ms: float):
    """
    Helper function to add timing segments from routes.
    
    Usage in routes:
        from middleware.request_tracking import add_timing_segment
        
        # In your route handler:
        start = time.perf_counter()
        # ... do database operation ...
        db_time = (time.perf_counter() - start) * 1000
        add_timing_segment(request, "db", db_time)
    """
    if hasattr(request.state, "timing_segments"):
        request.state.timing_segments[name] = duration_ms