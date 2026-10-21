export class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}

export async function api(method, path, body) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api/v1' + path, opts);
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* пустое тело */ }
  if (!res.ok) {
    const err = (data && data.error) || { code: 'NETWORK', message: 'Ошибка сети' };
    if (res.status === 401 && err.code === 'UNAUTHENTICATED') redirectToLogin();
    throw new ApiError(res.status, err.code, err.message);
  }
  return data;
}

export function redirectToLogin() {
  const next = location.pathname + location.search;
  location.href = '/login.html?next=' + encodeURIComponent(next);
}

export function safeNext(defaultPath = '/index.html') {
  const n = new URLSearchParams(location.search).get('next');
  return n && n.startsWith('/') && !n.startsWith('//') && !n.includes('\\') ? n : defaultPath;
}

export function text(el, value) { el.textContent = value == null ? '' : String(value); }
