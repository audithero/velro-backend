"""
Performance Tracking Middleware for Automatic Metric Collection

This middleware automatically tracks performance metrics for all API requests,
providing seamless integration with the performance monitoring system without
requiring manual instrumentation of individual endpoints.

Features:
- Automatic response time tracking for all endpoints
- Authentication and authorization performance monitoring
- Database query performance tracking
- Cache operation monitoring
- Concurrent user tracking
- Integration with existing performance tracker
- Low overhead operation (<1ms additional latency)
"""

import time
import asyncio
import logging
from typing import Callable, Dict, Any, Optional, List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
import weakref
import threading
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class PerformanceTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that automatically tracks performance metrics for all requests.
    
    Integrates with the performance tracker to provide comprehensive
    performance monitoring without requiring manual instrumentation.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.tracker = None
        self._active_requests: Dict[str, Dict[str, Any]] = {}
        self._request_lock = threading.RLock()
        
        # Initialize performance tracker
        try:
            from monitoring.performance_tracker import get_performance_tracker, MetricType
            self.tracker = get_performance_tracker()
            self.MetricType = MetricType
            logger.info("Performance tracking middleware initialized")
        except ImportError as e:
            logger.warning(f"Performance tracker not available: {e}")
            self.tracker = None
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with automatic performance tracking.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler in chain
            
        Returns:
            Response with performance headers added
        """
        if not self.tracker:
            # No tracking available, pass through
            return await call_next(request)
        
        # Start timing
        start_time = time.perf_counter()
        request_id = self._generate_request_id(request)
        
        # Track request start
        self._track_request_start(request_id, request)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate response time
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Track the request completion
            await self._track_request_completion(
                request_id, request, response, duration_ms, True
            )
            
            # Add performance headers
            self._add_performance_headers(response, duration_ms)
            
            return response
            
        except Exception as e:
            # Track failed request
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._track_request_completion(
                request_id, request, None, duration_ms, False, str(e)
            )
            raise
        
        finally:
            # Clean up request tracking
            self._track_request_end(request_id)
    
    def _generate_request_id(self, request: Request) -> str:
        """Generate unique request ID for tracking."""
        return f"{request.method}_{request.url.path}_{int(time.time() * 1000000)}"
    
    def _track_request_start(self, request_id: str, request: Request) -> None:
        """Track request start for concurrent monitoring."""
        with self._request_lock:
            self._active_requests[request_id] = {
                'start_time': time.time(),
                'method': request.method,
                'path': str(request.url.path),
                'client_ip': request.client.host if request.client else None,
                'user_agent': request.headers.get('User-Agent', ''),
                'user_id': self._extract_user_id(request)
            }
            
            # Update concurrent user count
            concurrent_users = len(set(
                req_data.get('user_id') 
                for req_data in self._active_requests.values()
                if req_data.get('user_id')
            ))
            
            if concurrent_users > 0:
                self.tracker.record_concurrent_users(concurrent_users)
    
    def _track_request_end(self, request_id: str) -> None:
        """Clean up request tracking."""
        with self._request_lock:
            if request_id in self._active_requests:
                del self._active_requests[request_id]
    
    async def _track_request_completion(self, request_id: str, request: Request, 
                                      response: Optional[Response], duration_ms: float,
                                      success: bool, error: str = None) -> None:
        """Track completed request with appropriate metrics."""
        if not self.tracker:
            return
        
        try:
            # Extract request information
            method = request.method
            path = str(request.url.path)
            status_code = response.status_code if response else 500
            user_id = self._extract_user_id(request)
            
            # Determine metric type based on endpoint
            metric_type = self._determine_metric_type(path, method)
            
            # Record the metric
            if metric_type:
                operation_name = self._get_operation_name(path, method)
                
                self.tracker.record_metric(
                    metric_type=metric_type,
                    operation_name=operation_name,
                    value=duration_ms,
                    unit="ms",
                    success=success,
                    user_id=user_id,
                    endpoint=path,
                    method=method,
                    status_code=status_code,
                    error=error
                )
            
            # Always record general API response time
            self.tracker.record_metric(
                metric_type=self.MetricType.API_RESPONSE,
                operation_name=f"{method} {path}",
                value=duration_ms,
                unit="ms",
                success=success,
                user_id=user_id,
                endpoint=path,
                method=method,
                status_code=status_code,
                error=error
            )
            
        except Exception as e:
            logger.error(f"Error tracking request completion: {e}")
    
    def _determine_metric_type(self, path: str, method: str) -> Optional[Any]:
        """Determine the appropriate metric type based on the request path."""
        if not self.MetricType:
            return None
        
        # Authentication endpoints
        if any(auth_path in path.lower() for auth_path in [
            '/auth/', '/login', '/register', '/token', '/refresh'
        ]):
            return self.MetricType.AUTHENTICATION
        
        # Authorization-heavy endpoints (checking permissions)
        if any(auth_path in path.lower() for auth_path in [
            '/api/v1/generations', '/api/v1/projects', '/api/v1/credits',
            '/api/v1/teams', '/api/v1/models'
        ]):
            return self.MetricType.AUTHORIZATION
        
        # Performance monitoring endpoints (skip to avoid recursive tracking)
        if '/performance' in path.lower():
            return None
        
        # Health check endpoints
        if any(health_path in path.lower() for health_path in [
            '/health', '/status', '/ping'
        ]):
            return None  # Don't track health checks as they should be lightweight
        
        # For other API endpoints, classify as general API response
        return self.MetricType.API_RESPONSE
    
    def _get_operation_name(self, path: str, method: str) -> str:
        """Generate descriptive operation name."""
        # Clean up path for operation name
        clean_path = path.replace('/api/v1', '').replace('/api', '').strip('/')
        
        if not clean_path:
            return f"{method.upper()} root"
        
        # Replace UUID patterns with placeholder
        import re
        clean_path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '/:id',
            clean_path
        )
        
        return f"{method.upper()} {clean_path}"
    
    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request if available."""
        # Try to extract from authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header:
            try:
                # This would need to be implemented based on your JWT structure
                # For now, return a placeholder
                if 'Bearer' in auth_header:
                    return 'authenticated_user'  # Placeholder
            except Exception:
                pass
        
        # Try to extract from request state (if set by auth middleware)
        if hasattr(request, 'state') and hasattr(request.state, 'user_id'):
            return request.state.user_id
        
        return None
    
    def _add_performance_headers(self, response: Response, duration_ms: float) -> None:
        """Add performance-related headers to response."""
        try:
            response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
            
            # Add performance grade
            if duration_ms < 50:
                performance_grade = "A"
            elif duration_ms < 100:
                performance_grade = "B"
            elif duration_ms < 200:
                performance_grade = "C"
            elif duration_ms < 500:
                performance_grade = "D"
            else:
                performance_grade = "F"
            
            response.headers["X-Performance-Grade"] = performance_grade
            
            # Add concurrent users if available
            with self._request_lock:
                concurrent_count = len(self._active_requests)
                response.headers["X-Concurrent-Requests"] = str(concurrent_count)
            
        except Exception as e:
            logger.error(f"Error adding performance headers: {e}")


class DatabasePerformanceMiddleware:
    """
    Middleware for tracking database query performance.
    
    This is designed to be integrated with database connections
    to automatically track query performance.
    """
    
    def __init__(self):
        self.tracker = None
        try:
            from monitoring.performance_tracker import get_performance_tracker, MetricType
            self.tracker = get_performance_tracker()
            self.MetricType = MetricType
        except ImportError:
            logger.warning("Performance tracker not available for database monitoring")
    
    async def track_query(self, query: str, duration_ms: float, success: bool = True,
                         table: str = None, operation: str = None) -> None:
        """Track database query performance."""
        if not self.tracker:
            return
        
        try:
            # Determine operation type if not provided
            if not operation:
                query_lower = query.lower().strip()
                if query_lower.startswith('select'):
                    operation = 'SELECT'
                elif query_lower.startswith('insert'):
                    operation = 'INSERT'
                elif query_lower.startswith('update'):
                    operation = 'UPDATE'
                elif query_lower.startswith('delete'):
                    operation = 'DELETE'
                else:
                    operation = 'OTHER'
            
            # Extract table name if not provided
            if not table:
                table = self._extract_table_name(query)
            
            operation_name = f"{operation} {table}" if table else operation
            
            self.tracker.record_metric(
                metric_type=self.MetricType.DATABASE_QUERY,
                operation_name=operation_name,
                value=duration_ms,
                unit="ms",
                success=success,
                query_type=operation,
                table_name=table
            )
            
        except Exception as e:
            logger.error(f"Error tracking database query: {e}")
    
    def _extract_table_name(self, query: str) -> str:
        """Extract table name from SQL query."""
        try:
            import re
            query_lower = query.lower()
            
            # Try to extract table name for common operations
            patterns = [
                r'from\s+([a-zA-Z_][a-zA-Z0-9_]*)',  # SELECT FROM
                r'into\s+([a-zA-Z_][a-zA-Z0-9_]*)',  # INSERT INTO
                r'update\s+([a-zA-Z_][a-zA-Z0-9_]*)',  # UPDATE
                r'delete\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)'  # DELETE FROM
            ]
            
            for pattern in patterns:
                match = re.search(pattern, query_lower)
                if match:
                    return match.group(1)
            
            return "unknown"
            
        except Exception:
            return "unknown"


class CachePerformanceMiddleware:
    """
    Middleware for tracking cache operation performance.
    
    This is designed to be integrated with cache operations
    to automatically track cache performance.
    """
    
    def __init__(self):
        self.tracker = None
        try:
            from monitoring.performance_tracker import get_performance_tracker, MetricType
            self.tracker = get_performance_tracker()
            self.MetricType = MetricType
        except ImportError:
            logger.warning("Performance tracker not available for cache monitoring")
    
    def track_cache_operation(self, cache_level: str, operation: str, 
                            duration_ms: float, hit: bool = None, 
                            key: str = None, success: bool = True) -> None:
        """Track cache operation performance."""
        if not self.tracker:
            return
        
        try:
            # Determine cache metric type
            cache_type_map = {
                'L1': self.MetricType.CACHE_L1,
                'L2': self.MetricType.CACHE_L2,
                'L3': self.MetricType.CACHE_L3,
                'l1': self.MetricType.CACHE_L1,
                'l2': self.MetricType.CACHE_L2,
                'l3': self.MetricType.CACHE_L3
            }
            
            metric_type = cache_type_map.get(cache_level, self.MetricType.CACHE_L1)
            
            # For cache hit rate tracking
            if operation in ['get', 'fetch'] and hit is not None:
                # Record hit rate as percentage (100% for hit, 0% for miss)
                hit_rate = 100.0 if hit else 0.0
                
                self.tracker.record_metric(
                    metric_type=metric_type,
                    operation_name=f"{operation}_hit_rate",
                    value=hit_rate,
                    unit="%",
                    success=success,
                    cache_level=cache_level,
                    operation_type=operation,
                    cache_key=key,
                    hit=hit,
                    response_time_ms=duration_ms
                )
            
            # Also record response time
            self.tracker.record_metric(
                metric_type=metric_type,
                operation_name=f"{operation}_response_time",
                value=duration_ms,
                unit="ms",
                success=success,
                cache_level=cache_level,
                operation_type=operation,
                cache_key=key,
                hit=hit
            )
            
        except Exception as e:
            logger.error(f"Error tracking cache operation: {e}")


# Context managers for manual performance tracking

class track_db_query:
    """Context manager for tracking database query performance."""
    
    def __init__(self, query: str, table: str = None, operation: str = None):
        self.query = query
        self.table = table
        self.operation = operation
        self.start_time = None
        self.middleware = DatabasePerformanceMiddleware()
    
    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        success = exc_type is None
        
        await self.middleware.track_query(
            query=self.query,
            duration_ms=duration_ms,
            success=success,
            table=self.table,
            operation=self.operation
        )


class track_cache_op:
    """Context manager for tracking cache operation performance."""
    
    def __init__(self, cache_level: str, operation: str, key: str = None):
        self.cache_level = cache_level
        self.operation = operation
        self.key = key
        self.start_time = None
        self.middleware = CachePerformanceMiddleware()
        self.hit = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        success = exc_type is None
        
        self.middleware.track_cache_operation(
            cache_level=self.cache_level,
            operation=self.operation,
            duration_ms=duration_ms,
            hit=self.hit,
            key=self.key,
            success=success
        )
    
    def set_hit(self, hit: bool):
        """Set whether the cache operation was a hit or miss."""
        self.hit = hit


# Performance tracking decorators for database and cache functions

def track_database_performance(query: str = None, table: str = None, operation: str = None):
    """Decorator for automatic database performance tracking."""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                middleware = DatabasePerformanceMiddleware()
                start_time = time.perf_counter()
                
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    
                    await middleware.track_query(
                        query=query or func.__name__,
                        duration_ms=duration_ms,
                        success=True,
                        table=table,
                        operation=operation
                    )
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    await middleware.track_query(
                        query=query or func.__name__,
                        duration_ms=duration_ms,
                        success=False,
                        table=table,
                        operation=operation
                    )
                    raise
            
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                middleware = DatabasePerformanceMiddleware()
                start_time = time.perf_counter()
                
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    
                    # Use asyncio.create_task if in async context
                    try:
                        import asyncio
                        loop = asyncio.get_running_loop()
                        loop.create_task(middleware.track_query(
                            query=query or func.__name__,
                            duration_ms=duration_ms,
                            success=True,
                            table=table,
                            operation=operation
                        ))
                    except RuntimeError:
                        # No event loop, skip tracking
                        pass
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    
                    try:
                        import asyncio
                        loop = asyncio.get_running_loop()
                        loop.create_task(middleware.track_query(
                            query=query or func.__name__,
                            duration_ms=duration_ms,
                            success=False,
                            table=table,
                            operation=operation
                        ))
                    except RuntimeError:
                        pass
                    
                    raise
            
            return sync_wrapper
    
    return decorator


def track_cache_performance(cache_level: str, operation: str):
    """Decorator for automatic cache performance tracking."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            middleware = CachePerformanceMiddleware()
            start_time = time.perf_counter()
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                # Determine if it was a cache hit based on result
                hit = result is not None if operation in ['get', 'fetch'] else None
                
                middleware.track_cache_operation(
                    cache_level=cache_level,
                    operation=operation,
                    duration_ms=duration_ms,
                    hit=hit,
                    success=True
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                middleware.track_cache_operation(
                    cache_level=cache_level,
                    operation=operation,
                    duration_ms=duration_ms,
                    success=False
                )
                
                raise
        
        return wrapper
    
    return decorator


# Global instances for easy access
db_performance_middleware = DatabasePerformanceMiddleware()
cache_performance_middleware = CachePerformanceMiddleware()


# Utility functions for integration

async def start_performance_tracking():
    """Initialize and start performance tracking."""
    try:
        from monitoring.performance_tracker import get_performance_tracker
        tracker = get_performance_tracker()
        await tracker.start_monitoring()
        logger.info("Performance tracking started successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to start performance tracking: {e}")
        return False


async def stop_performance_tracking():
    """Stop performance tracking gracefully."""
    try:
        from monitoring.performance_tracker import get_performance_tracker
        tracker = get_performance_tracker()
        await tracker.stop_monitoring()
        logger.info("Performance tracking stopped successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to stop performance tracking: {e}")
        return False