"""Build isolated, hash-bound model payloads for the three pilot routes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Literal, Mapping, Sequence

from tools.amr_pilot.models import Route, SentenceSample


SCHEMA_PAYLOAD = "amr-pilot-model-payload-v1"
SCHEMA_MANIFEST = "amr-pilot-payload-manifest-v1"
ATOMIC_SCHEMA = "amr-pilot-atomic-knowledge-v1"
MODEL_ID = "gpt-5.6-terra"

PROMPT_FILES: dict[Route, tuple[str, str, int]] = {
    "A": ("direct-amr-v1.md", "direct-amr-v1", 1200),
    "B": ("knowledge-to-amr-v1.md", "knowledge-to-amr-v1", 1200),
    "C": ("atomic-knowledge-v1.md", "atomic-knowledge-v1", 1000),
}


@dataclass(frozen=True, slots=True)
class PromptContract:
    route: Route
    version: str
    text: str
    sha256: str
    max_output_tokens: int


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_prompt_contracts(directory: str | Path) -> dict[Route, PromptContract]:
    root = Path(directory)
    contracts: dict[Route, PromptContract] = {}
    for route, (filename, version, max_output_tokens) in PROMPT_FILES.items():
        path = root / filename
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"prompt is empty: {path}")
        contracts[route] = PromptContract(
            route=route,
            version=version,
            text=text,
            sha256=_sha256_bytes(path.read_bytes()),
            max_output_tokens=max_output_tokens,
        )
    return contracts


def validate_atomic_knowledge(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "items",
        "representation_gaps",
    }:
        raise ValueError("atomic knowledge has unknown or missing fields")
    if value["schema_version"] != ATOMIC_SCHEMA:
        raise ValueError("atomic knowledge has an unsupported schema_version")
    items = value["items"]
    gaps = value["representation_gaps"]
    if not isinstance(items, list) or not items:
        raise ValueError("atomic knowledge items must be a non-empty list")
    if not isinstance(gaps, list) or any(not isinstance(gap, str) or not gap.strip() for gap in gaps):
        raise ValueError("atomic knowledge representation_gaps must contain non-empty strings")

    expected_ids = [f"K{index:03d}" for index in range(1, len(items) + 1)]
    actual_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "knowledge_id",
            "statement",
            "evidence_quote",
        }:
            raise ValueError("atomic knowledge item has unknown or missing fields")
        knowledge_id = item["knowledge_id"]
        statement = item["statement"]
        evidence_quote = item["evidence_quote"]
        if not isinstance(knowledge_id, str) or re.fullmatch(r"K[0-9]{3}", knowledge_id) is None:
            raise ValueError("atomic knowledge item has an invalid knowledge_id")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("atomic knowledge statement must be non-empty")
        if not isinstance(evidence_quote, str) or not evidence_quote.strip():
            raise ValueError("atomic knowledge evidence_quote must be non-empty")
        actual_ids.append(knowledge_id)
    if actual_ids != expected_ids:
        raise ValueError("atomic knowledge IDs must be consecutive from K001")
    return value


def build_payload(
    sample: SentenceSample,
    route: Route,
    contracts: Mapping[Route, PromptContract],
    *,
    atomic_knowledge: object | None = None,
) -> dict[str, object]:
    if route not in contracts:
        raise ValueError(f"missing prompt contract for route {route}")
    contract = contracts[route]
    if route == "B":
        if atomic_knowledge is None:
            raise ValueError("route B requires validated atomic knowledge")
        model_input: object = validate_atomic_knowledge(atomic_knowledge)
        user_content = _canonical_bytes(model_input).decode("utf-8")
        input_hash = _sha256_bytes(_canonical_bytes(model_input))
    else:
        if atomic_knowledge is not None:
            raise ValueError(f"route {route} must not receive atomic knowledge")
        user_content = sample.text
        input_hash = sample.text_sha256

    payload: dict[str, object] = {
        "schema_version": SCHEMA_PAYLOAD,
        "sample_id": sample.sample_id,
        "route": route,
        "model_id": MODEL_ID,
        "temperature": 0,
        "max_output_tokens": contract.max_output_tokens,
        "prompt_version": contract.version,
        "prompt_sha256": contract.sha256,
        "input_sha256": input_hash,
        "messages": [
            {"role": "system", "content": contract.text},
            {"role": "user", "content": user_content},
        ],
    }
    payload["payload_sha256"] = _sha256_bytes(_canonical_bytes(payload))
    return payload


def write_payload_manifest(
    contracts: Mapping[Route, PromptContract],
    payloads: Sequence[Mapping[str, object]],
    path: str | Path,
) -> Path:
    prompt_hashes = {route: contracts[route].sha256 for route in ("A", "B", "C")}
    payload_hashes: dict[str, object] = {}
    for payload in payloads:
        key = f"{payload['sample_id']}:{payload['route']}"
        if key in payload_hashes:
            raise ValueError(f"duplicate payload key: {key}")
        payload_hashes[key] = payload["payload_sha256"]
    document = {
        "schema_version": SCHEMA_MANIFEST,
        "prompt_hashes": prompt_hashes,
        "payload_hashes": dict(sorted(payload_hashes.items())),
    }
    content = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output_path = Path(path)
    if output_path.exists():
        if output_path.read_text(encoding="utf-8") == content:
            return output_path
        raise ValueError(f"refusing to overwrite different payload manifest: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
