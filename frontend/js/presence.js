import { api } from './api.js';

let heartbeatTimer = null;
let inFlight = false;

export async function sendPresenceHeartbeat() {
  if (inFlight) return;
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
  inFlight = true;
  try {
    await api('POST', '/me/presence', {}, { redirectOn401: false });
  } catch {
    // Фоновый пульс тихо пропускает сетевые ошибки
  } finally {
    inFlight = false;
  }
}

function onVisibilityOrFocus() {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
    sendPresenceHeartbeat();
  }
}

export function startPresenceHeartbeat() {
  if (heartbeatTimer !== null) return;
  sendPresenceHeartbeat();
  heartbeatTimer = setInterval(sendPresenceHeartbeat, 25000);

  if (typeof window !== 'undefined') {
    window.addEventListener('focus', onVisibilityOrFocus);
    window.addEventListener('pagehide', stopPresenceHeartbeat);
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityOrFocus);
  }
}

export function stopPresenceHeartbeat() {
  if (heartbeatTimer !== null) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('focus', onVisibilityOrFocus);
    window.removeEventListener('pagehide', stopPresenceHeartbeat);
  }
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibilityOrFocus);
  }
}
