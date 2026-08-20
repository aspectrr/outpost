"""
TimeTree Photo Reminder
~~~~~~~~~~~~~~~~~~~~~~~
Polls TimeTree for events matching a specific label, then sends
push notifications via Bark during those events to remind
you and your partner to take photos.

Runs as a long-lived process on Fly.io, polling every N minutes.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
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
TIMETREE_EMAIL = os.environ["TIMETREE_EMAIL"]
TIMETREE_PASSWORD = os.environ["TIMETREE_PASSWORD"]
CALENDAR_ID = int(os.environ["CALENDAR_ID"])
TARGET_LABEL_IDS = [
    int(x) for x in os.environ.get("TARGET_LABEL_IDS", "1").split(",") if x.strip()
]
BARK_SERVER = os.environ.get("BARK_SERVER", "https://api.day.app")
BARK_KEYS = [k.strip() for k in os.environ["BARK_KEY"].split(",") if k.strip()]
BARK_GROUP = os.environ.get("BARK_GROUP", "Photo Reminder")
BARK_URL = os.environ.get("BARK_URL", "shortcuts://run-shortcut?name=TakePhoto")
REMINDER_INTERVAL_MIN = int(os.environ.get("REMINDER_INTERVAL_MIN", "45"))
LOOKAHEAD_HOURS = int(os.environ.get("LOOKAHEAD_HOURS", "12"))
POLL_INTERVAL_MIN = int(os.environ.get("POLL_INTERVAL_MIN", "15"))
STATE_FILE = Path(os.environ.get("STATE_FILE", "/tmp/photo-reminder-state.json"))
LOCAL_TZ_OFFSET_HOURS = int(os.environ.get("LOCAL_TZ_OFFSET_HOURS", "0"))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("photo-reminder")

# ── TimeTree client ──────────────────────────────────────────────────
from timetree import TimeTreeClient  # noqa: E402

# ── Graceful shutdown ─────────────────────────────────────────────────
_shutdown = False


def _handle_signal(signum: int, _frame: object) -> None:
    global _shutdown
    sig_name = signal.Signals(signum).name
    log.info("Received %s, shutting down after this cycle...", sig_name)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ── State management ──────────────────────────────────────────────────


def load_state() -> dict[str, str]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not read state file, starting fresh: %s", e)
    return {}


def save_state(state: dict[str, str]) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError as e:
        log.error("Could not save state file: %s", e)


def prune_old_state(state: dict[str, str]) -> dict[str, str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    return {k: v for k, v in state.items() if v > cutoff}


# ── Bark notification ──────────────────────────────────────────────────


def send_notification(event_title: str, start_str: str, end_str: str) -> bool:
    body = (
        f'"{event_title}" is happening right now.\n'
        f"{start_str} → {end_str}\n\n"
        f"Open your camera and capture the moment! 🎉"
    )
    success = True
    for key in BARK_KEYS:
        try:
            resp = requests.post(
                f"{BARK_SERVER}/{key}",
                json={
                    "title": "📸 Photo Reminder",
                    "body": body,
                    "group": BARK_GROUP,
                    "url": BARK_URL,
                    "sound": "alarm",
                    "level": "timeSensitive",
                },
                timeout=10,
            )
            resp.raise_for_status()
            log.info("Notification sent for: %s (key ...%s)", event_title, key[-6:])
        except requests.RequestException as e:
            log.error("Failed to send to key ...%s: %s", key[-6:], e)
            success = False
    return success


# ── Time helpers ──────────────────────────────────────────────────────


def make_local_tz() -> timezone:
    return timezone(timedelta(hours=LOCAL_TZ_OFFSET_HOURS))


def format_time(dt: datetime | None) -> str:
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
    client = TimeTreeClient()
    log.info("Logging in to TimeTree as %s", TIMETREE_EMAIL)
    client.signin(TIMETREE_EMAIL, TIMETREE_PASSWORD)

    log.info("Fetching events for calendar %d", CALENDAR_ID)
    events = client.get_events_sync(CALENDAR_ID)
    log.info("Fetched %d total events", len(events))

    matching = [e for e in events if e.label_id in TARGET_LABEL_IDS]
    log.info("Events matching label IDs %s: %d", TARGET_LABEL_IDS, len(matching))
    return matching


def process_events(events: list) -> int:
    """Check which events are happening now and send notifications. Returns count sent."""
    now = datetime.now(timezone.utc)
    state = prune_old_state(load_state())
    notified = 0

    for event in events:
        if event.all_day:
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

        if start > now + timedelta(hours=LOOKAHEAD_HOURS):
            continue

        if end < now:
            continue

        if start <= now <= end:
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
                if send_notification(event.title, format_time(start), format_time(end)):
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
    return notified


def run_check_cycle() -> None:
    """Single check cycle: fetch events, process, notify."""
    log.info("=== Check cycle starting ===")
    try:
        events = get_current_events()
        notified = process_events(events)
        log.info("=== Check cycle complete. Sent %d notifications. ===", notified)
    except Exception:
        log.exception("Error during check cycle (will retry next poll)")


def main() -> None:
    """Entry point — run polling loop forever."""
    log.info(
        "📸 Photo Reminder starting (polling every %d min, reminders every %d min)",
        POLL_INTERVAL_MIN,
        REMINDER_INTERVAL_MIN,
    )

    while not _shutdown:
        run_check_cycle()

        if _shutdown:
            break

        # Sleep in small chunks so we can respond to signals quickly
        sleep_secs = POLL_INTERVAL_MIN * 60
        log.info("Next check in %d minutes...", POLL_INTERVAL_MIN)
        for _ in range(sleep_secs):
            if _shutdown:
                break
            time.sleep(1)

    log.info("📸 Photo Reminder shut down cleanly.")


if __name__ == "__main__":
    main()
