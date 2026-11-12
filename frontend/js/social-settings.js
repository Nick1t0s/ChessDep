import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { sendPresenceHeartbeat } from './presence.js';

await initLayout({ auth: 'required', active: 'friends' });

const main = h('main', { class: 'wrap-wide social-page settings-page' });
document.body.appendChild(main);

// Header
const header = h(
  'div',
  { class: 'page-header friends-header' },
  h(
    'div',
    { class: 'friends-header-main' },
    h('h1', { class: 'page-title' }, 'Настройки общения и приватности'),
    h('p', { class: 'page-subtitle' }, 'Управление присутствием, приёмом вызовов, уведомлениями и чёрным списком'),
  ),
  h('a', { class: 'btn btn-ghost btn-sm', href: '/friends.html' }, '← Назад к друзьям'),
);
main.appendChild(header);

const content = h('div', { class: 'settings-content' });
main.appendChild(content);

let settings = null;
let blocks = [];
let loading = false;
let patchQueue = Promise.resolve();
let pendingPatches = 0;
let blockInFlight = false;

function setSettingsInputsDisabled(disabled) {
  const inputs = content.querySelectorAll('.settings-section input');
  for (const el of inputs) {
    if (!el.classList.contains('settings-block-input')) {
      el.disabled = disabled;
    }
  }
}

async function enqueueSettingsPatch(patchPayload, successMsg, isPresenceChange = false) {
  pendingPatches++;
  setSettingsInputsDisabled(true);

  patchQueue = patchQueue.then(async () => {
    try {
      const res = await api('PATCH', '/me/social-settings', patchPayload);
      if (res) {
        settings = res;
      } else {
        if (patchPayload.presence_mode) settings.presence_mode = patchPayload.presence_mode;
        if (patchPayload.match_invites) settings.match_invites = patchPayload.match_invites;
        if (patchPayload.notifications) {
          settings.notifications = { ...(settings.notifications || {}), ...patchPayload.notifications };
        }
      }
      if (isPresenceChange) {
        sendPresenceHeartbeat();
      }
      toast(successMsg, 'success');
      renderSettings();
    } catch (err) {
      toast((err && err.message) || 'Ошибка сохранения настроек', 'error');
      await loadAll();
    } finally {
      pendingPatches--;
      if (pendingPatches <= 0) {
        pendingPatches = 0;
        setSettingsInputsDisabled(false);
      }
    }
  });

  return patchQueue;
}

async function loadAll() {
  loading = true;
  clear(content);
  content.appendChild(h('div', { class: 'social-loading' }, 'Загрузка настроек...'));

  try {
    const [settingsRes, blocksRes] = await Promise.all([
      api('GET', '/me/social-settings'),
      api('GET', '/me/blocks'),
    ]);
    settings = settingsRes || {};
    blocks = (blocksRes && blocksRes.items) || [];
    renderSettings();
  } catch {
    clear(content);
    const errBox = h(
      'div',
      { class: 'social-empty card social-error' },
      h('p', { class: 'social-empty-title' }, 'Не удалось загрузить настройки'),
    );
    const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
    retryBtn.addEventListener('click', () => loadAll());
    errBox.appendChild(retryBtn);
    content.appendChild(errBox);
  } finally {
    loading = false;
  }
}

function renderSettings() {
  clear(content);

  // 1. Presence mode
  content.appendChild(renderPresenceSection());

  // 2. Match invites policy
  content.appendChild(renderMatchInvitesSection());

  // 3. Notifications toggles
  content.appendChild(renderNotificationsSection());

  // 4. Block management
  content.appendChild(renderBlocksSection());

  if (pendingPatches > 0) {
    setSettingsInputsDisabled(true);
  }
}

function renderPresenceSection() {
  const card = h('div', { class: 'card settings-section' });
  card.appendChild(h('h2', { class: 'settings-section-title' }, 'Режим присутствия в сети'));
  card.appendChild(
    h(
      'p',
      { class: 'settings-section-desc' },
      'В режиме «Не беспокоить» друзья видят статус «Не беспокоить», а прямые вызовы на партию отклоняются.',
    ),
  );

  const group = h('div', { class: 'settings-radio-group' });

  const modes = [
    ['online', 'В сети', 'друзья видят статус В сети, когда вы активны на сайте'],
    ['dnd', 'Не беспокоить', 'друзья видят Не беспокоить; прямые приглашения отключены'],
  ];

  for (const [val, title, desc] of modes) {
    const radioAttrs = {
      type: 'radio',
      name: 'presence_mode',
      value: val,
    };
    if (settings && settings.presence_mode === val) {
      radioAttrs.checked = true;
    }
    const radio = h('input', radioAttrs);
    radio.addEventListener('change', () => {
      if (radio.checked) {
        enqueueSettingsPatch({ presence_mode: val }, 'Режим присутствия сохранён', true);
      }
    });

    const item = h(
      'label',
      { class: 'settings-radio-item' },
      radio,
      h(
        'div',
        { class: 'settings-radio-text' },
        h('span', { class: 'settings-radio-label' }, title),
        h('span', { class: 'settings-radio-sub' }, desc),
      ),
    );
    group.appendChild(item);
  }

  card.appendChild(group);
  return card;
}

function renderMatchInvitesSection() {
  const card = h('div', { class: 'card settings-section' });
  card.appendChild(h('h2', { class: 'settings-section-title' }, 'Приём вызовов на партию'));
  card.appendChild(
    h(
      'p',
      { class: 'settings-section-desc' },
      'Определяет, кто может отправлять вам прямые вызовы на партию. В режиме «Не беспокоить» прямые приглашения отклоняются.',
    ),
  );

  const group = h('div', { class: 'settings-radio-group' });

  const policies = [
    ['all', 'От всех игроков', 'Любой пользователь может отправить вам персональный вызов.'],
    ['friends', 'Только от друзей', 'Принимать прямые вызовы только от игроков из вашего списка друзей.'],
    ['none', 'Ни от кого', 'Запретить любые персональные вызовы на партию.'],
  ];

  for (const [val, title, desc] of policies) {
    const radioAttrs = {
      type: 'radio',
      name: 'match_invites',
      value: val,
    };
    if (settings && settings.match_invites === val) {
      radioAttrs.checked = true;
    }
    const radio = h('input', radioAttrs);
    radio.addEventListener('change', () => {
      if (radio.checked) {
        enqueueSettingsPatch({ match_invites: val }, 'Настройки приёма вызовов сохранены');
      }
    });

    const item = h(
      'label',
      { class: 'settings-radio-item' },
      radio,
      h(
        'div',
        { class: 'settings-radio-text' },
        h('span', { class: 'settings-radio-label' }, title),
        h('span', { class: 'settings-radio-sub' }, desc),
      ),
    );
    group.appendChild(item);
  }

  card.appendChild(group);
  return card;
}

function renderNotificationsSection() {
  const card = h('div', { class: 'card settings-section' });
  card.appendChild(h('h2', { class: 'settings-section-title' }, 'Уведомления'));
  card.appendChild(
    h(
      'p',
      { class: 'settings-section-desc' },
      'Настройка входящих уведомлений. Отключение категории отключает новые уведомления этого типа; история ранее полученных уведомлений сохраняется.',
    ),
  );

  const group = h('div', { class: 'settings-checkbox-group' });

  const kinds = [
    ['friend_request', 'Заявки в друзья', 'Оповещения о новых входящих запросах на добавление в друзья'],
    ['friend_accepted', 'Принятие заявки в друзья', 'Оповещения, когда другой игрок принял вашу заявку'],
    ['match_invite', 'Вызовы на партию', 'Приглашения сыграть персональный матч'],
    ['market_sale', 'Продажи на маркете', 'Сообщения об успешной продаже ваших лотов'],
    ['gift', 'Подарки', 'Уведомления о полученных подарках от других игроков'],
  ];

  const currentNotifs = (settings && settings.notifications) || {};

  for (const [kind, title, desc] of kinds) {
    const isChecked = currentNotifs[kind] !== false;
    const chkAttrs = {
      type: 'checkbox',
      name: kind,
    };
    if (isChecked) {
      chkAttrs.checked = true;
    }
    const chk = h('input', chkAttrs);
    chk.addEventListener('change', () => {
      enqueueSettingsPatch(
        { notifications: { [kind]: chk.checked } },
        'Настройки уведомлений сохранены',
      );
    });

    const item = h(
      'label',
      { class: 'settings-checkbox-item' },
      chk,
      h(
        'div',
        { class: 'settings-checkbox-text' },
        h('span', { class: 'settings-checkbox-label' }, title),
        h('span', { class: 'settings-checkbox-sub' }, desc),
      ),
    );
    group.appendChild(item);
  }

  card.appendChild(group);
  return card;
}

function renderBlocksSection() {
  const card = h('div', { class: 'card settings-section' });
  card.appendChild(h('h2', { class: 'settings-section-title' }, 'Чёрный список'));
  card.appendChild(
    h(
      'p',
      { class: 'settings-section-desc' },
      'Заблокированные пользователи не могут отправлять вам заявки в друзья, подарки и вызовы на партию. Блокировка взаимно удаляет пользователей из списка друзей.',
    ),
  );

  // Add block form with unified in-flight protection
  const input = h('input', {
    type: 'text',
    class: 'input settings-block-input',
    placeholder: 'Логин игрока для блокировки...',
    autocomplete: 'off',
    maxlength: '64',
  });
  const blockBtn = h('button', { type: 'button', class: 'btn btn-ghost' }, 'Заблокировать');

  const onAddBlock = async () => {
    if (blockInFlight) return;
    const val = input.value.trim();
    if (!val) return;
    blockInFlight = true;
    blockBtn.disabled = true;
    input.disabled = true;

    try {
      await api('POST', '/me/blocks', { login: val });
      toast(`Пользователь ${val} заблокирован`, 'success');
      input.value = '';
      await refreshBlocks();
    } catch (err) {
      toast((err && err.message) || 'Не удалось заблокировать пользователя', 'error');
    } finally {
      blockInFlight = false;
      blockBtn.disabled = false;
      input.disabled = false;
    }
  };

  blockBtn.addEventListener('click', onAddBlock);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      onAddBlock();
    }
  });

  const formRow = h('div', { class: 'settings-block-form' }, input, blockBtn);
  card.appendChild(formRow);

  // Blocked users list
  const listContainer = h('div', { class: 'settings-blocks-list' });
  if (blocks.length === 0) {
    listContainer.appendChild(
      h('p', { class: 'settings-empty-blocks' }, 'В чёрном списке пока никого нет.'),
    );
  } else {
    const list = h('div', { class: 'social-list' });
    for (const b of blocks) {
      const row = h(
        'div',
        { class: 'social-person card' },
        h(
          'div',
          { class: 'social-person-info' },
          h('span', { class: 'social-person-name' }, b.login),
          h('span', { class: 'social-person-elo pill' }, `${b.elo ?? 1200} Elo`),
        ),
        h(
          'div',
          { class: 'social-actions' },
          createUnblockButton(b.id, b.login),
        ),
      );
      list.appendChild(row);
    }
    listContainer.appendChild(list);
  }

  card.appendChild(listContainer);
  return card;
}

function createUnblockButton(userId, login) {
  const btn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Разблокировать');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      await api('DELETE', `/me/blocks/${userId}`);
      toast(`${login} разблокирован`, 'success');
      await refreshBlocks();
    } catch (err) {
      toast((err && err.message) || 'Не удалось разблокировать', 'error');
      btn.disabled = false;
    }
  });
  return btn;
}

async function refreshBlocks() {
  try {
    const res = await api('GET', '/me/blocks');
    blocks = (res && res.items) || [];
    renderSettings();
  } catch (err) {
    toast((err && err.message) || 'Ошибка обновления чёрного списка', 'error');
  }
}

loadAll();
