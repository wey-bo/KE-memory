from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar, cast


ItemT = TypeVar("ItemT")
ResultT = TypeVar("ResultT")


class _WorkerCancelled(Exception):
    pass


@dataclass(frozen=True)
class BatchFailure:
    item_id: str
    input_ordinal: int
    error_type: str
    message: str


@dataclass(frozen=True)
class BatchOutcome(Generic[ResultT]):
    values: tuple[ResultT, ...]
    failures: tuple[BatchFailure, ...]


async def bounded_ordered_map(
    items: Iterable[ItemT],
    worker: Callable[[ItemT], Awaitable[ResultT]],
    *,
    limit: int,
) -> tuple[ResultT, ...]:
    values = tuple(items)
    semaphore = asyncio.Semaphore(_positive_limit(limit))
    results: list[ResultT | None] = [None] * len(values)
    owner = asyncio.current_task()
    if owner is None:
        raise RuntimeError("bounded execution requires an asyncio task")
    owner_cancellations = owner.cancelling()

    async def run(index: int, item: ItemT) -> None:
        try:
            async with semaphore:
                results[index] = await worker(item)
        except asyncio.CancelledError as error:
            if owner.cancelling() > owner_cancellations:
                raise
            raise _WorkerCancelled from error

    try:
        async with asyncio.TaskGroup() as group:
            for index, item in enumerate(values):
                group.create_task(run(index, item))
    except* _WorkerCancelled:
        raise asyncio.CancelledError from None
    return tuple(cast(ResultT, value) for value in results)


async def bounded_collect(
    items: Iterable[ItemT],
    *,
    key: Callable[[ItemT], str],
    worker: Callable[[ItemT], Awaitable[ResultT]],
    limit: int,
) -> BatchOutcome[ResultT]:
    values = tuple(items)
    semaphore = asyncio.Semaphore(_positive_limit(limit))
    results: list[ResultT | None] = [None] * len(values)
    failed = [False] * len(values)
    failures: list[BatchFailure] = []
    owner = asyncio.current_task()
    if owner is None:
        raise RuntimeError("bounded execution requires an asyncio task")
    owner_cancellations = owner.cancelling()

    async def run(index: int, item: ItemT) -> None:
        try:
            async with semaphore:
                try:
                    results[index] = await worker(item)
                except Exception as error:
                    failed[index] = True
                    failures.append(
                        BatchFailure(
                            item_id=key(item),
                            input_ordinal=index,
                            error_type=type(error).__name__,
                            message=str(error),
                        )
                    )
        except asyncio.CancelledError as error:
            if owner.cancelling() > owner_cancellations:
                raise
            raise _WorkerCancelled from error

    try:
        async with asyncio.TaskGroup() as group:
            for index, item in enumerate(values):
                group.create_task(run(index, item))
    except* _WorkerCancelled:
        raise asyncio.CancelledError from None

    return BatchOutcome(
        values=tuple(
            cast(ResultT, value)
            for index, value in enumerate(results)
            if not failed[index]
        ),
        failures=tuple(sorted(failures, key=lambda failure: failure.input_ordinal)),
    )


def _positive_limit(limit: int) -> int:
    if limit < 1:
        raise ValueError("limit must be positive")
    return limit
