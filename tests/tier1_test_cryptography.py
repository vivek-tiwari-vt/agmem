"""
Tier 1: Critical Cryptographic Tests

Tests for cryptographic signing, encryption, and related security operations.
These are the highest-priority tests as they protect the integrity and
confidentiality of memory content.

Coverage target: 95% for all cryptographic modules

NOTE: These tests require memvcs.core.crypto and memvcs.core.merkle modules
which are not yet implemented. Tests are marked as skipped.
"""

import pytest
import json
import hashlib
from pathlib import Path
from typing import Dict, Any
import tempfile
import shutil

# Mark all tests as skipped since crypto modules don't exist yet
pytestmark = pytest.mark.skip(reason="Crypto and Merkle modules not yet implemented")


# Test cryptographic signing
def test_signature_generation_and_verification():
    """Test that signatures can be generated and verified correctly."""
    from memvcs.core.crypto import sign_content, verify_signature

    content = b"test memory content for signing"

    # Generate signature
    signature = sign_content(content)
    assert signature is not None
    assert isinstance(signature, bytes)
    assert len(signature) > 0

    # Verify signature with same content
    is_valid = verify_signature(content, signature)
    assert is_valid is True


def test_signature_fails_on_modified_content():
    """Test that signature verification fails if content is modified."""
    from memvcs.core.crypto import sign_content, verify_signature

    original_content = b"original memory content"
    modified_content = b"modified memory content"

    signature = sign_content(original_content)

    # Verification should fail with different content
    is_valid = verify_signature(modified_content, signature)
    assert is_valid is False


def test_signature_fails_on_tampered_signature():
    """Test that signature verification fails if signature is tampered with."""
    from memvcs.core.crypto import sign_content, verify_signature

    content = b"test content"
    signature = sign_content(content)

    # Tamper with signature by modifying first byte
    tampered = bytearray(signature)
    tampered[0] ^= 0xFF  # Flip all bits
    tampered_signature = bytes(tampered)

    # Verification should fail
    is_valid = verify_signature(content, tampered_signature)
    assert is_valid is False


def test_encryption_decryption_round_trip():
    """Test that content can be encrypted and decrypted correctly."""
    from memvcs.core.crypto import encrypt_content, decrypt_content

    plaintext = b"sensitive memory data that needs encryption"
    encryption_key = b"encryption_key_32_bytes_long_!!!"  # 32 bytes for AES-256

    # Encrypt
    ciphertext, iv, tag = encrypt_content(plaintext, encryption_key)

    assert ciphertext != plaintext
    assert len(iv) == 12  # GCM nonce is typically 12 bytes
    assert len(tag) == 16  # GCM authentication tag is 16 bytes

    # Decrypt
    decrypted = decrypt_content(ciphertext, encryption_key, iv, tag)

    assert decrypted == plaintext


def test_encryption_fails_with_wrong_key():
    """Test that decryption fails with incorrect key."""
    from memvcs.core.crypto import encrypt_content, decrypt_content

    plaintext = b"secret content"
    correct_key = b"correct_key_32_bytes_long!!!!"
    wrong_key = b"wrong_key_32_bytes_long!!!!!!"

    ciphertext, iv, tag = encrypt_content(plaintext, correct_key)

    # Decryption with wrong key should fail or return garbage
    with pytest.raises(Exception):
        decrypt_content(ciphertext, wrong_key, iv, tag)


def test_encryption_fails_on_tampered_ciphertext():
    """Test that decryption fails if ciphertext is modified."""
    from memvcs.core.crypto import encrypt_content, decrypt_content

    plaintext = b"original content"
    key = b"encryption_key_32_bytes_long_!!!"

    ciphertext, iv, tag = encrypt_content(plaintext, key)

    # Tamper with ciphertext
    tampered = bytearray(ciphertext)
    tampered[0] ^= 0xFF
    tampered_ciphertext = bytes(tampered)

    # Decryption should fail
    with pytest.raises(Exception):
        decrypt_content(tampered_ciphertext, key, iv, tag)


def test_encryption_fails_on_tampered_tag():
    """Test that decryption fails if authentication tag is tampered with."""
    from memvcs.core.crypto import encrypt_content, decrypt_content

    plaintext = b"authenticated content"
    key = b"encryption_key_32_bytes_long_!!!"

    ciphertext, iv, tag = encrypt_content(plaintext, key)

    # Tamper with authentication tag
    tampered_tag = bytearray(tag)
    tampered_tag[0] ^= 0xFF
    tampered_tag_bytes = bytes(tampered_tag)

    # Decryption should fail due to authentication failure
    with pytest.raises(Exception):
        decrypt_content(ciphertext, key, iv, tampered_tag_bytes)


def test_merkle_tree_construction():
    """Test Merkle tree construction with sample data."""
    from memvcs.core.merkle import MerkleTree

    hashes = [hashlib.sha256(f"fact-{i}".encode()).digest() for i in range(8)]

    tree = MerkleTree(hashes)

    # Verify tree properties
    assert tree.root is not None
    assert len(tree.root) == 32  # SHA-256 produces 32 bytes

    # Should have correct height for 8 leaves (height 3)
    assert tree.height == 3


def test_merkle_proof_generation_and_verification():
    """Test Merkle proof generation and verification."""
    from memvcs.core.merkle import MerkleTree

    hashes = [hashlib.sha256(f"fact-{i}".encode()).digest() for i in range(8)]

    tree = MerkleTree(hashes)

    # Generate proof for leaf 3
    proof = tree.proof(3)

    assert proof is not None
    assert len(proof) > 0  # Should have siblings along the path

    # Verify proof
    is_valid = tree.verify_proof(3, hashes[3], proof, tree.root)
    assert is_valid is True


def test_merkle_proof_fails_with_wrong_leaf():
    """Test that Merkle proof verification fails with wrong leaf."""
    from memvcs.core.merkle import MerkleTree

    hashes = [hashlib.sha256(f"fact-{i}".encode()).digest() for i in range(8)]

    tree = MerkleTree(hashes)
    proof = tree.proof(3)

    # Try to verify with different hash
    wrong_hash = hashlib.sha256(b"wrong_content").digest()
    is_valid = tree.verify_proof(3, wrong_hash, proof, tree.root)
    assert is_valid is False


def test_merkle_proof_fails_with_wrong_root():
    """Test that Merkle proof verification fails with wrong root."""
    from memvcs.core.merkle import MerkleTree

    hashes = [hashlib.sha256(f"fact-{i}".encode()).digest() for i in range(8)]

    tree = MerkleTree(hashes)
    proof = tree.proof(3)

    # Create wrong root
    wrong_root = hashlib.sha256(b"wrong_root").digest()

    is_valid = tree.verify_proof(3, hashes[3], proof, wrong_root)
    assert is_valid is False


def test_hash_consistency():
    """Test that hashing the same content produces the same hash."""
    from memvcs.core.crypto import hash_content

    content = b"consistent content"

    hash1 = hash_content(content)
    hash2 = hash_content(content)

    assert hash1 == hash2


def test_hash_differs_for_different_content():
    """Test that hashing different content produces different hashes."""
    from memvcs.core.crypto import hash_content

    content1 = b"content one"
    content2 = b"content two"

    hash1 = hash_content(content1)
    hash2 = hash_content(content2)

    assert hash1 != hash2


def test_key_derivation():
    """Test that key derivation is deterministic."""
    from memvcs.core.crypto import derive_key

    password = "test_password"
    salt = b"test_salt_value!"

    key1 = derive_key(password, salt)
    key2 = derive_key(password, salt)

    assert key1 == key2
    assert len(key1) == 32  # AES-256 key


def test_key_derivation_different_with_different_password():
    """Test that key derivation differs with different passwords."""
    from memvcs.core.crypto import derive_key

    password1 = "password_one"
    password2 = "password_two"
    salt = b"test_salt_value!"

    key1 = derive_key(password1, salt)
    key2 = derive_key(password2, salt)

    assert key1 != key2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
