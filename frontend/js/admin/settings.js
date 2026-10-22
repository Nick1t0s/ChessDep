import { api } from '../api.js';
import { h, clear } from '../dom.js';
import { toast } from '../toast.js';

export async function mount(root) {
  let settings;
  try {
    settings = await api('GET', '/admin/settings');
  } catch (e) {
    toast(e.message, 'error');
    return;
  }

  const table = h('table', { class: 'admin-table' },
    h('thead', {},
      h('tr', {},
        h('th', {}, 'Ключ'),
        h('th', {}, 'Значение'),
        h('th', {}, 'По умолчанию'),
        h('th', {}, 'Изменено'),
        h('th', {}, ''),
      ),
    ),
  );
  const tbody = h('tbody', {});
  table.appendChild(tbody);

  for (const s of settings) {
    const input = h('input', {
      type: 'text',
      class: 'set-input',
      value: JSON.stringify(s.value),
      'aria-label': 'Значение ' + s.key,
    });
    const changedCell = h('td', {}, fmtChanged(s.updated_at));
    const saveBtn = h('button', { type: 'button', class: 'btn btn-gold btn-sm' }, 'Сохранить');
    saveBtn.addEventListener('click', async () => {
      let value;
      try {
        value = JSON.parse(input.value);
      } catch {
        toast('Некорректный JSON', 'error');
        return;
      }
      try {
        const updated = await api('PUT', '/admin/settings/' + encodeURIComponent(s.key), { value });
        clear(changedCell);
        changedCell.append(fmtChanged(updated.updated_at));
        toast('Сохранено', 'success');
      } catch (e) {
        toast(e.message, 'error');
      }
    });

    tbody.appendChild(h('tr', {},
      h('td', {}, h('span', { class: 'mono' }, s.key)),
      h('td', {}, input),
      h('td', {}, h('span', { class: 'admin-muted mono' }, JSON.stringify(s.default))),
      changedCell,
      h('td', {}, saveBtn),
    ));
  }

  root.appendChild(table);
}

function fmtChanged(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU') : '—';
}
