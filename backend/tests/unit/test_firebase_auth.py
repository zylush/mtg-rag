import pytest

from app.api.auth import FirebaseTokenVerifier, TokenVerificationError


@pytest.mark.asyncio
async def test_firebase_verifier_extracts_uid_and_email() -> None:
    verifier = FirebaseTokenVerifier(
        verify_id_token=lambda token, check_revoked: {
            "uid": "firebase-user-1",
            "email": "user@example.com",
        }
    )

    identity = await verifier.verify("valid")

    assert identity.firebase_uid == "firebase-user-1"
    assert identity.email == "user@example.com"


@pytest.mark.asyncio
async def test_firebase_verifier_maps_provider_failures_to_safe_error() -> None:
    def fail(token: str, check_revoked: bool):  # type: ignore[no-untyped-def]
        raise RuntimeError("provider detail that must not leak")

    verifier = FirebaseTokenVerifier(verify_id_token=fail)

    with pytest.raises(TokenVerificationError, match="invalid authentication token"):
        await verifier.verify("bad")

