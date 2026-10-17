"""SQL persistence for local users and opaque authentication sessions."""

from __future__ import annotations

from datetime import datetime
from functools import wraps
from threading import Lock

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from src.integrations.practice_persistence import normalize_database_url
from src.models.auth import AccountAlreadyExistsError, AuthenticatedUser, StoredSession, StoredUser, UserRole


def _offload_sql(function):
    """Keep each synchronous SQL transaction in one worker, outside the event loop."""
    @wraps(function)
    async def run(*args, **kwargs):
        return await run_in_threadpool(function, *args, **kwargs)
    return run


class SQLAuthRepository:
    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(normalize_database_url(database_url), pool_pre_ping=True)
        metadata = MetaData()
        self._users = Table(
            "users",
            metadata,
            Column("user_id", String(120), primary_key=True),
            Column("username", String(120), nullable=False, unique=True, index=True),
            Column("display_name", String(200), nullable=False),
            Column("role", String(20), nullable=False),
            Column("password_hash", String(256), nullable=False),
            Column("password_salt", String(256), nullable=False),
            Column("password_iterations", Integer, nullable=False),
            Column("active", Boolean, nullable=False, default=True),
        )
        self._sessions = Table(
            "auth_sessions",
            metadata,
            Column("token_hash", String(64), primary_key=True),
            Column("user_id", String(120), nullable=False, index=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
        )
        self._password_change_required = Table(
            "password_change_required",
            metadata,
            Column("user_id", String(120), primary_key=True),
        )
        self._metadata = metadata
        self._schema_ready = False
        self._schema_lock = Lock()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if not self._schema_ready:
                self._metadata.create_all(self._engine)
                self._schema_ready = True

    @_offload_sql
    def upsert_user(self, user: StoredUser) -> None:
        """Create or replace one explicitly seeded local user."""
        self._ensure_schema()
        values = user.model_dump(mode="json", exclude={"must_change_password"})
        with self._engine.begin() as connection:
            connection.execute(delete(self._sessions).where(self._sessions.c.user_id == user.user_id))
            connection.execute(delete(self._users).where(self._users.c.user_id == user.user_id))
            # A renamed seeded user must not collide with another account.
            connection.execute(delete(self._users).where(self._users.c.username == user.username))
            connection.execute(insert(self._users).values(**values))

    @_offload_sql
    def create_user(self, user: StoredUser, *, require_password_change: bool = False) -> None:
        """Insert without replacing an account or invalidating its sessions."""
        self._ensure_schema()
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(self._users).values(**user.model_dump(mode="json", exclude={"must_change_password"}))
                )
                if require_password_change:
                    connection.execute(insert(self._password_change_required).values(user_id=user.user_id))
        except IntegrityError as exc:
            raise AccountAlreadyExistsError("username already exists") from exc

    @_offload_sql
    def user_by_username(self, username: str) -> StoredUser | None:
        self._ensure_schema()
        query = select(self._users).where(self._users.c.username == username)
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        return StoredUser.model_validate(dict(row)) if row else None

    @_offload_sql
    def manager_exists(self) -> bool:
        self._ensure_schema()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(self._users.c.user_id).where(self._users.c.role == UserRole.MANAGER.value).limit(1)
            ).first()
        return row is not None

    @_offload_sql
    def requires_password_change(self, user_id: str) -> bool:
        self._ensure_schema()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(self._password_change_required.c.user_id).where(
                    self._password_change_required.c.user_id == user_id
                )
            ).first()
        return row is not None

    @_offload_sql
    def update_password(self, user_id: str, password_hash: str, password_salt: str, iterations: int) -> None:
        self._ensure_schema()
        with self._engine.begin() as connection:
            connection.execute(
                update(self._users)
                .where(self._users.c.user_id == user_id)
                .values(
                    password_hash=password_hash,
                    password_salt=password_salt,
                    password_iterations=iterations,
                )
            )
            connection.execute(
                delete(self._password_change_required).where(self._password_change_required.c.user_id == user_id)
            )
            connection.execute(delete(self._sessions).where(self._sessions.c.user_id == user_id))

    @_offload_sql
    def active_advisors(self) -> list[AuthenticatedUser]:
        """Return public identities only; never expose password fields."""
        self._ensure_schema()
        query = (
            select(self._users.c.user_id, self._users.c.username, self._users.c.display_name, self._users.c.role)
            .where(self._users.c.role == UserRole.ADVISOR.value, self._users.c.active.is_(True))
            .order_by(self._users.c.display_name, self._users.c.user_id)
        )
        with self._engine.connect() as connection:
            return [AuthenticatedUser.model_validate(dict(row)) for row in connection.execute(query).mappings()]

    @_offload_sql
    def active_advisor(self, user_id: str) -> AuthenticatedUser | None:
        self._ensure_schema()
        query = select(
            self._users.c.user_id, self._users.c.username, self._users.c.display_name, self._users.c.role
        ).where(
            self._users.c.user_id == user_id,
            self._users.c.role == UserRole.ADVISOR.value,
            self._users.c.active.is_(True),
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        return AuthenticatedUser.model_validate(dict(row)) if row else None

    @_offload_sql
    def create_session(self, session: StoredSession) -> None:
        self._ensure_schema()
        with self._engine.begin() as connection:
            # Reclaim expired rows on login, never on the authenticated read path.
            connection.execute(delete(self._sessions).where(self._sessions.c.expires_at <= session.created_at))
            connection.execute(insert(self._sessions).values(**session.model_dump()))

    @_offload_sql
    def user_for_session(self, token_hash: str, now: datetime) -> AuthenticatedUser | None:
        self._ensure_schema()
        query = (
            select(
                self._users.c.user_id,
                self._users.c.username,
                self._users.c.display_name,
                self._users.c.role,
                select(self._password_change_required.c.user_id)
                .where(self._password_change_required.c.user_id == self._users.c.user_id)
                .exists().label("must_change_password"),
            )
            .select_from(self._sessions.join(self._users, self._sessions.c.user_id == self._users.c.user_id))
            .where(self._sessions.c.token_hash == token_hash)
            .where(self._sessions.c.expires_at > now)
            .where(self._users.c.active.is_(True))
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        if row is None:
            return None
        return AuthenticatedUser(
            user_id=row.user_id,
            username=row.username,
            display_name=row.display_name,
            role=UserRole(row.role),
            must_change_password=row.must_change_password,
        )

    @_offload_sql
    def delete_session(self, token_hash: str) -> None:
        self._ensure_schema()
        with self._engine.begin() as connection:
            connection.execute(delete(self._sessions).where(self._sessions.c.token_hash == token_hash))
