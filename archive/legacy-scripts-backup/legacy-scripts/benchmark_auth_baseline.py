#!/usr/bin/env python3
"""
Phase A: Baseline Auth Benchmark
Target: Measure current auth performance with Server-Timing instrumentation
"""

import asyncio
import httpx
import time
import statistics
import json
from typing import List, Dict, Any

# Configuration
API_URL = "https://velro-backend-production.up.railway.app"
TEST_EMAIL = "info@apostle.io"
TEST_PASSWORD = "12345678"
WARM_UP_REQUESTS = 5
BENCHMARK_REQUESTS = 50


async def measure_login(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Measure a single login request with timing data."""
    start = time.perf_counter()
    
    try:
        response = await client.post(
            f"{API_URL}/api/v1/auth/login",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            },
            timeout=httpx.Timeout(20.0)
        )
        
        end = time.perf_counter()
        total_ms = (end - start) * 1000
        
        # Extract Server-Timing header if present
        server_timing = response.headers.get("Server-Timing", "")
        phase_times = {}
        
        if server_timing:
            # Parse Server-Timing header: "pre;dur=10.5, supabase;dur=100.2, post;dur=5.3, total;dur=116.0"
            for part in server_timing.split(","):
                if ";" in part:
                    phase_name = part.split(";")[0].strip()
                    duration_str = part.split("dur=")[1].strip() if "dur=" in part else "0"
                    try:
                        phase_times[phase_name] = float(duration_str)
                    except ValueError:
                        pass
        
        return {
            "success": response.status_code == 200,
            "status_code": response.status_code,
            "total_ms": total_ms,
            "phase_times": phase_times,
            "server_timing_header": server_timing,
            "has_token": "access_token" in response.text if response.status_code == 200 else False
        }
        
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout, TimeoutError) as e:
        return {
            "success": False,
            "status_code": 0,
            "total_ms": 20000,  # Timeout value
            "phase_times": {},
            "error": "timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "total_ms": (time.perf_counter() - start) * 1000,
            "phase_times": {},
            "error": str(e)
        }


async def run_benchmark():
    """Run the baseline benchmark."""
    print(f"🚀 Auth Baseline Benchmark - Phase A")
    print(f"=" * 60)
    print(f"Target: {API_URL}")
    print(f"Warm-up: {WARM_UP_REQUESTS} requests")
    print(f"Benchmark: {BENCHMARK_REQUESTS} requests")
    print(f"=" * 60)
    
    async with httpx.AsyncClient() as client:
        # Check flags endpoint first
        print("\n📊 Checking configuration flags...")
        try:
            flags_response = await client.get(f"{API_URL}/api/v1/public/flags", timeout=5.0)
            if flags_response.status_code == 200:
                flags = flags_response.json()
                print(f"✅ Flags endpoint accessible")
                print(f"   - Fast login: {flags.get('auth', {}).get('fast_login')}")
                print(f"   - HTTP/1.1 fallback: {flags.get('auth', {}).get('http1_fallback')}")
                print(f"   - Target P95: {flags.get('performance', {}).get('target_p95_ms')}ms")
            else:
                print(f"⚠️ Flags endpoint returned {flags_response.status_code}")
        except Exception as e:
            print(f"❌ Flags endpoint error: {e}")
        
        # Warm-up phase
        print(f"\n🔥 Warming up with {WARM_UP_REQUESTS} requests...")
        for i in range(WARM_UP_REQUESTS):
            result = await measure_login(client)
            status = "✅" if result["success"] else "❌"
            print(f"   {i+1}. {status} {result['total_ms']:.0f}ms")
        
        # Benchmark phase
        print(f"\n📊 Running benchmark with {BENCHMARK_REQUESTS} requests...")
        results = []
        phase_data = {
            "pre": [],
            "supabase": [],
            "post": [],
            "total": []
        }
        
        for i in range(BENCHMARK_REQUESTS):
            result = await measure_login(client)
            results.append(result)
            
            # Collect phase times if available
            for phase, duration in result["phase_times"].items():
                if phase in phase_data:
                    phase_data[phase].append(duration)
            
            # Progress indicator
            if (i + 1) % 10 == 0:
                success_rate = sum(1 for r in results if r["success"]) / len(results) * 100
                avg_time = statistics.mean(r["total_ms"] for r in results)
                print(f"   Progress: {i+1}/{BENCHMARK_REQUESTS} | Success: {success_rate:.0f}% | Avg: {avg_time:.0f}ms")
        
        # Calculate statistics
        successful_results = [r for r in results if r["success"]]
        all_times = [r["total_ms"] for r in results]
        successful_times = [r["total_ms"] for r in successful_results]
        
        print(f"\n📈 Results Summary")
        print(f"=" * 60)
        print(f"Total requests: {len(results)}")
        print(f"Successful: {len(successful_results)} ({len(successful_results)/len(results)*100:.1f}%)")
        print(f"Failed: {len(results) - len(successful_results)}")
        
        if successful_times:
            print(f"\n⏱️ Response Time Statistics (successful requests):")
            print(f"   Min: {min(successful_times):.0f}ms")
            print(f"   P50: {statistics.median(successful_times):.0f}ms")
            print(f"   P90: {statistics.quantiles(successful_times, n=10)[8]:.0f}ms")
            print(f"   P95: {statistics.quantiles(successful_times, n=20)[18]:.0f}ms")
            print(f"   P99: {statistics.quantiles(successful_times, n=100)[98]:.0f}ms")
            print(f"   Max: {max(successful_times):.0f}ms")
            print(f"   Mean: {statistics.mean(successful_times):.0f}ms")
            print(f"   StdDev: {statistics.stdev(successful_times):.0f}ms" if len(successful_times) > 1 else "")
        
        # Phase timing breakdown (if available)
        if any(phase_data.values()):
            print(f"\n🔍 Phase Timing Breakdown:")
            for phase, times in phase_data.items():
                if times:
                    print(f"   {phase}:")
                    print(f"      P50: {statistics.median(times):.0f}ms")
                    print(f"      P95: {statistics.quantiles(times, n=20)[18]:.0f}ms" if len(times) >= 20 else f"      P95: N/A")
                    print(f"      Mean: {statistics.mean(times):.0f}ms")
        
        # Target comparison
        print(f"\n🎯 Target Comparison:")
        if successful_times:
            p95 = statistics.quantiles(successful_times, n=20)[18] if len(successful_times) >= 20 else max(successful_times)
            target = 1500  # Target P95 in ms
            
            if p95 <= target:
                print(f"   ✅ P95 ({p95:.0f}ms) meets target ({target}ms)")
            else:
                print(f"   ❌ P95 ({p95:.0f}ms) exceeds target ({target}ms)")
                print(f"   📉 Need to reduce by {p95 - target:.0f}ms ({(p95 - target) / p95 * 100:.1f}%)")
        
        # Error analysis
        errors = [r for r in results if not r["success"]]
        if errors:
            print(f"\n⚠️ Error Analysis:")
            error_types = {}
            for error in errors:
                error_type = error.get("error", f"HTTP {error.get('status_code', 'unknown')}")
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            for error_type, count in error_types.items():
                print(f"   {error_type}: {count} occurrences")
        
        # Save results to file
        output_file = f"auth_benchmark_{int(time.time())}.json"
        with open(output_file, "w") as f:
            json.dump({
                "timestamp": time.time(),
                "api_url": API_URL,
                "warm_up_requests": WARM_UP_REQUESTS,
                "benchmark_requests": BENCHMARK_REQUESTS,
                "results": results,
                "statistics": {
                    "success_rate": len(successful_results) / len(results) * 100 if results else 0,
                    "p50_ms": statistics.median(successful_times) if successful_times else None,
                    "p95_ms": statistics.quantiles(successful_times, n=20)[18] if len(successful_times) >= 20 else None,
                    "mean_ms": statistics.mean(successful_times) if successful_times else None
                },
                "phase_statistics": {
                    phase: {
                        "p50_ms": statistics.median(times) if times else None,
                        "p95_ms": statistics.quantiles(times, n=20)[18] if len(times) >= 20 else None,
                        "mean_ms": statistics.mean(times) if times else None
                    }
                    for phase, times in phase_data.items()
                }
            }, f, indent=2)
        
        print(f"\n💾 Results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())