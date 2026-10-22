import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { openModal, confirmModal } from './modal.js';
import { fmtCrystals } from './format.js';
import { itemCard } from './items.js';

const me = await initLayout({ auth: 'required', active: 'upgrade' });

const REASON_RU = {
  UPGRADE_CHANCE_OUT_OF_RANGE: 'Шанс вне допустимого диапазона',
  TOO_MANY_INPUTS: 'Слишком много предметов',
  DUPLICATE_INPUTS: 'Повторяющиеся предметы',
  UPGRADE_TARGET_NOT_AVAILABLE: 'Цель недоступна',
};

let items = [];
const selected = new Set();
let target = null;
let rotation = 0;
let previewSeq = 0;

const main = h('main', { class: 'wrap-wide upgrade' });

const invSum = h('p', { class: 'upg-sum' }, '');
const invGrid = h('div', { class: 'item-grid' });
const invCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Ваши предметы'),
  invSum,
  invGrid,
);

const wheel = h('div', { class: 'wheel' });
const chanceEl = h('div', { class: 'upg-chance mono' }, '—');
const reasonEl = h('p', { class: 'upg-reason' }, '');
const goBtn = h('button', { type: 'button', class: 'btn btn-gold btn-block', disabled: true }, 'Апгрейд');
const centerCard = h('div', { class: 'card upg-center' },
  h('div', { class: 'wheel-wrap' }, h('div', { class: 'wheel-pointer' }), wheel),
  chanceEl,
  reasonEl,
  goBtn,
);

const targetGrid = h('div', { class: 'item-grid' });
const targetCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Цель'),
  targetGrid,
);

main.append(h('h1', { class: 'page-title' }, 'Апгрейд'), h('div', { class: 'upg-layout' }, invCard, centerCard, targetCard));
document.body.appendChild(main);

function sumValue() {
  let sum = 0;
  for (const id of selected) {
    const item = items.find((it) => it.id === id);
    if (item) sum += item.def.value;
  }
  return sum;
}

function renderInventory() {
  const sum = sumValue();
  clear(invSum);
  invSum.append('Выбрано: ' + String(selected.size) + ' · ценность ' + fmtCrystals(sum));
  clear(invGrid);
  for (const item of items) {
    invGrid.appendChild(itemCard(item.def, {
      exterior: item.exterior,
      selected: selected.has(item.id),
      onClick: () => toggleItem(item.id),
    }));
  }
}

function renderTargets() {
  const sum = sumValue();
  clear(targetGrid);
  for (const def of targets) {
    if (selected.size > 0 && sum > 0 && def.value <= sum) continue;
    targetGrid.appendChild(itemCard(def, {
      selected: target?.id === def.id,
      onClick: () => {
        target = target?.id === def.id ? null : def;
        renderTargets();
        refreshPreview();
      },
    }));
  }
}

function toggleItem(id) {
  if (selected.has(id)) {
    selected.delete(id);
  } else {
    if (selected.size >= 10) {
      toast('Не больше 10 предметов', 'error');
      return;
    }
    selected.add(id);
  }
  if (selected.size === 0) target = null;
  renderInventory();
  renderTargets();
  refreshPreview();
}

function resetPreview() {
  wheel.style.setProperty('--win', '0deg');
  chanceEl.textContent = '—';
  reasonEl.textContent = '';
  goBtn.disabled = true;
}

async function refreshPreview() {
  if (selected.size === 0 || target === null) {
    resetPreview();
    return;
  }
  const seq = ++previewSeq;
  try {
    const p = await api('POST', '/upgrade/preview', {
      input_ids: [...selected],
      target_def_id: target.id,
    });
    if (seq !== previewSeq) return;
    wheel.style.setProperty('--win', (p.chance * 360) + 'deg');
    chanceEl.textContent = p.chance_text;
    reasonEl.textContent = REASON_RU[p.reason] ?? '';
    goBtn.disabled = !p.allowed;
  } catch (e) {
    if (seq !== previewSeq) return;
    resetPreview();
    toast(e.message, 'error');
  }
}

function waitSpin() {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      wheel.removeEventListener('transitionend', finish);
      resolve();
    };
    const timer = setTimeout(finish, 4500);
    wheel.addEventListener('transitionend', finish);
  });
}

goBtn.addEventListener('click', async () => {
  if (selected.size === 0 || target === null || goBtn.disabled) return;
  const chanceText = chanceEl.textContent;
  const ok = await confirmModal(
    'Апгрейд',
    'Все выбранные предметы сгорят при любом исходе. Шанс ' + chanceText + '.',
    'Рискнуть',
    'gold',
  );
  if (!ok) return;
  goBtn.disabled = true;
  let res;
  try {
    res = await api('POST', '/upgrade', {
      input_ids: [...selected],
      target_def_id: target.id,
    });
  } catch (e) {
    toast(e.message, 'error');
    refreshPreview();
    return;
  }

  const base = Math.ceil(rotation / 360) * 360 + 1800;
  rotation = base + (360 - res.roll_value * 360);
  wheel.style.setProperty('transition', 'transform 4s cubic-bezier(.15,.85,.25,1)');
  wheel.style.setProperty('transform', 'rotate(' + rotation + 'deg)');
  await waitSpin();

  if (res.success && res.item) {
    openModal({
      title: 'Апгрейд удался!',
      titleAnim: 'pop',
      body: itemCard(res.item.def, { exterior: res.item.exterior }),
      actions: [{ label: 'Отлично', kind: 'gold' }],
    });
  } else {
    openModal({
      title: 'Не повезло',
      titleAnim: 'shake',
      body: h('p', { class: 'm-text' }, 'Предметы сгорели.'),
      actions: [{ label: 'Ок', kind: 'ghost' }],
    });
  }

  selected.clear();
  target = null;
  await loadInventory();
  renderInventory();
  renderTargets();
  resetPreview();
});

async function loadInventory() {
  const inventory = await api('GET', '/inventory?sort=value');
  items = (inventory ?? []).filter((item) => item.status === 'owned');
}

const targets = await api('GET', '/item-defs?upgrade_target=true');

await loadInventory();
renderInventory();
renderTargets();
resetPreview();
