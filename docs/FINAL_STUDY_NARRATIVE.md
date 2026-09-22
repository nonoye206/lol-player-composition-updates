# Frozen study narrative

**Lock date:** 2026-09-21

## Title

**Who Plays Changes, but Does It Matter? Player Composition Around League of Legends Updates**

## Headline

> **Who plays changes a lot—but, for win rate, it matters less than expected.**

## Core result

Player composition changes substantially around champion updates, and newly observed users are systematically less experienced with the focal champion. However, these observable composition shifts have only limited impact on aggregate win-rate changes.

The conceptual result is `composition shift != outcome distortion`. The first condition is strongly present; the second remains limited because observed familiarity has only a weak relationship with win in this dataset.

## Research-question arc

1. **RQ1 — Does the player population change around champion updates?** Yes. Among higher-support events, the median post-only share of the pre/post user union is 35.5%, and the median rank and role TVDs are both 0.20.
2. **RQ2 — How does prior champion experience differ within changing populations?** Post-only users have lower mean log familiarity than continuing users in 92 of 93 comparable events. Their pooled prior-use medians are 0 and 5, respectively.
3. **RQ3 — Does the change materially alter performance evaluation?** Usually little for win rate. The baseline median absolute standardized-versus-raw difference is 0.72 pp; 6/97 events differ by at least 2 pp, none by at least 5 pp, and 2/97 reverse direction.

## Table 1. Dataset and analysis coverage

| Item | Result |
| --- | ---: |
| Players | 500 |
| Ranked Solo/Duo matches | 141,738 |
| Official champion × patch events | 258 |
| RQ1 events with pre/post users | 229 |
| Higher-support events | 97 |
| RQ3 match rows | 18,088 |
| RQ3 primary-model eligible matches | 8,502 |
| Primary familiarity window | 100 prior matches |
| Sensitivity window | 50 prior matches |

## Table 2. Composition changes around champion updates

| Result | Finding |
| --- | ---: |
| Median post-only among union, higher-support | **35.5%** |
| Median absolute observed-new-share change | **12.8 pp** |
| Events with absolute observed-new change >=10 pp | **54/97** |
| Median rank TVD | **0.20** |
| Median role TVD | **0.20** |
| Post-only lower experience than continuing | **92/93** |
| Pooled post-only prior-count median | **0** |
| Pooled continuing prior-count median | **5** |

## Table 3. RQ3 estimator robustness

| Estimator | Median absolute adjustment (pp) | >=2pp | >=5pp | Direction flips | Spearman with experience gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| M0 Baseline | **0.72** | 6 | 0 | 2 | 0.068 |
| M1 Post interactions | 0.68 | 10 | 0 | 3 | -0.049 |
| M2 Familiarity spline | 0.72 | 6 | 0 | 2 | 0.035 |
| M3 Player-period weighted | 0.80 | 15 | 1 | 2 | 0.024 |
| M4 Ridge* | 1.65 | 41 | 18 | 3 | -0.018 |
| M5 Weighting | 0.54 | 14 | 0 | 3 | -0.053 |
| S1 50-match window | 0.81 | 6 | 0 | 2 | 0.016 |

*Ridge regularization also shrinks event-specific post-update contrasts and is treated as a regularization-sensitivity analysis rather than a direct estimate of composition adjustment.*

## Main figures

1. Study design and pipeline: 500-player balanced cohort → official champion-patch events → RQ1 population composition → RQ2 champion familiarity → RQ3 raw versus composition-standardized win rate.
2. Higher-support player-composition changes: post-only share, rank TVD, and role TVD.
3. Post-only versus continuing-user familiarity ECDF.
4. Raw versus composition-standardized win-rate change with `y=x`, annotated with median absolute difference 0.72 pp and 2/97 direction flips.

The experience-gap-versus-adjustment plot and continuing-user diagnostics belong in supplementary material.

## Contributions

1. **Measurement:** Player populations around live-service updates are not static.
2. **Behavior:** Newly observed focal-champion users are consistently less experienced than continuing users.
3. **Boundary result:** Strong composition instability does not automatically imply material distortion of aggregate performance metrics; reasonable adjustment for familiarity, rank, and role changes win-rate comparisons only modestly here.

## Integrative mechanism analysis

The model-scale g-computation decomposition closes exactly for every event:

`model raw difference = standardized difference + composition component`.

The maximum numerical identity error is `3.55e-15` percentage points. The median absolute residual between the observed and model-implied raw difference is 0.0000 pp, with a maximum of 0.0008 pp. The small RQ3 adjustment is therefore a small fitted composition component rather than an arithmetic mismatch between observed and modeled change.

Across 97 events, median `|composition component|` is 0.723 pp; 36 events reach 1 pp, 6 reach 2 pp, and none reach 5 pp. Familiarity shows the clearest large-shift/weak-sensitivity mechanism: the median pre/post Wasserstein shift is 0.364, while the median P25-to-P75 predicted win-probability contrast is only 1.80 pp. Rank sensitivity is also modest at 2.67 pp. Role has a larger max-minus-min contrast of 7.87 pp, but `role shift × sensitivity` remains almost unrelated to the actual composition component (Pearson 0.064).

The mechanism is therefore more precise than a mechanical multiplication rule. Aggregate distortion requires three conditions: the population must shift, the changing attribute must be outcome-relevant, and the direction of the shift must align with the outcome gradient on the joint covariate surface. Scalar distribution distance or potential outcome contrast alone is insufficient.

> **Population instability and metric instability are distinct. Distribution shift propagates into aggregate metric distortion only when the shifting attributes are outcome-relevant and the distribution moves along that outcome gradient.**

## Interpretation boundary

These analyses are descriptive and composition-standardized. They do not identify the causal effect of a champion change. The robustness conclusion applies to win rate, observed familiarity/rank/role, the fixed balanced cohort, and the frozen event definitions. It does not establish that composition is unimportant for other outcomes or unobserved player attributes.
