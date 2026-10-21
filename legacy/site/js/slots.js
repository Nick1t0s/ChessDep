(function () {
  var ITEM_H = 130;
  var STRIP_LEN = 30;
  var RESULT_IDX = 26;
  var spinning = false;

  var SYMBOLS = [
    { key: 'pawn',   weight: 30, glyph: '\u265F\uFE0E', name: 'Пешка',  rarity: 'common' },
    { key: 'knight', weight: 20, glyph: '\u265E\uFE0E', name: 'Конь',   rarity: 'uncommon' },
    { key: 'bishop', weight: 20, glyph: '\u265D\uFE0E', name: 'Слон',   rarity: 'uncommon' },
    { key: 'rook',   weight: 14, glyph: '\u265C\uFE0E', name: 'Ладья',  rarity: 'rare' },
    { key: 'queen',  weight: 9,  glyph: '\u265B\uFE0E', name: 'Ферзь',  rarity: 'epic' },
    { key: 'gem',    weight: 3,  glyph: '\u25C6\uFE0E', name: 'Кристалл', rarity: 'mythic' }
  ];

  var PRIZES = {
    gem:    { text: '+1000 ◈ на баланс',  run: function () { CD.addBalance(1000); } },
    queen:  { text: 'Ферзь на склад',     run: function () { CD.addPiece('queen'); } },
    rook:   { text: 'Ладья на склад',     run: function () { CD.addPiece('rook'); } },
    knight: { text: 'Конь на склад',      run: function () { CD.addPiece('knight'); } },
    bishop: { text: 'Слон на склад',      run: function () { CD.addPiece('bishop'); } },
    pawn:   { text: 'Три пешки на склад', run: function () { CD.addPiece('pawn'); CD.addPiece('pawn'); CD.addPiece('pawn'); } }
  };

  function el(id) { return document.getElementById(id); }

  function pickSymbol() {
    var total = SYMBOLS.reduce(function (s, x) { return s + x.weight; }, 0);
    var r = Math.random() * total;
    for (var i = 0; i < SYMBOLS.length; i++) {
      r -= SYMBOLS[i].weight;
      if (r < 0) return SYMBOLS[i];
    }
    return SYMBOLS[0];
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    document.querySelectorAll('.reel').forEach(function (reel) {
      fillReel(reel, pickSymbol());
    });
    el('slot-cost').textContent = CD.config().slotCost;
    el('btn-slot').addEventListener('click', spin);
  });

  function fillReel(reel, finalSym) {
    var strip = reel.querySelector('.reel-strip');
    strip.classList.remove('reel-anim');
    strip.style.transform = 'translateY(0)';
    strip.innerHTML = '';
    for (var i = 0; i < STRIP_LEN; i++) {
      var sym = (i === RESULT_IDX) ? finalSym : pickSymbol();
      strip.appendChild(cell(sym));
    }
  }

  function cell(sym) {
    var c = document.createElement('div');
    c.className = 'reel-cell';
    c.innerHTML = '<span class="glyph r-' + sym.rarity + '">' + sym.glyph + '</span>';
    return c;
  }

  function spinReel(reel, finalSym, delay, done) {
    fillReel(reel, finalSym);
    var strip = reel.querySelector('.reel-strip');
    void strip.offsetWidth;
    strip.classList.add('reel-anim');
    strip.style.transform = 'translateY(' + (-(RESULT_IDX * ITEM_H)) + 'px)';
    setTimeout(done, delay + 3100);
  }

  function spin() {
    if (spinning) return;
    var cost = CD.config().slotCost;
    if (!CD.spend(cost)) {
      CD.toast('Не хватает ◈ на спин', 'fail');
      return;
    }
    spinning = true;
    el('btn-slot').disabled = true;
    el('slot-result').classList.remove('show');

    var finals = [pickSymbol(), pickSymbol(), pickSymbol()];
    var reels = document.querySelectorAll('.reel');
    var doneCount = 0;

    reels.forEach(function (reel, i) {
      spinReel(reel, finals[i], i * 350, function () {
        doneCount++;
        if (doneCount === reels.length) {
          evaluate(finals, cost);
          spinning = false;
          el('btn-slot').disabled = false;
        }
      });
    });
  }

  function evaluate(finals, cost) {
    var reels = document.querySelectorAll('.reel');
    var a = finals[0], b = finals[1], c = finals[2];
    var allSame = a.key === b.key && b.key === c.key;
    var two = a.key === b.key || b.key === c.key || a.key === c.key;

    var res = el('slot-result');
    var glyph = res.querySelector('.glyph');
    var title = res.querySelector('b');
    var sub = res.querySelector('p');

    res.classList.remove('jackpot');
    glyph.className = 'glyph';

    if (allSame) {
      PRIZES[a.key].run();
      glyph.classList.add('r-' + a.rarity);
      glyph.textContent = a.glyph;
      title.textContent = a.key === 'gem' ? 'ДЖЕКПОТ' : 'ТРИ ' + plural(a.key).toUpperCase() + '!';
      sub.textContent = PRIZES[a.key].text + ' · ставка ' + cost + ' ◈';
      if (a.key === 'gem') res.classList.add('jackpot');
      CD.pushHist({ t: 'slot', tag: 'win', note: 'Слоты: 3×' + a.name + ' — ' + PRIZES[a.key].text });
      CD.toast('Слоты: ' + PRIZES[a.key].text + '!', 'success');
    } else if (two) {
      glyph.classList.add('r-uncommon');
      glyph.textContent = a.key === b.key ? a.glyph : c.glyph;
      title.textContent = 'Пара';
      sub.textContent = '+60 ◈ на баланс · ставка ' + cost + ' ◈';
      CD.addBalance(60);
      CD.pushHist({ t: 'slot', tag: 'win', note: 'Слоты: пара — +60 ◈' });
      CD.toast('Слоты: пара, +60 ◈', 'success');
    } else {
      glyph.classList.add('r-common');
      glyph.textContent = c.glyph;
      title.textContent = 'Мимо';
      sub.textContent = 'Ставка ' + cost + ' ◈ сгорела. Крути ещё.';
      CD.pushHist({ t: 'slot', tag: 'fail', note: 'Слоты: нет совпадений · −' + cost + ' ◈' });
      CD.toast('Слоты: мимо. Ставка сгорела', 'fail');
    }
    res.classList.add('show');
    markHits(finals);
  }

  function markHits(finals) {
    var reels = document.querySelectorAll('.reel');
    reels.forEach(function (reel, i) {
      var strip = reel.querySelector('.reel-strip');
      var cells = strip.children;
      for (var k = 0; k < cells.length; k++) cells[k].classList.remove('hit');
      var cellHit = cells[RESULT_IDX + i * 0];
      if (cellHit) cellHit.classList.add('hit');
    });
  }

  function plural(key) {
    return {
      pawn: 'пешки', knight: 'коня', bishop: 'слона',
      rook: 'ладьи', queen: 'ферзя', gem: 'кристалла'
    }[key] || key;
  }
})();
