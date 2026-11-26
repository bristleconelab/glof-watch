"""Monitor rules without the network: the stored status files still follow scripts/monitor.py, and STATUS.md keeps
a measured 0 km2 (an empty lake) apart from a missing value.

Run: python -m pytest tests
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import monitor  # noqa: E402


def test_stored_status_files_follow_the_rules():
    files = sorted((ROOT / "status").glob("*.json"))
    assert files
    for p in files:
        for lake in json.loads(p.read_text())["lakes"]:
            # the stored series holds the clear, unfrozen scenes that assess() kept
            rows = [{"date": d, "area_km2": a, "seed_snow_ice_frac": 0.0} for d, a in lake["series"]]
            status, recent, base, _ = monitor.assess(rows)
            got = (status, None if recent is None else round(recent, 4), None if base is None else round(base, 4))
            assert got == (lake["status"], lake["recent_km2"], lake["baseline_km2"]), f"{p.name} {lake['id']}"


def test_status_table_shows_zero_area(tmp_path, monkeypatch):
    areas = [0.0, 0.0, 0.0, 0.0006, 0.0006]                   # a drained lake: earlier median 0 km2
    rows = [{"date": f"2026-0{i + 5}-01", "area_km2": a, "seed_snow_ice_frac": 0.0} for i, a in enumerate(areas)]
    monkeypatch.setattr(monitor, "scene_areas", lambda *a, **k: rows)
    wl = tmp_path / "watchlist.json"
    wl.write_text(json.dumps({"lakes": [{"id": "drained", "name": "Drained lake", "country": "-", "type": "ice-dammed",
                                         "bbox": [0, 0, 1, 1], "seed": [0, 0, 1, 1]}]}))
    monkeypatch.setattr(sys, "argv", ["monitor.py", "--watchlist", str(wl), "--out", str(tmp_path / "out")])
    monitor.main()
    row = (tmp_path / "out" / "STATUS.md").read_text(encoding="utf-8").splitlines()[-1]
    assert "| 0.0006 | 0.0 | – | 5 |" in row, row
