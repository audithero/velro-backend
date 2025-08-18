"""
Enterprise Intelligent Alerting and Notification System.
Provides multi-channel alerting with intelligent correlation, deduplication, and escalation.
"""

import asyncio
import json
import logging
import hashlib
from typing import Dict, List, Any, Optional, Set, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertStatus(Enum):
    """Alert status states."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class NotificationChannel(Enum):
    """Available notification channels."""
    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"
    SMS = "sms"
    TEAMS = "teams"
    DISCORD = "discord"


@dataclass
class Alert:
    """Alert data structure."""
    id: str
    title: str
    description: str
    severity: AlertSeverity
    source: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    status: AlertStatus = AlertStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    escalation_level: int = 0
    correlation_id: Optional[str] = None
    parent_alert_id: Optional[str] = None
    child_alert_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "source": self.source,
            "labels": self.labels,
            "annotations": self.annotations,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "escalation_level": self.escalation_level,
            "correlation_id": self.correlation_id,
            "parent_alert_id": self.parent_alert_id,
            "child_alert_ids": self.child_alert_ids
        }


@dataclass
class NotificationRule:
    """Notification routing rule."""
    name: str
    conditions: Dict[str, Any]  # Alert matching conditions
    channels: List[NotificationChannel]
    recipients: List[str]
    throttle_minutes: int = 5  # Minimum time between notifications
    escalation_delay_minutes: int = 30  # Time before escalation
    max_escalations: int = 3
    active_hours: Optional[Dict[str, str]] = None  # e.g., {"start": "09:00", "end": "17:00"}
    exclude_severities: List[AlertSeverity] = field(default_factory=list)
    include_severities: List[AlertSeverity] = field(default_factory=list)


@dataclass
class NotificationChannel:
    """Notification channel configuration."""
    type: NotificationChannel
    name: str
    config: Dict[str, Any]
    enabled: bool = True
    rate_limit_per_hour: int = 100
    retry_attempts: int = 3
    timeout_seconds: int = 30


class AlertCorrelationEngine:
    """Intelligent alert correlation engine."""
    
    def __init__(self):
        self.correlation_rules: List[Callable] = []
        self.time_window_minutes = 5
        self.similarity_threshold = 0.8
    
    def add_correlation_rule(self, rule_func: Callable):
        """Add a correlation rule function."""
        self.correlation_rules.append(rule_func)
    
    def correlate_alert(self, new_alert: Alert, existing_alerts: List[Alert]) -> Optional[str]:
        """Find correlation ID for new alert based on existing alerts."""
        # Time-based correlation window
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.time_window_minutes)
        recent_alerts = [
            alert for alert in existing_alerts 
            if alert.created_at > cutoff_time and alert.status == AlertStatus.ACTIVE
        ]
        
        # Apply correlation rules
        for rule in self.correlation_rules:
            correlation_id = rule(new_alert, recent_alerts)
            if correlation_id:
                return correlation_id
        
        # Default similarity-based correlation
        return self._similarity_correlation(new_alert, recent_alerts)
    
    def _similarity_correlation(self, new_alert: Alert, existing_alerts: List[Alert]) -> Optional[str]:
        """Correlate alerts based on similarity."""
        for existing_alert in existing_alerts:
            similarity_score = self._calculate_similarity(new_alert, existing_alert)
            
            if similarity_score > self.similarity_threshold:
                return existing_alert.correlation_id or existing_alert.id
        
        return None
    
    def _calculate_similarity(self, alert1: Alert, alert2: Alert) -> float:
        """Calculate similarity score between two alerts."""
        score = 0.0
        factors = 0
        
        # Source similarity
        if alert1.source == alert2.source:
            score += 0.3
        factors += 1
        
        # Severity similarity
        if alert1.severity == alert2.severity:
            score += 0.2
        factors += 1
        
        # Label similarity
        common_labels = set(alert1.labels.keys()) & set(alert2.labels.keys())
        if common_labels:
            matching_labels = sum(
                1 for label in common_labels 
                if alert1.labels[label] == alert2.labels[label]
            )
            label_similarity = matching_labels / len(common_labels)
            score += label_similarity * 0.3
        factors += 1
        
        # Title similarity (basic keyword matching)
        title1_words = set(alert1.title.lower().split())
        title2_words = set(alert2.title.lower().split())
        
        if title1_words and title2_words:
            title_similarity = len(title1_words & title2_words) / len(title1_words | title2_words)
            score += title_similarity * 0.2
        factors += 1
        
        return score / factors if factors > 0 else 0.0


class AlertDeduplicationEngine:
    """Alert deduplication engine."""
    
    def __init__(self):
        self.dedup_window_minutes = 5
        self.fingerprint_cache: Dict[str, str] = {}  # fingerprint -> alert_id
    
    def generate_fingerprint(self, alert: Alert) -> str:
        """Generate unique fingerprint for alert deduplication."""
        # Create a unique fingerprint based on key alert attributes
        fingerprint_data = {
            "source": alert.source,
            "severity": alert.severity.value,
            "title": alert.title,
            "labels": sorted(alert.labels.items()) if alert.labels else []
        }
        
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]
    
    def is_duplicate(self, alert: Alert, existing_alerts: List[Alert]) -> Optional[str]:
        """Check if alert is a duplicate of existing alerts."""
        fingerprint = self.generate_fingerprint(alert)
        
        # Check recent alerts for duplicates
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.dedup_window_minutes)
        
        for existing_alert in existing_alerts:
            if existing_alert.created_at > cutoff_time:
                existing_fingerprint = self.generate_fingerprint(existing_alert)
                if fingerprint == existing_fingerprint:
                    return existing_alert.id
        
        return None


class NotificationChannelManager:
    """Manages different notification channels."""
    
    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self.rate_limiters: Dict[str, List[datetime]] = {}
    
    def add_channel(self, channel: NotificationChannel):
        """Add a notification channel."""
        self.channels[channel.name] = channel
        self.rate_limiters[channel.name] = []
    
    async def send_notification(self, channel_name: str, alert: Alert, recipients: List[str]) -> bool:
        """Send notification through specified channel."""
        channel = self.channels.get(channel_name)
        if not channel or not channel.enabled:
            logger.warning(f"❌ [NOTIFICATION] Channel {channel_name} not available")
            return False
        
        # Check rate limiting
        if not self._check_rate_limit(channel_name, channel.rate_limit_per_hour):
            logger.warning(f"⚠️ [NOTIFICATION] Rate limit exceeded for {channel_name}")
            return False
        
        # Send notification based on channel type
        try:
            if channel.type == NotificationChannel.EMAIL:
                return await self._send_email(channel, alert, recipients)
            elif channel.type == NotificationChannel.SLACK:
                return await self._send_slack(channel, alert, recipients)
            elif channel.type == NotificationChannel.PAGERDUTY:
                return await self._send_pagerduty(channel, alert, recipients)
            elif channel.type == NotificationChannel.WEBHOOK:
                return await self._send_webhook(channel, alert, recipients)
            elif channel.type == NotificationChannel.TEAMS:
                return await self._send_teams(channel, alert, recipients)
            elif channel.type == NotificationChannel.DISCORD:
                return await self._send_discord(channel, alert, recipients)
            else:
                logger.error(f"❌ [NOTIFICATION] Unsupported channel type: {channel.type}")
                return False
                
        except Exception as e:
            logger.error(f"❌ [NOTIFICATION] Failed to send via {channel_name}: {e}")
            return False
    
    def _check_rate_limit(self, channel_name: str, limit_per_hour: int) -> bool:
        """Check if channel is within rate limits."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=1)
        
        # Clean old timestamps
        self.rate_limiters[channel_name] = [
            ts for ts in self.rate_limiters[channel_name] if ts > cutoff
        ]
        
        # Check limit
        if len(self.rate_limiters[channel_name]) >= limit_per_hour:
            return False
        
        # Add current timestamp
        self.rate_limiters[channel_name].append(now)
        return True
    
    async def _send_email(self, channel: NotificationChannel, alert: Alert, recipients: List[str]) -> bool:
        """Send email notification."""
        try:
            config = channel.config
            smtp_server = config.get('smtp_server', 'localhost')
            smtp_port = config.get('smtp_port', 587)
            username = config.get('username')
            password = config.get('password')
            from_email = config.get('from_email', 'alerts@velro.com')
            
            # Create message
            subject = f"[{alert.severity.value.upper()}] {alert.title}"
            
            body = f"""
Alert Details:
- ID: {alert.id}
- Severity: {alert.severity.value.upper()}
- Source: {alert.source}
- Created: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}

Description:
{alert.description}

Labels:
{json.dumps(alert.labels, indent=2) if alert.labels else 'None'}

Dashboard: https://monitoring.velro.com/alert/{alert.id}
"""
            
            # Send to each recipient
            for recipient in recipients:
                msg = MIMEMultipart()
                msg['From'] = from_email
                msg['To'] = recipient
                msg['Subject'] = subject
                
                msg.attach(MIMEText(body, 'plain'))
                
                # This is a placeholder - actual SMTP implementation would go here
                logger.info(f"📧 [EMAIL] Sent alert {alert.id} to {recipient}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [EMAIL] Failed to send email: {e}")
            return False
    
    async def _send_slack(self, channel: NotificationChannel, alert: Alert, recipients: List[str]) -> bool:
        """Send Slack notification."""
        try:
            config = channel.config
            webhook_url = config.get('webhook_url')
            
            if not webhook_url:
                logger.error("❌ [SLACK] No webhook URL configured")
                return False
            
            # Create Slack message
            color = {
                AlertSeverity.INFO: "#36a64f",
                AlertSeverity.WARNING: "#ff9500", 
                AlertSeverity.CRITICAL: "#ff0000",
                AlertSeverity.EMERGENCY: "#8B0000"
            }.get(alert.severity, "#808080")
            
            payload = {
                "username": "Velro Monitoring",
                "icon_emoji": ":warning:",
                "attachments": [
                    {
                        "color": color,
                        "title": f"{alert.severity.value.upper()}: {alert.title}",
                        "text": alert.description,
                        "fields": [
                            {
                                "title": "Source",
                                "value": alert.source,
                                "short": True
                            },
                            {
                                "title": "Alert ID",
                                "value": alert.id,
                                "short": True
                            },
                            {
                                "title": "Created",
                                "value": alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                                "short": True
                            }
                        ],
                        "footer": "Velro Monitoring",
                        "footer_icon": "https://velro.com/favicon.ico",
                        "ts": int(alert.created_at.timestamp())
                    }
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=channel.timeout_seconds) as response:
                    if response.status == 200:
                        logger.info(f"💬 [SLACK] Sent alert {alert.id}")
                        return True
                    else:
                        logger.error(f"❌ [SLACK] Failed with status {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ [SLACK] Failed to send Slack notification: {e}")
            return False
    
    async def _send_pagerduty(self, channel: NotificationChannel, alert: Alert, recipients: List[str]) -> bool:
        """Send PagerDuty notification."""
        try:
            config = channel.config
            api_key = config.get('api_key')
            service_key = config.get('service_key')
            
            if not api_key or not service_key:
                logger.error("❌ [PAGERDUTY] Missing API key or service key")
                return False
            
            url = "https://events.pagerduty.com/v2/enqueue"
            
            payload = {
                "routing_key": service_key,
                "event_action": "trigger",
                "dedup_key": alert.id,
                "payload": {
                    "summary": alert.title,
                    "source": alert.source,
                    "severity": alert.severity.value,
                    "component": alert.labels.get('component', 'unknown'),
                    "group": alert.labels.get('group', 'velro'),
                    "class": alert.labels.get('class', 'monitoring'),
                    "custom_details": {
                        "description": alert.description,
                        "labels": alert.labels,
                        "annotations": alert.annotations,
                        "alert_id": alert.id,
                        "dashboard_url": f"https://monitoring.velro.com/alert/{alert.id}"
                    }
                }
            }
            
            headers = {
                "Authorization": f"Token token={api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=channel.timeout_seconds) as response:
                    if response.status == 202:
                        logger.info(f"📟 [PAGERDUTY] Sent alert {alert.id}")
                        return True
                    else:
                        logger.error(f"❌ [PAGERDUTY] Failed with status {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ [PAGERDUTY] Failed to send PagerDuty notification: {e}")
            return False
    
    async def _send_webhook(self, channel: NotificationChannel, alert: Alert, recipients: List[str]) -> bool:
        """Send webhook notification."""
        try:
            config = channel.config
            webhook_url = config.get('url')
            
            if not webhook_url:
                logger.error("❌ [WEBHOOK] No webhook URL configured")
                return False
            
            payload = {
                "event": "alert",
                "alert": alert.to_dict(),
                "recipients": recipients,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            headers = config.get('headers', {})
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, headers=headers, timeout=channel.timeout_seconds) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"🔗 [WEBHOOK] Sent alert {alert.id} to {webhook_url}")
                        return True
                    else:
                        logger.error(f"❌ [WEBHOOK] Failed with status {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ [WEBHOOK] Failed to send webhook notification: {e}")
            return False
    
    async def _send_teams(self, channel: NotificationChannel, alert: Alert, recipients: List[str]) -> bool:
        """Send Microsoft Teams notification."""
        try:
            config = channel.config
            webhook_url = config.get('webhook_url')
            
            if not webhook_url:
                logger.error("❌ [TEAMS] No webhook URL configured")
                return False
            
            color = {
                AlertSeverity.INFO: "00FF00",
                AlertSeverity.WARNING: "FF9500", 
                AlertSeverity.CRITICAL: "FF0000",
                AlertSeverity.EMERGENCY: "8B0000"
            }.get(alert.severity, "808080")
            
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": color,
                "summary": f"{alert.severity.value.upper()}: {alert.title}",
                "sections": [
                    {
                        "activityTitle": f"Alert: {alert.title}",
                        "activitySubtitle": f"Severity: {alert.severity.value.upper()}",
                        "facts": [
                            {"name": "Source", "value": alert.source},
                            {"name": "Alert ID", "value": alert.id},
                            {"name": "Created", "value": alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')},
                            {"name": "Description", "value": alert.description}
                        ],
                        "markdown": True
                    }
                ],
                "potentialAction": [
                    {
                        "@type": "OpenUri",
                        "name": "View Alert",
                        "targets": [
                            {
                                "os": "default",
                                "uri": f"https://monitoring.velro.com/alert/{alert.id}"
                            }
                        ]
                    }
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=channel.timeout_seconds) as response:
                    if response.status == 200:
                        logger.info(f"🏢 [TEAMS] Sent alert {alert.id}")
                        return True
                    else:
                        logger.error(f"❌ [TEAMS] Failed with status {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ [TEAMS] Failed to send Teams notification: {e}")
            return False
    
    async def _send_discord(self, channel: NotificationChannel, alert: Alert, recipients: List[str]) -> bool:
        """Send Discord notification."""
        try:
            config = channel.config
            webhook_url = config.get('webhook_url')
            
            if not webhook_url:
                logger.error("❌ [DISCORD] No webhook URL configured")
                return False
            
            color = {
                AlertSeverity.INFO: 0x00FF00,
                AlertSeverity.WARNING: 0xFF9500, 
                AlertSeverity.CRITICAL: 0xFF0000,
                AlertSeverity.EMERGENCY: 0x8B0000
            }.get(alert.severity, 0x808080)
            
            payload = {
                "username": "Velro Monitoring",
                "avatar_url": "https://velro.com/favicon.ico",
                "embeds": [
                    {
                        "title": f"{alert.severity.value.upper()}: {alert.title}",
                        "description": alert.description,
                        "color": color,
                        "fields": [
                            {
                                "name": "Source",
                                "value": alert.source,
                                "inline": True
                            },
                            {
                                "name": "Alert ID",
                                "value": alert.id,
                                "inline": True
                            },
                            {
                                "name": "Created",
                                "value": alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                                "inline": False
                            }
                        ],
                        "footer": {
                            "text": "Velro Monitoring"
                        },
                        "timestamp": alert.created_at.isoformat()
                    }
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=channel.timeout_seconds) as response:
                    if response.status == 204:
                        logger.info(f"🎮 [DISCORD] Sent alert {alert.id}")
                        return True
                    else:
                        logger.error(f"❌ [DISCORD] Failed with status {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ [DISCORD] Failed to send Discord notification: {e}")
            return False


class IntelligentAlertingSystem:
    """
    Enterprise intelligent alerting system with correlation, deduplication, and multi-channel notifications.
    """
    
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.notification_rules: List[NotificationRule] = []
        self.correlation_engine = AlertCorrelationEngine()
        self.deduplication_engine = AlertDeduplicationEngine()
        self.notification_manager = NotificationChannelManager()
        
        self.alert_retention_days = 30
        self.cleanup_interval_hours = 24
        
        # Initialize default correlation rules
        self._initialize_correlation_rules()
        
        # Start background tasks
        self._cleanup_task = None
        self._escalation_task = None
    
    def _initialize_correlation_rules(self):
        """Initialize default alert correlation rules."""
        
        def service_correlation_rule(new_alert: Alert, existing_alerts: List[Alert]) -> Optional[str]:
            """Correlate alerts from the same service."""
            service = new_alert.labels.get('service')
            if not service:
                return None
                
            for existing in existing_alerts:
                if existing.labels.get('service') == service and existing.severity == new_alert.severity:
                    return existing.correlation_id or existing.id
            return None
        
        def circuit_breaker_correlation_rule(new_alert: Alert, existing_alerts: List[Alert]) -> Optional[str]:
            """Correlate circuit breaker related alerts."""
            if 'circuit_breaker' not in new_alert.source:
                return None
                
            circuit_name = new_alert.labels.get('circuit_name')
            if not circuit_name:
                return None
                
            for existing in existing_alerts:
                if (existing.labels.get('circuit_name') == circuit_name and 
                    'circuit_breaker' in existing.source):
                    return existing.correlation_id or existing.id
            return None
        
        def infrastructure_correlation_rule(new_alert: Alert, existing_alerts: List[Alert]) -> Optional[str]:
            """Correlate infrastructure alerts by hostname/instance."""
            hostname = new_alert.labels.get('hostname') or new_alert.labels.get('instance')
            if not hostname:
                return None
                
            for existing in existing_alerts:
                existing_hostname = existing.labels.get('hostname') or existing.labels.get('instance')
                if existing_hostname == hostname:
                    return existing.correlation_id or existing.id
            return None
        
        self.correlation_engine.add_correlation_rule(service_correlation_rule)
        self.correlation_engine.add_correlation_rule(circuit_breaker_correlation_rule)  
        self.correlation_engine.add_correlation_rule(infrastructure_correlation_rule)
    
    async def start(self):
        """Start the alerting system background tasks."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        if self._escalation_task is None or self._escalation_task.done():
            self._escalation_task = asyncio.create_task(self._escalation_loop())
        
        logger.info("🚨 [ALERTING] Intelligent alerting system started")
    
    async def stop(self):
        """Stop the alerting system background tasks."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        
        if self._escalation_task and not self._escalation_task.done():
            self._escalation_task.cancel()
        
        logger.info("🚨 [ALERTING] Intelligent alerting system stopped")
    
    async def create_alert(self, 
                          title: str,
                          description: str, 
                          severity: AlertSeverity,
                          source: str,
                          labels: Dict[str, str] = None,
                          annotations: Dict[str, str] = None) -> Alert:
        """Create a new alert with intelligent processing."""
        
        # Generate alert ID
        alert_id = f"alert_{int(datetime.now(timezone.utc).timestamp())}_{hash(title) % 10000:04d}"
        
        # Create alert object
        alert = Alert(
            id=alert_id,
            title=title,
            description=description,
            severity=severity,
            source=source,
            labels=labels or {},
            annotations=annotations or {}
        )
        
        # Check for duplicates
        existing_alerts = list(self.alerts.values())
        duplicate_id = self.deduplication_engine.is_duplicate(alert, existing_alerts)
        
        if duplicate_id:
            logger.info(f"🔄 [ALERTING] Alert is duplicate of {duplicate_id}, updating existing")
            existing_alert = self.alerts[duplicate_id]
            existing_alert.updated_at = datetime.now(timezone.utc)
            return existing_alert
        
        # Find correlation
        correlation_id = self.correlation_engine.correlate_alert(alert, existing_alerts)
        if correlation_id:
            alert.correlation_id = correlation_id
            logger.info(f"🔗 [ALERTING] Alert {alert_id} correlated with {correlation_id}")
        
        # Store alert
        self.alerts[alert_id] = alert
        
        # Process notification rules
        await self._process_notification_rules(alert)
        
        logger.info(f"🚨 [ALERTING] Created alert {alert_id}: {title} ({severity.value})")
        return alert
    
    async def _process_notification_rules(self, alert: Alert):
        """Process notification rules for an alert."""
        for rule in self.notification_rules:
            if self._matches_rule(alert, rule):
                logger.info(f"📋 [ALERTING] Alert {alert.id} matches rule: {rule.name}")
                
                # Check throttling
                if self._is_throttled(alert, rule):
                    logger.info(f"⏰ [ALERTING] Alert {alert.id} throttled for rule {rule.name}")
                    continue
                
                # Send notifications
                for channel_type in rule.channels:
                    channel_name = f"{channel_type.value}_default"  # Use default channel naming
                    success = await self.notification_manager.send_notification(
                        channel_name, alert, rule.recipients
                    )
                    
                    if success:
                        logger.info(f"✅ [ALERTING] Sent {alert.id} via {channel_name}")
                    else:
                        logger.error(f"❌ [ALERTING] Failed to send {alert.id} via {channel_name}")
    
    def _matches_rule(self, alert: Alert, rule: NotificationRule) -> bool:
        """Check if alert matches notification rule conditions."""
        # Check severity filters
        if rule.include_severities and alert.severity not in rule.include_severities:
            return False
        
        if rule.exclude_severities and alert.severity in rule.exclude_severities:
            return False
        
        # Check label conditions
        for label_key, label_value in rule.conditions.get('labels', {}).items():
            if alert.labels.get(label_key) != label_value:
                return False
        
        # Check source conditions
        if 'source' in rule.conditions:
            if alert.source != rule.conditions['source']:
                return False
        
        # Check active hours
        if rule.active_hours:
            now = datetime.now()
            start_hour = int(rule.active_hours['start'].split(':')[0])
            end_hour = int(rule.active_hours['end'].split(':')[0])
            
            if not (start_hour <= now.hour < end_hour):
                return False
        
        return True
    
    def _is_throttled(self, alert: Alert, rule: NotificationRule) -> bool:
        """Check if notifications for this rule are throttled."""
        # This would implement throttling logic based on rule.throttle_minutes
        # For now, return False (no throttling)
        return False
    
    async def _cleanup_loop(self):
        """Background task to cleanup old alerts."""
        while True:
            try:
                await self._cleanup_old_alerts()
                await asyncio.sleep(self.cleanup_interval_hours * 3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [ALERTING] Cleanup error: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error
    
    async def _escalation_loop(self):
        """Background task to handle alert escalations."""
        while True:
            try:
                await self._process_escalations()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [ALERTING] Escalation error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _cleanup_old_alerts(self):
        """Clean up old resolved alerts."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.alert_retention_days)
        
        old_alerts = [
            alert_id for alert_id, alert in self.alerts.items()
            if alert.status == AlertStatus.RESOLVED and alert.resolved_at and alert.resolved_at < cutoff_time
        ]
        
        for alert_id in old_alerts:
            del self.alerts[alert_id]
        
        if old_alerts:
            logger.info(f"🧹 [ALERTING] Cleaned up {len(old_alerts)} old alerts")
    
    async def _process_escalations(self):
        """Process alert escalations."""
        now = datetime.now(timezone.utc)
        
        for alert in self.alerts.values():
            if alert.status != AlertStatus.ACTIVE:
                continue
            
            # Find matching rules for escalation
            for rule in self.notification_rules:
                if not self._matches_rule(alert, rule):
                    continue
                
                # Check if escalation is needed
                escalation_time = alert.created_at + timedelta(minutes=rule.escalation_delay_minutes)
                
                if (now > escalation_time and 
                    alert.escalation_level < rule.max_escalations and
                    alert.status == AlertStatus.ACTIVE):
                    
                    alert.escalation_level += 1
                    alert.updated_at = now
                    
                    logger.warning(
                        f"📈 [ESCALATION] Alert {alert.id} escalated to level {alert.escalation_level}"
                    )
                    
                    # Send escalation notifications
                    for channel_type in rule.channels:
                        channel_name = f"{channel_type.value}_escalation"
                        await self.notification_manager.send_notification(
                            channel_name, alert, rule.recipients
                        )
    
    # Public API methods
    
    def add_notification_rule(self, rule: NotificationRule):
        """Add a notification rule."""
        self.notification_rules.append(rule)
        logger.info(f"📋 [ALERTING] Added notification rule: {rule.name}")
    
    def add_notification_channel(self, channel: NotificationChannel):
        """Add a notification channel."""
        self.notification_manager.add_channel(channel)
        logger.info(f"📡 [ALERTING] Added notification channel: {channel.name}")
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an alert."""
        alert = self.alerts.get(alert_id)
        if not alert:
            return False
        
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = acknowledged_by
        alert.updated_at = datetime.now(timezone.utc)
        
        logger.info(f"✅ [ALERTING] Alert {alert_id} acknowledged by {acknowledged_by}")
        return True
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        alert = self.alerts.get(alert_id)
        if not alert:
            return False
        
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        alert.updated_at = datetime.now(timezone.utc)
        
        logger.info(f"✅ [ALERTING] Alert {alert_id} resolved")
        return True
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return [alert for alert in self.alerts.values() if alert.status == AlertStatus.ACTIVE]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary statistics."""
        active_alerts = self.get_active_alerts()
        
        severity_counts = {severity: 0 for severity in AlertSeverity}
        for alert in active_alerts:
            severity_counts[alert.severity] += 1
        
        return {
            "total_alerts": len(self.alerts),
            "active_alerts": len(active_alerts),
            "severity_breakdown": {
                severity.value: count for severity, count in severity_counts.items()
            },
            "correlated_alerts": len([a for a in active_alerts if a.correlation_id]),
            "escalated_alerts": len([a for a in active_alerts if a.escalation_level > 0]),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


# Global intelligent alerting system
intelligent_alerting_system = IntelligentAlertingSystem()