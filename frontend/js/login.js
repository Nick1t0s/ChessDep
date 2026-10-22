import { api, safeNext } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';

await initLayout({ auth: 'none' });
await redirectIfLoggedIn();

const main = h('main', { class: 'wrap' });
const title = h('h1', { class: 'page-title' }, 'Вход');
const form = h('form', { class: 'auth-form-stack', id: 'login-form' });
const loginField = h('input', { id: 'auth-login', name: 'login', type: 'text', autocomplete: 'username', required: true, maxlength: '64' });
const passwordField = h('input', { id: 'auth-password', name: 'password', type: 'password', autocomplete: 'current-password', required: true, maxlength: '128' });
const submit = h('button', { type: 'submit', class: 'btn btn-gold btn-block' }, 'Войти');
form.append(
  h('div', { class: 'field' }, h('label', { for: 'auth-login' }, 'Логин'), loginField),
  h('div', { class: 'field' }, h('label', { for: 'auth-password' }, 'Пароль'), passwordField),
  submit,
);
const errorNote = h('p', { class: 'error-note' });
const note = h('p', { class: 'auth-note' }, 'Нет аккаунта? ', h('a', { href: '/register.html' }, 'Регистрация'));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorNote.textContent = '';
  errorNote.classList.remove('show');
  submit.disabled = true;
  try {
    await api('POST', '/auth/login', { login: loginField.value, password: passwordField.value });
    location.href = safeNext();
  } catch (e) {
    errorNote.textContent = e.message;
    errorNote.classList.add('show');
    submit.disabled = false;
  }
});

main.append(title, h('div', { class: 'card auth-card' }, form, errorNote, note));
document.body.appendChild(main);

async function redirectIfLoggedIn() {
  try {
    await api('GET', '/me', undefined, { redirectOn401: false });
    location.href = safeNext();
  } catch {
    /* не залогинен — показываем форму */
  }
}
