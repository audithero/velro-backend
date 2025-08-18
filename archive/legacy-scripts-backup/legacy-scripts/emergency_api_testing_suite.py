#!/usr/bin/env python3
"""
EMERGENCY API TESTING SUITE
Validates critical API endpoints after emergency fixes.
"""
import asyncio
import httpx
import logging
import json
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test configuration
BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 10.0

class EmergencyAPITester:
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "tests": []
        }
    
    async def test_endpoint(self, method: str, path: str, expected_status: int = 200, headers: dict = None, data: dict = None, description: str = ""):
        """Test a single endpoint."""
        self.results["total_tests"] += 1
        test_result = {
            "method": method,
            "path": path,
            "expected_status": expected_status,
            "description": description,
            "status": "FAILED",
            "actual_status": None,
            "error": None,
            "response_time": None
        }
        
        try:
            start_time = datetime.now()
            
            async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
                if method.upper() == "GET":
                    response = await client.get(f"{BASE_URL}{path}", headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(f"{BASE_URL}{path}", headers=headers, json=data)
                elif method.upper() == "OPTIONS":
                    response = await client.options(f"{BASE_URL}{path}", headers=headers)
                else:
                    raise ValueError(f"Unsupported method: {method}")
            
            end_time = datetime.now()
            test_result["response_time"] = (end_time - start_time).total_seconds()
            test_result["actual_status"] = response.status_code
            
            # Check if status matches expected
            if response.status_code == expected_status:
                test_result["status"] = "PASSED"
                self.results["passed"] += 1
                logger.info(f"✅ {method} {path} - Status: {response.status_code} ({test_result['response_time']:.3f}s)")
            else:
                test_result["status"] = "FAILED"
                test_result["error"] = f"Expected {expected_status}, got {response.status_code}"
                self.results["failed"] += 1
                logger.error(f"❌ {method} {path} - Expected: {expected_status}, Got: {response.status_code}")
                
                # Log response body for debugging
                try:
                    response_text = response.text[:500] if response.text else "No response body"
                    logger.error(f"   Response: {response_text}")
                except:
                    logger.error("   Could not read response body")
                    
        except Exception as e:
            test_result["status"] = "ERROR"
            test_result["error"] = str(e)
            self.results["failed"] += 1
            logger.error(f"💥 {method} {path} - Error: {str(e)}")
        
        self.results["tests"].append(test_result)
        return test_result

    async def run_emergency_tests(self):
        """Run emergency validation tests for critical endpoints."""
        logger.info("🚨 STARTING EMERGENCY API VALIDATION SUITE")
        logger.info("=" * 60)
        
        # Test 1: Health check (should always work)
        await self.test_endpoint("GET", "/health", 200, description="Basic health check")
        
        # Test 2: Root endpoint
        await self.test_endpoint("GET", "/", 200, description="Root API information")
        
        # Test 3: CORS preflight for auth endpoints
        await self.test_endpoint("OPTIONS", "/api/v1/auth/login", 200, description="CORS preflight for auth login")
        
        # Test 4: Models endpoint (public, no auth required)
        await self.test_endpoint("GET", "/api/v1/generations/models/supported", 200, description="Public models endpoint")
        
        # Test 5: Projects endpoint with mock auth (should not be 405)
        mock_headers = {"Authorization": "Bearer mock_token_test123"}
        await self.test_endpoint("GET", "/api/v1/projects/", 401, mock_headers, description="Projects endpoint with mock token (should get 401, not 405)")
        
        # Test 6: Generations endpoint with mock auth (should not be 500)
        await self.test_endpoint("GET", "/api/v1/generations/", 401, mock_headers, description="Generations endpoint with mock token (should get 401, not 500)")
        
        # Test 7: Credits stats endpoint (should not be 405)
        await self.test_endpoint("GET", "/api/v1/credits/stats", 401, mock_headers, description="Credits stats endpoint (should get 401, not 405)")
        
        # Test 8: Credits transactions endpoint (should not be 405)
        await self.test_endpoint("GET", "/api/v1/credits/transactions", 401, mock_headers, description="Credits transactions endpoint (should get 401, not 405)")
        
        logger.info("=" * 60)
        logger.info("🏁 EMERGENCY API VALIDATION COMPLETE")
        
        # Print summary
        total = self.results["total_tests"]
        passed = self.results["passed"]
        failed = self.results["failed"]
        success_rate = (passed / total * 100) if total > 0 else 0
        
        logger.info(f"📊 RESULTS: {passed}/{total} tests passed ({success_rate:.1f}% success rate)")
        
        if failed == 0:
            logger.info("🎉 ALL EMERGENCY TESTS PASSED - API IS OPERATIONAL!")
        else:
            logger.warning(f"⚠️ {failed} tests failed - API may have remaining issues")
        
        return self.results

async def main():
    """Main test runner."""
    tester = EmergencyAPITester()
    
    try:
        results = await tester.run_emergency_tests()
        
        # Save results to file
        with open("emergency_test_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info("📄 Test results saved to emergency_test_results.json")
        
        # Exit with appropriate code
        if results["failed"] == 0:
            exit(0)
        else:
            exit(1)
            
    except Exception as e:
        logger.error(f"💥 EMERGENCY TESTING FAILED: {e}")
        exit(2)

if __name__ == "__main__":
    asyncio.run(main())