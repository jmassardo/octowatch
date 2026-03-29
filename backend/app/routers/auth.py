"""Auth router: GitHub OAuth and SAML 2.0 authentication endpoints."""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, get_valkey
from app.schemas.auth import LogoutResponse, MeResponse
from app.services.auth_service import (
    build_github_authorize_url,
    clear_auth_cookies,
    create_jwt,
    exchange_github_code,
    fetch_github_orgs_and_teams,
    fetch_github_user,
    get_saml_auth,
    revoke_session,
    set_auth_cookies,
    store_session,
)
from app.services.rbac_service import get_user_scope, resolve_roles

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github/login")
async def github_login(request: Request) -> RedirectResponse:
    """Initiate GitHub OAuth flow. Redirects user to GitHub authorization page."""
    state = secrets.token_urlsafe(32)
    url = build_github_authorize_url(state=state)
    response = RedirectResponse(url=url)
    response.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        samesite="lax",
        max_age=600,
        secure=True,
    )
    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> Response:
    """Handle GitHub OAuth callback. Exchanges code for access token and issues JWT."""
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    token_data = await exchange_github_code(code=code)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to exchange code"
        )
    gh_at = token_data.get("access_token", "")

    github_user = await fetch_github_user(gh_at)
    if not github_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to fetch user")

    gh_login = github_user["login"]
    gh_id = github_user.get("id", 0)

    await fetch_github_orgs_and_teams(gh_at)
    roles = await resolve_roles(db, gh_login)
    scope = await get_user_scope(db, gh_login, roles)
    scope_type = "global" if scope.is_global else "scoped"

    jti = str(uuid.uuid4())
    jwt_token = create_jwt(github_login=gh_login, github_id=gh_id, jti=jti)
    csrf_token = secrets.token_urlsafe(32)

    await store_session(
        valkey=valkey,
        jti=jti,
        github_login=gh_login,
        github_id=gh_id,
        roles=roles,
        scoped_orgs=scope.scoped_orgs,
        scoped_repos=scope.scoped_repos,
        scope_type=scope_type,
    )

    # Return a 200 HTML page that does a client-side redirect.
    # A 302 RedirectResponse causes browsers to drop SameSite=Strict cookies
    # because the incoming request is a cross-site redirect from github.com.
    # With a 200 response, the browser stores the cookies normally, then the
    # meta-refresh causes a same-site top-level navigation where cookies are sent.
    html = (
        "<!doctype html><html><head>"
        '<meta http-equiv="refresh" content="0;url=/">'
        "</head><body>Authenticated, redirecting&hellip;</body></html>"
    )
    final_response = HTMLResponse(content=html, status_code=200)
    set_auth_cookies(final_response, jwt_token, csrf_token)
    final_response.delete_cookie("oauth_state")
    return final_response


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Return the currently authenticated user's profile and roles."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    return MeResponse(
        github_login=current_user.github_login,
        github_id=current_user.github_id,
        roles=current_user.roles,
        scoped_orgs=scope.scoped_orgs,
        scoped_repos=scope.scoped_repos,
        scope_type=scope.scope_type if not scope.is_global else "global",
        session_expires_at=current_user.session_expires_at,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
    valkey: Redis = Depends(get_valkey),
) -> LogoutResponse:
    """Revoke the current session and clear auth cookies."""
    await revoke_session(valkey, current_user.jti)
    clear_auth_cookies(response)
    return LogoutResponse(status="logged_out")


# ─── SAML 2.0 endpoints ────────────────────────────────────────────────────────


@router.get("/saml/login")
async def saml_login(request: Request) -> RedirectResponse:
    """Initiate SAML SSO login. Redirects browser to the IdP."""
    auth = get_saml_auth(request)
    return RedirectResponse(url=auth.login())


@router.post("/saml/acs")
async def saml_acs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> Response:
    """SAML Assertion Consumer Service — processes SAML response from IdP."""
    auth = get_saml_auth(request)
    auth.process_response()
    errors = auth.get_errors()

    if errors or not auth.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"SAML authentication failed: {errors}",
        )

    attributes = auth.get_attributes()
    gh_login = attributes.get("github_login", [None])[0] or attributes.get("uid", [None])[0]
    if not gh_login:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SAML response missing github_login attribute",
        )

    roles = await resolve_roles(db, gh_login)
    scope = await get_user_scope(db, gh_login, roles)
    scope_type = "global" if scope.is_global else "scoped"

    jti = str(uuid.uuid4())
    jwt_token = create_jwt(github_login=gh_login, github_id=0, jti=jti)
    csrf_token = secrets.token_urlsafe(32)

    await store_session(
        valkey=valkey,
        jti=jti,
        github_login=gh_login,
        github_id=0,
        roles=roles,
        scoped_orgs=scope.scoped_orgs,
        scoped_repos=scope.scoped_repos,
        scope_type=scope_type,
    )

    final_response = Response(content='{"status":"authenticated"}', media_type="application/json")
    set_auth_cookies(final_response, jwt_token, csrf_token)
    return final_response


@router.get("/saml/metadata")
async def saml_metadata(request: Request) -> Response:
    """Return SAML SP metadata XML for IdP registration."""
    auth = get_saml_auth(request)
    metadata = auth.get_settings().get_sp_metadata()
    errors = auth.get_settings().validate_metadata(metadata)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SP metadata validation failed: {errors}",
        )
    return Response(content=metadata, media_type="application/xml")


# ─── Dev/test login (non-production only) ───────────────────────────────────


@router.post("/dev-login")
async def dev_login(
    request: Request,
    valkey: Redis = Depends(get_valkey),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Credential-based login for development/testing only.

    Disabled when ENVIRONMENT=production.  Accepts ``{"username": "...",
    "password": "..."}`` and returns auth cookies.  The username must match
    a known user in the RBAC tables; the password must equal the username
    (trivial check — security is irrelevant in dev/test).
    """
    from app.config import settings as cfg

    if cfg.ENVIRONMENT == "production":
        raise HTTPException(status_code=404)

    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    if not username or password != username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid dev credentials",
        )

    roles = await resolve_roles(db, username)
    if not roles:
        roles = ["viewer"]
    scope = await get_user_scope(db, username, roles)
    scope_type = "global" if scope.is_global else "scoped"

    jti = str(uuid.uuid4())
    jwt_token = create_jwt(github_login=username, github_id=0, jti=jti)
    csrf_token = secrets.token_urlsafe(32)

    await store_session(
        valkey=valkey,
        jti=jti,
        github_login=username,
        github_id=0,
        roles=roles,
        scoped_orgs=scope.scoped_orgs,
        scoped_repos=scope.scoped_repos,
        scope_type=scope_type,
    )

    response = Response(
        content='{"status":"authenticated"}',
        media_type="application/json",
    )
    set_auth_cookies(response, jwt_token, csrf_token)
    return response
