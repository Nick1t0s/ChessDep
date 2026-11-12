import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { fmtCrystals } from './format.js';

await initLayout({ auth: 'required', active: '' });

const main = h('main', { class: 'wrap-wide trade-history' });
document.body.appendChild(main);

main.appendChild(h('h1', { class: 'page-title' }, 'История сделок'));

const urlParams = new URLSearchParams(location.search);
let currentDefId = urlParams.get('item_def_id') || '';
let currentDirection = urlParams.get('direction') || 'all';

// --- Сводка ---
const summaryGrid = h('div', { class: 'th-summary-grid' });
const summaryCard = h('div', { class: 'card th-summary' },
  h('h3', { class: 'card-title' }, 'Сводка сделок'),
  summaryGrid,
);
main.appendChild(summaryCard);

const summaryElements = {
  sold_count: makeSummaryItem('Продано', '0'),
  bought_count: makeSummaryItem('Куплено', '0'),
  gross_sales: makeSummaryItem('Продажи до комиссии', '0 ◈'),
  fees: makeSummaryItem('Комиссия', '0 ◈'),
  net_sales: makeSummaryItem('Чистая выручка', '0 ◈'),
  total_spent: makeSummaryItem('Всего потрачено', '0 ◈'),
};

function makeSummaryItem(label, defaultVal) {
  const valEl = h('b', { class: 'th-sum-val mono' }, defaultVal);
  const box = h('div', { class: 'th-sum-box' },
    h('span', { class: 'th-sum-label' }, label),
    valEl,
  );
  summaryGrid.appendChild(box);
  return valEl;
}

function updateSummary(summary) {
  if (!summary) return;
  summaryElements.sold_count.textContent = String(summary.sold_count ?? 0);
  summaryElements.bought_count.textContent = String(summary.bought_count ?? 0);
  summaryElements.gross_sales.textContent = fmtCrystals(summary.gross_sales ?? 0);
  summaryElements.fees.textContent = fmtCrystals(summary.fees ?? 0);
  summaryElements.net_sales.textContent = fmtCrystals(summary.net_sales ?? 0);
  summaryElements.total_spent.textContent = fmtCrystals(summary.total_spent ?? 0);
}

// --- Фильтры ---
const dirLabel = h('label', { for: 'th-dir-select', class: 'th-label' }, 'Направление');
const dirSelect = h('select', { id: 'th-dir-select', class: 'th-dir-select', 'aria-label': 'Направление сделок' },
  h('option', { value: 'all' }, 'Все направления'),
  h('option', { value: 'buy' }, 'Покупки'),
  h('option', { value: 'sell' }, 'Продажи'),
);
dirSelect.value = currentDirection;

const defLabel = h('label', { for: 'th-def-input', class: 'th-label' }, 'Скин');
const defInput = h('select', {
  id: 'th-def-input', class: 'th-def-input', 'aria-label': 'Фильтр по скину',
}, h('option', { value: '' }, 'Все скины'));
if (currentDefId) {
  defInput.appendChild(h('option', { value: currentDefId }, 'Выбранный скин'));
  defInput.value = currentDefId;
}
api('GET', '/item-defs').then((defs) => {
  const selectedId = currentDefId;
  for (const def of defs) {
    const option = [...defInput.options].find((el) => el.value === String(def.id));
    if (option) option.textContent = def.name;
    else defInput.appendChild(h('option', { value: String(def.id) }, def.name));
  }
  defInput.value = selectedId;
}).catch(() => { /* Фильтрация остаётся доступной через названия в истории. */ });

const filterBtn = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Применить');
const resetBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Сбросить');

const filtersCard = h('div', { class: 'card th-filters-card' },
  h('div', { class: 'th-filters' },
    dirLabel,
    dirSelect,
    defLabel,
    defInput,
    filterBtn,
    resetBtn,
  ),
);
main.appendChild(filtersCard);

// --- Таблица ---
const tableBody = h('tbody');
const emptyNote = h('div', { class: 'th-empty', hidden: true }, 'Сделок не найдено');
const loadingNote = h('div', { class: 'th-loading', hidden: true }, 'Загрузка…');
const errorNote = h('div', { class: 'th-error' });
const retryBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Повторить');
const errorWrap = h('div', { class: 'th-error-wrap', hidden: true }, errorNote, retryBtn);

const moreBtn = h('button', { type: 'button', class: 'btn btn-ghost btn-block', hidden: true }, 'Загрузить ещё');

const tableWrap = h('div', { class: 'table-wrap th-table-wrap' },
  h('table', { class: 'th-table' },
    h('thead', null, h('tr', null,
      h('th', null, 'Дата'),
      h('th', null, 'Предмет'),
      h('th', null, 'Направление'),
      h('th', null, 'Цена'),
      h('th', null, 'Комиссия'),
      h('th', null, 'Итого'),
    )),
    tableBody,
  ),
);

const listCard = h('div', { class: 'card th-list-card' },
  tableWrap,
  emptyNote,
  loadingNote,
  errorWrap,
  moreBtn,
);
main.appendChild(listCard);

let nextCursor = null;
let activeReqSeq = 0;
let pagingInFlight = false;
let lastFailedAppend = false;

function validateSkinId(val) {
  const s = (val ?? '').trim();
  if (!s) return '';
  const n = Number(s);
  if (!Number.isInteger(n) || n <= 0) return null;
  return String(n);
}

function setSkinFilter(defId) {
  if (![...defInput.options].some((el) => el.value === String(defId))) {
    defInput.appendChild(h('option', { value: String(defId) }, 'Выбранный скин'));
  }
  defInput.value = String(defId);
  currentDefId = String(defId);
  syncUrl();
  loadTrades(false);
}

function syncUrl() {
  const u = new URL(location.href);
  if (currentDefId) u.searchParams.set('item_def_id', currentDefId);
  else u.searchParams.delete('item_def_id');
  if (currentDirection && currentDirection !== 'all') u.searchParams.set('direction', currentDirection);
  else u.searchParams.delete('direction');
  history.replaceState(null, '', u.pathname + u.search);
}

filterBtn.addEventListener('click', () => {
  const parsed = validateSkinId(defInput.value);
  if (parsed === null) {
    toast('ID скина должен быть положительным целым числом', 'error');
    return;
  }
  currentDirection = dirSelect.value;
  currentDefId = parsed;
  defInput.value = parsed;
  syncUrl();
  loadTrades(false);
});

dirSelect.addEventListener('change', () => {
  currentDirection = dirSelect.value;
  syncUrl();
  loadTrades(false);
});

resetBtn.addEventListener('click', () => {
  dirSelect.value = 'all';
  defInput.value = '';
  currentDirection = 'all';
  currentDefId = '';
  syncUrl();
  loadTrades(false);
});

retryBtn.addEventListener('click', () => {
  loadTrades(lastFailedAppend);
});

moreBtn.addEventListener('click', () => {
  loadTrades(true);
});

function tradeRow(item) {
  const skinBtn = h('button', {
    type: 'button',
    class: 'th-skin-btn',
    title: 'Показать сделки с этим скином',
  }, item.item_name || ('Скин #' + item.item_def_id));
  skinBtn.addEventListener('click', () => setSkinFilter(item.item_def_id));

  const dirClass = item.direction === 'buy' ? 'dir-buy' : 'dir-sell';
  const dirText = item.direction === 'buy' ? 'Покупка' : 'Продажа';
  const feeText = item.fee > 0 ? fmtCrystals(item.fee) : '—';

  return h('tr', null,
    h('td', null, new Date(item.created_at).toLocaleString('ru-RU')),
    h('td', null, skinBtn),
    h('td', { class: dirClass }, dirText),
    h('td', { class: 'mono' }, fmtCrystals(item.price)),
    h('td', { class: 'mono' }, feeText),
    h('td', { class: 'mono' }, fmtCrystals(item.net)),
  );
}

async function loadTrades(append = false) {
  if (append && pagingInFlight) return;
  pagingInFlight = append;

  const seq = ++activeReqSeq;
  lastFailedAppend = false;

  if (!append) {
    clear(tableBody);
    nextCursor = null;
  }

  loadingNote.hidden = false;
  emptyNote.hidden = true;
  errorWrap.hidden = true;
  moreBtn.hidden = true;

  const params = new URLSearchParams();
  params.set('limit', '20');
  if (currentDirection && currentDirection !== 'all') params.set('direction', currentDirection);
  if (currentDefId) params.set('item_def_id', currentDefId);
  if (append && nextCursor !== null) params.set('before_id', String(nextCursor));

  try {
    const data = await api('GET', '/me/trades?' + params.toString());
    if (seq !== activeReqSeq) return;

    updateSummary(data.summary);

    for (const item of data.items || []) {
      tableBody.appendChild(tradeRow(item));
    }

    nextCursor = data.next_cursor ?? null;
    emptyNote.hidden = tableBody.children.length > 0;
    moreBtn.hidden = nextCursor === null;
  } catch (e) {
    if (seq !== activeReqSeq) return;
    lastFailedAppend = append;
    errorNote.textContent = e.message || 'Ошибка загрузки сделок';
    errorWrap.hidden = false;
    toast(e.message || 'Ошибка загрузки сделок', 'error');
    if (append) moreBtn.hidden = false;
  } finally {
    if (seq === activeReqSeq) {
      loadingNote.hidden = true;
      if (append) pagingInFlight = false;
    }
  }
}

loadTrades(false);
