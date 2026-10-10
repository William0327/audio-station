'use strict';
const setupPage=location.pathname==='/setup';
if(setupPage){$('setup-panel').hidden=false;$('overview').hidden=true;$('workspace').hidden=true;$('nav-dashboard').classList.remove('active');$('title').textContent='Build your audio workstation.';$('subtitle').textContent='Choose your tools. Keep your models. Start only what you need.';$('crumb').textContent='Setup & models';document.querySelector('header a').setAttribute('aria-current','page');}
let setupPolling=false,setupFingerprint='';
async function setupAction(url,options,message){if(message&&!confirm(message))return;try{await api(url,options);setupFingerprint='';await pollSetup();notice('Operation queued. Progress appears in Installation activity.');}catch(e){notice(e.message);}}
async function pollSetup(){
 if(setupPolling||document.hidden)return;setupPolling=true;
 try{
  const data=await api('/api/setup');
  if(!setupPage){if(Object.values(data.tools).some(t=>!t.installed)) {const n=$('notice'); if(n.hidden){n.replaceChildren(node('span','Welcome to Audio Station. '));const link=node('a','Install your tools in Setup →');link.href='/setup';n.append(link);n.hidden=false;}}return;}
  $('deployment-mode').textContent=data.mode==='managed'?'Managed installation':'Advanced external mode';
  const fingerprint=JSON.stringify(data);if(fingerprint===setupFingerprint)return;setupFingerprint=fingerprint;
  const active=data.operations.filter(o=>['queued','running'].includes(o.state));
  $('setup-tools').replaceChildren(...Object.entries(data.tools).map(([id,tool])=>{
   const card=node('article',undefined,'setup-card');card.append(node('h3',tool.title),node('p','Version '+tool.version,'help'),node('p',tool.installed?'Installed · '+(labels[tool.state]||tool.state):'Not installed','help'));
   if(tool.error)card.append(node('p',tool.error,'help'));
   const install=actionButton(tool.installed?'Check installation':'Install tool',()=>setupAction(`/api/tools/${id}/install`,{method:'POST'},`Install ${tool.title} ${tool.version} from its pinned official source? This builds a local GPU image. The tool will remain stopped.`));
   install.disabled=data.mode!=='managed'||active.some(o=>o.tool===id)||['ready','busy','starting'].includes(tool.state);card.append(install);
   if(tool.installed){const launch=actionButton('Start service',()=>serviceAction(id,'start',launch));launch.disabled=active.some(o=>o.tool===id)||['ready','busy','starting'].includes(tool.state);card.append(launch);const stop=actionButton('Stop service',()=>serviceAction(id,'stop',stop));stop.disabled=tool.state==='stopped';card.append(stop);}
   return card;
  }));
  $('model-catalog').replaceChildren(...data.models.map(model=>{
   const card=node('article',undefined,'setup-card');card.append(node('h3',model.title),node('p',model.publisher+' · '+size(model.size),'help'),node('p',model.license_note,'help'),node('p',model.installed?'Present in cache · install again to verify':'Not installed','help'));
   const source=node('a','Publisher & terms ↗','catalog-source');source.href=model.source;source.target='_blank';source.rel='noopener';card.append(source);
   const install=actionButton(model.installed?'Verify cache':'Install model',()=>setupAction(`/api/models/${model.id}/install`,{method:'POST'},`Download/verify ${model.title} (${size(model.size)}) from ${model.publisher}? Review publisher terms first. Existing different files will never be overwritten.`));
   const busy=active.some(o=>o.tool===model.tool)||['ready','busy','starting'].includes(data.tools[model.tool]?.state);install.disabled=data.mode!=='managed'||busy;card.append(install);
   if(model.installed){const remove=actionButton('Remove model',()=>setupAction(`/api/models/${model.id}?confirm=true`,{method:'DELETE'},`Remove the catalogue files for ${model.title}? Other models and directories will be preserved.`));remove.disabled=data.mode!=='managed'||busy;card.append(remove);}return card;
  }));
  $('install-operations').replaceChildren(...(data.operations.length?data.operations.map(op=>{const row=node('div',undefined,'install-row');row.append(node('strong',op.target+' · '+op.kind),badge(op.state),node('p',op.message,'help'));if(op.progress!==null){const progress=node('progress');progress.max=100;progress.value=op.progress;progress.setAttribute('aria-label',op.target+' installation progress');row.append(progress,node('small',op.progress+'%'));}return row;}):[node('p','No installation operations yet. Choose a tool to get started.','help')]));
 }catch(e){if(setupPage){$('deployment-mode').textContent='Gateway unavailable';notice(e.message);}}finally{setupPolling=false;}
}
pollSetup();if(setupPage)setInterval(pollSetup,5000);
