"""Delivery adapters for HTTP, MCP, identity, and runtime composition."""

from .identity import (
    InMemoryPrincipalRegistry,
    PrincipalConflict,
    PrincipalKind,
    PrincipalRegistration,
    PrincipalRegistry,
    PrincipalStatus,
    RegisteredPrincipal,
)
from .mcp import MCPMemoryFacade


__all__ = [
    "InMemoryPrincipalRegistry",
    "MCPMemoryFacade",
    "PrincipalConflict",
    "PrincipalKind",
    "PrincipalRegistration",
    "PrincipalRegistry",
    "PrincipalStatus",
    "RegisteredPrincipal",
]
