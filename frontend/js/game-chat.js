import { api } from './api.js';
import { h, clear } from './dom.js';
import { toast } from './toast.js';

const ROLE_RU = { white: 'белые', black: 'чёрные', spectator: 'зритель' };

export function createChat(container, { gameId, canWrite }) {
  const shown = new Set();

  clear(container);

  const list = h('div', { class: 'chat-list' });
  container.appendChild(list);

  let input = null;
  let sendBtn = null;

  if (canWrite) {
    input = h('input', {
      type: 'text',
      maxlength: '300',
      placeholder: 'Сообщение…',
      autocomplete: 'off',
    });
    sendBtn = h('button', { type: 'submit', class: 'btn btn-gold btn-sm' }, 'Отправить');
    const form = h('form', { class: 'chat-form', onSubmit: onSubmit }, input, sendBtn);
    container.appendChild(form);
  }

  async function load() {
    try {
      const data = await api('GET', '/games/' + gameId + '/chat?limit=50');
      for (const m of data && Array.isArray(data.items) ? data.items : []) {
        showMessage(m);
      }
      scrollBottom();
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  function onWsChat(message) {
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
    if (!showMessage(message)) return;
    if (atBottom) scrollBottom();
  }

  async function onSubmit(e) {
    e.preventDefault();
    const body = input.value.trim();
    if (!body) return;
    sendBtn.disabled = true;
    try {
      const msg = await api('POST', '/games/' + gameId + '/chat', { body });
      showMessage(msg);
      input.value = '';
      scrollBottom();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      sendBtn.disabled = false;
    }
  }

  function showMessage(m) {
    if (!m || m.id === undefined || m.id === null || shown.has(m.id)) return false;
    shown.add(m.id);
    const row = h('div', { class: 'chat-msg role-' + m.role },
      h('span', { class: 'chat-time' },
        new Date(m.created_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })),
      h('b', { class: 'chat-login' }, m.login),
      h('span', { class: 'chat-role' }, ROLE_RU[m.role] ?? 'зритель'),
      h('span', { class: 'chat-body' }, m.body),
    );
    list.appendChild(row);
    return true;
  }

  function scrollBottom() {
    list.scrollTop = list.scrollHeight;
  }

  return { load, onWsChat };
}
