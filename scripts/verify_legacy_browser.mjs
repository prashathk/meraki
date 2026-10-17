import {demoPassword} from './local-config.mjs';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const browser=await chromium.launch({channel:'msedge',headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 await page.goto('http://127.0.0.1:8000/auth');
 await page.getByLabel('Email address').fill('student@meraki.local');
 await page.getByLabel('Password',{exact:true}).fill(demoPassword());
 await page.getByRole('button',{name:'Log in',exact:true}).click();
 await page.getByRole('heading',{name:'Find your next opportunity.'}).waitFor();
 await page.goto('http://127.0.0.1:8000/app/catalogue');
 await expect(page.getByText('Showing 1-12 of 211 courses')).toBeVisible();
 for(const [name,count] of [['University of Kelaniya',105],['University of Moratuwa',20],['University of Sri Jayewardenepura',86]]) {
  await page.getByLabel('University',{exact:true}).selectOption({label:name});
  await expect(page.getByText(`Showing 1-12 of ${count} courses`)).toBeVisible();
 }
 await page.getByLabel('University',{exact:true}).selectOption('');
 await page.getByLabel('Search courses').fill('Chemistry');
 await expect(page.locator('.course-card').first()).toBeVisible();
 await expect(page.locator('.course-card img')).toHaveCount(0);
 await page.screenshot({path:'output/legacy-student-catalogue.png',fullPage:true});
 await page.goto('http://127.0.0.1:8000/app/recommendations');
 await page.getByRole('button',{name:'Reset',exact:true}).click();
 await page.getByLabel('Search interests').fill('Chemistry');
 await page.locator('fieldset').first().getByRole('button',{name:'Chemistry',exact:true}).click();
 await page.getByLabel('Search aptitudes').fill('Mathematics');
 await page.locator('fieldset').nth(1).getByRole('button',{name:'Mathematics',exact:true}).click();
 await page.getByRole('button',{name:'Generate recommendations'}).click();
 await expect(page.locator('.course-card').first()).toBeVisible();
 await expect(page.locator('.match strong').first()).toHaveText('100%');
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'Download shortlist'}).click();
 await (await download).saveAs('output/legacy-student-shortlist.pdf');
 await page.screenshot({path:'output/legacy-student-recommendations.png',fullPage:false});
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'output/legacy-student-mobile.png',fullPage:false});
 console.log('PASS: 211 catalogue offerings; university counts 105/20/86; Chemistry search; image-free cards; Chemistry/Mathematics 100% match; PDF download; populated 390px mobile layout.');
} finally {await browser.close();}
