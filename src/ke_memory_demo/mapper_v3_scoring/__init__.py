"""Scoring for mapper v3 against the frozen annotation gold.

This package never reads a mapper module, a mapper artifact, or the real gold. It scores whatever
gold records and mapping results a caller hands it, against a structural contract for what a
mapping result must provide (see :mod:`.scorer`). That separation is what lets the scorer and its
tests be built and verified before mapper v3 or the real gold exist.
"""

from __future__ import annotations
