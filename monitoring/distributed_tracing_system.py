"""
Enterprise Distributed Tracing and Observability System.
Provides comprehensive request flow tracking, performance analysis, and bottleneck identification.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Set, Callable, Union
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from contextvars import ContextVar
import threading
from collections import defaultdict

from monitoring.metrics import metrics_collector

logger = logging.getLogger(__name__)

# Context variables for trace propagation
trace_context: ContextVar[Optional['TraceContext']] = ContextVar('trace_context', default=None)
span_context: ContextVar[Optional['Span']] = ContextVar('span_context', default=None)


class SpanType(Enum):
    """Types of spans for categorization."""
    HTTP_REQUEST = "http_request"
    DATABASE_QUERY = "database_query"
    CACHE_OPERATION = "cache_operation"
    EXTERNAL_API_CALL = "external_api_call"
    AUTHORIZATION = "authorization"
    BUSINESS_LOGIC = "business_logic"
    BACKGROUND_TASK = "background_task"
    INTERNAL_SERVICE_CALL = "internal_service_call"


class SpanStatus(Enum):
    """Span completion status."""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TraceContext:
    """Trace context for request correlation."""
    trace_id: str
    parent_span_id: Optional[str] = None
    baggage: Dict[str, str] = field(default_factory=dict)
    sampling_decision: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "baggage": self.baggage,
            "sampling_decision": self.sampling_decision
        }


@dataclass
class Span:
    """Distributed trace span."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    operation_name: str
    service_name: str
    span_type: SpanType
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "service_name": self.service_name,
            "span_type": self.span_type.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "tags": self.tags,
            "logs": self.logs,
            "error": self.error
        }


@dataclass
class Trace:
    """Complete distributed trace."""
    trace_id: str
    root_span: Span
    spans: List[Span] = field(default_factory=list)
    services: Set[str] = field(default_factory=set)
    total_duration_ms: float = 0.0
    span_count: int = 0
    error_count: int = 0
    critical_path: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "root_span": self.root_span.to_dict(),
            "spans": [span.to_dict() for span in self.spans],
            "services": list(self.services),
            "total_duration_ms": self.total_duration_ms,
            "span_count": self.span_count,
            "error_count": self.error_count,
            "critical_path": self.critical_path
        }


class SpanProcessor:
    """Processes completed spans for analysis and export."""
    
    def __init__(self):
        self.completed_spans: List[Span] = []
        self.span_buffer_size = 1000
        self.flush_interval_seconds = 30
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
    
    def add_span(self, span: Span):
        """Add completed span to processor."""
        with self._lock:
            self.completed_spans.append(span)
            
            # Keep buffer size manageable
            if len(self.completed_spans) > self.span_buffer_size:
                self.completed_spans = self.completed_spans[-self.span_buffer_size:]
    
    async def start(self):
        """Start the span processor."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("🔄 [TRACING] Span processor started")
    
    async def stop(self):
        """Stop the span processor."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        logger.info("🔄 [TRACING] Span processor stopped")
    
    async def _flush_loop(self):
        """Flush spans periodically."""
        while True:
            try:
                await self._flush_spans()
                await asyncio.sleep(self.flush_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [TRACING] Span flush error: {e}")
                await asyncio.sleep(30)
    
    async def _flush_spans(self):
        """Flush spans to metrics and storage."""
        with self._lock:
            spans_to_flush = self.completed_spans.copy()
            self.completed_spans.clear()
        
        if not spans_to_flush:
            return
        
        # Update metrics
        for span in spans_to_flush:
            self._update_span_metrics(span)
        
        # Export spans (to Jaeger, Zipkin, etc.)
        await self._export_spans(spans_to_flush)
        
        logger.debug(f"📤 [TRACING] Flushed {len(spans_to_flush)} spans")
    
    def _update_span_metrics(self, span: Span):
        """Update Prometheus metrics from span data."""
        if span.duration_ms is not None:
            # Record span duration
            metrics_collector.tracing_metrics.record_span_duration(
                span.service_name,
                span.operation_name,
                span.span_type.value,
                span.duration_ms / 1000
            )
            
            # Record service call if it's an external call
            if span.parent_span_id and span.span_type == SpanType.EXTERNAL_API_CALL:
                parent_service = span.tags.get("parent_service", "unknown")
                metrics_collector.tracing_metrics.record_service_call(
                    parent_service,
                    span.service_name,
                    span.operation_name,
                    span.status.value,
                    span.duration_ms / 1000
                )
    
    async def _export_spans(self, spans: List[Span]):
        """Export spans to external tracing system."""
        # This would export to Jaeger, Zipkin, etc.
        # For now, just log for demonstration
        logger.debug(f"📡 [TRACING] Would export {len(spans)} spans to tracing backend")


class TraceAnalyzer:
    """Analyzes traces for performance insights and bottlenecks."""
    
    def __init__(self):
        self.completed_traces: Dict[str, Trace] = {}
        self.trace_retention_minutes = 60
        self.analysis_interval_seconds = 300  # 5 minutes
        self._analysis_task: Optional[asyncio.Task] = None
    
    def add_completed_trace(self, trace: Trace):
        """Add completed trace for analysis."""
        self.completed_traces[trace.trace_id] = trace
        
        # Clean old traces
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.trace_retention_minutes)
        traces_to_remove = [
            trace_id for trace_id, t in self.completed_traces.items()
            if t.root_span.start_time < cutoff_time
        ]
        
        for trace_id in traces_to_remove:
            del self.completed_traces[trace_id]
    
    async def start(self):
        """Start the trace analyzer."""
        if self._analysis_task is None or self._analysis_task.done():
            self._analysis_task = asyncio.create_task(self._analysis_loop())
        logger.info("🔍 [TRACING] Trace analyzer started")
    
    async def stop(self):
        """Stop the trace analyzer."""
        if self._analysis_task and not self._analysis_task.done():
            self._analysis_task.cancel()
        logger.info("🔍 [TRACING] Trace analyzer stopped")
    
    async def _analysis_loop(self):
        """Periodic trace analysis."""
        while True:
            try:
                await self._analyze_traces()
                await asyncio.sleep(self.analysis_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [TRACING] Trace analysis error: {e}")
                await asyncio.sleep(60)
    
    async def _analyze_traces(self):
        """Analyze completed traces."""
        if not self.completed_traces:
            return
        
        # Analyze performance patterns
        performance_analysis = self._analyze_performance_patterns()
        
        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks()
        
        # Analyze error patterns
        error_analysis = self._analyze_error_patterns()
        
        # Service dependency analysis
        dependency_analysis = self._analyze_service_dependencies()
        
        logger.info(
            f"🔍 [TRACING] Analysis complete - "
            f"Traces: {len(self.completed_traces)}, "
            f"Bottlenecks: {len(bottlenecks)}, "
            f"Error patterns: {len(error_analysis)}"
        )
        
        # Update metrics based on analysis
        await self._update_analysis_metrics(performance_analysis, bottlenecks, error_analysis)
    
    def _analyze_performance_patterns(self) -> Dict[str, Any]:
        """Analyze performance patterns across traces."""
        service_durations = defaultdict(list)
        operation_durations = defaultdict(list)
        
        for trace in self.completed_traces.values():
            for span in trace.spans:
                if span.duration_ms is not None:
                    service_durations[span.service_name].append(span.duration_ms)
                    operation_durations[span.operation_name].append(span.duration_ms)
        
        # Calculate percentiles
        def calculate_percentiles(values):
            if not values:
                return {}
            sorted_values = sorted(values)
            length = len(sorted_values)
            return {
                "p50": sorted_values[int(length * 0.5)],
                "p95": sorted_values[int(length * 0.95)],
                "p99": sorted_values[int(length * 0.99)],
                "avg": sum(values) / len(values),
                "max": max(values)
            }
        
        return {
            "services": {
                service: calculate_percentiles(durations)
                for service, durations in service_durations.items()
            },
            "operations": {
                operation: calculate_percentiles(durations)
                for operation, durations in operation_durations.items()
            }
        }
    
    def _identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks."""
        bottlenecks = []
        
        # Find slow operations (>1 second average)
        operation_times = defaultdict(list)
        for trace in self.completed_traces.values():
            for span in trace.spans:
                if span.duration_ms is not None:
                    operation_times[f"{span.service_name}:{span.operation_name}"].append(span.duration_ms)
        
        for operation, times in operation_times.items():
            avg_time = sum(times) / len(times)
            if avg_time > 1000:  # >1 second
                service, op_name = operation.split(':', 1)
                bottlenecks.append({
                    "type": "slow_operation",
                    "service": service,
                    "operation": op_name,
                    "avg_duration_ms": avg_time,
                    "occurrence_count": len(times),
                    "severity": "high" if avg_time > 5000 else "medium"
                })
        
        # Find high error rate operations
        operation_errors = defaultdict(int)
        operation_counts = defaultdict(int)
        
        for trace in self.completed_traces.values():
            for span in trace.spans:
                key = f"{span.service_name}:{span.operation_name}"
                operation_counts[key] += 1
                if span.status == SpanStatus.ERROR:
                    operation_errors[key] += 1
        
        for operation, total_count in operation_counts.items():
            error_count = operation_errors.get(operation, 0)
            error_rate = (error_count / total_count) * 100
            
            if error_rate > 5:  # >5% error rate
                service, op_name = operation.split(':', 1)
                bottlenecks.append({
                    "type": "high_error_rate",
                    "service": service,
                    "operation": op_name,
                    "error_rate_percent": error_rate,
                    "total_requests": total_count,
                    "error_requests": error_count,
                    "severity": "high" if error_rate > 20 else "medium"
                })
        
        return bottlenecks
    
    def _analyze_error_patterns(self) -> List[Dict[str, Any]]:
        """Analyze error patterns in traces."""
        error_patterns = []
        error_types = defaultdict(int)
        error_services = defaultdict(int)
        
        for trace in self.completed_traces.values():
            for span in trace.spans:
                if span.status == SpanStatus.ERROR and span.error:
                    error_types[span.error] += 1
                    error_services[span.service_name] += 1
        
        # Most common error types
        for error_type, count in error_types.items():
            error_patterns.append({
                "type": "error_frequency",
                "error_message": error_type,
                "occurrence_count": count,
                "category": "application_error"
            })
        
        # Services with most errors
        for service, count in error_services.items():
            if count > 5:  # More than 5 errors in analysis period
                error_patterns.append({
                    "type": "error_prone_service",
                    "service": service,
                    "error_count": count,
                    "category": "service_reliability"
                })
        
        return error_patterns
    
    def _analyze_service_dependencies(self) -> Dict[str, Any]:
        """Analyze service dependency patterns."""
        service_calls = defaultdict(lambda: defaultdict(int))
        service_latencies = defaultdict(lambda: defaultdict(list))
        
        for trace in self.completed_traces.values():
            # Build service call graph from spans
            spans_by_service = defaultdict(list)
            for span in trace.spans:
                spans_by_service[span.service_name].append(span)
            
            # Analyze calls between services
            for span in trace.spans:
                if span.parent_span_id:
                    parent_span = next(
                        (s for s in trace.spans if s.span_id == span.parent_span_id),
                        None
                    )
                    if parent_span and parent_span.service_name != span.service_name:
                        # Cross-service call
                        service_calls[parent_span.service_name][span.service_name] += 1
                        if span.duration_ms is not None:
                            service_latencies[parent_span.service_name][span.service_name].append(span.duration_ms)
        
        # Calculate dependency metrics
        dependencies = {}
        for from_service, to_services in service_calls.items():
            dependencies[from_service] = {}
            for to_service, call_count in to_services.items():
                latencies = service_latencies[from_service][to_service]
                avg_latency = sum(latencies) / len(latencies) if latencies else 0
                
                dependencies[from_service][to_service] = {
                    "call_count": call_count,
                    "avg_latency_ms": avg_latency,
                    "dependency_strength": "high" if call_count > 10 else "medium" if call_count > 3 else "low"
                }
        
        return {"service_dependencies": dependencies}
    
    async def _update_analysis_metrics(self, performance_analysis: Dict, bottlenecks: List, error_analysis: List):
        """Update metrics based on trace analysis."""
        # Update business metrics based on analysis
        total_bottlenecks = len(bottlenecks)
        critical_bottlenecks = len([b for b in bottlenecks if b.get("severity") == "high"])
        
        # This would update actual metrics
        logger.debug(f"📊 [TRACING] Analysis metrics - Bottlenecks: {total_bottlenecks}, Critical: {critical_bottlenecks}")
    
    def get_performance_insights(self) -> Dict[str, Any]:
        """Get performance insights from trace analysis."""
        if not self.completed_traces:
            return {"error": "No traces available for analysis"}
        
        performance_patterns = self._analyze_performance_patterns()
        bottlenecks = self._identify_bottlenecks()
        error_patterns = self._analyze_error_patterns()
        dependency_analysis = self._analyze_service_dependencies()
        
        return {
            "trace_count": len(self.completed_traces),
            "performance_patterns": performance_patterns,
            "bottlenecks": bottlenecks,
            "error_patterns": error_patterns,
            "service_dependencies": dependency_analysis,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat()
        }


class DistributedTracingSystem:
    """
    Enterprise distributed tracing system for comprehensive observability.
    """
    
    def __init__(self):
        self.active_traces: Dict[str, Trace] = {}
        self.active_spans: Dict[str, Span] = {}
        self.span_processor = SpanProcessor()
        self.trace_analyzer = TraceAnalyzer()
        
        self.sampling_rate = 1.0  # Sample 100% by default
        self.service_name = "velro-backend"
        
        # Background cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
        self.trace_timeout_minutes = 30
        
    async def start(self):
        """Start the distributed tracing system."""
        await self.span_processor.start()
        await self.trace_analyzer.start()
        
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("🔍 [TRACING] Distributed tracing system started")
    
    async def stop(self):
        """Stop the distributed tracing system."""
        await self.span_processor.stop()
        await self.trace_analyzer.stop()
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        
        logger.info("🔍 [TRACING] Distributed tracing system stopped")
    
    def start_trace(self, operation_name: str, 
                   span_type: SpanType = SpanType.HTTP_REQUEST,
                   parent_context: Optional[TraceContext] = None) -> Tuple[TraceContext, Span]:
        """Start a new trace or continue existing one."""
        
        # Check sampling decision
        if parent_context:
            should_sample = parent_context.sampling_decision
            trace_id = parent_context.trace_id
            parent_span_id = parent_context.parent_span_id
        else:
            should_sample = self._should_sample()
            trace_id = self._generate_trace_id()
            parent_span_id = None
        
        if not should_sample:
            # Return no-op span
            return self._create_noop_trace_context(trace_id), self._create_noop_span(trace_id)
        
        # Create span
        span_id = self._generate_span_id()
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            service_name=self.service_name,
            span_type=span_type,
            start_time=datetime.now(timezone.utc)
        )
        
        # Create or update trace context
        context = TraceContext(
            trace_id=trace_id,
            parent_span_id=span_id,
            sampling_decision=should_sample
        )
        
        # Store active span
        self.active_spans[span_id] = span
        
        # Create or update trace
        if trace_id not in self.active_traces:
            trace = Trace(
                trace_id=trace_id,
                root_span=span
            )
            self.active_traces[trace_id] = trace
        
        trace = self.active_traces[trace_id]
        trace.spans.append(span)
        trace.services.add(self.service_name)
        trace.span_count += 1
        
        # Set context
        trace_context.set(context)
        span_context.set(span)
        
        logger.debug(f"🔍 [TRACING] Started span {span_id} for trace {trace_id}: {operation_name}")
        
        return context, span
    
    def finish_span(self, span: Span, status: SpanStatus = SpanStatus.OK, error: str = None):
        """Finish a span."""
        if span.end_time is not None:
            return  # Already finished
        
        span.end_time = datetime.now(timezone.utc)
        span.duration_ms = (span.end_time - span.start_time).total_seconds() * 1000
        span.status = status
        
        if error:
            span.error = error
            span.status = SpanStatus.ERROR
        
        # Update trace
        trace = self.active_traces.get(span.trace_id)
        if trace:
            trace.total_duration_ms = max(trace.total_duration_ms, span.duration_ms)
            if span.status == SpanStatus.ERROR:
                trace.error_count += 1
        
        # Remove from active spans
        if span.span_id in self.active_spans:
            del self.active_spans[span.span_id]
        
        # Process completed span
        self.span_processor.add_span(span)
        
        # Record metrics
        metrics_collector.tracing_metrics.record_trace_request(
            self.service_name,
            span.operation_name,
            span.status.value,
            span.duration_ms,
            1  # span count
        )
        
        logger.debug(f"🔍 [TRACING] Finished span {span.span_id}: {span.operation_name} ({span.duration_ms:.1f}ms)")
        
        # Check if trace is complete
        self._check_trace_completion(span.trace_id)
    
    def add_span_tag(self, key: str, value: str, span: Optional[Span] = None):
        """Add tag to span."""
        target_span = span or span_context.get()
        if target_span:
            target_span.tags[key] = value
    
    def add_span_log(self, message: str, level: str = "info", span: Optional[Span] = None):
        """Add log entry to span."""
        target_span = span or span_context.get()
        if target_span:
            target_span.logs.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "message": message
            })
    
    def _check_trace_completion(self, trace_id: str):
        """Check if trace is complete and move to analysis."""
        trace = self.active_traces.get(trace_id)
        if not trace:
            return
        
        # Check if all spans in trace are completed
        active_spans_in_trace = [
            span for span in self.active_spans.values()
            if span.trace_id == trace_id
        ]
        
        if not active_spans_in_trace:
            # Trace is complete
            self._finalize_trace(trace)
            del self.active_traces[trace_id]
    
    def _finalize_trace(self, trace: Trace):
        """Finalize completed trace."""
        # Calculate critical path
        trace.critical_path = self._calculate_critical_path(trace)
        
        # Add to analyzer
        self.trace_analyzer.add_completed_trace(trace)
        
        logger.debug(f"🔍 [TRACING] Completed trace {trace.trace_id} with {trace.span_count} spans")
    
    def _calculate_critical_path(self, trace: Trace) -> List[str]:
        """Calculate critical path through trace spans."""
        # Simple implementation - find longest path
        spans_by_id = {span.span_id: span for span in trace.spans}
        
        def find_longest_path(span_id: str, visited: Set[str]) -> List[str]:
            if span_id in visited:
                return []
            
            span = spans_by_id.get(span_id)
            if not span or span.duration_ms is None:
                return []
            
            visited.add(span_id)
            
            # Find child spans
            children = [s for s in trace.spans if s.parent_span_id == span_id]
            
            if not children:
                return [span.operation_name]
            
            # Find child with longest path
            longest_child_path = []
            for child in children:
                child_path = find_longest_path(child.span_id, visited.copy())
                if len(child_path) > len(longest_child_path):
                    longest_child_path = child_path
            
            return [span.operation_name] + longest_child_path
        
        if trace.root_span:
            return find_longest_path(trace.root_span.span_id, set())
        
        return []
    
    async def _cleanup_loop(self):
        """Cleanup old traces and spans."""
        while True:
            try:
                await self._cleanup_old_traces()
                await asyncio.sleep(300)  # Every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [TRACING] Cleanup error: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_old_traces(self):
        """Clean up old traces that may have been abandoned."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.trace_timeout_minutes)
        
        # Find old traces
        old_traces = [
            trace_id for trace_id, trace in self.active_traces.items()
            if trace.root_span.start_time < cutoff_time
        ]
        
        # Clean up old spans
        old_spans = [
            span_id for span_id, span in self.active_spans.items()
            if span.start_time < cutoff_time
        ]
        
        # Remove old traces and spans
        for trace_id in old_traces:
            trace = self.active_traces[trace_id]
            logger.warning(f"⚠️ [TRACING] Cleaning up abandoned trace {trace_id}")
            self._finalize_trace(trace)
            del self.active_traces[trace_id]
        
        for span_id in old_spans:
            span = self.active_spans[span_id]
            logger.warning(f"⚠️ [TRACING] Cleaning up abandoned span {span_id}")
            self.finish_span(span, SpanStatus.TIMEOUT)
        
        if old_traces or old_spans:
            logger.info(f"🧹 [TRACING] Cleaned up {len(old_traces)} traces and {len(old_spans)} spans")
    
    def _should_sample(self) -> bool:
        """Determine if this trace should be sampled."""
        import random
        return random.random() < self.sampling_rate
    
    def _generate_trace_id(self) -> str:
        """Generate unique trace ID."""
        return f"trace_{uuid.uuid4().hex[:16]}"
    
    def _generate_span_id(self) -> str:
        """Generate unique span ID."""
        return f"span_{uuid.uuid4().hex[:12]}"
    
    def _create_noop_trace_context(self, trace_id: str) -> TraceContext:
        """Create no-op trace context."""
        return TraceContext(trace_id=trace_id, sampling_decision=False)
    
    def _create_noop_span(self, trace_id: str) -> Span:
        """Create no-op span."""
        return Span(
            span_id="noop",
            trace_id=trace_id,
            parent_span_id=None,
            operation_name="noop",
            service_name=self.service_name,
            span_type=SpanType.INTERNAL_SERVICE_CALL,
            start_time=datetime.now(timezone.utc)
        )
    
    # Public API methods
    
    def get_active_traces_summary(self) -> Dict[str, Any]:
        """Get summary of active traces."""
        return {
            "active_trace_count": len(self.active_traces),
            "active_span_count": len(self.active_spans),
            "traces": [
                {
                    "trace_id": trace.trace_id,
                    "root_operation": trace.root_span.operation_name,
                    "span_count": len(trace.spans),
                    "services": list(trace.services),
                    "duration_so_far_ms": trace.total_duration_ms,
                    "error_count": trace.error_count
                }
                for trace in self.active_traces.values()
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_trace_details(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific trace."""
        # Check active traces first
        trace = self.active_traces.get(trace_id)
        if trace:
            return trace.to_dict()
        
        # Check completed traces in analyzer
        trace = self.trace_analyzer.completed_traces.get(trace_id)
        if trace:
            return trace.to_dict()
        
        return None
    
    def get_performance_insights(self) -> Dict[str, Any]:
        """Get performance insights from trace analysis."""
        return self.trace_analyzer.get_performance_insights()
    
    def set_sampling_rate(self, rate: float):
        """Set trace sampling rate (0.0 to 1.0)."""
        self.sampling_rate = max(0.0, min(1.0, rate))
        logger.info(f"🔍 [TRACING] Sampling rate set to {self.sampling_rate * 100}%")


# Global distributed tracing system
distributed_tracing_system = DistributedTracingSystem()


# Convenience context managers and decorators

class trace_operation:
    """Context manager for tracing operations."""
    
    def __init__(self, operation_name: str, span_type: SpanType = SpanType.BUSINESS_LOGIC, service_name: str = None):
        self.operation_name = operation_name
        self.span_type = span_type
        self.service_name = service_name
        self.context = None
        self.span = None
    
    async def __aenter__(self):
        parent_context = trace_context.get()
        self.context, self.span = distributed_tracing_system.start_trace(
            self.operation_name, 
            self.span_type, 
            parent_context
        )
        return self.span
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            status = SpanStatus.ERROR if exc_type else SpanStatus.OK
            error = str(exc_val) if exc_val else None
            distributed_tracing_system.finish_span(self.span, status, error)


def traced_operation(operation_name: str, span_type: SpanType = SpanType.BUSINESS_LOGIC):
    """Decorator for tracing function calls."""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            async def wrapper(*args, **kwargs):
                async with trace_operation(operation_name, span_type) as span:
                    # Add function details as tags
                    distributed_tracing_system.add_span_tag("function.name", func.__name__, span)
                    distributed_tracing_system.add_span_tag("function.module", func.__module__, span)
                    return await func(*args, **kwargs)
        else:
            def wrapper(*args, **kwargs):
                # For sync functions, create a simple span
                parent_context = trace_context.get()
                context, span = distributed_tracing_system.start_trace(
                    operation_name, span_type, parent_context
                )
                
                try:
                    distributed_tracing_system.add_span_tag("function.name", func.__name__, span)
                    distributed_tracing_system.add_span_tag("function.module", func.__module__, span)
                    result = func(*args, **kwargs)
                    distributed_tracing_system.finish_span(span, SpanStatus.OK)
                    return result
                except Exception as e:
                    distributed_tracing_system.finish_span(span, SpanStatus.ERROR, str(e))
                    raise
        
        return wrapper
    return decorator


# Convenience functions

async def start_tracing_system():
    """Start the distributed tracing system."""
    await distributed_tracing_system.start()


async def stop_tracing_system():
    """Stop the distributed tracing system."""
    await distributed_tracing_system.stop()


def get_current_trace_context() -> Optional[TraceContext]:
    """Get current trace context."""
    return trace_context.get()


def get_current_span() -> Optional[Span]:
    """Get current span."""
    return span_context.get()


def add_trace_tag(key: str, value: str):
    """Add tag to current span."""
    distributed_tracing_system.add_span_tag(key, value)


def add_trace_log(message: str, level: str = "info"):
    """Add log to current span."""
    distributed_tracing_system.add_span_log(message, level)