# Mapper v3 fresh validation: root cause analysis

Appended after the immutable result in commit `2188ec5`. Nothing in this document changes the
result, the gold, the scorer or the mapper, and the 160-expression set was not re-run to produce
any figure here. Every number is read from the frozen artifacts or computed from the gold alone;
where a claim could not be checked without a re-run, it says so.

## The verdict stands, but "6x worse than v2" does not

Mapper v3 failed. That is not in question: recall of 0.028 micro and 0.000 macro means no
expression had its full gold target set recovered, and `ranking_or_sense` of 0.100 means only a
tenth of the targets it did return were a subset of gold.

What does not survive scrutiny is the direct comparison with v2's 0.165. The two numbers count
different things:

- v2's 0.165 was 13/79 **expressions** in which any gold target appeared.
- v3's 0.028 is 21/751 **atomic ids**, and its macro variant requires the entire target set.

Reporting them side by side, as the result commit does, invites a conclusion the measurement cannot
support. The failure is real; its magnitude relative to v2 is not established.

## Five causes, all pushing the same direction

### 1. v3 replaced v2's evidence sources rather than adding to them

`mapper_v2/candidate_generation.py` generates candidates from four kinds:

| source kind | v2 | v3 |
| --- | --- | --- |
| `PREDICATE_ROLESET` (PropBank) | yes | no |
| `LEXICAL_SENSE` (WordNet) | yes | no |
| `SCHEMA_TYPE` (schema.org) | yes | no |
| `ONTOLOGY_ALIAS` | yes | yes |

`mapper_v2/source_indices.py` loads three frozen archives for these: `wordnet-3.0-nltk.zip`,
`propbank-frames-3.4.0.tar.gz`, `schemaorg-30.0-current-https.jsonld`. Mapper v3 loads none of
them. Its evidence is ontology aliases, id leaf terms, and a regular-expression construction table.

Three of four candidate sources were removed while one was added. "v3 adds construction
understanding to v2" describes an intent, not the diff.

### 2. The added construction evidence is disabled by its own admissibility rule

`mapper_v3/frames.py` grades evidence into `DECISIVE_ALIAS`, `PHRASE_ALIAS` and
`TYPE_COMPATIBILITY`. Only the first two are admissible (`is_admissible` returns False for the
third, weight 0.2). The code states the condition itself:

> `# So construction evidence is decisive only for an item the utterance already`

Construction evidence is decisive **only for an item an alias already matched**. Otherwise it
degrades to the inadmissible kind.

This inverts the reason constructions were introduced. The v2 diagnosis was that an utterance can
express an intention syntactically while naming no word the ontology lists as an alias for
`task.declared_intention`. Constructions were the answer to exactly that case, and the
admissibility rule excludes exactly that case. Where a construction has something to add, it is not
admitted; where it is admitted, an alias had already found the item.

### 3. Constructions map to item-type sets too coarse to select a sense

Compatibility resolves to large fractions of the 139-item index:

| construction | compatible items |
| --- | --- |
| `habitual_aspect` | 49 |
| `past_episode` | 42 |
| `negated_or_ceased` | 42 |
| `possession_claim` | 33 |
| `intention_declaration` | 28 |
| `evaluative_predication` | 28 |
| `information_request` | 24 |
| `salience_claim` | 19 |

`habitual_aspect` reaches 49 because `qualifier_value` alone holds 33 items and the construction
admits that whole type. Admitting these independently would flood the candidate list; refusing to
admit them independently is cause 2. Both settings are wrong, which means the level of
representation is wrong rather than a constant needing adjustment.

### 4. The L1 → M_L1_to_L2 → L2 derivation path was dropped

`mapper_v2/l2_derivation.py` reads `m_l1_to_l2.json` and honours `evidence_required` strictly: an
abstraction needing two L1 sources is not attested by one. Mapper v3 contains no reference to
`m_l1_to_l2` at all. It indexes L1 and L2 items into a single alias table and matches L2 items
directly.

The fresh gold names 34 L2 targets. Under the ontology's own contract these are derivable, not
directly matchable, so v3 has no admissible route to any of them.

The pre-run manifest records `m_l1_to_l2_v3` among the ontology digests. **This overstates the
run.** Recording a digest is not evidence of consumption, and the manifest gives no way to tell the
two apart. Same for `inputs_read`, which lists directory contents rather than files actually opened.

### 5. Mapping and admission were conflated, and this violates a standing prohibition

`mapper_v3.py:190` returns `UNRESOLVED` with reason `request_only_asserts_nothing` for any
utterance detected as a pure information request. The gold, meanwhile, treats the request itself as
attested content: `modality.question` 72 times, `event.information_request` 71,
`predicate.seek_information` 61 — 204 of 751 targets, across 73 expressions.

Recognising "this utterance is a request" is a mapping question. Deciding whether a request is
worth persisting is an admission question. v3 answers the second inside the first, and loses the
first.

This is not only a design error. `benchmark-plan-v2.1.json` `semantic_assistance_policy.forbidden`
lists six prohibitions; mapper v3 violates three:

- `heuristic keyword or regular-expression semantic correction` — the `_PATTERNS` table is the
  mapper's semantic core, not an integrity check.
- `semantic gates that correct model output or force abstention` — `is_request_only` forces
  abstention.
- `contract narrowing that removes unsupported natural questions` — removing question-bearing
  utterances from the mappable range is precisely this.

Mapper v3 was ineligible for the formal benchmark before it was scored. A higher number would not
have changed that. The freeze artifact recorded `is_request_only` as a virtue ("reasoned rather
than thresholded") without checking it against the prohibition list.

## What the scale mismatch does and does not explain

The gold names every attested item, so id-bearing records average 6.31 targets and 118 of 119 are
multi-target. 55 records carry more than 6 targets while the mapper runs with `max_frames=6`, so
those 55 cannot achieve macro exact match under any behaviour: **the macro ceiling is 64/119 =
0.538**, not 1.0. Reporting macro against an implicit ceiling of 1.0 was a reporting error.

But the mismatch cannot absorb the result. Excluding all 204 question targets leaves 547, and even
crediting every one of the 21 hits to that remainder caps recall at **21/547 = 3.8%**. The
algorithm failed on its own terms.

## Instrument defects, separate from the mapper

1. **No per-expression raw output.** The runner wrote only the aggregate report. Error slicing —
   which cause accounts for which missing target — now requires a re-run, which the round forbids.
   Raw output should have been persisted alongside the report from the start.

2. **The freeze hash does not bind what it claims to.** The hashed identity has exactly seven keys:
   `mapper_id`, `mapper_version`, `ambiguity_ratio` and four ontology digests. It does not cover the
   source bytes, the ten-entry `_PATTERNS` regular-expression table, or the `M_L1_to_L2` digest.
   Rewriting the pattern table — the mapper's semantic core — leaves
   `f096094d789361314611c2bf58b887cb5338b6f78c8e1c2039f1f745aa2df219` unchanged, so two materially
   different mappers share one freeze hash.

3. **The behaviour tests verify structure, not capability.** The 11 tests cover multi-frame output,
   `len(target_ids) == len(frames)`, determinism and abstention reasons. None asks whether a
   construction finds the right item when no alias matches — the one property v3 existed to add.
   Every test passed while that property was absent.

## What remains trustworthy

`ontology_coverage` 0.969 (155/160) is a statement about the gold, computed from labels alone with
no mapper involvement. It says the annotator judged 155 of 160 expressions expressible in O_v2 plus
the O_v3 additions. The ontology is not the principal failure here.

The five `out_of_scope` expressions were removed from every recall and accuracy denominator before
computation, so no ontology gap is charged to the mapper.

`l2:abstraction.value_commitment` remains unattested on this corpus, as recorded in the gold
artifact. Cause 4 supplies a further reason to leave its threshold alone: with no derivation path
implemented, this run could not have attested it regardless of the evidence.

## Consequences for v4

The formal benchmark stays blocked. Two contract defects have to close first, and neither is a
mapper-tuning question:

1. **Mapping must not perform admission.** A question has to be representable as what it is, with
   persistence decided downstream.
2. **A structured memory bundle must not be scored as a flat id set.** Frame, role/qualifier,
   canonical mapping, L2 derivation and admission are distinct claims and need distinct scores.

Design constraints that follow from the five causes:

- Qualifiers, roles, predicates and events are slots of one frame, not independent frames.
- L2 is reached by derivation through `M_L1_to_L2` only, never by direct alias match.
- Regular expressions may not be the semantic core. Surface frames may come from a frozen SRL/AMR
  component or a model; deterministic code validates ids, senses, evidence and ontology references.
- Candidate generation restores lexical, roleset and type sources rather than replacing them.

Process requirements for the next round:

- Persist per-expression raw output.
- Bind the freeze hash to source bytes and every resource consumed, and record consumption rather
  than availability.
- Test the no-alias construction path before scoring anything.
- Check the implementation against `semantic_assistance_policy.forbidden` **before** freezing, not
  after the result.
- Freeze v4 and its source digests before any new gold is visible; these 160 expressions become
  exposed regression only, usable for neither tuning nor rescoring.
