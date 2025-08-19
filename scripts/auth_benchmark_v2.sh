#!/bin/bash

# Auth Hot-Path Benchmark Script v2
# Runs 10 samples and calculates p50/p95

echo "🚀 Auth Hot-Path Benchmark - 10 samples"
echo "========================================="
echo ""

# Arrays to store timings
declare -a direct_times
declare -a backend_times

echo "📊 Running 10 samples..."
echo ""

for i in {1..10}; do
    echo "Sample $i/10:"
    
    # Direct Supabase timing (baseline) - using time command
    TIMEFORMAT='%3R'
    exec 3>&1 4>&2
    direct_time=$( { time curl -sS --http1.1 -m 8 \
        -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx0c3Buc2R1emlwbHB1cXhjenZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI2MzM2MTEsImV4cCI6MjA2ODIwOTYxMX0.L1LGSXI1hdSd0I02U3dMcVlL6RHfJmEmuQnb86q9WAw" \
        -H "Content-Type: application/json" \
        -d '{"email":"info@apostle.io","password":"12345678"}' \
        "https://ltspnsduziplpuqxczvy.supabase.co/auth/v1/token?grant_type=password" > /tmp/direct_response.json 2>&4; } 2>&1 1>&3 )
    exec 3>&- 4>&-
    
    # Convert seconds to milliseconds
    direct_ms=$(echo "$direct_time * 1000" | bc | cut -d. -f1)
    direct_times+=($direct_ms)
    
    # Check if direct call succeeded
    if jq -e '.access_token' /tmp/direct_response.json > /dev/null 2>&1; then
        echo "  ✅ Direct Supabase: ${direct_ms}ms"
    else
        echo "  ❌ Direct Supabase: Failed"
        cat /tmp/direct_response.json | jq . 2>/dev/null || cat /tmp/direct_response.json
    fi
    
    # Backend login timing
    exec 3>&1 4>&2
    backend_time=$( { time curl -sS --http1.1 -m 12 \
        -H "Content-Type: application/json" \
        -d '{"email":"info@apostle.io","password":"12345678"}' \
        "https://velro-backend-production.up.railway.app/api/v1/auth/login" > /tmp/backend_response.json 2>&4; } 2>&1 1>&3 )
    exec 3>&- 4>&-
    
    # Convert seconds to milliseconds
    backend_ms=$(echo "$backend_time * 1000" | bc | cut -d. -f1)
    backend_times+=($backend_ms)
    
    # Check if backend call succeeded
    if jq -e '.access_token' /tmp/backend_response.json > /dev/null 2>&1; then
        echo "  ✅ Backend Login: ${backend_ms}ms"
    else
        echo "  ❌ Backend Login: Failed"
        cat /tmp/backend_response.json | jq . 2>/dev/null || cat /tmp/backend_response.json
    fi
    
    echo ""
    
    # Small delay between samples
    sleep 0.5
done

# Sort arrays for percentile calculation
IFS=$'\n' sorted_direct=($(sort -n <<<"${direct_times[*]}"))
IFS=$'\n' sorted_backend=($(sort -n <<<"${backend_times[*]}"))
unset IFS

# Calculate percentiles
echo "========================================="
echo "📈 Results Summary (10 samples):"
echo ""
echo "Direct Supabase (baseline):"
echo "  Min:  ${sorted_direct[0]}ms"
echo "  p50:  ${sorted_direct[4]}ms"
echo "  p95:  ${sorted_direct[9]}ms"
echo "  Max:  ${sorted_direct[9]}ms"
echo ""
echo "Backend /api/v1/auth/login:"
echo "  Min:  ${sorted_backend[0]}ms"
echo "  p50:  ${sorted_backend[4]}ms"
echo "  p95:  ${sorted_backend[9]}ms"
echo "  Max:  ${sorted_backend[9]}ms"
echo ""

# Check if we met the target
if [ "${sorted_backend[9]}" -le "1500" ]; then
    echo "✅ SUCCESS: p95 ≤ 1.5s target achieved!"
else
    echo "⚠️  WARNING: p95 > 1.5s target (${sorted_backend[9]}ms)"
fi

echo ""
echo "Raw data (ms):"
echo "Direct: ${direct_times[@]}"
echo "Backend: ${backend_times[@]}"

# Save results to JSON
cat > auth_benchmark_results.json <<EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "direct_supabase": {
    "min_ms": ${sorted_direct[0]},
    "p50_ms": ${sorted_direct[4]},
    "p95_ms": ${sorted_direct[9]},
    "max_ms": ${sorted_direct[9]},
    "samples": [${direct_times[@]}]
  },
  "backend_login": {
    "min_ms": ${sorted_backend[0]},
    "p50_ms": ${sorted_backend[4]},
    "p95_ms": ${sorted_backend[9]},
    "max_ms": ${sorted_backend[9]},
    "samples": [${backend_times[@]}]
  },
  "target_met": $([ "${sorted_backend[9]}" -le "1500" ] && echo "true" || echo "false")
}
EOF

echo ""
echo "Results saved to auth_benchmark_results.json"