#!/usr/bin/env python3
"""Targeted, non-destructive repair for selected fixed-cohort players.

Reads RIOT_API_KEY from the environment. Existing and fallback anonymized rows
are merged before any replacement is written, so a failed extension request
cannot erase previously collected history.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import riot_feasibility_smoke as smoke


MATCH_FIELDS = [
    "anonymized_player_id", "matchId", "gameStartTimestamp", "gameCreation",
    "match_date", "gameVersion", "patch", "queueId", "championName",
    "teamPosition", "individualPosition", "win", "kills", "deaths",
    "assists", "totalDamageDealtToChampions", "goldEarned", "visionScore",
    "item0", "item1", "item2", "item3", "item4", "item5", "item6",
    "summoner1Id", "summoner2Id",
]
SUMMARY_FIELDS = [
    "anonymized_player_id", "seed_tier", "number_of_matches",
    "earliest_match_date", "latest_match_date", "history_span_days",
    "number_of_unique_patches", "matches_per_patch",
    "median_matches_per_patch",
]


def read_matches(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def merge_rows(*groups: list[dict[str, str]], max_matches: int) -> list[dict[str, str]]:
    by_player: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for rows in groups:
        for row in rows:
            by_player[row["anonymized_player_id"]][row["matchId"]] = row
    merged = []
    for player in sorted(by_player):
        player_rows = sorted(
            by_player[player].values(),
            key=lambda r: (int(r["gameStartTimestamp"]), r["matchId"]),
            reverse=True,
        )[:max_matches]
        merged.extend(player_rows)
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair selected players in a fixed Riot cohort")
    ap.add_argument("--players", default="P019,P020")
    ap.add_argument("--max-matches", type=int, default=500)
    ap.add_argument("--out-dir", type=Path, default=Path("riot_feasibility"))
    ap.add_argument("--cohort-file", type=Path, default=Path("riot_feasibility/private/cohort.json"))
    ap.add_argument("--fallback-matches", type=Path, default=Path("riot_feasibility/runs/20260906T050304184130Z_completed/riot_feasibility_matches.csv"))
    ap.add_argument("--sleep", type=float, default=1.25)
    ap.add_argument("--max-retries", type=int, default=7)
    args = ap.parse_args()

    api_key = os.environ.get("RIOT_API_KEY", "").strip()
    if not api_key:
        print("RIOT_API_KEY is not set in this terminal.", file=sys.stderr)
        return 2
    cohort = json.loads(args.cohort_file.read_text(encoding="utf-8"))
    selected = {x.strip().upper() for x in args.players.split(",") if x.strip()}
    seeds = {p["anonymized_player_id"]: p for p in cohort["players"]}
    unknown = selected - set(seeds)
    if unknown:
        print(f"Unknown anonymized player IDs: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    platform = cohort["platform"].upper()
    queues = tuple(int(x) for x in cohort["queues"])
    client = smoke.RiotClient(
        api_key=api_key,
        platform=platform,
        regional=smoke.REGIONS[platform],
        cache_dir=args.out_dir / "raw_cache",
        request_log_path=args.out_dir / "request_log.jsonl",
        sleep=args.sleep,
        max_retries=args.max_retries,
    )

    current = read_matches(args.out_dir / "riot_feasibility_matches.csv")
    fallback = read_matches(args.fallback_matches)
    base = merge_rows(current, fallback, max_matches=args.max_matches)
    base_by_player = defaultdict(list)
    for row in base:
        base_by_player[row["anonymized_player_id"]].append(row)

    repaired_rows: list[dict[str, str]] = []
    failures = []
    before_counts = {p: len(base_by_player[p]) for p in selected}
    for anon_id in sorted(selected):
        seed = seeds[anon_id]
        print(f"{anon_id}: requesting up to {args.max_matches} ranked matches...")
        try:
            ids = smoke.match_ids_for_player(
                client, seed["puuid"], args.max_matches, queues, int(cohort["end_time"])
            )
        except urllib.error.HTTPError as exc:
            failures.append({"player": anon_id, "stage": "match_ids", "error": f"HTTP {exc.code}"})
            print(f"{anon_id}: match-ID request returned HTTP {exc.code}; preserving {before_counts[anon_id]} existing rows.")
            continue
        except Exception as exc:
            failures.append({"player": anon_id, "stage": "match_ids", "error": type(exc).__name__})
            print(f"{anon_id}: match-ID request failed; preserving {before_counts[anon_id]} existing rows.")
            continue
        for match_id in ids:
            try:
                match = client.get(
                    "regional", f"/lol/match/v5/matches/{urllib.parse.quote(match_id, safe='')}"
                )
                row = smoke.extract_participant(match, seed["puuid"])
                if row is None:
                    failures.append({"player": anon_id, "matchId": match_id, "stage": "filtered"})
                    continue
                row["anonymized_player_id"] = anon_id
                repaired_rows.append(row)
            except urllib.error.HTTPError as exc:
                failures.append({"player": anon_id, "matchId": match_id, "stage": "detail", "error": f"HTTP {exc.code}"})
            except Exception as exc:
                failures.append({"player": anon_id, "matchId": match_id, "stage": "detail", "error": type(exc).__name__})

    final_rows = merge_rows(base, repaired_rows, max_matches=args.max_matches)
    final_by_player = defaultdict(list)
    for row in final_rows:
        final_by_player[row["anonymized_player_id"]].append(row)
    after_counts = {p: len(final_by_player[p]) for p in selected}

    # Snapshot only immediately before the atomic logical replacement.
    smoke.snapshot_outputs(args.out_dir, "before_targeted_repair")
    smoke.write_csv(args.out_dir / "riot_feasibility_matches.csv", final_rows, MATCH_FIELDS)

    summary_rows = []
    for anon_id, seed in sorted(seeds.items()):
        summary = smoke.summarize(final_by_player[anon_id])
        summary.update({"anonymized_player_id": anon_id, "seed_tier": seed.get("seed_tier", "")})
        summary_rows.append(summary)
    smoke.write_csv(args.out_dir / "riot_feasibility_summary.csv", summary_rows, SUMMARY_FIELDS)

    patch_players: dict[str, Counter] = defaultdict(Counter)
    for row in final_rows:
        patch_players[row["patch"]][row["anonymized_player_id"]] += 1
    patch_rows = []
    for patch, counts in sorted(patch_players.items(), key=lambda x: tuple(map(int, x[0].split(".")))):
        values = list(counts.values())
        patch_rows.append({"patch": patch, "matches": sum(values), "players": len(values),
                           "median_matches_per_player": round(median(values), 2)})
    smoke.write_csv(args.out_dir / "riot_patch_coverage.csv", patch_rows,
                    ["patch", "matches", "players", "median_matches_per_player"])

    (args.out_dir / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    smoke.render_report(
        args.out_dir / "feasibility_report.md", platform, smoke.REGIONS[platform],
        summary_rows, patch_rows, client.stats, failures, len(seeds), args.max_matches,
    )

    finished_at = dt.datetime.now(dt.UTC).isoformat()
    cohort_id = hashlib.sha256(json.dumps(cohort, sort_keys=True).encode()).hexdigest()[:16]
    metadata = {
        "repair_finished_at_utc": finished_at,
        "cohort_id": cohort_id,
        "selected_players": sorted(selected),
        "before_counts": before_counts,
        "after_counts": after_counts,
        "total_players_with_history": sum(bool(final_by_player[p]) for p in seeds),
        "total_match_rows": len(final_rows),
        "repair_failure_count": len(failures),
        "request_stats": dict(client.stats),
    }
    (args.out_dir / "repair_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (args.out_dir / "repair_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    run_metadata = {
        "cohort_id": cohort_id, "platform": platform, "queues": list(queues),
        "history_cutoff_utc": dt.datetime.fromtimestamp(int(cohort["end_time"]), tz=dt.UTC).isoformat(),
        "max_matches_per_player": args.max_matches, "finished_at": finished_at,
        "players": len(seeds), "players_with_history": sum(bool(final_by_player[p]) for p in seeds),
        "match_rows": len(final_rows), "failure_count": len(failures),
        "run_type": "targeted_repair", "repaired_players": sorted(selected),
    }
    (args.out_dir / "run_metadata.json").write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")
    with (args.out_dir / "feasibility_report.md").open("a", encoding="utf-8") as f:
        f.write(f"\n## Fixed Cohort\n\n- Cohort ID: `{cohort_id}`\n- History cutoff (UTC): {run_metadata['history_cutoff_utc']}\n- Queues: {list(queues)}\n- Repair targets: {', '.join(sorted(selected))}\n")
    lines = [
        "# Targeted cohort repair", "",
        f"- Players: {', '.join(sorted(selected))}",
        f"- Before: {before_counts}",
        f"- After: {after_counts}",
        f"- Total anonymized match rows: {len(final_rows)}",
        f"- Repair failures: {len(failures)}",
        f"- 429 responses: {client.stats.get('http_429', 0)}",
        f"- Network errors: {client.stats.get('network_errors', 0)}",
        "", "Existing rows are retained whenever a request fails. No API key is written to output.",
    ]
    (args.out_dir / "repair_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if failures:
        print(f"Repair completed with {len(failures)} failure(s). Counts: {before_counts} -> {after_counts}")
        return 1
    print(f"Repair complete. Counts: {before_counts} -> {after_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
