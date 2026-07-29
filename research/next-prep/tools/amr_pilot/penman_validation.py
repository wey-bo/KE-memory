"""Strict PENMAN and lightweight AMR structural validation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Collection

import penman
from penman.exceptions import PenmanError


FRAME_PATTERN = re.compile(r"^.+-[0-9]{2}$")
CORE_ROLE_PATTERN = re.compile(r"^:ARG[0-9]+(?:-of)?$")


@dataclass(frozen=True, slots=True)
class PenmanValidationResult:
    syntax_valid: bool
    graph_count: int
    graphs: tuple[penman.Graph, ...]
    errors: tuple[str, ...]
    unknown_frames: tuple[str, ...]
    frame_inventory_status: str

    @property
    def is_valid(self) -> bool:
        return self.syntax_valid and self.graph_count == 1 and not self.errors


def validate_penman(
    text: str,
    *,
    propbank_inventory: Collection[str] | None,
) -> PenmanValidationResult:
    frame_inventory_status = (
        "validated" if propbank_inventory is not None else "unavailable"
    )
    if "```" in text:
        return PenmanValidationResult(
            syntax_valid=False,
            graph_count=0,
            graphs=(),
            errors=("Markdown fences are not allowed",),
            unknown_frames=(),
            frame_inventory_status=frame_inventory_status,
        )
    try:
        graphs = tuple(penman.loads(text))
    except (PenmanError, IndexError, ValueError) as error:
        return PenmanValidationResult(
            syntax_valid=False,
            graph_count=0,
            graphs=(),
            errors=(f"PENMAN parse failed: {error}",),
            unknown_frames=(),
            frame_inventory_status=frame_inventory_status,
        )

    errors: list[str] = []
    unknown_frames: set[str] = set()
    if len(graphs) != 1:
        errors.append("exactly one graph is required")

    for graph_index, graph in enumerate(graphs, start=1):
        variables: set[str] = set()
        for instance in graph.instances():
            if instance.target is None:
                errors.append(
                    f"graph {graph_index} variable {instance.source} is missing an instance triple"
                )
                continue
            variables.add(instance.source)
            concept = str(instance.target)
            if (
                propbank_inventory is not None
                and FRAME_PATTERN.fullmatch(concept)
                and concept not in propbank_inventory
            ):
                unknown_frames.add(concept)

        for source, role, target in graph.triples:
            if role != ":instance" and source not in variables:
                errors.append(f"graph {graph_index} variable {source} is missing an instance triple")
            if CORE_ROLE_PATTERN.fullmatch(role) and isinstance(target, str) and target not in variables:
                errors.append(f"graph {graph_index} has unbound reference {target} for {role}")

    for frame in sorted(unknown_frames):
        errors.append(f"unknown PropBank frame: {frame}")
    return PenmanValidationResult(
        syntax_valid=True,
        graph_count=len(graphs),
        graphs=graphs,
        errors=tuple(dict.fromkeys(errors)),
        unknown_frames=tuple(sorted(unknown_frames)),
        frame_inventory_status=frame_inventory_status,
    )
