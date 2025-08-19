#!/usr/bin/env python3
"""
Test Flux Image Generation via Velro API - Async Version
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Configuration
KONG_URL = "https://velro-kong-gateway-production.up.railway.app"

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

async def test_flux_generation():
    """Test Flux image generation through the async API"""
    print_header("Testing Async Flux Image Generation")
    
    # Create a new test account
    timestamp = int(time.time())
    email = f"e2e_test_{timestamp}@example.com"
    password = "TestPassword123!"
    
    print_info(f"Registering new user: {email}")
    
    async with aiohttp.ClientSession() as session:
        # Register new user
        try:
            async with session.post(
                f"{KONG_URL}/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "E2E Test User"
                },
                headers={"Content-Type": "application/json"}
            ) as response:
        
                if response.status == 200:
                    data = await response.json()
                    token = data.get("access_token")
                    print_success("Registration successful - Token received")
            
                    # Test async generation endpoint
                    print("\n" + "="*40)
                    print("Testing Async Generation Endpoint...")
                    print_info("Using /api/v1/generations/async/submit")
            
                    
                    # Submit generation request
                    generation_data = {
                        "model_id": "flux-dev",  # Using cheaper model for testing
                        "prompt": "A beautiful mountain landscape at sunset, photorealistic",
                        "parameters": {
                            "num_images": 1,
                            "image_size": "square"
                        }
                    }
                    
                    print_info(f"Model: {generation_data['model_id']}")
                    print_info(f"Prompt: {generation_data['prompt']}")
                    
                    async with session.post(
                        f"{KONG_URL}/api/v1/generations/async/submit",
                        json=generation_data,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"
                        }
                    ) as gen_response:
                
                        print(f"Response status: {gen_response.status}")
                        
                        if gen_response.status == 200:
                            gen_data = await gen_response.json()
                            print_success("Generation submitted successfully!")
                            print(f"Response: {json.dumps(gen_data, indent=2)}")
                            
                            generation_id = gen_data.get("generation_id")
                            print_info(f"Generation ID: {generation_id}")
                            print_info(f"Status: {gen_data.get('status')}")
                            print_info(f"Cached: {gen_data.get('cached', False)}")
                            print_info(f"Queue position: {gen_data.get('queue_position')}")
                            
                            # Poll for completion if not cached
                            if not gen_data.get('cached'):
                                print("\nPolling for generation completion...")
                                for i in range(30):
                                    await asyncio.sleep(2)
                                    
                                    async with session.get(
                                        f"{KONG_URL}/api/v1/generations/async/{generation_id}/status",
                                        headers={"Authorization": f"Bearer {token}"}
                                    ) as status_response:
                                        if status_response.status == 200:
                                            status_data = await status_response.json()
                                            status = status_data.get("status")
                                            print(f"   Poll {i+1}: {status}")
                                            
                                            if status == "completed":
                                                print_success("Image generation completed!")
                                                output_urls = status_data.get("output_urls", [])
                                                for url in output_urls:
                                                    print_success(f"Image URL: {url}")
                                                break
                                            elif status == "failed":
                                                print_error(f"Generation failed: {status_data.get('error')}")
                                                break
                            else:
                                print_success("Result from cache!")
                                output_urls = gen_data.get("output_urls", [])
                                for url in output_urls:
                                    print_success(f"Image URL: {url}")
                    
                        elif gen_response.status == 402:
                            print_error("Insufficient credits")
                            error_text = await gen_response.text()
                            print(f"Error: {error_text[:200]}")
                        else:
                            print_error(f"Submit failed: {gen_response.status}")
                            error_text = await gen_response.text()
                            print(f"Error: {error_text[:200]}")
                            
                else:
                    print_error(f"Registration failed: {response.status}")
                    error_text = await response.text()
                    print(f"Response: {error_text[:200]}")
                    
        except Exception as e:
            print_error(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_flux_generation())