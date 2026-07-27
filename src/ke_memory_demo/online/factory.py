"""Compatibility facade for :mod:`ke_memory_service.runtime`."""

from ke_memory_service.runtime import (
    EmptyOnlineExtractor,
    OnlineRuntime,
    build_online_runtime,
)


__all__ = ["EmptyOnlineExtractor", "OnlineRuntime", "build_online_runtime"]
