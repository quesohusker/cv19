#!/usr/bin/env python3
"""Run every data collector and write data/manifest.json summarizing results.

By default this only runs the two sources that work from a normal network
connection (ncaavolleyballr, mattwaite_early_years). Pass --all to also
attempt the three sources that this sandbox's egress policy blocked
(massey_ratings, ncaa_live_api) -- stats_ncaa_direct is excluded even from
--all since it needs specific team IDs supplied by the caller and has no
independent entry point (see its docstring).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from sources import mattwaite_early_years, massey_ratings, ncaa_live_api, ncaavolleyballr
from sources.common import DATA_ROOT

ALWAYS_ON = {
    "ncaavolleyballr": ncaavolleyballr.collect,
    "mattwaite_early_years": mattwaite_early_years.collect,
}
OPT_IN = {
    "massey_ratings": massey_ratings.collect,
    "ncaa_live_api": ncaa_live_api.collect,
}


def build_manifest(all_results: dict[str, list[dict]]) -> dict:
    summary = {}
    for source, results in all_results.items():
        total_bytes = sum(r.get("bytes", 0) for r in results if isinstance(r.get("bytes"), int))
        by_status: dict[str, int] = {}
        for r in results:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        summary[source] = {
            "files": len(results),
            "total_bytes": total_bytes,
            "by_status": by_status,
            "failed": [r for r in results if r["status"] == "failed"],
        }
    return {
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="also attempt sources blocked in restricted sandboxes")
    args = parser.parse_args()

    collectors = dict(ALWAYS_ON)
    if args.all:
        collectors.update(OPT_IN)

    all_results: dict[str, list[dict]] = {}
    for name, fn in collectors.items():
        print(f"\n=== {name} ===")
        try:
            all_results[name] = fn()
        except Exception as exc:  # noqa: BLE001 -- keep going on source failure
            print(f"[{name}] collector raised: {exc}")
            all_results[name] = [{"source": name, "status": "failed", "error": str(exc)}]

    manifest = build_manifest(all_results)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = DATA_ROOT / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nWrote {manifest_path}")
    for source, info in manifest["sources"].items():
        gb = info["total_bytes"] / 1024 / 1024 / 1024
        print(f"  {source}: {info['files']} files, {gb:.2f} GB, {info['by_status']}")


if __name__ == "__main__":
    main()
