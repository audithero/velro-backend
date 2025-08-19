#!/usr/bin/env python3
"""
Browser CORS Simulation Test
Simulates exact browser behavior for CORS requests to validate the fix.
"""

import asyncio
import aiohttp
import json
import logging
import time
from typing import Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BrowserCORSSimulator:
    """Simulates browser CORS behavior for testing."""
    
    def __init__(self, backend_url: str, frontend_origin: str):
        self.backend_url = backend_url.rstrip('/')
        self.frontend_origin = frontend_origin.rstrip('/')
        self.session = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def simulate_browser_request(self, endpoint: str, method: str = "POST", 
                                     data: Dict = None, headers: Dict = None) -> Dict:
        """Simulate exact browser CORS behavior."""
        
        url = f"{self.backend_url}{endpoint}"
        result = {
            "endpoint": endpoint,
            "method": method,
            "origin": self.frontend_origin,
            "preflight_needed": method in ["POST", "PUT", "PATCH", "DELETE"],
            "preflight_success": False,
            "request_success": False,
            "cors_headers": {},
            "errors": []
        }
        
        # Default headers for browser requests
        request_headers = {
            "Origin": self.frontend_origin,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Dest": "empty"
        }
        
        if headers:
            request_headers.update(headers)
        
        # Step 1: Preflight request (if needed)
        if result["preflight_needed"]:
            logger.info(f"🔍 Sending preflight OPTIONS for {method} {endpoint}")
            
            preflight_headers = {
                "Origin": self.frontend_origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type,authorization",
                "User-Agent": request_headers["User-Agent"],
                "Accept": "*/*",
                "Accept-Language": request_headers["Accept-Language"],
                "Accept-Encoding": request_headers["Accept-Encoding"],
                "Connection": "keep-alive",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Dest": "empty"
            }
            
            try:
                async with self.session.options(url, headers=preflight_headers) as response:
                    result["preflight_status"] = response.status
                    result["preflight_headers"] = dict(response.headers)
                    
                    # Check required CORS headers
                    allow_origin = response.headers.get("Access-Control-Allow-Origin")
                    allow_methods = response.headers.get("Access-Control-Allow-Methods", "")
                    allow_headers = response.headers.get("Access-Control-Allow-Headers", "")
                    allow_credentials = response.headers.get("Access-Control-Allow-Credentials")
                    
                    # Validate preflight response
                    preflight_valid = (
                        response.status in [200, 204] and
                        allow_origin in [self.frontend_origin, "*"] and
                        method.upper() in allow_methods.upper() and
                        allow_credentials == "true"
                    )
                    
                    result["preflight_success"] = preflight_valid
                    
                    if not preflight_valid:
                        errors = []
                        if response.status not in [200, 204]:
                            errors.append(f"Invalid preflight status: {response.status}")
                        if allow_origin not in [self.frontend_origin, "*"]:
                            errors.append(f"Origin not allowed: {allow_origin}")
                        if method.upper() not in allow_methods.upper():
                            errors.append(f"Method not allowed: {allow_methods}")
                        if allow_credentials != "true":
                            errors.append(f"Credentials not allowed: {allow_credentials}")
                        result["errors"].extend(errors)
                    
                    logger.info(f"   Preflight status: {response.status}")
                    logger.info(f"   Allow-Origin: {allow_origin}")
                    logger.info(f"   Allow-Methods: {allow_methods}")
                    logger.info(f"   Allow-Headers: {allow_headers}")
                    logger.info(f"   Allow-Credentials: {allow_credentials}")
                    
            except Exception as e:
                result["errors"].append(f"Preflight failed: {str(e)}")
                logger.error(f"   Preflight error: {e}")
                return result
        else:
            result["preflight_success"] = True  # No preflight needed
        
        # Step 2: Actual request (only if preflight succeeded or not needed)
        if result["preflight_success"]:
            logger.info(f"📡 Sending actual {method} request to {endpoint}")
            
            if method == "POST" and data:
                request_headers["Content-Type"] = "application/json"
            
            try:
                kwargs = {"headers": request_headers}
                if data and method in ["POST", "PUT", "PATCH"]:
                    kwargs["json"] = data
                
                async with self.session.request(method, url, **kwargs) as response:
                    result["request_status"] = response.status
                    result["request_headers"] = dict(response.headers)
                    
                    # Check CORS headers in response
                    response_origin = response.headers.get("Access-Control-Allow-Origin")
                    response_credentials = response.headers.get("Access-Control-Allow-Credentials")
                    
                    # Browser would check these headers
                    cors_valid = (
                        response_origin in [self.frontend_origin, "*"] and
                        response_credentials == "true"
                    )
                    
                    result["request_success"] = cors_valid
                    result["cors_headers"] = {
                        "Access-Control-Allow-Origin": response_origin,
                        "Access-Control-Allow-Credentials": response_credentials
                    }
                    
                    if not cors_valid:
                        errors = []
                        if response_origin not in [self.frontend_origin, "*"]:
                            errors.append(f"Response origin mismatch: {response_origin}")
                        if response_credentials != "true":
                            errors.append(f"Response credentials not allowed: {response_credentials}")
                        result["errors"].extend(errors)
                    
                    # Get response body
                    try:
                        result["response_body"] = await response.text()
                    except:
                        result["response_body"] = None
                    
                    logger.info(f"   Request status: {response.status}")
                    logger.info(f"   Response Origin: {response_origin}")
                    logger.info(f"   Response Credentials: {response_credentials}")
                    
            except Exception as e:
                result["errors"].append(f"Request failed: {str(e)}")
                logger.error(f"   Request error: {e}")
        
        return result
    
    async def test_login_flow(self) -> Dict:
        """Test the complete login flow that was failing."""
        logger.info("🔐 Testing complete login flow...")
        
        login_data = {
            "email": "test@example.com",
            "password": "testpassword123"
        }
        
        return await self.simulate_browser_request(
            "/api/v1/auth/login",
            "POST",
            data=login_data
        )
    
    async def test_credits_flow(self) -> Dict:
        """Test credits endpoint access."""
        logger.info("💰 Testing credits endpoint...")
        
        return await self.simulate_browser_request(
            "/api/v1/credits/balance",
            "GET"
        )
    
    async def test_generation_flow(self) -> Dict:
        """Test generation endpoint."""
        logger.info("🎨 Testing generation endpoint...")
        
        generation_data = {
            "prompt": "test image",
            "model": "flux-1.1-pro"
        }
        
        return await self.simulate_browser_request(
            "/api/v1/generations",
            "POST",
            data=generation_data
        )

async def main():
    """Run browser CORS simulation tests."""
    
    BACKEND_URL = "https://velro-backend-production.up.railway.app"
    FRONTEND_ORIGIN = "https://velro-frontend-production.up.railway.app"
    
    print("🌐 Browser CORS Simulation Test")
    print("=" * 50)
    print(f"Backend: {BACKEND_URL}")
    print(f"Frontend: {FRONTEND_ORIGIN}")
    print("=" * 50)
    
    async with BrowserCORSSimulator(BACKEND_URL, FRONTEND_ORIGIN) as simulator:
        
        # Test scenarios
        test_results = []
        
        # Test 1: Login flow
        login_result = await simulator.test_login_flow()
        test_results.append(("Login Flow", login_result))
        
        # Test 2: Credits flow
        credits_result = await simulator.test_credits_flow()
        test_results.append(("Credits Flow", credits_result))
        
        # Test 3: Generation flow
        generation_result = await simulator.test_generation_flow()
        test_results.append(("Generation Flow", generation_result))
        
        # Test 4: Simple GET request
        health_result = await simulator.simulate_browser_request("/health", "GET")
        test_results.append(("Health Check", health_result))
        
        # Print results
        print("\n" + "=" * 50)
        print("📊 SIMULATION RESULTS")
        print("=" * 50)
        
        total_tests = len(test_results)
        passed_tests = 0
        
        for test_name, result in test_results:
            success = result["request_success"] and (not result["preflight_needed"] or result["preflight_success"])
            status = "✅ PASS" if success else "❌ FAIL"
            
            print(f"\n{test_name}: {status}")
            print(f"  Endpoint: {result['endpoint']}")
            print(f"  Method: {result['method']}")
            
            if result["preflight_needed"]:
                preflight_status = "✅" if result["preflight_success"] else "❌"
                print(f"  Preflight: {preflight_status}")
            
            request_status = "✅" if result["request_success"] else "❌"
            print(f"  Request: {request_status}")
            
            if result["errors"]:
                print(f"  Errors:")
                for error in result["errors"]:
                    print(f"    - {error}")
            
            if success:
                passed_tests += 1
        
        # Summary
        print(f"\n" + "=" * 50)
        print(f"📈 OVERALL RESULTS")
        print("=" * 50)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if passed_tests == total_tests:
            print("\n🎉 ALL BROWSER SIMULATION TESTS PASSED!")
            print("✅ CORS configuration is working correctly")
            print("✅ Frontend will be able to communicate with backend")
        else:
            print(f"\n⚠️ {total_tests - passed_tests} tests failed")
            print("❌ CORS issues detected that will affect frontend")
        
        # Save detailed results
        report_file = f"cors_browser_simulation_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "backend_url": BACKEND_URL,
                "frontend_origin": FRONTEND_ORIGIN,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "test_results": {name: result for name, result in test_results}
            }, f, indent=2)
        
        print(f"\n📄 Detailed report saved to: {report_file}")
        
        return passed_tests == total_tests

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)