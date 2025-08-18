"""
Circuit Breaker Pattern Implementation for Authorization Services
Provides fault tolerance and graceful degradation for authorization failures.
"""
import asyncio
import time
from typing import Optional, Dict, Any, Callable, Union, List
from datetime import datetime, timedelta, timezone
from enum import Enum
from dataclasses import dataclass, field
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Circuit breaker is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5  # Number of failures before opening circuit
    recovery_timeout: int = 60  # Seconds to wait before trying half-open
    success_threshold: int = 3  # Successful calls needed to close circuit from half-open
    timeout: float = 30.0  # Request timeout in seconds
    expected_exception: Union[type, tuple] = Exception  # Exception types that count as failures
    fallback_function: Optional[Callable] = None  # Fallback function when circuit is open
    
    # Sliding window configuration
    window_size: int = 60  # Sliding window size in seconds
    minimum_requests: int = 10  # Minimum requests in window before considering failure rate


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    circuit_opened_count: int = 0
    circuit_closed_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    average_response_time: float = 0.0
    
    # Sliding window metrics
    recent_requests: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_request(self, success: bool, response_time: float, timestamp: Optional[datetime] = None):
        """Add a request to metrics."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        self.total_requests += 1
        
        if success:
            self.successful_requests += 1
            self.last_success_time = timestamp
        else:
            self.failed_requests += 1
            self.last_failure_time = timestamp
        
        # Update average response time
        if self.total_requests == 1:
            self.average_response_time = response_time
        else:
            self.average_response_time = (
                (self.average_response_time * (self.total_requests - 1) + response_time) / 
                self.total_requests
            )
        
        # Add to sliding window
        self.recent_requests.append({
            'timestamp': timestamp,
            'success': success,
            'response_time': response_time
        })
        
        # Clean old requests from sliding window
        cutoff_time = timestamp - timedelta(seconds=60)  # Keep last 60 seconds
        self.recent_requests = [
            req for req in self.recent_requests 
            if req['timestamp'] > cutoff_time
        ]
    
    def get_failure_rate(self, window_seconds: int = 60) -> float:
        """Get failure rate in the specified window."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        recent = [req for req in self.recent_requests if req['timestamp'] > cutoff_time]
        
        if len(recent) == 0:
            return 0.0
        
        failed = sum(1 for req in recent if not req['success'])
        return failed / len(recent)
    
    def get_request_count(self, window_seconds: int = 60) -> int:
        """Get request count in the specified window."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        return len([req for req in self.recent_requests if req['timestamp'] > cutoff_time])


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    
    def __init__(self, message: str, circuit_name: str, state: CircuitBreakerState):
        super().__init__(message)
        self.circuit_name = circuit_name
        self.state = state


class AuthCircuitBreaker:
    """
    Circuit breaker specifically designed for authorization services.
    Provides fault tolerance and graceful degradation for auth operations.
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.metrics = CircuitBreakerMetrics()
        self.last_state_change = datetime.now(timezone.utc)
        self.half_open_success_count = 0
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs):
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: The function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            Result of the function call
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Original exception from the function
        """
        async with self._lock:
            await self._update_state()
        
        if self.state == CircuitBreakerState.OPEN:
            # Circuit is open, check if fallback is available
            if self.config.fallback_function:
                logger.warning(f"🔥 [CIRCUIT-BREAKER] {self.name} is OPEN, using fallback")
                return await self._execute_fallback(*args, **kwargs)
            else:
                logger.error(f"🔥 [CIRCUIT-BREAKER] {self.name} is OPEN, no fallback available")
                raise CircuitBreakerError(
                    f"Circuit breaker {self.name} is OPEN",
                    self.name,
                    self.state
                )
        
        # Circuit is CLOSED or HALF_OPEN, attempt the call
        start_time = time.time()
        success = False
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_async(func, *args, **kwargs),
                timeout=self.config.timeout
            )
            success = True
            
            async with self._lock:
                await self._record_success(time.time() - start_time)
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"❌ [CIRCUIT-BREAKER] {self.name} timeout after {self.config.timeout}s")
            async with self._lock:
                self.metrics.timeout_requests += 1
                await self._record_failure(time.time() - start_time, "timeout")
            raise
            
        except Exception as e:
            # Check if this exception should count as a failure
            if isinstance(e, self.config.expected_exception):
                async with self._lock:
                    await self._record_failure(time.time() - start_time, str(e))
            raise
    
    async def _execute_async(self, func: Callable, *args, **kwargs):
        """Execute function, handling both sync and async functions."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    
    async def _execute_fallback(self, *args, **kwargs):
        """Execute fallback function."""
        if asyncio.iscoroutinefunction(self.config.fallback_function):
            return await self.config.fallback_function(*args, **kwargs)
        else:
            return self.config.fallback_function(*args, **kwargs)
    
    async def _record_success(self, response_time: float):
        """Record a successful request."""
        self.metrics.add_request(True, response_time)
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_success_count += 1
            logger.info(
                f"✅ [CIRCUIT-BREAKER] {self.name} HALF_OPEN success "
                f"({self.half_open_success_count}/{self.config.success_threshold})"
            )
            
            if self.half_open_success_count >= self.config.success_threshold:
                await self._close_circuit()
    
    async def _record_failure(self, response_time: float, error_msg: str):
        """Record a failed request."""
        self.metrics.add_request(False, response_time)
        
        logger.warning(f"❌ [CIRCUIT-BREAKER] {self.name} failure: {error_msg}")
        
        # Check if we should open the circuit
        await self._check_failure_threshold()
    
    async def _check_failure_threshold(self):
        """Check if failure threshold is exceeded and open circuit if needed."""
        failure_rate = self.metrics.get_failure_rate(self.config.window_size)
        request_count = self.metrics.get_request_count(self.config.window_size)
        
        # Only consider opening if we have minimum requests
        if request_count < self.config.minimum_requests:
            return
        
        # Open circuit if failure rate exceeds threshold
        if failure_rate >= (self.config.failure_threshold / self.config.minimum_requests):
            await self._open_circuit()
    
    async def _open_circuit(self):
        """Open the circuit breaker."""
        if self.state != CircuitBreakerState.OPEN:
            old_state = self.state
            self.state = CircuitBreakerState.OPEN
            self.last_state_change = datetime.now(timezone.utc)
            self.metrics.circuit_opened_count += 1
            
            logger.critical(
                f"🔥 [CIRCUIT-BREAKER] {self.name} OPENED "
                f"(was {old_state.value}, failure_rate={self.metrics.get_failure_rate():.2%})"
            )
    
    async def _close_circuit(self):
        """Close the circuit breaker."""
        if self.state != CircuitBreakerState.CLOSED:
            old_state = self.state
            self.state = CircuitBreakerState.CLOSED
            self.last_state_change = datetime.now(timezone.utc)
            self.half_open_success_count = 0
            self.metrics.circuit_closed_count += 1
            
            logger.info(
                f"✅ [CIRCUIT-BREAKER] {self.name} CLOSED "
                f"(was {old_state.value})"
            )
    
    async def _update_state(self):
        """Update circuit breaker state based on current conditions."""
        now = datetime.now(timezone.utc)
        
        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if (now - self.last_state_change).total_seconds() >= self.config.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.last_state_change = now
                self.half_open_success_count = 0
                
                logger.info(f"🔄 [CIRCUIT-BREAKER] {self.name} -> HALF_OPEN (recovery attempt)")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state and metrics."""
        return {
            'name': self.name,
            'state': self.state.value,
            'last_state_change': self.last_state_change.isoformat(),
            'metrics': {
                'total_requests': self.metrics.total_requests,
                'successful_requests': self.metrics.successful_requests,
                'failed_requests': self.metrics.failed_requests,
                'timeout_requests': self.metrics.timeout_requests,
                'circuit_opened_count': self.metrics.circuit_opened_count,
                'circuit_closed_count': self.metrics.circuit_closed_count,
                'failure_rate': self.metrics.get_failure_rate(),
                'recent_request_count': self.metrics.get_request_count(),
                'average_response_time': self.metrics.average_response_time,
                'last_failure_time': self.metrics.last_failure_time.isoformat() if self.metrics.last_failure_time else None,
                'last_success_time': self.metrics.last_success_time.isoformat() if self.metrics.last_success_time else None
            },
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'recovery_timeout': self.config.recovery_timeout,
                'success_threshold': self.config.success_threshold,
                'timeout': self.config.timeout,
                'window_size': self.config.window_size,
                'minimum_requests': self.config.minimum_requests
            }
        }
    
    async def reset(self):
        """Reset circuit breaker to initial state."""
        async with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self.metrics = CircuitBreakerMetrics()
            self.last_state_change = datetime.now(timezone.utc)
            self.half_open_success_count = 0
            
            logger.info(f"🔄 [CIRCUIT-BREAKER] {self.name} RESET")


class AuthCircuitBreakerManager:
    """
    Manager for multiple circuit breakers used in authorization system.
    """
    
    def __init__(self):
        self.circuit_breakers: Dict[str, AuthCircuitBreaker] = {}
        self.default_configs: Dict[str, CircuitBreakerConfig] = {
            'database': CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60,
                success_threshold=3,
                timeout=10.0,
                fallback_function=self._database_fallback
            ),
            'token_validation': CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=30,
                success_threshold=2,
                timeout=5.0,
                fallback_function=self._token_validation_fallback
            ),
            'external_auth': CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=45,
                success_threshold=2,
                timeout=15.0,
                fallback_function=self._external_auth_fallback
            ),
            'user_lookup': CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=30,
                success_threshold=3,
                timeout=8.0,
                fallback_function=self._user_lookup_fallback
            ),
            'permission_check': CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=20,
                success_threshold=2,
                timeout=5.0,
                fallback_function=self._permission_check_fallback
            )
        }
    
    def get_circuit_breaker(
        self, 
        name: str, 
        config: Optional[CircuitBreakerConfig] = None
    ) -> AuthCircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self.circuit_breakers:
            # Use provided config or default config for the name
            cb_config = config or self.default_configs.get(name, CircuitBreakerConfig())
            self.circuit_breakers[name] = AuthCircuitBreaker(name, cb_config)
            
            logger.info(f"📋 [CIRCUIT-BREAKER] Created circuit breaker: {name}")
        
        return self.circuit_breakers[name]
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get states of all circuit breakers."""
        return {name: cb.get_state() for name, cb in self.circuit_breakers.items()}
    
    async def reset_all(self):
        """Reset all circuit breakers."""
        for cb in self.circuit_breakers.values():
            await cb.reset()
    
    async def reset_circuit_breaker(self, name: str):
        """Reset a specific circuit breaker."""
        if name in self.circuit_breakers:
            await self.circuit_breakers[name].reset()
    
    # Fallback functions for different services
    
    async def _database_fallback(self, *args, **kwargs):
        """Fallback for database operations."""
        logger.warning("🔄 [FALLBACK] Using database fallback (cached data or basic response)")
        # In production, this would return cached data or a basic response
        return None
    
    async def _token_validation_fallback(self, *args, **kwargs):
        """Fallback for token validation."""
        logger.warning("🔄 [FALLBACK] Using token validation fallback (deny access)")
        # For security, fallback is to deny access when token validation fails
        return False
    
    async def _external_auth_fallback(self, *args, **kwargs):
        """Fallback for external authentication."""
        logger.warning("🔄 [FALLBACK] Using external auth fallback (local validation)")
        # Fallback to local token validation or cached auth state
        return False
    
    async def _user_lookup_fallback(self, *args, **kwargs):
        """Fallback for user lookup."""
        logger.warning("🔄 [FALLBACK] Using user lookup fallback (basic user data)")
        # Return basic user data from token or cache
        return None
    
    async def _permission_check_fallback(self, *args, **kwargs):
        """Fallback for permission checks."""
        logger.warning("🔄 [FALLBACK] Using permission check fallback (deny access)")
        # For security, fallback is to deny access when permission check fails
        return False


# Global circuit breaker manager
circuit_breaker_manager = AuthCircuitBreakerManager()


# Decorator for easy circuit breaker usage
def with_circuit_breaker(
    name: str, 
    config: Optional[CircuitBreakerConfig] = None
):
    """Decorator to add circuit breaker protection to functions."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cb = circuit_breaker_manager.get_circuit_breaker(name, config)
            return await cb.call(func, *args, **kwargs)
        return wrapper
    return decorator


# Context manager for circuit breaker operations
@asynccontextmanager
async def circuit_breaker_context(
    name: str, 
    config: Optional[CircuitBreakerConfig] = None
):
    """Context manager for circuit breaker operations."""
    cb = circuit_breaker_manager.get_circuit_breaker(name, config)
    
    # Check circuit state before entering
    if cb.state == CircuitBreakerState.OPEN:
        if cb.config.fallback_function:
            logger.warning(f"🔥 [CIRCUIT-BREAKER] {name} is OPEN in context manager")
            yield cb.config.fallback_function
        else:
            raise CircuitBreakerError(
                f"Circuit breaker {name} is OPEN",
                name,
                cb.state
            )
    else:
        yield cb


# Convenience functions for common authorization circuit breakers

async def with_database_circuit_breaker(func, *args, **kwargs):
    """Execute database operation with circuit breaker."""
    cb = circuit_breaker_manager.get_circuit_breaker('database')
    return await cb.call(func, *args, **kwargs)


async def with_token_validation_circuit_breaker(func, *args, **kwargs):
    """Execute token validation with circuit breaker."""
    cb = circuit_breaker_manager.get_circuit_breaker('token_validation')
    return await cb.call(func, *args, **kwargs)


async def with_external_auth_circuit_breaker(func, *args, **kwargs):
    """Execute external auth operation with circuit breaker."""
    cb = circuit_breaker_manager.get_circuit_breaker('external_auth')
    return await cb.call(func, *args, **kwargs)


async def with_user_lookup_circuit_breaker(func, *args, **kwargs):
    """Execute user lookup with circuit breaker."""
    cb = circuit_breaker_manager.get_circuit_breaker('user_lookup')
    return await cb.call(func, *args, **kwargs)


async def with_permission_check_circuit_breaker(func, *args, **kwargs):
    """Execute permission check with circuit breaker."""
    cb = circuit_breaker_manager.get_circuit_breaker('permission_check')
    return await cb.call(func, *args, **kwargs)