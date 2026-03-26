"""Application configuration using pydantic-settings.

All secrets and configuration come from environment variables only — never
hardcoded. Grouped into nested models for clarity. Validated at startup;
missing required values cause an immediate exit.
"""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    DATABASE_URL: str = Field(
        ...,
        description=(
            "PostgreSQL async connection string. "
            "Format: postgresql+asyncpg://user:pass@host:5432/db?sslmode=require"
        ),
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg:// scheme")
        return v


class ValkeySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    VALKEY_URL: str = Field(
        ...,
        description="Valkey connection string. Format: redis://:password@host:6379/0",
    )

    @field_validator("VALKEY_URL")
    @classmethod
    def validate_valkey_url(cls, v: str) -> str:
        if not v.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("VALKEY_URL must use redis://, rediss://, or unix:// scheme")
        return v


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    SECRET_KEY: str = Field(..., min_length=32, description="HS256 JWT signing key (256-bit hex)")
    APP_BASE_URL: str = Field(
        ..., description="Public base URL (no trailing slash). Used for OAuth callback + SAML ACS."
    )

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = Field(..., description="GitHub OAuth App client ID")
    GITHUB_CLIENT_SECRET: str = Field(..., description="GitHub OAuth App client secret")

    # SAML 2.0 (optional — app works without SAML)
    SAML_IDP_METADATA_URL: str | None = Field(None, description="URL of IdP SAML metadata XML")
    SAML_SP_CERT: str | None = Field(None, description="PEM-encoded SP certificate")
    SAML_SP_KEY: str | None = Field(None, description="PEM-encoded SP private key")

    JWT_TTL_SECONDS: int = Field(default=3600, description="JWT and session TTL in seconds")

    @field_validator("APP_BASE_URL")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("APP_BASE_URL must be http or https")
        if v.endswith("/"):
            return v.rstrip("/")
        return v


class MinIOSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    MINIO_ENDPOINT_URL: str = Field(
        default="http://minio:9000",
        description="Internal MinIO S3-compatible API endpoint",
    )
    MINIO_AUDIT_BUCKET: str = Field(..., description="MinIO bucket for audit logs")
    MINIO_INGEST_USER: str = Field(..., description="MinIO read-only service account username")
    MINIO_INGEST_PASSWORD: str = Field(..., description="MinIO read-only service account password")

    MINIO_HMAC_SECRET: str | None = Field(
        None,
        description="HMAC secret for MinIO bucket notification signature verification",
    )

    @field_validator("MINIO_ENDPOINT_URL")
    @classmethod
    def validate_minio_endpoint(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("MINIO_ENDPOINT_URL must be http or https")
        # SSRF protection: block cloud metadata IP ranges
        host = (parsed.hostname or "").lower()
        _SSRF_BLOCKED = (
            "169.254.169.254",
            "metadata.google.internal",
            "169.254.170.2",
        )
        if host in _SSRF_BLOCKED or host.startswith("169.254."):
            raise ValueError(
                "SSRF protection: MINIO_ENDPOINT_URL must not point to cloud metadata addresses"
            )
        return v


class S3Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_DEFAULT_REGION: str | None = Field(
        None, description="AWS region (required when INGESTION_MODE=s3)"
    )
    S3_AUDIT_BUCKET: str | None = Field(
        None, description="S3 bucket name (required when INGESTION_MODE=s3)"
    )

    @field_validator("AWS_DEFAULT_REGION")
    @classmethod
    def validate_region(cls, v: str | None) -> str | None:
        import re

        if v is not None and not re.fullmatch(r"[a-z0-9-]+", v):
            raise ValueError("AWS_DEFAULT_REGION must match [a-z0-9-]+")
        return v

    @field_validator("S3_AUDIT_BUCKET")
    @classmethod
    def validate_bucket(cls, v: str | None) -> str | None:
        import re

        if v is not None and not re.fullmatch(r"[a-z0-9\-\.]{3,63}", v):
            raise ValueError("S3_AUDIT_BUCKET must be a valid S3 bucket name")
        return v


class AzureBlobSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    AZURE_STORAGE_CONNECTION_STRING: str | None = Field(
        None,
        description="Azure Storage connection string (required when INGESTION_MODE=azure_blob)",
    )
    AZURE_AUDIT_CONTAINER: str | None = Field(None, description="Azure Blob container name")

    @field_validator("AZURE_STORAGE_CONNECTION_STRING")
    @classmethod
    def validate_azure_conn(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # SSRF protection: validate hostname ends in .blob.core.windows.net
        # Connection strings may not contain AccountName explicitly; just allow it
        # if the format looks like a standard Azure connection string.
        if "AccountName=" not in v and "BlobEndpoint=" not in v:
            raise ValueError("Azure connection string must contain AccountName or BlobEndpoint")
        if "BlobEndpoint=" in v:
            # Custom endpoint must be *.blob.core.windows.net
            import re

            match = re.search(r"BlobEndpoint=https?://([^;/]+)", v)
            if match:
                host = match.group(1)
                if not host.endswith(".blob.core.windows.net"):
                    raise ValueError(
                        "SSRF protection: BlobEndpoint must be *.blob.core.windows.net"
                    )
        return v


class GeoIPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    GEOIP_DB_PATH: str = Field(
        default="/app/data/GeoLite2-City.mmdb",
        description="Filesystem path to MaxMind GeoLite2 City .mmdb file",
    )
    MAXMIND_LICENSE_KEY: str | None = Field(
        None, description="MaxMind license key for GeoLite2 download (optional)"
    )


class GitHubRulesSettings(BaseSettings):
    """Settings for GitHub-backed detection rule versioning."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    GITHUB_RULES_REPO: str = Field(
        default="",
        description="GitHub repo for detection rules, e.g. my-org/audit-rules",
    )
    GITHUB_RULES_TOKEN: str = Field(
        default="",
        description="GitHub PAT or App installation token with contents:write on GITHUB_RULES_REPO",
    )
    GITHUB_RULES_BRANCH: str = Field(
        default="main",
        description="Branch to commit rule YAML files to",
    )


class IntegrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # Okta
    OKTA_ORG_URL: str | None = None
    OKTA_API_TOKEN: str | None = None

    # Entra / Azure AD
    AZURE_AD_TENANT_ID: str | None = None
    AZURE_AD_CLIENT_ID: str | None = Field(None, alias="AZURE_AD_CLIENT_ID")
    AZURE_AD_CLIENT_SECRET: str | None = None

    # Google Workspace
    GOOGLE_SERVICE_ACCOUNT_JSON: str | None = None
    GOOGLE_WORKSPACE_DOMAIN: str | None = None

    # Jira
    JIRA_URL: str | None = None
    JIRA_USERNAME: str | None = None
    JIRA_API_TOKEN: str | None = None

    # Slack
    SLACK_BOT_TOKEN: str | None = None

    # SMTP
    SMTP_HOST: str | None = None
    SMTP_PORT: int = Field(default=587)
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_ADDRESS: str | None = None
    SMTP_USE_TLS: bool = Field(default=True)

    @field_validator("OKTA_ORG_URL")
    @classmethod
    def validate_okta_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        if not (parsed.hostname or "").endswith(".okta.com"):
            raise ValueError("SSRF protection: OKTA_ORG_URL must end in .okta.com")
        return v

    @field_validator("JIRA_URL")
    @classmethod
    def validate_jira_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("https",):
            raise ValueError("JIRA_URL must use HTTPS")
        return v


class Settings(BaseSettings):
    """Root application settings. Reads from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Core
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    INGESTION_MODE: Literal["minio", "s3", "azure_blob"] = "minio"
    QUERY_MAX_ROWS: int = Field(default=100_000, ge=1, le=1_000_000)
    QUERY_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=300)
    DETECTION_CONFIDENCE_THRESHOLD: float = Field(default=0.7, ge=0.0, le=1.0)

    # Nested
    DB: DatabaseSettings = Field(default_factory=DatabaseSettings)
    VALKEY: ValkeySettings = Field(default_factory=ValkeySettings)
    AUTH: AuthSettings = Field(default_factory=AuthSettings)
    MINIO: MinIOSettings = Field(default_factory=MinIOSettings)
    S3: S3Settings = Field(default_factory=S3Settings)
    AZURE: AzureBlobSettings = Field(default_factory=AzureBlobSettings)
    GEOIP: GeoIPSettings = Field(default_factory=GeoIPSettings)
    GIT: GitHubRulesSettings = Field(default_factory=GitHubRulesSettings)
    INTEGRATIONS: IntegrationSettings = Field(default_factory=IntegrationSettings)

    # Convenience proxies (read directly from env for Celery and Alembic access)
    @property
    def DATABASE_URL(self) -> str:
        return self.DB.DATABASE_URL

    @property
    def VALKEY_URL(self) -> str:
        return self.VALKEY.VALKEY_URL

    @property
    def SECRET_KEY(self) -> str:
        return self.AUTH.SECRET_KEY

    @property
    def JWT_TTL_SECONDS(self) -> int:
        return self.AUTH.JWT_TTL_SECONDS

    @property
    def environment(self) -> str:
        return self.ENVIRONMENT

    @property
    def cors_origins(self) -> list[str]:
        return self.CORS_ORIGINS

    @model_validator(mode="after")
    def validate_ingestion_mode_deps(self) -> Settings:
        if self.INGESTION_MODE == "s3":
            if not self.S3.S3_AUDIT_BUCKET:
                raise ValueError("S3_AUDIT_BUCKET required when INGESTION_MODE=s3")
            if not self.S3.AWS_DEFAULT_REGION:
                raise ValueError("AWS_DEFAULT_REGION required when INGESTION_MODE=s3")
        if self.INGESTION_MODE == "azure_blob":
            if not self.AZURE.AZURE_STORAGE_CONNECTION_STRING:
                raise ValueError(
                    "AZURE_STORAGE_CONNECTION_STRING required when INGESTION_MODE=azure_blob"
                )
            if not self.AZURE.AZURE_AUDIT_CONTAINER:
                raise ValueError("AZURE_AUDIT_CONTAINER required when INGESTION_MODE=azure_blob")
        return self


def _build_settings() -> Settings:
    """Build settings, reading each nested model from the environment directly."""
    return Settings(
        DB=DatabaseSettings(),
        VALKEY=ValkeySettings(),
        AUTH=AuthSettings(),
        MINIO=MinIOSettings(
            MINIO_AUDIT_BUCKET=os.getenv("MINIO_AUDIT_BUCKET", "audit-logs"),
            MINIO_INGEST_USER=os.getenv("MINIO_INGEST_USER", ""),
            MINIO_INGEST_PASSWORD=os.getenv("MINIO_INGEST_PASSWORD", ""),
        ),
        S3=S3Settings(),
        AZURE=AzureBlobSettings(),
        GEOIP=GeoIPSettings(),
        GIT=GitHubRulesSettings(
            GITHUB_RULES_REPO=os.getenv("GITHUB_RULES_REPO", ""),
            GITHUB_RULES_TOKEN=os.getenv("GITHUB_RULES_TOKEN", ""),
            GITHUB_RULES_BRANCH=os.getenv("GITHUB_RULES_BRANCH", "main"),
        ),
        INTEGRATIONS=IntegrationSettings(),
    )


# Singleton — import this everywhere
settings: Settings = _build_settings()
