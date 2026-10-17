"""The destructive demo reseed path must stay outside production."""

from types import SimpleNamespace

import pytest

from scripts import seed_demo_users


@pytest.mark.asyncio
async def test_demo_seed_rejects_production_before_database_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_demo_users, "get_settings", lambda: SimpleNamespace(app_env="production"))

    with pytest.raises(RuntimeError, match="outside production"):
        await seed_demo_users.seed()
