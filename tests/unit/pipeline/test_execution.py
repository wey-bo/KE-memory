from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ke_memory_demo.aggregation import SessionMemory
from ke_memory_demo.extraction import TurnExtractionResult
from ke_memory_demo.pipeline import CheckpointStore, bounded_collect, bounded_ordered_map


def result() -> TurnExtractionResult:
    return TurnExtractionResult(
        exchange_id="exchange-1",
        knowledge_equations=(),
        coverage=(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [1, 2, 4])
async def test_bounded_map_preserves_input_order_and_limit(limit: int) -> None:
    active = 0
    peak = 0

    async def worker(value: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep((5 - value) / 1000)
        active -= 1
        return value * 10

    assert await bounded_ordered_map(range(5), worker, limit=limit) == (0, 10, 20, 30, 40)
    assert peak <= limit


@pytest.mark.asyncio
async def test_collect_keeps_successes_and_typed_failures() -> None:
    async def worker(value: int) -> int:
        if value == 2:
            raise ValueError("bad item")
        return value

    outcome = await bounded_collect(range(4), key=str, worker=worker, limit=2)
    assert outcome.values == (0, 1, 3)
    assert [(item.item_id, item.error_type) for item in outcome.failures] == [("2", "ValueError")]


def test_checkpoint_rejects_changed_input_and_model(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "state", run_id="run-1")
    store.save("turn-ke-extracted", "exchange-1", "a" * 64, TurnExtractionResult, result())
    assert store.load("turn-ke-extracted", "exchange-1", "a" * 64, TurnExtractionResult) == result()
    assert store.load("turn-ke-extracted", "exchange-1", "b" * 64, TurnExtractionResult) is None
    assert store.load("turn-ke-extracted", "exchange-1", "a" * 64, SessionMemory) is None
