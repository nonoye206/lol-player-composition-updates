# RQ4 exploratory boundary-condition report

RQ4 asks when observable player composition materially changes raw win-rate measurement. It reuses the frozen 97-event RQ3 analysis set and M0 estimates. No new data, estimator, outcome, or event selection was introduced.

## Definitions

- Outcome: `abs(standardized_delta_pp - raw_delta_pp)`.
- Post-only share uses the pre/post user union denominator.
- Familiarity Wasserstein compares post-only with continuing users on log1p prior champion count, matching the frozen RQ3 composition-gap diagnostic.
- Event support is the minimum number of experience-eligible users across pre and post.
- Player-match ESS is the minimum pre/post ESS and is used as a separate support diagnostic.
- Smooth lines are descriptive Gaussian-kernel trends. They are not inferential fits.

## Bivariate associations

- Post-only share among pre/post union: Pearson 0.127; Spearman 0.123
- Absolute observed-new share change (pp): Pearson -0.017; Spearman -0.095
- Post-only vs continuing familiarity Wasserstein (log1p): Pearson 0.001; Spearman 0.068
- Rank TVD: Pearson 0.061; Spearman 0.081
- Role TVD: Pearson 0.032; Spearman 0.030
- Minimum eligible users across periods: Pearson -0.283; Spearman -0.330
- Log1p minimum eligible users across periods: Pearson -0.356; Spearman -0.330
- Minimum player-match ESS across periods: Pearson -0.200; Spearman -0.211

There are 6/97 events with an adjustment of at least 2 pp.

The six >=2 pp events have median eligible support 6.0, compared with 9.0 among the remaining events. Their median minimum player-match ESS is 4.11, compared with 4.61. Rank and role TVD are somewhat higher in the six events, but their bivariate associations across all 97 events remain weak. No turnover, familiarity, rank, or role pattern consistently separates the large-adjustment events.

## Largest adjustments

- Tristana 16.1: 4.67 pp; rank TVD 0.18, role TVD 0.18, support 4, ESS 2.29
- Xayah 16.1: 4.24 pp; rank TVD 0.14, role TVD 0.30, support 5, ESS 3.77
- Twitch 16.4: 3.43 pp; rank TVD 0.27, role TVD 0.19, support 5, ESS 2.07
- Jax 16.1: 2.47 pp; rank TVD 0.26, role TVD 0.32, support 13, ESS 4.72
- Varus 16.3: 2.24 pp; rank TVD 0.27, role TVD 0.36, support 7, ESS 4.44
- Jayce 16.14: 2.23 pp; rank TVD 0.24, role TVD 0.19, support 9, ESS 6.94

The complete ranked top 15 is in `rq4_top_adjustment_events.csv`.

## Exploratory multivariable model

The OLS model uses standardized predictors and the six prespecified terms. Coefficients are descriptive associations with adjustment magnitude, not causal effects and not a variable-selection exercise.

- post_only_share_union: 0.059 pp per 1 SD (SE 0.079)
- abs_delta_observed_new_pp: -0.135 pp per 1 SD (SE 0.079)
- familiarity_wasserstein_log1p: -0.021 pp per 1 SD (SE 0.077)
- rank_tvd: -0.032 pp per 1 SD (SE 0.080)
- role_tvd: -0.030 pp per 1 SD (SE 0.081)
- log1p_event_support: -0.251 pp per 1 SD (SE 0.090)

- Model R-squared: 0.118
- Adjusted R-squared: 0.057
- Complete-case events: 93/97. Four events lack the post-only-versus-continuing familiarity Wasserstein because one comparison group is absent.

No p-value threshold is used. A coefficient describes the adjusted change in absolute adjustment, in percentage points, associated with a one-standard-deviation difference in that predictor within the 93 complete-case events.

## Boundary-condition interpretation

The composition indicators do not reliably identify events whose raw win-rate estimate changes materially after adjustment. Lower support shows the clearest association with larger adjustments, which is more consistent with sparse-event sensitivity than with a repeatable substantive composition boundary. The evidence therefore supports the project-level conclusion that composition changes are common and structured, but user turnover, familiarity shift, rank shift, and role shift do not reliably predict meaningful distortion in aggregate win-rate estimates in this sample.
