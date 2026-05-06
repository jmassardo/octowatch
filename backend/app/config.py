"""Application configuration using pydantic-settings.

All secrets and configuration come from environment variables only — never
hardcoded. Grouped into nested models for clarity. Validated at startup;
missing required values cause an immediate exit.
"""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
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
        env = os.getenv("ENVIRONMENT", "development")
        if env == "production" and "sslmode=require" not in v and "sslmode=verify" not in v:
            import warnings

            warnings.warn(
                "DATABASE_URL should include sslmode=require in production",
                stacklevel=2,
            )
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
        env = os.getenv("ENVIRONMENT", "development")
        if env == "production" and v and not v.startswith("rediss://"):
            import warnings

            warnings.warn(
                "VALKEY_URL should use rediss:// (TLS) in production",
                stacklevel=2,
            )
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
    ROLE_REFRESH_INTERVAL_SECONDS: int = Field(
        default=300,
        ge=30,
        le=3600,
        description=(
            "How often to re-fetch user roles from database (seconds). "
            "Lower = faster revocation, higher = less DB load."
        ),
    )

    @field_validator("APP_BASE_URL")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        # Auto-detect GitHub Codespaces: if CODESPACE_NAME is set and
        # APP_BASE_URL still points to localhost, override with the
        # Codespace port-forwarded URL (port 5173 = frontend proxy).
        codespace_name = os.environ.get("CODESPACE_NAME")
        forwarding_domain = os.environ.get(
            "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN",
            "app.github.dev",
        )
        if codespace_name and "localhost" in v:
            v = f"https://{codespace_name}-5173.{forwarding_domain}"

        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("APP_BASE_URL must be http or https")
        if v.endswith("/"):
            return v.rstrip("/")
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


class GitHubAppSettings(BaseSettings):
    """GitHub App credentials and sync behaviour.

    GITHUB_APP_PRIVATE_KEY_PATH must point to a file on the local filesystem.
    The key is NEVER stored in the database and NEVER appears in API responses.
    When running in Kubernetes, mount the key as a Secret volume at this path.
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    GITHUB_APP_ID: str | int | None = Field(
        default=None,
        description="GitHub App numeric App ID (from App settings page)",
    )
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = Field(
        default=None,
        description="Absolute path to the PEM-encoded RS256 private key file",
    )
    GITHUB_APP_PRIVATE_KEY_PEM: str | None = Field(
        default=None,
        description="Inline PEM-encoded RS256 private key (from vault; takes precedence over PATH)",
    )
    GITHUB_ENTERPRISE_SLUG: str | None = Field(
        default=None,
        description="GitHub Enterprise account slug (e.g. 'my-company')",
    )
    GITHUB_SYNC_INTERVAL_DAYS: int = Field(
        default=60,
        ge=60,
        le=90,
        description="How many days between automatic scheduled syncs (60–90)",
    )
    GITHUB_SYNC_ENABLED: bool = Field(
        default=False,
        description="Enable/disable the scheduled enterprise sync",
    )
    GITHUB_IP_ALLOWLIST_ENABLED: bool = Field(
        default=False,
        description=(
            "Enable/disable IP filtering for webhook/stream endpoints "
            "using GitHub's published IP ranges"
        ),
    )
    GITHUB_SYNC_ORGS: str = Field(
        default="",
        description="Comma-separated org logins to include (empty = all enterprise orgs)",
    )

    @property
    def sync_orgs_list(self) -> list[str]:
        """Parse comma-separated GITHUB_SYNC_ORGS into a list."""
        if not self.GITHUB_SYNC_ORGS or not self.GITHUB_SYNC_ORGS.strip():
            return []
        return [s.strip() for s in self.GITHUB_SYNC_ORGS.split(",") if s.strip()]

    def resolve_private_key(self) -> str | None:
        """Return the PEM private key from the vault (inline) or filesystem.

        Inline PEM (``GITHUB_APP_PRIVATE_KEY_PEM``, set by the config overlay
        from the secrets vault) takes precedence over the file path.
        """
        if self.GITHUB_APP_PRIVATE_KEY_PEM:
            return self.GITHUB_APP_PRIVATE_KEY_PEM
        if self.GITHUB_APP_PRIVATE_KEY_PATH:
            with open(self.GITHUB_APP_PRIVATE_KEY_PATH) as fh:
                return fh.read()
        return None

    @field_validator("GITHUB_APP_ID", mode="before")
    @classmethod
    def coerce_app_id(cls, v: int | str | None) -> int | None:
        """Coerce empty strings to None and string digits to int.

        pydantic-settings v2 may pass the raw env-var string before the
        declared union type is resolved, so we handle the int conversion
        ourselves to avoid ``int_parsing`` errors on ``''``.
        """
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        if isinstance(v, str):
            try:
                return int(v.strip())
            except ValueError:
                raise ValueError(f"GITHUB_APP_ID must be a valid integer, got: {v!r}") from None
        return v

    @field_validator("GITHUB_APP_PRIVATE_KEY_PATH")
    @classmethod
    def validate_key_path(cls, v: str | None) -> str | None:
        """Validate the key exists and is a regular file.

        Skips validation if the value looks like inline PEM content
        (which happens transiently during config overlay application —
        the overlay now targets GITHUB_APP_PRIVATE_KEY_PEM instead).
        """
        if v is None or v.strip() == "":
            return None
        if v.strip().startswith("-----BEGIN"):
            return None  # Inline PEM accidentally targeted here; ignore
        if not os.path.isfile(v):
            raise ValueError(f"GITHUB_APP_PRIVATE_KEY_PATH does not point to a file: {v}")
        return v

    @field_validator("GITHUB_ENTERPRISE_SLUG", mode="before")
    @classmethod
    def validate_enterprise_slug(cls, v: str | None) -> str | None:
        """Enterprise slug must be alphanumeric with hyphens only. Empty string → None."""
        import re

        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("GITHUB_ENTERPRISE_SLUG must be a string")
        if v.strip() == "":
            return None
        if not re.fullmatch(r"[a-zA-Z0-9-]+", v):
            raise ValueError(
                "GITHUB_ENTERPRISE_SLUG must contain only alphanumeric characters and hyphens"
            )
        return v

    @field_validator("GITHUB_SYNC_INTERVAL_DAYS")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if not (60 <= v <= 90):
            raise ValueError("GITHUB_SYNC_INTERVAL_DAYS must be between 60 and 90 inclusive")
        return v


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
        if not v:
            return None
        parsed = urlparse(v)
        if not (parsed.hostname or "").endswith(".okta.com"):
            raise ValueError("SSRF protection: OKTA_ORG_URL must end in .okta.com")
        return v

    @field_validator("JIRA_URL")
    @classmethod
    def validate_jira_url(cls, v: str | None) -> str | None:
        if not v:
            return None
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

    # Encryption — master key for the secrets store.  If empty, falls back
    # to SECRET_KEY with a logged warning.  Generate with:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    ENCRYPTION_KEY: str = Field(
        default="",
        description="Master key for encrypting secrets in the DB. If empty, SECRET_KEY is used.",
    )

    # Network / proxy trust
    TRUSTED_PROXIES: list[str] = Field(
        default_factory=list,
        description=(
            "List of trusted proxy IPs/CIDRs (e.g., ['10.0.0.0/8', '172.16.0.0/12']). "
            "When the direct client IP is in this list, X-Forwarded-For is parsed "
            "right-to-left and the first non-trusted IP is returned."
        ),
    )

    # Core
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: list[str]) -> list[str]:
        if v and "*" in v:
            import warnings

            warnings.warn(
                "CORS_ORIGINS contains '*' which is incompatible with credentials",
                stacklevel=2,
            )
        return v

    INGESTION_MODE: Literal["hec"] = "hec"
    QUERY_MAX_ROWS: int = Field(default=100_000, ge=1, le=1_000_000)
    QUERY_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=300)
    DETECTION_CONFIDENCE_THRESHOLD: float = Field(default=0.7, ge=0.0, le=1.0)

    # Nested
    DB: DatabaseSettings = Field(default_factory=DatabaseSettings)
    VALKEY: ValkeySettings = Field(default_factory=ValkeySettings)
    AUTH: AuthSettings = Field(default_factory=AuthSettings)
    GEOIP: GeoIPSettings = Field(default_factory=GeoIPSettings)
    GIT: GitHubRulesSettings = Field(default_factory=GitHubRulesSettings)
    GITHUB_APP: GitHubAppSettings = Field(default_factory=GitHubAppSettings)
    INTEGRATIONS: IntegrationSettings = Field(default_factory=IntegrationSettings)

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
    def github_app(self) -> GitHubAppSettings:
        return self.GITHUB_APP

    @property
    def cors_origins(self) -> list[str]:
        return self.CORS_ORIGINS


def _build_settings() -> Settings:
    """Build settings, reading each nested model from the environment directly."""
    return Settings(
        DB=DatabaseSettings(),
        VALKEY=ValkeySettings(),
        AUTH=AuthSettings(),
        GEOIP=GeoIPSettings(),
        GIT=GitHubRulesSettings(
            GITHUB_RULES_REPO=os.getenv("GITHUB_RULES_REPO", ""),
            GITHUB_RULES_TOKEN=os.getenv("GITHUB_RULES_TOKEN", ""),
            GITHUB_RULES_BRANCH=os.getenv("GITHUB_RULES_BRANCH", "main"),
        ),
        GITHUB_APP=GitHubAppSettings(),
        INTEGRATIONS=IntegrationSettings(),
    )


# Singleton — import this everywhere
settings: Settings = _build_settings()
