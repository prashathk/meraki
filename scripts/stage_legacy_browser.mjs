import {demoPassword} from './local-config.mjs';
import {createRequire} from 'node:module';
import path from 'node:path';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 await page.goto('http://127.0.0.1:8000/auth');await page.getByLabel('Email address').fill('admin@meraki.local');await page.getByLabel('Password',{exact:true}).fill(demoPassword());await page.getByRole('button',{name:'Log in',exact:true}).click();
 await page.getByRole('link',{name:'Prototype migration',exact:true}).click();
 await page.getByLabel('Original ontology file').setInputFiles(path.resolve('backend/fixtures/prototype-ontology.owl'));
 await page.getByRole('button',{name:'Preview migration',exact:true}).click();
 await expect(page.getByText('211',{exact:true})).toBeVisible({timeout:30000});
 await page.screenshot({path:'output/legacy-migration-preview.png',fullPage:true});
 const staged=page.getByRole('button',{name:'Staged for review',exact:true});
 if(!(await staged.count()))await page.getByRole('button',{name:'Stage resolved offerings',exact:true}).click();
 await expect(staged).toBeVisible({timeout:30000});
 await page.getByRole('link',{name:'Open review queue',exact:true}).click();
 await expect(page.locator('.review-row').first()).toBeVisible();await page.locator('.review-row').first().click();
 await page.screenshot({path:'output/legacy-migration-review.png',fullPage:true});
 console.log('Browser verified original ontology upload, 211-offering preview, staging and admin review detail. No publication bypass.');
}finally{await browser.close()}
