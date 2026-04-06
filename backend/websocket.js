const { WebSocketServer } = require('ws');

function setupWebSocket(server) {
  const wss = new WebSocketServer({ server, path: '/ws' });
  const clients = new Set();

  wss.on('connection', (ws) => {
    clients.add(ws);
    ws.on('close', () => clients.delete(ws));
    ws.on('error', () => clients.delete(ws));
  });

  function broadcast(data) {
    const msg = JSON.stringify(data);
    for (const client of clients) {
      if (client.readyState === 1) {
        client.send(msg);
      }
    }
  }

  return { wss, broadcast };
}

module.exports = { setupWebSocket };
