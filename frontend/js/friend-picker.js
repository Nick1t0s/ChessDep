import { api } from './api.js';
import { h, clear } from './dom.js';

export function createFriendPicker({ onSelect, searchAll = true, selectedId = null } = {}) {
  const root = h('div', { class: 'social-picker' });

  let friends = [];
  let displayedItems = [];
  let selectedUser = null;
  let currentQuery = '';
  let searchReqId = 0;
  let searchDebounceTimer = null;
  let initialLoading = false;
  let searchLoading = false;
  let loadError = null;
  let searchError = null;
  let isDisabled = false;

  const searchInput = h('input', {
    type: 'text',
    class: 'social-search',
    placeholder: searchAll ? 'Поиск друзей и игроков...' : 'Поиск среди друзей...',
    maxlength: '64',
    'aria-label': 'Поиск пользователей',
  });

  const listEl = h('div', { class: 'social-list', role: 'listbox' });
  listEl.style.maxHeight = '150px';
  listEl.style.overflowY = 'auto';

  root.append(searchInput, listEl);

  function renderList() {
    clear(listEl);

    if (initialLoading || searchLoading) {
      listEl.appendChild(h('div', { class: 'social-empty' }, 'Загрузка...'));
      return;
    }

    if (loadError) {
      const retryBtn = h('button', {
        type: 'button',
        class: 'btn btn-ghost btn-sm',
        disabled: isDisabled,
        onClick: () => {
          loadError = null;
          loadFriends();
        },
      }, 'Повторить');
      listEl.appendChild(h('div', { class: 'social-empty' },
        h('span', {}, loadError),
        h('div', { class: 'social-actions' }, retryBtn),
      ));
      return;
    }

    if (searchError) {
      const retryBtn = h('button', {
        type: 'button',
        class: 'btn btn-ghost btn-sm',
        disabled: isDisabled,
        onClick: () => {
          searchError = null;
          triggerSearch(currentQuery, true);
        },
      }, 'Повторить');
      listEl.appendChild(h('div', { class: 'social-empty' },
        h('span', {}, searchError),
        h('div', { class: 'social-actions' }, retryBtn),
      ));
      return;
    }

    if (displayedItems.length === 0) {
      const emptyText = currentQuery.trim().length > 0 ? 'Ничего не найдено' : 'Список пуст';
      listEl.appendChild(h('div', { class: 'social-empty' }, emptyText));
      return;
    }

    for (const user of displayedItems) {
      const isSelected = selectedUser && String(selectedUser.id) === String(user.id);
      const rowClasses = ['social-person'];
      if (isSelected) rowClasses.push('social-selected');

      const eloSpan = user.elo !== undefined && user.elo !== null
        ? h('span', { class: 'mono' }, ` (${user.elo})`)
        : null;

      const info = h('span', { class: 'social-person-info' },
        h('strong', {}, user.login),
        eloSpan,
      );

      const selectBtn = h('button', {
        type: 'button',
        class: isSelected ? 'btn btn-gold btn-sm' : 'btn btn-ghost btn-sm',
        disabled: isDisabled,
        onClick: (e) => {
          e.stopPropagation();
          if (!isDisabled) select(user);
        },
      }, isSelected ? 'Выбран' : 'Выбрать');

      const actions = h('div', { class: 'social-actions' }, selectBtn);

      const row = h('div', {
        class: rowClasses,
        role: 'option',
        'aria-selected': isSelected ? 'true' : 'false',
        tabindex: isDisabled ? '-1' : '0',
        onClick: () => {
          if (!isDisabled) select(user);
        },
        onKeydown: (e) => {
          if (isDisabled) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            select(user);
          }
        },
      }, info, actions);

      listEl.appendChild(row);
    }
  }

  function select(user) {
    selectedUser = user ? { id: user.id, login: user.login, elo: user.elo } : null;
    renderList();
    if (typeof onSelect === 'function') {
      onSelect(selectedUser);
    }
  }

  async function loadFriends() {
    initialLoading = true;
    loadError = null;
    renderList();

    try {
      const data = await api('GET', '/friends');
      friends = Array.isArray(data?.items) ? data.items : [];
      if (selectedId && !selectedUser) {
        const found = friends.find((f) => String(f.id) === String(selectedId));
        if (found) {
          selectedUser = { id: found.id, login: found.login, elo: found.elo };
          if (typeof onSelect === 'function') onSelect(selectedUser);
        }
      }
      applyLocalFilter(currentQuery);
    } catch (err) {
      loadError = err.message || 'Не удалось загрузить список друзей';
    } finally {
      initialLoading = false;
      renderList();
    }
  }

  function applyLocalFilter(q) {
    const trimmed = q.trim();
    if (!trimmed) {
      displayedItems = [...friends];
    } else {
      const lower = trimmed.toLowerCase();
      displayedItems = friends.filter((f) => f.login.toLowerCase().includes(lower));
    }
    renderList();
  }

  async function executeServerSearch(queryText, reqId) {
    searchLoading = true;
    searchError = null;
    renderList();

    try {
      const data = await api('GET', '/users/search?q=' + encodeURIComponent(queryText));
      if (reqId !== searchReqId) return; // Stale-response guard
      displayedItems = Array.isArray(data?.items) ? data.items : [];
    } catch (err) {
      if (reqId !== searchReqId) return;
      searchError = err.message || 'Ошибка поиска пользователей';
      displayedItems = [];
    } finally {
      if (reqId === searchReqId) {
        searchLoading = false;
        renderList();
      }
    }
  }

  function triggerSearch(q, immediate = false) {
    currentQuery = q;
    searchError = null;
    const trimmed = q.trim();

    if (searchDebounceTimer !== null) {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = null;
    }

    if (!searchAll || trimmed.length < 2) {
      searchReqId++;
      searchLoading = false;
      applyLocalFilter(trimmed);
      return;
    }

    const myReqId = ++searchReqId;

    if (immediate) {
      executeServerSearch(trimmed, myReqId);
    } else {
      searchDebounceTimer = setTimeout(() => {
        executeServerSearch(trimmed, myReqId);
      }, 200);
    }
  }

  searchInput.addEventListener('input', () => {
    triggerSearch(searchInput.value);
  });

  root.selectUser = (user) => select(user);
  root.clearSelection = () => select(null);
  root.getSelected = () => selectedUser;
  root.getFriends = () => [...friends];
  root.reload = () => loadFriends();
  root.setDisabled = (disabled) => {
    isDisabled = Boolean(disabled);
    searchInput.disabled = isDisabled;
    renderList();
  };

  loadFriends();

  return root;
}
