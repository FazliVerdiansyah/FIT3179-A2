// Shared Vega-Lite config and colour system, loaded before every spec.
//
// Specs reference colours in two ways, so no hex value lives in a spec:
//   "@cobs", "@ink", ...           replaced by DASH.colors[name] in dashboard.js
//   "scheme": "dash-counts"        registered below with vega.scheme()
//
// Colour rules
//   counts / magnitudes  one sequential blue ramp, everywhere      dash-counts
//   years                one sequential violet ramp, never categorical  dash-years
//   data sources         one fixed hue each (never shown together on one chart)
//   observation method   one fixed hue each
//   no data              neutral grey, outside every scale

const DASH = {
  font: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',

  colors: {
    // ink and chrome
    ink: "#141413",       // primary text, 17.9:1 on white
    ink2: "#4f4e4a",      // secondary text, 8.3:1
    muted: "#6b6a65",     // axis labels, metadata, 5.4:1
    grid: "#e6e5df",
    axis: "#b9b8b0",
    surface: "#ffffff",
    nodata: "#d9d8d2",    // tiles / cells with no records
    other: "#a8a79f",     // the folded "Other" series
    accent: "#1c5cab",    // the one UI accent (section numbers, links)

    // data sources
    mpc: "#2a78d6",
    cobs: "#eb6834",
    gmn: "#1baf7a",
    gan: "#e87ba4",

    // observation method
    visual: "#eda100",
    ccd: "#4a3aa7",

    // dumbbell baseline (a reference value, not a series hue)
    baseline: "#a8a79f",
  },

  // sequential counts: blue 100 -> 700
  counts: ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],

  // years 2021 -> 2025: one violet ramp, light end clears 2:1 on white
  years: ["#b3a8f2", "#8f81e6", "#6b5ad0", "#4a3aa7", "#2c2170"],

  // categorical, fixed order, for the one chart that needs identity (comets)
  categorical: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
};

vega.scheme("dash-counts", DASH.counts);
vega.scheme("dash-years", DASH.years);
vega.scheme("dash-cat", DASH.categorical);

DASH.vlConfig = {
  font: DASH.font,
  background: DASH.colors.surface,
  padding: 4,
  autosize: { type: "fit", contains: "padding" },
  view: { stroke: null },
  title: { anchor: "start", fontSize: 13, fontWeight: 600, color: DASH.colors.ink },
  axis: {
    labelFont: DASH.font,
    titleFont: DASH.font,
    labelFontSize: 11,
    titleFontSize: 11,
    titleFontWeight: 500,
    labelColor: DASH.colors.muted,
    titleColor: DASH.colors.ink2,
    domainColor: DASH.colors.axis,
    tickColor: DASH.colors.axis,
    gridColor: DASH.colors.grid,
    gridWidth: 1,
    labelPadding: 4,
    titlePadding: 8,
  },
  axisY: { domain: false, ticks: false },
  legend: {
    labelFont: DASH.font,
    titleFont: DASH.font,
    labelFontSize: 11,
    titleFontSize: 11,
    titleFontWeight: 500,
    labelColor: DASH.colors.ink2,
    titleColor: DASH.colors.ink2,
    orient: "top",
    direction: "horizontal",
    symbolSize: 80,
  },
  header: {
    labelFont: DASH.font,
    titleFont: DASH.font,
    labelColor: DASH.colors.ink2,
    labelFontSize: 11,
  },
  text: { font: DASH.font, fontSize: 11, color: DASH.colors.ink2 },
  line: { strokeWidth: 2, strokeCap: "round", strokeJoin: "round" },
  point: { size: 64, filled: true },
  circle: { size: 64 },
  rule: { color: DASH.colors.axis },
  range: {
    category: DASH.categorical,
    ramp: DASH.counts,
    heatmap: DASH.counts,
    ordinal: DASH.years,
  },
};
