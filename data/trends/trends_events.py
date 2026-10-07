#!/usr/bin/env python3
"""
Google Trends for celestial events: did people search when the sky did
something, and how big was the spike?

Three modes:

  fetch   try pytrends. Best effort only: pytrends was archived in April
          2025 and often returns 429 Too Many Requests.
  merge   turn CSVs downloaded by hand from trends.google.com into tidy
          long format. This always works.
  align   the interesting part. Line every series up against event dates,
          so week 0 is the event, and measure the spike against the
          preceding baseline.

Usage
-----
    python trends_events.py fetch -o trends.csv
    python trends_events.py merge downloads/*.csv -o trends.csv
    python trends_events.py align trends.csv -o aligned.csv
    python trends_events.py events          # print the event list

Manual download, which is the reliable route
--------------------------------------------
  1. https://trends.google.com/trends/explore
  2. Enter one group's terms (5 max per chart)
  3. Date range 2021-01-01 to 2025-12-31, region Worldwide
  4. Download the "Interest over time" chart
  5. Name the file after the group, then run merge

Trends values are relative, scaled 0 to 100 against the peak within one
query. Compare shape and timing, never magnitude across charts.
"""

import argparse
import csv
import glob
import io
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_TIMEFRAME = "2021-01-01 2025-12-31"

# Up to five terms per group: Google compares at most five at once.
# Every group carries an anchor term so the groups stay loosely comparable.
KEYWORD_GROUPS = {
    "eclipse": ["solar eclipse", "lunar eclipse", "eclipse glasses", "blood moon", "stargazing"],
    "meteor": ["meteor shower", "Perseids", "Geminids", "shooting star", "stargazing"],
    "comet": ["comet", "comet tonight", "Tsuchinshan ATLAS", "comet ATLAS", "stargazing"],
    "sky": ["supermoon", "aurora", "northern lights", "planet parade", "stargazing"],
}

# Dated events, 2021 to 2025. Verify against the NASA eclipse catalogue before
# you publish; these are the well-known ones and dates are UTC.
DATED_EVENTS = [
    ("2021-05-26", "Total lunar eclipse", "lunar eclipse"),
    ("2021-12-04", "Total solar eclipse (Antarctica)", "solar eclipse"),
    ("2021-12-12", "Comet Leonard closest to Earth", "comet"),
    ("2022-05-16", "Total lunar eclipse", "lunar eclipse"),
    ("2022-11-08", "Total lunar eclipse", "lunar eclipse"),
    ("2023-02-01", "Comet C/2022 E3 ZTF closest to Earth", "comet"),
    ("2023-04-20", "Hybrid solar eclipse (Australia)", "solar eclipse"),
    ("2023-10-14", "Annular solar eclipse (Americas)", "solar eclipse"),
    ("2024-04-08", "Total solar eclipse (North America)", "solar eclipse"),
    ("2024-09-18", "Partial lunar eclipse", "lunar eclipse"),
    ("2024-10-02", "Annular solar eclipse (South America)", "solar eclipse"),
    ("2024-10-12", "Comet Tsuchinshan-ATLAS closest to Earth", "comet"),
    ("2025-03-14", "Total lunar eclipse", "lunar eclipse"),
    ("2025-03-29", "Partial solar eclipse", "solar eclipse"),
    ("2025-09-07", "Total lunar eclipse", "lunar eclipse"),
    ("2025-09-21", "Partial solar eclipse", "solar eclipse"),
]

# Annual meteor shower peaks, repeated per year. Dates shift a day either way.
ANNUAL_SHOWERS = [("01-03", "Quadrantids peak"), ("08-12", "Perseids peak"), ("12-14", "Geminids peak")]


def event_table(from_year=2021, to_year=2025):
    events = [{"date": d, "event": label, "type": kind} for d, label, kind in DATED_EVENTS]
    for year in range(from_year, to_year + 1):
        for md, label in ANNUAL_SHOWERS:
            events.append({"date": f"{year}-{md}", "event": f"{label} {year}", "type": "meteor shower"})
    events = [e for e in events if from_year <= int(e["date"][:4]) <= to_year]
    return sorted(events, key=lambda e: e["date"])


# ----------------------------------------------------------------- fetch mode

def fetch(groups, timeframe, geo, sleep, out_path):
    try:
        from pytrends.request import TrendReq
    except ImportError:
        raise SystemExit("pytrends is not installed. Run: pip install pytrends\n"
                         "Or download by hand and use merge mode.")
    import pandas as pd

    client = TrendReq(hl="en-US", tz=0, retries=2, backoff_factor=1.0, timeout=(10, 30))
    frames = []
    for name in groups:
        terms = KEYWORD_GROUPS[name]
        print(f"{name}: {', '.join(terms)}")
        try:
            client.build_payload(terms, timeframe=timeframe, geo=geo)
            data = client.interest_over_time()
        except Exception as err:
            print(f"  failed: {err}", file=sys.stderr)
            continue
        if data is None or data.empty:
            print("  no data returned", file=sys.stderr)
            continue
        data = data.drop(columns=[c for c in ("isPartial",) if c in data.columns])
        tidy = data.reset_index().melt(id_vars="date", var_name="keyword", value_name="interest")
        tidy["group"] = name
        tidy["geo"] = geo or "Worldwide"
        frames.append(tidy)
        print(f"  {len(tidy):,} rows")
        time.sleep(sleep)

    if not frames:
        raise SystemExit("\nNothing fetched. Download by hand and use merge mode.")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(out_path, index=False)
    print(f"\nWrote {len(out):,} rows to {out_path}")


# ----------------------------------------------------------------- merge mode

def parse_export(path):
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]

    header_idx = None
    for i, line in enumerate(lines):
        first = line.split(",")[0].strip().strip('"').lower()
        if first in ("week", "day", "month", "time") and "," in line:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"{Path(path).name}: no header row found. "
                         "Is this the 'Interest over time' export?")

    reader = csv.reader(io.StringIO("\n".join(lines[header_idx:])))
    header = next(reader)
    rows = []
    for parts in reader:
        if not parts or not parts[0].strip():
            continue
        stamp = parts[0].strip()
        for col, value in zip(header[1:], parts[1:]):
            value = (value or "").strip()
            if value == "":
                continue
            interest = 0.5 if value == "<1" else float(re.sub(r"[^0-9.]", "", value) or 0)
            keyword, _, region = col.partition(":")
            rows.append({
                "date": stamp,
                "keyword": keyword.strip(),
                "interest": interest,
                "group": Path(path).stem,
                "geo": region.strip().strip("()") or "Worldwide",
            })
    if not rows:
        raise ValueError(f"{Path(path).name}: header found but no data rows")
    print(f"  {Path(path).name}: {len(rows):,} rows")
    return rows


def merge(patterns, out_path):
    rows = []
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)) or [pattern]:
            if not Path(match).exists():
                print(f"  skipping {match}, not found", file=sys.stderr)
                continue
            try:
                rows.extend(parse_export(match))
            except ValueError as err:
                print(f"  {err}", file=sys.stderr)
    if not rows:
        raise SystemExit("No rows parsed.")
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "keyword", "interest", "group", "geo"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows):,} rows to {out_path}")


# ----------------------------------------------------------------- align mode

def to_date(stamp):
    stamp = stamp.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(stamp[:len(fmt.replace("%Y", "2024").replace("%m", "01")
                                                .replace("%d", "01"))] if False else stamp, fmt).date()
        except ValueError:
            continue
    return None


def align(trends_path, out_path, window=8, baseline=(-12, -5)):
    """
    Put every series on a shared x-axis of weeks from the event, and measure
    the spike against a baseline taken before the event.
    """
    series = {}
    with open(trends_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            when = to_date(row["date"])
            if not when:
                continue
            key = (row["keyword"], row.get("group", ""), row.get("geo", ""))
            series.setdefault(key, []).append((when, float(row["interest"])))

    for points in series.values():
        points.sort()

    events = event_table()
    out_rows = []

    for (keyword, group, geo), points in series.items():
        dates = [p[0] for p in points]
        values = dict(points)
        if len(dates) < 10:
            continue
        step = max((dates[i + 1] - dates[i]).days for i in range(min(5, len(dates) - 1))) or 7

        for ev in events:
            ev_date = to_date(ev["date"])
            if not ev_date or not (dates[0] <= ev_date <= dates[-1]):
                continue

            base_points = [v for d, v in points
                           if baseline[0] * 7 <= (d - ev_date).days <= baseline[1] * 7]
            if len(base_points) < 2:
                continue
            base = sorted(base_points)[len(base_points) // 2]  # median

            for d, v in points:
                offset_days = (d - ev_date).days
                if abs(offset_days) > window * 7:
                    continue
                out_rows.append({
                    "event": ev["event"],
                    "event_date": ev["date"],
                    "event_type": ev["type"],
                    "keyword": keyword,
                    "group": group,
                    "geo": geo,
                    "date": d.isoformat(),
                    "week_offset": round(offset_days / 7),
                    "interest": v,
                    "baseline": base,
                    "lift": round(v / base, 3) if base else "",
                })

    if not out_rows:
        raise SystemExit("Nothing aligned. Check that the trends file covers the event dates.")

    fields = ["event", "event_date", "event_type", "keyword", "group", "geo",
              "date", "week_offset", "interest", "baseline", "lift"]
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Wrote {len(out_rows):,} rows to {out_path}")

    # Peak lift per event and keyword, the headline number for the chart.
    peaks = {}
    for r in out_rows:
        if r["lift"] == "":
            continue
        key = (r["event"], r["keyword"])
        if r["lift"] > peaks.get(key, (0,))[0]:
            peaks[key] = (r["lift"], r["week_offset"], r["event_type"])

    print("\nBiggest spikes (search interest against the preceding baseline)")
    ranked = sorted(peaks.items(), key=lambda kv: -kv[1][0])[:15]
    for (event, keyword), (lift, offset, kind) in ranked:
        print(f"  {lift:6.1f}x  {keyword:<22} {event}  (week {offset:+d})")


def main():
    p = argparse.ArgumentParser(description="Google Trends around celestial events.")
    sub = p.add_subparsers(dest="mode", required=True)

    f = sub.add_parser("fetch", help="try pytrends (rate limited, best effort)")
    f.add_argument("-o", "--output", default="trends.csv")
    f.add_argument("--group", choices=sorted(KEYWORD_GROUPS), action="append")
    f.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    f.add_argument("--geo", default="", help="country code, e.g. AU; blank is worldwide")
    f.add_argument("--sleep", type=float, default=10.0)

    m = sub.add_parser("merge", help="merge CSVs downloaded by hand")
    m.add_argument("inputs", nargs="+")
    m.add_argument("-o", "--output", default="trends.csv")

    a = sub.add_parser("align", help="line series up against event dates and measure spikes")
    a.add_argument("trends", help="tidy CSV from fetch or merge")
    a.add_argument("-o", "--output", default="trends_aligned.csv")
    a.add_argument("--window", type=int, default=8, help="weeks either side of the event")

    e = sub.add_parser("events", help="print the event list, or write it as CSV")
    e.add_argument("--csv", action="store_true", help="write CSV instead of printing a list")
    e.add_argument("-o", "--output", default="events.csv")
    e.add_argument("--no-showers", action="store_true",
                   help="dated events only, leave out the annual meteor shower peaks")

    args = p.parse_args()

    if args.mode == "fetch":
        fetch(args.group or sorted(KEYWORD_GROUPS), args.timeframe, args.geo,
              args.sleep, Path(args.output))
    elif args.mode == "merge":
        merge(args.inputs, Path(args.output))
    elif args.mode == "align":
        align(Path(args.trends), Path(args.output), window=args.window)
    else:
        rows = event_table()
        if args.no_showers:
            rows = [r for r in rows if r["type"] != "meteor shower"]
        if args.csv:
            with open(args.output, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["date", "event", "type"])
                w.writeheader()
                w.writerows(rows)
            print(f"Wrote {len(rows)} events to {args.output}")
            print("Verify the eclipse dates against the NASA catalogue before publishing:")
            print("  https://eclipse.gsfc.nasa.gov/SEsearch/")
            print("Cite: Eclipse Predictions by Fred Espenak, NASA's GSFC.")
        else:
            for ev in rows:
                print(f"  {ev['date']}  {ev['type']:<15} {ev['event']}")


if __name__ == "__main__":
    main()
