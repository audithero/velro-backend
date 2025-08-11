#!/usr/bin/env node

/**
 * FINAL PRODUCTION TEST - Using correct API schema
 * Tests with proper form data format as expected by the API
 */

const https = require('https');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');

const JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsImtpZCI6IjFLZVFoMGxkV3paZjBKaUUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2x0c3Buc2R1emlwbHB1cXhjenZ5LnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiIyMmNiMzkxNy01N2Y2LTQ5YzYtYWM5Ni1lYzI2NjU3MDA4MWIiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU0MTIyNzUzLCJpYXQiOjE3NTQxMTkxNTMsImVtYWlsIjoiZGVtb0B2ZWxyby5hcHAiLCJwaG9uZSI6IiIsImFwcF9tZXRhZGF0YSI6eyJwcm92aWRlciI6ImVtYWlsIiwicHJvdmlkZXJzIjpbImVtYWlsIl19LCJ1c2VyX21ldGFkYXRhIjp7ImVtYWlsIjoiZGVtb0B2ZWxyby5hcHAiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwicGhvbmVfdmVyaWZpZWQiOmZhbHNlLCJzdWIiOiIyMmNiMzkxNy01N2Y2LTQ5YzYtYWM5Ni1lYzI2NjU3MDA4MWIifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJwYXNzd29yZCIsInRpbWVzdGFtcCI6MTc1NDExOTE1M31dLCJzZXNzaW9uX2lkIjoiMTI1NGViYTktYmYwZi00YWYzLWJkNzMtM2M0NzQ5OGFhZWZkIiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.4p8NUcmcEW4u_bDi4LBg1re_RoJ3zggwAIrEKkb-bos';

// Create multipart form data
function createFormData(fields) {
  const boundary = '----FormBoundary' + crypto.randomBytes(16).toString('hex');
  let formData = '';
  
  for (const [name, value] of Object.entries(fields)) {
    formData += `--${boundary}\r\n`;
    formData += `Content-Disposition: form-data; name="${name}"\r\n\r\n`;
    formData += `${value}\r\n`;
  }
  
  formData += `--${boundary}--\r\n`;
  
  return {
    data: formData,
    contentType: `multipart/form-data; boundary=${boundary}`
  };
}

function makeRequest(options, postData = null, followRedirects = true) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      // Handle redirects
      if (followRedirects && (res.statusCode === 301 || res.statusCode === 302 || res.statusCode === 307 || res.statusCode === 308)) {
        const location = res.headers.location;
        console.log(`Following redirect to: ${location}`);
        
        // Parse the new URL
        const url = new URL(location);
        const newOptions = {
          hostname: url.hostname,
          path: url.pathname + url.search,
          method: options.method,
          headers: options.headers
        };
        
        // Recursive call with new URL
        return resolve(makeRequest(newOptions, postData, false));
      }
      
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: parsed
          });
        } catch (e) {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: data
          });
        }
      });
    });

    req.on('error', reject);
    
    if (postData) {
      req.write(postData);
    }
    
    req.end();
  });
}

async function testGenerationCorrectFormat() {
  console.log('🚀 TESTING GENERATION WITH CORRECT FORM DATA FORMAT');
  console.log('=' .repeat(60));
  
  // Create form data as expected by the API
  const formFields = {
    model_id: 'fal-ai/flux/schnell',  // Valid FAL.ai model
    prompt: 'A beautiful sunset over mountains, photorealistic style',
    negative_prompt: 'blurry, low quality',
    parameters: JSON.stringify({
      image_size: 'square_hd',
      num_inference_steps: 4,
      guidance_scale: 3.5
    })
  };

  const formData = createFormData(formFields);

  const options = {
    hostname: 'velro-backend-production.up.railway.app',
    path: '/api/v1/generations/',  // Use trailing slash to avoid redirect
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${JWT_TOKEN}`,
      'Content-Type': formData.contentType,
      'Content-Length': Buffer.byteLength(formData.data),
      'User-Agent': 'Production-Validation-Script/1.0'
    }
  };

  try {
    console.log('Sending form data:');
    console.log('- model_id:', formFields.model_id);
    console.log('- prompt:', formFields.prompt);
    console.log('- parameters:', formFields.parameters);
    
    const response = await makeRequest(options, formData.data, false);
    
    console.log(`\nStatus Code: ${response.statusCode}`);
    console.log('Response Body:', JSON.stringify(response.body, null, 2));
    
    if (response.statusCode === 200 || response.statusCode === 201) {
      console.log('✅ SUCCESS: Generation request processed successfully');
    } else if (response.statusCode === 402) {
      console.log('💳 CREDIT ISSUE: Insufficient credits detected');
    } else if (response.statusCode === 500 && JSON.stringify(response.body).includes('Profile lookup error')) {
      console.log('❌ PROFILE LOOKUP ERROR: This is the main bug - user profile not found');
    } else {
      console.log(`❌ FAILED: Unexpected status ${response.statusCode}`);
    }
    
    return response;
  } catch (error) {
    console.error('❌ Error testing generation:', error.message);
    return null;
  }
}

async function testGetSupportedModels() {
  console.log('\n🔄 TESTING SUPPORTED MODELS ENDPOINT');
  console.log('=' .repeat(60));
  
  const options = {
    hostname: 'velro-backend-production.up.railway.app',
    path: '/api/v1/generations/models/supported',
    method: 'GET',
    headers: {
      'User-Agent': 'Production-Validation-Script/1.0'
    }
  };

  try {
    const response = await makeRequest(options);
    
    console.log(`Status Code: ${response.statusCode}`);
    
    if (response.statusCode === 200) {
      console.log('✅ SUCCESS: Models endpoint working');
      if (response.body.models && Array.isArray(response.body.models)) {
        console.log(`Found ${response.body.models.length} supported models`);
        if (response.body.models.length > 0) {
          console.log('First model:', response.body.models[0]);
        }
      }
    } else {
      console.log(`❌ FAILED: Models endpoint returned ${response.statusCode}`);
      console.log('Response:', JSON.stringify(response.body, null, 2));
    }
    
    return response;
  } catch (error) {
    console.error('❌ Error testing models endpoint:', error.message);
    return null;
  }
}

async function runFinalValidation() {
  console.log('🎯 FINAL PRODUCTION VALIDATION');
  console.log('Testing with EXACT API schema requirements');
  console.log('Time: ' + new Date().toISOString());
  console.log('=' .repeat(80));

  // Decode JWT to show user details
  const decoded = jwt.decode(JWT_TOKEN);
  console.log(`User ID: ${decoded.sub}`);
  console.log(`Email: ${decoded.email}`);
  console.log(`Token valid until: ${new Date(decoded.exp * 1000).toISOString()}`);

  // Test endpoints
  const modelsResult = await testGetSupportedModels();
  const generationResult = await testGenerationCorrectFormat();

  console.log('\n📊 FINAL VALIDATION SUMMARY');
  console.log('=' .repeat(60));
  console.log(`Supported Models: ${modelsResult?.statusCode === 200 ? '✅ PASS' : '❌ FAIL'}`);
  console.log(`Generation (Correct Format): ${generationResult?.statusCode === 200 || generationResult?.statusCode === 201 ? '✅ PASS' : '❌ FAIL'}`);

  console.log('\n🔍 ROOT CAUSE ANALYSIS:');
  
  // Check for specific issues
  if (generationResult?.statusCode === 500) {
    const errorBody = JSON.stringify(generationResult.body);
    if (errorBody.includes('Profile lookup error')) {
      console.log('❌ CRITICAL: Profile lookup error - User profile not found in database');
      console.log('   This indicates the user authentication is working but profile lookup fails');
    } else if (errorBody.includes('NoneType')) {
      console.log('❌ CRITICAL: NoneType error - Some required data is None/null');
    } else {
      console.log('❌ CRITICAL: Internal server error with different cause');
    }
  } else if (generationResult?.statusCode === 402) {
    console.log('💳 Credit system working - insufficient credits for generation');
  } else if (generationResult?.statusCode === 422) {
    console.log('⚠️  Validation error - check required fields');
  }

  console.log('\n✅ VALIDATION COMPLETE');
  console.log('All issues are now documented with exact error details.');
}

if (require.main === module) {
  runFinalValidation().catch(console.error);
}