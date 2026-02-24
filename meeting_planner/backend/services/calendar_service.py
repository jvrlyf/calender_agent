"""
Google Calendar API wrapper with mock fallback.
"""

from __future__ import annotations
import os, json, uuid
from datetime import datetime, timedelta

from config import settings
from utils import get_logger

log = get_logger("services.calendar")


def _build_real_service():
    """Build authenticated Google Calendar service."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(settings.GOOGLE_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(
                settings.GOOGLE_TOKEN_FILE, settings.GOOGLE_SCOPES
            )
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    settings.GOOGLE_CREDENTIALS_FILE, settings.GOOGLE_SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(settings.GOOGLE_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        return build("calendar", "v3", credentials=creds)
    except Exception as exc:
        log.error("Google Calendar auth failed: %s", exc)
        return None


class CalendarService:
    """Thin wrapper – delegates to Google API or mock."""

    def __init__(self):
        if settings.MOCK_CALENDAR:
            log.info("Calendar running in MOCK mode")
            self._svc = None
        else:
            self._svc = _build_real_service()

    # ── create ────────────────────────────────────────
    def create_event(
        self,
        title: str,
        start_dt: str,
        end_dt: str,
        timezone: str,
        participants: list[str],
        description: str = "",
    ) -> dict:
        if self._svc is None:
            return self._mock_create(title, start_dt, end_dt, timezone, participants, description)

        try:
            body = {
                "summary": title,
                "description": description,
                "start": {"dateTime": start_dt, "timeZone": timezone},
                "end": {"dateTime": end_dt, "timeZone": timezone},
                "attendees": [{"email": e} for e in participants],
                "reminders": {"useDefault": True},
                "conferenceData": {
                    "createRequest": {
                        "requestId": uuid.uuid4().hex,
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                },
            }
            event = (
                self._svc.events()
                .insert(
                    calendarId="primary",
                    body=body,
                    sendUpdates="all",
                    conferenceDataVersion=1,
                )
                .execute()
            )
            log.info("Created event %s", event.get("id"))

            # Extract Google Meet link from conference data
            meet_link = ""
            conference = event.get("conferenceData", {})
            for ep in conference.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")
                    break

            return {
                "id": event["id"],
                "title": event.get("summary", title),
                "link": event.get("htmlLink", ""),
                "meet_link": meet_link,
                "start": start_dt,
                "end": end_dt,
                "organizer": settings.SENDER_EMAIL,
                "participants": participants,
                "timezone": timezone,
                "description": description,
                "status": "confirmed",
            }
        except Exception as exc:
            log.exception("create_event failed")
            raise RuntimeError(f"Calendar API error: {exc}") from exc

    # ── list ──────────────────────────────────────────
    def list_events(self, max_results: int = 10) -> list[dict]:
        if self._svc is None:
            return self._mock_list()

        try:
            now = datetime.utcnow().isoformat() + "Z"
            result = (
                self._svc.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = []
            for e in result.get("items", []):
                events.append({
                    "id": e["id"],
                    "title": e.get("summary", ""),
                    "start": e["start"].get("dateTime", e["start"].get("date", "")),
                    "end": e["end"].get("dateTime", e["end"].get("date", "")),
                    "participants": [a["email"] for a in e.get("attendees", [])],
                    "link": e.get("htmlLink", ""),
                })
            return events
        except Exception as exc:
            log.exception("list_events failed")
            raise RuntimeError(f"Calendar API error: {exc}") from exc

    # ── mocks ─────────────────────────────────────────
    @staticmethod
    def _mock_create(title, start_dt, end_dt, tz, participants, desc):
        eid = f"mock_{uuid.uuid4().hex[:10]}"
        log.info("MOCK create event %s", eid)
        return {
            "id": eid,
            "title": title,
            "link": f"mock://{eid}",
            "start": start_dt,
            "end": end_dt,
            "organizer": settings.SENDER_EMAIL,
            "participants": participants,
            "timezone": tz,
            "description": desc,
            "status": "confirmed (mock)",
        }

    @staticmethod
    def _mock_list():
        return [
            {
                "id": "mock_1",
                "title": "Sample meeting",
                "start": datetime.now().isoformat(),
                "end": (datetime.now() + timedelta(hours=1)).isoformat(),
                "participants": ["demo@example.com"],
                "link": "mock://mock_1",
            }
        ]