"""A fake Google for tests: issues codes, enforces PKCE at /token, signs RS256 ID tokens,
and serves /jwks. Plugged into the real OIDCClient through an httpx MockTransport."""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx2 as httpx
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = "https://idp.test"
CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"
REDIRECT_URI = "http://localhost:8080/auth/callback"


@dataclass
class _Grant:
    claims: dict[str, Any]
    code_challenge: str
    redirect_uri: str


@dataclass
class FakeIdP:
    key: RSAKey = field(
        default_factory=lambda: RSAKey.generate_key(2048, parameters={"kid": "k1", "use": "sig"})
    )
    grants: dict[str, _Grant] = field(default_factory=dict)
    token_requests: int = 0
    issued_tokens: list[str] = field(default_factory=list)  # every access/ID token handed out

    def approve(
        self,
        authorize_url: str,
        *,
        email: str,
        email_verified: bool = True,
        hd: str | None = "buenavidatrading.com",
        name: str | None = "Test User",
        **overrides: Any,
    ) -> tuple[str, str]:
        """Simulate the user consenting at Google. Returns (code, state)."""
        q = {k: v[0] for k, v in parse_qs(urlparse(authorize_url).query).items()}
        assert q["code_challenge_method"] == "S256"
        assert q["response_type"] == "code"
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": q["client_id"],
            "sub": "sub-" + email,
            "email": email,
            "email_verified": email_verified,
            "name": name,
            "nonce": q["nonce"],
            "iat": now,
            "exp": now + 3600,
        }
        if hd is not None:
            claims["hd"] = hd
        claims.update(overrides)
        code = secrets.token_urlsafe(16)
        self.grants[code] = _Grant(claims, q["code_challenge"], q["redirect_uri"])
        return code, q["state"]

    def sign(self, claims: dict[str, Any], key: RSAKey | None = None) -> str:
        k = key or self.key
        return jwt.encode({"alg": "RS256", "kid": k.kid}, claims, k)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if request.url.path == "/token":
            self.token_requests += 1
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            grant = self.grants.pop(form.get("code", ""), None)
            if (
                grant is None
                or form.get("client_id") != CLIENT_ID
                or form.get("client_secret") != CLIENT_SECRET
                or form.get("redirect_uri") != grant.redirect_uri
                or form.get("grant_type") != "authorization_code"
                or _s256(form.get("code_verifier", "")) != grant.code_challenge
            ):
                return httpx.Response(400, json={"error": "invalid_grant"})
            access_token = secrets.token_urlsafe(24)
            id_token = str(grant.claims.pop("__raw_id_token", None) or self.sign(grant.claims))
            body = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "id_token": id_token,
            }
            self.issued_tokens += [access_token, id_token]
            return httpx.Response(
                200, content=json.dumps(body), headers={"content-type": "application/json"}
            )
        return httpx.Response(404)


def _s256(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
