#!/usr/bin/env node

/**
 * CORS-Only Validation Script
 * Tests CORS configuration independently of database connectivity
 * Focuses on endpoints that don't require database access
 */

const https = require('https');
const http = require('http');

// Configuration
const CONFIG = {
  frontend: {
    url: 'https://velro-frontend-production.up.railway.app',
    origin: 'https://velro-frontend-production.up.railway.app'
  },
  backend: {
    url: 'https://velro-003-backend-production.up.railway.app',
    baseURL: 'https://velro-003-backend-production.up.railway.app/api/v1'
  }
};

// Colors
const colors = {
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
  bold: '\x1b[1m'
};

function log(color, message) {
  console.log(`${color}${message}${colors.reset}`);
}

function logSuccess(message) {
  log(colors.green, `✅ ${message}`);
}

function logError(message) {
  log(colors.red, `❌ ${message}`);
}

function logInfo(message) {
  log(colors.blue, `ℹ️  ${message}`);
}

function logWarning(message) {
  log(colors.yellow, `⚠️  ${message}`);
}

// HTTP Request Helper
function makeRequest(options, postData = null) {
  return new Promise((resolve, reject) => {
    const protocol = options.protocol === 'https:' ? https : http;
    
    const req = protocol.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          statusMessage: res.statusMessage,
          headers: res.headers,
          body: data
        });
      });
    });
    
    req.on('error', (error) => {
      reject(error);
    });
    
    if (postData) {
      req.write(postData);
    }
    
    req.end();
  });
}

// Test 1: Simple CORS preflight for root endpoint
async function testRootCORS() {
  logInfo('Testing CORS Preflight for Root Endpoint...');
  
  const url = new URL(CONFIG.backend.url);
  
  const options = {
    hostname: url.hostname,
    port: url.port || 443,
    path: '/',
    method: 'OPTIONS',
    protocol: url.protocol,
    headers: {
      'Origin': CONFIG.frontend.origin,
      'Access-Control-Request-Method': 'GET',
      'Access-Control-Request-Headers': 'Content-Type'
    }
  };
  
  try {
    const response = await makeRequest(options);
    
    logInfo(`Root OPTIONS status: ${response.statusCode}`);
    logInfo(`Response headers: ${JSON.stringify(response.headers, null, 2)}`);
    
    // Check for CORS headers
    const allowOrigin = response.headers['access-control-allow-origin'];
    const allowMethods = response.headers['access-control-allow-methods'];
    
    if (allowOrigin) {
      logSuccess(`CORS Allow-Origin: ${allowOrigin}`);
    } else {
      logWarning('No CORS Allow-Origin header found');
    }
    
    if (allowMethods) {
      logSuccess(`CORS Allow-Methods: ${allowMethods}`);
    } else {
      logWarning('No CORS Allow-Methods header found');
    }
    
    return {
      success: response.statusCode < 500,
      statusCode: response.statusCode,
      corsHeaders: { allowOrigin, allowMethods }
    };
    
  } catch (error) {
    logError(`Root CORS test error: ${error.message}`);
    return { success: false, error: error.message };
  }
}

// Test 2: Direct Backend Root Access
async function testDirectBackendAccess() {
  logInfo('Testing Direct Backend Access...');
  
  const url = new URL(CONFIG.backend.url);
  
  const options = {
    hostname: url.hostname,
    port: url.port || 443,
    path: '/',
    method: 'GET',
    protocol: url.protocol,
    headers: {
      'Origin': CONFIG.frontend.origin,
      'User-Agent': 'Production-Validation-Tool'
    }
  };
  
  try {
    const response = await makeRequest(options);
    
    logInfo(`Direct access status: ${response.statusCode}`);
    logInfo(`Response body: ${response.body}`);
    
    if (response.statusCode === 200) {
      logSuccess('Backend is responding to direct access');
    } else if (response.statusCode === 404) {
      logInfo('Root endpoint returns 404 (expected for API-only backend)');
    } else if (response.statusCode >= 500) {
      logError(`Backend server error: ${response.statusCode}`);
    }
    
    // Check if CORS headers are present even on errors
    const corsHeaders = response.headers['access-control-allow-origin'];
    if (corsHeaders) {
      logSuccess(`CORS headers present on response: ${corsHeaders}`);
    }
    
    return {
      success: response.statusCode < 500,
      statusCode: response.statusCode,
      hasResponse: response.body.length > 0
    };
    
  } catch (error) {
    logError(`Direct access error: ${error.message}`);
    return { success: false, error: error.message };
  }
}

// Test 3: API Base Path
async function testAPIBasePath() {
  logInfo('Testing API Base Path...');
  
  const url = new URL(`${CONFIG.backend.baseURL}/`);
  
  const options = {
    hostname: url.hostname,
    port: url.port || 443,
    path: url.pathname,
    method: 'GET',
    protocol: url.protocol,
    headers: {
      'Origin': CONFIG.frontend.origin,
      'Accept': 'application/json'
    }
  };
  
  try {
    const response = await makeRequest(options);
    
    logInfo(`API base path status: ${response.statusCode}`);
    logInfo(`Response: ${response.body}`);
    
    if (response.statusCode < 500) {
      logSuccess('API base path accessible');
    } else {
      logError(`API base path error: ${response.statusCode}`);
    }
    
    return {
      success: response.statusCode < 500,
      statusCode: response.statusCode
    };
    
  } catch (error) {
    logError(`API base path error: ${error.message}`);
    return { success: false, error: error.message };
  }
}

// Test 4: Non-database dependent endpoint (if any)
async function testNonDatabaseEndpoint() {
  logInfo('Testing Non-Database Endpoint...');
  
  // Try a simple endpoint that shouldn't require database
  const endpoints = [
    '/',
    '/docs',
    '/api/v1/',
    '/api/v1/status'
  ];
  
  const results = [];
  
  for (const endpoint of endpoints) {
    const url = new URL(`${CONFIG.backend.url}${endpoint}`);
    
    const options = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname,
      method: 'GET',
      protocol: url.protocol,
      headers: {
        'Origin': CONFIG.frontend.origin,
        'Accept': 'application/json'
      }
    };
    
    try {
      const response = await makeRequest(options);
      
      logInfo(`${endpoint} -> ${response.statusCode}`);
      
      if (response.statusCode < 500) {
        logSuccess(`Endpoint ${endpoint} accessible`);
      }
      
      // Check for CORS headers
      const corsHeader = response.headers['access-control-allow-origin'];
      if (corsHeader) {
        logSuccess(`CORS header found on ${endpoint}: ${corsHeader}`);
      }
      
      results.push({
        endpoint,
        statusCode: response.statusCode,
        success: response.statusCode < 500,
        hasCORS: !!corsHeader,
        corsValue: corsHeader
      });
      
    } catch (error) {
      logWarning(`${endpoint} error: ${error.message}`);
      results.push({
        endpoint,
        success: false,
        error: error.message
      });
    }
  }
  
  return results;
}

// Generate CORS-Specific Report
function generateCORSReport(results) {
  console.log('\n' + '='.repeat(60));
  log(colors.bold, '📊 CORS VALIDATION REPORT');
  console.log('='.repeat(60));
  
  console.log(`\n🎯 Configuration:`);
  console.log(`   Frontend Origin: ${CONFIG.frontend.origin}`);
  console.log(`   Backend URL: ${CONFIG.backend.url}`);
  
  console.log(`\n📊 Test Results:`);
  
  let totalTests = 0;
  let successfulTests = 0;
  let corsWorkingCount = 0;
  
  Object.entries(results).forEach(([testName, result]) => {
    if (Array.isArray(result)) {
      result.forEach((r, i) => {
        totalTests++;
        if (r.success) successfulTests++;
        if (r.hasCORS) corsWorkingCount++;
        
        const status = r.success ? `${colors.green}PASS${colors.reset}` : `${colors.red}FAIL${colors.reset}`;
        const cors = r.hasCORS ? `${colors.green}✓ CORS${colors.reset}` : `${colors.red}✗ CORS${colors.reset}`;
        console.log(`   ${testName}[${i}]: ${status} | ${cors}`);
      });
    } else {
      totalTests++;
      if (result.success) successfulTests++;
      if (result.corsHeaders && (result.corsHeaders.allowOrigin || result.corsHeaders.allowMethods)) {
        corsWorkingCount++;
      }
      
      const status = result.success ? `${colors.green}PASS${colors.reset}` : `${colors.red}FAIL${colors.reset}`;
      console.log(`   ${testName}: ${status}`);
    }
  });
  
  console.log(`\n📈 Summary:`);
  console.log(`   Total Tests: ${totalTests}`);
  console.log(`   Successful: ${colors.green}${successfulTests}${colors.reset}`);
  console.log(`   CORS Working: ${colors.green}${corsWorkingCount}${colors.reset}`);
  
  const backendResponding = successfulTests > 0;
  const corsConfigured = corsWorkingCount > 0;
  
  console.log(`\n🔍 Analysis:`);
  if (backendResponding) {
    logSuccess('Backend is responding to requests');
  } else {
    logError('Backend is not responding properly');
  }
  
  if (corsConfigured) {
    logSuccess('CORS is configured and working');
  } else {
    logWarning('CORS configuration may need attention');
  }
  
  if (backendResponding && corsConfigured) {
    console.log(`\n${colors.green}${colors.bold}✅ CORS VALIDATION PASSED${colors.reset}`);
    console.log(`${colors.green}The frontend should be able to communicate with the backend${colors.reset}`);
  } else {
    console.log(`\n${colors.yellow}${colors.bold}⚠️ CORS VALIDATION NEEDS ATTENTION${colors.reset}`);
  }
  
  console.log('\n' + '='.repeat(60));
}

// Main execution
async function runCORSValidation() {
  console.log(`${colors.bold}🔍 CORS-ONLY VALIDATION${colors.reset}`);
  console.log(`${colors.blue}Testing CORS configuration independently of database issues${colors.reset}\n`);
  
  const results = {};
  
  try {
    results.rootCORS = await testRootCORS();
    console.log('');
    
    results.directAccess = await testDirectBackendAccess();
    console.log('');
    
    results.apiBasePath = await testAPIBasePath();
    console.log('');
    
    results.endpoints = await testNonDatabaseEndpoint();
    console.log('');
    
  } catch (error) {
    logError(`Validation error: ${error.message}`);
  }
  
  generateCORSReport(results);
  
  // Determine if CORS is working
  const corsWorking = Object.values(results).some(result => {
    if (Array.isArray(result)) {
      return result.some(r => r.hasCORS);
    }
    return result.success && (result.corsHeaders?.allowOrigin || result.corsHeaders?.allowMethods);
  });
  
  process.exit(corsWorking ? 0 : 1);
}

// Run if called directly
if (require.main === module) {
  runCORSValidation();
}

module.exports = { runCORSValidation, CONFIG };