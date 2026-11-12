import { api } from './api.js';
import { h, clear } from './dom.js';
import { toast } from './toast.js';

const STATUS_TEXT = {
  accepted: 'Принято',
  declined: 'Отклонено',
  cancelled: 'Отменено',
  expired: 'Истекло',
  unavailable: 'Недоступно',
  pending: 'Ожидает ответа',
};

const busyNotificationIds = new Set();

function stopAllPropagation(e) {
  e.stopPropagation();
}

export function createNotificationActions(item, { onUpdate } = {}) {
  const container = h('div', { class: 'notif-actions' });
  container.addEventListener('click', stopAllPropagation);
  container.addEventListener('pointerdown', stopAllPropagation);
  container.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') e.stopPropagation();
  });

  renderInto(container, item, onUpdate);
  return container;
}

function renderInto(container, item, onUpdate) {
  clear(container);
  if (!item) return;

  const allowed = Array.isArray(item.allowed_actions) ? item.allowed_actions : [];
  const state = item.action_state || null;
  const gameId = item.game_id || (item.data && item.data.game_id) || null;

  if (allowed.length > 0) {
    const btnsRow = h('div', { class: 'notif-action-buttons' });

    if (allowed.includes('accept')) {
      const acceptBtn = h(
        'button',
        {
          type: 'button',
          class: 'btn btn-gold btn-sm notif-action-btn notif-action-accept',
        },
        'Принять',
      );
      acceptBtn.addEventListener('pointerdown', stopAllPropagation);
      acceptBtn.addEventListener('click', (e) => {
        stopAllPropagation(e);
        e.preventDefault();
        handleAction(container, item, 'accept', onUpdate);
      });
      btnsRow.appendChild(acceptBtn);
    }

    if (allowed.includes('decline')) {
      const declineBtn = h(
        'button',
        {
          type: 'button',
          class: 'btn btn-ghost btn-sm notif-action-btn notif-action-decline',
        },
        'Отклонить',
      );
      declineBtn.addEventListener('pointerdown', stopAllPropagation);
      declineBtn.addEventListener('click', (e) => {
        stopAllPropagation(e);
        e.preventDefault();
        handleAction(container, item, 'decline', onUpdate);
      });
      btnsRow.appendChild(declineBtn);
    }

    container.appendChild(btnsRow);
    return;
  }

  if (state && state !== 'pending') {
    const label = STATUS_TEXT[state] || state;
    const statusEl = h(
      'span',
      { class: 'pill notif-action-status notif-status-' + state },
      label,
    );
    container.appendChild(statusEl);

    // If accepted and game_id exists, offer direct button to open the game
    if (state === 'accepted' && gameId) {
      const openGameLink = h(
        'a',
        {
          class: 'btn btn-gold btn-sm notif-action-btn notif-game-link',
          href: `/game.html?id=${encodeURIComponent(gameId)}`,
        },
        'Открыть партию',
      );
      openGameLink.addEventListener('pointerdown', stopAllPropagation);
      openGameLink.addEventListener('click', stopAllPropagation);
      container.appendChild(openGameLink);
    }
  }
}

async function handleAction(container, item, action, onUpdate) {
  if (busyNotificationIds.has(item.id)) return;
  busyNotificationIds.add(item.id);

  const btns = container.querySelectorAll('button');
  for (const b of btns) b.disabled = true;

  try {
    const res = await api('POST', `/notifications/${item.id}/action`, { action });
    const finalStatus = (res && res.status) || (action === 'accept' ? 'accepted' : 'declined');
    item.action_state = finalStatus;
    item.allowed_actions = [];
    item.read = true;
    if (res && res.game_id) {
      item.game_id = res.game_id;
    }

    if (action === 'accept' && res && res.game_id) {
      location.href = `/game.html?id=${encodeURIComponent(res.game_id)}`;
      return;
    }

    toast(action === 'accept' ? 'Приглашение принято' : 'Приглашение отклонено', 'info');
    renderInto(container, item, onUpdate);

    if (typeof onUpdate === 'function') {
      onUpdate(res, item);
    }
    window.dispatchEvent(new CustomEvent('chessdep:notifications-updated'));
  } catch (err) {
    toast((err && err.message) || 'Ошибка обработки действия', 'error');
    for (const b of btns) b.disabled = false;
  } finally {
    busyNotificationIds.delete(item.id);
  }
}
