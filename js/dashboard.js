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
    const { view } = await vegaEmbed(el, spec, { actions: false, renderer: "svg" });
    if ("zoom" in el.dataset) enableMapZoom(el, view);
    if (el.dataset.brush) enableRangeBrush(el, view, el.dataset.brush);
    // A .chart.fill (height "container") takes the height its card has left
    // beside a taller card. Vega-Lite re-measures containers only on a window
    // resize, so send one whenever this element changes size.
    if (el.classList.contains("fill")) {
      let frame = 0;
      new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
      }).observe(el);
    }
  } catch (err) {
    el.innerHTML = `<p class="chart-error">Chart ${file} failed to load: ${err.message}</p>`;
    console.error(file, err);
  }
}

// Map zoom and pan on top of the spec's own controls (1_1_map.json). Ctrl +
// scroll zooms at the pointer (a trackpad pinch arrives as Ctrl + wheel) and a
// mouse drag pans. Both write the spec's params map_zoom, pan_x and pan_y, so
// the zoom slider stays in step. Plain scrolling and touch drags are left
// alone so they still scroll the page. Picking a continent or pressing the
// card's Reset button returns to that continent's view.
function enableMapZoom(el, view) {
  const ZOOM_MAX = 8; // the slider's max in the spec
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const s = { zoom: 1, panX: 0, panY: 0 }; // unrounded, so small pinch steps add up
  let frame = 0;

  function apply() {
    frame = 0;
    // keep the view centre within about one world-width of the continent
    const k = view.signal("map_view")[2];
    const mx = (view.width() * k) / 2, my = (view.height() * k) / 2;
    s.panX = clamp(s.panX, -mx, mx);
    s.panY = clamp(s.panY, -my, my);
    view.signal("map_zoom", Math.round(s.zoom * 100) / 100)
      .signal("pan_x", s.panX)
      .signal("pan_y", s.panY)
      .runAsync();
  }
  const schedule = () => { frame ||= requestAnimationFrame(apply); };
  const reset = () => { Object.assign(s, { zoom: 1, panX: 0, panY: 0 }); apply(); };

  // the slider moved
  view.addSignalListener("map_zoom", (_, z) => {
    if (z !== Math.round(s.zoom * 100) / 100) s.zoom = z;
  });
  view.addSignalListener("map_continent", reset);
  el.closest(".card")?.querySelector(".map-reset")?.addEventListener("click", reset);

  el.addEventListener("wheel", (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const z0 = s.zoom;
    const delta = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY; // lines -> pixels
    s.zoom = clamp(z0 * Math.exp(-delta * 0.002), 1, ZOOM_MAX);
    // keep the point under the pointer still: its offset from the plot centre
    const box = el.querySelector("svg").getBoundingClientRect();
    const [ox, oy] = view.origin();
    const dx = e.clientX - box.left - ox - view.width() / 2;
    const dy = e.clientY - box.top - oy - view.height() / 2;
    s.panX += dx / s.zoom - dx / z0;
    s.panY += dy / s.zoom - dy / z0;
    schedule();
  }, { passive: false });

  let last = null;
  el.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" || e.button !== 0) return;
    last = [e.clientX, e.clientY];
    el.setPointerCapture(e.pointerId);
    el.classList.add("dragging");
  });
  el.addEventListener("pointermove", (e) => {
    if (!last) return;
    s.panX += (e.clientX - last[0]) / s.zoom;
    s.panY += (e.clientY - last[1]) / s.zoom;
    last = [e.clientX, e.clientY];
    schedule();
  });
  const endDrag = () => { last = null; el.classList.remove("dragging"); };
  el.addEventListener("pointerup", endDrag);
  el.addEventListener("pointercancel", endDrag);
}

// Time-range brush (2_2_streamgraph.json): the spec's interval param, named in
// data-brush, sets the main view's time range. This keeps the card's readout
// in step with it and wires the card's Reset button.
function enableRangeBrush(el, view, name) {
  const card = el.closest(".card");
  const readout = card?.querySelector(".range-readout");
  const fullText = readout?.textContent;
  const fmt = (v) => new Date(v).toLocaleDateString("en-GB", { month: "short", year: "numeric" });

  // Reset sends the double-click that Vega-Lite's interval selection already
  // clears on, so the brush, its stored range and the main view all reset the
  // same way as a double-click on the chart. (Setting the brush's signals from
  // outside, via view.setState, leaves them out of step.)
  card?.querySelector(".range-reset")?.addEventListener("click", () => {
    el.querySelector("svg, canvas")?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
  });

  view.addSignalListener(name, (_, value) => {
    const range = value && Object.values(value)[0];
    if (readout) readout.textContent = range ? `Showing ${fmt(range[0])} – ${fmt(range[1])}` : fullText;
  });
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

// Table view of a chart's data: <details data-table="<csv>" data-columns=
// "field:Header,...">. Rows keep the CSV's order; numbers are right-aligned.
async function fillTables() {
  for (const el of document.querySelectorAll("[data-table]")) {
    try {
      const rows = vega.read(await vega.loader().load(el.dataset.table), { type: "csv", parse: "auto" });
      const cols = el.dataset.columns.split(",").map((c) => c.split(":"));
      const table = document.createElement("table");
      const head = table.createTHead().insertRow();
      const body = table.createTBody();
      const isNum = (f) => rows.every((r) => typeof r[f] === "number");
      cols.forEach(([f, label]) => {
        const th = document.createElement("th");
        th.textContent = label;
        if (isNum(f)) th.className = "num";
        head.appendChild(th);
      });
      rows.forEach((r) => {
        const tr = body.insertRow();
        cols.forEach(([f]) => {
          const td = tr.insertCell();
          td.textContent = typeof r[f] === "number" ? r[f].toLocaleString("en-GB") : r[f];
          if (isNum(f)) td.className = "num";
        });
      });
      const wrap = document.createElement("div");
      wrap.className = "table-scroll";
      wrap.appendChild(table);
      el.appendChild(wrap);
      el.querySelector("summary").textContent += ` (${rows.length} rows)`;
    } catch (err) {
      console.error(el.dataset.table, err);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-spec]").forEach(embedChart);
  fillCounts();
  fillTables();
});
