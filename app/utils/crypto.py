"""Credential encryption utilities using Fernet symmetric encryption."""

import os
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _get_key_path() -> Path:
    """Get path to the encryption key file in user's AppData."""
    app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    key_dir = app_data / "ServerC"
    key_dir.mkdir(parents=True, exist_ok=True)
    return key_dir / ".key"


def _get_or_create_key() -> bytes:
    """Get or create a machine-specific encryption key."""
    key_path = _get_key_path()
    if key_path.exists():
        return key_path.read_bytes()

    # Derive key from a random salt + machine-specific info
    salt = os.urandom(16)
    machine_id = (os.environ.get("COMPUTERNAME", "") + os.environ.get("USERNAME", "")).encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(machine_id + os.urandom(32)))

    key_path.write_bytes(salt + key)
    return salt + key


def _get_fernet() -> Fernet:
    """Get Fernet instance with the stored key."""
    raw = _get_or_create_key()
    # Salt is first 16 bytes, key is the rest
    key = raw[16:]
    return Fernet(key)


def encrypt_password(password: str) -> str:
    """Encrypt a password string. Returns base64-encoded encrypted text."""
    f = _get_fernet()
    return f.encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_password(encrypted: str) -> str:
    """Decrypt an encrypted password string."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")
