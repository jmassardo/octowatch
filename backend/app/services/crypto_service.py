"""AES-256-GCM encryption for the secrets store.

Derives per-purpose keys from ENCRYPTION_KEY using HKDF-SHA256.
Each encrypted value gets a unique 12-byte nonce prepended to the ciphertext.
"""

# DEPRECATED: This module provides backward compatibility during the migration
# from PostgreSQL-stored encrypted secrets to Azure Key Vault (Issue #135).
# New code should use the SecretProvider abstraction (app.services.secret_provider)
# instead of directly encrypting/decrypting values.
# This module will be removed once all secrets are migrated to Key Vault.

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_key(master_key: str, purpose: str = "app_secrets") -> bytes:
    """Derive a 256-bit key from the master key using HKDF.

    Args:
        master_key: The master encryption key (from env var).
        purpose: An info string for key derivation context separation.

    Returns:
        A 32-byte derived key suitable for AES-256-GCM.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"octowatch-secrets-v1",
        info=purpose.encode(),
    )
    return hkdf.derive(master_key.encode())


def encrypt_value(plaintext: str, key: bytes) -> str:
    """Encrypt a string value using AES-256-GCM.

    Returns base64-encoded ``nonce || ciphertext``.

    Args:
        plaintext: The plaintext string to encrypt.
        key: A 32-byte AES key (from :func:`derive_key`).

    Returns:
        Base64-encoded string of ``nonce + ciphertext + tag``.
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_value(encrypted: str, key: bytes) -> str:
    """Decrypt a base64-encoded ``nonce || ciphertext`` value.

    Args:
        encrypted: Base64-encoded string produced by :func:`encrypt_value`.
        key: The same 32-byte AES key used during encryption.

    Returns:
        The decrypted plaintext string.

    Raises:
        cryptography.exceptions.InvalidTag: If decryption fails (wrong key or
            tampered ciphertext).
    """
    raw = base64.b64decode(encrypted)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()


def mask_value(value: str, sensitivity: str) -> str:
    """Mask a setting value based on its sensitivity level.

    Args:
        value: The plaintext setting value.
        sensitivity: One of ``"critical"``, ``"sensitive"``, or ``"config"``.

    Returns:
        The masked (or unmasked) value.
    """
    if sensitivity == "critical":
        return "••••••••"
    if sensitivity == "sensitive":
        if len(value) <= 8:
            return "••••••••"
        return value[:4] + "••••" + value[-4:]
    return value  # config level — show plaintext
