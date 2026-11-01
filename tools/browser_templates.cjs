// Run against a disposable local workspace described in test-results/template-ui-config.json.
const {chromium}=require('./browser_runtime.cjs');
const fs=require('fs');const path=require('path');const assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const config=JSON.parse(fs.readFileSync(path.join(root,'test-results/template-ui-config.json'),'utf8'));
const base=new URL(config.base);assert.equal(base.hostname,'127.0.0.1');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CONTRACTS_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const context=await browser.newContext({baseURL:config.base,viewport:{width:1440,height:1050}});
  const external=[];const errors=[];const failed=[];
  await context.route('**/*',route=>{const url=route.request().url();if(!url.startsWith(config.base+'/')&&!url.startsWith('data:')&&!url.startsWith('chrome-extension:')){external.push(url);return route.abort();}return route.continue();});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)failed.push({status:r.status(),url:r.url()});});
  await page.goto(config.base);await page.waitForFunction(()=>document.querySelector('#engine-pill').textContent!=='Checking local AI…');
  assert.equal(await page.locator('.sidebar').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(52, 58, 61)');
  assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--nmo-turquoise').trim()),'#3bc1cc');
  await page.screenshot({path:path.join(root,'test-results/nmo-home.png'),fullPage:true});
  await page.locator('nav [data-nav="templates"]').click();
  await page.locator('[data-template-card="employment"]').waitFor();
  assert.equal(await page.locator('[data-template-card]').count(),3);
  await page.screenshot({path:path.join(root,'test-results/nmo-templates.png'),fullPage:true});
  const initial=await page.evaluate(async()=> (await (await fetch('/api/bootstrap')).json()).templates.employment.sha256);
  await page.locator('[data-replace-template="employment"]').first().click({noWaitAfter:true});
  await page.locator('#template-picker').setInputFiles(config.replacement);
  await page.locator('#template-editor').waitFor({state:'visible'});
  await page.locator('#template-editor .eyebrow').filter({hasText:'DRAFT'}).waitFor();
  assert(await page.locator('.template-check.error').count()>0);
  await page.locator('#template-reviewed').check();assert(await page.locator('#activate-template').isDisabled());
  const afterImport=await page.evaluate(async()=> (await (await fetch('/api/bootstrap')).json()).templates.employment.sha256);assert.equal(initial,afterImport);
  // Both occurrences of the Arabic name have to be mapped separately.
  for(const index of ['2','15']){
   await page.locator('#map-paragraph').fill(index);await page.locator('#map-before').fill('اسم تجريبي للتعيين');await page.locator('#map-key').selectOption('name_ar');
   await page.locator('#mapping-form button').click();await page.waitForFunction(()=>!document.querySelector('#mapping-form button').disabled);
   await page.waitForTimeout(100);
  }
  assert.equal(await page.locator('.template-check.error').count(),0);
  await page.locator('#preview-template').click();await page.locator('#template-page-image').waitFor({timeout:120000});
  await page.waitForFunction(()=>{const img=document.querySelector('#template-page-image');return img?.complete&&img.naturalWidth>500;});
  const previewResponse=await context.request.get(await page.locator('#template-preview a').getAttribute('href'));
  assert.equal(previewResponse.status(),200);assert.equal(previewResponse.headers()['content-type'],'application/pdf');
  await page.locator('#template-reviewed').check();await page.screenshot({path:path.join(root,'test-results/nmo-template-draft.png'),fullPage:true});
  await page.locator('#activate-template').click();await page.locator('#template-editor .eyebrow').filter({hasText:'CURRENT TEMPLATE'}).waitFor();
  const active=await page.evaluate(async()=> (await (await fetch('/api/bootstrap')).json()).templates.employment);
  assert.notEqual(active.sha256,initial);assert.equal(active.history_count,1);
  await page.locator('.template-history summary').click();await page.locator('[data-restore-template]').first().click();
  await page.locator('#template-reviewed').check();await page.locator('#activate-template').click();await page.locator('#template-editor .eyebrow').filter({hasText:'CURRENT TEMPLATE'}).waitFor();
  const restored=await page.evaluate(async()=> (await (await fetch('/api/bootstrap')).json()).templates.employment);assert.equal(restored.sha256,initial);assert.equal(restored.history_count,2);
  await page.setViewportSize({width:390,height:844});await page.locator('nav [data-nav="templates"]').click();
  await page.locator('#close-template').click();
  const width=await page.evaluate(()=>({body:document.documentElement.scrollWidth,viewport:innerWidth}));assert(width.body<=width.viewport);
  await page.screenshot({path:path.join(root,'test-results/nmo-templates-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.deepEqual(failed,[]);
  const result={template_upload:'draft only',field_mapping:'both repeated Arabic names mapped',local_pdf_preview:'passed',activation:'passed',restore:'passed',nmo_colors:'verified',mobile_overflow:false,browser_errors:errors,external_requests:external};
  fs.writeFileSync(path.join(root,'test-results/template-ui-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
