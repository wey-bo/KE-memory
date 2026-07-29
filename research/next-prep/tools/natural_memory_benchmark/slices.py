from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .ledger import build_external_results_ledger, validate_external_results_ledger
from .loaders import (
    BEAM_OFFICIAL_URL,
    BEAM_SOURCE_ID,
    LOCOMO_OFFICIAL_URL,
    LOCOMO_SOURCE_ID,
    LONGMEM_OFFICIAL_URL,
    LONGMEM_SOURCE_ID,
    load_beam_candidates,
    load_locomo_candidates,
    load_longmemeval_candidates,
)
from .models import (
    ExternalResultsLedger,
    NaturalBenchmarkCandidate,
    PublicSliceArtifact,
    SliceBundle,
    SourceArtifact,
    SourceManifest,
)


SOURCE_SPECS = (
    {
        "benchmark": "beam",
        "source_id": BEAM_SOURCE_ID,
        "official_url": BEAM_OFFICIAL_URL,
        "frozen_identity": "3205395e897e7318c7b094ef4e6047b9b82dbb03|c0519be25907005ba873c927c50877471d550873039d96c041554d0075a78ace",
        "relative_path": Path("raw") / "beam" / "100K-00000-of-00001.parquet",
        "reader": "duckdb",
    },
    {
        "benchmark": "locomo",
        "source_id": LOCOMO_SOURCE_ID,
        "official_url": LOCOMO_OFFICIAL_URL,
        "frozen_identity": "cbfbc1dba6bc53d00625212a0f22d55ffee7c1fc|d95b872480b413d935821fdc3c84f8a8f5f29e73",
        "relative_path": Path("raw") / "locomo" / "locomo10.json",
        "reader": "json",
    },
    {
        "benchmark": "longmemeval",
        "source_id": LONGMEM_SOURCE_ID,
        "official_url": LONGMEM_OFFICIAL_URL,
        "frozen_identity": "98d7416c24c778c2fee6e6f3006e7a073259d48f|821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c",
        "relative_path": Path("raw") / "longmemeval" / "longmemeval_oracle.json",
        "reader": "json",
    },
)

SLICE_V1_QUOTAS: dict[str, dict[str, int]] = {
    "beam": {
        "abstention": 2,
        "contradiction_resolution": 2,
        "knowledge_update": 2,
        "multi_session_reasoning": 2,
        "temporal_reasoning": 2,
    },
    "locomo": {
        "1": 2,
        "2": 2,
        "3": 2,
        "4": 2,
        "5": 2,
    },
    "longmemeval": {
        "temporal-reasoning": 2,
        "multi-session": 2,
        "knowledge-update": 2,
        "single-session-user": 2,
        "single-session-assistant": 2,
        "single-session-preference": 2,
    },
}

BENCHMARK_ORDER = ("beam", "locomo", "longmemeval")


def build_source_manifest(raw_root: Path) -> SourceManifest:
    sources = []
    for spec in SOURCE_SPECS:
        path = raw_root / spec["relative_path"]
        if not path.exists():
            raise FileNotFoundError(f"missing raw source: {path}")
        sources.append(
            SourceArtifact(
                benchmark=spec["benchmark"],
                source_id=spec["source_id"],
                official_url=spec["official_url"],
                frozen_identity=spec["frozen_identity"],
                local_path=path.as_posix(),
                reader=spec["reader"],
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return SourceManifest(sources=sources)


def _select_group(candidates: list[NaturalBenchmarkCandidate], quotas: Mapping[str, int]) -> list[NaturalBenchmarkCandidate]:
    selected: list[NaturalBenchmarkCandidate] = []
    for group, quota in quotas.items():
        group_candidates = [candidate for candidate in candidates if candidate.slice_group == group]
        group_candidates.sort(key=lambda candidate: (candidate.source_index, candidate.item_id))
        if len(group_candidates) < quota:
            raise ValueError(f"slice quota for {group} exceeds available candidates")
        selected.extend(group_candidates[:quota])
    return selected


def build_slice_v1(
    candidates_by_benchmark: Mapping[str, list[NaturalBenchmarkCandidate]],
    *,
    source_manifest_sha256: str = "0" * 64,
) -> SliceBundle:
    public_items: list[dict[str, Any]] = []
    gold_items: list[dict[str, Any]] = []
    selected_by_benchmark: dict[str, list[NaturalBenchmarkCandidate]] = {}
    for benchmark in BENCHMARK_ORDER:
        selected = _select_group(candidates_by_benchmark[benchmark], SLICE_V1_QUOTAS[benchmark])
        selected_by_benchmark[benchmark] = selected
        public_items.extend(candidate.public_item() for candidate in selected)
        gold_items.extend(candidate.gold_item() for candidate in selected)
    return SliceBundle(
        slice_id="slice-v1",
        source_manifest_sha256=source_manifest_sha256,
        selection_policy={
            "benchmark_order": list(BENCHMARK_ORDER),
            "quotas": {benchmark: dict(quotas) for benchmark, quotas in SLICE_V1_QUOTAS.items()},
        },
        public_items=public_items,
        gold_items=gold_items,
    )


def _load_all_candidates(raw_root: Path) -> dict[str, list[NaturalBenchmarkCandidate]]:
    return {
        "beam": load_beam_candidates(raw_root / "raw" / "beam" / "100K-00000-of-00001.parquet"),
        "locomo": load_locomo_candidates(raw_root / "raw" / "locomo" / "locomo10.json"),
        "longmemeval": load_longmemeval_candidates(raw_root / "raw" / "longmemeval" / "longmemeval_oracle.json"),
    }


def freeze_slice_bundle(raw_root: Path, output_root: Path, slice_id: str = "slice-v1") -> dict[str, Any]:
    if slice_id != "slice-v1":
        raise ValueError("slice v1 is the only frozen slice in this stage")
    source_manifest = build_source_manifest(raw_root)
    source_manifest_path = output_root / "source-manifest.json"
    write_json_immutable(source_manifest_path, source_manifest)
    manifest_sha256 = sha256_file(source_manifest_path)
    candidates_by_benchmark = _load_all_candidates(raw_root)
    bundle = build_slice_v1(candidates_by_benchmark, source_manifest_sha256=manifest_sha256)
    public_artifact = PublicSliceArtifact(
        slice_id=slice_id,
        source_manifest_sha256=manifest_sha256,
        selection_policy=bundle.selection_policy,
        public_items=bundle.public_items,
    )
    slice_dir = output_root / slice_id
    write_json_immutable(slice_dir / "slice.json", public_artifact)
    write_json_immutable(slice_dir / "gold.json", {"schema_version": "natural-benchmark-gold-v1", "slice_id": slice_id, "source_manifest_sha256": manifest_sha256, "items": bundle.gold_items})
    ledger = build_external_results_ledger()
    write_json_immutable(output_root / "external-results-ledger.json", ledger)
    return {
        "status": "frozen",
        "slice_id": slice_id,
        "source_manifest_sha256": manifest_sha256,
        "public_item_count": len(bundle.public_items),
        "gold_item_count": len(bundle.gold_items),
    }


def validate_slice_bundle(root: Path, slice_id: str = "slice-v1") -> dict[str, Any]:
    if slice_id != "slice-v1":
        raise ValueError("slice v1 is the only frozen slice in this stage")
    source_manifest_path = root / "source-manifest.json"
    slice_path = root / slice_id / "slice.json"
    gold_path = root / slice_id / "gold.json"
    ledger_path = root / "external-results-ledger.json"
    source_manifest = SourceManifest.model_validate(load_json(source_manifest_path))
    if sha256_file(source_manifest_path) != load_json(slice_path).get("source_manifest_sha256"):
        raise ValueError("slice source_manifest_sha256 mismatch")
    if sha256_file(source_manifest_path) != load_json(gold_path).get("source_manifest_sha256"):
        raise ValueError("gold source_manifest_sha256 mismatch")
    public_bundle = PublicSliceArtifact.model_validate(load_json(slice_path))
    gold_bundle = load_json(gold_path)
    ledger = validate_external_results_ledger(ledger_path)
    if public_bundle.slice_id != slice_id:
        raise ValueError("slice_id mismatch")
    if len(public_bundle.public_items) != 32 or len(gold_bundle["items"]) != 32:
        raise ValueError("slice v1 must contain 32 items")
    if [item["item_id"] for item in public_bundle.public_items] != [item["item_id"] for item in gold_bundle["items"]]:
        raise ValueError("public slice and gold item ordering diverge")
    public_item_keys = {
        "benchmark",
        "item_id",
        "source_id",
        "source_index",
        "source_ref",
        "question",
        "slice_group",
        "category",
        "metadata",
    }
    for item in public_bundle.public_items:
        if not public_item_keys.issuperset(item):
            raise ValueError("slice item contains an unexpected field")
        if "answer" in item or "evidence_refs" in item or "answer_policy" in item:
            raise ValueError("slice item leaked gold fields")
    if any(
        item["benchmark"] == "locomo" and item["answer_policy"] != "manual_required"
        for item in gold_bundle["items"]
        if item["category"] == 5
    ):
        raise ValueError("LoCoMo category 5 must remain manual_required")
    return {
        "status": "valid",
        "slice_id": slice_id,
        "source_manifest_sha256": sha256_file(source_manifest_path),
        "public_item_count": len(public_bundle.public_items),
        "gold_item_count": len(gold_bundle["items"]),
        "ledger_entries": len(ledger.entries),
    }
