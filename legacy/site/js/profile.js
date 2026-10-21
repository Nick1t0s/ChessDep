(function () {
  function el(id) { return document.getElementById(id); }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    var params = new URLSearchParams(location.search);
    var err = params.get('err');
    if (err) {
      CD.toast(err, 'fail');
      history.replaceState(null, '', 'profile.html');
    }
    renderCard();
    renderStats();
    renderInv();
    renderHist();
    bind();
  });

  function renderCard() {
    var s = CD.state;
    el('avatar').textContent = s.name.charAt(0).toUpperCase();
    el('u-name').textContent = s.name;
    el('u-role').textContent = s.role === 'admin' ? 'ADMIN' : 'USER';
    el('u-role').className = 'role-badge ' + (s.role === 'admin' ? 'admin' : 'user');
    el('u-email').textContent = s.email;
    var d = new Date(s.created);
    el('u-created').textContent = d.toLocaleDateString('ru-RU') + ' в ' + d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0');
    el('u-nick').textContent = '@' + s.name;
  }

  function renderStats() {
    var s = CD.state;
    var st = s.stats || {};
    el('ps-balance').textContent = CD.fmt(s.balance);
    el('ps-pieces').textContent = s.pieces.length;
    el('ps-value').textContent = CD.fmt(CD.totalValue());
    el('ps-spins').textContent = st.spins || 0;
    el('ps-wins').textContent = st.upgradeWins || 0;
    el('ps-losses').textContent = st.upgradeLosses || 0;
    el('ps-cases').textContent = st.cases || 0;
    el('ps-place').textContent = st.placements || 0;
  }

  function renderInv() {
    var box = el('pc-inv');
    box.innerHTML = '';
    var codes = CD.uniqueCodes().sort(function (a, b) {
      return CD.PIECES[b].val - CD.PIECES[a].val;
    });
    if (codes.length === 0) {
      box.innerHTML = '<div class="empty-note">Красота! Совсем пусто. Открывай кейсы и качай колесо.</div>';
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
        '<span class="count">×' + CD.count(code) + '</span>';
      box.appendChild(tile);
    });
  }

  function renderHist() {
    var box = el('pc-hist');
    box.innerHTML = '';
    var h = CD.hist();
    if (h.length === 0) {
      box.innerHTML = '<div class="hist-empty">История пуста. Крути колесо и открывай кейсы.</div>';
      return;
    }
    h.slice(0, 12).forEach(function (row) {
      var d = document.createElement('div');
      d.className = 'hist-row';
      var tag = document.createElement('span');
      tag.className = 'tag ' + (row.tag || '');
      tag.textContent = tagText(row.t);
      var txt = document.createElement('span');
      txt.textContent = row.note || row.t;
      var time = document.createElement('time');
      time.textContent = new Date(row.time).toLocaleString('ru-RU');
      d.appendChild(tag);
      d.appendChild(txt);
      d.appendChild(time);
      box.appendChild(d);
    });
  }

  function tagText(t) {
    switch (t) {
      case 'case': return 'кейс';
      case 'board': return 'доска';
      case 'fee': return 'комиссия';
      case 'sell': return 'продажа';
      default: return 'апгрейд';
    }
  }

  function bind() {
    var s = CD.state;

    el('btn-boost').addEventListener('click', function () {
      if (s.boostUsed) {
        CD.toast('Стартовый буст уже выдавался одним акком', 'fail');
        return;
      }
      s.boostUsed = true;
      CD.addBalance(200);
      CD.pushHist({ t: 'boost', tag: 'gold', note: 'Стартовый буст +200 ◈' });
      CD.toast('Начислено +200 ◈', 'success');
      renderStats();
    });

    el('btn-pass-show').addEventListener('click', function () {
      el('pass-panel').classList.toggle('show');
    });

    el('btn-pass-apply').addEventListener('click', function () {
      var oldP = el('pp-old');
      var newP = el('pp-new');
      var newP2 = el('pp-new2');
      var res = null;
      if (newP.value.length < 6) res = 'Новый пароль: минимум 6 символов';
      else if (newP.value !== newP2.value) res = 'Пароли не совпадают';
      else if (oldP.value === newP.value) res = 'Новый пароль такой же, как старый';
      else {
        res = CD.changePass(oldP.value, newP.value);
        if (!res) {
          oldP.value = newP.value = newP2.value = '';
          CD.toast('Пароль обновлён', 'success');
        }
      }
      if (res) CD.toast(res, 'fail');
    });

    el('btn-logout').addEventListener('click', function () {
      if (confirm('Точно выйти из аккаунта?')) CD.logout();
    });
  }
})();
