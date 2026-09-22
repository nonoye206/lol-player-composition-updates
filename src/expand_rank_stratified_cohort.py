#!/usr/bin/env python3
"""Append rank-stratified players to an existing fixed Riot cohort.

The original identities and historical cutoff are preserved. PUUIDs are stored
only in the gitignored private cohort file. The API key is read only from
RIOT_API_KEY.
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
from collections import Counter
from pathlib import Path

import riot_feasibility_smoke as smoke


TOP_ENDPOINTS = {
    "CHALLENGER": "/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5",
    "GRANDMASTER": "/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5",
    "MASTER": "/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5",
}


def parse_quotas(value: str) -> dict[str, int]:
    result = {}
    for part in value.split(","):
        tier, count = part.split(":", 1)
        result[tier.strip().upper()] = int(count)
    if any(v < 0 for v in result.values()):
        raise ValueError("Quota counts must be non-negative")
    return result


def tier_candidates(client: smoke.RiotClient, tier: str, rng: random.Random) -> list[dict]:
    if tier in TOP_ENDPOINTS:
        payload = client.get("platform", TOP_ENDPOINTS[tier])
        entries = list(payload.get("entries", []))
    else:
        entries = []
        for division in ("I", "II", "III", "IV"):
            page = 1
            while page <= 3 and len(entries) < 600:
                path = f"/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}"
                chunk = client.get("platform", path, {"page": page})
                if not chunk:
                    break
                entries.extend(chunk)
                page += 1
    rng.shuffle(entries)
    return entries


def resolve_puuid(client: smoke.RiotClient, entry: dict) -> str:
    if entry.get("puuid"):
        return entry["puuid"]
    summoner_id = entry.get("summonerId", "")
    if not summoner_id:
        return ""
    payload = client.get(
        "platform", f"/lol/summoner/v4/summoners/{urllib.parse.quote(summoner_id, safe='')}"
    )
    return payload.get("puuid", "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Expand a fixed Riot cohort by rank strata")
    ap.add_argument("--source", type=Path, default=Path("riot_feasibility/private/cohort.json"))
    ap.add_argument("--output", type=Path, default=Path("riot_feasibility/private/cohort_100.json"))
    ap.add_argument("--target-players", type=int, default=100)
    ap.add_argument(
        "--quotas",
        default="CHALLENGER:20,GRANDMASTER:16,MASTER:16,DIAMOND:16,EMERALD:16,PLATINUM:16",
        help="Final tier quotas; must sum to target players.",
    )
    ap.add_argument("--random-seed", type=int, default=20260906)
    ap.add_argument("--sleep", type=float, default=1.25)
    ap.add_argument("--max-retries", type=int, default=7)
    args = ap.parse_args()

    api_key = os.environ.get("RIOT_API_KEY", "").strip()
    if not api_key:
        print("RIOT_API_KEY is not set in this terminal.", file=sys.stderr)
        return 2
    quotas = parse_quotas(args.quotas)
    if sum(quotas.values()) != args.target_players:
        print("Tier quotas must sum to --target-players.", file=sys.stderr)
        return 2
    source = json.loads(args.source.read_text(encoding="utf-8"))

    if args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        source_ids = [p["puuid"] for p in source["players"]]
        existing_ids = [p["puuid"] for p in existing["players"]]
        valid = (
            len(existing_ids) == args.target_players
            and existing_ids[: len(source_ids)] == source_ids
            and existing.get("end_time") == source.get("end_time")
            and existing.get("platform") == source.get("platform")
            and existing.get("queues") == source.get("queues")
        )
        if not valid:
            print("Existing expanded cohort does not match the source cohort; nothing changed.", file=sys.stderr)
            return 2
        print(f"Reusing expanded cohort with {len(existing_ids)} players.")
        return 0

    platform = source["platform"].upper()
    client = smoke.RiotClient(
        api_key=api_key,
        platform=platform,
        regional=smoke.REGIONS[platform],
        cache_dir=Path("riot_cohort_expansion/raw_cache"),
        request_log_path=Path("riot_cohort_expansion/request_log.jsonl"),
        sleep=args.sleep,
        max_retries=args.max_retries,
    )
    rng = random.Random(args.random_seed)
    players = [dict(p) for p in source["players"]]
    seen = {p["puuid"] for p in players}
    current = Counter(p.get("seed_tier", "UNKNOWN").upper() for p in players)

    for tier, quota in quotas.items():
        need = quota - current[tier]
        if need <= 0:
            continue
        print(f"{tier}: selecting {need} additional players...")
        for entry in tier_candidates(client, tier, rng):
            try:
                puuid = resolve_puuid(client, entry)
            except urllib.error.HTTPError as exc:
                if exc.code in {401, 403}:
                    print(f"Riot authentication failed with HTTP {exc.code}.", file=sys.stderr)
                    return 3
                continue
            if not puuid or puuid in seen:
                continue
            seen.add(puuid)
            players.append({
                "anonymized_player_id": f"P{len(players) + 1:03d}",
                "puuid": puuid,
                "seed_tier": tier,
            })
            current[tier] += 1
            need -= 1
            if need == 0:
                break
        if need:
            print(f"Could not fill {tier} quota; cohort was not written.", file=sys.stderr)
            return 4

    if len(players) != args.target_players or len(seen) != args.target_players:
        print("Final cohort size or identity uniqueness check failed.", file=sys.stderr)
        return 4
    expanded = {
        **{k: source[k] for k in ("schema_version", "platform", "queues", "end_time", "created_at")},
        "expanded_at": dt.datetime.now(dt.UTC).isoformat(),
        "expansion_random_seed": args.random_seed,
        "tier_quotas": quotas,
        "source_player_count": len(source["players"]),
        "players": players,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(expanded, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(args.output)
    print(f"Created append-only cohort with {len(players)} players at the original cutoff.")
    print("Tier counts:", dict(sorted(current.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
