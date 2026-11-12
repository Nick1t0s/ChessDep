import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { toast } from './toast.js';
import { fmtCrystals } from './format.js';
import { openModal } from './modal.js';
import { itemCard } from './items.js';

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
  const dropsBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Содержимое');
  dropsBtn.addEventListener('click', () => showContents(c, buyBtn));
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
      dropsBtn,
    ),
  );
}

// Содержимое кейса — в модалке поверх магазина.
async function showContents(c, buyBtn) {
  let d = null;
  try {
    d = await api('GET', '/cases/' + encodeURIComponent(c.id));
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  const grid = h('div', { class: 'item-grid case-drops' });
  for (const drop of d.drops) {
    grid.appendChild(itemCard(drop.def, { badge: drop.chance_text }));
  }
  const actions = [{ label: 'Закрыть', kind: 'ghost' }];
  if (d.on_sale_now) {
    actions.push({ label: 'Купить за ' + fmtCrystals(d.price), kind: 'gold', onClick: () => buyCase(String(c.id), buyBtn) });
  }
  openModal({ title: d.name, titleAnim: 'none', body: grid, actions });
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
