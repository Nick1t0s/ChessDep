import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { fmtCrystals, END_REASON_RU } from './format.js';

const me = await initLayout({ auth: 'required', active: 'profile' });

const main = h('main', { class: 'wrap-wide profile' });
document.body.appendChild(main);

const REASON_RU = {
  signup_bonus: 'Бонус за регистрацию',
  daily_bonus: 'Ежедневный бонус',
  game_win: 'Победа в партии',
  game_draw: 'Ничья в партии',
  case_purchase: 'Покупка кейса',
  admin_adjust: 'Корректировка администратором',
  market_buy: 'Покупка на маркете',
  market_sale: 'Продажа на маркете',
};

// ---------- 1. Профиль ----------
const profileCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Профиль'),
  h('p', { class: 'pf-row' }, h('span', null, 'Логин'), h('b', null, me.login)),
  h('p', { class: 'pf-row' }, h('span', null, 'Elo'), h('b', null, String(me.elo))),
  h('p', { class: 'pf-row' }, h('span', null, 'Баланс'), h('b', null, fmtCrystals(me.balance))),
  h('p', { class: 'pf-row' }, h('span', null, 'Роль'), h('b', null, me.role === 'admin' ? 'Администратор' : 'Игрок')),
  h('button', {
    type: 'button',
    class: 'btn btn-ghost',
    onClick: () => {
      logout().catch((e) => toast(e.message, 'error'));
    },
  }, 'Выйти'),
);

async function logout() {
  await api('POST', '/auth/logout');
  location.href = '/login.html';
}

// ---------- 2. Смена пароля ----------
const oldInput = h('input', { type: 'password', id: 'pf-old-pass', name: 'old_password', autocomplete: 'current-password', required: true });
const newInput = h('input', { type: 'password', id: 'pf-new-pass', name: 'new_password', autocomplete: 'new-password', minlength: 8, maxlength: 128, required: true });
const passwordForm = h('form', { class: 'pf-form' },
  h('div', { class: 'field' }, h('label', { for: 'pf-old-pass' }, 'Текущий пароль'), oldInput),
  h('div', { class: 'field' }, h('label', { for: 'pf-new-pass' }, 'Новый пароль'), newInput),
  h('button', { type: 'submit', class: 'btn btn-gold' }, 'Сменить'),
);

passwordForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const newPassword = newInput.value;
  if (newPassword.length < 8) {
    toast('Новый пароль должен быть не короче 8 символов', 'error');
    return;
  }
  const changeBtn = passwordForm.querySelector('button[type=submit]');
  changeBtn.disabled = true;
  try {
    await api('POST', '/me/password', { old_password: oldInput.value, new_password: newPassword });
    toast('Пароль изменён', 'success');
    oldInput.value = '';
    newInput.value = '';
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    changeBtn.disabled = false;
  }
});

const passwordCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Смена пароля'),
  passwordForm,
);

// ---------- 3. Партии ----------
const gamesBody = h('tbody');
const gamesMoreBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', hidden: true }, 'Ещё');
const gamesCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Партии'),
  h('div', { class: 'table-wrap' },
    h('table', { class: 'pf-table' },
      h('thead', null, h('tr', null,
        h('th', null, 'Дата'),
        h('th', null, 'Соперник'),
        h('th', null, 'Цвет'),
        h('th', null, 'Результат'),
        h('th', null, 'Причина'),
        h('th', null, 'Контроль'),
        h('th', null, 'Elo'),
      )),
      gamesBody,
    ),
  ),
  gamesMoreBtn,
);

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
    h('td', null, game.opponent_login),
    h('td', null, game.color === 'white' ? 'Белые' : 'Чёрные'),
    h('td', null, result),
    h('td', null, END_REASON_RU[game.end_reason] ?? ''),
    h('td', null, game.time_control),
    h('td', null, elo),
  );
}

async function loadGames() {
  const params = new URLSearchParams({ limit: '20' });
  if (nextBefore !== null) params.set('before', nextBefore);
  const page = await api('GET', '/me/games?' + params.toString());
  for (const game of page.items) gamesBody.appendChild(gameRow(game));
  if (page.items.length === 0 && gamesBody.children.length === 0) {
    gamesBody.appendChild(h('tr', null, h('td', null, 'Партий ещё не было'), h('td', null, ''), h('td', null, ''), h('td', null, ''), h('td', null, ''), h('td', null, ''), h('td', null, '')));
  }
  nextBefore = page.next_before;
  gamesMoreBtn.hidden = nextBefore === null;
}

gamesMoreBtn.addEventListener('click', () => {
  loadGames().catch((e) => toast(e.message, 'error'));
});

// ---------- 4. Операции ----------
const ledgerBody = h('tbody');
const ledgerMoreBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', hidden: true }, 'Ещё');
const ledgerCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Операции'),
  h('div', { class: 'table-wrap' },
    h('table', { class: 'pf-table' },
      h('thead', null, h('tr', null,
        h('th', null, 'Дата'),
        h('th', null, 'Операция'),
        h('th', null, 'Сумма'),
        h('th', null, 'Баланс'),
      )),
      ledgerBody,
    ),
  ),
  ledgerMoreBtn,
);

let nextCursor = null;

function ledgerRow(entry) {
  const amount = (entry.delta > 0 ? '+' : '') + String(entry.delta) + ' ◈';
  return h('tr', null,
    h('td', null, new Date(entry.created_at).toLocaleString('ru-RU')),
    h('td', null, REASON_RU[entry.reason] ?? entry.reason),
    h('td', { class: entry.delta > 0 ? 'pos' : 'neg' }, amount),
    h('td', null, fmtCrystals(entry.balance_after)),
  );
}

async function loadLedger() {
  const params = new URLSearchParams({ limit: '20' });
  if (nextCursor !== null) params.set('cursor', String(nextCursor));
  const page = await api('GET', '/me/ledger?' + params.toString());
  for (const entry of page.items) ledgerBody.appendChild(ledgerRow(entry));
  nextCursor = page.next_cursor;
  ledgerMoreBtn.hidden = nextCursor === null;
}

ledgerMoreBtn.addEventListener('click', () => {
  loadLedger().catch((e) => toast(e.message, 'error'));
});

main.append(profileCard, passwordCard, gamesCard, ledgerCard);

loadGames().catch((e) => toast(e.message, 'error'));
loadLedger().catch((e) => toast(e.message, 'error'));
