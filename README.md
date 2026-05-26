# 📸 Photo Reminder

Sends push notifications during TimeTree calendar events so you remember to take photos.

Polls your TimeTree shared calendar, filters events by label (event type), and sends beautiful push notifications to your phone via [ntfy.sh](https://ntfy.sh) during those events.

**Free. No iOS app to build. Works in 15 minutes.**

---

## How It Works

```
TimeTree ← (unofficial web API) ← Python script (every 15 min) → ntfy.sh → Your Phones
```

1. Script logs in to TimeTree, fetches your calendar events
2. Filters to events matching your target label (e.g. "🎉 Celebrations")
3. For events happening *right now*, sends a push via ntfy.sh
4. You tap the notification → it opens your Photos app
5. Takes a photo. Memory captured. 🎉

Notifications repeat every 30 minutes during long events (configurable).

---

## Quick Start

### 1. Install ntfy on your phones

- **iOS**: [App Store](https://apps.apple.com/us/app/ntfy/id1625396347)
- **Android**: [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy)

Open the app, tap **+**, subscribe to a topic name (make it unguessable, like `our-photo-remind-k7x9m2`). Both phones subscribe to the **same topic**.

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` — you need your TimeTree email/password. Leave `CALENDAR_ID` and `TARGET_LABEL_IDS` blank for now.

### 3. Install dependencies & discover your calendar IDs

```bash
# Requires uv: https://docs.astral.sh/uv/getting-started/installation/
uv sync

# Find your calendar and label IDs
uv run discover.py
```

This prints your calendars, their IDs, and which label IDs are in use. Fill those into `.env`:

```
CALENDAR_ID=12345
TARGET_LABEL_IDS=3
```

### 4. Test locally

```bash
uv run main.py
```

Check the logs — if there's a matching event happening now, you'll get a push notification.

### 5. Deploy to Fly.io

```bash
# Install fly CLI: https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# Create the app
fly apps create photo-reminder

# Create a 1GB persistent volume (for state file)
fly volumes create photo_reminder_data --size 1

# Set secrets (your credentials)
fly secrets set TIMETREE_EMAIL=you@example.com
fly secrets set TIMETREE_PASSWORD=yourpassword
fly secrets set CALENDAR_ID=12345
fly secrets set TARGET_LABEL_IDS=3
fly secrets set NTFY_TOPIC=our-photo-remind-k7x9m2

# Deploy
fly deploy

# Schedule to run every 15 minutes
fly machines list  # copy the machine ID
fly machines schedule <machine-id> "*/15 * * * *"
```

Done. The machine wakes up every 15 min, checks TimeTree, sends notifications if needed, then goes back to sleep.

**Cost: $0** — Fly.io free tier handles this easily.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TIMETREE_EMAIL` | ✅ | — | Your TimeTree login email |
| `TIMETREE_PASSWORD` | ✅ | — | Your TimeTree password |
| `CALENDAR_ID` | ✅ | — | Numeric calendar ID (find with `discover.py`) |
| `TARGET_LABEL_IDS` | ✅ | `1` | Comma-separated label IDs to match |
| `NTFY_TOPIC` | ✅ | — | ntfy topic name (both phones subscribe to this) |
| `NTFY_SERVER` | ❌ | `https://ntfy.sh` | ntfy server URL (self-hostable) |
| `NTFY_CLICK_URL` | ❌ | `photos-redirect://` | URL opened when notification is tapped |
| `REMINDER_INTERVAL_MIN` | ❌ | `30` | Minutes between repeat reminders |
| `LOOKAHEAD_HOURS` | ❌ | `12` | How far ahead to check events |
| `LOCAL_TZ_OFFSET_HOURS` | ❌ | `0` | Your UTC offset (e.g. `-5` for EST) |
| `STATE_FILE` | ❌ | `/tmp/...` | Path to state file |
| `LOG_LEVEL` | ❌ | `INFO` | Logging verbosity |

---

## Notification Tap Actions

The `NTFY_CLICK_URL` controls what happens when you tap the notification:

| URL | Behavior |
|---|---|
| `photos-redirect://` | Opens iOS Photos app |
| `shortcuts://run-shortcut?name=TakePhoto` | Runs an iOS Shortcut (e.g. open camera) |
| `https://...` | Opens any URL in Safari |

To create a "Take Photo" shortcut that opens the camera directly:
1. Open the **Shortcuts** app on iPhone
2. Create a new shortcut named "TakePhoto"
3. Add action: **Take Photo** (from Camera)
4. Done — now `shortcuts://run-shortcut?name=TakePhoto` will open the camera

---

## Architecture

```
outpost/
├── main.py              # Main check cycle — run once per invocation
├── discover.py          # Helper to find your calendar & label IDs
├── pyproject.toml       # Project config & deps (uv)
├── uv.lock              # Locked dependencies
├── Dockerfile           # Container for Fly.io (uses uv)
├── fly.toml             # Fly.io config
├── .env.example         # Template for environment variables
├── .gitignore
└── timetree/            # Vendored unofficial TimeTree web API client
    ├── __init__.py
    ├── client.py
    ├── models.py
    └── exceptions.py
```

The TimeTree client is vendored from [github.com/Tiv122530/timetree](https://github.com/Tiv122530/timetree). It uses the TimeTree web API endpoints directly.

---

## How State Works

The script tracks which notifications it has already sent in a JSON state file. Each event gets divided into "slots" of `REMINDER_INTERVAL_MIN` minutes. Once a slot is notified, it won't notify again.

Example with 30-min intervals for a 2-hour event:
- Slot 0 (0–30 min) → notification sent ✅
- Slot 1 (30–60 min) → notification sent ✅
- Slot 2 (60–90 min) → notification sent ✅
- Slot 3 (90–120 min) → notification sent ✅

Old state entries (>48h) are automatically pruned.

---

## ⚠️ Important Notes

- **Unofficial API**: TimeTree has no public API. This uses reverse-engineered web endpoints. They *could* break if TimeTree changes their web app. In practice, these endpoints are stable since the web app depends on them.
- **Personal use only**: This is for your own calendar data. Don't distribute as a service to others.
- **Rate limiting**: 15-minute poll interval is conservative. Don't lower it below 5 minutes.
- **All-day events**: These are treated as photo-worthy for the entire day (midnight to midnight).

---

## License

MIT. The vendored TimeTree client is also MIT-ish (unofficial, use at your own risk).
