from __future__ import annotations

import hashlib
import re
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.pipeline.models import OntologyRunIdentity
from ke_memory_demo.settings import EvaluationConcurrencySettings


PositiveInt = Annotated[int, Field(gt=0)]
GitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_SHA256 = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    code_commit: GitSha
    spec_sha256: Sha256Hex
    plan_sha256: Sha256Hex
    ke_ready_snapshot_id: GitSha
    dataset_sha256: Sha256Hex
    selected_directories: tuple[int, int, int]
    expected_sessions: PositiveInt
    expected_exchanges: PositiveInt
    expected_questions: PositiveInt
    question_manifest_sha256: Sha256Hex
    gold_mapping_sha256: Sha256Hex
    ontology: OntologyRunIdentity
    work_model: str
    work_base_url: str
    judge_model: str
    judge_base_url: str
    answer_prompt_sha256: Sha256Hex
    judge_prompt_sha256: Sha256Hex
    embedding_enabled: Literal[False]
    concurrency: EvaluationConcurrencySettings
    created_at: AwareDatetime
    content_hash: str = ""

    @field_validator("work_base_url", "judge_base_url")
    @classmethod
    def _nonsecret_endpoint(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            _port = parsed.port
        except ValueError:
            raise ValueError("model base URL must be a valid HTTP(S) endpoint") from None
        if (
            parsed.scheme not in {"http", "https"}
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("model base URL must be a non-secret HTTP(S) endpoint")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _freeze_content_hash(self) -> ExperimentManifest:
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_hash", "created_at"}),
        )
        expected = hashlib.sha256(canonical_json(payload)).hexdigest()
        if not self.content_hash:
            object.__setattr__(self, "content_hash", expected)
        elif _SHA256.fullmatch(self.content_hash) is None or self.content_hash != expected:
            raise ValueError("experiment manifest content_hash does not match its content")
        return self
