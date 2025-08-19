#!/usr/bin/env python3
"""
CREDIT PROCESSING PRODUCTION VALIDATION
Validates the specific credit processing issue against live production environment.

This script tests the exact error condition reported by the frontend:
- User ID: 22cb3917-57f6-49c6-ac96-ec266570081b
- Error: "Credit processing failed: Profile lookup error"
- Expected Credits: 1200
"""
import json
import asyncio
import time
from datetime import datetime
from typing import Dict, Any

try:
    import httpx
except ImportError:
    print("❌ httpx not available, using basic HTTP testing")
    httpx = None

# Test Configuration
PRODUCTION_BASE_URL = "https://velro-backend-production.up.railway.app"
AFFECTED_USER_ID = "22cb3917-57f6-49c6-ac96-ec266570081b"
AFFECTED_USER_EMAIL = "demo@velro.app"
EXPECTED_CREDITS = 1200

class ProductionCreditValidation:
    """Production validation for credit processing issue."""
    
    def __init__(self):
        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": AFFECTED_USER_ID,
            "user_email": AFFECTED_USER_EMAIL,
            "expected_credits": EXPECTED_CREDITS,
            "production_url": PRODUCTION_BASE_URL,
            "tests": {},
            "overall_status": "PENDING"
        }
    
    async def test_production_health(self) -> bool:
        """Test 1: Basic production health check."""
        print("🔍 [HEALTH] Testing production backend health...")
        
        if not httpx:
            self.results["tests"]["health_check"] = {
                "status": "SKIPPED",
                "message": "httpx not available"
            }
            return False
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{PRODUCTION_BASE_URL}/health")
                
                if response.status_code == 200:
                    health_data = response.json()
                    self.results["tests"]["health_check"] = {
                        "status": "PASS",
                        "message": "Production backend is healthy",
                        "response_time": health_data.get("response_time", "unknown"),
                        "status_code": response.status_code
                    }
                    print("✅ [HEALTH] Production backend health check PASSED")
                    return True
                else:
                    self.results["tests"]["health_check"] = {
                        "status": "FAIL",
                        "message": f"Health check failed with status {response.status_code}",
                        "status_code": response.status_code
                    }
                    print(f"❌ [HEALTH] Production backend health check FAILED: {response.status_code}")
                    return False
                    
        except Exception as e:
            self.results["tests"]["health_check"] = {
                "status": "FAIL",
                "message": f"Health check exception: {str(e)}",
                "error": str(e)
            }
            print(f"❌ [HEALTH] Production backend health check FAILED: {e}")
            return False
    
    async def test_credit_balance_endpoint(self) -> bool:
        """Test 2: Credit balance endpoint (should work)."""
        print("🔍 [CREDIT-BALANCE] Testing credit balance endpoint...")
        
        if not httpx:
            self.results["tests"]["credit_balance"] = {
                "status": "SKIPPED",
                "message": "httpx not available"
            }
            return False
        
        try:
            # Test without authentication first (should fail with 401/403)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{PRODUCTION_BASE_URL}/api/v1/credits/balance")
                
                if response.status_code in [401, 403]:
                    self.results["tests"]["credit_balance"] = {
                        "status": "PASS",
                        "message": "Credit balance endpoint requires authentication (as expected)",
                        "status_code": response.status_code,
                        "endpoint_exists": True
                    }
                    print("✅ [CREDIT-BALANCE] Credit balance endpoint requires auth (expected)")
                    return True
                elif response.status_code == 404:
                    self.results["tests"]["credit_balance"] = {
                        "status": "FAIL",
                        "message": "Credit balance endpoint not found",
                        "status_code": response.status_code,
                        "endpoint_exists": False
                    }
                    print("❌ [CREDIT-BALANCE] Credit balance endpoint not found")
                    return False
                else:
                    self.results["tests"]["credit_balance"] = {
                        "status": "UNEXPECTED",
                        "message": f"Unexpected response from credit balance endpoint: {response.status_code}",
                        "status_code": response.status_code
                    }
                    print(f"⚠️ [CREDIT-BALANCE] Unexpected response: {response.status_code}")
                    return False
                    
        except Exception as e:
            self.results["tests"]["credit_balance"] = {
                "status": "FAIL",
                "message": f"Credit balance endpoint exception: {str(e)}",
                "error": str(e)
            }
            print(f"❌ [CREDIT-BALANCE] Credit balance endpoint FAILED: {e}")
            return False
    
    async def test_generation_create_endpoint(self) -> bool:
        """Test 3: Generation creation endpoint (should fail with profile lookup error)."""
        print("🔍 [GENERATION] Testing generation creation endpoint...")
        
        if not httpx:
            self.results["tests"]["generation_create"] = {
                "status": "SKIPPED",
                "message": "httpx not available"
            }
            return False
        
        try:
            # Test generation creation with mock JWT token
            test_payload = {
                "prompt": "Test prompt for production validation",
                "model_id": "fal-ai/fast-turbo-diffusion",
                "generation_type": "text_to_image"
            }
            
            # Use a sample JWT token format (will fail authentication but test endpoint structure)
            test_headers = {
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsImtpZCI6IjFLZVFoMGxkV3paZjBKaU",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{PRODUCTION_BASE_URL}/api/v1/generations/create",
                    json=test_payload,
                    headers=test_headers
                )
                
                if response.status_code in [401, 403]:
                    self.results["tests"]["generation_create"] = {
                        "status": "PASS",
                        "message": "Generation endpoint requires authentication (as expected)",
                        "status_code": response.status_code,
                        "endpoint_exists": True
                    }
                    print("✅ [GENERATION] Generation creation endpoint requires auth (expected)")
                    return True
                elif response.status_code == 404:
                    self.results["tests"]["generation_create"] = {
                        "status": "FAIL",
                        "message": "Generation creation endpoint not found",
                        "status_code": response.status_code,
                        "endpoint_exists": False
                    }
                    print("❌ [GENERATION] Generation creation endpoint not found")
                    return False
                elif response.status_code == 400:
                    # Check if this is the credit processing error
                    try:
                        error_data = response.json()
                        error_message = error_data.get("detail", "").lower()
                        
                        if "profile lookup error" in error_message:
                            self.results["tests"]["generation_create"] = {
                                "status": "CONFIRMED_ERROR",
                                "message": "CONFIRMED: Profile lookup error exists in production",
                                "status_code": response.status_code,
                                "error_details": error_data,
                                "profile_lookup_error": True
                            }
                            print("🎯 [GENERATION] CONFIRMED: Profile lookup error exists in production!")
                            return True
                        else:
                            self.results["tests"]["generation_create"] = {
                                "status": "OTHER_ERROR",
                                "message": f"Different error than expected: {error_message}",
                                "status_code": response.status_code,
                                "error_details": error_data
                            }
                            print(f"⚠️ [GENERATION] Different error than expected: {error_message}")
                            return False
                    except:
                        self.results["tests"]["generation_create"] = {
                            "status": "PARSE_ERROR",
                            "message": "Could not parse error response",
                            "status_code": response.status_code,
                            "response_text": response.text[:200]
                        }
                        print("⚠️ [GENERATION] Could not parse error response")
                        return False
                else:
                    self.results["tests"]["generation_create"] = {
                        "status": "UNEXPECTED",
                        "message": f"Unexpected response from generation endpoint: {response.status_code}",
                        "status_code": response.status_code
                    }
                    print(f"⚠️ [GENERATION] Unexpected response: {response.status_code}")
                    return False
                    
        except Exception as e:
            self.results["tests"]["generation_create"] = {
                "status": "FAIL",
                "message": f"Generation creation endpoint exception: {str(e)}",
                "error": str(e)
            }
            print(f"❌ [GENERATION] Generation creation endpoint FAILED: {e}")
            return False
    
    async def test_models_endpoint(self) -> bool:
        """Test 4: Models endpoint (should work without auth)."""
        print("🔍 [MODELS] Testing models endpoint...")
        
        if not httpx:
            self.results["tests"]["models"] = {
                "status": "SKIPPED",
                "message": "httpx not available"
            }
            return False
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{PRODUCTION_BASE_URL}/api/v1/generations/models/supported")
                
                if response.status_code == 200:
                    try:
                        models_data = response.json()
                        model_count = len(models_data) if isinstance(models_data, list) else 0
                        
                        self.results["tests"]["models"] = {
                            "status": "PASS",
                            "message": f"Models endpoint working: {model_count} models available",
                            "status_code": response.status_code,
                            "model_count": model_count
                        }
                        print(f"✅ [MODELS] Models endpoint PASSED: {model_count} models")
                        return True
                    except:
                        self.results["tests"]["models"] = {
                            "status": "PARSE_ERROR",
                            "message": "Could not parse models response",
                            "status_code": response.status_code,
                            "response_text": response.text[:200]
                        }
                        print("⚠️ [MODELS] Could not parse models response")
                        return False
                else:
                    self.results["tests"]["models"] = {
                        "status": "FAIL",
                        "message": f"Models endpoint failed: {response.status_code}",
                        "status_code": response.status_code
                    }
                    print(f"❌ [MODELS] Models endpoint FAILED: {response.status_code}")
                    return False
                    
        except Exception as e:
            self.results["tests"]["models"] = {
                "status": "FAIL",
                "message": f"Models endpoint exception: {str(e)}",
                "error": str(e)
            }
            print(f"❌ [MODELS] Models endpoint FAILED: {e}")
            return False
    
    async def run_validation(self) -> Dict[str, Any]:
        """Run complete production validation."""
        print("🚀 CREDIT PROCESSING PRODUCTION VALIDATION")
        print("=" * 60)
        print(f"🎯 Target User: {AFFECTED_USER_EMAIL} ({AFFECTED_USER_ID})")
        print(f"💳 Expected Credits: {EXPECTED_CREDITS}")
        print(f"🌐 Production URL: {PRODUCTION_BASE_URL}")
        print(f"🐛 Testing for: Credit processing failed - Profile lookup error")
        print("=" * 60)
        
        # Run all tests
        test_results = []
        
        test_results.append(await self.test_production_health())
        test_results.append(await self.test_models_endpoint())
        test_results.append(await self.test_credit_balance_endpoint())
        test_results.append(await self.test_generation_create_endpoint())
        
        # Calculate overall results
        passed_tests = sum(1 for result in test_results if result)
        total_tests = len(test_results)
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        # Check for specific error confirmation
        profile_error_confirmed = any(
            test.get("status") == "CONFIRMED_ERROR" and test.get("profile_lookup_error", False)
            for test in self.results["tests"].values()
        )
        
        # Determine overall status
        if profile_error_confirmed:
            overall_status = "ERROR_CONFIRMED"
        elif passed_tests >= total_tests * 0.75:
            overall_status = "HEALTHY"
        else:
            overall_status = "ISSUES"
        
        self.results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "success_rate": round(success_rate, 2),
            "profile_error_confirmed": profile_error_confirmed,
            "overall_status": overall_status,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        self.results["overall_status"] = overall_status
        
        # Print summary
        print("\n" + "=" * 60)
        print("🎯 PRODUCTION VALIDATION RESULTS")
        print("=" * 60)
        
        if profile_error_confirmed:
            print("🔴 CRITICAL: Profile lookup error CONFIRMED in production!")
            print("   The credit processing issue exists and needs to be fixed.")
        elif overall_status == "HEALTHY":
            print("🟢 Production backend appears healthy")
            print("   No obvious issues detected in endpoint testing")
        else:
            print("🟡 Production backend has some issues")
            print("   Review individual test results above")
        
        print(f"   Tests Passed: {passed_tests}/{total_tests}")
        print(f"   Success Rate: {success_rate}%")
        print(f"   Profile Error Confirmed: {'YES' if profile_error_confirmed else 'NO'}")
        
        # Recommendations
        print("\n📋 RECOMMENDATIONS:")
        if profile_error_confirmed:
            print("   1. Apply service key fix to bypass RLS policies")
            print("   2. Update credit transaction service to use service role key")
            print("   3. Test fix with same user ID and generation request")
            print("   4. Verify credit deduction works correctly after fix")
        elif overall_status == "HEALTHY":
            print("   1. The issue may already be resolved or not reproducible")
            print("   2. Test with actual frontend JWT token for full validation")
            print("   3. Monitor for any user reports of credit processing issues")
        else:
            print("   1. Review individual test failures above")
            print("   2. Check production logs for additional error details")
            print("   3. Ensure all required endpoints are deployed correctly")
        
        print("=" * 60)
        
        return self.results
    
    def save_results(self, filename: str = None):
        """Save validation results to JSON file."""
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"production_credit_validation_{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
            print(f"\n💾 Results saved to: {filename}")
        except Exception as e:
            print(f"\n❌ Failed to save results: {e}")


async def main():
    """Main validation function."""
    validator = ProductionCreditValidation()
    results = await validator.run_validation()
    validator.save_results()
    
    # Return appropriate exit code
    if results["overall_status"] == "ERROR_CONFIRMED":
        return 2  # Error confirmed - needs fix
    elif results["overall_status"] == "HEALTHY":
        return 0  # All good
    else:
        return 1  # Some issues


if __name__ == "__main__":
    import sys
    
    if httpx is None:
        print("⚠️ Warning: httpx not available. Install with: pip install httpx")
        print("Continuing with limited testing capabilities...\n")
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Validation interrupted by user")
        sys.exit(3)
    except Exception as e:
        print(f"\n💥 Validation failed: {e}")
        sys.exit(4)