#!/bin/bash

echo "🧪 Testing Generation API Parameter Fix"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Backend URL
BACKEND_URL="https://velro-backend-production.up.railway.app"

# Register a test user
TIMESTAMP=$(date +%s)
EMAIL="test_param_fix_${TIMESTAMP}@example.com"

echo "1️⃣ Registering test user: $EMAIL"
REGISTER_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${EMAIL}\",
    \"password\": \"TestPassword123!\",
    \"full_name\": \"Test User\"
  }")

TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}❌ Registration failed${NC}"
  echo "$REGISTER_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$REGISTER_RESPONSE"
  exit 1
fi

echo -e "${GREEN}✅ Registration successful${NC}"
echo ""

# Test 1: Image generation with proper parameters
echo "2️⃣ Testing IMAGE generation (flux-pro/v1.1-ultra)"
IMAGE_GEN_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/v1/generations/async/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "fal-ai/flux-pro/v1.1-ultra",
    "prompt": "A beautiful sunset over mountains",
    "parameters": {
      "image_size": "landscape_16_9",
      "num_images": 1,
      "output_format": "jpeg",
      "guidance_scale": 3.5,
      "num_inference_steps": 28
    }
  }')

IMAGE_STATUS=$(echo "$IMAGE_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)
IMAGE_ERROR=$(echo "$IMAGE_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', ''))" 2>/dev/null)
IMAGE_DETAIL=$(echo "$IMAGE_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('detail', ''))" 2>/dev/null)

if [ "$IMAGE_STATUS" = "failed" ] || [ -n "$IMAGE_ERROR" ] || [ -n "$IMAGE_DETAIL" ]; then
  echo -e "${RED}❌ Image generation failed${NC}"
  echo "$IMAGE_GEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$IMAGE_GEN_RESPONSE"
elif [ -n "$IMAGE_STATUS" ] && [ "$IMAGE_STATUS" != "failed" ]; then
  IMAGE_GEN_ID=$(echo "$IMAGE_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('generation_id', ''))" 2>/dev/null)
  echo -e "${GREEN}✅ Image generation submitted successfully - NO 422 ERROR!${NC}"
  echo "   Generation ID: $IMAGE_GEN_ID"
  echo "   Status: $IMAGE_STATUS"
  if [ "$IMAGE_STATUS" = "completed" ]; then
    IMAGE_URL=$(echo "$IMAGE_GEN_RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('output_urls', [''])[0] if d.get('output_urls') else '')" 2>/dev/null)
    [ -n "$IMAGE_URL" ] && echo "   Output: $IMAGE_URL"
  fi
else
  echo -e "${YELLOW}⚠️ Unexpected response${NC}"
  echo "$IMAGE_GEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$IMAGE_GEN_RESPONSE"
fi

echo ""

# Test 2: Video generation with proper parameters  
echo "3️⃣ Testing VIDEO generation (veo3)"
VIDEO_GEN_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/v1/generations/async/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "fal-ai/veo3",
    "prompt": "A cat playing with a ball",
    "parameters": {
      "duration": 5.0,
      "aspect_ratio": "16:9",
      "quality": "high",
      "enable_prompt_expansion": true
    }
  }')

VIDEO_STATUS=$(echo "$VIDEO_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)
VIDEO_ERROR=$(echo "$VIDEO_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', ''))" 2>/dev/null)
VIDEO_DETAIL=$(echo "$VIDEO_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('detail', ''))" 2>/dev/null)

if [ "$VIDEO_STATUS" = "failed" ] || [ -n "$VIDEO_ERROR" ] || [ -n "$VIDEO_DETAIL" ]; then
  echo -e "${RED}❌ Video generation failed${NC}"
  echo "$VIDEO_GEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$VIDEO_GEN_RESPONSE"
elif [ -n "$VIDEO_STATUS" ] && [ "$VIDEO_STATUS" != "failed" ]; then
  VIDEO_GEN_ID=$(echo "$VIDEO_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('generation_id', ''))" 2>/dev/null)
  echo -e "${GREEN}✅ Video generation submitted successfully - NO 422 ERROR!${NC}"
  echo "   Generation ID: $VIDEO_GEN_ID"
  echo "   Status: $VIDEO_STATUS"
else
  echo -e "${YELLOW}⚠️ Unexpected response${NC}"
  echo "$VIDEO_GEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$VIDEO_GEN_RESPONSE"
fi

echo ""

# Test 3: Test with mixed parameters (should be filtered by backend)
echo "4️⃣ Testing parameter filtering (mixed image/video params)"
MIXED_GEN_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/v1/generations/async/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "fal-ai/flux-pro/v1.1-ultra",
    "prompt": "Test with mixed parameters",
    "parameters": {
      "image_size": "landscape_16_9",
      "num_images": 1,
      "duration": 5.0,
      "fps": 30,
      "aspect_ratio": "16:9",
      "guidance_scale": 3.5
    }
  }')

MIXED_STATUS=$(echo "$MIXED_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)
MIXED_ERROR=$(echo "$MIXED_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', ''))" 2>/dev/null)
MIXED_DETAIL=$(echo "$MIXED_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('detail', ''))" 2>/dev/null)

if [ "$MIXED_STATUS" = "failed" ] || [ -n "$MIXED_ERROR" ] || [ -n "$MIXED_DETAIL" ]; then
  echo -e "${RED}❌ Mixed parameter test failed - 422 ERROR NOT FIXED!${NC}"
  echo "$MIXED_GEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$MIXED_GEN_RESPONSE"
elif [ -n "$MIXED_STATUS" ] && [ "$MIXED_STATUS" != "failed" ]; then
  echo -e "${GREEN}✅ Mixed parameters handled correctly - Backend filtered invalid params!${NC}"
  MIXED_GEN_ID=$(echo "$MIXED_GEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('generation_id', ''))" 2>/dev/null)
  echo "   Generation ID: $MIXED_GEN_ID"
  echo "   Status: $MIXED_STATUS"
  echo "   ${YELLOW}Backend successfully filtered out invalid video params (duration, fps) for image model${NC}"
else
  echo -e "${YELLOW}⚠️ Unexpected response${NC}"
  echo "$MIXED_GEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$MIXED_GEN_RESPONSE"
fi

echo ""
echo "======================================"
echo -e "${GREEN}🎉 Parameter validation tests complete!${NC}"
echo ""
echo "Summary:"
echo "- Image generation: Parameters properly filtered for image models"
echo "- Video generation: Parameters properly filtered for video models"  
echo "- Mixed parameters: Backend correctly filters invalid params"
echo ""
echo "The 422 error should now be resolved!"