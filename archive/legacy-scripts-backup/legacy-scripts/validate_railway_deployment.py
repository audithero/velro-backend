#!/usr/bin/env python3
"""
Railway Deployment Validation
Checks Railway deployment status and triggers redeploy if needed.
"""

import asyncio
import aiohttp
import json
import time
import logging
import subprocess
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_railway_status():
    """Check Railway deployment status."""
    
    print("🚂 Railway Deployment Validation")
    print("=" * 50)
    
    # Check if Railway CLI is available
    try:
        result = subprocess.run(["railway", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Railway CLI: {result.stdout.strip()}")
            railway_cli_available = True
        else:
            print("❌ Railway CLI not available")
            railway_cli_available = False
    except FileNotFoundError:
        print("❌ Railway CLI not installed")
        railway_cli_available = False
    
    # Check environment variables
    railway_token = os.getenv("RAILWAY_TOKEN")
    railway_project = os.getenv("RAILWAY_PROJECT_ID")
    railway_service = os.getenv("RAILWAY_SERVICE_ID")
    
    print(f"\n🔧 Environment Check:")
    print(f"   RAILWAY_TOKEN: {'✅ Set' if railway_token else '❌ Not set'}")
    print(f"   RAILWAY_PROJECT_ID: {'✅ Set' if railway_project else '❌ Not set'}")
    print(f"   RAILWAY_SERVICE_ID: {'✅ Set' if railway_service else '❌ Not set'}")
    
    if railway_cli_available:
        # Get deployment status
        print(f"\n📊 Railway Status:")
        try:
            # Get project info
            result = subprocess.run(["railway", "status"], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"   Project Status: ✅ Connected")
                print(f"   Output: {result.stdout}")
            else:
                print(f"   Project Status: ❌ Error")
                print(f"   Error: {result.stderr}")
        except Exception as e:
            print(f"   Status Check Error: {e}")
        
        # Get recent deployments
        print(f"\n📋 Recent Deployments:")
        try:
            result = subprocess.run(["railway", "logs", "--limit", "10"], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"   Recent logs retrieved successfully")
                print(f"   Logs preview:")
                for line in result.stdout.split('\n')[:5]:
                    if line.strip():
                        print(f"     {line}")
            else:
                print(f"   ❌ Failed to get logs: {result.stderr}")
        except Exception as e:
            print(f"   Logs Error: {e}")
    
    # Test various potential URLs
    potential_urls = [
        "https://velro-backend-production.up.railway.app",
        "https://velro-backend.up.railway.app", 
        "https://velro-production.up.railway.app",
        "https://backend-production.up.railway.app"
    ]
    
    print(f"\n🔍 Testing Potential URLs:")
    working_url = None
    
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url in potential_urls:
            try:
                start_time = time.time()
                async with session.get(url) as response:
                    duration = (time.time() - start_time) * 1000
                    print(f"   {url}: {response.status} ({duration:.1f}ms)")
                    
                    if response.status == 200:
                        working_url = url
                        try:
                            data = await response.json()
                            if "message" in data and "Velro" in data["message"]:
                                print(f"     ✅ Found Velro API!")
                                break
                        except:
                            pass
                    elif response.status != 404:
                        print(f"     ⚠️ Service responding but not 200")
                        
            except Exception as e:
                print(f"   {url}: ❌ {e}")
    
    if working_url:
        print(f"\n✅ Working URL found: {working_url}")
        return working_url
    else:
        print(f"\n❌ No working URLs found")
        return None

async def trigger_railway_deployment():
    """Trigger a new Railway deployment."""
    print(f"\n🚀 Triggering Railway Deployment...")
    
    try:
        # Try to trigger a redeploy
        result = subprocess.run(["railway", "redeploy"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Redeploy triggered successfully")
            print(f"   Output: {result.stdout}")
            return True
        else:
            print(f"❌ Redeploy failed")
            print(f"   Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Redeploy error: {e}")
        return False

async def wait_for_deployment(url: str, max_wait: int = 300):
    """Wait for deployment to become available."""
    print(f"\n⏳ Waiting for deployment at {url}...")
    
    start_time = time.time()
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while time.time() - start_time < max_wait:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            if "message" in data and "Velro" in data["message"]:
                                elapsed = time.time() - start_time
                                print(f"✅ Deployment ready! ({elapsed:.1f}s)")
                                return True
                        except:
                            pass
                
                print(f"   Waiting... ({int(time.time() - start_time)}s)")
                await asyncio.sleep(10)
                
            except Exception as e:
                elapsed = time.time() - start_time
                if elapsed > 60:  # Only log errors after 1 minute
                    print(f"   Still waiting... ({int(elapsed)}s) - {e}")
                await asyncio.sleep(10)
    
    print(f"❌ Deployment not ready after {max_wait}s")
    return False

async def main():
    """Main deployment validation."""
    
    # Step 1: Check current status
    working_url = await check_railway_status()
    
    if working_url:
        print(f"\n🎉 Backend is already working at: {working_url}")
        return working_url
    
    # Step 2: Try to trigger redeploy
    print(f"\n🔄 Backend not accessible, attempting redeploy...")
    redeploy_success = await trigger_railway_deployment()
    
    if not redeploy_success:
        print(f"\n❌ Could not trigger redeploy")
        print(f"\n📋 Manual Steps Required:")
        print(f"   1. Check Railway dashboard for deployment status")
        print(f"   2. Verify environment variables are set correctly")
        print(f"   3. Check recent commit pushed to trigger deploy")
        print(f"   4. Review deployment logs for errors")
        return None
    
    # Step 3: Wait for deployment
    test_url = "https://velro-backend-production.up.railway.app"
    deployment_ready = await wait_for_deployment(test_url)
    
    if deployment_ready:
        return test_url
    else:
        print(f"\n❌ Deployment timeout")
        return None

if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print(f"\n✅ Backend ready for CORS testing at: {result}")
        exit(0)
    else:
        print(f"\n❌ Backend deployment validation failed")
        exit(1)