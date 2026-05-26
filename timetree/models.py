from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _ms_to_dt(ms: int | None) -> datetime | None:
    """Convert a Unix millisecond timestamp to a datetime (UTC)."""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass
class User:
    id: int
    uuid: str
    name: str
    gender: str | None
    relationship: str | None
    birthday: datetime | None
    one_word: str
    created_at: datetime | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "User":
        return cls(
            id=d["id"],
            uuid=d["uuid"],
            name=d["name"],
            gender=d.get("gender"),
            relationship=d.get("relationship"),
            birthday=_ms_to_dt(d.get("birthday")),
            one_word=d.get("one_word", ""),
            created_at=_ms_to_dt(d.get("created_at")),
        )


@dataclass
class UserSetting:
    start_weekday: int
    lang: str
    military_time: bool
    holiday: bool
    holiday_countries: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UserSetting":
        return cls(
            start_weekday=d["start_weekday"],
            lang=d.get("lang", "ja"),
            military_time=d.get("military_time", False),
            holiday=d.get("holiday", True),
            holiday_countries=d.get("holiday_countries", []),
        )


@dataclass
class Calendar:
    id: int
    alias_code: str
    name: str
    author_id: int
    purpose: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Calendar":
        return cls(
            id=d["id"],
            alias_code=d.get("alias_code", ""),
            name=d["name"],
            author_id=d["author_id"],
            purpose=d.get("purpose"),
            created_at=_ms_to_dt(d.get("created_at")),
            updated_at=_ms_to_dt(d.get("updated_at")),
        )


@dataclass
class CalendarUser:
    id: int
    calendar_id: int
    user_id: int
    name: str
    role: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CalendarUser":
        return cls(
            id=d["id"],
            calendar_id=d["calendar_id"],
            user_id=d["user_id"],
            name=d.get("name", ""),
            role=d.get("role", 0),
        )


@dataclass
class Event:
    id: str
    calendar_id: int
    title: str
    all_day: bool
    start_at: datetime | None
    end_at: datetime | None
    start_timezone: str
    end_timezone: str
    label_id: int
    note: str
    location: str
    attendees: list[int]
    author_id: int
    created_at: datetime | None
    updated_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(
            id=d["id"],
            calendar_id=d["calendar_id"],
            title=d.get("title", ""),
            all_day=d.get("all_day", False),
            start_at=_ms_to_dt(d.get("start_at")),
            end_at=_ms_to_dt(d.get("end_at")),
            start_timezone=d.get("start_timezone", "UTC"),
            end_timezone=d.get("end_timezone", "UTC"),
            label_id=d.get("label_id", 1),
            note=d.get("note", ""),
            location=d.get("location", ""),
            attendees=d.get("attendees", []),
            author_id=d.get("author_id", 0),
            created_at=_ms_to_dt(d.get("created_at")),
            updated_at=_ms_to_dt(d.get("updated_at")),
            raw=d,
        )


@dataclass
class MemorialDay:
    date: str
    name: str
    country: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemorialDay":
        return cls(
            date=d.get("date", ""),
            name=d.get("name", ""),
            country=d.get("country", ""),
        )
