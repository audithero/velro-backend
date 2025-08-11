#!/bin/bash

# Frontend Deployment Log Checker
# CRITICAL MISSION COMPLETION REQUIREMENT
# 
# This script automatically checks Railway deployment logs for frontend build/deploy errors
# and provides actionable feedback for fixing build issues.
#
# Usage:
#   ./scripts/check-fe-deploy-logs.sh [DEPLOYMENT_ID]
#   
# If DEPLOYMENT_ID is not provided, it will auto-detect the latest frontend deployment.

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Log function
log() {
    echo -e "${BLUE}[FE-DEPLOY-CHECKER]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Frontend deployment patterns for Railway project discovery
FRONTEND_PATTERNS=("velro-frontend" "velro-003-frontend" "frontend")

# Common build/deploy failure indicators
declare -a ERROR_PATTERNS=(
    "ERROR"
    "UnhandledPromiseRejection"
    "Build failed"
    "Exit status 1"
    "Cannot find module"
    "TypeError"
    "SyntaxError"
    "missing script"
    "npm ERR!"
    "yarn ERR!"
    "ENOENT"
    "Module build failed"
    "Compilation failed"
    "Command failed"
    "Process exited with code 1"
    "Build process exited"
    "Failed to compile"
    "Module not found"
    "Unexpected token"
    "ReferenceError"
    "Invalid or unexpected"
    "Parse error"
    "Dependency error"
    "Package not found"
    "Installation failed"
    "Build timeout"
    "Out of memory"
    "FATAL ERROR"
    "Allocation failed"
    "JavaScript heap out of memory"
    "spawn ENOMEM"
)

# Success indicators
declare -a SUCCESS_PATTERNS=(
    "Build completed"
    "Build successful"
    "Deployment successful"
    "Successfully deployed"
    "Build finished"
    "Compiled successfully"
    "✓ Built"
    "✅ Deployed"
    "Ready in"
    "Local:"
    "Network:"
    "successfully built"
    "Export successful"
)

# Check if Railway CLI is available
check_railway_cli() {
    if ! command -v railway &> /dev/null; then
        error "Railway CLI is not installed or not in PATH"
        error "Install it with: npm install -g @railway/cli"
        error "Or use curl: curl -fsSL https://railway.app/install.sh | sh"
        exit 1
    fi
    
    log "Railway CLI found: $(railway --version)"
}

# Get project list and find frontend service
find_frontend_service() {
    log "Discovering frontend service..."
    
    # First try to list services in current project
    local services_output
    if services_output=$(railway service list 2>/dev/null); then
        log "Found services in current project"
        echo "$services_output"
        
        # Look for frontend service patterns
        for pattern in "${FRONTEND_PATTERNS[@]}"; do
            if echo "$services_output" | grep -i "$pattern" &> /dev/null; then
                local service_id=$(echo "$services_output" | grep -i "$pattern" | head -1 | awk '{print $1}')
                success "Found frontend service: $service_id"
                echo "$service_id"
                return 0
            fi
        done
    fi
    
    warn "No frontend service found in current project context"
    warn "Make sure you're in the correct Railway project directory"
    warn "Or run: railway login && railway link"
    return 1
}

# Get latest deployment for a service
get_latest_deployment() {
    local service_id="$1"
    
    if [[ -z "$service_id" ]]; then
        error "Service ID is required"
        return 1
    fi
    
    log "Getting latest deployment for service: $service_id"
    
    local deployments_output
    if deployments_output=$(railway deployment list --service "$service_id" 2>/dev/null | head -10); then
        local deployment_id=$(echo "$deployments_output" | grep -v "ID" | head -1 | awk '{print $1}')
        if [[ -n "$deployment_id" ]]; then
            success "Found latest deployment: $deployment_id"
            echo "$deployment_id"
            return 0
        fi
    fi
    
    error "Could not find any deployments for service: $service_id"
    return 1
}

# Get deployment logs
get_deployment_logs() {
    local deployment_id="$1"
    local lines="${2:-100}"
    
    if [[ -z "$deployment_id" ]]; then
        error "Deployment ID is required"
        return 1
    fi
    
    log "Fetching last $lines lines of deployment logs for: $deployment_id"
    
    # Try to get deployment logs
    local logs_output
    if logs_output=$(railway logs --deployment "$deployment_id" 2>/dev/null | tail -n "$lines"); then
        if [[ -n "$logs_output" ]]; then
            echo "$logs_output"
            return 0
        else
            warn "No logs found for deployment: $deployment_id"
            return 1
        fi
    else
        error "Failed to fetch logs for deployment: $deployment_id"
        
        # Try alternative command
        warn "Trying alternative log fetch method..."
        if logs_output=$(railway logs --deployment-id "$deployment_id" 2>/dev/null | tail -n "$lines"); then
            echo "$logs_output"
            return 0
        fi
        
        return 1
    fi
}

# Analyze logs for errors
analyze_logs() {
    local logs="$1"
    local found_errors=()
    local found_success=()
    local build_time=""
    local analysis_result=0
    
    log "Analyzing deployment logs for build/deploy issues..."
    
    # Check for error patterns
    while IFS= read -r line; do
        # Extract build time if available
        if echo "$line" | grep -q -i "built.*in.*ms\|built.*in.*s\|finished.*in\|completed.*in"; then
            build_time="$line"
        fi
        
        # Check for error patterns
        for pattern in "${ERROR_PATTERNS[@]}"; do
            if echo "$line" | grep -q -i "$pattern"; then
                found_errors+=("$line")
                break
            fi
        done
        
        # Check for success patterns
        for pattern in "${SUCCESS_PATTERNS[@]}"; do
            if echo "$line" | grep -q -i "$pattern"; then
                found_success+=("$line")
                break
            fi
        done
    done <<< "$logs"
    
    # Report findings
    echo "========================================="
    echo "FRONTEND DEPLOYMENT LOG ANALYSIS REPORT"
    echo "========================================="
    echo "Timestamp: $(date)"
    echo ""
    
    if [[ -n "$build_time" ]]; then
        success "Build timing information found:"
        echo "  $build_time"
        echo ""
    fi
    
    if [[ ${#found_success[@]} -gt 0 ]]; then
        success "Success indicators found (${#found_success[@]}):"
        for success_line in "${found_success[@]}"; do
            echo "  ✅ $success_line"
        done
        echo ""
    fi
    
    if [[ ${#found_errors[@]} -gt 0 ]]; then
        error "Build/Deploy errors found (${#found_errors[@]}):"
        for error_line in "${found_errors[@]}"; do
            echo "  ❌ $error_line"
        done
        echo ""
        analysis_result=1
        
        # Provide specific fix suggestions
        provide_fix_suggestions "${found_errors[@]}"
        
    else
        success "No critical build/deploy errors detected!"
        echo ""
    fi
    
    # Final assessment
    if [[ $analysis_result -eq 0 ]] && [[ ${#found_success[@]} -gt 0 ]]; then
        success "✅ FRONTEND DEPLOYMENT: PASS"
        echo "   - No critical errors found"
        echo "   - Success indicators present"
        [[ -n "$build_time" ]] && echo "   - Build completed with timing info"
    elif [[ $analysis_result -eq 0 ]]; then
        warn "⚠️  FRONTEND DEPLOYMENT: UNCLEAR"
        echo "   - No critical errors found"
        echo "   - But no clear success indicators either"
        echo "   - Manual verification recommended"
    else
        error "❌ FRONTEND DEPLOYMENT: FAIL" 
        echo "   - Critical errors detected"
        echo "   - Deployment likely failed"
        echo "   - Fix required before proceeding"
    fi
    
    return $analysis_result
}

# Provide fix suggestions based on error patterns
provide_fix_suggestions() {
    local errors=("$@")
    
    echo ""
    error "SUGGESTED FIXES:"
    
    # Analyze error types and provide specific suggestions
    local has_module_error=false
    local has_memory_error=false
    local has_build_error=false
    local has_syntax_error=false
    local has_dependency_error=false
    
    for error_line in "${errors[@]}"; do
        case "$error_line" in
            *"Cannot find module"*|*"Module not found"*|*"ENOENT"*)
                has_module_error=true
                ;;
            *"JavaScript heap out of memory"*|*"ENOMEM"*|*"Allocation failed"*)
                has_memory_error=true
                ;;
            *"Build failed"*|*"Compilation failed"*|*"Failed to compile"*)
                has_build_error=true
                ;;
            *"SyntaxError"*|*"Unexpected token"*|*"Parse error"*)
                has_syntax_error=true
                ;;
            *"npm ERR!"*|*"yarn ERR!"*|*"Dependency error"*)
                has_dependency_error=true
                ;;
        esac
    done
    
    if $has_module_error; then
        echo "  🔧 MODULE ERRORS:"
        echo "     - Run 'npm install' or 'yarn install' to ensure all dependencies"
        echo "     - Check package.json for missing dependencies"
        echo "     - Verify import paths and module names"
        echo "     - Check if modules exist in node_modules/"
    fi
    
    if $has_memory_error; then
        echo "  🔧 MEMORY ERRORS:"
        echo "     - Increase Node.js heap size: NODE_OPTIONS='--max-old-space-size=4096'"
        echo "     - Optimize build process to use less memory"
        echo "     - Consider splitting large bundles"
        echo "     - Check for memory leaks in build scripts"
    fi
    
    if $has_build_error; then
        echo "  🔧 BUILD ERRORS:"
        echo "     - Check build configuration (next.config.js, webpack.config.js)"
        echo "     - Verify all required build dependencies are installed"
        echo "     - Check for TypeScript errors if using TypeScript"
        echo "     - Run build locally to reproduce the issue"
    fi
    
    if $has_syntax_error; then
        echo "  🔧 SYNTAX ERRORS:"
        echo "     - Check for JavaScript/TypeScript syntax errors"
        echo "     - Verify all brackets, parentheses, and quotes are properly closed"
        echo "     - Run linter locally: 'npm run lint' or 'yarn lint'"
        echo "     - Check for proper import/export statements"
    fi
    
    if $has_dependency_error; then
        echo "  🔧 DEPENDENCY ERRORS:"
        echo "     - Clear node_modules and reinstall: 'rm -rf node_modules && npm install'"
        echo "     - Check package.json for correct version specifications"
        echo "     - Update dependencies: 'npm update' or 'yarn upgrade'"
        echo "     - Check for conflicting peer dependencies"
    fi
    
    echo ""
    echo "  📚 GENERAL DEBUGGING STEPS:"
    echo "     1. Run the build locally to reproduce issues"
    echo "     2. Check Railway environment variables match your needs"
    echo "     3. Verify Node.js version compatibility"
    echo "     4. Review deployment logs for additional context"
    echo "     5. Test with a minimal reproduction case"
}

# Main execution
main() {
    local deployment_id="$1"
    
    echo "=============================================="
    echo "🚀 Frontend Deployment Log Checker v1.0"
    echo "=============================================="
    echo ""
    
    # Check Railway CLI availability
    check_railway_cli
    
    # If no deployment ID provided, discover it
    if [[ -z "$deployment_id" ]]; then
        log "No deployment ID provided, discovering latest frontend deployment..."
        
        local service_id
        if service_id=$(find_frontend_service); then
            if deployment_id=$(get_latest_deployment "$service_id"); then
                log "Auto-discovered deployment: $deployment_id"
            else
                error "Could not auto-discover deployment ID"
                error "Please provide deployment ID manually: $0 DEPLOYMENT_ID"
                exit 1
            fi
        else
            error "Could not find frontend service"
            error "Please ensure you're in the correct Railway project"
            exit 1
        fi
    else
        log "Using provided deployment ID: $deployment_id"
    fi
    
    # Get deployment logs
    log "Fetching deployment logs..."
    local logs
    if logs=$(get_deployment_logs "$deployment_id" 100); then
        log "Successfully retrieved deployment logs"
        
        # Save logs to file for reference
        local log_file="frontend_deploy_logs_$(date +%Y%m%d_%H%M%S).txt"
        echo "$logs" > "$log_file"
        success "Logs saved to: $log_file"
        
        # Analyze logs
        if analyze_logs "$logs"; then
            success "Frontend deployment analysis completed successfully!"
            exit 0
        else
            error "Frontend deployment has issues that need to be resolved!"
            exit 1
        fi
    else
        error "Failed to retrieve deployment logs"
        exit 1
    fi
}

# Run main function with all arguments
main "$@"