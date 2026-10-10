'use strict';
const $ = id => document.getElementById(id);
const workspace = location.pathname === '/separator';
let selectedFile = null, requestKey = null, sending = false, selectedJob = null, resultVersion = null, polling = false;
const terminal = new Set(['completed', 'failed', 'cancelled']);
const labels = {ready:'Ready',stopped:'Stopped',starting:'Starting',busy:'Processing',stopping:'Stopping',error:'Needs attention'};
const node = (tag, text, className) => { const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(className) el.className=className; return el; };
function notice(message) { $('notice').textContent=message; $('notice').hidden=!message; }
async function api(path, options={}) { const response=await fetch(path, options); let data; try {data=await response.json();} catch {throw new Error('The controller returned an invalid response.');} if(!response.ok) { const e=new Error(typeof data.detail==='string'?data.detail:'Invalid request. Check your selection.'); e.status=response.status; throw e;} return data; }
function badge(state) {return node('span',labels[state]||state,'status '+state);}
function size(bytes) {return (bytes/1024/1024).toFixed(1)+' MB';}
if(workspace) { $('overview').hidden=true; $('workspace').hidden=false; $('title').textContent='Make room for every stem.'; $('subtitle').textContent='Upload. Separate. Listen. All on your own hardware.'; $('crumb').textContent='Audio Separator'; }
$(workspace?'nav-separator':'nav-dashboard').classList.add('active');
for(let i=0;i<80;i++) { const bar=node('i'); bar.style.height=(6+Math.abs(Math.sin(i*1.37)*Math.cos(i*.19))*45)+'px'; document.querySelector('.waveform').append(bar); }
async function serviceAction(service, action, button) {
  button.disabled=true; notice('');
  try {
    let confirmStop = false;
    if(service==='applio' && action==='stop') { if(!confirm('Stop Applio? Any voice conversion running in its interface will be interrupted.')) return; }
    try { await api(`/api/services/${service}/${action}`, {method:'POST'}); }
    catch(e) { if(e.status!==409||action!=='stop') throw e; confirmStop=confirm(e.message); if(confirmStop) await api(`/api/services/${service}/stop?confirm=true`,{method:'POST'}); }
    await poll();
  } catch(e) {notice(e.message);} finally {button.disabled=false;}
}
document.querySelectorAll('[data-service]').forEach(button=>button.addEventListener('click',()=>serviceAction(button.dataset.service,button.dataset.action,button)));
function renderServices(services) {
  for(const name of ['separator','applio']) {
    const info=services[name], state=$(name+'-state'); state.textContent=labels[info.state]||info.state; state.className='status '+info.state;
    $(name+'-detail').textContent=info.error || (info.installed===false?'Not installed · open Setup & models to install':name==='applio' && info.state==='ready' ? 'Interface available · manage conversion jobs in Applio' : info.state==='stopped' ? 'Offline · no inference processes running' : info.state==='ready' ? 'Ready for your next session' : info.state==='busy' ? 'Processing audio · see your session below' : 'Waiting for service readiness');
    document.querySelectorAll(`[data-service="${name}"]`).forEach(button=>{ if(!sending) button.disabled=info.installed===false||(button.dataset.action==='start'?['starting','ready','busy','stopping'].includes(info.state):['stopped','stopping'].includes(info.state)); });
  }
  const link=$('applio-link');
  try { const url=new URL(services.applio.url,location.origin); if(['http:','https:'].includes(url.protocol)) link.href=url.href; } catch {}
  link.setAttribute('aria-disabled',services.applio.state!=='ready');
  $('workspace-state').textContent='Separator · '+(labels[services.separator.state]||services.separator.state);
  $('submit').disabled=sending || !['ready','busy'].includes(services.separator.state) || !$('model').value;
}
function renderGPU(gpu) {
  if(!gpu.available||!gpu.gpus?.length) { $('gpu-util').textContent='—'; $('gpu-memory').textContent='—'; $('gpu-temp').textContent='—'; $('gpu-name').textContent=gpu.reason||'Telemetry unavailable'; $('gpu-meter').style.width='0'; return; }
  const g=gpu.gpus[0]; $('gpu-util').textContent=g.utilization+'%'; $('gpu-name').textContent=g.name;
  $('gpu-memory').textContent=(g.used_mb/1024).toFixed(1)+' / '+(g.total_mb/1024).toFixed(0)+' GB';
  $('gpu-temp').textContent=g.temperature+'°C'; $('gpu-meter').style.width=Math.min(100,g.used_mb/g.total_mb*100)+'%';
}
function actionButton(text, fn) { const b=node('button',text,'secondary'); b.addEventListener('click',async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;}}); return b; }
function renderJobs(jobs) {
  $('active-count').replaceChildren(document.createTextNode(jobs.filter(j=>j.state==='running').length+' '),node('em','jobs'));
  const queued=jobs.filter(j=>j.state==='queued').length; $('queue-count').textContent=queued?queued+' waiting in queue':'Queue is clear';
  $('history-count').textContent=jobs.length; $('empty-history').hidden=jobs.length>0;
  const rows=jobs.map(job=>{
    const tr=node('tr'), source=node('td'); source.append(node('strong',job.filename),node('small',size(job.size))); tr.append(source);
    const model=node('td',job.model); model.append(node('small',job.format)); tr.append(model);
    const status=node('td'); status.append(badge(job.state)); if(job.error) status.append(node('small',job.error)); tr.append(status,node('td',new Date(job.created).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})));
    const actions=node('td');
    if(job.state==='completed') actions.append(actionButton('Listen ↗',async()=>{if(!workspace){location.href='/separator#'+job.id;return;} selectedJob=job.id; resultVersion=null; await showResults(job); }));
    if(!terminal.has(job.state)) actions.append(actionButton('Cancel',async()=>{if(job.state==='running'&&!confirm('Cancel processing? This stops Audio Separator and cancels all queued jobs.'))return;await api(`/api/jobs/${job.id}/cancel`,{method:'POST'});await poll();}));
    actions.append(actionButton('Log',async()=>{const log=await api(`/api/jobs/${job.id}/log`);$('log-content').textContent=log.text;$('log-dialog').showModal();}));
    if(terminal.has(job.state)) actions.append(actionButton('Delete',async()=>{if(!confirm('Delete this session and all of its audio files?'))return;await api(`/api/jobs/${job.id}`,{method:'DELETE'});if(selectedJob===job.id){selectedJob=null;resultVersion=null;$('results').replaceChildren(node('p','Session deleted.','help'));}await poll();}));
    tr.append(actions);return tr;
  });
  $('jobs').replaceChildren(...rows);
  if(workspace) {if(!selectedJob) selectedJob=location.hash.slice(1)||jobs.find(j=>j.state==='completed')?.id; const job=jobs.find(j=>j.id===selectedJob);if(job)showResults(job).catch(e=>notice(e.message));}
}
async function showResults(job) {
  const version=job.id+job.state;if(resultVersion===version)return;
  const files=await api(`/api/jobs/${job.id}/results`); resultVersion=version;
  const container=$('results');container.replaceChildren(node('h3',job.filename,'result-title'),badge(job.state));
  if(job.error)container.append(node('p',job.error,'help'));
  if(!files.length)container.append(node('p',terminal.has(job.state)?'No completed stems available. Open the process log for details.':'Your session is in progress. Results appear here when processing finishes.','help'));
  for(const file of files) {const stem=node('div',undefined,'stem'), heading=node('div',undefined,'stem-heading'), link=node('a','Download ↓');link.href=file.url;link.download=file.name;heading.append(node('span',file.name),link);const audio=node('audio');audio.controls=true;audio.preload='none';audio.src=file.url;stem.append(heading,audio);container.append(stem);}
  if(files.length){const zip=node('a','Download all stems as ZIP ↓','download-all');zip.href=`/api/jobs/${job.id}/zip`;container.append(zip);}
}
let cycles=0;
async function poll() {
  if(polling||document.hidden)return;polling=true;
  try {const [services,jobs]=await Promise.all([api('/api/services'),api('/api/jobs')]);renderServices(services);renderJobs(jobs);if(cycles++%3===0)renderGPU(await api('/api/system/gpu'));$('last-sync').textContent='Updated '+new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});}
  catch(e){notice(e.message);$('last-sync').textContent='Connection unavailable';}finally{polling=false;}
}
function choose(file) {selectedFile=file;requestKey=crypto.randomUUID();$('file-info').textContent=file?file.name+' · '+size(file.size):'No audio selected';}
$('audio-file').addEventListener('change',event=>choose(event.target.files[0]));
$('model').addEventListener('change',()=>{requestKey=crypto.randomUUID();poll();});
$('format').addEventListener('change',()=>requestKey=crypto.randomUUID());
const drop=$('dropzone');['dragenter','dragover'].forEach(name=>drop.addEventListener(name,e=>{e.preventDefault();drop.classList.add('drag');}));['dragleave','drop'].forEach(name=>drop.addEventListener(name,e=>{e.preventDefault();drop.classList.remove('drag');}));
drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length){$('audio-file').files=e.dataTransfer.files;choose(e.dataTransfer.files[0]);}});
$('job-form').addEventListener('submit',async e=>{
  e.preventDefault();if(sending||!selectedFile)return;sending=true;$('submit').disabled=true;$('submit').textContent='Uploading audio…';notice('');
  try {const params=new URLSearchParams({filename:selectedFile.name,model:$('model').value,format:$('format').value});const job=await api('/api/separator/jobs?'+params,{method:'POST',headers:{'Content-Type':'application/octet-stream','Idempotency-Key':requestKey},body:selectedFile});selectedJob=job.id;resultVersion=null;await showResults(job);notice('Session queued. Keep the separator running until your queue finishes.');}
  catch(error){notice(error.message);}finally{sending=false;$('submit').textContent='Separate audio ↗';await poll();}
});
$('refresh').addEventListener('click',poll);$('close-log').addEventListener('click',()=>$('log-dialog').close());
async function init(){try{const result=await api('/api/separator/models');$('model').replaceChildren(...(result.models.length?result.models.map(name=>{const option=node('option',name);option.value=name;return option;}):[node('option','No local models found')]));if(!result.models.length){$('model').firstChild.value='';if(workspace)notice('No installed models found. Configure the existing models directory before processing.');}}catch(e){notice(e.message);}await poll();}
init();setInterval(poll,5000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
