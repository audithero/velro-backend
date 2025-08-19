#!/usr/bin/env python3
"""
Railway Deployment Investigation Tool
===================================

This tool investigates Railway deployment status and provides
actionable recommendations for fixing backend deployment issues.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List
import httpx
import subprocess
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RailwayDeploymentInvestigator:
    """Investigates Railway deployment issues and provides solutions."""
    
    def __init__(self):
        self.frontend_url = "https://velro-frontend-production.up.railway.app"
        self.client = httpx.AsyncClient(timeout=15.0)
        
        # Common Railway URL patterns to test
        self.url_patterns = [
            "https://velro-backend-production.up.railway.app",
            "https://web-production.up.railway.app", 
            "https://backend-production.up.railway.app",
            "https://api-production.up.railway.app",
            "https://velro-api.up.railway.app",
            "https://velro-backend.railway.app",
            # Add more specific patterns
            "https://velro-backend-production-*.up.railway.app",
            "https://web-production-*.up.railway.app"
        ]
    
    async def investigate_deployment(self) -> Dict[str, Any]:
        """Conduct comprehensive deployment investigation."""
        logger.info("🔍 Starting Railway deployment investigation...")
        
        investigation = {
            "timestamp": time.time(),
            "investigation_id": f"railway_investigation_{int(time.time())}",
            "frontend_status": {},
            "backend_investigation": {},
            "environment_analysis": {},
            "recommendations": [],
            "action_plan": []
        }
        
        # 1. Validate frontend is working
        await self.investigate_frontend(investigation)
        
        # 2. Deep dive into backend deployment issues
        await self.investigate_backend_deployment(investigation)
        
        # 3. Analyze environment and configuration
        await self.analyze_environment_config(investigation)
        
        # 4. Check for common Railway deployment issues
        await self.check_common_railway_issues(investigation)
        
        # 5. Generate action plan
        self.generate_action_plan(investigation)
        
        # Save investigation report
        filename = f"railway_investigation_{investigation['investigation_id']}.json"
        with open(filename, "w") as f:
            json.dump(investigation, f, indent=2)
        
        logger.info(f"📋 Investigation report saved to {filename}")
        return investigation
    
    async def investigate_frontend(self, investigation: Dict[str, Any]):
        """Investigate frontend deployment status."""
        logger.info("🎨 Investigating frontend deployment...")
        
        try:
            response = await self.client.get(self.frontend_url)
            
            investigation["frontend_status"] = {
                "url": self.frontend_url,
                "accessible": response.status_code == 200,
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds(),
                "headers": dict(response.headers),
                "railway_headers": {k: v for k, v in response.headers.items() if "railway" in k.lower()}
            }
            
            if response.status_code == 200:
                logger.info("✅ Frontend deployment is working correctly")
                
                # Check if frontend is trying to connect to backend
                try:
                    content = response.text
                    if "api" in content.lower() or "backend" in content.lower():
                        investigation["frontend_status"]["backend_references"] = True
                        logger.info("📡 Frontend contains backend/API references")
                    else:
                        investigation["frontend_status"]["backend_references"] = False
                except:
                    investigation["frontend_status"]["backend_references"] = "unknown"
            else:
                logger.error(f"❌ Frontend deployment issues: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Frontend investigation failed: {str(e)}")
            investigation["frontend_status"] = {
                "url": self.frontend_url,
                "accessible": False,
                "error": str(e)
            }
    
    async def investigate_backend_deployment(self, investigation: Dict[str, Any]):
        """Deep investigation of backend deployment issues."""
        logger.info("🔧 Investigating backend deployment...")
        
        backend_results = {
            "tested_urls": [],
            "all_404": True,
            "railway_responses": [],
            "potential_issues": []
        }
        
        # Test all potential backend URLs
        for url in self.url_patterns:
            if "*" in url:
                # Skip wildcard patterns for now
                continue
                
            try:
                logger.info(f"Testing: {url}")
                response = await self.client.get(f"{url}/health", timeout=5.0)
                
                result = {
                    "url": url,
                    "status_code": response.status_code,
                    "response_time": response.elapsed.total_seconds(),
                    "headers": dict(response.headers),
                    "railway_headers": {k: v for k, v in response.headers.items() if "railway" in k.lower()}
                }
                
                # Check for Railway-specific error responses
                if response.status_code == 404:
                    try:
                        error_data = response.json()
                        if "Application not found" in error_data.get("message", ""):
                            result["railway_error"] = "application_not_found"
                            backend_results["potential_issues"].append(f"Railway application not found at {url}")
                    except:
                        pass
                elif response.status_code == 200:
                    backend_results["all_404"] = False
                    result["working"] = True
                    logger.info(f"✅ Found working backend: {url}")
                
                backend_results["tested_urls"].append(result)
                backend_results["railway_responses"].append(result)
                
            except asyncio.TimeoutError:
                backend_results["tested_urls"].append({
                    "url": url,
                    "error": "timeout",
                    "potential_issue": "deployment_not_responding"
                })
                backend_results["potential_issues"].append(f"Timeout connecting to {url}")
            except Exception as e:
                backend_results["tested_urls"].append({
                    "url": url,
                    "error": str(e),
                    "potential_issue": "connection_failed"
                })
        
        investigation["backend_investigation"] = backend_results
        
        # Analyze Railway-specific patterns
        railway_errors = [r for r in backend_results["railway_responses"] if r.get("railway_error")]
        if railway_errors:
            investigation["backend_investigation"]["railway_diagnosis"] = "application_not_deployed_or_removed"
            logger.error("🚨 Railway indicates application not found - deployment may have failed")
        else:
            investigation["backend_investigation"]["railway_diagnosis"] = "unknown_deployment_issue"
    
    async def analyze_environment_config(self, investigation: Dict[str, Any]):
        """Analyze environment configuration issues."""
        logger.info("⚙️ Analyzing environment configuration...")
        
        env_analysis = {
            "local_config_files": [],
            "railway_config_files": [],
            "potential_config_issues": []
        }
        
        # Check for local configuration files
        config_files = [
            ".env",
            "railway.json",
            "nixpacks.toml", 
            "Procfile",
            "Dockerfile",
            "requirements.txt",
            "package.json"
        ]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                env_analysis["local_config_files"].append(config_file)
                
                # Basic config file analysis
                try:
                    with open(config_file, 'r') as f:
                        content = f.read()
                        
                    if config_file == "requirements.txt":
                        if "fastapi" not in content.lower():
                            env_analysis["potential_config_issues"].append("FastAPI not in requirements.txt")
                    elif config_file == "Procfile":
                        if "web:" not in content:
                            env_analysis["potential_config_issues"].append("No web process in Procfile")
                    elif config_file == ".env":
                        if "JWT_SECRET" not in content:
                            env_analysis["potential_config_issues"].append("Missing JWT_SECRET in .env")
                        
                except Exception as e:
                    env_analysis["potential_config_issues"].append(f"Could not read {config_file}: {str(e)}")
        
        investigation["environment_analysis"] = env_analysis
    
    async def check_common_railway_issues(self, investigation: Dict[str, Any]):
        """Check for common Railway deployment issues."""
        logger.info("🚂 Checking common Railway deployment issues...")
        
        common_issues = {
            "deployment_failures": [],
            "configuration_issues": [],
            "service_issues": []
        }
        
        # Check if backend deployment exists at all
        if investigation["backend_investigation"]["all_404"]:
            common_issues["deployment_failures"].extend([
                "Backend service not deployed to Railway",
                "Backend deployment failed or was removed",
                "Incorrect Railway service configuration",
                "Build process failure during deployment"
            ])
        
        # Check environment configuration
        env_config = investigation.get("environment_analysis", {})
        if "Procfile" not in env_config.get("local_config_files", []):
            common_issues["configuration_issues"].append("Missing Procfile for Railway deployment")
        
        if "requirements.txt" not in env_config.get("local_config_files", []):
            common_issues["configuration_issues"].append("Missing requirements.txt")
        
        # Check for service connectivity issues
        frontend_working = investigation.get("frontend_status", {}).get("accessible", False)
        if frontend_working and investigation["backend_investigation"]["all_404"]:
            common_issues["service_issues"].extend([
                "Frontend deployed successfully but backend failed",
                "Possible database connectivity issues",
                "Environment variables not properly configured",
                "Port configuration issues"
            ])
        
        investigation["common_railway_issues"] = common_issues
    
    def generate_action_plan(self, investigation: Dict[str, Any]):
        """Generate specific action plan based on investigation findings."""
        logger.info("📋 Generating action plan...")
        
        action_plan = []
        recommendations = []
        
        # Critical actions based on findings
        if investigation["backend_investigation"]["all_404"]:
            action_plan.extend([
                "1. IMMEDIATE: Check Railway dashboard for backend deployment status",
                "2. IMMEDIATE: Review Railway deployment logs for error messages",
                "3. IMMEDIATE: Verify all environment variables are set in Railway",
                "4. IMMEDIATE: Check if backend service exists in Railway project"
            ])
            
            recommendations.extend([
                "🔴 CRITICAL: Backend deployment completely failed",
                "🔴 Verify Railway project has backend service configured",
                "🔴 Check Railway build logs for deployment errors",
                "🔴 Ensure environment variables match production requirements"
            ])
        
        # Configuration-based actions
        env_issues = investigation.get("environment_analysis", {}).get("potential_config_issues", [])
        if env_issues:
            action_plan.extend([
                "5. Fix configuration issues identified:",
                *[f"   - {issue}" for issue in env_issues]
            ])
        
        # Railway-specific actions
        common_issues = investigation.get("common_railway_issues", {})
        if common_issues.get("deployment_failures"):
            action_plan.extend([
                "6. Address deployment failures:",
                "   - Re-deploy backend service to Railway",
                "   - Verify Procfile configuration",
                "   - Check build process compatibility"
            ])
        
        # Recovery actions
        action_plan.extend([
            "7. RECOVERY STEPS:",
            "   - Test backend deployment locally first",
            "   - Deploy to Railway with verbose logging",
            "   - Monitor deployment logs in real-time",
            "   - Verify health endpoint after deployment"
        ])
        
        # Success criteria
        action_plan.extend([
            "8. SUCCESS CRITERIA:",
            "   - Backend health endpoint returns 200",
            "   - API endpoints accessible and responding",
            "   - Frontend can connect to backend successfully",
            "   - End-to-end user flows working"
        ])
        
        investigation["recommendations"] = recommendations
        investigation["action_plan"] = action_plan
        
        # Priority assessment
        if investigation["backend_investigation"]["all_404"]:
            investigation["priority"] = "CRITICAL"
            investigation["deployment_status"] = "FAILED"
        elif investigation.get("frontend_status", {}).get("accessible", False):
            investigation["priority"] = "HIGH"
            investigation["deployment_status"] = "PARTIAL"
        else:
            investigation["priority"] = "CRITICAL"
            investigation["deployment_status"] = "COMPLETE_FAILURE"
    
    async def print_investigation_summary(self, investigation: Dict[str, Any]):
        """Print investigation summary."""
        print("\n" + "="*80)
        print("🔍 RAILWAY DEPLOYMENT INVESTIGATION SUMMARY")
        print("="*80)
        
        # Overall status
        deployment_status = investigation.get("deployment_status", "UNKNOWN")
        priority = investigation.get("priority", "UNKNOWN")
        
        print(f"Deployment Status: {deployment_status}")
        print(f"Priority Level: {priority}")
        
        # Frontend status
        frontend = investigation.get("frontend_status", {})
        print(f"Frontend Status: {'✅ Working' if frontend.get('accessible') else '❌ Failed'}")
        
        # Backend status
        backend = investigation.get("backend_investigation", {})
        print(f"Backend Status: {'❌ All URLs return 404' if backend.get('all_404') else '✅ Some endpoints working'}")
        
        # Critical issues
        print(f"\n🚨 Critical Issues:")
        recommendations = investigation.get("recommendations", [])
        for rec in recommendations[:3]:
            print(f"   {rec}")
        
        # Immediate actions
        print(f"\n📋 Immediate Actions:")
        action_plan = investigation.get("action_plan", [])
        for action in action_plan[:5]:
            print(f"   {action}")
        
        print(f"\n📄 Full investigation report saved to: railway_investigation_{investigation['investigation_id']}.json")
    
    async def cleanup(self):
        """Cleanup resources."""
        await self.client.aclose()


async def main():
    """Main investigation execution."""
    investigator = RailwayDeploymentInvestigator()
    
    try:
        investigation = await investigator.investigate_deployment()
        await investigator.print_investigation_summary(investigation)
        
        # Return exit code based on deployment status
        deployment_status = investigation.get("deployment_status", "UNKNOWN")
        if deployment_status == "FAILED":
            return 2  # Critical failure
        elif deployment_status == "PARTIAL":
            return 1  # Warning
        else:
            return 0  # Success
            
    except Exception as e:
        logger.error(f"❌ Investigation failed: {str(e)}")
        return 2
    finally:
        await investigator.cleanup()


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)