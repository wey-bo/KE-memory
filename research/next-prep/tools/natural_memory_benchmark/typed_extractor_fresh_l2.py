from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frozen_input_guard import require_frozen_input
from .extraction_bridge_assessment import (
    ExtractionCompatibilityLedger,
    replay_extraction_inputs,
)
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_fresh_l1 import (
    _lifecycle,
    _opaque_ref,
    _operations,
    _speaker,
)
from .typed_extractor_fresh_prereg import TypedExtractorFreshPreregistration
from .typed_extractor_l1 import PublicEvidenceSpan, PublicUntypedCandidate
from .typed_extractor_l1 import TypedEvidenceBinding
from .typed_extractor_l2 import (
    L2AuthorityCase,
    L2AuthorityPayload,
    L2GoldItem,
    L2GoldPayload,
    L2Manifest,
    L2PublicCase,
    L2PublicPayload,
    L2PublicTurn,
    L2SourceConfig,
    L2_DEV_THRESHOLDS,
    _ALLOWED_VOCABULARY,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FreshL2SourceCase(StrictModel):
    private_case_id: str = Field(pattern=r"^private-[0-9a-f]{16}$")
    case_id: str = Field(pattern=r"^case-[0-9a-f]{16}$")
    candidate_ref: str = Field(pattern=r"^candidate-[0-9a-f]{16}$")
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_session_ref: str = Field(pattern=r"^session-[0-9a-f]{16}$")
    source_turn_refs: list[str] = Field(min_length=2)
    source_turns: list[L2PublicTurn] = Field(min_length=2)
    evidence_ids: list[str] = Field(min_length=2)
    untyped_candidate: PublicUntypedCandidate

    @model_validator(mode="after")
    def validate_source_closure(self) -> "FreshL2SourceCase":
        if self.source_turn_refs != [turn.source_turn_ref for turn in self.source_turns]:
            raise ValueError("fresh L2 source turn refs do not match source turns")
        if self.evidence_ids != [
            item.evidence_id for item in self.untyped_candidate.evidence
        ]:
            raise ValueError("fresh L2 evidence IDs do not match untyped candidate")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("duplicate fresh L2 evidence ID")
        return self


class FreshL2SourcePayload(StrictModel):
    schema_version: Literal["typed-extractor-fresh-l2-source-v1"] = (
        "typed-extractor-fresh-l2-source-v1"
    )
    dataset_id: Literal["typed-extractor-v2-fresh-hidden-v1-l2"] = (
        "typed-extractor-v2-fresh-hidden-v1-l2"
    )
    namespace: Literal["typed-extractor-l2-fresh-hidden-v1:2026-07-28"] = (
        "typed-extractor-l2-fresh-hidden-v1:2026-07-28"
    )
    selection_policy: Literal["all_unused_bridge_v3_cross_turn"] = (
        "all_unused_bridge_v3_cross_turn"
    )
    selection_phase: Literal["frozen_before_gold"] = "frozen_before_gold"
    semantic_filtering_applied: Literal[False] = False
    case_count: Literal[8] = 8
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[FreshL2SourceCase]

    @model_validator(mode="after")
    def validate_selection(self) -> "FreshL2SourcePayload":
        if len(self.cases) != self.case_count:
            raise ValueError("fresh L2 source case count mismatch")
        for field in ("private_case_id", "case_id", "candidate_ref", "knowledge_id"):
            values = [getattr(case, field) for case in self.cases]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate fresh L2 {field}")
        expected_order = sorted(
            self.cases,
            key=lambda case: hashlib.sha256(
                f"{self.namespace}{case.knowledge_id}".encode()
            ).hexdigest(),
        )
        if self.cases != expected_order:
            raise ValueError("fresh L2 cases are not in namespace hash order")
        for case in self.cases:
            expected = hashlib.sha256(
                f"{self.namespace}{case.knowledge_id}".encode()
            ).hexdigest()
            if case.selection_sha256 != expected:
                raise ValueError("fresh L2 selection hash mismatch")
        return self


def _require_read_only(path: Path, label: str) -> None:
    """Verify a committed input portably.

    Content-based rather than mode-based: git records only the executable bit, so
    a 0444 input arrives as 0644 and a mode precondition rejects correct files on
    every fresh clone. Mode is retained only for freshly written output -- see
    ``frozen_input_guard``.
    """
    require_frozen_input(path, label)


def _selection_hash(namespace: str, knowledge_id: str) -> str:
    return hashlib.sha256(f"{namespace}{knowledge_id}".encode()).hexdigest()


def _verify_preregistration_inputs(
    preregistration_path: Path,
    preregistration: TypedExtractorFreshPreregistration,
    *,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
) -> None:
    _require_read_only(preregistration_path, "fresh preregistration")
    paths = {
        "bridge-v3/compatibility-ledger.json": bridge_ledger_path,
        "l2/source-cases-l2.json": l2_dev_root / "source-cases-l2.json",
        "l2/public-l2.json": l2_dev_root / "public-l2.json",
        "source/KE-test.json": source_path,
        "source/turn-manifest.json": turn_manifest_path,
        "source/dialogue-manifest.json": dialogue_manifest_path,
        "source/final-knowledge.json": final_knowledge_path,
        "source/run.json": run_path,
        "source/source-segments.json": source_segments_path,
    }
    for name, path in paths.items():
        expected = preregistration.input_sha256.get(name)
        if expected is None or sha256_file(path) != expected:
            raise ValueError(f"fresh preregistration input drift: {name}")


def _build_source(
    *,
    preregistration_path: Path,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
) -> FreshL2SourcePayload:
    preregistration = TypedExtractorFreshPreregistration.model_validate(
        load_json(preregistration_path)
    )
    _verify_preregistration_inputs(
        preregistration_path,
        preregistration,
        bridge_ledger_path=bridge_ledger_path,
        l2_dev_root=l2_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    namespace = preregistration.selection.l2_namespace
    ledger = ExtractionCompatibilityLedger.model_validate(load_json(bridge_ledger_path))
    replay = replay_extraction_inputs(
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    dev = load_json(l2_dev_root / "source-cases-l2.json")
    dev_ids = {str(case["knowledge_id"]) for case in dev["cases"]}
    envelopes = [
        envelope
        for envelope in ledger.envelopes
        if envelope.candidate_level == "l2_cross_turn_candidate"
        and envelope.knowledge_id not in dev_ids
    ]
    envelopes.sort(key=lambda item: _selection_hash(namespace, item.knowledge_id))
    if len(envelopes) != preregistration.selection.l2_case_count:
        raise ValueError("fresh L2 all-unused selection count mismatch")

    cases: list[FreshL2SourceCase] = []
    for envelope in envelopes:
        record = replay.view.by_id.get(envelope.knowledge_id)
        if record is None:
            raise ValueError("fresh L2 bridge record is missing from replay")
        evidence_turns = sorted(
            {int(item["turn_index"]) for item in record.knowledge["evidence"]}
        )
        if len(evidence_turns) < 2:
            raise ValueError("fresh L2 source must span at least two turns")
        turn_refs = [
            _opaque_ref("turn", namespace, f"{record.candidate_id}:{turn_index}")
            for turn_index in evidence_turns
        ]
        evidence = [
            PublicEvidenceSpan(
                evidence_id=str(item["evidence_id"]),
                speaker=_speaker(str(item["message"]), str(item["evidence_role"])),
                message=item["message"],
                quote=item["quote"],
                occurrence_index=item["occurrence_index"],
                start=item["start"],
                end=item["end"],
            )
            for item in sorted(
                record.knowledge["evidence"], key=lambda item: str(item["evidence_id"])
            )
        ]
        selection_hash = _selection_hash(namespace, record.knowledge_id)
        cases.append(
            FreshL2SourceCase(
                private_case_id=f"private-{selection_hash[:16]}",
                case_id=_opaque_ref("case", namespace, record.knowledge_id),
                candidate_ref=_opaque_ref("candidate", namespace, record.knowledge_id),
                knowledge_id=record.knowledge_id,
                candidate_id=record.candidate_id,
                selection_sha256=selection_hash,
                source_session_ref=_opaque_ref(
                    "session", namespace, record.candidate_id
                ),
                source_turn_refs=turn_refs,
                source_turns=[
                    L2PublicTurn(
                        source_turn_ref=turn_ref,
                        turn_index=turn_index,
                        user=replay.source_turns[(record.candidate_id, turn_index)].user,
                        agent=replay.source_turns[(record.candidate_id, turn_index)].agent,
                    )
                    for turn_ref, turn_index in zip(turn_refs, evidence_turns, strict=True)
                ],
                evidence_ids=[item.evidence_id for item in evidence],
                untyped_candidate=PublicUntypedCandidate(
                    statement=record.knowledge["statement"],
                    subject=record.knowledge["subject"],
                    predicate=record.knowledge["predicate"],
                    object=record.knowledge["object"],
                    qualifiers=record.knowledge["qualifiers"],
                    source_status=record.knowledge["source_status"],
                    derivation=record.knowledge["derivation"],
                    inference_basis=record.knowledge.get("inference_basis"),
                    projection_status=record.status,
                    lifecycle_links=_lifecycle(record, namespace),
                    operation_provenance=_operations(record, namespace),
                    evidence=evidence,
                ),
            )
        )
    return FreshL2SourcePayload(
        preregistration_sha256=sha256_file(preregistration_path),
        cases=cases,
    )


def _resolve_paths(**paths: Path) -> dict[str, Path]:
    return {name: path.resolve() for name, path in paths.items()}


def freeze_fresh_l2_selection(
    *,
    preregistration_path: Path,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    paths = _resolve_paths(
        preregistration_path=preregistration_path,
        bridge_ledger_path=bridge_ledger_path,
        l2_dev_root=l2_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    source = _build_source(**paths)
    output_path = output_root.resolve() / "source-cases-l2.json"
    write_json_immutable(output_path, source)
    output_path.chmod(0o444)
    return {
        "status": "valid",
        "case_count": source.case_count,
        "selection_phase": source.selection_phase,
    }


def validate_fresh_l2_selection(
    *,
    preregistration_path: Path,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    root: Path,
) -> dict[str, Any]:
    paths = _resolve_paths(
        preregistration_path=preregistration_path,
        bridge_ledger_path=bridge_ledger_path,
        l2_dev_root=l2_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
    )
    expected = _build_source(**paths)
    output_path = root.resolve() / "source-cases-l2.json"
    _require_read_only(output_path, "fresh L2 source selection")
    actual = FreshL2SourcePayload.model_validate(load_json(output_path))
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("fresh L2 source selection drift")
    return {
        "status": "valid",
        "case_count": actual.case_count,
        "selection_phase": actual.selection_phase,
    }


def _build_final_artifacts(
    source: FreshL2SourcePayload,
    adjudications: L2SourceConfig,
    records: dict[str, Any],
) -> tuple[L2PublicPayload, L2AuthorityPayload, L2GoldPayload, dict[str, Any]]:
    if adjudications.dataset_id != source.dataset_id:
        raise ValueError("fresh L2 adjudication dataset mismatch")
    overlap = set(adjudications.public_vocabulary) & set(_ALLOWED_VOCABULARY)
    if overlap:
        raise ValueError("fresh L2 vocabulary cannot override base vocabulary")
    source_by_private = {case.private_case_id: case for case in source.cases}
    adjudication_by_private = {
        case.private_case_id: case for case in adjudications.cases
    }
    if set(source_by_private) != set(adjudication_by_private):
        raise ValueError("fresh L2 adjudications must cover the exact frozen selection")
    for private_id, source_case in source_by_private.items():
        if adjudication_by_private[private_id].knowledge_id != source_case.knowledge_id:
            raise ValueError("fresh L2 adjudication knowledge ID mismatch")

    public_cases: list[L2PublicCase] = []
    authority_cases: list[L2AuthorityCase] = []
    gold_items: list[L2GoldItem] = []
    emit_count = abstain_count = 0
    methods: set[str] = set()
    patterns: set[str] = set()
    for source_case in source.cases:
        adjudication = adjudication_by_private[source_case.private_case_id]
        record = records.get(source_case.knowledge_id)
        if record is None:
            raise ValueError("fresh L2 adjudicated record is missing from replay")
        support_pack = adjudication.typed_l1_support_pack
        support_refs = [item.support_ref for item in support_pack]
        expected_support_refs = [
            _opaque_ref(
                "support",
                source.namespace,
                f"{source_case.knowledge_id}:{index}",
            )
            for index in range(1, len(support_refs) + 1)
        ]
        if support_refs != expected_support_refs:
            raise ValueError("fresh L2 support refs are not deterministic and ordered")
        expected_evidence = sorted(
            (
                str(item["evidence_id"]),
                _speaker(str(item["message"]), str(item["evidence_role"])),
                int(item["turn_index"]),
            )
            for item in record.knowledge["evidence"]
        )
        turn_ref_by_index = {
            turn.turn_index: turn.source_turn_ref for turn in source_case.source_turns
        }
        actual_evidence: list[tuple[str, str, int]] = []
        for support in support_pack:
            if support.source_session_ref != source_case.source_session_ref:
                raise ValueError("fresh L2 support has incorrect session ref")
            matching_turns = [
                turn_index
                for turn_index, turn_ref in turn_ref_by_index.items()
                if turn_ref == support.source_turn_ref
            ]
            if len(matching_turns) != 1:
                raise ValueError("fresh L2 support has incorrect turn ref")
            actual_evidence.extend(
                (binding.evidence_id, binding.speaker, matching_turns[0])
                for binding in support.evidence_bindings
            )
        if sorted(actual_evidence) != expected_evidence:
            raise ValueError("fresh L2 support pack does not exactly cover source evidence")
        evidence_bindings = [
            TypedEvidenceBinding(evidence_id=evidence_id, speaker=speaker)
            for evidence_id, speaker, _ in expected_evidence
        ]
        expected = adjudication.expected_typed_candidate
        if expected is not None:
            if expected.supporting_l1_refs != support_refs:
                raise ValueError("fresh L2 gold support refs do not match public support pack")
            if expected.source_turn_refs != source_case.source_turn_refs:
                raise ValueError("fresh L2 gold source turn coverage mismatch")
            if expected.source_session_refs != [source_case.source_session_ref]:
                raise ValueError("fresh L2 gold source session coverage mismatch")
            if expected.evidence_bindings != evidence_bindings:
                raise ValueError("fresh L2 gold evidence coverage mismatch")
            if expected.structured_claims[0].predicate.surface != (
                source_case.untyped_candidate.predicate
            ):
                raise ValueError("fresh L2 primary predicate surface must copy public input")
            if expected.abstraction.method not in adjudication.allowed_abstraction_methods:
                raise ValueError("fresh L2 gold abstraction is outside authority")
            if expected.closure.pattern not in adjudication.allowed_closure_patterns:
                raise ValueError("fresh L2 gold closure is outside authority")
            methods.add(expected.abstraction.method)
            patterns.add(expected.closure.pattern)

        public_cases.append(
            L2PublicCase(
                case_id=source_case.case_id,
                candidate_ref=source_case.candidate_ref,
                source_session_ref=source_case.source_session_ref,
                source_turns=source_case.source_turns,
                untyped_candidate=source_case.untyped_candidate,
                typed_l1_support_pack=support_pack,
            )
        )
        authority_cases.append(
            L2AuthorityCase(
                case_id=source_case.case_id,
                candidate_ref=source_case.candidate_ref,
                knowledge_id=source_case.knowledge_id,
                candidate_id=source_case.candidate_id,
                emission_allowed=adjudication.emission_allowed,
                required_support_refs=support_refs,
                required_evidence_bindings=evidence_bindings,
                required_source_turn_refs=source_case.source_turn_refs,
                required_source_session_refs=[source_case.source_session_ref],
                allowed_abstraction_methods=adjudication.allowed_abstraction_methods,
                allowed_closure_patterns=adjudication.allowed_closure_patterns,
                unresolved_required_fields=adjudication.unresolved_required_fields,
            )
        )
        gold_items.append(
            L2GoldItem(
                case_id=source_case.case_id,
                candidate_ref=source_case.candidate_ref,
                expected_decision=adjudication.expected_decision,
                expected_typed_candidate=expected,
            )
        )
        emit_count += adjudication.expected_decision == "emit_l2"
        abstain_count += adjudication.expected_decision == "abstain"

    distribution = {
        "emit_count": emit_count,
        "abstain_count": abstain_count,
        "abstraction_methods": sorted(methods),
        "closure_patterns": sorted(patterns),
    }
    return (
        L2PublicPayload(
            dataset_id=source.dataset_id,
            case_count=source.case_count,
            allowed_vocabulary={
                **_ALLOWED_VOCABULARY,
                **adjudications.public_vocabulary,
            },
            cases=public_cases,
        ),
        L2AuthorityPayload(
            dataset_id=source.dataset_id,
            case_count=source.case_count,
            cases=authority_cases,
        ),
        L2GoldPayload(
            dataset_id=source.dataset_id,
            case_count=source.case_count,
            items=gold_items,
        ),
        distribution,
    )


def _manifest_input_sha256(
    *,
    preregistration_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    selection_root: Path,
) -> dict[str, str]:
    return {
        "adjudications": sha256_file(selection_root / "adjudications-l2.json"),
        "bridge_ledger": sha256_file(bridge_ledger_path),
        "dev_authority": sha256_file(l2_dev_root / "authority-l2.json"),
        "dev_source": sha256_file(l2_dev_root / "source-cases-l2.json"),
        "dialogue_manifest": sha256_file(dialogue_manifest_path),
        "final_knowledge": sha256_file(final_knowledge_path),
        "preregistration": sha256_file(preregistration_path),
        "prompt": sha256_file(prompt_path),
        "run": sha256_file(run_path),
        "selection_source": sha256_file(selection_root / "source-cases-l2.json"),
        "source": sha256_file(source_path),
        "source_segments": sha256_file(source_segments_path),
        "turn_manifest": sha256_file(turn_manifest_path),
    }


def _build_manifest(
    *,
    public: L2PublicPayload,
    distribution: dict[str, Any],
    paths: dict[str, Path],
) -> L2Manifest:
    root = paths["selection_root"]
    preregistration = TypedExtractorFreshPreregistration.model_validate(
        load_json(paths["preregistration_path"])
    )
    l1_qualification = {
        name: value
        for name, value in preregistration.input_sha256.items()
        if name.startswith("l1/")
    }
    return L2Manifest(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        input_sha256=_manifest_input_sha256(**paths),
        l1_qualification_sha256=l1_qualification,
        output_sha256={
            name: sha256_file(root / name)
            for name in ("authority-l2.json", "gold-l2.json", "public-l2.json")
        },
        distribution=distribution,
        thresholds=dict(L2_DEV_THRESHOLDS),
        claim_boundary={
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "fresh_hidden_created": True,
            "l1_support_pack_is_authoritative": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
            "raw_gold_authored_after_selection": True,
        },
    )


def _final_paths(
    *,
    preregistration_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    selection_root: Path,
) -> dict[str, Path]:
    return _resolve_paths(
        preregistration_path=preregistration_path,
        prompt_path=prompt_path,
        bridge_ledger_path=bridge_ledger_path,
        l2_dev_root=l2_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
        selection_root=selection_root,
    )


def _validate_selection_from_final_paths(paths: dict[str, Path]) -> None:
    validate_fresh_l2_selection(
        preregistration_path=paths["preregistration_path"],
        bridge_ledger_path=paths["bridge_ledger_path"],
        l2_dev_root=paths["l2_dev_root"],
        source_path=paths["source_path"],
        turn_manifest_path=paths["turn_manifest_path"],
        dialogue_manifest_path=paths["dialogue_manifest_path"],
        final_knowledge_path=paths["final_knowledge_path"],
        run_path=paths["run_path"],
        source_segments_path=paths["source_segments_path"],
        root=paths["selection_root"],
    )


def _replay_records(paths: dict[str, Path]) -> dict[str, Any]:
    replay = replay_extraction_inputs(
        source_path=paths["source_path"],
        turn_manifest_path=paths["turn_manifest_path"],
        dialogue_manifest_path=paths["dialogue_manifest_path"],
        final_knowledge_path=paths["final_knowledge_path"],
        run_path=paths["run_path"],
        source_segments_path=paths["source_segments_path"],
    )
    return replay.view.by_id


def prepare_fresh_l2_slice(
    *,
    preregistration_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    selection_root: Path,
    adjudication_path: Path,
) -> dict[str, Any]:
    paths = _final_paths(
        preregistration_path=preregistration_path,
        prompt_path=prompt_path,
        bridge_ledger_path=bridge_ledger_path,
        l2_dev_root=l2_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
        selection_root=selection_root,
    )
    _validate_selection_from_final_paths(paths)
    _require_read_only(paths["prompt_path"], "fresh L2 prompt")
    preregistration = TypedExtractorFreshPreregistration.model_validate(
        load_json(paths["preregistration_path"])
    )
    if sha256_file(paths["prompt_path"]) != preregistration.input_sha256[
        "l2/proposer-prompt-l2.md"
    ]:
        raise ValueError("fresh L2 prompt drift")
    source = FreshL2SourcePayload.model_validate(
        load_json(paths["selection_root"] / "source-cases-l2.json")
    )
    adjudication_path = adjudication_path.resolve()
    _require_read_only(adjudication_path, "fresh L2 adjudications")
    adjudications = L2SourceConfig.model_validate(load_json(adjudication_path))
    public, authority, gold, distribution = _build_final_artifacts(
        source, adjudications, _replay_records(paths)
    )
    root = paths["selection_root"]
    outputs: dict[str, BaseModel] = {
        "adjudications-l2.json": adjudications,
        "public-l2.json": public,
        "authority-l2.json": authority,
        "gold-l2.json": gold,
    }
    for name, payload in outputs.items():
        write_json_immutable(root / name, payload)
        (root / name).chmod(0o444)
    manifest = _build_manifest(public=public, distribution=distribution, paths=paths)
    write_json_immutable(root / "manifest-l2.json", manifest)
    (root / "manifest-l2.json").chmod(0o444)
    return {
        "status": "valid",
        "case_count": public.case_count,
        "raw_gold_authored_after_selection": True,
        **distribution,
    }


def validate_fresh_l2_slice(
    *,
    preregistration_path: Path,
    prompt_path: Path,
    bridge_ledger_path: Path,
    l2_dev_root: Path,
    source_path: Path,
    turn_manifest_path: Path,
    dialogue_manifest_path: Path,
    final_knowledge_path: Path,
    run_path: Path,
    source_segments_path: Path,
    root: Path,
) -> dict[str, Any]:
    paths = _final_paths(
        preregistration_path=preregistration_path,
        prompt_path=prompt_path,
        bridge_ledger_path=bridge_ledger_path,
        l2_dev_root=l2_dev_root,
        source_path=source_path,
        turn_manifest_path=turn_manifest_path,
        dialogue_manifest_path=dialogue_manifest_path,
        final_knowledge_path=final_knowledge_path,
        run_path=run_path,
        source_segments_path=source_segments_path,
        selection_root=root,
    )
    _validate_selection_from_final_paths(paths)
    for name in (
        "adjudications-l2.json",
        "public-l2.json",
        "authority-l2.json",
        "gold-l2.json",
        "manifest-l2.json",
    ):
        _require_read_only(paths["selection_root"] / name, name)
    source = FreshL2SourcePayload.model_validate(
        load_json(paths["selection_root"] / "source-cases-l2.json")
    )
    adjudications = L2SourceConfig.model_validate(
        load_json(paths["selection_root"] / "adjudications-l2.json")
    )
    public, authority, gold, distribution = _build_final_artifacts(
        source, adjudications, _replay_records(paths)
    )
    expected_outputs = {
        "public-l2.json": public,
        "authority-l2.json": authority,
        "gold-l2.json": gold,
    }
    for name, expected in expected_outputs.items():
        if (paths["selection_root"] / name).read_bytes() != canonical_json_bytes(expected):
            raise ValueError(f"fresh L2 artifact drift: {name}")
    actual_manifest = L2Manifest.model_validate(
        load_json(paths["selection_root"] / "manifest-l2.json")
    )
    expected_manifest = _build_manifest(
        public=public, distribution=distribution, paths=paths
    )
    if canonical_json_bytes(actual_manifest) != canonical_json_bytes(expected_manifest):
        raise ValueError("fresh L2 manifest drift")
    return {
        "status": "valid",
        "case_count": public.case_count,
        "raw_gold_authored_after_selection": True,
    }
