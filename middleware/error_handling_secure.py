"""
Secure Error Handling Middleware
Prevents information disclosure while maintaining debugging capabilities for development.
Implements OWASP security guidelines for error handling.
"""
import logging
import traceback
import sys
import uuid
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

try:
    from config import settings
except ImportError:
    class FallbackSettings:
        def is_production(self): return True
        verbose_error_messages = False
        debug = False
    settings = FallbackSettings()

logger = logging.getLogger(__name__)

class SecureErrorHandler(BaseHTTPMiddleware):
    """
    Secure error handling middleware that:
    - Prevents information disclosure in production
    - Provides useful debugging info in development
    - Logs security-relevant errors
    - Generates unique error IDs for tracking
    - Sanitizes error responses
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Error classifications for security analysis
        self.security_sensitive_errors = {
            # Database errors (potential SQL injection attempts)
            "OperationalError", "DatabaseError", "IntegrityError",
            # Authentication/authorization errors
            "AuthenticationError", "PermissionError", "Unauthorized",
            # File system errors (potential path traversal)
            "FileNotFoundError", "PermissionError", "OSError",
            # Network errors (potential SSRF attempts)
            "ConnectionError", "TimeoutError", "HTTPError"
        }
        
        # Safe error messages for production
        self.production_error_messages = {
            400: "Bad request - please check your input",
            401: "Authentication required",
            403: "Access denied - insufficient permissions",
            404: "Resource not found",
            405: "Method not allowed",
            406: "Not acceptable",
            409: "Conflict - resource already exists",
            410: "Gone - resource no longer available", 
            413: "Request entity too large",
            414: "URI too long",
            415: "Unsupported media type",
            422: "Unprocessable entity - validation failed",
            423: "Locked",
            429: "Too many requests - please try again later",
            431: "Request header fields too large",
            500: "Internal server error",
            501: "Not implemented",
            502: "Bad gateway",
            503: "Service unavailable",
            504: "Gateway timeout",
            507: "Insufficient storage"
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with secure error handling."""
        
        # Generate unique request ID for error tracking
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        try:
            response = await call_next(request)
            
            # Add request ID to successful responses for debugging
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as exc:
            return await self._handle_exception(exc, request, request_id)
    
    async def _handle_exception(self, exc: Exception, request: Request, request_id: str) -> JSONResponse:
        """Handle exceptions with security-first approach."""
        
        # Log the full error details for internal debugging
        await self._log_error_details(exc, request, request_id)
        
        # Determine if this is a security-sensitive error
        is_security_sensitive = self._is_security_sensitive_error(exc)
        
        # Create secure error response
        if isinstance(exc, HTTPException):
            return await self._handle_http_exception(exc, request, request_id, is_security_sensitive)
        elif isinstance(exc, RequestValidationError):
            return await self._handle_validation_error(exc, request, request_id)
        elif isinstance(exc, StarletteHTTPException):
            return await self._handle_starlette_exception(exc, request, request_id, is_security_sensitive)
        else:
            return await self._handle_generic_exception(exc, request, request_id, is_security_sensitive)
    
    async def _handle_http_exception(
        self, 
        exc: HTTPException, 
        request: Request, 
        request_id: str,
        is_security_sensitive: bool
    ) -> JSONResponse:
        """Handle FastAPI HTTPException with security considerations."""
        
        status_code = exc.status_code
        
        # Determine error message based on environment and sensitivity
        if settings.is_production() and not settings.verbose_error_messages:
            # Use safe, generic messages in production
            if is_security_sensitive:
                error_message = "Request failed"
                # Don't leak any details for security-sensitive errors
            else:
                error_message = self.production_error_messages.get(
                    status_code, 
                    "Request failed"
                )
        else:
            # Development mode - include original message
            error_message = str(exc.detail) if exc.detail else "No error details available"
        
        response_data = {
            "error": error_message,
            "status_code": status_code,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add development-only debugging information
        if not settings.is_production() and settings.debug:
            response_data.update({
                "debug_info": {
                    "exception_type": type(exc).__name__,
                    "original_detail": str(exc.detail) if exc.detail else None,
                    "path": str(request.url.path),
                    "method": request.method,
                    "headers": dict(request.headers) if settings.debug else None
                }
            })
        
        # Log security events for monitoring
        if is_security_sensitive:
            await self._log_security_event(exc, request, request_id, status_code)
        
        return JSONResponse(
            status_code=status_code,
            content=response_data,
            headers=self._get_security_headers()
        )
    
    async def _handle_validation_error(
        self, 
        exc: RequestValidationError, 
        request: Request, 
        request_id: str
    ) -> JSONResponse:
        """Handle validation errors with input sanitization."""
        
        # Validation errors are usually not security-sensitive but could indicate probing
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        
        if settings.is_production() and not settings.verbose_error_messages:
            # Generic message in production
            error_message = "Validation failed - please check your input"
            response_data = {
                "error": error_message,
                "status_code": status_code,
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            # Development mode - include sanitized validation details
            validation_errors = []
            for error in exc.errors():
                sanitized_error = {
                    "field": " -> ".join(str(loc) for loc in error.get("loc", [])),
                    "message": self._sanitize_validation_message(error.get("msg", "")),
                    "type": error.get("type", "")
                }
                validation_errors.append(sanitized_error)
            
            response_data = {
                "error": "Validation failed",
                "validation_errors": validation_errors,
                "status_code": status_code,
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Check for potential malicious input patterns
        if self._contains_malicious_patterns(str(exc.errors())):
            await self._log_security_event(exc, request, request_id, status_code, "malicious_input_detected")
        
        return JSONResponse(
            status_code=status_code,
            content=response_data,
            headers=self._get_security_headers()
        )
    
    async def _handle_starlette_exception(
        self, 
        exc: StarletteHTTPException, 
        request: Request, 
        request_id: str,
        is_security_sensitive: bool
    ) -> JSONResponse:
        """Handle Starlette HTTP exceptions."""
        
        status_code = exc.status_code
        
        if settings.is_production() and not settings.verbose_error_messages:
            error_message = self.production_error_messages.get(status_code, "Request failed")
        else:
            error_message = str(exc.detail) if hasattr(exc, 'detail') else "Unknown error"
        
        response_data = {
            "error": error_message,
            "status_code": status_code,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if is_security_sensitive:
            await self._log_security_event(exc, request, request_id, status_code)
        
        return JSONResponse(
            status_code=status_code,
            content=response_data,
            headers=self._get_security_headers()
        )
    
    async def _handle_generic_exception(
        self, 
        exc: Exception, 
        request: Request, 
        request_id: str,
        is_security_sensitive: bool
    ) -> JSONResponse:
        """Handle generic exceptions with maximum security."""
        
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        if settings.is_production():
            # Never leak internal error details in production
            error_message = "Internal server error"
        else:
            # Development mode - provide helpful error information
            error_message = f"Internal error: {type(exc).__name__}"
            if not is_security_sensitive:
                error_message += f": {str(exc)}"
        
        response_data = {
            "error": error_message,
            "status_code": status_code,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Development debugging info
        if not settings.is_production() and settings.debug:
            response_data["debug_info"] = {
                "exception_type": type(exc).__name__,
                "exception_module": getattr(type(exc), '__module__', 'unknown'),
                "is_security_sensitive": is_security_sensitive
            }
        
        # Always log security-sensitive errors
        if is_security_sensitive:
            await self._log_security_event(exc, request, request_id, status_code, "security_sensitive_error")
        
        return JSONResponse(
            status_code=status_code,
            content=response_data,
            headers=self._get_security_headers()
        )
    
    def _is_security_sensitive_error(self, exc: Exception) -> bool:
        """Determine if an error is security-sensitive."""
        
        exc_type_name = type(exc).__name__
        
        # Check against known security-sensitive error types
        if exc_type_name in self.security_sensitive_errors:
            return True
        
        # Check error message for sensitive patterns
        error_message = str(exc).lower()
        sensitive_patterns = [
            "password", "token", "secret", "key", "credential",
            "authentication", "authorization", "permission",
            "sql", "database", "connection", "timeout",
            "file not found", "access denied", "forbidden"
        ]
        
        return any(pattern in error_message for pattern in sensitive_patterns)
    
    def _contains_malicious_patterns(self, text: str) -> bool:
        """Check if text contains patterns that might indicate malicious input."""
        
        text_lower = text.lower()
        malicious_patterns = [
            # SQL injection
            "union select", "drop table", "insert into", "delete from",
            # XSS
            "<script", "javascript:", "on\w+=",
            # Path traversal  
            "../", "..\\", "%2e%2e",
            # Command injection
            ";", "|", "&", "`", "$(", "<(", ">(",
            # LDAP injection
            "*)", "&(", "|(", "!("
        ]
        
        return any(pattern in text_lower for pattern in malicious_patterns)
    
    def _sanitize_validation_message(self, message: str) -> str:
        """Sanitize validation error messages to prevent information disclosure."""
        
        # Remove potentially sensitive information from validation messages
        sensitive_patterns = {
            r'\b\d{4}-\d{2}-\d{2}\b': '[DATE]',  # Dates
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b': '[IP]',  # IP addresses
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b': '[EMAIL]',  # Emails
            r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b': '[UUID]'  # UUIDs
        }
        
        import re
        sanitized_message = message
        for pattern, replacement in sensitive_patterns.items():
            sanitized_message = re.sub(pattern, replacement, sanitized_message, flags=re.IGNORECASE)
        
        return sanitized_message
    
    async def _log_error_details(self, exc: Exception, request: Request, request_id: str):
        """Log comprehensive error details for internal debugging."""
        
        # Extract request information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Log error with full context
        error_context = {
            "request_id": request_id,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "request_method": request.method,
            "request_path": str(request.url.path),
            "request_query": str(request.url.query) if request.url.query else None,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add traceback in development
        if not settings.is_production():
            error_context["traceback"] = traceback.format_exc()
        
        # Log based on error severity
        if isinstance(exc, HTTPException) and exc.status_code < 500:
            logger.warning(f"🔍 [ERROR-HANDLER] Client error: {error_context}")
        else:
            logger.error(f"❌ [ERROR-HANDLER] Server error: {error_context}")
    
    async def _log_security_event(
        self, 
        exc: Exception, 
        request: Request, 
        request_id: str, 
        status_code: int,
        event_type: str = "security_error"
    ):
        """Log security-relevant events for monitoring and alerting."""
        
        security_event = {
            "event_type": event_type,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent", "unknown"),
            "request_method": request.method,
            "request_path": str(request.url.path),
            "status_code": status_code,
            "exception_type": type(exc).__name__,
            "threat_indicators": {
                "is_security_sensitive": self._is_security_sensitive_error(exc),
                "contains_malicious_patterns": self._contains_malicious_patterns(str(exc)),
                "repeated_failures": self._is_repeated_failure(request)
            }
        }
        
        logger.warning(f"🚨 [SECURITY-EVENT] {event_type}: {security_event}")
        
        # In production, this would be sent to a SIEM or security monitoring system
    
    def _is_repeated_failure(self, request: Request) -> bool:
        """Check if this is a repeated failure from the same client."""
        # This would be implemented with proper tracking in production
        # For now, return False as a placeholder
        return False
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check forwarded headers (for reverse proxies)
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else 'unknown'
    
    def _get_security_headers(self) -> Dict[str, str]:
        """Get security headers for error responses."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }

# Exception handlers for specific error types
def create_custom_exception_handlers() -> Dict[Any, Any]:
    """Create custom exception handlers for FastAPI."""
    
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle HTTP exceptions."""
        # This will be handled by the middleware
        raise exc
    
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Handle validation exceptions."""
        # This will be handled by the middleware
        raise exc
    
    return {
        HTTPException: http_exception_handler,
        RequestValidationError: validation_exception_handler
    }