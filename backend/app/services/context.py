"""A light per-user context used by services that run both in requests and in the worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from ..models import User, UserSettings
from .periods import today_for


@dataclass
class UserContext:
    user_id: int
    base_currency: str
    timezone: str
    week_start: int
    settings: UserSettings
    is_demo: bool = False
    _today: date | None = None

    @property
    def today(self) -> date:
        return self._today or today_for(self.timezone)

    @classmethod
    def for_user(cls, db: Session, user: User, today: date | None = None) -> "UserContext":
        settings = user.settings
        if settings is None:
            settings = UserSettings(user_id=user.id)
            db.add(settings)
            db.flush()
        return cls(user.id, settings.base_currency, settings.timezone, settings.week_start, settings, user.is_demo, today)
