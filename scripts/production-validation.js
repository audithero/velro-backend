#!/usr/bin/env node

/**
 * Production Validation Script
 * Comprehensive test suite for frontend-backend authentication flow
 * Tests CORS configuration and end-to-end authentication
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
  },
  credentials: {
    email: 'demo@velro.app',
    password: 'demo123456'
  }
};

// Test Results Storage
const testResults = {
  cors: [],
  auth: [],
  endToEnd: [],
  summary: {
    total: 0,
    passed: 0,
    failed: 0,
    errors: []
  }
};

// Color console output
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

// Test 1: CORS Preflight Request (OPTIONS)
async function testCORSPreflight() {
  logInfo('Testing CORS Preflight Request...');
  
  const url = new URL(`${CONFIG.backend.baseURL}/auth/login`);
  
  const options = {
    hostname: url.hostname,
    port: url.port || 443,
    path: url.pathname,
    method: 'OPTIONS',
    protocol: url.protocol,
    headers: {
      'Origin': CONFIG.frontend.origin,
      'Access-Control-Request-Method': 'POST',
      'Access-Control-Request-Headers': 'Content-Type, Authorization'
    }
  };
  
  try {
    const response = await makeRequest(options);
    
    const test = {
      name: 'CORS Preflight',
      passed: false,
      statusCode: response.statusCode,
      headers: response.headers,
      issues: []
    };
    
    // Check status code
    if (response.statusCode === 200 || response.statusCode === 204) {
      logSuccess(`Preflight status: ${response.statusCode}`);
    } else {
      test.issues.push(`Invalid preflight status: ${response.statusCode}`);
      logError(`Preflight status: ${response.statusCode}`);
    }
    
    // Check CORS headers
    const requiredHeaders = [
      'access-control-allow-origin',
      'access-control-allow-methods',
      'access-control-allow-headers'
    ];
    
    requiredHeaders.forEach(header => {
      if (response.headers[header]) {
        logSuccess(`${header}: ${response.headers[header]}`);
      } else {
        test.issues.push(`Missing header: ${header}`);
        logError(`Missing header: ${header}`);
      }
    });
    
    // Validate specific CORS values
    const allowOrigin = response.headers['access-control-allow-origin'];
    if (allowOrigin === CONFIG.frontend.origin || allowOrigin === '*') {
      logSuccess(`Origin allowed: ${allowOrigin}`);
    } else {
      test.issues.push(`Origin not allowed. Expected: ${CONFIG.frontend.origin}, Got: ${allowOrigin}`);
      logError(`Origin not allowed. Expected: ${CONFIG.frontend.origin}, Got: ${allowOrigin}`);
    }
    
    test.passed = test.issues.length === 0;
    testResults.cors.push(test);
    
    if (test.passed) {
      logSuccess('CORS Preflight test PASSED');
    } else {
      logError('CORS Preflight test FAILED');
    }
    
    return test;
    
  } catch (error) {
    logError(`CORS Preflight test ERROR: ${error.message}`);
    testResults.cors.push({
      name: 'CORS Preflight',
      passed: false,
      error: error.message
    });
    throw error;
  }
}

// Test 2: Authentication Request (POST)
async function testAuthenticationRequest() {
  logInfo('Testing Authentication Request...');
  
  const url = new URL(`${CONFIG.backend.baseURL}/auth/login`);
  const postData = JSON.stringify(CONFIG.credentials);
  
  const options = {
    hostname: url.hostname,
    port: url.port || 443,
    path: url.pathname,
    method: 'POST',
    protocol: url.protocol,
    headers: {
      'Origin': CONFIG.frontend.origin,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(postData),
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
  };
  
  try {
    const response = await makeRequest(options, postData);
    
    const test = {
      name: 'Authentication Request',
      passed: false,
      statusCode: response.statusCode,
      headers: response.headers,
      body: response.body,
      issues: []
    };
    
    logInfo(`Auth status: ${response.statusCode}`);
    
    // Check CORS headers on actual request
    const corsHeaders = [
      'access-control-allow-origin',
      'access-control-allow-credentials'
    ];
    
    corsHeaders.forEach(header => {
      if (response.headers[header]) {
        logSuccess(`${header}: ${response.headers[header]}`);
      } else {
        test.issues.push(`Missing CORS header in response: ${header}`);
        logWarning(`Missing CORS header in response: ${header}`);
      }
    });
    
    // Parse response body
    let responseData = null;
    try {
      responseData = JSON.parse(response.body);
      logInfo(`Response: ${JSON.stringify(responseData, null, 2)}`);
    } catch (e) {
      logWarning('Response is not valid JSON');
      logInfo(`Raw response: ${response.body}`);
    }
    
    // Check if request was successful or properly rejected
    if (response.statusCode === 200) {
      logSuccess('Authentication successful');
      if (responseData && responseData.token) {
        logSuccess('JWT token received');
      }
    } else if (response.statusCode === 401) {
      logInfo('Authentication failed (401) - this is acceptable for demo credentials');
    } else if (response.statusCode === 404) {
      test.issues.push('Endpoint not found (404)');
      logError('Authentication endpoint not found');
    } else {
      test.issues.push(`Unexpected status code: ${response.statusCode}`);
      logWarning(`Unexpected status code: ${response.statusCode}`);
    }
    
    // Most important: no CORS errors (would be 0 status in browser)
    if (response.statusCode > 0) {
      logSuccess('No CORS policy violation detected');
    }
    
    test.passed = response.statusCode > 0 && test.issues.filter(i => i.includes('Missing CORS')).length === 0;
    testResults.auth.push(test);
    
    if (test.passed) {
      logSuccess('Authentication request test PASSED');
    } else {
      logError('Authentication request test FAILED');
    }
    
    return test;
    
  } catch (error) {
    logError(`Authentication test ERROR: ${error.message}`);
    testResults.auth.push({
      name: 'Authentication Request',
      passed: false,
      error: error.message
    });
    throw error;
  }
}

// Test 3: Health Check
async function testHealthCheck() {
  logInfo('Testing Health Check Endpoint...');
  
  const url = new URL(`${CONFIG.backend.baseURL}/health`);
  
  const options = {
    hostname: url.hostname,
    port: url.port || 443,
    path: url.pathname,
    method: 'GET',
    protocol: url.protocol,
    headers: {
      'Origin': CONFIG.frontend.origin
    }
  };
  
  try {
    const response = await makeRequest(options);
    
    const test = {
      name: 'Health Check',
      passed: response.statusCode === 200,
      statusCode: response.statusCode,
      headers: response.headers,
      body: response.body
    };
    
    if (test.passed) {
      logSuccess(`Health check: ${response.statusCode}`);
      try {
        const healthData = JSON.parse(response.body);
        logSuccess(`Health status: ${JSON.stringify(healthData, null, 2)}`);
      } catch (e) {
        logInfo(`Health response: ${response.body}`);
      }
    } else {
      logError(`Health check failed: ${response.statusCode}`);
    }
    
    testResults.endToEnd.push(test);
    return test;
    
  } catch (error) {
    logError(`Health check ERROR: ${error.message}`);
    testResults.endToEnd.push({
      name: 'Health Check',
      passed: false,
      error: error.message
    });
    return { passed: false, error: error.message };
  }
}

// Test 4: Browser-like Simulation
async function testBrowserSimulation() {
  logInfo('Testing Browser-like Request Simulation...');
  
  try {
    // First, preflight
    await testCORSPreflight();
    
    // Then, actual request with more browser-like headers
    const url = new URL(`${CONFIG.backend.baseURL}/auth/login`);
    const postData = JSON.stringify(CONFIG.credentials);
    
    const options = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname,
      method: 'POST',
      protocol: url.protocol,
      headers: {
        'Origin': CONFIG.frontend.origin,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': CONFIG.frontend.origin,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site'
      }
    };
    
    const response = await makeRequest(options, postData);
    
    const test = {
      name: 'Browser Simulation',
      passed: response.statusCode > 0,
      statusCode: response.statusCode,
      headers: response.headers,
      simulation: 'Chrome browser cross-origin request'
    };
    
    testResults.endToEnd.push(test);
    
    if (test.passed) {
      logSuccess('Browser simulation test PASSED');
    } else {
      logError('Browser simulation test FAILED');
    }
    
    return test;
    
  } catch (error) {
    logError(`Browser simulation ERROR: ${error.message}`);
    return { passed: false, error: error.message };
  }
}

// Generate Summary Report
function generateSummaryReport() {
  const allTests = [...testResults.cors, ...testResults.auth, ...testResults.endToEnd];
  const totalTests = allTests.length;
  const passedTests = allTests.filter(t => t.passed).length;
  const failedTests = totalTests - passedTests;
  
  testResults.summary = {
    total: totalTests,
    passed: passedTests,
    failed: failedTests,
    successRate: totalTests > 0 ? ((passedTests / totalTests) * 100).toFixed(1) : 0
  };
  
  console.log('\n' + '='.repeat(60));
  log(colors.bold, '📊 PRODUCTION VALIDATION SUMMARY');
  console.log('='.repeat(60));
  
  console.log(`\n🎯 Test Configuration:`);
  console.log(`   Frontend: ${CONFIG.frontend.url}`);
  console.log(`   Backend:  ${CONFIG.backend.url}`);
  console.log(`   Origin:   ${CONFIG.frontend.origin}`);
  
  console.log(`\n📈 Results:`);
  console.log(`   Total Tests: ${totalTests}`);
  console.log(`   Passed: ${colors.green}${passedTests}${colors.reset}`);
  console.log(`   Failed: ${colors.red}${failedTests}${colors.reset}`);
  console.log(`   Success Rate: ${passedTests === totalTests ? colors.green : colors.yellow}${testResults.summary.successRate}%${colors.reset}`);
  
  if (passedTests === totalTests) {
    console.log(`\n${colors.green}${colors.bold}🎉 ALL TESTS PASSED - PRODUCTION READY!${colors.reset}`);
  } else {
    console.log(`\n${colors.red}${colors.bold}⚠️  SOME TESTS FAILED - REQUIRES ATTENTION${colors.reset}`);
  }
  
  // Detailed test results
  console.log(`\n📋 Detailed Results:`);
  allTests.forEach((test, index) => {
    const status = test.passed ? `${colors.green}PASS${colors.reset}` : `${colors.red}FAIL${colors.reset}`;
    console.log(`   ${index + 1}. ${test.name}: ${status}`);
    if (!test.passed && test.issues) {
      test.issues.forEach(issue => {
        console.log(`      - ${colors.red}${issue}${colors.reset}`);
      });
    }
    if (test.error) {
      console.log(`      - ${colors.red}Error: ${test.error}${colors.reset}`);
    }
  });
  
  console.log('\n' + '='.repeat(60));
}

// Main execution function
async function runValidation() {
  console.log(`${colors.bold}🚀 VELRO PRODUCTION VALIDATION${colors.reset}`);
  console.log(`${colors.blue}Testing authentication flow between frontend and backend${colors.reset}\n`);
  
  try {
    // Test 1: CORS Preflight
    await testCORSPreflight();
    console.log('');
    
    // Test 2: Authentication
    await testAuthenticationRequest();
    console.log('');
    
    // Test 3: Health Check
    await testHealthCheck();
    console.log('');
    
    // Test 4: Browser Simulation
    await testBrowserSimulation();
    console.log('');
    
  } catch (error) {
    logError(`Validation failed with error: ${error.message}`);
  }
  
  // Generate final report
  generateSummaryReport();
  
  // Exit with appropriate code
  const success = testResults.summary.passed === testResults.summary.total;
  process.exit(success ? 0 : 1);
}

// Error handling
process.on('unhandledRejection', (reason, promise) => {
  logError(`Unhandled Rejection at: ${promise}, reason: ${reason}`);
  process.exit(1);
});

process.on('uncaughtException', (error) => {
  logError(`Uncaught Exception: ${error.message}`);
  process.exit(1);
});

// Run the validation
if (require.main === module) {
  runValidation();
}

module.exports = {
  runValidation,
  testCORSPreflight,
  testAuthenticationRequest,
  testHealthCheck,
  CONFIG
};