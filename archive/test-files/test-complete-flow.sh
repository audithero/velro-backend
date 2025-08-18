#!/bin/bash

# Register a new test user
TIMESTAMP=$(date +%s)
EMAIL="test_${TIMESTAMP}@example.com"

echo "🚀 Testing Complete Image Generation Flow"
echo "=========================================="
echo ""
echo "1️⃣ Registering user: $EMAIL"

REGISTER_RESPONSE=$(curl -s -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  --data-raw "{
    \"email\": \"${EMAIL}\",
    \"password\": \"TestPassword123!\",
    \"full_name\": \"Test User\"
  }")

echo "Response: $REGISTER_RESPONSE"

# Extract token
TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
  echo "✅ Registration successful"
  echo "Token: ${TOKEN:0:50}..."
  
  echo ""
  echo "2️⃣ Submitting image generation..."
  
  GEN_RESPONSE=$(curl -s -X POST "https://velro-backend-production.up.railway.app/api/v1/generations/async/submit" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    --data-raw '{
      "model_id": "fal-ai/flux-pro/v1.1-ultra",
      "prompt": "A beautiful sunset over the ocean",
      "parameters": {
        "num_images": 1,
        "image_size": "landscape_16_9"
      }
    }')
  
  echo "Generation response:"
  echo "$GEN_RESPONSE" | head -c 200
  echo ""
  
  # Extract generation ID
  GEN_ID=$(echo "$GEN_RESPONSE" | grep -o '"generation_id":"[^"]*' | cut -d'"' -f4)
  
  if [ -n "$GEN_ID" ]; then
    echo ""
    echo "3️⃣ Generation ID: $GEN_ID"
    echo "Checking status..."
    
    for i in {1..10}; do
      sleep 3
      STATUS_RESPONSE=$(curl -s "https://velro-backend-production.up.railway.app/api/v1/generations/async/${GEN_ID}/status" \
        -H "Authorization: Bearer $TOKEN")
      
      CURRENT_STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status":"[^"]*' | cut -d'"' -f4)
      echo "   Attempt $i/10: Status = $CURRENT_STATUS"
      
      if [ "$CURRENT_STATUS" = "completed" ]; then
        echo ""
        echo "✅ GENERATION COMPLETED!"
        OUTPUT_URL=$(echo "$STATUS_RESPONSE" | grep -o '"output_urls":\["[^"]*' | cut -d'"' -f4)
        echo "Image URL: $OUTPUT_URL"
        break
      elif [ "$CURRENT_STATUS" = "failed" ]; then
        echo ""
        echo "❌ Generation failed"
        echo "$STATUS_RESPONSE"
        break
      fi
    done
  else
    echo "❌ Failed to get generation ID"
  fi
else
  echo "❌ Registration failed - no token"
fi