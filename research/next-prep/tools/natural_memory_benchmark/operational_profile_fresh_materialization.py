"""Materialize the Phase C fresh-hidden artifacts from the authored blueprints.

Turns the blueprints into the four files the existing scorer reads —
``public-l1.json``, ``authority-l1.json``, ``gold-l1.json``,
``manifest-l1.json`` and the L2 equivalents — so no scoring code changes.

The split matters: ``public`` is all the proposer may see, ``authority`` and
``gold`` are the author's verdicts. The program derives typed expectations from
the blueprint rather than having the author hand-write them, so gold cannot
silently disagree with the prose it claims to encode.

Everything is written once and frozen ``0444``. A new version means a new
directory; nothing is edited in place.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .operational_profile_fresh_authoring import (
    L1_BLUEPRINTS,
    L2_BLUEPRINTS,
    L1CaseBlueprint,
    L2CaseBlueprint,
    coverage_report,
    label_confidence_report,
    opaque_ref,
)

DATASET_ID = "operational-profile-fresh-hidden-v1"

#: 只有这些键允许出现在 public 里。authority/gold 的字段名一旦出现在 public，
#: 就说明作者判断泄漏到了 proposer 可读侧。
_PUBLIC_ALLOWED_KEYS = frozenset(
    {"case_id", "candidate_ref", "source_turn", "untyped_candidate",
     "source_session_ref", "source_turns", "typed_l1_support_pack"}
)
#: 绝不允许出现在 public 中的作者判断字段。
_VERDICT_KEYS = frozenset(
    {"expected_decision", "expected_typed_candidate", "emission_allowed",
     "label_confidence", "rationale", "knowledge_id"}
)


def _evidence_id(quote: str) -> str:
    digest = hashlib.sha256(
        f"typed-extractor-l1-v1:evidence:{quote}".encode()
    ).hexdigest()
    return f"evidence-{digest}"


def _span(user_text: str, quote: str) -> dict[str, Any]:
    start = user_text.find(quote)
    if start < 0:
        raise ValueError(f"quote is not present in the user text: {quote!r}")
    return {
        "evidence_id": _evidence_id(quote),
        "speaker": "user",
        "message": "user",
        "quote": quote,
        "occurrence_index": 0,
        "start": start,
        "end": start + len(quote),
    }


def _public_l1_case(item: L1CaseBlueprint) -> dict[str, Any]:
    """The proposer's view: prose and an untyped candidate, no verdict."""
    return {
        "case_id": opaque_ref("case", item.knowledge_id),
        "candidate_ref": opaque_ref("candidate", item.knowledge_id),
        "source_turn": {"user": item.user_text, "agent": item.agent_text},
        "untyped_candidate": {
            "statement": item.statement,
            "subject": item.subject,
            "predicate": item.predicate,
            "object": item.object,
            "qualifiers": {"polarity": item.polarity},
            "source_status": "user_reported",
            "derivation": "explicit",
            "inference_basis": None,
            "projection_status": "active",
            "lifecycle_links": {
                "lifecycle": "active",
                "replacement_candidate_ref": None,
                "replaces_candidate_refs": [],
                "supersedes_candidate_refs": [],
                "conflicts_with_candidate_refs": [],
            },
            "operation_provenance": {
                "confirmed_by_operation_refs": [],
                "added_by_operation_refs": [],
            },
            "evidence": [_span(item.user_text, item.user_text)],
        },
    }


def _authority_l1_case(item: L1CaseBlueprint) -> dict[str, Any]:
    """The author's constraints: what may be emitted and within which bounds."""
    emitting = item.expected_decision == "emit_l1"
    return {
        "case_id": opaque_ref("case", item.knowledge_id),
        "candidate_ref": opaque_ref("candidate", item.knowledge_id),
        "knowledge_id": item.knowledge_id,
        "candidate_id": opaque_ref("candidate-id", item.knowledge_id),
        "emission_allowed": emitting,
        "required_evidence_bindings": [
            {"evidence_id": _evidence_id(item.user_text), "speaker": "user"}
        ],
        "allowed_modalities": [item.modality] if emitting else [],
        "allowed_polarities": [item.polarity] if emitting else [],
        "allowed_event_times": [],
        "event_time_may_be_null": True,
        "allowed_valid_times": (
            [item.valid_time] if emitting and item.valid_time else []
        ),
        "valid_time_may_be_null": item.valid_time is None,
        "allowed_condition_values": [],
        "allowed_scope_values": [],
        "required_derivation": {
            "method": "explicit",
            "basis": None,
            "evidence_ids": [_evidence_id(item.user_text)],
        },
        "required_lifecycle": {
            "lifecycle": "active",
            "replacement_candidate_ref": None,
            "replaces_candidate_refs": [],
            "supersedes_candidate_refs": [],
            "conflicts_with_candidate_refs": [],
        },
        "required_operation_provenance": {
            "confirmed_by_operation_refs": [],
            "added_by_operation_refs": [],
        },
        "unresolved_required_fields": [],
        "automatic_write_authorizations": {
            "l1": False,
            "l2": False,
            "unit_revision": False,
            "closure": False,
            "identity": False,
        },
    }


def _gold_l1_item(item: L1CaseBlueprint) -> dict[str, Any]:
    """The expected decision, and for an emission the typed candidate.

    Derived from the blueprint rather than hand-written, so the gold cannot drift
    from the prose and rationale it is supposed to encode.
    """
    payload: dict[str, Any] = {
        "case_id": opaque_ref("case", item.knowledge_id),
        "candidate_ref": opaque_ref("candidate", item.knowledge_id),
        "expected_decision": item.expected_decision,
    }
    if item.expected_decision != "emit_l1":
        payload["expected_typed_candidate"] = None
        return payload

    entity_ids: dict[str, str] = {}
    local_entities: list[dict[str, str]] = []
    roles: list[dict[str, str]] = []
    for role, surface in item.role_surfaces:
        entity_id = entity_ids.get(surface)
        if entity_id is None:
            entity_id = f"entity-{len(local_entities) + 1:02d}"
            entity_ids[surface] = entity_id
            local_entities.append(
                {"local_entity_id": entity_id, "surface": surface}
            )
        roles.append(
            {"role": role, "role_name": role, "local_entity_id": entity_id}
        )
    payload["expected_typed_candidate"] = {
        "kind": item.kind,
        "predicate": {
            "surface": item.predicate,
            "sense": item.predicate_sense,
            "canonical_operator": item.canonical_operator,
        },
        "local_entities": local_entities,
        "roles": roles,
        "modality": item.modality,
        "polarity": item.polarity,
        "time": {"event_time": None, "valid_time": item.valid_time},
        "condition_bindings": [],
        "scope_bindings": [],
        "derivation": {
            "method": "explicit",
            "basis": None,
            "evidence_ids": [_evidence_id(item.user_text)],
        },
        "evidence_bindings": [
            {"evidence_id": _evidence_id(item.user_text), "speaker": "user"}
        ],
        "lifecycle": {
            "lifecycle": "active",
            "replacement_candidate_ref": None,
            "replaces_candidate_refs": [],
            "supersedes_candidate_refs": [],
            "conflicts_with_candidate_refs": [],
        },
        "operation_provenance": {
            "confirmed_by_operation_refs": [],
            "added_by_operation_refs": [],
        },
    }
    return payload


def build_allowed_vocabulary(
    *,
    registry: Any,
    policy: Any,
) -> dict[str, list[str]]:
    """Derive the published vocabulary from the frozen policy, never by hand.

    Attempt 1 failed here. The hand-written vocabulary offered modalities
    ``['actual', 'requested']`` — taken from what the *cases* happened to use —
    while the policy authorizes ``actual`` alone, and the prompt told the model
    to use whatever was published. The model then read a request as ``requested``
    modality, faithfully, and was scored as a fabrication.

    Deriving the vocabulary from the policy makes that class of drift
    unrepresentable: the proposer can only ever be offered what the policy will
    actually accept.
    """
    return {
        "canonical_operators": sorted(
            {item.canonical_operator for item in policy.l1_operator_kind_bindings}
        ),
        "predicate_senses": sorted(
            {
                item.predicate_sense
                for item in registry.predicate_role_constraints
                if item.canonical_operator
                in {
                    binding.canonical_operator
                    for binding in policy.l1_operator_kind_bindings
                }
            }
        ),
        "decisions": ["abstain", "emit_l1", "no_memory"],
        "kinds": sorted({item.kind for item in policy.l1_operator_kind_bindings}),
        "modalities": [item.modality for item in policy.modality_time_policies],
        "polarities": sorted(policy.allowed_polarities),
        "speakers": ["user"],
        "roles": sorted(
            {item.machine_role for item in policy.l1_role_display_bindings}
        ),
    }


def assert_vocabulary_matches_policy(
    *,
    vocabulary: dict[str, list[str]],
    registry: Any,
    policy: Any,
) -> None:
    """Refuse a published vocabulary that disagrees with the policy.

    Checked rather than trusted: the drift that broke attempt 1 was invisible in
    every artifact until the model's own output exposed it.
    """
    expected = build_allowed_vocabulary(registry=registry, policy=policy)
    for key, values in expected.items():
        actual = vocabulary.get(key)
        if actual != values:
            raise ValueError(
                f"published {key} disagree with the policy: "
                f"published={actual}, authorized={values}"
            )


def build_l1_payloads(
    *,
    registry: Any | None = None,
    policy: Any | None = None,
    blueprints: tuple[L1CaseBlueprint, ...] = L1_BLUEPRINTS,
    dataset_id: str = DATASET_ID,
) -> dict[str, dict[str, Any]]:
    """Build public, authority and gold for L1.

    Parameterized over the case set so a later hidden version reuses this
    machinery instead of copying it; the frozen v1 artifacts on disk are
    unaffected because they are already written.
    """
    if registry is None or policy is None:
        from .e2e_openai_producers import build_diagnostic_production_policy
        from .l1_ontology_linking import build_diagnostic_ontology_registry

        registry = registry or build_diagnostic_ontology_registry()
        policy = policy or build_diagnostic_production_policy(registry)
    vocabulary = build_allowed_vocabulary(registry=registry, policy=policy)
    assert_vocabulary_matches_policy(
        vocabulary=vocabulary, registry=registry, policy=policy
    )
    return {
        "public-l1.json": {
            "schema_version": "typed-extractor-l1-public-v1",
            "dataset_id": dataset_id,
            "case_count": len(blueprints),
            "allowed_vocabulary": vocabulary,
            "cases": [_public_l1_case(item) for item in blueprints],
        },
        "authority-l1.json": {
            "schema_version": "typed-extractor-l1-authority-v1",
            "dataset_id": dataset_id,
            "case_count": len(blueprints),
            "cases": [_authority_l1_case(item) for item in blueprints],
        },
        "gold-l1.json": {
            "schema_version": "typed-extractor-l1-gold-v1",
            "dataset_id": dataset_id,
            "case_count": len(blueprints),
            "items": [_gold_l1_item(item) for item in blueprints],
        },
    }


#: L2 支撑轮次的原文 -> 该轮陈述的 L1 事实。写成显式表而不是从散文里猜：
#: 支撑集是 L2 的输入前提，若由启发式推断，L2 的判定就建立在不确定的输入上。
_L2_SUPPORT_FACTS: dict[str, dict[str, Any]] = {
    "Coffee is preferred.": {
        "kind": "preference",
        "operator": "prefer",
        "sense": "preference_theme",
        "surface": "Coffee",
        "polarity": "positive",
    },
    "Coffee is not preferred.": {
        "kind": "preference",
        "operator": "prefer",
        "sense": "preference_theme",
        "surface": "Coffee",
        "polarity": "negative",
    },
    "Coffee is drunk every morning.": {
        "kind": "event",
        "operator": "drink",
        "sense": "consume_beverage",
        "surface": "Coffee",
        "polarity": "positive",
    },
    "Tea is drunk every morning.": {
        "kind": "event",
        "operator": "drink",
        "sense": "consume_beverage",
        "surface": "Tea",
        "polarity": "positive",
    },
    "It is drunk every morning.": {
        # 代词轮次：支撑本身只知道"它"，回指解析是 L2 要做的判断，所以这里
        # 如实保留代词表面，不预先替换成 Coffee。
        "kind": "event",
        "operator": "drink",
        "sense": "consume_beverage",
        "surface": "It",
        "polarity": "positive",
    },
    # --- hidden-v2 的支撑轮次 ---
    "Tea is preferred.": {
        "kind": "preference",
        "operator": "prefer",
        "sense": "preference_theme",
        "surface": "Tea",
        "polarity": "positive",
    },
    "Tea is no longer preferred.": {
        "kind": "preference",
        "operator": "prefer",
        "sense": "preference_theme",
        "surface": "Tea",
        "polarity": "negative",
    },
    "Tea is drunk after every deployment.": {
        "kind": "event",
        "operator": "drink",
        "sense": "consume_beverage",
        "surface": "Tea",
        "polarity": "positive",
    },
    "Coffee is drunk at noon.": {
        "kind": "event",
        "operator": "drink",
        "sense": "consume_beverage",
        "surface": "Coffee",
        "polarity": "positive",
    },
    "That one is drunk at noon.": {
        # 同样如实保留指代表面，解析交给 L2。
        "kind": "event",
        "operator": "drink",
        "sense": "consume_beverage",
        "surface": "That one",
        "polarity": "positive",
    },
}


def _l2_support_candidate(
    *,
    support_ref: str,
    turn_ref: str,
    session_ref: str,
    user_text: str,
) -> dict[str, Any]:
    """Build one typed L1 support unit for an L2 case."""
    fact = _L2_SUPPORT_FACTS.get(user_text)
    if fact is None:
        raise ValueError(f"no declared support fact for turn: {user_text!r}")
    return {
        "support_ref": support_ref,
        "source_turn_ref": turn_ref,
        "source_session_ref": session_ref,
        "kind": fact["kind"],
        "predicate": {
            "surface": fact["operator"],
            "sense": fact["sense"],
            "canonical_operator": fact["operator"],
        },
        "local_entities": [
            {"local_entity_id": "entity-01", "surface": fact["surface"]}
        ],
        "roles": [
            {"role": "theme", "role_name": "theme", "local_entity_id": "entity-01"}
        ],
        "modality": "actual",
        "polarity": fact["polarity"],
        "time": {"event_time": None, "valid_time": None},
        "evidence_bindings": [
            {"evidence_id": _evidence_id(user_text), "speaker": "user"}
        ],
    }


def build_l2_payloads(
    *,
    blueprints: tuple[L2CaseBlueprint, ...] = L2_BLUEPRINTS,
    dataset_id: str = DATASET_ID,
) -> dict[str, dict[str, Any]]:
    """Build public, authority and gold for L2."""
    public_cases: list[dict[str, Any]] = []
    authority_cases: list[dict[str, Any]] = []
    gold_items: list[dict[str, Any]] = []
    for item in blueprints:
        case_id = opaque_ref("case", item.knowledge_id)
        candidate_ref = opaque_ref("candidate", item.knowledge_id)
        support_refs = [
            opaque_ref("support", f"{item.knowledge_id}#support-{index}")
            for index in range(len(item.turns))
        ]
        turn_refs = [
            opaque_ref("turn", f"{item.knowledge_id}#turn-{index}")
            for index in range(len(item.turns))
        ]
        session_ref = opaque_ref("session", item.knowledge_id)
        evidence = [
            {"evidence_id": _evidence_id(user_text), "speaker": "user"}
            for user_text, _agent in item.turns
        ]
        public_cases.append(
            {
                "case_id": case_id,
                "candidate_ref": candidate_ref,
                "source_session_ref": session_ref,
                "source_turns": [
                    {
                        "source_turn_ref": turn_refs[index],
                        "turn_index": index,
                        "user": user_text,
                        "agent": agent_text,
                    }
                    for index, (user_text, agent_text) in enumerate(item.turns)
                ],
                "untyped_candidate": {
                    "statement": item.statement,
                    "subject": item.subject,
                    "predicate": item.predicate,
                    "object": item.object,
                    "qualifiers": {"polarity": "positive"},
                    "source_status": "user_reported",
                    "derivation": "explicit",
                    "inference_basis": None,
                    "projection_status": "active",
                    "lifecycle_links": {
                        "lifecycle": "active",
                        "replacement_candidate_ref": None,
                        "replaces_candidate_refs": [],
                        "supersedes_candidate_refs": [],
                        "conflicts_with_candidate_refs": [],
                    },
                    "operation_provenance": {
                        "confirmed_by_operation_refs": [],
                        "added_by_operation_refs": [],
                    },
                    "evidence": [
                        _span(user_text, user_text)
                        for user_text, _agent in item.turns
                    ],
                },
                "typed_l1_support_pack": [
                    _l2_support_candidate(
                        support_ref=support_refs[index],
                        turn_ref=turn_refs[index],
                        session_ref=session_ref,
                        user_text=user_text,
                    )
                    for index, (user_text, _agent) in enumerate(item.turns)
                ],
            }
        )
        authority_cases.append(
            {
                "case_id": case_id,
                "candidate_ref": candidate_ref,
                "knowledge_id": item.knowledge_id,
                "candidate_id": opaque_ref("candidate-id", item.knowledge_id),
                "emission_allowed": item.expected_decision == "emit_l2",
                "required_support_refs": support_refs,
                "required_evidence_bindings": evidence,
                "required_source_turn_refs": turn_refs,
                "required_source_session_refs": [session_ref],
                "allowed_abstraction_methods": (
                    [item.abstraction_method]
                    if item.expected_decision == "emit_l2"
                    else []
                ),
                "allowed_closure_patterns": (
                    [item.closure_pattern]
                    if item.expected_decision == "emit_l2"
                    else []
                ),
                "unresolved_required_fields": [],
                "automatic_write_authorizations": {
                    "l1": False,
                    "l2": False,
                    "unit_revision": False,
                    "closure": False,
                    "identity": False,
                },
            }
        )
        gold_items.append(
            {
                "case_id": case_id,
                "candidate_ref": candidate_ref,
                "expected_decision": item.expected_decision,
                "expected_typed_candidate": None,
            }
        )
    return {
        "public-l2.json": {
            "schema_version": "typed-extractor-l2-public-v1",
            "dataset_id": DATASET_ID,
            "case_count": len(L2_BLUEPRINTS),
            "allowed_vocabulary": {
                "canonical_operators": ["prefer"],
                "predicate_senses": ["preference_theme"],
                "decisions": ["abstain", "emit_l2"],
                "abstraction_methods": ["preference_aggregation"],
                "closure_patterns": ["multi_evidence_set"],
            },
            "cases": public_cases,
        },
        "authority-l2.json": {
            "schema_version": "typed-extractor-l2-authority-v1",
            "dataset_id": DATASET_ID,
            "case_count": len(L2_BLUEPRINTS),
            "cases": authority_cases,
        },
        "gold-l2.json": {
            "schema_version": "typed-extractor-l2-gold-v1",
            "dataset_id": DATASET_ID,
            "case_count": len(L2_BLUEPRINTS),
            "items": gold_items,
        },
    }


def assert_public_carries_no_verdict(public_payload: dict[str, Any]) -> None:
    """Refuse a public payload that leaks any author verdict.

    Checked structurally rather than trusted: a verdict key reaching the
    proposer's input would make the score meaningless in a way the score itself
    would not reveal.
    """

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _VERDICT_KEYS:
                    raise ValueError(
                        f"public payload leaks author verdict {key!r} at {path}"
                    )
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(public_payload, "public")
    for case in public_payload.get("cases", []):
        unexpected = set(case) - _PUBLIC_ALLOWED_KEYS
        if unexpected:
            raise ValueError(
                f"public case carries unexpected keys: {sorted(unexpected)}"
            )


#: L2 的判定门槛。与既有 dev/fresh 数据集一致，避免为本次评测另设一套标准。
_L2_THRESHOLDS: dict[str, float | int] = {
    "deterministic_critical_false_materialization_count": 0,
    "exact_evidence_rate": 1.0,
    "proposal_coverage": 1.0,
    "raw_abstention_f1": 0.8,
    "raw_critical_false_emission_count": 0,
    "raw_decision_accuracy": 0.9,
    "safety_field_accuracy": 0.85,
    "schema_valid_rate": 1.0,
    "source_coverage_accuracy": 1.0,
    "support_id_accuracy": 1.0,
}


def build_manifest(
    *,
    layer: str,
    payloads: dict[str, dict[str, Any]],
    case_count: int,
    l1_payloads: dict[str, dict[str, Any]] | None = None,
    dataset_id: str = DATASET_ID,
) -> dict[str, Any]:
    """Bind the three outputs by hash, with the claim boundary recorded.

    For L2, ``l1_qualification_sha256`` binds the exact L1 dataset the L2 cases
    build on, so an L2 result cannot later be paired with different L1 data.
    """
    from .authoritative_memory import canonical_json_bytes

    output_sha256 = {
        name: hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        for name, payload in sorted(payloads.items())
    }
    if layer == "l2":
        if l1_payloads is None:
            raise ValueError("an L2 manifest must bind its L1 dataset")
        l1_manifest = build_manifest(
            layer="l1",
            payloads=l1_payloads,
            case_count=len(l1_payloads["gold-l1.json"]["items"]),
            dataset_id=dataset_id,
        )
        qualification = {
            name: hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
            for name, payload in sorted(l1_payloads.items())
        }
        qualification["manifest-l1.json"] = hashlib.sha256(
            canonical_json_bytes(l1_manifest)
        ).hexdigest()
        return {
            "schema_version": "typed-extractor-l2-manifest-v1",
            "dataset_id": dataset_id,
            "case_count": case_count,
            "input_sha256": {
                "authored_blueprints": hashlib.sha256(
                    canonical_json_bytes(
                        {
                            "coverage": coverage_report(),
                            "label_confidence": label_confidence_report(),
                        }
                    )
                ).hexdigest(),
            },
            "l1_qualification_sha256": qualification,
            "output_sha256": output_sha256,
            "distribution": {
                "coverage": coverage_report(),
                "label_confidence": label_confidence_report(),
            },
            "thresholds": dict(_L2_THRESHOLDS),
            "claim_boundary": {
                "diagnostic_only": True,
                "automatic_authoritative_writes": False,
                "embedding_authority": False,
                "fresh_hidden_v2_created": False,
                "longmemeval_status": "structured_l2_identity_unresolved",
            },
        }
    return {
        "schema_version": f"typed-extractor-{layer}-manifest-v1",
        "dataset_id": dataset_id,
        "case_count": case_count,
        "input_sha256": {
            "authored_blueprints": hashlib.sha256(
                canonical_json_bytes(
                    {
                        "coverage": coverage_report(),
                        "label_confidence": label_confidence_report(),
                    }
                )
            ).hexdigest(),
        },
        "output_sha256": output_sha256,
        "distribution": {
            "coverage": coverage_report(),
            "label_confidence": label_confidence_report(),
        },
        "claim_boundary": {
            "diagnostic_only": True,
            "automatic_authoritative_writes": False,
            "embedding_authority": False,
            "fresh_hidden_v2_created": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    }


def freeze_dataset(
    root: Path,
    *,
    l1_blueprints: tuple[L1CaseBlueprint, ...] = L1_BLUEPRINTS,
    l2_blueprints: tuple[Any, ...] = L2_BLUEPRINTS,
    dataset_id: str = DATASET_ID,
) -> dict[str, Any]:
    """Write and freeze every artifact once, refusing to overwrite.

    Append-only by construction: a changed dataset is a new directory, so a
    frozen record can never be quietly rewritten. The case set is a parameter so
    a later hidden version is a new directory built by the same code.
    """
    import os

    from .authoritative_memory import canonical_json_bytes

    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"dataset root already populated: {root}")
    root.mkdir(parents=True, exist_ok=True)

    written: dict[str, str] = {}
    l1_payloads = build_l1_payloads(
        blueprints=l1_blueprints, dataset_id=dataset_id
    )
    for layer, blueprints in (("l1", l1_blueprints), ("l2", l2_blueprints)):
        payloads = (
            l1_payloads
            if layer == "l1"
            else build_l2_payloads(
                blueprints=l2_blueprints, dataset_id=dataset_id
            )
        )
        assert_public_carries_no_verdict(payloads[f"public-{layer}.json"])
        manifest = build_manifest(
            layer=layer,
            payloads=payloads,
            case_count=len(blueprints),
            l1_payloads=l1_payloads if layer == "l2" else None,
            dataset_id=dataset_id,
        )
        for name, payload in (*payloads.items(), (f"manifest-{layer}.json", manifest)):
            path = root / name
            data = canonical_json_bytes(payload)
            path.write_bytes(data)
            os.chmod(path, 0o444)
            written[name] = hashlib.sha256(data).hexdigest()
    return written
