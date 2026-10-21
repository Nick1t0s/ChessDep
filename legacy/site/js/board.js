(function () {
  var UPG = {
    pawn:   { to: 'knight', pct: 22 },
    knight: { to: 'rook',   pct: 16 },
    bishop: { to: 'rook',   pct: 16 },
    rook:   { to: 'queen',  pct: 9 },
    queen:  { to: 'queen2', pct: 6 },
    queen2: { to: 'king',   pct: 4 }
  };
  var FILES = 'abcdefgh';
  var ENEMY_ROW = ['rook', 'knight', 'bishop', 'queen', 'king', 'bishop', 'knight', 'rook'];
  var cells = new Array(64).fill(null);
  var selected = null;

  function el(id) { return document.getElementById(id); }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    ENEMY_ROW.forEach(function (code, i) {
      cells[i] = { code: code, side: 'enemy' };
    });
    renderRanks();
    renderLegend();
    render();
  });

  function renderRanks() {
    var r = el('ranks'), f = el('files');
    for (var i = 0; i < 8; i++) {
      var s = document.createElement('span');
      s.textContent = String(8 - i);
      r.appendChild(s);
      var s2 = document.createElement('span');
      s2.textContent = FILES[i];
      f.appendChild(s2);
    }
  }

  function renderLegend() {
    var box = el('legend');
    box.innerHTML = '';
    Object.keys(UPG).forEach(function (code) {
      var p = CD.PIECES[code];
      var up = UPG[code];
      var row = document.createElement('div');
      row.className = 'legend-row r-' + p.rarity;
      row.innerHTML =
        '<span class="glyph">' + p.glyph + '</span>' +
        '<span class="to">→</span>' +
        '<span class="to"><span class="glyph">' + CD.PIECES[up.to].glyph + '</span></span>' +
        '<span class="pc">' + up.pct + '%</span>';
      box.appendChild(row);
    });
    var kingRow = document.createElement('div');
    kingRow.className = 'legend-row r-legendary';
    kingRow.innerHTML =
      '<span class="glyph">' + CD.PIECES.king.glyph + '</span>' +
      '<span class="to">апгрейда нет</span>' +
      '<span class="pc">0%</span>';
    box.appendChild(kingRow);
  }

  function render() {
    var b = el('board');
    b.innerHTML = '';
    cells.forEach(function (c, i) {
      var row = Math.floor(i / 8), col = i % 8;
      var d = document.createElement('div');
      d.className = 'cell ' + ((row + col) % 2 === 0 ? 'light' : 'dark');
      if (c) {
        d.classList.add(c.side === 'you' ? 'you' : 'enemy', 'occ');
        var g = document.createElement('span');
        g.className = 'glyph';
        g.textContent = CD.PIECES[c.code].glyph;
        if (c.side === 'you') {
          var skinColor = CD.skinColorFor(c.code);
          if (skinColor) g.style.color = skinColor;
        }
        d.appendChild(g);
      }
      d.addEventListener('click', function () { onCell(i); });
      b.appendChild(d);
    });
    b.classList.toggle('placing', !!selected);
    renderBench();
  }

  function renderBench() {
    var box = el('bench');
    box.innerHTML = '';
    var codes = CD.uniqueCodes().sort(function (a, b) {
      return CD.PIECES[a].val - CD.PIECES[b].val;
    });
    if (codes.length === 0) {
      var note = document.createElement('div');
      note.className = 'hint';
      note.textContent = 'Резерв пуст. Забери фигуру с доски обратно или открой кейсы.';
      box.appendChild(note);
      return;
    }
    codes.forEach(function (code) {
      var p = CD.PIECES[code];
      var item = document.createElement('div');
      item.className = 'item r-' + p.rarity + (selected === code ? ' selected' : '') + (CD.count(code) === 0 ? ' dim' : '');
      item.innerHTML =
        '<span class="glyph">' + p.glyph + '</span>' +
        '<span class="name">' + p.name + '</span>' +
        '<span class="val">' + p.val + ' ◈</span>' +
        '<span class="count">×' + CD.count(code) + '</span>';
      item.addEventListener('click', function () {
        selected = (selected === code) ? null : code;
        render();
      });
      var skinColor = CD.skinColorFor(code);
      if (skinColor) item.querySelector('.glyph').style.color = skinColor;
      box.appendChild(item);
    });
  }

  function onCell(i) {
    var c = cells[i];
    if (c && c.side === 'you') {
      cells[i] = null;
      CD.addPiece(c.code);
      CD.toast(CD.PIECES[c.code].name + ' вернулась в резерв', 'info');
      selected = null;
      render();
      return;
    }
    if (c || !selected) return;
    if (!CD.takeFirst(selected)) {
      CD.toast('Такой фигуры нет в резерве', 'fail');
      selected = null;
      render();
      return;
    }
    cells[i] = { code: selected, side: 'you' };
    var placed = CD.PIECES[selected];
    var up = UPG[selected];
    var coord = FILES[i % 8] + (8 - Math.floor(i / 8));
    CD.addStat('placements');

    if (up && Math.random() < up.pct / 100) {
      var to = CD.PIECES[up.to];
      cells[i] = { code: up.to, side: 'you' };
      addLog(coord, placed.glyph + ' → ' + to.glyph, placed.name + ' → ' + to.name + ' · шанс ' + up.pct + '%', 'ok');
      CD.pushHist({ t: 'board', tag: 'win', note: coord + ': ' + placed.name + ' → ' + to.name + ' (шанс ' + up.pct + '%)' });
      CD.toast('ПОСТАНОВКА-АПГРЕЙД! ' + placed.name + ' стала ' + to.name + '!', 'success');
      selected = null;
      render();
      flash(i);
    } else {
      addLog(coord, placed.glyph, placed.name + (up ? ' · шанс ' + up.pct + '% — мимо' : ' · без апгрейда'), up ? 'bad' : '');
      if (up) CD.pushHist({ t: 'board', tag: 'fail', note: coord + ': ' + placed.name + ' · шанс ' + up.pct + '% — мимо' });
      CD.toast(up ? 'Шанс ' + up.pct + '% не сработал' : 'Король не может быть апгрейдом', up ? 'fail' : 'info');
      selected = null;
      render();
    }
  }

  function flash(i) {
    requestAnimationFrame(function () {
      var cell = el('board').children[i];
      if (cell) cell.classList.add('win-flash');
    });
  }

  function addLog(coord, glyphs, txt, cls) {
    var box = el('log');
    var note = box.querySelector('.log-empty');
    if (note) note.remove();
    var row = document.createElement('div');
    row.className = 'log-row' + (cls ? ' ' + cls : '');
    row.innerHTML =
      '<span class="coord">' + coord + '</span>' +
      '<span class="glyph">' + glyphs + '</span>' +
      '<span class="txt">' + txt + '</span>';
    box.prepend(row);
    while (box.children.length > 9) box.removeChild(box.lastChild);
  }
})();
