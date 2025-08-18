"""
PHASE 2: Enterprise Connection Pool Performance Validator
Tests and validates the performance of the 6 specialized connection pools.
Ensures PRD compliance and optimal performance characteristics.
"""

import asyncio
import time
import statistics
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import random

logger = logging.getLogger(__name__)


@dataclass
class PerformanceTestResult:
    """Results from a performance test."""
    test_name: str
    pool_type: str
    total_queries: int
    successful_queries: int
    failed_queries: int
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float
    queries_per_second: float
    success_rate_percent: float
    test_duration_seconds: float
    errors: List[str]


@dataclass
class PoolPerformanceTargets:
    """Performance targets for each pool type."""
    max_avg_response_time_ms: float
    max_p95_response_time_ms: float
    min_success_rate_percent: float
    min_queries_per_second: float


class EnterprisePoolPerformanceValidator:
    """
    Comprehensive performance validator for enterprise connection pools.
    Tests each pool against PRD requirements and performance targets.
    """
    
    def __init__(self):
        self.performance_targets = {
            "auth": PoolPerformanceTargets(
                max_avg_response_time_ms=50.0,
                max_p95_response_time_ms=100.0,
                min_success_rate_percent=99.9,
                min_queries_per_second=100.0
            ),
            "read": PoolPerformanceTargets(
                max_avg_response_time_ms=200.0,
                max_p95_response_time_ms=500.0,
                min_success_rate_percent=99.5,
                min_queries_per_second=50.0
            ),
            "write": PoolPerformanceTargets(
                max_avg_response_time_ms=500.0,
                max_p95_response_time_ms=1000.0,
                min_success_rate_percent=99.9,
                min_queries_per_second=25.0
            ),
            "analytics": PoolPerformanceTargets(
                max_avg_response_time_ms=5000.0,
                max_p95_response_time_ms=10000.0,
                min_success_rate_percent=99.0,
                min_queries_per_second=5.0
            ),
            "admin": PoolPerformanceTargets(
                max_avg_response_time_ms=10000.0,
                max_p95_response_time_ms=30000.0,
                min_success_rate_percent=98.0,
                min_queries_per_second=1.0
            ),
            "batch": PoolPerformanceTargets(
                max_avg_response_time_ms=30000.0,
                max_p95_response_time_ms=60000.0,
                min_success_rate_percent=95.0,
                min_queries_per_second=2.0
            )
        }
        
        self.test_queries = {
            "auth": [
                "SELECT 1 as auth_test",
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'",
                "SELECT CURRENT_TIMESTAMP as auth_timestamp",
                "SELECT version() as auth_version"
            ],
            "read": [
                "SELECT * FROM information_schema.tables WHERE table_schema = 'public' LIMIT 10",
                "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' LIMIT 20",
                "SELECT COUNT(*) FROM information_schema.columns",
                "SELECT DISTINCT table_schema FROM information_schema.tables"
            ],
            "write": [
                "SELECT 1 as write_test",  # Safe write simulation
                "SELECT CURRENT_TIMESTAMP as write_timestamp",
                "SELECT random() as write_random",
                "SELECT generate_series(1, 5) as write_series"
            ],
            "analytics": [
                "SELECT table_schema, COUNT(*) as table_count FROM information_schema.tables GROUP BY table_schema",
                "SELECT data_type, COUNT(*) as column_count FROM information_schema.columns GROUP BY data_type ORDER BY column_count DESC",
                "SELECT LENGTH(table_name) as name_length, COUNT(*) FROM information_schema.tables GROUP BY LENGTH(table_name) ORDER BY name_length",
                "SELECT table_schema, AVG(LENGTH(table_name)) as avg_table_name_length FROM information_schema.tables GROUP BY table_schema"
            ],
            "admin": [
                "SELECT current_database() as admin_db",
                "SELECT current_user as admin_user",
                "SELECT version() as admin_version",
                "SELECT pg_database_size(current_database()) as admin_db_size"
            ],
            "batch": [
                "SELECT generate_series(1, 100) as batch_series",
                "SELECT table_name, column_name FROM information_schema.columns LIMIT 100",
                "SELECT REPEAT('batch_test', 10) as batch_repeat",
                "SELECT array_agg(table_name) FROM information_schema.tables WHERE table_schema = 'public'"
            ]
        }
    
    async def validate_all_pools(self, test_duration_seconds: int = 30) -> Dict[str, Any]:
        """
        Validate performance of all enterprise connection pools.
        
        Args:
            test_duration_seconds: Duration of each test in seconds
            
        Returns:
            Comprehensive validation results
        """
        logger.info(f"🚀 Starting enterprise pool performance validation ({test_duration_seconds}s per pool)")
        
        validation_start_time = time.time()
        results = {}
        overall_success = True
        
        # Import here to avoid circular imports
        try:
            from utils.connection_pool_manager import enterprise_pool_manager, SpecializedPoolType
            
            # Ensure pools are initialized
            if not enterprise_pool_manager.is_initialized:
                logger.info("🔄 Initializing enterprise pools for validation...")
                await enterprise_pool_manager.initialize()
            
            # Test each pool type
            for pool_name in ["auth", "read", "write", "analytics", "admin", "batch"]:
                logger.info(f"🧪 Testing {pool_name} pool performance...")
                
                try:
                    pool_type = SpecializedPoolType(f"{pool_name}_pool")
                    result = await self.test_pool_performance(
                        pool_type, pool_name, test_duration_seconds
                    )
                    results[pool_name] = result
                    
                    # Check if pool meets targets
                    targets = self.performance_targets.get(pool_name)
                    if targets:
                        compliance = self.check_target_compliance(result, targets)
                        results[pool_name]['target_compliance'] = compliance
                        if not compliance['overall_compliant']:
                            overall_success = False
                            logger.warning(f"⚠️ {pool_name} pool failed to meet performance targets")
                    
                except Exception as e:
                    logger.error(f"❌ Error testing {pool_name} pool: {e}")
                    results[pool_name] = {
                        'status': 'error',
                        'error': str(e)
                    }
                    overall_success = False
        
        except ImportError as e:
            logger.error(f"❌ Enterprise pools not available: {e}")
            return {
                'status': 'error',
                'error': 'Enterprise pools not available',
                'message': 'Install asyncpg dependency for enterprise pool support'
            }
        
        validation_duration = time.time() - validation_start_time
        
        # Calculate summary statistics
        summary = self.calculate_summary_statistics(results)
        
        validation_results = {
            'status': 'success' if overall_success else 'partial_success',
            'timestamp': datetime.utcnow().isoformat(),
            'validation_duration_seconds': round(validation_duration, 2),
            'overall_success': overall_success,
            'summary': summary,
            'pool_results': results,
            'performance_targets': {
                pool_name: {
                    'max_avg_response_time_ms': targets.max_avg_response_time_ms,
                    'max_p95_response_time_ms': targets.max_p95_response_time_ms,
                    'min_success_rate_percent': targets.min_success_rate_percent,
                    'min_queries_per_second': targets.min_queries_per_second
                }
                for pool_name, targets in self.performance_targets.items()
            },
            'recommendations': self.generate_recommendations(results)
        }
        
        logger.info(f"✅ Pool validation completed in {validation_duration:.2f}s - Overall success: {overall_success}")
        
        return validation_results
    
    async def test_pool_performance(
        self, 
        pool_type, 
        pool_name: str, 
        test_duration_seconds: int
    ) -> PerformanceTestResult:
        """
        Test performance of a specific pool.
        
        Args:
            pool_type: SpecializedPoolType enum
            pool_name: Human-readable pool name
            test_duration_seconds: Test duration in seconds
            
        Returns:
            Performance test results
        """
        from utils.connection_pool_manager import enterprise_pool_manager
        
        queries = self.test_queries.get(pool_name, ["SELECT 1"])
        response_times = []
        successful_queries = 0
        failed_queries = 0
        errors = []
        
        start_time = time.time()
        end_time = start_time + test_duration_seconds
        
        logger.info(f"🏃 Running {pool_name} pool test for {test_duration_seconds} seconds...")
        
        while time.time() < end_time:
            query = random.choice(queries)
            query_start_time = time.time()
            
            try:
                # Execute query using the specific pool
                await enterprise_pool_manager.execute_query(
                    query,
                    pool_type=pool_type,
                    timeout=30.0  # 30 second timeout
                )
                
                query_time_ms = (time.time() - query_start_time) * 1000
                response_times.append(query_time_ms)
                successful_queries += 1
                
            except Exception as e:
                query_time_ms = (time.time() - query_start_time) * 1000
                response_times.append(query_time_ms)  # Include failed query times
                failed_queries += 1
                errors.append(f"Query failed: {str(e)}")
                logger.debug(f"Query failed in {pool_name} pool: {e}")
            
            # Small delay to prevent overwhelming
            await asyncio.sleep(0.01)  # 10ms delay
        
        test_duration = time.time() - start_time
        total_queries = successful_queries + failed_queries
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = p95_response_time = 0.0
        
        queries_per_second = total_queries / test_duration if test_duration > 0 else 0
        success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
        
        return PerformanceTestResult(
            test_name=f"{pool_name}_pool_performance_test",
            pool_type=pool_name,
            total_queries=total_queries,
            successful_queries=successful_queries,
            failed_queries=failed_queries,
            avg_response_time_ms=round(avg_response_time, 2),
            min_response_time_ms=round(min_response_time, 2),
            max_response_time_ms=round(max_response_time, 2),
            p95_response_time_ms=round(p95_response_time, 2),
            queries_per_second=round(queries_per_second, 2),
            success_rate_percent=round(success_rate, 2),
            test_duration_seconds=round(test_duration, 2),
            errors=errors[:10]  # Limit to first 10 errors
        )
    
    def check_target_compliance(
        self, 
        result: PerformanceTestResult, 
        targets: PoolPerformanceTargets
    ) -> Dict[str, Any]:
        """
        Check if test results meet performance targets.
        
        Args:
            result: Test results
            targets: Performance targets
            
        Returns:
            Compliance analysis
        """
        compliance_checks = {
            'avg_response_time': result.avg_response_time_ms <= targets.max_avg_response_time_ms,
            'p95_response_time': result.p95_response_time_ms <= targets.max_p95_response_time_ms,
            'success_rate': result.success_rate_percent >= targets.min_success_rate_percent,
            'queries_per_second': result.queries_per_second >= targets.min_queries_per_second
        }
        
        overall_compliant = all(compliance_checks.values())
        
        return {
            'overall_compliant': overall_compliant,
            'individual_checks': compliance_checks,
            'targets': {
                'max_avg_response_time_ms': targets.max_avg_response_time_ms,
                'max_p95_response_time_ms': targets.max_p95_response_time_ms,
                'min_success_rate_percent': targets.min_success_rate_percent,
                'min_queries_per_second': targets.min_queries_per_second
            },
            'actual_values': {
                'avg_response_time_ms': result.avg_response_time_ms,
                'p95_response_time_ms': result.p95_response_time_ms,
                'success_rate_percent': result.success_rate_percent,
                'queries_per_second': result.queries_per_second
            }
        }
    
    def calculate_summary_statistics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate summary statistics across all pools."""
        successful_pools = []
        total_queries = 0
        total_successful = 0
        total_failed = 0
        avg_response_times = []
        
        for pool_name, result in results.items():
            if isinstance(result, dict) and 'status' in result and result['status'] == 'error':
                continue
                
            if hasattr(result, 'total_queries'):
                successful_pools.append(pool_name)
                total_queries += result.total_queries
                total_successful += result.successful_queries
                total_failed += result.failed_queries
                avg_response_times.append(result.avg_response_time_ms)
        
        overall_success_rate = (total_successful / total_queries * 100) if total_queries > 0 else 0
        overall_avg_response_time = statistics.mean(avg_response_times) if avg_response_times else 0
        
        return {
            'total_pools_tested': len(results),
            'successful_pools': len(successful_pools),
            'failed_pools': len(results) - len(successful_pools),
            'total_queries_executed': total_queries,
            'total_successful_queries': total_successful,
            'total_failed_queries': total_failed,
            'overall_success_rate_percent': round(overall_success_rate, 2),
            'overall_avg_response_time_ms': round(overall_avg_response_time, 2)
        }
    
    def generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate optimization recommendations based on test results."""
        recommendations = []
        
        for pool_name, result in results.items():
            if isinstance(result, dict) and 'status' in result:
                if result['status'] == 'error':
                    recommendations.append(f"Fix initialization issues with {pool_name} pool")
                continue
            
            if not hasattr(result, 'success_rate_percent'):
                continue
                
            # Check for performance issues
            if result.success_rate_percent < 95:
                recommendations.append(f"Investigate high error rate in {pool_name} pool ({result.success_rate_percent:.1f}% success)")
            
            targets = self.performance_targets.get(pool_name)
            if targets:
                if result.avg_response_time_ms > targets.max_avg_response_time_ms:
                    recommendations.append(f"Optimize {pool_name} pool - response time exceeds target ({result.avg_response_time_ms:.1f}ms vs {targets.max_avg_response_time_ms}ms)")
                
                if result.queries_per_second < targets.min_queries_per_second:
                    recommendations.append(f"Scale up {pool_name} pool - throughput below target ({result.queries_per_second:.1f} vs {targets.min_queries_per_second} QPS)")
        
        if not recommendations:
            recommendations.append("All pools are performing within acceptable parameters")
        
        return recommendations
    
    async def run_concurrent_load_test(
        self, 
        concurrent_connections: int = 50, 
        test_duration_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Run a concurrent load test across all pools to simulate real-world usage.
        
        Args:
            concurrent_connections: Number of concurrent connections per pool
            test_duration_seconds: Duration of the load test
            
        Returns:
            Load test results
        """
        logger.info(f"🏋️ Starting concurrent load test: {concurrent_connections} connections per pool for {test_duration_seconds}s")
        
        try:
            from utils.connection_pool_manager import enterprise_pool_manager, SpecializedPoolType
            
            # Ensure pools are initialized
            if not enterprise_pool_manager.is_initialized:
                await enterprise_pool_manager.initialize()
            
            load_test_tasks = []
            
            # Create concurrent tasks for each pool
            for pool_name in ["auth", "read", "write", "analytics", "admin", "batch"]:
                pool_type = SpecializedPoolType(f"{pool_name}_pool")
                
                for i in range(concurrent_connections):
                    task = asyncio.create_task(
                        self.concurrent_pool_worker(
                            pool_type, pool_name, test_duration_seconds, i
                        )
                    )
                    load_test_tasks.append(task)
            
            logger.info(f"🚀 Launched {len(load_test_tasks)} concurrent tasks")
            
            # Wait for all tasks to complete
            start_time = time.time()
            results = await asyncio.gather(*load_test_tasks, return_exceptions=True)
            test_duration = time.time() - start_time
            
            # Process results
            pool_results = {}
            total_operations = 0
            successful_operations = 0
            errors = []
            
            for result in results:
                if isinstance(result, Exception):
                    errors.append(str(result))
                    continue
                
                if isinstance(result, dict):
                    pool_name = result.get('pool_name')
                    if pool_name not in pool_results:
                        pool_results[pool_name] = {
                            'total_operations': 0,
                            'successful_operations': 0,
                            'errors': 0,
                            'avg_response_time_ms': []
                        }
                    
                    pool_results[pool_name]['total_operations'] += result.get('operations', 0)
                    pool_results[pool_name]['successful_operations'] += result.get('successful', 0)
                    pool_results[pool_name]['errors'] += result.get('errors', 0)
                    if result.get('avg_response_time_ms'):
                        pool_results[pool_name]['avg_response_time_ms'].append(result['avg_response_time_ms'])
                    
                    total_operations += result.get('operations', 0)
                    successful_operations += result.get('successful', 0)
            
            # Calculate summary statistics
            for pool_name in pool_results:
                response_times = pool_results[pool_name]['avg_response_time_ms']
                if response_times:
                    pool_results[pool_name]['avg_response_time_ms'] = round(statistics.mean(response_times), 2)
                else:
                    pool_results[pool_name]['avg_response_time_ms'] = 0.0
            
            success_rate = (successful_operations / total_operations * 100) if total_operations > 0 else 0
            operations_per_second = total_operations / test_duration if test_duration > 0 else 0
            
            return {
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat(),
                'test_configuration': {
                    'concurrent_connections_per_pool': concurrent_connections,
                    'total_concurrent_connections': concurrent_connections * 6,
                    'test_duration_seconds': test_duration_seconds,
                    'actual_duration_seconds': round(test_duration, 2)
                },
                'summary': {
                    'total_operations': total_operations,
                    'successful_operations': successful_operations,
                    'failed_operations': total_operations - successful_operations,
                    'success_rate_percent': round(success_rate, 2),
                    'operations_per_second': round(operations_per_second, 2),
                    'total_errors': len(errors)
                },
                'pool_results': pool_results,
                'errors': errors[:20]  # First 20 errors
            }
            
        except Exception as e:
            logger.error(f"❌ Concurrent load test failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def concurrent_pool_worker(
        self, 
        pool_type, 
        pool_name: str, 
        duration_seconds: int, 
        worker_id: int
    ) -> Dict[str, Any]:
        """Worker task for concurrent load testing."""
        from utils.connection_pool_manager import enterprise_pool_manager
        
        queries = self.test_queries.get(pool_name, ["SELECT 1"])
        operations = 0
        successful = 0
        errors = 0
        response_times = []
        
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            query = random.choice(queries)
            start_time = time.time()
            
            try:
                await enterprise_pool_manager.execute_query(
                    query,
                    pool_type=pool_type,
                    timeout=10.0
                )
                
                response_time_ms = (time.time() - start_time) * 1000
                response_times.append(response_time_ms)
                successful += 1
                
            except Exception:
                errors += 1
            
            operations += 1
            
            # Small delay
            await asyncio.sleep(0.05)  # 50ms delay
        
        avg_response_time = statistics.mean(response_times) if response_times else 0.0
        
        return {
            'pool_name': pool_name,
            'worker_id': worker_id,
            'operations': operations,
            'successful': successful,
            'errors': errors,
            'avg_response_time_ms': round(avg_response_time, 2)
        }


# Global validator instance
pool_validator = EnterprisePoolPerformanceValidator()


async def run_performance_validation(test_duration: int = 30) -> Dict[str, Any]:
    """
    Run comprehensive performance validation of enterprise pools.
    
    Args:
        test_duration: Test duration per pool in seconds
        
    Returns:
        Validation results
    """
    return await pool_validator.validate_all_pools(test_duration)


async def run_load_test(concurrent_connections: int = 50, duration: int = 60) -> Dict[str, Any]:
    """
    Run concurrent load test across all pools.
    
    Args:
        concurrent_connections: Concurrent connections per pool
        duration: Test duration in seconds
        
    Returns:
        Load test results
    """
    return await pool_validator.run_concurrent_load_test(concurrent_connections, duration)