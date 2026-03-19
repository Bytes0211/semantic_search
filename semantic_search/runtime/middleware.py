"""JWT authentication middleware for access-control Phase B.

Extracts and validates ``Authorization: Bearer <token>`` headers, decodes the
JWT using a JWKS endpoint, and attaches the caller's roles to
``request.state.roles`` for downstream consumption by the search endpoint.

Routes listed in ``bypass_paths`` (health/readiness probes, config) are
exempt from authentication.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set

import anyio
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOGGER = logging.getLogger(__name__)

# Paths that never require authentication.
DEFAULT_BYPASS_PATHS: Set[str] = {"/healthz", "/readyz", "/v1/config", "/docs", "/openapi.json"}


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces JWT authentication.

    On each request (except bypass paths):
    1. Extracts the ``Authorization: Bearer <token>`` header.
    2. Decodes and validates the JWT using the configured JWKS endpoint.
    3. Optionally validates ``iss`` and ``aud`` claims.
    4. Extracts roles from the configured claim key.
    5. Attaches roles to ``request.state.roles``.

    On failure, returns a 401 JSON response.

    Args:
        app: The ASGI application.
        jwks_url: JWKS endpoint URL for signature validation.
        issuer: Expected ``iss`` claim (``None`` to skip validation).
        audience: Expected ``aud`` claim (``None`` to skip validation).
        roles_claim: JWT claim key holding the caller's role list.
        bypass_paths: Paths exempt from authentication.
    """

    def __init__(
        self,
        app: object,
        *,
        jwks_url: str,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        roles_claim: str = "roles",
        bypass_paths: Optional[Set[str]] = None,
    ) -> None:
        """Initialise the JWT middleware.

        Args:
            app: The ASGI application.
            jwks_url: JWKS endpoint URL for public key retrieval.
            issuer: Expected JWT issuer claim.
            audience: Expected JWT audience claim.
            roles_claim: Claim key containing the role list.
            bypass_paths: Routes that skip authentication.
        """
        import jwt as _jwt  # noqa: PLC0415

        super().__init__(app)
        self._issuer = issuer
        self._audience = audience
        self._roles_claim = roles_claim
        self._bypass_paths = bypass_paths or DEFAULT_BYPASS_PATHS
        self._jwk_client = _jwt.PyJWKClient(jwks_url, cache_keys=True)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, enforcing JWT auth on non-bypass paths.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            The response from the downstream handler, or a 401 JSON
            response on authentication failure.
        """
        # Skip auth for bypass paths and preflight OPTIONS requests.
        if request.url.path in self._bypass_paths or request.method == "OPTIONS":
            return await call_next(request)

        # Also bypass paths that start with /data or /assets (static files).
        if request.url.path.startswith(("/data/", "/assets/")):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header."},
                headers={"WWW-Authenticate": 'Bearer realm="semantic-search"'},
            )

        token = auth_header[7:]  # strip "Bearer "
        roles = await anyio.to_thread.run_sync(self._decode_token, token)
        if roles is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token."},
                headers={"WWW-Authenticate": 'Bearer realm="semantic-search", error="invalid_token"'},
            )

        request.state.roles = roles
        return await call_next(request)

    def _decode_token(self, token: str) -> Optional[List[str]]:
        """Decode and validate a JWT, returning the roles claim.

        Args:
            token: Raw JWT string (without the ``Bearer`` prefix).

        Returns:
            List of role strings from the configured claim, or ``None``
            on any validation failure.
        """
        try:
            import jwt  # noqa: PLC0415

            signing_key = self._jwk_client.get_signing_key_from_jwt(token)

            decode_options: dict = {}
            kwargs: dict = {
                "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            }
            if self._issuer:
                kwargs["issuer"] = self._issuer
            if self._audience:
                kwargs["audience"] = self._audience
            else:
                decode_options["verify_aud"] = False

            payload = jwt.decode(
                token,
                signing_key.key,  # type: ignore[union-attr]
                options=decode_options,
                **kwargs,
            )

            raw_roles = payload.get(self._roles_claim)
            if raw_roles is None:
                LOGGER.warning(
                    "JWT payload missing configured roles claim '%s' — "
                    "treating caller as having no roles.",
                    self._roles_claim,
                )
                return []

            if isinstance(raw_roles, list):
                return [str(r) for r in raw_roles]
            if isinstance(raw_roles, str):
                return [raw_roles]
            return []

        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "JWT validation failed: %s", type(exc).__name__,
            )
            LOGGER.debug("JWT decode detail: %s", exc)
            return None
