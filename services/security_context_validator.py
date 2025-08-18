"""
Security Context Validator Service
Advanced IP geo-location, user agent analysis, and behavioral pattern detection.

This service implements Layer 4 of the 10-layer authorization system:
- IP address reputation and geolocation validation
- User agent analysis and bot detection
- Behavioral pattern analysis and anomaly detection
- Geographic access control and VPN/Tor detection
- Real-time threat intelligence integration

OWASP A01 (Broken Access Control) Mitigation:
- Validates request origin and patterns
- Detects suspicious IP addresses and user agents
- Implements geographic access controls
- Tracks behavioral patterns for anomaly detection
- Provides comprehensive security context for authorization decisions
"""

import asyncio
import hashlib
import json
import logging
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from uuid import UUID
from dataclasses import dataclass, asdict
import redis
import requests
from user_agents import parse as parse_user_agent

from models.authorization import ValidationContext
from models.authorization_layers import (
    SecurityThreatLevel, AnomalyType, LayerResult, AuthorizationLayerType,
    SecurityContextData, GeolocationData, UserAgentAnalysis, BehavioralPattern,
    ThreatIndicator, ThreatAssessment, ThreatCategory
)

logger = logging.getLogger(__name__)


class SecurityContextValidator:
    """
    Advanced security context validation service.
    
    Features:
    - IP geolocation and reputation checking
    - User agent analysis and bot detection
    - Behavioral pattern analysis
    - Real-time threat intelligence
    - VPN/Tor detection
    - Adaptive risk scoring
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(decode_responses=True)
        
        # IP reputation and tracking
        self.suspicious_ips = set()
        self.known_good_ips = set()
        self.vpn_tor_ips = set()
        
        # Threat intelligence feeds (in production, use external services)
        self.threat_intel_sources = [
            'malware_ips',
            'botnet_ips', 
            'tor_exit_nodes',
            'vpn_providers'
        ]
        
        # Bot detection patterns
        self.bot_patterns = [
            r'bot', r'crawler', r'spider', r'scraper', r'curl', r'wget',
            r'python', r'requests', r'automation', r'selenium', r'headless',
            r'phantom', r'zombie', r'scanner', r'monitoring'
        ]
        
        # Suspicious user agent patterns
        self.suspicious_ua_patterns = [
            r'<script', r'javascript:', r'vbscript:', r'onload=',
            r'onerror=', r'eval\(', r'alert\(', r'document\.cookie'
        ]
        
        # Risk scoring weights
        self.risk_weights = {
            'ip_reputation': 0.3,
            'geolocation': 0.2,
            'user_agent': 0.2,
            'behavioral': 0.2,
            'threat_intel': 0.1
        }
        
        # Performance metrics
        self.validation_times = []
        self.cache_stats = {'hits': 0, 'misses': 0}
        
    async def validate_security_context(
        self, 
        context: ValidationContext, 
        security_context: SecurityContextData
    ) -> LayerResult:
        """
        Perform comprehensive security context validation.
        
        Args:
            context: Authorization validation context
            security_context: Security context data including IP, user agent, etc.
            
        Returns:
            LayerResult with validation outcome and security assessment
        """
        start_time = time.time()
        
        try:
            # Generate cache key for this validation
            cache_key = self._generate_cache_key(security_context)
            
            # Check cache first for performance optimization
            cached_result = await self._get_cached_validation(cache_key)
            if cached_result:
                cached_result.cache_hit = True
                self.cache_stats['hits'] += 1
                return cached_result
            
            self.cache_stats['misses'] += 1
            
            # Perform comprehensive security analysis
            threat_indicators = []
            risk_scores = {}
            
            # 1. IP Address Analysis
            ip_analysis = await self._analyze_ip_address(
                security_context.ip_address, 
                context.user_id
            )
            risk_scores['ip_reputation'] = ip_analysis['risk_score']
            threat_indicators.extend(ip_analysis['indicators'])
            
            # 2. Geolocation Analysis  
            geo_analysis = await self._analyze_geolocation(
                security_context.ip_address,
                context.user_id
            )
            risk_scores['geolocation'] = geo_analysis['risk_score']
            threat_indicators.extend(geo_analysis['indicators'])
            security_context.geolocation = geo_analysis['geolocation_data']
            
            # 3. User Agent Analysis
            ua_analysis = await self._analyze_user_agent(
                security_context.user_agent,
                context.user_id
            )
            risk_scores['user_agent'] = ua_analysis['risk_score']
            threat_indicators.extend(ua_analysis['indicators'])
            security_context.user_agent_analysis = ua_analysis['analysis_data']
            
            # 4. Behavioral Pattern Analysis
            behavioral_analysis = await self._analyze_behavioral_patterns(
                context.user_id,
                security_context.previous_requests,
                security_context.request_timestamp
            )
            risk_scores['behavioral'] = behavioral_analysis['risk_score']
            threat_indicators.extend(behavioral_analysis['indicators'])
            
            # 5. Threat Intelligence Check
            threat_intel = await self._check_threat_intelligence(
                security_context.ip_address,
                security_context.user_agent
            )
            risk_scores['threat_intel'] = threat_intel['risk_score']
            threat_indicators.extend(threat_intel['indicators'])
            
            # Calculate overall risk score
            overall_risk = self._calculate_overall_risk_score(risk_scores)
            security_context.risk_score = overall_risk
            
            # Determine threat level and success
            threat_level = self._determine_threat_level(overall_risk, threat_indicators)
            success = threat_level not in [SecurityThreatLevel.RED]
            
            # Apply security flags
            security_context.security_flags = self._generate_security_flags(
                risk_scores, threat_indicators
            )
            
            # Create result
            execution_time = (time.time() - start_time) * 1000
            self.validation_times.append(execution_time)
            
            result = LayerResult(
                layer_type=AuthorizationLayerType.SECURITY_CONTEXT_VALIDATION,
                success=success,
                execution_time_ms=execution_time,
                threat_level=threat_level,
                anomalies=[indicator.indicator_type for indicator in threat_indicators],
                metadata={
                    'overall_risk_score': overall_risk,
                    'individual_risk_scores': risk_scores,
                    'threat_indicators_count': len(threat_indicators),
                    'geolocation_available': security_context.geolocation is not None,
                    'behavioral_analysis_available': len(security_context.previous_requests) > 0,
                    'security_flags': security_context.security_flags,
                    'threat_categories': list(set(
                        self._categorize_threat_indicator(ind) for ind in threat_indicators
                    ))
                }
            )
            
            # Cache successful validations for performance
            if success and overall_risk < 0.5:
                await self._cache_validation_result(cache_key, result, ttl=300)
            
            # Update user behavioral patterns
            await self._update_behavioral_patterns(
                context.user_id, security_context, risk_scores
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Security context validation failed: {e}")
            return LayerResult(
                layer_type=AuthorizationLayerType.SECURITY_CONTEXT_VALIDATION,
                success=False,
                execution_time_ms=(time.time() - start_time) * 1000,
                threat_level=SecurityThreatLevel.RED,
                anomalies=[AnomalyType.SYSTEM_RESOURCE_ABUSE],
                metadata={'error': str(e), 'validation_failed': True}
            )
    
    async def _analyze_ip_address(
        self, 
        ip_address: str, 
        user_id: UUID
    ) -> Dict[str, Any]:
        """Analyze IP address reputation and patterns."""
        indicators = []
        risk_score = 0.0
        
        try:
            # Check against known suspicious IPs
            if ip_address in self.suspicious_ips:
                indicators.append(ThreatIndicator(
                    indicator_type=AnomalyType.SUSPICIOUS_IP_PATTERN,
                    severity=SecurityThreatLevel.RED,
                    confidence=0.9,
                    timestamp=datetime.utcnow(),
                    description=f"IP {ip_address} is in suspicious IP list"
                ))
                risk_score = max(risk_score, 0.9)
            
            # Check against known good IPs
            if ip_address in self.known_good_ips:
                risk_score = min(risk_score, 0.1)
            else:
                # Unknown IP gets moderate risk
                risk_score = max(risk_score, 0.3)
            
            # Check request frequency from this IP
            ip_request_key = f"ip_requests:{ip_address}"
            recent_requests = await self._count_recent_requests(ip_request_key, 3600)
            
            if recent_requests > 1000:  # More than 1000 requests per hour
                indicators.append(ThreatIndicator(
                    indicator_type=AnomalyType.REQUEST_SPIKE_DETECTED,
                    severity=SecurityThreatLevel.ORANGE,
                    confidence=0.8,
                    timestamp=datetime.utcnow(),
                    description=f"High request rate from IP: {recent_requests} requests/hour",
                    metadata={'request_count': recent_requests}
                ))
                risk_score = max(risk_score, 0.7)
                # Add to suspicious IPs for future reference
                self.suspicious_ips.add(ip_address)
            
            # Check for multiple users from same IP (potential botnet)
            ip_users_key = f"ip_users:{ip_address}"
            unique_users = await self.redis_client.scard(ip_users_key)
            if unique_users > 50:  # More than 50 different users from same IP
                indicators.append(ThreatIndicator(
                    indicator_type=AnomalyType.SUSPICIOUS_IP_PATTERN,
                    severity=SecurityThreatLevel.ORANGE,
                    confidence=0.7,
                    timestamp=datetime.utcnow(),
                    description=f"Many users from same IP: {unique_users} users",
                    metadata={'unique_users': unique_users}
                ))
                risk_score = max(risk_score, 0.6)
            
            # Track this user/IP combination
            await self.redis_client.sadd(ip_users_key, str(user_id))
            await self.redis_client.expire(ip_users_key, 86400)  # 24 hours
            
            # Check for rapid IP changes by user
            user_ips_key = f"user_ips:{user_id}"
            await self.redis_client.sadd(user_ips_key, ip_address)
            await self.redis_client.expire(user_ips_key, 3600)  # 1 hour
            
            recent_ips = await self.redis_client.scard(user_ips_key)
            if recent_ips > 10:  # More than 10 different IPs in 1 hour
                indicators.append(ThreatIndicator(
                    indicator_type=AnomalyType.SUSPICIOUS_IP_PATTERN,
                    severity=SecurityThreatLevel.YELLOW,
                    confidence=0.6,
                    timestamp=datetime.utcnow(),
                    description=f"User changing IPs rapidly: {recent_ips} IPs in 1 hour",
                    metadata={'ip_count': recent_ips}
                ))
                risk_score = max(risk_score, 0.5)
            
        except Exception as e:
            logger.warning(f"IP analysis failed: {e}")
            risk_score = 0.5  # Moderate risk on analysis failure
        
        return {
            'risk_score': risk_score,
            'indicators': indicators,
            'analysis_type': 'ip_reputation'
        }
    
    async def _analyze_geolocation(
        self, 
        ip_address: str, 
        user_id: UUID
    ) -> Dict[str, Any]:
        """Analyze geographic location patterns."""
        indicators = []
        risk_score = 0.0
        geolocation_data = None
        
        try:
            # Get geolocation data (mock implementation - use real GeoIP service)
            geolocation_data = await self._get_geolocation_data(ip_address)
            
            if geolocation_data:
                # Check for VPN/Tor usage
                if geolocation_data.is_vpn or geolocation_data.is_tor:
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.VPN_TOR_DETECTED,
                        severity=SecurityThreatLevel.YELLOW,
                        confidence=0.8,
                        timestamp=datetime.utcnow(),
                        description=f"VPN/Tor detected from {geolocation_data.country_name}",
                        metadata={
                            'is_vpn': geolocation_data.is_vpn,
                            'is_tor': geolocation_data.is_tor,
                            'country': geolocation_data.country_code
                        }
                    ))
                    risk_score = max(risk_score, 0.4)
                
                # Check user's typical countries
                user_countries_key = f"user_countries:{user_id}"
                user_countries = await self.redis_client.smembers(user_countries_key)
                
                if not user_countries:
                    # First time user - record country
                    await self.redis_client.sadd(user_countries_key, geolocation_data.country_code)
                    await self.redis_client.expire(user_countries_key, 86400 * 30)  # 30 days
                    risk_score = max(risk_score, 0.2)  # Low risk for new users
                elif geolocation_data.country_code not in user_countries:
                    # User from new country
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.GEOGRAPHIC_ANOMALY,
                        severity=SecurityThreatLevel.YELLOW,
                        confidence=0.7,
                        timestamp=datetime.utcnow(),
                        description=f"User accessing from new country: {geolocation_data.country_name}",
                        metadata={
                            'new_country': geolocation_data.country_code,
                            'typical_countries': list(user_countries)
                        }
                    ))
                    risk_score = max(risk_score, 0.5)
                    
                    # Add new country to user's profile
                    await self.redis_client.sadd(user_countries_key, geolocation_data.country_code)
                
                # Check for impossible travel (very fast location changes)
                last_location_key = f"user_last_location:{user_id}"
                last_location_data = await self.redis_client.get(last_location_key)
                
                if last_location_data:
                    last_location = json.loads(last_location_data)
                    if await self._is_impossible_travel(
                        last_location, geolocation_data, datetime.utcnow()
                    ):
                        indicators.append(ThreatIndicator(
                            indicator_type=AnomalyType.GEOGRAPHIC_ANOMALY,
                            severity=SecurityThreatLevel.ORANGE,
                            confidence=0.8,
                            timestamp=datetime.utcnow(),
                            description="Impossible travel detected",
                            metadata={
                                'previous_location': last_location,
                                'current_location': {
                                    'country': geolocation_data.country_code,
                                    'city': geolocation_data.city
                                }
                            }
                        ))
                        risk_score = max(risk_score, 0.8)
                
                # Update last location
                location_data = {
                    'country_code': geolocation_data.country_code,
                    'latitude': geolocation_data.latitude,
                    'longitude': geolocation_data.longitude,
                    'timestamp': datetime.utcnow().isoformat()
                }
                await self.redis_client.setex(
                    last_location_key, 
                    3600,  # 1 hour
                    json.dumps(location_data)
                )
                
        except Exception as e:
            logger.warning(f"Geolocation analysis failed: {e}")
            risk_score = 0.3  # Moderate risk on analysis failure
        
        return {
            'risk_score': risk_score,
            'indicators': indicators,
            'geolocation_data': geolocation_data,
            'analysis_type': 'geolocation'
        }
    
    async def _analyze_user_agent(
        self, 
        user_agent: str, 
        user_id: UUID
    ) -> Dict[str, Any]:
        """Analyze user agent for suspicious patterns."""
        indicators = []
        risk_score = 0.0
        analysis_data = None
        
        try:
            if not user_agent:
                indicators.append(ThreatIndicator(
                    indicator_type=AnomalyType.UNUSUAL_USER_AGENT,
                    severity=SecurityThreatLevel.YELLOW,
                    confidence=0.8,
                    timestamp=datetime.utcnow(),
                    description="Missing user agent"
                ))
                risk_score = 0.6
                return {
                    'risk_score': risk_score,
                    'indicators': indicators,
                    'analysis_data': None,
                    'analysis_type': 'user_agent'
                }
            
            # Parse user agent
            parsed_ua = parse_user_agent(user_agent)
            
            analysis_data = UserAgentAnalysis(
                browser_family=parsed_ua.browser.family,
                browser_version=str(parsed_ua.browser.version),
                operating_system=str(parsed_ua.os),
                device_type='mobile' if parsed_ua.is_mobile else 'desktop',
                is_bot=parsed_ua.is_bot,
                is_mobile=parsed_ua.is_mobile,
                is_automation_tool=False,  # Will be determined below
                risk_score=0.0,
                unusual_patterns=[]
            )
            
            # Check for bot patterns
            user_agent_lower = user_agent.lower()
            for pattern in self.bot_patterns:
                if re.search(pattern, user_agent_lower):
                    analysis_data.is_automation_tool = True
                    analysis_data.unusual_patterns.append(f"bot_pattern_{pattern}")
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.BOT_PATTERN_DETECTED,
                        severity=SecurityThreatLevel.ORANGE,
                        confidence=0.8,
                        timestamp=datetime.utcnow(),
                        description=f"Bot/automation pattern detected: {pattern}",
                        metadata={'pattern': pattern}
                    ))
                    risk_score = max(risk_score, 0.7)
            
            # Check for suspicious patterns (potential XSS in user agent)
            for pattern in self.suspicious_ua_patterns:
                if re.search(pattern, user_agent_lower):
                    analysis_data.unusual_patterns.append(f"suspicious_pattern_{pattern}")
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.XSS_ATTEMPT,
                        severity=SecurityThreatLevel.RED,
                        confidence=0.9,
                        timestamp=datetime.utcnow(),
                        description=f"Suspicious pattern in user agent: {pattern}",
                        metadata={'pattern': pattern}
                    ))
                    risk_score = 1.0  # Maximum risk
            
            # Check for outdated/vulnerable browsers
            if parsed_ua.browser.family:
                if 'Internet Explorer' in parsed_ua.browser.family:
                    analysis_data.unusual_patterns.append("outdated_browser_ie")
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.UNUSUAL_USER_AGENT,
                        severity=SecurityThreatLevel.YELLOW,
                        confidence=0.6,
                        timestamp=datetime.utcnow(),
                        description="Outdated browser detected (IE)",
                        metadata={'browser': parsed_ua.browser.family}
                    ))
                    risk_score = max(risk_score, 0.4)
            
            # Check user's typical user agents
            user_agents_key = f"user_agents:{user_id}"
            ua_hash = hashlib.md5(user_agent.encode()).hexdigest()
            
            is_new_ua = not await self.redis_client.sismember(user_agents_key, ua_hash)
            if is_new_ua:
                await self.redis_client.sadd(user_agents_key, ua_hash)
                await self.redis_client.expire(user_agents_key, 86400 * 30)  # 30 days
                
                # Check ratio of new user agents
                total_uas = await self.redis_client.scard(user_agents_key)
                if total_uas > 10:  # User has many different user agents
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.UNUSUAL_USER_AGENT,
                        severity=SecurityThreatLevel.YELLOW,
                        confidence=0.5,
                        timestamp=datetime.utcnow(),
                        description=f"User has many different user agents: {total_uas}",
                        metadata={'total_user_agents': total_uas}
                    ))
                    risk_score = max(risk_score, 0.3)
            
            # Check for very long user agents (potential buffer overflow attempts)
            if len(user_agent) > 1000:
                analysis_data.unusual_patterns.append("excessively_long_ua")
                indicators.append(ThreatIndicator(
                    indicator_type=AnomalyType.UNUSUAL_USER_AGENT,
                    severity=SecurityThreatLevel.ORANGE,
                    confidence=0.8,
                    timestamp=datetime.utcnow(),
                    description=f"Excessively long user agent: {len(user_agent)} characters",
                    metadata={'user_agent_length': len(user_agent)}
                ))
                risk_score = max(risk_score, 0.6)
            
            analysis_data.risk_score = risk_score
            
        except Exception as e:
            logger.warning(f"User agent analysis failed: {e}")
            risk_score = 0.4  # Moderate risk on analysis failure
        
        return {
            'risk_score': risk_score,
            'indicators': indicators,
            'analysis_data': analysis_data,
            'analysis_type': 'user_agent'
        }
    
    async def _analyze_behavioral_patterns(
        self,
        user_id: UUID,
        previous_requests: List[Dict[str, Any]],
        current_timestamp: datetime
    ) -> Dict[str, Any]:
        """Analyze user behavioral patterns for anomalies."""
        indicators = []
        risk_score = 0.0
        
        try:
            if not previous_requests:
                return {
                    'risk_score': 0.2,  # Low risk for new users
                    'indicators': indicators,
                    'analysis_type': 'behavioral'
                }
            
            # Analyze request timing patterns
            if len(previous_requests) >= 2:
                time_intervals = []
                for i in range(1, len(previous_requests)):
                    prev_time = previous_requests[i-1].get('timestamp')
                    curr_time = previous_requests[i].get('timestamp')
                    if prev_time and curr_time:
                        if isinstance(prev_time, str):
                            prev_time = datetime.fromisoformat(prev_time)
                        if isinstance(curr_time, str):
                            curr_time = datetime.fromisoformat(curr_time)
                        interval = abs((curr_time - prev_time).total_seconds())
                        time_intervals.append(interval)
                
                if time_intervals:
                    avg_interval = sum(time_intervals) / len(time_intervals)
                    
                    # Check for suspiciously regular timing (bot behavior)
                    if len(set(time_intervals)) == 1:  # All intervals identical
                        indicators.append(ThreatIndicator(
                            indicator_type=AnomalyType.BOT_PATTERN_DETECTED,
                            severity=SecurityThreatLevel.ORANGE,
                            confidence=0.8,
                            timestamp=datetime.utcnow(),
                            description="Perfectly regular request timing detected",
                            metadata={'interval': time_intervals[0]}
                        ))
                        risk_score = max(risk_score, 0.7)
                    
                    # Check for very rapid requests (potential automated attack)
                    rapid_requests = sum(1 for interval in time_intervals if interval < 1.0)
                    if rapid_requests > len(time_intervals) * 0.8:  # 80% of requests < 1 second apart
                        indicators.append(ThreatIndicator(
                            indicator_type=AnomalyType.REQUEST_SPIKE_DETECTED,
                            severity=SecurityThreatLevel.ORANGE,
                            confidence=0.8,
                            timestamp=datetime.utcnow(),
                            description=f"Rapid request pattern: {rapid_requests} requests < 1s apart",
                            metadata={
                                'rapid_requests': rapid_requests,
                                'total_requests': len(time_intervals),
                                'average_interval': avg_interval
                            }
                        ))
                        risk_score = max(risk_score, 0.8)
            
            # Analyze access type patterns
            access_types = [req.get('access_type') for req in previous_requests if req.get('access_type')]
            if access_types:
                admin_attempts = access_types.count('admin')
                write_attempts = access_types.count('write') + access_types.count('delete')
                
                # Check for excessive privilege escalation attempts
                total_requests = len(access_types)
                admin_ratio = admin_attempts / total_requests if total_requests > 0 else 0
                
                if admin_ratio > 0.5:  # More than 50% admin attempts
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.PRIVILEGE_ESCALATION_ATTEMPT,
                        severity=SecurityThreatLevel.RED,
                        confidence=0.9,
                        timestamp=datetime.utcnow(),
                        description=f"High admin access attempts: {admin_ratio:.1%} of requests",
                        metadata={
                            'admin_attempts': admin_attempts,
                            'total_requests': total_requests,
                            'admin_ratio': admin_ratio
                        }
                    ))
                    risk_score = 1.0  # Maximum risk
                elif admin_ratio > 0.2:  # More than 20% admin attempts
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.PRIVILEGE_ESCALATION_ATTEMPT,
                        severity=SecurityThreatLevel.ORANGE,
                        confidence=0.7,
                        timestamp=datetime.utcnow(),
                        description=f"Elevated admin access attempts: {admin_ratio:.1%} of requests",
                        metadata={
                            'admin_attempts': admin_attempts,
                            'total_requests': total_requests,
                            'admin_ratio': admin_ratio
                        }
                    ))
                    risk_score = max(risk_score, 0.6)
            
            # Check for unusual time-based access patterns
            request_hours = []
            for req in previous_requests:
                timestamp = req.get('timestamp')
                if timestamp:
                    if isinstance(timestamp, str):
                        timestamp = datetime.fromisoformat(timestamp)
                    request_hours.append(timestamp.hour)
            
            if len(request_hours) > 10:
                # Check if all requests are at unusual hours (midnight to 6 AM)
                unusual_hours = sum(1 for hour in request_hours if 0 <= hour <= 6)
                if unusual_hours / len(request_hours) > 0.8:  # 80% at unusual hours
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.TIME_BASED_ANOMALY,
                        severity=SecurityThreatLevel.YELLOW,
                        confidence=0.6,
                        timestamp=datetime.utcnow(),
                        description="Unusual time-based access pattern detected",
                        metadata={
                            'unusual_hours_ratio': unusual_hours / len(request_hours),
                            'typical_hours': list(set(request_hours))
                        }
                    ))
                    risk_score = max(risk_score, 0.4)
            
        except Exception as e:
            logger.warning(f"Behavioral analysis failed: {e}")
            risk_score = 0.3  # Moderate risk on analysis failure
        
        return {
            'risk_score': risk_score,
            'indicators': indicators,
            'analysis_type': 'behavioral'
        }
    
    async def _check_threat_intelligence(
        self,
        ip_address: str,
        user_agent: str
    ) -> Dict[str, Any]:
        """Check against threat intelligence sources."""
        indicators = []
        risk_score = 0.0
        
        try:
            # Check IP against threat intelligence feeds
            for source in self.threat_intel_sources:
                is_threat = await self._check_threat_source(source, ip_address)
                if is_threat:
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.SUSPICIOUS_IP_PATTERN,
                        severity=SecurityThreatLevel.RED,
                        confidence=0.9,
                        timestamp=datetime.utcnow(),
                        description=f"IP found in threat intelligence source: {source}",
                        metadata={'source': source, 'ip': ip_address}
                    ))
                    risk_score = 1.0  # Maximum risk for known threats
                    break
            
            # Check user agent against known malicious patterns
            # This would integrate with real threat intelligence feeds
            malicious_ua_indicators = [
                'sqlmap', 'nmap', 'nikto', 'burp', 'owasp zap',
                'metasploit', 'havij', 'acunetix'
            ]
            
            user_agent_lower = user_agent.lower() if user_agent else ''
            for indicator in malicious_ua_indicators:
                if indicator in user_agent_lower:
                    indicators.append(ThreatIndicator(
                        indicator_type=AnomalyType.AUTOMATION_DETECTED,
                        severity=SecurityThreatLevel.RED,
                        confidence=0.95,
                        timestamp=datetime.utcnow(),
                        description=f"Malicious tool detected in user agent: {indicator}",
                        metadata={'tool': indicator}
                    ))
                    risk_score = 1.0
                    break
            
        except Exception as e:
            logger.warning(f"Threat intelligence check failed: {e}")
        
        return {
            'risk_score': risk_score,
            'indicators': indicators,
            'analysis_type': 'threat_intelligence'
        }
    
    # Helper methods
    
    def _generate_cache_key(self, security_context: SecurityContextData) -> str:
        """Generate cache key for security context validation."""
        key_data = f"{security_context.ip_address}:{hashlib.md5(security_context.user_agent.encode()).hexdigest()}"
        return f"security_context:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    async def _get_cached_validation(self, cache_key: str) -> Optional[LayerResult]:
        """Retrieve cached validation result."""
        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                data = json.loads(cached_data)
                return LayerResult(**data)
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
        return None
    
    async def _cache_validation_result(
        self, 
        cache_key: str, 
        result: LayerResult, 
        ttl: int = 300
    ):
        """Cache validation result."""
        try:
            await self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(asdict(result), default=str)
            )
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")
    
    def _calculate_overall_risk_score(self, risk_scores: Dict[str, float]) -> float:
        """Calculate weighted overall risk score."""
        total_score = 0.0
        total_weight = 0.0
        
        for component, score in risk_scores.items():
            weight = self.risk_weights.get(component, 0.1)
            total_score += score * weight
            total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def _determine_threat_level(
        self, 
        overall_risk: float, 
        indicators: List[ThreatIndicator]
    ) -> SecurityThreatLevel:
        """Determine overall threat level based on risk score and indicators."""
        # Check for any RED level indicators
        red_indicators = [ind for ind in indicators if ind.severity == SecurityThreatLevel.RED]
        if red_indicators:
            return SecurityThreatLevel.RED
        
        # Check for multiple ORANGE indicators
        orange_indicators = [ind for ind in indicators if ind.severity == SecurityThreatLevel.ORANGE]
        if len(orange_indicators) >= 2:
            return SecurityThreatLevel.ORANGE
        
        # Use risk score thresholds
        if overall_risk >= 0.8:
            return SecurityThreatLevel.RED
        elif overall_risk >= 0.6:
            return SecurityThreatLevel.ORANGE
        elif overall_risk >= 0.3:
            return SecurityThreatLevel.YELLOW
        else:
            return SecurityThreatLevel.GREEN
    
    def _generate_security_flags(
        self, 
        risk_scores: Dict[str, float], 
        indicators: List[ThreatIndicator]
    ) -> List[str]:
        """Generate security flags based on analysis results."""
        flags = []
        
        if risk_scores.get('ip_reputation', 0) > 0.7:
            flags.append('HIGH_IP_RISK')
        
        if risk_scores.get('user_agent', 0) > 0.7:
            flags.append('SUSPICIOUS_USER_AGENT')
        
        if risk_scores.get('behavioral', 0) > 0.7:
            flags.append('ANOMALOUS_BEHAVIOR')
        
        if risk_scores.get('geolocation', 0) > 0.5:
            flags.append('GEOGRAPHIC_ANOMALY')
        
        if risk_scores.get('threat_intel', 0) > 0.0:
            flags.append('THREAT_INTELLIGENCE_HIT')
        
        # Add specific flags based on indicators
        for indicator in indicators:
            if indicator.indicator_type == AnomalyType.VPN_TOR_DETECTED:
                flags.append('VPN_TOR_USAGE')
            elif indicator.indicator_type == AnomalyType.BOT_PATTERN_DETECTED:
                flags.append('BOT_DETECTED')
            elif indicator.indicator_type in [AnomalyType.SQL_INJECTION_ATTEMPT, AnomalyType.XSS_ATTEMPT]:
                flags.append('INJECTION_ATTEMPT')
        
        return list(set(flags))  # Remove duplicates
    
    def _categorize_threat_indicator(self, indicator: ThreatIndicator) -> ThreatCategory:
        """Categorize threat indicator into threat category."""
        if indicator.indicator_type in [
            AnomalyType.SQL_INJECTION_ATTEMPT, 
            AnomalyType.XSS_ATTEMPT
        ]:
            return ThreatCategory.INJECTION_ATTACK
        elif indicator.indicator_type in [
            AnomalyType.RATE_LIMIT_EXCEEDED,
            AnomalyType.REQUEST_SPIKE_DETECTED
        ]:
            return ThreatCategory.RATE_LIMIT_ABUSE
        elif indicator.indicator_type == AnomalyType.PRIVILEGE_ESCALATION_ATTEMPT:
            return ThreatCategory.PRIVILEGE_ESCALATION
        elif indicator.indicator_type in [
            AnomalyType.GEOGRAPHIC_ANOMALY,
            AnomalyType.VPN_TOR_DETECTED
        ]:
            return ThreatCategory.GEOGRAPHIC_ANOMALY
        elif indicator.indicator_type in [
            AnomalyType.BOT_PATTERN_DETECTED,
            AnomalyType.AUTOMATION_DETECTED
        ]:
            return ThreatCategory.BEHAVIORAL_ANOMALY
        else:
            return ThreatCategory.SYSTEM_COMPROMISE
    
    async def _count_recent_requests(self, key: str, window_seconds: int) -> int:
        """Count recent requests within time window."""
        try:
            current_time = time.time()
            window_start = current_time - window_seconds
            
            # Remove old entries
            await self.redis_client.zremrangebyscore(key, 0, window_start)
            
            # Add current request
            await self.redis_client.zadd(key, {str(current_time): current_time})
            await self.redis_client.expire(key, window_seconds)
            
            # Count entries in window
            return await self.redis_client.zcard(key)
        except Exception:
            return 0
    
    async def _get_geolocation_data(self, ip_address: str) -> Optional[GeolocationData]:
        """Get geolocation data for IP address."""
        # Mock implementation - in production use real GeoIP service
        try:
            # This would call a real geolocation service
            return GeolocationData(
                country_code='US',
                country_name='United States',
                region='California',
                city='San Francisco',
                latitude=37.7749,
                longitude=-122.4194,
                timezone='America/Los_Angeles',
                is_vpn=False,
                is_tor=False,
                is_proxy=False,
                confidence=0.9
            )
        except Exception:
            return None
    
    async def _is_impossible_travel(
        self, 
        last_location: Dict[str, Any], 
        current_location: GeolocationData,
        current_time: datetime
    ) -> bool:
        """Check if travel between locations is impossible given time elapsed."""
        try:
            if not last_location.get('latitude') or not current_location.latitude:
                return False
            
            last_time_str = last_location.get('timestamp')
            if not last_time_str:
                return False
            
            last_time = datetime.fromisoformat(last_time_str)
            time_diff = (current_time - last_time).total_seconds() / 3600  # Hours
            
            if time_diff < 0.5:  # Less than 30 minutes
                # Calculate distance (simplified - use proper geospatial calculation in production)
                lat_diff = abs(last_location['latitude'] - current_location.latitude)
                lon_diff = abs(last_location['longitude'] - current_location.longitude)
                
                # Rough distance calculation (not accurate for all cases)
                distance_km = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111  # Rough conversion
                
                # Maximum possible speed including commercial flights (1000 km/h)
                max_speed_kmh = 1000
                max_distance = max_speed_kmh * time_diff
                
                return distance_km > max_distance
        except Exception:
            pass
        
        return False
    
    async def _check_threat_source(self, source: str, ip_address: str) -> bool:
        """Check IP against specific threat intelligence source."""
        # Mock implementation - in production integrate with real threat intel feeds
        try:
            threat_list_key = f"threat_intel:{source}"
            return await self.redis_client.sismember(threat_list_key, ip_address)
        except Exception:
            return False
    
    async def _update_behavioral_patterns(
        self,
        user_id: UUID,
        security_context: SecurityContextData,
        risk_scores: Dict[str, float]
    ):
        """Update user behavioral patterns for future analysis."""
        try:
            patterns_key = f"behavioral_patterns:{user_id}"
            
            # Create/update behavioral pattern
            current_pattern = {
                'last_ip': security_context.ip_address,
                'last_user_agent_hash': hashlib.md5(security_context.user_agent.encode()).hexdigest(),
                'last_access_time': security_context.request_timestamp.isoformat(),
                'risk_history': risk_scores,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            await self.redis_client.setex(
                patterns_key,
                86400 * 7,  # Keep for 7 days
                json.dumps(current_pattern, default=str)
            )
            
        except Exception as e:
            logger.warning(f"Failed to update behavioral patterns: {e}")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for this validator."""
        return {
            'average_validation_time_ms': sum(self.validation_times) / len(self.validation_times) if self.validation_times else 0,
            'cache_hit_ratio': self.cache_stats['hits'] / (self.cache_stats['hits'] + self.cache_stats['misses']) if (self.cache_stats['hits'] + self.cache_stats['misses']) > 0 else 0,
            'total_validations': len(self.validation_times),
            'cache_hits': self.cache_stats['hits'],
            'cache_misses': self.cache_stats['misses']
        }