import { pageHeader, card, stat } from "../ui.js";
import { escapeHtml, prettyKey } from "../format.js";

const TEAM_NAMES = { A: "Live orders", B: "Payments & refunds", C: "Order accuracy", D: "Account, app & partners" };
const FILTERS = [["all", "All"], ["customer", "Customers"], ["admin", "From the admin"]];
const SHOWN = 40;

let data = null;
let filter = "all";
let who = "";
let note = "";

export function avg(v) {
  return v == null ? "—" : Number(v).toFixed(1);
}

export function stars(rating) {
  if (rating == null) return "";
  return `<span class="fb-stars" aria-label="${rating} out of 5"><span aria-hidden="true">${"★".repeat(rating)}${"☆".repeat(5 - rating)}</span>
    <b>${rating}/5</b></span>`;
}

export function ago(iso) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

export function itemHtml(f, { showAgent = true, markNew = false } = {}) {
  const fromAdmin = f.source === "admin";
  const fresh = markNew && !f.seen_at;
  return `<li class="fb-item${fromAdmin ? " is-admin" : ""}${f.rating != null && f.rating <= 2 ? " is-low" : ""}${fresh ? " is-new" : ""}">
      <div class="fb-meta">
        ${fresh ? `<span class="pill fb-new-pill">New</span>` : ""}
        ${fromAdmin ? `<span class="pill fb-admin">From the admin</span>` : `<span class="pill">Customer · entered by hand</span>`}
        ${stars(f.rating)}
        ${showAgent ? `<span class="fb-who">${escapeHtml(f.agent_name)} · Team ${escapeHtml(f.team)}</span>` : ""}
        ${f.category ? `<span class="muted small">${escapeHtml(prettyKey(f.category))}</span>` : ""}
        <span class="muted small fb-when">${escapeHtml(ago(f.created_at))}</span>
      </div>
      <p class="fb-body">${fromAdmin ? "" : "“"}${escapeHtml(f.body)}${fromAdmin ? "" : "”"}</p>
    </li>`;
}

export function render(section) {
  section.innerHTML = `${pageHeader("Customer feedback",
    "What customers say about each agent and team, and the admin's own notes to agents. <b>Entered by hand for now:</b> the floor's customers are simulated, so their feedback is written by us. The admin's notes are marked and never count in the customer rating.")}
    <div id="fb-body"><div class="card">Loading…</div></div>`;
  section.addEventListener("click", (event) => {
    const button = event.target.closest("[data-fb-filter]");
    if (!button || !data) return;
    filter = button.dataset.fbFilter;
    drawList(section);
  });
  section.addEventListener("change", (event) => {
    if (event.target.id === "fb-who") {
      who = event.target.value;
      drawList(section);
    }
    if (event.target.name === "source") drawForm(section);
  });
  section.addEventListener("submit", (event) => {
    if (event.target.id !== "fb-form") return;
    event.preventDefault();
    send(section, event.target);
  });
  load(section);
}

async function load(section) {
  const body = section.querySelector("#fb-body");
  try {
    const r = await fetch("/api/v2/feedback", { credentials: "same-origin" });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || d.error || `server answered ${r.status}`);
    data = d;
  } catch (error) {
    body.innerHTML = card({ title: "Feedback is not available", body: `<p class="small muted">${escapeHtml(error.message)}. Feedback needs Postgres: start it, then run <code>python -m opslens.seed</code>.</p>` });
    return;
  }
  body.innerHTML = [summaryCard(data), themesCard(data),
    `<div class="fb-grid">${teamsCard(data)}${agentsCard(data)}</div>`,
    card({ id: "fb-add", title: "Add feedback", sub: "Type in what a customer said, or write your own note to an agent", body: `<div id="fb-form-box"></div>` }),
    card({ id: "fb-latest", title: "Latest feedback", body: `<div id="fb-list-box"></div>` })].join("");
  drawForm(section);
  drawList(section);
}

function summaryCard(d) {
  const c = d.customer;
  const most = Math.max(1, ...Object.values(c.by_rating));
  const bars = [5, 4, 3, 2, 1].map((s) => `<div class="mini-bar"><span>${s} ★</span>
      <div class="cbar-track"><div class="cbar-fill ${s >= 4 ? "is-good" : s <= 2 ? "is-bad" : "is-normal"}" style="width:${Math.round((100 * c.by_rating[s]) / most)}%"></div></div>
      <span class="cbar-value">${c.by_rating[s]}</span></div>`).join("");
  return card({
    title: "How customers rate the service",
    sub: `${c.count} customer reviews · admin notes are counted separately`,
    body: `<div class="stat-row">${stat("Customer rating", c.average != null ? `${avg(c.average)}<small> / 5</small>` : "—", `${c.count} reviews`)}
        ${stat("Happy", c.happy, "rated 4 or 5")}${stat("Unhappy", c.unhappy, "rated 1 or 2")}${stat("Admin notes", d.admin_notes, "not in the rating")}</div>
      <div class="finding-bars fb-bars">${bars}</div>`,
  });
}

function themesCard(d) {
  const low = (v) => v != null && v < 3;
  const rows = d.themes.map((t) => `<tr><td>${escapeHtml(t.label)}</td>
      <td class="num">${t.count}</td><td class="num${low(t.average) ? " fb-low" : ""}">${avg(t.average)}${low(t.average) ? " low" : ""}</td><td class="num">${t.unhappy}</td>
      <td class="fb-worst">${t.worst ? `${stars(t.worst.rating)} “${escapeHtml(t.worst.body)}”` : ""}</td></tr>`).join("");
  return card({
    title: "What customers bring up",
    sub: "By kind of complaint, lowest rating first",
    body: `<div class="table-wrap"><table><thead><tr><th>Complaint</th><th class="num">Reviews</th><th class="num">Rating</th>
      <th class="num">Unhappy</th><th>Lowest-rated comment</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="small muted">The low ratings line up with the recurring problems OpsLens found: wrong items from one restaurant group, Hindi
        refunds waiting too long, the payment outage and the weekend dinner rush. <a href="#problems">See the problems →</a></p>`,
  });
}

function teamsCard(d) {
  const rows = d.teams.map((t) => `<tr><td>Team ${escapeHtml(t.team)} · ${escapeHtml(t.team_name)}</td><td class="num">${t.count}</td>
      <td class="num${t.average != null && t.average < 3 ? " fb-low" : ""}">${avg(t.average)}</td><td class="num">${t.unhappy}</td></tr>`).join("");
  return card({ title: "By team", sub: "Lowest rating first",
    body: `<div class="table-wrap"><table><thead><tr><th>Team</th><th class="num">Reviews</th><th class="num">Rating</th><th class="num">Unhappy</th></tr></thead>
      <tbody>${rows}</tbody></table></div>` });
}

function agentsCard(d) {
  const rows = d.agents.map((a) => `<tr><td><button type="button" class="link-btn" data-fb-agent="${escapeHtml(a.agent_code)}">${escapeHtml(a.agent_name)}</button>
      <span class="muted small">Team ${escapeHtml(a.team)}</span></td><td class="num">${a.count}</td><td class="num">${avg(a.average)}</td></tr>`).join("");
  return card({ title: "By agent", sub: "Lowest rating first · click a name to see their feedback",
    body: `<div class="table-wrap fb-agents"><table><thead><tr><th>Agent</th><th class="num">Reviews</th><th class="num">Rating</th></tr></thead>
      <tbody>${rows}</tbody></table></div>` });
}

function agentOptions(selected) {
  return Object.keys(TEAM_NAMES).map((team) => `<optgroup label="Team ${team} · ${escapeHtml(TEAM_NAMES[team])}">
      ${data.agents_all.filter((a) => a.team === team).map((a) => `<option value="${escapeHtml(a.agent_code)}"${a.agent_code === selected ? " selected" : ""}>
        ${escapeHtml(a.name)}</option>`).join("")}</optgroup>`).join("");
}

function drawForm(section) {
  const box = section.querySelector("#fb-form-box");
  if (!box) return;
  const old = section.querySelector("#fb-form");
  const source = old ? new FormData(old).get("source") : "customer";
  const keep = old ? Object.fromEntries(new FormData(old)) : {};
  const admin = source === "admin";
  const said = note;
  note = "";
  box.innerHTML = `<form id="fb-form" class="fb-form">
      <fieldset class="fb-source"><legend class="field-label">Who it is from</legend>
        <label><input type="radio" name="source" value="customer"${admin ? "" : " checked"}> A customer</label>
        <label><input type="radio" name="source" value="admin"${admin ? " checked" : ""}> Me, the admin</label>
      </fieldset>
      <label class="field"><span class="field-label">About which agent</span><select name="agent" required>${agentOptions(keep.agent)}</select></label>
      <label class="field"><span class="field-label">Rating${admin ? " (optional)" : ""}</span>
        <select name="rating"${admin ? "" : " required"}>${admin ? `<option value="">No rating</option>` : ""}
          ${[5, 4, 3, 2, 1].map((s) => `<option value="${s}"${String(s) === keep.rating ? " selected" : ""}>${s} ★ ${["", "very unhappy", "unhappy", "okay", "happy", "very happy"][s]}</option>`).join("")}
        </select></label>
      <label class="field"><span class="field-label">Kind of complaint${admin ? " (optional)" : ""}</span>
        <select name="category"><option value="">Not about one complaint</option>
          ${data.categories.map((c) => `<option value="${escapeHtml(c)}"${c === keep.category ? " selected" : ""}>${escapeHtml(prettyKey(c))}</option>`).join("")}
        </select></label>
      <label class="field fb-text"><span class="field-label">${admin ? "Your note to the agent" : "What the customer said"}</span>
        <textarea name="body" rows="3" maxlength="1000" required placeholder="${admin ? "Good save on the late order today…" : "The agent sorted my refund quickly…"}">${escapeHtml(keep.body || "")}</textarea></label>
      <div class="btn-row"><button type="submit" class="btn btn-primary">${admin ? "Send note to the agent" : "Add customer feedback"}</button>
        <span class="small muted" id="fb-note" aria-live="polite">${escapeHtml(said)}</span></div>
      <p class="small muted">${admin ? "Marked “From the admin” everywhere and never counted in the customer rating. The agent sees it on their screen."
        : "Private details such as phone numbers are hidden before it is saved. The agent sees it on their screen, and Ask OpsLens AI can quote it."}</p>
    </form>`;
}

async function send(section, form) {
  const button = form.querySelector("button[type=submit]");
  const payload = Object.fromEntries(new FormData(form));
  button.disabled = true;
  try {
    const r = await fetch("/api/v2/feedback", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || d.error || `server answered ${r.status}`);
    note = `Added: ${d.item.source === "admin" ? "note to" : "feedback about"} ${d.item.agent_name.replace(/\.$/, "")}.`;
    await load(section);
  } catch (error) {
    section.querySelector("#fb-note").textContent = error.message;
    button.disabled = false;
  }
}

function drawList(section) {
  const box = section.querySelector("#fb-list-box");
  if (!box) return;
  const items = data.items.filter((f) => (filter === "all" || f.source === filter) && (!who || f.agent_code === who));
  const tabs = `<div class="segmented" role="group" aria-label="Show">${FILTERS.map(([k, label]) =>
    `<button type="button" data-fb-filter="${k}" aria-pressed="${k === filter}">${label}</button>`).join("")}</div>`;
  box.innerHTML = `<div class="fb-tools">${tabs}
      <label class="field fb-who-pick"><span class="field-label">Agent</span><select id="fb-who"><option value="">Everyone</option>${agentOptions(who)}</select></label></div>
    ${items.length ? `<ul class="fb-list">${items.slice(0, SHOWN).map((f) => itemHtml(f)).join("")}</ul>` : `<p class="muted">No feedback here yet.</p>`}
    ${items.length > SHOWN ? `<p class="small muted">Showing the latest ${SHOWN} of ${items.length}.</p>` : ""}`;
}

export function pickAgent(section, code) {
  who = code;
  filter = "all";
  drawList(section);
  section.querySelector("#fb-latest")?.scrollIntoView({ block: "start", behavior: "smooth" });
}

document.addEventListener("click", (event) => {
  const b = event.target.closest("[data-fb-agent]");
  if (b) pickAgent(b.closest(".view"), b.dataset.fbAgent);
});
