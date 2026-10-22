import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { toast } from './toast.js';
import { confirmModal } from './modal.js';
import { fmtCrystals, PIECE_NAME_RU } from './format.js';
import { itemCard, RARITIES, RARITY_RU } from './items.js';

const me = await initLayout({ auth: 'optional', active: 'market' });

const main = h('main', { class: 'wrap-wide market' });
document.body.appendChild(main);

main.appendChild(h('h1', { class: 'page-title' }, 'Маркет'));

const tabs = h('div', { class: 'mk-tabs' });
const feedTab = h('button', { type: 'button', class: 'btn btn-gold' }, 'Лоты');
tabs.appendChild(feedTab);
let mineTab = null;
if (me !== null) {
  mineTab = h('button', { type: 'button', class: 'btn btn-ghost' }, 'Мои лоты');
  tabs.appendChild(mineTab);
}
main.appendChild(tabs);

function mkSelect(options) {
  const sel = h('select');
  for (const [value, label] of options) {
    sel.appendChild(h('option', { value }, label));
  }
  return sel;
}

const raritySel = mkSelect([['', 'Все'], ...RARITIES.map((r) => [r, RARITY_RU[r]])]);
const kindSel = mkSelect([['', 'Все'], ['piece_skin', 'Фигуры'], ['board_skin', 'Доски']]);
const pieceSel = mkSelect([['', 'Все'], ...['P', 'N', 'B', 'R', 'Q', 'K'].map((p) => [p, PIECE_NAME_RU[p]])]);
const sortSel = mkSelect([['new', 'Новые'], ['price_asc', 'Сначала дешёвые'], ['price_desc', 'Сначала дорогие']]);

const totalLine = h('p', { class: 'mk-total' });
const feedGrid = h('div', { class: 'item-grid' });
const pager = h('div', { class: 'mk-pager' });
const feedView = h('div', {},
  h('div', { class: 'mk-filters' }, raritySel, kindSel, pieceSel, sortSel),
  totalLine,
  feedGrid,
  pager,
);

const mineSel = mkSelect([['active', 'Активные'], ['sold', 'Проданные'], ['cancelled', 'Снятые']]);
const mineGrid = h('div', { class: 'item-grid' });
const mineEmpty = h('p', {}, 'Нет лотов');
const mineView = h('div', {},
  h('div', { class: 'mk-filters' }, mineSel),
  mineGrid,
  mineEmpty,
);

main.appendChild(feedView);
main.appendChild(mineView);

for (const sel of [raritySel, kindSel, pieceSel, sortSel]) {
  sel.addEventListener('change', () => {
    page = 1;
    loadFeed();
  });
}
mineSel.addEventListener('change', loadMine);

feedTab.addEventListener('click', () => setView('feed'));
if (mineTab !== null) mineTab.addEventListener('click', () => setView('mine'));

let mode = 'feed';
let page = 1;
let total = 0;

setView('feed');

async function loadFeed() {
  const params = new URLSearchParams();
  params.set('page', String(page));
  params.set('limit', '20');
  params.set('sort', sortSel.value);
  if (raritySel.value) params.set('rarity', raritySel.value);
  if (kindSel.value) params.set('kind', kindSel.value);
  if (pieceSel.value) params.set('piece_type', pieceSel.value);
  clear(feedGrid);
  try {
    const out = await api('GET', '/market?' + params.toString());
    total = out.total;
    totalLine.textContent = 'Найдено: ' + String(total);
    for (const l of out.items) {
      feedGrid.appendChild(lotCard(l));
    }
    renderPager();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function lotCard(l) {
  const row = h('div', { class: 'mk-row' },
    h('span', { class: 'mk-price mono' }, fmtCrystals(l.price)),
    h('span', { class: 'mk-seller' }, l.seller_login),
  );
  if (me !== null && !l.mine) {
    const buyBtn = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Купить');
    buyBtn.addEventListener('click', () => buyListing(l));
    row.appendChild(buyBtn);
  }
  row.appendChild(h('a', { class: 'btn btn-ghost btn-sm', href: '/market-item.html?def=' + String(l.item.def.id) }, 'История'));
  return itemCard(l.item.def, {
    exterior: l.item.exterior,
    badge: l.mine ? 'Ваш лот' : undefined,
    extra: row,
  });
}

function renderPager() {
  clear(pager);
  const pages = Math.max(1, Math.ceil(total / 20));
  const prev = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', disabled: page <= 1 }, 'Назад');
  const next = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', disabled: page >= pages }, 'Вперёд');
  prev.addEventListener('click', () => {
    page -= 1;
    loadFeed();
  });
  next.addEventListener('click', () => {
    page += 1;
    loadFeed();
  });
  pager.append(prev, h('span', {}, String(page) + ' / ' + String(pages)), next);
}

async function buyListing(l) {
  const ok = await confirmModal('Покупка', l.item.def.name + ' за ' + fmtCrystals(l.price), 'Купить', 'gold');
  if (!ok) return;
  try {
    await api('POST', '/market/listings/' + String(l.id) + '/buy');
    toast('Куплено', 'success');
    const fresh = await api('GET', '/me');
    setBalance(fresh.balance);
    await loadFeed();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function loadMine() {
  clear(mineGrid);
  mineEmpty.hidden = true;
  try {
    const listings = await api('GET', '/me/listings?status=' + encodeURIComponent(mineSel.value));
    for (const l of listings) {
      mineGrid.appendChild(myLotCard(l));
    }
    mineEmpty.hidden = listings.length > 0;
  } catch (e) {
    toast(e.message, 'error');
  }
}

function myLotCard(l) {
  const row = h('div', { class: 'mk-row' },
    h('span', { class: 'mk-price mono' }, fmtCrystals(l.price)),
    h('span', { class: 'mk-seller' }, new Date(l.created_at).toLocaleString('ru-RU')),
  );
  if (l.status === 'active') {
    const cancelBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Снять');
    cancelBtn.addEventListener('click', () => cancelListing(l));
    row.appendChild(cancelBtn);
  }
  return itemCard(l.item.def, {
    exterior: l.item.exterior,
    extra: row,
  });
}

async function cancelListing(l) {
  try {
    await api('DELETE', '/market/listings/' + String(l.id));
    toast('Лот снят', 'info');
    await loadMine();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function setView(next) {
  mode = next;
  feedView.hidden = next !== 'feed';
  mineView.hidden = next !== 'mine';
  feedTab.className = 'btn ' + (next === 'feed' ? 'btn-gold' : 'btn-ghost');
  if (mineTab !== null) mineTab.className = 'btn ' + (next === 'mine' ? 'btn-gold' : 'btn-ghost');
  if (next === 'feed') loadFeed();
  else loadMine();
}
