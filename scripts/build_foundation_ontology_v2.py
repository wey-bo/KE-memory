"""Build and freeze foundation ontology v2 from the frozen external sources.

Six units, each hashed over itself alone. There is deliberately no combined ontology digest: a
single hash tells an auditor that something moved without saying which unit moved, so re-freezing
O_L1 would appear to invalidate a citation about the map.

Assembly is where the guarantees are enforced. ``FoundationOntologyV2`` refuses to construct if the
two layers share an id outside the map, if the ledger accepts an item no unit contains, or if any
item entered a layer without a decision — so a defective ontology fails here rather than reaching
disk to be cited.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ke_memory_demo.ontology_v2.decisions import (
    ONTOLOGY_VERSION,
    build_decisions,
    build_provenance,
)
from ke_memory_demo.ontology_v2.l1_content import build_o_l1
from ke_memory_demo.ontology_v2.l2_content import build_o_l2
from ke_memory_demo.ontology_v2.mapping_content import build_m_l1_to_l2
from ke_memory_demo.ontology_v2.models import Disposition, FoundationOntologyV2
from ke_memory_demo.ontology_v2.supersession import build_supersession

OUTPUT_DIR = Path("artifacts/ontology-v2")


def _write(path: Path, payload: Any, unit: str, digest: str) -> None:
    """Write one unit with its own freeze block attached."""
    body = payload.model_dump(mode="json")
    body["freeze"] = {
        "unit": unit,
        "sha256": digest,
        "hash_scope": (
            "SHA-256 over the canonical JSON of this unit's model alone, excluding this freeze "
            "block; a change to another unit cannot move this digest"
        ),
        "excludes_individuals": True,
        "excludes_benchmark_facts": True,
        "judge_dependency": "none; no model or judge call was made by this build",
    }
    path.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")


def main() -> int:
    ontology = FoundationOntologyV2(
        l1=build_o_l1(),
        l2=build_o_l2(),
        map=build_m_l1_to_l2(),
        ledger=build_decisions(),
        provenance=build_provenance(),
        supersession=build_supersession(),
    )
    hashes = ontology.hashes()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, payload, unit, key in (
        ("o_l1.json", ontology.l1, "o_l1", "o_l1_sha256"),
        ("o_l2.json", ontology.l2, "o_l2", "o_l2_sha256"),
        ("m_l1_to_l2.json", ontology.map, "m_l1_to_l2", "m_l1_to_l2_sha256"),
        ("decisions.json", ontology.ledger, "decisions", "decisions_sha256"),
        ("provenance.json", ontology.provenance, "provenance", "provenance_sha256"),
        ("supersession.json", ontology.supersession, "supersession", "supersession_sha256"),
    ):
        _write(OUTPUT_DIR / filename, payload, unit, hashes[key])

    ledger = ontology.ledger
    summary: dict[str, Any] = {
        "ontology_version": ONTOLOGY_VERSION,
        "supersedes": ontology.provenance.supersedes,
        "hashes": hashes,
        "no_combined_hash": (
            "six independent digests and no combined one, so a change is attributable to a unit"
        ),
        "counts": {
            "o_l1_items": len(ontology.l1.items),
            "o_l2_items": len(ontology.l2.items),
            "map_entries": len(ontology.map.entries),
            "decisions": len(ledger.decisions),
            "accepted": ledger.count(Disposition.ACCEPTED),
            "rejected": ledger.count(Disposition.REJECTED),
            "deferred": ledger.count(Disposition.DEFERRED),
            "uncovered_expressions": len(ledger.uncovered),
        },
        "v1_deferrals_resolved": list(ledger.resolved_v1_deferrals()),
        "sources_consulted": [
            s.name for s in ontology.provenance.sources if s.consulted
        ],
        "declined_imports": list(ontology.provenance.declined_imports),
        "standing": (
            "the published sources are consulted rather than approximated, so breadth is no longer "
            "limited by provenance. It remains a curation result: the layers grew from 67 and 20 "
            "items to their current size by admitting what common memory situations need, not by "
            "importing what the sources contain."
        ),
        "judge": "not called",
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8"
    )

    print(f"foundation ontology v{ONTOLOGY_VERSION}, superseding {summary['supersedes']}")
    for key, digest in hashes.items():
        print(f"  {key:<22} {digest}")
    counts = summary["counts"]
    print(
        f"O_L1 {counts['o_l1_items']} items | O_L2 {counts['o_l2_items']} items | "
        f"map {counts['map_entries']} entries"
    )
    print(
        f"decisions {counts['decisions']}: accepted {counts['accepted']}, "
        f"rejected {counts['rejected']}, deferred {counts['deferred']}"
    )
    print(f"v1 deferrals resolved: {len(summary['v1_deferrals_resolved'])}")
    print(f"uncovered expressions still recorded: {counts['uncovered_expressions']}")
    print(f"artifacts: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
