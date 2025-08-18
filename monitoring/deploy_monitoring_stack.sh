#!/bin/bash

# Deploy Complete UUID Authorization Monitoring Stack
# Production-ready monitoring, caching, and logging infrastructure

set -e

echo "🚀 Deploying Velro UUID Authorization Monitoring Stack..."

# Configuration
MONITORING_DIR="$(dirname "$0")"
PROJECT_ROOT="$(dirname "$MONITORING_DIR")"
NETWORK_NAME="velro-app-network"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check available disk space (minimum 10GB)
    AVAILABLE_SPACE=$(df "$PWD" | tail -1 | awk '{print $4}')
    if [ "$AVAILABLE_SPACE" -lt 10485760 ]; then
        log_warning "Low disk space detected. Monitoring stack requires at least 10GB free space."
    fi
    
    log_success "Prerequisites check passed"
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."
    
    mkdir -p "$MONITORING_DIR/data/prometheus"
    mkdir -p "$MONITORING_DIR/data/grafana"
    mkdir -p "$MONITORING_DIR/data/alertmanager"
    mkdir -p "$MONITORING_DIR/data/redis"
    mkdir -p "$MONITORING_DIR/data/loki"
    mkdir -p "$PROJECT_ROOT/logs/audit"
    mkdir -p "$PROJECT_ROOT/logs/security"
    mkdir -p "$PROJECT_ROOT/logs/performance"
    
    # Set appropriate permissions
    sudo chown -R 472:472 "$MONITORING_DIR/data/grafana" 2>/dev/null || true
    sudo chown -R 65534:65534 "$MONITORING_DIR/data/prometheus" 2>/dev/null || true
    
    log_success "Directories created successfully"
}

# Create Docker network if it doesn't exist
create_network() {
    log_info "Creating Docker network..."
    
    if ! docker network ls | grep -q "$NETWORK_NAME"; then
        docker network create "$NETWORK_NAME" --driver bridge
        log_success "Network '$NETWORK_NAME' created"
    else
        log_info "Network '$NETWORK_NAME' already exists"
    fi
}

# Generate configuration files with environment-specific values
generate_configs() {
    log_info "Generating configuration files..."
    
    # Update Prometheus config with actual backend URL
    if [ -f "$PROJECT_ROOT/.env" ]; then
        source "$PROJECT_ROOT/.env"
        
        # Replace localhost with actual backend service name/URL
        sed -i.bak "s/localhost:8000/${BACKEND_HOST:-localhost:8000}/g" "$MONITORING_DIR/prometheus_config.yml" 2>/dev/null || true
    fi
    
    log_success "Configuration files updated"
}

# Deploy monitoring stack
deploy_stack() {
    log_info "Deploying monitoring stack..."
    
    cd "$MONITORING_DIR"
    
    # Pull latest images
    log_info "Pulling Docker images..."
    docker-compose -f docker-compose.monitoring.yml pull
    
    # Start services
    log_info "Starting monitoring services..."
    docker-compose -f docker-compose.monitoring.yml up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to start..."
    sleep 30
    
    # Check service health
    check_service_health
    
    log_success "Monitoring stack deployed successfully"
}

# Check health of deployed services
check_service_health() {
    log_info "Checking service health..."
    
    local services=(
        "prometheus:9090/api/v1/status/config"
        "grafana:3000/api/health"
        "alertmanager:9093/api/v1/status"
        "redis:6379"
    )
    
    for service in "${services[@]}"; do
        local name=$(echo "$service" | cut -d: -f1)
        local endpoint=$(echo "$service" | cut -d: -f2-)
        
        if [[ "$name" == "redis" ]]; then
            # Redis health check
            if docker exec velro-redis redis-cli ping | grep -q "PONG"; then
                log_success "$name is healthy"
            else
                log_error "$name health check failed"
            fi
        else
            # HTTP health check
            if curl -sf "http://localhost:$endpoint" >/dev/null 2>&1; then
                log_success "$name is healthy"
            else
                log_warning "$name health check failed - service may still be starting"
            fi
        fi
    done
}

# Import Grafana dashboards
import_dashboards() {
    log_info "Importing Grafana dashboards..."
    
    # Wait for Grafana to be fully ready
    sleep 10
    
    local dashboards_dir="$MONITORING_DIR/grafana_dashboards"
    local grafana_url="http://admin:velro_admin_2024@localhost:3000"
    
    for dashboard_file in "$dashboards_dir"/*.json; do
        if [ -f "$dashboard_file" ]; then
            local dashboard_name=$(basename "$dashboard_file" .json)
            
            # Import dashboard via API
            curl -X POST "$grafana_url/api/dashboards/db" \
                -H "Content-Type: application/json" \
                -d @"$dashboard_file" \
                >/dev/null 2>&1 && \
                log_success "Imported dashboard: $dashboard_name" || \
                log_warning "Failed to import dashboard: $dashboard_name"
        fi
    done
}

# Setup alerting rules
setup_alerting() {
    log_info "Setting up alerting rules..."
    
    # Reload Prometheus configuration
    curl -X POST http://localhost:9090/-/reload >/dev/null 2>&1 && \
        log_success "Prometheus configuration reloaded" || \
        log_warning "Failed to reload Prometheus configuration"
    
    # Check if alerts are loaded
    local alert_count=$(curl -s http://localhost:9090/api/v1/rules | jq '.data.groups | length' 2>/dev/null || echo "0")
    
    if [ "$alert_count" -gt 0 ]; then
        log_success "Loaded $alert_count alert groups"
    else
        log_warning "No alert groups loaded"
    fi
}

# Display access information
display_access_info() {
    log_success "🎉 Monitoring stack deployment complete!"
    
    echo ""
    echo "📊 Access Information:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 Prometheus (Metrics):     http://localhost:9090"
    echo "📈 Grafana (Dashboards):     http://localhost:3000"
    echo "   Username: admin"
    echo "   Password: velro_admin_2024"
    echo ""
    echo "🚨 Alertmanager:             http://localhost:9093"
    echo "💾 Redis Cache:              localhost:6379"
    echo "📋 Loki (Logs):              http://localhost:3100"
    echo "🔍 Jaeger (Tracing):         http://localhost:16686"
    echo "📊 cAdvisor (Containers):    http://localhost:8080"
    echo ""
    echo "🎯 Key Performance Targets:"
    echo "   • Authorization response time: < 100ms"
    echo "   • Cache hit rate: > 95%"
    echo "   • Security violation detection: Real-time"
    echo "   • Audit log completeness: 100%"
    echo ""
    echo "📚 Pre-loaded Dashboards:"
    echo "   • UUID Authorization Performance"
    echo "   • Redis Cache Performance (95%+ Hit Rate)"
    echo "   • Security Monitoring & Threat Detection"
    echo ""
    echo "🔔 Alerting Configured for:"
    echo "   • SLA violations (>100ms response time)"
    echo "   • Cache hit rate below 95%"
    echo "   • Security violations"
    echo "   • System health issues"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Cleanup function for failed deployments
cleanup() {
    log_warning "Cleaning up failed deployment..."
    cd "$MONITORING_DIR"
    docker-compose -f docker-compose.monitoring.yml down -v 2>/dev/null || true
}

# Main execution
main() {
    echo "🛡️  Velro UUID Authorization System - Complete Monitoring Stack Deployment"
    echo "========================================================================"
    
    # Set trap for cleanup on error
    trap cleanup EXIT
    
    check_prerequisites
    create_directories
    create_network
    generate_configs
    deploy_stack
    import_dashboards
    setup_alerting
    
    # Disable cleanup trap on success
    trap - EXIT
    
    display_access_info
    
    echo ""
    log_info "Monitoring stack is now collecting metrics and ready for production use."
    log_info "Check the logs with: docker-compose -f docker-compose.monitoring.yml logs -f"
}

# Script options
case "${1:-deploy}" in
    deploy)
        main
        ;;
    stop)
        log_info "Stopping monitoring stack..."
        cd "$MONITORING_DIR"
        docker-compose -f docker-compose.monitoring.yml stop
        log_success "Monitoring stack stopped"
        ;;
    restart)
        log_info "Restarting monitoring stack..."
        cd "$MONITORING_DIR"
        docker-compose -f docker-compose.monitoring.yml restart
        log_success "Monitoring stack restarted"
        ;;
    logs)
        cd "$MONITORING_DIR"
        docker-compose -f docker-compose.monitoring.yml logs -f
        ;;
    status)
        cd "$MONITORING_DIR"
        docker-compose -f docker-compose.monitoring.yml ps
        ;;
    *)
        echo "Usage: $0 {deploy|stop|restart|logs|status}"
        exit 1
        ;;
esac