import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';

const me = await initLayout({ auth: 'optional', active: 'sets' });

const main = h('main', { class: 'wrap-wide collections' });
const grid = h('div', { class: 'col-grid' });
main.append(h('h1', { class: 'page-title' }, 'Наборы'), grid);
document.body.appendChild(main);

try {
  const sets = await api('GET', '/sets');
  if (sets.length === 0) {
    grid.replaceWith(h('p', { class: 'col-desc' }, 'Наборов пока нет.'));
  }
  for (const s of sets) {
    grid.append(
      h('div', { class: 'card col-card' },
        h('h3', { class: 'card-title' }, s.name),
        s.status === 'retired' ? h('span', { class: 'pill' }, 'Снят с выпуска') : null,
        h('p', { class: 'col-desc' }, s.description),
        h('p', { class: 'col-meta' }, 'Коллекций: ' + s.collections_count + ' · Досок: ' + s.boards_count),
        h('a', { href: '/collection.html?set=' + encodeURIComponent(s.code), class: 'btn btn-gold btn-sm' }, 'Смотреть'),
      ),
    );
  }
} catch (e) {
  toast(e.message, 'error');
}
