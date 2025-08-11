#!/bin/bash

# Enterprise Security-First Deployment Script
# Validates all security configurations before deployment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT=${1:-production}
BASE_URL=${2:-""}
SKIP_VALIDATION=${SKIP_VALIDATION:-false}

echo -e "${BLUE}🔒 VELRO BACKEND SECURITY-FIRST DEPLOYMENT${NC}"
echo -e "${BLUE}=============================================${NC}"
echo -e "Environment: ${ENVIRONMENT}"
echo -e "Skip Validation: ${SKIP_VALIDATION}"
echo ""

# Function to print status
print_status() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "security_validation_script.py" ]; then
    print_error "security_validation_script.py not found. Please run from the backend directory."
    exit 1
fi

# Step 1: Pre-deployment Security Validation
if [ "$SKIP_VALIDATION" != "true" ]; then
    print_status "Running pre-deployment security validation..."
    
    # Run security validation script
    if ! python3 security_validation_script.py --environment "$ENVIRONMENT" --fail-on-issues; then
        print_error "Security validation failed. Deployment blocked."
        echo ""
        echo "To override (NOT RECOMMENDED for production):"
        echo "  SKIP_VALIDATION=true $0 $ENVIRONMENT"
        exit 1
    fi
    
    print_success "Security validation passed"
else
    print_warning "Security validation skipped (SKIP_VALIDATION=true)"
fi

# Step 2: Environment-specific Configuration
print_status "Setting up environment-specific configuration..."

case "$ENVIRONMENT" in
    "production")
        ENV_FILE=".env.production.hardened"
        REQUIRED_VARS=("JWT_SECRET" "SUPABASE_URL" "SUPABASE_ANON_KEY" "SUPABASE_SERVICE_ROLE_KEY" "FAL_KEY")
        ;;
    "staging")
        ENV_FILE=".env.staging.secure"
        REQUIRED_VARS=("JWT_SECRET" "SUPABASE_URL" "SUPABASE_ANON_KEY" "SUPABASE_SERVICE_ROLE_KEY" "FAL_KEY")
        ;;
    "development")
        ENV_FILE=".env.development.secure"
        REQUIRED_VARS=("JWT_SECRET")
        ;;
    *)
        print_error "Unknown environment: $ENVIRONMENT"
        exit 1
        ;;
esac

# Check if environment file exists
if [ ! -f "$ENV_FILE" ]; then
    print_error "Environment file not found: $ENV_FILE"
    print_error "Please create the environment file based on the template."
    exit 1
fi

print_success "Environment file found: $ENV_FILE"

# Step 3: Validate Required Environment Variables
print_status "Validating required environment variables..."

# Load environment file
set -a  # automatically export all variables
source "$ENV_FILE"
set +a

missing_vars=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ] || [ "${!var}" = "REPLACE_WITH_"* ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    print_error "Missing or placeholder environment variables:"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please set all required environment variables before deployment."
    exit 1
fi

print_success "All required environment variables are set"

# Step 4: Validate JWT Secret Strength
print_status "Validating JWT secret strength..."

JWT_LENGTH=${#JWT_SECRET}
if [ "$ENVIRONMENT" = "production" ]; then
    MIN_LENGTH=96
else
    MIN_LENGTH=64
fi

if [ $JWT_LENGTH -lt $MIN_LENGTH ]; then
    print_error "JWT secret too short: $JWT_LENGTH characters (minimum: $MIN_LENGTH)"
    echo "Generate a new secret with:"
    echo "  python3 -c \"import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(96))\""
    exit 1
fi

print_success "JWT secret meets security requirements ($JWT_LENGTH characters)"

# Step 5: Security Configuration Validation
print_status "Validating security configuration..."

security_errors=()

# Check critical security settings
if [ "$ENVIRONMENT" = "production" ]; then
    if [ "$DEBUG" != "false" ]; then
        security_errors+=("DEBUG must be false in production")
    fi
    
    if [ "$DEVELOPMENT_MODE" != "false" ]; then
        security_errors+=("DEVELOPMENT_MODE must be false in production")
    fi
    
    if [ "$EMERGENCY_AUTH_MODE" != "false" ]; then
        security_errors+=("EMERGENCY_AUTH_MODE must be false in production")
    fi
    
    if [ "$ENABLE_MOCK_AUTHENTICATION" != "false" ]; then
        security_errors+=("ENABLE_MOCK_AUTHENTICATION must be false in production")
    fi
    
    if [ "$ENABLE_DEBUG_ENDPOINTS" != "false" ]; then
        security_errors+=("ENABLE_DEBUG_ENDPOINTS must be false in production")
    fi
    
    if [ "$VERBOSE_ERROR_MESSAGES" != "false" ]; then
        security_errors+=("VERBOSE_ERROR_MESSAGES must be false in production")
    fi
fi

if [ ${#security_errors[@]} -gt 0 ]; then
    print_error "Security configuration errors:"
    for error in "${security_errors[@]}"; do
        echo "  - $error"
    done
    exit 1
fi

print_success "Security configuration validated"

# Step 6: Generate Deployment Report
print_status "Generating deployment report..."

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
REPORT_FILE="deployment_report_${ENVIRONMENT}_$(date +%Y%m%d_%H%M%S).json"

cat > "$REPORT_FILE" << EOF
{
  "deployment_metadata": {
    "timestamp": "$TIMESTAMP",
    "environment": "$ENVIRONMENT",
    "base_url": "$BASE_URL",
    "deployer": "$USER",
    "hostname": "$HOSTNAME",
    "deployment_script_version": "1.0.0"
  },
  "security_validation": {
    "validation_skipped": $SKIP_VALIDATION,
    "jwt_secret_length": $JWT_LENGTH,
    "min_jwt_secret_length": $MIN_LENGTH,
    "security_checks_passed": true
  },
  "environment_configuration": {
    "config_file": "$ENV_FILE",
    "debug_mode": "$DEBUG",
    "development_mode": "$DEVELOPMENT_MODE",
    "emergency_auth_mode": "$EMERGENCY_AUTH_MODE",
    "security_headers_enabled": "$SECURITY_HEADERS_ENABLED",
    "csrf_protection_enabled": "$CSRF_PROTECTION_ENABLED"
  },
  "deployment_status": "ready_for_deployment"
}
EOF

print_success "Deployment report generated: $REPORT_FILE"

# Step 7: Railway Deployment (if Railway CLI is available)
if command -v railway &> /dev/null; then
    print_status "Deploying to Railway..."
    
    # Set environment variables in Railway
    print_status "Setting environment variables in Railway..."
    
    # Set core environment variables
    railway variables set "ENVIRONMENT=$ENVIRONMENT" || print_warning "Failed to set ENVIRONMENT"
    railway variables set "DEBUG=$DEBUG" || print_warning "Failed to set DEBUG" 
    railway variables set "DEVELOPMENT_MODE=$DEVELOPMENT_MODE" || print_warning "Failed to set DEVELOPMENT_MODE"
    railway variables set "EMERGENCY_AUTH_MODE=$EMERGENCY_AUTH_MODE" || print_warning "Failed to set EMERGENCY_AUTH_MODE"
    
    # Set JWT configuration
    railway variables set "JWT_SECRET=$JWT_SECRET" || print_error "Failed to set JWT_SECRET (CRITICAL)"
    railway variables set "JWT_ALGORITHM=$JWT_ALGORITHM" || print_warning "Failed to set JWT_ALGORITHM"
    railway variables set "JWT_REQUIRE_HTTPS=$JWT_REQUIRE_HTTPS" || print_warning "Failed to set JWT_REQUIRE_HTTPS"
    
    # Set security configuration
    railway variables set "SECURITY_HEADERS_ENABLED=$SECURITY_HEADERS_ENABLED" || print_warning "Failed to set SECURITY_HEADERS_ENABLED"
    railway variables set "CSRF_PROTECTION_ENABLED=$CSRF_PROTECTION_ENABLED" || print_warning "Failed to set CSRF_PROTECTION_ENABLED"
    railway variables set "RATE_LIMIT_PER_MINUTE=$RATE_LIMIT_PER_MINUTE" || print_warning "Failed to set RATE_LIMIT_PER_MINUTE"
    
    # Deploy
    print_status "Triggering Railway deployment..."
    railway deploy || {
        print_error "Railway deployment failed"
        exit 1
    }
    
    print_success "Railway deployment triggered successfully"
    
else
    print_warning "Railway CLI not found. Please deploy manually or install Railway CLI."
    print_status "Manual deployment steps:"
    echo "1. Set environment variables in Railway dashboard"
    echo "2. Deploy the application"
    echo "3. Run post-deployment validation"
fi

# Step 8: Post-deployment Instructions
print_status "Deployment complete! Next steps:"
echo ""
echo "🔍 POST-DEPLOYMENT VALIDATION:"
echo "  1. Run security validation against deployed app:"
echo "     python3 security_validation_script.py --environment $ENVIRONMENT --base-url YOUR_DEPLOYED_URL"
echo ""
echo "  2. Test critical endpoints:"
echo "     curl -I YOUR_DEPLOYED_URL/health"
echo "     curl -H \"Authorization: Bearer invalid\" YOUR_DEPLOYED_URL/api/v1/auth/me"
echo ""
echo "  3. Monitor security logs:"
echo "     tail -f logs/security_*.log"
echo ""
echo "📊 MONITORING:"
echo "  - Security events dashboard"
echo "  - Rate limiting metrics" 
echo "  - Authentication failure alerts"
echo ""
echo "🚨 SECURITY CHECKLIST:"
echo "  [ ] All security headers present in responses"
echo "  [ ] Rate limiting active and functioning"
echo "  [ ] JWT authentication rejecting invalid tokens"
echo "  [ ] Error responses not leaking information"
echo "  [ ] CORS policies enforced correctly"
echo ""

print_success "Security-first deployment completed successfully!"

# Update deployment report with final status
cat > "$REPORT_FILE" << EOF
{
  "deployment_metadata": {
    "timestamp": "$TIMESTAMP",
    "environment": "$ENVIRONMENT",
    "base_url": "$BASE_URL",
    "deployer": "$USER",
    "hostname": "$HOSTNAME",
    "deployment_script_version": "1.0.0",
    "completion_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  },
  "security_validation": {
    "validation_skipped": $SKIP_VALIDATION,
    "jwt_secret_length": $JWT_LENGTH,
    "min_jwt_secret_length": $MIN_LENGTH,
    "security_checks_passed": true
  },
  "environment_configuration": {
    "config_file": "$ENV_FILE",
    "debug_mode": "$DEBUG",
    "development_mode": "$DEVELOPMENT_MODE",
    "emergency_auth_mode": "$EMERGENCY_AUTH_MODE",
    "security_headers_enabled": "$SECURITY_HEADERS_ENABLED",
    "csrf_protection_enabled": "$CSRF_PROTECTION_ENABLED"
  },
  "deployment_status": "completed_successfully",
  "railway_deployment": $(command -v railway &> /dev/null && echo "true" || echo "false")
}
EOF

echo -e "${GREEN}🎉 DEPLOYMENT COMPLETE - REPORT SAVED: $REPORT_FILE${NC}"