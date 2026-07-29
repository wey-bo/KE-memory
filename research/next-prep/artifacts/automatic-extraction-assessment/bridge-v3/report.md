# Automatic L1/L2 Extraction Bridge Assessment

Status: `pass`

## Raw extraction structure

- Projected records: 416
- Active records: 390
- Exact evidence binding rate: 1.0
- Source-status admissibility rate: 1.0
- These are structural measurements over existing model output, not gold semantic accuracy.

## Deterministic bridge safety

- L1 single-turn candidates: 402
- L2 cross-turn candidates: 14
- Authoritative-ready L1/L2: 0/0
- Materialization-blocked records: 416
- Automatic authoritative writes: 0
- Guard unchanged: true
- Integration ready: false

### Blocking gaps

- `missing_abstraction_method`: 14
- `missing_canonical_operator`: 416
- `missing_closure_specification`: 14
- `missing_local_entity_ids`: 416
- `missing_memory_kind`: 416
- `missing_predicate_sense`: 416
- `missing_source_turn_session_closure`: 14
- `missing_structured_claim`: 14
- `missing_supporting_l1_unit_ids`: 14
- `missing_typed_condition_bindings`: 51
- `missing_typed_derivation_provenance`: 68
- `missing_typed_role_bindings`: 416
- `missing_typed_scope_bindings`: 79
- `missing_typed_time_binding`: 64
- `unsupported_modality`: 52

## Typed extractor v2 requirements

- `explicit_level_and_typed_memory_kind`
- `typed_predicate_surface_sense_and_canonical_operator`
- `typed_role_bindings_and_candidate_scoped_local_entity_ids`
- `typed_modality_polarity_and_time_bindings`
- `typed_condition_and_scope_bindings`
- `typed_derivation_and_inference_provenance`
- `typed_evidence_speaker_bindings`
- `exact_evidence_references`
- `explicit_lifecycle_correction_supersession_and_conflict_links`
- `l2_supporting_l1_candidate_ids`
- `l2_structured_claims_and_abstraction_method`
- `l2_closure_pattern_and_source_turn_session_coverage`
- `explicit_abstention_or_no_memory_for_unresolved_required_fields`

## Limitations

- No model was rerun in this wave.
- The assessment does not publish authoritative L1, L2, unit revisions, closure, identity, or membership writes.
- Missing semantic fields are blocked rather than filled by heuristics, WordNet, schema.org, or embeddings.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- This wave does not compile questions, execute new benchmark queries, aggregate across sessions, or select a storage profile.
