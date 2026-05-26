#!/usr/bin/env python3
"""
Discovery script — find your calendar ID and label IDs.

Usage:
    python discover.py

Set TIMETREE_EMAIL and TIMETREE_PASSWORD in your .env file first.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv()
except ImportError:
    # Manual .env loading as fallback
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, str(Path(__file__).parent))
from timetree import TimeTreeClient  # type: ignore


def main() -> None:
    email = os.environ.get("TIMETREE_EMAIL", "")
    password = os.environ.get("TIMETREE_PASSWORD", "")

    if not email or not password:
        print("❌ Set TIMETREE_EMAIL and TIMETREE_PASSWORD in .env first")
        print("   Copy .env.example to .env and fill in your values")
        sys.exit(1)

    client = TimeTreeClient()
    print(f"🔐 Logging in as {email}...")
    client.signin(email, password)
    print("✅ Login successful!\n")

    # Show calendars
    calendars = client.get_calendars()
    print(f"📅 Found {len(calendars)} calendar(s):\n")
    for cal in calendars:
        members = client.get_calendar_users(cal.id)
        member_names = ", ".join(m.name for m in members)
        print(f'  Calendar: "{cal.name}"')
        print(f"  ID:       {cal.id}")
        print(f"  Code:     {cal.alias_code}")
        print(f"  Members:  {member_names}")

        # Fetch events and show which label IDs are in use
        try:
            events = client.get_events_sync(cal.id)
        except Exception as e:
            print(f"  ⚠️  Could not fetch events: {e}")
            print()
            continue

        # Count events per label
        label_counts: dict[int, list[str]] = {}
        now = datetime.now(timezone.utc)
        for event in events:
            label_counts.setdefault(event.label_id, []).append(event.title)

        if label_counts:
            print(f"  Labels used ({len(events)} events total):")
            for label_id in sorted(label_counts.keys()):
                titles = label_counts[label_id]
                example = titles[0] if titles else ""
                print(
                    f'    label_id={label_id}: {len(titles)} events (e.g. "{example}")'
                )
        else:
            print("  No events found.")

        # Show upcoming events
        upcoming = [e for e in events if e.start_at and e.start_at > now][:5]
        if upcoming:
            print(f"  Next {len(upcoming)} upcoming events:")
            for e in upcoming:
                start = e.start_at.strftime("%Y-%m-%d %H:%M") if e.start_at else "???"
                print(f'    {start} | label_id={e.label_id} | "{e.title}"')

        print()

    print("💡 To use photo-reminder, set these in your .env:")
    print("   CALENDAR_ID=<id from above>")
    print('   TARGET_LABEL_IDS=<label_id that means "photo-worthy">')
    print()
    print("   Example:")
    print("   CALENDAR_ID=12345")
    print("   TARGET_LABEL_IDS=3")


if __name__ == "__main__":
    main()
