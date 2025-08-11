#!/bin/bash

# 📊 Production Deployment Monitor
# Comprehensive health monitoring and alerting for blue-green deployment
# Usage: ./scripts/deployment-monitor.sh [duration] [interval]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
MONITOR_DURATION=${1:-300}  # Default 5 minutes
CHECK_INTERVAL=${2:-30}    # Default 30 seconds
ALERT_THRESHOLD_ERROR_RATE=5  # Percentage
ALERT_THRESHOLD_RESPONSE_TIME=2000  # Milliseconds
CONSECUTIVE_FAILURES_THRESHOLD=3

# URLs
KONG_URL="https://kong-production.up.railway.app"
BACKEND_URL="https://velro-003-backend-production.up.railway.app"
FRONTEND_URL="https://velro-003-frontend-production.up.railway.app"

# Monitoring state
declare -A service_status
declare -A error_counts
declare -A consecutive_failures
declare -A response_times

# Initialize monitoring state
init_monitoring_state() {
    service_status[kong]=unknown
    service_status[backend]=unknown
    service_status[frontend]=unknown
    
    error_counts[kong]=0
    error_counts[backend]=0
    error_counts[frontend]=0
    
    consecutive_failures[kong]=0
    consecutive_failures[backend]=0
    consecutive_failures[frontend]=0
    
    response_times[kong]=0
    response_times[backend]=0
    response_times[frontend]=0
}

# Logging functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

alert() {
    echo -e "${RED}🚨 ALERT: $1${NC}"
}

info() {
    echo -e "${CYAN}ℹ️ $1${NC}"
}

# Function to test service health with timing
test_service_health() {
    local service_name=$1
    local url=$2
    local expected_codes=$3
    local auth_header=$4
    
    local start_time=$(date +%s%N)
    local response_code
    local response_time
    
    if [ -n "$auth_header" ]; then
        response_code=$(curl -s -H "$auth_header" -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
    else
        response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
    fi
    
    local end_time=$(date +%s%N)
    response_time=$(( (end_time - start_time) / 1000000 )) # Convert to milliseconds
    
    response_times[$service_name]=$response_time
    
    # Check if response code is expected
    if [[ "$expected_codes" =~ $response_code ]] && [ "$response_code" != "000" ]; then
        service_status[$service_name]=healthy
        consecutive_failures[$service_name]=0
        return 0
    else
        service_status[$service_name]=unhealthy
        ((consecutive_failures[$service_name]++))
        ((error_counts[$service_name]++))
        return 1
    fi
}

# Function to check Kong Gateway health
check_kong_health() {
    local kong_auth_header=""
    if [ -n "$KONG_API_KEY" ]; then
        kong_auth_header="X-API-Key: $KONG_API_KEY"
    fi
    
    # Test Kong Gateway (expecting 401 without key, or 400/422 with key)
    if [ -n "$KONG_API_KEY" ]; then
        test_service_health "kong" "$KONG_URL/fal/flux-dev" "400|422|405" "$kong_auth_header"
    else
        test_service_health "kong" "$KONG_URL/" "401" ""
    fi
}

# Function to check backend health
check_backend_health() {
    test_service_health "backend" "$BACKEND_URL/health" "200" ""
}

# Function to check frontend health
check_frontend_health() {
    test_service_health "frontend" "$FRONTEND_URL/" "200" ""
}

# Function to analyze trends and detect issues
analyze_health_trends() {
    local service=$1
    local current_status=${service_status[$service]}
    local consecutive_fails=${consecutive_failures[$service]}
    local response_time=${response_times[$service]}
    
    # Check for consecutive failures
    if [ "$consecutive_fails" -ge "$CONSECUTIVE_FAILURES_THRESHOLD" ]; then
        alert "$service has failed $consecutive_fails consecutive times"
        return 1
    fi
    
    # Check response time
    if [ "$response_time" -gt "$ALERT_THRESHOLD_RESPONSE_TIME" ]; then
        warning "$service response time high: ${response_time}ms"
    fi
    
    return 0
}

# Function to generate health report
generate_health_report() {
    local check_number=$1
    local total_checks=$2
    
    echo ""
    echo "📊 Health Check $check_number/$total_checks - $(date)"
    echo "============================================="
    
    # Service status summary
    for service in kong backend frontend; do
        local status=${service_status[$service]}
        local failures=${consecutive_failures[$service]}
        local errors=${error_counts[$service]}
        local response_time=${response_times[$service]}
        
        case $status in
            "healthy")
                success "$service: HEALTHY (${response_time}ms, $errors errors)"
                ;;
            "unhealthy")
                error "$service: UNHEALTHY (${response_time}ms, $failures consecutive failures)"
                ;;
            *)
                warning "$service: UNKNOWN STATUS"
                ;;
        esac
    done
    
    # Overall system health
    local healthy_services=0
    for service in kong backend frontend; do
        if [ "${service_status[$service]}" = "healthy" ]; then
            ((healthy_services++))
        fi
    done
    
    echo ""
    if [ $healthy_services -eq 3 ]; then
        success "SYSTEM STATUS: ALL SERVICES HEALTHY ✅"
    elif [ $healthy_services -eq 2 ]; then
        warning "SYSTEM STATUS: PARTIAL SERVICE ISSUES ⚠️"
    else
        alert "SYSTEM STATUS: CRITICAL - MULTIPLE SERVICE FAILURES 🚨"
    fi
    
    echo "============================================="
}

# Function to test team collaboration endpoints
test_team_endpoints() {
    log "👥 Testing team collaboration endpoints..."
    
    local team_endpoints=(
        "/api/teams"
        "/api/auth/profile"
        "/api/projects"
        "/api/generations"
    )
    
    local endpoint_failures=0
    
    for endpoint in "${team_endpoints[@]}"; do
        local response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BACKEND_URL$endpoint" 2>/dev/null || echo "000")
        
        # Expecting 401 (unauthorized) for these endpoints
        if [[ "$response_code" =~ ^(401|422|405)$ ]]; then
            success "Team endpoint $endpoint: Available"
        else
            warning "Team endpoint $endpoint: Unexpected response ($response_code)"
            ((endpoint_failures++))
        fi
    done
    
    if [ $endpoint_failures -eq 0 ]; then
        success "All team collaboration endpoints available"
    else
        warning "$endpoint_failures team endpoints have issues"
    fi
}

# Function to test Kong Gateway routing
test_kong_routing() {
    if [ -z "$KONG_API_KEY" ]; then
        warning "Kong API key not available - skipping routing tests"
        return 0
    fi
    
    log "🔗 Testing Kong Gateway AI model routing..."
    
    local kong_routes=(
        "/fal/flux-dev"
        "/fal/flux-pro-ultra"
        "/fal/imagen4-ultra"
    )
    
    local routing_failures=0
    
    for route in "${kong_routes[@]}"; do
        local response_code=$(curl -s -H "X-API-Key: $KONG_API_KEY" -o /dev/null -w "%{http_code}" --max-time 10 "$KONG_URL$route" 2>/dev/null || echo "000")
        
        # Expecting 400/422 (bad request) for empty POST requests
        if [[ "$response_code" =~ ^(400|422|405)$ ]]; then
            success "Kong route $route: Working"
        else
            warning "Kong route $route: Unexpected response ($response_code)"
            ((routing_failures++))
        fi
    done
    
    if [ $routing_failures -eq 0 ]; then
        success "All Kong Gateway routes working"
    else
        warning "$routing_failures Kong routes have issues"
    fi
}

# Function to perform comprehensive system test
perform_system_test() {
    local check_number=$1
    
    log "🧪 Performing comprehensive system test ($check_number)..."
    
    # Test core services
    check_kong_health
    check_backend_health
    check_frontend_health
    
    # Analyze trends for each service
    for service in kong backend frontend; do
        analyze_health_trends $service
    done
    
    # Additional tests every 5th check
    if [ $((check_number % 5)) -eq 0 ]; then
        test_team_endpoints
        test_kong_routing
    fi
    
    generate_health_report $check_number
}

# Function to generate final monitoring report
generate_final_report() {
    local total_checks=$1
    local start_time=$2
    local end_time=$3
    
    echo ""
    echo "🏁 ==============================================="
    echo "📊 FINAL DEPLOYMENT MONITORING REPORT"
    echo "🏁 ==============================================="
    echo ""
    echo "Monitoring Period: $(date -d "@$start_time") to $(date -d "@$end_time")"
    echo "Total Duration: $((end_time - start_time)) seconds"
    echo "Total Health Checks: $total_checks"
    echo "Check Interval: $CHECK_INTERVAL seconds"
    echo ""
    
    # Service reliability summary
    echo "📈 Service Reliability Summary:"
    echo "================================"
    
    for service in kong backend frontend; do
        local total_errors=${error_counts[$service]}
        local success_rate=$(( (total_checks - total_errors) * 100 / total_checks ))
        local avg_response_time=${response_times[$service]}  # This is the last recorded time
        
        echo "🔧 $service:"
        echo "   Success Rate: $success_rate%"
        echo "   Total Errors: $total_errors"
        echo "   Last Response Time: ${avg_response_time}ms"
        echo "   Current Status: ${service_status[$service]}"
        echo ""
    done
    
    # Overall assessment
    local total_errors_all=$((error_counts[kong] + error_counts[backend] + error_counts[frontend]))
    local overall_success_rate=$(( ((total_checks * 3) - total_errors_all) * 100 / (total_checks * 3) ))
    
    echo "🎯 Overall Assessment:"
    echo "======================"
    echo "Overall Success Rate: $overall_success_rate%"
    
    if [ $overall_success_rate -ge 95 ]; then
        success "EXCELLENT - Deployment is performing exceptionally well"
        echo "✅ System is stable and ready for full production load"
    elif [ $overall_success_rate -ge 90 ]; then
        success "GOOD - Deployment is performing well"
        echo "✅ System is stable with minor issues"
    elif [ $overall_success_rate -ge 80 ]; then
        warning "MODERATE - Some performance issues detected"
        echo "⚠️ System needs attention but is functional"
    else
        error "POOR - Significant issues detected"
        echo "🚨 System may need immediate attention or rollback"
    fi
    
    echo ""
    echo "🔗 Service URLs:"
    echo "  Kong Gateway: $KONG_URL"
    echo "  Backend API: $BACKEND_URL"
    echo "  Frontend UI: $FRONTEND_URL"
    echo ""
    
    # Recommendations
    echo "📋 Recommendations:"
    echo "==================="
    
    if [ ${error_counts[kong]} -gt 0 ]; then
        echo "🔧 Kong Gateway: Review Kong configuration and API key setup"
    fi
    
    if [ ${error_counts[backend]} -gt 0 ]; then
        echo "🔧 Backend API: Check application logs and database connectivity"
    fi
    
    if [ ${error_counts[frontend]} -gt 0 ]; then
        echo "🔧 Frontend UI: Verify frontend build and static asset delivery"
    fi
    
    if [ $total_errors_all -eq 0 ]; then
        echo "🎉 No issues detected - system is performing optimally!"
    fi
    
    echo ""
    echo "📊 Monitoring completed successfully"
}

# Function to handle interruption
cleanup() {
    echo ""
    warning "Monitoring interrupted by user"
    local end_time=$(date +%s)
    generate_final_report $((check_count - 1)) $start_time $end_time
    exit 0
}

# Main monitoring function
main() {
    # Setup
    trap cleanup INT TERM
    
    echo ""
    echo "📊 ==============================================="
    echo "🔍 PRODUCTION DEPLOYMENT MONITOR"
    echo "📊 ==============================================="
    echo ""
    echo "Duration: $MONITOR_DURATION seconds"
    echo "Interval: $CHECK_INTERVAL seconds"
    echo "Started: $(date)"
    echo ""
    
    # Initialize state
    init_monitoring_state
    
    # Start monitoring
    local start_time=$(date +%s)
    local end_time=$((start_time + MONITOR_DURATION))
    local check_count=1
    local total_checks=$((MONITOR_DURATION / CHECK_INTERVAL))
    
    info "Starting continuous monitoring for $MONITOR_DURATION seconds..."
    info "Expected total checks: $total_checks"
    
    # Initial system test
    perform_system_test $check_count
    
    # Monitoring loop
    while [ $(date +%s) -lt $end_time ]; do
        sleep $CHECK_INTERVAL
        ((check_count++))
        
        perform_system_test $check_count
        
        # Check if we should trigger alerts
        local current_failures=0
        for service in kong backend frontend; do
            if [ "${service_status[$service]}" = "unhealthy" ]; then
                ((current_failures++))
            fi
        done
        
        # Alert if multiple services are down
        if [ $current_failures -gt 1 ]; then
            alert "CRITICAL: $current_failures services are unhealthy - consider rollback!"
        fi
    done
    
    # Generate final report
    local actual_end_time=$(date +%s)
    generate_final_report $check_count $start_time $actual_end_time
    
    echo ""
    echo "🏁 Monitoring completed successfully"
    
    # Return appropriate exit code
    local total_errors_all=$((error_counts[kong] + error_counts[backend] + error_counts[frontend]))
    if [ $total_errors_all -eq 0 ]; then
        echo "🎉 PERFECT DEPLOYMENT - No errors detected!"
        exit 0
    elif [ $total_errors_all -le 5 ]; then
        echo "✅ GOOD DEPLOYMENT - Minor issues detected"
        exit 0
    else
        echo "⚠️ PROBLEMATIC DEPLOYMENT - Multiple issues detected"
        exit 1
    fi
}

# Validate dependencies
check_dependencies() {
    if ! command -v curl &> /dev/null; then
        error "curl is required but not installed"
        exit 1
    fi
    
    if ! command -v date &> /dev/null; then
        error "date command is required but not available"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "📊 Production Deployment Monitor"
    echo ""
    echo "Usage: $0 [duration] [interval]"
    echo ""
    echo "Parameters:"
    echo "  duration  - Monitoring duration in seconds (default: 300)"
    echo "  interval  - Check interval in seconds (default: 30)"
    echo ""
    echo "Examples:"
    echo "  $0                    # Monitor for 5 minutes with 30s intervals"
    echo "  $0 600               # Monitor for 10 minutes with 30s intervals"
    echo "  $0 300 10            # Monitor for 5 minutes with 10s intervals"
    echo "  $0 1800 60           # Monitor for 30 minutes with 1m intervals"
    echo ""
    echo "Environment Variables:"
    echo "  KONG_API_KEY         # Kong Gateway API key for authenticated tests"
    echo ""
    echo "Exit Codes:"
    echo "  0 - Monitoring completed successfully"
    echo "  1 - Significant issues detected during monitoring"
    echo ""
}

# Script entry point
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    show_usage
    exit 0
fi

check_dependencies
main

# Example usage:
# ./scripts/deployment-monitor.sh                  # 5 min monitoring
# ./scripts/deployment-monitor.sh 600             # 10 min monitoring
# ./scripts/deployment-monitor.sh 300 15          # 5 min with 15s intervals
# KONG_API_KEY=xxx ./scripts/deployment-monitor.sh # With Kong testing