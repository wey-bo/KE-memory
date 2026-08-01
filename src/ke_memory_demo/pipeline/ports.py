"""The narrow surface ``EvaluationStage`` needs from the pipeline runtime.

Defined here, in the layer below evaluation, so evaluation can depend on it while
``pipeline`` stays free of any evaluation import.

Deliberately *not* the runtime factory itself. Handing ``EvaluationStage`` the whole
factory would replace an import cycle with a service locator: the stage could then
reach any attribute, the real coupling would stop being visible in a signature, and
the dependency gate would go quiet while nothing had actually been decoupled. What
the stage may use is exactly what these two types expose.

``RuntimeContext`` carries the immutable run identity the stage reads and never
mutates. ``EvaluationPort`` is the behaviour it calls. Both are structural, so the
pipeline never subclasses anything from evaluation and nothing needs registering.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from ke_memory_demo.systems import KEMemorySystem

SnapshotModelT = TypeVar("SnapshotModelT", bound=BaseModel)


class RuntimeContext(BaseModel):
    """Immutable run identity shared with the evaluation stage.

    Frozen because these values identify the run being measured: a stage that could
    change them could make a report describe a different state root or commit than
    the one it actually read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    state_root: Path
    code_commit: str


class EvaluationPort(Protocol):
    """Pipeline behaviour the evaluation stage is allowed to invoke.

    A Protocol rather than a base class, so the pipeline factory satisfies it by
    having the right methods and never imports this module. Kept to the two
    operations the stage genuinely needs -- widening it is how a narrow port turns
    back into a factory handle.
    """

    async def build_ke_systems(
        self,
        run_id: str,
        snapshot_id: str,
        *,
        conversation_ids: frozenset[str] | None = None,
    ) -> Mapping[str, KEMemorySystem]:
        """Build the memory systems for a verified ke-ready snapshot."""
        ...

    def snapshot_records(
        self,
        snapshot_id: str,
        run_id: str,
        artifact_name: str,
        model: type[SnapshotModelT],
    ) -> tuple[SnapshotModelT, ...]:
        """Read typed artifact records out of a snapshot."""
        ...
