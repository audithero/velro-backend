#!/usr/bin/env python3
"""
Monitor Railway deployment and validate route fixes in production.

This script:
1. Waits for Railway deployment to complete
2. Tests the production endpoints to verify fixes
3. Validates all critical routes are working
"""

import asyncio
import aiohttp
import logging
import time
import sys
from typing import Dict, List, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Production URLs
BACKEND_URL = "https://velro-003-backend-production.up.railway.app"
FRONTEND_URL = "https://velro-frontend-production.up.railway.app"

async def check_deployment_health() -> bool:
    """Check if the deployment is healthy."""
    logger.info("🔍 Checking deployment health...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Check health endpoint
            async with session.get(f"{BACKEND_URL}/health", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Health check passed: {data.get('status', 'unknown')}")
                    return True
                else:
                    logger.error(f"❌ Health check failed with status {response.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return False

async def test_projects_route() -> bool:
    """Test that projects route has no duplicates and works correctly."""
    logger.info("🔍 Testing projects route...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test both with and without trailing slash
            test_urls = [
                f"{BACKEND_URL}/api/v1/projects",
                f"{BACKEND_URL}/api/v1/projects/"
            ]
            
            for url in test_urls:
                async with session.get(url, timeout=10) as response:
                    logger.info(f"📍 Testing {url} - Status: {response.status}")
                    
                    if response.status == 401:
                        logger.info("✅ Projects endpoint returns 401 (unauthorized) as expected")
                        return True
                    elif response.status == 308:
                        logger.info("✅ Trailing slash redirect working (308)")
                        return True
                    elif response.status == 405:
                        logger.error(f"❌ Method not allowed (405) - trailing slash issue not fixed")
                        return False
                    elif response.status == 500:
                        logger.error(f"❌ Internal server error (500) - duplicate route issue")
                        return False
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Projects route test failed: {e}")
        return False

async def test_generations_stats_route() -> bool:
    """Test that generations/stats route doesn't return 500."""
    logger.info("🔍 Testing generations/stats route...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test both with and without trailing slash
            test_urls = [
                f"{BACKEND_URL}/api/v1/generations/stats",
                f"{BACKEND_URL}/api/v1/generations/stats/"
            ]
            
            for url in test_urls:
                async with session.get(url, timeout=10) as response:
                    logger.info(f"📍 Testing {url} - Status: {response.status}")
                    
                    if response.status == 401:
                        logger.info("✅ Stats endpoint returns 401 (unauthorized) as expected")
                        return True
                    elif response.status == 308:
                        logger.info("✅ Trailing slash redirect working (308)")
                        return True
                    elif response.status == 500:
                        logger.error(f"❌ Internal server error (500) - auth token issue not fixed")
                        return False
                    elif response.status == 405:
                        logger.error(f"❌ Method not allowed (405) - trailing slash issue")
                        return False
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Stats route test failed: {e}")
        return False

async def test_trailing_slash_redirects() -> bool:
    """Test that trailing slash redirects work correctly."""
    logger.info("🔍 Testing trailing slash redirect middleware...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test various API endpoints without trailing slashes
            test_paths = [
                "/api/v1/generations",
                "/api/v1/projects", 
                "/api/v1/models",
                "/api/v1/credits"
            ]
            
            for path in test_paths:
                url = f"{BACKEND_URL}{path}"
                async with session.get(url, allow_redirects=False, timeout=10) as response:
                    logger.info(f"📍 Testing {url} - Status: {response.status}")
                    
                    if response.status == 308:
                        location = response.headers.get('Location', '')
                        if location.endswith(path + '/'):
                            logger.info(f"✅ Redirect to {location} working correctly")
                        else:
                            logger.warning(f"⚠️ Redirect to {location} - unexpected destination")
                    elif response.status == 401:
                        logger.info("✅ Direct access returns 401 (unauthorized) - no redirect needed")
                    elif response.status == 405:
                        logger.error(f"❌ Method not allowed (405) for {url}")
                        return False
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Trailing slash test failed: {e}")
        return False

async def test_cors_configuration() -> bool:
    """Test CORS configuration is working."""
    logger.info("🔍 Testing CORS configuration...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test CORS preflight for auth endpoint
            headers = {
                'Origin': FRONTEND_URL,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Authorization,Content-Type'
            }
            
            async with session.options(f"{BACKEND_URL}/api/v1/auth/login", headers=headers, timeout=10) as response:
                logger.info(f"📍 CORS preflight test - Status: {response.status}")
                
                if response.status == 200:
                    cors_origin = response.headers.get('Access-Control-Allow-Origin')
                    cors_methods = response.headers.get('Access-Control-Allow-Methods')
                    logger.info(f"✅ CORS Origin: {cors_origin}")
                    logger.info(f"✅ CORS Methods: {cors_methods}")
                    return True
                else:
                    logger.error(f"❌ CORS preflight failed with status {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ CORS test failed: {e}")
        return False

async def wait_for_deployment(max_wait_minutes: int = 10) -> bool:
    """Wait for deployment to complete and become healthy."""
    logger.info(f"⏳ Waiting for deployment to complete (max {max_wait_minutes} minutes)...")
    
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    
    while time.time() - start_time < max_wait_seconds:
        if await check_deployment_health():
            elapsed = int(time.time() - start_time)
            logger.info(f"✅ Deployment healthy after {elapsed} seconds")
            return True
        
        logger.info("⏳ Waiting for deployment...")
        await asyncio.sleep(30)  # Wait 30 seconds between checks
    
    logger.error(f"❌ Deployment not healthy after {max_wait_minutes} minutes")
    return False

async def main():
    """Main monitoring function."""
    logger.info("🚀 Starting deployment monitoring...")
    logger.info(f"🎯 Backend URL: {BACKEND_URL}")
    logger.info(f"🎯 Frontend URL: {FRONTEND_URL}")
    
    # Wait for deployment
    if not await wait_for_deployment():
        logger.error("💥 Deployment failed to become healthy")
        return False
    
    # Run all tests
    tests = [
        ("Projects Route", test_projects_route()),
        ("Generations Stats Route", test_generations_stats_route()), 
        ("Trailing Slash Redirects", test_trailing_slash_redirects()),
        ("CORS Configuration", test_cors_configuration())
    ]
    
    results = []
    for test_name, test_coro in tests:
        logger.info(f"\n📋 Running test: {test_name}")
        try:
            result = await test_coro
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
        except Exception as e:
            logger.error(f"💥 {test_name}: ERROR - {e}")
            results.append((test_name, False))
        
        # Wait between tests
        await asyncio.sleep(2)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("📊 PRODUCTION DEPLOYMENT VALIDATION SUMMARY")
    logger.info("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name:.<40} {status}")
    
    logger.info("-"*60)
    logger.info(f"TOTAL: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 DEPLOYMENT VALIDATION SUCCESSFUL!")
        logger.info("✅ All route fixes are working in production")
        logger.info(f"🌐 Backend available at: {BACKEND_URL}")
        return True
    else:
        logger.error("💥 DEPLOYMENT VALIDATION FAILED!")
        logger.error("❌ Some route fixes are not working in production")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)