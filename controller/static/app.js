'use strict';
const $ = id => document.getElementById(id);
const applioWorkspace = location.pathname === '/applio';
const workspace = location.pathname === '/separator' || applioWorkspace;
const currentTool = applioWorkspace ? 'applio' : 'separator';
let selectedFile = null, requestKey = null, sending = false, selectedJob = null, resultVersion = null, polling = false;
const terminal = new Set(['completed', 'failed', 'cancelled']);
const labels = {ready:'Ready',stopped:'Stopped',starting:'Starting',busy:'Processing',stopping:'Stopping',error:'Needs attention'};
const node = (tag, text, className) => { const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(className) el.className=className; return el; };
function notice(message) { $('notice').textContent=message; $('notice').hidden=!message; }
async function api(path, options={}) { const response=await fetch(path, options); let data; try {data=await response.json();} catch {throw new Error('The controller returned an invalid response.');} if(!response.ok) { const e=new Error(typeof data.detail==='string'?data.detail:'Invalid request. Check your selection.'); e.status=response.status; throw e;} return data; }
function badge(state) {return node('span',labels[state]||state,'status '+state);}
function size(bytes) {return (bytes/1024/1024).toFixed(1)+' MB';}
if(workspace) { $('overview').hidden=true; $('workspace').hidden=false; $('title').textContent='Make room for every stem.'; $('subtitle').textContent='Upload. Separate. Listen. All on your own hardware.'; $('crumb').textContent='Audio Separator'; }
$(workspace?'nav-'+currentTool:'nav-dashboard').classList.add('active');
if(applioWorkspace) {
  $('title').textContent='Alter Tracks Voice.';$('subtitle').textContent='Import a voice. Convert audio. Listen here.';$('crumb').textContent='Applio';
  $('new-session-title').textContent='New voice conversion';$('results').replaceChildren(node('div','Select a completed conversion below to listen and download its audio.','empty-state'));$('separator-model-field').hidden=true;$('model').required=false;
  $('conversion-settings').hidden=false;$('voice-library').hidden=false;$('submit').textContent='Convert audio ↗';
  document.querySelector('#job-form [data-service]').dataset.service='applio';
} else {$('voice-model').required=false;}
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
    $(name+'-detail').textContent=info.error || (info.installed===false?'Not installed · open Setup & models to install':name==='applio' && info.state==='ready' ? 'Ready · convert audio in the Applio workspace' : info.state==='stopped' ? 'Offline · no inference processes running' : info.state==='ready' ? 'Ready for your next session' : info.state==='busy' ? 'Processing audio · see your session below' : 'Waiting for service readiness');
    document.querySelectorAll(`[data-service="${name}"]`).forEach(button=>{ if(!sending) button.disabled=info.installed===false||(button.dataset.action==='start'?['starting','ready','busy','stopping'].includes(info.state):['stopped','stopping'].includes(info.state)); });
  }
  const link=$('applio-link');
  try { const url=new URL(services.applio.url,location.origin); if(['http:','https:'].includes(url.protocol)) link.href=url.href; } catch {}
  link.setAttribute('aria-disabled',services.applio.state!=='ready');
  $('workspace-state').textContent=(applioWorkspace?'Applio':'Separator')+' · '+(labels[services[currentTool].state]||services[currentTool].state);
  $('submit').disabled=sending || !['ready','busy'].includes(services[currentTool].state) || !(applioWorkspace?$('voice-model').value:$('model').value);
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
    const model=node('td',job.tool==='applio'?job.model.split('/').pop():job.model); model.append(node('small',(job.tool==='applio'?'Voice conversion':'Separation')+' · '+job.format)); tr.append(model);
    const status=node('td'); status.append(badge(job.state)); if(job.error) status.append(node('small',job.error)); tr.append(status,node('td',new Date(job.created).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})));
    const actions=node('td');
    if(job.state==='completed') actions.append(actionButton('Listen ↗',async()=>{if(!workspace || (job.tool==='applio')!==applioWorkspace){location.href=(job.tool==='applio'?'/applio':'/separator')+'#'+job.id;return;} selectedJob=job.id; resultVersion=null; await showResults(job); }));
    if(!terminal.has(job.state)) actions.append(actionButton('Cancel',async()=>{if(job.state==='running'&&!confirm('Cancel processing? This stops the selected tool and cancels its queued jobs.'))return;await api(`/api/jobs/${job.id}/cancel`,{method:'POST'});await poll();}));
    actions.append(actionButton('Log',async()=>{const log=await api(`/api/jobs/${job.id}/log`);$('log-content').textContent=log.text;$('log-dialog').showModal();}));
    if(terminal.has(job.state)) actions.append(actionButton('Delete',async()=>{if(!confirm('Delete this session and all of its audio files?'))return;await api(`/api/jobs/${job.id}`,{method:'DELETE'});if(selectedJob===job.id){selectedJob=null;resultVersion=null;$('results').replaceChildren(node('p','Session deleted.','help'));}await poll();}));
    tr.append(actions);return tr;
  });
  $('jobs').replaceChildren(...rows);
  if(workspace) {if(!selectedJob) selectedJob=location.hash.slice(1)||jobs.find(j=>j.state==='completed' && (j.tool==='applio')===applioWorkspace)?.id; const job=jobs.find(j=>j.id===selectedJob);if(job)showResults(job).catch(e=>notice(e.message));}
}
async function showResults(job) {
  const version=job.id+job.state;if(resultVersion===version)return;
  const files=await api(`/api/jobs/${job.id}/results`); resultVersion=version;
  const container=$('results');container.replaceChildren(node('h3',job.filename,'result-title'),badge(job.state));
  if(job.error)container.append(node('p',job.error,'help'));
  if(!files.length)container.append(node('p',terminal.has(job.state)?'No completed stems available. Open the process log for details.':'Your session is in progress. Results appear here when processing finishes.','help'));
  for(const file of files) {const stem=node('div',undefined,'stem'), heading=node('div',undefined,'stem-heading'), link=node('a','Download ↓');link.href=file.url;link.download=file.name;heading.append(node('span',file.name),link);const audio=node('audio');audio.controls=true;audio.preload='none';audio.src=file.url;if(job.tool!=='applio'){const convert=node('a','Convert in Applio ↗','workspace-link');convert.href='/applio?'+new URLSearchParams({source:job.id,file:file.name});heading.append(convert);}stem.append(heading,audio);container.append(stem);}
  if(files.length){const zip=node('a','Download all audio as ZIP ↓','download-all');zip.href=`/api/jobs/${job.id}/zip`;container.append(zip);}
}
let cycles=0;
async function poll() {
  if(polling||document.hidden)return;polling=true;
  try {const [services,jobs]=await Promise.all([api('/api/services'),api('/api/jobs')]);renderServices(services);renderJobs(jobs);if(cycles++%3===0)renderGPU(await api('/api/system/gpu'));$('last-sync').textContent='Updated '+new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});}
  catch(e){notice(e.message);$('last-sync').textContent='Connection unavailable';}finally{polling=false;}
}
function newRequestKey() {
  // getRandomValues also works over HTTP on private network addresses.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
}
function choose(file) {selectedFile=file;requestKey=newRequestKey();$('file-info').textContent=file?file.name+' · '+size(file.size):'No audio selected';}
$('audio-file').addEventListener('change',event=>choose(event.target.files[0]));
$('model').addEventListener('change',()=>{requestKey=newRequestKey();poll();});
$('format').addEventListener('change',()=>requestKey=newRequestKey());
const drop=$('dropzone');['dragenter','dragover'].forEach(name=>drop.addEventListener(name,e=>{e.preventDefault();drop.classList.add('drag');}));['dragleave','drop'].forEach(name=>drop.addEventListener(name,e=>{e.preventDefault();drop.classList.remove('drag');}));
drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length){$('audio-file').files=e.dataTransfer.files;choose(e.dataTransfer.files[0]);}});
$('job-form').addEventListener('submit',async e=>{
  e.preventDefault();if(sending||!selectedFile)return;sending=true;$('submit').disabled=true;$('submit').textContent='Uploading audio…';notice('');
  try {const params=new URLSearchParams({filename:selectedFile.name,model:applioWorkspace?$('voice-model').value:$('model').value,format:$('format').value});if(applioWorkspace)for(const [key,value] of Object.entries(conversionSettings()))params.set(key,value);const job=await api('/api/'+currentTool+'/jobs?'+params,{method:'POST',headers:{'Content-Type':'application/octet-stream','Idempotency-Key':requestKey},body:selectedFile});selectedJob=job.id;resultVersion=null;await showResults(job);notice('Session queued. Keep the selected tool running until its queue finishes.');}
  catch(error){notice(error.message);}finally{sending=false;$('submit').textContent=applioWorkspace?'Convert audio ↗':'Separate audio ↗';await poll();}
});
$('refresh').addEventListener('click',poll);$('close-log').addEventListener('click',()=>$('log-dialog').close());
async function init(){if(applioWorkspace){await refreshVoices();await sourceStem();await poll();return;}try{const result=await api('/api/separator/models');$('model').replaceChildren(...(result.models.length?result.models.map(name=>{const option=node('option',result.labels?.[name]||name);option.value=name;return option;}):[node('option','No local models found')]));if(!result.models.length){$('model').firstChild.value='';if(workspace)notice('No installed models found. Configure the existing models directory before processing.');}}catch(e){notice(e.message);}await poll();}
function conversionSettings(){return {index:$('voice-index').value,pitch:$('voice-pitch').value,index_rate:$('voice-index-rate').value,protect:$('voice-protect').value,volume_envelope:$('voice-volume').value,f0_method:$('voice-f0').value};}
async function refreshVoices(){try{const data=await api('/api/applio/voices');const selected=$('voice-model').value,index=$('voice-index').value;
  $('voice-model').replaceChildren(...(data.models.length?data.models.map(item=>{const o=node('option',item.name+' · '+size(item.size));o.value=item.id;return o;}):[node('option','Import a voice model below')]));
  if(!data.models.length)$('voice-model').firstChild.value='';else if(data.models.some(item=>item.id===selected))$('voice-model').value=selected;
  const none=node('option','No index');none.value='';$('voice-index').replaceChildren(none,...data.indexes.map(item=>{const o=node('option',item.name);o.value=item.id;return o;}));if(data.indexes.some(item=>item.id===index))$('voice-index').value=index;
  $('voice-library-list').textContent=data.models.length+' voice models · '+data.indexes.length+' indexes';
}catch(e){notice(e.message);}}
async function sourceStem(){const params=new URLSearchParams(location.search);if(!params.has('source'))return;try{
  const source=params.get('source'),name=params.get('file');const files=await api('/api/jobs/'+encodeURIComponent(source)+'/results');const file=files.find(item=>item.name===name);if(!file)throw new Error('Source audio is no longer available.');
  const response=await fetch(file.url);if(!response.ok)throw new Error('Unable to read source audio.');choose(new File([await response.blob()],file.name));$('audio-file').required=false;
}catch(e){notice(e.message);}}
for(const id of ['voice-model','voice-index','voice-pitch','voice-index-rate','voice-protect','voice-volume','voice-f0'])$(id).addEventListener('change',()=>{requestKey=newRequestKey();poll();});
$('refresh-voices').addEventListener('click',refreshVoices);
function uploadVoice(file){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/applio/voices?'+new URLSearchParams({filename:file.name,confirm:'true'}));xhr.setRequestHeader('Content-Type','application/octet-stream');
 xhr.upload.onprogress=event=>{if(event.lengthComputable){$('voice-import-progress').value=event.loaded/event.total*100;$('voice-import-status').textContent='Uploading '+file.name+' · '+Math.round(event.loaded/event.total*100)+'%';}};
 xhr.upload.onload=()=>{$('voice-import-status').textContent='Storing and verifying '+file.name+'…';};xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch{reject(new Error('Invalid import response.'));return;}if(xhr.status>=200&&xhr.status<300)resolve(data);else reject(new Error(data.detail||'Import failed'));};xhr.onerror=()=>reject(new Error('Upload connection failed. Refresh the voice library before retrying.'));xhr.send(file);
});}
$('voice-import-form').addEventListener('submit',async event=>{event.preventDefault();if(!$('voice-trust').checked)return;const files=[$('voice-model-file').files[0],$('voice-index-file').files[0]].filter(Boolean);if(!files.length){notice('Select a voice model or index file.');return;}
 $('import-voices').disabled=true;$('voice-import-progress').hidden=false;try{for(const file of files){$('voice-import-progress').value=0;await uploadVoice(file);for(const id of ['voice-model-file','voice-index-file'])if($(id).files[0]===file)$(id).value='';$('voice-import-status').textContent='Imported '+file.name+'; transfer checksum verified.';}$('voice-import-form').reset();notice('Voice files imported. Select the model and its matching index above.');}
 catch(e){notice(e.message);}finally{$('import-voices').disabled=false;$('voice-import-progress').hidden=true;await refreshVoices();await poll();}});
init();setInterval(poll,5000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
