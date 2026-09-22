#!/usr/bin/env python3
"""
Riot / League of Legends API feasibility smoke test.

Reads the API key only from RIOT_API_KEY. The key is never written to cache,
logs, CSVs, or reports.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import shutil
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REGIONS = {
    "NA1": "AMERICAS",
    "BR1": "AMERICAS",
    "LA1": "AMERICAS",
    "LA2": "AMERICAS",
    "EUW1": "EUROPE",
    "EUN1": "EUROPE",
    "TR1": "EUROPE",
    "RU": "EUROPE",
    "KR": "ASIA",
    "JP1": "ASIA",
    "OC1": "SEA",
    "PH2": "SEA",
    "SG2": "SEA",
    "TH2": "SEA",
    "TW2": "SEA",
    "VN2": "SEA",
}

RANKED_SR_QUEUE_IDS = {420, 440}
DEFAULT_SEED_TIERS = ("CHALLENGER", "GRANDMASTER", "MASTER")


class RiotAuthError(RuntimeError):
    pass


class RiotClient:
    def __init__(
        self,
        api_key: str,
        platform: str,
        regional: str,
        cache_dir: Path,
        request_log_path: Path,
        sleep: float,
        max_retries: int,
    ) -> None:
        self.api_key = api_key
        self.platform = platform.lower()
        self.regional = regional.lower()
        self.cache_dir = cache_dir
        self.request_log_path = request_log_path
        self.sleep = sleep
        self.max_retries = max_retries
        self.stats = Counter()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_log_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, host_kind: str, path: str, params: dict[str, Any] | None = None) -> Any:
        host = self.platform if host_kind == "platform" else self.regional
        base_url = f"https://{host}.api.riotgames.com"
        query = urllib.parse.urlencode(params or {}, doseq=True)
        path_with_query = f"{path}?{query}" if query else path
        url = f"{base_url}{path_with_query}"
        cache_file = self._cache_file(host_kind, path_with_query)

        if cache_file.exists():
            self.stats["cache_hits"] += 1
            return json.loads(cache_file.read_text(encoding="utf-8"))

        backoff = 1.0
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            if self.sleep:
                time.sleep(self.sleep)

            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "riot-feasibility-smoke-test/0.1",
                    "X-Riot-Token": self.api_key,
                },
            )
            started = time.time()
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
                    status = response.getcode()
                    payload = json.loads(body) if body else {}
                    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    self.stats["http_2xx"] += 1
                    self._log_request(host_kind, path, params, status, attempt, time.time() - started)
                    return payload
            except urllib.error.HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After")
                last_error = f"HTTP {status}"
                self.stats[f"http_{status}"] += 1
                self._log_request(host_kind, path, params, status, attempt, time.time() - started)

                if status == 429:
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                    time.sleep(wait + random.uniform(0, 0.3))
                    backoff = min(backoff * 2, 60)
                    continue
                if status in {500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(backoff + random.uniform(0, 0.3))
                    backoff = min(backoff * 2, 60)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = type(exc).__name__
                self.stats["network_errors"] += 1
                self._log_request(host_kind, path, params, 0, attempt, time.time() - started, error=last_error)
                if attempt < self.max_retries:
                    time.sleep(backoff + random.uniform(0, 0.3))
                    backoff = min(backoff * 2, 60)
                    continue
                raise

        raise RuntimeError(last_error or "Riot request failed")

    def _cache_file(self, host_kind: str, path_with_query: str) -> Path:
        host = self.platform if host_kind == "platform" else self.regional
        digest = hashlib.sha256(f"{host}:{path_with_query}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _log_request(
        self,
        host_kind: str,
        path: str,
        params: dict[str, Any] | None,
        status: int,
        attempt: int,
        elapsed_s: float,
        error: str | None = None,
    ) -> None:
        row = {
            "ts": dt.datetime.now(dt.UTC).isoformat(),
            "host_kind": host_kind,
            "path": path,
            "params": params or {},
            "status": status,
            "attempt": attempt,
            "elapsed_s": round(elapsed_s, 3),
        }
        if error:
            row["error"] = error
        with self.request_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_patch(game_version: str | None) -> str:
    if not game_version:
        return ""
    parts = game_version.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[0])}.{int(parts[1])}"
    return ""


def utc_date_from_ms(timestamp_ms: int | None) -> str:
    if not timestamp_ms:
        return ""
    return dt.datetime.fromtimestamp(timestamp_ms / 1000, tz=dt.UTC).date().isoformat()


def median(values: list[int | float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def seed_ranked_players(client: RiotClient, target_players: int) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    seen: set[str] = set()

    for tier in DEFAULT_SEED_TIERS:
        if tier == "CHALLENGER":
            path = "/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"
        elif tier == "GRANDMASTER":
            path = "/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5"
        else:
            path = "/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5"

        try:
            league = client.get("platform", path)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise RiotAuthError(f"Riot API authentication failed with HTTP {exc.code}. Check RIOT_API_KEY.")
            continue

        entries = league.get("entries", [])
        random.shuffle(entries)
        for entry in entries:
            seed_id = entry.get("puuid") or entry.get("summonerId")
            if not seed_id or seed_id in seen:
                continue
            seen.add(seed_id)
            players.append(
                {
                    "seed_tier": tier,
                    "summonerId": entry.get("summonerId", ""),
                    "puuid": entry.get("puuid", ""),
                    "leaguePoints": entry.get("leaguePoints"),
                    "wins": entry.get("wins"),
                    "losses": entry.get("losses"),
                }
            )
            if len(players) >= target_players:
                return players
    return players


def load_or_create_cohort(
    path: Path,
    client: RiotClient,
    target_players: int,
    queues: tuple[int, ...],
    required_sampling_design: str | None = None,
) -> dict[str, Any]:
    """Persist identities before fetching histories; never silently replace a cohort."""
    if path.exists():
        try:
            cohort = json.loads(path.read_text(encoding="utf-8"))
            players = cohort["players"]
            valid = (
                cohort["schema_version"] == 1
                and cohort["platform"] == client.platform.upper()
                and cohort["queues"] == list(queues)
                and len(players) == target_players
                and isinstance(cohort["end_time"], int)
                and cohort["end_time"] > 0
                and len({p["puuid"] for p in players}) == len(players)
                and len({p["anonymized_player_id"] for p in players}) == len(players)
                and all(p["puuid"] and p["anonymized_player_id"] for p in players)
            )
        except (ValueError, KeyError, TypeError):
            raise ValueError("Invalid cohort file; no identities were changed.") from None
        if not valid:
            raise ValueError("Cohort settings mismatch or invalid identities. Reuse its platform, player count and queues, or choose a different --cohort-file.")
        if required_sampling_design and cohort.get("sampling_design") != required_sampling_design:
            raise ValueError(
                f"Cohort sampling design mismatch. Expected `{required_sampling_design}`, "
                f"found `{cohort.get('sampling_design', '')}`."
            )
        print(f"Reusing fixed cohort: {len(players)} players.")
        return cohort

    end_time = int(time.time())
    players = seed_ranked_players(client, target_players)
    if len(players) != target_players:
        raise ValueError("Not enough seed players. Cohort was not saved; retry later.")
    saved_players = []
    for idx, player in enumerate(players, 1):
        puuid = player.get("puuid")
        if not puuid and player.get("summonerId"):
            result = client.get("platform", f"/lol/summoner/v4/summoners/{urllib.parse.quote(player['summonerId'], safe='')}")
            puuid = result.get("puuid")
        if not puuid:
            raise ValueError("A seed lacks PUUID. Cohort was not saved; retry later.")
        saved_players.append({"anonymized_player_id": f"P{idx:03d}", "puuid": puuid,
                              "seed_tier": player.get("seed_tier", "")})
    if len({p["puuid"] for p in saved_players}) != target_players:
        raise ValueError("Duplicate seed identities. Cohort was not saved.")
    cohort = {"schema_version": 1, "platform": client.platform.upper(),
              "queues": list(queues), "end_time": end_time,
              "created_at": dt.datetime.now(dt.UTC).isoformat(), "players": saved_players}
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting another run's identities.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(cohort, handle, ensure_ascii=False, indent=2)
    print(f"Created fixed cohort: {len(players)} players. Future runs reuse it.")
    return cohort


OUTPUT_NAMES = ("riot_feasibility_matches.csv", "riot_feasibility_summary.csv",
                "riot_patch_coverage.csv", "feasibility_report.md", "failures.json", "run_metadata.json")


def snapshot_outputs(out_dir: Path, label: str) -> None:
    existing = [out_dir / name for name in OUTPUT_NAMES if (out_dir / name).exists()]
    if existing:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = out_dir / "runs" / f"{stamp}_{label}"
        destination.mkdir(parents=True, exist_ok=False)
        for source in existing:
            shutil.copy2(source, destination / source.name)


def match_ids_for_player(
    client: RiotClient,
    puuid: str,
    max_matches: int,
    queues: tuple[int, ...],
    end_time: int | None = None,
) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for queue_id in queues:
        start = 0
        while len(ids) < max_matches:
            count = min(100, max_matches - len(ids))
            if count <= 0:
                break
            path = f"/lol/match/v5/matches/by-puuid/{urllib.parse.quote(puuid, safe='')}/ids"
            params = {"queue": queue_id, "type": "ranked", "start": start, "count": count}
            if end_time is not None:
                params["endTime"] = end_time
            chunk = client.get("regional", path, params)
            if not chunk:
                break
            for match_id in chunk:
                if match_id not in seen:
                    seen.add(match_id)
                    ids.append(match_id)
            if len(chunk) < count:
                break
            start += count
    return ids[:max_matches]


def extract_participant(match: dict[str, Any], puuid: str) -> dict[str, Any] | None:
    info = match.get("info", {})
    metadata = match.get("metadata", {})
    participants = info.get("participants", [])
    participant = next((p for p in participants if p.get("puuid") == puuid), None)
    if not participant:
        return None

    queue_id = info.get("queueId")
    game_mode = info.get("gameMode")
    map_id = info.get("mapId")
    if queue_id not in RANKED_SR_QUEUE_IDS or game_mode != "CLASSIC" or map_id != 11:
        return None

    row = {
        "matchId": metadata.get("matchId", ""),
        "gameStartTimestamp": info.get("gameStartTimestamp", ""),
        "gameCreation": info.get("gameCreation", ""),
        "match_date": utc_date_from_ms(info.get("gameStartTimestamp") or info.get("gameCreation")),
        "gameVersion": info.get("gameVersion", ""),
        "patch": parse_patch(info.get("gameVersion", "")),
        "queueId": queue_id,
        "championName": participant.get("championName", ""),
        "teamPosition": participant.get("teamPosition", ""),
        "individualPosition": participant.get("individualPosition", ""),
        "win": participant.get("win", ""),
        "kills": participant.get("kills", ""),
        "deaths": participant.get("deaths", ""),
        "assists": participant.get("assists", ""),
        "totalDamageDealtToChampions": participant.get("totalDamageDealtToChampions", ""),
        "goldEarned": participant.get("goldEarned", ""),
        "visionScore": participant.get("visionScore", ""),
        "summoner1Id": participant.get("summoner1Id", ""),
        "summoner2Id": participant.get("summoner2Id", ""),
    }
    for idx in range(7):
        row[f"item{idx}"] = participant.get(f"item{idx}", "")
    return row


def summarize(matches: list[dict[str, Any]]) -> dict[str, Any]:
    if not matches:
        return {
            "number_of_matches": 0,
            "earliest_match_date": "",
            "latest_match_date": "",
            "history_span_days": 0,
            "number_of_unique_patches": 0,
            "matches_per_patch": "{}",
            "median_matches_per_patch": 0,
        }

    dates = sorted(dt.date.fromisoformat(m["match_date"]) for m in matches if m.get("match_date"))
    patch_counts = Counter(m.get("patch", "") for m in matches if m.get("patch"))
    span = (dates[-1] - dates[0]).days if dates else 0
    return {
        "number_of_matches": len(matches),
        "earliest_match_date": dates[0].isoformat() if dates else "",
        "latest_match_date": dates[-1].isoformat() if dates else "",
        "history_span_days": span,
        "number_of_unique_patches": len(patch_counts),
        "matches_per_patch": json.dumps(dict(sorted(patch_counts.items())), ensure_ascii=False),
        "median_matches_per_patch": round(median(list(patch_counts.values())), 2),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_report(
    path: Path,
    platform: str,
    regional: str,
    summary_rows: list[dict[str, Any]],
    patch_rows: list[dict[str, Any]],
    request_stats: Counter,
    failures: list[dict[str, Any]],
    target_players: int,
    max_matches_per_player: int,
) -> None:
    successful = [r for r in summary_rows if int(r["number_of_matches"]) > 0]
    match_counts = [int(r["number_of_matches"]) for r in successful]
    spans = [int(r["history_span_days"]) for r in successful]
    patch_counts = [int(r["number_of_unique_patches"]) for r in successful]
    ge3 = sum(1 for value in patch_counts if value >= 3)
    ge5 = sum(1 for value in patch_counts if value >= 5)
    avg_matches = round(sum(match_counts) / len(match_counts), 2) if match_counts else 0
    med_matches = round(median(match_counts), 2)
    med_span = round(median(spans), 2)
    med_patches = round(median(patch_counts), 2)

    coverage_verdict = "insufficient"
    patches_with_enough = [r for r in patch_rows if int(r["players"]) >= 5 and int(r["matches"]) >= 20]
    if patches_with_enough:
        coverage_verdict = "some patches have enough repeated within-player observations"

    feasibility = "high risk"
    if successful and ge3 >= math.ceil(len(successful) * 0.6) and ge5 >= math.ceil(len(successful) * 0.4):
        feasibility = "initially feasible"
    elif successful and ge3 >= math.ceil(len(successful) * 0.5):
        feasibility = "promising but patch depth needs expansion"

    http_failures = {k: v for k, v in sorted(request_stats.items()) if k.startswith("http_") and k != "http_2xx"}
    missing_fields = sum(1 for f in failures if f.get("stage") == "missing_participant_or_filtered")
    lines = [
        "# Riot API Feasibility Smoke Test",
        "",
        f"- Platform routing value: `{platform}`",
        f"- Regional routing value: `{regional}`",
        f"- Target players: {target_players}",
        f"- Max match IDs per player: {max_matches_per_player}",
        f"- Successful players with ranked history: {len(successful)} / {target_players}",
        f"- Average matches per successful player: {avg_matches}",
        f"- Median matches per successful player: {med_matches}",
        f"- Median history span days: {med_span}",
        f"- Median unique patch count: {med_patches}",
        f"- Players covering >=3 patches: {ge3}",
        f"- Players covering >=5 patches: {ge5}",
        f"- Within-player patch coverage assessment: {coverage_verdict}",
        f"- Feasibility verdict: **{feasibility}**",
        "",
        "## Patch Coverage",
        "",
        "| patch | matches | players | median_matches_per_player |",
        "|---|---:|---:|---:|",
    ]
    for row in patch_rows:
        lines.append(
            f"| {row['patch']} | {row['matches']} | {row['players']} | {row['median_matches_per_player']} |"
        )

    lines.extend(
        [
            "",
            "## API And Data Quality Notes",
            "",
            f"- Cache hits: {request_stats.get('cache_hits', 0)}",
            f"- Successful uncached API responses: {request_stats.get('http_2xx', 0)}",
            f"- HTTP failures by status: {json.dumps(http_failures, sort_keys=True)}",
            f"- 429 rate limit events: {request_stats.get('http_429', 0)}",
            f"- 404 events: {request_stats.get('http_404', 0)}",
            f"- Network errors: {request_stats.get('network_errors', 0)}",
            f"- Missing participant / filtered non-standard ranked rows: {missing_fields}",
            "",
            "This smoke test does not assume patch release dates. Patch coverage is parsed from match `gameVersion` as `major.minor`.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Riot LoL longitudinal feasibility smoke test")
    parser.add_argument("--platform", default="NA1", choices=sorted(REGIONS))
    parser.add_argument("--target-players", type=int, default=20)
    parser.add_argument("--max-matches-per-player", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=1.25)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--out-dir", default="riot_feasibility")
    parser.add_argument("--cohort-file", default="riot_feasibility/private/cohort.json",
                        help="Persistent private player list and fixed cutoff. Reused if it exists.")
    parser.add_argument("--queues", default="420,440", help="Comma-separated ranked queue IDs. Use 420 or 420,440.")
    parser.add_argument("--required-sampling-design", default="",
                        help="Optional cohort sampling_design value required when reusing a cohort file.")
    args = parser.parse_args()
    if args.target_players < 1 or args.max_matches_per_player < 1:
        parser.error("Player and match counts must be positive.")
    try:
        queue_ids = tuple(dict.fromkeys(int(q.strip()) for q in args.queues.split(",") if q.strip()))
    except ValueError:
        parser.error("Queues must be integers.")
    if not queue_ids or not set(queue_ids) <= RANKED_SR_QUEUE_IDS:
        parser.error("Only ranked Summoner's Rift queues 420 and 440 are supported.")

    api_key = os.environ.get("RIOT_API_KEY", "").strip()
    if not api_key:
        print("RIOT_API_KEY is not set. Set it in the local environment and rerun.", file=sys.stderr)
        return 2

    platform = args.platform.upper()
    regional = REGIONS[platform]
    out_dir = Path(args.out_dir)
    cache_dir = out_dir / "raw_cache"
    client = RiotClient(
        api_key=api_key,
        platform=platform,
        regional=regional,
        cache_dir=cache_dir,
        request_log_path=out_dir / "request_log.jsonl",
        sleep=args.sleep,
        max_retries=args.max_retries,
    )
    snapshot_outputs(out_dir, "before_run")
    print(f"Loading or creating fixed cohort for {platform}...")
    try:
        required_design = args.required_sampling_design.strip() or None
        cohort = load_or_create_cohort(Path(args.cohort_file), client, args.target_players, queue_ids, required_design)
        seeds = cohort["players"]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RiotAuthError as exc:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "feasibility_report.md").write_text(
            "\n".join(
                [
                    "# Riot API Feasibility Smoke Test",
                    "",
                    f"- Platform routing value: `{platform}`",
                    f"- Regional routing value: `{regional}`",
                    "- Run status: **authentication failed**",
                    f"- Error: {exc}",
                    "",
                    "No player history was fetched, so this run cannot evaluate longitudinal patch coverage.",
                    "The API key is read only from `RIOT_API_KEY`; regenerate or reset the environment variable and rerun.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(exc), file=sys.stderr)
        return 3
    print(f"Seeded {len(seeds)} players.")
    cutoff = dt.datetime.fromtimestamp(cohort["end_time"], tz=dt.UTC).isoformat()
    print(f"Fixed history cutoff (UTC): {cutoff}")

    all_match_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for idx, seed in enumerate(seeds, start=1):
        anon_id = seed["anonymized_player_id"]
        print(f"{anon_id}: resolving PUUID and fetching ranked match history...")
        player_matches: list[dict[str, Any]] = []
        try:
            puuid = seed.get("puuid")
            if not puuid and seed.get("summonerId"):
                summoner = client.get("platform", f"/lol/summoner/v4/summoners/{seed['summonerId']}")
                puuid = summoner.get("puuid")
            if not puuid:
                failures.append({"player": anon_id, "stage": "summoner", "error": "missing_puuid"})
                continue
            ids = match_ids_for_player(client, puuid, args.max_matches_per_player, queue_ids, cohort["end_time"])
            for match_id in ids:
                try:
                    match = client.get("regional", f"/lol/match/v5/matches/{urllib.parse.quote(match_id, safe='')}")
                    row = extract_participant(match, puuid)
                    if row is None:
                        failures.append({"player": anon_id, "matchId": match_id, "stage": "missing_participant_or_filtered"})
                        continue
                    row["anonymized_player_id"] = anon_id
                    player_matches.append(row)
                    all_match_rows.append(row)
                except urllib.error.HTTPError as exc:
                    failures.append({"player": anon_id, "matchId": match_id, "stage": "match_detail", "error": f"HTTP {exc.code}"})
        except urllib.error.HTTPError as exc:
            failures.append({"player": anon_id, "stage": "player", "error": f"HTTP {exc.code}"})
        except Exception as exc:
            failures.append({"player": anon_id, "stage": "player", "error": type(exc).__name__})

        summary = summarize(player_matches)
        summary["anonymized_player_id"] = anon_id
        summary["seed_tier"] = seed.get("seed_tier", "")
        summary_rows.append(summary)

    patch_to_player_counts: dict[str, Counter] = defaultdict(Counter)
    for row in all_match_rows:
        patch = row.get("patch", "")
        player = row.get("anonymized_player_id", "")
        if patch and player:
            patch_to_player_counts[patch][player] += 1

    patch_rows: list[dict[str, Any]] = []
    for patch, player_counts in sorted(patch_to_player_counts.items(), key=lambda entry: tuple(map(int, entry[0].split(".")))):
        counts = list(player_counts.values())
        patch_rows.append(
            {
                "patch": patch,
                "matches": sum(counts),
                "players": len(player_counts),
                "median_matches_per_player": round(median(counts), 2),
            }
        )

    match_fields = [
        "anonymized_player_id",
        "matchId",
        "gameStartTimestamp",
        "gameCreation",
        "match_date",
        "gameVersion",
        "patch",
        "queueId",
        "championName",
        "teamPosition",
        "individualPosition",
        "win",
        "kills",
        "deaths",
        "assists",
        "totalDamageDealtToChampions",
        "goldEarned",
        "visionScore",
        "item0",
        "item1",
        "item2",
        "item3",
        "item4",
        "item5",
        "item6",
        "summoner1Id",
        "summoner2Id",
    ]
    summary_fields = [
        "anonymized_player_id",
        "seed_tier",
        "number_of_matches",
        "earliest_match_date",
        "latest_match_date",
        "history_span_days",
        "number_of_unique_patches",
        "matches_per_patch",
        "median_matches_per_patch",
    ]
    patch_fields = ["patch", "matches", "players", "median_matches_per_player"]

    write_csv(out_dir / "riot_feasibility_matches.csv", all_match_rows, match_fields)
    write_csv(out_dir / "riot_feasibility_summary.csv", summary_rows, summary_fields)
    write_csv(out_dir / "riot_patch_coverage.csv", patch_rows, patch_fields)
    (out_dir / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    render_report(
        out_dir / "feasibility_report.md",
        platform,
        regional,
        summary_rows,
        patch_rows,
        client.stats,
        failures,
        args.target_players,
        args.max_matches_per_player,
    )

    cohort_digest = hashlib.sha256(json.dumps(cohort, sort_keys=True).encode()).hexdigest()[:16]
    metadata = {"cohort_id": cohort_digest, "platform": platform, "queues": list(queue_ids),
                "history_cutoff_utc": cutoff, "max_matches_per_player": args.max_matches_per_player,
                "finished_at": dt.datetime.now(dt.UTC).isoformat(), "players": len(seeds),
                "match_rows": len(all_match_rows), "failure_count": len(failures)}
    (out_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with (out_dir / "feasibility_report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n## Fixed Cohort\n\n- Cohort ID: `{cohort_digest}`\n- History cutoff (UTC): {cutoff}\n- Queues: {list(queue_ids)}\n")
    snapshot_outputs(out_dir, "completed")
    print(f"Wrote {len(all_match_rows)} match rows for {len(summary_rows)} players to {out_dir}.")
    print(f"HTTP stats: {dict(client.stats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
