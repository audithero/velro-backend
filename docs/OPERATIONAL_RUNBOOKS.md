# Operational Runbooks and Monitoring Guide

## Overview

This document provides comprehensive operational procedures for monitoring, alerting, incident response, and day-to-day maintenance of the Velro authentication system in production.

## Table of Contents

1. [Monitoring Strategy](#monitoring-strategy)
2. [Alert Configuration](#alert-configuration)
3. [Incident Response Procedures](#incident-response-procedures)
4. [Performance Monitoring](#performance-monitoring)
5. [Security Monitoring](#security-monitoring)
6. [Database Monitoring](#database-monitoring)
7. [Log Management](#log-management)
8. [Capacity Planning](#capacity-planning)
9. [Maintenance Procedures](#maintenance-procedures)
10. [Emergency Procedures](#emergency-procedures)

## Monitoring Strategy

### 1. Multi-Layer Monitoring Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Monitoring Layers                       │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Infrastructure (Railway, Network, Hardware)       │
│ Layer 2: Application (Health, Performance, Errors)         │
│ Layer 3: Business Logic (Auth Success, User Activity)      │
│ Layer 4: Security (Failed Logins, Suspicious Activity)     │
│ Layer 5: User Experience (Response Times, Availability)    │
└─────────────────────────────────────────────────────────────┘
```

### 2. Key Performance Indicators (KPIs)

#### System Health KPIs
- **Uptime**: Target 99.9% (8.76 hours downtime/year)
- **Response Time**: P95 < 500ms, P99 < 1000ms
- **Error Rate**: < 0.1% for 2xx responses
- **Throughput**: Requests per second capacity

#### Authentication KPIs
- **Login Success Rate**: > 98%
- **Registration Success Rate**: > 95%
- **Token Validation Success Rate**: > 99.9%
- **Average Authentication Time**: < 200ms

#### Security KPIs
- **Failed Login Rate**: < 2%
- **Suspicious Activity Alerts**: < 10/day
- **Rate Limit Violations**: < 50/day
- **Security Incident Count**: 0 critical/month

## Alert Configuration

### 1. Critical Alerts (Immediate Response Required)

#### System Down Alerts
```yaml
# Health Check Failure
alert: HealthCheckDown
description: "Health endpoint not responding"
condition: health_check_status != 200
severity: critical
notification: immediate
escalation: 5 minutes
runbook: #health-check-failure-runbook
```

#### Database Connection Alerts
```yaml
alert: DatabaseConnectionFailure
description: "Cannot connect to Supabase"
condition: database_connection_errors > 0
severity: critical
notification: immediate
escalation: 3 minutes
runbook: #database-connection-failure-runbook
```

#### High Error Rate Alerts
```yaml
alert: HighErrorRate
description: "Error rate exceeding threshold"
condition: error_rate > 5% for 2 minutes
severity: critical
notification: immediate
escalation: 5 minutes
runbook: #high-error-rate-runbook
```

### 2. Warning Alerts (Response within 30 minutes)

#### Performance Degradation
```yaml
alert: SlowResponseTimes
description: "Response times degrading"
condition: p95_response_time > 1000ms for 5 minutes
severity: warning
notification: 30 minutes
runbook: #performance-degradation-runbook
```

#### High Memory Usage
```yaml
alert: HighMemoryUsage
description: "Memory usage exceeding 80%"
condition: memory_usage > 80% for 10 minutes
severity: warning
notification: 30 minutes
runbook: #memory-usage-runbook
```

#### Rate Limit Violations
```yaml
alert: HighRateLimitViolations
description: "Unusual rate limit violations"
condition: rate_limit_violations > 100/hour
severity: warning
notification: 30 minutes
runbook: #rate-limit-violations-runbook
```

### 3. Info Alerts (Response within 4 hours)

#### Security Events
```yaml
alert: SuspiciousLoginActivity
description: "Unusual login patterns detected"
condition: failed_logins > 50/hour from same IP
severity: info
notification: 4 hours
runbook: #suspicious-activity-runbook
```

## Incident Response Procedures

### 1. Incident Classification

#### Severity Levels
| Level | Description | Response Time | Examples |
|-------|-------------|---------------|----------|
| P0 - Critical | Complete service outage | 15 minutes | Health check down, database offline |
| P1 - High | Major functionality impaired | 1 hour | Login failures, high error rates |
| P2 - Medium | Minor functionality impaired | 4 hours | Slow response times, API degradation |
| P3 - Low | Informational or planned | 24 hours | Security events, maintenance alerts |

### 2. Incident Response Workflow

#### Step 1: Detection and Alert
```bash
# Automated alert triggers
# Example: Health check failure
ALERT: [CRITICAL] Health Check Down
Time: 2025-08-03 22:30:00 UTC
Service: velro-backend
Status: DOWN
Response: HTTP 503
```

#### Step 2: Initial Response (Within 5 minutes)
1. **Acknowledge Alert**: Confirm receipt and start timer
2. **Initial Assessment**: Check Railway dashboard and logs
3. **Communicate Status**: Update status page and internal channels
4. **Activate Runbook**: Follow specific incident runbook

#### Step 3: Investigation and Diagnosis
```python
# Incident investigation checklist
INVESTIGATION_CHECKLIST = [
    "Check Railway service status",
    "Review application logs (last 1 hour)",
    "Verify database connectivity",
    "Check external service dependencies",
    "Review recent deployments",
    "Analyze performance metrics",
    "Check security events"
]
```

#### Step 4: Resolution and Recovery
1. **Implement Fix**: Apply appropriate resolution
2. **Verify Resolution**: Confirm service restoration
3. **Monitor Stability**: Watch for 30 minutes post-resolution
4. **Document Actions**: Record all steps taken

#### Step 5: Post-Incident Review
1. **Timeline Creation**: Document incident timeline
2. **Root Cause Analysis**: Identify underlying cause
3. **Action Items**: Create improvement tasks
4. **Runbook Updates**: Update procedures based on learnings

## Performance Monitoring

### 1. Application Performance Monitoring (APM)

#### Key Metrics to Monitor
```python
# Performance monitoring configuration
PERFORMANCE_METRICS = {
    "response_time_percentiles": [50, 75, 90, 95, 99],
    "error_rates": {
        "4xx_errors": "client_errors_per_minute",
        "5xx_errors": "server_errors_per_minute",
        "total_errors": "total_errors_per_minute"
    },
    "throughput": {
        "requests_per_second": "rps",
        "concurrent_users": "active_sessions"
    },
    "resource_utilization": {
        "cpu_usage": "cpu_percent",
        "memory_usage": "memory_percent",
        "disk_usage": "disk_percent"
    }
}
```

#### Performance Thresholds
```yaml
# Performance SLA thresholds
thresholds:
  response_time:
    p50: 100ms    # 50% of requests
    p95: 500ms    # 95% of requests
    p99: 1000ms   # 99% of requests
  
  availability:
    target: 99.9%
    measurement_window: 30 days
  
  error_rate:
    warning: 1%
    critical: 5%
    measurement_window: 5 minutes
  
  throughput:
    baseline: 100 rps
    capacity: 1000 rps
```

### 2. Database Performance Monitoring

#### Database Metrics
```sql
-- Query performance monitoring
SELECT 
  query,
  calls,
  total_time,
  mean_time,
  rows
FROM pg_stat_statements 
WHERE calls > 100 
ORDER BY total_time DESC 
LIMIT 10;

-- Connection monitoring
SELECT 
  state,
  count(*) as connection_count
FROM pg_stat_activity 
GROUP BY state;

-- Lock monitoring
SELECT 
  blocked_locks.pid AS blocked_pid,
  blocked_activity.usename AS blocked_user,
  blocking_locks.pid AS blocking_pid,
  blocking_activity.usename AS blocking_user,
  blocked_activity.query AS blocked_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

## Security Monitoring

### 1. Authentication Security Monitoring

#### Failed Login Monitoring
```python
# Security monitoring configuration
SECURITY_MONITORS = {
    "failed_login_threshold": {
        "per_ip": 10,           # 10 failed attempts per IP per hour
        "per_user": 5,          # 5 failed attempts per user per hour
        "global": 100           # 100 failed attempts globally per hour
    },
    "rate_limit_violations": {
        "threshold": 50,        # 50 violations per hour
        "action": "alert_and_block"
    },
    "suspicious_patterns": {
        "new_user_rapid_login": 5,      # 5 new users from same IP/hour
        "geographic_anomaly": True,      # Login from unusual location
        "time_anomaly": True            # Login at unusual time
    }
}
```

#### Security Event Logging
```python
# Security event logger
import logging
from datetime import datetime, timezone

security_logger = logging.getLogger('security')

class SecurityEventLogger:
    """Log security events for monitoring and analysis."""
    
    @staticmethod
    def log_failed_login(email: str, ip_address: str, reason: str):
        """Log failed login attempt."""
        security_logger.warning(f"FAILED_LOGIN: email={email}, ip={ip_address}, reason={reason}")
    
    @staticmethod
    def log_successful_login(user_id: str, ip_address: str):
        """Log successful login."""
        security_logger.info(f"SUCCESSFUL_LOGIN: user_id={user_id}, ip={ip_address}")
    
    @staticmethod
    def log_rate_limit_violation(ip_address: str, endpoint: str):
        """Log rate limit violation."""
        security_logger.warning(f"RATE_LIMIT_VIOLATION: ip={ip_address}, endpoint={endpoint}")
    
    @staticmethod
    def log_suspicious_activity(event_type: str, details: dict):
        """Log suspicious activity."""
        security_logger.error(f"SUSPICIOUS_ACTIVITY: type={event_type}, details={details}")
```

### 2. Security Alert Automation

#### Automated Response Rules
```python
# Automated security responses
SECURITY_AUTOMATION_RULES = {
    "ip_blocking": {
        "trigger": "failed_logins > 20 in 1 hour",
        "action": "block_ip_for_24_hours",
        "notification": "security_team"
    },
    "user_account_lockout": {
        "trigger": "failed_logins > 5 for user in 1 hour",
        "action": "lock_account_for_1_hour",
        "notification": "user_and_security_team"
    },
    "geographic_anomaly": {
        "trigger": "login_from_new_country",
        "action": "require_2fa_verification",
        "notification": "user_via_email"
    }
}
```

## Database Monitoring

### 1. Supabase Monitoring

#### Connection Pool Monitoring
```python
# Database connection monitoring
async def monitor_database_health():
    """Monitor database connection health."""
    
    try:
        db_client = SupabaseClient()
        
        # Test basic connectivity
        health_check = db_client.service_client.table('users').select('count').execute()
        
        metrics = {
            "connection_status": "healthy" if health_check else "unhealthy",
            "response_time": measure_query_time(),
            "active_connections": get_active_connections(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Log metrics
        logging.getLogger('database').info(f"DB_HEALTH: {metrics}")
        
        return metrics
        
    except Exception as e:
        logging.getLogger('database').error(f"DB_HEALTH_ERROR: {str(e)}")
        return {"connection_status": "error", "error": str(e)}

def measure_query_time():
    """Measure database query response time."""
    import time
    start_time = time.time()
    
    try:
        db_client = SupabaseClient()
        db_client.service_client.table('users').select('count').execute()
        return time.time() - start_time
    except:
        return -1

def get_active_connections():
    """Get count of active database connections."""
    try:
        db_client = SupabaseClient()
        result = db_client.service_client.postgrest.query(
            "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
        ).execute()
        return result.data[0]['count'] if result.data else 0
    except:
        return -1
```

### 2. Database Performance Alerts

#### Slow Query Detection
```sql
-- Create view for slow queries
CREATE OR REPLACE VIEW slow_queries AS
SELECT 
  query,
  calls,
  total_time,
  mean_time,
  (total_time / calls) as avg_time_ms
FROM pg_stat_statements 
WHERE mean_time > 1000  -- Queries taking more than 1 second
ORDER BY mean_time DESC;

-- Alert on slow queries
SELECT count(*) as slow_query_count 
FROM slow_queries 
WHERE avg_time_ms > 5000;  -- Alert if queries > 5 seconds
```

## Log Management

### 1. Structured Logging Configuration

#### Log Format Standardization
```python
# Structured logging configuration
import logging
import json
from datetime import datetime, timezone

class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logs."""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
        if hasattr(record, 'ip_address'):
            log_entry['ip_address'] = record.ip_address
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

# Configure structured logging
def setup_structured_logging():
    """Setup structured logging for production."""
    
    formatter = StructuredFormatter()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers
    loggers = ['uvicorn', 'fastapi', 'auth', 'security', 'database']
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
```

### 2. Log Analysis and Alerting

#### Log-Based Alerts
```python
# Log pattern monitoring
LOG_ALERT_PATTERNS = {
    "authentication_failures": {
        "pattern": "FAILED_LOGIN",
        "threshold": 50,
        "window": "1 hour",
        "action": "alert_security_team"
    },
    "server_errors": {
        "pattern": "ERROR",
        "threshold": 10,
        "window": "5 minutes",
        "action": "alert_dev_team"
    },
    "database_errors": {
        "pattern": "DB_HEALTH_ERROR",
        "threshold": 1,
        "window": "1 minute",
        "action": "alert_ops_team"
    }
}
```

## Capacity Planning

### 1. Resource Usage Monitoring

#### Railway Resource Monitoring
```python
# Resource usage monitoring
async def monitor_resource_usage():
    """Monitor application resource usage."""
    
    import psutil
    
    metrics = {
        "cpu": {
            "usage_percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
            "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
        },
        "memory": {
            "usage_percent": psutil.virtual_memory().percent,
            "available_gb": psutil.virtual_memory().available / (1024**3),
            "total_gb": psutil.virtual_memory().total / (1024**3)
        },
        "disk": {
            "usage_percent": psutil.disk_usage('/').percent,
            "free_gb": psutil.disk_usage('/').free / (1024**3),
            "total_gb": psutil.disk_usage('/').total / (1024**3)
        },
        "network": {
            "connections": len(psutil.net_connections()),
            "bytes_sent": psutil.net_io_counters().bytes_sent,
            "bytes_recv": psutil.net_io_counters().bytes_recv
        }
    }
    
    logging.getLogger('monitoring').info(f"RESOURCE_USAGE: {json.dumps(metrics)}")
    return metrics
```

### 2. Scaling Triggers

#### Auto-scaling Configuration
```yaml
# Scaling triggers (Railway auto-scaling)
scaling_config:
  cpu_threshold: 70%        # Scale up when CPU > 70%
  memory_threshold: 80%     # Scale up when memory > 80%
  response_time_threshold: 1000ms  # Scale up when P95 > 1s
  
  scale_up_policy:
    instances: +1
    cooldown: 300s          # 5 minutes between scale-ups
  
  scale_down_policy:
    instances: -1
    cooldown: 600s          # 10 minutes between scale-downs
    min_instances: 1
```

## Maintenance Procedures

### 1. Routine Maintenance Tasks

#### Daily Tasks
```bash
#!/bin/bash
# daily_maintenance.sh

# Check system health
echo "Checking system health..."
curl -f https://velro-backend-production.up.railway.app/health || echo "Health check failed"

# Review error logs
echo "Checking error logs..."
railway logs --since 24h | grep -i error | wc -l

# Check resource usage
echo "Checking resource usage..."
python scripts/monitor_resources.py

# Validate security
echo "Running security checks..."
python scripts/security_audit.py

# Check database performance
echo "Checking database performance..."
python scripts/db_health_check.py
```

#### Weekly Tasks
```python
# weekly_maintenance.py
import asyncio
from datetime import datetime, timedelta

async def weekly_maintenance():
    """Run weekly maintenance tasks."""
    
    tasks = [
        "Clean up expired JWT tokens from blacklist",
        "Analyze performance trends",
        "Review security logs for patterns",
        "Update dependency security scan",
        "Backup configuration settings",
        "Test disaster recovery procedures",
        "Review and update documentation"
    ]
    
    for task in tasks:
        print(f"Executing: {task}")
        # Implement specific task logic
        await asyncio.sleep(1)  # Placeholder
        
    print("Weekly maintenance completed")

if __name__ == "__main__":
    asyncio.run(weekly_maintenance())
```

### 2. Planned Maintenance Windows

#### Maintenance Window Schedule
```yaml
# Maintenance windows
regular_maintenance:
  schedule: "Weekly, Sunday 02:00-04:00 UTC"
  duration: 2 hours
  activities:
    - Security updates
    - Dependency updates
    - Performance optimization
    - Log cleanup

emergency_maintenance:
  trigger: "Critical security patches"
  max_duration: 30 minutes
  notification: "24 hours advance notice"
```

## Emergency Procedures

### 1. Service Outage Response

#### Complete Outage Runbook
```markdown
# RUNBOOK: Complete Service Outage

## Immediate Actions (0-5 minutes)
1. [ ] Acknowledge alert and start incident timer
2. [ ] Check Railway service status
3. [ ] Attempt basic service restart: `railway redeploy`
4. [ ] Update status page with outage notification
5. [ ] Notify incident response team

## Investigation Phase (5-15 minutes)
1. [ ] Check Railway deployment logs
2. [ ] Verify database connectivity
3. [ ] Check external service dependencies (Supabase, FAL.ai)
4. [ ] Review recent deployments and changes
5. [ ] Analyze error patterns in logs

## Resolution Phase (15-30 minutes)
1. [ ] If deployment issue: Rollback to last known good version
2. [ ] If database issue: Contact Supabase support
3. [ ] If resource issue: Scale up Railway service
4. [ ] If external dependency: Activate fallback procedures
5. [ ] Monitor service restoration

## Recovery Phase (30-60 minutes)
1. [ ] Verify full service functionality
2. [ ] Monitor error rates and performance
3. [ ] Update status page with resolution
4. [ ] Document incident timeline
5. [ ] Schedule post-incident review
```

### 2. Security Incident Response

#### Security Breach Runbook
```markdown
# RUNBOOK: Security Incident Response

## Immediate Containment (0-15 minutes)
1. [ ] Isolate affected systems
2. [ ] Revoke compromised credentials
3. [ ] Enable emergency security mode: `EMERGENCY_AUTH_MODE=true`
4. [ ] Block suspicious IP addresses
5. [ ] Notify security team and management

## Investigation Phase (15-60 minutes)
1. [ ] Preserve evidence (logs, system state)
2. [ ] Identify attack vector and scope
3. [ ] Assess data exposure risk
4. [ ] Contact external security experts if needed
5. [ ] Document all findings

## Recovery Phase (1-4 hours)
1. [ ] Patch security vulnerabilities
2. [ ] Reset all user passwords if needed
3. [ ] Update security configurations
4. [ ] Deploy security fixes
5. [ ] Monitor for continued threats

## Post-Incident Phase (24-48 hours)
1. [ ] Conduct thorough security audit
2. [ ] Notify affected users if required
3. [ ] Update security procedures
4. [ ] Implement additional monitoring
5. [ ] Schedule security review meeting
```

### 3. Data Recovery Procedures

#### Database Recovery Runbook
```markdown
# RUNBOOK: Database Recovery

## Data Loss Assessment (0-10 minutes)
1. [ ] Identify scope of data loss
2. [ ] Check Supabase backup status
3. [ ] Determine recovery point objective (RPO)
4. [ ] Notify stakeholders of data issue

## Recovery Execution (10-60 minutes)
1. [ ] Contact Supabase support for point-in-time recovery
2. [ ] If manual backup available: Restore from backup
3. [ ] Verify data integrity post-recovery
4. [ ] Test application functionality
5. [ ] Update users on recovery status

## Validation Phase (60-120 minutes)
1. [ ] Run data integrity checks
2. [ ] Verify user authentication works
3. [ ] Test critical user journeys
4. [ ] Monitor for any remaining issues
5. [ ] Document recovery process
```

## Monitoring Tools and Scripts

### 1. Health Check Script
```python
#!/usr/bin/env python3
# health_monitor.py
import asyncio
import httpx
import json
from datetime import datetime, timezone

async def comprehensive_health_check():
    """Run comprehensive health check."""
    
    base_url = "https://velro-backend-production.up.railway.app"
    results = {}
    
    # System health
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/health", timeout=10.0)
            results['system_health'] = {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'response_time': response.elapsed.total_seconds(),
                'data': response.json() if response.status_code == 200 else None
            }
    except Exception as e:
        results['system_health'] = {'status': 'error', 'error': str(e)}
    
    # Authentication health
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/api/v1/auth/security-info")
            results['auth_health'] = {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'response_time': response.elapsed.total_seconds()
            }
    except Exception as e:
        results['auth_health'] = {'status': 'error', 'error': str(e)}
    
    # Overall status
    all_healthy = all(
        result.get('status') == 'healthy' 
        for result in results.values()
    )
    
    results['overall'] = {
        'status': 'healthy' if all_healthy else 'unhealthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'summary': f"{sum(1 for r in results.values() if r.get('status') == 'healthy')}/{len(results)} services healthy"
    }
    
    print(json.dumps(results, indent=2))
    return all_healthy

if __name__ == "__main__":
    success = asyncio.run(comprehensive_health_check())
    exit(0 if success else 1)
```

This comprehensive operational runbook provides all necessary procedures for monitoring, alerting, incident response, and maintenance of the Velro authentication system in production.