const MINUS = "−";

const UNIT_RULES = {
  pct: { scale: 1, minDigits: 1, maxDigits: 1, suffix: "%" },
  pts: { scale: 1, minDigits: 1, maxDigits: 1, suffix: " pts" },
  frac_pct: { scale: 100, minDigits: 0, maxDigits: 1, suffix: "%" },
  min: { scale: 1, minDigits: 0, maxDigits: 1, suffix: " min" },
  int: { scale: 1, minDigits: 0, maxDigits: 0, suffix: "" },
  count: { scale: 1, minDigits: 1, maxDigits: 1, suffix: "" },
  ratio: { scale: 1, minDigits: 2, maxDigits: 2, suffix: "" },
  hours: { scale: 1, minDigits: 0, maxDigits: 2, suffix: " h" },
  sec: { scale: 1, minDigits: 0, maxDigits: 1, suffix: " s" },
  ms: { scale: 1, minDigits: 0, maxDigits: 2, suffix: " ms" },
  num: { scale: 1, minDigits: 0, maxDigits: 2, suffix: "" },
};

export function fmt(value, unit = "num", bare = false) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (typeof value !== "number") {
    return String(value);
  }
  if (unit === "dur") {
    if (Math.abs(value) < 120) return fmt(value, "min", bare);
    if (Math.abs(value) < 2880) return num(value / 60, 0, 1) + (bare ? "" : " h");
    return num(value / 1440, 0, 1) + (bare ? "" : " days");
  }
  const rule = UNIT_RULES[unit] || UNIT_RULES.num;
  const scaled = value * rule.scale;
  const maxDigits = unit === "min" && Math.abs(scaled) >= 100 ? 0 : rule.maxDigits;
  const text = num(scaled, Math.min(rule.minDigits, maxDigits), maxDigits);
  return bare ? text : text + rule.suffix;
}

export function fmtSigned(value, unit = "num", bare = false) {
  if (typeof value !== "number") {
    return fmt(value, unit, bare);
  }
  const text = fmt(Math.abs(value), unit, bare);
  if (!/[1-9]/.test(text)) return text;
  if (value > 0) return "+" + text;
  if (value < 0) return MINUS + text;
  return text;
}

export function unitSuffix(unit) {
  const rule = UNIT_RULES[unit] || UNIT_RULES.num;
  return rule.suffix.trim();
}

export function unitForPath(path) {
  const kpi = path.match(/kpis\.(.+)\.(mean|std)$/);
  if (kpi) {
    return kpiInfo(kpi[1]).unit;
  }
  const parts = path.replace(/\[\d+\]/g, "").split(".").filter((p) => p !== "mean" && p !== "std");
  return unitForKey(parts[parts.length - 1]);
}

export function spreadUnit(unit) {
  return unit === "pct" ? "pts" : unit;
}

export function fmtDateTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) + ", " + String(iso).slice(11, 16);
}

function num(value, minDigits, maxDigits) {
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: minDigits,
    maximumFractionDigits: maxDigits,
  });
}

export function unitForKey(key) {
  if (/_pct$/.test(key)) return "pct";
  if (/_min$|_wait$/.test(key)) return "min";
  if (/_ms$|^ms_|_ms_/.test(key)) return "ms";
  if (/seconds$/.test(key)) return "sec";
  if (/^(tickets|agents|n|sets)$/.test(key)) return "int";
  return "num";
}

export function prettyKey(key) {
  const words = key.replace(/_pct$/, " %").replace(/_min$/, " (min)").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function tidyDash(value) {
  return String(value)
    .replace(/\s+—\s+(\d+% of the push)/g, " ($1)")
    .replace(/\s+—\s+/g, ", ");
}

export function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export const KPI_GROUPS = {
  turnaround: "Turnaround",
  productivity: "Productivity",
  quality: "Service quality",
  segment: "Customer segments (who is protected)",
};

export const KPIS = {
  "turnaround.breach_pct": { label: "Missed promises (SLA breach rate)", unit: "pct", better: "lower" },
  "turnaround.mean_resolution_min": { label: "Average time to solve", unit: "min", better: "lower" },
  "turnaround.p90_resolution_min": { label: "Time to solve 9 in 10 tickets (P90)", unit: "min", better: "lower" },
  "turnaround.mean_wait_min": { label: "Average wait for an agent", unit: "min", better: "lower" },
  "turnaround.max_backlog": { label: "Longest queue (tickets)", unit: "int", better: "lower" },
  "productivity.tickets_per_agent_hour": { label: "Tickets per agent-hour", unit: "num", better: "higher" },
  "productivity.transfers_per_100": { label: "Sent to the wrong team, per 100 tickets", unit: "num", better: "lower" },
  "productivity.busy_agent_hours": { label: "Busy agent-hours", unit: "int", better: null },
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

const FILE_DEFINITIONS = {
  caught_pct: "Share of the real misses on your later items that this picker had flagged as they opened. Every picker flags the same share of each day's items.",
  auc: "How well the score ranks: the chance a real miss is scored above an item that was in time. A coin flip scores one half.",
  gap_pts: "OpsLens's share of the real misses caught minus the other picker's, in percentage points.",
  ci: "95% interval of the gap, from resampling whole days of your later items.",
  missed_pct: "Share of items that missed, by the rule shown on screen.",
  median_min: "Half of the items took less than this.",
  p90_min: "Nine in ten items took less than this.",
  items: "Number of items.",
  rows: "Rows in your file.",
  days: "Calendar days with at least one item.",
  risk: "OpsLens's chance that this item misses, known the moment it opened.",
  share: "Share of the push towards a miss that this reason gives, from the model itself (TreeSHAP).",
  flags: "Items each picker flagged that day: the same number for each.",
  misses: "Real misses: your file's own outcomes.",
  wape_learned: "Error of the learned forecast: the sum of |forecast − actual| over the sum of actual, over team-days. Lower is better.",
  wape_same_weekday_last_week: "The same error for \"same weekday last week\" (the forecast is last week's count).",
  forecast: "New items forecast for this team and day, a week ahead.",
  actual: "New items that really came that day.",
  usual_ends: "What this team usually finishes in a day: the median of the four weeks before the forecast.",
  same_weekday_last_week: "New items on the same weekday a week before.",
  items_scored: "New items on the scored days.",
  target_min: "The promised time: an item that takes longer counts as a miss.",
  flag_share_pct: "Each picker flags this share of each day's items, as they open.",
  learns_from_count: "Columns of your file the model learns from: only ones known when an item starts.",
  learn_items: "Items OpsLens learns from: the first part of your file, by start time.",
  test_items: "Items OpsLens is tested on: the later part, which it never sees while learning.",
  seconds: "Time the server took to analyse your file.",
};
const GROUP_DEFINITIONS = {
  learn_pct: "Share of this group's items that missed, on the first part of your file (where the group was found).",
  learn_rest_pct: "Share of all other items that missed, on the first part of your file.",
  test_pct: "Share of this group's items that missed on your later items, which the search never saw.",
  test_rest_pct: "Share of all other items that missed on your later items.",
  gap_ci: "95% interval of (this group's miss rate minus the rest's) on your later items, resampling whole days. Above zero: still true later.",
  test_misses: "Real misses in this group among your later items.",
  learn_items: "Items in this group in the first part of your file.",
  test_items: "Items in this group among your later items.",
  examples: "Items of this group that really missed, among your later items.",
};

function fileDefinition(rest) {
  const key = rest.replace(/\[\d+\]/g, "").split(".").pop();
  if (/^cards\[/.test(rest) && GROUP_DEFINITIONS[key]) return GROUP_DEFINITIONS[key];
  return FILE_DEFINITIONS[key] || "";
}

export function definitionFor(path) {
  if (path.startsWith("whatif.")) {
    return "Simulated live for your settings. " + definitionFor(path.slice("whatif.".length));
  }
  if (path.startsWith("upload.") || path.startsWith("uploadpeek.")) {
    const rest = path.slice(path.indexOf(".") + 1);
    const where = path.startsWith("uploadpeek.") ? "Read from your file by the server; nothing learned yet. "
      : "Computed live by the server on your file (not part of the results file). ";
    return where + (fileDefinition(rest) || definitionFor(rest));
  }
  if (path.startsWith("plant.")) {
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

export const CATEGORIES = [
  "late_delivery", "missing_item", "wrong_item", "refund",
  "payment_failure", "app_bug", "account", "restaurant_partner",
];
