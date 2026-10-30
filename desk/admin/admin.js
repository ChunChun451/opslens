import {
  $, api, signedIn, logout, initials, esc, agentPill, ticketTable, ticketDetail, onFloorChange, toast,
  CATEGORY, TEAM, prio, riskPill, runAgent, traceList, stepText, seconds, AGENT_NAME, ago, clock, pill,
} from "/desk/desk.js";

const PAGES = { overview: "Overview", tickets: "Tickets", team: "Team", ai: "AI activity" };
const RUN_STATUS = { running: ["Running", "blue"], done: ["Done", "green"], failed: ["Failed", "red"], needs_approval: ["Needs a decision", "amber"] };
const TICKET_VIEWS = [
  { key: "open", label: "All open" },
  { key: "unassigned", label: "Waiting for an agent" },
  { key: "due_soon", label: "Due in 15 minutes" },
  { key: "at_risk", label: "Likely to miss" },
  { key: "solved", label: "Solved today" },
];
const POLICY = { opslens: "OpsLens", baseline_d: "Usual routing" };
const state = { user: null, page: "overview", view: "open", team: "", ticket: null, run: null, chart: null, asking: false };

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  state.page = PAGES[h.get("p")] ? h.get("p") : "overview";
  state.view = TICKET_VIEWS.some(v => v.key === h.get("view")) ? h.get("view") : "open";
  state.team = h.get("team") || "";
  state.ticket = h.get("t");
  state.run = h.get("run");
}

function go(params) {
  const next = { p: state.page, view: state.view, team: state.team, ...params };
  const h = new URLSearchParams();
  for (const [k, v] of Object.entries(next)) if (v) h.set(k, v);
  location.hash = h.toString();
}

function tile(label, value, note = "", tone = "") {
  return `<div class="card tile ${tone}"><div class="label">${esc(label)}</div><div class="value">${value ?? "—"}</div><div class="note">${esc(note)}</div></div>`;
}

async function overview() {
  const [sum, floor] = await Promise.all([api("/api/v2/summary"), api("/api/v2/floor").catch(() => null)]);
  const t = sum.today;
  const main = $("#main");
  const compare = floor ? floor.compare : null;
  const ours = compare?.opslens, usual = compare?.baseline_d;
  const peopleByTeam = Object.fromEntries((floor?.teams || []).map(x => [x.team, x]));
  const keepAsk = $("#askbox");
  main.innerHTML = `<div class="page stack">
    <div class="card" id="askslot"></div>
    <div class="tiles">
      ${tile("Tickets today", t.arrived, `${t.solved} solved`)}
      ${tile("Waiting for an agent", t.unassigned, "not picked up yet", t.unassigned > 5 ? "bad" : "")}
      ${tile("Being worked", t.in_progress, "with an agent now")}
      ${tile("Likely to miss", t.at_risk, "open, 50%+ chance of missing", t.at_risk > 0 ? "bad" : "")}
      ${tile("Promises missed", t.breached_pct === null ? "—" : `${t.breached_pct}%`, `${t.breached} of ${t.arrived} today`, t.breached_pct > 15 ? "bad" : t.breached_pct !== null ? "good" : "")}
    </div>
    <div class="cols">
      <div class="stack">
        <div class="card"><div class="head"><h2>Needs attention now</h2><span class="muted" style="font-size:12px">Open tickets most likely to miss their promise</span></div>
          <div id="danger"></div></div>
        <div class="card"><div class="head"><h2>Tickets per hour</h2><span class="muted" style="font-size:12px">Today${state.user.role === "lead" ? ", your team" : ""}</span></div>
          <div class="body" style="height:230px"><canvas id="hourly" aria-label="Tickets that arrived each hour today"></canvas></div></div>
      </div>
      <div class="stack">
        ${ours && usual ? `<div class="card"><div class="head"><h2>Missed promises so far</h2><span class="muted" style="font-size:12px">Whole floor, same tickets</span></div><div class="body">
          ${[["opslens", ours], ["baseline_d", usual]].map(([k, p]) => {
            const most = Math.max(ours.missed, usual.missed, 1);
            return `<div style="margin-bottom:12px"><div style="display:flex;justify-content:space-between;font-size:13px"><span>${POLICY[k]}</span><b class="num">${p.missed} missed</b></div>
              <div class="bar" style="margin-top:4px"><span style="width:${100 * p.missed / most}%;background:${k === "opslens" ? "var(--accent)" : "var(--ink-3)"}"></span></div></div>`;
          }).join("")}
          <div class="muted" style="font-size:12px">The usual way is replayed on the same tickets and staff, so the gap is what OpsLens's routing changed.</div></div></div>` : ""}
        <div class="card" id="suggest"></div>
        <div class="card"><div class="head"><h2>Teams</h2></div>
          <table class="grid"><thead><tr><th>Team</th><th class="right">Open</th><th class="right">Likely to miss</th><th class="right">Missed</th><th class="right">Free / working</th></tr></thead><tbody>
          ${sum.teams.map(x => {
            const p = peopleByTeam[x.team];
            return `<tr class="row" data-team="${esc(x.team)}"><td>${esc(x.name || TEAM[x.team] || x.team)}</td><td class="right num">${x.open}</td>
              <td class="right num">${x.at_risk ? `<span class="pill red">${x.at_risk}</span>` : 0}</td><td class="right num">${x.breached}</td>
              <td class="right num">${p ? `${p.free} / ${p.working}` : "—"}</td></tr>`;
          }).join("")}</tbody></table></div>
      </div>
    </div></div>`;
  main.querySelectorAll("tr[data-team]").forEach(r => r.onclick = () => go({ p: "tickets", view: "open", team: r.dataset.team, t: "" }));
  const danger = floor?.danger || [];
  $("#danger").innerHTML = danger.length ? `<table class="grid"><thead><tr><th>Priority</th><th>Ticket</th><th>Left</th><th>Chance of missing</th></tr></thead><tbody>
    ${danger.map(d => `<tr class="row" data-id="${esc(d.ticket_id)}"><td>${prio(d.priority)}</td>
      <td><div class="subject">${esc(CATEGORY[d.category] || d.category)} · ${esc(d.ticket_id)}</div><div class="muted" style="font-size:12px">${esc((d.reasons || [])[0] || "")}${d.nobody_capable ? " · nobody on shift has this skill" : ""}</div></td>
      <td class="num">${Math.round(d.minutes_left)} min</td>
      <td>${riskPill(d.probability)}<div class="muted" style="font-size:12px;margin-top:2px">${Math.round(d.if_served_now * 100)}% if served now</div></td></tr>`).join("")}
    </tbody></table>` : `<div class="empty">Nothing is in danger right now.</div>`;
  $("#danger").querySelectorAll("tr.row").forEach(r => r.onclick = () => go({ p: "tickets", t: r.dataset.id }));
  drawHourly(sum.hourly);
  if (keepAsk) $("#askslot").replaceWith(keepAsk);
  else { $("#askslot").id = "askbox"; askBox($("#askbox")); }
  await suggestions();
}

function askBox(box) {
  box.innerHTML = `<div class="body"><form class="ask" id="askform"><input name="q" maxlength="300" autocomplete="off"
      placeholder="Ask OpsLens about the floor, e.g. Which team is most at risk right now?"><button class="btn primary">Ask</button></form>
      <div id="askout"></div></div>`;
  $("#askform").onsubmit = async event => {
    event.preventDefault();
    const question = new FormData(event.target).get("q").trim();
    if (!question || state.asking) return;
    state.asking = true;
    const out = $("#askout");
    out.innerHTML = `<div class="answer-box"><div class="muted">Thinking on the local model…</div></div>`;
    try {
      const done = await runAgent("/api/v2/ask", { question }, d => {
        out.innerHTML = `<div class="answer-box"><div class="muted">Thinking on the local model…</div>${traceList(d.steps)}</div>`;
      });
      out.innerHTML = `<div class="answer-box"><div>${esc(done.run.output?.text || done.run.summary || "No answer.")}</div>
        <div class="muted" style="font-size:12px;margin-top:6px">${done.run.output?.unverified?.length ? pill("Some numbers are not in the live data", "amber") : pill("Every number is in the live data", "green")}
        ${seconds(done.run)} · <a href="#p=ai&run=${done.run.id}">See how OpsLens worked it out</a></div></div>`;
    } catch (e) {
      out.innerHTML = `<div class="answer-box">${esc(e.message)}</div>`;
    }
    state.asking = false;
  };
}

async function suggestions() {
  const box = $("#suggest");
  if (!box) return;
  const { proposals } = await api("/api/v2/proposals").catch(() => ({ proposals: [] }));
  box.innerHTML = `<div class="head"><h2>OpsLens suggests</h2><button class="btn small" id="checknow">Check the floor now</button></div>
    ${proposals.length ? proposals.map(p => `<div class="proposal"><div>
        <div class="t">${esc(p.title)}</div><div class="w">${esc(p.why || "")}</div>
        <div class="muted" style="font-size:12px;margin-top:2px">${p.kind === "reassign" ? "Approving gives the ticket to this agent now" : "A note for a lead"} · ${ago(p.created_at)}</div></div>
        <div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn small primary" data-approve="${p.id}">${p.kind === "reassign" ? "Approve" : "Got it"}</button>
        <button class="btn small ghost" data-reject="${p.id}">Dismiss</button></div></div>`).join("")
      : `<div class="empty" style="padding:24px">No suggestions waiting. The floor analyst checks every 15 minutes.</div>`}`;
  box.querySelectorAll("[data-approve],[data-reject]").forEach(b => b.onclick = async () => {
    const id = b.dataset.approve || b.dataset.reject;
    b.disabled = true;
    try {
      const out = await api(`/api/v2/proposals/${id}`, { body: { decision: b.dataset.approve ? "approve" : "reject" } });
      const said = { approved: "Done.", rejected: "Dismissed.", expired: out.result?.error, failed: `That did not work: ${out.result?.error || ""}` };
      toast(said[out.status] || out.status, out.status === "failed");
    } catch (e) { toast(e.message, true); }
    await suggestions();
  });
  $("#checknow").onclick = async () => {
    const button = $("#checknow");
    button.disabled = true;
    button.textContent = "Checking…";
    try {
      const done = await runAgent("/api/v2/analyst", {}, () => {});
      toast(done.run.summary || "Checked.");
    } catch (e) { toast(e.message, true); }
    await suggestions();
  };
}

async function ai() {
  const main = $("#main");
  if (state.run) {
    let data;
    try { data = await api(`/api/v2/runs/${encodeURIComponent(state.run)}`); }
    catch (e) { main.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const r = data.run;
    const [label, color] = RUN_STATUS[r.status] || [r.status, "grey"];
    main.innerHTML = `<div class="page stack">
      <div><button class="btn small ghost" id="back">← Back to AI activity</button></div>
      <div class="card"><div class="head"><div><h2>${esc(AGENT_NAME[r.agent] || r.agent)} · run ${r.id}</h2>
        <div class="muted" style="font-size:12px">${esc(r.trigger)} · ${clock(r.started_at)} · ${seconds(r)}${r.ticket_id ? ` · <a href="#p=tickets&t=${encodeURIComponent(r.ticket_id)}">${esc(r.ticket_id)}</a>` : ""}</div></div>${pill(label, color)}</div>
        <div class="body"><div style="font-weight:600">${esc(r.summary || "")}</div></div></div>
      <div class="card"><div class="head"><h2>Every step</h2><span class="muted hide-sm" style="font-size:12px">What the agent asked for, what the tools returned, what it decided</span></div>
        <table class="grid"><thead><tr><th>#</th><th>Step</th><th>Details</th></tr></thead><tbody>
        ${data.steps.map(s => `<tr><td class="num">${s.n}</td><td>${esc(stepText(s))}</td>
          <td><details><summary class="muted" style="cursor:pointer">${esc(s.kind.replace("_", " "))}</summary><pre style="white-space:pre-wrap;font-size:12px;max-height:280px;overflow:auto">${esc(JSON.stringify(s.payload, null, 2))}</pre></details></td></tr>`).join("")}
        </tbody></table></div></div>`;
    $("#back").onclick = () => go({ run: "" });
    return;
  }
  const { runs, last_day } = await api("/api/v2/runs?limit=60");
  const by = Object.fromEntries(last_day.map(d => [d.agent, d]));
  main.innerHTML = `<div class="page stack">
    <div class="tiles">${["intake", "copilot", "analyst", "ask"].map(a => {
      const d = by[a];
      return tile(AGENT_NAME[a], d ? d.runs : 0, d ? `last 24 h · ${d.avg_seconds ?? "—"} s each · ${d.failed} failed` : "no runs in the last 24 h");
    }).join("")}</div>
    <div class="card"><div class="head"><h2>Recent runs</h2><span class="muted hide-sm" style="font-size:12px">All on the local model. The optimiser still decides who gets each ticket.</span></div>
    ${runs.length ? `<table class="grid"><thead><tr><th>Agent</th><th>What happened</th><th>Status</th><th class="right hide-sm">Tools</th><th class="right">When</th></tr></thead><tbody>
    ${runs.map(r => {
      const [label, color] = RUN_STATUS[r.status] || [r.status, "grey"];
      return `<tr class="row" data-run="${r.id}"><td style="white-space:nowrap">${esc(AGENT_NAME[r.agent] || r.agent)}</td>
        <td><div class="subject">${esc(r.summary || r.trigger)}</div><div class="muted" style="font-size:12px">${esc(r.trigger)}${r.ticket_id ? ` · ${esc(r.ticket_id)}` : ""}</div></td>
        <td>${pill(label, color)}</td><td class="right num hide-sm">${r.tools_used}</td><td class="right muted" style="white-space:nowrap">${ago(r.started_at)}</td></tr>`;
    }).join("")}</tbody></table>` : `<div class="empty">No AI runs yet.</div>`}</div></div>`;
  main.querySelectorAll("tr[data-run]").forEach(r => r.onclick = () => go({ run: r.dataset.run }));
}

function drawHourly(hourly) {
  const byHour = new Map();
  for (const h of hourly) {
    const key = new Date(h.hour).getHours();
    const cur = byHour.get(key) || { created: 0, breached: 0 };
    cur.created += h.created;
    cur.breached += h.breached;
    byHour.set(key, cur);
  }
  const hours = [...byHour.keys()].sort((a, b) => a - b);
  const canvas = $("#hourly");
  if (!canvas || !window.Chart) return;
  state.chart?.destroy();
  const css = getComputedStyle(document.documentElement);
  state.chart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: hours.map(h => `${String(h).padStart(2, "0")}:00`),
      datasets: [{ label: "Tickets arrived", data: hours.map(h => byHour.get(h).created), backgroundColor: css.getPropertyValue("--accent").trim(),
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "bottom", maxBarThickness: 22 }],
    },
    options: {
      maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: c => `${byHour.get(hours[c.dataIndex]).breached} missed their promise` } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: css.getPropertyValue("--ink-3").trim() } },
        y: { beginAtZero: true, grid: { color: css.getPropertyValue("--line").trim() }, border: { display: false }, ticks: { color: css.getPropertyValue("--ink-3").trim(), precision: 0 } },
      },
    },
  });
}

async function tickets() {
  const main = $("#main");
  if (state.ticket) {
    let data;
    try { data = await api(`/api/v2/tickets/${encodeURIComponent(state.ticket)}`); }
    catch (e) { main.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    main.innerHTML = `<div style="display:flex;flex-direction:column;height:100%"><div style="padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel)"><button class="btn small ghost" id="back">← Back to tickets</button></div>
      <div style="flex:1;min-height:0">${ticketDetail(data, { user: state.user, extraActions: `<span class="muted">Agents act on tickets from their workspace. OpsLens keeps routing on its own.</span>` })}</div></div>`;
    $("#back").onclick = () => go({ t: "" });
    return;
  }
  const team = state.user.role === "admin" ? state.team : "";
  const counts = await Promise.all(TICKET_VIEWS.map(v => api(`/api/v2/tickets?view=${v.key}&limit=500${team ? `&team=${team}` : ""}`).catch(() => ({ tickets: [] }))));
  const pick = TICKET_VIEWS.findIndex(v => v.key === state.view);
  const list = counts[pick].tickets;
  main.innerHTML = `<div class="split">
    <div class="views"><h3>Views</h3>${TICKET_VIEWS.map((v, i) => `<button data-view="${v.key}" class="${v.key === state.view ? "on" : ""}"><span>${esc(v.label)}</span><span class="count">${counts[i].tickets.length}</span></button>`).join("")}
      ${state.user.role === "admin" ? `<hr><h3>Team</h3><button data-team="" class="${!team ? "on" : ""}"><span>All teams</span></button>${Object.entries(TEAM).map(([k, n]) => `<button data-team="${k}" class="${team === k ? "on" : ""}"><span>${esc(n)}</span></button>`).join("")}` : ""}
    </div>
    <div class="list"><div style="padding:14px 16px;display:flex;justify-content:space-between;background:var(--panel);border-bottom:1px solid var(--line)"><h2>${esc(TICKET_VIEWS[pick].label)}${team ? ` · ${esc(TEAM[team])}` : ""}</h2><span class="muted num">${list.length} tickets</span></div>
      ${ticketTable(list, { emptyText: "No tickets in this view." })}</div></div>`;
  main.querySelectorAll("[data-view]").forEach(b => b.onclick = () => go({ view: b.dataset.view }));
  main.querySelectorAll("[data-team]").forEach(b => b.onclick = () => go({ team: b.dataset.team }));
  main.querySelectorAll("tr.row").forEach(r => r.onclick = () => go({ t: r.dataset.id }));
}

async function team() {
  const main = $("#main");
  let floor;
  try { floor = await api("/api/v2/floor"); }
  catch (e) { main.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const people = [...floor.people].sort((a, b) => (a.status === "off") - (b.status === "off")
    || (a.team || "").localeCompare(b.team || "") || a.id.localeCompare(b.id));
  const onShift = people.filter(p => p.status !== "off").length;
  main.innerHTML = `<div class="page stack">
    <div class="tiles">
      ${tile("On shift now", onShift, `of ${people.length} people`)}
      ${tile("Free", people.filter(p => p.status === "idle").length, "ready for the next ticket")}
      ${tile("Working", people.filter(p => ["busy", "cross", "wrong"].includes(p.status)).length, "on a ticket")}
      ${tile("On break", people.filter(p => p.status === "break").length)}
    </div>
    <div class="card"><div class="head"><h2>People</h2><span class="muted" style="font-size:12px">Updates as the floor changes</span></div>
    <table class="grid"><thead><tr><th>Agent</th><th class="hide-sm">Team</th><th>Status</th><th>Working on</th><th class="right">Solved</th><th class="right hide-sm">On time</th><th class="right hide-sm">Helped other teams</th></tr></thead><tbody>
    ${people.map(p => `<tr>
      <td><div style="display:flex;gap:10px;align-items:center"><div class="avatar">${esc(initials(p.name))}</div><div><div style="font-weight:600">${esc(p.name || p.id)}</div><div class="muted" style="font-size:12px">${esc(p.id)}</div></div></div></td>
      <td class="hide-sm">${esc(TEAM[p.team] || p.team || "")}</td>
      <td>${agentPill(p.status)}</td>
      <td>${p.current ? `<a href="#p=tickets&t=${encodeURIComponent(p.current.ticket_id)}">${esc(p.current.ticket_id)}</a> <span class="muted">· ${esc(CATEGORY[p.current.category] || p.current.category)} · ${p.current.minutes_left < 0 ? `${Math.round(-p.current.minutes_left)} min late` : `${Math.round(p.current.minutes_left)} min left`}</span>` : `<span class="muted">—</span>`}</td>
      <td class="right num">${p.done}</td><td class="right num hide-sm">${p.done ? `${Math.round(100 * p.kept / p.done)}%` : "—"}</td><td class="right num hide-sm">${p.rescues}</td></tr>`).join("")}
    </tbody></table></div></div>`;
}

async function render() {
  readHash();
  $("#title").textContent = PAGES[state.page];
  document.querySelectorAll("#rail [data-page]").forEach(b => b.classList.toggle("on", b.dataset.page === state.page));
  try {
    await ({ overview, tickets, team, ai })[state.page]();
    $("#updated").textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
  } catch (e) {
    toast(e.message, true);
  }
}

state.user = await signedIn(["admin", "lead"]);
$("#avatar").textContent = initials(state.user.name);
$("#myname").textContent = state.user.name;
$("#myrole").textContent = state.user.role === "admin" ? "Admin · all teams" : `Team lead · ${TEAM[state.user.team] || state.user.team}`;
$("#scope").textContent = state.user.role === "admin" ? "All teams" : TEAM[state.user.team] || "";
document.querySelectorAll("#rail [data-page]").forEach(b => b.onclick = () => { state.page = b.dataset.page; go({ p: b.dataset.page, t: "", run: "" }); });
document.querySelector("#rail [data-href]").onclick = () => { location.href = "/app/"; };
$("#logout").onclick = logout;
window.addEventListener("hashchange", render);
await render();
onFloorChange(() => { if (!state.ticket && !state.run && !state.asking && !document.activeElement?.closest?.("#askform")) render(); });
