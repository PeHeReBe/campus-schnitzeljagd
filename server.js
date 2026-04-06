const express = require('express');
const http = require('http');
const path = require('path');
const { getDb, closeDb } = require('./backend/db');
const { setupWebSocket } = require('./backend/websocket');
const teamsRouter = require('./backend/routes/teams');
const stationsRouter = require('./backend/routes/stations');
const adminRouter = require('./backend/routes/admin');

const PORT = process.env.PORT || 8080;

const app = express();
const server = http.createServer(app);

// WebSocket
const { broadcast } = setupWebSocket(server);
app.set('broadcast', broadcast);

// Middleware
app.use(express.json());

// API routes
app.use('/api/teams', teamsRouter);
app.use('/api/stations', stationsRouter);
app.use('/api/admin', adminRouter);

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Static frontend
app.use(express.static(path.join(__dirname, 'frontend', 'dist')));

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'dist', 'index.html'));
});

// Initialize DB on startup
getDb();

// Graceful shutdown
process.on('SIGTERM', () => {
  closeDb();
  server.close();
});

// Export for testing
module.exports = { app, server };

// Start server if run directly
if (require.main === module) {
  server.listen(PORT, () => {
    console.log(`Campus Hunt läuft auf http://localhost:${PORT}`);
    console.log(`Admin: http://localhost:${PORT}/admin.html (admin / campus2026)`);
  });
}
