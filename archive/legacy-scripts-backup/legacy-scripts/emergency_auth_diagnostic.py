#!/usr/bin/env python3
"""
Emergency Authentication Diagnostic Script
Emergency Auth Validation Swarm - Diagnostic Component
Version: 1.0.0

This script performs rapid diagnostic testing to identify the root cause
of authentication system failures and provides actionable remediation steps.
"""

import requests
import json
import sys
from datetime import datetime
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmergencyAuthDiagnostic:
    """Emergency diagnostic tool for authentication issues"""
    
    def __init__(self, base_url: str = "https://velro-backend.railway.app"):
        self.base_url = base_url.rstrip('/')
        self.api_base = f"{self.base_url}/api/v1"
        self.session = requests.Session()
        self.findings = []
        
    def log_finding(self, severity: str, issue: str, details: Dict[str, Any], remediation: str = ""):
        """Log diagnostic finding"""
        finding = {
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "issue": issue,
            "details": details,
            "remediation": remediation
        }
        self.findings.append(finding)
        
        severity_emoji = {"CRITICAL": "🚨", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "ℹ️"}
        emoji = severity_emoji.get(severity, "❓")
        
        logger.info(f"{emoji} {severity}: {issue}")
        if details:
            logger.info(f"   Details: {json.dumps(details, indent=2)}")
        if remediation:
            logger.info(f"   Remediation: {remediation}")
    
    def test_basic_connectivity(self) -> bool:
        """Test basic server connectivity"""
        logger.info("🔍 Testing Basic Connectivity...")
        
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                self.log_finding("INFO", "Basic connectivity working", {
                    "status_code": response.status_code,
                    "response_text": response.text[:100],
                    "headers": dict(response.headers)
                })
                return True
            else:
                self.log_finding("CRITICAL", "Health endpoint not responding correctly", {
                    "status_code": response.status_code,
                    "response_text": response.text
                }, "Check server deployment and health endpoint configuration")
                return False
                
        except Exception as e:
            self.log_finding("CRITICAL", "Cannot connect to server", {
                "error": str(e),
                "error_type": type(e).__name__
            }, "Verify server is running and URL is correct")
            return False
    
    def test_route_discovery(self) -> Dict[str, Any]:
        """Discover available routes and endpoints"""
        logger.info("🗺️ Discovering Available Routes...")
        
        routes = {}
        
        # Test common endpoints
        test_endpoints = [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/me",
            "/api/v1/projects",
            "/api/v1/generations",
            "/api/v1/models",
            "/api/v1/credits"
        ]
        
        for endpoint in test_endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", timeout=5)
                routes[endpoint] = {
                    "status_code": response.status_code,
                    "accessible": response.status_code != 404,
                    "response_size": len(response.text),
                    "content_type": response.headers.get("content-type", "")
                }
                
                if response.status_code == 404:
                    self.log_finding("HIGH", f"Route not found: {endpoint}", {
                        "endpoint": endpoint,
                        "status_code": response.status_code
                    }, f"Check FastAPI router registration for {endpoint}")
                
            except Exception as e:
                routes[endpoint] = {
                    "error": str(e),
                    "accessible": False
                }
        
        # Check if any auth routes are working
        auth_routes = [ep for ep in routes if "/auth/" in ep]
        working_auth_routes = [ep for ep in auth_routes if routes[ep].get("accessible", False)]
        
        if not working_auth_routes:
            self.log_finding("CRITICAL", "No authentication routes accessible", {
                "tested_routes": auth_routes,
                "working_routes": working_auth_routes
            }, "Verify auth router is properly registered in main.py")
        
        return routes
    
    def test_openapi_docs(self) -> Dict[str, Any]:
        """Check OpenAPI documentation for route information"""
        logger.info("📚 Checking OpenAPI Documentation...")
        
        try:
            # Try to get OpenAPI schema
            response = self.session.get(f"{self.base_url}/openapi.json", timeout=10)
            
            if response.status_code == 200:
                openapi_data = response.json()
                paths = openapi_data.get("paths", {})
                
                auth_paths = {path: details for path, details in paths.items() if "/auth/" in path}
                
                self.log_finding("INFO", "OpenAPI documentation accessible", {
                    "total_paths": len(paths),
                    "auth_paths": len(auth_paths),
                    "auth_endpoints": list(auth_paths.keys())
                })
                
                if not auth_paths:
                    self.log_finding("HIGH", "No auth routes in OpenAPI schema", {
                        "available_paths": list(paths.keys())[:10]  # First 10 paths
                    }, "Auth router may not be properly registered")
                
                return {"success": True, "paths": paths, "auth_paths": auth_paths}
            else:
                self.log_finding("MEDIUM", "OpenAPI documentation not accessible", {
                    "status_code": response.status_code,
                    "response_text": response.text[:200]
                })
                return {"success": False, "error": "Not accessible"}
                
        except Exception as e:
            self.log_finding("MEDIUM", "Failed to check OpenAPI documentation", {
                "error": str(e)
            })
            return {"success": False, "error": str(e)}
    
    def test_cors_configuration(self) -> Dict[str, Any]:
        """Test CORS configuration"""
        logger.info("🌐 Testing CORS Configuration...")
        
        cors_results = {}
        
        # Test origins
        test_origins = [
            "https://velro-frontend-production.up.railway.app",
            "https://velro-003-frontend-production.up.railway.app",
            "http://localhost:3000",
            "https://evil.attacker.com"  # Should be blocked
        ]
        
        for origin in test_origins:
            try:
                response = self.session.options(
                    f"{self.api_base}/auth/login",
                    headers={
                        'Origin': origin,
                        'Access-Control-Request-Method': 'POST',
                        'Access-Control-Request-Headers': 'Content-Type,Authorization'
                    },
                    timeout=10
                )
                
                allowed_origin = response.headers.get('Access-Control-Allow-Origin', '')
                cors_results[origin] = {
                    "status_code": response.status_code,
                    "allowed": allowed_origin == origin or allowed_origin == '*',
                    "allowed_origin": allowed_origin,
                    "cors_headers": {
                        "Access-Control-Allow-Origin": response.headers.get('Access-Control-Allow-Origin'),
                        "Access-Control-Allow-Methods": response.headers.get('Access-Control-Allow-Methods'),
                        "Access-Control-Allow-Headers": response.headers.get('Access-Control-Allow-Headers'),
                        "Access-Control-Allow-Credentials": response.headers.get('Access-Control-Allow-Credentials')
                    }
                }
                
            except Exception as e:
                cors_results[origin] = {"error": str(e)}
        
        # Check if any legitimate origins are blocked or malicious ones allowed
        legitimate_origins = test_origins[:3]  # First 3 are legitimate
        malicious_origins = test_origins[3:]   # Last one is malicious
        
        blocked_legitimate = [o for o in legitimate_origins if not cors_results.get(o, {}).get("allowed", False)]
        allowed_malicious = [o for o in malicious_origins if cors_results.get(o, {}).get("allowed", False)]
        
        if blocked_legitimate:
            self.log_finding("HIGH", "Legitimate origins blocked by CORS", {
                "blocked_origins": blocked_legitimate
            }, "Update CORS configuration to allow legitimate frontend origins")
        
        if allowed_malicious:
            self.log_finding("MEDIUM", "Potentially unsafe CORS configuration", {
                "allowed_malicious": allowed_malicious
            }, "Review CORS origin whitelist for security")
        
        return cors_results
    
    def test_environment_variables(self) -> Dict[str, Any]:
        """Test environment variable configuration (indirectly)"""
        logger.info("⚙️ Testing Environment Configuration...")
        
        # We can't directly access env vars, but we can infer from responses
        env_issues = []
        
        # Try to trigger a response that might reveal missing env vars
        try:
            # Test an endpoint that requires database connection
            response = self.session.post(
                f"{self.api_base}/auth/login",
                json={"email": "test@example.com", "password": "test123"},
                timeout=10
            )
            
            if response.status_code == 500:
                response_text = response.text.lower()
                if "database" in response_text or "supabase" in response_text:
                    env_issues.append("Database connection may be misconfigured")
                if "key" in response_text or "secret" in response_text:
                    env_issues.append("API keys or secrets may be missing")
            
        except Exception as e:
            pass  # Expected if routes don't work
        
        if env_issues:
            self.log_finding("HIGH", "Potential environment configuration issues", {
                "issues": env_issues
            }, "Check Railway environment variables are properly set")
        
        return {"issues": env_issues}
    
    def generate_diagnostic_report(self) -> str:
        """Generate comprehensive diagnostic report"""
        logger.info("📊 Generating Diagnostic Report...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"emergency_auth_diagnostic_report_{timestamp}.json"
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "target_url": self.base_url,
            "diagnostic_version": "1.0.0",
            "findings": self.findings,
            "summary": {
                "total_findings": len(self.findings),
                "critical": len([f for f in self.findings if f["severity"] == "CRITICAL"]),
                "high": len([f for f in self.findings if f["severity"] == "HIGH"]),
                "medium": len([f for f in self.findings if f["severity"] == "MEDIUM"]),
                "low": len([f for f in self.findings if f["severity"] == "LOW"]),
                "info": len([f for f in self.findings if f["severity"] == "INFO"])
            }
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📊 Diagnostic report saved to: {report_file}")
        return report_file
    
    def run_emergency_diagnostic(self) -> Dict[str, Any]:
        """Run complete emergency diagnostic"""
        logger.info("🚨 Starting Emergency Authentication Diagnostic")
        logger.info(f"   Target: {self.base_url}")
        logger.info("=" * 80)
        
        # Run all diagnostic tests
        connectivity = self.test_basic_connectivity()
        routes = self.test_route_discovery()
        openapi = self.test_openapi_docs()
        cors = self.test_cors_configuration()
        env_check = self.test_environment_variables()
        
        # Generate summary
        summary = {
            "connectivity": connectivity,
            "routes_discovered": len([r for r in routes.values() if r.get("accessible", False)]),
            "auth_routes_working": len([r for r, v in routes.items() if "/auth/" in r and v.get("accessible", False)]),
            "openapi_accessible": openapi.get("success", False),
            "cors_configured": len(cors) > 0
        }
        
        # Generate report
        report_file = self.generate_diagnostic_report()
        
        # Print summary
        logger.info("=" * 80)
        logger.info("🏁 Emergency Diagnostic Complete")
        logger.info(f"   Findings: {len(self.findings)}")
        logger.info(f"   Critical: {len([f for f in self.findings if f['severity'] == 'CRITICAL'])}")
        logger.info(f"   High: {len([f for f in self.findings if f['severity'] == 'HIGH'])}")
        logger.info(f"   Report: {report_file}")
        
        return {"summary": summary, "findings": self.findings, "report_file": report_file}


def main():
    """Main diagnostic runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Emergency Authentication Diagnostic")
    parser.add_argument("--url", default="https://velro-backend.railway.app",
                      help="Base URL of the API to diagnose")
    
    args = parser.parse_args()
    
    # Run diagnostic
    diagnostic = EmergencyAuthDiagnostic(base_url=args.url)
    
    try:
        results = diagnostic.run_emergency_diagnostic()
        
        # Exit with appropriate code
        critical_issues = len([f for f in results["findings"] if f["severity"] == "CRITICAL"])
        high_issues = len([f for f in results["findings"] if f["severity"] == "HIGH"])
        
        if critical_issues > 0:
            logger.error("🚨 CRITICAL issues found - immediate action required!")
            sys.exit(2)
        elif high_issues > 0:
            logger.warning("⚠️ HIGH priority issues found")
            sys.exit(1)
        else:
            logger.info("✅ No critical issues detected")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("Diagnostic interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Diagnostic failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()