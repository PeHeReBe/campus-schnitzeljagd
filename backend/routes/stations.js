const express = require('express');
const { getDb } = require('../db');

const router = express.Router();

// List all stations (public: no codes)
router.get('/', (req, res) => {
  const db = getDb();
  const stations = db.prepare(
    'SELECT id, name, description, lat, lng, points, sort_order FROM stations ORDER BY sort_order'
  ).all();
  res.json(stations);
});

// Get single station
router.get('/:id', (req, res) => {
  const db = getDb();
  const station = db.prepare(
    'SELECT id, name, description, lat, lng, points, sort_order FROM stations WHERE id = ?'
  ).get(Number(req.params.id));
  if (!station) return res.status(404).json({ error: 'Station nicht gefunden' });
  res.json(station);
});

module.exports = router;
