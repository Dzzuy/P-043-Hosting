"""Read-only index compatibility check; no schema creation or embeddings calls.

Run: .venv/Scripts/python.exe -m scripts.check_copilot_index
"""

import json
import shutil
import tempfile
from pathlib import Path

import psycopg

from src.config import get_settings
from src.knowledge.index_readiness import IndexNotReadyError, load_snapshot, verify_index
from src.knowledge.pgvector_store import PgVectorStore
from src.knowledge.vector_store import ChromaVectorStore


def check(store, settings):
    records = store.read_records()
    result = {"backend": settings.vector_store_type, "stored_chunks": len(records)}
    result["query_hits"] = len(store.similarity_search(records[0][1], top_k=1)) if records else 0
    try:
        verify_index(store, load_snapshot(), settings)
        result["readiness"] = "ready"
    except IndexNotReadyError as exc:
        result.update(readiness="not_ready", reason=str(exc))
    print(json.dumps(result))
    return 0 if result["readiness"] == "ready" else 1


def main():
    settings = get_settings()
    try:
        if settings.vector_store_type == "pgvector":
            # Skip the normal constructor's CREATE EXTENSION/TABLE calls.
            store = object.__new__(PgVectorStore)
            store.database_url, store.collection_name = settings.database_url, settings.chroma_collection_name

            def read_only_connection():
                connection = psycopg.connect(settings.database_url, connect_timeout=10)
                connection.read_only = True
                connection.execute("SET LOCAL statement_timeout = '10s'")
                return connection

            store._connect = read_only_connection
            return check(store, settings)
        if settings.vector_store_type == "chroma":
            source = Path(settings.chroma_persist_dir)
            if not source.exists():
                raise FileNotFoundError("Chroma index does not exist")
            # Chroma can migrate schemas on open: inspect a disposable copy.
            task_tmp = Path(tempfile.mkdtemp(prefix="p043-index-check-")).resolve()
            target = task_tmp / "chroma"
            shutil.copytree(source, target)
            result = check(ChromaVectorStore(str(target), settings.chroma_collection_name), settings)
            # Chroma's Rust client may keep Windows files open until process exit.
            if task_tmp.parent == Path(tempfile.gettempdir()).resolve() and task_tmp.name.startswith(
                "p043-index-check-"
            ):
                shutil.rmtree(task_tmp, ignore_errors=True)
            return result
        raise ValueError("Only persistent backends can be checked")
    except Exception as exc:
        # Connection strings/passwords may occur in driver exception messages.
        print(
            json.dumps(
                {"backend": settings.vector_store_type, "readiness": "unavailable", "error_type": type(exc).__name__}
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
