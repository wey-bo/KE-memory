# Identity Proposal Policy v1

Use only the public case fields and quoted evidence. These proposals are candidates, not authoritative writes.

## Identity

- Propose `merge` only when the public evidence explicitly says the mentions are the same entity, both mentions have the same non-null source actor binding for a person, or direct anaphoric/possessive continuity unambiguously names one object.
- Same source item, thread, topic, concept type, lexical similarity, or repository/application context alone is insufficient for `merge`.
- Propose `keep_distinct` only when public evidence contains incompatible non-null source actor bindings, incompatible trusted identifiers stated in the quotes, or an explicit statement that the entities are distinct.
- Differences in surface, role, class, title, format, or time alone are insufficient for `keep_distinct` when both mentions could still denote one entity.
- If neither the positive nor negative identity condition is established, propose `abstain`.

## Membership

- Propose `include` when the public evidence explicitly binds the mentioned item to the query subject, including a matching non-null source actor binding or an explicit requested-member statement.
- Propose `exclude` when the public evidence explicitly binds the mentioned item to a different subject or explicitly states non-membership.
- Topic relevance, shared context, lexical similarity, or embedding-like similarity is insufficient for membership.
- If neither inclusion nor exclusion is established, propose `abstain`.

## Evidence and confidence

- Cite every case-local mention used by the decision and no mention from another case.
- A non-abstain action requires direct public evidence satisfying the corresponding rule.
- Use calibrated confidence. Do not use high confidence to compensate for missing identity or membership evidence.
