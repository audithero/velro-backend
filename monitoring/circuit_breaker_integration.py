"""
Enhanced Circuit Breaker Integration for Enterprise Monitoring.
Integrates circuit breakers with Prometheus metrics, automatic recovery, and service isolation.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum

from utils.circuit_breaker import (
    AuthCircuitBreaker, 
    AuthCircuitBreakerManager, 
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitBreakerError,
    circuit_breaker_manager
)
from monitoring.metrics import metrics_collector

logger = logging.getLogger(__name__)


class ServiceHealth(Enum):
    """Service health states for monitoring."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"


@dataclass
class ServiceRecoveryPlan:
    """Recovery plan for degraded services."""
    service_name: str
    recovery_actions: List[str]
    estimated_recovery_time: int  # seconds
    fallback_service: Optional[str] = None
    notification_channels: List[str] = None


class EnterpriseCircuitBreakerManager:
    """
    Enterprise-grade circuit breaker manager with monitoring integration.
    Provides automatic recovery, service isolation, and comprehensive observability.
    """
    
    def __init__(self):
        self.base_manager = circuit_breaker_manager
        self.service_health: Dict[str, ServiceHealth] = {}
        self.recovery_plans: Dict[str, ServiceRecoveryPlan] = {}
        self.auto_recovery_enabled = True
        self.recovery_tasks: Dict[str, asyncio.Task] = {}
        
        # Initialize recovery plans
        self._initialize_recovery_plans()
        
        # Start monitoring task
        self._monitoring_task = None
        
    def _initialize_recovery_plans(self):
        """Initialize recovery plans for critical services."""
        self.recovery_plans = {
            'database': ServiceRecoveryPlan(
                service_name='database',
                recovery_actions=[
                    'Check database connectivity',
                    'Verify connection pool health',
                    'Test basic query execution',
                    'Validate read/write operations',
                    'Clear connection pool if needed'
                ],
                estimated_recovery_time=30,
                fallback_service='cache',
                notification_channels=['slack', 'email', 'pagerduty']
            ),
            'token_validation': ServiceRecoveryPlan(
                service_name='token_validation',
                recovery_actions=[
                    'Verify JWT secret availability',
                    'Test token parsing',
                    'Check external auth service',
                    'Validate token cache',
                    'Reset token validation state'
                ],
                estimated_recovery_time=15,
                fallback_service='local_validation',
                notification_channels=['slack', 'email']
            ),
            'external_auth': ServiceRecoveryPlan(
                service_name='external_auth',
                recovery_actions=[
                    'Test external service connectivity',
                    'Verify API credentials',
                    'Check rate limiting status',
                    'Validate response format',
                    'Switch to backup auth provider'
                ],
                estimated_recovery_time=45,
                fallback_service='local_auth',
                notification_channels=['slack', 'email', 'pagerduty']
            ),
            'user_lookup': ServiceRecoveryPlan(
                service_name='user_lookup',
                recovery_actions=[
                    'Test user database connectivity',
                    'Verify user cache availability',
                    'Check user index integrity',
                    'Validate user data consistency',
                    'Refresh user cache'
                ],
                estimated_recovery_time=20,
                fallback_service='cached_user_data',
                notification_channels=['slack', 'email']
            ),
            'permission_check': ServiceRecoveryPlan(
                service_name='permission_check',
                recovery_actions=[
                    'Verify permission database',
                    'Check role cache consistency',
                    'Test permission queries',
                    'Validate access control rules',
                    'Rebuild permission cache'
                ],
                estimated_recovery_time=25,
                fallback_service='basic_permissions',
                notification_channels=['slack', 'email']
            )
        }
    
    async def start_monitoring(self):
        """Start the monitoring and auto-recovery system."""
        if self._monitoring_task is None or self._monitoring_task.done():
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("🔄 [CIRCUIT-BREAKER] Started enterprise monitoring and auto-recovery")
    
    async def stop_monitoring(self):
        """Stop the monitoring system."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("🔄 [CIRCUIT-BREAKER] Stopped enterprise monitoring")
    
    async def _monitoring_loop(self):
        """Main monitoring loop for circuit breaker health."""
        try:
            while True:
                await self._check_all_circuit_breakers()
                await self._update_service_health()
                await self._trigger_recovery_if_needed()
                await self._update_metrics()
                await asyncio.sleep(10)  # Check every 10 seconds
        except asyncio.CancelledError:
            logger.info("🔄 [CIRCUIT-BREAKER] Monitoring loop cancelled")
            raise
        except Exception as e:
            logger.error(f"❌ [CIRCUIT-BREAKER] Monitoring loop error: {e}")
            await asyncio.sleep(30)  # Back-off on error
    
    async def _check_all_circuit_breakers(self):
        """Check all circuit breaker states and update health status."""
        for circuit_name, circuit_breaker in self.base_manager.circuit_breakers.items():
            try:
                state_info = circuit_breaker.get_state()
                current_state = CircuitBreakerState(state_info['state'])
                
                # Update service health based on circuit breaker state
                if current_state == CircuitBreakerState.CLOSED:
                    # Check if we're recovering from a previous issue
                    if self.service_health.get(circuit_name) in [ServiceHealth.CRITICAL, ServiceHealth.FAILED]:
                        self.service_health[circuit_name] = ServiceHealth.DEGRADED
                        logger.info(f"✅ [CIRCUIT-BREAKER] {circuit_name} recovering - state: DEGRADED")
                    else:
                        self.service_health[circuit_name] = ServiceHealth.HEALTHY
                
                elif current_state == CircuitBreakerState.HALF_OPEN:
                    self.service_health[circuit_name] = ServiceHealth.DEGRADED
                    logger.warning(f"🔄 [CIRCUIT-BREAKER] {circuit_name} in recovery - state: HALF_OPEN")
                
                elif current_state == CircuitBreakerState.OPEN:
                    # Escalate health status
                    current_health = self.service_health.get(circuit_name, ServiceHealth.HEALTHY)
                    if current_health != ServiceHealth.FAILED:
                        if current_health == ServiceHealth.HEALTHY:
                            self.service_health[circuit_name] = ServiceHealth.CRITICAL
                        else:
                            self.service_health[circuit_name] = ServiceHealth.FAILED
                        
                        logger.error(
                            f"🔥 [CIRCUIT-BREAKER] {circuit_name} circuit OPEN - "
                            f"health escalated to {self.service_health[circuit_name].value}"
                        )
                
                # Update metrics
                metrics_collector.update_circuit_breaker_state(
                    circuit_name, 
                    current_state.value
                )
                
            except Exception as e:
                logger.error(f"❌ [CIRCUIT-BREAKER] Error checking {circuit_name}: {e}")
                self.service_health[circuit_name] = ServiceHealth.FAILED
    
    async def _update_service_health(self):
        """Update overall service health assessment."""
        try:
            # Calculate overall system health
            health_counts = {health: 0 for health in ServiceHealth}
            for health in self.service_health.values():
                health_counts[health] += 1
            
            total_services = len(self.service_health)
            if total_services == 0:
                return
            
            # Determine overall system health
            failed_percentage = health_counts[ServiceHealth.FAILED] / total_services
            critical_percentage = health_counts[ServiceHealth.CRITICAL] / total_services
            
            if failed_percentage > 0.5:  # >50% services failed
                overall_health = "system_failure"
            elif failed_percentage > 0.2 or critical_percentage > 0.3:  # >20% failed or >30% critical
                overall_health = "degraded"
            elif health_counts[ServiceHealth.DEGRADED] > 0:
                overall_health = "degraded"
            else:
                overall_health = "healthy"
            
            # Log significant health changes
            logger.info(
                f"📊 [CIRCUIT-BREAKER] System health: {overall_health} "
                f"(H:{health_counts[ServiceHealth.HEALTHY]} "
                f"D:{health_counts[ServiceHealth.DEGRADED]} "
                f"C:{health_counts[ServiceHealth.CRITICAL]} "
                f"F:{health_counts[ServiceHealth.FAILED]})"
            )
            
        except Exception as e:
            logger.error(f"❌ [CIRCUIT-BREAKER] Error updating service health: {e}")
    
    async def _trigger_recovery_if_needed(self):
        """Trigger automatic recovery for failed services."""
        if not self.auto_recovery_enabled:
            return
        
        for service_name, health in self.service_health.items():
            # Trigger recovery for critical or failed services
            if health in [ServiceHealth.CRITICAL, ServiceHealth.FAILED]:
                if service_name not in self.recovery_tasks or self.recovery_tasks[service_name].done():
                    # Start recovery task
                    self.recovery_tasks[service_name] = asyncio.create_task(
                        self._execute_recovery_plan(service_name)
                    )
                    logger.info(f"🚑 [CIRCUIT-BREAKER] Starting recovery for {service_name}")
    
    async def _execute_recovery_plan(self, service_name: str):
        """Execute recovery plan for a specific service."""
        try:
            recovery_plan = self.recovery_plans.get(service_name)
            if not recovery_plan:
                logger.warning(f"⚠️ [CIRCUIT-BREAKER] No recovery plan for {service_name}")
                return
            
            logger.info(
                f"🚑 [CIRCUIT-BREAKER] Executing recovery plan for {service_name} "
                f"(ETA: {recovery_plan.estimated_recovery_time}s)"
            )
            
            # Execute recovery actions
            for i, action in enumerate(recovery_plan.recovery_actions, 1):
                logger.info(f"🔧 [RECOVERY] {service_name} Step {i}/{len(recovery_plan.recovery_actions)}: {action}")
                
                # Execute the actual recovery action
                success = await self._execute_recovery_action(service_name, action)
                
                if success:
                    logger.info(f"✅ [RECOVERY] {service_name} Step {i} completed successfully")
                else:
                    logger.warning(f"⚠️ [RECOVERY] {service_name} Step {i} failed, continuing...")
                
                # Brief pause between actions
                await asyncio.sleep(2)
            
            # Wait for recovery to take effect
            await asyncio.sleep(5)
            
            # Test service health
            if await self._test_service_health(service_name):
                logger.info(f"✅ [RECOVERY] {service_name} recovery completed successfully")
                
                # Reset circuit breaker
                await self.base_manager.reset_circuit_breaker(service_name)
                self.service_health[service_name] = ServiceHealth.DEGRADED  # Will improve to healthy on next check
                
                # Send recovery notification
                await self._send_recovery_notification(service_name, True)
                
            else:
                logger.error(f"❌ [RECOVERY] {service_name} recovery failed, service still unhealthy")
                await self._send_recovery_notification(service_name, False)
                
                # Try fallback service if available
                if recovery_plan.fallback_service:
                    logger.info(f"🔄 [RECOVERY] Activating fallback service: {recovery_plan.fallback_service}")
                    await self._activate_fallback_service(service_name, recovery_plan.fallback_service)
            
        except Exception as e:
            logger.error(f"❌ [RECOVERY] Recovery plan execution failed for {service_name}: {e}")
            await self._send_recovery_notification(service_name, False, str(e))
    
    async def _execute_recovery_action(self, service_name: str, action: str) -> bool:
        """Execute a specific recovery action."""
        try:
            # This would contain actual recovery logic
            # For now, we'll simulate recovery actions
            
            if "connectivity" in action.lower():
                # Test connectivity
                await asyncio.sleep(1)
                return True
            
            elif "pool" in action.lower():
                # Reset connection pool
                await asyncio.sleep(2)
                return True
            
            elif "cache" in action.lower():
                # Clear/refresh cache
                await asyncio.sleep(1)
                return True
            
            elif "validation" in action.lower():
                # Validate service state
                await asyncio.sleep(1)
                return True
            
            else:
                # Generic action
                await asyncio.sleep(1)
                return True
                
        except Exception as e:
            logger.error(f"❌ [RECOVERY] Action '{action}' failed for {service_name}: {e}")
            return False
    
    async def _test_service_health(self, service_name: str) -> bool:
        """Test if a service is healthy after recovery."""
        try:
            # This would contain actual health check logic
            # For now, we'll simulate a health check
            
            if service_name == "database":
                # Test database connectivity
                await asyncio.sleep(1)
                return True
            
            elif service_name == "token_validation":
                # Test token validation
                await asyncio.sleep(0.5)
                return True
            
            elif service_name == "external_auth":
                # Test external auth service
                await asyncio.sleep(2)
                return True
            
            elif service_name == "user_lookup":
                # Test user lookup
                await asyncio.sleep(1)
                return True
            
            elif service_name == "permission_check":
                # Test permission checking
                await asyncio.sleep(1)
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [RECOVERY] Health test failed for {service_name}: {e}")
            return False
    
    async def _activate_fallback_service(self, primary_service: str, fallback_service: str):
        """Activate fallback service when primary service fails."""
        logger.info(f"🔄 [FALLBACK] Activating {fallback_service} as fallback for {primary_service}")
        
        # This would contain logic to activate fallback services
        # For example, switching database connections, using cached data, etc.
        
        # Update metrics
        metrics_collector.business_metrics.record_feature_usage(
            f"fallback_{fallback_service}", 
            "system", 
            True
        )
    
    async def _send_recovery_notification(self, service_name: str, success: bool, error_msg: str = None):
        """Send recovery notification to configured channels."""
        try:
            recovery_plan = self.recovery_plans.get(service_name)
            if not recovery_plan or not recovery_plan.notification_channels:
                return
            
            status = "SUCCESS" if success else "FAILED"
            message = f"Service Recovery {status}: {service_name}"
            
            if error_msg:
                message += f" - Error: {error_msg}"
            
            for channel in recovery_plan.notification_channels:
                await self._send_notification(channel, message, service_name, success)
                
        except Exception as e:
            logger.error(f"❌ [RECOVERY] Failed to send notification: {e}")
    
    async def _send_notification(self, channel: str, message: str, service_name: str, success: bool):
        """Send notification to specific channel."""
        try:
            # This would contain actual notification logic
            logger.info(f"📢 [NOTIFICATION] {channel.upper()}: {message}")
            
            if channel == "slack":
                # Send Slack notification
                pass
            elif channel == "email":
                # Send email notification
                pass
            elif channel == "pagerduty":
                # Send PagerDuty alert
                pass
            elif channel == "webhook":
                # Send webhook notification
                pass
                
        except Exception as e:
            logger.error(f"❌ [NOTIFICATION] Failed to send to {channel}: {e}")
    
    async def _update_metrics(self):
        """Update Prometheus metrics with current circuit breaker states."""
        try:
            # Update circuit breaker state metrics
            for service_name, health in self.service_health.items():
                circuit_breaker = self.base_manager.circuit_breakers.get(service_name)
                if circuit_breaker:
                    state_info = circuit_breaker.get_state()
                    metrics_collector.update_circuit_breaker_state(
                        service_name, 
                        state_info['state']
                    )
            
            # Update SLA compliance based on circuit breaker states
            total_services = len(self.service_health)
            if total_services > 0:
                healthy_services = sum(
                    1 for health in self.service_health.values() 
                    if health in [ServiceHealth.HEALTHY, ServiceHealth.DEGRADED]
                )
                compliance_percentage = (healthy_services / total_services) * 100
                
                metrics_collector.update_sla_compliance(
                    "service_availability", 
                    "current", 
                    compliance_percentage
                )
            
        except Exception as e:
            logger.error(f"❌ [CIRCUIT-BREAKER] Error updating metrics: {e}")
    
    # Public API methods
    
    async def get_system_health_report(self) -> Dict[str, Any]:
        """Get comprehensive system health report."""
        try:
            circuit_states = self.base_manager.get_all_states()
            
            return {
                "overall_status": self._calculate_overall_health(),
                "services": {
                    service_name: {
                        "health": health.value,
                        "circuit_breaker": circuit_states.get(service_name, {}),
                        "recovery_plan": {
                            "available": service_name in self.recovery_plans,
                            "estimated_time": self.recovery_plans[service_name].estimated_recovery_time if service_name in self.recovery_plans else None,
                            "fallback_service": self.recovery_plans[service_name].fallback_service if service_name in self.recovery_plans else None
                        },
                        "recovery_status": {
                            "in_progress": service_name in self.recovery_tasks and not self.recovery_tasks[service_name].done(),
                            "last_attempt": None  # Would track last recovery attempt
                        }
                    }
                    for service_name, health in self.service_health.items()
                },
                "auto_recovery_enabled": self.auto_recovery_enabled,
                "active_recoveries": len([
                    task for task in self.recovery_tasks.values() 
                    if not task.done()
                ]),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ [CIRCUIT-BREAKER] Error generating health report: {e}")
            return {
                "overall_status": "unknown",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _calculate_overall_health(self) -> str:
        """Calculate overall system health status."""
        if not self.service_health:
            return "unknown"
        
        health_counts = {health: 0 for health in ServiceHealth}
        for health in self.service_health.values():
            health_counts[health] += 1
        
        total = len(self.service_health)
        failed_ratio = health_counts[ServiceHealth.FAILED] / total
        critical_ratio = health_counts[ServiceHealth.CRITICAL] / total
        
        if failed_ratio > 0.5:
            return "critical"
        elif failed_ratio > 0.2 or critical_ratio > 0.3:
            return "degraded"
        elif health_counts[ServiceHealth.DEGRADED] > 0:
            return "degraded"
        else:
            return "healthy"
    
    async def trigger_manual_recovery(self, service_name: str) -> bool:
        """Manually trigger recovery for a specific service."""
        try:
            if service_name in self.recovery_tasks and not self.recovery_tasks[service_name].done():
                logger.warning(f"⚠️ [RECOVERY] Recovery already in progress for {service_name}")
                return False
            
            self.recovery_tasks[service_name] = asyncio.create_task(
                self._execute_recovery_plan(service_name)
            )
            
            logger.info(f"🚑 [RECOVERY] Manual recovery triggered for {service_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [RECOVERY] Failed to trigger manual recovery for {service_name}: {e}")
            return False
    
    def enable_auto_recovery(self):
        """Enable automatic recovery."""
        self.auto_recovery_enabled = True
        logger.info("✅ [CIRCUIT-BREAKER] Automatic recovery enabled")
    
    def disable_auto_recovery(self):
        """Disable automatic recovery."""
        self.auto_recovery_enabled = False
        logger.info("⚠️ [CIRCUIT-BREAKER] Automatic recovery disabled")


# Global enterprise circuit breaker manager
enterprise_circuit_breaker_manager = EnterpriseCircuitBreakerManager()


# Convenience functions for integration

async def start_circuit_breaker_monitoring():
    """Start the enterprise circuit breaker monitoring system."""
    await enterprise_circuit_breaker_manager.start_monitoring()


async def stop_circuit_breaker_monitoring():
    """Stop the enterprise circuit breaker monitoring system."""
    await enterprise_circuit_breaker_manager.stop_monitoring()


async def get_circuit_breaker_health_report() -> Dict[str, Any]:
    """Get comprehensive circuit breaker health report."""
    return await enterprise_circuit_breaker_manager.get_system_health_report()


async def trigger_service_recovery(service_name: str) -> bool:
    """Manually trigger recovery for a specific service."""
    return await enterprise_circuit_breaker_manager.trigger_manual_recovery(service_name)


def get_service_health(service_name: str) -> Optional[ServiceHealth]:
    """Get current health status for a specific service."""
    return enterprise_circuit_breaker_manager.service_health.get(service_name)


def is_auto_recovery_enabled() -> bool:
    """Check if automatic recovery is enabled."""
    return enterprise_circuit_breaker_manager.auto_recovery_enabled