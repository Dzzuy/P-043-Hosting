"""Durable per-session voice usage without storing recordings or transcripts."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, DateTime, Float, MetaData, String, Table, create_engine, func, insert, select

from src.integrations.practice_persistence import normalize_database_url


class VoiceUsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stt_requests: int = 0
    stt_billed_seconds: float = 0
    tts_requests: int = 0
    tts_characters: int = 0
    estimated_usd: float = 0


class SQLVoiceUsageRepository:
    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
        metadata = MetaData()
        self._table = Table(
            "practice_voice_usage",
            metadata,
            Column("id", String(36), primary_key=True),
            Column("session_id", String(120), nullable=False, index=True),
            Column("provider", String(20), nullable=False),
            Column("operation", String(20), nullable=False),
            Column("units", Float, nullable=False),
            Column("estimated_usd", Float, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self._metadata = metadata
        self._schema_lock = Lock()
        self._schema_ready = False

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if not self._schema_ready:
                self._metadata.create_all(self._engine)
                self._schema_ready = True

    def record(self, session_id: str, provider: str, operation: str, units: float, estimated_usd: float) -> None:
        self._ensure_schema()
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._table).values(
                    id=str(uuid4()),
                    session_id=session_id,
                    provider=provider,
                    operation=operation,
                    units=units,
                    estimated_usd=estimated_usd,
                    created_at=datetime.now(UTC),
                )
            )

    def summary(self, session_id: str) -> VoiceUsageSummary:
        self._ensure_schema()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    self._table.c.operation,
                    func.count(),
                    func.sum(self._table.c.units),
                    func.sum(self._table.c.estimated_usd),
                )
                .where(self._table.c.session_id == session_id)
                .group_by(self._table.c.operation)
            ).all()
        summary = VoiceUsageSummary()
        for operation, count, units, cost in rows:
            if operation == "stt":
                summary.stt_requests = count
                summary.stt_billed_seconds = units
            elif operation == "tts":
                summary.tts_requests = count
                summary.tts_characters = int(units)
            summary.estimated_usd += cost
        return summary
