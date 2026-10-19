// format.js — how numbers look, what each KPI is called, and what each metric means.
//
// Why one file: the same value must look the same on every tab, and the evidence popover
// needs a one-line definition for every metric. Definitions follow CLAUDE.md section 4.
// This file holds NO result numbers — only words and formatting rules.
//
// Example:
//   fmt(13.0, "pct")        -> "13.0%"
//   fmt(0.92, "frac_pct")   -> "92%"
//   fmtSigned(-8.9, "pts")  -> "−8.9 pts"

const MINUS = "−"; // a real minus sign reads better on a projector than "-"

// Units used by ev() and the charts:
//   pct      value is already a percent (13.0 -> "13.0%")
//   pts      percentage points, for differences and spreads of a pct (1.04 -> "1.0 pts")
//   frac_pct a fraction shown as a percent (0.92 -> "92%")
//   min      minutes; int count; num plain number; ratio two decimals (rho, AUC)
//   hours    agent-hours; sec seconds; ms milliseconds; text a string
//   dur      minutes, shown as min, h or days depending on size (long IT incidents)
// scale multiplies the value; minDigits/maxDigits are decimal places; suffix is the unit text.
const UNIT_RULES = {
  pct: { scale: 1, minDigits: 1, maxDigits: 1, suffix: "%" },
  pts: { scale: 1, minDigits: 1, maxDigits: 1, suffix: " pts" },
  frac_pct: { scale: 100, minDigits: 0, maxDigits: 1, suffix: "%" },
  min: { scale: 1, minDigits: 0, maxDigits: 1, suffix: " min" },
  int: { scale: 1, minDigits: 0, maxDigits: 0, suffix: "" },
  count: { scale: 1, minDigits: 1, maxDigits: 1, suffix: "" }, // a mean count over seeds: "23.7", "15.0"
  ratio: { scale: 1, minDigits: 2, maxDigits: 2, suffix: "" },
  hours: { scale: 1, minDigits: 0, maxDigits: 2, suffix: " h" },
  sec: { scale: 1, minDigits: 0, maxDigits: 1, suffix: " s" },
  ms: { scale: 1, minDigits: 0, maxDigits: 2, suffix: " ms" }, // optimiser steps can be 0.07 ms
  num: { scale: 1, minDigits: 0, maxDigits: 2, suffix: "" },
};

// `bare` drops the unit text, for table cells whose header already names the unit.
export function fmt(value, unit = "num", bare = false) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (typeof value !== "number") {
    return String(value);
  }
  // "dur": minutes shown in the most readable unit (95 min, 6.4 h, 7.4 days).
  if (unit === "dur") {
    if (Math.abs(value) < 120) return fmt(value, "min", bare);
    if (Math.abs(value) < 2880) return num(value / 60, 0, 1) + (bare ? "" : " h");
    return num(value / 1440, 0, 1) + (bare ? "" : " days");
  }
  const rule = UNIT_RULES[unit] || UNIT_RULES.num;
  const scaled = value * rule.scale;
  // Minutes above 100 need no decimals ("816 min", not "816.0 min").
  const maxDigits = unit === "min" && Math.abs(scaled) >= 100 ? 0 : rule.maxDigits;
  const text = num(scaled, Math.min(rule.minDigits, maxDigits), maxDigits);
  return bare ? text : text + rule.suffix;
}

// Like fmt, but always shows the sign: "+0.8 pts", "−8.9 pts".
export function fmtSigned(value, unit = "num", bare = false) {
  if (typeof value !== "number") {
    return fmt(value, unit, bare);
  }
  const text = fmt(Math.abs(value), unit, bare);
  if (!/[1-9]/.test(text)) return text; // rounds to zero: "0", never "−0"
  if (value > 0) return "+" + text;
  if (value < 0) return MINUS + text;
  return text;
}

// The unit text for a table header: "%" for pct, "min" for min, "" when there is none.
export function unitSuffix(unit) {
  const rule = UNIT_RULES[unit] || UNIT_RULES.num;
  return rule.suffix.trim();
}

// The unit of a value found at `path`, for places that render arbitrary paths (the brief).
export function unitForPath(path) {
  const kpi = path.match(/kpis\.(.+)\.(mean|std)$/);
  if (kpi) {
    return kpiInfo(kpi[1]).unit;
  }
  const parts = path.replace(/\[\d+\]/g, "").split(".").filter((p) => p !== "mean" && p !== "std");
  return unitForKey(parts[parts.length - 1]);
}

// The unit for a spread or difference of a value in `unit` (a spread of 13.0% is "1.0 pts").
export function spreadUnit(unit) {
  return unit === "pct" ? "pts" : unit;
}

// "2026-10-16T00:22:40" -> "16 Oct 2026, 00:22" (only the look changes; the popover keeps the raw value).
export function fmtDateTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) + ", " + String(iso).slice(11, 16);
}

// Indian digit grouping (1,00,000) because the judges are in India.
function num(value, minDigits, maxDigits) {
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: minDigits,
    maximumFractionDigits: maxDigits,
  });
}

// Guess a unit from a key name, for generic tables (sensitivity, stress, speed).
export function unitForKey(key) {
  if (/_pct$/.test(key)) return "pct";
  if (/_min$|_wait$/.test(key)) return "min";
  if (/_ms$|^ms_|_ms_/.test(key)) return "ms";
  if (/seconds$/.test(key)) return "sec";
  if (/^(tickets|agents|n|sets)$/.test(key)) return "int";
  return "num";
}

// "gold_breach_pct" -> "Gold breach %"
export function prettyKey(key) {
  const words = key.replace(/_pct$/, " %").replace(/_min$/, " (min)").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// Every text we put into innerHTML goes through this, because ticket texts are user input.
export function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// The KPI groups, in the words of the problem statement:
// "turnaround time, productivity, and service quality".
export const KPI_GROUPS = {
  turnaround: "Turnaround",
  productivity: "Productivity",
  quality: "Service quality",
  segment: "Customer segments (who is protected)",
};

// Label, unit and direction for each simulator KPI. A KPI that is missing here still shows,
// with a label made from its key (see kpiInfo), so a new KPI from the engine never vanishes.
export const KPIS = {
  "turnaround.breach_pct": { label: "Missed promises (SLA breach rate)", unit: "pct", better: "lower" },
  "turnaround.mean_resolution_min": { label: "Average time to solve", unit: "min", better: "lower" },
  "turnaround.p90_resolution_min": { label: "Time to solve 9 in 10 tickets (P90)", unit: "min", better: "lower" },
  "turnaround.mean_wait_min": { label: "Average wait for an agent", unit: "min", better: "lower" },
  "turnaround.max_backlog": { label: "Longest queue (tickets)", unit: "int", better: "lower" },
  "productivity.tickets_per_agent_hour": { label: "Tickets per agent-hour", unit: "num", better: "higher" },
  "productivity.transfers_per_100": { label: "Sent to the wrong team, per 100 tickets", unit: "num", better: "lower" },
  "productivity.busy_agent_hours": { label: "Busy agent-hours", unit: "int", better: null }, // more or less is not clearly better
  "quality.reopen_rate_pct": { label: "Customers who came back (reopen rate)", unit: "pct", better: "lower" },
  "quality.p99_wait_min": { label: "Wait of the unluckiest 1 in 100 (P99)", unit: "min", better: "lower" },
  "quality.late_minutes_per_100": { label: "Minutes past the promise, per 100 tickets", unit: "int", better: "lower" },
  "quality.mean_minutes_late": { label: "How late, on average, when late", unit: "min", better: "lower" },
  "quality.p90_minutes_late": { label: "How late, 9 in 10 late tickets (P90)", unit: "min", better: "lower" },
  "quality.max_wait_min": { label: "Max wait", unit: "min", better: "lower" },
  "quality.mean_utilisation": { label: "How busy agents are (utilisation)", unit: "ratio", better: null },
  "quality.load_fairness_std": { label: "Workload spread between agents (lower = fairer)", unit: "ratio", better: "lower" },
  "segment.p1_breach_pct": { label: "Missed promises: live orders (P1)", unit: "pct", better: "lower" },
  "segment.gold_breach_pct": { label: "Missed promises: gold customers", unit: "pct", better: "lower" },
  "segment.hindi_breach_pct": { label: "Missed promises: Hindi-speaking customers", unit: "pct", better: "lower" },
  tickets: { label: "Tickets that day", unit: "int", better: null },
};

export function kpiInfo(kpiKey) {
  if (KPIS[kpiKey]) {
    return KPIS[kpiKey];
  }
  const short = kpiKey.split(".").pop();
  return { label: prettyKey(short), unit: unitForKey(short), better: null };
}

// One-line definitions for the evidence popover, keyed by the last part of a path.
// Wording from CLAUDE.md section 4. No result numbers here — only definitions.
export const DEFINITIONS = {
  breach_pct: "SLA breach = resolution time longer than the SLA for the ticket's priority. This is the share of tickets that breached.",
  gold_breach_pct: "Breach rate for gold-tier customers only.",
  p1_breach_pct: "Breach rate for P1 tickets only (live orders: late, payment debited, missing at the door).",
  hindi_breach_pct: "Breach rate for Hindi tickets only (the planted skill gap: few agents speak Hindi and know refunds).",
  after_first_pickup: "Average minutes from the end of the first handling to resolution: transfers, second waits and reopens.",
  peak_gap_agents: "The most agents missing in any one hour of this window (forecast upper band vs roster, Erlang C).",
  agent_hours_short: "Agent-hours missing over the whole window (forecast upper band vs roster, Erlang C).",
  diagnosed_pct: "Share of planted problems found AND given the right cause type (skill gap, capacity, ...).",
  unplanted_cards_per_set: "Average evidence cards per random set that match no plant (real patterns in the data, or false alarms).",
  clean_set_cards: "Evidence cards produced on a data set with nothing planted.",
  diagnosed: "Planted problems found with the right cause type.",
  live_false_alerts_per_week: "Live hourly alerts per week that matched no real spike.",
  wape_noise_floor: "The WAPE a perfect forecast of the average would still have, because arrivals are random (Poisson). No model can beat it.",
  wape_team_hour_workload_model: "WAPE of our forecast for team-hour workload (what staffing uses).",
  wape_team_hour_workload_naive: "WAPE of the seasonal-naive forecast for team-hour workload.",
  sale_day_error_pct: "Forecast error on the known sale day, in percent of actual volume.",
  shortage_before: "Agent-hours short in the week before the plan (forecast upper band vs roster, Erlang C).",
  shortage_after: "Agent-hours short in the week after the plan's moves, with the same headcount.",
  opslens_minus_b: "Breach rate of OpsLens minus Baseline B under this stress. Below zero = OpsLens is better.",
  menu_choice_accuracy: "How often the category the customer picked in the menu was right.",
  accuracy_cascade_hinglish: "Cascade accuracy on Hinglish tickets only.",
  misrouted_per_100_menu: "Tickets per 100 sent to the wrong team when routing by the customer's menu choice.",
  misrouted_per_100_opslens: "Tickets per 100 sent to the wrong team when routing by our predicted category.",
  llm_requests_per_million_tickets: "LLM requests needed per million tickets (batches of uncertain tickets only).",
  time_left_auc: "AUC of a simple rule: rank tickets by minutes left to SLA. Our model must beat it.",
  priority_auc: "AUC of a simple rule: rank tickets by priority.",
  priority_rule_auc: "AUC of the 'rank by priority' rule on the real UCI data.",
  agents_on_roster: "Agents on the roster for this simulated day, after your changes.",
  fresh_days: "Days of fresh data generated with the planted problem hidden in them.",
  rows: "Tickets (rows) in the uploaded data.",
  mean_resolution_min: "Resolution (turnaround) time = resolved_at − created_at, averaged over tickets.",
  tickets: "Number of tickets.",
  aging_lost: "Policy v3: a ticket that is already lost keeps only this share of its waiting-time value, so it stops crowding out tickets that can still be saved.",
  guard_queue_limit: "Policy v3: above this many waiting tickets the fairness guard pauses (crisis mode) and the optimiser protects what can still be saved.",
  test_breach_pct: "Breach rate on the test days.",
  aging_per_sla: "How fast a waiting ticket gains priority, in SLA lengths (policy v2).",
  p90_resolution_min: "P90 resolution time: 90% of tickets resolve faster than this.",
  mean_wait_min: "Wait time = first agent pickup − created_at, averaged over tickets.",
  wait_min: "Wait time = first agent pickup − created_at.",
  max_backlog: "The largest number of tickets waiting at the same moment.",
  tickets_per_agent_hour: "Tickets resolved per agent-hour on shift.",
  transfers_per_100: "Transfer = a ticket moved to another team after an agent finds it is in the wrong queue. Counted per 100 tickets.",
  busy_agent_hours: "Total agent-hours spent actively handling tickets.",
  reopen_rate_pct: "Reopen rate = reopens ÷ resolved. A reopen is a customer coming back because the fix did not work.",
  p99_wait_min: "P99 wait: 99% of tickets wait less than this. It shows no ticket is abandoned to game the breach number.",
  max_wait_min: "The longest any single ticket waited.",
  mean_utilisation: "Utilisation ρ = arrival rate ÷ (agents × tickets per agent-hour). ρ above 1 means the backlog grows.",
  load_fairness_std: "Load fairness = standard deviation of agent utilisation. Lower is fairer.",
  mean_diff: "Paired difference (policy − baseline) averaged over seeds. Same seed = same tickets and same luck.",
  ci_low: "Paired 95% CI: the range for (OpsLens − baseline) across seeds; same seed = same luck.",
  ci_high: "Paired 95% CI: the range for (OpsLens − baseline) across seeds; same seed = same luck.",
  n: "Number of seeds (independent simulator runs) in the comparison.",
  waiting: "Tickets waiting in the queue at this moment of the replay.",
  breached_cum: "Tickets that have breached their SLA so far in the replay.",
  value: "The measured value for this segment.",
  comparison_value: "The same metric for the comparison group.",
  affected_tickets: "Number of tickets in this segment over the history window.",
  affected_share_pct: "Share of all tickets that fall in this segment.",
  strength: "How unusual the finding is (robust z or ratio). Robust z = 0.6745 × (x − median) ÷ MAD; flagged when above 3.5.",
  planted: "Problems planted in the generated data. Only the evaluation reads the plant list; the engine never does.",
  found: "Planted problems the engine found on its own.",
  false_alarms: "Findings that match no planted problem (for example, a known sale day flagged by mistake).",
  found_pct: "Blind recall: share of randomly planted problems found, over many random plant sets.",
  false_alarms_mean: "Average false alarms per random plant set.",
  sets: "Number of random plant sets in the blind recall test.",
  live_detection_latency_min: "Detection latency = time from the start of a real spike to our first alert.",
  waiting_decomp: "Average minutes a ticket spends in this stage.",
  accuracy_local: "Share of tickets the local TF-IDF + logistic regression model classifies correctly.",
  accuracy_cascade: "Accuracy of the cascade: local model first, LLM only for low-confidence tickets.",
  accuracy_llm_sample: "Accuracy of the LLM alone on a ticket sample.",
  pct_sent_to_llm: "Share of tickets the local model was unsure about and sent to the LLM.",
  cost_per_million_tickets_usd: "LLM cost to classify one million tickets with the cascade.",
  transfers_avoided_per_100: "Transfers avoided per 100 tickets by routing on the predicted category instead of the customer's pick.",
  size: "Number of tickets in this cluster.",
  wape_model: "WAPE = Σ|forecast − actual| ÷ Σ actual, for our LightGBM forecast. Lower is better.",
  wape_naive: "WAPE of the seasonal-naive baseline (same hour last week).",
  coverage_80: "Coverage = share of actual values that fell inside the 80% conformal interval (should be about 80%).",
  coverage_90: "Coverage = share of actual values that fell inside the 90% conformal interval (should be about 90%).",
  demand_hours: "Forecast agent-hours of work arriving in this hour.",
  lo80: "Lower edge of the 80% conformal interval for demand.",
  hi80: "Upper edge (P80) of the 80% conformal interval. A bottleneck is when this exceeds capacity.",
  capacity_hours: "Agent-hours of capacity scheduled for this team in this hour.",
  actual_hours: "Agent-hours of work that actually arrived.",
  peak_rho: "Peak utilisation ρ in the bottleneck window. Above 1 the queue grows.",
  auc: "AUC = probability a breached ticket gets a higher risk score than a non-breached one.",
  pr_auc: "PR-AUC = area under the precision–recall curve; honest when breaches are rare.",
  top10_precision: "Top-10% precision = share of the 10% riskiest tickets that actually breached.",
  brier: "Brier score = mean of (predicted probability − outcome)². Lower = better calibrated.",
  base_rate: "Share of all test tickets that breached. A random guess scores this precision.",
  realdata_auc: "AUC of the same risk code on the real UCI ServiceNow incident log (made_sla flag).",
  realdata_n: "Number of real incidents in the UCI check.",
  predicted: "Average predicted breach probability in this bin.",
  observed: "Share of tickets in this bin that actually breached. Close to predicted = well calibrated.",
  probability: "Calibrated probability that this ticket breaches its SLA (LightGBM + isotonic calibration).",
  probability_after_action: "Re-scored probability if the suggested action is taken now.",
  minutes_to_sla: "Minutes left before this ticket breaches its SLA.",
  contribution: "TreeSHAP contribution of this feature, in probability points.",
  agent_value: "Edge value in the optimiser: grows with urgency, breach risk and customer impact, minus skill-mismatch and scarcity penalties.",
  expected_effect: "Change the simulator measured when this staffing move is applied.",
  delta_breach_vs_full: "Breach rate without this part minus breach rate of full OpsLens. Bigger = the part matters more.",
  gold_weight: "How much more a gold-tier ticket counts in the optimiser.",
  pipeline_seconds: "Wall-clock time for the full pipeline.",
  optimizer_ms_median: "Median time the optimiser needs for one decision step.",
  optimizer_ms_max: "Slowest optimiser decision step.",
  agents: "Agents in the scale test.",
  seconds: "Seconds the optimiser took in the scale test.",
  n_tickets: "Tickets in the generated dataset.",
  data_seed: "Random seed of the data generator (same seed = same data).",
  run_seconds: "Time the evaluation run took.",
  seeds: "Simulator seeds. Every policy runs on every seed with the same luck (common random numbers).",
  test_days: "Held-out days. No model, threshold or weight was chosen on them.",
  train_days: "Days used to train models.",
  validation_days: "Days used to choose thresholds and weights.",
  numbers_used: "Paths of the numbers the brief refers to. Code fills them in; the LLM never writes a digit.",
};

// Find the definition for a path: walk its parts from the end and take the first match.
// "sim.policies.opslens.kpis.turnaround.breach_pct.mean" -> DEFINITIONS.breach_pct
export function definitionFor(path) {
  if (path.startsWith("whatif.")) {
    return "Simulated live for your settings. " + definitionFor(path.slice("whatif.".length));
  }
  if (path.startsWith("plant.") || path.startsWith("upload.")) {
    const rest = path.slice(path.indexOf(".") + 1);
    return "Computed live by the server for this request (not part of the results file). " + definitionFor(rest);
  }
  if (/^patterns\.delay_decomposition\./.test(path)) {
    return /after_first_pickup$/.test(path) ? DEFINITIONS.after_first_pickup : DEFINITIONS.waiting_decomp;
  }
  if (/ablations\[\d+\]\.ci_(low|high)$/.test(path)) {
    return "Paired 95% CI of (breach without this part − full OpsLens) across seeds.";
  }
  if (/_p99_wait$/.test(path)) {
    return "P99 wait under this stress: 99% of tickets wait less than this.";
  }
  if (/^details\.design_v2\.rows\[\d+\]\./.test(path)) {
    return "Validation days only: how each candidate policy did, before we looked at the test days again.";
  }
  if (/^recommendations\.assignments\[\d+\]\.value$/.test(path)) {
    return DEFINITIONS.agent_value;
  }
  if (/\.expected_effect\./.test(path)) {
    return DEFINITIONS.expected_effect;
  }
  const parts = path.replace(/\[\d+\]/g, "").split(".");
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i];
    if (part === "mean" || part === "std") continue;
    if (DEFINITIONS[part]) return DEFINITIONS[part];
  }
  return "A value from the results file.";
}

// Food-delivery ticket categories (CLAUDE.md section 5.3). Words only, used by input forms.
export const CATEGORIES = [
  "late_delivery", "missing_item", "wrong_item", "refund",
  "payment_failure", "app_bug", "account", "restaurant_partner",
];
