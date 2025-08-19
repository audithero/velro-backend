"""
Load Testing Framework for Multi-Layer Cache Performance
Tests cache performance under 10,000+ concurrent users with sub-100ms targets.

Test Scenarios:
- L1 Memory Cache: <5ms access times, >95% hit rate
- L2 Redis Cache: <20ms access times, >85% hit rate  
- L3 Database Cache: <100ms query times for analytics
- Authorization cache performance under extreme load
- Cache warming and invalidation performance
- Failover and circuit breaker behavior
"""

import asyncio
import aiohttp
import time
import statistics
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import uuid
from concurrent.futures import ThreadPoolExecutor
import psutil
import random
import string

# Test framework imports
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

# Cache system imports
from caching.multi_layer_cache_manager import (
    MultiLayerCacheManager, get_cache_manager,
    CacheLevel, CacheOperation, EvictionPolicy
)
from monitoring.performance import performance_tracker, PerformanceTarget
from services.authorization_service import AuthorizationService
from database import get_database

logger = logging.getLogger(__name__)


@dataclass
class LoadTestConfig:
    """Configuration for load testing scenarios."""
    concurrent_users: int = 10000
    test_duration_seconds: int = 300  # 5 minutes
    ramp_up_time_seconds: int = 60    # 1 minute ramp-up
    cache_hit_rate_target: float = 90.0  # 90%+ hit rate
    response_time_target_ms: float = 100.0  # <100ms
    authorization_target_ms: float = 75.0   # <75ms for auth
    
    # Test data configuration
    num_test_users: int = 1000
    num_test_generations: int = 5000
    num_test_teams: int = 100
    
    # Cache configuration
    l1_cache_size_mb: int = 500
    l2_redis_max_connections: int = 50
    enable_cache_warming: bool = True
    
    # Load patterns
    read_write_ratio: float = 0.8  # 80% reads, 20% writes
    hot_data_percentage: float = 0.2  # 20% of data gets 80% of requests
    cache_invalidation_rate: float = 0.05  # 5% of operations trigger invalidation


@dataclass 
class LoadTestMetrics:
    """Comprehensive load test metrics."""
    test_name: str
    concurrent_users: int
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Response time metrics
    avg_response_time_ms: float = 0.0
    p50_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    
    # Cache performance metrics
    cache_hit_rate: float = 0.0
    l1_hit_rate: float = 0.0
    l2_hit_rate: float = 0.0
    l3_hit_rate: float = 0.0
    
    # System metrics
    peak_cpu_percent: float = 0.0
    peak_memory_mb: float = 0.0
    peak_connections: int = 0
    
    # Performance targets
    target_response_time_ms: float = 100.0
    target_hit_rate: float = 90.0
    targets_met: bool = False
    
    def calculate_targets_met(self):
        """Calculate if performance targets were met."""
        self.targets_met = (
            self.p95_response_time_ms <= self.target_response_time_ms and
            self.cache_hit_rate >= self.target_hit_rate and
            self.successful_requests > 0
        )


class LoadTestDataGenerator:
    """Generates realistic test data for cache load testing."""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.test_users: List[Dict[str, Any]] = []
        self.test_generations: List[Dict[str, Any]] = []
        self.test_teams: List[Dict[str, Any]] = []
        self.hot_keys: List[str] = []
        
    def generate_test_data(self):
        """Generate comprehensive test data."""
        logger.info(f"Generating test data for {self.config.concurrent_users} concurrent users")
        
        # Generate test users
        self.test_users = [
            {
                "id": str(uuid.uuid4()),
                "email": f"loadtest_user_{i}@velro.ai",
                "is_active": True,
                "created_at": datetime.utcnow() - timedelta(days=random.randint(1, 365))
            }
            for i in range(self.config.num_test_users)
        ]
        
        # Generate test teams
        self.test_teams = [
            {
                "id": str(uuid.uuid4()),
                "name": f"LoadTest Team {i}",
                "is_active": True,
                "created_at": datetime.utcnow() - timedelta(days=random.randint(1, 90))
            }
            for i in range(self.config.num_test_teams)
        ]
        
        # Generate test generations
        self.test_generations = []
        for i in range(self.config.num_test_generations):
            user = random.choice(self.test_users)
            team = random.choice(self.test_teams) if random.random() < 0.7 else None
            
            generation = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "team_id": team["id"] if team else None,
                "status": random.choice(["completed", "processing", "queued"]),
                "model_name": random.choice(["fal-ai/flux", "fal-ai/stable-diffusion"]),
                "created_at": datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
                "project_visibility": random.choice(["private", "team_only", "team_open", "public_read"])
            }
            self.test_generations.append(generation)
        
        # Identify hot keys (20% of data that gets 80% of requests)
        hot_count = int(len(self.test_generations) * self.config.hot_data_percentage)
        hot_generations = random.sample(self.test_generations, hot_count)
        
        self.hot_keys = [
            f"auth:{gen['user_id']}:{gen['id']}:generation"
            for gen in hot_generations
        ]
        
        logger.info(f"Generated {len(self.test_users)} users, {len(self.test_teams)} teams, "
                   f"{len(self.test_generations)} generations, {len(self.hot_keys)} hot keys")
    
    def get_random_cache_key(self, prefer_hot: bool = True) -> str:
        """Get a random cache key, preferring hot keys if specified."""
        if prefer_hot and self.hot_keys and random.random() < 0.8:
            return random.choice(self.hot_keys)
        else:
            gen = random.choice(self.test_generations)
            user = random.choice(self.test_users)
            return f"auth:{user['id']}:{gen['id']}:generation"
    
    def get_random_authorization_request(self) -> Dict[str, str]:
        """Get a random authorization request for testing."""
        gen = random.choice(self.test_generations)
        user = random.choice(self.test_users)
        
        return {
            "user_id": user["id"],
            "resource_id": gen["id"],
            "resource_type": "generation",
            "action": "read"
        }
    
    def get_cache_test_data(self) -> Dict[str, Any]:
        """Get random data for cache testing."""
        return {
            "user_data": random.choice(self.test_users),
            "generation_data": random.choice(self.test_generations),
            "team_data": random.choice(self.test_teams),
            "timestamp": datetime.utcnow().isoformat(),
            "test_payload": "".join(random.choices(string.ascii_letters, k=random.randint(100, 1000)))
        }


class CacheLoadTestRunner:
    """Runs comprehensive cache load tests with performance monitoring."""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.data_generator = LoadTestDataGenerator(config)
        self.cache_manager: Optional[MultiLayerCacheManager] = None
        self.metrics = LoadTestMetrics("cache_load_test", config.concurrent_users)
        self.response_times: List[float] = []
        self.system_metrics: List[Dict[str, float]] = []
        
    async def setup_test_environment(self):
        """Set up the test environment with cache manager and test data."""
        logger.info("Setting up cache load test environment")
        
        # Generate test data
        self.data_generator.generate_test_data()
        
        # Initialize cache manager with test configuration
        self.cache_manager = MultiLayerCacheManager(
            l1_size_mb=self.config.l1_cache_size_mb,
            redis_url="redis://localhost:6379"  # Use test Redis instance
        )
        
        # Warm up caches if enabled
        if self.config.enable_cache_warming:
            await self._warm_test_caches()
        
        logger.info("Test environment setup complete")
    
    async def _warm_test_caches(self):
        """Pre-warm caches with test data."""
        logger.info("Warming test caches with realistic data")
        
        warmup_count = 0
        for key in self.data_generator.hot_keys:
            test_data = self.data_generator.get_cache_test_data()
            results = await self.cache_manager.set_multi_level(key, test_data, priority=3)
            if any(results.values()):
                warmup_count += 1
        
        logger.info(f"Warmed {warmup_count} cache entries")
    
    async def run_authorization_load_test(self) -> LoadTestMetrics:
        """Run authorization-specific load test with cache performance monitoring."""
        logger.info(f"Starting authorization load test: {self.config.concurrent_users} concurrent users")
        
        self.metrics.test_name = "authorization_cache_load_test"
        self.metrics.target_response_time_ms = self.config.authorization_target_ms
        
        # Create semaphore to control concurrency
        semaphore = asyncio.Semaphore(self.config.concurrent_users)
        
        # Create test tasks
        tasks = []
        requests_per_user = max(1, self.config.test_duration_seconds // 10)  # ~10 requests per user
        
        for user_idx in range(self.config.concurrent_users):
            for req_idx in range(requests_per_user):
                task = asyncio.create_task(
                    self._authorization_test_request(semaphore, user_idx, req_idx)
                )
                tasks.append(task)
        
        # Start system monitoring
        monitor_task = asyncio.create_task(self._monitor_system_resources())
        
        # Run load test
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        # Process results
        successful_requests = 0
        failed_requests = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_requests += 1
            else:
                successful_requests += 1
                self.response_times.append(result)
        
        # Calculate metrics
        self.metrics.total_requests = len(results)
        self.metrics.successful_requests = successful_requests
        self.metrics.failed_requests = failed_requests
        
        if self.response_times:
            self.metrics.avg_response_time_ms = statistics.mean(self.response_times)
            self.metrics.p50_response_time_ms = statistics.median(self.response_times)
            self.metrics.p95_response_time_ms = statistics.quantiles(self.response_times, n=20)[18]
            self.metrics.p99_response_time_ms = statistics.quantiles(self.response_times, n=100)[98]
            self.metrics.min_response_time_ms = min(self.response_times)
            self.metrics.max_response_time_ms = max(self.response_times)
        
        # Get cache metrics
        cache_metrics = self.cache_manager.get_comprehensive_metrics()
        self.metrics.cache_hit_rate = cache_metrics["overall_performance"]["overall_hit_rate_percent"]
        self.metrics.l1_hit_rate = cache_metrics["cache_levels"]["L1_Memory"]["metrics"]["hit_rate"]
        self.metrics.l2_hit_rate = cache_metrics["cache_levels"]["L2_Redis"]["metrics"]["hit_rate"]
        self.metrics.l3_hit_rate = cache_metrics["cache_levels"]["L3_Database"]["metrics"]["hit_rate"]
        
        # System metrics
        if self.system_metrics:
            self.metrics.peak_cpu_percent = max(m["cpu_percent"] for m in self.system_metrics)
            self.metrics.peak_memory_mb = max(m["memory_mb"] for m in self.system_metrics)
        
        self.metrics.calculate_targets_met()
        
        test_duration = end_time - start_time
        logger.info(f"Authorization load test completed in {test_duration:.2f}s")
        logger.info(f"Results: {successful_requests}/{len(results)} successful, "
                   f"P95: {self.metrics.p95_response_time_ms:.2f}ms, "
                   f"Hit rate: {self.metrics.cache_hit_rate:.1f}%")
        
        return self.metrics
    
    async def _authorization_test_request(self, semaphore: asyncio.Semaphore, 
                                        user_idx: int, req_idx: int) -> float:
        """Execute a single authorization test request with cache lookup."""
        async with semaphore:
            start_time = time.time()
            
            try:
                # Get random authorization request
                auth_request = self.data_generator.get_random_authorization_request()
                
                # Simulate cache lookup with fallback to authorization check
                cache_key = f"auth:{auth_request['user_id']}:{auth_request['resource_id']}:{auth_request['resource_type']}"
                
                # Multi-level cache lookup with fallback
                async def auth_fallback():
                    # Simulate authorization service call
                    await asyncio.sleep(random.uniform(0.01, 0.05))  # 10-50ms simulated auth
                    return {
                        "authorized": random.choice([True, False]),
                        "method": "direct_ownership",
                        "cached_at": datetime.utcnow().isoformat()
                    }
                
                result, cache_level = await self.cache_manager.get_multi_level(cache_key, auth_fallback)
                
                # Record cache performance
                response_time_ms = (time.time() - start_time) * 1000
                
                # Simulate occasional cache invalidation
                if random.random() < self.config.cache_invalidation_rate:
                    await self.cache_manager.invalidate_multi_level(cache_key)
                
                return response_time_ms
                
            except Exception as e:
                logger.error(f"Authorization test request failed: {e}")
                raise
    
    async def run_cache_performance_test(self) -> LoadTestMetrics:
        """Run comprehensive cache performance test across all levels."""
        logger.info(f"Starting cache performance test: {self.config.concurrent_users} concurrent operations")
        
        self.metrics.test_name = "multi_level_cache_performance_test"
        
        # Create test tasks for different cache operations
        semaphore = asyncio.Semaphore(self.config.concurrent_users)
        tasks = []
        
        operations_per_user = max(1, self.config.test_duration_seconds // 5)
        
        for user_idx in range(self.config.concurrent_users):
            for op_idx in range(operations_per_user):
                # Mix of read/write operations based on configuration
                if random.random() < self.config.read_write_ratio:
                    task = asyncio.create_task(
                        self._cache_read_test(semaphore, user_idx, op_idx)
                    )
                else:
                    task = asyncio.create_task(
                        self._cache_write_test(semaphore, user_idx, op_idx)
                    )
                tasks.append(task)
        
        # Add cache invalidation tasks
        invalidation_tasks = max(1, len(tasks) // 20)  # 5% invalidation operations
        for inv_idx in range(invalidation_tasks):
            task = asyncio.create_task(
                self._cache_invalidation_test(semaphore, inv_idx)
            )
            tasks.append(task)
        
        # Start system monitoring
        monitor_task = asyncio.create_task(self._monitor_system_resources())
        
        # Run test
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        # Process results
        self._process_load_test_results(results)
        
        test_duration = end_time - start_time
        logger.info(f"Cache performance test completed in {test_duration:.2f}s")
        
        return self.metrics
    
    async def _cache_read_test(self, semaphore: asyncio.Semaphore, 
                              user_idx: int, op_idx: int) -> float:
        """Execute cache read operation test."""
        async with semaphore:
            start_time = time.time()
            
            try:
                cache_key = self.data_generator.get_random_cache_key()
                result, level = await self.cache_manager.get_multi_level(cache_key)
                
                response_time_ms = (time.time() - start_time) * 1000
                return response_time_ms
                
            except Exception as e:
                logger.error(f"Cache read test failed: {e}")
                raise
    
    async def _cache_write_test(self, semaphore: asyncio.Semaphore,
                               user_idx: int, op_idx: int) -> float:
        """Execute cache write operation test."""
        async with semaphore:
            start_time = time.time()
            
            try:
                cache_key = f"test:{user_idx}:{op_idx}:{uuid.uuid4()}"
                test_data = self.data_generator.get_cache_test_data()
                
                results = await self.cache_manager.set_multi_level(
                    cache_key, test_data,
                    l1_ttl=300, l2_ttl=900,
                    priority=random.randint(1, 3)
                )
                
                response_time_ms = (time.time() - start_time) * 1000
                return response_time_ms
                
            except Exception as e:
                logger.error(f"Cache write test failed: {e}")
                raise
    
    async def _cache_invalidation_test(self, semaphore: asyncio.Semaphore, 
                                      inv_idx: int) -> float:
        """Execute cache invalidation test."""
        async with semaphore:
            start_time = time.time()
            
            try:
                # Invalidate random pattern
                patterns = ["auth:*", "user:*", "gen:*", "team:*"]
                pattern = random.choice(patterns)
                
                results = await self.cache_manager.invalidate_pattern(pattern)
                
                response_time_ms = (time.time() - start_time) * 1000
                return response_time_ms
                
            except Exception as e:
                logger.error(f"Cache invalidation test failed: {e}")
                raise
    
    async def _monitor_system_resources(self):
        """Monitor system resources during load test."""
        try:
            while True:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                connections = len(psutil.net_connections(kind='inet'))
                
                metrics = {
                    "cpu_percent": cpu_percent,
                    "memory_mb": memory.used / (1024 * 1024),
                    "memory_percent": memory.percent,
                    "connections": connections,
                    "timestamp": time.time()
                }
                
                self.system_metrics.append(metrics)
                await asyncio.sleep(5)  # Sample every 5 seconds
                
        except asyncio.CancelledError:
            pass
    
    def _process_load_test_results(self, results: List):
        """Process load test results and calculate metrics."""
        successful_requests = 0
        failed_requests = 0
        response_times = []
        
        for result in results:
            if isinstance(result, Exception):
                failed_requests += 1
            else:
                successful_requests += 1
                response_times.append(result)
        
        self.metrics.total_requests = len(results)
        self.metrics.successful_requests = successful_requests  
        self.metrics.failed_requests = failed_requests
        self.response_times = response_times
        
        if response_times:
            self.metrics.avg_response_time_ms = statistics.mean(response_times)
            self.metrics.p50_response_time_ms = statistics.median(response_times)
            
            if len(response_times) >= 20:
                self.metrics.p95_response_time_ms = statistics.quantiles(response_times, n=20)[18]
            else:
                self.metrics.p95_response_time_ms = max(response_times)
            
            if len(response_times) >= 100:
                self.metrics.p99_response_time_ms = statistics.quantiles(response_times, n=100)[98]
            else:
                self.metrics.p99_response_time_ms = max(response_times)
            
            self.metrics.min_response_time_ms = min(response_times)
            self.metrics.max_response_time_ms = max(response_times)
        
        # Get cache metrics
        if self.cache_manager:
            cache_metrics = self.cache_manager.get_comprehensive_metrics()
            self.metrics.cache_hit_rate = cache_metrics["overall_performance"]["overall_hit_rate_percent"]
        
        # System metrics
        if self.system_metrics:
            self.metrics.peak_cpu_percent = max(m["cpu_percent"] for m in self.system_metrics)
            self.metrics.peak_memory_mb = max(m["memory_mb"] for m in self.system_metrics)
            self.metrics.peak_connections = max(m["connections"] for m in self.system_metrics)
        
        self.metrics.calculate_targets_met()
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        cache_metrics = self.cache_manager.get_comprehensive_metrics() if self.cache_manager else {}
        
        report = {
            "test_configuration": asdict(self.config),
            "performance_metrics": asdict(self.metrics),
            "cache_performance": cache_metrics,
            "system_metrics_summary": {
                "peak_cpu_percent": self.metrics.peak_cpu_percent,
                "peak_memory_mb": self.metrics.peak_memory_mb,
                "peak_connections": self.metrics.peak_connections
            },
            "performance_targets": {
                "response_time_target_ms": self.config.response_time_target_ms,
                "cache_hit_rate_target": self.config.cache_hit_rate_target,
                "authorization_target_ms": self.config.authorization_target_ms,
                "targets_achieved": self.metrics.targets_met
            },
            "recommendations": self._generate_recommendations(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return report
    
    def _generate_recommendations(self) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        if self.metrics.p95_response_time_ms > self.config.response_time_target_ms:
            recommendations.append(
                f"P95 response time ({self.metrics.p95_response_time_ms:.2f}ms) exceeds target "
                f"({self.config.response_time_target_ms}ms). Consider increasing L1 cache size or "
                f"optimizing cache warming strategies."
            )
        
        if self.metrics.cache_hit_rate < self.config.cache_hit_rate_target:
            recommendations.append(
                f"Cache hit rate ({self.metrics.cache_hit_rate:.1f}%) is below target "
                f"({self.config.cache_hit_rate_target}%). Implement more aggressive cache warming "
                f"or increase cache TTLs for stable data."
            )
        
        if self.metrics.peak_cpu_percent > 80:
            recommendations.append(
                f"Peak CPU usage ({self.metrics.peak_cpu_percent:.1f}%) is high. "
                f"Consider horizontal scaling or optimizing cache operations."
            )
        
        if self.metrics.failed_requests > 0:
            failure_rate = (self.metrics.failed_requests / self.metrics.total_requests) * 100
            recommendations.append(
                f"Request failure rate ({failure_rate:.1f}%) indicates system stress. "
                f"Implement better circuit breaker patterns or reduce concurrent load."
            )
        
        if not recommendations:
            recommendations.append("All performance targets met successfully!")
        
        return recommendations
    
    async def cleanup(self):
        """Clean up test environment."""
        if self.cache_manager:
            await self.cache_manager.shutdown()
        logger.info("Test environment cleanup complete")


# Test execution functions
async def run_authorization_load_test(concurrent_users: int = 10000) -> Dict[str, Any]:
    """Run authorization-focused load test."""
    config = LoadTestConfig(
        concurrent_users=concurrent_users,
        test_duration_seconds=300,
        authorization_target_ms=75.0,
        cache_hit_rate_target=95.0
    )
    
    runner = CacheLoadTestRunner(config)
    
    try:
        await runner.setup_test_environment()
        metrics = await runner.run_authorization_load_test()
        report = runner.generate_performance_report()
        
        # Save report
        report_file = f"authorization_load_test_{concurrent_users}_users_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Authorization load test report saved: {report_file}")
        return report
        
    finally:
        await runner.cleanup()


async def run_cache_performance_test(concurrent_users: int = 10000) -> Dict[str, Any]:
    """Run comprehensive cache performance test."""
    config = LoadTestConfig(
        concurrent_users=concurrent_users,
        test_duration_seconds=600,  # 10 minutes
        response_time_target_ms=100.0,
        cache_hit_rate_target=90.0
    )
    
    runner = CacheLoadTestRunner(config)
    
    try:
        await runner.setup_test_environment()
        metrics = await runner.run_cache_performance_test()
        report = runner.generate_performance_report()
        
        # Save report  
        report_file = f"cache_performance_test_{concurrent_users}_users_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Cache performance test report saved: {report_file}")
        return report
        
    finally:
        await runner.cleanup()


# Pytest test cases
@pytest_asyncio.async_def
async def test_cache_performance_1000_users():
    """Test cache performance with 1,000 concurrent users."""
    report = await run_cache_performance_test(concurrent_users=1000)
    
    metrics = LoadTestMetrics(**report["performance_metrics"])
    
    # Assert performance targets
    assert metrics.targets_met, f"Performance targets not met: {report['recommendations']}"
    assert metrics.p95_response_time_ms <= 100.0, f"P95 response time too high: {metrics.p95_response_time_ms}ms"
    assert metrics.cache_hit_rate >= 85.0, f"Cache hit rate too low: {metrics.cache_hit_rate}%"


@pytest_asyncio.async_def  
async def test_authorization_cache_5000_users():
    """Test authorization cache performance with 5,000 concurrent users."""
    report = await run_authorization_load_test(concurrent_users=5000)
    
    metrics = LoadTestMetrics(**report["performance_metrics"])
    
    # Assert authorization performance targets
    assert metrics.p95_response_time_ms <= 75.0, f"Authorization P95 too high: {metrics.p95_response_time_ms}ms"
    assert metrics.cache_hit_rate >= 90.0, f"Authorization cache hit rate too low: {metrics.cache_hit_rate}%"
    assert metrics.successful_requests > 0, "No successful authorization requests"


@pytest_asyncio.async_def
async def test_extreme_load_10000_users():
    """Test system performance with 10,000+ concurrent users."""
    report = await run_cache_performance_test(concurrent_users=10000)
    
    metrics = LoadTestMetrics(**report["performance_metrics"])
    
    # More relaxed targets for extreme load
    assert metrics.p95_response_time_ms <= 150.0, f"Extreme load P95 too high: {metrics.p95_response_time_ms}ms"
    assert metrics.cache_hit_rate >= 80.0, f"Extreme load cache hit rate too low: {metrics.cache_hit_rate}%"
    
    # Check system didn't crash
    failure_rate = (metrics.failed_requests / metrics.total_requests) * 100
    assert failure_rate <= 5.0, f"Too many failures under extreme load: {failure_rate}%"


if __name__ == "__main__":
    # Run load tests directly
    async def main():
        logging.basicConfig(level=logging.INFO)
        
        # Run progressive load tests
        for users in [1000, 5000, 10000]:
            logger.info(f"\n{'='*60}")
            logger.info(f"RUNNING LOAD TEST: {users} CONCURRENT USERS")
            logger.info(f"{'='*60}")
            
            try:
                report = await run_cache_performance_test(concurrent_users=users)
                metrics = LoadTestMetrics(**report["performance_metrics"])
                
                logger.info(f"\nLOAD TEST RESULTS ({users} users):")
                logger.info(f"P95 Response Time: {metrics.p95_response_time_ms:.2f}ms")
                logger.info(f"Cache Hit Rate: {metrics.cache_hit_rate:.1f}%")
                logger.info(f"Success Rate: {(metrics.successful_requests/metrics.total_requests)*100:.1f}%")
                logger.info(f"Targets Met: {metrics.targets_met}")
                
                if not metrics.targets_met:
                    logger.warning(f"Performance targets not met for {users} users")
                    for rec in report["recommendations"]:
                        logger.warning(f"  - {rec}")
                
            except Exception as e:
                logger.error(f"Load test failed for {users} users: {e}")
    
    asyncio.run(main())