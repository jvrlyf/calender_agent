from __future__ import annotations

import sys
import os
import json
import uuid
import logging
from datetime import datetime, timedelta


_this_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_this_dir, ".."))
_project_dir = os.path.abspath(os.path.join(_this_dir, "..", ".."))

for p in [_project_dir, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)-8s %(name)-20s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,  # MCP uses stdout for protocol, logs go to stderr
)
log = logging.getLogger("mcp.server")

try:
    from dotenv import load_dotenv
    # Try multiple .env locations
    for env_path in [
        os.path.join(_project_dir, ".env"),
        os.path.join(_backend_dir, ".env"),
        ".env",
    ]:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            log.info("Loaded .env from: %s", env_path)
            break
except ImportError:
    log.warning("python-dotenv not installed, using env vars directly")


# ── Load .env explicitly ──
try:
    from dotenv import load_dotenv
    for env_path in [
        os.path.join(_project_dir, ".env"),
        os.path.join(_backend_dir, ".env"),
        ".env",
    ]:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            log.info("Loaded .env from: %s", env_path)
            break
except ImportError:
    log.warning("python-dotenv not installed")

MOCK_CALENDAR = os.getenv("MOCK_CALENDAR", "true").lower() == "true"
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "")

log.info("MCP Server Config: MOCK=%s, SENDER=%s, TZ=%s", MOCK_CALENDAR, SENDER_EMAIL, DEFAULT_TIMEZONE)


class MockCalendar:
    """In-memory mock calendar for testing without Google API."""

    def __init__(self):
        self._events = []
        log.info("MockCalendar initialised")

    def create_event(self, title, start_dt, end_dt, timezone, participants, description=""):
        eid = f"mock_{uuid.uuid4().hex[:10]}"
        event = {
            "id": eid,
            "title": title,
            "link": f"mock://{eid}",
            "start": start_dt,
            "end": end_dt,
            "organizer": SENDER_EMAIL,
            "participants": participants,
            "timezone": timezone,
            "description": description,
            "status": "confirmed (mock)",
        }
        self._events.append(event)
        log.info("MOCK created event: %s — %s", eid, title)
        return event

    def list_events(self, max_results=10):
        if self._events:
            return self._events[:max_results]
        return [{
            "id": "mock_sample",
            "title": "Sample Meeting",
            "start": datetime.now().isoformat(),
            "end": (datetime.now() + timedelta(hours=1)).isoformat(),
            "participants": ["demo@example.com"],
            "link": "mock://mock_sample",
        }]


_calendar = None

if MOCK_CALENDAR:
    _calendar = MockCalendar()
else:
    try:
        from backend.services.calendar_service import CalendarService
        _calendar = CalendarService()
        log.info("Real CalendarService loaded")
    except Exception as exc:
        log.warning("CalendarService failed (%s), falling back to mock", exc)
        _calendar = MockCalendar()


from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Meeting Planner Calendar Server")


@mcp.tool()
def create_meeting(
    title: str,
    date: str,
    start_time: str,
    end_time: str,
    timezone: str,
    participants: list[str],
    description: str = "",
) -> str:

    try:
        start_dt = f"{date}T{start_time}:00"
        end_dt = f"{date}T{end_time}:00"
        result = _calendar.create_event(
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            timezone=timezone,
            participants=participants,
            description=description,
        )
        log.info("✅ Meeting created: %s", result.get("id"))
        return json.dumps(result)
    except Exception as exc:
        log.exception("❌ create_meeting error")
        return json.dumps({"error": str(exc)})


@mcp.tool()
def list_meetings(max_results: int = 10) -> str:

    try:
        events = _calendar.list_events(max_results=max_results)
        return json.dumps(events)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def check_availability(date: str, start_time: str, end_time: str, timezone: str) -> str:

    try:
        events = _calendar.list_events(max_results=50)
        target_start = f"{date}T{start_time}:00"
        target_end = f"{date}T{end_time}:00"
        conflicts = [
            e for e in events
            if e.get("start", "") < target_end and e.get("end", "") > target_start
        ]
        return json.dumps({
            "available": len(conflicts) == 0,
            "conflicts": conflicts,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    log.info("🚀 MCP Calendar Server starting (stdio transport)")
    mcp.run(transport="stdio")