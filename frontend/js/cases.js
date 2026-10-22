import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { fmtCrystals } from './format.js';

const me = await initLayout({ auth: 'optional', active: 'cases' });

const main = h('main', { class: 'wrap-wide cases' });

const title = h('h1', { class: 'page-title' }, 'Кейсы');
const grid = h('div', { class: 'case-grid' });

main.append(title, grid);
document.body.appendChild(main);

let cases = [];
try {
  cases = await api('GET', '/cases');
} catch (e) {
  toast(e.message, 'error');
}

if (!Array.isArray(cases) || cases.length === 0) {
  grid.replaceWith(h('p', {}, 'Кейсов пока нет.'));
} else {
  for (const c of cases) {
    grid.appendChild(h('div', { class: 'card case-card' },
      h('h3', { class: 'card-title' }, c.name),
      h('p', { class: 'case-collection' }, 'Коллекция ' + c.collection.name),
      h('p', { class: 'case-price mono' }, fmtCrystals(c.price)),
      h('a', { href: '/case.html?id=' + encodeURIComponent(c.id), class: 'btn btn-gold btn-block' }, 'Открыть'),
    ));
  }
}
