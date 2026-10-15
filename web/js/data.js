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
  whatif: null, // the last What-if answer from the server (M10), read by "whatif.*" paths
  staticServer: false, // true when served by `python -m http.server` (no API at all)
};

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
// "whatif.*" paths read the last What-if answer; everything else reads the results JSON.
export function lookup(path) {
  if (path.startsWith("whatif.")) {
    return getPath({ whatif: state.whatif }, path);
  }
  return getPath(state.results, path);
}

// Policies in the order the JSON lists them (Baseline A, Baseline B, OpsLens).
export function policyKeys() {
  const sim = state.results && state.results.sim;
  return sim ? Object.keys(sim.policies) : [];
}

// "Baseline A (FIFO)" for "baseline_a"; falls back to the key itself.
export function policyLabel(key) {
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
