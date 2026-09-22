# Main-text tables

## Table 1. Dataset and analysis coverage

| Item | Result |
| --- | ---: |
| Players | 500 |
| Ranked Solo/Duo matches | 141,738 |
| Official champion × patch events | 258 |
| RQ1 events with pre/post users | 229 |
| Higher-support events | 97 |
| RQ3 focal-champion match rows | 18,088 |
| RQ3 primary-model eligible matches | 8,502 |
| Primary familiarity window | 100 prior matches |
| Sensitivity window | 50 prior matches |

## Table 2. Composition changes around champion updates

| Result | Finding |
| --- | ---: |
| Median post-only share among union | **35.5%** |
| Median absolute observed-new-share change | **12.8 pp** |
| Events with absolute observed-new change ≥10 pp | **54/97** |
| Median rank TVD | **0.20** |
| Median role TVD | **0.20** |
| Post-only lower experience than continuing | **92/93** |
| Pooled post-only prior-count median | **0** |
| Pooled continuing prior-count median | **5** |

## Table 3. RQ3 estimator robustness

| Estimator | Median absolute adjustment (pp) | ≥2pp | ≥5pp | Direction flips | Spearman with experience gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| M0 Baseline | 0.72 | 6 | 0 | 2 | 0.068 |
| M1 Post interactions | 0.68 | 10 | 0 | 3 | -0.049 |
| M2 Familiarity spline | 0.72 | 6 | 0 | 2 | 0.035 |
| M3 Player-period weighted | 0.80 | 15 | 1 | 2 | 0.024 |
| M4 Ridge* | 1.65 | 41 | 18 | 3 | -0.018 |
| M5 Weighting | 0.54 | 14 | 0 | 3 | -0.053 |
| S1 50-match window | 0.81 | 6 | 0 | 2 | 0.016 |

*Ridge also shrinks event-specific post-update contrasts and is treated as a regularization-sensitivity analysis rather than a direct composition-adjustment estimate.*
