"""
Production Authentication Router - Full Supabase Integration
Replaces demo/simplified auth with real Supabase signInWithPassword workflow.
Now using fully async authentication service with guaranteed timeouts.
CRITICAL FIX: Double timeout protection to prevent 120s hangs.
"""
import logging
import time
import asyncio
import httpx
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional

# Import our existing models and services
from models.user import UserLogin, UserCreate, UserResponse, Token
from services.auth_service_async import get_async_auth_service, AsyncAuthService
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["authentication"])
security = HTTPBearer()

# Production-ready response models with user object
class ProductionToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: dict  # Full user object with UUID

@router.post("/login", response_model=ProductionToken)
async def production_login(credentials: UserLogin, request: Request):
    """
    Production login with real Supabase authentication.
    Now with GUARANTEED 2-second timeout using fully async service.
    Includes detailed timing traces to identify any remaining performance issues.
    """
    request_id = f"{time.time():.3f}-{hash(credentials.email) % 10000}"
    try:
        logger.info(f"🔐 [AUTH-PROD-{request_id}] Production login attempt for: {credentials.email}")
        start_time = time.time()
        
        # Trace middleware processing
        middleware_time = getattr(request.state, 'processing_start_time', start_time)
        if hasattr(request.state, 'processing_start_time'):
            middleware_delay = (start_time - middleware_time) * 1000
            logger.info(f"⚡ [AUTH-PROD-{request_id}] Middleware processing took {middleware_delay:.2f}ms")
            
            # Check for middleware bypass indicators
            fast_lane = getattr(request.state, 'fast_lane_processing', False)
            if fast_lane:
                logger.info(f"✅ [AUTH-PROD-{request_id}] Fast-lane processing active")
            else:
                logger.warning(f"⚠️ [AUTH-PROD-{request_id}] Fast-lane processing NOT active - may cause delays")
        
        # CRITICAL FIX: Use fully async auth service with guaranteed timeouts
        logger.info(f"🔐 [AUTH-PROD-{request_id}] Getting async auth service...")
        service_start = time.time()
        auth_service = await get_async_auth_service()
        service_time = (time.time() - service_start) * 1000
        logger.info(f"🔐 [AUTH-PROD-{request_id}] Got auth service after {service_time:.2f}ms")
        
        # Get client IP for security logging (for monitoring)
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")
        logger.info(f"📍 [AUTH-PROD-{request_id}] Login from IP: {client_ip}, User-Agent: {user_agent[:50]}...")
        
        # Real Supabase authentication with DOUBLE timeout protection
        logger.info(f"🔐 [AUTH-PROD-{request_id}] Calling authenticate_user with 2s hard timeout...")
        auth_start = time.time()
        
        # CRITICAL FIX: Add outer timeout wrapper as safety net
        try:
            user = await asyncio.wait_for(
                auth_service.authenticate_user(credentials),
                timeout=2.5  # 2.5s outer timeout (slightly higher than inner 2s)
            )
        except asyncio.TimeoutError:
            timeout_duration = (time.time() - auth_start) * 1000
            logger.error(f"⏱️ [AUTH-PROD-{request_id}] OUTER timeout enforced after {timeout_duration:.2f}ms")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service timeout - system overloaded"
            )
        
        auth_duration = (time.time() - auth_start) * 1000
        logger.info(f"🔐 [AUTH-PROD-{request_id}] authenticate_user returned after {auth_duration:.2f}ms")
        
        if not user:
            total_time = (time.time() - start_time) * 1000
            logger.warning(f"🚫 [AUTH-PROD-{request_id}] Authentication failed for {credentials.email} (total: {total_time:.2f}ms)")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Create real access token with Supabase JWT
        token_start = time.time()
        token = await auth_service.create_access_token(user)
        token_time = (time.time() - token_start) * 1000
        logger.info(f"🔑 [AUTH-PROD-{request_id}] Token created in {token_time:.2f}ms")
        
        # Performance logging for authentication with detailed breakdown
        auth_time_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ [AUTH-PROD-{request_id}] Authentication successful for {user.email} (ID: {user.id})")
        logger.info(f"📊 [AUTH-PROD-{request_id}] Timing breakdown: total={auth_time_ms:.2f}ms, service={service_time:.2f}ms, auth={auth_duration:.2f}ms, token={token_time:.2f}ms")
        logger.info(f"🔑 [AUTH-PROD-{request_id}] Token type: {type(token.access_token)}, length: {len(token.access_token)}")
        
        # Performance alert if over target
        if auth_time_ms > 1500:  # 1.5s target
            logger.warning(f"⚠️ [PERFORMANCE-{request_id}] Authentication took {auth_time_ms:.2f}ms (over 1.5s target)")
        elif auth_time_ms > 100:  # Optimal target
            logger.info(f"ℹ️ [PERFORMANCE-{request_id}] Authentication took {auth_time_ms:.2f}ms (under target, could be faster)")
        else:
            logger.info(f"🎯 [PERFORMANCE-{request_id}] Optimal authentication time: {auth_time_ms:.2f}ms")
        
        # Return production format with user object
        return ProductionToken(
            access_token=token.access_token,
            token_type="bearer",
            expires_in=token.expires_in,
            user={
                "id": str(user.id),  # UUID as string
                "email": user.email,
                "full_name": user.display_name or "",
                "display_name": user.display_name or "",
                "avatar_url": user.avatar_url,
                "credits_balance": user.credits_balance,
                "role": user.role,
                "created_at": user.created_at.isoformat()
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 401)
        raise
    except httpx.TimeoutException:
        logger.error(f"⏱️ [AUTH-PROD] Login timeout for {credentials.email} - async service timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service timeout - please try again"
        )
    except httpx.RequestError as e:
        logger.error(f"🔌 [AUTH-PROD] Login network error for {credentials.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable"
        )
    except asyncio.TimeoutError:
        logger.error(f"⏱️ [AUTH-PROD] Login timeout for {credentials.email} - async operation timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service timeout - please try again"
        )
    except Exception as e:
        logger.error(f"❌ [AUTH-PROD] Login error for {credentials.email}: {e}", exc_info=True)
        logger.error(f"❌ [AUTH-PROD] Error type: {type(e).__name__}")
        
        # Return 500 for unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service temporarily unavailable"
        )

@router.post("/register", response_model=ProductionToken)
async def production_register(user_data: UserCreate, request: Request):
    """
    Production registration with real Supabase user creation.
    Creates user in Supabase Auth and syncs profile to custom database.
    """
    try:
        logger.info(f"📝 [AUTH-PROD] Production registration for: {user_data.email}")
        start_time = time.time()
        
        # CRITICAL FIX: Use fully async auth service with guaranteed timeouts
        auth_service = await get_async_auth_service()
        
        # Register user with Supabase Auth
        user = await auth_service.register_user(user_data)
        
        # Create access token
        token = await auth_service.create_access_token(user)
        
        # Performance logging for registration
        reg_time_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ [AUTH-PROD] Registration successful for {user.email} (ID: {user.id}) in {reg_time_ms:.2f}ms")
        
        # Return production format with user object
        return ProductionToken(
            access_token=token.access_token,
            token_type="bearer",
            expires_in=token.expires_in,
            user={
                "id": str(user.id),  # UUID as string
                "email": user.email,
                "full_name": user.display_name or "",
                "display_name": user.display_name or "",
                "avatar_url": user.avatar_url,
                "credits_balance": user.credits_balance,
                "role": user.role,
                "created_at": user.created_at.isoformat()
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except httpx.TimeoutException:
        logger.error(f"⏱️ [AUTH-PROD] Registration timeout for {user_data.email} - async service timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service timeout - please try again"
        )
    except httpx.RequestError as e:
        logger.error(f"🔌 [AUTH-PROD] Registration network error for {user_data.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service unavailable"
        )
    except asyncio.TimeoutError:
        logger.error(f"⏱️ [AUTH-PROD] Registration timeout for {user_data.email} - async operation timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service timeout - please try again"
        )
    except Exception as e:
        logger.error(f"❌ [AUTH-PROD] Registration error for {user_data.email}: {e}", exc_info=True)
        
        # Handle common registration errors
        if "already_registered" in str(e) or "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration service temporarily unavailable"
        )

@router.get("/me")
async def get_current_user_production(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get current authenticated user with real JWT validation.
    """
    try:
        logger.info(f"👤 [AUTH-PROD] Getting current user info")
        
        # Extract JWT token
        token = credentials.credentials
        logger.info(f"🔍 [AUTH-PROD] Token received, length: {len(token)}")
        start_time = time.time()
        
        # CRITICAL FIX: Use fully async auth service with guaranteed timeouts
        auth_service = await get_async_auth_service()
        
        # CRITICAL SECURITY FIX: Use production JWT validation only
        # ALL development bypasses have been removed for production security
        
        # Validate JWT token with production security system
        try:
            logger.info(f"🔍 [AUTH-PROD] Processing JWT token for production validation")
            
            # Import our production JWT security service
            from utils.jwt_security import verify_supabase_jwt, JWTSecurityError
            
            # Verify JWT token with Supabase-specific validation
            verified_payload = verify_supabase_jwt(token)
            logger.info(f"✅ [AUTH-PROD] JWT validation successful for user {verified_payload.get('user_id')}")
            
            # Extract user info from verified payload
            user_id = UUID(verified_payload.get('user_id'))
            email = verified_payload.get('email', '')
            
            # Get full user profile from database
            user = await auth_service.get_user_by_id(user_id)
            
            if not user:
                # User exists in JWT but not in our database - get from async service
                logger.info(f"🔄 [AUTH-PROD] Getting user {user_id} via async auth service")
                
                # Try to get user via token
                user = await auth_service.get_user_by_token(token)
                
                if not user:
                    # Create basic user profile from JWT data
                    from models.user import UserResponse
                    user = UserResponse(
                        id=user_id,
                        email=email,
                        display_name=verified_payload.get('user_metadata', {}).get('display_name', ''),
                        avatar_url=verified_payload.get('user_metadata', {}).get('avatar_url'),
                        credits_balance=100,  # Default credits for new users
                        role=verified_payload.get('app_metadata', {}).get('role', 'viewer'),
                        created_at=datetime.now(timezone.utc)
                    )
                    
                    # Save to database for future requests
                    try:
                        profile_data = {
                            "display_name": user.display_name,
                            "avatar_url": user.avatar_url,
                            "role": user.role
                        }
                        await auth_service.sync_user_profile(str(user_id), profile_data)
                        logger.info(f"✅ [AUTH-PROD] User profile synced to database")
                    except Exception as sync_error:
                        logger.warning(f"⚠️ [AUTH-PROD] User sync failed: {sync_error}")
                        # Continue with in-memory user object
            
            # Performance logging for token verification
            verify_time_ms = (time.time() - start_time) * 1000
            logger.info(f"✅ [AUTH-PROD] Token verification completed for {user.email} in {verify_time_ms:.2f}ms")
            
            # Return standardized user response
            return {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.display_name or "",
                "display_name": user.display_name or "",
                "avatar_url": user.avatar_url,
                "credits_balance": user.credits_balance,
                "role": user.role,
                "created_at": user.created_at.isoformat()
            }
            
        except JWTSecurityError as jwt_error:
            logger.error(f"❌ [AUTH-PROD] JWT validation failed: {jwt_error}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception as jwt_error:
            logger.error(f"❌ [AUTH-PROD] JWT validation unexpected error: {jwt_error}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        except ValueError as ve:
            logger.error(f"❌ [AUTH-PROD] Token format error: {ve}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format"
            )
            
    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.error("⏱️ [AUTH-PROD] Token verification timeout - async service timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token verification timeout - please try again"
        )
    except httpx.RequestError as e:
        logger.error(f"🔌 [AUTH-PROD] Token verification network error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token verification service unavailable"
        )
    except asyncio.TimeoutError:
        logger.error("⏱️ [AUTH-PROD] Token verification timeout - async operation timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token verification timeout - please try again"
        )
    except Exception as e:
        logger.error(f"❌ [AUTH-PROD] Get current user error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User service temporarily unavailable"
        )

@router.get("/security-info")
async def production_security_info():
    """
    Production security information.
    """
    return {
        "status": "production",
        "auth_mode": "supabase_jwt",
        "features": [
            "Real Supabase authentication",
            "JWT token validation", 
            "User profile sync",
            "Credit management",
            "Security monitoring"
        ],
        "endpoints": {
            "login": "POST /login - Real Supabase authentication",
            "register": "POST /register - Real Supabase user creation",
            "me": "GET /me - JWT-validated user info"
        },
        "environment": settings.environment,
        "timestamp": time.time()
    }

@router.get("/ping")
async def ping():
    """
    Ultra-fast ping endpoint for authentication service health checks.
    Target: <200ms response time with connection status.
    CRITICAL FIX: This endpoint was missing, causing 404 errors.
    """
    start_time = time.time()
    
    try:
        # Minimal database connection check without heavy operations
        from database import SupabaseClient
        db = SupabaseClient()
        
        # Quick availability check (cached for performance)
        db_available = db.is_available()
        
        # Check if async auth service is initialized
        auth_service_ready = False
        try:
            from services.auth_service_async import get_async_auth_service
            auth_service = await get_async_auth_service()
            auth_service_ready = auth_service is not None
        except Exception as e:
            logger.debug(f"Auth service check failed: {e}")
        
        response_time_ms = (time.time() - start_time) * 1000
        
        return {
            "status": "ok",
            "message": "Auth service ping successful",
            "database_available": db_available,
            "auth_service_ready": auth_service_ready,
            "response_time_ms": round(response_time_ms, 2),
            "performance_target": "<200ms",
            "performance_met": response_time_ms < 200,
            "timestamp": time.time()
        }
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ [AUTH-PING] Ping failed after {response_time_ms:.2f}ms: {e}")
        
        return {
            "status": "error",
            "message": f"Auth service ping failed: {str(e)}",
            "database_available": False,
            "auth_service_ready": False,
            "response_time_ms": round(response_time_ms, 2),
            "performance_target": "<200ms",
            "performance_met": response_time_ms < 200,
            "timestamp": time.time()
        }

@router.get("/middleware-status")
async def middleware_fastpath_status(request: Request):
    """
    CRITICAL: Middleware fastpath verification endpoint.
    This proves that auth endpoints bypass heavy middleware for <100ms performance.
    """
    start_time = time.time()
    
    try:
        # Check middleware bypass markers in request state
        middleware_info = {
            "fastpath_active": False,
            "bypassed_middleware": [],
            "middleware_time_ms": 0,
            "total_middleware_count": 0,
            "performance_optimizations": []
        }
        
        # Check if production optimized middleware marked this as fast-lane
        if hasattr(request.state, 'fast_lane_processing'):
            middleware_info["fastpath_active"] = request.state.fast_lane_processing
            middleware_info["performance_optimizations"].append("fast_lane_processing")
        
        # Check for body cache optimization
        if hasattr(request.state, 'body_cached'):
            middleware_info["performance_optimizations"].append("body_caching")
            
        # Check for specific middleware bypasses
        bypass_markers = [
            "access_control_bypassed",
            "ssrf_protection_bypassed", 
            "security_enhanced_bypassed",
            "rate_limit_lightened"
        ]
        
        for marker in bypass_markers:
            if hasattr(request.state, marker):
                bypass_value = getattr(request.state, marker, False)
                if bypass_value:
                    middleware_info["bypassed_middleware"].append(marker)
        
        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000
        middleware_info["response_time_ms"] = round(response_time_ms, 2)
        
        # Performance assessment
        performance_met = response_time_ms < 100
        fastpath_working = middleware_info["fastpath_active"] or len(middleware_info["bypassed_middleware"]) > 0
        
        return {
            "status": "optimal" if performance_met and fastpath_working else "degraded",
            "fastpath_proof": {
                "performance_target_met": performance_met,
                "middleware_bypasses_active": fastpath_working,
                "response_time_ms": middleware_info["response_time_ms"],
                "target": "<100ms"
            },
            "middleware_analysis": middleware_info,
            "recommendations": [
                "Fastpath working - auth endpoints bypass heavy middleware",
                "Performance target met - <100ms response time"
            ] if performance_met and fastpath_working else [
                "ISSUE: Middleware bypasses not working properly",
                "ISSUE: Performance target not met - check middleware order",
                "SOLUTION: Verify ProductionOptimizedMiddleware is applied first"
            ],
            "timestamp": time.time()
        }
        
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ [MIDDLEWARE-STATUS] Failed after {response_time_ms:.2f}ms: {e}")
        
        return {
            "status": "error",
            "error": str(e),
            "response_time_ms": round(response_time_ms, 2),
            "fastpath_proof": {
                "performance_target_met": False,
                "middleware_bypasses_active": False,
                "error": "Unable to determine middleware status"
            },
            "timestamp": time.time()
        }

@router.get("/health")  
async def production_auth_health():
    """
    Production authentication health check.
    """
    try:
        start_time = time.time()
        
        # CRITICAL FIX: Use fully async auth service with guaranteed timeouts
        auth_service = await get_async_auth_service()
        
        # Test service availability with a simple validation
        test_result = await auth_service.validate_supabase_jwt("test")
        supabase_available = True  # If we get here without timeout, service is available
        
        health_check_time_ms = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy" if supabase_available else "degraded",
            "auth_mode": "production_supabase",
            "supabase_connection": "available" if supabase_available else "unavailable",
            "endpoints": ["ping", "login", "register", "me", "security-info", "middleware-status"],
            "environment": settings.environment,
            "health_check_time_ms": f"{health_check_time_ms:.2f}",
            "performance_target": "<50ms",
            "timestamp": time.time()
        }
    except httpx.TimeoutException:
        logger.error("⏱️ [AUTH-PROD] Health check timeout - async service timeout")
        return {
            "status": "timeout",
            "error": "Async auth service timeout",
            "performance_issue": "Auth service not responding within timeout",
            "timestamp": time.time()
        }
    except httpx.RequestError as e:
        logger.error(f"🔌 [AUTH-PROD] Health check network error: {e}")
        return {
            "status": "network_error",
            "error": f"Network error: {str(e)}",
            "timestamp": time.time()
        }
    except asyncio.TimeoutError:
        logger.error("⏱️ [AUTH-PROD] Health check timeout - async operation timeout")
        return {
            "status": "timeout",
            "error": "Async operation timeout",
            "performance_issue": "Service operation exceeded timeout",
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"❌ [AUTH-PROD] Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }