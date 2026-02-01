"""
Encryption at rest for agmem object store.

AES-256-GCM for object payloads; key derived from passphrase via Argon2id.
Hash-then-encrypt so content-addressable paths stay based on plaintext hash.
"""

import json
import os
import secrets
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Callable

# AES-GCM and Argon2id via cryptography
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False

IV_LEN = 12
TAG_LEN = 16
KEY_LEN = 32


def _encryption_config_path(mem_dir: Path) -> Path:
    return mem_dir / "encryption.json"


def load_encryption_config(mem_dir: Path) -> Optional[Dict[str, Any]]:
    """Load encryption config (salt, time_cost, memory_cost) from .mem/encryption.json."""
    path = _encryption_config_path(mem_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_encryption_config(
    mem_dir: Path,
    salt: bytes,
    time_cost: int = 3,
    memory_cost: int = 65536,
    parallelism: int = 4,
) -> Path:
    """Save encryption config; salt stored as hex. Returns config path."""
    mem_dir.mkdir(parents=True, exist_ok=True)
    path = _encryption_config_path(mem_dir)
    path.write_text(
        json.dumps(
            {
                "salt_hex": salt.hex(),
                "time_cost": time_cost,
                "memory_cost": memory_cost,
                "parallelism": parallelism,
            },
            indent=2,
        )
    )
    return path


def derive_key(
    passphrase: bytes,
    salt: bytes,
    time_cost: int = 3,
    memory_cost: int = 65536,
    parallelism: int = 4,
) -> bytes:
    """Derive 32-byte key from passphrase using Argon2id."""
    if not ENCRYPTION_AVAILABLE:
        raise RuntimeError("Encryption requires 'cryptography'")
    kdf = Argon2id(
        salt=salt,
        length=KEY_LEN,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
    )
    return kdf.derive(passphrase)


def encrypt(plaintext: bytes, key: bytes) -> Tuple[bytes, bytes]:
    """Encrypt with AES-256-GCM. Returns (iv, ciphertext_with_tag)."""
    if not ENCRYPTION_AVAILABLE:
        raise RuntimeError("Encryption requires 'cryptography'")
    aes = AESGCM(key)
    iv = secrets.token_bytes(IV_LEN)
    ct = aes.encrypt(iv, plaintext, None)  # ct includes 16-byte tag
    return (iv, ct)


def decrypt(iv: bytes, ciphertext_with_tag: bytes, key: bytes) -> bytes:
    """Decrypt AES-256-GCM. Raises on auth failure."""
    if not ENCRYPTION_AVAILABLE:
        raise RuntimeError("Encryption requires 'cryptography'")
    aes = AESGCM(key)
    return aes.decrypt(iv, ciphertext_with_tag, None)


def init_encryption(mem_dir: Path, time_cost: int = 3, memory_cost: int = 65536) -> bytes:
    """Create new encryption config with random salt. Returns salt (caller derives key from passphrase)."""
    salt = secrets.token_bytes(16)
    save_encryption_config(mem_dir, salt, time_cost=time_cost, memory_cost=memory_cost)
    return salt


class ObjectStoreEncryptor:
    """
    Encryptor for object store payloads (compressed bytes).
    Uses AES-256-GCM; IV and tag stored with ciphertext.
    """

    def __init__(self, get_key: Callable[[], Optional[bytes]]):
        self._get_key = get_key

    def encrypt_payload(self, plaintext: bytes) -> bytes:
        """Encrypt payload. Returns iv (12) + ciphertext_with_tag."""
        key = self._get_key()
        if not key:
            raise ValueError("Encryption key not available (passphrase required)")
        iv, ct = encrypt(plaintext, key)
        return iv + ct

    def decrypt_payload(self, raw: bytes) -> bytes:
        """Decrypt payload. raw = iv (12) + ciphertext_with_tag."""
        key = self._get_key()
        if not key:
            raise ValueError("Encryption key not available (passphrase required)")
        if len(raw) < IV_LEN + TAG_LEN:
            raise ValueError("Payload too short for encrypted object")
        iv = raw[:IV_LEN]
        ct = raw[IV_LEN:]
        return decrypt(iv, ct, key)


def get_key_from_env_or_cache(
    mem_dir: Path,
    env_var: str = "AGMEM_ENCRYPTION_PASSPHRASE",
    cache_var: str = "_agmem_encryption_key_cache",
) -> Optional[bytes]:
    """Get key from env or process cache. Derives key if passphrase in env and config exists."""
    # Module-level cache for session (same process)
    import sys

    mod = sys.modules.get("memvcs.core.encryption")
    if mod and getattr(mod, cache_var, None) is not None:
        return getattr(mod, cache_var)
    passphrase = os.environ.get(env_var)
    if not passphrase:
        return None
    cfg = load_encryption_config(mem_dir)
    if not cfg:
        return None
    salt = bytes.fromhex(cfg["salt_hex"])
    key = derive_key(
        passphrase.encode() if isinstance(passphrase, str) else passphrase,
        salt,
        time_cost=cfg.get("time_cost", 3),
        memory_cost=cfg.get("memory_cost", 65536),
        parallelism=cfg.get("parallelism", 4),
    )
    if mod is not None:
        setattr(mod, cache_var, key)
    return key
