#!/usr/bin/env python3
"""Send a test notification via Bark to all configured keys."""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import requests

BARK_SERVER = os.environ.get("BARK_SERVER", "https://api.day.app")
BARK_KEYS = [k.strip() for k in os.environ.get("BARK_KEY", "").split(",") if k.strip()]

if not BARK_KEYS:
    sys.exit("Error: BARK_KEY not set. Check .env or environment.")

for i, key in enumerate(BARK_KEYS, 1):
    print(f"[{i}/{len(BARK_KEYS)}] Sending to key ...{key[-6:]} ...")
    resp = requests.post(
        f"{BARK_SERVER}/{key}",
        json={
            "title": "Outpost Test",
            "body": "Test notification from outpost ✅",
            "group": "Photo Reminder",
            "sound": "alarm",
        },
        timeout=10,
    )
    print(f"  Status: {resp.status_code} {resp.reason} — {resp.text.strip()}")
