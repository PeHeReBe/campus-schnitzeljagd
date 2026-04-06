// ---- Admin Panel JS ----
let AUTH = '';

// Login gate
document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const user = document.getElementById('login-user').value;
  const pass = document.getElementById('login-pass').value;
  const testAuth = 'Basic ' + btoa(user + ':' + pass);
  try {
    const res = await fetch('/api/admin/stats', { headers: { 'Authorization': testAuth } });
    if (!res.ok) throw new Error();
    AUTH = testAuth;
    document.getElementById('admin-login').classList.add('hidden');
    document.getElementById('admin-app').classList.remove('hidden');
    document.getElementById('login-error').textContent = '';
    loadAdminStations();
  } catch {
    document.getElementById('login-error').textContent = 'Ungültige Zugangsdaten';
  }
});

document.getElementById('btn-logout').addEventListener('click', () => {
  AUTH = '';
  document.getElementById('admin-app').classList.add('hidden');
  document.getElementById('admin-login').classList.remove('hidden');
  document.getElementById('login-user').value = '';
  document.getElementById('login-pass').value = '';
});

// Navigation
document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    const view = document.getElementById('view-' + btn.dataset.view);
    if (view) view.classList.add('active');
    btn.classList.add('active');
    if (btn.dataset.view === 'admin-stations') loadAdminStations();
    if (btn.dataset.view === 'admin-teams') loadAdminTeams();
    if (btn.dataset.view === 'admin-pending') loadPending();
    if (btn.dataset.view === 'admin-scans') loadAllScans();
    if (btn.dataset.view === 'admin-log') loadAdminLog();
    if (btn.dataset.view === 'admin-stats') loadStats();
  });
});

async function adminApi(url, opts = {}) {
  opts.headers = {
    'Content-Type': 'application/json',
    'Authorization': AUTH,
    ...(opts.headers || {})
  };
  if (opts.body && typeof opts.body === 'object') opts.body = JSON.stringify(opts.body);
  const res = await fetch(url, opts);
  if (url.includes('/qr') && res.ok) return res;
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.error || 'Fehler');
  return data;
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

const QTYPE_LABELS = {
  qr_only: 'Nur QR',
  multiple_choice: 'Multiple Choice',
  text_answer: 'Text-Antwort',
  photo_upload: 'Foto-Upload'
};

// ---- Question type form toggle ----
document.getElementById('st-qtype').addEventListener('change', (e) => {
  const qtype = e.target.value;
  const qFields = document.getElementById('q-fields');
  const mcFields = document.getElementById('mc-fields');
  if (qtype === 'qr_only') {
    qFields.classList.add('hidden');
  } else {
    qFields.classList.remove('hidden');
    if (qtype === 'multiple_choice') {
      mcFields.classList.remove('hidden');
    } else {
      mcFields.classList.add('hidden');
    }
  }
});

// ---- Stations ----
document.getElementById('create-station-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const qtype = document.getElementById('st-qtype').value;
    const body = {
      name: document.getElementById('st-name').value,
      description: document.getElementById('st-desc').value,
      points: Number(document.getElementById('st-points').value),
      sort_order: Number(document.getElementById('st-order').value),
      question_type: qtype,
      question_text: document.getElementById('st-qtext').value || ''
    };
    if (qtype === 'multiple_choice') {
      const choicesText = document.getElementById('st-choices').value.trim();
      body.choices = choicesText.split('\n').map(c => c.trim()).filter(c => c);
      body.correct_answer = document.getElementById('st-correct').value.trim();
    }
    await adminApi('/api/admin/stations', { method: 'POST', body });
    document.getElementById('create-station-form').reset();
    document.getElementById('st-points').value = '10';
    document.getElementById('q-fields').classList.add('hidden');
    document.getElementById('mc-fields').classList.add('hidden');
    loadAdminStations();
  } catch (err) {
    alert(err.message);
  }
});

async function loadAdminStations() {
  const stations = await adminApi('/api/admin/stations');
  const el = document.getElementById('admin-stations-list');
  if (!stations.length) {
    el.innerHTML = '<p>Keine Stationen vorhanden.</p>';
    return;
  }
  el.innerHTML = stations.map(s => {
    const qLabel = QTYPE_LABELS[s.question_type] || 'Nur QR';
    return `
    <div class="station-card">
      <div class="station-admin">
        <div>
          <h3>${esc(s.name)}</h3>
          <p>${esc(s.description || '')} · ${s.points} Punkte · <strong>${qLabel}</strong></p>
          ${s.question_text ? `<p class="q-preview">Frage: ${esc(s.question_text)}</p>` : ''}
          <p style="font-size:0.8rem;opacity:0.6">Code: <code>${s.code}</code></p>
        </div>
        <div class="btns">
          <button onclick="downloadQR(${s.id}, '${esc(s.name)}')">QR ⬇</button>
          <button class="danger" onclick="deleteStation(${s.id})">Löschen</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function downloadQR(id, name) {
  const res = await adminApi(`/api/admin/stations/${id}/qr?format=png`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `station-${name}.png`;
  a.click();
  URL.revokeObjectURL(url);
}

async function deleteStation(id) {
  if (!confirm('Station wirklich löschen?')) return;
  await adminApi(`/api/admin/stations/${id}`, { method: 'DELETE' });
  loadAdminStations();
}

// ---- Teams ----
document.getElementById('create-team-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const name = document.getElementById('tm-name').value;
    await adminApi('/api/admin/teams', { method: 'POST', body: { name } });
    document.getElementById('create-team-form').reset();
    loadAdminTeams();
  } catch (err) {
    alert(err.message);
  }
});

async function loadAdminTeams() {
  const teams = await adminApi('/api/admin/teams');
  const el = document.getElementById('admin-teams-list');
  if (!teams.length) {
    el.innerHTML = '<p>Keine Teams vorhanden.</p>';
    return;
  }
  el.innerHTML = `<table>
    <thead><tr><th>Name</th><th>Stationen</th><th>Punkte</th><th></th></tr></thead>
    <tbody>${teams.map(t => `
      <tr>
        <td>${esc(t.name)}</td>
        <td>${t.stations_found}</td>
        <td>${t.score}</td>
        <td style="display:flex;gap:0.3rem">
          <button onclick="downloadTeamQR(${t.id}, '${esc(t.name)}')" style="padding:0.2rem 0.6rem;font-size:0.8rem" title="Login-QR herunterladen">🔗 QR</button>
          <button class="danger" onclick="deleteTeam(${t.id})" style="padding:0.2rem 0.6rem;font-size:0.8rem">×</button>
        </td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

async function downloadTeamQR(id, name) {
  const res = await adminApi(`/api/admin/teams/${id}/qr?format=png`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `team-login-${name}.png`;
  a.click();
  URL.revokeObjectURL(url);
}

async function deleteTeam(id) {
  if (!confirm('Team wirklich löschen?')) return;
  await adminApi(`/api/admin/teams/${id}`, { method: 'DELETE' });
  loadAdminTeams();
}

document.getElementById('btn-reset').addEventListener('click', async () => {
  if (!confirm('Alle Teams und Scans zurücksetzen?')) return;
  await adminApi('/api/admin/reset', { method: 'POST' });
  loadAdminTeams();
});

// ---- Pending Approvals ----
async function loadPending() {
  const items = await adminApi('/api/admin/pending');
  const el = document.getElementById('pending-list');
  if (!items.length) {
    el.innerHTML = '<p>Keine ausstehenden Bewertungen.</p>';
    return;
  }
  el.innerHTML = items.map(item => {
    const typeLabel = QTYPE_LABELS[item.question_type] || item.question_type;
    let answerHtml = '';
    if (item.photo_path) {
      answerHtml = `<div><img src="/${esc(item.photo_path)}" style="max-width:300px;max-height:200px;border-radius:8px;margin:0.5rem 0;"></div>`;
    } else if (item.answer) {
      answerHtml = `<p><strong>Antwort:</strong> ${esc(item.answer)}</p>`;
    }
    return `
    <div class="card pending-item" style="margin-bottom:1rem;">
      <h3>${esc(item.team_name)} → ${esc(item.station_name)}</h3>
      <p>${typeLabel} · ${item.points} Punkte · ${item.scanned_at}</p>
      ${item.question_text ? `<p><em>Frage: ${esc(item.question_text)}</em></p>` : ''}
      ${answerHtml}
      <div class="btns" style="margin-top:0.5rem;">
        <button style="background:#27ae60;color:white" onclick="approveScan(${item.id}, 'approved')">✅ Genehmigen</button>
        <button class="danger" onclick="approveScan(${item.id}, 'rejected')">❌ Ablehnen</button>
      </div>
    </div>`;
  }).join('');
}

async function approveScan(scanId, status) {
  try {
    await adminApi(`/api/admin/scans/${scanId}/approve`, { method: 'PUT', body: { status } });
    loadPending();
    // Also refresh scans tab if it has been loaded
    if (document.getElementById('view-admin-scans')) loadAllScans();
  } catch (err) {
    alert(err.message);
  }
}

// ---- All Scans ----
let allScansData = [];

async function loadAllScans() {
  allScansData = await adminApi('/api/admin/scans');
  renderScans();
}

function renderScans() {
  const filter = (document.getElementById('scan-filter-team')?.value || '').toLowerCase();
  const items = filter ? allScansData.filter(s => s.team_name.toLowerCase().includes(filter)) : allScansData;
  const el = document.getElementById('admin-scans-list');
  if (!items.length) {
    el.innerHTML = '<p>Keine Antworten vorhanden.</p>';
    return;
  }
  const STATUS_LABELS = { approved: '✅ Genehmigt', pending: '⏳ Ausstehend', rejected: '❌ Abgelehnt' };
  el.innerHTML = items.map(item => {
    const typeLabel = QTYPE_LABELS[item.question_type] || item.question_type;
    const statusLabel = STATUS_LABELS[item.status] || item.status;
    let answerHtml = '';
    if (item.photo_path) {
      answerHtml = `<div><img src="/${esc(item.photo_path)}" style="max-width:250px;max-height:150px;border-radius:8px;margin:0.5rem 0;"></div>`;
    } else if (item.answer) {
      answerHtml = `<p><strong>Antwort:</strong> ${esc(item.answer)}</p>`;
    }
    return `
    <div class="card scan-item" style="margin-bottom:0.75rem;border-left:4px solid ${item.status === 'approved' ? '#27ae60' : item.status === 'pending' ? '#f59e0b' : '#e74c3c'}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem">
        <div>
          <strong>${esc(item.team_name)}</strong> → ${esc(item.station_name)}
          <span style="margin-left:0.5rem;font-size:0.8rem;opacity:0.7">${typeLabel} · ${item.points} Pkt · ${statusLabel}</span>
          <br><small style="opacity:0.5">${item.scanned_at}</small>
          ${item.question_text ? `<br><em style="font-size:0.85rem">${esc(item.question_text)}</em>` : ''}
          ${answerHtml}
        </div>
        <div class="btns">
          <button class="danger" onclick="deleteScan(${item.id})" title="Löschen (Team kann erneut antworten)">🗑 Löschen</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

// Wire up filter input
document.getElementById('scan-filter-team')?.addEventListener('input', renderScans);

async function deleteScan(scanId) {
  if (!confirm('Antwort wirklich löschen? Das Team kann dann erneut antworten/hochladen.')) return;
  try {
    await adminApi(`/api/admin/scans/${scanId}`, { method: 'DELETE' });
    loadAllScans();
  } catch (err) {
    alert(err.message);
  }
}

// ---- Admin Log ----
async function loadAdminLog() {
  const logs = await adminApi('/api/admin/log');
  const el = document.getElementById('admin-log-list');
  if (!logs.length) {
    el.innerHTML = '<p>Noch keine Einträge.</p>';
    return;
  }
  el.innerHTML = `<table style="width:100%;font-size:0.9rem">
    <thead><tr><th>Zeitpunkt</th><th>Admin</th><th>Aktion</th><th>Details</th></tr></thead>
    <tbody>${logs.map(l => `
      <tr>
        <td style="white-space:nowrap">${esc(l.created_at)}</td>
        <td>${esc(l.admin_user)}</td>
        <td><code>${esc(l.action)}</code> ${esc(l.target_type)} #${l.target_id}</td>
        <td>${esc(l.details)}</td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

// ---- Stats ----
async function loadStats() {
  const stats = await adminApi('/api/admin/stats');
  document.getElementById('admin-stats').innerHTML = `
    <div class="stat-box"><div class="num">${stats.teamCount}</div><div class="label">Teams</div></div>
    <div class="stat-box"><div class="num">${stats.stationCount}</div><div class="label">Stationen</div></div>
    <div class="stat-box"><div class="num">${stats.scanCount}</div><div class="label">Scans</div></div>
    <div class="stat-box"><div class="num">${stats.pendingCount}</div><div class="label">Ausstehend</div></div>
  `;
}

// Initial load
loadAdminStations();
