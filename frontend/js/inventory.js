import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { openModal } from './modal.js';
import { invItemCard, SLOT_RU, WHITE_SLOTS, BLACK_SLOTS } from './items.js';

const me = await initLayout({ auth: 'required', active: 'inventory' });

const main = h('main', { class: 'wrap-wide inventory' });
document.body.appendChild(main);

const whiteSlots = h('div', { class: 'inv-slots' });
const blackSlots = h('div', { class: 'inv-slots' });
const boardSlots = h('div', { class: 'inv-slots' });
const invWarning = h('p', { class: 'inv-warning', hidden: true },
  'Экипируйте скины на все фигуры и доску — без этого нельзя играть');
const equipCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Экипировка'),
  invWarning,
  h('h4', {}, 'Белые'),
  whiteSlots,
  h('h4', {}, 'Чёрные'),
  blackSlots,
  h('h4', {}, 'Доска'),
  boardSlots,
);

const kindSelect = h('select', { 'aria-label': 'Вид' },
  h('option', { value: '' }, 'Все'),
  h('option', { value: 'piece' }, 'Фигуры'),
  h('option', { value: 'board' }, 'Доски'),
  h('option', { value: 'case' }, 'Кейсы'),
);
const sortSelect = h('select', { 'aria-label': 'Сортировка' },
  h('option', { value: 'rarity' }, 'По редкости'),
  h('option', { value: 'value' }, 'По ценности'),
  h('option', { value: 'new' }, 'Новые'),
);
const grid = h('div', { class: 'item-grid' });
const itemsCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Предметы'),
  h('div', { class: 'inv-filters' }, kindSelect, sortSelect),
  grid,
);

main.append(
  h('h1', { class: 'page-title' }, 'Инвентарь'),
  equipCard,
  itemsCard,
);

let sort = 'rarity';

await loadAll();

kindSelect.addEventListener('change', () => loadItems());
sortSelect.addEventListener('change', () => {
  sort = sortSelect.value;
  loadItems();
});

async function loadAll() {
  await Promise.all([loadLoadout(), loadItems()]);
}

async function loadLoadout() {
  let loadout;
  try {
    loadout = await api('GET', '/loadout');
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  clear(whiteSlots);
  clear(blackSlots);
  clear(boardSlots);
  invWarning.hidden = !loadout.complete;
  for (const slot of WHITE_SLOTS) whiteSlots.appendChild(slotEl(slot, loadout[slot]));
  for (const slot of BLACK_SLOTS) blackSlots.appendChild(slotEl(slot, loadout[slot]));
  for (const slot of ['board']) boardSlots.appendChild(slotEl(slot, loadout[slot]));
}

function slotEl(slot, item) {
  let content;
  if (item) {
    content = invItemCard(item, {
      extra: h('button', {
        type: 'button',
        class: 'btn btn-ghost btn-sm',
        onClick: () => unequip(slot),
      }, 'Снять'),
    });
  } else {
    content = h('div', { class: 'slot-empty' }, 'Пусто');
  }
  return h('div', { class: 'inv-slot' },
    h('div', { class: 'inv-slot-label' }, SLOT_RU[slot]),
    content,
  );
}

async function unequip(slot) {
  try {
    await api('PUT', '/loadout/' + slot, { inventory_item_id: null });
    toast('Готово', 'success');
    await loadAll();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function loadItems() {
  const params = new URLSearchParams({ sort });
  if (kindSelect.value) params.set('kind', kindSelect.value);
  let items;
  try {
    items = await api('GET', '/inventory?' + params.toString());
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  clear(grid);
  for (const item of items) {
    const badge = item.status === 'listed' ? 'На маркете' : (item.equipped_slot ? 'Надето' : undefined);
    grid.appendChild(invItemCard(item, {
      badge,
      extra: itemActions(item),
    }));
  }
  if (!items.length) {
    grid.appendChild(h('p', { class: 'inv-empty' }, 'Инвентарь пуст.'));
    grid.appendChild(h('a', { href: '/cases.html', class: 'btn btn-gold btn-sm' }, 'Открыть кейс'));
  }
}

function itemActions(item) {
  const box = h('div', { class: 'item-actions' });
  const act = (label, fn) => {
    box.appendChild(h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onClick: fn }, label));
  };
  if (item.status === 'owned') {
    if (item.kind === 'case') {
      act('Открыть', () => {
        location.href = '/case.html?item=' + encodeURIComponent(item.id);
      });
    }
    if (item.kind === 'skin' && !item.equipped_slot) act('Надеть', () => equip(item));
    if (!item.bound) {
      act('Продать', () => sellModal(item));
      act('Подарить', () => giftModal(item));
    }
  } else if (item.status === 'listed') {
    act('Снять с продажи', () => unlist(item));
  }
  return box;
}

async function equip(item) {
  const slot = item.def.kind === 'board' ? 'board' : item.def.side + item.def.piece_type;
  try {
    await api('PUT', '/loadout/' + slot, { inventory_item_id: item.id });
    toast('Готово', 'success');
    await loadAll();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function sellModal(item) {
  const input = h('input', {
    id: 'sell-price',
    type: 'number',
    min: '1',
    max: '10000000',
    step: '1',
    'aria-label': 'Цена в кристаллах',
  });
  const body = h('div', { class: 'inventory' },
    h('div', { class: 'field' },
      h('label', { for: 'sell-price' }, 'Цена (кристаллы: от 1 до 10 000 000)'),
      input,
    ),
  );
  openModal({
    title: 'Продажа предмета',
    titleAnim: 'none',
    body,
    actions: [
      {
        label: 'Выставить',
        kind: 'gold',
        onClick: async () => {
          const n = Number(input.value);
          if (input.value === '' || !Number.isInteger(n) || n < 1 || n > 10000000) {
            toast('Цена от 1 до 10 000 000', 'error');
            return false;
          }
          try {
            await api('POST', '/market/listings', { item_id: item.id, price: n });
            toast('Готово', 'success');
            await loadAll();
          } catch (e) {
            toast(e.message, 'error');
            return false;
          }
        },
      },
    ],
  });
}

function giftModal(item) {
  const login = h('input', { id: 'gift-login', type: 'text', maxlength: '64', 'aria-label': 'Логин получателя' });
  const note = h('textarea', { id: 'gift-note', rows: '3', maxlength: '140', 'aria-label': 'Записка' });
  const body = h('div', { class: 'inventory' },
    h('div', { class: 'field' },
      h('label', { for: 'gift-login' }, 'Логин получателя'),
      login,
    ),
    h('div', { class: 'field' },
      h('label', { for: 'gift-note' }, 'Записка (необязательно)'),
      note,
    ),
  );
  openModal({
    title: 'Подарок',
    titleAnim: 'none',
    body,
    actions: [
      {
        label: 'Подарить',
        kind: 'gold',
        onClick: async () => {
          const toLogin = login.value.trim();
          if (!toLogin) {
            toast('Укажите логин получателя', 'error');
            return false;
          }
          const noteText = note.value.trim();
          try {
            await api('POST', '/gifts', {
              item_id: item.id,
              to_login: toLogin,
              note: noteText || null,
            });
            toast('Готово', 'success');
            await loadAll();
          } catch (e) {
            toast(e.message, 'error');
            return false;
          }
        },
      },
    ],
  });
}

async function unlist(item) {
  try {
    const listings = await api('GET', '/me/listings?status=active');
    const listing = listings.find((l) => l.item && l.item.id === item.id);
    if (!listing) {
      toast('Активный лот не найден', 'error');
      return;
    }
    await api('DELETE', '/market/listings/' + String(listing.id));
    toast('Готово', 'success');
    await loadAll();
  } catch (e) {
    toast(e.message, 'error');
  }
}
