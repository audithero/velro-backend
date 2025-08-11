"""
Enterprise Security Monitoring and Audit Logging System
Phase 2 Step 2: Real-time security event detection, comprehensive audit logging,
and incident response automation for the Velro backend.
"""

import json
import time
import asyncio
import hashlib
import ipaddress
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from enum import Enum, IntEnum
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import logging
import threading
import geoip2.database
from pathlib import Path
import re

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Gauge, Summary, CollectorRegistry
import redis.asyncio as redis
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Import existing monitoring infrastructure
try:
    from monitoring.metrics import metrics_collector
    from config import settings
except ImportError:
    # Fallback for testing
    metrics_collector = None
    class FallbackSettings:
        def is_production(self): return True
        security_headers_enabled = True
        csrf_protection_enabled = True
    settings = FallbackSettings()


logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Security event types for categorization."""
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_VIOLATION = "authorization_violation"
    CSRF_TOKEN_FAILURE = "csrf_token_failure"
    JWT_MANIPULATION = "jwt_manipulation"
    INPUT_VALIDATION_FAILURE = "input_validation_failure"
    RATE_LIMIT_VIOLATION = "rate_limit_violation"
    SSRF_ATTEMPT = "ssrf_attempt"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    PATH_TRAVERSAL_ATTEMPT = "path_traversal_attempt"
    COMMAND_INJECTION_ATTEMPT = "command_injection_attempt"
    SUSPICIOUS_USER_AGENT = "suspicious_user_agent"
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    PRIVILEGE_ESCALATION_ATTEMPT = "privilege_escalation_attempt"
    DATA_EXFILTRATION_ATTEMPT = "data_exfiltration_attempt"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"


class SecuritySeverity(IntEnum):
    """Security event severity levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class AlertStatus(Enum):
    """Alert status for incident tracking."""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged" 
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


@dataclass
class SecurityEvent:
    """Structured security event data."""
    event_id: str
    event_type: SecurityEventType
    severity: SecuritySeverity
    timestamp: datetime
    source_ip: str
    user_id: Optional[str]
    session_id: Optional[str]
    endpoint: str
    method: str
    user_agent: str
    request_id: str
    description: str
    metadata: Dict[str, Any]
    geo_location: Optional[Dict[str, str]] = None
    blocked: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['event_type'] = self.event_type.value
        data['severity'] = self.severity.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class SecurityIncident:
    """Security incident data structure."""
    incident_id: str
    title: str
    description: str
    severity: SecuritySeverity
    status: AlertStatus
    created_at: datetime
    updated_at: datetime
    events: List[SecurityEvent]
    source_ips: Set[str]
    affected_users: Set[str]
    auto_blocked: bool = False
    escalated: bool = False
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "events_count": len(self.events),
            "source_ips": list(self.source_ips),
            "affected_users": list(self.affected_users),
            "auto_blocked": self.auto_blocked,
            "escalated": self.escalated,
            "metadata": self.metadata or {}
        }


class SecurityPatternMatcher:
    """Advanced pattern matching for threat detection."""
    
    def __init__(self):
        # SQL Injection patterns
        self.sql_patterns = [
            r'(?i)(union\s+select|select\s+.*\s+from|insert\s+into|update\s+.*\s+set)',
            r'(?i)(delete\s+from|drop\s+table|alter\s+table|create\s+table)',
            r'(?i)(exec\s*\(|execute\s*\(|sp_executesql)',
            r'(?i)(\'\s*or\s+.*\s*=|or\s+1\s*=\s*1)',
            r'(?i)(information_schema|sys\.databases|mysql\.user)',
        ]
        
        # XSS patterns
        self.xss_patterns = [
            r'(?i)<script[^>]*>.*?</script>',
            r'(?i)javascript\s*:',
            r'(?i)on\w+\s*=\s*["\'][^"\']*["\']',
            r'(?i)<iframe[^>]*>',
            r'(?i)data\s*:\s*text/html',
            r'(?i)vbscript\s*:',
        ]
        
        # Path traversal patterns
        self.path_traversal_patterns = [
            r'\.\.[\\/]',
            r'%2e%2e%2f',
            r'%2e%2e%5c',
            r'\.\.%2f',
            r'\.\.%5c',
        ]
        
        # Command injection patterns
        self.command_injection_patterns = [
            r'[;&|`$\(\)]',
            r'(?i)\b(cat|ls|ps|netstat|ifconfig|whoami|id|uname)\b',
            r'(?i)\b(rm|del|format|fdisk)\b',
        ]
        
        # Suspicious user agents
        self.suspicious_user_agents = [
            r'(?i)(sqlmap|nmap|nikto|dirb|gobuster)',
            r'(?i)(burp|scanner|hack|exploit)',
            r'(?i)(curl|wget|python-requests)\/',
        ]
        
        # Compile all patterns
        self.compiled_patterns = {
            'sql': [re.compile(p) for p in self.sql_patterns],
            'xss': [re.compile(p) for p in self.xss_patterns],
            'path_traversal': [re.compile(p) for p in self.path_traversal_patterns],
            'command_injection': [re.compile(p) for p in self.command_injection_patterns],
            'suspicious_ua': [re.compile(p) for p in self.suspicious_user_agents],
        }
    
    def analyze_request(self, request_data: Dict[str, str]) -> List[Tuple[SecurityEventType, str]]:
        """Analyze request for security threats."""
        threats = []
        
        # Analyze URL path
        path = request_data.get('path', '')
        if self._check_patterns('sql', path):
            threats.append((SecurityEventType.SQL_INJECTION_ATTEMPT, f"SQL injection in path: {path[:100]}"))
        if self._check_patterns('xss', path):
            threats.append((SecurityEventType.XSS_ATTEMPT, f"XSS attempt in path: {path[:100]}"))
        if self._check_patterns('path_traversal', path):
            threats.append((SecurityEventType.PATH_TRAVERSAL_ATTEMPT, f"Path traversal in path: {path[:100]}"))
        
        # Analyze query parameters
        query_params = request_data.get('query_params', '')
        if query_params:
            if self._check_patterns('sql', query_params):
                threats.append((SecurityEventType.SQL_INJECTION_ATTEMPT, f"SQL injection in query: {query_params[:100]}"))
            if self._check_patterns('xss', query_params):
                threats.append((SecurityEventType.XSS_ATTEMPT, f"XSS attempt in query: {query_params[:100]}"))
            if self._check_patterns('command_injection', query_params):
                threats.append((SecurityEventType.COMMAND_INJECTION_ATTEMPT, f"Command injection in query: {query_params[:100]}"))
        
        # Analyze user agent
        user_agent = request_data.get('user_agent', '')
        if self._check_patterns('suspicious_ua', user_agent):
            threats.append((SecurityEventType.SUSPICIOUS_USER_AGENT, f"Suspicious user agent: {user_agent[:100]}"))
        
        # Analyze headers for potential threats
        headers = request_data.get('headers', {})
        for header_name, header_value in headers.items():
            if self._check_patterns('xss', header_value):
                threats.append((SecurityEventType.XSS_ATTEMPT, f"XSS in header {header_name}: {header_value[:100]}"))
        
        return threats
    
    def _check_patterns(self, category: str, text: str) -> bool:
        """Check text against pattern category."""
        if not text or category not in self.compiled_patterns:
            return False
        
        for pattern in self.compiled_patterns[category]:
            if pattern.search(text):
                return True
        return False


class GeoIPAnalyzer:
    """Geographic IP analysis for threat intelligence."""
    
    def __init__(self, geoip_db_path: Optional[str] = None):
        self.reader = None
        if geoip_db_path and Path(geoip_db_path).exists():
            try:
                self.reader = geoip2.database.Reader(geoip_db_path)
                logger.info("✅ GeoIP database loaded successfully")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load GeoIP database: {e}")
    
    def analyze_ip(self, ip_address: str) -> Dict[str, str]:
        """Analyze IP address for geographic information."""
        if not self.reader:
            return {"status": "unavailable"}
        
        try:
            ip_obj = ipaddress.ip_address(ip_address)
            if ip_obj.is_private or ip_obj.is_loopback:
                return {"status": "private", "type": "private_ip"}
            
            response = self.reader.city(ip_address)
            return {
                "status": "success",
                "country": response.country.name or "Unknown",
                "country_code": response.country.iso_code or "XX",
                "city": response.city.name or "Unknown",
                "latitude": str(response.location.latitude or 0),
                "longitude": str(response.location.longitude or 0),
                "timezone": response.location.time_zone or "UTC"
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def is_suspicious_country(self, country_code: str) -> bool:
        """Check if country code is from a high-risk region."""
        # This would be configured based on threat intelligence
        high_risk_countries = {'CN', 'RU', 'KP', 'IR'}
        return country_code in high_risk_countries


class SecurityMetricsExtended:
    """Extended security metrics for comprehensive monitoring."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        
        # Security events by type and severity
        self.security_events_total = Counter(
            'velro_security_events_total',
            'Total security events detected',
            ['event_type', 'severity', 'source_country'],
            registry=self.registry
        )
        
        # Threat detection latency
        self.threat_detection_duration = Histogram(
            'velro_threat_detection_duration_seconds',
            'Time to detect security threats',
            ['detection_type'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
            registry=self.registry
        )
        
        # Incident metrics
        self.active_incidents = Gauge(
            'velro_active_incidents',
            'Current number of active security incidents',
            ['severity'],
            registry=self.registry
        )
        
        self.incidents_total = Counter(
            'velro_incidents_total',
            'Total security incidents created',
            ['severity', 'status'],
            registry=self.registry
        )
        
        # Auto-blocking metrics
        self.auto_blocks_total = Counter(
            'velro_auto_blocks_total',
            'Automatic blocks applied',
            ['block_type', 'reason'],
            registry=self.registry
        )
        
        # Pattern matching metrics
        self.pattern_matches_total = Counter(
            'velro_pattern_matches_total',
            'Security pattern matches',
            ['pattern_type', 'action_taken'],
            registry=self.registry
        )
        
        # Audit log metrics
        self.audit_events_total = Counter(
            'velro_audit_events_total',
            'Audit log events',
            ['event_category', 'user_type'],
            registry=self.registry
        )


class BehaviorAnalyzer:
    """User behavior analysis for anomaly detection."""
    
    def __init__(self):
        self.user_profiles: Dict[str, Dict[str, Any]] = {}
        self.ip_profiles: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def analyze_user_behavior(self, user_id: str, request_data: Dict[str, Any]) -> List[str]:
        """Analyze user behavior for anomalies."""
        anomalies = []
        
        with self._lock:
            if user_id not in self.user_profiles:
                self.user_profiles[user_id] = {
                    'typical_ips': set(),
                    'typical_user_agents': set(),
                    'typical_endpoints': set(),
                    'login_times': deque(maxlen=100),
                    'request_rate': deque(maxlen=50),
                    'countries': set()
                }
            
            profile = self.user_profiles[user_id]
            current_time = datetime.now(timezone.utc)
            
            # Analyze IP behavior
            current_ip = request_data.get('source_ip')
            if current_ip and current_ip not in profile['typical_ips']:
                if len(profile['typical_ips']) > 0:  # Not first login
                    anomalies.append(f"New IP address for user: {current_ip}")
                profile['typical_ips'].add(current_ip)
            
            # Analyze user agent
            user_agent = request_data.get('user_agent', '')
            if user_agent and user_agent not in profile['typical_user_agents']:
                if len(profile['typical_user_agents']) > 0:
                    anomalies.append(f"New user agent: {user_agent[:50]}")
                profile['typical_user_agents'].add(user_agent)
            
            # Analyze request rate
            profile['request_rate'].append(current_time)
            if len(profile['request_rate']) >= 10:
                # Check for rapid requests (>10 requests in 1 minute)
                minute_ago = current_time - timedelta(minutes=1)
                recent_requests = sum(1 for t in profile['request_rate'] if t > minute_ago)
                if recent_requests > 10:
                    anomalies.append(f"High request rate: {recent_requests} requests/minute")
            
            # Geographic analysis
            geo_data = request_data.get('geo_location', {})
            country = geo_data.get('country_code')
            if country and country not in profile['countries']:
                if len(profile['countries']) > 0:
                    anomalies.append(f"Access from new country: {country}")
                profile['countries'].add(country)
        
        return anomalies


class IncidentManager:
    """Incident management and escalation system."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.active_incidents: Dict[str, SecurityIncident] = {}
        self.redis_client = redis_client
        self._lock = threading.Lock()
        
        # Escalation thresholds
        self.escalation_thresholds = {
            SecuritySeverity.LOW: 10,      # 10 events
            SecuritySeverity.MEDIUM: 5,    # 5 events
            SecuritySeverity.HIGH: 2,      # 2 events
            SecuritySeverity.CRITICAL: 1   # 1 event
        }
    
    async def create_incident(self, events: List[SecurityEvent]) -> SecurityIncident:
        """Create new security incident from events."""
        if not events:
            raise ValueError("Cannot create incident without events")
        
        # Determine incident severity (highest event severity)
        max_severity = max(event.severity for event in events)
        
        # Generate incident ID
        incident_id = self._generate_incident_id()
        
        # Extract affected resources
        source_ips = {event.source_ip for event in events}
        affected_users = {event.user_id for event in events if event.user_id}
        
        # Create incident
        incident = SecurityIncident(
            incident_id=incident_id,
            title=self._generate_incident_title(events),
            description=self._generate_incident_description(events),
            severity=max_severity,
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            events=events,
            source_ips=source_ips,
            affected_users=affected_users,
            auto_blocked=False,
            escalated=False,
            metadata=self._extract_incident_metadata(events)
        )
        
        with self._lock:
            self.active_incidents[incident_id] = incident
        
        # Store in Redis if available
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"incident:{incident_id}",
                    86400,  # 24 hours
                    json.dumps(incident.to_dict())
                )
            except Exception as e:
                logger.error(f"Failed to store incident in Redis: {e}")
        
        logger.warning(f"🚨 Security incident created: {incident_id} (Severity: {max_severity.name})")
        return incident
    
    def _generate_incident_id(self) -> str:
        """Generate unique incident ID."""
        import secrets
        return f"INC-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
    
    def _generate_incident_title(self, events: List[SecurityEvent]) -> str:
        """Generate incident title from events."""
        event_types = {event.event_type.value for event in events}
        if len(event_types) == 1:
            return f"Security Event: {list(event_types)[0].replace('_', ' ').title()}"
        else:
            return f"Multiple Security Events ({len(event_types)} types)"
    
    def _generate_incident_description(self, events: List[SecurityEvent]) -> str:
        """Generate incident description."""
        event_summary = {}
        for event in events:
            event_type = event.event_type.value
            if event_type not in event_summary:
                event_summary[event_type] = 0
            event_summary[event_type] += 1
        
        description_parts = []
        for event_type, count in event_summary.items():
            description_parts.append(f"{count} {event_type.replace('_', ' ')} event(s)")
        
        return "Detected: " + ", ".join(description_parts)
    
    def _extract_incident_metadata(self, events: List[SecurityEvent]) -> Dict[str, Any]:
        """Extract metadata from events."""
        return {
            "total_events": len(events),
            "time_span": {
                "start": min(event.timestamp for event in events).isoformat(),
                "end": max(event.timestamp for event in events).isoformat()
            },
            "unique_endpoints": len({event.endpoint for event in events}),
            "unique_user_agents": len({event.user_agent for event in events}),
        }


class SecurityAuditLogger:
    """Comprehensive audit logging system."""
    
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file or "/var/log/velro/security_audit.log"
        self.audit_logger = self._setup_audit_logger()
        
        # Audit event categories
        self.categories = {
            'authentication': 'Authentication and authorization events',
            'data_access': 'Data access and modification events', 
            'configuration': 'System configuration changes',
            'security': 'Security-related events',
            'admin': 'Administrative actions',
            'api': 'API usage and access patterns'
        }
    
    def _setup_audit_logger(self) -> logging.Logger:
        """Setup dedicated audit logger."""
        audit_logger = logging.getLogger('velro.security.audit')
        audit_logger.setLevel(logging.INFO)
        
        # Create log directory if it doesn't exist
        log_dir = Path(self.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # File handler for audit logs
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # JSON formatter for structured logging
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}'
        )
        file_handler.setFormatter(formatter)
        audit_logger.addHandler(file_handler)
        
        return audit_logger
    
    async def log_security_event(self, event: SecurityEvent):
        """Log security event to audit trail."""
        audit_data = {
            "category": "security",
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "source_ip": event.source_ip,
            "user_id": event.user_id,
            "endpoint": event.endpoint,
            "method": event.method,
            "description": event.description,
            "blocked": event.blocked,
            "metadata": event.metadata
        }
        
        self.audit_logger.info(json.dumps(audit_data))
    
    async def log_authentication_event(self, user_id: str, event_type: str, 
                                     source_ip: str, success: bool, 
                                     metadata: Dict[str, Any]):
        """Log authentication events."""
        audit_data = {
            "category": "authentication",
            "event_type": event_type,
            "user_id": user_id,
            "source_ip": source_ip,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata
        }
        
        self.audit_logger.info(json.dumps(audit_data))
    
    async def log_data_access(self, user_id: str, resource: str, action: str,
                            source_ip: str, success: bool, metadata: Dict[str, Any]):
        """Log data access events."""
        audit_data = {
            "category": "data_access",
            "user_id": user_id,
            "resource": resource,
            "action": action,
            "source_ip": source_ip,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata
        }
        
        self.audit_logger.info(json.dumps(audit_data))
    
    async def log_admin_action(self, admin_user_id: str, action: str, target: str,
                             source_ip: str, metadata: Dict[str, Any]):
        """Log administrative actions."""
        audit_data = {
            "category": "admin",
            "admin_user_id": admin_user_id,
            "action": action,
            "target": target,
            "source_ip": source_ip,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata
        }
        
        self.audit_logger.info(json.dumps(audit_data))


class SecurityMonitoringSystem:
    """Main security monitoring and audit logging system."""
    
    def __init__(self, redis_url: Optional[str] = None, geoip_db_path: Optional[str] = None):
        self.pattern_matcher = SecurityPatternMatcher()
        self.geoip_analyzer = GeoIPAnalyzer(geoip_db_path)
        self.behavior_analyzer = BehaviorAnalyzer()
        self.incident_manager = IncidentManager()
        self.audit_logger = SecurityAuditLogger()
        
        # Extended metrics
        self.security_metrics = SecurityMetricsExtended()
        
        # Redis connection for caching and session management
        self.redis_client = None
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                self.incident_manager.redis_client = self.redis_client
                logger.info("✅ Redis connection established for security monitoring")
            except Exception as e:
                logger.error(f"❌ Failed to connect to Redis: {e}")
        
        # Blocked IPs and session tracking
        self.blocked_ips: Set[str] = set()
        self.suspicious_ips: Set[str] = set()
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Event queues for processing
        self.event_queue: deque = deque(maxlen=10000)
        self.incident_queue: deque = deque(maxlen=1000)
        
        # Background tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        
        logger.info("🛡️ Security Monitoring System initialized")
    
    async def start_monitoring(self):
        """Start background monitoring tasks."""
        # Start event processing task
        task1 = asyncio.create_task(self._process_events())
        self._monitoring_tasks.append(task1)
        
        # Start incident correlation task
        task2 = asyncio.create_task(self._correlate_incidents())
        self._monitoring_tasks.append(task2)
        
        # Start cleanup task
        task3 = asyncio.create_task(self._cleanup_old_data())
        self._monitoring_tasks.append(task3)
        
        logger.info("🚀 Security monitoring background tasks started")
    
    async def stop_monitoring(self):
        """Stop background monitoring tasks."""
        for task in self._monitoring_tasks:
            task.cancel()
        
        await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        self._monitoring_tasks.clear()
        
        logger.info("🛑 Security monitoring stopped")
    
    async def analyze_request(self, request: Request) -> List[SecurityEvent]:
        """Analyze incoming request for security threats."""
        start_time = time.time()
        events = []
        
        # Extract request data
        request_data = await self._extract_request_data(request)
        
        # Pattern-based threat detection
        threats = self.pattern_matcher.analyze_request(request_data)
        
        # Create security events for detected threats
        for threat_type, description in threats:
            event = SecurityEvent(
                event_id=self._generate_event_id(),
                event_type=threat_type,
                severity=self._determine_severity(threat_type),
                timestamp=datetime.now(timezone.utc),
                source_ip=request_data['source_ip'],
                user_id=request_data.get('user_id'),
                session_id=request_data.get('session_id'),
                endpoint=request_data['endpoint'],
                method=request_data['method'],
                user_agent=request_data['user_agent'],
                request_id=request_data['request_id'],
                description=description,
                metadata=request_data.get('metadata', {}),
                geo_location=self.geoip_analyzer.analyze_ip(request_data['source_ip'])
            )
            events.append(event)
        
        # Behavior analysis
        if request_data.get('user_id'):
            anomalies = self.behavior_analyzer.analyze_user_behavior(
                request_data['user_id'], request_data
            )
            
            for anomaly in anomalies:
                event = SecurityEvent(
                    event_id=self._generate_event_id(),
                    event_type=SecurityEventType.ANOMALOUS_BEHAVIOR,
                    severity=SecuritySeverity.MEDIUM,
                    timestamp=datetime.now(timezone.utc),
                    source_ip=request_data['source_ip'],
                    user_id=request_data['user_id'],
                    session_id=request_data.get('session_id'),
                    endpoint=request_data['endpoint'],
                    method=request_data['method'],
                    user_agent=request_data['user_agent'],
                    request_id=request_data['request_id'],
                    description=f"Behavioral anomaly: {anomaly}",
                    metadata={'anomaly_type': 'behavioral', 'details': anomaly},
                    geo_location=self.geoip_analyzer.analyze_ip(request_data['source_ip'])
                )
                events.append(event)
        
        # Add events to processing queue
        for event in events:
            self.event_queue.append(event)
        
        # Record metrics
        detection_time = time.time() - start_time
        self.security_metrics.threat_detection_duration.labels(
            detection_type="request_analysis"
        ).observe(detection_time)
        
        return events
    
    async def log_authentication_event(self, user_id: str, success: bool, 
                                     source_ip: str, method: str, 
                                     failure_reason: Optional[str] = None):
        """Log authentication events."""
        # Create security event if authentication failed
        if not success:
            event = SecurityEvent(
                event_id=self._generate_event_id(),
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=SecuritySeverity.MEDIUM,
                timestamp=datetime.now(timezone.utc),
                source_ip=source_ip,
                user_id=user_id,
                session_id=None,
                endpoint="/api/v1/auth/login",
                method=method,
                user_agent="",
                request_id=self._generate_event_id(),
                description=f"Authentication failure: {failure_reason or 'Invalid credentials'}",
                metadata={'failure_reason': failure_reason},
                geo_location=self.geoip_analyzer.analyze_ip(source_ip)
            )
            self.event_queue.append(event)
        
        # Log to audit trail
        await self.audit_logger.log_authentication_event(
            user_id=user_id,
            event_type="login_attempt",
            source_ip=source_ip,
            success=success,
            metadata={
                'method': method,
                'failure_reason': failure_reason
            }
        )
    
    async def check_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP address is blocked."""
        return ip_address in self.blocked_ips
    
    async def block_ip(self, ip_address: str, reason: str, duration_hours: int = 24):
        """Block IP address for security reasons."""
        self.blocked_ips.add(ip_address)
        
        # Store in Redis with expiration
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"blocked_ip:{ip_address}",
                    duration_hours * 3600,
                    json.dumps({
                        "reason": reason,
                        "blocked_at": datetime.now(timezone.utc).isoformat(),
                        "duration_hours": duration_hours
                    })
                )
            except Exception as e:
                logger.error(f"Failed to store blocked IP in Redis: {e}")
        
        # Record metrics
        self.security_metrics.auto_blocks_total.labels(
            block_type="ip_block",
            reason=reason
        ).inc()
        
        logger.warning(f"🚫 IP {ip_address} blocked for {duration_hours}h: {reason}")
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        import secrets
        return f"EVT-{int(time.time())}-{secrets.token_hex(6).upper()}"
    
    def _determine_severity(self, event_type: SecurityEventType) -> SecuritySeverity:
        """Determine event severity based on type."""
        high_severity_events = {
            SecurityEventType.SQL_INJECTION_ATTEMPT,
            SecurityEventType.COMMAND_INJECTION_ATTEMPT,
            SecurityEventType.PRIVILEGE_ESCALATION_ATTEMPT,
            SecurityEventType.DATA_EXFILTRATION_ATTEMPT,
        }
        
        critical_severity_events = {
            SecurityEventType.BRUTE_FORCE_ATTEMPT,
        }
        
        if event_type in critical_severity_events:
            return SecuritySeverity.CRITICAL
        elif event_type in high_severity_events:
            return SecuritySeverity.HIGH
        else:
            return SecuritySeverity.MEDIUM
    
    async def _extract_request_data(self, request: Request) -> Dict[str, Any]:
        """Extract relevant data from request for analysis."""
        return {
            'source_ip': self._get_client_ip(request),
            'endpoint': str(request.url.path),
            'method': request.method,
            'user_agent': request.headers.get('user-agent', ''),
            'headers': dict(request.headers),
            'query_params': str(request.url.query),
            'path': str(request.url.path),
            'request_id': request.headers.get('x-request-id', self._generate_event_id()),
            'user_id': getattr(request.state, 'user_id', None),
            'session_id': getattr(request.state, 'session_id', None),
            'metadata': {
                'host': request.headers.get('host', ''),
                'referer': request.headers.get('referer', ''),
                'content_type': request.headers.get('content-type', ''),
                'content_length': request.headers.get('content-length', '0'),
            }
        }
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request with proxy support."""
        # Check forwarded headers
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else 'unknown'
    
    async def _process_events(self):
        """Background task to process security events."""
        while True:
            try:
                if self.event_queue:
                    event = self.event_queue.popleft()
                    
                    # Log to audit trail
                    await self.audit_logger.log_security_event(event)
                    
                    # Record metrics
                    country_code = "XX"
                    if event.geo_location and event.geo_location.get('country_code'):
                        country_code = event.geo_location['country_code']
                    
                    self.security_metrics.security_events_total.labels(
                        event_type=event.event_type.value,
                        severity=event.severity.name.lower(),
                        source_country=country_code
                    ).inc()
                    
                    # Check for auto-blocking conditions
                    if event.severity >= SecuritySeverity.HIGH:
                        await self._evaluate_auto_blocking(event)
                else:
                    await asyncio.sleep(1)
            
            except Exception as e:
                logger.error(f"Error processing security event: {e}")
                await asyncio.sleep(5)
    
    async def _correlate_incidents(self):
        """Background task to correlate events into incidents."""
        event_buffer = []
        
        while True:
            try:
                # Collect events for correlation
                while self.event_queue and len(event_buffer) < 50:
                    event_buffer.append(self.event_queue.popleft())
                
                if not event_buffer:
                    await asyncio.sleep(10)
                    continue
                
                # Group events by potential incident
                incident_groups = self._group_events_for_incidents(event_buffer)
                
                # Create incidents
                for events in incident_groups:
                    if len(events) >= 1:  # Minimum events for incident
                        incident = await self.incident_manager.create_incident(events)
                        self.incident_queue.append(incident)
                        
                        # Update metrics
                        self.security_metrics.incidents_total.labels(
                            severity=incident.severity.name.lower(),
                            status=incident.status.value
                        ).inc()
                        
                        self.security_metrics.active_incidents.labels(
                            severity=incident.severity.name.lower()
                        ).inc()
                
                # Clear processed events
                event_buffer.clear()
                
                await asyncio.sleep(30)  # Process every 30 seconds
            
            except Exception as e:
                logger.error(f"Error correlating incidents: {e}")
                await asyncio.sleep(60)
    
    def _group_events_for_incidents(self, events: List[SecurityEvent]) -> List[List[SecurityEvent]]:
        """Group events into potential incidents."""
        # Group by source IP and time window
        groups = defaultdict(list)
        
        for event in events:
            # Group key: source IP + time window (5 minute blocks)
            time_window = int(event.timestamp.timestamp() // 300)  # 5-minute blocks
            group_key = f"{event.source_ip}:{time_window}"
            groups[group_key].append(event)
        
        # Return groups with multiple events or high-severity single events
        incident_groups = []
        for group_events in groups.values():
            if len(group_events) > 1 or any(e.severity >= SecuritySeverity.HIGH for e in group_events):
                incident_groups.append(group_events)
        
        return incident_groups
    
    async def _evaluate_auto_blocking(self, event: SecurityEvent):
        """Evaluate if automatic blocking should be applied."""
        # Count recent events from same IP
        recent_events = [
            e for e in list(self.event_queue)
            if e.source_ip == event.source_ip 
            and (datetime.now(timezone.utc) - e.timestamp).total_seconds() < 3600
        ]
        
        # Auto-block conditions
        should_block = False
        block_reason = ""
        
        if len(recent_events) >= 5:
            should_block = True
            block_reason = f"Multiple security violations ({len(recent_events)} in 1 hour)"
        elif event.event_type in [SecurityEventType.SQL_INJECTION_ATTEMPT, 
                                SecurityEventType.COMMAND_INJECTION_ATTEMPT]:
            should_block = True
            block_reason = f"Critical attack attempt: {event.event_type.value}"
        
        if should_block:
            await self.block_ip(event.source_ip, block_reason, duration_hours=24)
            event.blocked = True
    
    async def _cleanup_old_data(self):
        """Background task to cleanup old data."""
        while True:
            try:
                # Clean old incidents (keep 30 days)
                cutoff_time = datetime.now(timezone.utc) - timedelta(days=30)
                
                # This would typically clean database records
                # For now, just log cleanup activity
                logger.info("🧹 Security monitoring data cleanup completed")
                
                # Sleep for 24 hours
                await asyncio.sleep(86400)
            
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour


# Global security monitoring instance
security_monitor = SecurityMonitoringSystem()