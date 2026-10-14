"""J-Novel Club sign-in, and the token every authenticated call carries.

J-Novel Club publishes no API documentation. The contract here was read from
its own web app (labs.j-novel.club/app/v2) and observed live: sign-in returns
a session whose `id` is a bearer token, and a call made with a token that has
lapsed answers 401 or 410.

A token comes from one of two places. Credentials in .env sign in and renew
forever. A token saved from Settings cannot be renewed - the password is never
stored - so when it lapses the only honest answer is to ask for a new sign-in.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.sources.base import NotConfigured

API = "https://labs.j-novel.club/app/v2"
DEFAULT_TTL_SECONDS = 1_209_600  # 14 days, what J-Novel Club's own web app asks for
RENEW_AHEAD = timedelta(hours=1)

log = logging.getLogger(__name__)


class JncAuthError(RuntimeError):
    """Sign-in refused, with a reason a person can act on."""


@dataclass(frozen=True)
class JncSession:
    token: str
    expires_at: datetime


async def login(client, login_name: str, password: str, *, ttl: int = DEFAULT_TTL_SECONDS,
                now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> JncSession:
    response = await client.post(
        f"{API}/auth/login",
        params={"format": "json"},
        json={"login": login_name, "password": password, "slim": True, "ttl": ttl},
    )
    if response.status_code == 401:
        raise JncAuthError("wrong email or password")
    if response.status_code == 429:
        raise JncAuthError("too many sign-in attempts, try again later")
    if response.status_code >= 400:
        raise JncAuthError(f"J-Novel Club refused the sign-in ({response.status_code})")
    body = response.json()
    # The ttl in the answer is what the server granted, which need not be what
    # was asked for, so it is the one to trust.
    granted = _seconds(body.get("ttl"), ttl)
    return JncSession(token=body["id"], expires_at=now() + timedelta(seconds=granted))


def _seconds(value, fallback: int) -> int:
    """A session ttl in whichever shape it arrives.

    The session is a protobuf message served as JSON, and protobuf's JSON form
    of a Duration is a string like "1209600s"; a plain number is accepted too.
    Anything else falls back to what was asked for.
    """
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.removesuffix("s")))
        except ValueError:
            pass
    return fallback


async def logout(client, token: str) -> None:
    try:
        await client.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {token}"})
    except Exception as exc:  # noqa: BLE001 - signing out locally must not depend on it
        log.warning("J-Novel Club logout failed: %s", exc)


StoredLoader = Callable[[], Awaitable[JncSession | None]]


class TokenKeeper:
    """One valid token, renewed once however many callers ask at the same time.

    Either credentials (from .env) or a loader of the session saved from
    Settings. The loader is asked each time a token is needed rather than once
    at construction: the workers build their registry at boot, and a sign-in
    made afterwards in the web interface would otherwise never reach them.
    """

    def __init__(
        self,
        client,
        *,
        login_name: str = "",
        password: str = "",
        load_stored: StoredLoader | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._login = login_name
        self._password = password
        self._load_stored = load_stored
        self._now = now
        self._session: JncSession | None = None
        self._rejected: str | None = None
        self._lock = asyncio.Lock()

    @property
    def via(self) -> str:
        if self._login and self._password:
            return "env"
        return "settings" if self._load_stored is not None else "none"

    async def token(self) -> str:
        async with self._lock:
            if self.via == "env":
                if self._session is None or self._session.expires_at - RENEW_AHEAD <= self._now():
                    self._session = await login(
                        self._client, self._login, self._password, now=self._now
                    )
                return self._session.token
            if self.via == "settings":
                stored = await self._load_stored()
                if stored is None:
                    raise NotConfigured("J-Novel Club is not signed in")
                if stored.expires_at <= self._now() or stored.token == self._rejected:
                    raise NotConfigured("J-Novel Club sign-in expired; sign in again in Settings")
                return stored.token
            raise NotConfigured("J-Novel Club is not signed in")

    async def invalidate(self, token: str) -> None:
        """The server refused this token. Credentials sign in again on the next
        call; a stored token is remembered as dead until a new one is saved."""
        async with self._lock:
            if self.via == "env":
                if self._session is not None and self._session.token == token:
                    self._session = None
            else:
                self._rejected = token
