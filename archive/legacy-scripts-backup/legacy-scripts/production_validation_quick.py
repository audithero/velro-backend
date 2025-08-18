#!/usr/bin/env python3
"""
Quick Production Validation Script
Tests critical backend endpoints without full environment setup.
"""
import sys
import asyncio
import httpx
import json
from pathlib import Path

async def validate_production_deployment(base_url: str):
    """Validate production deployment with quick tests."""
    
    print(f"🔍 VALIDATING PRODUCTION DEPLOYMENT: {base_url}")
    print("=" * 60)
    
    results = {
        "base_url": base_url,
        "health_check": False,
        "models_endpoint": False,
        "auth_required": False,
        "cors_headers": False,
        "overall_status": "FAILED"
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        
        # Test 1: Health Check
        print("\n1. Testing health endpoint...")
        try:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("✅ Health check passed")
                results["health_check"] = True
            else:
                print(f"❌ Health check failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Health check error: {e}")
        
        # Test 2: Models Endpoint (Public)
        print("\n2. Testing models endpoint...")
        try:
            response = await client.get(f"{base_url}/api/v1/generations/models/supported")
            if response.status_code == 200:
                models = response.json()
                print(f"✅ Models endpoint works: {len(models)} models")
                
                # Check for new models
                model_ids = [m.get('model_id', '') for m in models]
                if 'fal-ai/flux-pro/v1.1-ultra' in model_ids:
                    print("✅ New FAL models detected")
                else:
                    print("⚠️ New FAL models not found")
                    
                results["models_endpoint"] = True
            else:
                print(f"❌ Models endpoint failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Models endpoint error: {e}")
        
        # Test 3: Authentication Required for Protected Endpoints
        print("\n3. Testing authentication requirement...")
        try:
            response = await client.get(f"{base_url}/api/v1/generations")
            if response.status_code == 401:
                print("✅ Authentication properly required")
                results["auth_required"] = True
            else:
                print(f"⚠️ Unexpected auth response: {response.status_code}")
        except Exception as e:
            print(f"❌ Auth test error: {e}")
        
        # Test 4: CORS Headers
        print("\n4. Testing CORS headers...")
        try:
            response = await client.options(f"{base_url}/api/v1/generations/models/supported")
            headers = response.headers
            if 'access-control-allow-origin' in headers:
                print("✅ CORS headers present")
                results["cors_headers"] = True
            else:
                print("⚠️ CORS headers not detected")
        except Exception as e:
            print(f"❌ CORS test error: {e}")
    
    # Overall Assessment
    passed = sum(1 for key, value in results.items() if key != "overall_status" and key != "base_url" and value)
    total = len(results) - 2
    
    print("\n" + "=" * 60)
    print("🎯 PRODUCTION VALIDATION RESULTS:")
    
    if passed >= total * 0.75:
        results["overall_status"] = "READY"
        print("🎉 PRODUCTION DEPLOYMENT VALIDATED!")
        print("   Backend is ready for production use")
    else:
        results["overall_status"] = "ISSUES"
        print("❌ Production deployment has issues")
        print("   Review failed tests above")
    
    print(f"   Tests Passed: {passed}/{total}")
    print(f"   Success Rate: {(passed/total)*100:.1f}%")
    
    # Save results
    results_file = Path(__file__).parent / "production_validation_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📊 Results saved to: {results_file}")
    
    return results["overall_status"] == "READY"

async def main():
    """Main validation function."""
    
    # Default production URL - update as needed
    production_urls = [
        "https://velro-backend-production.up.railway.app",
        "http://localhost:8000"  # Local testing
    ]
    
    if len(sys.argv) > 1:
        # Custom URL provided
        url = sys.argv[1]
        success = await validate_production_deployment(url)
    else:
        # Try known production URLs
        success = False
        for url in production_urls:
            print(f"\nTrying URL: {url}")
            try:
                success = await validate_production_deployment(url)
                if success:
                    break
            except Exception as e:
                print(f"Failed to connect to {url}: {e}")
                continue
    
    if success:
        print("\n🎉 PRODUCTION VALIDATION COMPLETE - BACKEND READY!")
    else:
        print("\n❌ PRODUCTION VALIDATION FAILED - REVIEW ISSUES")
    
    return success

if __name__ == "__main__":
    print("🚀 VELRO BACKEND PRODUCTION VALIDATION")
    print("Usage: python3 production_validation_quick.py [URL]")
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)