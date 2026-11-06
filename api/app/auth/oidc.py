"""Google OIDC, server side: Authorization Code flow with PKCE.

The browser only ever sees the authorization redirect. The code exchange and
the ID-token validation happen here, and no token leaves the API.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx2 as httpx
from authlib.integrations.httpx_client import OAuth2Client
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from app.config import Settings

HTTP_TIMEOUT = 10.0
JWKS_TTL_SECONDS = 3600
JWKS_MIN_REFRESH_SECONDS = 60
CLOCK_LEEWAY_SECONDS = 60


class OIDCError(Exception):
    """Login failed. `reason` is a short code, safe to log and audit."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    name: str | None


class OIDCClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport
        self._jwks: KeySet | None = None
        self._jwks_fetched_at = 0.0
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(s.google_client_id and s.google_client_secret.get_secret_value())

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        s = self.settings
        params = {
            "client_id": s.google_client_id,
            "redirect_uri": s.oidc_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": create_s256_code_challenge(code_verifier),
            "code_challenge_method": "S256",
            "hd": s.allowed_hosted_domain,  # UI hint only; enforced on the token below
            "prompt": "select_account",
        }
        return f"{s.oidc_authorization_endpoint}?{urlencode(params)}"

    def exchange_code(self, *, code: str, code_verifier: str) -> str:
        s = self.settings
        client = OAuth2Client(
            client_id=s.google_client_id,
            client_secret=s.google_client_secret.get_secret_value(),
            redirect_uri=s.oidc_redirect_uri,
            # A method name, not a secret.
            token_endpoint_auth_method="client_secret_post",  # noqa: S106  # nosec B106
            timeout=HTTP_TIMEOUT,
            transport=self._transport,
        )
        try:
            with client:
                token: dict[str, Any] = client.fetch_token(
                    s.oidc_token_endpoint, code=code, code_verifier=code_verifier
                )
        except Exception as exc:
            raise OIDCError("token_exchange_failed") from exc
        id_token = token.get("id_token")
        if not isinstance(id_token, str):
            raise OIDCError("no_id_token")
        return id_token

    def verify_id_token(self, id_token: str, *, nonce: str) -> Identity:
        s = self.settings
        try:
            decoded = self._decode(id_token)
            JWTClaimsRegistry(
                leeway=CLOCK_LEEWAY_SECONDS,
                iss={"essential": True, "values": sorted(s.accepted_issuers)},
                aud={"essential": True, "value": s.google_client_id},
                exp={"essential": True},
                iat={"essential": True},
                sub={"essential": True},
                nonce={"essential": True, "value": nonce},
            ).validate(decoded.claims)
        except JoseError as exc:
            raise OIDCError("invalid_id_token") from exc

        claims = decoded.claims
        if claims.get("email_verified") is not True:
            raise OIDCError("email_not_verified")
        email = str(claims.get("email", "")).strip().lower()
        if claims.get("hd") != s.allowed_hosted_domain or not email.endswith(
            "@" + s.allowed_hosted_domain
        ):
            raise OIDCError("wrong_domain")
        name = claims.get("name")
        return Identity(
            subject=str(claims["sub"]), email=email, name=name if isinstance(name, str) else None
        )

    # --- JWKS -------------------------------------------------------------------
    def _decode(self, id_token: str) -> jwt.Token:
        try:
            return jwt.decode(id_token, self._keyset(), algorithms=["RS256"])
        except JoseError:
            # Google rotates keys: on failure, refetch once (rate-limited) and retry.
            if not self._refresh_allowed():
                raise
            return jwt.decode(id_token, self._keyset(force=True), algorithms=["RS256"])

    def _refresh_allowed(self) -> bool:
        return time.monotonic() - self._jwks_fetched_at > JWKS_MIN_REFRESH_SECONDS

    def _keyset(self, *, force: bool = False) -> KeySet:
        with self._lock:
            stale = time.monotonic() - self._jwks_fetched_at > JWKS_TTL_SECONDS
            if self._jwks is None or stale or force:
                try:
                    with httpx.Client(timeout=HTTP_TIMEOUT, transport=self._transport) as http:
                        resp = http.get(self.settings.oidc_jwks_uri)
                        resp.raise_for_status()
                        self._jwks = KeySet.import_key_set(resp.json())
                except (httpx.HTTPError, ValueError, JoseError) as exc:
                    raise OIDCError("jwks_unavailable") from exc
                self._jwks_fetched_at = time.monotonic()
            return self._jwks
