# Analysis Plan v0.1 — Foundational Lock

**Project:** Who Plays Matters: Player Composition in Evaluating League of Legends Updates  
**Chinese title:** 谁在玩，改变了我们如何评价版本：基于玩家经验构成的 LoL 版本效果分析  
**Status:** Foundational decisions frozen; estimators and inferential models remain open  
**Freeze date:** 2026-09-20  
**Region:** North America (`NA1`; regional routing `AMERICAS`)

## 1. Purpose of this document

This document freezes the study's foundational definitions before outcome analysis. It records the research scope, cohort, data cutoff, event definition, familiarity window, analysis units, and core comparison targets. It is not a preregistration and does not yet freeze the final estimator, standardization reference distribution, uncertainty procedure, or minimum event sample size.

The familiarity decision was made from exposure-count support and label-stability diagnostics, without inspecting performance outcomes for official changed-champion events.

## 2. Research objective

The study asks whether changes in who plays a champion affect how League of Legends patch effects are described.

### Frozen research questions

1. **Composition change:** Around patches that modify a champion, how does the observable prior-experience composition of that champion's users change?
2. **Evaluation sensitivity:** Do aggregate performance changes, experience-composition-standardized changes, and changes among continuing users differ in magnitude or direction?
3. **Diagnostic value:** Are discrepancies concentrated in events with stronger user influx or larger experience-composition shifts, and do these patterns recur across patches?

The title and questions do not presume that composition adjustment will materially change every patch evaluation.

## 3. Scope and non-goals

### Included

- Riot Games official API data.
- One platform: `NA1`.
- Ranked Solo/Duo only: `queueId = 420`.
- Standard Summoner's Rift matches.
- Champion balance changes identified from Riot's official patch notes.
- Player-level match histories used to measure observable prior champion experience.
- Interpretable stratification, standardization, decomposition, and sensitivity analysis.

### Excluded from the first study

- ARAM, Arena, normal queues, Flex queue, remakes or other non-target matches.
- Item-only, rune-only, system-only, and game-mode-only changes.
- New-champion introduction text unless the champion also has an eligible balance-change heading.
- Bugfix-only champion mentions.
- Churn, disengagement, recovery-state modeling, and single-match outcome prediction.
- Claims that observational estimates identify the causal effect of a patch change.
- Complex predictive models unless later required by a specific robustness question.

## 4. Frozen cohort and data snapshot

### Sampling frame

- Fixed cohort size: **500 active ranked players**.
- Rank strata: **Gold, Platinum, Emerald, Diamond, Master+**.
- Target allocation: **100 players per rank stratum**.
- Primary-role allocation within each rank: **20 each for Top, Jungle, Middle, Bottom, and Utility**.
- Realized allocation: all **25 rank × role cells contain 20/20 players with history**.
- The same anonymized players are retained across patches; players are not resampled separately for each patch.
- Cohort identifier: `aec595ceb0297a53`.
- Fixed history cutoff: `2026-09-08T15:17:49+00:00` UTC.
- Maximum retrieved history: 500 ranked Solo/Duo matches per player.

### Observed snapshot

- Players with match history: **500/500**.
- Match rows: **141,738**.
- Mean matches per player: **283.48**.
- Median matches per player: **276**.
- Players with at least 100 observed matches: **396**.
- Median observed history span: **381.5 days**.
- Median number of observed patches per player: **14**.
- Players covering at least 3 patches: **491**.
- Players covering at least 5 patches: **474**.

### Snapshot files and SHA-256

| File | SHA-256 |
| --- | --- |
| `data/processed/riot_feasibility_matches.csv` | `6822535C1982093788125095AE5A1762F983A05B14F1C4258BA097717552E75F` |
| Original private match-summary snapshot (not distributed) | `1CF72B8DC5B981F2EE94B1A2AA3429DE4ABCF217C85945FF6B8EF4E8B51FD995` |
| `data/official_changed_champion_patch_table.csv` | `625C993E55E38C7430C89EA525C754D9D3A093FDF88ED96D18A07ABA7E950EC0` |

Any later refresh or supplemental sample must be stored as a new data version and must not silently replace this snapshot.

## 5. Patch and event definitions

- API patch is parsed from `gameVersion` as `major.minor`.
- Patch release dates are not inferred from match data.
- A study event is a **champion × patch** pair in the official changed-champion table.
- The official table currently contains **258 eligible champion × patch events** across API patches `16.1`–`16.17`, corresponding to Riot public patch labels `26.1`–`26.17`.
- The `16.x` to `26.x` mapping must remain explicit in all joins and reporting.
- Eligible changes come from named champion headings in the first main Summoner's Rift `Champions` section of the official patch notes.
- All eligible events are retained in the event inventory, including events with zero or low observed support. Insufficiently supported events may be excluded from a particular estimator but must remain visible in coverage reporting.

## 6. Analysis units

The project uses three nested units:

1. **Match-level observation:** one focal player's participation in one eligible ranked match.
2. **Player × champion × patch unit:** a player's observations for a champion within a patch, with familiarity computed strictly from matches preceding the focal observation or event boundary.
3. **Champion × patch event:** the main reporting and comparison unit for patch evaluation.

Repeated matches from the same player are not treated as independent observations. The final uncertainty method must account for player-level dependence and, where applicable, event-level heterogeneity.

## 7. Familiarity definition

### Frozen primary definition

- Primary familiarity window: the player's **100 prior observed ranked Solo/Duo matches**.
- Sensitivity window: **50 prior observed matches**.
- The 20-match window is rejected as the primary definition because observed-new classifications were unstable relative to longer histories.
- Primary familiarity measure: **prior matches played on the focal champion**, retained as a continuous or ordinal exposure count.
- Preferred descriptive grouping:
  - `observed_new`: 0 prior focal-champion matches;
  - `limited`: 1–4 prior focal-champion matches;
  - `established`: 5 or more prior focal-champion matches.
- Optional four-level summaries may split established users into 5–14 and 15+, but only where event support is adequate.

“Observed new” means no use of the champion within the specified observed window. It does not mean first-ever use and must never be described as lifetime novelty or account-level mastery.

### History completeness

Primary familiarity analyses require a complete 100-match prior window for the relevant player-event observation. Observations without that history may contribute to descriptive cohort coverage but not to the primary 100-match familiarity comparison. The 50-match analysis applies the corresponding 50-match completeness rule.

## 8. Core comparison targets

The study will distinguish three estimands because they answer different questions:

1. **Observed-user estimate:** performance among the users who actually played the champion in each comparison period.
2. **Composition-standardized estimate:** performance after aligning the observable familiarity distribution to a prespecified reference distribution.
3. **Continuing-user estimate:** performance among players observed using the same champion on both sides of the event definition.

No estimand is designated as the uniquely correct patch effect. Standardization does not create causal identification, and the continuing-user estimand describes a selected subpopulation.

## 9. Outcomes and covariates

### Candidate primary outcome — not yet frozen

- Win indicator, aggregated or modeled at an analysis level that respects repeated-player dependence.

### Candidate secondary outcomes — not yet frozen

- Kills, deaths, assists, and derived KDA measures.
- Damage dealt to champions.
- Gold earned.
- Vision score.
- Item and summoner-spell choices as descriptive behavioral context.

### Available adjustment and stratification variables

- Target rank stratum.
- Primary role and match-level position.
- Champion.
- Patch.
- Prior focal-champion matches.
- Observed match-history depth.
- Calendar/match time.

Variables such as true lifetime mastery, MMR, exact contemporaneous rank, premade-party status, lane-opponent strength, and unobserved account history are not established as available and must not be implied.

## 10. Coverage and sparse-event policy

The 500-player cohort is the broad, composition-balanced sampling frame. Current coverage diagnostics show:

- 258 official events across supported patches.
- Median experience-eligible users per event: **5**.
- Events with at least 10 eligible users: **64**.
- Events with at least 20 eligible users: **11**.
- Events with zero eligible users: **30**.

These results freeze the need for a **two-frame design**:

1. The fixed 500-player rank × role cohort estimates broad player-composition patterns.
2. A separately versioned event-enriched supplemental cohort may be collected for sparse changed-champion events.

Supplemental sampling must record selection rules and inclusion probabilities. It must not be merged into population-composition estimates without an explicit weighting or transport procedure. Exact event eligibility thresholds remain open pending estimator and precision design.

## 11. Data quality and exclusions

- Match rows must have the focal participant and required identifiers needed for the planned analysis.
- Records outside queue 420 or standard Summoner's Rift are excluded.
- Eight recorded repair failures do not remove any player from the cohort: seven records were filtered and one match-detail request ended with `RemoteDisconnected`.
- Missing or failed match details are not interpreted as zero outcomes.
- Duplicate `anonymized_player_id × matchId` rows must be removed or flagged before construction of the analysis dataset.
- Any additional exclusions introduced during processing must be counted and reported by reason, player, patch, and champion where disclosure is safe.

## 12. Required sensitivity and validity checks

The following checks are committed at the design level; their exact implementation remains to be specified:

- Repeat familiarity analysis with the 50-match window.
- Compare continuous/ordinal familiarity results with the `0 / 1–4 / 5+` descriptive grouping.
- Report event coverage and uncertainty rather than retaining only statistically favorable events.
- Examine heterogeneity by rank and role without treating the balanced cohort as the natural NA1 population distribution.
- Assess the influence of high-volume players and repeated matches.
- Separate events with adequate support from sparse or zero-support events.
- Report null, weak, inconsistent, and direction-reversing findings.
- Distinguish composition differences from patch severity and other contemporaneous patch changes in interpretation.

## 13. Claims this design can and cannot support

### Potentially supportable

- Observable user-experience composition changes around official champion updates.
- Differences among observed-user, standardized, and continuing-user descriptions.
- Conditions under which patch evaluation is more sensitive to user composition within this sampling design.

### Not supportable without stronger design or additional data

- The causal effect of a champion balance change.
- Lifetime champion mastery or true first-time champion use.
- Population prevalence for all NA1 ranked players without weighting to an appropriate target population.
- A claim that composition adjustment is always necessary or always changes conclusions.
- Direct comparison of patch severity based only on the number of patch-note changes.

## 14. Decisions still open

The following must be decided and appended before confirmatory outcome analysis:

1. Exact pre/post event windows and treatment of patch-transition dates.
2. Primary outcome and secondary-outcome hierarchy.
3. Reference distribution for familiarity standardization.
4. Continuing-user eligibility rule and minimum matches on each side.
5. Minimum users and matches required for event-level estimation.
6. Statistical estimator and player/event dependence structure.
7. Confidence interval or uncertainty procedure.
8. Multiple-comparison policy, if event-specific inference is reported.
9. Patch-severity representation and handling of simultaneous system changes.
10. Event-enriched sampling targets, stopping rule, and weighting procedure.
11. Missing-data and influential-observation diagnostics.
12. Main table/figure specifications and robustness hierarchy.

These choices must be made without selecting definitions because they produce a preferred substantive result.

## 15. Change control

- Changes to a frozen item require a dated amendment describing the old rule, new rule, reason, and whether outcomes had been inspected.
- Exploratory alternatives may be run, but they must be labeled exploratory and cannot silently replace the primary definition.
- New data pulls receive a new cohort/data version, cutoff, row count, and hashes.
- API keys, PUUIDs, raw cache, and private cohort identifiers beyond the anonymized study IDs must not appear in public artifacts.

## 16. Evidence status

This document fixes definitions and an evidence plan. It contains no estimated patch-performance result and makes no claim that composition effects are present. All outcome estimates, uncertainty intervals, robustness results, and substantive conclusions remain to be generated from the locked or explicitly amended protocol.

## Appendix A. RQ1 implementation lock

**Lock date:** 2026-09-21  
**Question:** Before and after an official champion update, does the composition of players using that champion change?

RQ1 is composition-only. Win, KDA, damage, gold, vision, items, and other performance outcomes are excluded from the RQ1 build and interpretation.

### Period definition

- `post` is the official changed-champion event patch.
- `pre` is the validated immediately preceding API patch.
- For `16.2`–`16.17`, the predecessor is the same major version with minor version minus one.
- The validated season-boundary mapping is `16.1 → 15.24`.
- The pipeline must never substitute the greatest earlier observed patch when the true predecessor is missing.
- All 258 current events have their true predecessor represented in the match data; zero cross-patch fallbacks were used.

### Participation denominators

For each champion × patch event, players are classified as `pre_only`, `both`, or `post_only`. The following measures are retained with explicit denominators:

- `pre_only_among_union = n_pre_only / (n_pre_only + n_both + n_post_only)`
- `both_among_union = n_both / (n_pre_only + n_both + n_post_only)`
- `post_only_among_union = n_post_only / (n_pre_only + n_both + n_post_only)`
- `pre_only_among_pre = n_pre_only / n_pre_users`
- `post_only_among_post = n_post_only / n_post_users`
- `continuation_rate = n_both / n_pre_users`

The labels `entrant`, `continuer`, and `leaver` are not used in RQ1.

### Analysis views

- **Overall coverage:** retain all official events and report data availability. There are currently 229 events with at least one observed user in both pre and post.
- **Higher-support view:** the primary RQ1 descriptive view requires `n_pre_users >= 10` and `n_post_users >= 10`. There are currently 97 such events.
- **Sensitivity views:** repeat summaries at thresholds of at least 5 and at least 20 users in both periods.
- Events below the higher-support threshold remain in the public coverage table and are not treated as zero-shift events.

### RQ1 measures

- Participation: pre-only, both, and post-only counts and denominator-explicit shares.
- Familiarity: mean, median, P25, P75, and `0 / 1–4 / 5+` shares among period-specific 100-match-history-eligible users.
- Rank composition: pre/post shares across the five frozen rank strata and Total Variation Distance.
- Role composition: pre/post shares across the five frozen primary roles and Total Variation Distance.
- Support diagnostic: `min(n_pre_users, n_post_users)` against rank TVD, role TVD, and absolute observed-new-share change.

RQ1 remains descriptive. No p-value threshold, causal interpretation, or performance-conditioned selection is part of this phase.

## Appendix B. RQ3 result and robustness lock

**Lock date:** 2026-09-21  
**Question:** Do observed player-composition changes materially alter pre/post win-rate comparisons around official champion updates?

### Primary estimands and analysis set

- The main view contains the 97 RQ1 higher-support events (`n_pre_users >= 10` and `n_post_users >= 10`).
- The primary outcome is match win.
- Primary familiarity is continuous `log1p(prior_champion_count_100)`; the `0 / 1–4 / 5+` groups are descriptive only.
- `Raw` is the post-minus-pre win-rate difference in the experience-eligible analysis sample.
- `Continuing-user` restricts to players observed using the focal champion in both periods and describes a selected subpopulation.
- `Composition-standardized` uses regression standardization to the pre-period covariate distribution. It is a composition-standardized difference, not a true or causal patch effect.

### Frozen main result

For the baseline estimator, the median absolute difference between composition-standardized and raw win-rate change is **0.723 percentage points**. Of 97 events, 36 differ by at least 1 pp, 6 by at least 2 pp, none by at least 5 pp, and 2 change direction. The event-level experience gap has essentially no monotonic relationship with adjustment magnitude (Spearman **0.068**).

The substantive interpretation is:

> Player composition changes substantially around champion updates, and newly observed users are systematically less experienced with the focal champion. However, these observable composition shifts have only limited impact on aggregate win-rate changes.

The project headline is:

> **Who plays changes a lot—but, for win rate, it matters less than expected.**

### Prespecified estimator robustness

The following variants are retained as robustness checks rather than searched for a preferred result:

| Variant | Purpose | Median absolute adjustment (pp) | Events >=2pp | Events >=5pp | Direction flips |
| --- | --- | ---: | ---: | ---: | ---: |
| M0 | Baseline pooled outcome regression | 0.723 | 6 | 0 | 2 |
| M1 | Post interactions with familiarity, rank, and role | 0.685 | 10 | 0 | 3 |
| M2 | Piecewise-linear familiarity spline | 0.719 | 6 | 0 | 2 |
| M3 | Player-period equal weighting | 0.800 | 15 | 1 | 2 |
| M4 | Ridge-penalized outcome regression | 1.649 | 41 | 18 | 3 |
| M5 | Inverse-odds weighting to pre composition | 0.541 | 14 | 0 | 3 |
| S1 | 50-match familiarity window | 0.815 | 6 | 0 | 2 |

M4 is a regularization-sensitivity analysis. Ridge also shrinks event-specific post-update contrasts, so its larger raw-to-adjusted difference must not be interpreted as direct evidence of a larger composition effect. M0, M1, M2, M3, M5, and S1 converge on a typical adjustment below 1 pp, few direction reversals, and near-zero association with the RQ2 experience gap.

### Mechanism diagnostic

Composition can change an aggregate outcome only when the changing covariate also predicts that outcome. In M0, a one-standard-deviation increase in log familiarity has an odds ratio of approximately **1.043** for win. The observed familiarity composition shifts are large, but their relationship with win is weak in this dataset. This supports the interpretation `composition shift != outcome distortion` for win rate under the observed adjustment set.

### Continuing-user status

Continuing-user estimates are supplementary diagnostics, not a headline finding. Only 93 of 97 events have paired eligible continuing users; median `n_both` is 5 and median match-weight effective sample size is 2.79. The paired-player bootstrap interval width is at least 20 pp for 90/93 events, has a median width of 67.4 pp, and includes zero for 81/93 events. Apparent raw-versus-continuing direction changes are therefore treated as highly unstable under sparse repeated-user support.

### Main-text and supplementary presentation lock

The main text retains three result tables: dataset and coverage; RQ1/RQ2 composition findings; and RQ3 estimator robustness. It retains four figures: study pipeline; higher-support composition changes; post-only versus continuing familiarity; and raw versus composition-standardized win-rate change. The experience-gap-versus-adjustment and continuing-user diagnostics move to supplementary material.

No result may be described as a causal patch effect. The final claim is limited to win rate, the measured familiarity/rank/role covariates, the fixed 500-player sample, and the frozen event/window definitions.
