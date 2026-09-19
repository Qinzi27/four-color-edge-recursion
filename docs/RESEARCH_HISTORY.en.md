# Research history and evidence map

Checkpoint: 2026-09-19. The initiating recursive edge-side and mother-line naming idea belongs to **Qinzi27**. Formalization, implementation and evidence organization include AI assistance.

The [complete Chinese research history](RESEARCH_HISTORY-2026-09-19.md) records the stages, assumptions, denominators, successes, stalls and regressions. This is a reproducible exploratory project, **not a new proof of the Four-Color Theorem or a universally successful new coloring algorithm**. No originality certification is claimed.

## Reading the counts

A distinct geometry, a construction history, a prefix reference, a single-step repair and a verified certificate are different units. `underdetermined` means the rules did not choose a remaining alternative; `outside_scope` is an implementation restriction; a strategy conflict does not imply that the map needs a fifth color. Choosing the smallest available number is not the same as minimizing the total number of colors.

The current common corpus contains **7069 distinct geometries**: 6113 earlier inputs plus 961 later-seed inputs, with 5 overlaps. It represents **363 histories, 7678 prefix references and 302 static references**. The later-seed cohort has now been used for development and is no longer an unseen holdout.

| Frozen policy | Solved / 7069 | Conflicts | Scope rejections | All-prefix histories / 363 | Final maps / 363 | Static references / 302 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `tight-hall` | 6801 | 268 | 0 | 268 | 337 | 279 |
| `tight-hall-relations` | 7063 | 6 | 0 | 359 | 363 | 302 |
| Mother-line levels v1 | 6772 | 1 | 296 | 338 | 339 | 275 |
| Auxiliary levels v2 | 7068 | 1 | 0 | 362 | 363 | 302 |
| Stage-anchored initialization v3 | 7065 | 4 | 0 | 362 | 363 | 302 |
| Peer batches / ready sides v4 | 7060 | 9 | 0 | 358 | 362 | 301 |

Machine summaries: [Hall](../outputs/frontier-restart-summary-2026-09-19.json), [relations](../outputs/relation-frontier-full-summary-2026-09-19.json), [v1](../outputs/level-sides-full-summary-2026-09-19.json), [v2](../outputs/level-sides-peer-full-summary-2026-09-19.json), [v3](../outputs/staged-levels-full-summary-2026-09-19.json), [v4](../outputs/peer-batches-full-summary-2026-09-19.json). Archived baseline results are not necessarily rerun in every subsequent experiment.

Versions are not monotonically stronger: relations fixed 268 Hall failures but introduced 6 regressions; v2 fixed those 6 but introduced 1; v3 fixed that case but introduced 4; v4 fixed those 4 but introduced 9. Taking a union of successful outputs is not one algorithm passing the corpus.

## Stage-by-stage navigation

Dates identify repository checkpoints, not an exact ordering of parallel work on the same day. Each linked stage document gives implementation and reproduction details; the Chinese history also links its machine evidence directly.

| Date / stage | Added method or result | Outcome and limitation | Primary documentation |
| --- | --- | --- | --- |
| Sep 06–07: foundations | Darts, side identities, directed profiles, split history, group differences, exact boundary relations; restricted repair formulas and TTSP dynamic programming | Initial commit `c74510e`: Sep 06; validation checkpoint: Sep 07. Known frameworks and restricted proofs; bridges have zero difference; TTSP requires a decomposition | [Foundations in English](FOUNDATIONS.en.md), [Chinese foundations](FOUNDATIONS.md), [initial checks](../outputs/validation.json) |
| Sep 07: line-first consistency | Propagate side-orbit identities and forced names without arbitrary color choices | Consistency alone admits a five-symbol witness and does not prove a four-symbol bound | [Line-first rules](LINE_FIRST_RULES-2026-09-07.md), [results](../outputs/line-names-2026-09-07.json) |
| Sep 07: tree grammar | Study CRZ parsing rules and their group-difference interpretation | 197 tree shapes, 323175 tree/word checks, 9806 unordered tree pairs; finite tests, not the general theorem | [Grammar and literature scope](TREE_GRAMMAR_RULES-2026-09-07.md), [results](../outputs/tree-grammar-rules-2026-09-07-02.json) |
| Sep 08: anchored construction | Require meaningful endpoints/closure; retain one child name and check its complete boundary | 160 guillotine histories all stalled; 40 ring/bridge and 40 fan histories completed. Gallery: 8 complete, 2 blocked, 2 draft, 1 invalid | [Construction](CONSTRUCTION_RULES-2026-09-08.md), [results](../outputs/construction-validation-2026-09-08.json) |
| Sep 08: reverse-merge diagnostic | Bounded abstract graph search, separate from production coloring | 147 graphs and 478 normalized colorings; one coloring lacked the tested relaxed chain. No general geometric realization guarantee | [Stage log](WORKLOG-2026-09-08-CONSTRUCTION.md), [results](../outputs/reverse-merge-search-2026-09-08.json) |
| Sep 18: recoloring / strips / targets | Compare B/C component changes; prove a two-anchor strip rule and scheduling for a given target coloring | B/C union fixed 152 of 160 first-stall snapshots, composition another 7; final case required bounded search. Target scheduling does not find the target | [Repair log](WORKLOG-2026-09-18-RENAMING.md), [strip theorem](STRIP_CHAIN_THEOREM-2026-09-18.md), [target theorem](TARGET_RENAMING_THEORY-2026-09-18.md) |
| Sep 18: retained profiles / forests | Separate birth labels from current local names; extend the strip structure to common-anchor forests | 85 of 360 blocked runs had a certified one-step repair; continuation gained 228 steps but all 85 stalled again | [Profiles](RETAINED_PROFILE_SYNTHESIS-2026-09-18.md), [continuation](ANCHOR_FOREST_CONTINUATION-2026-09-18.md) |
| Sep 18: first three priorities | Boundary / layer / constraint priorities, each in both directions | 252 maps, six schedules; 579 of 1512 outputs used more than four names. This was a control, not a faithful final specification of the initiating idea | [Priority rules](PRIORITY_RULES-2026-09-18.md), [point-to-point clarification](POINT_TO_POINT_MODEL-2026-09-18.md) |
| Sep 18: whole mother-lines / weights | Keep identity through T/X junctions; compare connection count, naming constraints and outer depth | Representation passed 255 maps; 7650 weighted runs showed order sensitivity. Best single schedule solved 183/255 | [Whole lines](WHOLE_LINE_VALIDATION-2026-09-18.md), [weights](WEIGHTED_LINES-2026-09-18.md) |
| Sep 18: joint / binary relations | Candidate reservation and path consistency | 15300 joint runs; strict 2/255 solved, safe symmetry 7/255. Binary filtering improved information but did not increase these totals; 60 further maps remained undetermined | [Joint rules](JOINT_LINES-2026-09-18.md), [comparison](METHOD_COMPARISON-2026-09-18.md) |
| Sep 18: local marks A/B/C/D/E | Current side name plus position; direct choice, one-neighbor repair and bounded two-name repair | Original nine one-step tests: 8 successes, 1 stop. C must restart from 2–3–2; E internally reuses 1. Corrected starts are not the old frozen counterexamples | [Local marks](LOCAL_SIDE_MARKS-2026-09-18.md), [reuse and parity](LOCAL_REUSE_PARITY-2026-09-18.md) |
| Sep 18: current rules D1–D4 | Complete current boundaries and safe shared-interface release | On 323 histories, D1–D4 with budget 3: 18 complete, 219 blocked, 86 outside scope; budget 32: 95/142/86 | [Current rules](CURRENT_NAMING_RULES-2026-09-18.md), [summary](../outputs/current-names-summary-2026-09-18.json) |
| Sep 18: global restart | Discard old colors and rebuild each accumulated prefix independently | 6113 distinct maps; four schedules solved 5330, 5641, 5377 and 5638. Closed-support fixed 9 and regressed 12 against interval scheduling | [Restart](GLOBAL_RESTART-2026-09-18.md), [summary](../outputs/global-restart-summary-2026-09-18-v2.json) |
| Sep 19: frontier / Hall | Dynamic urgency and candidate reservation only on actual cliques | Common corpus grew to 7069; Hall solved 6801 but regressed 135 earlier-cohort baseline successes | [Frontier rules](FRONTIER_RULES-2026-09-19.md), [regression audit](FRONTIER_AUDIT-2026-09-19.md), [later-seed audit](FRONTIER_HELDOUT_AUDIT-2026-09-19.md) |
| Sep 19: relation-frontier | Integrate binary relations with Hall and deterministic active naming | Fixed 307-case diagnostic passed; full corpus still had 6 new regressions | [Diagnostic stage](RELATION_FRONTIER-2026-09-19.md), [full run](RELATION_FRONTIER_FULL-2026-09-19.md) |
| Sep 19: minimum names / generations | Audit existing choices, then analyze whole-line ancestry | All 39301 active choices were already minimum. Six failures plus 36 controls showed levels were informative but not sufficient | [Minimum audit](MINIMUM_NAME_AUDIT-2026-09-19.md), [generations](LINE_GENERATIONS-2026-09-19.md) |
| Sep 19: levels v1/v2 | Geometry-derived endpoint support; later make unknown levels a scheduling group rather than a hard rejection | Six original failures fixed. Removing the gate recovered 296 scope rejections; one blue-box regression remained | [Six cases](LEVEL_SIDE_RULES-2026-09-19.md), [full v1/v2 results](LEVEL_SIDES_FULL-2026-09-19.md) |
| Sep 19: initialization v3 | One safely normalized interior anchor tied to the first eligible mother-line | Earlier 6113 inputs all solved; four later-cohort prefixes regressed | [Specification](STAGED_LEVEL_RULES-2026-09-19.md), [results](STAGED_LEVEL_RESULTS-2026-09-19.md), [failure dossier](STAGED_LEVEL_CONFLICTS-2026-09-19.md) |
| Sep 19: peer batches v4 | Activate equal-stage mother-lines together and prioritize geometrically ready final sides | Proved the readiness/partition lemma; 40 known diagnostics passed, but full run produced nine new regressions | [Specification](PEER_BATCH_RULES-2026-09-19.md), [full results](PEER_BATCH_RESULTS-2026-09-19.md) |
| Sep 19: implicit inequality | Nine distinct side IDs and nineteen real adjacency constraints imply two specified sides have different names | Proved local lemma; excludes the recorded fatal candidate in 3/9 failures. Not integrated into v4 and not three repaired full maps | [Lemma](IMPLICIT_INEQUALITY-2026-09-19.md), [coverage](../outputs/peer-batches-implicit-inequality-coverage-2026-09-19.json) |

Parallel work: the [probabilistic study](PROBABILITY_AI_REVIEW-2026-09-18.md) used 216 observations on six fixed small topologies, not a trained AI or general coloring benchmark. The [mathematical synthesis](MATHEMATICAL_METHOD-2026-09-19.md) and [related-work update](RELATED_WORK_UPDATE-2026-09-19.md) distinguish known equivalences, precise local results, unresolved claims and the depth of source reading. This historical compilation adds no new literature search.

## Latest negative results remain first-class evidence

All nine v4 conflicts are retained: `20260946` at steps 18/19/20; `20260950` at 19; `20260968` at 24; `20261041` at 21/22; `20260936` at 21/22. The first non-extendible commitment is the second active choice in seven cases and the fifth in the last two. These are failures of the specified strategy, with valid earlier-version witnesses, not failures of four-colorability. See the [full diagnostic](../outputs/peer-batches-failure-diagnosis-2026-09-19.json) and [smallest new conflict, blank image](figures/peer-batches-2026-09-19/least-new-conflict-blank.png).

The nine-side lemma covers only the three `20260946` prefixes. Its [implementation](../fourcolor/implicit_inequality.py) checks an injective graph-pattern embedding; the independent `4^9` color enumeration is confined to [tests](../tests/test_implicit_inequality.py). It was not used to rescue v4 or revise its score.

The unresolved distinction is between a sound necessary candidate set `D_A(F)` and the actually extendible set `E_A(F)`. Sound filtering gives `E_A(F) ⊆ D_A(F)`, not equality. Neither level nor geometric readiness proves that `min D_A(F)` is extendible.

## Reproduction and audit boundary

Start with the [single-map entry point](../scripts/name_peer_batch_map.py), [example input](../examples/peer-batch-five-lines.json), [v4 full runner](../scripts/validate_peer_batches_full.py) and [independent audit](../scripts/audit_peer_batches_full.py). Use new output paths and the source revision matching the archived hashes. The website demonstration and research command-line policies are separate; publishing documentation does not silently replace the website solver.

See the [complete reproduction guide](REPRODUCING_RESEARCH.md) for version boundaries. Historical scripts with the same filename may have been revised; follow each runner/auditor's declared source checks. The publication index binds v4's 30 frozen sources and archived evidence bytes, not unchanged original sources for every historical version or a fresh rerun of all historical experiments.

The [v4 report](../outputs/peer-batches-full-2026-09-19.json.gz) has SHA-256 `fb004374e06ee0ace87328a8559e108b23e0e9b71663e1a35158738a5e3ad543`. The subsequent [audit](../outputs/peer-batches-full-audit-2026-09-19.json) re-exported every geometry, checked all 7060 stored successful solutions, replayed 49 detailed failure/diagnostic certificates, and freshly reran a fixed union of 55 cases. It also bound 283 result parts and 30 frozen source files. **That audit was not a second complete solve of all 7069 maps.**

Older stage statements such as “not uploaded in this round” describe their historical checkpoint. Preserve them, the unsuccessful candidates and the corrected-start distinctions. A future algorithm revision must be separately frozen and retested on previous successes as well as failures, without combining per-map winners from different rules.
