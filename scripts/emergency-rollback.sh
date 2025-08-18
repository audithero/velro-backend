#!/bin/bash

# 🚨 Emergency Rollback Script
# Instant rollback capability for production deployment issues
# Usage: ./scripts/emergency-rollback.sh [rollback_type] [version]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ROLLBACK_TYPE=${1:-full}
ROLLBACK_VERSION=${2:-"previous"}
TIMEOUT=60
HEALTH_CHECK_INTERVAL=10

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

emergency() {
    echo -e "${RED}🚨 EMERGENCY: $1${NC}"
}

# Function to check if Railway CLI is available
check_railway_cli() {
    if ! command -v railway &> /dev/null; then
        error "Railway CLI is not installed or not in PATH"
        echo "Please install Railway CLI: curl -fsSL https://railway.app/install.sh | sh"
        return 1
    fi
    
    # Check if user is logged in
    if ! railway whoami &> /dev/null; then
        error "Not logged into Railway CLI"
        echo "Please login: railway login"
        return 1
    fi
    
    success "Railway CLI available and authenticated"
    return 0
}

# Function to enable Kong emergency bypass
enable_kong_bypass() {
    log "🔧 Enabling Kong Gateway emergency bypass..."
    
    # Set Kong to bypass mode
    railway variables set KONG_EMERGENCY_BYPASS=true --service kong-production || {
        error "Failed to set Kong emergency bypass"
        return 1
    }
    
    # Disable backend Kong proxy
    railway variables set KONG_PROXY_ENABLED=false --service velro-003-backend-production || {
        warning "Failed to disable backend Kong proxy (may not exist)"
    }
    
    # Set fallback enabled
    railway variables set KONG_FALLBACK_ENABLED=true --service velro-003-backend-production || {
        warning "Failed to enable backend fallback (may not exist)"
    }
    
    success "Kong Gateway emergency bypass enabled"
    success "Backend will route directly to FAL.ai APIs"
    return 0
}

# Function to rollback Railway service to previous deployment
rollback_service() {
    local service_name=$1
    local description=$2
    
    log "🔄 Rolling back $description ($service_name)..."
    
    # List recent deployments
    log "Getting recent deployments for $service_name..."
    deployments=$(railway status --service "$service_name" --json 2>/dev/null || echo "[]")
    
    if [ "$deployments" = "[]" ] || [ -z "$deployments" ]; then
        warning "Could not retrieve deployment history for $service_name"
        warning "Manual rollback may be required via Railway dashboard"
        return 1
    fi
    
    # Attempt rollback
    if railway rollback --service "$service_name" --yes; then
        success "$description rollback initiated"
        return 0
    else
        error "Failed to rollback $description"
        error "Manual intervention required via Railway dashboard"
        return 1
    fi
}

# Function to validate service health after rollback
validate_service_health() {
    local service_url=$1
    local service_name=$2
    local expected_code=${3:-200}
    local max_attempts=6
    
    log "🏥 Validating $service_name health post-rollback..."
    
    for i in $(seq 1 $max_attempts); do
        log "Health check attempt $i/$max_attempts for $service_name..."
        
        response=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$service_url" || echo "000")
        
        if [ "$response" = "$expected_code" ]; then
            success "$service_name is healthy (HTTP $response)"
            return 0
        elif [ "$response" = "000" ]; then
            warning "$service_name connection failed (attempt $i/$max_attempts)"
        else
            warning "$service_name returned HTTP $response (attempt $i/$max_attempts)"
        fi
        
        if [ $i -lt $max_attempts ]; then
            log "Waiting ${HEALTH_CHECK_INTERVAL}s before next check..."
            sleep $HEALTH_CHECK_INTERVAL
        fi
    done
    
    error "$service_name health check failed after $max_attempts attempts"
    return 1
}

# Function to perform database rollback
rollback_database() {
    log "🗄️ Initiating database rollback..."
    
    warning "DATABASE ROLLBACK REQUIRES MANUAL INTERVENTION"
    echo ""
    echo "To rollback database changes:"
    echo "1. Access Supabase Dashboard: https://app.supabase.com"
    echo "2. Navigate to your project > Database > Backups"
    echo "3. Find backup: pre-team-collab-$(date +%Y%m%d)"
    echo "4. Click 'Restore' for the backup"
    echo ""
    echo "Alternative - SQL Rollback:"
    echo "Execute the rollback SQL commands from migration 011 comments:"
    
    cat << 'EOF'
    -- Emergency database rollback SQL:
    DROP TABLE IF EXISTS generation_collaborations CASCADE;
    DROP TABLE IF EXISTS project_teams CASCADE;
    DROP TABLE IF EXISTS project_privacy_settings CASCADE;
    DROP TABLE IF EXISTS team_invitations CASCADE;
    DROP TABLE IF EXISTS team_members CASCADE;
    DROP TABLE IF EXISTS teams CASCADE;
    
    -- Remove added columns from generations
    ALTER TABLE generations DROP COLUMN IF EXISTS team_context_id;
    ALTER TABLE generations DROP COLUMN IF EXISTS collaboration_intent;
    ALTER TABLE generations DROP COLUMN IF EXISTS change_description;
    ALTER TABLE generations DROP COLUMN IF EXISTS parent_generation_id;
    
    -- Restore original visibility constraint
    ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_visibility_check;
    ALTER TABLE projects ADD CONSTRAINT projects_visibility_check 
        CHECK (visibility IN ('private', 'team', 'public'));
    
    -- Update visibility values back
    UPDATE projects SET visibility = 'team' WHERE visibility = 'team-only';
EOF
    
    warning "Please execute database rollback manually if database changes were deployed"
    return 0
}

# Function to generate rollback report
generate_rollback_report() {
    local rollback_success=$1
    local report_file="rollback_report_$(date +%Y%m%d_%H%M%S).md"
    
    cat > "$report_file" << EOF
# 🚨 Emergency Rollback Report

**Date**: $(date -u)
**Rollback Type**: $ROLLBACK_TYPE
**Target Version**: $ROLLBACK_VERSION
**Status**: $([ $rollback_success -eq 0 ] && echo "✅ SUCCESS" || echo "❌ PARTIAL/FAILED")
**Executed By**: $(whoami)@$(hostname)

## Rollback Actions Taken

### Kong Gateway
- $([ "$ROLLBACK_TYPE" = "kong" ] || [ "$ROLLBACK_TYPE" = "full" ] && echo "✅ Emergency bypass enabled" || echo "⏭️ Skipped")
- $([ "$ROLLBACK_TYPE" = "kong" ] || [ "$ROLLBACK_TYPE" = "full" ] && echo "✅ Direct API routing activated" || echo "⏭️ Skipped")

### Backend Service
- $([ "$ROLLBACK_TYPE" = "backend" ] || [ "$ROLLBACK_TYPE" = "full" ] && echo "✅ Service rollback initiated" || echo "⏭️ Skipped")
- $([ "$ROLLBACK_TYPE" = "backend" ] || [ "$ROLLBACK_TYPE" = "full" ] && echo "✅ Kong proxy disabled" || echo "⏭️ Skipped")

### Frontend Service
- $([ "$ROLLBACK_TYPE" = "frontend" ] || [ "$ROLLBACK_TYPE" = "full" ] && echo "✅ Service rollback initiated" || echo "⏭️ Skipped")

### Database
- $([ "$ROLLBACK_TYPE" = "database" ] || [ "$ROLLBACK_TYPE" = "full" ] && echo "⚠️ Manual intervention required" || echo "⏭️ Skipped")

## Post-Rollback Health Status

### Service URLs
- **Kong Gateway**: https://kong-production.up.railway.app
- **Backend API**: https://velro-003-backend-production.up.railway.app  
- **Frontend UI**: https://velro-003-frontend-production.up.railway.app

### Health Check Results
- Kong Gateway: $(curl -s -o /dev/null -w "%{http_code}" "https://kong-production.up.railway.app/" || echo "FAILED")
- Backend API: $(curl -s -o /dev/null -w "%{http_code}" "https://velro-003-backend-production.up.railway.app/health" || echo "FAILED")
- Frontend UI: $(curl -s -o /dev/null -w "%{http_code}" "https://velro-003-frontend-production.up.railway.app/" || echo "FAILED")

## Next Steps

### Immediate Actions Required:
1. **Monitor system stability** for next 30 minutes
2. **Validate user functionality** with test accounts
3. **Check error logs** for any remaining issues
4. **Communicate status** to stakeholders

### Investigation Required:
1. **Root cause analysis** of what triggered rollback
2. **Fix deployment issues** before next deployment attempt
3. **Update rollback procedures** based on lessons learned
4. **Test fixes** in staging environment

### Database Rollback (if needed):
If database migration was applied, manual rollback required:
1. Access Supabase Dashboard
2. Restore from backup: pre-team-collab-$(date +%Y%m%d)
3. Verify data integrity after restoration

## Emergency Contacts
- **Platform**: Railway Dashboard - https://railway.app
- **Database**: Supabase Dashboard - https://app.supabase.com
- **Monitoring**: Check service health endpoints
- **Support**: Contact development team immediately

---

**Rollback completed at**: $(date)
**Report generated**: $report_file
EOF

    success "Rollback report generated: $report_file"
    return 0
}

# Main rollback function
perform_rollback() {
    local rollback_success=0
    
    emergency "EMERGENCY ROLLBACK INITIATED"
    echo ""
    echo "Rollback Type: $ROLLBACK_TYPE"
    echo "Target Version: $ROLLBACK_VERSION"
    echo "Timestamp: $(date)"
    echo ""
    
    # Confirmation (skip in CI/CD)
    if [ -t 1 ] && [ -z "$CI" ]; then
        echo -e "${YELLOW}⚠️ This will rollback production services immediately.${NC}"
        echo -n "Continue? (y/N): "
        read -r confirmation
        if [[ ! "$confirmation" =~ ^[Yy]$ ]]; then
            log "Rollback cancelled by user"
            exit 0
        fi
    fi
    
    echo ""
    emergency "PROCEEDING WITH EMERGENCY ROLLBACK..."
    echo ""
    
    # Phase 1: Immediate Kong Gateway bypass (always do this first for safety)
    log "🚨 Phase 1: Emergency Kong Gateway Bypass"
    if ! enable_kong_bypass; then
        error "Failed to enable Kong bypass - continuing anyway"
        ((rollback_success++))
    fi
    echo ""
    
    # Phase 2: Service rollbacks based on type
    case "$ROLLBACK_TYPE" in
        "kong")
            log "🔧 Kong-only rollback complete"
            ;;
        "backend")
            log "🚨 Phase 2: Backend Service Rollback"
            if ! rollback_service "velro-003-backend-production" "Backend API"; then
                ((rollback_success++))
            fi
            ;;
        "frontend")
            log "🚨 Phase 2: Frontend Service Rollback"
            if ! rollback_service "velro-003-frontend-production" "Frontend UI"; then
                ((rollback_success++))
            fi
            ;;
        "database")
            log "🚨 Phase 2: Database Rollback"
            rollback_database
            ;;
        "full"|*)
            log "🚨 Phase 2: Full System Rollback"
            
            # Backend rollback
            if ! rollback_service "velro-003-backend-production" "Backend API"; then
                ((rollback_success++))
            fi
            
            # Frontend rollback
            if ! rollback_service "velro-003-frontend-production" "Frontend UI"; then
                ((rollback_success++))
            fi
            
            # Database rollback instructions
            rollback_database
            ;;
    esac
    
    echo ""
    
    # Phase 3: Health validation
    log "🚨 Phase 3: Post-Rollback Health Validation"
    echo ""
    
    # Wait for services to stabilize
    log "Waiting 30 seconds for services to stabilize..."
    sleep 30
    
    # Validate service health
    health_issues=0
    
    # Kong Gateway (should require auth)
    if ! validate_service_health "https://kong-production.up.railway.app/" "Kong Gateway" "401"; then
        ((health_issues++))
    fi
    
    # Backend API
    if ! validate_service_health "https://velro-003-backend-production.up.railway.app/health" "Backend API" "200"; then
        ((health_issues++))
    fi
    
    # Frontend UI
    if ! validate_service_health "https://velro-003-frontend-production.up.railway.app/" "Frontend UI" "200"; then
        ((health_issues++))
    fi
    
    echo ""
    
    # Phase 4: Results and reporting
    log "🚨 Phase 4: Rollback Complete"
    echo ""
    
    if [ $rollback_success -eq 0 ] && [ $health_issues -eq 0 ]; then
        success "EMERGENCY ROLLBACK COMPLETED SUCCESSFULLY"
        echo ""
        echo "✅ All services rolled back and healthy"
        echo "✅ Kong Gateway bypass enabled for safety"
        echo "✅ System should be stable on previous deployment"
        echo ""
        echo "🔍 Next steps:"
        echo "  1. Monitor system for 30 minutes"
        echo "  2. Validate user functionality"
        echo "  3. Investigate rollback cause"
        echo "  4. Plan corrective deployment"
        
        generate_rollback_report 0
        return 0
    else
        error "ROLLBACK COMPLETED WITH ISSUES"
        echo ""
        echo "⚠️ Rollback executed but some issues remain:"
        echo "  - Service rollback issues: $rollback_success"
        echo "  - Health check failures: $health_issues"
        echo ""
        echo "🚨 IMMEDIATE ACTIONS REQUIRED:"
        echo "  1. Check Railway dashboard for service status"
        echo "  2. Manually verify Kong Gateway bypass is working"
        echo "  3. Test critical user workflows"
        echo "  4. Contact development team if issues persist"
        
        generate_rollback_report 1
        return 1
    fi
}

# Function to show usage
show_usage() {
    echo "🚨 Emergency Rollback Script"
    echo ""
    echo "Usage: $0 [rollback_type] [version]"
    echo ""
    echo "Rollback Types:"
    echo "  kong      - Kong Gateway emergency bypass only"
    echo "  backend   - Backend service rollback + Kong bypass"  
    echo "  frontend  - Frontend service rollback + Kong bypass"
    echo "  database  - Database rollback instructions + Kong bypass"
    echo "  full      - Complete system rollback (default)"
    echo ""
    echo "Version (optional):"
    echo "  previous  - Previous stable deployment (default)"
    echo "  specific  - Specific deployment ID"
    echo ""
    echo "Examples:"
    echo "  $0                          # Full rollback to previous"
    echo "  $0 kong                     # Kong bypass only"
    echo "  $0 backend                  # Backend rollback + Kong bypass"  
    echo "  $0 full v1.2.3              # Full rollback to specific version"
    echo ""
    echo "Environment Variables:"
    echo "  CI=true                     # Skip confirmation prompts"
    echo ""
}

# Main script execution
main() {
    # Check for help flag
    if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
        show_usage
        exit 0
    fi
    
    # Validate rollback type
    case "$ROLLBACK_TYPE" in
        "kong"|"backend"|"frontend"|"database"|"full")
            ;;
        *)
            if [ -n "$1" ]; then
                error "Invalid rollback type: $ROLLBACK_TYPE"
                echo ""
                show_usage
                exit 1
            fi
            ;;
    esac
    
    # Check dependencies
    if ! check_railway_cli; then
        exit 1
    fi
    
    # Perform rollback
    perform_rollback
}

# Run main function with all arguments
main "$@"