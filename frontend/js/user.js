import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { END_REASON_RU } from './format.js';

await initLayout({ auth: 'required', active: '' });

const main = h('main', { class: 'wrap-wide user' });
document.body.appendChild(main);

const login = new URLSearchParams(location.search).get('login');

if (login === null || !/^[A-Za-z0-9_-]{3,16}$/.test(login)) {
  main.appendChild(h('p', {}, 'Некорректная ссылка'));
} else {
  let user;
  try {
    user = await api('GET', '/users/' + encodeURIComponent(login));
  } catch (e) {
    if (e.status === 404) {
      main.appendChild(h('p', {}, 'Игрок не найден'));
    } else {
      toast(e.message, 'error');
    }
  }

  if (user) {
    // ---------- 1. Профиль ----------
    main.appendChild(h('h1', { class: 'page-title' }, user.login));
    main.appendChild(h('div', { class: 'card' },
      h('h3', { class: 'card-title' }, 'Статистика'),
      h('p', { class: 'us-row' }, h('span', null, 'Elo'), h('b', null, String(user.elo))),
      h('p', { class: 'us-row' }, h('span', null, 'Сыграно'), h('b', null, String(user.games.played))),
      h('p', { class: 'us-row' }, h('span', null, 'Победы'), h('b', null, String(user.games.wins))),
      h('p', { class: 'us-row' }, h('span', null, 'Ничьи'), h('b', null, String(user.games.draws))),
      h('p', { class: 'us-row' }, h('span', null, 'Поражения'), h('b', null, String(user.games.losses))),
      h('p', { class: 'us-row' }, h('span', null, 'На сайте с'), h('b', null, new Date(user.created_at).toLocaleString('ru-RU'))),
    ));

    // ---------- 2. Партии ----------
    const gamesBody = h('tbody');
    const gamesMoreBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', hidden: true }, 'Ещё');
    main.appendChild(h('div', { class: 'card' },
      h('h3', { class: 'card-title' }, 'Партии'),
      h('div', { class: 'table-wrap' },
        h('table', { class: 'us-table' },
          h('thead', null, h('tr', null,
            h('th', null, 'Дата'),
            h('th', null, 'Соперник'),
            h('th', null, 'Цвет'),
            h('th', null, 'Результат'),
            h('th', null, 'Причина'),
            h('th', null, 'Контроль'),
            h('th', null, 'Elo'),
            h('th', null, ''),
          )),
          gamesBody,
        ),
      ),
      gamesMoreBtn,
    ));

    let nextBefore = null;

    function gameRow(game) {
      let result;
      if (game.result === null) result = 'Отменена';
      else if (game.result === 'draw') result = 'Ничья';
      else if (game.result === game.color) result = 'Победа';
      else result = 'Поражение';
      const elo = game.elo_delta === null ? '—' : (game.elo_delta > 0 ? '+' : '') + String(game.elo_delta);
      return h('tr', null,
        h('td', null, new Date(game.finished_at).toLocaleString('ru-RU')),
        h('td', null, h('a', { href: '/user.html?login=' + encodeURIComponent(game.opponent_login) }, game.opponent_login)),
        h('td', null, game.color === 'white' ? 'Белые' : 'Чёрные'),
        h('td', null, result),
        h('td', null, END_REASON_RU[game.end_reason] ?? ''),
        h('td', null, game.time_control),
        h('td', null, elo),
        h('td', null, h('a', { href: '/replay.html?id=' + game.id, class: 'btn btn-ghost btn-sm' }, 'Повтор')),
      );
    }

    async function loadGames() {
      const params = new URLSearchParams({ limit: '20' });
      if (nextBefore !== null) params.set('before', nextBefore);
      const page = await api('GET', '/users/' + encodeURIComponent(login) + '/games?' + params.toString());
      for (const game of page.items) gamesBody.appendChild(gameRow(game));
      if (page.items.length === 0 && gamesBody.children.length === 0) {
        gamesBody.appendChild(h('tr', null, h('td', null, 'Партий ещё нет'), h('td'), h('td'), h('td'), h('td'), h('td'), h('td'), h('td')));
      }
      nextBefore = page.next_before;
      gamesMoreBtn.hidden = nextBefore === null;
    }

    gamesMoreBtn.addEventListener('click', () => {
      loadGames().catch((e) => toast(e.message, 'error'));
    });

    loadGames().catch((e) => toast(e.message, 'error'));
  }
}
