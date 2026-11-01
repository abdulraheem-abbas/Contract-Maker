'use strict';
const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const state = {boot:null,job:null,tab:'documents',view:'workspace',mode:'create',source:null,page:1,task:null,role:'offer',saving:false};
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let toastTimer,saveTimer;

async function api(path,body){
  const options={credentials:'same-origin',headers:{}};
  if(body!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-Private-CSRF':state.boot.csrf};options.body=JSON.stringify(body);}
  const response=await fetch(path,options);
  const data=await response.json();
  if(!response.ok){const error=new Error(data.error||'This action could not finish.');error.findings=data.findings;throw error;}
  return data;
}
function toast(message,error=false){clearTimeout(toastTimer);const el=$('#toast');el.textContent=message;el.classList.remove('hidden');el.classList.toggle('error',error);toastTimer=setTimeout(()=>el.classList.add('hidden'),6500);}
function setView(view){
  state.view=view;
  for(const name of ['workspace','job','templates','setup'])$(`#${name}-view`).classList.toggle('hidden',name!==view);
  $$('.nav').forEach(n=>n.classList.toggle('active',n.dataset.nav===(view==='job'?'workspace':view)));
  $('#breadcrumb').textContent=({workspace:'My workspace',job:'My workspace / Contract details',templates:'Templates & rules',setup:'Local setup'})[view];
  if(view==='workspace')renderJobs();
  if(view==='templates')renderTemplates();
  if(view==='setup')renderSetup();
  window.scrollTo({top:0,behavior:'instant'});
}
function dateLabel(value){try{return new Date(value).toLocaleDateString('en-GB',{day:'numeric',month:'short'});}catch{return '';}}
function renderJobs(){
  const jobs=state.boot.jobs;
  $('#work-count').textContent=jobs.length?`${jobs.length} saved ${jobs.length===1?'workspace':'workspaces'}`:'Saved on this computer';
  if(!jobs.length)return;
  $('#job-list').innerHTML=jobs.map(job=>`<button class="job-row" data-job="${job.id}"><span class="row-icon">▤</span><span class="row-title"><strong dir="auto">${escapeHTML(job.title)}</strong><small>Saved locally</small></span><span class="status-chip">Continue work</span><span class="row-date">${dateLabel(job.updated)}</span><span>↗</span></button>`).join('');
}
function enginePill(engine){
  state.boot.engine=engine;
  const el=$('#engine-pill');el.classList.toggle('ready',engine.model_ready);el.textContent=engine.model_ready?'Local AI ready':engine.running?'Model download needed':'Local AI is stopped';
  $$('.read-ai').forEach(b=>b.disabled=!!state.task||!engine.model_ready);
}
async function refreshBootstrap(){const csrf=state.boot?.csrf;state.boot=await api('/api/bootstrap');enginePill(state.boot.engine);if(csrf&&csrf!==state.boot.csrf)toast('The local app restarted. Your saved work is safe.');}
function newDialog(mode){state.mode=mode;$('#new-mode-label').textContent=mode==='review'?'NEW REVIEW':'NEW CONTRACT';$('#new-dialog').showModal();}
async function openJob(id){
  clearTimeout(saveTimer);state.job=await api('/api/job?id='+encodeURIComponent(id));state.source=state.job.sources[0]||null;state.page=1;
  renderJob();setView('job');setTab(state.job.mode==='review'&&state.job.findings.length?'findings':'documents');
}
function setTab(tab){
  state.tab=tab;
  for(const name of ['documents','details','findings','outputs'])$(`#${name}-panel`).classList.toggle('hidden',name!==tab);
  $$('.tab').forEach(el=>el.classList.toggle('active',el.dataset.tab===tab));
  if(tab==='details')renderViewer();
}
function fieldValue(key){return state.job?.fields[key]?.value||'';}
function requiredFields(){
  const kind=fieldValue('contract_type');
  const common=['contract_type','name_ar','name_en','gender','identity_type','identity_number','identity_issue_date','execution_date','start_date','end_date','job_title_ar','job_title_en','workplace_ar','workplace_en','salary_usd','manager_title_ar','manager_title_en'];
  let required=kind==='employment'?[...common,'grade_ar','grade_en']:kind==='service'?[...common,'manager_name_ar','manager_name_en','project_ar','project_en']:['contract_type','name_ar','name_en','execution_date','start_date','end_date','original_contract_date'];
  return [...new Set([...required,...(state.boot.templates[kind]?.required_fields||[])])];
}
function updateCounts(){
  if(!state.job)return;
  const required=requiredFields();const confirmed=required.filter(k=>state.job.fields[k].confirmed&&state.job.fields[k].value).length;
  $('#source-count').textContent=state.job.sources.length;$('#confirmed-count').textContent=`${confirmed}/${required.length}`;
  $('#finding-count').textContent=state.job.findings.filter(f=>f.level!=='pass').length;$('#output-count').textContent=state.job.outputs.length;
}
function renderJob(){
  const kind=fieldValue('contract_type');$('#job-kind').textContent=`${kind.toUpperCase()} ${state.job.mode==='review'?'REVIEW':'CONTRACT'}`;
  $('#job-title').textContent=state.job.title;
  $('#main-action').innerHTML=state.job.mode==='review'?'Review contract <span>↗</span>':'Create Word &amp; PDF <span>↗</span>';
  $('#employee-hint').value=state.job.employee_hint||'';$('#list-row').value=state.job.list_row||'';
  renderSources();renderFields();renderFindings();renderOutputs();updateCounts();
}
function renderSources(){
  const cards=[['offer','▤','Job offer','Contract type, role, salary and dates.'],['identity','◫','ID or passport','Full name, document number and issuing details.'],['list','▦','Employee list','Workplace and reporting manager.']];
  if(state.job.mode==='review')cards.push(['contract','✓','Contract to review','The existing contract you want to check.']);
  $('#source-cards').innerHTML=cards.map(([role,icon,title,description])=>{
    const sources=state.job.source_details.filter(s=>s.role===role);
    return `<article class="source-card ${sources.length?'has-file':''}" data-drop-role="${role}"><span class="source-symbol">${icon}</span><h3>${title}</h3><p>${description}</p>${sources.map(s=>`<button class="source-file" data-preview="${s.id}">${escapeHTML(s.name)}<small>${s.pages.length} ${s.pages.length===1?'page':'pages'} · local copy</small></button>`).join('')}<button class="button secondary" data-add-role="${role}">${sources.length?'Add another file':'Choose file'} ＋</button></article>`;
  }).join('');
  $$('.source-card').forEach(el=>{
    el.addEventListener('dragover',event=>{event.preventDefault();el.classList.add('drop-hover');});
    el.addEventListener('dragleave',()=>el.classList.remove('drop-hover'));
    el.addEventListener('drop',event=>{event.preventDefault();el.classList.remove('drop-hover');if(event.dataTransfer.files[0])importFile(event.dataTransfer.files[0],el.dataset.dropRole).catch(handleError);});
  });
}
const fieldGroups=[
 ['Contract & identity',['contract_type','name_ar','name_en','gender','identity_type','identity_number','identity_issue_date','identity_expiry_date','issuer_ar','issuer_en']],
 ['Dates & pay',['execution_date','start_date','end_date','original_contract_date','salary_usd']],
 ['Role & workplace',['job_title_ar','job_title_en','grade_ar','grade_en','workplace_ar','workplace_en']],
 ['Reporting & project',['manager_title_ar','manager_title_en','manager_name_ar','manager_name_en','manager_base_ar','manager_base_en','project_ar','project_en']]
];
function visibleField(key){
  const kind=fieldValue('contract_type');
  if(key==='original_contract_date'&&kind!=='extension')return false;
  if(kind==='extension'&&!requiredFields().includes(key)&&!['issuer_ar','issuer_en','identity_expiry_date'].includes(key))return false;
  if(kind==='employment'&&['manager_name_ar','manager_name_en','manager_base_ar','manager_base_en','project_ar','project_en'].includes(key))return false;
  if(kind==='service'&&key.startsWith('grade_'))return false;
  return true;
}
function renderFields(){
  const specs=Object.fromEntries(state.boot.fields.map(s=>[s[0],s]));const required=requiredFields();
  $('#fields-form').innerHTML=fieldGroups.map(([label,keys])=>`<section class="field-group"><h3>${label}</h3>${keys.filter(visibleField).map(key=>{
    const [_,english,arabic,type]=specs[key];const field=state.job.fields[key];
    let input;
    if(type==='select'){
      const options=key==='contract_type'?[['employment','Employment contract · عقد عمل'],['service','Service contract · عقد خدمة'],['extension','Extension letter · خطاب تمديد']]:key==='gender'?[['','Not supplied'],['male','Male · ذكر'],['female','Female · أنثى']]:[['','Choose document type'],['id_card','ID card · بطاقة شخصية'],['national_id','ID with national number · الرقم الوطني'],['passport','Passport · جواز سفر']];
      input=`<select class="field-input" id="field-${key}" data-field="${key}">${options.map(([v,l])=>`<option value="${v}" ${field.value===v?'selected':''}>${escapeHTML(l)}</option>`).join('')}</select>`;
    }else input=`<input class="field-input" id="field-${key}" data-field="${key}" type="${type==='date'?'date':'text'}" dir="${key.endsWith('_ar')?'rtl':'ltr'}" value="${escapeHTML(field.value)}" autocomplete="off" ${key==='salary_usd'?'inputmode="decimal"':''}>`;
    const evidence=(field.evidence||[]).map((e,i)=>`<button class="evidence-link" data-evidence="${key}" data-index="${i}">↗ ${escapeHTML(e.source_name)} · p${e.page}${e.text_match===false?' · inspect image':''}</button>`).join('');
    const alternatives=(field.alternatives||[]).map((a,i)=>`<button class="evidence-link" data-alternative="${key}" data-index="${i}">Alternative: ${escapeHTML(a.value)}</button>`).join('');
    return `<div class="field-row ${field.confirmed?'confirmed':''}" data-row="${key}"><div class="field-label"><label for="field-${key}"><span>${english}${required.includes(key)?'<b class="required-star">*</b>':''}</span><br><small lang="ar" dir="rtl">${arabic}</small></label><label class="confirm-label"><input type="checkbox" data-confirm="${key}" ${field.confirmed?'checked':''} ${!field.value?'disabled':''}>Checked</label></div>${input}<div class="field-evidence">${evidence}${alternatives}<span class="field-origin">${escapeHTML(field.note||field.origin||'Enter or read from a source')}</span></div></div>`;
  }).join('')}</section>`).join('');
}
function savePayload(){return {job:state.job.id,fields:state.job.fields,employee_hint:$('#employee-hint').value,list_row:$('#list-row').value};}
async function saveJob(silent=true){
  if(!state.job)return;clearTimeout(saveTimer);
  const saved=await api('/api/save',savePayload());state.job.title=saved.title;$('#job-title').textContent=saved.title;$('#saved-status').textContent='Saved on this computer';
  if(!silent)toast('Your work is saved locally.');
}
function queueSave(){clearTimeout(saveTimer);$('#saved-status').textContent='Saving locally…';saveTimer=setTimeout(()=>saveJob().catch(handleError),800);}
async function importFile(file,role){
  if(state.task)throw new Error('Wait for the current task to finish first.');
  if(file.size>25*1024*1024)throw new Error('Choose a file up to 25 MB.');
  await saveJob();
  const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
  const result=await api('/api/import',{job:state.job.id,role,name:file.name,data});
  await watchTask(result.task);
  toast('Document added to this local workspace.');
}
async function watchTask(taskId){
  state.task=taskId;clearTimeout(saveTimer);$('#task-banner').classList.remove('hidden');$('#main-action').disabled=true;$$('.read-ai').forEach(b=>b.disabled=true);$$('#fields-form input,#fields-form select,#employee-hint,#list-row,#confirm-visible,#save-job').forEach(b=>b.disabled=true);
  try{
    while(true){
      const task=await api('/api/task?id='+taskId);$('#task-title').textContent=task.label;$('#task-message').textContent=task.message;
      if(task.status==='error')throw new Error(task.message);
      if(task.status==='complete'||task.status==='cancelled'){
        if(task.result?.job){const oldTab=state.tab;state.job=await api('/api/job?id='+task.result.job);renderJob();setTab(oldTab);}
        if(task.result?.pdf_error)toast(task.result.pdf_error,true);
        return task.result;
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  }finally{state.task=null;$('#task-banner').classList.add('hidden');$('#main-action').disabled=false;$$('#fields-form input,#fields-form select,#employee-hint,#list-row,#confirm-visible,#save-job').forEach(b=>b.disabled=false);if(state.job)renderFields();enginePill(state.boot.engine);}
}
async function readAI(){
  if(!state.job.sources.length)throw new Error('Add the source documents first, or enter details manually.');
  const result=await api('/api/extract',savePayload());await watchTask(result.task);setTab('details');
  toast('Suggestions are ready. Check each value against its source before confirming it.');
}
function selectedSource(){return state.job?.source_details.find(s=>s.id===state.source);}
function renderViewer(quote=''){
  if(!state.job)return;
  const sources=state.job.source_details;
  if(!state.source&&sources.length)state.source=sources[0].id;
  $('#viewer-source').innerHTML=sources.map(s=>`<option value="${s.id}" ${s.id===state.source?'selected':''}>${escapeHTML(s.name)}</option>`).join('');
  const source=selectedSource();const target=$('#viewer-content');
  if(!source){target.innerHTML='<div class="viewer-empty">Add a source document first.<br>Its pages will appear here.</div>';return;}
  state.page=Math.min(Math.max(state.page,1),source.pages.length);const page=source.pages[state.page-1];
  $('#page-number').textContent=`Page ${state.page} of ${source.pages.length}`;
  $('#prev-page').disabled=state.page<=1;$('#next-page').disabled=state.page>=source.pages.length;
  $('#evidence-quote').classList.toggle('hidden',!quote);$('#evidence-quote').textContent=quote?'Quoted evidence: '+quote:'';
  if(page.image)target.innerHTML=`<img src="/api/page?source=${source.id}&page=${state.page}" alt="Source document page ${state.page}" loading="eager">`;
  else target.innerHTML=`<pre dir="auto">${escapeHTML(page.text)}</pre>`;
}
function renderFindings(){
  const findings=state.job.findings;const counts={error:0,warning:0,pass:0};findings.forEach(f=>counts[f.level]=(counts[f.level]||0)+1);
  $('#findings-summary').innerHTML=findings.length?Object.entries(counts).map(([level,n])=>`<div class="summary-item"><strong>${n}</strong><span>${{error:'Needs correction',warning:'Needs your review',pass:'Matching checks'}[level]}</span></div>`).join(''):'';
  const labels=Object.fromEntries(state.boot.fields.map(s=>[s[0],s[1]]));
  $('#findings-list').innerHTML=findings.length?[...findings].sort((a,b)=>['error','warning','pass'].indexOf(a.level)-['error','warning','pass'].indexOf(b.level)).map(f=>`<article class="finding ${f.level}"><span class="finding-icon">${{error:'!',warning:'!',pass:'✓'}[f.level]}</span><div><h3>${escapeHTML(labels[f.field]||f.field||'Document')}</h3><p>${escapeHTML(f.message)}</p>${f.expected?`<p dir="auto">Expected: ${escapeHTML(f.expected)}</p>`:''}</div><small>${f.page?'Page '+f.page:'Check field'}</small></article>`).join(''):'<div class="empty-state"><span>✓</span><h3>No checks run yet</h3><p>Complete the expected fields, then run checks or review the existing contract.</p></div>';
}
function renderOutputs(){
  const outputs=state.job.outputs;
  $('#bundle-link').classList.toggle('hidden',!outputs.length);$('#bundle-link').href='/api/bundle?job='+state.job.id;
  $('#visual-review-note').classList.toggle('hidden',!outputs.length);
  $('#outputs-list').innerHTML=outputs.length?[...outputs].reverse().map(name=>{const ext=name.split('.').pop().toLowerCase();const url='/api/file?job='+state.job.id+'&name='+encodeURIComponent(name);return `<article class="output-card"><span class="file-type ${ext}">${ext.toUpperCase()}</span><div class="output-info"><strong dir="auto">${escapeHTML(name)}</strong><p>${ext==='json'?'Confirmed fields and source record':'Saved in your local workspace'}</p></div>${['pdf','html'].includes(ext)?`<a class="button secondary" href="${url}" target="_blank" rel="noopener">Open ↗</a>`:''}<a class="button secondary" href="${url}&download=1">Save copy ↓</a></article>`;}).join(''):'<div class="empty-state"><span>▤</span><h3>Your finished files will appear here</h3><p>Confirm the required fields, then create the contract or finish its review.</p></div>';
}
async function checkFields(){
  const result=await api('/api/check',savePayload());state.job.findings=result.findings;renderFindings();updateCounts();setTab('findings');return result.findings;
}
async function mainAction(acknowledge=false){
  clearTimeout(saveTimer);
  if(state.job.mode==='review'){const result=await api('/api/review',savePayload());await watchTask(result.task);setTab('findings');return;}
  const issues=await api('/api/check',savePayload());const errors=issues.findings.filter(f=>f.level==='error');
  if(errors.length){state.job.findings=issues.findings;renderFindings();updateCounts();setTab('findings');throw new Error('Complete the missing or invalid fields first.');}
  const unconfirmed=requiredFields().filter(k=>!state.job.fields[k].confirmed);
  if(unconfirmed.length){setTab('details');throw new Error(`Check and confirm the ${unconfirmed.length} remaining required fields first.`);}
  const warnings=issues.findings.filter(f=>f.level==='warning');
  if(warnings.length&&!acknowledge){$('#warning-content').innerHTML=warnings.map(f=>`<article class="finding warning"><span class="finding-icon">!</span><p>${escapeHTML(f.message)}</p></article>`).join('');$('#acknowledge-warnings').checked=false;$('#create-confirmed').disabled=true;$('#warning-dialog').showModal();return;}
  const result=await api('/api/generate',{...savePayload(),acknowledge_warnings:acknowledge});await watchTask(result.task);setTab('outputs');toast('The contract files are ready. Open the PDF for a final page check.');
}
function renderTemplates(){
  $('#templates-list').innerHTML=Object.entries(state.boot.templates).map(([kind,template])=>`<article class="template-card"><span class="source-symbol">▤</span><h3>${escapeHTML(template.label)}</h3><p>${{employment:'عقد عمل',service:'عقد خدمة',extension:'خطاب تمديد'}[kind]}</p><span class="status-chip">${template.placeholders?.length?'Configured locally':'Needs field mapping'}</span><button class="button secondary" data-template="${kind}">View template fields ↗</button></article>`).join('');
  $('#override-list').innerHTML=(state.boot.rules.job_title_overrides||[]).map(r=>`<div class="override-row"><strong dir="rtl">${escapeHTML(r.name_ar)}</strong><span>${escapeHTML(r.job_title_en)}</span></div>`).join('')||'<p>No individual overrides saved.</p>';
}
async function templateEditor(kind){
  const result=await api('/api/template-editor?kind='+kind);const editor=$('#template-editor');editor.classList.remove('hidden');
  editor.innerHTML=`<h2>${escapeHTML(kind[0].toUpperCase()+kind.slice(1))} template fields</h2><p class="subtle">Map only the text that should be filled. Original wording outside those fields is retained. A previous copy is kept.</p><form class="mapping-form" id="mapping-form"><label>Paragraph<input id="map-paragraph" type="number" min="0" required></label><label>Exact text to replace<input id="map-before" required></label><label>Fill with field<select id="map-key">${result.tokens.map(t=>`<option value="${t}">${escapeHTML(state.boot.fields.find(f=>f[0]===t)?.[1]||t.replaceAll('_',' '))}</option>`).join('')}</select></label><button class="button primary" type="submit">Save mapping</button></form><div>${result.paragraphs.map(p=>`<div class="template-paragraph" data-paragraph="${p.index}" dir="auto"><small class="subtle">Paragraph ${p.index}</small><br>${escapeHTML(p.text)}</div>`).join('')}</div>`;
  $('#mapping-form').addEventListener('submit',async event=>{event.preventDefault();try{await api('/api/template-save',{kind,mappings:[{paragraph:$('#map-paragraph').value,before:$('#map-before').value,key:$('#map-key').value}]});await refreshBootstrap();renderTemplates();await templateEditor(kind);toast('Template field mapping saved locally.');}catch(error){handleError(error);}});
  $$('.template-paragraph').forEach(el=>el.addEventListener('mouseup',()=>{const selected=window.getSelection().toString();if(selected){$('#map-paragraph').value=el.dataset.paragraph;$('#map-before').value=selected;}}));
  editor.scrollIntoView({behavior:'smooth'});
}
function renderSetup(){
  const e=state.boot.engine;const download=e.download;
  $('#setup-cards').innerHTML=`<article class="setup-card"><span class="status-chip">${e.model_ready?'Ready on this computer':e.running?'Engine running':'Engine stopped'}</span><h3>Local AI</h3><p>${escapeHTML(e.model)}<br>Cloud features disabled.<br>Processes one document page at a time.</p>${!e.running?'<button class="button secondary" id="start-engine">Start local engine</button>':''}${download?.percent!==undefined&&download.percent!==null?`<progress value="${download.percent}" max="100"></progress><p>Downloading model file: ${download.percent}%</p>`:''}</article><article class="setup-card"><span class="status-chip">${state.boot.ocr?'Installed':'Not installed yet'}</span><h3>Scanned text recognition</h3><p>Arabic and English OCR runs locally. The vision model can also read page images; uncertain names and numbers need checking.</p></article><article class="setup-card"><span class="status-chip">${state.boot.pdf_export?'Available locally':'Setup required'}</span><h3>Word &amp; PDF</h3><p>Your Word templates keep their layout. LibreOffice creates the PDF for a final visual page check.</p></article>`;
  $('#start-engine')?.addEventListener('click',async()=>{try{const result=await api('/api/start-engine',{});await watchTask(result.task);await refreshBootstrap();renderSetup();toast('Local AI engine started.');}catch(error){handleError(error);}});
}
function handleError(error){if(error.findings&&state.job){state.job.findings=error.findings;renderFindings();updateCounts();}toast(error.message||'The action could not finish.',true);}

document.addEventListener('click',async event=>{
  const nav=event.target.closest('[data-nav]');if(nav){if(state.job)await saveJob().catch(handleError);await refreshBootstrap().catch(handleError);setView(nav.dataset.nav);}
  const start=event.target.closest('[data-new]');if(start)newDialog(start.dataset.new);
  const tab=event.target.closest('[data-tab]');if(tab&&state.job)setTab(tab.dataset.tab);
  const job=event.target.closest('[data-job]');if(job)openJob(job.dataset.job).catch(handleError);
  const add=event.target.closest('[data-add-role]');if(add){state.role=add.dataset.addRole;$('#file-picker').click();}
  const preview=event.target.closest('[data-preview]');if(preview){state.source=preview.dataset.preview;state.page=1;setTab('details');renderViewer();}
  const evidence=event.target.closest('[data-evidence]');if(evidence){const e=state.job.fields[evidence.dataset.evidence].evidence[+evidence.dataset.index];state.source=e.source_id;state.page=e.page;renderViewer(e.quote);}
  const alternative=event.target.closest('[data-alternative]');if(alternative){const key=alternative.dataset.alternative;const value=state.job.fields[key].alternatives[+alternative.dataset.index];state.job.fields[key]={value:value.value,confirmed:false,origin:'selected source value',evidence:[value]};renderFields();queueSave();}
  const template=event.target.closest('[data-template]');if(template)templateEditor(template.dataset.template).catch(handleError);
  if(event.target.closest('.close-dialog'))event.target.closest('dialog').close();
  if(event.target.closest('.read-ai'))readAI().catch(handleError);
});
document.addEventListener('input',event=>{
  const key=event.target.dataset.field;
  if(key&&state.job){state.job.fields[key].value=event.target.value;state.job.fields[key].confirmed=false;state.job.fields[key].origin='entered by you';const row=event.target.closest('.field-row');row.classList.remove('confirmed');const check=$('[data-confirm]',row);check.checked=false;check.disabled=!event.target.value;updateCounts();queueSave();}
  if(['employee-hint','list-row'].includes(event.target.id))queueSave();
});
document.addEventListener('change',event=>{
  const key=event.target.dataset.confirm;
  if(key&&state.job){state.job.fields[key].confirmed=event.target.checked;event.target.closest('.field-row').classList.toggle('confirmed',event.target.checked);updateCounts();queueSave();}
  if(event.target.dataset.field==='contract_type'){renderFields();updateCounts();}
});
$('#new-form').addEventListener('submit',async event=>{event.preventDefault();try{const job=await api('/api/new',{mode:state.mode,kind:$('#new-kind').value});$('#new-dialog').close();await refreshBootstrap();await openJob(job.id);}catch(error){handleError(error);}});
$('#file-picker').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)importFile(file,state.role).catch(handleError);});
$('#save-job').addEventListener('click',()=>saveJob(false).catch(handleError));
$('#back-workspace').addEventListener('click',async()=>{await saveJob().catch(handleError);await refreshBootstrap();setView('workspace');});
$('#main-action').addEventListener('click',()=>mainAction().catch(handleError));
$('#create-confirmed').addEventListener('click',()=>{$('#warning-dialog').close();mainAction(true).catch(handleError);});
$('#acknowledge-warnings').addEventListener('change',event=>$('#create-confirmed').disabled=!event.target.checked);
$('#confirm-visible').addEventListener('click',()=>{for(const [key,field]of Object.entries(state.job.fields)){if(field.value&&visibleField(key))field.confirmed=true;}renderFields();updateCounts();queueSave();toast('Filled fields marked as checked. You can uncheck any field that needs another look.');});
$('#check-fields').addEventListener('click',()=>checkFields().catch(handleError));
$('#quit-app').addEventListener('click',async()=>{try{if(state.job)await saveJob();await api('/api/shutdown',{});document.body.innerHTML='<main><h1>Private Contracts is closed.</h1><p>Your work is saved on this Mac. You can close this tab and reopen the app whenever you need it.</p></main>';}catch(error){handleError(error);}});
$('#viewer-source').addEventListener('change',event=>{state.source=event.target.value;state.page=1;renderViewer();});
$('#prev-page').addEventListener('click',()=>{state.page--;renderViewer();});
$('#next-page').addEventListener('click',()=>{state.page++;renderViewer();});
$('#cancel-task').addEventListener('click',async()=>{if(state.task){await api('/api/cancel',{task:state.task});$('#task-message').textContent='Stopping after the current page. Any completed suggestions are retained.';}});
window.addEventListener('beforeunload',event=>{if(state.task){event.preventDefault();event.returnValue='A local operation is still running.';}});
async function init(){
  try{await refreshBootstrap();$('#today').textContent=new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',year:'numeric'}).toUpperCase();renderJobs();}
  catch(error){$('#job-list').innerHTML='<div class="empty-state"><h3>The local app is starting</h3><p>Reload this window in a moment. Your files remain on this computer.</p></div>';handleError(error);}
}
init();
