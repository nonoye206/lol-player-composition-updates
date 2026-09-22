"""Build the official changed-champion event table and pilot expansion test.

The event universe contains only champion headings in the main Summoner's Rift
"Champions" section of Riot's official patch notes. New-champion introductions,
bugfix-only mentions, items, runes, ARAM, Arena, and Classic are excluded.

No API key is read or written by this script.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


PATCHES = {
    "16.1": ("26.1", "2026-01-07", "https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-1-notes", ["Akshan", "Aphelios", "Ashe", "Caitlyn", "Cassiopeia", "Corki", "Draven", "Elise", "Gangplank", "Garen", "Graves", "Jax", "Jhin", "Jinx", "Kindred", "Lucian", "Miss Fortune", "Nilah", "Quinn", "Rengar", "Samira", "Senna", "Shaco", "Sivir", "Smolder", "Tristana", "Tryndamere", "Twitch", "Viego", "Xayah", "Yasuo", "Yone", "Yunara", "Zeri"]),
    "16.2": ("26.2", "2026-01-21", "https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-2-notes", ["Aatrox", "Ashe", "Gwen", "Jayce", "Lillia", "Malphite", "Master Yi", "Nunu & Willump", "Sivir", "Smolder", "Taliyah", "Varus", "Viego", "Zed"]),
    "16.3": ("26.3", "2026-02-03", "https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-3-notes", ["Ahri", "Bel'Veth", "Braum", "Briar", "Diana", "Draven", "Ekko", "Ezreal", "Hecarim", "Heimerdinger", "Jayce", "Kayn", "Maokai", "Mel", "Naafiri", "Nilah", "Riven", "Ryze", "Trundle", "Tryndamere", "Varus", "Vi", "Volibear", "Xin Zhao", "Yone", "Zaahen", "Zed"]),
    "16.4": ("26.4", "2026-02-18", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-4-notes", ["Ambessa", "Annie", "Aphelios", "Brand", "Braum", "Camille", "Darius", "Fizz", "Graves", "Gwen", "Hwei", "Illaoi", "Jinx", "Kassadin", "Kayle", "Kennen", "Lee Sin", "Lux", "Maokai", "Naafiri", "Qiyana", "Rengar", "Rumble", "Ryze", "Samira", "Senna", "Swain", "Syndra", "Teemo", "Twitch", "Udyr", "Xayah", "Zac"]),
    "16.5": ("26.5", "2026-03-03", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-5-notes", ["Akali", "Azir", "Garen", "Lee Sin", "Lillia", "Mel", "Neeko", "Nocturne", "Orianna", "Samira", "Taliyah", "Varus", "Volibear"]),
    "16.6": ("26.6", "2026-03-17", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-6-notes", ["Ahri", "Azir", "Cassiopeia", "Lissandra", "Olaf", "Pyke", "Shen", "Skarner", "Tryndamere", "Zaahen"]),
    "16.7": ("26.7", "2026-03-31", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-7-notes", ["Cassiopeia", "Graves", "Kalista", "Karma", "Nami", "Ornn", "Rell", "Shyvana", "Singed", "Veigar"]),
    "16.8": ("26.8", "2026-04-14", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-8-notes", ["Dr. Mundo", "Hwei", "Karma", "Lillia", "Lucian", "Mel", "Tahm Kench", "Yuumi", "Zilean", "Zyra"]),
    "16.9": ("26.9", "2026-04-28", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-9-notes", ["Ambessa", "Briar", "Ezreal", "Gragas", "Kennen", "Shyvana", "Tahm Kench", "Taliyah", "Teemo", "Udyr", "Warwick", "Xin Zhao", "Zeri", "Zoe"]),
    "16.10": ("26.10", "2026-05-12", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-10-notes", ["Ambessa", "Anivia", "Ashe", "Galio", "Lee Sin", "Naafiri", "Quinn", "Shyvana", "Wukong", "Zed", "Zeri"]),
    "16.11": ("26.11", "2026-05-27", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-11-notes/", ["Brand", "Diana", "Ekko", "Heimerdinger", "Kassadin", "Quinn", "Smolder", "Teemo", "Xin Zhao"]),
    "16.12": ("26.12", "2026-06-09", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-12-notes/", ["Aatrox", "Gwen", "Hwei", "Jax", "Lee Sin", "Nocturne", "Orianna", "Ryze", "Sylas", "Syndra", "Tristana", "Varus", "Xin Zhao", "Yuumi"]),
    "16.13": ("26.13", "2026-06-23", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-13-notes/", ["Aphelios", "Bard", "Brand", "Cassiopeia", "Draven", "Kai'Sa", "K'Sante", "LeBlanc", "Olaf", "Poppy", "Qiyana", "Rek'Sai", "Rumble", "Senna", "Sion", "Vex", "Zaahen"]),
    "16.14": ("26.14", "2026-07-14", "https://www.leagueoflegends.com/en-au/news/game-updates/league-of-legends-patch-26-14-notes/", ["Azir", "Corki", "Garen", "Jayce", "Locke", "Mordekaiser", "Nami", "Senna", "Seraphine", "Yunara"]),
    "16.15": ("26.15", "2026-07-28", "https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-15-notes/", ["Alistar", "Bel'Veth", "Kai'Sa", "Locke", "Maokai", "Mordekaiser", "Naafiri", "Riven", "Sylas", "Volibear", "Zac"]),
    "16.16": ("26.16", "2026-08-11", "https://www.leagueoflegends.com/en-au/news/game-updates/league-of-legends-patch-26-16-notes/", ["Azir", "Bel'Veth", "Camille", "Gwen", "Kennen", "Nasus", "Poppy"]),
    "16.17": ("26.17", "2026-08-25", "https://www.leagueoflegends.com/en-gb/news/game-updates/league-of-legends-patch-26-17-notes/", ["Aurelion Sol", "Cho'Gath", "Graves", "Irelia", "LeBlanc", "Nasus", "Nocturne", "Qiyana", "Thresh", "Trundle", "Vayne", "Xerath", "Yasuo", "Yone"]),
}


def patch_key(p: str) -> tuple[int, int]:
    a, b = p.split(".")[:2]
    return int(a), int(b)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def binomial_tail(n: int, p: float, threshold: int) -> float:
    if threshold <= 0:
        return 1.0
    if threshold > n or p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return sum(math.comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(threshold, n + 1))


def load_matches(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["ts"] = int(row["gameStartTimestamp"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=Path, default=Path("riot_feasibility/runs/20260906T050304184130Z_completed/riot_feasibility_matches.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("patch_changes"))
    ap.add_argument("--prior-window", type=int, default=100)
    ap.add_argument("--min-eligible-players", type=int, default=10)
    ap.add_argument("--intended-cohort-size", type=int, default=20)
    args = ap.parse_args()

    matches = load_matches(args.matches)
    players = sorted({r["anonymized_player_id"] for r in matches})
    if not players:
        raise ValueError("No players with match history were found")

    official = []
    for api_patch in sorted(PATCHES, key=patch_key):
        riot_patch, published, url, champions = PATCHES[api_patch]
        for champion in champions:
            official.append({
                "api_patch": api_patch,
                "riot_patch": riot_patch,
                "published_date_utc": published,
                "champion_name": champion,
                "event_id": f"{champion}|{api_patch}",
                "source_url": url,
                "source_section": "Champions (Summoner's Rift)",
                "inclusion_rule": "named champion heading with gameplay/balance change in main Champions section",
            })

    by_player = defaultdict(list)
    for r in matches:
        by_player[r["anonymized_player_id"]].append(r)
    for games in by_player.values():
        games.sort(key=lambda x: (x["ts"], x["matchId"]))
    player_match_counts = {p: len(games) for p, games in by_player.items()}

    # A player is experience-eligible for a patch if at least prior_window matches
    # occur before that player's first observed match in the patch.
    eligible = defaultdict(set)
    for player, games in by_player.items():
        first_index = {}
        for i, game in enumerate(games):
            first_index.setdefault(game["patch"], i)
        for patch, i in first_index.items():
            if i >= args.prior_window:
                eligible[patch].add(player)

    raw_users = defaultdict(set)
    eligible_users = defaultdict(set)
    for r in matches:
        key = (r["patch"], r["championName"])
        raw_users[key].add(r["anonymized_player_id"])
        if r["anonymized_player_id"] in eligible[r["patch"]]:
            eligible_users[key].add(r["anonymized_player_id"])

    patch_match_users = defaultdict(set)
    for r in matches:
        patch_match_users[r["patch"]].add(r["anonymized_player_id"])

    coverage = []
    for event in official:
        patch, champion = event["api_patch"], event["champion_name"]
        n_eligible = len(eligible[patch])
        coverage.append({
            **event,
            "pilot_players": len(players),
            "players_with_any_match_in_patch": len(patch_match_users[patch]),
            "players_with_100_prior_matches_at_patch": n_eligible,
            "raw_users_event": len(raw_users[(patch, champion)]),
            "experience_eligible_users_event": len(eligible_users[(patch, champion)]),
            "analysis_ready_patch": n_eligible >= args.min_eligible_players,
        })

    ready = [r for r in coverage if r["analysis_ready_patch"]]
    if not ready:
        raise ValueError("No analysis-ready patches under the requested eligibility rule")

    expansion = []
    for basis, field in [("raw", "raw_users_event"), ("experience_eligible_100", "experience_eligible_users_event")]:
        rates = [r[field] / len(players) for r in ready]
        for n in list(dict.fromkeys([len(players), 100, 300, 500])):
            expected_counts = [n * p for p in rates]
            ge10 = sum(binomial_tail(n, p, 10) for p in rates)
            ge20 = sum(binomial_tail(n, p, 20) for p in rates)
            expansion.append({
                "basis": basis,
                "target_players": n,
                "official_changed_events": len(ready),
                "analysis_ready_patches": len({r["api_patch"] for r in ready}),
                "projected_median_users_per_event": round(statistics.median(expected_counts), 2),
                "expected_events_ge_10_users": round(ge10, 2),
                "expected_share_events_ge_10_users": round(ge10 / len(ready), 4),
                "expected_events_ge_20_users": round(ge20, 2),
                "expected_share_events_ge_20_users": round(ge20 / len(ready), 4),
                "projection_model": "event-specific Binomial(N, pilot_rate); zero-observed events remain zero",
            })

    out = args.out_dir
    write_csv(out / "official_changed_champion_patch_table.csv", official)
    write_csv(out / "pilot_changed_event_coverage.csv", coverage)
    write_csv(out / "sample_size_expansion_test.csv", expansion)

    ready_patches = sorted({r["api_patch"] for r in ready}, key=patch_key)
    primary = [r for r in expansion if r["basis"] == "experience_eligible_100"]
    primary_by_target = {r["target_players"]: r for r in primary}
    zero = sum(r["experience_eligible_users_event"] == 0 for r in ready)
    pilot_counts = [r["experience_eligible_users_event"] for r in ready]
    patch_diagnostics = []
    for patch in ready_patches:
        members = [r for r in ready if r["api_patch"] == patch]
        counts = [r["experience_eligible_users_event"] for r in members]
        patch_diagnostics.append({
            "patch": patch,
            "events": len(members),
            "eligible_players": members[0]["players_with_100_prior_matches_at_patch"],
            "median": statistics.median(counts),
            "zero": sum(x == 0 for x in counts),
        })
    report = [
        "# Changed-champion event coverage and sample-size expansion",
        "",
        "## Event definition",
        "",
        f"The official event table contains **{len(official)}** true champion × patch events across API patches 16.1–16.17 (Riot labels 26.1–26.17). The 16.x → 26.x mapping is explicit because Match-V5/Data Dragon use 16.x while the public patch-note titles use 26.x in 2026.",
        "",
        "Included: named champion headings in the first, main Summoner's Rift `Champions` section of Riot's official patch notes. Excluded: new-champion introduction text unless the champion also has a balance heading, bugfix-only mentions, items, runes, systems, ARAM, Arena, and Classic.",
        "",
        "## Pilot coverage",
        "",
        f"Input: fixed NA1 cohort, {len(players)}/{args.intended_cohort_size} players with match history, {len(matches):,} ranked Solo/Duo match rows, maximum observed player history {max(player_match_counts.values())} matches, fixed cutoff. For the primary experience-ready count, a player must have at least {args.prior_window} observed matches before their first match in that patch.",
        "",
        f"Patches meeting the pilot support rule (at least {args.min_eligible_players}/{len(players)} observed players with a complete 100-match prior window): **{', '.join(ready_patches)}**. These contain **{len(ready)}** official changed-champion events.",
        "",
        f"Across these events, median experience-eligible users/event is **{statistics.median(pilot_counts):g}**; **{zero}/{len(ready)} ({zero/len(ready):.1%})** have zero eligible users in the {len(players)}-player pilot; **{sum(x >= 10 for x in pilot_counts)}** reach 10 users and **{sum(x >= 20 for x in pilot_counts)}** reach 20 users.",
        "",
        "| API patch | Official changed events | Players with complete 100-match history | Median eligible users/event | Zero-user events |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in patch_diagnostics:
        report.append(f"| {r['patch']} | {r['events']} | {r['eligible_players']} | {r['median']:g} | {r['zero']} |")
    report += [
        "",
        "## Expansion projection",
        "",
        f"Primary projection uses each event's observed rate in the {len(players)}-player observed pilot and an event-specific Binomial(N, pilot rate). Reported threshold totals are expected numbers of events, so they may be fractional. Events unseen in the pilot retain probability zero; this makes rare/newly observed champions a conservative blind spot rather than inventing prevalence.",
        "",
        "| Target players | Median eligible users/event | Expected events ≥10 | Share ≥10 | Expected events ≥20 | Share ≥20 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in primary:
        report.append(f"| {r['target_players']} | {r['projected_median_users_per_event']:.2f} | {r['expected_events_ge_10_users']:.2f} | {r['expected_share_events_ge_10_users']:.1%} | {r['expected_events_ge_20_users']:.2f} | {r['expected_share_events_ge_20_users']:.1%} |")
    report += [
        "",
        "## Interpretation",
        "",
        "This test estimates scaling under the current NA1 player mix. It does not prove what a newly sampled 300/500-player cohort will contain. Champion use is clustered by role, mastery, rank, and patch, so the sampling design can shift event rates materially.",
        "",
        f"The {len(players)}-player cohort is a screening stage. Based on its observed rates, at 300 players an estimated {primary_by_target[300]['expected_share_events_ge_10_users']:.1%} of supported events reach 10 eligible users and {primary_by_target[300]['expected_share_events_ge_20_users']:.1%} reach 20. At 500 players, the corresponding estimates are {primary_by_target[500]['expected_share_events_ge_10_users']:.1%} and {primary_by_target[500]['expected_share_events_ge_20_users']:.1%}. The projection remains conservative because {zero}/{len(ready)} events have zero eligible users in the pilot and no prevalence is invented for them.",
        "",
        "For the main study, use a two-frame design: (1) a broad cohort stratified by rank and role for population-composition estimates, and (2) an event-enriched supplemental cohort for sparse changed champions. Record inclusion probabilities and use sampling weights when estimating population composition. Expanding without rank and role balance would raise counts while preserving sampling bias.",
        "",
        "## Reproducibility",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()} from `{args.matches.as_posix()}`. No API key or PUUID is written to these outputs.",
    ]
    (out / "sample_size_expansion_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    metadata = {
        "input": str(args.matches), "input_match_rows": len(matches), "pilot_players_with_history": len(players),
        "intended_cohort_size": args.intended_cohort_size, "max_observed_matches_per_player": max(player_match_counts.values()),
        "prior_window": args.prior_window, "min_eligible_players_per_patch": args.min_eligible_players,
        "official_events": len(official), "analysis_ready_events": len(ready), "analysis_ready_patches": ready_patches,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / "analysis_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
