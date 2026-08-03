"""Foundation ontology v2, built from the frozen external sources.

Kept a separate package from ``ontology_v1`` so v1 stays readable as a frozen artifact while v2
supersedes it.
"""

from __future__ import annotations

from .decisions import build_decisions
from .l1_content import build_o_l1
from .l2_content import build_o_l2
from .mapping_content import build_m_l1_to_l2
from .supersession import build_supersession

__all__ = [
    "build_decisions",
    "build_m_l1_to_l2",
    "build_o_l1",
    "build_o_l2",
    "build_supersession",
]
