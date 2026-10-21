(function () {
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.table-tools input').forEach(function (inp) {
      inp.addEventListener('input', render);
    });
    render();
  });

  function render() {
    var q = document.getElementById('lb-search');
    var query = q ? q.value.trim().toLowerCase() : '';
    var all = CD.userList().sort(function (a, b) {
      return worth(b) - worth(a);
    });

    var stUsers = document.getElementById('lb-users');
    var stTop = document.getElementById('lb-top');
    var stMine = document.getElementById('lb-mine');
    if (stUsers) stUsers.textContent = all.length;
    if (stTop) stTop.textContent = all.length ? CD.fmt(Math.ceil(worth(all[0]))) : 0;
    if (stMine) {
      var me = all.filter(function (u) { return u.key === CD.user; })[0];
      stMine.textContent = me ? CD.fmt(Math.ceil(worth(me))) : '—';
    }

    var list = all.slice(0, 12);
    if (query) {
      list = list.filter(function (u) {
        return u.name.toLowerCase().indexOf(query) !== -1;
      });
    }
    var body = document.getElementById('lb-body');
    body.innerHTML = '';
    if (list.length === 0) {
      body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--dim)">Пока только ты. Позови друзей — основной каталог гонок скучает.</td></tr>';
      return;
    }
    list.forEach(function (u, i) {
      var tr = document.createElement('tr');
      var cls = [];
      if (i === 0) cls.push('top1');
      else if (i === 1) cls.push('top2');
      else if (i === 2) cls.push('top3');
      if (CD.user === u.key) cls.push('me');
      tr.className = cls.join(' ');
      var av = u.name.charAt(0).toUpperCase();
      var pv = u.pieces.length;
      var sv = u.pieces.reduce(function (s, c) { return s + CD.PIECES[c].val; }, 0);
      tr.innerHTML =
        '<td class="lb-place">#' + (i + 1) + '</td>' +
        '<td><div class="lb-player"><span class="av">' + av + '</span>' +
        '<span><span class="nm">' + u.name + '</span><br><span class="sub">' + (u.role === 'admin' ? 'админ' : 'игрок') + '</span></span></div></td>' +
        '<td class="mono">' + pv + ' шт</td>' +
        '<td class="mono">' + CD.fmt(sv) + ' ◈</td>' +
        '<td class="mono">' + CD.fmt(u.balance) + ' ◈</td>' +
        '<td class="mono sum">' + CD.fmt(sv + u.balance) + ' ◈</td>';
      body.appendChild(tr);
    });
  }

  function worth(u) {
    var s = u.pieces.reduce(function (sum, c) { return sum + (CD.PIECES[c] || {}).val; }, 0);
    return s + (u.balance || 0);
  }
})();
