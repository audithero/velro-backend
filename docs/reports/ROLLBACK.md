# Velro Auth - Rollback Instructions

## Quick Rollback (Recommended)

### Option 1: Disable Fast Path (Fastest)
```bash
# Disable the fast login path
railway variables set AUTH_FAST_LOGIN=false \
  --service velro-backend --environment production

# Restart service to apply
railway restart --service velro-backend --environment production
```

### Option 2: Full Deployment Rollback
```bash
# List recent deployments
railway deployment list --service velro-backend

# Rollback to previous working deployment
railway rollback --service velro-backend --deployment bd06392c-0288-45ea-be6e-40706f451d0b
```

## Manual Git Revert

If you need to revert the code changes:

```bash
# Revert the auth optimizations
git revert 1000a2e

# Revert the service_time fix
git revert c8b0c51

# Push the reverts
git push origin main
```

## Environment Variable Rollback

To restore original timeout settings:

```bash
railway variables set \
  AUTH_FAST_LOGIN=false \
  AUTH_SUPABASE_TIMEOUT=8.0 \
  HTTP1_FALLBACK=false \
  --service velro-backend --environment production

railway restart --service velro-backend
```

## Verification Steps

After rollback:

1. **Check health endpoint**:
```bash
curl https://velro-backend-production.up.railway.app/health
```

2. **Test auth timing**:
```bash
time curl -X POST -H "Content-Type: application/json" \
  -d '{"email":"info@apostle.io","password":"12345678"}' \
  https://velro-backend-production.up.railway.app/api/v1/auth/login
```

3. **Monitor logs**:
```bash
railway logs --service velro-backend --tail
```

## Emergency Contacts

- Railway Dashboard: https://railway.app/project/a6d6ccff-c1f6-425d-95b7-5ffcf4e02c16
- Service ID: 2b0320e7-d782-478a-967a-7619f608066b
- Environment ID: f74bbed0-82ed-4e58-8136-0dc65563b295

## Known Working State

- **Last working deployment**: bd06392c-0288-45ea-be6e-40706f451d0b (Jan 11, 9:33 PM)
- **Before optimization commits**: 5e42343
- **Expected auth response time**: ~3-4s (not ideal but functional)

## Post-Rollback Actions

1. Review auth service for blocking calls
2. Test HTTP/2 vs HTTP/1.1 separately
3. Verify Supabase service keys
4. Consider staged rollout of optimizations

---

**Note**: The AUTH_FAST_LOGIN toggle was specifically designed for quick rollback without code changes.