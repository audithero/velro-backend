"""
FastlaneAuthMiddleware - Minimal middleware stack for auth endpoints.
Bypasses heavy middleware operations for /api/v1/auth/* routes.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
import logging

logger = logging.getLogger(__name__)

AUTH_PREFIXES = ("/api/v1/auth/", "/auth/", "/api/v1/public/", "/health", "/metrics", "/__")
FASTLANE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin"
}

class FastlaneAuthMiddleware(BaseHTTPMiddleware):
    """
    Ultra-lightweight middleware that runs FIRST.
    Bypasses heavy middleware for auth routes while maintaining essential security.
    """
    
    async def dispatch(self, request, call_next):
        path = request.url.path
        
        # OPTIONS requests should always pass through quickly for CORS
        if request.method == "OPTIONS":
            request.state.is_fastlane = True
            return await call_next(request)
        
        # Check if this is a fastlane route
        if any(path.startswith(p) for p in AUTH_PREFIXES):
            start_time = time.perf_counter()
            
            # Mark request as fastlane for downstream middleware to skip
            request.state.is_fastlane = True
            
            # Process with minimal overhead
            response: Response = await call_next(request)
            
            # Add essential security headers (cheap operations only)
            for header, value in FASTLANE_HEADERS.items():
                response.headers.setdefault(header, value)
            
            # Add timing header for monitoring
            elapsed = (time.perf_counter() - start_time) * 1000
            response.headers["X-Fastlane-Time-Ms"] = f"{elapsed:.2f}"
            response.headers["X-Request-Path"] = "auth-fastlane"
            
            # Log only if slow (>100ms)
            if elapsed > 100:
                logger.warning(f"⚡ [FASTLANE] {path} took {elapsed:.2f}ms")
            
            return response
        
        # Non-fastlane routes go through normal middleware chain
        request.state.is_fastlane = False
        return await call_next(request)