import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { createBoard } from './board.js';
import { PIECE_NAME_RU, END_REASON_RU } from './format.js';
import { createMoveList } from './game-moves.js';
import { createChat } from './game-chat.js';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

await main();

async function main() {
  await initLayout({ auth: 'required', active: '' });

  const params = new URLSearchParams(location.search);
  const id = params.get('id') ?? '';
  const mainEl = h('main', { class: 'wrap-wide replay' });
  document.body.appendChild(mainEl);

  if (!UUID_RE.test(id)) {
    mainEl.appendChild(h('div', { class: 'card' },
      h('p', {}, 'Некорректная ссылка'),
      h('a', { href: '/index.html', class: 'btn btn-gold' }, 'В лобби'),
    ));
    return;
  }

  // ---- разметка ----
  const headEl = h('div', { class: 'rp-head' });
  const boardBox = h('div', { class: 'board-box' });

  const btnStart = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'В начало', title: 'В начало' }, '⏮');
  const btnPrev = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'Назад', title: 'Назад' }, '◀');
  const btnNext = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'Вперёд', title: 'Вперёд' }, '▶');
  const btnEnd = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', 'aria-label': 'В конец', title: 'В конец' }, '⏭');
  const btnFlip = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Перевернуть');
  const controls = h('div', { class: 'rp-controls' }, btnStart, btnPrev, btnNext, btnEnd, btnFlip);

  const infoEl = h('p', { class: 'rp-info' });
  const boardHolder = h('div', {}, headEl, boardBox, controls, infoEl);

  const movesBox = h('div', {});
  const chatBox = h('div', {});
  const movesCard = h('div', { class: 'card' }, h('h3', { class: 'card-title' }, 'Ходы'), movesBox);
  const chatCard = h('div', { class: 'card' }, h('h3', { class: 'card-title' }, 'Чат'), chatBox);

  mainEl.appendChild(h('div', { class: 'rp-layout' }, boardHolder, h('div', {}, movesCard, chatCard)));

  const board = createBoard(boardBox, {});
  btnStart.addEventListener('click', () => go(0));
  btnPrev.addEventListener('click', () => go(idx - 1));
  btnNext.addEventListener('click', () => go(idx + 1));
  btnEnd.addEventListener('click', () => go(positions.length - 1));
  btnFlip.addEventListener('click', flip);
  document.addEventListener('keydown', onKeydown);

  // ---- загрузка ----
  let data;
  try {
    data = await api('GET', '/games/' + id + '/events');
  } catch (e) {
    toast(e.message, 'error');
    infoEl.textContent = 'Партия недоступна';
    return;
  }
  const game = data.game;
  const events = [...(data.events ?? [])].sort((a, b) => a.seq - b.seq);

  renderHead(game);

  const positions = [{
    board: game.initial_board,
    check_square: null,
    last_action: null,
    ev: null,
  }];
  for (const ev of events) {
    if (ev.kind !== 'move' && ev.kind !== 'dep') continue;
    positions.push({
      board: ev.board,
      check_square: ev.check_square,
      last_action: { kind: ev.kind, ...ev.payload },
      ev,
    });
  }

  const moves = createMoveList(movesBox, {
    onSelect: (ev) => {
      const i = positions.findIndex((p) => p.ev !== null && p.ev.seq === ev.seq);
      if (i >= 0) go(i);
    },
  });
  moves.setEvents(events);

  const chat = createChat(chatBox, { gameId: id, canWrite: false });
  chat.load();

  let orientation = 'white';
  let idx = positions.length - 1;
  go(idx);

  // ---- функции ----
  function renderHead(game) {
    const outcome = resultText(game);
    const parts = [
      h('span', { class: 'mono' },
        h('b', {}, game.white?.login ?? '—'), ' (' + (game.white?.elo ?? '—') + ')',
      ),
      ' vs ',
      h('span', { class: 'mono' },
        h('b', {}, game.black?.login ?? '—'), ' (' + (game.black?.elo ?? '—') + ')',
      ),
      ' · ',
      h('span', { class: 'mono' }, game.time_control ?? '—'),
      h('br'),
      h('span', { class: 'rp-result', role: 'status' }, outcome),
    ];
    if (game.end_reason !== null) {
      parts.push(h('span', { class: 'rp-result' },
        outcome === '' ? (END_REASON_RU[game.end_reason] ?? game.end_reason) : ' · ' + (END_REASON_RU[game.end_reason] ?? game.end_reason)));
    }
    headEl.append(...parts);
  }

  function resultText(game) {
    if (game.status === 'active') return 'Партия идёт';
    if (game.result === 'white') return 'Победили белые';
    if (game.result === 'black') return 'Победили чёрные';
    if (game.result === 'draw') return 'Ничья';
    return '';
  }

  function go(i) {
    idx = Math.max(0, Math.min(positions.length - 1, i));
    const pos = positions[idx];
    board.render({
      board: pos.board,
      check_square: pos.check_square,
      last_action: pos.last_action,
      you: orientation,
      players: {
        white: { loadout: game.white_loadout },
        black: { loadout: game.black_loadout },
      },
    }, {});
    moves.select(pos.ev?.seq ?? null);
    renderInfo();
  }

  function renderInfo() {
    const pos = positions[idx];
    const ev = pos.ev;
    clearInfo();
    if (ev === null) {
      infoEl.textContent = 'Начальная позиция';
      return;
    }
    if (ev.kind === 'dep') {
      const p = ev.payload ?? {};
      infoEl.textContent = 'Ход ' + ev.ply + ' · Деп: ' + PIECE_NAME_RU[p.from] + ' → ' + PIECE_NAME_RU[p.to]
        + ' · шанс ' + (p.chance * 100).toFixed(2) + '% · ' + (p.success ? 'успех' : 'провал');
      return;
    }
    infoEl.textContent = 'Ход ' + ev.ply;
  }

  function clearInfo() {
    while (infoEl.firstChild) infoEl.firstChild.remove();
  }

  function flip() {
    orientation = orientation === 'white' ? 'black' : 'white';
    board.setOrientation(orientation);
    go(idx);
  }

  function onKeydown(e) {
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      go(idx - 1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      go(idx + 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      go(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      go(positions.length - 1);
    }
  }
}
