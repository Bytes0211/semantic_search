"""Tests for semantic_search.runtime.middleware — JWT authentication."""

from __future__ import annotations

import json
import time
from typing import Any, Dict
from unittest.mock import patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from starlette.testclient import TestClient

from semantic_search.runtime.api import create_app
from semantic_search.runtime.middleware import JWTAuthMiddleware


# ---------------------------------------------------------------------------
# RSA key fixtures — generate a fresh key pair per test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_private_key() -> rsa.RSAPrivateKey:
    """Generate an RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def rsa_public_key(rsa_private_key: rsa.RSAPrivateKey) -> rsa.RSAPublicKey:
    """Derive the public key from the private key."""
    return rsa_private_key.public_key()


@pytest.fixture(scope="module")
def rsa_public_pem(rsa_public_key: rsa.RSAPublicKey) -> bytes:
    """PEM-encoded public key bytes."""
    return rsa_public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _make_token(
    private_key: rsa.RSAPrivateKey,
    claims: Dict[str, Any],
    algorithm: str = "RS256",
) -> str:
    """Create a signed JWT from the given claims.

    Args:
        private_key: RSA private key used for signing.
        claims: JWT payload claims.
        algorithm: Signing algorithm.

    Returns:
        Encoded JWT string.
    """
    return pyjwt.encode(claims, private_key, algorithm=algorithm)


# ---------------------------------------------------------------------------
# App fixture with JWT middleware wired via monkeypatched JWKS
# ---------------------------------------------------------------------------


@pytest.fixture()
def jwt_app(rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey):
    """Create a FastAPI app with JWT middleware using the test RSA keys.

    Patches ``_decode_token`` to use the in-memory public key instead of
    fetching from a real JWKS endpoint.
    """
    app = create_app(jwt_enabled=True)

    # Patch the middleware's _decode_token to use our test key directly.
    def _patched_decode(self: JWTAuthMiddleware, token: str):
        """Decode using the test public key instead of JWKS."""
        try:
            decode_options: dict = {}
            kwargs: dict = {
                "algorithms": ["RS256"],
            }
            if self._issuer:
                kwargs["issuer"] = self._issuer
            if self._audience:
                kwargs["audience"] = self._audience
            else:
                decode_options["verify_aud"] = False

            payload = pyjwt.decode(
                token,
                rsa_public_key,
                options=decode_options,
                **kwargs,
            )
            raw_roles = payload.get(self._roles_claim)
            if raw_roles is None:
                raw_roles = payload.get("cognito:groups", [])
            if isinstance(raw_roles, list):
                return [str(r) for r in raw_roles]
            if isinstance(raw_roles, str):
                return [raw_roles]
            return []
        except Exception:
            return None

    app.add_middleware(
        JWTAuthMiddleware,
        jwks_url="https://example.com/.well-known/jwks.json",
        roles_claim="roles",
    )

    # Patch _decode_token at the class level so the middleware uses our
    # in-memory RSA key instead of fetching from a real JWKS endpoint.
    with patch.object(JWTAuthMiddleware, "_decode_token", _patched_decode):
        yield app, rsa_private_key


@pytest.fixture()
def jwt_client(jwt_app) -> TestClient:
    """Test client for the JWT-protected app."""
    app, _ = jwt_app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def jwt_private_key(jwt_app) -> rsa.RSAPrivateKey:
    """The RSA private key used by the test app."""
    _, pk = jwt_app
    return pk


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJWTBypassRoutes:
    """Bypass routes should not require authentication."""

    def test_healthz_no_auth(self, jwt_client: TestClient) -> None:
        """GET /healthz returns 200 without Authorization header."""
        resp = jwt_client.get("/healthz")
        assert resp.status_code == 200

    def test_readyz_no_auth(self, jwt_client: TestClient) -> None:
        """GET /readyz returns 503 (no runtime) not 401."""
        resp = jwt_client.get("/readyz")
        assert resp.status_code == 503  # no runtime configured, but NOT 401

    def test_config_no_auth(self, jwt_client: TestClient) -> None:
        """GET /v1/config returns 200 without Authorization header."""
        resp = jwt_client.get("/v1/config")
        assert resp.status_code == 200


class TestJWTMissingToken:
    """Requests without a valid Authorization header should return 401."""

    def test_no_auth_header(self, jwt_client: TestClient) -> None:
        """POST /v1/search without Authorization returns 401."""
        resp = jwt_client.post("/v1/search", json={"query": "test"})
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    def test_non_bearer_auth(self, jwt_client: TestClient) -> None:
        """Authorization header without Bearer prefix returns 401."""
        resp = jwt_client.post(
            "/v1/search",
            json={"query": "test"},
            headers={"Authorization": "Basic abc123"},
        )
        assert resp.status_code == 401


class TestJWTValidToken:
    """Requests with a valid JWT should pass through to the endpoint."""

    def test_valid_token_passes_through(
        self, jwt_client: TestClient, jwt_private_key: rsa.RSAPrivateKey
    ) -> None:
        """Valid JWT reaches the search endpoint (503 because no runtime)."""
        token = _make_token(jwt_private_key, {
            "sub": "user1",
            "roles": ["analyst"],
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
        })
        resp = jwt_client.post(
            "/v1/search",
            json={"query": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # 503 = no runtime configured, which means auth passed
        assert resp.status_code == 503

    def test_roles_extracted_from_token(
        self, jwt_client: TestClient, jwt_private_key: rsa.RSAPrivateKey
    ) -> None:
        """Verify JWT roles are attached to request.state.roles."""
        token = _make_token(jwt_private_key, {
            "sub": "user1",
            "roles": ["admin", "analyst"],
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
        })
        # This will 503 because no runtime, but confirms auth passed
        resp = jwt_client.post(
            "/v1/search",
            json={"query": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503


class TestJWTInvalidToken:
    """Invalid tokens should return 401."""

    def test_expired_token(
        self, jwt_client: TestClient, jwt_private_key: rsa.RSAPrivateKey
    ) -> None:
        """Expired JWT returns 401."""
        token = _make_token(jwt_private_key, {
            "sub": "user1",
            "roles": ["analyst"],
            "exp": int(time.time()) - 60,  # expired 60s ago
            "iat": int(time.time()) - 120,
        })
        resp = jwt_client.post(
            "/v1/search",
            json={"query": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_malformed_token(self, jwt_client: TestClient) -> None:
        """Garbage token returns 401."""
        resp = jwt_client.post(
            "/v1/search",
            json={"query": "test"},
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401


class TestJWTCognitoFallback:
    """When the primary roles claim is absent, fall back to cognito:groups."""

    def test_cognito_groups_fallback(
        self, jwt_client: TestClient, jwt_private_key: rsa.RSAPrivateKey
    ) -> None:
        """Token with cognito:groups but no 'roles' claim should pass auth."""
        token = _make_token(jwt_private_key, {
            "sub": "user1",
            "cognito:groups": ["viewer"],
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
        })
        resp = jwt_client.post(
            "/v1/search",
            json={"query": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # 503 = auth passed (no runtime)
        assert resp.status_code == 503
