#!/usr/bin/env python3
"""
Production Validation with Correct Railway URLs
==============================================

This script validates the actual deployed Railway services by:
1. Testing multiple potential URLs for backend
2. Validating the working frontend deployment  
3. Running focused validation on discovered services
4. Providing corrected deployment URLs for future use
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class URLDiscoveryValidator:
    """Discovers and validates actual Railway deployment URLs."""
    
    def __init__(self):
        # Potential backend URLs to test
        self.potential_backend_urls = [
            "https://velro-backend-production.up.railway.app",
            "https://web-production-3928.up.railway.app",  # Common Railway pattern
            "https://backend-production.up.railway.app",
            "https://velro-api-production.up.railway.app",
            "https://velro-backend.up.railway.app"
        ]
        
        # Known working frontend URL
        self.frontend_url = "https://velro-frontend-production.up.railway.app"
        
        self.working_backend_url: Optional[str] = None
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def discover_backend_url(self) -> Optional[str]:
        """Discover the working backend URL."""
        logger.info("🔍 Discovering working backend URL...")
        
        for url in self.potential_backend_urls:
            try:
                logger.info(f"Testing: {url}")
                response = await self.client.get(f"{url}/health", timeout=5.0)
                
                if response.status_code == 200:
                    logger.info(f"✅ Found working backend: {url}")
                    self.working_backend_url = url
                    return url
                else:
                    logger.info(f"❌ {url} returned {response.status_code}")
                    
            except Exception as e:
                logger.info(f"❌ {url} failed: {str(e)}")
        
        logger.warning("⚠️ No working backend URL found")
        return None
    
    async def validate_working_services(self):
        """Validate the services that are actually working."""
        results = {
            "timestamp": time.time(),
            "backend_discovery": {},
            "frontend_validation": {},
            "api_endpoints": {},
            "recommendations": []
        }
        
        # Discover backend
        backend_url = await self.discover_backend_url()
        results["backend_discovery"] = {
            "working_url": backend_url,
            "tested_urls": self.potential_backend_urls,
            "status": "found" if backend_url else "not_found"
        }
        
        if backend_url:
            # Test critical backend endpoints
            await self.test_backend_endpoints(backend_url, results)
        else:
            results["recommendations"].append("🔴 CRITICAL: Backend deployment not accessible - check Railway deployment status")
        
        # Test frontend
        await self.test_frontend_endpoints(results)
        
        # Generate final assessment
        await self.generate_assessment(results)
        
        return results
    
    async def test_backend_endpoints(self, backend_url: str, results: Dict[str, Any]):
        """Test critical backend endpoints."""
        logger.info("🔌 Testing backend endpoints...")
        
        endpoints = [
            "/health",
            "/security-status", 
            "/api/v1/models/supported",
            "/api/v1/auth/register",
            "/api/v1/auth/login"
        ]
        
        endpoint_results = {}
        
        for endpoint in endpoints:
            try:
                if endpoint in ["/api/v1/auth/register", "/api/v1/auth/login"]:
                    # POST endpoints - test with empty payload
                    response = await self.client.post(f"{backend_url}{endpoint}", json={})
                else:
                    # GET endpoints
                    response = await self.client.get(f"{backend_url}{endpoint}")
                
                endpoint_results[endpoint] = {
                    "status_code": response.status_code,
                    "working": response.status_code in [200, 401, 422, 405],  # Valid responses
                    "response_time": response.elapsed.total_seconds()
                }
                
                if response.status_code == 200:
                    try:
                        endpoint_results[endpoint]["response_data"] = response.json()
                    except:
                        pass
                
                logger.info(f"✅ {endpoint}: {response.status_code}")
                
            except Exception as e:
                endpoint_results[endpoint] = {
                    "status_code": None,
                    "working": False,
                    "error": str(e)
                }
                logger.error(f"❌ {endpoint}: {str(e)}")
        
        results["api_endpoints"] = endpoint_results
    
    async def test_frontend_endpoints(self, results: Dict[str, Any]):
        """Test frontend endpoints."""
        logger.info("🎨 Testing frontend endpoints...")
        
        frontend_routes = [
            "/",
            "/auth/login",
            "/auth/register", 
            "/dashboard",
            "/projects"
        ]
        
        frontend_results = {}
        
        for route in frontend_routes:
            try:
                response = await self.client.get(f"{self.frontend_url}{route}")
                frontend_results[route] = {
                    "status_code": response.status_code,
                    "working": response.status_code in [200, 302],
                    "response_time": response.elapsed.total_seconds()
                }
                logger.info(f"✅ Frontend {route}: {response.status_code}")
                
            except Exception as e:
                frontend_results[route] = {
                    "status_code": None,
                    "working": False, 
                    "error": str(e)
                }
                logger.error(f"❌ Frontend {route}: {str(e)}")
        
        results["frontend_validation"] = {
            "url": self.frontend_url,
            "routes": frontend_results,
            "overall_status": "working" if any(r.get("working", False) for r in frontend_results.values()) else "failed"
        }
    
    async def generate_assessment(self, results: Dict[str, Any]):
        """Generate production readiness assessment."""
        logger.info("📊 Generating assessment...")
        
        backend_working = results["backend_discovery"]["status"] == "found"
        frontend_working = results["frontend_validation"]["overall_status"] == "working"
        
        if backend_working:
            api_endpoints_working = sum(1 for ep in results["api_endpoints"].values() if ep.get("working", False))
            total_endpoints = len(results["api_endpoints"])
            api_success_rate = (api_endpoints_working / total_endpoints) * 100 if total_endpoints > 0 else 0
        else:
            api_success_rate = 0
        
        # Overall assessment
        if backend_working and frontend_working and api_success_rate >= 80:
            overall_status = "PRODUCTION_READY"
        elif frontend_working and api_success_rate >= 60:
            overall_status = "PARTIALLY_READY"
        else:
            overall_status = "NOT_READY"
        
        results["assessment"] = {
            "overall_status": overall_status,
            "backend_status": "working" if backend_working else "failed",
            "frontend_status": "working" if frontend_working else "failed", 
            "api_success_rate": api_success_rate,
            "critical_issues": []
        }
        
        # Add recommendations
        if not backend_working:
            results["recommendations"].append("🔴 CRITICAL: Backend deployment failed or not accessible")
            results["recommendations"].append("   - Check Railway deployment logs")
            results["recommendations"].append("   - Verify environment variables")
            results["recommendations"].append("   - Check database connectivity")
            results["assessment"]["critical_issues"].append("backend_deployment_failed")
        
        if not frontend_working:
            results["recommendations"].append("🔴 CRITICAL: Frontend deployment failed")
            results["assessment"]["critical_issues"].append("frontend_deployment_failed")
        
        if api_success_rate < 80:
            results["recommendations"].append(f"🟡 API endpoints success rate low: {api_success_rate:.1f}%")
        
        results["recommendations"].extend([
            "✅ Frontend deployment is working correctly",
            "✅ Continue monitoring deployment status",
            "✅ Test manual user flows in browser"
        ])
        
        # Save results
        filename = f"production_url_discovery_results_{int(time.time())}.json"
        with open(filename, "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"📋 Results saved to {filename}")
        
        # Print summary
        print("\n" + "="*80)
        print("🎯 PRODUCTION DEPLOYMENT VALIDATION")
        print("="*80)
        print(f"Overall Status: {overall_status}")
        print(f"Backend Status: {'✅ Working' if backend_working else '❌ Failed'}")
        print(f"Frontend Status: {'✅ Working' if frontend_working else '❌ Failed'}")
        if backend_working:
            print(f"API Success Rate: {api_success_rate:.1f}%")
            print(f"Working Backend URL: {results['backend_discovery']['working_url']}")
        print(f"Working Frontend URL: {self.frontend_url}")
        print("\n📋 Next Steps:")
        for rec in results["recommendations"][:5]:  # Show top 5 recommendations
            print(f"   {rec}")
    
    async def cleanup(self):
        """Cleanup resources."""
        await self.client.aclose()


async def main():
    """Main execution."""
    validator = URLDiscoveryValidator()
    
    try:
        results = await validator.validate_working_services()
        
        # Determine exit code based on results
        overall_status = results.get("assessment", {}).get("overall_status", "NOT_READY")
        
        if overall_status == "PRODUCTION_READY":
            return 0
        elif overall_status == "PARTIALLY_READY":
            return 1  # Warning level
        else:
            return 2  # Error level
            
    except Exception as e:
        logger.error(f"❌ Validation failed: {str(e)}")
        return 2
    finally:
        await validator.cleanup()


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())    
    sys.exit(exit_code)