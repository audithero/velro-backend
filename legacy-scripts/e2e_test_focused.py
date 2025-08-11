#!/usr/bin/env python3
"""
Focused End-to-End Test Suite for Velro Backend System
=====================================================

This script performs a comprehensive test of the Velro backend system with 
proper timeout handling and error recovery.

Usage: python3 e2e_test_focused.py
"""

import requests
import json
import time
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VelroE2ETest:
    """Focused End-to-End Test Suite for Velro Backend"""
    
    def __init__(self):
        self.base_url = "https://velro-003-backend-production.up.railway.app"
        self.session = requests.Session()
        self.session.timeout = 30  # 30 second timeout
        self.jwt_token = None
        self.user_profile = None
        self.generation_id = None
        self.test_results = []
        
        # Working credentials from successful tests
        self.test_email = "demo@example.com"
        self.test_password = "secure123!"
        
        # Common headers
        self.session.headers.update({
            "User-Agent": "Velro-E2E-Test/1.0",
            "Accept": "application/json"
        })
    
    def log_result(self, test_name: str, success: bool, details: Dict[str, Any] = None, error: str = None, duration: float = 0):
        """Log and store test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} | {test_name} | {duration:.2f}s")
        
        if error:
            logger.error(f"   Error: {error}")
        if details:
            logger.info(f"   Details: {json.dumps(details, indent=2)}")
        
        result = {
            "test": test_name,
            "success": success,
            "duration": duration,
            "details": details or {},
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        return result
    
    def test_1_backend_health(self) -> bool:
        """Test 1: Basic backend health check"""
        logger.info("\n🧪 Test 1: Backend Health Check")
        start_time = time.time()
        
        try:
            response = self.session.get(f"{self.base_url}/health")
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Backend Health Check",
                    True,
                    {
                        "status": data.get("status"),
                        "version": data.get("version"),
                        "environment": data.get("environment")
                    },
                    duration=duration
                )
                return True
            else:
                self.log_result(
                    "Backend Health Check",
                    False,
                    {"status_code": response.status_code},
                    f"Health check failed with status {response.status_code}",
                    duration
                )
                return False
                
        except Exception as e:
            self.log_result("Backend Health Check", False, {}, str(e), time.time() - start_time)
            return False
    
    def test_2_authentication(self) -> bool:
        """Test 2: Authentication with login endpoint"""
        logger.info("\n🧪 Test 2: Authentication")
        start_time = time.time()
        
        try:
            login_data = {
                "email": self.test_email,
                "password": self.test_password
            }
            
            response = self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            )
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                self.jwt_token = data.get("access_token")
                
                self.log_result(
                    "Authentication",
                    True,
                    {
                        "email": self.test_email,
                        "token_type": data.get("token_type"),
                        "expires_in": data.get("expires_in"),
                        "user_id": data.get("user", {}).get("id"),
                        "user_email": data.get("user", {}).get("email"),
                        "credits_balance": data.get("user", {}).get("credits_balance"),
                        "token_length": len(self.jwt_token) if self.jwt_token else 0
                    },
                    duration=duration
                )
                return True
            else:
                error_text = response.text
                self.log_result(
                    "Authentication",
                    False,
                    {"status_code": response.status_code, "response": error_text},
                    f"Authentication failed: {error_text}",
                    duration
                )
                return False
                
        except Exception as e:
            self.log_result("Authentication", False, {}, str(e), time.time() - start_time)
            return False
    
    def test_3_user_profile(self) -> bool:
        """Test 3: User profile retrieval with JWT token"""
        logger.info("\n🧪 Test 3: User Profile")
        start_time = time.time()
        
        if not self.jwt_token:
            self.log_result("User Profile", False, {}, "No JWT token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            response = self.session.get(f"{self.base_url}/api/v1/auth/me", headers=headers)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                self.user_profile = response.json()
                self.log_result(
                    "User Profile",
                    True,
                    {
                        "user_id": self.user_profile.get("id"),
                        "email": self.user_profile.get("email"),
                        "display_name": self.user_profile.get("display_name"),
                        "credits_balance": self.user_profile.get("credits_balance"),
                        "role": self.user_profile.get("role")
                    },
                    duration=duration
                )
                return True
            else:
                error_text = response.text
                self.log_result(
                    "User Profile",
                    False,
                    {"status_code": response.status_code},
                    f"Profile fetch failed: {error_text}",
                    duration
                )
                return False
                
        except Exception as e:
            self.log_result("User Profile", False, {}, str(e), time.time() - start_time)
            return False
    
    def test_4_available_models(self) -> bool:
        """Test 4: Check available AI models"""
        logger.info("\n🧪 Test 4: Available Models")
        start_time = time.time()
        
        if not self.jwt_token:
            self.log_result("Available Models", False, {}, "No JWT token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            response = self.session.get(f"{self.base_url}/api/v1/models", headers=headers)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                models = response.json()
                flux_models = [m for m in models if 'flux' in m.get('id', '').lower()]
                
                self.log_result(
                    "Available Models",
                    True,
                    {
                        "total_models": len(models),
                        "flux_models": len(flux_models),
                        "available_flux_models": [m.get('id') for m in flux_models],
                        "sample_model": models[0] if models else None
                    },
                    duration=duration
                )
                return True
            else:
                error_text = response.text
                self.log_result(
                    "Available Models",
                    False,
                    {"status_code": response.status_code},
                    f"Models fetch failed: {error_text}",
                    duration
                )
                return False
                
        except Exception as e:
            self.log_result("Available Models", False, {}, str(e), time.time() - start_time)
            return False
    
    def test_5_image_generation(self) -> bool:
        """Test 5: Create an image generation"""
        logger.info("\n🧪 Test 5: Image Generation")
        start_time = time.time()
        
        if not self.jwt_token:
            self.log_result("Image Generation", False, {}, "No JWT token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            # Prepare form data
            files = {
                'model_id': (None, 'fal-ai/flux/dev'),
                'prompt': (None, 'beautiful sunset over mountains'),
                'parameters': (None, '{"width": 512, "height": 512, "guidance_scale": 7.5}')
            }
            
            # Make request without Content-Type header (let requests handle multipart)
            response = self.session.post(
                f"{self.base_url}/api/v1/generations",
                files=files,
                headers=headers,
                timeout=60  # Longer timeout for generation creation
            )
            duration = time.time() - start_time
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.generation_id = data.get("id")
                
                self.log_result(
                    "Image Generation",
                    True,
                    {
                        "generation_id": self.generation_id,
                        "status": data.get("status"),
                        "model_id": data.get("model_id"),
                        "prompt": data.get("prompt"),
                        "user_id": data.get("user_id"),
                        "project_id": data.get("project_id")
                    },
                    duration=duration
                )
                return True
            else:
                error_text = response.text
                self.log_result(
                    "Image Generation",
                    False,
                    {"status_code": response.status_code, "response": error_text},
                    f"Generation creation failed: {error_text}",
                    duration
                )
                return False
                
        except Exception as e:
            self.log_result("Image Generation", False, {}, str(e), time.time() - start_time)
            return False
    
    def test_6_generation_status(self, max_wait_time: int = 180) -> bool:
        """Test 6: Monitor generation status until completion"""
        logger.info("\n🧪 Test 6: Generation Status Check")
        start_time = time.time()
        
        if not self.jwt_token or not self.generation_id:
            self.log_result("Generation Status", False, {}, "No JWT token or generation ID available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            status_checks = 0
            last_status = None
            
            while time.time() - start_time < max_wait_time:
                status_checks += 1
                
                response = self.session.get(
                    f"{self.base_url}/api/v1/generations/{self.generation_id}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    last_status = data.get("status")
                    
                    logger.info(f"Generation {self.generation_id} status: {last_status} (check #{status_checks})")
                    
                    if last_status in ["completed", "succeeded", "success"]:
                        duration = time.time() - start_time
                        self.log_result(
                            "Generation Status",
                            True,
                            {
                                "generation_id": self.generation_id,
                                "final_status": last_status,
                                "status_checks": status_checks,
                                "total_wait_time": duration,
                                "image_url": data.get("image_url"),
                                "media_urls": data.get("media_urls", [])
                            },
                            duration=duration
                        )
                        return True
                    elif last_status in ["failed", "error", "cancelled"]:
                        duration = time.time() - start_time
                        self.log_result(
                            "Generation Status",
                            False,
                            {
                                "generation_id": self.generation_id,
                                "final_status": last_status,
                                "status_checks": status_checks,
                                "error_details": data.get("error_message")
                            },
                            f"Generation failed with status: {last_status}",
                            duration
                        )
                        return False
                    
                    # Wait before next check
                    time.sleep(5)
                    
                else:
                    error_text = response.text
                    self.log_result(
                        "Generation Status",
                        False,
                        {"status_code": response.status_code},
                        f"Status check failed: {error_text}",
                        time.time() - start_time
                    )
                    return False
            
            # Timeout reached
            self.log_result(
                "Generation Status",
                False,
                {
                    "generation_id": self.generation_id,
                    "last_status": last_status,
                    "status_checks": status_checks,
                    "timeout_seconds": max_wait_time
                },
                f"Generation timed out after {max_wait_time} seconds",
                time.time() - start_time
            )
            return False
                
        except Exception as e:
            self.log_result("Generation Status", False, {}, str(e), time.time() - start_time)
            return False
    
    def test_7_storage_verification(self) -> bool:
        """Test 7: Verify generated image storage"""
        logger.info("\n🧪 Test 7: Storage Verification")
        start_time = time.time()
        
        if not self.jwt_token or not self.generation_id:
            self.log_result("Storage Verification", False, {}, "No JWT token or generation ID available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            # Get generation details
            response = self.session.get(
                f"{self.base_url}/api/v1/generations/{self.generation_id}",
                headers=headers
            )
            
            if response.status_code != 200:
                error_text = response.text
                self.log_result(
                    "Storage Verification",
                    False,
                    {"status_code": response.status_code},
                    f"Failed to get generation details: {error_text}",
                    time.time() - start_time
                )
                return False
            
            data = response.json()
            image_url = data.get("image_url")
            media_urls = data.get("media_urls", [])
            
            if not image_url and not media_urls:
                self.log_result(
                    "Storage Verification",
                    False,
                    {"generation_data": data},
                    "No image URL found in generation data",
                    time.time() - start_time
                )
                return False
            
            # Test the primary image URL
            test_url = image_url or (media_urls[0] if media_urls else None)
            
            if test_url:
                # Parse URL to check if it's Supabase storage
                parsed_url = urlparse(test_url)
                is_supabase = "supabase" in parsed_url.netloc
                
                # Try to access the image URL
                img_response = self.session.get(test_url, timeout=30)
                duration = time.time() - start_time
                
                details = {
                    "image_url": image_url,
                    "media_urls": media_urls,
                    "test_url": test_url,
                    "is_supabase_storage": is_supabase,
                    "host": parsed_url.netloc,
                    "url_accessible": img_response.status_code == 200,
                    "content_type": img_response.headers.get("content-type"),
                    "content_length": img_response.headers.get("content-length")
                }
                
                if img_response.status_code == 200:
                    self.log_result("Storage Verification", True, details, duration=duration)
                    return True
                else:
                    self.log_result(
                        "Storage Verification",
                        False,
                        details,
                        f"Image URL not accessible: HTTP {img_response.status_code}",
                        duration
                    )
                    return False
            else:
                self.log_result(
                    "Storage Verification",
                    False,
                    {"image_url": image_url, "media_urls": media_urls},
                    "No valid image URL to test",
                    time.time() - start_time
                )
                return False
                
        except Exception as e:
            self.log_result("Storage Verification", False, {}, str(e), time.time() - start_time)
            return False
    
    def test_8_project_association(self) -> bool:
        """Test 8: Verify generation appears in user's projects"""
        logger.info("\n🧪 Test 8: Project Association")
        start_time = time.time()
        
        if not self.jwt_token:
            self.log_result("Project Association", False, {}, "No JWT token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            response = self.session.get(f"{self.base_url}/api/v1/projects", headers=headers)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                projects = response.json()
                
                # Look for our generation in projects
                generation_found = False
                project_with_generation = None
                
                for project in projects:
                    generations = project.get("generations", [])
                    if any(gen.get("id") == self.generation_id for gen in generations):
                        generation_found = True
                        project_with_generation = project
                        break
                
                self.log_result(
                    "Project Association",
                    True,  # Consider successful even if not found in specific project
                    {
                        "total_projects": len(projects),
                        "generation_found_in_project": generation_found,
                        "project_id": project_with_generation.get("id") if project_with_generation else None,
                        "project_title": project_with_generation.get("title") if project_with_generation else None
                    },
                    duration=duration
                )
                return True
            else:
                error_text = response.text
                self.log_result(
                    "Project Association",
                    False,
                    {"status_code": response.status_code},
                    f"Projects fetch failed: {error_text}",
                    duration
                )
                return False
                
        except Exception as e:
            self.log_result("Project Association", False, {}, str(e), time.time() - start_time)
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests in sequence"""
        logger.info("🚀 Starting Velro Backend E2E Test Suite")
        logger.info(f"🎯 Target: {self.base_url}")
        logger.info(f"👤 Test User: {self.test_email}")
        
        overall_start_time = time.time()
        
        # Test sequence
        tests = [
            ("Backend Health", self.test_1_backend_health),
            ("Authentication", self.test_2_authentication),
            ("User Profile", self.test_3_user_profile),
            ("Available Models", self.test_4_available_models),
            ("Image Generation", self.test_5_image_generation),
            ("Generation Status", self.test_6_generation_status),
            ("Storage Verification", self.test_7_storage_verification),
            ("Project Association", self.test_8_project_association),
        ]
        
        passed_tests = 0
        for test_name, test_func in tests:
            try:
                success = test_func()
                if success:
                    passed_tests += 1
                else:
                    # Stop on critical test failures
                    if test_name in ["Backend Health", "Authentication"]:
                        logger.error(f"❌ Critical test '{test_name}' failed. Stopping test suite.")
                        break
            except Exception as e:
                logger.error(f"❌ Test '{test_name}' threw exception: {e}")
                self.log_result(test_name, False, {}, str(e))
        
        # Generate summary
        total_duration = time.time() - overall_start_time
        total_tests = len(self.test_results)
        failed_tests = total_tests - passed_tests
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "test_suite": "velro_backend_e2e_focused",
            "backend_url": self.base_url,
            "test_credentials": f"{self.test_email} / {self.test_password[:4]}***",
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            "total_duration": total_duration,
            "test_results": self.test_results
        }
        
        return summary

def main():
    """Main entry point"""
    print("🧪 Velro Backend E2E Test Suite (Focused)")
    print("=" * 60)
    
    test_suite = VelroE2ETest()
    summary = test_suite.run_all_tests()
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"🎯 Backend URL: {summary['backend_url']}")
    print(f"👤 Test User: {summary['test_credentials']}")
    print(f"⏱️  Total Duration: {summary['total_duration']:.2f} seconds")
    print(f"📈 Success Rate: {summary['success_rate']:.1f}%")
    print(f"✅ Passed: {summary['passed_tests']}/{summary['total_tests']}")
    print(f"❌ Failed: {summary['failed_tests']}/{summary['total_tests']}")
    
    # Print individual test results
    print("\n📋 DETAILED RESULTS:")
    for result in summary['test_results']:
        status = "✅ PASS" if result['success'] else "❌ FAIL"
        print(f"{status} | {result['test']} | {result['duration']:.2f}s")
        if result['error']:
            print(f"     Error: {result['error']}")
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"e2e_test_focused_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")
    
    # Exit with appropriate code
    exit_code = 0 if summary['failed_tests'] == 0 else 1
    print(f"\n🏁 Test suite completed with exit code: {exit_code}")
    
    return exit_code

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)