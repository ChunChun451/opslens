// data.js — loads the results JSON and reads values out of it by path.
//
// Why: CLAUDE.md says every number on screen comes from eval/results.json. So the UI never
// keeps its own copy of a number. It keeps the whole JSON in `state.results` and reads each
// value by its path at the moment it draws it. The same path is shown in the evidence popover.
//
// Example:
//   getPath(results, "sim.policies.opslens.kpis.turnaround.breach_pct.mean")  -> 4.1
//   getPath(results, "risk.at_risk[0].probability")                         -> 0.92

// One shared place for loaded data. Other files import this object and read from it.
export const state = {
  results: null, // the parsed results JSON
  source: "", // where it came from, shown in the header and the popover
  // The last live answers from the server. They are not in the results file; their numbers
  // are read by "whatif.*", "plant.*" and "upload.*" paths so they are clickable too.
  whatif: null, // POST /api/whatif
  plant: null, // POST /api/plant
  upload: null, // POST /api/upload
  staticServer: false, // true when served by `python -m http.server` (no API at all)
  // Plan v3 (19 Oct): which world the dashboard shows — "food" (simulated food-delivery floor)
  // or "real" (the public UCI ServiceNow service desk) — and the manager's plan: the
  // recommendations they accepted or overrode. Both are remembered in this browser only.
  world: readStored("opslens-world", "food"),
  plan: readStored("opslens-plan", {}),
  planimpact: null, // POST /api/plan/impact (live simulation of the accepted plan)
};

// localStorage can be missing or blocked (private windows); the dashboard must still work.
function readStored(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch (error) {
    return fallback;
  }
}

export function store(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    // Not remembered — fine for a demo.
  }
}

// Try the real server first (M9 adds GET /api/results). When it is not there, use the
// fixture file.
export async function loadResults() {
  state.staticServer = await servedByStaticServer();
  if (!state.staticServer) {
    try {
      const response = await fetch("/api/results", { cache: "no-store" });
      if (response.ok) {
        return { data: await response.json(), source: "/api/results" };
      }
    } catch (error) {
      // Server not reachable: fall through to the fixture file.
    }
  }
  const response = await fetch("../eval/fixture_results.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Could not load ../eval/fixture_results.json (HTTP " + response.status + ")");
  }
  return { data: await response.json(), source: "eval/fixture_results.json" };
}

// Python's static file server (`python -m http.server`, used for previews before M9) has no
// API. Asking it for /api/results would only print a 404 error in the console, so we look at
// the "Server" header of this page and skip straight to the fixture.
// (A plain GET of this small page; Python's server answers HEAD in a way Chrome logs as aborted.)
async function servedByStaticServer() {
  try {
    const response = await fetch(location.href, { cache: "no-store" });
    await response.text();
    const server = response.headers.get("Server") || "";
    return server.startsWith("SimpleHTTP");
  } catch (error) {
    return false;
  }
}

// Read a value by path. Array items use [n]. Some keys contain a dot themselves
// (the KPI key "turnaround.breach_pct"), so at each level we try the longest key first.
export function getPath(root, path) {
  const parts = path.replace(/\[(\d+)\]/g, ".$1").split(".");
  let node = root;
  let i = 0;
  while (i < parts.length) {
    if (node === null || typeof node !== "object") {
      return undefined;
    }
    let found = false;
    for (let j = parts.length; j > i; j--) {
      const key = parts.slice(i, j).join(".");
      if (Object.prototype.hasOwnProperty.call(node, key)) {
        node = node[key];
        i = j;
        found = true;
        break;
      }
    }
    if (!found) {
      return undefined;
    }
  }
  return node;
}

// The one function the rest of the UI uses to read a value.
// Paths that start with a live answer's name read that answer; everything else reads the
// results JSON.
export const LIVE_SOURCES = {
  whatif: "POST /api/whatif (live simulation)",
  plant: "POST /api/plant (live detection on fresh data)",
  upload: "POST /api/upload (live analysis of the uploaded file)",
  planimpact: "POST /api/plan/impact (live simulation of your plan)",
};

export function liveSource(path) {
  const first = path.split(/[.[]/)[0];
  return LIVE_SOURCES[first] ? first : null;
}

export function lookup(path) {
  const live = liveSource(path);
  if (live) {
    return getPath({ [live]: state[live] }, path);
  }
  return getPath(state.results, path);
}

// Policies in the order the JSON lists them (Baseline A, Baseline B, OpsLens).
export function policyKeys() {
  const sim = state.results && state.results.sim;
  return sim ? Object.keys(sim.policies) : [];
}

// Plain names a non-technical judge understands at once (design v3). The results file keeps
// its own labels ("Baseline A (FIFO)"); the evidence popovers still show those paths.
const PLAIN_NAMES = {
  baseline_a: "First come, first served",
  baseline_b: "Urgent first",
  baseline_c: "Due time first",
  baseline_d: "Industry standard",
  opslens: "OpsLens",
};

// "First come, first served" for "baseline_a"; falls back to the results' label, then the key.
export function policyLabel(key) {
  if (PLAIN_NAMES[key]) return PLAIN_NAMES[key];
  const sim = state.results && state.results.sim;
  if (sim && sim.policies[key]) {
    return sim.policies[key].label;
  }
  return key;
}

// Team names, taken from the data (forecast first, then the delay decomposition).
export function teamNames() {
  const r = state.results;
  if (r.forecast && r.forecast.horizon.length) {
    return [...new Set(r.forecast.horizon.map((p) => p.team))].sort();
  }
  if (r.patterns && Object.keys(r.patterns.delay_decomposition).length) {
    return Object.keys(r.patterns.delay_decomposition).sort();
  }
  return [];
}
