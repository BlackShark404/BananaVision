import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  console.log("Navigating to login page...");
  await page.goto('http://localhost:5173/login');
  
  console.log("Logging in as admin...");
  await page.fill('input[type="text"]', 'admin');
  await page.fill('input[type="password"]', 'admin');
  await page.click('button[type="submit"]');
  
  console.log("Waiting for dashboard...");
  await page.waitForURL('http://localhost:5173/dashboard');
  
  console.log("Clicking logout button...");
  // Need to find the logout button. It's usually in a sidebar or profile menu.
  // Assuming there's a button with text "Logout" or "Log out"
  const logoutButton = page.locator('button', { hasText: /log\s*out/i }).first();
  if (await logoutButton.count() === 0) {
    console.log("Could not find logout button by text. Trying to find a link or a button in sidebar...");
    // Let's just evaluate a script to click the button if we can't find it easily
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const logoutBtn = btns.find(b => b.textContent.toLowerCase().includes('log out') || b.textContent.toLowerCase().includes('logout'));
      if (logoutBtn) logoutBtn.click();
    });
  } else {
    await logoutButton.click();
  }
  
  console.log("Waiting for redirect to landing page...");
  await page.waitForURL('http://localhost:5173/');
  
  console.log("Checking if we are on landing page...");
  const url = page.url();
  console.log("Current URL:", url);
  
  if (url === 'http://localhost:5173/') {
    console.log("Successfully redirected to landing page!");
  } else {
    console.log("Failed: Did not land on landing page. URL is", url);
  }
  
  // Wait a bit to ensure no infinite redirect loop kicks in
  await page.waitForTimeout(3000);
  console.log("After 3 seconds, URL is:", page.url());
  
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
