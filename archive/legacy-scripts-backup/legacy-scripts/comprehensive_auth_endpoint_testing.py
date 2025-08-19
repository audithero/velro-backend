#!/usr/bin/env python3
"""
Comprehensive Auth Endpoint Testing Suite
Tests all possible auth endpoint combinations to identify exact path resolution issues.
"""

import requests
import json
import time
from typing import Dict, List, Any
from datetime import datetime

# Base URL from production validation
BASE_URL = "https://velro-backend-production.up.railway.app"

class AuthEndpointTester:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.results = []
        self.session = requests.Session()
        # Common headers for testing
        self.headers_json = {"Content-Type": "application/json"}
        self.headers_form = {"Content-Type": "application/x-www-form-urlencoded"}
        
    def test_endpoint_combination(self, path: str, method: str = "POST", 
                                headers: Dict = None, data: Any = None) -> Dict:
        """Test a specific endpoint combination and return detailed results."""
        full_url = f"{self.base_url}{path}"
        headers = headers or self.headers_json
        
        try:
            start_time = time.time()
            
            if method == "GET":
                response = self.session.get(full_url, headers=headers, timeout=10)
            elif method == "POST":
                if headers.get("Content-Type") == "application/json":
                    response = self.session.post(full_url, headers=headers, json=data, timeout=10)
                else:
                    response = self.session.post(full_url, headers=headers, data=data, timeout=10)
            elif method == "OPTIONS":
                response = self.session.options(full_url, headers=headers, timeout=10)
            else:
                response = self.session.request(method, full_url, headers=headers, timeout=10)
                
            duration = time.time() - start_time
            
            # Try to parse response as JSON
            try:
                response_json = response.json()
            except:
                response_json = None
                
            result = {
                "timestamp": datetime.now().isoformat(),
                "url": full_url,
                "path": path,
                "method": method,
                "status_code": response.status_code,
                "headers_sent": dict(headers),
                "response_headers": dict(response.headers),
                "response_time": round(duration * 1000, 2),  # ms
                "response_json": response_json,
                "response_text": response.text[:500] if response.text else None,
                "success": 200 <= response.status_code < 300
            }
            
        except requests.exceptions.RequestException as e:
            result = {
                "timestamp": datetime.now().isoformat(),
                "url": full_url,
                "path": path,
                "method": method,
                "error": str(e),
                "success": False
            }
            
        self.results.append(result)
        return result
    
    def test_all_path_combinations(self):
        """Test all possible auth endpoint path combinations."""
        print("🔍 Testing Path Combinations...")
        
        # Path combinations to test
        paths = [
            # Expected paths
            "/api/v1/auth/login",
            "/api/v1/auth/register", 
            "/api/v1/auth/me",
            "/api/v1/auth/logout",
            "/api/v1/auth/refresh",
            
            # Double prefix paths (potential issue)
            "/api/v1/auth/auth/login",
            "/api/v1/auth/auth/register",
            "/api/v1/auth/auth/me",
            
            # Router-only paths
            "/auth/login",
            "/auth/register",
            "/auth/me",
            "/auth/logout",
            
            # Prefix-only paths
            "/api/v1/login",
            "/api/v1/register",
            "/api/v1/me",
            
            # Root paths
            "/login",
            "/register",
            "/me",
            
            # Other potential paths
            "/api/auth/login",
            "/v1/auth/login",
            "/api/v1/authentication/login",
        ]
        
        # Test data for login
        login_data = {
            "email": "test@example.com",
            "password": "testpassword123"
        }
        
        for path in paths:
            print(f"  Testing: {path}")
            
            # Test with POST and login data
            result = self.test_endpoint_combination(
                path, "POST", self.headers_json, login_data
            )
            print(f"    POST {result['status_code']}: {result.get('response_json', {}).get('message', 'No message')}")
            
            # Test with GET
            result = self.test_endpoint_combination(path, "GET")
            print(f"    GET {result['status_code']}: {result.get('response_json', {}).get('message', 'No message')}")
            
            # Test with OPTIONS (CORS preflight)
            result = self.test_endpoint_combination(path, "OPTIONS")
            print(f"    OPTIONS {result['status_code']}")
            
            time.sleep(0.1)  # Rate limiting
    
    def test_method_variations(self):
        """Test different HTTP methods on main auth endpoints."""
        print("\n🔧 Testing Method Variations...")
        
        endpoints = ["/api/v1/auth/login", "/auth/login", "/login"]
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
        
        for endpoint in endpoints:
            print(f"  Testing endpoint: {endpoint}")
            for method in methods:
                result = self.test_endpoint_combination(endpoint, method)
                print(f"    {method}: {result['status_code']}")
                time.sleep(0.05)
    
    def test_header_variations(self):
        """Test different Content-Type headers."""
        print("\n📋 Testing Header Variations...")
        
        login_data = {"email": "test@example.com", "password": "testpassword123"}
        form_data = "email=test@example.com&password=testpassword123"
        
        headers_to_test = [
            {"Content-Type": "application/json"},
            {"Content-Type": "application/x-www-form-urlencoded"},
            {"Content-Type": "multipart/form-data"},
            {"Content-Type": "text/plain"},
            {},  # No Content-Type
        ]
        
        endpoints = ["/api/v1/auth/login", "/auth/login"]
        
        for endpoint in endpoints:
            print(f"  Testing endpoint: {endpoint}")
            for headers in headers_to_test:
                content_type = headers.get("Content-Type", "None")
                data = form_data if "form-urlencoded" in content_type else login_data
                result = self.test_endpoint_combination(endpoint, "POST", headers, data)
                print(f"    {content_type}: {result['status_code']}")
                time.sleep(0.05)
    
    def test_cors_behavior(self):
        """Test CORS preflight and actual requests."""
        print("\n🌐 Testing CORS Behavior...")
        
        cors_headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,Authorization"
        }
        
        endpoints = ["/api/v1/auth/login", "/auth/login", "/login"]
        
        for endpoint in endpoints:
            print(f"  Testing CORS for: {endpoint}")
            
            # CORS preflight
            result = self.test_endpoint_combination(endpoint, "OPTIONS", cors_headers)
            cors_allowed = "access-control-allow-origin" in [h.lower() for h in result.get("response_headers", {})]
            print(f"    CORS Preflight: {result['status_code']} (CORS allowed: {cors_allowed})")
            
            # Actual request with Origin
            request_headers = {**self.headers_json, "Origin": "http://localhost:3000"}
            result = self.test_endpoint_combination(
                endpoint, "POST", request_headers, 
                {"email": "test@example.com", "password": "test"}
            )
            cors_response = "access-control-allow-origin" in [h.lower() for h in result.get("response_headers", {})]
            print(f"    CORS Request: {result['status_code']} (CORS headers: {cors_response})")
            
            time.sleep(0.1)
    
    def analyze_results(self) -> Dict:
        """Analyze test results and identify patterns."""
        print("\n📊 Analyzing Results...\n")
        
        analysis = {
            "total_tests": len(self.results),
            "successful_requests": len([r for r in self.results if r.get("success", False)]),
            "status_code_distribution": {},
            "working_endpoints": [],
            "non_working_endpoints": [],
            "error_patterns": {},
            "cors_enabled_endpoints": [],
            "response_time_stats": {}
        }
        
        # Status code distribution
        for result in self.results:
            status = result.get("status_code", "error")
            analysis["status_code_distribution"][str(status)] = analysis["status_code_distribution"].get(str(status), 0) + 1
        
        # Working vs non-working endpoints
        for result in self.results:
            endpoint_key = f"{result.get('method', 'UNKNOWN')} {result.get('path', 'UNKNOWN')}"
            if result.get("success", False):
                analysis["working_endpoints"].append({
                    "endpoint": endpoint_key,
                    "status_code": result.get("status_code"),
                    "response_time": result.get("response_time")
                })
            else:
                analysis["non_working_endpoints"].append({
                    "endpoint": endpoint_key,
                    "status_code": result.get("status_code"),
                    "error": result.get("error"),
                    "response_message": result.get("response_json", {}).get("message") if result.get("response_json") else None
                })
        
        # Error patterns
        for result in self.results:
            if not result.get("success", False):
                status = str(result.get("status_code", "error"))
                if status not in analysis["error_patterns"]:
                    analysis["error_patterns"][status] = []
                analysis["error_patterns"][status].append(result.get("path", "unknown"))
        
        # CORS analysis
        for result in self.results:
            headers = result.get("response_headers", {})
            if any("access-control" in h.lower() for h in headers.keys()):
                analysis["cors_enabled_endpoints"].append(result.get("path"))
        
        # Response time stats
        response_times = [r.get("response_time", 0) for r in self.results if r.get("response_time")]
        if response_times:
            analysis["response_time_stats"] = {
                "min": min(response_times),
                "max": max(response_times),
                "avg": sum(response_times) / len(response_times)
            }
        
        return analysis
    
    def print_summary(self, analysis: Dict):
        """Print a comprehensive summary of test results."""
        print("=" * 80)
        print("🔍 COMPREHENSIVE AUTH ENDPOINT TESTING RESULTS")
        print("=" * 80)
        
        print(f"\n📈 OVERVIEW:")
        print(f"  Total Tests: {analysis['total_tests']}")
        print(f"  Successful: {analysis['successful_requests']}")
        print(f"  Failed: {analysis['total_tests'] - analysis['successful_requests']}")
        
        print(f"\n📊 STATUS CODE DISTRIBUTION:")
        for status, count in sorted(analysis['status_code_distribution'].items()):
            print(f"  {status}: {count}")
        
        print(f"\n✅ WORKING ENDPOINTS ({len(analysis['working_endpoints'])}):")
        for endpoint in analysis['working_endpoints'][:10]:  # Show first 10
            print(f"  {endpoint['endpoint']} -> {endpoint['status_code']} ({endpoint.get('response_time', 0):.1f}ms)")
        
        print(f"\n❌ NON-WORKING ENDPOINTS ({len(analysis['non_working_endpoints'])}):")
        for endpoint in analysis['non_working_endpoints'][:10]:  # Show first 10
            msg = endpoint.get('response_message', endpoint.get('error', 'No message'))
            print(f"  {endpoint['endpoint']} -> {endpoint.get('status_code', 'ERROR')}: {msg}")
        
        print(f"\n🔍 ERROR PATTERNS:")
        for status, paths in analysis['error_patterns'].items():
            print(f"  {status}: {len(paths)} occurrences")
            unique_paths = list(set(paths))[:5]  # Show unique paths
            for path in unique_paths:
                print(f"    - {path}")
        
        print(f"\n🌐 CORS ANALYSIS:")
        unique_cors = list(set(analysis['cors_enabled_endpoints']))
        print(f"  CORS Enabled Endpoints: {len(unique_cors)}")
        for endpoint in unique_cors[:5]:
            print(f"    - {endpoint}")
        
        if analysis['response_time_stats']:
            stats = analysis['response_time_stats']
            print(f"\n⏱️ RESPONSE TIME STATS:")
            print(f"  Min: {stats['min']:.1f}ms")
            print(f"  Max: {stats['max']:.1f}ms") 
            print(f"  Avg: {stats['avg']:.1f}ms")
    
    def save_results(self, filename: str):
        """Save all results to JSON file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{filename}_{timestamp}.json"
        
        output_data = {
            "test_metadata": {
                "timestamp": datetime.now().isoformat(),
                "base_url": self.base_url,
                "total_tests": len(self.results),
                "agent": "auth-tester",
                "swarm_id": "swarm_1754270436962_u0i9n97xs"
            },
            "test_results": self.results,
            "analysis": self.analyze_results()
        }
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
            
        print(f"\n💾 Results saved to: {output_file}")
        return output_file

def main():
    """Main testing function."""
    print("🚀 Starting Comprehensive Auth Endpoint Testing")
    print(f"🎯 Target: {BASE_URL}")
    print("=" * 80)
    
    tester = AuthEndpointTester(BASE_URL)
    
    # Run all test suites
    tester.test_all_path_combinations()
    tester.test_method_variations()
    tester.test_header_variations()
    tester.test_cors_behavior()
    
    # Analyze and summarize
    analysis = tester.analyze_results()
    tester.print_summary(analysis)
    
    # Save results
    output_file = tester.save_results("comprehensive_auth_endpoint_test_results")
    
    return output_file, analysis

if __name__ == "__main__":
    main()