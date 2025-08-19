#!/usr/bin/env python3
"""
Production CORS Validation Test Suite
Comprehensive testing for CORS functionality with real production endpoints.

This script validates:
1. Preflight OPTIONS requests work correctly
2. Actual POST/GET requests succeed without CORS errors
3. All required CORS headers are present and correct
4. Both development and production origins are handled
5. Specific failing scenarios from production logs
"""

import asyncio
import aiohttp
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import sys
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class CORSTestResult:
    """Test result for CORS validation."""
    endpoint: str
    method: str
    origin: str
    success: bool
    status_code: int
    headers: Dict[str, str]
    response_body: Optional[str]
    error: Optional[str]
    preflight_success: bool = False
    preflight_headers: Optional[Dict[str, str]] = None
    duration_ms: float = 0.0

@dataclass
class CORSValidationReport:
    """Complete CORS validation report."""
    timestamp: str
    backend_url: str
    frontend_origin: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    test_results: List[CORSTestResult]
    summary: Dict[str, any]
    recommendations: List[str]

class CORSProductionValidator:
    """Production CORS validation testing suite."""
    
    def __init__(self, backend_url: str, frontend_origin: str):
        self.backend_url = backend_url.rstrip('/')
        self.frontend_origin = frontend_origin.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.test_results: List[CORSTestResult] = []
        
        # Test endpoints to validate
        self.test_endpoints = [
            ("/api/v1/auth/login", "POST"),
            ("/api/v1/auth/logout", "POST"), 
            ("/api/v1/auth/register", "POST"),
            ("/api/v1/auth/refresh", "POST"),
            ("/api/v1/credits/balance", "GET"),
            ("/api/v1/credits/transactions", "GET"),
            ("/api/v1/generations", "POST"),
            ("/api/v1/generations", "GET"),
            ("/api/v1/projects", "GET"),
            ("/api/v1/projects", "POST"),
            ("/api/v1/models", "GET"),
            ("/health", "GET"),
            ("/", "GET")
        ]
        
        # Origins to test
        self.test_origins = [
            frontend_origin,
            "http://localhost:3000",
            "http://localhost:3001",
            "https://velro.ai",
            "https://www.velro.ai"
        ]
        
        # Expected CORS headers
        self.required_cors_headers = [
            "access-control-allow-origin",
            "access-control-allow-methods", 
            "access-control-allow-headers",
            "access-control-allow-credentials"
        ]
    
    async def __aenter__(self):
        """Async context manager entry."""
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def test_preflight_request(self, endpoint: str, origin: str, method: str = "POST") -> Tuple[bool, Dict[str, str], Optional[str]]:
        """Test CORS preflight OPTIONS request."""
        url = urljoin(self.backend_url, endpoint)
        
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type,accept"
        }
        
        try:
            start_time = time.time()
            async with self.session.options(url, headers=headers) as response:
                duration = (time.time() - start_time) * 1000
                response_headers = dict(response.headers)
                
                logger.info(f"OPTIONS {endpoint} from {origin}: {response.status} ({duration:.1f}ms)")
                
                # Check for successful preflight
                success = response.status in [200, 204]
                
                # Validate CORS headers
                for header in self.required_cors_headers:
                    if header not in response_headers:
                        logger.warning(f"Missing CORS header: {header}")
                        success = False
                
                return success, response_headers, None
                
        except Exception as e:
            logger.error(f"Preflight request failed for {endpoint}: {e}")
            return False, {}, str(e)
    
    async def test_actual_request(self, endpoint: str, origin: str, method: str, 
                                 headers: Optional[Dict[str, str]] = None,
                                 data: Optional[Dict] = None) -> CORSTestResult:
        """Test actual request after preflight."""
        url = urljoin(self.backend_url, endpoint)
        
        # Prepare headers
        request_headers = {
            "Origin": origin,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if headers:
            request_headers.update(headers)
        
        # Test preflight first
        preflight_success, preflight_headers, preflight_error = await self.test_preflight_request(
            endpoint, origin, method
        )
        
        # Test actual request
        start_time = time.time()
        try:
            kwargs = {"headers": request_headers}
            if data and method in ["POST", "PUT", "PATCH"]:
                kwargs["json"] = data
            
            async with self.session.request(method, url, **kwargs) as response:
                duration = (time.time() - start_time) * 1000
                response_headers = dict(response.headers)
                
                try:
                    response_body = await response.text()
                except:
                    response_body = None
                
                logger.info(f"{method} {endpoint} from {origin}: {response.status} ({duration:.1f}ms)")
                
                return CORSTestResult(
                    endpoint=endpoint,
                    method=method,
                    origin=origin,
                    success=response.status < 400,
                    status_code=response.status,
                    headers=response_headers,
                    response_body=response_body,
                    error=None,
                    preflight_success=preflight_success,
                    preflight_headers=preflight_headers,
                    duration_ms=duration
                )
                
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"{method} {endpoint} failed: {e}")
            
            return CORSTestResult(
                endpoint=endpoint,
                method=method,
                origin=origin,
                success=False,
                status_code=0,
                headers={},
                response_body=None,
                error=str(e),
                preflight_success=preflight_success,
                preflight_headers=preflight_headers,
                duration_ms=duration
            )
    
    async def test_login_scenario(self, origin: str) -> CORSTestResult:
        """Test the specific login scenario that was failing."""
        login_data = {
            "email": "test@example.com",
            "password": "testpassword123"
        }
        
        result = await self.test_actual_request(
            "/api/v1/auth/login",
            origin,
            "POST",
            data=login_data
        )
        
        # Additional validation for login endpoint
        if result.success:
            logger.info(f"✅ Login endpoint accessible from {origin}")
        else:
            logger.error(f"❌ Login endpoint failed from {origin}: {result.error or result.status_code}")
        
        return result
    
    async def test_credits_scenario(self, origin: str) -> CORSTestResult:
        """Test credits balance endpoint that was mentioned in logs."""
        # For credits, we need to test without auth (should get 401)
        result = await self.test_actual_request(
            "/api/v1/credits/balance",
            origin,
            "GET"
        )
        
        # 401 is expected without auth, but CORS should work
        if result.status_code == 401 and result.preflight_success:
            result.success = True  # CORS worked, auth failed as expected
            logger.info(f"✅ Credits endpoint CORS working from {origin} (401 expected)")
        
        return result
    
    async def run_comprehensive_validation(self) -> CORSValidationReport:
        """Run complete CORS validation test suite."""
        logger.info(f"🚀 Starting CORS validation for {self.backend_url}")
        logger.info(f"📱 Testing from frontend origin: {self.frontend_origin}")
        
        start_time = time.time()
        
        # Test all endpoint/origin combinations
        for endpoint, method in self.test_endpoints:
            for origin in self.test_origins:
                try:
                    result = await self.test_actual_request(endpoint, origin, method)
                    self.test_results.append(result)
                    
                    # Small delay to avoid overwhelming the server
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Test failed for {method} {endpoint} from {origin}: {e}")
                    self.test_results.append(CORSTestResult(
                        endpoint=endpoint,
                        method=method,
                        origin=origin,
                        success=False,
                        status_code=0,
                        headers={},
                        response_body=None,
                        error=str(e)
                    ))
        
        # Test specific scenarios
        logger.info("🎯 Testing specific login scenario...")
        login_result = await self.test_login_scenario(self.frontend_origin)
        self.test_results.append(login_result)
        
        logger.info("💰 Testing credits scenario...")
        credits_result = await self.test_credits_scenario(self.frontend_origin)
        self.test_results.append(credits_result)
        
        # Generate report
        total_time = time.time() - start_time
        passed = sum(1 for r in self.test_results if r.success)
        failed = len(self.test_results) - passed
        
        # Analyze results
        summary = self.analyze_results()
        recommendations = self.generate_recommendations()
        
        report = CORSValidationReport(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            backend_url=self.backend_url,
            frontend_origin=self.frontend_origin,
            total_tests=len(self.test_results),
            passed_tests=passed,
            failed_tests=failed,
            test_results=self.test_results,
            summary=summary,
            recommendations=recommendations
        )
        
        logger.info(f"✅ CORS validation completed in {total_time:.2f}s")
        logger.info(f"📊 Results: {passed}/{len(self.test_results)} tests passed")
        
        return report
    
    def analyze_results(self) -> Dict[str, any]:
        """Analyze test results and generate summary."""
        summary = {
            "preflight_success_rate": 0,
            "request_success_rate": 0,
            "origins_working": [],
            "origins_failing": [],
            "endpoints_working": [],
            "endpoints_failing": [],
            "common_errors": {},
            "cors_headers_present": {},
            "average_response_time": 0
        }
        
        if not self.test_results:
            return summary
        
        # Calculate success rates
        preflight_successes = sum(1 for r in self.test_results if r.preflight_success)
        request_successes = sum(1 for r in self.test_results if r.success)
        
        summary["preflight_success_rate"] = (preflight_successes / len(self.test_results)) * 100
        summary["request_success_rate"] = (request_successes / len(self.test_results)) * 100
        
        # Analyze by origin
        origin_stats = {}
        for result in self.test_results:
            origin = result.origin
            if origin not in origin_stats:
                origin_stats[origin] = {"passed": 0, "total": 0}
            origin_stats[origin]["total"] += 1
            if result.success:
                origin_stats[origin]["passed"] += 1
        
        for origin, stats in origin_stats.items():
            success_rate = (stats["passed"] / stats["total"]) * 100
            if success_rate >= 80:
                summary["origins_working"].append(f"{origin} ({success_rate:.1f}%)")
            else:
                summary["origins_failing"].append(f"{origin} ({success_rate:.1f}%)")
        
        # Analyze by endpoint  
        endpoint_stats = {}
        for result in self.test_results:
            endpoint = f"{result.method} {result.endpoint}"
            if endpoint not in endpoint_stats:
                endpoint_stats[endpoint] = {"passed": 0, "total": 0}
            endpoint_stats[endpoint]["total"] += 1
            if result.success:
                endpoint_stats[endpoint]["passed"] += 1
        
        for endpoint, stats in endpoint_stats.items():
            success_rate = (stats["passed"] / stats["total"]) * 100
            if success_rate >= 80:
                summary["endpoints_working"].append(f"{endpoint} ({success_rate:.1f}%)")
            else:
                summary["endpoints_failing"].append(f"{endpoint} ({success_rate:.1f}%)")
        
        # Common errors
        error_counts = {}
        for result in self.test_results:
            if result.error:
                error_counts[result.error] = error_counts.get(result.error, 0) + 1
        summary["common_errors"] = error_counts
        
        # CORS headers analysis
        header_counts = {}
        for result in self.test_results:
            for header in self.required_cors_headers:
                if header in result.headers:
                    header_counts[header] = header_counts.get(header, 0) + 1
        
        total_responses = len([r for r in self.test_results if r.headers])
        for header, count in header_counts.items():
            summary["cors_headers_present"][header] = f"{count}/{total_responses} ({(count/total_responses)*100:.1f}%)" if total_responses > 0 else "0/0"
        
        # Average response time
        response_times = [r.duration_ms for r in self.test_results if r.duration_ms > 0]
        summary["average_response_time"] = sum(response_times) / len(response_times) if response_times else 0
        
        return summary
    
    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        failed_results = [r for r in self.test_results if not r.success]
        
        if not failed_results:
            recommendations.append("✅ All CORS tests passed! The configuration is working correctly.")
            return recommendations
        
        # Check for preflight failures
        preflight_failures = [r for r in failed_results if not r.preflight_success]
        if preflight_failures:
            recommendations.append(
                f"❌ {len(preflight_failures)} preflight requests failed. "
                "Check that OPTIONS method is allowed and CORS headers are set correctly."
            )
        
        # Check for missing headers
        missing_headers = []
        for header in self.required_cors_headers:
            header_present = any(header in r.headers for r in self.test_results if r.headers)
            if not header_present:
                missing_headers.append(header)
        
        if missing_headers:
            recommendations.append(
                f"❌ Missing CORS headers: {', '.join(missing_headers)}. "
                "Add these headers to the CORS middleware configuration."
            )
        
        # Check for origin issues
        origin_failures = {}
        for result in failed_results:
            origin = result.origin
            origin_failures[origin] = origin_failures.get(origin, 0) + 1
        
        if origin_failures:
            recommendations.append(
                f"❌ Origin-specific failures detected: "
                f"{', '.join([f'{origin} ({count} failures)' for origin, count in origin_failures.items()])}. "
                "Verify that these origins are included in the allow_origins list."
            )
        
        # Check for method issues
        method_failures = {}
        for result in failed_results:
            method = result.method
            method_failures[method] = method_failures.get(method, 0) + 1
        
        if method_failures:
            recommendations.append(
                f"❌ Method-specific failures: "
                f"{', '.join([f'{method} ({count} failures)' for method, count in method_failures.items()])}. "
                "Ensure all required methods are in allow_methods list."
            )
        
        return recommendations

async def main():
    """Main execution function."""
    # Configuration
    BACKEND_URL = "https://velro-backend-production.up.railway.app"
    FRONTEND_ORIGIN = "https://velro-frontend-production.up.railway.app"
    
    print("🚀 CORS Production Validation Test Suite")
    print("=" * 50)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Frontend Origin: {FRONTEND_ORIGIN}")
    print("=" * 50)
    
    try:
        async with CORSProductionValidator(BACKEND_URL, FRONTEND_ORIGIN) as validator:
            report = await validator.run_comprehensive_validation()
            
            # Save report to file
            report_filename = f"cors_validation_report_{int(time.time())}.json"
            with open(report_filename, 'w') as f:
                json.dump(asdict(report), f, indent=2)
            
            # Print summary
            print("\n" + "=" * 50)
            print("📊 CORS VALIDATION RESULTS")
            print("=" * 50)
            print(f"Timestamp: {report.timestamp}")
            print(f"Total Tests: {report.total_tests}")
            print(f"Passed: {report.passed_tests} ({(report.passed_tests/report.total_tests)*100:.1f}%)")
            print(f"Failed: {report.failed_tests} ({(report.failed_tests/report.total_tests)*100:.1f}%)")
            
            print(f"\n📈 PERFORMANCE METRICS:")
            print(f"Preflight Success Rate: {report.summary['preflight_success_rate']:.1f}%")
            print(f"Request Success Rate: {report.summary['request_success_rate']:.1f}%")
            print(f"Average Response Time: {report.summary['average_response_time']:.1f}ms")
            
            print(f"\n🌐 ORIGINS ANALYSIS:")
            if report.summary['origins_working']:
                print("✅ Working Origins:")
                for origin in report.summary['origins_working']:
                    print(f"   {origin}")
            
            if report.summary['origins_failing']:
                print("❌ Failing Origins:")
                for origin in report.summary['origins_failing']:
                    print(f"   {origin}")
            
            print(f"\n🔧 ENDPOINTS ANALYSIS:")
            if report.summary['endpoints_working']:
                print("✅ Working Endpoints:")
                for endpoint in report.summary['endpoints_working'][:5]:  # Show top 5
                    print(f"   {endpoint}")
                if len(report.summary['endpoints_working']) > 5:
                    print(f"   ... and {len(report.summary['endpoints_working']) - 5} more")
            
            if report.summary['endpoints_failing']:
                print("❌ Failing Endpoints:")
                for endpoint in report.summary['endpoints_failing']:
                    print(f"   {endpoint}")
            
            print(f"\n🔍 CORS HEADERS STATUS:")
            for header, status in report.summary['cors_headers_present'].items():
                print(f"   {header}: {status}")
            
            if report.summary['common_errors']:
                print(f"\n⚠️ COMMON ERRORS:")
                for error, count in list(report.summary['common_errors'].items())[:3]:  # Top 3 errors
                    print(f"   {error}: {count} occurrences")
            
            print(f"\n💡 RECOMMENDATIONS:")
            for rec in report.recommendations:
                print(f"   {rec}")
            
            print(f"\n📄 Full report saved to: {report_filename}")
            
            # Return appropriate exit code
            if report.failed_tests == 0:
                print("\n🎉 All CORS tests passed! The fix is working correctly.")
                sys.exit(0)
            else:
                print(f"\n⚠️ {report.failed_tests} tests failed. Please review the issues above.")
                sys.exit(1)
                
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        print(f"\n❌ CORS validation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())