import { api } from './api.js';
import { h, clear } from './dom.js';
import { toast } from './toast.js';

let pollTimer = null;
let inFlight = false;
let baselineInitialized = false;
const seenIds = new Set();
let latestItems = [];
let currentUnreadCount = 0;
let lastFetchError = false;
let markingAll = false;

let badgeEl = null;
let bellBtn = null;
let popoverEl = null;
let listEl = null;
let markAllBtn = null;

const KIND_ICONS = {
  friend_request: '👤',
  friend_accepted: '🤝',
  match_invite: '♟',
  market_sale: '◈',
  gift: '🎁',
};

export function isSafeHref(url) {
  if (typeof url !== 'string') return false;
  if (url.startsWith('//') || url.includes('\\')) return false;
  return url.startsWith('/') || url.startsWith('#');
}

export function setupNotificationCenter() {
  const container = h('div', { class: 'notif-center' });

  bellBtn = h(
    'button',
    {
      type: 'button',
      class: 'notif-bell-btn',
      title: 'Уведомления',
      'aria-label': 'Уведомления',
      'aria-haspopup': 'dialog',
      'aria-expanded': 'false',
    },
    h('span', { class: 'notif-bell-icon', 'aria-hidden': 'true' }, '🔔'),
  );

  badgeEl = h('span', { class: 'notif-badge', hidden: true });
  bellBtn.appendChild(badgeEl);

  popoverEl = h(
    'div',
    {
      class: 'notif-popover',
      role: 'dialog',
      'aria-label': 'Панель уведомлений',
      hidden: true,
    },
  );

  const popoverHead = h(
    'div',
    { class: 'notif-popover-head' },
    h('span', { class: 'notif-popover-title' }, 'Уведомления'),
  );

  markAllBtn = h(
    'button',
    {
      type: 'button',
      class: 'btn btn-ghost btn-sm notif-read-all-btn',
      title: 'Прочитать все',
      disabled: true,
    },
    'Прочитать все',
  );
  markAllBtn.addEventListener('click', onMarkAllRead);
  popoverHead.appendChild(markAllBtn);

  listEl = h('div', { class: 'notif-popover-list' });

  const popoverFoot = h(
    'div',
    { class: 'notif-popover-foot' },
    h('a', { href: '/notifications.html', class: 'notif-all-link' }, 'Все уведомления →'),
  );

  popoverEl.append(popoverHead, listEl, popoverFoot);
  container.append(bellBtn, popoverEl);

  bellBtn.addEventListener('click', togglePopover);

  document.addEventListener('click', onDocumentClick);
  document.addEventListener('keydown', onDocumentKeydown);
  window.addEventListener('chessdep:notifications-updated', onExternalSync);

  startPolling();

  return container;
}

function onExternalSync(ev) {
  if (typeof ev?.detail?.count === 'number') {
    updateBadge(ev.detail.count);
    if (ev.detail.count === 0) {
      for (const item of latestItems) item.read = true;
    }
    if (popoverEl && !popoverEl.hasAttribute('hidden')) {
      renderPopoverList();
    }
  } else {
    pollNotifications();
  }
}

function togglePopover(ev) {
  if (ev) ev.stopPropagation();
  const willOpen = popoverEl.hasAttribute('hidden');
  if (willOpen) {
    popoverEl.removeAttribute('hidden');
    bellBtn.setAttribute('aria-expanded', 'true');
    renderPopoverList();
    // Фоновое обновление при открытии
    pollNotifications().then(() => {
      // Focus first control after popover is populated
      focusFirstControl();
    });
    focusFirstControl();
  } else {
    closePopover(true);
  }
}

function focusFirstControl() {
  if (popoverEl.hasAttribute('hidden')) return;
  if (markAllBtn && !markAllBtn.disabled) {
    markAllBtn.focus();
    return;
  }
  const firstItem = popoverEl.querySelector('.notif-item, .notif-all-link, button:not(:disabled)');
  if (firstItem && typeof firstItem.focus === 'function') {
    firstItem.focus();
  }
}

function closePopover(returnFocus = false) {
  if (!popoverEl.hasAttribute('hidden')) {
    popoverEl.setAttribute('hidden', 'hidden');
    bellBtn.setAttribute('aria-expanded', 'false');
    if (returnFocus && bellBtn) {
      bellBtn.focus();
    }
  }
}

function onDocumentClick(ev) {
  if (!popoverEl.hasAttribute('hidden')) {
    if (!popoverEl.contains(ev.target) && !bellBtn.contains(ev.target)) {
      closePopover(false);
    }
  }
}

function onDocumentKeydown(ev) {
  if (ev.key === 'Escape' && !popoverEl.hasAttribute('hidden')) {
    closePopover(true);
  }
}

export function updateBadge(count) {
  currentUnreadCount = Math.max(0, Number(count) || 0);
  if (badgeEl) {
    if (currentUnreadCount > 0) {
      badgeEl.removeAttribute('hidden');
      badgeEl.textContent = currentUnreadCount > 99 ? '99+' : String(currentUnreadCount);
      badgeEl.setAttribute('aria-label', `${currentUnreadCount} непрочитанных`);
      bellBtn.setAttribute('aria-label', `Уведомления (${currentUnreadCount} непрочитанных)`);
      if (markAllBtn && !markingAll) markAllBtn.disabled = false;
    } else {
      badgeEl.setAttribute('hidden', 'hidden');
      badgeEl.textContent = '0';
      badgeEl.removeAttribute('aria-label');
      bellBtn.setAttribute('aria-label', 'Уведомления');
      if (markAllBtn && !markingAll) markAllBtn.disabled = true;
    }
  }
}

export function renderPopoverList() {
  if (!listEl) return;
  clear(listEl);

  if (lastFetchError && latestItems.length === 0) {
    const errBox = h(
      'div',
      { class: 'notif-empty social-error' },
      h('p', null, 'Ошибка загрузки уведомлений'),
    );
    const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
    retryBtn.addEventListener('click', () => {
      clear(listEl);
      listEl.appendChild(h('div', { class: 'notif-empty' }, 'Загрузка...'));
      pollNotifications();
    });
    errBox.appendChild(retryBtn);
    listEl.appendChild(errBox);
    return;
  }

  if (!baselineInitialized && inFlight) {
    listEl.appendChild(h('div', { class: 'notif-empty' }, 'Загрузка...'));
    return;
  }

  if (!latestItems || latestItems.length === 0) {
    listEl.appendChild(h('div', { class: 'notif-empty' }, 'Нет новых уведомлений'));
    return;
  }

  for (const item of latestItems.slice(0, 6)) {
    const icon = KIND_ICONS[item.kind] || '🔔';
    const rowClasses = ['notif-item'];
    if (!item.read) rowClasses.push('unread');

    const itemEl = h(
      'div',
      { class: rowClasses.join(' '), role: 'button', tabindex: '0' },
      h('span', { class: 'notif-kind-icon', 'aria-hidden': 'true' }, icon),
      h(
        'div',
        { class: 'notif-content' },
        h('div', { class: 'notif-title' }, item.title || 'Уведомление'),
        item.body ? h('div', { class: 'notif-body' }, item.body) : null,
        h('div', { class: 'notif-date' }, formatDate(item.created_at)),
      ),
    );

    const onActivate = async () => {
      let targetHref = item.href;
      if (item.kind === 'friend_request' && (!targetHref || !isSafeHref(targetHref))) {
        targetHref = '/friends.html';
      }

      if (!item.read) {
        try {
          await api('POST', `/notifications/${item.id}/read`);
          item.read = true;
          updateBadge(Math.max(0, currentUnreadCount - 1));
          itemEl.classList.remove('unread');
          window.dispatchEvent(
            new CustomEvent('chessdep:notifications-updated', { detail: { count: currentUnreadCount } }),
          );
        } catch (err) {
          // On read failure preserve unread state and show visible toast
          toast(err.message || 'Не удалось отметить уведомление', 'error');
          return;
        }
      }
      closePopover(true);
      if (isSafeHref(targetHref)) {
        location.href = targetHref;
      }
    };

    itemEl.addEventListener('click', onActivate);
    itemEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onActivate();
      }
    });

    listEl.appendChild(itemEl);
  }
}

async function onMarkAllRead() {
  if (markingAll) return;
  markingAll = true;
  if (markAllBtn) markAllBtn.disabled = true;

  try {
    await api('POST', '/notifications/read-all');
    for (const item of latestItems) {
      item.read = true;
    }
    updateBadge(0);
    renderPopoverList();
    toast('Все уведомления прочитаны', 'success');
    window.dispatchEvent(
      new CustomEvent('chessdep:notifications-updated', { detail: { count: 0 } }),
    );
  } catch (err) {
    // Preserve unread state on failure and show visible toast
    toast(err.message || 'Не удалось прочитать уведомления', 'error');
    if (markAllBtn && currentUnreadCount > 0) {
      markAllBtn.disabled = false;
    }
  } finally {
    markingAll = false;
  }
}

export async function pollNotifications() {
  if (inFlight) return;
  if (document.visibilityState !== 'visible') return;

  inFlight = true;
  try {
    const res = await api('GET', '/notifications?limit=10', undefined, { redirectOn401: false });
    if (!res) return;

    lastFetchError = false;
    const items = res.items || [];
    const count = typeof res.unread_count === 'number' ? res.unread_count : items.filter((x) => !x.read).length;

    if (!baselineInitialized) {
      // Базовое состояние: запоминаем все существующие id без тостов
      for (const it of items) {
        seenIds.add(it.id);
      }
      baselineInitialized = true;
    } else {
      // Показываем тосты только для действительно новых входящих уведомлений
      const incomingNew = [];
      for (const it of items) {
        if (!seenIds.has(it.id)) {
          seenIds.add(it.id);
          if (!it.read) {
            incomingNew.push(it);
          }
        }
      }
      for (let i = incomingNew.length - 1; i >= 0; i--) {
        const n = incomingNew[i];
        const msg = n.title && n.body ? `${n.title}: ${n.body}` : n.title || n.body || 'Новое уведомление';
        toast(msg, 'info');
      }
    }

    latestItems = items;
    updateBadge(count);
    window.dispatchEvent(new CustomEvent('chessdep:notifications-polled', {
      detail: { items, count },
    }));
    if (popoverEl && !popoverEl.hasAttribute('hidden')) {
      renderPopoverList();
    }
  } catch (err) {
    if (err && err.status === 401) {
      stopPolling();
    } else {
      lastFetchError = true;
      if (popoverEl && !popoverEl.hasAttribute('hidden')) {
        renderPopoverList();
      }
    }
  } finally {
    inFlight = false;
  }
}

export function startPolling() {
  if (pollTimer !== null) return;

  pollNotifications();

  pollTimer = setInterval(() => {
    if (document.visibilityState === 'visible') {
      pollNotifications();
    }
  }, 10000);

  window.addEventListener('focus', onFocusRefresh);
  document.addEventListener('visibilitychange', onVisibilityChange);
  window.addEventListener('pagehide', stopPolling);
}

function onFocusRefresh() {
  if (document.visibilityState === 'visible') {
    pollNotifications();
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    pollNotifications();
  }
}

export function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  window.removeEventListener('focus', onFocusRefresh);
  document.removeEventListener('visibilitychange', onVisibilityChange);
  window.removeEventListener('pagehide', stopPolling);
  window.removeEventListener('chessdep:notifications-updated', onExternalSync);
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);
  if (diffSec < 60) return 'только что';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} мин назад`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} ч назад`;
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}
