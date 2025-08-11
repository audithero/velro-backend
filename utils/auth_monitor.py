"""
Production Authentication Monitoring and Security System
Real-time auth monitoring, threat detection, and security audit logging.
Enterprise-grade security monitoring with comprehensive alerting.
"""
import os
import logging
import json
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict, deque
import hashlib
import re

from utils.cache_manager import get_cache_manager, CacheLevel
from config import settings

logger = logging.getLogger(__name__)

class SecurityThreatLevel(Enum):
    """Security threat levels for monitoring."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high" 
    CRITICAL = "critical"

class AuthEventType(Enum):
    """Authentication event types for monitoring."""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    REGISTRATION = "registration"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_EXPIRED = "token_expired"
    LOGOUT = "logout"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_CONFIRM = "password_reset_confirm"
    PROFILE_UPDATE = "profile_update"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    SECURITY_VIOLATION = "security_violation"

@dataclass
class AuthEvent:
    """Authentication event data structure."""
    event_type: AuthEventType
    user_id: Optional[str]
    email: Optional[str]
    ip_address: str
    user_agent: str
    timestamp: datetime
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    threat_level: SecurityThreatLevel = SecurityThreatLevel.LOW
    geographic_location: Optional[str] = None
    device_fingerprint: Optional[str] = None

@dataclass
class SecurityIncident:
    """Security incident data structure."""
    incident_id: str
    threat_level: SecurityThreatLevel
    incident_type: str
    description: str
    affected_user_id: Optional[str]
    ip_address: str
    timestamp: datetime
    evidence: Dict[str, Any]
    resolved: bool = False
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None

class AuthSecurityMonitor:
    """Real-time authentication security monitoring system."""
    
    def __init__(self):
        self.cache_manager = get_cache_manager()
        self.failed_attempts = defaultdict(list)  # IP -> list of timestamps
        self.user_sessions = defaultdict(list)  # user_id -> list of session info
        self.suspicious_ips = set()
        self.blocked_ips = set()
        self.security_incidents = []
        
        # Configuration
        self.max_failed_attempts = 5
        self.rate_limit_window = 300  # 5 minutes
        self.max_concurrent_sessions = 5
        self.geographic_anomaly_threshold = 1000  # km
        
    async def log_auth_event(self, event: AuthEvent):
        """Log authentication event and perform real-time analysis."""
        try:
            # Store event in cache for analysis
            event_key = f"auth_event:{event.timestamp.timestamp()}:{hashlib.md5(f'{event.ip_address}{event.user_id}'.encode()).hexdigest()[:8]}"
            await self.cache_manager.set(
                event_key,
                asdict(event),
                CacheLevel.L2_PERSISTENT,
                ttl=86400 * 30  # Keep for 30 days
            )
            
            # Perform real-time threat analysis
            await self._analyze_event_for_threats(event)
            
            # Update monitoring metrics
            await self._update_monitoring_metrics(event)
            
            # Log for external monitoring systems
            self._log_to_external_systems(event)
            
            logger.info(f"🔍 [AUTH-MONITOR] Event logged: {event.event_type.value} for {event.email or 'unknown'}")
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to log auth event: {e}")
    
    async def _analyze_event_for_threats(self, event: AuthEvent):
        """Analyze authentication event for security threats."""
        threats_detected = []
        
        # 1. Brute Force Detection
        if event.event_type == AuthEventType.LOGIN_FAILED:
            threats_detected.extend(await self._detect_brute_force(event))
        
        # 2. Geographic Anomaly Detection
        if event.user_id and event.event_type in [AuthEventType.LOGIN_SUCCESS, AuthEventType.LOGIN_FAILED]:
            threats_detected.extend(await self._detect_geographic_anomaly(event))
        
        # 3. Device Fingerprint Analysis
        if event.device_fingerprint:
            threats_detected.extend(await self._analyze_device_fingerprint(event))
        
        # 4. User Agent Analysis
        threats_detected.extend(await self._analyze_user_agent(event))
        
        # 5. Time-based Pattern Analysis
        threats_detected.extend(await self._analyze_temporal_patterns(event))
        
        # 6. IP Reputation Check
        threats_detected.extend(await self._check_ip_reputation(event))
        
        # Create security incidents for threats
        for threat in threats_detected:
            await self._create_security_incident(threat, event)
    
    async def _detect_brute_force(self, event: AuthEvent) -> List[Dict[str, Any]]:
        """Detect brute force attacks."""
        threats = []
        
        try:
            # Track failed attempts by IP
            ip_key = f"failed_attempts:{event.ip_address}"
            attempts = await self.cache_manager.get(ip_key, CacheLevel.L1_MEMORY) or []
            
            # Add current attempt
            attempts.append(event.timestamp.isoformat())
            
            # Clean old attempts (outside time window)
            cutoff_time = event.timestamp - timedelta(seconds=self.rate_limit_window)
            attempts = [ts for ts in attempts if datetime.fromisoformat(ts) > cutoff_time]
            
            # Store updated attempts
            await self.cache_manager.set(
                ip_key,
                attempts,
                CacheLevel.L1_MEMORY,
                ttl=self.rate_limit_window
            )
            
            # Check for brute force
            if len(attempts) >= self.max_failed_attempts:
                threat_level = SecurityThreatLevel.HIGH if len(attempts) >= 10 else SecurityThreatLevel.MEDIUM
                
                threats.append({
                    'type': 'brute_force_attack',
                    'threat_level': threat_level,
                    'description': f'Multiple failed login attempts from IP {event.ip_address}',
                    'evidence': {
                        'failed_attempts': len(attempts),
                        'time_window': self.rate_limit_window,
                        'attempts_list': attempts
                    }
                })
                
                # Auto-block IP if critical threshold reached
                if len(attempts) >= 15:
                    await self._block_ip(event.ip_address, "Automated block: Brute force attack")
                    
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Brute force detection failed: {e}")
        
        return threats
    
    async def _detect_geographic_anomaly(self, event: AuthEvent) -> List[Dict[str, Any]]:
        """Detect geographic anomalies in user login patterns."""
        threats = []
        
        try:
            if not event.user_id or not event.geographic_location:
                return threats
            
            # Get user's recent locations
            location_key = f"user_locations:{event.user_id}"
            recent_locations = await self.cache_manager.get(location_key, CacheLevel.L2_PERSISTENT) or []
            
            # Simple geographic anomaly detection (in production, use proper geolocation service)
            if recent_locations:
                # Check if current location is significantly different from recent ones
                # This is a simplified check - in production, use proper geographic distance calculation
                current_location = event.geographic_location
                
                for recent_location in recent_locations[-5:]:  # Check last 5 locations
                    if recent_location != current_location:
                        # In production, calculate actual distance
                        threats.append({
                            'type': 'geographic_anomaly',
                            'threat_level': SecurityThreatLevel.MEDIUM,
                            'description': f'Login from unusual geographic location for user {event.user_id}',
                            'evidence': {
                                'current_location': current_location,
                                'recent_locations': recent_locations[-5:],
                                'user_id': event.user_id
                            }
                        })
                        break
            
            # Update user locations
            recent_locations.append({
                'location': event.geographic_location,
                'timestamp': event.timestamp.isoformat(),
                'ip_address': event.ip_address
            })
            
            # Keep last 10 locations
            if len(recent_locations) > 10:
                recent_locations = recent_locations[-10:]
            
            await self.cache_manager.set(
                location_key,
                recent_locations,
                CacheLevel.L2_PERSISTENT,
                ttl=86400 * 30  # Keep for 30 days
            )
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Geographic anomaly detection failed: {e}")
        
        return threats
    
    async def _analyze_device_fingerprint(self, event: AuthEvent) -> List[Dict[str, Any]]:
        """Analyze device fingerprints for suspicious activity."""
        threats = []
        
        try:
            if not event.user_id or not event.device_fingerprint:
                return threats
            
            # Track user devices
            devices_key = f"user_devices:{event.user_id}"
            known_devices = await self.cache_manager.get(devices_key, CacheLevel.L2_PERSISTENT) or []
            
            # Check if device is known
            device_known = any(
                device['fingerprint'] == event.device_fingerprint 
                for device in known_devices
            )
            
            if not device_known:
                # New device detected
                threats.append({
                    'type': 'new_device_login',
                    'threat_level': SecurityThreatLevel.LOW,
                    'description': f'Login from new device for user {event.user_id}',
                    'evidence': {
                        'device_fingerprint': event.device_fingerprint,
                        'user_id': event.user_id,
                        'known_devices_count': len(known_devices)
                    }
                })
                
                # Add device to known devices
                known_devices.append({
                    'fingerprint': event.device_fingerprint,
                    'first_seen': event.timestamp.isoformat(),
                    'user_agent': event.user_agent,
                    'ip_address': event.ip_address
                })
                
                # Keep last 20 devices
                if len(known_devices) > 20:
                    known_devices = known_devices[-20:]
                
                await self.cache_manager.set(
                    devices_key,
                    known_devices,
                    CacheLevel.L2_PERSISTENT,
                    ttl=86400 * 60  # Keep for 60 days
                )
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Device fingerprint analysis failed: {e}")
        
        return threats
    
    async def _analyze_user_agent(self, event: AuthEvent) -> List[Dict[str, Any]]:
        """Analyze user agent for suspicious patterns."""
        threats = []
        
        try:
            user_agent = event.user_agent.lower()
            
            # Check for suspicious user agents
            suspicious_patterns = [
                r'bot',
                r'crawler',
                r'spider',
                r'scraper',
                r'curl',
                r'wget',
                r'python',
                r'automation',
                r'headless'
            ]
            
            for pattern in suspicious_patterns:
                if re.search(pattern, user_agent):
                    threats.append({
                        'type': 'suspicious_user_agent',
                        'threat_level': SecurityThreatLevel.MEDIUM,
                        'description': f'Suspicious user agent detected: {pattern}',
                        'evidence': {
                            'user_agent': event.user_agent,
                            'pattern_matched': pattern,
                            'ip_address': event.ip_address
                        }
                    })
                    break
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] User agent analysis failed: {e}")
        
        return threats
    
    async def _analyze_temporal_patterns(self, event: AuthEvent) -> List[Dict[str, Any]]:
        """Analyze temporal patterns for anomalies."""
        threats = []
        
        try:
            if not event.user_id:
                return threats
            
            # Get user's typical activity hours
            activity_key = f"user_activity_hours:{event.user_id}"
            activity_hours = await self.cache_manager.get(activity_key, CacheLevel.L2_PERSISTENT) or []
            
            current_hour = event.timestamp.hour
            
            # Check if login is at unusual hour
            if activity_hours and len(activity_hours) >= 10:  # Need some history
                hour_counts = defaultdict(int)
                for hour in activity_hours:
                    hour_counts[hour] += 1
                
                # If current hour is very rare (less than 5% of activity)
                total_activities = len(activity_hours)
                current_hour_percentage = hour_counts[current_hour] / total_activities
                
                if current_hour_percentage < 0.05:
                    threats.append({
                        'type': 'unusual_time_activity',
                        'threat_level': SecurityThreatLevel.LOW,
                        'description': f'Login at unusual hour for user {event.user_id}',
                        'evidence': {
                            'current_hour': current_hour,
                            'hour_percentage': current_hour_percentage,
                            'typical_hours': dict(hour_counts)
                        }
                    })
            
            # Update activity hours
            activity_hours.append(current_hour)
            
            # Keep last 100 activity hours
            if len(activity_hours) > 100:
                activity_hours = activity_hours[-100:]
            
            await self.cache_manager.set(
                activity_key,
                activity_hours,
                CacheLevel.L2_PERSISTENT,
                ttl=86400 * 30  # Keep for 30 days
            )
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Temporal pattern analysis failed: {e}")
        
        return threats
    
    async def _check_ip_reputation(self, event: AuthEvent) -> List[Dict[str, Any]]:
        """Check IP reputation against known threat databases."""
        threats = []
        
        try:
            # Simple IP reputation check (in production, integrate with threat intelligence feeds)
            ip_reputation_key = f"ip_reputation:{event.ip_address}"
            reputation_data = await self.cache_manager.get(ip_reputation_key, CacheLevel.L2_PERSISTENT)
            
            if not reputation_data:
                # In production, query threat intelligence APIs
                # For now, implement basic checks
                
                # Check for private/local IPs (usually safe)
                if self._is_private_ip(event.ip_address):
                    reputation_data = {'status': 'safe', 'reason': 'private_ip'}
                else:
                    # In production, integrate with services like VirusTotal, AbuseIPDB, etc.
                    reputation_data = {'status': 'unknown', 'reason': 'no_data'}
                
                # Cache reputation for 1 hour
                await self.cache_manager.set(
                    ip_reputation_key,
                    reputation_data,
                    CacheLevel.L2_PERSISTENT,
                    ttl=3600
                )
            
            if reputation_data.get('status') == 'malicious':
                threats.append({
                    'type': 'malicious_ip',
                    'threat_level': SecurityThreatLevel.HIGH,
                    'description': f'Login attempt from known malicious IP {event.ip_address}',
                    'evidence': {
                        'ip_address': event.ip_address,
                        'reputation_data': reputation_data
                    }
                })
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] IP reputation check failed: {e}")
        
        return threats
    
    def _is_private_ip(self, ip_address: str) -> bool:
        """Check if IP address is private/local."""
        try:
            import ipaddress
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback
        except Exception:
            return False
    
    async def _create_security_incident(self, threat: Dict[str, Any], event: AuthEvent):
        """Create security incident from detected threat."""
        try:
            incident_id = hashlib.md5(
                f"{threat['type']}{event.ip_address}{event.timestamp.isoformat()}".encode()
            ).hexdigest()[:16]
            
            incident = SecurityIncident(
                incident_id=incident_id,
                threat_level=threat['threat_level'],
                incident_type=threat['type'],
                description=threat['description'],
                affected_user_id=event.user_id,
                ip_address=event.ip_address,
                timestamp=event.timestamp,
                evidence=threat['evidence']
            )
            
            # Store incident
            incident_key = f"security_incident:{incident_id}"
            await self.cache_manager.set(
                incident_key,
                asdict(incident),
                CacheLevel.L2_PERSISTENT,
                ttl=86400 * 90  # Keep for 90 days
            )
            
            # Alert if high/critical threat
            if incident.threat_level in [SecurityThreatLevel.HIGH, SecurityThreatLevel.CRITICAL]:
                await self._send_security_alert(incident)
            
            logger.warning(f"🚨 [AUTH-MONITOR] Security incident created: {incident.incident_type} ({incident.threat_level.value}) - {incident_id}")
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to create security incident: {e}")
    
    async def _send_security_alert(self, incident: SecurityIncident):
        """Send security alert for high/critical incidents."""
        try:
            alert_data = {
                'incident_id': incident.incident_id,
                'threat_level': incident.threat_level.value,
                'type': incident.incident_type,
                'description': incident.description,
                'ip_address': incident.ip_address,
                'timestamp': incident.timestamp.isoformat(),
                'affected_user': incident.affected_user_id
            }
            
            # In production, integrate with alerting systems (PagerDuty, Slack, email, etc.)
            logger.critical(f"🚨 [SECURITY-ALERT] {json.dumps(alert_data)}")
            
            # Store alert in high-priority cache
            alert_key = f"security_alert:{incident.incident_id}"
            await self.cache_manager.set(
                alert_key,
                alert_data,
                CacheLevel.L1_MEMORY,
                ttl=86400  # Keep for 24 hours
            )
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to send security alert: {e}")
    
    async def _block_ip(self, ip_address: str, reason: str):
        """Block IP address from accessing the system."""
        try:
            block_key = f"blocked_ip:{ip_address}"
            block_data = {
                'ip_address': ip_address,
                'blocked_at': datetime.now(timezone.utc).isoformat(),
                'reason': reason,
                'auto_blocked': True
            }
            
            await self.cache_manager.set(
                block_key,
                block_data,
                CacheLevel.L2_PERSISTENT,
                ttl=86400 * 7  # Block for 7 days
            )
            
            logger.critical(f"🚫 [AUTH-MONITOR] IP blocked: {ip_address} - {reason}")
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to block IP {ip_address}: {e}")
    
    async def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP address is blocked."""
        try:
            block_key = f"blocked_ip:{ip_address}"
            block_data = await self.cache_manager.get(block_key, CacheLevel.L2_PERSISTENT)
            return block_data is not None
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to check IP block status for {ip_address}: {e}")
            return False
    
    async def _update_monitoring_metrics(self, event: AuthEvent):
        """Update monitoring metrics for dashboards."""
        try:
            # Update daily metrics
            date_key = event.timestamp.date().isoformat()
            metrics_key = f"auth_metrics:{date_key}"
            
            metrics = await self.cache_manager.get(metrics_key, CacheLevel.L2_PERSISTENT) or {
                'date': date_key,
                'total_events': 0,
                'login_attempts': 0,
                'login_successes': 0,
                'login_failures': 0,
                'registrations': 0,
                'password_resets': 0,
                'unique_ips': set(),
                'unique_users': set(),
                'threat_levels': {level.value: 0 for level in SecurityThreatLevel}
            }
            
            metrics['total_events'] += 1
            
            if event.event_type == AuthEventType.LOGIN_SUCCESS:
                metrics['login_attempts'] += 1
                metrics['login_successes'] += 1
            elif event.event_type == AuthEventType.LOGIN_FAILED:
                metrics['login_attempts'] += 1
                metrics['login_failures'] += 1
            elif event.event_type == AuthEventType.REGISTRATION:
                metrics['registrations'] += 1
            elif event.event_type in [AuthEventType.PASSWORD_RESET_REQUEST, AuthEventType.PASSWORD_RESET_CONFIRM]:
                metrics['password_resets'] += 1
            
            metrics['unique_ips'].add(event.ip_address)
            if event.user_id:
                metrics['unique_users'].add(event.user_id)
            
            metrics['threat_levels'][event.threat_level.value] += 1
            
            # Convert sets to lists for JSON serialization
            metrics['unique_ips'] = list(metrics['unique_ips'])
            metrics['unique_users'] = list(metrics['unique_users'])
            
            await self.cache_manager.set(
                metrics_key,
                metrics,
                CacheLevel.L2_PERSISTENT,
                ttl=86400 * 365  # Keep for 1 year
            )
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to update monitoring metrics: {e}")
    
    def _log_to_external_systems(self, event: AuthEvent):
        """Log to external monitoring systems."""
        try:
            # Format for external systems (Splunk, ELK, etc.)
            log_entry = {
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type.value,
                'user_id': event.user_id,
                'email': event.email,
                'ip_address': event.ip_address,
                'user_agent': event.user_agent,
                'success': event.success,
                'error_message': event.error_message,
                'threat_level': event.threat_level.value,
                'geographic_location': event.geographic_location,
                'device_fingerprint': event.device_fingerprint,
                'metadata': event.metadata
            }
            
            # In production, send to external logging systems
            logger.info(f"AUTH_EVENT: {json.dumps(log_entry)}")
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to log to external systems: {e}")
    
    async def get_security_dashboard_data(self) -> Dict[str, Any]:
        """Get security dashboard data for monitoring interface."""
        try:
            # Get recent metrics (last 7 days)
            dashboard_data = {
                'summary': {
                    'total_events_24h': 0,
                    'login_success_rate_24h': 0,
                    'active_incidents': 0,
                    'blocked_ips': 0
                },
                'daily_metrics': [],
                'top_threats': [],
                'recent_incidents': [],
                'geographic_distribution': {}
            }
            
            # Calculate metrics for last 7 days
            for i in range(7):
                date = (datetime.now(timezone.utc) - timedelta(days=i)).date()
                date_key = date.isoformat()
                metrics_key = f"auth_metrics:{date_key}"
                
                daily_metrics = await self.cache_manager.get(metrics_key, CacheLevel.L2_PERSISTENT)
                if daily_metrics:
                    dashboard_data['daily_metrics'].append(daily_metrics)
                    
                    if i == 0:  # Today's data
                        dashboard_data['summary']['total_events_24h'] = daily_metrics.get('total_events', 0)
                        login_attempts = daily_metrics.get('login_attempts', 0)
                        login_successes = daily_metrics.get('login_successes', 0)
                        
                        if login_attempts > 0:
                            dashboard_data['summary']['login_success_rate_24h'] = (login_successes / login_attempts) * 100
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"❌ [AUTH-MONITOR] Failed to get dashboard data: {e}")
            return {}


# Global auth monitor instance
_auth_monitor: Optional[AuthSecurityMonitor] = None

def get_auth_monitor() -> AuthSecurityMonitor:
    """Get global auth monitor instance."""
    global _auth_monitor
    if _auth_monitor is None:
        _auth_monitor = AuthSecurityMonitor()
    return _auth_monitor