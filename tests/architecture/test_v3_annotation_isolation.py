"""Architecture gate for the v3 annotation line.

The claim this round rests on is that the gold was decided without the mapper. Part of that claim
is checkable and part is not, and the value of these tests lies in keeping the two apart.

Checkable, and checked here:

- The annotation package imports no mapper module, directly or transitively. Import-time isolation
  is what stops a future edit from indexing gold against mapper aliases while looking reasonable in
  review.
- The mapper package references neither the fresh set nor the gold, by import or by path string. A
  path literal is enough to read a file, so a grep for the artifact names is part of the gate.
- The gold artifact on disk matches the labels in the package, and its recorded digest recomputes.

Not checkable, and deliberately asserted as a limitation rather than as a pass: the annotator's own
independence. Both halves of the gold were written while mapper v3 already existed in this working
tree, so no timestamp ordering can establish that no mapper output was read. The artifact records
that as ``procedural_declaration_not_artifact_proof`` and the last test here pins that wording, so
a later reader cannot mistake the import gate for proof of the stronger claim.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "ke_memory_demo"
ANNOTATION_PACKAGE = PACKAGE_ROOT / "mapper_v3_validation"
MAPPER_PACKAGE = PACKAGE_ROOT / "mapper_v3"
GOLD_ARTIFACT = REPOSITORY_ROOT / "artifacts" / "mapper-v3-validation" / "annotation-gold.json"

# Artefact names the mapper must not be able to reach. Checked as substrings of the source text,
# not as imports, because opening a path literal needs no import at all.
FORBIDDEN_PATH_FRAGMENTS = (
    "fresh-mapping-set",
    "annotation-gold",
    "mapper_v3_validation",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _load_gold_payload() -> dict[str, object]:
    payload: object = json.loads(GOLD_ARTIFACT.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast("dict[str, object]", payload)


def _obj(payload: dict[str, object], key: str) -> dict[str, object]:
    """Fetch a nested object, narrowing it so the assertions below are typed rather than Any."""
    value = payload[key]
    assert isinstance(value, dict), f"{key} is not a JSON object"
    return cast("dict[str, object]", value)


def _entries(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload[key]
    assert isinstance(value, list), f"{key} is not a JSON array"
    entries: list[dict[str, object]] = []
    for entry in cast("list[object]", value):
        assert isinstance(entry, dict), f"an entry of {key} is not a JSON object"
        entries.append(cast("dict[str, object]", entry))
    return entries


def _text(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    assert isinstance(value, str), f"{key} is not a string"
    return value


def test_annotation_package_imports_no_mapper_module() -> None:
    offenders: list[str] = []
    for source in sorted(ANNOTATION_PACKAGE.rglob("*.py")):
        for imported in _imported_modules(source):
            if "mapper_v1" in imported or "mapper_v2" in imported or "mapper_v3" in imported:
                # Its own package is not a mapper import.
                if imported.startswith("ke_memory_demo.mapper_v3_validation"):
                    continue
                offenders.append(f"{source.relative_to(REPOSITORY_ROOT)} imports {imported}")
    assert offenders == [], (
        "the annotation line must not import a mapper; a gold set that can reach the mapper it "
        "scores stops being independent evidence: " + "; ".join(offenders)
    )


def test_mapper_package_cannot_reach_the_set_or_the_gold() -> None:
    """Neither by import nor by path literal."""
    offenders: list[str] = []
    for source in sorted(MAPPER_PACKAGE.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for fragment in FORBIDDEN_PATH_FRAGMENTS:
            if fragment in text:
                offenders.append(f"{source.relative_to(REPOSITORY_ROOT)} mentions {fragment!r}")
    assert offenders == [], (
        "mapper v3 must not name the evaluation set or the gold; a path literal is enough to read "
        "one: " + "; ".join(offenders)
    )


def test_importing_the_annotation_package_loads_no_mapper() -> None:
    """Transitive isolation, checked in a fresh interpreter rather than by reading imports."""
    probe = (
        "import sys\n"
        "import ke_memory_demo.mapper_v3_validation.annotations\n"
        "leaked = sorted(m for m in sys.modules if '.mapper_v3.' in m + '.'"
        " or m.endswith('.mapper_v3'))\n"
        "print(','.join(leaked))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPOSITORY_ROOT,
        env={
            "PYTHONPATH": ":".join(
                str(REPOSITORY_ROOT / part) for part in ("src", "service", "ontology")
            ),
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"importing the gold loaded mapper modules: {result.stdout.strip()}"
    )


def test_gold_artifact_matches_the_labels_in_the_package() -> None:
    from ke_memory_demo.mapper_v3_validation.annotations import build_annotation_gold

    gold = build_annotation_gold()
    payload = _load_gold_payload()
    records = _entries(payload, "records")
    assert len(records) == len(gold.records) == 160
    on_disk = [_text(record, "expression_id") for record in records]
    in_package = [record.expression_id for record in gold.records]
    assert on_disk == in_package, "the frozen artifact and the labels have diverged"


def test_gold_artifact_digest_recomputes() -> None:
    from ke_memory_demo.core.json import JsonObject, canonical_json

    payload = _load_gold_payload()
    recorded = payload.pop("gold_sha256")
    # The digest is taken over the payload minus the digest field, which is what makes the freeze
    # replayable; the cast carries the guarantee json.loads already established.
    remaining = cast("JsonObject", payload)
    assert hashlib.sha256(canonical_json(remaining)).hexdigest() == recorded, (
        "the gold artifact's digest does not match its content, so the freeze is not replayable"
    )


def test_gold_is_bound_to_the_set_digest_it_annotated() -> None:
    from ke_memory_demo.mapper_v3_validation.loader import mapping_set_digest

    payload = _load_gold_payload()
    assert _text(payload, "annotated_set_sha256") == mapping_set_digest(REPOSITORY_ROOT)


def test_zero_ambiguous_records_is_recorded_as_an_unavailable_metric() -> None:
    """The absence must travel with the gold, not be rediscovered from the distribution."""
    payload = _load_gold_payload()
    assert _obj(payload, "counts_by_outcome")["ambiguous"] == 0

    abstention = _obj(_obj(payload, "evaluation_limits"), "true_ambiguity_abstention")
    assert abstention["status"] == "unavailable"
    assert len(_text(abstention, "reason")) > 40
    assert "not_backfilled" in abstention, (
        "the gold must state that ambiguous records were not manufactured to give the metric a "
        "denominator"
    )


def test_isolation_limit_is_stated_as_declaration_not_proof() -> None:
    """The gate above proves import isolation. It does not prove the annotator's independence."""
    limit = _obj(_load_gold_payload(), "isolation_limit")
    assert limit["evidence_strength"] == "procedural_declaration_not_artifact_proof", (
        "overstating the isolation evidence is the failure this test exists to prevent"
    )


def test_known_ontology_gaps_are_accounted_without_touching_a_frozen_unit() -> None:
    accounted = _entries(_load_gold_payload(), "known_ontology_gaps_accounted")
    assert len(accounted) == 3
    for entry in accounted:
        assert _text(entry, "disposition").startswith("accounted, not fixed")
        assert _text(entry, "observed_at")


def test_unattested_v3_addition_is_filed_separately_from_gaps() -> None:
    """A v3 item the fresh corpus never licensed is neither a gap nor a mapper failure."""
    payload = _load_gold_payload()
    unattested = _entries(payload, "unattested_v3_additions")
    assert len(unattested) == 1
    entry = unattested[0]
    assert entry["item"] == "l2:abstraction.value_commitment"
    assert entry["kind"] == "addition_the_fresh_evidence_does_not_license"
    assert "not_evidence_of" in entry, (
        "the entry must say what it does not prove, or a reader will read it as either an "
        "ontology defect or a mapper defect"
    )
    # The temptation this records a refusal of: lowering evidence_required to earn a label.
    assert "tuning the ontology to the evaluation set" in _text(entry, "disposition")

    gap_units = {_text(gap, "unit") for gap in _entries(payload, "known_ontology_gaps_accounted")}
    assert "O_v3" not in gap_units, "the unattested addition must not be double-filed as a gap"
