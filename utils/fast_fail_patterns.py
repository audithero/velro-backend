"""
Fast-fail patterns and error handling optimizations.
Implements intelligent error detection and early failure mechanisms to improve API response times.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque
import re

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for fast-fail decisions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureType(Enum):
    """Types of failures that should trigger fast-fail."""
    AUTHENTICATION_EXPIRED = "auth_expired"
    RATE_LIMIT_EXCEEDED = "rate_limit"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    INVALID_INPUT = "invalid_input"
    NETWORK_TIMEOUT = "network_timeout"
    SERVICE_UNAVAILABLE = "service_unavailable"
    QUOTA_EXCEEDED = "quota_exceeded"


@dataclass
class ErrorPattern:
    """Error pattern for fast-fail detection."""
    pattern: str
    failure_type: FailureType
    severity: ErrorSeverity
    should_retry: bool
    fast_fail_threshold: float  # seconds
    cache_duration: int  # seconds


@dataclass
class FailureEvent:
    """Failure event record."""
    timestamp: datetime
    failure_type: FailureType
    error_message: str
    response_time: float
    user_id: Optional[str] = None
    endpoint: Optional[str] = None


class FastFailPatternMatcher:
    """Intelligent pattern matcher for fast-fail scenarios."""
    
    def __init__(self):
        self.error_patterns = self._initialize_error_patterns()
        self.failure_history: deque = deque(maxlen=1000)
        self.failure_cache: Dict[str, datetime] = {}
        self.error_counters = defaultdict(int)
        
        # Circuit breaker states per error type
        self.circuit_states: Dict[FailureType, str] = {}  # open, closed, half-open
        self.circuit_failure_counts: Dict[FailureType, int] = defaultdict(int)
        self.circuit_last_failures: Dict[FailureType, float] = {}
        
        # Performance thresholds
        self.slow_response_threshold = 3.0  # 3 seconds
        self.critical_response_threshold = 10.0  # 10 seconds
        
    def _initialize_error_patterns(self) -> List[ErrorPattern]:
        """Initialize predefined error patterns for fast-fail detection."""
        return [
            # Authentication errors
            ErrorPattern(
                pattern=r"(invalid|expired|unauthorized|forbidden|authentication|token)",
                failure_type=FailureType.AUTHENTICATION_EXPIRED,
                severity=ErrorSeverity.HIGH,
                should_retry=False,
                fast_fail_threshold=0.1,  # Fail immediately
                cache_duration=300  # Cache for 5 minutes
            ),
            
            # Rate limiting
            ErrorPattern(
                pattern=r"(rate.?limit|too.?many.?requests|429)",
                failure_type=FailureType.RATE_LIMIT_EXCEEDED,
                severity=ErrorSeverity.MEDIUM,
                should_retry=True,
                fast_fail_threshold=0.5,
                cache_duration=60
            ),
            
            # Resource unavailable
            ErrorPattern(
                pattern=r"(not.?found|404|resource.?not.?available|does.?not.?exist)",
                failure_type=FailureType.RESOURCE_UNAVAILABLE,
                severity=ErrorSeverity.MEDIUM,
                should_retry=False,
                fast_fail_threshold=0.2,
                cache_duration=180
            ),
            
            # Invalid input
            ErrorPattern(
                pattern=r"(invalid.?input|validation.?error|bad.?request|400|malformed)",
                failure_type=FailureType.INVALID_INPUT,
                severity=ErrorSeverity.LOW,
                should_retry=False,
                fast_fail_threshold=0.1,
                cache_duration=30
            ),
            
            # Network timeouts
            ErrorPattern(
                pattern=r"(timeout|timed.?out|connection.?reset|network.?error)",
                failure_type=FailureType.NETWORK_TIMEOUT,
                severity=ErrorSeverity.HIGH,
                should_retry=True,
                fast_fail_threshold=1.0,
                cache_duration=120
            ),
            
            # Service unavailable
            ErrorPattern(
                pattern=r"(service.?unavailable|503|502|down|maintenance)",
                failure_type=FailureType.SERVICE_UNAVAILABLE,
                severity=ErrorSeverity.CRITICAL,
                should_retry=True,
                fast_fail_threshold=2.0,
                cache_duration=300
            ),
            
            # Quota/Credit errors
            ErrorPattern(
                pattern=r"(insufficient.?credits|quota.?exceeded|payment.?required|402)",
                failure_type=FailureType.QUOTA_EXCEEDED,
                severity=ErrorSeverity.MEDIUM,
                should_retry=False,
                fast_fail_threshold=0.1,
                cache_duration=600  # 10 minutes
            )
        ]
    
    async def should_fast_fail(
        self, 
        error_message: str, 
        response_time: float = 0,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None
    ) -> tuple[bool, Optional[FailureType], str]:
        """
        Determine if request should fast-fail based on error patterns and history.
        
        Returns:
            (should_fail, failure_type, reason)
        """
        start_time = time.time()
        
        # Check for pattern matches
        matched_pattern = self._match_error_pattern(error_message.lower())
        
        if matched_pattern:
            failure_type = matched_pattern.failure_type
            
            # Check if we should fail immediately based on pattern
            if response_time > matched_pattern.fast_fail_threshold:
                reason = f"Pattern match: {failure_type.value} (response_time: {response_time:.2f}s > {matched_pattern.fast_fail_threshold}s)"
                
                # Record failure event
                await self._record_failure_event(
                    failure_type=failure_type,
                    error_message=error_message,
                    response_time=response_time,
                    user_id=user_id,
                    endpoint=endpoint
                )
                
                # Check circuit breaker state
                circuit_decision = await self._check_circuit_breaker(failure_type)
                if circuit_decision:
                    reason += f" + Circuit breaker: {circuit_decision}"
                
                logger.warning(f"⚡ [FAST-FAIL] {reason}")
                return True, failure_type, reason
        
        # Check for slow response patterns (even without error pattern match)
        if response_time > self.critical_response_threshold:
            failure_type = FailureType.NETWORK_TIMEOUT
            reason = f"Critical response time: {response_time:.2f}s > {self.critical_response_threshold}s"
            
            await self._record_failure_event(
                failure_type=failure_type,
                error_message=f"Slow response: {error_message}",
                response_time=response_time,
                user_id=user_id,
                endpoint=endpoint
            )
            
            logger.warning(f"🐌 [FAST-FAIL] {reason}")
            return True, failure_type, reason
        
        # Check cached failures for this specific context
        cache_key = self._generate_cache_key(error_message, user_id, endpoint)
        if cache_key in self.failure_cache:
            cached_time = self.failure_cache[cache_key]
            if datetime.utcnow() - cached_time < timedelta(seconds=60):
                reason = f"Cached recent failure for context: {cache_key[:50]}..."
                logger.debug(f"💾 [FAST-FAIL] {reason}")
                return True, FailureType.RESOURCE_UNAVAILABLE, reason
        
        analysis_time = time.time() - start_time
        logger.debug(f"🔍 [FAST-FAIL] Analysis completed in {analysis_time:.3f}s: no fast-fail needed")
        return False, None, "No fast-fail conditions met"
    
    def _match_error_pattern(self, error_message: str) -> Optional[ErrorPattern]:
        """Match error message against predefined patterns."""
        for pattern in self.error_patterns:
            if re.search(pattern.pattern, error_message, re.IGNORECASE):
                return pattern
        return None
    
    async def _record_failure_event(
        self,
        failure_type: FailureType,
        error_message: str,
        response_time: float,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None
    ):
        """Record failure event for pattern analysis."""
        event = FailureEvent(
            timestamp=datetime.utcnow(),
            failure_type=failure_type,
            error_message=error_message[:200],  # Truncate long messages
            response_time=response_time,
            user_id=user_id,
            endpoint=endpoint
        )
        
        self.failure_history.append(event)
        self.error_counters[failure_type] += 1
        
        # Cache failure for fast lookup
        cache_key = self._generate_cache_key(error_message, user_id, endpoint)
        self.failure_cache[cache_key] = datetime.utcnow()
        
        # Update circuit breaker state
        await self._update_circuit_breaker(failure_type)
    
    async def _check_circuit_breaker(self, failure_type: FailureType) -> Optional[str]:
        """Check circuit breaker state for failure type."""
        state = self.circuit_states.get(failure_type, "closed")
        
        if state == "open":
            # Check if we should try half-open
            last_failure = self.circuit_last_failures.get(failure_type, 0)
            if time.time() - last_failure > 30:  # 30 second timeout
                self.circuit_states[failure_type] = "half-open"
                return "half-open (testing recovery)"
            return "open (failing fast)"
        
        return None
    
    async def _update_circuit_breaker(self, failure_type: FailureType):
        """Update circuit breaker based on failure."""
        self.circuit_failure_counts[failure_type] += 1
        self.circuit_last_failures[failure_type] = time.time()
        
        # Open circuit if too many failures
        if self.circuit_failure_counts[failure_type] >= 5:
            if self.circuit_states.get(failure_type) != "open":
                self.circuit_states[failure_type] = "open"
                logger.warning(f"🔴 [CIRCUIT-BREAKER] Opened for {failure_type.value}")
    
    def record_success(self, failure_type: FailureType):
        """Record successful operation for circuit breaker recovery."""
        if self.circuit_states.get(failure_type) == "half-open":
            self.circuit_states[failure_type] = "closed"
            self.circuit_failure_counts[failure_type] = 0
            logger.info(f"🟢 [CIRCUIT-BREAKER] Closed for {failure_type.value}")
    
    def _generate_cache_key(
        self, 
        error_message: str, 
        user_id: Optional[str], 
        endpoint: Optional[str]
    ) -> str:
        """Generate cache key for failure context."""
        key_parts = [
            error_message[:50],  # First 50 chars of error
            user_id or "anonymous",
            endpoint or "unknown"
        ]
        return "|".join(key_parts)
    
    def get_failure_statistics(self) -> Dict[str, Any]:
        """Get failure statistics and analysis."""
        now = datetime.utcnow()
        recent_failures = [
            event for event in self.failure_history
            if now - event.timestamp < timedelta(hours=1)
        ]
        
        failure_by_type = defaultdict(int)
        avg_response_times = defaultdict(list)
        
        for event in recent_failures:
            failure_by_type[event.failure_type.value] += 1
            avg_response_times[event.failure_type.value].append(event.response_time)
        
        # Calculate averages
        avg_times = {}
        for failure_type, times in avg_response_times.items():
            if times:
                avg_times[failure_type] = sum(times) / len(times)
        
        return {
            "total_failures_1h": len(recent_failures),
            "failure_by_type": dict(failure_by_type),
            "average_response_times": avg_times,
            "circuit_breaker_states": {
                failure_type.value: state 
                for failure_type, state in self.circuit_states.items()
            },
            "cache_entries": len(self.failure_cache),
            "patterns_configured": len(self.error_patterns)
        }
    
    async def cleanup_old_entries(self):
        """Clean up old cache entries and failure history."""
        # Clean cache entries older than 10 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=10)
        expired_keys = [
            key for key, timestamp in self.failure_cache.items()
            if timestamp < cutoff_time
        ]
        
        for key in expired_keys:
            del self.failure_cache[key]
        
        logger.debug(f"🧹 [FAST-FAIL] Cleaned {len(expired_keys)} expired cache entries")


# Global fast-fail pattern matcher
fast_fail_matcher = FastFailPatternMatcher()


# Decorator for fast-fail protection
def fast_fail_protection(
    endpoint_name: str = None,
    max_response_time: float = 5.0
):
    """Decorator to add fast-fail protection to API endpoints."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                response_time = time.time() - start_time
                
                # Record successful operation if it was previously failing
                # This would need to be implemented based on specific requirements
                
                return result
                
            except Exception as e:
                response_time = time.time() - start_time
                error_message = str(e)
                
                # Get user context if available
                user_id = None
                if args and hasattr(args[0], 'state') and hasattr(args[0].state, 'user_id'):
                    user_id = str(args[0].state.user_id)
                
                # Check if should fast-fail
                should_fail, failure_type, reason = await fast_fail_matcher.should_fast_fail(
                    error_message=error_message,
                    response_time=response_time,
                    user_id=user_id,
                    endpoint=endpoint_name or func.__name__
                )
                
                if should_fail:
                    logger.warning(f"⚡ [FAST-FAIL] {endpoint_name or func.__name__}: {reason}")
                    # Could customize the error response based on failure type
                    raise HTTPException(
                        status_code=503,
                        detail=f"Service temporarily unavailable: {failure_type.value if failure_type else 'unknown'}"
                    )
                
                # Re-raise original exception if not fast-failing
                raise
        
        return wrapper
    return decorator