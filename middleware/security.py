"""
Security middleware for comprehensive security controls and monitoring.
Implements OWASP security best practices and production hardening.
"""
import logging
import time
import hashlib
from datetime import datetime, timezone
from typing import Callable, Dict, Set
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from utils.cache_manager import cache_manager, CacheLevel
from config import settings

logger = logging.getLogger(__name__)

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive security middleware implementing:
    - Security headers (OWASP recommendations)
    - Rate limiting per IP and endpoint
    - Request validation and sanitization  
    - Security incident detection and logging
    - Production environment validation
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.blocked_ips: Set[str] = set()
        self.suspicious_patterns = [
            # Common attack patterns
            'union select', 'script>', 'javascript:', 'vbscript:',
            '../', '..\\', '/etc/passwd', '/etc/shadow',
            'cmd.exe', 'powershell', 'bash', '/bin/sh',
            'eval(', 'exec(', 'system(', 'shell_exec(',
            # XSS patterns
            '<script', '</script>', 'onerror=', 'onload=',
            # SQLi patterns  
            "' or '1'='1", '" or "1"="1', '1=1--', '1=1#'
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with comprehensive security checks."""
        start_time = time.time()
        
        # Get client IP (handle proxy headers)
        client_ip = self._get_client_ip(request)
        path = request.url.path
        method = request.method
        
        try:
            # Security Check 1: IP blocking
            if client_ip in self.blocked_ips:
                logger.warning(f"🚫 [SECURITY] Blocked IP attempted access: {client_ip}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            
            # Security Check 2: Rate limiting
            await self._check_rate_limits(client_ip, path)
            
            # Security Check 3: Request validation
            await self._validate_request(request, client_ip)
            
            # Security Check 4: Production environment validation
            if settings.is_production():
                await self._validate_production_request(request)
            
            # Process request
            response = await call_next(request)
            
            # Add security headers
            response = self._add_security_headers(response)
            
            # Log successful request
            processing_time = time.time() - start_time
            logger.debug(f"✅ [SECURITY] {method} {path} - {response.status_code} - {processing_time:.3f}s - IP: {client_ip}")
            
            return response
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Log unexpected errors
            logger.error(f"❌ [SECURITY] Unexpected error processing {method} {path}: {e}")
            await self._log_security_incident("MIDDLEWARE_ERROR", request, {"error": str(e)})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP considering proxy headers."""
        # Check common proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fallback to direct connection
        client_host = getattr(request.client, "host", "unknown")
        return client_host
    
    async def _check_rate_limits(self, client_ip: str, path: str):
        """Implement rate limiting per IP and endpoint."""
        try:
            # Global rate limit: 1000 requests per hour per IP
            global_key = f"rate_limit:global:{client_ip}"
            global_count = await cache_manager.get(global_key, CacheLevel.L1_MEMORY) or 0
            
            if global_count > 1000:
                await self._handle_rate_limit_exceeded(client_ip, "GLOBAL_RATE_LIMIT")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "3600"}
                )
            
            # Endpoint-specific rate limits
            endpoint_limits = {
                "/api/v1/auth/login": 10,      # 10 login attempts per hour
                "/api/v1/auth/register": 5,    # 5 registrations per hour
                "/api/v1/generations": 100,    # 100 generations per hour
            }
            
            for endpoint, limit in endpoint_limits.items():
                if path.startswith(endpoint):
                    endpoint_key = f"rate_limit:endpoint:{client_ip}:{endpoint}"
                    endpoint_count = await cache_manager.get(endpoint_key, CacheLevel.L1_MEMORY) or 0
                    
                    if endpoint_count > limit:
                        await self._handle_rate_limit_exceeded(client_ip, f"ENDPOINT_RATE_LIMIT:{endpoint}")
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Rate limit exceeded for {endpoint}",
                            headers={"Retry-After": "3600"}
                        )
                    
                    await cache_manager.set(endpoint_key, endpoint_count + 1, CacheLevel.L1_MEMORY, ttl=3600)
                    break
            
            # Update global counter
            await cache_manager.set(global_key, global_count + 1, CacheLevel.L1_MEMORY, ttl=3600)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ [SECURITY] Rate limiting error: {e}")
            # Continue processing if rate limiting fails
    
    async def _validate_request(self, request: Request, client_ip: str):
        """Validate request for malicious patterns."""
        try:
            # Check URL path for suspicious patterns
            path = request.url.path.lower()
            query = str(request.url.query).lower() if request.url.query else ""
            
            for pattern in self.suspicious_patterns:
                if pattern in path or pattern in query:
                    await self._log_security_incident(
                        "MALICIOUS_PATTERN_DETECTED",
                        request,
                        {
                            "pattern": pattern,
                            "in_path": pattern in path,
                            "in_query": pattern in query
                        }
                    )
                    
                    # Consider blocking the IP after multiple violations
                    await self._track_security_violation(client_ip)
                    
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Bad request"
                    )
            
            # Check headers for suspicious content
            user_agent = request.headers.get("User-Agent", "").lower()
            if any(pattern in user_agent for pattern in ["sqlmap", "nmap", "nikto", "dirb"]):
                await self._log_security_incident(
                    "SECURITY_SCANNER_DETECTED", 
                    request,
                    {"user_agent": user_agent}
                )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,  
                    detail="Access denied"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ [SECURITY] Request validation error: {e}")
    
    async def _validate_production_request(self, request: Request):
        """Additional validation for production environment."""
        # Block access to development endpoints in production
        dev_paths = ["/api/v1/debug", "/docs", "/redoc", "/openapi.json"]
        path = request.url.path
        
        for dev_path in dev_paths:
            if path.startswith(dev_path):
                await self._log_security_incident(
                    "DEV_ENDPOINT_ACCESS_IN_PRODUCTION",
                    request,
                    {"attempted_path": path}
                )
                
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Not found"  # Hide existence of dev endpoints
                )
    
    def _add_security_headers(self, response: Response) -> Response:
        """Add comprehensive security headers."""
        headers = settings.get_security_headers()
        
        # Add all configured security headers
        for header, value in headers.items():
            if value is not None:  # Only add headers with values
                response.headers[header] = value
        
        # Additional security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        # CSP header for additional XSS protection
        if settings.is_production():
            csp_policy = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://api.fal.ai https://*.supabase.co; "
                "frame-ancestors 'none';"
            )
            response.headers["Content-Security-Policy"] = csp_policy
        
        return response
    
    async def _track_security_violation(self, client_ip: str):
        """Track security violations per IP and block if necessary."""
        try:
            violation_key = f"security_violations:{client_ip}"
            violations = await cache_manager.get(violation_key, CacheLevel.L1_MEMORY) or 0
            violations += 1
            
            await cache_manager.set(violation_key, violations, CacheLevel.L1_MEMORY, ttl=3600)
            
            # Block IP after 5 violations in an hour
            if violations >= 5:
                self.blocked_ips.add(client_ip)
                await self._log_security_incident(
                    "IP_BLOCKED_FOR_VIOLATIONS",
                    None,
                    {"client_ip": client_ip, "violation_count": violations}
                )
                logger.error(f"🚫 [SECURITY] IP blocked for repeated violations: {client_ip}")
                
        except Exception as e:
            logger.warning(f"⚠️ [SECURITY] Error tracking violations: {e}")
    
    async def _handle_rate_limit_exceeded(self, client_ip: str, limit_type: str):
        """Handle rate limit exceeded events."""
        await self._log_security_incident(
            "RATE_LIMIT_EXCEEDED",
            None,
            {"client_ip": client_ip, "limit_type": limit_type}
        )
        
        # Track as security violation
        await self._track_security_violation(client_ip)
    
    async def _log_security_incident(self, incident_type: str, request: Request = None, additional_data: Dict = None):
        """Log security incidents for monitoring and analysis."""
        try:
            incident = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "incident_type": incident_type,
                "severity": self._get_incident_severity(incident_type),
                "client_ip": self._get_client_ip(request) if request else additional_data.get("client_ip", "unknown"),
                "user_agent": request.headers.get("User-Agent") if request else "unknown",
                "path": request.url.path if request else "unknown",
                "method": request.method if request else "unknown",
                "headers": dict(request.headers) if request else {},
                "additional_data": additional_data or {}
            }
            
            # Store incident
            incident_key = f"security_incident:{incident['timestamp']}:{hashlib.md5(str(incident).encode()).hexdigest()[:8]}"
            await cache_manager.set(
                incident_key, 
                incident, 
                CacheLevel.L2_PERSISTENT, 
                ttl=86400 * 30  # 30 days retention
            )
            
            # Log based on severity
            if incident["severity"] == "CRITICAL":
                logger.error(f"🚨 [SECURITY-CRITICAL] {incident_type}: {incident}")
            elif incident["severity"] == "HIGH":
                logger.error(f"⚠️ [SECURITY-HIGH] {incident_type}: {incident}")
            else:
                logger.warning(f"ℹ️ [SECURITY-INFO] {incident_type}: {incident}")
                
        except Exception as e:
            logger.error(f"❌ [SECURITY] Failed to log security incident: {e}")
    
    def _get_incident_severity(self, incident_type: str) -> str:
        """Determine incident severity based on type."""
        critical_incidents = [
            "DEV_TOKEN_IN_PRODUCTION",
            "DEV_ENDPOINT_ACCESS_IN_PRODUCTION", 
            "SECURITY_SCANNER_DETECTED",
            "IP_BLOCKED_FOR_VIOLATIONS"
        ]
        
        high_incidents = [
            "MALICIOUS_PATTERN_DETECTED",
            "RATE_LIMIT_EXCEEDED"
        ]
        
        if incident_type in critical_incidents:
            return "CRITICAL"
        elif incident_type in high_incidents:
            return "HIGH"
        else:
            return "INFO"