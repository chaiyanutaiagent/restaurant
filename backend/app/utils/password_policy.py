from __future__ import annotations


PLATFORM_PASSWORD_MIN_LENGTH = 8
PLATFORM_PASSWORD_MAX_LENGTH = 128


def validate_platform_password(password: str) -> str:
    """Validate credentials used by Platform owners and operators."""
    errors: list[str] = []
    if len(password) < PLATFORM_PASSWORD_MIN_LENGTH:
        errors.append(f"at least {PLATFORM_PASSWORD_MIN_LENGTH} characters")
    if len(password) > PLATFORM_PASSWORD_MAX_LENGTH:
        errors.append(f"at most {PLATFORM_PASSWORD_MAX_LENGTH} characters")
    if not any(character.isupper() for character in password):
        errors.append("an uppercase letter")
    if not any(character.islower() for character in password):
        errors.append("a lowercase letter")
    if not any(character.isdigit() for character in password):
        errors.append("a number")
    if not any(not character.isalnum() and not character.isspace() for character in password):
        errors.append("a special character")
    if any(character.isspace() for character in password):
        errors.append("no whitespace")
    if errors:
        raise ValueError("Platform password must contain " + ", ".join(errors))
    return password
