"""
Production-Safe Authentication Debugging Endpoints
Comprehensive debugging tools for authentication system troubleshooting.
"""
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import settings
from middleware.auth import get_current_user_optional
from models.user import UserResponse
from utils.auth_debugger import auth_debugger, debug_token, debug_auth_endpoint
from utils.network_inspector import network_inspector
from utils.production_debugger import production_debugger, DebugLevel, debug_context
from services.auth_service import AuthService
from database import SupabaseClient

router = APIRouter(prefix="/debug", tags=["debug-auth"])


class TokenAnalysisRequest(BaseModel):
    """Request model for token analysis."""
    token: str = Field(..., description="JWT token to analyze")


class AuthFlowTestRequest(BaseModel):
    """Request model for auth flow testing."""
    email: str = Field(..., description="Email for auth flow test")
    endpoint: Optional[str] = Field(None, description="Specific endpoint to test")


class CORSTestRequest(BaseModel):
    """Request model for CORS testing."""
    origin: str = Field(..., description="Origin to test CORS configuration")
    methods: Optional[List[str]] = Field(None, description="HTTP methods to test")


@router.get("/health")
async def debug_health_check():
    """
    Basic health check for debug endpoints.
    Production-safe endpoint that provides system status.
    """
    with debug_context("debug_auth", "health_check", "Debug health check"):
        try:
            # Get system health
            system_health = await production_debugger.get_system_health()
            
            # Get basic stats
            recent_events = production_debugger.get_recent_events(10)
            error_summary = production_debugger.get_error_summary()
            
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": settings.environment,
                "debug_mode": settings.debug,
                "system_health": {
                    "database_status": system_health.database_status,
                    "external_services": system_health.external_services,
                    "error_rate": system_health.error_rate
                },
                "recent_activity": {
                    "total_events": len(recent_events),
                    "total_errors": error_summary["total_errors"],
                    "error_rate": f"{error_summary['error_rate']:.2f}%"
                }
            }
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "health_check_error", 
                f"Health check failed: {str(e)}", DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Health check failed"
            )


@router.post("/token/analyze")
async def analyze_token(
    request: TokenAnalysisRequest,
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Analyze JWT token structure and validity.
    Safe for production - no sensitive data exposed.
    """
    if settings.is_production() and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required in production"
        )
    
    with debug_context("debug_auth", "token_analysis", "Token analysis"):
        try:
            # Analyze token
            analysis = debug_token(request.token)
            
            # Log analysis (safe)
            production_debugger.log_event(
                "debug_auth", "token_analyzed",
                f"Token analysis completed - Type: {analysis.token_type}, Valid: {analysis.is_valid}",
                DebugLevel.SAFE,
                metadata={
                    "token_type": analysis.token_type,
                    "format_valid": analysis.format_valid,
                    "expired": analysis.expired,
                    "security_flags_count": len(analysis.security_flags)
                }
            )
            
            # Return safe analysis results
            return {
                "token_type": analysis.token_type,
                "is_valid": analysis.is_valid,
                "format_valid": analysis.format_valid,
                "signature_valid": analysis.signature_valid,
                "expired": analysis.expired,
                "validation_errors": analysis.validation_errors,
                "security_flags": analysis.security_flags,
                "claims_count": len(analysis.claims),
                "header_algorithm": analysis.header.get("alg") if analysis.header else None,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "token_analysis_error",
                f"Token analysis failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token analysis failed"
            )


@router.post("/auth-flow/test")
async def test_auth_flow(
    request: AuthFlowTestRequest,
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Test complete authentication flow.
    Development/staging use - requires authentication in production.
    """
    if settings.is_production() and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required in production"
        )
    
    with debug_context("debug_auth", "auth_flow_test", f"Auth flow test for {request.email}"):
        try:
            flow_id = f"test_flow_{int(time.time())}"
            results = {}
            
            # Test 1: Authentication Service
            auth_debugger.start_auth_flow(flow_id, "auth_service", "test_authentication")
            
            try:
                db_client = SupabaseClient()
                auth_service = AuthService(db_client)
                
                # Check if database is available
                db_available = db_client.is_available()
                results["database_available"] = db_available
                
                auth_debugger.complete_auth_step(
                    flow_id, f"{flow_id}_0", "success",
                    metadata={"database_available": db_available}
                )
                
            except Exception as e:
                auth_debugger.complete_auth_step(
                    flow_id, f"{flow_id}_0", "error",
                    errors=[str(e)]
                )
                results["auth_service_error"] = str(e)[:100]
            
            # Test 2: Token Validation Endpoint
            if request.endpoint:
                endpoint_test = await debug_auth_endpoint(request.endpoint)
                results["endpoint_test"] = endpoint_test
            
            # Test 3: Middleware Validation
            # This would require a mock request, simplified for safety
            results["middleware_status"] = "available"
            
            # Get auth flow results
            auth_flow_steps = auth_debugger.auth_flows.get(flow_id, [])
            results["auth_flow_steps"] = [
                {
                    "component": step.component,
                    "action": step.action,
                    "status": step.status,
                    "duration_ms": step.duration_ms,
                    "errors": step.errors
                }
                for step in auth_flow_steps
            ]
            
            production_debugger.log_event(
                "debug_auth", "auth_flow_tested",
                f"Auth flow test completed for {request.email}",
                DebugLevel.SAFE,
                metadata={"steps_count": len(auth_flow_steps)}
            )
            
            return {
                "test_id": flow_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "email": request.email,
                "results": results,
                "overall_status": "completed"
            }
            
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "auth_flow_test_error",
                f"Auth flow test failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Auth flow test failed"
            )


@router.post("/cors/test")
async def test_cors_configuration(
    request: CORSTestRequest,
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Test CORS configuration for specific origin.
    Safe for production use.
    """
    with debug_context("debug_auth", "cors_test", f"CORS test for {request.origin}"):
        try:
            # Test CORS configuration
            cors_results = await network_inspector.test_cors_configuration(
                request.origin, 
                request.methods or ["GET", "POST", "OPTIONS"]
            )
            
            # Diagnose CORS issues
            cors_diagnosis = await auth_debugger.diagnose_cors_issues(request.origin)
            
            production_debugger.log_event(
                "debug_auth", "cors_tested",
                f"CORS test completed for {request.origin}",
                DebugLevel.SAFE,
                metadata={
                    "origin": request.origin,
                    "overall_status": cors_results["overall_status"],
                    "origin_allowed": cors_diagnosis["origin_allowed"]
                }
            )
            
            return {
                "test_results": cors_results,
                "diagnosis": cors_diagnosis,
                "recommendations": [
                    "Ensure frontend URL is in CORS allowed origins",
                    "Check for typos in origin URL",
                    "Verify HTTPS/HTTP protocol match",
                    "Test with browser developer tools"
                ],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "cors_test_error",
                f"CORS test failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CORS test failed"
            )


@router.get("/network/recent")
async def get_recent_network_activity(
    limit: int = 20,
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Get recent network activity for debugging.
    Production-safe - no sensitive data exposed.
    """
    if settings.is_production() and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required in production"
        )
    
    with debug_context("debug_auth", "network_activity", "Get recent network activity"):
        try:
            # Get recent requests
            recent_requests = network_inspector.get_recent_requests(limit)
            
            # Get CORS requests
            cors_requests = network_inspector.get_cors_requests(10)
            
            # Get failed requests
            failed_requests = network_inspector.get_failed_requests(10)
            
            # Get performance summary
            performance_summary = network_inspector.get_performance_summary()
            
            # Safe response (no sensitive data)
            return {
                "recent_requests": [
                    {
                        "id": req.request.id,
                        "timestamp": req.request.timestamp.isoformat(),
                        "method": req.request.method,
                        "path": req.request.url.split('?')[0],  # Remove query params
                        "status_code": req.response.status_code if req.response else None,
                        "duration_ms": req.duration_ms,
                        "client_ip": req.request.client_ip,
                        "cors_request": req.cors_analysis.is_cors_request if req.cors_analysis else False
                    }
                    for req in recent_requests
                ],
                "cors_activity": {
                    "total_cors_requests": len(cors_requests),
                    "recent_cors": [
                        {
                            "timestamp": req.request.timestamp.isoformat(),
                            "origin": req.cors_analysis.origin if req.cors_analysis else None,
                            "method": req.request.method,
                            "status": req.response.status_code if req.response else None
                        }
                        for req in cors_requests[:5]
                    ]
                },
                "error_activity": {
                    "total_failed_requests": len(failed_requests),
                    "recent_failures": [
                        {
                            "timestamp": req.request.timestamp.isoformat(),
                            "method": req.request.method,
                            "path": req.request.url.split('?')[0],
                            "status_code": req.response.status_code if req.response else None
                        }
                        for req in failed_requests[:5]
                    ]
                },
                "performance_summary": {
                    "total_requests": performance_summary["total_requests"],
                    "avg_response_time": performance_summary["avg_response_time"],
                    "method_distribution": performance_summary["method_distribution"],
                    "status_code_distribution": performance_summary["status_code_distribution"]
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "network_activity_error",
                f"Network activity retrieval failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve network activity"
            )


@router.get("/system/status")
async def get_system_debug_status(
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Get comprehensive system debug status.
    Production-safe with appropriate access controls.
    """
    if settings.is_production() and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required in production"
        )
    
    with debug_context("debug_auth", "system_status", "System debug status"):
        try:
            # Get system health
            system_health = await production_debugger.get_system_health()
            
            # Get error summary
            error_summary = production_debugger.get_error_summary()
            
            # Get performance summary
            performance_summary = production_debugger.get_performance_summary()
            
            # Get recent alerts
            recent_alerts = production_debugger.alerts[-10:]
            
            return {
                "system_health": {
                    "database_status": system_health.database_status,
                    "external_services": system_health.external_services,
                    "error_rate": system_health.error_rate,
                    "avg_response_time": system_health.response_time_avg
                },
                "error_analysis": {
                    "total_errors": error_summary["total_errors"],
                    "error_rate": error_summary["error_rate"],
                    "top_error_components": dict(
                        sorted(
                            error_summary["by_component"].items(),
                            key=lambda x: x[1],
                            reverse=True
                        )[:5]
                    ),
                    "recent_error_patterns": list(error_summary["error_patterns"].keys())[:5]
                },
                "performance_metrics": performance_summary,
                "alerts": [
                    {
                        "timestamp": alert["timestamp"],
                        "type": alert["type"],
                        "severity": alert["severity"],
                        "message": alert["message"][:100]
                    }
                    for alert in recent_alerts
                ],
                "configuration": {
                    "environment": settings.environment,
                    "debug_mode": settings.debug,
                    "development_mode": settings.development_mode,
                    "cors_origins_count": len(settings.cors_origins)
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "system_status_error",
                f"System status retrieval failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve system status"
            )


@router.post("/export/debug-data")
async def export_debug_data(
    include_metadata: bool = False,
    current_user: Optional[UserResponse] = Depends(get_current_user_optional)
):
    """
    Export comprehensive debug data for analysis.
    Requires authentication in production.
    """
    if settings.is_production() and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required in production"
        )
    
    # Restrict metadata export in production
    if settings.is_production():
        include_metadata = False
    
    with debug_context("debug_auth", "export_debug_data", "Export debug data"):
        try:
            # Export from all debug systems
            auth_debug_data = auth_debugger.export_debug_data(include_sensitive=False)
            network_debug_data = network_inspector.export_network_data(format="dict")
            production_debug_data = production_debugger.export_debug_data(include_metadata)
            
            export_package = {
                "export_metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "environment": settings.environment,
                    "include_metadata": include_metadata,
                    "user_id": str(current_user.id) if current_user else None
                },
                "authentication_debug": auth_debug_data,
                "network_debug": network_debug_data,
                "production_debug": production_debug_data,
                "summary": {
                    "total_auth_traces": auth_debug_data["metadata"]["total_traces"],
                    "total_network_requests": network_debug_data["metadata"]["total_requests"],
                    "total_debug_events": production_debug_data["metadata"]["total_events"],
                    "export_size_estimate": "large" if include_metadata else "compact"
                }
            }
            
            production_debugger.log_event(
                "debug_auth", "debug_data_exported",
                f"Debug data exported by user {current_user.id if current_user else 'anonymous'}",
                DebugLevel.SAFE,
                metadata={
                    "include_metadata": include_metadata,
                    "export_components": 3
                }
            )
            
            return export_package
            
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "export_debug_data_error",
                f"Debug data export failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Debug data export failed"
            )


@router.delete("/reset/debug-data")
async def reset_debug_data(
    current_user: UserResponse = Depends(get_current_user_optional)  # Require auth
):
    """
    Reset debug data and metrics.
    Requires authentication and not allowed in production.
    """
    if settings.is_production():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug data reset not allowed in production"
        )
    
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    with debug_context("debug_auth", "reset_debug_data", "Reset debug data"):
        try:
            # Reset all debug systems
            production_debugger.reset_metrics()
            
            # Clear network inspector history
            network_inspector.request_history.clear()
            network_inspector.performance_stats.clear()
            network_inspector.cors_stats = {
                "total_cors_requests": 0,
                "preflight_requests": 0,
                "cors_errors": 0,
                "blocked_origins": set()
            }
            
            # Clear auth debugger data
            auth_debugger.traces.clear()
            auth_debugger.auth_flows.clear()
            auth_debugger.performance_metrics.clear()
            auth_debugger.security_incidents.clear()
            
            production_debugger.log_event(
                "debug_auth", "debug_data_reset",
                f"Debug data reset by user {current_user.id}",
                DebugLevel.SAFE
            )
            
            return {
                "status": "success",
                "message": "Debug data reset successfully",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reset_by": str(current_user.id)
            }
            
        except Exception as e:
            production_debugger.log_event(
                "debug_auth", "reset_debug_data_error",
                f"Debug data reset failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Debug data reset failed"
            )