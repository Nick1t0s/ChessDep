import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { toast } from './toast.js';

const me = await initLayout({ auth: 'required', active: 'play' });

const main = h('main', { class: 'wrap-wide lobby' });

// 1. Активная партия
const goBackActive = h('a', { href: '/index.html', class: 'btn btn-gold btn-block' }, 'Вернуться');
const activeCard = h('div', { class: 'card game-card', hidden: true },
  h('h3', { class: 'card-title' }, 'У вас идёт партия'),
  h('p', { class: 'note' }, 'Вернитесь на доску, чтобы продолжить.'),
  goBackActive,
);

// 2. Играть онлайн
const tcRow = h('div', { class: 'tc-grid' });
const searchLine = h('div', { class: 'search-state mono' });
const cancelSearch = h('button', { type: 'button', class: 'btn btn-ghost btn-block' }, 'Отмена');
const searchBox = h('div', { class: 'search-box', hidden: true }, searchLine, cancelSearch);
const playCard = h('div', { class: 'card lobby-card' },
  h('h3', { class: 'card-title' }, 'Играть онлайн'),
  tcRow,
  searchBox,
);

// 3. Сыграть с другом
const friendControls = h('div', { class: 'tc-grid' });
const friendStates = h('div', { class: 'friend-box' });
const friendCard = h('div', { class: 'card lobby-card' },
  h('h3', { class: 'card-title' }, 'Сыграть с другом'),
  friendControls,
  friendStates,
);

// 4. Ежедневный бонус
const dailyBtn = h('button', { type: 'button', class: 'btn btn-gold btn-block' }, 'Забрать ежедневный бонус');
const dailyCard = h('div', { class: 'card lobby-card' },
  h('h3', { class: 'card-title' }, 'Ежедневный бонус'),
  dailyBtn,
);

main.append(activeCard, playCard, friendCard, dailyCard);
document.body.appendChild(main);

// ---------- helpers ----------
function fmtRemaining(msLeft) {
  if (msLeft <= 0) return 'меньше минуты';
  const totalMin = Math.ceil(msLeft / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours > 0) return String(hours) + ' ч ' + String(mins) + ' мин';
  return String(mins) + ' мин';
}

function fmtElapsed(totalSec) {
  const m = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return String(m) + ':' + String(sec).padStart(2, '0');
}

// ---------- 1. активная партия ----------
const activeGame = await api('GET', '/me/active-game').catch(() => null);
if (activeGame?.game_id) {
  goBackActive.setAttribute('href', '/game.html?id=' + encodeURIComponent(activeGame.game_id));
  activeCard.hidden = false;
  tcRow.hidden = true;
  friendControls.hidden = true;
} else {
  initPlayOnline();
  initFriend();
}

// ---------- 2. играть онлайн ----------
let searchTc = '';
let searchStartedAt = 0;
let searchTimer = null;

function searching() {
  return searchTimer !== null;
}

function stopSearch(pollCancelToast) {
  if (searchTimer === null) return;
  clearInterval(searchTimer);
  searchTimer = null;
  tcRow.hidden = activeGame?.game_id !== null;
  searchBox.hidden = true;
  window.removeEventListener('pagehide', leaveQueue);
  if (pollCancelToast) toast('Поиск отменён', 'info');
}

async function leaveQueue() {
  try {
    await fetch('/api/v1/matchmaking/queue', {
      method: 'DELETE',
      credentials: 'same-origin',
      keepalive: true,
    });
  } catch {
    /* страница закрывается */
  }
}

function enterSearch(tc) {
  if (searchTimer !== null) return;
  searchTc = tc;
  searchStartedAt = Date.now();
  tcRow.hidden = true;
  searchBox.hidden = false;
  searchTimer = setInterval(async () => {
    clear(searchLine);
    searchLine.append(
      'Ищем соперника · ' + searchTc + ' · ' + fmtElapsed(Math.floor((Date.now() - searchStartedAt) / 1000)),
    );
    try {
      const status = await api('GET', '/matchmaking/status');
      if (status.status === 'matched' && status.game_id) {
        location.href = '/game.html?id=' + encodeURIComponent(status.game_id);
      } else if (status.status === 'idle') {
        stopSearch(true);
      }
    } catch {
      /* сеть моргнула — продолжим на следующем тике */
    }
  }, 1000);
}

cancelSearch.addEventListener('click', async () => {
  stopSearch(false);
  await leaveQueue();
  toast('Поиск отменён', 'info');
});

window.addEventListener('pagehide', () => {
  if (searching()) leaveQueue();
});

async function initPlayOnline() {
  const config = await api('GET', '/config');
  for (const tc of config.time_controls ?? []) {
    const btn = h('button', { type: 'button', class: 'btn btn-ghost btn-tc' }, tc);
    btn.addEventListener('click', async () => {
      try {
        await api('POST', '/matchmaking/queue', { time_control: tc });
        enterSearch(tc);
      } catch (e) {
        if (e.code === 'ALREADY_IN_GAME') {
          const active = await api('GET', '/me/active-game');
          if (active?.game_id) location.href = '/game.html?id=' + encodeURIComponent(active.game_id);
        } else {
          toast(e.message, 'error');
        }
      }
    });
    tcRow.appendChild(btn);
  }

  // Обновили страницу во время поиска — сразу вернуть режим поиска.
  try {
    const status = await api('GET', '/matchmaking/status');
    if (status.status === 'queued') enterSearch(status.time_control);
    else if (status.status === 'matched' && status.game_id) {
      location.href = '/game.html?id=' + encodeURIComponent(status.game_id);
    }
  } catch {
    /* просто не показываем поиск */
  }
}

// ---------- 3. сыграть с другом ----------
let friendPoll = null;
let inviteCountdown = null;

async function initFriend() {
  const config = await api('GET', '/config');
  for (const tc of config.time_controls ?? []) {
    const btn = h('button', { type: 'button', class: 'btn btn-ghost btn-tc' }, tc);
    btn.addEventListener('click', async () => {
      try {
        const invite = await api('POST', '/invites', { time_control: tc });
        renderFriendInvite(invite);
      } catch (e) {
        toast(e.message, 'error');
      }
    });
    friendControls.appendChild(btn);
  }
}

function stopFriendTimers() {
  if (friendPoll !== null) {
    clearInterval(friendPoll);
    friendPoll = null;
  }
  if (inviteCountdown !== null) {
    clearInterval(inviteCountdown);
    inviteCountdown = null;
  }
}

function renderFriendIdle(message) {
  stopFriendTimers();
  clear(friendStates);
  friendControls.hidden = activeGame?.game_id !== null;
  if (message) friendStates.append(h('p', { class: 'note' }, message));
}

function renderFriendInvite(invite) {
  stopFriendTimers();
  clear(friendStates);
  friendControls.hidden = true;
  const link = location.origin + '/invite.html?code=' + encodeURIComponent(invite.code);
  const field = h('input', { class: 'invite-link mono', readonly: 'true', 'aria-label': 'Ссылка-приглашение', value: link });
  const copy = h('button', { type: 'button', class: 'btn btn-ghost' }, 'Копировать');
  const countdown = h('span', { class: 'mono invite-countdown' }, '');
  const cancel = h('button', { type: 'button', class: 'btn btn-ghost' }, 'Отменить');

  copy.addEventListener('click', async () => {
    if (navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(link);
        toast('Скопировано', 'success');
        return;
      } catch {
        /* clipboard недоступен */
      }
    }
    field.focus();
    field.select();
    toast('Скопируйте ссылку вручную', 'info');
  });

  cancel.addEventListener('click', async () => {
    try {
      await api('DELETE', '/invites/' + encodeURIComponent(invite.code));
    } catch (e) {
      toast(e.message, 'error');
    }
    renderFriendIdle();
  });

  friendPoll = setInterval(async () => {
    try {
      const active = await api('GET', '/me/active-game');
      if (active?.game_id) {
        stopFriendTimers();
        location.href = '/game.html?id=' + encodeURIComponent(active.game_id);
      }
    } catch {
      /* продолжаем поллинг */
    }
  }, 2000);

  const expires = Date.parse(invite.expires_at);
  inviteCountdown = setInterval(() => {
    const left = expires - Date.now();
    if (left <= 0) {
      renderFriendIdle('Приглашение истекло');
      return;
    }
    countdown.textContent = 'истекает через ' + fmtRemaining(left);
  }, 1000);

  friendStates.append(
    h('p', { class: 'note' }, 'Отправьте другу ссылку:'),
    h('div', { class: 'invite-row' }, field, copy),
    h('div', { class: 'invite-meta' }, countdown, cancel),
  );
}

// ---------- 4. ежедневный бонус ----------
let bonusTimer = null;

function renderDaily(meNow) {
  const availableAt = meNow?.daily_bonus_available_at ?? null;
  if (availableAt === null) {
    if (bonusTimer !== null) {
      clearInterval(bonusTimer);
      bonusTimer = null;
    }
    dailyBtn.disabled = false;
    dailyBtn.textContent = 'Забрать ежедневный бонус';
    return;
  }
  const deadline = Date.parse(availableAt);
  const tick = () => {
    dailyBtn.disabled = deadline > Date.now();
    dailyBtn.textContent = 'Следующий бонус через ' + fmtRemaining(deadline - Date.now());
  };
  tick();
  if (bonusTimer === null) bonusTimer = setInterval(tick, 60000);
}

dailyBtn.addEventListener('click', async () => {
  try {
    const out = await api('POST', '/me/daily-bonus');
    setBalance(out.balance);
    renderDaily({ daily_bonus_available_at: out.next_available_at });
    toast('Бонус получен', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
});

renderDaily({ daily_bonus_available_at: me?.daily_bonus_available_at ?? null });
