import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { itemCard, RARITIES, RARITY_RU } from './items.js';
import { toast } from './toast.js';

const me = await initLayout({ auth: 'optional', active: '' });

const main = h('main', { class: 'wrap-wide collection' });
document.body.appendChild(main);

const code = new URLSearchParams(location.search).get('code');
if (!code || !/^[a-z0-9-]{2,40}$/.test(code)) {
  main.append(h('p', { class: 'col-desc' }, 'Некорректная ссылка'));
} else {
  try {
    const collection = await api('GET', '/collections/' + encodeURIComponent(code));
    render(collection);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function render(collection) {
  main.append(
    h('h1', { class: 'page-title' }, collection.name),
    h('p', { class: 'col-desc' }, collection.description),
  );
  for (const rarity of [...RARITIES].reverse()) {
    const defs = collection.items.filter((d) => d.rarity === rarity);
    if (defs.length === 0) continue;
    main.append(h('h2', { class: 'col-rarity r-' + rarity }, RARITY_RU[rarity]));
    main.append(
      h('div', { class: 'item-grid' },
        defs.map((def) => itemCard(def, {
          extra: h('a', { href: '/market-item.html?def=' + def.id, class: 'btn btn-ghost btn-sm' }, 'На маркете'),
        })),
      ),
    );
  }
}
