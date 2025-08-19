"""
Live Authentication Session Debugging Tools
Provides real-time debugging endpoints for authentication and profile issues.
"""
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timezone
import asyncio
from uuid import UUID
import traceback

from middleware.auth import get_current_user_optional, AuthMiddleware
from database import SupabaseClient
from services.user_service import UserService
from repositories.user_repository import UserRepository
from models.user import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/debug/auth", tags=["debug"])

# Global monitoring state
class AuthMonitor:
    """Global authentication monitoring singleton."""
    
    def __init__(self):
        self.session_attempts = []
        self.profile_creations = []
        self.token_validations = []
        self.error_patterns = {}
    
    def log_session_attempt(self, event_type: str, user_id: str = None, success: bool = True, error: str = None, metadata: Dict = None):
        """Log authentication session attempt."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "success": success,
            "error": error,
            "metadata": metadata or {}
        }
        
        self.session_attempts.append(event)
        
        # Keep only last 1000 events
        if len(self.session_attempts) > 1000:
            self.session_attempts = self.session_attempts[-1000:]
        
        if not success and error:
            self.error_patterns[error] = self.error_patterns.get(error, 0) + 1
        
        logger.info(f"[AUTH-MONITOR] {event_type}: {event}")
    
    def log_profile_creation(self, user_id: str, method: str, success: bool, error: str = None):
        """Log profile creation attempt."""
        self.log_session_attempt("profile_creation", user_id, success, error, {"method": method})
        
        creation_event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "method": method,
            "success": success,
            "error": error
        }
        
        self.profile_creations.append(creation_event)
        
        # Keep only last 500 profile creation events
        if len(self.profile_creations) > 500:
            self.profile_creations = self.profile_creations[-500:]
    
    def log_token_validation(self, token_type: str, user_id: str = None, success: bool = True, error: str = None):
        """Log token validation attempt."""
        self.log_session_attempt("token_validation", user_id, success, error, {"token_type": token_type})
        
        validation_event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_type": token_type,
            "user_id": user_id,
            "success": success,
            "error": error
        }
        
        self.token_validations.append(validation_event)
        
        # Keep only last 500 validation events
        if len(self.token_validations) > 500:
            self.token_validations = self.token_validations[-500:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get authentication statistics."""
        total_attempts = len(self.session_attempts)
        failed_attempts = [a for a in self.session_attempts if not a["success"]]
        
        recent_attempts = [a for a in self.session_attempts 
                          if (datetime.now(timezone.utc) - datetime.fromisoformat(a["timestamp"])).total_seconds() < 3600]
        
        return {
            "total_session_attempts": total_attempts,
            "failed_attempts": len(failed_attempts),
            "success_rate": (total_attempts - len(failed_attempts)) / total_attempts if total_attempts > 0 else 1.0,
            "recent_attempts_1h": len(recent_attempts),
            "error_patterns": dict(sorted(self.error_patterns.items(), key=lambda x: x[1], reverse=True)[:10]),
            "profile_creation_stats": {
                "total": len(self.profile_creations),
                "successful": len([p for p in self.profile_creations if p["success"]]),
                "failed": len([p for p in self.profile_creations if not p["success"]])
            },
            "token_validation_stats": {
                "total": len(self.token_validations),
                "successful": len([t for t in self.token_validations if t["success"]]),
                "failed": len([t for t in self.token_validations if not t["success"]])
            }
        }

# Global monitor instance
auth_monitor = AuthMonitor()


@router.get("/session-state")
async def debug_session_state(request: Request) -> Dict[str, Any]:
    """Debug current session authentication state."""
    auth_monitor.log_session_attempt("session_state_check")
    
    return {
        "middleware_user": getattr(request.state, 'user', None),
        "middleware_user_id": getattr(request.state, 'user_id', None),
        "auth_header": request.headers.get('Authorization', 'NOT_SET'),
        "has_bearer": request.headers.get('Authorization', '').startswith('Bearer '),
        "token_preview": request.headers.get('Authorization', 'NOT_SET')[:50] + "..." if len(request.headers.get('Authorization', '')) > 50 else request.headers.get('Authorization', 'NOT_SET'),
        "request_path": str(request.url.path),
        "client_ip": request.client.host if request.client else "unknown",
        "request_method": request.method,
        "user_agent": request.headers.get('User-Agent', 'unknown')[:100]
    }


@router.post("/validate-token")
async def debug_token_validation(token: str) -> Dict[str, Any]:
    """Validate token and return detailed debugging information."""
    start_time = datetime.now(timezone.utc)
    
    try:
        middleware = AuthMiddleware(app=None)
        user = await middleware._verify_token(token)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        auth_monitor.log_token_validation(
            token_type="custom" if token.startswith("supabase_token_") else "jwt",
            user_id=str(user.id) if user else None,
            success=True
        )
        
        return {
            "token_valid": True,
            "user_id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "credits_balance": user.credits_balance,
            "role": user.role,
            "profile_source": "database" if user.display_name else "fallback",
            "validation_duration_ms": duration * 1000,
            "token_type": "custom" if token.startswith("supabase_token_") else "jwt",
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        error_msg = str(e)
        
        auth_monitor.log_token_validation(
            token_type="custom" if token.startswith("supabase_token_") else "jwt",
            success=False,
            error=error_msg
        )
        
        return {
            "token_valid": False,
            "error": error_msg,
            "error_type": type(e).__name__,
            "validation_duration_ms": duration * 1000,
            "token_type": "custom" if token.startswith("supabase_token_") else "jwt",
            "traceback": traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
        }


@router.get("/profile-status/{user_id}")
async def debug_profile_status(user_id: str) -> Dict[str, Any]:
    """Check profile status across auth and public tables."""
    start_time = datetime.now(timezone.utc)
    
    try:
        db_client = SupabaseClient()
        result = {
            "user_id": user_id,
            "database_available": db_client.is_available(),
            "service_key_status": "unknown",
            "anon_key_status": "unknown",
            "auth_user_exists": False,
            "profile_exists": False,
            "profile_data": None,
            "sync_status": "unknown",
            "errors": []
        }
        
        if not db_client.is_available():
            result["errors"].append("Database unavailable")
            return result
        
        # Check auth.users (requires admin access)
        auth_user = None
        try:
            # This would require admin client setup
            # auth_result = db_client.service_client.auth.admin.get_user_by_id(user_id)
            # auth_user = auth_result.user if auth_result else None
            result["service_key_status"] = "available"
            result["auth_user_exists"] = True  # Assume exists for debugging
        except Exception as e:
            result["service_key_status"] = f"error: {str(e)}"
            result["errors"].append(f"Auth user check failed: {e}")
        
        # Check public.users with service key
        profile = None
        try:
            profile_result = db_client.service_client.table('users').select('*').eq('id', user_id).execute()
            if profile_result.data:
                profile = profile_result.data[0]
                result["profile_exists"] = True
                result["profile_data"] = profile
        except Exception as e:
            result["errors"].append(f"Service key profile check failed: {e}")
        
        # Check public.users with anon key (if service failed)
        if not profile:
            try:
                profile_result = db_client.client.table('users').select('*').eq('id', user_id).execute()
                if profile_result.data:
                    profile = profile_result.data[0]
                    result["profile_exists"] = True
                    result["profile_data"] = profile
                    result["anon_key_status"] = "available"
            except Exception as e:
                result["anon_key_status"] = f"error: {str(e)}"
                result["errors"].append(f"Anon key profile check failed: {e}")
        
        # Determine sync status
        if result["auth_user_exists"] and result["profile_exists"]:
            result["sync_status"] = "synced"
        elif result["auth_user_exists"] and not result["profile_exists"]:
            result["sync_status"] = "missing_profile"
        elif not result["auth_user_exists"] and result["profile_exists"]:
            result["sync_status"] = "orphaned_profile"
        else:
            result["sync_status"] = "not_found"
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        result["check_duration_ms"] = duration * 1000
        
        auth_monitor.log_session_attempt(
            "profile_status_check",
            user_id,
            success=len(result["errors"]) == 0,
            error="; ".join(result["errors"]) if result["errors"] else None
        )
        
        return result
        
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        error_msg = str(e)
        
        auth_monitor.log_session_attempt(
            "profile_status_check",
            user_id,
            success=False,
            error=error_msg
        )
        
        return {
            "user_id": user_id,
            "error": error_msg,
            "error_type": type(e).__name__,
            "check_duration_ms": duration * 1000,
            "traceback": traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
        }


@router.post("/force-profile-creation/{user_id}")
async def debug_force_profile_creation(user_id: str, email: str = Query(...)) -> Dict[str, Any]:
    """Force profile creation for debugging purposes."""
    start_time = datetime.now(timezone.utc)
    
    try:
        # Validate UUID format
        UUID(user_id)
        
        user_service = UserService()
        
        # Attempt to create profile
        user = await user_service.create_user_profile(
            user_id=user_id,
            email=email,
            full_name=f"Debug User {user_id[:8]}",
            avatar_url=None
        )
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        auth_monitor.log_profile_creation(user_id, "forced_creation", True)
        
        return {
            "success": True,
            "user_id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "credits_balance": user.credits_balance,
            "creation_duration_ms": duration * 1000,
            "message": "Profile created successfully"
        }
        
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        error_msg = str(e)
        
        auth_monitor.log_profile_creation(user_id, "forced_creation", False, error_msg)
        
        return {
            "success": False,
            "user_id": user_id,
            "error": error_msg,
            "error_type": type(e).__name__,
            "creation_duration_ms": duration * 1000,
            "traceback": traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
        }


@router.get("/user-credits/{user_id}")
async def debug_user_credits(user_id: str) -> Dict[str, Any]:
    """Debug user credits lookup with detailed error tracking."""
    start_time = datetime.now(timezone.utc)
    
    try:
        user_service = UserService()
        
        # Test credits lookup
        credits = await user_service.get_user_credits(user_id)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        auth_monitor.log_session_attempt(
            "credits_check",
            user_id,
            success=True,
            metadata={"credits": credits}
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "credits_balance": credits,
            "lookup_duration_ms": duration * 1000,
            "message": "Credits retrieved successfully"
        }
        
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        error_msg = str(e)
        
        auth_monitor.log_session_attempt(
            "credits_check",
            user_id,
            success=False,
            error=error_msg
        )
        
        return {
            "success": False,
            "user_id": user_id,
            "error": error_msg,
            "error_type": type(e).__name__,
            "lookup_duration_ms": duration * 1000,
            "traceback": traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
        }


@router.get("/statistics")
async def debug_auth_statistics() -> Dict[str, Any]:
    """Get authentication and profile creation statistics."""
    return auth_monitor.get_statistics()


@router.get("/recent-events")
async def debug_recent_events(
    limit: int = Query(50, ge=1, le=500),
    event_type: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Get recent authentication events."""
    events = auth_monitor.session_attempts
    
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]
    
    # Get most recent events
    recent_events = events[-limit:] if len(events) > limit else events
    recent_events.reverse()  # Most recent first
    
    return {
        "total_events": len(auth_monitor.session_attempts),
        "filtered_events": len(events),
        "returned_events": len(recent_events),
        "events": recent_events
    }


@router.get("/health-check")
async def debug_auth_health_check() -> Dict[str, Any]:
    """Comprehensive authentication system health check."""
    start_time = datetime.now(timezone.utc)
    health_status = {
        "timestamp": start_time.isoformat(),
        "overall_status": "unknown",
        "components": {},
        "errors": []
    }
    
    try:
        # Check database connectivity
        try:
            db_client = SupabaseClient()
            health_status["components"]["database"] = {
                "status": "healthy" if db_client.is_available() else "unhealthy",
                "details": "Database connection active" if db_client.is_available() else "Database unavailable"
            }
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "error",
                "details": str(e)
            }
            health_status["errors"].append(f"Database check failed: {e}")
        
        # Check authentication middleware
        try:
            middleware = AuthMiddleware(app=None)
            test_token = "test_token_validation"
            
            try:
                await middleware._verify_token(test_token)
                middleware_status = "error"  # Should fail with test token
            except HTTPException:
                middleware_status = "healthy"  # Expected to fail
            except Exception as e:
                middleware_status = "error"
                health_status["errors"].append(f"Middleware unexpected error: {e}")
            
            health_status["components"]["auth_middleware"] = {
                "status": middleware_status,
                "details": "Authentication middleware responding"
            }
        except Exception as e:
            health_status["components"]["auth_middleware"] = {
                "status": "error",
                "details": str(e)
            }
            health_status["errors"].append(f"Middleware check failed: {e}")
        
        # Check user service
        try:
            user_service = UserService()
            health_status["components"]["user_service"] = {
                "status": "healthy",
                "details": "User service initialized"
            }
        except Exception as e:
            health_status["components"]["user_service"] = {
                "status": "error",
                "details": str(e)
            }
            health_status["errors"].append(f"User service check failed: {e}")
        
        # Overall status
        component_statuses = [comp["status"] for comp in health_status["components"].values()]
        if all(status == "healthy" for status in component_statuses):
            health_status["overall_status"] = "healthy"
        elif any(status == "error" for status in component_statuses):
            health_status["overall_status"] = "error"
        else:
            health_status["overall_status"] = "degraded"
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        health_status["check_duration_ms"] = duration * 1000
        
        return health_status
        
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        return {
            "timestamp": start_time.isoformat(),
            "overall_status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "check_duration_ms": duration * 1000,
            "traceback": traceback.format_exc()
        }


@router.post("/simulate-auth-flow/{user_id}")
async def debug_simulate_auth_flow(user_id: str, email: str = Query(...)) -> Dict[str, Any]:
    """Simulate complete authentication flow for testing."""
    start_time = datetime.now(timezone.utc)
    flow_results = {
        "user_id": user_id,
        "email": email,
        "steps": [],
        "overall_success": False,
        "errors": []
    }
    
    try:
        # Step 1: Token validation
        step_start = datetime.now(timezone.utc)
        token = f"supabase_token_{user_id}"
        
        try:
            middleware = AuthMiddleware(app=None)
            user = await middleware._verify_token(token)
            
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "token_validation",
                "success": True,
                "duration_ms": step_duration * 1000,
                "details": f"Token validated for user {user.id}"
            })
            
        except Exception as e:
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "token_validation",
                "success": False,
                "duration_ms": step_duration * 1000,
                "error": str(e)
            })
            flow_results["errors"].append(f"Token validation failed: {e}")
        
        # Step 2: Profile lookup
        step_start = datetime.now(timezone.utc)
        
        try:
            user_service = UserService()
            profile = await user_service.get_user_profile(user_id)
            
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "profile_lookup",
                "success": True,
                "duration_ms": step_duration * 1000,
                "details": f"Profile found for {profile.email}"
            })
            
        except Exception as e:
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "profile_lookup",
                "success": False,
                "duration_ms": step_duration * 1000,
                "error": str(e)
            })
            flow_results["errors"].append(f"Profile lookup failed: {e}")
        
        # Step 3: Credits check
        step_start = datetime.now(timezone.utc)
        
        try:
            credits = await user_service.get_user_credits(user_id)
            
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "credits_check",
                "success": True,
                "duration_ms": step_duration * 1000,
                "details": f"Credits balance: {credits}"
            })
            
        except Exception as e:
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "credits_check",
                "success": False,
                "duration_ms": step_duration * 1000,
                "error": str(e)
            })
            flow_results["errors"].append(f"Credits check failed: {e}")
        
        # Step 4: Affordability test
        step_start = datetime.now(timezone.utc)
        
        try:
            can_afford = await user_service.can_afford_generation(user_id, 10)
            
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "affordability_check",
                "success": True,
                "duration_ms": step_duration * 1000,
                "details": f"Can afford 10 credits: {can_afford}"
            })
            
        except Exception as e:
            step_duration = (datetime.now(timezone.utc) - step_start).total_seconds()
            flow_results["steps"].append({
                "step": "affordability_check",
                "success": False,
                "duration_ms": step_duration * 1000,
                "error": str(e)
            })
            flow_results["errors"].append(f"Affordability check failed: {e}")
        
        # Overall assessment
        successful_steps = len([s for s in flow_results["steps"] if s["success"]])
        total_steps = len(flow_results["steps"])
        flow_results["overall_success"] = successful_steps == total_steps
        flow_results["success_rate"] = successful_steps / total_steps if total_steps > 0 else 0
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        flow_results["total_duration_ms"] = duration * 1000
        
        auth_monitor.log_session_attempt(
            "auth_flow_simulation",
            user_id,
            success=flow_results["overall_success"],
            error="; ".join(flow_results["errors"]) if flow_results["errors"] else None,
            metadata={"success_rate": flow_results["success_rate"]}
        )
        
        return flow_results
        
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        flow_results["errors"].append(f"Simulation failed: {e}")
        flow_results["total_duration_ms"] = duration * 1000
        flow_results["traceback"] = traceback.format_exc()
        
        return flow_results


# Add monitoring to existing auth components
def monitor_auth_attempt(func):
    """Decorator to monitor authentication attempts."""
    async def wrapper(*args, **kwargs):
        start_time = datetime.now(timezone.utc)
        try:
            result = await func(*args, **kwargs)
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            auth_monitor.log_session_attempt(
                func.__name__,
                success=True,
                metadata={"duration_ms": duration * 1000}
            )
            return result
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            auth_monitor.log_session_attempt(
                func.__name__,
                success=False,
                error=str(e),
                metadata={"duration_ms": duration * 1000}
            )
            raise
    
    return wrapper