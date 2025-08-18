"""
Middleware utility functions for performance optimization and monitoring.
Provides fastpath detection, timing logs, and bypass coordination.
"""
import time
import logging
from typing import Dict, List, Optional, Any
from fastapi import Request

logger = logging.getLogger(__name__)

# Auth endpoints that should use fastpath processing
FASTPATH_PREFIXES = (
    '/api/v1/auth/',
    '/auth/',
    '/api/v1/public/',
    '/health',
    '/metrics',
    '/__version',
    '/__health'
)

# Timing thresholds for different middleware (in milliseconds)
MIDDLEWARE_TIMING_THRESHOLDS = {
    'fastlane_auth': 5,
    'production_optimized': 10,
    'access_control': 15,
    'ssrf_protection': 20,
    'security_enhanced': 25,
    'csrf_protection': 10,
    'rate_limiting': 30,
    'secure_design': 15,
    'default': 10
}

# Global middleware performance tracking
middleware_performance_stats = {}

def is_fastpath(request: Request) -> bool:
    """
    Check if request should use fastpath processing.
    
    Args:
        request: FastAPI request object
        
    Returns:
        True if request should use fastpath, False otherwise
    """
    # Check if FastlaneAuthMiddleware marked this as fastlane
    if hasattr(request.state, 'is_fastlane') and request.state.is_fastlane:
        return True
    
    # Check path-based fastpath
    path = request.url.path
    is_fast = any(path.startswith(prefix) for prefix in FASTPATH_PREFIXES)
    
    if not is_fast:
        # Check config-based fastpath
        try:
            from config import settings
            fastpath_paths = getattr(settings, 'fastpath_exempt_paths', [])
            
            # Check exact matches first (most common case)
            if path in fastpath_paths:
                return True
            
            # Check prefix matches for parameterized endpoints
            for exempt_path in fastpath_paths:
                if path.startswith(exempt_path.rstrip("/*")):
                    return True
                    
        except Exception as e:
            logger.debug(f"Config fastpath check failed: {e}")
    
    return is_fast

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
    Log middleware processing time for performance monitoring and track statistics.
    
    Args:
        request: FastAPI request object
        middleware_name: Name of the middleware
        duration_ms: Processing time in milliseconds
    """
    # Update performance statistics
    if middleware_name not in middleware_performance_stats:
        middleware_performance_stats[middleware_name] = {
            'total_requests': 0,
            'total_time_ms': 0,
            'max_time_ms': 0,
            'slow_requests': 0
        }
    
    stats = middleware_performance_stats[middleware_name]
    stats['total_requests'] += 1
    stats['total_time_ms'] += duration_ms
    stats['max_time_ms'] = max(stats['max_time_ms'], duration_ms)
    
    # Get threshold for this middleware
    threshold = MIDDLEWARE_TIMING_THRESHOLDS.get(middleware_name, MIDDLEWARE_TIMING_THRESHOLDS['default'])
    
    # Log and track slow requests
    if duration_ms > threshold:
        stats['slow_requests'] += 1
        logger.warning(
            f"[MIDDLEWARE-TIMING] {middleware_name} took {duration_ms:.2f}ms "
            f"for {request.method} {request.url.path} (threshold: {threshold}ms)"
        )
    elif duration_ms > 5:  # Debug log moderate timing
        logger.debug(
            f"[MIDDLEWARE-TIMING] {middleware_name}: {duration_ms:.2f}ms "
            f"for {request.method} {request.url.path}"
        )

def should_bypass_heavy_middleware(request: Request) -> bool:
    """
    Check if heavy middleware should be bypassed for this request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        True if heavy middleware should be bypassed
    """
    # Check for fastlane bypass flag
    if hasattr(request.state, 'bypass_heavy_middleware') and request.state.bypass_heavy_middleware:
        return True
        
    return is_fastpath(request)

def is_auth_endpoint(request: Request) -> bool:
    """
    Check if request is for an authentication endpoint.
    
    Args:
        request: FastAPI request object
        
    Returns:
        True if request is for auth endpoint
    """
    path = request.url.path
    return path.startswith('/api/v1/auth/') or path.startswith('/auth/')

def log_auth_performance_warning(request: Request, total_time_ms: float):
    """
    Log performance warnings specifically for auth endpoints.
    
    Args:
        request: FastAPI request object
        total_time_ms: Total processing time in milliseconds
    """
    if not is_auth_endpoint(request):
        return
    
    path = request.url.path
    
    if total_time_ms > 1500:  # 1.5 second target
        logger.error(
            f"🚨 [AUTH-PERFORMANCE] CRITICAL: {path} took {total_time_ms:.0f}ms "
            f"(target: <1500ms, optimal: <500ms)"
        )
    elif total_time_ms > 500:  # 500ms optimal
        logger.warning(
            f"⚠️ [AUTH-PERFORMANCE] SLOW: {path} took {total_time_ms:.0f}ms "
            f"(target: <1500ms, optimal: <500ms)"
        )
    elif total_time_ms > 100:  # 100ms good
        logger.info(
            f"ℹ️ [AUTH-PERFORMANCE] OK: {path} took {total_time_ms:.0f}ms "
            f"(target: <1500ms, optimal: <500ms)"
        )

def get_middleware_performance_stats() -> Dict[str, Any]:
    """
    Get comprehensive middleware performance statistics.
    
    Returns:
        Dictionary containing performance statistics for all middleware
    """
    stats = {}
    
    for middleware_name, data in middleware_performance_stats.items():
        avg_time = data['total_time_ms'] / max(data['total_requests'], 1)
        slow_percentage = (data['slow_requests'] / max(data['total_requests'], 1)) * 100
        
        stats[middleware_name] = {
            'total_requests': data['total_requests'],
            'avg_time_ms': round(avg_time, 2),
            'max_time_ms': round(data['max_time_ms'], 2),
            'slow_requests': data['slow_requests'],
            'slow_percentage': round(slow_percentage, 2),
            'threshold_ms': MIDDLEWARE_TIMING_THRESHOLDS.get(
                middleware_name, 
                MIDDLEWARE_TIMING_THRESHOLDS['default']
            )
        }
    
    return stats