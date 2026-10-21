(function () {
  var FILTERS = [
    ['all', 'Все'],
    ['pawn', 'Пешки'],
    ['knight', 'Конь/Слон'],
    ['rook', 'Ладьи'],
    ['queen', 'Ферзь'],
    ['queen2', 'Ферзь ×2'],
    ['king', 'Король']
  ];
  var filter = 'all';

  function el(id) { return document.getElementById(id); }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    renderFilters();
    render();
    el('btn-seed').addEventListener('click', seed);
  });

  function renderFilters() {
    var box = el('filters');
    box.innerHTML = '';
    FILTERS.forEach(function (f) {
      var b = document.createElement('button');
      b.className = 'fbtn' + (filter === f[0] ? ' on' : '');
      b.textContent = f[1];
      b.addEventListener('click', function () {
        filter = f[0];
        renderFilters();
        render();
      });
      box.appendChild(b);
    });
  }

  function render() {
    var stCount = document.getElementById('st-count');
    var stValue = document.getElementById('st-value');
    var stKing = document.getElementById('st-kings');
    if (stCount) stCount.textContent = CD.state.pieces.length;
    if (stValue) stValue.textContent = CD.fmt(CD.totalValue());
    if (stKing) stKing.textContent = CD.count('king');

    var box = el('grid');
    box.innerHTML = '';
    var codes = CD.uniqueCodes().filter(function (c) {
      return filter === 'all' || c === filter;
    });
    codes.sort(function (a, b) { return CD.PIECES[b].val - CD.PIECES[a].val; });

    if (codes.length === 0) {
      var note = document.createElement('div');
      note.className = 'empty-note grid-empty';
      note.textContent = 'Тут пусто. Апгрейди, что есть, или ткни «Наполнить демо-склад».';
      box.appendChild(note);
      return;
    }

    codes.forEach(function (code) {
      var p = CD.PIECES[code];
      var tile = document.createElement('div');
      tile.className = 'item r-' + p.rarity;
      tile.innerHTML =
        '<span class="glyph">' + p.glyph + '</span>' +
        '<span class="name">' + p.name + '</span>' +
        '<span class="val">' + p.val + ' <b>◈</b></span>' +
        '<span class="count">×' + CD.count(code) + '</span>' +
        '<button class="sell" data-code="' + code + '">Продать · ' + p.val + ' ◈</button>';
      tile.querySelector('.sell').addEventListener('click', function () {
        if (!CD.takeFirst(code)) return;
        CD.addBalance(p.val);
        CD.pushHist({ t: 'sell', tag: 'gold', note: 'Продана ' + p.name + ' за ' + p.val + ' ◈' });
        CD.toast('Продано: ' + p.name + ' за ' + p.val + ' ◈', 'success');
        render();
      });
      box.appendChild(tile);
    });
  }

  function seed() {
    ['pawn', 'pawn', 'pawn', 'pawn', 'knight', 'knight', 'bishop', 'rook', 'queen'].forEach(function (c) {
      CD.addPiece(c);
    });
    CD.toast('Демо-склад наполнен', 'success');
    render();
  }
})();
