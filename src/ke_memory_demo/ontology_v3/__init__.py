"""Foundation ontology v3: four families added on top of the v2 candidate freeze.

Kept a separate package so v2 stays readable as a frozen artifact. Nothing here reads the validation
sample, the mapper output or the annotation gold: aliases come from independent corpora and the
frozen published sources, so an item earns its place by what the corpora attest.
"""

from __future__ import annotations

from .evidence import FamilyEvidence, SurfaceEvidence, collect_all

__all__ = ["FamilyEvidence", "SurfaceEvidence", "collect_all"]
