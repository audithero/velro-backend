#!/usr/bin/env python3
"""
Comprehensive Backend Endpoint Testing Suite
============================================

This script performs extensive testing of all backend endpoints to identify
and diagnose issues with the Velro API production deployment.

Key Issues to Investigate:
- 405 errors on /projects and /credits/balance GET requests
- 500 errors on /generations GET requests
- Credits balance returning 100 instead of 1400

Test Strategy:
1. System health checks
2. Authentication flow validation
3. Endpoint access testing with proper authentication
4. Error analysis and reporting
5. Performance benchmarking

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
import argparse
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

@dataclass
class AuthTokens:
    """Authentication tokens container"""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None

class ComprehensiveEndpointTester:
    """Comprehensive endpoint testing suite"""
    
    def __init__(self, base_url: str, test_user_email: str, test_user_password: str):
        self.base_url = base_url.rstrip('/')
        self.test_user_email = test_user_email
        self.test_user_password = test_user_password
        self.auth_tokens = AuthTokens()
        self.test_results: List[TestResult] = []
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Test endpoints configuration
        self.endpoints = {
            "system": [
                {"path": "/", "method": "GET", "auth_required": False},
                {"path": "/health", "method": "GET", "auth_required": False},
                {"path": "/security-status", "method": "GET", "auth_required": False},
                {"path": "/cors-test", "method": "GET", "auth_required": False},
                {"path": "/performance-metrics", "method": "GET", "auth_required": False},
            ],
            "auth": [
                {"path": "/api/v1/auth/login", "method": "POST", "auth_required": False},
                {"path": "/api/v1/auth/register", "method": "POST", "auth_required": False},
                {"path": "/api/v1/auth/me", "method": "GET", "auth_required": True},
                {"path": "/api/v1/auth/debug-auth", "method": "GET", "auth_required": True},
                {"path": "/api/v1/auth/security-info", "method": "GET", "auth_required": False},
            ],
            "credits": [
                {"path": "/api/v1/credits/balance/", "method": "GET", "auth_required": True},
                {"path": "/api/v1/credits/transactions/", "method": "GET", "auth_required": True},
                {"path": "/api/v1/credits/stats/", "method": "GET", "auth_required": True},
            ],
            "projects": [
                {"path": "/api/v1/projects/", "method": "GET", "auth_required": True},
                {"path": "/api/v1/projects/", "method": "POST", "auth_required": True},
            ],
            "generations": [
                {"path": "/api/v1/generations/", "method": "GET", "auth_required": True},
                {"path": "/api/v1/generations/stats", "method": "GET", "auth_required": True},
                {"path": "/api/v1/generations/models/supported", "method": "GET", "auth_required": False},
            ],
        }

    async def __aenter__(self):
        """Async context manager entry"""
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=20,
            ssl=False  # Handle SSL verification separately
        )
        
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Velro-Backend-Testing-Suite/1.0'
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
        auth_required: bool = False
    ) -> TestResult:
        """Make HTTP request and return test result"""
        url = f"{self.base_url}{path}"
        start_time = time.time()
        
        # Prepare headers
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
            
        # Add authentication if required and available
        if auth_required and self.auth_tokens.access_token:
            request_headers["Authorization"] = f"Bearer {self.auth_tokens.access_token}"
        
        try:
            logger.info(f"Testing {method} {path}")
            
            async with self.session.request(
                method=method.upper(),
                url=url,
                json=data if data else None,
                headers=request_headers,
                ssl=False  # Handle SSL issues in production
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
                
                return TestResult(
                    endpoint=path,
                    method=method.upper(),
                    status_code=response.status,
                    response_time=response_time,
                    success=success,
                    error_message=error_message,
                    response_data=response_data,
                    headers=dict(response.headers)
                )
                
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            return TestResult(
                endpoint=path,
                method=method.upper(),
                status_code=0,
                response_time=response_time,
                success=False,
                error_message="Request timeout"
            )
        except Exception as e:
            response_time = time.time() - start_time
            return TestResult(
                endpoint=path,
                method=method.upper(),
                status_code=0,
                response_time=response_time,
                success=False,
                error_message=f"Request failed: {str(e)}"
            )

    async def test_authentication_flow(self) -> bool:
        """Test authentication and obtain tokens"""
        logger.info("=== Testing Authentication Flow ===")
        
        # Test login
        login_data = {
            "email": self.test_user_email,
            "password": self.test_user_password
        }
        
        result = await self.make_request("POST", "/api/v1/auth/login", data=login_data)
        self.test_results.append(result)
        
        if result.success and result.response_data:
            # Extract tokens
            if "access_token" in result.response_data:
                self.auth_tokens.access_token = result.response_data["access_token"]
                if "refresh_token" in result.response_data:
                    self.auth_tokens.refresh_token = result.response_data["refresh_token"]
                
                logger.info("✅ Authentication successful")
                logger.info(f"Access token: {self.auth_tokens.access_token[:20]}...")
                
                # Test /auth/me to get user info
                me_result = await self.make_request("GET", "/api/v1/auth/me", auth_required=True)
                self.test_results.append(me_result)
                
                if me_result.success and me_result.response_data:
                    self.auth_tokens.user_id = me_result.response_data.get("id")
                    self.auth_tokens.user_email = me_result.response_data.get("email")
                    logger.info(f"User ID: {self.auth_tokens.user_id}")
                    logger.info(f"User Email: {self.auth_tokens.user_email}")
                
                return True
            else:
                logger.error("❌ Login succeeded but no access_token in response")
                logger.error(f"Response: {result.response_data}")
                return False
        else:
            logger.error("❌ Authentication failed")
            logger.error(f"Status: {result.status_code}, Error: {result.error_message}")
            logger.error(f"Response: {result.response_data}")
            return False

    async def test_system_endpoints(self):
        """Test system health and status endpoints"""
        logger.info("=== Testing System Endpoints ===")
        
        for endpoint_config in self.endpoints["system"]:
            result = await self.make_request(
                endpoint_config["method"], 
                endpoint_config["path"],
                auth_required=endpoint_config["auth_required"]
            )
            self.test_results.append(result)
            
            # Log result
            status_icon = "✅" if result.success else "❌"
            logger.info(f"{status_icon} {endpoint_config['method']} {endpoint_config['path']}: {result.status_code} ({result.response_time:.3f}s)")
            
            if not result.success:
                logger.error(f"   Error: {result.error_message}")

    async def test_credits_endpoints(self):
        """Test credits-related endpoints - investigating the 405 error issue"""
        logger.info("=== Testing Credits Endpoints ===")
        
        for endpoint_config in self.endpoints["credits"]:
            result = await self.make_request(
                endpoint_config["method"], 
                endpoint_config["path"],
                auth_required=endpoint_config["auth_required"]
            )
            self.test_results.append(result)
            
            # Log result with special attention to 405 errors
            status_icon = "✅" if result.success else "❌"
            logger.info(f"{status_icon} {endpoint_config['method']} {endpoint_config['path']}: {result.status_code} ({result.response_time:.3f}s)")
            
            if not result.success:
                logger.error(f"   Error: {result.error_message}")
                if result.status_code == 405:
                    logger.error(f"   🚨 METHOD NOT ALLOWED - Router configuration issue!")
                    logger.error(f"   Response headers: {result.headers}")
                    
            # Special analysis for credits balance
            if endpoint_config["path"] == "/api/v1/credits/balance/" and result.success:
                balance = result.response_data.get("balance")
                logger.info(f"   💰 Credits balance: {balance}")
                if balance == 100:
                    logger.warning(f"   ⚠️ Balance is 100 - expected 1400!")

    async def test_projects_endpoints(self):
        """Test projects endpoints - investigating the 405 error issue"""
        logger.info("=== Testing Projects Endpoints ===")
        
        for endpoint_config in self.endpoints["projects"]:
            # For POST, add sample data
            data = None
            if endpoint_config["method"] == "POST":
                data = {
                    "title": "Test Project",
                    "description": "Test project for endpoint validation",
                    "visibility": "private"
                }
            
            result = await self.make_request(
                endpoint_config["method"], 
                endpoint_config["path"],
                data=data,
                auth_required=endpoint_config["auth_required"]
            )
            self.test_results.append(result)
            
            # Log result with special attention to 405 errors
            status_icon = "✅" if result.success else "❌"
            logger.info(f"{status_icon} {endpoint_config['method']} {endpoint_config['path']}: {result.status_code} ({result.response_time:.3f}s)")
            
            if not result.success:
                logger.error(f"   Error: {result.error_message}")
                if result.status_code == 405:
                    logger.error(f"   🚨 METHOD NOT ALLOWED - Router configuration issue!")
                    logger.error(f"   Response headers: {result.headers}")

    async def test_generations_endpoints(self):
        """Test generations endpoints - investigating the 500 error issue"""
        logger.info("=== Testing Generations Endpoints ===")
        
        for endpoint_config in self.endpoints["generations"]:
            result = await self.make_request(
                endpoint_config["method"], 
                endpoint_config["path"],
                auth_required=endpoint_config["auth_required"]
            )
            self.test_results.append(result)
            
            # Log result with special attention to 500 errors
            status_icon = "✅" if result.success else "❌"
            logger.info(f"{status_icon} {endpoint_config['method']} {endpoint_config['path']}: {result.status_code} ({result.response_time:.3f}s)")
            
            if not result.success:
                logger.error(f"   Error: {result.error_message}")
                if result.status_code == 500:
                    logger.error(f"   🚨 INTERNAL SERVER ERROR - Service implementation issue!")
                    if result.response_data:
                        logger.error(f"   Error details: {result.response_data}")

    async def test_specific_error_cases(self):
        """Test specific error cases and edge conditions"""
        logger.info("=== Testing Specific Error Cases ===")
        
        # Test endpoints without authentication when auth is required
        test_cases = [
            {"path": "/api/v1/credits/balance/", "method": "GET"},
            {"path": "/api/v1/projects/", "method": "GET"},
            {"path": "/api/v1/generations/", "method": "GET"},
        ]
        
        for case in test_cases:
            result = await self.make_request(case["method"], case["path"], auth_required=False)
            self.test_results.append(result)
            
            status_icon = "✅" if result.status_code in [401, 403] else "❌"
            logger.info(f"{status_icon} {case['method']} {case['path']} (no auth): {result.status_code}")
            
            if result.status_code not in [401, 403]:
                logger.warning(f"   ⚠️ Expected 401/403 but got {result.status_code}")

    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run all tests and return comprehensive results"""
        start_time = time.time()
        logger.info("🚀 Starting Comprehensive Endpoint Testing Suite")
        logger.info(f"Target: {self.base_url}")
        logger.info(f"Test User: {self.test_user_email}")
        
        # Test system endpoints first
        await self.test_system_endpoints()
        
        # Test authentication flow
        auth_success = await self.test_authentication_flow()
        
        if auth_success:
            # Test authenticated endpoints
            await self.test_credits_endpoints()
            await self.test_projects_endpoints()
            await self.test_generations_endpoints()
        else:
            logger.error("❌ Skipping authenticated endpoint tests due to auth failure")
        
        # Test specific error cases
        await self.test_specific_error_cases()
        
        total_time = time.time() - start_time
        
        # Generate comprehensive report
        return self.generate_comprehensive_report(total_time)

    def generate_comprehensive_report(self, total_time: float) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - successful_tests
        
        # Categorize failures
        failures_by_status = {}
        failures_by_endpoint = {}
        
        for result in self.test_results:
            if not result.success:
                status = result.status_code
                if status not in failures_by_status:
                    failures_by_status[status] = []
                failures_by_status[status].append(result)
                
                endpoint = result.endpoint
                if endpoint not in failures_by_endpoint:
                    failures_by_endpoint[endpoint] = []
                failures_by_endpoint[endpoint].append(result)
        
        # Performance analysis
        response_times = [r.response_time for r in self.test_results if r.response_time > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        report = {
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "success_rate": (successful_tests / total_tests * 100) if total_tests > 0 else 0,
                "total_time": total_time,
                "average_response_time": avg_response_time
            },
            "authentication": {
                "access_token_obtained": bool(self.auth_tokens.access_token),
                "user_id": self.auth_tokens.user_id,
                "user_email": self.auth_tokens.user_email
            },
            "failures_by_status_code": {
                str(status): len(results) for status, results in failures_by_status.items()
            },
            "critical_issues": self.identify_critical_issues(),
            "detailed_results": [asdict(result) for result in self.test_results],
            "timestamp": datetime.now().isoformat(),
            "target_url": self.base_url
        }
        
        return report

    def identify_critical_issues(self) -> List[Dict[str, Any]]:
        """Identify and categorize critical issues"""
        issues = []
        
        # Check for 405 errors on known endpoints
        for result in self.test_results:
            if result.status_code == 405:
                issues.append({
                    "type": "method_not_allowed",
                    "severity": "high",
                    "endpoint": result.endpoint,
                    "method": result.method,
                    "description": f"405 Method Not Allowed on {result.method} {result.endpoint}",
                    "potential_cause": "Router configuration issue or missing route handler"
                })
        
        # Check for 500 errors
        for result in self.test_results:
            if result.status_code == 500:
                issues.append({
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
                issues.append({
                    "type": "incorrect_credits_balance",
                    "severity": "medium",
                    "endpoint": result.endpoint,
                    "description": "Credits balance returning 100 instead of expected 1400",
                    "potential_cause": "Database initialization issue or credit allocation problem"
                })
        
        return issues

async def main():
    """Main function to run the testing suite"""
    parser = argparse.ArgumentParser(description="Comprehensive Backend Endpoint Testing Suite")
    parser.add_argument(
        "--base-url", 
        default="https://velro-003-backend-production.up.railway.app",
        help="Base URL of the backend API"
    )
    parser.add_argument(
        "--email", 
        default="test@apostle.digital",
        help="Test user email"
    )
    parser.add_argument(
        "--password", 
        default="TestPassword123!",
        help="Test user password"
    )
    parser.add_argument(
        "--output", 
        default="endpoint_testing_results.json",
        help="Output file for test results"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    async with ComprehensiveEndpointTester(args.base_url, args.email, args.password) as tester:
        try:
            report = await tester.run_comprehensive_tests()
            
            # Save results to file
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2)
            
            # Print summary
            logger.info("=" * 80)
            logger.info("🎯 COMPREHENSIVE TEST RESULTS SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Total Tests: {report['summary']['total_tests']}")
            logger.info(f"Successful: {report['summary']['successful_tests']}")
            logger.info(f"Failed: {report['summary']['failed_tests']}")
            logger.info(f"Success Rate: {report['summary']['success_rate']:.1f}%")
            logger.info(f"Average Response Time: {report['summary']['average_response_time']:.3f}s")
            
            if report['critical_issues']:
                logger.info("\n🚨 CRITICAL ISSUES FOUND:")
                for issue in report['critical_issues']:
                    logger.error(f"  • {issue['description']}")
                    logger.error(f"    Cause: {issue['potential_cause']}")
            
            logger.info(f"\n📊 Detailed results saved to: {args.output}")
            
            # Return exit code based on test results
            if report['summary']['failed_tests'] > 0:
                sys.exit(1)
            else:
                sys.exit(0)
                
        except Exception as e:
            logger.error(f"❌ Testing suite failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())