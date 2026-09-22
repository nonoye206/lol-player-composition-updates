#!/usr/bin/env python3
"""RQ4 exploratory boundary-condition analysis using frozen RQ1-RQ3 outputs."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any

import numpy as np


PREDICTORS = [
    "post_only_share_union",
    "abs_delta_observed_new_pp",
    "familiarity_wasserstein_log1p",
    "rank_tvd",
    "role_tvd",
    "log1p_event_support",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty output: {path}")
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def as_float(value: str | float | int) -> float:
    return float(value)


def optional_float(value: str | float | int | None) -> float | None:
    return float(value) if value not in (None, "") else None


def rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    return ranks


def correlation(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def gaussian_smooth(x: np.ndarray, y: np.ndarray, points: int = 120) -> tuple[np.ndarray, np.ndarray]:
    grid = np.linspace(float(np.min(x)), float(np.max(x)), points)
    span = float(np.max(x) - np.min(x))
    bandwidth = max(span * 0.22, 1e-9)
    fitted = []
    for center in grid:
        weights = np.exp(-0.5 * ((x - center) / bandwidth) ** 2)
        fitted.append(float(np.sum(weights * y) / np.sum(weights)))
    return grid, np.array(fitted)


def build_table(args: argparse.Namespace) -> list[dict[str, Any]]:
    rq1 = {row["event_id"]: row for row in read_csv(args.rq1)}
    rq2 = {row["event_id"]: row for row in read_csv(args.rq2)}
    perf = {row["event_id"]: row for row in read_csv(args.performance) if row["higher_support_view"].lower() == "true"}
    ess_rows = read_csv(args.ess)
    ess: dict[str, dict[str, float]] = {}
    for row in ess_rows:
        ess.setdefault(row["event_id"], {})[row["period"]] = as_float(row["player_match_ess"])

    rows: list[dict[str, Any]] = []
    for event_id in sorted(perf):
        a, b, c = rq1[event_id], rq2[event_id], perf[event_id]
        eligible_pre = int(c["eligible_pre_users"])
        eligible_post = int(c["eligible_post_users"])
        event_support = min(eligible_pre, eligible_post)
        event_ess = min(ess[event_id]["pre"], ess[event_id]["post"])
        adjustment = abs(as_float(c["standardized_delta_pp"]) - as_float(c["raw_delta_pp"]))
        rows.append({
            "event_id": event_id,
            "champion": c["champion"],
            "patch": c["patch"],
            "raw_delta_pp": as_float(c["raw_delta_pp"]),
            "standardized_delta_pp": as_float(c["standardized_delta_pp"]),
            "adjustment_magnitude_pp": adjustment,
            "adjustment_ge_2pp": adjustment >= 2.0,
            "post_only_share_union": as_float(a["post_only_among_union"]),
            "abs_delta_observed_new_pp": abs(as_float(a["delta_observed_new_pp"])),
            "familiarity_wasserstein_log1p": optional_float(c["rq2_post_only_vs_both_wasserstein_log1p"]),
            "rank_tvd": as_float(a["rank_tvd"]),
            "role_tvd": as_float(a["role_tvd"]),
            "n_pre": int(a["n_pre_users"]),
            "n_post": int(a["n_post_users"]),
            "experience_eligible_pre": eligible_pre,
            "experience_eligible_post": eligible_post,
            "event_support": event_support,
            "log1p_event_support": math.log1p(event_support),
            "player_match_ess": event_ess,
            "pre_player_match_ess": ess[event_id]["pre"],
            "post_player_match_ess": ess[event_id]["post"],
        })
    if len(rows) != 97:
        raise ValueError(f"Expected 97 frozen higher-support events, found {len(rows)}")
    return rows


def correlation_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    y_all = np.array([row["adjustment_magnitude_pp"] for row in rows], dtype=float)
    labels = {
        "post_only_share_union": "Post-only share among pre/post union",
        "abs_delta_observed_new_pp": "Absolute observed-new share change (pp)",
        "familiarity_wasserstein_log1p": "Post-only vs continuing familiarity Wasserstein (log1p)",
        "rank_tvd": "Rank TVD",
        "role_tvd": "Role TVD",
        "event_support": "Minimum eligible users across periods",
        "log1p_event_support": "Log1p minimum eligible users across periods",
        "player_match_ess": "Minimum player-match ESS across periods",
    }
    output = []
    for name, label in labels.items():
        pairs = [(row[name], y) for row, y in zip(rows, y_all) if row[name] is not None]
        x = np.array([pair[0] for pair in pairs], dtype=float)
        y = np.array([pair[1] for pair in pairs], dtype=float)
        output.append({
            "predictor": name,
            "label": label,
            "n_events": len(pairs),
            "pearson": correlation(x, y),
            "spearman": correlation(rankdata(x), rankdata(y)),
        })
    return output


def exploratory_model(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    complete = [row for row in rows if all(row[name] is not None for name in PREDICTORS)]
    y = np.array([row["adjustment_magnitude_pp"] for row in complete], dtype=float)
    raw_x = np.column_stack([[row[name] for row in complete] for name in PREDICTORS]).astype(float)
    means = raw_x.mean(axis=0)
    sds = raw_x.std(axis=0, ddof=0)
    if np.any(sds == 0):
        raise ValueError("A frozen RQ4 predictor has zero variance")
    z = (raw_x - means) / sds
    design = np.column_stack([np.ones(len(complete)), z])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ beta
    residual = y - fitted
    n, p = design.shape
    sigma2 = float(np.sum(residual**2) / (n - p))
    covariance = sigma2 * np.linalg.inv(design.T @ design)
    se = np.sqrt(np.diag(covariance))
    tss = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum(residual**2)) / tss
    adjusted_r2 = 1.0 - (1.0 - r2) * (n - 1) / (n - p)
    output = [{
        "term": "intercept",
        "standardized_predictor": False,
        "coefficient_pp": float(beta[0]),
        "standard_error_pp": float(se[0]),
        "predictor_mean": "",
        "predictor_sd": "",
    }]
    for index, name in enumerate(PREDICTORS, start=1):
        output.append({
            "term": name,
            "standardized_predictor": True,
            "coefficient_pp": float(beta[index]),
            "standard_error_pp": float(se[index]),
            "predictor_mean": float(means[index - 1]),
            "predictor_sd": float(sds[index - 1]),
        })
    return output, {"n": n, "predictors": p - 1, "r_squared": r2, "adjusted_r_squared": adjusted_r2}


def font(size: int, bold: bool = False):
    from PIL import ImageFont
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def plot_group(rows: list[dict[str, Any]], specs: list[tuple[str, str]], title: str, path: Path) -> None:
    from PIL import Image, ImageDraw

    panel_width, height = 560, 500
    width = panel_width * len(specs)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((35, 18), title, fill="#222222", font=font(25, True))
    y_values = np.array([row["adjustment_magnitude_pp"] for row in rows], dtype=float)
    y_min, y_max = 0.0, max(2.2, float(y_values.max()) * 1.08)
    for panel, (name, label) in enumerate(specs):
        offset = panel * panel_width
        left, right, top, bottom = offset + 78, offset + panel_width - 25, 75, height - 72
        pairs = [(row[name], row["adjustment_magnitude_pp"]) for row in rows if row[name] is not None]
        x_values = np.array([pair[0] for pair in pairs], dtype=float)
        panel_y_values = np.array([pair[1] for pair in pairs], dtype=float)
        x_min, x_max = float(x_values.min()), float(x_values.max())
        if x_min == x_max:
            x_max = x_min + 1
        for tick in range(6):
            x = left + (right - left) * tick / 5
            y = bottom - (bottom - top) * tick / 5
            draw.line((x, top, x, bottom), fill="#eeeeee", width=1)
            draw.line((left, y, right, y), fill="#eeeeee", width=1)
            xv = x_min + (x_max - x_min) * tick / 5
            yv = y_min + (y_max - y_min) * tick / 5
            draw.text((x - 18, bottom + 9), f"{xv:.1f}", fill="#444444", font=font(13))
            draw.text((left - 49, y - 8), f"{yv:.1f}", fill="#444444", font=font(13))
        draw.line((left, top, left, bottom), fill="#333333", width=2)
        draw.line((left, bottom, right, bottom), fill="#333333", width=2)
        threshold_y = bottom - (2.0 - y_min) / (y_max - y_min) * (bottom - top)
        draw.line((left, threshold_y, right, threshold_y), fill="#777777", width=2)
        for xv, yv in zip(x_values, panel_y_values):
            x = left + (xv - x_min) / (x_max - x_min) * (right - left)
            y = bottom - (yv - y_min) / (y_max - y_min) * (bottom - top)
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#35618fa6", outline="#244a70")
        gx, gy = gaussian_smooth(x_values, panel_y_values)
        trend = []
        for xv, yv in zip(gx, gy):
            x = left + (xv - x_min) / (x_max - x_min) * (right - left)
            y = bottom - (yv - y_min) / (y_max - y_min) * (bottom - top)
            trend.append((x, y))
        draw.line(trend, fill="#c4473a", width=3)
        draw.text((left + 10, height - 35), label, fill="#333333", font=font(15))
        if panel == 0:
            draw.text((8, top + (bottom - top) / 2), "Adjustment (pp)", fill="#333333", font=font(14))
    image.save(path)


def report(rows: list[dict[str, Any]], corr: list[dict[str, Any]], model: list[dict[str, Any]], stats: dict[str, float]) -> str:
    large = [row for row in rows if row["adjustment_ge_2pp"]]
    remainder = [row for row in rows if not row["adjustment_ge_2pp"]]
    median = lambda items, key: float(np.median([row[key] for row in items]))
    corr_lines = "\n".join(
        f"- {row['label']}: Pearson {row['pearson']:.3f}; Spearman {row['spearman']:.3f}"
        for row in corr
    )
    coefficient_lines = "\n".join(
        f"- {row['term']}: {row['coefficient_pp']:.3f} pp per 1 SD (SE {row['standard_error_pp']:.3f})"
        for row in model[1:]
    )
    top = sorted(rows, key=lambda row: row["adjustment_magnitude_pp"], reverse=True)[:6]
    top_lines = "\n".join(
        f"- {row['champion']} {row['patch']}: {row['adjustment_magnitude_pp']:.2f} pp; "
        f"rank TVD {row['rank_tvd']:.2f}, role TVD {row['role_tvd']:.2f}, support {row['event_support']}, ESS {row['player_match_ess']:.2f}"
        for row in top
    )
    return f"""# RQ4 exploratory boundary-condition report

RQ4 asks when observable player composition materially changes raw win-rate measurement. It reuses the frozen 97-event RQ3 analysis set and M0 estimates. No new data, estimator, outcome, or event selection was introduced.

## Definitions

- Outcome: `abs(standardized_delta_pp - raw_delta_pp)`.
- Post-only share uses the pre/post user union denominator.
- Familiarity Wasserstein compares post-only with continuing users on log1p prior champion count, matching the frozen RQ3 composition-gap diagnostic.
- Event support is the minimum number of experience-eligible users across pre and post.
- Player-match ESS is the minimum pre/post ESS and is used as a separate support diagnostic.
- Smooth lines are descriptive Gaussian-kernel trends. They are not inferential fits.

## Bivariate associations

{corr_lines}

There are {len(large)}/97 events with an adjustment of at least 2 pp.

The six >=2 pp events have median eligible support {median(large, 'event_support'):.1f}, compared with {median(remainder, 'event_support'):.1f} among the remaining events. Their median minimum player-match ESS is {median(large, 'player_match_ess'):.2f}, compared with {median(remainder, 'player_match_ess'):.2f}. Rank and role TVD are somewhat higher in the six events, but their bivariate associations across all 97 events remain weak. No turnover, familiarity, rank, or role pattern consistently separates the large-adjustment events.

## Largest adjustments

{top_lines}

The complete ranked top 15 is in `rq4_top_adjustment_events.csv`.

## Exploratory multivariable model

The OLS model uses standardized predictors and the six prespecified terms. Coefficients are descriptive associations with adjustment magnitude, not causal effects and not a variable-selection exercise.

{coefficient_lines}

- Model R-squared: {stats['r_squared']:.3f}
- Adjusted R-squared: {stats['adjusted_r_squared']:.3f}
- Complete-case events: {int(stats['n'])}/97. Four events lack the post-only-versus-continuing familiarity Wasserstein because one comparison group is absent.

No p-value threshold is used. A coefficient describes the adjusted change in absolute adjustment, in percentage points, associated with a one-standard-deviation difference in that predictor within the 93 complete-case events.

## Boundary-condition interpretation

The composition indicators do not reliably identify events whose raw win-rate estimate changes materially after adjustment. Lower support shows the clearest association with larger adjustments, which is more consistent with sparse-event sensitivity than with a repeatable substantive composition boundary. The evidence therefore supports the project-level conclusion that composition changes are common and structured, but user turnover, familiarity shift, rank shift, and role shift do not reliably predict meaningful distortion in aggregate win-rate estimates in this sample.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rq1", type=Path, default=Path("results/rq1/rq1_event_summary_higher_support.csv"))
    parser.add_argument("--rq2", type=Path, default=Path("results/rq2/rq2_event_experience_shift_higher_support.csv"))
    parser.add_argument("--performance", type=Path, default=Path("results/rq3/rq3_event_performance.csv"))
    parser.add_argument("--ess", type=Path, default=Path("results/rq3_robustness/rq3_player_weight_diagnostics.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/rq4"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = build_table(args)
    correlations = correlation_table(rows)
    model, stats = exploratory_model(rows)
    ranked = sorted(rows, key=lambda row: row["adjustment_magnitude_pp"], reverse=True)
    top = [{"adjustment_rank": index, **row} for index, row in enumerate(ranked[:15], start=1)]

    write_csv(args.out_dir / "rq4_boundary_conditions.csv", rows)
    write_csv(args.out_dir / "rq4_top_adjustment_events.csv", top)
    write_csv(args.out_dir / "rq4_correlations.csv", correlations)
    write_csv(args.out_dir / "rq4_exploratory_model.csv", model)

    plot_group(rows, [("rank_tvd", "Rank TVD"), ("role_tvd", "Role TVD")], "Rank and role composition shifts", args.out_dir / "rq4_rank_role_vs_adjustment.png")
    plot_group(rows, [("post_only_share_union", "Post-only share among union"), ("abs_delta_observed_new_pp", "Absolute observed-new change (pp)"), ("familiarity_wasserstein_log1p", "Familiarity Wasserstein (log1p)")], "Turnover and familiarity shifts", args.out_dir / "rq4_turnover_familiarity_vs_adjustment.png")
    plot_group(rows, [("event_support", "Minimum eligible users"), ("player_match_ess", "Minimum player-match ESS")], "Event support and adjustment", args.out_dir / "rq4_support_vs_adjustment.png")
    (args.out_dir / "rq4_report.md").write_text(report(rows, correlations, model, stats), encoding="utf-8")


if __name__ == "__main__":
    main()
