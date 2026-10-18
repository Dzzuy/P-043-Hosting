"""Isolated, optional LangSmith tracing for Practice operations."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from langsmith import Client, RunTree, tracing_context

from src.config import Settings, get_settings
from src.observability import redact

logger = logging.getLogger(__name__)


class RoleplayTracing:
    """Own the Roleplay account client without changing ambient SDK settings."""

    def __init__(self, settings: Settings) -> None:
        self.project = settings.roleplay_langsmith_project
        self.client: Client | None = None
        if not settings.roleplay_langsmith_tracing:
            return
        key = settings.roleplay_langsmith_api_key.get_secret_value().strip()
        if not key or key.startswith("your-"):
            logger.warning("Roleplay tracing disabled: missing or placeholder API key")
            return
        hide_content = redact if settings.roleplay_langsmith_capture_content else True
        try:
            self.client = Client(
                api_url=settings.roleplay_langsmith_endpoint,
                api_key=key,
                auto_batch_tracing=True,
                timeout_ms=2000,
                hide_inputs=hide_content,
                hide_outputs=hide_content,
            )
        except Exception as exc:
            logger.warning("Roleplay tracing client unavailable (%s)", type(exc).__name__)

    @contextmanager
    def trace(self, name: str, **metadata: str) -> Iterator[None]:
        """Create one root run and let graph/model calls nest under it."""
        if self.client is None:
            with tracing_context(enabled=False):
                yield
            return
        values = {key: redact(value) for key, value in metadata.items() if key in {"session_id", "scenario_id", "kind"}}
        root = None
        try:
            # An explicit RunTree creates a root even inside another account's scope.
            root = RunTree(
                name=name,
                run_type="chain",
                inputs={},
                project_name=self.project,
                ls_client=self.client,
                tags=["roleplay"],
                extra={"metadata": values},
            )
            root.post()
        except Exception as exc:
            logger.warning("Roleplay trace export unavailable (%s)", type(exc).__name__)
            root = None
        error = None
        try:
            with tracing_context(
                enabled=root is not None,
                parent=root if root is not None else False,
                client=self.client,
                project_name=self.project,
                tags=["roleplay"],
                metadata=values,
            ):
                yield
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            if root is not None:
                try:
                    root.end(error=error)
                    root.patch()
                except Exception as exc:
                    logger.warning("Roleplay trace export unavailable (%s)", type(exc).__name__)

    def close(self) -> None:
        """Flush pending runs without breaking application shutdown."""
        if self.client is not None:
            try:
                flush = getattr(self.client, "flush", None)
                if flush is not None:
                    flush()
            except Exception as exc:
                logger.warning("Roleplay trace flush unavailable (%s)", type(exc).__name__)


@lru_cache
def get_roleplay_tracing() -> RoleplayTracing:
    """Reuse the Roleplay client configured by application settings."""
    return RoleplayTracing(get_settings())
