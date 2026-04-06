const { describe, it, before, after, beforeEach } = require('node:test');
const assert = require('node:assert');
const http = require('http');
const { app, server } = require('../server');

const BASE = 'http://127.0.0.1:0';
let baseUrl;
let httpServer;

function req(path, opts = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, baseUrl);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      method: opts.method || 'GET',
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) }
    };
    const r = http.request(options, (res) => {
      let body = '';
      res.on('data', (c) => body += c);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(body), headers: res.headers });
        } catch {
          resolve({ status: res.statusCode, data: body, headers: res.headers });
        }
      });
    });
    r.on('error', reject);
    if (opts.body) r.write(JSON.stringify(opts.body));
    r.end();
  });
}

function adminHeaders() {
  return { Authorization: 'Basic ' + Buffer.from('admin:campus2026').toString('base64') };
}

before(async () => {
  await new Promise((resolve) => {
    httpServer = app.listen(0, '127.0.0.1', () => {
      const addr = httpServer.address();
      baseUrl = `http://127.0.0.1:${addr.port}`;
      resolve();
    });
  });
});

after(async () => {
  httpServer.close();
  const { closeDb } = require('../backend/db');
  closeDb();
});

describe('Health Check', () => {
  it('GET /api/health returns ok', async () => {
    const res = await req('/api/health');
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.data.status, 'ok');
  });
});

describe('Admin Stations', () => {
  let stationId;

  it('creates a station', async () => {
    const res = await req('/api/admin/stations', {
      method: 'POST',
      headers: adminHeaders(),
      body: { name: 'Bibliothek', description: 'Alte Bibliothek', points: 15 }
    });
    assert.strictEqual(res.status, 201);
    assert.ok(res.data.id);
    assert.ok(res.data.code);
    stationId = res.data.id;
  });

  it('lists stations', async () => {
    const res = await req('/api/admin/stations', { headers: adminHeaders() });
    assert.strictEqual(res.status, 200);
    assert.ok(Array.isArray(res.data));
    assert.ok(res.data.length >= 1);
  });

  it('rejects unauthenticated requests', async () => {
    const res = await req('/api/admin/stations');
    assert.strictEqual(res.status, 401);
  });

  it('public station list hides codes', async () => {
    const res = await req('/api/stations');
    assert.strictEqual(res.status, 200);
    assert.ok(res.data.length >= 1);
    assert.strictEqual(res.data[0].code, undefined);
  });
});

describe('Teams', () => {
  it('registers a team', async () => {
    const res = await req('/api/teams', {
      method: 'POST',
      body: { name: 'TestTeam', pin: '1234' }
    });
    assert.strictEqual(res.status, 201);
    assert.strictEqual(res.data.name, 'TestTeam');
  });

  it('rejects duplicate team name', async () => {
    const res = await req('/api/teams', {
      method: 'POST',
      body: { name: 'TestTeam', pin: '5678' }
    });
    assert.strictEqual(res.status, 409);
  });

  it('rejects short PIN', async () => {
    const res = await req('/api/teams', {
      method: 'POST',
      body: { name: 'ShortPin', pin: '12' }
    });
    assert.strictEqual(res.status, 400);
  });

  it('logs in a team', async () => {
    const res = await req('/api/teams/login', {
      method: 'POST',
      body: { name: 'TestTeam', pin: '1234' }
    });
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.data.name, 'TestTeam');
    assert.ok(Array.isArray(res.data.scans));
  });

  it('rejects wrong credentials', async () => {
    const res = await req('/api/teams/login', {
      method: 'POST',
      body: { name: 'TestTeam', pin: 'wrong' }
    });
    assert.strictEqual(res.status, 401);
  });
});

describe('Scanning', () => {
  let teamId;
  let stationCode;

  before(async () => {
    // Get team
    const loginRes = await req('/api/teams/login', {
      method: 'POST',
      body: { name: 'TestTeam', pin: '1234' }
    });
    teamId = loginRes.data.id;

    // Get station code from admin
    const stationsRes = await req('/api/admin/stations', { headers: adminHeaders() });
    stationCode = stationsRes.data[0].code;
  });

  it('scans a station', async () => {
    const res = await req(`/api/teams/${teamId}/scan`, {
      method: 'POST',
      body: { code: stationCode, pin: '1234' }
    });
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.data.success, true);
    assert.ok(res.data.points);
  });

  it('rejects duplicate scan', async () => {
    const res = await req(`/api/teams/${teamId}/scan`, {
      method: 'POST',
      body: { code: stationCode, pin: '1234' }
    });
    assert.strictEqual(res.status, 409);
  });

  it('rejects invalid code', async () => {
    const res = await req(`/api/teams/${teamId}/scan`, {
      method: 'POST',
      body: { code: 'doesnotexist', pin: '1234' }
    });
    assert.strictEqual(res.status, 404);
  });
});

describe('Leaderboard', () => {
  it('returns teams with scores', async () => {
    const res = await req('/api/teams');
    assert.strictEqual(res.status, 200);
    assert.ok(res.data.length >= 1);
    const team = res.data.find(t => t.name === 'TestTeam');
    assert.ok(team);
    assert.ok(team.score > 0);
  });
});

describe('Admin Stats', () => {
  it('returns stats', async () => {
    const res = await req('/api/admin/stats', { headers: adminHeaders() });
    assert.strictEqual(res.status, 200);
    assert.ok(res.data.teamCount >= 1);
    assert.ok(res.data.stationCount >= 1);
    assert.ok(res.data.scanCount >= 1);
  });
});

describe('QR Code', () => {
  it('generates QR PNG', async () => {
    const stationsRes = await req('/api/admin/stations', { headers: adminHeaders() });
    const id = stationsRes.data[0].id;
    const url = new URL(`/api/admin/stations/${id}/qr`, baseUrl);
    const res = await new Promise((resolve, reject) => {
      http.get({ hostname: '127.0.0.1', port: new URL(baseUrl).port, path: url.pathname, headers: adminHeaders() }, (r) => {
        const chunks = [];
        r.on('data', c => chunks.push(c));
        r.on('end', () => resolve({ status: r.statusCode, headers: r.headers, body: Buffer.concat(chunks) }));
      }).on('error', reject);
    });
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.headers['content-type'], 'image/png');
    assert.ok(res.body.length > 100);
  });
});
