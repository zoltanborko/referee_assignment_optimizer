import { api, dateLabel, emptyState, escapeHtml, matchTable } from "./api.js";

export async function renderSender(user, renderPage) {
  renderPage(user, `<div class="page-heading"><div><p class="eyebrow">Küldés kezelése</p><h1>Feltöltések és kiosztások</h1><p>Tölts fel mérkőzéseket, készíts kiosztási piszkozatot, majd véglegesítsd a küldést.</p></div></div>
    <div class="grid"><section class="card span-12"><div class="card-head"><h2>Új Excel-feltöltés</h2><span class="badge">.xlsx vagy .xls</span></div>
      <form id="upload-form" class="inline"><input id="excel-file" type="file" accept=".xlsx,.xls" required><button class="button">Excel feltöltése</button></form><div id="upload-message"></div>
      <p class="helper">Ha a fájl bármelyik dátumára már van feltöltés, a teljes Excel elutasításra kerül.</p></section>
      <section class="card span-12"><div class="card-head"><div><h2>Feltöltött mérkőzések</h2><p class="muted small">A piszkozat csak neked látható; a játékvezetők a véglegesített küldést látják.</p></div><button class="button secondary small-button" id="refresh-uploads">Frissítés</button></div><div id="uploads"></div></section>
      <section class="card span-12"><div class="card-head"><h2>Figyelmeztetések</h2><button class="button secondary small-button" id="refresh-notifications">Frissítés</button></div><div id="notifications"></div></section></div>`);
  const list = document.querySelector("#uploads");
  const message = document.querySelector("#upload-message");
  const refresh = async () => {
    list.innerHTML = '<p class="muted">Feltöltések betöltése…</p>';
    try {
      const { uploads } = await api("/uploads");
      list.innerHTML = uploads.length ? uploads.map(uploadCard).join("") : emptyState("Még nincs feltöltés.");
      list.querySelectorAll("[data-upload-action]").forEach(button => button.addEventListener("click", () => act(button)));
      list.querySelectorAll("[data-upload-detail]").forEach(button => button.addEventListener("click", () => toggleDetail(button)));
      list.querySelectorAll("[data-upload-cancellations]").forEach(button => {
        const upload = uploads.find(item => String(item.upload_id) === button.dataset.uploadCancellations);
        button.addEventListener("click", () => toggleCancellations(button, upload?.dates || []));
      });
      list.querySelectorAll("[data-upload-exclusions]").forEach(button => {
        button.addEventListener("click", () => toggleExclusions(button));
      });
    } catch (error) { list.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
  };
  const loadNotifications = async () => {
    const target = document.querySelector("#notifications");
    try {
      const { notifications } = await api("/notifications");
      target.innerHTML = notifications.length ? `<div class="list">${notifications.map(item => `<div class="list-row"><div><div>${escapeHtml(item.message)}</div><p class="muted small">${escapeHtml(dateLabel(item.match_date))}${item.read_at ? " · Olvasva" : " · Új"}</p></div>${item.read_at ? "" : `<button class="button secondary small-button" data-read="${item.notification_id}">Olvasottnak jelöl</button>`}</div>`).join("")}</div>` : emptyState("Nincs figyelmeztetés.");
      target.querySelectorAll("[data-read]").forEach(button => button.addEventListener("click", async () => {
        try { await api(`/notifications/${button.dataset.read}/read`, { method: "POST", body: "{}" }); await loadNotifications(); }
        catch (error) { target.insertAdjacentHTML("afterbegin", `<div class="notice error">${escapeHtml(error.message)}</div>`); }
      }));
    } catch (error) { target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
  };
  document.querySelector("#upload-form").addEventListener("submit", async event => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const file = document.querySelector("#excel-file").files[0];
    if (!file) return;
    const button = formElement.querySelector("button");
    button.disabled = true;
    const form = new FormData(); form.append("file", file);
    try {
      const data = await api("/matches", { method: "POST", body: form });
      const warnings = (data.warnings || []).join(" ");
      message.innerHTML = `<div class="notice ${warnings ? "warning" : ""}">${escapeHtml(data.message)} ${data.count} mérkőzés feldolgozva. ${escapeHtml(warnings)}</div>`;
      formElement.reset();
      await refresh();
    } catch (error) { message.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
    finally { button.disabled = false; }
  });
  document.querySelector("#refresh-uploads").addEventListener("click", refresh);
  document.querySelector("#refresh-notifications").addEventListener("click", loadNotifications);
  await Promise.all([refresh(), loadNotifications()]);
}

export function uploadCard(upload) {
  const draft = upload.draft;
  const published = upload.published;
  const dates = (upload.dates || []).map(dateLabel).join(", ");
  const current = draft || published;
  const canManage = upload.is_owner === true;
  const status = draft ? '<span class="badge amber">Piszkozat</span>' : published ? '<span class="badge green">Véglegesítve</span>' : '<span class="badge">Nincs kiosztás</span>';
  const ownership = canManage ? "Saját feltöltés" : "Másik küldő feltöltése · csak megtekintés";
  const stats = current ? `<span class="muted small">${current.assigned_count ?? 0} kiosztott · ${current.unassigned_count ?? 0} hiányzó</span>` : "";
  const unusedReferees = current?.unused_referees_by_date
    ? Object.entries(current.unused_referees_by_date).map(([date, referees]) =>
      `<div class="muted small"><strong>${escapeHtml(dateLabel(date))} · Fel nem használt játékvezetők:</strong> ${referees.length ? referees.map(referee => escapeHtml(referee.name || referee.id)).join(", ") : "Nincs fel nem használt játékvezető."}</div>`
    ).join("")
    : "";
  return `<article class="card upload-card" data-upload-id="${upload.upload_id}"><div class="upload-summary"><div><div class="inline"><strong>${escapeHtml(upload.source_filename || `Feltöltés #${upload.upload_id}`)}</strong>${status}</div><div class="muted small">${escapeHtml(ownership)} · ${escapeHtml(dates)} ${stats ? ` · ${stats}` : ""}</div></div>
    <div class="actions"><button class="button secondary small-button" data-upload-detail="${upload.upload_id}">Meccsek megtekintése</button>
      <button class="button secondary small-button" data-upload-cancellations="${upload.upload_id}">Lemondások megtekintése</button>
      ${canManage ? `<button class="button secondary small-button" data-upload-exclusions="${upload.upload_id}">Letiltás</button>` : ""}
      ${canManage ? `<button class="button small-button" data-upload-action="assign" data-id="${upload.upload_id}">Kiosztás keresése</button>` : ""}
      ${canManage && draft ? `<button class="button small-button" data-upload-action="finalize" data-id="${upload.upload_id}" ${draft.assigned_count ? "" : "disabled"}>Véglegesítés</button>` : ""}
      ${canManage ? `<button class="button danger small-button" data-upload-action="delete" data-id="${upload.upload_id}">Törlés</button>` : ""}</div></div>${unusedReferees ? `<div class="upload-details">${unusedReferees}</div>` : ""}<div class="divider"></div><div class="upload-details hidden" id="detail-${upload.upload_id}"></div><div class="upload-details hidden" id="cancellations-${upload.upload_id}"></div><div class="upload-details hidden" id="exclusions-${upload.upload_id}"></div></article>`;
}

async function toggleDetail(button) {
  const id = button.dataset.uploadDetail;
  const target = document.querySelector(`#detail-${CSS.escape(id)}`);
  if (!target.classList.contains("hidden")) {
    target.classList.add("hidden");
    button.textContent = "Meccsek megtekintése";
    return;
  }
  target.classList.remove("hidden");
  button.textContent = "Meccsek elrejtése";
  target.innerHTML = '<p class="muted">Mérkőzések betöltése…</p>';
  try {
    const { upload } = await api(`/uploads/${id}`);
    target.innerHTML = matchTable(upload.matches, true);
  } catch (error) { target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
}

async function toggleCancellations(button, dates) {
  const id = button.dataset.uploadCancellations;
  const target = document.querySelector(`#cancellations-${CSS.escape(id)}`);
  if (!target.classList.contains("hidden")) {
    target.classList.add("hidden");
    button.textContent = "Lemondások megtekintése";
    return;
  }
  target.classList.remove("hidden");
  button.textContent = "Lemondások elrejtése";
  target.innerHTML = '<p class="muted">Lemondások betöltése…</p>';
  try {
    const { referees } = await api("/referees");
    if (target.classList.contains("hidden")) return;
    target.innerHTML = dates.length ? `<div class="list">${dates.map(date => {
      const names = referees
        .filter(referee => (referee.unavailable_dates || []).includes(date))
        .map(referee => referee.name || referee.id)
        .sort((first, second) => String(first).localeCompare(String(second), "hu"));
      return `<div class="list-row"><div><strong>${escapeHtml(dateLabel(date))}</strong><div class="muted small">${names.length ? names.map(escapeHtml).join(", ") : "Nincs lemondás erre a dátumra."}</div></div></div>`;
    }).join("")}</div>` : emptyState("Ehhez a feltöltéshez nincs dátum.");
  } catch (error) {
    if (target.classList.contains("hidden")) return;
    target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

async function toggleExclusions(button) {
  const id = button.dataset.uploadExclusions;
  const target = document.querySelector(`#exclusions-${CSS.escape(id)}`);
  if (!target.classList.contains("hidden")) {
    target.classList.add("hidden");
    button.textContent = "Letiltás";
    return;
  }
  target.classList.remove("hidden");
  button.textContent = "Letiltások elrejtése";
  target.innerHTML = '<p class="muted">Elérhető játékvezetők betöltése…</p>';
  try {
    const { dates } = await api(`/uploads/${id}/referee-exclusions`);
    if (target.classList.contains("hidden")) return;
    target.innerHTML = dates.map(day => {
      const excluded = new Set((day.excluded_ids || []).map(String));
      const refereeControls = day.referees.length
        ? day.referees.map(referee => `<label class="checkline"><input type="checkbox" data-exclusion-date="${escapeHtml(day.date)}" data-referee-id="${escapeHtml(referee.id)}" ${excluded.has(String(referee.id)) ? "checked" : ""}>${escapeHtml(referee.name || referee.id)}</label>`).join("")
        : '<p class="muted small">Nincs elérhető játékvezető erre a dátumra.</p>';
      return `<section class="exclusion-date" data-date-section="${escapeHtml(day.date)}"><h3>${escapeHtml(dateLabel(day.date))}</h3><p class="muted small">Pipáld be, akit ki kell hagyni az adott napi kiosztásból.</p><div class="list">${refereeControls}</div><div class="exclusion-message" aria-live="polite"></div></section>`;
    }).join("") || emptyState("Nincs dátum ehhez a feltöltéshez.");

    target.querySelectorAll("[data-exclusion-date]").forEach(checkbox => {
      checkbox.addEventListener("change", async () => {
        const dateSection = checkbox.closest("[data-date-section]");
        const dateCheckboxes = [...dateSection.querySelectorAll("[data-exclusion-date]")];
        const originalChecked = checkbox.checked;
        dateCheckboxes.forEach(input => { input.disabled = true; });
        const status = dateSection.querySelector(".exclusion-message");
        status.innerHTML = '<p class="muted small">Letiltások mentése…</p>';
        try {
          await api(`/uploads/${id}/referee-exclusions`, {
            method: "PUT",
            body: JSON.stringify({
              match_date: checkbox.dataset.exclusionDate,
              excluded_referee_ids: dateCheckboxes
                .filter(input => input.checked)
                .map(input => input.dataset.refereeId),
            }),
          });
          status.innerHTML = '<div class="notice">A dátum letiltásai elmentve.</div>';
        } catch (error) {
          checkbox.checked = !originalChecked;
          status.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
        } finally {
          dateCheckboxes.forEach(input => { input.disabled = false; });
        }
      });
    });
  } catch (error) {
    if (!target.classList.contains("hidden")) {
      target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
    }
  }
}

async function act(button) {
  const id = button.dataset.id;
  const action = button.dataset.uploadAction;
  if (action === "delete" && !confirm("Törlöd ezt a feltöltést és a hozzá tartozó kiosztást?")) return;
  if (action === "finalize" && !confirm("Véglegesíted ezt a kiosztást? A játékvezetők ettől kezdve látják a saját meccseiket.")) return;
  const original = button.textContent; button.disabled = true;
  try {
    if (action === "assign") {
      button.textContent = "Keresés…";
      const { assignment } = await api(`/uploads/${id}/assign`, { method: "POST", body: "{}" });
      alert(`Kiosztási piszkozat elkészült.\nKiosztva: ${assignment.assigned_count}\nKiosztatlan: ${assignment.unassigned_count}\nUtazás összesen: ${assignment.total_travel_distance} km`);
    } else if (action === "finalize") {
      await api(`/uploads/${id}/finalize`, { method: "POST", body: "{}" });
    } else {
      await api(`/uploads/${id}`, { method: "DELETE" });
    }
    document.dispatchEvent(new CustomEvent("uploads-changed"));
    button.closest(".page")?.dispatchEvent(new CustomEvent("uploads-changed"));
    // Refresh the owning dashboard without losing role context.
    location.reload();
  } catch (error) { alert(error.message); button.disabled = false; button.textContent = original; }
}
