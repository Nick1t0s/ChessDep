import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';

const me = await initLayout({ auth: 'required', active: '' });

const main = h('main', { class: 'wrap-wide admin' });
document.body.appendChild(main);

if (me && me.role !== 'admin') {
  main.append(h('p', {}, 'Нет доступа'));
} else {
  const TABS = [
    { key: 'catalog', label: 'Коллекции', path: './admin/catalog.js', fn: 'mount' },
    { key: 'users', label: 'Пользователи', path: './admin/users.js', fn: 'mount' },
    { key: 'settings', label: 'Настройки', path: './admin/settings.js', fn: 'mount' },
    { key: 'market', label: 'Маркет', path: './admin/misc.js', fn: 'mountMarket' },
    { key: 'audit', label: 'Журнал', path: './admin/misc.js', fn: 'mountAudit' },
  ];

  main.append(h('h1', { class: 'page-title' }, 'Админка'));

  const buttons = new Map();
  const tabsRow = h('div', { class: 'admin-tabs' });
  for (const t of TABS) {
    const btn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, t.label);
    btn.addEventListener('click', () => openTab(t.key));
    buttons.set(t.key, btn);
    tabsRow.appendChild(btn);
  }
  const container = h('div', { class: 'admin-tab' });
  main.append(tabsRow, container);

  let current = null;

  async function openTab(key) {
    if (current === key) return;
    current = key;
    const tab = TABS.find(t => t.key === key);
    for (const [k, btn] of buttons) {
      btn.className = k === key ? 'btn btn-gold btn-sm' : 'btn btn-ghost btn-sm';
    }
    clear(container);
    location.hash = key;
    try {
      const mod = await import(tab.path);
      await mod[tab.fn](container);
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  const initial = TABS.some(t => location.hash.slice(1) === t.key)
    ? location.hash.slice(1)
    : 'catalog';
  openTab(initial);
}
