"""
Enhanced Security Audit System
Integrates with existing authentication, authorization, and security systems
to provide comprehensive audit logging and compliance monitoring.
"""

import json
import asyncio
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

# Import existing systems
try:
    from security.security_monitoring_system import security_monitor, SecurityEvent, SecurityEventType
    from middleware.security_monitoring import SecurityMonitoringIntegration
    from config import settings
    from database import get_async_session
except ImportError:
    # Fallback for testing
    security_monitor = None
    
    class FallbackSettings:
        def is_production(self): return True
    settings = FallbackSettings()
    
    async def get_async_session():
        pass


logger = logging.getLogger(__name__)


class AuditCategory(Enum):
    """Audit event categories for compliance tracking."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION_CHANGE = "configuration_change"
    SECURITY_EVENT = "security_event"
    ADMINISTRATIVE_ACTION = "administrative_action"
    API_ACCESS = "api_access"
    USER_MANAGEMENT = "user_management"
    SESSION_MANAGEMENT = "session_management"
    PAYMENT_PROCESSING = "payment_processing"
    SYSTEM_ACCESS = "system_access"


class AuditResult(Enum):
    """Audit event results."""
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    WARNING = "warning"


@dataclass
class AuditEvent:
    """Enhanced audit event structure for compliance."""
    event_id: str
    category: AuditCategory
    action: str
    result: AuditResult
    timestamp: datetime
    user_id: Optional[str]
    session_id: Optional[str]
    source_ip: str
    user_agent: str
    resource: str
    resource_id: Optional[str]
    details: Dict[str, Any]
    risk_score: int  # 0-100
    compliance_tags: List[str]
    retention_period_days: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "category": self.category.value,
            "action": self.action,
            "result": self.result.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "details": self.details,
            "risk_score": self.risk_score,
            "compliance_tags": self.compliance_tags,
            "retention_period_days": self.retention_period_days
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class ComplianceStandard(Enum):
    """Supported compliance standards."""
    GDPR = "gdpr"
    SOC2 = "soc2"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO27001 = "iso27001"
    OWASP = "owasp"


class AuditStorage:
    """Audit event storage with multiple backends."""
    
    def __init__(self, storage_type: str = "file", connection_string: Optional[str] = None):
        self.storage_type = storage_type
        self.connection_string = connection_string
        self.file_path = "/var/log/velro/audit.jsonl"
        self.db_path = "/var/log/velro/audit.db"
        
        # Ensure log directory exists
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize storage backend
        if storage_type == "sqlite":
            self._init_sqlite()
    
    def _init_sqlite(self):
        """Initialize SQLite database for audit storage."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    session_id TEXT,
                    source_ip TEXT NOT NULL,
                    user_agent TEXT,
                    resource TEXT NOT NULL,
                    resource_id TEXT,
                    details TEXT,
                    risk_score INTEGER,
                    compliance_tags TEXT,
                    retention_period_days INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON audit_events(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON audit_events(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source_ip ON audit_events(source_ip)")
            
            conn.commit()
            conn.close()
            logger.info("✅ SQLite audit storage initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize SQLite audit storage: {e}")
    
    async def store_audit_event(self, event: AuditEvent):
        """Store audit event in the configured backend."""
        try:
            if self.storage_type == "file":
                await self._store_to_file(event)
            elif self.storage_type == "sqlite":
                await self._store_to_sqlite(event)
            else:
                logger.error(f"Unsupported storage type: {self.storage_type}")
        except Exception as e:
            logger.error(f"❌ Failed to store audit event: {e}")
    
    async def _store_to_file(self, event: AuditEvent):
        """Store audit event to file (JSONL format)."""
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
        except Exception as e:
            logger.error(f"❌ Failed to write audit event to file: {e}")
    
    async def _store_to_sqlite(self, event: AuditEvent):
        """Store audit event to SQLite database."""
        try:
            # Run in thread pool to avoid blocking
            def _insert_event():
                conn = sqlite3.connect(self.db_path)
                conn.execute("""
                    INSERT INTO audit_events (
                        event_id, category, action, result, timestamp,
                        user_id, session_id, source_ip, user_agent,
                        resource, resource_id, details, risk_score,
                        compliance_tags, retention_period_days
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id, event.category.value, event.action,
                    event.result.value, event.timestamp.isoformat(),
                    event.user_id, event.session_id, event.source_ip,
                    event.user_agent, event.resource, event.resource_id,
                    json.dumps(event.details), event.risk_score,
                    json.dumps(event.compliance_tags), event.retention_period_days
                ))
                conn.commit()
                conn.close()
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _insert_event)
            
        except Exception as e:
            logger.error(f"❌ Failed to store audit event to SQLite: {e}")
    
    async def query_audit_events(self, filters: Dict[str, Any], limit: int = 1000) -> List[Dict[str, Any]]:
        """Query audit events with filters."""
        if self.storage_type == "sqlite":
            return await self._query_sqlite(filters, limit)
        else:
            # For file storage, this would need to parse the JSONL file
            return []
    
    async def _query_sqlite(self, filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """Query SQLite database for audit events."""
        try:
            def _execute_query():
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                
                # Build WHERE clause
                where_conditions = []
                params = []
                
                if filters.get("category"):
                    where_conditions.append("category = ?")
                    params.append(filters["category"])
                
                if filters.get("user_id"):
                    where_conditions.append("user_id = ?")
                    params.append(filters["user_id"])
                
                if filters.get("source_ip"):
                    where_conditions.append("source_ip = ?")
                    params.append(filters["source_ip"])
                
                if filters.get("start_time"):
                    where_conditions.append("timestamp >= ?")
                    params.append(filters["start_time"])
                
                if filters.get("end_time"):
                    where_conditions.append("timestamp <= ?")
                    params.append(filters["end_time"])
                
                where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                query = f"""
                    SELECT * FROM audit_events 
                    {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params.append(limit)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                conn.close()
                
                return [dict(row) for row in rows]
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _execute_query)
            
        except Exception as e:
            logger.error(f"❌ Failed to query audit events: {e}")
            return []


class ComplianceReporter:
    """Generate compliance reports for various standards."""
    
    def __init__(self, audit_storage: AuditStorage):
        self.audit_storage = audit_storage
    
    async def generate_report(self, standard: ComplianceStandard, 
                            start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate compliance report for specified standard."""
        filters = {
            "start_time": start_date.isoformat(),
            "end_time": end_date.isoformat()
        }
        
        # Get relevant audit events
        events = await self.audit_storage.query_audit_events(filters, limit=10000)
        
        if standard == ComplianceStandard.GDPR:
            return await self._generate_gdpr_report(events, start_date, end_date)
        elif standard == ComplianceStandard.SOC2:
            return await self._generate_soc2_report(events, start_date, end_date)
        else:
            return await self._generate_generic_report(events, start_date, end_date, standard)
    
    async def _generate_gdpr_report(self, events: List[Dict], 
                                  start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate GDPR compliance report."""
        gdpr_events = [e for e in events if "gdpr" in (json.loads(e.get("compliance_tags", "[]")))]
        
        data_access_events = [e for e in gdpr_events if e.get("category") == "data_access"]
        data_modification_events = [e for e in gdpr_events if e.get("category") == "data_modification"]
        user_management_events = [e for e in gdpr_events if e.get("category") == "user_management"]
        
        return {
            "report_type": "GDPR Compliance Report",
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_gdpr_events": len(gdpr_events),
                "data_access_events": len(data_access_events),
                "data_modification_events": len(data_modification_events),
                "user_management_events": len(user_management_events)
            },
            "data_processing_activities": self._analyze_data_processing(gdpr_events),
            "right_to_access_requests": self._count_access_requests(events),
            "right_to_erasure_requests": self._count_erasure_requests(events),
            "data_breach_incidents": self._count_breach_incidents(events),
            "compliance_score": self._calculate_gdpr_compliance_score(events)
        }
    
    async def _generate_soc2_report(self, events: List[Dict], 
                                  start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate SOC 2 compliance report."""
        return {
            "report_type": "SOC 2 Type II Compliance Report",
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trust_services_criteria": {
                "security": self._analyze_security_controls(events),
                "availability": self._analyze_availability_controls(events),
                "processing_integrity": self._analyze_processing_integrity(events),
                "confidentiality": self._analyze_confidentiality_controls(events),
                "privacy": self._analyze_privacy_controls(events)
            },
            "total_events": len(events),
            "compliance_score": self._calculate_soc2_compliance_score(events)
        }
    
    async def _generate_generic_report(self, events: List[Dict], 
                                     start_date: datetime, end_date: datetime,
                                     standard: ComplianceStandard) -> Dict[str, Any]:
        """Generate generic compliance report."""
        return {
            "report_type": f"{standard.value.upper()} Compliance Report",
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_events": len(events),
            "events_by_category": self._group_events_by_category(events),
            "events_by_result": self._group_events_by_result(events),
            "high_risk_events": len([e for e in events if e.get("risk_score", 0) >= 70]),
            "compliance_tags": self._analyze_compliance_tags(events)
        }
    
    def _analyze_data_processing(self, events: List[Dict]) -> Dict[str, int]:
        """Analyze data processing activities for GDPR."""
        activities = {}
        for event in events:
            action = event.get("action", "unknown")
            if action not in activities:
                activities[action] = 0
            activities[action] += 1
        return activities
    
    def _count_access_requests(self, events: List[Dict]) -> int:
        """Count data access requests."""
        return len([e for e in events if e.get("action") == "data_access_request"])
    
    def _count_erasure_requests(self, events: List[Dict]) -> int:
        """Count data erasure requests."""
        return len([e for e in events if e.get("action") == "data_erasure_request"])
    
    def _count_breach_incidents(self, events: List[Dict]) -> int:
        """Count data breach incidents."""
        return len([e for e in events if e.get("action") == "data_breach_incident"])
    
    def _calculate_gdpr_compliance_score(self, events: List[Dict]) -> float:
        """Calculate GDPR compliance score."""
        if not events:
            return 100.0
        
        total_events = len(events)
        failed_events = len([e for e in events if e.get("result") == "failure"])
        
        return max(0.0, 100.0 - (failed_events / total_events * 100))
    
    def _analyze_security_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze security controls for SOC 2."""
        security_events = [e for e in events if e.get("category") in ["authentication", "authorization", "security_event"]]
        return {
            "total_security_events": len(security_events),
            "failed_authentications": len([e for e in security_events if e.get("action") == "login" and e.get("result") == "failure"]),
            "authorization_violations": len([e for e in security_events if e.get("category") == "authorization" and e.get("result") == "failure"])
        }
    
    def _analyze_availability_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze availability controls for SOC 2."""
        return {"system_availability": "99.9%"}  # Placeholder
    
    def _analyze_processing_integrity(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze processing integrity for SOC 2."""
        return {"data_processing_accuracy": "99.8%"}  # Placeholder
    
    def _analyze_confidentiality_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze confidentiality controls for SOC 2."""
        return {"data_access_violations": len([e for e in events if e.get("category") == "data_access" and e.get("result") == "blocked"])}
    
    def _analyze_privacy_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze privacy controls for SOC 2."""
        return {"privacy_violations": 0}  # Placeholder
    
    def _calculate_soc2_compliance_score(self, events: List[Dict]) -> float:
        """Calculate SOC 2 compliance score."""
        return 95.0  # Placeholder
    
    def _group_events_by_category(self, events: List[Dict]) -> Dict[str, int]:
        """Group events by category."""
        categories = {}
        for event in events:
            category = event.get("category", "unknown")
            categories[category] = categories.get(category, 0) + 1
        return categories
    
    def _group_events_by_result(self, events: List[Dict]) -> Dict[str, int]:
        """Group events by result."""
        results = {}
        for event in events:
            result = event.get("result", "unknown")
            results[result] = results.get(result, 0) + 1
        return results
    
    def _analyze_compliance_tags(self, events: List[Dict]) -> Dict[str, int]:
        """Analyze compliance tags."""
        tags = {}
        for event in events:
            event_tags = json.loads(event.get("compliance_tags", "[]"))
            for tag in event_tags:
                tags[tag] = tags.get(tag, 0) + 1
        return tags


class EnhancedAuditSystem:
    """Enhanced audit system with compliance and security integration."""
    
    def __init__(self, storage_type: str = "sqlite", redis_url: Optional[str] = None):
        self.audit_storage = AuditStorage(storage_type)
        self.compliance_reporter = ComplianceReporter(self.audit_storage)
        
        # Redis for caching and real-time tracking
        self.redis_client = None
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                logger.info("✅ Redis connection established for audit system")
            except Exception as e:
                logger.error(f"❌ Failed to connect to Redis: {e}")
        
        # Risk scoring rules
        self.risk_scoring_rules = {
            AuditCategory.AUTHENTICATION: {
                "login_failure": 30,
                "multiple_failures": 70,
                "suspicious_location": 50
            },
            AuditCategory.AUTHORIZATION: {
                "access_denied": 40,
                "privilege_escalation": 90
            },
            AuditCategory.DATA_ACCESS: {
                "sensitive_data_access": 60,
                "bulk_data_export": 80
            },
            AuditCategory.SECURITY_EVENT: {
                "sql_injection": 95,
                "xss_attempt": 85,
                "brute_force": 90
            }
        }
        
        logger.info("🔍 Enhanced Audit System initialized")
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        import secrets
        return f"AUDIT-{int(datetime.now().timestamp())}-{secrets.token_hex(6).upper()}"
    
    def _calculate_risk_score(self, category: AuditCategory, action: str, 
                            details: Dict[str, Any]) -> int:
        """Calculate risk score for audit event."""
        base_score = 10
        
        # Apply category-specific scoring
        if category in self.risk_scoring_rules:
            category_rules = self.risk_scoring_rules[category]
            if action in category_rules:
                base_score = category_rules[action]
        
        # Apply contextual scoring
        if details.get("failure_count", 0) > 3:
            base_score = min(base_score + 20, 100)
        
        if details.get("suspicious_ip", False):
            base_score = min(base_score + 15, 100)
        
        if details.get("off_hours_access", False):
            base_score = min(base_score + 10, 100)
        
        return min(base_score, 100)
    
    def _determine_compliance_tags(self, category: AuditCategory, action: str) -> List[str]:
        """Determine compliance tags for audit event."""
        tags = []
        
        # GDPR tags
        if category in [AuditCategory.DATA_ACCESS, AuditCategory.DATA_MODIFICATION, AuditCategory.USER_MANAGEMENT]:
            tags.append("gdpr")
        
        # SOC 2 tags
        if category in [AuditCategory.AUTHENTICATION, AuditCategory.AUTHORIZATION, AuditCategory.SECURITY_EVENT]:
            tags.append("soc2")
        
        # PCI DSS tags
        if category == AuditCategory.PAYMENT_PROCESSING:
            tags.append("pci_dss")
        
        # ISO 27001 tags
        if category in [AuditCategory.SECURITY_EVENT, AuditCategory.CONFIGURATION_CHANGE]:
            tags.append("iso27001")
        
        return tags
    
    def _determine_retention_period(self, category: AuditCategory, risk_score: int) -> int:
        """Determine retention period based on category and risk."""
        base_retention = {
            AuditCategory.AUTHENTICATION: 365,
            AuditCategory.AUTHORIZATION: 365,
            AuditCategory.DATA_ACCESS: 1095,  # 3 years
            AuditCategory.DATA_MODIFICATION: 2555,  # 7 years
            AuditCategory.SECURITY_EVENT: 2555,  # 7 years
            AuditCategory.PAYMENT_PROCESSING: 2555,  # 7 years (PCI requirement)
        }
        
        retention = base_retention.get(category, 365)
        
        # Extend retention for high-risk events
        if risk_score >= 80:
            retention = max(retention, 2555)  # 7 years minimum
        
        return retention
    
    async def log_authentication_event(self, user_id: Optional[str], action: str, 
                                     result: AuditResult, source_ip: str, 
                                     user_agent: str, details: Dict[str, Any],
                                     session_id: Optional[str] = None):
        """Log authentication-related audit event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            category=AuditCategory.AUTHENTICATION,
            action=action,
            result=result,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            resource="authentication_system",
            resource_id=None,
            details=details,
            risk_score=self._calculate_risk_score(AuditCategory.AUTHENTICATION, action, details),
            compliance_tags=self._determine_compliance_tags(AuditCategory.AUTHENTICATION, action),
            retention_period_days=self._determine_retention_period(AuditCategory.AUTHENTICATION, 0)
        )
        
        await self.audit_storage.store_audit_event(event)
        
        # Create security monitoring event if high risk
        if event.risk_score >= 70 and security_monitor:
            await SecurityMonitoringIntegration.create_security_alert(
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=2 if event.risk_score < 90 else 3,
                description=f"High-risk authentication event: {action}",
                source_ip=source_ip,
                user_id=user_id,
                metadata=details
            )
    
    async def log_data_access_event(self, user_id: str, action: str, result: AuditResult,
                                  resource: str, resource_id: Optional[str],
                                  source_ip: str, user_agent: str,
                                  details: Dict[str, Any], session_id: Optional[str] = None):
        """Log data access audit event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            category=AuditCategory.DATA_ACCESS,
            action=action,
            result=result,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            resource=resource,
            resource_id=resource_id,
            details=details,
            risk_score=self._calculate_risk_score(AuditCategory.DATA_ACCESS, action, details),
            compliance_tags=self._determine_compliance_tags(AuditCategory.DATA_ACCESS, action),
            retention_period_days=self._determine_retention_period(AuditCategory.DATA_ACCESS, 0)
        )
        
        await self.audit_storage.store_audit_event(event)
        
        # Cache recent data access for analytics
        if self.redis_client:
            try:
                key = f"data_access:{user_id}:{datetime.now().strftime('%Y-%m-%d-%H')}"
                await self.redis_client.incr(key)
                await self.redis_client.expire(key, 86400)  # 24 hours
            except Exception as e:
                logger.error(f"❌ Failed to cache data access event: {e}")
    
    async def log_administrative_action(self, admin_user_id: str, action: str,
                                      target: str, target_id: Optional[str],
                                      result: AuditResult, source_ip: str,
                                      user_agent: str, details: Dict[str, Any],
                                      session_id: Optional[str] = None):
        """Log administrative action audit event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            category=AuditCategory.ADMINISTRATIVE_ACTION,
            action=action,
            result=result,
            timestamp=datetime.now(timezone.utc),
            user_id=admin_user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            resource=target,
            resource_id=target_id,
            details=details,
            risk_score=self._calculate_risk_score(AuditCategory.ADMINISTRATIVE_ACTION, action, details),
            compliance_tags=self._determine_compliance_tags(AuditCategory.ADMINISTRATIVE_ACTION, action),
            retention_period_days=self._determine_retention_period(AuditCategory.ADMINISTRATIVE_ACTION, 0)
        )
        
        await self.audit_storage.store_audit_event(event)
    
    async def log_security_event(self, security_event: SecurityEvent):
        """Log security monitoring event to audit trail."""
        details = {
            "security_event_id": security_event.event_id,
            "security_event_type": security_event.event_type.value,
            "security_severity": security_event.severity.value,
            "endpoint": security_event.endpoint,
            "method": security_event.method,
            "blocked": security_event.blocked,
            "geo_location": security_event.geo_location,
            "metadata": security_event.metadata
        }
        
        event = AuditEvent(
            event_id=self._generate_event_id(),
            category=AuditCategory.SECURITY_EVENT,
            action=security_event.event_type.value,
            result=AuditResult.BLOCKED if security_event.blocked else AuditResult.WARNING,
            timestamp=security_event.timestamp,
            user_id=security_event.user_id,
            session_id=security_event.session_id,
            source_ip=security_event.source_ip,
            user_agent=security_event.user_agent,
            resource=security_event.endpoint,
            resource_id=None,
            details=details,
            risk_score=min(security_event.severity.value * 25, 100),
            compliance_tags=self._determine_compliance_tags(AuditCategory.SECURITY_EVENT, security_event.event_type.value),
            retention_period_days=self._determine_retention_period(AuditCategory.SECURITY_EVENT, security_event.severity.value * 25)
        )
        
        await self.audit_storage.store_audit_event(event)
    
    async def query_audit_events(self, filters: Dict[str, Any], limit: int = 1000) -> List[Dict[str, Any]]:
        """Query audit events with filters."""
        return await self.audit_storage.query_audit_events(filters, limit)
    
    async def generate_compliance_report(self, standard: ComplianceStandard,
                                       start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate compliance report."""
        return await self.compliance_reporter.generate_report(standard, start_date, end_date)
    
    async def get_user_audit_summary(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get audit summary for specific user."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        end_date = datetime.now(timezone.utc)
        
        filters = {
            "user_id": user_id,
            "start_time": start_date.isoformat(),
            "end_time": end_date.isoformat()
        }
        
        events = await self.audit_storage.query_audit_events(filters, limit=5000)
        
        return {
            "user_id": user_id,
            "period_days": days,
            "total_events": len(events),
            "events_by_category": self.compliance_reporter._group_events_by_category(events),
            "events_by_result": self.compliance_reporter._group_events_by_result(events),
            "high_risk_events": len([e for e in events if e.get("risk_score", 0) >= 70]),
            "last_login": max([e.get("timestamp") for e in events if e.get("action") == "login"] or ["N/A"]),
            "unique_source_ips": len(set([e.get("source_ip") for e in events])),
            "data_access_count": len([e for e in events if e.get("category") == "data_access"])
        }


# Global enhanced audit system instance
enhanced_audit_system = EnhancedAuditSystem()