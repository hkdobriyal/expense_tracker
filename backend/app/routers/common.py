"""Helpers shared by routers."""

from __future__ import annotations

from ..deps import CurrentUser
from ..services.context import UserContext


def ctx_of(current: CurrentUser) -> UserContext:
    return UserContext(current.user.id, current.settings.base_currency, current.settings.timezone, current.settings.week_start, current.settings, current.user.is_demo)
