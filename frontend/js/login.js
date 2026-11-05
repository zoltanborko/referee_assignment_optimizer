import { api, escapeHtml } from "./api.js";
import { setAppMarkup, showPasswordModal } from "./common.js";

export function renderLogin(onAuthenticated) {
  setAppMarkup(`<main class="login-wrap"><section class="login-card">
    <div class="brand"><img class="brand-logo" src="/assets/assets/whistle.png" alt=""><span>Játékvezetői küldés</span></div>
    <h1>Bejelentkezés</h1>
    <p class="helper">Add meg a rendszerhez kapott felhasználónevedet és jelszavadat.</p>
    <form id="login-form"><div class="field"><label for="username">Felhasználónév</label><input id="username" name="username" autocomplete="username" required autofocus></div>
    <div class="field"><label for="password">Jelszó</label><input id="password" name="password" type="password" autocomplete="current-password" required></div>
    <div id="login-message"></div><button class="button">Belépés</button></form>
  </section></main><div id="modal-root"></div>`);
  document.querySelector("#login-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button");
    const message = document.querySelector("#login-message");
    button.disabled = true;
    button.textContent = "Belépés…";
    try {
      const data = await api("/auth/login", { method: "POST", body: JSON.stringify({
        username: form.username.value, password: form.password.value
      }), timeoutMs: 20000 });
      if (data.user.must_change_password) showPasswordModal(data.user, true, onAuthenticated);
      else onAuthenticated(data.user);
    } catch (error) {
      if (form.isConnected) {
        message.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
        button.textContent = "Belépés";
        button.disabled = false;
      }
    }
  });
}
