"""Stage 1A: the four evaluation contracts, each frozen and hashed on its own.

Stage 0.5 published coverage 22/32 and selection metrics of 1.000 while three things the
numbers depend on were still unfrozen: how a token is counted, what bytes actually reach the
model, and how much of the context window is already spoken for. Any of the three can move a
budget, and a moved budget moves the eligible set, so those figures described a harness
rather than a measurement.

Four contracts are frozen here, and each carries its own SHA-256:

- :class:`TokenizerFreeze` -- identity, parameters and the exact counting expression.
- :class:`SerializationFreeze` -- the real system-prompt bytes, per-turn rendering and how
  evidence is assembled into one request.
- :class:`ReserveFreeze` -- context window less system, envelope, output and safety margin,
  with the subtraction shown rather than asserted.
- :class:`OverLimitPolicyFreeze` -- what happens to an item that does not fit.

One combined hash was rejected deliberately. A single digest tells an auditor that something
changed but not which contract, and re-freezing the tokenizer would silently invalidate a
citation about serialization. Four hashes localise the change.

The frozen tokenizer is the deterministic character approximation from
:mod:`ke_memory_demo.evaluation.arms`, not a provider tokenizer. Everything derived here is
therefore diagnostic: it bounds instrumentation, and it cannot prove a request fits the
model's context window. Replacing the approximation with a provider-authoritative tokenizer
is what would let these figures be cited as capability results.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Final, cast
import tomllib

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

from .arms import APPROXIMATE_TOKENIZER, ArmBudget, TokenizerContract
from .channels import BenchmarkQuestion, PublicTurn

NonEmptyString = Annotated[str, Field(min_length=1)]

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
ANSWER_SYSTEM_PROMPT_PATH: Final[Path] = REPO_ROOT / "prompts" / "answer" / "system.md"
MODELS_CONFIG_PATH: Final[Path] = REPO_ROOT / "config" / "models.toml"
EXPERIMENT_CONFIG_PATH: Final[Path] = REPO_ROOT / "config" / "experiment.toml"

DIAGNOSTIC_STANDING: Final[str] = (
    "every figure derived from these contracts stays diagnostic until a "
    "provider-authoritative tokenizer replaces the character approximation. The frozen "
    "tokenizer makes budgets reproducible, not correct: it cannot prove a request fits the "
    "model context window, so an eligible set computed from it bounds instrumentation only "
    "and may not be cited as a capability result."
)


class ContractFreezeError(ValueError):
    """A contract was frozen with inputs that cannot be audited."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _sha256_of(payload: BaseModel | JsonValue) -> str:
    """SHA-256 over canonical JSON, so key order cannot move a hash."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def approximate_tokens(text: str, tokenizer: TokenizerContract = APPROXIMATE_TOKENIZER) -> int:
    """The frozen count, expressed once so nothing re-derives it slightly differently.

    This reproduces ``max(1, (len(text) + 3) // 4)`` as used by the regression-slice loader
    and by ``PublicTurn.approximate_tokens``, generalised over ``chars_per_token``. The
    ``max(1, ...)`` floor matters: empty text still occupies a delimiter in the request, so
    charging it zero would make a long list of empty units look free.
    """
    return approximate_tokens_for_length(len(text), tokenizer)


def approximate_tokens_for_length(
    character_count: int,
    tokenizer: TokenizerContract = APPROXIMATE_TOKENIZER,
) -> int:
    """The same count from a length alone, for text already measured and hashed.

    The reserve contract counts the system prompt from the character count the serialization
    contract recorded. Re-reading the file there could measure a different prompt than the
    one that was hashed, which is the disagreement the freeze exists to prevent.
    """
    if character_count < 0:
        raise ContractFreezeError("character count cannot be negative")
    per_token = tokenizer.chars_per_token
    return max(1, (character_count + per_token - 1) // per_token)


# The counting method as an auditable string. A reviewer comparing a future implementation
# against this contract needs the expression, not a prose description of it: "about four
# characters per token" is not something an implementation can be checked against.
TOKEN_COUNT_EXPRESSION: Final[str] = "max(1, (len(text) + chars_per_token - 1) // chars_per_token)"


class TokenizerFreeze(_Frozen):
    """Contract (a): how a token is counted, and what that count cannot be used for."""

    tokenizer_id: NonEmptyString
    tokenizer_version: NonEmptyString
    implementation_identity: NonEmptyString
    implementation_sha256: NonEmptyString
    parameters: JsonObject
    counting_method: NonEmptyString
    count_expression: NonEmptyString
    unit_of_measurement: NonEmptyString
    is_provider_authoritative: bool
    is_deterministic: bool
    # Recorded as a field rather than a docstring: the artifact must carry the consequence to
    # whoever reads it, not require them to find this module.
    authority_limitation: NonEmptyString
    consequence: NonEmptyString
    replaced_by_when_available: NonEmptyString

    @model_validator(mode="after")
    def _validate(self) -> TokenizerFreeze:
        # A tokenizer claiming provider authority while being this approximation is the exact
        # confusion the freeze exists to prevent, so it is rejected structurally.
        if self.is_provider_authoritative:
            raise ContractFreezeError(
                "the frozen tokenizer is a character approximation and must not be recorded "
                "as provider authoritative"
            )
        return self

    def freeze_hash(self) -> str:
        return _sha256_of(self)


def freeze_tokenizer(tokenizer: TokenizerContract = APPROXIMATE_TOKENIZER) -> TokenizerFreeze:
    """Freeze the tokenizer, hashing the real source of the counting function.

    ``implementation_sha256`` digests the source text of both counting functions rather than
    a version label a human maintains. A label can stay put while the arithmetic under it
    changes; the source digest cannot.

    The authority check is repeated here as well as in the model validator. Pydantic wraps a
    validator's ValueError in a ValidationError, so a caller of this function would otherwise
    have to unwrap one to find out what it did wrong.
    """
    if tokenizer.is_provider_authoritative:
        raise ContractFreezeError(
            "the frozen tokenizer is a character approximation and must not be recorded as "
            "provider authoritative"
        )
    source = inspect.getsource(approximate_tokens) + inspect.getsource(
        approximate_tokens_for_length
    )
    return TokenizerFreeze(
        tokenizer_id=tokenizer.tokenizer_id,
        # Derived from the parameter, not typed in: bumping chars_per_token without moving
        # the version string would leave two different tokenizers sharing one identity.
        tokenizer_version=f"chars-per-token-{tokenizer.chars_per_token}-floor-1",
        implementation_identity=(
            f"{approximate_tokens.__module__}.{approximate_tokens.__qualname__}"
        ),
        implementation_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        parameters={
            "chars_per_token": tokenizer.chars_per_token,
            "minimum_tokens_per_unit": 1,
            "rounding": "ceiling",
            "text_encoding": "utf-8",
            "length_measured_in": "python_str_characters",
        },
        counting_method=(
            "count Python string characters, divide by chars_per_token rounding up, and "
            "floor the result at one token per counted unit"
        ),
        count_expression=TOKEN_COUNT_EXPRESSION,
        # len() over a str counts code points, which is not the same as UTF-8 bytes for any
        # non-ASCII content. Naming the unit keeps a later byte-based reimplementation from
        # being mistaken for the same contract.
        unit_of_measurement="unicode_code_points_not_utf8_bytes",
        is_provider_authoritative=tokenizer.is_provider_authoritative,
        is_deterministic=True,
        authority_limitation=(
            "NOT provider-authoritative: no DeepSeek tokenizer is consulted, and the true "
            "token count for the same text may be higher or lower"
        ),
        consequence=(
            "this count cannot prove a request fits the model context window. A conversation "
            "measured under the derived evidence budget may still be rejected by the "
            "provider, and one measured over it may in fact have fitted"
        ),
        replaced_by_when_available=(
            "the provider tokenizer for the answer model; on replacement every budget and "
            "the eligible set must be recomputed and this hash re-frozen"
        ),
    )


# Contract (b): serialization.
#
# The per-turn form mirrors what answering.py actually sends. That path builds a canonical
# JSON envelope of task, question and an evidence list, so a turn is frozen as a canonical
# JSON object rather than as human-readable prose. Field names are fixed here because
# renaming "evidence_id" to "id" would change every token count in the corpus while leaving
# the conversation content untouched.
TURN_FIELD_ORDER: Final[tuple[str, ...]] = ("evidence_id", "speaker", "text")
REQUEST_ENVELOPE_TASK: Final[str] = "answer_from_evidence"
REQUEST_ENVELOPE_FIELD_ORDER: Final[tuple[str, ...]] = ("evidence", "question", "task")


def serialize_turn(turn: PublicTurn) -> str:
    """Render one turn to the exact string whose characters are counted.

    Canonical JSON, not an f-string template: the delivered request is canonical JSON, and
    counting a prettier representation would under- or over-charge every unit by the
    difference in punctuation. ``approximate_tokens`` is deliberately excluded -- it is
    instrumentation about the turn, and the model never sees it.
    """
    return canonical_json(
        {
            "evidence_id": turn.evidence_handle,
            "speaker": turn.speaker,
            "text": turn.text,
        }
    ).decode("utf-8")


def serialize_evidence_request(question: str, turns: Sequence[PublicTurn]) -> str:
    """Assemble evidence plus question into the single user message that is sent.

    Turn order is preserved rather than sorted. Order carries meaning in a conversation, and
    the arms in :mod:`ke_memory_demo.evaluation.arms` already fix it by selection and budget;
    re-sorting here would silently disagree with what they recorded as delivered.
    """
    payload = cast(
        JsonValue,
        {
            "task": REQUEST_ENVELOPE_TASK,
            "question": question,
            "evidence": [
                {
                    "evidence_id": turn.evidence_handle,
                    "speaker": turn.speaker,
                    "text": turn.text,
                }
                for turn in turns
            ],
        },
    )
    return canonical_json(payload).decode("utf-8")


class SerializationFreeze(_Frozen):
    """Contract (b): the exact bytes, so a token count refers to something specific."""

    system_prompt_path: NonEmptyString
    system_prompt_sha256: NonEmptyString
    system_prompt_bytes: int = Field(ge=0)
    system_prompt_characters: int = Field(ge=0)
    system_prompt_encoding: NonEmptyString
    system_prompt_newline: NonEmptyString
    turn_serialization_form: NonEmptyString
    turn_serialization_identity: NonEmptyString
    turn_serialization_sha256: NonEmptyString
    turn_field_order: tuple[str, ...]
    turn_fields_excluded: tuple[str, ...]
    request_assembly_form: NonEmptyString
    request_assembly_identity: NonEmptyString
    request_assembly_sha256: NonEmptyString
    request_envelope_field_order: tuple[str, ...]
    message_roles: tuple[str, ...]
    canonical_json_settings: JsonObject
    empty_envelope_serialization: NonEmptyString
    empty_envelope_tokens: int = Field(gt=0)
    evidence_order_policy: NonEmptyString

    @model_validator(mode="after")
    def _validate(self) -> SerializationFreeze:
        # An empty prompt file would hash fine and reserve nothing, which is how a reserve
        # silently becomes too large.
        if self.system_prompt_bytes == 0:
            raise ContractFreezeError("the frozen system prompt must not be empty")
        return self

    def freeze_hash(self) -> str:
        return _sha256_of(self)


def _display_path(path: Path) -> str:
    """Repo-relative when possible, so the record does not depend on a checkout location.

    A path outside the repository is reported verbatim rather than raising: tests freeze a
    temporary prompt, and a path formatting concern must not decide whether a freeze runs.
    """
    resolved = path.resolve()
    if resolved.is_relative_to(REPO_ROOT):
        return str(resolved.relative_to(REPO_ROOT))
    return str(resolved)


def freeze_serialization(
    system_prompt_path: Path = ANSWER_SYSTEM_PROMPT_PATH,
) -> SerializationFreeze:
    """Freeze serialization against the real prompt file on disk.

    The prompt is read as bytes and hashed as bytes. Reading it as text and hashing the
    decoded string would make a CRLF/LF change invisible, and line endings are part of what
    is sent.

    Emptiness is checked here as well as in the model validator, so a caller gets a
    ContractFreezeError rather than a pydantic ValidationError wrapping one.
    """
    try:
        raw = system_prompt_path.read_bytes()
    except OSError as error:
        raise ContractFreezeError(
            f"the system prompt to freeze is unavailable: {system_prompt_path}"
        ) from error
    if not raw:
        raise ContractFreezeError(
            f"the frozen system prompt must not be empty: {system_prompt_path}"
        )

    empty_envelope = serialize_evidence_request("", ())
    return SerializationFreeze(
        system_prompt_path=_display_path(system_prompt_path),
        system_prompt_sha256=hashlib.sha256(raw).hexdigest(),
        system_prompt_bytes=len(raw),
        system_prompt_characters=len(raw.decode("utf-8")),
        system_prompt_encoding="utf-8",
        # Byte-level, so the record states what is in the file rather than what the reader
        # normalised it to.
        system_prompt_newline="lf" if b"\r\n" not in raw else "crlf",
        turn_serialization_form=(
            'canonical_json({"evidence_id": <handle>, "speaker": <speaker>, "text": <text>}) '
            "decoded as utf-8; keys sorted, separators (\",\", \":\"), ensure_ascii false"
        ),
        turn_serialization_identity=f"{serialize_turn.__module__}.{serialize_turn.__qualname__}",
        turn_serialization_sha256=hashlib.sha256(
            inspect.getsource(serialize_turn).encode("utf-8")
        ).hexdigest(),
        turn_field_order=TURN_FIELD_ORDER,
        turn_fields_excluded=("approximate_tokens",),
        request_assembly_form=(
            'canonical_json({"task": "answer_from_evidence", "question": <question>, '
            '"evidence": [<turn>, ...]}) decoded as utf-8, sent as the single user message '
            "alongside the frozen system prompt"
        ),
        request_assembly_identity=(
            f"{serialize_evidence_request.__module__}."
            f"{serialize_evidence_request.__qualname__}"
        ),
        request_assembly_sha256=hashlib.sha256(
            inspect.getsource(serialize_evidence_request).encode("utf-8")
        ).hexdigest(),
        request_envelope_field_order=REQUEST_ENVELOPE_FIELD_ORDER,
        message_roles=("system", "user"),
        canonical_json_settings={
            "sort_keys": True,
            "separators": ",:",
            "ensure_ascii": False,
            "allow_nan": False,
            "encoding": "utf-8",
        },
        empty_envelope_serialization=empty_envelope,
        # The envelope costs tokens even with no evidence and no question, and that cost is
        # charged against the context window before any evidence is delivered.
        empty_envelope_tokens=approximate_tokens(empty_envelope),
        evidence_order_policy=(
            "delivery order preserved, never re-sorted: conversation order is semantic and "
            "must match what an arm recorded as delivered"
        ),
    )


# Contract (c): reserve.
#
# deepseek-v4-flash advertises a 128K context. Stage 0.5 deducted a flat 1024 + 2048 with no
# statement of where 2048 came from; here the prompt side is measured from the real file and
# the remainder is a named safety margin rather than an unexplained constant.
MODEL_CONTEXT_TOKENS: Final[int] = 128_000
SAFETY_MARGIN_PERCENT: Final[int] = 2


class ReserveFreeze(_Frozen):
    """Contract (c): what the context window is spent on before evidence gets any."""

    model_id: NonEmptyString
    context_window_tokens: int = Field(gt=0)
    context_window_source: NonEmptyString
    system_reserve_tokens: int = Field(gt=0)
    system_reserve_basis: NonEmptyString
    prompt_envelope_reserve_tokens: int = Field(gt=0)
    prompt_envelope_reserve_basis: NonEmptyString
    output_reserve_tokens: int = Field(gt=0)
    output_reserve_source: NonEmptyString
    safety_margin_percent: int = Field(ge=0)
    safety_margin_tokens: int = Field(ge=0)
    safety_margin_rationale: NonEmptyString
    total_reserved_tokens: int = Field(gt=0)
    evidence_budget_tokens: int = Field(gt=0)
    # The subtraction as a string, so an auditor can check the number without rerunning
    # anything. A budget that only appears as an integer cannot be disputed.
    arithmetic: NonEmptyString
    arithmetic_terms: JsonObject
    measured_with_tokenizer_id: NonEmptyString
    authority_note: NonEmptyString

    @model_validator(mode="after")
    def _validate(self) -> ReserveFreeze:
        # The point of showing the arithmetic is that it is checkable, so it is checked here
        # too: a hand-edited budget that no longer matches its own terms is rejected.
        reserved = (
            self.system_reserve_tokens
            + self.prompt_envelope_reserve_tokens
            + self.output_reserve_tokens
            + self.safety_margin_tokens
        )
        if reserved != self.total_reserved_tokens:
            raise ContractFreezeError(
                f"reserve components sum to {reserved}, not the recorded "
                f"{self.total_reserved_tokens}"
            )
        if self.context_window_tokens - reserved != self.evidence_budget_tokens:
            raise ContractFreezeError(
                f"evidence budget {self.evidence_budget_tokens} does not equal context "
                f"{self.context_window_tokens} less reserve {reserved}"
            )
        return self

    def as_arm_budget(self, max_evidence_units: int) -> ArmBudget:
        """The full-history delivery limit implied by this reserve."""
        return ArmBudget(
            evidence_budget_tokens=self.evidence_budget_tokens,
            answer_max_output_tokens=self.output_reserve_tokens,
            max_evidence_units=max_evidence_units,
        )

    def freeze_hash(self) -> str:
        return _sha256_of(self)


def _read_toml(path: Path) -> Mapping[str, object]:
    try:
        with path.open("rb") as stream:
            return cast(dict[str, object], tomllib.load(stream))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ContractFreezeError(f"configuration to freeze is unavailable: {path}") from error


def _work_model_config(models_config_path: Path) -> Mapping[str, object]:
    work = cast(Mapping[str, object], _read_toml(models_config_path).get("work") or {})
    if not work:
        raise ContractFreezeError(f"{models_config_path} has no [work] model section")
    return work


def freeze_reserve(
    serialization: SerializationFreeze,
    *,
    models_config_path: Path = MODELS_CONFIG_PATH,
    experiment_config_path: Path = EXPERIMENT_CONFIG_PATH,
    context_window_tokens: int = MODEL_CONTEXT_TOKENS,
    safety_margin_percent: int = SAFETY_MARGIN_PERCENT,
    tokenizer: TokenizerContract = APPROXIMATE_TOKENIZER,
) -> ReserveFreeze:
    """Derive the evidence budget from measured reserve rather than chosen constants.

    The system reserve is counted from the prompt bytes that :func:`freeze_serialization`
    hashed, so the two contracts cannot disagree about which prompt is in force. The output
    reserve comes from ``config/experiment.toml`` rather than being written here, because the
    answer client validates against that file at runtime.
    """
    work = _work_model_config(models_config_path)
    model_id = str(work.get("model") or "")
    if not model_id:
        raise ContractFreezeError(f"{models_config_path} [work] has no model name")

    retrieval = cast(
        Mapping[str, object],
        _read_toml(experiment_config_path).get("retrieval") or {},
    )
    output_reserve = retrieval.get("answer_max_output_tokens")
    if not isinstance(output_reserve, int) or isinstance(output_reserve, bool):
        raise ContractFreezeError(
            f"{experiment_config_path} [retrieval] answer_max_output_tokens must be an integer"
        )

    # Counted from the frozen character length, not re-read from disk: the reserve must
    # measure the prompt whose hash is in the serialization contract.
    system_reserve = approximate_tokens_for_length(
        serialization.system_prompt_characters, tokenizer
    )
    envelope_reserve = serialization.empty_envelope_tokens
    # Ceiling division, so the margin is never rounded down to less protection than stated.
    margin = -(-context_window_tokens * safety_margin_percent // 100)
    total_reserved = system_reserve + envelope_reserve + output_reserve + margin
    budget = context_window_tokens - total_reserved
    if budget <= 0:
        raise ContractFreezeError(
            f"reserve {total_reserved} leaves no evidence budget in a "
            f"{context_window_tokens}-token context"
        )

    return ReserveFreeze(
        model_id=model_id,
        context_window_tokens=context_window_tokens,
        context_window_source=(
            f"advertised context window for {model_id}; a vendor-published figure, not "
            "measured against the API by this freeze"
        ),
        system_reserve_tokens=system_reserve,
        system_reserve_basis=(
            f"frozen system prompt {serialization.system_prompt_path} "
            f"({serialization.system_prompt_bytes} bytes, "
            f"{serialization.system_prompt_characters} characters, "
            f"sha256 {serialization.system_prompt_sha256[:16]}) counted with "
            f"{tokenizer.tokenizer_id}"
        ),
        prompt_envelope_reserve_tokens=envelope_reserve,
        prompt_envelope_reserve_basis=(
            "canonical JSON request envelope with no evidence and an empty question: "
            f"{serialization.empty_envelope_serialization}. Excludes question text, which "
            "is charged per item against the evidence budget"
        ),
        output_reserve_tokens=output_reserve,
        output_reserve_source=(
            f"{experiment_config_path.name} [retrieval] answer_max_output_tokens; the answer "
            "model runs with thinking disabled, so this covers visible output only"
        ),
        safety_margin_percent=safety_margin_percent,
        safety_margin_tokens=margin,
        safety_margin_rationale=(
            f"{safety_margin_percent}% of the context window, held back because the "
            "tokenizer is a character approximation whose error is unbounded in either "
            "direction. The margin reduces how often an item measured as fitting is rejected "
            "by the provider; it does not make the count authoritative"
        ),
        total_reserved_tokens=total_reserved,
        evidence_budget_tokens=budget,
        arithmetic=(
            f"{context_window_tokens} context - {system_reserve} system - "
            f"{envelope_reserve} envelope - {output_reserve} output - {margin} margin "
            f"({safety_margin_percent}%) = {budget} evidence"
        ),
        arithmetic_terms={
            "context_window_tokens": context_window_tokens,
            "system_reserve_tokens": system_reserve,
            "prompt_envelope_reserve_tokens": envelope_reserve,
            "output_reserve_tokens": output_reserve,
            "safety_margin_tokens": margin,
            "total_reserved_tokens": total_reserved,
            "evidence_budget_tokens": budget,
        },
        measured_with_tokenizer_id=tokenizer.tokenizer_id,
        authority_note=(
            "every term above is measured with a non-authoritative approximation, so this "
            "budget bounds instrumentation and does not guarantee the request fits"
        ),
    )


# Contract (d): over-limit policy.
#
# Fixed, not configurable. A configurable policy is how truncation becomes acceptable under
# schedule pressure, and a truncated full-history arm reported as full history does not
# overstate a number -- it measures a different condition and gives it the wrong name.
OVER_LIMIT_STATUS: Final[str] = "not_executed_context_limit"


class OverLimitPolicyFreeze(_Frozen):
    """Contract (d): what happens to an item whose evidence exceeds the budget."""

    status: NonEmptyString
    policy: NonEmptyString
    forbidden_behaviour: tuple[str, ...]
    denominator_rule: NonEmptyString
    cross_arm_rule: NonEmptyString
    reporting_requirement: NonEmptyString
    is_configurable: bool

    @model_validator(mode="after")
    def _validate(self) -> OverLimitPolicyFreeze:
        if self.status != OVER_LIMIT_STATUS:
            raise ContractFreezeError(
                f"the over-limit status is fixed to {OVER_LIMIT_STATUS!r}, not {self.status!r}"
            )
        if self.is_configurable:
            raise ContractFreezeError("the over-limit policy must not be recorded as configurable")
        return self

    def freeze_hash(self) -> str:
        return _sha256_of(self)


def freeze_over_limit_policy() -> OverLimitPolicyFreeze:
    """Freeze the only permitted handling of an over-context item."""
    return OverLimitPolicyFreeze(
        status=OVER_LIMIT_STATUS,
        policy=(
            "an item whose serialized evidence exceeds the frozen evidence budget is recorded "
            f"as {OVER_LIMIT_STATUS} for the full_history arm and excluded from that arm's "
            "denominator. It is never executed against a shortened history"
        ),
        forbidden_behaviour=(
            "truncating an over-context conversation and reporting the result as full_history "
            "is FORBIDDEN: the measurement would be a truncated-history condition carrying a "
            "full-history name",
            "silently dropping over-limit items from the item count, which would hide the "
            "coverage loss instead of reporting it",
            "raising the evidence budget above the frozen reserve to make an item fit",
            "substituting a retrieval or memory arm's selection for full history on these "
            "items, which compares a different arm under the full_history label",
        ),
        denominator_rule=(
            "full_history metrics are reported over the eligible denominator only, alongside "
            "eligible/total coverage and the exact ineligible item ids"
        ),
        cross_arm_rule=(
            "cross-arm comparison uses only items every arm executed, so the full_history "
            "exclusions set the shared denominator. Arms that are not context limited may "
            "additionally be reported over all items, labelled as a different denominator"
        ),
        reporting_requirement=(
            "any citation of full_history results must state the coverage fraction; a bare "
            "rate over an unstated denominator is not a permitted form"
        ),
        is_configurable=False,
    )


class ItemEligibility(_Frozen):
    """Per-item eligibility, with the measured cost that decided it."""

    question_id: NonEmptyString
    conversation_handle: NonEmptyString
    turn_count: int = Field(ge=0)
    serialized_evidence_tokens: int = Field(ge=0)
    question_tokens: int = Field(gt=0)
    total_request_tokens: int = Field(ge=0)
    # The Stage 0.5 basis for the same item, so the two measurements can be compared per item
    # instead of only in aggregate.
    raw_text_tokens: int = Field(ge=0)
    serialization_overhead_tokens: int
    eligible: bool
    eligible_under_previous_basis: bool
    status: NonEmptyString
    headroom_tokens: int


class EligibilityRecomputation(_Frozen):
    """The eligible set under the frozen contract, with the delta against Stage 0.5."""

    evidence_budget_tokens: int = Field(gt=0)
    total_items: int = Field(gt=0)
    eligible_count: int = Field(ge=0)
    ineligible_count: int = Field(ge=0)
    coverage: NonEmptyString
    eligible_item_ids: tuple[str, ...]
    ineligible_item_ids: tuple[str, ...]
    items: tuple[ItemEligibility, ...]
    measurement_basis: NonEmptyString
    previous_coverage: NonEmptyString
    previous_evidence_budget_tokens: int = Field(gt=0)
    previous_eligible_item_ids: tuple[str, ...]
    coverage_delta: NonEmptyString
    eligible_set_changed: bool
    newly_ineligible_item_ids: tuple[str, ...]
    newly_eligible_item_ids: tuple[str, ...]
    boundary_analysis: NonEmptyString
    delta_cause: NonEmptyString
    standing: NonEmptyString

    @model_validator(mode="after")
    def _validate(self) -> EligibilityRecomputation:
        if self.eligible_count + self.ineligible_count != self.total_items:
            raise ContractFreezeError(
                "eligible and ineligible counts must partition the item set"
            )
        if len(self.items) != self.total_items:
            raise ContractFreezeError("per-item records must cover every item")
        # The set-changed flag is what a reader checks before trusting an unchanged coverage
        # fraction, so it may not disagree with the id lists it summarises.
        changed = bool(self.newly_ineligible_item_ids or self.newly_eligible_item_ids)
        if self.eligible_set_changed != changed:
            raise ContractFreezeError(
                "eligible_set_changed must be true exactly when items moved between sets"
            )
        return self


# Stage 0.5's budget: a flat 1024 + 2048 deduction from the 128K context, with no statement
# of where 2048 came from. Reconstructed as an expression so the comparison names the same
# arithmetic the earlier harness used, and the previous eligible set is recomputed from it
# rather than copied from that report.
PREVIOUS_OUTPUT_RESERVE_TOKENS: Final[int] = 1024
PREVIOUS_PROMPT_RESERVE_TOKENS: Final[int] = 2048
PREVIOUS_EVIDENCE_BUDGET_TOKENS: Final[int] = (
    MODEL_CONTEXT_TOKENS - PREVIOUS_OUTPUT_RESERVE_TOKENS - PREVIOUS_PROMPT_RESERVE_TOKENS
)


def recompute_eligibility(
    questions: Sequence[BenchmarkQuestion],
    turns_by_handle: Mapping[str, Sequence[PublicTurn]],
    reserve: ReserveFreeze,
    *,
    tokenizer: TokenizerContract = APPROXIMATE_TOKENIZER,
    previous_budget_tokens: int = PREVIOUS_EVIDENCE_BUDGET_TOKENS,
) -> EligibilityRecomputation:
    """Recompute the eligible set from serialized cost under the frozen budget.

    Stage 0.5 summed each turn's raw ``approximate_tokens``, which measures the conversation
    text and not the request. JSON keys, quoting and the evidence handle are sent too, so the
    frozen measurement serializes each turn and charges the question as well -- a question
    consumes context alongside its evidence.
    """
    if not questions:
        raise ContractFreezeError("eligibility cannot be recomputed over an empty question set")
    records: list[ItemEligibility] = []
    for question in questions:
        turns = tuple(turns_by_handle.get(question.conversation_handle, ()))
        evidence_tokens = sum(approximate_tokens(serialize_turn(t), tokenizer) for t in turns)
        question_tokens = approximate_tokens(question.question, tokenizer)
        total = evidence_tokens + question_tokens
        # The Stage 0.5 basis, recomputed here rather than read from its report, so the delta
        # is derived from the same slice in the same run instead of trusting a stale figure.
        raw_tokens = sum(t.approximate_tokens for t in turns)
        eligible = total <= reserve.evidence_budget_tokens
        records.append(
            ItemEligibility(
                question_id=question.question_id,
                conversation_handle=question.conversation_handle,
                turn_count=len(turns),
                serialized_evidence_tokens=evidence_tokens,
                question_tokens=question_tokens,
                total_request_tokens=total,
                raw_text_tokens=raw_tokens,
                serialization_overhead_tokens=evidence_tokens - raw_tokens,
                eligible=eligible,
                eligible_under_previous_basis=raw_tokens <= previous_budget_tokens,
                status="eligible" if eligible else OVER_LIMIT_STATUS,
                # Signed distance to the limit. A near-zero value on any item is what would
                # make the unchanged coverage fraction fragile, so it is recorded per item.
                headroom_tokens=reserve.evidence_budget_tokens - total,
            )
        )

    eligible_ids = tuple(sorted(r.question_id for r in records if r.eligible))
    ineligible_ids = tuple(sorted(r.question_id for r in records if not r.eligible))
    previous_eligible_ids = tuple(
        sorted(r.question_id for r in records if r.eligible_under_previous_basis)
    )
    newly_ineligible = tuple(sorted(set(previous_eligible_ids) - set(eligible_ids)))
    newly_eligible = tuple(sorted(set(eligible_ids) - set(previous_eligible_ids)))
    delta = len(eligible_ids) - len(previous_eligible_ids)

    # Whether the unchanged fraction is robust or a coincidence is a question about the
    # distribution, so the gap around the limit is measured instead of asserted.
    closest_eligible = max((r for r in records if r.eligible), key=lambda r: r.total_request_tokens)
    closest_ineligible = min(
        (r for r in records if not r.eligible),
        key=lambda r: r.total_request_tokens,
        default=None,
    )
    largest_overhead = max(r.serialization_overhead_tokens for r in records)
    if closest_ineligible is None:
        boundary = (
            f"no item exceeds the budget; the largest measures "
            f"{closest_eligible.total_request_tokens} tokens with "
            f"{closest_eligible.headroom_tokens} headroom"
        )
    else:
        boundary = (
            f"the largest eligible item measures {closest_eligible.total_request_tokens} "
            f"tokens ({closest_eligible.headroom_tokens} below the "
            f"{reserve.evidence_budget_tokens} budget) and the smallest ineligible item "
            f"measures {closest_ineligible.total_request_tokens} tokens "
            f"({-closest_ineligible.headroom_tokens} above it). The gap across the limit is "
            f"{closest_ineligible.total_request_tokens - closest_eligible.total_request_tokens} "
            f"tokens, against a largest per-item serialization overhead of {largest_overhead} "
            f"and a budget change of "
            f"{reserve.evidence_budget_tokens - previous_budget_tokens}, so neither change is "
            "large enough to move an item across the limit"
        )

    return EligibilityRecomputation(
        evidence_budget_tokens=reserve.evidence_budget_tokens,
        total_items=len(records),
        eligible_count=len(eligible_ids),
        ineligible_count=len(ineligible_ids),
        coverage=f"{len(eligible_ids)}/{len(records)}",
        eligible_item_ids=eligible_ids,
        ineligible_item_ids=ineligible_ids,
        items=tuple(records),
        measurement_basis=(
            "sum over turns of approximate_tokens(serialize_turn(turn)) plus the question "
            "tokens, compared against the frozen evidence budget. Stage 0.5 compared raw "
            "turn text totals and did not charge the question"
        ),
        previous_coverage=f"{len(previous_eligible_ids)}/{len(records)}",
        previous_evidence_budget_tokens=previous_budget_tokens,
        previous_eligible_item_ids=previous_eligible_ids,
        coverage_delta=(
            f"{len(previous_eligible_ids)}/{len(records)} -> {len(eligible_ids)}/{len(records)} "
            f"({delta:+d} eligible items)"
        ),
        eligible_set_changed=bool(newly_ineligible or newly_eligible),
        newly_ineligible_item_ids=newly_ineligible,
        newly_eligible_item_ids=newly_eligible,
        boundary_analysis=boundary,
        delta_cause=(
            "two changes push in opposite directions. Serializing each turn adds JSON keys, "
            "quoting and the evidence handle, and the question is now charged too, so every "
            f"item measures more than its raw text total (up to {largest_overhead} extra "
            f"tokens); meanwhile the budget moved from {previous_budget_tokens} to "
            f"{reserve.evidence_budget_tokens}, because the system reserve is "
            f"{reserve.system_reserve_tokens} tokens measured from the real prompt rather "
            f"than an assumed 2048, while a {reserve.safety_margin_percent}% safety margin "
            f"({reserve.safety_margin_tokens} tokens) is now held back explicitly. "
            f"Net effect on the eligible set: {delta:+d} items. " + boundary
        ),
        standing=DIAGNOSTIC_STANDING,
    )


class ContractFreeze(_Frozen):
    """All four contracts, each hashed separately, plus the recomputed eligible set.

    ``combined_hash`` exists for convenience only, and is a hash *of the four hashes*. It is
    not a substitute for them: citing it alone would tell a reader that something moved
    without saying which contract, which is what four separate digests are for.
    """

    stage: NonEmptyString
    tokenizer: TokenizerFreeze
    serialization: SerializationFreeze
    reserve: ReserveFreeze
    over_limit_policy: OverLimitPolicyFreeze
    eligibility: EligibilityRecomputation
    standing: NonEmptyString

    def hashes(self) -> dict[str, str]:
        """The four independent digests, one per frozen contract."""
        return {
            "tokenizer_sha256": self.tokenizer.freeze_hash(),
            "serialization_sha256": self.serialization.freeze_hash(),
            "reserve_sha256": self.reserve.freeze_hash(),
            "over_limit_policy_sha256": self.over_limit_policy.freeze_hash(),
        }

    def combined_hash(self) -> str:
        return _sha256_of(cast(JsonValue, self.hashes()))


def freeze_contracts(
    questions: Sequence[BenchmarkQuestion],
    turns_by_handle: Mapping[str, Sequence[PublicTurn]],
    *,
    system_prompt_path: Path = ANSWER_SYSTEM_PROMPT_PATH,
    models_config_path: Path = MODELS_CONFIG_PATH,
    experiment_config_path: Path = EXPERIMENT_CONFIG_PATH,
    tokenizer: TokenizerContract = APPROXIMATE_TOKENIZER,
) -> ContractFreeze:
    """Freeze all four contracts and recompute the eligible set under them."""
    tokenizer_freeze = freeze_tokenizer(tokenizer)
    serialization = freeze_serialization(system_prompt_path)
    reserve = freeze_reserve(
        serialization,
        models_config_path=models_config_path,
        experiment_config_path=experiment_config_path,
        tokenizer=tokenizer,
    )
    return ContractFreeze(
        stage="1A",
        tokenizer=tokenizer_freeze,
        serialization=serialization,
        reserve=reserve,
        over_limit_policy=freeze_over_limit_policy(),
        eligibility=recompute_eligibility(
            questions, turns_by_handle, reserve, tokenizer=tokenizer
        ),
        standing=DIAGNOSTIC_STANDING,
    )


def freeze_as_json(freeze: ContractFreeze) -> JsonObject:
    """The artifact payload: contracts, their own hashes, and the recomputed coverage."""
    payload = cast(JsonObject, freeze.model_dump(mode="json"))
    hashes = freeze.hashes()
    payload["contract_hashes"] = {
        **hashes,
        "hash_scope": (
            "each digest is SHA-256 over the canonical JSON of its own contract section only, "
            "so a change to one contract moves exactly one hash"
        ),
        "combined_hash_of_hashes": freeze.combined_hash(),
        "combined_hash_scope": (
            "SHA-256 over the four hashes above; a convenience digest that must not be cited "
            "in place of the individual four"
        ),
    }
    payload["metric_standing"] = {
        "classification": "diagnostic_only",
        "reason": DIAGNOSTIC_STANDING,
        "may_not_be_cited_as": [
            "a capability result",
            "evidence that a request fits the model context window",
            "a qualification or readiness signal",
        ],
        "becomes_citable_when": (
            "a provider-authoritative tokenizer replaces the character approximation and "
            "every budget, reserve term and the eligible set are recomputed under it"
        ),
    }
    payload["judge_dependency"] = "none; no model or judge call is made by this freeze"
    return payload




