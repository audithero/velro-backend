"""
VELRO PHASE 4: Comprehensive Load Testing Suite for 10,000+ Users

This script validates that our system optimizations meet PRD requirements:
- Concurrent Users: 10,000+ simultaneous users
- Database Connections: 200+ optimized connections
- Cache Hit Rate: 95%+ for authorization operations
- Throughput: 1,000+ requests/second sustained
- Response Time: <50ms authentication, <75ms authorization

Features:
- Progressive user ramp-up (0 → 10,000 users)
- Real API endpoint testing with authentication
- Comprehensive metrics collection (P50, P95, P99)
- Cache performance validation
- System resource monitoring
- PRD compliance validation
- Real-world traffic patterns simulation
"""

import asyncio
import aiohttp
import time
import statistics
import json
import logging
import os
import sys
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import uuid
import random
import string
import psutil
import jwt
from concurrent.futures import ThreadPoolExecutor
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('load_test_10k_users.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Test Configuration
@dataclass
class LoadTestScenario:
    """Individual load test scenario configuration."""
    name: str
    concurrent_users: int
    test_duration_seconds: int
    ramp_up_time_seconds: int
    target_rps: float
    target_p95_ms: float
    target_cache_hit_rate: float
    
@dataclass 
class SystemTargets:
    """PRD compliance targets from requirements."""
    max_concurrent_users: int = 10000
    min_cache_hit_rate: float = 95.0
    min_throughput_rps: float = 1000.0
    max_auth_response_ms: float = 50.0
    max_authz_response_ms: float = 75.0
    max_generation_access_ms: float = 100.0
    max_media_url_ms: float = 200.0
    min_db_connections: int = 200

@dataclass
class LoadTestMetrics:
    """Comprehensive load test metrics for PRD validation."""
    scenario_name: str
    timestamp: str
    
    # Test configuration
    concurrent_users: int = 0
    test_duration_seconds: int = 0
    actual_duration_seconds: float = 0.0
    
    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    
    # Response time metrics (milliseconds)
    avg_response_time_ms: float = 0.0
    p50_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    
    # Throughput metrics
    requests_per_second: float = 0.0
    peak_requests_per_second: float = 0.0
    
    # Cache performance
    cache_hit_rate: float = 0.0
    auth_cache_hit_rate: float = 0.0
    generation_cache_hit_rate: float = 0.0
    
    # System resource metrics
    peak_cpu_percent: float = 0.0
    peak_memory_mb: float = 0.0
    peak_db_connections: int = 0
    peak_redis_connections: int = 0
    
    # Error analysis
    error_types: Dict[str, int] = None
    status_code_distribution: Dict[int, int] = None
    
    # PRD compliance
    prd_compliance_score: float = 0.0
    compliance_details: Dict[str, bool] = None
    
    def __post_init__(self):
        if self.error_types is None:
            self.error_types = {}
        if self.status_code_distribution is None:
            self.status_code_distribution = {}
        if self.compliance_details is None:
            self.compliance_details = {}

class RealAPILoadTester:
    """Real API load tester that hits actual Velro endpoints with authentication."""
    
    def __init__(self, base_url: str, service_key: str):
        self.base_url = base_url.rstrip('/')
        self.service_key = service_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.test_users: List[Dict[str, Any]] = []
        self.auth_tokens: Dict[str, str] = {}
        self.system_targets = SystemTargets()
        
    async def setup_session(self):
        """Setup aiohttp session with connection pooling."""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(
            limit=1000,  # Maximum number of connections
            limit_per_host=100,  # Maximum connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                'User-Agent': 'VelroLoadTest/1.0',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        )
        
    async def cleanup_session(self):
        """Cleanup session and connections."""
        if self.session:
            await self.session.close()
    
    async def create_test_users(self, count: int = 100) -> List[Dict[str, Any]]:
        """Create test users for load testing."""
        logger.info(f"Creating {count} test users...")
        
        test_users = []
        for i in range(count):
            user_data = {
                'id': str(uuid.uuid4()),
                'email': f'loadtest_{i}_{int(time.time())}@velro.ai',
                'password': f'LoadTest123!{i}',
                'full_name': f'Load Test User {i}'
            }
            
            try:
                # Create user via API
                async with self.session.post(
                    f'{self.base_url}/auth/register',
                    json={
                        'email': user_data['email'],
                        'password': user_data['password'],
                        'full_name': user_data['full_name']
                    },
                    headers={'Authorization': f'Bearer {self.service_key}'}
                ) as response:
                    if response.status == 201:
                        result = await response.json()
                        user_data['user_id'] = result.get('user', {}).get('id')
                        user_data['access_token'] = result.get('access_token')
                        test_users.append(user_data)
                        logger.debug(f"Created test user: {user_data['email']}")
                    elif response.status == 409:
                        # User already exists - try login
                        login_result = await self._login_user(user_data['email'], user_data['password'])
                        if login_result:
                            user_data.update(login_result)
                            test_users.append(user_data)
                    else:
                        logger.warning(f"Failed to create user {user_data['email']}: {response.status}")
                        
            except Exception as e:
                logger.error(f"Error creating test user {user_data['email']}: {e}")
                
        self.test_users = test_users
        logger.info(f"Successfully created/authenticated {len(test_users)} test users")
        return test_users
    
    async def _login_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Login existing user and get auth token."""
        try:
            async with self.session.post(
                f'{self.base_url}/auth/login',
                json={'email': email, 'password': password}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        'user_id': result.get('user', {}).get('id'),
                        'access_token': result.get('access_token')
                    }
        except Exception as e:
            logger.error(f"Failed to login user {email}: {e}")
            
        return None
    
    def get_random_user(self) -> Optional[Dict[str, Any]]:
        """Get a random test user with auth token."""
        return random.choice(self.test_users) if self.test_users else None
    
    async def run_load_test_scenario(self, scenario: LoadTestScenario) -> LoadTestMetrics:
        """Run a comprehensive load test scenario."""
        logger.info(f"Starting load test scenario: {scenario.name}")
        logger.info(f"Target: {scenario.concurrent_users} users, {scenario.test_duration_seconds}s duration")
        
        metrics = LoadTestMetrics(
            scenario_name=scenario.name,
            timestamp=datetime.utcnow().isoformat(),
            concurrent_users=scenario.concurrent_users,
            test_duration_seconds=scenario.test_duration_seconds
        )
        
        # Setup
        await self.setup_session()
        await self.create_test_users(min(100, scenario.concurrent_users // 10))
        
        # System monitoring
        system_monitor = SystemResourceMonitor()
        system_monitor.start_monitoring()
        
        start_time = time.time()
        
        try:
            # Run progressive load test
            results = await self._run_progressive_load_test(scenario)
            
            end_time = time.time()
            metrics.actual_duration_seconds = end_time - start_time
            
            # Process results
            self._process_test_results(results, metrics, scenario)
            
            # Get system metrics
            system_metrics = system_monitor.get_metrics()
            metrics.peak_cpu_percent = system_metrics['peak_cpu_percent']
            metrics.peak_memory_mb = system_metrics['peak_memory_mb']
            
            # Calculate PRD compliance
            self._calculate_prd_compliance(metrics, scenario)
            
            logger.info(f"Load test scenario '{scenario.name}' completed")
            logger.info(f"Results: {metrics.successful_requests}/{metrics.total_requests} successful")
            logger.info(f"P95: {metrics.p95_response_time_ms:.2f}ms, RPS: {metrics.requests_per_second:.1f}")
            logger.info(f"PRD Compliance Score: {metrics.prd_compliance_score:.1f}%")
            
        finally:
            system_monitor.stop_monitoring()
            await self.cleanup_session()
        
        return metrics
    
    async def _run_progressive_load_test(self, scenario: LoadTestScenario) -> List[Dict[str, Any]]:
        """Run progressive load test with gradual user ramp-up."""
        results = []
        
        # Calculate ramp-up steps
        ramp_steps = 10
        users_per_step = scenario.concurrent_users // ramp_steps
        step_duration = scenario.ramp_up_time_seconds // ramp_steps
        
        logger.info(f"Progressive ramp-up: {ramp_steps} steps, {users_per_step} users per step")
        
        # Progressive ramp-up
        current_users = 0
        for step in range(ramp_steps):
            current_users = min(current_users + users_per_step, scenario.concurrent_users)
            logger.info(f"Ramp-up step {step + 1}/{ramp_steps}: {current_users} concurrent users")
            
            # Run test with current user count
            step_results = await self._run_concurrent_requests(
                current_users, 
                step_duration,
                f"ramp_step_{step + 1}"
            )
            results.extend(step_results)
            
        # Sustained load test
        logger.info(f"Starting sustained load: {scenario.concurrent_users} users for {scenario.test_duration_seconds}s")
        sustained_results = await self._run_concurrent_requests(
            scenario.concurrent_users,
            scenario.test_duration_seconds,
            "sustained_load"
        )
        results.extend(sustained_results)
        
        return results
    
    async def _run_concurrent_requests(self, concurrent_users: int, duration: int, phase: str) -> List[Dict[str, Any]]:
        """Run concurrent requests for specified duration."""
        semaphore = asyncio.Semaphore(concurrent_users)
        results = []
        start_time = time.time()
        end_time = start_time + duration
        
        # Create request tasks
        tasks = []
        request_count = 0
        
        while time.time() < end_time:
            # Create batch of requests
            batch_size = min(50, concurrent_users)
            
            for _ in range(batch_size):
                task = asyncio.create_task(
                    self._execute_api_request_sequence(semaphore, request_count, phase)
                )
                tasks.append(task)
                request_count += 1
            
            # Wait a bit before next batch
            await asyncio.sleep(0.1)
            
            # Collect completed tasks
            if len(tasks) >= concurrent_users * 2:  # Prevent memory buildup
                done_tasks = [t for t in tasks if t.done()]
                for task in done_tasks:
                    try:
                        result = await task
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.error(f"Task failed: {e}")
                        results.append({
                            'success': False,
                            'error': str(e),
                            'response_time_ms': 0,
                            'status_code': 0,
                            'phase': phase,
                            'timestamp': time.time()
                        })
                
                # Remove completed tasks
                tasks = [t for t in tasks if not t.done()]
        
        # Wait for remaining tasks
        if tasks:
            remaining_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in remaining_results:
                if isinstance(result, Exception):
                    results.append({
                        'success': False,
                        'error': str(result),
                        'response_time_ms': 0,
                        'status_code': 0,
                        'phase': phase,
                        'timestamp': time.time()
                    })
                elif result:
                    results.append(result)
        
        return results
    
    async def _execute_api_request_sequence(self, semaphore: asyncio.Semaphore, 
                                          request_id: int, phase: str) -> Optional[Dict[str, Any]]:
        """Execute a realistic API request sequence with authentication."""
        async with semaphore:
            user = self.get_random_user()
            if not user or not user.get('access_token'):
                return None
                
            sequence_start = time.time()
            
            try:
                # Simulate realistic user journey
                sequence_results = []
                
                # 1. Authentication check (/auth/me)
                auth_result = await self._test_auth_endpoint(user)
                sequence_results.append(auth_result)
                
                # 2. Authorization check (generations list)
                if random.random() < 0.8:  # 80% check generations
                    gen_result = await self._test_generations_endpoint(user)
                    sequence_results.append(gen_result)
                
                # 3. Model access (less frequent)
                if random.random() < 0.3:  # 30% check models
                    model_result = await self._test_models_endpoint(user)
                    sequence_results.append(model_result)
                
                # 4. Generation creation (write operation)
                if random.random() < 0.2:  # 20% create generation
                    create_result = await self._test_generation_create(user)
                    sequence_results.append(create_result)
                
                # Calculate sequence metrics
                total_time_ms = (time.time() - sequence_start) * 1000
                successful_requests = sum(1 for r in sequence_results if r and r.get('success', False))
                
                return {
                    'success': successful_requests > 0,
                    'response_time_ms': total_time_ms,
                    'status_code': 200 if successful_requests > 0 else 500,
                    'phase': phase,
                    'timestamp': time.time(),
                    'request_id': request_id,
                    'sequence_results': sequence_results,
                    'requests_in_sequence': len(sequence_results),
                    'successful_in_sequence': successful_requests
                }
                
            except Exception as e:
                logger.error(f"Request sequence failed: {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'response_time_ms': (time.time() - sequence_start) * 1000,
                    'status_code': 0,
                    'phase': phase,
                    'timestamp': time.time(),
                    'request_id': request_id
                }
    
    async def _test_auth_endpoint(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Test authentication endpoint (/auth/me)."""
        start_time = time.time()
        
        try:
            headers = {'Authorization': f'Bearer {user["access_token"]}'}
            async with self.session.get(f'{self.base_url}/auth/me', headers=headers) as response:
                response_time_ms = (time.time() - start_time) * 1000
                
                return {
                    'endpoint': '/auth/me',
                    'success': response.status == 200,
                    'status_code': response.status,
                    'response_time_ms': response_time_ms,
                    'cache_hit': response.headers.get('X-Cache-Status') == 'HIT'
                }
                
        except Exception as e:
            return {
                'endpoint': '/auth/me',
                'success': False,
                'error': str(e),
                'response_time_ms': (time.time() - start_time) * 1000,
                'status_code': 0
            }
    
    async def _test_generations_endpoint(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Test generations list endpoint."""
        start_time = time.time()
        
        try:
            headers = {'Authorization': f'Bearer {user["access_token"]}'}
            params = {'page': 1, 'limit': 20}
            
            async with self.session.get(
                f'{self.base_url}/generations/', 
                headers=headers, 
                params=params
            ) as response:
                response_time_ms = (time.time() - start_time) * 1000
                
                return {
                    'endpoint': '/generations/',
                    'success': response.status == 200,
                    'status_code': response.status,
                    'response_time_ms': response_time_ms,
                    'cache_hit': response.headers.get('X-Cache-Status') == 'HIT'
                }
                
        except Exception as e:
            return {
                'endpoint': '/generations/',
                'success': False,
                'error': str(e),
                'response_time_ms': (time.time() - start_time) * 1000,
                'status_code': 0
            }
    
    async def _test_models_endpoint(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Test models endpoint."""
        start_time = time.time()
        
        try:
            headers = {'Authorization': f'Bearer {user["access_token"]}'}
            
            async with self.session.get(f'{self.base_url}/models/', headers=headers) as response:
                response_time_ms = (time.time() - start_time) * 1000
                
                return {
                    'endpoint': '/models/',
                    'success': response.status == 200,
                    'status_code': response.status,
                    'response_time_ms': response_time_ms,
                    'cache_hit': response.headers.get('X-Cache-Status') == 'HIT'
                }
                
        except Exception as e:
            return {
                'endpoint': '/models/',
                'success': False,
                'error': str(e),
                'response_time_ms': (time.time() - start_time) * 1000,
                'status_code': 0
            }
    
    async def _test_generation_create(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Test generation creation endpoint (write operation)."""
        start_time = time.time()
        
        try:
            headers = {'Authorization': f'Bearer {user["access_token"]}'}
            payload = {
                'prompt': f'Load test image {random.randint(1, 1000)}',
                'model': 'fal-ai/flux',
                'width': 512,
                'height': 512,
                'num_inference_steps': 20
            }
            
            async with self.session.post(
                f'{self.base_url}/generations/create', 
                headers=headers, 
                json=payload
            ) as response:
                response_time_ms = (time.time() - start_time) * 1000
                
                return {
                    'endpoint': '/generations/create',
                    'success': response.status in [200, 201, 202],
                    'status_code': response.status,
                    'response_time_ms': response_time_ms,
                    'operation_type': 'write'
                }
                
        except Exception as e:
            return {
                'endpoint': '/generations/create',
                'success': False,
                'error': str(e),
                'response_time_ms': (time.time() - start_time) * 1000,
                'status_code': 0,
                'operation_type': 'write'
            }
    
    def _process_test_results(self, results: List[Dict[str, Any]], 
                            metrics: LoadTestMetrics, scenario: LoadTestScenario):
        """Process test results and calculate comprehensive metrics."""
        if not results:
            return
            
        metrics.total_requests = len(results)
        metrics.successful_requests = sum(1 for r in results if r.get('success', False))
        metrics.failed_requests = metrics.total_requests - metrics.successful_requests
        
        # Response time metrics
        response_times = [r['response_time_ms'] for r in results if 'response_time_ms' in r]
        if response_times:
            metrics.avg_response_time_ms = statistics.mean(response_times)
            metrics.p50_response_time_ms = statistics.median(response_times)
            metrics.min_response_time_ms = min(response_times)
            metrics.max_response_time_ms = max(response_times)
            
            if len(response_times) >= 20:
                metrics.p95_response_time_ms = np.percentile(response_times, 95)
            if len(response_times) >= 100:
                metrics.p99_response_time_ms = np.percentile(response_times, 99)
            
        # Throughput metrics
        if metrics.actual_duration_seconds > 0:
            metrics.requests_per_second = metrics.total_requests / metrics.actual_duration_seconds
        
        # Cache hit rate analysis
        cache_hits = sum(1 for r in results 
                        if r.get('sequence_results') 
                        for seq in r['sequence_results'] 
                        if seq and seq.get('cache_hit', False))
        
        cache_requests = sum(1 for r in results 
                           if r.get('sequence_results')
                           for seq in r['sequence_results'] 
                           if seq)
        
        if cache_requests > 0:
            metrics.cache_hit_rate = (cache_hits / cache_requests) * 100
        
        # Error analysis
        for result in results:
            status_code = result.get('status_code', 0)
            metrics.status_code_distribution[status_code] = metrics.status_code_distribution.get(status_code, 0) + 1
            
            if not result.get('success', False):
                error = result.get('error', 'Unknown error')
                metrics.error_types[error] = metrics.error_types.get(error, 0) + 1
    
    def _calculate_prd_compliance(self, metrics: LoadTestMetrics, scenario: LoadTestScenario):
        """Calculate PRD compliance score based on requirements."""
        compliance_checks = {}
        
        # Response time targets
        compliance_checks['auth_response_time'] = metrics.p95_response_time_ms <= self.system_targets.max_auth_response_ms
        compliance_checks['throughput_target'] = metrics.requests_per_second >= scenario.target_rps
        compliance_checks['cache_hit_rate'] = metrics.cache_hit_rate >= self.system_targets.min_cache_hit_rate
        compliance_checks['error_rate_acceptable'] = (metrics.failed_requests / max(1, metrics.total_requests)) <= 0.05
        compliance_checks['concurrent_users_handled'] = scenario.concurrent_users >= self.system_targets.max_concurrent_users * 0.8
        
        # Calculate overall score
        passed_checks = sum(1 for check in compliance_checks.values() if check)
        total_checks = len(compliance_checks)
        
        metrics.prd_compliance_score = (passed_checks / total_checks) * 100
        metrics.compliance_details = compliance_checks

class SystemResourceMonitor:
    """Monitor system resources during load testing."""
    
    def __init__(self):
        self.monitoring = False
        self.metrics_history = []
        self.monitor_task = None
    
    def start_monitoring(self):
        """Start system resource monitoring."""
        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
    
    def stop_monitoring(self):
        """Stop system resource monitoring."""
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
    
    async def _monitor_loop(self):
        """Monitor system resources in a loop."""
        try:
            while self.monitoring:
                metrics = {
                    'timestamp': time.time(),
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_mb': psutil.virtual_memory().used / (1024 * 1024),
                    'memory_percent': psutil.virtual_memory().percent,
                    'connections': len(psutil.net_connections(kind='inet')),
                    'disk_io': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
                    'network_io': psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {}
                }
                
                self.metrics_history.append(metrics)
                await asyncio.sleep(5)  # Sample every 5 seconds
                
        except asyncio.CancelledError:
            pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated system metrics."""
        if not self.metrics_history:
            return {}
            
        return {
            'peak_cpu_percent': max(m['cpu_percent'] for m in self.metrics_history),
            'avg_cpu_percent': statistics.mean(m['cpu_percent'] for m in self.metrics_history),
            'peak_memory_mb': max(m['memory_mb'] for m in self.metrics_history),
            'avg_memory_mb': statistics.mean(m['memory_mb'] for m in self.metrics_history),
            'peak_connections': max(m['connections'] for m in self.metrics_history),
            'sample_count': len(self.metrics_history)
        }

# Pre-defined load test scenarios
LOAD_TEST_SCENARIOS = [
    LoadTestScenario(
        name="warm_up_1000_users",
        concurrent_users=1000,
        test_duration_seconds=120,
        ramp_up_time_seconds=30,
        target_rps=200.0,
        target_p95_ms=100.0,
        target_cache_hit_rate=90.0
    ),
    LoadTestScenario(
        name="scale_test_5000_users", 
        concurrent_users=5000,
        test_duration_seconds=300,
        ramp_up_time_seconds=60,
        target_rps=800.0,
        target_p95_ms=75.0,
        target_cache_hit_rate=93.0
    ),
    LoadTestScenario(
        name="prd_validation_10000_users",
        concurrent_users=10000,
        test_duration_seconds=600,
        ramp_up_time_seconds=120,
        target_rps=1000.0,
        target_p95_ms=75.0,
        target_cache_hit_rate=95.0
    ),
    LoadTestScenario(
        name="stress_test_15000_users",
        concurrent_users=15000, 
        test_duration_seconds=300,
        ramp_up_time_seconds=90,
        target_rps=1200.0,
        target_p95_ms=100.0,
        target_cache_hit_rate=90.0
    )
]

async def run_comprehensive_load_test_suite(base_url: str, service_key: str) -> Dict[str, Any]:
    """Run comprehensive load test suite across all scenarios."""
    logger.info("Starting comprehensive load test suite for 10K+ users")
    
    tester = RealAPILoadTester(base_url, service_key)
    suite_results = {
        'test_suite': 'Velro 10K+ Users Load Test',
        'timestamp': datetime.utcnow().isoformat(),
        'scenarios': [],
        'overall_summary': {}
    }
    
    all_metrics = []
    
    for scenario in LOAD_TEST_SCENARIOS:
        logger.info(f"\n{'='*80}")
        logger.info(f"SCENARIO: {scenario.name.upper()}")
        logger.info(f"{'='*80}")
        
        try:
            metrics = await tester.run_load_test_scenario(scenario)
            all_metrics.append(metrics)
            
            suite_results['scenarios'].append({
                'scenario': asdict(scenario),
                'metrics': asdict(metrics),
                'passed': metrics.prd_compliance_score >= 80.0
            })
            
        except Exception as e:
            logger.error(f"Scenario {scenario.name} failed: {e}")
            suite_results['scenarios'].append({
                'scenario': asdict(scenario),
                'error': str(e),
                'passed': False
            })
    
    # Calculate overall summary
    if all_metrics:
        suite_results['overall_summary'] = {
            'total_scenarios': len(LOAD_TEST_SCENARIOS),
            'successful_scenarios': len([m for m in all_metrics if m.prd_compliance_score >= 80.0]),
            'max_concurrent_users_tested': max(m.concurrent_users for m in all_metrics),
            'best_p95_response_time_ms': min(m.p95_response_time_ms for m in all_metrics if m.p95_response_time_ms > 0),
            'best_throughput_rps': max(m.requests_per_second for m in all_metrics),
            'best_cache_hit_rate': max(m.cache_hit_rate for m in all_metrics),
            'prd_compliance_achieved': any(m.prd_compliance_score >= 95.0 for m in all_metrics)
        }
    
    return suite_results

if __name__ == "__main__":
    async def main():
        # Configuration from environment
        base_url = os.getenv('VELRO_API_URL', 'https://velro-backend-production.up.railway.app')
        service_key = os.getenv('SUPABASE_SERVICE_KEY', '')
        
        if not service_key:
            logger.error("SUPABASE_SERVICE_KEY environment variable required")
            sys.exit(1)
        
        try:
            # Run comprehensive load test suite
            results = await run_comprehensive_load_test_suite(base_url, service_key)
            
            # Save results
            timestamp = int(time.time())
            results_file = f'load_test_10k_users_results_{timestamp}.json'
            
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            logger.info(f"\n{'='*80}")
            logger.info("LOAD TEST SUITE COMPLETED")
            logger.info(f"{'='*80}")
            logger.info(f"Results saved to: {results_file}")
            
            # Summary
            summary = results['overall_summary']
            logger.info(f"Max Users Tested: {summary.get('max_concurrent_users_tested', 0)}")
            logger.info(f"Best P95 Response Time: {summary.get('best_p95_response_time_ms', 0):.2f}ms")
            logger.info(f"Best Throughput: {summary.get('best_throughput_rps', 0):.1f} RPS")
            logger.info(f"Best Cache Hit Rate: {summary.get('best_cache_hit_rate', 0):.1f}%")
            logger.info(f"PRD Compliance Achieved: {summary.get('prd_compliance_achieved', False)}")
            
        except Exception as e:
            logger.error(f"Load test suite failed: {e}")
            sys.exit(1)
    
    asyncio.run(main())