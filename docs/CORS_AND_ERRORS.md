# CORS & Error Handling

## Overview

This document describes the CORS (Cross-Origin Resource Sharing) configuration and error handling strategy for the Velro backend API.

## CORS Configuration

### Middleware Order

The CORSMiddleware is registered **last** in the middleware stack, making it the **outermost** middleware. This ensures CORS headers are added to ALL responses, including:
- Successful responses (2xx)
- Client errors (4xx)
- Server errors (5xx)
- Preflight OPTIONS requests
- Early returns from other middleware

### Allowed Origins

CORS origins are configured via the `CORS_ORIGINS` environment variable:
- **JSON array format**: `["https://velro.ai", "https://velro-frontend-production.up.railway.app"]`
- **CSV format**: `https://velro.ai,https://velro-frontend-production.up.railway.app`

Production origins include:
- `https://velro-frontend-production.up.railway.app`
- `https://velro-003-frontend-production.up.railway.app`
- `https://velro.ai`
- `https://www.velro.ai`

### CORS Headers

The following headers are included in responses:
- `Access-Control-Allow-Origin`: Echoes the request Origin if allowed
- `Access-Control-Allow-Credentials`: `true`
- `Access-Control-Allow-Methods`: `GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD`
- `Access-Control-Allow-Headers`: `*` (all headers allowed)
- `Access-Control-Expose-Headers`: Various custom headers including `Server-Timing`, `X-Request-ID`
- `Access-Control-Max-Age`: `86400` (24 hours preflight cache)

## Error Handling

### Exception Handlers

All exception handlers return `JSONResponse` to ensure CORS middleware can add headers:

1. **HTTPException Handler** (401, 403, 404, etc):
   ```python
   @app.exception_handler(HTTPException)
   async def http_exception_handler(request, exc):
       return JSONResponse(
           status_code=exc.status_code,
           content={"detail": exc.detail, "request_id": req_id}
       )
   ```

2. **Validation Error Handler** (422):
   ```python
   @app.exception_handler(RequestValidationError)
   async def validation_exception_handler(request, exc):
       return JSONResponse(
           status_code=422,
           content={"detail": exc.errors(), "request_id": req_id}
       )
   ```

3. **Global Exception Handler** (500):
   ```python
   @app.exception_handler(Exception)
   async def global_exception_handler(request, exc):
       return JSONResponse(
           status_code=500,
           content={"detail": "Internal server error", "request_id": req_id}
       )
   ```

### Error Response Format

All error responses follow this JSON structure:
```json
{
  "detail": "Error message",
  "request_id": "unique-request-id",
  "status_code": 401
}
```

### Authentication Errors

When authentication fails (missing/invalid JWT):
- **Status**: 401 Unauthorized
- **Response**: JSON with error details
- **CORS Headers**: Always included

Example:
```bash
curl -i "https://api.velro.ai/api/v1/credits/balance" \
  -H "Origin: https://velro.ai"

HTTP/2 401
Access-Control-Allow-Origin: https://velro.ai
Content-Type: application/json

{"detail": "Unauthorized", "request_id": "...", "status_code": 401}
```

## Health Check Endpoints

Special ping endpoints that don't require authentication:
- `/api/v1/credits/_ping` - Credits service health
- `/api/v1/projects/_ping` - Projects service health

These return:
```json
{"ok": true, "service": "credits", "timestamp": 1234567890.123}
```

## Testing CORS

### Smoke Test Script

Run the CORS smoke test:
```bash
./scripts/smoke_cors.sh
```

This tests:
- Ping endpoints (no auth)
- Protected endpoints without auth (should return 401)
- Preflight OPTIONS requests
- Invalid JWT scenarios
- Non-existent endpoints (404)

### Manual Testing

Test CORS headers with curl:
```bash
# Test with Origin header
curl -i -H "Origin: https://velro.ai" \
  https://api.velro.ai/api/v1/credits/balance

# Test OPTIONS preflight
curl -i -X OPTIONS \
  -H "Origin: https://velro.ai" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization" \
  https://api.velro.ai/api/v1/credits/balance
```

## Middleware Stack

At startup, the middleware stack is logged for verification:
```
📊 [MIDDLEWARE-STACK] Middleware order (outermost to innermost):
  1. CORSMiddleware (handles OPTIONS, adds CORS headers)
  2. RateLimitMiddleware
  3. CSRFProtectionMiddleware
  4. SecurityEnhancedMiddleware
  5. SecureDesignMiddleware
  6. SSRFProtectionMiddleware
  7. AccessControlMiddleware
  8. GZipMiddleware
  9. ProductionOptimizedMiddleware
 10. FastlaneAuthMiddleware
```

## Deployment Notes

### Railway Environment Variables

Required environment variables:
```bash
CORS_ORIGINS='["https://velro.ai","https://velro-frontend-production.up.railway.app"]'
JWT_SECRET=your-secret-here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

### Verification

After deployment, verify CORS is working:
1. Check deployment logs for middleware stack output
2. Run smoke tests against production
3. Verify browser console shows no CORS errors
4. Check that error responses include CORS headers

## Troubleshooting

### CORS Headers Missing

If CORS headers are missing:
1. Verify CORSMiddleware is registered last (outermost)
2. Check that exception handlers return JSONResponse
3. Ensure no middleware returns Response() directly
4. Verify CORS_ORIGINS includes the request Origin

### 500 Errors on Auth Endpoints

If auth endpoints return 500:
1. Check JWT_SECRET is set correctly
2. Verify SUPABASE_URL and SUPABASE_ANON_KEY
3. Ensure database connection is working
4. Check rate limiting isn't blocking requests

### Browser CORS Errors

If browser shows CORS errors:
1. Check Network tab for actual response headers
2. Verify Origin header matches allowed origins
3. Check for preflight OPTIONS failures
4. Ensure credentials are included if needed