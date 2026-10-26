export const state = {
  results: null,
  source: "",
  whatif: null,
  plant: null,
  upload: null,
  uploadpeek: null,
  uploadMeta: null,
  staticServer: false,
  world: readStored("opslens-world", "food"),
  realSource: readSession("opslens-real-source", "uci"),
  plan: readStored("opslens-plan", {}),
  planimpact: null,
  live: null,
  role: readStored("opslens-role", "lead"),
  agent: readStored("opslens-agent", null),
  feedback: readStored("opslens-agent-feedback", []),
};

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
  }
}

export function readSession(key, fallback) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch (error) {
    return fallback;
  }
}

export function storeSession(key, value) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
  }
}

export async function loadResults() {
  state.staticServer = await servedByStaticServer();
  if (!state.staticServer) {
    try {
      const response = await fetch("/api/results", { cache: "no-store" });
      if (response.ok) {
        return { data: await response.json(), source: "/api/results" };
      }
    } catch (error) {
    }
  }
  const response = await fetch("../eval/fixture_results.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Could not load ../eval/fixture_results.json (HTTP " + response.status + ")");
  }
  return { data: await response.json(), source: "eval/fixture_results.json" };
}

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

export const LIVE_SOURCES = {
  whatif: "POST /api/whatif (live simulation)",
  plant: "POST /api/plant (live detection on fresh data)",
  upload: "GET /api/anyfile/job (OpsLens on your file: learned on its first 70%, scored on the rest)",
  uploadpeek: "POST /api/anyfile/peek (your file as the server read it; nothing learned yet)",
  planimpact: "POST /api/plan/impact (live simulation of your plan)",
  live: "GET /api/live (today's day, simulated on this laptop, at your clock)",
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

export function policyKeys() {
  const sim = state.results && state.results.sim;
  return sim ? Object.keys(sim.policies) : [];
}

const PLAIN_NAMES = {
  baseline_a: "First come, first served",
  baseline_b: "Urgent first",
  baseline_c: "Due time first",
  baseline_d: "Industry standard",
  least_slack: "Least slack first",
  opslens: "OpsLens",
};

export function policyLabel(key) {
  if (PLAIN_NAMES[key]) return PLAIN_NAMES[key];
  const sim = state.results && state.results.sim;
  if (sim && sim.policies[key]) {
    return sim.policies[key].label;
  }
  return key;
}

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
