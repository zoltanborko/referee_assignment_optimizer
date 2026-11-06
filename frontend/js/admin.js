import { api, dateLabel, emptyState, escapeHtml, matchTable } from "./api.js";

const cadres = [
  ["", "Nincs megadva"],
  ["megye1", "Megye 1"],
  ["megye2", "Megye 2"],
  ["megye3", "Megye 3"],
  ["megye_egyeb", "Megye egyéb"],
];

export async function renderAdmin(user, renderPage) {
  renderPage(user, `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Rendszerfelügyelet</p>
        <h1>Adminisztráció</h1>
        <p>Felhasználók, játékvezetői profilok és feltöltött küldések kezelése.</p>
      </div>
    </div>
    <div class="grid">
      <section class="card span-7">
        <div class="card-head">
          <h2>Játékvezetők</h2>
          <button class="button secondary small-button" id="refresh-referees">Frissítés</button>
        </div>
        <form id="referee-form">
          <div class="field-grid">
            <div class="field">
              <label for="ref-id">Azonosító</label>
              <input id="ref-id" required>
            </div>
            <div class="field">
              <label for="ref-name">Név</label>
              <input id="ref-name" required>
            </div>
            <div class="field">
              <label for="ref-residence">Lakóhely</label>
              <input id="ref-residence">
            </div>
            <div class="field">
              <label for="ref-cadre">Keret</label>
              <select id="ref-cadre">
                ${cadres.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
              </select>
            </div>
            <div class="field">
              <label for="ref-car">Autó</label>
              <select id="ref-car">
                <option value="">Nincs megadva</option>
                <option value="true">Igen</option>
                <option value="false">Nem</option>
              </select>
            </div>
            <div class="field">
              <label for="ref-active">Státusz</label>
              <select id="ref-active">
                <option value="true">Aktív</option>
                <option value="false">Inaktív</option>
              </select>
            </div>
            <div class="field full">
              <label for="ref-banned">Tiltott csapatok (soronként egy)</label>
              <textarea id="ref-banned" rows="2"></textarea>
            </div>
          </div>
          <div class="form-actions">
            <button class="button" id="save-referee">Új játékvezető</button>
            <button type="button" class="button secondary hidden" id="cancel-referee">Mégse</button>
          </div>
          <div id="referee-message"></div>
        </form>
        <details class="admin-list-disclosure">
          <summary id="referees-summary">Játékvezetők listája</summary>
          <div id="referees" style="margin-top:12px"></div>
        </details>
      </section>
      <section class="card span-5">
        <div class="card-head">
          <h2>Fiókok</h2>
          <button class="button secondary small-button" id="refresh-users">Frissítés</button>
        </div>
        <form id="user-form">
          <div class="field-grid">
            <div class="field">
              <label for="new-username">Felhasználónév</label>
              <input id="new-username" required maxlength="64">
            </div>
            <div class="field">
              <label for="new-role">Szerepkör</label>
              <select id="new-role">
                <option value="sender">Küldő</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <div class="form-actions"><button class="button">Fiók létrehozása</button></div>
          <div id="user-message"></div>
        </form>
        <details class="admin-list-disclosure">
          <summary id="users-summary">Fiókok és jelszó-visszaállítás</summary>
          <div id="users" style="margin-top:12px"></div>
        </details>
      </section>
      <section class="card span-12">
        <div class="card-head">
          <div>
            <h2>Feltöltött mérkőzések</h2>
            <p class="muted small">Az összes küldő feltöltése és kiosztási állapota.</p>
          </div>
          <button class="button secondary small-button" id="refresh-uploads">Frissítés</button>
        </div>
        <div id="uploads"></div>
      </section>
    </div>`);

  const refsEl = document.querySelector("#referees");
  const usersEl = document.querySelector("#users");
  const uploadsEl = document.querySelector("#uploads");
  const refForm = document.querySelector("#referee-form");
  const refMessage = document.querySelector("#referee-message");
  const userMessage = document.querySelector("#user-message");
  let referees = [];
  let editingRefereeId = null;
  const loadReferees = async () => {
    try {
      const data = await api("/referees");
      referees = data.referees.sort((first, second) =>
        String(first.name || "").localeCompare(String(second.name || ""), "hu")
      );
      document.querySelector("#referees-summary").textContent = `Játékvezetők listája (${referees.length})`;
      refsEl.innerHTML = referees.length
        ? `<div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Azonosító</th>
                  <th>Név</th>
                  <th>Település</th>
                  <th>Státusz</th>
                  <th>Művelet</th>
                </tr>
              </thead>
              <tbody>
                ${referees.map(referee => `
                  <tr>
                    <td>${escapeHtml(referee.id)}</td>
                    <td>${escapeHtml(referee.name)}</td>
                    <td>${escapeHtml(referee.residence || "—")}</td>
                    <td>
                      <span class="badge ${referee.active ? "green" : "red"}">
                        ${referee.active ? "Aktív" : "Inaktív"}
                      </span>
                    </td>
                    <td>
                      <div class="actions">
                        <button class="button secondary small-button" data-edit-ref="${escapeHtml(referee.id)}">Szerkesztés</button>
                        <button class="button danger small-button" data-delete-ref="${escapeHtml(referee.id)}">Törlés</button>
                      </div>
                    </td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>`
        : emptyState("Nincs játékvezető.");
      refsEl.querySelectorAll("[data-edit-ref]").forEach(button => button.addEventListener("click", () => fillReferee(button.dataset.editRef)));
      refsEl.querySelectorAll("[data-delete-ref]").forEach(button => button.addEventListener("click", async () => {
        const referee = referees.find(item => String(item.id) === button.dataset.deleteRef);
        if (!referee || !confirm(`Törlöd ${referee.name} játékvezetői profilját? A bejelentkezési fiók megmarad, de inaktív lesz.`)) return;
        button.disabled = true;
        try {
          await api(`/referees/${encodeURIComponent(referee.id)}`, { method: "DELETE" });
          if (editingRefereeId === String(referee.id)) resetRefereeForm();
          refMessage.innerHTML = `<div class="notice">${escapeHtml(referee.name)} játékvezetői profilja törölve.</div>`;
          await loadReferees();
          await loadUsers();
        } catch (error) {
          refMessage.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
          button.disabled = false;
        }
      }));
    } catch (error) { refsEl.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
  };
  const fillReferee = id => {
    const referee = referees.find(item => String(item.id) === String(id));
    if (!referee) return;
    editingRefereeId = String(referee.id);
    document.querySelector("#ref-id").value = referee.id;
    document.querySelector("#ref-id").disabled = true;
    document.querySelector("#ref-name").value = referee.name || "";
    document.querySelector("#ref-name").disabled = true;
    document.querySelector("#ref-residence").value = referee.residence || "";
    document.querySelector("#ref-cadre").value = referee.cadre || "";
    document.querySelector("#ref-car").value = referee.has_car == null ? "" : String(referee.has_car);
    document.querySelector("#ref-active").value = String(referee.active !== false);
    document.querySelector("#ref-banned").value = (referee.banned_teams || []).join("\n");
    document.querySelector("#save-referee").textContent = "Változtatások mentése";
    document.querySelector("#cancel-referee").classList.remove("hidden");
    refForm.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const resetRefereeForm = () => {
    refForm.reset(); document.querySelector("#ref-id").disabled = false;
    editingRefereeId = null;
    document.querySelector("#ref-name").disabled = false;
    document.querySelector("#ref-active").value = "true";
    document.querySelector("#save-referee").textContent = "Új játékvezető";
    document.querySelector("#cancel-referee").classList.add("hidden");
  };
  const loadUsers = async () => {
    try {
      const { users } = await api("/users");
      const visibleUsers = users.filter(account => !(account.role === "referee" && account.referee_id == null));
      document.querySelector("#users-summary").textContent = `Fiókok és jelszó-visszaállítás (${visibleUsers.length})`;
      usersEl.innerHTML = visibleUsers.length
        ? `<div class="list">
            ${visibleUsers.map(account => `
              <div class="list-row">
                <div>
                  <strong>${escapeHtml(account.username)}</strong>
                  <div class="muted small">
                    ${account.role === "admin" ? "Admin" : account.role === "sender" ? "Küldő" : "Játékvezető"}
                    · ${account.must_change_password ? "Jelszócsere szükséges" : "Jelszó beállítva"}
                    · ${account.active ? "Aktív" : "Inaktív"}
                  </div>
                </div>
                <div class="actions">
                  <button class="button secondary small-button" data-reset-user="${account.user_id}">
                    Jelszó visszaállítása
                  </button>
                  ${account.role === "referee" ? "" : `
                    <button
                      class="button ${account.active ? "danger" : "secondary"} small-button"
                      data-toggle-user="${account.user_id}"
                      data-active="${account.active}"
                    >${account.active ? "Inaktiválás" : "Aktiválás"}</button>
                  `}
                </div>
              </div>
            `).join("")}
          </div>`
        : emptyState("Nincs fiók.");
      usersEl.querySelectorAll("[data-reset-user]").forEach(button => button.addEventListener("click", async () => {
        const password = prompt("Adj meg ideiglenes jelszót (legalább 8 karakter):");
        if (!password) return;
        try {
          const data = await api(
            `/users/${button.dataset.resetUser}/reset-password`,
            {
              method: "POST",
              body: JSON.stringify({ temporary_password: password }),
            },
          );
          alert(data.message);
          await loadUsers();
        }
        catch (error) { alert(error.message); }
      }));
      usersEl.querySelectorAll("[data-toggle-user]").forEach(button => button.addEventListener("click", async () => {
        const active = button.dataset.active !== "true";
        try { await api(`/users/${button.dataset.toggleUser}/active`, { method: "PUT", body: JSON.stringify({ active }) }); await loadUsers(); }
        catch (error) { alert(error.message); }
      }));
    } catch (error) { usersEl.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
  };
  const loadUploads = async () => {
    try {
      const { uploads } = await api("/uploads");
      uploadsEl.innerHTML = uploads.length
        ? uploads.map(upload => `
            <article class="card" style="padding:0;margin-bottom:12px">
              <div class="upload-summary">
                <div>
                  <strong>
                    ${escapeHtml(upload.source_filename || `Feltöltés #${upload.upload_id}`)}
                  </strong>
                  <div class="muted small">
                    ${escapeHtml((upload.dates || []).map(dateLabel).join(", "))}
                    · Feltöltő: ${escapeHtml(upload.created_by_username || "—")}
                  </div>
                </div>
                <div class="inline">
                  <span class="badge ${upload.published ? "green" : upload.draft ? "amber" : ""}">
                    ${upload.published ? "Véglegesítve" : upload.draft ? "Piszkozat" : "Feltöltve"}
                  </span>
                  <button class="button secondary small-button" data-show-upload="${upload.upload_id}">
                    Részletek
                  </button>
                  ${upload.has_source_file && (upload.draft || upload.published) ? `
                    <a class="button secondary small-button" href="/uploads/${upload.upload_id}/export">
                      Kitöltött Excel letöltése
                    </a>
                  ` : ""}
                  <button class="button danger small-button" data-delete-upload="${upload.upload_id}">
                    Excel törlése
                  </button>
                </div>
              </div>
              <div class="upload-details hidden" id="upload-${upload.upload_id}"></div>
            </article>
          `).join("")
        : emptyState("Nincs feltöltött mérkőzés.");
      uploadsEl.querySelectorAll("[data-show-upload]").forEach(button => button.addEventListener("click", async () => {
        const target = uploadsEl.querySelector(`#upload-${CSS.escape(button.dataset.showUpload)}`);
        if (!target.classList.contains("hidden")) { target.classList.add("hidden"); return; }
        target.classList.remove("hidden"); target.innerHTML = '<p class="muted">Betöltés…</p>';
        try {
          const { upload } = await api(`/uploads/${button.dataset.showUpload}`);
          target.innerHTML = matchTable(upload.matches, true);
        }
        catch (error) { target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
      }));
      uploadsEl.querySelectorAll("[data-delete-upload]").forEach(button => button.addEventListener("click", async () => {
        if (!confirm("Törlöd ezt az Excel-feltöltést és a hozzá tartozó összes mérkőzést, kiosztást és értesítést?")) return;
        button.disabled = true;
        try {
          await api(`/uploads/${button.dataset.deleteUpload}`, { method: "DELETE" });
          await loadUploads();
          uploadsEl.insertAdjacentHTML("afterbegin", '<div class="notice">Az Excel-feltöltés és a hozzá tartozó adatok törölve.</div>');
        } catch (error) {
          button.disabled = false;
          uploadsEl.insertAdjacentHTML("afterbegin", `<div class="notice error">${escapeHtml(error.message)}</div>`);
        }
      }));
    } catch (error) { uploadsEl.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
  };

  refForm.addEventListener("submit", async event => {
    event.preventDefault();
    const id = document.querySelector("#ref-id").value.trim();
    const carValue = document.querySelector("#ref-car").value;
    const payload = {
      id,
      name: document.querySelector("#ref-name").value.trim(),
      residence: document.querySelector("#ref-residence").value.trim(),
      cadre: document.querySelector("#ref-cadre").value,
      has_car: carValue === "" ? null : carValue === "true",
      active: document.querySelector("#ref-active").value === "true",
      banned_teams: document.querySelector("#ref-banned").value.split("\n").map(x => x.trim()).filter(Boolean),
    };
    const saveButton = document.querySelector("#save-referee");
    const originalText = saveButton.textContent;
    saveButton.disabled = true;
    saveButton.textContent = "Mentés…";
    try {
      if (editingRefereeId !== null) await api(`/referees/${encodeURIComponent(editingRefereeId)}`, { method: "PUT", body: JSON.stringify(payload) });
      else await api("/referees", { method: "POST", body: JSON.stringify(payload) });
      resetRefereeForm();
      await loadReferees();
      await loadUsers();
      refMessage.innerHTML = '<div class="notice">A játékvezető adatai sikeresen elmentve.</div>';
    } catch (error) {
      refMessage.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = editingRefereeId === null ? "Új játékvezető" : originalText;
    }
  });
  document.querySelector("#cancel-referee").addEventListener("click", resetRefereeForm);
  document.querySelector("#user-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const username = document.querySelector("#new-username").value.trim();
    const role = document.querySelector("#new-role").value;
    try {
      const data = await api("/users", { method: "POST", body: JSON.stringify({ username, role }) });
      userMessage.innerHTML = `
        <div class="notice">
          ${escapeHtml(data.message || "Fiók létrehozva.")}
          Kezdeti jelszó: <strong>${escapeHtml(data.initial_password)}</strong>.
          Első belépéskor kötelező megváltoztatni.
        </div>`;
      form.reset();
      await loadUsers();
    } catch (error) { userMessage.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
  });
  document.querySelector("#refresh-referees").addEventListener("click", loadReferees);
  document.querySelector("#refresh-users").addEventListener("click", loadUsers);
  document.querySelector("#refresh-uploads").addEventListener("click", loadUploads);
  await Promise.all([loadReferees(), loadUsers(), loadUploads()]);
}
