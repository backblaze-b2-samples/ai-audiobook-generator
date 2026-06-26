"""Tenant authentication for audiobook routes."""

from dataclasses import dataclass
from functools import lru_cache
from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException

from app.config import settings
from app.config.book_auth_tokens import parse_book_auth_tokens


@dataclass(frozen=True)
class BookPrincipal:
    owner_id: str


@lru_cache(maxsize=1)
def _configured_tokens() -> dict[str, str]:
    return parse_book_auth_tokens(settings.book_auth_tokens)


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
