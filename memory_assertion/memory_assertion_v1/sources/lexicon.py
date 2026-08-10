"""The derived lexical index, and the two normalisation steps it is allowed to perform.

Non-authoritative by construction. Embedded Lexicalizations travel inside their
Concept/Operator shard and therefore participate in the snapshot hash; this index is
computed *from* them and does not. A consumer may rebuild it at will, and rebuilding it
must never change a snapshot's identity.

The normalisation is exactly two steps, per the standard: keep the language tag as the
snapshot spells it, and apply Unicode NFC to the surface form. Nothing else. No case
folding, no punctuation stripping, no whitespace collapsing, no language-specific
stemming -- each of those would merge forms the ontology deliberately kept distinct, and
`Person` versus `person` is a different Concept, not a spelling variant.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from memory_assertion_v1.ontology.profile import Lexicalization

IndexKey = tuple[str, str]


def normalize_surface_form(surface_form: str) -> str:
    """Apply NFC and nothing else."""
    return unicodedata.normalize("NFC", surface_form)


def index_key(language: str, surface_form: str) -> IndexKey:
    """The v1 canonical index key: language verbatim, surface form under NFC."""
    return (language, normalize_surface_form(surface_form))


def build_owner_index(
    owners: Iterable[tuple[str, Iterable[Lexicalization]]],
) -> dict[IndexKey, tuple[str, ...]]:
    """Map each `(language, NFC(surface_form))` to the owners that declare it.

    Values are tuples of owner ids, not single ids, because one key legitimately resolves to
    several owners: `resolved` does not promise global unambiguity, and NL2KE still has to
    disambiguate using context, Concept types and Operator signatures. An index that kept
    only one owner per key would silently make that ambiguity invisible.

    Owner ids are sorted so the index is reproducible.
    """
    grouped: dict[IndexKey, set[str]] = {}
    for owner_id, lexicalizations in owners:
        for lexicalization in lexicalizations:
            key = index_key(lexicalization.language, lexicalization.surface_form)
            grouped.setdefault(key, set()).add(owner_id)
    return {key: tuple(sorted(values)) for key, values in grouped.items()}
