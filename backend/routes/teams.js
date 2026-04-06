const express = require('express');
const crypto = require('crypto');
const { getDb } = require('../db');

const router = express.Router();

// List all teams with scores
router.get('/', (req, res) => {
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

// Register new team
router.post('/', (req, res) => {
  const { name, pin } = req.body;
  if (!name || !pin || typeof name !== 'string' || typeof pin !== 'string') {
    return res.status(400).json({ error: 'Name und PIN benötigt' });
  }
  if (pin.length < 4) {
    return res.status(400).json({ error: 'PIN muss mindestens 4 Zeichen haben' });
  }
  const db = getDb();
  const pinHash = crypto.createHash('sha256').update(pin).digest('hex');
  try {
    const result = db.prepare('INSERT INTO teams (name, pin) VALUES (?, ?)').run(name.trim(), pinHash);
    res.status(201).json({ id: result.lastInsertRowid, name: name.trim() });
  } catch (err) {
    if (err.message.includes('UNIQUE')) {
      return res.status(409).json({ error: 'Teamname bereits vergeben' });
    }
    throw err;
  }
});

// Team login
router.post('/login', (req, res) => {
  const { name, pin } = req.body;
  if (!name || !pin) {
    return res.status(400).json({ error: 'Name und PIN benötigt' });
  }
  const db = getDb();
  const pinHash = crypto.createHash('sha256').update(pin).digest('hex');
  const team = db.prepare('SELECT id, name FROM teams WHERE name = ? AND pin = ?').get(name, pinHash);
  if (!team) {
    return res.status(401).json({ error: 'Ungültige Anmeldedaten' });
  }
  // Return team info + progress
  const scans = db.prepare(`
    SELECT s.id AS station_id, s.name AS station_name, s.points, sc.scanned_at
    FROM scans sc
    JOIN stations s ON s.id = sc.station_id
    WHERE sc.team_id = ?
    ORDER BY sc.scanned_at
  `).all(team.id);
  res.json({ ...team, scans });
});

// Scan a station QR code
router.post('/:teamId/scan', (req, res) => {
  const { teamId } = req.params;
  const { code, pin } = req.body;
  if (!code || !pin) {
    return res.status(400).json({ error: 'Code und PIN benötigt' });
  }
  const db = getDb();
  // Verify team PIN
  const pinHash = crypto.createHash('sha256').update(pin).digest('hex');
  const team = db.prepare('SELECT id, name FROM teams WHERE id = ? AND pin = ?').get(Number(teamId), pinHash);
  if (!team) {
    return res.status(401).json({ error: 'Ungültige Team-Anmeldedaten' });
  }
  // Find station by code
  const station = db.prepare('SELECT * FROM stations WHERE code = ?').get(code);
  if (!station) {
    return res.status(404).json({ error: 'Station nicht gefunden' });
  }
  // Record scan
  try {
    db.prepare('INSERT INTO scans (team_id, station_id) VALUES (?, ?)').run(team.id, station.id);
    const broadcast = req.app.get('broadcast');
    if (broadcast) {
      broadcast({ type: 'scan', team: team.name, station: station.name, points: station.points });
    }
    res.json({ success: true, station: station.name, points: station.points });
  } catch (err) {
    if (err.message.includes('UNIQUE')) {
      return res.status(409).json({ error: 'Station bereits gescannt' });
    }
    throw err;
  }
});

module.exports = router;
