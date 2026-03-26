"""Pydantic schemas for authentication endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MeResponse(BaseModel):
    """Response for GET /auth/me."""

    model_config = ConfigDict(from_attributes=True)

    github_login: str
    github_id: int
    roles: list[str]
    scoped_orgs: list[str]
    scoped_repos: list[str]
    scope_type: str
    session_expires_at: str


class LogoutResponse(BaseModel):
    status: str = "ok"


class GitHubOAuthInitResponse(BaseModel):
    """Not returned directly; handler issues a redirect."""

    authorization_url: str


class SAMLMetadataResponse(BaseModel):
    """Wrapper for SAML SP metadata XML (returned as text/xml)."""

    xml: str
