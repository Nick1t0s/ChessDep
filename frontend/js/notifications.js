import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';

await initLayout({ auth: 'required', active: '' });

const main = h('main', { class: 'wrap-wide social-page notif-page' });
document.body.appendChild(main);

// Header
const header = h('div', { class: 'page-header notif-header' });
const titleRow = h(
  'div',
  { class: 'notif-header-title' },
  h('h1', { class: 'page-title' }, 'Уведомления'),
);

const unreadBadge = h('span', { class: 'pill notif-header-badge', hidden: true });
titleRow.appendChild(unreadBadge);

const markAllBtn = h(
  'button',
  {
    type: 'button',
    class: 'btn btn-ghost btn-sm notif-mark-all-btn',
    disabled: true,
  },
  'Прочитать все',
);
markAllBtn.addEventListener('click', onMarkAllRead);

header.append(titleRow, markAllBtn);
main.appendChild(header);

// Notification list container
const listContainer = h('div', { class: 'notif-list' });
const emptyState = h(
  'div',
  { class: 'social-empty card', hidden: true },
  h('p', { class: 'social-empty-title' }, 'Уведомлений нет'),
  h(
    'p',
    { class: 'social-empty-sub' },
    'Здесь будут появляться приглашения в игру, заявки в друзья и новости маркета.',
  ),
);
const loadingState = h('div', { class: 'social-loading' }, 'Загрузка уведомлений...');
const loadMoreBtn = h(
  'button',
  {
    type: 'button',
    class: 'btn btn-ghost btn-sm notif-load-more',
    hidden: true,
  },
  'Загрузить ещё',
);
loadMoreBtn.addEventListener('click', onLoadMore);

main.append(emptyState, loadingState, listContainer, loadMoreBtn);

// State
let items = [];
let nextCursor = null;
let unreadCount = 0;
let loading = false;
let markingAll = false;
const busyIds = new Set();

const KIND_INFO = {
  friend_request: { icon: '👤', label: 'Заявка в друзья' },
  friend_accepted: { icon: '🤝', label: 'Дружба' },
  match_invite: { icon: '♟', label: 'Вызов на партию' },
  market_sale: { icon: '◈', label: 'Маркет' },
  gift: { icon: '🎁', label: 'Подарок' },
};

function isSafeHref(url) {
  if (typeof url !== 'string') return false;
  if (url.startsWith('//') || url.includes('\\')) return false;
  return url.startsWith('/') || url.startsWith('#');
}

async function loadInitial() {
  loading = true;
  loadingState.removeAttribute('hidden');
  emptyState.setAttribute('hidden', 'hidden');
  loadMoreBtn.setAttribute('hidden', 'hidden');
  clear(listContainer);
  items = [];
  nextCursor = null;

  try {
    const res = await api('GET', '/notifications?limit=20');
    items = res?.items || [];
    nextCursor = res?.next_cursor || null;
    unreadCount =
      typeof res?.unread_count === 'number'
        ? res.unread_count
        : items.filter((x) => !x.read).length;

    renderList();
    window.dispatchEvent(
      new CustomEvent('chessdep:notifications-updated', { detail: { count: unreadCount } }),
    );
  } catch (err) {
    toast(err.message || 'Ошибка загрузки уведомлений', 'error');
    clear(listContainer);
    const errBox = h(
      'div',
      { class: 'social-empty card social-error' },
      h('p', { class: 'social-empty-title' }, 'Не удалось загрузить уведомления'),
    );
    const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
    retryBtn.addEventListener('click', () => loadInitial());
    errBox.appendChild(retryBtn);
    listContainer.appendChild(errBox);
  } finally {
    loading = false;
    loadingState.setAttribute('hidden', 'hidden');
  }
}

async function onLoadMore() {
  if (loading || !nextCursor) return;
  loading = true;
  loadMoreBtn.disabled = true;

  try {
    const res = await api(
      'GET',
      `/notifications?before_id=${encodeURIComponent(nextCursor)}&limit=20`,
    );
    const newItems = res?.items || [];
    nextCursor = res?.next_cursor || null;
    if (typeof res?.unread_count === 'number') {
      unreadCount = res.unread_count;
    }

    for (const it of newItems) {
      items.push(it);
      listContainer.appendChild(renderNotificationItem(it));
    }

    updateHeaderState();
  } catch (err) {
    toast(err.message || 'Ошибка загрузки следующей страницы', 'error');
  } finally {
    loading = false;
    loadMoreBtn.disabled = false;
    if (!nextCursor) {
      loadMoreBtn.setAttribute('hidden', 'hidden');
    }
  }
}

function updateHeaderState() {
  if (unreadCount > 0) {
    unreadBadge.removeAttribute('hidden');
    unreadBadge.textContent = `${unreadCount} новых`;
    if (!markingAll) markAllBtn.disabled = false;
  } else {
    unreadBadge.setAttribute('hidden', 'hidden');
    markAllBtn.disabled = true;
  }

  if (nextCursor) {
    loadMoreBtn.removeAttribute('hidden');
  } else {
    loadMoreBtn.setAttribute('hidden', 'hidden');
  }
}

function renderList() {
  clear(listContainer);

  if (items.length === 0) {
    emptyState.removeAttribute('hidden');
    updateHeaderState();
    return;
  }

  emptyState.setAttribute('hidden', 'hidden');

  for (const it of items) {
    listContainer.appendChild(renderNotificationItem(it));
  }

  updateHeaderState();
}

function renderNotificationItem(item) {
  const kindMeta = KIND_INFO[item.kind] || { icon: '🔔', label: 'Уведомление' };
  const cardClasses = ['card', 'notif-card'];
  if (!item.read) cardClasses.push('unread');

  const card = h('div', { class: cardClasses.join(' ') });

  // Icon
  const iconEl = h('div', { class: 'notif-card-icon', 'aria-hidden': 'true' }, kindMeta.icon);

  // Content
  const content = h('div', { class: 'notif-card-content' });

  const topRow = h('div', { class: 'notif-card-top' });
  topRow.appendChild(h('span', { class: 'notif-card-kind' }, kindMeta.label));
  topRow.appendChild(h('time', { class: 'notif-card-date' }, formatDateTime(item.created_at)));
  content.appendChild(topRow);

  if (item.title) {
    content.appendChild(h('h3', { class: 'notif-card-title' }, item.title));
  }

  if (item.body) {
    content.appendChild(h('p', { class: 'notif-card-body' }, item.body));
  }

  // Actions
  const actions = h('div', { class: 'notif-card-actions' });

  let targetHref = item.href;
  if (item.kind === 'friend_request' && (!targetHref || !isSafeHref(targetHref))) {
    targetHref = '/friends.html';
  }

  if (isSafeHref(targetHref)) {
    actions.appendChild(
      h(
        'a',
        {
          class: 'btn btn-gold btn-sm',
          href: targetHref,
        },
        'Перейти',
      ),
    );
  }

  if (!item.read) {
    const markBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Прочитать');
    markBtn.addEventListener('click', async () => {
      if (busyIds.has(item.id)) return;
      busyIds.add(item.id);
      markBtn.disabled = true;

      try {
        await api('POST', `/notifications/${item.id}/read`);
        item.read = true;
        unreadCount = Math.max(0, unreadCount - 1);
        card.className = 'card notif-card';
        markBtn.remove();
        updateHeaderState();
        window.dispatchEvent(
          new CustomEvent('chessdep:notifications-updated', { detail: { count: unreadCount } }),
        );
      } catch (err) {
        // Preserve unread state on failure
        toast(err.message || 'Ошибка обновления статуса', 'error');
        markBtn.disabled = false;
      } finally {
        busyIds.delete(item.id);
      }
    });
    actions.appendChild(markBtn);
  }

  if (actions.children.length > 0) {
    content.appendChild(actions);
  }

  card.append(iconEl, content);
  return card;
}

async function onMarkAllRead() {
  if (markingAll || unreadCount === 0) return;
  markingAll = true;
  markAllBtn.disabled = true;

  try {
    await api('POST', '/notifications/read-all');
    for (const it of items) {
      it.read = true;
    }
    unreadCount = 0;
    renderList();
    toast('Все уведомления прочитаны', 'success');
    window.dispatchEvent(
      new CustomEvent('chessdep:notifications-updated', { detail: { count: 0 } }),
    );
  } catch (err) {
    // Preserve unread state on failure and show visible toast
    toast(err.message || 'Ошибка отметки всех прочитанными', 'error');
    if (unreadCount > 0) {
      markAllBtn.disabled = false;
    }
  } finally {
    markingAll = false;
    updateHeaderState();
  }
}

async function refreshUnreadStateQuietly() {
  if (loading) return;
  try {
    const res = await api('GET', '/notifications/unread-count', undefined, { redirectOn401: false });
    if (res && typeof res.count === 'number') {
      unreadCount = res.count;
      updateHeaderState();
    }
  } catch {
    /* ignore */
  }
}

function onFocusRefresh() {
  if (document.visibilityState === 'visible') {
    refreshUnreadStateQuietly();
  }
}

function onPageCleanup() {
  window.removeEventListener('focus', onFocusRefresh);
  document.removeEventListener('visibilitychange', onFocusRefresh);
  window.removeEventListener('pagehide', onPageCleanup);
  window.removeEventListener('chessdep:notifications-polled', onNotificationsPolled);
}

function onNotificationsPolled(event) {
  if (loading || markingAll || busyIds.size) return;
  const fresh = event.detail.items;
  const byId = new Map(items.map((item) => [item.id, item]));
  for (const item of fresh) byId.set(item.id, item);
  items = [...byId.values()].sort((a, b) => b.id - a.id);
  unreadCount = event.detail.count;
  renderList();
}

window.addEventListener('focus', onFocusRefresh);
document.addEventListener('visibilitychange', onFocusRefresh);
window.addEventListener('pagehide', onPageCleanup);
window.addEventListener('chessdep:notifications-polled', onNotificationsPolled);

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

loadInitial();
