#\!/usr/bin/env python3
"""Test complete image generation flow with Redis fix."""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://velro-backend-production.up.railway.app"
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPassword123\!"

def test_full_flow():
    """Test the complete generation flow."""
    print("=" * 60)
    print("🚀 TESTING COMPLETE IMAGE GENERATION FLOW")
    print("=" * 60)
    print()
    
    # Step 1: Register user
    print("1️⃣ Registering new user...")
    register_response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": "Test User"
        }
    )
    
    if register_response.status_code \!= 200:
        print(f"❌ Registration failed: {register_response.text}")
        return False
    
    register_data = register_response.json()
    token = register_data.get("access_token")
    print(f"✅ User registered successfully")
    print(f"   Credits: {register_data.get('user', {}).get('credits_balance', 0)}")
    print()
    
    # Step 2: Submit generation
    print("2️⃣ Submitting image generation...")
    headers = {"Authorization": f"Bearer {token}"}
    
    generation_response = requests.post(
        f"{BASE_URL}/api/v1/generations/async/submit",
        headers=headers,
        json={
            "model_id": "flux-pro",
            "prompt": "A beautiful mountain landscape at sunset",
            "parameters": {
                "num_images": 1,
                "image_size": "landscape_16_9"
            }
        }
    )
    
    if generation_response.status_code \!= 200:
        print(f"❌ Generation submission failed: {generation_response.text}")
        return False
    
    generation_data = generation_response.json()
    generation_id = generation_data.get("generation_id")
    print(f"✅ Generation submitted")
    print(f"   ID: {generation_id}")
    print(f"   Status: {generation_data.get('status')}")
    print(f"   Queue Position: {generation_data.get('queue_position')}")
    print()
    
    # Step 3: Poll for completion
    print("3️⃣ Polling for completion...")
    max_attempts = 60  # 3 minutes max
    for attempt in range(max_attempts):
        time.sleep(3)
        
        status_response = requests.get(
            f"{BASE_URL}/api/v1/generations/async/{generation_id}/status",
            headers=headers
        )
        
        if status_response.status_code \!= 200:
            print(f"   ⚠️ Status check failed: {status_response.text}")
            continue
        
        status_data = status_response.json()
        current_status = status_data.get("status")
        
        print(f"   [{attempt+1}/{max_attempts}] Status: {current_status}", end="")
        
        if current_status == "completed":
            print()
            print(f"✅ Generation completed\!")
            print(f"   Output URLs: {status_data.get('output_urls', [])}")
            return True
        elif current_status == "failed":
            print()
            print(f"❌ Generation failed: {status_data.get('error')}")
            return False
        else:
            queue_pos = status_data.get("queue_position")
            if queue_pos:
                print(f" (Queue: {queue_pos})")
            else:
                print()
    
    print()
    print("⏱️ Generation timed out after 3 minutes")
    return False

if __name__ == "__main__":
    success = test_full_flow()
    print()
    print("=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED - IMAGE GENERATION WORKING\!")
    else:
        print("❌ TEST FAILED - CHECK LOGS FOR DETAILS")
    print("=" * 60)
