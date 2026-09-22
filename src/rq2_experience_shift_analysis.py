#!/usr/bin/env python3
"""RQ2: describe changes in prior champion experience distributions.

Inputs are the composition-only RQ1 player-period table and event summary.
No gameplay performance outcome is read or analyzed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WINDOWS = (100, 50)
DIRECTION_THRESHOLD_LOG1P = 0.10


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty output: {path}")
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], probability: float) -> float | None:
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


def distribution_stats(values: list[int]) -> dict[str, float | int | None]:
    logs = [math.log1p(value) for value in values]
    return {
        "n": len(values),
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p25": percentile(values, 0.25),
        "p75": percentile(values, 0.75),
        "mean_log1p": statistics.fmean(logs) if logs else None,
        "median_log1p": statistics.median(logs) if logs else None,
        "p25_log1p": percentile(logs, 0.25),
        "p75_log1p": percentile(logs, 0.75),
    }


def wasserstein_1d(first: list[float], second: list[float]) -> float | None:
    """Exact first Wasserstein distance between equally weighted empirical samples."""
    if not first or not second:
        return None
    first_sorted = sorted(first)
    second_sorted = sorted(second)
    support = sorted(set(first_sorted) | set(second_sorted))
    first_index = second_index = 0
    distance = 0.0
    for index, value in enumerate(support[:-1]):
        while first_index < len(first_sorted) and first_sorted[first_index] <= value:
            first_index += 1
        while second_index < len(second_sorted) and second_sorted[second_index] <= value:
            second_index += 1
        width = support[index + 1] - value
        distance += abs(first_index / len(first_sorted) - second_index / len(second_sorted)) * width
    return distance


def shift_direction(delta_mean_log1p: float | None, threshold: float = DIRECTION_THRESHOLD_LOG1P) -> str:
    if delta_mean_log1p is None:
        return "not_computable"
    if delta_mean_log1p <= -threshold:
        return "toward_lower_experience"
    if delta_mean_log1p >= threshold:
        return "toward_higher_experience"
    return "approximately_stable"


def parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def load_inputs(participation_path: Path, event_summary_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw_participation = read_csv(participation_path)
    required = {
        "event_id", "player_id", "champion", "patch", "period", "participation_status",
        "prior_champion_count_100", "experience_eligible_100",
        "prior_champion_count_50", "experience_eligible_50",
    }
    if not raw_participation or not required <= set(raw_participation[0]):
        raise ValueError(f"RQ1 participation input lacks columns: {sorted(required)}")
    participation = []
    for row in raw_participation:
        clean: dict[str, Any] = dict(row)
        for window in WINDOWS:
            clean[f"experience_eligible_{window}"] = parse_bool(row[f"experience_eligible_{window}"])
            clean[f"prior_champion_count_{window}"] = (
                int(row[f"prior_champion_count_{window}"]) if row[f"prior_champion_count_{window}"] != "" else None
            )
        participation.append(clean)

    event_rows = read_csv(event_summary_path)
    events: dict[str, dict[str, Any]] = {}
    for row in event_rows:
        events[row["event_id"]] = {
            "event_id": row["event_id"],
            "champion": row["champion"],
            "patch": row["patch"],
            "pre_patch": row["pre_patch"],
            "change_direction": row.get("change_direction", ""),
            "n_pre_users": int(row["n_pre_users"]),
            "n_post_users": int(row["n_post_users"]),
            "higher_support_view": parse_bool(row["higher_support_view"]),
        }
    return participation, events


def build_event_shifts(
    participation: list[dict[str, Any]], events: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[int]] = defaultdict(list)
    for row in participation:
        for window in WINDOWS:
            value = row[f"prior_champion_count_{window}"]
            if row[f"experience_eligible_{window}"] and value is not None:
                grouped[(row["event_id"], window, row["period"])].append(value)

    output = []
    for event_id, event in events.items():
        for window in WINDOWS:
            pre = grouped.get((event_id, window, "pre"), [])
            post = grouped.get((event_id, window, "post"), [])
            pre_stats = distribution_stats(pre)
            post_stats = distribution_stats(post)
            delta_mean_log = (
                post_stats["mean_log1p"] - pre_stats["mean_log1p"]
                if post_stats["mean_log1p"] is not None and pre_stats["mean_log1p"] is not None else None
            )
            row: dict[str, Any] = {**event, "window": window}
            for name, value in pre_stats.items():
                row[f"pre_{name}"] = value
            for name, value in post_stats.items():
                row[f"post_{name}"] = value
            for name in ("mean", "median", "p25", "p75", "mean_log1p", "median_log1p", "p25_log1p", "p75_log1p"):
                row[f"delta_{name}"] = (
                    post_stats[name] - pre_stats[name]
                    if post_stats[name] is not None and pre_stats[name] is not None else None
                )
            row["wasserstein_raw"] = wasserstein_1d(pre, post)
            row["wasserstein_log1p"] = wasserstein_1d([math.log1p(value) for value in pre], [math.log1p(value) for value in post])
            row["experience_shift_direction"] = shift_direction(delta_mean_log)
            row["experience_support_10"] = len(pre) >= 10 and len(post) >= 10
            output.append(row)
    output.sort(key=lambda row: (row["window"], tuple(map(int, row["patch"].split("."))), row["champion"]))
    return output


def build_post_only_vs_both(
    participation: list[dict[str, Any]], events: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[int]] = defaultdict(list)
    for row in participation:
        if row["period"] != "post" or row["participation_status"] not in {"post_only", "both"}:
            continue
        for window in WINDOWS:
            value = row[f"prior_champion_count_{window}"]
            if row[f"experience_eligible_{window}"] and value is not None:
                grouped[(row["event_id"], window, row["participation_status"])].append(value)
    output = []
    for event_id, event in events.items():
        for window in WINDOWS:
            post_only = grouped.get((event_id, window, "post_only"), [])
            both = grouped.get((event_id, window, "both"), [])
            post_stats = distribution_stats(post_only)
            both_stats = distribution_stats(both)
            row: dict[str, Any] = {**event, "window": window}
            for name, value in post_stats.items():
                row[f"post_only_{name}"] = value
            for name, value in both_stats.items():
                row[f"both_{name}"] = value
            for name in ("mean", "median", "mean_log1p", "median_log1p"):
                row[f"post_only_minus_both_{name}"] = (
                    post_stats[name] - both_stats[name]
                    if post_stats[name] is not None and both_stats[name] is not None else None
                )
            row["post_only_vs_both_wasserstein_raw"] = wasserstein_1d(post_only, both)
            row["post_only_vs_both_wasserstein_log1p"] = wasserstein_1d(
                [math.log1p(value) for value in post_only], [math.log1p(value) for value in both]
            )
            row["both_groups_observed"] = bool(post_only and both)
            output.append(row)
    output.sort(key=lambda row: (row["window"], tuple(map(int, row["patch"].split("."))), row["champion"]))
    return output


def build_window_sensitivity(event_shifts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_event_window = {(row["event_id"], row["window"]): row for row in event_shifts}
    rows = []
    for event_id in sorted({row["event_id"] for row in event_shifts}):
        primary = by_event_window[(event_id, 100)]
        sensitivity = by_event_window[(event_id, 50)]
        direction_100 = primary["experience_shift_direction"]
        direction_50 = sensitivity["experience_shift_direction"]
        comparable = direction_100 != "not_computable" and direction_50 != "not_computable"
        rows.append({
            "event_id": event_id,
            "champion": primary["champion"],
            "patch": primary["patch"],
            "higher_support_view": primary["higher_support_view"],
            "direction_100": direction_100,
            "direction_50": direction_50,
            "direction_agreement": comparable and direction_100 == direction_50,
            "delta_mean_log1p_100": primary["delta_mean_log1p"],
            "delta_mean_log1p_50": sensitivity["delta_mean_log1p"],
            "same_signed_direction": (
                comparable and primary["delta_mean_log1p"] * sensitivity["delta_mean_log1p"] >= 0
            ),
            "wasserstein_log1p_100": primary["wasserstein_log1p"],
            "wasserstein_log1p_50": sensitivity["wasserstein_log1p"],
            "comparable": comparable,
        })
    return rows


def font(size: int, bold: bool = False):
    from PIL import ImageFont
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def plot_median_scatter(event_shifts: list[dict[str, Any]], out_dir: Path) -> int:
    from PIL import Image, ImageDraw
    rows = [
        row for row in event_shifts
        if row["window"] == 100 and row["higher_support_view"]
        and row["pre_median"] is not None and row["post_median"] is not None
    ]
    width, height = 1050, 950
    left, right, top, bottom = 125, 65, 100, 120
    plot_width, plot_height = width - left - right, height - top - bottom
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    max_value = max(max(row["pre_median"], row["post_median"]) for row in rows)
    max_log = math.log1p(max_value or 1)
    draw.line((left, top, left, top + plot_height), fill="#333333", width=3)
    draw.line((left, top + plot_height, left + plot_width, top + plot_height), fill="#333333", width=3)
    draw.line((left, top + plot_height, left + plot_width, top), fill="#777777", width=3)
    ticks = [0, 1, 2, 5, 10, 20, 50, 100]
    ticks = [value for value in ticks if value <= max_value]
    for value in ticks:
        position = math.log1p(value) / max_log if max_log else 0
        x = left + position * plot_width
        y = top + plot_height - position * plot_height
        draw.line((x, top, x, top + plot_height), fill="#EEEEEE", width=1)
        draw.line((left, y, left + plot_width, y), fill="#EEEEEE", width=1)
        draw.text((x - 12, top + plot_height + 18), str(value), fill="#444444", font=font(20))
        draw.text((55, y - 12), str(value), fill="#444444", font=font(20))
    for row in rows:
        x = left + math.log1p(row["pre_median"]) / max_log * plot_width
        y = top + plot_height - math.log1p(row["post_median"]) / max_log * plot_height
        direction = row["experience_shift_direction"]
        color = {"toward_lower_experience": "#D55E00AA", "approximately_stable": "#77777799", "toward_higher_experience": "#0072B2AA"}[direction]
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color)
    draw.text((left, 28), "Pre versus post median prior champion experience", fill="#222222", font=font(34, True))
    draw.text((left + 190, height - 50), "Pre median prior champion count (log scale)", fill="#333333", font=font(23))
    draw.text((16, top + plot_height / 2), "Post median", fill="#333333", font=font(23))
    draw.text((left + plot_width - 250, top + 15), "Above: higher experience", fill="#0072B2", font=font(20))
    draw.text((left + 20, top + plot_height - 45), "Below: lower experience", fill="#D55E00", font=font(20))
    image.convert("RGB").save(out_dir / "rq2_pre_post_median_scatter.png")
    return len(rows)


def plot_post_only_vs_both_distribution(
    participation: list[dict[str, Any]], higher_support_ids: set[str], out_dir: Path
) -> dict[str, Any]:
    from PIL import Image, ImageDraw
    groups: dict[str, list[int]] = {"post_only": [], "both": []}
    for row in participation:
        if row["event_id"] not in higher_support_ids or row["period"] != "post":
            continue
        status = row["participation_status"]
        value = row["prior_champion_count_100"]
        if status in groups and row["experience_eligible_100"] and value is not None:
            groups[status].append(value)
    width, height = 1200, 800
    left, right, top, bottom = 125, 70, 110, 120
    plot_width, plot_height = width - left - right, height - top - bottom
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    max_value = max(value for values in groups.values() for value in values)
    max_log = math.log1p(max_value or 1)
    draw.line((left, top, left, top + plot_height), fill="#333333", width=3)
    draw.line((left, top + plot_height, left + plot_width, top + plot_height), fill="#333333", width=3)
    for tick in range(6):
        y = top + plot_height - tick * plot_height / 5
        draw.line((left, y, left + plot_width, y), fill="#E2E2E2", width=1)
        draw.text((50, y - 12), f"{tick / 5:.1f}", fill="#444444", font=font(20))
    ticks = [0, 1, 2, 5, 10, 20, 50, 100]
    ticks = [value for value in ticks if value <= max_value]
    for value in ticks:
        x = left + math.log1p(value) / max_log * plot_width
        draw.line((x, top, x, top + plot_height), fill="#EEEEEE", width=1)
        draw.text((x - 12, top + plot_height + 18), str(value), fill="#444444", font=font(20))
    for label, color in (("post_only", "#D55E00"), ("both", "#0072B2")):
        values = sorted(groups[label])
        points = []
        for index, value in enumerate(values, start=1):
            x = left + math.log1p(value) / max_log * plot_width
            y = top + plot_height - index / len(values) * plot_height
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=color, width=5)
    draw.text((left, 22), "Prior champion experience among post-period users", fill="#222222", font=font(34, True))
    draw.text((left, 66), "Higher-support events; pooled player-event observations", fill="#555555", font=font(21))
    draw.text((left + 235, height - 50), "Prior champion count (log scale)", fill="#333333", font=font(23))
    draw.text((18, top + plot_height / 2), "Empirical CDF", fill="#333333", font=font(23))
    legend = [
        ("Post-only", "post_only", "#D55E00"),
        ("Both periods", "both", "#0072B2"),
    ]
    for index, (label, key, color) in enumerate(legend):
        y = top + 20 + index * 42
        draw.line((width - 390, y + 12, width - 345, y + 12), fill=color, width=5)
        median = statistics.median(groups[key]) if groups[key] else None
        draw.text((width - 330, y), f"{label}: n={len(groups[key])}, median={median}", fill="#333333", font=font(20))
    image.convert("RGB").save(out_dir / "rq2_post_only_vs_both_distribution.png")
    return {
        "post_only_n": len(groups["post_only"]),
        "both_n": len(groups["both"]),
        "post_only_median": statistics.median(groups["post_only"]) if groups["post_only"] else None,
        "both_median": statistics.median(groups["both"]) if groups["both"] else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RQ2 prior champion experience distribution analysis")
    parser.add_argument("--participation", type=Path, default=Path("results/rq1/rq1_user_participation.csv"))
    parser.add_argument("--events", type=Path, default=Path("results/rq1/rq1_event_summary.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/rq2"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    participation, events = load_inputs(args.participation, args.events)
    event_shifts = build_event_shifts(participation, events)
    post_only_vs_both = build_post_only_vs_both(participation, events)
    sensitivity = build_window_sensitivity(event_shifts)
    higher_support_100 = [row for row in event_shifts if row["window"] == 100 and row["higher_support_view"]]
    higher_support_ids = {row["event_id"] for row in higher_support_100}

    write_csv(args.out_dir / "rq2_event_experience_shift.csv", event_shifts)
    write_csv(args.out_dir / "rq2_event_experience_shift_higher_support.csv", higher_support_100)
    write_csv(args.out_dir / "rq2_post_only_vs_both.csv", post_only_vs_both)
    write_csv(args.out_dir / "rq2_window_sensitivity.csv", sensitivity)
    scatter_n = plot_median_scatter(event_shifts, args.out_dir)
    group_plot = plot_post_only_vs_both_distribution(participation, higher_support_ids, args.out_dir)

    primary = higher_support_100
    directions = Counter(row["experience_shift_direction"] for row in primary)
    comparable_sensitivity = [row for row in sensitivity if row["higher_support_view"] and row["comparable"]]
    group_comparisons = [
        row for row in post_only_vs_both
        if row["window"] == 100 and row["higher_support_view"] and row["both_groups_observed"]
    ]
    post_only_lower = sum(
        row["post_only_minus_both_mean_log1p"] < 0 for row in group_comparisons
        if row["post_only_minus_both_mean_log1p"] is not None
    )
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rq": "RQ2 prior champion experience composition; no performance outcomes",
        "primary_window": 100,
        "sensitivity_window": 50,
        "higher_support_definition": "RQ1 higher-support view: n_pre_users >= 10 and n_post_users >= 10",
        "direction_rule": {
            "basis": "delta mean log1p(prior champion count)",
            "threshold": DIRECTION_THRESHOLD_LOG1P,
            "lower": "delta <= -0.10",
            "stable": "-0.10 < delta < 0.10",
            "higher": "delta >= 0.10",
        },
        "event_rows": len(event_shifts),
        "higher_support_primary_events": len(primary),
        "primary_direction_counts": dict(directions),
        "window_comparable_higher_support_events": len(comparable_sensitivity),
        "direction_agreement_events": sum(row["direction_agreement"] for row in comparable_sensitivity),
        "same_signed_direction_events": sum(row["same_signed_direction"] for row in comparable_sensitivity),
        "post_only_vs_both_comparable_events": len(group_comparisons),
        "events_post_only_lower_mean_log1p": post_only_lower,
        "median_scatter_events": scatter_n,
        "pooled_post_period_plot": group_plot,
        "interpretation_limits": [
            "Pre-to-post familiarity is time-varying: continuing users may accumulate focal-champion matches between periods.",
            "The pooled ECDF weights player-event observations; one player may contribute to multiple champion-patch events.",
            "The event-level post-only versus both comparison is descriptive and does not explain why players selected a champion.",
        ],
    }
    (args.out_dir / "rq2_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    agreement_rate = (
        metadata["direction_agreement_events"] / metadata["window_comparable_higher_support_events"]
        if metadata["window_comparable_higher_support_events"] else None
    )
    sign_rate = (
        metadata["same_signed_direction_events"] / metadata["window_comparable_higher_support_events"]
        if metadata["window_comparable_higher_support_events"] else None
    )
    lower_rate = post_only_lower / len(group_comparisons) if group_comparisons else None
    lines = [
        "# RQ2 experience-composition report", "",
        "No gameplay performance outcome was read or analyzed.", "",
        f"- Higher-support primary events: {len(primary)}",
        f"- Direction counts: {dict(directions)}",
        f"- 100/50 exact direction agreement: {metadata['direction_agreement_events']}/{metadata['window_comparable_higher_support_events']} ({agreement_rate:.1%})" if agreement_rate is not None else "- 100/50 exact direction agreement: unavailable",
        f"- 100/50 same signed direction: {metadata['same_signed_direction_events']}/{metadata['window_comparable_higher_support_events']} ({sign_rate:.1%})" if sign_rate is not None else "- 100/50 same signed direction: unavailable",
        f"- Events with both post-only and both-period users: {len(group_comparisons)}",
        f"- Events where post-only users have lower mean log1p experience: {post_only_lower}/{len(group_comparisons)} ({lower_rate:.1%})" if lower_rate is not None else "- Post-only versus both comparison: unavailable",
        f"- Pooled post-only median prior count: {group_plot['post_only_median']}",
        f"- Pooled both-period median prior count: {group_plot['both_median']}", "",
        "Direction is a descriptive label based on mean log1p difference with a prespecified ±0.10 band. Raw/log summaries and Wasserstein distances remain the primary numeric evidence.",
        "Pre-to-post familiarity is time-varying: continuing users may accumulate focal-champion matches between periods. The pooled ECDF uses player-event observations, while the 92/93 comparison is calculated separately within each event.",
    ]
    (args.out_dir / "rq2_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
