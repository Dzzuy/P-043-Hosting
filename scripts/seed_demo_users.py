"""Seed local demo accounts without storing passwords in the repository."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from src.config import get_settings  # noqa: E402
from src.integrations.auth_repository import SQLAuthRepository  # noqa: E402
from src.models.auth import UserRole  # noqa: E402
from src.services.auth import AuthService  # noqa: E402


def required_password(variable_name: str) -> str:
    value = os.getenv(variable_name, "")
    if not value:
        raise RuntimeError(f"Set {variable_name} before seeding demo users.")
    return value


async def seed() -> None:
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("Demo account seeding is only allowed outside production")
    service = AuthService(SQLAuthRepository(settings.database_url))
    accounts = (
        ("advisor-demo", "advisor.demo", "Tư vấn viên Demo", UserRole.ADVISOR, "DEMO_ADVISOR_PASSWORD"),
        ("manager-demo", "manager.demo", "Quản lý Demo", UserRole.MANAGER, "DEMO_MANAGER_PASSWORD"),
    )
    for user_id, username, display_name, role, password_variable in accounts:
        await service.seed_user(
            user_id=user_id,
            username=username,
            display_name=display_name,
            role=role,
            password=required_password(password_variable),
        )
        print(f"Seeded {role.value} account: {username}")


if __name__ == "__main__":
    asyncio.run(seed())
