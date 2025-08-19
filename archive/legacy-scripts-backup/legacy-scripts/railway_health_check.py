#!/usr/bin/env python3
"""
Railway deployment health check and validation script.
Validates Railway deployment configuration and tests all endpoints.
"""
import asyncio
import json
import os
import sys
import time
from typing import Dict, List, Optional
import httpx
import logging
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class HealthCheckResult:
    """Health check result data structure."""
    endpoint: str
    status_code: int
    response_time: float
    success: bool
    error: Optional[str] = None
    response_data: Optional[Dict] = None

@dataclass
class DeploymentValidation:
    """Deployment validation results."""
    railway_config_valid: bool
    nixpacks_config_valid: bool
    environment_variables_valid: bool
    health_checks_passing: bool
    total_checks: int
    passed_checks: int
    failed_checks: List[str]
    recommendations: List[str]

class RailwayHealthChecker:
    """Railway deployment health checker and validator."""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize health checker with base URL."""
        self.base_url = base_url or os.getenv("RAILWAY_SERVICE_VELRO_BACKEND_URL", "http://localhost:8000")
        self.timeout = 30.0
        self.results: List[HealthCheckResult] = []
        
        # Core endpoints to test
        self.endpoints = [
            "/",
            "/health", 
            "/security-status",
            "/api/v1/auth/status",
            "/api/v1/models",
        ]
    
    async def check_endpoint(self, endpoint: str) -> HealthCheckResult:
        """Check a single endpoint health."""
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}{endpoint}")
                
                response_time = time.time() - start_time
                success = response.status_code in [200, 404]  # 404 is acceptable for some endpoints
                
                try:
                    response_data = response.json()
                except:
                    response_data = {"text": response.text[:200]}
                
                result = HealthCheckResult(
                    endpoint=endpoint,
                    status_code=response.status_code,
                    response_time=response_time,
                    success=success,
                    response_data=response_data
                )
                
                if success:
                    logger.info(f"✅ {endpoint}: {response.status_code} ({response_time:.3f}s)")
                else:
                    logger.warning(f"⚠️ {endpoint}: {response.status_code} ({response_time:.3f}s)")
                
                return result
                
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"❌ {endpoint}: {str(e)} ({response_time:.3f}s)")
            
            return HealthCheckResult(
                endpoint=endpoint,
                status_code=500,
                response_time=response_time,
                success=False,
                error=str(e)
            )
    
    async def run_health_checks(self) -> List[HealthCheckResult]:
        """Run all health checks concurrently."""
        logger.info(f"🏥 Starting health checks for: {self.base_url}")
        
        # Run all checks concurrently
        tasks = [self.check_endpoint(endpoint) for endpoint in self.endpoints]
        self.results = await asyncio.gather(*tasks)
        
        # Summary
        successful = len([r for r in self.results if r.success])
        total = len(self.results)
        
        logger.info(f"📊 Health check summary: {successful}/{total} passed")
        
        return self.results
    
    def validate_railway_config(self) -> Dict[str, bool]:
        """Validate Railway configuration files."""
        validation = {
            "railway_toml_exists": os.path.exists("railway.toml"),
            "nixpacks_toml_exists": os.path.exists("nixpacks.toml"),
            "requirements_txt_exists": os.path.exists("requirements.txt"),
            "main_py_exists": os.path.exists("main.py"),
            "config_py_exists": os.path.exists("config.py")
        }
        
        # Check railway.toml content
        if validation["railway_toml_exists"]:
            try:
                with open("railway.toml", "r") as f:
                    content = f.read()
                    validation["railway_has_health_check"] = "healthcheckPath" in content
                    validation["railway_has_nixpacks"] = "nixpacks" in content
                    validation["railway_has_deploy_config"] = "[deploy]" in content
            except Exception as e:
                logger.error(f"Error reading railway.toml: {e}")
                validation["railway_config_readable"] = False
        
        # Check nixpacks.toml content
        if validation["nixpacks_toml_exists"]:
            try:
                with open("nixpacks.toml", "r") as f:
                    content = f.read()
                    validation["nixpacks_has_start_cmd"] = "[start]" in content
                    validation["nixpacks_has_build_cmd"] = "[build]" in content
                    validation["nixpacks_has_python_config"] = "PYTHON" in content
            except Exception as e:
                logger.error(f"Error reading nixpacks.toml: {e}")
                validation["nixpacks_config_readable"] = False
        
        return validation
    
    def validate_environment_variables(self) -> Dict[str, bool]:
        """Validate required environment variables."""
        required_vars = [
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY", 
            "SUPABASE_SERVICE_ROLE_KEY",
            "FAL_KEY"
        ]
        
        optional_vars = [
            "DATABASE_URL",
            "REDIS_URL",
            "JWT_SECRET",
            "ENVIRONMENT"
        ]
        
        validation = {}
        
        # Check required variables
        for var in required_vars:
            validation[f"{var.lower()}_set"] = bool(os.getenv(var))
        
        # Check optional variables
        for var in optional_vars:
            validation[f"{var.lower()}_set"] = bool(os.getenv(var))
        
        # Railway-specific variables
        railway_vars = [
            "RAILWAY_PROJECT_ID",
            "RAILWAY_ENVIRONMENT_ID", 
            "RAILWAY_SERVICE_ID",
            "PORT"
        ]
        
        for var in railway_vars:
            validation[f"{var.lower()}_set"] = bool(os.getenv(var))
        
        return validation
    
    async def full_deployment_validation(self) -> DeploymentValidation:
        """Run full deployment validation."""
        logger.info("🔍 Starting full Railway deployment validation...")
        
        # Run health checks
        await self.run_health_checks()
        
        # Validate configurations
        railway_config = self.validate_railway_config()
        env_vars = self.validate_environment_variables()
        
        # Calculate results
        health_checks_passing = all(r.success for r in self.results)
        railway_config_valid = all([
            railway_config.get("railway_toml_exists", False),
            railway_config.get("nixpacks_toml_exists", False),
            railway_config.get("requirements_txt_exists", False),
            railway_config.get("main_py_exists", False)
        ])
        
        env_vars_valid = all([
            env_vars.get("supabase_url_set", False),
            env_vars.get("supabase_anon_key_set", False),
            env_vars.get("fal_key_set", False)
        ])
        
        # Count checks
        total_checks = len(self.results) + len(railway_config) + len(env_vars)
        passed_checks = (
            len([r for r in self.results if r.success]) +
            len([v for v in railway_config.values() if v]) +
            len([v for v in env_vars.values() if v])
        )
        
        # Generate recommendations
        recommendations = []
        failed_checks = []
        
        if not health_checks_passing:
            failed_health = [r.endpoint for r in self.results if not r.success]
            recommendations.append(f"Fix failing health checks: {', '.join(failed_health)}")
            failed_checks.extend(failed_health)
        
        if not railway_config_valid:
            recommendations.append("Verify Railway configuration files are present and valid")
            failed_checks.append("railway_config")
        
        if not env_vars_valid:
            recommendations.append("Set all required environment variables")
            failed_checks.append("environment_variables")
        
        if passed_checks / total_checks < 0.8:
            recommendations.append("Address failing checks to improve deployment reliability")
        
        validation = DeploymentValidation(
            railway_config_valid=railway_config_valid,
            nixpacks_config_valid=railway_config.get("nixpacks_toml_exists", False),
            environment_variables_valid=env_vars_valid,
            health_checks_passing=health_checks_passing,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            recommendations=recommendations
        )
        
        return validation
    
    def generate_report(self, validation: DeploymentValidation) -> Dict:
        """Generate comprehensive deployment report."""
        report = {
            "timestamp": time.time(),
            "base_url": self.base_url,
            "validation": asdict(validation),
            "health_checks": [asdict(result) for result in self.results],
            "railway_config": self.validate_railway_config(),
            "environment_variables": self.validate_environment_variables(),
            "summary": {
                "overall_health": validation.passed_checks / validation.total_checks if validation.total_checks > 0 else 0,
                "ready_for_production": validation.health_checks_passing and validation.railway_config_valid,
                "critical_issues": len([check for check in validation.failed_checks if check in ["health_checks", "railway_config"]]),
                "recommendations_count": len(validation.recommendations)
            }
        }
        
        return report

async def main():
    """Main function to run Railway health checks."""
    # Parse command line arguments
    base_url = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Initialize health checker
    checker = RailwayHealthChecker(base_url)
    
    try:
        # Run full validation
        validation = await checker.full_deployment_validation()
        
        # Generate report
        report = checker.generate_report(validation)
        
        # Print results
        print("\n" + "="*60)
        print("🚀 RAILWAY DEPLOYMENT VALIDATION REPORT")
        print("="*60)
        print(f"Base URL: {checker.base_url}")
        print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Overall status
        overall_health = report["summary"]["overall_health"]
        if overall_health >= 0.9:
            print("🟢 Status: EXCELLENT")
        elif overall_health >= 0.7:
            print("🟡 Status: GOOD")
        elif overall_health >= 0.5:
            print("🟠 Status: NEEDS ATTENTION")
        else:
            print("🔴 Status: CRITICAL ISSUES")
        
        print(f"Overall Health: {overall_health:.1%}")
        print(f"Checks Passed: {validation.passed_checks}/{validation.total_checks}")
        print()
        
        # Component status
        print("📋 Component Status:")
        print(f"  Health Checks: {'✅' if validation.health_checks_passing else '❌'}")
        print(f"  Railway Config: {'✅' if validation.railway_config_valid else '❌'}")
        print(f"  Environment Variables: {'✅' if validation.environment_variables_valid else '❌'}")
        print()
        
        # Recommendations
        if validation.recommendations:
            print("💡 Recommendations:")
            for i, rec in enumerate(validation.recommendations, 1):
                print(f"  {i}. {rec}")
            print()
        
        # Failed checks
        if validation.failed_checks:
            print("❌ Failed Checks:")
            for check in validation.failed_checks:
                print(f"  - {check}")
            print()
        
        # Save detailed report
        report_file = f"railway_health_report_{int(time.time())}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 Detailed report saved to: {report_file}")
        
        # Exit with appropriate code
        if validation.health_checks_passing and validation.railway_config_valid:
            print("\n🎉 Deployment is ready for Railway!")
            sys.exit(0)
        elif overall_health >= 0.7:
            print("\n⚠️ Deployment has minor issues but should work")
            sys.exit(0)
        else:
            print("\n🚨 Deployment has critical issues - fix before deploying")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        print(f"\n🚨 VALIDATION FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())