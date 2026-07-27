"""Compatibility facade for :mod:`ke_memory_service.api`."""

from ke_memory_service.api import (
    ContextRequest,
    CorrectionRequest,
    SearchRequest,
    TurnRequest,
    create_app,
    main,
)


__all__ = [
    "ContextRequest",
    "CorrectionRequest",
    "SearchRequest",
    "TurnRequest",
    "create_app",
    "main",
]
