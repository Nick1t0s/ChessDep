import { api, apiUpload } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { confirmModal, openModal } from '../modal.js';
import { fmtCrystals } from '../format.js';
import { skinPreview, SLOT_RU, WHITE_SLOTS, BLACK_SLOTS, RARITIES, RARITY_RU, EXTERIOR_RU } from '../items.js';

const SET_STATUS_RU = { draft: 'Черновик', released: 'Выпущен', retired: 'Снят' };

const DEFAULT_RARITY = { P: 'common', N: 'uncommon', B: 'uncommon', R: 'rare', Q: 'epic', K: 'legendary' };
const RARITY_VALUE = { common: 20, uncommon: 60, rare: 150, epic: 500, legendary: 1500, mythic: 5000 };
const EXTERIORS = ['FN', 'MW', 'FT', 'WW', 'BS'];

let fieldSeq = 0;

function field(labelText, input) {
  const id = 'f-' + String(++fieldSeq);
  input.id = id;
  return h('div', { class: 'field' }, h('label', { for: id }, labelText), input);
}

// Поле PNG скина: файл сразу грузится на сервер, picker.image — id картинки или null.
function imagePicker(kind, initialImage) {
  const picker = { image: initialImage, el: null };
  const preview = h('span', { class: 'admin-skin-preview' });
  const input = h('input', { type: 'file' });
  input.accept = 'image/png';
  function showPreview() {
    clear(preview);
    if (picker.image !== null) preview.appendChild(skinPreview({ kind, asset: { type: 'png', image: picker.image } }));
  }
  input.addEventListener('change', async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const res = await apiUpload('/admin/skin-images?kind=' + kind, file);
      picker.image = res.image;
      showPreview();
    } catch (err) {
      input.value = '';
      toast(err.message, 'error');
    }
  });
  showPreview();
  picker.el = h('div', { class: 'admin-skin-picker' }, input, preview);
  return picker;
}

// Пять обязательных картинок качеств; initial — asset.exteriors или null.
function exteriorPickers(kind, initial) {
  const pickers = {};
  for (const ext of EXTERIORS) pickers[ext] = imagePicker(kind, initial?.[ext] ?? null);
  return pickers;
}

// asset из основной картинки и картинок всех качеств; null, если чего-то не хватает.
function buildAsset(picker, extPickers) {
  if (picker.image === null) return null;
  const exteriors = {};
  for (const ext of EXTERIORS) {
    if (extPickers[ext].image === null) return null;
    exteriors[ext] = extPickers[ext].image;
  }
  return { type: 'png', image: picker.image, exteriors };
}

function setPill(status) {
  return h('span', { class: 'pill status-' + status }, SET_STATUS_RU[status] ?? status);
}

function baseMark() {
  return h('span', { class: 'pill' }, 'Базовый');
}

async function done(root, screen, id) {
  toast('Готово', 'success');
  if (screen === 'detail') await renderDetail(root, id);
  else await renderList(root);
}

export async function mount(root) {
  await renderList(root);
}

// ---------- список ----------

async function renderList(root) {
  clear(root);
  root.appendChild(h('h2', { class: 'page-title' }, 'Наборы'));

  let sets;
  try {
    sets = await api('GET', '/admin/sets');
  } catch (e) {
    toast(e.message, 'error');
    return;
  }

  const tbody = h('tbody');
  for (const s of sets) {
    tbody.appendChild(h('tr', { onClick: () => renderDetail(root, s.id) },
      h('td', { class: 'mono' }, s.code),
      h('td', {}, s.name, ' ', s.is_base ? baseMark() : null),
      h('td', {}, setPill(s.status)),
      h('td', { class: 'mono' }, String(s.collections_count)),
      h('td', { class: 'mono' }, String(s.boards_count)),
    ));
  }

  root.appendChild(h('table', { class: 'admin-table' },
    h('thead', {}, h('tr', {},
      h('th', {}, 'Код'),
      h('th', {}, 'Название'),
      h('th', {}, 'Статус'),
      h('th', {}, 'Коллекций'),
      h('th', {}, 'Досок'),
    )),
    tbody,
  ));

  if (!sets.length) {
    root.appendChild(h('p', { class: 'admin-muted' }, 'Пока нет наборов.'));
  }

  root.appendChild(h('div', { class: 'card admin-section' },
    h('h3', { class: 'card-title' }, 'Новый набор'),
    createSetForm(root),
  ));
}

function createSetForm(root) {
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
      const created = await api('POST', '/admin/sets', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        description: descIn.value.trim(),
      });
      toast('Готово', 'success');
      await renderDetail(root, created.id);
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  return form;
}

// ---------- карточка набора ----------

async function renderDetail(root, id) {
  clear(root);

  let d;
  try {
    d = await api('GET', '/admin/sets/' + encodeURIComponent(id));
  } catch (e) {
    toast(e.message, 'error');
    await renderList(root);
    return;
  }

  root.appendChild(h('div', { class: 'admin-row' },
    h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => renderList(root) }, '← К списку'),
  ));
  root.appendChild(h('h2', { class: 'page-title' },
    d.name, ' ', setPill(d.status), ' ', d.is_base ? baseMark() : null));
  root.appendChild(h('p', { class: 'admin-muted' },
    d.code + (d.description ? ' · ' + d.description : '')));

  root.appendChild(actionsRow(root, d));
  root.appendChild(collectionsSection(root, d));
  root.appendChild(boardsSection(root, d));
}

function actionsRow(root, d) {
  const row = h('div', { class: 'admin-row' });
  if (d.status === 'draft') {
    row.appendChild(h('button', { type: 'button', class: 'btn btn-gold', onClick: () => releaseSet(root, d) }, 'Выпустить'));
    row.appendChild(h('button', { type: 'button', class: 'btn btn-danger', onClick: () => deleteSet(root, d) }, 'Удалить набор'));
  } else if (d.status === 'released' && !d.is_base) {
    row.appendChild(h('button', { type: 'button', class: 'btn btn-ghost', onClick: () => retireSet(root, d) }, 'Снять с выпуска'));
  }
  return row;
}

async function releaseSet(root, d) {
  try {
    await api('POST', '/admin/sets/' + encodeURIComponent(d.id) + '/release');
  } catch (e) {
    toast(e.message, 'error');
  }
  await renderDetail(root, d.id);
}

async function retireSet(root, d) {
  const ok = await confirmModal(
    'Снять с выпуска',
    'Все кейсы в продаже с его скинами будут сняты с продажи.',
    'Снять', 'danger');
  if (!ok) return;
  try {
    await api('POST', '/admin/sets/' + encodeURIComponent(d.id) + '/retire');
    toast('Готово', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
  await renderDetail(root, d.id);
}

async function deleteSet(root, d) {
  const ok = await confirmModal(
    'Удалить набор',
    'Удалить черновик «' + d.name + '»? Действие необратимо.',
    'Удалить', 'danger');
  if (!ok) return;
  try {
    await api('DELETE', '/admin/sets/' + encodeURIComponent(d.id));
  } catch (e) {
    toast(e.message, 'error');
    await renderDetail(root, d.id);
    return;
  }
  await done(root, 'list');
}

// ---------- коллекции ----------

function collectionsSection(root, d) {
  const section = h('div', { class: 'admin-section' }, h('h3', { class: 'card-title' }, 'Коллекции'));

  if (!d.collections.length) {
    section.appendChild(h('p', { class: 'admin-muted' }, 'Коллекций нет.'));
  }

  for (const c of d.collections) {
    const card = h('div', { class: 'card' },
      h('h4', {}, c.name),
      h('p', { class: 'admin-muted' }, c.code),
      collectionSkinsTable(root, d, c),
    );
    if (d.status === 'draft') {
      card.appendChild(h('div', { class: 'admin-row' },
        h('button', {
          type: 'button', class: 'btn btn-danger btn-sm', onClick: () => deleteCollection(root, d, c),
        }, 'Удалить коллекцию'),
      ));
    }
    section.appendChild(card);
  }

  if (d.status === 'draft') {
    section.appendChild(h('div', { class: 'card admin-section' },
      h('h3', { class: 'card-title' }, 'Новая коллекция'),
      createCollectionForm(root, d),
    ));
  }

  return section;
}

function collectionSkinsTable(root, d, c) {
  const tbody = h('tbody');
  for (const def of c.items) {
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

  return h('table', { class: 'admin-table' },
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
  );
}

function createCollectionForm(root, d) {
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
        h('th', {}, 'Картинка 128×128'),
        ...EXTERIORS.map((ext) => h('th', {}, EXTERIOR_RU[ext])),
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
      if (!Number.isInteger(value) || value < 1 || buildAsset(row.picker, row.extPickers) === null) {
        toast('Строка «' + SLOT_RU[row.slot] + '»: проверьте ценность и загрузите все картинки', 'error');
        return;
      }
      pieces.push({
        side: row.slot[0],
        piece_type: row.slot[1],
        rarity: row.rarSel.value,
        value,
        asset: buildAsset(row.picker, row.extPickers),
        is_upgrade_target: row.upIn.checked,
      });
    }
    try {
      await api('POST', '/admin/sets/' + encodeURIComponent(d.id) + '/collections', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        description: descIn.value.trim(),
        pieces,
      });
      toast('Готово', 'success');
      await renderDetail(root, d.id);
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  return form;
}

function makePiecesRow(slot) {
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

  const picker = imagePicker('piece', null);
  const extPickers = exteriorPickers('piece', null);
  const upIn = h('input', { type: 'checkbox', name: 'target-' + slot, checked: true });

  const tr = h('tr', {},
    h('td', {}, SLOT_RU[slot]),
    h('td', {}, rarSel),
    h('td', {}, valIn),
    h('td', {}, picker.el),
    ...EXTERIORS.map((ext) => h('td', {}, extPickers[ext].el)),
    h('td', {}, upIn),
  );

  return { slot, tr, rarSel, valIn, picker, extPickers, upIn };
}

async function deleteCollection(root, d, c) {
  const ok = await confirmModal(
    'Удалить коллекцию',
    'Удалить коллекцию «' + c.name + '»? Её скины будут удалены безвозвратно.',
    'Удалить', 'danger');
  if (!ok) return;
  try {
    await api('DELETE', '/admin/collections/' + encodeURIComponent(c.id));
    toast('Готово', 'success');
    await renderDetail(root, d.id);
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ---------- доски ----------

function boardsSection(root, d) {
  const section = h('div', { class: 'admin-section' }, h('h3', { class: 'card-title' }, 'Доски'));

  if (!d.boards.length) {
    section.appendChild(h('p', { class: 'admin-muted' }, 'Досок нет.'));
  } else {
    const tbody = h('tbody');
    for (const def of d.boards) {
      const tds = [
        h('td', {}, skinPreview(def)),
        h('td', { class: 'mono' }, def.code),
        h('td', {}, def.name),
        h('td', {}, RARITY_RU[def.rarity] ?? def.rarity),
        h('td', { class: 'mono' }, fmtCrystals(def.value)),
        h('td', {},
          h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openEditModal(root, d, def) }, 'Изменить')),
      ];
      if (d.status === 'draft') {
        tds.push(h('td', {},
          h('button', { type: 'button', class: 'btn btn-danger btn-sm', onClick: () => deleteBoard(root, d, def) }, 'Удалить')));
      }
      tbody.appendChild(h('tr', {}, ...tds));
    }

    const headCells = [
      h('th', {}, 'Превью'),
      h('th', {}, 'Код'),
      h('th', {}, 'Название'),
      h('th', {}, 'Редкость'),
      h('th', {}, 'Ценность'),
      h('th', {}, ''),
    ];
    if (d.status === 'draft') headCells.push(h('th', {}, ''));

    section.appendChild(h('table', { class: 'admin-table' },
      h('thead', {}, h('tr', {}, ...headCells)),
      tbody,
    ));
  }

  if (d.status === 'draft') {
    section.appendChild(h('div', { class: 'card admin-section' },
      h('h3', { class: 'card-title' }, 'Новая доска'),
      createBoardForm(root, d),
    ));
  }

  return section;
}

function createBoardForm(root, d) {
  const codeIn = h('input', { type: 'text', name: 'code', required: true });
  const nameIn = h('input', { type: 'text', name: 'name', required: true });
  const rarSel = h('select', { name: 'rarity' });
  for (const r of RARITIES) {
    rarSel.appendChild(h('option', { value: r }, RARITY_RU[r] ?? r));
  }
  rarSel.value = 'common';
  const valIn = h('input', { type: 'number', name: 'value', min: 1, value: RARITY_VALUE[rarSel.value] });
  rarSel.addEventListener('change', () => {
    valIn.value = String(RARITY_VALUE[rarSel.value]);
  });
  const picker = imagePicker('board', null);
  const extPickers = exteriorPickers('board', null);
  const upIn = h('input', { type: 'checkbox', name: 'target', checked: true });

  const form = h('form', { class: 'admin-form' },
    field('Код', codeIn),
    field('Название', nameIn),
    field('Редкость', rarSel),
    field('Ценность', valIn),
    field('Картинка 1088×1088', picker.el),
    ...EXTERIORS.map((ext) => field('Картинка: ' + EXTERIOR_RU[ext], extPickers[ext].el)),
    field('Цель апгрейда', upIn),
    h('div', { class: 'admin-row' },
      h('button', { type: 'submit', class: 'btn btn-gold' }, 'Создать')),
  );

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = Number(valIn.value);
    if (!Number.isInteger(value) || value < 1) {
      toast('Ценность должна быть целым числом ≥ 1', 'error');
      return;
    }
    const asset = buildAsset(picker, extPickers);
    if (asset === null) {
      toast('Загрузите основную картинку и картинки всех качеств', 'error');
      return;
    }
    try {
      await api('POST', '/admin/sets/' + encodeURIComponent(d.id) + '/boards', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        rarity: rarSel.value,
        value,
        asset,
        is_upgrade_target: upIn.checked,
      });
      toast('Готово', 'success');
      await renderDetail(root, d.id);
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  return form;
}

async function deleteBoard(root, d, def) {
  const ok = await confirmModal(
    'Удалить доску',
    'Удалить доску «' + def.name + '»? Действие необратимо.',
    'Удалить', 'danger');
  if (!ok) return;
  try {
    await api('DELETE', '/admin/item-defs/' + encodeURIComponent(def.id));
    toast('Готово', 'success');
    await renderDetail(root, d.id);
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ---------- скины ----------

function openEditModal(root, d, def) {
  const isBoard = def.kind === 'board';
  const nameIn = h('input', { type: 'text', value: def.name });
  const valIn = h('input', { type: 'number', min: 1, value: def.value });
  const upIn = h('input', { type: 'checkbox', checked: def.is_upgrade_target });

  const picker = imagePicker(def.kind, def.asset.image);
  const extPickers = exteriorPickers(def.kind, def.asset.exteriors);

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
    field(isBoard ? 'Картинка 1088×1088' : 'Картинка 128×128', picker.el),
    ...EXTERIORS.map((ext) => field('Картинка: ' + EXTERIOR_RU[ext], extPickers[ext].el)),
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
        onClick: async () => {
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
          const asset = buildAsset(picker, extPickers);
          if (asset === null) {
            toast('Загрузите основную картинку и картинки всех качеств', 'error');
            return false;
          }
          try {
            await saveItemDef(d, def, { name, value, upIn, rarSel, asset });
            toast('Готово', 'success');
            await renderDetail(root, d.id);
            return true;
          } catch (e) {
            toast(e.message, 'error');
            return false;
          }
        },
      },
    ],
  });
}

async function saveItemDef(d, def, { name, value, upIn, rarSel, asset }) {
  const body = {
    name,
    value,
    is_upgrade_target: upIn.checked,
    asset,
  };
  if (d.status === 'draft' && rarSel) {
    body.rarity = rarSel.value;
  }
  await api('PATCH', '/admin/item-defs/' + encodeURIComponent(def.id), body);
}
