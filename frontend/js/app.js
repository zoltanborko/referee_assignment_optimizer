import { api, getCsrfToken } from "./api.js";
import { renderPage, showPasswordModal } from "./common.js";
import { renderLogin } from "./login.js";
import { renderReferee } from "./referee.js";
import { renderSender } from "./sender.js";
import { renderAdmin } from "./admin.js";

function enter(user) {
  if (user.must_change_password) {
    showPasswordModal(user, true, enter);
    return;
  }
  if (user.role === "referee") {
    renderReferee(user, renderPage);
  } else if (user.role === "sender") {
    renderSender(user, renderPage);
  } else if (user.role === "admin") {
    renderAdmin(user, renderPage);
  }
}

async function start() {
  try {
    await getCsrfToken();
    const { user } = await api("/auth/me");
    enter(user);
  } catch (error) {
    if (error.status === 401) renderLogin(enter);
    else {
      document.querySelector("#app").innerHTML = `
        <main class="login-wrap">
          <section class="login-card">
            <h1>Nem sikerült betölteni</h1>
            <p>${error.message}</p>
            <button class="button" onclick="location.reload()">Újrapróbálás</button>
          </section>
        </main>`;
    }
  }
}

start();
