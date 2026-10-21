(function () {
  var POOL = [
    ['pawn', 38], ['knight', 17], ['bishop', 17],
    ['rook', 11], ['queen', 7], ['queen2', 3], ['king', 3]
  ];
  var CELLW = 130, GAP = 12;
  var COUNT = 60;
  var WIN_IDX = Math.floor(COUNT * 0.88);
  var spinning = false;

  function el(id) { return document.getElementById(id); }

  function pick() {
    var total = POOL.reduce(function (s, x) { return s + x[1]; }, 0);
    var r = Math.random() * total;
    for (var i = 0; i < POOL.length; i++) {
      r -= POOL[i][1];
      if (r < 0) return POOL[i][0];
    }
    return 'pawn';
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    renderChances();
    fillStrip(null);
    el('cost-label').textContent = CD.config().caseCost + ' ◈';
    el('btn-open').textContent = 'Открыть · ' + CD.config().caseCost + ' ◈';
    el('btn-open').addEventListener('click', spin);
  });

  function cellItem(code) {
    var p = CD.PIECES[code];
    var card = document.createElement('div');
    card.className = 'item r-' + p.rarity;
    card.innerHTML =
      '<span class="glyph">' + p.glyph + '</span>' +
      '<span class="name">' + p.name + '</span>' +
      '<span class="val">' + p.val + ' <b>◈</b></span>';
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
    var cost = CD.config().caseCost;
    if (!CD.spend(cost)) {
      CD.toast('Не хватает ◈ на кейс', 'fail');
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
      var p = CD.PIECES[winCode];
      CD.addPiece(winCode);
      CD.addStat('cases');
      CD.pushHist({ t: 'case', tag: winCode === 'king' || winCode === 'queen2' ? 'gold' : '', note: p.name + ' (' + p.val + ' ◈) за ' + cost + ' ◈' });
      showResult(p);
      addRecent(p);
      CD.toast('Из кейса выпало: ' + p.name + ' (' + p.val + ' ◈)', 'success');
      spinning = false;
      el('btn-open').disabled = false;
    }, 5800);
  }

  function showResult(p) {
    var box = el('case-result');
    box.classList.remove('show');
    void box.offsetWidth;
    box.innerHTML =
      '<span class="cg r-' + p.rarity + '">' + p.glyph + '</span>' +
      '<div><b>' + p.name + '</b><p>Ценность ' + p.val + ' ◈ · уже на складе</p></div>' +
      '<button class="btn btn-ghost btn-sm" id="cr-close2">Спрятать</button>';
    box.classList.add('show');
    el('cr-close2').addEventListener('click', function () {
      box.classList.remove('show');
    });
  }

  function renderChances() {
    var total = POOL.reduce(function (s, x) { return s + x[1]; }, 0);
    var box = el('chance-table');
    box.innerHTML = '';
    POOL.forEach(function (rowDef) {
      var p = CD.PIECES[rowDef[0]];
      var pct = rowDef[1] / total * 100;
      var row = document.createElement('div');
      row.className = 'ch-row r-' + p.rarity;
      row.innerHTML =
        '<span class="glyph">' + p.glyph + '</span>' +
        '<span class="nm">' + p.name + '</span>' +
        '<span class="pc">' + pct.toFixed(1) + '%</span>';
      box.appendChild(row);
    });
  }

  function addRecent(p) {
    var box = el('recent-list');
    var note = box.querySelector('.empty-note');
    if (note) note.remove();
    box.prepend(cellItem(p.code));
    while (box.children.length > 6) box.removeChild(box.lastChild);
  }
})();
