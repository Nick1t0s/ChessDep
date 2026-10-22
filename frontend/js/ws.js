import { api } from './api.js';

const RECONNECT_DELAYS = [1000, 2000, 5000, 10000];
const PING_INTERVAL = 25000;

export function connectGame(gameId, { onMessage, onStatus }) {
  let socket = null;
  let closed = false;
  let pingTimer = null;
  let attempt = 0;

  function postStatus(status) {
    try {
      onStatus(status);
    } catch (e) {
      console.error(e);
    }
  }

  function stopPing() {
    if (pingTimer !== null) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  }

  let verifyTimer = null;

  async function connect() {
    if (closed) return;
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    let ws;
    try {
      ws = new WebSocket(protocol + '://' + location.host + '/ws/games/' + gameId);
    } catch (e) {
      console.error(e);
      verify();
      return;
    }
    socket = ws;
    ws.onopen = () => {
      if (closed) return;
      attempt = 0;
      postStatus('online');
      pingTimer = setInterval(() => {
        try {
          ws.send(JSON.stringify({ type: 'ping' }));
        } catch {
          /* соединение закрывается */
        }
      }, PING_INTERVAL);
    };
    ws.onmessage = (event) => {
      let data = null;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data !== null && typeof data === 'object') {
        try {
          onMessage(data);
        } catch (e) {
          console.error(e);
        }
      }
    };
    ws.onclose = () => {
      socket = null;
      stopPing();
      if (closed) return;
      verify();
    };
    ws.onerror = () => {
      console.error('ws error');
    };
  }

  async function verify() {
    if (closed) return;
    let ok = false;
    try {
      // Ответ 200, состояния нет — сервер сам пришлёт state по WS.
      await api('GET', '/games/' + gameId, undefined, { redirectOn401: false });
      ok = true;
    } catch (e) {
      if (e && (e.status === 401 || e.status === 403 || e.status === 404)) {
        postStatus('forbidden');
        return;
      }
      // Ошибка сети при проверке — тоже переподключение.
    }
    if (closed) return;
    if (verifyTimer !== null) {
      clearTimeout(verifyTimer);
      verifyTimer = null;
    }
    const delay = RECONNECT_DELAYS[Math.min(attempt, RECONNECT_DELAYS.length - 1)];
    attempt += 1;
    postStatus('reconnecting');
    verifyTimer = setTimeout(() => {
      verifyTimer = null;
      connect();
    }, delay);
  }

  connect();

  return {
    close() {
      closed = true;
      stopPing();
      if (verifyTimer !== null) {
        clearTimeout(verifyTimer);
        verifyTimer = null;
      }
      if (socket !== null) {
        const ws = socket;
        socket = null;
        try {
          ws.close();
        } catch {
          /* уже закрыт */
        }
      }
    },
  };
}
