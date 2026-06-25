"""Tenant authentication for audiobook routes."""

from dataclasses import dataclass
from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException

from app.config import settings


@dataclass(frozen=True)
class BookPrincipal:
    owner_id: str


def _configured_tokens() -> dict[str, str]:
    tokens: dict[str, str] = {}
    for item in settings.book_auth_tokens.split(","):
        if not item.strip():
            continue
        if ":" in item:
            sep = ":"
        elif "=" in item:
            sep = "="
        else:
            continue
        owner, token = item.split(sep, 1)
        if owner.strip() and token.strip():
            tokens[owner.strip()] = token.strip()
    return tokens


def require_book_principal(
    x_book_owner: Annotated[str | None, Header(alias="X-Book-Owner")] = None,
    x_book_token: Annotated[str | None, Header(alias="X-Book-Token")] = None,
) -> BookPrincipal:
    owner_id = (x_book_owner or "").strip()
    token = (x_book_token or "").strip()
    expected = _configured_tokens().get(owner_id)
    if not owner_id or not expected or not compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Not authorized")
    return BookPrincipal(owner_id=owner_id)
