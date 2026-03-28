"""Unit tests for the crypto_service module (AES-256-GCM encryption)."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.services.crypto_service import (
    decrypt_value,
    derive_key,
    encrypt_value,
    mask_value,
)


class TestDeriveKey:
    """Tests for HKDF key derivation."""

    def test_returns_32_bytes(self) -> None:
        key = derive_key("my-master-key")
        assert len(key) == 32

    def test_deterministic_for_same_inputs(self) -> None:
        key1 = derive_key("master", "purpose-a")
        key2 = derive_key("master", "purpose-a")
        assert key1 == key2

    def test_different_purposes_produce_different_keys(self) -> None:
        key1 = derive_key("master", "purpose-a")
        key2 = derive_key("master", "purpose-b")
        assert key1 != key2

    def test_different_master_keys_produce_different_keys(self) -> None:
        key1 = derive_key("master-1")
        key2 = derive_key("master-2")
        assert key1 != key2

    def test_empty_master_key(self) -> None:
        """Even an empty master key should produce a valid 32-byte key."""
        key = derive_key("")
        assert len(key) == 32


class TestEncryptDecrypt:
    """Tests for AES-256-GCM encrypt/decrypt round-trip."""

    def test_round_trip(self) -> None:
        key = derive_key("test-master")
        plaintext = "hello, world!"
        encrypted = encrypt_value(plaintext, key)
        decrypted = decrypt_value(encrypted, key)
        assert decrypted == plaintext

    def test_encrypted_value_is_base64(self) -> None:
        key = derive_key("test-master")
        encrypted = encrypt_value("test", key)
        # Should be valid base64
        raw = base64.b64decode(encrypted)
        # At least 12 bytes of nonce + some ciphertext
        assert len(raw) > 12

    def test_different_encryptions_produce_different_ciphertexts(self) -> None:
        """Each encryption uses a random nonce, so ciphertexts should differ."""
        key = derive_key("test-master")
        ct1 = encrypt_value("same value", key)
        ct2 = encrypt_value("same value", key)
        assert ct1 != ct2

    def test_wrong_key_raises(self) -> None:
        key1 = derive_key("key-1")
        key2 = derive_key("key-2")
        encrypted = encrypt_value("secret", key1)
        with pytest.raises(InvalidTag):
            decrypt_value(encrypted, key2)

    def test_tampered_ciphertext_raises(self) -> None:
        key = derive_key("test-master")
        encrypted = encrypt_value("secret", key)
        # Tamper with the base64 data
        raw = bytearray(base64.b64decode(encrypted))
        raw[-1] ^= 0xFF  # flip last byte
        tampered = base64.b64encode(bytes(raw)).decode()
        with pytest.raises(InvalidTag):
            decrypt_value(tampered, key)

    def test_empty_plaintext(self) -> None:
        key = derive_key("test-master")
        encrypted = encrypt_value("", key)
        decrypted = decrypt_value(encrypted, key)
        assert decrypted == ""

    def test_unicode_plaintext(self) -> None:
        key = derive_key("test-master")
        plaintext = "日本語テスト 🔑 Ñoño"
        encrypted = encrypt_value(plaintext, key)
        decrypted = decrypt_value(encrypted, key)
        assert decrypted == plaintext

    def test_long_plaintext(self) -> None:
        key = derive_key("test-master")
        plaintext = "x" * 100_000
        encrypted = encrypt_value(plaintext, key)
        decrypted = decrypt_value(encrypted, key)
        assert decrypted == plaintext


class TestMaskValue:
    """Tests for value masking by sensitivity level."""

    def test_critical_always_fully_masked(self) -> None:
        assert mask_value("super-secret-key", "critical") == "••••••••"

    def test_critical_short_value(self) -> None:
        assert mask_value("abc", "critical") == "••••••••"

    def test_sensitive_long_value_shows_prefix_suffix(self) -> None:
        result = mask_value("ghp_abc123xyz789", "sensitive")
        assert result.startswith("ghp_")
        assert result.endswith("z789")
        assert "••••" in result

    def test_sensitive_short_value_fully_masked(self) -> None:
        assert mask_value("short", "sensitive") == "••••••••"

    def test_sensitive_exactly_8_chars_fully_masked(self) -> None:
        assert mask_value("12345678", "sensitive") == "••••••••"

    def test_sensitive_9_chars_shows_prefix_suffix(self) -> None:
        result = mask_value("123456789", "sensitive")
        assert result == "1234••••6789"

    def test_config_shows_plaintext(self) -> None:
        assert mask_value("my-config-value", "config") == "my-config-value"

    def test_config_empty_string(self) -> None:
        assert mask_value("", "config") == ""

    def test_unknown_sensitivity_shows_plaintext(self) -> None:
        """Unknown sensitivity levels default to showing the value."""
        assert mask_value("value", "unknown") == "value"
