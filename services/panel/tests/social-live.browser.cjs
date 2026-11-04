// Explicit production E2E: edits only the four requested accounts' categories.
if(process.env.CR_SOCIAL_LIVE_E2E!=='1'){console.error('Set CR_SOCIAL_LIVE_E2E=1 for this authorized live check');process.exit(2);}
const {chromium,request}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
let secret='',password='';
(async()=>{
 const out='/root/cryptoreport/services/social/validation/accounts-2026-10-16';fs.mkdirSync(out,{recursive:true});
 secret=fs.readFileSync('/root/.cryptoreport-panel-token','utf8').trim();password=fs.readFileSync('/root/.cryptoreport-panel-password','utf8').trim();
 const adminBase='http://127.0.0.1:8750/'+secret+'/';
 const anonymous=await request.newContext();assert.equal((await anonymous.get(adminBase+'api/social/accounts')).status(),401);await anonymous.dispose();
 const browser=await chromium.launch({args:['--no-sandbox']});const context=await browser.newContext({viewport:{width:1280,height:900}});const page=await context.newPage();const exceptions=[];
 page.on('pageerror',()=>exceptions.push('pageerror'));const report={authentication:'PASS',invalidInput:null,accounts:[],browser:[]};
 try{
  await page.goto(adminBase+'#creadores').catch(()=>{throw Error('admin_navigation_failed')});
  await page.locator('#pw').fill(password);await page.locator('#login-btn').click();await page.locator('[data-x-account="crediblecrypto"]').waitFor();
  assert.equal((await context.request.post(adminBase+'api/social/accounts',{data:{}})).status(),403);
  const listing=await page.evaluate(()=>fetch('api/social/accounts').then(r=>r.json()));
  const catalog='/root/cryptoreport/services/social/accounts.json';const before=fs.readFileSync(catalog);
  let invalid;for(let attempt=0;attempt<10;attempt++){invalid=await page.evaluate(async body=>{const r=await fetch('api/social/accounts',{method:'POST',headers:{'Content-Type':'application/json','X-Panel':'1'},body:JSON.stringify(body)});return {status:r.status};},{handle:'bulltheoryio',revision:listing.revision,lookback_days:0,enabled:true});if(invalid.status!==409)break;await page.waitForTimeout(4000);}
  assert.equal(invalid.status,422);assert.equal(before.equals(fs.readFileSync(catalog)),true);report.invalidInput='422 with unchanged catalog';
  for(const [handle,label] of [['bulltheoryio','Narrativas'],['bitcoinarchive','Bitcoin'],['watcherguru','Noticias'],['crediblecrypto','Mercados']]){
   let saved=false;
   for(let i=0;i<8&&!saved;i++){
    const row=page.locator(`[data-x-account="${handle}"]`);await row.locator('[data-x-label]').fill(label);
    const [res]=await Promise.all([page.waitForResponse(r=>r.url().endsWith('/api/social/accounts')&&r.request().method()==='POST'),row.locator('[data-x-save]').click()]);
    if(res.status()===409){await page.waitForTimeout(4000);continue;}
    assert.equal(res.status(),200);const data=await res.json();assert.equal(data.accounts.find(a=>a.handle===handle).label,label);saved=true;await page.waitForFunction(({handle,label})=>document.querySelector('[data-x-account="'+handle+'"] [data-x-label]')?.value===label,{handle,label});
   }
   assert.equal(saved,true,'admin edit must persist');report.accounts.push({handle,label,save:'PASS'});
  }
  await page.locator('#x-accounts').screenshot({path:out+'/admin-edited-1280.png'});
  await page.setViewportSize({width:390,height:844});await page.locator('#x-accounts').screenshot({path:out+'/admin-edited-390.png'});
  const overflow=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,elements:[...document.querySelectorAll('main,main>section,.card,#x-accounts,#creators')].map(e=>({tag:e.id||e.tagName,cls:e.className,width:e.getBoundingClientRect().width,scroll:e.scrollWidth}))}));fs.writeFileSync(out+'/admin-layout.json',JSON.stringify(overflow,null,2));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'admin mobile overflow');
  const base='https://communist-mature-gravity-deeper.trycloudflare.com';
  const res=await context.request.get(base+'/data/social-feed.json');assert.equal(res.status(),200);const feed=await res.json();
  assert.equal(feed.accounts.length,8);assert.equal(feed.status,'ok');
  for(const width of [390,1280]){
   await page.setViewportSize({width,height:844});
   for(const handle of ['bulltheoryio','bitcoinarchive','watcherguru','crediblecrypto']){
    await page.goto(base+'/b4-urania/#/feed?account='+handle+'&quality=todos');
    await page.locator(`[data-account="${handle}"][aria-pressed="true"]`).waitFor();await page.locator('[data-post]').first().waitFor();
    const ids=await page.locator('[data-post]').evaluateAll(es=>es.map(e=>e.dataset.post));
    const expected=feed.posts.filter(p=>p.author_handle===handle);const known=new Set(expected.map(p=>p.id));assert.ok(ids.every(id=>known.has(id)));
    const first=feed.posts.find(p=>p.id===ids[0]);await page.locator(`[data-post="${ids[0]}"]`).click();await page.locator('.fr-post-x').waitFor();
    const norm=x=>x.replace(/\s+/g,' ').trim();assert.equal(norm(await page.locator('.fr-post-x').innerText()),norm(first.text));
    assert.equal(await page.locator('.fr-post-open').getAttribute('href'),'https://x.com/i/web/status/'+first.id);
    await page.locator('[data-act="ficha-close"]').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    if(width===390)await page.screenshot({path:out+'/feed-'+handle+'-390.png'});
    report.browser.push({width,handle,published:expected.length,rendered:ids.length,authorAndTextFidelity:'PASS'});
   }
  }
  assert.equal(exceptions.length,0);report.exceptions=0;report.posts=feed.posts.length;report.status='PASS';
  fs.writeFileSync(out+'/e2e-live.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{await browser.close();}
})().catch(e=>{let s=String(e.message);if(secret)s=s.split(secret).join('[private]');if(password)s=s.split(password).join('[private]');console.error(s.slice(0,500));process.exit(1)});
