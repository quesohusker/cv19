"""Command-line entry point: ``python -m cfbd_pull``."""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
from typing import List

from . import endpoints as ep
from .client import AuthError, CFBDClient
from .runner import Runner
from .store import DEFAULT_OUT, DriveNotMounted, Store

#: CFBD's earliest broadly-populated season. Play-by-play begins around 2001;
#: box scores and results reach back much further.
EARLIEST_SEASON = 1869


def _current_season() -> int:
    today = _dt.date.today()
    # A season is labelled by the calendar year it starts in; roll over in July.
    return today.year if today.month >= 7 else today.year - 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m cfbd_pull",
        description="Pull every available statistic from the CollegeFootballData API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python -m cfbd_pull --years 2024 --dry-run\n"
            "  python -m cfbd_pull --years 2020-2024\n"
            "  python -m cfbd_pull --years 2024 --tier full\n"
            "  python -m cfbd_pull --groups betting ratings --years 2015-2024\n"
            "  python -m cfbd_pull --list-endpoints\n"
        ),
    )
    p.add_argument(
        "--years",
        default=str(_current_season()),
        help="season or range, e.g. 2024, 2010-2024, or 'all' "
        f"(default: {_current_season()})",
    )
    p.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"output directory (default: {DEFAULT_OUT!r})",
    )
    p.add_argument(
        "--tier",
        choices=[ep.CORE, ep.FULL, ep.EXHAUSTIVE],
        default=ep.CORE,
        help="how deep to pull: core=season aggregates, full=+plays/drives, "
        "exhaustive=+per-game and per-player detail (default: core)",
    )
    p.add_argument(
        "--groups",
        nargs="+",
        metavar="GROUP",
        help=f"limit to endpoint groups: {' '.join(ep.GROUPS)}",
    )
    p.add_argument(
        "--endpoints",
        nargs="+",
        metavar="PATH",
        help="limit to specific endpoint paths, e.g. /games /lines",
    )
    p.add_argument("--api-key", help="override the configured API key")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the calls that would be made without contacting the API",
    )
    p.add_argument(
        "--min-interval",
        type=float,
        default=0.6,
        help="minimum seconds between requests (default: 0.6)",
    )
    p.add_argument(
        "--no-compress", action="store_true", help="write plain .json, not .json.gz"
    )
    p.add_argument(
        "--no-resume",
        action="store_true",
        help="re-pull calls already recorded in the manifest",
    )
    p.add_argument(
        "--include-live",
        action="store_true",
        help="include live-only endpoints (/scoreboard, /live/plays)",
    )
    p.add_argument(
        "--include-meta",
        action="store_true",
        help="include account endpoints (/info, /info/usage)",
    )
    p.add_argument(
        "--extra-season-types",
        action="store_true",
        help="also sweep allstar and spring season types",
    )
    p.add_argument(
        "--stop-on-error", action="store_true", help="abort on the first failure"
    )
    p.add_argument(
        "--list-endpoints",
        action="store_true",
        help="print the endpoint registry and exit",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return p


def parse_years(spec: str) -> List[int]:
    """Parse ``2024``, ``2010-2024``, ``2019,2021`` or ``all``."""
    spec = spec.strip().lower()
    if spec == "all":
        return list(range(EARLIEST_SEASON, _current_season() + 1))

    years: List[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo_s, _, hi_s = chunk.partition("-")
            lo, hi = int(lo_s), int(hi_s)
            if lo > hi:
                raise ValueError(f"empty year range: {chunk}")
            years.extend(range(lo, hi + 1))
        else:
            years.append(int(chunk))

    if not years:
        raise ValueError(f"no years parsed from {spec!r}")
    return sorted(set(years))


def list_endpoints() -> None:
    print(f"{len(ep.ENDPOINTS)} endpoints\n")
    for group in ep.GROUPS:
        print(f"{group}:")
        for e in ep.ENDPOINTS:
            if e.group != group:
                continue
            note = f"  # {e.notes}" if e.notes else ""
            print(f"  {e.path:<30} {e.strategy:<12} {e.tier}{note}")
        print()


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list_endpoints:
        list_endpoints()
        return 0

    try:
        years = parse_years(args.years)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        selected = ep.select(
            tier=args.tier,
            groups=args.groups,
            paths=args.endpoints,
            include_live=args.include_live,
            include_meta=args.include_meta,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not selected:
        print("error: no endpoints matched those filters", file=sys.stderr)
        return 2

    try:
        store = Store(args.out, compress=not args.no_compress)
    except (DriveNotMounted, PermissionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.no_resume:
        store._done.clear()

    try:
        # A dry run never contacts the API, so it should not demand a key.
        client = CFBDClient(
            args.api_key or ("dry-run" if args.dry_run else None),
            min_interval=args.min_interval,
        )
    except AuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    logging.info(
        "%d endpoint(s), seasons %d-%d, tier=%s -> %s",
        len(selected),
        years[0],
        years[-1],
        args.tier,
        store.root,
    )

    runner = Runner(
        client,
        store,
        years=years,
        dry_run=args.dry_run,
        stop_on_error=args.stop_on_error,
        extra_season_types=args.extra_season_types,
    )

    tasks, dependent = runner.plan(selected)
    logging.info("phase 1: %d call(s) planned", len(tasks))
    try:
        runner.run(tasks)

        if dependent:
            dep_tasks = runner.plan_dependent(dependent)
            if dep_tasks:
                logging.info("phase 2: %d id-keyed call(s) planned", len(dep_tasks))
                runner.run(dep_tasks)
    except KeyboardInterrupt:
        print("\ninterrupted -- progress saved; rerun to resume", file=sys.stderr)
        print(runner.summary.render(client))
        return 130
    except AuthError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        print(runner.summary.render(client))
        return 1

    print(runner.summary.render(client))
    return 1 if runner.summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
