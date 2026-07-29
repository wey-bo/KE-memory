# Identity Proposal Policy v4.1

Use only the public case fields and quoted evidence. These proposals are candidates, not authoritative writes.

## Identity

- Evaluate identity in this order: first look for an authorized `merge` trigger, then an authorized `keep_distinct` trigger, and otherwise `abstain`.
- Propose `merge` only when the public evidence explicitly says the mentions are the same entity, both mentions have the same non-null source actor binding for a person, trusted identifiers explicitly match, or direct anaphoric/possessive wording unambiguously names one object.
- Direct anaphoric/possessive continuity requires observable coreference wording in the quoted evidence, such as a pronoun, possessive, `same`, or another explicit reference whose antecedent is unique. Repeated definite descriptions, occurrence in one source item, or related repository/application/branch context do not establish coreference.
- When mentions occur in different evidence units and have null actor bindings, abstain unless the quotes explicitly state same identity, share a trusted identifier, or contain the observable unambiguous coreference wording above.
- Do not use `direct_anaphoric_continuity` as a reason code unless that observable wording is present in the cited quotes.
- Same source item, thread, topic, concept type, lexical similarity, software stack, or repository/application context alone is insufficient for `merge`.
- Propose `keep_distinct` only when public evidence contains incompatible non-null source actor bindings, incompatible trusted identifiers stated in the quotes, or an explicit statement that the entities are distinct.
- Differences in surface, role, class, title, format, or time alone are insufficient for `keep_distinct` when both mentions could still denote one entity.
- If neither the positive nor negative identity condition is established, propose `abstain`.

## Membership

- Before semantic fallback, compare the public `query_subject_id` with every required mention's public `source_actor_id`.
- If the query subject and the required mention actor are both non-null and exactly equal, propose `include`; do not abstain from that exact match.
- If the query subject and the required mention actor are both non-null and unequal, propose `exclude`; do not abstain from that exact mismatch.
- When actor bindings are null, mixed across required mentions, or otherwise unavailable, propose `include` only when the public evidence explicitly binds the mentioned item to the query subject, including an explicit requested-member statement.
- A requested-member statement is explicit when the public question asks whether the named member is requested for the named group and the cited quote uses an imperative or request verb such as `include`, `add`, or `create` for that same member surface. The quote need not repeat the group name when the public case supplies that group context.
- Under the same null, mixed, or unavailable conditions, propose `exclude` only when the public evidence explicitly binds the mentioned item to a different subject or explicitly states non-membership.
- Topic relevance, shared context, lexical similarity, or embedding-like similarity is insufficient for membership.
- If neither inclusion nor exclusion is established, propose `abstain`.

## Evidence and confidence

- Cite every case-local mention used by the decision and no mention from another case.
- A non-abstain action requires direct public evidence satisfying the corresponding rule.
- Use calibrated confidence. Do not use high confidence to compensate for missing identity or membership evidence.
