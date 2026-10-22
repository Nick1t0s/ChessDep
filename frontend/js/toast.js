const LIMIT = 4;
const TTL = 3500;
const EXIT_MS = 300;

let box = null;

function stack() {
  if (box === null) {
    box = document.createElement('div');
    box.className = 'toasts';
    document.body.appendChild(box);
  }
  return box;
}

export function toast(message, kind = 'info') {
  const el = document.createElement('div');
  el.className = 'toast ' + (kind === 'success' || kind === 'error' ? kind : 'info');
  el.setAttribute('role', 'status');

  const body = document.createElement('span');
  body.className = 't-body';
  body.textContent = message;
  const close = document.createElement('button');
  close.className = 't-x';
  close.type = 'button';
  close.title = 'Закрыть';
  close.textContent = '✕';
  close.addEventListener('click', () => dismiss(el));

  el.appendChild(body);
  el.appendChild(close);
  const pane = stack();
  // Считаем только живые тосты: исчезающий (.out) удаляется через EXIT_MS,
  // и повторный dismiss по нему ничего не меняет — иначе цикл вечный.
  const live = [...pane.children].filter((c) => !c.classList.contains('out'));
  while (live.length >= LIMIT) dismiss(live.shift());
  pane.appendChild(el);
  const timer = setTimeout(() => dismiss(el), TTL);
  return el;
}

function dismiss(el) {
  if (!el || el.classList.contains('out')) return;
  el.classList.add('out');
  setTimeout(() => el.remove(), EXIT_MS);
}
