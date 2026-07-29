# Semantic IR Diagnostic Report

Run: `run-20260727Tsemantic-ir-diagnostic`

Scope: hand-authored IR only; no model extraction; no benchmark expansion.

## Metrics

- Passed: 5/5
- Abstentions: 1
- Fallback allowed: 0
- Closure complete: 4

## Cases

### led_manage_vs_led_to_cause: PASS

A project-leadership query must match lead/manage and ignore causal led-to.

- Category: `predicate_sense`
- Matched units: `['l1-led-migration']`
- Evidence IDs: `['E-led-migration']`
- Abstained: `False`
- Reason: `matched units without explicit closure`

### led_to_cause_match: PASS

A causal query must match led-to/cause and ignore lead/manage.

- Category: `predicate_sense`
- Matched units: `['l1-feedback-led-to-change']`
- Evidence IDs: `['E-led-to-change']`
- Abstained: `False`
- Reason: `matched units without explicit closure`

### feedback_causal_answerability_missing_link: PASS

Feedback and UI/UX change mentions are insufficient without a causal link unit.

- Category: `causal_answerability`
- Matched units: `['l1-feedback-observation', 'l1-ui-change']`
- Evidence IDs: `[]`
- Abstained: `True`
- Reason: `missing causal answerability roles`

### multi_session_evidence_closure: PASS

A cross-session project query must return the complete evidence set.

- Category: `evidence_closure`
- Matched units: `['l1-led-migration', 'l1-leading-dashboard', 'l2-projects-led']`
- Evidence IDs: `['E-led-migration', 'E-leading-dashboard']`
- Abstained: `False`
- Reason: `closure complete`

### current_preference_supersession: PASS

Current preference queries must ignore superseded preference records.

- Category: `lifecycle`
- Matched units: `['l1-pref-new']`
- Evidence IDs: `['E-pref-new']`
- Abstained: `False`
- Reason: `matched units without explicit closure`

## Interpretation

The diagnostic suite confirms that the AMR-style semantic IR can represent predicate sense, closure completeness, and lifecycle constraints without dense retrieval.
It specifically separates `led/manage` from `led-to/cause`, blocks feedback causal answerability when the causal link is missing, requires complete multi-session evidence, and ignores superseded preferences.

This does not prove model extraction quality. The next step is to map real slice items into this IR and compare runner behavior against `symbolic_fallback_answerability_v2` before adding model-based extraction.
