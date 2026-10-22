import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { openModal, confirmModal } from '../modal.js';
import { fmtCrystals } from '../format.js';

const CASE_STATUS_RU = { draft: 'Черновик', active: 'Активен', closed: 'Закрыт' };
const COLL_STATUS_RU = { draft: 'Черновик', released: 'Выпущена', retired: 'Снята' };

let fieldSeq = 0;

function field(labelText, input) {
  const id = 'f-' + String(++fieldSeq);
  input.id = id;
  return h('div', { class: 'field' }, h('label', { for: id }, labelText), input);
}

function statusPill(status) {
  return h('span', { class: 'pill status-' + status }, CASE_STATUS_RU[status] ?? status);
}

export async function mount(root) {
  await render(root);
}

async function render(root) {
  clear(root);

  let cases;
  let defs;
  let collections;
  try {
    [cases, defs, collections] = await Promise.all([
      api('GET', '/admin/cases'),
      api('GET', '/admin/item-defs'),
      api('GET', '/admin/collections'),
    ]);
  } catch (e) {
    toast(e.message, 'error');
    return;
  }

  root.appendChild(h('h2', { class: 'page-title' }, 'Кейсы'));
  root.appendChild(buildCreateForm(root));

  if (!cases.length) {
    root.appendChild(h('p', { class: 'admin-muted' }, 'Кейсов пока нет'));
    return;
  }

  for (const cs of cases) {
    root.appendChild(buildCaseCard(root, cs, defs, collections));
  }
}

async function done(root) {
  toast('Готово', 'success');
  await render(root);
}

function buildCreateForm(root) {
  const codeIn = h('input', { name: 'code', required: true, maxlength: 64 });
  const nameIn = h('input', { name: 'name', required: true, maxlength: 128 });
  const priceIn = h('input', { name: 'price', type: 'number', min: 1, value: 100, required: true });
  const sortIn = h('input', { name: 'sort', type: 'number', value: 0, required: true });

  const form = h('form', { class: 'admin-form card admin-section' },
    h('h4', {}, 'Новый кейс'),
    field('Код', codeIn),
    field('Название', nameIn),
    field('Цена', priceIn),
    field('Порядок', sortIn),
    h('div', { class: 'admin-row' },
      h('button', { type: 'submit', class: 'btn btn-gold' }, 'Создать'),
    ),
  );

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('POST', '/admin/cases', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        price: Number(priceIn.value),
        sort: Number(sortIn.value),
      });
      await done(root);
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  return form;
}

function collectionsLine(cs) {
  const cols = cs.collections || [];
  if (!cols.length) return 'Без дропов';
  const names = cols.map(c => c.name);
  if (names.length === 1) return 'Коллекция ' + names[0];
  return 'Смешанный: ' + names.join(', ');
}

function buildCaseCard(root, cs, defs, collections) {
  const card = h('div', { class: 'card admin-section' });

  card.appendChild(h('h4', {}, cs.name, ' ', statusPill(cs.status)));
  card.appendChild(h('p', { class: 'admin-muted' },
    cs.code, ' · цена ', fmtCrystals(cs.price), ' · порядок ', String(cs.sort),
  ));
  card.appendChild(h('p', { class: 'admin-muted' }, collectionsLine(cs)));

  card.appendChild(buildDropsTable(cs, defs));
  card.appendChild(buildActions(root, cs, collections, defs));

  return card;
}

function buildDropsTable(cs, defs) {
  const drops = cs.drops || [];
  if (!drops.length) {
    return h('p', { class: 'admin-muted' }, 'Дропов нет');
  }
  const nameById = new Map();
  for (const def of defs) nameById.set(def.id, def.name);
  const sum = drops.reduce((acc, d) => acc + Number(d.weight || 0), 0);

  const tbody = h('tbody', {});
  for (const d of drops) {
    tbody.appendChild(h('tr', {},
      h('td', {}, nameById.get(d.item_def_id) || '#' + String(d.item_def_id)),
      h('td', { class: 'mono' }, String(d.weight)),
      h('td', { class: 'mono' }, (sum > 0 ? ((Number(d.weight) / sum) * 100).toFixed(2) : '0.00') + '%'),
    ));
  }
  return h('table', { class: 'admin-table' },
    h('thead', {},
      h('tr', {},
        h('th', {}, 'Скин'),
        h('th', {}, 'Вес'),
        h('th', {}, 'Шанс'),
      ),
    ),
    tbody,
  );
}

function buildActions(root, cs, collections, defs) {
  const row = h('div', { class: 'admin-row' });

  row.appendChild(h('button', {
    type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openEditModal(root, cs),
  }, 'Изменить'));

  if (cs.status === 'draft') {
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openAutoWeightsModal(root, cs, collections),
    }, 'Автовеса'));
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openManualDropsModal(root, cs, defs),
    }, 'Дропы вручную'));
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => postAction(root, cs, 'activate'),
    }, 'Активировать'));
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-danger btn-sm', onClick: async () => {
        const ok = await confirmModal('Удалить кейс', 'Удалить кейс «' + cs.name + '»?', 'Удалить', 'danger');
        if (!ok) return;
        try {
          await api('DELETE', '/admin/cases/' + cs.id);
          await done(root);
        } catch (err) {
          toast(err.message, 'error');
        }
      },
    }, 'Удалить'));
  } else if (cs.status === 'active') {
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: async () => {
        const ok = await confirmModal('Закрыть кейс', 'Кейс перестанет открываться.', 'Закрыть', 'danger');
        if (!ok) return;
        await postAction(root, cs, 'close');
      },
    }, 'Закрыть'));
  } else if (cs.status === 'closed') {
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => postAction(root, cs, 'activate'),
    }, 'Активировать'));
  }

  return row;
}

async function postAction(root, cs, action) {
  try {
    await api('POST', '/admin/cases/' + cs.id + '/' + action);
    await done(root);
  } catch (err) {
    toast(err.message, 'error');
  }
}

function openEditModal(root, cs) {
  const nameIn = h('input', { name: 'name', required: true, maxlength: 128, value: cs.name });
  const priceIn = h('input', { name: 'price', type: 'number', min: 1, value: cs.price, required: true });
  const sortIn = h('input', { name: 'sort', type: 'number', value: cs.sort, required: true });

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() },
    field('Название', nameIn),
    field('Цена', priceIn),
    field('Порядок', sortIn),
  );

  openModal({
    title: 'Изменить кейс',
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      {
        label: 'Сохранить', kind: 'gold',
        onClick: async () => {
          try {
            await api('PATCH', '/admin/cases/' + cs.id, {
              name: nameIn.value.trim(),
              price: Number(priceIn.value),
              sort: Number(sortIn.value),
            });
            await done(root);
            return true;
          } catch (err) {
            toast(err.message, 'error');
            return false;
          }
        },
      },
    ],
  });
}

function openAutoWeightsModal(root, cs, collections) {
  const boxes = [];
  const rows = [];
  for (const c of collections) {
    if (c.status === 'retired') continue;
    const input = h('input', { type: 'checkbox', name: 'col-' + String(c.id) });
    boxes.push({ id: c.id, input });
    rows.push(h('label', { class: 'admin-row' },
      input,
      c.name + ' (' + c.code + ') — ' + (COLL_STATUS_RU[c.status] ?? c.status),
    ));
  }

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() }, ...rows);

  openModal({
    title: 'Автовеса',
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      {
        label: 'Заполнить', kind: 'gold',
        onClick: async () => {
          const collectionIds = boxes
            .filter(b => b.input.checked)
            .map(b => Number(b.id));
          if (!collectionIds.length) {
            toast('Выберите хотя бы одну коллекцию', 'error');
            return false;
          }
          try {
            await api('POST', '/admin/cases/' + cs.id + '/drops/auto', { collection_ids: collectionIds });
            await done(root);
            return true;
          } catch (err) {
            toast(err.message, 'error');
            return false;
          }
        },
      },
    ],
  });
}

function openManualDropsModal(root, cs, defs) {
  const weightByDef = new Map();
  for (const d of cs.drops || []) weightByDef.set(d.item_def_id, Number(d.weight) || 0);

  const inputs = [];
  const bodies = [];
  let currentName = null;
  let tbody = null;
  for (const def of defs) {
    const groupName = def.collection ? def.collection.name : '';
    if (groupName !== currentName) {
      currentName = groupName;
      tbody = h('tbody', {},
        h('tr', { class: 'admin-muted' }, h('td', {}, groupName), h('td', {})),
      );
      bodies.push(tbody);
    }
    const input = h('input', {
      type: 'number', min: 0, step: 1,
      value: weightByDef.get(def.id) || 0,
      name: 'weight-' + String(def.id),
    });
    inputs.push({ def, input });
    tbody.appendChild(h('tr', {},
      h('td', {}, def.name),
      h('td', {}, input),
    ));
  }

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() },
    h('table', { class: 'admin-table' },
      h('thead', {},
        h('tr', {},
          h('th', {}, 'Скин'),
          h('th', {}, 'Вес'),
        ),
      ),
      ...bodies,
    ),
  );

  openModal({
    title: 'Дропы вручную',
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      {
        label: 'Сохранить', kind: 'gold',
        onClick: async () => {
          const drops = [];
          for (const { def, input } of inputs) {
            const weight = Number(input.value);
            if (!Number.isInteger(weight) || weight < 0) {
              toast('Вес должен быть целым числом ≥ 0', 'error');
              return false;
            }
            if (weight > 0) drops.push({ item_def_id: def.id, weight });
          }
          try {
            await api('PUT', '/admin/cases/' + cs.id + '/drops', drops);
            await done(root);
            return true;
          } catch (err) {
            toast(err.message, 'error');
            return false;
          }
        },
      },
    ],
  });
}
