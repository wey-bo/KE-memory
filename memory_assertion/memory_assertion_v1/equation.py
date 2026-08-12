"""The knowledge equation: one operator application, equated to one leaf term.

```text
KnowledgeEquation := OperatorApplication "=" LeafTerm
```

The `=` is real many-sorted equality, not assignment and not fact acceptance. `lhs` and
`rhs` are the canonical serialisation direction -- fixed so that one equation has one
byte sequence and can be hashed -- and nothing here derives symmetry, transitivity or
substitution from it. A well-formed equation is a *candidate*: structural validity says
the sentence is grammatical, not that it is true, admitted, or resolvable against any
particular snapshot.

Deliberately absent: `polarity`, `modality`, `temporal`, `assertion_scope`. The older
ke_contract_v1 carried an `AssertionScope` on every equation; this contract's profile
schema lists all three names as forbidden keys, so `extra="forbid"` rejects them rather
than a validator having to know they used to exist.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from memory_assertion_v1.terms import LeafTerm, OperatorApplication


class KnowledgeEquation(BaseModel):
    """`lhs = rhs`, where the left side applies an operator and the right side is a leaf.

    The asymmetry of the two sides is structural, not semantic: only an application may
    stand on the left, which is what makes the serialisation canonical. It does not mean
    the equality reads in one direction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    lhs: OperatorApplication
    rhs: LeafTerm
