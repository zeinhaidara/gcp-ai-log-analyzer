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
    button.onclick = async () => {
      try {
        const detail = await request(`/logs/${encodeURIComponent(log.id)}`);
        document.querySelector('#filename').textContent = detail.filename;
        document.querySelector('#content').textContent = detail.content;
        document.querySelector('#detail').hidden = false;
      } catch (error) { message.textContent = error.message; }
    };
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
    await request('/logs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filename: file.name, content})});
    message.textContent = 'Log processed.';
    await refresh();
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
