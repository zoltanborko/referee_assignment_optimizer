import { api, dateLabel, emptyState, escapeHtml, matchTable } from "./api.js";

export async function renderReferee(user, renderPage) {
  renderPage(user, `<div class="page-heading"><div><p class="eyebrow">Személyes oldal</p><h1 id="referee-greeting">Szia!</h1><p>Itt találod a véglegesített mérkőzéseidet és az elérhetőségi adataidat.</p></div></div>
    <div class="grid"><section class="card span-12"><div class="card-head"><h2>Saját mérkőzéseim</h2><button class="button secondary small-button" id="refresh-matches">Frissítés</button></div><div id="my-matches"></div></section>
    <section class="card span-12"><div class="card-head"><div><h2>Adataim és elérhetőségem</h2><p class="muted small">A lemondott dátumot legalább 5 nappal korábban lehet felvenni.</p></div></div><form id="profile-form"><div id="profile-fields"></div><div id="profile-message"></div><div class="form-actions"><button class="button">Adatok mentése</button></div></form></section></div>`);
  const matchesEl = document.querySelector("#my-matches");
  const profileEl = document.querySelector("#profile-fields");
  const messageEl = document.querySelector("#profile-message");
  let profile;
  const loadMatches = async () => {
    matchesEl.innerHTML = '<div class="muted">Mérkőzések betöltése…</div>';
    try {
      const { matches } = await api("/me/matches");
      matchesEl.innerHTML = matches.length ? matchTable(matches) : emptyState("Még nincs véglegesített mérkőzésed.");
    } catch (error) { matchesEl.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
  };
  const loadProfile = async () => {
    const data = await api("/me/referee");
    profile = data.referee;
    document.querySelector("#referee-greeting").textContent = `Szia, ${profile.name}!`;
    drawProfile();
  };
  const drawProfile = () => {
    const unavailable = profile.unavailable_dates || [];
    profileEl.innerHTML = `<div class="field-grid">
      <div class="field"><label>Azonosító</label><input value="${escapeHtml(profile.id)}" disabled></div>
      <div class="field"><label>Név</label><input value="${escapeHtml(profile.name)}" disabled></div>
      <div class="field"><label for="residence">Lakóhely</label><input id="residence" value="${escapeHtml(profile.residence || "")}" autocomplete="address-level2"></div>
      <div class="field"><label>Van autód?</label><select id="has-car"><option value="">Nincs megadva</option><option value="true" ${profile.has_car === true ? "selected" : ""}>Igen</option><option value="false" ${profile.has_car === false ? "selected" : ""}>Nem</option></select></div>
      <div class="field full"><label for="banned-teams">Tiltott csapatok (soronként egy)</label><textarea id="banned-teams" rows="3">${escapeHtml((profile.banned_teams || []).join("\n"))}</textarea></div>
      <div class="field full"><label>Lemondott dátumok</label><div class="date-pills">${unavailable.length ? unavailable.map(date => `<span class="date-pill">${escapeHtml(dateLabel(date))}<button type="button" aria-label="${escapeHtml(dateLabel(date))} eltávolítása" data-remove-date="${escapeHtml(date)}">×</button></span>`).join("") : '<span class="muted small">Nincs megadva dátum.</span>'}</div></div>
      <div class="field"><label for="new-date">Új lemondás</label><input id="new-date" type="date" min="${new Date(Date.now() + 5 * 86400000).toISOString().slice(0, 10)}"></div>
      <div class="field" style="align-content:end"><button type="button" class="button secondary" id="add-date">Dátum hozzáadása</button></div>
    </div>`;
    profileEl.querySelector("#add-date").addEventListener("click", () => {
      const value = profileEl.querySelector("#new-date").value;
      if (value && !unavailable.includes(value)) profile.unavailable_dates = [...unavailable, value].sort();
      drawProfile();
    });
    profileEl.querySelectorAll("[data-remove-date]").forEach(button => button.addEventListener("click", () => {
      profile.unavailable_dates = unavailable.filter(value => value !== button.dataset.removeDate);
      drawProfile();
    }));
  };
  document.querySelector("#refresh-matches").addEventListener("click", loadMatches);
  document.querySelector("#profile-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = form.querySelector('button[type="submit"], button:not([type])');
    const car = profileEl.querySelector("#has-car").value;
    const payload = {
      residence: profileEl.querySelector("#residence").value.trim(),
      has_car: car === "" ? null : car === "true",
      banned_teams: profileEl.querySelector("#banned-teams").value.split("\n").map(team => team.trim()).filter(Boolean),
      unavailable_dates: profile.unavailable_dates || [],
    };
    submitButton.disabled = true;
    submitButton.textContent = "Mentés…";
    try {
      await api("/me/referee", { method: "PUT", body: JSON.stringify(payload) });
      const result = await api("/me/referee");
      profile = result.referee;
      drawProfile();
      messageEl.innerHTML = '<div class="notice">Az adataid frissültek.</div>';
    } catch (error) {
      messageEl.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
    } finally {
      if (submitButton.isConnected) {
        submitButton.disabled = false;
        submitButton.textContent = "Adatok mentése";
      }
    }
  });
  try { await Promise.all([loadMatches(), loadProfile()]); }
  catch (error) { profileEl.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
}
