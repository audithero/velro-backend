#!/usr/bin/env python3
"""
Debug script to identify where the 120s auth timeout is occurring.
Run this directly to test auth endpoints with detailed tracing.
"""
import asyncio
import httpx
import time
import json
from datetime import datetime

# Configuration
BACKEND_URL = "https://velro-backend-production.up.railway.app"
TEST_EMAIL = "admin@velro.com"
TEST_PASSWORD = "Admin123!"

async def test_auth_ping():
    """Test the ping endpoint performance"""
    print("\n" + "="*60)
    print("TESTING: /api/v1/auth/ping")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        start = time.time()
        try:
            response = await client.get(f"{BACKEND_URL}/api/v1/auth/ping")
            duration = (time.time() - start) * 1000
            
            print(f"✅ Status: {response.status_code}")
            print(f"⏱️  Duration: {duration:.2f}ms")
            
            if response.status_code == 200:
                data = response.json()
                print(f"📊 Response: {json.dumps(data, indent=2)}")
                
                if data.get("performance_met"):
                    print(f"✅ Performance target met (<200ms)")
                else:
                    print(f"⚠️  Performance target NOT met (>{data.get('performance_target', '200ms')})")
            else:
                print(f"❌ Error response: {response.text}")
                
        except httpx.TimeoutException:
            duration = (time.time() - start) * 1000
            print(f"❌ TIMEOUT after {duration:.2f}ms")
        except Exception as e:
            duration = (time.time() - start) * 1000
            print(f"❌ ERROR after {duration:.2f}ms: {e}")

async def test_auth_login_with_tracing():
    """Test login endpoint with detailed request tracing"""
    print("\n" + "="*60)
    print("TESTING: /api/v1/auth/login (with tracing)")
    print("="*60)
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Request-ID": f"debug-{time.time():.3f}"
    }
    
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    # Test with different timeout values
    timeouts = [2.0, 5.0, 10.0, 30.0]
    
    for timeout_val in timeouts:
        print(f"\n📍 Testing with {timeout_val}s timeout...")
        
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=1.0,
                read=timeout_val,
                write=1.0,
                pool=0.5
            )
        ) as client:
            start = time.time()
            phases = {"start": start}
            
            try:
                # Log connection phase
                print(f"  → Connecting to {BACKEND_URL}...")
                
                # Make request with event hooks for tracing
                response = await client.post(
                    f"{BACKEND_URL}/api/v1/auth/login",
                    json=payload,
                    headers=headers
                )
                
                phases["response_received"] = time.time()
                duration = (phases["response_received"] - phases["start"]) * 1000
                
                print(f"  ← Response received: {response.status_code} after {duration:.2f}ms")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"  ✅ Login successful!")
                    print(f"  📊 Token length: {len(data.get('access_token', ''))}")
                    print(f"  👤 User: {data.get('user', {}).get('email', 'unknown')}")
                    break  # Success, no need to try longer timeouts
                    
                elif response.status_code == 503:
                    print(f"  ⚠️  Service unavailable: {response.json().get('detail', 'unknown')}")
                    
                elif response.status_code == 401:
                    print(f"  ❌ Authentication failed: {response.json().get('detail', 'unknown')}")
                    break  # Auth failure, no point trying longer timeouts
                    
                else:
                    print(f"  ❌ Unexpected status: {response.status_code}")
                    print(f"  📄 Response: {response.text[:200]}")
                    
            except httpx.ConnectTimeout:
                duration = (time.time() - start) * 1000
                print(f"  ❌ CONNECTION TIMEOUT after {duration:.2f}ms")
                
            except httpx.ReadTimeout:
                duration = (time.time() - start) * 1000
                print(f"  ❌ READ TIMEOUT after {duration:.2f}ms")
                print(f"  💡 Server accepted connection but didn't respond in time")
                
            except httpx.WriteTimeout:
                duration = (time.time() - start) * 1000
                print(f"  ❌ WRITE TIMEOUT after {duration:.2f}ms")
                
            except httpx.PoolTimeout:
                duration = (time.time() - start) * 1000
                print(f"  ❌ POOL TIMEOUT after {duration:.2f}ms")
                
            except httpx.TimeoutException as e:
                duration = (time.time() - start) * 1000
                print(f"  ❌ GENERAL TIMEOUT after {duration:.2f}ms: {e}")
                
            except Exception as e:
                duration = (time.time() - start) * 1000
                print(f"  ❌ ERROR after {duration:.2f}ms: {type(e).__name__}: {e}")

async def test_middleware_status():
    """Test middleware status endpoint"""
    print("\n" + "="*60)
    print("TESTING: /api/v1/auth/middleware-status")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        start = time.time()
        try:
            response = await client.get(f"{BACKEND_URL}/api/v1/auth/middleware-status")
            duration = (time.time() - start) * 1000
            
            print(f"✅ Status: {response.status_code}")
            print(f"⏱️  Duration: {duration:.2f}ms")
            
            if response.status_code == 200:
                data = response.json()
                print(f"📊 Middleware Status: {data.get('status', 'unknown')}")
                
                fastpath_proof = data.get("fastpath_proof", {})
                if fastpath_proof.get("middleware_bypasses_active"):
                    print(f"✅ Fastpath ACTIVE - middleware bypasses working")
                else:
                    print(f"❌ Fastpath NOT ACTIVE - middleware may be causing delays")
                    
                print(f"📋 Recommendations:")
                for rec in data.get("recommendations", []):
                    print(f"   • {rec}")
                    
        except httpx.TimeoutException:
            duration = (time.time() - start) * 1000
            print(f"❌ TIMEOUT after {duration:.2f}ms")
        except Exception as e:
            duration = (time.time() - start) * 1000
            print(f"❌ ERROR after {duration:.2f}ms: {e}")

async def test_health_endpoint():
    """Test basic health endpoint"""
    print("\n" + "="*60)
    print("TESTING: /health")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        start = time.time()
        try:
            response = await client.get(f"{BACKEND_URL}/health")
            duration = (time.time() - start) * 1000
            
            print(f"✅ Status: {response.status_code}")
            print(f"⏱️  Duration: {duration:.2f}ms")
            
            if response.status_code == 200:
                data = response.json()
                print(f"📊 Status: {data.get('status', 'unknown')}")
                print(f"📦 Version: {data.get('version', 'unknown')}")
                print(f"🌍 Environment: {data.get('environment', 'unknown')}")
                
        except httpx.TimeoutException:
            duration = (time.time() - start) * 1000
            print(f"❌ TIMEOUT after {duration:.2f}ms")
        except Exception as e:
            duration = (time.time() - start) * 1000
            print(f"❌ ERROR after {duration:.2f}ms: {e}")

async def main():
    """Run all debug tests"""
    print("\n" + "="*60)
    print("🔍 AUTH TIMEOUT DEBUG SCRIPT")
    print(f"🌐 Backend: {BACKEND_URL}")
    print(f"📅 Time: {datetime.now().isoformat()}")
    print("="*60)
    
    # Run tests in sequence
    await test_health_endpoint()
    await test_auth_ping()
    await test_middleware_status()
    await test_auth_login_with_tracing()
    
    print("\n" + "="*60)
    print("🏁 DEBUG COMPLETE")
    print("="*60)
    
    print("\n📊 ANALYSIS:")
    print("1. If login times out at exactly 120s, it's likely a proxy/gateway timeout")
    print("2. If login times out at random times, it's likely a Supabase service issue")
    print("3. If middleware-status shows fastpath NOT active, middleware ordering is wrong")
    print("4. If ping works but login doesn't, the issue is in the auth service")

if __name__ == "__main__":
    asyncio.run(main())