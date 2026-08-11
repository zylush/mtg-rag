from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from firebase_admin import auth as firebase_auth


class TokenVerificationError(ValueError):
    """Safe authentication failure exposed at the HTTP boundary."""


@dataclass(frozen=True)
class AuthenticatedUser:
    firebase_uid: str
    email: str | None


class FirebaseTokenVerifier:
    def __init__(
        self,
        verify_id_token: Callable[..., Mapping[str, Any]] = firebase_auth.verify_id_token,
    ) -> None:
        self._verify_id_token = verify_id_token

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            claims = await asyncio.to_thread(
                self._verify_id_token, token, check_revoked=True
            )
            uid = claims.get("uid") or claims.get("sub")
            if not isinstance(uid, str) or not uid:
                raise ValueError("missing uid")
            email_claim = claims.get("email")
            email = email_claim if isinstance(email_claim, str) else None
            return AuthenticatedUser(firebase_uid=uid, email=email)
        except Exception as exc:
            raise TokenVerificationError("invalid authentication token") from exc

