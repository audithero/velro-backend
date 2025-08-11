"""
Advanced Authentication Debugging Utilities
Enterprise-grade debugging toolkit for authentication systems.
"""
import json
import time
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import asyncio
import httpx
from fastapi import Request, Response
import jwt as pyjwt
from urllib.parse import urlparse

from config import settings
from database import SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class AuthFlowStep:
    """Represents a single step in the authentication flow."""
    step_id: str
    timestamp: datetime
    component: str
    action: str
    status: str
    duration_ms: float
    metadata: Dict[str, Any]
    errors: List[str]


@dataclass
class TokenAnalysis:
    """Comprehensive token analysis results."""
    token_type: str
    is_valid: bool
    format_valid: bool
    signature_valid: bool
    expired: bool
    claims: Dict[str, Any]
    header: Dict[str, Any]
    validation_errors: List[str]
    security_flags: List[str]


@dataclass
class RequestTrace:
    """Request tracing information."""
    trace_id: str
    timestamp: datetime
    method: str
    path: str
    headers: Dict[str, str]
    query_params: Dict[str, str]
    client_ip: str
    user_agent: str
    auth_header: Optional[str]
    response_status: Optional[int]
    response_time_ms: Optional[float]
    errors: List[str]


class AuthenticationDebugger:
    """Advanced authentication debugging and diagnostic system."""
    
    def __init__(self, enable_logging: bool = True, log_sensitive_data: bool = False):
        self.enable_logging = enable_logging
        self.log_sensitive_data = log_sensitive_data
        self.traces: Dict[str, RequestTrace] = {}
        self.auth_flows: Dict[str, List[AuthFlowStep]] = {}
        self.performance_metrics: Dict[str, List[float]] = {}
        self.security_incidents: List[Dict[str, Any]] = []
        
    def generate_trace_id(self) -> str:
        """Generate unique trace ID for request tracking."""
        return f"trace_{int(time.time() * 1000)}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    def start_auth_flow(self, flow_id: str, component: str, action: str) -> str:
        """Start tracking an authentication flow."""
        if flow_id not in self.auth_flows:
            self.auth_flows[flow_id] = []
        
        step = AuthFlowStep(
            step_id=f"{flow_id}_{len(self.auth_flows[flow_id])}",
            timestamp=datetime.now(timezone.utc),
            component=component,
            action=action,
            status="started",
            duration_ms=0.0,
            metadata={},
            errors=[]
        )
        
        self.auth_flows[flow_id].append(step)
        return step.step_id
    
    def complete_auth_step(self, flow_id: str, step_id: str, status: str, 
                          metadata: Dict[str, Any] = None, errors: List[str] = None):
        """Complete an authentication flow step."""
        if flow_id not in self.auth_flows:
            return
        
        for step in self.auth_flows[flow_id]:
            if step.step_id == step_id:
                step.status = status
                step.duration_ms = (datetime.now(timezone.utc) - step.timestamp).total_seconds() * 1000
                step.metadata = metadata or {}
                step.errors = errors or []
                break
    
    def analyze_jwt_token(self, token: str) -> TokenAnalysis:
        """Comprehensive JWT token analysis."""
        analysis = TokenAnalysis(
            token_type="unknown",
            is_valid=False,
            format_valid=False,
            signature_valid=False,
            expired=False,
            claims={},
            header={},
            validation_errors=[],
            security_flags=[]
        )
        
        try:
            # Check token format
            if not token or not isinstance(token, str):
                analysis.validation_errors.append("Invalid token format: empty or not string")
                return analysis
            
            # Handle custom token formats
            if token.startswith(("mock_token_", "emergency_token_", "supabase_token_")):
                analysis.token_type = "custom"
                analysis.format_valid = True
                
                if token.startswith("mock_token_"):
                    analysis.security_flags.append("DEVELOPMENT_TOKEN")
                elif token.startswith("emergency_token_"):
                    analysis.security_flags.append("EMERGENCY_TOKEN")
                    analysis.security_flags.append("HIGH_RISK")
                
                if settings.is_production():
                    analysis.security_flags.append("PRODUCTION_SECURITY_VIOLATION")
                    analysis.validation_errors.append("Custom tokens not allowed in production")
                
                return analysis
            
            # JWT token analysis
            analysis.token_type = "jwt"
            
            # Decode header without verification to check format
            try:
                header = pyjwt.get_unverified_header(token)
                analysis.header = header
                analysis.format_valid = True
            except Exception as e:
                analysis.validation_errors.append(f"Invalid JWT header: {str(e)}")
                return analysis
            
            # Decode payload without verification
            try:
                payload = pyjwt.decode(token, options={"verify_signature": False})
                analysis.claims = payload
            except Exception as e:
                analysis.validation_errors.append(f"Invalid JWT payload: {str(e)}")
                return analysis
            
            # Check expiration
            if "exp" in payload:
                exp_timestamp = payload["exp"]
                if datetime.fromtimestamp(exp_timestamp, timezone.utc) < datetime.now(timezone.utc):
                    analysis.expired = True
                    analysis.validation_errors.append("Token expired")
            
            # Security analysis
            if "aud" not in payload:
                analysis.security_flags.append("NO_AUDIENCE_CLAIM")
            
            if "iss" not in payload:
                analysis.security_flags.append("NO_ISSUER_CLAIM")
            
            if "sub" not in payload:
                analysis.security_flags.append("NO_SUBJECT_CLAIM")
            
            # Check token age
            if "iat" in payload:
                issued_at = datetime.fromtimestamp(payload["iat"], timezone.utc)
                age_hours = (datetime.now(timezone.utc) - issued_at).total_seconds() / 3600
                if age_hours > 24:
                    analysis.security_flags.append("OLD_TOKEN")
            
            analysis.is_valid = len(analysis.validation_errors) == 0 and not analysis.expired
            
        except Exception as e:
            analysis.validation_errors.append(f"Token analysis error: {str(e)}")
        
        return analysis
    
    def trace_request(self, request: Request) -> str:
        """Start tracing a request."""
        trace_id = self.generate_trace_id()
        
        # Extract safe headers (no sensitive data)
        safe_headers = {}
        for header, value in request.headers.items():
            if header.lower() not in ["authorization", "cookie", "x-api-key"]:
                safe_headers[header] = value
            else:
                safe_headers[header] = "***REDACTED***"
        
        auth_header = request.headers.get("authorization")
        if auth_header and not self.log_sensitive_data:
            auth_header = f"{auth_header[:20]}...***REDACTED***" if len(auth_header) > 20 else "***REDACTED***"
        
        trace = RequestTrace(
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc),
            method=request.method,
            path=str(request.url.path),
            headers=safe_headers,
            query_params=dict(request.query_params),
            client_ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown"),
            auth_header=auth_header,
            response_status=None,
            response_time_ms=None,
            errors=[]
        )
        
        self.traces[trace_id] = trace
        return trace_id
    
    def complete_request_trace(self, trace_id: str, response_status: int, errors: List[str] = None):
        """Complete request tracing."""
        if trace_id in self.traces:
            trace = self.traces[trace_id]
            trace.response_status = response_status
            trace.response_time_ms = (datetime.now(timezone.utc) - trace.timestamp).total_seconds() * 1000
            trace.errors = errors or []
    
    def record_security_incident(self, incident_type: str, description: str, 
                                metadata: Dict[str, Any] = None, severity: str = "medium"):
        """Record security incidents for analysis."""
        incident = {
            "id": f"incident_{int(time.time() * 1000)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": incident_type,
            "description": description,
            "severity": severity,
            "metadata": metadata or {},
            "environment": settings.environment
        }
        
        self.security_incidents.append(incident)
        
        # Log based on severity
        if severity == "critical":
            logger.critical(f"🚨 SECURITY INCIDENT: {incident_type} - {description}")
        elif severity == "high":
            logger.error(f"🚨 SECURITY ALERT: {incident_type} - {description}")
        else:
            logger.warning(f"⚠️ SECURITY WARNING: {incident_type} - {description}")
    
    async def diagnose_cors_issues(self, origin: str = None) -> Dict[str, Any]:
        """Diagnose CORS configuration issues."""
        diagnosis = {
            "cors_enabled": True,
            "allowed_origins": settings.cors_origins,
            "origin_allowed": False,
            "issues": [],
            "recommendations": []
        }
        
        if origin:
            if origin in settings.cors_origins:
                diagnosis["origin_allowed"] = True
            elif "*" in settings.cors_origins:
                diagnosis["origin_allowed"] = True
            else:
                diagnosis["origin_allowed"] = False
                diagnosis["issues"].append(f"Origin '{origin}' not in allowed origins")
                diagnosis["recommendations"].append(f"Add '{origin}' to CORS allowed origins")
        
        # Check for common CORS issues
        if "localhost" in str(settings.cors_origins) and settings.is_production():
            diagnosis["issues"].append("Localhost origins found in production")
            diagnosis["recommendations"].append("Remove localhost origins in production")
        
        if not settings.cors_origins:
            diagnosis["issues"].append("No CORS origins configured")
            diagnosis["recommendations"].append("Configure CORS origins for your frontend")
        
        return diagnosis
    
    async def test_auth_endpoint(self, endpoint: str, token: str = None) -> Dict[str, Any]:
        """Test authentication endpoint connectivity and response."""
        test_result = {
            "endpoint": endpoint,
            "accessible": False,
            "response_time_ms": 0,
            "status_code": None,
            "headers": {},
            "errors": [],
            "auth_required": False,
            "auth_successful": False
        }
        
        start_time = time.time()
        
        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
                test_result["auth_required"] = True
            
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(endpoint, headers=headers)
                
                test_result["accessible"] = True
                test_result["status_code"] = response.status_code
                test_result["headers"] = dict(response.headers)
                test_result["response_time_ms"] = (time.time() - start_time) * 1000
                
                if token and response.status_code == 200:
                    test_result["auth_successful"] = True
                elif token and response.status_code == 401:
                    test_result["errors"].append("Authentication failed")
                
        except httpx.TimeoutException:
            test_result["errors"].append("Request timeout")
        except httpx.ConnectError:
            test_result["errors"].append("Connection failed")
        except Exception as e:
            test_result["errors"].append(f"Unexpected error: {str(e)}")
        
        return test_result
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance analysis report."""
        report = {
            "total_requests": len(self.traces),
            "avg_response_time_ms": 0,
            "slow_requests": [],
            "error_rate": 0,
            "common_errors": {},
            "auth_success_rate": 0,
            "security_incidents": len(self.security_incidents)
        }
        
        if not self.traces:
            return report
        
        response_times = []
        error_count = 0
        auth_success_count = 0
        auth_total_count = 0
        error_types = {}
        
        for trace in self.traces.values():
            if trace.response_time_ms:
                response_times.append(trace.response_time_ms)
                
                if trace.response_time_ms > 1000:  # Slow request > 1s
                    report["slow_requests"].append({
                        "trace_id": trace.trace_id,
                        "path": trace.path,
                        "response_time_ms": trace.response_time_ms
                    })
            
            if trace.response_status and trace.response_status >= 400:
                error_count += 1
                status_key = str(trace.response_status)
                error_types[status_key] = error_types.get(status_key, 0) + 1
            
            if trace.auth_header:
                auth_total_count += 1
                if trace.response_status and trace.response_status == 200:
                    auth_success_count += 1
        
        if response_times:
            report["avg_response_time_ms"] = sum(response_times) / len(response_times)
        
        report["error_rate"] = (error_count / len(self.traces)) * 100 if self.traces else 0
        report["common_errors"] = error_types
        report["auth_success_rate"] = (auth_success_count / auth_total_count * 100) if auth_total_count > 0 else 0
        
        return report
    
    def export_debug_data(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Export comprehensive debug data for analysis."""
        export_data = {
            "metadata": {
                "export_time": datetime.now(timezone.utc).isoformat(),
                "environment": settings.environment,
                "debug_mode": settings.debug,
                "total_traces": len(self.traces),
                "total_auth_flows": len(self.auth_flows),
                "total_incidents": len(self.security_incidents)
            },
            "traces": [],
            "auth_flows": {},
            "security_incidents": self.security_incidents,
            "performance_report": self.get_performance_report()
        }
        
        # Export traces (sanitized)
        for trace in self.traces.values():
            trace_data = asdict(trace)
            if not include_sensitive and trace_data.get("auth_header"):
                trace_data["auth_header"] = "***REDACTED***"
            export_data["traces"].append(trace_data)
        
        # Export auth flows
        for flow_id, steps in self.auth_flows.items():
            export_data["auth_flows"][flow_id] = [asdict(step) for step in steps]
        
        return export_data


# Global debugger instance
auth_debugger = AuthenticationDebugger(
    enable_logging=settings.debug,
    log_sensitive_data=settings.debug and not settings.is_production()
)


@asynccontextmanager
async def debug_auth_flow(flow_id: str, component: str, action: str):
    """Context manager for debugging authentication flows."""
    step_id = auth_debugger.start_auth_flow(flow_id, component, action)
    start_time = time.time()
    
    try:
        yield step_id
        auth_debugger.complete_auth_step(flow_id, step_id, "success")
    except Exception as e:
        auth_debugger.complete_auth_step(
            flow_id, step_id, "error", 
            errors=[str(e)]
        )
        raise


def debug_token(token: str) -> TokenAnalysis:
    """Quick token analysis function."""
    return auth_debugger.analyze_jwt_token(token)


async def debug_auth_endpoint(endpoint: str, token: str = None) -> Dict[str, Any]:
    """Quick auth endpoint testing function."""
    return await auth_debugger.test_auth_endpoint(endpoint, token)