"""L2 derivation through M_L1_to_L2, rather than direct alias matching.

The contract review caught a structural defect before validation was consumed. L2 was being indexed
the same way as L1 — by alias string — so ``I go running every Tuesday without fail`` returned
no_map, because the utterance contains no word from ``["routine", "usually does", "regular
practice"]``. Matching a habit by the literal word "routine" is not how an abstraction is recognised.

The map already says how it should work. Every entry declares ``l1_source_ids``, an
``evidence_required`` count and a ``kind``: an L2 item is attested when enough of its L1 sources are
attested, not when its own name appears. So L2 derivation consumes L1 candidates.

This makes the two layers behave differently on purpose, which matters for reading the validation
report: an L1 result is a lexical-and-structural recognition, while an L2 result is a derivation over
L1 evidence. A single accuracy figure spanning both would hide that difference.

``evidence_required`` is honoured strictly. An abstraction requiring two L1 sources is not attested by
one, and admitting it anyway would report an abstraction the ontology says is unsupported.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ke_memory_demo.core.json import JsonObject

from .candidate_generation import Candidate, Evidence, EvidenceKind


@dataclass(frozen=True)
class DerivationRule:
    """One map entry: which L1 items attest an L2 item, and how many are needed."""

    map_id: str
    l2_target_id: str
    l1_source_ids: frozenset[str]
    evidence_required: int
    kind: str
    rule: str


@dataclass(frozen=True)
class L2Derivation:
    """An L2 item, the L1 candidates that attest it, and whether the rule was satisfied."""

    l2_target_id: str
    sense: str
    map_id: str
    kind: str
    satisfied_by: tuple[str, ...]
    evidence_required: int

    @property
    def is_attested(self) -> bool:
        return len(self.satisfied_by) >= self.evidence_required

    def as_candidate(self, score: float) -> Candidate:
        """Present the derivation as a candidate, keeping its provenance in the evidence."""
        return Candidate(
            ontology_id=self.l2_target_id,
            sense=self.sense,
            evidence=tuple(
                Evidence(
                    kind=EvidenceKind.PREDICATE_ROLESET,
                    term=source_id,
                    detail=f"derived via {self.map_id} ({self.kind})",
                )
                for source_id in self.satisfied_by
            ),
        )

    def as_json(self) -> JsonObject:
        return {
            "ontology_id": self.l2_target_id,
            "sense": self.sense,
            "map_id": self.map_id,
            "kind": self.kind,
            "satisfied_by": list(self.satisfied_by),
            "evidence_required": self.evidence_required,
            "is_attested": self.is_attested,
        }


class L2Deriver:
    """Derive L2 candidates from L1 candidates through the frozen map."""

    def __init__(self, ontology_dir: Path) -> None:
        mapping = cast(
            "dict[str, Any]",
            json.loads((ontology_dir / "m_l1_to_l2.json").read_text(encoding="utf-8")),
        )
        l2 = cast(
            "dict[str, Any]",
            json.loads((ontology_dir / "o_l2.json").read_text(encoding="utf-8")),
        )
        self._senses: dict[str, str] = {}
        for wrapper in cast("list[Any]", l2["items"]):
            item = cast("dict[str, Any]", cast("dict[str, Any]", wrapper)["item"])
            self._senses[str(item["id"])] = str(item.get("sense", ""))

        rules: list[DerivationRule] = []
        for raw in cast("list[Any]", mapping["entries"]):
            entry = cast("dict[str, Any]", raw)
            rules.append(
                DerivationRule(
                    map_id=str(entry["map_id"]),
                    l2_target_id=str(entry["l2_target_id"]),
                    l1_source_ids=frozenset(
                        str(x) for x in cast("list[Any]", entry["l1_source_ids"])
                    ),
                    evidence_required=int(entry["evidence_required"]),
                    kind=str(entry.get("kind", "")),
                    rule=str(entry.get("rule", "")),
                )
            )
        self._rules = tuple(rules)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def covered_l2_ids(self) -> frozenset[str]:
        return frozenset(rule.l2_target_id for rule in self._rules)

    def derive(self, l1_candidates: Sequence[Candidate]) -> tuple[L2Derivation, ...]:
        """Which L2 items the L1 candidates attest, strongest support first."""
        attested_l1 = {candidate.ontology_id for candidate in l1_candidates}
        scores = {candidate.ontology_id: candidate.score for candidate in l1_candidates}

        derivations: list[L2Derivation] = []
        for rule in self._rules:
            satisfied = tuple(sorted(rule.l1_source_ids & attested_l1))
            if not satisfied:
                continue
            derivation = L2Derivation(
                l2_target_id=rule.l2_target_id,
                sense=self._senses.get(rule.l2_target_id, ""),
                map_id=rule.map_id,
                kind=rule.kind,
                satisfied_by=satisfied,
                evidence_required=rule.evidence_required,
            )
            # An unsatisfied rule is dropped rather than reported weakly: the ontology states how much
            # evidence an abstraction needs, and offering it on less would contradict the ontology.
            if derivation.is_attested:
                derivations.append(derivation)

        derivations.sort(
            key=lambda d: (
                -sum(scores.get(source, 0.0) for source in d.satisfied_by),
                d.l2_target_id,
            )
        )
        return tuple(derivations)

    def derived_candidates(
        self, l1_candidates: Sequence[Candidate]
    ) -> tuple[Candidate, ...]:
        scores = {candidate.ontology_id: candidate.score for candidate in l1_candidates}
        return tuple(
            derivation.as_candidate(
                sum(scores.get(source, 0.0) for source in derivation.satisfied_by)
            )
            for derivation in self.derive(l1_candidates)
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "derivation_path": (
                "L2 is derived from L1 candidates through M_L1_to_L2, not indexed by its own aliases"
            ),
            "why": (
                "direct alias indexing returned no_map for clear abstractions: a habit utterance "
                "contains no word from the habit item's alias list, because an abstraction is "
                "recognised from what attests it rather than from its own name"
            ),
            "rules": self.rule_count,
            "l2_items_covered": len(self.covered_l2_ids()),
            "evidence_required_honoured": (
                "a rule needing two L1 sources is not satisfied by one; an unsatisfied rule yields no "
                "candidate rather than a weak one"
            ),
        }
