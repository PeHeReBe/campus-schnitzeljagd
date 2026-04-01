// ---- State ----
let currentTeam = null;

// ---- Credential Storage ----
function saveCredentials(teamId, name, token) {
  localStorage.setItem('hunt_team_id', String(teamId));
  localStorage.setItem('hunt_team', name);
  localStorage.setItem('hunt_token', token);
  // Clean up old pin storage
  localStorage.removeItem('hunt_pin');
}
function clearCredentials() {
  localStorage.removeItem('hunt_team_id');
  localStorage.removeItem('hunt_team');
  localStorage.removeItem('hunt_token');
  localStorage.removeItem('hunt_pin');
}
function getSavedCredentials() {
  const id = localStorage.getItem('hunt_team_id');
  const name = localStorage.getItem('hunt_team');
  const token = localStorage.getItem('hunt_token');
  if (id && name && token) return { id: Number(id), name, token };
  // Fallback: old pin-based
  const pin = localStorage.getItem('hunt_pin');
  if (name && pin) return { name, pin };
  return null;
}

// ---- Navigation ----
document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => showView(btn.dataset.view));
});

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const view = document.getElementById('view-' + name);
  if (view) view.classList.add('active');
  const navBtn = document.querySelector(`.nav-btn[data-view="${name}"]`);
  if (navBtn) navBtn.classList.add('active');

  if (name === 'leaderboard') loadLeaderboard();
  if (name === 'stations') loadStations();
  if (name === 'team') updateTeamView();
}

// ---- Toast ----
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 3000);
}

// ---- API helpers ----
async function api(url, opts = {}) {
  opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (opts.body && typeof opts.body === 'object') opts.body = JSON.stringify(opts.body);
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Fehler');
  return data;
}

// ---- Team Auth ----
document.getElementById('team-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errEl = document.getElementById('team-error');
  errEl.textContent = '';
  const name = document.getElementById('team-name').value;
  const pin = document.getElementById('team-pin').value;
  try {
    const team = await api('/api/teams/login', { method: 'POST', body: { name, pin } });
    currentTeam = { ...team, token: team.login_token };
    if (team.login_token) {
      saveCredentials(team.id, name, team.login_token);
    }
    updateTeamView();
    toast(`Willkommen ${team.name}!`);
  } catch (err) {
    errEl.textContent = err.message;
  }
});

function updateTeamView() {
  if (currentTeam) {
    document.getElementById('team-auth').classList.add('hidden');
    document.getElementById('team-dashboard').classList.remove('hidden');
    document.getElementById('dash-team-name').textContent = currentTeam.name;
    const scans = currentTeam.scans || [];
    const approved = scans.filter(s => s.status === 'approved');
    document.getElementById('dash-found').textContent = approved.length;
    const ul = document.getElementById('dash-scans');
    const statusIcons = { approved: '✅', pending: '⏳', rejected: '❌' };
    ul.innerHTML = scans.map(s => {
      const icon = statusIcons[s.status] || '✅';
      return `<li>${icon} ${esc(s.station_name)} — ${s.points} Punkte${s.status === 'pending' ? ' (wird geprüft)' : s.status === 'rejected' ? ' (abgelehnt)' : ''}</li>`;
    }).join('');
  } else {
    document.getElementById('team-auth').classList.remove('hidden');
    document.getElementById('team-dashboard').classList.add('hidden');
  }
}

function logout() {
  currentTeam = null;
  clearCredentials();
  updateTeamView();
}

// ---- Auto-login from saved credentials ----
(async () => {
  const saved = getSavedCredentials();
  if (!saved) return;
  try {
    let team;
    if (saved.token) {
      team = await api('/api/teams/token-login', { method: 'POST', body: { token: saved.token } });
      currentTeam = { ...team, token: saved.token };
    } else if (saved.pin) {
      team = await api('/api/teams/login', { method: 'POST', body: { name: saved.name, pin: saved.pin } });
      currentTeam = { ...team, token: team.login_token };
      // Upgrade to token-based storage
      if (team.login_token) {
        saveCredentials(team.id, team.name, team.login_token);
      }
    }
    updateTeamView();
  } catch {
    clearCredentials();
  }
})();

// ---- Leaderboard ----
async function loadLeaderboard() {
  try {
    const teams = await api('/api/teams');
    const tbody = document.querySelector('#leaderboard-table tbody');
    tbody.innerHTML = teams.map((t, i) =>
      `<tr><td>${i + 1}</td><td>${esc(t.name)}</td><td>${t.stations_found}</td><td>${t.score}</td></tr>`
    ).join('');
  } catch (err) {
    toast('Fehler beim Laden der Rangliste');
  }
}

// ---- Stations ----
async function loadStations() {
  try {
    const stations = await api('/api/stations');
    const el = document.getElementById('stations-list');
    if (!stations.length) {
      el.innerHTML = '<p>Noch keine Stationen vorhanden.</p>';
      return;
    }
    el.innerHTML = stations.map(s => {
      const badges = {multiple_choice: '🔘 Multiple Choice', text_answer: '✍️ Text-Antwort', photo_upload: '📷 Foto-Upload'};
      const badge = badges[s.question_type] || '';
      return `
      <div class="station-card">
        <h3>${esc(s.name)}</h3>
        <p>${esc(s.description || '')}</p>
        <span class="points">${s.points} Punkte</span>
        ${badge ? `<span class="badge">${badge}</span>` : ''}
      </div>
    `}).join('');
  } catch (err) {
    toast('Fehler beim Laden der Stationen');
  }
}

// ---- WebSocket ----
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'scan') {
        toast(`${data.team} hat ${data.station} gefunden! (+${data.points})`);
        // Refresh leaderboard if visible
        if (document.getElementById('view-leaderboard').classList.contains('active')) {
          loadLeaderboard();
        }
      } else if (data.type === 'reset') {
        toast('Spiel wurde zurückgesetzt!');
        currentTeam = null;
        updateTeamView();
      }
    } catch {}
  };
  ws.onclose = () => setTimeout(connectWS, 3000);
}
connectWS();

// ---- Helpers ----
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
