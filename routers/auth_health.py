"""
Authentication Health and Monitoring Endpoints
Production-ready health checks, monitoring, and debugging endpoints for authentication system.
"""
import time
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse

from middleware.auth import get_current_user, get_current_user_optional
from utils.auth_monitor import get_auth_monitor
from utils.token_manager import get_token_manager, get_session_manager
from middleware.rate_limiting import get_rate_limiter, api_limit
from tools.auth_debug_toolkit import AuthDebugToolkit
from models.user import UserResponse
from config import settings

router = APIRouter(tags=["authentication-health"])  # Removed prefix to avoid path conflict

# Initialize monitoring components
auth_monitor = get_auth_monitor()
token_manager = get_token_manager()
session_manager = get_session_manager()
rate_limiter = get_rate_limiter()
debug_toolkit = AuthDebugToolkit()


@router.get("/health")
@api_limit()
async def auth_health_check(request: Request):
    """
    Comprehensive authentication system health check.
    
    Returns health status of all auth components with performance metrics.
    """
    try:
        start_time = time.time()
        
        # Get comprehensive system status
        system_status = await debug_toolkit.get_system_status()
        
        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000
        
        # Determine overall health
        critical_components = [
            system_status.database_available,
            system_status.cache_available,
            system_status.token_manager_active,
            system_status.security_monitor_active
        ]
        
        overall_health = "healthy" if all(critical_components) else "degraded"
        
        if not system_status.database_available:
            overall_health = "unhealthy"
        
        health_data = {
            "status": overall_health,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "response_time_ms": round(response_time_ms, 2),
            "environment": system_status.environment,
            "components": {
                "database": "healthy" if system_status.database_available else "unhealthy",
                "supabase_auth": "healthy" if system_status.supabase_auth_available else "degraded",
                "cache": "healthy" if system_status.cache_available else "degraded",
                "redis": "healthy" if system_status.redis_available else "degraded",
                "token_manager": "healthy" if system_status.token_manager_active else "unhealthy",
                "rate_limiter": "healthy" if system_status.rate_limiter_active else "degraded",
                "security_monitor": "healthy" if system_status.security_monitor_active else "degraded"
            },
            "metrics": {
                "active_sessions": system_status.active_sessions,
                "cached_tokens": system_status.cached_tokens,
                "blocked_ips": system_status.blocked_ips,
                "security_incidents_24h": system_status.security_incidents_24h
            }
        }
        
        # Set appropriate HTTP status code
        if overall_health == "healthy":
            status_code = status.HTTP_200_OK
        elif overall_health == "degraded":
            status_code = status.HTTP_206_PARTIAL_CONTENT
        else:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
        return JSONResponse(content=health_data, status_code=status_code)
        
    except Exception as e:
        return JSONResponse(
            content={
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "message": "Health check failed"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get("/metrics")
@api_limit()
async def auth_metrics(request: Request, current_user: Optional[UserResponse] = Depends(get_current_user_optional)):
    """
    Authentication system metrics and performance data.
    
    Provides detailed metrics for monitoring and alerting systems.
    """
    try:
        # Get security dashboard data
        dashboard_data = await auth_monitor.get_security_dashboard_data()
        
        # Get system status
        system_status = await debug_toolkit.get_system_status()
        
        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": settings.environment,
            "system_metrics": {
                "database_available": system_status.database_available,
                "supabase_auth_available": system_status.supabase_auth_available,
                "cache_available": system_status.cache_available,
                "redis_available": system_status.redis_available
            },
            "auth_metrics": {
                "active_sessions": system_status.active_sessions,
                "cached_tokens": system_status.cached_tokens,
                "blocked_ips": system_status.blocked_ips
            },
            "security_metrics": dashboard_data.get("summary", {}),
            "daily_metrics": dashboard_data.get("daily_metrics", [])[:7],  # Last 7 days
            "performance": {
                "avg_response_time_ms": 0,  # Would be calculated from actual metrics
                "success_rate_percentage": dashboard_data.get("summary", {}).get("login_success_rate_24h", 0),
                "error_rate_percentage": 100 - dashboard_data.get("summary", {}).get("login_success_rate_24h", 0)
            }
        }
        
        return JSONResponse(content=metrics)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metrics: {str(e)}"
        )


@router.get("/session-status")
@api_limit()
async def session_status(request: Request, current_user: UserResponse = Depends(get_current_user)):
    """
    Get current user session status and timeout information.
    
    Provides session timeout warnings and extension capabilities.
    """
    try:
        # Check session timeout status
        session_info = await session_manager.check_session_timeout(str(current_user.id))
        
        return {
            "user_id": str(current_user.id),
            "session_status": session_info,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "can_extend": session_info.get("can_extend", False)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session status: {str(e)}"
        )


@router.post("/session-extend")
@api_limit()
async def extend_session(request: Request, current_user: UserResponse = Depends(get_current_user)):
    """
    Extend current user session.
    
    Extends session timeout for active users.
    """
    try:
        # Extend session
        extended = await session_manager.extend_session(str(current_user.id))
        
        if extended:
            # Track activity
            await session_manager.track_user_activity(str(current_user.id), "session_extension")
            
            return {
                "message": "Session extended successfully",
                "user_id": str(current_user.id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "extended": True
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to extend session"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Session extension failed: {str(e)}"
        )


@router.get("/security-dashboard")
@api_limit()
async def security_dashboard(request: Request, current_user: Optional[UserResponse] = Depends(get_current_user_optional)):
    """
    Security dashboard data for monitoring interface.
    
    Provides security metrics, threats, and incidents for administrative monitoring.
    Note: In production, this should have additional authorization checks.
    """
    try:
        # In production, add role-based access control
        # if current_user and current_user.role not in ["admin", "security"]:
        #     raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        dashboard_data = await auth_monitor.get_security_dashboard_data()
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dashboard_data": dashboard_data,
            "environment": settings.environment
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get security dashboard: {str(e)}"
        )


@router.post("/validate-token")
@api_limit()
async def validate_token_endpoint(request: Request, token_data: Dict[str, str]):
    """
    Validate token with comprehensive diagnostics.
    
    Provides detailed token validation for debugging and monitoring.
    """
    try:
        token = token_data.get("token")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token is required"
            )
        
        # Validate token comprehensively
        validation_result = await debug_toolkit.validate_token_comprehensive(token)
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_result": {
                "is_valid": validation_result.is_valid,
                "token_type": validation_result.token_type,
                "user_id": validation_result.user_id,
                "email": validation_result.email,
                "expires_at": validation_result.expires_at.isoformat() if validation_result.expires_at else None,
                "is_expired": validation_result.is_expired,
                "error_message": validation_result.error_message,
                "validation_method": validation_result.validation_method,
                "metadata": validation_result.metadata
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token validation failed: {str(e)}"
        )


@router.get("/debug-report")
@api_limit()
async def debug_report(
    request: Request, 
    include_sensitive: bool = False,
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Generate comprehensive debug report.
    
    Provides detailed system diagnostics for troubleshooting.
    Note: In production, this should have strict authorization.
    """
    try:
        # In production, add strict authorization
        # if not current_user or current_user.role != "admin":
        #     raise HTTPException(status_code=403, detail="Admin access required")
        
        # Only allow sensitive data in development
        include_sensitive = include_sensitive and settings.debug
        
        report = await debug_toolkit.generate_debug_report(include_sensitive)
        
        return JSONResponse(content=report)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Debug report generation failed: {str(e)}"
        )


@router.post("/diagnose")
@api_limit()
async def diagnose_auth_issues(
    request: Request,
    diagnosis_data: Dict[str, Any],
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Diagnose authentication issues with detailed analysis.
    
    Provides comprehensive diagnostics for troubleshooting auth problems.
    """
    try:
        token = diagnosis_data.get("token")
        user_id = diagnosis_data.get("user_id")
        
        diagnosis = await debug_toolkit.diagnose_auth_issues(token, user_id)
        
        return JSONResponse(content=diagnosis)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Diagnosis failed: {str(e)}"
        )


@router.get("/rate-limit-status")
@api_limit()
async def rate_limit_status(request: Request):
    """
    Get current rate limiting status for the requesting client.
    
    Provides rate limit information for the current IP/user.
    """
    try:
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limits for different types
        rate_checks = {}
        
        for limit_type in ["auth_login", "auth_register", "api_standard"]:
            try:
                result = await rate_limiter.check_rate_limit(f"ip:{client_ip}", limit_type, request)
                rate_checks[limit_type] = {
                    "allowed": result["allowed"],
                    "limit": result["limit"],
                    "remaining": result["remaining"],
                    "reset_time": result["reset_time"],
                    "retry_after": result["retry_after"]
                }
            except Exception as e:
                rate_checks[limit_type] = {"error": str(e)}
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_ip": client_ip,
            "rate_limits": rate_checks
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rate limit status check failed: {str(e)}"
        )


@router.get("/system-info")
@api_limit()
async def system_info(request: Request):
    """
    Get basic authentication system information.
    
    Provides non-sensitive system information for monitoring.
    """
    try:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": settings.environment,
            "debug_mode": settings.debug,
            "development_mode": settings.development_mode,
            "jwt_expiration_seconds": settings.jwt_expiration_seconds,
            "version": "1.1.2",
            "features": {
                "token_refresh": True,
                "session_management": True,
                "rate_limiting": True,
                "security_monitoring": True,
                "csrf_protection": True,
                "audit_logging": True
            },
            "supported_auth_methods": [
                "email_password",
                "jwt_tokens",
                "refresh_tokens"
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"System info retrieval failed: {str(e)}"
        )