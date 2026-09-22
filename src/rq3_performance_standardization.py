#!/usr/bin/env python3
"""RQ3 performance comparison with provisional composition standardization.

Primary descriptive view: the 97 RQ1 events with at least 10 observed users in
both pre and post. Standardization uses experience-eligible match rows and a
pooled logistic model with event intercepts, event-specific post terms,
continuous log1p familiarity, rank, and primary role. No significance testing
or causal-effect claim is produced.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


RANKS = ("GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER+")
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
FORBIDDEN_MODEL_FIELDS = {
    "kills", "deaths", "assists", "totalDamageDealtToChampions", "goldEarned", "visionScore",
    "item0", "item1", "item2", "item3", "item4", "item5", "item6", "summoner1Id", "summoner2Id",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty output: {path}")
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def familiarity_group(count: int) -> str:
    if count == 0:
        return "observed_new"
    if count <= 4:
        return "limited_1_4"
    return "established_5plus"


def patch_key(value: str) -> tuple[int, int]:
    major, minor = value.split(".", 1)
    return int(major), int(minor)


def load_event_definitions(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_csv(path)
    events = {}
    for row in rows:
        events[row["event_id"]] = {
            "event_id": row["event_id"],
            "champion": row["champion"],
            "patch": row["patch"],
            "pre_patch": row["pre_patch"],
            "change_direction": row.get("change_direction", ""),
            "higher_support_view": parse_bool(row["higher_support_view"]),
        }
    return events


def load_player_event_status(path: Path) -> tuple[dict[tuple[str, str], str], dict[str, dict[str, str]]]:
    rows = read_csv(path)
    statuses: dict[tuple[str, str], str] = {}
    player_covariates: dict[str, dict[str, str]] = {}
    for row in rows:
        statuses[(row["event_id"], row["player_id"])] = row["participation_status"]
        player_covariates[row["player_id"]] = {
            "rank_stratum": row["rank_stratum"],
            "primary_role": row["primary_role"],
        }
    return statuses, player_covariates


def build_match_analysis(
    match_path: Path,
    events: dict[str, dict[str, Any]],
    statuses: dict[tuple[str, str], str],
    player_covariates: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    post_lookup = {(event["champion"], event["patch"]): event for event in events.values()}
    pre_lookup: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events.values():
        pre_lookup[(event["champion"], event["pre_patch"])].append(event)

    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with match_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"anonymized_player_id", "matchId", "gameStartTimestamp", "patch", "championName", "win"}
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            raise ValueError(f"Match input lacks required columns: {sorted(required)}")
        for raw in reader:
            player = raw["anonymized_player_id"]
            if player not in player_covariates:
                continue
            by_player[player].append({
                "player_id": player,
                "match_id": raw["matchId"],
                "timestamp": int(raw["gameStartTimestamp"]),
                "patch": raw["patch"],
                "champion": raw["championName"],
                "win": 1 if parse_bool(raw["win"]) else 0,
            })

    output = []
    for player, games in by_player.items():
        games.sort(key=lambda row: (row["timestamp"], row["match_id"]))
        window: deque[str] = deque()
        counts: Counter[str] = Counter()
        for game in games:
            eligible = len(window) == 100
            prior_count = counts[game["champion"]] if eligible else None
            eligible_50 = len(window) >= 50
            prior_count_50 = sum(champion == game["champion"] for champion in list(window)[-50:]) if eligible_50 else None
            relevant: list[tuple[dict[str, Any], str]] = []
            post_event = post_lookup.get((game["champion"], game["patch"]))
            if post_event:
                relevant.append((post_event, "post"))
            for pre_event in pre_lookup.get((game["champion"], game["patch"]), []):
                relevant.append((pre_event, "pre"))
            for event, period in relevant:
                status = statuses.get((event["event_id"], player), "")
                output.append({
                    "event_id": event["event_id"],
                    "match_id": game["match_id"],
                    "player_id": player,
                    "champion": event["champion"],
                    "patch": event["patch"],
                    "pre_patch": event["pre_patch"],
                    "period": period,
                    "post": 1 if period == "post" else 0,
                    "win": game["win"],
                    "rank_stratum": player_covariates[player]["rank_stratum"],
                    "primary_role": player_covariates[player]["primary_role"],
                    "prior_champion_count_100": prior_count,
                    "log1p_prior_count": math.log1p(prior_count) if prior_count is not None else None,
                    "familiarity_group_100": familiarity_group(prior_count) if prior_count is not None else "",
                    "experience_eligible_100": eligible,
                    "prior_champion_count_50": prior_count_50,
                    "log1p_prior_count_50": math.log1p(prior_count_50) if prior_count_50 is not None else None,
                    "experience_eligible_50": eligible_50,
                    "participation_status": status,
                    "higher_support_view": event["higher_support_view"],
                })
            window.append(game["champion"])
            counts[game["champion"]] += 1
            if len(window) > 100:
                removed = window.popleft()
                counts[removed] -= 1
                if counts[removed] == 0:
                    del counts[removed]
    output.sort(key=lambda row: (patch_key(row["patch"]), row["champion"], row["timestamp"] if "timestamp" in row else row["match_id"], row["player_id"]))
    return output


def coverage_audit(match_rows: list[dict[str, Any]], events: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in match_rows:
        grouped[(row["event_id"], row["period"])].append(row)
    output = []
    for event_id, event in events.items():
        for period in ("pre", "post"):
            rows = grouped.get((event_id, period), [])
            eligible = [row for row in rows if row["experience_eligible_100"]]
            observed_users = {row["player_id"] for row in rows}
            eligible_users = {row["player_id"] for row in eligible}
            both_rows = [row for row in rows if row["participation_status"] == "both"]
            eligible_both = [row for row in both_rows if row["experience_eligible_100"]]
            output.append({
                **event,
                "period": period,
                "observed_users": len(observed_users),
                "observed_matches": len(rows),
                "experience_eligible_users": len(eligible_users),
                "experience_eligible_matches": len(eligible),
                "eligible_user_retention_share": len(eligible_users) / len(observed_users) if observed_users else None,
                "eligible_match_retention_share": len(eligible) / len(rows) if rows else None,
                "both_period_users": len({row["player_id"] for row in both_rows}),
                "eligible_both_period_users": len({row["player_id"] for row in eligible_both}),
                "eligible_both_period_matches": len(eligible_both),
            })
    return output


def sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -35, 35)
    return 1.0 / (1.0 + np.exp(-clipped))


def build_design(rows: list[dict[str, Any]], event_ids: list[str]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    event_index = {event_id: index for index, event_id in enumerate(event_ids)}
    p = 2 * len(event_ids) + 1 + (len(RANKS) - 1) + (len(ROLES) - 1)
    matrix = np.zeros((len(rows), p), dtype=float)
    outcomes = np.zeros(len(rows), dtype=float)
    log_values = np.array([row["log1p_prior_count"] for row in rows], dtype=float)
    log_mean = float(log_values.mean())
    log_sd = float(log_values.std()) or 1.0
    for i, row in enumerate(rows):
        event_position = event_index[row["event_id"]]
        matrix[i, event_position] = 1.0
        matrix[i, len(event_ids) + event_position] = row["post"]
        cursor = 2 * len(event_ids)
        matrix[i, cursor] = (row["log1p_prior_count"] - log_mean) / log_sd
        cursor += 1
        for category in RANKS[1:]:
            matrix[i, cursor] = row["rank_stratum"] == category
            cursor += 1
        for category in ROLES[1:]:
            matrix[i, cursor] = row["primary_role"] == category
            cursor += 1
        outcomes[i] = row["win"]
    metadata = {"event_ids": event_ids, "log_mean": log_mean, "log_sd": log_sd, "parameters": p}
    return matrix, outcomes, metadata


def fit_logistic_irls(
    matrix: np.ndarray, outcomes: np.ndarray, ridge: float = 1e-6, max_iter: int = 100, tolerance: float = 1e-8
) -> tuple[np.ndarray, dict[str, Any]]:
    coefficients = np.zeros(matrix.shape[1], dtype=float)
    penalty = np.full(matrix.shape[1], ridge)

    def objective(beta: np.ndarray) -> float:
        eta = matrix @ beta
        likelihood = np.logaddexp(0, eta).sum() - outcomes @ eta
        return float(likelihood + 0.5 * np.sum(penalty * beta * beta))

    converged = False
    current_objective = objective(coefficients)
    iteration = 0
    for iteration in range(1, max_iter + 1):
        probabilities = sigmoid(matrix @ coefficients)
        weights = np.clip(probabilities * (1 - probabilities), 1e-7, None)
        gradient = matrix.T @ (probabilities - outcomes) + penalty * coefficients
        hessian = (matrix.T * weights) @ matrix + np.diag(penalty)
        step = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
        scale = 1.0
        while scale > 1e-6:
            candidate = coefficients - scale * step
            candidate_objective = objective(candidate)
            if candidate_objective <= current_objective:
                break
            scale *= 0.5
        coefficients = candidate
        improvement = current_objective - candidate_objective
        current_objective = candidate_objective
        if np.max(np.abs(scale * step)) < tolerance or abs(improvement) < tolerance:
            converged = True
            break
    probabilities = sigmoid(matrix @ coefficients)
    diagnostics = {
        "converged": converged,
        "iterations": iteration,
        "ridge_penalty": ridge,
        "negative_log_likelihood_penalized": current_objective,
        "mean_log_loss": float(-np.mean(outcomes * np.log(np.clip(probabilities, 1e-12, 1)) + (1 - outcomes) * np.log(np.clip(1 - probabilities, 1e-12, 1)))),
        "brier_score": float(np.mean((outcomes - probabilities) ** 2)),
        "min_predicted_probability": float(probabilities.min()),
        "max_predicted_probability": float(probabilities.max()),
        "max_absolute_coefficient": float(np.max(np.abs(coefficients))),
        "gradient_max_abs": float(np.max(np.abs(matrix.T @ (probabilities - outcomes) + penalty * coefficients))),
    }
    return coefficients, diagnostics


def design_row(row: dict[str, Any], forced_post: int, metadata: dict[str, Any]) -> np.ndarray:
    event_ids = metadata["event_ids"]
    event_index = {event_id: index for index, event_id in enumerate(event_ids)}
    vector = np.zeros(metadata["parameters"], dtype=float)
    event_position = event_index[row["event_id"]]
    vector[event_position] = 1.0
    vector[len(event_ids) + event_position] = forced_post
    cursor = 2 * len(event_ids)
    vector[cursor] = (row["log1p_prior_count"] - metadata["log_mean"]) / metadata["log_sd"]
    cursor += 1
    for category in RANKS[1:]:
        vector[cursor] = row["rank_stratum"] == category
        cursor += 1
    for category in ROLES[1:]:
        vector[cursor] = row["primary_role"] == category
        cursor += 1
    return vector


def win_rate(rows: list[dict[str, Any]]) -> float | None:
    return statistics.fmean(row["win"] for row in rows) if rows else None


def delta_pp(post: float | None, pre: float | None) -> float | None:
    return (post - pre) * 100 if post is not None and pre is not None else None


def direction_reversed(first: float | None, second: float | None) -> bool | None:
    if first is None or second is None:
        return None
    return first * second < 0


def event_performance(
    all_rows: list[dict[str, Any]], model_rows: list[dict[str, Any]], events: dict[str, dict[str, Any]],
    coefficients: np.ndarray, design_metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    all_grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    model_grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        all_grouped[(row["event_id"], row["period"])].append(row)
    for row in model_rows:
        model_grouped[(row["event_id"], row["period"])].append(row)
    output = []
    for event_id in design_metadata["event_ids"]:
        event = events[event_id]
        all_pre = all_grouped[(event_id, "pre")]
        all_post = all_grouped[(event_id, "post")]
        pre = model_grouped[(event_id, "pre")]
        post = model_grouped[(event_id, "post")]
        all_pre_both = [row for row in all_pre if row["participation_status"] == "both"]
        all_post_both = [row for row in all_post if row["participation_status"] == "both"]
        pre_both = [row for row in pre if row["participation_status"] == "both"]
        post_both = [row for row in post if row["participation_status"] == "both"]
        raw_pre = win_rate(pre)
        raw_post = win_rate(post)
        continuing_pre = win_rate(pre_both)
        continuing_post = win_rate(post_both)
        predictions_pre = [float(sigmoid(np.array([design_row(row, 0, design_metadata) @ coefficients]))[0]) for row in pre]
        predictions_post = [float(sigmoid(np.array([design_row(row, 1, design_metadata) @ coefficients]))[0]) for row in pre]
        standardized_pre = statistics.fmean(predictions_pre) if predictions_pre else None
        standardized_post = statistics.fmean(predictions_post) if predictions_post else None
        raw_delta = delta_pp(raw_post, raw_pre)
        continuing_delta = delta_pp(continuing_post, continuing_pre)
        standardized_delta = delta_pp(standardized_post, standardized_pre)
        output.append({
            **event,
            "eligible_pre_matches": len(pre),
            "eligible_post_matches": len(post),
            "eligible_pre_users": len({row["player_id"] for row in pre}),
            "eligible_post_users": len({row["player_id"] for row in post}),
            "eligible_continuing_pre_matches": len(pre_both),
            "eligible_continuing_post_matches": len(post_both),
            "eligible_pre_wins": sum(row["win"] for row in pre),
            "eligible_post_wins": sum(row["win"] for row in post),
            "pre_outcome_all_same": bool(pre) and sum(row["win"] for row in pre) in (0, len(pre)),
            "post_outcome_all_same": bool(post) and sum(row["win"] for row in post) in (0, len(post)),
            "raw_all_pre_win_rate": win_rate(all_pre),
            "raw_all_post_win_rate": win_rate(all_post),
            "raw_all_delta_pp": delta_pp(win_rate(all_post), win_rate(all_pre)),
            "raw_pre_win_rate": raw_pre,
            "raw_post_win_rate": raw_post,
            "raw_delta_pp": raw_delta,
            "continuing_all_pre_win_rate": win_rate(all_pre_both),
            "continuing_all_post_win_rate": win_rate(all_post_both),
            "continuing_all_delta_pp": delta_pp(win_rate(all_post_both), win_rate(all_pre_both)),
            "continuing_pre_win_rate": continuing_pre,
            "continuing_post_win_rate": continuing_post,
            "continuing_delta_pp": continuing_delta,
            "standardized_pre": standardized_pre,
            "standardized_post": standardized_post,
            "standardized_delta_pp": standardized_delta,
            "standardization_shift_pp": standardized_delta - raw_delta if standardized_delta is not None and raw_delta is not None else None,
            "absolute_standardization_shift_pp": abs(standardized_delta - raw_delta) if standardized_delta is not None and raw_delta is not None else None,
            "direction_changed_raw_vs_standardized": direction_reversed(raw_delta, standardized_delta),
            "direction_changed_raw_vs_continuing": direction_reversed(raw_delta, continuing_delta),
        })
    return output


def rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for position in order[index:end]:
            ranks[position] = average_rank
        index = end
    return ranks


def correlation(first: list[float], second: list[float], spearman: bool = False) -> float | None:
    if len(first) < 2 or len(second) != len(first):
        return None
    x = rankdata(first) if spearman else first
    y = rankdata(second) if spearman else second
    x_mean, y_mean = statistics.fmean(x), statistics.fmean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y))
    return numerator / denominator if denominator else None


def font(size: int, bold: bool = False):
    from PIL import ImageFont
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def scatter_plot(
    rows: list[dict[str, Any]], x_key: str, y_key: str, title: str, xlabel: str, ylabel: str,
    output: Path, diagonal: bool = False, x_absolute: bool = False, y_absolute: bool = False,
) -> int:
    from PIL import Image, ImageDraw
    points = []
    for row in rows:
        x, y = row.get(x_key), row.get(y_key)
        if x is None or y is None:
            continue
        points.append((abs(x) if x_absolute else x, abs(y) if y_absolute else y))
    width, height = 1100, 900
    left, right, top, bottom = 135, 65, 105, 120
    plot_width, plot_height = width - left - right, height - top - bottom
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    if diagonal:
        bound = max(max(abs(x), abs(y)) for x, y in points) * 1.08 or 1
        x_min = y_min = -bound
        x_max = y_max = bound
    else:
        x_min, x_max = min(x for x, _ in points), max(x for x, _ in points)
        y_min, y_max = 0.0, max(y for _, y in points) * 1.08 or 1
        if x_min == x_max:
            x_max = x_min + 1
    draw.line((left, top, left, top + plot_height), fill="#333333", width=3)
    draw.line((left, top + plot_height, left + plot_width, top + plot_height), fill="#333333", width=3)
    for tick in range(6):
        x_value = x_min + (x_max - x_min) * tick / 5
        y_value = y_min + (y_max - y_min) * tick / 5
        x = left + plot_width * tick / 5
        y = top + plot_height - plot_height * tick / 5
        draw.line((x, top, x, top + plot_height), fill="#EEEEEE", width=1)
        draw.line((left, y, left + plot_width, y), fill="#EEEEEE", width=1)
        draw.text((x - 28, top + plot_height + 18), f"{x_value:.1f}", fill="#444444", font=font(19))
        draw.text((48, y - 11), f"{y_value:.1f}", fill="#444444", font=font(19))
    if diagonal:
        draw.line((left, top + plot_height, left + plot_width, top), fill="#777777", width=3)
    for x_value, y_value in points:
        x = left + (x_value - x_min) / (x_max - x_min) * plot_width
        y = top + plot_height - (y_value - y_min) / (y_max - y_min) * plot_height
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="#3465A4A0", outline="#234F80DD")
    draw.text((left, 28), title, fill="#222222", font=font(33, True))
    draw.text((left + 150, height - 48), xlabel, fill="#333333", font=font(22))
    draw.text((15, top + plot_height / 2), ylabel, fill="#333333", font=font(22))
    image.convert("RGB").save(output)
    return len(points)


def main() -> int:
    parser = argparse.ArgumentParser(description="RQ3 provisional performance standardization")
    parser.add_argument("--matches", type=Path, default=Path("data/processed/riot_feasibility_matches.csv"))
    parser.add_argument("--rq1-events", type=Path, default=Path("results/rq1/rq1_event_summary.csv"))
    parser.add_argument("--rq1-participation", type=Path, default=Path("results/rq1/rq1_user_participation.csv"))
    parser.add_argument("--rq2-shifts", type=Path, default=Path("results/rq2/rq2_event_experience_shift_higher_support.csv"))
    parser.add_argument("--rq2-groups", type=Path, default=Path("results/rq2/rq2_post_only_vs_both.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/rq3"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    events = load_event_definitions(args.rq1_events)
    statuses, player_covariates = load_player_event_status(args.rq1_participation)
    match_rows = build_match_analysis(args.matches, events, statuses, player_covariates)
    audit = coverage_audit(match_rows, events)
    higher_event_ids = sorted([event_id for event_id, event in events.items() if event["higher_support_view"]])
    model_rows = [
        row for row in match_rows
        if row["event_id"] in higher_event_ids and row["experience_eligible_100"]
    ]
    matrix, outcomes, design_metadata = build_design(model_rows, higher_event_ids)
    coefficients, global_diagnostics = fit_logistic_irls(matrix, outcomes)
    performance = event_performance(match_rows, model_rows, events, coefficients, design_metadata)

    rq2_shifts = {row["event_id"]: row for row in read_csv(args.rq2_shifts) if row["window"] == "100"}
    rq2_groups = {row["event_id"]: row for row in read_csv(args.rq2_groups) if row["window"] == "100"}
    for row in performance:
        shift = rq2_shifts.get(row["event_id"], {})
        groups = rq2_groups.get(row["event_id"], {})
        row["rq2_pre_post_wasserstein_log1p"] = float(shift["wasserstein_log1p"]) if shift.get("wasserstein_log1p") else None
        row["rq2_post_only_vs_both_wasserstein_log1p"] = (
            float(groups["post_only_vs_both_wasserstein_log1p"])
            if groups.get("post_only_vs_both_wasserstein_log1p") else None
        )
        row["rq2_post_only_minus_both_mean_log1p"] = (
            float(groups["post_only_minus_both_mean_log1p"])
            if groups.get("post_only_minus_both_mean_log1p") else None
        )

    event_diagnostics = []
    for row in performance:
        event_diagnostics.append({
            "event_id": row["event_id"],
            "champion": row["champion"],
            "patch": row["patch"],
            "eligible_pre_matches": row["eligible_pre_matches"],
            "eligible_post_matches": row["eligible_post_matches"],
            "eligible_pre_users": row["eligible_pre_users"],
            "eligible_post_users": row["eligible_post_users"],
            "standardized_pre": row["standardized_pre"],
            "standardized_post": row["standardized_post"],
            "prediction_in_unit_interval": (
                row["standardized_pre"] is not None and row["standardized_post"] is not None
                and 0 <= row["standardized_pre"] <= 1 and 0 <= row["standardized_post"] <= 1
            ),
            "pre_outcome_all_same": row["pre_outcome_all_same"],
            "post_outcome_all_same": row["post_outcome_all_same"],
            "separated_event_period_cells": int(row["pre_outcome_all_same"]) + int(row["post_outcome_all_same"]),
            **global_diagnostics,
            "model_rows": len(model_rows),
            "model_parameters": design_metadata["parameters"],
        })

    write_csv(args.out_dir / "rq3_match_analysis.csv", match_rows)
    write_csv(args.out_dir / "rq3_coverage_audit.csv", audit)
    write_csv(args.out_dir / "rq3_event_performance.csv", performance)
    write_csv(args.out_dir / "rq3_model_diagnostics.csv", event_diagnostics)

    figure_rows = [row for row in performance if row["higher_support_view"]]
    figure_counts = {
        "raw_vs_standardized": scatter_plot(
            figure_rows, "raw_delta_pp", "standardized_delta_pp",
            "Raw versus composition-standardized win-rate change",
            "Raw change (percentage points)", "Standardized change (pp)",
            args.out_dir / "rq3_raw_vs_standardized.png", diagonal=True,
        ),
        "raw_vs_continuing": scatter_plot(
            figure_rows, "raw_delta_pp", "continuing_delta_pp",
            "Raw versus continuing-user win-rate change",
            "Raw change (percentage points)", "Continuing-user change (pp)",
            args.out_dir / "rq3_raw_vs_continuing.png", diagonal=True,
        ),
        "composition_vs_adjustment": scatter_plot(
            figure_rows, "rq2_post_only_vs_both_wasserstein_log1p", "absolute_standardization_shift_pp",
            "Experience gap versus standardization adjustment",
            "Post-only vs both Wasserstein distance (log1p)", "Absolute adjustment (pp)",
            args.out_dir / "rq3_composition_shift_vs_adjustment.png",
        ),
    }

    valid_adjustments = [row["absolute_standardization_shift_pp"] for row in figure_rows if row["absolute_standardization_shift_pp"] is not None]
    separated_cells = sum(int(row["pre_outcome_all_same"]) + int(row["post_outcome_all_same"]) for row in figure_rows)
    primary_audit = [row for row in audit if row["higher_support_view"]]
    direction_standardized = sum(row["direction_changed_raw_vs_standardized"] is True for row in figure_rows)
    direction_continuing = sum(row["direction_changed_raw_vs_continuing"] is True for row in figure_rows)
    paired = [
        row for row in figure_rows
        if row["rq2_post_only_vs_both_wasserstein_log1p"] is not None and row["absolute_standardization_shift_pp"] is not None
    ]
    x = [row["rq2_post_only_vs_both_wasserstein_log1p"] for row in paired]
    y = [row["absolute_standardization_shift_pp"] for row in paired]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_view_events": len(higher_event_ids),
        "match_analysis_rows": len(match_rows),
        "experience_eligible_primary_match_rows": len(model_rows),
        "model": "provisional pooled logistic g-computation: event + event×post + log1p prior count + rank + primary role",
        "standardization_target": "event-specific pre-period eligible match-level covariate distribution",
        "raw_delta_definition": "eligible-sample post win rate minus eligible-sample pre win rate",
        "continuing_delta_definition": "eligible-sample both-period users only",
        "global_model_diagnostics": global_diagnostics,
        "separated_event_period_cells": separated_cells,
        "minimum_eligible_users_in_an_event_period": min(row["experience_eligible_users"] for row in primary_audit),
        "minimum_eligible_matches_in_an_event_period": min(row["experience_eligible_matches"] for row in primary_audit),
        "median_absolute_standardization_shift_pp": statistics.median(valid_adjustments),
        "events_adjustment_at_least_1pp": sum(value >= 1 for value in valid_adjustments),
        "events_adjustment_at_least_2pp": sum(value >= 2 for value in valid_adjustments),
        "events_adjustment_at_least_5pp": sum(value >= 5 for value in valid_adjustments),
        "direction_changed_raw_vs_standardized": direction_standardized,
        "direction_changed_raw_vs_continuing": direction_continuing,
        "composition_adjustment_pairs": len(paired),
        "composition_gap_vs_adjustment_pearson": correlation(x, y),
        "composition_gap_vs_adjustment_spearman": correlation(x, y, spearman=True),
        "figure_counts": figure_counts,
        "claim_boundary": "composition-standardized difference; not a true or causal patch effect",
        "inference": "descriptive first pass; no p-values, confidence intervals, or significance filtering",
    }
    (args.out_dir / "rq3_metadata.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# RQ3 provisional composition-standardized performance report", "",
        "The adjusted quantity is a composition-standardized difference, not a true or causal patch effect.", "",
        f"- Higher-support events: {len(higher_event_ids)}",
        f"- Match-analysis rows across all events: {len(match_rows):,}",
        f"- Experience-eligible match rows in the primary model: {len(model_rows):,}",
        f"- Model converged: {global_diagnostics['converged']} in {global_diagnostics['iterations']} iterations",
        f"- Event-period cells with all wins or all losses: {separated_cells}/194",
        f"- Minimum eligible users in an event-period cell: {summary['minimum_eligible_users_in_an_event_period']}",
        f"- Minimum eligible matches in an event-period cell: {summary['minimum_eligible_matches_in_an_event_period']}",
        f"- Median absolute standardized-versus-raw difference: {summary['median_absolute_standardization_shift_pp']:.2f} pp",
        f"- Events with adjustment >=1 pp: {summary['events_adjustment_at_least_1pp']}/{len(higher_event_ids)}",
        f"- Events with adjustment >=2 pp: {summary['events_adjustment_at_least_2pp']}/{len(higher_event_ids)}",
        f"- Events with adjustment >=5 pp: {summary['events_adjustment_at_least_5pp']}/{len(higher_event_ids)}",
        f"- Raw versus standardized direction reversals: {direction_standardized}/{len(higher_event_ids)}",
        f"- Raw versus continuing-user direction reversals: {direction_continuing}/{len(higher_event_ids)}",
        f"- Experience-gap versus adjustment Pearson correlation: {summary['composition_gap_vs_adjustment_pearson']}",
        f"- Experience-gap versus adjustment Spearman correlation: {summary['composition_gap_vs_adjustment_spearman']}", "",
        "The first-pass model is provisional. It uses continuous log1p familiarity; the 0 / 1–4 / 5+ groups are retained only for interpretation.",
        "Two event-period cells have complete outcome separation, producing near-boundary fitted probabilities; this is recorded in the diagnostics and is one reason the estimator is not yet locked.",
        "No p-values, confidence intervals, bootstrap selection, or significance-based event filtering were run.",
    ]
    (args.out_dir / "rq3_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
