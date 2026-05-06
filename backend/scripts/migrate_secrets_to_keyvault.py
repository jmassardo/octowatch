"""Migrate encrypted secrets from PostgreSQL to Azure Key Vault.

This script reads all ``app_settings`` rows whose keys are in the known
secret set, decrypts them using the existing crypto service, and writes
them to Azure Key Vault using the :data:`KV_NAME_MAP` naming convention.

The script is idempotent: it checks whether each secret already exists in
Key Vault before writing. Existing secrets are skipped.

Usage:
    cd backend
    python -m scripts.migrate_secrets_to_keyvault

Environment variables required:
    - SECRET_KEY or ENCRYPTION_KEY: for decrypting DB values
    - DATABASE_URL: PostgreSQL connection string
    - AZURE_KEYVAULT_URI: Key Vault URI (for azure_keyvault provider)
    - SECRET_PROVIDER: set to "azure_keyvault" (or rely on ENVIRONMENT=production)
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime

import structlog

# Ensure the backend package is importable when running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Run the secret migration from PostgreSQL to Key Vault."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import settings
    from app.models.app_settings import AppSetting
    from app.services.config_overlay import KV_NAME_MAP, SECRET_KEYS
    from app.services.crypto_service import decrypt_value, derive_key
    from app.services.secret_provider import create_secret_provider

    # Derive encryption key
    master = settings.ENCRYPTION_KEY or settings.SECRET_KEY
    if not master:
        logger.error("migrate.no_encryption_key", detail="Set ENCRYPTION_KEY or SECRET_KEY")
        sys.exit(1)
    enc_key = derive_key(master)

    # Create DB session
    database_url = str(settings.DATABASE_URL)
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create secret provider (must be azure_keyvault for this to be useful)
    provider = create_secret_provider()

    environment = os.environ.get("ENVIRONMENT", "development")
    migrated_at = datetime.now(UTC).isoformat()

    stats = {"found": 0, "migrated": 0, "skipped": 0, "failed": 0}

    try:
        async with async_session() as db:
            # Load all settings that are secrets
            result = await db.execute(select(AppSetting).where(AppSetting.key.in_(SECRET_KEYS)))
            rows = result.scalars().all()
            stats["found"] = len(rows)

            for row in rows:
                kv_name = KV_NAME_MAP.get(row.key)
                if kv_name is None:
                    logger.warning(
                        "migrate.no_kv_mapping",
                        key=row.key,
                        detail="Key not in KV_NAME_MAP, skipping",
                    )
                    stats["skipped"] += 1
                    continue

                # Check if secret already exists in KV
                try:
                    existing = await provider.get_secret(kv_name)
                    if existing is not None:
                        logger.info("migrate.already_exists", key=row.key, kv_name=kv_name)
                        stats["skipped"] += 1
                        continue
                except Exception as exc:
                    # Secret doesn't exist or provider error — proceed with write
                    logger.debug("migrate.kv_check_failed", key=row.key, error=str(exc))

                # Decrypt from DB
                try:
                    plaintext = decrypt_value(row.encrypted_value, enc_key)
                except Exception as exc:
                    logger.error("migrate.decrypt_failed", key=row.key, error=str(exc))
                    stats["failed"] += 1
                    continue

                # Write to Key Vault with tags
                try:
                    await provider.set_secret(
                        kv_name,
                        plaintext,
                        content_type="text/plain",
                        tags={
                            "environment": environment,
                            "managed-by": "octowatch",
                            "migrated-from": "postgresql",
                            "migrated-at": migrated_at,
                            "db-key": row.key,
                        },
                    )
                    logger.info("migrate.success", key=row.key, kv_name=kv_name)
                    stats["migrated"] += 1
                except Exception as exc:
                    logger.error(
                        "migrate.write_failed",
                        key=row.key,
                        kv_name=kv_name,
                        error=str(exc),
                    )
                    stats["failed"] += 1
    finally:
        await provider.close()
        await engine.dispose()

    # Print summary
    summary = (
        "\n" + "=" * 60 + "\n"
        "  Secret Migration Summary\n" + "=" * 60 + "\n"
        f"  Found in DB:  {stats['found']}\n"
        f"  Migrated:     {stats['migrated']}\n"
        f"  Skipped:      {stats['skipped']} (already in KV or no mapping)\n"
        f"  Failed:       {stats['failed']}\n" + "=" * 60 + "\n"
    )
    sys.stdout.write(summary)

    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
