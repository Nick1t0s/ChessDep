(function () {
  var CELLW = 130, GAP = 12;
  var COUNT = 60;
  var WIN_IDX = Math.floor(COUNT * 0.88);
  var spinning = false;

  function el(id) { return document.getElementById(id); }

  function pickRarity() {
    var w = CD.config().skinWeights || { common: 50, uncommon: 26, rare: 14, epic: 6.5, legendary: 2.5, mythic: 1 };
    var keys = Object.keys(w);
    var total = keys.reduce(function (s, k) { return s + w[k]; }, 0);
    var r = Math.random() * total;
    var out = keys[keys.length - 1];
    for (var i = 0; i < keys.length; i++) {
      r -= w[keys[i]];
      if (r < 0) { out = keys[i]; break; }
    }
    return out;
  }

  function pickSkin(rarity) {
    var pool = Object.keys(CD.SKINS).filter(function (c) {
      return CD.SKINS[c].rarity === rarity;
    });
    if (!pool.length) pool = Object.keys(CD.SKINS);
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function pick() { return pickSkin(pickRarity()); }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    renderChances();
    fillStrip(null);
    var cost = CD.config().skinCaseCost;
    el('cost-label').textContent = cost + ' ◈';
    el('btn-open').textContent = 'Открыть · ' + cost + ' ◈';
    el('btn-open').addEventListener('click', spin);
  });

  function cellItem(code) {
    var s = CD.SKINS[code];
    var p = CD.PIECES[s.piece];
    var card = document.createElement('div');
    card.className = 'item r-' + s.rarity;
    card.innerHTML =
      '<span class="glyph">' + p.glyph + '</span>' +
      '<span class="name">' + s.name + '</span>' +
      '<span class="val">' + p.name + ' · ' + s.val + ' <b>◈</b></span>';
    return card;
  }

  function fillStrip(winnerCode) {
    var strip = el('strip');
    strip.classList.remove('strip-anim');
    strip.style.transform = 'translateX(0)';
    strip.innerHTML = '';
    for (var i = 0; i < COUNT; i++) {
      strip.appendChild(cellItem(i === WIN_IDX && winnerCode ? winnerCode : pick()));
    }
  }

  function spin() {
    if (spinning) return;
    var cost = CD.config().skinCaseCost;
    if (!CD.spend(cost)) {
      CD.toast('Не хватает ◈ на скин-кейс', 'fail');
      return;
    }
    spinning = true;
    el('btn-open').disabled = true;

    var winCode = pick();
    fillStrip(winCode);
    void el('strip').offsetWidth;
    el('strip').classList.add('strip-anim');

    var wrapW = el('strip-wrap').clientWidth;
    var offset = WIN_IDX * (CELLW + GAP) + CELLW / 2 - wrapW / 2;
    el('strip').style.transform = 'translateX(' + (-offset) + 'px)';

    setTimeout(function () {
      var s = CD.SKINS[winCode];
      CD.addSkin(winCode);
      CD.pushHist({ t: 'skin', tag: s.rarity === 'mythic' || s.rarity === 'legendary' ? 'gold' : '', note: 'Из скин-кейса: «' + s.name + '» (' + s.val + ' ◈) за ' + cost + ' ◈' });
      showResult(s);
      addRecent(s);
      CD.toast('Дроп со скин-кейса: «' + s.name + '»', 'success');
      spinning = false;
      el('btn-open').disabled = false;
    }, 5800);
  }

  function showResult(s) {
    var box = el('case-result');
    box.classList.remove('show');
    void box.offsetWidth;
    var p = CD.PIECES[s.piece];
    box.innerHTML =
      '<span class="cg r-' + s.rarity + '">' + p.glyph + '</span>' +
      '<div><b>' + s.name + '</b><p>Для ' + p.name.toLowerCase() + ' · ценность ' + s.val + ' ◈ · надевай в «Скинах»</p></div>' +
      '<button class="btn btn-ghost btn-sm" id="cr-close2">Спрятать</button>';
    box.classList.add('show');
    el('cr-close2').addEventListener('click', function () {
      box.classList.remove('show');
    });
  }

  function renderChances() {
    var w = CD.config().skinWeights;
    var total = Object.keys(w).reduce(function (s, k) { return s + w[k]; }, 0);
    var box = el('chance-table');
    box.innerHTML = '';
    Object.keys(w).forEach(function (r) {
      var row = document.createElement('div');
      row.className = 'ch-row r-' + r;
      var sample = Object.keys(CD.SKINS).filter(function (c) { return CD.SKINS[c].rarity === r; })[0];
      row.innerHTML =
        '<span class="glyph">' + (sample ? CD.PIECES[CD.SKINS[sample].piece].glyph : '?') + '</span>' +
        '<span class="nm">' + rarityRu(r) + ' скин</span>' +
        '<span class="pc">' + (w[r] / total * 100).toFixed(1) + '%</span>';
      box.appendChild(row);
    });
  }

  function rarityRu(r) {
    return {
      common: 'обычный', uncommon: 'необычный', rare: 'редкий',
      epic: 'эпик', legendary: 'легендарный', mythic: 'мифический'
    }[r] || r;
  }

  function addRecent(s) {
    var box = el('recent-list');
    var note = box.querySelector('.empty-note');
    if (note) note.remove();
    box.prepend(cellItem(s.code));
    while (box.children.length > 6) box.removeChild(box.lastChild);
  }
})();
