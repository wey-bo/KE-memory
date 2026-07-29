# Typed Extractor V2 L2 Dev Proposer Contract V7

You are a fresh proposer with no inherited conversation history.

## Allowed Input

Read only the frozen `public-l2.json` supplied by the dispatch request. Do not
read authority, gold, source cases, manifests, prior proposals, reports,
scorer code/output, historical error analysis, or any other file.

## Output Contract

Return one JSON object with exactly these top-level keys:

`schema_version`, `dataset_id`, `run_id`, `proposer_id`, `proposer_version`,
`case_count`, `proposals`.

`schema_version` is exactly `typed-extractor-l2-proposals-v1`. Copy dataset,
run and proposer metadata exactly. Emit one proposal per public case using
exactly:

`case_id`, `candidate_ref`, `decision`, `confidence`, `typed_candidate`,
`reason_code`.

Decision is `emit_l2` only when the public typed L1 support pack completely
supports a closed L2 candidate. Otherwise use `abstain`. Abstention requires
`typed_candidate: null`. Confidence is from 0 through 1. Reason code is a
concise snake_case description based only on public input.

## Exact Typed L2 Candidate

For `emit_l2`, use every key below and no others:

```json
{
  "kind": "task",
  "summary": "evidence-backed cross-turn summary",
  "supporting_l1_refs": ["support-ref-copied-from-public"],
  "structured_claims": [
    {
      "claim_ref": "claim-01",
      "predicate": {
        "surface": "public predicate surface",
        "sense": "catalog predicate sense",
        "canonical_operator": "catalog operator"
      },
      "local_entities": [
        {"local_entity_id": "entity-01", "surface": "publicly supported surface"}
      ],
      "roles": [
        {"role": "catalog role", "role_name": "catalog display name", "local_entity_id": "entity-01"}
      ],
      "modality": "actual",
      "polarity": "positive",
      "time": {"event_time": null, "valid_time": null},
      "supporting_l1_refs": ["support-ref-copied-from-public"]
    }
  ],
  "abstraction": {
    "method": "coreference_resolution",
    "basis": "concise public-only basis"
  },
  "closure": {
    "pattern": "multi_evidence_set",
    "required_support_refs": ["support-ref-copied-from-public"],
    "optional_support_refs": []
  },
  "source_turn_refs": ["turn-ref-copied-from-public"],
  "source_session_refs": ["session-ref-copied-from-public"],
  "evidence_bindings": [
    {"evidence_id": "evidence-id-copied-from-public", "speaker": "user"}
  ],
  "lifecycle": "candidate"
}
```

## Deterministic Construction Order

Apply these steps in order for every case:

1. Run the abstention checks before constructing typed content. `possible`
   without an allowed `possible` output modality and a deictic selected option
   without public identifying details are mandatory abstentions.
2. For an emission, create exactly one primary structured claim. Set its
   predicate surface from `untyped_candidate.predicate`, its first entity from
   `untyped_candidate.subject`, and its theme/object entity from
   `untyped_candidate.object`. These candidate strings take precedence over
   shorter L1 support surfaces. Add another entity only for an explicit target
   value or format stated in public text/support.
3. Map candidate modality exactly: `requested` becomes `requested`,
   `committed` becomes `planned`, `planned` becomes `planned`, and `actual`
   becomes `actual`. Never infer primary-claim modality from the final L1
   support when the untyped candidate supplies a modality.
4. Select the L2 operator and abstraction for the resolved cross-turn meaning.
   A request that transforms previously produced items into an explicit target
   form uses the catalog's operator whose name starts with `transform_` and
   corresponding `.transform_` sense, plus `lifecycle_resolution`; do not
   reuse an L1 `request_...conversion` operator for that L2 transformation.
   A requested task assembled from independent prerequisite constraints,
   current state and instruction/request supports uses `task_composition`.
   A committed decision that advances an earlier considered/proposed task uses
   `lifecycle_resolution`. Use `coreference_resolution` only when neither a
   state transition nor task composition applies. In particular, when an
   earlier support only identifies the entity referred to by a later request
   and adds no independent task constraint, use `coreference_resolution`, not
   `task_composition`.
5. Map closure directly from abstraction: `lifecycle_resolution` requires
   `update_supersession`; `task_composition` and `coreference_resolution`
   require `multi_evidence_set` for this dev contract.

The public canonical operator policy includes this domain binding:

- A performance-goal L2 claim that transforms an existing goal set into SMART
  goals uses canonical operator `transform_performance_goals_smart` and sense
  `performance.transform_goals_smart`. The L1 operator
  `request_smart_goal_conversion` describes the individual request turn only;
  do not copy it into the resolved L2 transformation claim. Every
  transformation claim must represent the existing input and explicit target
  as distinct local entities. Bind `theme` to the existing input and
  `target_format` to the target entity; never bind both roles to the same local
  entity. For a SMART-goal transformation, the target entity surface is the
  exact public phrase `SMART 绩效目标`.

## Rules

- For every emission, copy `summary` exactly from
  `untyped_candidate.statement`, including punctuation. In the primary
  structured claim, copy `predicate.surface` exactly from
  `untyped_candidate.predicate`; copy the subject and object entity surfaces
  exactly from `untyped_candidate.subject` and `untyped_candidate.object`.
  Preserve any additional role value as an exact phrase explicitly present in
  the public statement or typed supports. Do not shorten, paraphrase or add a
  second claim merely to restate an input support.
- Copy support, turn, session and evidence references exactly from the same
  public case. Do not invent global IDs, identity links, revisions or closure
  evaluation IDs.
- Top-level `supporting_l1_refs` must contain every public support exactly once.
  Every top-level support must be consumed by at least one structured claim,
  and `closure.required_support_refs` must equal the top-level support set.
  When the candidate has one primary claim, that claim's
  `supporting_l1_refs` must equal the top-level support set. Source turns,
  sessions and evidence must cover all public supports exactly.
- `kind`, abstraction method, closure pattern, predicate sense, canonical
  operator, roles, modality and polarity must come from public catalogs and be
  selected by meaning.
- Entity numbering is local to each structured claim, not shared across
  claims. Restart at `entity-01` inside every claim. A two-entity claim uses
  exactly `entity-01` and `entity-02`, even when earlier claims used those
  IDs. Claim-local IDs do not express cross-claim identity. Every role
  references a local entity. Copy entity surfaces from public text or typed L1
  supports; do not create global entity identity.
- Preserve unresolved time as null. Do not guess calendar dates or identity.
- Choose the dominant abstraction, not merely the presence of a pronoun.
  Use `lifecycle_resolution` with `update_supersession` whenever later support
  commits, schedules, transforms, replaces or otherwise advances an earlier
  proposed/requested state. Use `task_composition` when multiple supports
  jointly provide requirements, current state and the requested task. Use
  `coreference_resolution` only when resolving the cross-turn referent is the
  abstraction and no lifecycle transition or multi-support task composition
  applies. Otherwise use `multi_evidence_set` for a complete multi-turn
  evidence bundle.
- Abstain when source modality has no exact typed meaning, when a selected
  option or object lacks typed L1 support, when required evidence is absent,
  or when closure/source coverage would be incomplete. Do not repair missing
  support with agent text, lexical similarity, embedding, WordNet,
  schema.org, Extended-AMR or KEOL.
- In particular, if `untyped_candidate.qualifiers.modality` is `possible` and
  `possible` is not an allowed output modality, abstain; never reinterpret it
  as `planned` or `actual` from a related support. If a selection refers only
  to a deictic option such as a numbered/relative choice and the public support
  pack lacks the selected option's identifying details or evidence chain,
  abstain even when a selection event support exists.
- The support pack is non-authoritative input. Do not claim or execute L1/L2,
  revision, closure, identity, membership, snapshot or aggregate writes.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.

Before finishing, parse the JSON and verify exact metadata, exact case
coverage, no extra keys, confidence bounds, closed local references, public
vocabulary membership, exact public support/turn/session/evidence references,
and null typed candidate for every abstention. Verify each structured claim
independently restarts contiguous entity numbering at `entity-01`. Emit JSON
only.
