"""
Structured logging system for authorization events, security monitoring, and compliance.
Provides centralized logging with search capabilities and SIEM integration support.
"""

import logging
import json
import time
import threading
import traceback
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import uuid
import hashlib
import os

from config import settings

class LogLevel(Enum):
    """Log level enumeration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EventType(Enum):
    """Event type classification for structured logging."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SECURITY_VIOLATION = "security_violation"
    PERFORMANCE = "performance"
    AUDIT = "audit"
    ACCESS = "access"
    DATA_ACCESS = "data_access"
    SYSTEM = "system"
    COMPLIANCE = "compliance"


@dataclass
class LogEvent:
    """Structured log event with comprehensive metadata."""
    event_id: str
    event_type: EventType
    timestamp: datetime
    level: LogLevel
    message: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = None
    duration_ms: Optional[float] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    stack_trace: Optional[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.tags is None:
            self.tags = []
        if self.event_id is None:
            self.event_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert log event to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['event_type'] = self.event_type.value
        data['level'] = self.level.value
        return data
    
    def to_json(self) -> str:
        """Convert log event to JSON string."""
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        
        # Extract structured data from record
        event_data = getattr(record, 'event_data', {})
        
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'process_id': record.process,
            'thread_id': record.thread,
            **event_data
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'stack_trace': self.formatException(record.exc_info)
            }
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


class StructuredLogger:
    """
    High-performance structured logger with event classification and filtering.
    Provides centralized logging for all application events with metadata support.
    """
    
    def __init__(self, name: str, log_dir: str = "logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
        
        # Remove default handlers to avoid duplication
        self.logger.handlers.clear()
        
        # Setup structured formatter
        self.formatter = StructuredFormatter()
        
        # Console handler with structured output
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self.formatter)
        console_handler.setLevel(logging.INFO)
        self.logger.addHandler(console_handler)
        
        # File handler for all logs
        log_file = self.log_dir / f"{name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=10
        )
        file_handler.setFormatter(self.formatter)
        file_handler.setLevel(logging.DEBUG)
        self.logger.addHandler(file_handler)
        
        # Time-based handler for daily rotation
        daily_handler = TimedRotatingFileHandler(
            self.log_dir / f"{name}_daily.log",
            when='midnight',
            interval=1,
            backupCount=30
        )
        daily_handler.setFormatter(self.formatter)
        daily_handler.setLevel(logging.INFO)
        self.logger.addHandler(daily_handler)
        
        # Thread-safe event buffer for high-throughput scenarios
        self._event_buffer: List[LogEvent] = []
        self._buffer_lock = threading.Lock()
        self._buffer_max_size = 1000
    
    def _log_structured(self, level: LogLevel, event_type: EventType, 
                       message: str, **kwargs):
        """Internal method for structured logging."""
        
        event = LogEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
            **kwargs
        )
        
        # Add to buffer for analysis
        with self._buffer_lock:
            self._event_buffer.append(event)
            if len(self._event_buffer) > self._buffer_max_size:
                self._event_buffer = self._event_buffer[-self._buffer_max_size:]
        
        # Convert to log record
        log_level = getattr(logging, level.value)
        extra = {'event_data': event.to_dict()}
        
        self.logger.log(log_level, message, extra=extra)
    
    def debug(self, message: str, event_type: EventType = EventType.SYSTEM, **kwargs):
        """Log debug message with structured data."""
        self._log_structured(LogLevel.DEBUG, event_type, message, **kwargs)
    
    def info(self, message: str, event_type: EventType = EventType.SYSTEM, **kwargs):
        """Log info message with structured data."""
        self._log_structured(LogLevel.INFO, event_type, message, **kwargs)
    
    def warning(self, message: str, event_type: EventType = EventType.SYSTEM, **kwargs):
        """Log warning message with structured data."""
        self._log_structured(LogLevel.WARNING, event_type, message, **kwargs)
    
    def error(self, message: str, event_type: EventType = EventType.SYSTEM, 
             exception: Optional[Exception] = None, **kwargs):
        """Log error message with optional exception details."""
        if exception:
            kwargs['stack_trace'] = traceback.format_exc()
            kwargs['exception_type'] = type(exception).__name__
            kwargs['exception_message'] = str(exception)
        
        self._log_structured(LogLevel.ERROR, event_type, message, **kwargs)
    
    def critical(self, message: str, event_type: EventType = EventType.SYSTEM, 
                exception: Optional[Exception] = None, **kwargs):
        """Log critical message with optional exception details."""
        if exception:
            kwargs['stack_trace'] = traceback.format_exc()
            kwargs['exception_type'] = type(exception).__name__
            kwargs['exception_message'] = str(exception)
        
        self._log_structured(LogLevel.CRITICAL, event_type, message, **kwargs)
    
    def get_recent_events(self, limit: int = 100, 
                         event_type: Optional[EventType] = None) -> List[Dict[str, Any]]:
        """Get recent log events from buffer."""
        with self._buffer_lock:
            events = self._event_buffer.copy()
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return [event.to_dict() for event in events[-limit:]]


class AuditLogger(StructuredLogger):
    """
    Specialized audit logger for compliance and regulatory requirements.
    Provides immutable audit trail with integrity verification.
    """
    
    def __init__(self, name: str = "audit"):
        super().__init__(name, log_dir="logs/audit")
        
        # Additional security measures for audit logs
        self._audit_sequence = 0
        self._sequence_lock = threading.Lock()
        
        # Setup dedicated audit file handler
        audit_file = self.log_dir / "audit_trail.log"
        audit_handler = TimedRotatingFileHandler(
            audit_file,
            when='midnight',
            interval=1,
            backupCount=365  # Keep audit logs for 1 year
        )
        audit_handler.setFormatter(self.formatter)
        audit_handler.setLevel(logging.INFO)
        self.logger.addHandler(audit_handler)
    
    def _get_next_sequence(self) -> int:
        """Get next audit sequence number."""
        with self._sequence_lock:
            self._audit_sequence += 1
            return self._audit_sequence
    
    def _calculate_integrity_hash(self, event_data: Dict[str, Any]) -> str:
        """Calculate integrity hash for audit event."""
        event_string = json.dumps(event_data, sort_keys=True, default=str)
        return hashlib.sha256(event_string.encode()).hexdigest()
    
    def audit_event(self, event_type: str, user_id: Optional[str], 
                   action: str, resource: Optional[str] = None,
                   result: str = "success", **metadata):
        """Log audit event with integrity verification."""
        
        sequence = self._get_next_sequence()
        
        audit_data = {
            'audit_sequence': sequence,
            'event_type': event_type,
            'user_id': user_id,
            'action': action,
            'resource': resource,
            'result': result,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metadata': metadata
        }
        
        # Add integrity hash
        audit_data['integrity_hash'] = self._calculate_integrity_hash(audit_data)
        
        message = f"AUDIT: {event_type} - {action}"
        if resource:
            message += f" on {resource}"
        
        self._log_structured(
            LogLevel.INFO,
            EventType.AUDIT,
            message,
            **audit_data
        )
    
    def user_login(self, user_id: str, success: bool, source_ip: str, 
                  user_agent: str, **metadata):
        """Audit user login attempt."""
        self.audit_event(
            "user_authentication",
            user_id,
            "login",
            result="success" if success else "failure",
            source_ip=source_ip,
            user_agent=user_agent,
            **metadata
        )
    
    def user_logout(self, user_id: str, session_id: str, **metadata):
        """Audit user logout."""
        self.audit_event(
            "user_authentication",
            user_id,
            "logout",
            session_id=session_id,
            **metadata
        )
    
    def authorization_check(self, user_id: str, resource: str, action: str,
                          result: bool, **metadata):
        """Audit authorization check."""
        self.audit_event(
            "authorization",
            user_id,
            f"check_{action}",
            resource=resource,
            result="granted" if result else "denied",
            **metadata
        )
    
    def data_access(self, user_id: str, table: str, operation: str,
                   record_count: int = 1, **metadata):
        """Audit data access operations."""
        self.audit_event(
            "data_access",
            user_id,
            operation,
            resource=table,
            record_count=record_count,
            **metadata
        )
    
    def security_violation(self, violation_type: str, source_ip: str,
                          severity: str = "medium", **metadata):
        """Audit security violations."""
        self.audit_event(
            "security_violation",
            None,
            violation_type,
            result="blocked",
            source_ip=source_ip,
            severity=severity,
            **metadata
        )


class SecurityLogger(StructuredLogger):
    """
    Specialized security logger for threat detection and incident response.
    Provides real-time security event monitoring with alerting capabilities.
    """
    
    def __init__(self, name: str = "security"):
        super().__init__(name, log_dir="logs/security")
        
        # Security event counters
        self._violation_counts: Dict[str, int] = {}
        self._violation_lock = threading.Lock()
        
        # Setup dedicated security file handler
        security_file = self.log_dir / "security_events.log"
        security_handler = RotatingFileHandler(
            security_file,
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=20
        )
        security_handler.setFormatter(self.formatter)
        security_handler.setLevel(logging.WARNING)
        self.logger.addHandler(security_handler)
    
    def _increment_violation_count(self, violation_type: str) -> int:
        """Increment violation counter and return new count."""
        with self._violation_lock:
            self._violation_counts[violation_type] = self._violation_counts.get(violation_type, 0) + 1
            return self._violation_counts[violation_type]
    
    def security_violation(self, violation_type: str, source_ip: str,
                          severity: str = "medium", user_id: Optional[str] = None,
                          **metadata):
        """Log security violation with automatic counting."""
        
        count = self._increment_violation_count(violation_type)
        
        message = f"SECURITY VIOLATION: {violation_type} from {source_ip}"
        
        self.warning(
            message,
            event_type=EventType.SECURITY_VIOLATION,
            violation_type=violation_type,
            source_ip=source_ip,
            severity=severity,
            user_id=user_id,
            violation_count=count,
            **metadata
        )
    
    def failed_authentication(self, user_id: str, source_ip: str, 
                            failure_reason: str, **metadata):
        """Log failed authentication attempt."""
        self.security_violation(
            "failed_authentication",
            source_ip,
            severity="high",
            user_id=user_id,
            failure_reason=failure_reason,
            **metadata
        )
    
    def rate_limit_exceeded(self, source_ip: str, endpoint: str, 
                           limit_type: str, **metadata):
        """Log rate limit violations."""
        self.security_violation(
            "rate_limit_exceeded",
            source_ip,
            severity="medium",
            endpoint=endpoint,
            limit_type=limit_type,
            **metadata
        )
    
    def suspicious_activity(self, activity_type: str, source_ip: str,
                           user_id: Optional[str] = None, **metadata):
        """Log suspicious activity patterns."""
        self.security_violation(
            f"suspicious_{activity_type}",
            source_ip,
            severity="high",
            user_id=user_id,
            **metadata
        )
    
    def unauthorized_access_attempt(self, resource: str, source_ip: str,
                                   user_id: Optional[str] = None, **metadata):
        """Log unauthorized access attempts."""
        self.security_violation(
            "unauthorized_access",
            source_ip,
            severity="high",
            user_id=user_id,
            resource=resource,
            **metadata
        )
    
    def get_violation_summary(self) -> Dict[str, int]:
        """Get summary of security violations."""
        with self._violation_lock:
            return self._violation_counts.copy()


class PerformanceLogger(StructuredLogger):
    """
    Specialized logger for performance monitoring and optimization.
    Tracks response times, throughput, and performance bottlenecks.
    """
    
    def __init__(self, name: str = "performance"):
        super().__init__(name, log_dir="logs/performance")
        
        # Performance tracking
        self._response_times: List[float] = []
        self._performance_lock = threading.Lock()
        
        # Setup performance-specific handler
        perf_file = self.log_dir / "performance_metrics.jsonl"
        perf_handler = TimedRotatingFileHandler(
            perf_file,
            when='midnight',
            interval=1,
            backupCount=7
        )
        perf_handler.setFormatter(self.formatter)
        perf_handler.setLevel(logging.INFO)
        self.logger.addHandler(perf_handler)
    
    def log_request_performance(self, endpoint: str, method: str, 
                              duration_ms: float, status_code: int,
                              user_id: Optional[str] = None, **metadata):
        """Log HTTP request performance metrics."""
        
        # Track response time
        with self._performance_lock:
            self._response_times.append(duration_ms)
            if len(self._response_times) > 1000:
                self._response_times = self._response_times[-1000:]
        
        # Determine performance level
        level = LogLevel.INFO
        if duration_ms > 1000:  # > 1 second
            level = LogLevel.WARNING
        elif duration_ms > 5000:  # > 5 seconds
            level = LogLevel.ERROR
        
        message = f"REQUEST: {method} {endpoint} - {duration_ms}ms - {status_code}"
        
        self._log_structured(
            level,
            EventType.PERFORMANCE,
            message,
            endpoint=endpoint,
            method=method,
            duration_ms=duration_ms,
            status_code=status_code,
            user_id=user_id,
            **metadata
        )
    
    def log_database_performance(self, operation: str, table: str,
                               duration_ms: float, record_count: int = 0,
                               **metadata):
        """Log database operation performance."""
        
        level = LogLevel.INFO
        if duration_ms > 100:  # > 100ms for DB operations
            level = LogLevel.WARNING
        elif duration_ms > 1000:  # > 1 second
            level = LogLevel.ERROR
        
        message = f"DB: {operation} on {table} - {duration_ms}ms - {record_count} records"
        
        self._log_structured(
            level,
            EventType.PERFORMANCE,
            message,
            operation=operation,
            table=table,
            duration_ms=duration_ms,
            record_count=record_count,
            **metadata
        )
    
    def log_cache_performance(self, cache_name: str, operation: str,
                             duration_ms: float, hit: bool, **metadata):
        """Log cache operation performance."""
        
        message = f"CACHE: {cache_name} {operation} - {duration_ms}ms - {'HIT' if hit else 'MISS'}"
        
        self._log_structured(
            LogLevel.INFO,
            EventType.PERFORMANCE,
            message,
            cache_name=cache_name,
            operation=operation,
            duration_ms=duration_ms,
            cache_hit=hit,
            **metadata
        )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary statistics."""
        with self._performance_lock:
            response_times = self._response_times.copy()
        
        if not response_times:
            return {"status": "no_data"}
        
        return {
            "total_requests": len(response_times),
            "avg_response_time_ms": sum(response_times) / len(response_times),
            "min_response_time_ms": min(response_times),
            "max_response_time_ms": max(response_times),
            "p95_response_time_ms": sorted(response_times)[int(len(response_times) * 0.95)],
            "p99_response_time_ms": sorted(response_times)[int(len(response_times) * 0.99)],
            "slow_requests": sum(1 for rt in response_times if rt > 1000),
            "very_slow_requests": sum(1 for rt in response_times if rt > 5000)
        }


# Global logger instances
app_logger = StructuredLogger("velro_app")
audit_logger = AuditLogger()
security_logger = SecurityLogger()
performance_logger = PerformanceLogger()


def get_logger(name: str) -> StructuredLogger:
    """Get or create a named structured logger."""
    return StructuredLogger(name)