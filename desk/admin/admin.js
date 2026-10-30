import {
  $, $$, api, signedIn, createShell, route, ticketTable, ticketPage, onFloorChange, tickDue, toast, store, esc, icon, tag,
  prio, agentTag, riskTag, dueText, fmtMin, signed, ago, clock, initials, runAgent, traceList, stepText, seconds, dialog,
  CATEGORY, TEAM, LANGUAGE, AGENT_NAME,
} from "/desk/desk.js";

const VIEWS = [
  { key: "open", label: "All unsolved" },
  { key: "unassigned", label: "Unassigned" },
  { key: "due_soon", label: "Due in 15 minutes" },
  { key: "at_risk", label: "Likely to miss" },
  { key: "solved", label: "Solved today" },
];
const CAUSE = { skill_gap: ["Skill gap", "amber"], process: ["Process", "blue"], capacity: ["Capacity", "red"],
                volume_spike: ["Volume spike", "ai"], partner_issue: ["Restaurant partner", "green"], other: ["Other", ""] };
const RUN_STATUS = { running: ["Running", "blue"], done: ["Done", "green"], failed: ["Failed", "red"], needs_approval: ["Needs a decision", "amber"] };

const user = await signedIn("admin");
const state = { counts: {}, sort: store(`opslens.sort.${user.id}`) || {}, team: store(`opslens.team.${user.id}`) || "",
                problems: null, chart: null, asking: false, simulating: false };
const shell = createShell({
  user, homeTitle: "Home",
  nav: [
    { key: "home", label: "Home", icon: "home" }, { key: "views", label: "Views", icon: "views" },
    { key: "problems", label: "Recurring problems", icon: "problems" }, { key: "plan", label: "Plan and impact", icon: "plan" },
    { key: "team", label: "Team", icon: "team" }, { key: "analysis", label: "Analysis", icon: "analysis" },
    { key: "ai", label: "AI activity", icon: "ai", bottom: true },
  ],
  shortcuts: [{ key: "a", label: "Ask OpsLens (on Home)", run: () => { location.hash = "#/home"; setTimeout(() => $("#askq")?.focus(), 300); } }],
});

const go = h => { location.hash = h; };
const tile = (label, value, note = "", tone = "", href = "") =>
  `<${href ? `a href="${href}"` : "div"} class="card tile ${tone} ${href ? "link" : ""}" style="color:inherit;text-decoration:none"><div class="label">${esc(label)}</div><div class="value">${value ?? "—"}</div><div class="note">${note}</div></${href ? "a" : "div"}>`;

async function problemsData(force = false) {
  if (!state.problems || force) state.problems = await api("/api/v2/problems");
  return state.problems;
}

function impactText(e, compact = false) {
  const cls = e.certain ? "good" : e.worse ? "bad" : "meh";
  const word = e.missed <= 0 ? "fewer" : "more";
  return compact ? `<span class="impact ${cls}" style="font-size:15px">${signed(e.missed)}</span>`
    : `<div class="impact ${cls}">${Math.abs(e.missed).toLocaleString()} ${word}</div><div class="small muted">missed promises over 14 days · 95% range ${signed(e.missed_low)} to ${signed(e.missed_high)}</div>`;
}

async function loadCounts() {
  state.counts = await api("/api/v2/counts").catch(() => ({}));
  shell.setBadge("views", state.counts.unassigned || 0);
  const waiting = await api("/api/v2/proposals").catch(() => ({ proposals: [] }));
  shell.setBadge("home", waiting.proposals.length);
  state.proposals = waiting.proposals;
}

async function home() {
  shell.setTitle("Home");
  const keepAsk = $("#askbox");
  const [sum, floor, probs] = await Promise.all([api("/api/v2/summary"), api("/api/v2/floor").catch(() => null), problemsData().catch(() => null)]);
  const t = sum.today;
  const ours = floor?.compare?.S2 || floor?.compare?.opslens, usual = floor?.compare?.baseline_d;
  const people = Object.fromEntries((floor?.teams || []).map(x => [x.team, x]));
  const free = (floor?.teams || []).reduce((n, x) => n + x.free, 0), working = (floor?.teams || []).reduce((n, x) => n + x.working, 0);
  const top = probs ? [...probs.cards].map(c => ({ c, best: c.fixes.map(id => probs.fixes.find(f => f.id === id)).sort((a, b) => a.effect.missed - b.effect.missed)[0] }))
    .filter(x => x.best).sort((a, b) => a.best.effect.missed - b.best.effect.missed).slice(0, 3) : [];
  shell.main.innerHTML = `<div class="page stack">
    <div class="page-head"><div><h1>Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}</h1>
      <p>The floor right now, what needs you, and what to fix for good.</p></div>
      <div style="display:flex;gap:8px"><a class="btn quiet" href="#/views/unassigned">Unassigned (${t.unassigned})</a><a class="btn primary" href="#/problems">See recurring problems</a></div></div>
    <div class="card" id="askslot"></div>
    <div class="tiles">
      ${tile("Tickets today", t.arrived, `${t.solved} solved`, "", "#/views/solved")}
      ${tile("Unassigned", t.unassigned, "waiting for an agent", t.unassigned > 5 ? "bad" : "", "#/views/unassigned")}
      ${tile("Being worked", t.in_progress, `${working} agents busy · ${free} free`, "", "#/team")}
      ${tile("Likely to miss", t.at_risk, "50%+ chance of missing", t.at_risk > 0 ? "bad" : "", "#/views/at_risk")}
      ${tile("Promises missed", t.breached_pct === null ? "—" : `${t.breached_pct}%`, `${t.breached} of ${t.arrived} today`, t.breached_pct > 15 ? "bad" : t.breached_pct !== null ? "good" : "")}
      ${tile("Average wait", t.avg_wait_min === null ? "—" : `${t.avg_wait_min}<span class="small muted"> min</span>`, "before an agent picks it up")}
    </div>
    <div class="cols">
      <div class="stack">
        <div class="card"><div class="head"><h2>Needs attention now</h2><span class="small muted">Open tickets most likely to miss their promise</span></div><div id="danger"></div></div>
        <div class="card"><div class="head"><h2>Recurring problems worth fixing</h2><a class="small" href="#/problems">All ${probs ? probs.cards.length : ""} problems</a></div>
          ${top.length ? top.map(({ c, best }) => `<div class="proposal" style="cursor:pointer" data-prob="${esc(c.id)}"><div>
            <div class="t">${esc(c.title)}</div><div class="w">Fix: ${esc(best.title)} <span class="faint">· ${esc(best.owner || "")}</span></div></div>
            <div style="text-align:right">${impactText(best.effect, true)}<div class="small muted">missed promises / 14 days</div></div></div>`).join("") : `<div class="empty">Loading…</div>`}
          ${probs ? `<div class="foot small muted">All ${probs.fixes.length} fixes together: <b>${signed(probs.all.missed)}</b> missed promises (${probs.all.without_pct}% → ${probs.all.with_pct}%), replayed on 14 held-out days.</div>` : ""}</div>
        <div class="card"><div class="head"><h2>Tickets per hour</h2><span class="small muted">Today</span></div><div class="body" style="height:220px"><canvas id="hourly" aria-label="Tickets that arrived each hour today"></canvas></div></div>
      </div>
      <div class="stack">
        <div class="card" id="suggest"></div>
        ${ours && usual ? `<div class="card"><div class="head"><h2>OpsLens against usual routing</h2><span class="small muted">Same tickets, same people, today</span></div><div class="body">
          ${[["OpsLens", ours, "var(--blue)"], ["Usual skills routing", usual, "var(--ink-4)"]].map(([n, p, c]) => {
            const most = Math.max(ours.missed, usual.missed, 1);
            return `<div style="margin-bottom:12px"><div style="display:flex;justify-content:space-between;font-size:13px"><span>${n}</span><b class="num">${p.missed} missed</b></div>
              <div class="bar" style="margin-top:4px"><span style="width:${100 * p.missed / most}%;background:${c}"></span></div></div>`;
          }).join("")}
          <div class="small muted">${usual.missed - ours.missed > 0 ? `<b style="color:var(--green)">${usual.missed - ours.missed} customers</b> kept their promise today because of OpsLens's routing.` : "Usual routing is replayed on the same tickets and staff."}</div></div></div>` : ""}
        <div class="card"><div class="head"><h2>Teams</h2><a class="small" href="#/team">Team</a></div>
          <table class="grid"><thead><tr><th>Team</th><th class="right">Open</th><th class="right">Likely to miss</th><th class="right">Missed</th><th class="right">Free / busy</th></tr></thead><tbody>
          ${sum.teams.map(x => {
            const p = people[x.team];
            return `<tr class="row" data-team="${esc(x.team)}"><td><b>${esc(x.name || TEAM[x.team])}</b><div class="sub">Team ${esc(x.team)}</div></td><td class="right num">${x.open}</td>
              <td class="right num">${x.at_risk ? tag(x.at_risk, "red") : 0}</td><td class="right num">${x.breached}</td><td class="right num">${p ? `${p.free} / ${p.working}` : "—"}</td></tr>`;
          }).join("")}</tbody></table></div>
      </div>
    </div></div>`;
  if (keepAsk) $("#askslot").replaceWith(keepAsk);
  else { $("#askslot").id = "askbox"; askBox($("#askbox")); }
  $$("[data-team]").forEach(r => r.onclick = () => { state.team = r.dataset.team; store(`opslens.team.${user.id}`, state.team); go("#/views/open"); });
  $$("[data-prob]").forEach(r => r.onclick = () => go(`#/problems/${r.dataset.prob}`));
  const danger = floor?.danger || [];
  $("#danger").innerHTML = danger.length ? `<table class="grid"><thead><tr><th>Priority</th><th>Ticket</th><th>Left</th><th>Chance of missing</th></tr></thead><tbody>
    ${danger.map(d => `<tr class="row" data-id="${esc(d.ticket_id)}"><td>${prio(d.priority)}</td>
      <td><div class="subject">${esc(CATEGORY[d.category] || d.category)} · #${esc(d.ticket_id)}</div><div class="sub">${esc((d.reasons || [])[0] || "")}${d.nobody_capable ? " · nobody on shift has this skill" : ""}</div></td>
      <td class="num nowrap">${Math.round(d.minutes_left)} min</td><td>${riskTag(d.probability)}<div class="sub">${Math.round(d.if_served_now * 100)}% if served now</div></td></tr>`).join("")}
    </tbody></table>` : `<div class="empty">${icon("inbox", 40)}Nothing is in danger right now.</div>`;
  $$("#danger tr.row").forEach(r => r.onclick = () => go(`#/t/${r.dataset.id}`));
  drawHourly(sum.hourly);
  suggestions();
}

function drawHourly(hourly) {
  const byHour = new Map();
  for (const h of hourly) {
    const k = new Date(h.hour).getHours();
    const cur = byHour.get(k) || { created: 0, breached: 0 };
    cur.created += h.created;
    cur.breached += h.breached;
    byHour.set(k, cur);
  }
  const hours = [...byHour.keys()].sort((a, b) => a - b);
  const canvas = $("#hourly");
  if (!canvas || !window.Chart) return;
  state.chart?.destroy();
  const css = getComputedStyle(document.documentElement);
  state.chart = new Chart(canvas, {
    type: "bar",
    data: { labels: hours.map(h => `${String(h).padStart(2, "0")}:00`),
            datasets: [{ label: "Tickets arrived", data: hours.map(h => byHour.get(h).created), backgroundColor: css.getPropertyValue("--blue").trim(),
                         borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "bottom", maxBarThickness: 22 }] },
    options: { maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: c => `${byHour.get(hours[c.dataIndex]).breached} missed their promise` } } },
      scales: { x: { grid: { display: false }, ticks: { color: css.getPropertyValue("--ink-3").trim() } },
                y: { beginAtZero: true, grid: { color: css.getPropertyValue("--line-soft").trim() }, border: { display: false }, ticks: { color: css.getPropertyValue("--ink-3").trim(), precision: 0 } } } },
  });
}

function askBox(box) {
  const examples = ["Which team has missed the most promises today?", "Is anything overdue right now?", "When was the busiest hour today?"];
  box.innerHTML = `<div class="body"><form class="ask" id="askform"><input class="field" id="askq" name="q" maxlength="300" autocomplete="off"
      placeholder="Ask OpsLens about the floor…"><button class="btn primary">${icon("sparkle", 14)} Ask</button></form>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">${examples.map(x => `<button class="btn quiet small" type="button" data-ex="${esc(x)}">${esc(x)}</button>`).join("")}</div>
      <div id="askout"></div></div>`;
  const ask = async question => {
    if (!question || state.asking) return;
    state.asking = true;
    const out = $("#askout");
    out.innerHTML = `<div class="answer-box"><div class="muted">Thinking on the local model…</div></div>`;
    try {
      const done = await runAgent("/api/v2/ask", { question }, d => {
        out.innerHTML = `<div class="answer-box"><div class="muted">Thinking on the local model…</div>${traceList(d.steps)}</div>`;
      });
      const o = done.run.output || {};
      out.innerHTML = `<div class="answer-box"><div style="font-size:15px">${esc(o.text || done.run.summary || "No answer.")}</div>
        <div class="small muted" style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">${o.unverified?.length ? tag("Some numbers are not in the live data", "amber") : tag("Every number is in the live data", "green")}
        <span>${seconds(done.run)} on this laptop</span><a href="#/ai/${done.run.id}">See how it worked it out</a></div></div>`;
    } catch (e) {
      out.innerHTML = `<div class="answer-box">${esc(e.message)}</div>`;
    }
    state.asking = false;
  };
  $("#askform").onsubmit = e => { e.preventDefault(); ask($("#askq").value.trim()); };
  $$("[data-ex]", box).forEach(b => b.onclick = () => { $("#askq").value = b.dataset.ex; ask(b.dataset.ex); });
}

async function suggestions() {
  const box = $("#suggest");
  if (!box) return;
  const proposals = state.proposals || (await api("/api/v2/proposals").catch(() => ({ proposals: [] }))).proposals;
  box.innerHTML = `<div class="head"><h2>${icon("sparkle", 14)} OpsLens suggests</h2><button class="btn quiet small" id="checknow">Check the floor now</button></div>
    ${proposals.length ? proposals.map(p => `<div class="proposal"><div>
        <div class="t">${p.ticket_id ? `<a href="#/t/${esc(p.ticket_id)}">${esc(p.title)}</a>` : esc(p.title)}</div><div class="w">${esc(p.why || "")}</div>
        <div class="small faint" style="margin-top:2px">${p.kind === "reassign" ? "Approving hands the ticket to this agent now" : "A note for you"} · ${ago(p.created_at)}</div></div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end"><button class="btn primary small" data-approve="${p.id}">${p.kind === "reassign" ? "Approve" : "Got it"}</button>
        <button class="btn quiet small" data-reject="${p.id}">Dismiss</button></div></div>`).join("")
      : `<div class="empty" style="padding:24px">No suggestions waiting. The floor analyst checks every 15 minutes.</div>`}`;
  $$("[data-approve],[data-reject]", box).forEach(b => b.onclick = async () => {
    const id = b.dataset.approve || b.dataset.reject;
    b.disabled = true;
    try {
      const out = await api(`/api/v2/proposals/${id}`, { body: { decision: b.dataset.approve ? "approve" : "reject" } });
      const said = { approved: "Done. OpsLens re-planned the floor.", rejected: "Dismissed.", expired: out.result?.error, failed: `That did not work: ${out.result?.error || ""}` };
      toast(said[out.status] || out.status, out.status === "approved" ? "good" : out.status === "failed");
    } catch (e) { toast(e.message, true); }
    state.proposals = null;
    await loadCounts();
    suggestions();
  });
  $("#checknow").onclick = async () => {
    const button = $("#checknow");
    button.disabled = true;
    button.textContent = "Checking…";
    try {
      const done = await runAgent("/api/v2/analyst", {}, () => {});
      toast(done.run.summary || "Checked.", "good");
    } catch (e) { toast(e.message, true); }
    state.proposals = null;
    await loadCounts();
    suggestions();
  };
}

async function views(key) {
  const v = VIEWS.find(x => x.key === key) || VIEWS[0];
  store(`opslens.lastview.${user.id}`, `#/views/${v.key}`);
  shell.setTitle("Views");
  const sort = state.sort[v.key] || "";
  const prevScroll = $(".listing")?.scrollTop || 0;
  const data = await api(`/api/v2/tickets?view=${v.key}&limit=300${state.team ? `&team=${state.team}` : ""}${sort ? `&sort=${sort}` : ""}`).catch(() => ({ tickets: [] }));
  shell.main.innerHTML = `<div class="split">
    <div class="side-list"><h3>Views <button class="btn quiet small" id="re" title="Refresh">${icon("refresh", 14)}</button></h3>
      ${VIEWS.map(x => `<button data-view="${x.key}" class="${x.key === v.key ? "on" : ""}"><span>${esc(x.label)}</span><span class="count">${state.counts[x.key] ?? ""}</span></button>`).join("")}
      <hr><h3>Team</h3>
      <button data-team="" class="${!state.team ? "on" : ""}"><span>All teams</span></button>
      ${Object.entries(TEAM).map(([k, n]) => `<button data-team="${k}" class="${state.team === k ? "on" : ""}"><span>${esc(n)}</span><span class="count">${k}</span></button>`).join("")}</div>
    <div class="listing"><div class="list-head"><h1>${esc(v.label)}</h1>${state.team ? tag(TEAM[state.team], "blue") : ""}<span class="muted num">${data.tickets.length} tickets</span><span class="grow"></span>
      <a class="btn quiet small" href="/api/v2/export.csv?view=${v.key}${state.team ? `&team=${state.team}` : ""}">${icon("download", 14)} Export CSV</a></div>
      ${ticketTable(data.tickets, { emptyText: "No tickets in this view.", sortable: true, sort })}</div></div>`;
  $(".listing").scrollTop = prevScroll;
  $$("[data-view]").forEach(b => b.onclick = () => go(`#/views/${b.dataset.view}`));
  $$("[data-team]").forEach(b => b.onclick = () => { state.team = b.dataset.team; store(`opslens.team.${user.id}`, state.team); views(v.key); });
  $$("th[data-sort]").forEach(th => th.onclick = () => {
    state.sort[v.key] = state.sort[v.key] === th.dataset.sort ? "" : th.dataset.sort;
    store(`opslens.sort.${user.id}`, state.sort);
    views(v.key);
  });
  $("#re").onclick = async () => { await loadCounts(); await views(v.key); toast("Up to date."); };
  $$("tr.row").forEach(r => r.onclick = () => go(`#/t/${r.dataset.id}`));
  shell.listKeys(".listing tr.row", r => go(`#/t/${r.dataset.id}`));
}

function ticketContext(t) {
  const solved = t.status === "solved";
  return {
    assignee: solved ? `<div class="val">${esc(t.assignee || "—")}</div>`
      : `<select class="field" id="assignee"><option value="">${t.assignee ? `${esc(t.assignee)} (current)` : "Unassigned"}</option></select>
         <button class="btn primary small" id="assign" style="margin-top:6px;width:100%" disabled>Assign</button><div class="small faint" id="assignnote" style="margin-top:4px">Loading who is on shift…</div>`,
    actions: "", canReply: !solved, canNote: true, canSolve: false,
    async wire() {
      if (solved) return;
      const sel = $("#assignee"), btn = $("#assign"), note = $("#assignnote");
      try {
        const { agents } = await api(`/api/v2/tickets/${encodeURIComponent(t.id)}/assignees`);
        sel.innerHTML += agents.map(a => `<option value="${esc(a.agent)}">${a.good ? "✓" : "·"} ${esc(a.agent)} ${esc(a.name)} — ${esc(a.status_word)}${a.good ? "" : !a.skill ? ", no skill" : ", no language"}</option>`).join("");
        note.textContent = agents.length ? `${agents.filter(a => a.good).length} on shift can handle ${CATEGORY[t.category] || t.category} in ${LANGUAGE[t.language] || t.language}.` : "Nobody is on shift.";
      } catch (e) { note.textContent = e.message; }
      sel.onchange = () => { btn.disabled = !sel.value; };
      btn.onclick = async () => {
        btn.disabled = true;
        btn.textContent = "Assigning…";
        try {
          await api(`/api/v2/tickets/${encodeURIComponent(t.id)}/assign`, { body: { agent: sel.value } });
          toast(`Assigned to ${sel.value}. OpsLens re-planned the floor around it.`, "good");
          setTimeout(() => render(), 1500);
        } catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = "Assign"; }
      };
    },
  };
}

async function problems(id) {
  shell.setTitle("Recurring problems");
  const panes = $$(".problem-list, .problem-detail");
  const keep = route().arg === (state.lastProblem || "") ? panes.map(x => x.scrollTop) : [];
  state.lastProblem = route().arg;
  const p = await problemsData();
  const chosen = new Set(p.chosen);
  const card = p.cards.find(c => c.id === id) || p.cards[0];
  const fixesFor = c => c.fixes.map(fid => p.fixes.find(f => f.id === fid)).filter(Boolean);
  const best = c => fixesFor(c).sort((a, b) => a.effect.missed - b.effect.missed)[0];
  const fixes = fixesFor(card);
  const [cause, color] = CAUSE[card.cause_type] || CAUSE.other;
  shell.main.innerHTML = `<div class="split" style="grid-template-columns:340px minmax(0,1fr)">
    <div class="listing problem-list" style="border-right:1px solid var(--line)">
      <div class="list-head"><div><h1 style="font-size:17px">${p.cards.length} recurring problems</h1><div class="small muted">Found in 56 days of tickets</div></div></div>
      ${p.cards.map(c => { const b = best(c); const [cw, cc] = CAUSE[c.cause_type] || CAUSE.other;
        return `<button data-card="${esc(c.id)}" class="${c.id === card.id ? "on" : ""}"><div class="t">${esc(c.title)}</div>
          <div class="m">${tag(cw, cc)}<span class="small muted">${c.affected_tickets.toLocaleString()} tickets</span>${c.today?.tickets ? `<span class="small muted">· ${c.today.tickets} today</span>` : ""}<span style="margin-left:auto">${b ? impactText(b.effect, true) : `<span class="small faint">no measured fix</span>`}</span></div></button>`; }).join("")}
    </div>
    <div class="listing problem-detail"><div class="page stack" style="max-width:980px">
      <div><div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">${tag(cause, color)}<span class="small muted">${esc(card.id)} · ${card.affected_tickets.toLocaleString()} tickets (${card.affected_share_pct}% of all)</span></div>
        <h1>${esc(card.title)}</h1><p class="muted" style="margin:6px 0 0">${esc(card.comparison_text || "")}</p></div>
      <div class="tiles">
        ${tile(card.metric, Number(card.value).toLocaleString(undefined, { maximumFractionDigits: 1 }), `vs ${Number(card.comparison_value).toLocaleString(undefined, { maximumFractionDigits: 1 })} for everyone else`, "bad")}
        ${tile("Tickets affected", card.affected_tickets.toLocaleString(), `${card.affected_share_pct}% of all tickets`)}
        ${card.today ? tile("Like this today", card.today.tickets, `${card.today.missed} missed · ${card.today.avg_wait_min ?? "—"} min average wait`, card.today.missed ? "bad" : "", "#/views/open") : ""}
      </div>
      <div class="card"><div class="head"><h2>Why it happens</h2></div><div class="body">
        <div>${esc(card.not_explained_by ? `Not explained by chance: ${card.not_explained_by}.` : "")}</div>
        <div style="margin-top:8px"><b>What to do:</b> ${esc(card.recommendation || "")}</div>
        ${card.examples?.length ? `<h3 style="margin-top:16px">Real tickets from this group</h3>${card.examples.map(x => `<div class="example">“${esc(x.text)}” <span class="faint">· ${esc(x.ticket_id)}${x.wait_min ? ` · waited ${fmtMin(x.wait_min)}` : ""}${x.breached ? " · missed" : ""}</span></div>`).join("")}` : ""}
      </div></div>
      <div class="card"><div class="head"><h2>Fixes, measured</h2><span class="small muted">${esc(p.how)}</span></div><div class="body">
        ${fixes.length ? fixes.map(f => `<div class="fix ${chosen.has(f.id) ? "chosen" : ""}"><div class="top-row"><div style="min-width:0">
            <div style="font-weight:600;font-size:15px">${esc(f.title)}</div>
            <div class="small muted" style="margin-top:2px">${esc(f.owner || "")} · ${esc(f.when || "")}${f.kind === "staffing" ? " · staffing move" : ""}</div>
            ${f.action ? `<div style="margin-top:8px">${esc(f.action)}</div>` : ""}
            ${f.assumptions?.length ? `<div class="small faint" style="margin-top:6px">Assumes ${esc(f.assumptions.join("; "))}</div>` : ""}</div>
          <div style="text-align:right;min-width:190px">${impactText(f.effect)}<div class="small muted">${signed(f.effect.rate, 2)} points on the missed rate</div>
            <button class="btn ${chosen.has(f.id) ? "quiet" : "primary"} small" style="margin-top:10px" data-choose="${esc(f.id)}" data-on="${chosen.has(f.id) ? 1 : 0}">${chosen.has(f.id) ? "✓ In your plan" : "Add to plan"}</button></div></div></div>`).join("")
          : `<div class="muted">No fix has been measured for this one yet. ${esc(card.recommendation || "")}</div>`}
      </div>${chosen.size ? `<div class="foot small">${chosen.size} fix${chosen.size === 1 ? "" : "es"} in your plan · <a href="#/plan">Simulate the plan</a></div>` : ""}</div>
    </div></div></div>`;
  $$(".problem-list, .problem-detail").forEach((x, i) => { if (keep[i]) x.scrollTop = keep[i]; });
  $$("[data-card]").forEach(b => b.onclick = () => go(`#/problems/${b.dataset.card}`));
  $$("[data-choose]").forEach(b => b.onclick = () => choose(b.dataset.choose, b.dataset.on !== "1", () => problems(card.id)));
  shell.listKeys(".problem-list button[data-card]", b => go(`#/problems/${b.dataset.card}`));
}

async function choose(id, on, redraw) {
  try {
    const out = await api(`/api/v2/plan/${encodeURIComponent(id)}`, { body: { chosen: on } });
    state.problems.chosen = out.chosen;
    shell.setBadge("plan", out.chosen.length);
    toast(on ? "Added to your plan." : "Removed from your plan.", on ? "good" : "", on ? { label: "Open plan", run: () => go("#/plan") } : null);
    redraw();
  } catch (e) { toast(e.message, true); }
}

async function plan() {
  shell.setTitle("Plan and impact");
  const [p, past] = await Promise.all([problemsData(), api("/api/v2/plan/runs").catch(() => ({ runs: [] }))]);
  const chosen = p.fixes.filter(f => p.chosen.includes(f.id));
  const sumIdea = chosen.reduce((n, f) => n + f.effect.missed, 0);
  const cardOf = id => p.cards.find(c => c.fixes.includes(id));
  shell.main.innerHTML = `<div class="page stack" style="max-width:1100px">
    <div class="page-head"><div><h1>Plan and impact</h1><p>Pick fixes on Recurring problems, then replay a real held-out day with and without them. The same tickets, people and luck are used both ways, so the difference is the plan.</p></div>
      <a class="btn quiet" href="#/problems">Add fixes</a></div>
    <div class="tiles">
      ${tile("Fixes in your plan", chosen.length, `of ${p.fixes.length} measured fixes`)}
      ${tile("Measured one by one", chosen.length ? signed(sumIdea) : "—", "missed promises over 14 days, added up", chosen.length ? "good" : "")}
      ${tile("All 18 together", signed(p.all.missed), `${p.all.without_pct}% → ${p.all.with_pct}% missed`, "good")}
    </div>
    <div class="card"><div class="head"><h2>Your plan</h2>${chosen.length ? `<button class="btn quiet small" id="clear">Clear plan</button>` : ""}</div>
      ${chosen.length ? `<table class="grid"><thead><tr><th>Fix</th><th class="hide-sm">For</th><th class="hide-sm">Owner</th><th class="right">Measured effect</th><th></th></tr></thead><tbody>
        ${chosen.map(f => { const c = cardOf(f.id); return `<tr><td><b>${esc(f.title)}</b><div class="sub">${esc(f.when || "")}</div></td>
          <td class="hide-sm">${c ? `<a href="#/problems/${esc(c.id)}">${esc(c.title)}</a>` : `<span class="muted">Staffing</span>`}</td><td class="hide-sm small">${esc(f.owner || "")}</td>
          <td class="right">${impactText(f.effect, true)}<div class="sub">${signed(f.effect.missed_low)} to ${signed(f.effect.missed_high)}</div></td>
          <td class="right"><button class="btn quiet small" data-drop="${esc(f.id)}">Remove</button></td></tr>`; }).join("")}</tbody></table>`
        : `<div class="empty">${icon("plan", 40)}Your plan is empty. <a href="#/problems">Choose fixes from recurring problems</a>, or <button class="btn quiet small" id="addbest">add the five strongest</button></div>`}
    </div>
    <div class="card"><div class="head"><h2>Replay a day with your plan</h2></div><div class="body">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span>Day</span>
        <select class="field" id="day">${p.days.map(d => `<option value="${d.day}">Day ${d.day} · ${esc(d.weekday)} ${esc(d.date)}</option>`).join("")}</select>
        <button class="btn primary" id="sim" ${chosen.length ? "" : "disabled"}>Simulate</button><span class="small muted" id="simnote">Takes about 30 seconds: 3 seeds, with and without.</span></div>
      <div class="progress" id="prog" hidden><span></span></div><div id="simout"></div>
    </div></div>
    ${past.runs.length ? `<div class="card"><div class="head"><h2>Earlier replays</h2></div><table class="grid"><thead><tr><th>When</th><th>Day</th><th class="right">Fixes</th><th class="right">Missed without</th><th class="right">With plan</th><th class="right">Difference</th></tr></thead><tbody>
      ${past.runs.map(r => `<tr><td class="small">${ago(r.at)}</td><td>Day ${r.day} · ${esc(r.weekday || "")}</td><td class="right num">${r.items.length}</td><td class="right num">${Math.round(r.without)}</td><td class="right num">${Math.round(r.with_plan)}</td>
        <td class="right">${impactText({ missed: r.with_plan - r.without, certain: r.with_plan < r.without, worse: r.with_plan > r.without }, true)}</td></tr>`).join("")}</tbody></table></div>` : ""}
  </div>`;
  $$("[data-drop]").forEach(b => b.onclick = () => choose(b.dataset.drop, false, plan));
  if ($("#clear")) $("#clear").onclick = async () => { for (const f of chosen) await api(`/api/v2/plan/${f.id}`, { body: { chosen: false } }); state.problems = null; plan(); toast("Plan cleared."); };
  if ($("#addbest")) $("#addbest").onclick = async () => {
    for (const f of [...p.fixes].filter(f => f.effect.certain).sort((a, b) => a.effect.missed - b.effect.missed).slice(0, 5)) await api(`/api/v2/plan/${f.id}`, { body: { chosen: true } });
    state.problems = null;
    toast("Added the five fixes with the largest measured effect.", "good");
    plan();
  };
  const daySel = $("#day");
  const firstDay = Math.min(...chosen.map(f => Number((f.when || "").match(/\d+/)?.[0] || p.test_days[0])), p.test_days[1]);
  if (chosen.length) daySel.value = String(Math.max(p.test_days[0], firstDay));
  $("#sim").onclick = async () => {
    if (state.simulating) return;
    state.simulating = true;
    const btn = $("#sim"), prog = $("#prog"), bar = prog.firstElementChild;
    btn.disabled = true;
    btn.textContent = "Simulating…";
    prog.hidden = false;
    const started = Date.now();
    const timer = setInterval(() => { const s = (Date.now() - started) / 1000; bar.style.width = `${Math.min(95, s / 40 * 100)}%`; $("#simnote").textContent = `${Math.round(s)} s · replaying day ${daySel.value}…`; }, 400);
    try {
      const r = await api("/api/v2/plan/simulate", { body: { day: Number(daySel.value) } });
      bar.style.width = "100%";
      $("#simout").innerHTML = simResult(r);
      toast(`Day ${r.day}: ${Math.round(r.without.breaches)} → ${Math.round(r.with.breaches)} missed promises with your plan.`, r.delta.breaches < 0 ? "good" : "");
    } catch (e) { toast(e.message, true); $("#simout").innerHTML = `<div class="answer-box">${esc(e.message)}</div>`; }
    clearInterval(timer);
    $("#simnote").textContent = "Takes about 30 seconds: 3 seeds, with and without.";
    btn.disabled = false;
    btn.textContent = "Simulate";
    state.simulating = false;
    setTimeout(() => { prog.hidden = true; bar.style.width = "0"; }, 600);
  };
}

function simResult(r) {
  const keys = ["breaches", "breach_pct", "mean_resolution_min", "p90_resolution_min", "transfers", "busy_agent_hours"];
  const changes = (r.items || []).filter(i => !i.applied && i.applied !== undefined);
  return `<div style="margin-top:14px"><div class="tiles">
    ${tile(`Missed without · day ${r.day}`, Math.round(r.without.breaches), `${r.without.breach_pct.toFixed(2)}% of tickets`)}
    ${tile("Missed with your plan", Math.round(r.with.breaches), `${r.with.breach_pct.toFixed(2)}% of tickets`, r.delta.breaches < 0 ? "good" : r.delta.breaches > 0 ? "bad" : "")}
    ${tile("Customers who keep their promise", r.delta.breaches < 0 ? Math.round(-r.delta.breaches) : 0, `on ${esc(r.weekday)}, from ${r.items.length} fix${r.items.length === 1 ? "" : "es"}`, r.delta.breaches < 0 ? "good" : "")}
  </div>
  <table class="grid" style="margin-top:12px"><thead><tr><th>Measure</th><th class="right">Without</th><th class="right">With plan</th><th class="right">Change</th><th class="right hide-sm">Each seed</th></tr></thead><tbody>
    ${keys.filter(k => r.without[k] !== undefined).map(k => { const d = r.delta[k]; const better = r.better?.[k] === "lower" ? d < 0 : r.better?.[k] === "higher" ? d > 0 : null;
      return `<tr><td>${esc(r.labels?.[k] || k)}</td><td class="right num">${Number(r.without[k]).toFixed(k.includes("pct") ? 2 : 1)}</td><td class="right num">${Number(r.with[k]).toFixed(k.includes("pct") ? 2 : 1)}</td>
        <td class="right num" style="color:${better === null || d === 0 ? "inherit" : better ? "var(--green)" : "var(--red)"};font-weight:600">${signed(d, k.includes("pct") ? 2 : 1)} ${esc(r.units?.[k] || "")}</td>
        <td class="right small muted hide-sm">${(r.delta_by_seed?.[k] || []).map(x => signed(x, 1)).join(" · ")}</td></tr>`; }).join("")}</tbody></table>
  <div class="small muted" style="margin-top:8px">${esc(r.note || "")} ${changes.length ? `${changes.length} fix(es) do not apply on this day.` : ""} Took ${r.seconds} s.</div></div>`;
}

async function team(code) {
  shell.setTitle("Team");
  let floor;
  try { floor = await api("/api/v2/floor"); }
  catch (e) { shell.main.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const order = { busy: 0, cross: 0, wrong: 0, idle: 1, break: 2, off: 3 };
  const people = [...floor.people].sort((a, b) => (order[a.status] ?? 4) - (order[b.status] ?? 4) || (a.team || "").localeCompare(b.team || "") || a.id.localeCompare(b.id));
  const filter = state.teamFilter || "";
  const shown = people.filter(p => !filter || p.team === filter);
  const count = s => people.filter(p => s.includes(p.status)).length;
  shell.main.innerHTML = `<div class="page stack">
    <div class="page-head"><div><h1>Team</h1><p>Who is working on what right now. Send someone on a break or bring them back: OpsLens re-plans the floor at once.</p></div>
      <select class="field" id="tf"><option value="">All teams</option>${Object.entries(TEAM).map(([k, n]) => `<option value="${k}" ${filter === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>
    <div class="tiles">${tile("On shift", people.length - count(["off"]), `of ${people.length} people`)}${tile("Free", count(["idle"]), "ready for the next ticket", "good")}
      ${tile("Working", count(["busy", "cross", "wrong"]), `${count(["cross"])} helping another team`)}${tile("On break", count(["break"]), "")}</div>
    <div class="card"><table class="grid"><thead><tr><th>Agent</th><th class="hide-sm">Team</th><th>Status</th><th>Working on</th><th class="right">Solved</th><th class="right hide-sm">On time</th><th class="right hide-sm">Helped others</th><th></th></tr></thead><tbody>
    ${shown.map(p => `<tr class="row" data-agent="${esc(p.id)}">
      <td><div style="display:flex;gap:10px;align-items:center"><span class="avatar">${esc(initials(p.name))}<span class="pres ${esc(p.status)}"></span></span><div><b>${esc(p.name || p.id)}</b><div class="sub">${esc(p.id)} · ${esc((p.languages || []).map(l => LANGUAGE[l] || l).join(", "))}</div></div></div></td>
      <td class="hide-sm small">${esc(TEAM[p.team] || p.team || "")}</td><td>${agentTag(p.status)}</td>
      <td>${p.current ? `<a href="#/t/${encodeURIComponent(p.current.ticket_id)}" data-stop>#${esc(p.current.ticket_id)}</a> <span class="small muted">${esc(CATEGORY[p.current.category] || p.current.category)} · ${p.current.minutes_left < 0 ? `${fmtMin(-p.current.minutes_left)} late` : `${fmtMin(p.current.minutes_left)} left`}</span>` : `<span class="faint">—</span>`}</td>
      <td class="right num">${p.done}</td><td class="right num hide-sm">${p.done ? `${Math.round(100 * p.kept / p.done)}%` : "—"}</td><td class="right num hide-sm">${p.rescues}</td>
      <td class="right nowrap">${p.status === "break" ? `<button class="btn quiet small" data-status="back" data-who="${esc(p.id)}" data-stop>Bring back</button>`
        : p.status !== "off" ? `<button class="btn quiet small" data-status="break" data-who="${esc(p.id)}" data-stop>Send on break</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div></div>`;
  $("#tf").onchange = e => { state.teamFilter = e.target.value; team(); };
  $$("[data-stop]").forEach(el => el.addEventListener("click", e => e.stopPropagation()));
  $$("[data-status]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    try {
      await api(`/api/v2/agents/${b.dataset.who}/status`, { body: { kind: b.dataset.status } });
      toast(b.dataset.status === "break" ? `${b.dataset.who} is on a break. Their tickets are being re-planned.` : `${b.dataset.who} is back and can take tickets.`, "good");
      setTimeout(() => team(code), 1500);
    } catch (e) { toast(e.message, true); b.disabled = false; }
  });
  $$("tr[data-agent]").forEach(r => r.onclick = () => go(`#/team/${r.dataset.agent}`));
  shell.listKeys(".main tr[data-agent]", r => go(`#/team/${r.dataset.agent}`));
  if (code) drawer(code);
}

async function drawer(code) {
  $(".drawer")?.remove();
  const d = document.createElement("div");
  d.className = "drawer";
  d.innerHTML = `<div class="head"><h2>${esc(code)}</h2><button class="btn quiet small" id="dclose">${icon("x", 14)}</button></div><div class="body" style="padding:18px"><div class="skeleton"></div></div>`;
  document.body.append(d);
  const close = () => { d.remove(); if (route().page === "team") history.replaceState(null, "", "#/team"); };
  $("#dclose").onclick = close;
  try {
    const p = await api(`/api/v2/team/${encodeURIComponent(code)}`);
    const pr = p.profile;
    d.querySelector(".body").innerHTML = `<div style="display:flex;gap:12px;align-items:center"><span class="avatar big">${esc(initials(pr.name))}<span class="pres ${esc(p.live?.status || "off")}"></span></span>
      <div><h2>${esc(pr.name)}</h2><div class="small muted">${esc(pr.agent_code)} · ${esc(TEAM[pr.team] || pr.team)} · ${agentTag(p.live?.status || "off")}</div></div></div>
      <dl class="kv" style="margin-top:16px"><dt>Shift</dt><dd>${String(pr.shift_start_hour).padStart(2, "0")}:00 for ${pr.shift_hours} h</dd>
        <dt>Handles</dt><dd>${pr.skills.map(s => tag(CATEGORY[s] || s)).join(" ")}</dd><dt>Speaks</dt><dd>${pr.languages.map(l => esc(LANGUAGE[l] || l)).join(", ")}</dd>
        <dt>Today</dt><dd>${p.today.solved} solved · ${p.today.on_time} on time · ${p.today.open} open</dd></dl>
      ${p.live?.current ? `<div class="box" style="margin-top:14px"><h3>Working on</h3><a href="#/t/${esc(p.live.current.ticket_id)}">#${esc(p.live.current.ticket_id)}</a> ${esc(CATEGORY[p.live.current.category] || "")}</div>` : ""}
      <h3 style="margin:18px 0 6px">Today's tickets</h3>${p.recent.length ? p.recent.map(t => `<a href="#/t/${esc(t.id)}" style="display:flex;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line-soft);color:inherit;text-decoration:none">
        <span class="st ${esc(t.status)}">${t.status === "solved" ? "S" : t.status === "open" ? "N" : "O"}</span><span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" class="small">${esc(t.subject)}</span>${t.breached ? tag("missed", "red") : ""}</a>`).join("") : `<div class="small muted">None yet.</div>`}`;
  } catch (e) { d.querySelector(".body").innerHTML = `<div class="muted">${esc(e.message)}</div>`; }
}

async function analysis() {
  shell.setTitle("Analysis");
  const a = await api("/api/v2/analysis");
  const h = a.headline;
  const ms = Object.entries(h.metrics);
  const colors = { baseline_d: "var(--ink-4)", least_slack_rescue: "#8fb3cf", S2: "var(--blue)" };
  const vs = h.pairs["vs skills routing"]["turnaround.breach_pct"], vs2 = h.pairs["vs least slack + rescue"]["turnaround.breach_pct"];
  const ops = h.policies.find(p => p.key === "S2"), base = h.policies.find(p => p.key === "baseline_d");
  shell.main.innerHTML = `<div class="page stack" style="max-width:1100px">
    <div class="page-head"><div><h1>Analysis</h1><p>How OpsLens was measured. Days ${h.days[0]}–${h.days[1]} were held out and replayed once with the code frozen, ${h.seeds.length} seeds each, the same customers and agents for every way of routing.</p></div>
      <a class="btn quiet" href="/app/" target="_blank" rel="noopener">${icon("external", 14)} Research dashboard</a></div>
    <div class="tiles">
      ${tile("OpsLens missed", `${ops["turnaround.breach_pct"]}%`, "of promises on held-out days", "good")}
      ${tile("Industry skills routing", `${base["turnaround.breach_pct"]}%`, "same tickets, same people", "bad")}
      ${tile("Difference", `${signed(vs.diff, 2)} pts`, `95% range ${signed(vs.low, 2)} to ${signed(vs.high, 2)}`, "good")}
      ${tile("Against the best published rule", `${signed(vs2.diff, 2)} pts`, `least slack + rescue · ${signed(vs2.low, 2)} to ${signed(vs2.high, 2)}`, "good")}
    </div>
    <div class="card"><div class="head"><h2>Three ways to route the same 14 days</h2><div style="display:flex;gap:12px" class="small">${h.policies.map(p => `<span><span class="dot" style="color:${colors[p.key]}"></span> ${esc(p.name)}</span>`).join("")}</div></div><div class="body">
      ${ms.map(([k, label]) => { const most = Math.max(...h.policies.map(p => p[k]));
        return `<div style="margin-bottom:14px"><div style="font-weight:600;margin-bottom:4px">${esc(label)}</div>${h.policies.map(p => `<div class="hbar"><span class="small muted">${esc(p.name)}</span>
          <div class="track"><span style="width:${100 * p[k] / most}%;background:${colors[p.key]}"></span></div><b class="num right" style="text-align:right">${p[k]}${k.includes("pct") ? "%" : ""}</b></div>`).join("")}</div>`; }).join("")}
      <div class="small muted">Lower is better for every row. The decision recorded before the run: “${esc(h.decision)}”.</div></div></div>
    <div class="cols even">
      <div class="card"><div class="head"><h2>The models inside</h2></div><div class="body"><dl class="kv" style="grid-template-columns:1fr auto">
        <dt>Who will miss their promise (risk model)</dt><dd><b>${a.models.risk_auc}</b> AUC</dd>
        <dt>The same model on the real UCI help desk</dt><dd><b>${a.models.risk_real_auc}</b> AUC</dd>
        <dt>48-hour ticket forecast error</dt><dd><b>${a.models.forecast_wape}</b> vs ${a.models.forecast_naive_wape} naive</dd>
        <dt>Forecast 80% band covers</dt><dd><b>${a.models.forecast_cover_80}%</b></dd>
        <dt>Routing classifier on the laptop</dt><dd><b>${a.models.classify_local}%</b> correct</dd>
        ${a.models.classify_local_llm ? `<dt>Local LLM alone (qwen2.5:3b) vs cloud</dt><dd><b>${a.models.classify_local_llm}%</b> vs ${a.models.classify_cloud_llm}%</dd>` : ""}
      </dl></div></div>
      <div class="card"><div class="head"><h2>Finding problems and scale</h2></div><div class="body"><dl class="kv" style="grid-template-columns:1fr auto">
        <dt>Problems we hid in the data and it found</dt><dd><b>${a.patterns.found} of ${a.patterns.planted}</b></dd>
        <dt>In a blind test of 20 fresh sets</dt><dd><b>${a.patterns.blind_found} of ${a.patterns.blind_planted}</b></dd>
        ${a.scale.tickets ? `<dt>Load test</dt><dd><b>${Number(a.scale.tickets).toLocaleString()}</b> tickets · ${esc(a.scale.size)}</dd>
        <dt>Team queue at that size</dt><dd><b>${a.scale.queue_ms} ms</b></dd>
        <dt>40 users at once</dt><dd><b>${a.scale.rps}</b> requests/s · ${a.scale.errors} errors · p95 ${a.scale.p95_ms} ms</dd>` : ""}
      </dl></div></div>
    </div></div>`;
}

async function ai(id) {
  shell.setTitle("AI activity");
  if (id) {
    let data;
    try { data = await api(`/api/v2/runs/${encodeURIComponent(id)}`); }
    catch (e) { shell.main.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const r = data.run;
    const [label, color] = RUN_STATUS[r.status] || [r.status, ""];
    shell.main.innerHTML = `<div class="page stack" style="max-width:1000px">
      <div><a href="#/ai" class="small">← AI activity</a></div>
      <div class="card"><div class="head"><div><h2>${esc(AGENT_NAME[r.agent] || r.agent)} · run ${r.id}</h2>
        <div class="small muted">${esc(r.trigger)} · ${clock(r.started_at)} · ${seconds(r)}${r.ticket_id ? ` · <a href="#/t/${encodeURIComponent(r.ticket_id)}">#${esc(r.ticket_id)}</a>` : ""}</div></div>${tag(label, color)}</div>
        <div class="body"><div style="font-weight:600">${esc(r.summary || "")}</div>${r.output?.reply ? `<div class="answer-box">${esc(r.output.reply)}</div>` : ""}</div></div>
      <div class="card"><div class="head"><h2>Every step</h2><span class="small muted">What it asked for, what came back, what it decided</span></div>
        <table class="grid"><thead><tr><th>#</th><th>Step</th><th>Details</th></tr></thead><tbody>
        ${data.steps.map(s => `<tr><td class="num">${s.n}</td><td>${esc(stepText(s))}</td><td><details><summary class="small muted" style="cursor:pointer">${esc(s.kind.replace("_", " "))}</summary>
          <pre style="white-space:pre-wrap;font-size:12px;max-height:280px;overflow:auto">${esc(JSON.stringify(s.payload, null, 2))}</pre></details></td></tr>`).join("")}</tbody></table></div></div>`;
    return;
  }
  const { runs, last_day } = await api("/api/v2/runs?limit=80");
  const by = Object.fromEntries(last_day.map(d => [d.agent, d]));
  shell.main.innerHTML = `<div class="page stack">
    <div class="page-head"><div><h1>AI activity</h1><p>Four agents on the local model (qwen2.5:3b on Ollama). They read, draft, explain and propose; the optimiser still decides who gets each ticket, and you approve what they suggest.</p></div></div>
    <div class="tiles">${["intake", "copilot", "analyst", "ask"].map(k => { const d = by[k];
      return tile(AGENT_NAME[k], d ? d.runs : 0, d ? `last 24 h · ${d.avg_seconds ?? "—"} s each · ${d.failed} failed` : "no runs in the last 24 h"); }).join("")}</div>
    <div class="card">${runs.length ? `<table class="grid"><thead><tr><th>Agent</th><th>What happened</th><th>Status</th><th class="right hide-sm">Tools</th><th class="right">When</th></tr></thead><tbody>
    ${runs.map(r => { const [label, color] = RUN_STATUS[r.status] || [r.status, ""];
      return `<tr class="row" data-run="${r.id}"><td class="nowrap">${esc(AGENT_NAME[r.agent] || r.agent)}</td><td><div class="subject" style="font-weight:500">${esc(r.summary || r.trigger)}</div><div class="sub">${esc(r.trigger)}${r.ticket_id ? ` · #${esc(r.ticket_id)}` : ""}</div></td>
        <td>${tag(label, color)}</td><td class="right num hide-sm">${r.tools_used}</td><td class="right small muted nowrap">${ago(r.started_at)}</td></tr>`; }).join("")}</tbody></table>`
      : `<div class="empty">No AI runs yet.</div>`}</div></div>`;
  $$("tr[data-run]").forEach(r => r.onclick = () => go(`#/ai/${r.dataset.run}`));
  shell.listKeys(".main tr[data-run]", r => go(`#/ai/${r.dataset.run}`));
}

async function render() {
  const r = route();
  shell.state.current = null;
  shell.state.listKeys = null;
  if (r.page !== "team") $(".drawer")?.remove();
  shell.setNav(r.page === "t" ? "views" : r.page);
  try {
    if (r.page === "t") await ticketPage(shell, r.arg, { context: ticketContext, after: loadCounts });
    else if (r.page === "views") await views(r.arg);
    else if (r.page === "problems") await problems(r.arg);
    else if (r.page === "plan") await plan();
    else if (r.page === "team") await team(r.arg);
    else if (r.page === "analysis") await analysis();
    else if (r.page === "ai") await ai(r.arg);
    else await home();
  } catch (e) {
    shell.main.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
  shell.drawTabs();
}

async function refresh() {
  await loadCounts();
  const r = route();
  if (state.asking || state.simulating || document.activeElement?.closest?.("#askform, .composer, select")) return;
  const top = shell.main.scrollTop;
  if (r.page === "home") await home();
  else if (r.page === "views") await views(r.arg);
  else if (r.page === "team" && !$(".drawer")) await team();
  else return;
  shell.main.scrollTop = top;
}

window.addEventListener("hashchange", render);
await loadCounts();
problemsData().then(p => shell.setBadge("plan", p.chosen.length)).catch(() => {});
await render();
onFloorChange(refresh);
tickDue();
