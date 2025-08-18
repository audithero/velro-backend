#!/bin/bash
# Railway Deployment Script for Velro Backend
# Optimized for FastAPI deployment with comprehensive validation

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Railway CLI is installed
check_railway_cli() {
    log "Checking Railway CLI installation..."
    if ! command -v railway &> /dev/null; then
        error "Railway CLI not found. Install it with: npm install -g @railway/cli"
        exit 1
    fi
    success "Railway CLI found: $(railway --version)"
}

# Login to Railway
railway_login() {
    log "Checking Railway authentication..."
    if ! railway whoami &> /dev/null; then
        warning "Not logged in to Railway. Please login..."
        railway login
    fi
    success "Authenticated with Railway as: $(railway whoami)"
}

# Validate environment variables
validate_env_vars() {
    log "Validating environment variables..."
    
    local required_vars=(
        "SUPABASE_URL"
        "SUPABASE_ANON_KEY"
        "SUPABASE_SERVICE_ROLE_KEY"
        "FAL_KEY"
    )
    
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        error "Missing required environment variables:"
        printf '%s\n' "${missing_vars[@]}"
        echo ""
        echo "Please set these variables before deploying:"
        echo "export SUPABASE_URL='your-supabase-url'"
        echo "export SUPABASE_ANON_KEY='your-anon-key'"
        echo "export SUPABASE_SERVICE_ROLE_KEY='your-service-role-key'"
        echo "export FAL_KEY='your-fal-key'"
        exit 1
    fi
    
    success "All required environment variables are set"
}

# Validate configuration files
validate_config_files() {
    log "Validating configuration files..."
    
    local required_files=(
        "main.py"
        "requirements.txt"
        "nixpacks.toml"
        "railway.toml"
        "config.py"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            error "Required file missing: $file"
            exit 1
        fi
    done
    
    success "All required configuration files present"
}

# Run tests before deployment
run_tests() {
    log "Running pre-deployment tests..."
    
    # Check if test requirements are available
    if [ -f "requirements-test.txt" ]; then
        log "Installing test dependencies..."
        pip install -r requirements-test.txt
    fi
    
    # Run health check validation
    if [ -f "railway_health_check.py" ]; then
        log "Running health check validation..."
        python railway_health_check.py || warning "Health check validation failed"
    fi
    
    # Run basic import test
    log "Testing Python imports..."
    python -c "
import sys
sys.path.append('.')
try:
    from main import app
    from config import settings
    print('✅ Import test passed')
except Exception as e:
    print(f'❌ Import test failed: {e}')
    sys.exit(1)
    "
    
    success "Pre-deployment tests completed"
}

# Deploy to Railway
deploy_to_railway() {
    log "Starting Railway deployment..."
    
    # Check if already in a Railway project
    if ! railway status &> /dev/null; then
        warning "Not in a Railway project. Creating new project..."
        railway init
    fi
    
    # Set environment variables
    log "Setting environment variables..."
    railway variables set ENVIRONMENT=production
    railway variables set DEBUG=false
    railway variables set RAILWAY_DEPLOYMENT=true
    
    # Set required environment variables
    railway variables set SUPABASE_URL="$SUPABASE_URL"
    railway variables set SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" 
    railway variables set SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY"
    railway variables set FAL_KEY="$FAL_KEY"
    
    # Set optional variables if they exist
    [ -n "$JWT_SECRET" ] && railway variables set JWT_SECRET="$JWT_SECRET"
    [ -n "$REDIS_URL" ] && railway variables set REDIS_URL="$REDIS_URL"
    
    # Deploy
    log "Deploying to Railway..."
    railway up --detach
    
    success "Deployment initiated"
}

# Monitor deployment
monitor_deployment() {
    log "Monitoring deployment status..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        log "Checking deployment status (attempt $attempt/$max_attempts)..."
        
        if railway status | grep -q "Active"; then
            success "Deployment is active!"
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error "Deployment monitoring timeout"
            return 1
        fi
        
        sleep 10
        ((attempt++))
    done
    
    # Get deployment URL
    local service_url
    service_url=$(railway domain | head -n 1 || echo "URL not available")
    
    if [ "$service_url" != "URL not available" ] && [ -n "$service_url" ]; then
        success "Service deployed at: $service_url"
        
        # Test the deployed service
        log "Testing deployed service..."
        if curl -f "$service_url/health" &> /dev/null; then
            success "Health check passed!"
        else
            warning "Health check failed - service may still be starting"
        fi
    else
        warning "Service URL not available yet"
    fi
}

# Show deployment logs
show_logs() {
    log "Showing recent deployment logs..."
    railway logs --tail 50 || warning "Could not fetch logs"
}

# Main deployment function
main() {
    echo ""
    echo "🚀 Railway Deployment Script for Velro Backend"
    echo "=============================================="
    echo ""
    
    # Pre-deployment checks
    check_railway_cli
    railway_login
    validate_env_vars
    validate_config_files
    
    # Optional: Run tests
    if [ "$1" != "--skip-tests" ]; then
        run_tests
    else
        warning "Skipping tests (--skip-tests flag used)"
    fi
    
    # Deploy
    deploy_to_railway
    
    # Monitor deployment
    if [ "$1" != "--no-monitor" ]; then
        monitor_deployment
    fi
    
    # Show logs
    if [ "$1" != "--no-logs" ]; then
        show_logs
    fi
    
    echo ""
    success "Deployment process completed!"
    echo ""
    echo "Next steps:"
    echo "1. Check Railway dashboard: https://railway.app/dashboard"
    echo "2. Monitor logs: railway logs"
    echo "3. Check service status: railway status"
    echo "4. View domains: railway domain"
    echo ""
}

# Handle script arguments
case "$1" in
    --help|-h)
        echo "Railway Deployment Script for Velro Backend"
        echo ""
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --skip-tests    Skip pre-deployment tests"
        echo "  --no-monitor    Skip deployment monitoring"
        echo "  --no-logs       Skip showing deployment logs"
        echo "  --help, -h      Show this help message"
        echo ""
        echo "Required environment variables:"
        echo "  SUPABASE_URL"
        echo "  SUPABASE_ANON_KEY"
        echo "  SUPABASE_SERVICE_ROLE_KEY"
        echo "  FAL_KEY"
        echo ""
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac