import { pageHeader, card, stat } from "../ui.js";
import { escapeHtml } from "../format.js";

const pct = (v, digits = 1) => (typeof v === "number" ? `${(v * 100).toFixed(digits)}%` : "—");
const MODES = [["both", "Meaning and words (used)"], ["meaning", "Meaning only"], ["words", "Words only"]];

export function render(section) {
  section.innerHTML = `${pageHeader("AI with retrieval (RAG)",
    "Before the AI answers, OpsLens finds the most relevant pieces of its own data and gives only those to the AI, which must answer from them and cite them.")}
    <div id="rag-body"><div class="card">Loading…</div></div>`;
  load(section);
}

async function load(section) {
  const body = section.querySelector("#rag-body");
  let d;
  try {
    const r = await fetch("/api/rag/status", { credentials: "same-origin" });
    d = await r.json();
    if (!r.ok) throw new Error(d.error || `server answered ${r.status}`);
  } catch (error) {
    body.innerHTML = card({ title: "Not available", body: `<p class="small muted">${escapeHtml(error.message)}. Start Postgres, then run <code>python -m opslens.rag build</code>.</p>` });
    return;
  }
  body.innerHTML = [howItWorks(d.index), retrieval(d.rag_retrieval), reading(d.rag_classification)].join("");
}

function howItWorks(index) {
  const rows = (index.sources || []).map((s) => `<tr><td>${escapeHtml(s.label)}</td><td class="num">${s.n}</td>
      <td class="num">${s.embedded === s.n ? "yes" : `${s.embedded} of ${s.n}`}</td></tr>`).join("");
  return card({
    title: "What the AI can look things up in",
    sub: `${index.chunks} pieces in Postgres, each stored with its meaning (nomic-embed-text on this laptop)`,
    body: `<ol class="small" style="margin:0 0 12px 18px;line-height:1.7">
        <li>Your question is turned into numbers that capture its meaning.</li>
        <li>OpsLens finds the 5 closest pieces, by meaning and by exact words together (past tickets count a little less than rules and results).</li>
        <li>The local AI (qwen2.5:3b) writes the answer from those pieces only, with [1] [2] citations.</li>
        <li>Every number in the answer must appear in the pieces; if not, the AI is asked again. Off-topic questions get "I don't know".</li>
      </ol>
      <div class="table-wrap"><table><thead><tr><th>Source</th><th class="num">Pieces</th><th class="num">Meaning stored</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="small muted">Try it: open <b>Ask OpsLens AI</b> in the sidebar. Every written answer lists its sources with Open links.</p>`,
  });
}

function retrieval(r) {
  if (!r) return card({ title: "Does it find the right source?", body: `<p class="small muted">Run <code>python -m opslens.rag eval</code>.</p>` });
  const bars = MODES.map(([key, label]) => {
    const m = r.modes[key];
    return `<div class="mini-bar"><span>${escapeHtml(label)}</span>
      <div class="cbar-track"><div class="cbar-fill ${key === "both" ? "is-good" : "is-normal"}" style="width:${Math.round(m.hit_at_1 * 100)}%"></div></div>
      <span class="cbar-value">${pct(m.hit_at_1, 0)} first · ${pct(m.hit_at_3, 0)} top 3</span></div>`;
  }).join("");
  return card({
    title: "Does it find the right source?",
    sub: `${r.questions} test questions written in different words from the sources (config/rag_eval.yaml)`,
    body: `<div class="stat-row">${stat("Right source first", pct(r.hit_at_1, 0))}${stat("Right source in the top 3", pct(r.hit_at_3, 0))}${stat("Mean reciprocal rank", r.mrr.toFixed(2))}</div>
      <div class="finding-bars" style="margin-top:12px">${bars}</div>
      <p class="small muted">Searching by meaning and words together beats either one alone. Re-run with <code>python -m opslens.rag eval</code>.</p>`,
  });
}

function reading(c) {
  if (!c) return card({ title: "Does retrieval help the AI read tickets?", body: `<p class="small muted">Run <code>python scripts/eval_rag_classify.py</code>.</p>` });
  const s = c.sample, g = c.routing;
  const better = s.llm_with_examples > s.llm_alone_recorded;
  const routeRow = (label, acc, fixed, broke) => `<tr><td>${label}</td><td class="num">${pct(acc, 2)}</td>
      <td class="num">${fixed ?? "—"}</td><td class="num">${broke ?? "—"}</td></tr>`;
  const ex = g.llm_with_examples, kn = g.nearest_tickets_vote;
  const gained = Math.round((kn.accuracy - g.classifier_alone) * c.test_tickets);
  const verdict = [
    ex.accuracy > g.classifier_alone
      ? `With retrieved examples, letting the AI correct the classifier now helps: ${pct(ex.accuracy, 2)} against ${pct(g.classifier_alone, 2)} for the classifier alone.`
      : `Retrieved examples halve the damage the AI does (it broke ${ex.broke} correct tickets instead of ${g.llm_alone_broke_recorded}), but it still does not beat the classifier alone (${pct(ex.accuracy, 2)} vs ${pct(g.classifier_alone, 2)}).`,
    gained > 0
      ? `A plain vote of the 5 nearest past tickets edges past the classifier by ${gained} tickets out of ${c.test_tickets.toLocaleString()}: too small to change routing, so routing stays as tested and the AI stays a second opinion.`
      : "No retrieval variant beats the classifier alone, so routing stays as tested and the AI stays a second opinion.",
  ].join(" ");
  return card({
    title: "Does retrieval help the AI read tickets?",
    sub: `Before deciding, the AI is shown the ${c.examples_per_ticket} most similar past tickets with their correct category (from ${c.example_pool.tickets.toLocaleString()} tickets of the training days only)`,
    body: `<div class="stat-row">${stat("AI alone", pct(s.llm_alone_recorded, 2), "400 test tickets")}
        ${stat("AI with retrieved examples", pct(s.llm_with_examples, 2), `${better ? "better" : "not better"} on the same 400`)}
        ${stat("Vote of the 5 nearest tickets", pct(s.nearest_tickets_vote, 2), "no AI at all")}</div>
      <h4 style="margin:16px 0 6px">Routing, when the AI may correct the classifier on its ${g.hard_tickets} least sure tickets</h4>
      <div class="table-wrap"><table><thead><tr><th>How the hard tickets are read</th><th class="num">Routing accuracy</th><th class="num">Fixed</th><th class="num">Broke</th></tr></thead><tbody>
        ${routeRow("Classifier alone", g.classifier_alone, "", "")}
        ${routeRow("AI alone (measured before)", g.llm_alone_recorded, g.llm_alone_fixed_recorded, g.llm_alone_broke_recorded)}
        ${routeRow("Vote of the 5 nearest tickets", kn.accuracy, kn.fixed, kn.broke)}
        ${routeRow("AI with 5 retrieved examples", ex.accuracy, ex.fixed, ex.broke)}
      </tbody></table></div>
      <p class="small">${escapeHtml(verdict)}</p>
      <p class="small muted">Same held-out test tickets as before; examples come only from the training days. Re-run with <code>python scripts/eval_rag_classify.py</code>.</p>`,
  });
}
