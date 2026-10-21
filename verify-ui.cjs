const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge',args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1280,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:18765');
 const frame=page.frames().find(f=>f.url().includes('/overlay'));
 await frame.waitForFunction(()=>window.modelReady,{timeout:30000});
 await frame.locator('#enable').click();await page.waitForTimeout(700);
 await page.locator('#uid').fill('verify-'+Date.now());await page.locator('#enter').click();
 await frame.locator('#bubble.show').waitFor({timeout:30000});
 await page.waitForTimeout(400);await page.screenshot({path:'data/preview.png',fullPage:true});
 await frame.waitForFunction(()=>window.lastWelcome,{timeout:35000});
 await page.locator('#enter').click();await page.waitForTimeout(300);
 const result=await page.locator('#result').innerText();if(!result.includes('60 秒内'))throw Error('Cooldown failed: '+result);
 await page.locator('#mute').click();await page.waitForTimeout(700);await page.locator('#enter').click();await page.waitForTimeout(300);
 if(!(await page.locator('#result').innerText()).includes('暂停'))throw Error('Mute failed');await page.locator('#mute').click();
 console.log(JSON.stringify({modelReady:true,spoken:await frame.evaluate(()=>window.lastWelcome),cooldown:result,errors,voiceErrors:await frame.locator('#error').innerText()},null,2));
 await browser.close();if(errors.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
