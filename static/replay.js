/* Replay state is computed from observations. AI hypotheses never change the map. */
'use strict';

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function svgElement(tag, attrs) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}
function clock(event) {
  return event?.timestamp?.match(/\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?/)?.[0] || (event ? event.id : '—');
}
function duration(ms) {
  if (ms === null || ms === undefined) return 'Source order';
  return ms < 60000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.floor(ms / 60000)}m ${Math.round(ms % 60000 / 1000)}s`;
}

class ReplayStudio {
  constructor() {
    this.data = null; this.record = null; this.events = []; this.position = 0;
    this.trace = ''; this.service = ''; this.timer = null; this.playing = false;
    this.positions = new Map(); this.nodeElements = new Map(); this.question = '';
    this.$ = selector => document.querySelector(selector);
    this.$('#timeline').addEventListener('input', event => this.seek(Number(event.target.value)));
    this.$('#play-replay').onclick = () => this.playing ? this.pause() : this.play();
    this.$('#step-back').onclick = () => this.seek(this.position - 1);
    this.$('#step-next').onclick = () => this.seek(this.position + 1);
    this.$('#jump-fault').onclick = () => this.jump('failure');
    this.$('#jump-error').onclick = () => this.jump('failure', this.position + 1);
    this.$('#jump-recovery').onclick = () => this.jump('recovery', this.position + 1);
    this.$('#trace-filter').onchange = event => {
      this.pause(); this.trace = event.target.value; this.service = ''; this.question = '';
      this.$('#answer').hidden = true; this.filter(); this.layoutMap(); this.render();
    };
    this.$('#clear-service').onclick = () => { this.service = ''; this.renderMap(); this.renderTrail(); };
    this.$('#open-source').onclick = () => this.openSource(this.events[this.position]?.line);
    this.$('#export-replay').onclick = () => this.export();
    this.$('#raw-source').addEventListener('toggle', () => {
      if (this.$('#raw-source').open && !this.$('#content').childNodes.length) this.openSource(this.events[this.position]?.line);
    });
    document.querySelectorAll('[data-question]').forEach(button => button.onclick = () => this.ask(button.dataset.question));
    this.$('#question-form').onsubmit = event => { event.preventDefault(); this.ask(this.$('#question').value); };
    ['evidence', 'investigation'].forEach(name => this.$(`#${name}-tab`).onclick = () => this.tab(name));
    document.addEventListener('keydown', event => {
      if (!this.data || this.$('#studio').hidden || this.$('#upload-dialog').open || event.altKey || event.ctrlKey || event.metaKey || /INPUT|SELECT|TEXTAREA|BUTTON|SUMMARY|A/.test(event.target.tagName)) return;
      if (event.code === 'Space') { event.preventDefault(); this.playing ? this.pause() : this.play(); }
      if (event.key === 'ArrowRight') { event.preventDefault(); this.seek(this.position + 1); }
      if (event.key === 'ArrowLeft') { event.preventDefault(); this.seek(this.position - 1); }
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden) this.pause(); });
    new ResizeObserver(() => { if (this.data && !this.$('#studio').hidden) { this.layoutMap(); this.render(); } }).observe(this.$('.replay-main'));
  }
  load(record, data) {
    this.pause(); this.record = record; this.data = data; this.trace = ''; this.service = ''; this.position = 0; this.question = '';
    this.lines = record.content.split(/\r\n|\n|\r/);
    this.$('#welcome').hidden = true; this.$('#studio').hidden = false;
    this.$('#filename').textContent = record.filename;
    this.$('#source-badge').textContent = record.demo ? 'Synthetic scenario · unsaved' : 'Saved log';
    this.$('#save-demo').hidden = !record.demo;
    this.$('#raw-source').open = false; this.$('#content').replaceChildren();
    this.$('#event-trail').open = false; this.$('.ask-panel').open = false;
    this.$('#source-line-count').textContent = `${data.coverage.total_lines.toLocaleString()} lines`;
    this.$('#answer').hidden = true; this.$('#question').value = '';
    const traceSelect = this.$('#trace-filter'); traceSelect.replaceChildren();
    const all = element('option', '', 'All requests'); all.value = ''; traceSelect.append(all);
    for (const trace of data.traces) { const option = element('option', '', trace); option.value = trace; traceSelect.append(option); }
    traceSelect.disabled = !data.traces.length;
    this.filter(); this.layoutMap(); this.render(); this.renderHypotheses(data.hypotheses || []); this.tab('evidence');
  }
  filter() {
    // Untraced events remain as shared context; unrelated requests are excluded.
    this.events = this.data.events.filter(event => !this.trace || !event.trace || event.trace === this.trace);
    this.position = 0;
    this.$('#timeline').max = Math.max(0, this.events.length - 1);
    this.$('#stat-events').textContent = this.events.length.toLocaleString();
    const names = new Set(this.events.flatMap(e => [e.service, e.target].filter(Boolean)));
    this.$('#stat-services').textContent = names.size;
    this.$('#stat-errors').textContent = this.events.filter(e => e.kind === 'failure').length;
    const elapsed = this.data.coverage.order === 'timestamp' && this.events.length ? this.events.at(-1).offset_ms - this.events[0].offset_ms : null;
    this.$('#stat-duration').textContent = duration(elapsed);
    this.$('#duration-label').textContent = elapsed === null ? 'REPLAY ORDER' : 'OBSERVED WINDOW';
    this.$('#coverage-label').textContent = `${this.events.length.toLocaleString()} events · ${this.data.coverage.order === 'timestamp' ? 'timestamp order' : 'source order'}${this.trace ? ' · shared context included' : ''}`;
    this.$('#clock-label').textContent = this.data.coverage.order === 'timestamp' ? 'RECORDED TIME' : 'SOURCE POSITION';
    this.$('#time-start').textContent = clock(this.events[0]); this.$('#time-end').textContent = clock(this.events.at(-1));
    const c = this.data.coverage, notes = [];
    if (c.order === 'source') notes.push('Missing or mixed clocks: replay uses source order; elapsed time is unavailable.');
    if (c.clock_rollover_assumed) notes.push('Time-only stamps crossed midnight: a day rollover is assumed for backward jumps greater than 12 hours.');
    if (c.sampled) notes.push(`Replay samples ${c.shown_events.toLocaleString()} of ${c.parsed_events.toLocaleString()} events. Source line numbers are preserved.`);
    if (c.truncated) notes.push(`Reconstruction covers the first ${c.scanned_lines.toLocaleString()} of ${c.total_lines.toLocaleString()} lines. The full source remains available.`);
    if (c.omitted_services) notes.push(`The map shows at most 20 services; ${c.omitted_services} additional services are in the event evidence.`);
    if (this.trace) notes.push('Untraced configuration and other shared events remain visible; they are not proven members of this request.');
    notes.push('Event states describe recorded signals, not live service health. Earlier errors are clues, not confirmed causes.');
    this.$('#coverage-note').textContent = notes.join(' ');
  }
  tab(name) {
    for (const view of ['evidence', 'investigation']) {
      this.$(`#${view}-tab`).setAttribute('aria-selected', String(view === name));
      this.$(`#${view}-panel`).hidden = view !== name;
    }
  }
  seek(position) {
    this.pause(); this.position = Math.max(0, Math.min(position, this.events.length - 1)); this.render();
  }
  jump(kind, from = 0) {
    let index = this.events.findIndex((event, i) => i >= from && event.kind === kind);
    if (index < 0 && kind === 'recovery') index = this.events.findIndex(event => event.kind === kind);
    if (index >= 0) this.seek(index);
  }
  pause() { clearTimeout(this.timer); this.timer = null; this.playing = false; this.$('#play-replay').textContent = '▶ Play replay'; }
  play() {
    if (!this.events.length) return;
    if (this.position >= this.events.length - 1) this.position = 0;
    this.playing = true; this.$('#play-replay').textContent = 'Ⅱ Pause replay'; this.render();
    const tick = () => {
      if (!this.playing) return;
      if (this.position >= this.events.length - 1) { this.pause(); return; }
      this.position++; this.render();
      if (this.position >= this.events.length - 1) { this.pause(); return; }
      const gap = this.events[this.position + 1].offset_ms - this.events[this.position].offset_ms;
      const speed = Number(this.$('#replay-speed').value);
      this.timer = setTimeout(tick, Math.min(1300, Math.max(450, gap || 700)) / speed);
    };
    this.timer = setTimeout(tick, 700 / Number(this.$('#replay-speed').value));
  }
  layoutMap() {
    const map = this.$('#service-map'), width = map.clientWidth;
    if (width < 1) return;
    const visible = new Set(this.events.flatMap(e => [e.service, e.target].filter(Boolean)));
    const nodes = this.data.nodes.filter(node => visible.has(node.id));
    const links = this.data.links.filter(link => visible.has(link.source) && visible.has(link.target));
    const pending = new Map(nodes.map(node => [node.id, 0]));
    links.forEach(link => pending.set(link.target, (pending.get(link.target) || 0) + 1));
    const ordered = [], queue = nodes.filter(node => !pending.get(node.id));
    while (queue.length) {
      const node = queue.shift(); if (ordered.some(item => item.id === node.id)) continue;
      ordered.push(node);
      for (const link of links.filter(link => link.source === node.id)) { pending.set(link.target, pending.get(link.target) - 1); if (!pending.get(link.target)) queue.push(nodes.find(node => node.id === link.target)); }
    }
    ordered.push(...nodes.filter(node => !ordered.some(item => item.id === node.id)));
    const columns = Math.max(1, Math.min(5, ordered.length, Math.floor((width - 30) / 145)));
    const nodeWidth = Math.min(145, (width - 32 - (columns - 1) * 20) / columns);
    const gap = columns > 1 ? (width - 32 - columns * nodeWidth) / (columns - 1) : 0;
    const rows = Math.ceil(ordered.length / columns), height = Math.max(210, rows * 131 + 40);
    map.style.height = `${height}px`; this.positions.clear(); this.nodeElements.clear();
    const focused = document.activeElement?.dataset.nodeName;
    this.$('#map-nodes').replaceChildren();
    ordered.forEach((node, index) => {
      const x = columns === 1 ? (width - nodeWidth) / 2 : 16 + (index % columns) * (nodeWidth + gap), y = 36 + Math.floor(index / columns) * 131;
      this.positions.set(node.id, {x, y, width: nodeWidth, height: 90});
      const button = element('button', 'service-node'); button.type = 'button'; button.dataset.nodeName = node.id;
      button.style.left = `${x}px`; button.style.top = `${y}px`; button.style.width = `${nodeWidth}px`; button.style.height = '90px';
      const top = element('span', 'node-top'), symbol = element('span', 'node-symbol', node.id === 'unattributed' ? '?' : '◈'); symbol.setAttribute('aria-hidden', 'true');
      const name = element('span', 'node-name', node.id.length > 26 ? node.id.slice(0, 24) + '…' : node.id); name.title = node.id;
      top.append(symbol, name); button.append(top, element('span', 'node-state'), element('span', 'node-foot'));
      button.onclick = () => { this.service = this.service === node.id ? '' : node.id; this.$('#event-trail').open = !!this.service; this.renderMap(); this.renderTrail(); };
      this.$('#map-nodes').append(button); this.nodeElements.set(node.id, button);
      if (focused === node.id) button.focus({preventScroll: true});
    });
    this.$('#map-edges').setAttribute('viewBox', `0 0 ${width} ${height}`);
  }
  render() {
    const event = this.events[this.position];
    this.$('#timeline').value = Math.max(0, this.position);
    this.$('#play-replay').disabled = this.events.length < 2;
    this.$('#step-back').disabled = this.position <= 0;
    this.$('#step-next').disabled = this.position >= this.events.length - 1;
    this.$('#jump-fault').disabled = !this.events.some(e => e.kind === 'failure');
    this.$('#jump-error').disabled = !this.events.some((e, i) => i > this.position && e.kind === 'failure');
    this.$('#jump-recovery').disabled = !this.events.some(e => e.kind === 'recovery');
    this.$('#event-position').textContent = `Event ${event ? this.position + 1 : 0} / ${this.events.length}`;
    this.$('#replay-clock').textContent = this.data.coverage.order === 'timestamp' ? clock(event) : event?.id || '—';
    if (!event) {
      this.$('#beat-title').textContent = 'No events to reconstruct.'; this.$('#beat-description').textContent = 'Open a log with nonempty event lines.'; return;
    }
    const first = this.events.find(e => e.kind === 'failure');
    const titles = {failure: event.id === first?.id ? `First recorded failure · ${event.service}` : `Error recorded · ${event.service}`, retry: `Retry recorded · ${event.service}`, change: `A change appears · ${event.service}`, recovery: `Recovery recorded · ${event.service}`, warning: `Warning in ${event.service}`, success: `Success recorded · ${event.service}`};
    this.$('#beat-kind').textContent = event.kind; this.$('#beat-kind').dataset.kind = event.kind;
    this.$('#beat-title').textContent = titles[event.kind] || (event.target ? `${event.service} → ${event.target}` : `Activity in ${event.service}`);
    this.$('#beat-description').textContent = event.message;
    this.$('#evidence-service').textContent = event.service;
    this.$('#evidence-meta').textContent = `${event.id} · ${event.severity.toUpperCase()}${event.trace ? ' · ' + event.trace : ' · shared / untraced'}`;
    this.$('#evidence-raw').textContent = event.raw;
    this.$('#open-source').textContent = `Open ${event.id} in source log ↗`;
    const attribution = event.service_source === 'unattributed' ? 'No service identifier was found. This event stays unattributed.' : event.service_source === 'log_format' ? 'Service name follows the text log format; inspect the source to verify attribution.' : 'Service name comes from an explicit field in the log.';
    this.$('#evidence-attribution').textContent = attribution + (event.clipped ? ' Evidence preview is clipped; open the source for the full line.' : '');
    this.renderMap(); this.renderTrack(); this.renderTrail();
  }
  renderMap() {
    const seen = this.events.slice(0, this.position + 1), first = seen.find(e => e.kind === 'failure');
    for (const [name, node] of this.nodeElements) {
      const observations = seen.filter(e => e.service === name), latest = observations.at(-1);
      let state = observations.length ? 'activity' : 'idle', resolved = null;
      for (const event of observations) {
        if (event.kind === 'failure') state = 'failure';
        else if (event.kind === 'recovery' || event.kind === 'success') { state = 'recovery'; resolved = event.kind; }
        else if (['retry', 'warning'].includes(event.kind) && state !== 'failure') state = 'warning';
      }
      node.dataset.state = state; node.dataset.first = String(first?.service === name);
      node.setAttribute('aria-pressed', String(this.service === name));
      node.querySelector('.node-state').textContent = {idle:'No event yet', activity:'Activity observed', failure:'Error observed', warning:'Warning observed', recovery:resolved === 'recovery' ? 'Recovery observed' : 'Success observed'}[state];
      node.querySelector('.node-foot').textContent = latest ? `${observations.length} event${observations.length === 1 ? '' : 's'} · ${latest.id}` : 'Recorded in full-log map';
      node.setAttribute('aria-label', `${name}: ${node.querySelector('.node-state').textContent}. Filter event trail.`);
    }
    const svg = this.$('#map-edges'); svg.replaceChildren();
    const defs = svgElement('defs', {}), marker = svgElement('marker', {id:'replay-arrow', viewBox:'0 0 10 10', refX:9, refY:5, markerWidth:5, markerHeight:5, orient:'auto-start-reverse'});
    marker.append(svgElement('path', {d:'M 0 0 L 10 5 L 0 10 z', fill:'#61768a'})); defs.append(marker); svg.append(defs);
    const activeIds = new Set(seen.map(e => e.id)), current = this.events[this.position];
    for (const link of this.data.links) {
      const a = this.positions.get(link.source), b = this.positions.get(link.target); if (!a || !b) continue;
      let x1, y1, x2, y2, path;
      if (a.y === b.y) {
        const forward = a.x < b.x; x1 = a.x + (forward ? a.width : 0); x2 = b.x + (forward ? 0 : b.width); y1 = a.y + 45; y2 = b.y + 45;
        path = `M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}`;
      } else {
        x1 = a.x + a.width / 2; y1 = a.y + a.height; x2 = b.x + b.width / 2; y2 = b.y;
        path = `M ${x1} ${y1} C ${x1} ${y1+25}, ${x2} ${y2-25}, ${x2} ${y2}`;
      }
      const active = link.event_ids.some(id => activeIds.has(id));
      const line = svgElement('path', {d:path, fill:'none', stroke:current?.target === link.target && current?.service === link.source ? '#90e6c3' : '#61768a', 'stroke-width':1.3, opacity:active ? .8 : .2, 'marker-end':'url(#replay-arrow)'});
      svg.append(line);
      if (active && this.playing && current?.target === link.target && current?.service === link.source && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
        const dot = svgElement('circle', {r:3, class:'flow-packet'}), motion = svgElement('animateMotion', {path, dur:'0.7s', repeatCount:1, fill:'freeze'}); dot.append(motion); svg.append(dot);
      }
    }
    this.$('#map-caption').textContent = this.data.links.length ? 'Full-log map · explicit call fields' : 'No explicit call fields; no connections inferred.';
  }
  renderTrack() {
    const svg = this.$('#event-track'), width = svg.clientWidth; if (!width || !this.events.length) return;
    svg.setAttribute('viewBox', `0 0 ${width} 58`); svg.replaceChildren();
    const timed = this.data.coverage.order === 'timestamp', first = this.events[0].offset_ms, end = this.events.at(-1).offset_ms;
    const fraction = (event, index) => timed && end > first ? (event.offset_ms - first) / (end - first) : index / Math.max(1, this.events.length - 1);
    const bins = Array.from({length:Math.min(70, Math.max(1, Math.floor(width / 8)))}, () => []);
    this.events.forEach((event, index) => bins[Math.min(bins.length - 1, Math.floor(fraction(event,index) * bins.length))].push(event));
    const highest = Math.max(1, ...bins.map(bin => bin.length)), colors = {failure:'#ff8895',retry:'#efc27a',warning:'#efc27a',change:'#8bb8fa',recovery:'#90e6c3',success:'#90e6c3',activity:'#61768a'};
    bins.forEach((bin,index) => {
      const priority = bin.find(e=>e.kind==='failure') || bin.find(e=>e.kind==='recovery') || bin.find(e=>e.kind==='retry') || bin[0];
      const height = bin.length ? 9 + 34 * Math.sqrt(bin.length / highest) : 2;
      const bar = svgElement('rect',{x:index*width/bins.length,y:50-height,width:Math.max(1,width/bins.length-3),height,rx:1,fill:colors[priority?.kind]||'#23313e',opacity:.85}); svg.append(bar);
    });
    const cursor = fraction(this.events[this.position],this.position)*(width-2)+1;
    svg.append(svgElement('line',{x1:cursor,x2:cursor,y1:0,y2:56,stroke:'#e8eef4','stroke-width':1}));
    svg.onclick = event => {
      const bounds=svg.getBoundingClientRect(), value=Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width));
      let nearest=0;this.events.forEach((item,index)=>{if(Math.abs(fraction(item,index)-value)<Math.abs(fraction(this.events[nearest],nearest)-value))nearest=index;});this.seek(nearest);
    };
  }
  renderTrail() {
    const list = this.$('#event-list'), selected = this.events[this.position], focused = document.activeElement?.dataset.eventId;
    list.replaceChildren(); this.$('#clear-service').hidden = !this.service;
    const items = this.events.filter(event => !this.service || event.service === this.service);
    let center = items.findIndex(event => event.id === selected?.id);
    if (center < 0) { center = items.findIndex(event => this.events.indexOf(event) >= this.position); if (center < 0) center = items.length - 1; }
    const start = Math.max(0, Math.min(center - 2, items.length - 7));
    for (const event of items.slice(start, start + 7)) {
      const button = element('button','event-row'); button.type='button';button.dataset.kind=event.kind;button.dataset.eventId=event.id;button.setAttribute('aria-current',String(event.id===selected?.id));
      const info=element('span','event-info');info.append(element('strong','',`${event.service} · ${event.kind}`),element('small','',event.message.length>125?event.message.slice(0,125)+'…':event.message));
      button.append(element('span','line-ref',event.id),element('time','',clock(event)),info);
      button.onclick=()=>{this.seek(this.events.indexOf(event));this.tab('evidence');};list.append(button);
      if(focused===event.id)button.focus({preventScroll:true});
    }
    if(!items.length)list.append(element('p','fine-print','No source events for this service in the selected request.'));
  }
  reference(line) {
    const button=element('button','evidence-chip',`L${line}`);button.type='button';
    button.onclick=()=>{const index=this.events.findIndex(event=>event.line===line);if(index>=0){this.seek(index);this.tab('evidence');}else this.openSource(line);};return button;
  }
  openSource(line) {
    if(!Number.isInteger(line)||line<1||line>this.lines.length)return;
    this.$('#raw-source').open=true;const pre=this.$('#content');pre.replaceChildren();
    const format=(text,index)=>`L${index+1}  ${text}`;
    pre.append(document.createTextNode(this.lines.slice(0,line-1).map(format).join('\n')+(line>1?'\n':'')));
    const mark=element('span','source-line',`L${line}  ${this.lines[line-1]}`);mark.dataset.selected='true';pre.append(mark);
    pre.append(document.createTextNode((line<this.lines.length?'\n':'')+this.lines.slice(line).map((text,index)=>format(text,index+line)).join('\n')));
    mark.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});
  }
  ask(question) {
    if(!this.data||!question.trim())return;
    this.question=question;this.$('#question').value=question;
    const lower=question.toLowerCase(),events=this.events, failures=events.filter(e=>e.kind==='failure'),first=failures[0];
    let text='', references=[];
    const described=e=>`${e.service} at ${clock(e)} (${e.id})`;
    if(/chang|deploy|before/.test(lower)) {
      const changes=events.filter(e=>e.kind==='change'&&(!first||events.indexOf(e)<events.indexOf(first)));
      text=changes.length?`Before the first recorded failure, the log shows ${changes.length} change event${changes.length===1?'':'s'}. The closest is ${described(changes.at(-1))}. Timing makes it worth investigating; it does not establish causality.`:'No explicit deployment or configuration change is recorded before the first failure in this replay.';references=[...changes.slice(-3),...(first?[first]:[])];
    } else if(/retry|retries|attempt/.test(lower)) {
      references=events.filter(e=>e.kind==='retry');text=references.length?`There are ${references.length} retry events in this view, involving ${[...new Set(references.map(e=>e.service))].join(', ')}. Compare the retry messages and timings with the failure evidence. These records alone do not prove retries caused additional load.`:'No explicit retry events were identified in this view.';references=references.slice(0,6);
    } else if(/recover|restor|resolv/.test(lower)) {
      references=events.filter(e=>e.kind==='recovery');text=references.length?`Explicit recovery messages first appear in ${described(references[0])}. Recovery is observed for ${[...new Set(references.map(e=>e.service))].join(', ')}. A success for one request does not establish system-wide recovery.`:'No explicit recovery message appears in this replay. A missing recovery event does not prove the service stayed down.';references=references.slice(0,6);
    } else if(/first|start|origin/.test(lower)) {
      text=first?`The earliest recorded error in this view is ${described(first)}. This is the first observed fault, not necessarily the root cause or the first failure outside this file.`:'No error-level or failing HTTP-status event was identified in this view.';references=first?[first]:[];
    } else if(/why|fail|error|broke/.test(lower)) {
      const service=this.data.nodes.find(node=>new RegExp(`(^|[^a-z0-9_])${node.id.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}([^a-z0-9_]|$)`).test(lower));
      const symptom=service?failures.find(e=>e.service===service.id):failures.at(-1);
      if(symptom?.trace) {
        references=failures.filter(e=>e.trace===symptom.trace&&events.indexOf(e)<=events.indexOf(symptom));
        text=`Request ${symptom.trace} connects these recorded errors: ${references.map(e=>described(e)).join(' → ')}. This reconstructs the observed failure sequence; confirming a cause needs more evidence.`;
      } else {references=symptom?[symptom]:failures.slice(0,4);text=references.length?'These are the matching recorded errors. Without a shared request identifier, the replay cannot establish that they belong to one failure chain.':'No matching error was identified. Try a service name, request ID, or message keyword.';}
    } else {
      const tokens=lower.match(/[a-z0-9_-]{3,}/g)||[];
      references=events.filter(e=>tokens.some(token=>`${e.service} ${e.trace||''} ${e.message}`.toLowerCase().includes(token))).slice(0,6);
      text=references.length?`These source events match your search. Inspect their evidence or narrow the view to a request. This is source search, not an AI-generated explanation.`:'No source events match that question. Try first failure, changes, retries, recovery, or a service/request identifier.';
    }
    const answer=this.$('#answer');answer.replaceChildren(element('span','answer-label','TIMELINE EVIDENCE · FULL SELECTED REPLAY'),element('p','',text));
    const refs=element('div','answer-refs');references.slice(0,8).forEach(event=>refs.append(this.reference(event.line)));answer.append(refs);answer.hidden=false;
  }
  renderHypotheses(hypotheses) {
    const target=this.$('#hypotheses');target.replaceChildren();const validated=[];
    for(const hypothesis of (Array.isArray(hypotheses)?hypotheses:[]).slice(0,3)) {
      if(!hypothesis || typeof hypothesis.title!=='string' || typeof hypothesis.explanation!=='string')continue;
      const refs=Array.isArray(hypothesis.evidence_lines)?[...new Set(hypothesis.evidence_lines.filter(n=>Number.isInteger(n)&&n>0&&n<=this.lines.length&&this.lines[n-1].trim()))].slice(0,8):[];
      if(!refs.length)continue;
      validated.push({title:hypothesis.title,explanation:hypothesis.explanation,evidence_lines:refs,basis:'AI hypothesis'});
      const item=element('div','hypothesis');item.append(element('span','eyebrow','AI HYPOTHESIS'),element('h3','',hypothesis.title),element('p','',hypothesis.explanation));
      const chips=element('div','answer-refs');refs.forEach(line=>chips.append(this.reference(line)));item.append(chips);target.append(item);
    }
    return validated;
  }
  export() {
    if(!this.data)return;
    const output={filename:this.record.filename,synthetic:!!this.record.demo,exported_at:new Date().toISOString(),selected_request:this.trace||null,interpretation:'Observed log sequence and explicit relationships; AI hypotheses are unconfirmed.',replay:this.data};
    const url=URL.createObjectURL(new Blob([JSON.stringify(output,null,2)],{type:'application/json'}));
    const link=element('a');link.href=url;link.download='incident-replay.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
}
