"""
MCP Integration Patterns for Velro Platform

Production-ready MCP integration patterns with:
1. Advanced error handling and recovery
2. Exponential backoff retry mechanisms
3. Data transformation utilities
4. Connection pooling
5. Validation schemas
6. Circuit breaker patterns
7. Performance monitoring
8. Security best practices
"""

import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional, List, Union, Callable, TypeVar, Generic
from datetime import datetime, timedelta
from functools import wraps, lru_cache
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel, Field, validator
import hashlib
import ssl
from urllib.parse import urlparse
import aiohttp
from asyncio import Semaphore, Queue
import weakref

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Configuration and Error Types
class MCPErrorCode(Enum):
    """Standardized MCP error codes"""
    AUTHENTICATION_ERROR = "AUTH_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT"
    SERVICE_UNAVAILABLE = "SERVICE_DOWN"
    TIMEOUT_ERROR = "TIMEOUT"
    VALIDATION_ERROR = "VALIDATION"
    CONNECTION_ERROR = "CONNECTION"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_OPEN"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    DATA_TRANSFORMATION_ERROR = "TRANSFORM_ERROR"
    SCHEMA_VALIDATION_ERROR = "SCHEMA_ERROR"


class MCPIntegrationError(Exception):
    """Enhanced MCP integration error with detailed context"""
    
    def __init__(
        self,
        message: str,
        code: MCPErrorCode,
        service: str = None,
        operation: str = None,
        details: Optional[Dict] = None,
        retryable: bool = True,
        retry_after: Optional[int] = None
    ):
        self.message = message
        self.code = code
        self.service = service
        self.operation = operation
        self.details = details or {}
        self.retryable = retryable
        self.retry_after = retry_after
        self.timestamp = datetime.utcnow()
        
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/response"""
        return {
            "message": self.message,
            "code": self.code.value,
            "service": self.service,
            "operation": self.operation,
            "details": self.details,
            "retryable": self.retryable,
            "retry_after": self.retry_after,
            "timestamp": self.timestamp.isoformat()
        }


# Validation Schemas
class MCPRequestSchema(BaseModel):
    """Base schema for MCP requests"""
    service: str = Field(..., description="Target MCP service")
    operation: str = Field(..., description="Operation to perform")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timeout: Optional[int] = Field(default=30, ge=1, le=300)
    priority: Optional[int] = Field(default=5, ge=1, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('service')
    def validate_service(cls, v):
        allowed_services = {'supabase', 'railway', 'claude-flow', 'ruv-swarm'}
        if v not in allowed_services:
            raise ValueError(f"Service must be one of {allowed_services}")
        return v


class MCPResponseSchema(BaseModel):
    """Base schema for MCP responses"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    execution_time: float
    timestamp: datetime
    service: str
    operation: str
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        },
        "protected_namespaces": ()
    }


class SupabaseQuerySchema(BaseModel):
    """Schema for Supabase query operations"""
    query: str = Field(..., min_length=1, max_length=10000)
    parameters: Optional[Dict[str, Any]] = None
    transaction: bool = False
    timeout: Optional[int] = Field(default=30, ge=1, le=300)
    
    @validator('query')
    def validate_query(cls, v):
        # Basic SQL injection prevention
        dangerous_keywords = ['drop', 'delete', 'truncate', 'alter']
        v_lower = v.lower()
        if any(keyword in v_lower for keyword in dangerous_keywords):
            if not v_lower.startswith('select'):
                raise ValueError("Potentially dangerous SQL operation detected")
        return v


class RailwayDeploymentSchema(BaseModel):
    """Schema for Railway deployment operations"""
    project_id: str = Field(..., pattern=r'^[a-zA-Z0-9-_]+$')
    service_id: str = Field(..., pattern=r'^[a-zA-Z0-9-_]+$')
    environment_id: str = Field(..., pattern=r'^[a-zA-Z0-9-_]+$')
    commit_sha: Optional[str] = Field(None, pattern=r'^[a-f0-9]{40}$')
    variables: Optional[Dict[str, str]] = None


# Retry Configuration
@dataclass
class RetryConfig:
    """Configuration for retry mechanisms"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_errors: List[MCPErrorCode] = field(default_factory=lambda: [
        MCPErrorCode.RATE_LIMIT_ERROR,
        MCPErrorCode.SERVICE_UNAVAILABLE,
        MCPErrorCode.TIMEOUT_ERROR,
        MCPErrorCode.CONNECTION_ERROR
    ])


# Circuit Breaker Implementation
@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3
    success_threshold: int = 2


class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Advanced circuit breaker with monitoring"""
    
    def __init__(self, config: CircuitBreakerConfig, name: str = "default"):
        self.config = config
        self.name = name
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        async with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.half_open_calls = 0
                    logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
                else:
                    raise MCPIntegrationError(
                        f"Circuit breaker {self.name} is OPEN",
                        MCPErrorCode.CIRCUIT_BREAKER_OPEN,
                        retryable=False
                    )
            
            try:
                result = await func(*args, **kwargs)
                await self._on_success()
                return result
            except Exception as e:
                await self._on_failure()
                raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset"""
        if self.last_failure_time is None:
            return True
        
        time_since_failure = datetime.utcnow() - self.last_failure_time
        return time_since_failure.total_seconds() >= self.config.recovery_timeout
    
    async def _on_success(self):
        """Handle successful operation"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"Circuit breaker {self.name} reset to CLOSED")
        else:
            self.failure_count = 0
    
    async def _on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker {self.name} opened after half-open failure")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker {self.name} opened after {self.failure_count} failures")


# Connection Pool Implementation
class MCPConnection:
    """Individual MCP connection with health tracking"""
    
    def __init__(self, service: str, connection_id: str):
        self.service = service
        self.connection_id = connection_id
        self.created_at = datetime.utcnow()
        self.last_used = datetime.utcnow()
        self.is_healthy = True
        self.use_count = 0
        self.session = None
    
    async def initialize(self):
        """Initialize connection session"""
        connector = aiohttp.TCPConnector(
            limit=10,
            ssl=ssl.create_default_context()
        )
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
    
    async def close(self):
        """Close connection and cleanup"""
        if self.session:
            await self.session.close()
        self.is_healthy = False
    
    def mark_used(self):
        """Mark connection as used"""
        self.last_used = datetime.utcnow()
        self.use_count += 1
    
    def is_expired(self, max_age: int = 3600) -> bool:
        """Check if connection is expired"""
        age = (datetime.utcnow() - self.created_at).total_seconds()
        return age > max_age


class MCPConnectionPool:
    """Connection pool for MCP services with health monitoring"""
    
    def __init__(self, max_connections: int = 10, max_age: int = 3600):
        self.max_connections = max_connections
        self.max_age = max_age
        self.pools: Dict[str, List[MCPConnection]] = {}
        self.semaphores: Dict[str, Semaphore] = {}
        self._lock = asyncio.Lock()
    
    async def get_connection(self, service: str) -> MCPConnection:
        """Get a connection from the pool"""
        async with self._lock:
            if service not in self.pools:
                self.pools[service] = []
                self.semaphores[service] = Semaphore(self.max_connections)
            
            # Try to reuse existing connection
            pool = self.pools[service]
            for conn in pool[:]:
                if conn.is_healthy and not conn.is_expired(self.max_age):
                    conn.mark_used()
                    return conn
                else:
                    await conn.close()
                    pool.remove(conn)
            
            # Create new connection if pool not full
            await self.semaphores[service].acquire()
            try:
                connection_id = hashlib.md5(
                    f"{service}_{datetime.utcnow().isoformat()}".encode()
                ).hexdigest()[:8]
                
                conn = MCPConnection(service, connection_id)
                await conn.initialize()
                pool.append(conn)
                conn.mark_used()
                
                logger.debug(f"Created new connection {connection_id} for service {service}")
                return conn
            except Exception:
                self.semaphores[service].release()
                raise
    
    async def return_connection(self, connection: MCPConnection):
        """Return connection to pool"""
        # Connection is automatically returned to pool
        # Could implement additional logic here if needed
        pass
    
    async def cleanup_expired(self):
        """Cleanup expired connections"""
        async with self._lock:
            for service, pool in self.pools.items():
                for conn in pool[:]:
                    if conn.is_expired(self.max_age) or not conn.is_healthy:
                        await conn.close()
                        pool.remove(conn)
                        self.semaphores[service].release()
    
    async def close_all(self):
        """Close all connections"""
        async with self._lock:
            for pool in self.pools.values():
                for conn in pool:
                    await conn.close()
            self.pools.clear()


# Data Transformation Utilities
class MCPDataTransformer:
    """Advanced data transformation utilities for MCP responses"""
    
    @staticmethod
    def transform_supabase_response(raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Supabase MCP response to standardized format"""
        try:
            transformed = {
                "success": raw_response.get("status") == "success",
                "data": {
                    "rows": raw_response.get("rows", []),
                    "count": len(raw_response.get("rows", [])),
                    "affected_rows": raw_response.get("affected_rows"),
                    "columns": MCPDataTransformer._extract_columns(raw_response.get("rows", []))
                },
                "metadata": {
                    "execution_time": raw_response.get("execution_time"),
                    "query_hash": hashlib.md5(
                        str(raw_response).encode()
                    ).hexdigest()[:8]
                }
            }
            
            return transformed
        except Exception as e:
            raise MCPIntegrationError(
                f"Failed to transform Supabase response: {str(e)}",
                MCPErrorCode.DATA_TRANSFORMATION_ERROR,
                service="supabase",
                details={"raw_response": raw_response}
            )
    
    @staticmethod
    def transform_railway_response(raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Railway MCP response to standardized format"""
        try:
            if "deployment_id" in raw_response:
                transformed = {
                    "success": True,
                    "data": {
                        "deployment": {
                            "id": raw_response.get("deployment_id"),
                            "status": raw_response.get("status", "unknown"),
                            "project_id": raw_response.get("project_id"),
                            "service_id": raw_response.get("service_id"),
                            "environment_id": raw_response.get("environment_id")
                        }
                    },
                    "metadata": {
                        "timestamp": datetime.utcnow().isoformat(),
                        "operation": "deployment"
                    }
                }
            elif "projects" in raw_response:
                transformed = {
                    "success": True,
                    "data": {
                        "projects": raw_response.get("projects", []),
                        "count": len(raw_response.get("projects", []))
                    },
                    "metadata": {
                        "timestamp": datetime.utcnow().isoformat(),
                        "operation": "list_projects"
                    }
                }
            else:
                transformed = {
                    "success": True,
                    "data": raw_response,
                    "metadata": {
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            
            return transformed
        except Exception as e:
            raise MCPIntegrationError(
                f"Failed to transform Railway response: {str(e)}",
                MCPErrorCode.DATA_TRANSFORMATION_ERROR,
                service="railway",
                details={"raw_response": raw_response}
            )
    
    @staticmethod
    def transform_claude_flow_response(raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Claude Flow MCP response to standardized format"""
        try:
            transformed = {
                "success": True,
                "data": {
                    "swarm": raw_response.get("swarm", {}),
                    "task": raw_response.get("task", {}),
                    "agents": raw_response.get("agents", []),
                    "coordination": {
                        "topology": raw_response.get("topology", "unknown"),
                        "strategy": raw_response.get("strategy", "unknown")
                    }
                },
                "metadata": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "coordination_id": raw_response.get("swarm_id") or raw_response.get("task_id")
                }
            }
            
            return transformed
        except Exception as e:
            raise MCPIntegrationError(
                f"Failed to transform Claude Flow response: {str(e)}",
                MCPErrorCode.DATA_TRANSFORMATION_ERROR,
                service="claude-flow",
                details={"raw_response": raw_response}
            )
    
    @staticmethod
    def _extract_columns(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Extract column information from query results"""
        if not rows:
            return []
        
        first_row = rows[0]
        columns = []
        
        for key, value in first_row.items():
            column_type = type(value).__name__
            if column_type == 'NoneType':
                column_type = 'unknown'
            
            columns.append({
                "name": key,
                "type": column_type
            })
        
        return columns
    
    @staticmethod
    def sanitize_input_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize input data for security"""
        sanitized = {}
        
        for key, value in data.items():
            # Remove potentially dangerous keys
            if key.lower() in ['password', 'secret', 'token', 'key']:
                continue
            
            # Sanitize string values
            if isinstance(value, str):
                # Basic XSS prevention
                value = value.replace('<script', '&lt;script')
                value = value.replace('javascript:', '')
                # SQL injection prevention
                value = value.replace(';--', '')
                value = value.replace("'; DROP", '')
            
            sanitized[key] = value
        
        return sanitized


# Advanced Retry Manager
class MCPRetryManager:
    """Advanced retry manager with intelligent backoff strategies"""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.retry_history: Dict[str, List[datetime]] = {}
    
    async def execute_with_retry(
        self,
        operation: Callable,
        operation_id: str,
        *args,
        **kwargs
    ) -> Any:
        """Execute operation with intelligent retry logic"""
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                start_time = time.time()
                result = await operation(*args, **kwargs)
                
                # Record successful execution
                execution_time = time.time() - start_time
                logger.debug(
                    f"Operation {operation_id} succeeded on attempt {attempt + 1} "
                    f"in {execution_time:.3f}s"
                )
                
                return result
                
            except MCPIntegrationError as e:
                last_error = e
                
                # Don't retry non-retryable errors
                if not e.retryable or e.code not in self.config.retryable_errors:
                    logger.warning(
                        f"Operation {operation_id} failed with non-retryable error: {e.code.value}"
                    )
                    raise
                
                # Don't retry on last attempt
                if attempt == self.config.max_retries:
                    break
                
                # Calculate delay with jitter
                delay = self._calculate_delay(attempt, e)
                
                # Record retry attempt
                self._record_retry(operation_id)
                
                logger.warning(
                    f"Operation {operation_id} failed on attempt {attempt + 1}, "
                    f"retrying in {delay:.2f}s. Error: {e.message}"
                )
                
                await asyncio.sleep(delay)
        
        # All retries exhausted
        raise MCPIntegrationError(
            f"Operation {operation_id} failed after {self.config.max_retries + 1} attempts",
            MCPErrorCode.RETRY_EXHAUSTED,
            details={"last_error": last_error.to_dict() if last_error else None},
            retryable=False
        )
    
    def _calculate_delay(self, attempt: int, error: MCPIntegrationError) -> float:
        """Calculate retry delay with intelligent backoff"""
        # Base exponential backoff
        delay = self.config.base_delay * (self.config.backoff_factor ** attempt)
        
        # Apply rate limit specific delay
        if error.code == MCPErrorCode.RATE_LIMIT_ERROR and error.retry_after:
            delay = max(delay, error.retry_after)
        
        # Add jitter if enabled
        if self.config.jitter:
            import random
            jitter = random.uniform(0.1, 0.9)
            delay *= jitter
        
        # Respect maximum delay
        return min(delay, self.config.max_delay)
    
    def _record_retry(self, operation_id: str):
        """Record retry attempt for monitoring"""
        if operation_id not in self.retry_history:
            self.retry_history[operation_id] = []
        
        self.retry_history[operation_id].append(datetime.utcnow())
        
        # Keep only recent history (last hour)
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self.retry_history[operation_id] = [
            ts for ts in self.retry_history[operation_id] if ts > cutoff
        ]
    
    def get_retry_stats(self) -> Dict[str, Any]:
        """Get retry statistics for monitoring"""
        total_retries = sum(len(history) for history in self.retry_history.values())
        operation_count = len(self.retry_history)
        
        return {
            "total_retries": total_retries,
            "operations_with_retries": operation_count,
            "avg_retries_per_operation": total_retries / max(operation_count, 1),
            "operations": {
                op_id: len(history) 
                for op_id, history in self.retry_history.items()
            }
        }


# Performance Monitor
class MCPPerformanceMonitor:
    """Monitor MCP operation performance and health"""
    
    def __init__(self):
        self.metrics = {
            "operations": {},
            "services": {},
            "errors": {},
            "performance": {}
        }
        self._lock = asyncio.Lock()
    
    async def record_operation(
        self,
        service: str,
        operation: str,
        execution_time: float,
        success: bool,
        error_code: Optional[MCPErrorCode] = None
    ):
        """Record operation metrics"""
        async with self._lock:
            timestamp = datetime.utcnow()
            
            # Update operation metrics
            op_key = f"{service}.{operation}"
            if op_key not in self.metrics["operations"]:
                self.metrics["operations"][op_key] = {
                    "count": 0,
                    "success_count": 0,
                    "total_time": 0.0,
                    "min_time": float('inf'),
                    "max_time": 0.0,
                    "recent_times": []
                }
            
            op_metrics = self.metrics["operations"][op_key]
            op_metrics["count"] += 1
            op_metrics["total_time"] += execution_time
            op_metrics["min_time"] = min(op_metrics["min_time"], execution_time)
            op_metrics["max_time"] = max(op_metrics["max_time"], execution_time)
            
            # Keep recent times for percentile calculations
            op_metrics["recent_times"].append(execution_time)
            if len(op_metrics["recent_times"]) > 100:
                op_metrics["recent_times"] = op_metrics["recent_times"][-100:]
            
            if success:
                op_metrics["success_count"] += 1
            
            # Update service metrics
            if service not in self.metrics["services"]:
                self.metrics["services"][service] = {
                    "total_operations": 0,
                    "successful_operations": 0,
                    "last_operation": None
                }
            
            service_metrics = self.metrics["services"][service]
            service_metrics["total_operations"] += 1
            service_metrics["last_operation"] = timestamp.isoformat()
            
            if success:
                service_metrics["successful_operations"] += 1
            
            # Update error metrics
            if error_code:
                error_key = f"{service}.{error_code.value}"
                if error_key not in self.metrics["errors"]:
                    self.metrics["errors"][error_key] = 0
                self.metrics["errors"][error_key] += 1
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        summary = {
            "services": {},
            "top_operations": [],
            "error_summary": {},
            "overall_health": "unknown"
        }
        
        # Service summaries
        for service, metrics in self.metrics["services"].items():
            total_ops = metrics["total_operations"]
            if total_ops > 0:
                success_rate = metrics["successful_operations"] / total_ops
                summary["services"][service] = {
                    "success_rate": success_rate,
                    "total_operations": total_ops,
                    "health": "healthy" if success_rate >= 0.95 else 
                             "degraded" if success_rate >= 0.8 else "unhealthy"
                }
        
        # Top operations by volume
        operation_volumes = [
            (op, metrics["count"]) 
            for op, metrics in self.metrics["operations"].items()
        ]
        summary["top_operations"] = sorted(
            operation_volumes, 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        # Error summary
        total_errors = sum(self.metrics["errors"].values())
        summary["error_summary"] = {
            "total_errors": total_errors,
            "error_types": dict(self.metrics["errors"])
        }
        
        # Overall health
        if summary["services"]:
            healthy_services = sum(
                1 for s in summary["services"].values() 
                if s["health"] == "healthy"
            )
            total_services = len(summary["services"])
            
            if healthy_services == total_services:
                summary["overall_health"] = "healthy"
            elif healthy_services >= total_services * 0.8:
                summary["overall_health"] = "degraded"
            else:
                summary["overall_health"] = "unhealthy"
        
        return summary


# Main Integration Pattern Class
class MCPIntegrationPatterns:
    """Main class implementing production-ready MCP integration patterns"""
    
    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        connection_pool_size: int = 10
    ):
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        
        # Initialize components
        self.retry_manager = MCPRetryManager(self.retry_config)
        self.connection_pool = MCPConnectionPool(max_connections=connection_pool_size)
        self.transformer = MCPDataTransformer()
        self.performance_monitor = MCPPerformanceMonitor()
        
        # Circuit breakers per service
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Request/response cache
        self.response_cache: Dict[str, Any] = {}
        self.cache_ttl: Dict[str, datetime] = {}
        
        logger.info("MCP Integration Patterns initialized with production-ready components")
    
    def _get_circuit_breaker(self, service: str) -> CircuitBreaker:
        """Get or create circuit breaker for service"""
        if service not in self.circuit_breakers:
            self.circuit_breakers[service] = CircuitBreaker(
                self.circuit_breaker_config,
                name=service
            )
        return self.circuit_breakers[service]
    
    async def execute_mcp_operation(
        self,
        request: MCPRequestSchema,
        use_circuit_breaker: bool = True,
        cache_ttl: Optional[int] = None
    ) -> MCPResponseSchema:
        """
        Execute MCP operation with all integration patterns applied:
        - Input validation
        - Circuit breaker protection
        - Retry with exponential backoff
        - Connection pooling
        - Response caching
        - Data transformation
        - Performance monitoring
        """
        operation_id = f"{request.service}.{request.operation}.{hash(str(request.parameters))}"
        start_time = time.time()
        
        try:
            # 1. Input validation
            validated_request = self._validate_request(request)
            
            # 2. Check cache
            if cache_ttl and operation_id in self.response_cache:
                if datetime.utcnow() < self.cache_ttl.get(operation_id, datetime.min):
                    logger.debug(f"Returning cached response for {operation_id}")
                    return self.response_cache[operation_id]
            
            # 3. Execute with circuit breaker and retry
            circuit_breaker = self._get_circuit_breaker(request.service) if use_circuit_breaker else None
            
            async def _execute_operation():
                if circuit_breaker:
                    return await circuit_breaker.call(
                        self._execute_raw_operation,
                        validated_request
                    )
                else:
                    return await self._execute_raw_operation(validated_request)
            
            raw_response = await self.retry_manager.execute_with_retry(
                _execute_operation,
                operation_id
            )
            
            # 4. Transform response
            transformed_response = self._transform_response(raw_response, request.service)
            
            # 5. Create standardized response
            execution_time = time.time() - start_time
            response = MCPResponseSchema(
                success=True,
                data=transformed_response,
                execution_time=execution_time,
                timestamp=datetime.utcnow(),
                service=request.service,
                operation=request.operation
            )
            
            # 6. Cache response if requested
            if cache_ttl:
                self.response_cache[operation_id] = response
                self.cache_ttl[operation_id] = datetime.utcnow() + timedelta(seconds=cache_ttl)
            
            # 7. Record metrics
            await self.performance_monitor.record_operation(
                request.service,
                request.operation,
                execution_time,
                success=True
            )
            
            return response
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_code = self._extract_error_code(e)
            
            # Record error metrics
            await self.performance_monitor.record_operation(
                request.service,
                request.operation,
                execution_time,
                success=False,
                error_code=error_code
            )
            
            # Convert to standardized error response
            if isinstance(e, MCPIntegrationError):
                response = MCPResponseSchema(
                    success=False,
                    error=e.to_dict(),
                    execution_time=execution_time,
                    timestamp=datetime.utcnow(),
                    service=request.service,
                    operation=request.operation
                )
            else:
                response = MCPResponseSchema(
                    success=False,
                    error={
                        "message": str(e),
                        "code": "UNKNOWN_ERROR",
                        "details": {"exception_type": type(e).__name__}
                    },
                    execution_time=execution_time,
                    timestamp=datetime.utcnow(),
                    service=request.service,
                    operation=request.operation
                )
            
            return response
    
    def _validate_request(self, request: MCPRequestSchema) -> MCPRequestSchema:
        """Validate and sanitize request"""
        # Sanitize parameters
        if request.parameters:
            request.parameters = self.transformer.sanitize_input_data(request.parameters)
        
        # Service-specific validation
        if request.service == "supabase" and request.operation == "execute_sql":
            query_schema = SupabaseQuerySchema(**request.parameters)
            request.parameters = query_schema.dict()
        elif request.service == "railway" and request.operation == "deploy_service":
            deploy_schema = RailwayDeploymentSchema(**request.parameters)
            request.parameters = deploy_schema.dict()
        
        return request
    
    async def _execute_raw_operation(self, request: MCPRequestSchema) -> Dict[str, Any]:
        """Execute the actual MCP operation"""
        # Get connection from pool
        connection = await self.connection_pool.get_connection(request.service)
        
        try:
            # This would be replaced with actual MCP calls
            # For now, simulate the operation
            if request.service == "supabase":
                return await self._simulate_supabase_operation(request, connection)
            elif request.service == "railway":
                return await self._simulate_railway_operation(request, connection)
            elif request.service == "claude-flow":
                return await self._simulate_claude_flow_operation(request, connection)
            else:
                raise MCPIntegrationError(
                    f"Unsupported service: {request.service}",
                    MCPErrorCode.VALIDATION_ERROR,
                    service=request.service,
                    operation=request.operation
                )
        finally:
            await self.connection_pool.return_connection(connection)
    
    async def _simulate_supabase_operation(
        self, 
        request: MCPRequestSchema, 
        connection: MCPConnection
    ) -> Dict[str, Any]:
        """Simulate Supabase MCP operation"""
        # Simulate network delay
        await asyncio.sleep(0.1)
        
        if request.operation == "execute_sql":
            return {
                "status": "success",
                "rows": [{"id": 1, "name": "test"}],
                "affected_rows": 1,
                "execution_time": 0.05
            }
        elif request.operation == "list_tables":
            return {
                "tables": [{"name": "users", "schema": "public"}],
                "count": 1
            }
        else:
            raise MCPIntegrationError(
                f"Unknown Supabase operation: {request.operation}",
                MCPErrorCode.VALIDATION_ERROR,
                service="supabase",
                operation=request.operation
            )
    
    async def _simulate_railway_operation(
        self, 
        request: MCPRequestSchema, 
        connection: MCPConnection
    ) -> Dict[str, Any]:
        """Simulate Railway MCP operation"""
        await asyncio.sleep(0.2)
        
        if request.operation == "deploy_service":
            return {
                "deployment_id": "dep_123456",
                "status": "pending",
                "project_id": request.parameters.get("project_id"),
                "service_id": request.parameters.get("service_id"),
                "environment_id": request.parameters.get("environment_id")
            }
        elif request.operation == "list_projects":
            return {
                "projects": [{"id": "proj_123", "name": "velro-backend"}],
                "count": 1
            }
        else:
            raise MCPIntegrationError(
                f"Unknown Railway operation: {request.operation}",
                MCPErrorCode.VALIDATION_ERROR,
                service="railway",
                operation=request.operation
            )
    
    async def _simulate_claude_flow_operation(
        self, 
        request: MCPRequestSchema, 
        connection: MCPConnection
    ) -> Dict[str, Any]:
        """Simulate Claude Flow MCP operation"""
        await asyncio.sleep(0.15)
        
        if request.operation == "orchestrate_task":
            return {
                "swarm_id": "swarm_123",
                "task_id": "task_456",
                "status": "pending",
                "topology": "hierarchical",
                "strategy": "adaptive"
            }
        elif request.operation == "init_swarm":
            return {
                "swarm_id": "swarm_789",
                "topology": request.parameters.get("topology", "hierarchical"),
                "max_agents": request.parameters.get("max_agents", 8)
            }
        else:
            raise MCPIntegrationError(
                f"Unknown Claude Flow operation: {request.operation}",
                MCPErrorCode.VALIDATION_ERROR,
                service="claude-flow",
                operation=request.operation
            )
    
    def _transform_response(self, raw_response: Dict[str, Any], service: str) -> Dict[str, Any]:
        """Transform raw response using service-specific transformer"""
        if service == "supabase":
            return self.transformer.transform_supabase_response(raw_response)
        elif service == "railway":
            return self.transformer.transform_railway_response(raw_response)
        elif service == "claude-flow":
            return self.transformer.transform_claude_flow_response(raw_response)
        else:
            return raw_response
    
    def _extract_error_code(self, error: Exception) -> MCPErrorCode:
        """Extract error code from exception"""
        if isinstance(error, MCPIntegrationError):
            return error.code
        elif "timeout" in str(error).lower():
            return MCPErrorCode.TIMEOUT_ERROR
        elif "connection" in str(error).lower():
            return MCPErrorCode.CONNECTION_ERROR
        else:
            return MCPErrorCode.VALIDATION_ERROR
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check of integration patterns"""
        health_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
            "performance": self.performance_monitor.get_performance_summary(),
            "retry_stats": self.retry_manager.get_retry_stats(),
            "circuit_breakers": {},
            "connection_pools": {}
        }
        
        # Check circuit breakers
        for service, cb in self.circuit_breakers.items():
            health_data["circuit_breakers"][service] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "last_failure": cb.last_failure_time.isoformat() if cb.last_failure_time else None
            }
        
        # Check connection pools
        for service, pool in self.connection_pool.pools.items():
            healthy_connections = sum(1 for conn in pool if conn.is_healthy)
            health_data["connection_pools"][service] = {
                "total_connections": len(pool),
                "healthy_connections": healthy_connections,
                "utilization": len(pool) / self.connection_pool.max_connections
            }
        
        return health_data
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.connection_pool.close_all()
        self.response_cache.clear()
        self.cache_ttl.clear()
        logger.info("MCP Integration Patterns cleanup completed")


# Singleton instance
_integration_patterns_instance = None

def get_mcp_integration_patterns(
    retry_config: Optional[RetryConfig] = None,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    connection_pool_size: int = 10
) -> MCPIntegrationPatterns:
    """Get or create singleton instance of MCP integration patterns"""
    global _integration_patterns_instance
    
    if _integration_patterns_instance is None:
        _integration_patterns_instance = MCPIntegrationPatterns(
            retry_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
            connection_pool_size=connection_pool_size
        )
    
    return _integration_patterns_instance


# Convenience functions
async def execute_supabase_query_with_patterns(
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    use_cache: bool = True
) -> MCPResponseSchema:
    """Execute Supabase query with all integration patterns"""
    patterns = get_mcp_integration_patterns()
    
    request = MCPRequestSchema(
        service="supabase",
        operation="execute_sql",
        parameters={"query": query, "parameters": parameters or {}}
    )
    
    return await patterns.execute_mcp_operation(
        request,
        cache_ttl=300 if use_cache else None
    )


async def deploy_railway_service_with_patterns(
    project_id: str,
    service_id: str,
    environment_id: str,
    commit_sha: Optional[str] = None
) -> MCPResponseSchema:
    """Deploy Railway service with all integration patterns"""
    patterns = get_mcp_integration_patterns()
    
    request = MCPRequestSchema(
        service="railway",
        operation="deploy_service",
        parameters={
            "project_id": project_id,
            "service_id": service_id,
            "environment_id": environment_id,
            "commit_sha": commit_sha
        }
    )
    
    return await patterns.execute_mcp_operation(request)


async def coordinate_claude_flow_task_with_patterns(
    task: str,
    agents: Optional[List[str]] = None,
    strategy: str = "adaptive"
) -> MCPResponseSchema:
    """Coordinate Claude Flow task with all integration patterns"""
    patterns = get_mcp_integration_patterns()
    
    request = MCPRequestSchema(
        service="claude-flow",
        operation="orchestrate_task",
        parameters={
            "task": task,
            "agents": agents or [],
            "strategy": strategy
        }
    )
    
    return await patterns.execute_mcp_operation(request)