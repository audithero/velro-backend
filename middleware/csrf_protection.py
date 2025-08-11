"""
CSRF (Cross-Site Request Forgery) Protection Middleware
Implements enterprise-grade CSRF protection following OWASP guidelines.
Phase 1 Step 3 - Critical security implementation.
"""
import logging
import secrets
import hashlib
import hmac
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Set, Optional, List
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from utils.cache_manager import cache_manager, CacheLevel
from config import settings

logger = logging.getLogger(__name__)

class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    Enterprise-grade CSRF protection middleware implementing:
    - Double-submit cookie pattern
    - Cryptographically secure token generation
    - SameSite cookie attributes
    - Synchronized token validation
    - Origin and Referer validation
    - Time-based token expiration
    - Rate limiting for token requests
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Protected HTTP methods requiring CSRF validation
        self.protected_methods: Set[str] = {"POST", "PUT", "DELETE", "PATCH"}
        
        # Endpoints that are exempt from CSRF protection
        self.csrf_exempt_paths: Set[str] = {
            "/health",
            "/metrics", 
            "/api/v1/auth/login",      # Authentication endpoints have their own protection
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/auth/health",     # Auth production health endpoint
            "/api/v1/auth/security-info",  # Auth production security info
            # Auth health monitoring endpoints (no CSRF needed for monitoring)
            "/api/v1/auth-health/health",
            "/api/v1/auth-health/metrics",
            "/api/v1/auth-health/system-info",
            "/api/v1/auth-health/rate-limit-status",
            "/api/v1/auth-health/security-dashboard"
        }
        
        # Safe endpoints that provide CSRF tokens
        self.token_providing_endpoints: Set[str] = {
            "/api/v1/auth/csrf-token",
            "/api/v1/csrf-token"
        }
        
        # Token configuration
        self.token_length = 32
        self.token_expiry_hours = 2
        self.max_tokens_per_ip = 10
        
        logger.info("🛡️ [CSRF] CSRF Protection Middleware initialized")
        logger.info(f"🛡️ [CSRF] Protected methods: {self.protected_methods}")
        logger.info(f"🛡️ [CSRF] Exempt paths: {len(self.csrf_exempt_paths)} paths")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with CSRF protection."""
        
        # Skip CSRF protection if disabled
        if not settings.csrf_protection_enabled:
            logger.debug("⚠️ [CSRF] CSRF protection disabled - proceeding without validation")
            return await call_next(request)
        
        path = request.url.path
        method = request.method
        client_ip = self._get_client_ip(request)
        
        try:
            # Check if path is exempt from CSRF protection
            if self._is_exempt_path(path):
                logger.debug(f"✅ [CSRF] Path {path} is exempt from CSRF protection")
                response = await call_next(request)
                return self._add_csrf_headers(response, request)
            
            # Check for E2E test mode - bypass CSRF for test requests
            if self._is_test_request(request):
                logger.debug(f"🧪 [CSRF] E2E test request detected, bypassing CSRF for {path}")
                response = await call_next(request)
                return self._add_csrf_headers(response, request)
            
            # Handle CSRF token requests
            if path in self.token_providing_endpoints and method == "GET":
                return await self._handle_csrf_token_request(request, client_ip)
            
            # Validate CSRF for protected methods
            if method in self.protected_methods:
                await self._validate_csrf_protection(request, client_ip)
            
            # Process the request
            response = await call_next(request)
            
            # Add CSRF headers to response
            return self._add_csrf_headers(response, request)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ [CSRF] Unexpected error in CSRF middleware: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal security error"
            )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP considering proxy headers."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        return getattr(request.client, "host", "unknown")
    
    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from CSRF protection."""
        # Exact match
        if path in self.csrf_exempt_paths:
            return True
        
        # Prefix match for dynamic paths
        exempt_prefixes = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/static/",
            "/health",
            "/api/v1/e2e/",  # E2E testing endpoints
            "/api/v1/auth-health/"  # Auth health monitoring endpoints
        ]
        
        # Exact matches for common paths
        if path in ["/", "/health", "/api/v1/debug/health"]:
            return True
        
        return any(path.startswith(prefix) for prefix in exempt_prefixes)
    
    def _is_test_request(self, request: Request) -> bool:
        """Check if request is from E2E testing infrastructure."""
        try:
            # Import testing config
            from testing_config import is_e2e_testing_enabled, is_test_request
            
            # Check if E2E testing is enabled
            if not is_e2e_testing_enabled():
                return False
            
            # Check if this is a test request
            return is_test_request(request)
            
        except ImportError:
            # Testing config not available
            return False
        except Exception as e:
            logger.debug(f"[CSRF] Error checking test request: {e}")
            return False
    
    async def _handle_csrf_token_request(self, request: Request, client_ip: str) -> Response:
        """Handle CSRF token request with rate limiting."""
        
        try:
            # Rate limiting for token requests
            await self._check_csrf_token_rate_limit(client_ip)
            
            # Generate new CSRF token
            csrf_token = await self._generate_csrf_token(client_ip)
            
            # Log token generation
            logger.info(f"🛡️ [CSRF] Generated new CSRF token for IP: {client_ip}")
            
            # Create response with token
            response_data = {
                "csrf_token": csrf_token,
                "expires_in": self.token_expiry_hours * 3600,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            response = Response(
                content=str(response_data).replace("'", '"'),
                media_type="application/json",
                status_code=200
            )
            
            # Set secure cookie
            response.set_cookie(
                key="csrf_token",
                value=csrf_token,
                max_age=self.token_expiry_hours * 3600,
                httponly=True,
                secure=settings.is_production(),
                samesite="strict"
            )
            
            return self._add_csrf_headers(response, request)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ [CSRF] Error generating CSRF token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to generate CSRF token"
            )
    
    async def _check_csrf_token_rate_limit(self, client_ip: str):
        """Rate limit CSRF token requests per IP."""
        rate_limit_key = f"csrf_token_requests:{client_ip}"
        
        try:
            request_count = await cache_manager.get(rate_limit_key, CacheLevel.L1_MEMORY) or 0
            
            if request_count >= self.max_tokens_per_ip:
                logger.warning(f"🚫 [CSRF] Rate limit exceeded for CSRF token requests from IP: {client_ip}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many CSRF token requests",
                    headers={"Retry-After": "3600"}
                )
            
            await cache_manager.set(
                rate_limit_key, 
                request_count + 1, 
                CacheLevel.L1_MEMORY, 
                ttl=3600
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ [CSRF] Error checking rate limit: {e}")
    
    async def _generate_csrf_token(self, client_ip: str) -> str:
        """Generate cryptographically secure CSRF token."""
        
        # Generate base token
        base_token = secrets.token_urlsafe(self.token_length)
        
        # Add timestamp and IP for validation
        timestamp = str(int(time.time()))
        
        # Create signed token
        token_data = f"{base_token}:{timestamp}:{client_ip}"
        signature = hmac.new(
            settings.jwt_secret.encode(),
            token_data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        csrf_token = f"{base_token}.{timestamp}.{signature[:16]}"
        
        # Store token in cache for validation
        token_key = f"csrf_token:{csrf_token}"
        token_info = {
            "client_ip": client_ip,
            "created_at": timestamp,
            "expires_at": str(int(time.time()) + (self.token_expiry_hours * 3600))
        }
        
        await cache_manager.set(
            token_key,
            token_info,
            CacheLevel.L1_MEMORY,
            ttl=self.token_expiry_hours * 3600
        )
        
        return csrf_token
    
    async def _validate_csrf_protection(self, request: Request, client_ip: str):
        """Comprehensive CSRF validation for protected requests."""
        
        # Step 1: Origin/Referer validation
        await self._validate_origin(request)
        
        # Step 2: CSRF token validation
        await self._validate_csrf_token(request, client_ip)
        
        logger.debug(f"✅ [CSRF] CSRF validation passed for {request.method} {request.url.path}")
    
    async def _validate_origin(self, request: Request):
        """Validate request origin and referer headers."""
        
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        host = request.headers.get("Host")
        
        # Get allowed origins from settings
        allowed_origins = set(settings.cors_origins)
        
        # Add current host to allowed origins
        if host:
            allowed_origins.add(f"https://{host}")
            allowed_origins.add(f"http://{host}")
        
        # Validate Origin header
        if origin:
            if origin not in allowed_origins:
                logger.warning(f"🚫 [CSRF] Invalid origin detected: {origin}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid origin"
                )
        
        # Validate Referer header (fallback)
        elif referer:
            referer_origin = self._extract_origin_from_referer(referer)
            if referer_origin and referer_origin not in allowed_origins:
                logger.warning(f"🚫 [CSRF] Invalid referer detected: {referer}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid referer"
                )
        
        else:
            # No Origin or Referer header (suspicious)
            logger.warning("🚫 [CSRF] Request missing Origin and Referer headers")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing origin information"
            )
    
    def _extract_origin_from_referer(self, referer: str) -> Optional[str]:
        """Extract origin from referer URL."""
        try:
            if referer.startswith("https://"):
                return "https://" + referer.split("/")[2]
            elif referer.startswith("http://"):
                return "http://" + referer.split("/")[2]
        except:
            pass
        return None
    
    async def _validate_csrf_token(self, request: Request, client_ip: str):
        """Validate CSRF token using double-submit cookie pattern."""
        
        # Get token from header
        token_header = request.headers.get("X-CSRF-Token")
        
        # Get token from cookie
        token_cookie = request.cookies.get("csrf_token")
        
        # Get token from body (for form submissions)
        token_body = None
        if request.method == "POST":
            try:
                # Check if it's form data
                content_type = request.headers.get("Content-Type", "")
                if "application/x-www-form-urlencoded" in content_type:
                    form = await request.form()
                    token_body = form.get("csrf_token")
            except:
                pass
        
        # Determine which token to use
        csrf_token = token_header or token_body
        
        if not csrf_token:
            logger.warning(f"🚫 [CSRF] No CSRF token provided in request from {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token required",
                headers={"X-CSRF-Required": "true"}
            )
        
        if not token_cookie:
            logger.warning(f"🚫 [CSRF] No CSRF cookie found from {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF cookie required"
            )
        
        # Double-submit cookie validation
        if csrf_token != token_cookie:
            logger.warning(f"🚫 [CSRF] CSRF token mismatch from {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token"
            )
        
        # Validate token structure and signature
        await self._validate_token_integrity(csrf_token, client_ip)
    
    async def _validate_token_integrity(self, token: str, client_ip: str):
        """Validate CSRF token integrity and expiration."""
        
        try:
            # Parse token structure
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("Invalid token format")
            
            base_token, timestamp, signature = parts
            
            # Verify token exists in cache
            token_key = f"csrf_token:{token}"
            token_info = await cache_manager.get(token_key, CacheLevel.L1_MEMORY)
            
            if not token_info:
                logger.warning(f"🚫 [CSRF] Token not found in cache: {token[:16]}...")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or expired CSRF token"
                )
            
            # Verify token expiration
            expires_at = int(token_info["expires_at"])
            if time.time() > expires_at:
                logger.warning(f"🚫 [CSRF] Expired CSRF token: {token[:16]}...")
                await cache_manager.delete(token_key, CacheLevel.L1_MEMORY)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Expired CSRF token"
                )
            
            # Verify IP match
            if token_info["client_ip"] != client_ip:
                logger.warning(f"🚫 [CSRF] IP mismatch for token: {token[:16]}... (expected: {token_info['client_ip']}, got: {client_ip})")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid CSRF token"
                )
            
            # Verify signature
            token_data = f"{base_token}:{timestamp}:{client_ip}"
            expected_signature = hmac.new(
                settings.jwt_secret.encode(),
                token_data.encode(),
                hashlib.sha256
            ).hexdigest()[:16]
            
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning(f"🚫 [CSRF] Invalid signature for token: {token[:16]}...")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid CSRF token"
                )
            
            logger.debug(f"✅ [CSRF] Token validation successful: {token[:16]}...")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"🚫 [CSRF] Token validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token"
            )
    
    def _add_csrf_headers(self, response: Response, request: Request) -> Response:
        """Add CSRF-related security headers to response."""
        
        # Add CSRF-related headers
        response.headers["X-CSRF-Protection"] = "enabled"
        
        if settings.is_production():
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
        
        return response


class CSRFTokenEndpoint:
    """Dedicated CSRF token endpoint for frontend integration."""
    
    @staticmethod
    async def get_csrf_token(request: Request) -> dict:
        """
        Get CSRF token for frontend use.
        This endpoint is handled by the middleware.
        """
        return {
            "message": "CSRF token endpoint handled by middleware",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Utility functions for manual CSRF operations
async def generate_csrf_token_for_user(user_id: str, ip_address: str) -> str:
    """Generate CSRF token for specific user (utility function)."""
    middleware = CSRFProtectionMiddleware(None)
    return await middleware._generate_csrf_token(ip_address)


async def validate_csrf_token_manually(token: str, ip_address: str) -> bool:
    """Manually validate CSRF token (utility function)."""
    try:
        middleware = CSRFProtectionMiddleware(None)
        await middleware._validate_token_integrity(token, ip_address)
        return True
    except:
        return False


def csrf_exempt(func):
    """Decorator to exempt specific endpoints from CSRF protection."""
    func._csrf_exempt = True
    return func