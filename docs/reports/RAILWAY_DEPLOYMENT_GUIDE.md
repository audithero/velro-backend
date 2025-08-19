# Railway Deployment Guide

## ✅ Configuration Fixes Applied

### 1. **Fixed railway.toml**
- Added proper `startCommand` using uvicorn for ASGI FastAPI
- Configured health check with 300s timeout
- Added restart policies for resilience

### 2. **Fixed nixpacks.toml**
- Switched from gunicorn to uvicorn for ASGI compatibility
- Added proper worker configuration and logging

### 3. **Updated config.py**
- Removed JWT_SECRET dependency (using Supabase signing keys)
- Added Railway environment variable support
- Made configuration more resilient

### 4. **Enhanced main.py**
- Added Railway-specific startup handling
- Added startup delays for environment variable loading
- Added retry logic for database connections
- Improved error handling for production

## 🚀 Next Steps for Deployment

### **1. Update Railway Environment Variables**
Go to Railway dashboard → Your project → Variables and ensure:

**Required Variables:**
- `SUPABASE_URL` = your-supabase-url
- `SUPABASE_ANON_KEY` = your-anon-key
- `SUPABASE_SERVICE_ROLE_KEY` = your-service-key (rename from SUPABASE_SERVICE_KEY)
- `FAL_KEY` = your-fal-key
- `REDIS_URL` = railway-provided-redis-url
- `ENVIRONMENT` = production
- `DEBUG` = false

**Remove:**
- `JWT_SECRET` (no longer needed)

### **2. Deploy to Railway**
```bash
# Commit and push your changes
git add .
git commit -m "Fix Railway deployment configuration"
git push origin main
```

### **3. Monitor Deployment**
1. Go to Railway dashboard → Deployments
2. Watch the deployment logs
3. Check the health endpoint: `https://your-app.railway.app/health`

### **4. Test the Deployment**
```bash
# Test health endpoint
curl https://your-app.railway.app/health

# Test root endpoint
curl https://your-app.railway.app/

# Test API endpoints
curl https://your-app.railway.app/api/v1/models
```

## 🔧 Troubleshooting

### **If deployment fails:**
1. Check Railway logs for specific error messages
2. Verify all environment variables are set correctly
3. Ensure SUPABASE_SERVICE_ROLE_KEY is renamed from SUPABASE_SERVICE_KEY
4. Check that FAL_KEY is valid

### **Common Issues:**
- **Database connection timeout**: Normal during startup, should resolve
- **Missing environment variables**: Check Railway Variables tab
- **Port binding issues**: Railway handles PORT automatically

## ✅ Expected Behavior
After deployment, you should see:
- ✅ Health endpoint returns "healthy"
- ✅ Root endpoint shows API information
- ✅ All API endpoints are accessible
- ✅ Database connection established
- ✅ Rate limiting and security features active
