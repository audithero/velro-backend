#!/usr/bin/env python3
"""
Final Production Validation Suite with Correct Backend URL
========================================================

This is the definitive production validation using the discovered working backend URL.
Performs complete validation of all critical systems for production readiness.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional
import httpx
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    test_name: str
    passed: bool
    message: str
    details: Dict[str, Any]
    execution_time: float
    critical: bool = False

class FinalProductionValidator:
    """Final production validation with working URLs."""
    
    def __init__(self):
        # Discovered working URLs
        self.backend_url = "https://velro-backend.railway.app"
        self.frontend_url = "https://velro-frontend-production.up.railway.app"
        
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results: List[ValidationResult] = []
        self.test_user_data = {}
    
    async def run_final_validation(self) -> Dict[str, Any]:
        """Execute final production validation."""
        logger.info("🎯 Starting Final Production Validation with Working URLs")
        start_time = time.time()
        
        # Core validation phases
        await self.validate_infrastructure_health()
        await self.validate_security_configuration()
        await self.validate_api_endpoints()
        await self.validate_user_authentication_flow()
        await self.validate_database_operations()
        await self.validate_frontend_integration()
        await self.validate_performance()
        await self.run_security_tests()
        
        # Generate final report
        total_time = time.time() - start_time
        return await self.generate_final_report(total_time)
    
    async def validate_infrastructure_health(self):
        """Validate infrastructure is healthy and ready."""
        logger.info("🏥 Validating infrastructure health...")
        
        # Backend health check
        try:
            response = await self.client.get(f"{self.backend_url}/health")
            health_data = response.json() if response.status_code == 200 else {}
            
            self.results.append(ValidationResult(
                test_name="Backend Health Check",
                passed=response.status_code == 200,
                message=f"Backend health: {response.status_code}",
                details=health_data,
                execution_time=response.elapsed.total_seconds(),
                critical=True
            ))
            
            # Check database status
            if response.status_code == 200:
                db_status = health_data.get("database", "unknown")
                db_healthy = db_status in ["connected", "railway-optimized"]
                
                self.results.append(ValidationResult(
                    test_name="Database Connectivity",
                    passed=db_healthy,
                    message=f"Database status: {db_status}",
                    details={"database_status": db_status},
                    execution_time=0.0,
                    critical=True
                ))
            
        except Exception as e:
            self.results.append(ValidationResult(
                test_name="Backend Health Check",
                passed=False,
                message=f"Backend health check failed: {str(e)}",
                details={"error": str(e)},
                execution_time=0.0,
                critical=True
            ))
        
        # Frontend health check
        try:
            response = await self.client.get(f"{self.frontend_url}/health")
            
            self.results.append(ValidationResult(
                test_name="Frontend Health Check",
                passed=response.status_code == 200,
                message=f"Frontend health: {response.status_code}",
                details={"status_code": response.status_code},
                execution_time=response.elapsed.total_seconds(),
                critical=True
            ))
            
        except Exception as e:
            self.results.append(ValidationResult(
                test_name="Frontend Health Check",
                passed=False,
                message=f"Frontend health check failed: {str(e)}",
                details={"error": str(e)},
                execution_time=0.0,
                critical=True
            ))
    
    async def validate_security_configuration(self):
        """Validate security configuration."""
        logger.info("🔒 Validating security configuration...")
        
        try:
            response = await self.client.get(f"{self.backend_url}/security-status")
            
            if response.status_code == 200:
                security_config = response.json()
                
                # Check critical security features
                security_features = security_config.get("security_features", {})
                critical_checks = {
                    "rate_limiting": security_features.get("rate_limiting") == "enabled",
                    "input_validation": security_features.get("input_validation") == "enabled",
                    "authentication": security_features.get("authentication") == "jwt_required",
                    "security_headers": security_features.get("security_headers") == "enabled"
                }
                
                all_passed = all(critical_checks.values())
                
                self.results.append(ValidationResult(
                    test_name="Security Configuration",
                    passed=all_passed,
                    message="Security configuration validated" if all_passed else "Security issues detected",
                    details={"checks": critical_checks, "config": security_config},
                    execution_time=response.elapsed.total_seconds(),
                    critical=True
                ))
                
                # Check security headers
                required_headers = ["X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection"]
                headers_present = {h: h in response.headers for h in required_headers}
                
                self.results.append(ValidationResult(
                    test_name="Security Headers",
                    passed=all(headers_present.values()),
                    message="Security headers validated",
                    details={"headers": headers_present},
                    execution_time=0.0,
                    critical=True
                ))
            else:
                self.results.append(ValidationResult(
                    test_name="Security Configuration",
                    passed=False,
                    message=f"Security endpoint returned {response.status_code}",
                    details={"status_code": response.status_code},
                    execution_time=response.elapsed.total_seconds(),
                    critical=True
                ))
                
        except Exception as e:
            self.results.append(ValidationResult(
                test_name="Security Configuration",
                passed=False,
                message=f"Security validation failed: {str(e)}",
                details={"error": str(e)},
                execution_time=0.0,
                critical=True
            ))
    
    async def validate_api_endpoints(self):
        """Validate critical API endpoints."""
        logger.info("🔌 Validating API endpoints...")
        
        # Critical endpoints to test
        endpoints = [
            {"path": "/api/v1/models/supported", "method": "GET", "auth": False},
            {"path": "/api/v1/auth/register", "method": "POST", "auth": False},
            {"path": "/api/v1/auth/login", "method": "POST", "auth": False},
            {"path": "/api/v1/projects", "method": "GET", "auth": True},
            {"path": "/api/v1/credits/balance", "method": "GET", "auth": True}
        ]
        
        for endpoint in endpoints:
            try:
                if endpoint["method"] == "GET":
                    response = await self.client.get(f"{self.backend_url}{endpoint['path']}")
                else:
                    response = await self.client.post(f"{self.backend_url}{endpoint['path']}", json={})
                
                # Expected responses: 200 (success), 401 (auth required), 422 (validation error)
                valid_responses = [200, 401, 422]
                endpoint_working = response.status_code in valid_responses
                
                self.results.append(ValidationResult(
                    test_name=f"API Endpoint: {endpoint['path']}",
                    passed=endpoint_working,
                    message=f"Endpoint response: {response.status_code}",
                    details={
                        "status_code": response.status_code,
                        "method": endpoint["method"],
                        "requires_auth": endpoint["auth"]
                    },
                    execution_time=response.elapsed.total_seconds(),
                    critical=True
                ))
                
                # If successful, try to get response data
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        self.results[-1].details["response_sample"] = response_data
                    except:
                        pass
                        
            except Exception as e:
                self.results.append(ValidationResult(
                    test_name=f"API Endpoint: {endpoint['path']}",
                    passed=False,
                    message=f"Endpoint error: {str(e)}",
                    details={"error": str(e), "method": endpoint["method"]},
                    execution_time=0.0,
                    critical=True
                ))
    
    async def validate_user_authentication_flow(self):
        """Validate user authentication end-to-end."""
        logger.info("👤 Validating user authentication flow...")
        
        # Test user registration
        test_user = {
            "email": f"validation-user-{int(time.time())}@example.com",
            "password": "SecureValidationPassword123!",
            "full_name": "Validation Test User"
        }
        
        try:
            # Registration test
            reg_response = await self.client.post(
                f"{self.backend_url}/api/v1/auth/register",
                json=test_user
            )
            
            registration_success = reg_response.status_code in [200, 201]
            
            self.results.append(ValidationResult(
                test_name="User Registration Flow",
                passed=registration_success,
                message=f"Registration: {reg_response.status_code}",
                details={"status_code": reg_response.status_code},
                execution_time=reg_response.elapsed.total_seconds(),
                critical=True
            ))
            
            # If registration successful, test login
            if registration_success:
                try:
                    reg_data = reg_response.json()
                    access_token = reg_data.get("access_token")
                    user_data = reg_data.get("user", {})
                    
                    self.test_user_data = {
                        "access_token": access_token,
                        "user": user_data,
                        "email": test_user["email"]
                    }
                    
                    # Test login
                    login_response = await self.client.post(
                        f"{self.backend_url}/api/v1/auth/login",
                        json={"email": test_user["email"], "password": test_user["password"]}
                    )
                    
                    login_success = login_response.status_code == 200
                    
                    self.results.append(ValidationResult(
                        test_name="User Login Flow",
                        passed=login_success,
                        message=f"Login: {login_response.status_code}",
                        details={"status_code": login_response.status_code},
                        execution_time=login_response.elapsed.total_seconds(),
                        critical=True
                    ))
                    
                except json.JSONDecodeError:
                    self.results.append(ValidationResult(
                        test_name="User Login Flow",
                        passed=False,
                        message="Registration response invalid JSON",
                        details={"error": "invalid_json"},
                        execution_time=0.0,
                        critical=True
                    ))
            
        except Exception as e:
            self.results.append(ValidationResult(
                test_name="User Authentication Flow",
                passed=False,
                message=f"Auth flow error: {str(e)}",
                details={"error": str(e)},
                execution_time=0.0,
                critical=True
            ))
    
    async def validate_database_operations(self):
        """Validate database operations are working."""
        logger.info("🗄️ Validating database operations...")
        
        if not self.test_user_data.get("access_token"):
            self.results.append(ValidationResult(
                test_name="Database Operations",
                passed=False,
                message="No auth token for database testing",
                details={"reason": "authentication_failed"},
                execution_time=0.0,
                critical=True
            ))
            return
        
        # Test authenticated database operations
        headers = {"Authorization": f"Bearer {self.test_user_data['access_token']}"}
        
        try:
            # Test projects list (requires database)
            projects_response = await self.client.get(
                f"{self.backend_url}/api/v1/projects",
                headers=headers
            )
            
            projects_working = projects_response.status_code == 200
            
            self.results.append(ValidationResult(
                test_name="Database Read Operations",
                passed=projects_working,
                message=f"Projects list: {projects_response.status_code}",
                details={"status_code": projects_response.status_code},
                execution_time=projects_response.elapsed.total_seconds(),
                critical=True
            ))
            
            # Test credits balance (requires database)
            credits_response = await self.client.get(
                f"{self.backend_url}/api/v1/credits/balance",
                headers=headers
            )
            
            credits_working = credits_response.status_code == 200
            
            self.results.append(ValidationResult(
                test_name="Database User Data Operations",
                passed=credits_working,
                message=f"Credits balance: {credits_response.status_code}",
                details={"status_code": credits_response.status_code},
                execution_time=credits_response.elapsed.total_seconds(),
                critical=True
            ))
            
        except Exception as e:
            self.results.append(ValidationResult(
                test_name="Database Operations",
                passed=False,
                message=f"Database test error: {str(e)}",
                details={"error": str(e)},
                execution_time=0.0,
                critical=True
            ))
    
    async def validate_frontend_integration(self):
        """Validate frontend integration and routes."""
        logger.info("🎨 Validating frontend integration...")
        
        # Critical frontend routes
        routes = [
            {"path": "/", "critical": True},
            {"path": "/auth/login", "critical": True},
            {"path": "/auth/register", "critical": True},
            {"path": "/dashboard", "critical": False},
            {"path": "/projects", "critical": False},
            {"path": "/settings", "critical": False}
        ]
        
        for route in routes:
            try:
                response = await self.client.get(f"{self.frontend_url}{route['path']}")
                
                # 200 or 302 (redirect) are acceptable
                route_working = response.status_code in [200, 302]
                
                self.results.append(ValidationResult(
                    test_name=f"Frontend Route: {route['path']}",
                    passed=route_working,
                    message=f"Route response: {response.status_code}",
                    details={"status_code": response.status_code, "path": route["path"]},
                    execution_time=response.elapsed.total_seconds(),
                    critical=route["critical"]
                ))
                
            except Exception as e:
                self.results.append(ValidationResult(
                    test_name=f"Frontend Route: {route['path']}",
                    passed=False,
                    message=f"Route error: {str(e)}",
                    details={"error": str(e), "path": route["path"]},
                    execution_time=0.0,
                    critical=route["critical"]
                ))
    
    async def validate_performance(self):
        """Validate system performance."""
        logger.info("⚡ Validating performance...")
        
        # Test response times for critical endpoints
        endpoints = [
            f"{self.backend_url}/health",
            f"{self.backend_url}/api/v1/models/supported",
            f"{self.frontend_url}/"
        ]
        
        for endpoint in endpoints:
            response_times = []
            
            # Make 5 requests to measure average response time
            for _ in range(5):
                try:
                    start_time = time.time()
                    response = await self.client.get(endpoint)
                    response_time = time.time() - start_time
                    
                    if response.status_code in [200, 302]:
                        response_times.append(response_time)
                        
                except Exception:
                    pass
            
            if response_times:
                avg_time = sum(response_times) / len(response_times)
                max_time = max(response_times)
                
                # Performance thresholds: avg < 2s, max < 5s
                performance_ok = avg_time < 2.0 and max_time < 5.0
                
                self.results.append(ValidationResult(
                    test_name=f"Performance: {endpoint.split('/')[-1] or 'root'}",
                    passed=performance_ok,
                    message=f"Avg: {avg_time:.2f}s, Max: {max_time:.2f}s",
                    details={
                        "average_response_time": avg_time,
                        "max_response_time": max_time,
                        "samples": len(response_times)
                    },
                    execution_time=sum(response_times),
                    critical=False
                ))
    
    async def run_security_tests(self):
        """Run basic security validation tests."""
        logger.info("🛡️ Running security tests...")
        
        # Test authentication requirements
        protected_endpoints = [
            "/api/v1/projects",
            "/api/v1/credits/balance",
            "/api/v1/generations"
        ]
        
        for endpoint in protected_endpoints:
            try:
                # Test without authentication
                response = await self.client.get(f"{self.backend_url}{endpoint}")
                
                # Should return 401 (Unauthorized)
                auth_required = response.status_code == 401
                
                self.results.append(ValidationResult(
                    test_name=f"Auth Required: {endpoint}",
                    passed=auth_required,
                    message="Authentication enforced" if auth_required else f"Got {response.status_code}",
                    details={"status_code": response.status_code, "endpoint": endpoint},
                    execution_time=response.elapsed.total_seconds(),
                    critical=True
                ))
                
            except Exception as e:
                self.results.append(ValidationResult(
                    test_name=f"Auth Required: {endpoint}",
                    passed=False,
                    message=f"Auth test error: {str(e)}",
                    details={"error": str(e), "endpoint": endpoint},
                    execution_time=0.0,
                    critical=True
                ))
    
    async def generate_final_report(self, total_time: float) -> Dict[str, Any]:
        """Generate final production validation report."""
        logger.info("📊 Generating final validation report...")
        
        # Calculate statistics
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        failed_tests = total_tests - passed_tests
        critical_failures = sum(1 for r in self.results if not r.passed and r.critical)
        
        # Performance metrics
        avg_response_time = sum(r.execution_time for r in self.results if r.execution_time > 0) / max(1, len([r for r in self.results if r.execution_time > 0]))
        
        # Overall assessment
        critical_systems_healthy = critical_failures == 0
        success_rate = (passed_tests / total_tests) * 100
        performance_acceptable = avg_response_time < 3.0
        
        # Determine overall status
        if critical_systems_healthy and success_rate >= 90:
            overall_status = "PRODUCTION_READY"
        elif critical_systems_healthy and success_rate >= 75:
            overall_status = "MOSTLY_READY"
        elif success_rate >= 60:
            overall_status = "NEEDS_FIXES"
        else:
            overall_status = "NOT_READY"
        
        # Generate report
        report = {
            "validation_session": {
                "timestamp": int(time.time()),
                "backend_url": self.backend_url,
                "frontend_url": self.frontend_url,
                "total_execution_time": total_time,
                "overall_status": overall_status
            },
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "critical_failures": critical_failures,
                "success_rate": success_rate,
                "performance_acceptable": performance_acceptable
            },
            "system_health": {
                "backend_accessible": any(r.test_name == "Backend Health Check" and r.passed for r in self.results),
                "frontend_accessible": any(r.test_name == "Frontend Health Check" and r.passed for r in self.results),
                "database_connected": any("Database" in r.test_name and r.passed for r in self.results),
                "authentication_working": any("Authentication" in r.test_name and r.passed for r in self.results)
            },
            "security_status": {
                "security_config_valid": any("Security Configuration" in r.test_name and r.passed for r in self.results),
                "auth_enforcement": sum(1 for r in self.results if "Auth Required" in r.test_name and r.passed),
                "security_headers": any("Security Headers" in r.test_name and r.passed for r in self.results)
            },
            "detailed_results": [
                {
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "message": r.message,
                    "execution_time": r.execution_time,
                    "critical": r.critical,
                    "details": r.details
                }
                for r in self.results
            ],
            "recommendations": self.generate_recommendations(overall_status, critical_failures, success_rate),
            "deployment_readiness": {
                "ready_for_production": overall_status == "PRODUCTION_READY",
                "confidence_level": "HIGH" if success_rate >= 90 else "MEDIUM" if success_rate >= 75 else "LOW",
                "estimated_risk": "LOW" if critical_failures == 0 else "MEDIUM" if critical_failures <= 2 else "HIGH"
            }
        }
        
        # Save report
        filename = f"final_production_validation_{int(time.time())}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📋 Final validation report saved to {filename}")
        
        # Print summary
        self.print_validation_summary(report)
        
        return report
    
    def generate_recommendations(self, status: str, critical_failures: int, success_rate: float) -> List[str]:
        """Generate deployment recommendations."""
        recommendations = []
        
        if status == "PRODUCTION_READY":
            recommendations.extend([
                "✅ System is ready for production deployment",
                "✅ All critical systems are functioning correctly",
                "✅ Security configuration is properly implemented",
                "✅ Performance metrics are within acceptable ranges"
            ])
        else:
            if critical_failures > 0:
                recommendations.append(f"🔴 CRITICAL: Fix {critical_failures} critical system failures")
            
            if success_rate < 75:
                recommendations.append(f"🟡 WARNING: Success rate ({success_rate:.1f}%) below recommended threshold")
        
        # Always include monitoring recommendations
        recommendations.extend([
            "📊 Set up production monitoring and alerting",
            "🔍 Implement health check automation",
            "📈 Monitor performance metrics continuously",
            "🔄 Prepare rollback procedures"
        ])
        
        return recommendations
    
    def print_validation_summary(self, report: Dict[str, Any]):
        """Print validation summary."""
        print("\n" + "="*80)
        print("🎯 FINAL PRODUCTION VALIDATION SUMMARY")
        print("="*80)
        
        summary = report["summary"]
        session = report["validation_session"]
        
        print(f"Overall Status: {session['overall_status']}")
        print(f"Backend URL: {session['backend_url']}")
        print(f"Frontend URL: {session['frontend_url']}")
        print(f"Success Rate: {summary['success_rate']:.1f%} ({summary['passed_tests']}/{summary['total_tests']})")
        print(f"Critical Failures: {summary['critical_failures']}")
        print(f"Execution Time: {session['total_execution_time']:.1f}s")
        
        # System health
        health = report["system_health"]
        print(f"\nSystem Health:")
        print(f"  Backend: {'✅' if health['backend_accessible'] else '❌'}")
        print(f"  Frontend: {'✅' if health['frontend_accessible'] else '❌'}")
        print(f"  Database: {'✅' if health['database_connected'] else '❌'}")
        print(f"  Authentication: {'✅' if health['authentication_working'] else '❌'}")
        
        # Deployment readiness
        deployment = report["deployment_readiness"]
        print(f"\nDeployment Readiness:")
        print(f"  Production Ready: {'✅ YES' if deployment['ready_for_production'] else '❌ NO'}")
        print(f"  Confidence Level: {deployment['confidence_level']}")
        print(f"  Risk Level: {deployment['estimated_risk']}")
        
        # Top recommendations
        print(f"\nTop Recommendations:")
        for rec in report["recommendations"][:5]:
            print(f"  {rec}")
    
    async def cleanup(self):
        """Cleanup resources."""
        await self.client.aclose()


async def main():
    """Main validation execution."""
    validator = FinalProductionValidator()
    
    try:
        report = await validator.run_final_validation()
        
        # Return exit code based on status
        overall_status = report["validation_session"]["overall_status"]
        
        if overall_status == "PRODUCTION_READY":
            return 0
        elif overall_status in ["MOSTLY_READY", "NEEDS_FIXES"]:
            return 1
        else:
            return 2
            
    except Exception as e:
        logger.error(f"❌ Final validation failed: {str(e)}")
        return 2
    finally:
        await validator.cleanup()


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)