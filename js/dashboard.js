// Loads each Vega-Lite spec from js/specs/, swaps "@name" colour tokens for
// DASH.colors values, applies the shared config and embeds it.
// Every element with data-spec="<file>" becomes a chart.

function resolveTokens(node) {
  if (typeof node === "string") {
    return node.startsWith("@") && node.slice(1) in DASH.colors ? DASH.colors[node.slice(1)] : node;
  }
  if (Array.isArray(node)) return node.map(resolveTokens);
  if (node && typeof node === "object") {
    const out = {};
    for (const [k, v] of Object.entries(node)) out[k] = resolveTokens(v);
    return out;
  }
  return node;
}

async function embedChart(el) {
  const file = el.dataset.spec;
  try {
    const res = await fetch(`js/specs/${file}.json`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const spec = resolveTokens(await res.json());
    spec.config = { ...DASH.vlConfig, ...(spec.config || {}) };
    await vegaEmbed(el, spec, { actions: false, renderer: "svg" });
  } catch (err) {
    el.innerHTML = `<p class="chart-error">Chart ${file} failed to load: ${err.message}</p>`;
    console.error(file, err);
  }
}

// Fill each card's "N" line from data/prepared/chart_counts.csv so no row count
// is typed by hand.
async function fillCounts() {
  const targets = document.querySelectorAll("[data-n]");
  if (!targets.length) return;
  try {
    const rows = await vega.loader().load("data/prepared/chart_counts.csv");
    const table = vega.read(rows, { type: "csv", parse: "auto" });
    const byChart = Object.fromEntries(table.map((r) => [String(r.chart), r]));
    targets.forEach((el) => {
      const r = byChart[el.dataset.n];
      if (r) el.textContent = `${Number(r.n).toLocaleString("en-GB")} ${el.dataset.unit || "rows"}`;
    });
  } catch (err) {
    console.error("chart_counts.csv", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-spec]").forEach(embedChart);
  fillCounts();
});
