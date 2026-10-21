(function () {
  var PIECE_TYPES = ['pawn', 'knight', 'bishop', 'rook', 'queen', 'king'];
  var skinFilter = 'all';

  function el(id) { return document.getElementById(id); }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    renderSlots();
    renderOwned();
    renderCatalog();
    document.querySelectorAll('.fbtn').forEach(function (b) {
      b.addEventListener('click', function () {
        skinFilter = b.dataset.filter;
        document.querySelectorAll('.fbtn').forEach(function (x) {
          x.classList.toggle('on', x.dataset.filter === skinFilter);
        });
        renderOwned();
      });
    });
  });

  function renderSlots() {
    var box = el('slot-cards');
    box.innerHTML = '';
    PIECE_TYPES.forEach(function (pt) {
      var p = CD.PIECES[pt];
      var cur = CD.skinOf(pt);
      var card = document.createElement('div');
      card.className = 'slot-card';
      card.innerHTML =
        '<span class="glyph" style="--c:' + (cur ? CD.RCOL[cur.rarity] : '#f6f8ff') + '">' + p.glyph + '</span>' +
        '<span class="meta"><b>' + p.name + '</b><span>' +
          (cur ? 'Скин: <b style="color:var(--' + cur.rarity + ')">' + cur.name + '</b>' : 'Скин не надет') +
        '</span></span>' +
        '<select id="sel-' + pt + '"><option value="">— нет скина —</option></select>' +
        '<button class="uneq">Снять</button>';
      var sel = card.querySelector('select');
      CD.ownedSkins().forEach(function (code) {
        var s = CD.SKINS[code];
        if (s.piece !== pt) return;
        var o = document.createElement('option');
        o.value = code;
        o.textContent = s.name + ' (×' + CD.skinCount(code) + ')';
        if (cur && cur.code === code) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () {
        var ok = CD.equip(pt, sel.value || null);
        CD.toast(ok ? (sel.value ? 'Скин «' + CD.SKINS[sel.value].name + '» надет на ' + p.name : 'Скин снят с ' + p.name) : 'Не получилось надеть скин', ok ? 'success' : 'fail');
        renderAll();
      });
      card.querySelector('.uneq').addEventListener('click', function () {
        CD.equip(pt, null);
        CD.toast('Скин снят с ' + p.name, 'info');
        renderAll();
      });
      box.appendChild(card);
    });
  }

  function renderOwned() {
    var box = el('owned-grid');
    box.innerHTML = '';
    var codes = CD.ownedSkins().filter(function (c) {
      return skinFilter === 'all' || CD.SKINS[c].rarity === skinFilter;
    });
    codes.sort(function (a, b) { return CD.SKINS[b].val - CD.SKINS[a].val; });
    if (codes.length === 0) {
      box.innerHTML = '<div class="empty-note grid-empty">Скинов нет. Крути скин-кейс — там падают даже мифики.</div>';
      return;
    }
    codes.forEach(function (code) {
      var s = CD.SKINS[code];
      var p = CD.PIECES[s.piece];
      var equipped = CD.slotOf(s.piece) && CD.slotOf(s.piece).code === code;
      var tile = document.createElement('div');
      tile.className = 'item r-' + s.rarity;
      tile.innerHTML =
        '<span class="glyph">' + p.glyph + '</span>' +
        '<span class="rtag pill r-' + s.rarity + '">' + rarityRu(s.rarity) + '</span>' +
        '<span class="name">' + s.name + '</span>' +
        '<span class="ptype">для ' + p.name.toLowerCase() + '</span>' +
        '<span class="val">' + s.val + ' <b>◈</b></span>' +
        '<span class="count">×' + CD.skinCount(code) + '</span>' +
        (equipped ? '<span class="rtag" style="top:8px;right:8px;left:auto;background:rgba(74,222,128,.12);color:var(--green);border-color:rgba(74,222,128,.4);border-radius:999px;padding:2px 7px;font-size:10.5px;font-weight:700">НАДЕТ</span>' : '') +
        '<button class="sell" data-code="' + code + '">Продать · ' + s.val + ' ◈</button>';
      tile.querySelector('.sell').addEventListener('click', function () {
        if (!CD.takeSkin(code)) return;
        CD.addBalance(s.val);
        CD.pushHist({ t: 'skin', tag: 'gold', note: 'Продан скин «' + s.name + '» за ' + s.val + ' ◈' });
        CD.toast('Скин продан за ' + s.val + ' ◈', 'success');
        renderAll();
      });
      box.appendChild(tile);
    });
  }

  function renderCatalog() {
    var box = el('catalog-grid');
    box.innerHTML = '';
    Object.keys(CD.SKINS).sort(function (a, b) {
      return CD.SKINS[b].val - CD.SKINS[a].val;
    }).forEach(function (code) {
      var s = CD.SKINS[code];
      var p = CD.PIECES[s.piece];
      var own = CD.skinCount(code);
      var div = document.createElement('div');
      div.className = 'item r-' + s.rarity + (own > 0 ? ' selected' : '');
      div.innerHTML =
        '<span class="glyph">' + p.glyph + '</span>' +
        '<span class="name">' + s.name + '</span>' +
        '<span class="ptype">' + p.name.toLowerCase() + '</span>' +
        '<span class="rtag pill r-' + s.rarity + '">' + rarityRu(s.rarity) + '</span>' +
        '<span class="val">' + s.val + ' <b>◈</b>' + (own > 0 ? ' · есть ×' + own : '') + '</span>';
      box.appendChild(div);
    });
  }

  function rarityRu(r) {
    return {
      common: 'обычный', uncommon: 'необычный', rare: 'редкий',
      epic: 'эпик', legendary: 'легенда', mythic: 'мифик'
    }[r] || r;
  }

  function renderAll() {
    renderSlots();
    renderOwned();
    renderCatalog();
  }
})();
