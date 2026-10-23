import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { itemCard } from './items.js';
import { toast } from './toast.js';

const me = await initLayout({ auth: 'optional', active: 'sets' });

const main = h('main', { class: 'wrap-wide collection' });
document.body.appendChild(main);

const code = new URLSearchParams(location.search).get('set');
if (!code || !/^[a-z0-9-]{2,40}$/.test(code)) {
  main.append(h('p', { class: 'col-desc' }, 'Некорректная ссылка'));
} else {
  try {
    const set = await api('GET', '/sets/' + encodeURIComponent(code));
    render(set);
  } catch (e) {
    if (e.status === 404) {
      main.append(h('h1', { class: 'page-title' }, 'Набор не найден'));
    } else {
      toast(e.message, 'error');
    }
  }
}

function itemRow(defs) {
  return h('div', { class: 'item-grid' }, defs.map((def) => itemCard(def)));
}

function render(set) {
  main.append(
    h('h1', { class: 'page-title' }, set.name),
    h('p', { class: 'col-desc' }, set.description),
  );
  for (const c of set.collections) {
    main.append(
      h('h2', { class: 'col-rarity' }, c.name),
      h('p', { class: 'col-desc' }, c.description),
      h('h3', { class: 'col-meta' }, 'Белые'),
      itemRow(c.items.slice(0, 6)),
      h('h3', { class: 'col-meta' }, 'Чёрные'),
      itemRow(c.items.slice(6, 12)),
    );
  }
  if (set.boards.length > 0) {
    main.append(h('h2', { class: 'col-rarity' }, 'Доски'), itemRow(set.boards));
  }
}
