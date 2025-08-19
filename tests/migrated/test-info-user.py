#!/usr/bin/env python3
"""Test login and credits for info@apostle.io"""

import requests
import json

# Try different passwords
passwords = ["Testing123!", "Apostle2025!", "Password123!"]

for password in passwords:
    print(f"\nTrying password: {password[:3]}...")
    
    response = requests.post(
        "https://velro-backend-production.up.railway.app/api/v1/auth/login",
        json={
            "email": "info@apostle.io",
            "password": password,
            "remember_me": False
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        user = data.get("user", {})
        
        print(f"✅ Login successful!")
        print(f"   User ID: {user.get('id')}")
        print(f"   Credits in login response: {user.get('credits_balance', 'NOT PROVIDED')}")
        
        # Get /auth/me
        me_response = requests.get(
            "https://velro-backend-production.up.railway.app/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if me_response.status_code == 200:
            me_data = me_response.json()
            print(f"   Credits from /auth/me: {me_data.get('credits_balance')}")
            print(f"   Full response: {json.dumps(me_data, indent=2)}")
        
        break
    else:
        print(f"   Failed: {response.status_code}")