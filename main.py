"""
TimeTree Photo Reminder
~~~~~~~~~~~~~~~~~~~~~~~
Polls TimeTree for events matching a specific label, then sends
push notifications via ntfy.sh during those events to remind
you and your partner to take photos.

Designed to run as a scheduled process on Fly.io (or any cron host).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# Load .env when running locally (Fly.io uses secrets instead)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────
# All config comes from env vars. See .env.example for descriptions.
TIMETREE_EMAIL = os.environ["TIMETREE_EMAIL"]
TIMETREE_PASSWORD = os.environ["TIMETREE_PASSWORD"]
CALENDAR_ID = int(os.environ["CALENDAR_ID"])
TARGET_LABEL_IDS = [
    int(x) for x in os.environ.get("TARGET_LABEL_IDS", "1").split(",") if x.strip()
]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
NTFY_CLICK_URL = os.environ.get(
    "NTFY_CLICK_URL", "shortcuts://run-shortcut?name=TakePhoto"
)
# How often (minutes) to send a repeat reminder during a single event
REMINDER_INTERVAL_MIN = int(os.environ.get("REMINDER_INTERVAL_MIN", "30"))
# How far ahead (hours) to look for events
LOOKAHEAD_HOURS = int(os.environ.get("LOOKAHEAD_HOURS", "12"))
# State file to track which reminders have already been sent
STATE_FILE = Path(os.environ.get("STATE_FILE", "/tmp/photo-reminder-state.json"))
# Timezone offset for your local time (e.g. "-5" for EST, "+1" for CET)
LOCAL_TZ_OFFSET_HOURS = int(os.environ.get("LOCAL_TZ_OFFSET_HOURS", "0"))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("photo-reminder")

# ── TimeTree client (vendored at ./timetree/) ─────────────────────────
from timetree import TimeTreeClient  # noqa: E402


# ── State management ──────────────────────────────────────────────────
# Track sent notifications as {"event_id:slot": timestamp}
# A "slot" is the reminder interval bucket, e.g. "0" for first 30 min, "1" for next 30, etc.


def load_state() -> dict[str, str]:
    """Load notification state from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not read state file, starting fresh: %s", e)
    return {}


def save_state(state: dict[str, str]) -> None:
    """Persist notification state to disk."""
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError as e:
        log.error("Could not save state file: %s", e)


def prune_old_state(state: dict[str, str]) -> dict[str, str]:
    """Remove entries older than 48 hours to keep state file small."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    return {k: v for k, v in state.items() if v > cutoff}


# ── ntfy notification ─────────────────────────────────────────────────


def send_notification(event_title: str, start_str: str, end_str: str) -> bool:
    """Send a push notification via ntfy.sh. Returns True on success."""
    body = (
        f"📸 Time to take photos!\n\n"
        f'"{event_title}" is happening right now.\n'
        f"{start_str} → {end_str}\n\n"
        f"Open your camera and capture the moment! 🎉"
    )
    try:
        resp = requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers={
                "Title": "Photo Reminder",
                "Priority": "high",
                "Tags": "camera,sparkles",
                "Click": NTFY_CLICK_URL,
            },
            timeout=10,
        )
        resp.raise_for_status()
        log.info("Notification sent for: %s", event_title)
        return True
    except requests.RequestException as e:
        log.error("Failed to send notification: %s", e)
        return False


# ── Time helpers ──────────────────────────────────────────────────────


def make_local_tz() -> timezone:
    """Create a fixed-offset timezone from LOCAL_TZ_OFFSET_HOURS."""
    return timezone(timedelta(hours=LOCAL_TZ_OFFSET_HOURS))


def format_time(dt: datetime | None) -> str:
    """Format a datetime for display in notifications."""
    if dt is None:
        return "???"
    local = dt.astimezone(make_local_tz())
    return (
        local.strftime("%-I:%M %p")
        if sys.platform != "win32"
        else local.strftime("%I:%M %p")
    )


# ── Main logic ────────────────────────────────────────────────────────


def get_current_events() -> list:
    """Fetch events from TimeTree, return those matching target labels."""
    client = TimeTreeClient()
    log.info("Logging in to TimeTree as %s", TIMETREE_EMAIL)
    client.signin(TIMETREE_EMAIL, TIMETREE_PASSWORD)

    log.info("Fetching events for calendar %d", CALENDAR_ID)
    events = client.get_events_sync(CALENDAR_ID)
    log.info("Fetched %d total events", len(events))

    # Filter to target labels only
    matching = [e for e in events if e.label_id in TARGET_LABEL_IDS]
    log.info(
        "Events matching label IDs %s: %d",
        TARGET_LABEL_IDS,
        len(matching),
    )
    return matching


def process_events(events: list) -> None:
    """Check which events are happening now and send notifications."""
    now = datetime.now(timezone.utc)
    state = prune_old_state(load_state())
    notified = 0

    for event in events:
        if event.all_day:
            # For all-day events, use the whole day
            start = (
                event.start_at.replace(hour=0, minute=0, second=0)
                if event.start_at
                else None
            )
            end = (
                event.end_at.replace(hour=23, minute=59, second=59)
                if event.end_at
                else None
            )
        else:
            start = event.start_at
            end = event.end_at

        if start is None or end is None:
            continue

        # Skip events that are too far in the future
        if start > now + timedelta(hours=LOOKAHEAD_HOURS):
            continue

        # Skip events that already ended
        if end < now:
            continue

        # Is this event happening right now?
        if start <= now <= end:
            # Calculate which reminder "slot" we're in
            minutes_in = (now - start).total_seconds() / 60
            slot = int(minutes_in // REMINDER_INTERVAL_MIN)
            state_key = f"{event.id}:{slot}"

            if state_key not in state:
                log.info(
                    "Event '%s' is active (slot %d, %.0f min in) — sending reminder",
                    event.title,
                    slot,
                    minutes_in,
                )
                if send_notification(
                    event.title,
                    format_time(start),
                    format_time(end),
                ):
                    state[state_key] = now.isoformat()
                    notified += 1
            else:
                log.debug(
                    "Event '%s' slot %d already notified at %s, skipping",
                    event.title,
                    slot,
                    state[state_key],
                )

    save_state(state)
    log.info("Run complete. Sent %d new notifications.", notified)


def main() -> None:
    """Entry point — run one check cycle."""
    log.info("=== Photo Reminder check starting ===")
    try:
        events = get_current_events()
        process_events(events)
    except Exception:
        log.exception("Fatal error during check cycle")
        sys.exit(1)
    log.info("=== Photo Reminder check complete ===")


if __name__ == "__main__":
    main()
