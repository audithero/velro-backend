# Railway Service Retirement Plan

**Generated**: 2025-08-11T15:52:00Z  
**Project**: velro-production (a6d6ccff-c1f6-425d-95b7-5ffcf4e02c16)

## Retirement Strategy

### Services to Retire Safely

#### 1. velro-backend-fresh
- **Service ID**: `281a659e-2b7a-40f4-89df-0fee93163551`
- **Current Status**: FAILED deployment
- **Domain**: `velro-backend-fresh-production.up.railway.app`
- **Retirement Risk**: **LOW** - Already failing, no traffic
- **Action**: Can be deleted immediately after final verification

#### 2. velro-backend-working  
- **Service ID**: `9d567f51-388f-43c6-b039-b30c92faa614`
- **Current Status**: SUCCESS but temporary inline code
- **Domain**: `velro-backend-working-production.up.railway.app`
- **Retirement Risk**: **HIGH** - Currently functional, may have dependencies
- **Action**: Retire ONLY after canonical backend is fully working

## Pre-Retirement Checklist

### ✅ Completed Steps
- [x] Environment variable snapshots created
- [x] Service configurations documented
- [x] Canonical services updated with merged environment variables
- [x] Supabase keys standardized across all services

### ⏳ Pending Prerequisites  
- [ ] Canonical backend service successfully deployed
- [ ] All canonical services health-checked and verified
- [ ] Frontend confirmed calling canonical backend (not working backend)
- [ ] Kong Gateway fully operational
- [ ] End-to-end API flow testing completed

## Retirement Sequence

### Phase 1: Immediate Retirement (Safe)
**Target**: `velro-backend-fresh` 
**Reason**: Already failing, no risk

```bash
# Safe to execute immediately
railway service delete --service-id 281a659e-2b7a-40f4-89df-0fee93163551
```

### Phase 2: Conditional Retirement (After Backend Fix)
**Target**: `velro-backend-working`
**Condition**: Canonical backend must be working first

```bash
# Execute ONLY after canonical backend is verified working
railway service delete --service-id 9d567f51-388f-43c6-b039-b30c92faa614
```

## Verification Requirements Before Retirement

### 1. Backend Service Verification
```bash
# Must return 200 OK
curl https://velro-backend-production.up.railway.app/health

# Must return valid auth response  
curl https://velro-backend-production.up.railway.app/api/v1/auth/ping
```

### 2. Frontend-Backend Integration
```bash
# Frontend must successfully call canonical backend
# Check Network tab in frontend for API calls to:
# https://velro-backend-production.up.railway.app/api/v1/*
```

### 3. Kong Gateway Operational
```bash
# Kong must be responding to health checks
curl https://velro-kong-gateway-production.up.railway.app/health

# Kong must handle FAL proxy requests (not backend API)
curl https://velro-kong-gateway-production.up.railway.app/fal/status
```

## Risk Mitigation

### Rollback Plan
If retirement causes issues:

1. **Immediate rollback** available by restoring `velro-backend-working`
2. **Environment variables** can be restored from snapshots in `docs/railway-env-snapshots/`
3. **Service configurations** documented in `docs/runtime-config-map.md`

### Monitoring During Retirement
1. Watch frontend error rates
2. Monitor backend API response times  
3. Check Kong Gateway metrics
4. Verify no 404/502 errors on canonical services

## Current Blocker: Backend Repository Issue

### The Problem
The canonical backend service (`velro-backend`) is failing because:
- Connected to monorepo structure (`audithero/velro-003`)  
- Railway expects dedicated repository for each service
- Current root directory: `velro-backend` (subdirectory)
- Expected root directory: `/` (dedicated repo)

### The Solution Required
1. **Create dedicated repository**: `audithero/velro-backend`
2. **Copy backend code** from monorepo to dedicated repo
3. **Update Railway service** to point to new repository
4. **Change root directory** to `/`
5. **Verify deployment** works with new structure

### Alternative Workaround
Temporarily use the working backend's approach:
- Update canonical backend start command to inline installation
- Keep monorepo structure but make it work
- Create dedicated repository as Phase 2 improvement

## Success Criteria

### Phase 1 Success (Immediate)
- [ ] `velro-backend-fresh` deleted successfully
- [ ] No impact on other services
- [ ] All canonical services still accessible

### Phase 2 Success (Final)  
- [ ] Canonical backend fully operational
- [ ] Frontend successfully calling canonical backend APIs
- [ ] Kong Gateway handling external provider requests
- [ ] `velro-backend-working` deleted successfully
- [ ] Only 3 canonical services remain active

## Post-Retirement Verification

After all retirements:
```bash
# Final service count verification
railway services list --project velro-production
# Expected result: 4 services total
# - velro-frontend ✅
# - velro-backend ✅  
# - velro-kong-gateway ✅
# - velro-redis ✅ (database service)
```

---

**Next Action**: Fix canonical backend deployment, then execute Phase 1 retirement of `velro-backend-fresh`.