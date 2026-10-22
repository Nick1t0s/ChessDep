import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';

const me = await initLayout({ auth: 'optional', active: '' });

const main = h('main', { class: 'wrap-wide collections' });
const grid = h('div', { class: 'col-grid' });
main.append(h('h1', { class: 'page-title' }, 'Коллекции'), grid);
document.body.appendChild(main);

try {
  const collections = await api('GET', '/collections');
  for (const c of collections) {
    const statusText = c.status === 'retired' ? 'Снята с выпуска' : 'В продаже';
    const released = c.released_at ? new Date(c.released_at).toLocaleString('ru-RU') : '—';
    grid.append(
      h('div', { class: 'card col-card' },
        h('h3', { class: 'card-title' }, c.name),
        h('span', { class: 'pill' }, statusText),
        h('p', { class: 'col-desc' }, c.description),
        h('p', { class: 'col-meta' }, 'Скинов: ' + c.items_count + ' · выпущена ' + released),
        h('a', { href: '/collection.html?code=' + encodeURIComponent(c.code), class: 'btn btn-gold btn-sm' }, 'Смотреть'),
      ),
    );
  }
} catch (e) {
  toast(e.message, 'error');
}
