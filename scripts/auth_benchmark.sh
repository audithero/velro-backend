#!/bin/bash

# Auth Hot-Path Benchmark Script
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
    
    # Direct Supabase timing (baseline)
    start=$(date +%s%3N)
    direct_response=$(curl -sS --http1.1 -m 8 \
        -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx0c3Buc2R1emlwbHB1cXhjenZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI2MzM2MTEsImV4cCI6MjA2ODIwOTYxMX0.L1LGSXI1hdSd0I02U3dMcVlL6RHfJmEmuQnb86q9WAw" \
        -H "Content-Type: application/json" \
        -d '{"email":"info@apostle.io","password":"12345678"}' \
        "https://ltspnsduziplpuqxczvy.supabase.co/auth/v1/token?grant_type=password" 2>/dev/null)
    end=$(date +%s%3N)
    direct_time=$((end - start))
    direct_times+=($direct_time)
    
    # Check if direct call succeeded
    if echo "$direct_response" | jq -e '.access_token' > /dev/null 2>&1; then
        echo "  ✅ Direct Supabase: ${direct_time}ms"
    else
        echo "  ❌ Direct Supabase: Failed"
    fi
    
    # Backend login timing
    start=$(date +%s%3N)
    backend_response=$(curl -sS --http1.1 -m 12 \
        -H "Content-Type: application/json" \
        -d '{"email":"info@apostle.io","password":"12345678"}' \
        "https://velro-backend-production.up.railway.app/api/v1/auth/login" 2>/dev/null)
    end=$(date +%s%3N)
    backend_time=$((end - start))
    backend_times+=($backend_time)
    
    # Check if backend call succeeded
    if echo "$backend_response" | jq -e '.access_token' > /dev/null 2>&1; then
        echo "  ✅ Backend Login: ${backend_time}ms"
    else
        echo "  ❌ Backend Login: Failed"
    fi
    
    echo ""
    
    # Small delay between samples
    sleep 1
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
if [ ${sorted_backend[9]} -le 1500 ]; then
    echo "✅ SUCCESS: p95 ≤ 1.5s target achieved!"
else
    echo "⚠️  WARNING: p95 > 1.5s target (${sorted_backend[9]}ms)"
fi

echo ""
echo "Raw data:"
echo "Direct: ${direct_times[@]}"
echo "Backend: ${backend_times[@]}"