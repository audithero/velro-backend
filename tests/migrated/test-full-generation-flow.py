#!/usr/bin/env python3
"""
Test Full Generation Flow - Direct Backend Testing
Tests registration, login, and image generation through async endpoints
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Configuration - Direct to backend, no Kong
BACKEND_URL = "https://velro-backend-production.up.railway.app"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{Colors.RESET}")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.YELLOW}ℹ️  {text}{Colors.RESET}")

async def test_full_generation_flow():
    """Test the complete flow: register, login, generate image"""
    print_header("🚀 VELRO PRODUCTION TEST - FULL GENERATION FLOW")
    print_info(f"Backend URL: {BACKEND_URL}")
    print_info(f"Timestamp: {datetime.now()}")
    
    # Create test account
    timestamp = int(time.time())
    email = f"test_{timestamp}@example.com"
    password = "TestPassword123!"
    
    async with aiohttp.ClientSession() as session:
        # ============= STEP 1: REGISTRATION =============
        print_header("STEP 1: USER REGISTRATION")
        print_info(f"Email: {email}")
        
        try:
            async with session.post(
                f"{BACKEND_URL}/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "Test User"
                },
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    token = data.get("access_token")
                    user = data.get("user", {})
                    
                    print_success("Registration successful!")
                    print_info(f"User ID: {user.get('id', 'N/A')}")
                    print_info(f"Credits: {user.get('credits_balance', 100)}")
                    print_info(f"Token: {token[:50]}..." if token else "No token")
                else:
                    error_text = await response.text()
                    print_error(f"Registration failed: {response.status}")
                    print(f"Error: {error_text}")
                    return
                    
        except Exception as e:
            print_error(f"Registration error: {e}")
            return
        
        # ============= STEP 2: LOGIN TEST =============
        print_header("STEP 2: LOGIN VERIFICATION")
        
        try:
            async with session.post(
                f"{BACKEND_URL}/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password
                },
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    token = data.get("access_token")
                    print_success("Login successful!")
                    print_info(f"Fresh token received: {token[:50]}...")
                else:
                    error_text = await response.text()
                    print_error(f"Login failed: {response.status}")
                    print(f"Error: {error_text}")
                    
        except Exception as e:
            print_error(f"Login error: {e}")
        
        # ============= STEP 3: ASYNC GENERATION TEST =============
        print_header("STEP 3: ASYNC IMAGE GENERATION")
        print_info("Testing /api/v1/generations/async/submit")
        
        generation_data = {
            "model_id": "flux-dev",
            "prompt": "A beautiful mountain landscape at sunset with snow-capped peaks, photorealistic, 8k quality",
            "parameters": {
                "num_images": 1,
                "image_size": "square"
            }
        }
        
        print_info(f"Model: {generation_data['model_id']}")
        print_info(f"Prompt: {generation_data['prompt'][:50]}...")
        
        try:
            async with session.post(
                f"{BACKEND_URL}/api/v1/generations/async/submit",
                json=generation_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            ) as response:
                
                print_info(f"Response status: {response.status}")
                
                if response.status == 200:
                    gen_data = await response.json()
                    print_success("Generation submitted successfully!")
                    
                    generation_id = gen_data.get("generation_id")
                    print_info(f"Generation ID: {generation_id}")
                    print_info(f"Status: {gen_data.get('status')}")
                    print_info(f"Queue Position: {gen_data.get('queue_position', 'N/A')}")
                    print_info(f"Estimated Time: {gen_data.get('estimated_time', 'N/A')}s")
                    print_info(f"Cached: {gen_data.get('cached', False)}")
                    
                    # If result is cached, show immediately
                    if gen_data.get('cached') and gen_data.get('output_urls'):
                        print_success("Result from cache!")
                        for url in gen_data.get('output_urls', []):
                            print_success(f"Image URL: {url}")
                    else:
                        # Poll for completion
                        print_header("STEP 4: POLLING FOR COMPLETION")
                        print_info("Checking status every 3 seconds...")
                        
                        for i in range(20):  # Poll for up to 60 seconds
                            await asyncio.sleep(3)
                            
                            async with session.get(
                                f"{BACKEND_URL}/api/v1/generations/async/{generation_id}/status",
                                headers={"Authorization": f"Bearer {token}"}
                            ) as status_response:
                                
                                if status_response.status == 200:
                                    status_data = await status_response.json()
                                    status = status_data.get("status")
                                    
                                    print(f"   Poll {i+1}: Status = {status}")
                                    
                                    if status == "completed":
                                        print_success("🎉 IMAGE GENERATION COMPLETED!")
                                        output_urls = status_data.get("output_urls", [])
                                        
                                        if output_urls:
                                            print_success(f"Generated {len(output_urls)} image(s):")
                                            for idx, url in enumerate(output_urls, 1):
                                                print_success(f"  Image {idx}: {url}")
                                        else:
                                            print_error("No output URLs returned")
                                        break
                                        
                                    elif status == "failed":
                                        print_error(f"Generation failed: {status_data.get('error')}")
                                        break
                                else:
                                    print_error(f"Status check failed: {status_response.status}")
                                    break
                    
                elif response.status == 402:
                    print_error("Insufficient credits")
                    error_text = await response.text()
                    print(f"Error: {error_text}")
                    
                elif response.status == 401:
                    print_error("Authentication failed")
                    error_text = await response.text()
                    print(f"Error: {error_text}")
                    
                else:
                    print_error(f"Generation submission failed: {response.status}")
                    error_text = await response.text()
                    print(f"Error: {error_text}")
                    
        except Exception as e:
            print_error(f"Generation error: {e}")
        
        # ============= FINAL SUMMARY =============
        print_header("📊 TEST SUMMARY")
        print_info("Test completed")
        print_info(f"User: {email}")
        print_info(f"Backend: {BACKEND_URL}")
        print_info(f"Timestamp: {datetime.now()}")

if __name__ == "__main__":
    print(f"{Colors.BOLD}{Colors.GREEN}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           VELRO ASYNC GENERATION TEST SUITE             ║")
    print("║                  Production Environment                  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")
    
    asyncio.run(test_full_generation_flow())