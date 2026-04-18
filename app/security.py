from __future__ import annotations

import hashlib
import hmac
import secrets


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
MIN_PASSWORD_LENGTH = 10


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters.")
    if password.lower() == password or password.upper() == password:
        raise ValueError("Password must mix upper- and lower-case characters.")
    if not any(character.isdigit() for character in password):
        raise ValueError("Password must include at least one digit.")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n_value, r_value, p_value, salt_hex, digest_hex = encoded_hash.split("$", maxsplit=5)
        if algorithm != "scrypt":
            return False
        candidate_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_value),
            r=int(r_value),
            p=int(p_value),
        )
    except Exception:
        return False

    return hmac.compare_digest(candidate_digest.hex(), digest_hex)


def generate_bootstrap_password() -> str:
    return secrets.token_urlsafe(12)
