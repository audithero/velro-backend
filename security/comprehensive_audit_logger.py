"""
Comprehensive Audit Logging System
Implements security event logging per PRD Section 5.4.10
Tracks all authorization decisions, authentication events, and security violations
"""

import asyncio
import logging
import json
import hashlib
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import uuid
import gzip
import base64

try:
    from elasticsearch import AsyncElasticsearch
    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    ELASTICSEARCH_AVAILABLE = False

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from database import get_database
from config import settings

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    SECURITY_VIOLATION = "security_violation"
    ADMIN_ACTION = "admin_action"
    SYSTEM_EVENT = "system_event"
    USER_ACTION = "user_action"
    API_ACCESS = "api_access"
    FILE_ACCESS = "file_access"
    CONFIGURATION_CHANGE = "configuration_change"
    ERROR_EVENT = "error_event"


class AuditSeverity(Enum):
    """Severity levels for audit events"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditOutcome(Enum):
    """Outcomes of audited operations"""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"
    PARTIAL = "partial"


@dataclass
class AuditEvent:
    """Comprehensive audit event structure"""
    # Core identification
    event_id: str
    timestamp: str
    event_type: AuditEventType
    severity: AuditSeverity
    outcome: AuditOutcome
    
    # Actor information
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Resource information
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_owner: Optional[str] = None
    
    # Action details
    action: Optional[str] = None
    method: Optional[str] = None
    endpoint: Optional[str] = None
    
    # Context and metadata
    description: str = ""
    details: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    
    # Security context
    risk_score: int = 0
    requires_investigation: bool = False
    
    # Technical details
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    duration_ms: Optional[float] = None
    response_status: Optional[int] = None
    
    # Compliance tracking
    compliance_tags: Optional[List[str]] = None
    retention_days: int = 2555  # 7 years default for compliance
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
        
        if self.details is None:
            self.details = {}
        
        if self.tags is None:
            self.tags = []
        
        if self.compliance_tags is None:
            self.compliance_tags = []
        
        # Auto-tag based on event characteristics
        self._auto_tag_event()
    
    def _auto_tag_event(self):
        """Automatically tag events based on their characteristics"""
        # Add severity tags
        self.tags.append(f"severity:{self.severity.value}")
        
        # Add outcome tags
        self.tags.append(f"outcome:{self.outcome.value}")
        
        # Add compliance tags based on event type
        if self.event_type in [AuditEventType.AUTHENTICATION, AuditEventType.AUTHORIZATION]:
            self.compliance_tags.extend(["SOX", "PCI-DSS", "GDPR"])
        
        if self.event_type == AuditEventType.DATA_ACCESS and self.resource_type == "user_data":
            self.compliance_tags.extend(["GDPR", "HIPAA"])
        
        if self.event_type == AuditEventType.ADMIN_ACTION:
            self.compliance_tags.extend(["SOX", "AUDIT_TRAIL"])
        
        # Add investigation flags for high-risk events
        if (self.severity == AuditSeverity.CRITICAL or 
            self.outcome == AuditOutcome.DENIED or
            self.risk_score >= 80):
            self.requires_investigation = True
            self.tags.append("investigation_required")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        
        # Convert enums to strings
        data["event_type"] = self.event_type.value
        data["severity"] = self.severity.value
        data["outcome"] = self.outcome.value
        
        return data
    
    def calculate_risk_score(self, context: Optional[Dict[str, Any]] = None) -> int:
        """Calculate risk score based on event characteristics"""
        score = 0
        
        # Base score by event type
        type_scores = {
            AuditEventType.SECURITY_VIOLATION: 50,
            AuditEventType.AUTHORIZATION: 30,
            AuditEventType.AUTHENTICATION: 25,
            AuditEventType.ADMIN_ACTION: 40,
            AuditEventType.DATA_MODIFICATION: 35,
            AuditEventType.DATA_ACCESS: 15,
            AuditEventType.API_ACCESS: 10
        }
        
        score += type_scores.get(self.event_type, 5)
        
        # Severity multiplier
        severity_multipliers = {
            AuditSeverity.CRITICAL: 2.0,
            AuditSeverity.HIGH: 1.5,
            AuditSeverity.MEDIUM: 1.0,
            AuditSeverity.LOW: 0.5
        }
        
        score *= severity_multipliers.get(self.severity, 1.0)
        
        # Outcome adjustment
        if self.outcome == AuditOutcome.FAILURE:
            score += 20
        elif self.outcome == AuditOutcome.DENIED:
            score += 25
        elif self.outcome == AuditOutcome.ERROR:
            score += 15
        
        # Context-based adjustments
        if context:
            # Multiple failed attempts
            if context.get("failed_attempts", 0) > 3:
                score += 30
            
            # Off-hours access
            current_hour = datetime.utcnow().hour
            if current_hour < 6 or current_hour > 22:
                score += 10
            
            # Unusual location (simplified check)
            if context.get("unusual_location", False):
                score += 20
        
        self.risk_score = min(100, int(score))
        return self.risk_score


class AuditStorage:
    """Storage backend for audit events"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.elasticsearch_client: Optional[AsyncElasticsearch] = None
        self.local_buffer: List[AuditEvent] = []
        self.max_buffer_size = 1000
        
        # Initialize storage backends
        asyncio.create_task(self._initialize_storage())
    
    async def _initialize_storage(self):
        """Initialize storage backends"""
        # Initialize Redis for real-time querying
        if REDIS_AVAILABLE:
            try:
                redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379')
                self.redis_client = redis.from_url(redis_url)
                await self.redis_client.ping()
                logger.info("Audit logging: Redis storage initialized")
            except Exception as e:
                logger.warning(f"Audit logging: Redis initialization failed: {e}")
        
        # Initialize Elasticsearch for long-term storage and analytics
        if ELASTICSEARCH_AVAILABLE:
            try:
                es_url = getattr(settings, 'elasticsearch_url', 'http://localhost:9200')
                self.elasticsearch_client = AsyncElasticsearch([es_url])
                await self.elasticsearch_client.ping()
                logger.info("Audit logging: Elasticsearch storage initialized")
            except Exception as e:
                logger.warning(f"Audit logging: Elasticsearch initialization failed: {e}")
    
    async def store_event(self, event: AuditEvent) -> bool:
        """Store audit event in all available backends"""
        success = False
        
        try:
            # Store in Redis for immediate access
            if self.redis_client:
                try:
                    redis_key = f"velro:audit:{event.event_id}"
                    event_data = json.dumps(event.to_dict())
                    await self.redis_client.setex(redis_key, 86400 * 30, event_data)  # 30 days
                    
                    # Add to sorted sets for efficient querying
                    timestamp_score = int(time.time())
                    await self.redis_client.zadd(
                        f"velro:audit:by_time",
                        {event.event_id: timestamp_score}
                    )
                    
                    if event.user_id:
                        await self.redis_client.zadd(
                            f"velro:audit:user:{event.user_id}",
                            {event.event_id: timestamp_score}
                        )
                    
                    success = True
                except Exception as e:
                    logger.error(f"Redis audit storage failed: {e}")
            
            # Store in Elasticsearch for analytics and long-term retention
            if self.elasticsearch_client:
                try:
                    index_name = f"velro-audit-{datetime.utcnow().strftime('%Y-%m')}"
                    await self.elasticsearch_client.index(
                        index=index_name,
                        id=event.event_id,
                        body=event.to_dict()
                    )
                    success = True
                except Exception as e:
                    logger.error(f"Elasticsearch audit storage failed: {e}")
            
            # Fallback to local buffer and file storage
            self.local_buffer.append(event)
            if len(self.local_buffer) >= self.max_buffer_size:
                await self._flush_local_buffer()
            
            success = True
            
        except Exception as e:
            logger.error(f"Audit event storage failed: {e}")
        
        return success
    
    async def _flush_local_buffer(self):
        """Flush local buffer to file storage"""
        if not self.local_buffer:
            return
        
        try:
            # Create audit logs directory
            log_dir = Path("logs/audit")
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Create compressed log file
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"audit_log_{timestamp}.jsonl.gz"
            
            with gzip.open(log_file, 'wt') as f:
                for event in self.local_buffer:
                    f.write(json.dumps(event.to_dict()) + '\n')
            
            logger.info(f"Flushed {len(self.local_buffer)} audit events to {log_file}")
            self.local_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush audit buffer: {e}")
    
    async def query_events(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Query audit events"""
        events = []
        
        try:
            # Query from Elasticsearch if available
            if self.elasticsearch_client:
                query = {"bool": {"must": []}}
                
                if user_id:
                    query["bool"]["must"].append({"term": {"user_id": user_id}})
                
                if event_type:
                    query["bool"]["must"].append({"term": {"event_type": event_type.value}})
                
                if start_time or end_time:
                    time_range = {}
                    if start_time:
                        time_range["gte"] = start_time.isoformat()
                    if end_time:
                        time_range["lte"] = end_time.isoformat()
                    query["bool"]["must"].append({"range": {"timestamp": time_range}})
                
                result = await self.elasticsearch_client.search(
                    index="velro-audit-*",
                    body={"query": query, "size": limit, "sort": [{"timestamp": "desc"}]}
                )
                
                for hit in result['hits']['hits']:
                    event_data = hit['_source']
                    # Convert back to AuditEvent object
                    event_data['event_type'] = AuditEventType(event_data['event_type'])
                    event_data['severity'] = AuditSeverity(event_data['severity'])
                    event_data['outcome'] = AuditOutcome(event_data['outcome'])
                    events.append(AuditEvent(**event_data))
            
            # Fallback to Redis query
            elif self.redis_client and user_id:
                event_ids = await self.redis_client.zrevrange(
                    f"velro:audit:user:{user_id}", 0, limit - 1
                )
                
                for event_id in event_ids:
                    event_data = await self.redis_client.get(f"velro:audit:{event_id}")
                    if event_data:
                        data = json.loads(event_data)
                        data['event_type'] = AuditEventType(data['event_type'])
                        data['severity'] = AuditSeverity(data['severity'])
                        data['outcome'] = AuditOutcome(data['outcome'])
                        events.append(AuditEvent(**data))
        
        except Exception as e:
            logger.error(f"Audit event query failed: {e}")
        
        return events


class ComprehensiveAuditLogger:
    """
    Comprehensive audit logging system for security and compliance.
    Tracks all security-relevant events across the application.
    """
    
    def __init__(self):
        self.storage = AuditStorage()
        self.event_queue = asyncio.Queue(maxsize=10000)
        self.processing_task: Optional[asyncio.Task] = None
        self.stats = {
            "events_logged": 0,
            "events_failed": 0,
            "storage_errors": 0,
            "high_risk_events": 0
        }
        
        # Start background event processing
        self._start_event_processing()
    
    def _start_event_processing(self):
        """Start background task for processing audit events"""
        try:
            loop = asyncio.get_running_loop()
            self.processing_task = loop.create_task(self._process_events())
        except RuntimeError:
            # No event loop running, will start later
            pass
    
    async def _process_events(self):
        """Background task to process queued audit events"""
        while True:
            try:
                # Get event from queue with timeout
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                
                # Store the event
                success = await self.storage.store_event(event)
                
                if success:
                    self.stats["events_logged"] += 1
                    
                    # Track high-risk events
                    if event.risk_score >= 70 or event.requires_investigation:
                        self.stats["high_risk_events"] += 1
                        await self._handle_high_risk_event(event)
                else:
                    self.stats["events_failed"] += 1
                
                # Mark task as done
                self.event_queue.task_done()
                
            except asyncio.TimeoutError:
                # No events in queue, continue
                continue
            except Exception as e:
                logger.error(f"Event processing error: {e}")
                self.stats["storage_errors"] += 1
                await asyncio.sleep(1)
    
    async def _handle_high_risk_event(self, event: AuditEvent):
        """Handle high-risk events that require immediate attention"""
        try:
            # Log to security monitoring system
            logger.warning(f"HIGH RISK AUDIT EVENT: {event.event_type.value} - {event.description}")
            
            # Store in high-priority queue for security team
            if self.storage.redis_client:
                await self.storage.redis_client.lpush(
                    "velro:audit:high_risk",
                    json.dumps(event.to_dict())
                )
                # Keep only last 1000 high-risk events
                await self.storage.redis_client.ltrim("velro:audit:high_risk", 0, 999)
            
            # TODO: Send to SIEM/security monitoring system
            # await self._send_to_security_monitoring(event)
            
        except Exception as e:
            logger.error(f"High-risk event handling failed: {e}")
    
    async def log_authentication_event(
        self,
        user_id: Optional[str],
        action: str,
        outcome: AuditOutcome,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> str:
        """Log authentication event"""
        
        severity = AuditSeverity.HIGH if outcome != AuditOutcome.SUCCESS else AuditSeverity.MEDIUM
        
        event = AuditEvent(
            event_id="",  # Will be auto-generated
            timestamp="",  # Will be auto-generated
            event_type=AuditEventType.AUTHENTICATION,
            severity=severity,
            outcome=outcome,
            user_id=user_id,
            session_id=session_id,
            client_ip=client_ip,
            user_agent=user_agent,
            action=action,
            description=f"Authentication {action} for user {user_id or 'unknown'}",
            details=details or {},
            tags=["authentication", action],
            compliance_tags=["SOX", "PCI-DSS", "GDPR"]
        )
        
        # Calculate risk score with authentication context
        event.calculate_risk_score({
            "failed_attempts": details.get("failed_attempts", 0) if details else 0,
            "unusual_location": details.get("unusual_location", False) if details else False
        })
        
        await self._enqueue_event(event)
        return event.event_id
    
    async def log_authorization_event(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        outcome: AuditOutcome,
        access_method: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log authorization event"""
        
        severity = AuditSeverity.HIGH if outcome == AuditOutcome.DENIED else AuditSeverity.MEDIUM
        
        event = AuditEvent(
            event_id="",
            timestamp="",
            event_type=AuditEventType.AUTHORIZATION,
            severity=severity,
            outcome=outcome,
            user_id=user_id,
            client_ip=client_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            description=f"Authorization check: {user_id} {action} {resource_type}/{resource_id}",
            details={
                "access_method": access_method,
                **(details or {})
            },
            tags=["authorization", action, resource_type],
            compliance_tags=["SOX", "GDPR", "AUDIT_TRAIL"]
        )
        
        event.calculate_risk_score()
        await self._enqueue_event(event)
        return event.event_id
    
    async def log_data_access_event(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        outcome: AuditOutcome,
        data_classification: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log data access event"""
        
        # Higher severity for sensitive data access
        severity = AuditSeverity.HIGH if data_classification in ["sensitive", "confidential"] else AuditSeverity.MEDIUM
        
        event = AuditEvent(
            event_id="",
            timestamp="",
            event_type=AuditEventType.DATA_ACCESS,
            severity=severity,
            outcome=outcome,
            user_id=user_id,
            client_ip=client_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            description=f"Data access: {user_id} {action} {resource_type}/{resource_id}",
            details={
                "data_classification": data_classification,
                **(details or {})
            },
            tags=["data_access", action, resource_type, data_classification or "unknown"],
            compliance_tags=["GDPR", "HIPAA", "PCI-DSS"] if data_classification == "sensitive" else ["AUDIT_TRAIL"]
        )
        
        event.calculate_risk_score()
        await self._enqueue_event(event)
        return event.event_id
    
    async def log_security_violation(
        self,
        violation_type: str,
        description: str,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.HIGH,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log security violation"""
        
        event = AuditEvent(
            event_id="",
            timestamp="",
            event_type=AuditEventType.SECURITY_VIOLATION,
            severity=severity,
            outcome=AuditOutcome.DENIED,
            user_id=user_id,
            client_ip=client_ip,
            action=violation_type,
            description=description,
            details=details or {},
            tags=["security_violation", violation_type],
            compliance_tags=["SECURITY_INCIDENT", "INVESTIGATION_REQUIRED"],
            requires_investigation=True
        )
        
        # Security violations always get high risk scores
        event.risk_score = 85
        
        await self._enqueue_event(event)
        return event.event_id
    
    async def log_admin_action(
        self,
        admin_user_id: str,
        action: str,
        target_resource: str,
        outcome: AuditOutcome,
        details: Optional[Dict[str, Any]] = None,
        client_ip: Optional[str] = None
    ) -> str:
        """Log administrative action"""
        
        event = AuditEvent(
            event_id="",
            timestamp="",
            event_type=AuditEventType.ADMIN_ACTION,
            severity=AuditSeverity.HIGH,  # All admin actions are high severity
            outcome=outcome,
            user_id=admin_user_id,
            client_ip=client_ip,
            action=action,
            description=f"Admin action: {admin_user_id} {action} on {target_resource}",
            details={
                "target_resource": target_resource,
                **(details or {})
            },
            tags=["admin_action", action],
            compliance_tags=["SOX", "ADMIN_AUDIT", "PRIVILEGED_ACCESS"]
        )
        
        event.calculate_risk_score()
        await self._enqueue_event(event)
        return event.event_id
    
    async def log_api_access(
        self,
        user_id: Optional[str],
        endpoint: str,
        method: str,
        response_status: int,
        duration_ms: float,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> str:
        """Log API access event"""
        
        outcome = AuditOutcome.SUCCESS if 200 <= response_status < 300 else AuditOutcome.FAILURE
        severity = AuditSeverity.LOW  # Most API calls are low severity
        
        # Increase severity for failed authentication/authorization
        if response_status in [401, 403]:
            severity = AuditSeverity.MEDIUM
        elif response_status >= 500:
            severity = AuditSeverity.HIGH
        
        event = AuditEvent(
            event_id="",
            timestamp="",
            event_type=AuditEventType.API_ACCESS,
            severity=severity,
            outcome=outcome,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            endpoint=endpoint,
            method=method,
            response_status=response_status,
            duration_ms=duration_ms,
            request_id=request_id,
            action=f"{method} {endpoint}",
            description=f"API call: {method} {endpoint} -> {response_status}",
            details={
                "response_time_ms": duration_ms,
                "status_category": self._get_status_category(response_status)
            },
            tags=["api_access", method.lower(), self._get_status_category(response_status)]
        )
        
        event.calculate_risk_score()
        await self._enqueue_event(event)
        return event.event_id
    
    def _get_status_category(self, status_code: int) -> str:
        """Get status code category"""
        if 200 <= status_code < 300:
            return "success"
        elif 400 <= status_code < 500:
            return "client_error"
        elif 500 <= status_code < 600:
            return "server_error"
        else:
            return "other"
    
    async def _enqueue_event(self, event: AuditEvent):
        """Enqueue event for background processing"""
        try:
            await self.event_queue.put(event)
        except asyncio.QueueFull:
            logger.error("Audit event queue is full, dropping event")
            self.stats["events_failed"] += 1
    
    async def search_events(
        self,
        query: Dict[str, Any],
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search audit events"""
        try:
            # Convert query parameters
            user_id = query.get("user_id")
            event_type = AuditEventType(query["event_type"]) if "event_type" in query else None
            start_time = datetime.fromisoformat(query["start_time"]) if "start_time" in query else None
            end_time = datetime.fromisoformat(query["end_time"]) if "end_time" in query else None
            
            events = await self.storage.query_events(
                user_id=user_id,
                event_type=event_type,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            
            return [event.to_dict() for event in events]
            
        except Exception as e:
            logger.error(f"Audit search failed: {e}")
            return []
    
    def get_audit_statistics(self) -> Dict[str, Any]:
        """Get audit logging statistics"""
        return {
            **self.stats,
            "queue_size": self.event_queue.qsize(),
            "processing_active": self.processing_task is not None and not self.processing_task.done(),
            "storage_backends": {
                "redis": self.storage.redis_client is not None,
                "elasticsearch": self.storage.elasticsearch_client is not None,
                "local_buffer_size": len(self.storage.local_buffer)
            }
        }
    
    async def shutdown(self):
        """Graceful shutdown of audit logging system"""
        # Stop event processing
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        
        # Process remaining events in queue
        while not self.event_queue.empty():
            try:
                event = self.event_queue.get_nowait()
                await self.storage.store_event(event)
                self.event_queue.task_done()
            except asyncio.QueueEmpty:
                break
        
        # Flush local buffer
        await self.storage._flush_local_buffer()
        
        logger.info("Audit logging system shutdown complete")


# Global audit logger instance
audit_logger: Optional[ComprehensiveAuditLogger] = None


def get_audit_logger() -> ComprehensiveAuditLogger:
    """Get or create the global audit logger instance"""
    global audit_logger
    if audit_logger is None:
        audit_logger = ComprehensiveAuditLogger()
    return audit_logger


# Convenience functions for common audit scenarios
async def audit_user_login(user_id: str, success: bool, client_ip: str, details: Optional[Dict[str, Any]] = None) -> str:
    """Audit user login attempt"""
    logger = get_audit_logger()
    return await logger.log_authentication_event(
        user_id=user_id,
        action="login",
        outcome=AuditOutcome.SUCCESS if success else AuditOutcome.FAILURE,
        client_ip=client_ip,
        details=details
    )


async def audit_resource_access(user_id: str, resource_type: str, resource_id: str, allowed: bool, details: Optional[Dict[str, Any]] = None) -> str:
    """Audit resource access attempt"""
    logger = get_audit_logger()
    return await logger.log_authorization_event(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action="access",
        outcome=AuditOutcome.SUCCESS if allowed else AuditOutcome.DENIED,
        details=details
    )


async def audit_data_modification(user_id: str, resource_type: str, resource_id: str, action: str, success: bool, details: Optional[Dict[str, Any]] = None) -> str:
    """Audit data modification"""
    logger = get_audit_logger()
    return await logger.log_data_access_event(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        outcome=AuditOutcome.SUCCESS if success else AuditOutcome.FAILURE,
        details=details
    )


async def audit_security_incident(violation_type: str, description: str, user_id: Optional[str] = None, client_ip: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> str:
    """Audit security incident"""
    logger = get_audit_logger()
    return await logger.log_security_violation(
        violation_type=violation_type,
        description=description,
        user_id=user_id,
        client_ip=client_ip,
        severity=AuditSeverity.HIGH,
        details=details
    )