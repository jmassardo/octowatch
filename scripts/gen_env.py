#!/usr/bin/env python3
"""Generate .env file with random secrets for local development.

Usage:
    python scripts/gen_env.py          # Docker service hostnames (default)
    python scripts/gen_env.py --local  # localhost for running outside Docker
"""

import argparse
import subprocess
import os


def gen(n):
    return subprocess.check_output(["openssl", "rand", "-hex", str(n)]).decode().strip()


parser = argparse.ArgumentParser(description="Generate .env for OctoWatch")
parser.add_argument(
    "--local",
    action="store_true",
    help="Use localhost hostnames instead of Docker service names",
)
args = parser.parse_args()

secret_key = gen(32)
postgres_pw = gen(16)
valkey_pw = gen(16)
minio_root_pw = gen(16)
minio_ingest_pw = gen(16)

if args.local:
    db_host = "localhost"
    valkey_host = "localhost"
    minio_host = "localhost"
    app_base_url = "http://localhost:5173"
else:
    db_host = "db"
    valkey_host = "valkey"
    minio_host = "minio"
    app_base_url = "https://localhost"

lines = [
    "# Core Application",
    f"DATABASE_URL=postgresql+asyncpg://appuser:{postgres_pw}@{db_host}:5432/audit_logs",
    f"SECRET_KEY={secret_key}",
    f"VALKEY_URL=redis://:{valkey_pw}@{valkey_host}:6379/0",
    "LOG_LEVEL=INFO",
    "INGESTION_MODE=minio",
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
    f"APP_BASE_URL={app_base_url}",
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
    "# MinIO",
    f"MINIO_ENDPOINT_URL=http://{minio_host}:9000",
    "MINIO_AUDIT_BUCKET=audit-logs",
    "MINIO_ROOT_USER=minioadmin",
    f"MINIO_ROOT_PASSWORD={minio_root_pw}",
    "MINIO_INGEST_USER=ingest-service",
    f"MINIO_INGEST_PASSWORD={minio_ingest_pw}",
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

output_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)
with open(output_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Created {output_path}")
