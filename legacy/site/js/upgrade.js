(function () {
  var TARGETS = ['knight', 'bishop', 'rook', 'queen', 'queen2', 'king'];
  var drop = null, target = null, spinning = false, rot = 0;

  function el(id) { return document.getElementById(id); }

  function pctOf(inVal, outVal) {
    return Math.min(98, Math.round(inVal / outVal * 1000) / 10);
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    var fee = CD.config().upgradeFeePct || 0;
    var hint = document.querySelector('.upgrade-hint');
    if (hint) hint.textContent = fee > 0
      ? 'Каждый спин списывает комиссию ' + fee + '% от ставки (настройка админки).'
      : 'Коэффициент честный: шанс = ставка ÷ цель. Комиссия отключена.';
    renderDrop();
    renderTargets();
    updateWheel();
    el('btn-spin').addEventListener('click', spin);
    el('res-close').addEventListener('click', closeResult);
  });

  function renderDrop() {
    var box = el('drop-list');
    box.innerHTML = '';
    var codes = CD.uniqueCodes();
    if (codes.length === 0) {
      box.innerHTML = '<div class="empty-note">Склад пуст.<br>Открой кейс в разделе «Кейсы»</div>';
      return;
    }
    codes.sort(function (a, b) { return CD.PIECES[a].val - CD.PIECES[b].val; });
    codes.forEach(function (code) {
      var p = CD.PIECES[code];
      var row = document.createElement('button');
      row.className = 'pick-row r-' + p.rarity + (drop === code ? ' sel' : '');
      row.innerHTML =
        '<span class="row-glyph">' + p.glyph + '</span>' +
        '<span class="row-meta"><b>' + p.name + '</b><span>' + p.val + ' ◈</span></span>' +
        '<span class="row-side"><span class="cnt">×' + CD.count(code) + '</span></span>';
      row.addEventListener('click', function () {
        drop = (drop === code) ? null : code;
        renderDrop();
        renderTargets();
        updateWheel();
        spinGuard();
      });
      box.appendChild(row);
    });
  }

  function renderTargets() {
    var box = el('target-list');
    box.innerHTML = '';
    var inVal = drop ? CD.PIECES[drop].val : 0;
    TARGETS.forEach(function (code) {
      var p = CD.PIECES[code];
      var tooCheap = drop && p.val <= inVal;
      var pct = drop ? pctOf(inVal, p.val) : null;
      var row = document.createElement('button');
      row.className = 'pick-row r-' + p.rarity + (target === code ? ' sel' : '') + (tooCheap ? ' dis' : '');
      row.innerHTML =
        '<span class="row-glyph">' + p.glyph + '</span>' +
        '<span class="row-meta"><b>' + p.name + '</b><span>' + p.val + ' ◈</span></span>' +
        '<span class="row-side"><span class="pct">' + (pct === null ? '—' : pct.toFixed(1) + '%') + '</span></span>';
      row.addEventListener('click', function () {
        if (tooCheap) return;
        target = (target === code) ? null : code;
        renderTargets();
        updateWheel();
        spinGuard();
      });
      box.appendChild(row);
    });
  }

  function updateWheel() {
    var disc = el('wheel-disc');
    var label = el('chance-label');
    var gy = el('match-goal');
    var my = el('match-you');

    my.textContent = drop ? CD.PIECES[drop].glyph : '?';
    my.className = drop ? 'mg r-' + CD.PIECES[drop].rarity : 'mg ph';

    gy.textContent = target ? CD.PIECES[target].glyph : '?';
    gy.className = target ? 'mg r-' + CD.PIECES[target].rarity : 'mg ph';

    if (drop && target) {
      var pct = pctOf(CD.PIECES[drop].val, CD.PIECES[target].val);
      var deg = pct * 3.6;
      disc.style.background = 'conic-gradient(from 0deg, var(--gold) 0deg ' + deg + 'deg, rgba(255,255,255,.07) ' + deg + 'deg 360deg)';
      label.textContent = pct.toFixed(1) + '%';
    } else {
      disc.style.background = 'conic-gradient(from 0deg, rgba(255,255,255,.05) 0deg 360deg)';
      label.textContent = '—';
    }
  }

  function spinGuard() {
    el('btn-spin').disabled = spinning || drop === null || target === null || !CD.state;
  }

  function spin() {
    if (spinning || drop === null || target === null || !CD.state) return;
    var inCode = drop, outCode = target;
    var inVal = CD.PIECES[inCode].val;
    var outVal = CD.PIECES[outCode].val;
    var feePct = CD.config().upgradeFeePct || 0;
    var fee = Math.round(inVal * feePct / 100);
    if (fee > 0 && !CD.spend(fee)) {
      CD.toast('Не хватает ◈ на комиссию спина', 'fail');
      return;
    }

    spinning = true;
    spinGuard();

    var pct = pctOf(inVal, outVal);
    var winDeg = pct * 3.6;
    var r = Math.random() * 360;
    var win = r < winDeg;

    var delta = 360 * 5 + (((-(r) - rot) % 360) + 360) % 360;
    rot += delta;
    el('wheel-disc').style.transform = 'rotate(' + rot + 'deg)';

    setTimeout(function () {
      CD.addStat('spins');
      if (win) {
        CD.takeFirst(inCode);
        CD.addPiece(outCode);
        CD.addStat('upgradeWins');
        showResult(true, CD.PIECES[outCode], fee, inVal, outVal);
        CD.pushHist({ t: 'upgrade', tag: 'win', note: CD.PIECES[inCode].name + ' → ' + CD.PIECES[outCode].name + ' · шанс ' + pct + '%' });
        CD.toast('Апгрейд удался: ' + CD.PIECES[outCode].name + ' на складе!', 'success');
      } else {
        if (!CD.takeFirst(inCode)) { /* Уже не было */ }
        CD.addStat('upgradeLosses');
        showResult(false, CD.PIECES[outCode], fee, inVal, outVal);
        CD.pushHist({ t: 'upgrade', tag: 'fail', note: 'Крутилка забрала ' + CD.PIECES[inCode].name + ' · шанс ' + pct + '%' });
        CD.toast('Не повезло. ' + CD.PIECES[inCode].name + ' потеряна', 'fail');
      }
      if (fee > 0) CD.pushHist({ t: 'fee', tag: 'gold', note: 'Комиссия спина ' + fee + ' ◈' });
      drop = null;
      target = null;
      updateWheel();
      renderDrop();
      renderTargets();
      spinning = false;
      spinGuard();
    }, 4900);
  }

  function showResult(win, piece, fee, inVal, outVal) {
    var card = el('spin-card');
    var g = el('res-glyph');
    g.textContent = piece.glyph;
    if (win) {
      g.style.color = 'var(--' + piece.rarity + ')';
      g.style.filter = 'drop-shadow(0 0 34px color-mix(in srgb, var(--' + piece.rarity + ') 65%, transparent))';
    } else {
      g.style.color = '#39415c';
      g.style.filter = 'none';
    }
    el('res-title').textContent = win ? 'АПГРЕЙД УДАЛСЯ' : 'ШАНС ПРОВАЛЕН';
    el('res-sub').textContent = win
      ? 'Ставка ' + inVal + ' ◈ превратилась в ' + piece.name + ' на ' + outVal + ' ◈. Множитель ×' + (outVal / inVal).toFixed(1) + '.' + (fee > 0 ? ' Комиссия спина: ' + fee + ' ◈.' : '')
      : 'Крутилка забрала ставку ' + inVal + ' ◈. Фарт не вечный — попробуй снова.' + (fee > 0 ? ' Комиссия спина: ' + fee + ' ◈.' : '');
    card.classList.toggle('win', win);
    card.classList.toggle('lose', !win);
    el('spin-result').classList.add('show');
  }

  function closeResult() {
    el('spin-result').classList.remove('show');
    renderDrop();
  }
})();
