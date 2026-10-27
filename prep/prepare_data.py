"""Aggregate the raw amateur-astronomy sources into small chart-ready CSVs.

Reads   data/<source>/...           (never modified)
Writes  data/prepared/*.csv         (one file per chart, plus lookups)

Run from the project root:
    py prep/prepare_data.py

Network: on first run this downloads reference files into prep/cache/
(the MPC ObsCodes list, which carries the site codes that data/MPC lost,
the world-atlas 50m and 110m country boundaries used for the spatial join
and the basemap, and the Natural Earth 50m countries table, whose CONTINENT
field world-atlas drops).
"""

import json
import shutil
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data"
OUT = RAW / "prepared"
CACHE = Path(__file__).resolve().parent / "cache"
OUT.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

START, END = pd.Timestamp("2021-01-01"), pd.Timestamp("2025-12-31 23:59:59")
YEARS = range(2021, 2026)

OBSCODES_URL = "https://minorplanetcenter.net/iau/lists/ObsCodes.html"
WORLD50_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"
WORLD110_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"
NE50_URL = ("https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/"
            "geojson/ne_50m_admin_0_countries.geojson")

# world-atlas name -> display name, and COBS name -> display name
ATLAS_DISPLAY = {
    "United States of America": "United States",
    "Czechia": "Czech Republic",
    "Bosnia and Herz.": "Bosnia and Herzegovina",
    "Dominican Rep.": "Dominican Republic",
}
COBS_DISPLAY = {
    "Korea Republic of": "South Korea",
    "Russian Federation": "Russia",
}

counts = []  # (chart, file, n_rows_behind_chart, note)


def fetch(url, path):
    if not path.exists():
        print(f"  downloading {url}")
        urllib.request.urlretrieve(url, path)
    return path


def write(df, name, chart=None, n=None, note=""):
    path = OUT / name
    df.to_csv(path, index=False)
    kb = path.stat().st_size / 1024
    print(f"  {name:32s} {len(df):>7,} rows  {kb:7.1f} KB")
    if chart:
        counts.append((chart, name, int(n if n is not None else len(df)), note))


# --------------------------------------------------------------------------
# TopoJSON point-in-polygon (pandas/numpy only, no geopandas)
# --------------------------------------------------------------------------

def topo_polygons(topo_path):
    """Return [(name, [rings as (k,2) arrays], bbox)] for each country."""
    topo = json.loads(Path(topo_path).read_text(encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        a = np.cumsum(np.array(arc, dtype=float), axis=0)
        arcs.append(np.column_stack([a[:, 0] * sx + tx, a[:, 1] * sy + ty]))

    def ring(idx):
        pts = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.append(a if not pts else a[1:])
        return np.vstack(pts)

    out = []
    for g in topo["objects"]["countries"]["geometries"]:
        polys = g.get("arcs", [])
        if g["type"] == "Polygon":
            polys = [polys]
        elif g["type"] != "MultiPolygon":
            continue
        rings = [[ring(r) for r in poly] for poly in polys]
        allpts = np.vstack([r for poly in rings for r in poly])
        bbox = (*allpts.min(axis=0), *allpts.max(axis=0))
        out.append((g["properties"]["name"], rings, bbox))
    return out


def in_ring(x, y, r):
    """Vectorised even-odd ray casting for points (x, y) against one ring."""
    x1, y1 = r[:-1, 0], r[:-1, 1]
    x2, y2 = r[1:, 0], r[1:, 1]
    X, Y = x[:, None], y[:, None]
    cond = (y1 > Y) != (y2 > Y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = (x2 - x1) * (Y - y1) / (y2 - y1) + x1
    return (cond & (X < xint)).sum(axis=1) % 2 == 1


def assign_country(lon, lat, countries, max_km=150):
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    result = np.full(len(lon), None, dtype=object)
    for name, polys, (bx0, by0, bx1, by1) in countries:
        m = (result == None) & (lon >= bx0) & (lon <= bx1) & (lat >= by0) & (lat <= by1)  # noqa: E711
        if not m.any():
            continue
        idx = np.where(m)[0]
        hit = np.zeros(len(idx), bool)
        for poly in polys:
            inside = in_ring(lon[idx], lat[idx], poly[0])
            for hole in poly[1:]:
                inside &= ~in_ring(lon[idx], lat[idx], hole)
            hit |= inside
        result[idx[hit]] = name
    # coastal / island sites that fall just outside the 50m outline:
    # nearest boundary vertex within max_km
    miss = np.where(result == None)[0]  # noqa: E711
    fallback = 0
    if len(miss):
        verts, owner = [], []
        for name, polys, _ in countries:
            for poly in polys:
                verts.append(poly[0])
                owner += [name] * len(poly[0])
        verts = np.radians(np.vstack(verts))
        owner = np.array(owner, dtype=object)
        for i in miss:
            p0, l0 = np.radians(lat[i]), np.radians(lon[i])
            dlat, dlon = verts[:, 1] - p0, verts[:, 0] - l0
            h = np.sin(dlat / 2) ** 2 + np.cos(p0) * np.cos(verts[:, 1]) * np.sin(dlon / 2) ** 2
            d = 2 * 6371 * np.arcsin(np.sqrt(h))
            j = d.argmin()
            if d[j] <= max_km:
                result[i] = owner[j]
                fallback += 1
    return result, fallback


def atlas_continents(topo):
    """world-atlas country name -> Natural Earth CONTINENT.

    world-atlas is built from Natural Earth but keeps only the name, so the
    continent is joined back by name, falling back to the ISO numeric id
    (world-atlas still says "Macedonia" where Natural Earth 5 has a new name).
    """
    ne = json.loads(fetch(NE50_URL, CACHE / "ne_50m_admin_0_countries.geojson")
                    .read_text(encoding="utf-8"))
    by_name = {f["properties"]["NAME"]: f["properties"]["CONTINENT"] for f in ne["features"]}
    by_id = {str(f["properties"]["ISO_N3"]): f["properties"]["CONTINENT"] for f in ne["features"]}
    out = {}
    for g in topo["objects"]["countries"]["geometries"]:
        name = g["properties"]["name"]
        out[name] = by_name.get(name) or by_id.get(str(g.get("id")))
    missing = [n for n, c in out.items() if c is None]
    assert not missing, f"no Natural Earth continent for {missing}"
    return out


def ne_continent_by_name():
    """Any Natural Earth name form (NAME, ADMIN, NAME_LONG, ...) -> CONTINENT.

    Earlier fields win, so "France" is France (Europe), not the French Southern
    Lands whose SOVEREIGNT is also France.
    """
    ne = json.loads(fetch(NE50_URL, CACHE / "ne_50m_admin_0_countries.geojson")
                    .read_text(encoding="utf-8"))
    out = {}
    for key in ["NAME", "ADMIN", "NAME_LONG", "NAME_EN", "BRK_NAME", "FORMAL_EN", "NAME_SORT", "GEOUNIT"]:
        for f in ne["features"]:
            name = f["properties"].get(key)
            if name:
                out.setdefault(name, f["properties"]["CONTINENT"])
    return out


# Globe at Night country names that no Natural Earth name form matches
GAN_CONTINENT = {"Macedonia": "Europe", "Virgin Islands": "North America",
                 "St Kitts and Nevis": "North America", "Guadeloupe": "North America"}


def write_basemap():
    """world-atlas 110m basemap with a continent property on every country."""
    topo = json.loads(fetch(WORLD110_URL, CACHE / "countries-110m.json").read_text(encoding="utf-8"))
    cont = atlas_continents(topo)
    for g in topo["objects"]["countries"]["geometries"]:
        g["properties"]["continent"] = cont[g["properties"]["name"]]
    path = OUT / "world-110m.json"
    path.write_text(json.dumps(topo, separators=(",", ":")), encoding="utf-8")
    print(f"  {'world-110m.json':32s} {len(cont):>7,} countries {path.stat().st_size / 1024:6.1f} KB")


# --------------------------------------------------------------------------
# MPC observatory sites
# --------------------------------------------------------------------------

def prep_mpc():
    print("\nMPC")
    sites = pd.read_csv(RAW / "MPC" / "mpc_sites.csv")
    html = fetch(OBSCODES_URL, CACHE / "ObsCodes.html").read_text(encoding="utf-8")
    rows = []
    for line in html.splitlines():
        if len(line) < 30 or line.startswith(("Code", "<")):
            continue
        rows.append({"code": line[0:3], "lon_east": line[4:13].strip(),
                     "rho_cos": line[13:21].strip(), "rho_sin": line[21:30].strip(),
                     "Name": line[30:].strip()})
    codes = pd.DataFrame(rows)
    for c in ["lon_east", "rho_cos", "rho_sin"]:
        codes[c] = pd.to_numeric(codes[c], errors="coerce")
    # join on name + rounded parallax constants (the same values convert.py used)
    key = lambda d: (d["Name"].str.strip() + "|" + d["lon_east"].round(4).astype(str) + "|"
                     + d["rho_cos"].round(5).astype(str) + "|" + d["rho_sin"].round(5).astype(str))
    codes["k"], sites["k"] = key(codes), key(sites)
    codes = codes.drop_duplicates("k")
    sites = sites.merge(codes[["k", "code"]], on="k", how="left")
    print(f"  sites {len(sites):,}, matched to a code {sites.code.notna().sum():,}")
    assert sites.code.notna().all(), "some MPC sites did not match an ObsCodes entry"

    world50 = fetch(WORLD50_URL, CACHE / "countries-50m.json")
    world = topo_polygons(world50)
    country, fallback = assign_country(sites.lon, sites.lat, world)
    sites["country"] = pd.Series(country).replace(ATLAS_DISPLAY)
    print(f"  country assigned {sites.country.notna().sum():,} "
          f"(of which {fallback} by nearest coastline within 150 km), "
          f"unassigned {sites.country.isna().sum()}")

    # continent = Natural Earth continent of the site's country, so Russia is
    # Europe and overseas territories follow their country. Sites outside every
    # outline (Antarctic plateau, open sea) take the continent of the nearest one.
    home = pd.Series(country)
    lost = home.isna()
    home[lost], _ = assign_country(sites.lon[lost], sites.lat[lost], world, max_km=np.inf)
    sites["continent"] = home.map(atlas_continents(json.loads(world50.read_text(encoding="utf-8"))))
    print("  continent " + ", ".join(f"{k} {v}" for k, v in sites.continent.value_counts().items()))
    print("  sites with no country: "
          + "; ".join(f"{r.Name} -> {r.continent}" for r in sites[lost].itertuples()))

    out = sites.rename(columns={"Name": "name"})[["code", "name", "lat", "lon", "country", "continent"]]
    out["lat"], out["lon"] = out.lat.round(3), out.lon.round(3)
    write(out, "mpc_sites.csv", "1.1", note="MPC sites with valid parallax constants")
    return out


# --------------------------------------------------------------------------
# COBS
# --------------------------------------------------------------------------

def prep_cobs(mpc):
    print("\nCOBS")
    raw = pd.read_csv(RAW / "cobs" / "cobs.csv", parse_dates=["date"])
    cobs = raw[(raw.date >= START) & (raw.date <= END)].copy()
    print(f"  raw {len(raw):,}, in 2021-2025 by observation date {len(cobs):,}")
    cobs["country"] = cobs.country.replace(COBS_DISPLAY)
    cobs["day"] = cobs.date.dt.normalize()

    # 1.2 ridgeline: aperture per instrument type, types with >= 200 observations
    inst = cobs.groupby("instrument").size()
    keep = inst[inst >= 200].index
    ap = (cobs[cobs.instrument.isin(keep)]
          .groupby(["instrument", "aperture_cm"]).size().rename("n").reset_index())
    ap["obs_total"] = ap.instrument.map(inst)
    write(ap, "cobs_aperture.csv", "1.2", ap.n.sum(),
          f"{len(keep)} instrument types with >= 200 observations")

    # 1.3 scatter: MPC sites per country vs distinct COBS observers per country
    sites_c = mpc.dropna(subset=["country"]).groupby("country").size().rename("sites")
    obs_c = cobs.groupby("country").observer_code.nunique().rename("observers")
    sc = pd.concat([sites_c, obs_c], axis=1).reset_index().rename(columns={"index": "country"})
    both = sc.dropna().astype({"sites": int, "observers": int})
    only_cobs = sc[sc.sites.isna()].country.tolist()
    print(f"  countries with sites and observers {len(both)}; COBS-only {only_cobs}")
    both = both.sort_values("sites", ascending=False)
    # label the top 10 by geometric mean of the two axes (distance along the log-log diagonal)
    gm = np.sqrt(both.sites * both.observers)
    both["label"] = gm.rank(ascending=False, method="first") <= 10
    # continent comes with the country (Natural Earth, see prep_mpc)
    both["continent"] = both.country.map(mpc.dropna(subset=["country"]).groupby("country").continent.first())
    assert both.continent.notna().all()
    print("  continents " + ", ".join(f"{k} {v}" for k, v in both.continent.value_counts().items()))
    write(both, "country_sites_observers.csv", "1.3", len(both),
          "countries present in both MPC (spatial join) and COBS")

    # 2.1 Lorenz curve
    per = cobs.groupby("observer_code").size().sort_values().reset_index(name="obs")
    per["rank"] = np.arange(1, len(per) + 1)
    per["cum_observers"] = per["rank"] / len(per)
    per["cum_obs"] = per.obs.cumsum() / per.obs.sum()
    lor = pd.concat([pd.DataFrame({"rank": [0], "obs": [0], "cum_observers": [0.0], "cum_obs": [0.0]}),
                     per[["rank", "obs", "cum_observers", "cum_obs"]]])
    n_obs = len(per)
    lor["p90"] = lor["rank"] == (n_obs - int(round(0.1 * n_obs)))
    lor["cum_observers"], lor["cum_obs"] = lor.cum_observers.round(5), lor.cum_obs.round(5)
    top10_share = per.obs.iloc[-int(round(0.1 * n_obs)):].sum() / per.obs.sum()
    print(f"  observers {n_obs}; top 10% ({int(round(0.1 * n_obs))}) file {top10_share:.1%}")
    write(lor, "cobs_lorenz.csv", "2.1", per.obs.sum(), f"{n_obs} observers")

    # 2.2 streamgraph: monthly observations, top 8 comets + Other
    top8 = cobs.comet_name.value_counts().head(8).index
    cobs["comet_label"] = np.where(cobs.comet_name.isin(top8), cobs.comet_name, "Other")
    cobs["month"] = cobs.date.dt.to_period("M").dt.to_timestamp()
    st = cobs.groupby(["month", "comet_label"]).size().rename("n")
    full = pd.MultiIndex.from_product(
        [pd.date_range("2021-01-01", "2025-12-01", freq="MS"), list(top8) + ["Other"]],
        names=["month", "comet_label"])
    st = st.reindex(full, fill_value=0).reset_index()
    st["month"] = st.month.dt.strftime("%Y-%m-%d")
    order = {c: i for i, c in enumerate(list(top8) + ["Other"])}
    st["order"] = st.comet_label.map(order)  # colour slot: rank by total observations
    # stream layout: Other in the centre, comets alternate below/above it by peak month
    peak = (st[st.comet_label != "Other"].sort_values("n", ascending=False)
            .drop_duplicates("comet_label").sort_values("month").comet_label.tolist())
    below, above = peak[0::2], peak[1::2]
    stack = {c: -(i + 1) for i, c in enumerate(below)}
    stack.update({c: i + 1 for i, c in enumerate(above)})
    stack["Other"] = 0
    st["stack_order"] = st.comet_label.map(stack)
    st["side"] = np.where(st.stack_order < 0, "below", "above")
    st["short"] = st.comet_label.str.split("/").str[0].where(
        ~st.comet_label.str.startswith("C/"), st.comet_label.str.split(" ").str[:2].str.join(" "))
    write(st, "cobs_comets_monthly.csv", "2.2", len(cobs), "top 8 comets by observations, rest as Other")

    events = pd.read_csv(OUT / "events.csv", parse_dates=["date"])

    # +-15-day event windows (the same window the 3.3 dumbbell uses). Eclipses are
    # labelled first and comets override, so overlapping days count as comet windows.
    days = pd.date_range("2021-01-01", "2025-12-31", freq="D")
    daily = cobs.groupby("day").size().reindex(days, fill_value=0)
    window = pd.Series("Other days", index=daily.index)
    for kinds, label in [(["lunar eclipse", "solar eclipse"], "Eclipse window"), (["comet"], "Comet window")]:
        for t in events[events.type.isin(kinds)].date:
            window[(window.index >= t - pd.Timedelta(days=15)) & (window.index <= t + pd.Timedelta(days=15))] = label

    # 3.1 daily waffle (draft): one square per day in calendar layout,
    # columns = Monday-based week of the year, rows = weekday (0 = Monday).
    # Also read by the horizon spec 3_1_horizon.json, which only uses date and n.
    dd = daily.rename("n").reset_index().rename(columns={"index": "date"})
    jan1_wd = pd.to_datetime(dd.date.dt.year.astype(str) + "-01-01").dt.weekday
    dd["year"] = dd.date.dt.year
    dd["week"] = (dd.date.dt.dayofyear - 1 + jan1_wd) // 7
    dd["weekday"] = dd.date.dt.weekday
    dd["window"] = window.values
    ev = events.set_index("date")
    dd["event"] = dd.date.map(ev.event).fillna("")
    dd["event_type"] = dd.date.map(ev.type).fillna("")
    dd["date"] = dd.date.dt.strftime("%Y-%m-%d")
    write(dd, "cobs_daily.csv", "3.1", int(dd.n.sum()), "1,826 days, zero-filled, one square per day")

    # 3.1 alternative (waffle pair, kept for switching back): share of days vs
    # share of observations in each window category, 100 squares each
    order = {"Comet window": 0, "Eclipse window": 1, "Other days": 2}
    ew = (pd.DataFrame({"n": daily, "category": window}).groupby("category")
          .agg(days=("n", "size"), obs=("n", "sum")).reset_index())
    ew["order"] = ew.category.map(order)
    ew = ew.sort_values("order").reset_index(drop=True)
    ew["obs_per_day"] = (ew.obs / ew.days).round(1)

    def largest_remainder(counts, total=100):
        exact = counts / counts.sum() * total
        squares = np.floor(exact).astype(int)
        short = total - squares.sum()
        squares[(exact - squares).sort_values(ascending=False).index[:short]] += 1
        return squares

    for col in ["days", "obs"]:
        ew[f"share_{col}"] = (ew[col] / ew[col].sum() * 100).round(1)
        ew[f"squares_{col}"] = largest_remainder(ew[col])
    print(ew.to_string(index=False))
    write(ew, "event_windows.csv")

    # 3.3 dumbbell: baseline vs peak per event
    rows = []
    for e in events.itertuples():
        base = daily[(daily.index >= e.date - pd.Timedelta(days=90)) &
                     (daily.index <= e.date - pd.Timedelta(days=30))]
        peak = daily[(daily.index >= e.date - pd.Timedelta(days=15)) &
                     (daily.index <= e.date + pd.Timedelta(days=15))]
        rows.append({"date": e.date.strftime("%Y-%m-%d"), "event": e.event, "type": e.type,
                     "label": f"{e.event}, {e.date.strftime('%b %Y')}",
                     "baseline": round(base.median(), 2), "peak": round(peak.mean(), 2),
                     "baseline_days": len(base), "peak_days": len(peak)})
    db = pd.DataFrame(rows)
    db["gap"] = (db.peak - db.baseline).round(2)
    db["ratio"] = (db.peak / db.baseline.replace(0, np.nan)).round(2)
    db = db.sort_values("gap", ascending=False)
    print(db[["event", "baseline", "peak", "gap"]].to_string(index=False))
    write(db, "event_response.csv", "3.3", int(db.baseline_days.sum() + db.peak_days.sum()),
          "event-days of COBS counts in the baseline and peak windows")

    # 5.x context: method by year (not a chart on its own, kept for prose checks)
    mby = (cobs.assign(year=cobs.date.dt.year)
           .groupby(["year", "type"]).size().unstack(fill_value=0)
           .rename(columns={"V": "visual", "C": "ccd"}).reset_index())
    mby["ccd_share"] = (mby.ccd / (mby.ccd + mby.visual)).round(4)
    write(mby, "cobs_method_by_year.csv")
    return cobs


# --------------------------------------------------------------------------
# GMN (chunked)
# --------------------------------------------------------------------------

def prep_gmn():
    print("\nGMN")
    cols = ["beginning_utc_time", "iau_no", "iau_code", "sol_lon_deg", "num_stat",
            "participating_stations"]
    radial = []
    yearly = []
    peaks = []
    for y in YEARS:
        path = RAW / "GMN" / f"gmn_{y}.csv"
        header = pd.read_csv(path, nrows=0).columns
        use = cols + (["n_stations"] if "n_stations" in header else [])
        total = kept = 0
        stations, ctry = set(), set()
        bins = np.zeros(360, int)
        shower = {}
        for ch in pd.read_csv(path, usecols=use, na_values=["nan"], keep_default_na=True,
                              dtype={"iau_code": str, "participating_stations": str},
                              chunksize=200_000):
            total += len(ch)
            nst = ch["n_stations"] if "n_stations" in ch else ch["num_stat"]
            ch = ch[pd.to_numeric(nst, errors="coerce") >= 2]
            kept += len(ch)
            for s in ch.participating_stations.dropna():
                for code in s.split(","):
                    stations.add(code)
                    ctry.add(code[:2])
            sp = (ch.iau_code == "...") | (ch.iau_no == -1)
            sh = ch[~sp & ch.sol_lon_deg.notna()]
            b = np.floor(sh.sol_lon_deg).astype(int) % 360
            bins += np.bincount(b, minlength=360)
            for code in ["PER", "GEM", "QUA"]:
                bc = np.bincount(np.floor(sh.sol_lon_deg[sh.iau_code == code]).astype(int) % 360,
                                 minlength=360)
                shower[code] = shower.get(code, 0) + bc
        print(f"  {y}: rows {total:,}, >=2 stations {kept:,}, stations {len(stations):,}, "
              f"station countries {len(ctry)}, shower meteors {bins.sum():,}")
        yearly.append({"year": y, "stations": len(stations), "trajectories": kept,
                       "station_countries": len(ctry), "shower_meteors": int(bins.sum())})
        radial.append(pd.DataFrame({"year": y, "sol_lon": np.arange(360), "n": bins}))
        for code, bc in shower.items():
            peaks.append(pd.DataFrame({"shower": code, "year": y, "sol_lon": np.arange(360), "n": bc}))

    yr = pd.DataFrame(yearly)
    write(yr, "gmn_yearly.csv", "5.1", yr.trajectories.sum(), "trajectories seen by >= 2 stations, sporadics kept")
    rad = pd.concat(radial)
    write(rad, "gmn_sollon.csv", "3.2", rad.n.sum(), "shower meteors only, >= 2 stations, 1-degree bins")

    pk = pd.concat(peaks).groupby(["shower", "sol_lon"]).n.sum().reset_index()
    pk = pk.loc[pk.groupby("shower").n.idxmax()]
    names = {"PER": "Perseids", "GEM": "Geminids", "QUA": "Quadrantids"}
    pk["name"] = pk.shower.map(names)
    # the year-ring value at that longitude, for placing the label on the outermost ring
    pk["n_max_year"] = [rad[(rad.sol_lon == s)].n.max() for s in pk.sol_lon]
    write(pk, "gmn_shower_peaks.csv")


# --------------------------------------------------------------------------
# Globe at Night
# --------------------------------------------------------------------------

def prep_gan():
    print("\nGlobe at Night")
    frames = []
    for y in YEARS:
        g = pd.read_csv(RAW / "GlobeAtNight" / f"GaN{y}.csv", low_memory=False,
                        usecols=["ID", "Latitude", "Longitude", "UTDate", "Country",
                                 "LimitingMag", "CloudCover"])
        frames.append(g)
    g = pd.concat(frames).drop_duplicates("ID")
    n0 = len(g)
    g = g[~((g.Latitude == 0) & (g.Longitude == 0))]
    g["year"] = pd.to_datetime(g.UTDate, format="%d/%m/%Y", errors="coerce").dt.year
    g = g[g.year.between(2021, 2025)].astype({"year": int})
    g["country"] = g.Country.astype(str).str.split(" - ").str[0].str.strip()
    g = g[g.country.ne("nan") & g.country.ne("")]
    print(f"  rows {n0:,}, after 0/0 + year + country filters {len(g):,}, "
          f"countries {g.country.nunique()}")
    tot = g.groupby("country").size().sort_values(ascending=False)
    top = tot.head(25).index
    hm = (g[g.country.isin(top)].groupby(["country", "year"]).size()
          .reindex(pd.MultiIndex.from_product([top, list(YEARS)], names=["country", "year"]),
                   fill_value=0).rename("n").reset_index())
    hm["total"] = hm.country.map(tot)
    write(hm, "gan_country_year.csv", "4.1", hm.n.sum(), "top 25 countries by submissions")
    by_year = g.groupby("year").size().rename("n").reset_index()
    write(by_year, "gan_year.csv")

    # 4.3 sky darkness map: clear-sky reports binned to 2-degree squares, mean
    # limiting magnitude (faintest star seen, 0-7; -9999 = not given)
    s = g.copy()
    for c in ["Latitude", "Longitude", "LimitingMag"]:
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s = s[(s.CloudCover == "clear") & s.LimitingMag.between(0, 7)
          & s.Latitude.between(-90, 90) & s.Longitude.between(-180, 180)
          & ~((s.Latitude == 0) & (s.Longitude == 0))]
    # Location check: the continent under the report (Natural Earth, nearest
    # outline when at sea, looked up per 0.25-degree point) must match the
    # continent of the country the report names. A mismatch (an Alabama report
    # placed in Sicily, say) is a location error and is dropped.
    said = ne_continent_by_name() | GAN_CONTINENT
    s["said"] = s.country.map(said)
    assert s.said.notna().all(), f"no continent for {s[s.said.isna()].country.unique()}"
    s["qy"], s["qx"] = (np.floor(s.Latitude * 4) + 0.5) / 4, (np.floor(s.Longitude * 4) + 0.5) / 4
    pts = s[["qy", "qx"]].drop_duplicates().reset_index(drop=True)
    world50 = fetch(WORLD50_URL, CACHE / "countries-50m.json")
    home, _ = assign_country(pts.qx, pts.qy, topo_polygons(world50), max_km=np.inf)
    pts["continent"] = pd.Series(home).map(atlas_continents(json.loads(world50.read_text(encoding="utf-8"))))
    s = s.merge(pts, on=["qy", "qx"])
    bad = s.said != s.continent
    print(f"  4.3 clear-sky reports {len(s):,}; location on another continent than the "
          f"named country {bad.sum():,} ({bad.mean() * 100:.1f}%), dropped; most from "
          + ", ".join(f"{k} {v}" for k, v in s[bad].Country.value_counts().head(3).items()))
    s = s[~bad]
    s["lat0"] = (np.floor(s.Latitude / 2) * 2).astype(int)
    s["lon0"] = (np.floor(s.Longitude / 2) * 2).astype(int)
    mode = lambda x: x.astype(str).mode().iloc[0]  # noqa: E731
    cells = (s.groupby(["lat0", "lon0"])
             .agg(n=("LimitingMag", "size"), lm=("LimitingMag", "mean"),
                  top=("Country", mode), continent=("continent", mode))
             .reset_index())
    cells["lm"] = cells.lm.round(2)
    full = cells[cells.n >= 10]
    print(f"  4.3 clear-sky reports kept {len(s):,} in {len(cells):,} squares; "
          f">= 10 reports {len(full)} squares ({full.n.sum():,} reports)")
    print(f"  4.3 reports at magnitude <= 3: {(s.LimitingMag <= 3).mean() * 100:.1f}%, "
          f">= 5: {(s.LimitingMag >= 5).mean() * 100:.1f}%; "
          f"squares (>= 10) by mean: < 2 {(full.lm < 2).sum()}, >= 5 {(full.lm >= 5).sum()}")
    print("  4.3 continents (squares >= 10): "
          + ", ".join(f"{k} {v}" for k, v in full.continent.value_counts().items())
          + "; all squares: " + ", ".join(f"{k} {v}" for k, v in cells.continent.value_counts().items()))
    cols = ["lat0", "lon0", "n", "lm", "top"]
    print("  4.3 darkest squares (>= 10):\n" + full.nlargest(8, "lm")[cols].to_string(index=False))
    print("  4.3 brightest squares (>= 10):\n" + full.nsmallest(8, "lm")[cols].to_string(index=False))
    write(cells[["lat0", "lon0", "n", "lm", "top", "continent"]], "gan_sky_cells.csv", "4.3",
          len(s), "clear-sky reports, 2-degree squares")


# --------------------------------------------------------------------------
# Night Sky Network clubs + tile grid
# --------------------------------------------------------------------------

# Hand-assigned tile grid (row, col), 0-indexed from the top left. Based on the
# common NPR-style layout, with DC between MD and VA and PR off the south-east.
GRID = """
AK 0 0|ME 0 11
VT 1 10|NH 1 11
WA 2 1|ID 2 2|MT 2 3|ND 2 4|MN 2 5|IL 2 6|WI 2 7|MI 2 8|NY 2 9|RI 2 10|MA 2 11
OR 3 1|NV 3 2|WY 3 3|SD 3 4|IA 3 5|IN 3 6|OH 3 7|PA 3 8|NJ 3 9|CT 3 10
CA 4 1|UT 4 2|CO 4 3|NE 4 4|MO 4 5|KY 4 6|WV 4 7|VA 4 8|MD 4 9|DE 4 10
AZ 5 2|NM 5 3|KS 5 4|AR 5 5|TN 5 6|NC 5 7|SC 5 8|DC 5 9
OK 6 4|LA 6 5|MS 6 6|AL 6 7|GA 6 8
HI 7 0|TX 7 4|FL 7 8
PR 8 11
"""
STATE_NAMES = dict(
    AL="Alabama", AK="Alaska", AZ="Arizona", AR="Arkansas", CA="California", CO="Colorado",
    CT="Connecticut", DE="Delaware", DC="District of Columbia", FL="Florida", GA="Georgia",
    HI="Hawaii", ID="Idaho", IL="Illinois", IN="Indiana", IA="Iowa", KS="Kansas", KY="Kentucky",
    LA="Louisiana", ME="Maine", MD="Maryland", MA="Massachusetts", MI="Michigan", MN="Minnesota",
    MS="Mississippi", MO="Missouri", MT="Montana", NE="Nebraska", NV="Nevada", NH="New Hampshire",
    NJ="New Jersey", NM="New Mexico", NY="New York", NC="North Carolina", ND="North Dakota",
    OH="Ohio", OK="Oklahoma", OR="Oregon", PA="Pennsylvania", RI="Rhode Island",
    SC="South Carolina", SD="South Dakota", TN="Tennessee", TX="Texas", UT="Utah", VT="Vermont",
    VA="Virginia", WA="Washington", WV="West Virginia", WI="Wisconsin", WY="Wyoming",
    PR="Puerto Rico",
)


def prep_clubs():
    print("\nNight Sky Network clubs")
    rows = []
    for line in GRID.strip().splitlines():
        for cell in line.split("|"):
            s, r, c = cell.split()
            rows.append({"state": s, "name": STATE_NAMES[s], "row": int(r), "col": int(c)})
    grid = pd.DataFrame(rows)
    assert grid.state.is_unique and len(grid) == 52, len(grid)
    assert not grid.duplicated(["row", "col"]).any(), "two states share a tile"
    write(grid, "us_state_grid.csv")

    clubs = pd.read_csv(RAW / "clubs" / "us_clubs.csv")
    n = clubs.state.value_counts()
    tiles = grid.assign(clubs=grid.state.map(n).fillna(0).astype(int))
    print(f"  clubs {len(clubs)}, states/territories with clubs {(tiles.clubs > 0).sum()}, "
          f"without {tiles[tiles.clubs == 0].state.tolist()}")
    write(tiles, "us_clubs_by_state.csv", "4.2", len(clubs), "member clubs per state")


# --------------------------------------------------------------------------

def main(steps):
    print("Events")
    ev_src = RAW / "trends" / "raw" / "events.csv"
    if not (OUT / "events.csv").exists():
        shutil.copyfile(ev_src, OUT / "events.csv")
    ev = pd.read_csv(OUT / "events.csv")
    print(f"  events.csv {len(ev)} events")
    counts.append(("events", "events.csv", len(ev), "celestial events 2021-2025"))

    write_basemap()
    mpc = prep_mpc()
    if "cobs" in steps:
        prep_cobs(mpc)
    if "gan" in steps:
        prep_gan()
    if "clubs" in steps:
        prep_clubs()
    if "gmn" in steps:
        prep_gmn()

    meta = pd.DataFrame(counts, columns=["chart", "file", "n", "note"])
    if steps != ALL_STEPS:
        # partial run: keep the counts of the steps that were skipped
        old = pd.read_csv(OUT / "chart_counts.csv", dtype={"chart": str})
        meta = pd.concat([old[~old.chart.isin(meta.chart)], meta])
        meta = meta.sort_values("chart", key=lambda c: c.str.replace("events", "0"))
    write(meta, "chart_counts.csv")
    print("\nRows behind each chart")
    print(meta.to_string(index=False))


ALL_STEPS = {"cobs", "gan", "clubs", "gmn"}

if __name__ == "__main__":
    # py prep/prepare_data.py            all steps
    # py prep/prepare_data.py cobs gan   only those steps (MPC and events always run)
    import sys
    main(set(sys.argv[1:]) or ALL_STEPS)
