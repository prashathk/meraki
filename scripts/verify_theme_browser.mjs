import {demoPassword} from './local-config.mjs';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const browser=await chromium.launch({channel:'msedge',headless:true});
try {
 for(const role of ['student','university','admin']){
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  await page.goto('http://127.0.0.1:8000/auth');
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.getByLabel('Email address').fill(role+'@meraki.local');
  await page.getByLabel('Password',{exact:true}).fill(demoPassword());
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await expect(page.locator('.app-header')).toBeVisible();
  const toggle=page.getByRole('button',{name:'Dark mode',exact:true});
  await expect(toggle).toHaveAttribute('aria-pressed','true');
  if(role==='student'){await page.getByRole('link',{name:'Explore courses',exact:true}).click();await expect(page.locator('.course-card').first()).toBeVisible();}
  await page.screenshot({path:`output/midnight-${role}-dark.png`});
  await toggle.click();await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await page.reload();await expect(page.locator('.app-header')).toBeVisible();await expect(toggle).toHaveAttribute('aria-pressed','false');
  if(role==='student')await expect(page.locator('.course-card').first()).toBeVisible();
  await page.screenshot({path:`output/midnight-${role}-light.png`});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Toggle navigation'}).click();
  await expect(toggle).toBeVisible();await toggle.click();
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.getByRole('button',{name:'Toggle navigation'}).click();
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`output/midnight-${role}-mobile.png`});
  await context.close();
 }
 console.log('PASS: student, university and admin dark/light rendering, navigation toggle, persisted reload choice and 390px mobile switching/overflow.');
}finally{await browser.close()}
