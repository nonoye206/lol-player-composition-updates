#!/usr/bin/env python3
"""Build RQ1 composition tables and overview figures.

RQ1 only asks whether the users of officially changed champions differ before
and after a patch. This script deliberately does not read or analyze gameplay
performance outcomes such as win, KDA, damage, gold, or vision.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


RANKS = ("GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER+")
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
SEASON_PREDECESSORS = {"16.1": "15.24"}
REQUIRED_MATCH_COLUMNS = {
    "anonymized_player_id",
    "matchId",
    "gameStartTimestamp",
    "patch",
    "championName",
}


def patch_key(value: str) -> tuple[int, int]:
    major, minor = value.split(".", 1)
    return int(major), int(minor)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str] | None = None) -> None:
    names = list(fieldnames or (rows[0].keys() if rows else []))
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def percentile(values: list[int], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def familiarity_group(count: int) -> str:
    if count == 0:
        return "observed_new"
    if count <= 4:
        return "limited_1_4"
    return "established_5plus"


def safe_share(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def difference(post: float | None, pre: float | None) -> float | None:
    return post - pre if post is not None and pre is not None else None


def percentage_point_difference(post: float | None, pre: float | None) -> float | None:
    value = difference(post, pre)
    return value * 100 if value is not None else None


def load_cohort(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        players = {}
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                player = row["anonymized_player_id"]
                rank = row["rank_stratum"].upper()
                role = row["primary_role"].upper()
                if rank not in RANKS or role not in ROLES:
                    raise ValueError(f"Invalid cohort stratum for {player}: rank={rank!r}, role={role!r}")
                players[player] = {"rank_stratum": rank, "primary_role": role}
        return players, {"source": "anonymized cohort metadata", "players": len(players)}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    players = {}
    for row in payload["players"]:
        player = row["anonymized_player_id"]
        rank = (row.get("seed_stratum") or row.get("seed_tier") or "").upper()
        rank = {"MASTER_PLUS": "MASTER+", "MASTER PLUS": "MASTER+"}.get(rank, rank)
        role = (row.get("primary_role") or "").upper()
        if rank not in RANKS or role not in ROLES:
            raise ValueError(f"Invalid cohort stratum for {player}: rank={rank!r}, role={role!r}")
        players[player] = {"rank_stratum": rank, "primary_role": role}
    safe_metadata = {
        "sampling_design": payload.get("sampling_design"),
        "platform": payload.get("platform"),
        "queues": payload.get("queues"),
        "end_time": payload.get("end_time"),
        "players": len(players),
    }
    return players, safe_metadata


def load_matches(path: Path, cohort: dict[str, dict[str, str]]) -> tuple[dict[str, list[dict[str, Any]]], list[str], int]:
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    duplicates = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not REQUIRED_MATCH_COLUMNS <= set(reader.fieldnames):
            raise ValueError(f"Match input lacks required columns: {sorted(REQUIRED_MATCH_COLUMNS)}")
        for raw in reader:
            player = raw["anonymized_player_id"]
            if player not in cohort:
                continue
            identity = (player, raw["matchId"])
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            by_player[player].append({
                "player_id": player,
                "match_id": raw["matchId"],
                "timestamp": int(raw["gameStartTimestamp"]),
                "patch": raw["patch"],
                "champion": raw["championName"],
            })
    for games in by_player.values():
        games.sort(key=lambda row: (row["timestamp"], row["match_id"]))
    patches = sorted({game["patch"] for games in by_player.values() for game in games}, key=patch_key)
    return by_player, patches, duplicates


def immediately_preceding_patch(patch: str) -> str:
    if patch in SEASON_PREDECESSORS:
        return SEASON_PREDECESSORS[patch]
    major, minor = patch_key(patch)
    if minor <= 1:
        raise ValueError(f"No validated season-boundary predecessor for {patch}")
    return f"{major}.{minor - 1}"


def load_events(path: Path, observed_patches: list[str]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    rows = read_csv(path)
    required = {"api_patch", "champion_name", "event_id"}
    if not rows or not required <= set(rows[0]):
        raise ValueError(f"Official event table lacks required columns: {sorted(required)}")
    observed = set(observed_patches)
    events = []
    validation = []
    seen = set()
    for row in rows:
        patch = row["api_patch"]
        champion = row["champion_name"]
        identity = (champion, patch)
        if identity in seen:
            raise ValueError(f"Duplicate official event: {champion}|{patch}")
        seen.add(identity)
        pre_patch = immediately_preceding_patch(patch)
        pre_patch_observed = pre_patch in observed
        events.append({
            "event_id": row.get("event_id") or f"{champion}|{patch}",
            "champion": champion,
            "patch": patch,
            "pre_patch": pre_patch,
            "pre_patch_observed": pre_patch_observed,
            "change_direction": row.get("change_direction", ""),
        })
        validation.append({
            "event_id": row.get("event_id") or f"{champion}|{patch}",
            "champion": champion,
            "patch": patch,
            "expected_immediately_preceding_patch": pre_patch,
            "pre_patch_observed_in_match_data": pre_patch_observed,
            "cross_patch_fallback_used": False,
            "eligible_for_pre_post_comparison": pre_patch_observed,
        })
    return (
        sorted(events, key=lambda row: (patch_key(row["patch"]), row["champion"])),
        sorted(validation, key=lambda row: (patch_key(row["patch"]), row["champion"])),
    )


def make_player_period_rows(
    matches_by_player: dict[str, list[dict[str, Any]]],
    cohort: dict[str, dict[str, str]],
    events: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    event_lookup = {(event["champion"], event["patch"]): event for event in events}
    event_by_pre = defaultdict(list)
    for event in events:
        if event["pre_patch"]:
            event_by_pre[(event["champion"], event["pre_patch"])].append(event)

    rows_by_event_player: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for player, games in matches_by_player.items():
        positions_by_patch_champion: dict[tuple[str, str], list[int]] = defaultdict(list)
        for index, game in enumerate(games):
            positions_by_patch_champion[(game["champion"], game["patch"])].append(index)

        relevant: list[tuple[dict[str, str], str, list[int]]] = []
        for (champion, patch), indices in positions_by_patch_champion.items():
            post_event = event_lookup.get((champion, patch))
            if post_event:
                relevant.append((post_event, "post", indices))
            for pre_event in event_by_pre.get((champion, patch), []):
                relevant.append((pre_event, "pre", indices))

        for event, period, indices in relevant:
            first_index = min(indices)
            prior_100 = None
            prior_50 = None
            if first_index >= 100:
                prior_100 = sum(game["champion"] == event["champion"] for game in games[first_index - 100:first_index])
            if first_index >= 50:
                prior_50 = sum(game["champion"] == event["champion"] for game in games[first_index - 50:first_index])
            rows_by_event_player[(event["event_id"], player)][period] = {
                "event_id": event["event_id"],
                "player_id": player,
                "champion": event["champion"],
                "patch": event["patch"],
                "pre_patch": event["pre_patch"],
                "change_direction": event["change_direction"],
                "period": period,
                "matches_in_period": len(indices),
                "rank_stratum": cohort[player]["rank_stratum"],
                "primary_role": cohort[player]["primary_role"],
                "prior_champion_count_100": prior_100,
                "familiarity_group_100": familiarity_group(prior_100) if prior_100 is not None else "",
                "experience_eligible_100": prior_100 is not None,
                "prior_champion_count_50": prior_50,
                "familiarity_group_50": familiarity_group(prior_50) if prior_50 is not None else "",
                "experience_eligible_50": prior_50 is not None,
            }

    flat_rows = []
    membership: dict[str, dict[str, Any]] = defaultdict(dict)
    for (event_id, player), periods in rows_by_event_player.items():
        status = "both" if {"pre", "post"} <= periods.keys() else "pre_only" if "pre" in periods else "post_only"
        membership[event_id][player] = {"status": status, "periods": periods}
        for period in ("pre", "post"):
            if period in periods:
                row = dict(periods[period])
                row["participation_status"] = status
                flat_rows.append(row)
    flat_rows.sort(key=lambda row: (patch_key(row["patch"]), row["champion"], row["player_id"], row["period"]))
    return flat_rows, membership


def participation_summary(events: list[dict[str, str]], membership: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        members = membership.get(event["event_id"], {})
        counts = Counter(item["status"] for item in members.values())
        union = len(members)
        pre_users = counts["pre_only"] + counts["both"]
        post_users = counts["post_only"] + counts["both"]
        rows.append({
            **event,
            "n_union_users": union,
            "n_pre_users": pre_users,
            "n_post_users": post_users,
            "n_pre_only": counts["pre_only"],
            "n_both": counts["both"],
            "n_post_only": counts["post_only"],
            "pre_only_among_union": safe_share(counts["pre_only"], union),
            "both_among_union": safe_share(counts["both"], union),
            "post_only_among_union": safe_share(counts["post_only"], union),
            "pre_only_among_pre": safe_share(counts["pre_only"], pre_users),
            "post_only_among_post": safe_share(counts["post_only"], post_users),
            "continuation_rate": safe_share(counts["both"], pre_users),
        })
    return rows


def period_familiarity(values: list[int]) -> dict[str, Any]:
    counts = Counter(familiarity_group(value) for value in values)
    n = len(values)
    return {
        "experience_eligible": n,
        "mean_prior_champion_count": statistics.fmean(values) if values else None,
        "median_prior_champion_count": statistics.median(values) if values else None,
        "p25_prior_champion_count": percentile(values, 0.25),
        "p75_prior_champion_count": percentile(values, 0.75),
        "observed_new_share": safe_share(counts["observed_new"], n),
        "limited_1_4_share": safe_share(counts["limited_1_4"], n),
        "established_5plus_share": safe_share(counts["established_5plus"], n),
    }


def familiarity_summary(events: list[dict[str, str]], player_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in player_rows:
        value = row["prior_champion_count_100"]
        if value is not None:
            grouped[(row["event_id"], row["period"])].append(value)
    output = []
    metrics = (
        "mean_prior_champion_count", "median_prior_champion_count", "p25_prior_champion_count",
        "p75_prior_champion_count", "observed_new_share", "limited_1_4_share", "established_5plus_share",
    )
    for event in events:
        pre = period_familiarity(grouped.get((event["event_id"], "pre"), []))
        post = period_familiarity(grouped.get((event["event_id"], "post"), []))
        row: dict[str, Any] = {**event}
        for metric, value in pre.items():
            row[f"pre_{metric}"] = value
        for metric, value in post.items():
            row[f"post_{metric}"] = value
        for metric in metrics:
            suffix = "_pp" if metric.endswith("_share") else ""
            row[f"delta_{metric}{suffix}"] = (
                percentage_point_difference(post[metric], pre[metric])
                if metric.endswith("_share") else difference(post[metric], pre[metric])
            )
        output.append(row)
    return output


def tvd(pre_counts: Counter[str], post_counts: Counter[str], categories: tuple[str, ...]) -> float | None:
    pre_total = sum(pre_counts[category] for category in categories)
    post_total = sum(post_counts[category] for category in categories)
    if not pre_total or not post_total:
        return None
    return 0.5 * sum(abs(pre_counts[category] / pre_total - post_counts[category] / post_total) for category in categories)


def rank_role_summary(events: list[dict[str, str]], player_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, float | None]]]:
    lookup: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for row in player_rows:
        lookup[(row["event_id"], "rank", row["period"])][row["rank_stratum"]] += 1
        lookup[(row["event_id"], "role", row["period"])][row["primary_role"]] += 1
    long_rows = []
    event_tvds: dict[str, dict[str, float | None]] = defaultdict(dict)
    for event in events:
        for dimension, categories in (("rank", RANKS), ("role", ROLES)):
            pre = lookup[(event["event_id"], dimension, "pre")]
            post = lookup[(event["event_id"], dimension, "post")]
            pre_total = sum(pre.values())
            post_total = sum(post.values())
            event_tvd = tvd(pre, post, categories)
            event_tvds[event["event_id"]][f"{dimension}_tvd"] = event_tvd
            for category in categories:
                pre_share = safe_share(pre[category], pre_total)
                post_share = safe_share(post[category], post_total)
                long_rows.append({
                    **event,
                    "dimension": dimension,
                    "category": category,
                    "pre_users": pre[category],
                    "post_users": post[category],
                    "pre_share": pre_share,
                    "post_share": post_share,
                    "delta_percentage_points": percentage_point_difference(post_share, pre_share),
                    "tvd": event_tvd,
                })
    return long_rows, event_tvds


def merge_event_summary(
    participation: list[dict[str, Any]],
    familiarity: list[dict[str, Any]],
    event_tvds: dict[str, dict[str, float | None]],
) -> list[dict[str, Any]]:
    familiarity_by_event = {row["event_id"]: row for row in familiarity}
    output = []
    for part in participation:
        fam = familiarity_by_event[part["event_id"]]
        tvds = event_tvds.get(part["event_id"], {})
        output.append({
            "event_id": part["event_id"],
            "champion": part["champion"],
            "patch": part["patch"],
            "pre_patch": part["pre_patch"],
            "change_direction": part["change_direction"],
            "n_pre_users": part["n_pre_users"],
            "n_post_users": part["n_post_users"],
            "n_pre_only": part["n_pre_only"],
            "n_both": part["n_both"],
            "n_post_only": part["n_post_only"],
            "pre_only_among_union": part["pre_only_among_union"],
            "both_among_union": part["both_among_union"],
            "post_only_among_union": part["post_only_among_union"],
            "pre_only_among_pre": part["pre_only_among_pre"],
            "post_only_among_post": part["post_only_among_post"],
            "continuation_rate": part["continuation_rate"],
            "pre_observed_new_share": fam["pre_observed_new_share"],
            "post_observed_new_share": fam["post_observed_new_share"],
            "delta_observed_new_pp": fam["delta_observed_new_share_pp"],
            "pre_established_share": fam["pre_established_5plus_share"],
            "post_established_share": fam["post_established_5plus_share"],
            "delta_established_pp": fam["delta_established_5plus_share_pp"],
            "rank_tvd": tvds.get("rank_tvd"),
            "role_tvd": tvds.get("role_tvd"),
            "experience_eligible_pre": fam["pre_experience_eligible"],
            "experience_eligible_post": fam["post_experience_eligible"],
            "higher_support_view": part["n_pre_users"] >= 10 and part["n_post_users"] >= 10,
        })
    return output


def plot_overviews(
    event_summary: list[dict[str, Any]], out_dir: Path, filename_suffix: str = "", title_suffix: str = ""
) -> dict[str, int]:
    from PIL import Image, ImageDraw, ImageFont

    def present(metric: str) -> list[float]:
        return [float(row[metric]) for row in event_summary if row[metric] not in (None, "")]

    def font(size: int, bold: bool = False):
        path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            return ImageFont.load_default()

    def histogram(values: list[float], bins: int = 20) -> tuple[list[int], float, float]:
        low, high = min(values), max(values)
        if low == high:
            low -= 0.5
            high += 0.5
        counts = [0] * bins
        for value in values:
            index = min(bins - 1, int((value - low) / (high - low) * bins))
            counts[index] += 1
        return counts, low, high

    def draw_histogram(series: list[tuple[str, list[float], str]], title: str, xlabel: str, filename: str, zero_line: bool = False) -> None:
        width, height = 1440, 900
        left, right, top, bottom = 130, 70, 110, 120
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image, "RGBA")
        all_values = [value for _, values, _ in series for value in values]
        if not all_values:
            draw.text((left, top), "No eligible events", fill="#333333", font=font(28))
            image.save(out_dir / filename)
            return
        global_low, global_high = min(all_values), max(all_values)
        if global_low == global_high:
            global_low -= 0.5
            global_high += 0.5
        bins = 20
        all_counts = []
        for _, values, _ in series:
            counts = [0] * bins
            for value in values:
                index = min(bins - 1, int((value - global_low) / (global_high - global_low) * bins))
                counts[index] += 1
            all_counts.append(counts)
        max_count = max(max(counts, default=0) for counts in all_counts) or 1
        plot_width = width - left - right
        plot_height = height - top - bottom
        draw.line((left, top, left, top + plot_height), fill="#333333", width=3)
        draw.line((left, top + plot_height, left + plot_width, top + plot_height), fill="#333333", width=3)
        for tick in range(6):
            y = top + plot_height - tick * plot_height / 5
            count_value = max_count * tick / 5
            draw.line((left, y, left + plot_width, y), fill="#D9D9D9", width=1)
            draw.text((35, y - 12), f"{count_value:.0f}", fill="#444444", font=font(22))
        group_width = plot_width / bins
        for series_index, ((label, _, color), counts) in enumerate(zip(series, all_counts)):
            bar_width = group_width / len(series)
            for index, count in enumerate(counts):
                x0 = left + index * group_width + series_index * bar_width + 1
                x1 = x0 + bar_width - 2
                y0 = top + plot_height - (count / max_count) * plot_height
                draw.rectangle((x0, y0, x1, top + plot_height), fill=color)
        if zero_line and global_low <= 0 <= global_high:
            x = left + (0 - global_low) / (global_high - global_low) * plot_width
            draw.line((x, top, x, top + plot_height), fill="#111111", width=3)
        for tick in range(6):
            value = global_low + (global_high - global_low) * tick / 5
            x = left + plot_width * tick / 5
            draw.text((x - 35, top + plot_height + 18), f"{value:.2f}", fill="#444444", font=font(20))
        draw.text((left, 30), title, fill="#222222", font=font(34, bold=True))
        draw.text((left + plot_width / 2 - 160, height - 55), xlabel, fill="#333333", font=font(24))
        draw.text((18, top + plot_height / 2), "Events", fill="#333333", font=font(24))
        if len(series) > 1:
            legend_x = width - 360
            for index, (label, _, color) in enumerate(series):
                y = 45 + index * 38
                draw.rectangle((legend_x, y, legend_x + 24, y + 24), fill=color)
                draw.text((legend_x + 35, y - 2), label, fill="#333333", font=font(22))
        image.save(out_dir / filename)

    figures = [
        ("post_only_among_union", f"Post-only share across champion-patch events{title_suffix}", "Post-only among union", f"rq1_post_only_share_distribution{filename_suffix}.png"),
        ("delta_observed_new_pp", f"Change in observed-new share{title_suffix}", "Post minus pre (percentage points)", f"rq1_observed_new_change_distribution{filename_suffix}.png"),
    ]
    counts = {}
    for metric, title, xlabel, filename in figures:
        values = present(metric)
        counts[metric] = len(values)
        draw_histogram([("Events", values, "#3465A4")], title, xlabel, filename, metric.startswith("delta_"))

    rank = present("rank_tvd")
    role = present("role_tvd")
    counts["rank_tvd"] = len(rank)
    counts["role_tvd"] = len(role)
    draw_histogram(
        [("Rank TVD", rank, "#4C78A8"), ("Role TVD", role, "#F58518")],
        f"Rank and role composition shift{title_suffix}", "Total Variation Distance", f"rq1_rank_role_tvd_distribution{filename_suffix}.png",
    )
    return counts


def plot_support_scatter(event_summary: list[dict[str, Any]], out_dir: Path) -> int:
    from PIL import Image, ImageDraw, ImageFont

    def font(size: int, bold: bool = False):
        path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            return ImageFont.load_default()

    panels = (
        ("rank_tvd", "Rank TVD", 0.0, 1.0, "#4C78A8"),
        ("role_tvd", "Role TVD", 0.0, 1.0, "#F58518"),
        ("delta_observed_new_pp", "Absolute observed-new change (pp)", 0.0, 100.0, "#54A24B"),
    )
    rows = [row for row in event_summary if row["n_pre_users"] > 0 and row["n_post_users"] > 0]
    max_support = max(min(row["n_pre_users"], row["n_post_users"]) for row in rows)
    max_log = math.log10(max_support)
    width, height = 1500, 1500
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    left, right, top = 160, 70, 105
    panel_height, gap = 350, 95
    plot_width = width - left - right
    x_ticks = [1, 2, 5, 10, 20, 50, 100]
    x_ticks = [value for value in x_ticks if value <= max_support]
    draw.text((left, 28), "Event support versus measured composition shift", fill="#222222", font=font(38, True))
    for panel_index, (metric, ylabel, y_min, y_max, color) in enumerate(panels):
        y_top = top + panel_index * (panel_height + gap)
        y_bottom = y_top + panel_height
        draw.line((left, y_top, left, y_bottom), fill="#333333", width=3)
        draw.line((left, y_bottom, left + plot_width, y_bottom), fill="#333333", width=3)
        for tick in range(5):
            y_value = y_min + (y_max - y_min) * tick / 4
            y = y_bottom - panel_height * tick / 4
            draw.line((left, y, left + plot_width, y), fill="#D9D9D9", width=1)
            draw.text((55, y - 12), f"{y_value:.0f}" if y_max > 1 else f"{y_value:.2f}", fill="#444444", font=font(20))
        for x_value in x_ticks:
            x = left + math.log10(x_value) / max_log * plot_width if max_log else left
            draw.line((x, y_top, x, y_bottom), fill="#EEEEEE", width=1)
            if panel_index == len(panels) - 1:
                draw.text((x - 13, y_bottom + 16), str(x_value), fill="#444444", font=font(20))
        if max_support >= 10:
            threshold_x = left + math.log10(10) / max_log * plot_width
            draw.line((threshold_x, y_top, threshold_x, y_bottom), fill="#222222", width=3)
        for row in rows:
            value = row[metric]
            if value is None:
                continue
            if metric == "delta_observed_new_pp":
                value = abs(value)
            support = min(row["n_pre_users"], row["n_post_users"])
            x = left + math.log10(support) / max_log * plot_width if max_log else left
            y = y_bottom - (value - y_min) / (y_max - y_min) * panel_height
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color + "80", outline=color + "CC")
        draw.text((left, y_top - 40), ylabel, fill="#222222", font=font(26, True))
    draw.text((left + plot_width / 2 - 190, height - 48), "min(n_pre, n_post), log scale", fill="#333333", font=font(25))
    draw.text((left + math.log10(10) / max_log * plot_width + 8, top + 4), "higher-support threshold = 10", fill="#222222", font=font(19))
    image.convert("RGB").save(out_dir / "rq1_support_vs_shift_scatter.png")
    return len(rows)


def numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "median": None, "p25": None, "p75": None}
    return {
        "n": len(values),
        "median": statistics.median(values),
        "p25": percentile(values, 0.25),
        "p75": percentile(values, 0.75),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RQ1 player-composition analysis")
    parser.add_argument("--matches", type=Path, default=Path("data/processed/riot_feasibility_matches.csv"))
    parser.add_argument("--events", type=Path, default=Path("data/official_changed_champion_patch_table.csv"))
    parser.add_argument("--cohort", type=Path, default=Path("data/processed/cohort_metadata.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/rq1"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    cohort, cohort_metadata = load_cohort(args.cohort)
    matches_by_player, observed_patches, duplicates = load_matches(args.matches, cohort)
    events, pre_patch_validation = load_events(args.events, observed_patches)
    player_rows, membership = make_player_period_rows(matches_by_player, cohort, events)
    participation = participation_summary(events, membership)
    familiarity = familiarity_summary(events, player_rows)
    rank_role, event_tvds = rank_role_summary(events, player_rows)
    event_summary = merge_event_summary(participation, familiarity, event_tvds)

    write_csv(args.out_dir / "rq1_user_participation.csv", player_rows)
    write_csv(args.out_dir / "rq1_familiarity_shift.csv", familiarity)
    write_csv(args.out_dir / "rq1_rank_role_shift.csv", rank_role)
    write_csv(args.out_dir / "rq1_event_summary.csv", event_summary)
    higher_support = [row for row in event_summary if row["higher_support_view"]]
    write_csv(args.out_dir / "rq1_event_summary_higher_support.csv", higher_support)
    write_csv(args.out_dir / "rq1_pre_patch_validation.csv", pre_patch_validation)
    plotted = {
        "overall": plot_overviews(event_summary, args.out_dir),
        "higher_support": plot_overviews(
            higher_support, args.out_dir, filename_suffix="_higher_support", title_suffix=" (pre/post users >=10)"
        ),
        "support_scatter_events": plot_support_scatter(event_summary, args.out_dir),
    }

    post_only = [row["post_only_among_union"] for row in event_summary if row["post_only_among_union"] is not None]
    new_shift = [row["delta_observed_new_pp"] for row in event_summary if row["delta_observed_new_pp"] is not None]
    rank_tvd_values = [row["rank_tvd"] for row in event_summary if row["rank_tvd"] is not None]
    role_tvd_values = [row["role_tvd"] for row in event_summary if row["role_tvd"] is not None]
    coverage_stratified = []
    for threshold in (1, 5, 10, 20):
        supported = [row for row in event_summary if row["n_pre_users"] >= threshold and row["n_post_users"] >= threshold]
        def supported_values(metric: str) -> list[float]:
            return [row[metric] for row in supported if row[metric] is not None]
        new_values = supported_values("delta_observed_new_pp")
        rank_values = supported_values("rank_tvd")
        role_values = supported_values("role_tvd")
        post_values = supported_values("post_only_among_union")
        coverage_stratified.append({
            "minimum_users_each_period": threshold,
            "events": len(supported),
            "median_post_only_share": statistics.median(post_values) if post_values else None,
            "median_absolute_observed_new_change_pp": statistics.median(map(abs, new_values)) if new_values else None,
            "median_rank_tvd": statistics.median(rank_values) if rank_values else None,
            "median_role_tvd": statistics.median(role_values) if role_values else None,
            "events_absolute_observed_new_change_at_least_10pp": sum(abs(value) >= 10 for value in new_values),
            "events_rank_tvd_at_least_0_2": sum(value >= 0.2 for value in rank_values),
            "events_role_tvd_at_least_0_2": sum(value >= 0.2 for value in role_values),
        })
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rq": "RQ1 composition only; no performance outcomes read or analyzed",
        "period_definition": "pre = validated immediately preceding API patch; post = event patch; no observed-data fallback",
        "season_boundary_predecessors": SEASON_PREDECESSORS,
        "pre_patch_validation": {
            "events_checked": len(pre_patch_validation),
            "events_with_expected_pre_patch_observed": sum(row["pre_patch_observed_in_match_data"] for row in pre_patch_validation),
            "events_missing_expected_pre_patch": sum(not row["pre_patch_observed_in_match_data"] for row in pre_patch_validation),
            "cross_patch_fallbacks": sum(row["cross_patch_fallback_used"] for row in pre_patch_validation),
        },
        "familiarity_primary_window": 100,
        "familiarity_sensitivity_window_retained": 50,
        "familiarity_anchor": "immediately before the player's first focal-champion match in that period",
        "rank_role_basis": "fixed cohort rank stratum and primary role",
        "change_direction": "left blank because the official event table has no validated direction field",
        "cohort": cohort_metadata,
        "input_sha256": {"matches": sha256(args.matches), "events": sha256(args.events)},
        "input_match_rows_after_deduplication": sum(map(len, matches_by_player.values())),
        "duplicate_player_match_rows_removed": duplicates,
        "official_events": len(events),
        "player_period_rows": len(player_rows),
        "events_with_pre_and_post_observed_users": sum(row["n_pre_users"] > 0 and row["n_post_users"] > 0 for row in event_summary),
        "events_with_familiarity_pre_and_post": sum(row["experience_eligible_pre"] > 0 and row["experience_eligible_post"] > 0 for row in event_summary),
        "overview_metrics": {
            "post_only_among_union": numeric_summary(post_only),
            "delta_observed_new_pp": numeric_summary(new_shift),
            "rank_tvd": numeric_summary(rank_tvd_values),
            "role_tvd": numeric_summary(role_tvd_values),
        },
        "coverage_stratified": coverage_stratified,
        "higher_support_definition": "n_pre_users >= 10 and n_post_users >= 10",
        "higher_support_events": len(higher_support),
        "figure_event_counts": plotted,
    }
    (args.out_dir / "rq1_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    report = [
        "# RQ1 composition-only build report", "",
        f"- Official champion-patch events: {len(events)}",
        f"- Player-period rows: {len(player_rows):,}",
        f"- Events with observed users in both periods: {metadata['events_with_pre_and_post_observed_users']}",
        f"- Events with 100-match-eligible users in both periods: {metadata['events_with_familiarity_pre_and_post']}",
        f"- Higher-support events (pre and post users >=10): {len(higher_support)}",
        f"- Events missing the true immediately preceding patch in match data: {metadata['pre_patch_validation']['events_missing_expected_pre_patch']}",
        f"- Cross-patch fallbacks used: {metadata['pre_patch_validation']['cross_patch_fallbacks']}",
        f"- Duplicate player-match rows removed: {duplicates}", "",
        "No win, KDA, damage, gold, vision, item, or other performance outcome was read or analyzed.", "",
        "## Descriptive distributions", "",
        "| Metric | Events | Median | P25 | P75 |", "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, key in (("Post-only among union", "post_only_among_union"), ("Observed-new change", "delta_observed_new_pp"), ("Rank TVD", "rank_tvd"), ("Role TVD", "role_tvd")):
        item = metadata["overview_metrics"][key]
        report.append(f"| {label} | {item['n']} | {item['median'] if item['median'] is not None else ''} | {item['p25'] if item['p25'] is not None else ''} | {item['p75'] if item['p75'] is not None else ''} |")
    report.extend(["", "## Coverage-stratified diagnostics", "",
                   "| Minimum pre and post users | Events | Median post-only share | Median absolute observed-new change (pp) | Median rank TVD | Median role TVD |",
                   "| ---: | ---: | ---: | ---: | ---: | ---: |"])
    for item in coverage_stratified:
        report.append(f"| {item['minimum_users_each_period']} | {item['events']} | {item['median_post_only_share']} | {item['median_absolute_observed_new_change_pp']} | {item['median_rank_tvd']} | {item['median_role_tvd']} |")
    report.extend(["", "These are coverage and effect-size descriptions. No significance tests or causal claims are made. Extreme values from sparse events must not be treated as stable estimates."])
    (args.out_dir / "rq1_build_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps({
        "events": len(events),
        "player_period_rows": len(player_rows),
        "events_both_periods": metadata["events_with_pre_and_post_observed_users"],
        "events_familiarity_both_periods": metadata["events_with_familiarity_pre_and_post"],
        "out_dir": str(args.out_dir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
