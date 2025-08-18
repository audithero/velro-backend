"""
Team Audit Service
Comprehensive team activity logging and audit trails for enterprise compliance.
Implements security monitoring, activity tracking, and audit reporting.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID, uuid4
import json
import hashlib
from enum import Enum

from database import get_database
from models.team import TeamRole, TeamResponse
from models.authorization import SecurityLevel, ValidationContext, AuthorizationMethod
from services.team_service import TeamService
from utils.enhanced_uuid_utils import EnhancedUUIDUtils
from utils.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Audit event types for team activities."""
    # Team Management Events
    TEAM_CREATED = "team_created"
    TEAM_UPDATED = "team_updated"
    TEAM_DELETED = "team_deleted"
    
    # Membership Events
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    MEMBER_ROLE_CHANGED = "member_role_changed"
    MEMBER_JOINED = "member_joined"
    MEMBER_LEFT = "member_left"
    
    # Invitation Events
    INVITATION_SENT = "invitation_sent"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    INVITATION_EXPIRED = "invitation_expired"
    INVITATION_CANCELLED = "invitation_cancelled"
    
    # Resource Events
    RESOURCE_SHARED = "resource_shared"
    RESOURCE_UNSHARED = "resource_unshared"
    RESOURCE_ACCESSED = "resource_accessed"
    RESOURCE_MODIFIED = "resource_modified"
    RESOURCE_DELETED = "resource_deleted"
    
    # Collaboration Events
    GENERATION_CREATED = "generation_created"
    GENERATION_IMPROVED = "generation_improved"
    GENERATION_SHARED = "generation_shared"
    GENERATION_FORKED = "generation_forked"
    GENERATION_REMIXED = "generation_remixed"
    
    # Permission Events
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    ACCESS_DENIED = "access_denied"
    SECURITY_VIOLATION = "security_violation"
    
    # Administrative Events
    ADMIN_ACTION = "admin_action"
    SETTINGS_CHANGED = "settings_changed"
    BULK_OPERATION = "bulk_operation"


class AuditSeverity(str, Enum):
    """Audit event severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TeamAuditService:
    """
    Enterprise team audit service with comprehensive logging and compliance features.
    Implements security monitoring, activity tracking, and detailed audit reporting.
    """
    
    def __init__(self):
        self.cache_manager = CacheManager()
        self.team_service = TeamService()
        
        # Audit metrics and monitoring
        self.metrics = {
            "audit_events_logged": 0,
            "security_violations_detected": 0,
            "compliance_checks_performed": 0,
            "audit_queries_executed": 0,
            "retention_operations": 0
        }
        
        # Audit configuration
        self.audit_config = {
            "retention_days": 2555,  # 7 years for enterprise compliance
            "real_time_monitoring": True,
            "security_alert_threshold": 5,  # Security violations per hour
            "batch_size": 100,
            "compression_enabled": True,
            "encryption_enabled": True
        }
        
        # Security monitoring
        self.security_patterns = {
            "suspicious_access_attempts": {},
            "privilege_escalation_attempts": {},
            "bulk_operation_patterns": {},
            "anomalous_activity_patterns": {}
        }
    
    async def log_team_audit_event(
        self,
        event_type: AuditEventType,
        team_id: UUID,
        user_id: UUID,
        severity: AuditSeverity = AuditSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        resource_id: Optional[UUID] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        auth_token: str = None
    ) -> Dict[str, Any]:
        """
        Log a comprehensive team audit event with full context.
        Implements enterprise-grade audit logging with security monitoring.
        """
        
        event_id = str(uuid4())
        timestamp = datetime.utcnow()
        
        logger.info(f"📋 [AUDIT] Logging {event_type.value} event for team {team_id}, user {user_id}")        
        try:
            # Build comprehensive audit event
            audit_event = {
                "id": event_id,
                "event_type": event_type.value,
                "severity": severity.value,
                "timestamp": timestamp.isoformat(),
                "team_id": str(team_id),
                "user_id": str(user_id),
                "resource_id": str(resource_id) if resource_id else None,
                "details": details or {},
                "context": {
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "session_id": session_id,
                    "user_id_hash": EnhancedUUIDUtils.hash_uuid_for_logging(str(user_id)),
                    "team_id_hash": EnhancedUUIDUtils.hash_uuid_for_logging(str(team_id)),
                    "resource_id_hash": EnhancedUUIDUtils.hash_uuid_for_logging(str(resource_id)) if resource_id else None
                },
                "metadata": {
                    "logged_at": timestamp.isoformat(),
                    "audit_version": "2.0",
                    "compliance_flags": self._generate_compliance_flags(event_type, severity),
                    "retention_date": (timestamp + timedelta(days=self.audit_config["retention_days"])).isoformat()
                }
            }
            
            # Security analysis
            security_analysis = await self._analyze_security_implications(
                event_type, team_id, user_id, details, client_ip, timestamp
            )
            audit_event["security_analysis"] = security_analysis
            
            # Compliance tags
            compliance_tags = self._generate_compliance_tags(event_type, severity, details)
            audit_event["compliance_tags"] = compliance_tags
            
            # Store audit event
            storage_result = await self._store_audit_event(audit_event, auth_token, str(user_id))
            
            # Real-time monitoring and alerts
            if self.audit_config["real_time_monitoring"]:
                await self._process_real_time_monitoring(audit_event)
            
            # Update metrics
            self.metrics["audit_events_logged"] += 1
            if security_analysis.get("security_risk_score", 0) > 7:
                self.metrics["security_violations_detected"] += 1
            
            logger.info(f"✅ [AUDIT] Event {event_id} logged successfully with {security_analysis.get('security_risk_score', 0)} risk score")            
            return {
                "audit_event_id": event_id,
                "logged_at": timestamp.isoformat(),
                "event_type": event_type.value,
                "severity": severity.value,
                "storage_result": storage_result,
                "security_analysis": security_analysis,
                "compliance_tags": compliance_tags
            }
            
        except Exception as e:
            logger.error(f"❌ [AUDIT] Failed to log audit event: {e}")            
            # Critical: Audit logging failure is a security concern
            await self._handle_audit_logging_failure(event_type, team_id, user_id, str(e))
            
            return {
                "audit_event_id": event_id,
                "error": str(e),
                "event_type": event_type.value,
                "logged_at": timestamp.isoformat(),
                "fallback_logged": True
            }
    
    async def get_team_audit_trail(
        self,
        team_id: UUID,
        user_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        severity_filter: Optional[List[AuditSeverity]] = None,
        limit: int = 100,
        auth_token: str = None
    ) -> Dict[str, Any]:
        """
        Retrieve comprehensive audit trail for a team.
        Supports filtering, pagination, and compliance reporting.
        """
        
        logger.info(f"🔍 [AUDIT-TRAIL] Retrieving audit trail for team {team_id}")        
        try:
            # Validate user has access to view audit trail
            team_access = await self.team_service.validate_team_access(
                team_id, user_id, TeamRole.ADMIN, auth_token  # Requires admin access
            )
            
            if not team_access.granted:
                # Log access attempt
                await self.log_team_audit_event(
                    event_type=AuditEventType.ACCESS_DENIED,
                    team_id=team_id,
                    user_id=user_id,
                    severity=AuditSeverity.HIGH,
                    details={"attempted_resource": "audit_trail", "reason": "insufficient_permissions"},
                    auth_token=auth_token
                )
                raise PermissionError("Insufficient permissions to view audit trail")            
            # Build query filters
            filters = {"team_id": str(team_id)}
            
            if start_date:
                filters["timestamp__gte"] = start_date.isoformat()
            if end_date:
                filters["timestamp__lte"] = end_date.isoformat()
            
            if event_types:
                filters["event_type__in"] = [et.value for et in event_types]
            
            if severity_filter:
                filters["severity__in"] = [sf.value for sf in severity_filter]
            
            # Execute audit query
            audit_events = await self._query_audit_events(filters, limit, auth_token, str(user_id))
            
            # Generate audit trail summary
            trail_summary = self._generate_audit_trail_summary(audit_events)
            
            # Compliance analysis
            compliance_analysis = self._analyze_compliance_status(audit_events)
            
            # Security insights
            security_insights = self._generate_security_insights(audit_events)
            
            self.metrics["audit_queries_executed"] += 1
            
            audit_trail_result = {
                "team_id": str(team_id),
                "requested_by": str(user_id),
                "query_timestamp": datetime.utcnow().isoformat(),
                "filters_applied": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "event_types": [et.value for et in event_types] if event_types else None,
                    "severity_filter": [sf.value for sf in severity_filter] if severity_filter else None,
                    "limit": limit
                },
                "events_found": len(audit_events),
                "audit_events": audit_events,
                "trail_summary": trail_summary,
                "compliance_analysis": compliance_analysis,
                "security_insights": security_insights
            }
            
            logger.info(f"✅ [AUDIT-TRAIL] Retrieved {len(audit_events)} audit events for team {team_id}")            
            return audit_trail_result
            
        except Exception as e:
            logger.error(f"❌ [AUDIT-TRAIL] Failed to retrieve audit trail: {e}")
            return {
                "team_id": str(team_id),
                "error": str(e),
                "query_timestamp": datetime.utcnow().isoformat()
            }
    
    async def generate_compliance_report(
        self,
        team_id: UUID,
        user_id: UUID,
        report_type: str = "comprehensive",
        time_period: int = 30,  # days
        auth_token: str = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive compliance report for team activities.
        Supports various compliance standards and audit requirements.
        """
        
        logger.info(f"📊 [COMPLIANCE] Generating {report_type} compliance report for team {team_id}")        
        try:
            # Validate administrative access
            team_access = await self.team_service.validate_team_access(
                team_id, user_id, TeamRole.OWNER, auth_token  # Requires owner access for compliance reports
            )
            
            if not team_access.granted:
                raise PermissionError("Insufficient permissions to generate compliance reports")            
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=time_period)
            
            # Get comprehensive audit data
            audit_data = await self.get_team_audit_trail(
                team_id=team_id,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                limit=10000,  # Large limit for compliance reports
                auth_token=auth_token
            )
            
            # Compliance analysis by category
            compliance_categories = {
                "data_access": self._analyze_data_access_compliance(audit_data["audit_events"]),
                "user_management": self._analyze_user_management_compliance(audit_data["audit_events"]),
                "security_events": self._analyze_security_compliance(audit_data["audit_events"]),
                "resource_sharing": self._analyze_resource_sharing_compliance(audit_data["audit_events"]),
                "administrative_actions": self._analyze_admin_compliance(audit_data["audit_events"])
            }
            
            # Risk assessment
            risk_assessment = self._generate_risk_assessment(audit_data["audit_events"])
            
            # Recommendations
            compliance_recommendations = self._generate_compliance_recommendations(
                compliance_categories, risk_assessment
            )
            
            # Generate report metadata
            report_metadata = {
                "report_id": str(uuid4()),
                "generated_at": datetime.utcnow().isoformat(),
                "generated_by": str(user_id),
                "team_id": str(team_id),
                "report_type": report_type,
                "time_period_days": time_period,
                "events_analyzed": len(audit_data["audit_events"]),
                "compliance_version": "2.0"
            }
            
            compliance_report = {
                "metadata": report_metadata,
                "executive_summary": {
                    "overall_compliance_score": self._calculate_compliance_score(compliance_categories),
                    "critical_issues": self._extract_critical_issues(compliance_categories),
                    "improvement_areas": self._identify_improvement_areas(compliance_categories)
                },
                "compliance_categories": compliance_categories,
                "risk_assessment": risk_assessment,
                "recommendations": compliance_recommendations,
                "audit_statistics": audit_data["trail_summary"],
                "security_insights": audit_data["security_insights"]
            }
            
            # Store compliance report
            await self._store_compliance_report(compliance_report, auth_token, str(user_id))
            
            self.metrics["compliance_checks_performed"] += 1
            
            logger.info(f"✅ [COMPLIANCE] Generated compliance report with score {compliance_report['executive_summary']['overall_compliance_score']:.2f}")            
            return compliance_report
            
        except Exception as e:
            logger.error(f"❌ [COMPLIANCE] Failed to generate compliance report: {e}")
            return {
                "team_id": str(team_id),
                "error": str(e),
                "report_type": report_type,
                "generated_at": datetime.utcnow().isoformat()
            }
    
    # PRIVATE HELPER METHODS FOR AUDIT PROCESSING
    
    async def _analyze_security_implications(
        self,
        event_type: AuditEventType,
        team_id: UUID,
        user_id: UUID,
        details: Optional[Dict[str, Any]],
        client_ip: Optional[str],
        timestamp: datetime
    ) -> Dict[str, Any]:
        """Analyze security implications of audit event."""
        
        security_analysis = {
            "security_risk_score": 0,
            "threat_indicators": [],
            "behavioral_anomalies": [],
            "compliance_flags": []
        }
        
        # Base risk scoring by event type
        risk_scores = {
            AuditEventType.SECURITY_VIOLATION: 10,
            AuditEventType.ACCESS_DENIED: 7,
            AuditEventType.MEMBER_ROLE_CHANGED: 6,
            AuditEventType.PERMISSION_GRANTED: 5,
            AuditEventType.RESOURCE_SHARED: 4,
            AuditEventType.MEMBER_ADDED: 3
        }
        
        base_risk = risk_scores.get(event_type, 1)
        security_analysis["security_risk_score"] = base_risk
        
        # Detect suspicious patterns
        if await self._detect_suspicious_activity_pattern(team_id, user_id, event_type, timestamp):
            security_analysis["threat_indicators"].append("suspicious_activity_pattern")
            security_analysis["security_risk_score"] += 3
        
        # Check for privilege escalation attempts
        if await self._detect_privilege_escalation(event_type, details):
            security_analysis["threat_indicators"].append("privilege_escalation_attempt")
            security_analysis["security_risk_score"] += 5
        
        # Analyze behavioral anomalies
        anomalies = await self._analyze_behavioral_anomalies(team_id, user_id, event_type, client_ip)
        security_analysis["behavioral_anomalies"] = anomalies
        security_analysis["security_risk_score"] += len(anomalies)
        
        return security_analysis
    
    def _generate_compliance_flags(self, event_type: AuditEventType, severity: AuditSeverity) -> List[str]:
        """Generate compliance flags based on event characteristics."""
        
        flags = []
        
        # High-severity events require compliance attention
        if severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL]:
            flags.append("high_severity_review_required")
        
        # Security-related events
        if event_type in [AuditEventType.SECURITY_VIOLATION, AuditEventType.ACCESS_DENIED]:
            flags.extend(["security_review_required", "incident_response_needed"])
        
        # Administrative actions
        if event_type in [AuditEventType.ADMIN_ACTION, AuditEventType.MEMBER_ROLE_CHANGED]:
            flags.append("administrative_oversight_required")
        
        # Resource access events
        if event_type in [AuditEventType.RESOURCE_ACCESSED, AuditEventType.RESOURCE_SHARED]:
            flags.append("data_access_compliance_check")
        
        return flags
    
    async def _store_audit_event(self, audit_event: Dict[str, Any], auth_token: str, user_id: str) -> Dict[str, Any]:
        """Store audit event in secure audit log."""
        
        try:
            db = await get_database()
            
            # Encrypt sensitive data if configured
            if self.audit_config["encryption_enabled"]:
                audit_event = self._encrypt_sensitive_audit_data(audit_event)
            
            # Store in audit_events table
            stored_event = db.execute_query(
                table="audit_events",
                operation="insert",
                data=audit_event,
                single=True,
                auth_token=auth_token,
                user_id=user_id
            )
            
            return {
                "stored": True,
                "storage_id": stored_event.get("id"),
                "compression_applied": self.audit_config["compression_enabled"],
                "encryption_applied": self.audit_config["encryption_enabled"]
            }
            
        except Exception as e:
            logger.error(f"❌ [AUDIT-STORE] Failed to store audit event: {e}")            
            # Fallback storage mechanism
            return await self._fallback_audit_storage(audit_event)
    
    async def _fallback_audit_storage(self, audit_event: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback mechanism for audit event storage when primary storage fails."""
        
        try:
            # Write to local file as emergency backup
            fallback_file = f"/tmp/audit_fallback_{datetime.utcnow().strftime('%Y%m%d')}.log"
            
            with open(fallback_file, "a") as f:
                f.write(json.dumps(audit_event) + "\n")
            
            logger.warning(f"⚠️ [AUDIT-FALLBACK] Event stored in fallback file: {fallback_file}")
            
            return {
                "stored": True,
                "fallback_storage": True,
                "fallback_file": fallback_file,
                "requires_recovery": True
            }
            
        except Exception as e:
            logger.critical(f"🚨 [AUDIT-CRITICAL] Complete audit storage failure: {e}")
            return {
                "stored": False,
                "critical_failure": True,
                "error": str(e)
            }


# Singleton instance for global use
team_audit_service = TeamAuditService()