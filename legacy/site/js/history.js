(function () {
  var filter = 'all';

  function el(id) { return document.getElementById(id); }

  var TAGS = {
    upgrade: 'апгрейд',
    case: 'кейс',
    board: 'доска',
    sell: 'продажа',
    skin: 'скин',
    slot: 'слоты',
    deposit: 'депозит',
    fee: 'комиссия',
    boost: 'буст'
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    document.querySelectorAll('#hist-filters .fbtn').forEach(function (b) {
      b.addEventListener('click', function () {
        filter = b.dataset.filter;
        document.querySelectorAll('#hist-filters .fbtn').forEach(function (x) {
          x.classList.toggle('on', x === b);
        });
        render();
      });
    });
    render();
  });

  function render() {
    var box = el('hist-list');
    box.innerHTML = '';
    var list = CD.hist().filter(function (row) {
      return filter === 'all' || row.t === filter;
    });
    if (list.length === 0) {
      box.innerHTML = '<div class="hist-empty">Тишина. Сыграй что-нибудь — история появится тут.</div>';
      return;
    }
    list.forEach(function (row) {
      var d = document.createElement('div');
      d.className = 'hist-row';
      var tag = document.createElement('span');
      tag.className = 'tag ' + (row.tag || '');
      tag.textContent = TAGS[row.t] || row.t || ' action';
      var txt = document.createElement('span');
      txt.textContent = row.note || '—';
      var time = document.createElement('time');
      time.textContent = new Date(row.time).toLocaleString('ru-RU');
      d.appendChild(tag);
      d.appendChild(txt);
      d.appendChild(time);
      box.appendChild(d);
    });
  }
})();
