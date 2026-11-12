"""Bounded, opt-in ORS import for nearby directional candidates."""

import argparse
import json
import sys
import time
from pathlib import Path

from ..gtfs.sources import GTFSError, configured_path as transit_path
from .client import WalkingError, fetch_walking
from .nearby import MAX_CANDIDATES, nearby
from .store import configured_path, save_result

HARD_MAX_PAIRS = 20
HARD_MAX_REQUESTS = 20


def run(transit: Path, walking: Path, stop_id: str, radius_m=500, limit=50, max_pairs=3,
        max_requests=3, interval_seconds=2, execute=False, refresh=False) -> dict:
    if (isinstance(max_pairs, bool) or not isinstance(max_pairs, int) or not 1 <= max_pairs <= HARD_MAX_PAIRS
            or isinstance(max_requests, bool) or not isinstance(max_requests, int) or not 1 <= max_requests <= HARD_MAX_REQUESTS
            or isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)) or not 1 <= interval_seconds <= 60):
        raise WalkingError("invalid_budget", "Budżety: max-pairs 1–20, max-requests 1–20, odstęp 1–60 sekund.")
    discovery = nearby(transit, walking, stop_id, radius_m, limit)
    pending = [item for item in discovery["candidates"] if refresh or item["status"] not in ("available", "no_route")]
    selected = pending[:max_pairs]
    plan = {"dry_run": not execute, "candidate_count": discovery["candidate_count"],
            "returned_count": discovery["returned_count"], "has_more_candidates": discovery["has_more"],
            "cache_hits": discovery["cache_hits"], "selected_pairs": len(selected),
            "planned_initial_requests": min(len(selected), max_requests), "request_budget": max_requests,
            "max_pairs": max_pairs, "interval_seconds": interval_seconds, "refresh": refresh,
            "deferred_pairs": len(pending) - len(selected), "rejected": discovery["rejected"],
            "pairs": selected, "requests_made": 0, "saved_pairs": 0, "errors": [],
            "remaining_selected_pairs": len(selected), "stopped_reason": "dry_run" if not execute else None}
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not execute:
        return plan
    last_request = None

    def before_request():
        nonlocal last_request
        if plan["requests_made"] >= max_requests:
            raise WalkingError("request_budget", "Wyczerpano globalny budżet żądań.")
        if last_request is not None:
            wait = interval_seconds - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
        last_request = time.monotonic()
        plan["requests_made"] += 1

    for item in selected:
        if plan["requests_made"] >= max_requests:
            plan["stopped_reason"] = "request_budget"
            break
        try:
            result = fetch_walking(*item["coordinates"], max_requests=min(3, max_requests - plan["requests_made"]), before_request=before_request)
            save_result(walking, item["from_stop_id"], item["to_stop_id"], item["coordinates"], result)
            plan["saved_pairs"] += 1
            plan["remaining_selected_pairs"] -= 1
        except WalkingError as error:
            plan["errors"].append({"from_stop_id": item["from_stop_id"], "to_stop_id": item["to_stop_id"], "code": error.code, "message": str(error)})
            plan["stopped_reason"] = "error"
            # Stop the batch on any failed pair; rerunning resumes from committed results.
            break
    return plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kandydaci ZTM/SKM: domyślnie dry-run. ORS wymaga --execute.")
    parser.add_argument("stop_id")
    parser.add_argument("--radius-m", type=float, default=500)
    parser.add_argument("--limit", type=int, default=50, help=f"Maksymalnie {MAX_CANDIDATES} kandydatów.")
    parser.add_argument("--max-pairs", type=int, default=3)
    parser.add_argument("--max-requests", type=int, default=3, help="Globalny budżet, razem z retry.")
    parser.add_argument("--interval-seconds", type=float, default=2)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--database", type=Path, default=configured_path())
    parser.add_argument("--transit-database", type=Path, default=transit_path())
    args = parser.parse_args(argv)
    try:
        result = run(args.transit_database, args.database, args.stop_id, args.radius_m, args.limit,
                     args.max_pairs, args.max_requests, args.interval_seconds, args.execute, args.refresh)
        if args.execute:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        return 1 if result["errors"] else 0
    except (WalkingError, GTFSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("Nie można odczytać lub zapisać lokalnej bazy.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
