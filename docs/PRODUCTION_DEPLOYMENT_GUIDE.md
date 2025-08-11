# Production Deployment Guide

## Overview

This guide provides comprehensive procedures for deploying the Velro authentication system to production environments, with specific focus on Railway deployment, security configuration, and operational readiness.

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Environment Configuration](#environment-configuration)
3. [Railway Deployment](#railway-deployment)
4. [Security Configuration](#security-configuration)
5. [Database Setup](#database-setup)
6. [Monitoring and Logging](#monitoring-and-logging)
7. [Health Checks](#health-checks)
8. [Backup and Recovery](#backup-and-recovery)
9. [Rollback Procedures](#rollback-procedures)
10. [Post-Deployment Validation](#post-deployment-validation)

## Pre-Deployment Checklist

### Code Quality Validation
- [ ] All tests passing (unit, integration, security)
- [ ] Code review completed and approved
- [ ] Security scan passed (no critical vulnerabilities)
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Changelog prepared

### Dependencies Validation
- [ ] All Python dependencies pinned in `requirements.txt`
- [ ] No development-only dependencies in production
- [ ] Security audit of dependencies completed
- [ ] Dockerfile optimized for production

### Security Pre-checks
- [ ] JWT secrets generated and stored securely
- [ ] No hardcoded credentials in code
- [ ] All environment variables configured
- [ ] SSL/TLS certificates validated
- [ ] CORS origins properly configured

## Environment Configuration

### Required Environment Variables

#### Core Application Settings
```bash
# Application Configuration
APP_NAME="Velro"
APP_VERSION="1.1.2"
ENVIRONMENT="production"
DEBUG="false"
DEVELOPMENT_MODE="false"
EMERGENCY_AUTH_MODE="false"

# Server Configuration
PORT="8000"
HOST="0.0.0.0"

# Railway Environment (auto-configured)
RAILWAY_ENVIRONMENT="production"
RAILWAY_PROJECT_NAME="velro-backend"
RAILWAY_SERVICE_NAME="velro-backend"
```

#### Database Configuration (Supabase)
```bash
# Supabase Configuration
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Optional: Direct database URL (Railway-provided)
DATABASE_URL="postgresql://username:password@host:port/database"
```

#### Authentication Configuration
```bash
# JWT Configuration (CRITICAL)
JWT_SECRET="your-super-secure-64-character-minimum-jwt-secret-key-here-with-random-chars"
JWT_ALGORITHM="HS256"
JWT_EXPIRATION_HOURS="24"
JWT_REFRESH_EXPIRE_HOURS="168"  # 7 days
JWT_BLACKLIST_ENABLED="true"
JWT_REQUIRE_HTTPS="true"

# Security Configuration
PASSWORD_HASH_ROUNDS="12"
MAX_LOGIN_ATTEMPTS="5"
LOCKOUT_DURATION_MINUTES="15"
SESSION_TIMEOUT_MINUTES="30"
```

#### External Services
```bash
# FAL.ai API Configuration
FAL_KEY="your-fal-api-key-here"

# Email Service (optional)
SMTP_HOST="smtp.example.com"
SMTP_PORT="587"
SMTP_USER="noreply@velro.ai"
SMTP_PASS="your-email-password"
```

#### Rate Limiting and Performance
```bash
# Rate Limiting
RATE_LIMIT_PER_MINUTE="60"
GENERATION_RATE_LIMIT="10"

# File Upload
MAX_FILE_SIZE="10485760"  # 10MB
ALLOWED_FILE_TYPES="image/jpeg,image/png,image/webp,image/gif"

# Storage
STORAGE_BUCKET="velro-storage"

# Redis (optional, for advanced rate limiting)
REDIS_URL="redis://user:pass@host:port/0"
```

#### CORS Configuration
```bash
# CORS Origins (comma-separated)
ALLOWED_ORIGINS="https://velro.ai,https://www.velro.ai,https://velro-frontend-production.up.railway.app"
```

#### User Configuration
```bash
# Default Settings
DEFAULT_USER_CREDITS="1000"
```

### Environment Variable Validation Script

Create a validation script to check environment configuration:

```python
# scripts/validate_env.py
import os
import sys
from typing import List, Dict, Any

class EnvironmentValidator:
    """Validate production environment configuration."""
    
    REQUIRED_VARS = {
        'ENVIRONMENT': 'production',
        'DEBUG': 'false',
        'DEVELOPMENT_MODE': 'false',
        'EMERGENCY_AUTH_MODE': 'false',
        'SUPABASE_URL': None,
        'SUPABASE_ANON_KEY': None,
        'SUPABASE_SERVICE_ROLE_KEY': None,
        'JWT_SECRET': None,
        'FAL_KEY': None,
    }
    
    SECURITY_VALIDATIONS = {
        'JWT_SECRET': lambda x: len(x) >= 64,
        'JWT_REQUIRE_HTTPS': lambda x: x.lower() == 'true',
        'PASSWORD_HASH_ROUNDS': lambda x: int(x) >= 12,
    }
    
    def validate(self) -> Dict[str, Any]:
        """Validate all environment variables."""
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'config': {}
        }
        
        # Check required variables
        for var, expected_value in self.REQUIRED_VARS.items():
            value = os.getenv(var)
            
            if value is None:
                results['errors'].append(f"Missing required environment variable: {var}")
                results['valid'] = False
            elif expected_value and value != expected_value:
                results['errors'].append(f"Invalid value for {var}: expected {expected_value}, got {value}")
                results['valid'] = False
            else:
                results['config'][var] = value
        
        # Security validations
        for var, validator in self.SECURITY_VALIDATIONS.items():
            value = os.getenv(var)
            if value and not validator(value):
                results['errors'].append(f"Security validation failed for {var}")
                results['valid'] = False
        
        # Warnings for best practices
        if os.getenv('REDIS_URL') is None:
            results['warnings'].append("REDIS_URL not set - rate limiting will use in-memory storage")
        
        return results

if __name__ == "__main__":
    validator = EnvironmentValidator()
    results = validator.validate()
    
    print("Environment Validation Report")
    print("=" * 40)
    print(f"Status: {'PASS' if results['valid'] else 'FAIL'}")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  ❌ {error}")
    
    if results['warnings']:
        print("\nWarnings:")
        for warning in results['warnings']:
            print(f"  ⚠️  {warning}")
    
    print(f"\nConfiguration Summary:")
    for key, value in results['config'].items():
        if 'SECRET' in key or 'KEY' in key or 'PASS' in key:
            print(f"  {key}: {'*' * len(value) if value else 'NOT_SET'}")
        else:
            print(f"  {key}: {value}")
    
    sys.exit(0 if results['valid'] else 1)
```

## Railway Deployment

### 1. Project Setup

#### Create Railway Project
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Create new project
railway create velro-backend

# Link to existing project (if already created)
railway link <project-id>
```

#### Configure Railway Services
```bash
# Add backend service
railway service create velro-backend

# Add database service (if using Railway PostgreSQL)
railway service create postgresql
```

### 2. Deployment Configuration

#### railway.json Configuration
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "buildCommand": "pip install -r requirements.txt"
  },
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

#### Dockerfile Optimization
```dockerfile
# Use Python 3.11 slim image for production
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Expose port
EXPOSE 8000

# Start application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. Environment Variables Setup

#### Set Production Variables
```bash
# Set all required environment variables
railway variables set ENVIRONMENT=production
railway variables set DEBUG=false
railway variables set DEVELOPMENT_MODE=false
railway variables set EMERGENCY_AUTH_MODE=false

# Set JWT secret (generate secure 64+ character string)
railway variables set JWT_SECRET="$(openssl rand -base64 64)"

# Set Supabase configuration
railway variables set SUPABASE_URL="your-supabase-url"
railway variables set SUPABASE_ANON_KEY="your-anon-key"
railway variables set SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"

# Set FAL.ai API key
railway variables set FAL_KEY="your-fal-api-key"

# Set CORS origins
railway variables set ALLOWED_ORIGINS="https://velro.ai,https://www.velro.ai,https://velro-frontend-production.up.railway.app"
```

#### Validate Environment Setup
```bash
# Run validation script before deployment
python scripts/validate_env.py
```

### 4. Deployment Execution

#### Deploy to Railway
```bash
# Deploy current branch
railway up

# Deploy specific branch
railway up --service velro-backend

# Monitor deployment logs
railway logs --service velro-backend

# Check deployment status
railway status
```

#### Custom Domain Setup (Optional)
```bash
# Add custom domain
railway domain add velro-backend.com

# Configure DNS (add CNAME record)
# velro-backend.com -> <railway-provided-domain>
```

## Security Configuration

### 1. JWT Security Setup

#### Generate Secure JWT Secret
```bash
# Generate 64-character secure secret
openssl rand -base64 64

# Or use Python
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

#### JWT Configuration Validation
```python
# Validate JWT configuration
from config import settings

def validate_jwt_config():
    """Validate JWT configuration for production."""
    errors = []
    
    if len(settings.jwt_secret) < 64:
        errors.append("JWT_SECRET must be at least 64 characters in production")
    
    if not settings.jwt_require_https:
        errors.append("JWT_REQUIRE_HTTPS must be enabled in production")
    
    if settings.jwt_expiration_hours > 24:
        errors.append("JWT expiration should not exceed 24 hours")
    
    return errors
```

### 2. HTTPS Configuration

#### Railway HTTPS (Automatic)
Railway automatically provides HTTPS for all deployments with:
- Automatic SSL certificate generation
- HTTP to HTTPS redirects
- TLS 1.2+ enforcement

#### Custom Domain HTTPS
```bash
# Railway automatically handles SSL for custom domains
railway domain add your-domain.com

# Verify SSL certificate
curl -I https://your-domain.com/health
```

### 3. Security Headers Configuration

Headers are automatically configured in the application:

```python
# Security headers (in config.py)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"
}
```

## Database Setup

### 1. Supabase Configuration

#### Database Schema Setup
```sql
-- Run these SQL commands in Supabase SQL Editor

-- Enable RLS (Row Level Security)
ALTER TABLE auth.users ENABLE ROW LEVEL SECURITY;

-- Create users profile table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE,
    display_name TEXT,
    avatar_url TEXT,
    credits_balance INTEGER DEFAULT 1000,
    role TEXT DEFAULT 'viewer',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS on users table
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Create RLS policies
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- Create trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

#### Storage Configuration
```sql
-- Enable storage for user avatars
INSERT INTO storage.buckets (id, name, public) VALUES ('avatars', 'avatars', true);

-- Create storage policies
CREATE POLICY "Avatar images are publicly accessible" ON storage.objects
    FOR SELECT USING (bucket_id = 'avatars');

CREATE POLICY "Users can upload their own avatar" ON storage.objects
    FOR INSERT WITH CHECK (bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]);
```

### 2. Database Migrations

#### Migration Management
```python
# scripts/run_migrations.py
import os
import asyncio
from database import SupabaseClient

async def run_migrations():
    """Run database migrations."""
    db_client = SupabaseClient()
    
    # Check if migrations table exists
    result = db_client.service_client.table('migrations').select('*').execute()
    
    # Run pending migrations
    migrations_dir = 'migrations'
    for file in sorted(os.listdir(migrations_dir)):
        if file.endswith('.sql'):
            migration_name = file[:-4]
            
            # Check if migration already applied
            existing = db_client.service_client.table('migrations').select('*').eq('name', migration_name).execute()
            
            if not existing.data:
                # Apply migration
                with open(os.path.join(migrations_dir, file), 'r') as f:
                    sql = f.read()
                
                # Execute migration SQL
                db_client.service_client.postgrest.query(sql).execute()
                
                # Record migration
                db_client.service_client.table('migrations').insert({
                    'name': migration_name,
                    'applied_at': 'NOW()'
                }).execute()
                
                print(f"Applied migration: {migration_name}")

if __name__ == "__main__":
    asyncio.run(run_migrations())
```

## Monitoring and Logging

### 1. Application Logging

#### Logging Configuration
```python
# logging_config.py
import logging
import sys
from config import settings

def setup_logging():
    """Configure production logging."""
    
    # Set log level based on environment
    log_level = logging.DEBUG if settings.debug else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('app.log') if not settings.is_production() else logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Configure specific loggers
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    
    # Security logger
    security_logger = logging.getLogger('security')
    security_logger.setLevel(logging.INFO)
    
    return logging.getLogger(__name__)
```

### 2. Health Checks

#### Application Health Check
```python
# health_check.py
from fastapi import APIRouter, status
from database import SupabaseClient
import time
import os

router = APIRouter()

@router.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": os.getenv("APP_VERSION", "unknown"),
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "checks": {}
    }
    
    # Database health check
    try:
        db_client = SupabaseClient()
        if db_client.is_available():
            # Test database connection
            result = db_client.service_client.table('users').select('count').execute()
            health_status["checks"]["database"] = "healthy"
        else:
            health_status["checks"]["database"] = "unhealthy"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
    
    # External services health check
    try:
        # Check FAL.ai API availability
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("https://fal.run/", timeout=5.0)
            if response.status_code == 200:
                health_status["checks"]["fal_api"] = "healthy"
            else:
                health_status["checks"]["fal_api"] = "degraded"
    except Exception:
        health_status["checks"]["fal_api"] = "unknown"
    
    # Memory and CPU checks (basic)
    import psutil
    health_status["system"] = {
        "memory_percent": psutil.virtual_memory().percent,
        "cpu_percent": psutil.cpu_percent(),
        "disk_percent": psutil.disk_usage('/').percent
    }
    
    # Return appropriate status code
    if health_status["status"] == "healthy":
        status_code = status.HTTP_200_OK
    elif health_status["status"] == "degraded":
        status_code = status.HTTP_200_OK  # Still serving traffic
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return health_status
```

### 3. Railway Monitoring

#### Railway Health Check Configuration
Railway automatically monitors:
- HTTP response codes
- Response times
- Memory usage
- CPU usage
- Restart frequency

#### Custom Metrics
```bash
# View Railway metrics
railway metrics

# View logs
railway logs --follow

# Monitor deployment status
railway status
```

## Backup and Recovery

### 1. Database Backup

#### Supabase Backup (Automatic)
Supabase provides:
- Automatic daily backups
- Point-in-time recovery
- Cross-region replication

#### Manual Backup Script
```python
# scripts/backup_database.py
import os
import datetime
from database import SupabaseClient

def backup_user_data():
    """Backup user data to file."""
    
    db_client = SupabaseClient()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export users table
    users_data = db_client.service_client.table('users').select('*').execute()
    
    backup_file = f"backup_users_{timestamp}.json"
    with open(backup_file, 'w') as f:
        import json
        json.dump(users_data.data, f, indent=2, default=str)
    
    print(f"Backup saved to {backup_file}")
    return backup_file

if __name__ == "__main__":
    backup_user_data()
```

### 2. Application State Backup

#### Configuration Backup
```bash
# Backup environment variables
railway variables > railway_vars_backup_$(date +%Y%m%d).txt

# Backup Railway configuration
railway config > railway_config_backup_$(date +%Y%m%d).json
```

## Rollback Procedures

### 1. Railway Rollback

#### Quick Rollback
```bash
# View deployment history
railway deployments

# Rollback to previous deployment
railway rollback <deployment-id>

# Or rollback to previous successful deployment
railway rollback --latest-successful
```

#### Manual Rollback Process
1. **Identify Issue**: Check logs and metrics
2. **Stop Traffic**: Update load balancer (if applicable)
3. **Rollback Code**: Deploy previous version
4. **Verify Health**: Check health endpoints
5. **Resume Traffic**: Re-enable load balancer
6. **Post-Rollback**: Investigate and document

### 2. Database Rollback

#### Supabase Point-in-Time Recovery
```bash
# Contact Supabase support for point-in-time recovery
# or use Supabase dashboard to restore backup
```

#### Migration Rollback
```python
# scripts/rollback_migration.py
def rollback_migration(migration_name: str):
    """Rollback a specific migration."""
    
    db_client = SupabaseClient()
    
    # Load rollback SQL
    rollback_file = f"migrations/{migration_name}_rollback.sql"
    if os.path.exists(rollback_file):
        with open(rollback_file, 'r') as f:
            rollback_sql = f.read()
        
        # Execute rollback
        db_client.service_client.postgrest.query(rollback_sql).execute()
        
        # Remove migration record
        db_client.service_client.table('migrations').delete().eq('name', migration_name).execute()
        
        print(f"Rolled back migration: {migration_name}")
    else:
        print(f"No rollback script found for {migration_name}")
```

## Post-Deployment Validation

### 1. Automated Validation Script

```python
# scripts/post_deployment_validation.py
import asyncio
import httpx
import time
from typing import Dict, Any

class DeploymentValidator:
    """Validate production deployment."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.results = {}
    
    async def validate_health_endpoint(self) -> bool:
        """Validate health endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=10.0)
                
                if response.status_code == 200:
                    data = response.json()
                    self.results['health'] = {
                        'status': 'pass',
                        'response_time': response.elapsed.total_seconds(),
                        'data': data
                    }
                    return True
                else:
                    self.results['health'] = {
                        'status': 'fail',
                        'status_code': response.status_code
                    }
                    return False
        except Exception as e:
            self.results['health'] = {
                'status': 'error',
                'error': str(e)
            }
            return False
    
    async def validate_auth_endpoints(self) -> bool:
        """Validate authentication endpoints."""
        auth_results = {}
        
        # Test registration endpoint
        try:
            async with httpx.AsyncClient() as client:
                # Test security info endpoint (public)
                response = await client.get(f"{self.base_url}/api/v1/auth/security-info")
                
                if response.status_code == 200:
                    auth_results['security_info'] = 'pass'
                else:
                    auth_results['security_info'] = f'fail: {response.status_code}'
        except Exception as e:
            auth_results['security_info'] = f'error: {e}'
        
        self.results['auth'] = auth_results
        return all(result == 'pass' for result in auth_results.values())
    
    async def validate_cors_configuration(self) -> bool:
        """Validate CORS configuration."""
        try:
            async with httpx.AsyncClient() as client:
                # Send preflight request
                response = await client.options(
                    f"{self.base_url}/api/v1/auth/login",
                    headers={
                        'Origin': 'https://velro.ai',
                        'Access-Control-Request-Method': 'POST',
                        'Access-Control-Request-Headers': 'Content-Type'
                    }
                )
                
                cors_headers = {
                    'access-control-allow-origin': response.headers.get('access-control-allow-origin'),
                    'access-control-allow-methods': response.headers.get('access-control-allow-methods'),
                    'access-control-allow-headers': response.headers.get('access-control-allow-headers'),
                }
                
                self.results['cors'] = {
                    'status': 'pass' if response.status_code == 200 else 'fail',
                    'headers': cors_headers
                }
                
                return response.status_code == 200
        except Exception as e:
            self.results['cors'] = {
                'status': 'error',
                'error': str(e)
            }
            return False
    
    async def validate_ssl_certificate(self) -> bool:
        """Validate SSL certificate."""
        try:
            import ssl
            import socket
            from urllib.parse import urlparse
            
            parsed_url = urlparse(self.base_url)
            hostname = parsed_url.hostname
            port = parsed_url.port or 443
            
            context = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    
                    self.results['ssl'] = {
                        'status': 'pass',
                        'certificate': {
                            'subject': cert.get('subject'),
                            'issuer': cert.get('issuer'),
                            'notAfter': cert.get('notAfter')
                        }
                    }
                    return True
        except Exception as e:
            self.results['ssl'] = {
                'status': 'error',
                'error': str(e)
            }
            return False
    
    async def run_all_validations(self) -> Dict[str, Any]:
        """Run comprehensive deployment validation."""
        
        print("Running post-deployment validation...")
        
        validations = [
            ("Health Check", self.validate_health_endpoint()),
            ("Authentication Endpoints", self.validate_auth_endpoints()),
            ("CORS Configuration", self.validate_cors_configuration()),
            ("SSL Certificate", self.validate_ssl_certificate())
        ]
        
        results = {}
        for name, validation in validations:
            print(f"Validating {name}...")
            results[name.lower().replace(' ', '_')] = await validation
            time.sleep(1)  # Rate limiting
        
        # Generate summary
        passed = sum(results.values())
        total = len(results)
        
        self.results['summary'] = {
            'total_checks': total,
            'passed_checks': passed,
            'failed_checks': total - passed,
            'success_rate': (passed / total) * 100,
            'overall_status': 'PASS' if passed == total else 'FAIL'
        }
        
        return self.results

async def main():
    """Run post-deployment validation."""
    
    # Use production URL
    base_url = "https://velro-backend-production.up.railway.app"
    
    validator = DeploymentValidator(base_url)
    results = await validator.run_all_validations()
    
    # Print results
    print("\n" + "="*50)
    print("POST-DEPLOYMENT VALIDATION REPORT")
    print("="*50)
    
    summary = results['summary']
    print(f"Overall Status: {summary['overall_status']}")
    print(f"Success Rate: {summary['success_rate']:.1f}%")
    print(f"Checks: {summary['passed_checks']}/{summary['total_checks']} passed")
    
    print("\nDetailed Results:")
    for key, value in results.items():
        if key != 'summary':
            print(f"  {key}: {value}")
    
    return summary['overall_status'] == 'PASS'

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
```

### 2. Manual Validation Checklist

#### Functional Testing
- [ ] Health endpoint responds (200 OK)
- [ ] Authentication endpoints accessible
- [ ] CORS headers properly configured
- [ ] SSL certificate valid and trusted
- [ ] Database connectivity working
- [ ] External API integrations functional

#### Performance Testing
- [ ] Response times under 2 seconds
- [ ] Memory usage within limits
- [ ] CPU usage normal
- [ ] No memory leaks detected

#### Security Testing
- [ ] HTTPS enforced
- [ ] Security headers present
- [ ] No sensitive data in logs
- [ ] Rate limiting functional
- [ ] Input validation working

#### Integration Testing
- [ ] Frontend-backend communication
- [ ] User registration flow
- [ ] User login flow
- [ ] Protected endpoints working
- [ ] Token refresh working

## Troubleshooting Common Issues

### 1. Deployment Failures

#### Build Failures
```bash
# Check build logs
railway logs --deployment <deployment-id>

# Common fixes:
# 1. Update requirements.txt
# 2. Fix Python version compatibility
# 3. Resolve dependency conflicts
```

#### Environment Variable Issues
```bash
# List all variables
railway variables

# Check specific variable
railway variables get JWT_SECRET

# Update variable
railway variables set JWT_SECRET="new-value"
```

### 2. Runtime Issues

#### Database Connection Errors
```python
# Check database configuration
from database import SupabaseClient
db_client = SupabaseClient()
print(f"DB Available: {db_client.is_available()}")
```

#### Authentication Failures
```bash
# Test auth endpoint
curl -X GET "https://your-domain.com/api/v1/auth/security-info"

# Check JWT configuration
curl -X GET "https://your-domain.com/api/v1/auth/debug-auth" \
  -H "Authorization: Bearer mock_token_test"
```

### 3. Performance Issues

#### High Response Times
1. Check database query performance
2. Review rate limiting configuration
3. Monitor memory usage
4. Check external API response times

#### Memory Leaks
1. Monitor memory usage trends
2. Check for unclosed connections
3. Review caching implementation
4. Consider connection pooling

This comprehensive deployment guide ensures a secure, reliable, and monitored production deployment of the Velro authentication system.