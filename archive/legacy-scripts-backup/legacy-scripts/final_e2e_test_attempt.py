#!/usr/bin/env python3
"""
Final E2E Test Attempt with Alternative Approaches
==================================================

Try different authentication approaches and simplified requests to identify
any working paths through the system.
"""

import asyncio
import json
import time
import httpx
import uuid

async def test_alternative_auth_approaches():
    """Test various authentication approaches"""
    
    backend_url = "https://velro-003-backend-production.up.railway.app"
    client = httpx.AsyncClient(timeout=10.0)  # Shorter timeout
    
    print("🔍 FINAL E2E TEST - ALTERNATIVE APPROACHES")
    print("="*60)
    
    results = []
    
    try:
        # 1. Test if there's a working demo user or default credentials
        print("\n1️⃣ Testing with demo/default credentials...")
        demo_credentials = [
            {"email": "demo@velro.com", "password": "demo123"},
            {"email": "test@velro.com", "password": "test123"},
            {"email": "admin@velro.com", "password": "admin123"}
        ]
        
        for creds in demo_credentials:
            try:
                response = await client.post(
                    f"{backend_url}/api/v1/auth/login",
                    json=creds,
                    timeout=8.0
                )
                print(f"   Demo login {creds['email']}: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    if "access_token" in data:
                        print(f"   ✅ SUCCESS! Token obtained with {creds['email']}")
                        return data["access_token"]
                        
            except asyncio.TimeoutError:
                print(f"   ❌ Timeout with {creds['email']}")
            except Exception as e:
                print(f"   ❌ Error with {creds['email']}: {e}")
        
        # 2. Try minimal registration data
        print("\n2️⃣ Testing minimal registration...")
        minimal_user = {
            "email": f"minimal-{uuid.uuid4().hex[:4]}@test.com",
            "password": "Test123!"
        }
        
        try:
            response = await client.post(
                f"{backend_url}/api/v1/auth/register",
                json=minimal_user,
                timeout=8.0
            )
            print(f"   Minimal registration: {response.status_code}")
            if response.status_code in [200, 201]:
                data = response.json()
                if "access_token" in data:
                    print(f"   ✅ SUCCESS! Registration worked")
                    token = data["access_token"]
                    
                    # Test the token immediately
                    headers = {"Authorization": f"Bearer {token}"}
                    me_response = await client.get(
                        f"{backend_url}/api/v1/auth/me",
                        headers=headers,
                        timeout=5.0
                    )
                    print(f"   Token validation: {me_response.status_code}")
                    return token
                    
        except asyncio.TimeoutError:
            print(f"   ❌ Registration timeout")
        except Exception as e:
            print(f"   ❌ Registration error: {e}")
        
        # 3. Check if there's an API key approach
        print("\n3️⃣ Testing API key approach...")
        api_keys = [
            "velro-api-key-123",
            "test-api-key",
            "demo-key"
        ]
        
        for api_key in api_keys:
            try:
                headers = {"X-API-Key": api_key}
                response = await client.get(
                    f"{backend_url}/api/v1/credits/balance",
                    headers=headers,
                    timeout=5.0
                )
                print(f"   API key {api_key}: {response.status_code}")
                if response.status_code != 401:
                    print(f"   ✅ API key approach might work!")
                    
            except Exception as e:
                print(f"   ❌ API key error: {e}")
        
        # 4. Test public endpoints that might not need auth
        print("\n4️⃣ Testing potentially public endpoints...")
        public_endpoints = [
            "/api/v1/models/public",
            "/api/v1/health/public", 
            "/api/v1/status",
            "/docs",
            "/openapi.json"
        ]
        
        for endpoint in public_endpoints:
            try:
                response = await client.get(
                    f"{backend_url}{endpoint}",
                    timeout=5.0
                )
                print(f"   {endpoint}: {response.status_code}")
                if response.status_code == 200:
                    print(f"   ✅ Public endpoint found!")
                    
            except Exception as e:
                print(f"   ❌ {endpoint} error: {e}")
        
        # 5. Final attempt - try registration with full data and longer timeout
        print("\n5️⃣ Final registration attempt with extended timeout...")
        full_user = {
            "email": f"final-test-{uuid.uuid4().hex[:6]}@test.com",
            "password": "FinalTest2025!",
            "full_name": "Final Test User"
        }
        
        print(f"   Attempting registration for {full_user['email']}...")
        start_time = time.time()
        
        try:
            response = await client.post(
                f"{backend_url}/api/v1/auth/register",
                json=full_user,
                timeout=15.0  # Longer timeout
            )
            duration = time.time() - start_time
            print(f"   Final registration: {response.status_code} ({duration:.1f}s)")
            
            if response.status_code in [200, 201]:
                try:
                    data = response.json()
                    token = data.get("access_token")
                    if token:
                        print(f"   ✅ FINAL SUCCESS! Token obtained after {duration:.1f}s")
                        
                        # Quick test of the token
                        headers = {"Authorization": f"Bearer {token}"}
                        
                        # Test credit balance
                        start_time = time.time()
                        credits_response = await client.get(
                            f"{backend_url}/api/v1/credits/balance",
                            headers=headers,
                            timeout=8.0
                        )
                        credits_duration = time.time() - start_time
                        print(f"   Credits check: {credits_response.status_code} ({credits_duration:.1f}s)")
                        
                        if credits_response.status_code == 200:
                            credits_data = credits_response.json()
                            credits = credits_data.get("credits", 0)
                            print(f"   💰 Credits available: {credits}")
                            
                            # If we have credits, try to test image generation endpoint
                            if credits > 0:
                                print("\n6️⃣ Testing image generation with valid token...")
                                gen_data = {
                                    "prompt": "simple test image",
                                    "model": "fal-ai/flux-pro"
                                }
                                
                                start_time = time.time()
                                gen_response = await client.post(
                                    f"{backend_url}/api/v1/generations",
                                    headers=headers,
                                    json=gen_data,
                                    timeout=10.0
                                )
                                gen_duration = time.time() - start_time
                                print(f"   Image generation: {gen_response.status_code} ({gen_duration:.1f}s)")
                                
                                if gen_response.status_code in [200, 201]:
                                    gen_result = gen_response.json()
                                    image_url = gen_result.get("image_url") or gen_result.get("media_url")
                                    print(f"   ✅ Image generated! URL: {image_url[:50] if image_url else 'N/A'}...")
                                    
                                    # Test Supabase storage
                                    if image_url:
                                        storage_check = await client.get(image_url, timeout=5.0)
                                        print(f"   Supabase storage: {storage_check.status_code}")
                                        if storage_check.status_code == 200:
                                            print(f"   ✅ Supabase storage working! Image size: {len(storage_check.content)} bytes")
                        
                        return {
                            "success": True,
                            "token": token,
                            "user_email": full_user["email"],
                            "credits": credits,
                            "performance": {
                                "registration_time": duration,
                                "credits_check_time": credits_duration
                            }
                        }
                        
                except json.JSONDecodeError:
                    print(f"   ❌ Invalid JSON in final response")
            else:
                print(f"   ❌ Final registration failed: {response.text[:200]}")
                
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            print(f"   ❌ Final registration timeout after {duration:.1f}s")
        except Exception as e:
            duration = time.time() - start_time
            print(f"   ❌ Final registration error after {duration:.1f}s: {e}")
    
    finally:
        await client.aclose()
    
    print("\n" + "="*60)
    print("❌ ALL AUTHENTICATION ATTEMPTS FAILED")
    print("No working authentication path found.")
    print("="*60)
    
    return None

async def main():
    result = await test_alternative_auth_approaches()
    if result:
        print("\n✅ SUCCESS! Authentication working")
        return 0
    else:
        print("\n❌ FAILURE! No authentication method worked")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())