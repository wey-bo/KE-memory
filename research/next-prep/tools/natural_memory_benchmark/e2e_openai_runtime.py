from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Sequence
from urllib.request import Request, urlopen

from pydantic import Field, TypeAdapter

from .authoritative_memory import ProducerIdentity, StrictModel, canonical_sha256
from .e2e_openai_producers import (
    ModelCallHashV1,
    OpenAICompatibleL1BatchProducer,
    OpenAICompatibleL2Producer,
    build_diagnostic_production_policy,
)
from .e2e_pipeline import (
    EndToEndResultV1,
    EvidenceBackedAnswerV1,
    RawTurnV1,
    build_compiler_registry,
    run_e2e_pipeline,
)
from .l1_ontology_linking import build_diagnostic_ontology_registry
from .query_compiler_v2_openai_producer import OpenAICompatibleQueryDraftProducer


class _BufferedResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_BufferedResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class _QueryRecordingOpener:
    def __init__(self, opener: Callable[..., Any]) -> None:
        self._opener = opener
        self.attempts = 0
        self.request_sha256: str | None = None
        self.response_sha256: str | None = None
        self.response_model: str | None = None

    def __call__(self, request: Request, *, timeout: int) -> _BufferedResponse:
        self.attempts += 1
        request_bytes = request.data
        if not isinstance(request_bytes, bytes):
            raise TypeError("query request body must be bytes")
        with self._opener(request, timeout=timeout) as response:
            raw = response.read()
        self.request_sha256 = hashlib.sha256(request_bytes).hexdigest()
        self.response_sha256 = hashlib.sha256(raw).hexdigest()
        try:
            response_model = json.loads(raw)["model"]
            if not isinstance(response_model, str) or not response_model.strip():
                raise TypeError("query response model is absent")
        except Exception:
            response_model = "unidentified-response-model"
        self.response_model = response_model
        return _BufferedResponse(raw)

    def receipt(self, requested_model: str) -> ModelCallHashV1:
        if (
            self.request_sha256 is None
            or self.response_sha256 is None
            or self.response_model is None
        ):
            raise ValueError("query model call receipt is unavailable")
        return ModelCallHashV1(
            stage="query",
            requested_model=requested_model,
            response_model=self.response_model,
            request_sha256=self.request_sha256,
            response_sha256=self.response_sha256,
            attempts=self.attempts,
        )


class SnapshotRunReceiptV1(StrictModel):
    repository_path: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    previous_git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    verification_status: Literal["valid"] = "valid"


class OpenAIE2ERunReceiptV1(StrictModel):
    schema_version: Literal["openai-e2e-run-receipt-v1"] = (
        "openai-e2e-run-receipt-v1"
    )
    workflow_run_id: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    model_calls: tuple[ModelCallHashV1, ModelCallHashV1, ModelCallHashV1]
    snapshot: SnapshotRunReceiptV1
    answer: EvidenceBackedAnswerV1


@dataclass(frozen=True)
class OpenAIE2EOutcome:
    pipeline: EndToEndResultV1
    receipt: OpenAIE2ERunReceiptV1


def run_openai_e2e(
    *,
    turns: Sequence[RawTurnV1],
    question: str,
    repository_path: Path,
    base_url: str,
    api_key: str,
    model: str,
    opener: Callable[..., Any] = urlopen,
) -> OpenAIE2EOutcome:
    repository_path = repository_path.resolve()
    raw_path = repository_path.with_name(f"{repository_path.name}.raw.json")
    if repository_path.exists() or raw_path.exists():
        raise FileExistsError("model E2E repository and raw artifact must be fresh")
    ordered_turns = [
        RawTurnV1.model_validate(item.model_dump(mode="json")) for item in turns
    ]
    if not ordered_turns:
        raise ValueError("model E2E requires raw turns")
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)

    l1_batch = OpenAICompatibleL1BatchProducer(
        registry=registry,
        policy=policy,
        base_url=base_url,
        api_key=api_key,
        model=model,
        opener=opener,
    )
    bound_l1 = l1_batch.produce(ordered_turns)

    l2_producer = OpenAICompatibleL2Producer(
        registry=registry,
        policy=policy,
        base_url=base_url,
        api_key=api_key,
        model=model,
        opener=opener,
    )
    query_recording_opener = _QueryRecordingOpener(opener)
    query_producer = OpenAICompatibleQueryDraftProducer(
        registry=build_compiler_registry(registry),
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_attempts=2,
        opener=query_recording_opener,
    )
    workflow_run_id = "run-openai-e2e-" + canonical_sha256(
        {
            "turns": [item.model_dump(mode="json") for item in ordered_turns],
            "question": question,
            "model": model,
        }
    )[:16]
    pipeline = run_e2e_pipeline(
        turns=ordered_turns,
        l1_producer=bound_l1,
        l2_producer=l2_producer,
        query_producer=query_producer,
        repository_path=repository_path,
        question=question,
        ontology_registry=registry,
        memory_producer=ProducerIdentity(
            workflow_run_id=workflow_run_id,
            producer_id="openai-compatible-model",
            producer_version=model,
        ),
    )
    if l1_batch.last_call is None or l2_producer.last_call is None:
        raise ValueError("model extraction call receipt is unavailable")
    receipt = OpenAIE2ERunReceiptV1(
        workflow_run_id=workflow_run_id,
        requested_model=model,
        model_calls=(
            l1_batch.last_call,
            l2_producer.last_call,
            query_recording_opener.receipt(model),
        ),
        snapshot=SnapshotRunReceiptV1(
            repository_path=pipeline.snapshot.repository_path,
            checkpoint_id=pipeline.snapshot.checkpoint_id,
            git_commit=pipeline.snapshot.git_commit,
            previous_git_commit=pipeline.snapshot.previous_git_commit,
            verification_status="valid",
        ),
        answer=pipeline.answer,
    )
    return OpenAIE2EOutcome(pipeline=pipeline, receipt=receipt)


def _write_receipt_exclusive(path: Path, receipt: OpenAIE2ERunReceiptV1) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        receipt.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(payload)
    path.chmod(0o444)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    if not base_url or not api_key or not model:
        raise RuntimeError(
            "OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL are required"
        )
    turns_payload = json.loads(Path(args.turns).read_text(encoding="utf-8"))
    turns = TypeAdapter(list[RawTurnV1]).validate_python(turns_payload)
    outcome = run_openai_e2e(
        turns=turns,
        question=args.question,
        repository_path=Path(args.repository),
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    _write_receipt_exclusive(Path(args.result), outcome.receipt)
    print(
        json.dumps(
            {
                "status": "complete",
                "git_commit": outcome.receipt.snapshot.git_commit,
                "answer_values": outcome.receipt.answer.answer_values,
                "result": str(Path(args.result).resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
