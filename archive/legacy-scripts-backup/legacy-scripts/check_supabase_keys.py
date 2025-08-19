#!/usr/bin/env python3
"""
Diagnostic script to check Supabase API keys and configuration.
"""
import os
import requests
from config import settings

def check_supabase_keys():
    """Check if Supabase API keys are valid."""
    print("🔍 SUPABASE KEY VALIDATION")
    print("=" * 50)
    
    print(f"Supabase URL: {settings.supabase_url}")
    print(f"Anon Key Length: {len(settings.supabase_anon_key)}")
    print(f"Service Key Length: {len(settings.supabase_service_role_key)}")
    print(f"Anon Key Start: {settings.supabase_anon_key[:20]}...")
    print(f"Service Key Start: {settings.supabase_service_role_key[:20]}...")
    
    print("\n1️⃣ Testing Anon Key...")
    try:
        response = requests.get(
            f"{settings.supabase_url}/rest/v1/users?select=count",
            headers={
                "Authorization": f"Bearer {settings.supabase_anon_key}",
                "apikey": settings.supabase_anon_key
            },
            timeout=10
        )
        if response.status_code == 200:
            print("✅ Anon key is VALID")
        else:
            print(f"❌ Anon key failed: {response.status_code} - {response.text[:200]}")
    except Exception as e:
        print(f"❌ Anon key test failed: {e}")
    
    print("\n2️⃣ Testing Service Role Key...")
    try:
        response = requests.get(
            f"{settings.supabase_url}/rest/v1/users?select=count",
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key
            },
            timeout=10
        )
        if response.status_code == 200:
            print("✅ Service role key is VALID")
        else:
            print(f"❌ Service role key failed: {response.status_code} - {response.text[:200]}")
    except Exception as e:
        print(f"❌ Service role key test failed: {e}")
    
    print("\n3️⃣ Testing Auth Endpoint...")
    try:
        response = requests.post(
            f"{settings.supabase_url}/auth/v1/signup",
            headers={
                "Authorization": f"Bearer {settings.supabase_anon_key}",
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json"
            },
            json={
                "email": "test@example.com",
                "password": "testpass123"
            },
            timeout=10
        )
        print(f"Auth endpoint response: {response.status_code}")
        if response.status_code in [200, 422, 400]:  # 422 = validation error, which means endpoint works
            print("✅ Auth endpoint is accessible")
        else:
            print(f"❌ Auth endpoint failed: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Auth endpoint test failed: {e}")

if __name__ == "__main__":
    check_supabase_keys()