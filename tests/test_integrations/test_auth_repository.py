"""Authentication latency regressions using an isolated SQLite database."""

import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, event, select, update

from src.integrations.auth_repository import SQLAuthRepository
from src.models.auth import StoredSession
from src.services.auth import AuthenticationRequiredError, AuthService


@pytest.mark.asyncio
async def test_current_user_is_one_readonly_checkout_and_keeps_live_account_flags(tmp_path):
    repo = SQLAuthRepository(f"sqlite:///{tmp_path / 'auth.db'}")
    service = AuthService(repo)
    advisor = await service.create_advisor(username="sales", display_name="Sales", password="temporary secure password")
    token, _ = await service.login("sales", "temporary secure password")
    statements, checkouts = [], []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    def checkout(*args):
        checkouts.append(True)

    event.listen(repo._engine, "before_cursor_execute", capture)
    event.listen(repo._engine.pool, "checkout", checkout)
    try:
        current = await service.current_user(token)
    finally:
        event.remove(repo._engine, "before_cursor_execute", capture)
        event.remove(repo._engine.pool, "checkout", checkout)
    assert current.user_id == advisor.user_id and current.must_change_password
    assert len(checkouts) == len(statements) == 1
    assert statements[0].lstrip().upper().startswith("SELECT")

    # No cache may hide account/flag changes from the next authenticated request.
    with repo._engine.begin() as connection:
        connection.execute(delete(repo._password_change_required).where(repo._password_change_required.c.user_id == advisor.user_id))
    assert not (await service.current_user(token)).must_change_password
    with repo._engine.begin() as connection:
        connection.execute(update(repo._users).where(repo._users.c.user_id == advisor.user_id).values(active=False))
    with pytest.raises(AuthenticationRequiredError):
        await service.current_user(token)
    repo._engine.dispose()


@pytest.mark.asyncio
async def test_slow_auth_sql_does_not_block_an_independent_http_request(tmp_path):
    repo = SQLAuthRepository(f"sqlite:///{tmp_path / 'auth.db'}")
    service = AuthService(repo)
    await service.create_advisor(username="sales", display_name="Sales", password="temporary secure password")
    token, _ = await service.login("sales", "temporary secure password")
    entered, release = Event(), Event()

    def slow_query(conn, cursor, statement, parameters, context, many):
        if "FROM auth_sessions JOIN users" in statement:
            entered.set()
            if not release.wait(3):
                raise AssertionError("Authentication blocked the event loop")

    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    event.listen(repo._engine, "before_cursor_execute", slow_query)
    lookup = asyncio.create_task(service.current_user(token))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
        assert not lookup.done(), "Health must complete while the database read is still blocked"
    finally:
        release.set()
        await lookup
        event.remove(repo._engine, "before_cursor_execute", slow_query)
        repo._engine.dispose()


@pytest.mark.asyncio
async def test_expiry_is_enforced_on_read_and_cleanup_runs_when_creating_a_session(tmp_path):
    repo = SQLAuthRepository(f"sqlite:///{tmp_path / 'auth.db'}")
    service = AuthService(repo)
    user = await service.create_advisor(username="sales", display_name="Sales", password="temporary secure password")
    now = datetime.now(UTC)
    expired = StoredSession(token_hash=service.hash_token("expired"), user_id=user.user_id,
                            created_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1))
    await repo.create_session(expired)
    assert await repo.user_for_session(expired.token_hash, now) is None
    with repo._engine.connect() as connection:
        assert connection.execute(select(repo._sessions.c.token_hash)).scalar_one() == expired.token_hash
    valid = StoredSession(token_hash=service.hash_token("valid"), user_id=user.user_id,
                          created_at=now, expires_at=now + timedelta(hours=1))
    await repo.create_session(valid)
    with repo._engine.connect() as connection:
        assert connection.execute(select(repo._sessions.c.token_hash)).scalars().all() == [valid.token_hash]
    assert (await repo.user_for_session(valid.token_hash, now)).must_change_password
    repo._engine.dispose()
