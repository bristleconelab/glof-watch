#!/usr/bin/env python3
"""Watchlist monitor: recent Sentinel-2 lake areas -> status per lake (drainage alert, fast growth, ok, no data).

Rules (from the Thame, Shisper and Merzbacher back-tests):
  * frozen scenes (more than 30 % of the seed box in the L2A snow/ice class) are ignored;
  * DRAINAGE if BOTH of the last 2 clear scenes are below 50 % of the median of the earlier scenes in the window
    and the earlier median is at least 0.02 km2 (one scene is never enough: ice, shadow and thin cloud make spikes);
  * POSSIBLE DRAINAGE if only the latest scene is below 40 % of the earlier median (wait for confirmation);
  * GROWTH if BOTH of the last 2 clear scenes are more than 25 % above the earlier median;
  * otherwise OK, or NO DATA when fewer than 4 clear scenes exist.

Usage: monitor.py --watchlist watchlist.json --out status [--as-of 2024-09-20] [--days 120]
Writes <out>/latest.json and <out>/STATUS.md (or <out>/backtest_<date>.json/.md with --as-of).
"""
import argparse
import datetime as dt
import json
import os

import numpy as np

from lake_scenes import scene_areas

ICON = {"DRAINAGE": "🔴 DRAINAGE", "POSSIBLE DRAINAGE": "⚠️ POSSIBLE DRAINAGE", "GROWTH": "🟠 GROWTH", "OK": "🟢 OK",
        "NO DATA": "⚪ NO DATA"}


def assess(rows):
    rows = [r for r in rows if r["seed_snow_ice_frac"] <= 0.3]
    if len(rows) < 4:
        return "NO DATA", None, None, rows
    areas = np.array([r["area_km2"] for r in rows])
    recent, base = float(np.median(areas[-2:])), float(np.median(areas[:-2]))
    last, hi2, lo2 = float(areas[-1]), float(areas[-2:].max()), float(areas[-2:].min())
    if base >= 0.02 and hi2 < 0.5 * base:              # BOTH latest scenes low
        status = "DRAINAGE"
    elif base >= 0.02 and last < 0.4 * base:
        status = "POSSIBLE DRAINAGE"                   # one scene only: needs the next clear scene to confirm
    elif base >= 0.02 and lo2 > 1.25 * base:           # BOTH latest scenes high (one bright/icy scene is not enough)
        status = "GROWTH"
    else:
        status = "OK"
    return status, recent, base, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", help="YYYY-MM-DD; default today (back-test when in the past)")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--only", help="comma-separated lake ids")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    end = dt.date.fromisoformat(a.as_of) if a.as_of else dt.date.today()
    start = end - dt.timedelta(days=a.days)
    lakes = json.load(open(a.watchlist))["lakes"]
    if a.only:
        lakes = [l for l in lakes if l["id"] in a.only.split(",")]
    results = []
    for lk in lakes:
        rows = scene_areas(lk["bbox"], lk["seed"], start.isoformat(), end.isoformat(), gr=lk.get("gr", 0.02), verbose=False)
        status, recent, base, used = assess(rows)
        cx = (lk["bbox"][0] + lk["bbox"][2]) / 2; cy = (lk["bbox"][1] + lk["bbox"][3]) / 2
        res = {"id": lk["id"], "name": lk["name"], "country": lk["country"], "type": lk["type"], "status": status,
               "recent_km2": None if recent is None else round(recent, 4), "baseline_km2": None if base is None else round(base, 4),
               "change_pct": None if not base else round(100 * (recent - base) / base, 1),
               "clear_scenes": len(used), "last_scene": used[-1]["date"] if used else None,
               "map": f"https://www.google.com/maps/@{cy:.4f},{cx:.4f},3000m/data=!3m1!1e3",
               "series": [(r["date"], r["area_km2"]) for r in used]}
        results.append(res)
        print(f"{lk['id']:12s} {status:9s} recent={res['recent_km2']} base={res['baseline_km2']} scenes={len(used)}", flush=True)
    tag = f"backtest_{end.isoformat()}" if a.as_of else "latest"
    meta = {"as_of": end.isoformat(), "window_days": a.days, "generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"}
    json.dump({**meta, "lakes": results}, open(os.path.join(a.out, f"{tag}.json"), "w"), indent=1)
    lines = [f"# Lake status, {end.isoformat()}" + (" (back-test)" if a.as_of else ""), "",
             f"Sentinel-2 clear scenes in the last {a.days} days; frozen scenes ignored. Rules: see `scripts/monitor.py`.", "",
             "| Lake | Country | Type | Status | Recent km² | Baseline km² | Change | Clear scenes | Last scene | Map |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        ch = "–" if r["change_pct"] is None else f"{r['change_pct']:+.0f} %"
        km = ["–" if r[k] is None else r[k] for k in ("recent_km2", "baseline_km2")]   # 0.0 = empty lake, not missing
        lines.append(f"| {r['name']} | {r['country']} | {r['type']} | {ICON[r['status']]} | {km[0]} | "
                     f"{km[1]} | {ch} | {r['clear_scenes']} | {r['last_scene'] or '–'} | [map]({r['map']}) |")
    open(os.path.join(a.out, f"{'STATUS' if not a.as_of else tag}.md"), "w").write("\n".join(lines) + "\n")
    print("->", os.path.join(a.out, tag))


if __name__ == "__main__":
    main()
