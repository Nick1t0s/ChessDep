import { h, clear } from './dom.js';
import { PIECE_NAME_RU, END_REASON_RU } from './format.js';

const SYS_TEXT = {
  resign: 'Сдача',
  draw_offer: 'Предложена ничья',
  draw_accept: 'Ничья принята',
  draw_decline: 'Ничья отклонена',
  abort: 'Партия отменена',
  flag: 'Время вышло',
};

export function createMoveList(container, { onSelect } = {}) {
  clear(container);

  const list = h('div', { class: 'mv-list' });
  container.appendChild(list);

  let events = [];
  let current = null;

  const handleKey = (ev) => (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(ev);
    }
  };

  function clickable(ev, className, text) {
    return h(
      className.startsWith('mv-dep') ? 'div' : 'span',
      {
        class: className,
        role: 'button',
        tabindex: '0',
        'data-seq': String(ev.seq),
        onClick: () => onSelect(ev),
        onKeydown: handleKey(ev),
      },
      text
    );
  }

  function depText(ev) {
    const p = ev.payload ?? {};
    return '⚡ ' + PIECE_NAME_RU[p.from] + ' → ' + PIECE_NAME_RU[p.to] + (p.success ? ' ✓' : ' ✗');
  }

  function sysText(ev) {
    if (ev.kind === 'game_over') {
      const reason = ev.payload?.end_reason;
      return 'Итог: ' + (END_REASON_RU[reason] ?? reason);
    }
    return SYS_TEXT[ev.kind] ?? ev.kind;
  }

  function addMove(ev) {
    const num = Math.floor(((ev.ply ?? 0) - 1) / 2) + 1;
    if (!current || current.num !== num || current.cells >= 2) {
      const row = h('div', { class: 'mv-row' }, h('span', { class: 'mv-num' }, num + '.'));
      list.appendChild(row);
      current = { num, row, cells: 0 };
      if (ev.actor === 'black') {
        current.row.appendChild(h('span', { class: 'mv-cell' }, '…'));
        current.cells++;
      }
    }
    current.row.appendChild(clickable(ev, 'mv-cell', ev.payload?.san ?? ''));
    current.cells++;
  }

  function renderEvent(ev) {
    if (ev.kind === 'move') {
      addMove(ev);
    } else if (ev.kind === 'dep') {
      const p = ev.payload ?? {};
      list.appendChild(clickable(ev, 'mv-dep ' + (p.success ? 'ok' : 'fail'), depText(ev)));
    } else {
      list.appendChild(h('div', { class: 'mv-sys' }, sysText(ev)));
    }
  }

  function renderAll() {
    clear(list);
    current = null;
    for (const ev of events) renderEvent(ev);
  }

  function setEvents(newEvents) {
    events = Array.isArray(newEvents) ? newEvents.slice() : [];
    renderAll();
    list.scrollTop = list.scrollHeight;
  }

  function appendEvents(newEvents) {
    const last = lastSeq();
    const fresh = (Array.isArray(newEvents) ? newEvents : []).filter((ev) => ev.seq > last);
    if (!fresh.length) return;
    events = events.concat(fresh);
    for (const ev of fresh) renderEvent(ev);
    list.scrollTop = list.scrollHeight;
  }

  function lastSeq() {
    return events.length ? events[events.length - 1].seq : 0;
  }

  function select(seq) {
    for (const el of list.querySelectorAll('.sel')) el.classList.remove('sel');
    if (seq === null || seq === undefined) return;
    const target = list.querySelector('[data-seq="' + seq + '"]');
    if (target) target.classList.add('sel');
  }

  return { setEvents, appendEvents, lastSeq, select };
}
