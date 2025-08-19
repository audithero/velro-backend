# 🔄 Rollback Notes & Recovery Procedures

## Quick Rollback Commands

### Immediate Rollback to Stable
```bash
# Last known good deployment
git checkout a17042f
git push --force origin main
```

### Railway CLI Rollback
```bash
railway deployment rollback 92430c50-fd96-48fc-84eb-38336cd84cfa
```

## Stable Deployment Points

### Git Commits (Chronological)
1. **e6308ac** - Pre-repair baseline (failed deployments)
2. **c1b1420** - Health check bypass implementation
3. **a17042f** - All middleware fixes applied ✅ **STABLE**

### Railway Deployment IDs
- **Failed**: 7b87453b-40bb-45cc-b722-a1dbd17feba8
- **Success**: 92430c50-fd96-48fc-84eb-38336cd84cfa ✅ **CURRENT**

## Common Issues & Recovery

### 1. Middleware Time Import Errors
**Symptom**: `NameError: name 'time' is not defined`

**Fix**:
```python
# Add to top of middleware file
import time
```

**Affected Files**:
- middleware/secure_design.py
- middleware/security_enhanced.py
- middleware/ssrf_protection.py

### 2. Health Check Timeouts
**Symptom**: Deployment fails with health check timeout

**Fix**:
```python
# main.py - Add BEFORE middleware
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### 3. SecurityAuditValidator Log Flooding
**Symptom**: Railway 500 logs/sec limit hit

**Fix**:
```python
# utils/security_audit_validator.py
if self._is_railway_infrastructure(ip):
    return  # Skip logging
```

### 4. Auth Endpoint Slow/Timing Out
**Symptom**: Auth takes >1.5s or times out

**Fix**:
1. Verify fastlane bypass active
2. Check Supabase keys correct
3. Enable lightweight mode:
```bash
railway variables set DISABLE_HEAVY_MIDDLEWARE=true
```

## Environment Variable Rollback

### Critical Variables to Preserve
```bash
# Save current config
railway variables list > vars_backup.txt

# Required for auth performance
ENABLE_FASTLANE_AUTH=true
SUPABASE_URL=https://ltspnsduziplpuqxczvy.supabase.co
REDIS_URL=redis://velro-redis.railway.internal:6379
```

### Emergency Lightweight Mode
```bash
# Disable all heavy middleware
railway variables set DISABLE_HEAVY_MIDDLEWARE=true
railway service restart
```

## Rollback Decision Tree

```
Performance Issue Detected
├── p95 > 1.5s?
│   ├── Yes → Check middleware bypass
│   │   ├── Not working → Rollback to a17042f
│   │   └── Working → Check Supabase
│   └── No → Monitor for 15 min
│
├── Health check failing?
│   ├── Yes → Enable lightweight mode
│   │   ├── Still failing → Rollback
│   │   └── Fixed → Investigate middleware
│   └── No → Continue monitoring
│
└── Deployment failing?
    ├── Build error → Check git commit
    ├── Runtime error → Check logs
    └── Health timeout → Apply health fix
```

## Recovery Procedures

### Procedure A: Performance Degradation
1. **Identify**: Auth p95 > 1.5s
2. **Mitigate**: Enable DISABLE_HEAVY_MIDDLEWARE
3. **Diagnose**: Check Server-Timing headers
4. **Fix**: Apply specific middleware fix
5. **Verify**: Run performance benchmark
6. **Document**: Update this file

### Procedure B: Deployment Failure
1. **Stop**: Cancel deployment
2. **Rollback**: Deploy last good commit
3. **Analyze**: Check deployment logs
4. **Fix**: Apply targeted fix
5. **Test**: Local deployment first
6. **Deploy**: With monitoring

### Procedure C: Complete Outage
1. **Rollback**: Immediate to stable version
2. **Communicate**: Status page update
3. **Enable**: Maintenance mode
4. **Debug**: In staging environment
5. **Fix**: With comprehensive testing
6. **Deploy**: Gradual rollout

## Testing Before Rollback

### Quick Health Test
```bash
#!/bin/bash
URL="https://velro-backend-production.up.railway.app"

echo "Testing deployment health..."
curl -s -o /dev/null -w "Health: %{http_code} in %{time_total}s\n" $URL/health
curl -s -o /dev/null -w "Auth Ping: %{http_code} in %{time_total}s\n" $URL/api/v1/auth/ping
```

### Performance Validation
```python
# Run from repo root
python performance_benchmark.py --quick
```

## Rollback Verification

### Post-Rollback Checklist
- [ ] Deployment status GREEN
- [ ] Health endpoint < 300ms
- [ ] Auth endpoint < 1.5s p95
- [ ] No error logs in first 5 min
- [ ] Server-Timing headers present
- [ ] Monitoring alerts cleared

### Verification Commands
```bash
# Check deployment status
railway deployment status

# Test endpoints
./test-auth-endpoints.sh

# Monitor logs
railway logs --tail 100
```

## Historical Issues Log

### 2025-01-12 - Middleware Cascade Failure
- **Issue**: Multiple middleware missing time imports
- **Impact**: 12 failed deployments
- **Resolution**: Fixed imports in 4 files
- **Prevention**: Added import checker to CI

### 2025-01-12 - Health Check Blocking
- **Issue**: Middleware processing health checks
- **Impact**: Deployment timeouts
- **Resolution**: Pre-middleware health routes
- **Prevention**: Health bypass pattern

### 2025-01-12 - Log Flooding
- **Issue**: SecurityAuditValidator 500 logs/sec
- **Impact**: Dropped logs, failed deploys
- **Resolution**: Railway IP filtering
- **Prevention**: Infrastructure allowlist

## Contact & Escalation

### Performance Issues
1. Check this document first
2. Run performance benchmark
3. Check Railway status page
4. Review recent commits

### Deployment Issues
1. Check deployment logs
2. Verify environment variables
3. Test locally with Docker
4. Rollback if needed

### Emergency Contacts
- Railway Support: via dashboard
- Supabase Status: status.supabase.com
- GitHub Issues: repo/issues

---

## Quick Reference Card

```bash
# Current stable version
STABLE_COMMIT="a17042f"
STABLE_DEPLOYMENT="92430c50-fd96-48fc-84eb-38336cd84cfa"

# Rollback command
git checkout $STABLE_COMMIT && git push --force

# Enable lightweight mode
railway variables set DISABLE_HEAVY_MIDDLEWARE=true

# Test performance
curl -w "Time: %{time_total}s\n" $URL/api/v1/auth/ping

# Check logs
railway logs --tail 50 | grep ERROR
```

---

*Last Updated: 2025-01-12*  
*Stable Version: 1.1.3*  
*Recovery Time Objective: < 5 minutes*