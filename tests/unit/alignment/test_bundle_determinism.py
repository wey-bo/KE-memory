"""The byte contract, and the metrics report's refusal to guess.

Determinism is checked the way the specification asks for it: two builds into two fresh
directories, comparing the full file list and every digest, excluding only the run receipt.
Comparing digests alone would miss a file appearing or disappearing.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

from memory_assertion_v1.alignment.canonical_bytes import (
    CanonicalBytesError,
    canonical_bytes,
    digest,
    normalize_text,
)
from memory_assertion_v1.alignment.channels import (
    PROMOTION_RULE_VERSION,
    ProposalChannel,
    VerificationChannel,
    run_channel,
)
from memory_assertion_v1.alignment.decisions import combine
from memory_assertion_v1.alignment.evidence import (
    EvidenceEntry,
    SourceRecordRef,
    make_candidate,
)
from memory_assertion_v1.alignment.pipeline import run_alignment, write_bundle, write_run_receipt
from memory_assertion_v1.alignment.reports import (
    UNMEASURABLE_METRICS,
    IngestionCounts,
    build_metrics,
    summarize_quarantine,
)
from memory_assertion_v1.alignment.source_manifest import (
    PARSER_VERSION,
    SourceArtifact,
    SourceShard,
    build_manifest,
)

DIGEST = "c" * 64


def _ingestion() -> IngestionCounts:
    return IngestionCounts(
        wordnet_sense_count=5,
        wordnet_distinct_lemma_count=5,
        propbank_frame_file_count=4,
        propbank_roleset_occurrence_count=6,
        propbank_unique_roleset_id_count=5,
        propbank_role_count=13,
        schema_org_declared_class_count=5,
        schema_org_declared_property_count=1,
        schema_org_labeled_class_count=3,
        schema_org_labeled_property_count=1,
        schema_org_enumeration_member_count=1,
        schema_org_unlabeled_foreign_stub_count=2,
    )


def _manifest():
    artifact = SourceArtifact(
        source="wordnet",
        logical_name="wordnet-3.0-nltk.zip",
        source_version="3.0",
        artifact_sha256=DIGEST,
        byte_size=1024,
    )
    shard = SourceShard(
        source="wordnet",
        shard_path="source-records/wordnet.json",
        artifact_sha256=DIGEST,
        parser_version=PARSER_VERSION,
        record_count=5,
        shard_sha256=DIGEST,
    )
    return build_manifest((artifact,), (shard,))


def _candidates():
    left = SourceRecordRef(
        source="wordnet", artifact_sha256=DIGEST, member_path="m", native_id="A"
    )
    right = SourceRecordRef(
        source="propbank", artifact_sha256=DIGEST, member_path="m", native_id="B"
    )
    evidence = (
        EvidenceEntry(
            evidence_kind="lexical_match", polarity="context_only", detail="shared form"
        ),
        EvidenceEntry(
            evidence_kind="signature", polarity="context_only", detail="arity 2"
        ),
    )
    return (make_candidate(left, right, "operator", evidence),)


def _build(root: Path) -> dict[str, str]:
    result = run_alignment(_manifest(), _candidates(), {}, _ingestion())
    written = write_bundle(result, root)
    write_run_receipt(root, started_at="2026-08-09T00:00:00Z", dataset_root=str(root))
    return written


def test_two_builds_produce_identical_bundles(tmp_path: Path) -> None:
    """Same inputs, two fresh directories, identical file list and digests."""
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = _build(first_root)
    second = _build(second_root)

    assert sorted(first) == sorted(second)
    assert first == second

    def listing(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name != "run-receipt.json"
        }

    assert listing(first_root) == listing(second_root)


def test_run_receipt_is_the_only_nondeterministic_file(tmp_path: Path) -> None:
    """Build time lives outside the bundle, not as an unhashed field inside it.

    A field excluded from a hash still changes the bytes of its file, which is why the receipt is
    a separate file the comparison skips.
    """
    root = tmp_path / "build"
    _build(root)
    receipt = (root / "run-receipt.json").read_text(encoding="utf-8")
    assert "2026-08-09T00:00:00Z" in receipt

    for path in root.rglob("*.json"):
        if path.name == "run-receipt.json":
            continue
        assert "started_at" not in path.read_text(encoding="utf-8")


def test_build_manifest_records_others_but_not_itself(tmp_path: Path) -> None:
    """The hash graph points one way: a file cannot contain its own digest."""
    root = tmp_path / "build"
    written = _build(root)
    manifest_path = "build-audit/build-manifest.json"
    text = (root / manifest_path).read_text(encoding="utf-8")
    assert written[manifest_path] not in text
    assert written["promotion-bundle.json"] in text


def test_unknown_metrics_stay_unknown(tmp_path: Path) -> None:
    """The metrics this layer cannot measure must not be filled in as zero.

    Zero reads as "checked, none found", which is a stronger claim than this layer supports: no
    Canonical Ontology exists yet, and there is no independent gold set.
    """
    root = tmp_path / "build"
    _build(root)
    text = (root / "build-audit/alignment-metrics.json").read_text(encoding="utf-8")

    expected = {
        "accepted_canonical_concept_count",
        "accepted_canonical_operator_count",
        "canonical_dag_closure",
        "resolved_lexicalization_coverage",
        "duplicate_semantic_identity_rate",
        "false_merge_rate",
    }
    assert set(UNMEASURABLE_METRICS) == expected
    for metric in expected:
        assert f'"{metric}"' in text
        assert f'"{metric}":0' not in text.replace(" ", "")


def test_derived_views_carry_their_authority_digest() -> None:
    """A summary that could not name its source could silently drift from it."""
    candidate = _candidates()[0]
    decision = combine(
        candidate,
        (
            run_channel(ProposalChannel(), candidate, ()),
            run_channel(VerificationChannel(), candidate, ()),
        ),
        PROMOTION_RULE_VERSION,
    )
    summary = summarize_quarantine((decision,), ())
    metrics = build_metrics((decision,), (), _ingestion(), (), reproducibility="unknown")
    assert summary.derived_from_sha256 == metrics.derived_from_sha256
    assert len(summary.derived_from_sha256) == 64


def test_channel_agreement_is_unknown_with_no_candidates() -> None:
    """0/0 is not 0%: an empty run has no agreement rate to report."""
    metrics = build_metrics((), (), _ingestion(), (), reproducibility="unknown")
    assert metrics.channel_agreement_rate == "unknown"


def test_canonical_bytes_applies_nfc_and_sorts_members() -> None:
    """NFC on values and member names, members ordered, output stable."""
    composed = "é"
    decomposed = "é"
    assert normalize_text(decomposed) == composed
    assert digest({"a": decomposed}) == digest({"a": composed})
    assert canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}\n'


def test_canonical_bytes_rejects_non_ijson_numbers() -> None:
    """A value that cannot round-trip cannot be part of a reproducible digest."""
    with pytest.raises(CanonicalBytesError):
        canonical_bytes({"value": math.nan})
    with pytest.raises(CanonicalBytesError):
        canonical_bytes({"value": math.inf})


def test_canonical_bytes_rejects_member_names_colliding_under_nfc() -> None:
    """Two keys differing only by Unicode form are a mistake, not a merge to perform."""
    with pytest.raises(CanonicalBytesError):
        canonical_bytes({"é": 1, "é": 2})
