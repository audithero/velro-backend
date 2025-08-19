#!/usr/bin/env python3
"""
Endpoint Testing with Valid Authentication
==========================================

This script uses the correct production URL and valid demo credentials
to test all backend endpoints and identify specific issues.

Author: Backend Testing Specialist
Date: 2025-08-03
"""

import asyncio
import aiohttp
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Correct production configuration
BASE_URL = "https://velro-003-backend-production.up.railway.app"
DEMO_EMAIL = "demo@velro.app"
DEMO_PASSWORD = "velrodemo123"

@dataclass
class TestResult:
    """Test result data structure"""
    endpoint: str
    method: str
    status_code: int
    response_time: float
    success: bool
    error_message: Optional[str] = None
    response_data: Optional[Dict] = None
    headers: Optional[Dict] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

class EndpointTesterWithAuth:
    """Endpoint testing with proper authentication"""
    
    def __init__(self):
        self.base_url = BASE_URL
        self.demo_email = DEMO_EMAIL
        self.demo_password = DEMO_PASSWORD
        self.access_token = None
        self.user_id = None
        self.user_email = None
        self.credits_balance = None
        self.test_results = []
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=20,
            ssl=False
        )
        
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Velro-Endpoint-Testing-Suite/1.0'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def make_request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        use_auth: bool = False
    ) -> TestResult:
        """Make HTTP request and return test result"""
        url = f"{self.base_url}{path}"
        start_time = time.time()
        
        # Prepare headers
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
            
        # Add authentication if required and available
        if use_auth and self.access_token:
            request_headers["Authorization"] = f"Bearer {self.access_token}"
        
        try:
            logger.info(f"Testing {method} {path}")
            
            async with self.session.request(
                method=method.upper(),
                url=url,
                json=data if data else None,
                headers=request_headers,
                ssl=False
            ) as response:
                response_time = time.time() - start_time
                
                # Read response data
                try:
                    response_data = await response.json()
                except:
                    response_data = {"raw_response": await response.text()}
                
                # Determine success based on status code
                success = 200 <= response.status < 400
                error_message = None
                
                if not success:
                    error_message = f"HTTP {response.status}: {response.reason}"
                    if isinstance(response_data, dict) and "detail" in response_data:
                        error_message += f" - {response_data['detail']}"
                    elif isinstance(response_data, dict) and "message" in response_data:
                        error_message += f" - {response_data['message']}"
                
                result = TestResult(
                    endpoint=path,
                    method=method.upper(),
                    status_code=response.status,
                    response_time=response_time,
                    success=success,
                    error_message=error_message,
                    response_data=response_data,
                    headers=dict(response.headers)
                )
                
                # Log result
                status_icon = "✅" if success else "❌"
                logger.info(f"{status_icon} {method} {path}: {response.status} ({response_time:.3f}s)")
                
                if not success and response_data:
                    logger.warning(f"   Error details: {response_data}")
                
                self.test_results.append(result)
                return result
                
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            result = TestResult(
                endpoint=path,
                method=method.upper(),
                status_code=0,
                response_time=response_time,
                success=False,
                error_message="Request timeout"
            )
            self.test_results.append(result)
            return result
        except Exception as e:
            response_time = time.time() - start_time
            result = TestResult(
                endpoint=path,
                method=method.upper(),
                status_code=0,
                response_time=response_time,
                success=False,
                error_message=f"Request failed: {str(e)}"
            )
            self.test_results.append(result)
            return result

    async def authenticate(self) -> bool:
        """Authenticate and obtain access token"""
        logger.info("=== Authentication Phase ===")
        
        login_data = {
            "email": self.demo_email,
            "password": self.demo_password
        }
        
        result = await self.make_request("POST", "/api/v1/auth/login", data=login_data)
        
        if result.success and result.response_data:
            # Extract tokens and user info
            self.access_token = result.response_data.get("access_token")
            
            if self.access_token:
                logger.info(f"✅ Authentication successful")
                logger.info(f"🔑 Access token: {self.access_token[:20]}...")
                
                # Extract user info from login response
                user_data = result.response_data.get("user", {})
                self.user_id = user_data.get("id")
                self.user_email = user_data.get("email")
                self.credits_balance = user_data.get("credits_balance")
                
                logger.info(f"👤 User ID: {self.user_id}")
                logger.info(f"📧 User Email: {self.user_email}")
                logger.info(f"💰 Credits Balance: {self.credits_balance}")
                
                # Test /auth/me to verify token works
                me_result = await self.make_request("GET", "/api/v1/auth/me", use_auth=True)
                
                if me_result.success:
                    logger.info("✅ Token validation successful")
                    return True
                else:
                    logger.error("❌ Token validation failed")
                    return False
            else:
                logger.error("❌ No access_token in login response")
                return False
        else:
            logger.error(f"❌ Authentication failed: {result.error_message}")
            if result.response_data:
                logger.error(f"   Response: {result.response_data}")
            return False

    async def test_all_endpoints(self):
        """Test all endpoints systematically"""
        logger.info("=== System Endpoints Testing ===")
        
        # System endpoints (no auth required)
        system_endpoints = [
            ("GET", "/", "Root endpoint"),
            ("GET", "/health", "Health check"),
            ("GET", "/security-status", "Security status"),
            ("GET", "/cors-test", "CORS test"),
            ("GET", "/performance-metrics", "Performance metrics"),
        ]
        
        for method, path, description in system_endpoints:
            await self.make_request(method, path)
        
        logger.info("=== Credits Endpoints Testing ===")
        
        # Credits endpoints (investigating 405 errors)
        credits_endpoints = [
            ("GET", "/api/v1/credits/balance/", "Get credits balance"),
            ("GET", "/api/v1/credits/transactions/", "List transactions"),
            ("GET", "/api/v1/credits/stats/", "Get usage stats"),
        ]
        
        for method, path, description in credits_endpoints:
            result = await self.make_request(method, path, use_auth=True)
            
            # Special analysis for credits balance
            if path == "/api/v1/credits/balance/" and result.success:
                balance = result.response_data.get("balance")
                logger.info(f"   💰 Credits balance from API: {balance}")
                if balance != self.credits_balance:
                    logger.warning(f"   ⚠️ Balance mismatch! Login: {self.credits_balance}, API: {balance}")
        
        logger.info("=== Projects Endpoints Testing ===")
        
        # Projects endpoints (investigating 405 errors)
        projects_endpoints = [
            ("GET", "/api/v1/projects/", "List projects"),
            ("POST", "/api/v1/projects/", "Create project"),
        ]
        
        for method, path, description in projects_endpoints:
            data = None
            if method == "POST":
                data = {
                    "title": "Test Project",
                    "description": "Endpoint validation test project",
                    "visibility": "private"
                }
            
            await self.make_request(method, path, data=data, use_auth=True)
        
        logger.info("=== Generations Endpoints Testing ===")
        
        # Generations endpoints (investigating 500 errors)
        generations_endpoints = [
            ("GET", "/api/v1/generations/", "List generations"),
            ("GET", "/api/v1/generations/stats", "Get generation stats"),
            ("GET", "/api/v1/generations/models/supported", "Get supported models"),
        ]
        
        for method, path, description in generations_endpoints:
            use_auth = not path.endswith("models/supported")  # models/supported doesn't need auth
            await self.make_request(method, path, use_auth=use_auth)
        
        logger.info("=== Error Condition Testing ===")
        
        # Test without authentication (should return 401)
        error_test_endpoints = [
            ("GET", "/api/v1/credits/balance/", "Credits balance without auth"),
            ("GET", "/api/v1/projects/", "Projects without auth"),
            ("GET", "/api/v1/generations/", "Generations without auth"),
        ]
        
        for method, path, description in error_test_endpoints:
            result = await self.make_request(method, path, use_auth=False)
            if result.status_code not in [401, 403]:
                logger.warning(f"   ⚠️ Expected 401/403 but got {result.status_code} for {path}")

    async def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - successful_tests
        
        # Categorize failures
        failures_by_status = {}
        critical_issues = []
        
        for result in self.test_results:
            if not result.success:
                status = result.status_code
                if status not in failures_by_status:
                    failures_by_status[status] = []
                failures_by_status[status].append(result)
                
                # Identify critical issues
                if status == 405:
                    critical_issues.append({
                        "type": "method_not_allowed",
                        "severity": "high",
                        "endpoint": result.endpoint,
                        "method": result.method,
                        "description": f"405 Method Not Allowed on {result.method} {result.endpoint}",
                        "potential_cause": "Router configuration issue or missing route handler"
                    })
                elif status == 500:
                    critical_issues.append({
                        "type": "internal_server_error", 
                        "severity": "critical",
                        "endpoint": result.endpoint,
                        "method": result.method,
                        "description": f"500 Internal Server Error on {result.method} {result.endpoint}",
                        "potential_cause": "Service implementation error or database connectivity issue"
                    })
        
        # Check credits balance issue
        for result in self.test_results:
            if (result.endpoint == "/api/v1/credits/balance/" and 
                result.success and 
                result.response_data and 
                result.response_data.get("balance") == 100):
                critical_issues.append({
                    "type": "incorrect_credits_balance",
                    "severity": "medium",
                    "endpoint": result.endpoint,
                    "description": "Credits balance returning 100 instead of expected value",
                    "potential_cause": "Database initialization issue or credit allocation problem"
                })
        
        # Performance analysis
        response_times = [r.response_time for r in self.test_results if r.response_time > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        report = {
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "success_rate": (successful_tests / total_tests * 100) if total_tests > 0 else 0,
                "average_response_time": avg_response_time
            },
            "authentication": {
                "access_token_obtained": bool(self.access_token),
                "user_id": self.user_id,
                "user_email": self.user_email,
                "credits_balance": self.credits_balance
            },
            "failures_by_status_code": {
                str(status): len(results) for status, results in failures_by_status.items()
            },
            "critical_issues": critical_issues,
            "detailed_results": [asdict(result) for result in self.test_results],
            "timestamp": datetime.now().isoformat(),
            "target_url": self.base_url,
            "test_credentials": {
                "email": self.demo_email,
                "password_length": len(self.demo_password)
            }
        }
        
        return report

    async def run_comprehensive_tests(self):
        """Run all tests and generate report"""
        start_time = time.time()
        logger.info("🚀 Starting Comprehensive Endpoint Testing with Authentication")
        logger.info(f"🎯 Target: {self.base_url}")
        logger.info(f"👤 Test User: {self.demo_email}")
        
        # Authenticate first
        auth_success = await self.authenticate()
        
        if not auth_success:
            logger.error("❌ Cannot proceed without authentication")
            return await self.generate_report()
        
        # Run all endpoint tests
        await self.test_all_endpoints()
        
        total_time = time.time() - start_time
        logger.info(f"⏱️ Total test time: {total_time:.2f}s")
        
        # Generate and display report
        report = await self.generate_report()
        
        logger.info("=" * 80)
        logger.info("🎯 COMPREHENSIVE TEST RESULTS SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total Tests: {report['summary']['total_tests']}")
        logger.info(f"Successful: {report['summary']['successful_tests']}")
        logger.info(f"Failed: {report['summary']['failed_tests']}")
        logger.info(f"Success Rate: {report['summary']['success_rate']:.1f}%")
        logger.info(f"Average Response Time: {report['summary']['average_response_time']:.3f}s")
        
        if report['authentication']['access_token_obtained']:
            logger.info(f"✅ Authentication: SUCCESS")
            logger.info(f"👤 User: {report['authentication']['user_email']}")
            logger.info(f"💰 Credits: {report['authentication']['credits_balance']}")
        else:
            logger.error("❌ Authentication: FAILED")
        
        if report['critical_issues']:
            logger.info("\n🚨 CRITICAL ISSUES FOUND:")
            for issue in report['critical_issues']:
                logger.error(f"  • {issue['description']}")
                logger.error(f"    Severity: {issue['severity']}")
                logger.error(f"    Cause: {issue['potential_cause']}")
        else:
            logger.info("\n✅ No critical issues found!")
        
        # Save detailed report
        output_file = f"endpoint_test_results_authenticated_{int(time.time())}.json"
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"\n📊 Detailed results saved to: {output_file}")
        
        return report

async def main():
    """Main function"""
    async with EndpointTesterWithAuth() as tester:
        try:
            report = await tester.run_comprehensive_tests()
            
            # Return exit code based on critical issues
            if report['critical_issues']:
                sys.exit(1)
            else:
                sys.exit(0)
                
        except Exception as e:
            logger.error(f"❌ Testing suite failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())