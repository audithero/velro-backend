"""
Refactored authentication middleware with proper error handling.
Returns clean 401s with CORS headers, never crashes.
"""
import os
import logging
from typing import Optional, Dict, Any
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware that verifies JWT tokens."""
    
    def __init__(self, app: ASGIApp, public_paths: list = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/health",
            "/__health",
            "/__version",
            "/__diag",
            "/__config",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]
    
    async def dispatch(self, request: Request, call_next):
        """Process request with authentication check."""
        request_id = getattr(request.state, "request_id", "unknown")
        path = request.url.path
        
        # Skip auth for public paths
        if self._is_public_path(path):
            logger.debug(f"[{request_id}] Auth bypass for public path: {path}")
            return await call_next(request)
        
        # Extract token
        auth_header = request.headers.get("Authorization", "")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.info(f"[{request_id}] Missing or invalid auth header for {path}")
            return self._unauthorized_response(request_id, "Missing authentication token")
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        try:
            # Verify token
            user_data = await self._verify_token(token)
            
            if not user_data:
                logger.info(f"[{request_id}] Invalid token for {path}")
                return self._unauthorized_response(request_id, "Invalid or expired token")
            
            # Attach user to request
            request.state.user = user_data
            request.state.user_id = user_data.get("id")
            
            logger.debug(f"[{request_id}] Auth success for user {request.state.user_id}")
            
            # Continue processing
            response = await call_next(request)
            return response
            
        except Exception as e:
            logger.error(f"[{request_id}] Auth middleware error: {e}")
            return self._unauthorized_response(request_id, "Authentication failed")
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (no auth required)."""
        for public_path in self.public_paths:
            if path.startswith(public_path):
                return True
        return False
    
    async def _verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return user data."""
        try:
            import os
            
            # Check if using Supabase auth
            use_supabase = os.getenv("USE_SUPABASE_AUTH", "true").lower() == "true"
            
            if use_supabase:
                # Use Supabase auth service for proper JWT verification
                from services.supabase_auth import SupabaseAuth
                auth_service = SupabaseAuth()
                
                # verify_jwt returns Dict with user data
                user_data = auth_service.verify_jwt(token)
                
                # Ensure we have the expected structure
                if isinstance(user_data, dict) and "sub" in user_data:
                    # Convert Supabase format to expected format
                    return {
                        "id": user_data.get("sub"),
                        "email": user_data.get("email"),
                        "role": user_data.get("role", "authenticated"),
                        **user_data  # Include all other claims
                    }
                
                return user_data
            else:
                # Use legacy auth service
                from services.auth_service_async import get_async_auth_service
                auth_service = await get_async_auth_service()
                
                # For legacy, try to use jwt_security utility directly
                from utils.jwt_security import verify_supabase_jwt
                user_data = verify_supabase_jwt(token)
                return user_data
            
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None
    
    def _unauthorized_response(self, request_id: str, detail: str) -> Response:
        """Return 401 Unauthorized response with proper headers."""
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "detail": detail,
                "request_id": request_id,
                "error": "unauthorized",
            },
            headers={
                "X-Request-ID": request_id,
                "WWW-Authenticate": 'Bearer realm="api"',
            }
        )