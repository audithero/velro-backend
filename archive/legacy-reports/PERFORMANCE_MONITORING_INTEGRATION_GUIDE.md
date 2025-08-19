# Performance Monitoring System - Integration Guide

This guide provides comprehensive instructions for integrating and using the performance monitoring system that tracks PRD compliance and provides real-time performance insights.

## Overview

The performance monitoring system provides:
- Real-time tracking of authentication (<50ms target) and authorization (<75ms target)
- Multi-layer cache monitoring (L1, L2, L3 with >95% hit rate targets)
- Database query performance tracking
- Concurrent user impact analysis
- PRD compliance grading (A-F scale)
- Actionable performance recommendations
- Alert system for performance violations

## Quick Start

### 1. Add Middleware to FastAPI Application

```python
# In main.py or your FastAPI app initialization
from middleware.performance_tracking_middleware import PerformanceTrackingMiddleware
from monitoring.performance_tracker import get_performance_tracker

app = FastAPI()

# Add performance tracking middleware
app.add_middleware(PerformanceTrackingMiddleware)

# Initialize performance tracker
@app.on_event("startup")
async def startup_event():
    from middleware.performance_tracking_middleware import start_performance_tracking
    await start_performance_tracking()

@app.on_event("shutdown") 
async def shutdown_event():
    from middleware.performance_tracking_middleware import stop_performance_tracking
    await stop_performance_tracking()
```

### 2. Include Performance Router

```python
# Add performance monitoring endpoints
from routers.performance import performance_router
app.include_router(performance_router)
```

### 3. Start Monitoring

Once integrated, the system automatically tracks all API requests. No additional code changes needed for basic monitoring.

## API Endpoints

### Core Monitoring Endpoints

#### GET /api/v1/performance/metrics
Real-time performance metrics with PRD compliance tracking.

**Response:**
```json
{
  "timestamp": "2025-01-10T12:00:00Z",
  "concurrent_users": 150,
  "overall_grade": "B",
  "prd_compliance": {
    "authentication": 95.2,
    "authorization": 87.3,
    "cache_l1": 96.8,
    "database_query": 91.5
  },
  "metrics_by_type": {
    "authentication": {
      "current_stats": {
        "count": 1250,
        "mean": 42.1,
        "p95": 68.2,
        "grade": "A",
        "target_compliance": 95.2
      }
    }
  }
}
```

#### GET /api/v1/performance/health
System health check with performance assessment.

**Response:**
```json
{
  "overall_status": "healthy",
  "component_health": {
    "authentication": {
      "status": "healthy",
      "grade": "A",
      "target_compliance": 95.2
    },
    "authorization": {
      "status": "warning", 
      "grade": "C",
      "target_compliance": 78.5
    }
  },
  "active_alerts": [
    {
      "level": "warning",
      "message": "Authorization averaging 82.3ms (target: <75ms)",
      "duration_seconds": 180
    }
  ]
}
```

#### GET /api/v1/performance/report
Comprehensive performance analysis report.

**Response includes:**
- Executive summary with overall grade
- PRD compliance analysis
- Performance trends
- Concurrent user impact analysis
- Actionable recommendations
- Alert history and patterns

#### GET /api/v1/performance/prd-compliance
PRD target compliance status.

**Response:**
```json
{
  "overall_compliance_status": "good",
  "overall_grade": "B",
  "average_compliance_percentage": 87.2,
  "target_compliance": {
    "authentication": 95.2,
    "authorization": 78.5,
    "cache_l1": 96.8,
    "cache_l2": 94.1,
    "cache_l3": 92.7,
    "database_query": 88.9
  },
  "prd_targets": {
    "authentication_ms": 50,
    "authorization_ms": 75,
    "cache_hit_rate_percent": 95,
    "database_query_ms": 25
  }
}
```

## Manual Performance Tracking

### Track Authentication Operations

```python
from monitoring.performance_tracker import track_authentication

# Using context manager
async def validate_jwt_token(token: str):
    with track_authentication("jwt_validation", user_id="user123"):
        # Your authentication logic here
        result = await verify_token(token)
        return result

# Using decorator
from monitoring.performance_tracker import monitor_performance, MetricType

@monitor_performance(MetricType.AUTHENTICATION, "user_login")
async def login_user(credentials):
    # Login logic
    return user_data
```

### Track Authorization Operations  

```python
from monitoring.performance_tracker import track_authorization

async def check_user_permissions(user_id: str, resource: str):
    with track_authorization("permission_check", user_id=user_id):
        # Authorization logic here
        permissions = await get_user_permissions(user_id, resource)
        return permissions
```

### Track Database Queries

```python
from middleware.performance_tracking_middleware import track_database_performance

@track_database_performance(query="user_lookup", table="users", operation="SELECT")
async def get_user_by_id(user_id: str):
    # Database query logic
    return user_data

# Using context manager
from middleware.performance_tracking_middleware import track_db_query

async def update_user_credits(user_id: str, credits: int):
    async with track_db_query("UPDATE users SET credits = ? WHERE id = ?", 
                              table="users", operation="UPDATE"):
        await db.execute(query, (credits, user_id))
```

### Track Cache Operations

```python
from middleware.performance_tracking_middleware import track_cache_performance

@track_cache_performance(cache_level="L1", operation="get")
def get_from_l1_cache(key: str):
    return cache.get(key)

# Using context manager  
from middleware.performance_tracking_middleware import track_cache_op

def cache_user_permissions(user_id: str):
    with track_cache_op("L2", "set", key=f"permissions:{user_id}") as tracker:
        permissions = generate_permissions(user_id)
        cache.set(f"permissions:{user_id}", permissions, ttl=300)
        tracker.set_hit(True)  # Indicate successful cache operation
        return permissions
```

## Integration with Existing Systems

### Database Integration

```python
# Example with SQLAlchemy/Supabase
from middleware.performance_tracking_middleware import db_performance_middleware

class DatabaseManager:
    async def execute_query(self, query: str, params=None):
        start_time = time.perf_counter()
        try:
            result = await self.connection.execute(query, params)
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Track performance
            await db_performance_middleware.track_query(
                query=query,
                duration_ms=duration_ms,
                success=True
            )
            
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await db_performance_middleware.track_query(
                query=query,
                duration_ms=duration_ms,
                success=False
            )
            raise
```

### Cache Integration

```python
# Example with Redis cache
from middleware.performance_tracking_middleware import cache_performance_middleware

class CacheManager:
    def get(self, key: str, cache_level: str = "L1"):
        start_time = time.perf_counter()
        try:
            result = self.redis_client.get(key)
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Track cache performance
            cache_performance_middleware.track_cache_operation(
                cache_level=cache_level,
                operation="get",
                duration_ms=duration_ms,
                hit=result is not None,
                key=key,
                success=True
            )
            
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            cache_performance_middleware.track_cache_operation(
                cache_level=cache_level,
                operation="get", 
                duration_ms=duration_ms,
                success=False
            )
            raise
```

## Performance Alerts

### Setting Up Alert Callbacks

```python
from monitoring.performance_tracker import get_performance_tracker

def performance_alert_handler(alert):
    """Handle performance alerts."""
    if alert.level.value == 'critical':
        # Send critical alert notification
        send_slack_notification(f"CRITICAL: {alert.message}")
        send_email_alert(alert)
    elif alert.level.value == 'warning':
        # Log warning alert
        logger.warning(f"Performance warning: {alert.message}")

# Register callback
tracker = get_performance_tracker()
tracker.add_alert_callback(performance_alert_handler)
```

### Alert Types

The system generates alerts for:
- **Critical (2x target violations)**: Response times >2x PRD targets
- **Warning (1.5x target violations)**: Response times >1.5x PRD targets
- **Cache performance**: Hit rates below thresholds
- **System resources**: High CPU/memory usage
- **Database performance**: Slow query detection

## Monitoring Dashboard Setup

### Custom Performance Dashboard

```python
from monitoring.performance_tracker import get_performance_tracker

async def get_custom_dashboard():
    tracker = get_performance_tracker()
    
    # Get current metrics
    metrics = tracker.get_current_metrics()
    
    # Get system health
    health = tracker.get_system_health()
    
    # Get detailed report
    report = tracker.get_detailed_report()
    
    # Combine into custom dashboard
    dashboard = {
        'overview': {
            'grade': metrics.get('overall_grade'),
            'status': health.get('overall_status'),
            'compliance': metrics.get('prd_compliance')
        },
        'alerts': health.get('active_alerts', []),
        'recommendations': report.get('recommendations', [])[:5]  # Top 5
    }
    
    return dashboard
```

## Performance Optimization Workflow

### 1. Monitor Current Performance
```bash
curl http://localhost:8000/api/v1/performance/metrics
```

### 2. Check PRD Compliance
```bash
curl http://localhost:8000/api/v1/performance/prd-compliance
```

### 3. Get Recommendations
```bash
curl http://localhost:8000/api/v1/performance/report | jq '.recommendations'
```

### 4. Implement Fixes and Validate
```bash
# After implementing fixes, validate improvements
curl http://localhost:8000/api/v1/performance/trends
```

## Performance Targets (PRD)

| Component | Target | Warning | Critical | Grade A | Grade B |
|-----------|--------|---------|----------|---------|---------|
| Authentication | <50ms | >75ms | >100ms | <30ms | <40ms |
| Authorization | <75ms | >112.5ms | >150ms | <50ms | <60ms |
| Cache L1 Hit Rate | >95% | <90% | <85% | >98% | >96% |
| Cache L2 Hit Rate | >95% | <90% | <85% | >97% | >95% |
| Cache L3 Hit Rate | >95% | <90% | <85% | >96% | >94% |
| Database Queries | <25ms | >37.5ms | >50ms | <15ms | <20ms |
| API Response | <100ms | >150ms | >200ms | <60ms | <80ms |

## Troubleshooting

### Performance Tracker Not Available
If you see "Performance tracking system not available":
1. Ensure `monitoring/performance_tracker.py` is properly imported
2. Check for import errors in the performance tracker module
3. Verify middleware is properly registered

### Missing Metrics
If metrics aren't being recorded:
1. Check that the performance tracking middleware is added to FastAPI
2. Verify manual tracking code is using correct metric types
3. Check application logs for tracking errors

### High Alert Volume
If receiving too many alerts:
1. Adjust target thresholds in PRD configuration
2. Implement alert suppression for known issues
3. Focus on critical alerts first

## Best Practices

### 1. Gradual Rollout
- Start with basic endpoint monitoring
- Add manual tracking to critical paths
- Implement cache and database tracking last

### 2. Alert Management
- Set up proper alert channels (Slack, email)
- Implement alert escalation for critical issues
- Regular review of alert patterns

### 3. Performance Culture
- Regular review of performance reports
- Share performance grades with team
- Set performance improvement goals

### 4. Monitoring Overhead
- The monitoring system adds <1ms overhead per request
- Disable detailed tracking in high-load scenarios if needed
- Monitor the monitoring system's own performance

## Examples

See the `/tests/` directory for comprehensive examples of:
- Authentication performance testing
- Authorization load testing  
- Cache performance validation
- Database query optimization validation
- Integration testing with performance tracking

This monitoring system provides the foundation for maintaining and improving performance to meet PRD targets consistently.