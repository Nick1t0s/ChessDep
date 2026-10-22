import { api, safeNext } from './api.js';
import { h } from './dom.js';
import { initLayout } from './layout.js';

await initLayout({ auth: 'none' });
await redirectIfLoggedIn();

const main = h('main', { class: 'wrap' });
const title = h('h1', { class: 'page-title' }, 'Регистрация');
const form = h('form', { class: 'auth-form-stack', id: 'register-form' });
const loginField = h('input', { id: 'auth-login', name: 'login', type: 'text', autocomplete: 'username', required: true, minlength: '3', maxlength: '16' });
const emailField = h('input', { id: 'auth-email', name: 'email', type: 'email', autocomplete: 'email', required: true, maxlength: '128' });
const passwordField = h('input', { id: 'auth-password', name: 'password', type: 'password', autocomplete: 'new-password', required: true, minlength: '8', maxlength: '128' });
const submit = h('button', { type: 'submit', class: 'btn btn-gold btn-block' }, 'Создать аккаунт');
form.append(
  h('div', { class: 'field' }, h('label', { for: 'auth-login' }, 'Логин'), loginField),
  h('div', { class: 'field' }, h('label', { for: 'auth-email' }, 'Email'), emailField),
  h('div', { class: 'field' }, h('label', { for: 'auth-password' }, 'Пароль'), passwordField),
  submit,
);
const errorNote = h('p', { class: 'error-note' });
const note = h('p', { class: 'auth-note' }, 'Уже есть аккаунт? ', h('a', { href: '/login.html' }, 'Вход'));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorNote.textContent = '';
  errorNote.classList.remove('show');
  submit.disabled = true;
  try {
    await api('POST', '/auth/register', {
      login: loginField.value,
      email: emailField.value,
      password: passwordField.value,
    });
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
