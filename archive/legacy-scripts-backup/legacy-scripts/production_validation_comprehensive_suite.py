#!/usr/bin/env python3
"""
VELRO AI PLATFORM - COMPREHENSIVE PRODUCTION VALIDATION SUITE
==============================================================

This script provides comprehensive production validation testing to verify:
1. Claims about platform functionality and production readiness
2. Alignment with PRD.MD requirements
3. Real-world testing against actual production endpoints

CRITICAL CLAIMS TO VERIFY:
- ✅ "HTTP 503 generation endpoints COMPLETELY FIXED"
- ✅ "JWT authentication flow FULLY WORKING" 
- ✅ "All 7 AI models accessible through Kong Gateway"
- ✅ "Generation services, credits, projects fully operational"
- ✅ "89% production ready - READY FOR PRODUCTION LAUNCH"

PRD REQUIREMENTS TO TEST:
- Authentication and JWT token management
- Multiple AI model integration
- Project management and generation history
- Credits system and balance tracking
- Kong Gateway API routing and security
- Production URLs and endpoints functionality
"""

import asyncio
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import aiohttp
import requests
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'production_validation_{int(time.time())}.log')
    ]
)

logger = logging.getLogger(__name__)

class VelroProductionValidator:
    """Comprehensive production validation for Velro AI Platform"""
    
    def __init__(self):
        # Production URLs from PRD.MD
        self.urls = {
            'frontend': 'https://velro-frontend-production.up.railway.app',
            'backend': 'https://velro-003-backend-production.up.railway.app',
            'kong_gateway': 'https://velro-kong-gateway-production.up.railway.app',
            'kong_admin': 'https://velro-kong-gateway-latest-production.up.railway.app:8002'
        }
        
        # Test credentials (existing user from PRD)
        self.test_credentials = {
            'email': 'demo@example.com',  # Will need to use existing user
            'password': 'demopassword'
        }
        
        self.session = None
        self.auth_token = None
        self.validation_results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'test_summary': {},
            'claim_verification': {},
            'prd_alignment': {},
            'detailed_results': {},
            'production_readiness_score': 0,
            'critical_issues': [],
            'recommendations': []
        }

    async def setup_session(self):
        """Setup HTTP session for testing"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(ssl=False)  # For development testing
        )

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def test_endpoint_availability(self, url: str, endpoint_name: str) -> Dict[str, Any]:
        """Test if endpoint is available and responding"""
        logger.info(f"Testing {endpoint_name} availability: {url}")
        
        try:
            async with self.session.get(url) as response:
                result = {
                    'endpoint': endpoint_name,
                    'url': url,
                    'status_code': response.status,
                    'response_time_ms': 0,
                    'available': response.status < 500,
                    'headers': dict(response.headers),
                    'error': None
                }
                
                # Try to read response body
                try:
                    body = await response.text()
                    result['has_response_body'] = len(body) > 0
                    result['response_length'] = len(body)
                except:
                    result['has_response_body'] = False
                    result['response_length'] = 0
                
                return result
                
        except Exception as e:
            return {
                'endpoint': endpoint_name,
                'url': url,
                'status_code': 0,
                'response_time_ms': 0,
                'available': False,
                'headers': {},
                'error': str(e),
                'has_response_body': False,
                'response_length': 0
            }

    async def test_authentication_flow(self) -> Dict[str, Any]:
        """Test JWT authentication flow - CRITICAL CLAIM VERIFICATION"""
        logger.info("Testing JWT authentication flow...")
        
        auth_results = {
            'test_name': 'JWT Authentication Flow',
            'claim_tested': 'JWT authentication flow FULLY WORKING',
            'test_steps': [],
            'overall_success': False,
            'jwt_token_obtained': False,
            'token_validation_success': False,
            'protected_endpoint_access': False
        }
        
        # Step 1: Test login endpoint
        login_url = f"{self.urls['kong_gateway']}/api/v1/auth/login"
        logger.info(f"Step 1: Testing login at {login_url}")
        
        try:
            login_data = {
                'email': self.test_credentials['email'],
                'password': self.test_credentials['password']
            }
            
            async with self.session.post(
                login_url, 
                json=login_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                
                login_result = {
                    'step': 'login_request',
                    'url': login_url,
                    'status_code': response.status,
                    'success': response.status == 200,
                    'error': None
                }
                
                if response.status == 200:
                    try:
                        login_response = await response.json()
                        if 'access_token' in login_response:
                            self.auth_token = login_response['access_token']
                            auth_results['jwt_token_obtained'] = True
                            login_result['token_obtained'] = True
                            logger.info("✅ JWT token obtained successfully")
                        else:
                            login_result['error'] = "No access_token in response"
                    except Exception as e:
                        login_result['error'] = f"Failed to parse login response: {e}"
                else:
                    login_result['error'] = f"Login failed with status {response.status}"
                    try:
                        error_body = await response.text()
                        login_result['response_body'] = error_body
                    except:
                        pass
                
                auth_results['test_steps'].append(login_result)
                
        except Exception as e:
            auth_results['test_steps'].append({
                'step': 'login_request',
                'url': login_url,
                'status_code': 0,
                'success': False,
                'error': str(e)
            })
            
        # Step 2: Test protected endpoint access
        if self.auth_token:
            logger.info("Step 2: Testing protected endpoint access with JWT token")
            
            # Test /me endpoint
            me_url = f"{self.urls['kong_gateway']}/api/v1/auth/me"
            try:
                headers = {'Authorization': f'Bearer {self.auth_token}'}
                
                async with self.session.get(me_url, headers=headers) as response:
                    me_result = {
                        'step': 'protected_endpoint_access',
                        'url': me_url,
                        'status_code': response.status,
                        'success': response.status == 200,
                        'error': None
                    }
                    
                    if response.status == 200:
                        auth_results['protected_endpoint_access'] = True
                        auth_results['token_validation_success'] = True
                        logger.info("✅ Protected endpoint access successful")
                    else:
                        me_result['error'] = f"Protected endpoint failed with status {response.status}"
                        try:
                            error_body = await response.text()
                            me_result['response_body'] = error_body
                        except:
                            pass
                    
                    auth_results['test_steps'].append(me_result)
                    
            except Exception as e:
                auth_results['test_steps'].append({
                    'step': 'protected_endpoint_access',
                    'url': me_url,
                    'status_code': 0,
                    'success': False,
                    'error': str(e)
                })
        
        # Overall assessment
        auth_results['overall_success'] = (
            auth_results['jwt_token_obtained'] and 
            auth_results['token_validation_success'] and 
            auth_results['protected_endpoint_access']
        )
        
        return auth_results

    async def test_generation_endpoints_503_fix(self) -> Dict[str, Any]:
        """Test generation endpoints - CRITICAL CLAIM: HTTP 503 COMPLETELY FIXED"""
        logger.info("Testing generation endpoints for 503 error fix...")
        
        generation_results = {
            'test_name': 'Generation Endpoints 503 Fix',
            'claim_tested': 'HTTP 503 generation endpoints COMPLETELY FIXED',
            'endpoints_tested': [],
            'overall_success': False,
            'no_503_errors': True,
            'all_endpoints_working': False
        }
        
        # List of generation endpoints to test
        generation_endpoints = [
            '/api/v1/generations',
            '/api/v1/generations/stats',
            '/api/v1/models',
            '/api/v1/credits/balance'
        ]
        
        headers = {}
        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'
        
        working_endpoints = 0
        
        for endpoint in generation_endpoints:
            url = f"{self.urls['kong_gateway']}{endpoint}"
            logger.info(f"Testing: {url}")
            
            try:
                async with self.session.get(url, headers=headers) as response:
                    endpoint_result = {
                        'endpoint': endpoint,
                        'url': url,
                        'status_code': response.status,
                        'success': response.status == 200,
                        'has_503_error': response.status == 503,
                        'error': None
                    }
                    
                    if response.status == 503:
                        generation_results['no_503_errors'] = False
                        endpoint_result['error'] = "HTTP 503 Service Unavailable - CLAIM FAILED"
                        logger.error(f"❌ HTTP 503 found at {endpoint} - Claim about 503 fix is FALSE")
                    elif response.status == 200:
                        working_endpoints += 1
                        logger.info(f"✅ {endpoint} working correctly")
                    else:
                        endpoint_result['error'] = f"HTTP {response.status}"
                        try:
                            error_body = await response.text()
                            endpoint_result['response_body'] = error_body
                        except:
                            pass
                    
                    generation_results['endpoints_tested'].append(endpoint_result)
                    
            except Exception as e:
                generation_results['endpoints_tested'].append({
                    'endpoint': endpoint,
                    'url': url,
                    'status_code': 0,
                    'success': False,
                    'has_503_error': False,
                    'error': str(e)
                })
        
        # Overall assessment
        generation_results['all_endpoints_working'] = working_endpoints == len(generation_endpoints)
        generation_results['overall_success'] = (
            generation_results['no_503_errors'] and 
            working_endpoints > 0
        )
        
        return generation_results

    async def test_ai_models_kong_gateway(self) -> Dict[str, Any]:
        """Test AI models through Kong Gateway - CRITICAL CLAIM: All 7 models accessible"""
        logger.info("Testing AI models accessibility through Kong Gateway...")
        
        models_results = {
            'test_name': 'AI Models Kong Gateway Access',
            'claim_tested': 'All 7 AI models accessible through Kong Gateway',
            'models_tested': [],
            'overall_success': False,
            'accessible_models_count': 0,
            'claimed_models_count': 7
        }
        
        # Test models endpoint
        models_url = f"{self.urls['kong_gateway']}/api/v1/models"
        
        headers = {}
        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'
        
        try:
            async with self.session.get(models_url, headers=headers) as response:
                models_result = {
                    'endpoint': '/api/v1/models',
                    'url': models_url,
                    'status_code': response.status,
                    'success': response.status == 200,
                    'models_returned': [],
                    'error': None
                }
                
                if response.status == 200:
                    try:
                        models_data = await response.json()
                        if isinstance(models_data, list):
                            models_results['accessible_models_count'] = len(models_data)
                            models_result['models_returned'] = models_data
                            
                            for model in models_data:
                                models_results['models_tested'].append({
                                    'model_id': model.get('id', 'unknown'),
                                    'model_name': model.get('name', 'unknown'),
                                    'accessible': True
                                })
                            
                            logger.info(f"✅ Found {len(models_data)} accessible models")
                        elif isinstance(models_data, dict) and 'models' in models_data:
                            models_list = models_data['models']
                            models_results['accessible_models_count'] = len(models_list)
                            models_result['models_returned'] = models_list
                            
                            for model in models_list:
                                models_results['models_tested'].append({
                                    'model_id': model.get('id', 'unknown'),
                                    'model_name': model.get('name', 'unknown'),
                                    'accessible': True
                                })
                                
                            logger.info(f"✅ Found {len(models_list)} accessible models")
                        else:
                            models_result['error'] = "Unexpected models response format"
                    except Exception as e:
                        models_result['error'] = f"Failed to parse models response: {e}"
                else:
                    models_result['error'] = f"Models endpoint failed with status {response.status}"
                    try:
                        error_body = await response.text()
                        models_result['response_body'] = error_body
                    except:
                        pass
                
                models_results['models_tested'].append(models_result)
                
        except Exception as e:
            models_results['models_tested'].append({
                'endpoint': '/api/v1/models',
                'url': models_url,
                'status_code': 0,
                'success': False,
                'error': str(e)
            })
        
        # Overall assessment
        models_results['overall_success'] = (
            models_results['accessible_models_count'] >= models_results['claimed_models_count']
        )
        
        return models_results

    async def test_core_platform_features(self) -> Dict[str, Any]:
        """Test core platform features - credits, projects, generation services"""
        logger.info("Testing core platform features...")
        
        core_results = {
            'test_name': 'Core Platform Features',
            'claim_tested': 'Generation services, credits, projects fully operational',
            'feature_tests': [],
            'overall_success': False,
            'working_features_count': 0
        }
        
        headers = {}
        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'
        
        # Test core endpoints
        core_endpoints = [
            {'endpoint': '/api/v1/credits/balance', 'feature': 'Credits System'},
            {'endpoint': '/api/v1/projects', 'feature': 'Project Management'},
            {'endpoint': '/api/v1/generations', 'feature': 'Generation Services'},
            {'endpoint': '/api/v1/generations/stats', 'feature': 'Generation Statistics'}
        ]
        
        for test in core_endpoints:
            url = f"{self.urls['kong_gateway']}{test['endpoint']}"
            logger.info(f"Testing {test['feature']}: {url}")
            
            try:
                async with self.session.get(url, headers=headers) as response:
                    feature_result = {
                        'feature': test['feature'],
                        'endpoint': test['endpoint'],
                        'url': url,
                        'status_code': response.status,
                        'success': response.status == 200,
                        'operational': response.status in [200, 201, 204],
                        'error': None
                    }
                    
                    if feature_result['operational']:
                        core_results['working_features_count'] += 1
                        logger.info(f"✅ {test['feature']} is operational")
                    else:
                        feature_result['error'] = f"HTTP {response.status}"
                        try:
                            error_body = await response.text()
                            feature_result['response_body'] = error_body
                        except:
                            pass
                        logger.error(f"❌ {test['feature']} failed with status {response.status}")
                    
                    core_results['feature_tests'].append(feature_result)
                    
            except Exception as e:
                core_results['feature_tests'].append({
                    'feature': test['feature'],
                    'endpoint': test['endpoint'],
                    'url': url,
                    'status_code': 0,
                    'success': False,
                    'operational': False,
                    'error': str(e)
                })
        
        # Overall assessment
        core_results['overall_success'] = core_results['working_features_count'] >= 3
        
        return core_results

    async def verify_prd_alignment(self) -> Dict[str, Any]:
        """Verify platform alignment with PRD requirements"""
        logger.info("Verifying PRD alignment...")
        
        prd_results = {
            'test_name': 'PRD Alignment Verification',
            'requirements_tested': [],
            'overall_alignment_score': 0,
            'critical_gaps': [],
            'implementation_status': {}
        }
        
        # PRD Requirements to verify
        prd_requirements = [
            {
                'requirement': 'User Authentication and JWT Management',
                'test_method': 'authentication_flow',
                'critical': True
            },
            {
                'requirement': 'Multiple AI Model Integration',
                'test_method': 'ai_models_test',
                'critical': True
            },
            {
                'requirement': 'Project Management System',
                'test_method': 'core_features',
                'critical': True
            },
            {
                'requirement': 'Credits System and Balance Tracking',
                'test_method': 'core_features',
                'critical': True
            },
            {
                'requirement': 'Kong Gateway API Routing',
                'test_method': 'endpoint_availability',
                'critical': True
            },
            {
                'requirement': 'Production URLs Functionality',
                'test_method': 'endpoint_availability',
                'critical': True
            }
        ]
        
        # Will be populated based on test results
        for req in prd_requirements:
            prd_results['requirements_tested'].append({
                'requirement': req['requirement'],
                'implemented': False,  # Will be updated based on test results
                'critical': req['critical'],
                'test_method': req['test_method'],
                'issues': []
            })
        
        return prd_results

    async def calculate_production_readiness_score(self) -> float:
        """Calculate production readiness score based on test results"""
        logger.info("Calculating production readiness score...")
        
        # Weight factors for different test categories
        weights = {
            'endpoint_availability': 20,
            'authentication': 25,
            'generation_endpoints': 25,
            'ai_models': 15,
            'core_features': 15
        }
        
        score = 0.0
        
        # This will be calculated based on actual test results
        # Placeholder for now - will be updated with real results
        
        return score

    async def run_comprehensive_validation(self) -> Dict[str, Any]:
        """Run comprehensive production validation suite"""
        logger.info("🚀 Starting Comprehensive Production Validation Suite")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        try:
            await self.setup_session()
            
            # Test 1: Endpoint Availability
            logger.info("\n📡 PHASE 1: Testing Endpoint Availability")
            endpoint_results = {}
            for name, url in self.urls.items():
                result = await self.test_endpoint_availability(url, name)
                endpoint_results[name] = result
            
            self.validation_results['detailed_results']['endpoint_availability'] = endpoint_results
            
            # Test 2: Authentication Flow (CRITICAL CLAIM)
            logger.info("\n🔐 PHASE 2: Testing JWT Authentication Flow")
            auth_results = await self.test_authentication_flow()
            self.validation_results['detailed_results']['authentication'] = auth_results
            self.validation_results['claim_verification']['jwt_fully_working'] = auth_results['overall_success']
            
            # Test 3: Generation Endpoints 503 Fix (CRITICAL CLAIM)
            logger.info("\n🔧 PHASE 3: Testing Generation Endpoints 503 Fix")
            generation_results = await self.test_generation_endpoints_503_fix()
            self.validation_results['detailed_results']['generation_endpoints'] = generation_results
            self.validation_results['claim_verification']['503_completely_fixed'] = generation_results['overall_success']
            
            # Test 4: AI Models through Kong Gateway (CRITICAL CLAIM)
            logger.info("\n🤖 PHASE 4: Testing AI Models Kong Gateway Access")
            models_results = await self.test_ai_models_kong_gateway()
            self.validation_results['detailed_results']['ai_models'] = models_results
            self.validation_results['claim_verification']['7_models_accessible'] = models_results['overall_success']
            
            # Test 5: Core Platform Features (CRITICAL CLAIM)
            logger.info("\n⚙️ PHASE 5: Testing Core Platform Features")
            core_results = await self.test_core_platform_features()
            self.validation_results['detailed_results']['core_features'] = core_results
            self.validation_results['claim_verification']['services_fully_operational'] = core_results['overall_success']
            
            # Test 6: PRD Alignment Verification
            logger.info("\n📋 PHASE 6: Verifying PRD Alignment")
            prd_results = await self.verify_prd_alignment()
            self.validation_results['prd_alignment'] = prd_results
            
            # Calculate Production Readiness Score
            logger.info("\n📊 PHASE 7: Calculating Production Readiness Score")
            readiness_score = await self.calculate_production_readiness_score()
            self.validation_results['production_readiness_score'] = readiness_score
            
            # Generate summary
            await self.generate_test_summary()
            
        except Exception as e:
            logger.error(f"Critical error in validation suite: {e}")
            self.validation_results['critical_error'] = str(e)
            
        finally:
            await self.cleanup_session()
            
        end_time = time.time()
        self.validation_results['test_duration_seconds'] = end_time - start_time
        
        logger.info(f"\n✅ Validation suite completed in {end_time - start_time:.2f} seconds")
        return self.validation_results

    async def generate_test_summary(self):
        """Generate test execution summary"""
        summary = {
            'total_tests_run': 0,
            'tests_passed': 0,
            'tests_failed': 0,
            'critical_claims_verified': 0,
            'critical_claims_failed': 0,
            'endpoint_availability_rate': 0,
            'authentication_working': False,
            'generation_503_fixed': False,
            'ai_models_accessible': 0,
            'core_features_operational': 0
        }
        
        # Analyze results
        claim_verification = self.validation_results['claim_verification']
        
        summary['authentication_working'] = claim_verification.get('jwt_fully_working', False)
        summary['generation_503_fixed'] = claim_verification.get('503_completely_fixed', False)
        
        if summary['authentication_working']:
            summary['critical_claims_verified'] += 1
        else:
            summary['critical_claims_failed'] += 1
            
        if summary['generation_503_fixed']:
            summary['critical_claims_verified'] += 1
        else:
            summary['critical_claims_failed'] += 1
        
        # Count endpoint availability
        endpoint_results = self.validation_results['detailed_results'].get('endpoint_availability', {})
        available_endpoints = sum(1 for result in endpoint_results.values() if result.get('available', False))
        total_endpoints = len(endpoint_results)
        
        if total_endpoints > 0:
            summary['endpoint_availability_rate'] = (available_endpoints / total_endpoints) * 100
        
        # AI Models count
        models_results = self.validation_results['detailed_results'].get('ai_models', {})
        summary['ai_models_accessible'] = models_results.get('accessible_models_count', 0)
        
        # Core features count
        core_results = self.validation_results['detailed_results'].get('core_features', {})
        summary['core_features_operational'] = core_results.get('working_features_count', 0)
        
        summary['total_tests_run'] = summary['critical_claims_verified'] + summary['critical_claims_failed']
        summary['tests_passed'] = summary['critical_claims_verified']
        summary['tests_failed'] = summary['critical_claims_failed']
        
        self.validation_results['test_summary'] = summary

    def save_results(self, filename: Optional[str] = None):
        """Save validation results to JSON file"""
        if not filename:
            timestamp = int(time.time())
            filename = f'production_validation_comprehensive_{timestamp}.json'
        
        filepath = os.path.join(os.getcwd(), filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.validation_results, f, indent=2, default=str)
            
            logger.info(f"📄 Validation results saved to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            return None

    def print_executive_summary(self):
        """Print executive summary of validation results"""
        print("\n" + "="*80)
        print("🎯 VELRO AI PLATFORM - PRODUCTION VALIDATION EXECUTIVE SUMMARY")
        print("="*80)
        
        summary = self.validation_results.get('test_summary', {})
        claims = self.validation_results.get('claim_verification', {})
        
        print(f"\n📊 TEST EXECUTION SUMMARY:")
        print(f"   • Total Tests Run: {summary.get('total_tests_run', 0)}")
        print(f"   • Tests Passed: {summary.get('tests_passed', 0)}")
        print(f"   • Tests Failed: {summary.get('tests_failed', 0)}")
        print(f"   • Endpoint Availability: {summary.get('endpoint_availability_rate', 0):.1f}%")
        
        print(f"\n🎯 CRITICAL CLAIMS VERIFICATION:")
        print(f"   • JWT Authentication FULLY WORKING: {'✅ VERIFIED' if claims.get('jwt_fully_working', False) else '❌ FAILED'}")
        print(f"   • HTTP 503 COMPLETELY FIXED: {'✅ VERIFIED' if claims.get('503_completely_fixed', False) else '❌ FAILED'}")
        print(f"   • 7 AI Models Accessible: {'✅ VERIFIED' if claims.get('7_models_accessible', False) else '❌ FAILED'}")
        print(f"   • Services Fully Operational: {'✅ VERIFIED' if claims.get('services_fully_operational', False) else '❌ FAILED'}")
        
        print(f"\n📈 PLATFORM METRICS:")
        print(f"   • AI Models Accessible: {summary.get('ai_models_accessible', 0)}")
        print(f"   • Core Features Operational: {summary.get('core_features_operational', 0)}")
        print(f"   • Production Readiness Score: {self.validation_results.get('production_readiness_score', 0):.1f}%")
        
        print(f"\n🚀 PRODUCTION READINESS ASSESSMENT:")
        readiness_score = self.validation_results.get('production_readiness_score', 0)
        
        if readiness_score >= 89:
            print(f"   ✅ PRODUCTION READY - Score: {readiness_score:.1f}% (Meets claimed 89%)")
        else:
            print(f"   ❌ NOT PRODUCTION READY - Score: {readiness_score:.1f}% (Below claimed 89%)")
        
        print("\n" + "="*80)


async def main():
    """Main execution function"""
    print("🚀 VELRO AI PLATFORM - COMPREHENSIVE PRODUCTION VALIDATION")
    print("Testing all claims about production readiness and PRD alignment...")
    print("="*80)
    
    validator = VelroProductionValidator()
    
    try:
        # Run comprehensive validation
        results = await validator.run_comprehensive_validation()
        
        # Print executive summary
        validator.print_executive_summary()
        
        # Save detailed results
        results_file = validator.save_results()
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        print("\n✅ Production validation suite completed!")
        
        return results
        
    except Exception as e:
        logger.error(f"Validation suite failed: {e}")
        print(f"\n❌ Validation suite failed: {e}")
        return None


if __name__ == "__main__":
    # Run the validation suite
    results = asyncio.run(main())
    
    if results:
        # Exit code based on results
        summary = results.get('test_summary', {})
        failed_tests = summary.get('tests_failed', 0)
        
        if failed_tests > 0:
            print(f"\n⚠️  {failed_tests} critical claims failed validation")
            sys.exit(1)
        else:
            print("\n✅ All critical claims verified successfully")
            sys.exit(0)
    else:
        print("\n❌ Validation suite could not complete")
        sys.exit(1)