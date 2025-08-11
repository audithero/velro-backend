#!/usr/bin/env python3
"""
Comprehensive Production Validation Suite for Velro AI Platform
Tests all claimed production endpoints for actual functionality.
"""
import asyncio
import aiohttp
import json
import time
import sys
from typing import Dict, Any, List
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductionValidator:
    def __init__(self):
        self.backend_url = "https://velro-003-backend-production.up.railway.app"
        self.frontend_url = "https://velro-frontend-production.up.railway.app"
        self.kong_url = "https://velro-kong-gateway-production.up.railway.app"
        
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unknown",
            "backend_tests": {},
            "frontend_tests": {},
            "kong_tests": {},
            "integration_tests": {},
            "critical_issues": [],
            "recommendations": []
        }
        
        # Test credentials for authentication
        self.test_credentials = {
            "email": "demo@example.com",
            "password": "demo123"
        }
        self.auth_token = None
        
    async def run_all_validations(self):
        """Run comprehensive production validation suite."""
        logger.info("🚀 Starting comprehensive production validation...")
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            self.session = session
            
            # 1. Backend Validation
            await self.validate_backend_health()
            await self.validate_backend_auth()
            await self.validate_backend_apis()
            await self.validate_team_collaboration()
            
            # 2. Kong Gateway Validation
            await self.validate_kong_gateway()
            
            # 3. Frontend Validation
            await self.validate_frontend()
            
            # 4. Integration Tests
            await self.validate_end_to_end_flow()
            
        # Generate final report
        self.generate_final_report()
        
    async def validate_backend_health(self):
        """Test backend health endpoints."""
        logger.info("🔍 Validating backend health endpoints...")
        
        # Test root endpoint
        try:
            async with self.session.get(f"{self.backend_url}/") as response:
                if response.status == 200:
                    data = await response.json()
                    self.results["backend_tests"]["root_endpoint"] = {
                        "status": "pass",
                        "response_code": response.status,
                        "has_api_info": "api_endpoints" in data,
                        "version": data.get("version", "unknown")
                    }
                else:
                    self.results["backend_tests"]["root_endpoint"] = {
                        "status": "fail",
                        "response_code": response.status,
                        "error": f"Unexpected status code: {response.status}"
                    }
        except Exception as e:
            self.results["backend_tests"]["root_endpoint"] = {
                "status": "fail",
                "error": str(e)
            }
            
        # Test health endpoint
        try:
            async with self.session.get(f"{self.backend_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    self.results["backend_tests"]["health_endpoint"] = {
                        "status": "pass",
                        "response_code": response.status,
                        "health_status": data.get("status"),
                        "environment": data.get("environment")
                    }
                else:
                    self.results["backend_tests"]["health_endpoint"] = {
                        "status": "fail",
                        "response_code": response.status
                    }
        except Exception as e:
            self.results["backend_tests"]["health_endpoint"] = {
                "status": "fail",
                "error": str(e)
            }
            
        # Test detailed health services endpoint
        try:
            async with self.session.get(f"{self.backend_url}/health/services") as response:
                if response.status == 200:
                    data = await response.json()
                    self.results["backend_tests"]["health_services"] = {
                        "status": "pass",
                        "response_code": response.status,
                        "overall_status": data.get("overall_status"),
                        "services": data.get("services", {})
                    }
                else:
                    self.results["backend_tests"]["health_services"] = {
                        "status": "fail",
                        "response_code": response.status
                    }
        except Exception as e:
            self.results["backend_tests"]["health_services"] = {
                "status": "fail",
                "error": str(e)
            }
    
    async def validate_backend_auth(self):
        """Test authentication endpoints."""
        logger.info("🔐 Validating authentication system...")
        
        # Test login endpoint
        try:
            login_data = {
                "email": self.test_credentials["email"],
                "password": self.test_credentials["password"]
            }
            
            async with self.session.post(
                f"{self.backend_url}/api/v1/auth/login",
                json=login_data
            ) as response:
                if response.status in [200, 201]:
                    data = await response.json()
                    if "access_token" in data:
                        self.auth_token = data["access_token"]
                        self.results["backend_tests"]["auth_login"] = {
                            "status": "pass",
                            "response_code": response.status,
                            "has_token": True,
                            "token_type": data.get("token_type", "bearer")
                        }
                    else:
                        self.results["backend_tests"]["auth_login"] = {
                            "status": "fail",
                            "response_code": response.status,
                            "error": "No access_token in response"
                        }
                else:
                    self.results["backend_tests"]["auth_login"] = {
                        "status": "fail",
                        "response_code": response.status,
                        "error": f"Login failed with status: {response.status}"
                    }
        except Exception as e:
            self.results["backend_tests"]["auth_login"] = {
                "status": "fail",
                "error": str(e)
            }
            
        # Test /me endpoint with token
        if self.auth_token:
            try:
                headers = {"Authorization": f"Bearer {self.auth_token}"}
                async with self.session.get(
                    f"{self.backend_url}/api/v1/auth/me",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.results["backend_tests"]["auth_me"] = {
                            "status": "pass",
                            "response_code": response.status,
                            "user_id": data.get("id"),
                            "user_email": data.get("email")
                        }
                    else:
                        self.results["backend_tests"]["auth_me"] = {
                            "status": "fail",
                            "response_code": response.status
                        }
            except Exception as e:
                self.results["backend_tests"]["auth_me"] = {
                    "status": "fail",
                    "error": str(e)
                }
        else:
            self.results["backend_tests"]["auth_me"] = {
                "status": "skip",
                "reason": "No auth token available"
            }
    
    async def validate_backend_apis(self):
        """Test main API endpoints."""
        logger.info("📡 Validating main API endpoints...")
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            
        api_endpoints = [
            "/api/v1/models",
            "/api/v1/projects",
            "/api/v1/generations", 
            "/api/v1/credits"
        ]
        
        for endpoint in api_endpoints:
            try:
                async with self.session.get(
                    f"{self.backend_url}{endpoint}",
                    headers=headers
                ) as response:
                    endpoint_key = endpoint.replace("/api/v1/", "").replace("/", "_")
                    
                    if response.status == 200:
                        try:
                            data = await response.json()
                            self.results["backend_tests"][f"api_{endpoint_key}"] = {
                                "status": "pass",
                                "response_code": response.status,
                                "returns_json": True,
                                "data_type": type(data).__name__
                            }
                        except:
                            self.results["backend_tests"][f"api_{endpoint_key}"] = {
                                "status": "partial",
                                "response_code": response.status,
                                "returns_json": False,
                                "note": "Endpoint accessible but doesn't return valid JSON"
                            }
                    elif response.status == 401:
                        self.results["backend_tests"][f"api_{endpoint_key}"] = {
                            "status": "fail",
                            "response_code": response.status,
                            "error": "Authentication required but failed"
                        }
                    elif response.status == 403:
                        self.results["backend_tests"][f"api_{endpoint_key}"] = {
                            "status": "fail", 
                            "response_code": response.status,
                            "error": "Access forbidden"
                        }
                    elif response.status == 404:
                        self.results["backend_tests"][f"api_{endpoint_key}"] = {
                            "status": "fail",
                            "response_code": response.status,
                            "error": "Endpoint not found - routing issue"
                        }
                    else:
                        self.results["backend_tests"][f"api_{endpoint_key}"] = {
                            "status": "fail",
                            "response_code": response.status,
                            "error": f"Unexpected status code: {response.status}"
                        }
            except Exception as e:
                endpoint_key = endpoint.replace("/api/v1/", "").replace("/", "_")
                self.results["backend_tests"][f"api_{endpoint_key}"] = {
                    "status": "fail",
                    "error": str(e)
                }
    
    async def validate_team_collaboration(self):
        """Test team collaboration endpoints."""
        logger.info("👥 Validating team collaboration endpoints...")
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            
        # Test teams list endpoint
        try:
            async with self.session.get(
                f"{self.backend_url}/api/v1/teams",
                headers=headers
            ) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        self.results["backend_tests"]["teams_list"] = {
                            "status": "pass",
                            "response_code": response.status,
                            "returns_json": True,
                            "has_pagination": "items" in data
                        }
                    except:
                        self.results["backend_tests"]["teams_list"] = {
                            "status": "partial",
                            "response_code": response.status,
                            "returns_json": False
                        }
                elif response.status == 401:
                    self.results["backend_tests"]["teams_list"] = {
                        "status": "fail",
                        "response_code": response.status,
                        "error": "Authentication required but failed"
                    }
                elif response.status == 404:
                    self.results["backend_tests"]["teams_list"] = {
                        "status": "fail",
                        "response_code": response.status,
                        "error": "Teams endpoint not found - routing issue"
                    }
                else:
                    self.results["backend_tests"]["teams_list"] = {
                        "status": "fail",
                        "response_code": response.status
                    }
        except Exception as e:
            self.results["backend_tests"]["teams_list"] = {
                "status": "fail",
                "error": str(e)
            }
            
        # Test team creation endpoint
        if self.auth_token:
            try:
                team_data = {
                    "name": "Validation Test Team",
                    "description": "Created for production validation testing"
                }
                
                async with self.session.post(
                    f"{self.backend_url}/api/v1/teams",
                    json=team_data,
                    headers=headers
                ) as response:
                    if response.status in [200, 201]:
                        try:
                            data = await response.json()
                            self.results["backend_tests"]["teams_create"] = {
                                "status": "pass",
                                "response_code": response.status,
                                "created_team_id": data.get("id"),
                                "returns_json": True
                            }
                        except:
                            self.results["backend_tests"]["teams_create"] = {
                                "status": "partial",
                                "response_code": response.status,
                                "returns_json": False
                            }
                    else:
                        self.results["backend_tests"]["teams_create"] = {
                            "status": "fail",
                            "response_code": response.status
                        }
            except Exception as e:
                self.results["backend_tests"]["teams_create"] = {
                    "status": "fail",
                    "error": str(e)
                }
    
    async def validate_kong_gateway(self):
        """Test Kong Gateway functionality."""
        logger.info("🏰 Validating Kong Gateway...")
        
        # Test Kong health
        try:
            async with self.session.get(f"{self.kong_url}/health") as response:
                self.results["kong_tests"]["health"] = {
                    "status": "pass" if response.status == 200 else "fail",
                    "response_code": response.status
                }
        except Exception as e:
            self.results["kong_tests"]["health"] = {
                "status": "fail",
                "error": str(e)
            }
            
        # Test Kong routing to backend
        try:
            async with self.session.get(f"{self.kong_url}/api/v1/models") as response:
                if response.status in [200, 401, 403]:  # These indicate routing works
                    self.results["kong_tests"]["backend_routing"] = {
                        "status": "pass",
                        "response_code": response.status,
                        "routing_works": True
                    }
                elif response.status == 404:
                    self.results["kong_tests"]["backend_routing"] = {
                        "status": "fail",
                        "response_code": response.status,
                        "error": "Kong not routing to backend properly"
                    }
                else:
                    self.results["kong_tests"]["backend_routing"] = {
                        "status": "partial",
                        "response_code": response.status
                    }
        except Exception as e:
            self.results["kong_tests"]["backend_routing"] = {
                "status": "fail",
                "error": str(e)
            }
    
    async def validate_frontend(self):
        """Test frontend accessibility."""
        logger.info("🌐 Validating frontend...")
        
        try:
            async with self.session.get(self.frontend_url) as response:
                if response.status == 200:
                    content = await response.text()
                    self.results["frontend_tests"]["accessibility"] = {
                        "status": "pass",
                        "response_code": response.status,
                        "is_html": content.strip().startswith("<"),
                        "has_react": "react" in content.lower(),
                        "content_length": len(content)
                    }
                else:
                    self.results["frontend_tests"]["accessibility"] = {
                        "status": "fail",
                        "response_code": response.status
                    }
        except Exception as e:
            self.results["frontend_tests"]["accessibility"] = {
                "status": "fail",
                "error": str(e)
            }
    
    async def validate_end_to_end_flow(self):
        """Test complete user workflow."""
        logger.info("🔄 Validating end-to-end workflows...")
        
        if not self.auth_token:
            self.results["integration_tests"]["full_workflow"] = {
                "status": "skip",
                "reason": "No authentication token available"
            }
            return
            
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        workflow_steps = []
        
        # Step 1: Get user profile
        try:
            async with self.session.get(
                f"{self.backend_url}/api/v1/auth/me",
                headers=headers
            ) as response:
                if response.status == 200:
                    workflow_steps.append({"step": "get_profile", "status": "pass"})
                else:
                    workflow_steps.append({"step": "get_profile", "status": "fail", "code": response.status})
        except Exception as e:
            workflow_steps.append({"step": "get_profile", "status": "fail", "error": str(e)})
        
        # Step 2: List user projects
        try:
            async with self.session.get(
                f"{self.backend_url}/api/v1/projects",
                headers=headers
            ) as response:
                if response.status == 200:
                    workflow_steps.append({"step": "list_projects", "status": "pass"})
                else:
                    workflow_steps.append({"step": "list_projects", "status": "fail", "code": response.status})
        except Exception as e:
            workflow_steps.append({"step": "list_projects", "status": "fail", "error": str(e)})
        
        # Step 3: Check available models
        try:
            async with self.session.get(
                f"{self.backend_url}/api/v1/models",
                headers=headers
            ) as response:
                if response.status == 200:
                    workflow_steps.append({"step": "list_models", "status": "pass"})
                else:
                    workflow_steps.append({"step": "list_models", "status": "fail", "code": response.status})
        except Exception as e:
            workflow_steps.append({"step": "list_models", "status": "fail", "error": str(e)})
        
        # Step 4: Check teams
        try:
            async with self.session.get(
                f"{self.backend_url}/api/v1/teams",
                headers=headers
            ) as response:
                if response.status == 200:
                    workflow_steps.append({"step": "list_teams", "status": "pass"})
                else:
                    workflow_steps.append({"step": "list_teams", "status": "fail", "code": response.status})
        except Exception as e:
            workflow_steps.append({"step": "list_teams", "status": "fail", "error": str(e)})
        
        passed_steps = sum(1 for step in workflow_steps if step["status"] == "pass")
        total_steps = len(workflow_steps)
        
        self.results["integration_tests"]["full_workflow"] = {
            "status": "pass" if passed_steps == total_steps else "partial" if passed_steps > 0 else "fail",
            "passed_steps": passed_steps,
            "total_steps": total_steps,
            "workflow_steps": workflow_steps
        }
    
    def generate_final_report(self):
        """Generate comprehensive validation report."""
        logger.info("📊 Generating final validation report...")
        
        # Count passes and failures
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        
        for category in ["backend_tests", "frontend_tests", "kong_tests", "integration_tests"]:
            for test_name, test_result in self.results.get(category, {}).items():
                total_tests += 1
                if test_result.get("status") == "pass":
                    passed_tests += 1
                elif test_result.get("status") == "fail":
                    failed_tests += 1
        
        # Determine overall status
        if passed_tests == total_tests:
            self.results["overall_status"] = "healthy"
        elif passed_tests > total_tests * 0.7:
            self.results["overall_status"] = "degraded"
        else:
            self.results["overall_status"] = "critical"
        
        # Generate critical issues list
        critical_issues = []
        
        # Check backend health
        if self.results["backend_tests"].get("root_endpoint", {}).get("status") == "fail":
            critical_issues.append("Backend root endpoint is not accessible")
        
        if self.results["backend_tests"].get("auth_login", {}).get("status") == "fail":
            critical_issues.append("Authentication system is not working")
        
        if self.results["backend_tests"].get("teams_list", {}).get("status") == "fail":
            critical_issues.append("Team collaboration endpoints are not accessible")
        
        if self.results["kong_tests"].get("health", {}).get("status") == "fail":
            critical_issues.append("Kong Gateway is not responding")
        
        if self.results["frontend_tests"].get("accessibility", {}).get("status") == "fail":
            critical_issues.append("Frontend application is not accessible")
        
        self.results["critical_issues"] = critical_issues
        
        # Generate recommendations
        recommendations = []
        
        if critical_issues:
            recommendations.append("Address critical issues before considering deployment production-ready")
        
        if self.results["backend_tests"].get("auth_login", {}).get("status") == "fail":
            recommendations.append("Fix authentication system - check Supabase configuration and credentials")
        
        if self.results["backend_tests"].get("teams_list", {}).get("status") == "fail":
            recommendations.append("Verify team collaboration database schema and API endpoints")
        
        if self.results["kong_tests"].get("backend_routing", {}).get("status") == "fail":
            recommendations.append("Fix Kong Gateway routing configuration to backend services")
        
        self.results["recommendations"] = recommendations
        self.results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": total_tests - passed_tests - failed_tests,
            "success_rate": f"{(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "0%"
        }
        
        # Save results to file
        timestamp = int(time.time())
        filename = f"production_validation_report_{timestamp}.json"
        with open(filename, "w") as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"📄 Validation report saved to: {filename}")
        
        # Print summary
        print("\n" + "="*80)
        print("🚀 VELRO AI PLATFORM PRODUCTION VALIDATION REPORT")
        print("="*80)
        print(f"Overall Status: {self.results['overall_status'].upper()}")
        print(f"Success Rate: {self.results['summary']['success_rate']}")
        print(f"Tests: {passed_tests}/{total_tests} passed")
        print()
        
        if critical_issues:
            print("🚨 CRITICAL ISSUES:")
            for issue in critical_issues:
                print(f"  ❌ {issue}")
            print()
        
        if recommendations:
            print("💡 RECOMMENDATIONS:")
            for rec in recommendations:
                print(f"  🔧 {rec}")
            print()
        
        print("📊 DETAILED RESULTS:")
        self._print_test_results("Backend", self.results.get("backend_tests", {}))
        self._print_test_results("Kong Gateway", self.results.get("kong_tests", {}))
        self._print_test_results("Frontend", self.results.get("frontend_tests", {}))
        self._print_test_results("Integration", self.results.get("integration_tests", {}))
        
        print("="*80)
        return filename
    
    def _print_test_results(self, category: str, tests: Dict[str, Any]):
        """Print test results for a category."""
        if not tests:
            return
            
        print(f"\n{category} Tests:")
        for test_name, result in tests.items():
            status = result.get("status", "unknown")
            if status == "pass":
                print(f"  ✅ {test_name}")
            elif status == "fail":
                print(f"  ❌ {test_name} - {result.get('error', result.get('response_code', 'Unknown error'))}")
            elif status == "partial":
                print(f"  ⚠️  {test_name} - Partial success")
            else:
                print(f"  ⏭️  {test_name} - Skipped")

async def main():
    """Main validation function."""
    validator = ProductionValidator()
    await validator.run_all_validations()
    return validator.results

if __name__ == "__main__":
    try:
        results = asyncio.run(main())
        sys.exit(0 if results["overall_status"] == "healthy" else 1)
    except KeyboardInterrupt:
        logger.info("Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        sys.exit(1)