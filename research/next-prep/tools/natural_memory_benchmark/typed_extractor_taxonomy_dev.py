from __future__ import annotations

import hashlib
import copy
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import model_validator

from . import typed_extractor_l1_dev_repair as l1_dev
from . import typed_extractor_l2_dev_repair as l2_dev
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_l1 import (
    AutomaticWriteAuthorizations,
    L1AuthorityCase,
    L1AuthorityPayload,
    L1GoldItem,
    L1GoldPayload,
    L1Manifest,
    L1PublicCase,
    L1PublicPayload,
    StrictModel,
)
from .typed_extractor_l2 import (
    L2AuthorityCase,
    L2AuthorityPayload,
    L2GoldItem,
    L2GoldPayload,
    L2Manifest,
    L2PublicCase,
    L2PublicPayload,
    L2PublicTurn,
    L2_DEV_THRESHOLDS,
)


Layer = Literal["l1", "l2"]
L1_DATASET_ID = "typed-extractor-taxonomy-l1-dev-v1"
L2_DATASET_ID = "typed-extractor-taxonomy-l2-dev-v1"
NAMESPACES = {
    "l1": "typed-extractor-taxonomy-l1-dev-v1:2026-07-29",
    "l2": "typed-extractor-taxonomy-l2-dev-v1:2026-07-29",
}
L1_PRIMARY_COUNTS = {
    "condition_or_scope": 3,
    "derivation_or_speaker": 1,
    "evidence": 2,
    "false_abstention": 3,
    "false_emission": 3,
    "lifecycle": 1,
    "role_or_local_entity": 4,
    "time": 3,
}
L2_PRIMARY_COUNTS = {
    "coreference_case": 2,
    "incompatible_support_control": 1,
    "incomplete_closure_control": 1,
    "lifecycle_case": 2,
    "preference_aggregation_case": 1,
    "state_summary_case": 1,
    "task_composition_case": 2,
    "unresolved_selection_control": 1,
    "unsupported_modality_control": 1,
}
L2_METHOD_COUNTS = {
    "coreference_resolution": 2,
    "lifecycle_resolution": 2,
    "preference_aggregation": 1,
    "state_summary": 1,
    "task_composition": 2,
}
L1_TEMPLATE_SHA256 = "f0cd17d4a88f2d9299a75d2f8b12539943ff57e6f7922de3726803c3715a21a3"
L2_TEMPLATE_SHA256 = "fc3c336967a994ed6cd1bb33bf98d6d93fcf8cd5ac87e36eea7c7a9935cc07bf"


L1_CASE_SPECS: tuple[tuple[str, str, str | None, dict[str, str]], ...] = (
    (
        "control-question-no-durable-fact",
        "question-scanner-color",
        None,
        {
            "Is the printer blue?": "Is the document scanner green?",
            "I do not have that information.": "That color detail is unavailable.",
            "The printer may be blue.": "The document scanner may be green.",
            "the printer": "the document scanner",
            "blue": "green",
        },
    ),
    (
        "control-instruction-no-state",
        "instruction-single-sentence",
        None,
        {
            "Answer in one line.": "Respond using a single sentence.",
            "Understood.": "I will follow that response format.",
            "The answer format is one line.": "The response format is one sentence.",
            "the answer": "the response",
            "one line": "one sentence",
        },
    ),
    (
        "unsupported-modal-rumor",
        "unverified-studio-rumor",
        "false_emission",
        {
            "Someone said Ava might own the red cabin.": "A colleague claimed Elise may lease the amber studio.",
            "That report is not verified.": "The studio claim has no verification.",
            "Ava owns the red cabin.": "Elise leases the amber studio.",
            "Ava": "Elise",
            "owns": "leases",
            "the red cabin": "the amber studio",
            "might own": "may lease",
        },
    ),
    (
        "insufficient-evidence-attribution",
        "unresolved-proposal-endorser",
        None,
        {
            "They praised the draft.": "Someone endorsed the proposal.",
            "No person was identified.": "The endorser was not identified.",
            "A specific reviewer praised the draft.": "A named reviewer endorsed the proposal.",
            "a specific reviewer": "a named reviewer",
            "praised": "endorsed",
            "the draft": "the proposal",
        },
    ),
    (
        "valid-user-state",
        "explicit-user-rested-state",
        None,
        {
            "I feel calm today.": "I feel rested this afternoon.",
            "Noted.": "I recorded that current state.",
            "The user feels calm.": "The user feels rested.",
            "calm": "rested",
        },
    ),
    (
        "valid-requested-task",
        "explicit-review-with-luis",
        None,
        {
            "Please schedule a review with Dana.": "Please arrange a review with Luis.",
            "I will prepare the request.": "I will prepare that review request.",
            "The user requests a review with Dana.": "The user requests a review with Luis.",
            "Dana": "Luis",
        },
    ),
    (
        "valid-tool-event",
        "tool-backup-job-91",
        None,
        {
            "Run the backup now.": "Start the backup immediately.",
            "Tool: backup job 73 completed.": "Tool: backup job 91 completed successfully.",
            "Backup job 73 completed.": "Backup job 91 completed successfully.",
            "backup job 73": "backup job 91",
        },
    ),
    (
        "evidence-same-speaker-distractor",
        "approval-with-same-speaker-distractor",
        None,
        {
            "Mira approved Atlas. Earlier, Mira reviewed Orion.": "Tessa approved Harbor. Earlier, Tessa reviewed Quartz.",
            "The approval was recorded.": "The Harbor approval was recorded.",
            "Mira": "Tessa",
            "Atlas": "Harbor",
            "Orion": "Quartz",
        },
    ),
    (
        "evidence-cross-speaker-distractor",
        "archive-request-cross-speaker",
        None,
        {
            "Ravi asked Nia to archive Cedar.": "Nolan asked Iris to archive Maple.",
            "I will remind Nia tomorrow.": "I will remind Iris next week.",
            "Ravi": "Nolan",
            "Nia": "Iris",
            "Cedar": "Maple",
            "tomorrow": "next week",
        },
    ),
    (
        "condition-explicit-approver",
        "publish-if-owen-approves",
        None,
        {
            "Sam will publish Beacon if Lee approves.": "Imani will publish Comet if Owen approves.",
            "The approval condition is clear.": "The Comet approval condition is explicit.",
            "Sam": "Imani",
            "Beacon": "Comet",
            "Lee": "Owen",
        },
    ),
    (
        "scope-explicit-project",
        "navigation-preference-aurora-scope",
        None,
        {
            "I prefer the compact layout for Project Kestrel.": "I prefer dense navigation for Project Aurora.",
            "That project scope is noted.": "The Aurora project scope is recorded.",
            "the compact layout": "dense navigation",
            "Project Kestrel": "Project Aurora",
        },
    ),
    (
        "resolved-calendar-valid-time",
        "permit-expiration-date",
        None,
        {
            "The access expires on 2026-09-14.": "The permit expires on 2027-02-11.",
            "The date is recorded.": "The permit date is recorded.",
            "the access": "the permit",
            "2026-09-14": "2027-02-11",
        },
    ),
    (
        "unresolved-deictic-time",
        "supplier-call-next-week",
        None,
        {
            "I will call the vendor tomorrow.": "I will call the supplier next week.",
            "No calendar anchor is available.": "No calendar anchor resolves next week.",
            "The user plans to call the vendor tomorrow.": "The user plans to call the supplier next week.",
            "the vendor": "the supplier",
            "tomorrow": "next week",
        },
    ),
    (
        "role-two-people-transfer",
        "badge-transfer-recipient",
        None,
        {
            "Nora transferred the key to Omar.": "Elian transferred the badge to Suri.",
            "The transfer was recorded.": "The badge transfer was recorded.",
            "Nora": "Elian",
            "the key": "the badge",
            "Omar": "Suri",
        },
    ),
    (
        "role-agent-versus-beneficiary",
        "agent-books-visit-for-marin",
        None,
        {
            "The agent booked a clinic visit for Priya.": "The agent booked a specialist visit for Marin.",
            "The booking is complete.": "The specialist booking is complete.",
            "a clinic visit": "a specialist visit",
            "Priya": "Marin",
        },
    ),
    (
        "lifecycle-correction-confirmation",
        "receipt-recipient-correction",
        None,
        {
            "Correction: send the invoice to Sol, not Ren.": "Correction: send the receipt to Jade, not Kai.",
            "Confirmed: the invoice recipient is Sol.": "Confirmed: the receipt recipient is Jade.",
            "The invoice recipient is Sol.": "The receipt recipient is Jade.",
            "invoice recipient": "receipt recipient",
            "the invoice": "the receipt",
            "Sol": "Jade",
            "Ren": "Kai",
        },
    ),
    (
        "role-two-people-transfer",
        "folder-transfer-custodian",
        None,
        {
            "Nora transferred the key to Omar.": "Rhea transferred the folder to Dario.",
            "The transfer was recorded.": "The folder transfer was recorded.",
            "Nora": "Rhea",
            "the key": "the folder",
            "Omar": "Dario",
        },
    ),
    (
        "role-agent-versus-beneficiary",
        "agent-books-consult-for-kenji",
        None,
        {
            "The agent booked a clinic visit for Priya.": "The agent booked a dental visit for Kenji.",
            "The booking is complete.": "The dental booking is complete.",
            "a clinic visit": "a dental visit",
            "Priya": "Kenji",
        },
    ),
    (
        "resolved-calendar-valid-time",
        "license-expiration-date",
        None,
        {
            "The access expires on 2026-09-14.": "The license expires on 2027-06-03.",
            "The date is recorded.": "The license date is recorded.",
            "the access": "the license",
            "2026-09-14": "2027-06-03",
        },
    ),
    (
        "condition-explicit-approver",
        "deploy-if-sana-approves",
        None,
        {
            "Sam will publish Beacon if Lee approves.": "Marek will publish Nova if Sana approves.",
            "The approval condition is clear.": "The Nova approval condition is explicit.",
            "Sam": "Marek",
            "Beacon": "Nova",
            "Lee": "Sana",
        },
    ),
)


L2_REPLACEMENTS: dict[str, dict[str, str]] = {
    "abstain-unsupported-modality": {
        "Milo": "Keira",
        "the audit": "the inventory review",
        "The audit possibility remains unverified.": "The review possibility remains unverified.",
        "A rumor repeats that possibility.": "A secondhand note repeats that possibility.",
        "No direct confirmation was supplied.": "No direct confirmation supports the note.",
    },
    "abstain-unresolved-selected-option": {
        "Option Cedar": "Option Juniper",
        "40 credits": "65 credits",
        "Only Cedar is described in this turn.": "Only Juniper is described in this turn.",
        "Choose the earlier one.": "Select the previous one.",
        "The referenced option is not recoverable.": "The referenced selection is not recoverable.",
        "an earlier option": "a previous option",
    },
    "abstain-incompatible-supports": {
        "Oslo": "Riga",
        "Lima": "Perth",
        "one report": "the first report",
        "the earlier report": "the first report",
    },
    "abstain-incomplete-evidence-closure": {
        "Juno": "Ari",
        "the migration plan": "the retention plan",
        "The approval happened in another channel.": "The approval occurred in an unavailable workspace.",
        "The approval source is unavailable here.": "That approval source is unavailable in this record.",
        "The draft event is directly supported.": "The retention draft is directly supported.",
    },
    "emit-coreference-device-request": {
        "The tablet": "The handheld terminal",
        "the tablet": "the handheld terminal",
        "a battery check": "a firmware check",
        "Please service that device.": "Please inspect that device.",
        "The request refers to the tablet.": "The request resolves to the handheld terminal.",
        "The tablet is the active device.": "The terminal is the active device.",
    },
    "emit-coreference-document-reference": {
        "The budget memo": "The staffing brief",
        "the budget memo": "the staffing brief",
        "shared folder": "team folder",
        "The memo is now the active document.": "The brief is now the active document.",
        "Archive that document after review.": "Archive that document after approval.",
        "That document resolves to the budget memo.": "That document resolves to the staffing brief.",
    },
    "emit-task-composition-release": {
        "build 7": "release 12",
        "Build 7": "Release 12",
        "Prepare": "Stage",
        "Publish it after the tests pass.": "Release it once the tests pass.",
        "successful tests": "completed tests",
    },
    "emit-task-composition-travel": {
        "Leeds": "Ghent",
        "York": "Bruges",
        "Friday": "Monday",
        "train": "coach",
        "outbound leg": "first leg",
        "return leg": "second leg",
    },
    "emit-lifecycle-commitment": {
        "a design review": "a security review",
        "the design review": "the security review",
        "Tuesday": "Thursday",
        "under consideration": "tentative",
        "The later turn commits to the review.": "The later turn commits to the security review.",
    },
    "emit-lifecycle-supersession": {
        "the report": "the dossier",
        "Uma": "Lena",
        "Vic": "Noor",
        "initial recipient": "original recipient",
        "supersedes Uma": "supersedes Lena",
    },
    "emit-state-summary": {
        "My wrist": "My shoulder",
        "wrist soreness": "shoulder stiffness",
        "The soreness": "The stiffness",
        "the soreness": "the stiffness",
        "after typing": "after lifting boxes",
        "this morning": "this evening",
        "The later observation shows persistence.": "The second observation confirms persistence.",
    },
    "emit-preference-aggregation": {
        "quiet rooms": "aisle seats",
        "seats away from doors": "rooms away from elevators",
        "Door distance": "Elevator distance",
        "Quiet rooms": "Aisle seats",
    },
}


class L1TaxonomySource(StrictModel):
    schema_version: Literal["typed-extractor-taxonomy-l1-source-v1"]
    dataset_id: Literal["typed-extractor-taxonomy-l1-dev-v1"]
    provenance: Literal["diagnostic_authored"]
    authoring_policy: Literal["diagnostic_template_transformation_no_hidden_input"]
    template_source_sha256: str
    public_vocabulary: dict[str, list[str]]
    cases: list[l1_dev.L1DiagnosticCase]

    @model_validator(mode="after")
    def validate_contract(self) -> "L1TaxonomySource":
        if len(self.cases) != 20:
            raise ValueError("L1 taxonomy source must contain exactly 20 cases")
        private_ids = [case.private_case_id for case in self.cases]
        if len(private_ids) != len(set(private_ids)):
            raise ValueError("duplicate L1 taxonomy private case ID")
        knowledge_ids = [case.authority.knowledge_id for case in self.cases]
        if len(knowledge_ids) != len(set(knowledge_ids)):
            raise ValueError("duplicate L1 authority knowledge ID")
        candidate_ids = [case.authority.candidate_id for case in self.cases]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate L1 authority candidate ID")
        counts = dict(sorted(Counter(x.primary_family for x in self.cases).items()))
        if counts != L1_PRIMARY_COUNTS:
            raise ValueError("L1 taxonomy primary-family distribution differs")
        if set(self.public_vocabulary) & set(l1_dev._BASE_VOCABULARY):
            raise ValueError("L1 taxonomy vocabulary overrides a base catalog")
        return self


class L2TaxonomySource(StrictModel):
    schema_version: Literal["typed-extractor-taxonomy-l2-source-v1"]
    dataset_id: Literal["typed-extractor-taxonomy-l2-dev-v1"]
    provenance: Literal["diagnostic_authored"]
    authoring_policy: Literal["diagnostic_template_transformation_no_hidden_input"]
    template_source_sha256: str
    public_vocabulary: dict[str, list[str]]
    cases: list[l2_dev.L2DiagnosticCase]

    @model_validator(mode="after")
    def validate_contract(self) -> "L2TaxonomySource":
        if len(self.cases) != 12:
            raise ValueError("L2 taxonomy source must contain exactly 12 cases")
        private_ids = [case.private_case_id for case in self.cases]
        if len(private_ids) != len(set(private_ids)):
            raise ValueError("duplicate L2 taxonomy private case ID")
        knowledge_ids = [case.authority.knowledge_id for case in self.cases]
        if len(knowledge_ids) != len(set(knowledge_ids)):
            raise ValueError("duplicate L2 authority knowledge ID")
        candidate_ids = [case.authority.candidate_id for case in self.cases]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate L2 authority candidate ID")
        counts = dict(sorted(Counter(x.primary_family for x in self.cases).items()))
        if counts != L2_PRIMARY_COUNTS:
            raise ValueError("L2 taxonomy primary-family distribution differs")
        if set(self.public_vocabulary) & set(l2_dev._BASE_VOCABULARY):
            raise ValueError("L2 taxonomy vocabulary overrides a base catalog")
        return self


_TEXT_KEYS = {
    "agent",
    "allowed_condition_values",
    "allowed_event_times",
    "allowed_scope_values",
    "allowed_valid_times",
    "basis",
    "event_time",
    "inference_basis",
    "object",
    "predicate",
    "quote",
    "statement",
    "subject",
    "summary",
    "surface",
    "user",
    "valid_time",
    "value",
}


def _replace_text(
    value: Any,
    replacements: dict[str, str],
    key: str | None = None,
    inherited_text: bool = False,
) -> Any:
    textual = inherited_text or key == "qualifiers"
    if isinstance(value, dict):
        return {
            child_key: _replace_text(
                child,
                replacements,
                child_key,
                textual,
            )
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _replace_text(item, replacements, key, textual) for item in value
        ]
    if isinstance(value, str) and (textual or key in _TEXT_KEYS):
        for old, new in sorted(replacements.items(), key=lambda item: -len(item[0])):
            value = value.replace(old, new)
    return value


def _replace_private_ids(value: Any, layer: Layer, ordinal: int) -> Any:
    replacements: dict[str, str] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, str) and node.startswith("diag-"):
            digest = hashlib.sha256(node.encode()).hexdigest()[:12]
            replacements[node] = f"taxonomy-{layer}-{ordinal:02d}-{digest}"

    visit(value)

    def apply(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: apply(child) for key, child in node.items()}
        if isinstance(node, list):
            return [apply(child) for child in node]
        if isinstance(node, str):
            return replacements.get(node, node)
        return node

    return apply(value)


def _recompute_l1_evidence(case: dict[str, Any]) -> None:
    for evidence in case["untyped_candidate"]["evidence"]:
        message = case["source_turn"][evidence["message"]]
        quote = evidence["quote"]
        positions = [
            index for index in range(len(message)) if message.startswith(quote, index)
        ]
        if len(positions) != 1:
            raise ValueError(
                f"authored L1 evidence is not unique: {case['private_case_id']}"
            )
        evidence["start"] = positions[0]
        evidence["end"] = positions[0] + len(quote)
        evidence["occurrence_index"] = 0


def _recompute_l2_evidence(case: dict[str, Any]) -> None:
    for evidence in case["untyped_candidate"]["evidence"]:
        quote = evidence["quote"]
        matches: list[int] = []
        for turn in case["source_turns"]:
            message = turn[evidence["message"]]
            matches.extend(
                index
                for index in range(len(message))
                if message.startswith(quote, index)
            )
        if len(matches) != 1:
            raise ValueError(
                f"authored L2 evidence is not unique: {case['private_case_id']}"
            )
        evidence["start"] = matches[0]
        evidence["end"] = matches[0] + len(quote)
        evidence["occurrence_index"] = 0


def _author_l1_payload(template: dict[str, Any]) -> L1TaxonomySource:
    by_id = {case["private_case_id"]: case for case in template["cases"]}
    cases: list[dict[str, Any]] = []
    for ordinal, (base_id, new_id, primary, replacements) in enumerate(
        L1_CASE_SPECS,
        start=1,
    ):
        case = _replace_private_ids(copy.deepcopy(by_id[base_id]), "l1", ordinal)
        case["private_case_id"] = new_id
        if primary is not None:
            old_primary = case["primary_family"]
            case["primary_family"] = primary
            case["secondary_families"] = [
                item for item in case["secondary_families"] if item != primary
            ]
            if old_primary not in case["secondary_families"]:
                case["secondary_families"].append(old_primary)
        case = _replace_text(case, replacements)
        _recompute_l1_evidence(case)
        cases.append(case)
    payload = L1TaxonomySource(
        schema_version="typed-extractor-taxonomy-l1-source-v1",
        dataset_id=L1_DATASET_ID,
        provenance="diagnostic_authored",
        authoring_policy="diagnostic_template_transformation_no_hidden_input",
        template_source_sha256=L1_TEMPLATE_SHA256,
        public_vocabulary=template["public_vocabulary"],
        cases=cases,
    )
    old_text = _scan_json(template)[2]
    new_text = _scan_json(payload.model_dump(mode="json"))[2]
    if old_text & new_text:
        raise ValueError("authored L1 evidence text overlaps its template")
    return payload


def _author_l2_payload(template: dict[str, Any]) -> L2TaxonomySource:
    cases: list[dict[str, Any]] = []
    for ordinal, source_case in enumerate(template["cases"], start=1):
        old_id = source_case["private_case_id"]
        case = _replace_private_ids(copy.deepcopy(source_case), "l2", ordinal)
        case["private_case_id"] = f"taxonomy-{old_id}"
        case = _replace_text(case, L2_REPLACEMENTS[old_id])
        _recompute_l2_evidence(case)
        cases.append(case)
    payload = L2TaxonomySource(
        schema_version="typed-extractor-taxonomy-l2-source-v1",
        dataset_id=L2_DATASET_ID,
        provenance="diagnostic_authored",
        authoring_policy="diagnostic_template_transformation_no_hidden_input",
        template_source_sha256=L2_TEMPLATE_SHA256,
        public_vocabulary=template["public_vocabulary"],
        cases=cases,
    )
    old_text = _scan_json(template)[2]
    new_text = _scan_json(payload.model_dump(mode="json"))[2]
    if old_text & new_text:
        raise ValueError("authored L2 evidence text overlaps its template")
    return payload


def author_taxonomy_dev_sources(
    l1_template_path: Path,
    l2_template_path: Path,
    l1_output_path: Path,
    l2_output_path: Path,
) -> dict[str, Any]:
    l1_template_path = l1_template_path.resolve()
    l2_template_path = l2_template_path.resolve()
    l1_output_path = l1_output_path.resolve()
    l2_output_path = l2_output_path.resolve()
    for path, label, expected_hash in (
        (l1_template_path, "L1 diagnostic template", L1_TEMPLATE_SHA256),
        (l2_template_path, "L2 diagnostic template", L2_TEMPLATE_SHA256),
    ):
        _require_read_only(path, label)
        if sha256_file(path) != expected_hash:
            raise ValueError(f"{label} hash drift")
    for path in (l1_output_path, l2_output_path):
        if path.exists() or path.parent.exists():
            raise ValueError(f"taxonomy output must be wholly absent: {path}")
        if not path.parent.parent.is_dir():
            raise FileNotFoundError(f"taxonomy output parent missing: {path.parent.parent}")
    l1_payload = _author_l1_payload(load_json(l1_template_path))
    l2_payload = _author_l2_payload(load_json(l2_template_path))
    for path, payload in (
        (l1_output_path, l1_payload),
        (l2_output_path, l2_payload),
    ):
        path.parent.mkdir()
        write_json_immutable(path, payload)
        path.chmod(0o444)
    return {
        "status": "authored",
        "l1_case_count": len(l1_payload.cases),
        "l2_case_count": len(l2_payload.cases),
        "l1_source_sha256": sha256_file(l1_output_path),
        "l2_source_sha256": sha256_file(l2_output_path),
    }


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _opaque_ref(prefix: str, value: str, namespace: str) -> str:
    digest = hashlib.sha256(f"{namespace}:{prefix}:{value}".encode()).hexdigest()
    length = 64 if prefix == "evidence" else 16
    return f"{prefix}-{digest[:length]}"


def _scan_json(value: Any) -> tuple[set[str], set[str], set[str]]:
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_text: set[str] = set()
    identifier_keys = {
        "case_id",
        "candidate_ref",
        "private_case_id",
        "private_session_id",
        "private_turn_id",
        "private_support_id",
        "knowledge_id",
        "candidate_id",
        "support_ref",
        "supporting_l1_refs",
        "required_support_refs",
        "optional_support_refs",
        "source_turn_ref",
        "source_turn_refs",
        "source_session_ref",
        "source_session_refs",
        "replacement_candidate_ref",
        "replaces_candidate_refs",
        "supersedes_candidate_refs",
        "conflicts_with_candidate_refs",
        "confirmed_by_operation_refs",
        "added_by_operation_refs",
    }

    def visit(node: Any, key: str | None = None) -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                visit(child, child_key)
        elif isinstance(node, list):
            for child in node:
                visit(child, key)
        elif isinstance(node, str) and key:
            if key in {"evidence_id", "evidence_ids"}:
                evidence_ids.add(node)
            elif key in identifier_keys:
                identifiers.add(node)
            elif key in {"quote", "user", "agent"}:
                evidence_text.add(node)

    visit(value)
    return identifiers, evidence_ids, evidence_text


def _prior_inventory(
    prior_roots: Sequence[Path],
    *,
    bind_l1_root: bool,
) -> tuple[set[str], set[str], set[str], dict[str, str], dict[str, str]]:
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_text: set[str] = set()
    fingerprints: dict[str, str] = {}
    l1_hashes: dict[str, str] = {}
    l1_names = (
        "diagnostic-source-l1.json",
        "public-l1.json",
        "authority-l1.json",
        "gold-l1.json",
        "manifest-l1.json",
    )
    for index, root_value in enumerate(prior_roots):
        root = root_value.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"prior root missing: {root}")
        is_l1_taxonomy = all((root / name).is_file() for name in l1_names)
        paths = (
            [root / name for name in l1_names]
            if is_l1_taxonomy
            else sorted(path for path in root.rglob("*.json") if path.is_file())
        )
        if not paths:
            raise ValueError(f"prior root has no JSON artifacts: {root}")
        digest = hashlib.sha256()
        for path in paths:
            relative = path.relative_to(root).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
            found_ids, found_evidence, found_text = _scan_json(load_json(path))
            identifiers.update(found_ids)
            evidence_ids.update(found_evidence)
            evidence_text.update(found_text)
        fingerprints[f"prior_root_{index:02d}"] = digest.hexdigest()
        if is_l1_taxonomy and bind_l1_root:
            if l1_hashes:
                raise ValueError("multiple L1 taxonomy roots are bound")
            l1_hashes = {name: sha256_file(root / name) for name in l1_names}
    return identifiers, evidence_ids, evidence_text, fingerprints, l1_hashes


def _validate_l1_catalog(source: L1TaxonomySource) -> None:
    vocabulary = {**l1_dev._BASE_VOCABULARY, **source.public_vocabulary}
    for case in source.cases:
        l1_dev._validate_evidence(case)
        candidate = case.expected_typed_candidate
        if candidate is None:
            continue
        operator = candidate.predicate.canonical_operator
        if operator not in vocabulary["canonical_operators"]:
            raise ValueError("L1 taxonomy operator catalog mismatch")
        if candidate.predicate.sense not in vocabulary["predicate_senses"]:
            raise ValueError("L1 taxonomy predicate-sense catalog mismatch")
        if f"{operator}|{candidate.kind}" not in vocabulary["operator_kind_bindings"]:
            raise ValueError("L1 taxonomy operator-kind catalog mismatch")
        required_roles = {
            f"{operator}|{role.role}|{role.role_name}" for role in candidate.roles
        }
        if not required_roles.issubset(vocabulary["operator_role_bindings"]):
            raise ValueError("L1 taxonomy operator-role catalog mismatch")


def _validate_l2_catalog(source: L2TaxonomySource) -> None:
    vocabulary = {**l2_dev._BASE_VOCABULARY, **source.public_vocabulary}
    for case in source.cases:
        l2_dev._validate_case(case)
        candidate = case.expected_typed_candidate
        if candidate is None:
            continue
        for claim in candidate.structured_claims:
            operator = claim.predicate.canonical_operator
            if operator not in vocabulary["canonical_operators"]:
                raise ValueError("L2 taxonomy operator catalog mismatch")
            if claim.predicate.sense not in vocabulary["predicate_senses"]:
                raise ValueError("L2 taxonomy predicate-sense catalog mismatch")
            if f"{operator}|{candidate.kind}" not in vocabulary["operator_kind_bindings"]:
                raise ValueError("L2 taxonomy operator-kind catalog mismatch")
            if (
                f"{operator}|{claim.predicate.sense}"
                not in vocabulary["operator_sense_bindings"]
            ):
                raise ValueError("L2 taxonomy operator-sense catalog mismatch")


def _check_overlap(source: StrictModel, layer: Layer, prior_roots: Sequence[Path]) -> tuple[dict[str, str], dict[str, str]]:
    prior_ids, prior_evidence, prior_text, hashes, l1_hashes = _prior_inventory(
        prior_roots,
        bind_l1_root=layer == "l2",
    )
    source_ids, source_evidence, source_text = _scan_json(
        source.model_dump(mode="json")
    )
    namespace = NAMESPACES[layer]
    opaque_ids: set[str] = set()
    opaque_evidence = {
        _opaque_ref("evidence", item, namespace) for item in source_evidence
    }
    if layer == "l1":
        for case in source.cases:  # type: ignore[attr-defined]
            opaque_ids.add(_opaque_ref("case", case.private_case_id, namespace))
            opaque_ids.add(_opaque_ref("candidate", case.private_case_id, namespace))
    else:
        for case in source.cases:  # type: ignore[attr-defined]
            opaque_ids.update(
                {
                    _opaque_ref("case", case.private_case_id, namespace),
                    _opaque_ref("candidate", case.private_case_id, namespace),
                    _opaque_ref("session", case.private_session_id, namespace),
                }
            )
            opaque_ids.update(
                _opaque_ref("turn", item.private_turn_id, namespace)
                for item in case.source_turns
            )
            opaque_ids.update(
                _opaque_ref("support", item.private_support_id, namespace)
                for item in case.typed_l1_support_pack
            )
    if (source_ids | opaque_ids) & prior_ids:
        raise ValueError("prior identifier overlap detected")
    if (source_evidence | opaque_evidence) & prior_evidence or source_text & prior_text:
        raise ValueError("prior evidence overlap detected")
    return hashes, l1_hashes


def _build_l1(
    source_path: Path, prior_roots: Sequence[Path]
) -> tuple[L1PublicPayload, L1AuthorityPayload, L1GoldPayload, dict[str, Any], dict[str, str]]:
    _require_read_only(source_path, "L1 taxonomy source")
    source = L1TaxonomySource.model_validate(load_json(source_path))
    _validate_l1_catalog(source)
    prior_hashes, _ = _check_overlap(source, "l1", prior_roots)
    namespace = NAMESPACES["l1"]
    public_cases: list[L1PublicCase] = []
    authority_cases: list[L1AuthorityCase] = []
    gold_items: list[L1GoldItem] = []
    for case in source.cases:
        case_id = _opaque_ref("case", case.private_case_id, namespace)
        candidate_ref = _opaque_ref("candidate", case.private_case_id, namespace)
        authority = case.authority
        public_cases.append(
            L1PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_turn=case.source_turn,
                untyped_candidate=l1_dev._remap_untyped_candidate(
                    case.untyped_candidate, namespace
                ),
            )
        )
        authority_cases.append(
            L1AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=authority.knowledge_id,
                candidate_id=authority.candidate_id,
                emission_allowed=authority.emission_allowed,
                required_evidence_bindings=[
                    l1_dev._remap_evidence_binding(item, namespace)
                    for item in authority.required_evidence_bindings
                ],
                allowed_modalities=authority.allowed_modalities,
                allowed_polarities=authority.allowed_polarities,
                allowed_event_times=authority.allowed_event_times,
                event_time_may_be_null=authority.event_time_may_be_null,
                allowed_valid_times=authority.allowed_valid_times,
                valid_time_may_be_null=authority.valid_time_may_be_null,
                allowed_condition_values=authority.allowed_condition_values,
                allowed_scope_values=authority.allowed_scope_values,
                required_derivation=l1_dev._remap_derivation(
                    authority.required_derivation, namespace
                ),
                required_lifecycle=l1_dev._remap_lifecycle(
                    authority.required_lifecycle, namespace
                ),
                required_operation_provenance=l1_dev._remap_operations(
                    authority.required_operation_provenance, namespace
                ),
                unresolved_required_fields=authority.unresolved_required_fields,
                automatic_write_authorizations=AutomaticWriteAuthorizations(),
            )
        )
        gold_items.append(
            L1GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=case.expected_decision,
                expected_typed_candidate=(
                    l1_dev._remap_typed_candidate(
                        case.expected_typed_candidate, namespace
                    )
                    if case.expected_typed_candidate
                    else None
                ),
            )
        )
    decisions = Counter(case.expected_decision for case in source.cases)
    distribution = {
        "provenance": source.provenance,
        "diagnostic_only": True,
        "primary_family_counts": dict(
            sorted(Counter(case.primary_family for case in source.cases).items())
        ),
        "decision_counts": dict(sorted(decisions.items())),
        "non_emission_count": sum(x.expected_decision != "emit_l1" for x in source.cases),
        "prior_identifier_overlap_count": 0,
        "prior_evidence_overlap_count": 0,
    }
    if distribution["non_emission_count"] != 4:
        raise ValueError("L1 taxonomy requires exactly four non-emissions")
    public = L1PublicPayload(
        dataset_id=source.dataset_id,
        case_count=len(public_cases),
        allowed_vocabulary={**l1_dev._BASE_VOCABULARY, **source.public_vocabulary},
        cases=public_cases,
    )
    authority = L1AuthorityPayload(
        dataset_id=source.dataset_id,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L1GoldPayload(
        dataset_id=source.dataset_id,
        case_count=len(gold_items),
        items=gold_items,
    )
    return public, authority, gold, distribution, prior_hashes


def _build_l2(
    source_path: Path, prior_roots: Sequence[Path]
) -> tuple[L2PublicPayload, L2AuthorityPayload, L2GoldPayload, dict[str, Any], dict[str, str], dict[str, str]]:
    _require_read_only(source_path, "L2 taxonomy source")
    source = L2TaxonomySource.model_validate(load_json(source_path))
    _validate_l2_catalog(source)
    prior_hashes, l1_hashes = _check_overlap(source, "l2", prior_roots)
    if not l1_hashes:
        raise ValueError("one L1 taxonomy root must be bound")
    namespace = NAMESPACES["l2"]
    public_cases: list[L2PublicCase] = []
    authority_cases: list[L2AuthorityCase] = []
    gold_items: list[L2GoldItem] = []
    for case in source.cases:
        case_id = _opaque_ref("case", case.private_case_id, namespace)
        candidate_ref = _opaque_ref("candidate", case.private_case_id, namespace)
        authority = case.authority
        public_cases.append(
            L2PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_session_ref=_opaque_ref(
                    "session", case.private_session_id, namespace
                ),
                source_turns=[
                    L2PublicTurn(
                        source_turn_ref=_opaque_ref(
                            "turn", turn.private_turn_id, namespace
                        ),
                        turn_index=turn.turn_index,
                        user=turn.user,
                        agent=turn.agent,
                    )
                    for turn in case.source_turns
                ],
                untyped_candidate=l2_dev._remap_untyped(
                    case.untyped_candidate, namespace
                ),
                typed_l1_support_pack=[
                    l2_dev._remap_support(
                        item, case.private_session_id, namespace
                    )
                    for item in case.typed_l1_support_pack
                ],
            )
        )
        authority_cases.append(
            L2AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=authority.knowledge_id,
                candidate_id=authority.candidate_id,
                emission_allowed=authority.emission_allowed,
                required_support_refs=[
                    _opaque_ref("support", item, namespace)
                    for item in authority.required_support_refs
                ],
                required_evidence_bindings=[
                    l2_dev._remap_evidence(item, namespace)
                    for item in authority.required_evidence_bindings
                ],
                required_source_turn_refs=[
                    _opaque_ref("turn", item, namespace)
                    for item in authority.required_source_turn_refs
                ],
                required_source_session_refs=[
                    _opaque_ref("session", item, namespace)
                    for item in authority.required_source_session_refs
                ],
                allowed_abstraction_methods=authority.allowed_abstraction_methods,
                allowed_closure_patterns=authority.allowed_closure_patterns,
                unresolved_required_fields=authority.unresolved_required_fields,
                automatic_write_authorizations=AutomaticWriteAuthorizations(),
            )
        )
        gold_items.append(
            L2GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=case.expected_decision,
                expected_typed_candidate=(
                    l2_dev._remap_candidate(case.expected_typed_candidate, namespace)
                    if case.expected_typed_candidate
                    else None
                ),
            )
        )
    emitted = [
        case.expected_typed_candidate
        for case in source.cases
        if case.expected_typed_candidate is not None
    ]
    methods = dict(sorted(Counter(x.abstraction.method for x in emitted).items()))
    if methods != L2_METHOD_COUNTS:
        raise ValueError("L2 taxonomy abstraction distribution differs")
    distribution = {
        "provenance": source.provenance,
        "diagnostic_only": True,
        "primary_family_counts": dict(
            sorted(Counter(case.primary_family for case in source.cases).items())
        ),
        "abstraction_method_counts": methods,
        "emit_count": len(emitted),
        "abstain_count": sum(x.expected_decision == "abstain" for x in source.cases),
        "prior_identifier_overlap_count": 0,
        "prior_evidence_overlap_count": 0,
    }
    if distribution["emit_count"] != 8 or distribution["abstain_count"] != 4:
        raise ValueError("L2 taxonomy decision distribution differs")
    public = L2PublicPayload(
        dataset_id=source.dataset_id,
        case_count=len(public_cases),
        allowed_vocabulary={**l2_dev._BASE_VOCABULARY, **source.public_vocabulary},
        cases=public_cases,
    )
    authority = L2AuthorityPayload(
        dataset_id=source.dataset_id,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L2GoldPayload(
        dataset_id=source.dataset_id,
        case_count=len(gold_items),
        items=gold_items,
    )
    return public, authority, gold, distribution, prior_hashes, l1_hashes


def _payloads(source_path: Path, layer: Layer, prior_roots: Sequence[Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    if layer == "l1":
        public, authority, gold, distribution, prior_hashes = _build_l1(
            source_path, prior_roots
        )
        l1_hashes: dict[str, str] = {}
    elif layer == "l2":
        public, authority, gold, distribution, prior_hashes, l1_hashes = _build_l2(
            source_path, prior_roots
        )
    else:
        raise ValueError(f"unsupported taxonomy layer: {layer}")
    return (
        {
            f"authority-{layer}.json": authority,
            f"gold-{layer}.json": gold,
            f"public-{layer}.json": public,
        },
        distribution,
        {**prior_hashes, **{f"l1:{k}": v for k, v in l1_hashes.items()}},
    )


def _manifest(
    source_path: Path,
    layer: Layer,
    output_root: Path,
    outputs: dict[str, Any],
    distribution: dict[str, Any],
    bindings: dict[str, str],
) -> L1Manifest | L2Manifest:
    public = outputs[f"public-{layer}.json"]
    common = {
        "dataset_id": public.dataset_id,
        "case_count": public.case_count,
        "input_sha256": {
            "diagnostic_source": sha256_file(source_path),
            **{k: v for k, v in bindings.items() if not k.startswith("l1:")},
        },
        "output_sha256": {
            name: sha256_file(output_root / name) for name in outputs
        },
        "distribution": distribution,
        "claim_boundary": {
            "automatic_authoritative_writes": False,
            "diagnostic_only": True,
            "embedding_authority": False,
            "fresh_hidden_v2_created": False,
            "fresh_hidden_created_by_this_wave": False,
            "pipeline_integration_authorized": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    }
    if layer == "l1":
        return L1Manifest(**common)
    return L2Manifest(
        **common,
        l1_qualification_sha256={
            key.removeprefix("l1:"): value
            for key, value in bindings.items()
            if key.startswith("l1:")
        },
        thresholds=dict(L2_DEV_THRESHOLDS),
    )


def prepare_taxonomy_dev_slice(
    source_path: Path,
    layer: Layer,
    output_root: Path,
    prior_roots: Sequence[Path],
) -> dict[str, Any]:
    source_path = source_path.resolve()
    output_root = output_root.resolve()
    if not output_root.is_dir():
        raise FileNotFoundError(f"taxonomy output root missing: {output_root}")
    outputs, distribution, bindings = _payloads(source_path, layer, prior_roots)
    for name, payload in outputs.items():
        write_json_immutable(output_root / name, payload)
        (output_root / name).chmod(0o444)
    manifest = _manifest(
        source_path, layer, output_root, outputs, distribution, bindings
    )
    write_json_immutable(output_root / f"manifest-{layer}.json", manifest)
    (output_root / f"manifest-{layer}.json").chmod(0o444)
    return {
        "status": "valid",
        "case_count": outputs[f"public-{layer}.json"].case_count,
        **distribution,
    }


def validate_taxonomy_dev_slice(
    source_path: Path,
    layer: Layer,
    root: Path,
    prior_roots: Sequence[Path],
) -> dict[str, Any]:
    source_path = source_path.resolve()
    root = root.resolve()
    outputs, distribution, bindings = _payloads(source_path, layer, prior_roots)
    for name, expected in outputs.items():
        path = root / name
        _require_read_only(path, name)
        if path.read_bytes() != canonical_json_bytes(expected):
            raise ValueError(f"taxonomy artifact drift: {name}")
    manifest_path = root / f"manifest-{layer}.json"
    _require_read_only(manifest_path, manifest_path.name)
    manifest_type = L1Manifest if layer == "l1" else L2Manifest
    actual = manifest_type.model_validate(load_json(manifest_path))
    expected_manifest = _manifest(
        source_path, layer, root, outputs, distribution, bindings
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected_manifest):
        raise ValueError(f"taxonomy manifest drift: {layer}")
    return {
        "status": "valid",
        "case_count": outputs[f"public-{layer}.json"].case_count,
        **distribution,
    }
