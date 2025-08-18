"""
Network Request/Response Inspection Utilities
Advanced debugging tools for HTTP traffic analysis and CORS troubleshooting.
"""
import json
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, parse_qs
from collections import defaultdict
import httpx
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class NetworkRequest:
    """Represents a network request for inspection."""
    id: str
    timestamp: datetime
    method: str
    url: str
    headers: Dict[str, str]
    query_params: Dict[str, List[str]]
    body: Optional[str]
    client_ip: str
    user_agent: str
    content_type: Optional[str]
    content_length: Optional[int]


@dataclass
class NetworkResponse:
    """Represents a network response for inspection."""
    id: str
    timestamp: datetime
    status_code: int
    headers: Dict[str, str]
    body: Optional[str]
    content_type: Optional[str]
    content_length: Optional[int]
    duration_ms: float


@dataclass
class CORSAnalysis:
    """CORS request analysis results."""
    is_cors_request: bool
    origin: Optional[str]
    method: str
    is_preflight: bool
    requested_headers: List[str]
    requested_methods: List[str]
    cors_headers: Dict[str, str]
    issues: List[str]
    recommendations: List[str]


@dataclass
class RequestResponsePair:
    """Complete request-response pair for analysis."""
    request: NetworkRequest
    response: Optional[NetworkResponse]
    duration_ms: float
    errors: List[str]
    cors_analysis: Optional[CORSAnalysis]


class NetworkInspector:
    """Advanced network traffic inspector for debugging."""
    
    def __init__(self, max_history: int = 1000, log_bodies: bool = False):
        self.max_history = max_history
        self.log_bodies = log_bodies
        self.request_history: Dict[str, RequestResponsePair] = {}
        self.active_requests: Dict[str, NetworkRequest] = {}
        self.performance_stats = defaultdict(list)
        self.cors_stats = {
            "total_cors_requests": 0,
            "preflight_requests": 0,
            "cors_errors": 0,
            "blocked_origins": set()
        }
    
    def generate_request_id(self) -> str:
        """Generate unique request ID."""
        return f"req_{int(time.time() * 1000)}_{hash(time.time()) % 10000}"
    
    def inspect_request(self, request: Request) -> str:
        """Inspect incoming request and return request ID."""
        request_id = self.generate_request_id()
        
        # Parse query parameters
        query_params = {}
        for key, value in request.query_params.items():
            if key not in query_params:
                query_params[key] = []
            query_params[key].append(value)
        
        # Safe header extraction
        headers = {}
        sensitive_headers = {"authorization", "cookie", "x-api-key", "x-auth-token"}
        
        for header, value in request.headers.items():
            if header.lower() in sensitive_headers and not settings.debug:
                headers[header] = "***REDACTED***"
            else:
                headers[header] = value
        
        # Extract body if logging enabled
        body = None
        if self.log_bodies and hasattr(request, "_body"):
            try:
                body = request._body.decode("utf-8") if request._body else None
                # Redact sensitive data from body
                if body and not settings.debug:
                    body = self._redact_sensitive_data(body)
            except Exception:
                body = "***BINARY_DATA***"
        
        network_request = NetworkRequest(
            id=request_id,
            timestamp=datetime.now(timezone.utc),
            method=request.method,
            url=str(request.url),
            headers=headers,
            query_params=query_params,
            body=body,
            client_ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown"),
            content_type=request.headers.get("content-type"),
            content_length=int(request.headers.get("content-length", 0)) if request.headers.get("content-length") else None
        )
        
        self.active_requests[request_id] = network_request
        
        # Analyze CORS
        cors_analysis = self._analyze_cors_request(request)
        if cors_analysis.is_cors_request:
            self.cors_stats["total_cors_requests"] += 1
            if cors_analysis.is_preflight:
                self.cors_stats["preflight_requests"] += 1
        
        # Create request-response pair
        pair = RequestResponsePair(
            request=network_request,
            response=None,
            duration_ms=0.0,
            errors=[],
            cors_analysis=cors_analysis
        )
        
        self.request_history[request_id] = pair
        self._cleanup_history()
        
        return request_id
    
    def inspect_response(self, request_id: str, response: Response, duration_ms: float):
        """Inspect outgoing response."""
        if request_id not in self.request_history:
            return
        
        # Safe header extraction
        headers = {}
        for header, value in response.headers.items():
            headers[header] = value
        
        # Extract body if logging enabled
        body = None
        if self.log_bodies and hasattr(response, "body"):
            try:
                if isinstance(response.body, bytes):
                    body = response.body.decode("utf-8")
                else:
                    body = str(response.body)
                
                # Limit body size for logging
                if len(body) > 1000:
                    body = body[:1000] + "...[TRUNCATED]"
                    
            except Exception:
                body = "***BINARY_DATA***"
        
        network_response = NetworkResponse(
            id=request_id,
            timestamp=datetime.now(timezone.utc),
            status_code=response.status_code,
            headers=headers,
            body=body,
            content_type=response.headers.get("content-type"),
            content_length=int(response.headers.get("content-length", 0)) if response.headers.get("content-length") else None,
            duration_ms=duration_ms
        )
        
        # Update request-response pair
        pair = self.request_history[request_id]
        pair.response = network_response
        pair.duration_ms = duration_ms
        
        # Update performance stats
        self.performance_stats[pair.request.method].append(duration_ms)
        self.performance_stats["all"].append(duration_ms)
        
        # CORS error detection
        if pair.cors_analysis and pair.cors_analysis.is_cors_request:
            if response.status_code >= 400:
                self.cors_stats["cors_errors"] += 1
                if pair.cors_analysis.origin:
                    self.cors_stats["blocked_origins"].add(pair.cors_analysis.origin)
        
        # Clean up active requests
        if request_id in self.active_requests:
            del self.active_requests[request_id]
    
    def _analyze_cors_request(self, request: Request) -> CORSAnalysis:
        """Analyze CORS aspects of the request."""
        origin = request.headers.get("origin")
        method = request.method
        is_preflight = method == "OPTIONS"
        
        # Check if this is a CORS request
        is_cors_request = origin is not None
        
        # Parse preflight headers
        requested_headers = []
        requested_methods = []
        
        if is_preflight:
            access_control_request_headers = request.headers.get("access-control-request-headers", "")
            requested_headers = [h.strip() for h in access_control_request_headers.split(",") if h.strip()]
            
            access_control_request_method = request.headers.get("access-control-request-method", "")
            if access_control_request_method:
                requested_methods = [access_control_request_method]
        
        # Analyze CORS configuration
        cors_headers = {}
        issues = []
        recommendations = []
        
        if is_cors_request:
            # Check if origin is allowed
            origin_allowed = (
                origin in settings.cors_origins or 
                "*" in settings.cors_origins or
                any(origin.endswith(allowed.replace("*", "")) for allowed in settings.cors_origins if "*" in allowed)
            )
            
            if not origin_allowed:
                issues.append(f"Origin '{origin}' not allowed by CORS policy")
                recommendations.append(f"Add '{origin}' to CORS allowed origins")
            
            # Check method allowance
            if method not in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]:
                issues.append(f"Method '{method}' not typically allowed")
            
            # Check headers
            for header in requested_headers:
                if header.lower() in ["x-requested-with", "content-type", "authorization"]:
                    # These are common and should be allowed
                    pass
                else:
                    recommendations.append(f"Ensure header '{header}' is allowed in CORS policy")
        
        return CORSAnalysis(
            is_cors_request=is_cors_request,
            origin=origin,
            method=method,
            is_preflight=is_preflight,
            requested_headers=requested_headers,
            requested_methods=requested_methods,
            cors_headers=cors_headers,
            issues=issues,
            recommendations=recommendations
        )
    
    def _redact_sensitive_data(self, body: str) -> str:
        """Redact sensitive data from request/response bodies."""
        import re
        
        # Redact common sensitive patterns
        patterns = [
            (r'"password"\s*:\s*"[^"]*"', '"password": "***REDACTED***"'),
            (r'"token"\s*:\s*"[^"]*"', '"token": "***REDACTED***"'),
            (r'"secret"\s*:\s*"[^"]*"', '"secret": "***REDACTED***"'),
            (r'"api_key"\s*:\s*"[^"]*"', '"api_key": "***REDACTED***"'),
            (r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*', 'Bearer ***REDACTED***'),
        ]
        
        redacted_body = body
        for pattern, replacement in patterns:
            redacted_body = re.sub(pattern, replacement, redacted_body, flags=re.IGNORECASE)
        
        return redacted_body
    
    def _cleanup_history(self):
        """Clean up old request history to prevent memory issues."""
        if len(self.request_history) > self.max_history:
            # Remove oldest entries
            sorted_ids = sorted(
                self.request_history.keys(),
                key=lambda x: self.request_history[x].request.timestamp
            )
            
            for request_id in sorted_ids[:-self.max_history]:
                del self.request_history[request_id]
    
    def get_request_by_id(self, request_id: str) -> Optional[RequestResponsePair]:
        """Get specific request-response pair by ID."""
        return self.request_history.get(request_id)
    
    def get_recent_requests(self, limit: int = 50) -> List[RequestResponsePair]:
        """Get recent requests sorted by timestamp."""
        sorted_requests = sorted(
            self.request_history.values(),
            key=lambda x: x.request.timestamp,
            reverse=True
        )
        return sorted_requests[:limit]
    
    def get_cors_requests(self, limit: int = 50) -> List[RequestResponsePair]:
        """Get recent CORS requests."""
        cors_requests = [
            pair for pair in self.request_history.values()
            if pair.cors_analysis and pair.cors_analysis.is_cors_request
        ]
        
        sorted_cors = sorted(
            cors_requests,
            key=lambda x: x.request.timestamp,
            reverse=True
        )
        return sorted_cors[:limit]
    
    def get_failed_requests(self, limit: int = 50) -> List[RequestResponsePair]:
        """Get recent failed requests (4xx, 5xx status codes)."""
        failed_requests = [
            pair for pair in self.request_history.values()
            if pair.response and pair.response.status_code >= 400
        ]
        
        sorted_failed = sorted(
            failed_requests,
            key=lambda x: x.request.timestamp,
            reverse=True
        )
        return sorted_failed[:limit]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance analysis summary."""
        summary = {
            "total_requests": len(self.request_history),
            "avg_response_time": {},
            "slow_requests": [],
            "method_distribution": {},
            "status_code_distribution": {},
            "cors_summary": dict(self.cors_stats)
        }
        
        # Calculate average response times by method
        for method, times in self.performance_stats.items():
            if times:
                summary["avg_response_time"][method] = {
                    "avg_ms": sum(times) / len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                    "count": len(times)
                }
        
        # Find slow requests (>1s)
        for pair in self.request_history.values():
            if pair.response and pair.duration_ms > 1000:
                summary["slow_requests"].append({
                    "id": pair.request.id,
                    "method": pair.request.method,
                    "url": pair.request.url,
                    "duration_ms": pair.duration_ms,
                    "status_code": pair.response.status_code
                })
        
        # Method and status code distribution
        method_counts = defaultdict(int)
        status_counts = defaultdict(int)
        
        for pair in self.request_history.values():
            method_counts[pair.request.method] += 1
            if pair.response:
                status_counts[pair.response.status_code] += 1
        
        summary["method_distribution"] = dict(method_counts)
        summary["status_code_distribution"] = dict(status_counts)
        
        # Convert set to list for JSON serialization
        summary["cors_summary"]["blocked_origins"] = list(summary["cors_summary"]["blocked_origins"])
        
        return summary
    
    async def test_cors_configuration(self, origin: str, methods: List[str] = None) -> Dict[str, Any]:
        """Test CORS configuration against specific origin and methods."""
        if methods is None:
            methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        
        test_results = {
            "origin": origin,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tests": [],
            "overall_status": "unknown",
            "issues": [],
            "recommendations": []
        }
        
        base_url = f"http://localhost:{settings.port if hasattr(settings, 'port') else 8000}"
        
        for method in methods:
            test_result = {
                "method": method,
                "preflight_required": method not in ["GET", "HEAD"],
                "preflight_success": False,
                "actual_request_success": False,
                "errors": []
            }
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Test preflight if required
                    if test_result["preflight_required"]:
                        preflight_headers = {
                            "Origin": origin,
                            "Access-Control-Request-Method": method,
                            "Access-Control-Request-Headers": "Content-Type, Authorization"
                        }
                        
                        preflight_response = await client.options(
                            f"{base_url}/api/v1/auth/login",
                            headers=preflight_headers
                        )
                        
                        if preflight_response.status_code in [200, 204]:
                            test_result["preflight_success"] = True
                        else:
                            test_result["errors"].append(f"Preflight failed: {preflight_response.status_code}")
                    
                    # Test actual request
                    request_headers = {"Origin": origin}
                    if method == "GET":
                        response = await client.get(f"{base_url}/health", headers=request_headers)
                    else:
                        response = await client.request(method, f"{base_url}/health", headers=request_headers)
                    
                    cors_headers = {
                        k: v for k, v in response.headers.items() 
                        if k.lower().startswith("access-control-")
                    }
                    
                    test_result["cors_headers"] = cors_headers
                    
                    if "access-control-allow-origin" in cors_headers:
                        allowed_origin = cors_headers["access-control-allow-origin"]
                        if allowed_origin == origin or allowed_origin == "*":
                            test_result["actual_request_success"] = True
                        else:
                            test_result["errors"].append(f"Origin not allowed: {allowed_origin}")
                    else:
                        test_result["errors"].append("No Access-Control-Allow-Origin header")
            
            except Exception as e:
                test_result["errors"].append(f"Request failed: {str(e)}")
            
            test_results["tests"].append(test_result)
        
        # Analyze overall status
        successful_tests = sum(1 for test in test_results["tests"] if test["actual_request_success"])
        total_tests = len(test_results["tests"])
        
        if successful_tests == total_tests:
            test_results["overall_status"] = "pass"
        elif successful_tests > 0:
            test_results["overall_status"] = "partial"
        else:
            test_results["overall_status"] = "fail"
            test_results["issues"].append("All CORS tests failed")
            test_results["recommendations"].append(f"Add '{origin}' to CORS allowed origins")
        
        return test_results
    
    def export_network_data(self, format: str = "json") -> Union[str, Dict[str, Any]]:
        """Export network inspection data."""
        export_data = {
            "metadata": {
                "export_time": datetime.now(timezone.utc).isoformat(),
                "total_requests": len(self.request_history),
                "environment": settings.environment
            },
            "requests": [],
            "performance_summary": self.get_performance_summary(),
            "cors_analysis": {
                "total_cors_requests": self.cors_stats["total_cors_requests"],
                "preflight_requests": self.cors_stats["preflight_requests"],
                "cors_errors": self.cors_stats["cors_errors"],
                "blocked_origins": list(self.cors_stats["blocked_origins"])
            }
        }
        
        # Export request-response pairs
        for pair in self.request_history.values():
            pair_data = {
                "request": asdict(pair.request),
                "response": asdict(pair.response) if pair.response else None,
                "duration_ms": pair.duration_ms,
                "errors": pair.errors,
                "cors_analysis": asdict(pair.cors_analysis) if pair.cors_analysis else None
            }
            export_data["requests"].append(pair_data)
        
        if format == "json":
            return json.dumps(export_data, indent=2, default=str)
        else:
            return export_data


class NetworkInspectionMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic network traffic inspection."""
    
    def __init__(self, app, inspector: NetworkInspector):
        super().__init__(app)
        self.inspector = inspector
    
    async def dispatch(self, request: Request, call_next):
        """Intercept request and response for inspection."""
        start_time = time.time()
        
        # Inspect request
        request_id = self.inspector.inspect_request(request)
        
        try:
            # Process request
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            
            # Inspect response
            self.inspector.inspect_response(request_id, response, duration_ms)
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            # Record error in request history
            if request_id in self.inspector.request_history:
                self.inspector.request_history[request_id].errors.append(str(e))
            
            raise


# Global network inspector instance
network_inspector = NetworkInspector(
    max_history=1000,
    log_bodies=settings.debug and not settings.is_production()
)