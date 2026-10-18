"""Owned dialogue storage: durable advisor/customer sessions and expiring standalone sessions."""

import json
import logging
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    desc,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from src.integrations.practice_persistence import normalize_database_url
from src.observability import db_connection, span

logger = logging.getLogger(__name__)


class CopilotSessionNotFoundError(LookupError):
    pass


class CopilotSessionConflictError(RuntimeError):
    pass


class SQLCopilotSessionsRepository:
    def __init__(self, database_url: str, *, engine=None, ttl_hours: int = 8):
        self.engine = engine or create_engine(normalize_database_url(database_url), pool_pre_ping=True)
        self.ttl = timedelta(hours=ttl_hours)
        self.metadata = MetaData()

        # Legacy sessions table (kept for backward compatibility and fast text replay)
        self.sessions = Table(
            "copilot_sessions",
            self.metadata,
            Column("session_id", String(64), primary_key=True),
            Column("owner_id", String(120), nullable=False, index=True),
            Column("history_json", Text, nullable=False),
            Column("customer_context", Text, nullable=False),
            Column("revision", Integer, nullable=False),
            Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
        )

        # Structured conversations table for session management and listing
        self.conversations = Table(
            "conversations",
            self.metadata,
            Column("session_id", String(64), primary_key=True),
            Column("owner_id", String(120), nullable=False, index=True),
            Column("title", Text, nullable=False),
            Column("last_seq", Integer, nullable=False, default=0),
            Column("customer_context", Text, nullable=False, default=""),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
            Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
        )

        # Immutable message items with rich metadata (citations, product_insights, status)
        self.messages = Table(
            "copilot_messages",
            self.metadata,
            Column("id", String(64), primary_key=True),
            Column("session_id", String(64), nullable=False, index=True),
            Column("request_id", String(64), nullable=True),
            Column("seq", Integer, nullable=False),
            Column("role", String(20), nullable=False),
            Column("content", Text, nullable=False),
            Column("metadata_json", Text, nullable=False, default="{}"),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )

        # Rolling structured memory table
        self.memories = Table(
            "conversation_memories",
            self.metadata,
            Column("session_id", String(64), primary_key=True),
            Column("summary_json", Text, nullable=False, default="{}"),
            Column("summarized_through_seq", Integer, nullable=False, default=0),
            Column("version", Integer, nullable=False, default=0),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

        # A binding gives a session durable, private customer scope. Legacy sessions keep their TTL.
        self.lookup_sessions = Table(
            "sales_copilot_lookup_sessions", self.metadata,
            Column("owner_id", String(120), primary_key=True),
            Column("sales_conversation_id", String(64), primary_key=True),
            Column("session_id", String(64), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            UniqueConstraint("session_id", name="uq_sales_lookup_session"),
        )

        # Shared knowledge Q&A belongs to the advisor, independently of CRM customers.
        self.advisor_sessions = Table(
            "sales_copilot_advisor_sessions", self.metadata,
            Column("owner_id", String(120), primary_key=True),
            Column("session_id", String(64), nullable=False, unique=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )

        self._ready = False
        self._lock = Lock()

    def _ensure_schema(self):
        if not self._ready:
            with self._lock:
                if not self._ready:
                    with span("session.schema", backend="session"):
                        self.metadata.create_all(self.engine)
                    self._ready = True

    def _scope(self, table, owner_id, customer_conversation_id=None, *, advisor=False):
        bound = select(self.lookup_sessions.c.session_id).where(
            self.lookup_sessions.c.session_id == table.c.session_id,
        )
        shared = select(self.advisor_sessions.c.session_id).where(
            self.advisor_sessions.c.session_id == table.c.session_id,
        )
        if advisor:
            return shared.where(self.advisor_sessions.c.owner_id == owner_id).exists() & ~bound.exists()
        if customer_conversation_id is None:
            return ~bound.exists() & ~shared.exists()
        return bound.where(
            self.lookup_sessions.c.owner_id == owner_id,
            self.lookup_sessions.c.sales_conversation_id == customer_conversation_id,
        ).exists()

    def customer_session(self, owner_id, conversation_id, *, create=False):
        """Resolve one stable session per advisor/customer conversation, without writes on GET."""
        self._ensure_schema()
        predicate = (
            self.lookup_sessions.c.owner_id == owner_id,
            self.lookup_sessions.c.sales_conversation_id == conversation_id,
        )
        with self.engine.connect() as connection:
            sid = connection.execute(select(self.lookup_sessions.c.session_id).where(*predicate)).scalar()
        if sid or not create:
            return sid
        sid, now = uuid4().hex, datetime.now(UTC)
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(self.lookup_sessions).values(
                    owner_id=owner_id, sales_conversation_id=conversation_id, session_id=sid,
                    created_at=now, updated_at=now,
                ))
                connection.execute(insert(self.sessions).values(
                    session_id=sid, owner_id=owner_id, history_json="[]", customer_context="",
                    revision=0, expires_at=now + self.ttl,
                ))
            return sid
        except IntegrityError:
            # A concurrent first question may have created the binding while we were reading.
            with self.engine.connect() as connection:
                existing = connection.execute(select(self.lookup_sessions.c.session_id).where(*predicate)).scalar()
            if existing:
                return existing
            raise

    def advisor_session(self, owner_id, *, create=False):
        """One durable knowledge session per advisor. Reads do not create sessions."""
        self._ensure_schema()
        predicate = self.advisor_sessions.c.owner_id == owner_id
        with self.engine.connect() as connection:
            sid = connection.execute(select(self.advisor_sessions.c.session_id).where(predicate)).scalar()
        if sid or not create:
            return sid
        sid, now = uuid4().hex, datetime.now(UTC)
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(self.advisor_sessions).values(
                    owner_id=owner_id, session_id=sid, created_at=now,
                ))
                connection.execute(insert(self.sessions).values(
                    session_id=sid, owner_id=owner_id, history_json="[]", customer_context="",
                    revision=0, expires_at=now + self.ttl,
                ))
            return sid
        except IntegrityError:
            with self.engine.connect() as connection:
                existing = connection.execute(select(self.advisor_sessions.c.session_id).where(predicate)).scalar()
            if existing:
                return existing
            raise

    def load(self, session_id: str, owner_id: str, *, customer_conversation_id=None, advisor=False) -> dict:
        """Load conversation history for Agent intake. Preserves backward compatibility contract."""
        self._ensure_schema()
        with db_connection(self.engine.connect, backend="session") as connection:
            row = (
                connection.execute(
                    select(self.sessions).where(
                        self.sessions.c.session_id == session_id,
                        self.sessions.c.owner_id == owner_id,
                        self._scope(self.sessions, owner_id, customer_conversation_id, advisor=advisor),
                        self.sessions.c.expires_at > datetime.now(UTC) if customer_conversation_id is None and not advisor else True,
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise CopilotSessionNotFoundError(session_id)
        with span("session.deserialize", backend="session"):
            with db_connection(self.engine.connect, backend="session") as conn:
                mem_row = (
                    conn.execute(select(self.memories).where(self.memories.c.session_id == session_id))
                    .mappings()
                    .first()
                )
            mem_summary = json.loads(mem_row["summary_json"]) if mem_row else None
            return {
                "history": json.loads(row["history_json"]),
                "customer_context": row["customer_context"],
                "revision": row["revision"],
                "memory_summary": mem_summary,
            }

    def get_memory_summary(self, session_id: str) -> dict[str, Any] | None:
        """Fetch rolling conversation summary for long sessions."""
        self._ensure_schema()
        with db_connection(self.engine.connect, backend="session") as connection:
            row = (
                connection.execute(select(self.memories).where(self.memories.c.session_id == session_id))
                .mappings()
                .first()
            )
            if row:
                return {
                    "summary": json.loads(row["summary_json"]),
                    "summarized_through_seq": row["summarized_through_seq"],
                    "version": row["version"],
                }
        return None

    def save_memory_summary(
        self,
        session_id: str,
        summary_data: dict[str, Any],
        through_seq: int,
        expected_version: int | None = None,
    ) -> bool:
        """Update or insert rolling conversation summary with non-regressive conditional update."""
        self._ensure_schema()
        now = datetime.now(UTC)
        with db_connection(self.engine.begin, backend="session") as connection:
            row = (
                connection.execute(select(self.memories).where(self.memories.c.session_id == session_id))
                .mappings()
                .first()
            )
            summary_json = json.dumps(summary_data, ensure_ascii=False)
            if row is None:
                connection.execute(
                    insert(self.memories).values(
                        session_id=session_id,
                        summary_json=summary_json,
                        summarized_through_seq=through_seq,
                        version=1,
                        updated_at=now,
                    )
                )
                return True
            else:
                current_ver = row["version"]
                current_through = row["summarized_through_seq"]
                # Reject stale version or regressive watermark
                if expected_version is not None and current_ver != expected_version:
                    logger.warning(
                        "Dropping stale summary update for session %s (expected=%s, current=%s)",
                        session_id,
                        expected_version,
                        current_ver,
                    )
                    return False
                if through_seq < current_through:
                    logger.warning(
                        "Dropping regressive watermark for session %s (through_seq=%s, current=%s)",
                        session_id,
                        through_seq,
                        current_through,
                    )
                    return False

                result = connection.execute(
                    update(self.memories)
                    .where(
                        self.memories.c.session_id == session_id,
                        self.memories.c.version == current_ver,
                    )
                    .values(
                        summary_json=summary_json,
                        summarized_through_seq=through_seq,
                        version=current_ver + 1,
                        updated_at=now,
                    )
                )
                return result.rowcount > 0

    def save(
        self,
        session_id: str,
        owner_id: str,
        history: list,
        customer_context: str,
        revision: int | None = None,
        *,
        rich_turn: dict[str, Any] | None = None,
        customer_conversation_id: str | None = None,
        advisor: bool = False,
    ):
        """Save dialogue history. Preserves optimistic concurrency and synchronizes both tables."""
        self._ensure_schema()
        now = datetime.now(UTC)
        values = {
            "history_json": json.dumps(history[-20:], ensure_ascii=False),
            "customer_context": customer_context,
            "revision": (revision or 0) + 1,
            "expires_at": now + self.ttl,
        }
        with db_connection(self.engine.begin, backend="session") as connection:
            expired_sids = [
                r[0]
                for r in connection.execute(
                    select(self.sessions.c.session_id).where(
                        self.sessions.c.expires_at <= now,
                        self._scope(self.sessions, owner_id),
                    )
                ).fetchall()
            ]
            if expired_sids:
                connection.execute(delete(self.sessions).where(self.sessions.c.session_id.in_(expired_sids)))
                connection.execute(delete(self.conversations).where(self.conversations.c.session_id.in_(expired_sids)))
                connection.execute(delete(self.messages).where(self.messages.c.session_id.in_(expired_sids)))
                connection.execute(delete(self.memories).where(self.memories.c.session_id.in_(expired_sids)))
            if revision is None:
                connection.execute(insert(self.sessions).values(session_id=session_id, owner_id=owner_id, **values))
            else:
                result = connection.execute(
                    update(self.sessions)
                    .where(
                        self.sessions.c.session_id == session_id,
                        self.sessions.c.owner_id == owner_id,
                        self.sessions.c.revision == revision,
                        self._scope(self.sessions, owner_id, customer_conversation_id, advisor=advisor),
                        self.sessions.c.expires_at > now if customer_conversation_id is None and not advisor else True,
                    )
                    .values(**values)
                )
                if result.rowcount != 1:
                    raise CopilotSessionConflictError("conversation changed during request")

            # Also synchronize conversations table
            conv_row = connection.execute(
                select(self.conversations).where(self.conversations.c.session_id == session_id)
            ).mappings().first()

            title = "Cuộc trò chuyện"
            if history:
                first_usr = next((m.get("content") for m in history if m.get("role") == "user"), None)
                if first_usr:
                    title = first_usr[:70].strip()

            curr_seq = conv_row["last_seq"] if conv_row else 0

            if rich_turn:
                u_query = rich_turn.get("user_query") or ""
                resp_data = rich_turn.get("response_data") or {}
                req_id = rich_turn.get("request_id") or uuid4().hex
                user_seq = curr_seq + 1
                asst_seq = curr_seq + 2
                last_seq = asst_seq
                time_str = now.strftime("%H:%M")

                user_msg_id = "msg-" + uuid4().hex[:12]
                connection.execute(
                    insert(self.messages).values(
                        id=user_msg_id,
                        session_id=session_id,
                        request_id=req_id,
                        seq=user_seq,
                        role="user",
                        content=u_query,
                        metadata_json=json.dumps({"time": time_str}, ensure_ascii=False),
                        created_at=now,
                    )
                )

                asst_msg_id = "msg-" + uuid4().hex[:12]
                asst_meta = {
                    "response_data": resp_data,
                    "time": time_str,
                    "citations": resp_data.get("citations", []),
                    "product_insights": resp_data.get("product_insights", []),
                    "status": resp_data.get("status", "answered"),
                    "reason_code": resp_data.get("reason_code"),
                    "missing_information": resp_data.get("missing_information", []),
                }
                connection.execute(
                    insert(self.messages).values(
                        id=asst_msg_id,
                        session_id=session_id,
                        request_id=req_id,
                        seq=asst_seq,
                        role="assistant",
                        content=resp_data.get("answer", ""),
                        metadata_json=json.dumps(asst_meta, ensure_ascii=False),
                        created_at=now,
                    )
                )
            else:
                last_seq = max(curr_seq, len(history))

            if conv_row is None:
                connection.execute(
                    insert(self.conversations).values(
                        session_id=session_id,
                        owner_id=owner_id,
                        title=title,
                        last_seq=last_seq,
                        customer_context=customer_context,
                        created_at=now,
                        updated_at=now,
                        expires_at=now + self.ttl,
                    )
                )
            else:
                connection.execute(
                    update(self.conversations)
                    .where(self.conversations.c.session_id == session_id)
                    .values(
                        customer_context=customer_context,
                        last_seq=last_seq,
                        updated_at=now,
                        expires_at=now + self.ttl,
                    )
                )
            if customer_conversation_id:
                connection.execute(update(self.lookup_sessions).where(
                    self.lookup_sessions.c.session_id == session_id,
                    self.lookup_sessions.c.owner_id == owner_id,
                    self.lookup_sessions.c.sales_conversation_id == customer_conversation_id,
                ).values(updated_at=now))
            return last_seq

    def get_conversation_last_seq(self, session_id: str) -> int:
        """Get the total message sequence count for a conversation."""
        self._ensure_schema()
        with db_connection(self.engine.connect, backend="session") as connection:
            row = connection.execute(
                select(self.conversations.c.last_seq).where(self.conversations.c.session_id == session_id)
            ).scalar()
            return row or 0

    def delete(self, session_id: str, owner_id: str):
        """Delete conversation across all tables."""
        self._ensure_schema()
        with db_connection(self.engine.begin, backend="session") as connection:
            authorized = connection.execute(select(self.sessions.c.session_id).where(
                self.sessions.c.session_id == session_id,
                self.sessions.c.owner_id == owner_id,
                self._scope(self.sessions, owner_id),
            )).scalar()
            if authorized is None:
                raise CopilotSessionNotFoundError(session_id)
            result = connection.execute(
                delete(self.sessions).where(
                    self.sessions.c.session_id == session_id,
                    self.sessions.c.owner_id == owner_id,
                )
            )
            # Delete from structured tables
            connection.execute(
                delete(self.conversations).where(
                    self.conversations.c.session_id == session_id,
                    self.conversations.c.owner_id == owner_id,
                )
            )
            connection.execute(
                delete(self.messages).where(self.messages.c.session_id == session_id)
            )
            connection.execute(
                delete(self.memories).where(self.memories.c.session_id == session_id)
            )
            if result.rowcount != 1:
                raise CopilotSessionNotFoundError(session_id)

    def list_conversations(self, owner_id: str, limit: int = 30) -> list[dict[str, Any]]:
        """List active conversations for a sales user for the sidebar."""
        self._ensure_schema()
        now = datetime.now(UTC)
        with db_connection(self.engine.connect, backend="session") as connection:
            rows = (
                connection.execute(
                    select(self.conversations)
                    .where(
                        self.conversations.c.owner_id == owner_id,
                        self.conversations.c.expires_at > now,
                        self._scope(self.conversations, owner_id),
                    )
                    .order_by(desc(self.conversations.c.updated_at))
                    .limit(limit)
                )
                .mappings()
                .fetchall()
            )
            results = []
            for row in rows:
                sid = row["session_id"]
                msg_count = connection.execute(
                    select(self.messages.c.id).where(self.messages.c.session_id == sid)
                ).rowcount
                if msg_count < 0:
                    msg_count = row["last_seq"]
                results.append(
                    {
                        "session_id": sid,
                        "title": row["title"],
                        "customer_context": row["customer_context"],
                        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
                        "message_count": max(msg_count, row["last_seq"]),
                    }
                )

            # Fallback for any legacy rows in copilot_sessions not yet in conversations
            if not results:
                legacy_rows = (
                    connection.execute(
                        select(self.sessions)
                        .where(
                            self.sessions.c.owner_id == owner_id,
                            self.sessions.c.expires_at > now,
                            self._scope(self.sessions, owner_id),
                        )
                        .limit(limit)
                    )
                    .mappings()
                    .fetchall()
                )
                for lr in legacy_rows:
                    hist = json.loads(lr["history_json"])
                    title = "Cuộc trò chuyện"
                    if hist:
                        first_usr = next((m.get("content") for m in hist if m.get("role") == "user"), None)
                        if first_usr:
                            title = first_usr[:70].strip()
                    results.append(
                        {
                            "session_id": lr["session_id"],
                            "title": title,
                            "customer_context": lr["customer_context"],
                            "created_at": None,
                            "updated_at": None,
                            "message_count": len(hist),
                        }
                    )
            return results

    def get_conversation_detail(self, session_id: str, owner_id: str | None = None) -> dict[str, Any]:
        """Load conversation with full rich messages (including citations and product_insights)."""
        self._ensure_schema()
        now = datetime.now(UTC)
        with db_connection(self.engine.connect, backend="session") as connection:
            # Check authorization and active status in sessions or conversations
            query = select(self.sessions).where(
                self.sessions.c.session_id == session_id,
                self.sessions.c.expires_at > now,
                self._scope(self.sessions, owner_id),
            )
            if owner_id is not None:
                query = query.where(self.sessions.c.owner_id == owner_id)
            row = connection.execute(query).mappings().first()
            if row is None:
                raise CopilotSessionNotFoundError(session_id)

            conv_row = connection.execute(
                select(self.conversations).where(self.conversations.c.session_id == session_id)
            ).mappings().first()
            title = conv_row["title"] if conv_row else "Cuộc trò chuyện"
            context = conv_row["customer_context"] if conv_row else row["customer_context"]

            # Load structured messages
            msg_rows = (
                connection.execute(
                    select(self.messages)
                    .where(self.messages.c.session_id == session_id)
                    .order_by(self.messages.c.seq.asc())
                )
                .mappings()
                .fetchall()
            )

            messages = []
            if msg_rows:
                for mr in msg_rows:
                    meta = json.loads(mr["metadata_json"] or "{}")
                    dt = mr["created_at"]
                    time_str = dt.strftime("%H:%M") if hasattr(dt, "strftime") else "10:00"
                    messages.append(
                        {
                            "id": mr["id"],
                            "role": mr["role"],
                            "content": mr["content"],
                            "time": time_str,
                            "citations": meta.get("citations", []),
                            "product_insights": meta.get("product_insights", []),
                            "status": meta.get("status", "answered"),
                            "missing_information": meta.get("missing_information", []),
                        }
                    )
            else:
                # Fallback to legacy history_json
                raw_hist = json.loads(row["history_json"])
                for idx, m in enumerate(raw_hist, 1):
                    messages.append(
                        {
                            "id": f"msg-legacy-{idx}",
                            "role": m.get("role", "user"),
                            "content": m.get("content", ""),
                            "time": "10:00",
                            "citations": [],
                            "product_insights": [],
                            "status": "answered",
                        }
                    )

            return {
                "session_id": session_id,
                "title": title,
                "customer_context": context,
                "messages": messages,
            }

    def customer_history(self, owner_id, conversation_id, *, before_seq=None, limit=20):
        """Read a bounded rich page; customer authorization is performed by the adapter first."""
        sid = self.customer_session(owner_id, conversation_id)
        return self._history_page(sid, before_seq=before_seq, limit=limit)

    def advisor_history(self, owner_id, *, before_seq=None, limit=20):
        """Load only this advisor's shared knowledge history, with a bounded page."""
        sid = self.advisor_session(owner_id)
        return self._history_page(sid, before_seq=before_seq, limit=limit)

    def _history_page(self, sid, *, before_seq=None, limit=20):
        if not sid:
            return {"session_id": None, "messages": [], "next_before_seq": None}
        query = select(self.messages).where(self.messages.c.session_id == sid)
        if before_seq is not None:
            query = query.where(self.messages.c.seq < before_seq)
        with self.engine.connect() as connection:
            rows = connection.execute(query.order_by(self.messages.c.seq.desc()).limit(limit + 1)).mappings().all()
        more, rows = len(rows) > limit, rows[:limit]
        messages = []
        for row in reversed(rows):
            meta = json.loads(row["metadata_json"] or "{}")
            messages.append({
                "id": row["id"], "seq": row["seq"], "role": row["role"], "content": row["content"],
                "request_id": row["request_id"], "created_at": row["created_at"].isoformat(),
                **meta,
            })
        return {
            "session_id": sid, "messages": messages,
            "next_before_seq": rows[-1]["seq"] if more else None,
        }

    def summary_batch(self, session_id, *, after_seq, through_seq):
        """Internal bounded read for rolling memory, valid for durable and legacy sessions."""
        self._ensure_schema()
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(
                select(self.messages.c.seq, self.messages.c.role, self.messages.c.content).where(
                    self.messages.c.session_id == session_id,
                    self.messages.c.seq > after_seq,
                    self.messages.c.seq <= through_seq,
                ).order_by(self.messages.c.seq).limit(20)
            ).mappings()]


