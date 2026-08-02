"""Track A: build and freeze foundation ontology v1.

Writes five artifacts to ``artifacts/ontology-v1/``: the three freeze units, the candidate
ledger and the provenance snapshot. Each unit carries its own SHA-256 over its own canonical
JSON, so a change to O_L2 moves exactly one hash and a citation about O_L1 stays valid.

There is deliberately no combined ontology hash. Stage 1A rejected one for the same reason: a
single digest says something moved without saying which unit moved.

No model call and no judge call is made. The build is authorship plus arithmetic over local
corpus files, and the judge is hard-prohibited for this task.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.ontology_v1 import FoundationOntology, build_foundation_ontology
from ke_memory_demo.ontology_v1.models import Disposition

ARTIFACT_DIR = Path("artifacts/ontology-v1")


def _unit_payload(ontology: FoundationOntology, unit: str) -> JsonObject:
    """One unit's JSON, with its own digest and nothing about the other units.

    The scope note travels with the artifact rather than living only in this script, because
    whoever reads o_l1.json in six months is the person who needs to know that the digest
    covers this file alone.
    """
    hashes = ontology.hashes()
    bodies = {
        "o_l1": (ontology.l1, "o_l1_sha256"),
        "o_l2": (ontology.l2, "o_l2_sha256"),
        "m_l1_to_l2": (ontology.map, "m_l1_to_l2_sha256"),
        "decisions": (ontology.ledger, "decisions_sha256"),
        "provenance": (ontology.provenance, "provenance_sha256"),
    }
    model, hash_key = bodies[unit]
    payload = cast(JsonObject, model.model_dump(mode="json"))
    payload["freeze"] = {
        "unit": unit,
        "sha256": hashes[hash_key],
        "hash_scope": (
            "SHA-256 over the canonical JSON of this unit's model only, excluding this "
            "freeze block; a change to any other unit cannot move this digest"
        ),
        "excludes_individuals": True,
        "excludes_benchmark_facts": True,
        "judge_dependency": "none; no model or judge call was made by this build",
    }
    return payload


def _write(path: Path, payload: JsonObject) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def main() -> int:
    # Construction runs every cross-unit check, so a broken ontology fails here rather than
    # reaching disk and being cited.
    ontology = build_foundation_ontology()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for unit in ("o_l1", "o_l2", "m_l1_to_l2", "decisions", "provenance"):
        _write(ARTIFACT_DIR / f"{unit}.json", _unit_payload(ontology, unit))

    print("five independent hashes (no combined ontology hash, by design):")
    for name, digest in ontology.hashes().items():
        print(f"  {name:<20} {digest}")

    counts = ontology.item_counts()
    print(
        f"O_L1 {counts['o_l1_items']} items, O_L2 {counts['o_l2_items']} items, "
        f"map {counts['m_l1_to_l2_entries']} entries"
    )
    print(f"  O_L1 by type: {ontology.l1.counts_by_type()}")
    print(f"  O_L2 by type: {ontology.l2.counts_by_type()}")

    ledger = ontology.ledger
    print(
        f"candidates: {ledger.count(Disposition.ACCEPTED)} accepted, "
        f"{ledger.count(Disposition.REJECTED)} rejected, "
        f"{ledger.count(Disposition.DEFERRED)} deferred"
    )
    print(f"uncovered expressions recorded: {len(ledger.uncovered)}")

    print(f"sources consulted:   {', '.join(ontology.provenance.consulted_names())}")
    print(f"sources unconsulted: {', '.join(ontology.provenance.unconsulted_names())}")

    # Asserted in the output because they are the two properties the plan is strictest about
    # and the two a reader cannot check by eye from a 67-item file.
    shared = sorted(ontology.l1.item_ids & ontology.l2.item_ids)
    print(f"ids shared between layers outside the map: {shared or 'none'}")
    print(f"cross-layer edges declared in M_L1_to_L2: {len(ontology.map.entries)}")
    print("individuals and benchmark facts: excluded structurally; no item can hold a value")
    print("judge dependency: none; no model or judge call was made")
    print(f"artifacts: {ARTIFACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
