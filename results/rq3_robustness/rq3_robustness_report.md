# RQ3 estimator robustness and continuing-user diagnostics

All variants were specified for a distinct diagnostic purpose. No estimator was selected because it produced a preferred result.

## Estimator summary

| Variant | Median absolute adjustment (pp) | >=1pp | >=2pp | >=5pp | Direction flips | Spearman with RQ2 gap | Extreme predictions | Events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M0 | 0.723 | 36 | 6 | 0 | 2 | 0.06766434901972487 | 11 | 97 |
| M1 | 0.685 | 33 | 10 | 0 | 3 | -0.04892423383366656 | 11 | 97 |
| M2 | 0.719 | 38 | 6 | 0 | 2 | 0.03488406791799708 | 11 | 97 |
| M3 | 0.800 | 40 | 15 | 1 | 2 | 0.02378323535555489 | 11 | 97 |
| M4 | 1.649 | 60 | 41 | 18 | 3 | -0.017636000119363792 | 0 | 97 |
| M5 | 0.541 | 30 | 14 | 0 | 3 | -0.05301244367521112 | 0 | 97 |
| S1 | 0.815 | 33 | 6 | 0 | 2 | 0.01626331652293277 | 0 | 97 |

## Continuing users

- Events with paired eligible continuing users: 93/97
- Match-weighted direction flips: 20/93
- Player-balanced direction flips: 35/93
- Original match-weighted flips that remain after player balancing: 17/20
- Events with paired-player bootstrap CI width >=20pp: 90/93
- Events whose paired-player bootstrap CI includes zero: 81/93

Bootstrap intervals describe sampling instability among observed continuing players; they are not patch-effect confidence intervals.
