"""
Service Account Health Check Service
=====================================
Monitors and validates service account JWT and database connectivity.
Provides automated alerts and diagnostics.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import aiohttp
import json

from config_service_account import get_service_config
from repositories.user_repository_refactored import UserRepository

logger = logging.getLogger(__name__)

class HealthCheckService:
    """
    Service for monitoring service account health.
    """
    
    def __init__(self):
        """Initialize health check service."""
        self.config = get_service_config()
        self.enabled = os.getenv("HEALTH_CHECK_ENABLED", "true").lower() == "true"
        self.interval_minutes = int(os.getenv("HEALTH_CHECK_INTERVAL_MINUTES", 60))
        self.webhook_url = os.getenv("HEALTH_CHECK_WEBHOOK_URL")
        self._last_check: Optional[datetime] = None
        self._last_status: Optional[Dict[str, Any]] = None
        self._user_repo: Optional[UserRepository] = None
        
    async def initialize(self):
        """Initialize the health check service."""
        if self.enabled:
            # Initialize user repository with service JWT
            supabase_url = os.getenv("SUPABASE_URL")
            if not supabase_url:
                raise ValueError("SUPABASE_URL not configured")
            
            self._user_repo = UserRepository(
                supabase_url=supabase_url,
                service_jwt=self.config.service_jwt
            )
            
            # Verify initial connection
            initialized = await self._user_repo.initialize()
            if not initialized:
                logger.error("Failed to initialize user repository with service JWT")
                raise RuntimeError("Service account initialization failed")
            
            logger.info("Health check service initialized successfully")
    
    async def run_health_check(self) -> Dict[str, Any]:
        """
        Run a comprehensive health check.
        
        Returns:
            Health status dictionary
        """
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "velro-backend",
            "checks": {}
        }
        
        # 1. Check JWT configuration
        jwt_health = self.config.health_check()
        results["checks"]["jwt_configuration"] = jwt_health
        
        # 2. Check database connectivity
        if self._user_repo:
            db_health = await self._user_repo.health_check()
            results["checks"]["database"] = db_health
        else:
            results["checks"]["database"] = {
                "status": "not_initialized",
                "error": "User repository not initialized"
            }
        
        # 3. Check service account exists in database
        service_account_health = await self._check_service_account()
        results["checks"]["service_account"] = service_account_health
        
        # 4. Test RLS policies
        rls_health = await self._check_rls_policies()
        results["checks"]["rls_policies"] = rls_health
        
        # Determine overall status
        all_healthy = all(
            check.get("status") == "healthy"
            for check in results["checks"].values()
        )
        results["overall_status"] = "healthy" if all_healthy else "unhealthy"
        
        # Store results
        self._last_check = datetime.now(timezone.utc)
        self._last_status = results
        
        # Send alert if unhealthy
        if not all_healthy and self.webhook_url:
            await self._send_alert(results)
        
        return results
    
    async def _check_service_account(self) -> Dict[str, Any]:
        """Check if service account exists and is properly configured."""
        try:
            if not self._user_repo:
                return {
                    "status": "unhealthy",
                    "error": "Repository not initialized"
                }
            
            # Try to fetch the service account user
            service_user = await self._user_repo.get_user_by_id(self.config.service_account_id)
            
            if service_user:
                return {
                    "status": "healthy",
                    "exists": True,
                    "id": service_user.id,
                    "email": service_user.email,
                    "credits": service_user.credits_balance,
                    "created_at": service_user.created_at.isoformat() if service_user.created_at else None
                }
            else:
                return {
                    "status": "unhealthy",
                    "exists": False,
                    "error": "Service account not found in database"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def _check_rls_policies(self) -> Dict[str, Any]:
        """Test RLS policies are working correctly."""
        try:
            if not self._user_repo:
                return {
                    "status": "unhealthy",
                    "error": "Repository not initialized"
                }
            
            # Test SELECT permission
            can_select = False
            try:
                users = await self._user_repo.get_all_users(limit=1)
                can_select = True
            except Exception as e:
                logger.error(f"RLS SELECT test failed: {e}")
            
            # Test UPDATE permission (using service account itself)
            can_update = False
            try:
                # This should work with proper RLS policies
                balance = await self._user_repo.get_user_credits(self.config.service_account_id)
                can_update = balance is not None
            except Exception as e:
                logger.error(f"RLS UPDATE test failed: {e}")
            
            return {
                "status": "healthy" if (can_select and can_update) else "unhealthy",
                "can_select": can_select,
                "can_update": can_update,
                "policies_working": can_select and can_update
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def _send_alert(self, health_status: Dict[str, Any]):
        """Send alert to webhook if configured."""
        if not self.webhook_url:
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": f"⚠️ Velro Backend Health Check Failed",
                    "status": health_status["overall_status"],
                    "timestamp": health_status["timestamp"],
                    "failed_checks": [
                        name for name, check in health_status["checks"].items()
                        if check.get("status") != "healthy"
                    ],
                    "details": health_status
                }
                
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info("Health check alert sent successfully")
                    else:
                        logger.error(f"Failed to send alert: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error sending health check alert: {e}")
    
    async def start_monitoring(self):
        """Start continuous health monitoring."""
        if not self.enabled:
            logger.info("Health monitoring is disabled")
            return
        
        logger.info(f"Starting health monitoring (interval: {self.interval_minutes} minutes)")
        
        while True:
            try:
                # Run health check
                status = await self.run_health_check()
                
                # Log results
                if status["overall_status"] == "healthy":
                    logger.info("Health check passed")
                else:
                    logger.warning(f"Health check failed: {status}")
                
                # Wait for next check
                await asyncio.sleep(self.interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")
                # Wait before retrying
                await asyncio.sleep(60)
    
    def get_last_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the last health check status.
        
        Returns:
            Last health status or None
        """
        return self._last_status
    
    def should_check(self) -> bool:
        """
        Determine if a health check should run.
        
        Returns:
            True if check should run
        """
        if not self.enabled:
            return False
        
        if not self._last_check:
            return True
        
        time_since_check = datetime.now(timezone.utc) - self._last_check
        return time_since_check > timedelta(minutes=self.interval_minutes)

# FastAPI endpoint integration
async def health_check_endpoint() -> Dict[str, Any]:
    """
    FastAPI endpoint for health checks.
    Can be integrated into your existing API.
    """
    service = HealthCheckService()
    await service.initialize()
    return await service.run_health_check()

# CLI tool for manual health checks
async def main():
    """Run health check from command line."""
    import sys
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("SERVICE ACCOUNT HEALTH CHECK")
    print("=" * 60)
    print()
    
    try:
        service = HealthCheckService()
        await service.initialize()
        
        status = await service.run_health_check()
        
        print(json.dumps(status, indent=2))
        
        if status["overall_status"] == "healthy":
            print("\n✅ All health checks passed")
            sys.exit(0)
        else:
            print("\n❌ Some health checks failed")
            failed = [
                name for name, check in status["checks"].items()
                if check.get("status") != "healthy"
            ]
            print(f"Failed checks: {', '.join(failed)}")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Health check error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())