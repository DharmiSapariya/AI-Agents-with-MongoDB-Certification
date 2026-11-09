"""Shared embedding contract for document ingestion and query retrieval."""
import math
from collections.abc import Sequence
from functools import cached_property
from typing import Literal, Protocol

from .config import Settings
from .errors import EmbeddingError

InputType = Literal["query", "document"]


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]: ...


class VoyageEmbeddingProvider:
    def __init__(self, config: Settings):
        self.config = config

    @cached_property
    def client(self):
        import voyageai

        return voyageai.Client(api_key=self.config.voyage_api_key,
                               max_retries=self.config.embedding_max_retries,
                               timeout=self.config.embedding_timeout_s)

    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]:
        try:
            response = self.client.embed(list(texts), model=self.config.embedding_model, input_type=input_type)
            vectors = [[float(value) for value in vector] for vector in response.embeddings]
        except Exception as exc:
            raise EmbeddingError() from exc
        if len(vectors) != len(texts):
            raise EmbeddingError("Embedding provider returned an unexpected number of vectors.")
        if any(len(vector) != self.config.embedding_dims or not all(map(math.isfinite, vector))
               for vector in vectors):
            raise EmbeddingError("Embedding provider returned an invalid vector for the configured dimensions.")
        return vectors
