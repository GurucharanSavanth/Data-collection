from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from constants import RECORD_STATUSES, ROLE_ORDER, SOURCE_MODES


LOGIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")
APPLICATION_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{3,64}$")
PHONE_PATTERN = re.compile(r"^[0-9+\-\s()]{7,20}$")


def normalize_login_id(value: str) -> str:
    return value.strip()


def validate_login_id(value: str) -> str:
    normalized = normalize_login_id(value)
    if not LOGIN_ID_PATTERN.fullmatch(normalized):
        raise ValueError("Login ID must be 3-64 characters and contain only letters, digits, '.', '_', '-', or '@'.")
    return normalized


def normalize_role(value: str) -> str:
    return value.strip().upper()


def validate_role(value: str) -> str:
    normalized = normalize_role(value)
    if normalized not in ROLE_ORDER:
        raise ValueError(f"Unsupported role: {value}")
    return normalized


def validate_phone_number(value: str, allow_empty: bool = False) -> str:
    normalized = value.strip()
    if not normalized and allow_empty:
        return ""
    if not PHONE_PATTERN.fullmatch(normalized):
        raise ValueError("Phone number must contain 7-20 supported characters.")
    digit_count = len(re.sub(r"\D", "", normalized))
    if digit_count < 7 or digit_count > 15:
        raise ValueError("Phone number must contain between 7 and 15 digits.")
    return normalized


def validate_application_number(value: str) -> str:
    normalized = value.strip()
    if not APPLICATION_NUMBER_PATTERN.fullmatch(normalized):
        raise ValueError("Application Number must be 3-64 characters and may only use letters, digits, '.', '_', '/', or '-'.")
    return normalized


def validate_status(value: str) -> str:
    normalized = value.strip()
    if normalized not in RECORD_STATUSES:
        raise ValueError(f"Status must be one of: {', '.join(RECORD_STATUSES)}")
    return normalized


def compose_title(display_name: str, deployed_location: str) -> str:
    name = display_name.strip()
    location = deployed_location.strip()
    if name and location:
        return f"{name} : {location}"
    return name or location


def validate_source_mode(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in SOURCE_MODES:
        raise ValueError("Credential source mode must be OFFLINE or ONLINE.")
    return normalized


def validate_source_reference(source_mode: str, local_path: str, remote_url: str) -> str:
    mode = validate_source_mode(source_mode)
    if mode == "OFFLINE":
        normalized_path = local_path.strip()
        if not normalized_path:
            raise ValueError("Offline (Path) mode requires a local CSV path.")
        if not Path(normalized_path).exists():
            raise ValueError("Offline credential source path does not exist.")
        return normalized_path

    normalized_url = remote_url.strip()
    if not normalized_url:
        raise ValueError("Online (URL) mode requires a remote CSV URL.")
    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Online credential source URL must be a valid http(s) URL.")
    return normalized_url


def ensure_candidate_referral(login_id: str, referral_code: str | None) -> str:
    candidate_referral = (referral_code or login_id).strip()
    if candidate_referral != login_id:
        raise ValueError("Candidate referral code must match login ID.")
    return candidate_referral
