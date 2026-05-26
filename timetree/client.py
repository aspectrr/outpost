"""TimeTree unofficial client.

Authentication flow
-------------------
1. GET https://timetreeapp.com/signin  →  extract CSRF token from <meta> tag
2. PUT /api/v1/auth/email/signin       →  log in with email + password
3. All subsequent requests carry the session Cookie and x-csrf-token header.

Vendored from: https://github.com/Tiv122530/timetree
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

import requests

from .exceptions import AuthError, NotFoundError, RateLimitError, TimeTreeError
from .models import (
    Calendar,
    CalendarUser,
    Event,
    MemorialDay,
    User,
    UserSetting,
)

_BASE = "https://timetreeapp.com"
_HEADERS = {
    "x-timetreea": "web/2.1.0/ja",
    "content-type": "application/json",
}


def _raise_for_status(resp: requests.Response) -> None:
    code = resp.status_code
    if code == 200 or code == 204:
        return
    try:
        msg = resp.json()
    except Exception:
        msg = resp.text
    if code == 400 or code == 401 or code == 403:
        raise AuthError(str(msg), status_code=code)
    if code == 404:
        raise NotFoundError(str(msg), status_code=code)
    if code == 429:
        raise RateLimitError(str(msg), status_code=code)
    raise TimeTreeError(str(msg), status_code=code)


class TimeTreeClient:
    """Unofficial client for the TimeTree web API.

    Usage::

        client = TimeTreeClient()
        client.signin("you@example.com", "yourpassword")
        calendars = client.get_calendars()
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._csrf_token: str = ""
        self._device_uuid: str = str(uuid.uuid4()).replace("-", "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_csrf_token(self) -> str:
        resp = self._session.get(f"{_BASE}/signin?locale=ja")
        resp.raise_for_status()
        match = re.search(
            r'<meta\s+name=["\']csrf-token["\']\s+content=["\'](.*?)["\']',
            resp.text,
        )
        if not match:
            raise TimeTreeError("CSRF token not found in signin page.")
        return match.group(1)

    def _set_csrf(self, token: str) -> None:
        self._csrf_token = token
        self._session.headers["x-csrf-token"] = token

    def _get(self, path: str, **kwargs: Any) -> Any:
        resp = self._session.get(f"{_BASE}{path}", **kwargs)
        _raise_for_status(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def _put(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        resp = self._session.put(f"{_BASE}{path}", json=json, **kwargs)
        _raise_for_status(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def _post(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        resp = self._session.post(f"{_BASE}{path}", json=json, **kwargs)
        _raise_for_status(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def _delete(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        resp = self._session.delete(f"{_BASE}{path}", json=json, **kwargs)
        _raise_for_status(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def signin(self, email: str, password: str) -> dict[str, Any]:
        csrf = self._get_csrf_token()
        self._set_csrf(csrf)
        body = {
            "uid": email,
            "password": password,
            "uuid": self._device_uuid,
        }
        resp = self._session.put(f"{_BASE}/api/v1/auth/email/signin", json=body)
        _raise_for_status(resp)
        data = resp.json()
        new_csrf = resp.headers.get("x-csrf-token")
        if new_csrf:
            self._set_csrf(new_csrf)
        return data

    def get_auth_info(self) -> dict[str, Any]:
        return self._get("/api/v1/auths")

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    def get_user(self) -> User:
        data = self._get("/api/v1/user")
        return User.from_dict(data["user"])

    def get_user_setting(self) -> UserSetting:
        data = self._get("/api/v1/user/setting")
        return UserSetting.from_dict(data["user_setting"])

    # ------------------------------------------------------------------
    # Calendars
    # ------------------------------------------------------------------

    def get_calendars(self) -> list[Calendar]:
        data = self._get("/api/v2/calendars")
        return [Calendar.from_dict(c) for c in data.get("calendars", [])]

    def get_calendar_users(self, calendar_id: int) -> list[CalendarUser]:
        data = self._get(f"/api/v2/calendars/{calendar_id}/users")
        return [CalendarUser.from_dict(u) for u in data.get("calendar_users", [])]

    def mark_calendar_read(self, calendar_id: int) -> None:
        self._put(f"/api/v1/calendar/{calendar_id}/mark")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def get_events_sync(self, calendar_id: int) -> list[Event]:
        data = self._get(f"/api/v1/calendar/{calendar_id}/events/sync")
        return [Event.from_dict(e) for e in data.get("events", [])]

    def get_events(
        self, calendar_id: int, since: int | None = None
    ) -> tuple[list[Event], int]:
        params: dict[str, Any] = {}
        if since is not None:
            params["since"] = since
        data = self._get(
            f"/api/v1/calendar/{calendar_id}/events", params=params
        )
        events = [Event.from_dict(e) for e in data.get("events", [])]
        next_since: int = data.get("since", since or 0)
        return events, next_since

    def create_event(
        self,
        calendar_id: int,
        title: str,
        start_at: datetime,
        end_at: datetime,
        *,
        all_day: bool = False,
        label_id: int = 1,
        note: str = "",
        location: str = "",
        attendees: list[int] | None = None,
        start_timezone: str = "Asia/Tokyo",
        end_timezone: str = "Asia/Tokyo",
    ) -> Event:
        def _to_ms(dt: datetime) -> int:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)

        body: dict[str, Any] = {
            "title": title,
            "all_day": all_day,
            "start_at": _to_ms(start_at),
            "start_timezone": start_timezone,
            "end_at": _to_ms(end_at),
            "end_timezone": end_timezone,
            "label_id": label_id,
            "note": note,
            "location": location,
            "attendees": attendees or [],
            "recurrences": [],
            "alerts": [],
            "attachment": {"virtual_user_attendees": []},
            "category": 1,
        }
        data = self._post(f"/api/v1/calendar/{calendar_id}/event", json=body)
        return Event.from_dict(data["event"])

    def delete_event(self, calendar_id: int, event_id: str) -> None:
        self._delete(f"/api/v1/calendar/{calendar_id}/event/{event_id}")

    def get_event_activities(
        self, calendar_id: int, event_id: str
    ) -> list[dict[str, Any]]:
        data = self._get(
            f"/api/v1/calendar/{calendar_id}/event/{event_id}/activities"
        )
        return data.get("event_activities", [])

    # ------------------------------------------------------------------
    # Memorial days (public holidays)
    # ------------------------------------------------------------------

    def get_memorial_days(
        self,
        from_date: datetime,
        to_date: datetime,
        countries: list[str] | None = None,
    ) -> list[MemorialDay]:
        if countries is None:
            countries = ["JP"]
        params: dict[str, Any] = {
            "country_iso[]": countries,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        data = self._get("/api/v2/memorialdays", params=params)
        return [MemorialDay.from_dict(d) for d in data.get("memorial_days", [])]
