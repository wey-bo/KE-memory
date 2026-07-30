from __future__ import annotations

import json
import socket
from typing import Any, Callable, Literal
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .query_compiler_v2 import (
    AnswerDraftV1,
    CompilerRegistryV1,
    QueryDraftRequestV1,
    QueryDraftV1,
)


class _OperationalAnswerDraftV1(AnswerDraftV1):
    kind: Literal["fact", "count"]


class _OperationalQueryDraftV1(QueryDraftV1):
    answer: _OperationalAnswerDraftV1


def _operational_contract() -> dict[str, object]:
    return {
        "schema_version": "query-draft-operational-contract-v1",
        "answer_kind": {
            "supported": ["fact", "count"],
            "entity_valued_what_which": "fact",
            "explicit_count_or_how_many": "count",
        },
    }


class QueryDraftProductionError(RuntimeError):
    """A credential-safe failure at the remote model boundary."""


class OpenAICompatibleQueryDraftProducer:
    def __init__(
        self,
        *,
        registry: CompilerRegistryV1,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 120,
        max_tokens: int = 4096,
        max_attempts: int = 2,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must be non-empty")
        if not api_key:
            raise ValueError("api_key must be non-empty")
        if not model.strip():
            raise ValueError("model must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.registry = CompilerRegistryV1.model_validate(
            registry.model_dump(mode="json")
        )
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        self._opener = opener

    def _request(self, request: QueryDraftRequestV1) -> Request:
        public_input = {
            "request": request.model_dump(mode="json"),
            "registry": self.registry.model_dump(mode="json"),
            "response_schema": _OperationalQueryDraftV1.model_json_schema(),
            "operational_contract": _operational_contract(),
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Compile the natural-language question into exactly one "
                        "QueryDraftV1 JSON object. Use only aliases and role types "
                        "from the supplied registry. Return JSON only, with no "
                        "Markdown or explanatory text. Follow the supplied "
                        "operational_contract: entity-valued what/which questions "
                        "use answer.kind fact; use count only for explicit count "
                        "or how-many questions."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        public_input,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        return Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    @staticmethod
    def _typed_draft(raw_bytes: bytes, request: QueryDraftRequestV1) -> QueryDraftV1:
        try:
            response = json.loads(raw_bytes)
            choices = response["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("response must contain exactly one choice")
            content = choices[0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("response content must be text")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise TypeError("response content must be a JSON object")
            operational_draft = _OperationalQueryDraftV1.model_validate(payload)
            draft = QueryDraftV1.model_validate(
                operational_draft.model_dump(mode="json")
            )
            if draft.query_id != request.query_id:
                raise ValueError("response query_id mismatch")
            return draft
        except Exception:
            raise QueryDraftProductionError(
                "query draft invalid response"
            ) from None

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        return isinstance(exc, HTTPError) and exc.code in {
            408,
            429,
            500,
            502,
            503,
            504,
        }

    def produce(self, request: QueryDraftRequestV1) -> QueryDraftV1:
        validated_request = QueryDraftRequestV1.model_validate(
            request.model_dump(mode="json")
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._opener(
                    self._request(validated_request),
                    timeout=self.timeout_seconds,
                ) as response:
                    return self._typed_draft(response.read(), validated_request)
            except QueryDraftProductionError:
                raise
            except Exception as exc:
                if self._retryable(exc) and attempt < self.max_attempts:
                    continue
                raise QueryDraftProductionError(
                    "query draft request failed after "
                    f"{attempt} attempt(s) ({type(exc).__name__})"
                ) from None
        raise AssertionError("unreachable query draft retry state")
