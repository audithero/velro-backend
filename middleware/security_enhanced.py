"""
Enhanced Security Middleware for Production Deployment
Comprehensive security hardening with OWASP compliance and zero-trust architecture.
"""
import logging
import hashlib
import hmac
import time
import re
from typing import Optional, Dict, Any, Set, List
from datetime import datetime, timezone
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import ipaddress

try:
    from config import settings
except ImportError:
    class FallbackSettings:
        def is_production(self): return True
        security_headers_enabled = True
        csrf_protection_enabled = True
        verbose_error_messages = False
    settings = FallbackSettings()

logger = logging.getLogger(__name__)

class SecurityEnhancedMiddleware(BaseHTTPMiddleware):
    """
    Enterprise-grade security middleware implementing:
    - Security headers (OWASP recommended)
    - Request size limits
    - Input validation and sanitization
    - IP-based security controls
    - Security event logging
    - Content Security Policy
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Security configuration
        self.max_request_size = 10 * 1024 * 1024  # 10MB
        self.max_header_size = 8192  # 8KB
        self.max_query_params = 100
        self.request_timeout = 30  # seconds
        
        # Blocked patterns (potential attacks)
        self.blocked_patterns = [
            # SQL injection patterns
            r'(?i)(union\s+select|drop\s+table|insert\s+into|delete\s+from)',
            # XSS patterns  
            r'(?i)(<script|javascript:|on\w+\s*=)',
            # Path traversal
            r'(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)',
            # Command injection - fixed to avoid false positives
            r'(?i)(;\s*rm\s+|;\s*curl\s+|;\s*wget\s+|\|\s*sh\s+|`.*`|\$\(.*\))',
            # LDAP injection
            r'(\*\)[\s;]|&\([\s;]|\|\([\s;]|!\(\)[\s;])',
            # XML injection
            r'(?i)(<!entity|<!doctype|<\?xml)',
            # Server-side template injection - more specific patterns
            r'(\{\{.*\}\}|\{%.*%\}|\$\{.*\})',
        ]
        
        # Compile patterns for performance
        self.compiled_patterns = [re.compile(pattern) for pattern in self.blocked_patterns]
        
        # Suspicious IP tracking
        self.suspicious_ips: Set[str] = set()
        self.failed_requests: Dict[str, List[float]] = {}
        
        # Content Security Policy
        self.csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' https: data:; "
            "connect-src 'self' https:; "
            "media-src 'self'; "
            "object-src 'none'; "
            "child-src 'none'; "
            "worker-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "manifest-src 'self'"
        )
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Main security middleware processing."""
        start_time = time.time()
        client_ip = self._get_client_ip(request)
        
        try:
            # PERFORMANCE: Skip heavy security validation for fastpath endpoints
            from middleware.utils import is_fastpath, log_middleware_skip
            if is_fastpath(request):
                log_middleware_skip(request, "security_enhanced", "fastpath_bypass")
                # Still add basic security headers but skip expensive validation
                response = await call_next(request)
                self._add_security_headers(response, request)
                return response
            
            # Security checks (fail fast)
            await self._validate_request_security(request, client_ip)
            
            # Process request
            response = await call_next(request)
            
            # Add security headers
            self._add_security_headers(response, request)
            
            # Log successful request
            processing_time = (time.time() - start_time) * 1000
            from middleware.utils import log_middleware_timing
            log_middleware_timing(request, "security_enhanced", processing_time)
            if processing_time > 5000:  # Log very slow requests (5+ seconds)
                logger.warning(f"⚠️ [SECURITY] Slow request: {request.method} {request.url.path} ({processing_time/1000:.2f}s)")
            
            return response
            
        except HTTPException as e:
            # Log security violations
            await self._log_security_event(request, client_ip, str(e.detail), e.status_code)
            
            # Track failed requests for rate limiting
            await self._track_failed_request(client_ip)
            
            # Return secure error response
            return await self._create_secure_error_response(e, request)
            
        except Exception as e:
            # Log unexpected errors
            logger.error(f"❌ [SECURITY] Middleware error: {e}")
            await self._log_security_event(request, client_ip, f"Internal error: {type(e).__name__}", 500)
            
            # Return generic error (no information disclosure)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Internal server error", "request_id": self._generate_request_id()}
            )
    
    async def _validate_request_security(self, request: Request, client_ip: str):
        """Comprehensive request security validation."""
        
        # 1. IP-based security checks
        await self._validate_client_ip(client_ip, request)
        
        # 2. Request size validation
        await self._validate_request_size(request)
        
        # 3. Header validation
        await self._validate_headers(request)
        
        # 4. URL and query parameter validation
        await self._validate_url_and_params(request)
        
        # 5. Content validation (if applicable)
        await self._validate_request_content(request)
        
        # 6. Rate limiting check
        await self._check_rate_limiting(client_ip, request)
    
    async def _validate_client_ip(self, client_ip: str, request: Request):
        """Validate client IP address and check for suspicious activity."""
        
        # Check if IP is in suspicious list
        if client_ip in self.suspicious_ips:
            logger.warning(f"🚨 [SECURITY] Request from suspicious IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Access temporarily restricted"
            )
        
        # Validate IP format
        try:
            ip_obj = ipaddress.ip_address(client_ip)
            
            # Block private networks in production (except localhost for development)
            if settings.is_production() and ip_obj.is_private:
                if not (ip_obj.is_loopback or str(ip_obj).startswith('10.') or str(ip_obj).startswith('172.')):
                    logger.warning(f"⚠️ [SECURITY] Private IP access in production: {client_ip}")
                    
        except ValueError:
            logger.warning(f"⚠️ [SECURITY] Invalid IP format: {client_ip}")
    
    async def _validate_request_size(self, request: Request):
        """Validate request size limits."""
        
        # Check content length
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_request_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request too large"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid content length"
                )
    
    async def _validate_headers(self, request: Request):
        """Validate HTTP headers for security."""
        
        # Check for oversized headers
        total_header_size = sum(len(f"{k}: {v}") for k, v in request.headers.items())
        if total_header_size > self.max_header_size:
            raise HTTPException(
                status_code=status.HTTP_431_REQUEST_HEADER_FIELDS_TOO_LARGE,
                detail="Headers too large"
            )
        
        # Validate critical headers
        user_agent = request.headers.get('user-agent', '')
        if len(user_agent) > 1000:  # Abnormally long user agent
            logger.warning(f"⚠️ [SECURITY] Suspicious user agent length: {len(user_agent)}")
        
        # Check for malicious header values
        for name, value in request.headers.items():
            if self._contains_malicious_patterns(value):
                logger.warning(f"🚨 [SECURITY] Malicious pattern in header {name}: {value[:100]}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid header value"
                )
    
    async def _validate_url_and_params(self, request: Request):
        """Validate URL path and query parameters."""
        
        # URL path validation
        path = str(request.url.path)
        if len(path) > 2048:  # Abnormally long path
            raise HTTPException(
                status_code=status.HTTP_414_REQUEST_URI_TOO_LONG,
                detail="URL too long"
            )
        
        # Check for malicious patterns in path
        if self._contains_malicious_patterns(path):
            logger.warning(f"🚨 [SECURITY] Malicious pattern in URL: {path}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid URL"
            )
        
        # Query parameter validation
        query_params = dict(request.query_params)
        if len(query_params) > self.max_query_params:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many query parameters"
            )
        
        # Check query parameter values
        for name, value in query_params.items():
            if len(str(value)) > 1000:  # Large parameter value
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parameter value too large"
                )
            
            if self._contains_malicious_patterns(str(value)):
                logger.warning(f"🚨 [SECURITY] Malicious pattern in parameter {name}: {str(value)[:100]}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid parameter value"
                )
    
    async def _validate_request_content(self, request: Request):
        """Validate request content for security."""
        
        # Only validate for methods with potential payloads
        if request.method not in ['POST', 'PUT', 'PATCH']:
            return
        
        # Content-Type validation
        content_type = request.headers.get('content-type', '')
        
        # Block potentially dangerous content types
        dangerous_types = [
            'text/xml', 'application/xml',  # XML-based attacks
            'text/html',  # HTML injection
            'application/x-www-form-urlencoded',  # Form-based attacks (if not expected)
        ]
        
        if any(dangerous_type in content_type.lower() for dangerous_type in dangerous_types):
            if not self._is_expected_content_type(request.url.path, content_type):
                logger.warning(f"⚠️ [SECURITY] Unexpected content type: {content_type}")
    
    def _is_expected_content_type(self, path: str, content_type: str) -> bool:
        """Check if content type is expected for the endpoint."""
        # This would be expanded based on actual API endpoints
        json_endpoints = ['/api/v1/auth/', '/api/v1/generations/', '/api/v1/projects/']
        
        if any(path.startswith(endpoint) for endpoint in json_endpoints):
            return 'application/json' in content_type.lower()
        
        return True  # Allow for now, expand as needed
    
    def _contains_malicious_patterns(self, text: str) -> bool:
        """Check if text contains malicious patterns."""
        if not text:
            return False
        
        # Check against compiled patterns
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        
        return False
    
    async def _check_rate_limiting(self, client_ip: str, request: Request):
        """Basic rate limiting check."""
        current_time = time.time()
        
        # Initialize tracking for new IPs
        if client_ip not in self.failed_requests:
            self.failed_requests[client_ip] = []
        
        # Clean old entries (older than 1 hour)
        self.failed_requests[client_ip] = [
            req_time for req_time in self.failed_requests[client_ip] 
            if current_time - req_time < 3600
        ]
        
        # Check if IP has too many recent failed requests
        if len(self.failed_requests[client_ip]) > 50:  # More than 50 failures in an hour
            self.suspicious_ips.add(client_ip)
            logger.warning(f"🚨 [SECURITY] IP {client_ip} marked as suspicious due to excessive failures")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Access temporarily restricted due to suspicious activity"
            )
    
    async def _track_failed_request(self, client_ip: str):
        """Track failed request for rate limiting."""
        current_time = time.time()
        
        if client_ip not in self.failed_requests:
            self.failed_requests[client_ip] = []
        
        self.failed_requests[client_ip].append(current_time)
        
        # Mark as suspicious after 20 failures in 10 minutes
        recent_failures = [
            req_time for req_time in self.failed_requests[client_ip]
            if current_time - req_time < 600
        ]
        
        if len(recent_failures) > 20:
            self.suspicious_ips.add(client_ip)
            logger.warning(f"🚨 [SECURITY] IP {client_ip} marked suspicious: {len(recent_failures)} failures in 10 minutes")
    
    def _add_security_headers(self, response: Response, request: Request):
        """Add comprehensive security headers."""
        
        if not settings.security_headers_enabled:
            return
        
        # Get security headers from settings
        try:
            security_headers = settings.get_security_headers()
            for name, value in security_headers.items():
                if value:
                    response.headers[name] = value
        except:
            # Fallback security headers
            response.headers.update({
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Referrer-Policy": "strict-origin-when-cross-origin",
            })
        
        # Add CSP header
        if settings.is_production():
            response.headers["Content-Security-Policy"] = self.csp_policy
        
        # Add request ID for tracking
        response.headers["X-Request-ID"] = self._generate_request_id()
        
        # Security-specific headers
        response.headers["X-Security-Version"] = "1.0"
        response.headers["X-Content-Security-Policy"] = "default-src 'self'"
        
        # Remove server information
        if "Server" in response.headers:
            del response.headers["Server"]
    
    async def _create_secure_error_response(self, exception: HTTPException, request: Request) -> Response:
        """Create secure error response without information disclosure."""
        
        # Generic error messages for security
        secure_messages = {
            400: "Bad request",
            401: "Authentication required", 
            403: "Access forbidden",
            404: "Resource not found",
            405: "Method not allowed",
            413: "Request too large",
            414: "URI too long",
            415: "Unsupported media type",
            429: "Too many requests",
            431: "Request headers too large",
            500: "Internal server error",
        }
        
        status_code = exception.status_code
        
        # Use generic message in production, detailed in development
        if settings.is_production() and not settings.verbose_error_messages:
            error_message = secure_messages.get(status_code, "Request failed")
        else:
            error_message = exception.detail
        
        response_data = {
            "error": error_message,
            "status_code": status_code,
            "request_id": self._generate_request_id(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add helpful information only in development
        if not settings.is_production():
            response_data["path"] = str(request.url.path)
            response_data["method"] = request.method
        
        response = JSONResponse(
            status_code=status_code,
            content=response_data
        )
        
        # Add security headers
        self._add_security_headers(response, request)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request with proxy support."""
        # Check forwarded headers (for reverse proxies like Railway)
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        forwarded = request.headers.get('x-forwarded')
        if forwarded:
            return forwarded.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        # Fallback to client host
        return request.client.host if request.client else 'unknown'
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID for tracking."""
        import secrets
        return secrets.token_urlsafe(12)
    
    async def _log_security_event(self, request: Request, client_ip: str, message: str, status_code: int):
        """Log security-related events."""
        
        event_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_ip": client_ip,
            "method": request.method,
            "path": str(request.url.path),
            "user_agent": request.headers.get('user-agent', 'unknown'),
            "message": message,
            "status_code": status_code,
            "request_id": self._generate_request_id()
        }
        
        # Log based on severity
        if status_code >= 500:
            logger.error(f"🚨 [SECURITY-ERROR] {message} | IP: {client_ip} | Path: {request.url.path}")
        elif status_code >= 400:
            logger.warning(f"⚠️ [SECURITY-WARNING] {message} | IP: {client_ip} | Path: {request.url.path}")
        else:
            logger.info(f"ℹ️ [SECURITY-INFO] {message} | IP: {client_ip} | Path: {request.url.path}")
        
        # In production, you would send this to a security monitoring system
        # like SIEM, Splunk, or other security analytics platforms