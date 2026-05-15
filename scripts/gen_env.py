#!/usr/bin/env python3
"""Generate .env file with random secrets for local development."""
import subprocess
import os

def gen(n):
    return subprocess.check_output(["openssl", "rand", "-hex", str(n)]).decode().strip()

secret_key = gen(32)
postgres_pw = gen(16)
valkey_pw = gen(16)

lines = [
    "# Core Application",
    f"DATABASE_URL=postgresql+asyncpg://appuser:{postgres_pw}@db:5432/audit_logs",
    f"SECRET_KEY={secret_key}",
    f"VALKEY_URL=redis://:{valkey_pw}@valkey:6379/0",
    "LOG_LEVEL=INFO",
    "INGESTION_MODE=hec",
    "GEOIP_DB_PATH=/app/data/GeoLite2-City.mmdb",
    "GITHUB_RULES_REPO=",
    "GITHUB_RULES_TOKEN=",
    "GITHUB_RULES_BRANCH=main",
    "QUERY_MAX_ROWS=100000",
    "QUERY_TIMEOUT_SECONDS=30",
    "DETECTION_CONFIDENCE_THRESHOLD=0.7",
    "",
    "# GitHub OAuth - fill in your GitHub OAuth App credentials",
    "GITHUB_CLIENT_ID=CHANGE_ME",
    "GITHUB_CLIENT_SECRET=CHANGE_ME",
    "APP_BASE_URL=https://localhost",
    "",
    "# SAML (disabled for local dev)",
    "SAML_IDP_METADATA_URL=",
    "SAML_SP_CERT=",
    "SAML_SP_KEY=",
    "",
    "# PostgreSQL",
    "POSTGRES_USER=appuser",
    f"POSTGRES_PASSWORD={postgres_pw}",
    "POSTGRES_DB=audit_logs",
    "",
    "# Valkey",
    f"VALKEY_PASSWORD={valkey_pw}",
    "",
    "# HEC (Splunk-compatible audit log streaming)",
    f"HEC_TOKEN={gen(32)}",
    "",
    "# GeoIP (optional - leave MAXMIND_LICENSE_KEY blank to disable)",
    "MAXMIND_LICENSE_KEY=",
    "",
    "# Optional integrations (leave blank to disable)",
    "OKTA_ORG_URL=",
    "OKTA_API_TOKEN=",
    "AZURE_AD_TENANT_ID=",
    "AZURE_AD_CLIENT_ID=",
    "AZURE_AD_CLIENT_SECRET=",
    "GOOGLE_SERVICE_ACCOUNT_JSON=",
    "GOOGLE_WORKSPACE_DOMAIN=",
    "JIRA_URL=",
    "JIRA_USERNAME=",
    "JIRA_API_TOKEN=",
    "SLACK_BOT_TOKEN=",
    "SMTP_HOST=",
    "SMTP_PORT=587",
    "SMTP_USERNAME=",
    "SMTP_PASSWORD=",
    "SMTP_FROM_ADDRESS=",
    "AWS_ACCESS_KEY_ID=",
    "AWS_SECRET_ACCESS_KEY=",
    "AWS_DEFAULT_REGION=",
    "S3_AUDIT_BUCKET=",
    "AZURE_STORAGE_CONNECTION_STRING=",
    "AZURE_AUDIT_CONTAINER=",
]

output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

# Write with restrictive permissions (owner-only read/write) to protect secrets
fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Created {output_path}")
