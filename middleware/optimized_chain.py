"""
Ultra-Optimized Middleware Chain for <100ms Authorization Response Times
High-performance middleware orchestrator with parallel processing and smart routing.

Performance Optimizations:
- Authorization endpoints bypass non-critical middleware
- Async parallel processing for non-blocking operations  
- Smart route prioritization for sub-100ms targets
- Early returns and circuit breakers
- Real-time performance monitoring integration
- Connection pooling and resource optimization

Target Performance:
- Auth endpoints: <100ms total response time
- Health checks: <10ms response time
- Critical operations: Priority lane processing
- Non-critical ops: Background processing without blocking
"""
import time
import asyncio
import logging
from typing import Optional, List, Callable, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from concurrent.futures import ThreadPoolExecutor
import threading
from collections import defaultdict

# Import performance monitoring
try:
    from monitoring.performance_monitor import get_performance_monitor, PerformanceTracker
    PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    PERFORMANCE_MONITORING_AVAILABLE = False

# Import cache manager
try:
    from utils.cache_manager import get_cache_manager
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)

class UltraOptimizedMiddlewareChain(BaseHTTPMiddleware):
    """
    Ultra-high performance middleware chain targeting <100ms authorization response times.
    
    Key Features:
    - Smart route classification with priority lanes
    - Parallel non-blocking operations
    - Early returns for cached responses
    - Circuit breaker protection
    - Real-time performance monitoring
    - Resource-aware request handling
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # High-performance thread pool for non-blocking operations
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="middleware")
        
        # Route classification for performance optimization
        self.route_classes = {
            # Ultra-fast lane (target <10ms)
            'ultra_fast': {
                'patterns': ['/health', '/api/v1/health', '/ping', '/ready'],
                'target_ms': 10
            },
            
            # Critical authorization lane (target <100ms)
            'critical_auth': {
                'patterns': ['/api/v1/auth', '/api/v1/me', '/api/v1/verify'],
                'target_ms': 100
            },
            
            # Fast lane (target <200ms)
            'fast': {
                'patterns': ['/api/v1/generations', '/api/v1/users', '/api/v1/sessions'],
                'target_ms': 200
            },
            
            # Normal lane (target <500ms)
            'normal': {
                'patterns': ['/api/v1/projects', '/api/v1/teams', '/api/v1/credits'],
                'target_ms': 500
            },
            
            # Background lane (no strict target)
            'background': {
                'patterns': ['/api/v1/analytics', '/api/v1/reports', '/api/v1/admin'],
                'target_ms': 2000
            }
        }
        
        # Performance metrics
        self.request_metrics = defaultdict(lambda: {'count': 0, 'total_time': 0.0, 'slow_count': 0})
        self.metrics_lock = threading.Lock()
        
        # Circuit breaker for overload protection
        self.circuit_breaker = {
            'failures': 0,
            'last_failure': 0,
            'timeout': 30,  # 30 second timeout
            'threshold': 10,  # 10 failures to open circuit
            'state': 'closed'  # closed, open, half-open
        }
    
    def _classify_route(self, path: str) -> tuple[str, Dict[str, Any]]:
        """Classify route for performance optimization."""
        path_lower = path.lower()
        
        # Check each route class
        for class_name, config in self.route_classes.items():
            for pattern in config['patterns']:
                if path_lower.startswith(pattern.lower()):
                    return class_name, config
        
        # Default to normal lane
        return 'normal', self.route_classes['normal']
    
    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.circuit_breaker['state'] == 'closed':
            return False
        elif self.circuit_breaker['state'] == 'open':
            if time.time() - self.circuit_breaker['last_failure'] > self.circuit_breaker['timeout']:
                self.circuit_breaker['state'] = 'half-open'
                return False
            return True
        else:  # half-open
            return False
    
    def _record_success(self):
        """Record successful operation for circuit breaker."""
        if self.circuit_breaker['state'] == 'half-open':
            self.circuit_breaker['state'] = 'closed'
            self.circuit_breaker['failures'] = 0
    
    def _record_failure(self):
        """Record failed operation for circuit breaker."""
        self.circuit_breaker['failures'] += 1
        self.circuit_breaker['last_failure'] = time.time()
        
        if self.circuit_breaker['failures'] >= self.circuit_breaker['threshold']:
            self.circuit_breaker['state'] = 'open'
            logger.error(f"Circuit breaker OPEN - too many middleware failures ({self.circuit_breaker['failures']})")
    
    async def dispatch(self, request: Request, call_next):
        """Ultra-optimized request dispatch with performance monitoring."""
        start_time = time.perf_counter()
        path = request.url.path
        route_class, route_config = self._classify_route(path)
        
        # Performance tracking context
        perf_context = {}
        if PERFORMANCE_MONITORING_AVAILABLE:
            perf_context['tracker'] = PerformanceTracker('api_endpoint', path, route_class=route_class)
            perf_context['tracker'].__enter__()
        
        try:
            # Circuit breaker check
            if self._is_circuit_open():
                # Return simple error response when circuit is open
                response = Response(
                    content="Service temporarily unavailable", 
                    status_code=503,
                    headers={"Retry-After": "30"}
                )
                return response
            
            # Route to appropriate processing lane
            if route_class == 'ultra_fast':
                response = await self._ultra_fast_path(request, call_next, route_config)
            elif route_class == 'critical_auth':
                response = await self._critical_auth_path(request, call_next, route_config)
            elif route_class == 'fast':
                response = await self._fast_path(request, call_next, route_config)
            else:
                response = await self._normal_path(request, call_next, route_config)
            
            # Record success
            self._record_success()
            
            # Add performance headers
            total_time = time.perf_counter() - start_time
            total_time_ms = total_time * 1000
            
            response.headers["X-Response-Time"] = f"{total_time_ms:.2f}"
            response.headers["X-Route-Class"] = route_class
            response.headers["X-Target-Time"] = str(route_config['target_ms'])
            
            # Record metrics
            with self.metrics_lock:
                metrics = self.request_metrics[route_class]
                metrics['count'] += 1
                metrics['total_time'] += total_time_ms
                
                if total_time_ms > route_config['target_ms']:
                    metrics['slow_count'] += 1
                    
                    # Log slow requests
                    logger.warning(
                        f"Slow {route_class} request: {path} took {total_time_ms:.2f}ms "
                        f"(target: {route_config['target_ms']}ms)"
                    )
            
            return response
            
        except Exception as e:
            self._record_failure()
            logger.error(f"Middleware error for {path}: {e}")
            
            # Return error response
            return Response(
                content="Internal middleware error", 
                status_code=500
            )
            
        finally:
            # Cleanup performance tracking
            if perf_context.get('tracker'):
                try:
                    perf_context['tracker'].__exit__(None, None, None)
                except:
                    pass
    
    async def _ultra_fast_path(self, request: Request, call_next, config: Dict[str, Any]):
        """Ultra-fast path for health checks and simple endpoints (<10ms target)."""
        # Minimal processing - just pass through
        return await call_next(request)
    
    async def _critical_auth_path(self, request: Request, call_next, config: Dict[str, Any]):
        """Critical authorization path with maximum optimization (<100ms target)."""
        # Check cache first for auth responses (if available)
        cache_key = None
        cached_response = None
        
        if CACHE_AVAILABLE and request.method == "GET":
            try:
                cache = get_cache_manager()
                cache_key = f"auth_response:{request.url.path}:{request.headers.get('Authorization', '')[:50]}"
                
                # Try to get cached response
                cached_response = await cache.get(cache_key, default=None)
                if cached_response and isinstance(cached_response, dict):
                    # Return cached auth response
                    return Response(
                        content=cached_response.get('content', ''),
                        status_code=cached_response.get('status_code', 200),
                        headers=dict(cached_response.get('headers', {})),
                        media_type=cached_response.get('media_type', 'application/json')
                    )
            except Exception as e:
                logger.debug(f"Auth cache lookup failed: {e}")
        
        # Process request normally
        response = await call_next(request)
        
        # Cache successful auth responses (if cacheable)
        if (CACHE_AVAILABLE and cache_key and response.status_code == 200 and 
            request.method == "GET" and 'no-cache' not in response.headers.get('Cache-Control', '')):
            
            try:
                # Cache for 60 seconds to balance performance and freshness
                cache_data = {
                    'content': response.body.decode() if response.body else '',
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'media_type': response.media_type
                }
                
                asyncio.create_task(
                    cache.set(cache_key, cache_data, ttl=60)
                )
            except Exception as e:
                logger.debug(f"Auth response caching failed: {e}")
        
        return response
    
    async def _fast_path(self, request: Request, call_next, config: Dict[str, Any]):
        """Fast path with lightweight checks (<200ms target)."""
        # Run lightweight security checks in parallel (non-blocking)
        security_tasks = []
        
        # Basic rate limiting check (async, non-blocking)
        if request.client:
            security_tasks.append(
                self._async_rate_limit_check(request.client.host)
            )
        
        # IP validation (async, non-blocking)  
        security_tasks.append(
            self._async_ip_validation(request)
        )
        
        # Start security checks (don't wait for completion)
        if security_tasks:
            asyncio.create_task(asyncio.gather(*security_tasks, return_exceptions=True))
        
        # Process request immediately
        response = await call_next(request)
        
        # Add caching headers for fast endpoints
        if response.status_code == 200 and request.method == "GET":
            response.headers["Cache-Control"] = "public, max-age=60"
        
        return response
    
    async def _normal_path(self, request: Request, call_next, config: Dict[str, Any]):
        """Normal processing path with all checks (<500ms target)."""
        # Run comprehensive checks in parallel
        check_tasks = [
            self._async_security_validation(request),
            self._async_rate_limit_check(request.client.host if request.client else "unknown"),
            self._async_request_validation(request)
        ]
        
        # Wait for critical checks
        try:
            check_results = await asyncio.wait_for(
                asyncio.gather(*check_tasks, return_exceptions=True),
                timeout=0.1  # 100ms timeout for checks
            )
            
            # Check for critical failures
            for result in check_results:
                if isinstance(result, Exception) and getattr(result, 'critical', False):
                    return Response(
                        content="Request validation failed",
                        status_code=400
                    )
                    
        except asyncio.TimeoutError:
            logger.warning(f"Middleware checks timed out for {request.url.path}")
            # Continue processing - don't block on slow checks
        
        # Process request
        response = await call_next(request)
        
        # Background logging (non-blocking)
        asyncio.create_task(
            self._async_log_request(request, response)
        )
        
        return response
    
    # Async helper methods for non-blocking operations
    async def _async_security_validation(self, request: Request):
        """Async security validation (non-blocking)."""
        try:
            # Quick security checks
            user_agent = request.headers.get('User-Agent', '')
            
            # Basic bot detection
            if any(bot in user_agent.lower() for bot in ['bot', 'crawler', 'spider']):
                # Log but don't block
                logger.info(f"Bot detected: {user_agent}")
            
            # Check for suspicious patterns
            if len(request.url.path) > 1000:  # Extremely long URLs
                logger.warning(f"Suspicious long URL: {len(request.url.path)} chars")
                
        except Exception as e:
            logger.debug(f"Security validation error: {e}")
    
    async def _async_rate_limit_check(self, client_ip: str):
        """Async rate limit check (non-blocking with cache)."""
        try:
            if CACHE_AVAILABLE:
                cache = get_cache_manager()
                rate_key = f"rate_limit:{client_ip}"
                
                # Get current request count
                current_count = await cache.get(rate_key, default=0)
                
                # Simple rate limiting: 100 requests per minute
                if isinstance(current_count, int) and current_count > 100:
                    logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                    # Don't block, just log for now
                
                # Increment counter
                await cache.set(rate_key, current_count + 1, ttl=60)
                
        except Exception as e:
            logger.debug(f"Rate limit check error: {e}")
    
    async def _async_ip_validation(self, request: Request):
        """Async IP validation (non-blocking)."""
        try:
            if request.client:
                client_ip = request.client.host
                
                # Basic IP validation
                if client_ip and '.' in client_ip:
                    # Simple validation for IPv4
                    parts = client_ip.split('.')
                    if len(parts) == 4:
                        # Log valid IP access
                        logger.debug(f"Valid IP access: {client_ip}")
                        
        except Exception as e:
            logger.debug(f"IP validation error: {e}")
    
    async def _async_request_validation(self, request: Request):
        """Async request validation (non-blocking)."""
        try:
            # Validate request size
            content_length = request.headers.get('Content-Length', '0')
            if content_length.isdigit() and int(content_length) > 10 * 1024 * 1024:  # 10MB
                logger.warning(f"Large request: {content_length} bytes")
            
            # Validate content type for POST/PUT
            if request.method in ['POST', 'PUT', 'PATCH']:
                content_type = request.headers.get('Content-Type', '')
                if not content_type:
                    logger.warning(f"Missing Content-Type for {request.method} request")
                    
        except Exception as e:
            logger.debug(f"Request validation error: {e}")
    
    async def _async_log_request(self, request: Request, response: Response):
        """Asynchronous request logging with performance data."""
        try:
            # Extract performance headers
            response_time = response.headers.get('X-Response-Time', '0')
            route_class = response.headers.get('X-Route-Class', 'unknown')
            
            # Structured logging with performance context
            logger.info(
                f"{request.method} {request.url.path} - {response.status_code} - "
                f"{response_time}ms ({route_class})",
                extra={
                    'method': request.method,
                    'path': request.url.path,
                    'status_code': response.status_code,
                    'response_time_ms': response_time,
                    'route_class': route_class,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'client_ip': request.client.host if request.client else None
                }
            )
            
        except Exception as e:
            # Don't let logging errors affect the response
            logger.debug(f"Async logging error: {e}")
    
    def get_middleware_metrics(self) -> Dict[str, Any]:
        """Get comprehensive middleware performance metrics."""
        with self.metrics_lock:
            metrics = {
                'circuit_breaker': {
                    'state': self.circuit_breaker['state'],
                    'failures': self.circuit_breaker['failures'],
                    'last_failure': self.circuit_breaker['last_failure']
                },
                'route_classes': {},
                'overall_performance': {
                    'total_requests': 0,
                    'avg_response_time_ms': 0.0,
                    'slow_request_rate_percent': 0.0
                }
            }
            
            # Calculate metrics for each route class
            total_requests = 0
            total_time = 0.0
            total_slow = 0
            
            for route_class, data in self.request_metrics.items():
                if data['count'] > 0:
                    avg_time = data['total_time'] / data['count']
                    slow_rate = (data['slow_count'] / data['count']) * 100
                    
                    metrics['route_classes'][route_class] = {
                        'request_count': data['count'],
                        'avg_response_time_ms': round(avg_time, 2),
                        'slow_request_count': data['slow_count'],
                        'slow_request_rate_percent': round(slow_rate, 2),
                        'target_ms': self.route_classes.get(route_class, {}).get('target_ms', 0)
                    }
                    
                    # Accumulate for overall metrics
                    total_requests += data['count']
                    total_time += data['total_time']
                    total_slow += data['slow_count']
            
            # Overall metrics
            if total_requests > 0:
                metrics['overall_performance'] = {
                    'total_requests': total_requests,
                    'avg_response_time_ms': round(total_time / total_requests, 2),
                    'slow_request_rate_percent': round((total_slow / total_requests) * 100, 2)
                }
            
            return metrics


class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    """Monitor and report performance metrics."""
    
    def __init__(self, app):
        super().__init__(app)
        self.metrics = {
            'total_requests': 0,
            'slow_requests': 0,
            'errors': 0,
            'avg_response_time': 0
        }
        self.response_times = []
    
    async def dispatch(self, request: Request, call_next):
        """Track performance metrics."""
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            
            # Track metrics
            response_time = time.perf_counter() - start_time
            self.metrics['total_requests'] += 1
            
            if response_time > 1.0:
                self.metrics['slow_requests'] += 1
            
            if response.status_code >= 500:
                self.metrics['errors'] += 1
            
            # Keep last 100 response times for averaging
            self.response_times.append(response_time)
            if len(self.response_times) > 100:
                self.response_times.pop(0)
            
            self.metrics['avg_response_time'] = sum(self.response_times) / len(self.response_times)
            
            # Add metrics to response headers
            response.headers["X-Response-Time"] = f"{response_time:.3f}"
            response.headers["X-Avg-Response-Time"] = f"{self.metrics['avg_response_time']:.3f}"
            
            return response
            
        except Exception as e:
            self.metrics['errors'] += 1
            logger.error(f"Performance monitor error: {e}")
            raise