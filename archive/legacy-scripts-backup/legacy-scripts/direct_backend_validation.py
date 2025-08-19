#!/usr/bin/env python3
"""
Direct Backend API Validation (Bypassing Kong)
Confirms backend functionality independent of Kong Gateway
"""

import requests
import json
import time
import logging
from datetime import datetime

# Direct backend URL (bypassing Kong)
BACKEND_URL = "https://velro-003-backend-production.up.railway.app"
TEST_EMAIL = "demo@example.com"
TEST_PASSWORD = "secure123!"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DirectBackendValidator:
    """Validate backend API directly without Kong Gateway"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30
        self.access_token = None
        self.results = []
    
    def log_result(self, test_name: str, success: bool, details: dict = None, error: str = None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} | {test_name}")
        if error:
            logger.error(f"   Error: {error}")
        if details:
            logger.info(f"   Details: {details}")
        
        self.results.append({
            "test": test_name,
            "success": success,
            "details": details or {},
            "error": error,
            "timestamp": datetime.now().isoformat()
        })
    
    def test_health_check(self):
        """Test backend health endpoint"""
        try:
            response = self.session.get(f"{BACKEND_URL}/health")
            
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Backend Health Check",
                    True,
                    {
                        "status": data.get("status"),
                        "environment": data.get("environment"),
                        "version": data.get("version"),
                        "response_time": response.elapsed.total_seconds()
                    }
                )
                return True
            else:
                self.log_result("Backend Health Check", False, error=f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Backend Health Check", False, error=str(e))
            return False
    
    def test_authentication(self):
        """Test authentication workflow"""
        try:
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            response = self.session.post(
                f"{BACKEND_URL}/api/v1/auth/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.access_token = data["access_token"]
                    self.log_result(
                        "Backend Authentication", 
                        True,
                        {
                            "token_type": data.get("token_type"),
                            "expires_in": data.get("expires_in"),
                            "user_email": data.get("user", {}).get("email"),
                            "token_length": len(self.access_token)
                        }
                    )
                    return True
                else:
                    self.log_result("Backend Authentication", False, error="No access token in response")
                    return False
            else:
                self.log_result("Backend Authentication", False, error=f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Backend Authentication", False, error=str(e))
            return False
    
    def test_authenticated_endpoints(self):
        """Test authenticated endpoints"""
        if not self.access_token:
            self.log_result("Authenticated Endpoints", False, error="No access token available")
            return False
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        endpoints = [
            ("/api/v1/auth/me", "GET", "User Profile"),
            ("/api/v1/generations", "GET", "User Generations"),  
            ("/api/v1/projects", "GET", "User Projects"),
            ("/api/v1/credits", "GET", "User Credits"),
        ]
        
        all_passed = True
        
        for endpoint, method, description in endpoints:
            try:
                if method == "GET":
                    response = self.session.get(f"{BACKEND_URL}{endpoint}", headers=headers)
                
                if 200 <= response.status_code < 300:
                    self.log_result(f"Backend {description}", True, {"status": response.status_code})
                else:
                    self.log_result(f"Backend {description}", False, error=f"Status {response.status_code}: {response.text[:200]}")
                    all_passed = False
                    
            except Exception as e:
                self.log_result(f"Backend {description}", False, error=str(e))
                all_passed = False
        
        return all_passed
    
    def test_team_collaboration(self):
        """Test team collaboration endpoints"""
        if not self.access_token:
            self.log_result("Team Collaboration", False, error="No access token available")
            return False
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        team_endpoints = [
            ("/api/v1/teams", "GET", "List Teams"),
            ("/api/v1/collaboration", "GET", "Collaboration Status"),
        ]
        
        all_passed = True
        
        for endpoint, method, description in team_endpoints:
            try:
                if method == "GET":
                    response = self.session.get(f"{BACKEND_URL}{endpoint}", headers=headers)
                
                # Accept 200 OK or 404 (no teams created yet)
                if response.status_code in [200, 404]:
                    self.log_result(f"Backend {description}", True, {"status": response.status_code})
                else:
                    self.log_result(f"Backend {description}", False, error=f"Status {response.status_code}: {response.text[:200]}")
                    all_passed = False
                    
            except Exception as e:
                self.log_result(f"Backend {description}", False, error=str(e))
                all_passed = False
        
        return all_passed
    
    def test_generation_workflow(self):
        """Test generation workflow"""
        if not self.access_token:
            self.log_result("Generation Workflow", False, error="No access token available")
            return False
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Test generation creation
        try:
            generation_data = {
                "prompt": "A beautiful sunset over mountains (validation test)",
                "model_name": "flux-dev",
                "project_id": None
            }
            
            response = self.session.post(
                f"{BACKEND_URL}/api/v1/generations",
                json=generation_data,
                headers=headers
            )
            
            if 200 <= response.status_code < 300:
                data = response.json()
                self.log_result(
                    "Backend Generation Creation",
                    True,
                    {
                        "generation_id": data.get("id", "unknown"),
                        "status": data.get("status", "unknown"),
                        "model": data.get("model_name", "unknown")
                    }
                )
                return True
            else:
                self.log_result("Backend Generation Creation", False, error=f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Backend Generation Creation", False, error=str(e))
            return False
    
    def run_validation(self):
        """Run complete direct backend validation"""
        logger.info("🚀 Starting Direct Backend API Validation")
        logger.info(f"   Backend URL: {BACKEND_URL}")
        
        start_time = datetime.now()
        
        # Run all tests
        self.test_health_check()
        self.test_authentication()
        self.test_authenticated_endpoints()
        self.test_team_collaboration()
        self.test_generation_workflow()
        
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        # Calculate results
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["success"])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        # Generate report
        report = {
            "timestamp": start_time.isoformat(),
            "test_suite": "direct_backend_validation",
            "backend_url": BACKEND_URL,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": success_rate,
            "execution_time": execution_time,
            "results": self.results
        }
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"direct_backend_validation_{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        logger.info("\n" + "="*80)
        logger.info("🎯 DIRECT BACKEND VALIDATION SUMMARY")
        logger.info("="*80)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        logger.info(f"Success Rate: {success_rate:.1f}%")
        logger.info(f"Execution Time: {execution_time:.2f}s")
        logger.info(f"Results saved to: {results_file}")
        
        if failed_tests > 0:
            logger.warning("\n❌ FAILED TESTS:")
            for result in self.results:
                if not result["success"]:
                    logger.warning(f"  - {result['test']}: {result['error']}")
        
        # Assessment
        if success_rate >= 95:
            logger.info("\n✅ BACKEND IS PRODUCTION READY!")
        elif success_rate >= 80:
            logger.warning("\n⚠️ BACKEND READY WITH WARNINGS")
        else:
            logger.error("\n❌ BACKEND NOT READY")
        
        return report

def main():
    """Main execution"""
    validator = DirectBackendValidator()
    return validator.run_validation()

if __name__ == "__main__":
    main()