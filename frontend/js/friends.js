import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';

await initLayout({ auth: 'required', active: 'friends' });

const main = h('main', { class: 'wrap-wide social-page friends-page' });
document.body.appendChild(main);

// Header with link to Settings
main.appendChild(
  h(
    'div',
    { class: 'page-header friends-header' },
    h(
      'div',
      { class: 'friends-header-main' },
      h('h1', { class: 'page-title' }, 'Друзья'),
      h('p', { class: 'page-subtitle' }, 'Играйте в шахматы и соревнуйтесь с друзьями'),
    ),
    h(
      'a',
      { class: 'btn btn-ghost btn-sm', href: '/social-settings.html' },
      'Настройки общения',
    ),
  ),
);

// Search box
const searchInput = h('input', {
  type: 'text',
  class: 'social-search input',
  placeholder: 'Поиск игроков по нику (от 2 символов)...',
  'aria-label': 'Поиск игроков по нику',
  autocomplete: 'off',
  maxlength: '64',
});

const searchClearBtn = h(
  'button',
  {
    type: 'button',
    class: 'btn btn-ghost btn-sm',
    title: 'Очистить поиск',
    'aria-label': 'Очистить поиск',
    hidden: true,
  },
  '✕',
);

const searchWrap = h('div', { class: 'social-search-box' }, searchInput, searchClearBtn);
main.appendChild(searchWrap);

// Navigation tabs
const tabsNav = h('div', { class: 'sc-tabs' });
const TAB_FRIENDS = 'friends';
const TAB_INCOMING = 'incoming';
const TAB_OUTGOING = 'outgoing';
const TAB_SEARCH = 'search';

let currentTab = TAB_FRIENDS;
const tabButtons = {};

for (const [id, label] of [
  [TAB_FRIENDS, 'Мои друзья'],
  [TAB_INCOMING, 'Входящие заявки'],
  [TAB_OUTGOING, 'Исходящие'],
  [TAB_SEARCH, 'Результаты поиска'],
]) {
  const btn = h('button', { type: 'button', class: 'btn btn-ghost' }, label);
  btn.addEventListener('click', () => switchTab(id));
  if (id === TAB_SEARCH) btn.setAttribute('hidden', 'hidden');
  tabsNav.appendChild(btn);
  tabButtons[id] = btn;
}
main.appendChild(tabsNav);

// Container for content
const contentContainer = h('div', { class: 'social-content' });
main.appendChild(contentContainer);

// State
let friendsList = [];
let incomingList = [];
let outgoingList = [];
let searchResults = [];
let searchLoading = false;
let pageLoading = false;
let initialLoadError = false;
let searchTimer = null;
let searchSeq = 0;
const busyActions = new Set();
let socialPollTimer = null;
let socialInFlight = false;

const STATUS_CONFIG = {
  online: { label: 'В сети', cls: 'status-online' },
  dnd: { label: 'Не беспокоить', cls: 'status-dnd' },
  in_game: { label: 'В игре', cls: 'status-in_game' },
  offline: { label: 'Не в сети', cls: 'status-offline' },
};

function setTab(tabId) {
  currentTab = tabId;
  for (const [id, btn] of Object.entries(tabButtons)) {
    btn.className = 'btn ' + (id === currentTab ? 'btn-gold' : 'btn-ghost');
  }
}

function updateTabLabels() {
  tabButtons[TAB_FRIENDS].textContent = `Мои друзья (${friendsList.length})`;
  tabButtons[TAB_INCOMING].textContent =
    incomingList.length > 0 ? `Входящие заявки (${incomingList.length})` : 'Входящие заявки';
  tabButtons[TAB_OUTGOING].textContent =
    outgoingList.length > 0 ? `Исходящие (${outgoingList.length})` : 'Исходящие';
}

function switchTab(tabId) {
  setTab(tabId);
  renderContent();
}

async function loadSocialData() {
  pageLoading = true;
  renderLoading();
  try {
    const [friendsRes, requestsRes] = await Promise.all([
      api('GET', '/friends'),
      api('GET', '/friends/requests'),
    ]);
    friendsList = (friendsRes && friendsRes.items) || [];
    incomingList = (requestsRes && requestsRes.incoming) || [];
    outgoingList = (requestsRes && requestsRes.outgoing) || [];
    initialLoadError = false;
    updateTabLabels();
  } catch (err) {
    initialLoadError = true;
    toast((err && err.message) || 'Ошибка загрузки друзей', 'error');
  } finally {
    pageLoading = false;
    renderContent();
  }
}

async function refreshSocialDataQuietly() {
  if (socialInFlight || pageLoading) return;
  if (document.visibilityState !== 'visible') return;
  socialInFlight = true;
  try {
    const [friendsRes, requestsRes] = await Promise.all([
      api('GET', '/friends', undefined, { redirectOn401: false }),
      api('GET', '/friends/requests', undefined, { redirectOn401: false }),
    ]);
    friendsList = (friendsRes && friendsRes.items) || [];
    incomingList = (requestsRes && requestsRes.incoming) || [];
    outgoingList = (requestsRes && requestsRes.outgoing) || [];
    initialLoadError = false;
    updateTabLabels();
    if (currentTab !== TAB_SEARCH) {
      renderContent();
    }
  } catch {
    /* Фоновое обновление тихо пропускает сетевые сбои */
  } finally {
    socialInFlight = false;
  }
}

function renderLoading() {
  clear(contentContainer);
  contentContainer.appendChild(h('div', { class: 'social-loading' }, 'Загрузка...'));
}

function renderContent() {
  clear(contentContainer);

  if (pageLoading) {
    contentContainer.appendChild(h('div', { class: 'social-loading' }, 'Загрузка...'));
    return;
  }

  if (currentTab === TAB_SEARCH) {
    renderSearchResults();
    return;
  }

  if (currentTab === TAB_FRIENDS) {
    renderFriendsList();
  } else if (currentTab === TAB_INCOMING) {
    renderIncomingRequests();
  } else if (currentTab === TAB_OUTGOING) {
    renderOutgoingRequests();
  }
}

function renderFriendsList() {
  if (initialLoadError && friendsList.length === 0) {
    const errCard = h(
      'div',
      { class: 'social-empty card social-error' },
      h('p', { class: 'social-empty-title' }, 'Не удалось загрузить друзей'),
      h('p', { class: 'social-empty-sub' }, 'Проверьте соединение с сервером и повторите попытку.'),
    );
    const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
    retryBtn.addEventListener('click', () => loadSocialData());
    errCard.appendChild(retryBtn);
    contentContainer.appendChild(errCard);
    return;
  }

  if (friendsList.length === 0) {
    contentContainer.appendChild(
      h(
        'div',
        { class: 'social-empty card' },
        h('p', { class: 'social-empty-title' }, 'У вас пока нет друзей'),
        h('p', { class: 'social-empty-sub' }, 'Найдите других игроков по нику через форму поиска выше.'),
      ),
    );
    return;
  }

  const list = h('div', { class: 'social-list' });
  for (const friend of friendsList) {
    const presKey = friend.presence || 'offline';
    const presMeta = STATUS_CONFIG[presKey] || STATUS_CONFIG.offline;

    const personInfo = h(
      'div',
      { class: 'social-person-info' },
      h(
        'a',
        { class: 'social-person-name', href: `/user.html?login=${encodeURIComponent(friend.login)}` },
        friend.login,
      ),
      h('span', { class: 'social-person-elo pill' }, `${friend.elo ?? 1200} Elo`),
      h('span', { class: 'pill social-status-pill ' + presMeta.cls }, presMeta.label),
    );

    const actions = h('div', { class: 'social-actions' });

    // Review fix 3: Watch button appears if game_id exists even if presence is dnd
    if (friend.game_id) {
      actions.appendChild(
        h(
          'a',
          {
            class: 'btn btn-ghost btn-sm',
            href: `/game.html?id=${encodeURIComponent(friend.game_id)}`,
            title: 'Смотреть партию',
          },
          'Смотреть',
        ),
      );
    }

    // Invite to game button: disabled for dnd and in_game
    if (presKey === 'dnd') {
      actions.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'btn btn-gold btn-sm',
            disabled: true,
            title: 'друзья видят Не беспокоить; прямые приглашения отключены',
          },
          'Позвать в игру',
        ),
      );
    } else if (presKey === 'in_game') {
      actions.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'btn btn-gold btn-sm',
            disabled: true,
            title: 'Игрок уже участвует в партии',
          },
          'Позвать в игру',
        ),
      );
    } else {
      actions.appendChild(
        h(
          'a',
          {
            class: 'btn btn-gold btn-sm',
            href: `/index.html?friend=${encodeURIComponent(friend.id)}`,
            title: 'Создать партию с другом',
          },
          'Позвать в игру',
        ),
      );
    }

    actions.appendChild(
      createActionButton('Удалить', 'btn-ghost', () => removeFriend(friend.id, friend.login)),
    );
    actions.appendChild(
      createActionButton('Заблокировать', 'btn-ghost', () => blockFriend(friend.id, friend.login)),
    );

    const item = h('div', { class: 'social-person card' }, personInfo, actions);
    list.appendChild(item);
  }
  contentContainer.appendChild(list);
}

function renderIncomingRequests() {
  if (initialLoadError && incomingList.length === 0) {
    const errCard = h(
      'div',
      { class: 'social-empty card social-error' },
      h('p', { class: 'social-empty-title' }, 'Ошибка загрузки входящих заявок'),
    );
    const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
    retryBtn.addEventListener('click', () => loadSocialData());
    errCard.appendChild(retryBtn);
    contentContainer.appendChild(errCard);
    return;
  }

  if (incomingList.length === 0) {
    contentContainer.appendChild(
      h(
        'div',
        { class: 'social-empty card' },
        h('p', { class: 'social-empty-title' }, 'Нет входящих заявок в друзья'),
      ),
    );
    return;
  }

  const list = h('div', { class: 'social-list' });
  for (const req of incomingList) {
    const item = h(
      'div',
      { class: 'social-person card' },
      h(
        'div',
        { class: 'social-person-info' },
        h(
          'a',
          { class: 'social-person-name', href: `/user.html?login=${encodeURIComponent(req.login)}` },
          req.login,
        ),
        h('span', { class: 'social-person-elo pill' }, `${req.elo ?? 1200} Elo`),
      ),
      h(
        'div',
        { class: 'social-actions' },
        createActionButton('Принять', 'btn-gold', () => acceptRequest(req.id, req.login)),
        createActionButton('Отклонить', 'btn-ghost', () => rejectRequest(req.id, req.login)),
        createActionButton('Заблокировать', 'btn-ghost', () => blockFriend(req.id, req.login)),
      ),
    );
    list.appendChild(item);
  }
  contentContainer.appendChild(list);
}

function renderOutgoingRequests() {
  if (initialLoadError && outgoingList.length === 0) {
    const errCard = h(
      'div',
      { class: 'social-empty card social-error' },
      h('p', { class: 'social-empty-title' }, 'Ошибка загрузки исходящих заявок'),
    );
    const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
    retryBtn.addEventListener('click', () => loadSocialData());
    errCard.appendChild(retryBtn);
    contentContainer.appendChild(errCard);
    return;
  }

  if (outgoingList.length === 0) {
    contentContainer.appendChild(
      h(
        'div',
        { class: 'social-empty card' },
        h('p', { class: 'social-empty-title' }, 'Нет исходящих заявок'),
      ),
    );
    return;
  }

  const list = h('div', { class: 'social-list' });
  for (const req of outgoingList) {
    const item = h(
      'div',
      { class: 'social-person card' },
      h(
        'div',
        { class: 'social-person-info' },
        h(
          'a',
          { class: 'social-person-name', href: `/user.html?login=${encodeURIComponent(req.login)}` },
          req.login,
        ),
        h('span', { class: 'social-person-elo pill' }, `${req.elo ?? 1200} Elo`),
      ),
      h(
        'div',
        { class: 'social-actions' },
        createActionButton('Отменить заявку', 'btn-ghost', () => cancelRequest(req.id, req.login)),
        createActionButton('Заблокировать', 'btn-ghost', () => blockFriend(req.id, req.login)),
      ),
    );
    list.appendChild(item);
  }
  contentContainer.appendChild(list);
}

function renderSearchResults() {
  if (searchLoading) {
    contentContainer.appendChild(h('div', { class: 'social-loading' }, 'Поиск игроков...'));
    return;
  }

  if (searchResults.length === 0) {
    contentContainer.appendChild(
      h(
        'div',
        { class: 'social-empty card' },
        h('p', { class: 'social-empty-title' }, 'Пользователи не найдены'),
        h('p', { class: 'social-empty-sub' }, 'Попробуйте изменить запрос.'),
      ),
    );
    return;
  }

  const list = h('div', { class: 'social-list' });
  for (const u of searchResults) {
    const item = h(
      'div',
      { class: 'social-person card' },
      h(
        'div',
        { class: 'social-person-info' },
        h(
          'a',
          { class: 'social-person-name', href: `/user.html?login=${encodeURIComponent(u.login)}` },
          u.login,
        ),
        h('span', { class: 'social-person-elo pill' }, `${u.elo ?? 1200} Elo`),
      ),
      h('div', { class: 'social-actions' }, createSearchUserActions(u)),
    );
    list.appendChild(item);
  }
  contentContainer.appendChild(list);
}

function createSearchUserActions(u) {
  const container = h('div', { class: 'social-action-buttons' });
  const rel = u.relationship || 'none';

  if (rel === 'friend') {
    container.appendChild(h('span', { class: 'pill social-tag-friend' }, 'В друзьях'));
    container.appendChild(
      h(
        'a',
        {
          class: 'btn btn-gold btn-sm',
          href: `/index.html?friend=${encodeURIComponent(u.id)}`,
        },
        'Позвать',
      ),
    );
  } else if (rel === 'incoming') {
    container.appendChild(createActionButton('Принять', 'btn-gold', () => acceptRequest(u.id, u.login)));
    container.appendChild(createActionButton('Отклонить', 'btn-ghost', () => rejectRequest(u.id, u.login)));
  } else if (rel === 'outgoing') {
    container.appendChild(h('span', { class: 'pill' }, 'Заявка отправлена'));
    container.appendChild(createActionButton('Отменить', 'btn-ghost', () => cancelRequest(u.id, u.login)));
  } else {
    container.appendChild(createActionButton('Добавить в друзья', 'btn-gold', () => sendRequest(u.login)));
  }

  return container;
}

function createActionButton(label, variantClass, handler) {
  const btn = h('button', { type: 'button', class: `btn ${variantClass} btn-sm` }, label);
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      await handler();
    } finally {
      btn.disabled = false;
    }
  });
  return btn;
}

async function withActionLock(key, actionFn) {
  if (busyActions.has(key)) return;
  busyActions.add(key);
  try {
    await actionFn();
  } finally {
    busyActions.delete(key);
  }
}

async function sendRequest(login) {
  await withActionLock(`send:${login}`, async () => {
    try {
      await api('POST', '/friends/requests', { login });
      toast(`Заявка пользователю ${login} отправлена`, 'success');
      await loadSocialData();
      if (searchInput.value.trim().length >= 2) {
        performSearch(searchInput.value.trim());
      }
    } catch (err) {
      toast((err && err.message) || 'Не удалось отправить заявку', 'error');
    }
  });
}

async function acceptRequest(userId, login) {
  await withActionLock(`accept:${userId}`, async () => {
    try {
      await api('POST', `/friends/requests/${userId}/accept`);
      toast(`Заявка от ${login} принята`, 'success');
      await loadSocialData();
      if (currentTab === TAB_SEARCH && searchInput.value.trim().length >= 2) {
        performSearch(searchInput.value.trim());
      }
    } catch (err) {
      toast((err && err.message) || 'Не удалось принять заявку', 'error');
    }
  });
}

async function rejectRequest(userId, login) {
  await withActionLock(`reject:${userId}`, async () => {
    try {
      await api('DELETE', `/friends/requests/${userId}`);
      toast(`Заявка от ${login} отклонена`, 'info');
      await loadSocialData();
      if (currentTab === TAB_SEARCH && searchInput.value.trim().length >= 2) {
        performSearch(searchInput.value.trim());
      }
    } catch (err) {
      toast((err && err.message) || 'Не удалось отклонить заявку', 'error');
    }
  });
}

async function cancelRequest(userId, login) {
  await withActionLock(`cancel:${userId}`, async () => {
    try {
      await api('DELETE', `/friends/requests/${userId}`);
      toast(`Заявка пользователю ${login} отменена`, 'info');
      await loadSocialData();
      if (currentTab === TAB_SEARCH && searchInput.value.trim().length >= 2) {
        performSearch(searchInput.value.trim());
      }
    } catch (err) {
      toast((err && err.message) || 'Не удалось отменить заявку', 'error');
    }
  });
}

async function removeFriend(userId, login) {
  await withActionLock(`remove:${userId}`, async () => {
    try {
      await api('DELETE', `/friends/${userId}`);
      toast(`${login} удалён из друзей`, 'info');
      await loadSocialData();
      if (currentTab === TAB_SEARCH && searchInput.value.trim().length >= 2) {
        performSearch(searchInput.value.trim());
      }
    } catch (err) {
      toast((err && err.message) || 'Не удалось удалить друга', 'error');
    }
  });
}

async function blockFriend(userId, login) {
  await withActionLock(`block:${userId}`, async () => {
    try {
      await api('POST', '/me/blocks', { login });
      toast(`${login} заблокирован`, 'info');
      await loadSocialData();
      if (currentTab === TAB_SEARCH && searchInput.value.trim().length >= 2) {
        performSearch(searchInput.value.trim());
      }
    } catch (err) {
      toast((err && err.message) || 'Не удалось заблокировать', 'error');
    }
  });
}

// Search handling with immediate stale guard
searchInput.addEventListener('input', () => {
  const q = searchInput.value.trim();
  ++searchSeq;
  if (searchTimer !== null) {
    clearTimeout(searchTimer);
    searchTimer = null;
  }

  if (q.length > 0) {
    searchClearBtn.removeAttribute('hidden');
  } else {
    searchClearBtn.setAttribute('hidden', 'hidden');
  }

  if (q.length < 2) {
    tabButtons[TAB_SEARCH].setAttribute('hidden', 'hidden');
    searchResults = [];
    if (currentTab === TAB_SEARCH) {
      switchTab(TAB_FRIENDS);
    }
    return;
  }

  searchTimer = setTimeout(() => {
    performSearch(q);
  }, 250);
});

searchClearBtn.addEventListener('click', () => {
  searchInput.value = '';
  searchClearBtn.setAttribute('hidden', 'hidden');
  tabButtons[TAB_SEARCH].setAttribute('hidden', 'hidden');
  ++searchSeq;
  if (searchTimer !== null) {
    clearTimeout(searchTimer);
    searchTimer = null;
  }
  searchResults = [];
  if (currentTab === TAB_SEARCH) {
    switchTab(TAB_FRIENDS);
  }
});

async function performSearch(query) {
  const currentSeq = ++searchSeq;
  searchLoading = true;
  tabButtons[TAB_SEARCH].removeAttribute('hidden');
  switchTab(TAB_SEARCH);

  try {
    const res = await api('GET', `/users/search?q=${encodeURIComponent(query)}`);
    if (currentSeq !== searchSeq) return;
    searchResults = (res && res.items) || [];
  } catch (err) {
    if (currentSeq !== searchSeq) return;
    toast((err && err.message) || 'Ошибка поиска пользователей', 'error');
    searchResults = [];
  } finally {
    if (currentSeq === searchSeq) {
      searchLoading = false;
      renderContent();
    }
  }
}

// Background sync on focus / new notifications
function onFocusRefresh() {
  if (document.visibilityState === 'visible') {
    refreshSocialDataQuietly();
  }
}

function onSocialCleanup() {
  if (socialPollTimer !== null) {
    clearInterval(socialPollTimer);
    socialPollTimer = null;
  }
  window.removeEventListener('focus', onFocusRefresh);
  document.removeEventListener('visibilitychange', onFocusRefresh);
  window.removeEventListener('chessdep:notifications-updated', onFocusRefresh);
  window.removeEventListener('pagehide', onSocialCleanup);
}

window.addEventListener('focus', onFocusRefresh);
document.addEventListener('visibilitychange', onFocusRefresh);
window.addEventListener('chessdep:notifications-updated', onFocusRefresh);
window.addEventListener('pagehide', onSocialCleanup);
socialPollTimer = setInterval(refreshSocialDataQuietly, 10000);

// Initial load
setTab(TAB_FRIENDS);
loadSocialData();
