from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io import canonical_json_bytes, sha256_file, write_json_immutable


V5_RESULTS_SHA256 = "3ec6656c037200f8591fac44cd7e1e4bf2caa3aa9447f3fa5ba9854324d4cc33"

RelationKind = Literal["identity", "membership"]
ProposalAction = Literal["merge", "keep_distinct", "include", "exclude", "abstain"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActorLocator(StrictModel):
    kind: Literal["locomo_dia_id"]
    sample_id: str = Field(min_length=1)
    dia_id: str = Field(min_length=1)


class SourceMention(StrictModel):
    mention_id: str = Field(min_length=1)
    source_item_id: str = Field(min_length=1)
    evidence_unit_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    source_actor_id: str | None = None
    actor_locator: ActorLocator | None = None


class SourceAuthority(StrictModel):
    shared_trusted_identifiers: list[str] = Field(default_factory=list)
    conflicting_trusted_identifiers: list[str] = Field(default_factory=list)
    explicit_same_entity: bool = False
    explicit_distinct: bool = False
    actor_binding_authoritative: bool = False
    explicit_membership: bool = False
    explicit_non_membership: bool = False
    required_mention_ids: list[str] = Field(min_length=1)


class SourceGold(StrictModel):
    expected_action: ProposalAction
    critical_false_merge: bool
    critical_false_membership: bool


class SourceCase(StrictModel):
    case_id: str = Field(min_length=1)
    split: Literal["dev", "hidden"]
    relation_kind: RelationKind
    question: str = Field(min_length=1)
    mentions: list[SourceMention] = Field(min_length=1)
    query_subject_id: str | None = None
    group_surface: str | None = None
    member_surface: str | None = None
    authority: SourceAuthority
    gold: SourceGold

    @model_validator(mode="after")
    def validate_action_family_and_evidence(self) -> "SourceCase":
        allowed = (
            {"merge", "keep_distinct", "abstain"}
            if self.relation_kind == "identity"
            else {"include", "exclude", "abstain"}
        )
        if self.gold.expected_action not in allowed:
            raise ValueError("gold action does not match relation kind")
        mention_ids = [item.mention_id for item in self.mentions]
        if len(mention_ids) != len(set(mention_ids)):
            raise ValueError("duplicate mention id")
        if set(self.authority.required_mention_ids) != set(mention_ids):
            raise ValueError("required mention ids must equal case mention ids")
        if self.relation_kind == "membership" and self.query_subject_id is None:
            if not self.authority.explicit_membership and not self.authority.explicit_non_membership:
                raise ValueError("membership case requires a subject or explicit relation evidence")
        return self


class SourceConfig(StrictModel):
    schema_version: Literal["natural-identity-source-config-v1"]
    dataset_id: str = Field(min_length=1)
    source_inputs: dict[str, str]
    cases: list[SourceCase] = Field(min_length=1)


class PublicMention(StrictModel):
    mention_id: str = Field(min_length=1)
    source_item_id: str = Field(min_length=1)
    evidence_unit_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    source_actor_id: str | None = None
    actor_locator: ActorLocator | None = None


class PublicIdentityCase(StrictModel):
    case_id: str = Field(min_length=1)
    split: Literal["dev", "hidden"]
    relation_kind: RelationKind
    question: str = Field(min_length=1)
    mentions: list[PublicMention] = Field(min_length=1)
    query_subject_id: str | None = None
    group_surface: str | None = None
    member_surface: str | None = None


class PublicIdentityPayload(StrictModel):
    schema_version: Literal["natural-identity-public-v1"] = "natural-identity-public-v1"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    cases: list[PublicIdentityCase] = Field(min_length=1)


class AuthorityIdentityCase(StrictModel):
    case_id: str = Field(min_length=1)
    relation_kind: RelationKind
    shared_trusted_identifiers: list[str] = Field(default_factory=list)
    conflicting_trusted_identifiers: list[str] = Field(default_factory=list)
    explicit_same_entity: bool = False
    explicit_distinct: bool = False
    actor_binding_authoritative: bool = False
    explicit_membership: bool = False
    explicit_non_membership: bool = False
    trusted_actor_bindings: dict[str, str | None] = Field(default_factory=dict)
    required_mention_ids: list[str] = Field(min_length=1)
    required_evidence_unit_ids: list[str] = Field(min_length=1)


class AuthorityIdentityPayload(StrictModel):
    schema_version: Literal["natural-identity-authority-v1"] = "natural-identity-authority-v1"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    cases: list[AuthorityIdentityCase] = Field(min_length=1)


class GoldIdentityItem(StrictModel):
    case_id: str = Field(min_length=1)
    split: Literal["dev", "hidden"]
    relation_kind: RelationKind
    expected_action: ProposalAction
    critical_false_merge: bool
    critical_false_membership: bool


class GoldIdentityPayload(StrictModel):
    schema_version: Literal["natural-identity-gold-v1"] = "natural-identity-gold-v1"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    items: list[GoldIdentityItem] = Field(min_length=1)


class NaturalIdentityManifest(StrictModel):
    schema_version: Literal["natural-identity-manifest-v1"] = "natural-identity-manifest-v1"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    dev_count: int = Field(ge=0)
    hidden_count: int = Field(ge=0)
    source_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_inputs: dict[str, str]
    source_input_sha256: dict[str, str]
    output_sha256: dict[str, str]


class IdentityProposalRecord(StrictModel):
    case_id: str = Field(min_length=1)
    relation_kind: RelationKind
    action: ProposalAction
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_mention_ids: list[str]
    reason_code: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_action(self) -> "IdentityProposalRecord":
        if self.relation_kind == "identity" and self.action not in {
            "merge",
            "keep_distinct",
            "abstain",
        }:
            raise ValueError("identity proposal action must be merge, keep_distinct, or abstain")
        if self.relation_kind == "membership" and self.action not in {
            "include",
            "exclude",
            "abstain",
        }:
            raise ValueError("membership proposal action must be include, exclude, or abstain")
        if self.action != "abstain" and not self.evidence_mention_ids:
            raise ValueError("non-abstain proposal requires evidence")
        if len(self.evidence_mention_ids) != len(set(self.evidence_mention_ids)):
            raise ValueError("proposal evidence mention ids must be unique")
        return self


class IdentityProposalPayload(StrictModel):
    schema_version: Literal["natural-identity-proposals-v1"] = "natural-identity-proposals-v1"
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    proposals: list[IdentityProposalRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_run_metadata(self) -> "IdentityProposalPayload":
        case_ids = [item.case_id for item in self.proposals]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate proposal case id")
        if self.case_count != len(self.proposals):
            raise ValueError("proposal case count mismatch")
        for proposal in self.proposals:
            if (
                proposal.run_id != self.run_id
                or proposal.proposer_id != self.proposer_id
                or proposal.proposer_version != self.proposer_version
            ):
                raise ValueError("proposal run metadata mismatch")
        return self


class GatedIdentityDecision(StrictModel):
    case_id: str
    relation_kind: RelationKind
    proposed_action: ProposalAction
    accepted_action: ProposalAction
    gate_reason: str
    evidence_mention_ids: list[str]
    required_evidence_exact: bool
    proposal: IdentityProposalRecord


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(path: str | Path, workspace_root: Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (workspace_root / candidate).resolve()


def _sha256_bytes(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _gold_evidence_index(path: Path) -> dict[str, list[dict[str, Any]]]:
    payload = _load(path)
    items = payload.get("items")
    if not isinstance(items, dict):
        raise ValueError("gold evidence items must be an object")
    return items


def _locomo_dialogue_index(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = _load(path)
    if not isinstance(payload, list):
        raise ValueError("LoCoMo raw snapshot must be a list")
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for sample in payload:
        sample_id = sample.get("sample_id")
        conversation = sample.get("conversation", {})
        if not isinstance(conversation, dict):
            continue
        for value in conversation.values():
            if not isinstance(value, list):
                continue
            for turn in value:
                if isinstance(turn, dict) and turn.get("dia_id"):
                    index[(str(sample_id), str(turn["dia_id"]))] = turn
    return index


def _expected_actor_id(speaker: str) -> str:
    normalized = re.sub(r"\s+", "-", speaker.strip().casefold())
    return f"person:{normalized}"


def _find_evidence_unit(
    evidence_index: dict[str, list[dict[str, Any]]],
    mention: SourceMention | PublicMention,
) -> dict[str, Any]:
    units = evidence_index.get(mention.source_item_id)
    if units is None:
        raise ValueError(f"source item not found: {mention.source_item_id}")
    unit = next(
        (
            item
            for item in units
            if str(item.get("unit_id")) == str(mention.evidence_unit_id)
        ),
        None,
    )
    if unit is None:
        raise ValueError(
            f"evidence unit not found: {mention.source_item_id}/{mention.evidence_unit_id}"
        )
    if mention.quote not in str(unit.get("text", "")):
        raise ValueError(f"quote mismatch for mention {mention.mention_id}")
    return unit


def _validate_actor(
    mention: SourceMention | PublicMention,
    locomo_index: dict[tuple[str, str], dict[str, Any]],
) -> None:
    if mention.actor_locator is None:
        return
    locator = mention.actor_locator
    turn = locomo_index.get((locator.sample_id, locator.dia_id))
    if turn is None:
        raise ValueError(f"LoCoMo actor locator not found for mention {mention.mention_id}")
    if mention.quote not in str(turn.get("text", "")):
        raise ValueError(f"LoCoMo quote mismatch for mention {mention.mention_id}")
    expected = _expected_actor_id(str(turn.get("speaker", "")))
    if mention.source_actor_id != expected:
        raise ValueError(f"actor mismatch for mention {mention.mention_id}")


def _validate_source_cases(
    cases: list[SourceCase],
    evidence_index: dict[str, list[dict[str, Any]]],
    locomo_index: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate case id")
    for case in cases:
        mentions: list[dict[str, Any]] = []
        for mention in case.mentions:
            unit = _find_evidence_unit(evidence_index, mention)
            _validate_actor(mention, locomo_index)
            item = mention.model_dump(mode="json")
            item["source_ref"] = str(unit.get("source_ref", ""))
            if not item["source_ref"]:
                raise ValueError(f"source ref missing for mention {mention.mention_id}")
            mentions.append(item)
        resolved.append({"case": case, "mentions": mentions})
    return resolved


def _restricted_field(value: Any, restricted: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in restricted:
                return key
            found = _restricted_field(child, restricted)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _restricted_field(child, restricted)
            if found:
                return found
    return None


def freeze_natural_identity_slice(
    source_config_path: Path,
    output_root: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    source_path = _resolve_path(source_config_path, workspace_root)
    source = SourceConfig.model_validate(_load(source_path))
    required_inputs = {"gold_evidence", "locomo_raw"}
    if set(source.source_inputs) != required_inputs:
        raise ValueError("source inputs must contain gold_evidence and locomo_raw")
    input_paths = {
        key: _resolve_path(value, workspace_root)
        for key, value in source.source_inputs.items()
    }
    evidence_index = _gold_evidence_index(input_paths["gold_evidence"])
    locomo_index = _locomo_dialogue_index(input_paths["locomo_raw"])
    resolved = _validate_source_cases(source.cases, evidence_index, locomo_index)

    public_cases: list[dict[str, Any]] = []
    authority_cases: list[dict[str, Any]] = []
    gold_items: list[dict[str, Any]] = []
    for item in resolved:
        case: SourceCase = item["case"]
        mentions = item["mentions"]
        public_case = {
            "case_id": case.case_id,
            "split": case.split,
            "relation_kind": case.relation_kind,
            "question": case.question,
            "mentions": mentions,
            "query_subject_id": case.query_subject_id,
            "group_surface": case.group_surface,
            "member_surface": case.member_surface,
        }
        public_cases.append(PublicIdentityCase.model_validate(public_case).model_dump(mode="json"))

        authority = case.authority
        authority_case = {
            "case_id": case.case_id,
            "relation_kind": case.relation_kind,
            **authority.model_dump(mode="json", exclude={"required_mention_ids"}),
            "trusted_actor_bindings": {
                mention.mention_id: mention.source_actor_id for mention in case.mentions
            },
            "required_mention_ids": authority.required_mention_ids,
            "required_evidence_unit_ids": [
                mention.evidence_unit_id for mention in case.mentions
            ],
        }
        authority_cases.append(
            AuthorityIdentityCase.model_validate(authority_case).model_dump(mode="json")
        )
        gold_items.append(
            GoldIdentityItem(
                case_id=case.case_id,
                split=case.split,
                relation_kind=case.relation_kind,
                **case.gold.model_dump(mode="json"),
            ).model_dump(mode="json")
        )

    public = PublicIdentityPayload(
        dataset_id=source.dataset_id,
        case_count=len(public_cases),
        cases=public_cases,
    )
    authority = AuthorityIdentityPayload(
        dataset_id=source.dataset_id,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = GoldIdentityPayload(
        dataset_id=source.dataset_id,
        case_count=len(gold_items),
        items=gold_items,
    )

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "public.json": output_root / "public.json",
        "authority.json": output_root / "authority.json",
        "gold.json": output_root / "gold.json",
    }
    write_json_immutable(output_paths["public.json"], public)
    write_json_immutable(output_paths["authority.json"], authority)
    write_json_immutable(output_paths["gold.json"], gold)

    manifest = NaturalIdentityManifest(
        dataset_id=source.dataset_id,
        case_count=len(source.cases),
        dev_count=sum(case.split == "dev" for case in source.cases),
        hidden_count=sum(case.split == "hidden" for case in source.cases),
        source_config_sha256=sha256_file(source_path),
        source_inputs=source.source_inputs,
        source_input_sha256={key: sha256_file(path) for key, path in input_paths.items()},
        output_sha256={key: sha256_file(path) for key, path in output_paths.items()},
    )
    write_json_immutable(output_root / "manifest.json", manifest)
    return {
        "status": "valid",
        "dataset_id": source.dataset_id,
        "case_count": len(source.cases),
        "dev_count": manifest.dev_count,
        "hidden_count": manifest.hidden_count,
        "output_sha256": manifest.output_sha256,
    }


def validate_natural_identity_slice(
    root: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    workspace_root = (workspace_root or Path.cwd()).resolve()
    public_raw = _load(root / "public.json")
    authority_raw = _load(root / "authority.json")
    gold_raw = _load(root / "gold.json")
    manifest_raw = _load(root / "manifest.json")

    leaked = _restricted_field(
        public_raw,
        {
            "authority",
            "gold",
            "expected_action",
            "critical_false_merge",
            "critical_false_membership",
            "shared_trusted_identifiers",
            "conflicting_trusted_identifiers",
            "explicit_same_entity",
            "explicit_distinct",
            "actor_binding_authoritative",
            "explicit_membership",
            "explicit_non_membership",
            "trusted_actor_bindings",
        },
    )
    if leaked:
        raise ValueError(f"public case leaks restricted field: {leaked}")
    leaked = _restricted_field(
        authority_raw,
        {"gold", "expected_action", "critical_false_merge", "critical_false_membership"},
    )
    if leaked:
        raise ValueError(f"authority case leaks gold field: {leaked}")
    leaked = _restricted_field(
        gold_raw,
        {
            "authority",
            "shared_trusted_identifiers",
            "conflicting_trusted_identifiers",
            "trusted_actor_bindings",
        },
    )
    if leaked:
        raise ValueError(f"gold item leaks authority field: {leaked}")

    public = PublicIdentityPayload.model_validate(public_raw)
    authority = AuthorityIdentityPayload.model_validate(authority_raw)
    gold = GoldIdentityPayload.model_validate(gold_raw)
    manifest = NaturalIdentityManifest.model_validate(manifest_raw)
    if not (
        public.dataset_id == authority.dataset_id == gold.dataset_id == manifest.dataset_id
    ):
        raise ValueError("dataset id mismatch")
    public_ids = {item.case_id for item in public.cases}
    authority_ids = {item.case_id for item in authority.cases}
    gold_ids = {item.case_id for item in gold.items}
    if public_ids != authority_ids or public_ids != gold_ids:
        raise ValueError("public/authority/gold case ids differ")
    if len(public_ids) != manifest.case_count:
        raise ValueError("manifest case count mismatch")

    output_paths = {
        "public.json": root / "public.json",
        "authority.json": root / "authority.json",
        "gold.json": root / "gold.json",
    }
    for name, path in output_paths.items():
        if manifest.output_sha256.get(name) != sha256_file(path):
            raise ValueError(f"manifest hash mismatch: {name}")
    input_paths = {
        key: _resolve_path(value, workspace_root)
        for key, value in manifest.source_inputs.items()
    }
    for key, path in input_paths.items():
        if manifest.source_input_sha256.get(key) != sha256_file(path):
            raise ValueError(f"source input hash mismatch: {key}")

    evidence_index = _gold_evidence_index(input_paths["gold_evidence"])
    locomo_index = _locomo_dialogue_index(input_paths["locomo_raw"])
    authority_by_id = {item.case_id: item for item in authority.cases}
    for case in public.cases:
        rule = authority_by_id[case.case_id]
        for mention in case.mentions:
            unit = _find_evidence_unit(evidence_index, mention)
            if str(unit.get("source_ref")) != mention.source_ref:
                raise ValueError(f"source ref mismatch for mention {mention.mention_id}")
            _validate_actor(mention, locomo_index)
            if rule.trusted_actor_bindings.get(mention.mention_id) != mention.source_actor_id:
                raise ValueError(f"authority actor mismatch for mention {mention.mention_id}")
        if set(rule.required_mention_ids) != {item.mention_id for item in case.mentions}:
            raise ValueError(f"required mention mismatch for case {case.case_id}")
        if set(rule.required_evidence_unit_ids) != {
            item.evidence_unit_id for item in case.mentions
        }:
            raise ValueError(f"required evidence mismatch for case {case.case_id}")

    return {
        "status": "valid",
        "dataset_id": public.dataset_id,
        "case_count": len(public.cases),
        "dev_count": sum(item.split == "dev" for item in public.cases),
        "hidden_count": sum(item.split == "hidden" for item in public.cases),
        "source_validation_valid": True,
        "manifest_integrity_valid": True,
    }


def _normalized_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _reference_proposal(case: PublicIdentityCase, *, run_id: str) -> IdentityProposalRecord:
    evidence = [item.mention_id for item in case.mentions]
    if case.relation_kind == "identity":
        public_actors = {
            item.source_actor_id for item in case.mentions if item.source_actor_id is not None
        }
        if len(public_actors) == 1 and len(case.mentions) > 1:
            action, reason, confidence = "merge", "public_actor_id_match", 0.95
        elif len(public_actors) > 1:
            action, reason, confidence = "keep_distinct", "public_actor_id_conflict", 0.95
        else:
            token_sets = [_normalized_tokens(item.surface) for item in case.mentions]
            overlap = set.intersection(*token_sets) if token_sets else set()
            if overlap:
                action, reason, confidence = "merge", "surface_token_overlap", 0.75
            elif all(tokens for tokens in token_sets):
                action, reason, confidence = "keep_distinct", "disjoint_named_surfaces", 0.70
            else:
                action, reason, confidence = "abstain", "insufficient_public_identity_signal", 0.40
    else:
        actor_ids = {
            item.source_actor_id for item in case.mentions if item.source_actor_id is not None
        }
        if case.query_subject_id is not None and actor_ids:
            if actor_ids == {case.query_subject_id}:
                action, reason, confidence = "include", "public_subject_match", 0.92
            else:
                action, reason, confidence = "exclude", "public_subject_mismatch", 0.92
        else:
            member_tokens = _normalized_tokens(case.member_surface or "")
            quote_tokens = set().union(
                *(_normalized_tokens(item.quote) for item in case.mentions)
            )
            if member_tokens and member_tokens & quote_tokens:
                action, reason, confidence = "include", "explicit_member_phrase", 0.80
            else:
                action, reason, confidence = "abstain", "insufficient_public_membership_signal", 0.40
    return IdentityProposalRecord(
        case_id=case.case_id,
        relation_kind=case.relation_kind,
        action=action,
        confidence=confidence,
        evidence_mention_ids=evidence,
        reason_code=reason,
        proposer_id="deterministic-public-reference",
        proposer_version="1",
        run_id=run_id,
    )


def run_reference_identity_proposer(public_path: Path, *, run_id: str) -> dict[str, Any]:
    public = PublicIdentityPayload.model_validate(_load(public_path))
    proposals = [_reference_proposal(case, run_id=run_id) for case in public.cases]
    payload = IdentityProposalPayload(
        dataset_id=public.dataset_id,
        run_id=run_id,
        proposer_id="deterministic-public-reference",
        proposer_version="1",
        case_count=len(proposals),
        proposals=proposals,
    )
    return payload.model_dump(mode="json")


def apply_identity_proposal_gate(
    public_case: PublicIdentityCase | dict[str, Any],
    authority_case: AuthorityIdentityCase | dict[str, Any],
    proposal: IdentityProposalRecord | dict[str, Any],
) -> GatedIdentityDecision:
    case = (
        public_case
        if isinstance(public_case, PublicIdentityCase)
        else PublicIdentityCase.model_validate(public_case)
    )
    rule = (
        authority_case
        if isinstance(authority_case, AuthorityIdentityCase)
        else AuthorityIdentityCase.model_validate(authority_case)
    )
    proposal_record = (
        proposal
        if isinstance(proposal, IdentityProposalRecord)
        else IdentityProposalRecord.model_validate(proposal)
    )
    if case.case_id != rule.case_id or case.case_id != proposal_record.case_id:
        raise ValueError("gate case id mismatch")
    if case.relation_kind != rule.relation_kind or case.relation_kind != proposal_record.relation_kind:
        raise ValueError("gate relation kind mismatch")
    evidence_exact = set(proposal_record.evidence_mention_ids) == set(rule.required_mention_ids)
    accepted: ProposalAction = "abstain"
    reason = "required_evidence_mismatch"
    if evidence_exact:
        action = proposal_record.action
        if action == "abstain":
            reason = "proposer_abstained"
        elif case.relation_kind == "identity":
            if action == "merge":
                if rule.shared_trusted_identifiers or rule.explicit_same_entity:
                    accepted, reason = "merge", "merge_authorized"
                else:
                    reason = "merge_not_authorized"
            elif action == "keep_distinct":
                if rule.conflicting_trusted_identifiers or rule.explicit_distinct:
                    accepted, reason = "keep_distinct", "distinctness_authorized"
                else:
                    reason = "distinctness_not_authorized"
        else:
            trusted_actors = {
                actor
                for mention_id, actor in rule.trusted_actor_bindings.items()
                if mention_id in rule.required_mention_ids and actor is not None
            }
            subject_matches = bool(
                case.query_subject_id is not None
                and trusted_actors
                and trusted_actors == {case.query_subject_id}
            )
            subject_mismatch = bool(
                case.query_subject_id is not None
                and trusted_actors
                and trusted_actors != {case.query_subject_id}
            )
            if action == "include":
                if rule.explicit_membership or (
                    rule.actor_binding_authoritative and subject_matches
                ):
                    accepted, reason = "include", "membership_authorized"
                elif rule.actor_binding_authoritative and subject_mismatch:
                    reason = "membership_subject_mismatch"
                else:
                    reason = "membership_not_authorized"
            elif action == "exclude":
                if rule.explicit_non_membership or (
                    rule.actor_binding_authoritative and subject_mismatch
                ):
                    accepted, reason = "exclude", "non_membership_authorized"
                elif rule.actor_binding_authoritative and subject_matches:
                    reason = "non_membership_subject_match"
                else:
                    reason = "non_membership_not_authorized"
    return GatedIdentityDecision(
        case_id=case.case_id,
        relation_kind=case.relation_kind,
        proposed_action=proposal_record.action,
        accepted_action=accepted,
        gate_reason=reason,
        evidence_mention_ids=proposal_record.evidence_mention_ids,
        required_evidence_exact=evidence_exact,
        proposal=proposal_record,
    )


def _v5_regression(workspace_root: Path) -> dict[str, Any]:
    path = (
        workspace_root
        / "artifacts"
        / "natural-benchmark-slices"
        / "slice-v1"
        / "representation-conformance-results-v5.json"
    )
    if not path.exists():
        return {
            "v5_results_sha256": None,
            "v5_hash_preserved": False,
            "v5_longmemeval_abstention_preserved": False,
        }
    payload = _load(path)
    probe = next(
        (
            item
            for item in payload.get("correctness_probes", [])
            if item.get("query_id") == "LONGMEMEVAL-6d550036"
        ),
        None,
    )
    preserved = bool(
        probe
        and probe.get("expected", {}).get("abstained") is True
        and probe.get("expected", {}).get("reason")
        == "structured_l2_identity_unresolved"
        and probe.get("reference_result", {}).get("abstained") is True
        and probe.get("reference_result", {}).get("reason")
        == "structured_l2_identity_unresolved"
    )
    digest = sha256_file(path)
    return {
        "v5_results_sha256": digest,
        "v5_hash_preserved": digest == V5_RESULTS_SHA256,
        "v5_longmemeval_abstention_preserved": preserved,
    }


def _ratio(numerator: int, denominator: int, *, empty: float = 0.0) -> float:
    return numerator / denominator if denominator else empty


def score_identity_proposal_payload(
    root: Path,
    proposals: IdentityProposalPayload | dict[str, Any],
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    workspace_root = (workspace_root or Path.cwd()).resolve()
    validation = validate_natural_identity_slice(root, workspace_root=workspace_root)
    public = PublicIdentityPayload.model_validate(_load(root / "public.json"))
    authority = AuthorityIdentityPayload.model_validate(_load(root / "authority.json"))
    gold = GoldIdentityPayload.model_validate(_load(root / "gold.json"))
    proposal_payload = (
        proposals
        if isinstance(proposals, IdentityProposalPayload)
        else IdentityProposalPayload.model_validate(proposals)
    )
    if proposal_payload.dataset_id != public.dataset_id:
        raise ValueError("proposal dataset id mismatch")
    public_by_id = {item.case_id: item for item in public.cases}
    authority_by_id = {item.case_id: item for item in authority.cases}
    gold_by_id = {item.case_id: item for item in gold.items}
    proposal_by_id = {item.case_id: item for item in proposal_payload.proposals}
    if set(proposal_by_id) != set(public_by_id):
        raise ValueError("proposal case coverage mismatch")

    gated = [
        apply_identity_proposal_gate(
            public_by_id[case_id], authority_by_id[case_id], proposal_by_id[case_id]
        )
        for case_id in public_by_id
    ]
    gated_by_id = {item.case_id: item for item in gated}
    case_count = len(public_by_id)
    raw_correct = sum(
        proposal_by_id[case_id].action == gold_by_id[case_id].expected_action
        for case_id in public_by_id
    )
    gated_correct = sum(
        gated_by_id[case_id].accepted_action == gold_by_id[case_id].expected_action
        for case_id in public_by_id
    )
    raw_false_merge = sum(
        proposal_by_id[case_id].action == "merge"
        and gold_by_id[case_id].critical_false_merge
        for case_id in public_by_id
    )
    gated_false_merge = sum(
        gated_by_id[case_id].accepted_action == "merge"
        and gold_by_id[case_id].critical_false_merge
        for case_id in public_by_id
    )
    raw_false_membership = sum(
        proposal_by_id[case_id].action == "include"
        and gold_by_id[case_id].critical_false_membership
        for case_id in public_by_id
    )
    gated_false_membership = sum(
        gated_by_id[case_id].accepted_action == "include"
        and gold_by_id[case_id].critical_false_membership
        for case_id in public_by_id
    )
    expected_abstain = {
        case_id
        for case_id, item in gold_by_id.items()
        if item.expected_action == "abstain"
    }
    raw_abstain = {
        case_id
        for case_id, item in proposal_by_id.items()
        if item.action == "abstain"
    }
    gated_abstain = {
        case_id
        for case_id, item in gated_by_id.items()
        if item.accepted_action == "abstain"
    }
    abstain_true_positive = len(raw_abstain & expected_abstain)
    raw_abstention_precision = _ratio(
        abstain_true_positive, len(raw_abstain), empty=0.0
    )
    raw_abstention_recall = _ratio(
        abstain_true_positive, len(expected_abstain), empty=1.0
    )
    raw_abstention_f1 = (
        2 * raw_abstention_precision * raw_abstention_recall
        / (raw_abstention_precision + raw_abstention_recall)
        if raw_abstention_precision + raw_abstention_recall
        else 0.0
    )
    evidence_exact_count = sum(item.required_evidence_exact for item in gated)
    interventions = sum(item.proposed_action != item.accepted_action for item in gated)
    expected_non_abstain = case_count - len(expected_abstain)
    accepted_non_abstain_correct = sum(
        item.accepted_action != "abstain"
        and item.accepted_action == gold_by_id[item.case_id].expected_action
        for item in gated
    )
    metrics = {
        "raw_action_accuracy": _ratio(raw_correct, case_count),
        "gated_action_accuracy": _ratio(gated_correct, case_count),
        "raw_critical_false_merge_count": raw_false_merge,
        "gated_critical_false_merge_count": gated_false_merge,
        "raw_critical_false_membership_count": raw_false_membership,
        "gated_critical_false_membership_count": gated_false_membership,
        "raw_abstention_precision": raw_abstention_precision,
        "raw_abstention_recall": raw_abstention_recall,
        "raw_abstention_f1": raw_abstention_f1,
        "gated_abstention_correctness": _ratio(
            len(gated_abstain & expected_abstain), len(expected_abstain), empty=1.0
        ),
        "proposal_evidence_exact_rate": _ratio(evidence_exact_count, case_count),
        "required_evidence_exact_rate": _ratio(evidence_exact_count, case_count),
        "gate_intervention_count": interventions,
        "gate_intervention_rate": _ratio(interventions, case_count),
        "accepted_non_abstain_coverage": _ratio(
            accepted_non_abstain_correct, expected_non_abstain, empty=1.0
        ),
        "structural_fallback_count": 0,
    }
    regressions = _v5_regression(workspace_root)
    gate_safety_ready = bool(
        validation["source_validation_valid"]
        and validation["manifest_integrity_valid"]
        and metrics["gated_critical_false_merge_count"] == 0
        and metrics["gated_critical_false_membership_count"] == 0
        and metrics["gated_action_accuracy"] == 1.0
        and metrics["gated_abstention_correctness"] == 1.0
        and metrics["required_evidence_exact_rate"] == 1.0
        and metrics["structural_fallback_count"] == 0
        and regressions["v5_hash_preserved"]
        and regressions["v5_longmemeval_abstention_preserved"]
    )
    proposal_quality_ready = bool(
        metrics["raw_action_accuracy"] >= 0.85
        and metrics["raw_critical_false_merge_count"] == 0
        and metrics["raw_critical_false_membership_count"] == 0
        and metrics["raw_abstention_f1"] >= 0.80
        and metrics["proposal_evidence_exact_rate"] >= 0.95
    )
    return {
        "schema_version": "natural-identity-proposal-score-v1",
        "status": "pass" if gate_safety_ready else "fail",
        "dataset_id": public.dataset_id,
        "run_id": proposal_payload.run_id,
        "proposer_id": proposal_payload.proposer_id,
        "proposer_version": proposal_payload.proposer_version,
        "case_count": case_count,
        "gate_safety_ready": gate_safety_ready,
        "proposal_quality_ready": proposal_quality_ready,
        "metrics": metrics,
        "validation": validation,
        "regressions": regressions,
        "gated_decisions": [item.model_dump(mode="json") for item in gated],
        "input_sha256": {
            "public": sha256_file(root / "public.json"),
            "authority": sha256_file(root / "authority.json"),
            "gold": sha256_file(root / "gold.json"),
            "manifest": sha256_file(root / "manifest.json"),
            "proposals": _sha256_bytes(proposal_payload),
        },
        "claim_boundary": {
            "core_impact": "none",
            "reference_proposer_is_model_run": False,
            "automatic_merge_authorized": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    }

