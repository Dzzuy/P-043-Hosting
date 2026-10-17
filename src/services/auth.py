"""Password verification and opaque session lifecycle for local authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.models.auth import AuthenticatedUser, StoredSession, StoredUser, UserRole

PBKDF2_ITERATIONS = 600_000


class InvalidCredentialsError(ValueError):
    """Username/password authentication failed without revealing which field."""


class AuthenticationRequiredError(PermissionError):
    """No active session maps to the supplied cookie."""


class AuthService:
    def __init__(
        self,
        repository,
        *,
        session_ttl: timedelta = timedelta(hours=8),
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if session_ttl.total_seconds() <= 0:
            raise ValueError("session_ttl must be positive")
        self._repository = repository
        self._session_ttl = session_ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    @property
    def session_ttl(self) -> timedelta:
        return self._session_ttl

    async def seed_user(
        self,
        *,
        user_id: str,
        username: str,
        display_name: str,
        role: UserRole,
        password: str,
    ) -> AuthenticatedUser:
        normalized_username = username.strip().casefold()
        if not all(value.strip() for value in (user_id, normalized_username, display_name)):
            raise ValueError("user identity fields must not be blank")
        if len(password) < 12:
            raise ValueError("demo passwords must contain at least 12 characters")
        salt = secrets.token_bytes(16)
        password_hash = self._derive_password(password, salt, PBKDF2_ITERATIONS)
        user = StoredUser(
            user_id=user_id.strip(),
            username=normalized_username,
            display_name=display_name.strip(),
            role=role,
            password_hash=base64.urlsafe_b64encode(password_hash).decode("ascii"),
            password_salt=base64.urlsafe_b64encode(salt).decode("ascii"),
            password_iterations=PBKDF2_ITERATIONS,
        )
        await self._repository.upsert_user(user)
        return self._public_user(user)

    async def create_advisor(self, *, username: str, display_name: str, password: str) -> AuthenticatedUser:
        normalized_username = username.strip().casefold()
        normalized_name = display_name.strip()
        if not normalized_username or not normalized_name:
            raise ValueError("user identity fields must not be blank")
        if len(password) < 12:
            raise ValueError("password must contain at least 12 characters")
        salt = secrets.token_bytes(16)
        user = StoredUser(
            user_id=str(uuid4()),
            username=normalized_username,
            display_name=normalized_name,
            role=UserRole.ADVISOR,
            password_hash=base64.urlsafe_b64encode(self._derive_password(password, salt, PBKDF2_ITERATIONS)).decode(
                "ascii"
            ),
            password_salt=base64.urlsafe_b64encode(salt).decode("ascii"),
            password_iterations=PBKDF2_ITERATIONS,
        )
        await self._repository.create_user(user, require_password_change=True)
        return self._public_user(user, must_change_password=True)

    async def bootstrap_manager(
        self,
        *,
        username: str | None,
        display_name: str | None,
        password: str | None,
    ) -> bool:
        """Create the first manager once; never replace an existing account."""
        if await self._repository.manager_exists():
            return False
        if not username or not display_name or not password:
            raise RuntimeError("Set BOOTSTRAP_MANAGER_USERNAME, DISPLAY_NAME, and PASSWORD for the first deploy")
        if not username.strip() or not display_name.strip():
            raise ValueError("Bootstrap manager identity fields must not be blank")
        if len(password) < 16:
            raise ValueError("Bootstrap manager password must contain at least 16 characters")
        salt = secrets.token_bytes(16)
        user = StoredUser(
            user_id=str(uuid4()),
            username=username.strip().casefold(),
            display_name=display_name.strip(),
            role=UserRole.MANAGER,
            password_hash=base64.urlsafe_b64encode(self._derive_password(password, salt, PBKDF2_ITERATIONS)).decode(
                "ascii"
            ),
            password_salt=base64.urlsafe_b64encode(salt).decode("ascii"),
            password_iterations=PBKDF2_ITERATIONS,
        )
        await self._repository.create_user(user, require_password_change=True)
        return True

    async def active_advisors(self) -> list[AuthenticatedUser]:
        return await self._repository.active_advisors()

    async def active_advisor(self, user_id: str) -> AuthenticatedUser | None:
        return await self._repository.active_advisor(user_id)

    async def login(self, username: str, password: str) -> tuple[str, AuthenticatedUser]:
        user = await self._repository.user_by_username(username.strip().casefold())
        if user is None or not user.active or not self._password_matches(user, password):
            raise InvalidCredentialsError("invalid username or password")
        now = self._clock()
        token = self._token_factory()
        await self._repository.create_session(
            StoredSession(
                token_hash=self.hash_token(token),
                user_id=user.user_id,
                created_at=now,
                expires_at=now + self._session_ttl,
            )
        )
        return token, self._public_user(
            user,
            must_change_password=await self._repository.requires_password_change(user.user_id),
        )

    async def current_user(self, token: str | None) -> AuthenticatedUser:
        if not token:
            raise AuthenticationRequiredError("authentication required")
        user = await self._repository.user_for_session(self.hash_token(token), self._clock())
        if user is None:
            raise AuthenticationRequiredError("authentication required")
        return user

    async def change_password(self, user: AuthenticatedUser, current_password: str, new_password: str) -> None:
        if not 12 <= len(new_password) <= 1024:
            raise ValueError("New password must contain 12 to 1024 characters")
        stored = await self._repository.user_by_username(user.username)
        if stored is None or not self._password_matches(stored, current_password):
            raise InvalidCredentialsError("invalid current password")
        if hmac.compare_digest(current_password, new_password):
            raise ValueError("New password must differ from current password")
        salt = secrets.token_bytes(16)
        password_hash = base64.urlsafe_b64encode(self._derive_password(new_password, salt, PBKDF2_ITERATIONS)).decode(
            "ascii"
        )
        await self._repository.update_password(
            user.user_id,
            password_hash,
            base64.urlsafe_b64encode(salt).decode("ascii"),
            PBKDF2_ITERATIONS,
        )

    async def logout(self, token: str | None) -> None:
        if token:
            await self._repository.delete_session(self.hash_token(token))

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _derive_password(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)

    def _password_matches(self, user: StoredUser, password: str) -> bool:
        salt = base64.urlsafe_b64decode(user.password_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(user.password_hash.encode("ascii"))
        actual = self._derive_password(password, salt, user.password_iterations)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _public_user(user: StoredUser, *, must_change_password: bool = False) -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            must_change_password=must_change_password,
        )
