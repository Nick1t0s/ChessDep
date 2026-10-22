import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { itemCard } from './items.js';

const me = await initLayout({ auth: 'required', active: '' });

const main = h('main', { class: 'wrap-wide gifts' });

const tabs = h('div', { class: 'sc-tabs' });
const tabBtns = {};
for (const [dir, label] of [['in', 'Входящие'], ['out', 'Отправленные']]) {
  const btn = h('button', { type: 'button', class: 'btn btn-ghost' }, label);
  btn.addEventListener('click', () => selectTab(dir));
  tabs.appendChild(btn);
  tabBtns[dir] = btn;
}

const hint = h('p', { class: 'sc-hint' },
  'Подарить предмет можно из ',
  h('a', { href: '/inventory.html' }, 'инвентаря'),
);

const grid = h('div', { class: 'item-grid' });
const emptyMsg = h('p', { hidden: true }, 'Подарков нет');
const moreBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', hidden: true }, 'Ещё');
moreBtn.addEventListener('click', () => loadPage());

main.append(tabs, hint, grid, emptyMsg, moreBtn);
document.body.appendChild(main);

let dir = '';
let nextCursor = null;
let loading = false;

selectTab('in');

function selectTab(newDir) {
  if (newDir === dir) return;
  dir = newDir;
  for (const [key, btn] of Object.entries(tabBtns)) {
    btn.className = 'btn ' + (key === dir ? 'btn-gold' : 'btn-ghost');
  }
  nextCursor = null;
  clear(grid);
  loadPage();
}

async function loadPage() {
  if (loading) return;
  loading = true;
  try {
    let path = '/me/gifts?direction=' + dir + '&limit=20';
    if (nextCursor !== null) path += '&before_id=' + nextCursor;
    const out = await api('GET', path);
    nextCursor = out.next_cursor;
    for (const g of out.items) grid.appendChild(giftCard(g));
    emptyMsg.hidden = grid.childElementCount > 0;
    moreBtn.hidden = nextCursor === null;
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    loading = false;
  }
}

function giftCard(g) {
  return itemCard(g.item.def, {
    exterior: g.item.exterior,
    badge: dir === 'in' && !g.seen ? 'Новый' : undefined,
    extra: h('div', { class: 'sc-gift' },
      h('p', { class: 'sc-who' }, dir === 'in' ? 'От ' + g.from_login : 'Кому: ' + g.to_login),
      h('p', { class: 'sc-date' }, new Date(g.created_at).toLocaleString('ru-RU')),
      g.note ? h('p', { class: 'sc-note' }, g.note) : null,
    ),
  });
}
