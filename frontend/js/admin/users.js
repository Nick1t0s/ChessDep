// Админка — вкладка «Пользователи»: поиск, карточка, бан, баланс, выдача скина.
import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { openModal } from '../modal.js';
import { fmtCrystals } from '../format.js';
import { RARITY_RU } from '../items.js';

export async function mount(root) {
  clear(root);
  root.append(
    h('h1', { class: 'page-title' }, 'Пользователи'),
  );
  const tab = h('div', { class: 'admin-section' });
  root.appendChild(tab);
  await renderList(tab);
}

// ---------- список ----------

async function renderList(host) {
  clear(host);

  const q = h('input', { type: 'text', placeholder: 'логин или email', autocomplete: 'off' });
  const searchBtn = h('button', { type: 'button', class: 'btn btn-gold' }, 'Найти');
  const found = h('p', { class: 'admin-muted' }, 'Найдено: …');
  const tableView = h('div', { class: 'admin-section' });

  const openDetail = (id) => renderDetail(host, id);

  const search = async () => {
    const term = q.value.trim();
    let path = '/admin/users?page=1&limit=50';
    if (term) path += '&q=' + encodeURIComponent(term);
    searchBtn.disabled = true;
    try {
      const out = await api('GET', path);
      clear(found);
      found.append('Найдено: ' + out.total);
      clear(tableView);
      tableView.appendChild(usersTable(out.items ?? [], openDetail));
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      searchBtn.disabled = false;
    }
  };

  searchBtn.addEventListener('click', search);
  q.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') search();
  });

  host.append(
    h('div', { class: 'admin-row' }, q, searchBtn),
    found,
    tableView,
  );
  await search();
}

function usersTable(items, openDetail) {
  const tbody = h('tbody');
  for (const u of items) {
    const open = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Открыть');
    open.addEventListener('click', () => openDetail(u.id));
    tbody.appendChild(h('tr', {},
      h('td', { class: 'mono' }, String(u.id)),
      h('td', {}, u.login),
      h('td', {}, u.email ?? ''),
      h('td', {}, u.role),
      h('td', {}, u.is_banned ? 'Да' : ''),
      h('td', { class: 'mono' }, fmtCrystals(u.balance)),
      h('td', {}, String(u.elo)),
      h('td', {}, new Date(u.created_at).toLocaleString('ru-RU')),
      h('td', {}, open),
    ));
  }
  return h('table', { class: 'admin-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'ID'),
      h('th', {}, 'Логин'),
      h('th', {}, 'Email'),
      h('th', {}, 'Роль'),
      h('th', {}, 'Бан'),
      h('th', {}, 'Баланс'),
      h('th', {}, 'Elo'),
      h('th', {}, 'Создан'),
      h('th', {}, ''),
    )),
    tbody,
  );
}

// ---------- карточка ----------

async function renderDetail(host, id) {
  clear(host);
  let u = null;
  try {
    u = await api('GET', '/admin/users/' + encodeURIComponent(id));
  } catch (e) {
    toast(e.message, 'error');
    await renderList(host);
    return;
  }

  const refresh = () => renderDetail(host, id);

  const back = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, '← К списку');
  back.addEventListener('click', () => renderList(host));

  const actions = h('div', { class: 'admin-row' });
  if (u.is_banned) {
    const unbanBtn = h('button', { type: 'button', class: 'btn btn-ghost' }, 'Разбанить');
    unbanBtn.addEventListener('click', async () => {
      unbanBtn.disabled = true;
      try {
        await api('POST', '/admin/users/' + id + '/unban');
        toast('Пользователь разбанен', 'success');
        refresh();
      } catch (e) {
        toast(e.message, 'error');
        unbanBtn.disabled = false;
      }
    });
    actions.appendChild(unbanBtn);
  } else {
    const banBtn = h('button', { type: 'button', class: 'btn btn-danger' }, 'Забанить');
    banBtn.addEventListener('click', () => openBanModal(u, refresh));
    actions.appendChild(banBtn);
  }

  const balanceBtn = h('button', { type: 'button', class: 'btn btn-gold' }, 'Изменить баланс');
  balanceBtn.addEventListener('click', () => openBalanceModal(u, refresh));
  actions.appendChild(balanceBtn);

  const grantBtn = h('button', { type: 'button', class: 'btn btn-ghost' }, 'Выдать скин');
  grantBtn.addEventListener('click', () => openGrantModal(u, refresh));
  actions.appendChild(grantBtn);

  host.append(
    back,
    h('div', { class: 'card' },
      h('h2', { class: 'card-title' }, u.login),
      h('p', {}, 'Email: ' + (u.email ?? '—')),
      h('p', {}, 'Роль: ' + u.role),
      h('p', {}, 'Бан: ' + (u.is_banned ? 'Да' : 'Нет')),
      h('p', {}, 'Баланс: ' + fmtCrystals(u.balance)),
      h('p', {}, 'Elo: ' + String(u.elo)),
      h('p', {}, 'Скинов: ' + String(u.items_owned)),
      h('p', {}, 'Активных лотов: ' + String(u.active_listings)),
      h('p', {}, 'Активная партия: ' + (u.active_game_id == null ? '—' : String(u.active_game_id))),
    ),
    actions,
    h('div', { class: 'admin-section' },
      h('h3', { class: 'card-title' }, 'Операции'),
      ledgerTable(u.ledger ?? []),
    ),
  );
}

// ---------- операции ----------

function ledgerTable(rows) {
  const tbody = h('tbody');
  for (const r of rows) {
    tbody.appendChild(h('tr', {},
      h('td', {}, new Date(r.created_at).toLocaleString('ru-RU')),
      h('td', {}, r.reason),
      h('td', { class: 'mono' }, fmtDelta(r.delta)),
      h('td', { class: 'mono' }, fmtCrystals(r.balance_after)),
      h('td', { class: 'mono' }, r.ref == null ? '—' : String(r.ref)),
    ));
  }
  return h('table', { class: 'admin-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'Дата'),
      h('th', {}, 'Причина'),
      h('th', {}, 'Сумма'),
      h('th', {}, 'Баланс после'),
      h('th', {}, 'Ref'),
    )),
    tbody,
  );
}

function fmtDelta(delta) {
  const n = Number(delta);
  return (n > 0 ? '+' : '') + fmtCrystals(n);
}

// ---------- модалки ----------

function openBanModal(u, refresh) {
  const reason = h('textarea', { id: 'adm-ban-reason', rows: 4, maxlength: 200, placeholder: 'Причина бана' });
  const body = h('div', { class: 'admin-form' },
    h('div', { class: 'field' },
      h('label', { for: 'adm-ban-reason' }, 'Причина (1–200 символов)'),
      reason,
    ),
  );
  let busy = false;
  const closeFn = openModal({
    title: 'Забанить: ' + u.login,
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      { label: 'Забанить', kind: 'danger', onClick: () => {
        if (busy) return false;
        const reasonText = reason.value.trim();
        if (reasonText.length === 0 || reasonText.length > 200) {
          toast('Укажите причину (1–200 символов)', 'error');
          return false;
        }
        busy = true;
        api('POST', '/admin/users/' + u.id + '/ban', { reason: reasonText })
          .then(() => {
            toast('Пользователь забанен', 'success');
            closeFn();
            refresh();
          })
          .catch((e) => toast(e.message, 'error'))
          .finally(() => { busy = false; });
        return false;
      } },
    ],
  });
}

function openBalanceModal(u, refresh) {
  const delta = h('input', { id: 'adm-balance-delta', type: 'number', step: 1, autocomplete: 'off' });
  const comment = h('input', { id: 'adm-balance-comment', type: 'text', maxlength: 200, autocomplete: 'off' });
  const body = h('div', { class: 'admin-form' },
    h('div', { class: 'field' },
      h('label', { for: 'adm-balance-delta' }, 'Изменение (целое, ≠ 0, может быть отрицательным)'),
      delta,
    ),
    h('div', { class: 'field' },
      h('label', { for: 'adm-balance-comment' }, 'Комментарий (1–200 символов)'),
      comment,
    ),
  );
  let busy = false;
  const closeFn = openModal({
    title: 'Изменить баланс: ' + u.login,
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      { label: 'Сохранить', kind: 'gold', onClick: () => {
        if (busy) return false;
        const raw = delta.value.trim();
        const num = Number(raw);
        if (raw === '' || !Number.isInteger(num) || num === 0) {
          toast('Введите целое изменение, не 0', 'error');
          return false;
        }
        const commentText = comment.value.trim();
        if (commentText.length === 0 || commentText.length > 200) {
          toast('Укажите комментарий (1–200 символов)', 'error');
          return false;
        }
        busy = true;
        api('POST', '/admin/users/' + u.id + '/balance', { delta: num, comment: commentText })
          .then(() => {
            toast('Баланс изменён', 'success');
            closeFn();
            refresh();
          })
          .catch((e) => toast(e.message, 'error'))
          .finally(() => { busy = false; });
        return false;
      } },
    ],
  });
}

async function openGrantModal(u, refresh) {
  let defs = [];
  try {
    defs = await api('GET', '/item-defs');
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  if (!Array.isArray(defs) || defs.length === 0) {
    toast('Нет выпущенных скинов', 'info');
    return;
  }

  const sel = h('select', { id: 'adm-grant-def' });
  for (const def of defs) {
    sel.appendChild(h('option', { value: String(def.id) },
      def.name + ' · ' + (RARITY_RU[def.rarity] ?? def.rarity)));
  }
  const body = h('div', { class: 'admin-form' },
    h('div', { class: 'field' },
      h('label', { for: 'adm-grant-def' }, 'Скин'),
      sel,
    ),
  );
  let busy = false;
  const closeFn = openModal({
    title: 'Выдать скин: ' + u.login,
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      { label: 'Выдать', kind: 'gold', onClick: () => {
        if (busy) return false;
        const defId = Number(sel.value);
        if (!Number.isInteger(defId)) {
          toast('Выберите скин', 'error');
          return false;
        }
        busy = true;
        api('POST', '/admin/users/' + u.id + '/grant-item', { item_def_id: defId })
          .then(() => {
            toast('Скин выдан', 'success');
            closeFn();
            refresh();
          })
          .catch((e) => toast(e.message, 'error'))
          .finally(() => { busy = false; });
        return false;
      } },
    ],
  });
}
