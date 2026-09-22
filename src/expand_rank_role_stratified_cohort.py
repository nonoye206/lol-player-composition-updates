#!/usr/bin/env python3
"""Create a rank-by-role stratified Riot cohort.

The API key is read only from RIOT_API_KEY. PUUIDs are written only to the
gitignored private cohort file. Request logs never include the key.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import urllib.error
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import riot_feasibility_smoke as smoke


TOP_ENDPOINTS = {
    "CHALLENGER": "/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5",
    "GRANDMASTER": "/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5",
    "MASTER": "/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5",
}

DEFAULT_STRATA = ("GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER_PLUS")
DEFAULT_ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
MASTER_PLUS_TIERS = ("CHALLENGER", "GRANDMASTER", "MASTER")


def parse_int_map(value: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for part in value.split(","):
        if not part.strip():
            continue
        key, raw_count = part.split(":", 1)
        count = int(raw_count)
        if count < 0:
            raise ValueError("Quota counts must be non-negative")
        result[key.strip().upper()] = count
    return result


def parse_role_targets(value: str) -> dict[str, int]:
    targets = parse_int_map(value)
    unknown = sorted(set(targets) - set(DEFAULT_ROLES))
    if unknown:
        raise ValueError(f"Unknown role quota(s): {', '.join(unknown)}")
    return targets


def stratum_for_tier(tier: str) -> str:
    tier = tier.upper()
    if tier in MASTER_PLUS_TIERS:
        return "MASTER_PLUS"
    return tier


def tier_candidates(
    client: smoke.RiotClient,
    tier: str,
    rng: random.Random,
    max_pages_per_division: int,
) -> list[dict[str, Any]]:
    if tier in TOP_ENDPOINTS:
        payload = client.get("platform", TOP_ENDPOINTS[tier])
        entries = list(payload.get("entries", []))
    else:
        entries = []
        for division in ("I", "II", "III", "IV"):
            for page in range(1, max_pages_per_division + 1):
                path = f"/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}"
                chunk = client.get("platform", path, {"page": page})
                if not chunk:
                    break
                entries.extend(chunk)
    rng.shuffle(entries)
    return entries


def stratum_candidates(
    client: smoke.RiotClient,
    stratum: str,
    rng: random.Random,
    max_pages_per_division: int,
) -> list[dict[str, Any]]:
    tiers = MASTER_PLUS_TIERS if stratum == "MASTER_PLUS" else (stratum,)
    combined: list[dict[str, Any]] = []
    for tier in tiers:
        for entry in tier_candidates(client, tier, rng, max_pages_per_division):
            item = dict(entry)
            item["seed_tier"] = tier
            item["seed_stratum"] = stratum_for_tier(tier)
            combined.append(item)
    rng.shuffle(combined)
    return combined


def resolve_puuid(client: smoke.RiotClient, entry: dict[str, Any]) -> str:
    if entry.get("puuid"):
        return str(entry["puuid"])
    summoner_id = entry.get("summonerId", "")
    if not summoner_id:
        return ""
    payload = client.get(
        "platform",
        f"/lol/summoner/v4/summoners/{urllib.parse.quote(summoner_id, safe='')}",
    )
    return payload.get("puuid", "")


def infer_primary_role(
    client: smoke.RiotClient,
    puuid: str,
    probe_matches: int,
    min_probe_matches: int,
    end_time: int,
) -> tuple[str, Counter[str]]:
    role_counts: Counter[str] = Counter()
    match_ids = smoke.match_ids_for_player(client, puuid, probe_matches, (420,), end_time)
    for match_id in match_ids:
        match = client.get("regional", f"/lol/match/v5/matches/{urllib.parse.quote(match_id, safe='')}")
        row = smoke.extract_participant(match, puuid)
        if not row:
            continue
        role = row.get("teamPosition") or row.get("individualPosition") or ""
        if role in DEFAULT_ROLES:
            role_counts[role] += 1
    if sum(role_counts.values()) < min_probe_matches:
        return "", role_counts
    if not role_counts:
        return "", role_counts
    role_rank = {role: idx for idx, role in enumerate(DEFAULT_ROLES)}
    primary = sorted(role_counts.items(), key=lambda item: (-item[1], role_rank[item[0]]))[0][0]
    return primary, role_counts


def quota_grid(strata: tuple[str, ...], stratum_size: int, role_targets: dict[str, int]) -> dict[str, dict[str, int]]:
    if sum(role_targets.values()) != stratum_size:
        raise ValueError("Role targets must sum to --players-per-stratum.")
    return {stratum: dict(role_targets) for stratum in strata}


def grid_counts(players: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for player in players:
        counts[player["seed_stratum"]][player["primary_role"]] += 1
    return counts


def is_full(counts: dict[str, Counter[str]], grid: dict[str, dict[str, int]]) -> bool:
    for stratum, role_targets in grid.items():
        for role, target in role_targets.items():
            if counts[stratum][role] < target:
                return False
    return True


def checkpoint_path_for(output: Path) -> Path:
    return output.with_suffix(".checkpoint.json")


def write_checkpoint(
    path: Path,
    args: argparse.Namespace,
    platform: str,
    strata: tuple[str, ...],
    role_targets: dict[str, int],
    end_time: int,
    selected: list[dict[str, Any]],
    rejection_counts: Counter[str],
) -> None:
    checkpoint = {
        "schema_version": 1,
        "platform": platform,
        "queues": [420],
        "end_time": end_time,
        "sampling_design": "rank_by_primary_role",
        "random_seed": args.random_seed,
        "strata": list(strata),
        "players_per_stratum": args.players_per_stratum,
        "role_targets_per_stratum": role_targets,
        "role_probe_matches": args.role_probe_matches,
        "min_role_probe_matches": args.min_role_probe_matches,
        "selected_players": selected,
        "rejection_counts": dict(rejection_counts),
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load_checkpoint(
    path: Path,
    args: argparse.Namespace,
    platform: str,
    strata: tuple[str, ...],
    role_targets: dict[str, int],
) -> tuple[int, list[dict[str, Any]], Counter[str]]:
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    valid = (
        checkpoint.get("schema_version") == 1
        and checkpoint.get("platform") == platform
        and checkpoint.get("queues") == [420]
        and checkpoint.get("sampling_design") == "rank_by_primary_role"
        and checkpoint.get("random_seed") == args.random_seed
        and checkpoint.get("strata") == list(strata)
        and checkpoint.get("players_per_stratum") == args.players_per_stratum
        and checkpoint.get("role_targets_per_stratum") == role_targets
        and checkpoint.get("role_probe_matches") == args.role_probe_matches
        and checkpoint.get("min_role_probe_matches") == args.min_role_probe_matches
    )
    if not valid:
        raise ValueError("Existing checkpoint does not match requested settings.")
    selected = list(checkpoint.get("selected_players", []))
    end_time = int(checkpoint["end_time"])
    rejection_counts = Counter(checkpoint.get("rejection_counts", {}))
    return end_time, selected, rejection_counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a 500-player rank-by-role Riot cohort")
    parser.add_argument("--platform", default="NA1", choices=sorted(smoke.REGIONS))
    parser.add_argument("--output", type=Path, default=Path("riot_feasibility/private/cohort_500_rank_role.json"))
    parser.add_argument("--strata", default=",".join(DEFAULT_STRATA))
    parser.add_argument("--players-per-stratum", type=int, default=100)
    parser.add_argument("--role-targets", default="TOP:20,JUNGLE:20,MIDDLE:20,BOTTOM:20,UTILITY:20")
    parser.add_argument("--role-probe-matches", type=int, default=50)
    parser.add_argument("--min-role-probe-matches", type=int, default=10)
    parser.add_argument("--max-pages-per-division", type=int, default=10)
    parser.add_argument("--random-seed", type=int, default=20260907)
    parser.add_argument("--sleep", type=float, default=1.25)
    parser.add_argument("--max-retries", type=int, default=7)
    parser.add_argument("--checkpoint-file", type=Path, default=None)
    args = parser.parse_args()

    api_key = os.environ.get("RIOT_API_KEY", "").strip()
    if not api_key:
        print("RIOT_API_KEY is not set in this terminal.", file=sys.stderr)
        return 2
    if args.role_probe_matches < 1 or args.min_role_probe_matches < 1:
        parser.error("Role probe match counts must be positive.")
    if args.min_role_probe_matches > args.role_probe_matches:
        parser.error("--min-role-probe-matches cannot exceed --role-probe-matches.")

    strata = tuple(s.strip().upper() for s in args.strata.split(",") if s.strip())
    if not strata:
        parser.error("At least one stratum is required.")
    role_targets = parse_role_targets(args.role_targets)
    grid = quota_grid(strata, args.players_per_stratum, role_targets)
    target_players = len(strata) * args.players_per_stratum

    if args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        players = existing.get("players", [])
        counts = grid_counts(players)
        valid = (
            existing.get("schema_version") == 1
            and existing.get("platform") == args.platform.upper()
            and existing.get("queues") == [420]
            and len(players) == target_players
            and len({p.get("puuid") for p in players}) == target_players
            and is_full(counts, grid)
        )
        if not valid:
            print("Existing cohort does not match requested rank-role quotas; nothing changed.", file=sys.stderr)
            return 2
        print(f"Reusing rank-role cohort with {len(players)} players.")
        return 0

    platform = args.platform.upper()
    checkpoint_file = args.checkpoint_file or checkpoint_path_for(args.output)
    client = smoke.RiotClient(
        api_key=api_key,
        platform=platform,
        regional=smoke.REGIONS[platform],
        cache_dir=Path("riot_rank_role_cohort_expansion/raw_cache"),
        request_log_path=Path("riot_rank_role_cohort_expansion/request_log.jsonl"),
        sleep=args.sleep,
        max_retries=args.max_retries,
    )
    rng = random.Random(args.random_seed)
    if checkpoint_file.exists():
        try:
            end_time, selected, rejection_counts = load_checkpoint(
                checkpoint_file, args, platform, strata, role_targets
            )
            print(f"Resuming from checkpoint with {len(selected)} selected players.")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        end_time = int(dt.datetime.now(dt.UTC).timestamp())
        selected = []
        rejection_counts = Counter()
    selected_counts = grid_counts(selected)
    seen_puuids = {p["puuid"] for p in selected}

    for stratum in strata:
        print(f"{stratum}: collecting candidates...")
        candidates = stratum_candidates(client, stratum, rng, args.max_pages_per_division)
        print(f"{stratum}: {len(candidates)} candidate league entries.")
        for entry in candidates:
            if all(selected_counts[stratum][role] >= grid[stratum][role] for role in DEFAULT_ROLES):
                break
            try:
                puuid = resolve_puuid(client, entry)
                if not puuid:
                    rejection_counts[f"{stratum}:missing_puuid"] += 1
                    continue
                if puuid in seen_puuids:
                    rejection_counts[f"{stratum}:duplicate"] += 1
                    continue
                primary_role, role_counts = infer_primary_role(
                    client,
                    puuid,
                    args.role_probe_matches,
                    args.min_role_probe_matches,
                    end_time,
                )
            except urllib.error.HTTPError as exc:
                if exc.code in {401, 403}:
                    print(f"Riot authentication failed with HTTP {exc.code}.", file=sys.stderr)
                    return 3
                rejection_counts[f"{stratum}:http_{exc.code}"] += 1
                continue
            except Exception as exc:
                rejection_counts[f"{stratum}:{type(exc).__name__}"] += 1
                continue

            if not primary_role:
                rejection_counts[f"{stratum}:insufficient_role_probe"] += 1
                continue
            if selected_counts[stratum][primary_role] >= grid[stratum][primary_role]:
                rejection_counts[f"{stratum}:role_full_{primary_role}"] += 1
                continue

            seen_puuids.add(puuid)
            selected_counts[stratum][primary_role] += 1
            selected.append(
                {
                    "anonymized_player_id": f"P{len(selected) + 1:03d}",
                    "puuid": puuid,
                    "seed_tier": entry.get("seed_tier", stratum),
                    "seed_stratum": stratum,
                    "primary_role": primary_role,
                    "role_probe_matches": sum(role_counts.values()),
                    "role_probe_counts": dict(sorted(role_counts.items())),
                }
            )
            print(f"{stratum} {primary_role}: {selected_counts[stratum][primary_role]}/{grid[stratum][primary_role]}")
            write_checkpoint(
                checkpoint_file,
                args,
                platform,
                strata,
                role_targets,
                end_time,
                selected,
                rejection_counts,
            )

        missing = {
            role: grid[stratum][role] - selected_counts[stratum][role]
            for role in DEFAULT_ROLES
            if selected_counts[stratum][role] < grid[stratum][role]
        }
        if missing:
            print(f"Could not fill {stratum} quota: {missing}. Cohort was not written.", file=sys.stderr)
            print(f"Rejections: {dict(rejection_counts)}", file=sys.stderr)
            return 4

    if len(selected) != target_players or len(seen_puuids) != target_players:
        print("Final cohort size or uniqueness check failed. Cohort was not written.", file=sys.stderr)
        return 4

    cohort = {
        "schema_version": 1,
        "platform": platform,
        "queues": [420],
        "end_time": end_time,
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "sampling_design": "rank_by_primary_role",
        "random_seed": args.random_seed,
        "strata": list(strata),
        "players_per_stratum": args.players_per_stratum,
        "role_targets_per_stratum": role_targets,
        "role_probe_matches": args.role_probe_matches,
        "min_role_probe_matches": args.min_role_probe_matches,
        "players": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(cohort, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(args.output)
    if checkpoint_file.exists():
        checkpoint_file.unlink()
    print(f"Created rank-role cohort with {len(selected)} players at fixed cutoff {end_time}.")
    print("Grid counts:", {stratum: dict(selected_counts[stratum]) for stratum in strata})
    print("Request stats:", dict(client.stats))
    print("Rejections:", dict(rejection_counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
