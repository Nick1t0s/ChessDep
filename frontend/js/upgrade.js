import { api } from './api.js';
import { h, clear } from './dom.js';
import { initLayout } from './layout.js';
import { toast } from './toast.js';
import { openModal } from './modal.js';
import { fmtCrystals } from './format.js';
import { itemCard } from './items.js';
import { playSound } from './sound.js';

const me = await initLayout({ auth: 'required', active: 'upgrade' });

const REASON_RU = {
  UPGRADE_CHANCE_OUT_OF_RANGE: 'Шанс вне допустимого диапазона',
  TOO_MANY_INPUTS: 'Слишком много предметов',
  DUPLICATE_INPUTS: 'Повторяющиеся предметы',
  UPGRADE_TARGET_NOT_AVAILABLE: 'Цель недоступна',
  UPGRADE_SET_MISMATCH: 'Апгрейд возможен только внутри одного набора',
};

let items = [];
const selected = new Set();
let target = null;
let rotation = 180; // стрелка в покое — внизу, в центре дуги
let previewSeq = 0;
let busy = false;

const main = h('main', { class: 'wrap-wide upgrade' });

const invSum = h('p', { class: 'upg-sum' }, '');
const invGrid = h('div', { class: 'item-grid' });
const invCard = h('div', { class: 'card' },
  h('h3', { class: 'card-title' }, 'Ваши предметы'),
  invSum,
  invGrid,
);

const arrow = h('div', { class: 'gauge-arrow' }, h('div', { class: 'gauge-needle' }));
const gaugeArc = h('div', { class: 'gauge-arc' });
const chanceEl = h('div', { class: 'gauge-chance mono' }, '—');
const levelEl = h('div', { class: 'gauge-level' }, '');
const gauge = h('div', { class: 'gauge' },
  h('div', { class: 'gauge-ticks' }),
  gaugeArc,
  h('div', { class: 'gauge-inner' }, chanceEl, levelEl),
  arrow,
);
const reasonEl = h('p', { class: 'upg-reason' }, '');
const goBtn = h('button', { type: 'button', class: 'btn btn-gold btn-block', disabled: true }, 'Апгрейд');
const centerCard = h('div', { class: 'card upg-center' }, gauge, reasonEl, goBtn);

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

function selectedSetCode() {
  for (const id of selected) {
    const item = items.find((it) => it.id === id);
    if (item) return item.def.set.code;
  }
  return null;
}

function renderInventory() {
  const sum = sumValue();
  clear(invSum);
  invSum.append('Выбрано: ' + String(selected.size) + ' · ценность ' + fmtCrystals(sum));
  clear(invGrid);
  for (const item of items) {
    invGrid.appendChild(itemCard(item.def, {
      exterior: item.exterior,
      image: item.image,
      selected: selected.has(item.id),
      onClick: () => toggleItem(item.id),
    }));
  }
}

function renderTargets() {
  const sum = sumValue();
  const setCode = selectedSetCode();
  clear(targetGrid);
  for (const def of targets) {
    if (setCode !== null && def.set.code !== setCode) continue;
    if (selected.size > 0 && sum > 0 && def.value <= sum) continue;
    targetGrid.appendChild(itemCard(def, {
      selected: target?.id === def.id,
      onClick: () => {
        if (busy) return;
        target = target?.id === def.id ? null : def;
        renderTargets();
        refreshPreview();
      },
    }));
  }
}

function toggleItem(id) {
  if (busy) return;
  if (selected.has(id)) {
    selected.delete(id);
  } else {
    if (selected.size >= 10) {
      toast('Не больше 10 предметов', 'error');
      return;
    }
    const item = items.find((it) => it.id === id);
    const setCode = selectedSetCode();
    if (item && setCode !== null && item.def.set.code !== setCode) {
      toast('Апгрейд возможен только внутри одного набора', 'error');
      return;
    }
    selected.add(id);
  }
  if (selected.size === 0) target = null;
  if (target !== null && selected.size > 0 && target.set.code !== selectedSetCode()) target = null;
  renderInventory();
  renderTargets();
  refreshPreview();
}

function chanceLevel(chance) {
  if (chance < 0.3) return 'низкий шанс';
  if (chance < 0.6) return 'средний шанс';
  return 'высокий шанс';
}

function resetPreview() {
  previewSeq++;
  gaugeArc.style.setProperty('--half', '0deg');
  chanceEl.textContent = '—';
  levelEl.textContent = '';
  reasonEl.textContent = '';
  goBtn.disabled = true;
}

async function refreshPreview() {
  if (busy) return;
  if (selected.size === 0 || target === null) {
    resetPreview();
    return;
  }
  const seq = ++previewSeq;
  goBtn.disabled = true;
  chanceEl.textContent = '…';
  levelEl.textContent = '';
  try {
    const p = await api('POST', '/upgrade/preview', {
      input_ids: [...selected],
      target_def_id: target.id,
    });
    if (seq !== previewSeq || busy || selected.size === 0 || target === null) return;
    gaugeArc.style.setProperty('--half', (p.chance * 180) + 'deg');
    chanceEl.textContent = p.chance_text;
    levelEl.textContent = chanceLevel(p.chance);
    reasonEl.textContent = REASON_RU[p.reason] ?? '';
    goBtn.disabled = !p.allowed;
  } catch (e) {
    if (seq !== previewSeq || busy || selected.size === 0 || target === null) return;
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
      arrow.removeEventListener('transitionend', finish);
      resolve();
    };
    const timer = setTimeout(finish, 4500);
    arrow.addEventListener('transitionend', finish);
  });
}

// Щелчок каждые 15° поворота стрелки, но не чаще раза в 45 мс.
function tickWhileSpinning() {
  let last = null;
  let unwrapped = 0;
  let lastTickAt = 0;
  let raf = 0;
  const step = () => {
    const t = getComputedStyle(arrow).transform;
    if (t !== 'none') {
      const m = new DOMMatrix(t);
      const angle = Math.atan2(m.b, m.a) * 180 / Math.PI;
      if (last !== null) {
        let d = angle - last;
        if (d < -180) d += 360;
        if (d > 180) d -= 360;
        const before = Math.floor(unwrapped / 15);
        unwrapped += d;
        const now = performance.now();
        if (Math.floor(unwrapped / 15) !== before && now - lastTickAt > 45) {
          lastTickAt = now;
          playSound('tick', 0.35);
        }
      }
      last = angle;
    }
    raf = requestAnimationFrame(step);
  };
  raf = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf);
}

goBtn.addEventListener('click', async () => {
  if (busy || selected.size === 0 || target === null || goBtn.disabled) return;
  busy = true;
  goBtn.disabled = true;
  previewSeq++;

  let res;
  try {
    res = await api('POST', '/upgrade', {
      input_ids: [...selected],
      target_def_id: target.id,
    });
  } catch (e) {
    busy = false;
    toast(e.message, 'error');
    refreshPreview();
    return;
  }

  try {
    // Дуга шанса — по центру снизу: [180° − chance·180°, 180° + chance·180°).
    // Успех ⇔ roll_value < chance, поэтому стрелка встаёт в 180° − chance·180° + roll·360°.
    const stop = 180 - res.chance * 180 + res.roll_value * 360;
    rotation = Math.ceil(rotation / 360) * 360 + 1800 + stop;
    const stopTicks = tickWhileSpinning();
    arrow.style.setProperty('transition', 'transform 4s cubic-bezier(.15,.85,.25,1)');
    arrow.style.setProperty('transform', 'rotate(' + rotation + 'deg)');
    await waitSpin();
    stopTicks();
    playSound(res.success ? 'win' : 'fail');

    if (res.success && res.item) {
      openModal({
        title: 'Апгрейд удался!',
        titleAnim: 'pop',
        body: itemCard(res.item.def, { exterior: res.item.exterior, image: res.item.image }),
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
  } finally {
    selected.clear();
    target = null;
    try {
      await loadInventory();
    } catch (e) {
      toast(e.message, 'error');
    }
    renderInventory();
    renderTargets();
    resetPreview();
    busy = false;
  }
});

async function loadInventory() {
  const inventory = await api('GET', '/inventory?sort=value');
  items = (inventory ?? []).filter((item) => item.kind === 'skin' && !item.bound && item.status === 'owned');
}

const targets = await api('GET', '/item-defs?upgrade_target=true');

await loadInventory();
renderInventory();
renderTargets();
resetPreview();
