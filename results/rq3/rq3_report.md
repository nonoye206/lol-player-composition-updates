# RQ3 provisional composition-standardized performance report

The adjusted quantity is a composition-standardized difference, not a true or causal patch effect.

- Higher-support events: 97
- Match-analysis rows across all events: 18,088
- Experience-eligible match rows in the primary model: 8,502
- Model converged: True in 15 iterations
- Event-period cells with all wins or all losses: 2/194
- Minimum eligible users in an event-period cell: 3
- Minimum eligible matches in an event-period cell: 4
- Median absolute standardized-versus-raw difference: 0.72 pp
- Events with adjustment >=1 pp: 36/97
- Events with adjustment >=2 pp: 6/97
- Events with adjustment >=5 pp: 0/97
- Raw versus standardized direction reversals: 2/97
- Raw versus continuing-user direction reversals: 20/97
- Experience-gap versus adjustment Pearson correlation: 0.0007731284426106375
- Experience-gap versus adjustment Spearman correlation: 0.06766434901972487

The first-pass model is provisional. It uses continuous log1p familiarity; the 0 / 1–4 / 5+ groups are retained only for interpretation.
Two event-period cells have complete outcome separation, producing near-boundary fitted probabilities; this is recorded in the diagnostics and is one reason the estimator is not yet locked.
No p-values, confidence intervals, bootstrap selection, or significance-based event filtering were run.
