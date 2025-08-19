#!/usr/bin/env python3
"""
Debug script to test JWT authentication and identify base64 encoding issues.
"""
import os
import sys
import requests
import json
import base64
from datetime import datetime

def debug_jwt_token(token):
    """Debug JWT token format and identify issues."""
    print(f"\n=== JWT TOKEN DEBUG ===")
    print(f"Token length: {len(token)}")
    print(f"Token preview: {token[:50]}...")
    
    # Check JWT structure
    parts = token.split('.')
    print(f"JWT parts count: {len(parts)} (should be 3)")
    
    if len(parts) == 3:
        header, payload, signature = parts
        print(f"Header length: {len(header)}")
        print(f"Payload length: {len(payload)}")
        print(f"Signature length: {len(signature)}")
        
        # Try to decode each part
        for i, (part_name, part) in enumerate([("Header", header), ("Payload", payload), ("Signature", signature)]):
            try:
                # Add padding if needed
                padding = 4 - len(part) % 4
                if padding != 4:
                    padded = part + '=' * padding
                else:
                    padded = part
                
                decoded = base64.urlsafe_b64decode(padded)
                print(f"{part_name} decoded successfully: {len(decoded)} bytes")
                
                if i < 2:  # Header and payload are JSON
                    try:
                        json_data = json.loads(decoded)
                        print(f"{part_name} JSON: {json_data}")
                    except json.JSONDecodeError as je:
                        print(f"{part_name} JSON decode failed: {je}")
                        print(f"Raw bytes: {decoded}")
                        
            except Exception as e:
                print(f"{part_name} decode failed: {e}")
                print(f"Problematic part: {part}")
                
                # Try to find the issue
                for j, char in enumerate(part):
                    if ord(char) > 127:
                        print(f"Non-ASCII character at position {j}: {ord(char)} ({char})")
                        break
    else:
        print("Invalid JWT format - not 3 parts")

def test_auth_endpoints():
    """Test authentication endpoints and diagnose issues."""
    backend_url = 'https://velro-003-backend-production.up.railway.app'
    
    print(f"Testing backend: {backend_url}")
    
    # Test login
    print("\n=== LOGIN TEST ===")
    login_data = {
        'email': 'demo@example.com',
        'password': 'demo123'
    }
    
    try:
        response = requests.post(f'{backend_url}/api/v1/auth/login', json=login_data, timeout=15)
        print(f"Login status: {response.status_code}")
        
        if response.status_code == 200:
            token_data = response.json()
            print(f"Login response keys: {list(token_data.keys())}")
            
            if 'access_token' in token_data:
                token = token_data['access_token']
                debug_jwt_token(token)
                
                # Test /me endpoint with this token
                print(f"\n=== /ME TEST WITH LOGIN TOKEN ===")
                headers = {'Authorization': f'Bearer {token}'}
                me_response = requests.get(f'{backend_url}/api/v1/auth/me', headers=headers, timeout=15)
                print(f"/me status: {me_response.status_code}")
                print(f"/me response: {me_response.text}")
                
            else:
                print("No access_token in login response")
        else:
            print(f"Login failed: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"Login request failed: {e}")
    
    # Test with a manually crafted JWT
    print(f"\n=== MANUAL JWT TEST ===")
    try:
        import json
        import base64
        
        # Create a simple JWT header and payload
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": "bd1a2f69-89eb-489f-9288-8aacf4924763",
            "email": "demo@example.com",
            "iat": int(datetime.now().timestamp()),
            "exp": int(datetime.now().timestamp()) + 3600
        }
        
        header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        
        # Create a dummy signature
        signature = base64.urlsafe_b64encode(b'dummy_signature').decode().rstrip('=')
        
        manual_jwt = f"{header_encoded}.{payload_encoded}.{signature}"
        print(f"Manual JWT created: {manual_jwt[:100]}...")
        
        debug_jwt_token(manual_jwt)
        
        # Test this token
        headers = {'Authorization': f'Bearer {manual_jwt}'}
        me_response = requests.get(f'{backend_url}/api/v1/auth/me', headers=headers, timeout=15)
        print(f"Manual JWT /me status: {me_response.status_code}")
        print(f"Manual JWT /me response: {me_response.text}")
        
    except Exception as e:
        print(f"Manual JWT test failed: {e}")

if __name__ == "__main__":
    test_auth_endpoints()