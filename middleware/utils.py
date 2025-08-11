"""
Middleware utility functions for performance optimization.
Provides fastpath detection and common middleware helpers.
"""
import logging
from typing import List
from fastapi import Request

logger = logging.getLogger(__name__)

def is_fastpath(request: Request) -> bool:
    """
    Check if request should use fastpath processing (skip heavy middleware).
    
    Fastpath endpoints bypass expensive middleware operations like:
    - Access Control validation
    - SSRF protection scanning
    - Heavy rate limiting checks
    
    Returns True if request path is in FASTPATH_EXEMPT_PATHS config.
    """
    try:
        from config import settings
        fastpath_paths = getattr(settings, 'fastpath_exempt_paths', [])
        
        request_path = request.url.path
        
        # Check exact matches first (most common case)
        if request_path in fastpath_paths:
            logger.debug(f"✅ [FASTPATH] Exact match for {request_path}")
            return True
        
        # Check prefix matches for parameterized endpoints
        for exempt_path in fastpath_paths:
            if request_path.startswith(exempt_path.rstrip("/*")):
                logger.debug(f"✅ [FASTPATH] Prefix match for {request_path} -> {exempt_path}")
                return True
        
        return False
        
    except Exception as e:
        logger.warning(f"⚠️ [FASTPATH] Error checking fastpath: {e}, defaulting to full processing")
        # Fail safe: if we can't determine fastpath, use full processing
        return False

def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request with proper proxy header handling.
    Used by multiple middleware components.
    """
    # Check Railway/proxy headers first
    forwarded_for = request.headers.get('x-forwarded-for')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    real_ip = request.headers.get('x-real-ip')
    if real_ip:
        return real_ip.strip()
    
    # Fallback to client host
    return getattr(request.client, 'host', 'unknown')

def get_request_size(request: Request) -> int:
    """
    Get request content length safely.
    Returns 0 if content-length header is missing or invalid.
    """
    try:
        content_length = request.headers.get('content-length')
        return int(content_length) if content_length else 0
    except (ValueError, TypeError):
        return 0

def is_authenticated_request(request: Request) -> bool:
    """
    Quick check if request has authentication headers.
    Does not validate the token, just checks presence.
    """
    auth_header = request.headers.get('authorization')
    return bool(auth_header and auth_header.startswith('Bearer '))

def should_skip_middleware(request: Request, middleware_name: str) -> tuple[bool, str]:
    """
    Centralized logic to determine if middleware should be skipped.
    
    Returns:
        (should_skip: bool, reason: str)
    """
    # Always process non-fastpath endpoints fully
    if not is_fastpath(request):
        return False, "not_fastpath"
    
    # Different middleware have different fastpath behaviors
    if middleware_name == "access_control":
        # Skip access control for public fastpath endpoints
        return True, "fastpath_public"
    
    elif middleware_name == "security_enhanced":
        # Skip heavy SSRF and input validation for trusted fastpath
        return True, "fastpath_trusted"
    
    elif middleware_name == "rate_limiting":
        # Use lighter rate limiting for fastpath
        return True, "fastpath_light_limits"
    
    return False, "unknown_middleware"

def log_middleware_skip(request: Request, middleware_name: str, reason: str):
    """
    Log when middleware processing is skipped for monitoring.
    """
    logger.debug(
        f"⚡ [FASTPATH] Skipped {middleware_name} for {request.url.path} "
        f"({reason}) - optimizing for <100ms response"
    )

def log_middleware_timing(request: Request, middleware_name: str, duration_ms: float):
    """
    Log middleware processing time for performance monitoring.
    """
    if duration_ms > 50:  # Log slow middleware operations
        logger.warning(
            f"⚠️ [PERF] Slow {middleware_name}: {duration_ms:.1f}ms for {request.url.path}"
        )
    elif duration_ms > 10:  # Debug log moderate timing
        logger.debug(
            f"🔍 [PERF] {middleware_name}: {duration_ms:.1f}ms for {request.url.path}"
        )