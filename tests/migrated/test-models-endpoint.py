#!/usr/bin/env python3
"""
End-to-end test for models endpoint
Tests both public access and authenticated access
"""

import requests
import json
from datetime import datetime

# Configuration
BACKEND_URL = "https://velro-backend-production.up.railway.app"
API_V1 = f"{BACKEND_URL}/api/v1"

def test_models_endpoint():
    """Test the models endpoint for public access"""
    print("\n" + "="*60)
    print("🔍 TESTING MODELS ENDPOINT")
    print("="*60)
    
    # Test 1: Direct backend endpoint (should work without auth)
    endpoint = f"{API_V1}/generations/models/supported"
    print(f"\n1️⃣ Testing: {endpoint}")
    
    try:
        response = requests.get(endpoint)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS - Found {len(data.get('models', []))} models")
            for model in data.get('models', [])[:3]:
                print(f"      - {model['name']} ({model['model_id']})")
        else:
            print(f"   ❌ FAILED - {response.status_code}: {response.text[:200]}")
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test 2: Wrong endpoint (should return 404)
    wrong_endpoint = f"{API_V1}/models/supported"
    print(f"\n2️⃣ Testing wrong endpoint: {wrong_endpoint}")
    
    try:
        response = requests.get(wrong_endpoint)
        print(f"   Status: {response.status_code}")
        print(f"   Expected 404, got {response.status_code}")
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test 3: Missing /api/v1 (should return 401)
    no_api_endpoint = f"{BACKEND_URL}/generations/models/supported"
    print(f"\n3️⃣ Testing without /api/v1: {no_api_endpoint}")
    
    try:
        response = requests.get(no_api_endpoint)
        print(f"   Status: {response.status_code}")
        print(f"   Expected 401, got {response.status_code}")
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

def test_full_user_flow():
    """Test complete user flow with authentication"""
    print("\n" + "="*60)
    print("🚀 TESTING FULL USER FLOW")
    print("="*60)
    
    # Register a test user
    timestamp = int(datetime.now().timestamp())
    email = f"test_models_{timestamp}@example.com"
    
    print(f"\n1️⃣ Registering user: {email}")
    
    register_response = requests.post(
        f"{API_V1}/auth/register",
        json={
            "email": email,
            "password": "TestPassword123!",
            "full_name": "Test User"
        }
    )
    
    if register_response.status_code != 200:
        print(f"   ❌ Registration failed: {register_response.text}")
        return
    
    user_data = register_response.json()
    token = user_data.get('access_token')
    print(f"   ✅ Registered successfully")
    print(f"   User ID: {user_data.get('user', {}).get('id')}")
    print(f"   Credits: {user_data.get('user', {}).get('credits')}")
    
    # Test authenticated models endpoint
    print(f"\n2️⃣ Testing models endpoint with authentication")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{API_V1}/generations/models/supported",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ SUCCESS - Found {len(data.get('models', []))} models")
    else:
        print(f"   ❌ FAILED - {response.status_code}: {response.text[:200]}")
    
    # Test generation submission
    print(f"\n3️⃣ Testing generation submission")
    
    generation_response = requests.post(
        f"{API_V1}/generations/async/submit",
        headers=headers,
        json={
            "model_id": "fal-ai/flux-pro/v1.1-ultra",
            "prompt": "A beautiful mountain landscape",
            "parameters": {
                "num_images": 1,
                "image_size": "landscape_16_9"
            }
        }
    )
    
    if generation_response.status_code == 200:
        gen_data = generation_response.json()
        print(f"   ✅ Generation submitted")
        print(f"   ID: {gen_data.get('generation_id')}")
        print(f"   Status: {gen_data.get('status')}")
    else:
        print(f"   ❌ Generation failed: {generation_response.text[:200]}")

def main():
    print("\n🔧 VELRO MODELS ENDPOINT TEST")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Backend: {BACKEND_URL}")
    
    # Run tests
    test_models_endpoint()
    test_full_user_flow()
    
    print("\n" + "="*60)
    print("✅ TEST COMPLETE")
    print("="*60)
    print("\n📝 SUMMARY:")
    print("- Models endpoint should be accessible without auth")
    print("- URL must be: /api/v1/generations/models/supported")
    print("- Frontend should cache the results")
    print("\n⚠️ If you see errors in the browser:")
    print("1. Clear browser cache (Cmd+Shift+R)")
    print("2. Check browser console for cached JavaScript")
    print("3. Try incognito/private mode")

if __name__ == "__main__":
    main()