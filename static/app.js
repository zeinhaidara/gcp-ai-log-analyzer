const message = document.querySelector('#message');
async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
async function refresh() {
  const logs = await request('/logs');
  const list = document.querySelector('#logs');
  list.replaceChildren();
  if (!logs.length) list.textContent = 'No logs yet. Upload your first file.';
  for (const log of logs) {
    const button = document.createElement('button');
    button.className = 'log';
    button.textContent = `${log.filename} | ${new Date(log.timestamp).toLocaleString()} | ${log.error_count} errors | ${log.warning_count} warnings | ${log.status}`;
    button.onclick = () => openLog(log.id);
    list.append(button);
  }
}
document.querySelector('#upload').onsubmit = async event => {
  event.preventDefault();
  const button = event.target.querySelector('button');
  button.disabled = true;
  try {
    const file = document.querySelector('#file').files[0];
    if (!file || file.size > 900 * 1024) throw new Error('Choose a .txt file under 900 KiB.');
    const content = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
    const uploaded = await request('/logs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filename: file.name, content})});
    message.textContent = uploaded.investigation.status === 'dispatch_failed' ? uploaded.investigation.message : 'Log saved. Investigation status appears below.';
    await refresh();
    await openLog(uploaded.id);
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
};
refresh().catch(error => { message.textContent = error.message; });
async function refreshAnalytics() {
  const target = document.querySelector('#analytics');
  try {
    const report = await request('/analytics');
    target.replaceChildren();
    if (!report.enabled) { target.textContent = report.message; return; }
    const total = document.createElement('p');
    total.textContent = `${report.total} completed investigations in the last ${report.days} days`;
    target.append(total);
    for (const [title, values] of [['Severity', report.severity], ['Daily incidents', report.daily], ['Failure categories', report.categories], ['Services', report.services]]) {
      const heading = document.createElement('h3'); heading.textContent = title;
      const list = document.createElement('ul');
      for (const [name, count] of Object.entries(values)) {
        const item = document.createElement('li'); item.textContent = `${name}: ${count}`; list.append(item);
      }
      if (!list.children.length) { const item = document.createElement('li'); item.textContent = 'No investigations yet'; list.append(item); }
      target.append(heading, list);
    }
  } catch { target.textContent = 'Incident reporting is temporarily unavailable.'; }
}
document.querySelector('#refresh-analytics').onclick = refreshAnalytics;
refreshAnalytics();

let activeLogId = null;
let pollTimer = null;
async function openLog(logId) {
  activeLogId = logId;
  clearTimeout(pollTimer);
  document.querySelector('#investigation').textContent = 'Loading investigation…';
  document.querySelector('#retry-investigation').hidden = true;
  try {
    const detail = await request(`/logs/${encodeURIComponent(logId)}`);
    if (activeLogId !== logId) return;
    document.querySelector('#filename').textContent = detail.filename;
    document.querySelector('#content').textContent = detail.content;
    document.querySelector('#detail').hidden = false;
    await pollInvestigation(logId, 0);
  } catch (error) { message.textContent = error.message; }
}
async function pollInvestigation(logId, attempt) {
  if (activeLogId !== logId) return;
  const target = document.querySelector('#investigation');
  const retry = document.querySelector('#retry-investigation');
  try {
    const result = await request(`/logs/${encodeURIComponent(logId)}/investigation`);
    if (activeLogId !== logId) return;
    target.replaceChildren();
    const status = document.createElement('p');
    status.textContent = `AI investigation: ${result.status.replaceAll('_', ' ')}`;
    target.append(status);
    retry.hidden = !['dispatch_failed', 'not_requested', 'retrying'].includes(result.status);
    if (result.findings) {
      for (const [label, value] of [['Severity', result.findings.severity], ['Summary', result.findings.summary], ['Possible cause', result.findings.likely_cause]]) {
        const line = document.createElement('p'); line.textContent = `${label}: ${value}`; target.append(line);
      }
      const steps = document.createElement('ol');
      for (const text of result.findings.recommendations || []) {
        const item = document.createElement('li'); item.textContent = text; steps.append(item);
      }
      target.append(steps);
      const context = document.createElement('p');
      context.textContent = `Historical incidents used: ${result.history_count || 0}. AI suggestions require review.`;
      target.append(context);
    }
    if (['queued', 'processing', 'retrying'].includes(result.status) && attempt < 60) {
      pollTimer = setTimeout(() => pollInvestigation(logId, attempt + 1), 5000);
    } else if (attempt >= 60 && result.status !== 'completed') {
      const notice = document.createElement('p'); notice.textContent = 'Still pending. Reopen this log later to check progress.'; target.append(notice);
    }
    if (result.status === 'completed') refreshAnalytics();
  } catch (error) {
    if (activeLogId !== logId) return;
    target.textContent = error.message;
    retry.hidden = false;
  }
}
document.querySelector('#retry-investigation').onclick = async () => {
  const logId = activeLogId;
  if (!logId) return;
  const button = document.querySelector('#retry-investigation'); button.disabled = true;
  clearTimeout(pollTimer);
  try {
    await request(`/logs/${encodeURIComponent(logId)}/investigation`, {method: 'POST'});
    await pollInvestigation(logId, 0);
  } catch (error) { document.querySelector('#investigation').textContent = error.message; }
  finally { button.disabled = false; }
};
