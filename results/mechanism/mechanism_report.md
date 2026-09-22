# Mechanism Analysis: Why Large Population Shifts Produce Small Win-Rate Distortion

This is an integrative mechanism layer over the frozen RQ1-RQ4 results. It is not a new research question and does not change any prior definition, sample, outcome, or estimator.

## Exact model-scale decomposition

For each event, the fitted M0 outcome surface defines:

`model_raw = E_post[m_post(X)] - E_pre[m_pre(X)]`

`standardized = E_pre[m_post(X)] - E_pre[m_pre(X)]`

`composition component C = E_post[m_post(X)] - E_pre[m_post(X)]`

Therefore `model_raw = standardized + C`. The largest absolute numerical identity error is 3.553e-15 pp.

The observed raw difference is retained separately. The median absolute observed-versus-model residual is 0.0000 pp and the maximum is 0.0008 pp. This residual is a model-fit diagnostic rather than a composition component.

## Composition component

- Median |C|: 0.723 pp
- Events with |C| >=1 pp: 36/97
- Events with |C| >=2 pp: 6/97
- Events with |C| >=5 pp: 0/97

## Shift and outcome sensitivity

Familiarity sensitivity is the average post-model predicted-probability contrast between the global P25 and P75 of log1p prior champion count. Rank and role sensitivity are event-specific max-minus-min average predicted-probability contrasts across categories observed in that event. All sensitivities are measured in win-probability percentage points.

- Familiarity: median shift 0.364; median sensitivity 1.80 pp; corr(shift × sensitivity, |C|) 0.010
- Rank: median shift 0.200; median sensitivity 2.67 pp; corr(shift × sensitivity, |C|) 0.029
- Role: median shift 0.200; median sensitivity 7.87 pp; corr(shift × sensitivity, |C|) 0.064

The shift × sensitivity products are conceptual diagnostics. They do not replace the exact g-computation component and are not interpreted as additive variable contributions.

## Interpretation

The formal decomposition confirms that the small RQ3 adjustment is a small model-scale composition component rather than an arithmetic mismatch between observed and modeled raw change. Familiarity has a small predicted-probability contrast, matching the proposed large-shift/weak-sensitivity mechanism. Rank sensitivity is also modest. Role has a larger potential max-minus-min contrast, but role shift × sensitivity is still almost unrelated to |C|. This shows that generic sensitivity and scalar distribution distance are not sufficient: the direction of the shift and its alignment with the joint outcome surface also matter.

Population instability and metric instability are distinct. Distribution shift propagates into aggregate metric distortion only when the shifting attributes are outcome-relevant and the distribution moves along that outcome gradient.

## Scope

This is a descriptive model-based measurement decomposition. It does not identify a causal champion-change effect. It uses the frozen M0 model, 97 higher-support events, 100-match familiarity window, and win outcome. A Shapley allocation across correlated familiarity, rank, and role blocks is not included because it requires a separate, prespecified joint-distribution replacement rule.

Model converged: True in 15 iterations.
