"""
Enterprise-Grade Rate Limiting with Advanced Threat Detection
Implements multiple rate limiting strategies with comprehensive monitoring.
"""
import os
import logging
import hashlib
import asyncio
import json
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
import time

from fastapi import Request, HTTPException, status

try:
    from config import settings
except ImportError:
    class FallbackSettings:
        def is_production(self): return True
        rate_limit_per_minute = 30
        enable_adaptive_rate_limiting = True
    settings = FallbackSettings()

logger = logging.getLogger(__name__)

class ThreatLevel(Enum):
    """Security threat levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RateLimitStrategy(Enum):
    """Rate limiting strategies."""
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    ADAPTIVE = "adaptive"

@dataclass
class RateLimitRule:
    """Rate limit rule configuration."""
    name: str
    limit: int
    window: int  # seconds
    strategy: RateLimitStrategy
    endpoint_pattern: Optional[str] = None
    method: Optional[str] = None
    user_based: bool = False
    threat_multiplier: float = 1.0

@dataclass
class SecurityEvent:
    """Security event for monitoring."""
    timestamp: datetime
    client_ip: str
    user_id: Optional[str]
    event_type: str
    threat_level: ThreatLevel
    details: Dict[str, Any]

class EnterpriseRateLimiter:
    """
    Enterprise-grade rate limiter with:
    - Multiple rate limiting strategies
    - Adaptive limits based on system load
    - Advanced threat detection
    - Comprehensive monitoring and alerting
    - Distributed rate limiting support
    """
    
    def __init__(self):
        # In-memory storage (in production, use Redis)
        self._request_counts: Dict[str, List[float]] = {}
        self._token_buckets: Dict[str, Dict[str, Any]] = {}
        self._suspicious_ips: Set[str] = set()
        self._security_events: List[SecurityEvent] = []
        
        # Rate limiting rules (enterprise configuration)
        self._rules = self._initialize_rate_limit_rules()
        
        # System monitoring
        self._system_load = 0.5  # Would be actual system metrics in production
        self._error_rate = 0.0
        
        # Advanced threat detection
        self._ip_behavior_analysis = {}
        self._attack_patterns = self._initialize_attack_patterns()
    
    def _initialize_rate_limit_rules(self) -> List[RateLimitRule]:
        """Initialize comprehensive rate limiting rules."""
        return [
            # Authentication endpoints (most restrictive)
            RateLimitRule(
                name="auth_login",
                limit=3,
                window=3600,  # 1 hour
                strategy=RateLimitStrategy.SLIDING_WINDOW,
                endpoint_pattern="/api/v1/auth/login",
                method="POST",
                threat_multiplier=2.0
            ),
            RateLimitRule(
                name="auth_register", 
                limit=2,
                window=3600,  # 1 hour
                strategy=RateLimitStrategy.SLIDING_WINDOW,
                endpoint_pattern="/api/v1/auth/register",
                method="POST",
                threat_multiplier=2.0
            ),
            RateLimitRule(
                name="auth_refresh",
                limit=20,
                window=3600,  # 1 hour
                strategy=RateLimitStrategy.TOKEN_BUCKET,
                endpoint_pattern="/api/v1/auth/refresh",
                method="POST",
                user_based=True
            ),
            
            # Generation endpoints (resource intensive)
            RateLimitRule(
                name="generation_create",
                limit=10,
                window=3600,  # 1 hour
                strategy=RateLimitStrategy.ADAPTIVE,
                endpoint_pattern="/api/v1/generations",
                method="POST", 
                user_based=True,
                threat_multiplier=1.5
            ),
            
            # API endpoints (standard)
            RateLimitRule(
                name="api_standard",
                limit=100,
                window=60,  # 1 minute
                strategy=RateLimitStrategy.SLIDING_WINDOW,
                user_based=True
            ),
            
            # File upload endpoints
            RateLimitRule(
                name="file_upload",
                limit=20,
                window=3600,  # 1 hour
                strategy=RateLimitStrategy.TOKEN_BUCKET,
                endpoint_pattern="/api/v1/storage/upload",
                method="POST",
                user_based=True,
                threat_multiplier=1.2
            ),
            
            # Password reset (security sensitive)
            RateLimitRule(
                name="password_reset",
                limit=3,
                window=3600,  # 1 hour
                strategy=RateLimitStrategy.FIXED_WINDOW,
                endpoint_pattern="/api/v1/auth/reset-password",
                method="POST",
                threat_multiplier=3.0
            ),
            
            # Global rate limit (catch-all)
            RateLimitRule(
                name="global_limit",
                limit=200,
                window=60,  # 1 minute
                strategy=RateLimitStrategy.SLIDING_WINDOW,
                threat_multiplier=1.0
            )
        ]
    
    def _initialize_attack_patterns(self) -> Dict[str, Dict]:
        """Initialize attack pattern detection."""
        return {
            "brute_force": {
                "pattern": "rapid_auth_failures",
                "threshold": 10,
                "window": 300,  # 5 minutes
                "action": "block_ip"
            },
            "ddos_attempt": {
                "pattern": "high_request_volume",
                "threshold": 1000,
                "window": 60,  # 1 minute
                "action": "rate_limit"
            },
            "credential_stuffing": {
                "pattern": "multi_account_failures",
                "threshold": 50,
                "window": 3600,  # 1 hour
                "action": "block_ip"
            },
            "api_abuse": {
                "pattern": "resource_exhaustion",
                "threshold": 100,
                "window": 300,  # 5 minutes
                "action": "throttle"
            }
        }
    
    async def check_rate_limit(self, request: Request, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Comprehensive rate limit check with advanced threat detection.
        
        Args:
            request: FastAPI request object
            user_id: Optional authenticated user ID
            
        Returns:
            Dict containing rate limit status and metadata
            
        Raises:
            HTTPException: If rate limit is exceeded
        """
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Advanced threat detection
        threat_level = await self._analyze_request_threat(request, client_ip, user_id)
        
        # Get applicable rules for this request
        applicable_rules = self._get_applicable_rules(request, user_id)
        
        # Check each applicable rule
        for rule in applicable_rules:
            # Create rate limit key
            rate_key = self._create_rate_key(rule, client_ip, user_id, request)
            
            # Apply threat multiplier
            effective_limit = int(rule.limit / rule.threat_multiplier) if threat_level != ThreatLevel.LOW else rule.limit
            
            # Check rate limit based on strategy
            result = await self._check_rule_limit(rule, rate_key, effective_limit, current_time)
            
            if not result["allowed"]:
                # Log security event
                await self._log_security_event(
                    client_ip, user_id, "rate_limit_exceeded", threat_level,
                    {"rule": rule.name, "limit": effective_limit, "window": rule.window}
                )
                
                # Update threat analysis
                await self._update_threat_analysis(client_ip, user_id, "rate_limit_violation")
                
                # Create appropriate error response
                retry_after = result.get("retry_after", rule.window)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=self._get_rate_limit_message(rule, threat_level),
                    headers={
                        "Retry-After": str(int(retry_after)),
                        "X-RateLimit-Limit": str(effective_limit),
                        "X-RateLimit-Remaining": str(result.get("remaining", 0)),
                        "X-RateLimit-Reset": str(int(current_time + rule.window))
                    }
                )
        
        return {"allowed": True, "threat_level": threat_level.value}
    
    async def _analyze_request_threat(self, request: Request, client_ip: str, user_id: Optional[str]) -> ThreatLevel:
        """Advanced threat level analysis."""
        
        # Check if IP is already flagged as suspicious
        if client_ip in self._suspicious_ips:
            return ThreatLevel.HIGH
        
        # Analyze IP behavior patterns
        ip_analysis = self._ip_behavior_analysis.get(client_ip, {
            "request_count": 0,
            "error_count": 0,
            "first_seen": time.time(),
            "last_seen": time.time(),
            "endpoints": set(),
            "user_agents": set()
        })
        
        current_time = time.time()
        ip_analysis["last_seen"] = current_time
        ip_analysis["request_count"] += 1
        ip_analysis["endpoints"].add(request.url.path)
        ip_analysis["user_agents"].add(request.headers.get("user-agent", "unknown")[:100])
        
        # Calculate threat indicators
        threat_score = 0
        
        # High request frequency from single IP
        time_window = current_time - ip_analysis["first_seen"]
        if time_window > 0:
            request_rate = ip_analysis["request_count"] / (time_window / 60)  # requests per minute
            if request_rate > 100:
                threat_score += 2
            elif request_rate > 50:
                threat_score += 1
        
        # High error rate
        error_rate = ip_analysis["error_count"] / max(ip_analysis["request_count"], 1)
        if error_rate > 0.5:
            threat_score += 2
        elif error_rate > 0.2:
            threat_score += 1
        
        # Multiple user agents (possible bot)
        if len(ip_analysis["user_agents"]) > 10:
            threat_score += 1
        
        # Accessing many different endpoints (scanning behavior)
        if len(ip_analysis["endpoints"]) > 50:
            threat_score += 1
        
        # Check for attack patterns
        for pattern_name, pattern_config in self._attack_patterns.items():
            if await self._matches_attack_pattern(pattern_name, pattern_config, client_ip, user_id):
                threat_score += 3
        
        self._ip_behavior_analysis[client_ip] = ip_analysis
        
        # Determine threat level
        if threat_score >= 5:
            self._suspicious_ips.add(client_ip)
            return ThreatLevel.CRITICAL
        elif threat_score >= 3:
            return ThreatLevel.HIGH
        elif threat_score >= 1:
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW
    
    async def _matches_attack_pattern(self, pattern_name: str, pattern_config: Dict, client_ip: str, user_id: Optional[str]) -> bool:
        """Check if request matches known attack patterns."""
        
        # This would be expanded with actual pattern matching logic
        # For now, basic placeholder implementation
        
        if pattern_name == "brute_force":
            # Check for rapid authentication failures
            recent_failures = self._count_recent_events(
                client_ip, "auth_failure", pattern_config["window"]
            )
            return recent_failures >= pattern_config["threshold"]
        
        elif pattern_name == "ddos_attempt":
            # Check for high volume of requests
            recent_requests = self._count_recent_events(
                client_ip, "request", pattern_config["window"]
            )
            return recent_requests >= pattern_config["threshold"]
        
        # Add more pattern matching logic as needed
        return False
    
    def _count_recent_events(self, client_ip: str, event_type: str, window: int) -> int:
        """Count recent events for pattern matching."""
        current_time = time.time()
        cutoff_time = current_time - window
        
        count = 0
        for event in self._security_events:
            if (event.client_ip == client_ip and 
                event.event_type == event_type and 
                event.timestamp.timestamp() > cutoff_time):
                count += 1
        
        return count
    
    def _get_applicable_rules(self, request: Request, user_id: Optional[str]) -> List[RateLimitRule]:
        """Get rate limiting rules applicable to this request."""
        applicable_rules = []
        
        for rule in self._rules:
            # Check endpoint pattern
            if rule.endpoint_pattern:
                if not request.url.path.startswith(rule.endpoint_pattern):
                    continue
            
            # Check HTTP method
            if rule.method and rule.method.upper() != request.method.upper():
                continue
            
            # Check user-based rules
            if rule.user_based and not user_id:
                continue
            
            applicable_rules.append(rule)
        
        # Always include global limit
        global_rule = next((r for r in self._rules if r.name == "global_limit"), None)
        if global_rule and global_rule not in applicable_rules:
            applicable_rules.append(global_rule)
        
        return applicable_rules
    
    def _create_rate_key(self, rule: RateLimitRule, client_ip: str, user_id: Optional[str], request: Request) -> str:
        """Create unique rate limiting key."""
        key_parts = [rule.name]
        
        if rule.user_based and user_id:
            key_parts.append(f"user:{user_id}")
        else:
            key_parts.append(f"ip:{client_ip}")
        
        if rule.endpoint_pattern:
            key_parts.append(f"endpoint:{rule.endpoint_pattern}")
        
        if rule.method:
            key_parts.append(f"method:{rule.method}")
        
        return ":".join(key_parts)
    
    async def _check_rule_limit(self, rule: RateLimitRule, rate_key: str, limit: int, current_time: float) -> Dict[str, Any]:
        """Check rate limit for specific rule."""
        
        if rule.strategy == RateLimitStrategy.SLIDING_WINDOW:
            return await self._sliding_window_check(rate_key, limit, rule.window, current_time)
        elif rule.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return await self._token_bucket_check(rate_key, limit, rule.window, current_time)
        elif rule.strategy == RateLimitStrategy.ADAPTIVE:
            return await self._adaptive_limit_check(rate_key, limit, rule.window, current_time)
        else:  # FIXED_WINDOW
            return await self._fixed_window_check(rate_key, limit, rule.window, current_time)
    
    async def _sliding_window_check(self, key: str, limit: int, window: int, current_time: float) -> Dict[str, Any]:
        """Sliding window rate limiting implementation."""
        if key not in self._request_counts:
            self._request_counts[key] = []
        
        # Remove old entries
        cutoff_time = current_time - window
        self._request_counts[key] = [t for t in self._request_counts[key] if t > cutoff_time]
        
        # Check limit
        current_count = len(self._request_counts[key])
        if current_count >= limit:
            oldest_request = min(self._request_counts[key]) if self._request_counts[key] else current_time
            retry_after = window - (current_time - oldest_request)
            return {
                "allowed": False,
                "remaining": 0,
                "retry_after": max(1, retry_after)
            }
        
        # Add current request
        self._request_counts[key].append(current_time)
        
        return {
            "allowed": True,
            "remaining": limit - current_count - 1,
            "retry_after": 0
        }
    
    async def _token_bucket_check(self, key: str, capacity: int, refill_time: int, current_time: float) -> Dict[str, Any]:
        """Token bucket rate limiting implementation."""
        if key not in self._token_buckets:
            self._token_buckets[key] = {
                "tokens": capacity,
                "last_refill": current_time
            }
        
        bucket = self._token_buckets[key]
        
        # Calculate tokens to add
        time_passed = current_time - bucket["last_refill"]
        tokens_to_add = (time_passed / refill_time) * capacity
        bucket["tokens"] = min(capacity, bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = current_time
        
        # Check if token available
        if bucket["tokens"] < 1:
            retry_after = refill_time / capacity  # Time for one token
            return {
                "allowed": False,
                "remaining": 0,
                "retry_after": retry_after
            }
        
        # Consume token
        bucket["tokens"] -= 1
        
        return {
            "allowed": True,
            "remaining": int(bucket["tokens"]),
            "retry_after": 0
        }
    
    async def _adaptive_limit_check(self, key: str, base_limit: int, window: int, current_time: float) -> Dict[str, Any]:
        """Adaptive rate limiting based on system conditions."""
        
        # Calculate adaptive limit based on system metrics
        load_factor = 1.0
        
        # Adjust based on system load
        if self._system_load > 0.8:
            load_factor *= 0.5  # Reduce limits when system is under load
        elif self._system_load < 0.3:
            load_factor *= 1.5  # Increase limits when system has capacity
        
        # Adjust based on error rate
        if self._error_rate > 0.1:
            load_factor *= 0.7  # Reduce limits when error rate is high
        
        adaptive_limit = int(base_limit * load_factor)
        
        # Use sliding window with adaptive limit
        return await self._sliding_window_check(key, adaptive_limit, window, current_time)
    
    async def _fixed_window_check(self, key: str, limit: int, window: int, current_time: float) -> Dict[str, Any]:
        """Fixed window rate limiting implementation."""
        window_start = int(current_time // window) * window
        window_key = f"{key}:window:{window_start}"
        
        if window_key not in self._request_counts:
            self._request_counts[window_key] = []
        
        current_count = len(self._request_counts[window_key])
        if current_count >= limit:
            retry_after = window - (current_time - window_start)
            return {
                "allowed": False,
                "remaining": 0,
                "retry_after": max(1, retry_after)
            }
        
        # Add current request
        self._request_counts[window_key].append(current_time)
        
        return {
            "allowed": True,
            "remaining": limit - current_count - 1,
            "retry_after": 0
        }
    
    async def _log_security_event(self, client_ip: str, user_id: Optional[str], event_type: str, threat_level: ThreatLevel, details: Dict[str, Any]):
        """Log security event for monitoring."""
        event = SecurityEvent(
            timestamp=datetime.now(timezone.utc),
            client_ip=client_ip,
            user_id=user_id,
            event_type=event_type,
            threat_level=threat_level,
            details=details
        )
        
        self._security_events.append(event)
        
        # Keep only recent events (last 24 hours)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        self._security_events = [e for e in self._security_events if e.timestamp > cutoff_time]
        
        # Log event
        logger.warning(f"🚨 [SECURITY-EVENT] {event_type} | IP: {client_ip} | Threat: {threat_level.value} | Details: {details}")
    
    async def _update_threat_analysis(self, client_ip: str, user_id: Optional[str], violation_type: str):
        """Update threat analysis based on violations."""
        if client_ip in self._ip_behavior_analysis:
            self._ip_behavior_analysis[client_ip]["error_count"] += 1
        
        # Mark IP as suspicious after multiple violations
        if violation_type == "rate_limit_violation":
            violations = self._count_recent_events(client_ip, "rate_limit_exceeded", 3600)
            if violations >= 3:
                self._suspicious_ips.add(client_ip)
                logger.error(f"🚨 [SECURITY] IP {client_ip} marked as suspicious due to repeated rate limit violations")
    
    def _get_rate_limit_message(self, rule: RateLimitRule, threat_level: ThreatLevel) -> str:
        """Get appropriate rate limit error message."""
        if threat_level == ThreatLevel.CRITICAL:
            return "Access denied due to suspicious activity. Contact support if this is an error."
        elif threat_level == ThreatLevel.HIGH:
            return "Rate limit exceeded. Please try again later."
        else:
            return f"Rate limit exceeded for {rule.name}. Please try again later."
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        return request.client.host if request.client else 'unknown'
    
    async def get_security_metrics(self) -> Dict[str, Any]:
        """Get security and performance metrics."""
        current_time = datetime.now(timezone.utc)
        
        # Calculate metrics for last hour
        last_hour = current_time - timedelta(hours=1)
        recent_events = [e for e in self._security_events if e.timestamp > last_hour]
        
        return {
            "timestamp": current_time.isoformat(),
            "total_events": len(self._security_events),
            "recent_events": len(recent_events),
            "suspicious_ips": len(self._suspicious_ips),
            "threat_levels": {
                level.value: len([e for e in recent_events if e.threat_level == level])
                for level in ThreatLevel
            },
            "system_load": self._system_load,
            "error_rate": self._error_rate,
            "active_rate_limits": len(self._request_counts),
            "active_token_buckets": len(self._token_buckets)
        }

# Global instance
_enterprise_rate_limiter: Optional[EnterpriseRateLimiter] = None

def get_enterprise_rate_limiter() -> EnterpriseRateLimiter:
    """Get global enterprise rate limiter instance."""
    global _enterprise_rate_limiter
    if _enterprise_rate_limiter is None:
        _enterprise_rate_limiter = EnterpriseRateLimiter()
    return _enterprise_rate_limiter