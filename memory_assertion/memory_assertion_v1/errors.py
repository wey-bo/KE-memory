"""Errors raised when a document does not satisfy the structural contract.

One error type, not a hierarchy. Callers act on "this is not a well-formed KE", and the
detail that matters -- which field, which value -- is already carried by pydantic's
ValidationError, which this wraps rather than replaces.
"""

from __future__ import annotations


class StructuralContractError(ValueError):
    """A document violates the memory-assertion/v1 structural contract.

    Structural only. A KE that satisfies this contract is *well-formed*, not true, not
    admitted, and not known to resolve against any snapshot -- those are separate
    claims that this layer does not make.
    """
