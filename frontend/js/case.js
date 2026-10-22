import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout, setBalance } from './layout.js';
import { toast } from './toast.js';
import { openModal } from './modal.js';
import { itemCard } from './items.js';
import { fmtCrystals } from './format.js';

const me = await initLayout({ auth: 'required', active: 'cases' });

const main = h('main', { class: 'wrap-wide case-page' });
document.body.appendChild(main);

const id = new URLSearchParams(location.search).get('id') ?? '';
if (!/^\d+$/.test(id)) {
  main.appendChild(h('p', {}, 'Некорректная ссылка'));
} else {
  initPage();
}

async function initPage() {
  let loot = null;
  try {
    loot = await api('GET', '/cases/' + id);
  } catch (e) {
    toast(e.message, 'error');
    return;
  }

  const title = h('h1', { class: 'page-title' }, loot.name);

  const windowEl = h('div', { class: 'strip-window' },
    h('div', { class: 'strip-marker' }),
    h('div', { class: 'strip-track' }),
  );
  const track = windowEl.querySelector('.strip-track');

  const openBtn = h('button', { type: 'button', class: 'btn btn-gold' }, 'Открыть за ' + fmtCrystals(loot.price));
  const stripCard = h('div', { class: 'card' }, windowEl, openBtn);

  const contentsGrid = h('div', { class: 'item-grid' });
  const contentsCard = h('div', { class: 'card' },
    h('h3', { class: 'card-title' }, 'Содержимое'),
    contentsGrid,
  );

  main.append(title, stripCard, contentsCard);

  for (const drop of loot.drops) {
    track.appendChild(h('div', { class: 'strip-cell' }, itemCard(drop.def)));
  }
  for (const drop of loot.drops) {
    contentsGrid.appendChild(itemCard(drop.def, { badge: drop.chance_text }));
  }

  openBtn.addEventListener('click', () => openCase(openBtn, windowEl, track));
}

async function openCase(openBtn, windowEl, track) {
  openBtn.disabled = true;
  let res = null;
  try {
    res = await api('POST', '/cases/' + id + '/open');
  } catch (e) {
    toast(e.message, 'error');
    openBtn.disabled = false;
    return;
  }

  clear(track);
  for (const defId of res.strip) {
    track.appendChild(h('div', { class: 'strip-cell' }, itemCard(res.defs[String(defId)])));
  }

  track.style.setProperty('transition', 'none');
  track.style.setProperty('transform', 'translateX(0px)');
  void track.offsetWidth;

  const offset = res.win_index * 132 + 66 - windowEl.clientWidth / 2;

  track.style.setProperty('transition', 'transform 5.5s cubic-bezier(.12,.8,.18,1)');
  track.style.setProperty('transform', 'translateX(' + String(-offset) + 'px)');

  await new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve();
    };
    track.addEventListener('transitionend', finish, { once: true });
    setTimeout(finish, 6000);
  });

  setBalance(res.balance);
  openModal({
    title: 'Выпало!',
    titleAnim: 'pop',
    body: itemCard(res.item.def, { exterior: res.item.exterior }),
    actions: [
      { label: 'В инвентарь', kind: 'ghost', onClick: () => { location.href = '/inventory.html'; } },
      { label: 'Ещё раз', kind: 'gold' },
    ],
  });

  openBtn.disabled = false;
}
