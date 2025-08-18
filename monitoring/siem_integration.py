"""
SIEM Integration for Security Monitoring and Compliance
Provides structured log forwarding and real-time threat detection integration.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import hashlib
import hmac
from contextlib import asynccontextmanager

from monitoring.logger import security_logger, audit_logger, EventType, LogLevel
from monitoring.metrics import metrics_collector

logger = logging.getLogger(__name__)


class SIEMProvider(Enum):
    """Supported SIEM providers."""
    SPLUNK = "splunk"
    ELASTIC_SECURITY = "elastic_security"
    AZURE_SENTINEL = "azure_sentinel"
    AWS_SECURITY_HUB = "aws_security_hub"
    CUSTOM_WEBHOOK = "custom_webhook"


class ThreatLevel(Enum):
    """Threat severity levels for SIEM correlation."""
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SIEMEvent:
    """Structured SIEM event format."""
    event_id: str
    timestamp: datetime
    event_type: str
    threat_level: ThreatLevel
    source_ip: Optional[str]
    user_id: Optional[str]
    session_id: Optional[str]
    endpoint: Optional[str]
    description: str
    raw_data: Dict[str, Any]
    indicators: List[str]
    mitre_attack_tactics: List[str]
    compliance_tags: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['threat_level'] = self.threat_level.value
        return data


class SIEMIntegration:
    """
    Production-ready SIEM integration with multiple provider support.
    Handles security event forwarding, threat correlation, and compliance logging.
    """
    
    def __init__(self, 
                 provider: SIEMProvider = SIEMProvider.CUSTOM_WEBHOOK,
                 endpoint_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 api_secret: Optional[str] = None,
                 batch_size: int = 100,
                 flush_interval: int = 30):
        
        self.provider = provider
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        
        # Event batching for performance
        self._event_buffer: List[SIEMEvent] = []
        self._buffer_lock = asyncio.Lock()
        self._last_flush = time.time()
        
        # Statistics tracking
        self._stats = {
            'events_sent': 0,
            'events_failed': 0,
            'batches_sent': 0,
            'last_successful_send': None,
            'connection_errors': 0
        }
        
        # Background task for periodic flushing
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start the SIEM integration service."""
        if self._running:
            return
            
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info(f"✅ SIEM integration started ({self.provider.value})")
    
    async def stop(self):
        """Stop the SIEM integration service."""
        self._running = False
        
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining events
        await self._flush_events()
        logger.info("🛑 SIEM integration stopped")
    
    async def send_security_event(self, 
                                 event_type: str,
                                 description: str,
                                 threat_level: ThreatLevel = ThreatLevel.MEDIUM,
                                 source_ip: Optional[str] = None,
                                 user_id: Optional[str] = None,
                                 session_id: Optional[str] = None,
                                 endpoint: Optional[str] = None,
                                 raw_data: Optional[Dict[str, Any]] = None,
                                 indicators: Optional[List[str]] = None,
                                 mitre_tactics: Optional[List[str]] = None) -> bool:
        """Send security event to SIEM system."""
        
        event = SIEMEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            threat_level=threat_level,
            source_ip=source_ip,
            user_id=user_id,
            session_id=session_id,
            endpoint=endpoint,
            description=description,
            raw_data=raw_data or {},
            indicators=indicators or [],
            mitre_attack_tactics=mitre_tactics or [],
            compliance_tags=self._get_compliance_tags(event_type, threat_level)
        )
        
        async with self._buffer_lock:
            self._event_buffer.append(event)
            
            # Auto-flush for critical events or when buffer is full
            if (threat_level == ThreatLevel.CRITICAL or 
                len(self._event_buffer) >= self.batch_size):
                await self._flush_events()
        
        # Log locally for backup
        await self._log_event_locally(event)
        
        return True
    
    async def send_authorization_violation(self,
                                         user_id: str,
                                         resource: str,
                                         violation_type: str,
                                         source_ip: str,
                                         session_id: Optional[str] = None) -> bool:
        """Send authorization violation to SIEM."""
        
        indicators = [
            f"user_id:{user_id}",
            f"resource:{resource}",
            f"source_ip:{source_ip}"
        ]
        
        mitre_tactics = []
        threat_level = ThreatLevel.MEDIUM
        
        # Classify threat based on violation type
        if "brute_force" in violation_type.lower():
            mitre_tactics = ["TA0006"]  # Credential Access
            threat_level = ThreatLevel.HIGH
        elif "privilege_escalation" in violation_type.lower():
            mitre_tactics = ["TA0004"]  # Privilege Escalation
            threat_level = ThreatLevel.CRITICAL
        elif "unauthorized_access" in violation_type.lower():
            mitre_tactics = ["TA0001"]  # Initial Access
            threat_level = ThreatLevel.HIGH
        
        return await self.send_security_event(
            event_type="authorization_violation",
            description=f"Authorization violation: {violation_type} by user {user_id}",
            threat_level=threat_level,
            source_ip=source_ip,
            user_id=user_id,
            session_id=session_id,
            raw_data={
                "resource": resource,
                "violation_type": violation_type,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            indicators=indicators,
            mitre_tactics=mitre_tactics
        )
    
    async def send_performance_anomaly(self,
                                     metric_name: str,
                                     current_value: float,
                                     threshold_value: float,
                                     endpoint: str,
                                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send performance anomaly that might indicate attack."""
        
        # Performance anomalies can indicate DDoS or resource exhaustion attacks
        threat_level = ThreatLevel.LOW
        if current_value > threshold_value * 10:  # 10x threshold
            threat_level = ThreatLevel.HIGH
        elif current_value > threshold_value * 5:  # 5x threshold
            threat_level = ThreatLevel.MEDIUM
        
        return await self.send_security_event(
            event_type="performance_anomaly",
            description=f"Performance anomaly detected: {metric_name} = {current_value} (threshold: {threshold_value})",
            threat_level=threat_level,
            endpoint=endpoint,
            raw_data={
                "metric_name": metric_name,
                "current_value": current_value,
                "threshold_value": threshold_value,
                "metadata": metadata or {}
            },
            indicators=[f"metric:{metric_name}", f"endpoint:{endpoint}"],
            mitre_tactics=["TA0040"]  # Impact
        )
    
    async def send_data_access_event(self,
                                   user_id: str,
                                   table: str,
                                   operation: str,
                                   record_count: int,
                                   authorized: bool = True) -> bool:
        """Send data access event for compliance monitoring."""
        
        threat_level = ThreatLevel.LOW if authorized else ThreatLevel.HIGH
        
        return await self.send_security_event(
            event_type="data_access",
            description=f"Data access: {operation} on {table} by user {user_id} ({'authorized' if authorized else 'UNAUTHORIZED'})",
            threat_level=threat_level,
            user_id=user_id,
            raw_data={
                "table": table,
                "operation": operation,
                "record_count": record_count,
                "authorized": authorized
            },
            indicators=[f"user_id:{user_id}", f"table:{table}"],
            compliance_tags=["GDPR", "SOC2", "HIPAA"] if not authorized else ["audit"]
        )
    
    async def _periodic_flush(self):
        """Periodically flush events to SIEM system."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                
                async with self._buffer_lock:
                    if (self._event_buffer and 
                        time.time() - self._last_flush > self.flush_interval):
                        await self._flush_events()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")
    
    async def _flush_events(self):
        """Flush buffered events to SIEM system."""
        if not self._event_buffer:
            return
        
        events_to_send = self._event_buffer.copy()
        self._event_buffer.clear()
        self._last_flush = time.time()
        
        try:
            success = await self._send_to_siem(events_to_send)
            
            if success:
                self._stats['events_sent'] += len(events_to_send)
                self._stats['batches_sent'] += 1
                self._stats['last_successful_send'] = datetime.now(timezone.utc)
                logger.info(f"✅ Sent {len(events_to_send)} events to SIEM")
            else:
                self._stats['events_failed'] += len(events_to_send)
                # Re-queue events for retry (with limit)
                if len(self._event_buffer) < self.batch_size * 2:
                    self._event_buffer.extend(events_to_send)
                
        except Exception as e:
            logger.error(f"❌ Failed to send events to SIEM: {e}")
            self._stats['events_failed'] += len(events_to_send)
            self._stats['connection_errors'] += 1
    
    async def _send_to_siem(self, events: List[SIEMEvent]) -> bool:
        """Send events to configured SIEM provider."""
        
        if not self.endpoint_url:
            logger.warning("No SIEM endpoint configured")
            return False
        
        payload = self._format_payload(events)
        headers = self._get_headers()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers
                ) as response:
                    
                    if response.status < 400:
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"SIEM API error: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"SIEM connection error: {e}")
            return False
    
    def _format_payload(self, events: List[SIEMEvent]) -> Dict[str, Any]:
        """Format events for specific SIEM provider."""
        
        if self.provider == SIEMProvider.SPLUNK:
            return {
                "events": [
                    {
                        "time": event.timestamp.timestamp(),
                        "source": "velro-authorization",
                        "sourcetype": "velro:security",
                        "event": event.to_dict()
                    }
                    for event in events
                ]
            }
        
        elif self.provider == SIEMProvider.ELASTIC_SECURITY:
            return {
                "events": [
                    {
                        "@timestamp": event.timestamp.isoformat(),
                        "event": {
                            "kind": "alert",
                            "category": ["security"],
                            "type": [event.event_type],
                            "severity": self._threat_to_ecs_severity(event.threat_level)
                        },
                        "velro": event.to_dict()
                    }
                    for event in events
                ]
            }
        
        else:  # Custom webhook or other providers
            return {
                "source": "velro-authorization-system",
                "events": [event.to_dict() for event in events],
                "metadata": {
                    "batch_id": self._generate_event_id(),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "event_count": len(events)
                }
            }
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for SIEM API requests."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Velro-Authorization-System/1.0"
        }
        
        if self.api_key:
            if self.provider == SIEMProvider.SPLUNK:
                headers["Authorization"] = f"Splunk {self.api_key}"
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Add signature for webhook security
        if self.api_secret:
            timestamp = str(int(time.time()))
            headers["X-Timestamp"] = timestamp
            headers["X-Signature"] = self._generate_signature(timestamp)
        
        return headers
    
    def _generate_signature(self, timestamp: str) -> str:
        """Generate HMAC signature for webhook security."""
        message = f"velro-authorization:{timestamp}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        return f"velro-{int(time.time())}-{hash(time.time()) % 100000:05d}"
    
    def _get_compliance_tags(self, event_type: str, threat_level: ThreatLevel) -> List[str]:
        """Get compliance tags based on event type and severity."""
        tags = ["audit"]
        
        if threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            tags.extend(["incident", "security"])
        
        if "data_access" in event_type or "authorization" in event_type:
            tags.extend(["GDPR", "SOC2"])
        
        return tags
    
    def _threat_to_ecs_severity(self, threat_level: ThreatLevel) -> int:
        """Convert threat level to ECS severity score."""
        mapping = {
            ThreatLevel.LOW: 2,
            ThreatLevel.MEDIUM: 5,
            ThreatLevel.HIGH: 7,
            ThreatLevel.CRITICAL: 9
        }
        return mapping.get(threat_level, 5)
    
    async def _log_event_locally(self, event: SIEMEvent):
        """Log event locally as backup."""
        if event.threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            security_logger.critical(
                f"SIEM Event: {event.description}",
                event_type=EventType.SECURITY_VIOLATION,
                source_ip=event.source_ip,
                user_id=event.user_id,
                session_id=event.session_id,
                endpoint=event.endpoint,
                threat_level=event.threat_level.value,
                indicators=event.indicators,
                mitre_tactics=event.mitre_attack_tactics
            )
        else:
            security_logger.warning(
                f"SIEM Event: {event.description}",
                event_type=EventType.SECURITY_VIOLATION,
                **{k: v for k, v in event.to_dict().items() 
                   if k not in ['timestamp', 'raw_data']}
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get SIEM integration statistics."""
        return {
            **self._stats,
            'buffer_size': len(self._event_buffer),
            'provider': self.provider.value,
            'running': self._running,
            'last_flush': datetime.fromtimestamp(self._last_flush).isoformat()
        }


# Global SIEM integration instance
siem_integration = SIEMIntegration()


@asynccontextmanager
async def siem_context():
    """Context manager for SIEM integration lifecycle."""
    await siem_integration.start()
    try:
        yield siem_integration
    finally:
        await siem_integration.stop()


# Convenience functions for common security events
async def report_authorization_failure(user_id: str, resource: str, 
                                     reason: str, source_ip: str,
                                     session_id: Optional[str] = None):
    """Report authorization failure to SIEM."""
    await siem_integration.send_authorization_violation(
        user_id=user_id,
        resource=resource,
        violation_type=f"authorization_failure_{reason}",
        source_ip=source_ip,
        session_id=session_id
    )


async def report_suspicious_activity(activity_type: str, source_ip: str,
                                   user_id: Optional[str] = None,
                                   metadata: Optional[Dict[str, Any]] = None):
    """Report suspicious activity to SIEM."""
    await siem_integration.send_security_event(
        event_type=f"suspicious_{activity_type}",
        description=f"Suspicious activity detected: {activity_type}",
        threat_level=ThreatLevel.HIGH,
        source_ip=source_ip,
        user_id=user_id,
        raw_data=metadata,
        indicators=[f"activity:{activity_type}", f"source_ip:{source_ip}"],
        mitre_tactics=["TA0043"]  # Reconnaissance
    )


async def report_performance_anomaly(metric: str, value: float, 
                                   threshold: float, endpoint: str):
    """Report performance anomaly that might indicate attack."""
    await siem_integration.send_performance_anomaly(
        metric_name=metric,
        current_value=value,
        threshold_value=threshold,
        endpoint=endpoint
    )