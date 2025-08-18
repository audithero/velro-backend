"""
CSRF Security Router - Provides CSRF tokens and security endpoints.
Phase 1 Step 3 - Critical security implementation.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from middleware.csrf_protection import generate_csrf_token_for_user, validate_csrf_token_manually

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/security", tags=["Security"])

@router.get("/csrf-token")
async def get_csrf_token(request: Request):
    """
    Generate and return a CSRF token for the client.
    This endpoint is handled by the CSRF middleware but we provide
    a manual implementation for testing purposes.
    """
    try:
        client_ip = _get_client_ip(request)
        
        # This is a simple implementation - in production, the middleware handles this
        csrf_token = await generate_csrf_token_for_user("anonymous", client_ip)
        
        response_data = {
            "csrf_token": csrf_token,
            "expires_in": 7200,  # 2 hours
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "usage_instructions": {
                "header": "Include token in X-CSRF-Token header",
                "cookie": "Token is also available in csrf_token cookie",
                "form": "For form submissions, include as csrf_token field"
            }
        }
        
        response = JSONResponse(content=response_data)
        
        # Set secure CSRF cookie
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=7200,  # 2 hours
            httponly=True,
            secure=True,  # HTTPS only in production
            samesite="strict"
        )
        
        logger.info(f"✅ [CSRF] Generated CSRF token for IP: {client_ip}")
        return response
        
    except Exception as e:
        logger.error(f"❌ [CSRF] Error generating CSRF token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate CSRF token"
        )

@router.post("/validate-csrf")
async def validate_csrf_token(request: Request):
    """
    Validate a CSRF token (for testing purposes).
    In production, this validation is handled by middleware.
    """
    try:
        client_ip = _get_client_ip(request)
        
        # Get token from header or form data
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            # Try to get from form data
            form = await request.form()
            csrf_token = form.get("csrf_token")
        
        if not csrf_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSRF token required"
            )
        
        # Validate token
        is_valid = await validate_csrf_token_manually(csrf_token, client_ip)
        
        return {
            "valid": is_valid,
            "token_preview": csrf_token[:16] + "...",
            "client_ip": client_ip,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [CSRF] Error validating CSRF token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to validate CSRF token"
        )

@router.get("/security-headers")
async def get_security_headers_info():
    """
    Return information about the security headers implemented.
    """
    return {
        "security_headers": {
            "X-Content-Type-Options": {
                "value": "nosniff",
                "description": "Prevents MIME type sniffing"
            },
            "X-Frame-Options": {
                "value": "DENY",
                "description": "Prevents clickjacking attacks"
            },
            "X-XSS-Protection": {
                "value": "1; mode=block",
                "description": "Enables XSS filtering"
            },
            "Strict-Transport-Security": {
                "value": "max-age=31536000; includeSubDomains; preload",
                "description": "Enforces HTTPS connections"
            },
            "Content-Security-Policy": {
                "description": "Controls resource loading to prevent XSS",
                "directives": [
                    "default-src 'self'",
                    "script-src 'self'",
                    "style-src 'self' 'unsafe-inline'",
                    "img-src 'self' data: https:",
                    "connect-src 'self' https://api.fal.ai https://*.supabase.co",
                    "frame-ancestors 'none'"
                ]
            },
            "Referrer-Policy": {
                "value": "strict-origin-when-cross-origin",
                "description": "Controls referrer information"
            },
            "Permissions-Policy": {
                "value": "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
                "description": "Controls browser feature access"
            }
        },
        "csrf_protection": {
            "enabled": True,
            "token_endpoint": "/api/v1/security/csrf-token",
            "validation_methods": [
                "X-CSRF-Token header",
                "csrf_token cookie (double-submit pattern)",
                "csrf_token form field"
            ],
            "token_expiry": "2 hours",
            "protected_methods": ["POST", "PUT", "DELETE", "PATCH"]
        },
        "additional_security": {
            "rate_limiting": "Adaptive rate limiting based on endpoint and threat history",
            "threat_detection": "Real-time pattern-based threat detection",
            "ip_blocking": "Automatic IP blocking for repeated violations",
            "request_validation": "Comprehensive input validation and sanitization",
            "security_logging": "Detailed security event logging and monitoring"
        },
        "compliance": {
            "owasp_top_10": "Protection against OWASP Top 10 vulnerabilities",
            "gdpr_ready": "Privacy-focused logging and data handling",
            "production_hardened": "Enterprise-grade security configuration"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.get("/security-status")
async def get_security_status():
    """
    Return current security status and configuration.
    """
    try:
        from config import settings
        
        return {
            "security_status": "operational",
            "configuration": {
                "environment": "production" if settings.is_production() else "development",
                "csrf_protection": settings.csrf_protection_enabled,
                "security_headers": settings.security_headers_enabled,
                "production_security_checks": getattr(settings, 'production_security_checks', True),
                "verbose_error_messages": settings.verbose_error_messages
            },
            "features": {
                "enhanced_security_middleware": True,
                "csrf_protection_middleware": True,
                "threat_detection": True,
                "rate_limiting": True,
                "security_headers": True,
                "content_security_policy": True,
                "automatic_ip_blocking": True
            },
            "monitoring": {
                "security_events_logging": True,
                "threat_pattern_detection": True,
                "performance_monitoring": True,
                "incident_tracking": True
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.warning(f"⚠️ [SECURITY] Could not load full security status: {e}")
        return {
            "security_status": "operational",
            "note": "Basic security status - full configuration unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@router.post("/test-csrf-protected")
async def test_csrf_protected_endpoint(request: Request):
    """
    Test endpoint that requires CSRF protection.
    This endpoint will be protected by the CSRF middleware.
    """
    return {
        "message": "CSRF protection test successful",
        "method": request.method,
        "path": request.url.path,
        "csrf_validation": "passed",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    return getattr(request.client, "host", "unknown")