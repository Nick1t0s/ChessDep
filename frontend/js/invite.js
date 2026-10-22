import { api } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';

await initLayout({ auth: 'required' });

const params = new URLSearchParams(location.search);
const code = params.get('code') ?? '';
const CODE_RE = /^[a-z2-9]{10}$/;

const noteEl = h('p', { class: 'error-note' });
const card = h('div', { class: 'card auth-card' });

if (!CODE_RE.test(code)) {
  noteEl.textContent = 'Некорректная ссылка';
  noteEl.classList.add('show');
  card.appendChild(noteEl);
  card.appendChild(h('a', { href: '/index.html', class: 'btn btn-ghost btn-block' }, 'В лобби'));
} else {
  card.appendChild(h('h3', { class: 'card-title' }, 'Вас пригласили сыграть'));
  const acceptBtn = h('button', { type: 'button', class: 'btn btn-gold btn-block' }, 'Принять');
  acceptBtn.addEventListener('click', async () => {
    acceptBtn.disabled = true;
    noteEl.classList.remove('show');
    try {
      const out = await api('POST', '/invites/' + encodeURIComponent(code) + '/accept');
      location.href = '/game.html?id=' + encodeURIComponent(out.game_id);
    } catch (e) {
      noteEl.textContent = e.message;
      noteEl.classList.add('show');
      if (e.code === 'ALREADY_IN_GAME') {
        try {
          const active = await api('GET', '/me/active-game');
          if (active?.game_id) {
            card.appendChild(h('a', {
              href: '/game.html?id=' + encodeURIComponent(active.game_id),
              class: 'btn btn-ghost btn-block',
            }, 'Вернуться в свою партию'));
          }
        } catch {
          /* не нашли свою партию — остаётся только сообщение */
        }
      } else {
        acceptBtn.disabled = false;
      }
    }
  });
  card.append(acceptBtn, noteEl);
}

const mainWrap = document.createElement('main');
mainWrap.className = 'wrap';
mainWrap.appendChild(card);
document.body.appendChild(mainWrap);
