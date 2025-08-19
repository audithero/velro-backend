const puppeteer = require('puppeteer');

async function checkFrontend() {
  const browser = await puppeteer.launch({ 
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800 });
    
    console.log('Navigating to frontend...');
    await page.goto('https://velro-frontend-production.up.railway.app', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });
    
    // Get page title
    const title = await page.title();
    console.log('Page title:', title);
    
    // Get all text content
    const textContent = await page.evaluate(() => document.body.innerText);
    console.log('\nPage content preview:');
    console.log(textContent.substring(0, 500));
    
    // Check for specific elements
    console.log('\nChecking for elements:');
    
    const hasLoginForm = await page.$('input[type="email"], input[type="password"]') \!== null;
    console.log('Has login form:', hasLoginForm);
    
    const hasGenerateButton = await page.$('button') \!== null;
    console.log('Has buttons:', hasGenerateButton);
    
    // Get all button texts
    const buttonTexts = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('button')).map(b => b.innerText);
    });
    console.log('Button texts:', buttonTexts);
    
    // Check for links
    const links = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('a')).map(a => ({
        text: a.innerText,
        href: a.href
      })).filter(l => l.text);
    });
    console.log('\nLinks found:', links.slice(0, 5));
    
    // Take screenshot
    await page.screenshot({ path: 'frontend-current.png' });
    console.log('\nScreenshot saved as frontend-current.png');
    
  } finally {
    await browser.close();
  }
}

checkFrontend().catch(console.error);
