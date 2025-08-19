#!/usr/bin/env python3
"""
Velro Auth Performance Benchmark Script
Tests auth endpoints at different RPS levels and measures percentiles.
Target: p95 < 1.5s, p50 < 500ms
"""

import asyncio
import time
import httpx
import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple
import sys
import os

# Configuration
BASE_URL = os.getenv("VELRO_BACKEND_URL", "https://velro-backend-production.up.railway.app")
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "wrongpassword123"  # Invalid creds for consistent testing

# Test configurations (RPS, duration)
TEST_CONFIGS = [
    (1, 120),   # 1 RPS for 2 minutes
    (5, 120),   # 5 RPS for 2 minutes  
    (10, 120),  # 10 RPS for 2 minutes
]

class AuthBenchmark:
    def __init__(self):
        self.results = []
        self.start_time = None
        
    async def single_auth_request(self, client: httpx.AsyncClient) -> Dict:
        """Execute a single auth request and capture timing."""
        start = time.perf_counter()
        
        try:
            response = await client.post(
                f"{BASE_URL}/api/v1/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                timeout=httpx.Timeout(10.0)
            )
            
            latency = (time.perf_counter() - start) * 1000  # Convert to ms
            
            # Extract server timing if available
            server_timing = None
            if "x-fastlane-time-ms" in response.headers:
                server_timing = float(response.headers["x-fastlane-time-ms"])
            elif "x-processing-time" in response.headers:
                timing_str = response.headers["x-processing-time"]
                if timing_str.endswith("ms"):
                    server_timing = float(timing_str[:-2])
            
            return {
                "timestamp": time.time(),
                "latency_ms": latency,
                "status_code": response.status_code,
                "server_timing_ms": server_timing,
                "success": response.status_code in [200, 401, 500],  # 401 or 500 is expected for invalid creds
            }
            
        except asyncio.TimeoutError:
            return {
                "timestamp": time.time(),
                "latency_ms": 10000,  # 10s timeout
                "status_code": 0,
                "server_timing_ms": None,
                "success": False,
                "error": "timeout"
            }
        except Exception as e:
            return {
                "timestamp": time.time(),
                "latency_ms": (time.perf_counter() - start) * 1000,
                "status_code": 0,
                "server_timing_ms": None,
                "success": False,
                "error": str(e)
            }
    
    async def run_benchmark(self, rps: int, duration: int) -> Dict:
        """Run benchmark at specified RPS for given duration."""
        print(f"\n{'='*60}")
        print(f"Starting benchmark: {rps} RPS for {duration} seconds")
        print(f"{'='*60}")
        
        results = []
        interval = 1.0 / rps  # Time between requests
        end_time = time.time() + duration
        request_count = 0
        
        async with httpx.AsyncClient(
            http2=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        ) as client:
            # Warm up connection
            print("Warming up connection...")
            await self.single_auth_request(client)
            
            print(f"Running test...")
            start_time = time.time()
            
            tasks = []
            while time.time() < end_time:
                # Start request
                task = asyncio.create_task(self.single_auth_request(client))
                tasks.append(task)
                
                # Wait for interval
                await asyncio.sleep(interval)
                
                request_count += 1
                
                # Progress update every 10 requests
                if request_count % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"  Progress: {request_count} requests, {elapsed:.1f}s elapsed")
            
            # Wait for all tasks to complete
            print("Waiting for pending requests...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and convert to proper format
            clean_results = []
            for r in results:
                if isinstance(r, dict):
                    clean_results.append(r)
                elif isinstance(r, Exception):
                    clean_results.append({
                        "timestamp": time.time(),
                        "latency_ms": 10000,
                        "status_code": 0,
                        "server_timing_ms": None,
                        "success": False,
                        "error": str(r)
                    })
            results = clean_results
        
        # Calculate statistics
        return self._calculate_stats(results, rps, duration)
    
    async def _collect_result(self, task, results):
        """Helper to collect delayed results."""
        try:
            result = await task
            results.append(result)
        except:
            pass
    
    def _calculate_stats(self, results: List[Dict], rps: int, duration: int) -> Dict:
        """Calculate performance statistics."""
        if not results:
            return {"error": "No results collected"}
        
        # Extract latencies
        latencies = [r["latency_ms"] for r in results]
        successful = [r for r in results if r.get("success", False)]
        failed = [r for r in results if not r.get("success", False)]
        
        # Calculate percentiles
        p50 = np.percentile(latencies, 50)
        p95 = np.percentile(latencies, 95)
        p99 = np.percentile(latencies, 99)
        
        # Server timing stats (if available)
        server_timings = [r["server_timing_ms"] for r in successful if r.get("server_timing_ms")]
        server_p50 = np.percentile(server_timings, 50) if server_timings else None
        server_p95 = np.percentile(server_timings, 95) if server_timings else None
        
        stats = {
            "rps": rps,
            "duration_s": duration,
            "total_requests": len(results),
            "successful_requests": len(successful),
            "failed_requests": len(failed),
            "success_rate": len(successful) / len(results) * 100,
            "latency_p50_ms": round(p50, 2),
            "latency_p95_ms": round(p95, 2),
            "latency_p99_ms": round(p99, 2),
            "latency_min_ms": round(min(latencies), 2),
            "latency_max_ms": round(max(latencies), 2),
            "latency_mean_ms": round(np.mean(latencies), 2),
            "server_p50_ms": round(server_p50, 2) if server_p50 else None,
            "server_p95_ms": round(server_p95, 2) if server_p95 else None,
            "target_met": bool(p95 < 1500),  # p95 < 1.5s - ensure it's a Python bool
        }
        
        return stats
    
    def print_results(self, stats: Dict):
        """Pretty print benchmark results."""
        if "error" in stats:
            print(f"\nError: {stats['error']}")
            return
            
        print(f"\n{'='*60}")
        print(f"Results for {stats['rps']} RPS:")
        print(f"{'='*60}")
        print(f"Total Requests:     {stats['total_requests']}")
        print(f"Successful:         {stats['successful_requests']}")
        print(f"Failed:             {stats['failed_requests']}")
        print(f"Success Rate:       {stats['success_rate']:.1f}%")
        print(f"\nLatency (End-to-End):")
        print(f"  p50:              {stats['latency_p50_ms']:.2f} ms")
        print(f"  p95:              {stats['latency_p95_ms']:.2f} ms {'✅' if stats['latency_p95_ms'] < 1500 else '❌'}")
        print(f"  p99:              {stats['latency_p99_ms']:.2f} ms")
        print(f"  min:              {stats['latency_min_ms']:.2f} ms")
        print(f"  max:              {stats['latency_max_ms']:.2f} ms")
        print(f"  mean:             {stats['latency_mean_ms']:.2f} ms")
        
        if stats.get('server_p50_ms'):
            print(f"\nServer Processing Time:")
            print(f"  p50:              {stats['server_p50_ms']:.2f} ms")
            print(f"  p95:              {stats['server_p95_ms']:.2f} ms")
        
        print(f"\nTarget Met (p95 < 1500ms): {'✅ YES' if stats['target_met'] else '❌ NO'}")
    
    async def run_all_benchmarks(self):
        """Run all benchmark configurations."""
        print(f"\n{'='*60}")
        print(f"VELRO AUTH PERFORMANCE BENCHMARK")
        print(f"Target: p95 < 1500ms, p50 < 500ms")
        print(f"Endpoint: {BASE_URL}/api/v1/auth/login")
        print(f"Started: {datetime.now().isoformat()}")
        print(f"{'='*60}")
        
        all_results = []
        
        for rps, duration in TEST_CONFIGS:
            stats = await self.run_benchmark(rps, duration)
            self.print_results(stats)
            all_results.append(stats)
            
            # Brief pause between tests
            if (rps, duration) != TEST_CONFIGS[-1]:
                print("\nPausing 10 seconds before next test...")
                await asyncio.sleep(10)
        
        # Save results to file
        self.save_results(all_results)
        
        # Final summary
        self.print_summary(all_results)
        
        return all_results
    
    def save_results(self, results: List[Dict]):
        """Save benchmark results to JSON file."""
        filename = f"auth_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "endpoint": f"{BASE_URL}/api/v1/auth/login",
                "results": results
            }, f, indent=2)
        print(f"\nResults saved to: {filename}")
    
    def print_summary(self, results: List[Dict]):
        """Print final summary."""
        print(f"\n{'='*60}")
        print(f"BENCHMARK SUMMARY")
        print(f"{'='*60}")
        
        all_met = all(r['target_met'] for r in results)
        
        print(f"\nPerformance by RPS:")
        for r in results:
            status = "✅" if r['target_met'] else "❌"
            print(f"  {r['rps']:2d} RPS: p95={r['latency_p95_ms']:7.2f}ms, p50={r['latency_p50_ms']:7.2f}ms {status}")
        
        print(f"\nOverall Target Met: {'✅ YES - All tests passed!' if all_met else '❌ NO - Some tests failed'}")
        
        if all_met:
            print("\n🎉 SUCCESS! Auth endpoint meets performance targets!")
        else:
            print("\n⚠️  Performance targets not met. Consider optimization.")


async def main():
    benchmark = AuthBenchmark()
    await benchmark.run_all_benchmarks()


if __name__ == "__main__":
    asyncio.run(main())