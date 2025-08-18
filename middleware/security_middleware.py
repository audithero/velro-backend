"""
OWASP-Compliant Security Middleware for Velro Backend
Implements comprehensive security controls per OWASP Top 10 2023

Security Features:
- OWASP-compliant security headers
- Content Security Policy (CSP) enforcement
- SQL injection prevention via input validation
- XSS protection through output encoding
- CSRF protection with secure tokens
- Rate limiting per OWASP guidelines
- Input validation and sanitization
- Secure session management
- Error handling without information leakage
"""
import re
import json
import time
import hashlib
import secrets
import logging
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import ipaddress

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from config import settings

logger = logging.getLogger(__name__)

class SecurityHeaders:
    """OWASP-compliant security headers configuration."""
    
    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """Get comprehensive security headers per OWASP guidelines."""
        return {
            # OWASP A05:2021 – Security Misconfiguration
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            
            # OWASP A01:2021 – Broken Access Control
            "X-Permitted-Cross-Domain-Policies": "none",
            "Cross-Origin-Embedder-Policy": "require-corp",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-site",
            
            # OWASP A02:2021 – Cryptographic Failures
            "Strict-Transport-Security": f"max-age={settings.hsts_max_age}; includeSubDomains; preload" if settings.is_production() else None,
            
            # OWASP A03:2021 – Injection (CSP for XSS prevention)
            "Content-Security-Policy": settings.content_security_policy,
            
            # Additional security headers
            "X-Download-Options": "noopen",
            "X-DNS-Prefetch-Control": "off",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
            "Expect-CT": "max-age=86400, enforce" if settings.is_production() else None,
            
            # API security
            "X-API-Version": settings.app_version,
            "X-Rate-Limit-Remaining": "dynamic",  # Will be set by rate limiter
            "X-Security-Framework": "OWASP-2023",
        }

class InputValidator:
    """
    OWASP-compliant input validation and sanitization.
    Prevents OWASP A03:2021 – Injection attacks.
    """
    
    # SQL injection patterns (OWASP A03:2021)
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b)",
        r"(;|\-\-|/\*|\*/|\bOR\b|\bAND\b).*(\b(SELECT|INSERT|UPDATE|DELETE)\b)",
        r"(\'\s*(OR|AND)\s*\'\s*=\s*\')",
        r"(\bUNION\b.*\bSELECT\b)",
        r"(\bEXEC\()",
    ]
    
    # XSS patterns (OWASP A03:2021)
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>.*?</iframe>",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>",
        r"<link[^>]*>",
        r"<meta[^>]*>",
    ]
    
    # Path traversal patterns (OWASP A01:2021)
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\.\/",
        r"\.\.\\",
        r"%2e%2e%2f",
        r"%2e%2e%5c",
        r"..%2f",
        r"..%5c",
    ]
    
    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$()]",
        r"\b(cat|ls|pwd|whoami|id|uname|netstat|ps|kill)\b",
        r"(>|<|>>|<<)",
    ]
    
    @classmethod
    def validate_input(cls, value: Any, field_name: str, input_type: str = "general") -> Tuple[bool, str]:
        """
        Comprehensive input validation per OWASP guidelines.
        
        Args:
            value: Input value to validate
            field_name: Name of the field being validated
            input_type: Type of input validation to apply
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if value is None:
                return True, ""
            
            # Convert to string for pattern matching
            str_value = str(value) if not isinstance(value, str) else value
            
            # Length validation (prevent buffer overflow attacks)
            if len(str_value) > 10000:  # 10KB limit
                return False, f"Input too long for field '{field_name}'"
            
            # SQL injection detection
            for pattern in cls.SQL_INJECTION_PATTERNS:
                if re.search(pattern, str_value, re.IGNORECASE | re.MULTILINE):
                    logger.warning(f"🚨 [SECURITY] SQL injection attempt detected in '{field_name}': {str_value[:100]}...")
                    return False, f"Invalid characters detected in '{field_name}'"
            
            # XSS detection
            for pattern in cls.XSS_PATTERNS:
                if re.search(pattern, str_value, re.IGNORECASE | re.DOTALL):
                    logger.warning(f"🚨 [SECURITY] XSS attempt detected in '{field_name}': {str_value[:100]}...")
                    return False, f"Invalid script content detected in '{field_name}'"
            
            # Path traversal detection
            for pattern in cls.PATH_TRAVERSAL_PATTERNS:
                if re.search(pattern, str_value, re.IGNORECASE):
                    logger.warning(f"🚨 [SECURITY] Path traversal attempt detected in '{field_name}': {str_value[:100]}...")
                    return False, f"Invalid path characters detected in '{field_name}'"
            
            # Command injection detection
            if input_type in ["filename", "general"]:
                for pattern in cls.COMMAND_INJECTION_PATTERNS:
                    if re.search(pattern, str_value):
                        logger.warning(f"🚨 [SECURITY] Command injection attempt detected in '{field_name}': {str_value[:100]}...")
                        return False, f"Invalid command characters detected in '{field_name}'"
            
            # Type-specific validation
            if input_type == "email":
                return cls._validate_email(str_value)
            elif input_type == "uuid":
                return cls._validate_uuid(str_value)
            elif input_type == "numeric":
                return cls._validate_numeric(str_value)
            elif input_type == "alphanumeric":
                return cls._validate_alphanumeric(str_value)
            
            return True, ""
            
        except Exception as e:
            logger.error(f"❌ [SECURITY] Input validation error for '{field_name}': {e}")
            return False, "Input validation failed"
    
    @staticmethod
    def _validate_email(email: str) -> Tuple[bool, str]:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, "Invalid email format"
        if len(email) > 320:  # RFC 5321 limit
            return False, "Email address too long"
        return True, ""
    
    @staticmethod
    def _validate_uuid(uuid_str: str) -> Tuple[bool, str]:
        """Validate UUID format."""
        pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        if not re.match(pattern, uuid_str):
            return False, "Invalid UUID format"
        return True, ""
    
    @staticmethod
    def _validate_numeric(value: str) -> Tuple[bool, str]:
        """Validate numeric input."""
        try:
            float(value)
            return True, ""
        except ValueError:
            return False, "Invalid numeric value"
    
    @staticmethod
    def _validate_alphanumeric(value: str) -> Tuple[bool, str]:
        """Validate alphanumeric input."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', value):
            return False, "Only alphanumeric characters, underscores, and hyphens allowed"
        return True, ""
    
    @staticmethod
    def sanitize_output(data: Any) -> Any:
        """
        Sanitize output data to prevent XSS.
        OWASP A03:2021 – Injection prevention.
        """
        if isinstance(data, str):
            # HTML encode special characters
            data = data.replace("&", "&amp;")
            data = data.replace("<", "&lt;")
            data = data.replace(">", "&gt;")
            data = data.replace("\"", "&quot;")
            data = data.replace("'", "&#x27;")
            data = data.replace("/", "&#x2F;")
            return data
        elif isinstance(data, dict):
            return {key: InputValidator.sanitize_output(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [InputValidator.sanitize_output(item) for item in data]
        else:
            return data

class CSRFProtection:
    """
    CSRF protection implementation per OWASP guidelines.
    Prevents OWASP A01:2021 – Broken Access Control.
    """
    
    def __init__(self):
        self._tokens = {}  # In-memory token store (use Redis in production)
        self._cleanup_interval = 3600  # 1 hour
        self._last_cleanup = time.time()
    
    def generate_csrf_token(self, session_id: str) -> str:
        """Generate secure CSRF token."""
        token = secrets.token_urlsafe(32)
        timestamp = time.time()
        
        # Store token with expiration
        self._tokens[session_id] = {
            'token': token,
            'expires': timestamp + 3600,  # 1 hour expiration
            'created': timestamp
        }
        
        # Periodic cleanup
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired_tokens()
        
        return token
    
    def validate_csrf_token(self, session_id: str, provided_token: str) -> bool:
        """Validate CSRF token."""
        if session_id not in self._tokens:
            return False
        
        stored_data = self._tokens[session_id]
        
        # Check expiration
        if time.time() > stored_data['expires']:
            del self._tokens[session_id]
            return False
        
        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(stored_data['token'], provided_token)
    
    def _cleanup_expired_tokens(self):
        """Remove expired CSRF tokens."""
        current_time = time.time()
        expired_sessions = [
            session_id for session_id, data in self._tokens.items()
            if current_time > data['expires']
        ]
        
        for session_id in expired_sessions:
            del self._tokens[session_id]
        
        self._last_cleanup = current_time
        logger.debug(f"🧹 [SECURITY] Cleaned {len(expired_sessions)} expired CSRF tokens")

class RateLimiter:
    """
    Advanced rate limiting per OWASP guidelines.
    Prevents OWASP A10:2021 – Server-Side Request Forgery and DoS.
    """
    
    def __init__(self):
        self._requests = {}  # IP -> request data
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.time()
    
    def is_rate_limited(self, client_ip: str, endpoint: str, limits: Dict[str, int]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request should be rate limited.
        
        Args:
            client_ip: Client IP address
            endpoint: API endpoint
            limits: Rate limit configuration
            
        Returns:
            Tuple of (is_limited, rate_limit_info)
        """
        current_time = time.time()
        key = f"{client_ip}:{endpoint}"
        
        # Initialize tracking if not exists
        if key not in self._requests:
            self._requests[key] = {
                'requests': [],
                'blocked_until': 0
            }
        
        request_data = self._requests[key]
        
        # Check if currently blocked
        if current_time < request_data['blocked_until']:
            return True, {
                'blocked': True,
                'reset_time': request_data['blocked_until'],
                'reason': 'rate_limit_exceeded'
            }
        
        # Clean old requests
        window_start = current_time - limits.get('window', 60)
        request_data['requests'] = [
            req_time for req_time in request_data['requests']
            if req_time > window_start
        ]
        
        # Check rate limits
        request_count = len(request_data['requests'])
        max_requests = limits.get('max_requests', 100)
        
        if request_count >= max_requests:
            # Block for escalating duration
            block_duration = min(3600, 60 * (2 ** (request_count // max_requests)))  # Max 1 hour
            request_data['blocked_until'] = current_time + block_duration
            
            logger.warning(f"🚨 [SECURITY] Rate limit exceeded for {client_ip}:{endpoint} - blocked for {block_duration}s")
            
            return True, {
                'blocked': True,
                'reset_time': request_data['blocked_until'],
                'reason': 'rate_limit_exceeded',
                'requests_made': request_count,
                'max_requests': max_requests
            }
        
        # Add current request
        request_data['requests'].append(current_time)
        
        # Periodic cleanup
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_requests()
        
        return False, {
            'blocked': False,
            'requests_remaining': max_requests - request_count - 1,
            'reset_time': window_start + limits.get('window', 60),
            'requests_made': request_count + 1,
            'max_requests': max_requests
        }
    
    def _cleanup_old_requests(self):
        """Clean up old request tracking data."""
        current_time = time.time()
        keys_to_remove = []
        
        for key, data in self._requests.items():
            # Remove if no recent requests and not blocked
            if (not data['requests'] and 
                current_time > data['blocked_until'] and
                current_time - data.get('last_request', 0) > 3600):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._requests[key]
        
        self._last_cleanup = current_time
        logger.debug(f"🧹 [SECURITY] Cleaned {len(keys_to_remove)} old rate limit entries")

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive OWASP-compliant security middleware.
    Implements security controls for OWASP Top 10 2023.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.csrf_protection = CSRFProtection()
        self.rate_limiter = RateLimiter()
        self.input_validator = InputValidator()
        
        # Security configuration
        self.blocked_ips = set()
        self.suspicious_ips = {}
        self.security_events = []
        
        logger.info("🛡️ [SECURITY] OWASP-compliant security middleware initialized")
    
    async def dispatch(self, request: Request, call_next):
        """Process request through security controls."""
        start_time = time.time()
        
        try:
            # 1. IP validation and blocking
            client_ip = self._get_client_ip(request)
            if await self._is_blocked_ip(client_ip):
                return self._create_security_response(403, "Access denied", "blocked_ip")
            
            # 2. Rate limiting
            rate_limit_info = await self._check_rate_limits(request, client_ip)
            if rate_limit_info['blocked']:
                return self._create_security_response(429, "Rate limit exceeded", "rate_limited", rate_limit_info)
            
            # 3. Input validation
            if request.method in ["POST", "PUT", "PATCH"]:
                validation_result = await self._validate_request_input(request)
                if not validation_result['valid']:
                    await self._log_security_event(client_ip, "input_validation_failed", validation_result['error'])
                    return self._create_security_response(400, "Invalid input", "validation_failed")
            
            # 4. CSRF protection for state-changing operations
            if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
                if not await self._validate_csrf_token(request):
                    await self._log_security_event(client_ip, "csrf_validation_failed", "Missing or invalid CSRF token")
                    return self._create_security_response(403, "CSRF validation failed", "csrf_failed")
            
            # 5. Security headers on request
            request.state.security_context = {
                'client_ip': client_ip,
                'rate_limit_info': rate_limit_info,
                'security_score': self._calculate_security_score(client_ip),
                'csrf_token': self.csrf_protection.generate_csrf_token(client_ip)
            }
            
            # Process request
            response = await call_next(request)
            
            # 6. Add security headers to response
            self._add_security_headers(response, request)
            
            # 7. Output sanitization
            if hasattr(response, 'body'):
                response = await self._sanitize_response(response)
            
            # 8. Security monitoring
            processing_time = (time.time() - start_time) * 1000
            await self._log_request_metrics(client_ip, request, processing_time, response.status_code)
            
            return response
            
        except Exception as e:
            logger.error(f"❌ [SECURITY] Middleware error: {e}")
            await self._log_security_event(client_ip or "unknown", "middleware_error", str(e))
            
            # Return secure error response without information leakage
            return self._create_security_response(
                500, 
                "Internal server error" if settings.is_production() else str(e),
                "internal_error"
            )
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP with proxy header support."""
        # Check forwarded headers (in order of preference)
        forwarded_headers = [
            "CF-Connecting-IP",  # Cloudflare
            "X-Forwarded-For",   # Standard
            "X-Real-IP",         # Nginx
            "X-Client-IP"        # Apache
        ]
        
        for header in forwarded_headers:
            if header in request.headers:
                ip = request.headers[header].split(",")[0].strip()
                try:
                    ipaddress.ip_address(ip)
                    return ip
                except ValueError:
                    continue
        
        # Fallback to direct connection
        return request.client.host if request.client else "unknown"
    
    async def _is_blocked_ip(self, client_ip: str) -> bool:
        """Check if IP is blocked."""
        if client_ip in self.blocked_ips:
            return True
        
        # Check for suspicious activity
        if client_ip in self.suspicious_ips:
            suspicious_data = self.suspicious_ips[client_ip]
            if suspicious_data['score'] > 100:  # Threshold for auto-blocking
                self.blocked_ips.add(client_ip)
                logger.warning(f"🚨 [SECURITY] Auto-blocked suspicious IP: {client_ip}")
                return True
        
        return False
    
    async def _check_rate_limits(self, request: Request, client_ip: str) -> Dict[str, Any]:
        """Check rate limits for the request."""
        endpoint = request.url.path
        method = request.method
        
        # Different limits for different endpoint types
        if endpoint.startswith("/auth/"):
            limits = {"max_requests": 10, "window": 300}  # 10 requests per 5 minutes
        elif endpoint.startswith("/api/generations"):
            limits = {"max_requests": 50, "window": 3600}  # 50 requests per hour
        else:
            limits = {"max_requests": 100, "window": 60}  # 100 requests per minute
        
        is_limited, rate_info = self.rate_limiter.is_rate_limited(client_ip, f"{method}:{endpoint}", limits)
        
        return rate_info
    
    async def _validate_request_input(self, request: Request) -> Dict[str, Any]:
        """Validate all request input."""
        try:
            # Validate URL parameters
            for param, value in request.query_params.items():
                is_valid, error = self.input_validator.validate_input(value, param)
                if not is_valid:
                    return {"valid": False, "error": f"Query parameter validation failed: {error}"}
            
            # Validate request body if present
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    content_type = request.headers.get("content-type", "")
                    if "application/json" in content_type:
                        # CRITICAL FIX: Use body cache helper to prevent deadlock
                        try:
                            from middleware.production_optimized import BodyCacheHelper
                            body = await BodyCacheHelper.safe_get_body(request)
                        except ImportError:
                            # Fallback to direct body read
                            try:
                                body = await request.body()
                            except RuntimeError:
                                # Body already read - skip validation
                                return {"valid": True, "error": None}
                        
                        if body:
                            json_data = json.loads(body)
                            validation_result = self._validate_json_data(json_data)
                            if not validation_result["valid"]:
                                return validation_result
                except json.JSONDecodeError:
                    return {"valid": False, "error": "Invalid JSON format"}
                except Exception as e:
                    return {"valid": False, "error": f"Request body validation error: {e}"}
            
            return {"valid": True, "error": None}
            
        except Exception as e:
            logger.error(f"❌ [SECURITY] Input validation error: {e}")
            return {"valid": False, "error": "Input validation failed"}
    
    def _validate_json_data(self, data: Any, path: str = "") -> Dict[str, Any]:
        """Recursively validate JSON data."""
        if isinstance(data, dict):
            for key, value in data.items():
                field_path = f"{path}.{key}" if path else key
                
                # Validate key name
                is_valid, error = self.input_validator.validate_input(key, f"field_name_{field_path}")
                if not is_valid:
                    return {"valid": False, "error": error}
                
                # Validate value
                result = self._validate_json_data(value, field_path)
                if not result["valid"]:
                    return result
        
        elif isinstance(data, list):
            for i, item in enumerate(data):
                result = self._validate_json_data(item, f"{path}[{i}]")
                if not result["valid"]:
                    return result
        
        elif isinstance(data, str):
            # Validate string content
            input_type = self._determine_input_type(path, data)
            is_valid, error = self.input_validator.validate_input(data, path, input_type)
            if not is_valid:
                return {"valid": False, "error": error}
        
        return {"valid": True, "error": None}
    
    def _determine_input_type(self, field_path: str, value: str) -> str:
        """Determine input validation type based on field name and content."""
        field_lower = field_path.lower()
        
        if "email" in field_lower:
            return "email"
        elif "id" in field_lower or "uuid" in field_lower:
            return "uuid"
        elif any(word in field_lower for word in ["count", "amount", "price", "number"]):
            return "numeric"
        elif any(word in field_lower for word in ["username", "name", "title"]):
            return "alphanumeric"
        else:
            return "general"
    
    async def _validate_csrf_token(self, request: Request) -> bool:
        """Validate CSRF token for state-changing operations."""
        if not settings.csrf_protection_enabled:
            return True
        
        # Skip CSRF for API endpoints with proper authentication
        if request.headers.get("authorization") and request.url.path.startswith("/api/"):
            return True
        
        client_ip = self._get_client_ip(request)
        csrf_token = request.headers.get("x-csrf-token") or request.cookies.get("csrf_token")
        
        if not csrf_token:
            return False
        
        return self.csrf_protection.validate_csrf_token(client_ip, csrf_token)
    
    def _add_security_headers(self, response: Response, request: Request):
        """Add OWASP-compliant security headers to response."""
        security_headers = SecurityHeaders.get_security_headers()
        
        for header_name, header_value in security_headers.items():
            if header_value is not None:
                response.headers[header_name] = header_value
        
        # Add CSRF token to response if needed
        if hasattr(request.state, 'security_context'):
            csrf_token = request.state.security_context.get('csrf_token')
            if csrf_token:
                response.headers["x-csrf-token"] = csrf_token
    
    async def _sanitize_response(self, response: Response) -> Response:
        """Sanitize response data to prevent XSS."""
        try:
            if hasattr(response, 'body') and response.headers.get("content-type", "").startswith("application/json"):
                body = response.body.decode("utf-8")
                data = json.loads(body)
                sanitized_data = self.input_validator.sanitize_output(data)
                
                # Update response body
                response.body = json.dumps(sanitized_data, default=str).encode("utf-8")
                response.headers["content-length"] = str(len(response.body))
            
            return response
            
        except Exception as e:
            logger.error(f"❌ [SECURITY] Response sanitization error: {e}")
            return response
    
    def _calculate_security_score(self, client_ip: str) -> int:
        """Calculate security score for client IP."""
        if client_ip not in self.suspicious_ips:
            return 0
        
        return self.suspicious_ips[client_ip].get('score', 0)
    
    async def _log_security_event(self, client_ip: str, event_type: str, details: str):
        """Log security events for monitoring."""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'client_ip': client_ip,
            'event_type': event_type,
            'details': details,
            'severity': self._get_event_severity(event_type)
        }
        
        self.security_events.append(event)
        
        # Update suspicious IP tracking
        if client_ip not in self.suspicious_ips:
            self.suspicious_ips[client_ip] = {'score': 0, 'events': []}
        
        self.suspicious_ips[client_ip]['score'] += self._get_event_score(event_type)
        self.suspicious_ips[client_ip]['events'].append(event)
        
        # Log high-severity events
        if event['severity'] in ['HIGH', 'CRITICAL']:
            logger.warning(f"🚨 [SECURITY] {event['severity']} event from {client_ip}: {event_type} - {details}")
        
        # Keep only recent events (memory management)
        if len(self.security_events) > 10000:
            self.security_events = self.security_events[-5000:]
    
    def _get_event_severity(self, event_type: str) -> str:
        """Get severity level for security event."""
        severity_map = {
            'input_validation_failed': 'MEDIUM',
            'csrf_validation_failed': 'HIGH',
            'rate_limited': 'MEDIUM',
            'blocked_ip': 'HIGH',
            'sql_injection_attempt': 'CRITICAL',
            'xss_attempt': 'HIGH',
            'path_traversal_attempt': 'HIGH',
            'command_injection_attempt': 'CRITICAL',
            'middleware_error': 'LOW'
        }
        return severity_map.get(event_type, 'LOW')
    
    def _get_event_score(self, event_type: str) -> int:
        """Get score increase for security event."""
        score_map = {
            'input_validation_failed': 5,
            'csrf_validation_failed': 20,
            'rate_limited': 10,
            'sql_injection_attempt': 50,
            'xss_attempt': 30,
            'path_traversal_attempt': 30,
            'command_injection_attempt': 50,
            'middleware_error': 1
        }
        return score_map.get(event_type, 1)
    
    async def _log_request_metrics(self, client_ip: str, request: Request, processing_time: float, status_code: int):
        """Log request metrics for monitoring."""
        # Only log detailed metrics in debug mode to avoid performance impact
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"📊 [SECURITY] Request: {client_ip} {request.method} {request.url.path} "
                f"-> {status_code} in {processing_time:.2f}ms"
            )
    
    def _create_security_response(self, status_code: int, message: str, error_type: str, details: Dict = None) -> JSONResponse:
        """Create standardized security response."""
        response_data = {
            "error": {
                "type": error_type,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }
        
        # Add details only in development
        if details and not settings.is_production():
            response_data["error"]["details"] = details
        
        response = JSONResponse(
            content=response_data,
            status_code=status_code
        )
        
        # Add security headers
        security_headers = SecurityHeaders.get_security_headers()
        for header_name, header_value in security_headers.items():
            if header_value is not None:
                response.headers[header_name] = header_value
        
        return response