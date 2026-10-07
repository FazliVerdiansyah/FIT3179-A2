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
count of every file. The first run downloads two reference files into
`prep/cache/`:

- `ObsCodes.html` from the Minor Planet Center. `data/MPC/mpc_sites.csv` lost
  its site codes (the fetcher wrote it with `index=False`), so they are joined
  back from this list.
- `countries-50m.json` (world-atlas / Natural Earth) for the spatial join that
  gives each MPC site a country. `data/prepared/world-110m.json` is the map
  basemap.

### Filters applied

| Source | Filter |
|---|---|
| COBS | observation date 2021-01-01 to 2025-12-31 (the API filtered on submission date) |
| GMN | `num_stat` / `n_stations` ≥ 2; sporadics (`iau_code == "..."` or `iau_no == -1`) dropped for the shower chart, kept for totals; the string `"nan"` read as missing |
| Globe at Night | rows at 0°, 0° dropped; year from `UTDate`; `United States - <State>` merged into United States |
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

## Notes

- The chart N lines are filled at load time from `data/prepared/chart_counts.csv`.
  No row count is typed by hand.
- Caption claims marked `[VERIFY]` go beyond what the chart shows on its own.
  `[TODO]` marks licence terms that could not be found (MPC, NASA Night Sky Network).
- Light theme only.
