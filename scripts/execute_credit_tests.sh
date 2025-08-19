#!/bin/bash

# CREDIT PROCESSING FIX VALIDATION - EXECUTION SCRIPT
# 
# This script provides an easy way to execute the comprehensive credit processing tests
# with proper environment setup and error handling.
#
# Usage:
#   ./execute_credit_tests.sh [phase] [options]
#
# Examples:
#   ./execute_credit_tests.sh                    # Run all tests
#   ./execute_credit_tests.sh pipeline          # Run pipeline tests only
#   ./execute_credit_tests.sh all --verbose     # Run all tests with verbose output
#   ./execute_credit_tests.sh performance       # Run performance tests only

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/test-results"
LOG_FILE="$RESULTS_DIR/test_execution.log"

# Test configuration
AFFECTED_USER_ID="22cb3917-57f6-49c6-ac96-ec266570081b"
EXPECTED_CREDITS="1200"
PRODUCTION_URL="https://velro-backend-production.up.railway.app"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

log_header() {
    echo -e "${PURPLE}$1${NC}" | tee -a "$LOG_FILE"
}

# Print banner
print_banner() {
    log_header "================================================================================"
    log_header "🚀 CREDIT PROCESSING FIX VALIDATION TEST SUITE"
    log_header "================================================================================"
    log_info "📅 Execution Time: $(date)"
    log_info "🎯 Affected User: $AFFECTED_USER_ID"
    log_info "💳 Expected Credits: $EXPECTED_CREDITS"
    log_info "🐛 Issue: Credit processing failed: Profile lookup error"
    log_info "📍 Working Directory: $SCRIPT_DIR"
    log_header "================================================================================"
    echo
}

# Setup functions
setup_environment() {
    log_info "🔧 Setting up test environment..."
    
    # Create results directory
    mkdir -p "$RESULTS_DIR"
    
    # Initialize log file
    echo "Credit Processing Fix Validation - Test Execution Log" > "$LOG_FILE"
    echo "Started: $(date)" >> "$LOG_FILE"
    echo "==========================================" >> "$LOG_FILE"
    
    # Check Python version
    if ! command -v python &> /dev/null; then
        log_error "Python is not installed or not in PATH"
        exit 1
    fi
    
    PYTHON_VERSION=$(python --version 2>&1 | cut -d' ' -f2)
    log_info "🐍 Python version: $PYTHON_VERSION"
    
    # Check if we're in a virtual environment
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        log_info "📦 Virtual environment: $VIRTUAL_ENV"
    else
        log_warning "No virtual environment detected - consider using one"
    fi
    
    # Verify required files exist
    local required_files=(
        "run_credit_processing_tests.py"
        "tests/test_comprehensive_credit_processing_fix.py"
        "tests/test_performance_credit_operations.py"
        "tests/conftest.py"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "$SCRIPT_DIR/$file" ]]; then
            log_error "Required file not found: $file"
            exit 1
        fi
    done
    
    log_success "Environment setup completed"
}

# Validate environment variables
validate_environment_variables() {
    log_info "🔍 Validating environment variables..."
    
    local required_vars=(
        "SUPABASE_URL"
        "SUPABASE_ANON_KEY"
        "SUPABASE_SERVICE_ROLE_KEY"
        "FAL_KEY"
    )
    
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        else
            log_info "✅ $var is set"
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            log_error "  - $var"
        done
        log_error "Please set all required environment variables before running tests"
        exit 1
    fi
    
    # Set default values for optional variables
    export ENVIRONMENT="${ENVIRONMENT:-test}"
    export DEBUG="${DEBUG:-false}"
    export TESTING="${TESTING:-true}"
    
    log_success "Environment variables validated"
}

# Install dependencies
install_dependencies() {
    log_info "📦 Installing dependencies..."
    
    # Check if requirements.txt exists
    if [[ ! -f "$SCRIPT_DIR/requirements.txt" ]]; then
        log_error "requirements.txt not found"
        exit 1
    fi
    
    # Install requirements
    if ! pip install -r "$SCRIPT_DIR/requirements.txt" >> "$LOG_FILE" 2>&1; then
        log_error "Failed to install requirements"
        exit 1
    fi
    
    # Install test-specific dependencies
    local test_deps=("pytest" "pytest-asyncio" "httpx" "psutil")
    for dep in "${test_deps[@]}"; do
        if ! pip install "$dep" >> "$LOG_FILE" 2>&1; then
            log_warning "Failed to install $dep - tests may not work properly"
        fi
    done
    
    log_success "Dependencies installed"
}

# Run specific test phase
run_test_phase() {
    local phase="$1"
    local verbose_flag="${2:-}"
    
    log_header "📋 RUNNING TEST PHASE: ${phase^^}"
    log_info "Phase: $phase"
    log_info "Verbose: ${verbose_flag:+enabled}"
    
    local cmd="python $SCRIPT_DIR/run_credit_processing_tests.py --phase $phase --save-results"
    
    if [[ -n "$verbose_flag" ]]; then
        cmd="$cmd --verbose"
    fi
    
    log_info "Executing: $cmd"
    
    # Run the test and capture exit code
    local exit_code=0
    if ! eval "$cmd" | tee -a "$LOG_FILE"; then
        exit_code=$?
    fi
    
    # Interpret exit code
    case $exit_code in
        0)
            log_success "Phase '$phase' completed successfully - All tests passed!"
            return 0
            ;;
        1)
            log_warning "Phase '$phase' completed with warnings - Profile error may be resolved"
            return 1
            ;;
        2)
            log_error "Phase '$phase' failed - Credit processing issue still exists"
            return 2
            ;;
        *)
            log_error "Phase '$phase' failed with unexpected exit code: $exit_code"
            return 3
            ;;
    esac
}

# Run performance tests
run_performance_tests() {
    log_header "⚡ RUNNING PERFORMANCE TESTS"
    
    local cmd="python -m pytest $SCRIPT_DIR/tests/test_performance_credit_operations.py -v -m performance"
    
    log_info "Executing: $cmd"
    
    if eval "$cmd" | tee -a "$LOG_FILE"; then
        log_success "Performance tests completed successfully"
        return 0
    else
        log_error "Performance tests failed"
        return 1
    fi
}

# Generate test report
generate_report() {
    local overall_status="$1"
    
    log_header "📊 GENERATING TEST REPORT"
    
    local report_file="$RESULTS_DIR/test_execution_report.txt"
    
    cat > "$report_file" << EOF
CREDIT PROCESSING FIX VALIDATION - TEST EXECUTION REPORT
=========================================================

Execution Details:
- Date: $(date)
- User: $(whoami)
- Host: $(hostname)
- Working Directory: $SCRIPT_DIR

Test Configuration:
- Affected User ID: $AFFECTED_USER_ID
- Expected Credits: $EXPECTED_CREDITS
- Production URL: $PRODUCTION_URL
- Environment: ${ENVIRONMENT:-test}

Overall Status: $overall_status

Environment Variables:
- SUPABASE_URL: ${SUPABASE_URL:0:50}...
- SUPABASE_ANON_KEY: Set (${#SUPABASE_ANON_KEY} characters)
- SUPABASE_SERVICE_ROLE_KEY: Set (${#SUPABASE_SERVICE_ROLE_KEY} characters)
- FAL_KEY: Set (${#FAL_KEY} characters)

Files Generated:
$(ls -la "$RESULTS_DIR" | grep -E "\.(json|log|txt)$" || echo "  No result files found")

Summary:
$(case "$overall_status" in
    "PASS")
        echo "✅ ALL TESTS PASSED - Credit processing issue is FULLY RESOLVED!"
        echo "   The fix is working correctly and all validation tests passed."
        ;;
    "PARTIAL_PASS")
        echo "⚠️ PARTIAL SUCCESS - Profile error may be resolved but some tests failed"
        echo "   Manual review recommended to verify the fix is complete."
        ;;
    "FAIL")
        echo "❌ TESTS FAILED - Credit processing issue still exists"
        echo "   The fix has not resolved the profile lookup error."
        ;;
    *)
        echo "❓ UNKNOWN STATUS - Review logs for details"
        ;;
esac)

For detailed results, check:
- Test logs: $LOG_FILE
- JSON results: $RESULTS_DIR/*.json
- This report: $report_file

EOF

    log_info "Report generated: $report_file"
}

# Cleanup function
cleanup() {
    log_info "🧹 Performing cleanup..."
    
    # Archive old results if they exist
    if [[ -d "$RESULTS_DIR" ]] && [[ $(ls -A "$RESULTS_DIR" 2>/dev/null | wc -l) -gt 0 ]]; then
        local archive_name="test_results_archive_$(date +%Y%m%d_%H%M%S).tar.gz"
        if tar -czf "$RESULTS_DIR/$archive_name" "$RESULTS_DIR"/*.json "$RESULTS_DIR"/*.log 2>/dev/null; then
            log_info "Previous results archived: $archive_name"
        fi
    fi
    
    log_success "Cleanup completed"
}

# Main execution function
main() {
    local phase="${1:-all}"
    local verbose_flag=""
    
    # Parse arguments
    shift || true
    while [[ $# -gt 0 ]]; do
        case $1 in
            --verbose|-v)
                verbose_flag="--verbose"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Validate phase
    local valid_phases=("all" "pre_fix" "service_key" "pipeline" "edge_cases" "production" "performance")
    if [[ ! " ${valid_phases[*]} " =~ " ${phase} " ]]; then
        log_error "Invalid phase: $phase"
        log_error "Valid phases: ${valid_phases[*]}"
        exit 1
    fi
    
    print_banner
    
    # Setup and validation
    setup_environment
    validate_environment_variables
    install_dependencies
    
    local overall_status="UNKNOWN"
    local exit_code=0
    
    # Run tests based on phase
    if [[ "$phase" == "performance" ]]; then
        if run_performance_tests; then
            overall_status="PASS"
        else
            overall_status="FAIL"
            exit_code=1
        fi
    elif [[ "$phase" == "all" ]]; then
        if run_test_phase "all" "$verbose_flag"; then
            overall_status="PASS"
        else
            case $? in
                1) overall_status="PARTIAL_PASS"; exit_code=1 ;;
                *) overall_status="FAIL"; exit_code=2 ;;
            esac
        fi
        
        # Also run performance tests for completeness
        log_info "🔄 Running additional performance validation..."
        if ! run_performance_tests; then
            log_warning "Performance tests failed but main tests passed"
        fi
    else
        if run_test_phase "$phase" "$verbose_flag"; then
            overall_status="PASS"
        else
            case $? in
                1) overall_status="PARTIAL_PASS"; exit_code=1 ;;
                *) overall_status="FAIL"; exit_code=2 ;;
            esac
        fi
    fi
    
    # Generate report
    generate_report "$overall_status"
    cleanup
    
    # Final summary
    echo
    log_header "🎯 FINAL EXECUTION SUMMARY"
    log_info "Phase: $phase"
    log_info "Overall Status: $overall_status"
    
    case "$overall_status" in
        "PASS")
            log_success "All tests passed - Credit processing issue is RESOLVED!"
            ;;
        "PARTIAL_PASS")
            log_warning "Partial success - Manual review needed"
            ;;
        "FAIL")
            log_error "Tests failed - Issue not resolved"
            ;;
    esac
    
    log_info "Results saved to: $RESULTS_DIR"
    log_header "================================================================================"
    
    exit $exit_code
}

# Help function
show_help() {
    cat << EOF
Credit Processing Fix Validation - Test Execution Script

USAGE:
    $0 [phase] [options]

PHASES:
    all         Run all test phases (default)
    pre_fix     Pre-fix state validation
    service_key Service key fix testing
    pipeline    Generation pipeline testing
    edge_cases  Edge case testing
    production  Production environment testing
    performance Performance tests only

OPTIONS:
    --verbose, -v    Enable verbose output
    --help, -h       Show this help message

EXAMPLES:
    $0                      # Run all tests
    $0 pipeline             # Run pipeline tests only
    $0 all --verbose        # Run all tests with verbose output
    $0 performance          # Run performance tests only

ENVIRONMENT VARIABLES (Required):
    SUPABASE_URL             Supabase project URL
    SUPABASE_ANON_KEY        Supabase anonymous key
    SUPABASE_SERVICE_ROLE_KEY    Supabase service role key (critical for fix)
    FAL_KEY                  FAL.ai API key

RESULTS:
    Test results are saved to: $RESULTS_DIR/
    Exit codes: 0=Success, 1=Partial Success, 2=Failure

EOF
}

# Execute main function with all arguments
main "$@"