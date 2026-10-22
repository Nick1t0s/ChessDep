import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';

await initLayout({ auth: 'required', active: 'live' });

const main = h('main', { class: 'wrap-wide live' });

const grid = h('div', { class: 'lv-grid' });
const empty = h('div', { hidden: true },
  h('p', { class: 'lv-empty' }, 'Сейчас никто не играет.'),
  h('a', { href: '/index.html', class: 'btn btn-ghost btn-sm' }, 'Сыграть'),
);

main.append(
  h('h1', { class: 'page-title' }, 'Идут партии'),
  h('p', { class: 'lv-hint' }, 'Обновляется каждые 10 секунд'),
  grid,
  empty,
);
document.body.appendChild(main);

let errored = false;

function gameCard(g) {
  return h('div', { class: 'card lv-card' },
    h('div', { class: 'lv-players' },
      h('b', null, g.white.login),
      h('span', { class: 'lv-elo' }, '(' + g.white.elo + ')'),
      h('span', { class: 'lv-vs' }, 'vs'),
      h('b', null, g.black.login),
      h('span', { class: 'lv-elo' }, '(' + g.black.elo + ')'),
    ),
    h('p', { class: 'lv-meta' },
      g.time_control
      + ' · ход ' + (Math.floor(g.ply / 2) + 1)
      + ' · депов ' + g.deps_used,
    ),
    h('a', { href: '/game.html?id=' + g.id, class: 'btn btn-gold btn-sm' }, 'Смотреть'),
  );
}

async function reload() {
  let games;
  try {
    games = await api('GET', '/games/live?limit=50');
  } catch (e) {
    if (!errored) {
      errored = true;
      toast(e.message, 'error');
    }
    return;
  }
  errored = false;
  clear(grid);
  if (games.length) {
    for (const g of games) grid.appendChild(gameCard(g));
    grid.hidden = false;
    empty.hidden = true;
  } else {
    grid.hidden = true;
    empty.hidden = false;
  }
}

await reload();
setInterval(reload, 10000);
