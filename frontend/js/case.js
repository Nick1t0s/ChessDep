import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { toast } from './toast.js';
import { openModal } from './modal.js';
import { itemCard } from './items.js';
import { fmtCrystals } from './format.js';

await initLayout({ auth: 'optional', active: 'cases' });

const main = h('main', { class: 'wrap-wide case-page' });
document.body.appendChild(main);

const params = new URLSearchParams(location.search);
const idParam = params.get('id');
const itemParam = params.get('item');

if (idParam !== null && /^\d+$/.test(idParam)) {
  await initDetail(idParam);
} else if (itemParam !== null && /^\d+$/.test(itemParam)) {
  await initOpen(itemParam);
} else if (idParam !== null || itemParam !== null) {
  main.appendChild(h('div', { class: 'card' },
    h('p', {}, 'Некорректная ссылка'),
    h('a', { href: '/index.html', class: 'btn btn-gold' }, 'В лобби'),
  ));
} else {
  main.appendChild(h('a', { href: '/cases.html', class: 'btn btn-ghost' }, 'В магазин'));
}

function caseCaption(c) {
  if (c.kind === 'set' && c.set) return 'Набор ' + c.set.name;
  if (c.kind === 'collection' && c.collection) return 'Коллекция ' + c.collection.name;
  return null;
}

function detailHead(d) {
  const head = h('div', { class: 'card case-detail-head' },
    h('h1', { class: 'page-title' }, d.name),
    caseCaption(d) !== null ? h('p', { class: 'case-collection' }, caseCaption(d)) : null,
    h('p', { class: 'case-price mono' }, fmtCrystals(d.price)),
  );
  if (d.stock_left !== null) {
    head.appendChild(h('p', { class: 'case-stock' }, 'Осталось ' + d.stock_left));
  }
  if (d.sale_ends_at !== null) {
    head.appendChild(h('p', { class: 'case-sale' }, 'До ' + new Date(d.sale_ends_at).toLocaleString('ru-RU')));
  }
  if (!d.on_sale_now) {
    head.appendChild(h('p', {}, 'Сейчас не продаётся'));
  }
  if (d.on_sale_now) {
    const buyBtn = h('button', { type: 'button', class: 'btn btn-gold' }, 'Купить');
    buyBtn.addEventListener('click', () => buyDetail(String(d.id), buyBtn));
    head.appendChild(buyBtn);
  }
  return head;
}

function contentsCard(d) {
  const grid = h('div', { class: 'item-grid' });
  for (const drop of d.drops) {
    grid.appendChild(itemCard(drop.def, { badge: drop.chance_text }));
  }
  return h('div', { class: 'card' },
    h('h3', { class: 'card-title' }, 'Содержимое'),
    grid,
  );
}

async function initDetail(id) {
  clear(main);
  let d = null;
  try {
    d = await api('GET', '/cases/' + id);
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  main.append(detailHead(d), contentsCard(d));
}

async function buyDetail(id, btn) {
  btn.disabled = true;
  try {
    await api('POST', '/cases/' + id + '/buy');
    toast('Кейс в инвентаре', 'success');
    const fresh = await api('GET', '/me');
    setBalance(fresh.balance);
    await initDetail(id);
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
  }
}

function stripWindow() {
  const windowEl = h('div', { class: 'strip-window' },
    h('div', { class: 'strip-marker' }),
    h('div', { class: 'strip-track' }),
  );
  return [windowEl, windowEl.querySelector('.strip-track')];
}

function playStrip(windowEl, track, res) {
  clear(track);
  for (const defId of res.strip) {
    track.appendChild(h('div', { class: 'strip-cell' }, itemCard(res.defs[String(defId)])));
  }

  track.style.setProperty('transition', 'none');
  track.style.setProperty('transform', 'translateX(0px)');
  void track.offsetWidth;

  const offset = res.win_index * 132 + 66 - windowEl.clientWidth / 2;

  track.style.setProperty('transition', 'transform 5.5s cubic-bezier(.12,.8,.18,1)');
  track.style.setProperty('transform', 'translateX(' + String(-offset) + 'px)');

  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve();
    };
    track.addEventListener('transitionend', finish, { once: true });
    setTimeout(finish, 6000);
  });
}

async function initOpen(itemId) {
  clear(main);
  let items = [];
  try {
    items = await api('GET', '/inventory?kind=case');
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  const item = Array.isArray(items)
    ? items.find((it) => String(it.id) === itemId && it.status === 'owned')
    : null;
  if (item === null) {
    main.appendChild(h('p', {}, 'Кейс не найден'));
    main.appendChild(h('a', { href: '/inventory.html', class: 'btn btn-ghost' }, 'В инвентарь'));
    return;
  }

  let d = null;
  try {
    d = await api('GET', '/cases/' + String(item.case.id));
  } catch (e) {
    toast(e.message, 'error');
    return;
  }

  const [windowEl, track] = stripWindow();
  const openBtn = h('button', { type: 'button', class: 'btn btn-gold' }, 'Открыть');
  openBtn.addEventListener('click', () => openItemCase(String(item.id), openBtn, windowEl, track));

  const stripCard = h('div', { class: 'card' }, windowEl, openBtn);

  main.append(h('h1', { class: 'page-title' }, d.name), stripCard, contentsCard(d));

  for (const drop of d.drops) {
    track.appendChild(h('div', { class: 'strip-cell' }, itemCard(drop.def)));
  }
}

async function openItemCase(itemId, openBtn, windowEl, track) {
  openBtn.disabled = true;
  let res = null;
  try {
    res = await api('POST', '/inventory/' + itemId + '/open');
  } catch (e) {
    toast(e.message, 'error');
    openBtn.disabled = false;
    return;
  }

  await playStrip(windowEl, track, res);

  openModal({
    title: 'Выпало!',
    titleAnim: 'pop',
    body: itemCard(res.item.def, { exterior: res.item.exterior, image: res.item.image }),
    actions: [
      { label: 'В инвентарь', kind: 'ghost', onClick: () => { location.href = '/inventory.html'; } },
      { label: 'В магазин', kind: 'gold', onClick: () => { location.href = '/cases.html'; } },
    ],
  });

  openBtn.disabled = false;
}
