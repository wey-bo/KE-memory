"""Run the Phase C proposer against the frozen public cases.

One real request per layer, no retry, no fallback. The attempt is frozen in the
order the provenance contract requires — dispatch, raw response, proposals,
provenance — so a later artifact can never be the reason an earlier one looks
consistent.

The proposer is handed the public payload only. Gold and authority live in the
same directory, so the caller passes the public *files* rather than the directory
and the exposure check is run before the request goes out.

Credentials come from the environment and are never written to a dispatch, a
provenance record, a log line or an exception message. The dispatch records the
base URL host and the model name, which are configuration rather than secrets.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

from .authoritative_memory import canonical_json_bytes

RUN_ROOT = Path("/public/home/wwb/KE_mem/ke-memory-demo/.runs")
DATASET_ID = "operational-profile-fresh-hidden-v1"

_L1_SYSTEM_PROMPT = (
    "You extract durable memory facts. For each case you receive the raw turn "
    "and an untyped candidate. Decide exactly one of: emit_l1 when the user's "
    "own words state a durable fact; abstain when a fact may be present but the "
    "evidence does not support recording it as actual; no_memory when the turn "
    "states nothing durable to keep.\n"
    "Return JSON only, as {\"proposals\": [{\"case_id\": ..., "
    "\"candidate_ref\": ..., \"decision\": ..., \"confidence\": 0.0-1.0, "
    "\"reason_code\": ..., \"typed_candidate\": ... or null}]}.\n"
    "typed_candidate is required for emit_l1 and must be null otherwise. It "
    "carries kind, predicate{surface,sense,canonical_operator}, local_entities, "
    "roles, modality, polarity, time, condition_bindings, scope_bindings, "
    "derivation, evidence_bindings, lifecycle and operation_provenance.\n"
    "Use only operators, senses, kinds, modalities and polarities listed in "
    "allowed_vocabulary. Quote entity surfaces verbatim from the user text. "
    "Never invent a fact the text does not state."
)

_L2_SYSTEM_PROMPT = (
    "You decide whether admitted L1 facts jointly establish a durable "
    "abstraction. For each case you receive the source turns, an untyped "
    "candidate and the typed L1 support pack. Decide emit_l2 when the support "
    "establishes the abstraction, or abstain when it does not.\n"
    "Return JSON only, as {\"proposals\": [{\"case_id\": ..., "
    "\"candidate_ref\": ..., \"decision\": ..., \"confidence\": 0.0-1.0, "
    "\"reason_code\": ..., \"typed_candidate\": ... or null}]}.\n"
    "typed_candidate is required for emit_l2 and must be null otherwise.\n"
    "Abstain when the summary names something no support mentions, or when the "
    "support denies what the summary asserts. Never emit an abstraction the "
    "support does not carry."
)


class ProposerError(RuntimeError):
    """Credential-safe failure at the Phase C proposer boundary."""


def _endpoint() -> tuple[str, str, str]:
    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    missing = [
        name
        for name, value in (
            ("OPENAI_BASE_URL", base_url),
            ("OPENAI_API_KEY", api_key),
            ("OPENAI_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise ProposerError(
            "missing required environment configuration: " + ", ".join(missing)
        )
    assert base_url is not None and api_key is not None and model is not None
    return base_url.rstrip("/"), api_key, model


def _request(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    public_payload: dict[str, Any],
    timeout_seconds: int,
) -> bytes:
    """Issue exactly one request and return the raw response bytes.

    Errors report an HTTP status and a response fingerprint, never the body or
    any header, so a failure cannot leak the key or provider content.
    """
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(public_payload, sort_keys=True),
                },
            ],
            "temperature": 0,
        },
        sort_keys=True,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read()
    except urllib.error.HTTPError as error:  # pragma: no cover - network path
        payload = error.read() or b""
        raise ProposerError(
            f"proposer request failed: http_status={error.code}; "
            f"response_sha256={hashlib.sha256(payload).hexdigest()}"
        ) from None
    except Exception as error:  # pragma: no cover - network path
        raise ProposerError(
            f"proposer request failed: reason={type(error).__name__}"
        ) from None


def _freeze(path: Path, data: bytes) -> str:
    if path.exists():
        raise ProposerError(f"refusing to overwrite a frozen artifact: {path.name}")
    path.write_bytes(data)
    os.chmod(path, 0o444)
    return hashlib.sha256(data).hexdigest()


def run_layer(
    *,
    layer: Literal["l1", "l2"],
    dataset_root: Path,
    attempt_root: Path,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Run one layer's single attempt and freeze it in contract order."""
    from .operational_profile_fresh_prereg import assert_gold_not_exposed

    dataset_root = Path(dataset_root).resolve()
    attempt_root = Path(attempt_root)
    if attempt_root.exists() and any(attempt_root.iterdir()):
        raise ProposerError(f"attempt root already populated: {attempt_root}")
    attempt_root.mkdir(parents=True, exist_ok=True)

    public_path = dataset_root / f"public-{layer}.json"
    system_prompt = _L1_SYSTEM_PROMPT if layer == "l1" else _L2_SYSTEM_PROMPT
    # 请求发出之前先确认 gold 不可达：事后再查就已经晚了。
    assert_gold_not_exposed(
        gold_paths=(
            dataset_root / "gold-l1.json",
            dataset_root / "gold-l2.json",
            dataset_root / "authority-l1.json",
            dataset_root / "authority-l2.json",
        ),
        proposer_readable_paths=(public_path,),
        prompt_text=system_prompt,
    )
    public_payload = json.loads(public_path.read_text(encoding="utf-8"))
    base_url, api_key, model = _endpoint()

    # 1) dispatch：先冻结"打算做什么"，再去做。
    dispatch = {
        "schema_version": f"operational-profile-{layer}-dispatch-v1",
        "status": "frozen",
        "dataset_id": DATASET_ID,
        "layer": layer,
        "case_count": public_payload["case_count"],
        "requested_model": model,
        "endpoint_host": base_url.split("://")[-1].split("/")[0],
        "isolation_context": "fresh-agent-no-history-declarative",
        "history_context_inherited": False,
        "authority_or_gold_allowed": False,
        "requests_authorized": 1,
        "retry_authorized": False,
        "allowed_files": {f"public-{layer}.json": str(public_path)},
        "allowed_input_sha256": {
            f"public-{layer}.json": hashlib.sha256(
                public_path.read_bytes()
            ).hexdigest()
        },
        "system_prompt_sha256": hashlib.sha256(
            system_prompt.encode("utf-8")
        ).hexdigest(),
    }
    dispatch_sha = _freeze(
        attempt_root / f"dispatch-{layer}.json", canonical_json_bytes(dispatch)
    )

    # 2) raw response：原样冻结，评分前不做任何加工。
    raw = _request(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        public_payload=public_payload,
        timeout_seconds=timeout_seconds,
    )
    raw_sha = _freeze(attempt_root / f"raw-response-{layer}.json", raw)

    # 3) proposals：从原始响应中提取，附上数据集与运行身份。
    envelope = json.loads(raw.decode("utf-8"))
    response_model = envelope.get("model") or model
    message = (envelope.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or message.get("reasoning_content") or ""
    content = content.strip()
    if content.startswith("```"):
        lines = [
            line
            for line in content.splitlines()
            if not line.strip().startswith("```")
        ]
        content = "\n".join(lines).strip()
    if not content:
        raise ProposerError(
            "proposer returned no JSON content: "
            f"response_sha256={raw_sha}"
        )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        raise ProposerError(
            f"proposer content is not JSON: response_sha256={raw_sha}"
        ) from None
    run_id = f"phase-c-{layer}-" + hashlib.sha256(
        f"{DATASET_ID}:{layer}:{raw_sha}".encode()
    ).hexdigest()[:16]
    proposals = {
        "schema_version": f"typed-extractor-{layer}-proposals-v1",
        "dataset_id": DATASET_ID,
        "run_id": run_id,
        "proposer_id": "operational-profile-openai-proposer",
        "proposer_version": "1",
        "case_count": public_payload["case_count"],
        "proposals": parsed.get("proposals", parsed),
    }
    proposals_sha = _freeze(
        attempt_root / f"proposals-{layer}.json", canonical_json_bytes(proposals)
    )

    # 4) provenance：最后冻结，绑定前三者的哈希。
    provenance = {
        "schema_version": f"operational-profile-{layer}-provenance-v1",
        "status": "frozen",
        "dataset_id": DATASET_ID,
        "layer": layer,
        "case_count": public_payload["case_count"],
        "run_id": run_id,
        "proposer_id": "operational-profile-openai-proposer",
        "proposer_version": "1",
        "requested_model": model,
        "response_model": response_model,
        "isolation_context": "fresh-agent-no-history-declarative",
        "history_context_inherited": False,
        "authority_or_gold_read_before_freeze": False,
        "requests_issued": 1,
        "retried": False,
        "allowed_files": dispatch["allowed_files"],
        "allowed_input_sha256": dispatch["allowed_input_sha256"],
        "dispatch_filename": f"dispatch-{layer}.json",
        "dispatch_sha256": dispatch_sha,
        "raw_response_filename": f"raw-response-{layer}.json",
        "raw_response_sha256": raw_sha,
        "proposals_sha256": proposals_sha,
        "proposal_source_verified": True,
        "freeze_sequence": ["dispatch", "raw_response", "proposals", "provenance"],
    }
    _freeze(
        attempt_root / f"provenance-{layer}.json", canonical_json_bytes(provenance)
    )
    return {
        "run_id": run_id,
        "requested_model": model,
        "response_model": response_model,
        "dispatch_sha256": dispatch_sha,
        "raw_response_sha256": raw_sha,
        "proposals_sha256": proposals_sha,
    }
