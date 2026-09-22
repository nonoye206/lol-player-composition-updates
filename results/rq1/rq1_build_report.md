# RQ1 composition-only build report

- Official champion-patch events: 258
- Player-period rows: 5,227
- Events with observed users in both periods: 229
- Events with 100-match-eligible users in both periods: 220
- Higher-support events (pre and post users >=10): 97
- Events missing the true immediately preceding patch in match data: 0
- Cross-patch fallbacks used: 0
- Duplicate player-match rows removed: 0

No win, KDA, damage, gold, vision, item, or other performance outcome was read or analyzed.

## Descriptive distributions

| Metric | Events | Median | P25 | P75 |
| --- | ---: | ---: | ---: | ---: |
| Post-only among union | 232 | 0.375 | 0.29316888045540795 | 0.5 |
| Observed-new change | 220 | 0.0 | -16.666666666666668 | 16.666666666666668 |
| Rank TVD | 229 | 0.26666666666666666 | 0.17222222222222222 | 0.38888888888888884 |
| Role TVD | 229 | 0.26573426573426573 | 0.18181818181818182 | 0.4 |

## Coverage-stratified diagnostics

| Minimum pre and post users | Events | Median post-only share | Median absolute observed-new change (pp) | Median rank TVD | Median role TVD |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 229 | 0.375 | 16.666666666666668 | 0.26666666666666666 | 0.26573426573426573 |
| 5 | 172 | 0.36666666666666664 | 16.614420062695924 | 0.23273809523809524 | 0.2236111111111111 |
| 10 | 97 | 0.3548387096774194 | 12.82051282051282 | 0.2 | 0.19999999999999996 |
| 20 | 17 | 0.35135135135135137 | 15.818181818181817 | 0.15 | 0.1617391304347826 |

These are coverage and effect-size descriptions. No significance tests or causal claims are made. Extreme values from sparse events must not be treated as stable estimates.
