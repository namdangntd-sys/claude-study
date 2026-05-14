"""Lark Calendar -> Google Calendar one-way sync.

Run modes:
    python sync.py --list-calendars      # show Lark calendars (need scope first)
    python sync.py --auth-google         # one-time Google OAuth (opens browser)
    python sync.py                       # do a sync pass
    python sync.py --dry-run             # log what would happen, change nothing

Dedup strategy:
    Each Google event we create gets extendedProperties.private.larkEventId.
    On every pass we list the Google window, build {larkEventId: googleEventId},
    then for each Lark event:
        - missing in Google -> insert
        - present and lark.updated_time > google.updated -> patch
        - present in Google but not in Lark anymore -> delete

Caveats:
    - Uses tenant_access_token. The Lark app must be invited to the source
      calendar (Lark Calendar UI -> Share -> add the bot).
    - Attendees are NOT copied (avoids re-inviting people).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

LARK_BASE = os.environ.get("LARK_BASE_URL", "https://open.larksuite.com").rstrip("/")
APP_ID = os.environ["LARK_APP_ID"]
APP_SECRET = os.environ["LARK_APP_SECRET"]
LARK_CAL_ID = os.environ.get("LARK_CALENDAR_ID", "")
GOOGLE_CAL_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
DAYS_PAST = int(os.environ.get("SYNC_DAYS_PAST", "7"))
DAYS_FUTURE = int(os.environ.get("SYNC_DAYS_FUTURE", "60"))
LOG_PATH = os.environ.get("LOG_PATH", str(HERE / "sync.log"))

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_CRED_PATH = HERE / "google_credentials.json"
GOOGLE_TOKEN_PATH = HERE / "google_token.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("lark2gcal")


# ---------- Lark side ----------

_lark_token: dict[str, Any] = {"value": None, "exp": 0.0}


def lark_token() -> str:
    now = time.time()
    if _lark_token["value"] and _lark_token["exp"] > now + 60:
        return _lark_token["value"]
    r = httpx.post(
        f"{LARK_BASE}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"Lark auth failed: {d}")
    _lark_token["value"] = d["tenant_access_token"]
    _lark_token["exp"] = now + int(d.get("expire", 7200))
    return _lark_token["value"]


def lark_get(path: str, params: dict | None = None) -> dict:
    r = httpx.get(
        f"{LARK_BASE}{path}",
        headers={"Authorization": f"Bearer {lark_token()}"},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"Lark API {path} failed: {d}")
    return d.get("data", {})


def lark_list_calendars() -> list[dict]:
    data = lark_get("/open-apis/calendar/v4/calendars")
    return data.get("calendar_list", [])


def lark_list_events(cal_id: str, start_ts: int, end_ts: int) -> list[dict]:
    events: list[dict] = []
    page_token = ""
    while True:
        params = {
            "start_time": str(start_ts),
            "end_time": str(end_ts),
            "page_size": 500,
        }
        if page_token:
            params["page_token"] = page_token
        data = lark_get(f"/open-apis/calendar/v4/calendars/{cal_id}/events", params)
        events.extend(data.get("items", []))
        page_token = data.get("page_token", "")
        if not page_token:
            break
    return events


# ---------- Google side ----------


def google_service():
    creds = None
    if GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), GOOGLE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not GOOGLE_CRED_PATH.exists():
                raise SystemExit(
                    f"Missing {GOOGLE_CRED_PATH}. Download OAuth client JSON from "
                    "Google Cloud Console and save it there. See README."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CRED_PATH), GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def google_list_synced(svc, cal_id: str, time_min_iso: str, time_max_iso: str) -> dict[str, dict]:
    """Return {larkEventId: google_event_dict} for events we've synced before."""
    out: dict[str, dict] = {}
    page_token = None
    while True:
        resp = svc.events().list(
            calendarId=cal_id,
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            privateExtendedProperty="syncSource=lark",
            singleEvents=False,
            showDeleted=False,
            pageToken=page_token,
            maxResults=2500,
        ).execute()
        for ev in resp.get("items", []):
            lark_id = ev.get("extendedProperties", {}).get("private", {}).get("larkEventId")
            if lark_id:
                out[lark_id] = ev
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


# ---------- Mapping ----------


def lark_to_google(lark_ev: dict) -> dict:
    summary = lark_ev.get("summary") or "(no title)"
    description = lark_ev.get("description") or ""
    location = (lark_ev.get("location") or {}).get("name", "")

    body: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "extendedProperties": {
            "private": {
                "syncSource": "lark",
                "larkEventId": lark_ev["event_id"],
                "larkUpdated": str(lark_ev.get("event_organizer", {}).get("update_time")
                                   or lark_ev.get("update_time", "")),
            }
        },
    }
    if location:
        body["location"] = location

    start = lark_ev.get("start_time") or {}
    end = lark_ev.get("end_time") or {}
    tz = start.get("timezone") or "Asia/Ho_Chi_Minh"

    if start.get("date"):  # all-day event
        body["start"] = {"date": start["date"]}
        body["end"] = {"date": end.get("date")}
    else:
        start_dt = datetime.fromtimestamp(int(start["timestamp"]), tz=timezone.utc)
        end_dt = datetime.fromtimestamp(int(end["timestamp"]), tz=timezone.utc)
        body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": tz}
        body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": tz}

    return body


def needs_update(lark_ev: dict, google_ev: dict) -> bool:
    last = google_ev.get("extendedProperties", {}).get("private", {}).get("larkUpdated", "")
    cur = str(lark_ev.get("event_organizer", {}).get("update_time")
              or lark_ev.get("update_time", ""))
    return cur != last


# ---------- Sync ----------


def sync_pass(dry_run: bool = False) -> None:
    if not LARK_CAL_ID:
        raise SystemExit("LARK_CALENDAR_ID not set in .env. Run with --list-calendars first.")

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=DAYS_PAST)
    end = now + timedelta(days=DAYS_FUTURE)

    log.info("Sync window: %s -> %s", start.isoformat(), end.isoformat())

    lark_events = lark_list_events(LARK_CAL_ID, int(start.timestamp()), int(end.timestamp()))
    log.info("Lark returned %d events", len(lark_events))

    svc = google_service()
    google_synced = google_list_synced(svc, GOOGLE_CAL_ID, start.isoformat(), end.isoformat())
    log.info("Google has %d previously-synced events in window", len(google_synced))

    lark_ids_seen: set[str] = set()
    inserts = updates = deletes = skipped = 0

    for ev in lark_events:
        if ev.get("status") == "cancelled":
            continue
        lark_id = ev["event_id"]
        lark_ids_seen.add(lark_id)
        body = lark_to_google(ev)

        if lark_id not in google_synced:
            if dry_run:
                log.info("[dry] INSERT %s :: %s", lark_id, body["summary"])
            else:
                try:
                    svc.events().insert(calendarId=GOOGLE_CAL_ID, body=body).execute()
                    log.info("INSERT %s :: %s", lark_id, body["summary"])
                except HttpError as e:
                    log.error("INSERT failed for %s: %s", lark_id, e)
            inserts += 1
        elif needs_update(ev, google_synced[lark_id]):
            gid = google_synced[lark_id]["id"]
            if dry_run:
                log.info("[dry] UPDATE %s :: %s", lark_id, body["summary"])
            else:
                try:
                    svc.events().patch(calendarId=GOOGLE_CAL_ID, eventId=gid, body=body).execute()
                    log.info("UPDATE %s :: %s", lark_id, body["summary"])
                except HttpError as e:
                    log.error("UPDATE failed for %s: %s", lark_id, e)
            updates += 1
        else:
            skipped += 1

    for lark_id, gev in google_synced.items():
        if lark_id not in lark_ids_seen:
            if dry_run:
                log.info("[dry] DELETE %s :: %s", lark_id, gev.get("summary"))
            else:
                try:
                    svc.events().delete(calendarId=GOOGLE_CAL_ID, eventId=gev["id"]).execute()
                    log.info("DELETE %s :: %s", lark_id, gev.get("summary"))
                except HttpError as e:
                    log.error("DELETE failed for %s: %s", lark_id, e)
            deletes += 1

    log.info("Done. inserts=%d updates=%d deletes=%d skipped=%d",
             inserts, updates, deletes, skipped)


# ---------- CLI ----------


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list-calendars", action="store_true")
    p.add_argument("--auth-google", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.list_calendars:
        cals = lark_list_calendars()
        if not cals:
            print("No calendars visible. The bot must be added to a calendar via Share.")
            return 1
        for c in cals:
            print(f"{c.get('calendar_id')}\t{c.get('summary')}\trole={c.get('role')}")
        return 0

    if args.auth_google:
        google_service()
        log.info("Google auth saved to %s", GOOGLE_TOKEN_PATH)
        return 0

    sync_pass(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
