"""
OWASP Security Audit Validator
Comprehensive security incident logging and validation system for OWASP compliance.

This module provides:
- Security incident logging with severity classification
- OWASP compliance validation
- Security metrics tracking
- Threat detection and alerting
"""

import logging
import hashlib
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from enum import Enum
from uuid import UUID

from utils.cache_manager import CacheManager
from config import settings

logger = logging.getLogger(__name__)

class SecurityIncidentType(Enum):
    """Security incident classification."""
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    ACCESS_DENIED = "access_denied"
    PRIVILEGE_ESCALATION_ATTEMPT = "privilege_escalation_attempt"
    BRUTE_FORCE_ATTACK = "brute_force_attack"
    INJECTION_ATTEMPT = "injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    CSRF_ATTEMPT = "csrf_attempt"
    SECURITY_SCANNER_DETECTED = "security_scanner_detected"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    MALICIOUS_PATTERN_DETECTED = "malicious_pattern_detected"
    INSECURE_DESIGN_VIOLATION = "insecure_design_violation"
    SSRF_ATTEMPT = "ssrf_attempt"
    FILE_UPLOAD_VIOLATION = "file_upload_violation"
    DATA_INTEGRITY_VIOLATION = "data_integrity_violation"
    CRYPTOGRAPHIC_FAILURE = "cryptographic_failure"
    COMPONENT_VULNERABILITY = "component_vulnerability"
    LOGGING_FAILURE = "logging_failure"

class SecuritySeverity(Enum):
    """Security incident severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class SecurityAuditValidator:
    """
    Comprehensive security audit validator for OWASP compliance.
    
    Features:
    - Security incident logging with retention
    - OWASP Top 10 compliance tracking
    - Real-time threat detection
    - Security metrics and reporting
    - Automated alerting for critical incidents
    """
    
    def __init__(self):
        self.cache_manager = CacheManager()
        
        # Security incident classification rules
        self.severity_rules = {
            # Critical incidents - immediate response required
            SecurityIncidentType.PRIVILEGE_ESCALATION_ATTEMPT: SecuritySeverity.CRITICAL,
            SecurityIncidentType.INJECTION_ATTEMPT: SecuritySeverity.CRITICAL,
            SecurityIncidentType.CRYPTOGRAPHIC_FAILURE: SecuritySeverity.CRITICAL,
            SecurityIncidentType.AUTHENTICATION_FAILURE: SecuritySeverity.HIGH,
            
            # High severity incidents
            SecurityIncidentType.AUTHORIZATION_FAILURE: SecuritySeverity.HIGH,
            SecurityIncidentType.BRUTE_FORCE_ATTACK: SecuritySeverity.HIGH,
            SecurityIncidentType.XSS_ATTEMPT: SecuritySeverity.HIGH,
            SecurityIncidentType.CSRF_ATTEMPT: SecuritySeverity.HIGH,
            SecurityIncidentType.SECURITY_SCANNER_DETECTED: SecuritySeverity.HIGH,
            SecurityIncidentType.SSRF_ATTEMPT: SecuritySeverity.HIGH,
            SecurityIncidentType.FILE_UPLOAD_VIOLATION: SecuritySeverity.HIGH,
            
            # Medium severity incidents
            SecurityIncidentType.ACCESS_DENIED: SecuritySeverity.MEDIUM,
            SecurityIncidentType.RATE_LIMIT_EXCEEDED: SecuritySeverity.MEDIUM,
            SecurityIncidentType.MALICIOUS_PATTERN_DETECTED: SecuritySeverity.MEDIUM,
            SecurityIncidentType.INSECURE_DESIGN_VIOLATION: SecuritySeverity.MEDIUM,
            SecurityIncidentType.DATA_INTEGRITY_VIOLATION: SecuritySeverity.MEDIUM,
            
            # Low severity incidents
            SecurityIncidentType.COMPONENT_VULNERABILITY: SecuritySeverity.LOW,
            SecurityIncidentType.LOGGING_FAILURE: SecuritySeverity.LOW,
        }
        
        # OWASP compliance tracking
        self.owasp_categories = {
            "A01_BROKEN_ACCESS_CONTROL": [
                SecurityIncidentType.AUTHORIZATION_FAILURE,
                SecurityIncidentType.PRIVILEGE_ESCALATION_ATTEMPT,
                SecurityIncidentType.ACCESS_DENIED
            ],
            "A02_CRYPTOGRAPHIC_FAILURES": [
                SecurityIncidentType.CRYPTOGRAPHIC_FAILURE
            ],
            "A03_INJECTION": [
                SecurityIncidentType.INJECTION_ATTEMPT
            ],
            "A04_INSECURE_DESIGN": [
                SecurityIncidentType.INSECURE_DESIGN_VIOLATION,
                SecurityIncidentType.RATE_LIMIT_EXCEEDED
            ],
            "A05_SECURITY_MISCONFIGURATION": [
                SecurityIncidentType.SECURITY_SCANNER_DETECTED,
                SecurityIncidentType.MALICIOUS_PATTERN_DETECTED
            ],
            "A06_VULNERABLE_COMPONENTS": [
                SecurityIncidentType.COMPONENT_VULNERABILITY
            ],
            "A07_IDENTIFICATION_AUTHENTICATION_FAILURES": [
                SecurityIncidentType.AUTHENTICATION_FAILURE,
                SecurityIncidentType.BRUTE_FORCE_ATTACK
            ],
            "A08_SOFTWARE_DATA_INTEGRITY_FAILURES": [
                SecurityIncidentType.DATA_INTEGRITY_VIOLATION,
                SecurityIncidentType.CSRF_ATTEMPT
            ],
            "A09_SECURITY_LOGGING_MONITORING_FAILURES": [
                SecurityIncidentType.LOGGING_FAILURE
            ],
            "A10_SERVER_SIDE_REQUEST_FORGERY": [
                SecurityIncidentType.SSRF_ATTEMPT
            ]
        }
    
    async def log_security_incident(
        self,
        incident_type: str,
        severity: str,
        user_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_path: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a security incident with comprehensive context.
        
        Returns:
            incident_id: Unique identifier for the incident
        """
        try:
            # Convert string to enum if needed
            if isinstance(incident_type, str):
                try:
                    incident_type = SecurityIncidentType(incident_type.lower())
                except ValueError:
                    incident_type = SecurityIncidentType.MALICIOUS_PATTERN_DETECTED
            
            if isinstance(severity, str):
                try:
                    severity = SecuritySeverity(severity.lower())
                except ValueError:
                    severity = SecuritySeverity.MEDIUM
            
            # Generate unique incident ID
            timestamp = datetime.now(timezone.utc)
            incident_data = {
                "user_id": str(user_id) if user_id else None,
                "incident_type": incident_type.value,
                "timestamp": timestamp.isoformat(),
                "details": details or {}
            }
            
            incident_id = hashlib.sha256(
                json.dumps(incident_data, sort_keys=True).encode()
            ).hexdigest()[:16]
            
            # Create comprehensive incident record
            incident = {
                "incident_id": incident_id,
                "incident_type": incident_type.value,
                "severity": severity.value,
                "timestamp": timestamp.isoformat(),
                "user_id": str(user_id) if user_id else None,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "request_path": request_path,
                "details": details or {},
                "additional_context": additional_context or {},
                "owasp_category": self._get_owasp_category(incident_type),
                "remediation_required": severity in [SecuritySeverity.HIGH, SecuritySeverity.CRITICAL],
                "alert_sent": False
            }
            
            # Store incident with appropriate TTL
            ttl = self._get_incident_retention_period(severity)
            cache_key = f"security_incident:{incident_id}"
            
            await self.cache_manager.set(
                cache_key,
                incident,
                ttl=ttl
            )
            
            # Log based on severity
            log_message = (
                f"🚨 [SECURITY-{severity.value.upper()}] {incident_type.value}: "
                f"User: {user_id}, IP: {client_ip}, Path: {request_path}"
            )
            
            if severity == SecuritySeverity.CRITICAL:
                logger.critical(log_message)
                await self._send_critical_alert(incident)
            elif severity == SecuritySeverity.HIGH:
                logger.error(log_message)
                await self._send_high_priority_alert(incident)
            elif severity == SecuritySeverity.MEDIUM:
                logger.warning(log_message)
            else:
                logger.info(log_message)
            
            # Update security metrics
            await self._update_security_metrics(incident_type, severity, timestamp)
            
            # Check for attack patterns
            if client_ip:
                await self._analyze_attack_patterns(client_ip, incident_type, timestamp)
            
            logger.info(f"✅ [SECURITY-AUDIT] Incident logged: {incident_id}")
            return incident_id
            
        except Exception as e:
            logger.error(f"❌ [SECURITY-AUDIT] Failed to log security incident: {e}")
            # Fallback logging to ensure incidents are never lost
            logger.critical(
                f"🚨 [SECURITY-FALLBACK] {incident_type}: "
                f"User: {user_id}, IP: {client_ip}, Details: {details}"
            )
            return "fallback_logged"
    
    def _get_owasp_category(self, incident_type: SecurityIncidentType) -> Optional[str]:
        """Map incident type to OWASP Top 10 category."""
        for category, types in self.owasp_categories.items():
            if incident_type in types:
                return category
        return None
    
    def _get_incident_retention_period(self, severity: SecuritySeverity) -> int:
        """Get retention period in seconds based on severity."""
        retention_periods = {
            SecuritySeverity.CRITICAL: 86400 * 365,  # 1 year
            SecuritySeverity.HIGH: 86400 * 180,      # 6 months
            SecuritySeverity.MEDIUM: 86400 * 90,     # 3 months
            SecuritySeverity.LOW: 86400 * 30         # 1 month
        }
        return retention_periods.get(severity, 86400 * 30)
    
    async def _send_critical_alert(self, incident: Dict[str, Any]):
        """Send immediate alert for critical security incidents."""
        try:
            # In a real implementation, this would send alerts via:
            # - Email to security team
            # - Slack/Teams notification
            # - PagerDuty/OpsGenie alert
            # - SIEM integration
            
            logger.critical(
                f"🚨 [CRITICAL-ALERT] Security incident requires immediate attention: "
                f"{incident['incident_id']} - {incident['incident_type']}"
            )
            
            # Update incident to mark alert sent
            incident['alert_sent'] = True
            cache_key = f"security_incident:{incident['incident_id']}"
            await self.cache_manager.set(cache_key, incident)
            
        except Exception as e:
            logger.error(f"❌ [SECURITY-ALERT] Failed to send critical alert: {e}")
    
    async def _send_high_priority_alert(self, incident: Dict[str, Any]):
        """Send alert for high priority security incidents."""
        try:
            logger.error(
                f"⚠️ [HIGH-PRIORITY-ALERT] Security incident: "
                f"{incident['incident_id']} - {incident['incident_type']}"
            )
            
            # Update incident to mark alert sent
            incident['alert_sent'] = True
            cache_key = f"security_incident:{incident['incident_id']}"
            await self.cache_manager.set(cache_key, incident)
            
        except Exception as e:
            logger.error(f"❌ [SECURITY-ALERT] Failed to send high priority alert: {e}")
    
    async def _update_security_metrics(
        self, 
        incident_type: SecurityIncidentType, 
        severity: SecuritySeverity, 
        timestamp: datetime
    ):
        """Update security metrics for monitoring and reporting."""
        try:
            current_hour = timestamp.replace(minute=0, second=0, microsecond=0)
            
            # Update hourly metrics
            metrics_key = f"security_metrics:hourly:{current_hour.isoformat()}"
            metrics = await self.cache_manager.get(metrics_key) or {
                "timestamp": current_hour.isoformat(),
                "total_incidents": 0,
                "incidents_by_type": {},
                "incidents_by_severity": {},
                "owasp_categories": {}
            }
            
            # Update counters
            metrics["total_incidents"] += 1
            metrics["incidents_by_type"][incident_type.value] = \
                metrics["incidents_by_type"].get(incident_type.value, 0) + 1
            metrics["incidents_by_severity"][severity.value] = \
                metrics["incidents_by_severity"].get(severity.value, 0) + 1
            
            # Update OWASP category metrics
            owasp_category = self._get_owasp_category(incident_type)
            if owasp_category:
                metrics["owasp_categories"][owasp_category] = \
                    metrics["owasp_categories"].get(owasp_category, 0) + 1
            
            # Store metrics (24 hour TTL)
            await self.cache_manager.set(metrics_key, metrics, ttl=86400)
            
        except Exception as e:
            logger.error(f"❌ [SECURITY-METRICS] Failed to update metrics: {e}")
    
    async def _analyze_attack_patterns(
        self, 
        client_ip: str, 
        incident_type: SecurityIncidentType, 
        timestamp: datetime
    ):
        """Analyze attack patterns to detect coordinated attacks."""
        try:
            # Track incidents per IP
            ip_key = f"security_patterns:ip:{client_ip}"
            ip_incidents = await self.cache_manager.get(ip_key) or []
            
            # Add current incident
            ip_incidents.append({
                "incident_type": incident_type.value,
                "timestamp": timestamp.isoformat()
            })
            
            # Keep only last 24 hours
            cutoff = timestamp - timedelta(hours=24)
            ip_incidents = [
                incident for incident in ip_incidents
                if datetime.fromisoformat(incident["timestamp"]) > cutoff
            ]
            
            # Store updated list
            await self.cache_manager.set(ip_key, ip_incidents, ttl=86400)
            
            # Check for attack patterns
            if len(ip_incidents) >= 10:  # 10+ incidents in 24 hours
                await self.log_security_incident(
                    incident_type="malicious_pattern_detected",
                    severity="high",
                    client_ip=client_ip,
                    details={
                        "pattern_type": "high_frequency_attacks",
                        "incident_count": len(ip_incidents),
                        "time_period": "24_hours"
                    }
                )
            
        except Exception as e:
            logger.error(f"❌ [SECURITY-PATTERNS] Failed to analyze attack patterns: {e}")
    
    async def get_security_report(
        self, 
        hours: int = 24,
        include_details: bool = False
    ) -> Dict[str, Any]:
        """
        Generate security report for the specified time period.
        
        Args:
            hours: Number of hours to include in report
            include_details: Whether to include detailed incident information
        
        Returns:
            Comprehensive security report
        """
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=hours)
            
            report = {
                "report_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "hours": hours
                },
                "summary": {
                    "total_incidents": 0,
                    "critical_incidents": 0,
                    "high_priority_incidents": 0,
                    "medium_priority_incidents": 0,
                    "low_priority_incidents": 0
                },
                "owasp_compliance": {
                    "A01_broken_access_control": 0,
                    "A02_cryptographic_failures": 0,
                    "A03_injection": 0,
                    "A04_insecure_design": 0,
                    "A05_security_misconfiguration": 0,
                    "A06_vulnerable_components": 0,
                    "A07_identification_authentication_failures": 0,
                    "A08_software_data_integrity_failures": 0,
                    "A09_security_logging_monitoring_failures": 0,
                    "A10_server_side_request_forgery": 0
                },
                "top_incident_types": {},
                "top_attacking_ips": {},
                "recommendations": []
            }
            
            if include_details:
                report["detailed_incidents"] = []
            
            # Collect metrics from hourly buckets
            current_time = start_time.replace(minute=0, second=0, microsecond=0)
            while current_time <= end_time:
                metrics_key = f"security_metrics:hourly:{current_time.isoformat()}"
                metrics = await self.cache_manager.get(metrics_key)
                
                if metrics:
                    # Update summary
                    report["summary"]["total_incidents"] += metrics.get("total_incidents", 0)
                    
                    # Update by severity
                    severity_counts = metrics.get("incidents_by_severity", {})
                    for severity, count in severity_counts.items():
                        report["summary"][f"{severity}_priority_incidents"] += count
                    
                    # Update OWASP categories
                    owasp_counts = metrics.get("owasp_categories", {})
                    for category, count in owasp_counts.items():
                        category_key = category.lower()
                        if category_key in report["owasp_compliance"]:
                            report["owasp_compliance"][category_key] += count
                    
                    # Update top incident types
                    incident_types = metrics.get("incidents_by_type", {})
                    for incident_type, count in incident_types.items():
                        report["top_incident_types"][incident_type] = \
                            report["top_incident_types"].get(incident_type, 0) + count
                
                current_time += timedelta(hours=1)
            
            # Generate recommendations based on incident patterns
            report["recommendations"] = self._generate_security_recommendations(report)
            
            logger.info(f"✅ [SECURITY-REPORT] Generated report for {hours} hours")
            return report
            
        except Exception as e:
            logger.error(f"❌ [SECURITY-REPORT] Failed to generate security report: {e}")
            return {"error": f"Failed to generate report: {e}"}
    
    def _generate_security_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Generate security recommendations based on incident patterns."""
        recommendations = []
        
        # Check for high incident counts
        if report["summary"]["total_incidents"] > 100:
            recommendations.append(
                "High incident volume detected. Consider implementing additional rate limiting."
            )
        
        # Check for critical incidents
        if report["summary"]["critical_incidents"] > 0:
            recommendations.append(
                f"URGENT: {report['summary']['critical_incidents']} critical security incidents require immediate attention."
            )
        
        # Check OWASP compliance issues
        owasp_issues = []
        for category, count in report["owasp_compliance"].items():
            if count > 10:  # Threshold for concern
                owasp_issues.append(f"{category.replace('_', ' ').title()}: {count} incidents")
        
        if owasp_issues:
            recommendations.append(
                f"OWASP compliance issues detected: {'; '.join(owasp_issues)}"
            )
        
        # Check for common attack patterns
        top_types = report.get("top_incident_types", {})
        if top_types.get("injection_attempt", 0) > 5:
            recommendations.append(
                "Multiple injection attempts detected. Review input validation and parameterized queries."
            )
        
        if top_types.get("privilege_escalation_attempt", 0) > 0:
            recommendations.append(
                "Privilege escalation attempts detected. Review access control implementations."
            )
        
        if not recommendations:
            recommendations.append("Security posture appears normal for the reporting period.")
        
        return recommendations
    
    async def validate_owasp_compliance(self) -> Dict[str, Any]:
        """
        Validate current OWASP Top 10 2021 compliance status.
        
        Returns:
            Compliance status for each OWASP category
        """
        try:
            # Get security report for last 7 days
            report = await self.get_security_report(hours=24*7)
            
            compliance_status = {
                "overall_compliance_score": 0,
                "categories": {},
                "recommendations": [],
                "last_assessed": datetime.now(timezone.utc).isoformat()
            }
            
            total_score = 0
            category_count = 0
            
            # Assess each OWASP category
            for category, incident_count in report["owasp_compliance"].items():
                category_name = category.replace("_", " ").title()
                
                # Scoring logic (lower incidents = higher compliance)
                if incident_count == 0:
                    score = 100
                    status = "COMPLIANT"
                elif incident_count <= 5:
                    score = 80
                    status = "MOSTLY_COMPLIANT"
                elif incident_count <= 15:
                    score = 60
                    status = "PARTIALLY_COMPLIANT"
                else:
                    score = 30
                    status = "NON_COMPLIANT"
                
                compliance_status["categories"][category] = {
                    "name": category_name,
                    "score": score,
                    "status": status,
                    "incident_count": incident_count,
                    "assessment": self._get_category_assessment(category, incident_count)
                }
                
                total_score += score
                category_count += 1
            
            # Calculate overall compliance score
            compliance_status["overall_compliance_score"] = total_score / category_count if category_count > 0 else 0
            
            # Generate compliance recommendations
            compliance_status["recommendations"] = self._generate_compliance_recommendations(
                compliance_status["categories"]
            )
            
            logger.info(f"✅ [OWASP-COMPLIANCE] Assessment completed. Score: {compliance_status['overall_compliance_score']:.1f}/100")
            return compliance_status
            
        except Exception as e:
            logger.error(f"❌ [OWASP-COMPLIANCE] Failed to validate compliance: {e}")
            return {"error": f"Compliance validation failed: {e}"}
    
    def _get_category_assessment(self, category: str, incident_count: int) -> str:
        """Get detailed assessment for OWASP category."""
        assessments = {
            "a01_broken_access_control": {
                0: "Access control mechanisms are properly implemented and functioning correctly.",
                5: "Minor access control issues detected. Review authorization logic.",
                15: "Moderate access control violations. Immediate review required.",
                50: "Significant access control failures. Critical security risk."
            },
            "a02_cryptographic_failures": {
                0: "Cryptographic implementations are secure and up to standard.",
                5: "Minor cryptographic issues detected. Review encryption implementations.",
                15: "Cryptographic vulnerabilities present. Immediate attention required.",
                50: "Critical cryptographic failures. Data security at risk."
            },
            "a03_injection": {
                0: "Input validation and parameterized queries are properly implemented.",
                5: "Minor injection vulnerabilities detected. Review input handling.",
                15: "Multiple injection attempts successful. Critical review required.",
                50: "Severe injection vulnerabilities. Immediate remediation required."
            }
        }
        
        category_assessments = assessments.get(category, {})
        
        # Find the appropriate threshold
        for threshold in sorted(category_assessments.keys(), reverse=True):
            if incident_count >= threshold:
                return category_assessments[threshold]
        
        return "Assessment not available for this category."
    
    def _generate_compliance_recommendations(self, categories: Dict[str, Any]) -> List[str]:
        """Generate OWASP compliance recommendations."""
        recommendations = []
        
        for category_key, category_data in categories.items():
            if category_data["status"] == "NON_COMPLIANT":
                recommendations.append(
                    f"CRITICAL: {category_data['name']} - {category_data['assessment']}"
                )
            elif category_data["status"] == "PARTIALLY_COMPLIANT":
                recommendations.append(
                    f"HIGH: {category_data['name']} - Review and strengthen controls"
                )
        
        if not recommendations:
            recommendations.append("OWASP Top 10 2021 compliance is satisfactory.")
        
        return recommendations


# Global security audit validator instance
security_audit_validator = SecurityAuditValidator()