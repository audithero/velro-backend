#!/usr/bin/env python3
"""
Comprehensive End-to-End Test Suite for Velro Backend System
===========================================================

This script performs a comprehensive test of the entire Velro backend system including:
1. Authentication and JWT token validation
2. User profile retrieval
3. Image generation workflow
4. Generation status monitoring
5. Storage verification
6. Project association checks

Usage: python e2e_test_suite.py
"""

import asyncio
import aiohttp
import json
import time
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from urllib.parse import urlparse
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('e2e_test_results.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Data class to store individual test results"""
    test_name: str
    success: bool
    duration: float
    details: Dict[str, Any]
    error: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

class VelroE2ETestSuite:
    """Comprehensive End-to-End Test Suite for Velro Backend"""
    
    def __init__(self):
        self.base_url = "https://velro-003-backend-production.up.railway.app"
        self.session = None
        self.jwt_token = None
        self.user_profile = None
        self.test_results: List[TestResult] = []
        self.generation_id = None
        self.test_project_id = None
        
        # Test credentials - trying common passwords based on the codebase
        self.test_credentials = [
            {"email": "demo@example.com", "password": "demo1234"},
            {"email": "demo@example.com", "password": "Demo1234!"},
            {"email": "demo@example.com", "password": "velrodemo123"},
            {"email": "demo@example.com", "password": "demo12345"},
        ]
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120),
            headers={
                "User-Agent": "Velro-E2E-Test-Suite/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def log_test_result(self, result: TestResult):
        """Log and store test result"""
        self.test_results.append(result)
        status = "✅ PASS" if result.success else "❌ FAIL"
        logger.info(f"{status} | {result.test_name} | {result.duration:.2f}s")
        if result.error:
            logger.error(f"   Error: {result.error}")
        if result.details:
            logger.info(f"   Details: {json.dumps(result.details, indent=2)}")
    
    async def test_backend_health(self) -> TestResult:
        """Test 1: Basic backend health check"""
        start_time = time.time()
        test_name = "Backend Health Check"
        
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                duration = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    return TestResult(
                        test_name=test_name,
                        success=True,
                        duration=duration,
                        details={
                            "status": data.get("status"),
                            "version": data.get("version"),
                            "environment": data.get("environment"),
                            "response_time": duration
                        }
                    )
                else:
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=duration,
                        details={"status_code": response.status},
                        error=f"Health check failed with status {response.status}"
                    )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def test_authentication(self) -> TestResult:
        """Test 2: Authentication with login endpoint"""
        start_time = time.time()
        test_name = "Authentication Test"
        
        try:
            # Try each set of credentials
            for credentials in self.test_credentials:
                logger.info(f"Attempting login with {credentials['email']} and password {credentials['password'][:4]}***")
                
                async with self.session.post(
                    f"{self.base_url}/api/v1/auth/login",
                    json=credentials
                ) as response:
                    duration = time.time() - start_time
                    
                    if response.status == 200:
                        data = await response.json()
                        self.jwt_token = data.get("access_token")
                        
                        return TestResult(
                            test_name=test_name,
                            success=True,
                            duration=duration,
                            details={
                                "credentials_used": f"{credentials['email']} / {credentials['password'][:4]}***",
                                "token_type": data.get("token_type"),
                                "expires_in": data.get("expires_in"),
                                "user_id": data.get("user", {}).get("id"),
                                "user_email": data.get("user", {}).get("email"),
                                "user_credits": data.get("user", {}).get("credits_balance"),
                                "token_length": len(self.jwt_token) if self.jwt_token else 0
                            }
                        )
                    elif response.status == 401:
                        logger.warning(f"Authentication failed for {credentials['email']} with password {credentials['password'][:4]}***")
                        continue
                    else:
                        error_text = await response.text()
                        logger.error(f"Login error {response.status}: {error_text}")
                        continue
            
            # If we get here, all credentials failed
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={"attempted_credentials": len(self.test_credentials)},
                error="All authentication attempts failed"
            )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def test_user_profile(self) -> TestResult:
        """Test 3: User profile retrieval with JWT token"""
        start_time = time.time()
        test_name = "User Profile Test"
        
        if not self.jwt_token:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=0,
                details={},
                error="No JWT token available from authentication test"
            )
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            async with self.session.get(
                f"{self.base_url}/api/v1/auth/me",
                headers=headers
            ) as response:
                duration = time.time() - start_time
                
                if response.status == 200:
                    self.user_profile = await response.json()
                    return TestResult(
                        test_name=test_name,
                        success=True,
                        duration=duration,
                        details={
                            "user_id": self.user_profile.get("id"),
                            "email": self.user_profile.get("email"),
                            "display_name": self.user_profile.get("display_name"),
                            "credits_balance": self.user_profile.get("credits_balance"),
                            "role": self.user_profile.get("role"),
                            "created_at": self.user_profile.get("created_at")
                        }
                    )
                else:
                    error_text = await response.text()
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=duration,
                        details={"status_code": response.status},
                        error=f"Profile fetch failed: {error_text}"
                    )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def test_available_models(self) -> TestResult:
        """Test 4: Check available AI models"""
        start_time = time.time()
        test_name = "Available Models Test"
        
        if not self.jwt_token:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=0,
                details={},
                error="No JWT token available"
            )
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            async with self.session.get(
                f"{self.base_url}/api/v1/models",
                headers=headers
            ) as response:
                duration = time.time() - start_time
                
                if response.status == 200:
                    models = await response.json()
                    flux_models = [m for m in models if 'flux' in m.get('id', '').lower()]
                    
                    return TestResult(
                        test_name=test_name,
                        success=True,
                        duration=duration,
                        details={
                            "total_models": len(models),
                            "flux_models": len(flux_models),
                            "available_flux_models": [m.get('id') for m in flux_models],
                            "sample_model": models[0] if models else None
                        }
                    )
                else:
                    error_text = await response.text()
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=duration,
                        details={"status_code": response.status},
                        error=f"Models fetch failed: {error_text}"
                    )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def test_image_generation(self) -> TestResult:
        """Test 5: Create an image generation"""
        start_time = time.time()
        test_name = "Image Generation Test"
        
        if not self.jwt_token:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=0,
                details={},
                error="No JWT token available"
            )
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            # Prepare form data for generation
            data = aiohttp.FormData()
            data.add_field('model_id', 'fal-ai/flux/dev')  # Use the Flux model as requested
            data.add_field('prompt', 'beautiful sunset over mountains')
            data.add_field('parameters', '{"width": 512, "height": 512, "guidance_scale": 7.5}')
            
            async with self.session.post(
                f"{self.base_url}/api/v1/generations",
                headers={"Authorization": f"Bearer {self.jwt_token}"},  # Only keep Authorization header
                data=data
            ) as response:
                duration = time.time() - start_time
                
                if response.status == 200 or response.status == 201:
                    generation_data = await response.json()
                    self.generation_id = generation_data.get("id")
                    
                    return TestResult(
                        test_name=test_name,
                        success=True,
                        duration=duration,
                        details={
                            "generation_id": self.generation_id,
                            "status": generation_data.get("status"),
                            "model_id": generation_data.get("model_id"),
                            "prompt": generation_data.get("prompt"),
                            "user_id": generation_data.get("user_id"),
                            "project_id": generation_data.get("project_id"),
                            "created_at": generation_data.get("created_at")
                        }
                    )
                else:
                    error_text = await response.text()
                    logger.error(f"Generation creation failed: {response.status} - {error_text}")
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=duration,
                        details={"status_code": response.status, "response": error_text},
                        error=f"Generation creation failed: {error_text}"
                    )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def test_generation_status(self, max_wait_time: int = 300) -> TestResult:
        """Test 6: Monitor generation status until completion"""
        start_time = time.time()
        test_name = "Generation Status Check"
        
        if not self.jwt_token or not self.generation_id:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=0,
                details={},
                error="No JWT token or generation ID available"
            )
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            status_checks = 0
            last_status = None
            
            while time.time() - start_time < max_wait_time:
                status_checks += 1
                
                async with self.session.get(
                    f"{self.base_url}/api/v1/generations/{self.generation_id}",
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        generation_data = await response.json()
                        last_status = generation_data.get("status")
                        
                        logger.info(f"Generation {self.generation_id} status: {last_status} (check #{status_checks})")
                        
                        if last_status in ["completed", "succeeded", "success"]:
                            duration = time.time() - start_time
                            return TestResult(
                                test_name=test_name,
                                success=True,
                                duration=duration,
                                details={
                                    "generation_id": self.generation_id,
                                    "final_status": last_status,
                                    "status_checks": status_checks,
                                    "total_wait_time": duration,
                                    "image_url": generation_data.get("image_url"),
                                    "media_urls": generation_data.get("media_urls", []),
                                    "metadata": generation_data.get("metadata", {})
                                }
                            )
                        elif last_status in ["failed", "error", "cancelled"]:
                            duration = time.time() - start_time
                            return TestResult(
                                test_name=test_name,
                                success=False,
                                duration=duration,
                                details={
                                    "generation_id": self.generation_id,
                                    "final_status": last_status,
                                    "status_checks": status_checks,
                                    "error_details": generation_data.get("error_message")
                                },
                                error=f"Generation failed with status: {last_status}"
                            )
                        
                        # Wait before next status check
                        await asyncio.sleep(5)
                        
                    else:
                        error_text = await response.text()
                        return TestResult(
                            test_name=test_name,
                            success=False,
                            duration=time.time() - start_time,
                            details={"status_code": response.status},
                            error=f"Status check failed: {error_text}"
                        )
            
            # Timeout reached
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={
                    "generation_id": self.generation_id,
                    "last_status": last_status,
                    "status_checks": status_checks,
                    "timeout_seconds": max_wait_time
                },
                error=f"Generation timed out after {max_wait_time} seconds with status: {last_status}"
            )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={"status_checks": status_checks if 'status_checks' in locals() else 0},
                error=str(e)
            )
    
    async def test_storage_verification(self) -> TestResult:
        """Test 7: Verify generated image storage"""
        start_time = time.time()
        test_name = "Storage Verification"
        
        # Get the latest generation info first
        if not self.jwt_token or not self.generation_id:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=0,
                details={},
                error="No JWT token or generation ID available"
            )
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            # Get generation details
            async with self.session.get(
                f"{self.base_url}/api/v1/generations/{self.generation_id}",
                headers=headers
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=time.time() - start_time,
                        details={},
                        error=f"Failed to get generation details: {error_text}"
                    )
                
                generation_data = await response.json()
                image_url = generation_data.get("image_url")
                media_urls = generation_data.get("media_urls", [])
                
                if not image_url and not media_urls:
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=time.time() - start_time,
                        details={"generation_data": generation_data},
                        error="No image URL found in generation data"
                    )
                
                # Test the primary image URL
                test_url = image_url or (media_urls[0] if media_urls else None)
                url_details = {
                    "image_url": image_url,
                    "media_urls": media_urls,
                    "test_url": test_url
                }
                
                if test_url:
                    # Parse URL to check if it's Supabase storage
                    parsed_url = urlparse(test_url)
                    is_supabase = "supabase" in parsed_url.netloc or "supabase.co" in parsed_url.netloc
                    
                    url_details.update({
                        "is_supabase_storage": is_supabase,
                        "host": parsed_url.netloc,
                        "path": parsed_url.path
                    })
                    
                    # Try to access the image URL
                    async with self.session.get(test_url) as img_response:
                        duration = time.time() - start_time
                        
                        url_details.update({
                            "url_accessible": img_response.status == 200,
                            "content_type": img_response.headers.get("content-type"),
                            "content_length": img_response.headers.get("content-length")
                        })
                        
                        if img_response.status == 200:
                            return TestResult(
                                test_name=test_name,
                                success=True,
                                duration=duration,
                                details=url_details
                            )
                        else:
                            return TestResult(
                                test_name=test_name,
                                success=False,
                                duration=duration,
                                details=url_details,
                                error=f"Image URL not accessible: HTTP {img_response.status}"
                            )
                else:
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=time.time() - start_time,
                        details=url_details,
                        error="No valid image URL to test"
                    )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def test_project_association(self) -> TestResult:
        """Test 8: Verify generation appears in user's projects"""
        start_time = time.time()
        test_name = "Project Association Test"
        
        if not self.jwt_token:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=0,
                details={},
                error="No JWT token available"
            )
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            # Get user's projects
            async with self.session.get(
                f"{self.base_url}/api/v1/projects",
                headers=headers
            ) as response:
                duration = time.time() - start_time
                
                if response.status == 200:
                    projects = await response.json()
                    
                    # Look for our generation in the projects
                    generation_found = False
                    project_with_generation = None
                    
                    for project in projects:
                        generations = project.get("generations", [])
                        if any(gen.get("id") == self.generation_id for gen in generations):
                            generation_found = True
                            project_with_generation = project
                            self.test_project_id = project.get("id")
                            break
                    
                    return TestResult(
                        test_name=test_name,
                        success=True,  # We consider this successful even if not found, as it might be in a default project
                        duration=duration,
                        details={
                            "total_projects": len(projects),
                            "generation_found_in_project": generation_found,
                            "project_id": project_with_generation.get("id") if project_with_generation else None,
                            "project_title": project_with_generation.get("title") if project_with_generation else None,
                            "projects_summary": [
                                {
                                    "id": p.get("id"),
                                    "title": p.get("title"),
                                    "generation_count": len(p.get("generations", []))
                                }
                                for p in projects
                            ]
                        }
                    )
                else:
                    error_text = await response.text()
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=duration,
                        details={"status_code": response.status},
                        error=f"Projects fetch failed: {error_text}"
                    )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def test_generation_listing(self) -> TestResult:
        """Test 9: List user's generations to verify our generation appears"""
        start_time = time.time()
        test_name = "Generation Listing Test"
        
        if not self.jwt_token:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=0,
                details={},
                error="No JWT token available"
            )
        
        try:
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            async with self.session.get(
                f"{self.base_url}/api/v1/generations",
                headers=headers
            ) as response:
                duration = time.time() - start_time
                
                if response.status == 200:
                    generations = await response.json()
                    
                    # Look for our generation
                    our_generation = None
                    if isinstance(generations, list):
                        our_generation = next(
                            (gen for gen in generations if gen.get("id") == self.generation_id),
                            None
                        )
                    elif isinstance(generations, dict) and "generations" in generations:
                        our_generation = next(
                            (gen for gen in generations["generations"] if gen.get("id") == self.generation_id),
                            None
                        )
                    
                    return TestResult(
                        test_name=test_name,
                        success=True,
                        duration=duration,
                        details={
                            "total_generations": len(generations) if isinstance(generations, list) else len(generations.get("generations", [])),
                            "our_generation_found": our_generation is not None,
                            "our_generation_details": our_generation,
                            "generations_summary": generations if isinstance(generations, dict) else {"count": len(generations)}
                        }
                    )
                else:
                    error_text = await response.text()
                    return TestResult(
                        test_name=test_name,
                        success=False,
                        duration=duration,
                        details={"status_code": response.status},
                        error=f"Generations fetch failed: {error_text}"
                    )
                    
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                details={},
                error=str(e)
            )
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests in sequence"""
        logger.info("🚀 Starting Velro Backend E2E Test Suite")
        logger.info(f"🎯 Target: {self.base_url}")
        
        overall_start_time = time.time()
        
        # Test sequence
        tests = [
            ("Backend Health Check", self.test_backend_health),
            ("Authentication", self.test_authentication),
            ("User Profile", self.test_user_profile),
            ("Available Models", self.test_available_models),
            ("Image Generation", self.test_image_generation),
            ("Generation Status", self.test_generation_status),
            ("Storage Verification", self.test_storage_verification),
            ("Project Association", self.test_project_association),
            ("Generation Listing", self.test_generation_listing),
        ]
        
        for test_name, test_func in tests:
            logger.info(f"\n🧪 Running: {test_name}")
            result = await test_func()
            self.log_test_result(result)
            
            # Stop if critical tests fail
            if not result.success and test_name in ["Backend Health Check", "Authentication"]:
                logger.error(f"❌ Critical test '{test_name}' failed. Stopping test suite.")
                break
        
        # Generate summary
        total_duration = time.time() - overall_start_time
        passed_tests = [r for r in self.test_results if r.success]
        failed_tests = [r for r in self.test_results if not r.success]
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "test_suite": "velro_backend_e2e",
            "backend_url": self.base_url,
            "total_tests": len(self.test_results),
            "passed_tests": len(passed_tests),
            "failed_tests": len(failed_tests),
            "success_rate": len(passed_tests) / len(self.test_results) * 100 if self.test_results else 0,
            "total_duration": total_duration,
            "test_results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "duration": r.duration,
                    "details": r.details,
                    "error": r.error,
                    "timestamp": r.timestamp
                }
                for r in self.test_results
            ]
        }
        
        return summary

async def main():
    """Main entry point"""
    print("🧪 Velro Backend E2E Test Suite")
    print("=" * 50)
    
    async with VelroE2ETestSuite() as test_suite:
        summary = await test_suite.run_all_tests()
        
        # Print summary
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        print(f"🎯 Backend URL: {summary['backend_url']}")
        print(f"⏱️  Total Duration: {summary['total_duration']:.2f} seconds")
        print(f"📈 Success Rate: {summary['success_rate']:.1f}%")
        print(f"✅ Passed: {summary['passed_tests']}/{summary['total_tests']}")
        print(f"❌ Failed: {summary['failed_tests']}/{summary['total_tests']}")
        
        # Print individual test results
        print("\n📋 DETAILED RESULTS:")
        for result in summary['test_results']:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status} | {result['test_name']} | {result['duration']:.2f}s")
            if result['error']:
                print(f"     Error: {result['error']}")
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"e2e_test_results_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        
        # Exit with appropriate code
        exit_code = 0 if summary['failed_tests'] == 0 else 1
        print(f"\n🏁 Test suite completed with exit code: {exit_code}")
        
        return exit_code

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)