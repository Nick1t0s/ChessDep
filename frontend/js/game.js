import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { createBoard } from './board.js';
import { connectGame } from './ws.js';
import { playDep } from './dep-fx.js';
import { fmtClock, END_REASON_RU, PIECE_NAME_RU, DEP_REASON_RU } from './format.js';
import { glyph, pieceColor } from './pieces.js';
import { toast } from './toast.js';
import { openModal, confirmModal } from './modal.js';
import { createMoveList } from './game-moves.js';
import { createChat } from './game-chat.js';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

await main();

async function main() {
  await initLayout({ auth: 'required', active: 'play' });

  const params = new URLSearchParams(location.search);
  const id = params.get('id') ?? '';
  if (!UUID_RE.test(id)) {
    const bad = h('main', { class: 'game-main' },
      h('div', { class: 'card center-note' },
        h('p', {}, 'Некорректная ссылка на партию.'),
        h('a', { href: '/index.html', class: 'btn btn-gold' }, 'В лобби'),
      ),
    );
    document.body.appendChild(bad);
    return;
  }

  // ---- переменные партии ----
  let state = null;          // последнее применённое GameState
  let mode = 'idle';         // idle | dep_piece | dep_target | dep_confirm
  let selected = null;       // выбранная клетка
  let depOptions = null;
  let depPiece = null;
  let depTarget = null;
  let busy = false;          // собственный запрос в полёте
  let fxRunning = false;     // идёт анимация депа
  let endShown = false;
  let endTimer = null;
  let gameOverInfo = null;
  let endBody = null;        // тело открытой модалки итога
  let endInfoFilled = false; // Elo и награда уже дописаны
  let receivedAt = 0;
  let forbidden = false;
  let firstStateSeen = false;
  let viewing = null;        // просматриваемое событие (история ходов) или null

  // ---- очередь событий: всё последовательно ----
  let chain = Promise.resolve();
  function enqueue(fn) {
    chain = chain.then(fn).catch((e) => console.error(e));
    return chain;
  }

  // ---- DOM ----
  const oppPanel = playerPanel();
  const youPanel = playerPanel();
  const cancelPick = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Отмена');
  cancelPick.addEventListener('click', () => cancelDep());
  const depHint = h('div', { class: 'dep-hint' }, h('span', { class: 'dep-hint-text' }, 'Выберите фигуру для депа'), cancelPick);
  depHint.hidden = true;

  const spectatorBadge = h('div', { class: 'spectator-badge', hidden: true }, 'Вы смотрите партию');

  const viewBannerText = h('span', { class: 'view-banner-text' });
  const viewBannerBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'К текущей позиции');
  viewBannerBtn.addEventListener('click', () => exitView());
  const viewBanner = h('div', { class: 'view-banner', hidden: true }, viewBannerText, viewBannerBtn);

  const boardBox = h('div', { class: 'board-box' });
  const boardApi = createBoard(boardBox, { onSquareClick });

  const drawBannerTitle = h('span', { class: 'banner-text' }, 'Соперник предлагает ничью');
  const drawAccept = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Принять');
  const drawDecline = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Отклонить');
  drawAccept.addEventListener('click', () => gameAction('/draw/accept'));
  drawDecline.addEventListener('click', () => gameAction('/draw/decline'));
  const drawBanner = h('div', { class: 'card banner' }, drawBannerTitle, drawAccept, drawDecline);
  drawBanner.hidden = true;

  const depPanel = h('div', { class: 'card dep-panel', hidden: true });
  const connIndicator = h('div', { class: 'conn card', hidden: true }, 'Соединение потеряно, переподключаемся…');

  const depCountEl = h('span', { class: 'btn-cap' });
  const btnDep = h('button', { type: 'button', class: 'btn btn-gold btn-block' }, 'Деп', depCountEl);
  btnDep.addEventListener('click', () => onDepClick());
  const btnDraw = h('button', { type: 'button', class: 'btn btn-ghost btn-block' }, 'Предложить ничью');
  btnDraw.addEventListener('click', () => {
    if (state && state.draw_offer_by === state.you) return;
    gameAction('/draw/offer');
  });
  const btnResign = h('button', { type: 'button', class: 'btn btn-danger btn-block' }, 'Сдаться');
  btnResign.addEventListener('click', onResign);
  const btnAbort = h('button', { type: 'button', class: 'btn btn-ghost btn-block' }, 'Отменить партию');
  btnAbort.addEventListener('click', () => gameAction('/abort'));
  btnAbort.hidden = true;

  const movesBox = h('div', { class: 'moves' });
  const movesCard = h('div', { class: 'card moves-card' }, h('h4', { class: 'card-title' }, 'Ходы'), movesBox);

  const chatBox = h('div', { class: 'chat-box' });
  const chatCard = h('div', { class: 'card chat-card' }, h('h4', { class: 'card-title' }, 'Чат'), chatBox);

  const actionsCard = h('div', { class: 'card actions-card' }, btnDep, btnDraw, btnResign, btnAbort, connIndicator);

  const sideCol = h('div', { class: 'side-col' }, drawBanner, depPanel, actionsCard, movesCard, chatCard);

  const gameMain = h('main', { class: 'game-main' },
    h('div', { class: 'match-grid' },
      h('div', { class: 'board-side' }, spectatorBadge, viewBanner, oppPanel, depHint, boardBox, youPanel),
      sideCol,
    ),
  );
  document.body.appendChild(gameMain);

  const moves = createMoveList(movesBox, { onSelect: viewEvent });
  const chat = createChat(chatBox, { gameId: id, canWrite: true });

  function playerPanel() {
    return h('div', { class: 'player-panel' },
      h('span', { class: 'p-king' }, ''),
      h('b', { class: 'p-login' }, '—'),
      h('span', { class: 'p-elo' }, ''),
      h('span', { class: 'p-deps' }, ''),
      h('span', { class: 'p-clock' }, '—'),
    );
  }

  // ---- состояние ----
  function isSpectator() {
    return state !== null && state.you === 'spectator';
  }

  function applyState(s) {
    if (s === null || typeof s !== 'object') return;
    if (state !== null && !(s.version > state.version)) return; // защита от перепутанного порядка
    const prevState = state;
    state = s;
    receivedAt = performance.now();
    const spectator = isSpectator();
    const versionGrew = prevState !== null;

    // Игрок, чей сейчас ход, всегда смотрит актуальную позицию.
    if (viewing !== null && versionGrew && !spectator && state.turn === state.you) exitView();

    boardApi.setOrientation(state.you === 'black' ? 'black' : 'white');
    if (mode !== 'idle' && (spectator || state.status !== 'active' || state.turn !== state.you)) {
      mode = 'idle';
      depOptions = null;
      depPiece = null;
      depTarget = null;
      depHint.hidden = true;
      renderDepPanel();
    }
    if (mode === 'idle') selected = null;
    boardRender();
    renderPanels();
    updateButtons();
    spectatorBadge.hidden = !spectator;
    actionsCard.hidden = spectator;
    depHint.hidden = spectator;
    depPanel.hidden = spectator;
    drawBanner.hidden = spectator
      || !(state.draw_offer_by !== null && state.draw_offer_by !== state.you && state.status === 'active');
    btnAbort.hidden = spectator || !(state.status === 'active' && state.ply < 2);

    if (spectator) {
      if (state.status !== 'active' && !endShown) scheduleEnd();
      else if (state.status === 'active') clearEndTimer();
    } else if (state.status !== 'active' && !endShown) scheduleEnd();
    else if (state.status === 'active') clearEndTimer();

    // История ходов: первичная полная загрузка, затем инкрементально по версии.
    if (!firstStateSeen) {
      firstStateSeen = true;
      loadEvents(false);
    } else if (versionGrew) {
      loadEvents(true);
    }
  }

  function scheduleEnd() {
    if (endTimer !== null || endShown) return;
    // партии, загруженные после окончания (перезагрузка страницы), не получат
    // WS game_over — итоги показываем без Elo/наград.
    endTimer = setTimeout(() => {
      endTimer = null;
      showEnd(null);
    }, 350);
  }

  function clearEndTimer() {
    if (endTimer !== null) {
      clearTimeout(endTimer);
      endTimer = null;
    }
  }

  async function rememberGameOver(data) {
    let meFresh = null;
    try {
      meFresh = await api('GET', '/me', undefined, { redirectOn401: false });
    } catch {
      meFresh = null;
    }
    if (meFresh) setBalance(meFresh.balance);
    gameOverInfo = {
      result: data?.result ?? null,
      end_reason: data?.end_reason ?? null,
      eloDelta: data?.elo_delta ? data.elo_delta[state.you] : null,
      reward: data?.rewards ? data.rewards[state.you] : null,
      myElo: meFresh ? meFresh.elo : null,
    };
    if (endShown) fillEndInfo(gameOverInfo);
    else showEnd(gameOverInfo);
  }

  // game_over по WS может прийти позже, чем откроется модалка по таймеру
  // (медленная сеть), — тогда строки Elo и награды дописываются в неё.
  function fillEndInfo(info) {
    if (endBody === null || info === null || endInfoFilled) return;
    endInfoFilled = true;
    if (info.eloDelta !== null && info.eloDelta !== undefined && info.myElo !== null) {
      const delta = info.eloDelta;
      const sign = delta > 0 ? '+' : '';
      endBody.appendChild(h('p', { class: 'm-line' }, 'Elo ' + info.myElo + ' (' + sign + delta + ')'));
    }
    if (info.reward !== null && info.reward > 0) {
      endBody.appendChild(h('p', { class: 'm-line' }, 'Награда +' + info.reward + ' ◈'));
    }
  }

  function showEnd(info) {
    if (endShown) return;
    if (info === null && gameOverInfo !== null) info = gameOverInfo;
    endShown = true;
    clearEndTimer();
    const aborted = state?.status === 'aborted';
    const res = state?.result;

    if (isSpectator()) {
      const body = h('div', { class: 'm-body' });
      let line = null;
      if (aborted) line = 'Партия отменена';
      else if (res === 'white') line = 'Победили белые';
      else if (res === 'black') line = 'Победили чёрные';
      else if (res === 'draw') line = 'Ничья';
      if (line) body.appendChild(h('p', { class: 'm-line' }, line));
      const reason = info?.end_reason ?? state?.end_reason ?? null;
      const reasonRu = reason === null ? null : (END_REASON_RU[reason] ?? reason);
      if (reasonRu) body.appendChild(h('p', { class: 'm-line' }, reasonRu));
      endBody = body;
      openModal({
        title: 'Партия завершена',
        titleAnim: 'none',
        dismissible: false,
        body,
        actions: [
          { label: 'В лобби', kind: 'ghost', onClick: () => { location.href = '/index.html'; } },
          { label: 'Новая партия', kind: 'gold', onClick: () => { location.href = '/index.html'; } },
        ],
      });
      return;
    }

    let title;
    let anim = 'none';
    if (aborted) title = 'Партия отменена';
    else if (res === 'draw') title = 'Ничья';
    else if (res === state?.you) {
      title = 'Победа';
      anim = 'pop';
    } else if (res !== null && res !== undefined) {
      title = 'Поражение';
      anim = 'shake';
    } else {
      title = 'Партия завершена';
    }

    const body = h('div', { class: 'm-body' });
    const reason = info?.end_reason ?? state?.end_reason ?? null;
    const reasonRu = reason === null ? null : (END_REASON_RU[reason] ?? reason);
    if (reasonRu) body.appendChild(h('p', { class: 'm-line' }, reasonRu));
    endBody = body;
    fillEndInfo(info);

    openModal({
      title,
      titleAnim: anim,
      dismissible: false,
      body,
      actions: [
        { label: 'В лобби', kind: 'ghost', onClick: () => { location.href = '/index.html'; } },
        { label: 'Новая партия', kind: 'gold', onClick: () => { location.href = '/index.html'; } },
      ],
    });
  }

  // ---- рендер ----
  function pieceAt(square) {
    for (const cell of state?.board ?? []) {
      if (cell.square === square) return cell;
    }
    return null;
  }

  function boardRender() {
    if (viewing !== null) {
      const lastAction = viewing.kind === 'move'
        ? { kind: 'move', ...viewing.payload }
        : (viewing.kind === 'dep' ? { kind: 'dep', ...viewing.payload } : null);
      boardApi.render(
        { ...state, board: viewing.board, check_square: viewing.check_square, last_action: lastAction },
        {},
      );
      return;
    }
    const opts = {};
    if (mode === 'idle' && selected !== null) {
      opts.selected = selected;
      opts.hints = [];
      opts.captures = [];
      for (const uci of state?.legal_moves ?? []) {
        if (uci.slice(0, 2) !== selected) continue;
        const to = uci.slice(2, 4);
        if (pieceAt(to)) opts.captures.push(to);
        else opts.hints.push(to);
      }
    }
    if (mode === 'dep_piece' && depOptions !== null) {
      opts.depPickable = depOptions.pieces.map((p) => p.square);
    }
    boardApi.render(state, opts);
  }

  function panelFor(color) {
    if (state === null) return null;
    const bottom = state.you === 'black' ? 'black' : 'white';
    return color === bottom ? youPanel : oppPanel;
  }

  function renderPanels() {
    if (state === null) return;
    for (const color of ['white', 'black']) {
      const panel = panelFor(color);
      if (panel === null) continue;
      const info = state.players?.[color];
      const loadout = info?.loadout ?? {};
      const king = panel.querySelector('.p-king');
      king.textContent = glyph('K', color);
      king.style.setProperty('--piece-color', pieceColor(loadout, 'K', color));
      panel.querySelector('.p-login').textContent = info?.login ?? '—';
      panel.querySelector('.p-elo').textContent = 'Elo ' + (info?.elo ?? '—');
      const used = color === 'white' ? state.deps.white_used : state.deps.black_used;
      panel.querySelector('.p-deps').textContent = 'депов ' + used + '/' + state.deps.limit;
    }
  }

  // Часы: локальный тик от момента получения состояния.
  function clockTick() {
    if (state === null) return;
    const clocks = state.clocks;
    const delta = performance.now() - receivedAt;
    for (const color of ['white', 'black']) {
      const panel = panelFor(color);
      if (panel === null) continue;
      const el = panel.querySelector('.p-clock');
      const running = clocks.running === color;
      let ms = color === 'white' ? clocks.white_ms : clocks.black_ms;
      if (running) ms -= delta;
      el.textContent = fmtClock(ms);
      panel.classList.toggle('is-turn', running);
      el.classList.toggle('is-low', running && ms < 10000);
    }
  }

  // ---- кнопки ----
  function myDepsUsed() {
    if (state === null) return 0;
    return state.you === 'white' ? state.deps.white_used : state.deps.black_used;
  }

  function depBlockedReason() {
    if (state === null) return 'GAME_NOT_ACTIVE';
    if (state.status !== 'active') return 'GAME_NOT_ACTIVE';
    if (state.turn !== state.you) return 'NOT_YOUR_TURN';
    if (state.deps.used_this_turn) return 'DEP_ALREADY_USED_THIS_TURN';
    if (myDepsUsed() >= state.deps.limit) return 'DEP_LIMIT_REACHED';
    return null;
  }

  function depClickable() {
    if (state === null || mode !== 'idle' || busy || fxRunning || forbidden) return false;
    return depBlockedReason() === null;
  }

  function actionClickable() {
    return state !== null && state.status === 'active' && !busy && !fxRunning && !forbidden;
  }

  function updateButtons() {
    const reason = depBlockedReason();
    const depOk = depClickable();
    btnDep.disabled = !depOk;
    if (reason !== null) btnDep.title = DEP_REASON_RU[reason] ?? reason;
    else btnDep.removeAttribute('title');
    depCountEl.textContent = state === null
      ? ''
      : ' · осталось ' + (state.deps.limit - myDepsUsed());
    const available = state !== null && state.status === 'active';
    btnDraw.disabled = !available || busy || fxRunning || forbidden
      || (state !== null && state.draw_offer_by === state.you);
    if (state !== null && state.draw_offer_by === state.you) btnDraw.textContent = 'Ничья предложена';
    else btnDraw.textContent = 'Предложить ничью';
    btnResign.disabled = !actionClickable();
    btnAbort.disabled = !actionClickable();
  }

  function onDepClick() {
    if (!depClickable()) {
      const reason = depBlockedReason();
      if (reason !== null && reason !== 'NOT_YOUR_TURN') toast(DEP_REASON_RU[reason] ?? reason, 'error');
      return;
    }
    busy = true;
    updateButtons();
    enqueue(async () => {
      try {
        const opts = await api('GET', '/games/' + id + '/dep-options');
        if (state !== null && opts.available === false) {
          toast(DEP_REASON_RU[opts.unavailable_reason] ?? 'Деп недоступен', 'error');
        } else if (state !== null) {
          depOptions = opts;
          depPiece = null;
          depTarget = null;
          mode = 'dep_piece';
          selected = null;
          depHint.hidden = false;
          renderDepPanel();
          boardRender();
        }
      } catch (e) {
        toast(e.message, 'error');
      } finally {
        busy = false;
        updateButtons();
      }
    });
  }

  function cancelDep() {
    mode = 'idle';
    depOptions = null;
    depPiece = null;
    depTarget = null;
    depHint.hidden = true;
    renderDepPanel();
    boardRender();
    updateButtons();
  }

  function chooseDepPiece(square) {
    depPiece = depOptions.pieces.find((p) => p.square === square) ?? null;
    if (depPiece === null) {
      cancelDep();
      return;
    }
    mode = 'dep_target';
    depHint.hidden = true;
    renderDepPanel();
    boardRender();
  }

  function renderDepPanel() {
    clear(depPanel);
    if (mode === 'dep_target' && depPiece !== null) {
      depPanel.hidden = false;
      const title = h('h4', { class: 'card-title' },
        glyph(depPiece.piece, state.you) + ' ' + PIECE_NAME_RU[depPiece.piece] + ' ' + depPiece.square + ' → во что?');
      depPanel.appendChild(title);
      for (const target of depPiece.targets) {
        const row = h('button', { type: 'button', class: 'dep-row' });
        const g = h('span', { class: 'dep-row-glyph ' + (state.you === 'white' ? 'side-white' : 'side-black') }, glyph(target.piece, state.you));
        g.style.setProperty('--piece-color', pieceColor(state.players[state.you].loadout, target.piece, state.you));
        row.appendChild(g);
        row.appendChild(h('b', { class: 'dep-row-name' }, PIECE_NAME_RU[target.piece]));
        if (target.allowed) {
          row.appendChild(h('span', { class: 'dep-row-chance mono' }, 'шанс ' + target.chance_text));
        } else {
          row.disabled = true;
          row.appendChild(h('small', { class: 'dep-row-note' }, DEP_REASON_RU[target.reason] ?? target.reason ?? 'недоступно'));
        }
        row.addEventListener('click', () => {
          if (!target.allowed) return;
          depTarget = target;
          mode = 'dep_confirm';
          renderDepPanel();
        });
        depPanel.appendChild(row);
      }
      depPanel.appendChild(makePanelBtns(
        { label: 'Отмена', kind: 'ghost', onClick: () => cancelDep() },
      ));
    } else if (mode === 'dep_confirm' && depPiece !== null && depTarget !== null) {
      depPanel.hidden = false;
      depPanel.appendChild(h('h4', { class: 'card-title' }, 'Подтверждение депа'));
      depPanel.appendChild(h('p', { class: 'dep-summary' },
        (PIECE_NAME_RU[depPiece.piece] ?? depPiece.piece) + ' → ' + (PIECE_NAME_RU[depTarget.piece] ?? depTarget.piece)
        + ' · шанс ' + depTarget.chance_text + ' · при провале фигура сгорит'));
      depPanel.appendChild(makePanelBtns(
        { label: 'Депнуть', kind: 'gold', onClick: () => sendDep() },
        { label: 'Назад', kind: 'ghost', onClick: () => {
          mode = 'dep_target';
          depTarget = null;
          renderDepPanel();
        } },
      ));
    } else {
      depPanel.hidden = true;
    }
  }

  function makePanelBtns(...buttons) {
    const row = h('div', { class: 'dep-btnrow' });
    for (const b of buttons) {
      const el = h('button', { type: 'button', class: 'btn btn-' + b.kind + ' btn-block' }, b.label);
      el.addEventListener('click', () => {
        const proceed = b.onClick ? b.onClick() : undefined;
        if (proceed === false) return;
      });
      row.appendChild(el);
    }
    return row;
  }

  function sendDep() {
    if (depPiece === null || depTarget === null || !state || state.status !== 'active') return;
    const square = depPiece.square;
    const target = depTarget.piece;
    cancelDep();
    busy = true;
    fxRunning = true;
    updateButtons();
    enqueue(async () => {
      try {
        const res = await api('POST', '/games/' + id + '/dep', {
          square,
          target,
          expected_version: state.version,
        });
        await playDep(boardApi, res, { mine: true });
        applyState(res.state);
      } catch (e) {
        toast(e.message, 'error');
        if (e.code === 'VERSION_CONFLICT') await refreshState();
      } finally {
        fxRunning = false;
        busy = false;
        updateButtons();
      }
    });
  }

  // ---- клики по доске ----
  function interactionAllowed() {
    if (state === null || forbidden) return false;
    if (state.status !== 'active') return false;
    if (state.turn !== state.you) return false;
    if (busy || fxRunning) return false;
    return true;
  }

  function onSquareClick(name) {
    if (viewing !== null) return;
    if (isSpectator()) return;
    if (mode === 'dep_piece') {
      if (depOptions !== null && depOptions.pieces.some((p) => p.square === name)) {
        chooseDepPiece(name);
      } else {
        cancelDep();
      }
      return;
    }
    if (mode !== 'idle') return;
    if (!interactionAllowed()) return;
    const cell = pieceAt(name);
    if (selected !== null) {
      const matches = (state.legal_moves ?? []).filter((uci) => uci.slice(0, 2) === selected && uci.slice(2, 4) === name);
      if (matches.length > 0) {
        if (matches.some((uci) => uci.length > 4)) openPromotion(matches);
        else sendMove(selected + name);
        return;
      }
    }
    if (cell !== null && cell.color === state.you) {
      selected = selected === name ? null : name;
      boardRender();
    } else {
      selected = null;
      boardRender();
    }
  }

  function openPromotion(matches) {
    const body = h('div', { class: 'promo-row' });
    for (const suffix of ['q', 'r', 'b', 'n']) {
      const uci = matches.find((m) => m[4] === suffix);
      if (uci === undefined) continue;
      const upper = suffix.toUpperCase();
      const btn = h('button', { type: 'button', class: 'promo-btn', title: PIECE_NAME_RU[upper] });
      const g = h('span', { class: 'glyph ' + (state.you === 'white' ? 'side-white' : 'side-black') }, glyph(upper, state.you));
      g.style.setProperty('--piece-color', pieceColor(state.players[state.you].loadout, upper, state.you));
      btn.appendChild(g);
      btn.appendChild(h('span', { class: 'promo-name' }, PIECE_NAME_RU[upper]));
      btn.addEventListener('click', () => {
        closePromo();
        sendMove(uci);
      });
      body.appendChild(btn);
    }
    const closePromo = openModal({ title: 'Превращение пешки', titleAnim: 'none', body, dismissible: true });
  }

  function sendMove(uci) {
    if (!state || state.status !== 'active') return;
    selected = null;
    busy = true;
    boardRender();
    updateButtons();
    enqueue(async () => {
      try {
        const res = await api('POST', '/games/' + id + '/move', { uci, expected_version: state.version });
        applyState(res);
      } catch (e) {
        toast(e.message, 'error');
        if (e.code === 'VERSION_CONFLICT' || e.code === 'TIME_EXPIRED') await refreshState();
      } finally {
        busy = false;
        updateButtons();
      }
    });
  }

  async function refreshState() {
    try {
      applyState(await api('GET', '/games/' + id));
    } catch {
      /* состояние придёт по WS */
    }
  }

  async function gameAction(pathSuffix) {
    if (!actionClickable()) return;
    if (pathSuffix === '/draw/offer' && state !== null && state.draw_offer_by === state.you) return;
    busy = true;
    updateButtons();
    enqueue(async () => {
      try {
        const res = await api('POST', '/games/' + id + pathSuffix, { expected_version: state.version });
        applyState(res);
      } catch (e) {
        toast(e.message, 'error');
        if (e.code === 'VERSION_CONFLICT') await refreshState();
      } finally {
        busy = false;
        updateButtons();
      }
    });
  }

  async function onResign() {
    if (!actionClickable()) return;
    const ok = await confirmModal('Сдаться?', 'Партия будет засчитана как поражение.', 'Сдаться', 'danger');
    if (!ok) return;
    busy = true;
    updateButtons();
    enqueue(async () => {
      try {
        const res = await api('POST', '/games/' + id + '/resign', { expected_version: state.version });
        applyState(res);
      } catch (e) {
        toast(e.message, 'error');
        if (e.code === 'VERSION_CONFLICT') await refreshState();
      } finally {
        busy = false;
        updateButtons();
      }
    });
  }

  // ---- история ходов: просмотр позиции ----
  function viewEvent(ev) {
    if (state === null || ev === null || typeof ev !== 'object' || typeof ev.seq !== 'number') return;
    viewing = ev;
    moves.select(ev.seq);
    viewBannerText.textContent = 'Просмотр позиции · ход ' + (Math.floor((ev.ply - 1) / 2) + 1);
    viewBanner.hidden = false;
    boardRender();
  }

  function exitView() {
    if (viewing === null) return;
    viewing = null;
    moves.select(null);
    viewBanner.hidden = true;
    boardRender();
  }

  async function loadEvents(after) {
    const path = after
      ? '/games/' + id + '/events?after_seq=' + moves.lastSeq()
      : '/games/' + id + '/events';
    try {
      const res = await api('GET', path);
      if (after) moves.appendEvents(res.events);
      else moves.setEvents(res.events);
    } catch (e) {
      console.error(e);
    }
  }

  // ---- WS ----
  function onMessage(msg) {
    if (msg.type === 'state') {
      enqueue(() => applyState(msg.data));
    } else if (msg.type === 'dep') {
      const data = msg.data;
      if (data && data.by !== (state?.you ?? null)) {
        fxRunning = true;
        updateButtons();
        enqueue(async () => {
          try {
            await playDep(boardApi, data, { mine: false });
          } finally {
            fxRunning = false;
            updateButtons();
          }
        });
      }
    } else if (msg.type === 'game_over') {
      enqueue(() => rememberGameOver(msg.data));
    } else if (msg.type === 'chat') {
      chat.onWsChat(msg.data);
    }
  }

  function onStatus(status) {
    if (status === 'online') {
      forbidden = false;
      connIndicator.hidden = true;
      updateButtons();
    } else if (status === 'reconnecting') {
      connIndicator.hidden = false;
      connIndicator.textContent = 'Соединение потеряно, переподключаемся…';
    } else if (status === 'forbidden') {
      forbidden = true;
      connIndicator.hidden = false;
      connIndicator.textContent = 'Нет доступа к партии.';
      updateButtons();
    }
  }

  // ---- запуск ----
  setInterval(() => clockTick(), 100);

  try {
    applyState(await api('GET', '/games/' + id));
  } catch (e) {
    const noGame = h('div', { class: 'card center-note' },
      h('p', {}, e.message || 'Партия недоступна.'),
      h('a', { href: '/index.html', class: 'btn btn-gold' }, 'В лобби'),
    );
    gameMain.prepend(noGame);
    return;
  }

  chat.load();
  connectGame(id, { onMessage, onStatus });
}
