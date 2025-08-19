#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 Testing Complete Image Generation Flow"
echo "=========================================="
echo ""

# Register a new test user
TIMESTAMP=$(date +%s)
EMAIL="test_${TIMESTAMP}@example.com"

echo "1️⃣ Registering user: $EMAIL"

REGISTER_RESPONSE=$(curl -s -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${EMAIL}\",
    \"password\": \"TestPassword123!\",
    \"full_name\": \"Test User\"
  }")

TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

if [ -n "$TOKEN" ]; then
  echo -e "${GREEN}✅ Registration successful${NC}"
  
  echo ""
  echo "2️⃣ Getting user credits..."
  
  CREDITS_RESPONSE=$(curl -s "https://velro-backend-production.up.railway.app/api/v1/user/credits" \
    -H "Authorization: Bearer $TOKEN")
  
  CREDITS=$(echo "$CREDITS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('credits_balance', 0))" 2>/dev/null || echo "0")
  echo "   Credits balance: $CREDITS"
  
  echo ""
  echo "3️⃣ Testing models endpoint (should work without auth)..."
  
  MODELS_RESPONSE=$(curl -s "https://velro-backend-production.up.railway.app/generations/models/supported")
  MODEL_COUNT=$(echo "$MODELS_RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(len(d.get('models', [])))" 2>/dev/null || echo "0")
  
  if [ "$MODEL_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ Models endpoint working! Found $MODEL_COUNT models${NC}"
  else
    echo -e "${RED}❌ Models endpoint failed or returned no models${NC}"
    echo "$MODELS_RESPONSE" | head -100
  fi
  
  echo ""
  echo "4️⃣ Submitting image generation..."
  
  GEN_RESPONSE=$(curl -s -X POST "https://velro-backend-production.up.railway.app/api/v1/generations" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: multipart/form-data" \
    -F "model_id=fal-ai/flux-pro/v1.1-ultra" \
    -F "prompt=A beautiful mountain landscape at sunset" \
    -F 'parameters={"num_images":1,"image_size":"landscape_16_9"}' \
    -F "project_id=")
  
  echo "$GEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$GEN_RESPONSE"
  
  GEN_ID=$(echo "$GEN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('id', ''))" 2>/dev/null || echo "")
  STATUS=$(echo "$GEN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status', ''))" 2>/dev/null || echo "")
  
  if [ "$STATUS" != "failed" ] && [ -n "$GEN_ID" ]; then
    echo ""
    echo "5️⃣ Checking generation status..."
    
    for i in {1..10}; do
      sleep 3
      STATUS_RESPONSE=$(curl -s "https://velro-backend-production.up.railway.app/api/v1/generations/${GEN_ID}" \
        -H "Authorization: Bearer $TOKEN")
      
      CURRENT_STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null || echo "")
      echo "   Attempt $i/10: Status = $CURRENT_STATUS"
      
      if [ "$CURRENT_STATUS" = "completed" ]; then
        echo ""
        echo -e "${GREEN}✅ GENERATION COMPLETED!${NC}"
        echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null | head -50
        break
      elif [ "$CURRENT_STATUS" = "failed" ]; then
        echo ""
        echo -e "${RED}❌ Generation failed${NC}"
        echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null
        break
      fi
    done
  else
    echo -e "${RED}❌ Failed to submit generation${NC}"
  fi
  
  echo ""
  echo "6️⃣ Final credit check..."
  
  FINAL_CREDITS=$(curl -s "https://velro-backend-production.up.railway.app/api/v1/user/credits" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; print(json.load(sys.stdin).get('credits_balance', 0))" 2>/dev/null || echo "0")
  
  echo "   Final credits: $FINAL_CREDITS (was $CREDITS)"
  
else
  echo -e "${RED}❌ Registration failed${NC}"
  echo "$REGISTER_RESPONSE"
fi

echo ""
echo "=========================================="
echo "Test completed!"