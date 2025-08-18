#!/usr/bin/env python3
"""
Comprehensive Performance Benchmark for Velro Backend Auth Endpoint
"""

import asyncio
import aiohttp
import time
import statistics
import json
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import concurrent.futures

@dataclass
class BenchmarkResult:
    """Individual benchmark result"""
    response_time: float
    status_code: int
    success: bool
    server_timing: Dict[str, str]
    timestamp: float
    error: str = None

class AuthPerformanceBenchmarker:
    def __init__(self, endpoint_config: Dict[str, Any]):
        self.endpoint_config = endpoint_config
        self.results: List[BenchmarkResult] = []
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def parse_server_timing(self, header_value: str) -> Dict[str, str]:
        """Parse Server-Timing header"""
        timing_data = {}
        if not header_value:
            return timing_data
        
        entries = header_value.split(',')
        for entry in entries:
            entry = entry.strip()
            if ';dur=' in entry:
                parts = entry.split(';dur=')
                metric_name = parts[0].strip()
                duration = parts[1].strip()
                timing_data[metric_name] = duration
        
        return timing_data
    
    async def single_request(self, request_id: int) -> BenchmarkResult:
        """Perform a single request based on endpoint configuration"""
        start_time = time.perf_counter()
        timestamp = time.time()
        
        try:
            # Prepare request based on method
            if self.endpoint_config['method'] == 'GET':
                request_coro = self.session.get(
                    self.endpoint_config['url'],
                    headers={'Content-Type': 'application/json'}
                )
            else:  # POST
                request_coro = self.session.post(
                    self.endpoint_config['url'],
                    json=self.endpoint_config['payload'],
                    headers={'Content-Type': 'application/json'}
                )
            
            async with request_coro as response:
                end_time = time.perf_counter()
                response_time = (end_time - start_time) * 1000  # Convert to ms
                
                # Parse Server-Timing header and Railway timing headers
                server_timing_header = response.headers.get('Server-Timing', '')
                server_timing = self.parse_server_timing(server_timing_header)
                
                # Also capture Railway's custom timing headers
                processing_time = response.headers.get('x-processing-time', '')
                fastlane_time = response.headers.get('x-fastlane-time-ms', '')
                
                if processing_time:
                    server_timing['x-processing-time'] = processing_time.replace('ms', '')
                if fastlane_time:
                    server_timing['x-fastlane-time-ms'] = fastlane_time
                
                # Read response body
                response_body = await response.text()
                
                # Include error details for failed requests
                error_msg = None
                if not (200 <= response.status < 300):
                    error_msg = f"HTTP {response.status}: {response_body[:200]}..."
                
                return BenchmarkResult(
                    response_time=response_time,
                    status_code=response.status,
                    success=200 <= response.status < 300,
                    server_timing=server_timing,
                    timestamp=timestamp,
                    error=error_msg
                )
        
        except asyncio.TimeoutError:
            end_time = time.perf_counter()
            response_time = (end_time - start_time) * 1000
            return BenchmarkResult(
                response_time=response_time,
                status_code=0,
                success=False,
                server_timing={},
                timestamp=timestamp,
                error="Timeout"
            )
        except Exception as e:
            end_time = time.perf_counter()
            response_time = (end_time - start_time) * 1000
            return BenchmarkResult(
                response_time=response_time,
                status_code=0,
                success=False,
                server_timing={},
                timestamp=timestamp,
                error=str(e)
            )
    
    async def run_sequential_benchmark(self, num_requests: int = 30):
        """Run sequential benchmark tests"""
        print(f"Running {num_requests} sequential requests...")
        
        for i in range(num_requests):
            result = await self.single_request(i)
            self.results.append(result)
            print(f"Request {i+1}/{num_requests}: {result.response_time:.1f}ms - Status: {result.status_code}")
            
            # Small delay between requests to avoid overwhelming the server
            await asyncio.sleep(0.1)
    
    async def run_concurrent_benchmark(self, num_concurrent: int = 5, batches: int = 2):
        """Run concurrent benchmark tests"""
        print(f"Running {batches} batches of {num_concurrent} concurrent requests...")
        
        for batch in range(batches):
            print(f"Batch {batch + 1}/{batches}")
            
            # Create concurrent tasks
            tasks = []
            for i in range(num_concurrent):
                task = asyncio.create_task(self.single_request(f"concurrent_{batch}_{i}"))
                tasks.append(task)
            
            # Wait for all tasks to complete
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in batch_results:
                if isinstance(result, BenchmarkResult):
                    self.results.append(result)
                    print(f"  Concurrent request: {result.response_time:.1f}ms - Status: {result.status_code}")
            
            # Delay between batches
            await asyncio.sleep(1)
    
    def calculate_percentiles(self, values: List[float]) -> Dict[str, float]:
        """Calculate percentile statistics"""
        if not values:
            return {
                'p50': 0,
                'p95': 0,
                'p99': 0,
                'min': 0,
                'max': 0,
                'mean': 0,
                'std': 0
            }
        
        sorted_values = sorted(values)
        return {
            'p50': statistics.median(sorted_values),
            'p95': sorted_values[min(int(len(sorted_values) * 0.95), len(sorted_values) - 1)],
            'p99': sorted_values[min(int(len(sorted_values) * 0.99), len(sorted_values) - 1)],
            'min': min(sorted_values),
            'max': max(sorted_values),
            'mean': statistics.mean(sorted_values),
            'std': statistics.stdev(sorted_values) if len(sorted_values) > 1 else 0
        }
    
    def analyze_server_timing(self) -> Dict[str, Any]:
        """Analyze Server-Timing headers"""
        timing_metrics = {}
        
        for result in self.results:
            if result.server_timing:
                for metric, value in result.server_timing.items():
                    if metric not in timing_metrics:
                        timing_metrics[metric] = []
                    try:
                        timing_metrics[metric].append(float(value))
                    except (ValueError, TypeError):
                        continue
        
        # Calculate statistics for each timing metric
        timing_analysis = {}
        for metric, values in timing_metrics.items():
            if values:
                timing_analysis[metric] = self.calculate_percentiles(values)
        
        return timing_analysis
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        if not self.results:
            return {"error": "No benchmark results available"}
        
        # Separate successful and failed requests
        successful_results = [r for r in self.results if r.success]
        failed_results = [r for r in self.results if not r.success]
        
        # Response times (only successful requests)
        response_times = [r.response_time for r in successful_results]
        
        # Calculate percentiles
        percentiles = self.calculate_percentiles(response_times)
        
        # Analyze Server-Timing headers
        server_timing_analysis = self.analyze_server_timing()
        
        # Status code distribution
        status_codes = {}
        for result in self.results:
            status = result.status_code
            status_codes[status] = status_codes.get(status, 0) + 1
        
        # Error analysis
        errors = {}
        for result in failed_results:
            error = result.error or "Unknown error"
            errors[error] = errors.get(error, 0) + 1
        
        return {
            "benchmark_summary": {
                "total_requests": len(self.results),
                "successful_requests": len(successful_results),
                "failed_requests": len(failed_results),
                "success_rate": len(successful_results) / len(self.results) * 100,
                "test_duration": max(r.timestamp for r in self.results) - min(r.timestamp for r in self.results)
            },
            "response_time_analysis": {
                "percentiles": percentiles,
                "target_compliance": {
                    "p95_under_1500ms": percentiles.get('p95', 0) < 1500,
                    "p95_under_200ms": percentiles.get('p95', 0) < 200,
                    "p95_value_ms": percentiles.get('p95', 0)
                }
            },
            "server_timing_analysis": server_timing_analysis,
            "status_code_distribution": status_codes,
            "error_analysis": errors,
            "raw_results": [
                {
                    "response_time_ms": r.response_time,
                    "status_code": r.status_code,
                    "success": r.success,
                    "server_timing": r.server_timing,
                    "timestamp": r.timestamp,
                    "error": r.error
                } for r in self.results
            ]
        }
    
    def generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []
        
        percentiles = report.get("response_time_analysis", {}).get("percentiles", {})
        p95 = percentiles.get('p95', 0)
        p99 = percentiles.get('p99', 0)
        success_rate = report.get("benchmark_summary", {}).get("success_rate", 0)
        
        # Performance recommendations
        if p95 > 1500:
            recommendations.append("🚨 CRITICAL: p95 latency ({:.1f}ms) exceeds 1.5s target by {:.1f}ms".format(p95, p95 - 1500))
        elif p95 > 200:
            recommendations.append("⚠️  WARNING: p95 latency ({:.1f}ms) exceeds optimal 200ms target by {:.1f}ms".format(p95, p95 - 200))
        else:
            recommendations.append("✅ GOOD: p95 latency ({:.1f}ms) meets performance targets".format(p95))
        
        if p99 > p95 * 3:
            recommendations.append("⚠️  HIGH tail latency: p99 ({:.1f}ms) is {:.1f}x higher than p95 - investigate outliers".format(p99, p99/p95))
        
        # Success rate recommendations
        if success_rate < 95:
            recommendations.append("🚨 RELIABILITY: Success rate ({:.1f}%) is below 95% - investigate failures".format(success_rate))
        elif success_rate < 99:
            recommendations.append("⚠️  Success rate ({:.1f}%) could be improved - target 99%+".format(success_rate))
        else:
            recommendations.append("✅ EXCELLENT: Success rate ({:.1f}%) meets reliability targets".format(success_rate))
        
        # Server timing recommendations
        server_timing = report.get("server_timing_analysis", {})
        if not server_timing:
            recommendations.append("📊 Consider adding Server-Timing headers for detailed performance analysis")
        
        # Concurrency recommendations
        std = percentiles.get('std', 0)
        if std > percentiles.get('mean', 0) * 0.5:
            recommendations.append("⚠️  High response time variability ({:.1f}ms std) - investigate consistency issues".format(std))
        
        return recommendations


async def main():
    """Main benchmark execution"""
    # Test both ping (baseline) and login (auth processing) endpoints
    endpoints = {
        "ping": {
            "url": "https://velro-backend-production.up.railway.app/api/v1/auth/ping",
            "method": "GET",
            "payload": None
        },
        "login": {
            "url": "https://velro-backend-production.up.railway.app/api/v1/auth/login", 
            "method": "POST",
            "payload": {
                "email": "test@example.com",
                "password": "TestPassword123"
            }
        }
    }
    
    print("🚀 Starting Velro Backend Auth Performance Benchmark")
    print("Testing both ping (baseline) and login (auth processing) endpoints")
    print("=" * 60)
    
    all_reports = {}
    
    for endpoint_name, config in endpoints.items():
        print(f"\n🔍 Testing {endpoint_name.upper()} endpoint: {config['url']}")
        if config['payload']:
            print(f"Payload: {json.dumps(config['payload'], indent=2)}")
        print("-" * 40)
        
        async with AuthPerformanceBenchmarker(config) as benchmarker:
            # Run sequential tests (reduced for multiple endpoints)
            await benchmarker.run_sequential_benchmark(15)
            
            # Run concurrent tests
            await benchmarker.run_concurrent_benchmark(5, 1)
            
            print(f"📊 Analyzing {endpoint_name} results...")
            
            # Generate report
            report = benchmarker.generate_report()
            recommendations = benchmarker.generate_recommendations(report)
            
            # Add endpoint info to report
            report["endpoint_info"] = {
                "name": endpoint_name,
                "url": config['url'],
                "method": config['method'],
                "payload": config['payload']
            }
            
            all_reports[endpoint_name] = report
            
            # Print summary for this endpoint
            print(f"\n🎯 {endpoint_name.upper()} SUMMARY")
            print("=" * 30)
            summary = report["benchmark_summary"]
            print(f"Total Requests: {summary['total_requests']}")
            print(f"Successful: {summary['successful_requests']}")
            print(f"Failed: {summary['failed_requests']}")
            print(f"Success Rate: {summary['success_rate']:.1f}%")
            
            percentiles = report["response_time_analysis"]["percentiles"]
            print(f"p50: {percentiles['p50']:.1f}ms | p95: {percentiles['p95']:.1f}ms | p99: {percentiles['p99']:.1f}ms")
            
            if endpoint_name == "ping":
                print("✅ Ping endpoint shows infrastructure baseline performance")
            else:
                target_compliance = report["response_time_analysis"]["target_compliance"]
                print(f"p95 < 1.5s: {'✅' if target_compliance['p95_under_1500ms'] else '❌'} | p95 < 200ms: {'✅' if target_compliance['p95_under_200ms'] else '❌'}")
    
    # Save consolidated results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"auth_benchmark_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(all_reports, f, indent=2)
    
    print(f"\n💾 Consolidated results saved to: {results_file}")
    
    # Print overall analysis
    print(f"\n🎯 OVERALL PERFORMANCE ANALYSIS")
    print("=" * 50)
    
    for endpoint_name, report in all_reports.items():
        percentiles = report["response_time_analysis"]["percentiles"]
        server_timing = report.get("server_timing_analysis", {})
        
        print(f"\n{endpoint_name.upper()} Endpoint:")
        print(f"  Response Time: p50={percentiles['p50']:.1f}ms, p95={percentiles['p95']:.1f}ms")
        
        if server_timing:
            for metric, stats in server_timing.items():
                if isinstance(stats, dict) and 'p50' in stats:
                    print(f"  {metric}: p50={stats['p50']:.1f}ms, p95={stats['p95']:.1f}ms")
        
        recommendations = benchmarker.generate_recommendations(report)
        if recommendations:
            print(f"  Top Recommendation: {recommendations[0]}")
    
    return all_reports


if __name__ == "__main__":
    asyncio.run(main())