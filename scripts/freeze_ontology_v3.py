"""Freeze O_v3 as a replayable candidate freeze.

Four units, each hashed over itself alone: O_L1 additions, O_L2 additions, the derivation mapping and
the decision ledger. No combined digest, for the same reason as v2 — one hash says something moved
without saying which unit moved.

Replayability is the property v2 lacked. The generator was committed before this script ran, evidence
is deterministic over fixed corpora with a checked digest, and running this twice produces identical
unit hashes. That is what makes this a freeze rather than a recovery.

O_v2 is untouched. v3 is additive: it declares what it adds and what it supersedes, and the v2
artifacts keep their own digests so any earlier citation stays valid.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.ontology_v3.content import (
    SUPERSEDES,
    V3_VERSION,
    build_items,
    build_l2_additions,
    build_new_roles,
)
from ke_memory_demo.ontology_v3.evidence import collect_all

V2_DIR = Path("artifacts/ontology-v2")
OUTPUT_DIR = Path("artifacts/ontology-v3")

# The v2 digests this freeze builds on. Checked, so a v3 citation names the v2 bytes it extends.
V2_L1_SHA256 = "76465be5ecfed0c988599f3c2dba442af0bc149911d2189bfe8e6f37b47932e9"
V2_L2_SHA256 = "308ba27fc274f4c1b538d70c0166e7ea01ba6c16d92adcb3136b801647c64858"


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _freeze_block(unit: str, digest: str) -> dict[str, Any]:
    return {
        "unit": unit,
        "sha256": digest,
        "hash_scope": (
            "SHA-256 over the canonical JSON of this unit alone, excluding this freeze block; a "
            "change to another unit cannot move this digest"
        ),
        "excludes_individuals": True,
        "excludes_benchmark_facts": True,
        "derived_from_validation_sample": False,
        "judge_dependency": "none; no model or judge call was made by this build",
    }


def main() -> int:
    v2_l1 = json.loads((V2_DIR / "o_l1.json").read_text(encoding="utf-8"))
    v2_l2 = json.loads((V2_DIR / "o_l2.json").read_text(encoding="utf-8"))
    if v2_l1["freeze"]["sha256"] != V2_L1_SHA256:
        print("FAIL: v2 O_L1 digest changed; v3 must extend the bytes it names")
        return 1
    if v2_l2["freeze"]["sha256"] != V2_L2_SHA256:
        print("FAIL: v2 O_L2 digest changed")
        return 1

    families, provenance = collect_all()
    items = build_items(families)
    roles = build_new_roles()
    l2_additions = build_l2_additions()

    v2_l1_ids = {entry["item"]["id"] for entry in v2_l1["items"]}
    v2_l2_ids = {entry["item"]["id"] for entry in v2_l2["items"]}

    # An addition that collides with a v2 id would silently redefine a frozen item.
    collisions = sorted(
        ({item.item_id for item in items} | {str(r["id"]) for r in roles}) & v2_l1_ids
    )
    if collisions:
        print(f"FAIL: v3 additions collide with frozen v2 L1 ids: {collisions}")
        return 1
    l2_collisions = sorted({str(a["id"]) for a in l2_additions} & v2_l2_ids)
    if l2_collisions:
        print(f"FAIL: v3 L2 additions collide with frozen v2 ids: {l2_collisions}")
        return 1

    # Every role an item requires must exist, either in v2 or among the new roles.
    known_roles = v2_l1_ids | {str(r["id"]) for r in roles}
    dangling = sorted(
        {role.role_id for item in items for role in item.roles} - known_roles
    )
    if dangling:
        print(f"FAIL: items reference roles that do not exist: {dangling}")
        return 1

    l1_unit = {
        "unit_id": "O_L1_V3_ADDITIONS",
        "version": V3_VERSION,
        "supersedes": SUPERSEDES,
        "extends_v2_l1_sha256": V2_L1_SHA256,
        "items": [item.as_json() for item in items],
        "new_roles": list(roles),
    }
    l2_unit = {
        "unit_id": "O_L2_V3_ADDITIONS",
        "version": V3_VERSION,
        "extends_v2_l2_sha256": V2_L2_SHA256,
        "items": list(l2_additions),
    }
    mapping_unit = {
        "unit_id": "M_L1_TO_L2_V3_ADDITIONS",
        "version": V3_VERSION,
        "entries": [
            {
                "map_id": f"m3-{index:03d}",
                "l2_target_id": str(addition["id"]),
                "l1_source_ids": list(addition["l1_source_ids"]),
                "evidence_required": int(addition["evidence_required"]),
                "kind": str(addition["kind"]),
                "rule": (
                    "an abstraction is attested when at least evidence_required of its L1 sources "
                    "are attested; fewer yields nothing rather than a weak candidate"
                ),
            }
            for index, addition in enumerate(l2_additions)
        ],
    }
    ledger_unit = {
        "unit_id": "DECISIONS_V3",
        "version": V3_VERSION,
        "families_admitted": [
            {
                "family": family.family,
                "admitted_on": next(
                    (i.admitted_on for i in items if i.evidence_family == family.family),
                    "unknown",
                ),
                "corpus_occurrences": family.total_occurrences,
                "sgd_support_fields": len(family.sgd_support),
                "aliases_used": len(family.aliases),
                "notes": list(family.notes),
            }
            for family in families
        ],
        "families_excluded": [
            {
                "family": "episodic_significance",
                "disposition": "explicit_residual_gap",
                "reason": (
                    "3 of 11 out_of_scope cases is concentration within one sample, not independent "
                    "coverage: 24 MSC sentences and no SGD support"
                ),
                "validation_requirement": (
                    "validate against new corpora covering personal experience, commemorative events "
                    "and object meaning before modelling"
                ),
            },
            {
                "family": "role_play_framing",
                "disposition": "residual_limitation",
                "reason": (
                    "what is missing is an in-fiction source status, a provenance and modality "
                    "concern rather than a concept gap, and no fiction guard was committed to"
                ),
            },
        ],
        "value_and_belief_separation": {
            "enforced": True,
            "why": (
                "a merged item would have to drop either the strength qualifier only values take or "
                "the assertion modality only beliefs take"
            ),
            "value_qualifiers": [
                q for i in items if i.item_id == "l1:predicate.hold_value" for q in i.qualifiers
            ],
            "belief_qualifiers": [
                q for i in items if i.item_id == "l1:predicate.hold_belief" for q in i.qualifiers
            ],
        },
        "evidence_provenance": provenance,
    }

    units = {
        "o_l1_additions.json": ("o_l1_additions", l1_unit),
        "o_l2_additions.json": ("o_l2_additions", l2_unit),
        "m_l1_to_l2_additions.json": ("m_l1_to_l2_additions", mapping_unit),
        "decisions.json": ("decisions", ledger_unit),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for filename, (unit_name, payload) in units.items():
        digest = _digest(payload)
        hashes[f"{unit_name}_sha256"] = digest
        document = dict(payload)
        document["freeze"] = _freeze_block(unit_name, digest)
        (OUTPUT_DIR / filename).write_text(
            json.dumps(document, indent=1, sort_keys=True), encoding="utf-8"
        )

    summary = {
        "ontology_version": V3_VERSION,
        "standing": "replayable_candidate_freeze",
        "supersedes": SUPERSEDES,
        "additive": (
            "v3 adds to v2 rather than replacing it. The v2 artifacts keep their digests, so an "
            "earlier citation stays valid."
        ),
        "hashes": hashes,
        "no_combined_hash": (
            "four independent digests and no combined one, so a change is attributable to a unit"
        ),
        "counts": {
            "new_l1_items": len(items),
            "new_roles": len(roles),
            "new_l2_items": len(l2_additions),
            "new_mapping_entries": len(mapping_unit["entries"]),
        },
        "families": {
            family.family: {
                "occurrences": family.total_occurrences,
                "sgd_support": len(family.sgd_support),
            }
            for family in families
        },
        "replayability": {
            "generator_committed_before_freeze": True,
            "evidence_deterministic": True,
            "corpus_digest_checked": provenance["msc_sha256"],
            "contrast_with_v2": (
                "v2 was a recovered-only freeze whose generator was lost before commit, so its "
                "content could not be regenerated. This one can."
            ),
        },
        "isolation": provenance["isolation"],
        "regression_status": (
            "the 120 validation expressions are exposed regression only. Any v3 conclusion needs a "
            "fresh set, because the gaps were identified from that sample."
        ),
        "independent_blocker": (
            "mapper candidate recall 0.165 and gold-none false mapping 0.633 remain blocking and are "
            "untouched by this freeze"
        ),
        "judge": "not called",
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8"
    )

    print(f"O_v3 {V3_VERSION}, additive over {SUPERSEDES}")
    for key, digest in hashes.items():
        print(f"  {key:<30} {digest[:32]}")
    counts = summary["counts"]
    print(
        f"new: {counts['new_l1_items']} L1 items, {counts['new_roles']} roles, "
        f"{counts['new_l2_items']} L2 items, {counts['new_mapping_entries']} mapping entries"
    )
    for family, data in summary["families"].items():
        print(f"  {family:<30} occ={data['occurrences']:<5} sgd={data['sgd_support']}")
    print(f"artifacts: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
