# Railway Service Configuration Map

Generated: 2025-08-11T15:49:00Z  
Project: velro-production (a6d6ccff-c1f6-425d-95b7-5ffcf4e02c16)

## Current Service Status

### ✅ CANONICAL SERVICES (KEEP)

#### 1. velro-frontend
- **Service ID**: `09cf3946-5b09-4f01-9060-98c0e9cc6765`
- **Status**: ✅ **SUCCESS** - Deployed successfully
- **Domain**: `velro-frontend-production.up.railway.app`
- **Repository**: `https://github.com/audithero/Velro-003-frontend.git`
- **Root Directory**: `/`
- **Build Command**: `npm run build`
- **Start Command**: `npm start`
- **Health Check**: `/health`

#### 2. velro-backend  
- **Service ID**: `2b0320e7-d782-478a-967a-7619f608066b`
- **Status**: ❌ **FAILED** - Repository connection issue
- **Domain**: `velro-backend-production.up.railway.app`
- **Repository**: Currently connected to monorepo (problem)
- **Root Directory**: `velro-backend` (monorepo structure)
- **Start Command**: `cd velro-backend && pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}`
- **Health Check**: `/health`
- **Issue**: Needs dedicated repository for proper deployment

#### 3. velro-kong-gateway
- **Service ID**: `381f5b28-8bd8-42a9-be5b-c93bddf16e79`  
- **Status**: ✅ **SUCCESS** - Running successfully
- **Domain**: `velro-kong-gateway-production.up.railway.app`
- **Repository**: `https://github.com/audithero/velro-kong.git`
- **Root Directory**: `/`

### ❌ DUPLICATE SERVICES (TO RETIRE)

#### 4. velro-backend-working
- **Service ID**: `9d567f51-388f-43c6-b039-b30c92faa614`
- **Status**: ✅ **SUCCESS** - But temporary inline code
- **Domain**: `velro-backend-working-production.up.railway.app`
- **Issue**: Hardcoded inline FastAPI app, not proper codebase

#### 5. velro-backend-fresh  
- **Service ID**: `281a659e-2b7a-40f4-89df-0fee93163551`
- **Status**: ❌ **FAILED** - Duplicate to retire
- **Domain**: `velro-backend-fresh-production.up.railway.app`

#### 6. velro-redis
- **Service ID**: `9615344a-4561-45ce-8589-34bae96b4f69`
- **Status**: Active database service
- **Note**: Required for backend operations

## Environment Variables Configuration

### Standardized Supabase Keys
```bash
SUPABASE_URL=https://ltspnsduziplpuqxczvy.supabase.co
SUPABASE_PUBLISHABLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx0c3Buc2R1emlwbHB1cXhjenZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI2MzM2MTEsImV4cCI6MjA2ODIwOTYxMX0.L1LGSXI1hdSd0I02U3dMcVlL6RHfJmEmuQnb86q9WAw
SUPABASE_SECRET_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx0c3Buc2R1emlwbHB1cXhjenZ5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MjYzMzYxMSwiZXhwIjoyMDY4MjA5NjExfQ.CibHbRQF23Qo8E3-aOzJlzwJjJOGRMt84vx0OXnPkSY

# Legacy compatibility
SUPABASE_ANON_KEY=${SUPABASE_PUBLISHABLE_KEY}
SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SECRET_KEY}
```

### Frontend API Configuration
```bash
NEXT_PUBLIC_API_URL=https://velro-backend-production.up.railway.app
NEXT_PUBLIC_KONG_GATEWAY_URL=https://velro-kong-gateway-production.up.railway.app
NEXT_PUBLIC_FAL_API_BASE=https://velro-kong-gateway-production.up.railway.app
```

## Critical Issues Requiring Resolution

### 1. Backend Repository Problem
The canonical backend service is failing because:
- It's connected to a monorepo structure (`velro-backend` subdirectory)
- Railway expects each service to have its own dedicated repository
- The `audithero/velro-003` monorepo may not exist or be accessible

### 2. Required Actions
1. **Create dedicated backend repository**: `audithero/velro-backend`
2. **Copy backend code** from `velro-003/velro-backend/` to new repo
3. **Update Railway service** to point to new repository
4. **Set root directory** to `/` for new repo structure

### 3. Immediate Workaround
The `velro-backend-working` service is currently functional because it:
- Uses inline FastAPI code in the start command
- Doesn't depend on repository structure
- Has all required environment variables

## Routing Architecture

### Frontend → Backend Direct
```
velro-frontend → velro-backend-production.up.railway.app/api/v1/*
```

### Kong Gateway → External Providers Only  
```
velro-kong-gateway → /fal/* (external AI providers)
```

### No Kong Proxy for Backend API
Kong does NOT proxy `/api/v1/*` traffic to backend. Frontend calls backend directly.

## Next Steps

1. ✅ **Snapshot created** - All environment variables backed up
2. ✅ **Services configured** - Canonical services updated
3. ❌ **Backend failing** - Repository issue needs resolution
4. ⏳ **Repository creation** - Need dedicated backend repo
5. ⏳ **Final deployment** - After repository fix
6. ⏳ **Retire duplicates** - After canonical services working

## Service URLs

| Service | URL | Status |
|---------|-----|--------|
| Frontend | `https://velro-frontend-production.up.railway.app` | ✅ Working |
| Backend | `https://velro-backend-production.up.railway.app` | ❌ Failed |
| Kong Gateway | `https://velro-kong-gateway-production.up.railway.app` | ✅ Working |
| Backend Working (temp) | `https://velro-backend-working-production.up.railway.app` | ✅ Working |

---

**Key Insight**: The main blocker is the backend repository structure. All other services are properly configured and deployed.