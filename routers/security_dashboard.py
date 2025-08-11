"""
Security Dashboard API Router
Provides real-time security metrics, incident management, and compliance reporting
for the comprehensive security monitoring system.
"""

import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Import security monitoring components
try:
    from security.security_monitoring_system import (
        security_monitor,
        SecurityEvent,
        SecurityEventType,
        SecuritySeverity,
        SecurityIncident,
        AlertStatus
    )
    from middleware.security_monitoring import SecurityMonitoringIntegration
    from monitoring.metrics import metrics_collector
    from middleware.auth import get_current_user  # Assuming auth middleware exists
except ImportError:
    # Fallback for testing
    security_monitor = None
    metrics_collector = None
    
    # Mock dependencies
    async def get_current_user():
        return {"user_id": "admin", "role": "admin"}


router = APIRouter(prefix="/api/v1/security", tags=["Security Dashboard"])


# Pydantic models for API responses
class SecurityMetricsSummary(BaseModel):
    """Security metrics summary response."""
    total_events_24h: int
    critical_events_24h: int
    active_incidents: int
    blocked_ips_count: int
    threat_level: str
    security_score: float
    last_updated: datetime


class SecurityEvent(BaseModel):
    """Security event response model."""
    event_id: str
    event_type: str
    severity: int
    timestamp: datetime
    source_ip: str
    user_id: Optional[str]
    endpoint: str
    description: str
    blocked: bool
    geo_location: Optional[Dict[str, str]]


class SecurityIncidentResponse(BaseModel):
    """Security incident response model."""
    incident_id: str
    title: str
    description: str
    severity: int
    status: str
    created_at: datetime
    updated_at: datetime
    events_count: int
    source_ips: List[str]
    affected_users: List[str]
    auto_blocked: bool
    escalated: bool


class SecurityAlert(BaseModel):
    """Security alert creation model."""
    event_type: str
    severity: int
    description: str
    metadata: Dict[str, Any] = {}


class IncidentUpdate(BaseModel):
    """Incident update model."""
    status: str
    notes: Optional[str] = None
    escalate: Optional[bool] = False


@router.get("/metrics/summary", response_model=SecurityMetricsSummary)
async def get_security_metrics_summary(
    current_user: dict = Depends(get_current_user)
):
    """Get real-time security metrics summary."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        # Calculate metrics from the last 24 hours
        current_time = datetime.now(timezone.utc)
        yesterday = current_time - timedelta(days=1)
        
        # Get recent events from the event queue
        recent_events = [
            event for event in list(security_monitor.event_queue)
            if event.timestamp >= yesterday
        ]
        
        # Calculate metrics
        total_events = len(recent_events)
        critical_events = len([e for e in recent_events if e.severity >= SecuritySeverity.HIGH])
        
        # Get active incidents
        active_incidents_count = len([
            incident for incident in security_monitor.incident_manager.active_incidents.values()
            if incident.status not in [AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE]
        ])
        
        # Get blocked IPs count
        blocked_ips_count = len(security_monitor.blocked_ips)
        
        # Calculate threat level
        if critical_events > 5:
            threat_level = "critical"
        elif critical_events > 2:
            threat_level = "high"
        elif total_events > 20:
            threat_level = "medium"
        else:
            threat_level = "low"
        
        # Calculate security score (0-100)
        base_score = 100
        score_deduction = min(critical_events * 10, 80)  # Max 80 point deduction
        security_score = max(base_score - score_deduction, 0) / 100
        
        return SecurityMetricsSummary(
            total_events_24h=total_events,
            critical_events_24h=critical_events,
            active_incidents=active_incidents_count,
            blocked_ips_count=blocked_ips_count,
            threat_level=threat_level,
            security_score=security_score,
            last_updated=current_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get security metrics: {str(e)}")


@router.get("/events", response_model=List[SecurityEvent])
async def get_security_events(
    limit: int = Query(50, ge=1, le=1000),
    severity: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    source_ip: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    current_user: dict = Depends(get_current_user)
):
    """Get recent security events with filtering."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        # Get events from the specified time range
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        events = [
            event for event in list(security_monitor.event_queue)
            if event.timestamp >= cutoff_time
        ]
        
        # Apply filters
        if severity:
            try:
                severity_level = SecuritySeverity(int(severity))
                events = [e for e in events if e.severity >= severity_level]
            except ValueError:
                pass
        
        if event_type:
            events = [e for e in events if e.event_type.value == event_type]
        
        if source_ip:
            events = [e for e in events if e.source_ip == source_ip]
        
        # Sort by timestamp (most recent first) and limit
        events.sort(key=lambda x: x.timestamp, reverse=True)
        events = events[:limit]
        
        # Convert to response format
        return [
            SecurityEvent(
                event_id=event.event_id,
                event_type=event.event_type.value,
                severity=event.severity.value,
                timestamp=event.timestamp,
                source_ip=event.source_ip,
                user_id=event.user_id,
                endpoint=event.endpoint,
                description=event.description,
                blocked=event.blocked,
                geo_location=event.geo_location
            )
            for event in events
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get security events: {str(e)}")


@router.get("/incidents", response_model=List[SecurityIncidentResponse])
async def get_security_incidents(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    current_user: dict = Depends(get_current_user)
):
    """Get security incidents."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        incidents = list(security_monitor.incident_manager.active_incidents.values())
        
        # Apply filters
        if status:
            try:
                status_filter = AlertStatus(status)
                incidents = [i for i in incidents if i.status == status_filter]
            except ValueError:
                pass
        
        if severity:
            try:
                severity_level = SecuritySeverity(int(severity))
                incidents = [i for i in incidents if i.severity >= severity_level]
            except ValueError:
                pass
        
        # Sort by created_at (most recent first) and limit
        incidents.sort(key=lambda x: x.created_at, reverse=True)
        incidents = incidents[:limit]
        
        # Convert to response format
        return [
            SecurityIncidentResponse(
                incident_id=incident.incident_id,
                title=incident.title,
                description=incident.description,
                severity=incident.severity.value,
                status=incident.status.value,
                created_at=incident.created_at,
                updated_at=incident.updated_at,
                events_count=len(incident.events),
                source_ips=list(incident.source_ips),
                affected_users=list(incident.affected_users),
                auto_blocked=incident.auto_blocked,
                escalated=incident.escalated
            )
            for incident in incidents
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get security incidents: {str(e)}")


@router.get("/incidents/{incident_id}")
async def get_incident_details(
    incident_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed incident information."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        incident = security_monitor.incident_manager.active_incidents.get(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        # Convert events to response format
        events = [
            {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "timestamp": event.timestamp.isoformat(),
                "source_ip": event.source_ip,
                "user_id": event.user_id,
                "endpoint": event.endpoint,
                "description": event.description,
                "metadata": event.metadata,
                "geo_location": event.geo_location
            }
            for event in incident.events
        ]
        
        return {
            "incident_id": incident.incident_id,
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "created_at": incident.created_at.isoformat(),
            "updated_at": incident.updated_at.isoformat(),
            "source_ips": list(incident.source_ips),
            "affected_users": list(incident.affected_users),
            "auto_blocked": incident.auto_blocked,
            "escalated": incident.escalated,
            "metadata": incident.metadata,
            "events": events
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get incident details: {str(e)}")


@router.put("/incidents/{incident_id}")
async def update_incident(
    incident_id: str,
    update_data: IncidentUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update incident status and details."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        incident = security_monitor.incident_manager.active_incidents.get(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        # Update incident
        try:
            incident.status = AlertStatus(update_data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        incident.updated_at = datetime.now(timezone.utc)
        
        if update_data.escalate:
            incident.escalated = True
        
        # Log admin action
        await SecurityMonitoringIntegration.log_admin_action(
            admin_user_id=current_user.get("user_id"),
            action=f"update_incident_status",
            target=incident_id,
            source_ip="admin_dashboard",  # This would be extracted from request
            metadata={
                "new_status": update_data.status,
                "notes": update_data.notes,
                "escalated": update_data.escalate
            }
        )
        
        return {"message": "Incident updated successfully", "incident_id": incident_id}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update incident: {str(e)}")


@router.post("/alerts")
async def create_security_alert(
    alert_data: SecurityAlert,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Create custom security alert."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        # Validate event type
        try:
            event_type = SecurityEventType(alert_data.event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid event type")
        
        # Validate severity
        try:
            severity = SecuritySeverity(alert_data.severity)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid severity")
        
        # Get client IP
        client_ip = request.headers.get('x-forwarded-for', request.client.host).split(',')[0].strip()
        
        # Create security alert
        await SecurityMonitoringIntegration.create_security_alert(
            event_type=event_type,
            severity=severity,
            description=alert_data.description,
            source_ip=client_ip,
            user_id=current_user.get("user_id"),
            metadata=alert_data.metadata
        )
        
        return {"message": "Security alert created successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create security alert: {str(e)}")


@router.get("/blocked-ips")
async def get_blocked_ips(
    current_user: dict = Depends(get_current_user)
):
    """Get list of blocked IP addresses."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        blocked_ips = list(security_monitor.blocked_ips)
        
        # Get additional info from Redis if available
        blocked_ip_details = []
        
        for ip in blocked_ips:
            ip_info = {"ip": ip, "blocked_at": "unknown", "reason": "unknown"}
            
            if security_monitor.redis_client:
                try:
                    redis_data = await security_monitor.redis_client.get(f"blocked_ip:{ip}")
                    if redis_data:
                        redis_info = json.loads(redis_data)
                        ip_info.update(redis_info)
                except:
                    pass
            
            blocked_ip_details.append(ip_info)
        
        return {"blocked_ips": blocked_ip_details, "total_count": len(blocked_ips)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get blocked IPs: {str(e)}")


@router.delete("/blocked-ips/{ip_address}")
async def unblock_ip(
    ip_address: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Unblock an IP address."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        if ip_address not in security_monitor.blocked_ips:
            raise HTTPException(status_code=404, detail="IP address not found in blocked list")
        
        # Remove from blocked IPs
        security_monitor.blocked_ips.discard(ip_address)
        
        # Remove from Redis
        if security_monitor.redis_client:
            try:
                await security_monitor.redis_client.delete(f"blocked_ip:{ip_address}")
            except:
                pass
        
        # Log admin action
        await SecurityMonitoringIntegration.log_admin_action(
            admin_user_id=current_user.get("user_id"),
            action="unblock_ip",
            target=ip_address,
            source_ip=request.headers.get('x-forwarded-for', request.client.host).split(',')[0].strip(),
            metadata={"unblocked_ip": ip_address}
        )
        
        return {"message": f"IP address {ip_address} unblocked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unblock IP: {str(e)}")


@router.get("/audit-trail")
async def get_audit_trail(
    category: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_user)
):
    """Get audit trail entries."""
    # This would typically read from audit log files or database
    # For now, return a placeholder response
    return {
        "message": "Audit trail functionality requires log file parsing implementation",
        "parameters": {
            "category": category,
            "user_id": user_id,
            "hours": hours,
            "limit": limit
        },
        "note": "This endpoint would parse structured audit logs and return entries"
    }


@router.get("/compliance-report")
async def get_compliance_report(
    report_type: str = Query("security_summary"),
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user)
):
    """Generate security compliance report."""
    if not security_monitor:
        raise HTTPException(status_code=503, detail="Security monitoring not available")
    
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Get events from the specified time range
        events = [
            event for event in list(security_monitor.event_queue)
            if event.timestamp >= cutoff_time
        ]
        
        # Generate report based on type
        if report_type == "security_summary":
            report = {
                "report_type": "Security Summary",
                "period": f"Last {days} days",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_events": len(events),
                "events_by_severity": {
                    "low": len([e for e in events if e.severity == SecuritySeverity.LOW]),
                    "medium": len([e for e in events if e.severity == SecuritySeverity.MEDIUM]),
                    "high": len([e for e in events if e.severity == SecuritySeverity.HIGH]),
                    "critical": len([e for e in events if e.severity == SecuritySeverity.CRITICAL])
                },
                "events_by_type": {},
                "top_source_ips": {},
                "security_score": 0,
                "recommendations": []
            }
            
            # Count events by type
            for event in events:
                event_type = event.event_type.value
                if event_type not in report["events_by_type"]:
                    report["events_by_type"][event_type] = 0
                report["events_by_type"][event_type] += 1
            
            # Count events by source IP
            ip_counts = {}
            for event in events:
                if event.source_ip not in ip_counts:
                    ip_counts[event.source_ip] = 0
                ip_counts[event.source_ip] += 1
            
            # Get top 10 source IPs
            sorted_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            report["top_source_ips"] = dict(sorted_ips)
            
            # Calculate security score
            critical_count = report["events_by_severity"]["critical"]
            high_count = report["events_by_severity"]["high"]
            total_events = len(events)
            
            if total_events > 0:
                threat_ratio = (critical_count * 2 + high_count) / total_events
                report["security_score"] = max(100 - (threat_ratio * 100), 0)
            else:
                report["security_score"] = 100
            
            # Generate recommendations
            if critical_count > 0:
                report["recommendations"].append(
                    f"Address {critical_count} critical security events immediately"
                )
            
            if high_count > 5:
                report["recommendations"].append(
                    f"Review and mitigate {high_count} high-severity security events"
                )
            
            if len(security_monitor.blocked_ips) > 10:
                report["recommendations"].append(
                    f"Review {len(security_monitor.blocked_ips)} blocked IPs for potential threats"
                )
            
            return report
        
        else:
            return {"error": "Unsupported report type", "supported_types": ["security_summary"]}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate compliance report: {str(e)}")


@router.get("/health")
async def get_security_monitoring_health():
    """Get security monitoring system health status."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "security_monitor": security_monitor is not None,
            "metrics_collector": metrics_collector is not None,
            "pattern_matcher": False,
            "geoip_analyzer": False,
            "behavior_analyzer": False,
            "incident_manager": False,
            "audit_logger": False
        }
    }
    
    if security_monitor:
        health_status["components"]["pattern_matcher"] = hasattr(security_monitor, 'pattern_matcher')
        health_status["components"]["geoip_analyzer"] = hasattr(security_monitor, 'geoip_analyzer')
        health_status["components"]["behavior_analyzer"] = hasattr(security_monitor, 'behavior_analyzer')
        health_status["components"]["incident_manager"] = hasattr(security_monitor, 'incident_manager')
        health_status["components"]["audit_logger"] = hasattr(security_monitor, 'audit_logger')
        
        # Check if background tasks are running
        if hasattr(security_monitor, '_monitoring_tasks'):
            health_status["background_tasks"] = len(security_monitor._monitoring_tasks)
        
        # Get queue sizes
        health_status["queue_status"] = {
            "event_queue_size": len(security_monitor.event_queue),
            "incident_queue_size": len(security_monitor.incident_queue) if hasattr(security_monitor, 'incident_queue') else 0,
            "blocked_ips_count": len(security_monitor.blocked_ips)
        }
    
    # Determine overall health
    component_health = list(health_status["components"].values())
    if all(component_health):
        health_status["status"] = "healthy"
    elif any(component_health):
        health_status["status"] = "degraded"
    else:
        health_status["status"] = "unhealthy"
    
    return health_status


# WebSocket endpoint for real-time security events (optional)
@router.websocket("/events/stream")
async def security_events_websocket(websocket):
    """WebSocket endpoint for real-time security event streaming."""
    # This would be implemented for real-time dashboard updates
    await websocket.accept()
    await websocket.send_text(json.dumps({
        "type": "connection_established",
        "message": "Real-time security event streaming not yet implemented"
    }))
    await websocket.close()