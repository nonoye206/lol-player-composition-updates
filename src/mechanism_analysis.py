#!/usr/bin/env python3
"""Mechanism analysis: why large population shifts produce small win-rate distortion."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

import rq3_performance_standardization as rq3


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


def parse_match_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for raw in read_csv(path):
        row: dict[str, Any] = dict(raw)
        for key in ("post", "win", "prior_champion_count_100"):
            row[key] = int(raw[key]) if raw[key] else None
        row["log1p_prior_count"] = float(raw["log1p_prior_count"]) if raw["log1p_prior_count"] else None
        row["experience_eligible_100"] = rq3.parse_bool(raw["experience_eligible_100"])
        row["higher_support_view"] = rq3.parse_bool(raw["higher_support_view"])
        rows.append(row)
    return rows


def predict(rows: list[dict[str, Any]], post: int, beta: np.ndarray, metadata: dict[str, Any]) -> np.ndarray:
    matrix = np.vstack([rq3.design_row(row, post, metadata) for row in rows])
    return rq3.sigmoid(matrix @ beta)


def mean_prediction(rows: list[dict[str, Any]], post: int, beta: np.ndarray, metadata: dict[str, Any]) -> float:
    return float(np.mean(predict(rows, post, beta, metadata)))


def changed_rows(rows: list[dict[str, Any]], **changes: Any) -> list[dict[str, Any]]:
    return [{**row, **changes} for row in rows]


def sensitivity(
    event_rows: list[dict[str, Any]], beta: np.ndarray, metadata: dict[str, Any],
    familiarity_low: float, familiarity_high: float,
) -> dict[str, Any]:
    post_rows = [row for row in event_rows if row["period"] == "post"]
    all_ranks = sorted({row["rank_stratum"] for row in event_rows}, key=rq3.RANKS.index)
    all_roles = sorted({row["primary_role"] for row in event_rows}, key=rq3.ROLES.index)

    low = mean_prediction(changed_rows(post_rows, log1p_prior_count=familiarity_low), 1, beta, metadata)
    high = mean_prediction(changed_rows(post_rows, log1p_prior_count=familiarity_high), 1, beta, metadata)
    rank_predictions = [mean_prediction(changed_rows(post_rows, rank_stratum=value), 1, beta, metadata) for value in all_ranks]
    role_predictions = [mean_prediction(changed_rows(post_rows, primary_role=value), 1, beta, metadata) for value in all_roles]
    return {
        "familiarity_low_log1p": familiarity_low,
        "familiarity_high_log1p": familiarity_high,
        "familiarity_sensitivity_signed_pp": (high - low) * 100,
        "familiarity_sensitivity_pp": abs(high - low) * 100,
        "rank_sensitivity_pp": (max(rank_predictions) - min(rank_predictions)) * 100,
        "role_sensitivity_pp": (max(role_predictions) - min(role_predictions)) * 100,
        "rank_categories_observed": len(all_ranks),
        "role_categories_observed": len(all_roles),
    }


def decompose(
    rows: list[dict[str, Any]], beta: np.ndarray, metadata: dict[str, Any],
    rq4_rows: dict[str, dict[str, str]], performance: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["event_id"]].append(row)
    familiarity = np.array([row["log1p_prior_count"] for row in rows], dtype=float)
    familiarity_low, familiarity_high = (float(value) for value in np.quantile(familiarity, [0.25, 0.75]))
    output = []
    for event_id in metadata["event_ids"]:
        event_rows = grouped[event_id]
        pre = [row for row in event_rows if row["period"] == "pre"]
        post = [row for row in event_rows if row["period"] == "post"]
        e_pre_m_pre = mean_prediction(pre, 0, beta, metadata)
        e_pre_m_post = mean_prediction(pre, 1, beta, metadata)
        e_post_m_post = mean_prediction(post, 1, beta, metadata)
        model_raw = (e_post_m_post - e_pre_m_pre) * 100
        standardized = (e_pre_m_post - e_pre_m_pre) * 100
        composition = (e_post_m_post - e_pre_m_post) * 100
        identity_error = model_raw - standardized - composition
        observed_raw = float(performance[event_id]["raw_delta_pp"])
        support = rq4_rows[event_id]
        row = {
            "event_id": event_id,
            "champion": performance[event_id]["champion"],
            "patch": performance[event_id]["patch"],
            "observed_raw_delta_pp": observed_raw,
            "model_raw_delta_pp": model_raw,
            "standardized_delta_pp": standardized,
            "composition_component_pp": composition,
            "absolute_composition_component_pp": abs(composition),
            "model_fit_residual_pp": observed_raw - model_raw,
            "identity_error_pp": identity_error,
            "turnover_post_only_share_union": float(support["post_only_share_union"]),
            "abs_delta_observed_new_pp": float(support["abs_delta_observed_new_pp"]),
            "familiarity_shift_pre_post_wasserstein_log1p": float(performance[event_id]["rq2_pre_post_wasserstein_log1p"]),
            "familiarity_gap_post_only_vs_both_wasserstein_log1p": performance[event_id]["rq2_post_only_vs_both_wasserstein_log1p"],
            "rank_shift_tvd": float(support["rank_tvd"]),
            "role_shift_tvd": float(support["role_tvd"]),
            "eligible_support": int(support["event_support"]),
            "player_match_ess": float(support["player_match_ess"]),
            **sensitivity(event_rows, beta, metadata, familiarity_low, familiarity_high),
        }
        output.append(row)
    return output


def correlation(x: list[float], y: list[float]) -> float:
    return float(np.corrcoef(np.array(x), np.array(y))[0, 1])


def mechanism_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [
        ("familiarity", "familiarity_shift_pre_post_wasserstein_log1p", "familiarity_sensitivity_pp"),
        ("rank", "rank_shift_tvd", "rank_sensitivity_pp"),
        ("role", "role_shift_tvd", "role_sensitivity_pp"),
    ]
    output = []
    component = [row["absolute_composition_component_pp"] for row in rows]
    for domain, shift_key, sensitivity_key in specs:
        shift = [row[shift_key] for row in rows]
        sensitivity_values = [row[sensitivity_key] for row in rows]
        product = [a * b for a, b in zip(shift, sensitivity_values)]
        output.append({
            "domain": domain,
            "shift_variable": shift_key,
            "sensitivity_variable": sensitivity_key,
            "median_shift": statistics.median(shift),
            "median_sensitivity_pp": statistics.median(sensitivity_values),
            "pearson_shift_with_abs_component": correlation(shift, component),
            "pearson_sensitivity_with_abs_component": correlation(sensitivity_values, component),
            "pearson_shift_times_sensitivity_with_abs_component": correlation(product, component),
        })
    return output


def font(size: int, bold: bool = False):
    from PIL import ImageFont
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def mechanism_map(rows: list[dict[str, Any]], output: Path) -> None:
    from PIL import Image, ImageDraw

    specs = [
        ("familiarity_shift_pre_post_wasserstein_log1p", "familiarity_sensitivity_pp", "Familiarity"),
        ("rank_shift_tvd", "rank_sensitivity_pp", "Rank"),
        ("role_shift_tvd", "role_sensitivity_pp", "Role"),
    ]
    panel_width, height = 570, 540
    image = Image.new("RGB", (panel_width * 3, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((35, 16), "Composition shift and outcome sensitivity", fill="#222222", font=font(27, True))
    max_component = max(row["absolute_composition_component_pp"] for row in rows)
    for panel, (x_key, y_key, label) in enumerate(specs):
        offset = panel * panel_width
        left, right, top, bottom = offset + 82, offset + panel_width - 28, 82, height - 78
        xs = [row[x_key] for row in rows]
        ys = [row[y_key] for row in rows]
        x_min, x_max = 0.0, max(xs) * 1.05 or 1.0
        y_min, y_max = 0.0, max(ys) * 1.08 or 1.0
        x_median, y_median = statistics.median(xs), statistics.median(ys)
        for tick in range(6):
            x = left + (right - left) * tick / 5
            y = bottom - (bottom - top) * tick / 5
            draw.line((x, top, x, bottom), fill="#eeeeee", width=1)
            draw.line((left, y, right, y), fill="#eeeeee", width=1)
            draw.text((x - 18, bottom + 10), f"{x_max * tick / 5:.1f}", fill="#444444", font=font(13))
            draw.text((left - 54, y - 8), f"{y_max * tick / 5:.1f}", fill="#444444", font=font(13))
        xm = left + x_median / x_max * (right - left)
        ym = bottom - y_median / y_max * (bottom - top)
        draw.line((xm, top, xm, bottom), fill="#888888", width=2)
        draw.line((left, ym, right, ym), fill="#888888", width=2)
        draw.line((left, top, left, bottom), fill="#333333", width=2)
        draw.line((left, bottom, right, bottom), fill="#333333", width=2)
        for row in rows:
            x = left + row[x_key] / x_max * (right - left)
            y = bottom - row[y_key] / y_max * (bottom - top)
            radius = 3 + 9 * math.sqrt(row["absolute_composition_component_pp"] / max_component)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#35618f80", outline="#234f80")
        draw.text((left + 120, height - 37), f"{label} shift", fill="#333333", font=font(16))
        if panel == 0:
            draw.text((8, top + 150), "Sensitivity (pp)", fill="#333333", font=font(15))
    draw.text((1265, 48), "Bubble size = |composition component|", fill="#555555", font=font(15))
    image.save(output)


def decomposition_plot(rows: list[dict[str, Any]], output: Path) -> None:
    from PIL import Image, ImageDraw

    ordered = sorted(rows, key=lambda row: row["composition_component_pp"])
    width, height = 1200, 720
    left, right, top, bottom = 100, 45, 75, height - 105
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((left, 20), "Composition component across events", fill="#222222", font=font(28, True))
    bound = max(abs(row["composition_component_pp"]) for row in rows) * 1.08
    zero_y = top + (bound / (2 * bound)) * (bottom - top)
    draw.line((left, zero_y, width - right, zero_y), fill="#555555", width=2)
    for index, row in enumerate(ordered):
        x = left + index / (len(ordered) - 1) * (width - left - right)
        y = top + (bound - row["composition_component_pp"]) / (2 * bound) * (bottom - top)
        color = "#c4473a" if abs(row["composition_component_pp"]) >= 2 else "#35618f"
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color, outline=color)
    for tick in range(5):
        value = -bound + 2 * bound * tick / 4
        y = top + (bound - value) / (2 * bound) * (bottom - top)
        draw.line((left, y, width - right, y), fill="#eeeeee", width=1)
        draw.text((35, y - 9), f"{value:.1f}", fill="#444444", font=font(14))
    draw.text((left + 380, height - 45), "Events ordered by composition component", fill="#333333", font=font(17))
    draw.text((8, top + 230), "Component (pp)", fill="#333333", font=font(15))
    image.save(output)


def report(rows: list[dict[str, Any]], summary: list[dict[str, Any]], diagnostics: dict[str, Any]) -> str:
    abs_components = [row["absolute_composition_component_pp"] for row in rows]
    residuals = [abs(row["model_fit_residual_pp"]) for row in rows]
    identity = [abs(row["identity_error_pp"]) for row in rows]
    sensitivity_lines = "\n".join(
        f"- {row['domain'].title()}: median shift {row['median_shift']:.3f}; median sensitivity {row['median_sensitivity_pp']:.2f} pp; "
        f"corr(shift × sensitivity, |C|) {row['pearson_shift_times_sensitivity_with_abs_component']:.3f}"
        for row in summary
    )
    return f"""# Mechanism Analysis: Why Large Population Shifts Produce Small Win-Rate Distortion

This is an integrative mechanism layer over the frozen RQ1-RQ4 results. It is not a new research question and does not change any prior definition, sample, outcome, or estimator.

## Exact model-scale decomposition

For each event, the fitted M0 outcome surface defines:

`model_raw = E_post[m_post(X)] - E_pre[m_pre(X)]`

`standardized = E_pre[m_post(X)] - E_pre[m_pre(X)]`

`composition component C = E_post[m_post(X)] - E_pre[m_post(X)]`

Therefore `model_raw = standardized + C`. The largest absolute numerical identity error is {max(identity):.3e} pp.

The observed raw difference is retained separately. The median absolute observed-versus-model residual is {statistics.median(residuals):.4f} pp and the maximum is {max(residuals):.4f} pp. This residual is a model-fit diagnostic rather than a composition component.

## Composition component

- Median |C|: {statistics.median(abs_components):.3f} pp
- Events with |C| >=1 pp: {sum(value >= 1 for value in abs_components)}/97
- Events with |C| >=2 pp: {sum(value >= 2 for value in abs_components)}/97
- Events with |C| >=5 pp: {sum(value >= 5 for value in abs_components)}/97

## Shift and outcome sensitivity

Familiarity sensitivity is the average post-model predicted-probability contrast between the global P25 and P75 of log1p prior champion count. Rank and role sensitivity are event-specific max-minus-min average predicted-probability contrasts across categories observed in that event. All sensitivities are measured in win-probability percentage points.

{sensitivity_lines}

The shift × sensitivity products are conceptual diagnostics. They do not replace the exact g-computation component and are not interpreted as additive variable contributions.

## Interpretation

The formal decomposition confirms that the small RQ3 adjustment is a small model-scale composition component rather than an arithmetic mismatch between observed and modeled raw change. Familiarity has a small predicted-probability contrast, matching the proposed large-shift/weak-sensitivity mechanism. Rank sensitivity is also modest. Role has a larger potential max-minus-min contrast, but role shift × sensitivity is still almost unrelated to |C|. This shows that generic sensitivity and scalar distribution distance are not sufficient: the direction of the shift and its alignment with the joint outcome surface also matter.

Population instability and metric instability are distinct. Distribution shift propagates into aggregate metric distortion only when the shifting attributes are outcome-relevant and the distribution moves along that outcome gradient.

## Scope

This is a descriptive model-based measurement decomposition. It does not identify a causal champion-change effect. It uses the frozen M0 model, 97 higher-support events, 100-match familiarity window, and win outcome. A Shapley allocation across correlated familiarity, rank, and role blocks is not included because it requires a separate, prespecified joint-distribution replacement rule.

Model converged: {diagnostics['converged']} in {diagnostics['iterations']} iterations.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=Path, default=Path("results/rq3/rq3_match_analysis.csv"))
    parser.add_argument("--performance", type=Path, default=Path("results/rq3/rq3_event_performance.csv"))
    parser.add_argument("--rq4", type=Path, default=Path("results/rq4/rq4_boundary_conditions.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/mechanism"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = parse_match_rows(args.matches)
    model_rows = [row for row in all_rows if row["higher_support_view"] and row["experience_eligible_100"]]
    event_ids = sorted({row["event_id"] for row in model_rows})
    if len(event_ids) != 97:
        raise ValueError(f"Expected 97 frozen events, found {len(event_ids)}")
    matrix, outcomes, metadata = rq3.build_design(model_rows, event_ids)
    beta, diagnostics = rq3.fit_logistic_irls(matrix, outcomes)
    performance = {row["event_id"]: row for row in read_csv(args.performance) if row["higher_support_view"].lower() == "true"}
    rq4_rows = {row["event_id"]: row for row in read_csv(args.rq4)}
    rows = decompose(model_rows, beta, metadata, rq4_rows, performance)
    summary = mechanism_summary(rows)

    write_csv(args.out_dir / "mechanism_event_decomposition.csv", rows)
    write_csv(args.out_dir / "mechanism_shift_sensitivity_summary.csv", summary)
    write_csv(args.out_dir / "mechanism_model_diagnostics.csv", [{**diagnostics, "events": len(rows), "matches": len(model_rows)}])
    mechanism_map(rows, args.out_dir / "mechanism_shift_sensitivity_map.png")
    decomposition_plot(rows, args.out_dir / "mechanism_composition_component.png")
    (args.out_dir / "mechanism_report.md").write_text(report(rows, summary, diagnostics), encoding="utf-8")


if __name__ == "__main__":
    main()
