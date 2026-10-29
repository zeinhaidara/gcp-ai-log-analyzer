'use strict';
const studio = new ReplayStudio();
const $ = selector => document.querySelector(selector);
let selectedId = null, selection = 0, timer = null, demoRecord = null;
let savedLogs = [], currentView = 'home';

function showView(view) {
  currentView = view;
  document.body.dataset.view = view;
  $('#welcome').hidden = view !== 'home';
  $('#library').hidden = !['home','logs'].includes(view);
  $('#studio').hidden = view !== 'case';
  $('#report-section').hidden = view !== 'reports';
  $('#library-title').textContent = view === 'logs' ? 'Saved logs' : 'Recent logs';
  $('#library-description').textContent = view === 'logs' ? 'Your saved uploads. Choose a file to open its replay and AI findings.' : 'Your latest saved uploads.';
  $('#log-search-label').hidden = view !== 'logs';
  $('#view-all-logs').hidden = view !== 'home' || savedLogs.length <= 3;
  document.querySelectorAll('[data-view-link]').forEach(link => {
    if(link.dataset.viewLink === view) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
  });
  renderLogs();
}
function navigate(view) {
  ++selection; clearTimeout(timer); studio.pause(); notify('');
  showView(view);
  window.scrollTo({top:0});
  if(view === 'reports') refreshAnalytics();
}
function route() {
  const hash = location.hash.slice(1);
  const demo = new URLSearchParams(hash).get('demo');
  if(['retry-storm','token-expiry','payment-recovery'].includes(demo)) loadDemo(demo);
  else if(hash.startsWith('case=')) {
    const id = new URLSearchParams(hash).get('case');
    if(/^[0-9a-f-]{36}$/.test(id)) selectLog({id});
    else navigate('home');
  } else navigate(['logs','reports'].includes(hash) ? hash : 'home');
}

async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed.');
  return data;
}
function notify(text) { $('#message').textContent = text; $('#message').hidden = !text; }
function renderInvestigation(result) {
  const labels = {preview:'This scenario is a local replay. Choose “Investigate this scenario” to save it and run the cloud agent.',queued:'Queued for the agent. Your replay is ready now.',waiting:'Waiting for the agent. Retry if delivery stalled.',not_requested:'Investigation has not been requested.',processing:'Gemini is investigating the saved log…',retrying:'The agent encountered an error. Pub/Sub will retry delivery.',completed:'Investigation completed. Review the hypotheses against the source.',disabled:'Replay is ready. AI investigations require the cloud deployment.',enqueue_failed:result.error,dispatch_failed:result.message || 'Upload saved. Retry this investigation.'};
  $('#investigation-status').textContent = labels[result.status] || 'Investigation status is temporarily unavailable.';
  $('#retry').hidden = !selectedId || !['waiting','not_requested','retrying','enqueue_failed','dispatch_failed'].includes(result.status);
  const findings = result.findings;
  $('#findings').hidden = !findings;
  if (findings) {
    $('#severity').textContent = findings.severity; $('#severity').dataset.kind = findings.severity;
    $('#summary').textContent = findings.summary; $('#cause').textContent = findings.likely_cause;
    $('#recommendations').replaceChildren();
    (findings.recommendations || []).forEach(text => $('#recommendations').append(element('li','',text)));
    $('#model').textContent = `${result.model || 'Gemini'}${result.truncated ? ' · Only the first 24,000 source characters were supplied to the model.' : ''}`;
    $('#history').textContent = result.history_available === false ? 'Historical lookup was unavailable; investigation used this log.' : `Historical incidents used: ${result.history_count || 0}`;
    const hypotheses = studio.renderHypotheses(findings.hypotheses || []);
    if (studio.data) studio.data.hypotheses = hypotheses;
  }
}
async function watch(logId, version, attempts = 0) {
  try {
    const result = await request(`/investigations/${logId}`);
    if (version !== selection) return;
    renderInvestigation(result);
    if (result.status === 'completed') refreshAnalytics();
    if (!['completed','disabled'].includes(result.status) && attempts < 60) timer = setTimeout(() => watch(logId,version,attempts+1),3000);
    else if (attempts === 60) $('#investigation-status').textContent += ' Live updates paused; select this case again to check progress.';
  } catch(error) { if(version === selection) $('#investigation-status').textContent = `${error.message} Replay remains available. Select the case again to check AI progress.`; }
}
function markSelected() { document.querySelectorAll('.case-button').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.logId === selectedId))); }
async function selectLog(log) {
  const version = ++selection; clearTimeout(timer); studio.pause(); notify('Opening case…');
  selectedId = log.id; demoRecord = null; markSelected();
  try {
    const artifact = await request(`/logs/${log.id}/replay`);
    if(version !== selection) return;
    showView('case');
    studio.load({...log,...artifact},artifact.replay); renderInvestigation(artifact.investigation || log.investigation || {status:'waiting'}); notify('');
    history.replaceState(null,'',`#case=${log.id}`);
    window.scrollTo({top:0});
    await watch(log.id,version);
  } catch(error) { if(version === selection) notify(error.message); }
}
async function loadDemo(name) {
  const version = ++selection; clearTimeout(timer); studio.pause(); notify('Reconstructing the scenario…');
  selectedId = null; markSelected();
  try {
    const record = await request(`/replay/demo/${encodeURIComponent(name)}`);
    if(version !== selection) return;
    showView('case');
    demoRecord = record; studio.load(record,record.replay); renderInvestigation({status:'preview'}); notify('');
    history.replaceState(null,'',`#demo=${name}`);
    window.scrollTo({top:0});
  } catch(error) { if(version === selection) notify(error.message); }
}
async function refresh() {
  savedLogs = await request('/logs'); renderLogs();
}
function renderLogs() {
  const query = currentView === 'logs' ? $('#log-search').value.trim().toLowerCase() : '';
  const matching = savedLogs.filter(log => log.filename.toLowerCase().includes(query));
  const logs = currentView === 'home' ? matching.slice(0,3) : matching;
  $('#case-count').textContent = savedLogs.length;
  $('#view-all-logs').hidden = currentView !== 'home' || savedLogs.length <= 3;
  const list = $('#logs'); list.replaceChildren();
  if(!logs.length) list.append(element('p','empty-logs',query ? 'No filenames match your search.' : 'Your saved logs will appear here. Open a log to get started.'));
  for(const log of logs) {
    const button = element('button','case-button'); button.type='button';button.dataset.logId=log.id;
    const name=element('span','case-name',log.filename);name.title=log.filename;
    const date=new Date(log.timestamp).toLocaleDateString(undefined,{month:'short',day:'numeric'});
    const details=element('span','case-details',`${log.error_count} errors · ${log.warning_count} warnings`);
    button.append(name,details,element('time','case-date',date),element('span','case-arrow','→'));
    button.onclick=()=>selectLog(log);list.append(button);
  }
  markSelected();
}
async function saveContent(filename,content) {
  const log = await request('/logs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename,content})});
  // The durable case ID is retained even when a later refresh fails.
  await selectLog(log);
  if(log.investigation.status === 'enqueue_failed' || log.investigation.status === 'dispatch_failed') notify(log.investigation.error || log.investigation.message);
  try { await refresh(); } catch { notify('Case saved. The case list could not refresh; select Refresh to try again.'); }
  return log;
}
const dialog=$('#upload-dialog');
['#open-upload','#welcome-upload'].forEach(selector=>$(selector).onclick=()=>{ $('#upload-error').hidden=true;dialog.showModal(); });
$('#close-upload').onclick=()=>dialog.close();
$('#upload').onsubmit=async event=>{
  event.preventDefault();const button=event.target.querySelector('[type="submit"]');button.disabled=true;
  try {
    const file=$('#file').files[0];
    if(!file || !/\.(txt|log|jsonl)$/i.test(file.name) || file.size>900*1024)throw new Error('Choose a UTF-8 .txt, .log or .jsonl file under 900 KiB.');
    const content=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
    const log=await request('/logs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,content})});
    dialog.close();await selectLog(log);try{await refresh();}catch{notify('Case saved. The case list could not refresh.');}
  } catch(error) { $('#upload-error').textContent=error.message;$('#upload-error').hidden=false; }
  finally { button.disabled=false; }
};
$('#save-demo').onclick=async()=>{
  if(!demoRecord)return;const record=demoRecord;const button=$('#save-demo');button.disabled=true;
  try { await saveContent(record.filename,record.content); } catch(error) { notify(error.message); } finally { button.disabled=false; }
};
$('#retry').onclick=async()=>{
  const logId=selectedId,version=selection;if(!logId)return;$('#retry').disabled=true;clearTimeout(timer);
  try {const result=await request(`/investigations/${logId}`,{method:'POST'});if(version!==selection)return;renderInvestigation(result);await watch(logId,version);}
  catch(error){if(version===selection)$('#investigation-status').textContent=error.message;}
  finally{$('#retry').disabled=false;}
};
document.querySelectorAll('[data-demo]').forEach(button=>button.onclick=()=>loadDemo(button.dataset.demo));
$('#refresh-logs').onclick=()=>refresh().catch(error=>notify(error.message));
$('#log-search').oninput=renderLogs;
window.addEventListener('hashchange',route);

async function refreshAnalytics() {
  const target=$('#analytics');
  try {
    const report=await request('/analytics');target.replaceChildren();
    if(!report.enabled){target.append(element('p','',report.message));return;}
    const total=element('p','report-total',String(report.total));total.append(element('span','',` completed investigations · last ${report.days} days`));target.append(total);
    const grid=element('div','report-grid');
    for(const [title,values] of [['Severity',report.severity],['Daily incidents',report.daily],['Failure categories',report.categories],['Services',report.services]]) {
      const group=element('div','report-group');group.append(element('h3','',title));const max=Math.max(1,...Object.values(values));
      for(const [name,count]of Object.entries(values)) {const item=element('div','report-item');item.append(element('span','',name),element('strong','',String(count)));const bar=element('div','report-bar'),fill=element('div','report-bar-fill');fill.style.width=`${count/max*100}%`;bar.append(fill);group.append(item,bar);}
      if(!Object.keys(values).length)group.append(element('p','fine-print','No completed investigations.'));grid.append(group);
    }
    target.append(grid);
  } catch { target.textContent='Incident reporting is temporarily unavailable.'; }
}
$('#refresh-analytics').onclick=refreshAnalytics;
route();
refresh().catch(error=>notify(error.message));
