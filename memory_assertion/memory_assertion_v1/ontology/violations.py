"""Violations, and the total order they are reported in.

Order is part of the contract, not a presentation detail. A builder diffing two
validation runs needs the same snapshot to produce the same list, so violations sort by
(code, subject, detail) rather than by the order checks happen to run in. Reordering the
checks must not change the output.

Codes are an enum so a caller can branch on a specific failure without matching on
message text, and so a renamed message does not silently break a consumer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ViolationCode(StrEnum):
    """Every way a snapshot can fail the profile's semantic rules.

    Grouped by the batch that produces them: identity closure first, because the later
    batches read the maps it validates.
    """

    # Parse -- a record or profile that did not become a model at all.
    RECORD_PARSE_FAILED = "record_parse_failed"
    PROFILE_MISSING = "profile_missing"
    PROFILE_PARSE_FAILED = "profile_parse_failed"
    SHARD_MIXES_ARTIFACT_KINDS = "shard_mixes_artifact_kinds"
    ONTOLOGY_RECORD_MISSING = "ontology_record_missing"

    # Batch 1 -- identity and reference closure.
    DUPLICATE_CONCEPT_ID = "duplicate_concept_id"
    DUPLICATE_OPERATOR_ID = "duplicate_operator_id"
    DUPLICATE_CONCEPT_SYMBOL = "duplicate_concept_symbol"
    DUPLICATE_OPERATOR_SYMBOL = "duplicate_operator_symbol"
    UNRESOLVED_CONCEPT_REFERENCE = "unresolved_concept_reference"
    UNRESOLVED_OPERATOR_REFERENCE = "unresolved_operator_reference"
    CONCEPT_SELF_PARENT = "concept_self_parent"
    CONCEPT_INHERITANCE_CYCLE = "concept_inheritance_cycle"
    REPLACED_BY_WITHOUT_DEPRECATION = "replaced_by_without_deprecation"
    REPLACED_BY_SELF = "replaced_by_self"
    REPLACED_BY_UNRESOLVED = "replaced_by_unresolved"
    REPLACED_BY_CYCLE = "replaced_by_cycle"
    REPLACED_BY_CHAIN_ENDS_DEPRECATED = "replaced_by_chain_ends_deprecated"

    # Batch 2 -- Concept semantics.
    DISJOINT_SELF = "disjoint_self"
    DISJOINT_UNRESOLVED = "disjoint_unresolved"
    DISJOINT_ASYMMETRIC = "disjoint_asymmetric"
    DISJOINT_ANCESTOR_CONFLICT = "disjoint_ancestor_conflict"
    DISJOINT_UNSATISFIABLE_INHERITANCE = "disjoint_unsatisfiable_inheritance"
    LITERAL_CONTRACT_REQUIRED = "literal_contract_required"
    LITERAL_CONTRACT_FORBIDDEN = "literal_contract_forbidden"
    LITERAL_CODEC_KIND_MISMATCH = "literal_codec_kind_mismatch"
    MONEY_CONTRACT_INCOMPLETE = "money_contract_incomplete"
    QUANTITY_CONTRACT_INCOMPLETE = "quantity_contract_incomplete"
    CURRENCY_MINOR_UNITS_UNSORTED = "currency_minor_units_unsorted"
    CURRENCY_MINOR_UNITS_DUPLICATE = "currency_minor_units_duplicate"

    # Batch 3 -- Operator signatures.
    POSITIONAL_PARAMETER_COUNT_MISMATCH = "positional_parameter_count_mismatch"
    POSITIONAL_PARAMETER_INDEX_BROKEN = "positional_parameter_index_broken"
    POSITIONAL_PARAMETER_NAME_DUPLICATE = "positional_parameter_name_duplicate"
    PROPOSITION_OPERATION_INPUT_INVALID = "proposition_operation_input_invalid"
    PROPOSITION_OPERATION_OUTPUT_INVALID = "proposition_operation_output_invalid"
    DEFINEDNESS_CONTRACT_REQUIRED = "definedness_contract_required"
    DEFINEDNESS_CONTRACT_FORBIDDEN = "definedness_contract_forbidden"
    REQUIRED_INPUT_INDEXES_EMPTY = "required_input_indexes_empty"
    REQUIRED_INPUT_INDEXES_DUPLICATE = "required_input_indexes_duplicate"
    REQUIRED_INPUT_INDEXES_OUT_OF_RANGE = "required_input_indexes_out_of_range"
    RELATION_ENUM_CONFUSED = "relation_enum_confused"
    SOURCE_ATTESTATION_FIELDS_INVALID = "source_attestation_fields_invalid"


class Violation(BaseModel):
    """One failure, attributable to one subject.

    `subject` is the id of the offending record where there is one, or a shard position
    where the id itself is what failed to parse. `detail` carries the specifics a builder
    needs to locate it -- the field, the conflicting value -- and participates in the sort
    so that two violations differing only in detail still order deterministically.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ViolationCode
    subject: str
    detail: str = ""

    def sort_key(self) -> tuple[str, str, str]:
        return (str(self.code), self.subject, self.detail)


class QuarantineReason(BaseModel):
    """Why a snapshot cannot be provisioned even though it may be well-formed.

    Separate from Violation because the consequence differs: a violation says the
    snapshot is wrong, a quarantine reason says v1 cannot deliver it. A partial operator
    is the only current cause -- the runtime ships no content-addressed registry of
    definedness predicates, so provisioning must refuse rather than warn.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: Literal["partial_operator_unsupported"]
    subject: str
    detail: str = ""

    def sort_key(self) -> tuple[str, str, str]:
        return (self.code, self.subject, self.detail)
