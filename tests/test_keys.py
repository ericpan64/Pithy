"""
Unit tests for pithy_cli.keys module.

Run with: pytest tests/test_keys.py -v
"""

import pytest
import os
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from pithy_cli.keys import (
    KeyStore, EncryptedKeyStore, CachedPassword,
    encrypt_keystore, decrypt_keystore,
    read_cached_password, write_cached_password, clear_cached_password,
    load_keystore, save_keystore,
    set_key, get_key, list_keys, remove_key, unlock, lock,
    ensure_pithy_dir, PITHY_DIR, KEYSTORE_PATH, CACHE_PATH,
    Provider, PROVIDER_KEYS, LEGACY_KEY_NAMES,
    get_provider_key, set_provider_key, list_providers, migrate_legacy_keys
)
from pithy_cli.cli import app

runner = CliRunner()


# Fixtures

@pytest.fixture
def temp_pithy_dir(tmp_path: Path, monkeypatch):
    """Mock the PITHY_DIR to use a temporary directory."""
    temp_dir = tmp_path / ".pithy"
    temp_dir.mkdir()

    # Patch the module-level constants
    monkeypatch.setattr('pithy_cli.keys.PITHY_DIR', temp_dir)
    monkeypatch.setattr('pithy_cli.keys.KEYSTORE_PATH', temp_dir / "keys")
    monkeypatch.setattr('pithy_cli.keys.CACHE_PATH', temp_dir / ".cache")

    return temp_dir


@pytest.fixture
def sample_keystore():
    """Create a sample keystore for testing."""
    return KeyStore(keys={
        "openai": "sk-test-123",
        "anthropic": "sk-ant-456",
        "test_key": "test_value"
    })


@pytest.fixture
def mock_getpass():
    """Mock getpass.getpass for testing."""
    with patch('pithy_cli.keys.getpass.getpass') as mock:
        yield mock


# Core Encryption Tests

def test_encrypt_decrypt_roundtrip(sample_keystore):
    """Test basic encrypt -> decrypt flow works correctly."""
    password = "test_password_123"

    # Encrypt
    encrypted = encrypt_keystore(sample_keystore, password)

    # Verify encrypted structure
    assert encrypted.version == 2
    assert len(encrypted.salt) == 32  # 16 bytes hex = 32 chars
    assert len(encrypted.nonce) == 24  # 12 bytes hex = 24 chars
    assert len(encrypted.ciphertext) > 0

    # Decrypt
    decrypted = decrypt_keystore(encrypted, password)

    # Verify content
    assert decrypted.keys == sample_keystore.keys
    assert "openai" in decrypted.keys
    assert decrypted.keys["openai"] == "sk-test-123"


def test_decrypt_wrong_password_fails(sample_keystore):
    """Test that wrong password raises ValueError."""
    correct_password = "correct_password"
    wrong_password = "wrong_password"

    encrypted = encrypt_keystore(sample_keystore, correct_password)

    with pytest.raises(ValueError, match="Invalid password or corrupted keystore"):
        decrypt_keystore(encrypted, wrong_password)


def test_empty_keystore_encryption():
    """Test encryption/decryption of empty keystore."""
    empty_keystore = KeyStore()
    password = "test_password"

    encrypted = encrypt_keystore(empty_keystore, password)
    decrypted = decrypt_keystore(encrypted, password)

    assert decrypted.keys == {}
    assert len(decrypted.keys) == 0


def test_special_characters_in_keys():
    """Test handling of unicode and special characters in keys/values."""
    special_keystore = KeyStore(keys={
        "unicode_key": "🔑 test_value with émojis",
        "special-chars": "value with spaces & symbols: !@#$%^&*()",
        "json_like": '{"nested": "value", "number": 123}'
    })
    password = "test_password"

    encrypted = encrypt_keystore(special_keystore, password)
    decrypted = decrypt_keystore(encrypted, password)

    assert decrypted.keys == special_keystore.keys
    assert "🔑 test_value with émojis" in decrypted.keys["unicode_key"]


# Password Caching Tests

def test_password_cache_valid_within_ttl(temp_pithy_dir):
    """Test password cache returns valid password within TTL."""
    password = "cached_password"
    ttl = 3600  # 1 hour

    write_cached_password(password, ttl)

    cached = read_cached_password()
    assert cached == password


def test_password_cache_expired_after_ttl(temp_pithy_dir, monkeypatch):
    """Test password cache returns None after TTL expires."""
    password = "expired_password"
    ttl = 1  # 1 second

    write_cached_password(password, ttl)

    # Mock time to simulate TTL expiration
    future_time = int(time.time()) + ttl + 1
    monkeypatch.setattr('time.time', lambda: future_time)

    cached = read_cached_password()
    assert cached is None

    # Cache file should be removed
    cache_path = temp_pithy_dir / ".cache"
    assert not cache_path.exists()


def test_clear_cached_password(temp_pithy_dir):
    """Test manual cache clearing."""
    password = "to_be_cleared"
    write_cached_password(password, 3600)

    # Verify cache exists
    assert read_cached_password() == password

    # Clear cache
    clear_cached_password()

    # Verify cache is gone
    assert read_cached_password() is None
    cache_path = temp_pithy_dir / ".cache"
    assert not cache_path.exists()


def test_corrupted_cache_file_recovery(temp_pithy_dir):
    """Test recovery from corrupted cache file."""
    cache_path = temp_pithy_dir / ".cache"

    # Write corrupted JSON
    cache_path.write_text("invalid json content")

    # Should handle gracefully and return None
    cached = read_cached_password()
    assert cached is None

    # Corrupted file should be removed
    assert not cache_path.exists()


# Keystore Operations Tests

def test_set_key_new(temp_pithy_dir, mock_getpass):
    """Test setting a new key."""
    mock_getpass.side_effect = ["master_password", "api_key_value"]

    set_key("new_key", "api_key_value")  # Pass value directly

    # Verify key was stored
    keystore = load_keystore()
    assert "new_key" in keystore.keys
    assert keystore.keys["new_key"] == "api_key_value"


def test_set_key_overwrite(temp_pithy_dir, mock_getpass, sample_keystore):
    """Test overwriting an existing key."""
    # First, save the sample keystore
    mock_getpass.return_value = "master_password"
    save_keystore(sample_keystore)

    # Mock user confirmation and new value
    with patch('builtins.input', return_value='y'):
        mock_getpass.side_effect = ["master_password", "new_value"]
        set_key("openai", "new_value")

    # Verify key was updated
    keystore = load_keystore()
    assert keystore.keys["openai"] == "new_value"


def test_get_key_exists(temp_pithy_dir, mock_getpass, sample_keystore):
    """Test retrieving an existing key."""
    mock_getpass.return_value = "master_password"
    save_keystore(sample_keystore)

    value = get_key("openai")
    assert value == "sk-test-123"


def test_get_key_not_found(temp_pithy_dir):
    """Test retrieving non-existent key returns None."""
    value = get_key("nonexistent_key")
    assert value is None


def test_list_keys_empty(temp_pithy_dir, capsys):
    """Test listing keys when keystore is empty."""
    list_keys()

    captured = capsys.readouterr()
    assert "No keys stored" in captured.out


def test_list_keys_multiple(temp_pithy_dir, mock_getpass, sample_keystore, capsys):
    """Test listing multiple keys."""
    mock_getpass.return_value = "master_password"
    save_keystore(sample_keystore)

    list_keys()

    captured = capsys.readouterr()
    assert "Stored Keys:" in captured.out
    assert "anthropic" in captured.out
    assert "openai" in captured.out
    assert "test_key" in captured.out


def test_remove_key_exists(temp_pithy_dir, mock_getpass, sample_keystore):
    """Test removing an existing key."""
    mock_getpass.return_value = "master_password"
    save_keystore(sample_keystore)

    with patch('builtins.input', return_value='y'):
        remove_key("test_key")

    # Verify key was removed
    keystore = load_keystore()
    assert "test_key" not in keystore.keys
    assert "openai" in keystore.keys  # Other keys preserved


def test_remove_key_not_found(temp_pithy_dir, mock_getpass):
    """Test removing non-existent key raises error."""
    mock_getpass.return_value = "master_password"
    save_keystore(KeyStore())  # Empty keystore

    with pytest.raises(ValueError, match="Key 'nonexistent' not found"):
        remove_key("nonexistent")


# Session Management Tests

def test_unlock_valid_password(temp_pithy_dir, mock_getpass, sample_keystore, capsys):
    """Test unlocking with valid password."""
    password = "valid_password"
    mock_getpass.return_value = password

    # Create keystore first
    save_keystore(sample_keystore)

    # Test unlock
    unlock(2.0)  # 2 hours

    captured = capsys.readouterr()
    assert "Unlocked for 2.0h" in captured.out

    # Verify password is cached
    cached = read_cached_password()
    assert cached == password


def test_unlock_invalid_password(temp_pithy_dir, mock_getpass, sample_keystore):
    """Test unlocking with wrong password."""
    # Create keystore with one password
    mock_getpass.return_value = "correct_password"
    save_keystore(sample_keystore)

    # Try to unlock with wrong password
    mock_getpass.return_value = "wrong_password"

    with pytest.raises(ValueError, match="Invalid password"):
        unlock()


def test_lock_clears_session(temp_pithy_dir, capsys):
    """Test locking clears cached password."""
    # Set up cached password
    write_cached_password("test_password", 3600)
    assert read_cached_password() == "test_password"

    # Lock
    lock()

    captured = capsys.readouterr()
    assert "Locked" in captured.out

    # Verify cache is cleared
    assert read_cached_password() is None


# CLI Integration Tests

def test_cli_keys_list_empty():
    """Test CLI keys list command with no keys."""
    with patch('pithy_cli.keys.load_keystore', return_value=KeyStore()):
        result = runner.invoke(app, ["keys", "list"])

    assert result.exit_code == 0
    assert "No keys stored" in result.stdout


def test_cli_keys_get_not_found():
    """Test CLI keys get command for missing key."""
    with patch('pithy_cli.keys.get_key', return_value=None):
        result = runner.invoke(app, ["keys", "get", "missing_key"])

    assert result.exit_code == 1
    assert "Key 'missing_key' not found" in result.stderr


def test_cli_help_commands():
    """Test CLI help shows all key commands."""
    result = runner.invoke(app, ["keys", "--help"])

    assert result.exit_code == 0
    assert "set" in result.stdout
    assert "get" in result.stdout
    assert "list" in result.stdout
    assert "remove" in result.stdout
    assert "unlock" in result.stdout
    assert "lock" in result.stdout


# File System & Security Tests

def test_secure_file_permissions(temp_pithy_dir, mock_getpass, sample_keystore):
    """Test that files are created with secure permissions."""
    if os.name == 'nt':  # Skip on Windows
        pytest.skip("File permission tests not applicable on Windows")

    mock_getpass.return_value = "test_password"
    save_keystore(sample_keystore)

    # Check directory permissions (should be 0o700)
    dir_stat = temp_pithy_dir.stat()
    assert oct(dir_stat.st_mode)[-3:] == '700'

    # Check keystore file permissions (should be 0o600)
    keystore_path = temp_pithy_dir / "keys"
    if keystore_path.exists():
        file_stat = keystore_path.stat()
        assert oct(file_stat.st_mode)[-3:] == '600'


def test_ensure_pithy_dir_creation(tmp_path, monkeypatch):
    """Test .pithy directory creation with proper setup."""
    test_dir = tmp_path / ".pithy"

    # Patch the global PITHY_DIR
    monkeypatch.setattr('pithy_cli.keys.PITHY_DIR', test_dir)

    ensure_pithy_dir()

    assert test_dir.exists()
    assert test_dir.is_dir()

    if os.name != 'nt':  # Unix systems
        stat = test_dir.stat()
        assert oct(stat.st_mode)[-3:] == '700'


# Provider-specific key management tests

def test_get_provider_key_new_name(temp_pithy_dir, mock_getpass):
    """Test getting provider key with new naming convention."""
    mock_getpass.return_value = "master_password"
    keystore = KeyStore(keys={"Anthropic": "sk-ant-test-123"})
    save_keystore(keystore)

    key = get_provider_key(Provider.ANTHROPIC)
    assert key == "sk-ant-test-123"


def test_get_provider_key_legacy_name(temp_pithy_dir, mock_getpass):
    """Test backward compatibility with legacy key names."""
    mock_getpass.return_value = "master_password"
    keystore = KeyStore(keys={"ANTHROPIC_API_KEY": "sk-ant-legacy-456"})
    save_keystore(keystore)

    key = get_provider_key(Provider.ANTHROPIC)
    assert key == "sk-ant-legacy-456"


def test_get_provider_key_prefers_new_name(temp_pithy_dir, mock_getpass):
    """Test that new naming convention is preferred over legacy."""
    mock_getpass.return_value = "master_password"
    keystore = KeyStore(keys={
        "Anthropic": "sk-ant-new",
        "ANTHROPIC_API_KEY": "sk-ant-old"
    })
    save_keystore(keystore)

    key = get_provider_key(Provider.ANTHROPIC)
    assert key == "sk-ant-new"


def test_get_provider_key_not_found(temp_pithy_dir):
    """Test getting non-existent provider key returns None."""
    key = get_provider_key(Provider.ANTHROPIC)
    assert key is None


def test_set_provider_key(temp_pithy_dir, mock_getpass):
    """Test setting provider key with new naming convention."""
    mock_getpass.return_value = "master_password"

    set_provider_key(Provider.ANTHROPIC, "sk-ant-new-key")

    keystore = load_keystore()
    assert "Anthropic" in keystore.keys
    assert keystore.keys["Anthropic"] == "sk-ant-new-key"


def test_list_providers_empty(temp_pithy_dir):
    """Test listing providers with no keys."""
    providers = list_providers()

    assert len(providers) == 2
    assert providers[Provider.ANTHROPIC] is False
    assert providers[Provider.OPENAI] is False


def test_list_providers_with_keys(temp_pithy_dir, mock_getpass):
    """Test listing providers with some keys set."""
    mock_getpass.return_value = "master_password"
    keystore = KeyStore(keys={
        "Anthropic": "sk-ant-123",
        "OPENAI_API_KEY": "sk-openai-456"  # Legacy name
    })
    save_keystore(keystore)

    providers = list_providers()

    assert providers[Provider.ANTHROPIC] is True
    assert providers[Provider.OPENAI] is True


def test_migrate_legacy_keys_success(temp_pithy_dir, mock_getpass, capsys):
    """Test successful migration of legacy keys."""
    mock_getpass.return_value = "master_password"
    keystore = KeyStore(keys={
        "ANTHROPIC_API_KEY": "sk-ant-legacy",
        "OPENAI_API_KEY": "sk-openai-legacy"
    })
    save_keystore(keystore)

    migrate_legacy_keys()

    # Check output
    captured = capsys.readouterr()
    assert "Migrated ANTHROPIC_API_KEY → Anthropic" in captured.out
    assert "Migrated OPENAI_API_KEY → OpenAI" in captured.out
    assert "Migration complete!" in captured.out

    # Verify keys were migrated
    keystore = load_keystore()
    assert "Anthropic" in keystore.keys
    assert "OpenAI" in keystore.keys
    assert "ANTHROPIC_API_KEY" not in keystore.keys
    assert "OPENAI_API_KEY" not in keystore.keys
    assert keystore.keys["Anthropic"] == "sk-ant-legacy"
    assert keystore.keys["OpenAI"] == "sk-openai-legacy"


def test_migrate_legacy_keys_no_legacy(temp_pithy_dir, mock_getpass, capsys):
    """Test migration when no legacy keys exist."""
    mock_getpass.return_value = "master_password"
    keystore = KeyStore(keys={"Anthropic": "sk-ant-new"})
    save_keystore(keystore)

    migrate_legacy_keys()

    captured = capsys.readouterr()
    assert "No legacy keys found to migrate" in captured.out


def test_migrate_legacy_keys_conflict(temp_pithy_dir, mock_getpass, capsys):
    """Test migration when both old and new keys exist."""
    mock_getpass.return_value = "master_password"
    keystore = KeyStore(keys={
        "Anthropic": "sk-ant-new",
        "ANTHROPIC_API_KEY": "sk-ant-old"
    })
    save_keystore(keystore)

    migrate_legacy_keys()

    captured = capsys.readouterr()
    assert "Both ANTHROPIC_API_KEY and Anthropic exist" in captured.out
    assert "Keeping Anthropic, removing ANTHROPIC_API_KEY" in captured.out

    # Verify new key is kept, legacy is removed
    keystore = load_keystore()
    assert "Anthropic" in keystore.keys
    assert "ANTHROPIC_API_KEY" not in keystore.keys
    assert keystore.keys["Anthropic"] == "sk-ant-new"


def test_migrate_legacy_keys_no_keystore(temp_pithy_dir, capsys):
    """Test migration when no keystore exists."""
    # Don't create a keystore - temp_pithy_dir is empty
    migrate_legacy_keys()

    captured = capsys.readouterr()
    # When no keystore file exists, load_keystore() returns empty KeyStore
    # So migration just says no legacy keys found
    assert "No legacy keys found to migrate" in captured.out