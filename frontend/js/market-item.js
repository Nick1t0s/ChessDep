import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { toast } from './toast.js';
import { confirmModal } from './modal.js';
import { fmtCrystals } from './format.js';
import { itemCard, casePreview, EXTERIOR_RU } from './items.js';

const me = await initLayout({ auth: 'optional', active: 'market' });

const main = h('main', { class: 'wrap-wide market-item' });
document.body.appendChild(main);

const params = new URLSearchParams(location.search);
const caseParam = params.get('case');
const defParam = params.get('def');

if (caseParam !== null && /^\d+$/.test(caseParam)) {
  await loadPage('cases/' + caseParam);
} else if (defParam !== null && /^\d+$/.test(defParam)) {
  await loadPage('defs/' + defParam);
} else {
  main.appendChild(h('div', { class: 'card' },
    h('p', {}, 'Некорректная ссылка'),
    h('a', { href: '/index.html', class: 'btn btn-gold' }, 'В лобби'),
  ));
}

async function loadPage(path) {
  try {
    const data = await api('GET', '/market/' + path);
    render(data);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function reload() {
  if (caseParam !== null && /^\d+$/.test(caseParam)) return loadPage('cases/' + caseParam);
  return loadPage('defs/' + defParam);
}

function render(data) {
  const stats = data.stats;

  clear(main);
  const head = data.case
    ? h('div', { class: 'item-card' },
        casePreview(data.case),
        h('div', { class: 'item-name' }, data.case.name),
      )
    : itemCard(data.def);
  main.appendChild(h('div', { class: 'mi-head' },
    head,
    h('div', { class: 'mi-stats' },
      h('p', {}, 'Лотов: ' + String(stats.active_count)),
      h('p', {}, 'Мин. цена: ' + (stats.min_price === null ? '—' : fmtCrystals(stats.min_price))),
      h('p', {}, 'Последняя продажа: ' + (stats.last_sale_price === null ? '—' : fmtCrystals(stats.last_sale_price))),
    ),
  ));

  main.appendChild(h('div', { class: 'card' },
    h('h3', { class: 'card-title' }, 'Лоты'),
    listingsTable(data.listings),
  ));

  main.appendChild(h('div', { class: 'card' },
    h('h3', { class: 'card-title' }, 'История продаж'),
    salesTable(data.sales),
  ));
}

function listingsTable(listings) {
  const tbody = h('tbody');
  for (const l of listings) {
    const btnTd = h('td');
    if (me !== null && !l.mine) {
      const buyBtn = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Купить');
      buyBtn.addEventListener('click', () => buyListing(l));
      btnTd.appendChild(buyBtn);
    }
    tbody.appendChild(h('tr', {},
      h('td', {}, h('span', { class: 'mk-price mono' }, fmtCrystals(l.price))),
      h('td', {}, l.seller_login),
      h('td', {}, EXTERIOR_RU[l.item.exterior] ?? l.item.exterior),
      btnTd,
    ));
  }
  return h('table', { class: 'mk-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'Цена'),
      h('th', {}, 'Продавец'),
      h('th', {}, 'Износ'),
      h('th'),
    )),
    tbody,
  );
}

function salesTable(sales) {
  const tbody = h('tbody');
  if (sales.length === 0) {
    tbody.appendChild(h('tr', {}, h('td', {}, 'Продаж ещё не было'), h('td')));
  } else {
    for (const s of sales) {
      tbody.appendChild(h('tr', {},
        h('td', {}, h('span', { class: 'mk-price mono' }, fmtCrystals(s.price))),
        h('td', {}, new Date(s.closed_at).toLocaleString('ru-RU')),
      ));
    }
  }
  return h('table', { class: 'mk-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'Цена'),
      h('th', {}, 'Дата'),
    )),
    tbody,
  );
}

async function buyListing(l) {
  const name = l.item.kind === 'case' ? l.item.case.name : l.item.def.name;
  const ok = await confirmModal('Покупка', name + ' за ' + fmtCrystals(l.price), 'Купить', 'gold');
  if (!ok) return;
  try {
    await api('POST', '/market/listings/' + String(l.id) + '/buy');
    toast('Куплено', 'success');
    const fresh = await api('GET', '/me');
    setBalance(fresh.balance);
    await reload();
  } catch (e) {
    toast(e.message, 'error');
  }
}
