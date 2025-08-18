const puppeteer = require('puppeteer');

async function testFrontendGeneration() {
  console.log('🚀 TESTING FRONTEND IMAGE GENERATION WITH PUPPETEER');
  console.log('=' .repeat(60));
  
  const browser = await puppeteer.launch({ 
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  try {
    const page = await browser.newPage();
    
    // Set viewport
    await page.setViewport({ width: 1280, height: 800 });
    
    // Navigate to frontend
    console.log('\n1️⃣ Navigating to frontend...');
    await page.goto('https://velro-frontend-production.up.railway.app', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });
    console.log('   ✅ Page loaded');
    
    // Check if we're on login page or dashboard
    const url = page.url();
    console.log(`   Current URL: ${url}`);
    
    // If not logged in, register a new account
    if (url.includes('/login') || url.includes('/auth')) {
      console.log('\n2️⃣ Need to register/login...');
      
      // Look for sign up link
      const signUpLink = await page.$('a[href*="signup"], a[href*="register"], button:has-text("Sign up"), button:has-text("Register")');
      if (signUpLink) {
        console.log('   Found sign up link, clicking...');
        await signUpLink.click();
        await page.waitForNavigation({ waitUntil: 'networkidle2' });
      }
      
      // Fill registration form
      const timestamp = Date.now();
      const email = `test_${timestamp}@example.com`;
      const password = 'TestPassword123!';
      
      console.log(`   Registering as: ${email}`);
      
      // Try to find and fill email field
      await page.waitForSelector('input[type="email"], input[name="email"], input[placeholder*="email" i]', { timeout: 5000 });
      await page.type('input[type="email"], input[name="email"], input[placeholder*="email" i]', email);
      
      // Fill password
      await page.type('input[type="password"]', password);
      
      // Fill confirm password if exists
      const confirmPassword = await page.$('input[name="confirmPassword"], input[placeholder*="confirm" i][type="password"]');
      if (confirmPassword) {
        await page.type('input[name="confirmPassword"], input[placeholder*="confirm" i][type="password"]', password);
      }
      
      // Fill name if exists
      const nameField = await page.$('input[name="name"], input[name="fullName"], input[placeholder*="name" i]:not([type="email"])');
      if (nameField) {
        await page.type('input[name="name"], input[name="fullName"], input[placeholder*="name" i]:not([type="email"])', 'Test User');
      }
      
      // Submit form
      await page.click('button[type="submit"], button:has-text("Sign up"), button:has-text("Register")');
      
      // Wait for navigation or error
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 10000 }).catch(() => {
        console.log('   No navigation after submit, checking for errors...');
      });
      
      console.log('   ✅ Registration/login attempted');
    }
    
    // Check if we're now on the dashboard
    console.log('\n3️⃣ Checking for generation interface...');
    await new Promise(r => setTimeout(r, 2000));
    
    // Look for prompt input field
    const promptSelector = 'textarea[placeholder*="prompt" i], input[placeholder*="prompt" i], textarea[placeholder*="describe" i], input[placeholder*="describe" i], textarea[name="prompt"], input[name="prompt"]';
    
    try {
      await page.waitForSelector(promptSelector, { timeout: 5000 });
      console.log('   ✅ Found prompt input field');
      
      // Enter a prompt
      const testPrompt = 'A beautiful sunset over the ocean with waves';
      await page.type(promptSelector, testPrompt);
      console.log(`   ✅ Entered prompt: "${testPrompt}"`);
      
      // Find and click generate button
      const generateButton = await page.$('button:has-text("Generate"), button:has-text("Create"), button[type="submit"]');
      if (generateButton) {
        console.log('   ✅ Found generate button, clicking...');
        await generateButton.click();
        
        // Wait for generation to start
        console.log('\n4️⃣ Waiting for generation to complete...');
        
        // Wait for either an image to appear or an error message
        const maxWaitTime = 60000; // 60 seconds
        const startTime = Date.now();
        
        while (Date.now() - startTime < maxWaitTime) {
          // Check for image
          const image = await page.$('img[src*="fal.media"], img[src*="fal.ai"], img[alt*="generated" i]');
          if (image) {
            const imageSrc = await page.evaluate(img => img.src, image);
            console.log('   ✅ GENERATION COMPLETED!');
            console.log(`   Image URL: ${imageSrc}`);
            break;
          }
          
          // Check for error
          const error = await page.$('.error, .alert-error, [role="alert"]');
          if (error) {
            const errorText = await page.evaluate(el => el.innerText, error);
            console.log(`   ❌ Error: ${errorText}`);
            break;
          }
          
          // Check for status text
          const statusElement = await page.$('.status, .generation-status, [data-status]');
          if (statusElement) {
            const statusText = await page.evaluate(el => el.innerText, statusElement);
            console.log(`   Status: ${statusText}`);
          }
          
          await new Promise(r => setTimeout(r, 2000));
        }
      } else {
        console.log('   ❌ Could not find generate button');
      }
    } catch (error) {
      console.log(`   ❌ Could not find generation interface: ${error.message}`);
      
      // Take a screenshot for debugging
      await page.screenshot({ path: 'frontend-state.png' });
      console.log('   📸 Screenshot saved as frontend-state.png');
    }
    
  } catch (error) {
    console.error('Test failed:', error);
  } finally {
    await browser.close();
    console.log('\n' + '='.repeat(60));
    console.log('Test completed');
  }
}

testFrontendGeneration().catch(console.error);