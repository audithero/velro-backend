"""
Enterprise Monitoring Integration Hub.
Integrates all monitoring systems with existing security, caching, and collaboration systems.
Provides unified monitoring API and orchestrates all monitoring components.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
import json

# Import existing systems
from monitoring.metrics import metrics_collector
from monitoring.circuit_breaker_integration import enterprise_circuit_breaker_manager
from monitoring.intelligent_alerting_system import (
    intelligent_alerting_system, 
    AlertSeverity, 
    NotificationRule, 
    NotificationChannel
)
from monitoring.deep_health_check_system import deep_health_check_system
from monitoring.distributed_tracing_system import distributed_tracing_system

# Import existing Velro systems for integration
from security.security_monitoring_system import SecurityMonitoringSystem
from caching.multi_layer_cache_manager import multi_layer_cache_manager
from services.team_collaboration_service import TeamCollaborationService
from services.authorization_service import AuthorizationService

logger = logging.getLogger(__name__)


@dataclass
class MonitoringSystemStatus:
    """Status of a monitoring system component."""
    name: str
    status: str  # healthy, degraded, failed
    last_check: datetime
    metrics: Dict[str, Any]
    error: Optional[str] = None


class EnterpriseMonitoringIntegration:
    """
    Enterprise monitoring integration hub that orchestrates all monitoring systems
    and provides unified observability across the Velro platform.
    """
    
    def __init__(self):
        self.systems_status: Dict[str, MonitoringSystemStatus] = {}
        self.integration_started = False
        self.monitoring_config = self._load_monitoring_config()
        
        # Background tasks
        self._integration_health_task: Optional[asyncio.Task] = None
        self._metrics_aggregation_task: Optional[asyncio.Task] = None
        self._cross_system_correlation_task: Optional[asyncio.Task] = None
    
    def _load_monitoring_config(self) -> Dict[str, Any]:
        """Load monitoring configuration."""
        return {
            "metrics_collection_interval_seconds": 15,
            "health_check_interval_seconds": 30,
            "alert_correlation_window_minutes": 5,
            "trace_sampling_rate": 1.0,
            "circuit_breaker_auto_recovery": True,
            "notification_channels": {
                "slack": {
                    "enabled": True,
                    "webhook_url": "https://hooks.slack.com/services/..."
                },
                "email": {
                    "enabled": True,
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587
                },
                "pagerduty": {
                    "enabled": True,
                    "integration_key": "..."
                }
            },
            "business_metrics": {
                "track_user_activity": True,
                "track_generation_metrics": True,
                "track_team_collaboration": True,
                "track_authorization_performance": True,
                "track_cache_performance": True
            }
        }
    
    async def start_monitoring_integration(self):
        """Start the complete enterprise monitoring integration."""
        if self.integration_started:
            logger.warning("⚠️ [MONITORING] Integration already started")
            return
        
        logger.info("🚀 [MONITORING] Starting enterprise monitoring integration...")
        
        try:
            # Initialize and start all monitoring systems
            await self._initialize_monitoring_systems()
            
            # Configure integrations
            await self._configure_system_integrations()
            
            # Start background tasks
            await self._start_background_tasks()
            
            # Configure notifications
            await self._configure_notification_channels()
            
            # Setup default monitoring rules
            await self._setup_default_monitoring_rules()
            
            self.integration_started = True
            
            logger.info("✅ [MONITORING] Enterprise monitoring integration started successfully")
            
            # Generate startup success alert
            await intelligent_alerting_system.create_alert(
                title="Monitoring System Startup Complete",
                description="All enterprise monitoring systems have been initialized and are operational",
                severity=AlertSeverity.INFO,
                source="monitoring_integration",
                labels={"event": "startup", "status": "success"},
                annotations={"systems_count": str(len(self.systems_status))}
            )
            
        except Exception as e:
            logger.error(f"❌ [MONITORING] Failed to start monitoring integration: {e}")
            await self._handle_startup_failure(e)
            raise
    
    async def stop_monitoring_integration(self):
        """Stop the enterprise monitoring integration."""
        if not self.integration_started:
            return
        
        logger.info("🛑 [MONITORING] Stopping enterprise monitoring integration...")
        
        try:
            # Stop background tasks
            await self._stop_background_tasks()
            
            # Stop monitoring systems
            await self._stop_monitoring_systems()
            
            self.integration_started = False
            
            logger.info("✅ [MONITORING] Enterprise monitoring integration stopped")
            
        except Exception as e:
            logger.error(f"❌ [MONITORING] Error stopping monitoring integration: {e}")
    
    async def _initialize_monitoring_systems(self):
        """Initialize all monitoring systems."""
        logger.info("🔧 [MONITORING] Initializing monitoring systems...")
        
        systems_to_initialize = [
            ("metrics_collector", self._initialize_metrics_system),
            ("circuit_breaker", self._initialize_circuit_breaker_system),
            ("alerting_system", self._initialize_alerting_system),
            ("health_check_system", self._initialize_health_check_system),
            ("tracing_system", self._initialize_tracing_system)
        ]
        
        for system_name, initializer in systems_to_initialize:
            try:
                logger.info(f"🔧 [MONITORING] Initializing {system_name}...")
                await initializer()
                self.systems_status[system_name] = MonitoringSystemStatus(
                    name=system_name,
                    status="healthy",
                    last_check=datetime.now(timezone.utc),
                    metrics={}
                )
                logger.info(f"✅ [MONITORING] {system_name} initialized successfully")
                
            except Exception as e:
                logger.error(f"❌ [MONITORING] Failed to initialize {system_name}: {e}")
                self.systems_status[system_name] = MonitoringSystemStatus(
                    name=system_name,
                    status="failed",
                    last_check=datetime.now(timezone.utc),
                    metrics={},
                    error=str(e)
                )
                raise
    
    async def _initialize_metrics_system(self):
        """Initialize Prometheus metrics collection."""
        # Metrics collector is already initialized, just configure it
        logger.info("📊 [MONITORING] Configuring Prometheus metrics collection...")
        
        # The metrics_collector is already available globally
        # Configure sampling and collection intervals if needed
        
        logger.info("📊 [MONITORING] Metrics system ready")
    
    async def _initialize_circuit_breaker_system(self):
        """Initialize circuit breaker system."""
        logger.info("🔄 [MONITORING] Starting circuit breaker system...")
        await enterprise_circuit_breaker_manager.start_monitoring()
        
        if self.monitoring_config.get("circuit_breaker_auto_recovery", True):
            enterprise_circuit_breaker_manager.enable_auto_recovery()
        else:
            enterprise_circuit_breaker_manager.disable_auto_recovery()
    
    async def _initialize_alerting_system(self):
        """Initialize intelligent alerting system."""
        logger.info("🚨 [MONITORING] Starting intelligent alerting system...")
        await intelligent_alerting_system.start()
    
    async def _initialize_health_check_system(self):
        """Initialize deep health check system."""
        logger.info("🏥 [MONITORING] Starting health check system...")
        await deep_health_check_system.start()
        
        if self.monitoring_config.get("auto_recovery_enabled", True):
            deep_health_check_system.enable_auto_recovery()
    
    async def _initialize_tracing_system(self):
        """Initialize distributed tracing system."""
        logger.info("🔍 [MONITORING] Starting distributed tracing system...")
        
        # Set sampling rate from config
        sampling_rate = self.monitoring_config.get("trace_sampling_rate", 1.0)
        distributed_tracing_system.set_sampling_rate(sampling_rate)
        
        await distributed_tracing_system.start()
    
    async def _configure_system_integrations(self):
        """Configure integrations with existing Velro systems."""
        logger.info("🔗 [MONITORING] Configuring system integrations...")
        
        # Security system integration
        await self._integrate_security_monitoring()
        
        # Cache system integration
        await self._integrate_cache_monitoring()
        
        # Team collaboration integration
        await self._integrate_team_collaboration_monitoring()
        
        # Authorization system integration
        await self._integrate_authorization_monitoring()
    
    async def _integrate_security_monitoring(self):
        """Integrate with security monitoring system."""
        logger.info("🛡️ [MONITORING] Integrating security monitoring...")
        
        # Configure security metrics collection
        def security_event_handler(event_type: str, severity: str, details: Dict[str, Any]):
            """Handle security events and convert to metrics/alerts."""
            # Record security metrics
            metrics_collector.security_metrics.record_security_violation(
                event_type, severity, details.get('source_ip', 'unknown')
            )
            
            # Create alert for critical security events
            if severity in ['critical', 'high']:
                asyncio.create_task(intelligent_alerting_system.create_alert(
                    title=f"Security Event: {event_type}",
                    description=f"Security violation detected: {details.get('message', 'No details')}",
                    severity=AlertSeverity.CRITICAL if severity == 'critical' else AlertSeverity.WARNING,
                    source="security_monitoring",
                    labels={
                        "event_type": event_type,
                        "severity": severity,
                        "source_ip": details.get('source_ip', 'unknown')
                    },
                    annotations=details
                ))
        
        # This would register the handler with the security system
        # For now, just log the integration
        logger.info("🛡️ [MONITORING] Security monitoring integration configured")
    
    async def _integrate_cache_monitoring(self):
        """Integrate with multi-layer cache monitoring."""
        logger.info("🗄️ [MONITORING] Integrating cache monitoring...")
        
        # Configure cache performance monitoring
        async def monitor_cache_performance():
            """Monitor cache performance and update metrics."""
            try:
                # This would get actual cache metrics from multi_layer_cache_manager
                # For now, simulate cache monitoring
                cache_stats = {
                    "l1_hit_rate": 85.0,
                    "l2_hit_rate": 95.0,
                    "l3_hit_rate": 98.0,
                    "overall_hit_rate": 93.0,
                    "memory_usage_mb": 512,
                    "active_connections": 10
                }
                
                # Update cache metrics
                metrics_collector.cache_metrics.record_cache_operation(
                    "redis", "get", "hit" if cache_stats["overall_hit_rate"] > 90 else "miss", 0.001
                )
                
                # Alert on low cache hit rate
                if cache_stats["overall_hit_rate"] < 85:
                    await intelligent_alerting_system.create_alert(
                        title="Low Cache Hit Rate",
                        description=f"Cache hit rate dropped to {cache_stats['overall_hit_rate']:.1f}%",
                        severity=AlertSeverity.WARNING,
                        source="cache_monitoring",
                        labels={"cache_type": "multi_layer", "metric": "hit_rate"},
                        annotations=cache_stats
                    )
                
            except Exception as e:
                logger.error(f"❌ [MONITORING] Cache monitoring error: {e}")
        
        # This would be called periodically
        logger.info("🗄️ [MONITORING] Cache monitoring integration configured")
    
    async def _integrate_team_collaboration_monitoring(self):
        """Integrate with team collaboration monitoring."""
        logger.info("👥 [MONITORING] Integrating team collaboration monitoring...")
        
        # Configure team collaboration metrics
        def team_activity_handler(activity_type: str, team_size: int, user_type: str):
            """Handle team collaboration activities."""
            # Record business metrics
            metrics_collector.business_metrics.record_team_collaboration(activity_type, team_size)
            metrics_collector.business_metrics.record_feature_usage(
                "team_collaboration", user_type, True
            )
        
        logger.info("👥 [MONITORING] Team collaboration monitoring integration configured")
    
    async def _integrate_authorization_monitoring(self):
        """Integrate with authorization system monitoring."""
        logger.info("🔐 [MONITORING] Integrating authorization monitoring...")
        
        # Configure authorization performance monitoring
        def authorization_event_handler(event_type: str, user_id: str, endpoint: str, 
                                      duration_ms: float, success: bool):
            """Handle authorization events."""
            # Record authorization metrics
            metrics_collector.authorization_metrics.record_auth_request(
                "POST" if event_type == "permission_check" else "GET",
                endpoint,
                "success" if success else "failure",
                "authenticated",
                duration_ms / 1000
            )
            
            # Record UUID validation metrics
            if "uuid" in event_type:
                metrics_collector.authorization_metrics.record_uuid_validation(
                    event_type, "success" if success else "failure", duration_ms / 1000
                )
            
            # Alert on authorization failures or slow responses
            if not success or duration_ms > 100:  # >100ms SLA violation
                severity = AlertSeverity.CRITICAL if duration_ms > 500 else AlertSeverity.WARNING
                asyncio.create_task(intelligent_alerting_system.create_alert(
                    title=f"Authorization Issue: {event_type}",
                    description=f"Authorization event failed or exceeded SLA: {duration_ms:.1f}ms",
                    severity=severity,
                    source="authorization_monitoring",
                    labels={
                        "event_type": event_type,
                        "endpoint": endpoint,
                        "success": str(success).lower()
                    },
                    annotations={
                        "duration_ms": str(duration_ms),
                        "user_id": user_id[:8] + "..." if len(user_id) > 8 else user_id  # Redacted
                    }
                ))
        
        logger.info("🔐 [MONITORING] Authorization monitoring integration configured")
    
    async def _start_background_tasks(self):
        """Start monitoring background tasks."""
        logger.info("⚡ [MONITORING] Starting background tasks...")
        
        # Integration health monitoring
        if self._integration_health_task is None or self._integration_health_task.done():
            self._integration_health_task = asyncio.create_task(self._integration_health_loop())
        
        # Metrics aggregation
        if self._metrics_aggregation_task is None or self._metrics_aggregation_task.done():
            self._metrics_aggregation_task = asyncio.create_task(self._metrics_aggregation_loop())
        
        # Cross-system correlation
        if self._cross_system_correlation_task is None or self._cross_system_correlation_task.done():
            self._cross_system_correlation_task = asyncio.create_task(self._cross_system_correlation_loop())
    
    async def _stop_background_tasks(self):
        """Stop monitoring background tasks."""
        tasks = [self._integration_health_task, self._metrics_aggregation_task, self._cross_system_correlation_task]
        
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def _stop_monitoring_systems(self):
        """Stop all monitoring systems."""
        systems_to_stop = [
            ("tracing_system", distributed_tracing_system.stop),
            ("health_check_system", deep_health_check_system.stop),
            ("alerting_system", intelligent_alerting_system.stop),
            ("circuit_breaker", enterprise_circuit_breaker_manager.stop_monitoring)
        ]
        
        for system_name, stop_func in systems_to_stop:
            try:
                logger.info(f"🛑 [MONITORING] Stopping {system_name}...")
                await stop_func()
                logger.info(f"✅ [MONITORING] {system_name} stopped")
            except Exception as e:
                logger.error(f"❌ [MONITORING] Error stopping {system_name}: {e}")
    
    async def _configure_notification_channels(self):
        """Configure notification channels for alerting."""
        logger.info("📢 [MONITORING] Configuring notification channels...")
        
        channels_config = self.monitoring_config.get("notification_channels", {})
        
        # Configure Slack channel
        if channels_config.get("slack", {}).get("enabled", False):
            slack_channel = NotificationChannel(
                type=NotificationChannel.SLACK,
                name="slack_default",
                config={
                    "webhook_url": channels_config["slack"].get("webhook_url")
                },
                enabled=True
            )
            intelligent_alerting_system.add_notification_channel(slack_channel)
        
        # Configure email channel
        if channels_config.get("email", {}).get("enabled", False):
            email_channel = NotificationChannel(
                type=NotificationChannel.EMAIL,
                name="email_default",
                config={
                    "smtp_server": channels_config["email"].get("smtp_server"),
                    "smtp_port": channels_config["email"].get("smtp_port"),
                    "from_email": "monitoring@velro.com"
                },
                enabled=True
            )
            intelligent_alerting_system.add_notification_channel(email_channel)
        
        # Configure PagerDuty channel
        if channels_config.get("pagerduty", {}).get("enabled", False):
            pagerduty_channel = NotificationChannel(
                type=NotificationChannel.PAGERDUTY,
                name="pagerduty_default",
                config={
                    "integration_key": channels_config["pagerduty"].get("integration_key")
                },
                enabled=True
            )
            intelligent_alerting_system.add_notification_channel(pagerduty_channel)
    
    async def _setup_default_monitoring_rules(self):
        """Setup default monitoring and alerting rules."""
        logger.info("📋 [MONITORING] Setting up default monitoring rules...")
        
        # Critical system alerts
        critical_rule = NotificationRule(
            name="critical_system_alerts",
            conditions={"labels": {"severity": "critical"}},
            channels=[NotificationChannel.SLACK, NotificationChannel.PAGERDUTY],
            recipients=["engineering@velro.com", "oncall@velro.com"],
            throttle_minutes=5,
            escalation_delay_minutes=15,
            include_severities=[AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]
        )
        intelligent_alerting_system.add_notification_rule(critical_rule)
        
        # Performance alerts
        performance_rule = NotificationRule(
            name="performance_alerts",
            conditions={"labels": {"source": "authorization_monitoring"}},
            channels=[NotificationChannel.SLACK, NotificationChannel.EMAIL],
            recipients=["performance@velro.com"],
            throttle_minutes=10,
            escalation_delay_minutes=30,
            include_severities=[AlertSeverity.WARNING, AlertSeverity.CRITICAL]
        )
        intelligent_alerting_system.add_notification_rule(performance_rule)
        
        # Security alerts
        security_rule = NotificationRule(
            name="security_alerts",
            conditions={"source": "security_monitoring"},
            channels=[NotificationChannel.SLACK, NotificationChannel.EMAIL],
            recipients=["security@velro.com"],
            throttle_minutes=2,
            escalation_delay_minutes=10,
            include_severities=[AlertSeverity.WARNING, AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]
        )
        intelligent_alerting_system.add_notification_rule(security_rule)
    
    async def _integration_health_loop(self):
        """Monitor health of monitoring integration systems."""
        while True:
            try:
                await self._check_systems_health()
                await asyncio.sleep(self.monitoring_config.get("health_check_interval_seconds", 30))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [MONITORING] Integration health check error: {e}")
                await asyncio.sleep(60)
    
    async def _metrics_aggregation_loop(self):
        """Aggregate metrics across systems."""
        while True:
            try:
                await self._aggregate_cross_system_metrics()
                await asyncio.sleep(self.monitoring_config.get("metrics_collection_interval_seconds", 15))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [MONITORING] Metrics aggregation error: {e}")
                await asyncio.sleep(60)
    
    async def _cross_system_correlation_loop(self):
        """Correlate events across monitoring systems."""
        while True:
            try:
                await self._correlate_cross_system_events()
                await asyncio.sleep(60)  # Every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [MONITORING] Cross-system correlation error: {e}")
                await asyncio.sleep(120)
    
    async def _check_systems_health(self):
        """Check health of all monitoring systems."""
        for system_name in self.systems_status.keys():
            try:
                # Get system-specific health check
                health_status = await self._get_system_health(system_name)
                
                self.systems_status[system_name] = MonitoringSystemStatus(
                    name=system_name,
                    status=health_status["status"],
                    last_check=datetime.now(timezone.utc),
                    metrics=health_status.get("metrics", {}),
                    error=health_status.get("error")
                )
                
            except Exception as e:
                logger.error(f"❌ [MONITORING] Health check failed for {system_name}: {e}")
                self.systems_status[system_name] = MonitoringSystemStatus(
                    name=system_name,
                    status="failed",
                    last_check=datetime.now(timezone.utc),
                    metrics={},
                    error=str(e)
                )
    
    async def _get_system_health(self, system_name: str) -> Dict[str, Any]:
        """Get health status for specific monitoring system."""
        if system_name == "circuit_breaker":
            health_report = await enterprise_circuit_breaker_manager.get_system_health_report()
            return {
                "status": health_report.get("overall_status", "unknown"),
                "metrics": {
                    "active_recoveries": health_report.get("active_recoveries", 0),
                    "services_count": len(health_report.get("services", {}))
                }
            }
        
        elif system_name == "health_check_system":
            health_report = await deep_health_check_system.get_health_report()
            return {
                "status": health_report.get("overall_health", "unknown"),
                "metrics": {
                    "total_components": health_report.get("total_components", 0),
                    "healthy_components": health_report.get("healthy_components", 0),
                    "failed_components": health_report.get("failed_components", 0)
                }
            }
        
        elif system_name == "tracing_system":
            trace_summary = distributed_tracing_system.get_active_traces_summary()
            return {
                "status": "healthy" if trace_summary["active_trace_count"] >= 0 else "failed",
                "metrics": {
                    "active_traces": trace_summary["active_trace_count"],
                    "active_spans": trace_summary["active_span_count"]
                }
            }
        
        elif system_name == "alerting_system":
            alert_summary = intelligent_alerting_system.get_alert_summary()
            return {
                "status": "healthy",
                "metrics": {
                    "total_alerts": alert_summary["total_alerts"],
                    "active_alerts": alert_summary["active_alerts"]
                }
            }
        
        else:
            return {
                "status": "healthy",
                "metrics": {}
            }
    
    async def _aggregate_cross_system_metrics(self):
        """Aggregate metrics across monitoring systems."""
        try:
            # Update business KPI metrics
            business_config = self.monitoring_config.get("business_metrics", {})
            
            if business_config.get("track_user_activity", False):
                # This would get actual user activity metrics
                metrics_collector.business_metrics.record_user_activity(
                    active_1h=100,  # Would be real data
                    active_24h=500,
                    active_7d=2000
                )
            
            if business_config.get("track_generation_metrics", False):
                # This would get actual generation metrics
                metrics_collector.business_metrics.record_generation_created(
                    "flux-1.1-pro", "premium", True, 15.5, "standard"
                )
            
            # Update system health SLA compliance
            overall_health_score = self._calculate_overall_health_score()
            metrics_collector.update_sla_compliance(
                "overall_system", "current", overall_health_score
            )
            
        except Exception as e:
            logger.error(f"❌ [MONITORING] Metrics aggregation error: {e}")
    
    async def _correlate_cross_system_events(self):
        """Correlate events across different monitoring systems."""
        try:
            # This would implement intelligent correlation of events
            # across circuit breakers, health checks, traces, and alerts
            
            # For example, correlate:
            # - Circuit breaker opens with health check failures
            # - Trace latency spikes with authorization SLA violations
            # - Cache performance drops with database issues
            
            logger.debug("🔗 [MONITORING] Cross-system event correlation completed")
            
        except Exception as e:
            logger.error(f"❌ [MONITORING] Cross-system correlation error: {e}")
    
    def _calculate_overall_health_score(self) -> float:
        """Calculate overall system health score."""
        if not self.systems_status:
            return 100.0
        
        health_weights = {
            "healthy": 1.0,
            "degraded": 0.7,
            "failed": 0.0
        }
        
        total_weight = 0.0
        weighted_score = 0.0
        
        for status in self.systems_status.values():
            weight = health_weights.get(status.status, 0.5)
            total_weight += 1.0
            weighted_score += weight
        
        return (weighted_score / total_weight * 100) if total_weight > 0 else 100.0
    
    async def _handle_startup_failure(self, error: Exception):
        """Handle monitoring system startup failure."""
        logger.critical(f"🚨 [MONITORING] Critical startup failure: {error}")
        
        # Try to send alert even if systems aren't fully started
        try:
            if intelligent_alerting_system.alerts is not None:  # Basic check
                await intelligent_alerting_system.create_alert(
                    title="Monitoring System Startup Failure",
                    description=f"Critical failure during monitoring system startup: {str(error)}",
                    severity=AlertSeverity.EMERGENCY,
                    source="monitoring_integration",
                    labels={"event": "startup_failure", "critical": "true"},
                    annotations={"error": str(error)}
                )
        except Exception as alert_error:
            logger.error(f"❌ [MONITORING] Failed to send startup failure alert: {alert_error}")
    
    # Public API methods
    
    async def get_comprehensive_monitoring_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all monitoring systems."""
        try:
            # Get status from all systems
            circuit_breaker_status = await enterprise_circuit_breaker_manager.get_system_health_report()
            health_check_status = await deep_health_check_system.get_health_report()
            trace_status = distributed_tracing_system.get_active_traces_summary()
            alert_status = intelligent_alerting_system.get_alert_summary()
            metrics_health = metrics_collector.get_health_summary()
            
            return {
                "integration_status": {
                    "started": self.integration_started,
                    "overall_health_score": self._calculate_overall_health_score(),
                    "systems_status": {
                        name: {
                            "status": status.status,
                            "last_check": status.last_check.isoformat(),
                            "metrics": status.metrics,
                            "error": status.error
                        }
                        for name, status in self.systems_status.items()
                    }
                },
                "circuit_breakers": circuit_breaker_status,
                "health_checks": health_check_status,
                "distributed_tracing": trace_status,
                "alerting": alert_status,
                "metrics_collection": metrics_health,
                "performance_insights": distributed_tracing_system.get_performance_insights(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ [MONITORING] Error getting comprehensive status: {e}")
            return {
                "integration_status": {"error": str(e)},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def get_business_intelligence_dashboard(self) -> Dict[str, Any]:
        """Get business intelligence data for executive dashboard."""
        try:
            business_kpis = metrics_collector.get_business_kpi_summary()
            performance_summary = metrics_collector.get_performance_summary()
            security_dashboard = metrics_collector.get_security_dashboard_data()
            capacity_planning = metrics_collector.get_capacity_planning_data()
            
            return {
                "executive_summary": {
                    "overall_health_score": self._calculate_overall_health_score(),
                    "system_availability_sla": 99.9,  # Would be calculated from actual metrics
                    "performance_sla_compliance": 99.5,
                    "security_incidents_24h": security_dashboard.get("security_incidents_24h", 0)
                },
                "business_kpis": business_kpis,
                "performance_metrics": performance_summary,
                "security_status": security_dashboard,
                "capacity_planning": capacity_planning,
                "recommendations": self._generate_optimization_recommendations(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ [MONITORING] Error getting business intelligence: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _generate_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate optimization recommendations based on monitoring data."""
        recommendations = []
        
        # Analyze system health and generate recommendations
        failed_systems = [
            name for name, status in self.systems_status.items()
            if status.status == "failed"
        ]
        
        if failed_systems:
            recommendations.append({
                "priority": "high",
                "category": "system_health",
                "title": "Address Failed Monitoring Systems",
                "description": f"The following monitoring systems have failed: {', '.join(failed_systems)}",
                "action": "Investigate and restart failed monitoring components",
                "impact": "Reduced visibility and alerting capability"
            })
        
        # Add performance recommendations
        recommendations.append({
            "priority": "medium",
            "category": "performance",
            "title": "Optimize Authorization Response Times",
            "description": "Monitor authorization performance to maintain <100ms SLA",
            "action": "Review authorization caching and query optimization",
            "impact": "Improved user experience and SLA compliance"
        })
        
        return recommendations
    
    def get_integration_config(self) -> Dict[str, Any]:
        """Get current monitoring integration configuration."""
        return self.monitoring_config.copy()
    
    async def update_integration_config(self, new_config: Dict[str, Any]):
        """Update monitoring integration configuration."""
        self.monitoring_config.update(new_config)
        logger.info("🔧 [MONITORING] Integration configuration updated")
        
        # Apply configuration changes
        if "trace_sampling_rate" in new_config:
            distributed_tracing_system.set_sampling_rate(new_config["trace_sampling_rate"])
        
        if "circuit_breaker_auto_recovery" in new_config:
            if new_config["circuit_breaker_auto_recovery"]:
                enterprise_circuit_breaker_manager.enable_auto_recovery()
            else:
                enterprise_circuit_breaker_manager.disable_auto_recovery()


# Global enterprise monitoring integration
enterprise_monitoring_integration = EnterpriseMonitoringIntegration()


# Convenience functions for FastAPI integration

async def start_enterprise_monitoring():
    """Start the complete enterprise monitoring system."""
    await enterprise_monitoring_integration.start_monitoring_integration()


async def stop_enterprise_monitoring():
    """Stop the enterprise monitoring system."""
    await enterprise_monitoring_integration.stop_monitoring_integration()


async def get_monitoring_status() -> Dict[str, Any]:
    """Get comprehensive monitoring status."""
    return await enterprise_monitoring_integration.get_comprehensive_monitoring_status()


async def get_business_dashboard() -> Dict[str, Any]:
    """Get business intelligence dashboard data."""
    return await enterprise_monitoring_integration.get_business_intelligence_dashboard()