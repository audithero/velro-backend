#!/usr/bin/env python3
"""
Test credits API endpoint for info@apostle.io user
"""

import requests
import json

BACKEND_URL = "https://velro-backend-production.up.railway.app/api/v1"

def test_login_and_credits():
    print("\n" + "="*60)
    print("🔍 TESTING CREDITS API FOR info@apostle.io")
    print("="*60)
    
    # Step 1: Login
    print("\n1️⃣ Logging in as info@apostle.io...")
    
    login_response = requests.post(
        f"{BACKEND_URL}/auth/login",
        json={
            "email": "info@apostle.io",
            "password": "Apostle2025!"  # You'll need to provide the correct password
        }
    )
    
    if login_response.status_code != 200:
        print(f"   ❌ Login failed: {login_response.status_code}")
        print(f"   Response: {login_response.text}")
        return
    
    login_data = login_response.json()
    token = login_data.get('access_token')
    user_data = login_data.get('user', {})
    
    print(f"   ✅ Login successful")
    print(f"   User ID: {user_data.get('id')}")
    print(f"   Email: {user_data.get('email')}")
    print(f"   Credits in login response: {user_data.get('credits_balance', 'NOT PROVIDED')}")
    
    # Step 2: Get user profile
    print("\n2️⃣ Getting user profile via /auth/me...")
    
    headers = {"Authorization": f"Bearer {token}"}
    me_response = requests.get(
        f"{BACKEND_URL}/auth/me",
        headers=headers
    )
    
    if me_response.status_code == 200:
        me_data = me_response.json()
        print(f"   ✅ Profile retrieved")
        print(f"   User data: {json.dumps(me_data, indent=2)}")
    else:
        print(f"   ❌ Failed to get profile: {me_response.status_code}")
        print(f"   Response: {me_response.text}")
    
    # Step 3: Get credits balance
    print("\n3️⃣ Getting credits balance via /credits/balance...")
    
    credits_response = requests.get(
        f"{BACKEND_URL}/credits/balance",
        headers=headers
    )
    
    if credits_response.status_code == 200:
        credits_data = credits_response.json()
        print(f"   ✅ Credits retrieved")
        print(f"   Credits data: {json.dumps(credits_data, indent=2)}")
    else:
        print(f"   ❌ Failed to get credits: {credits_response.status_code}")
        print(f"   Response: {credits_response.text}")
    
    # Step 4: Check what's in the JWT token
    print("\n4️⃣ Decoding JWT token (without verification)...")
    
    try:
        import base64
        # JWT format: header.payload.signature
        parts = token.split('.')
        if len(parts) >= 2:
            # Decode the payload (add padding if needed)
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += '=' * padding
            
            decoded = base64.urlsafe_b64decode(payload)
            jwt_data = json.loads(decoded)
            print(f"   JWT Payload: {json.dumps(jwt_data, indent=2)}")
    except Exception as e:
        print(f"   ⚠️ Could not decode JWT: {e}")
    
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"Database shows: 1000 credits")
    print(f"Login response shows: {user_data.get('credits_balance', 'NOT PROVIDED')}")
    print(f"Profile endpoint shows: Check above")
    print(f"Credits endpoint shows: Check above")

if __name__ == "__main__":
    test_login_and_credits()