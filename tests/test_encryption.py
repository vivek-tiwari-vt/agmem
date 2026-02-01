"""Tests for encryption at rest (when cryptography available)."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.encryption import (
    load_encryption_config,
    save_encryption_config,
    init_encryption,
    ENCRYPTION_AVAILABLE,
    ObjectStoreEncryptor,
    get_key_from_env_or_cache,
)


class TestEncryptionConfig:
    """Test encryption config load/save."""

    def test_load_config_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert load_encryption_config(Path(tmpdir)) is None

    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            salt = b"\x00" * 16
            save_encryption_config(mem_dir, salt, time_cost=2, memory_cost=1024)
            cfg = load_encryption_config(mem_dir)
            assert cfg is not None
            assert cfg.get("salt_hex") == salt.hex()
            assert cfg.get("time_cost") == 2
            assert cfg.get("memory_cost") == 1024


class TestInitEncryption:
    """Test init_encryption (creates salt and config)."""

    def test_init_encryption_creates_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            salt = init_encryption(Path(tmpdir), time_cost=2, memory_cost=1024)
            assert len(salt) == 16
            assert load_encryption_config(Path(tmpdir)) is not None


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="cryptography not installed")
class TestEncryptDecrypt:
    """Test encrypt/decrypt round-trip (requires cryptography)."""

    def test_encryptor_round_trip(self):
        from memvcs.core.encryption import encrypt, decrypt

        key = b"0" * 32
        plain = b"secret data"
        iv, ct = encrypt(plain, key)
        dec = decrypt(iv, ct, key)
        assert dec == plain

    def test_encryptor_different_iv_each_time(self):
        from memvcs.core.encryption import encrypt

        key = b"0" * 32
        _, ct1 = encrypt(b"x", key)
        _, ct2 = encrypt(b"x", key)
        assert ct1 != ct2


class TestObjectStoreEncryptor:
    """Test ObjectStoreEncryptor (key callback)."""

    def test_encryptor_raises_when_no_key(self):
        encryptor = ObjectStoreEncryptor(lambda: None)
        with pytest.raises(ValueError, match="passphrase required"):
            encryptor.encrypt_payload(b"data")

    def test_encryptor_decrypt_payload_raises_when_no_key(self):
        encryptor = ObjectStoreEncryptor(lambda: None)
        with pytest.raises(ValueError, match="passphrase required"):
            encryptor.decrypt_payload(b"x" * 50)


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="cryptography not installed")
class TestEncryptionEdgeCases:
    """Edge cases: wrong key, corrupted ciphertext."""

    def test_decrypt_with_wrong_key_fails(self):
        from memvcs.core.encryption import encrypt, decrypt

        key = b"0" * 32
        wrong_key = b"1" * 32
        plain = b"secret"
        iv, ct = encrypt(plain, key)
        with pytest.raises(Exception):
            decrypt(iv, ct, wrong_key)

    def test_decrypt_corrupted_ciphertext_fails(self):
        from memvcs.core.encryption import encrypt, decrypt

        key = b"0" * 32
        iv, ct = encrypt(b"secret", key)
        with pytest.raises(Exception):
            decrypt(iv, ct[:-1] + bytes([ct[-1] ^ 1]), key)
