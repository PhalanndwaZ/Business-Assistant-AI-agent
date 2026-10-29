"""Hash and verify demo-account passwords with the recommended Argon2 method."""

from pwdlib import PasswordHash

PASSWORD_HASHER = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Return a salted Argon2 password hash."""
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches its stored hash."""
    return PASSWORD_HASHER.verify(password, password_hash)
