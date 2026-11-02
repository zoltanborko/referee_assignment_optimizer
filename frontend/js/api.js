let csrfToken = null;

export function updateCsrfToken(token) {
  csrfToken = token;
}

export async function api(path, options = {}) {
  const { timeoutMs, ...requestOptions } = options;
  const headers = new Headers(options.headers || {});
  const isForm = requestOptions.body instanceof FormData;
  if (requestOptions.body && !isForm && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD"].includes((options.method || "GET").toUpperCase())) {
    await getCsrfToken();
    headers.set("X-CSRF-Token", csrfToken);
  }
  const controller = timeoutMs ? new AbortController() : null;
  const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let response;
  try {
    response = await fetch(path, {
      ...requestOptions,
      headers,
      credentials: "same-origin",
      ...(controller ? { signal: controller.signal } : {}),
    });
  } catch (error) {
    if (controller?.signal.aborted) {
      throw new Error("A szerver nem válaszolt időben. Ellenőrizd, hogy fut-e a backend, majd próbáld újra.");
    }
    throw error;
  } finally {
    if (timeout) clearTimeout(timeout);
  }
  let data = {};
  try { data = await response.json(); } catch { /* Empty or non-JSON response. */ }
  if (!response.ok) {
    const error = new Error(data.error || `A kérés nem sikerült (${response.status}).`);
    error.status = response.status;
    error.payload = data;
    throw error;
  }
  if (path === "/auth/login" && data.csrf_token) csrfToken = data.csrf_token;
  return data;
}

export async function getCsrfToken() {
  const response = await fetch("/auth/csrf", {
    credentials: "same-origin",
    cache: "no-store",
  });
  let data = {};
  try { data = await response.json(); } catch { /* Invalid response. */ }
  if (!response.ok || !data.csrf_token) {
    throw new Error(data.error || "Nem sikerült biztonsági tokent kérni. Töltsd újra az oldalt.");
  }
  csrfToken = data.csrf_token;
  return csrfToken;
}

export const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[char]);

export const dateLabel = value => {
  if (!value) return "—";
  const [year, month, day] = String(value).slice(0, 10).split("-");
  return year && month && day ? `${year}.${month}.${day}.` : value;
};

export function notice(message, kind = "success") {
  if (!message) return "";
  return `<div class="notice ${kind === "error" ? "error" : kind === "warning" ? "warning" : ""}" role="status">${escapeHtml(message)}</div>`;
}

export const emptyState = message => `<div class="empty">${escapeHtml(message)}</div>`;

export function matchTable(matches, showOfficials = true) {
  if (!matches?.length) return emptyState("Ehhez a feltöltéshez még nincs mérkőzés.");
  const rows = matches.map(match => {
    const crew = [match.referee, ...(match.assistant || [])]
      .filter(Boolean)
      .map(person => person.name || person.id)
      .join(", ");
    return `<tr>
      <td>${escapeHtml(dateLabel(match.date))}</td><td>${escapeHtml(match.time || "—")}</td>
      <td>${escapeHtml(match.compname || "—")}</td>
      <td>${escapeHtml(match.home_team || "—")} – ${escapeHtml(match.away_team || "—")}</td>
      <td>${escapeHtml(match.location || "—")}</td><td>${escapeHtml(match.required_referees ?? "—")}</td>
      ${showOfficials ? `<td>${crew ? escapeHtml(crew) : '<span class="muted">Nincs kiosztva</span>'}</td>` : ""}
    </tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr><th>Dátum</th><th>Kezdés</th><th>Verseny típusa</th><th>Mérkőzés</th><th>Helyszín</th><th>Stáb</th>${showOfficials ? "<th>Játékvezetők</th>" : ""}</tr></thead><tbody>${rows}</tbody></table></div>`;
}
