"""Parsing helpers for BOOK_AUTH_TOKENS."""


def _parse_book_auth_entry(value: str) -> tuple[str, str] | None:
    item = value.strip()
    if not item:
        return None
    if ":" in item:
        sep = ":"
    elif "=" in item:
        sep = "="
    else:
        return None
    owner, token = item.split(sep, 1)
    owner = owner.strip()
    token = token.strip()
    if not owner or not token:
        return None
    return owner, token


def parse_book_auth_tokens(value: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for item in value.split(","):
        parsed = _parse_book_auth_entry(item)
        if parsed is None:
            continue
        owner, token = parsed
        tokens[owner] = token
    return tokens


def book_auth_tokens_are_valid(value: str) -> bool:
    entries = [item for item in value.split(",") if item.strip()]
    return bool(entries) and all(
        _parse_book_auth_entry(item) is not None for item in entries
    )
