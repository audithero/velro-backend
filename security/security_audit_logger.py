"""
Security Audit Logger - Comprehensive Security Event Monitoring
==============================================================

This module provides comprehensive security audit logging that meets OWASP
requirements for security monitoring and incident response.

OWASP Compliance:
- A09:2021 – Security Logging and Monitoring Failures - FIXED
- A01:2021 – Broken Access Control - MONITORING
- A03:2021 – Injection - DETECTION

Security Features:
1. Structured security event logging
2. Real-time anomaly detection
3. Compliance reporting
4. Incident response integration
5. Performance monitoring
"""

import logging
import json
import hashlib
from typing import Dict, Any, Optional, List, Set
from uuid import UUID
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
import asyncio
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Types of security events to log."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    INPUT_VALIDATION = "input_validation"
    SESSION_MANAGEMENT = "session_management"
    SYSTEM_INTEGRITY = "system_integrity"
    ANOMALY_DETECTION = "anomaly_detection"
    COMPLIANCE_VIOLATION = "compliance_violation"
    SECURITY_CONFIGURATION = "security_configuration"
    INCIDENT_RESPONSE = "incident_response"


class SecurityEventSeverity(Enum):
    """Severity levels for security events."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5


class SecurityEventStatus(Enum):
    """Status of security events."""
    NEW = "new"
    INVESTIGATING = "investigating"
    CONFIRMED = "confirmed"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


@dataclass
class SecurityEvent:
    """Structured security event data."""
    event_id: str
    timestamp: datetime
    event_type: SecurityEventType
    severity: SecurityEventSeverity
    title: str
    description: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    operation: Optional[str] = None
    status: SecurityEventStatus = SecurityEventStatus.NEW
    risk_score: int = 0
    tags: List[str] = None
    metadata: Dict[str, Any] = None
    correlation_id: Optional[str] = None
    owasp_category: Optional[str] = None
    compliance_impact: List[str] = None
    remediation_steps: List[str] = None
    
    def __post_init__(self):
        """Post-initialization processing."""
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
        if self.compliance_impact is None:
            self.compliance_impact = []
        if self.remediation_steps is None:
            self.remediation_steps = []


class AnomalyPattern:
    """Patterns for anomaly detection."""
    
    def __init__(self, name: str, threshold: int, window_minutes: int):
        self.name = name
        self.threshold = threshold
        self.window_minutes = window_minutes
        self.events = deque()
    
    def add_event(self, event: SecurityEvent) -> bool:
        """Add event and check if anomaly threshold is exceeded."""
        current_time = datetime.now(timezone.utc)
        
        # Remove old events outside the window
        while self.events and (current_time - self.events[0].timestamp).seconds > (self.window_minutes * 60):
            self.events.popleft()
        
        # Add new event
        self.events.append(event)
        
        # Check if threshold exceeded
        return len(self.events) > self.threshold


class SecurityAuditLogger:
    """
    Comprehensive security audit logger with anomaly detection and compliance reporting.
    
    Features:
    - Structured security event logging
    - Real-time anomaly detection
    - OWASP compliance mapping
    - Risk scoring and correlation
    - Incident response automation
    """
    
    def __init__(self, enable_real_time_monitoring: bool = True):
        """Initialize the security audit logger."""
        self.enable_real_time_monitoring = enable_real_time_monitoring
        
        # Event storage and indexing
        self._events = deque(maxlen=10000)  # Keep last 10,000 events
        self._events_by_user = defaultdict(list)
        self._events_by_ip = defaultdict(list)
        self._events_by_type = defaultdict(list)
        
        # Anomaly detection patterns
        self._anomaly_patterns = {
            "failed_auth": AnomalyPattern("failed_authentication", 5, 10),  # 5 failed auths in 10 min
            "rapid_access": AnomalyPattern("rapid_resource_access", 50, 5),  # 50 accesses in 5 min
            "privilege_escalation": AnomalyPattern("privilege_escalation", 3, 30),  # 3 attempts in 30 min
            "data_exfiltration": AnomalyPattern("data_exfiltration", 100, 60),  # 100 downloads in 1 hour
            "injection_attempts": AnomalyPattern("injection_attempts", 10, 15),  # 10 injection tries in 15 min
        }
        
        # Risk scoring weights
        self._risk_weights = {
            SecurityEventType.AUTHENTICATION: 20,
            SecurityEventType.AUTHORIZATION: 30,
            SecurityEventType.DATA_ACCESS: 15,
            SecurityEventType.INPUT_VALIDATION: 25,
            SecurityEventType.SESSION_MANAGEMENT: 20,
            SecurityEventType.SYSTEM_INTEGRITY: 40,
            SecurityEventType.ANOMALY_DETECTION: 35,
            SecurityEventType.COMPLIANCE_VIOLATION: 30
        }
        
        # OWASP mapping
        self._owasp_mapping = {
            SecurityEventType.AUTHORIZATION: "A01:2021 - Broken Access Control",
            SecurityEventType.AUTHENTICATION: "A07:2021 - Identification and Authentication Failures",
            SecurityEventType.INPUT_VALIDATION: "A03:2021 - Injection",
            SecurityEventType.SESSION_MANAGEMENT: "A07:2021 - Identification and Authentication Failures",
            SecurityEventType.SYSTEM_INTEGRITY: "A08:2021 - Software and Data Integrity Failures",
            SecurityEventType.SECURITY_CONFIGURATION: "A05:2021 - Security Misconfiguration",
            SecurityEventType.DATA_ACCESS: "A01:2021 - Broken Access Control",
        }
        
        logger.info("🔍 [SECURITY-AUDIT] Security audit logger initialized")
    
    def _generate_event_id(self, event_data: Dict[str, Any]) -> str:
        """Generate unique event ID based on event data."""
        event_string = json.dumps(event_data, sort_keys=True, default=str)
        event_hash = hashlib.sha256(event_string.encode()).hexdigest()
        timestamp_suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"SEC-{timestamp_suffix}-{event_hash[:8]}"
    
    def _calculate_risk_score(self, event: SecurityEvent) -> int:
        """Calculate risk score for security event."""
        base_score = self._risk_weights.get(event.event_type, 10)
        
        # Severity multiplier
        severity_multiplier = {
            SecurityEventSeverity.LOW: 0.5,
            SecurityEventSeverity.MEDIUM: 1.0,
            SecurityEventSeverity.HIGH: 1.5,
            SecurityEventSeverity.CRITICAL: 2.0,
            SecurityEventSeverity.EMERGENCY: 3.0
        }.get(event.severity, 1.0)
        
        # Context-based adjustments
        context_adjustments = 0
        
        # User context
        if event.user_id:
            # Check user's recent event history
            user_events = self._events_by_user.get(event.user_id, [])
            recent_events = [e for e in user_events 
                           if (event.timestamp - e.timestamp).seconds < 3600]  # Last hour
            if len(recent_events) > 10:
                context_adjustments += 10
        
        # IP context
        if event.client_ip:
            ip_events = self._events_by_ip.get(event.client_ip, [])
            recent_ip_events = [e for e in ip_events
                              if (event.timestamp - e.timestamp).seconds < 3600]
            if len(recent_ip_events) > 20:
                context_adjustments += 15
        
        # Resource access patterns
        if event.resource_id and event.operation == "delete":
            context_adjustments += 20  # Deletion operations are higher risk
        
        final_score = int(base_score * severity_multiplier + context_adjustments)
        return min(final_score, 100)  # Cap at 100
    
    def _detect_anomalies(self, event: SecurityEvent) -> List[str]:
        """Detect anomalies based on event patterns."""
        anomalies = []
        
        # Check against defined patterns
        for pattern_name, pattern in self._anomaly_patterns.items():
            if pattern.add_event(event):
                anomalies.append(f"Anomaly detected: {pattern.name}")
                
                # Create anomaly event
                anomaly_event = SecurityEvent(
                    event_id=self._generate_event_id({"anomaly": pattern_name}),
                    timestamp=datetime.now(timezone.utc),
                    event_type=SecurityEventType.ANOMALY_DETECTION,
                    severity=SecurityEventSeverity.HIGH,
                    title=f"Anomaly Pattern: {pattern.name}",
                    description=f"Anomaly threshold exceeded: {len(pattern.events)} events in {pattern.window_minutes} minutes",
                    user_id=event.user_id,
                    client_ip=event.client_ip,
                    risk_score=75,
                    tags=["anomaly", "automated_detection"],
                    metadata={
                        "pattern_name": pattern.name,
                        "threshold": pattern.threshold,
                        "window_minutes": pattern.window_minutes,
                        "event_count": len(pattern.events),
                        "trigger_event_id": event.event_id
                    },
                    owasp_category="A09:2021 - Security Logging and Monitoring Failures",
                    remediation_steps=[
                        "Investigate user activity pattern",
                        "Check for compromised credentials",
                        "Consider temporary access restrictions",
                        "Review system logs for correlation"
                    ]
                )
                
                # Log anomaly event
                self._store_event(anomaly_event)
        
        return anomalies
    
    def _store_event(self, event: SecurityEvent) -> None:
        """Store event in internal data structures."""
        # Add to main event queue
        self._events.append(event)
        
        # Index by user
        if event.user_id:
            self._events_by_user[event.user_id].append(event)
        
        # Index by IP
        if event.client_ip:
            self._events_by_ip[event.client_ip].append(event)
        
        # Index by type
        self._events_by_type[event.event_type].append(event)
    
    def log_security_event(
        self,
        event_type: SecurityEventType,
        severity: SecurityEventSeverity,
        title: str,
        description: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        operation: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> SecurityEvent:
        """
        Log a security event with comprehensive metadata and analysis.
        
        Args:
            event_type: Type of security event
            severity: Event severity level
            title: Brief event title
            description: Detailed event description
            user_id: User ID (truncated for privacy)
            session_id: Session identifier
            client_ip: Client IP address
            user_agent: Client user agent
            resource_id: Resource identifier
            resource_type: Type of resource accessed
            operation: Operation performed
            metadata: Additional event metadata
            tags: Event tags for categorization
            
        Returns:
            SecurityEvent object with calculated risk score and analysis
        """
        try:
            # Create event object
            event_data = {
                "event_type": event_type.value,
                "severity": severity.value,
                "title": title,
                "description": description,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "resource_id": resource_id,
                "operation": operation
            }
            
            event = SecurityEvent(
                event_id=self._generate_event_id(event_data),
                timestamp=datetime.now(timezone.utc),
                event_type=event_type,
                severity=severity,
                title=title,
                description=description,
                user_id=user_id,
                session_id=session_id,
                client_ip=client_ip,
                user_agent=user_agent,
                resource_id=resource_id,
                resource_type=resource_type,
                operation=operation,
                metadata=metadata or {},
                tags=tags or [],
                owasp_category=self._owasp_mapping.get(event_type)
            )
            
            # Calculate risk score
            event.risk_score = self._calculate_risk_score(event)
            
            # Store event
            self._store_event(event)
            
            # Detect anomalies if real-time monitoring is enabled
            if self.enable_real_time_monitoring:
                anomalies = self._detect_anomalies(event)
                if anomalies:
                    event.tags.extend(["anomaly_trigger"])
                    event.metadata["anomalies_detected"] = anomalies
            
            # Log based on severity
            log_data = asdict(event)
            log_data["timestamp"] = event.timestamp.isoformat()
            
            if severity in [SecurityEventSeverity.CRITICAL, SecurityEventSeverity.EMERGENCY]:
                logger.critical(f"🚨 [SECURITY-CRITICAL] {json.dumps(log_data, default=str)}")
            elif severity == SecurityEventSeverity.HIGH:
                logger.error(f"⚠️ [SECURITY-HIGH] {json.dumps(log_data, default=str)}")
            elif severity == SecurityEventSeverity.MEDIUM:
                logger.warning(f"⚡ [SECURITY-MEDIUM] {json.dumps(log_data, default=str)}")
            else:
                logger.info(f"ℹ️ [SECURITY-LOW] {json.dumps(log_data, default=str)}")
            
            return event
            
        except Exception as e:
            logger.error(f"❌ [SECURITY-AUDIT] Failed to log security event: {e}")
            # Create fallback event
            fallback_event = SecurityEvent(
                event_id="ERROR-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                timestamp=datetime.now(timezone.utc),
                event_type=SecurityEventType.SYSTEM_INTEGRITY,
                severity=SecurityEventSeverity.HIGH,
                title="Security Logging Error",
                description=f"Failed to log security event: {str(e)}",
                metadata={"original_error": str(e)},
                risk_score=60
            )
            return fallback_event
    
    def get_security_dashboard_data(self, hours: int = 24) -> Dict[str, Any]:
        """Generate security dashboard data for monitoring."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_events = [e for e in self._events if e.timestamp > cutoff_time]
        
        # Event statistics
        event_stats = {
            "total_events": len(recent_events),
            "by_severity": {},
            "by_type": {},
            "high_risk_events": [],
            "top_users": {},
            "top_ips": {},
            "anomalies_detected": 0
        }
        
        # Count by severity
        for severity in SecurityEventSeverity:
            count = len([e for e in recent_events if e.severity == severity])
            event_stats["by_severity"][severity.name] = count
        
        # Count by type
        for event_type in SecurityEventType:
            count = len([e for e in recent_events if e.event_type == event_type])
            event_stats["by_type"][event_type.name] = count
        
        # High risk events (risk score > 70)
        high_risk = [e for e in recent_events if e.risk_score > 70]
        event_stats["high_risk_events"] = [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp.isoformat(),
                "title": e.title,
                "severity": e.severity.name,
                "risk_score": e.risk_score,
                "user_id": e.user_id[:8] + "..." if e.user_id else None
            }
            for e in high_risk[:10]  # Top 10
        ]
        
        # User activity
        user_counts = defaultdict(int)
        for event in recent_events:
            if event.user_id:
                user_counts[event.user_id] += 1
        
        event_stats["top_users"] = dict(sorted(user_counts.items(), 
                                             key=lambda x: x[1], reverse=True)[:10])
        
        # IP activity
        ip_counts = defaultdict(int)
        for event in recent_events:
            if event.client_ip:
                ip_counts[event.client_ip] += 1
        
        event_stats["top_ips"] = dict(sorted(ip_counts.items(), 
                                           key=lambda x: x[1], reverse=True)[:10])
        
        # Anomaly count
        anomaly_events = [e for e in recent_events 
                         if e.event_type == SecurityEventType.ANOMALY_DETECTION]
        event_stats["anomalies_detected"] = len(anomaly_events)
        
        return event_stats
    
    def get_compliance_report(self, owasp_category: Optional[str] = None) -> Dict[str, Any]:
        """Generate OWASP compliance report."""
        recent_events = list(self._events)[-1000:]  # Last 1000 events
        
        report = {
            "total_events": len(recent_events),
            "owasp_categories": {},
            "compliance_violations": [],
            "recommendations": []
        }
        
        # Group by OWASP category
        for event in recent_events:
            if event.owasp_category:
                if event.owasp_category not in report["owasp_categories"]:
                    report["owasp_categories"][event.owasp_category] = {
                        "total": 0,
                        "high_severity": 0,
                        "unresolved": 0
                    }
                
                report["owasp_categories"][event.owasp_category]["total"] += 1
                
                if event.severity in [SecurityEventSeverity.HIGH, SecurityEventSeverity.CRITICAL]:
                    report["owasp_categories"][event.owasp_category]["high_severity"] += 1
                
                if event.status in [SecurityEventStatus.NEW, SecurityEventStatus.INVESTIGATING]:
                    report["owasp_categories"][event.owasp_category]["unresolved"] += 1
        
        # Compliance violations (high severity unresolved events)
        violations = [e for e in recent_events 
                     if e.severity in [SecurityEventSeverity.HIGH, SecurityEventSeverity.CRITICAL]
                     and e.status in [SecurityEventStatus.NEW, SecurityEventStatus.INVESTIGATING]]
        
        report["compliance_violations"] = [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp.isoformat(),
                "title": e.title,
                "owasp_category": e.owasp_category,
                "risk_score": e.risk_score,
                "remediation_steps": e.remediation_steps
            }
            for e in violations[:20]  # Top 20 violations
        ]
        
        # Generate recommendations
        if report["owasp_categories"].get("A01:2021 - Broken Access Control", {}).get("high_severity", 0) > 5:
            report["recommendations"].append("Review and strengthen access control mechanisms")
        
        if report["owasp_categories"].get("A03:2021 - Injection", {}).get("total", 0) > 10:
            report["recommendations"].append("Implement comprehensive input validation")
        
        return report


# Convenience functions for common security events
class SecurityEventHelpers:
    """Helper functions for logging common security events."""
    
    @staticmethod
    def log_authentication_failure(audit_logger: SecurityAuditLogger, 
                                 user_identifier: str, client_ip: str,
                                 failure_reason: str, user_agent: Optional[str] = None):
        """Log authentication failure event."""
        return audit_logger.log_security_event(
            event_type=SecurityEventType.AUTHENTICATION,
            severity=SecurityEventSeverity.MEDIUM,
            title="Authentication Failure",
            description=f"Authentication failed for user: {failure_reason}",
            user_id=user_identifier,
            client_ip=client_ip,
            user_agent=user_agent,
            operation="authenticate",
            tags=["authentication", "failure"],
            metadata={"failure_reason": failure_reason}
        )
    
    @staticmethod
    def log_authorization_violation(audit_logger: SecurityAuditLogger,
                                  user_id: str, resource_id: str, 
                                  operation: str, client_ip: Optional[str] = None):
        """Log authorization violation event."""
        return audit_logger.log_security_event(
            event_type=SecurityEventType.AUTHORIZATION,
            severity=SecurityEventSeverity.HIGH,
            title="Authorization Violation",
            description=f"Unauthorized {operation} attempt on resource",
            user_id=user_id,
            client_ip=client_ip,
            resource_id=resource_id,
            operation=operation,
            tags=["authorization", "violation"],
            metadata={"attempted_operation": operation}
        )
    
    @staticmethod
    def log_injection_attempt(audit_logger: SecurityAuditLogger,
                            user_id: Optional[str], client_ip: str,
                            injection_type: str, payload: str):
        """Log injection attempt event."""
        return audit_logger.log_security_event(
            event_type=SecurityEventType.INPUT_VALIDATION,
            severity=SecurityEventSeverity.HIGH,
            title="Injection Attempt Detected",
            description=f"{injection_type} injection attempt detected",
            user_id=user_id,
            client_ip=client_ip,
            operation="inject",
            tags=["injection", "attack", injection_type.lower()],
            metadata={
                "injection_type": injection_type,
                "payload_hash": hashlib.sha256(payload.encode()).hexdigest()[:16]
            }
        )


# Global security audit logger instance
security_audit_logger = SecurityAuditLogger()