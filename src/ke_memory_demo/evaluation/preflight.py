from __future__ import annotations

# Defined in core so the pipeline can raise it without importing evaluation.
from ke_memory_demo.core.errors import PreflightCheckFailure

from collections.abc import Awaitable
import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict


PREFLIGHT_CHECK_NAMES = (
    "code_identity",
    "concurrency",
    "credential_scan",
    "embedding",
    "environment",
    "judge_model",
    "ke_ready_snapshot",
    "ontology_identity",
    "state_repo",
    "work_model",
)
_SAFE_DETAIL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/=,()@+\-]*", flags=re.ASCII)
_FORBIDDEN_DETAIL_TERMS = (
    "authorization",
    "bearer",
    "cookie",
    "provider_response",
)


class PreflightCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    detail: str


class PreflightReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checks: tuple[PreflightCheck, ...]

    @property
    def ready(self) -> bool:
        return all(item.passed for item in self.checks)

    @property
    def failed(self) -> tuple[PreflightCheck, ...]:
        return tuple(item for item in self.checks if not item.passed)


class PreflightPorts(Protocol):
    def check(self, name: str) -> Awaitable[str]: ...





class EvaluationPreflight:
    def __init__(self, ports: PreflightPorts) -> None:
        self._ports = ports

    async def run(self) -> PreflightReport:
        checks: list[PreflightCheck] = []
        for name in PREFLIGHT_CHECK_NAMES:
            try:
                raw_detail = await self._ports.check(name)
                detail = _safe_detail(raw_detail)
            except PreflightCheckFailure as error:
                checks.append(
                    PreflightCheck(
                        name=name,
                        passed=False,
                        detail=_safe_failure_detail(error),
                    )
                )
            except Exception as error:
                checks.append(PreflightCheck(name=name, passed=False, detail=type(error).__name__))
            else:
                if detail is None:
                    checks.append(
                        PreflightCheck(
                            name=name,
                            passed=False,
                            detail="PreflightDetailError",
                        )
                    )
                else:
                    checks.append(PreflightCheck(name=name, passed=True, detail=detail))
        return PreflightReport(checks=tuple(sorted(checks, key=lambda item: item.name)))


def _safe_failure_detail(error: PreflightCheckFailure) -> str:
    detail = _safe_detail(str(error))
    return detail if detail is not None else type(error).__name__


def _safe_detail(value: str) -> str | None:
    lowered = value.casefold()
    if (
        not value
        or len(value) > 512
        or _SAFE_DETAIL.fullmatch(value) is None
        or any(term in lowered for term in _FORBIDDEN_DETAIL_TERMS)
    ):
        return None
    return value
