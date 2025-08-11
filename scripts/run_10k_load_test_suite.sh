#!/bin/bash

# VELRO PHASE 4: Comprehensive 10K+ User Load Testing Suite
# Execute complete load testing validation for PRD compliance

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="${PROJECT_ROOT}/load_test_results"
LOG_FILE="${RESULTS_DIR}/load_test_execution.log"

# Create results directory
mkdir -p "$RESULTS_DIR"

# Logging function
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Header
print_header() {
    log "${BLUE}================================================================${NC}"
    log "${BLUE}VELRO PHASE 4: Comprehensive Load Testing Suite for 10K+ Users${NC}"
    log "${BLUE}================================================================${NC}"
    log "Start Time: $(date)"
    log "Results Directory: $RESULTS_DIR"
    log ""
}

# Environment validation
validate_environment() {
    log "${YELLOW}Validating Environment...${NC}"
    
    # Check required environment variables
    if [[ -z "$SUPABASE_SERVICE_KEY" ]]; then
        log "${RED}ERROR: SUPABASE_SERVICE_KEY environment variable not set${NC}"
        log "Please set your Supabase service key:"
        log "export SUPABASE_SERVICE_KEY='your_service_key_here'"
        exit 1
    fi
    
    if [[ -z "$VELRO_API_URL" ]]; then
        log "${YELLOW}WARNING: VELRO_API_URL not set, using default${NC}"
        export VELRO_API_URL="https://velro-backend-production.up.railway.app"
    fi
    
    # Check Python environment
    if ! command -v python3 &> /dev/null; then
        log "${RED}ERROR: python3 not found${NC}"
        exit 1
    fi
    
    # Check required Python packages
    python3 -c "import aiohttp, numpy, pandas, psutil, jinja2, yaml" 2>/dev/null || {
        log "${YELLOW}Installing required Python packages...${NC}"
        pip3 install aiohttp numpy pandas psutil jinja2 pyyaml
    }
    
    log "${GREEN}Environment validation complete${NC}"
    log ""
}

# System preparation
prepare_system() {
    log "${YELLOW}Preparing System for Load Testing...${NC}"
    
    # Increase system limits for load testing
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux optimizations
        log "Applying Linux system optimizations..."
        
        # Increase file descriptor limits
        ulimit -n 65536 || log "${YELLOW}Warning: Could not increase file descriptor limit${NC}"
        
        # Optimize network settings
        sudo sysctl -w net.core.somaxconn=65535 2>/dev/null || true
        sudo sysctl -w net.core.netdev_max_backlog=5000 2>/dev/null || true
        sudo sysctl -w net.ipv4.tcp_max_syn_backlog=4096 2>/dev/null || true
        
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS optimizations
        log "Applying macOS system optimizations..."
        ulimit -n 10240 || log "${YELLOW}Warning: Could not increase file descriptor limit${NC}"
    fi
    
    # Clear previous test data
    log "Cleaning up previous test data..."
    rm -f "${RESULTS_DIR}/load_test_10k_users_results_*.json"
    rm -f "${RESULTS_DIR}/performance_validation_report_*.json"
    rm -f "${RESULTS_DIR}/executive_summary_*.json"
    
    log "${GREEN}System preparation complete${NC}"
    log ""
}

# Health check
health_check() {
    log "${YELLOW}Performing Pre-Test Health Check...${NC}"
    
    # Check API availability
    if curl -s --max-time 10 "${VELRO_API_URL}/health" > /dev/null 2>&1; then
        log "${GREEN}✓ API endpoint accessible${NC}"
    else
        log "${RED}✗ API endpoint not accessible${NC}"
        log "Attempting to reach: ${VELRO_API_URL}/health"
        exit 1
    fi
    
    # Check database connectivity (if possible)
    log "Database connectivity check..."
    python3 -c "
import os
import asyncio
import aiohttp

async def check_db():
    try:
        headers = {'Authorization': f'Bearer {os.getenv(\"SUPABASE_SERVICE_KEY\")}'}
        async with aiohttp.ClientSession() as session:
            async with session.get('${VELRO_API_URL}/auth/me', headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status in [200, 401]:  # 401 is expected without valid user token
                    print('✓ Database connectivity OK')
                    return True
        return False
    except Exception as e:
        print(f'✗ Database connectivity issue: {e}')
        return False

result = asyncio.run(check_db())
exit(0 if result else 1)
" && log "${GREEN}✓ Database connectivity OK${NC}" || log "${YELLOW}⚠ Database connectivity uncertain${NC}"
    
    # System resource check
    log "System resource check..."
    python3 -c "
import psutil
import sys

cpu_count = psutil.cpu_count()
memory_gb = psutil.virtual_memory().total / (1024**3)
disk_free_gb = psutil.disk_usage('.').free / (1024**3)

print(f'CPU Cores: {cpu_count}')
print(f'Total Memory: {memory_gb:.1f} GB')
print(f'Free Disk Space: {disk_free_gb:.1f} GB')

# Minimum requirements check
if cpu_count < 2:
    print('⚠ WARNING: Low CPU core count for load testing')
if memory_gb < 4:
    print('⚠ WARNING: Low memory for load testing')
if disk_free_gb < 2:
    print('⚠ WARNING: Low disk space for results')

print('✓ System resource check complete')
"
    
    log "${GREEN}Health check complete${NC}"
    log ""
}

# Execute load tests
execute_load_tests() {
    log "${YELLOW}Starting Load Testing Suite Execution...${NC}"
    
    local start_time=$(date +%s)
    
    # Change to script directory for execution
    cd "$SCRIPT_DIR"
    
    log "Executing comprehensive 10K+ user load test..."
    log "This may take 30-60 minutes to complete..."
    log ""
    
    # Execute the load test with proper error handling
    if python3 load_test_10k_users.py 2>&1 | tee -a "$LOG_FILE"; then
        log "${GREEN}✓ Load testing suite execution completed successfully${NC}"
    else
        log "${RED}✗ Load testing suite execution failed${NC}"
        log "Check the log file for details: $LOG_FILE"
        return 1
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log "Load testing duration: ${duration} seconds ($((duration / 60)) minutes)"
    
    # Move results to results directory
    mv load_test_10k_users_results_*.json "$RESULTS_DIR/" 2>/dev/null || true
    mv load_test_10k_users.log "$RESULTS_DIR/" 2>/dev/null || true
    
    log ""
}

# Generate performance reports
generate_reports() {
    log "${YELLOW}Generating Performance Validation Reports...${NC}"
    
    # Find the latest results file
    local results_file=$(ls -t "${RESULTS_DIR}"/load_test_10k_users_results_*.json 2>/dev/null | head -n1)
    
    if [[ -z "$results_file" ]]; then
        log "${RED}ERROR: No load test results file found${NC}"
        return 1
    fi
    
    log "Processing results from: $results_file"
    
    # Generate comprehensive reports
    cd "$SCRIPT_DIR"
    if python3 performance_validation_report.py "$results_file" \
        --output-dir "$RESULTS_DIR" \
        --formats json html csv 2>&1 | tee -a "$LOG_FILE"; then
        log "${GREEN}✓ Performance validation reports generated${NC}"
    else
        log "${RED}✗ Report generation failed${NC}"
        return 1
    fi
    
    log ""
}

# Results summary
display_results_summary() {
    log "${YELLOW}Load Testing Results Summary${NC}"
    log "=========================="
    
    # Find latest executive summary
    local summary_file=$(ls -t "${RESULTS_DIR}"/executive_summary_*.json 2>/dev/null | head -n1)
    
    if [[ -n "$summary_file" ]]; then
        log "Executive Summary from: $summary_file"
        log ""
        
        # Extract key metrics using Python
        python3 -c "
import json
import sys

try:
    with open('$summary_file', 'r') as f:
        summary = json.load(f)
    
    key_findings = summary.get('key_findings', {})
    critical_metrics = summary.get('critical_metrics', {})
    business_impact = summary.get('business_impact', {})
    
    print('KEY FINDINGS:')
    print(f'  PRD Compliance: {key_findings.get(\"prd_compliance\", \"UNKNOWN\")}')
    print(f'  Compliance Score: {key_findings.get(\"compliance_score\", \"N/A\")}')
    print(f'  Production Ready: {key_findings.get(\"ready_for_production\", \"UNKNOWN\")}')
    print(f'  Performance Level: {key_findings.get(\"performance_level\", \"UNKNOWN\")}')
    print()
    
    print('CRITICAL METRICS:')
    print(f'  P95 Response Time: {critical_metrics.get(\"response_time_p95_ms\", 0):.2f}ms')
    print(f'  Throughput: {critical_metrics.get(\"throughput_rps\", 0):.1f} req/sec')
    print(f'  Cache Hit Rate: {critical_metrics.get(\"cache_hit_rate_percent\", 0):.1f}%')
    print(f'  Error Rate: {critical_metrics.get(\"error_rate_percent\", 0):.3f}%')
    print()
    
    print('BUSINESS IMPACT:')
    for key, value in business_impact.items():
        print(f'  {key.replace(\"_\", \" \").title()}: {value}')
    
except Exception as e:
    print(f'Error reading summary: {e}')
    sys.exit(1)
"
    else
        log "${YELLOW}No executive summary found${NC}"
    fi
    
    log ""
    log "Detailed reports available in: $RESULTS_DIR"
    log ""
}

# Cleanup function
cleanup() {
    log "${YELLOW}Performing cleanup...${NC}"
    
    # Archive old logs
    if [[ -f "${RESULTS_DIR}/load_test_execution.log" ]]; then
        mv "${RESULTS_DIR}/load_test_execution.log" "${RESULTS_DIR}/load_test_execution_$(date +%Y%m%d_%H%M%S).log"
    fi
    
    # Reset system limits if modified
    # (Most changes are temporary and reset on shell exit)
    
    log "${GREEN}Cleanup complete${NC}"
}

# Main execution
main() {
    print_header
    
    # Trap for cleanup on exit
    trap cleanup EXIT
    
    # Execute phases
    validate_environment
    prepare_system
    health_check
    
    if execute_load_tests; then
        generate_reports
        display_results_summary
        
        log "${GREEN}================================================================${NC}"
        log "${GREEN}PHASE 4 LOAD TESTING SUITE COMPLETED SUCCESSFULLY${NC}"
        log "${GREEN}================================================================${NC}"
        log "End Time: $(date)"
        log ""
        log "Next Steps:"
        log "1. Review detailed reports in: $RESULTS_DIR"
        log "2. Address any performance recommendations"
        log "3. Proceed with production deployment if PRD compliance achieved"
        log ""
        
        exit 0
    else
        log "${RED}================================================================${NC}"
        log "${RED}PHASE 4 LOAD TESTING SUITE FAILED${NC}"
        log "${RED}================================================================${NC}"
        log "Check logs and address issues before retrying"
        exit 1
    fi
}

# Help function
show_help() {
    cat << EOF
VELRO PHASE 4: Comprehensive 10K+ User Load Testing Suite

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose logging
    --dry-run          Perform all checks but skip actual load testing
    --quick-test       Run abbreviated load test (faster, less comprehensive)

ENVIRONMENT VARIABLES:
    SUPABASE_SERVICE_KEY    Required: Supabase service key for API authentication
    VELRO_API_URL          Optional: API URL (default: production endpoint)
    REDIS_URL              Optional: Redis URL for caching tests

EXAMPLES:
    # Standard execution
    ./run_10k_load_test_suite.sh
    
    # With environment variables
    SUPABASE_SERVICE_KEY="your_key" ./run_10k_load_test_suite.sh
    
    # Dry run to validate setup
    ./run_10k_load_test_suite.sh --dry-run

PRD REQUIREMENTS VALIDATED:
    - Concurrent Users: 10,000+ simultaneous users
    - Database Connections: 200+ optimized connections  
    - Cache Hit Rate: 95%+ for authorization operations
    - Throughput: 1,000+ requests/second sustained
    - Response Time: <50ms authentication, <75ms authorization

RESULTS:
    Results and reports will be saved in: ./load_test_results/
    - JSON results with detailed metrics
    - HTML performance report
    - CSV summary for analysis
    - Executive summary for stakeholders

EOF
}

# Command line argument handling
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            set -x  # Enable verbose output
            shift
            ;;
        --dry-run)
            log "${YELLOW}DRY RUN MODE: Performing validation only${NC}"
            validate_environment
            prepare_system
            health_check
            log "${GREEN}Dry run completed successfully${NC}"
            exit 0
            ;;
        --quick-test)
            log "${YELLOW}QUICK TEST MODE: Running abbreviated test suite${NC}"
            export QUICK_TEST_MODE=1
            shift
            ;;
        *)
            log "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Execute main function
main "$@"