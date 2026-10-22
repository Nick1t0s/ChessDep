import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';
import { openModal, confirmModal } from '../modal.js';
import { fmtCrystals } from '../format.js';

export function renderCasesSection(container, detail, reload) {
  clear(container);
  container.appendChild(h('h3', {}, 'Кейсы'));

  const form = buildCreateForm(detail, reload);
  container.appendChild(form);

  const cases = (detail.cases || []).slice().sort((a, b) => (a.sort - b.sort) || (a.id - b.id));
  if (!cases.length) {
    container.appendChild(h('p', { class: 'admin-muted' }, 'Кейсов пока нет'));
    return;
  }

  for (const cs of cases) {
    container.appendChild(buildCaseCard(detail, cs, reload));
  }
}

function buildCreateForm(detail, reload) {
  const codeIn = h('input', { name: 'code', required: true, maxlength: 64 });
  const nameIn = h('input', { name: 'name', required: true, maxlength: 128 });
  const priceIn = h('input', { name: 'price', type: 'number', min: 1, value: 100, required: true });
  const sortIn = h('input', { name: 'sort', type: 'number', value: 0, required: true });

  const form = h('form', { class: 'admin-form card admin-section' },
    h('h4', {}, 'Новый кейс'),
    h('div', { class: 'field' }, h('label', { for: 'nc-code' }, 'Код'), codeIn),
    h('div', { class: 'field' }, h('label', { for: 'nc-name' }, 'Название'), nameIn),
    h('div', { class: 'field' }, h('label', { for: 'nc-price' }, 'Цена'), priceIn),
    h('div', { class: 'field' }, h('label', { for: 'nc-sort' }, 'Порядок'), sortIn),
    h('div', { class: 'admin-row' },
      h('button', { type: 'submit', class: 'btn btn-gold' }, 'Создать'),
    ),
  );
  codeIn.id = 'nc-code';
  nameIn.id = 'nc-name';
  priceIn.id = 'nc-price';
  sortIn.id = 'nc-sort';

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('POST', '/admin/collections/' + detail.id + '/cases', {
        code: codeIn.value.trim(),
        name: nameIn.value.trim(),
        price: Number(priceIn.value),
        sort: Number(sortIn.value),
      });
      toast('Готово', 'success');
      await reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  return form;
}

function buildCaseCard(detail, cs, reload) {
  const card = h('div', { class: 'card admin-section' });

  card.appendChild(h('h4', {}, cs.name));
  card.appendChild(h('p', { class: 'admin-muted' },
    cs.code, ' · цена ', fmtCrystals(cs.price), ' · ', cs.is_active ? 'активен' : 'выключен', ' · порядок ', String(cs.sort),
  ));

  card.appendChild(buildDropsTable(detail, cs));
  card.appendChild(buildActions(detail, cs, reload));

  return card;
}

function buildDropsTable(detail, cs) {
  const drops = cs.drops || [];
  if (!drops.length) {
    return h('p', { class: 'admin-muted' }, 'Дропов нет');
  }
  const nameById = new Map();
  for (const def of detail.items || []) nameById.set(def.id, def.name);
  const sum = drops.reduce((acc, d) => acc + Number(d.weight || 0), 0);

  const tbody = h('tbody', {});
  for (const d of drops) {
    tbody.appendChild(h('tr', {},
      h('td', {}, nameById.get(d.item_def_id) || '—'),
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

function buildActions(detail, cs, reload) {
  const row = h('div', { class: 'admin-row' });

  row.appendChild(h('button', {
    type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openEditModal(cs, reload),
  }, 'Изменить'));

  if (detail.status === 'draft') {
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openAutoWeightsModal(cs, reload),
    }, 'Автовеса'));
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-ghost btn-sm', onClick: () => openManualDropsModal(detail, cs, reload),
    }, 'Дропы вручную'));
    row.appendChild(h('button', {
      type: 'button', class: 'btn btn-danger btn-sm', onClick: async () => {
        const ok = await confirmModal('Удалить кейс', 'Удалить кейс «' + cs.name + '»?', 'Удалить', 'danger');
        if (!ok) return;
        try {
          await api('DELETE', '/admin/cases/' + cs.id);
          toast('Готово', 'success');
          await reload();
        } catch (err) {
          toast(err.message, 'error');
        }
      },
    }, 'Удалить'));
  }

  return row;
}

function openEditModal(cs, reload) {
  const nameIn = h('input', { name: 'name', required: true, maxlength: 128, value: cs.name });
  const priceIn = h('input', { name: 'price', type: 'number', min: 1, value: cs.price, required: true });
  const sortIn = h('input', { name: 'sort', type: 'number', value: cs.sort, required: true });
  const activeIn = h('input', { name: 'is_active', type: 'checkbox', checked: cs.is_active });

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() },
    h('div', { class: 'field' }, h('label', { for: 'ec-name' }, 'Название'), nameIn),
    h('div', { class: 'field' }, h('label', { for: 'ec-price' }, 'Цена'), priceIn),
    h('div', { class: 'field' }, h('label', { for: 'ec-sort' }, 'Порядок'), sortIn),
    h('div', { class: 'field' }, h('label', { for: 'ec-active' }, 'Активен'), activeIn),
  );
  nameIn.id = 'ec-name';
  priceIn.id = 'ec-price';
  sortIn.id = 'ec-sort';
  activeIn.id = 'ec-active';

  openModal({
    title: 'Изменить кейс',
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      {
        label: 'Сохранить', kind: 'gold',
        onClick: async () => {
          const patch = {};
          const name = nameIn.value.trim();
          if (name !== cs.name) patch.name = name;
          if (Number(priceIn.value) !== Number(cs.price)) patch.price = Number(priceIn.value);
          if (Number(sortIn.value) !== Number(cs.sort)) patch.sort = Number(sortIn.value);
          if (activeIn.checked !== cs.is_active) patch.is_active = activeIn.checked;
          if (!Object.keys(patch).length) return true;
          try {
            await api('PATCH', '/admin/cases/' + cs.id, patch);
            toast('Готово', 'success');
            await reload();
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

function openAutoWeightsModal(cs, reload) {
  const sel = h('select', { name: 'kind' },
    h('option', { value: '' }, 'Все'),
    h('option', { value: 'piece_skin' }, 'Фигуры'),
    h('option', { value: 'board_skin' }, 'Доски'),
  );

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() },
    h('div', { class: 'field' }, h('label', { for: 'aw-kind' }, 'Тип предметов'), sel),
  );
  sel.id = 'aw-kind';

  openModal({
    title: 'Автовеса',
    titleAnim: 'none',
    body,
    actions: [
      { label: 'Отмена', kind: 'ghost' },
      {
        label: 'Применить', kind: 'gold',
        onClick: async () => {
          try {
            await api('POST', '/admin/cases/' + cs.id + '/drops/auto', { kind: sel.value || null });
            toast('Готово', 'success');
            await reload();
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

function openManualDropsModal(detail, cs, reload) {
  const weightByDef = new Map();
  for (const d of cs.drops || []) weightByDef.set(d.item_def_id, Number(d.weight) || 0);

  const inputs = [];
  const rows = [];
  for (const def of detail.items || []) {
    const idx = inputs.length;
    const input = h('input', {
      type: 'number', min: 0, step: 1, value: weightByDef.get(def.id) || 0,
      name: 'weight-' + idx,
    });
    input.id = 'md-w-' + idx;
    inputs.push(input);
    rows.push(h('div', { class: 'admin-row' },
      h('span', {}, def.name),
      input,
    ));
  }

  const body = h('form', { class: 'admin-form', onSubmit: (e) => e.preventDefault() }, ...rows);

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
          (detail.items || []).forEach((def, i) => {
            const w = Number(inputs[i].value) || 0;
            if (w > 0) drops.push({ item_def_id: def.id, weight: w });
          });
          try {
            await api('PUT', '/admin/cases/' + cs.id + '/drops', drops);
            toast('Готово', 'success');
            await reload();
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
