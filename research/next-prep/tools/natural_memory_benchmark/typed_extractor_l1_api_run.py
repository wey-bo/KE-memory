from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from .frozen_input_guard import require_frozen_input
from .io import load_json, sha256_file, write_json_immutable
from .typed_extractor_l1 import L1PublicPayload
from .typed_extractor_model_run import (
    L1ModelDispatch,
    _validate_dispatch,
    extract_l1_proposal_payload,
)


def _require_read_only(path: Path, label: str) -> None:
    """Verify a committed input portably.

    Content-based rather than mode-based: git records only the executable bit, so
    a 0444 input arrives as 0644 and a mode precondition rejects correct files on
    every fresh clone. Mode is retained only for freshly written output -- see
    ``frozen_input_guard``.
    """
    require_frozen_input(path, label)


def _write_exclusive_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
    path.chmod(0o444)


def run_l1_openai_compatible_proposer(
    *,
    public_path: Path,
    prompt_path: Path,
    dispatch_path: Path,
    raw_response_path: Path,
    staged_proposals_path: Path,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
    max_tokens: int = 16000,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    public_path = public_path.resolve()
    prompt_path = prompt_path.resolve()
    dispatch_path = dispatch_path.resolve()
    raw_response_path = raw_response_path.resolve()
    staged_proposals_path = staged_proposals_path.resolve()
    for path, label in (
        (public_path, "public input"),
        (prompt_path, "prompt"),
        (dispatch_path, "dispatch"),
    ):
        _require_read_only(path, label)
    public = L1PublicPayload.model_validate(load_json(public_path))
    dispatch = L1ModelDispatch.model_validate(load_json(dispatch_path))
    _validate_dispatch(
        dispatch,
        public_path=public_path,
        prompt_path=prompt_path,
        isolation_context=dispatch.isolation_context,
    )
    if model != dispatch.requested_model:
        raise ValueError("requested model does not match frozen dispatch")
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt_path.read_text(encoding="utf-8")},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "dispatch_metadata": {
                            "run_id": dispatch.run_id,
                            "proposer_id": dispatch.proposer_id,
                            "proposer_version": dispatch.proposer_version,
                        },
                        "public_input": public.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(request_payload, ensure_ascii=False).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with opener(request, timeout=timeout_seconds) as response:
        raw_bytes = response.read()
    _write_exclusive_bytes(raw_response_path, raw_bytes)
    response_payload = json.loads(raw_bytes)
    response_model = response_payload.get("model")
    if not isinstance(response_model, str) or not response_model.strip():
        raise ValueError("API response does not identify the response model")
    proposal_payload = extract_l1_proposal_payload(response_payload)
    if (
        proposal_payload.dataset_id != public.dataset_id
        or proposal_payload.case_count != public.case_count
        or proposal_payload.run_id != dispatch.run_id
        or proposal_payload.proposer_id != dispatch.proposer_id
        or proposal_payload.proposer_version != dispatch.proposer_version
    ):
        raise ValueError("model proposal metadata does not match dispatch")
    write_json_immutable(staged_proposals_path, proposal_payload)
    staged_proposals_path.chmod(0o444)
    return {
        "status": "staged",
        "run_id": dispatch.run_id,
        "case_count": public.case_count,
        "requested_model": model,
        "response_model": response_model,
        "raw_response_sha256": sha256_file(raw_response_path),
        "staged_proposals_sha256": sha256_file(staged_proposals_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--dispatch", required=True)
    parser.add_argument("--raw-response", required=True)
    parser.add_argument("--staged-proposals", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-tokens", type=int, default=16000)
    args = parser.parse_args()
    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("OPENAI_BASE_URL and OPENAI_API_KEY are required")
    result = run_l1_openai_compatible_proposer(
        public_path=Path(args.public),
        prompt_path=Path(args.prompt),
        dispatch_path=Path(args.dispatch),
        raw_response_path=Path(args.raw_response),
        staged_proposals_path=Path(args.staged_proposals),
        base_url=base_url,
        api_key=api_key,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        max_tokens=args.max_tokens,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
