#!/usr/bin/env python3
"""
Deployment Status Check
Checks if the backend is properly deployed and accessible before running CORS tests.
"""

import asyncio
import aiohttp
import json
import time
import logging
from typing import Optional, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_deployment_status():
    """Check if the backend deployment is working."""
    
    BACKEND_URL = "https://velro-backend-production.up.railway.app"
    
    print("🔍 Backend Deployment Status Check")
    print("=" * 50)
    print(f"Backend URL: {BACKEND_URL}")
    print("=" * 50)
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        
        # Test 1: Basic connectivity
        print("\n1. Testing basic connectivity...")
        try:
            start_time = time.time()
            async with session.get(BACKEND_URL) as response:
                duration = (time.time() - start_time) * 1000
                
                print(f"   Status: {response.status}")
                print(f"   Duration: {duration:.1f}ms")
                
                if response.status == 200:
                    try:
                        response_data = await response.json()
                        print(f"   Response: {json.dumps(response_data, indent=2)}")
                        connectivity_ok = True
                    except:
                        response_text = await response.text()
                        print(f"   Response: {response_text[:200]}...")
                        connectivity_ok = True
                else:
                    response_text = await response.text()
                    print(f"   Error Response: {response_text[:200]}...")
                    connectivity_ok = False
                    
        except Exception as e:
            print(f"   ❌ Connectivity failed: {e}")
            connectivity_ok = False
        
        # Test 2: Health endpoint
        print("\n2. Testing health endpoint...")
        try:
            start_time = time.time()
            async with session.get(f"{BACKEND_URL}/health") as response:
                duration = (time.time() - start_time) * 1000
                
                print(f"   Status: {response.status}")
                print(f"   Duration: {duration:.1f}ms")
                
                if response.status == 200:
                    try:
                        health_data = await response.json()
                        print(f"   Health Status: {health_data.get('status', 'unknown')}")
                        print(f"   Version: {health_data.get('version', 'unknown')}")
                        print(f"   Environment: {health_data.get('environment', 'unknown')}")
                        health_ok = True
                    except:
                        health_ok = False
                else:
                    response_text = await response.text()
                    print(f"   Error: {response_text[:200]}...")
                    health_ok = False
                    
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
            health_ok = False
        
        # Test 3: API endpoints
        print("\n3. Testing API endpoints...")
        api_endpoints = [
            "/api/v1/models",
            "/api/v1/auth/login"
        ]
        
        api_results = {}
        for endpoint in api_endpoints:
            try:
                start_time = time.time()
                async with session.get(f"{BACKEND_URL}{endpoint}") as response:
                    duration = (time.time() - start_time) * 1000
                    
                    print(f"   {endpoint}: {response.status} ({duration:.1f}ms)")
                    api_results[endpoint] = {
                        "status": response.status,
                        "duration": duration,
                        "accessible": response.status != 404
                    }
                    
            except Exception as e:
                print(f"   {endpoint}: ERROR - {e}")
                api_results[endpoint] = {
                    "status": 0,
                    "duration": 0,
                    "accessible": False
                }
        
        # Test 4: CORS headers check (if service is up)
        if connectivity_ok or health_ok:
            print("\n4. Testing basic CORS headers...")
            try:
                headers = {
                    "Origin": "https://velro-frontend-production.up.railway.app"
                }
                
                start_time = time.time()
                async with session.get(f"{BACKEND_URL}/", headers=headers) as response:
                    duration = (time.time() - start_time) * 1000
                    
                    cors_headers = {
                        "Access-Control-Allow-Origin": response.headers.get("Access-Control-Allow-Origin"),
                        "Access-Control-Allow-Credentials": response.headers.get("Access-Control-Allow-Credentials"),
                        "Access-Control-Allow-Methods": response.headers.get("Access-Control-Allow-Methods"),
                        "Access-Control-Allow-Headers": response.headers.get("Access-Control-Allow-Headers")
                    }
                    
                    print(f"   Request Status: {response.status} ({duration:.1f}ms)")
                    print(f"   CORS Headers:")
                    for header, value in cors_headers.items():
                        status = "✅" if value else "❌"
                        print(f"     {status} {header}: {value}")
                    
                    cors_working = any(cors_headers.values())
                    
            except Exception as e:
                print(f"   ❌ CORS test failed: {e}")
                cors_working = False
        else:
            cors_working = False
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 DEPLOYMENT STATUS SUMMARY")
        print("=" * 50)
        
        overall_status = "HEALTHY" if (connectivity_ok and health_ok) else "ISSUES DETECTED"
        
        print(f"Overall Status: {overall_status}")
        print(f"Basic Connectivity: {'✅' if connectivity_ok else '❌'}")
        print(f"Health Endpoint: {'✅' if health_ok else '❌'}")
        
        # API endpoint status
        working_endpoints = sum(1 for r in api_results.values() if r["accessible"])
        total_endpoints = len(api_results)
        print(f"API Endpoints: {working_endpoints}/{total_endpoints} accessible")
        
        if cors_working:
            print(f"CORS Configuration: ✅ Working")
        else:
            print(f"CORS Configuration: ❌ Not working or service down")
        
        # Recommendations
        print("\n💡 RECOMMENDATIONS:")
        
        if not connectivity_ok and not health_ok:
            print("❌ Backend service appears to be down or unreachable")
            print("   - Check Railway deployment status")
            print("   - Verify the URL is correct")
            print("   - Check for recent deployment issues")
        elif not health_ok:
            print("⚠️ Service is responding but health endpoint failing")
            print("   - Check application startup logs")
            print("   - Verify database connections")
        elif working_endpoints < total_endpoints:
            print("⚠️ Some API endpoints not accessible")
            print("   - Check routing configuration")
            print("   - Verify middleware setup")
        
        if not cors_working and (connectivity_ok or health_ok):
            print("⚠️ CORS headers not detected")
            print("   - Check CORS middleware configuration")
            print("   - Verify allowed origins include frontend URL")
        
        return {
            "connectivity": connectivity_ok,
            "health": health_ok,
            "api_accessible": working_endpoints > 0,
            "cors_working": cors_working,
            "overall_healthy": connectivity_ok and health_ok
        }

async def main():
    """Run deployment status check."""
    try:
        status = await check_deployment_status()
        
        if status["overall_healthy"]:
            print("\n🎉 Backend is healthy and ready for CORS testing!")
            return True
        else:
            print("\n⚠️ Backend has issues that need to be resolved before CORS testing")
            return False
            
    except Exception as e:
        print(f"\n❌ Deployment check failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)