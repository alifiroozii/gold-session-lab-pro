const {chromium}=require('/Users/alifiroozi/.npm/_npx/420ff84f11983ee5/node_modules/playwright');
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});try{
 const p=await b.newPage(); const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto('http://127.0.0.1:8017/',{waitUntil:'domcontentloaded'});
 await p.locator('#sessionNowCards article').first().waitFor();
 if(await p.locator('#sessionNowCards article').count()!==6) throw Error('Missing session cards');
 await p.locator('#sessionHistoryDays').selectOption('30');
 await p.waitForResponse(r=>r.url().includes('/api/sessions/calendar?days=30'));
 const options=await p.locator('#sessionHistoryDate option').count();
 if(options<30) throw Error('Missing previous sessions');
 await p.locator('#sessionHistoryDate').selectOption({index:options-1});
 if(await p.locator('#sessionHistoryRows tr').count()!==6) throw Error('Missing history rows');
 for(const width of [1440,1024,390]){
  await p.setViewportSize({width,height:1100});await p.screenshot({path:`/tmp/goldlab-sessions-${width}.png`});
  console.log('viewport',width,'overflow',await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
 }
 await p.locator('[data-tab="tab-ai-research"]').click();
 await p.locator('#btnQueueSessionResearch').click();
 await p.locator('#sessionResearchStatus').filter({hasText:'6'}).waitFor();
 await p.screenshot({path:'/tmp/goldlab-research-mobile.png'});
 await p.reload({waitUntil:'domcontentloaded'});
 await p.locator('#sessionNowCards article').first().waitFor();
 await p.locator('[data-tab="tab-ai-research"]').click();
 await p.locator('#sessionResearchStatus').filter({hasText:'6'}).waitFor();
 console.log(JSON.stringify({cards:6,historyDays:options,persistentQueue:6,pageErrors:errors}));
 }finally{await b.close();}})().catch(e=>{console.error(e.message);process.exit(1)});
