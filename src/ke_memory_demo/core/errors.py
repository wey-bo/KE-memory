"""Errors shared across layers.

``PreflightCheckFailure`` lives here rather than in ``evaluation`` because both
evaluation and the pipeline runtime raise it, and having the pipeline import it
from evaluation made orchestration depend on measurement. The exception itself
carries no evaluation semantics -- it is a sanitized failure signal.

Sanitized is the point: the detail is written for a log or a CLI message, so it
must never carry a path, endpoint, credential or other environment specific. The
callers deliberately pass a fixed ``failure_detail`` string instead of formatting
the offending value into it.
"""

from __future__ import annotations


class PreflightCheckFailure(RuntimeError):
    """A precondition check failed, with an intentionally sanitized detail.

    Raised before work begins, when the environment cannot support it. The message
    is safe to surface; it names what class of check failed, not the value that
    failed it.
    """
