import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { confirmModal, openModal } from '../modal.js';
import { fmtCrystals } from '../format.js';
import { skinPreview, SLOT_RU, WHITE_SLOTS, BLACK_SLOTS, RARITIES, RARITY_RU } from '../items.js';

const STATUS_RU = { draft: 'Черновик', released: 'Выпущена', retired: 'Снята' };

const DEFAULT_RARITY = { P: 'common', N: 'uncommon', B: 'uncommon', R: 'rare', Q: 'epic', K: 'legendary' };
const RARITY_VALUE = { common: 20, uncommon: 60, rare: 150, epic: 500, legendary: 1500, mythic: 5000 };
const DEFAULT_COLOR = { w: '#ffffff', b: '#ffc93c' };

let fieldSeq = 0;

function field(labelText, input) {
  const id = 'f-' + String(++fieldSeq);
  input.id = id;
  return h('div', { class: 'field' }, h('label', { for: id }, labelText), input);
}

function statusPill(status) {
  return h('span', { class: 'pill status-' + status }, STATUS_RU[status] ?? status);
}

export async function mount(root) {
  await renderList(root);
}

// ---------- список ----------

async function renderList(root) {
  clear(root);
  root.appendChild(h('h2', { class: 'page-title' }, 'Коллекции'));

  let collections;
  try {
    collections = await api('GET', '/admin/collections');
  } catch (e) {
    toast(e.message, 'error');
    return;
  }

  const tbody = h('tbody');
  for (const c of collections) {
    tbody.appendChild(h('tr', {},
      h('td', { class: 'mono' }, c.code),
      h('td', {}, c.name),
      h('td', {}, statusPill(c.status)),
      h('td', { class: 'mono' }, String(c.items_count)),
      h('td', {},
        h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => renderDetail(root, c.id) }, 'Открыть')),
    ));
  }

  root.appendChild(h('table', { class: 'admin-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'Код'),
      h('th', {}, 'Название'),
      h('th', {}, 'Статус'),
      h('th', {}, 'Скинов'),
      h('th', {}, ''),
    )),
    tbody,
  ));

  if (!collections.length) {
    root.appendChild(h('p', { class: 'admin-muted' }, 'Пока нет коллекций.'));
  }

  root.appendChild(h('div', { class: 'card admin-section' },
    h('h3', { class: 'card-title' }, 'Новая коллекция'),
    createCollectionForm(root),
  ));
}

function createCollectionForm(root) {
  const codeIn = h('input', { type: 'text', name: 'code', placeholder: 'winter-2026', required: true });
  const nameIn = h('input', { type: 'text', name: 'name', required: true });
  const descIn = h('textarea', { name: 'description', rows: 3 });

  const rows = [...WHITE_SLOTS, ...BLACK_SLOTS].map(makePiecesRow);

  const form = h('form', { class: 'admin-form' },
    field('Код', codeIn),
    field('Название', nameIn),
    field('Описание', descIn),
    h('table', { class: 'admin-table' },
      h('thead', {}, h('tr', {},
        h('th', {}, 'Фигура'),
        h('th', {}, 'Редкость'),
        h('th', {}, 'Ценность'),
        h('th', {}, 'Цвет'),
        h('th', {}, 'Цель апгрейда'),
      )),
      h('tbody', {}, ...rows.map((r) => r.tr)),
    ),
    h('div', { class: 'admin-row' },
      h('button', { type: 'submit', class: 'btn btn-gold' }, 'Создать')),
  );

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pieces = [];
    for (const row of rows) {
      const value = Number(row.valIn.value);
      if (!Number.isInteger(value) || value < 1 || !/^#[0-9a-fA-F]{6}$/.test(row.colorIn.value.trim())) {
        toast('Строка «' + SLOT_RU[row.slot] + '»: проверьте ценность и цвет', 'error');
        return;
      }
      pieces.push({
        side: row.slot[0],
        piece_type: row.slot[1],
        rarity: row.rarSel.value,
        value,
        asset: { type: 'stub', color: row.colorIn.value.trim() },
        is_upgrade_target: row.upIn.checked,
      });
    }
    try {
      const created = await api('POST', '/admin/collections', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        description: descIn.value.trim(),
        pieces,
      });
      toast('Готово', 'success');
      await renderDetail(root, created.id);
    } catch (err2) {
      toast(err2.message, 'error');
    }
  });

  return form;
}

function makePiecesRow(slot) {
  const side = slot[0];
  const pt = slot[1];

  const rarSel = h('select', { name: 'rarity-' + slot });
  for (const r of RARITIES) {
    rarSel.appendChild(h('option', { value: r }, RARITY_RU[r] ?? r));
  }
  rarSel.value = DEFAULT_RARITY[pt];

  const valIn = h('input', { type: 'number', name: 'value-' + slot, min: 1, value: RARITY_VALUE[DEFAULT_RARITY[pt]] });
  rarSel.addEventListener('change', () => {
    valIn.value = String(RARITY_VALUE[rarSel.value]);
  });

  const colorIn = h('input', { type: 'text', name: 'color-' + slot, value: DEFAULT_COLOR[side] });
  const upIn = h('input', { type: 'checkbox', name: 'target-' + slot, checked: true });

  const tr = h('tr', {},
    h('td', {}, SLOT_RU[slot]),
    h('td', {}, rarSel),
    h('td', {}, valIn),
    h('td', {}, colorIn),
    h('td', {}, upIn),
  );

  return { slot, tr, rarSel, valIn, colorIn, upIn };
}

// ---------- карточка ----------

async function renderDetail(root, id) {
  clear(root);

  let d;
  try {
    d = await api('GET', '/admin/collections/' + encodeURIComponent(id));
  } catch (e) {
    toast(e.message, 'error');
    await renderList(root);
    return;
  }

  root.appendChild(h('div', { class: 'admin-row' },
    h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => renderList(root) }, '← К списку'),
  ));
  root.appendChild(h('h2', { class: 'page-title' }, d.name, ' ', statusPill(d.status)));
  root.appendChild(h('p', { class: 'admin-muted' },
    d.code + (d.description ? ' · ' + d.description : '')));

  root.appendChild(actionsRow(root, d));
  root.appendChild(skinsSection(root, d));
}

function actionsRow(root, d) {
  const row = h('div', { class: 'admin-row' });
  if (d.status === 'draft') {
    row.appendChild(h('button', { type: 'button', class: 'btn btn-gold', onClick: () => releaseCollection(root, d) }, 'Выпустить'));
    row.appendChild(h('button', { type: 'button', class: 'btn btn-danger', onClick: () => deleteCollection(root, d) }, 'Удалить коллекцию'));
  } else if (d.status === 'released') {
    row.appendChild(h('button', { type: 'button', class: 'btn btn-ghost', onClick: () => retireCollection(root, d) }, 'Снять с выпуска'));
  }
  return row;
}

async function releaseCollection(root, d) {
  const ok = await confirmModal(
    'Выпустить коллекцию',
    'Выпустить коллекцию «' + d.name + '»? Она появится у игроков.',
    'Выпустить', 'gold');
  if (!ok) return;
  try {
    await api('POST', '/admin/collections/' + encodeURIComponent(d.id) + '/release');
    toast('Коллекция выпущена', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
  await renderDetail(root, d.id);
}

async function retireCollection(root, d) {
  const ok = await confirmModal(
    'Снять с выпуска',
    'Снять коллекцию «' + d.name + '» с выпуска? Все активные кейсы с её скинами будут закрыты.',
    'Снять', 'danger');
  if (!ok) return;
  try {
    await api('POST', '/admin/collections/' + encodeURIComponent(d.id) + '/retire');
    toast('Коллекция снята с выпуска', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
  await renderDetail(root, d.id);
}

async function deleteCollection(root, d) {
  const ok = await confirmModal(
    'Удалить коллекцию',
    'Удалить черновик «' + d.name + '»? Действие необратимо.',
    'Удалить', 'danger');
  if (!ok) return;
  try {
    await api('DELETE', '/admin/collections/' + encodeURIComponent(d.id));
    toast('Коллекция удалена', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
  await renderList(root);
}

// ---------- скины ----------

function skinsSection(root, d) {
  const section = h('div', { class: 'admin-section' }, h('h3', { class: 'card-title' }, 'Скины (12)'));

  const tbody = h('tbody');
  for (const def of d.items) {
    tbody.appendChild(h('tr', {},
      h('td', {}, skinPreview(def)),
      h('td', {}, SLOT_RU[def.side + def.piece_type] ?? (def.side + def.piece_type)),
      h('td', { class: 'mono' }, def.code),
      h('td', {}, def.name),
      h('td', {}, RARITY_RU[def.rarity] ?? def.rarity),
      h('td', { class: 'mono' }, fmtCrystals(def.value)),
      h('td', {}, def.is_upgrade_target ? 'Да' : 'Нет'),
      h('td', {},
        h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openEditModal(root, d, def) }, 'Изменить')),
    ));
  }

  section.appendChild(h('table', { class: 'admin-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'Превью'),
      h('th', {}, 'Фигура'),
      h('th', {}, 'Код'),
      h('th', {}, 'Название'),
      h('th', {}, 'Редкость'),
      h('th', {}, 'Ценность'),
      h('th', {}, 'Цель апгрейда'),
      h('th', {}, ''),
    )),
    tbody,
  ));

  return section;
}

function openEditModal(root, d, def) {
  const nameIn = h('input', { type: 'text', value: def.name });
  const valIn = h('input', { type: 'number', min: 1, value: def.value });
  const colorIn = h('input', { type: 'text', value: def.asset.color });
  const upIn = h('input', { type: 'checkbox', checked: def.is_upgrade_target });

  let rarField = null;
  let rarSel = null;
  if (d.status === 'draft') {
    rarSel = h('select', {});
    for (const r of RARITIES) {
      rarSel.appendChild(h('option', { value: r }, RARITY_RU[r] ?? r));
    }
    rarSel.value = def.rarity;
    rarField = field('Редкость', rarSel);
  }

  const body = h('div', { class: 'admin-form' },
    field('Название', nameIn),
    field('Ценность', valIn),
    field('Цвет фигуры', colorIn),
    field('Цель апгрейда', upIn),
    rarField,
  );

  openModal({
    title: 'Изменить скин ' + def.code,
    titleAnim: 'none',
    body,
    dismissible: true,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      {
        label: 'Сохранить',
        kind: 'gold',
        onClick: () => {
          const name = nameIn.value.trim();
          const value = Number(valIn.value);
          if (!name) {
            toast('Введите название', 'error');
            return false;
          }
          if (!Number.isInteger(value) || value < 1) {
            toast('Ценность должна быть целым числом ≥ 1', 'error');
            return false;
          }
          saveItemDef(root, d, def, { nameIn, valIn, colorIn, upIn, rarSel });
        },
      },
    ],
  });
}

async function saveItemDef(root, d, def, inputs) {
  const body = {};
  const name = inputs.nameIn.value.trim();
  const value = Number(inputs.valIn.value);
  body.name = name;
  body.value = value;

  body.asset = {
    type: 'stub',
    color: inputs.colorIn.value.trim() || def.asset.color,
  };

  body.is_upgrade_target = inputs.upIn.checked;
  if (d.status === 'draft' && inputs.rarSel) {
    body.rarity = inputs.rarSel.value;
  }

  try {
    await api('PATCH', '/admin/item-defs/' + encodeURIComponent(def.id), body);
    toast('Скин обновлён', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
  await renderDetail(root, d.id);
}
