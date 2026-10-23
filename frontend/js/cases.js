import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { toast } from './toast.js';
import { fmtCrystals } from './format.js';

await initLayout({ auth: 'optional', active: 'cases' });

const main = h('main', { class: 'wrap-wide cases' });
const listWrap = h('div', { class: 'cases-list' });

main.appendChild(h('h1', { class: 'page-title' }, 'Магазин'));
main.appendChild(listWrap);
document.body.appendChild(main);

const GROUPS = [
  ['Наборы', 'set'],
  ['Коллекции', 'collection'],
  ['Особые', 'custom'],
];

await loadShop();

async function loadShop() {
  let cases = [];
  try {
    cases = await api('GET', '/shop');
  } catch (e) {
    toast(e.message, 'error');
  }
  renderShop(cases);
}

function renderShop(cases) {
  clear(listWrap);
  if (!Array.isArray(cases) || cases.length === 0) {
    listWrap.appendChild(h('p', {}, 'Сейчас в магазине пусто.'));
    return;
  }
  for (const [label, kind] of GROUPS) {
    const items = cases.filter((c) => c.kind === kind);
    if (items.length === 0) continue;
    listWrap.appendChild(h('h2', { class: 'page-title' }, label));
    const grid = h('div', { class: 'case-grid' });
    for (const c of items) grid.appendChild(caseCard(c));
    listWrap.appendChild(grid);
  }
}

function caseCaption(c) {
  if (c.kind === 'set' && c.set) return 'Набор ' + c.set.name;
  if (c.kind === 'collection' && c.collection) return 'Коллекция ' + c.collection.name;
  return null;
}

function caseCard(c) {
  const buyBtn = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Купить');
  buyBtn.addEventListener('click', () => buyCase(String(c.id), buyBtn));
  return h('div', { class: 'card case-card' },
    h('h3', { class: 'card-title' }, c.name),
    caseCaption(c) !== null ? h('p', { class: 'case-collection' }, caseCaption(c)) : null,
    h('p', { class: 'case-price mono' }, fmtCrystals(c.price)),
    c.stock_left !== null ? h('p', { class: 'case-stock' }, 'Осталось ' + c.stock_left) : null,
    c.sale_ends_at !== null
      ? h('p', { class: 'case-sale' }, 'До ' + new Date(c.sale_ends_at).toLocaleString('ru-RU'))
      : null,
    h('div', { class: 'case-actions' },
      buyBtn,
      h('a', { href: '/case.html?id=' + encodeURIComponent(c.id), class: 'btn btn-ghost btn-sm' }, 'Содержимое'),
    ),
  );
}

async function buyCase(id, btn) {
  btn.disabled = true;
  try {
    await api('POST', '/cases/' + id + '/buy');
    toast('Кейс в инвентаре', 'success');
    const fresh = await api('GET', '/me');
    setBalance(fresh.balance);
    await loadShop();
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
  }
}
