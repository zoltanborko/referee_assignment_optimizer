import { api, escapeHtml } from "./api.js";

const app = document.querySelector("#app");
const roleLabels = {
  referee: "Játékvezetői felület",
  sender: "Küldői felület",
  admin: "Adminisztráció",
};

export function renderPage(user, content) {
  app.innerHTML = `
    <header class="topbar">
      <div class="brand">
        <img class="brand-logo" src="/assets/assets/whistle.png" alt="">
        <span>Játékvezetői küldés</span>
      </div>
      <div class="top-actions">
        <span class="user-chip">
          ${escapeHtml(user.username)} · ${roleLabels[user.role] || "Felhasználó"}
        </span>
        <button class="button secondary" id="change-password">Jelszócsere</button>
        <button class="button" id="logout">Kilépés</button>
      </div>
    </header>
    <main class="page">${content}</main>
    <div id="modal-root"></div>`;
  document.querySelector("#logout").addEventListener("click", async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      location.reload();
    }
  });
  document
    .querySelector("#change-password")
    .addEventListener("click", () => showPasswordModal(user, false));
}

export function showPasswordModal(user, required, onDone = () => location.reload()) {
  const root = document.querySelector("#modal-root");
  root.innerHTML = `
    <div class="modal-backdrop">
      <section
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="password-title"
      >
        <p class="eyebrow">${required ? "Első belépés" : "Fiókbeállítás"}</p>
        <h2 id="password-title">
          ${required ? "Állíts be új jelszót" : "Jelszó megváltoztatása"}
        </h2>
        <p class="helper">Legalább 8 karakter hosszú jelszót válassz.</p>
        <form id="password-form">
          <div class="field-grid">
            <div class="field full">
              <label for="current-password">
                ${required ? "Jelenlegi / ideiglenes jelszó" : "Jelenlegi jelszó"}
              </label>
              <input
                id="current-password"
                type="password"
                autocomplete="current-password"
                required
              >
            </div>
            <div class="field full">
              <label for="new-password">Új jelszó</label>
              <input
                id="new-password"
                type="password"
                minlength="8"
                autocomplete="new-password"
                required
              >
            </div>
            <div class="field full">
              <label for="confirm-password">Új jelszó ismét</label>
              <input
                id="confirm-password"
                type="password"
                minlength="8"
                autocomplete="new-password"
                required
              >
            </div>
          </div>
          <label class="checkline" style="margin-top:12px">
            <input id="show-passwords" type="checkbox">
            Jelszavak megjelenítése
          </label>
          <div id="password-message"></div>
          <div class="form-actions">
            <button class="button" id="save-password">Jelszó mentése</button>
            ${required ? "" : `
              <button type="button" class="button secondary" id="cancel-password">
                Mégse
              </button>
            `}
          </div>
        </form>
      </section>
    </div>`;
  const form = root.querySelector("#password-form");
  const currentInput = root.querySelector("#current-password");
  const newInput = root.querySelector("#new-password");
  const confirmInput = root.querySelector("#confirm-password");
  const message = root.querySelector("#password-message");
  const saveButton = root.querySelector("#save-password");
  let mismatchVisible = false;
  const validateMatch = () => {
    const mismatch =
      confirmInput.value.length > 0 && newInput.value !== confirmInput.value;
    if (mismatch) {
      message.innerHTML = '<div class="notice error">A két új jelszó nem egyezik.</div>';
      mismatchVisible = true;
    } else if (mismatchVisible) {
      message.replaceChildren();
      mismatchVisible = false;
    }
    saveButton.disabled = mismatch;
    return !mismatch;
  };
  newInput.addEventListener("input", validateMatch);
  confirmInput.addEventListener("input", validateMatch);
  root.querySelector("#show-passwords").addEventListener("change", event => {
    const type = event.currentTarget.checked ? "text" : "password";
    [currentInput, newInput, confirmInput].forEach(input => {
      input.type = type;
    });
  });
  root
    .querySelector("#cancel-password")
    ?.addEventListener("click", () => root.replaceChildren());
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const current_password = currentInput.value;
    const new_password = newInput.value;
    if (!validateMatch()) return;
    saveButton.disabled = true;
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password, new_password }),
      });
      root.replaceChildren();
      onDone({ ...user, must_change_password: false });
    } catch (error) {
      message.innerHTML = `
        <div class="notice error">${escapeHtml(error.message)}</div>`;
      saveButton.disabled = false;
    }
  });
}

export function setAppMarkup(markup) {
  app.innerHTML = markup;
}
