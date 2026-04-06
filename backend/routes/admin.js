const express = require('express');
const crypto = require('crypto');
const QRCode = require('qrcode');
const { getDb } = require('../db');

const router = express.Router();

// Default admin credentials (should be changed on first use)
const ADMIN_USER = process.env.ADMIN_USER || 'admin';
const ADMIN_PASS = process.env.ADMIN_PASS || 'campus2026';

// Simple auth middleware
function requireAdmin(req, res, next) {
  const auth = req.headers.authorization;
  if (!auth || !auth.startsWith('Basic ')) {
    res.set('WWW-Authenticate', 'Basic realm="Admin"');
    return res.status(401).json({ error: 'Authentifizierung erforderlich' });
  }
  const decoded = Buffer.from(auth.slice(6), 'base64').toString();
  const [user, pass] = decoded.split(':');
  if (user !== ADMIN_USER || pass !== ADMIN_PASS) {
    return res.status(403).json({ error: 'Zugriff verweigert' });
  }
  next();
}

router.use(requireAdmin);

// ---- Stations CRUD ----

// List all stations (admin: includes codes)
router.get('/stations', (req, res) => {
  const db = getDb();
  const stations = db.prepare('SELECT * FROM stations ORDER BY sort_order').all();
  res.json(stations);
});

// Create station
router.post('/stations', (req, res) => {
  const { name, description, lat, lng, points, sort_order } = req.body;
  if (!name || typeof name !== 'string') {
    return res.status(400).json({ error: 'Stationsname benötigt' });
  }
  const code = crypto.randomBytes(8).toString('hex');
  const db = getDb();
  const result = db.prepare(
    'INSERT INTO stations (name, description, lat, lng, code, points, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).run(name.trim(), description || '', lat || null, lng || null, code, points || 10, sort_order || 0);
  res.status(201).json({ id: result.lastInsertRowid, name: name.trim(), code });
});

// Update station
router.put('/stations/:id', (req, res) => {
  const { name, description, lat, lng, points, sort_order } = req.body;
  const db = getDb();
  const existing = db.prepare('SELECT * FROM stations WHERE id = ?').get(Number(req.params.id));
  if (!existing) return res.status(404).json({ error: 'Station nicht gefunden' });
  db.prepare(
    'UPDATE stations SET name=?, description=?, lat=?, lng=?, points=?, sort_order=? WHERE id=?'
  ).run(
    name || existing.name,
    description ?? existing.description,
    lat ?? existing.lat,
    lng ?? existing.lng,
    points ?? existing.points,
    sort_order ?? existing.sort_order,
    Number(req.params.id)
  );
  res.json({ success: true });
});

// Delete station
router.delete('/stations/:id', (req, res) => {
  const db = getDb();
  db.prepare('DELETE FROM scans WHERE station_id = ?').run(Number(req.params.id));
  const result = db.prepare('DELETE FROM stations WHERE id = ?').run(Number(req.params.id));
  if (result.changes === 0) return res.status(404).json({ error: 'Station nicht gefunden' });
  res.json({ success: true });
});

// Generate QR code for station
router.get('/stations/:id/qr', async (req, res) => {
  const db = getDb();
  const station = db.prepare('SELECT * FROM stations WHERE id = ?').get(Number(req.params.id));
  if (!station) return res.status(404).json({ error: 'Station nicht gefunden' });

  const baseUrl = `${req.protocol}://${req.get('host')}`;
  const scanUrl = `${baseUrl}/scan.html?code=${station.code}`;

  const format = req.query.format || 'png';
  if (format === 'svg') {
    const svg = await QRCode.toString(scanUrl, { type: 'svg' });
    res.set('Content-Type', 'image/svg+xml');
    return res.send(svg);
  }
  const png = await QRCode.toBuffer(scanUrl, { width: 400, margin: 2 });
  res.set('Content-Type', 'image/png');
  res.send(png);
});

// ---- Teams Management ----

router.get('/teams', (req, res) => {
  const db = getDb();
  const teams = db.prepare(`
    SELECT t.id, t.name, t.created_at,
      COALESCE(SUM(s2.points), 0) AS score,
      COUNT(sc.id) AS stations_found
    FROM teams t
    LEFT JOIN scans sc ON sc.team_id = t.id
    LEFT JOIN stations s2 ON s2.id = sc.station_id
    GROUP BY t.id
    ORDER BY score DESC
  `).all();
  res.json(teams);
});

router.delete('/teams/:id', (req, res) => {
  const db = getDb();
  db.prepare('DELETE FROM scans WHERE team_id = ?').run(Number(req.params.id));
  const result = db.prepare('DELETE FROM teams WHERE id = ?').run(Number(req.params.id));
  if (result.changes === 0) return res.status(404).json({ error: 'Team nicht gefunden' });
  res.json({ success: true });
});

// ---- Leaderboard / Stats ----

router.get('/stats', (req, res) => {
  const db = getDb();
  const teamCount = db.prepare('SELECT COUNT(*) AS count FROM teams').get().count;
  const stationCount = db.prepare('SELECT COUNT(*) AS count FROM stations').get().count;
  const scanCount = db.prepare('SELECT COUNT(*) AS count FROM scans').get().count;
  res.json({ teamCount, stationCount, scanCount });
});

// Reset all data
router.post('/reset', (req, res) => {
  const db = getDb();
  db.exec('DELETE FROM scans; DELETE FROM teams;');
  const broadcast = req.app.get('broadcast');
  if (broadcast) broadcast({ type: 'reset' });
  res.json({ success: true });
});

module.exports = router;
