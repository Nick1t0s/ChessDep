import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { openModal, confirmModal } from '../modal.js';
import { fmtCrystals } from '../format.js';
import { CASE_KIND_RU } from '../items.js';

const CASE_STATUS_RU = { draft: 'Черновик', on_sale: 'В продаже', off_sale: 'Снят с продажи' };
const SET_STATUS_RU = { draft: 'Черновик', released: 'Выпущен', retired: 'Снят' };

let fieldSeq = 0;

function field(labelText, input) {
  const id = 'f-' + String(++fieldSeq);
  input.id = id;
  return h('div', { class: 'field' }, h('label', { for: id }, labelText), input);
}

function statusPill(status) {
  return h('span', { class: 'pill status-' + status }, CASE_STATUS_RU[status] ?? status);
}

function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU') : '—';
}

function toInputDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
    + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

export async function mount(root) {
  await render(root);
}

async function render(root) {
  clear(root);

  let cases;
  let defs;
  let sets;
  let pool;
  let collections;
  try {
    [cases, defs, sets, pool] = await Promise.all([
      api('GET', '/admin/cases'),
      api('GET', '/admin/item-defs'),
      api('GET', '/admin/sets'),
      api('GET', '/admin/daily-reward-pool'),
    ]);
    collections = await loadCollections(sets);
  } catch (e) {
    toast(e.message, 'error');
    return;
  }

  const sources = sets.filter(s => !s.is_base && s.status !== 'retired');

  root.appendChild(h('h2', { class: 'page-title' }, 'Кейсы'));
  root.appendChild(buildCreateForm(root, sources, collections));

  if (!cases.length) {
    root.appendChild(h('p', { class: 'admin-muted' }, 'Кейсов пока нет'));
  }

  for (const cs of cases) {
    root.appendChild(buildCaseCard(root, cs, defs, sources, collections));
  }

  root.appendChild(buildDailySection(root, cases, pool));
}

async function loadCollections(sets) {
  const sources = sets.filter(s => !s.is_base && s.status !== 'retired');
  const details = await Promise.all(sources.map(s => api('GET', '/admin/sets/' + s.id)));
  const collections = [];
  for (const d of details) {
    for (const c of d.collections || []) {
      collections.push({ id: c.id, name: c.name, set_name: d.name });
    }
  }
  return collections;
}

async function done(root) {
  toast('Готово', 'success');
  await render(root);
}

function stockValue(input) {
  const v = input.value;
  return v === '' ? null : Number(v);
}

function dateValue(input) {
  return input.value ? new Date(input.value).toISOString() : null;
}

function buildCreateForm(root, sources, collections) {
  const codeIn = h('input', { name: 'code', required: true, maxlength: 64 });
  const nameIn = h('input', { name: 'name', required: true, maxlength: 128 });
  const priceIn = h('input', { name: 'price', type: 'number', min: 1, value: 100, required: true });
  const sortIn = h('input', { name: 'sort', type: 'number', value: 0, required: true });
  const stockIn = h('input', { name: 'stock_limit', type: 'number', min: 1 });
  const startsIn = h('input', { name: 'sale_starts_at', type: 'datetime-local' });
  const endsIn = h('input', { name: 'sale_ends_at', type: 'datetime-local' });

  const kindSel = h('select', { name: 'kind' },
    h('option', { value: 'set' }, 'По набору'),
    h('option', { value: 'collection' }, 'По коллекции'),
    h('option', { value: 'custom' }, 'Особый'),
  );

  const setSel = h('select', { name: 'set_id' });
  for (const s of sources) setSel.appendChild(h('option', { value: String(s.id) }, s.name));

  const collSel = h('select', { name: 'collection_id' });
  for (const c of collections) {
    collSel.appendChild(h('option', { value: String(c.id) }, c.name + ' (' + c.set_name + ')'));
  }

  const setField = field('Набор', setSel);
  const collField = field('Коллекция', collSel);

  const syncSource = () => {
    setField.hidden = kindSel.value !== 'set';
    collField.hidden = kindSel.value !== 'collection';
  };

  kindSel.addEventListener('change', syncSource);
  syncSource();

  const form = h('form', { class: 'admin-form card admin-section' },
    h('h4', {}, 'Новый кейс'),
    field('Код', codeIn),
    field('Название', nameIn),
    field('Цена', priceIn),
    field('Порядок', sortIn),
    field('Вид', kindSel),
    setField,
    collField,
    field('Тираж', stockIn),
    field('Начало продаж', startsIn),
    field('Конец продаж', endsIn),
    h('div', { class: 'admin-row' },
      h('button', { type: 'submit', class: 'btn btn-gold' }, 'Создать'),
    ),
  );

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const kind = kindSel.value;
    try {
      await api('POST', '/admin/cases', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        price: Number(priceIn.value),
        sort: Number(sortIn.value),
        kind,
        set_id: kind === 'set' ? Number(setSel.value) : null,
        collection_id: kind === 'collection' ? Number(collSel.value) : null,
        stock_limit: stockValue(stockIn),
        sale_starts_at: dateValue(startsIn),
        sale_ends_at: dateValue(endsIn),
      });
      await done(root);
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  return form;
}

function sourceLine(cs) {
  if (cs.kind === 'set') return cs.set ? cs.set.name : '—';
  if (cs.kind === 'collection') return cs.collection ? cs.collection.name : '—';
  return '—';
}

function buildCaseCard(root, cs, defs, sources, collections) {
  const card = h('div', { class: 'card admin-section' });

  card.appendChild(h('h4', {}, cs.name, ' ', statusPill(cs.status),
    ' ', cs.on_sale_now ? h('span', { class: 'pill' }, 'Продаётся сейчас') : null));

  card.appendChild(h('p', { class: 'admin-muted' },
    (CASE_KIND_RU[cs.kind] ?? cs.kind) + ' · ' + sourceLine(cs)
    + ' · цена ' + fmtCrystals(cs.price) + ' · порядок ' + String(cs.sort),
  ));

  const limits = ['Продаётся ' + cs.sold_count + (cs.stock_limit ? ' из ' + cs.stock_limit : '')];
  if (cs.sale_starts_at || cs.sale_ends_at) {
    limits.push('Окно продаж: ' + fmtDate(cs.sale_starts_at) + ' — ' + fmtDate(cs.sale_ends_at));
  }
  card.appendChild(h('p', { class: 'admin-muted' }, limits.join(' · ')));

  card.appendChild(buildDropsTable(cs, defs));
  card.appendChild(buildActions(root, cs, defs, sources, collections));

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

function buildActions(root, cs, defs, sources, collections) {
  const row = h('div', { class: 'admin-row' });

  row.appendChild(h('button', {
    type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openEditModal(root, cs),
  }, 'Изменить'));

  if (cs.status === 'draft') {
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => autoWeights(root, cs, sources, collections),
    }, 'Автовеса'));
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openManualDropsModal(root, cs, defs),
    }, 'Дропы вручную'));
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => postAction(root, cs, 'publish'),
    }, 'Опубликовать'));
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
  } else if (cs.status === 'on_sale') {
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => postAction(root, cs, 'unpublish'),
    }, 'Снять с продажи'));
  } else if (cs.status === 'off_sale') {
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => postAction(root, cs, 'publish'),
    }, 'Опубликовать'));
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
  const stockIn = h('input', { name: 'stock_limit', type: 'number', min: 1, value: cs.stock_limit ?? '' });
  const startsIn = h('input', { name: 'sale_starts_at', type: 'datetime-local', value: toInputDate(cs.sale_starts_at) });
  const endsIn = h('input', { name: 'sale_ends_at', type: 'datetime-local', value: toInputDate(cs.sale_ends_at) });

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() },
    field('Название', nameIn),
    field('Цена', priceIn),
    field('Порядок', sortIn),
    field('Тираж', stockIn),
    field('Начало продаж', startsIn),
    field('Конец продаж', endsIn),
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
              stock_limit: stockValue(stockIn),
              sale_starts_at: dateValue(startsIn),
              sale_ends_at: dateValue(endsIn),
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

async function autoWeights(root, cs, sources, collections) {
  if (cs.kind === 'custom') {
    openAutoWeightsModal(root, cs, sources, collections);
    return;
  }
  const ok = await confirmModal(
    'Автовеса',
    'Заполнить дропы кейса «' + cs.name + '» по весам по умолчанию?',
    'Заполнить', 'gold');
  if (!ok) return;
  try {
    await api('POST', '/admin/cases/' + cs.id + '/drops/auto', {});
    await done(root);
  } catch (err) {
    toast(err.message, 'error');
  }
}

function openAutoWeightsModal(root, cs, sources, collections) {
  const setBoxes = sources.map(s => {
    const input = h('input', { type: 'checkbox', name: 'set-' + String(s.id) });
    return { id: s.id, input };
  });
  const collBoxes = collections.map((c) => {
    const input = h('input', { type: 'checkbox', name: 'col-' + String(c.id) });
    return { id: c.id, input };
  });

  const rows = [];
  rows.push(h('p', { class: 'admin-muted' }, 'Наборы'));
  for (let i = 0; i < sources.length; i++) {
    rows.push(h('label', { class: 'admin-row' },
      setBoxes[i].input,
      sources[i].name + ' — ' + (SET_STATUS_RU[sources[i].status] ?? sources[i].status),
    ));
  }
  rows.push(h('p', { class: 'admin-muted' }, 'Коллекции'));
  for (let i = 0; i < collections.length; i++) {
    rows.push(h('label', { class: 'admin-row' },
      collBoxes[i].input,
      collections[i].name + ' (' + collections[i].set_name + ')',
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
          const setIds = setBoxes.filter(b => b.input.checked).map(b => Number(b.id));
          const collectionIds = collBoxes.filter(b => b.input.checked).map(b => Number(b.id));
          if (!setIds.length && !collectionIds.length) {
            toast('Выберите хотя бы один набор или коллекцию', 'error');
            return false;
          }
          try {
            await api('POST', '/admin/cases/' + cs.id + '/drops/auto', {
              set_ids: setIds,
              collection_ids: collectionIds,
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

function dropDefsFor(cs, defs) {
  if (cs.kind === 'set') {
    return defs.filter(d => d.set.code === cs.set.code);
  }
  if (cs.kind === 'collection') {
    return defs.filter(d => d.collection?.code === cs.collection.code);
  }
  return defs;
}

function openManualDropsModal(root, cs, defs) {
  const list = dropDefsFor(cs, defs);
  const weightByDef = new Map();
  for (const d of cs.drops || []) weightByDef.set(d.item_def_id, Number(d.weight) || 0);

  const inputs = [];
  const bodies = [];
  let curSet = null;
  let curColl = null;
  let tbody = null;
  for (const def of list) {
    const setName = def.set.name;
    if (setName !== curSet) {
      curSet = setName;
      curColl = null;
      tbody = h('tbody', {},
        h('tr', {}, h('td', {}, setName)),
      );
      bodies.push(tbody);
    }
    const collName = def.collection ? def.collection.name : 'Доски';
    if (collName !== curColl) {
      curColl = collName;
      tbody.appendChild(h('tr', { class: 'admin-muted' }, h('td', {}, collName)));
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

// ---------- Ежедневная награда ----------

function buildDailySection(root, cases, pool) {
  const section = h('div', { class: 'card admin-section' },
    h('h3', { class: 'card-title' }, 'Ежедневная награда'),
    h('p', { class: 'admin-muted' }, 'Игрок получает один кейс по весам после N побед за день'),
  );

  if (!pool.length) {
    section.appendChild(h('p', { class: 'admin-muted' }, 'Пул пуст'));
  } else {
    const sum = pool.reduce((acc, p) => acc + Number(p.weight || 0), 0);
    const tbody = h('tbody');
    for (const p of pool) {
      tbody.appendChild(h('tr', {},
        h('td', {}, p.case ? p.case.name : '#' + String(p.case_id)),
        h('td', { class: 'mono' }, String(p.weight)),
        h('td', { class: 'mono' },
          (sum > 0 ? ((Number(p.weight) / sum) * 100).toFixed(2) : '0.00') + '%'),
      ));
    }
    section.appendChild(h('table', { class: 'admin-table' },
      h('thead', {},
        h('tr', {},
          h('th', {}, 'Кейс'),
          h('th', {}, 'Вес'),
          h('th', {}, 'Шанс'),
        ),
      ),
      tbody,
    ));
  }

  section.appendChild(h('div', { class: 'admin-row' },
    h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openPoolModal(root, cases, pool),
    }, 'Изменить пул'),
  ));

  return section;
}

function openPoolModal(root, cases, pool) {
  const eligible = cases.filter(c => c.status !== 'draft');
  const weightByCaseId = new Map(pool.map(p => [p.case.id, Number(p.weight)]));

  const inputs = [];
  const tbody = h('tbody');
  for (const c of eligible) {
    const input = h('input', {
      type: 'number', min: 0, step: 1,
      value: weightByCaseId.get(c.id) ?? 0,
      name: 'pool-' + String(c.id),
    });
    inputs.push({ case: c, input });
    tbody.appendChild(h('tr', {},
      h('td', {}, c.name),
      h('td', {}, input),
    ));
  }

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() },
    h('table', { class: 'admin-table' },
      h('thead', {},
        h('tr', {},
          h('th', {}, 'Кейс'),
          h('th', {}, 'Вес'),
        ),
      ),
      tbody,
    ),
  );

  openModal({
    title: 'Изменить пул',
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      {
        label: 'Сохранить', kind: 'gold',
        onClick: async () => {
          const entries = [];
          for (const { case: cs, input } of inputs) {
            const weight = Number(input.value);
            if (!Number.isInteger(weight) || weight < 0) {
              toast('Вес должен быть целым числом ≥ 0', 'error');
              return false;
            }
            if (weight > 0) entries.push({ case_id: cs.id, weight });
          }
          try {
            await api('PUT', '/admin/daily-reward-pool', entries);
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
