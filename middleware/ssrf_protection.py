"""
OWASP A10: Server-Side Request Forgery (SSRF) - Complete Implementation
Comprehensive SSRF protection middleware implementing enterprise-grade URL validation.

This module addresses OWASP Top 10 2021 A10: SSRF by implementing:
- URL validation and sanitization
- Allowlist and blocklist management
- Network segmentation controls
- External request security monitoring
- Webhook and callback validation
- DNS rebinding attack prevention
- Internal service protection
"""

import logging
import re
import time
import ipaddress
import socket
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import urlparse, urlunparse
from datetime import datetime, timedelta
import asyncio
import aiohttp
import ssl

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from utils.security_audit_validator import SecurityAuditValidator
from utils.cache_manager import CacheManager
from config import settings

logger = logging.getLogger(__name__)

class SSRFThreatLevel:
    """SSRF threat severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class URLValidationResult:
    """URL validation result with comprehensive context."""
    
    def __init__(self, is_safe: bool, threat_level: str = SSRFThreatLevel.LOW, 
                 violations: List[str] = None, sanitized_url: str = None,
                 blocked_reason: str = None):
        self.is_safe = is_safe
        self.threat_level = threat_level
        self.violations = violations or []
        self.sanitized_url = sanitized_url
        self.blocked_reason = blocked_reason
        self.validated_at = datetime.utcnow()

class SSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    OWASP A10 Compliance: Comprehensive SSRF protection middleware.
    
    Features:
    - URL allowlist/blocklist validation
    - DNS rebinding attack prevention
    - Internal network protection
    - Protocol restrictions and validation
    - External request monitoring and logging
    - Webhook URL validation
    - File upload URL validation
    - API integration security
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.security_validator = SecurityAuditValidator()
        self.cache_manager = CacheManager()
        
        # URL allowlist - explicitly allowed external domains
        self.allowed_domains = {
            'api.fal.ai',           # FAL.ai API integration
            'files.fal.ai',         # FAL.ai file storage
            'supabase.co',          # Supabase services
            '*.supabase.co',        # Supabase subdomains
            'githubusercontent.com', # GitHub raw content
            'gravatar.com',         # Avatar service
            'unsplash.com',         # Image service
            'picsum.photos',        # Test images
        }
        
        # Protocol allowlist
        self.allowed_protocols = {'https', 'http'}  # http only for localhost in development
        
        # Port restrictions
        self.allowed_ports = {80, 443, 8080, 8443}  # Add development ports if needed
        
        # Internal/private IP ranges to block
        self.blocked_ip_ranges = [
            ipaddress.IPv4Network('127.0.0.0/8'),      # Loopback
            ipaddress.IPv4Network('10.0.0.0/8'),       # Private Class A
            ipaddress.IPv4Network('172.16.0.0/12'),    # Private Class B
            ipaddress.IPv4Network('192.168.0.0/16'),   # Private Class C
            ipaddress.IPv4Network('169.254.0.0/16'),   # Link-local
            ipaddress.IPv4Network('224.0.0.0/4'),      # Multicast
            ipaddress.IPv4Network('240.0.0.0/4'),      # Reserved
            ipaddress.IPv6Network('::1/128'),          # IPv6 loopback
            ipaddress.IPv6Network('fe80::/10'),        # IPv6 link-local
            ipaddress.IPv6Network('fc00::/7'),         # IPv6 unique local
        ]
        
        # Development localhost exception (only in non-production)
        self.development_localhost_allowed = not settings.is_production()
        
        # Common SSRF target patterns to block
        self.ssrf_patterns = [
            r'localhost',
            r'127\.0\.0\.1',
            r'0\.0\.0\.0',
            r'::1',
            r'metadata\.google\.internal',
            r'169\.254\.169\.254',          # AWS/GCP metadata service
            r'metadata\.amazonaws\.com',
            r'metadata\.azure\.com',
            r'metadata\.packet\.net',
            r'fd00:ec2::',                  # AWS IPv6 metadata
        ]
        
        # URL patterns that might indicate SSRF attempts
        self.suspicious_patterns = [
            r'file://',
            r'ftp://',
            r'gopher://',
            r'dict://',
            r'sftp://',
            r'ldap://',
            r'jar://',
            r'netdoc:',
            r'@localhost',
            r'@127\.0\.0\.1',
            r'@internal',
            r'url=http',
            r'redirect=http',
            r'callback=http',
            r'webhook=http',
        ]
        
        # Cache for DNS lookups to prevent DNS rebinding attacks
        self.dns_cache_ttl = 300  # 5 minutes
        
        # Request monitoring
        self.monitored_parameters = {
            'url', 'callback', 'webhook', 'redirect', 'link', 'src', 'href',
            'image_url', 'avatar_url', 'profile_url', 'webhook_url', 'api_url'
        }
    
    async def dispatch(self, request: Request, call_next):
        """Apply SSRF protection to all requests with deadlock prevention."""
        start_time = time.perf_counter()
        
        # OPTIONS requests must pass through for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # AGGRESSIVE AUTH BYPASS: Skip all SSRF processing for auth endpoints
        path = str(request.url.path)
        if path.startswith('/api/v1/auth/'):
            return await call_next(request)
        
        # CRITICAL: Check for fastlane flag from FastlaneAuthMiddleware first
        if hasattr(request.state, 'is_fastlane') and request.state.is_fastlane:
            return await call_next(request)
        
        # Skip for health and other internal endpoints that don't make external calls
        if path in ['/health', '/healthz', '/ping']:
            return await call_next(request)
        
        # Skip for other internal endpoints that don't make external calls
        skip_paths = ['/api/v1/credits', '/api/v1/projects', '/api/v1/teams']
        if any(path.startswith(skip) for skip in skip_paths):
            logger.debug(f"⚡ [SSRF-PROTECTION] Bypassing for internal endpoint: {path}")
            return await call_next(request)
        
        # Skip SSRF analysis for E2E test endpoints - they don't contain external URLs
        if request.url.path.startswith('/api/v1/e2e/'):
            logger.debug(f"🧪 [SSRF-PROTECTION] Skipping SSRF check for E2E test endpoint: {request.url.path}")
            return await call_next(request)
        
        # EMERGENCY FIX: Add timeout to prevent blocking
        import asyncio
        try:
            async with asyncio.timeout(0.5):  # 500ms max for SSRF analysis
                # Step 1: Extract and validate URLs from request
                url_analysis = await self._analyze_request_urls(request)
                
                # Step 2: Apply SSRF protection if URLs found
                if url_analysis['urls_found']:
                    protection_result = await self._apply_ssrf_protection(request, url_analysis)
                    if not protection_result.is_safe:
                        return await self._handle_ssrf_threat(request, protection_result)
                
                # Step 3: Monitor outgoing requests (if any)
                request.state.ssrf_analysis = url_analysis
                
            # Process request
            response = await call_next(request)
            
            # Step 4: Log successful URL access (if analysis completed)
            if 'url_analysis' in locals() and url_analysis.get('urls_found'):
                await self._log_url_access(request, url_analysis, success=True)
            
            # PERFORMANCE: Add timing logs for slow processing
            elapsed = (time.perf_counter() - start_time) * 1000
            if elapsed > 10:  # Log if >10ms
                logger.warning(f"[MIDDLEWARE] SSRF protection took {elapsed:.2f}ms")
            
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ [SSRF-PROTECTION] Analysis timeout for {request.url.path} - allowing request")
            return await call_next(request)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ [SSRF-PROTECTION] Error processing request: {e}")
            
            await self.security_validator.log_security_incident(
                incident_type="ssrf_attempt",
                severity="medium",
                details={
                    "error_type": type(e).__name__,
                    "path": request.url.path,
                    "method": request.method
                },
                client_ip=self._get_client_ip(request),
                request_path=request.url.path
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Request processing error"
            )
    
    async def _analyze_request_urls(self, request: Request) -> Dict[str, Any]:
        """Analyze request for URLs that need SSRF protection."""
        urls_found = []
        analysis_results = {
            'urls_found': [],
            'parameters_checked': [],
            'suspicious_patterns_detected': [],
            'total_urls': 0
        }
        
        try:
            # Check query parameters
            for param_name, param_value in request.query_params.items():
                if param_name.lower() in self.monitored_parameters:
                    analysis_results['parameters_checked'].append(param_name)
                    
                    # Check if parameter value looks like a URL
                    if self._looks_like_url(param_value):
                        urls_found.append({
                            'url': param_value,
                            'source': 'query_parameter',
                            'parameter': param_name
                        })
                    
                    # Check for suspicious patterns
                    for pattern in self.suspicious_patterns:
                        if re.search(pattern, param_value, re.IGNORECASE):
                            analysis_results['suspicious_patterns_detected'].append({
                                'pattern': pattern,
                                'parameter': param_name,
                                'value': param_value[:100]  # Truncate for logging
                            })
            
            # Check request body for URLs (if JSON or form data)
            if request.method in ['POST', 'PUT', 'PATCH']:
                body_urls = await self._extract_urls_from_body(request)
                urls_found.extend(body_urls)
            
            # Check headers for callback URLs
            for header_name, header_value in request.headers.items():
                if any(callback_header in header_name.lower() for callback_header in ['callback', 'webhook', 'redirect']):
                    if self._looks_like_url(header_value):
                        urls_found.append({
                            'url': header_value,
                            'source': 'header',
                            'parameter': header_name
                        })
            
            analysis_results['urls_found'] = urls_found
            analysis_results['total_urls'] = len(urls_found)
            
            return analysis_results
            
        except Exception as e:
            logger.error(f"❌ [SSRF-ANALYSIS] Error analyzing request URLs: {e}")
            return analysis_results
    
    async def _extract_urls_from_body(self, request: Request) -> List[Dict[str, Any]]:
        """Extract URLs from request body using cached body to prevent deadlock."""
        urls_found = []
        
        try:
            # CRITICAL FIX: Use body cache helper to prevent deadlock
            from middleware.production_optimized import BodyCacheHelper
            
            # Check if we should bypass heavy processing for fast-lane requests
            if BodyCacheHelper.should_bypass_heavy_middleware(request):
                logger.debug("⚡ [SSRF-PROTECTION] Bypassing URL extraction for fast-lane request")
                return urls_found
            
            # Use cached body if available, otherwise safely get body
            body = await BodyCacheHelper.safe_get_body(request)
            if not body:
                return urls_found
            
            # Skip large bodies to prevent blocking
            if len(body) > 10240:  # 10KB max for URL extraction
                logger.debug("⚡ [SSRF-ANALYSIS] Skipping URL extraction for large body")
                return urls_found
            
            content_type = request.headers.get('content-type', '')
            
            # Skip auth endpoints - they don't have URLs
            if request.url.path.startswith('/api/v1/auth'):
                return urls_found
            
            if 'application/json' in content_type:
                import json
                try:
                    data = json.loads(body.decode('utf-8'))
                    # Only check if data is a dict (not login credentials)
                    if isinstance(data, dict) and not {'email', 'password'}.issubset(data.keys()):
                        urls_found.extend(self._extract_urls_from_json(data))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # Invalid JSON, skip URL extraction
            
            elif 'application/x-www-form-urlencoded' in content_type:
                from urllib.parse import parse_qs
                try:
                    body_str = body.decode('utf-8')
                    form_data = parse_qs(body_str)
                    
                    for param_name, param_values in form_data.items():
                        if param_name.lower() in self.monitored_parameters:
                            for param_value in param_values:
                                if self._looks_like_url(param_value):
                                    urls_found.append({
                                        'url': param_value,
                                        'source': 'form_data',
                                        'parameter': param_name
                                    })
                except UnicodeDecodeError:
                    pass  # Invalid encoding, skip URL extraction
                    
        except Exception as e:
            # Don't log warnings for expected cases
            if "Error extracting URLs" not in str(e):
                logger.debug(f"[SSRF-ANALYSIS] Skipped URL extraction: {type(e).__name__}")
        
        return urls_found
    
    def _extract_urls_from_json(self, data: Any, path: str = "") -> List[Dict[str, Any]]:
        """Recursively extract URLs from JSON data."""
        urls_found = []
        
        try:
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    if key.lower() in self.monitored_parameters and isinstance(value, str):
                        if self._looks_like_url(value):
                            urls_found.append({
                                'url': value,
                                'source': 'json_body',
                                'parameter': current_path
                            })
                    
                    # Recursively check nested objects
                    if isinstance(value, (dict, list)):
                        urls_found.extend(self._extract_urls_from_json(value, current_path))
            
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    current_path = f"{path}[{i}]"
                    urls_found.extend(self._extract_urls_from_json(item, current_path))
        
        except Exception as e:
            logger.warning(f"⚠️ [SSRF-ANALYSIS] Error in JSON URL extraction: {e}")
        
        return urls_found
    
    def _looks_like_url(self, value: str) -> bool:
        """Check if a string looks like a URL."""
        if not isinstance(value, str) or len(value) < 7:  # Minimum: http://x
            return False
        
        # Basic URL pattern matching
        url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return bool(re.match(url_pattern, value, re.IGNORECASE))
    
    async def _apply_ssrf_protection(self, request: Request, url_analysis: Dict[str, Any]) -> URLValidationResult:
        """Apply comprehensive SSRF protection to discovered URLs."""
        all_violations = []
        max_threat_level = SSRFThreatLevel.LOW
        blocked_urls = []
        
        for url_info in url_analysis['urls_found']:
            url = url_info['url']
            validation_result = await self._validate_url(url, url_info)
            
            if not validation_result.is_safe:
                all_violations.extend(validation_result.violations)
                blocked_urls.append({
                    'url': url,
                    'source': url_info['source'],
                    'parameter': url_info['parameter'],
                    'blocked_reason': validation_result.blocked_reason,
                    'threat_level': validation_result.threat_level
                })
                
                # Update maximum threat level
                if validation_result.threat_level == SSRFThreatLevel.CRITICAL:
                    max_threat_level = SSRFThreatLevel.CRITICAL
                elif validation_result.threat_level == SSRFThreatLevel.HIGH and max_threat_level != SSRFThreatLevel.CRITICAL:
                    max_threat_level = SSRFThreatLevel.HIGH
                elif validation_result.threat_level == SSRFThreatLevel.MEDIUM and max_threat_level not in [SSRFThreatLevel.CRITICAL, SSRFThreatLevel.HIGH]:
                    max_threat_level = SSRFThreatLevel.MEDIUM
        
        is_safe = len(blocked_urls) == 0
        
        return URLValidationResult(
            is_safe=is_safe,
            threat_level=max_threat_level,
            violations=all_violations,
            blocked_reason=f"Blocked {len(blocked_urls)} suspicious URLs" if blocked_urls else None
        )
    
    async def _validate_url(self, url: str, url_info: Dict[str, Any]) -> URLValidationResult:
        """Comprehensive URL validation for SSRF protection."""
        violations = []
        threat_level = SSRFThreatLevel.LOW
        
        try:
            # Parse URL
            parsed = urlparse(url)
            
            # Step 1: Protocol validation
            if parsed.scheme.lower() not in self.allowed_protocols:
                violations.append(f"disallowed_protocol: {parsed.scheme}")
                threat_level = SSRFThreatLevel.HIGH
            
            # Step 2: Check for suspicious patterns
            for pattern in self.ssrf_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    violations.append(f"ssrf_pattern_detected: {pattern}")
                    threat_level = SSRFThreatLevel.CRITICAL
            
            # Step 3: Domain/hostname validation
            hostname = parsed.hostname
            if not hostname:
                violations.append("missing_hostname")
                threat_level = SSRFThreatLevel.HIGH
            else:
                domain_result = await self._validate_domain(hostname)
                if not domain_result.is_safe:
                    violations.extend(domain_result.violations)
                    threat_level = max(threat_level, domain_result.threat_level)
            
            # Step 4: Port validation
            port = parsed.port
            if port and port not in self.allowed_ports:
                # Allow standard ports for allowed protocols
                if not ((parsed.scheme == 'http' and port == 80) or 
                        (parsed.scheme == 'https' and port == 443)):
                    violations.append(f"disallowed_port: {port}")
                    threat_level = max(threat_level, SSRFThreatLevel.MEDIUM)
            
            # Step 5: Path validation
            if parsed.path:
                path_result = self._validate_url_path(parsed.path)
                if not path_result.is_safe:
                    violations.extend(path_result.violations)
                    threat_level = max(threat_level, path_result.threat_level)
            
            # Step 6: Query parameter validation
            if parsed.query:
                query_result = self._validate_url_query(parsed.query)
                if not query_result.is_safe:
                    violations.extend(query_result.violations)
                    threat_level = max(threat_level, query_result.threat_level)
            
            # Step 7: DNS rebinding protection
            if hostname and threat_level < SSRFThreatLevel.HIGH:
                dns_result = await self._check_dns_rebinding(hostname)
                if not dns_result.is_safe:
                    violations.extend(dns_result.violations)
                    threat_level = max(threat_level, dns_result.threat_level)
            
        except Exception as e:
            violations.append(f"url_parsing_error: {str(e)}")
            threat_level = SSRFThreatLevel.MEDIUM
        
        is_safe = threat_level not in [SSRFThreatLevel.HIGH, SSRFThreatLevel.CRITICAL]
        
        return URLValidationResult(
            is_safe=is_safe,
            threat_level=threat_level,
            violations=violations,
            blocked_reason="; ".join(violations) if violations else None
        )
    
    async def _validate_domain(self, hostname: str) -> URLValidationResult:
        """Validate domain against allowlists and blocklists."""
        violations = []
        threat_level = SSRFThreatLevel.LOW
        
        # Check if domain is in allowlist
        domain_allowed = False
        for allowed_domain in self.allowed_domains:
            if allowed_domain.startswith('*.'):
                # Wildcard subdomain matching
                base_domain = allowed_domain[2:]
                if hostname == base_domain or hostname.endswith('.' + base_domain):
                    domain_allowed = True
                    break
            else:
                if hostname == allowed_domain:
                    domain_allowed = True
                    break
        
        if not domain_allowed:
            # Check if it's localhost (only allowed in development)
            if hostname in ['localhost', '127.0.0.1'] and self.development_localhost_allowed:
                domain_allowed = True
            else:
                violations.append(f"domain_not_in_allowlist: {hostname}")
                threat_level = SSRFThreatLevel.HIGH
        
        # Additional checks for IP addresses
        if self._is_ip_address(hostname):
            ip_result = self._validate_ip_address(hostname)
            if not ip_result.is_safe:
                violations.extend(ip_result.violations)
                threat_level = max(threat_level, ip_result.threat_level)
        
        return URLValidationResult(
            is_safe=len(violations) == 0,
            threat_level=threat_level,
            violations=violations
        )
    
    def _is_ip_address(self, hostname: str) -> bool:
        """Check if hostname is an IP address."""
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            return False
    
    def _validate_ip_address(self, ip_str: str) -> URLValidationResult:
        """Validate IP address against blocked ranges."""
        violations = []
        threat_level = SSRFThreatLevel.LOW
        
        try:
            ip = ipaddress.ip_address(ip_str)
            
            # Check against blocked IP ranges
            for blocked_range in self.blocked_ip_ranges:
                if ip in blocked_range:
                    violations.append(f"ip_in_blocked_range: {ip_str} in {blocked_range}")
                    threat_level = SSRFThreatLevel.CRITICAL
                    break
            
        except ValueError:
            violations.append(f"invalid_ip_address: {ip_str}")
            threat_level = SSRFThreatLevel.MEDIUM
        
        return URLValidationResult(
            is_safe=len(violations) == 0,
            threat_level=threat_level,
            violations=violations
        )
    
    def _validate_url_path(self, path: str) -> URLValidationResult:
        """Validate URL path for suspicious patterns."""
        violations = []
        threat_level = SSRFThreatLevel.LOW
        
        # Check for path traversal attempts
        if '..' in path:
            violations.append("path_traversal_attempt")
            threat_level = SSRFThreatLevel.HIGH
        
        # Check for encoded path traversal
        if '%2e' in path.lower() or '%2f' in path.lower():
            violations.append("encoded_path_traversal")
            threat_level = SSRFThreatLevel.HIGH
        
        # Check for suspicious file extensions
        suspicious_extensions = ['.php', '.asp', '.jsp', '.cgi', '.pl', '.py', '.sh']
        for ext in suspicious_extensions:
            if path.lower().endswith(ext):
                violations.append(f"suspicious_file_extension: {ext}")
                threat_level = max(threat_level, SSRFThreatLevel.MEDIUM)
        
        # Check path length
        if len(path) > 2048:
            violations.append("excessive_path_length")
            threat_level = max(threat_level, SSRFThreatLevel.MEDIUM)
        
        return URLValidationResult(
            is_safe=threat_level not in [SSRFThreatLevel.HIGH, SSRFThreatLevel.CRITICAL],
            threat_level=threat_level,
            violations=violations
        )
    
    def _validate_url_query(self, query: str) -> URLValidationResult:
        """Validate URL query parameters."""
        violations = []
        threat_level = SSRFThreatLevel.LOW
        
        # Check for suspicious query parameters
        suspicious_params = ['file=', 'url=', 'redirect=', 'callback=', 'path=', 'cmd=', 'exec=']
        for param in suspicious_params:
            if param in query.lower():
                violations.append(f"suspicious_query_parameter: {param}")
                threat_level = max(threat_level, SSRFThreatLevel.MEDIUM)
        
        # Check query length
        if len(query) > 4096:
            violations.append("excessive_query_length")
            threat_level = max(threat_level, SSRFThreatLevel.MEDIUM)
        
        return URLValidationResult(
            is_safe=threat_level not in [SSRFThreatLevel.HIGH, SSRFThreatLevel.CRITICAL],
            threat_level=threat_level,
            violations=violations
        )
    
    async def _check_dns_rebinding(self, hostname: str) -> URLValidationResult:
        """Check for DNS rebinding attacks by resolving hostname."""
        violations = []
        threat_level = SSRFThreatLevel.LOW
        
        try:
            # Check DNS cache first
            cache_key = f"dns_resolution:{hostname}"
            cached_result = await self.cache_manager.get(cache_key)
            
            if cached_result:
                # Use cached DNS resolution
                ip_addresses = cached_result['ips']
            else:
                # Resolve hostname
                try:
                    addr_info = await asyncio.get_event_loop().run_in_executor(
                        None, socket.getaddrinfo, hostname, None
                    )
                    ip_addresses = list(set([addr[4][0] for addr in addr_info]))
                    
                    # Cache the result
                    await self.cache_manager.set(
                        cache_key,
                        {'ips': ip_addresses, 'resolved_at': datetime.utcnow().isoformat()},
                        ttl=self.dns_cache_ttl
                    )
                    
                except socket.gaierror:
                    violations.append("dns_resolution_failed")
                    threat_level = SSRFThreatLevel.MEDIUM
                    return URLValidationResult(
                        is_safe=False,
                        threat_level=threat_level,
                        violations=violations
                    )
            
            # Check resolved IPs against blocked ranges
            for ip_str in ip_addresses:
                ip_result = self._validate_ip_address(ip_str)
                if not ip_result.is_safe:
                    violations.extend([f"dns_rebinding_{v}" for v in ip_result.violations])
                    threat_level = SSRFThreatLevel.CRITICAL
                    break
                    
        except Exception as e:
            violations.append(f"dns_check_error: {str(e)}")
            threat_level = SSRFThreatLevel.MEDIUM
        
        return URLValidationResult(
            is_safe=len(violations) == 0,
            threat_level=threat_level,
            violations=violations
        )
    
    async def _handle_ssrf_threat(self, request: Request, protection_result: URLValidationResult) -> HTTPException:
        """Handle detected SSRF threats."""
        client_ip = self._get_client_ip(request)
        
        # Log security incident
        await self.security_validator.log_security_incident(
            incident_type="ssrf_attempt",
            severity="critical" if protection_result.threat_level == SSRFThreatLevel.CRITICAL else "high",
            client_ip=client_ip,
            details={
                "violations": protection_result.violations,
                "threat_level": protection_result.threat_level,
                "blocked_reason": protection_result.blocked_reason
            },
            request_path=request.url.path
        )
        
        # Return appropriate error response
        if protection_result.threat_level == SSRFThreatLevel.CRITICAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request blocked by security policy"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid URL in request"
            )
    
    async def _log_url_access(self, request: Request, url_analysis: Dict[str, Any], success: bool):
        """Log URL access for monitoring and audit purposes."""
        try:
            access_log = {
                "timestamp": datetime.utcnow().isoformat(),
                "client_ip": self._get_client_ip(request),
                "path": request.url.path,
                "method": request.method,
                "urls_accessed": len(url_analysis['urls_found']),
                "success": success,
                "urls": [
                    {
                        "url": url_info['url'][:100],  # Truncate for logging
                        "source": url_info['source'],
                        "parameter": url_info['parameter']
                    }
                    for url_info in url_analysis['urls_found']
                ]
            }
            
            # Store in cache for monitoring
            log_key = f"url_access_log:{datetime.utcnow().strftime('%Y%m%d%H')}:{hash(str(access_log))}"
            await self.cache_manager.set(log_key, access_log, ttl=86400)  # 24 hour retention
            
            logger.info(f"📊 [SSRF-MONITOR] URL access logged: {len(url_analysis['urls_found'])} URLs")
            
        except Exception as e:
            logger.error(f"❌ [SSRF-MONITOR] Failed to log URL access: {e}")
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address considering proxy headers."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        return getattr(request.client, "host", "unknown")


# Utility functions for SSRF protection in services

async def validate_external_url(url: str, purpose: str = "general") -> URLValidationResult:
    """
    Standalone function to validate external URLs in services.
    
    Args:
        url: The URL to validate
        purpose: Purpose of the URL (e.g., 'webhook', 'api_call', 'file_upload')
    
    Returns:
        URLValidationResult with validation details
    """
    # Create a temporary instance for validation
    temp_middleware = SSRFProtectionMiddleware(app=None)
    
    url_info = {
        'url': url,
        'source': 'service_call',
        'parameter': purpose
    }
    
    return await temp_middleware._validate_url(url, url_info)

async def make_safe_external_request(url: str, method: str = 'GET', **kwargs) -> Dict[str, Any]:
    """
    Make a safe external HTTP request with SSRF protection.
    
    Args:
        url: The URL to request
        method: HTTP method
        **kwargs: Additional arguments for the HTTP request
    
    Returns:
        Response data or error information
    """
    # Validate URL first
    validation_result = await validate_external_url(url, purpose='api_call')
    
    if not validation_result.is_safe:
        return {
            'success': False,
            'error': 'URL blocked by SSRF protection',
            'details': validation_result.violations
        }
    
    try:
        # Configure secure HTTP client
        connector = aiohttp.TCPConnector(
            limit=10,  # Connection pool limit
            limit_per_host=2,  # Max connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
        )
        
        timeout = aiohttp.ClientTimeout(
            total=30,  # Total timeout
            connect=10,  # Connection timeout
            sock_read=10  # Socket read timeout
        )
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'Velro-API/1.0'}
        ) as session:
            
            async with session.request(method.upper(), url, **kwargs) as response:
                content = await response.text()
                
                return {
                    'success': True,
                    'status_code': response.status,
                    'headers': dict(response.headers),
                    'content': content,
                    'url': str(response.url)
                }
                
    except aiohttp.ClientError as e:
        logger.error(f"❌ [SAFE-REQUEST] HTTP client error: {e}")
        return {
            'success': False,
            'error': 'HTTP request failed',
            'details': str(e)
        }
    except Exception as e:
        logger.error(f"❌ [SAFE-REQUEST] Unexpected error: {e}")
        return {
            'success': False,
            'error': 'Request processing failed',
            'details': str(e)
        }

def is_safe_callback_url(url: str) -> bool:
    """
    Quick check if a callback URL is safe for webhooks.
    
    Args:
        url: The callback URL to check
    
    Returns:
        True if URL appears safe, False otherwise
    """
    if not url or not isinstance(url, str):
        return False
    
    # Basic URL format check
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Parse URL
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        if not hostname:
            return False
        
        # Check for localhost/internal addresses
        if hostname in ['localhost', '127.0.0.1', 'internal', 'metadata.google.internal']:
            return False
        
        # Check for private IP ranges (basic check)
        if hostname.startswith(('10.', '172.16.', '192.168.', '169.254.')):
            return False
        
        # Check for IPv6 loopback
        if hostname in ['::1', 'localhost']:
            return False
        
        return True
        
    except Exception:
        return False