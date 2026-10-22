import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { confirmModal, openModal } from '../modal.js';
import { fmtCrystals, PIECE_NAME_RU } from '../format.js';
import { skinPreview, RARITIES, RARITY_RU } from '../items.js';
import { renderCasesSection } from './cases.js';

const STATUS_RU = { draft: 'Черновик', released: 'Выпущена', retired: 'Снята' };

let fieldSeq = 0;

function field(labelText, input) {
  const id = 'f-' + String(++fieldSeq);
  input.id = id;
  return h('div', { class: 'field' }, h('label', { for: id }, labelText), input);
}

function statusPill(status) {
  return h('span', { class: 'pill status-' + status }, STATUS_RU[status] ?? status);
}

function kindRu(def) {
  if (def.kind === 'board_skin') return 'Доска';
  return 'Фигура ' + (PIECE_NAME_RU[def.piece_type] ?? def.piece_type ?? '');
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
      h('td', { class: 'mono' }, String(c.cases_count)),
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
      h('th', {}, 'Кейсов'),
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

  const form = h('form', { class: 'admin-form' },
    field('Код', codeIn),
    field('Название', nameIn),
    field('Описание', descIn),
    h('div', { class: 'admin-row' },
      h('button', { type: 'submit', class: 'btn btn-gold' }, 'Создать')),
  );

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const created = await api('POST', '/admin/collections', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        description: descIn.value.trim(),
      });
      toast('Коллекция создана', 'success');
      await renderDetail(root, created.id);
    } catch (err2) {
      toast(err2.message, 'error');
    }
  });

  return form;
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

  const casesBox = h('div', { class: 'admin-section' });
  root.appendChild(casesBox);
  renderCasesSection(casesBox, d, () => renderDetail(root, id));
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
    'Снять коллекцию «' + d.name + '» с выпуска?',
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
  const section = h('div', { class: 'admin-section' }, h('h3', { class: 'card-title' }, 'Скины'));

  const tbody = h('tbody');
  for (const def of d.items) {
    const btns = h('td', {},
      h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openEditModal(root, d, def) }, 'Изменить'),
      d.status === 'draft'
        ? h('button', { type: 'button', class: 'btn btn-danger btn-sm', onClick: () => deleteItemDef(root, d, def) }, 'Удалить')
        : null,
    );
    tbody.appendChild(h('tr', {},
      h('td', {}, skinPreview(def)),
      h('td', { class: 'mono' }, def.code),
      h('td', {}, def.name),
      h('td', {}, kindRu(def)),
      h('td', {}, RARITY_RU[def.rarity] ?? def.rarity),
      h('td', { class: 'mono' }, fmtCrystals(def.value)),
      h('td', {}, def.is_upgrade_target ? 'Да' : 'Нет'),
      btns,
    ));
  }

  section.appendChild(h('table', { class: 'admin-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'Превью'),
      h('th', {}, 'Код'),
      h('th', {}, 'Название'),
      h('th', {}, 'Вид'),
      h('th', {}, 'Редкость'),
      h('th', {}, 'Ценность'),
      h('th', {}, 'Цель апгрейда'),
      h('th', {}, ''),
    )),
    tbody,
  ));

  section.appendChild(h('h3', { class: 'card-title' }, 'Новый скин'));
  section.appendChild(newSkinForm(root, d));
  return section;
}

function newSkinForm(root, d) {
  const codeIn = h('input', { type: 'text', name: 'code', required: true });
  const nameIn = h('input', { type: 'text', name: 'name', required: true });

  const kindSel = h('select', { name: 'kind' },
    h('option', { value: 'piece_skin' }, 'Фигура'),
    h('option', { value: 'board_skin' }, 'Доска'),
  );

  const ptSel = h('select', { name: 'piece_type' });
  for (const pt of ['P', 'N', 'B', 'R', 'Q', 'K']) {
    ptSel.appendChild(h('option', { value: pt }, PIECE_NAME_RU[pt]));
  }

  const rarSel = h('select', { name: 'rarity' });
  for (const r of RARITIES) {
    rarSel.appendChild(h('option', { value: r }, RARITY_RU[r] ?? r));
  }

  const valIn = h('input', { type: 'number', name: 'value', min: 1, value: 20 });
  const colorIn = h('input', { type: 'text', name: 'color', value: '#ffffff' });
  const lightIn = h('input', { type: 'text', name: 'light', value: '#ffffff' });
  const darkIn = h('input', { type: 'text', name: 'dark', value: '#e5e5e5' });
  const upIn = h('input', { type: 'checkbox', name: 'is_upgrade_target', checked: true });

  const ptField = field('Тип фигуры', ptSel);
  const colorField = field('Цвет фигуры', colorIn);
  const lightField = field('Светлые клетки', lightIn);
  const darkField = field('Тёмные клетки', darkIn);

  const syncKind = () => {
    const board = kindSel.value === 'board_skin';
    ptField.hidden = board;
    colorField.hidden = board;
    lightField.hidden = !board;
    darkField.hidden = !board;
  };
  kindSel.addEventListener('change', syncKind);
  syncKind();

  const form = h('form', { class: 'admin-form' },
    field('Код', codeIn),
    field('Название', nameIn),
    field('Вид', kindSel),
    ptField,
    field('Редкость', rarSel),
    field('Ценность', valIn),
    colorField,
    lightField,
    darkField,
    field('Цель апгрейда', upIn),
    h('div', { class: 'admin-row' },
      h('button', { type: 'submit', class: 'btn btn-gold' }, 'Добавить')),
  );

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const kind = kindSel.value;
    const value = Number(valIn.value);
    if (!codeIn.value.trim() || !nameIn.value.trim()) {
      toast('Заполните код и название', 'error');
      return;
    }
    if (!Number.isInteger(value) || value < 1) {
      toast('Ценность должна быть целым числом ≥ 1', 'error');
      return;
    }
    const body = {
      code: codeIn.value.trim(),
      name: nameIn.value.trim(),
      kind,
      piece_type: kind === 'piece_skin' ? ptSel.value : null,
      rarity: rarSel.value,
      value,
      asset: kind === 'piece_skin'
        ? { type: 'stub', color: colorIn.value.trim() || colorIn.placeholder || '#ffffff' }
        : { type: 'stub', light: lightIn.value.trim() || '#ffffff', dark: darkIn.value.trim() || '#e5e5e5' },
      is_upgrade_target: upIn.checked,
    };
    try {
      await api('POST', '/admin/collections/' + encodeURIComponent(d.id) + '/items', body);
      toast('Скин добавлен', 'success');
      await renderDetail(root, d.id);
    } catch (err2) {
      toast(err2.message, 'error');
    }
  });

  return form;
}

function openEditModal(root, d, def) {
  const nameIn = h('input', { type: 'text', value: def.name });
  const valIn = h('input', { type: 'number', min: 1, value: def.value });

  let colorField = null;
  let lightField = null;
  let darkField = null;
  let colorIn = null;
  let lightIn = null;
  let darkIn = null;
  if (def.kind === 'board_skin') {
    lightIn = h('input', { type: 'text', value: def.asset.light });
    darkIn = h('input', { type: 'text', value: def.asset.dark });
    lightField = field('Светлые клетки', lightIn);
    darkField = field('Тёмные клетки', darkIn);
  } else {
    colorIn = h('input', { type: 'text', value: def.asset.color });
    colorField = field('Цвет фигуры', colorIn);
  }

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
    colorField,
    lightField,
    darkField,
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
          saveItemDef(root, d, def, { nameIn, valIn, colorIn, lightIn, darkIn, upIn, rarSel });
        },
      },
    ],
  });
}

async function saveItemDef(root, d, def, inputs) {
  const body = {};
  const name = inputs.nameIn.value.trim();
  const value = Number(inputs.valIn.value);
  if (name !== def.name) body.name = name;
  if (value !== def.value) body.value = value;

  if (def.kind === 'board_skin') {
    body.asset = {
      type: 'stub',
      light: inputs.lightIn.value.trim() || def.asset.light,
      dark: inputs.darkIn.value.trim() || def.asset.dark,
    };
  } else {
    body.asset = {
      type: 'stub',
      color: inputs.colorIn.value.trim() || def.asset.color,
    };
  }

  if (inputs.upIn.checked !== def.is_upgrade_target) {
    body.is_upgrade_target = inputs.upIn.checked;
  }
  if (d.status === 'draft' && inputs.rarSel && inputs.rarSel.value !== def.rarity) {
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

async function deleteItemDef(root, d, def) {
  const ok = await confirmModal(
    'Удалить скин',
    'Удалить скин «' + def.name + '» (' + def.code + ')?',
    'Удалить', 'danger');
  if (!ok) return;
  try {
    await api('DELETE', '/admin/item-defs/' + encodeURIComponent(def.id));
    toast('Скин удалён', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
  await renderDetail(root, d.id);
}
