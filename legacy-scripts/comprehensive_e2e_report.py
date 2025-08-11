#!/usr/bin/env python3
"""
Comprehensive E2E Test Report for Velro Backend System
=====================================================

This script performs comprehensive testing of all Velro backend endpoints
and provides detailed analysis of what works and what doesn't.

Based on the analysis, authentication endpoints are experiencing timeouts,
but we can still test other aspects of the system.
"""

import requests
import json
import time
from datetime import datetime
from urllib.parse import urlparse
import sys

BASE_URL = "https://velro-003-backend-production.up.railway.app"

class VelroE2EReport:
    """Comprehensive E2E testing and reporting"""
    
    def __init__(self):
        self.results = {}
        self.issues = []
        self.recommendations = []
        
    def test_endpoint(self, name, method, url, headers=None, data=None, files=None, timeout=10):
        """Generic endpoint test method"""
        try:
            start_time = time.time()
            
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.upper() == "POST":
                if files:
                    response = requests.post(url, headers=headers, files=files, timeout=timeout)
                else:
                    response = requests.post(url, headers=headers, json=data, timeout=timeout)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}
            
            duration = time.time() - start_time
            
            result = {
                "success": response.status_code < 400,
                "status_code": response.status_code,
                "duration": duration,
                "response_size": len(response.content)
            }
            
            # Add response data for successful calls
            if result["success"]:
                try:
                    result["data"] = response.json()
                except:
                    result["data"] = response.text[:200] + "..." if len(response.text) > 200 else response.text
            else:
                result["error"] = response.text[:200] + "..." if len(response.text) > 200 else response.text
                
            return result
            
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": f"Request timed out after {timeout}s",
                "duration": timeout,
                "status_code": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time if 'start_time' in locals() else 0,
                "status_code": None
            }
    
    def run_comprehensive_tests(self):
        """Run all available tests"""
        print("🧪 Velro Backend Comprehensive E2E Analysis")
        print("=" * 60)
        
        # 1. Basic Health and Info Tests
        print("\n📋 1. BASIC HEALTH & INFORMATION TESTS")
        print("-" * 40)
        
        tests = {
            "root_endpoint": ("GET", f"{BASE_URL}/"),
            "health_endpoint": ("GET", f"{BASE_URL}/health"),
            "health_services": ("GET", f"{BASE_URL}/health/services"),
        }
        
        for test_name, (method, url) in tests.items():
            print(f"Testing {test_name}...")
            result = self.test_endpoint(test_name, method, url, timeout=15)
            self.results[test_name] = result
            
            if result["success"]:
                print(f"  ✅ {result['status_code']} ({result['duration']:.2f}s)")
                if isinstance(result.get("data"), dict):
                    # Show key info
                    data = result["data"]
                    if "status" in data:
                        print(f"     Status: {data['status']}")
                    if "version" in data:
                        print(f"     Version: {data['version']}")
                    if "environment" in data:
                        print(f"     Environment: {data['environment']}")
            else:
                print(f"  ❌ {result.get('status_code', 'TIMEOUT')} - {result.get('error', 'Unknown error')}")
        
        # 2. Authentication Tests (with timeout handling)
        print("\n🔐 2. AUTHENTICATION TESTS")
        print("-" * 40)
        
        auth_tests = {
            "auth_health": ("GET", f"{BASE_URL}/api/v1/auth/health"),
            "auth_security_info": ("GET", f"{BASE_URL}/api/v1/auth/security-info"),
        }
        
        for test_name, (method, url) in auth_tests.items():
            print(f"Testing {test_name}...")
            result = self.test_endpoint(test_name, method, url, timeout=10)
            self.results[test_name] = result
            
            if result["success"]:
                print(f"  ✅ {result['status_code']} ({result['duration']:.2f}s)")
            else:
                print(f"  ❌ {result.get('status_code', 'TIMEOUT')} - {result.get('error', 'Unknown error')}")
        
        # Test login with multiple approaches
        print("Testing authentication login (multiple credentials)...")
        credentials_list = [
            {"email": "demo@example.com", "password": "secure123!"},
            {"email": "demo@example.com", "password": "demo1234"},
            {"email": "demo@example.com", "password": "Demo1234!"},
        ]
        
        login_success = False
        jwt_token = None
        
        for i, creds in enumerate(credentials_list):
            print(f"  Trying credentials set {i+1}: {creds['email']} / {creds['password'][:4]}***")
            result = self.test_endpoint(
                f"login_attempt_{i+1}", 
                "POST", 
                f"{BASE_URL}/api/v1/auth/login", 
                data=creds,
                timeout=20  # Longer timeout for auth
            )
            
            if result["success"]:
                print(f"    ✅ Login successful!")
                login_success = True
                jwt_token = result["data"].get("access_token") if isinstance(result["data"], dict) else None
                self.results["successful_login"] = result
                break
            else:
                print(f"    ❌ {result.get('status_code', 'TIMEOUT')} - {result.get('error', 'Unknown error')[:50]}...")
                self.results[f"failed_login_{i+1}"] = result
        
        if not login_success:
            print("  ⚠️  All login attempts failed or timed out")
            self.issues.append("Authentication endpoint is not responding or credentials are incorrect")
        
        # 3. API Endpoint Tests (without authentication)
        print("\n🔌 3. PUBLIC API ENDPOINT TESTS")
        print("-" * 40)
        
        public_tests = {
            "models_endpoint_public": ("GET", f"{BASE_URL}/api/v1/models"),
            "debug_routes": ("GET", f"{BASE_URL}/debug/routes"),
            "debug_imports": ("GET", f"{BASE_URL}/debug/imports"),
        }
        
        for test_name, (method, url) in public_tests.items():
            print(f"Testing {test_name}...")
            result = self.test_endpoint(test_name, method, url, timeout=15)
            self.results[test_name] = result
            
            if result["success"]:
                print(f"  ✅ {result['status_code']} ({result['duration']:.2f}s)")
                if test_name == "models_endpoint_public" and isinstance(result.get("data"), list):
                    models = result["data"]
                    flux_models = [m for m in models if 'flux' in str(m).lower()]
                    print(f"     Found {len(models)} models, {len(flux_models)} Flux models")
            else:
                print(f"  ❌ {result.get('status_code', 'TIMEOUT')} - {result.get('error', 'Unknown error')[:50]}...")
        
        # 4. Authenticated Endpoint Tests (if we have a token)
        if jwt_token:
            print(f"\n🔑 4. AUTHENTICATED ENDPOINT TESTS (Token: {jwt_token[:20]}...)")
            print("-" * 40)
            
            auth_headers = {"Authorization": f"Bearer {jwt_token}"}
            
            auth_tests = {
                "user_profile": ("GET", f"{BASE_URL}/api/v1/auth/me"),
                "user_projects": ("GET", f"{BASE_URL}/api/v1/projects"),
                "user_generations": ("GET", f"{BASE_URL}/api/v1/generations"),
                "models_authenticated": ("GET", f"{BASE_URL}/api/v1/models"),
            }
            
            for test_name, (method, url) in auth_tests.items():
                print(f"Testing {test_name}...")
                result = self.test_endpoint(test_name, method, url, headers=auth_headers, timeout=15)
                self.results[test_name] = result
                
                if result["success"]:
                    print(f"  ✅ {result['status_code']} ({result['duration']:.2f}s)")
                    if isinstance(result.get("data"), dict):
                        data = result["data"]
                        if "email" in data:
                            print(f"     User: {data['email']}")
                        if "credits_balance" in data:
                            print(f"     Credits: {data['credits_balance']}")
                    elif isinstance(result.get("data"), list):
                        print(f"     Items: {len(result['data'])}")
                else:
                    print(f"  ❌ {result.get('status_code', 'TIMEOUT')} - {result.get('error', 'Unknown error')[:50]}...")
            
            # Test image generation
            print("Testing image generation...")
            gen_files = {
                'model_id': (None, 'fal-ai/flux/dev'),
                'prompt': (None, 'beautiful sunset over mountains'),
                'parameters': (None, '{"width": 512, "height": 512}')
            }
            
            result = self.test_endpoint(
                "image_generation",
                "POST",
                f"{BASE_URL}/api/v1/generations",
                headers=auth_headers,
                files=gen_files,
                timeout=60
            )
            self.results["image_generation"] = result
            
            if result["success"]:
                print(f"  ✅ Generation created! {result['status_code']} ({result['duration']:.2f}s)")
                if isinstance(result.get("data"), dict):
                    gen_data = result["data"]
                    gen_id = gen_data.get("id")
                    status = gen_data.get("status")
                    print(f"     ID: {gen_id}, Status: {status}")
                    
                    # Test generation status check
                    if gen_id:
                        print(f"Testing generation status for {gen_id}...")
                        status_result = self.test_endpoint(
                            "generation_status_check",
                            "GET",
                            f"{BASE_URL}/api/v1/generations/{gen_id}",
                            headers=auth_headers,
                            timeout=15
                        )
                        self.results["generation_status_check"] = status_result
                        
                        if status_result["success"]:
                            status_data = status_result.get("data", {})
                            current_status = status_data.get("status")
                            image_url = status_data.get("image_url")
                            print(f"    ✅ Status check: {current_status}")
                            if image_url:
                                print(f"       Image URL: {image_url}")
                                
                                # Test image URL accessibility
                                print("Testing image URL accessibility...")
                                try:
                                    img_response = requests.get(image_url, timeout=10)
                                    if img_response.status_code == 200:
                                        print(f"    ✅ Image accessible ({img_response.headers.get('content-type')})")
                                        self.results["image_url_accessibility"] = {
                                            "success": True,
                                            "status_code": img_response.status_code,
                                            "content_type": img_response.headers.get('content-type'),
                                            "content_length": img_response.headers.get('content-length')
                                        }
                                    else:
                                        print(f"    ❌ Image not accessible: {img_response.status_code}")
                                        self.results["image_url_accessibility"] = {
                                            "success": False,
                                            "status_code": img_response.status_code
                                        }
                                except Exception as e:
                                    print(f"    ❌ Image URL error: {e}")
                                    self.results["image_url_accessibility"] = {"success": False, "error": str(e)}
                        else:
                            print(f"    ❌ Status check failed: {status_result.get('error', 'Unknown error')}")
            else:
                print(f"  ❌ Generation failed: {result.get('status_code', 'TIMEOUT')} - {result.get('error', 'Unknown error')[:50]}...")
        else:
            print("\n🔑 4. AUTHENTICATED ENDPOINT TESTS")
            print("-" * 40)
            print("  ⚠️  Skipped - No authentication token available")
            self.issues.append("Cannot test authenticated endpoints due to authentication failure")
        
        # 5. System Analysis
        self.analyze_results()
        
        # 6. Generate Report
        return self.generate_report()
    
    def analyze_results(self):
        """Analyze test results and generate insights"""
        print("\n🔍 5. SYSTEM ANALYSIS")
        print("-" * 40)
        
        # Count successes and failures
        total_tests = len(self.results)
        successful_tests = sum(1 for r in self.results.values() if r.get("success", False))
        failed_tests = total_tests - successful_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Successful: {successful_tests} ({successful_tests/total_tests*100:.1f}%)")
        print(f"Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        
        # Check for specific issues
        auth_timeouts = sum(1 for k, r in self.results.items() if 'login' in k or 'auth' in k and 'timed out' in str(r.get('error', '')))
        if auth_timeouts > 0:
            self.issues.append(f"Authentication endpoints timing out ({auth_timeouts} timeouts detected)")
            self.recommendations.append("Check authentication service performance and database connections")
        
        # Check response times
        slow_responses = [(k, r) for k, r in self.results.items() if r.get('duration', 0) > 5 and r.get('success')]
        if slow_responses:
            self.issues.append(f"Slow response times detected on {len(slow_responses)} endpoints")
            for endpoint, result in slow_responses:
                print(f"  ⚠️  Slow: {endpoint} ({result['duration']:.2f}s)")
            self.recommendations.append("Optimize slow endpoints for better user experience")
        
        # Check for working features
        working_features = []
        if self.results.get("health_endpoint", {}).get("success"):
            working_features.append("Health monitoring")
        if self.results.get("models_endpoint_public", {}).get("success"):
            working_features.append("AI models API")
        if self.results.get("successful_login", {}).get("success"):
            working_features.append("Authentication")
        if self.results.get("user_profile", {}).get("success"):
            working_features.append("User profiles")
        if self.results.get("image_generation", {}).get("success"):
            working_features.append("Image generation")
        if self.results.get("image_url_accessibility", {}).get("success"):
            working_features.append("Supabase storage")
        
        print(f"\n✅ Working Features ({len(working_features)}):")
        for feature in working_features:
            print(f"  - {feature}")
        
        if self.issues:
            print(f"\n⚠️  Issues Identified ({len(self.issues)}):")
            for issue in self.issues:
                print(f"  - {issue}")
        
        if self.recommendations:
            print(f"\n💡 Recommendations ({len(self.recommendations)}):")
            for rec in self.recommendations:
                print(f"  - {rec}")
    
    def generate_report(self):
        """Generate comprehensive report"""
        timestamp = datetime.now()
        
        # Calculate summary stats
        total_tests = len(self.results)
        successful_tests = sum(1 for r in self.results.values() if r.get("success", False))
        failed_tests = total_tests - successful_tests
        
        # Categorize results
        categories = {
            "health": [k for k in self.results.keys() if "health" in k],
            "authentication": [k for k in self.results.keys() if "auth" in k or "login" in k],
            "api_endpoints": [k for k in self.results.keys() if "models" in k or "projects" in k or "generations" in k],
            "image_generation": [k for k in self.results.keys() if "generation" in k or "image" in k],
            "other": [k for k in self.results.keys() if not any(cat in k for cat in ["health", "auth", "login", "models", "projects", "generations", "image"])]
        }
        
        report = {
            "timestamp": timestamp.isoformat(),
            "test_suite": "velro_backend_comprehensive_e2e",
            "backend_url": BASE_URL,
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "success_rate": (successful_tests / total_tests * 100) if total_tests > 0 else 0,
                "total_duration": sum(r.get("duration", 0) for r in self.results.values())
            },
            "categories": {
                cat: {
                    "tests": tests,
                    "success_count": sum(1 for t in tests if self.results.get(t, {}).get("success", False)),
                    "total_count": len(tests)
                }
                for cat, tests in categories.items() if tests
            },
            "issues": self.issues,
            "recommendations": self.recommendations,
            "detailed_results": self.results
        }
        
        return report

def main():
    """Main execution"""
    tester = VelroE2EReport()
    report = tester.run_comprehensive_tests()
    
    # Save detailed report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"comprehensive_e2e_report_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 DETAILED REPORT SAVED: {filename}")
    
    # Print final summary
    print("\n" + "=" * 60)
    print("📊 FINAL SUMMARY")
    print("=" * 60)
    
    summary = report["summary"]
    print(f"🎯 Backend URL: {BASE_URL}")
    print(f"⏱️  Total Duration: {summary['total_duration']:.2f} seconds")
    print(f"📈 Success Rate: {summary['success_rate']:.1f}%")
    print(f"✅ Passed: {summary['successful_tests']}/{summary['total_tests']}")
    print(f"❌ Failed: {summary['failed_tests']}/{summary['total_tests']}")
    
    print(f"\n📋 CATEGORY BREAKDOWN:")
    for category, data in report.get("categories", {}).items():
        success_rate = (data["success_count"] / data["total_count"] * 100) if data["total_count"] > 0 else 0
        print(f"  {category.title()}: {data['success_count']}/{data['total_count']} ({success_rate:.1f}%)")
    
    if report["issues"]:
        print(f"\n⚠️  KEY ISSUES:")
        for issue in report["issues"][:3]:  # Show top 3 issues
            print(f"  - {issue}")
    
    if report["recommendations"]:
        print(f"\n💡 TOP RECOMMENDATIONS:")
        for rec in report["recommendations"][:3]:  # Show top 3 recommendations
            print(f"  - {rec}")
    
    print(f"\n🏁 E2E Analysis Complete - Detailed results in {filename}")
    
    return 0 if summary["failed_tests"] == 0 else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)