#!/usr/bin/env python3
"""
Railway Deployment Validator
Validates FastAPI deployment configuration for Railway platform.
"""
import asyncio
import aiohttp
import json
import os
import sys
import time
from typing import Dict, List, Any
from urllib.parse import urljoin

class RailwayDeploymentValidator:
    """Validates Railway deployment configuration and health."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv("RAILWAY_SERVICE_VELRO_BACKEND_URL", "http://localhost:8000")
        self.validation_results = []
        
    async def validate_health_endpoint(self) -> Dict[str, Any]:
        """Validate health endpoint responds correctly."""
        try:
            async with aiohttp.ClientSession() as session:
                # Test GET request
                async with session.get(f"{self.base_url}/health", timeout=10) as response:
                    get_status = response.status
                    get_data = await response.json()
                
                # Test HEAD request (Railway uses this)
                async with session.head(f"{self.base_url}/health", timeout=10) as response:
                    head_status = response.status
                
                result = {
                    "endpoint": "/health",
                    "status": "✅ PASS" if get_status == 200 and head_status == 200 else "❌ FAIL",
                    "get_status": get_status,
                    "head_status": head_status,
                    "response_data": get_data,
                    "issue": None if get_status == 200 and head_status == 200 else "Health endpoint not responding correctly"
                }
                
        except Exception as e:
            result = {
                "endpoint": "/health",
                "status": "❌ FAIL",
                "error": str(e),
                "issue": "Health endpoint unreachable"
            }
        
        self.validation_results.append(result)
        return result
    
    async def validate_cors_configuration(self) -> Dict[str, Any]:
        """Validate CORS configuration."""
        try:
            async with aiohttp.ClientSession() as session:
                # Test preflight OPTIONS request
                headers = {
                    "Origin": "https://velro-frontend-production.up.railway.app",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Authorization, Content-Type"
                }
                
                async with session.options(f"{self.base_url}/api/v1/auth/login", headers=headers, timeout=10) as response:
                    status = response.status
                    cors_headers = {
                        "access-control-allow-origin": response.headers.get("Access-Control-Allow-Origin"),
                        "access-control-allow-methods": response.headers.get("Access-Control-Allow-Methods"),
                        "access-control-allow-headers": response.headers.get("Access-Control-Allow-Headers"),
                        "access-control-allow-credentials": response.headers.get("Access-Control-Allow-Credentials")
                    }
                
                result = {
                    "endpoint": "CORS Configuration",
                    "status": "✅ PASS" if status == 200 else "❌ FAIL",
                    "preflight_status": status,
                    "cors_headers": cors_headers,
                    "issue": None if status == 200 else "CORS preflight failing"
                }
                
        except Exception as e:
            result = {
                "endpoint": "CORS Configuration", 
                "status": "❌ FAIL",
                "error": str(e),
                "issue": "CORS configuration test failed"
            }
        
        self.validation_results.append(result)
        return result
    
    async def validate_api_endpoints(self) -> Dict[str, Any]:
        """Validate core API endpoints."""
        endpoints_to_test = [
            ("/", "GET", "Root endpoint"),
            ("/api/v1/generations/models/supported", "GET", "Public models endpoint"),
            ("/security-status", "GET", "Security status endpoint")
        ]
        
        results = []
        
        async with aiohttp.ClientSession() as session:
            for path, method, description in endpoints_to_test:
                try:
                    async with session.request(method, f"{self.base_url}{path}", timeout=10) as response:
                        status = response.status
                        # Try to parse JSON, but don't fail if it's not JSON
                        try:
                            data = await response.json()
                        except:
                            data = await response.text()
                        
                        result = {
                            "endpoint": path,
                            "method": method,
                            "description": description,
                            "status": "✅ PASS" if 200 <= status < 400 else "❌ FAIL",
                            "http_status": status,
                            "response_sample": str(data)[:200] + "..." if len(str(data)) > 200 else str(data),
                            "issue": None if 200 <= status < 400 else f"Endpoint returning {status}"
                        }
                        
                except Exception as e:
                    result = {
                        "endpoint": path,
                        "method": method,
                        "description": description,
                        "status": "❌ FAIL",
                        "error": str(e),
                        "issue": "Endpoint unreachable"
                    }
                
                results.append(result)
        
        overall_result = {
            "test": "API Endpoints",
            "status": "✅ PASS" if all(r["status"] == "✅ PASS" for r in results) else "❌ FAIL",
            "individual_results": results
        }
        
        self.validation_results.append(overall_result)
        return overall_result
    
    async def validate_authentication_flow(self) -> Dict[str, Any]:
        """Test authentication middleware."""
        try:
            async with aiohttp.ClientSession() as session:
                # Test protected endpoint without auth (should get 401)
                async with session.get(f"{self.base_url}/api/v1/projects", timeout=10) as response:
                    unauth_status = response.status
                
                # Test with mock token (development)
                headers = {"Authorization": "Bearer mock_token_test"}
                async with session.get(f"{self.base_url}/api/v1/projects", headers=headers, timeout=10) as response:
                    mock_auth_status = response.status
                
                result = {
                    "test": "Authentication Flow",
                    "status": "✅ PASS" if unauth_status == 401 else "❌ FAIL",
                    "unauthenticated_status": unauth_status,
                    "mock_token_status": mock_auth_status,
                    "issue": None if unauth_status == 401 else "Authentication middleware not working correctly"
                }
                
        except Exception as e:
            result = {
                "test": "Authentication Flow",
                "status": "❌ FAIL",
                "error": str(e),
                "issue": "Authentication test failed"
            }
        
        self.validation_results.append(result)
        return result
    
    async def validate_deployment_configuration(self) -> Dict[str, Any]:
        """Validate Railway deployment configuration."""
        config_checks = []
        
        # Check environment variables
        required_env_vars = [
            "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", 
            "FAL_KEY", "PORT"
        ]
        
        for var in required_env_vars:
            is_set = bool(os.getenv(var))
            config_checks.append({
                "check": f"Environment Variable: {var}",
                "status": "✅ PASS" if is_set else "❌ FAIL",
                "value": "SET" if is_set else "MISSING",
                "issue": None if is_set else f"Required environment variable {var} is missing"
            })
        
        # Check Railway configuration files
        config_files = [
            "railway.toml",
            "nixpacks.toml", 
            "requirements.txt"
        ]
        
        for file in config_files:
            file_path = os.path.join(os.path.dirname(__file__), file)
            exists = os.path.exists(file_path)
            config_checks.append({
                "check": f"Configuration File: {file}",
                "status": "✅ PASS" if exists else "❌ FAIL",
                "exists": exists,
                "issue": None if exists else f"Configuration file {file} is missing"
            })
        
        result = {
            "test": "Deployment Configuration",
            "status": "✅ PASS" if all(c["status"] == "✅ PASS" for c in config_checks) else "❌ FAIL",
            "checks": config_checks
        }
        
        self.validation_results.append(result)
        return result
    
    async def run_validation(self) -> Dict[str, Any]:
        """Run all validation tests."""
        print("🚀 Starting Railway Deployment Validation...")
        print(f"   Target URL: {self.base_url}")
        print("=" * 60)
        
        # Run all validation tests
        tests = [
            ("Health Endpoint", self.validate_health_endpoint),
            ("CORS Configuration", self.validate_cors_configuration), 
            ("API Endpoints", self.validate_api_endpoints),
            ("Authentication Flow", self.validate_authentication_flow),
            ("Deployment Configuration", self.validate_deployment_configuration)
        ]
        
        for test_name, test_func in tests:
            print(f"\n🔍 Testing: {test_name}")
            try:
                result = await test_func()
                print(f"   Result: {result['status']}")
                if result.get('issue'):
                    print(f"   Issue: {result['issue']}")
            except Exception as e:
                print(f"   Result: ❌ FAIL - {e}")
        
        # Generate summary
        passed_tests = sum(1 for r in self.validation_results if r["status"] == "✅ PASS")
        total_tests = len(self.validation_results)
        
        summary = {
            "validation_timestamp": time.time(),
            "target_url": self.base_url,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "overall_status": "✅ DEPLOYMENT READY" if passed_tests == total_tests else "❌ ISSUES FOUND",
            "detailed_results": self.validation_results
        }
        
        print("\n" + "=" * 60)
        print(f"📊 VALIDATION SUMMARY")
        print(f"   Overall Status: {summary['overall_status']}")
        print(f"   Tests Passed: {passed_tests}/{total_tests}")
        
        if passed_tests != total_tests:
            print(f"\n⚠️  Issues Found:")
            for result in self.validation_results:
                if result["status"] == "❌ FAIL" and result.get("issue"):
                    print(f"   • {result.get('test', result.get('endpoint', 'Unknown'))}: {result['issue']}")
        
        print("=" * 60)
        
        return summary

async def main():
    """Main validation function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate Railway deployment")
    parser.add_argument("--url", help="Base URL to test (default: from RAILWAY_SERVICE_VELRO_BACKEND_URL or localhost)")
    parser.add_argument("--output", help="Output file for detailed results (JSON)")
    args = parser.parse_args()
    
    validator = RailwayDeploymentValidator(args.url)
    results = await validator.run_validation()
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📄 Detailed results saved to: {args.output}")
    
    # Exit with appropriate code
    sys.exit(0 if results["overall_status"] == "✅ DEPLOYMENT READY" else 1)

if __name__ == "__main__":
    asyncio.run(main())