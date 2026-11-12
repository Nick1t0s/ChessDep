import { api } from './api.js';
import { h, clear } from './dom.js';
import { toast } from './toast.js';

export function createUserSocialControls(login) {
  const container = h('div', { class: 'social-controls' });
  let seq = 0;
  let busy = false;

  async function loadData() {
    const currentSeq = ++seq;
    clear(container);
    container.appendChild(h('div', { class: 'social-controls-loading' }, 'Загрузка...'));

    try {
      const data = await api('GET', `/users/${encodeURIComponent(login)}/social`);
      if (currentSeq !== seq) return;
      render(data);
    } catch {
      if (currentSeq !== seq) return;
      clear(container);
      const errBox = h('div', { class: 'social-controls-error' }, 'Не удалось загрузить данные');
      const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
      retryBtn.addEventListener('click', () => loadData());
      errBox.appendChild(retryBtn);
      container.appendChild(errBox);
    }
  }

  async function runAction(actionFn, successMsg) {
    if (busy) return;
    busy = true;
    const btns = container.querySelectorAll('button');
    for (const b of btns) b.disabled = true;

    try {
      await actionFn();
      if (successMsg) toast(successMsg, 'success');
      await loadData();
    } catch (err) {
      toast((err && err.message) || 'Ошибка выполнения действия', 'error');
      for (const b of btns) b.disabled = false;
    } finally {
      busy = false;
    }
  }

  function render(data) {
    clear(container);
    if (!data) return;

    const rel = data.relationship || 'none';
    if (rel === 'self') {
      return;
    }

    const row = h('div', { class: 'social-controls-row' });

    // Review fix 3: allow unblock when blocked_by_me is true even if relationship is 'unavailable'
    if (data.blocked_by_me || rel === 'blocked') {
      row.appendChild(h('span', { class: 'pill notif-status-declined' }, 'Заблокирован'));
      const unblockBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Разблокировать');
      unblockBtn.addEventListener('click', () => {
        runAction(() => api('DELETE', `/me/blocks/${data.id}`), `${login} разблокирован`);
      });
      row.appendChild(unblockBtn);
      container.appendChild(row);
      return;
    }

    if (rel === 'unavailable') {
      row.appendChild(h('span', { class: 'pill' }, 'Недоступно'));
      container.appendChild(row);
      return;
    }

    if (rel === 'friend') {
      row.appendChild(h('span', { class: 'pill social-tag-friend' }, 'В друзьях'));

      // Review fix 3: Watch link appears if game_id exists even if presence is dnd
      if (data.game_id) {
        row.appendChild(
          h(
            'a',
            {
              class: 'btn btn-ghost btn-sm',
              href: `/game.html?id=${encodeURIComponent(data.game_id)}`,
            },
            'Смотреть партию',
          ),
        );
      }

      if (data.presence === 'dnd') {
        row.appendChild(
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
      } else if (data.presence === 'in_game') {
        row.appendChild(
          h(
            'button',
            {
              type: 'button',
              class: 'btn btn-gold btn-sm',
              disabled: true,
              title: 'Пользователь в партии',
            },
            'Позвать в игру',
          ),
        );
      } else {
        row.appendChild(
          h(
            'a',
            {
              class: 'btn btn-gold btn-sm',
              href: `/index.html?friend=${encodeURIComponent(data.id)}`,
            },
            'Позвать в игру',
          ),
        );
      }

      const removeBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Удалить из друзей');
      removeBtn.addEventListener('click', () => {
        runAction(() => api('DELETE', `/friends/${data.id}`), `${login} удалён из друзей`);
      });
      row.appendChild(removeBtn);

      const blockBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Заблокировать');
      blockBtn.addEventListener('click', () => {
        runAction(() => api('POST', '/me/blocks', { login }), `${login} заблокирован`);
      });
      row.appendChild(blockBtn);
    } else if (rel === 'incoming') {
      row.appendChild(h('span', { class: 'pill' }, 'Входящая заявка'));

      const acceptBtn = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Принять');
      acceptBtn.addEventListener('click', () => {
        runAction(() => api('POST', `/friends/requests/${data.id}/accept`), `Заявка от ${login} принята`);
      });
      row.appendChild(acceptBtn);

      const rejectBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Отклонить');
      rejectBtn.addEventListener('click', () => {
        runAction(() => api('DELETE', `/friends/requests/${data.id}`), `Заявка от ${login} отклонена`);
      });
      row.appendChild(rejectBtn);

      const blockBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Заблокировать');
      blockBtn.addEventListener('click', () => {
        runAction(() => api('POST', '/me/blocks', { login }), `${login} заблокирован`);
      });
      row.appendChild(blockBtn);
    } else if (rel === 'outgoing') {
      row.appendChild(h('span', { class: 'pill' }, 'Заявка отправлена'));

      const cancelBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Отменить заявку');
      cancelBtn.addEventListener('click', () => {
        runAction(() => api('DELETE', `/friends/requests/${data.id}`), `Заявка пользователю ${login} отменена`);
      });
      row.appendChild(cancelBtn);

      const blockBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Заблокировать');
      blockBtn.addEventListener('click', () => {
        runAction(() => api('POST', '/me/blocks', { login }), `${login} заблокирован`);
      });
      row.appendChild(blockBtn);
    } else {
      const addBtn = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Добавить в друзья');
      addBtn.addEventListener('click', () => {
        runAction(() => api('POST', '/friends/requests', { login }), `Заявка отправлена ${login}`);
      });
      row.appendChild(addBtn);

      const blockBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Заблокировать');
      blockBtn.addEventListener('click', () => {
        runAction(() => api('POST', '/me/blocks', { login }), `${login} заблокирован`);
      });
      row.appendChild(blockBtn);
    }

    container.appendChild(row);
  }

  loadData();
  return container;
}
