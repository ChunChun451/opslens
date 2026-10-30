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
  body.innerHTML = [howItWorks(d.index), retrieval(d.rag_retrieval), faithful(d.rag_faithfulness_before, d.rag_faithfulness_after),
    blend(d.rag_blend), reading(d.rag_classification)].join("");
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

function faithful(before, after) {
  if (!after) return "";
  return card({
    title: "Are the answers worded right?",
    sub: `${after.questions} fact questions, each with words the answer must contain and wrong phrasings it must not (config/rag_faithful.yaml)`,
    body: `<div class="stat-row">${before ? stat("Before the checks", `${before.right} of ${before.questions}`, pct(before.right_pct, 0)) : ""}
        ${stat("Now", `${after.right} of ${after.questions}`, pct(after.right_pct, 0))}${stat("Wrong now", after.wrong, `${after.declined} declined`)}</div>
      <p class="small">Every number in an answer must be in the sources, and a number may only carry a comparison word (longer, fewer, more…)
        the sources give it. "368 minutes longer" is now caught: the sources say 13.0 times longer, and 368 minutes is the whole wait.
        A caught answer is sent back once; if it is still wrong the chatbot says what to check.</p>
      <p class="small muted">With a 3-billion-parameter model and 16 questions, small changes move one or two answers either way; the
        code check is what reliably stops this kind of mistake. Re-run with <code>python -m opslens.rag faith after</code>.</p>`,
  });
}

function blend(b) {
  if (!b) return card({ title: "Does retrieval help read tickets?", body: `<p class="small muted">Run <code>python scripts/eval_rag_blend.py</code>.</p>` });
  const t = b.test, v = b.validation, s = b.chosen_on_validation;
  const wrongBefore = Math.round((1 - t.classifier_alone) * t.tickets), wrongAfter = Math.round((1 - t.with_retrieval) * t.tickets);
  return card({
    title: "Does retrieval help read tickets? Yes",
    sub: `Where the classifier is less than ${Math.round(s.threshold * 100)}% sure, its answer is blended with a vote of the ${s.k} most similar past tickets (${Math.round(s.weight * 100)}% weight), from ${b.pool.tickets.toLocaleString()} tickets of the training days`,
    body: `<div class="stat-row">${stat("Classifier alone", pct(t.classifier_alone, 2), `${t.tickets.toLocaleString()} held-out tickets`)}
        ${stat("With similar past tickets", pct(t.with_retrieval, 2), `${t.net_tickets} more routed right`)}
        ${stat("Wrong team", `${wrongBefore} → ${wrongAfter}`, `${Math.round((1 - wrongAfter / wrongBefore) * 100)}% fewer mistakes`)}</div>
      <p class="small">On the test days it fixed ${t.fixed} tickets and broke ${t.broke}. The settings were chosen on the validation days
        (${pct(v.classifier_alone, 2)} → ${pct(v.with_retrieval, 2)}) and the test days were scored once. The vote alone scores
        ${pct(t.vote_only_same_settings, 2)}: the gain comes from combining it with the classifier.</p>
      <p class="small muted">The simulated floor still routes with the categories frozen in Round 1, so its 8.79% is unchanged; this is a
        measured improvement to reading tickets. Re-run with <code>python scripts/eval_rag_blend.py</code> (about 6 minutes, no AI calls).</p>`,
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
    title: "What did not work: letting the AI read tickets with examples",
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
