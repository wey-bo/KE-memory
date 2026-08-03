"""Freeze mapper v3's identity before it is scored, so the run names what produced it.

The artifact answers one question a reader will have when they see the scores: which mapper, over
which ontology, with which configuration. It records no result, no candidate list and no threshold
fitted to anything -- there is nowhere in it to put a number derived from the evaluation set.

Two things are deliberately absent. There is no accuracy figure, because this file is written
before the run. And there is no reference to the fresh set or the gold: this script imports the
mapper and the ontology only, which is checked by the architecture gate rather than left to
review.

The construction inventory *is* recorded, with its discovery-split frequencies. Those frequencies
came from the discovery pool, never from the fresh set, and stating them here is what makes a later
claim of "the mapper was tuned to the evaluation corpus" checkable rather than a matter of trust.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.mapper_v3.constructions import CONSTRUCTION_TO_ITEM_TYPES
from ke_memory_demo.mapper_v3.mapper_v3 import MapperV3

ROOT: Final[Path] = Path(".")
V2_DIR: Final[Path] = ROOT / "artifacts" / "ontology-v2"
V3_DIR: Final[Path] = ROOT / "artifacts" / "ontology-v3"
OUTPUT: Final[Path] = ROOT / "artifacts" / "mapper-v3-validation" / "mapper-freeze.json"

# Measured on the discovery split before the fresh set was drawn. Recorded so a reader can see
# which constructions carry the mapper and which are close to unused.
DISCOVERY_FREQUENCIES: Final[dict[str, float]] = {
    "HABITUAL_ASPECT": 0.210,
    "INTENTION_DECLARATION": 0.200,
    "POSSESSION_CLAIM": 0.041,
    "EVALUATIVE_PREDICATION": 0.022,
    "PAST_EPISODE": 0.015,
}


def main() -> int:
    mapper = MapperV3(v2_dir=V2_DIR, v3_dir=V3_DIR)

    payload: dict[str, Any] = {
        "artifact": "mapper v3 freeze",
        "standing": "frozen_before_being_scored",
        "identity": dict(mapper.identity),
        "freeze_hash": mapper.freeze_hash(),
        "design": {
            "frames_per_expression": (
                "0..N. An utterance attesting two unrelated things yields two frames and two "
                "targets; mapper v2 returned a single best guess, which is why its recall on "
                "multi-topic turns was 0.165"
            ),
            "targets_match_frames": (
                "len(target_ids) == len(frames), enforced by the result model. A target without "
                "its frame has no evidence behind it"
            ),
            "abstention_is_reasoned": (
                "unresolved carries one of no_content, request_only or no_admissible_evidence. "
                "None of the three is a score below a cutoff: five v2 calibration attempts moved "
                "its abstention rate between 0.000 and 0.998 without the number ever meaning "
                "anything, and a stated reason cannot drift that way"
            ),
            "constructions_map_to_item_types": (
                "a construction licenses an item *type*, never a specific item id. Binding syntax "
                "to ids would let the ontology's naming leak into the evidence"
            ),
            "evidence_excludes_namespace_words": (
                "only an id's leaf segment contributes decisive words, minus namespace words such "
                "as role, predicate and time. Without that exclusion 'time' alone matched seven "
                "items and 680 of 1500 discovery turns hit the frame cap"
            ),
        },
        "inputs_read": {
            "ontology_v2": sorted(p.name for p in V2_DIR.glob("*.json")),
            "ontology_v3": sorted(p.name for p in V3_DIR.glob("*.json")),
            "corpus": "discovery split only; the fresh mapping set was never read",
        },
        "constructions": {
            name: sorted(item_types)
            for name, item_types in sorted(CONSTRUCTION_TO_ITEM_TYPES.items())
        },
        "construction_count": len(CONSTRUCTION_TO_ITEM_TYPES),
        "discovery_split_frequencies": DISCOVERY_FREQUENCIES,
        "frequencies_provenance": (
            "measured on the discovery pool before the fresh set was drawn; no frequency here was "
            "computed over the evaluation corpus"
        ),
        "contains_no_result": (
            "written before the run. There is no field for a score, a candidate list or a "
            "threshold fitted to the evaluation set"
        ),
    }
    payload["artifact_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    print(f"mapper: {payload['identity']['mapper_id']} {payload['identity']['mapper_version']}")
    print(f"freeze hash: {payload['freeze_hash']}")
    print(f"constructions: {payload['construction_count']}")
    print(f"artifact sha256: {payload['artifact_sha256']}")
    print(f"artifact: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
