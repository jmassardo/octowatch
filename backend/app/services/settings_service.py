"""Settings service — reads/writes encrypted settings from the app_settings table.

Provides an overlay on top of env-var-based config: if a key exists in the DB,
it takes precedence over the env var value.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.app_settings import AppSetting, AppSettingAudit, SetupState
from app.services.crypto_service import decrypt_value, derive_key, encrypt_value, mask_value

if TYPE_CHECKING:
    from app.services.secret_provider import SecretProvider

logger = structlog.get_logger(__name__)


def _get_encryption_key() -> bytes:
    """Return the derived encryption key, falling back to SECRET_KEY if needed."""
    master = settings.ENCRYPTION_KEY
    if not master:
        master = settings.SECRET_KEY
        logger.warning(
            "settings_service.encryption_key_fallback",
            detail="ENCRYPTION_KEY not set; falling back to SECRET_KEY. "
            "Set ENCRYPTION_KEY for production use.",
        )
    return derive_key(master)


async def get_setting(db: AsyncSession, key: str) -> str | None:
    """Get a decrypted setting value. Returns ``None`` if not found."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    enc_key = _get_encryption_key()
    return decrypt_value(row.encrypted_value, enc_key)


async def get_setting_with_provider(
    db: AsyncSession,
    key: str,
    secret_provider: SecretProvider | None = None,
) -> str | None:
    """Get a setting value, checking Key Vault first then falling back to DB.

    If a SecretProvider is available, it is checked first using the
    :data:`~app.services.config_overlay.KV_NAME_MAP` to translate the DB key
    to the Key Vault secret name. If the secret is not found in the provider
    (or no provider is given), falls back to the encrypted DB value.

    Args:
        db: Async database session.
        key: The setting key to look up.
        secret_provider: Optional SecretProvider instance. If None, only DB is checked.

    Returns:
        The decrypted/retrieved value, or None if not found in either location.
    """
    # Check Key Vault first if provider is available
    if secret_provider is not None:
        from app.services.config_overlay import KV_NAME_MAP

        kv_name = KV_NAME_MAP.get(key, key)
        try:
            value = await secret_provider.get_secret(kv_name)
            if value is not None:
                return value
        except Exception as exc:
            logger.warning(
                "settings_service.keyvault_fallback",
                key=key,
                kv_name=kv_name,
                error=str(exc),
                detail="Falling back to DB-encrypted value",
            )

    # Fall back to DB-encrypted value
    return await get_setting(db, key)


async def set_setting(
    db: AsyncSession,
    key: str,
    value: str,
    *,
    category: str = "config",
    sensitivity: str = "config",
    description: str | None = None,
    changed_by: str = "system",
) -> None:
    """Set an encrypted setting value. Creates an audit trail entry."""
    enc_key = _get_encryption_key()
    encrypted = encrypt_value(value, enc_key)

    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    existing = result.scalar_one_or_none()

    old_masked: str | None = None
    action: str

    if existing is not None:
        # Update
        old_value = decrypt_value(existing.encrypted_value, enc_key)
        old_masked = mask_value(old_value, existing.sensitivity)
        existing.encrypted_value = encrypted
        existing.category = category
        existing.sensitivity = sensitivity
        existing.description = description
        existing.updated_by = changed_by
        existing.updated_at = datetime.now(UTC)
        action = "updated"
    else:
        # Create
        setting = AppSetting(
            key=key,
            encrypted_value=encrypted,
            category=category,
            sensitivity=sensitivity,
            description=description,
            updated_by=changed_by,
        )
        db.add(setting)
        action = "created"

    new_masked = mask_value(value, sensitivity)

    audit = AppSettingAudit(
        setting_key=key,
        action=action,
        changed_by=changed_by,
        old_value_masked=old_masked,
        new_value_masked=new_masked,
    )
    db.add(audit)
    await db.flush()
    logger.info(
        "settings_service.setting_changed",
        key=key,
        action=action,
        changed_by=changed_by,
    )


async def delete_setting(db: AsyncSession, key: str, *, changed_by: str = "system") -> bool:
    """Delete a setting. Returns ``True`` if it existed."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    existing = result.scalar_one_or_none()
    if existing is None:
        return False

    enc_key = _get_encryption_key()
    old_value = decrypt_value(existing.encrypted_value, enc_key)
    old_masked = mask_value(old_value, existing.sensitivity)

    audit = AppSettingAudit(
        setting_key=key,
        action="deleted",
        changed_by=changed_by,
        old_value_masked=old_masked,
        new_value_masked=None,
    )
    db.add(audit)
    await db.execute(delete(AppSetting).where(AppSetting.key == key))
    await db.flush()
    logger.info("settings_service.setting_deleted", key=key, changed_by=changed_by)
    return True


async def list_settings(
    db: AsyncSession, category: str | None = None
) -> list[dict[str, str | None]]:
    """List all settings with masked values for critical/sensitive entries."""
    stmt = select(AppSetting).order_by(AppSetting.category, AppSetting.key)
    if category is not None:
        stmt = stmt.where(AppSetting.category == category)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    enc_key = _get_encryption_key()
    items: list[dict[str, str | None]] = []
    for row in rows:
        plaintext = decrypt_value(row.encrypted_value, enc_key)
        items.append(
            {
                "key": row.key,
                "value": mask_value(plaintext, row.sensitivity),
                "category": row.category,
                "sensitivity": row.sensitivity,
                "description": row.description,
                "updated_by": row.updated_by,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
    return items


async def get_settings_bulk(db: AsyncSession, keys: list[str]) -> dict[str, str]:
    """Get multiple decrypted settings at once (for startup overlay)."""
    if not keys:
        return {}
    stmt = select(AppSetting).where(AppSetting.key.in_(keys))
    result = await db.execute(stmt)
    rows = result.scalars().all()

    enc_key = _get_encryption_key()
    return {row.key: decrypt_value(row.encrypted_value, enc_key) for row in rows}


async def get_all_settings_decrypted(db: AsyncSession) -> dict[str, str]:
    """Get all decrypted settings (for config overlay at startup)."""
    result = await db.execute(select(AppSetting))
    rows = result.scalars().all()

    enc_key = _get_encryption_key()
    return {row.key: decrypt_value(row.encrypted_value, enc_key) for row in rows}


async def get_audit_trail(
    db: AsyncSession,
    *,
    setting_key: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, str | int | None]]:
    """Get the audit trail for setting changes."""
    stmt = (
        select(AppSettingAudit)
        .order_by(AppSettingAudit.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if setting_key is not None:
        stmt = stmt.where(AppSettingAudit.setting_key == setting_key)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "setting_key": row.setting_key,
            "action": row.action,
            "changed_by": row.changed_by,
            "old_value_masked": row.old_value_masked,
            "new_value_masked": row.new_value_masked,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


# ─── Setup state helpers ────────────────────────────────────────────────────────


async def _get_or_create_setup_state(db: AsyncSession) -> SetupState:
    """Return the singleton setup state row, creating it if it doesn't exist."""
    result = await db.execute(select(SetupState).where(SetupState.id == 1))
    state = result.scalar_one_or_none()
    if state is None:
        state = SetupState(id=1, is_complete=False)
        db.add(state)
        await db.flush()
    return state


async def is_setup_complete(db: AsyncSession) -> bool:
    """Check if initial setup has been completed."""
    state = await _get_or_create_setup_state(db)
    return state.is_complete


async def complete_setup(db: AsyncSession, completed_by: str) -> None:
    """Mark setup as complete. Invalidate the setup token."""
    state = await _get_or_create_setup_state(db)
    state.is_complete = True
    state.completed_by = completed_by
    state.completed_at = datetime.now(UTC)
    state.setup_token_hash = None  # invalidate token
    await db.flush()
    logger.info("settings_service.setup_completed", completed_by=completed_by)


def _hash_token(token: str) -> str:
    """Hash a setup token using SHA-256 for storage.

    We use SHA-256 instead of bcrypt here because the token is a 32-byte
    cryptographically random string — not a user-chosen password — so
    dictionary/brute-force attacks are not a concern.
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def verify_setup_token(db: AsyncSession, token: str) -> bool:
    """Verify the one-time setup token."""
    state = await _get_or_create_setup_state(db)
    if state.setup_token_hash is None:
        return False
    if state.is_complete:
        return False
    return secrets.compare_digest(state.setup_token_hash, _hash_token(token))


async def generate_setup_token(db: AsyncSession) -> str:
    """Generate and store a one-time setup token. Returns the plaintext token."""
    token = secrets.token_urlsafe(32)
    state = await _get_or_create_setup_state(db)
    state.setup_token_hash = _hash_token(token)
    await db.flush()
    logger.info("settings_service.setup_token_generated")
    return token
