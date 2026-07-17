from .fusion import EvidenceCandidate
from .query import RetrievalInvariantError


class DisabledEmbeddingRetriever:
    async def retrieve(self, *, question: str) -> tuple[EvidenceCandidate, ...]:
        if not question.strip():
            raise RetrievalInvariantError("question must not be empty")
        return ()
