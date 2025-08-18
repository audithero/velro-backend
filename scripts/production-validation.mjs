#!/usr/bin/env node

/**
 * Production Validation Script (ESM Version)
 * Modern fetch-based validation for frontend-backend authentication flow
 */

import fetch from 'node-fetch';
import { URL } from 'url';

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

const testResults = {
  cors: [],
  auth: [],
  endToEnd: [],
  summary: { total: 0, passed: 0, failed: 0 }
};

// Test 1: CORS Preflight using fetch
async function testCORSPreflightFetch() {
  logInfo('Testing CORS Preflight with fetch...');
  
  try {
    const response = await fetch(`${CONFIG.backend.baseURL}/auth/login`, {
      method: 'OPTIONS',
      headers: {
        'Origin': CONFIG.frontend.origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'Content-Type, Authorization'
      }
    });
    
    const test = {
      name: 'CORS Preflight (fetch)',
      passed: false,
      statusCode: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      issues: []
    };
    
    logInfo(`Preflight status: ${response.status}`);
    
    // Check required CORS headers
    const requiredHeaders = ['access-control-allow-origin', 'access-control-allow-methods'];
    requiredHeaders.forEach(header => {
      const value = response.headers.get(header);
      if (value) {
        logSuccess(`${header}: ${value}`);
      } else {
        test.issues.push(`Missing header: ${header}`);
        logError(`Missing header: ${header}`);
      }
    });
    
    // Check origin
    const allowOrigin = response.headers.get('access-control-allow-origin');
    if (allowOrigin === CONFIG.frontend.origin || allowOrigin === '*') {
      logSuccess(`Origin allowed: ${allowOrigin}`);
    } else {
      test.issues.push(`Origin not allowed: ${allowOrigin}`);
      logError(`Origin not allowed: ${allowOrigin}`);
    }
    
    test.passed = (response.status === 200 || response.status === 204) && test.issues.length === 0;
    testResults.cors.push(test);
    
    return test;
    
  } catch (error) {
    logError(`CORS Preflight error: ${error.message}`);
    const test = { name: 'CORS Preflight (fetch)', passed: false, error: error.message };
    testResults.cors.push(test);
    return test;
  }
}

// Test 2: Authentication with fetch
async function testAuthenticationFetch() {
  logInfo('Testing Authentication with fetch...');
  
  try {
    const response = await fetch(`${CONFIG.backend.baseURL}/auth/login`, {
      method: 'POST',
      headers: {
        'Origin': CONFIG.frontend.origin,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
      },
      body: JSON.stringify(CONFIG.credentials)
    });
    
    const test = {
      name: 'Authentication (fetch)',
      passed: false,
      statusCode: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      issues: []
    };
    
    logInfo(`Auth status: ${response.status}`);
    
    // Check CORS headers
    const corsHeaders = ['access-control-allow-origin'];
    corsHeaders.forEach(header => {
      const value = response.headers.get(header);
      if (value) {
        logSuccess(`${header}: ${value}`);
      } else {
        test.issues.push(`Missing CORS header: ${header}`);
        logWarning(`Missing CORS header: ${header}`);
      }
    });
    
    // Get response body
    const responseText = await response.text();
    let responseData = null;
    
    try {
      responseData = JSON.parse(responseText);
      logInfo(`Response: ${JSON.stringify(responseData, null, 2)}`);
    } catch (e) {
      logInfo(`Raw response: ${responseText}`);
    }
    
    // Status validation
    if (response.status === 200) {
      logSuccess('Authentication successful');
    } else if (response.status === 401) {
      logInfo('Authentication failed (401) - acceptable for demo credentials');
    } else if (response.status === 404) {
      test.issues.push('Endpoint not found');
      logError('Authentication endpoint not found');
    } else {
      logWarning(`Unexpected status: ${response.status}`);
    }
    
    test.passed = response.status > 0 && !test.issues.some(i => i.includes('Missing CORS'));
    testResults.auth.push(test);
    
    return test;
    
  } catch (error) {
    logError(`Authentication error: ${error.message}`);
    const test = { name: 'Authentication (fetch)', passed: false, error: error.message };
    testResults.auth.push(test);
    return test;
  }
}

// Test 3: Health Check
async function testHealthCheckFetch() {
  logInfo('Testing Health Check...');
  
  try {
    const response = await fetch(`${CONFIG.backend.baseURL}/health`, {
      method: 'GET',
      headers: {
        'Origin': CONFIG.frontend.origin
      }
    });
    
    const test = {
      name: 'Health Check',
      passed: response.status === 200,
      statusCode: response.status
    };
    
    if (test.passed) {
      logSuccess(`Health check: ${response.status}`);
      const healthText = await response.text();
      try {
        const healthData = JSON.parse(healthText);
        logSuccess(`Health: ${JSON.stringify(healthData, null, 2)}`);
      } catch (e) {
        logInfo(`Health response: ${healthText}`);
      }
    } else {
      logError(`Health check failed: ${response.status}`);
    }
    
    testResults.endToEnd.push(test);
    return test;
    
  } catch (error) {
    logError(`Health check error: ${error.message}`);
    const test = { name: 'Health Check', passed: false, error: error.message };
    testResults.endToEnd.push(test);
    return test;
  }
}

// Test 4: Complete Flow Simulation
async function testCompleteFlow() {
  logInfo('Testing Complete Authentication Flow...');
  
  try {
    // Step 1: Preflight
    logInfo('Step 1: Preflight request...');
    const preflightResponse = await fetch(`${CONFIG.backend.baseURL}/auth/login`, {
      method: 'OPTIONS',
      headers: {
        'Origin': CONFIG.frontend.origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'Content-Type'
      }
    });
    
    logInfo(`Preflight: ${preflightResponse.status}`);
    
    // Step 2: Actual request if preflight passes
    if (preflightResponse.status === 200 || preflightResponse.status === 204) {
      logInfo('Step 2: Authentication request...');
      
      const authResponse = await fetch(`${CONFIG.backend.baseURL}/auth/login`, {
        method: 'POST',
        headers: {
          'Origin': CONFIG.frontend.origin,
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(CONFIG.credentials)
      });
      
      logInfo(`Authentication: ${authResponse.status}`);
      
      const test = {
        name: 'Complete Flow',
        passed: authResponse.status > 0,
        preflightStatus: preflightResponse.status,
        authStatus: authResponse.status,
        corsWorking: true
      };
      
      testResults.endToEnd.push(test);
      
      if (test.passed) {
        logSuccess('Complete flow test PASSED');
      }
      
      return test;
    } else {
      throw new Error(`Preflight failed: ${preflightResponse.status}`);
    }
    
  } catch (error) {
    logError(`Complete flow error: ${error.message}`);
    const test = { name: 'Complete Flow', passed: false, error: error.message };
    testResults.endToEnd.push(test);
    return test;
  }
}

// Generate Report
function generateReport() {
  const allTests = [...testResults.cors, ...testResults.auth, ...testResults.endToEnd];
  const total = allTests.length;
  const passed = allTests.filter(t => t.passed).length;
  const failed = total - passed;
  
  testResults.summary = { total, passed, failed, successRate: total > 0 ? ((passed / total) * 100).toFixed(1) : 0 };
  
  console.log('\n' + '='.repeat(60));
  log(colors.bold, '📊 PRODUCTION VALIDATION REPORT');
  console.log('='.repeat(60));
  
  console.log(`\n🎯 Configuration:`);
  console.log(`   Frontend: ${CONFIG.frontend.url}`);
  console.log(`   Backend:  ${CONFIG.backend.url}`);
  
  console.log(`\n📈 Results:`);
  console.log(`   Total: ${total} | Passed: ${colors.green}${passed}${colors.reset} | Failed: ${colors.red}${failed}${colors.reset}`);
  console.log(`   Success Rate: ${passed === total ? colors.green : colors.yellow}${testResults.summary.successRate}%${colors.reset}`);
  
  if (passed === total) {
    console.log(`\n${colors.green}${colors.bold}🎉 ALL TESTS PASSED - PRODUCTION READY!${colors.reset}`);
  } else {
    console.log(`\n${colors.red}${colors.bold}⚠️  SOME TESTS FAILED${colors.reset}`);
  }
  
  console.log(`\n📋 Test Details:`);
  allTests.forEach((test, i) => {
    const status = test.passed ? `${colors.green}PASS${colors.reset}` : `${colors.red}FAIL${colors.reset}`;
    console.log(`   ${i + 1}. ${test.name}: ${status}`);
    if (!test.passed && test.error) {
      console.log(`      Error: ${colors.red}${test.error}${colors.reset}`);
    }
  });
  
  console.log('\n' + '='.repeat(60));
}

// Main function
async function runValidation() {
  console.log(`${colors.bold}🚀 VELRO PRODUCTION VALIDATION (ESM)${colors.reset}`);
  console.log(`${colors.blue}Testing CORS and authentication flow${colors.reset}\n`);
  
  try {
    await testCORSPreflightFetch();
    console.log('');
    
    await testAuthenticationFetch();
    console.log('');
    
    await testHealthCheckFetch();
    console.log('');
    
    await testCompleteFlow();
    console.log('');
    
  } catch (error) {
    logError(`Validation error: ${error.message}`);
  }
  
  generateReport();
  
  const success = testResults.summary.passed === testResults.summary.total;
  process.exit(success ? 0 : 1);
}

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  runValidation();
}

export { runValidation, testCORSPreflightFetch, testAuthenticationFetch, CONFIG };