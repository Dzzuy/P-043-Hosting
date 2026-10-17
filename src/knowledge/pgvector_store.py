"""PostgreSQL vector store for persistent, diskless web services."""

from __future__ import annotations

import math
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk
from src.knowledge.vector_store import BaseVectorStore
from src.observability import db_connection, span


class PgVectorStore(BaseVectorStore):
    """Small-corpus exact cosine search with the same contract as Chroma."""

    def __init__(self, database_url: str, collection_name: str):
        if not database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("pgvector requires a PostgreSQL DATABASE_URL")
        self.database_url = database_url
        self.collection_name = collection_name
        self._ensure_schema()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, connect_timeout=10)

    def _ensure_schema(self) -> None:
        with db_connection(self._connect, backend="pgvector") as connection:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_vectors (
                    collection_name text NOT NULL,
                    chunk_id text NOT NULL,
                    content text NOT NULL,
                    metadata jsonb NOT NULL,
                    embedding vector NOT NULL,
                    PRIMARY KEY (collection_name, chunk_id)
                )"""
            )

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        if not embedding or any(not math.isfinite(value) for value in embedding):
            raise ValueError("Embedding must contain finite numeric values")
        return "[" + ",".join(str(value) for value in embedding) + "]"

    @staticmethod
    def _chunk(chunk_id: str, content: str, metadata: dict[str, Any]) -> KnowledgeChunk:
        parsed = ChunkMetadata.model_validate(metadata)
        return KnowledgeChunk(
            chunk_id=chunk_id,
            document_id=parsed.document_id,
            content=content,
            metadata=parsed,
        )

    def upsert_chunks(self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Every chunk requires one embedding")
        if not chunks:
            return
        dimensions = {len(embedding) for embedding in embeddings}
        if len(dimensions) != 1:
            raise ValueError("All embeddings in an upsert must have the same dimensions")
        rows = [
            (
                self.collection_name,
                chunk.chunk_id,
                chunk.content,
                Jsonb(chunk.metadata.model_dump(mode="json", exclude_none=True)),
                self._vector_literal(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        with db_connection(self._connect, backend="pgvector") as connection:
            connection.cursor().executemany(
                """INSERT INTO knowledge_vectors (collection_name, chunk_id, content, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (collection_name, chunk_id) DO UPDATE
                SET content = EXCLUDED.content, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding""",
                rows,
            )

    def similarity_search_with_scores(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        if top_k <= 0:
            return []
        query = self._vector_literal(query_embedding)
        filters = ["collection_name = %s"]
        parameters: list[Any] = [query, self.collection_name]
        for key, value in (where or {}).items():
            if value is None:
                continue
            if key not in {"product_model", "document_type", "policy_type"}:
                raise ValueError(f"Unsupported knowledge metadata filter: {key}")
            if isinstance(value, dict):
                if set(value) != {"$in"}:
                    raise ValueError("Only $in metadata filters are supported")
                value = value["$in"]
            values = value if isinstance(value, (list, tuple, set)) else [value]
            normalized = [str(item.value if hasattr(item, "value") else item) for item in values]
            filters.append("metadata ->> %s = ANY(%s)")
            parameters.extend((key, normalized))
        parameters.extend((query, top_k))
        statement = (
            "SELECT chunk_id, content, metadata, 1 - (embedding <=> %s::vector) AS score "
            "FROM knowledge_vectors WHERE " + " AND ".join(filters) + " ORDER BY embedding <=> %s::vector LIMIT %s"
        )
        with db_connection(self._connect, backend="pgvector") as connection:
            rows = connection.execute(statement, parameters).fetchall()
        with span("db.deserialize", backend="pgvector", result_count=len(rows)):
            return [(self._chunk(row[0], row[1], row[2]), float(row[3])) for row in rows]

    def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[KnowledgeChunk]:
        return [chunk for chunk, _ in self.similarity_search_with_scores(query_embedding, top_k, where)]

    def get_by_id(self, chunk_id: str) -> KnowledgeChunk | None:
        with db_connection(self._connect, backend="pgvector") as connection:
            row = connection.execute(
                "SELECT chunk_id, content, metadata FROM knowledge_vectors WHERE collection_name = %s AND chunk_id = %s",
                (self.collection_name, chunk_id),
            ).fetchone()
        return self._chunk(*row) if row else None

    def count(self) -> int:
        with db_connection(self._connect, backend="pgvector") as connection:
            row = connection.execute(
                "SELECT count(*) FROM knowledge_vectors WHERE collection_name = %s",
                (self.collection_name,),
            ).fetchone()
        return int(row[0])

    def read_records(self):
        with db_connection(self._connect, backend="pgvector") as connection:
            rows = connection.execute(
                "SELECT chunk_id, content, metadata, embedding::text FROM knowledge_vectors WHERE collection_name = %s ORDER BY chunk_id",
                (self.collection_name,),
            ).fetchall()
        import json

        records = []
        for cid, content, metadata, vector in rows:
            if set(metadata) - set(ChunkMetadata.model_fields):
                raise ValueError("Unexpected stored metadata")
            records.append((self._chunk(cid, content, metadata), [float(value) for value in json.loads(vector)]))
        return records

    def reset(self) -> None:
        with db_connection(self._connect, backend="pgvector") as connection:
            connection.execute(
                "DELETE FROM knowledge_vectors WHERE collection_name = %s",
                (self.collection_name,),
            )
