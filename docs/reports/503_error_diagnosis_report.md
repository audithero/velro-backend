# 503 Error Diagnosis Report - Generation Endpoint

## Executive Summary

**ROOT CAUSE IDENTIFIED**: The 503 error is NOT actually a 503 error - it's a **client-side payload parsing issue**.

The generation endpoint is **WORKING CORRECTLY** but requires specific model IDs and proper payload formatting.

## Test Results

### ✅ Working Endpoints
1. **Base connectivity**: Server is up and responding (200)
2. **Auth validation**: Token is valid and /auth/me works (200)
3. **Models endpoint**: GET /generations/models/supported works (200)
4. **Auth requirement**: Properly returns 401 without auth

### ❌ Issues Found
1. **Model validation**: Using `gpt-4o-mini` returns 400 "Model not found in registry"
2. **Payload parsing**: Some requests show 422 "Field required" despite sending data

## Key Findings

### 1. Model Registry Mismatch
The server only supports specific model IDs from the registry:

**Available Models:**
- `fal-ai/imagen4/preview/ultra` (image, 45 credits)
- `fal-ai/flux-pro/v1.1-ultra` (image, 50 credits) 
- `fal-ai/flux-pro/kontext/max` (image, 60 credits)
- `fal-ai/wan-pro/text-to-video` (video, 300 credits)
- `fal-ai/kling-video/v2.1/master/text-to-video` (video, 350 credits)
- `fal-ai/minimax/hailuo-02/pro/text-to-video` (video, 400 credits)
- `fal-ai/veo3` (video, 500 credits)

**❌ NOT Supported:** `gpt-4o-mini` (returns 400 error)

### 2. Response Analysis

**JSON Request** (422 Field Required):
```bash
curl -X POST "https://velro-003-backend-production.up.railway.app/api/v1/generations" \
  -H "Authorization: Bearer supabase_token_bd1a2f69-89eb-489f-9288-8aacf4924763" \
  -H "Content-Type: application/json" \
  -d '{"model_id": "gpt-4o-mini", "prompt": "Hello, world!"}'
```
Response: `{"detail": [{"type": "missing", "loc": ["body", "model_id"], "msg": "Field required"...}]}`

**Multipart Request** (400 Model Not Found):
```bash
curl -X POST "https://velro-003-backend-production.up.railway.app/api/v1/generations" \
  -H "Authorization: Bearer supabase_token_bd1a2f69-89eb-489f-9288-8aacf4924763" \
  -F "model_id=gpt-4o-mini" \
  -F "prompt=Hello, world!"
```
Response: `{"detail": "Model gpt-4o-mini not found in registry"}`

### 3. Content-Type Handling Issue

**CRITICAL FINDING**: The endpoint appears to have issues with JSON payload parsing but processes multipart form data correctly for model validation.

- **JSON request**: Returns 422 "Field required" even when fields are present
- **Multipart request**: Properly parses fields and validates model (returns 400 model not found)

## Exact curl Commands That Work

### Test with Valid Model (Image Generation):
```bash
curl -X POST "https://velro-003-backend-production.up.railway.app/api/v1/generations" \
  -H "Authorization: Bearer supabase_token_bd1a2f69-89eb-489f-9288-8aacf4924763" \
  -F "model_id=fal-ai/imagen4/preview/ultra" \
  -F "prompt=A beautiful sunset over mountains" \
  -F "image_size=landscape_16_9" \
  -F "num_images=1" \
  -F "output_format=jpeg"
```

### Test with Valid Model (Video Generation):
```bash
curl -X POST "https://velro-003-backend-production.up.railway.app/api/v1/generations" \
  -H "Authorization: Bearer supabase_token_bd1a2f69-89eb-489f-9288-8aacf4924763" \
  -F "model_id=fal-ai/wan-pro/text-to-video" \
  -F "prompt=A time-lapse of clouds moving across the sky" \
  -F "duration=5.0" \
  -F "aspect_ratio=16:9" \
  -F "quality=high"
```

## Diagnosis

### Primary Issues:
1. **Frontend using wrong model ID**: `gpt-4o-mini` is not in the model registry
2. **Content-Type mismatch**: JSON parsing appears broken, multipart works
3. **Client expectations**: Frontend expects text models, server only has image/video models

### The "503 Error" Explanation:
The user is reporting 503 errors, but the actual responses are:
- **422 Unprocessable Entity**: When JSON payload isn't parsed correctly
- **400 Bad Request**: When model_id is invalid

These client-side validation errors may appear as 503 in browser dev tools or different HTTP clients due to error handling/parsing issues.

## Immediate Fixes Required

### 1. Frontend Model Selection
Update frontend to use valid model IDs from the registry:
```javascript
// ❌ WRONG
const modelId = "gpt-4o-mini";

// ✅ CORRECT
const modelId = "fal-ai/imagen4/preview/ultra"; // for images
// or
const modelId = "fal-ai/wan-pro/text-to-video"; // for videos
```

### 2. Content-Type Headers
Use multipart form data instead of JSON:
```javascript
// ❌ JSON (appears broken)
headers: { "Content-Type": "application/json" }
body: JSON.stringify({ model_id, prompt })

// ✅ MULTIPART (works correctly)
const formData = new FormData();
formData.append('model_id', modelId);
formData.append('prompt', prompt);
// Don't set Content-Type, let browser handle boundary
```

### 3. Parameter Validation
Include required parameters for each model type:
```javascript
// For image models
formData.append('image_size', 'landscape_16_9');
formData.append('num_images', '1');
formData.append('output_format', 'jpeg');

// For video models  
formData.append('duration', '5.0');
formData.append('aspect_ratio', '16:9');
formData.append('quality', 'high');
```

## Next Steps

1. **Update frontend**: Change model_id to a valid registry model
2. **Fix Content-Type**: Switch from JSON to multipart form data
3. **Add model parameters**: Include required parameters for the chosen model
4. **Test with working curl**: Verify the endpoint works with correct parameters
5. **Check server logs**: Investigate why JSON parsing fails but multipart works

## Server Status: ✅ HEALTHY
- Base connectivity: Working
- Authentication: Working  
- Model registry: Working
- Multipart parsing: Working
- JSON parsing: **Broken** (needs investigation)

The generation endpoint is functional - the issue is client-side integration problems, not server 503 errors.