import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { fmtCrystals } from './format.js';

const me = await initLayout({ auth: 'optional', active: 'leaderboard' });

const main = h('main', { class: 'wrap-wide leaderboard' });

const tabs = h('div', { class: 'sc-tabs' });
const tabBtns = {};
for (const [by, label] of [['elo', 'По Elo'], ['balance', 'По балансу']]) {
  const btn = h('button', { type: 'button', class: 'btn btn-ghost' }, label);
  btn.addEventListener('click', () => selectTab(by));
  tabs.appendChild(btn);
  tabBtns[by] = btn;
}

const tbody = h('tbody');
const table = h('table', { class: 'sc-table' },
  h('thead', {},
    h('tr', {},
      h('th', {}, '#'),
      h('th', {}, 'Игрок'),
      h('th', {}, 'Elo'),
      h('th', {}, 'Баланс'),
    ),
  ),
  tbody,
);

main.append(tabs, table);
document.body.appendChild(main);

let by = '';

selectTab('elo');

function selectTab(value) {
  if (value === by) return;
  by = value;
  for (const [key, btn] of Object.entries(tabBtns)) {
    btn.className = 'btn ' + (key === by ? 'btn-gold' : 'btn-ghost');
  }
  load();
}

async function load() {
  try {
    const rows = await api('GET', '/leaderboard?by=' + by + '&limit=100');
    clear(tbody);
    for (const row of rows) {
      tbody.appendChild(h('tr', { class: row.login === me?.login ? 'me' : '' },
        h('td', {}, row.rank),
        h('td', {}, h('a', { href: '/user.html?login=' + encodeURIComponent(row.login) }, row.login)),
        h('td', {}, row.elo),
        h('td', {}, fmtCrystals(row.balance)),
      ));
    }
  } catch (e) {
    toast(e.message, 'error');
  }
}
