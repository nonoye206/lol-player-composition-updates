#!/usr/bin/env python3
"""Prespecified RQ3 estimator and continuing-user robustness checks."""

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

import numpy as np

import rq3_performance_standardization as base


VARIANTS = ("M0", "M1", "M2", "M3", "M4", "M5", "S1")


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


def parse_match_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for raw in read_csv(path):
        row: dict[str, Any] = dict(raw)
        for key in ("post", "win", "prior_champion_count_100", "prior_champion_count_50"):
            row[key] = int(raw[key]) if raw[key] != "" else None
        for key in ("log1p_prior_count", "log1p_prior_count_50"):
            row[key] = float(raw[key]) if raw[key] != "" else None
        for key in ("experience_eligible_100", "experience_eligible_50", "higher_support_view"):
            row[key] = base.parse_bool(raw[key])
        rows.append(row)
    return rows


def player_period_weights(rows: list[dict[str, Any]]) -> np.ndarray:
    counts = Counter((row["event_id"], row["period"], row["player_id"]) for row in rows)
    return np.array([1.0 / counts[(row["event_id"], row["period"], row["player_id"])] for row in rows])


def feature_metadata(rows: list[dict[str, Any]], event_ids: list[str], variant: str, log_key: str) -> dict[str, Any]:
    values = np.array([row[log_key] for row in rows], dtype=float)
    mean, sd = float(values.mean()), float(values.std()) or 1.0
    names = [f"event:{event_id}" for event_id in event_ids] + [f"event_post:{event_id}" for event_id in event_ids]
    names.append("log1p_prior_count_z")
    spline_knots_z: list[float] = []
    if variant == "M2":
        spline_knots_z = [(math.log1p(value) - mean) / sd for value in (1, 5, 15)]
        names.extend([f"log1p_hinge_at_{value}" for value in (1, 5, 15)])
    names.extend([f"rank:{category}" for category in base.RANKS[1:]])
    names.extend([f"role:{category}" for category in base.ROLES[1:]])
    if variant == "M1":
        names.append("post_x_log1p_prior_count_z")
        names.extend([f"post_x_rank:{category}" for category in base.RANKS[1:]])
        names.extend([f"post_x_role:{category}" for category in base.ROLES[1:]])
    return {
        "event_ids": event_ids,
        "event_index": {event_id: index for index, event_id in enumerate(event_ids)},
        "log_key": log_key,
        "log_mean": mean,
        "log_sd": sd,
        "spline_knots_z": spline_knots_z,
        "feature_names": names,
        "parameters": len(names),
        "variant": variant,
    }


def row_vector(row: dict[str, Any], forced_post: int, meta: dict[str, Any]) -> np.ndarray:
    vector = np.zeros(meta["parameters"], dtype=float)
    event_count = len(meta["event_ids"])
    event_position = meta["event_index"][row["event_id"]]
    vector[event_position] = 1
    vector[event_count + event_position] = forced_post
    cursor = 2 * event_count
    z = (row[meta["log_key"]] - meta["log_mean"]) / meta["log_sd"]
    vector[cursor] = z
    cursor += 1
    if meta["variant"] == "M2":
        for knot in meta["spline_knots_z"]:
            vector[cursor] = max(0.0, z - knot)
            cursor += 1
    rank_values = []
    for category in base.RANKS[1:]:
        value = float(row["rank_stratum"] == category)
        rank_values.append(value)
        vector[cursor] = value
        cursor += 1
    role_values = []
    for category in base.ROLES[1:]:
        value = float(row["primary_role"] == category)
        role_values.append(value)
        vector[cursor] = value
        cursor += 1
    if meta["variant"] == "M1":
        vector[cursor] = forced_post * z
        cursor += 1
        for value in rank_values:
            vector[cursor] = forced_post * value
            cursor += 1
        for value in role_values:
            vector[cursor] = forced_post * value
            cursor += 1
    return vector


def design_matrix(rows: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.vstack([row_vector(row, row["post"], meta) for row in rows])
    outcomes = np.array([row["win"] for row in rows], dtype=float)
    return matrix, outcomes


def fit_weighted_logistic(
    matrix: np.ndarray, outcomes: np.ndarray, weights: np.ndarray, ridge: float, max_iter: int = 100
) -> tuple[np.ndarray, dict[str, Any]]:
    beta = np.zeros(matrix.shape[1])
    penalty = np.full(matrix.shape[1], ridge)

    def objective(value: np.ndarray) -> float:
        eta = matrix @ value
        return float(np.sum(weights * (np.logaddexp(0, eta) - outcomes * eta)) + 0.5 * np.sum(penalty * value * value))

    current = objective(beta)
    converged = False
    iteration = 0
    for iteration in range(1, max_iter + 1):
        probabilities = base.sigmoid(matrix @ beta)
        variance = np.clip(probabilities * (1 - probabilities), 1e-7, None)
        gradient = matrix.T @ (weights * (probabilities - outcomes)) + penalty * beta
        hessian = (matrix.T * (weights * variance)) @ matrix + np.diag(penalty)
        step = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
        scale = 1.0
        while scale > 1e-6:
            candidate = beta - scale * step
            candidate_objective = objective(candidate)
            if candidate_objective <= current:
                break
            scale *= 0.5
        improvement = current - candidate_objective
        beta, current = candidate, candidate_objective
        if np.max(np.abs(scale * step)) < 1e-8 or abs(improvement) < 1e-8:
            converged = True
            break
    probabilities = base.sigmoid(matrix @ beta)
    return beta, {
        "converged": converged,
        "iterations": iteration,
        "parameters": matrix.shape[1],
        "rows": matrix.shape[0],
        "ridge": ridge,
        "min_probability": float(probabilities.min()),
        "max_probability": float(probabilities.max()),
        "extreme_predictions": int(np.sum((probabilities < 0.01) | (probabilities > 0.99))),
        "max_absolute_coefficient": float(np.max(np.abs(beta))),
        "brier_score": float(np.average((outcomes - probabilities) ** 2, weights=weights)),
    }


def weighted_mean(values: list[float], weights: list[float]) -> float | None:
    return float(np.average(values, weights=weights)) if values else None


def estimate_outcome_variant(
    rows: list[dict[str, Any]], event_ids: list[str], variant: str, window: int = 100
) -> tuple[list[dict[str, Any]], dict[str, Any], np.ndarray, dict[str, Any]]:
    log_key = "log1p_prior_count" if window == 100 else "log1p_prior_count_50"
    eligible_key = "experience_eligible_100" if window == 100 else "experience_eligible_50"
    analysis = [row for row in rows if row["event_id"] in event_ids and row[eligible_key]]
    meta = feature_metadata(analysis, event_ids, variant, log_key)
    matrix, outcomes = design_matrix(analysis, meta)
    weights = player_period_weights(analysis) if variant == "M3" else np.ones(len(analysis))
    ridge = 1.0 if variant == "M4" else 1e-6
    beta, diagnostics = fit_weighted_logistic(matrix, outcomes, weights, ridge)
    row_weights = {id(row): weight for row, weight in zip(analysis, weights)}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in analysis:
        grouped[(row["event_id"], row["period"])].append(row)
    output = []
    for event_id in event_ids:
        pre, post = grouped[(event_id, "pre")], grouped[(event_id, "post")]
        pre_weights = [row_weights[id(row)] for row in pre]
        post_weights = [row_weights[id(row)] for row in post]
        raw_pre = weighted_mean([row["win"] for row in pre], pre_weights)
        raw_post = weighted_mean([row["win"] for row in post], post_weights)
        reference_rows = pre
        reference_weights = pre_weights
        predicted_pre = [float(base.sigmoid(np.array([row_vector(row, 0, meta) @ beta]))[0]) for row in reference_rows]
        predicted_post = [float(base.sigmoid(np.array([row_vector(row, 1, meta) @ beta]))[0]) for row in reference_rows]
        standardized_pre = weighted_mean(predicted_pre, reference_weights)
        standardized_post = weighted_mean(predicted_post, reference_weights)
        raw_delta = base.delta_pp(raw_post, raw_pre)
        standardized_delta = base.delta_pp(standardized_post, standardized_pre)
        output.append({
            "variant": variant if window == 100 else "S1",
            "event_id": event_id,
            "window": window,
            "pre_matches": len(pre),
            "post_matches": len(post),
            "pre_users": len({row["player_id"] for row in pre}),
            "post_users": len({row["player_id"] for row in post}),
            "raw_delta_pp": raw_delta,
            "standardized_delta_pp": standardized_delta,
            "standardization_shift_pp": standardized_delta - raw_delta,
            "absolute_standardization_shift_pp": abs(standardized_delta - raw_delta),
            "direction_flip": base.direction_reversed(raw_delta, standardized_delta),
        })
    return output, diagnostics, beta, meta


def estimate_weighting(rows: list[dict[str, Any]], event_ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    analysis = [row for row in rows if row["event_id"] in event_ids and row["experience_eligible_100"]]
    values = np.array([row["log1p_prior_count"] for row in analysis])
    mean, sd = float(values.mean()), float(values.std()) or 1.0
    event_index = {event_id: i for i, event_id in enumerate(event_ids)}
    p = len(event_ids) + 1 + len(base.RANKS) - 1 + len(base.ROLES) - 1
    matrix = np.zeros((len(analysis), p))
    outcome = np.array([row["post"] for row in analysis], dtype=float)
    for i, row in enumerate(analysis):
        matrix[i, event_index[row["event_id"]]] = 1
        cursor = len(event_ids)
        matrix[i, cursor] = (row["log1p_prior_count"] - mean) / sd
        cursor += 1
        for category in base.RANKS[1:]:
            matrix[i, cursor] = row["rank_stratum"] == category
            cursor += 1
        for category in base.ROLES[1:]:
            matrix[i, cursor] = row["primary_role"] == category
            cursor += 1
    beta, diagnostics = fit_weighted_logistic(matrix, outcome, np.ones(len(analysis)), 1e-6)
    propensity = np.clip(base.sigmoid(matrix @ beta), 0.02, 0.98)
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], float]]] = defaultdict(list)
    for row, probability in zip(analysis, propensity):
        weight = (1 - probability) / probability if row["post"] else 1.0
        grouped[(row["event_id"], row["period"])].append((row, weight))
    output = []
    for event_id in event_ids:
        pre = grouped[(event_id, "pre")]
        post = grouped[(event_id, "post")]
        raw_pre = statistics.fmean(row["win"] for row, _ in pre)
        raw_post = statistics.fmean(row["win"] for row, _ in post)
        standardized_pre = raw_pre
        standardized_post = weighted_mean([row["win"] for row, _ in post], [weight for _, weight in post])
        raw_delta = base.delta_pp(raw_post, raw_pre)
        standardized_delta = base.delta_pp(standardized_post, standardized_pre)
        post_weights = [weight for _, weight in post]
        output.append({
            "variant": "M5",
            "event_id": event_id,
            "window": 100,
            "pre_matches": len(pre),
            "post_matches": len(post),
            "pre_users": len({row["player_id"] for row, _ in pre}),
            "post_users": len({row["player_id"] for row, _ in post}),
            "raw_delta_pp": raw_delta,
            "standardized_delta_pp": standardized_delta,
            "standardization_shift_pp": standardized_delta - raw_delta,
            "absolute_standardization_shift_pp": abs(standardized_delta - raw_delta),
            "direction_flip": base.direction_reversed(raw_delta, standardized_delta),
            "post_weight_max": max(post_weights),
            "post_weight_ess": sum(post_weights) ** 2 / sum(weight * weight for weight in post_weights),
        })
    diagnostics.update({
        "propensity_clipping": "0.02-0.98",
        "max_post_odds_weight": max((1 - p) / p for p, row in zip(propensity, analysis) if row["post"]),
        "extreme_propensities_before_clipping_not_stored": True,
    })
    return output, diagnostics


def variant_summary(
    estimates: list[dict[str, Any]], diagnostics: dict[str, dict[str, Any]], rq2_gap: dict[str, float]
) -> list[dict[str, Any]]:
    output = []
    for variant in VARIANTS:
        rows = [row for row in estimates if row["variant"] == variant]
        shifts = [row["absolute_standardization_shift_pp"] for row in rows]
        paired = [(rq2_gap[row["event_id"]], row["absolute_standardization_shift_pp"]) for row in rows if row["event_id"] in rq2_gap]
        x, y = [a for a, _ in paired], [b for _, b in paired]
        diag = diagnostics[variant]
        output.append({
            "variant": variant,
            "purpose": {
                "M0": "baseline pooled outcome regression",
                "M1": "post interactions with familiarity, rank, and role",
                "M2": "piecewise-linear spline familiarity at counts 1, 5, 15",
                "M3": "player-period equal weighting",
                "M4": "ridge-penalized outcome regression",
                "M5": "inverse-odds weighting to pre composition",
                "S1": "50-match familiarity window",
            }[variant],
            "interpretation_caution": (
                "ridge also shrinks event-post contrasts; adjustment includes regularization sensitivity"
                if variant == "M4" else
                "post weights clipped through propensity range 0.02-0.98"
                if variant == "M5" else ""
            ),
            "median_absolute_adjustment_pp": statistics.median(shifts),
            "events_adjustment_ge_1pp": sum(value >= 1 for value in shifts),
            "events_adjustment_ge_2pp": sum(value >= 2 for value in shifts),
            "events_adjustment_ge_5pp": sum(value >= 5 for value in shifts),
            "direction_flips": sum(row["direction_flip"] is True for row in rows),
            "correlation_with_rq2_gap_pearson": base.correlation(x, y),
            "correlation_with_rq2_gap_spearman": base.correlation(x, y, spearman=True),
            "extreme_predicted_probabilities": diag.get("extreme_predictions", "not_applicable_outcome_prediction"),
            "events_successfully_estimated": len(rows),
            "converged": diag.get("converged"),
            "max_absolute_coefficient": diag.get("max_absolute_coefficient"),
        })
    return output


def covariate_associations(beta: np.ndarray, meta: dict[str, Any], variant: str) -> list[dict[str, Any]]:
    rows = []
    for name, coefficient in zip(meta["feature_names"], beta):
        if name.startswith(("event:", "event_post:")):
            continue
        rows.append({
            "variant": variant,
            "term": name,
            "coefficient_log_odds": coefficient,
            "odds_ratio": math.exp(max(-20, min(20, coefficient))),
            "reference_or_scale": "one SD" if "log1p" in name and "hinge" not in name else "reference categories GOLD and TOP",
        })
    return rows


def player_weight_diagnostics(rows: list[dict[str, Any]], event_ids: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        if row["event_id"] in event_ids and row["experience_eligible_100"]:
            grouped[(row["event_id"], row["period"])][row["player_id"]] += 1
    output = []
    for event_id in event_ids:
        for period in ("pre", "post"):
            counts = grouped[(event_id, period)]
            total = sum(counts.values())
            shares = [count / total for count in counts.values()]
            output.append({
                "event_id": event_id,
                "period": period,
                "users": len(counts),
                "matches": total,
                "max_player_match_share": max(shares),
                "player_match_ess": 1 / sum(share * share for share in shares),
                "median_matches_per_player": statistics.median(counts.values()),
                "max_matches_by_one_player": max(counts.values()),
            })
    return output


def continuing_diagnostics(rows: list[dict[str, Any]], event_ids: list[str], bootstrap_reps: int = 1000) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, list[int]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    raw_grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        if row["event_id"] not in event_ids or not row["experience_eligible_100"]:
            continue
        raw_grouped[(row["event_id"], row["period"])].append(row["win"])
        if row["participation_status"] == "both":
            grouped[row["event_id"]][row["player_id"]][row["period"]].append(row["win"])
    rng = np.random.default_rng(20260921)
    output = []
    for event_id in event_ids:
        players = {
            player: periods for player, periods in grouped[event_id].items()
            if periods["pre"] and periods["post"]
        }
        player_deltas = [statistics.fmean(periods["post"]) - statistics.fmean(periods["pre"]) for periods in players.values()]
        pre_matches = [win for periods in players.values() for win in periods["pre"]]
        post_matches = [win for periods in players.values() for win in periods["post"]]
        raw_delta = base.delta_pp(
            statistics.fmean(raw_grouped[(event_id, "post")]), statistics.fmean(raw_grouped[(event_id, "pre")])
        )
        match_delta = base.delta_pp(statistics.fmean(post_matches), statistics.fmean(pre_matches)) if pre_matches and post_matches else None
        balanced_delta = statistics.fmean(player_deltas) * 100 if player_deltas else None
        bootstrap = []
        if player_deltas:
            values = np.array(player_deltas)
            for _ in range(bootstrap_reps):
                bootstrap.append(float(rng.choice(values, size=len(values), replace=True).mean() * 100))
        match_counts = [len(periods["pre"]) + len(periods["post"]) for periods in players.values()]
        ess = sum(match_counts) ** 2 / sum(count * count for count in match_counts) if match_counts else None
        output.append({
            "event_id": event_id,
            "n_both_eligible_paired": len(players),
            "continuing_total_matches": sum(match_counts),
            "continuing_match_weight_ess": ess,
            "raw_delta_pp": raw_delta,
            "match_weighted_continuing_delta_pp": match_delta,
            "player_balanced_continuing_delta_pp": balanced_delta,
            "match_weighted_minus_raw_pp": match_delta - raw_delta if match_delta is not None else None,
            "player_balanced_minus_raw_pp": balanced_delta - raw_delta if balanced_delta is not None else None,
            "match_weighted_direction_flip": base.direction_reversed(raw_delta, match_delta),
            "player_balanced_direction_flip": base.direction_reversed(raw_delta, balanced_delta),
            "bootstrap_ci_low_pp": float(np.percentile(bootstrap, 2.5)) if bootstrap else None,
            "bootstrap_ci_high_pp": float(np.percentile(bootstrap, 97.5)) if bootstrap else None,
            "bootstrap_ci_width_pp": float(np.percentile(bootstrap, 97.5) - np.percentile(bootstrap, 2.5)) if bootstrap else None,
            "bootstrap_ci_includes_zero": (
                float(np.percentile(bootstrap, 2.5)) <= 0 <= float(np.percentile(bootstrap, 97.5))
                if bootstrap else None
            ),
            "bootstrap_reps": bootstrap_reps,
        })
    return output


def font(size: int, bold: bool = False):
    from PIL import ImageFont
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def support_plot(rows: list[dict[str, Any]], x_key: str, y_key: str, output: Path, title: str, ylabel: str, binary: bool = False) -> None:
    from PIL import Image, ImageDraw
    points = [(row[x_key], abs(row[y_key]) if not binary else int(row[y_key])) for row in rows if row[x_key] is not None and row[y_key] is not None]
    width, height = 1100, 820
    left, right, top, bottom = 130, 65, 100, 115
    plot_width, plot_height = width - left - right, height - top - bottom
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    x_max = max(x for x, _ in points) or 1
    y_max = 1.1 if binary else max(y for _, y in points) * 1.08 or 1
    draw.line((left, top, left, top + plot_height), fill="#333333", width=3)
    draw.line((left, top + plot_height, left + plot_width, top + plot_height), fill="#333333", width=3)
    for tick in range(6):
        x_value = x_max * tick / 5
        x = left + plot_width * tick / 5
        draw.line((x, top, x, top + plot_height), fill="#EEEEEE", width=1)
        draw.text((x - 15, top + plot_height + 15), f"{x_value:.0f}", fill="#444444", font=font(18))
    y_ticks = (0, 1) if binary else tuple(y_max * tick / 5 for tick in range(6))
    for y_value in y_ticks:
        y = top + plot_height - y_value / y_max * plot_height
        draw.line((left, y, left + plot_width, y), fill="#EEEEEE", width=1)
        draw.text((55, y - 10), f"{y_value:.0f}" if binary else f"{y_value:.1f}", fill="#444444", font=font(18))
    for x_value, y_value in points:
        x = left + x_value / x_max * plot_width
        jitter = 0
        if binary:
            jitter = ((hash((x_value, y_value)) % 101) / 100 - 0.5) * 0.08
        y = top + plot_height - (y_value + jitter) / y_max * plot_height
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#3465A4A0")
    draw.text((left, 25), title, fill="#222222", font=font(32, True))
    draw.text((left + 250, height - 45), x_key.replace("_", " "), fill="#333333", font=font(22))
    draw.text((15, top + plot_height / 2), ylabel, fill="#333333", font=font(22))
    image.convert("RGB").save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="RQ3 prespecified robustness suite")
    parser.add_argument("--match-analysis", type=Path, default=Path("results/rq3/rq3_match_analysis.csv"))
    parser.add_argument("--rq2-groups", type=Path, default=Path("results/rq2/rq2_post_only_vs_both.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/rq3_robustness"))
    parser.add_argument("--bootstrap-reps", type=int, default=1000)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = parse_match_rows(args.match_analysis)
    event_ids = sorted({row["event_id"] for row in rows if row["higher_support_view"]})
    rq2_gap = {
        row["event_id"]: float(row["post_only_vs_both_wasserstein_log1p"])
        for row in read_csv(args.rq2_groups)
        if row["window"] == "100" and row["higher_support_view"] == "True" and row["post_only_vs_both_wasserstein_log1p"]
    }
    all_estimates: list[dict[str, Any]] = []
    diagnostics: dict[str, dict[str, Any]] = {}
    associations: list[dict[str, Any]] = []
    for variant in ("M0", "M1", "M2", "M3", "M4"):
        estimates, diag, beta, meta = estimate_outcome_variant(rows, event_ids, variant)
        all_estimates.extend(estimates)
        diagnostics[variant] = diag
        if variant in {"M0", "M1"}:
            associations.extend(covariate_associations(beta, meta, variant))
    weighting, diagnostics["M5"] = estimate_weighting(rows, event_ids)
    all_estimates.extend(weighting)
    sensitivity, diagnostics["S1"], _, _ = estimate_outcome_variant(rows, event_ids, "M0", window=50)
    for row in sensitivity:
        row["variant"] = "S1"
    all_estimates.extend(sensitivity)

    summaries = variant_summary(all_estimates, diagnostics, rq2_gap)
    player_weights = player_weight_diagnostics(rows, event_ids)
    continuing = continuing_diagnostics(rows, event_ids, args.bootstrap_reps)
    write_csv(args.out_dir / "rq3_estimator_summary.csv", summaries)
    write_csv(args.out_dir / "rq3_robustness_event_estimates.csv", all_estimates)
    write_csv(args.out_dir / "rq3_covariate_association.csv", associations)
    write_csv(args.out_dir / "rq3_player_weight_diagnostics.csv", player_weights)
    write_csv(args.out_dir / "rq3_continuing_diagnostics.csv", continuing)

    support_plot(
        continuing, "n_both_eligible_paired", "match_weighted_minus_raw_pp",
        args.out_dir / "rq3_n_both_vs_continuing_gap.png",
        "Continuing support versus raw/continuing difference", "Absolute difference (pp)",
    )
    support_plot(
        continuing, "continuing_match_weight_ess", "match_weighted_direction_flip",
        args.out_dir / "rq3_ess_vs_direction_flip.png",
        "Continuing effective sample size versus direction flip", "Direction flip (0/1)", binary=True,
    )

    match_flips = sum(row["match_weighted_direction_flip"] is True for row in continuing)
    balanced_flips = sum(row["player_balanced_direction_flip"] is True for row in continuing)
    continuing_comparable = [row for row in continuing if row["player_balanced_continuing_delta_pp"] is not None]
    match_flip_rows = [row for row in continuing if row["match_weighted_direction_flip"] is True]
    stable_match_flips = sum(row["player_balanced_direction_flip"] is True for row in match_flip_rows)
    ci_wide = sum(row["bootstrap_ci_width_pp"] is not None and row["bootstrap_ci_width_pp"] >= 20 for row in continuing)
    ci_includes_zero = sum(row["bootstrap_ci_includes_zero"] is True for row in continuing)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "prespecified_variants": list(VARIANTS),
        "primary_events": len(event_ids),
        "bootstrap_reps": args.bootstrap_reps,
        "variant_diagnostics": diagnostics,
        "continuing_match_weighted_flips": match_flips,
        "continuing_player_balanced_flips": balanced_flips,
        "continuing_events_with_paired_eligible_players": len(continuing_comparable),
        "original_match_flips_remaining_player_balanced": stable_match_flips,
        "continuing_events_ci_width_at_least_20pp": ci_wide,
        "continuing_events_ci_includes_zero": ci_includes_zero,
        "no_significance_hunting": True,
    }
    (args.out_dir / "rq3_robustness_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    lines = [
        "# RQ3 estimator robustness and continuing-user diagnostics", "",
        "All variants were specified for a distinct diagnostic purpose. No estimator was selected because it produced a preferred result.", "",
        "## Estimator summary", "",
        "| Variant | Median absolute adjustment (pp) | >=1pp | >=2pp | >=5pp | Direction flips | Spearman with RQ2 gap | Extreme predictions | Events |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summaries:
        lines.append(f"| {row['variant']} | {row['median_absolute_adjustment_pp']:.3f} | {row['events_adjustment_ge_1pp']} | {row['events_adjustment_ge_2pp']} | {row['events_adjustment_ge_5pp']} | {row['direction_flips']} | {row['correlation_with_rq2_gap_spearman']} | {row['extreme_predicted_probabilities']} | {row['events_successfully_estimated']} |")
    lines.extend(["", "## Continuing users", "",
                  f"- Events with paired eligible continuing users: {len(continuing_comparable)}/{len(continuing)}",
                  f"- Match-weighted direction flips: {match_flips}/{len(continuing_comparable)}",
                  f"- Player-balanced direction flips: {balanced_flips}/{len(continuing_comparable)}",
                  f"- Original match-weighted flips that remain after player balancing: {stable_match_flips}/{match_flips}",
                  f"- Events with paired-player bootstrap CI width >=20pp: {ci_wide}/{len(continuing_comparable)}",
                  f"- Events whose paired-player bootstrap CI includes zero: {ci_includes_zero}/{len(continuing_comparable)}", "",
                  "Bootstrap intervals describe sampling instability among observed continuing players; they are not patch-effect confidence intervals."])
    (args.out_dir / "rq3_robustness_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"summaries": summaries, "continuing": metadata}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
