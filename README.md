# Who looks up? Amateur astronomy, 2021–2025

A single-page Vega-Lite dashboard: 11 charts in five sections on telescope
ownership, observation records, celestial events, community participation and
technology.

## Open the page

Browsers block `fetch()` from `file://`, so serve the folder:

```
py -m http.server 8000
```

then open <http://localhost:8000/>. Vega, Vega-Lite and vega-embed load from
the jsDelivr CDN, so the page needs a network connection.

## Regenerate the data

```
py prep/prepare_data.py              # all steps (GMN takes a few minutes)
py prep/prepare_data.py cobs gan     # only some steps: cobs, gan, clubs, gmn
```

Requires Python 3 with pandas and numpy. Nothing else.

The script reads the raw files in `data/<source>/` and never writes there.
Outputs go to `data/prepared/`, one small CSV per chart, and it prints the row
count of every file. The first run downloads four reference files into
`prep/cache/`:

- `ObsCodes.html` from the Minor Planet Center. `data/MPC/mpc_sites.csv` lost
  its site codes (the fetcher wrote it with `index=False`), so they are joined
  back from this list.
- `countries-50m.json` (world-atlas / Natural Earth) for the spatial join that
  gives each MPC site a country.
- `countries-110m.json` (world-atlas), written to `data/prepared/world-110m.json`
  as the map basemap with a `continent` property added to every country.
- `ne_50m_admin_0_countries.geojson` (Natural Earth 5.1.2) for its `CONTINENT`
  field, which world-atlas drops. It is joined to world-atlas by country name
  (ISO numeric id as fallback). A site's continent is its country's, so Russia
  counts as Europe and overseas territories follow their country; the 3 sites
  outside every country outline take the continent of the nearest one.

### Filters applied

| Source | Filter |
|---|---|
| COBS | observation date 2021-01-01 to 2025-12-31 (the API filtered on submission date) |
| GMN | `num_stat` / `n_stations` ≥ 2; sporadics (`iau_code == "..."` or `iau_no == -1`) dropped for the shower chart, kept for totals; the string `"nan"` read as missing |
| Globe at Night | rows at 0°, 0° dropped; year from `UTDate`; `United States - <State>` merged into United States |
| Globe at Night, map 4.3 | cloud cover `clear` only; `LimitingMag` 0–7 (−9999 = not given). The report's location must lie on the same continent as the country it names (Natural Earth names; 4 GaN-only names mapped in `GAN_CONTINENT`). 901 reports (2.1%) fail this check and are dropped as location errors. Mean magnitude per 2° square, shown where a square has ≥ 10 reports |
| MPC | sites without parallax constants dropped (done in `data/MPC/convert.py`) |

GMN files for 2022–2025 have no `year`, `month`, `n_stations` or `countries`
columns, so the script derives them: year and month from `beginning_utc_time`,
station count from `num_stat`, and country from the two-letter prefix of each
station code.

`data/prepared/events.csv` is a copy of `data/trends/raw/events.csv`: 16 events,
with eclipse dates from Fred Espenak's NASA GSFC catalogue. `data/trends/` holds
no Google Trends exports, so no chart uses it.

## Files

```
index.html               the page: narrative, cards, captions, metadata
css/style.css            layout (12-column grid, one column under 900px)
js/config.js             shared Vega-Lite config and the colour system
js/dashboard.js          loads js/specs/*.json, swaps colour tokens, embeds
js/specs/*.json          one Vega-Lite spec per chart
prep/prepare_data.py     raw data -> data/prepared/
prep/preview.html        dev harness: one spec at a set width (?spec=1_1_map&w=1200)
prep/mobile.html         dev harness: the page in a 390px frame
data/prepared/           chart-ready CSVs, chart_counts.csv, us_state_grid.csv
```

## Colour system

Specs contain no hex values for shared roles. They use `"@name"` tokens
(replaced from `DASH.colors` in `js/config.js`) and the named schemes
`dash-counts` (blue, every count and magnitude) and `dash-years` (violet,
every year encoding). Each data source has one fixed hue: MPC blue, COBS
orange, GMN aqua, Globe at Night magenta. No chart shows two sources at once.
Grey (`@nodata`) marks missing data and sits outside every scale.

Continents (scatter 1.3) have six fixed hues (`@africa` … `@southAmerica`),
chosen from the categorical palette as the six-hue subset that passes the
all-pairs check a scatter needs: normal-vision ΔE ≥ 15.6, worst colour-blind
ΔE 6.9 (red/aqua). That falls in the 6–8 band, so every continent also has
its own shape. Aqua and yellow fall below 3:1 on white, so they go to the two
smallest groups (Oceania, Africa), and the card carries a data table.
The colour follows the continent, so filtering never repaints a point.

## Notes

- Map 1.1 is interactive. The spec declares the controls as Vega-Lite params:
  `map_continent` (a menu) filters the sites and dims the other continents'
  land, and `map_zoom` (a slider) zooms. Picking a continent flies to its entry
  in `map_views`: `[centre longitude, centre latitude, zoom relative to the
  world view]`. `dashboard.js` (`enableMapZoom`) adds Ctrl + scroll to zoom at
  the pointer and mouse drag to pan by writing the same params (`map_zoom`,
  `pan_x`, `pan_y`). Plain scrolling and touch still scroll the page, and phones
  use the menu and slider. The projection sets its scale by hand instead of
  `fit`, because `fit` would override zoom. 5.4133 × 2.6347 is the size of the
  whole Equal Earth globe at scale 1, so `map_base` is the world-fitting scale.
  Cells with no site on the chosen continent keep their full count and are
  drawn at size 0. The size scale's domain therefore stays the same under
  every filter, and a 50-site circle is the same size everywhere.
- Map 4.3 (`4_3_skymap.json`, data `gan_sky_cells.csv`) uses the same
  controls. It declares the same `map_*` params, so the same `enableMapZoom`
  runs on it, and its controls go into `#sky-binds`. Its `map_views` block is a
  copy of 1.1's, so change both together. Each 2° square is built as a GeoJSON
  polygon in the spec (`calculate`, corners clockwise, as d3 expects) and drawn
  with `geoshape`.
- Streamgraph 2.2 has a time-range filter (overview + detail). The main stream
  and the grey strip under it are one `vconcat` spec. Dragging across the
  strip makes the interval param `brush`, and the main view's x domain is
  `{"param": "brush"}`. Each comet's label moves to its peak inside the range;
  comets with fewer than 20 observations in the range get no label, and labels
  that share a month stack. Double-clicking the chart, or the card's Reset
  range button, shows the whole period again. `enableRangeBrush` in
  `dashboard.js` (turned on by `data-brush`) keeps the card's readout in step
  and makes Reset send that double-click. `width: "container"` works on each
  view in a `vconcat` but autosize `fit` does not, so the spec sets
  `autosize: pad`.
- Ridgeline 1.2, Lorenz curve 2.1, dumbbell 3.3 and tile map 4.2 use
  `height: "container"` and `class="chart fill"`. Each takes the height left in
  its card, so it lines up with the taller card beside it (1.3, 2.2, 3.2, 4.1).
  The tile map sizes its tiles from the space (`tile`, `tile_h` in the spec):
  as wide as 12 columns allow, and up to 20% taller than wide to use spare
  height, with every state the same area.
- Radial chart 3.2 has a Year menu (`radial_year`, bound to `#radial-binds`):
  all five rings, or one year's ring alone. The radius scale and the year
  colours stay fixed, so a ring keeps its size and colour. Shower labels come
  from `gmn_shower_peaks.csv`, which has a row per shower for `year` "All" (the
  peak of the five years summed, placed on the outermost ring) and one per
  shower and year (that year's peak, on that year's ring); `ring_n` is the
  ring's value at the label's longitude.
- Scatter 1.3 has its own continent menu (`scatter_continent`, independent of
  the map's) that filters the countries. The axes keep fixed domains, so a
  filter never rescales. The `<details data-table>` under it is filled by
  `fillTables()` in `dashboard.js`, and any card can reuse it.
- Two prepared files back prose rather than a chart:
  `cobs_late2025_comets.csv` (every comet observed in October–December 2025,
  with its share of each month, for the 3.1 caption) and
  `cobs_method_by_year.csv` (camera vs visual COBS observations per year, for
  the closing paragraph).
- The chart N lines are filled at load time from `data/prepared/chart_counts.csv`.
  No row count is typed by hand.
- Claims that go beyond the data are cited inline (Section 5: Vida et al. 2021,
  MNRAS 506, 5046; Western News 2021). Every data source and cited work is
  listed in the References section at the end of the page. Licences: the MPC states none and asks
  for an acknowledgement, and NASA content (the Night Sky Network club list) is
  generally not under US copyright with NASA credited as the source. Both
  acknowledgements are in the page footer.
- Chart 3.1 is a per-day waffle (`js/specs/3_1_daily_waffle.json`, data
  `data/prepared/cobs_daily.csv`): one square per day, calendar layout, ±15-day
  comet and eclipse windows outlined. Two earlier versions are kept for switching
  back by changing `data-spec` on the 3.1 card in `index.html`:
  `3_1_waffle` (share of days vs share of observations, data `event_windows.csv`)
  and `3_1_horizon` (horizon chart, data `cobs_daily.csv`).
- Light theme only.
