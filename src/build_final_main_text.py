#!/usr/bin/env python3
"""Build the frozen main-text tables and figures from existing outputs."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


NAVY = "#17324D"
BLUE = "#3E78A8"
ORANGE = "#D55E00"
RED = "#B33A3A"
GRAY = "#5B6570"
LIGHT = "#E7EBEF"
TEXT = "#20262D"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def centered(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], text: str, text_font, fill=TEXT) -> None:
    x0, y0, x1, y1 = box
    bounds = draw.multiline_textbbox((0, 0), text, font=text_font, spacing=7, align="center")
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    draw.multiline_text(((x0 + x1 - width) / 2, (y0 + y1 - height) / 2), text, font=text_font, fill=fill, spacing=7, align="center")


def vertical_label(image: Image.Image, text: str, center_y: int, x: int, size: int = 22) -> None:
    label_font = font(size)
    bounds = label_font.getbbox(text)
    layer = Image.new("RGBA", (bounds[2] - bounds[0] + 18, bounds[3] - bounds[1] + 18), (255, 255, 255, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.text((9, 9), text, font=label_font, fill=TEXT)
    rotated = layer.rotate(90, expand=True)
    image.paste(rotated, (x, int(center_y - rotated.height / 2)), rotated)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill=GRAY, width=5) -> None:
    draw.line((start, end), fill=fill, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 16
    for offset in (2.55, -2.55):
        point = (end[0] + length * math.cos(angle + offset), end[1] + length * math.sin(angle + offset))
        draw.line((end, point), fill=fill, width=width)


def figure1_pipeline(output: Path) -> None:
    width, height = 1800, 1050
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 45), "Study design", font=font(46, True), fill=TEXT)
    draw.text((70, 106), "Player composition around official champion updates", font=font(25), fill=GRAY)

    boxes = [
        (75, 210, 385, 405, "Official Riot API\nNA1 Ranked Solo/Duo\n141,738 matches", "#EAF1F7"),
        (470, 210, 780, 405, "Balanced cohort\n500 active players\n5 ranks × 5 roles", "#EAF1F7"),
        (865, 210, 1175, 405, "Official update events\n258 champion × patch\nvalidated pre-patch", "#F5EFE6"),
        (1260, 210, 1570, 405, "Analysis views\n229 with pre/post users\n97 higher-support events", "#F5EFE6"),
    ]
    for x0, y0, x1, y1, label, color in boxes:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=color, outline=NAVY, width=3)
        centered(draw, (x0 + 14, y0 + 12, x1 - 14, y1 - 12), label, font(25, True))
    for first, second in zip(boxes, boxes[1:]):
        arrow(draw, (first[2] + 12, 307), (second[0] - 12, 307))

    stage_boxes = [
        (120, 585, 520, 820, "RQ1\nPopulation composition", "Turnover\nRank TVD\nRole TVD", "#EAF1F7"),
        (700, 585, 1100, 820, "RQ2\nChampion familiarity", "Prior 100 matches\nPost-only vs continuing", "#F5EFE6"),
        (1280, 585, 1680, 820, "RQ3 + mechanism\nPerformance measurement", "Raw vs standardized\nComposition component", "#E9F3EE"),
    ]
    for x0, y0, x1, y1, title, detail, color in stage_boxes:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=26, fill=color, outline=NAVY, width=3)
        centered(draw, (x0 + 15, y0 + 15, x1 - 15, y0 + 105), title, font(29, True))
        draw.line((x0 + 45, y0 + 112, x1 - 45, y0 + 112), fill="#B6C1CB", width=2)
        centered(draw, (x0 + 15, y0 + 120, x1 - 15, y1 - 15), detail, font(24))
    arrow(draw, (520, 702), (680, 702))
    arrow(draw, (1100, 702), (1260, 702))
    draw.text((105, 915), "Composition shift", font=font(24, True), fill=BLUE)
    arrow(draw, (330, 930), (450, 930), fill=GRAY)
    draw.text((475, 915), "Outcome relevance", font=font(24, True), fill=ORANGE)
    arrow(draw, (705, 930), (825, 930), fill=GRAY)
    draw.text((850, 915), "Alignment", font=font(24, True), fill=NAVY)
    arrow(draw, (985, 930), (1105, 930), fill=GRAY)
    draw.text((1130, 915), "Metric distortion", font=font(24, True), fill=RED)
    image.save(output)


def histogram_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], values: list[float], title: str, xlabel: str, median_label: str, panel: str, bins: int = 10) -> None:
    x0, y0, x1, y1 = box
    left, right, top, bottom = x0 + 78, x1 - 25, y0 + 72, y1 - 70
    lo, hi = min(values), max(values)
    if lo == hi:
        hi = lo + 1
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, int((value - lo) / (hi - lo) * bins))
        counts[index] += 1
    max_count = max(counts)
    draw.text((x0 + 8, y0 + 6), panel, font=font(25, True), fill=TEXT)
    draw.text((x0 + 48, y0 + 8), title, font=font(22, True), fill=TEXT)
    for tick in range(5):
        y = bottom - (bottom - top) * tick / 4
        draw.line((left, y, right, y), fill=LIGHT, width=1)
        draw.text((left - 42, y - 8), str(round(max_count * tick / 4)), font=font(13), fill=GRAY)
    bar_width = (right - left) / bins
    for index, count in enumerate(counts):
        bx0 = left + index * bar_width + 2
        bx1 = left + (index + 1) * bar_width - 2
        by = bottom - count / max_count * (bottom - top)
        draw.rectangle((bx0, by, bx1, bottom), fill=BLUE, outline=NAVY)
    med = statistics.median(values)
    mx = left + (med - lo) / (hi - lo) * (right - left)
    draw.line((mx, top, mx, bottom), fill=ORANGE, width=4)
    draw.text((left + 5, top + 5), f"Median {median_label}", font=font(15, True), fill=ORANGE)
    draw.line((left, top, left, bottom), fill=TEXT, width=2)
    draw.line((left, bottom, right, bottom), fill=TEXT, width=2)
    for tick in range(5):
        x = left + (right - left) * tick / 4
        value = lo + (hi - lo) * tick / 4
        draw.text((x - 18, bottom + 10), f"{value:.1f}", font=font(13), fill=GRAY)
    bounds = draw.textbbox((0, 0), xlabel, font=font(15))
    draw.text(((left + right - (bounds[2] - bounds[0])) / 2, y1 - 30), xlabel, font=font(15), fill=GRAY)


def figure2_composition(rows: list[dict[str, str]], output: Path) -> None:
    width, height = 1800, 1200
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((65, 32), "Player composition changes across higher-support events", font=font(42, True), fill=TEXT)
    draw.text((65, 87), "97 champion × patch events with at least 10 observed users in both periods", font=font(23), fill=GRAY)
    specs = [
        ("post_only_among_union", "Post-only share", "Post-only share", "35.5%", "A"),
        ("delta_observed_new_pp", "Absolute observed-new change (pp)", "|Δ observed-new share| (pp)", "12.8 pp", "B"),
        ("rank_tvd", "Rank TVD", "Rank TVD", "0.20", "C"),
        ("role_tvd", "Role TVD", "Role TVD", "0.20", "D"),
    ]
    boxes = [(45, 145, 885, 650), (915, 145, 1755, 650), (45, 675, 885, 1180), (915, 675, 1755, 1180)]
    for (key, title, xlabel, med, panel), box in zip(specs, boxes):
        values = [abs(float(row[key])) if key == "delta_observed_new_pp" else float(row[key]) for row in rows]
        histogram_panel(draw, box, values, title, xlabel, med, panel)
    image.save(output)


def figure3_ecdf(participation: list[dict[str, str]], higher_ids: set[str], output: Path) -> tuple[int, int]:
    groups: dict[str, list[int]] = {"post_only": [], "both": []}
    for row in participation:
        if row["event_id"] not in higher_ids or row["period"] != "post" or row["experience_eligible_100"].lower() != "true":
            continue
        if row["participation_status"] in groups and row["prior_champion_count_100"]:
            groups[row["participation_status"]].append(int(row["prior_champion_count_100"]))
    width, height = 1800, 1120
    left, right, top, bottom = 175, 100, 165, 920
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((75, 35), "Post-only users have less prior champion experience", font=font(43, True), fill=TEXT)
    draw.text((75, 94), "Higher-support events; pooled post-period player–event observations", font=font(24), fill=GRAY)
    max_value = max(value for values in groups.values() for value in values)
    max_log = math.log1p(max_value)
    for tick in range(6):
        y = bottom - (bottom - top) * tick / 5
        draw.line((left, y, width - right, y), fill=LIGHT, width=1)
        draw.text((92, y - 13), f"{tick / 5:.1f}", font=font(20), fill=GRAY)
    for value in [0, 1, 2, 5, 10, 20, 50, 100]:
        if value > max_value:
            continue
        x = left + math.log1p(value) / max_log * (width - right - left)
        draw.line((x, top, x, bottom), fill="#F1F3F5", width=1)
        draw.text((x - 13, bottom + 17), str(value), font=font(20), fill=GRAY)
    for key, color in (("post_only", ORANGE), ("both", BLUE)):
        values = sorted(groups[key])
        points = []
        for index, value in enumerate(values, start=1):
            x = left + math.log1p(value) / max_log * (width - right - left)
            y = bottom - index / len(values) * (bottom - top)
            points.append((x, y))
        draw.line(points, fill=color, width=7)
    draw.line((left, top, left, bottom), fill=TEXT, width=3)
    draw.line((left, bottom, width - right, bottom), fill=TEXT, width=3)
    draw.text((675, 1010), "Prior focal-champion matches in the previous 100 matches (log scale)", font=font(23), fill=TEXT)
    vertical_label(image, "Empirical CDF", (top + bottom) // 2, 28, 23)
    legend_x, legend_y = 1110, 600
    for index, (key, label, color) in enumerate((("post_only", "Post-only", ORANGE), ("both", "Continuing users (both periods)", BLUE))):
        y = legend_y + index * 65
        draw.line((legend_x, y + 15, legend_x + 70, y + 15), fill=color, width=7)
        med = statistics.median(groups[key])
        draw.text((legend_x + 92, y), f"{label}: n={len(groups[key]):,}, median={med:g}", font=font(22, True), fill=TEXT)
    draw.rounded_rectangle((1060, 380, 1640, 535), radius=18, fill="#F6F7F8", outline="#CAD1D8", width=2)
    centered(draw, (1080, 395, 1620, 520), "Post-only users had lower mean\nlog familiarity in 92 of 93 events", font(23, True))
    image.save(output)
    return len(groups["post_only"]), len(groups["both"])


def figure4_component(rows: list[dict[str, str]], output: Path) -> None:
    ordered = sorted(rows, key=lambda row: float(row["composition_component_pp"]))
    width, height = 1800, 1050
    left, right, top, bottom = 150, 80, 145, 865
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 35), "Composition-induced win-rate difference is usually small", font=font(43, True), fill=TEXT)
    draw.text((70, 94), "Model-scale g-computation component; 97 higher-support events", font=font(24), fill=GRAY)
    values = [float(row["composition_component_pp"]) for row in ordered]
    bound = max(abs(value) for value in values) * 1.12
    for value in [-5, -2.5, 0, 2.5, 5]:
        y = top + (bound - value) / (2 * bound) * (bottom - top)
        draw.line((left, y, width - right, y), fill=LIGHT if value else GRAY, width=3 if value == 0 else 1)
        draw.text((73, y - 13), f"{value:g}", font=font(20), fill=GRAY)
    for value in (-2, 2):
        y = top + (bound - value) / (2 * bound) * (bottom - top)
        segment = 18
        x = left
        while x < width - right:
            draw.line((x, y, min(x + segment, width - right), y), fill="#B9C0C7", width=3)
            x += segment * 2
    for index, (row, value) in enumerate(zip(ordered, values)):
        x = left + index / (len(values) - 1) * (width - right - left)
        y = top + (bound - value) / (2 * bound) * (bottom - top)
        color = RED if abs(value) >= 2 else BLUE
        radius = 8 if abs(value) >= 2 else 6
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="white", width=1)
    draw.line((left, top, left, bottom), fill=TEXT, width=3)
    draw.line((left, bottom, width - right, bottom), fill=TEXT, width=3)
    draw.text((665, 955), "Events ordered by composition component", font=font(23), fill=TEXT)
    vertical_label(image, "Composition component (pp)", (top + bottom) // 2, 20, 20)
    draw.rounded_rectangle((190, 190, 690, 365), radius=18, fill="#F6F7F8", outline="#CAD1D8", width=2)
    centered(draw, (210, 205, 670, 350), "Median |C| = 0.72 pp\n|C| ≥2 pp: 6/97\n|C| ≥5 pp: 0/97", font(25, True))
    draw.ellipse((1320, 205, 1338, 223), fill=RED)
    draw.text((1350, 198), "|C| ≥2 pp", font=font(20), fill=TEXT)
    draw.ellipse((1320, 250, 1338, 268), fill=BLUE)
    draw.text((1350, 243), "|C| <2 pp", font=font(20), fill=TEXT)
    image.save(output)


def tables(out_dir: Path) -> None:
    table1 = [
        {"item": "Players", "result": "500"},
        {"item": "Ranked Solo/Duo matches", "result": "141,738"},
        {"item": "Official champion × patch events", "result": "258"},
        {"item": "RQ1 events with pre/post users", "result": "229"},
        {"item": "Higher-support events", "result": "97"},
        {"item": "RQ3 focal-champion match rows", "result": "18,088"},
        {"item": "RQ3 primary-model eligible matches", "result": "8,502"},
        {"item": "Primary familiarity window", "result": "100 prior matches"},
        {"item": "Sensitivity window", "result": "50 prior matches"},
    ]
    table2 = [
        {"result": "Median post-only share among union", "finding": "35.5%"},
        {"result": "Median absolute observed-new-share change", "finding": "12.8 pp"},
        {"result": "Events with absolute observed-new change ≥10 pp", "finding": "54/97"},
        {"result": "Median rank TVD", "finding": "0.20"},
        {"result": "Median role TVD", "finding": "0.20"},
        {"result": "Post-only lower experience than continuing", "finding": "92/93"},
        {"result": "Pooled post-only prior-count median", "finding": "0"},
        {"result": "Pooled continuing prior-count median", "finding": "5"},
    ]
    source = read_csv(Path("results/rq3_robustness/rq3_estimator_summary.csv"))
    labels = {"M0": "Baseline", "M1": "Post interactions", "M2": "Familiarity spline", "M3": "Player-period weighted", "M4": "Ridge*", "M5": "Weighting", "S1": "50-match window"}
    table3 = [{
        "estimator": f"{row['variant']} {labels[row['variant']]}",
        "median_absolute_adjustment_pp": f"{float(row['median_absolute_adjustment_pp']):.2f}",
        "events_ge_2pp": row["events_adjustment_ge_2pp"],
        "events_ge_5pp": row["events_adjustment_ge_5pp"],
        "direction_flips": row["direction_flips"],
        "spearman_with_experience_gap": f"{float(row['correlation_with_rq2_gap_spearman']):.3f}",
    } for row in source]
    write_csv(out_dir / "table1_dataset_coverage.csv", table1)
    write_csv(out_dir / "table2_composition_results.csv", table2)
    write_csv(out_dir / "table3_rq3_robustness.csv", table3)
    md = """# Main-text tables

## Table 1. Dataset and analysis coverage

| Item | Result |
| --- | ---: |
""" + "\n".join(f"| {r['item']} | {r['result']} |" for r in table1)
    md += "\n\n## Table 2. Composition changes around champion updates\n\n| Result | Finding |\n| --- | ---: |\n"
    md += "\n".join(f"| {r['result']} | **{r['finding']}** |" for r in table2)
    md += "\n\n## Table 3. RQ3 estimator robustness\n\n| Estimator | Median absolute adjustment (pp) | ≥2pp | ≥5pp | Direction flips | Spearman with experience gap |\n| --- | ---: | ---: | ---: | ---: | ---: |\n"
    md += "\n".join(f"| {r['estimator']} | {r['median_absolute_adjustment_pp']} | {r['events_ge_2pp']} | {r['events_ge_5pp']} | {r['direction_flips']} | {r['spearman_with_experience_gap']} |" for r in table3)
    md += "\n\n*Ridge also shrinks event-specific post-update contrasts and is treated as a regularization-sensitivity analysis rather than a direct composition-adjustment estimate.*\n"
    (out_dir / "main_tables.md").write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("results/main"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rq1 = read_csv(Path("results/rq1/rq1_event_summary_higher_support.csv"))
    participation = read_csv(Path("results/rq1/rq1_user_participation.csv"))
    mechanism = read_csv(Path("results/mechanism/mechanism_event_decomposition.csv"))
    higher_ids = {row["event_id"] for row in rq1}
    figure1_pipeline(args.out_dir / "figure1_study_design.png")
    figure2_composition(rq1, args.out_dir / "figure2_composition_shift.png")
    post_n, both_n = figure3_ecdf(participation, higher_ids, args.out_dir / "figure3_familiarity_ecdf.png")
    figure4_component(mechanism, args.out_dir / "figure4_composition_component.png")
    tables(args.out_dir)
    captions = f"""# Main-text figure captions

**Figure 1. Study design.** The analysis begins with a rank × role balanced cohort of 500 active NA1 Ranked Solo/Duo players and 141,738 matches. Official champion-update events define validated adjacent-patch comparisons. The primary descriptive view contains 97 events with at least 10 observed focal-champion users in both periods.

**Figure 2. Player-composition changes across higher-support events.** Event-level distributions of post-only participation, absolute change in observed-new share, rank Total Variation Distance (TVD), and role TVD. Orange lines mark the reported medians. These measures establish that the player population often changes around champion updates.

**Figure 3. Prior champion experience among post-update users.** Empirical cumulative distributions pool {post_n:,} post-only and {both_n:,} continuing-user (both-period) player-event observations from higher-support events with 100-match history eligibility. Pooled medians are 0 and 5 prior focal-champion matches, respectively; post-only users have lower mean log familiarity in 92 of 93 comparable events. Post-only denotes newly observed focal-champion use within the recorded history and does not imply a player's first lifetime use.

**Figure 4. Model-scale composition component across events.** Each point is one higher-support champion × patch event, ordered by the signed g-computation composition component. Median absolute magnitude is 0.72 percentage points; 6 of 97 events reach 2 pp and none reach 5 pp. Red points mark events with an absolute component of at least 2 pp.
"""
    (args.out_dir / "figure_captions.md").write_text(captions, encoding="utf-8")
    manifest = """# Main-text artifact manifest

Included: four frozen main figures, three frozen main tables, and captions.

Supplementary only: shift × sensitivity mechanism map, RQ4 exploratory scatterplots, continuing-user diagnostics, support diagnostics, and alternative RQ3 estimator plots.
"""
    (args.out_dir / "README.md").write_text(manifest, encoding="utf-8")


if __name__ == "__main__":
    main()
