import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { openModal } from '../modal.js';
import { fmtCrystals } from '../format.js';

const STATUS_OPTIONS = [
  ['', 'Все'],
  ['active', 'Активные'],
  ['sold', 'Проданные'],
  ['cancelled', 'Снятые'],
];

const STATUS_RU = {
  active: 'Активные',
  sold: 'Проданные',
  cancelled: 'Снятые',
};

function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU') : '—';
}

export async function mountMarket(root) {
  clear(root);

  let statusValue = '';
  let nextCursor = null;

  const tbody = h('tbody');
  const moreBtn = h('button', { type: 'button', hidden: true, class: 'btn btn-ghost' }, 'Ещё');
  const table = h('table', { class: 'admin-table' },
    h('thead', null,
      h('tr', null,
        h('th', null, 'ID'),
        h('th', null, 'Предмет'),
        h('th', null, 'Скин'),
        h('th', null, 'Продавец'),
        h('th', null, 'Цена'),
        h('th', null, 'Статус'),
        h('th', null, 'Покупатель'),
        h('th', null, 'Комиссия'),
        h('th', null, 'Создан'),
        h('th', null, ''),
      ),
    ),
    tbody,
  );

  const statusSelect = h('select', { id: 'market-status' },
    STATUS_OPTIONS.map(([value, label]) => {
      const option = h('option', { value }, label);
      if (value === statusValue) option.selected = true;
      return option;
    }),
  );

  root.append(
    h('h2', { class: 'page-title' }, 'Маркет'),
    h('div', { class: 'admin-section' },
      h('div', { class: 'admin-form' },
        h('div', { class: 'field' },
          h('label', { for: 'market-status' }, 'Статус'),
          statusSelect,
        ),
      ),
    ),
    table,
    h('div', { class: 'admin-section admin-row' }, moreBtn),
  );

  statusSelect.addEventListener('change', () => {
    statusValue = statusSelect.value;
    loadPage(true);
  });

  moreBtn.addEventListener('click', () => loadPage(false));

  async function loadPage(reset) {
    if (reset) {
      nextCursor = null;
      clear(tbody);
    }
    const params = new URLSearchParams({ limit: '50' });
    if (statusValue) params.set('status', statusValue);
    if (nextCursor !== null) params.set('before_id', String(nextCursor));
    try {
      const data = await api('GET', '/admin/market?' + params.toString());
      nextCursor = data?.next_cursor ?? null;
      for (const listing of data?.items ?? []) tbody.appendChild(listingRow(listing));
      moreBtn.hidden = nextCursor === null;
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  function listingRow(listing) {
    const cancelCell = h('td');
    if (listing.status === 'active') {
      const cancelBtn = h('button', { type: 'button', class: 'btn btn-danger btn-sm' }, 'Снять');
      cancelBtn.addEventListener('click', () => openCancelModal(listing));
      cancelCell.appendChild(cancelBtn);
    } else {
      cancelCell.textContent = '—';
    }
    return h('tr', null,
      h('td', { class: 'mono' }, String(listing.id)),
      h('td', { class: 'mono' }, String(listing.item_id)),
      h('td', null, String(listing.item_def_id)),
      h('td', { class: 'mono' }, String(listing.seller_id)),
      h('td', null, fmtCrystals(listing.price)),
      h('td', null, h('span', { class: 'pill' }, STATUS_RU[listing.status] ?? String(listing.status))),
      h('td', { class: 'mono' }, listing.buyer_id == null ? '—' : String(listing.buyer_id)),
      h('td', null, listing.fee == null ? '—' : fmtCrystals(listing.fee)),
      h('td', null, fmtDate(listing.created_at)),
      cancelCell,
    );
  }

  function openCancelModal(listing) {
    const ta = h('textarea', {
      id: 'market-cancel-reason',
      rows: 4,
      required: true,
      placeholder: 'Причина снятия (обязательно)',
    });
    const body = h('div', { class: 'admin-form' },
      h('p', { class: 'admin-muted' },
        'Лот №' + String(listing.id) + ' · ' + String(listing.item_def_id) + ' · ' + fmtCrystals(listing.price)),
      h('div', { class: 'field' },
        h('label', { for: 'market-cancel-reason' }, 'Причина снятия'),
        ta,
      ),
    );
    const close = openModal({
      title: 'Снять лот',
      titleAnim: 'none',
      body,
      dismissible: true,
      actions: [
        { label: 'Отмена', kind: 'ghost' },
        {
          label: 'Снять',
          kind: 'danger',
          onClick: () => {
            const reason = ta.value.trim();
            if (!reason) {
              toast('Укажите причину снятия', 'error');
              ta.focus();
              return false;
            }
            submit();
            return false;
          },
        },
      ],
    });

    async function submit() {
      try {
        await api('POST', '/admin/market/listings/' + String(listing.id) + '/cancel', {
          reason: ta.value.trim(),
        });
        close();
        toast('Лот снят', 'success');
        await loadPage(true);
      } catch (e) {
        toast(e.message, 'error');
      }
    }
  }

  await loadPage(true);
}

export async function mountAudit(root) {
  clear(root);

  let nextCursor = null;

  const tbody = h('tbody');
  const moreBtn = h('button', { type: 'button', hidden: true, class: 'btn btn-ghost' }, 'Ещё');
  const table = h('table', { class: 'admin-table' },
    h('thead', null,
      h('tr', null,
        h('th', null, 'Дата'),
        h('th', null, 'Админ'),
        h('th', null, 'Действие'),
        h('th', null, 'Объект'),
        h('th', null, 'Данные'),
      ),
    ),
    tbody,
  );

  root.append(
    h('h2', { class: 'page-title' }, 'Журнал'),
    table,
    h('div', { class: 'admin-section admin-row' }, moreBtn),
  );

  moreBtn.addEventListener('click', () => loadPage(false));

  async function loadPage(reset) {
    if (reset) {
      nextCursor = null;
      clear(tbody);
    }
    const params = new URLSearchParams({ limit: '50' });
    if (nextCursor !== null) params.set('before_id', String(nextCursor));
    try {
      const data = await api('GET', '/admin/audit?' + params.toString());
      nextCursor = data?.next_cursor ?? null;
      for (const entry of data?.items ?? []) tbody.appendChild(auditRow(entry));
      moreBtn.hidden = nextCursor === null;
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  function auditRow(entry) {
    return h('tr', null,
      h('td', null, fmtDate(entry.created_at)),
      h('td', null, entry.admin_login ?? 'CLI'),
      h('td', null, h('span', { class: 'mono' }, String(entry.action))),
      h('td', { class: 'mono' }, entry.target === null || entry.target === undefined ? '—' : String(entry.target)),
      h('td', null, h('code', { class: 'admin-muted' }, payloadPreview(entry.payload))),
    );
  }

  function payloadPreview(payload) {
    let s;
    try {
      s = JSON.stringify(payload);
    } catch {
      s = String(payload);
    }
    if (s === undefined) s = 'undefined';
    if (s.length > 200) s = s.slice(0, 200) + '…';
    return s;
  }

  await loadPage(true);
}
