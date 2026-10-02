import { chromium } from "playwright";
(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.error('PAGE ERROR:', err.message));
    
    await page.goto('http://localhost:5173/login');
    // Wait for the form to be ready
    await page.waitForSelector('input[type="text"]');
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'banana123');
    await page.click('button[type="submit"]');
    
    // Wait for navigation or successful login indication
    await page.waitForURL('http://localhost:5173/dashboard', { timeout: 10000 }).catch(() => console.log("Did not navigate to dashboard immediately"));
    
    await page.goto('http://localhost:5173/analytics');
    await page.waitForTimeout(3000);
    await browser.close();
})();
