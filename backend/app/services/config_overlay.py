"""Overlay DB-backed settings onto the Pydantic settings singleton.

At app startup (after DB is available), this reads all app_settings from the DB
and patches the in-memory settings object.  Workers call :func:`refresh_settings`
periodically or at task start.

The ``SETTING_MAP`` maps DB key names to ``(nested_attr, field_name)`` pairs on
the :class:`~app.config.Settings` singleton.  When ``nested_attr`` is ``None``,
the field lives directly on the root settings object.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.settings_service import get_all_settings_decrypted

logger = structlog.get_logger(__name__)

# Mapping from DB key → (nested_attr_on_settings, field_name)
# None as first element means the field lives on the root Settings object.
SETTING_MAP: dict[str, tuple[str | None, str]] = {
    # GitHub OAuth
    "github_client_id": ("AUTH", "GITHUB_CLIENT_ID"),
    "github_client_secret": ("AUTH", "GITHUB_CLIENT_SECRET"),
    # GitHub App
    "github_app_id": ("GITHUB_APP", "GITHUB_APP_ID"),
    "github_app_private_key": ("GITHUB_APP", "GITHUB_APP_PRIVATE_KEY_PEM"),
    "github_enterprise_slug": ("GITHUB_APP", "GITHUB_ENTERPRISE_SLUG"),
    "github_sync_enabled": ("GITHUB_APP", "GITHUB_SYNC_ENABLED"),
    "github_sync_interval_days": ("GITHUB_APP", "GITHUB_SYNC_INTERVAL_DAYS"),
    "github_sync_orgs": ("GITHUB_APP", "GITHUB_SYNC_ORGS"),
    # SAML
    "saml_idp_metadata_url": ("AUTH", "SAML_IDP_METADATA_URL"),
    "saml_sp_cert": ("AUTH", "SAML_SP_CERT"),
    "saml_sp_key": ("AUTH", "SAML_SP_KEY"),
    # MinIO
    "minio_endpoint_url": ("MINIO", "MINIO_ENDPOINT_URL"),
    "minio_ingest_user": ("MINIO", "MINIO_INGEST_USER"),
    "minio_ingest_password": ("MINIO", "MINIO_INGEST_PASSWORD"),
    "minio_audit_bucket": ("MINIO", "MINIO_AUDIT_BUCKET"),
    "minio_stream_user": ("MINIO", "MINIO_STREAM_USER"),
    "minio_stream_password": ("MINIO", "MINIO_STREAM_PASSWORD"),
    # App config
    "app_base_url": ("AUTH", "APP_BASE_URL"),
    "detection_confidence_threshold": (None, "DETECTION_CONFIDENCE_THRESHOLD"),
    "query_max_rows": (None, "QUERY_MAX_ROWS"),
    "query_timeout_seconds": (None, "QUERY_TIMEOUT_SECONDS"),
    # GeoIP
    "geoip_db_path": ("GEOIP", "GEOIP_DB_PATH"),
    "maxmind_license_key": ("GEOIP", "MAXMIND_LICENSE_KEY"),
    # Git rules
    "github_rules_repo": ("GIT", "GITHUB_RULES_REPO"),
    "github_rules_token": ("GIT", "GITHUB_RULES_TOKEN"),
    "github_rules_branch": ("GIT", "GITHUB_RULES_BRANCH"),
    # S3
    "aws_access_key_id": ("S3", "AWS_ACCESS_KEY_ID"),
    "aws_secret_access_key": ("S3", "AWS_SECRET_ACCESS_KEY"),
    "aws_default_region": ("S3", "AWS_DEFAULT_REGION"),
    "s3_audit_bucket": ("S3", "S3_AUDIT_BUCKET"),
    # Azure
    "azure_storage_connection_string": ("AZURE", "AZURE_STORAGE_CONNECTION_STRING"),
    "azure_audit_container": ("AZURE", "AZURE_AUDIT_CONTAINER"),
    # Integrations
    "okta_org_url": ("INTEGRATIONS", "OKTA_ORG_URL"),
    "okta_api_token": ("INTEGRATIONS", "OKTA_API_TOKEN"),
    "azure_ad_tenant_id": ("INTEGRATIONS", "AZURE_AD_TENANT_ID"),
    "azure_ad_client_id": ("INTEGRATIONS", "AZURE_AD_CLIENT_ID"),
    "azure_ad_client_secret": ("INTEGRATIONS", "AZURE_AD_CLIENT_SECRET"),
    "google_service_account_json": ("INTEGRATIONS", "GOOGLE_SERVICE_ACCOUNT_JSON"),
    "google_workspace_domain": ("INTEGRATIONS", "GOOGLE_WORKSPACE_DOMAIN"),
    "jira_url": ("INTEGRATIONS", "JIRA_URL"),
    "jira_username": ("INTEGRATIONS", "JIRA_USERNAME"),
    "jira_api_token": ("INTEGRATIONS", "JIRA_API_TOKEN"),
    "slack_bot_token": ("INTEGRATIONS", "SLACK_BOT_TOKEN"),
    "smtp_host": ("INTEGRATIONS", "SMTP_HOST"),
    "smtp_port": ("INTEGRATIONS", "SMTP_PORT"),
    "smtp_username": ("INTEGRATIONS", "SMTP_USERNAME"),
    "smtp_password": ("INTEGRATIONS", "SMTP_PASSWORD"),
    "smtp_from_address": ("INTEGRATIONS", "SMTP_FROM_ADDRESS"),
    "smtp_use_tls": ("INTEGRATIONS", "SMTP_USE_TLS"),
}

# Fields that require type coercion from string to their actual type
_BOOL_FIELDS = {"GITHUB_SYNC_ENABLED", "SMTP_USE_TLS"}
_INT_FIELDS = {
    "GITHUB_APP_ID",
    "GITHUB_SYNC_INTERVAL_DAYS",
    "SMTP_PORT",
    "QUERY_MAX_ROWS",
    "QUERY_TIMEOUT_SECONDS",
}
_FLOAT_FIELDS = {"DETECTION_CONFIDENCE_THRESHOLD"}


def _coerce_value(field_name: str, value: str) -> object:
    """Coerce a string value to the correct Python type for the target field."""
    if field_name in _BOOL_FIELDS:
        return value.lower() in ("true", "1", "yes")
    if field_name in _INT_FIELDS:
        return int(value)
    if field_name in _FLOAT_FIELDS:
        return float(value)
    return value


def _apply_setting(db_key: str, value: str) -> bool:
    """Apply a single DB setting to the in-memory settings singleton.

    Returns ``True`` if the setting was applied successfully.
    """
    mapping = SETTING_MAP.get(db_key)
    if mapping is None:
        logger.debug("config_overlay.unknown_key", key=db_key)
        return False

    nested_attr, field_name = mapping
    try:
        coerced = _coerce_value(field_name, value)
    except (ValueError, TypeError):
        logger.warning("config_overlay.coerce_failed", key=db_key, field=field_name)
        return False

    try:
        if nested_attr is None:
            # Root-level setting
            object.__setattr__(settings, field_name, coerced)
        else:
            target = getattr(settings, nested_attr)
            object.__setattr__(target, field_name, coerced)
        return True
    except Exception:
        logger.warning("config_overlay.apply_failed", key=db_key, field=field_name, exc_info=True)
        return False


async def load_settings_overlay(db: AsyncSession) -> int:
    """Load all DB settings and overlay them onto the settings singleton.

    Returns the number of settings successfully applied.
    """
    all_settings = await get_all_settings_decrypted(db)
    applied = 0
    for db_key, value in all_settings.items():
        if _apply_setting(db_key, value):
            applied += 1
    logger.info("config_overlay.loaded", total=len(all_settings), applied=applied)
    return applied


async def refresh_settings(db: AsyncSession) -> int:
    """Refresh the settings overlay (for workers/periodic refresh).

    This is an alias for :func:`load_settings_overlay` that can be called
    by Celery workers at task start.
    """
    return await load_settings_overlay(db)
