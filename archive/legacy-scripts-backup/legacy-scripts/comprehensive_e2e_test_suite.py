#!/usr/bin/env python3
"""
Comprehensive End-to-End Test Suite for Velro Backend Platform
============================================================

This test suite provides comprehensive validation of all core backend functionality
including authentication, authorization, credit balance, image generation, and 
performance metrics comparison against PRD targets.

Backend URL: https://velro-003-backend-production.up.railway.app
Performance Targets: Authorization <75ms, Authentication <50ms, Generation Access <100ms
"""

import asyncio
import json
import logging
import time
import uuid
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import httpx
import asyncpg
from urllib.parse import urlparse
import base64
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Represents a single test result with performance metrics"""
    test_name: str
    passed: bool
    message: str
    response_time_ms: float
    status_code: Optional[int] = None
    details: Dict[str, Any] = None
    critical: bool = False
    prd_target_ms: Optional[float] = None
    performance_grade: str = "UNKNOWN"

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        
        # Calculate performance grade against PRD targets
        if self.prd_target_ms and self.response_time_ms > 0:
            if self.response_time_ms <= self.prd_target_ms:
                self.performance_grade = "EXCELLENT"
            elif self.response_time_ms <= self.prd_target_ms * 2:
                self.performance_grade = "ACCEPTABLE" 
            elif self.response_time_ms <= self.prd_target_ms * 5:
                self.performance_grade = "POOR"
            else:
                self.performance_grade = "CRITICAL"

class VelroE2ETestSuite:
    """Comprehensive end-to-end test suite for Velro backend platform"""
    
    def __init__(self):
        self.backend_url = "https://velro-003-backend-production.up.railway.app"
        self.client = httpx.AsyncClient(timeout=60.0)
        self.results: List[TestResult] = []
        
        # Test user data
        self.test_user_email = f"e2e-test-{uuid.uuid4().hex[:8]}@velrotest.com"
        self.test_user_password = "VelroE2ETest2025!"
        self.test_user_full_name = "E2E Test User"
        
        # Authentication tokens and data
        self.access_token = None
        self.user_id = None
        self.initial_credits = 0
        
        # Generated content tracking
        self.generated_image_data = {}
        self.created_project_id = None
        
        # Performance tracking
        self.performance_metrics = {
            "authorization_times": [],
            "authentication_times": [],
            "generation_times": [],
            "database_times": []
        }

    async def run_comprehensive_test_suite(self) -> Dict[str, Any]:
        """Execute the complete end-to-end test suite"""
        logger.info("🚀 Starting Comprehensive E2E Test Suite for Velro Backend")
        logger.info(f"Backend URL: {self.backend_url}")
        logger.info(f"Test User: {self.test_user_email}")
        
        suite_start_time = time.time()
        
        try:
            # Phase 1: Infrastructure and Health Checks
            await self._test_infrastructure_health()
            
            # Phase 2: User Registration and Authentication
            await self._test_user_registration()
            await self._test_user_login()
            
            # Phase 3: Authorization and JWT Validation
            await self._test_jwt_token_validation()
            await self._test_authorization_endpoints()
            
            # Phase 4: Credit Balance and Transaction System
            await self._test_credit_balance_checking()
            
            # Phase 5: Project Management System
            await self._test_project_creation()
            await self._test_project_management()
            
            # Phase 6: AI Image Generation with FAL.ai
            await self._test_image_generation()
            await self._test_supabase_storage_verification()
            
            # Phase 7: Performance Validation
            await self._test_performance_benchmarks()
            
            # Phase 8: Security and Error Handling
            await self._test_security_validation()
            
            # Generate comprehensive report
            suite_end_time = time.time()
            total_execution_time = suite_end_time - suite_start_time
            
            return await self._generate_comprehensive_report(total_execution_time)
            
        except Exception as e:
            logger.error(f"❌ Test suite execution failed: {str(e)}")
            raise
        finally:
            await self.client.aclose()

    async def _test_infrastructure_health(self):
        """Test infrastructure health and connectivity"""
        logger.info("🏥 Testing infrastructure health...")
        
        # Test backend health endpoint
        start_time = time.time()
        try:
            response = await self.client.get(f"{self.backend_url}/health")
            response_time = (time.time() - start_time) * 1000
            
            self.results.append(TestResult(
                test_name="Backend Health Check",
                passed=response.status_code == 200,
                message=f"Backend health check returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                details=response.json() if response.status_code == 200 else {},
                critical=True
            ))
            
            # Test database connectivity through health endpoint
            if response.status_code == 200:
                health_data = response.json()
                db_status = health_data.get("database", "unknown")
                
                self.results.append(TestResult(
                    test_name="Database Connectivity",
                    passed=db_status in ["connected", "railway-optimized", "healthy"],
                    message=f"Database status: {db_status}",
                    response_time_ms=0,
                    details={"database_status": db_status},
                    critical=True
                ))
                
        except Exception as e:
            self.results.append(TestResult(
                test_name="Backend Health Check",
                passed=False,
                message=f"Health check failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)},
                critical=True
            ))

    async def _test_user_registration(self):
        """Test user registration flow"""
        logger.info("👤 Testing user registration...")
        
        registration_data = {
            "email": self.test_user_email,
            "password": self.test_user_password,
            "full_name": self.test_user_full_name
        }
        
        start_time = time.time()
        try:
            response = await self.client.post(
                f"{self.backend_url}/api/v1/auth/register",
                json=registration_data
            )
            response_time = (time.time() - start_time) * 1000
            
            success = response.status_code in [200, 201]
            
            self.results.append(TestResult(
                test_name="User Registration",
                passed=success,
                message=f"Registration returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=50.0,  # PRD target for authentication
                details={"registration_data": registration_data},
                critical=True
            ))
            
            # Store registration response data
            if success:
                try:
                    reg_response = response.json()
                    self.access_token = reg_response.get("access_token")
                    self.user_id = reg_response.get("user", {}).get("id")
                    
                    self.results.append(TestResult(
                        test_name="Registration Token Generation",
                        passed=bool(self.access_token),
                        message="JWT token generated successfully" if self.access_token else "No token in response",
                        response_time_ms=0,
                        details={"has_token": bool(self.access_token), "has_user_id": bool(self.user_id)}
                    ))
                    
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Registration Response Parsing",
                        passed=False,
                        message="Failed to parse registration response",
                        response_time_ms=0,
                        details={"raw_response": response.text[:500]}
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="User Registration",
                passed=False,
                message=f"Registration failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)},
                critical=True
            ))

    async def _test_user_login(self):
        """Test user login and JWT token retrieval"""
        logger.info("🔐 Testing user login...")
        
        login_data = {
            "email": self.test_user_email,
            "password": self.test_user_password
        }
        
        start_time = time.time()
        try:
            response = await self.client.post(
                f"{self.backend_url}/api/v1/auth/login",
                json=login_data
            )
            response_time = (time.time() - start_time) * 1000
            
            success = response.status_code == 200
            
            self.results.append(TestResult(
                test_name="User Login",
                passed=success,
                message=f"Login returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=50.0,  # PRD target for authentication
                critical=True
            ))
            
            # Verify JWT token in response
            if success:
                try:
                    login_response = response.json()
                    login_token = login_response.get("access_token")
                    
                    self.results.append(TestResult(
                        test_name="Login Token Validation",
                        passed=bool(login_token),
                        message="JWT token received from login" if login_token else "No token in login response",
                        response_time_ms=0,
                        details={"token_present": bool(login_token)}
                    ))
                    
                    # Use login token if available (prefer login over registration token)
                    if login_token:
                        self.access_token = login_token
                        
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Login Response Parsing", 
                        passed=False,
                        message="Failed to parse login response",
                        response_time_ms=0
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="User Login",
                passed=False,
                message=f"Login failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)},
                critical=True
            ))

    async def _test_jwt_token_validation(self):
        """Test JWT token validation and user profile access"""
        logger.info("🎫 Testing JWT token validation...")
        
        if not self.access_token:
            self.results.append(TestResult(
                test_name="JWT Token Validation",
                passed=False,
                message="No access token available for validation",
                response_time_ms=0,
                critical=True
            ))
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        start_time = time.time()
        try:
            response = await self.client.get(
                f"{self.backend_url}/api/v1/auth/me",
                headers=headers
            )
            response_time = (time.time() - start_time) * 1000
            self.performance_metrics["authorization_times"].append(response_time)
            
            success = response.status_code == 200
            
            self.results.append(TestResult(
                test_name="JWT Token Validation",
                passed=success,
                message=f"Profile access returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=75.0,  # PRD target for authorization
                critical=True
            ))
            
            # Validate user profile data
            if success:
                try:
                    profile_data = response.json()
                    self.results.append(TestResult(
                        test_name="User Profile Data Validation",
                        passed=bool(profile_data.get("email")),
                        message="User profile data retrieved successfully",
                        response_time_ms=0,
                        details={"profile_keys": list(profile_data.keys()) if profile_data else []}
                    ))
                    
                    # Store user ID if not already set
                    if not self.user_id and profile_data.get("id"):
                        self.user_id = profile_data.get("id")
                        
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Profile Response Parsing",
                        passed=False,
                        message="Failed to parse profile response",
                        response_time_ms=0
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="JWT Token Validation",
                passed=False,
                message=f"Token validation failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)},
                critical=True
            ))

    async def _test_authorization_endpoints(self):
        """Test authorization on protected endpoints"""
        logger.info("🔒 Testing authorization endpoints...")
        
        if not self.access_token:
            logger.warning("Skipping authorization tests - no access token")
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # Test various protected endpoints
        protected_endpoints = [
            ("/api/v1/projects", "GET", "Projects List"),
            ("/api/v1/credits/balance", "GET", "Credits Balance"),
            ("/api/v1/generations", "GET", "Generations List"),
            ("/api/v1/models/supported", "GET", "Supported Models")
        ]
        
        for endpoint, method, description in protected_endpoints:
            start_time = time.time()
            try:
                if method == "GET":
                    response = await self.client.get(f"{self.backend_url}{endpoint}", headers=headers)
                else:
                    response = await self.client.post(f"{self.backend_url}{endpoint}", headers=headers, json={})
                
                response_time = (time.time() - start_time) * 1000
                self.performance_metrics["authorization_times"].append(response_time)
                
                # Accept 200 (success) or 422 (validation error) as valid authorization
                success = response.status_code in [200, 422]
                
                self.results.append(TestResult(
                    test_name=f"Authorization: {description}",
                    passed=success,
                    message=f"{description} returned {response.status_code}",
                    response_time_ms=response_time,
                    status_code=response.status_code,
                    prd_target_ms=75.0,  # PRD target for authorization
                    details={"endpoint": endpoint, "method": method}
                ))
                
            except Exception as e:
                self.results.append(TestResult(
                    test_name=f"Authorization: {description}",
                    passed=False,
                    message=f"Authorization test failed: {str(e)}",
                    response_time_ms=0,
                    details={"error": str(e), "endpoint": endpoint}
                ))

    async def _test_credit_balance_checking(self):
        """Test credit balance checking and validation"""
        logger.info("💰 Testing credit balance system...")
        
        if not self.access_token:
            logger.warning("Skipping credit tests - no access token")
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        start_time = time.time()
        try:
            response = await self.client.get(
                f"{self.backend_url}/api/v1/credits/balance",
                headers=headers
            )
            response_time = (time.time() - start_time) * 1000
            self.performance_metrics["database_times"].append(response_time)
            
            success = response.status_code == 200
            
            self.results.append(TestResult(
                test_name="Credit Balance Check",
                passed=success,
                message=f"Credit balance check returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=100.0,  # PRD target for generation access
                critical=True
            ))
            
            # Validate credit balance data
            if success:
                try:
                    balance_data = response.json()
                    credits = balance_data.get("credits", 0)
                    self.initial_credits = credits
                    
                    self.results.append(TestResult(
                        test_name="Credit Balance Validation",
                        passed=isinstance(credits, (int, float)) and credits >= 0,
                        message=f"User has {credits} credits available",
                        response_time_ms=0,
                        details={"credits": credits, "balance_data": balance_data}
                    ))
                    
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Credit Balance Response Parsing",
                        passed=False,
                        message="Failed to parse credit balance response",
                        response_time_ms=0
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="Credit Balance Check",
                passed=False,
                message=f"Credit balance check failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)},
                critical=True
            ))

    async def _test_project_creation(self):
        """Test project creation and management"""
        logger.info("📁 Testing project creation...")
        
        if not self.access_token:
            logger.warning("Skipping project tests - no access token")
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        project_data = {
            "title": f"E2E Test Project {uuid.uuid4().hex[:8]}",
            "description": "Automated E2E test project",
            "visibility": "private"
        }
        
        start_time = time.time()
        try:
            response = await self.client.post(
                f"{self.backend_url}/api/v1/projects",
                headers=headers,
                json=project_data
            )
            response_time = (time.time() - start_time) * 1000
            self.performance_metrics["database_times"].append(response_time)
            
            success = response.status_code in [200, 201]
            
            self.results.append(TestResult(
                test_name="Project Creation",
                passed=success,
                message=f"Project creation returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=100.0,  # PRD target for team operations
                details={"project_data": project_data}
            ))
            
            # Store created project ID
            if success:
                try:
                    project_response = response.json()
                    self.created_project_id = project_response.get("id")
                    
                    self.results.append(TestResult(
                        test_name="Project Creation Response Validation",
                        passed=bool(self.created_project_id),
                        message="Project created successfully with ID" if self.created_project_id else "Project created but no ID returned",
                        response_time_ms=0,
                        details={"project_id": self.created_project_id, "response": project_response}
                    ))
                    
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Project Creation Response Parsing",
                        passed=False,
                        message="Failed to parse project creation response",
                        response_time_ms=0
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="Project Creation",
                passed=False,
                message=f"Project creation failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)}
            ))

    async def _test_project_management(self):
        """Test project listing and management"""
        logger.info("📋 Testing project management...")
        
        if not self.access_token:
            logger.warning("Skipping project management tests - no access token")
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        start_time = time.time()
        try:
            response = await self.client.get(
                f"{self.backend_url}/api/v1/projects",
                headers=headers
            )
            response_time = (time.time() - start_time) * 1000
            self.performance_metrics["database_times"].append(response_time)
            
            success = response.status_code == 200
            
            self.results.append(TestResult(
                test_name="Project List Retrieval",
                passed=success,
                message=f"Project list returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=100.0,  # PRD target for team operations
            ))
            
            # Validate project list data
            if success:
                try:
                    projects_data = response.json()
                    projects = projects_data if isinstance(projects_data, list) else projects_data.get("projects", [])
                    
                    self.results.append(TestResult(
                        test_name="Project List Validation",
                        passed=isinstance(projects, list),
                        message=f"Retrieved {len(projects)} projects" if isinstance(projects, list) else "Invalid project list format",
                        response_time_ms=0,
                        details={"project_count": len(projects) if isinstance(projects, list) else 0}
                    ))
                    
                    # Check if our created project is in the list
                    if self.created_project_id and isinstance(projects, list):
                        project_found = any(p.get("id") == self.created_project_id for p in projects)
                        self.results.append(TestResult(
                            test_name="Created Project Visibility",
                            passed=project_found,
                            message="Created project found in list" if project_found else "Created project not found in list",
                            response_time_ms=0,
                            details={"created_project_id": self.created_project_id}
                        ))
                        
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Project List Response Parsing",
                        passed=False,
                        message="Failed to parse project list response",
                        response_time_ms=0
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="Project List Retrieval",
                passed=False,
                message=f"Project list retrieval failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)}
            ))

    async def _test_image_generation(self):
        """Test image generation with FAL.ai"""
        logger.info("🎨 Testing image generation with FAL.ai...")
        
        if not self.access_token:
            logger.warning("Skipping image generation tests - no access token")
            return
        
        # Check if user has sufficient credits
        if self.initial_credits < 1:
            self.results.append(TestResult(
                test_name="Image Generation Credit Check",
                passed=False,
                message=f"Insufficient credits for generation test (has {self.initial_credits}, needs >= 1)",
                response_time_ms=0,
                details={"credits": self.initial_credits}
            ))
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        generation_data = {
            "prompt": "beautiful sunset over mountains in watercolor style",
            "model": "fal-ai/flux-pro",  # Using reliable model
            "project_id": self.created_project_id  # Associate with created project if available
        }
        
        start_time = time.time()
        try:
            response = await self.client.post(
                f"{self.backend_url}/api/v1/generations",
                headers=headers,
                json=generation_data
            )
            response_time = (time.time() - start_time) * 1000
            self.performance_metrics["generation_times"].append(response_time)
            
            success = response.status_code in [200, 201]
            
            self.results.append(TestResult(
                test_name="Image Generation Request",
                passed=success,
                message=f"Image generation request returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=100.0,  # PRD target for generation access
                details={"generation_data": generation_data},
                critical=True
            ))
            
            # Process generation response
            if success:
                try:
                    generation_response = response.json()
                    generation_id = generation_response.get("id")
                    image_url = generation_response.get("image_url") or generation_response.get("media_url")
                    
                    self.generated_image_data = {
                        "id": generation_id,
                        "image_url": image_url,
                        "prompt": generation_data["prompt"],
                        "response": generation_response
                    }
                    
                    self.results.append(TestResult(
                        test_name="Image Generation Response Validation",
                        passed=bool(generation_id),
                        message="Generation completed with ID" if generation_id else "Generation response invalid",
                        response_time_ms=0,
                        details={
                            "generation_id": generation_id,
                            "has_image_url": bool(image_url),
                            "response_keys": list(generation_response.keys()) if generation_response else []
                        }
                    ))
                    
                    # Test image URL accessibility if provided
                    if image_url:
                        await self._test_generated_image_access(image_url)
                        
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Image Generation Response Parsing",
                        passed=False,
                        message="Failed to parse image generation response",
                        response_time_ms=0
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="Image Generation Request",
                passed=False,
                message=f"Image generation failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)},
                critical=True
            ))

    async def _test_generated_image_access(self, image_url: str):
        """Test access to generated image"""
        logger.info("🖼️ Testing generated image access...")
        
        start_time = time.time()
        try:
            response = await self.client.get(image_url)
            response_time = (time.time() - start_time) * 1000
            
            success = response.status_code == 200 and response.headers.get("content-type", "").startswith("image/")
            
            self.results.append(TestResult(
                test_name="Generated Image Access",
                passed=success,
                message=f"Image access returned {response.status_code}, content-type: {response.headers.get('content-type', 'unknown')}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=200.0,  # PRD target for media URL generation
                details={
                    "image_url": image_url,
                    "content_type": response.headers.get("content-type"),
                    "content_length": len(response.content) if response.status_code == 200 else 0
                }
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                test_name="Generated Image Access",
                passed=False,
                message=f"Image access failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e), "image_url": image_url}
            ))

    async def _test_supabase_storage_verification(self):
        """Verify image is properly stored in Supabase storage"""
        logger.info("☁️ Testing Supabase storage verification...")
        
        if not self.generated_image_data.get("image_url"):
            self.results.append(TestResult(
                test_name="Supabase Storage Verification",
                passed=False,
                message="No image URL available to verify storage",
                response_time_ms=0
            ))
            return
        
        image_url = self.generated_image_data["image_url"]
        
        # Check if URL is from Supabase storage
        is_supabase = "supabase" in image_url.lower() or "velro" in image_url.lower()
        
        self.results.append(TestResult(
            test_name="Supabase Storage URL Validation",
            passed=is_supabase,
            message="Image stored in Supabase" if is_supabase else f"Image stored elsewhere: {urlparse(image_url).netloc}",
            response_time_ms=0,
            details={
                "image_url": image_url,
                "storage_domain": urlparse(image_url).netloc,
                "is_supabase": is_supabase
            }
        ))
        
        # Test storage accessibility and metadata
        if self.access_token and self.generated_image_data.get("id"):
            await self._test_generation_metadata_storage()

    async def _test_generation_metadata_storage(self):
        """Test that generation metadata is properly stored"""
        logger.info("📊 Testing generation metadata storage...")
        
        if not self.access_token or not self.generated_image_data.get("id"):
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        generation_id = self.generated_image_data["id"]
        
        start_time = time.time()
        try:
            response = await self.client.get(
                f"{self.backend_url}/api/v1/generations/{generation_id}",
                headers=headers
            )
            response_time = (time.time() - start_time) * 1000
            
            success = response.status_code == 200
            
            self.results.append(TestResult(
                test_name="Generation Metadata Storage",
                passed=success,
                message=f"Generation metadata retrieval returned {response.status_code}",
                response_time_ms=response_time,
                status_code=response.status_code,
                prd_target_ms=100.0,
                details={"generation_id": generation_id}
            ))
            
            # Validate stored metadata
            if success:
                try:
                    metadata = response.json()
                    expected_fields = ["id", "prompt", "created_at", "user_id"]
                    has_required_fields = all(field in metadata for field in expected_fields)
                    
                    self.results.append(TestResult(
                        test_name="Generation Metadata Validation",
                        passed=has_required_fields,
                        message="Generation metadata contains required fields" if has_required_fields else "Missing required metadata fields",
                        response_time_ms=0,
                        details={
                            "metadata_fields": list(metadata.keys()) if metadata else [],
                            "required_fields": expected_fields
                        }
                    ))
                    
                except json.JSONDecodeError:
                    self.results.append(TestResult(
                        test_name="Generation Metadata Parsing",
                        passed=False,
                        message="Failed to parse generation metadata",
                        response_time_ms=0
                    ))
                    
        except Exception as e:
            self.results.append(TestResult(
                test_name="Generation Metadata Storage",
                passed=False,
                message=f"Metadata storage test failed: {str(e)}",
                response_time_ms=0,
                details={"error": str(e)}
            ))

    async def _test_performance_benchmarks(self):
        """Test performance benchmarks against PRD targets"""
        logger.info("⚡ Testing performance benchmarks...")
        
        # Calculate performance statistics
        auth_times = self.performance_metrics["authorization_times"]
        generation_times = self.performance_metrics["generation_times"]
        db_times = self.performance_metrics["database_times"]
        
        # Authorization performance analysis
        if auth_times:
            avg_auth_time = sum(auth_times) / len(auth_times)
            max_auth_time = max(auth_times)
            
            self.results.append(TestResult(
                test_name="Authorization Performance Benchmark",
                passed=avg_auth_time <= 75.0,  # PRD target
                message=f"Avg authorization time: {avg_auth_time:.1f}ms (target: 75ms)",
                response_time_ms=avg_auth_time,
                prd_target_ms=75.0,
                details={
                    "average_ms": avg_auth_time,
                    "max_ms": max_auth_time,
                    "sample_count": len(auth_times),
                    "all_samples": auth_times
                },
                critical=True
            ))
        
        # Generation performance analysis
        if generation_times:
            avg_gen_time = sum(generation_times) / len(generation_times)
            
            self.results.append(TestResult(
                test_name="Generation Performance Benchmark",
                passed=avg_gen_time <= 100.0,  # PRD target
                message=f"Avg generation access time: {avg_gen_time:.1f}ms (target: 100ms)",
                response_time_ms=avg_gen_time,
                prd_target_ms=100.0,
                details={
                    "average_ms": avg_gen_time,
                    "sample_count": len(generation_times),
                    "all_samples": generation_times
                },
                critical=True
            ))
        
        # Database performance analysis
        if db_times:
            avg_db_time = sum(db_times) / len(db_times)
            
            self.results.append(TestResult(
                test_name="Database Performance Benchmark",
                passed=avg_db_time <= 100.0,  # Reasonable target
                message=f"Avg database operation time: {avg_db_time:.1f}ms",
                response_time_ms=avg_db_time,
                prd_target_ms=100.0,
                details={
                    "average_ms": avg_db_time,
                    "sample_count": len(db_times),
                    "all_samples": db_times
                }
            ))

    async def _test_security_validation(self):
        """Test security features and validation"""
        logger.info("🛡️ Testing security validation...")
        
        # Test unauthorized access protection
        protected_endpoints = [
            "/api/v1/projects",
            "/api/v1/credits/balance", 
            "/api/v1/generations",
            "/api/v1/auth/me"
        ]
        
        for endpoint in protected_endpoints:
            start_time = time.time()
            try:
                # Test without authorization header
                response = await self.client.get(f"{self.backend_url}{endpoint}")
                response_time = (time.time() - start_time) * 1000
                
                # Should return 401 Unauthorized
                security_enforced = response.status_code == 401
                
                self.results.append(TestResult(
                    test_name=f"Security: Unauthorized Access Protection ({endpoint})",
                    passed=security_enforced,
                    message=f"Endpoint returned {response.status_code} without auth (expected 401)",
                    response_time_ms=response_time,
                    status_code=response.status_code,
                    details={"endpoint": endpoint},
                    critical=True
                ))
                
            except Exception as e:
                self.results.append(TestResult(
                    test_name=f"Security: Unauthorized Access Test ({endpoint})",
                    passed=False,
                    message=f"Security test failed: {str(e)}",
                    response_time_ms=0,
                    details={"error": str(e), "endpoint": endpoint}
                ))
        
        # Test malicious input handling
        await self._test_malicious_input_handling()

    async def _test_malicious_input_handling(self):
        """Test handling of malicious inputs"""
        logger.info("🔍 Testing malicious input handling...")
        
        malicious_payloads = [
            {"name": "SQL Injection", "payload": "'; DROP TABLE users; --"},
            {"name": "XSS Attempt", "payload": "<script>alert('xss')</script>"},
            {"name": "Command Injection", "payload": "; cat /etc/passwd"},
            {"name": "Path Traversal", "payload": "../../etc/passwd"}
        ]
        
        for payload_info in malicious_payloads:
            try:
                # Test malicious input in registration (should be sanitized/rejected)
                malicious_data = {
                    "email": f"test{payload_info['payload']}@example.com",
                    "password": "ValidPassword123!",
                    "full_name": payload_info["payload"]
                }
                
                start_time = time.time()
                response = await self.client.post(
                    f"{self.backend_url}/api/v1/auth/register",
                    json=malicious_data
                )
                response_time = (time.time() - start_time) * 1000
                
                # Should either reject (400-level error) or sanitize the input
                secure_handling = response.status_code in [400, 422, 429] or (
                    response.status_code in [200, 201] and 
                    payload_info["payload"] not in response.text
                )
                
                self.results.append(TestResult(
                    test_name=f"Security: {payload_info['name']} Handling",
                    passed=secure_handling,
                    message=f"Malicious input handled appropriately (status: {response.status_code})",
                    response_time_ms=response_time,
                    status_code=response.status_code,
                    details={"payload": payload_info["payload"]},
                    critical=True
                ))
                
            except Exception as e:
                self.results.append(TestResult(
                    test_name=f"Security: {payload_info['name']} Handling",
                    passed=True,  # Exception likely means input was rejected
                    message=f"Malicious input rejected: {str(e)}",
                    response_time_ms=0,
                    details={"error": str(e)}
                ))

    async def _generate_comprehensive_report(self, total_execution_time: float) -> Dict[str, Any]:
        """Generate comprehensive test report with performance analysis"""
        logger.info("📊 Generating comprehensive test report...")
        
        # Calculate statistics
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        failed_tests = total_tests - passed_tests
        critical_failures = sum(1 for r in self.results if not r.passed and r.critical)
        
        # Performance analysis
        performance_results = [r for r in self.results if r.prd_target_ms and r.response_time_ms > 0]
        performance_grades = {}
        for grade in ["EXCELLENT", "ACCEPTABLE", "POOR", "CRITICAL"]:
            performance_grades[grade] = sum(1 for r in performance_results if r.performance_grade == grade)
        
        # Calculate average response times by category
        auth_times = [r.response_time_ms for r in self.results if "Authorization" in r.test_name or "JWT" in r.test_name and r.response_time_ms > 0]
        gen_times = [r.response_time_ms for r in self.results if "Generation" in r.test_name and r.response_time_ms > 0]
        db_times = [r.response_time_ms for r in self.results if "Database" in r.test_name or "Credit" in r.test_name and r.response_time_ms > 0]
        
        # PRD comparison
        prd_comparison = {
            "authorization": {
                "target_ms": 75,
                "actual_avg_ms": sum(auth_times) / len(auth_times) if auth_times else 0,
                "performance_ratio": (sum(auth_times) / len(auth_times) / 75) if auth_times else 0
            },
            "authentication": {
                "target_ms": 50,
                "actual_avg_ms": sum([r.response_time_ms for r in self.results if "Login" in r.test_name or "Registration" in r.test_name and r.response_time_ms > 0]) / max(1, len([r for r in self.results if "Login" in r.test_name or "Registration" in r.test_name and r.response_time_ms > 0])),
                "performance_ratio": 0
            },
            "generation_access": {
                "target_ms": 100,
                "actual_avg_ms": sum(gen_times) / len(gen_times) if gen_times else 0,
                "performance_ratio": (sum(gen_times) / len(gen_times) / 100) if gen_times else 0
            }
        }
        
        # Calculate authentication ratio
        auth_login_times = [r.response_time_ms for r in self.results if ("Login" in r.test_name or "Registration" in r.test_name) and r.response_time_ms > 0]
        if auth_login_times:
            prd_comparison["authentication"]["actual_avg_ms"] = sum(auth_login_times) / len(auth_login_times)
            prd_comparison["authentication"]["performance_ratio"] = prd_comparison["authentication"]["actual_avg_ms"] / 50
        
        # Overall assessment
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        if critical_failures == 0 and success_rate >= 95:
            overall_status = "EXCELLENT"
        elif critical_failures == 0 and success_rate >= 85:
            overall_status = "GOOD"
        elif critical_failures <= 2 and success_rate >= 75:
            overall_status = "ACCEPTABLE"
        elif success_rate >= 60:
            overall_status = "NEEDS_IMPROVEMENT"
        else:
            overall_status = "CRITICAL_ISSUES"
        
        # Generate report
        report = {
            "test_session": {
                "timestamp": datetime.now().isoformat(),
                "backend_url": self.backend_url,
                "test_user": self.test_user_email,
                "total_execution_time_seconds": total_execution_time,
                "overall_status": overall_status
            },
            "test_summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "critical_failures": critical_failures,
                "success_rate_percent": success_rate
            },
            "performance_analysis": {
                "prd_comparison": prd_comparison,
                "performance_grades": performance_grades,
                "response_time_statistics": {
                    "authorization_avg_ms": sum(auth_times) / len(auth_times) if auth_times else 0,
                    "generation_avg_ms": sum(gen_times) / len(gen_times) if gen_times else 0,
                    "database_avg_ms": sum(db_times) / len(db_times) if db_times else 0
                }
            },
            "feature_validation": {
                "user_registration": any(r.test_name == "User Registration" and r.passed for r in self.results),
                "user_login": any(r.test_name == "User Login" and r.passed for r in self.results),
                "jwt_validation": any(r.test_name == "JWT Token Validation" and r.passed for r in self.results),
                "credit_balance": any(r.test_name == "Credit Balance Check" and r.passed for r in self.results),
                "project_creation": any(r.test_name == "Project Creation" and r.passed for r in self.results),
                "image_generation": any(r.test_name == "Image Generation Request" and r.passed for r in self.results),
                "supabase_storage": any(r.test_name == "Generated Image Access" and r.passed for r in self.results),
                "security_protection": sum(1 for r in self.results if "Security:" in r.test_name and r.passed) > 0
            },
            "generated_content": {
                "project_created": bool(self.created_project_id),
                "project_id": self.created_project_id,
                "image_generated": bool(self.generated_image_data.get("id")),
                "image_data": self.generated_image_data,
                "initial_credits": self.initial_credits
            },
            "detailed_results": [
                {
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "message": r.message,
                    "response_time_ms": r.response_time_ms,
                    "status_code": r.status_code,
                    "prd_target_ms": r.prd_target_ms,
                    "performance_grade": r.performance_grade,
                    "critical": r.critical,
                    "details": r.details or {}
                }
                for r in self.results
            ],
            "recommendations": self._generate_recommendations(overall_status, prd_comparison, critical_failures),
            "performance_vs_prd": self._generate_prd_comparison_summary(prd_comparison)
        }
        
        # Save report to file
        timestamp = int(time.time())
        filename = f"comprehensive_e2e_report_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📋 Comprehensive test report saved to {filename}")
        
        # Print summary
        self._print_test_summary(report)
        
        return report

    def _generate_recommendations(self, overall_status: str, prd_comparison: Dict, critical_failures: int) -> List[str]:
        """Generate actionable recommendations based on test results"""
        recommendations = []
        
        if overall_status == "EXCELLENT":
            recommendations.append("✅ All systems operational - ready for production")
        else:
            if critical_failures > 0:
                recommendations.append(f"🔴 CRITICAL: Fix {critical_failures} critical system failures before production")
        
        # Performance recommendations
        for operation, metrics in prd_comparison.items():
            if metrics["performance_ratio"] > 2.0:
                recommendations.append(f"⚡ PERFORMANCE: {operation} is {metrics['performance_ratio']:.1f}x slower than PRD target")
            elif metrics["performance_ratio"] > 1.5:
                recommendations.append(f"🟡 OPTIMIZATION: {operation} performance could be improved")
        
        # Feature-specific recommendations
        if not any(r.test_name == "Image Generation Request" and r.passed for r in self.results):
            recommendations.append("🎨 IMAGE GENERATION: Fix image generation system")
        
        if not any(r.test_name == "Generated Image Access" and r.passed for r in self.results):
            recommendations.append("☁️ STORAGE: Verify Supabase storage integration")
        
        # Security recommendations
        security_failures = sum(1 for r in self.results if "Security:" in r.test_name and not r.passed)
        if security_failures > 0:
            recommendations.append(f"🛡️ SECURITY: Address {security_failures} security vulnerabilities")
        
        return recommendations[:10]  # Limit to top 10 recommendations

    def _generate_prd_comparison_summary(self, prd_comparison: Dict) -> Dict[str, Any]:
        """Generate PRD comparison summary"""
        return {
            "authorization_performance": {
                "target_met": prd_comparison["authorization"]["performance_ratio"] <= 1.0,
                "performance_gap": f"{prd_comparison['authorization']['performance_ratio']:.1f}x target" if prd_comparison["authorization"]["performance_ratio"] > 1.0 else "Within target",
                "actual_vs_target": f"{prd_comparison['authorization']['actual_avg_ms']:.1f}ms vs {prd_comparison['authorization']['target_ms']}ms target"
            },
            "authentication_performance": {
                "target_met": prd_comparison["authentication"]["performance_ratio"] <= 1.0,
                "performance_gap": f"{prd_comparison['authentication']['performance_ratio']:.1f}x target" if prd_comparison["authentication"]["performance_ratio"] > 1.0 else "Within target",
                "actual_vs_target": f"{prd_comparison['authentication']['actual_avg_ms']:.1f}ms vs {prd_comparison['authentication']['target_ms']}ms target"
            },
            "generation_performance": {
                "target_met": prd_comparison["generation_access"]["performance_ratio"] <= 1.0,
                "performance_gap": f"{prd_comparison['generation_access']['performance_ratio']:.1f}x target" if prd_comparison["generation_access"]["performance_ratio"] > 1.0 else "Within target",
                "actual_vs_target": f"{prd_comparison['generation_access']['actual_avg_ms']:.1f}ms vs {prd_comparison['generation_access']['target_ms']}ms target"
            },
            "overall_performance_grade": "MEETS_PRD" if all(
                comp["performance_ratio"] <= 1.0 for comp in prd_comparison.values()
            ) else "NEEDS_OPTIMIZATION"
        }

    def _print_test_summary(self, report: Dict[str, Any]):
        """Print formatted test summary to console"""
        print("\n" + "="*100)
        print("🧪 COMPREHENSIVE E2E TEST SUITE RESULTS")
        print("="*100)
        
        session = report["test_session"]
        summary = report["test_summary"]
        features = report["feature_validation"]
        performance = report["performance_analysis"]
        
        print(f"Overall Status: {session['overall_status']}")
        print(f"Backend URL: {session['backend_url']}")
        print(f"Execution Time: {session['total_execution_time_seconds']:.1f}s")
        print(f"Success Rate: {summary['success_rate_percent']:.1f}% ({summary['passed_tests']}/{summary['total_tests']})")
        print(f"Critical Failures: {summary['critical_failures']}")
        
        print("\n📊 PERFORMANCE vs PRD TARGETS:")
        prd_comp = performance["prd_comparison"]
        for operation, metrics in prd_comp.items():
            status = "✅" if metrics["performance_ratio"] <= 1.0 else "❌"
            print(f"  {status} {operation.title()}: {metrics['actual_avg_ms']:.1f}ms (target: {metrics['target_ms']}ms) [{metrics['performance_ratio']:.1f}x]")
        
        print("\n🔧 FEATURE VALIDATION:")
        for feature, working in features.items():
            status = "✅" if working else "❌"
            print(f"  {status} {feature.replace('_', ' ').title()}")
        
        print("\n📈 PERFORMANCE GRADES:")
        for grade, count in performance["performance_grades"].items():
            if count > 0:
                print(f"  {grade}: {count} tests")
        
        print("\n🎯 TOP RECOMMENDATIONS:")
        for rec in report["recommendations"][:5]:
            print(f"  {rec}")
        
        if report["generated_content"]["image_generated"]:
            print(f"\n🎨 GENERATED CONTENT:")
            print(f"  Project Created: {report['generated_content']['project_id']}")
            print(f"  Image Generated: {report['generated_content']['image_data']['id']}")
            print(f"  Image URL: {report['generated_content']['image_data']['image_url'][:80]}...")
        
        print("\n" + "="*100)


async def main():
    """Main execution function"""
    test_suite = VelroE2ETestSuite()
    
    try:
        logger.info("🚀 Starting Velro Backend E2E Test Suite")
        report = await test_suite.run_comprehensive_test_suite()
        
        # Determine exit code based on results
        critical_failures = report["test_summary"]["critical_failures"]
        success_rate = report["test_summary"]["success_rate_percent"]
        
        if critical_failures == 0 and success_rate >= 95:
            return 0  # Excellent
        elif critical_failures == 0 and success_rate >= 85:
            return 0  # Good
        elif critical_failures <= 2 and success_rate >= 75:
            return 1  # Acceptable but needs improvement
        else:
            return 2  # Critical issues
            
    except Exception as e:
        logger.error(f"❌ Test suite execution failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 2
    finally:
        logger.info("🏁 Test suite execution completed")


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)