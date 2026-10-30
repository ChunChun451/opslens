export const CATEGORY = {
  late_delivery: "Late delivery", missing_item: "Missing item", wrong_item: "Wrong item", refund: "Refund",
  payment_failure: "Payment failed", app_bug: "App problem", account: "Account", restaurant_partner: "Restaurant partner",
};
export const LANGUAGE = { en: "English", hi: "Hindi", other: "Other" };
export const TEAM = { A: "Team A", B: "Team B", C: "Team C", D: "Team D" };
export const STATUS = {
  open: ["Waiting", "amber"], in_progress: ["Being worked", "blue"], solved: ["Solved", "green"],
};
export const AGENT_STATUS = {
  idle: ["Free", "green"], busy: ["Working", "blue"], cross: ["Helping out", "accent"], wrong: ["Working", "blue"],
  break: ["On break", "amber"], off: ["Off shift", "grey"],
};

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function $(sel, root = document) { return root.querySelector(sel); }

export async function api(path, options = {}) {
  const init = { credentials: "same-origin", ...options };
  if (options.body !== undefined) {
    init.method = options.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  if (response.status === 401 && location.pathname !== "/") {
    location.href = "/";
    throw new Error("Please log in again.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || body.detail || `Request failed (${response.status})`);
  return body;
}

export async function signedIn(roles) {
  const { user } = await api("/api/v2/me");
  if (!roles.includes(user.role)) {
    location.href = user.role === "agent" ? "/agent/" : "/admin/";
    throw new Error("wrong screen");
  }
  return user;
}

export async function logout() {
  await api("/api/v2/logout", { body: {} }).catch(() => {});
  location.href = "/";
}

export function initials(name) {
  return String(name || "?").split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

export function pill(text, color) { return `<span class="pill ${color}">${esc(text)}</span>`; }

export function prio(p) { return `<span class="prio ${esc(p)}">${esc(p)}</span>`; }

export function statusPill(status) {
  const [text, color] = STATUS[status] || [status, "grey"];
  return pill(text, color);
}

export function agentPill(status) {
  const [text, color] = AGENT_STATUS[status] || [status, "grey"];
  return `<span class="pill ${color}"><span class="dot"></span>${esc(text)}</span>`;
}

export function riskPill(risk) {
  if (risk === null || risk === undefined) return pill("Not scored", "grey");
  const pct = Math.round(risk * 100);
  if (risk >= 0.5) return pill(`High · ${pct}%`, "red");
  if (risk >= 0.25) return pill(`Medium · ${pct}%`, "amber");
  return pill(`Low · ${pct}%`, "green");
}

export function minutesUntil(iso) { return (new Date(iso) - Date.now()) / 60000; }

export function dueText(ticket) {
  if (ticket.status === "solved") {
    return ticket.breached ? `<span class="due late">Missed promise</span>` : `<span class="muted">Kept promise</span>`;
  }
  const m = minutesUntil(ticket.sla_due_at);
  if (m < 0) return `<span class="due late">${Math.round(-m)} min late</span>`;
  const cls = m <= 10 ? "due soon" : "due";
  return `<span class="${cls} num">${m < 1 ? "under 1" : Math.round(m)} min left</span>`;
}

export function clock(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)} h ${m % 60} min ago`;
}

export function subject(ticket) {
  const body = String(ticket.subject || ticket.body || "").trim();
  return body.length > 90 ? body.slice(0, 88) + "…" : body;
}

let toastTimer;
export function toast(message, bad = false) {
  let box = $(".toast");
  if (!box) { box = document.createElement("div"); box.className = "toast"; document.body.append(box); }
  box.textContent = message;
  box.classList.toggle("bad", bad);
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, 4000);
}

export function onFloorChange(refresh, everyMs = 15000) {
  let pending;
  const soon = () => { clearTimeout(pending); pending = setTimeout(refresh, 400); };
  try {
    const stream = new EventSource("/api/v2/stream");
    stream.addEventListener("floor", soon);
  } catch { }
  setInterval(() => { if (!document.hidden) refresh(); }, everyMs);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) soon(); });
}

export function ticketTable(tickets, { selected, showAssignee = true, emptyText = "Nothing here right now." } = {}) {
  if (!tickets.length) return `<div class="empty">${esc(emptyText)}</div>`;
  const rows = tickets.map(t => `
    <tr class="row ${t.id === selected ? "sel" : ""}" data-id="${esc(t.id)}">
      <td>${prio(t.priority)}</td>
      <td><div class="subject">${esc(subject(t))}</div><div class="muted" style="font-size:12px">${esc(t.id)} · ${esc(CATEGORY[t.category] || t.category || "")} · ${esc(LANGUAGE[t.language] || t.language || "")}</div></td>
      <td>${statusPill(t.status)}</td>
      ${showAssignee ? `<td class="hide-sm">${esc(t.assignee || "—")}</td>` : ""}
      <td>${dueText(t)}</td>
      <td class="hide-sm">${t.status === "solved" ? "" : riskPill(t.risk)}</td>
    </tr>`).join("");
  return `<table class="grid"><thead><tr><th>Priority</th><th>Ticket</th><th>Status</th>
    ${showAssignee ? `<th class="hide-sm">Agent</th>` : ""}<th>Promise</th><th class="hide-sm">Chance of missing</th></tr></thead><tbody>${rows}</tbody></table>`;
}

export function wireCopilot(root, ticketId) {
  const button = root.querySelector("#draft");
  if (!button) return;
  const out = root.querySelector("#draftout");
  button.onclick = async () => {
    button.disabled = true;
    button.textContent = "Drafting…";
    try {
      const done = await runAgent("/api/v2/copilot", { ticket_id: ticketId }, d => { out.innerHTML = traceList(d.steps); });
      const o = done.run.output || {};
      if (done.run.status !== "done" || !o.reply) throw new Error(done.run.summary || "No draft this time.");
      out.innerHTML = traceList(done.steps) + `
        <textarea class="draft" style="margin-top:10px">${esc(o.reply)}</textarea>
        <div style="font-size:12px;margin-top:6px" class="muted">Policy: ${esc(o.policy || "—")} · ${seconds(done.run)} on this laptop's GPU</div>
        ${o.fixed ? `<div style="font-size:12px;margin-top:4px">${pill("Fixed after checking", "amber")} removed: ${esc(o.problems.join("; "))}</div>` : ""}
        ${o.check ? `<div style="font-size:12px;margin-top:4px"><b>Check first:</b> ${esc(o.check)}</div>` : ""}
        <button class="btn small" id="copy" style="margin-top:8px">Copy</button>`;
      out.querySelector("#copy").onclick = async () => {
        await navigator.clipboard.writeText(out.querySelector("textarea").value).catch(() => {});
        toast("Copied. Paste it into your reply.");
      };
    } catch (e) {
      out.innerHTML = `<div class="muted" style="font-size:13px;margin-top:8px">${esc(e.message)}</div>`;
    }
    button.disabled = false;
    button.textContent = "Draft again";
  };
}

export function ticketDetail(data, { user, extraActions = "", copilot = false } = {}) {
  const t = data.ticket;
  const events = data.events.map(e => `<li><span class="muted num">${clock(e.at)}</span><span>${esc(eventText(e))}</span></li>`).join("");
  const reasons = Array.isArray(t.risk_reasons) ? t.risk_reasons : [];
  const decided = data.decisions.at(-1);
  return `
  <div class="ticket">
    <div class="conv">
      <div class="muted" style="font-size:12px">${esc(t.id)} · ${esc(t.channel || "")}</div>
      <h1 style="margin-top:4px">${esc(CATEGORY[t.category] || t.category)} ${t.customer_tier && t.customer_tier !== "normal" ? pill(t.customer_tier, "accent") : ""}</h1>
      <div class="meta">${prio(t.priority)} ${statusPill(t.status)} ${pill(LANGUAGE[t.language] || t.language, "grey")} ${pill(TEAM[t.team] || t.team, "grey")}</div>
      <div class="msg"><div class="from"><span>Customer · ${esc(t.channel || "")}</span><span>${clock(t.created_at)}</span></div>${esc(t.body)}</div>
      ${decided ? `<div class="msg note"><div class="from"><span>OpsLens assigned this to ${esc(decided.agent_code)}</span><span>${clock(decided.at)}</span></div>${esc(decided.reason)}</div>` : ""}
      <div class="actions">${extraActions || `<span class="muted">No actions for you on this ticket.</span>`}</div>
    </div>
    <aside class="side">
      <div class="aside-box">
        <h3>Promise</h3>
        <dl class="kv">
          <dt>Due</dt><dd>${clock(t.sla_due_at)} · ${dueText(t)}</dd>
          <dt>Arrived</dt><dd>${clock(t.created_at)}</dd>
          <dt>Picked up</dt><dd>${t.assigned_at ? clock(t.assigned_at) : "Not yet"}</dd>
          <dt>Solved</dt><dd>${t.solved_at ? clock(t.solved_at) : "Not yet"}</dd>
          <dt>Agent</dt><dd>${esc(t.assignee || "Nobody yet")}</dd>
        </dl>
      </div>
      <div class="aside-box ai">
        <h3>OpsLens</h3>
        ${t.status === "solved" ? `<div class="muted">Closed. ${t.breached ? "The promise was missed." : "The promise was kept."}</div>`
          : `<div>Chance of missing the promise: ${riskPill(t.risk)}</div>`}
        ${reasons.length ? `<ul class="reasons">${reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
        ${t.assign_reason ? `<div style="margin-top:10px;font-size:13px"><b>Why this agent:</b> ${esc(t.assign_reason)}</div>` : ""}
        ${t.ai_summary ? `<div style="margin-top:10px;font-size:13px"><b>AI read:</b> ${esc(t.ai_summary)}
          <div style="margin-top:4px">${t.ai_category && t.ai_category !== t.category
            ? pill(`AI thinks: ${CATEGORY[t.ai_category] || t.ai_category}`, "amber") : pill("Category confirmed", "green")}
          ${t.ai_urgency === "high" ? pill("Urgent", "red") : ""}</div></div>` : ""}
      </div>
      ${copilot ? `<div class="aside-box ai" id="copilot"><h3>Reply copilot</h3>
        <div class="muted" style="font-size:13px">Drafts a reply from the company policy on the local model. You edit it before sending.</div>
        <button class="btn small primary" id="draft" style="margin-top:10px">Draft a reply</button><div id="draftout"></div></div>` : ""}
      <div class="aside-box">
        <h3>History</h3>
        <ul class="timeline">${events || `<li><span></span><span class="muted">No events yet</span></li>`}</ul>
      </div>
    </aside>
  </div>`;
}

export function eventText(e) {
  const d = e.detail || {};
  if (e.kind === "created") return "Customer wrote in";
  if (e.kind === "assigned") return `Given to ${e.actor || d.agent || "an agent"}`;
  if (e.kind === "solved") return `Solved by ${e.actor || "the agent"}`;
  if (e.kind === "breached") return "Promise time passed";
  return e.kind;
}

export const AGENT_NAME = { intake: "Intake", copilot: "Reply copilot", analyst: "Floor analyst", ask: "Ask OpsLens" };
const TOOL_WORDS = {
  read_ticket: "Read the ticket", search_policies: "Searched the policies", similar_tickets: "Looked for similar solved tickets",
  review_against_policy: "Checked the draft against the policy", embed: "Stored the message's meaning for search",
  floor_summary: "Read today's numbers", at_risk: "Listed tickets likely to miss", people_now: "Counted who is working",
  free_agents: "Found who is free", category_mix: "Compared categories with usual", tickets_per_hour: "Read tickets per hour",
  check_proposals: "Dropped actions that failed checks",
};

export function stepText(step) {
  const tool = TOOL_WORDS[step.tool] || step.tool || "";
  if (step.kind === "tool_call") return tool;
  if (step.kind === "tool_result") {
    const p = step.payload;
    if (Array.isArray(p)) return `${tool}: ${p.length} found`;
    if (p && p.unsupported) return `${tool}: ${p.unsupported.length ? `${p.unsupported.length} claim(s) not backed by policy` : "all claims backed"}`;
    return `${tool}: done`;
  }
  if (step.kind === "answer") return "Wrote the answer";
  if (step.kind === "error") return `${tool || "Step"} was refused: ${JSON.stringify(step.payload).slice(0, 120)}`;
  return step.kind;
}

export function seconds(run) {
  if (!run.finished_at) return "";
  return `${((new Date(run.finished_at) - new Date(run.started_at)) / 1000).toFixed(1)} s`;
}

export async function runAgent(path, body, onProgress) {
  const { run_id } = await api(path, { body });
  for (let i = 0; i < 300; i++) {
    const data = await api(`/api/v2/runs/${run_id}`);
    onProgress(data);
    if (data.run.status !== "running") return data;
    await new Promise(r => setTimeout(r, 700));
  }
  throw new Error("The local model is taking too long. Is Ollama running?");
}

export function traceList(steps) {
  const shown = steps.filter(s => s.kind !== "tool_call");
  return `<ol class="trace">${shown.map(s => `<li class="${s.kind}">${esc(stepText(s))}</li>`).join("") || `<li>Starting…</li>`}</ol>`;
}
