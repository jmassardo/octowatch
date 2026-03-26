"""IdP actor enrichment service: Okta / Entra ID (MSAL) / Google Workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.integration import IdpActorEnrichment

logger = structlog.get_logger(__name__)

# ─── Cache helpers ─────────────────────────────────────────────────────────────

_IDP_CACHE_TTL = 3600  # 1 hour


async def get_enrichment(
    session: AsyncSession,
    actor: str,
) -> IdpActorEnrichment | None:
    """Return cached enrichment for an actor if it exists and is fresh."""
    result = await session.execute(
        select(IdpActorEnrichment).where(IdpActorEnrichment.github_login == actor)
    )
    enrichment = result.scalar_one_or_none()
    if enrichment:
        age = (datetime.now(UTC) - enrichment.updated_at).total_seconds()
        if age < _IDP_CACHE_TTL:
            return enrichment
    return None


async def upsert_enrichment(
    session: AsyncSession,
    actor: str,
    data: dict[str, Any],
) -> IdpActorEnrichment:
    """Write or update enrichment data for an actor."""
    result = await session.execute(
        select(IdpActorEnrichment).where(IdpActorEnrichment.github_login == actor)
    )
    enrichment = result.scalar_one_or_none()

    if enrichment:
        enrichment.display_name = data.get("display_name") or enrichment.display_name
        enrichment.email = data.get("email") or enrichment.email
        enrichment.department = data.get("department") or enrichment.department
        enrichment.title = data.get("title") or enrichment.title
        enrichment.manager_login = data.get("manager_login") or enrichment.manager_login
        enrichment.is_active = data.get("is_active", True)
        enrichment.idp_source = data.get("idp_source") or enrichment.idp_source
        enrichment.raw_profile = data.get("raw_profile") or {}
        enrichment.updated_at = datetime.now(UTC)
    else:
        enrichment = IdpActorEnrichment(
            github_login=actor,
            display_name=data.get("display_name"),
            email=data.get("email"),
            department=data.get("department"),
            title=data.get("title"),
            manager_login=data.get("manager_login"),
            is_active=data.get("is_active", True),
            idp_source=data.get("idp_source", "unknown"),
            raw_profile=data.get("raw_profile") or {},
        )
        session.add(enrichment)

    await session.flush()
    return enrichment


# ─── Okta ──────────────────────────────────────────────────────────────────────


async def enrich_from_okta(actor: str) -> dict[str, Any] | None:
    """Fetch Okta user profile for a GitHub login (email search)."""
    try:
        from okta.client import Client as OktaClient

        okta_cfg = settings.integrations
        if not okta_cfg.okta_domain or not okta_cfg.okta_api_token:
            return None

        client = OktaClient(
            {
                "orgUrl": f"https://{okta_cfg.okta_domain}",
                "token": okta_cfg.okta_api_token,
            }
        )

        # Search by login (assume GitHub login == Okta login or email prefix)
        users, _, err = await client.list_users(query_params={"search": f'login eq "{actor}"'})
        if err or not users:
            # Fallback: search by profile.githubUsername custom attribute
            users, _, err = await client.list_users(
                query_params={"search": f'profile.githubUsername eq "{actor}"'}
            )

        if err or not users:
            logger.debug("idp.okta_not_found", actor=actor)
            return None

        user = users[0]
        profile = user.profile

        return {
            "display_name": f"{profile.firstName} {profile.lastName}".strip(),
            "email": profile.email,
            "department": getattr(profile, "department", None),
            "title": getattr(profile, "title", None),
            "is_active": user.status == "ACTIVE",
            "idp_source": "okta",
            "raw_profile": {
                "okta_id": user.id,
                "status": user.status,
                "login": profile.login,
            },
        }
    except Exception as exc:
        logger.error("idp.okta_error", actor=actor, error=str(exc))
        return None


# ─── Microsoft Entra ID (MSAL / Graph API) ────────────────────────────────────


async def enrich_from_entra(actor: str) -> dict[str, Any] | None:
    """Fetch Entra ID / Azure AD user profile."""
    try:
        import msal

        entra_cfg = settings.integrations
        if not entra_cfg.entra_tenant_id or not entra_cfg.entra_client_id:
            return None

        app = msal.ConfidentialClientApplication(
            entra_cfg.entra_client_id,
            authority=f"https://login.microsoftonline.com/{entra_cfg.entra_tenant_id}",
            client_credential=entra_cfg.entra_client_secret,
        )
        token_result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in token_result:
            logger.warning("idp.entra_token_error", error=token_result.get("error"))
            return None

        import aiohttp

        headers = {"Authorization": f"Bearer {token_result['access_token']}"}
        filter_param = f"userPrincipalName eq '{actor}' or displayName eq '{actor}'"
        url = f"https://graph.microsoft.com/v1.0/users?$filter={filter_param}&$select=id,displayName,mail,department,jobTitle,accountEnabled,manager"

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        users = data.get("value", [])
        if not users:
            return None

        user = users[0]
        return {
            "display_name": user.get("displayName"),
            "email": user.get("mail"),
            "department": user.get("department"),
            "title": user.get("jobTitle"),
            "is_active": user.get("accountEnabled", True),
            "idp_source": "entra",
            "raw_profile": {"entra_id": user.get("id")},
        }
    except Exception as exc:
        logger.error("idp.entra_error", actor=actor, error=str(exc))
        return None


# ─── Google Workspace ─────────────────────────────────────────────────────────


async def enrich_from_google(actor: str) -> dict[str, Any] | None:
    """Fetch Google Workspace user profile via Admin SDK."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        google_cfg = settings.integrations
        if not google_cfg.google_sa_key_path or not google_cfg.google_admin_email:
            return None

        scopes = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]
        credentials = service_account.Credentials.from_service_account_file(
            google_cfg.google_sa_key_path,
            scopes=scopes,
            subject=google_cfg.google_admin_email,
        )
        service = build("admin", "directory_v1", credentials=credentials)

        # Search by primaryEmail
        result = (
            service.users()
            .list(
                customer="my_customer",
                query=f"email={actor} OR externalId={actor}",
                maxResults=1,
            )
            .execute()
        )

        users = result.get("users", [])
        if not users:
            return None

        user = users[0]
        return {
            "display_name": user.get("name", {}).get("fullName"),
            "email": user.get("primaryEmail"),
            "department": user.get("orgUnitPath"),
            "title": user.get("organizations", [{}])[0].get("title"),
            "is_active": not user.get("suspended", False),
            "idp_source": "google",
            "raw_profile": {"google_id": user.get("id")},
        }
    except Exception as exc:
        logger.error("idp.google_error", actor=actor, error=str(exc))
        return None


# ─── Auto-enrich dispatcher ───────────────────────────────────────────────────


async def auto_enrich_actor(
    session: AsyncSession,
    actor: str,
) -> IdpActorEnrichment | None:
    """Try all available IdP sources in order and write to cache."""
    # Check Valkey cache first (DB cache)
    existing = await get_enrichment(session, actor)
    if existing:
        return existing

    # Try each IdP source
    for enrich_fn in [enrich_from_okta, enrich_from_entra, enrich_from_google]:
        data = await enrich_fn(actor)
        if data:
            return await upsert_enrichment(session, actor, data)

    logger.debug("idp.no_enrichment_found", actor=actor)
    return None
