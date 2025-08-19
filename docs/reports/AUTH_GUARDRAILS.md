# 🛡️ Auth Performance Guardrails

## Automated Monitoring & Protection

### 1. Health Check Gates

#### Railway Health Checks
```yaml
# railway.json
{
  "healthcheck": {
    "path": "/health",
    "timeout": 5,
    "interval": 30,
    "max_retries": 3
  }
}
```

#### Deployment Validation
```bash
#!/bin/bash
# deploy-health-check.sh
URL="https://velro-backend-production.up.railway.app"

# Test health endpoint
HEALTH=$(curl -s -w "%{http_code}" $URL/health -o /dev/null)
if [ "$HEALTH" != "200" ]; then
  echo "❌ Health check failed: $HEALTH"
  exit 1
fi

# Test auth ping
AUTH_TIME=$(curl -s -w "%{time_total}" -X GET $URL/api/v1/auth/ping -o /dev/null)
if (( $(echo "$AUTH_TIME > 1.5" | bc -l) )); then
  echo "❌ Auth ping too slow: ${AUTH_TIME}s"
  exit 1
fi

echo "✅ Health checks passed"
```

### 2. Performance Monitoring

#### Continuous Benchmarking
```python
# monitor_auth_performance.py
import asyncio
import aiohttp
import statistics
from datetime import datetime

async def monitor_auth_endpoint():
    """Monitor auth endpoint p95 performance"""
    url = "https://velro-backend-production.up.railway.app/api/v1/auth/login"
    
    async with aiohttp.ClientSession() as session:
        times = []
        for _ in range(20):
            start = datetime.now()
            async with session.post(url, json={
                "email": "monitor@test.com",
                "password": "MonitorTest123"
            }) as response:
                elapsed = (datetime.now() - start).total_seconds()
                times.append(elapsed)
            await asyncio.sleep(1)
        
        p95 = statistics.quantiles(times, n=20)[18]
        
        if p95 > 1.5:
            print(f"⚠️ ALERT: Auth p95 degraded to {p95:.2f}s")
            # Trigger rollback or alert
        elif p95 > 1.0:
            print(f"⚠️ WARNING: Auth p95 at {p95:.2f}s")
        else:
            print(f"✅ Auth p95 healthy at {p95:.2f}s")

# Run every 5 minutes
asyncio.run(monitor_auth_endpoint())
```

### 3. Rollback Triggers

#### Automatic Rollback Conditions
1. **Auth p95 > 2.0s** for 3 consecutive checks
2. **Health endpoint timeout** (>5s)
3. **Deployment fails health check** 3 times
4. **Error rate > 10%** on auth endpoints

#### Rollback Script
```bash
#!/bin/bash
# rollback-to-stable.sh

STABLE_COMMIT="a17042f"  # Last known good
PROJECT_ID="a6d6ccff-c1f6-425d-95b7-5ffcf4e02c16"
SERVICE_ID="2b0320e7-d782-478a-967a-7619f608066b"
ENV_ID="f74bbed0-82ed-4e58-8136-0dc65563b295"

echo "🔄 Rolling back to stable version..."

# Trigger deployment of stable commit
railway deployment trigger \
  --project $PROJECT_ID \
  --service $SERVICE_ID \
  --environment $ENV_ID \
  --commit $STABLE_COMMIT

echo "✅ Rollback initiated to commit $STABLE_COMMIT"
```

### 4. Middleware Bypass Verification

#### Test Fastlane Effectiveness
```python
# test_fastlane_bypass.py
import requests
import time

def test_middleware_bypass():
    """Verify fastlane bypass is working"""
    
    # Test auth endpoint (should bypass)
    start = time.time()
    r = requests.post(
        "https://velro-backend-production.up.railway.app/api/v1/auth/login",
        json={"email": "test@test.com", "password": "test"}
    )
    auth_time = time.time() - start
    
    # Check Server-Timing header
    timing = r.headers.get('Server-Timing', '')
    
    if 'middleware' in timing and 'ms=0' not in timing:
        print("⚠️ WARNING: Middleware not fully bypassed")
    
    if auth_time > 1.5:
        print(f"❌ FAIL: Auth took {auth_time:.2f}s")
        return False
    
    print(f"✅ PASS: Auth completed in {auth_time:.2f}s")
    return True

test_middleware_bypass()
```

### 5. Environment Variable Guards

#### Required Production Variables
```bash
# .env.production
DISABLE_HEAVY_MIDDLEWARE=false  # Set true during incidents
ENABLE_FASTLANE_AUTH=true       # Must be true for performance
MAX_AUTH_TIMEOUT=1500            # 1.5s max
RAILWAY_DEPLOYMENT_ID=<auto>    # Auto-detected

# Supabase (verified correct project)
SUPABASE_URL=https://ltspnsduziplpuqxczvy.supabase.co
SUPABASE_ANON_KEY=<verified>
SUPABASE_SERVICE_ROLE_KEY=<verified>

# Redis (internal URL for performance)
REDIS_URL=redis://velro-redis.railway.internal:6379
```

### 6. CI/CD Pipeline Guards

#### GitHub Actions Workflow
```yaml
# .github/workflows/deploy-guard.yml
name: Deployment Guard

on:
  push:
    branches: [main]

jobs:
  performance-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Test Local Performance
        run: |
          docker build -t velro-backend .
          docker run -d -p 8000:8000 velro-backend
          sleep 10
          
          # Run performance test
          python performance_benchmark.py --local
          
      - name: Check p95 Threshold
        run: |
          P95=$(cat benchmark_results.json | jq '.auth_login.p95')
          if (( $(echo "$P95 > 1.5" | bc -l) )); then
            echo "❌ p95 exceeds 1.5s threshold: ${P95}s"
            exit 1
          fi
          
      - name: Deploy if Passed
        if: success()
        run: |
          echo "✅ Performance gates passed, deploying..."
```

### 7. Incident Response Playbook

#### Performance Degradation Response

**Level 1: Warning (p95 > 1.0s)**
1. Check Railway deployment logs
2. Verify Supabase status
3. Monitor for 15 minutes

**Level 2: Alert (p95 > 1.5s)**
1. Enable `DISABLE_HEAVY_MIDDLEWARE=true`
2. Restart service
3. Check middleware order
4. Verify fastlane bypass

**Level 3: Critical (p95 > 2.0s or timeouts)**
1. Immediate rollback to stable version
2. Enable maintenance mode
3. Investigate root cause
4. Test fix in staging

### 8. Monitoring Dashboard

#### Key Metrics to Track
- **Auth p50, p95, p99** response times
- **Health check success rate**
- **Middleware bypass effectiveness**
- **Server-Timing header values**
- **Concurrent request handling**
- **Error rates by endpoint**

#### Alert Thresholds
```json
{
  "alerts": {
    "auth_p95": {
      "warning": 1000,    // 1.0s
      "critical": 1500    // 1.5s
    },
    "health_check": {
      "warning": 300,     // 300ms
      "critical": 1000    // 1.0s
    },
    "error_rate": {
      "warning": 0.05,    // 5%
      "critical": 0.10    // 10%
    }
  }
}
```

### 9. Version Endpoint

#### Implementation
```python
# routers/system.py
@router.get("/__version")
async def get_version():
    """Version endpoint for deployment verification"""
    return {
        "version": "1.1.3",
        "commit": os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown"),
        "deployed": os.getenv("RAILWAY_DEPLOYMENT_ID", "local"),
        "timestamp": datetime.utcnow().isoformat(),
        "auth_optimized": True,
        "fastlane_enabled": True
    }
```

### 10. Testing Checklist

#### Pre-Deployment
- [ ] Local auth benchmark < 500ms
- [ ] Middleware bypass verified
- [ ] Health checks respond < 100ms
- [ ] All time imports present
- [ ] Railway infrastructure filtering active

#### Post-Deployment  
- [ ] Health endpoint < 300ms
- [ ] Auth ping < 500ms
- [ ] Auth login p95 < 1.5s
- [ ] Server-Timing headers present
- [ ] No 500 errors in first 5 minutes
- [ ] Logs not flooding (< 100/sec)

#### Weekly Validation
- [ ] Run full performance benchmark
- [ ] Review p95 trends
- [ ] Check for middleware regression
- [ ] Validate Supabase keys
- [ ] Test rollback procedure

---

## Quick Commands

### Check Current Performance
```bash
curl -s -w "\nTime: %{time_total}s\n" \
  https://velro-backend-production.up.railway.app/api/v1/auth/ping
```

### Monitor Auth p95
```bash
python performance_benchmark.py --endpoint auth --samples 20
```

### Emergency Rollback
```bash
./rollback-to-stable.sh
```

### Enable Lightweight Mode
```bash
railway variables set DISABLE_HEAVY_MIDDLEWARE=true
railway service restart
```

---

*These guardrails ensure auth performance stays within target and provide rapid response to degradation.*