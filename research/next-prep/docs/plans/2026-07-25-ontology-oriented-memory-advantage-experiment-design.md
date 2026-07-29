# Ontology-Oriented Memory Advantage Experiment Design

Status: approved by the user; implementation has not started.

## 1. Objective

This experiment tests whether ontology-oriented memory has a measurable advantage over strong vector retrieval and under-modeled ontologies on memory tasks that require structural semantics.

The experiment does not assume that ontology must use KE, RDF, OWL, or a fully explicit graph. WordNet senses, canonical entities, AMR, typed event roles, temporal state, and other symbolic structures are eligible when they materially participate in retrieval or constraint execution. KE is one possible serialization, not the default winner.

Embedding remains a fallback and evidence-recovery mechanism. It must not override explicit provenance, polarity, temporal validity, modality, quantity, conflict, or supersession semantics.

This is a directional, small-scale go/no-go experiment. Passing it justifies a larger confirmatory study; it does not by itself prove universal superiority over existing memory systems.

## 2. Operational Definitions

### 2.1 Ontology-oriented memory

A memory is ontology-oriented for a competency when stable concepts, senses, types, relations, roles, temporal constraints, provenance, or lifecycle state are used to filter, bind, traverse, or otherwise execute the query.

### 2.2 Under-modeled ontology

An ontology is under-modeled relative to a competency when it lacks one or more semantic primitives required to answer that competency reliably. The same representation can be sufficient for synonym normalization and under-modeled for temporal updates or participant roles.

The label is therefore query-relative, not system-wide. A graph, keyword set, or schema is not sufficient merely because structured fields exist.

### 2.3 Ranking versus execution

The audit and experiment distinguish four capability levels:

1. `stored`: the information is retained;
2. `normalized`: it has stable identity or type;
3. `queryable`: a query can address it;
4. `executable`: it deterministically affects binding, filtering, traversal, validity, or conflict handling.

## 3. Research Questions and Hypotheses

- RQ1: Does sufficient ontology plus symbolic execution outperform strong dense or hybrid ranking on structural memory tasks?
- RQ2: Which missing ontology primitives create critical false positives or incomplete evidence sets?
- RQ3: How much of the oracle representation advantage survives automatic extraction?
- RQ4: Can conditional embedding fallback preserve lexical and out-of-domain recall without damaging symbolic precision?
- RQ5: Do documented architecture choices in mainstream memory systems expose the same capability risks as the controlled ablations?

Pre-registered hypotheses:

- H1: role, polarity, quantity, temporal-state, and multi-constraint probes will favor sufficient ontology execution over ranking-only retrieval.
- H2: deleting the required primitive from the same representation will recreate the corresponding error.
- H3: embedding fallback will mainly help synonym, unresolved-entity, and ontology-coverage misses rather than structural queries.
- H4: automatic extraction will retain at least 70 percent of the oracle gain if representation is not the bottleneck.

## 4. Mainstream Architecture Audit

The primary audit targets are version-frozen on 2026-07-25:

| System | Frozen commit | Confirmed capabilities from official sources | Initial risk to test |
| --- | --- | --- | --- |
| Mem0 | `d653b63fac6c8ad0ad84aead0912b366e705d269` | fact extraction, vector storage, entity linking, semantic/BM25/entity fusion, temporal reasoning | relevance fusion may not execute exact role, polarity, quantity, or epistemic constraints; agent-generated facts are first-class in the documented v3 algorithm |
| Graphiti | `3bb2d0bba56f8e22311574c045452c420a012f49` | temporal fact edges, validity windows, episode provenance, custom node/edge types, date filtering, hybrid search and graph reranking | strongest ontology-oriented opponent; test n-ary events, polarity, modality, quantity, and deterministic conjunctive execution rather than treating time as a weakness |
| Hindsight | `ed120a256d51d731085ec8aca724573a7f2f1e1c` | world/experience facts, entity resolution, two temporal dimensions, semantic/keyword/graph/temporal retrieval | graph expansion and equal-weight RRF may retrieve structural neighbors without enforcing typed role or conjunction constraints |
| MemPalace | `8ab251c452c43f2b07a76a28f2433e258307f571` | temporal entity-relation triples, invalidation, source-memory links, entity timeline queries | official documentation marks end-to-end contradiction detection as planned rather than shipped |

Each audit claim receives one evidence grade:

- `confirmed_capability`: explicit official code or documentation;
- `confirmed_gap`: explicitly unimplemented or shown in an official per-item failure;
- `architectural_risk`: not documented, or used only as a ranking signal rather than a constraint;
- `class_level_evidence`: controlled ablation proves that the architecture class is vulnerable, without claiming the unrun named system fails.

The project will not install or rerun these systems. A local architecture-class baseline or ablation must never be reported as the named system's score.

## 5. Representation and Execution Factorization

Representations are a capability ladder rather than a single mandatory schema:

| Layer | Minimum content | Target competencies |
| --- | --- | --- |
| `L0` | atomic natural-language facts, summaries, raw evidence links | extraction-only baseline |
| `L1` | canonical entities, keywords, WordNet synsets, type hierarchy | synonymy, sense disambiguation, subsumption |
| `L2` | AMR or typed event-role graph | predicate and participant binding, polarity, event structure |
| `L3` | time, quantity, modality, provenance status, conflict, supersession | current state, history, epistemic control, exact constraints |

Execution is varied independently:

- `E0`: dense or hybrid ranking only;
- `E1`: entity binding, typed filtering, conjunction, temporal filtering, and graph traversal;
- `E2`: execute `E1`, then invoke embedding only for a pre-declared symbolic miss.

The experimental arms are:

- `B0 = raw + E0`;
- `B1 = L0 + E0`;
- `B2 = L1+L2+L3 + E0`, isolating representation without structural execution;
- `O- = sufficient representation minus one required primitive + E1`;
- `O+ = L1+L2+L3 + E1`;
- `O+E = L1+L2+L3 + E2`.

Every arm is evaluated in an oracle representation track and an automatic extraction track. An adapter may expose only semantics encoded by its source representation. It cannot reconstruct hidden gold fields.

## 6. Controlled Dataset

The dataset contains 60 independent English base scenarios, 15 in each family:

1. participant roles, polarity, modality, and quantity;
2. temporal updates, corrections, conflicts, supersession, and provenance;
3. AND constraints, exact sets, and multi-hop composition;
4. synonymy, sense ambiguity, ontology-external language, and unanswerable queries.

Forty scenarios are architecture-directed, with ten primary scenarios attributed to each audited system. Twenty are neutral competency scenarios derived from the pre-registered capability list rather than a named architecture. A scenario may provide secondary coverage for more than one system.

Each scenario contains:

- four to eight dialogue turns;
- a unique correct answer or explicit unanswerable label;
- exact evidence spans and the complete required evidence set;
- two to four semantically similar but structurally wrong hard negatives;
- the required semantic primitives;
- architecture claim, risk, proposed ontology remedy, and falsifier.

Each base scenario runs with 0, 50, and 500 distractor memories. Distractors reuse entities, relation words, and dates while changing role, polarity, quantity, or validity. The three scales are repeated observations of one base scenario, not independent statistical samples.

Twelve base scenarios, three per family, form the development set. The remaining 48 are frozen hidden tests. Architecture coverage proportions must be preserved across the split.

## 7. Isolation and Fairness

Gold is frozen before representation generation. No prompt, adapter, or executor may see answers, question IDs, benchmark labels, or hidden evidence annotations.

All arms share source turns, ingestion units, question text, answer model, evidence token budget, hardware class, and warm/cold timing protocol. Dense baselines must use a strong current embedding model and documented search parameters rather than an intentionally weak lexical baseline.

Two tracks isolate different causes:

1. Oracle representation track: human-correct representation and semantic query plan measure the representation and execution ceiling. Results are labeled ceiling results, not end-to-end system scores.
2. Automatic end-to-end track: frozen extraction and query compilation operate on natural-language inputs. Their latency, tokens, and failures are included.

The hidden test set cannot be used to revise prompts, schemas, ontology primitives, fallback rules, or query plans.

## 8. Query Boundary and Fallback

Detailed product query syntax remains outside this design. The experiment requires only the minimum query-plan operations needed by the probes:

- entity and sense resolution;
- predicate or event-role matching;
- polarity, modality, quantity, time, status, and provenance filters;
- AND constraints and bounded path traversal;
- evidence-set completion and abstention.

Embedding fallback may trigger only when a pre-declared condition is observed, such as unresolved entity, uncovered predicate, missing required slot, or empty symbolic result. Every trigger records its reason. Embedding candidates may supplement missing evidence but may not override explicit invalidity, negation, provenance status, conflict, or supersession.

## 9. Metrics

Primary metrics:

- Evidence Set Exact Match;
- Critical False Positive Rate;
- Constraint Satisfaction Rate;
- final Answer Correctness;
- Abstention Accuracy.

Diagnostic and efficiency metrics:

- Evidence Precision@K and Recall@K under a fixed evidence-token budget;
- symbolic query coverage and embedding fallback frequency;
- candidate count and evidence tokens returned;
- extraction accuracy per required primitive;
- ingestion, update, and query P50/P95 latency;
- model input/output tokens, storage growth, and update cost.

Comparisons are paired by base scenario. Reports include absolute differences, family-level results, failure categories, and 95 percent bootstrap intervals sampled at the base-scenario level. The 60-scenario pilot remains directional even when an interval excludes zero.

## 10. Go/No-Go Gates

The experiment finds a worthwhile ontology advantage only when all conditions hold:

- `O+` improves Evidence Set Exact Match by at least 15 percentage points over strong dense and `O-` in at least two structural families;
- Critical False Positive Rate falls by at least 50 percent;
- the advantage remains at 500 hard distractors;
- automatic extraction retains at least 70 percent of the oracle gain;
- `O+E` loses no more than 3 percentage points of recall against the best dense arm on lexical and out-of-domain cases;
- total embedding fallback remains below 30 percent and structural-family fallback below 10 percent.

Interpretation and stop rules:

- oracle failure means the representation or primitive is rejected for that competency;
- oracle success plus automatic failure identifies extraction tax;
- correct automatic representation plus retrieval failure identifies execution weakness;
- correct evidence plus wrong answer identifies answer-generation failure;
- `O-` matching `O+` means the removed primitive does not justify its complexity;
- persistent embedding use on structural families rejects the symbol-first claim for those families.

Passing this gate authorizes an expanded confirmatory set with at least 50 independent scenarios per family.

## 11. Execution Flow and Failure Policy

The execution order is fixed:

1. freeze official architecture sources and claims;
2. freeze gold scenarios and distractors;
3. generate and validate representation layers;
4. run oracle representations and execution;
5. run automatic extraction and frozen query compilation;
6. generate answers with the fixed answer model;
7. perform paired attribution and error analysis;
8. append compatible official benchmark results as external context.

Format failure receives at most one uniform deterministic repair. A second failure is an extraction failure. Hidden-test facts, query plans, or answers cannot be manually repaired. Ambiguous gold discovered after freezing is quarantined with a reason and excluded from the main denominator without replacement.

Every run preserves raw input, raw model output, representation and prompt versions, candidate rankings, symbolic trace, fallback reason, evidence selection, answer, latency, tokens, and error classification.

## 12. Natural Benchmarks and External Results

After the controlled gate, the surviving arms are evaluated on pre-registered slices of LoCoMo, LongMemEval, and BEAM, followed by broader runs only if the slices pass. The same evidence, answer, latency, token, and failure metrics apply.

Other memory systems remain author-reported comparisons only. An external result ledger records:

- system and version or retrieval date;
- benchmark version and split;
- base and answer models;
- context and retrieval budget;
- metric definition;
- official source URL and artifact path;
- comparability status.

Only identical or demonstrably compatible protocols may be placed in a direct numeric table. Retrieval recall, end-to-end QA, different splits, or different judges remain separate contextual evidence.

## 13. Planned Artifacts

Implementation should keep executable code and immutable experiment evidence separate:

```text
tools/ontology_memory_experiment/
  contracts, validators, representation adapters, executors, scoring, reports

artifacts/ontology-memory-experiment/
  architecture-audit/
  gold/
  prompts/
  representations/
  runs/<run_id>/
  reports/
```

Minimum audit artifacts are a source manifest, capability matrix, gap-hypothesis ledger, official-results ledger, frozen scenario manifest, run ledger, error ledger, and final gate report.

No implementation directory or experiment result is created by approving this design. A separate implementation plan must define schemas, commands, dependencies, fixtures, and verification steps.

## 14. Official Sources Used for the Initial Audit

- Mem0 repository and architecture documentation at `d653b63fac6c8ad0ad84aead0912b366e705d269`
- Graphiti repository, README, edge model, and search filters at `3bb2d0bba56f8e22311574c045452c420a012f49`
- Hindsight retain and retrieval documentation at `ed120a256d51d731085ec8aca724573a7f2f1e1c`
- MemPalace knowledge-graph and contradiction-detection documentation at `8ab251c452c43f2b07a76a28f2433e258307f571`

The implementation must preserve exact URLs, retrieved timestamps, hashes where practical, and claim-level excerpts in the source manifest.
