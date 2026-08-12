"""The `supply.memory_assertion` profile carried by Concepts and Operators.

Upstream owns `id`, `description`, `sources`, `created_at`, `parents`,
`input_concepts`, `output_concept` and `version`; this profile adds nothing to them and
reinterprets none of them. Everything here lives under one namespace key, so a Concept
may carry other profiles' namespaces beside it without this one claiming to understand
them.

These models are closed (`extra="forbid"`), which is what makes the superseded
contract's vocabulary -- `roles`, `core_roles`, `qualifiers`, `operator_form` -- a
parse failure rather than a silently ignored field.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_assertion_v1.ids import ConceptId, OperatorId

PROFILE_VERSION = "memory-assertion/v1"

SemanticKind = Literal[
    "entity", "proposition", "event", "state", "literal_value", "ontology_symbol"
]
PropositionOperation = Literal["none", "modifier", "attitude", "relation"]
MappingRelation = Literal["exact", "narrow", "broad", "related"]
SurfaceRelation = Literal[
    "canonical_label", "equivalent_expression", "abbreviated_expression", "surface_variant"
]
DisambiguationStatus = Literal["resolved", "candidate"]
SourceKind = Literal["wordnet", "propbank", "schema_org", "human", "domain_corpus"]

BOOLEAN_CODEC = "ke-literal:boolean/v1"

# Closed by contract: an unknown codec makes the snapshot invalid, and declaring a
# capability does not extend the set. A new codec requires a new profile version.
CODEC_JSON_KINDS: dict[str, str] = {
    BOOLEAN_CODEC: "boolean",
    "ke-literal:text-nfc/v1": "string",
    "ke-literal:decimal/v1": "string",
    "ke-literal:date/v1": "string",
    "ke-literal:datetime/v1": "string",
    "ke-literal:duration/v1": "string",
    "ke-literal:money/v1": "object",
    "ke-literal:quantity/v1": "object",
}
CodecId = Literal[
    "ke-literal:boolean/v1",
    "ke-literal:text-nfc/v1",
    "ke-literal:decimal/v1",
    "ke-literal:date/v1",
    "ke-literal:datetime/v1",
    "ke-literal:duration/v1",
    "ke-literal:money/v1",
    "ke-literal:quantity/v1",
]

NonEmptyString = Annotated[str, Field(min_length=1)]


class _ProfileRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceAttestation(_ProfileRecord):
    """Evidence that a surface form came from a named source.

    It attests the *surface form*, not that the owner's semantics equal the external
    resource's. The conditional matrix in section 6.2 is enforced by the validator
    rather than here, because "wordnet requires sense_id" is a cross-field rule that a
    field type cannot state.
    """

    source_kind: SourceKind
    lemma: NonEmptyString
    sense_id: NonEmptyString | None = None
    roleset_id: NonEmptyString | None = None
    provenance_refs: tuple[NonEmptyString, ...] = Field(min_length=1)


class Lexicalization(_ProfileRecord):
    """A surface form owned by the Concept or Operator that embeds it.

    Embedded, never a top-level table with a `target_id`: the owner *is* the target. Two
    forms in different languages under one owner are two independent records, not a
    translation edge between them.

    `resolved` does not promise global unambiguity -- the same
    `(language, NFC(surface_form))` may be resolved under several owners, and NL2KE
    still has to disambiguate using context, Concept types and Operator signatures.
    """

    language: NonEmptyString
    surface_form: NonEmptyString
    surface_relation: SurfaceRelation
    disambiguation_status: DisambiguationStatus
    source_attestations: tuple[SourceAttestation, ...] = Field(min_length=1)


class ExternalMapping(_ProfileRecord):
    """A directed mapping from this canonical owner to an external target.

    Direction is fixed owner -> target. Only `exact` can support an identity-level merge
    proposal, and even then only through build governance; `narrow`, `broad` and
    `related` never change a canonical id.

    `target` is deliberately not a snapshot reference: external identifiers are not
    required to resolve inside the snapshot, so reference closure does not apply to it.
    """

    relation: MappingRelation
    target: NonEmptyString


class CurrencyMinorUnits(_ProfileRecord):
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    minor_units: Annotated[int, Field(ge=0)]


class LiteralValueContract(_ProfileRecord):
    """The closed codec for a literal-bearing Concept.

    Defines how a value is spelled canonically; it does not create a new ontology
    identity. `accepts_null` is pinned to False and `equality_mode` to canonical JSON
    identity, so equality is byte identity after normalisation rather than a per-codec
    comparison rule.
    """

    codec_id: CodecId
    canonical_json_kind: Literal["boolean", "string", "object"]
    equality_mode: Literal["canonical_json_identity"]
    accepts_null: Literal[False]
    currency_minor_units: tuple[CurrencyMinorUnits, ...] | None = None
    canonical_unit_symbol: NonEmptyString | None = None


class ConceptProfile(_ProfileRecord):
    """`Concept.supply.memory_assertion`."""

    profile_version: Literal["memory-assertion/v1"]
    semantic_kind: SemanticKind
    lexicalizations: tuple[Lexicalization, ...]
    disjoint_with: tuple[ConceptId, ...] = ()
    external_mappings: tuple[ExternalMapping, ...] = ()
    literal_value_contract: LiteralValueContract | None = None
    deprecated: bool | None = None
    replaced_by: ConceptId | None = None


class PositionalParameter(_ProfileRecord):
    """Describes `input_concepts[index]` and nothing else.

    The name is for definition, review and display. It is not an identity that another
    Operator can reference -- which is the distinction that keeps positional arguments
    from turning back into named roles.
    """

    index: Annotated[int, Field(ge=0)]
    name: NonEmptyString
    definition: NonEmptyString


class FunctionSemantics(_ProfileRecord):
    """What the operator's evaluation depends on -- not its quality or truth.

    `purity=pure` and `deterministic=True` are pinned in v1. Time, state version or a
    data snapshot may influence a result, but only by appearing as an ordinary ordered
    input, which is why purity survives: every dependency is already in the signature.
    """

    purity: Literal["pure"]
    deterministic: Literal[True]
    partiality: Literal["total", "partial"]


class DefinednessContract(_ProfileRecord):
    """Where a partial operator is defined.

    Structurally retained for forward compatibility and build audit. v1 runtime
    snapshots ship no content-addressed registry of definedness predicates, so a
    snapshot carrying any partial operator is quarantined regardless of how well-formed
    this contract is.
    """

    contract_id: Literal["ke-definedness/v1"]
    required_input_indexes: tuple[int, ...]
    failure_behavior: Literal["reject_application"]


class OperatorProfile(_ProfileRecord):
    """`Operator.supply.memory_assertion`."""

    profile_version: Literal["memory-assertion/v1"]
    positional_parameters: tuple[PositionalParameter, ...]
    proposition_operation: PropositionOperation
    function_semantics: FunctionSemantics
    definedness_contract: DefinednessContract | None = None
    external_mappings: tuple[ExternalMapping, ...] = ()
    lexicalizations: tuple[Lexicalization, ...]
    deprecated: bool | None = None
    replaced_by: OperatorId | None = None
