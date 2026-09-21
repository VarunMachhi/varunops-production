(() => {
  'use strict';
  const qs = (s, root=document) => root.querySelector(s);
  const qsa = (s, root=document) => [...root.querySelectorAll(s)];
  const content = qs('#consoleContent');
  const title = qs('#viewTitle');
  const eyebrow = qs('#viewEyebrow');
  const subtitle = qs('#viewSubtitle');
  const search = qs('#globalSearch');
  const queueBadge = qs('#queueBadge');
  const requestBadge = qs('#requestBadge');
  const ticketBadge = qs('#ticketBadge');
  const complianceBadge = qs('#complianceBadge');
  const syncStamp = qs('#syncStamp');
  const csrf = qs('meta[name="csrf-token"]')?.content || '';
  const toastEl = qs('#toast');
  const modal = qs('#confirmModal');
  const modalTitle = qs('#confirmTitle');
  const modalText = qs('#confirmText');
  const modalIcon = qs('#confirmIcon');
  const modalOk = qs('#confirmOk');
  const modalCancel = qs('#confirmCancel');

  let state = { machines: [], apps: [], commands: [], activity: [], software_requests: [], tickets: [], network_policies: [], employees: [], unauthorized_count: 0, user: null };
  let currentView = 'overview';
  let searchTerm = '';
  const selectedMachines = new Set();
  const selectedCells = new Set();
  let pendingConfirm = null;

  const esc = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  const fmtTime = value => {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
  };

  const relative = value => {
    if (!value) return 'Never';
    const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds/60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds/3600)}h ago`;
    return `${Math.floor(seconds/86400)}d ago`;
  };

  const toast = message => {
    toastEl.textContent = message;
    toastEl.classList.add('show');
    clearTimeout(toastEl._timer);
    toastEl._timer = setTimeout(() => toastEl.classList.remove('show'), 2600);
  };

  async function api(url, options={}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = { 'Accept':'application/json', ...(options.headers || {}) };
    if (!['GET','HEAD','OPTIONS'].includes(method)) {
      headers['X-CSRFToken'] = csrf;
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(url, { credentials:'same-origin', ...options, method, headers });
    if (response.status === 401 || response.status === 403) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Your session is not authorized for this action.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  async function refresh(silent=false) {
    if (!silent) content.innerHTML = '<div class="loading-state"><span></span><p>Loading workspace…</p></div>';
    try {
      state = await api('/api/bootstrap/');
      queueBadge.textContent = state.commands.filter(c => ['queued','running'].includes(c.status)).length;
      requestBadge.textContent = state.software_requests.filter(r => r.status === 'submitted').length;
      ticketBadge.textContent = state.tickets.filter(t => !['resolved','closed'].includes(t.status)).length;
      if (complianceBadge) complianceBadge.textContent = state.unauthorized_count || 0;
      syncStamp.textContent = `Synced ${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
      render();
    } catch (err) {
      content.innerHTML = `<div class="console-panel empty-state"><strong>Couldn’t load the console.</strong><p>${esc(err.message)}</p></div>`;
      toast(err.message);
    }
  }

  const visibleMachines = () => {
    if (!searchTerm) return state.machines;
    return state.machines.filter(m => {
      const haystack = [m.name,m.branch,m.device_type,m.ip_address,m.os_version,m.serial_number,m.policy,...(m.tags||[])].join(' ').toLowerCase();
      const apps = (m.installed_apps||[]).map(a => `${a.name} ${a.slug} ${a.version}`).join(' ').toLowerCase();
      return haystack.includes(searchTerm) || apps.includes(searchTerm);
    });
  };

  const installationFor = (m, slug) => (m.installed_apps || []).find(x => x.slug === slug);
  const outdatedCount = m => (m.installed_apps || []).filter(x => x.version && x.latest_version && x.version !== x.latest_version).length;
  const totalPossible = () => Math.max(1, state.machines.length * Math.max(1, state.apps.length));
  const totalOutdated = () => state.machines.reduce((n,m) => n + outdatedCount(m), 0);
  const healthPct = () => Math.max(0, Math.round((1 - totalOutdated()/totalPossible()) * 100));

  const pageMeta = {
    overview:['Workspace','Overview','Your IT estate at a glance.'],
    apps:['Software','Apps','Install, update and remove approved software.'],
    catalog:['Software','Software Store','Manage approved company applications, versions and licensing notes.'],
    compliance:['Security','Compliance','See approved-software drift, live usage and unauthorized installations.'],
    network:['Network','Website policies','Apply per-PC Edge/Chrome allowlists and blocklists.'],
    machines:['Inventory','Machines','Branch endpoints and reported hardware context.'],
    policies:['Control','Policies','Choose how software changes are handled.'],
    employees:['People','Employees','Employee profiles, assigned PCs and live device linkage.'],
    requests:['Employees','Software requests','Review employee requests and safely queue approved apps.'],
    tickets:['Support','IT tickets','Assign, reply to and resolve employee support issues.'],
    commands:['Operations','Commands','Queued, running and completed endpoint work.'],
    activity:['Audit','Activity','A server-side timeline of important actions.'],
  };

  function render() {
    const meta = pageMeta[currentView];
    eyebrow.textContent = meta[0]; title.textContent = meta[1]; subtitle.textContent = meta[2];
    qsa('.console-nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === currentView));
    const views = { overview:renderOverview, apps:renderApps, catalog:renderCatalog, compliance:renderCompliance, network:renderNetwork, employees:renderEmployees, machines:renderMachines, policies:renderPolicies, requests:renderRequests, tickets:renderTickets, commands:renderCommands, activity:renderActivity };
    content.innerHTML = views[currentView]();
    bindDynamic();
  }

  function renderOverview() {
    const machines = visibleMachines();
    const online = state.machines.filter(m => m.online).length;
    const branches = new Set(state.machines.map(m => m.branch).filter(Boolean)).size;
    const queued = state.commands.filter(c => ['queued','running'].includes(c.status)).length;
    const health = healthPct();
    const coverage = state.apps.map(app => {
      const installed = state.machines.filter(m => installationFor(m, app.slug)).length;
      const pct = state.machines.length ? Math.round(installed/state.machines.length*100) : 0;
      return `<div class="health-item"><div class="health-title"><b>${esc(app.name)}</b><span>${installed}/${state.machines.length} · ${pct}%</span></div><div class="health-bar"><i style="width:${pct}%"></i></div></div>`;
    }).join('');
    return `
      <div class="metric-grid">
        ${metric('Devices',state.machines.length,`${online} online`, state.machines.length ? Math.round(online/state.machines.length*100) : 0)}
        ${metric('Software health',`${health}%`,`${totalOutdated()} updates due`,health)}
        ${metric('Branches',branches,'Reporting to one workspace',Math.min(100,branches*18))}
        ${metric('Active commands',queued,queued ? 'Queued or running' : 'Nothing waiting',queued ? 62 : 100)}
        ${metric('Employee requests',state.software_requests.filter(r=>r.status==='submitted').length,'Waiting for IT review',state.software_requests.some(r=>r.status==='submitted') ? 48 : 100)}
        ${metric('Open tickets',state.tickets.filter(t=>!['resolved','closed'].includes(t.status)).length,'Employee support queue',state.tickets.some(t=>!['resolved','closed'].includes(t.status)) ? 55 : 100)}
      </div>
      <div class="dashboard-columns">
        <section class="console-panel">
          <div class="panel-heading"><div><h2>Device health</h2><p>Connectivity, policy and outstanding software.</p></div><div class="toolbar"><button class="action-button primary" data-action="update-all">Update all outdated</button></div></div>
          <div class="data-table-wrap"><table class="data-table"><thead><tr><th>Machine</th><th>Branch</th><th>Status</th><th>Policy</th><th>Updates due</th><th>Last seen</th></tr></thead><tbody>
          ${machines.length ? machines.map(m => `<tr><td><span class="machine-name">${esc(m.name)}</span><span class="machine-meta">${esc(m.device_type)}</span></td><td>${esc(m.branch||'—')}</td><td>${statusPill(m.online)}</td><td>${policyPill(m.policy)}</td><td>${outdatedCount(m)}</td><td>${esc(relative(m.last_seen))}</td></tr>`).join('') : emptyRow(6)}
          </tbody></table></div>
        </section>
        <section class="console-panel"><div class="panel-heading"><div><h2>Software coverage</h2><p>Approved catalog presence.</p></div></div><div class="health-list">${coverage || '<div class="empty-state"><p>No apps in catalog.</p></div>'}</div></section>
      </div>
      <section class="console-panel"><div class="panel-heading"><div><h2>Recent activity</h2><p>Latest audited events from server and agents.</p></div><button class="subtle-button" data-view-jump="activity">View all</button></div>${activityMarkup(state.activity.slice(0,7))}</section>`;
  }

  function renderApps() {
    const machines = visibleMachines();
    const appHeads = state.apps.map(a => `<th>${esc(a.name)}<span class="machine-meta">Latest ${esc(a.latest_version||'—')}</span></th>`).join('');
    const rows = machines.map(m => `<tr>
      <td><input class="row-check" type="checkbox" data-machine-select="${esc(m.id)}" ${selectedMachines.has(m.id)?'checked':''}></td>
      <td><span class="machine-name">${esc(m.name)}</span><span class="machine-meta">${esc(m.branch||'—')}</span></td>
      ${state.apps.map(a => renderAppCell(m,a)).join('')}
      <td>${statusPill(m.online)}</td>
    </tr>`).join('');
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Apps × Machines</h2><p>Select app cells or complete device rows, then queue an action.</p></div><div class="toolbar"><button class="action-button primary" data-action="install">Install</button><button class="action-button" data-action="update">Update</button><button class="danger-button" data-action="uninstall">Uninstall</button><button class="subtle-button" data-action="clear-selection">Clear</button></div></div>
      <div class="data-table-wrap"><table class="data-table"><thead><tr><th><input class="select-all" type="checkbox" id="selectAllMachines"></th><th>Machine</th>${appHeads}<th>Status</th></tr></thead><tbody>${rows || emptyRow(state.apps.length+3)}</tbody></table></div>
      <p class="selection-note">${selectedCells.size} app cell(s) and ${selectedMachines.size} complete machine(s) selected. Locked machines are rejected by the server.</p></section>`;
  }

  function metricBar(label, value, suffix='%') {
    const n=Math.max(0,Math.min(100,Number(value)||0));
    return `<div class="live-meter"><span><b>${esc(label)}</b><i>${esc(Number(value||0).toFixed(1))}${esc(suffix)}</i></span><div><em style="width:${n}%"></em></div></div>`;
  }

  function renderCatalog() {
    const cards=state.apps.map(a=>`<article class="catalog-card"><div class="software-icon">${esc(a.name.slice(0,1).toUpperCase())}</div><div><h3>${esc(a.name)}</h3><p>${esc(a.description||'Approved company software')}</p><small>${esc(a.publisher||'Publisher not set')} · ${esc(a.category||'General')} · Latest ${esc(a.latest_version||'—')}</small><div class="catalog-tags"><span>${a.employee_visible?'Employee store':'IT only'}</span><span>${a.license_required?'License required':'No managed license'}</span>${a.winget_id?`<span>${esc(a.winget_id)}</span>`:''}</div></div><div class="catalog-policy-actions"><select data-app-policy-mode="${esc(a.slug)}"><option value="required">Required</option><option value="optional" selected>Optional</option><option value="blocked">Blocked</option></select><label><input type="checkbox" data-app-auto-update="${esc(a.slug)}" checked> Auto update</label><button class="secondary-button compact" data-apply-app-policy="${esc(a.slug)}">Apply to selected PCs</button></div></article>`).join('');
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Company Software Store</h2><p>Only legitimate approved installers/packages belong here. Use Winget package IDs, versions, descriptions and license notes.</p></div><span class="selection-note">${selectedMachines.size} PC(s) selected</span></div>
      <form id="catalogForm" class="settings-form"><div class="form-grid"><label>Name<input name="name" required placeholder="Google Chrome"></label><label>Slug<input name="slug" required placeholder="google-chrome"></label><label>Winget ID<input name="winget_id" placeholder="Google.Chrome"></label><label>Latest version<input name="latest_version" placeholder="Stable/current"></label><label>Publisher<input name="publisher"></label><label>Category<input name="category" placeholder="Browser"></label></div><label>Description<textarea name="description" rows="2"></textarea></label><label>Detection names <small>comma separated</small><input name="detection_names" placeholder="Google Chrome,Chrome"></label><div class="form-grid"><label><input type="checkbox" name="employee_visible" checked> Show in employee store</label><label><input type="checkbox" name="license_required"> License required</label></div><label>License / activation notes <small>Do not store cracked software or bypass instructions.</small><input name="license_notes" placeholder="Example: Microsoft 365 user license assigned by IT"></label><label>Update notes<input name="update_notes" placeholder="Stable channel; restart browser after update"></label><button class="apple-button" type="submit">Add / update app</button></form></section>
      <section class="console-panel"><div class="panel-heading"><div><h2>Approved applications</h2><p>Set required, optional or blocked state for selected machines.</p></div></div><div class="catalog-grid">${cards||'<div class="empty-state"><p>No apps configured.</p></div>'}</div></section>`;
  }

  function renderCompliance() {
    const rows=[];
    for(const m of visibleMachines()){
      const metric=m.latest_metric||{};
      const alerts=(m.unauthorized_software||[]).filter(x=>!x.resolved);
      rows.push(`<article class="compliance-device"><div class="panel-heading"><div><h3>${esc(m.name)}</h3><p>${esc(m.branch||'—')} · ${m.online?'Online':'Offline'} · ${esc(m.compliance_mode||'audit')} mode</p></div><div class="toolbar"><button class="subtle-button" data-select-one="${esc(m.id)}">Select</button></div></div><div class="telemetry-grid">${metricBar('CPU',metric.cpu_percent||0)}${metricBar('RAM',metric.memory_percent||0)}${metricBar('Storage',metric.storage_percent||0)}</div><div class="compliance-alerts">${alerts.length?alerts.map(x=>`<div class="warning-row"><div><b>⚠ ${esc(x.display_name)}</b><small>${esc(x.version||'')} ${x.publisher?'· '+esc(x.publisher):''} · detected ${esc(relative(x.last_seen))}</small></div><div><button class="secondary-button compact" data-unauthorized-action="allow" data-alert-id="${x.id}">Allow on this PC</button><button class="danger-button compact" data-unauthorized-action="uninstall" data-alert-id="${x.id}">Uninstall</button></div></div>`).join(''):'<div class="healthy-note">✓ No unauthorized third-party software currently detected.</div>'}</div></article>`);
    }
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Software compliance</h2><p>Audit mode warns. Enforce mode also restores required catalog apps and removes catalog apps marked Blocked.</p></div><div class="toolbar"><button class="secondary-button" data-compliance="audit">Audit selected</button><button class="apple-button" data-compliance="enforce">Enforce selected</button></div></div><p class="selection-note">${selectedMachines.size} PC(s) selected. Unknown third-party software is never given arbitrary shell commands; removal uses a validated Winget name task and may require manual follow-up if Winget cannot identify it.</p></section><div class="compliance-grid">${rows.join('')||'<div class="console-panel empty-state"><p>No devices.</p></div>'}</div>`;
  }

  function renderNetwork() {
    const options=state.network_policies.map(p=>`<option value="${p.id}">${esc(p.name)} · ${esc(p.mode)}</option>`).join('');
    const cards=state.network_policies.map(p=>`<article class="policy-card network-card"><div class="policy-icon">◎</div><h3>${esc(p.name)}</h3><p>${p.mode==='allowlist'?'Only listed URLs are allowed in managed Edge/Chrome.':'Listed URLs are blocked in managed Edge/Chrome.'}</p><small>${p.machine_count||0} PC(s) · revision ${p.revision}</small><div class="site-preview">${(p.mode==='allowlist'?p.allowed_sites:p.blocked_sites).slice(0,6).map(x=>`<span>${esc(x)}</span>`).join('')||'<span>No sites yet</span>'}</div></article>`).join('');
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Create website policy</h2><p>Per-PC managed browser restriction. Allowlist mode blocks everything except allowed URL patterns; blocklist mode only blocks selected patterns.</p></div></div><form id="networkPolicyForm" class="settings-form"><div class="form-grid"><label>Policy name<input name="name" required placeholder="Clinic Work Only"></label><label>Mode<select name="mode"><option value="allowlist">Allow only selected sites</option><option value="blocklist">Block selected sites</option></select></label></div><label>Allowed sites <small>one per line, e.g. https://*.dncc.in/*</small><textarea name="allowed_sites" rows="4"></textarea></label><label>Blocked sites <small>one per line</small><textarea name="blocked_sites" rows="4"></textarea></label><div class="form-grid"><label><input type="checkbox" name="enforce_edge" checked> Microsoft Edge</label><label><input type="checkbox" name="enforce_chrome" checked> Google Chrome</label></div><button class="apple-button" type="submit">Save policy</button></form></section><section class="console-panel"><div class="panel-heading"><div><h2>Assign to selected PCs</h2><p>${selectedMachines.size} PC(s) selected.</p></div><div class="toolbar"><select id="networkAssignSelect"><option value="">No policy</option>${options}</select><button class="secondary-button" data-assign-network>Apply</button></div></div><div class="policy-grid">${cards||'<div class="empty-state"><p>No network policies configured.</p></div>'}</div></section>`;
  }

  function renderEmployees(){const rows=(state.employees||[]).filter(e=>!searchTerm||`${e.full_name} ${e.username} ${e.employee_code||''} ${e.department||''} ${e.branch||''} ${e.assigned_machine_name||''}`.toLowerCase().includes(searchTerm));return`<section class="console-panel"><div class="panel-heading"><div><h2>Employee directory</h2><p>Profiles are linked server-side to managed machines. Pairing or Django Admin can assign a PC.</p></div></div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Employee</th><th>Code</th><th>Department</th><th>Branch</th><th>Job title</th><th>Phone</th><th>Assigned PC</th><th>PC status</th></tr></thead><tbody>${rows.length?rows.map(e=>{const m=state.machines.find(x=>x.id===e.assigned_machine_id);return`<tr><td><span class="machine-name">${esc(e.full_name||e.username)}</span><span class="machine-meta">${esc(e.username)}${e.email?' · '+esc(e.email):''}</span></td><td>${esc(e.employee_code||'—')}</td><td>${esc(e.department||'—')}</td><td>${esc(e.branch||'—')}</td><td>${esc(e.job_title||'—')}</td><td>${esc(e.phone||'—')}</td><td>${esc(e.assigned_machine_name||'Not paired')}</td><td>${m?statusPill(m.online):'—'}</td></tr>`}).join(''):emptyRow(8)}</tbody></table></div></section>`}

  function renderMachines() {
    const machines = visibleMachines();
    const powerLabel = e => e.event_type === 'boot' ? 'Started' : e.event_type === 'shutdown' ? 'Shutdown' : 'Unexpected shutdown';
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Machine inventory</h2><p>Only enrolled VarunOps agents can report endpoint data. Usage is the latest authenticated sample.</p></div><div class="toolbar"><button class="subtle-button" data-action="clear-selection">Clear selection</button></div></div>
      <div class="data-table-wrap"><table class="data-table"><thead><tr><th></th><th>Machine</th><th>Branch</th><th>Type</th><th>IP</th><th>OS / serial</th><th>Policy</th><th>Compliance</th><th>Network</th><th>Live usage</th><th>Status</th></tr></thead><tbody>
      ${machines.length ? machines.map(m => `<tr><td><input class="row-check" type="checkbox" data-machine-select="${esc(m.id)}" ${selectedMachines.has(m.id)?'checked':''}></td><td><span class="machine-name">${esc(m.name)}</span><span class="machine-meta">ID ${esc(m.id.slice(0,8))}</span></td><td>${esc(m.branch||'—')}</td><td>${esc(m.device_type)}</td><td>${esc(m.ip_address||'—')}</td><td><span class="machine-name">${esc(m.os_version||'—')}</span><span class="machine-meta">${esc(m.serial_number||'No serial reported')}</span></td><td>${policyPill(m.policy)}</td><td>${esc(m.compliance_mode||'audit')}</td><td>${esc(m.network_policy_name||'None')}</td><td>${m.latest_metric?`${esc(Math.round(m.latest_metric.cpu_percent))}% CPU · ${esc(Math.round(m.latest_metric.memory_percent))}% RAM · ${esc(Math.round(m.latest_metric.storage_percent))}% disk`:'—'}</td><td>${statusPill(m.online)}</td></tr>`).join('') : emptyRow(11)}
      </tbody></table></div></section>
      <section class="console-panel"><div class="panel-heading"><div><h2>Individual device details</h2><p>Hardware, live health, software policy and recent startup/shutdown history for each PC.</p></div></div><div class="software-inventory-list">${machines.map(m=>{const metric=m.latest_metric||{};const req=(m.app_policies||[]).filter(x=>x.mode==='required');const blocked=(m.app_policies||[]).filter(x=>x.mode==='blocked');return`<details class="software-inventory-device"><summary><span><b>${esc(m.name)}</b><small>${esc(m.branch||'—')} · ${m.online?'Online':'Offline'} · last seen ${esc(relative(m.last_seen))}</small></span><span>${(m.unauthorized_software||[]).filter(x=>!x.resolved).length} compliance warning(s)</span></summary><div class="device-detail-grid"><div><h4>Live health</h4><div class="telemetry-grid">${metricBar('CPU',metric.cpu_percent||0)}${metricBar('RAM',metric.memory_percent||0)}${metricBar('Storage',metric.storage_percent||0)}</div><p class="machine-meta">RAM ${esc(metric.memory_used_gb||0)} / ${esc(metric.memory_total_gb||0)} GB · Storage ${esc(metric.storage_used_gb||0)} / ${esc(metric.storage_total_gb||0)} GB · Uptime ${esc(Math.floor((metric.uptime_seconds||0)/3600))}h</p></div><div><h4>Hardware inventory</h4><div class="system-info">${Object.entries(m.system_info||{}).slice(0,12).map(([k,v])=>`<span>${esc(k)}: ${esc(v)}</span>`).join('')||'<span>No hardware inventory yet</span>'}</div></div><div><h4>Policy</h4><p class="machine-meta">Endpoint: ${esc(m.policy)} · Compliance: ${esc(m.compliance_mode||'audit')} · Website: ${esc(m.network_policy_name||'None')}</p><p class="machine-meta">Required apps: ${req.length?req.map(x=>esc(x.app_name)).join(', '):'None'}<br>Blocked apps: ${blocked.length?blocked.map(x=>esc(x.app_name)).join(', '):'None'}</p></div><div><h4>Recent power history</h4><div class="activity-list">${(m.recent_power_events||[]).length?(m.recent_power_events||[]).map(e=>`<div class="activity-row"><i class="event-dot ${e.event_type==='unexpected_shutdown'?'error':e.event_type==='boot'?'success':'info'}"></i><span><b>${esc(powerLabel(e))}</b><small>${esc(fmtTime(e.occurred_at))}</small></span></div>`).join(''):'<p class="machine-meta">No Windows power events reported yet.</p>'}</div></div></div></details>`}).join('')||'<div class="empty-state"><p>No enrolled devices.</p></div>'}</div></section>
      <section class="console-panel"><div class="panel-heading"><div><h2>Detected software by device</h2><p>Complete agent-reported program inventory with company approval classification.</p></div></div><div class="software-inventory-list">${machines.map(m=>`<details class="software-inventory-device"><summary><span><b>${esc(m.name)}</b><small>${esc(m.branch||'—')} · ${(m.detected_software||[]).length} detected program(s)</small></span><span>${(m.detected_software||[]).filter(x=>x.classification==='unauthorized').length} warning(s)</span></summary><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Application</th><th>Version</th><th>Publisher</th><th>Classification</th><th>Last seen</th></tr></thead><tbody>${(m.detected_software||[]).length?(m.detected_software||[]).map(s=>`<tr><td><span class="machine-name">${esc(s.display_name)}</span></td><td>${esc(s.version||'—')}</td><td>${esc(s.publisher||'—')}</td><td><span class="software-class ${esc(s.classification)}">${esc(String(s.classification||'').replaceAll('_',' '))}</span></td><td>${esc(relative(s.last_seen))}</td></tr>`).join(''):emptyRow(5)}</tbody></table></div></details>`).join('')}</div></section>`;
  }

  function renderPolicies() {
    const cards = [
      ['manual','⌁','Manual','Only changes you explicitly queue are sent to the device.'],
      ['automatic','↻','Automatic','Marks the machine for automated maintenance workflows you can extend server-side.'],
      ['locked','⌽','Locked','Blocks new install, update and uninstall commands from the console.'],
    ];
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Apply a policy</h2><p>Select machines in Apps or Machines first.</p></div><span class="selection-note">${selectedMachines.size} machine(s) selected</span></div><div class="policy-grid">${cards.map(([key,icon,name,desc])=>`<article class="policy-card" data-policy="${key}"><div class="policy-icon">${icon}</div><h3>${name}</h3><p>${desc}</p></article>`).join('')}</div></section>
      <section class="console-panel"><div class="panel-heading"><div><h2>Current assignment</h2><p>Policy status from the backend.</p></div></div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Machine</th><th>Branch</th><th>Policy</th><th>Status</th></tr></thead><tbody>${visibleMachines().map(m=>`<tr><td><span class="machine-name">${esc(m.name)}</span></td><td>${esc(m.branch||'—')}</td><td>${policyPill(m.policy)}</td><td>${statusPill(m.online)}</td></tr>`).join('')}</tbody></table></div></section>`;
  }

  function requestStatusPill(s){return `<span class="command-status ${esc(s)}">${esc(String(s||'').replaceAll('_',' '))}</span>`}

  function renderRequests() {
    const rows = state.software_requests.filter(r => !searchTerm || `${r.employee_name} ${r.machine_name} ${r.app_name} ${r.status} ${r.reason}`.toLowerCase().includes(searchTerm));
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Employee software requests</h2><p>Approval creates only allow-listed install/update/uninstall commands for the employee's assigned managed PC.</p></div><button class="subtle-button" data-action="refresh">Refresh</button></div>
      <div class="data-table-wrap"><table class="data-table"><thead><tr><th>Requested</th><th>Employee</th><th>Machine</th><th>Application</th><th>Reason</th><th>Status</th><th>Action</th></tr></thead><tbody>
      ${rows.length ? rows.map(r=>`<tr><td>${esc(fmtTime(r.requested_at))}</td><td><span class="machine-name">${esc(r.employee_name)}</span><span class="machine-meta">${esc(r.employee_username)}</span></td><td>${esc(r.machine_name)}</td><td><span class="machine-name">${esc(r.app_name)}</span><span class="machine-meta">${esc((r.action||'install').toUpperCase())} · ${r.current_version?`Installed ${esc(r.current_version)} · `:''}Latest ${esc(r.latest_version||'—')}</span></td><td>${esc(r.reason||'No reason provided')}</td><td>${requestStatusPill(r.status)}</td><td>${r.status==='submitted'?`<div class="toolbar"><button class="action-button primary" data-software-decision="approve" data-request-id="${esc(r.id)}">Approve</button><button class="danger-button" data-software-decision="reject" data-request-id="${esc(r.id)}">Reject</button></div>`:`<span class="machine-meta">${esc(r.admin_note||r.command_status||'Reviewed')}</span>`}</td></tr>`).join('') : emptyRow(7)}
      </tbody></table></div></section>`;
  }

  function renderTickets() {
    const tickets = state.tickets.filter(t => !searchTerm || `${t.employee_name} ${t.machine_name||''} ${t.subject} ${t.category} ${t.priority} ${t.status}`.toLowerCase().includes(searchTerm));
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Employee IT tickets</h2><p>Ticket conversations stay inside VarunOps and are visible only to the employee and authorized staff.</p></div><button class="subtle-button" data-action="refresh">Refresh</button></div>
      <div class="ticket-admin-list">${tickets.length?tickets.map(t=>`<details class="ticket-admin-card" ${!['resolved','closed'].includes(t.status)?'open':''}><summary><div><span class="ticket-priority ${esc(t.priority)}">${esc(t.priority)}</span><b>${esc(t.subject)}</b><small>${esc(t.employee_name)} · ${esc(t.machine_name||'No assigned PC')} · ${esc(fmtTime(t.created_at))}</small></div><div>${requestStatusPill(t.status)}</div></summary>
      <div class="ticket-admin-body"><p class="ticket-description">${esc(t.description)}</p><div class="ticket-meta-row"><span>Category <b>${esc(t.category)}</b></span><span>Assigned <b>${esc(t.assigned_to_name||'Unassigned')}</b></span></div>
      <div class="ticket-thread">${(t.messages||[]).length?(t.messages||[]).map(m=>`<div class="ticket-message ${m.author_is_staff?'staff':'employee'}"><b>${esc(m.author_name)}</b><p>${esc(m.body||'')}</p>${m.attachment?`<a href="${esc(m.attachment.download_url)}">📎 ${esc(m.attachment.original_name)}</a>`:''}<small>${esc(fmtTime(m.created_at))}</small></div>`).join(''):'<p class="machine-meta">No replies yet.</p>'}</div>
      <div class="ticket-reply"><textarea id="reply-${esc(t.id)}" rows="2" maxlength="4000" placeholder="Reply to employee…"></textarea><button class="action-button" data-ticket-reply="${esc(t.id)}">Send reply</button></div>
      <div class="toolbar ticket-actions">${t.status==='submitted'?`<button class="action-button primary" data-ticket-action="assign" data-ticket-id="${esc(t.id)}">Assign to me</button>`:''}${!['resolved','closed'].includes(t.status)?`<button class="action-button" data-ticket-action="in_progress" data-ticket-id="${esc(t.id)}">In progress</button><button class="action-button primary" data-ticket-action="resolved" data-ticket-id="${esc(t.id)}">Resolve</button>`:''}${t.status==='resolved'?`<button class="subtle-button" data-ticket-action="closed" data-ticket-id="${esc(t.id)}">Close</button>`:''}${['resolved','closed'].includes(t.status)?`<button class="subtle-button" data-ticket-action="reopen" data-ticket-id="${esc(t.id)}">Reopen</button>`:''}</div>
      </div></details>`).join(''):'<div class="empty-state"><strong>No tickets.</strong><p>Employee support requests will appear here.</p></div>'}</div></section>`;
  }

  function renderCommands() {
    const cmds = state.commands.filter(c => !searchTerm || `${c.machine_name} ${c.app_name} ${c.action} ${c.status}`.toLowerCase().includes(searchTerm));
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Command queue</h2><p>Server-owned state: queued → running → succeeded / failed.</p></div><button class="subtle-button" data-action="refresh">Refresh</button></div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Requested</th><th>Machine</th><th>App</th><th>Action</th><th>Status</th><th>Result</th><th></th></tr></thead><tbody>${cmds.length?cmds.map(c=>`<tr><td>${esc(fmtTime(c.requested_at))}</td><td><span class="machine-name">${esc(c.machine_name)}</span></td><td>${esc(c.app_name)}</td><td>${esc(c.action)}</td><td>${commandPill(c.status)}</td><td>${esc(c.result_message||'—')}</td><td>${c.status==='queued'?`<button class="danger-button" data-cancel-command="${esc(c.id)}">Cancel</button>`:''}</td></tr>`).join(''):emptyRow(7)}</tbody></table></div></section>`;
  }

  function renderActivity() {
    const rows = state.activity.filter(a => !searchTerm || `${a.event} ${a.message} ${a.actor||''} ${a.machine_name||''}`.toLowerCase().includes(searchTerm));
    return `<section class="console-panel"><div class="panel-heading"><div><h2>Audit activity</h2><p>Recorded on the server, including agent enrollments, dispatches and results.</p></div><button class="subtle-button" data-action="refresh">Refresh</button></div>${activityMarkup(rows)}</section>`;
  }

  function metric(name,value,note,pct){return `<article class="metric-card"><span>${esc(name)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small><div class="metric-accent"><i style="width:${Math.max(0,Math.min(100,Number(pct)||0))}%"></i></div></article>`}
  function statusPill(online){return `<span class="status-pill ${online?'online':'offline'}">${online?'Online':'Offline'}</span>`}
  function policyPill(policy){const p=String(policy||'manual').toLowerCase();return `<span class="policy-pill ${esc(p)}">${esc(p.charAt(0).toUpperCase()+p.slice(1))}</span>`}
  function commandPill(s){return `<span class="command-status ${esc(s)}">${esc(s)}</span>`}
  function emptyRow(cols){return `<tr><td colspan="${cols}"><div class="empty-state"><strong>No matching data.</strong><p>Try a different search or wait for an agent check-in.</p></div></td></tr>`}
  function activityMarkup(rows){return `<div class="activity-list">${rows.length?rows.map(a=>`<div class="activity-row"><i class="event-dot ${a.kind==='success'?'success':a.kind==='error'?'warning':a.kind==='warning'?'warning':'queued'}"></i><span><b>${esc(a.message)}</b><small>${esc(a.event)}${a.machine_name?' · '+esc(a.machine_name):''}${a.actor?' · '+esc(a.actor):''}</small></span><time>${esc(relative(a.created_at))}</time></div>`).join(''):'<div class="empty-state"><strong>No activity yet.</strong><p>Server events will appear here.</p></div>'}</div>`}

  function renderAppCell(machine, app) {
    const install = installationFor(machine, app.slug);
    const key = `${machine.id}|${app.slug}`;
    let cls='missing', text='Not installed';
    if (install) {
      if (install.version === app.latest_version) { cls='current'; text=install.version || 'Installed'; }
      else { cls='outdated'; text=`${install.version||'Installed'} ↑`; }
    }
    return `<td class="app-cell ${selectedCells.has(key)?'selected':''}" data-app-cell="${esc(key)}"><span class="app-pill ${cls}">${esc(text)}</span></td>`;
  }

  function targetList(action) {
    const map = new Map();
    for (const key of selectedCells) {
      const [machine_id, app_slug] = key.split('|');
      map.set(key,{machine_id,app_slug});
    }
    for (const machine_id of selectedMachines) {
      for (const app of state.apps) map.set(`${machine_id}|${app.slug}`,{machine_id,app_slug:app.slug});
    }
    if (action === 'update') {
      return [...map.values()].filter(t => {
        const m=state.machines.find(x=>x.id===t.machine_id); const a=state.apps.find(x=>x.slug===t.app_slug); const i=m&&installationFor(m,a?.slug);
        return i && i.version !== a.latest_version;
      });
    }
    if (action === 'install') {
      return [...map.values()].filter(t => { const m=state.machines.find(x=>x.id===t.machine_id); return m && !installationFor(m,t.app_slug); });
    }
    if (action === 'uninstall') {
      return [...map.values()].filter(t => { const m=state.machines.find(x=>x.id===t.machine_id); return m && installationFor(m,t.app_slug); });
    }
    return [...map.values()];
  }

  function confirmAction({title,text,icon='↻',ok='Continue'}, callback) {
    modalTitle.textContent=title; modalText.textContent=text; modalIcon.textContent=icon; modalOk.textContent=ok;
    pendingConfirm=callback; modal.hidden=false;
  }
  function closeModal(){modal.hidden=true;pendingConfirm=null}

  async function queueAction(action, targets) {
    if (!targets.length) return toast(`Nothing eligible to ${action}. Select matching app cells or machines.`);
    try {
      const result = await api('/api/commands/', {method:'POST',body:JSON.stringify({action,targets})});
      selectedCells.clear(); selectedMachines.clear();
      const parts=[`${result.created} command(s) queued`];
      if(result.blocked?.length)parts.push(`${result.blocked.length} locked`);
      if(result.invalid?.length)parts.push(`${result.invalid.length} invalid`);
      toast(parts.join(' · '));
      await refresh(true);
    } catch (err) { toast(err.message); }
  }

  function updateAll() {
    const targets=[];
    for(const m of state.machines) for(const app of state.apps){
      const inst=installationFor(m,app.slug);
      if(inst && inst.version!==app.latest_version) targets.push({machine_id:m.id,app_slug:app.slug});
    }
    confirmAction({title:'Queue all approved updates?',text:`This will create up to ${targets.length} update command(s). Locked machines will remain protected.`,icon:'↑',ok:'Queue updates'},()=>queueAction('update',targets));
  }

  async function applyPolicy(policy) {
    if(!selectedMachines.size) return toast('Select one or more machines in Apps or Machines first.');
    const ids=[...selectedMachines];
    confirmAction({title:`Apply ${policy} policy?`,text:`This changes policy for ${ids.length} selected machine(s).`,icon:'◌',ok:'Apply policy'}, async()=>{
      try{const r=await api('/api/policies/assign/',{method:'POST',body:JSON.stringify({machine_ids:ids,policy})});toast(`${r.updated} machine(s) updated`);selectedMachines.clear();await refresh(true)}catch(e){toast(e.message)}
    });
  }

  async function cancelCommand(id){
    try{await api(`/api/commands/${encodeURIComponent(id)}/cancel/`,{method:'POST',body:'{}'});toast('Command cancelled');await refresh(true)}catch(e){toast(e.message)}
  }

  async function reviewSoftwareRequest(id, decision){
    const verb=decision==='approve'?'Approve':'Reject';
    confirmAction({title:`${verb} software request?`,text:decision==='approve'?'If the app is missing or outdated, VarunOps will queue the appropriate allow-listed agent command.':'The employee will be notified that IT declined this request.',icon:decision==='approve'?'✓':'×',ok:verb},async()=>{
      try{await api(`/api/software-requests/${encodeURIComponent(id)}/action/`,{method:'POST',body:JSON.stringify({decision})});toast(`Request ${decision==='approve'?'approved':'rejected'}`);await refresh(true)}catch(e){toast(e.message)}
    });
  }

  async function ticketAction(id, action){
    try{await api(`/api/tickets/${encodeURIComponent(id)}/action/`,{method:'POST',body:JSON.stringify({action})});toast('Ticket updated');await refresh(true)}catch(e){toast(e.message)}
  }

  async function replyTicket(id){
    const field=qs(`#reply-${CSS.escape(id)}`); const body=field?.value.trim()||'';
    if(!body)return toast('Write a reply first.');
    try{await api(`/api/tickets/${encodeURIComponent(id)}/messages/`,{method:'POST',body:JSON.stringify({body})});toast('Reply sent');await refresh(true)}catch(e){toast(e.message)}
  }

  async function applyCompliance(mode){if(!selectedMachines.size)return toast('Select machines first.');try{const r=await api('/api/compliance/mode/',{method:'POST',body:JSON.stringify({machine_ids:[...selectedMachines],mode})});toast(`${r.updated} PC(s) set to ${mode}`);await refresh(true)}catch(e){toast(e.message)}}
  async function unauthorizedAction(id,action){const verb=action==='allow'?'allow this exception':'queue removal';confirmAction({title:`${verb}?`,text:action==='allow'?'This exact detected software name will be allowed only on this PC.':'VarunOps will ask Winget to uninstall the exact currently-detected program. No arbitrary command text is executed.',icon:action==='allow'?'✓':'−',ok:action==='allow'?'Allow':'Uninstall'},async()=>{try{await api(`/api/compliance/unauthorized/${encodeURIComponent(id)}/action/`,{method:'POST',body:JSON.stringify({action})});toast('Compliance action saved');await refresh(true)}catch(e){toast(e.message)}})}
  async function applyAppPolicy(slug){if(!selectedMachines.size)return toast('Select machines first.');const mode=qs(`[data-app-policy-mode="${CSS.escape(slug)}"]`)?.value||'optional';const auto=!!qs(`[data-app-auto-update="${CSS.escape(slug)}"]`)?.checked;try{const r=await api('/api/app-policies/assign/',{method:'POST',body:JSON.stringify({machine_ids:[...selectedMachines],app_slug:slug,mode,auto_update:auto})});toast(`${r.updated} PC app policy updated`);await refresh(true)}catch(e){toast(e.message)}}
  async function saveCatalog(form){const fd=new FormData(form);const data=Object.fromEntries(fd.entries());data.employee_visible=fd.has('employee_visible');data.license_required=fd.has('license_required');data.enabled=true;data.detection_names=String(data.detection_names||'').split(',').map(x=>x.trim()).filter(Boolean);try{await api('/api/catalog/save/',{method:'POST',body:JSON.stringify(data)});toast('Software store item saved');form.reset();await refresh(true)}catch(e){toast(e.message)}}
  async function saveNetworkPolicy(form){const fd=new FormData(form);const data=Object.fromEntries(fd.entries());data.allowed_sites=String(data.allowed_sites||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);data.blocked_sites=String(data.blocked_sites||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);data.enforce_edge=fd.has('enforce_edge');data.enforce_chrome=fd.has('enforce_chrome');data.enabled=true;try{await api('/api/network-policies/save/',{method:'POST',body:JSON.stringify(data)});toast('Network policy saved');form.reset();await refresh(true)}catch(e){toast(e.message)}}
  async function assignNetwork(){if(!selectedMachines.size)return toast('Select machines first.');const value=qs('#networkAssignSelect')?.value||null;try{const r=await api('/api/network-policies/assign/',{method:'POST',body:JSON.stringify({machine_ids:[...selectedMachines],policy_id:value||null})});toast(`${r.updated} PC(s) updated`);await refresh(true)}catch(e){toast(e.message)}}

  function bindDynamic() {
    qs('#catalogForm')?.addEventListener('submit',e=>{e.preventDefault();saveCatalog(e.currentTarget)});
    qs('#networkPolicyForm')?.addEventListener('submit',e=>{e.preventDefault();saveNetworkPolicy(e.currentTarget)});
    qs('[data-assign-network]')?.addEventListener('click',assignNetwork);
    qsa('[data-apply-app-policy]').forEach(b=>b.addEventListener('click',()=>applyAppPolicy(b.dataset.applyAppPolicy)));
    qsa('[data-compliance]').forEach(b=>b.addEventListener('click',()=>applyCompliance(b.dataset.compliance)));
    qsa('[data-unauthorized-action]').forEach(b=>b.addEventListener('click',()=>unauthorizedAction(b.dataset.alertId,b.dataset.unauthorizedAction)));
    qsa('[data-select-one]').forEach(b=>b.addEventListener('click',()=>{selectedMachines.clear();selectedMachines.add(b.dataset.selectOne);toast('PC selected')}));
    qsa('[data-software-decision]').forEach(b=>b.addEventListener('click',()=>reviewSoftwareRequest(b.dataset.requestId,b.dataset.softwareDecision)));
    qsa('[data-ticket-action]').forEach(b=>b.addEventListener('click',()=>ticketAction(b.dataset.ticketId,b.dataset.ticketAction)));
    qsa('[data-ticket-reply]').forEach(b=>b.addEventListener('click',()=>replyTicket(b.dataset.ticketReply)));
    qsa('[data-machine-select]').forEach(el=>el.addEventListener('change',()=>{el.checked?selectedMachines.add(el.dataset.machineSelect):selectedMachines.delete(el.dataset.machineSelect);render()}));
    qsa('[data-app-cell]').forEach(el=>el.addEventListener('click',()=>{const k=el.dataset.appCell;selectedCells.has(k)?selectedCells.delete(k):selectedCells.add(k);render()}));
    qs('#selectAllMachines')?.addEventListener('change',e=>{visibleMachines().forEach(m=>e.target.checked?selectedMachines.add(m.id):selectedMachines.delete(m.id));render()});
    qsa('[data-view-jump]').forEach(b=>b.addEventListener('click',()=>{currentView=b.dataset.viewJump;render()}));
    qsa('[data-policy]').forEach(c=>c.addEventListener('click',()=>applyPolicy(c.dataset.policy)));
    qsa('[data-cancel-command]').forEach(b=>b.addEventListener('click',()=>confirmAction({title:'Cancel queued command?',text:'Only commands that have not been picked up by an agent can be cancelled.',icon:'×',ok:'Cancel command'},()=>cancelCommand(b.dataset.cancelCommand))));
    qsa('[data-action]').forEach(b=>b.addEventListener('click',()=>{
      const action=b.dataset.action;
      if(action==='refresh') return refresh(true);
      if(action==='clear-selection'){selectedCells.clear();selectedMachines.clear();toast('Selection cleared');return render()}
      if(action==='update-all') return updateAll();
      if(['install','update','uninstall'].includes(action)){
        const targets=targetList(action);
        const labels={install:['Install selected apps?','Install'],update:['Queue selected updates?','Update'],uninstall:['Uninstall selected apps?','Uninstall']};
        const [t,ok]=labels[action];
        confirmAction({title:t,text:`${targets.length} eligible app target(s) will be queued. Offline devices will receive them when they check in.`,icon:action==='uninstall'?'−':'↑',ok},()=>queueAction(action,targets));
      }
    }));
  }

  qsa('.console-nav-item').forEach(b=>b.addEventListener('click',()=>{currentView=b.dataset.view;render()}));
  search.addEventListener('input',()=>{searchTerm=search.value.trim().toLowerCase();render()});
  qs('#refreshData').addEventListener('click',()=>refresh(true));
  modalCancel.addEventListener('click',closeModal);
  modal.addEventListener('click',e=>{if(e.target===modal)closeModal()});
  modalOk.addEventListener('click',async()=>{const fn=pendingConfirm;closeModal();if(fn)await fn()});
  window.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden)closeModal()});

  const initialHash = location.hash.replace('#','');
  if (['overview','apps','catalog','compliance','network','employees','machines','policies','requests','tickets','commands','activity'].includes(initialHash)) currentView = initialHash;
  refresh();
  setInterval(()=>refresh(true),15000);
})();
