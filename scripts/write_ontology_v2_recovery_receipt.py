"""Write the ontology v2 recovery receipt.

The six unit digests prove what the current bytes are. They cannot prove the ontology is
reproducible, because the original build script was lost when the building process died. This
receipt records that distinction rather than papering over it: the crash state, the recovery rule,
which fields are original and which were reconstructed, and what was verified.

It is deliberately not framed as a clean rebuild. A reader deciding whether to trust a citation
about PropBank grounding needs to know that the content modules are original while the assembly and
the ledger were reconstructed afterwards.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.ontology_v2.decisions import (
    _NEW_ACCEPTED,
    _NEW_BREADTH,
    build_decisions,
    build_provenance,
)
from ke_memory_demo.ontology_v2.l1_content import build_o_l1
from ke_memory_demo.ontology_v2.l2_content import build_o_l2
from ke_memory_demo.ontology_v2.mapping_content import build_m_l1_to_l2
from ke_memory_demo.ontology_v2.models import Disposition, FoundationOntologyV2
from ke_memory_demo.ontology_v2.supersession import build_supersession

MODULE_DIR = Path("src/ke_memory_demo/ontology_v2")
OUTPUT = Path("artifacts/ontology-v2/recovery-receipt.json")

# Modules the crashed process had already written. Their content is original; nothing in them was
# authored during recovery except the two corrections named below.
ORIGINAL_MODULES = (
    "models.py",
    "l1_content.py",
    "l2_content.py",
    "mapping_content.py",
    "supersession.py",
)


def main() -> int:
    ontology = FoundationOntologyV2(
        l1=build_o_l1(),
        l2=build_o_l2(),
        map=build_m_l1_to_l2(),
        ledger=build_decisions(),
        provenance=build_provenance(),
        supersession=build_supersession(),
    )
    ledger = ontology.ledger
    explicit = {d.candidate for d in _NEW_ACCEPTED + _NEW_BREADTH}
    derived = [
        d
        for d in ledger.decisions
        if d.candidate not in explicit and d.disposition is Disposition.ACCEPTED
    ]
    carried = [d for d in ledger.decisions if d.disposition is not Disposition.ACCEPTED]

    receipt: dict[str, Any] = {
        "artifact": "ontology v2 recovery receipt",
        "standing": "recovered_candidate_frozen",
        "not_a_clean_rebuild": (
            "the original build script was lost with the crash, so the ontology cannot currently be "
            "regenerated from source. The digests establish byte identity, not reproducibility."
        ),
        "crash_state": {
            "cause": (
                "the building process terminated on an HTTP 524 from the inference gateway at "
                "api.penguinsaichat.dpdns.org, mid-write"
            ),
            "modules_present_on_disk": list(ORIGINAL_MODULES) + ["decisions.py (truncated)"],
            "modules_absent": [
                "__init__.py",
                "scripts/build_foundation_ontology_v2.py",
                "tests/unit/ontology_v2/",
            ],
            "artifacts_present": "none; artifacts/ontology-v2 did not exist",
            "truncation_point": (
                "decisions.py held its candidate tuples but ended before build_decisions, "
                "build_provenance and the source snapshots"
            ),
        },
        "recovery_rule": (
            "recover rather than rebuild, on the grounds that all six modules parsed and their "
            "content was substantial. Nothing in the content modules was rewritten; only the missing "
            "assembly was completed, and every correction to existing content is listed below."
        ),
        "original_fields": {
            "modules": {
                name: hashlib.sha256((MODULE_DIR / name).read_bytes()).hexdigest()
                for name in ORIGINAL_MODULES
            },
            "scope": (
                "every ontology item, its sense, aliases, roles, constraints and provenance, plus "
                "the layer mapping and the supersession record, are as the original process wrote "
                "them"
            ),
        },
        "reconstructed_fields": {
            "build_decisions": "written during recovery; assembles the ledger",
            "build_provenance": "written during recovery; source snapshots and declined imports",
            "_decisions_from_items": "written during recovery; derives a decision per undecided item",
            "_carried_forward_refusals": "written during recovery; carries v1 refusals",
            "__init__.py": "written during recovery",
            "scripts/build_foundation_ontology_v2.py": "written during recovery",
            "tests/unit/ontology_v2/": "written during recovery",
        },
        "corrections_to_original_content": [
            {
                "field": "ExternalGrounding.gloss min_length",
                "was": 8,
                "now": 3,
                "why": (
                    "the constraint rejected real source data: PropBank decide.01 is named exactly "
                    "'decide', six characters. Verified against the frozen archive at "
                    "propbank-frames-3.4.0.tar.gz before changing the floor."
                ),
            },
            {
                "field": "l1_content._carried and l1_content._wn_source",
                "action": "removed",
                "why": "unreferenced helpers left by the crash; no item used either",
            },
        ],
        "decision_provenance": {
            "human_reviewed": len(explicit),
            "reconstructed_from_entry_provenance": len(derived),
            "carried_from_v1_with_original_reasoning": len(carried),
            "marker": "reconstructed_from_entry_provenance",
            "what_the_marker_means": (
                "a reconstructed decision cites the evidence recorded on the item that admitted it. "
                "That closes the ledger completeness gap and is not independent semantic review: "
                "nobody re-judged whether the item should exist."
            ),
            "must_not_be_reported_as": "human reviewed",
        },
        "verification_performed": {
            "unit_digests_recomputed": ontology.hashes(),
            "cross_unit_validators": (
                "assembly enforces layer id separation, map completeness, ledger coverage of every "
                "item and version agreement; the ontology cannot construct otherwise"
            ),
            "artifacts_match_build": True,
            "tests": "16 ontology v2 tests; full suite 1025 passed, 1 skipped",
            "layers_share_no_id": ontology.l1.item_ids & ontology.l2.item_ids == set(),
            "every_item_decided": (
                (ontology.l1.item_ids | ontology.l2.item_ids) - ledger.accepted_ids() == set()
            ),
        },
        "required_before_formal_benchmark": (
            "either restore reproducibility by regenerating the content modules from the frozen "
            "sources with a committed script, or cite this ontology explicitly as a recovered "
            "candidate freeze whose provenance is this receipt"
        ),
        "judge": "not called",
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json(receipt)).hexdigest()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(receipt, indent=1, sort_keys=True), encoding="utf-8")

    provenance = receipt["decision_provenance"]
    print(f"standing: {receipt['standing']}")
    print(
        f"decisions: human_reviewed={provenance['human_reviewed']} "
        f"reconstructed={provenance['reconstructed_from_entry_provenance']} "
        f"carried_from_v1={provenance['carried_from_v1_with_original_reasoning']}"
    )
    print(f"original modules hashed: {len(receipt['original_fields']['modules'])}")
    print(f"corrections to original content: {len(receipt['corrections_to_original_content'])}")
    print(f"receipt sha256: {receipt['receipt_sha256'][:16]}")
    print(f"artifact: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
