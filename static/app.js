const message = document.querySelector('#message');
const state = document.querySelector('#investigation-status');
const retry = document.querySelector('#retry');
let selectedId, selection = 0, timer;
async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function renderInvestigation(result) {
  const labels = {queued: 'Queued for investigation.', waiting: 'Waiting for the agent. You can retry if delivery stalled.', processing: 'Agent is investigating…', retrying: 'Agent encountered an error; Pub/Sub will retry delivery.', completed: 'Investigation completed. AI suggestions need your review.', disabled: 'AI investigation is available when connected to GCP.', enqueue_failed: result.error};
  state.textContent = labels[result.status] || 'Investigation status unavailable.';
  retry.hidden = !['waiting', 'retrying', 'enqueue_failed'].includes(result.status);
  const findings = result.findings;
  document.querySelector('#findings').hidden = !findings;
  if (findings) {
    document.querySelector('#severity').textContent = findings.severity;
    document.querySelector('#summary').textContent = findings.summary;
    document.querySelector('#cause').textContent = findings.likely_cause;
    const list = document.querySelector('#recommendations');
    list.replaceChildren();
    for (const suggestion of findings.recommendations || []) {
      const item = document.createElement('li');
      item.textContent = suggestion;
      list.append(item);
    }
    document.querySelector('#model').textContent = `${result.model || ''}${result.truncated ? ' · Only the first 24,000 characters were analyzed.' : ''}`;
  }
}
async function watch(logId, version, attempts = 0) {
  try {
    const result = await request(`/investigations/${logId}`);
    if (version !== selection) return;
    renderInvestigation(result);
    if (!['completed', 'disabled'].includes(result.status) && attempts < 60) {
      timer = setTimeout(() => watch(logId, version, attempts + 1), 3000);
    } else if (attempts === 60 && result.status !== 'completed') {
      state.textContent += ' Live updates paused; select this log again to check progress.';
    }
  } catch (error) {
    if (version === selection) state.textContent = error.message + ' Select this log again to check progress.';
  }
}
async function selectLog(log) {
  const version = ++selection;
  selectedId = log.id;
  clearTimeout(timer);
  try {
    const detail = log.content === undefined ? await request(`/logs/${log.id}`) : log;
    if (version !== selection) return;
    document.querySelector('#filename').textContent = detail.filename;
    document.querySelector('#content').textContent = detail.content;
    document.querySelector('#detail').hidden = false;
    renderInvestigation(detail.investigation || {status: 'waiting'});
    await watch(log.id, version);
  } catch (error) { if (version === selection) message.textContent = error.message; }
}
async function refresh() {
  const logs = await request('/logs');
  const list = document.querySelector('#logs');
  list.replaceChildren();
  if (!logs.length) list.textContent = 'No logs yet. Upload your first file.';
  for (const log of logs) {
    const button = document.createElement('button');
    button.className = 'log';
    button.textContent = `${log.filename} | ${new Date(log.timestamp).toLocaleString()} | ${log.error_count} errors | ${log.warning_count} warnings`;
    button.onclick = () => selectLog(log);
    list.append(button);
  }
}
retry.onclick = async () => {
  const logId = selectedId, version = selection;
  retry.disabled = true;
  clearTimeout(timer);
  try {
    const result = await request(`/investigations/${logId}`, {method: 'POST'});
    if (version !== selection) return;
    renderInvestigation(result);
    await watch(logId, version);
  } catch (error) { if (version === selection) state.textContent = error.message; }
  finally { retry.disabled = false; }
};
document.querySelector('#upload').onsubmit = async event => {
  event.preventDefault();
  const button = event.target.querySelector('button');
  button.disabled = true;
  try {
    const file = document.querySelector('#file').files[0];
    if (!file || file.size > 900 * 1024) throw new Error('Choose a .txt file under 900 KiB.');
    const content = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
    const log = await request('/logs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filename: file.name, content})});
    message.textContent = log.investigation.error || 'Log saved.';
    // Show the saved ID immediately, even if list refresh later fails.
    await selectLog(log);
    await refresh();
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
};
refresh().catch(error => { message.textContent = error.message; });
