"""
DEBUG ENDPOINTS: Enhanced Live Session Debugging
Add these endpoints to your FastAPI app for debugging live sessions

PURPOSE: Debug authentication flow, profile lookups, and credit processing in real-time
USAGE: Call these endpoints during live user sessions to diagnose issues
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, Optional
import logging
import os
from datetime import datetime
from uuid import UUID
from config import settings

logger = logging.getLogger(__name__)

# Create debug router with production safety
debug_router = APIRouter(prefix="/api/v1/debug", tags=["Debug"])

# SECURITY: Production safety decorator
def require_development_mode(func):
    """Decorator to ensure debug endpoints are only accessible in development."""
    def wrapper(*args, **kwargs):
        # Multiple production environment checks
        production_indicators = [
            settings.is_production(),
            settings.environment.lower() == "production",
            os.getenv("RAILWAY_ENVIRONMENT") == "production",
            os.getenv("NODE_ENV") == "production",
            not settings.debug,
            not settings.development_mode
        ]
        
        if any(production_indicators):
            # Log security incident
            logger.error(f"🚨 [SECURITY-CRITICAL] Debug endpoint access attempted in production")
            logger.error(f"   Endpoint: {func.__name__}")
            logger.error(f"   Environment checks: {dict(zip(['is_production', 'env_production', 'railway_production', 'node_env_production', 'not_debug', 'not_development'], production_indicators))}")
            
            raise HTTPException(
                status_code=404,  # Hide existence of debug endpoints in production
                detail="Not Found"
            )
        
        # Additional safety: require explicit debug flags
        if not (settings.debug and settings.development_mode):
            logger.error(f"🚨 [SECURITY-VIOLATION] Debug endpoint access without proper development flags")
            raise HTTPException(
                status_code=403,
                detail="Debug endpoints require explicit development mode"
            )
        
        return func(*args, **kwargs)
    return wrapper

@debug_router.get("/auth/profile-status/{user_id}")
@require_development_mode
async def debug_profile_status(user_id: str) -> Dict[str, Any]:
    """
    Debug user profile status across all systems.
    Use this to check why profile lookups are failing.
    """
    try:
        from database import db
        from repositories.user_repository import UserRepository
        
        user_repo = UserRepository(db)
        debug_info = {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
            "recommendations": []
        }
        
        # Check 1: Database connectivity
        try:
            db_available = db.is_available()
            debug_info["checks"]["database_available"] = db_available
            if not db_available:
                debug_info["recommendations"].append("Database connection failed - check Supabase configuration")
        except Exception as e:
            debug_info["checks"]["database_error"] = str(e)
            debug_info["recommendations"].append(f"Database connection error: {e}")
        
        # Check 2: Service key validation
        try:
            service_key_valid = db._service_key_valid
            debug_info["checks"]["service_key_valid"] = service_key_valid
            if not service_key_valid:
                debug_info["recommendations"].append("Service key invalid - regenerate in Supabase dashboard")
        except Exception as e:
            debug_info["checks"]["service_key_error"] = str(e)
            debug_info["recommendations"].append("Service key validation failed")
        
        # Check 3: Profile lookup with service key
        try:
            profile_service = await user_repo.get_user_by_id(user_id, use_service_key=True)
            debug_info["checks"]["profile_service_key"] = {
                "found": profile_service is not None,
                "credits": profile_service.credits_balance if profile_service else None,
                "email": profile_service.email if profile_service else None
            }
        except Exception as e:
            debug_info["checks"]["profile_service_key"] = {
                "error": str(e),
                "error_type": type(e).__name__
            } 
            debug_info["recommendations"].append(f"Service key profile lookup failed: {e}")
        
        # Check 4: Profile lookup with anon key (requires JWT)
        try:
            profile_anon = await user_repo.get_user_by_id(user_id, use_service_key=False)
            debug_info["checks"]["profile_anon_key"] = {
                "found": profile_anon is not None,
                "credits": profile_anon.credits_balance if profile_anon else None
            }
        except Exception as e:
            debug_info["checks"]["profile_anon_key"] = {
                "error": str(e),
                "error_type": type(e).__name__
            }
            debug_info["recommendations"].append("Anon key lookup requires JWT token")
        
        # Check 5: Supabase auth.users table (if accessible)
        try:
            auth_user_result = db.service_client.auth.admin.get_user_by_id(user_id)
            debug_info["checks"]["supabase_auth_user"] = {
                "found": auth_user_result.user is not None,
                "email": auth_user_result.user.email if auth_user_result.user else None,
                "created_at": auth_user_result.user.created_at if auth_user_result.user else None
            }
        except Exception as e:
            debug_info["checks"]["supabase_auth_user"] = {
                "error": str(e),
                "error_type": type(e).__name__
            }
            debug_info["recommendations"].append("Auth user lookup may require admin privileges")
        
        # Generate final diagnosis
        if debug_info["checks"].get("profile_service_key", {}).get("found"):
            debug_info["diagnosis"] = "Profile exists and accessible via service key"
        elif debug_info["checks"].get("profile_anon_key", {}).get("found"):
            debug_info["diagnosis"] = "Profile exists but only accessible via anon key with JWT"
        else:
            debug_info["diagnosis"] = "Profile not found in public.users table"
            debug_info["recommendations"].append("Profile may need to be created or migrated from auth.users")
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Debug profile status failed: {e}")
        raise HTTPException(status_code=500, detail=f"Debug failed: {e}")


@debug_router.post("/auth/validate-token")
@require_development_mode
async def debug_validate_token(request_data: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate and debug authentication token.
    Use this to verify if user tokens are working properly.
    """
    try:
        token = request_data.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token required")
        
        from middleware.auth import AuthMiddleware
        
        # Create temporary auth middleware for validation
        auth_middleware = AuthMiddleware(app=None)
        
        debug_info = {
            "token_format": "unknown",
            "timestamp": datetime.utcnow().isoformat(),
            "validation_result": {},
            "recommendations": []
        }
        
        # Analyze token format
        if token.startswith("mock_token_"):
            debug_info["token_format"] = "mock_development"
            debug_info["recommendations"].append("Mock token - only works in development mode")
        elif token.startswith("supabase_token_"):
            debug_info["token_format"] = "custom_supabase"
            debug_info["recommendations"].append("Custom token format - requires database profile lookup")
        elif token.startswith("eyJ"):
            debug_info["token_format"] = "jwt"
            debug_info["recommendations"].append("Standard JWT token - requires Supabase auth validation")
        else:
            debug_info["token_format"] = "unknown"
            debug_info["recommendations"].append("Unknown token format - validation may fail")
        
        # Attempt token validation
        try:
            user_response = await auth_middleware._verify_token(token)
            debug_info["validation_result"] = {
                "valid": True,
                "user_id": str(user_response.id),
                "email": user_response.email,
                "credits_balance": user_response.credits_balance,
                "role": user_response.role
            }
            debug_info["diagnosis"] = "Token validation successful"
            
        except Exception as validation_error:
            debug_info["validation_result"] = {
                "valid": False,
                "error": str(validation_error),
                "error_type": type(validation_error).__name__
            }
            debug_info["diagnosis"] = f"Token validation failed: {validation_error}"
            debug_info["recommendations"].append("Check token expiration and format")
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Debug token validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Debug failed: {e}")


@debug_router.post("/auth/force-profile-creation/{user_id}")
@require_development_mode
async def debug_force_profile_creation(user_id: str, email: Optional[str] = None) -> Dict[str, Any]:
    """
    Force profile creation for emergency recovery.
    Use this when a user is authenticated but profile is missing.
    """
    try:
        from database import db
        from repositories.user_repository import UserRepository
        from datetime import datetime, timezone
        
        user_repo = UserRepository(db)
        
        profile_data = {
            "id": user_id,
            "email": email or f"user-{user_id}@authenticated.com",
            "display_name": "",
            "avatar_url": None,
            "credits_balance": 100,
            "role": "viewer",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        debug_info = {
            "user_id": user_id,
            "operation": "force_profile_creation",
            "timestamp": datetime.utcnow().isoformat(),
            "attempts": []
        }
        
        # Attempt 1: Service key creation
        try:
            service_result = db.service_client.table('users').insert(profile_data).execute()
            if service_result.data:
                debug_info["attempts"].append({
                    "method": "service_key",
                    "success": True,
                    "profile_created": True
                })
                debug_info["diagnosis"] = "Profile created successfully with service key"
                debug_info["profile"] = service_result.data[0]
                return debug_info
                
        except Exception as service_error:
            debug_info["attempts"].append({
                "method": "service_key", 
                "success": False,
                "error": str(service_error)
            })
        
        # Attempt 2: Check if profile already exists
        try:
            existing = db.service_client.table('users').select('*').eq('id', user_id).execute()
            if existing.data:
                debug_info["attempts"].append({
                    "method": "existing_check",
                    "success": True,
                    "profile_found": True
                })
                debug_info["diagnosis"] = "Profile already exists"
                debug_info["profile"] = existing.data[0]
                return debug_info
                
        except Exception as check_error:
            debug_info["attempts"].append({
                "method": "existing_check",
                "success": False,
                "error": str(check_error)
            })
        
        debug_info["diagnosis"] = "Profile creation failed - manual intervention required"
        debug_info["recommendations"] = [
            "Check Supabase service key permissions",
            "Verify RLS policies allow profile creation",
            "Check if user exists in auth.users table"
        ]
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Debug force profile creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Debug failed: {e}")


@debug_router.get("/auth/health-check")
@require_development_mode
async def debug_auth_health_check() -> Dict[str, Any]:
    """
    Comprehensive authentication system health check.
    Use this to verify all authentication components are working.
    """
    try:
        from database import db
        from repositories.user_repository import UserRepository
        from services.credit_transaction_service import credit_transaction_service
        
        health_info = {
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
            "overall_status": "unknown"
        }
        
        # Check database connectivity
        try:
            db_available = db.is_available()
            health_info["components"]["database"] = {
                "status": "healthy" if db_available else "unhealthy",
                "available": db_available
            }
        except Exception as e:
            health_info["components"]["database"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check service key status
        try:
            service_key_valid = db._service_key_valid
            health_info["components"]["service_key"] = {
                "status": "healthy" if service_key_valid else "degraded",
                "valid": service_key_valid
            }
        except Exception as e:
            health_info["components"]["service_key"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check credit service
        try:
            credit_health = await credit_transaction_service.health_check()
            health_info["components"]["credit_service"] = credit_health
        except Exception as e:
            health_info["components"]["credit_service"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check user repository
        try:
            user_repo = UserRepository(db)
            # Test with a non-existent user (should fail gracefully)
            await user_repo.get_user_credits("health_check_test_user")
            health_info["components"]["user_repository"] = {
                "status": "healthy",
                "note": "Repository accessible"
            }
        except Exception as e:
            # Expected to fail for non-existent user
            if "not found" in str(e).lower():
                health_info["components"]["user_repository"] = {
                    "status": "healthy",
                    "note": "Repository working (expected user not found error)"
                }
            else:
                health_info["components"]["user_repository"] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # Determine overall status
        statuses = [comp.get("status", "error") for comp in health_info["components"].values()]
        if all(status == "healthy" for status in statuses):
            health_info["overall_status"] = "healthy"
        elif any(status == "error" for status in statuses):
            health_info["overall_status"] = "unhealthy"
        else:
            health_info["overall_status"] = "degraded"
        
        # Add recommendations
        health_info["recommendations"] = []
        if health_info["components"].get("service_key", {}).get("status") != "healthy":
            health_info["recommendations"].append("Regenerate Supabase service key")
        if health_info["components"].get("database", {}).get("status") != "healthy":
            health_info["recommendations"].append("Check Supabase database connection")
        
        return health_info
        
    except Exception as e:
        logger.error(f"Debug health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")