#!/usr/bin/env python3
"""Evaluate candidate player-experience definitions on a fixed Riot cohort.

This is a feasibility diagnostic. It does not label champion-patch events as
balance changes and does not estimate causal patch effects.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


WINDOWS = (20, 50, 100)
GROUPS = ("observed_new", "low_1_4", "medium_5_14", "high_15_plus")
BIN_SCHEMES = {
    "four_level_0_1_4_5_14_15plus": (("observed_new", 0, 0), ("low_1_4", 1, 4),
                                      ("medium_5_14", 5, 14), ("high_15_plus", 15, None)),
    "three_level_0_1_4_5plus": (("observed_new", 0, 0), ("limited_1_4", 1, 4),
                                 ("established_5plus", 5, None)),
    "three_level_0_1_9_10plus": (("observed_new", 0, 0), ("limited_1_9", 1, 9),
                                  ("established_10plus", 10, None)),
    "binary_0_1plus": (("observed_new", 0, 0), ("previously_used", 1, None)),
}


def patch_key(value: str) -> tuple[int, int]:
    major, minor = value.split(".", 1)
    return int(major), int(minor)


def prior_patch(value: str) -> str | None:
    major, minor = patch_key(value)
    if minor <= 1:
        return None  # exclude season boundaries from this pilot
    return f"{major}.{minor - 1}"


def experience_group(count: int) -> str:
    if count == 0:
        return "observed_new"
    if count <= 4:
        return "low_1_4"
    if count <= 14:
        return "medium_5_14"
    return "high_15_plus"


def binned_group(count: int, scheme: str) -> str:
    for name, lower, upper in BIN_SCHEMES[scheme]:
        if count >= lower and (upper is None or count <= upper):
            return name
    raise ValueError(f"Count {count} is not covered by {scheme}")


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"anonymized_player_id", "matchId", "gameStartTimestamp", "patch", "championName", "win"}
    if not rows or not required <= set(rows[0]):
        raise ValueError(f"Input is empty or lacks required columns: {sorted(required)}")
    for row in rows:
        row["gameStartTimestamp"] = int(row["gameStartTimestamp"])
    return rows


def player_units(rows: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_player[row["anonymized_player_id"]].append(row)

    units: list[dict[str, Any]] = []
    for player, games in by_player.items():
        games.sort(key=lambda row: (row["gameStartTimestamp"], row["matchId"]))
        patches: dict[str, list[int]] = defaultdict(list)
        for index, game in enumerate(games):
            patches[game["patch"]].append(index)

        for patch, indices in patches.items():
            previous = prior_patch(patch)
            if previous is None or previous not in patches:
                continue
            start = min(indices)
            if start < window:
                continue  # require a complete observed history window
            history = games[start - window:start]
            history_counts = Counter(game["championName"] for game in history)
            previous_champions = {games[index]["championName"] for index in patches[previous]}
            post_by_champion: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for index in indices:
                post_by_champion[games[index]["championName"]].append(games[index])
            for champion, post_games in post_by_champion.items():
                count = history_counts[champion]
                wins = sum(str(game["win"]).lower() == "true" for game in post_games)
                units.append({
                    "window": window,
                    "player": player,
                    "patch": patch,
                    "prior_patch": previous,
                    "champion": champion,
                    "event": f"{champion}|{patch}",
                    "history_games": window,
                    "prior_champion_games": count,
                    "experience_group": experience_group(count),
                    "continued_from_prior_patch": champion in previous_champions,
                    "post_matches": len(post_games),
                    "post_wins": wins,
                    "post_win_rate": wins / len(post_games),
                })
    return units


def summarize_window(units: list[dict[str, Any]], window: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        by_event[unit["event"]].append(unit)
    event_rows = []
    for event, members in by_event.items():
        group_counts = Counter(member["experience_group"] for member in members)
        represented = sum(count >= 2 for count in group_counts.values())
        event_rows.append({
            "window": window,
            "event": event,
            "champion": members[0]["champion"],
            "patch": members[0]["patch"],
            "users": len(members),
            "post_matches": sum(member["post_matches"] for member in members),
            **{f"users_{group}": group_counts[group] for group in GROUPS},
            "experience_groups_with_at_least_2_users": represented,
            "pilot_composition_ready": len(members) >= 5 and represented >= 2,
        })
    user_counts = [row["users"] for row in event_rows]
    groups = Counter(unit["experience_group"] for unit in units)
    total = len(units)
    summary = {
        "window": window,
        "eligible_player_champion_patch_units": total,
        "champion_patch_events": len(event_rows),
        "events_with_at_least_5_users": sum(row["users"] >= 5 for row in event_rows),
        "pilot_composition_ready_events": sum(row["pilot_composition_ready"] for row in event_rows),
        "median_users_per_event": round(statistics.median(user_counts), 2) if user_counts else 0,
        "max_users_per_event": max(user_counts, default=0),
        "continued_from_prior_patch_share": round(sum(unit["continued_from_prior_patch"] for unit in units) / total, 4) if total else 0,
        **{f"share_{group}": round(groups[group] / total, 4) if total else 0 for group in GROUPS},
    }
    return summary, event_rows


def stability_rows(units_by_window: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result = []
    for short, long in ((20, 50), (50, 100), (20, 100)):
        short_map = {(u["player"], u["event"]): u for u in units_by_window[short]}
        long_map = {(u["player"], u["event"]): u for u in units_by_window[long]}
        keys = short_map.keys() & long_map.keys()
        exact = sum(short_map[key]["experience_group"] == long_map[key]["experience_group"] for key in keys)
        short_new = [key for key in keys if short_map[key]["experience_group"] == "observed_new"]
        no_longer_new = sum(long_map[key]["experience_group"] != "observed_new" for key in short_new)
        result.append({
            "short_window": short,
            "long_window": long,
            "common_units": len(keys),
            "exact_group_agreement": round(exact / len(keys), 4) if keys else 0,
            "short_window_observed_new_units": len(short_new),
            "short_new_reclassified_with_longer_history": no_longer_new,
            "short_new_reclassification_share": round(no_longer_new / len(short_new), 4) if short_new else 0,
        })
    return result


def bin_scheme_rows(units_by_window: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for window, units in units_by_window.items():
        events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for unit in units:
            events[unit["event"]].append(unit)
        for scheme in BIN_SCHEMES:
            overall = Counter(binned_group(unit["prior_champion_games"], scheme) for unit in units)
            ready = 0
            for members in events.values():
                counts = Counter(binned_group(unit["prior_champion_games"], scheme) for unit in members)
                if len(members) >= 5 and sum(count >= 2 for count in counts.values()) >= 2:
                    ready += 1
            shares = {name: round(overall[name] / len(units), 4) if units else 0
                      for name, _, _ in BIN_SCHEMES[scheme]}
            rows.append({"window": window, "scheme": scheme, "units": len(units),
                         "events": len(events), "pilot_composition_ready_events": ready,
                         "group_shares": json.dumps(shares, sort_keys=True)})
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose candidate experience definitions")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", default="candidate_definitions", type=Path)
    args = parser.parse_args()
    rows = load_rows(args.input)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    units_by_window = {window: player_units(rows, window) for window in WINDOWS}
    summaries, all_events = [], []
    for window in WINDOWS:
        summary, event_rows = summarize_window(units_by_window[window], window)
        summaries.append(summary)
        all_events.extend(event_rows)
    stability = stability_rows(units_by_window)
    bin_schemes = bin_scheme_rows(units_by_window)
    write_csv(args.out_dir / "definition_window_summary.csv", summaries)
    write_csv(args.out_dir / "event_sample_sizes.csv", sorted(all_events, key=lambda r: (r["window"], patch_key(r["patch"]), r["champion"])))
    write_csv(args.out_dir / "definition_stability.csv", stability)
    write_csv(args.out_dir / "group_scheme_summary.csv", bin_schemes)

    by_window = {row["window"]: row for row in summaries}
    recommended = 100
    lines = [
        "# Candidate Experience Definition Diagnostic", "",
        f"Input: `{args.input.as_posix()}`", "",
        "This diagnostic evaluates computability on all observed champion-patch events. It does not identify which champions were changed by official patch notes and makes no causal claim.", "",
        "## Window comparison", "",
        "| Prior match window | Eligible player-event units | Champion-patch events | Events with >=5 users | Pilot composition-ready events | Observed-new share | Median users/event |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(f"| {row['window']} | {row['eligible_player_champion_patch_units']} | {row['champion_patch_events']} | {row['events_with_at_least_5_users']} | {row['pilot_composition_ready_events']} | {row['share_observed_new']:.1%} | {row['median_users_per_event']} |")
    lines.extend(["", "Pilot composition-ready means at least 5 observed users in an event and at least two experience groups containing at least 2 users each.", "", "## Stability", "",
                  "| Windows | Common units | Exact group agreement | Short-window observed-new reclassified |", "|---|---:|---:|---:|"])
    for row in stability:
        lines.append(f"| {row['short_window']} vs {row['long_window']} | {row['common_units']} | {row['exact_group_agreement']:.1%} | {row['short_new_reclassification_share']:.1%} ({row['short_new_reclassified_with_longer_history']}/{row['short_window_observed_new_units']}) |")
    lines.extend(["", "## Group scheme comparison", "",
                  "| Window | Scheme | Pilot composition-ready events | Group shares |", "|---:|---|---:|---|"])
    for row in bin_schemes:
        lines.append(f"| {row['window']} | {row['scheme']} | {row['pilot_composition_ready_events']} | `{row['group_shares']}` |")
    lines.extend(["", "## Provisional decision", "",
                  f"Use {recommended} prior matches as the primary experience window. Use 50 matches as a sensitivity check and reject 20 matches as the primary definition because its observed-new label is unstable against longer history.",
                  "Use prior champion count as the primary continuous/ordinal experience measure. For descriptive tables, prefer three_level_0_1_4_5plus; retain the four-level scheme only if formal expanded sampling supports all cells.",
                  "This decision uses exposure counts and sample support only, not performance outcomes. It should be frozen before inspecting official changed-champion results.",
                  "This diagnostic intentionally uses all observed champion-patch events. Official changed-champion labels are maintained separately and should be joined only after the familiarity definition is frozen.",
                  "Event-level inference remains limited by the currently observed cohort coverage and champion-event sparsity; formal analysis should use the completed composition-aware sample and any planned event-enriched supplementation."])
    (args.out_dir / "candidate_definition_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    metadata = {"input": str(args.input), "input_rows": len(rows), "windows": WINDOWS,
                "group_rules": {"observed_new": 0, "low_1_4": "1-4", "medium_5_14": "5-14", "high_15_plus": ">=15"},
                "season_boundaries_excluded": True}
    (args.out_dir / "diagnostic_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Analyzed {len(rows)} match rows. Wrote diagnostics to {args.out_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
