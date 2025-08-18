"""
Security Monitoring System Integration
Integrates the comprehensive security monitoring system with the existing Velro backend
and provides middleware configuration for real-time security monitoring.
"""

import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

# Import security monitoring components
try:
    from security.security_monitoring_system import security_monitor
    from security.audit_system_enhanced import enhanced_audit_system, AuditResult, AuditCategory
    from middleware.security_monitoring import SecurityMonitoringMiddleware
    from middleware.security_enhanced import SecurityEnhancedMiddleware
    from routers.security_dashboard import router as security_dashboard_router
    from config import settings
except ImportError as e:
    logging.error(f"❌ Failed to import security components: {e}")
    security_monitor = None
    enhanced_audit_system = None
    SecurityMonitoringMiddleware = None
    SecurityEnhancedMiddleware = None
    security_dashboard_router = None


logger = logging.getLogger(__name__)


class SecurityIntegrationManager:
    """
    Manages the integration of all security monitoring components with the FastAPI application.
    """
    
    def __init__(self, app: FastAPI):
        self.app = app
        self.security_monitor = security_monitor
        self.audit_system = enhanced_audit_system
        self.monitoring_enabled = False
        self.audit_enabled = False
        
        logger.info("🛡️ Security Integration Manager initialized")
    
    @asynccontextmanager
    async def lifespan_context(self):
        """
        Context manager for application lifespan events.
        Starts and stops security monitoring services.
        """
        try:
            # Startup
            await self.startup()
            yield
        finally:
            # Shutdown
            await self.shutdown()
    
    async def startup(self):
        """Start security monitoring services."""
        logger.info("🚀 Starting security monitoring services...")
        
        # Initialize security monitoring
        if self.security_monitor:
            try:
                await self.security_monitor.start_monitoring()
                self.monitoring_enabled = True
                logger.info("✅ Security monitoring system started")
            except Exception as e:
                logger.error(f"❌ Failed to start security monitoring: {e}")
        
        # Initialize audit system
        if self.audit_system:
            try:
                # Test audit system by logging startup event
                await self.audit_system.log_administrative_action(
                    admin_user_id="system",
                    action="security_system_startup",
                    target="security_monitoring_system",
                    target_id=None,
                    result=AuditResult.SUCCESS,
                    source_ip="127.0.0.1",
                    user_agent="System",
                    details={"component": "security_integration", "version": "1.0"},
                    session_id=None
                )
                self.audit_enabled = True
                logger.info("✅ Enhanced audit system initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize audit system: {e}")
        
        logger.info("🛡️ Security services startup completed")
    
    async def shutdown(self):
        """Stop security monitoring services."""
        logger.info("🛑 Shutting down security monitoring services...")
        
        # Log shutdown event
        if self.audit_system:
            try:
                await self.audit_system.log_administrative_action(
                    admin_user_id="system",
                    action="security_system_shutdown",
                    target="security_monitoring_system",
                    target_id=None,
                    result=AuditResult.SUCCESS,
                    source_ip="127.0.0.1",
                    user_agent="System",
                    details={"component": "security_integration"},
                    session_id=None
                )
            except Exception as e:
                logger.error(f"❌ Failed to log shutdown event: {e}")
        
        # Stop security monitoring
        if self.security_monitor and self.monitoring_enabled:
            try:
                await self.security_monitor.stop_monitoring()
                logger.info("✅ Security monitoring stopped")
            except Exception as e:
                logger.error(f"❌ Failed to stop security monitoring: {e}")
        
        logger.info("🛡️ Security services shutdown completed")
    
    def add_middleware(self):
        """Add security monitoring middleware to the FastAPI application."""
        if not SecurityMonitoringMiddleware or not SecurityEnhancedMiddleware:
            logger.warning("⚠️ Security middleware not available")
            return
        
        try:
            # Add security monitoring middleware (outer layer)
            self.app.add_middleware(
                SecurityMonitoringMiddleware,
                enable_blocking=True,
                enable_audit_logging=True
            )
            
            # Add enhanced security middleware (inner layer)
            self.app.add_middleware(SecurityEnhancedMiddleware)
            
            logger.info("✅ Security middleware added to application")
            
        except Exception as e:
            logger.error(f"❌ Failed to add security middleware: {e}")
    
    def add_security_routes(self):
        """Add security dashboard routes to the FastAPI application."""
        if not security_dashboard_router:
            logger.warning("⚠️ Security dashboard router not available")
            return
        
        try:
            self.app.include_router(security_dashboard_router)
            logger.info("✅ Security dashboard routes added")
        except Exception as e:
            logger.error(f"❌ Failed to add security routes: {e}")
    
    def get_status(self) -> dict:
        """Get security integration status."""
        return {
            "security_monitoring": {
                "enabled": self.monitoring_enabled,
                "available": self.security_monitor is not None
            },
            "audit_system": {
                "enabled": self.audit_enabled,
                "available": self.audit_system is not None
            },
            "middleware": {
                "security_monitoring": SecurityMonitoringMiddleware is not None,
                "security_enhanced": SecurityEnhancedMiddleware is not None
            },
            "dashboard": {
                "available": security_dashboard_router is not None
            }
        }


def create_security_middleware_stack():
    """Create a configured security middleware stack."""
    middleware_stack = []
    
    if SecurityMonitoringMiddleware:
        middleware_stack.append({
            "middleware": SecurityMonitoringMiddleware,
            "kwargs": {
                "enable_blocking": True,
                "enable_audit_logging": True
            }
        })
    
    if SecurityEnhancedMiddleware:
        middleware_stack.append({
            "middleware": SecurityEnhancedMiddleware,
            "kwargs": {}
        })
    
    return middleware_stack


def setup_security_monitoring(app: FastAPI, enable_dashboard: bool = True) -> SecurityIntegrationManager:
    """
    Set up comprehensive security monitoring for a FastAPI application.
    
    Args:
        app: FastAPI application instance
        enable_dashboard: Whether to include the security dashboard routes
    
    Returns:
        SecurityIntegrationManager instance
    """
    # Create security integration manager
    security_manager = SecurityIntegrationManager(app)
    
    # Add middleware
    security_manager.add_middleware()
    
    # Add security dashboard routes if enabled
    if enable_dashboard:
        security_manager.add_security_routes()
    
    # Add lifespan events for startup/shutdown
    @app.on_event("startup")
    async def startup_event():
        await security_manager.startup()
    
    @app.on_event("shutdown")
    async def shutdown_event():
        await security_manager.shutdown()
    
    # Add custom exception handler for security events
    @app.exception_handler(Exception)
    async def security_exception_handler(request: Request, exc: Exception):
        """Handle exceptions with security logging."""
        if enhanced_audit_system:
            try:
                # Extract request info
                client_ip = request.headers.get('x-forwarded-for', request.client.host).split(',')[0].strip()
                user_agent = request.headers.get('user-agent', '')
                
                # Log exception as security event
                await enhanced_audit_system.log_administrative_action(
                    admin_user_id="system",
                    action="application_exception",
                    target=str(request.url.path),
                    target_id=None,
                    result=AuditResult.FAILURE,
                    source_ip=client_ip,
                    user_agent=user_agent,
                    details={
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                        "method": request.method,
                        "endpoint": str(request.url.path)
                    },
                    session_id=getattr(request.state, 'session_id', None)
                )
            except Exception as audit_error:
                logger.error(f"❌ Failed to log exception to audit system: {audit_error}")
        
        # Re-raise the original exception
        raise exc
    
    logger.info("🛡️ Security monitoring setup completed")
    return security_manager


def create_security_health_check():
    """Create a health check function for security services."""
    async def security_health_check():
        """Health check for security monitoring services."""
        health_status = {
            "status": "healthy",
            "components": {
                "security_monitor": False,
                "audit_system": False,
                "middleware": False
            },
            "details": {}
        }
        
        # Check security monitor
        if security_monitor:
            try:
                # Test security monitor by checking queue sizes
                health_status["components"]["security_monitor"] = True
                health_status["details"]["security_monitor"] = {
                    "event_queue_size": len(security_monitor.event_queue),
                    "blocked_ips_count": len(security_monitor.blocked_ips),
                    "monitoring_tasks": len(getattr(security_monitor, '_monitoring_tasks', []))
                }
            except Exception as e:
                health_status["details"]["security_monitor"] = {"error": str(e)}
        
        # Check audit system
        if enhanced_audit_system:
            try:
                # Test audit system by checking storage
                health_status["components"]["audit_system"] = True
                health_status["details"]["audit_system"] = {
                    "storage_type": enhanced_audit_system.audit_storage.storage_type,
                    "redis_available": enhanced_audit_system.redis_client is not None
                }
            except Exception as e:
                health_status["details"]["audit_system"] = {"error": str(e)}
        
        # Check middleware availability
        health_status["components"]["middleware"] = (
            SecurityMonitoringMiddleware is not None and 
            SecurityEnhancedMiddleware is not None
        )
        
        # Determine overall status
        if all(health_status["components"].values()):
            health_status["status"] = "healthy"
        elif any(health_status["components"].values()):
            health_status["status"] = "degraded"
        else:
            health_status["status"] = "unhealthy"
        
        return health_status
    
    return security_health_check


# Utility functions for integration with existing systems

async def log_authentication_event(user_id: Optional[str], action: str, success: bool,
                                 request: Request, failure_reason: Optional[str] = None):
    """Helper function to log authentication events from existing auth systems."""
    if not enhanced_audit_system:
        return
    
    try:
        client_ip = request.headers.get('x-forwarded-for', request.client.host).split(',')[0].strip()
        user_agent = request.headers.get('user-agent', '')
        session_id = getattr(request.state, 'session_id', None)
        
        result = AuditResult.SUCCESS if success else AuditResult.FAILURE
        details = {
            "endpoint": str(request.url.path),
            "method": request.method
        }
        
        if failure_reason:
            details["failure_reason"] = failure_reason
        
        await enhanced_audit_system.log_authentication_event(
            user_id=user_id,
            action=action,
            result=result,
            source_ip=client_ip,
            user_agent=user_agent,
            details=details,
            session_id=session_id
        )
        
        # Also log to security monitor if authentication failed
        if not success and security_monitor:
            await security_monitor.log_authentication_event(
                user_id=user_id,
                success=success,
                source_ip=client_ip,
                method=request.method,
                failure_reason=failure_reason
            )
            
    except Exception as e:
        logger.error(f"❌ Failed to log authentication event: {e}")


async def log_data_access_event(user_id: str, resource: str, action: str,
                              request: Request, success: bool = True,
                              resource_id: Optional[str] = None):
    """Helper function to log data access events from existing API endpoints."""
    if not enhanced_audit_system:
        return
    
    try:
        client_ip = request.headers.get('x-forwarded-for', request.client.host).split(',')[0].strip()
        user_agent = request.headers.get('user-agent', '')
        session_id = getattr(request.state, 'session_id', None)
        
        result = AuditResult.SUCCESS if success else AuditResult.FAILURE
        details = {
            "endpoint": str(request.url.path),
            "method": request.method,
            "query_params": str(request.url.query) if request.url.query else None
        }
        
        await enhanced_audit_system.log_data_access_event(
            user_id=user_id,
            action=action,
            result=result,
            resource=resource,
            resource_id=resource_id,
            source_ip=client_ip,
            user_agent=user_agent,
            details=details,
            session_id=session_id
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to log data access event: {e}")


async def log_admin_action(admin_user_id: str, action: str, target: str,
                         request: Request, success: bool = True,
                         target_id: Optional[str] = None, metadata: Optional[dict] = None):
    """Helper function to log administrative actions."""
    if not enhanced_audit_system:
        return
    
    try:
        client_ip = request.headers.get('x-forwarded-for', request.client.host).split(',')[0].strip()
        user_agent = request.headers.get('user-agent', '')
        session_id = getattr(request.state, 'session_id', None)
        
        result = AuditResult.SUCCESS if success else AuditResult.FAILURE
        details = {
            "endpoint": str(request.url.path),
            "method": request.method,
            **(metadata or {})
        }
        
        await enhanced_audit_system.log_administrative_action(
            admin_user_id=admin_user_id,
            action=action,
            target=target,
            target_id=target_id,
            result=result,
            source_ip=client_ip,
            user_agent=user_agent,
            details=details,
            session_id=session_id
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to log admin action: {e}")


# Export utility functions and classes
__all__ = [
    'SecurityIntegrationManager',
    'setup_security_monitoring', 
    'create_security_middleware_stack',
    'create_security_health_check',
    'log_authentication_event',
    'log_data_access_event',
    'log_admin_action'
]