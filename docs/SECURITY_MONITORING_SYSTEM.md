# Velro Security Monitoring and Audit Logging System

## Overview

The Velro Security Monitoring and Audit Logging System is a comprehensive, enterprise-grade security solution that provides real-time threat detection, incident response automation, and comprehensive audit logging for compliance and security analysis.

## Architecture

### Core Components

1. **Security Monitoring System** (`security/security_monitoring_system.py`)
   - Real-time threat detection and pattern matching
   - Behavioral analysis and anomaly detection
   - Automated incident creation and management
   - Geographic IP analysis and threat intelligence

2. **Enhanced Audit System** (`security/audit_system_enhanced.py`)
   - Comprehensive audit logging with compliance support
   - Multi-backend storage (SQLite, file-based)
   - Automated compliance reporting (GDPR, SOC2, ISO27001)
   - Risk scoring and retention management

3. **Security Monitoring Middleware** (`middleware/security_monitoring.py`)
   - Request-level security analysis integration
   - Real-time blocking of malicious requests
   - Seamless integration with existing middleware stack

4. **Security Dashboard** (`routers/security_dashboard.py`)
   - Real-time security metrics and analytics
   - Incident management interface
   - Compliance reporting endpoints
   - Administrative controls

5. **Integration Layer** (`security/security_integration.py`)
   - FastAPI application integration
   - Lifecycle management (startup/shutdown)
   - Helper functions for existing systems

## Features

### Real-Time Security Event Detection

- **SQL Injection Detection**: Advanced pattern matching for SQL injection attempts
- **Cross-Site Scripting (XSS) Detection**: Comprehensive XSS pattern recognition
- **Path Traversal Detection**: Directory traversal attempt identification
- **Command Injection Detection**: System command injection pattern matching
- **Suspicious User Agent Detection**: Automated scanning tool identification
- **Brute Force Detection**: Failed authentication attempt correlation
- **Rate Limiting Violations**: Automated abuse detection
- **CSRF Token Validation**: Cross-site request forgery protection
- **JWT Token Security**: Token manipulation and validation monitoring

### Comprehensive Audit Logging

- **Authentication Events**: Login attempts, session management, password changes
- **Authorization Events**: Access control decisions, privilege escalation attempts
- **Data Access Events**: CRUD operations, sensitive data access, bulk exports
- **Administrative Actions**: User management, system configuration changes
- **API Access Patterns**: Endpoint usage, parameter validation, response analysis
- **Security Events**: All security violations, blocked requests, incidents

### Behavioral Analysis

- **User Behavior Monitoring**: Login patterns, geographic analysis, device fingerprinting
- **Anomaly Detection**: Unusual access patterns, off-hours activity, suspicious locations
- **Session Analysis**: Concurrent sessions, session hijacking detection
- **Request Pattern Analysis**: Automated vs. human behavior detection

### Incident Management

- **Automated Incident Creation**: Correlation of related security events
- **Severity Classification**: Risk-based incident prioritization
- **Escalation Workflows**: Automated escalation based on severity and impact
- **Response Automation**: Auto-blocking, notifications, containment actions
- **Investigation Support**: Timeline analysis, evidence collection, forensics

### Compliance Reporting

- **GDPR Compliance**: Data processing activities, consent tracking, breach reporting
- **SOC 2 Compliance**: Security controls, availability monitoring, integrity verification
- **ISO 27001 Compliance**: Information security management, risk assessment
- **PCI DSS Compliance**: Payment processing security, cardholder data protection
- **Custom Compliance**: Configurable compliance standards and reporting

## Installation and Setup

### Prerequisites

```bash
pip install geoip2 redis sqlalchemy aiosqlite prometheus-client
```

### Basic Setup

```python
from fastapi import FastAPI
from security.security_integration import setup_security_monitoring

app = FastAPI()

# Setup security monitoring with dashboard
security_manager = setup_security_monitoring(app, enable_dashboard=True)
```

### Configuration

Create configuration file at `/opt/velro/config/security_monitoring.json`:

```json
{
  "environment": "production",
  "monitoring": {
    "enabled": true,
    "real_time_blocking": true,
    "incident_escalation": true,
    "patterns": {
      "enable_sql_injection_detection": true,
      "enable_xss_detection": true,
      "enable_path_traversal_detection": true,
      "enable_command_injection_detection": true
    },
    "thresholds": {
      "auto_block_threshold": 5,
      "incident_creation_threshold": 3,
      "high_risk_score_threshold": 70
    }
  },
  "audit": {
    "enabled": true,
    "storage_type": "sqlite",
    "retention_days": 2555,
    "compliance_standards": ["gdpr", "soc2", "iso27001"]
  },
  "redis": {
    "url": "redis://localhost:6379"
  },
  "geoip": {
    "database_path": "/opt/geoip/GeoLite2-City.mmdb"
  },
  "logging": {
    "directory": "/var/log/velro",
    "level": "INFO"
  }
}
```

### Deployment

Use the deployment script for production setup:

```bash
python scripts/deploy_security_monitoring.py --environment production
```

## API Reference

### Security Dashboard Endpoints

#### Get Security Metrics Summary
```http
GET /api/v1/security/metrics/summary
```

Response:
```json
{
  "total_events_24h": 1247,
  "critical_events_24h": 3,
  "active_incidents": 2,
  "blocked_ips_count": 15,
  "threat_level": "medium",
  "security_score": 0.89,
  "last_updated": "2024-01-15T10:30:00Z"
}
```

#### Get Security Events
```http
GET /api/v1/security/events?limit=50&severity=3&hours=24
```

Response:
```json
[
  {
    "event_id": "EVT-1234567890-ABC123",
    "event_type": "sql_injection_attempt",
    "severity": 3,
    "timestamp": "2024-01-15T10:25:00Z",
    "source_ip": "192.168.1.100",
    "user_id": "user123",
    "endpoint": "/api/users",
    "description": "SQL injection pattern detected",
    "blocked": true,
    "geo_location": {
      "country": "United States",
      "city": "New York"
    }
  }
]
```

#### Get Security Incidents
```http
GET /api/v1/security/incidents?status=new&severity=2
```

#### Create Security Alert
```http
POST /api/v1/security/alerts
```

Request Body:
```json
{
  "event_type": "brute_force_attempt",
  "severity": 3,
  "description": "Multiple failed login attempts detected",
  "metadata": {
    "attempts": 10,
    "timeframe": "5 minutes"
  }
}
```

#### Generate Compliance Report
```http
GET /api/v1/security/compliance-report?report_type=security_summary&days=30
```

## Integration Examples

### Authentication Event Logging

```python
from security.security_integration import log_authentication_event

@router.post("/auth/login")
async def login(request: Request, credentials: UserCredentials):
    try:
        user = await authenticate_user(credentials)
        await log_authentication_event(
            user_id=user.id,
            action="login",
            success=True,
            request=request
        )
        return {"token": create_jwt_token(user)}
    except AuthenticationError as e:
        await log_authentication_event(
            user_id=credentials.email,
            action="login",
            success=False,
            request=request,
            failure_reason=str(e)
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
```

### Data Access Logging

```python
from security.security_integration import log_data_access_event

@router.get("/api/users/{user_id}")
async def get_user(user_id: str, request: Request, current_user: User = Depends(get_current_user)):
    user = await get_user_by_id(user_id)
    
    await log_data_access_event(
        user_id=current_user.id,
        resource="user_profile",
        action="read_user_data",
        request=request,
        resource_id=user_id
    )
    
    return user
```

### Administrative Action Logging

```python
from security.security_integration import log_admin_action

@router.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str, request: Request, admin_user: User = Depends(get_admin_user)):
    await delete_user_by_id(user_id)
    
    await log_admin_action(
        admin_user_id=admin_user.id,
        action="delete_user",
        target="user_account",
        request=request,
        target_id=user_id,
        metadata={"reason": "account_violation"}
    )
    
    return {"message": "User deleted successfully"}
```

## Monitoring and Alerting

### Prometheus Metrics

The system exposes comprehensive metrics for monitoring:

- `velro_security_events_total` - Total security events by type and severity
- `velro_auth_failures_total` - Authentication failures by reason
- `velro_blocked_requests_total` - Blocked requests by rule type
- `velro_incidents_total` - Security incidents by severity and status
- `velro_audit_events_total` - Audit events by category

### Grafana Dashboard

The system includes pre-configured Grafana dashboards:

- **Security Overview**: Real-time security metrics and threat levels
- **Incident Management**: Active incidents, escalation status, response times
- **Compliance Monitoring**: Audit event tracking, compliance scores
- **User Behavior**: Authentication patterns, anomaly detection
- **System Health**: Performance metrics, error rates, availability

### Alerting Rules

Example alerting rules for Prometheus/Alertmanager:

```yaml
groups:
  - name: velro-security
    rules:
      - alert: HighSecurityEventRate
        expr: rate(velro_security_events_total[5m]) > 10
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: High security event rate detected
          
      - alert: CriticalSecurityIncident
        expr: increase(velro_incidents_total{severity="critical"}[1h]) > 0
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: Critical security incident created
          
      - alert: AuthenticationFailureSpike
        expr: rate(velro_auth_failures_total[5m]) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Authentication failure rate spike
```

## Performance Considerations

### Scaling

- **Event Processing**: Asynchronous event processing with configurable intervals
- **Storage Optimization**: SQLite with proper indexing, automatic cleanup
- **Redis Caching**: Fast IP blocking lookups, session tracking
- **Geographic Analysis**: Cached GeoIP lookups to reduce database calls

### Resource Usage

- **Memory**: Typical usage 50-100MB for active monitoring
- **CPU**: Pattern matching optimized with compiled regex patterns
- **Storage**: Audit logs with configurable retention (7-year default)
- **Network**: Minimal overhead, async processing

## Security Considerations

### Data Protection

- **PII Handling**: Automatic detection and masking of sensitive data
- **Encryption**: All audit logs encrypted at rest
- **Access Controls**: Role-based access to security dashboard
- **Data Retention**: Automated cleanup based on compliance requirements

### System Security

- **Input Validation**: All security system inputs validated and sanitized
- **SQL Injection Protection**: Parameterized queries for all database operations
- **Authentication**: Secure authentication required for all admin functions
- **Audit Trail Integrity**: Cryptographic hashing of audit records

## Troubleshooting

### Common Issues

1. **Redis Connection Errors**
   ```bash
   # Check Redis service
   systemctl status redis
   
   # Test connection
   redis-cli ping
   ```

2. **GeoIP Database Missing**
   ```bash
   # Download and install GeoLite2 database
   wget "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=YOUR_KEY&suffix=tar.gz"
   ```

3. **High Memory Usage**
   ```python
   # Adjust queue sizes in configuration
   security_monitor.event_queue = deque(maxlen=5000)  # Reduce from 10000
   ```

4. **Performance Issues**
   ```python
   # Disable expensive features in high-load scenarios
   config["patterns"]["enable_behavioral_analysis"] = False
   ```

### Debugging

Enable debug logging:

```python
import logging
logging.getLogger('velro.security').setLevel(logging.DEBUG)
```

Check system health:

```bash
curl -X GET "http://localhost:8000/api/v1/security/health"
```

## Compliance and Legal

### Data Retention

- **Security Events**: 7 years (configurable)
- **Audit Logs**: Based on compliance requirements (2-7 years)
- **Personal Data**: GDPR-compliant retention and deletion
- **Incident Records**: Permanent retention for critical incidents

### Privacy Protection

- **Data Minimization**: Only necessary data collected and stored
- **Consent Management**: Integration with consent management systems
- **Right to Erasure**: Automated data deletion upon request
- **Data Portability**: Audit log export in standard formats

### Regulatory Compliance

- **GDPR**: Article 32 security measures, breach notification
- **SOC 2**: Type II controls for security, availability, confidentiality
- **ISO 27001**: Information security management system
- **PCI DSS**: Payment card industry data security standards
- **HIPAA**: Healthcare information privacy and security (if applicable)

## Support and Maintenance

### Updates and Patches

- **Security Updates**: Regular updates for threat detection patterns
- **Dependency Updates**: Automated security vulnerability scanning
- **Configuration Updates**: Version-controlled configuration management

### Backup and Recovery

- **Audit Log Backup**: Daily backup of audit databases
- **Configuration Backup**: Version-controlled configuration files
- **Incident Data**: Replicated across multiple storage locations

### Support Contacts

For security monitoring system support:
- **Security Team**: security@velro.com
- **Emergency**: security-emergency@velro.com
- **Documentation**: docs.velro.com/security

---

*This document is part of the Velro Security Documentation Suite. Last updated: January 2024*