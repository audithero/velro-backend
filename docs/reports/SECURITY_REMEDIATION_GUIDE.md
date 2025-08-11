# SECURITY REMEDIATION GUIDE
## Critical Security Fixes for Production Deployment

**Priority:** 🚨 IMMEDIATE ACTION REQUIRED  
**Target:** Fix critical security blockers before production go-live  
**Estimated Time:** 2-3 days for critical fixes

---

## CRITICAL FIXES CHECKLIST

### ✅ Step 1: Production Environment Configuration

**File to modify:** `.env` (create for production)

```bash
# Production Environment Configuration
ENVIRONMENT=production
DEBUG=false
DEVELOPMENT_MODE=false
EMERGENCY_AUTH_MODE=false

# JWT Security - CRITICAL: Generate strong secret
JWT_SECRET=your-64-character-minimum-cryptographically-secure-secret-here-change-this
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
JWT_REFRESH_EXPIRE_HOURS=168
JWT_BLACKLIST_ENABLED=true
JWT_REQUIRE_HTTPS=true

# Password Security
PASSWORD_HASH_ROUNDS=12
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15

# Rate Limiting (Production Values)
RATE_LIMIT_PER_MINUTE=30
GENERATION_RATE_LIMIT=10

# CORS Security (Replace with your actual domain)
ALLOWED_ORIGINS=https://your-production-frontend-domain.com

# Security Headers
STRICT_TRANSPORT_SECURITY=true
CONTENT_SECURITY_POLICY=true
```

**Generate Strong JWT Secret:**
```bash
# Use this command to generate a secure JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

### ✅ Step 2: Remove Development Authentication Bypasses

**Files to modify:**
- `middleware/auth.py` (lines 94-119, 122-343)
- `routers/auth_production.py`
- `routers/debug_auth.py`

**1. Update `middleware/auth.py`:**

```python
async def _verify_token(self, token: str) -> UserResponse:
    """Verify JWT token with Supabase and return user - PRODUCTION SECURE."""
    try:
        # Check cache first for token validation (short TTL for security)
        cache_key = f"auth_token:{hashlib.md5(token.encode()).hexdigest()}"
        cached_user = await cache_manager.get(cache_key, CacheLevel.L1_MEMORY)
        if cached_user is not None:
            logger.debug("🚀 [AUTH-MIDDLEWARE] Cache hit for token validation")
            return cached_user
        
        # SECURITY: Block all development tokens in production
        if settings.is_production():
            if token.startswith(("mock_token_", "dev_token_", "test_token_", "supabase_token_")):
                logger.error(f"🚨 [SECURITY-VIOLATION] Development token blocked in production")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed"
                )
        
        # PRODUCTION-ONLY: Only allow development tokens in strict development mode
        if token.startswith("mock_token_") or token.startswith("dev_token_"):
            if not (settings.development_mode and settings.debug and not settings.is_production()):
                logger.error(f"🚨 [SECURITY-VIOLATION] Development token used outside development mode")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed"
                )
            # Allow only in development - remove this entire section for production
            # ... (existing mock token handling)
        
        # === PRODUCTION JWT Token Verification ===
        try:
            # Use secure JWT verification
            payload = JWTSecurity.verify_token(token, "access_token")
            user_id = payload.get("sub")
            email = payload.get("email")
            
            if user_id and email:
                logger.info(f"✅ [AUTH-MIDDLEWARE] JWT token verification successful for user {user_id}")
                
                # Get enhanced profile from database
                # ... (rest of existing JWT handling)
                
        except SecurityError as jwt_error:
            logger.info(f"🔍 [AUTH-MIDDLEWARE] JWT verification failed, trying Supabase: {jwt_error}")
            # Fall through to Supabase verification
        
        # === Fallback: Supabase JWT Token Verification ===
        # ... (existing Supabase verification code)
```

**2. Disable debug authentication endpoints in production:**

Add to `main.py`:
```python
# Conditional router inclusion based on environment
if not settings.is_production():
    app.include_router(debug_router, prefix="/api/v1/debug", tags=["debug"])
    app.include_router(debug_auth_router, prefix="/api/v1/debug/auth", tags=["debug-auth"])
else:
    logger.info("🔒 [SECURITY] Debug endpoints disabled in production")
```

### ✅ Step 3: Harden Kong Gateway Configuration

**File to modify:** `kong-declarative-config.yml`

```yaml
# Updated CORS Plugin - SECURE
plugins:
  - name: cors
    config:
      origins:
        - "https://your-production-frontend-domain.com"  # REPLACE WITH ACTUAL DOMAIN
        # Remove wildcard "*" entirely
      methods:
        - "GET"
        - "POST"
        - "PUT"
        - "DELETE"
        - "OPTIONS"
        - "HEAD"
        - "PATCH"
      headers:
        - "Accept"
        - "Accept-Language"
        - "Content-Language"
        - "Content-Type"
        - "Authorization"
        - "X-Requested-With"
        - "X-API-Key"
        - "X-User-ID"
      exposed_headers:
        - "X-Kong-Request-ID"
        - "X-RateLimit-Limit"
        - "X-RateLimit-Remaining"
        - "X-Kong-Proxy"
      credentials: true
      max_age: 3600
      
  # Enhanced Rate Limiting for Production
  - name: rate-limiting
    config:
      minute: 30    # Reduced from higher limits
      hour: 1000
      policy: "local"
      fault_tolerant: true
      hide_client_headers: false
      
  # IP Restriction (Optional - for high-security environments)
  - name: ip-restriction
    config:
      allow:
        - "0.0.0.0/0"  # Allow all for now, restrict as needed
      # deny: []  # Add problematic IPs here
```

### ✅ Step 4: Strengthen Security Headers

**File to modify:** `middleware/security.py` (update `_add_security_headers` method)

```python
def _add_security_headers(self, response: Response) -> Response:
    """Add comprehensive security headers for production."""
    headers = settings.get_security_headers()
    
    # Add all configured security headers
    for header, value in headers.items():
        if value is not None:
            response.headers[header] = value
    
    # Production-grade security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(self), sync-xhr=()"
    
    # Cache control for sensitive data
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    # Content Security Policy for production
    if settings.is_production():
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  # Be more restrictive if possible
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://api.fal.ai https://*.supabase.co wss://*.supabase.co; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "upgrade-insecure-requests;"
        )
        response.headers["Content-Security-Policy"] = csp_policy
        
        # HSTS for HTTPS enforcement
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    
    return response
```

### ✅ Step 5: Production Configuration Validation

**File to modify:** `config.py` (update validation method)

```python
def validate_production_security(self) -> None:
    """Validate that security configurations are production-ready."""
    if self.is_production():
        # Critical security validations for production
        if self.debug:
            raise SecurityError("CRITICAL: DEBUG mode must be disabled in production")
        
        if self.development_mode:
            raise SecurityError("CRITICAL: DEVELOPMENT_MODE must be disabled in production")
        
        if self.emergency_auth_mode:
            raise SecurityError("CRITICAL: EMERGENCY_AUTH_MODE must be disabled in production")
        
        # Validate JWT secret strength (minimum 64 characters for production)
        if len(self.jwt_secret) < 64:
            raise SecurityError("CRITICAL: JWT_SECRET must be at least 64 characters in production")
        
        # Check for default/weak secrets
        weak_secrets = ["your-secret-key-change-in-production", "test", "dev", "debug", "change-this"]
        if any(weak in self.jwt_secret.lower() for weak in weak_secrets):
            raise SecurityError("CRITICAL: Weak or default JWT secret detected in production")
        
        # Ensure HTTPS enforcement
        if not self.jwt_require_https:
            raise SecurityError("CRITICAL: JWT_REQUIRE_HTTPS must be enabled in production")
        
        # Validate CORS origins don't include wildcards
        if "*" in self.cors_origins:
            raise SecurityError("CRITICAL: Wildcard CORS origins not allowed in production")
        
        # Validate rate limits are reasonable for production
        if self.rate_limit_per_minute > 60:
            logger.warning("⚠️ [SECURITY] Rate limits may be too permissive for production")
        
        logger.info("✅ [SECURITY] Production security validation passed")
```

### ✅ Step 6: Database Security Hardening

**File to create:** `migrations/012_production_security_hardening.sql`

```sql
-- Production Security Hardening Migration
-- Ensures all RLS policies are optimal for production

-- Audit and strengthen existing RLS policies
-- Add performance indexes for security queries
CREATE INDEX IF NOT EXISTS idx_users_auth_lookup ON public.users(id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_team_members_auth_check ON public.team_members(user_id, team_id, is_active);
CREATE INDEX IF NOT EXISTS idx_projects_security_check ON public.projects(user_id, visibility);

-- Add audit logging trigger for security events
CREATE OR REPLACE FUNCTION log_security_events()
RETURNS TRIGGER AS $$
BEGIN
    -- Log critical security events
    IF TG_OP = 'DELETE' AND TG_TABLE_NAME IN ('users', 'team_members', 'projects') THEN
        INSERT INTO audit_log (table_name, operation, old_data, user_id, timestamp)
        VALUES (TG_TABLE_NAME, TG_OP, row_to_json(OLD), auth.uid(), NOW());
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Apply audit triggers to critical tables
CREATE TRIGGER audit_users_security 
    AFTER DELETE ON public.users
    FOR EACH ROW EXECUTE FUNCTION log_security_events();

CREATE TRIGGER audit_team_members_security
    AFTER DELETE ON public.team_members  
    FOR EACH ROW EXECUTE FUNCTION log_security_events();
```

### ✅ Step 7: Error Handling Security

**File to modify:** `main.py` (add production error handler)

```python
from fastapi import HTTPException
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def production_exception_handler(request: Request, exc: Exception):
    """Production-safe error handling that prevents information disclosure."""
    
    if settings.is_production():
        # Log the full error for debugging (secure logs only)
        logger.error(f"🚨 [PRODUCTION-ERROR] {request.method} {request.url.path}: {exc}", 
                    extra={"request_id": request.headers.get("X-Kong-Request-ID")})
        
        # Return generic error to prevent information disclosure
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request.headers.get("X-Kong-Request-ID"),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    else:
        # Development: show detailed errors
        return JSONResponse(
            status_code=500,
            content={
                "error": str(exc),
                "type": type(exc).__name__,
                "request_id": request.headers.get("X-Kong-Request-ID")
            }
        )
```

---

## DEPLOYMENT VERIFICATION CHECKLIST

After implementing all fixes, verify with this checklist:

### Environment Configuration
- [ ] `ENVIRONMENT=production` set
- [ ] `DEBUG=false` confirmed
- [ ] `JWT_SECRET` is 64+ characters and cryptographically secure
- [ ] `DEVELOPMENT_MODE=false` verified
- [ ] `EMERGENCY_AUTH_MODE=false` confirmed

### Authentication Security
- [ ] No mock tokens accepted in production
- [ ] JWT signature verification working
- [ ] Token expiration enforced
- [ ] Refresh token rotation implemented
- [ ] Session timeout configured

### API Security
- [ ] All debug endpoints disabled
- [ ] Rate limiting active and tested
- [ ] CORS restricted to production domains
- [ ] Security headers present in responses
- [ ] Input validation comprehensive

### Database Security
- [ ] RLS policies active on all tables
- [ ] Service key usage properly isolated
- [ ] Audit logging functional
- [ ] Performance indexes created

### Kong Gateway
- [ ] CORS wildcard removed
- [ ] Rate limits appropriate for production load
- [ ] API key authentication required
- [ ] Request size limits enforced

---

## SECURITY TESTING COMMANDS

Run these commands to verify fixes:

```bash
# 1. Test production configuration
python3 -c "from config import settings; settings.validate_production_security(); print('✅ Production config valid')"

# 2. Test JWT security
python3 -c "from utils.security import JWTSecurity; print('JWT secret length:', len(settings.jwt_secret))"

# 3. Test authentication endpoints
curl -X POST https://your-backend-url/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"wrongpass"}' \
  -v  # Should return 401, not 500

# 4. Test rate limiting
for i in {1..10}; do curl -X POST https://your-backend-url/api/v1/auth/login -d '{}' & done
# Should show rate limiting after several requests

# 5. Test security headers
curl -I https://your-backend-url/
# Should include X-Content-Type-Options, X-Frame-Options, CSP, etc.

# 6. Test CORS
curl -H "Origin: https://malicious.com" -I https://your-backend-url/
# Should NOT return Access-Control-Allow-Origin for unauthorized domains
```

---

## POST-DEPLOYMENT MONITORING

Set up these security monitoring alerts:

1. **Authentication Failures**
   - Alert on >10 failed auth attempts per minute
   - Monitor for development token usage attempts

2. **Rate Limiting Triggers**
   - Track IPs hitting rate limits
   - Alert on unusual patterns

3. **Error Rate Monitoring**
   - Monitor 5xx error rates
   - Alert on security-related exceptions

4. **Database Security**
   - Monitor RLS policy violations
   - Track unauthorized access attempts

---

## EMERGENCY ROLLBACK PLAN

If security issues are discovered post-deployment:

1. **Immediate Actions:**
   ```bash
   # Emergency: Enable maintenance mode
   export MAINTENANCE_MODE=true
   
   # Emergency: Invalidate all JWT tokens
   export JWT_SECRET=new-emergency-secret
   
   # Emergency: Block suspicious IPs via Kong
   # Update Kong configuration with IP restrictions
   ```

2. **Investigation Steps:**
   - Review security logs
   - Check for data exposure
   - Identify attack vectors
   - Document incident timeline

3. **Recovery Actions:**
   - Apply security patches
   - Reset compromised credentials
   - Notify affected users if necessary
   - Conduct post-incident review

---

## FINAL VERIFICATION

Before declaring production-ready:

1. ✅ All 7 critical security blockers resolved
2. ✅ Security test suite passes 100%
3. ✅ Production environment validated
4. ✅ Third-party security scan completed
5. ✅ Security monitoring active
6. ✅ Incident response plan tested

**Status After Fixes:** Ready for security re-audit and production deployment approval.

---

**Contact Security Team for:**
- Production JWT secret generation
- Final security audit scheduling  
- Penetration testing coordination
- Production deployment approval