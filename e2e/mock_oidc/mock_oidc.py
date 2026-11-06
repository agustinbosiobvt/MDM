"""Mock Google OIDC provider for the e2e suite ONLY. Never deployed.

Behaves like Google where it matters to the API: Authorization Code + PKCE (S256
enforced), RS256-signed ID tokens with iss/aud/exp/iat/nonce/hd/email_verified,
a JWKS endpoint, single-use codes and client authentication.

The "consent screen" is a tiny form where the test types the Google account email.
"""

import base64
import hashlib
import html
import os
import secrets
import time
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = os.environ["MOCK_ISSUER"]
CLIENT_ID = os.environ["MOCK_CLIENT_ID"]
CLIENT_SECRET = os.environ["MOCK_CLIENT_SECRET"]
REDIRECT_URI = os.environ["MOCK_REDIRECT_URI"]

KEY = RSAKey.generate_key(2048, parameters={"kid": "mock-1", "use": "sig", "alg": "RS256"})
CODES: dict[str, dict[str, Any]] = {}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@app.get("/authorize", response_class=HTMLResponse)
def authorize(request: Request) -> str:
    q = request.query_params
    if q.get("client_id") != CLIENT_ID or q.get("redirect_uri") != REDIRECT_URI:
        raise HTTPException(400, "invalid client or redirect_uri")
    if q.get("response_type") != "code" or q.get("code_challenge_method") != "S256":
        raise HTTPException(400, "code flow with PKCE S256 required")
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(q.get(k, ""))}">'
        for k in ("state", "nonce", "code_challenge", "redirect_uri")
    )
    return f"""<!doctype html><html><head><title>Mock Google sign-in</title></head>
<body><h1>Mock Google sign-in</h1>
<form method="post" action="/approve">{hidden}
  <label>Google account email <input name="email" type="email" required></label>
  <label><input name="email_verified" type="checkbox" value="true" checked> Email verified</label>
  <label>Hosted domain (hd) <input name="hd" placeholder="derived from the email"></label>
  <button type="submit">Continue</button>
  <button type="submit" name="cancel" value="1" formnovalidate>Cancel</button>
</form></body></html>"""


@app.post("/approve")
def approve(
    state: Annotated[str, Form()],
    nonce: Annotated[str, Form()],
    code_challenge: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
    email_verified: Annotated[str, Form()] = "false",
    hd: Annotated[str, Form()] = "",
    cancel: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if cancel:
        return RedirectResponse(f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}", 303)
    email = email.strip().lower()
    domain = email.split("@")[-1]
    # Like Google: consumer accounts (gmail.com) have no hd claim.
    hd_claim = hd.strip() or (None if domain == "gmail.com" else domain)
    code = secrets.token_urlsafe(24)
    CODES[code] = {
        "challenge": code_challenge,
        "redirect_uri": redirect_uri,
        "expires": time.time() + 120,
        "claims": {
            "email": email,
            "email_verified": email_verified == "true",
            "name": email.split("@")[0].replace(".", " ").title(),
            "nonce": nonce,
            **({"hd": hd_claim} if hd_claim else {}),
        },
    }
    return RedirectResponse(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}", 303)


@app.post("/token")
def token(
    grant_type: Annotated[str, Form()],
    code: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    code_verifier: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    client_secret: Annotated[str, Form()],
) -> JSONResponse:
    grant = CODES.pop(code, None)  # single use
    if (
        grant is None
        or grant["expires"] < time.time()
        or grant_type != "authorization_code"
        or client_id != CLIENT_ID
        or not secrets.compare_digest(client_secret, CLIENT_SECRET)
        or redirect_uri != grant["redirect_uri"]
        or _s256(code_verifier) != grant["challenge"]
    ):
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "mock-" + hashlib.sha256(grant["claims"]["email"].encode()).hexdigest()[:16],
        "iat": now,
        "exp": now + 3600,
        **grant["claims"],
    }
    id_token = jwt.encode({"alg": "RS256", "kid": KEY.kid}, claims, KEY)
    return JSONResponse(
        {"access_token": secrets.token_urlsafe(16), "token_type": "Bearer", "expires_in": 3600, "id_token": id_token}
    )


@app.get("/jwks")
def jwks() -> dict[str, Any]:
    return {"keys": [KEY.as_dict(private=False)]}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
