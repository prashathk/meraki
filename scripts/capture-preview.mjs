import {demoPassword} from './local-config.mjs';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const browser=await chromium.launch({channel:'msedge',headless:true});
const base='http://127.0.0.1:8000';
const page=await browser.newPage({viewport:{width:1440,height:1000}});
await page.goto(base);await page.screenshot({path:'output/meraki-home-desktop.png',fullPage:true});
async function login(email){await page.goto(base+'/auth');await page.getByLabel('Email address').fill(email);await page.getByLabel('Password',{exact:true}).fill(demoPassword());await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('**/app');}
await login('student@meraki.local');await page.getByRole('button',{name:'Generate recommendations'}).click();await page.locator('.course-card').first().waitFor();await page.screenshot({path:'output/meraki-student-desktop.png',fullPage:true});
await page.setViewportSize({width:390,height:844});await page.screenshot({path:'output/meraki-student-mobile.png',fullPage:true});
await page.setViewportSize({width:1440,height:1000});await login('university@meraki.local');await page.getByRole('heading',{name:'Prepare courses for discovery.'}).waitFor();await page.getByRole('cell',{name:'BSc Artificial Intelligence',exact:false}).first().waitFor();await page.screenshot({path:'output/meraki-university-desktop.png',fullPage:true});
await login('admin@meraki.local');await page.getByRole('heading',{name:'Review course submissions.'}).waitFor();await page.locator('.review-row').first().click();await page.getByText('COURSE REVISION',{exact:true}).waitFor();await page.screenshot({path:'output/meraki-admin-desktop.png',fullPage:true});
await browser.close();console.log('Updated home, student/mobile, university and admin preview screenshots.');
