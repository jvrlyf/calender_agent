from __future__ import annotations

import json
from datetime import datetime, timedelta

from backend.agent.state import AgentState, MeetingInfo
from backend.agent.sub_agents import (
    classify_intent,
    parse_meeting_details,
    generate_response,
)
from backend.config import settings
from backend.utils.logger import get_logger

log = get_logger("agent.nodes")

# reference set at runtime by graph builder
_mcp_client = None


def set_mcp_client(client):
    global _mcp_client
    _mcp_client = client


# ── helpers ───────────────────────────────────────────

REQUIRED_FIELDS = ["title", "date", "start_time", "participants"]


def _missing_fields(info: MeetingInfo) -> list[str]:
    missing = []
    for f in REQUIRED_FIELDS:
        val = info.get(f)
        if val is None or val == "" or val == []:
            missing.append(f)
    return missing


def _format_details(info: MeetingInfo) -> str:
    lines = []
    if info.get("title"):
        lines.append(f"📌 Title        : {info['title']}")
    if info.get("date"):
        lines.append(f"📅 Date         : {info['date']}")
    if info.get("start_time"):
        end = info.get("end_time", "—")
        lines.append(f"⏰ Time         : {info['start_time']} – {end}")
    lines.append(f"🌍 Timezone     : {info.get('timezone', settings.DEFAULT_TIMEZONE)}")
    if info.get("participants"):
        lines.append(f"👥 Participants : {', '.join(info['participants'])}")
    if info.get("description"):
        lines.append(f"📝 Description  : {info['description']}")
    return "\n".join(lines)


FIELD_QUESTIONS = {
    "title": "What should the meeting title be?",
    "date": "Which date? (e.g. 2025-07-15 or 'tomorrow')",
    "start_time": "What time should it start? (e.g. 15:00 or 3 PM)",
    "participants": "Please share participant email(s) — comma-separated.",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: classify_input
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def classify_input_node(state: AgentState) -> dict:
    last_msg = state["messages"][-1]["content"]
    intent = classify_intent(last_msg, state.get("status", "idle"))
    log.info("Intent classified: %s", intent)
    return {"intent": intent}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: extract_details
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_details_node(state: AgentState) -> dict:
    last_msg = state["messages"][-1]["content"]
    parsed = parse_meeting_details(last_msg, state["messages"])

    # merge with existing
    info: MeetingInfo = dict(state.get("meeting_info", {}))
    for key in ("title", "date", "start_time", "end_time", "timezone", "participants", "description"):
        new_val = parsed.get(key)
        if new_val is not None and new_val != "" and new_val != []:
            info[key] = new_val

    # default timezone
    if not info.get("timezone"):
        info["timezone"] = settings.DEFAULT_TIMEZONE

    # auto end_time
    if info.get("start_time") and not info.get("end_time"):
        try:
            st = datetime.strptime(info["start_time"], "%H:%M")
            info["end_time"] = (st + timedelta(hours=1)).strftime("%H:%M")
        except ValueError:
            pass

    log.info("Extracted meeting info: %s", info)
    return {"meeting_info": info, "status": "collecting"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: check_completeness
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_completeness_node(state: AgentState) -> dict:
    missing = _missing_fields(state["meeting_info"])
    log.info("Missing fields: %s", missing)
    if missing:
        return {"intent": "incomplete"}
    return {"intent": "complete"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: ask_missing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ask_missing_node(state: AgentState) -> dict:
    missing = _missing_fields(state["meeting_info"])
    questions = [FIELD_QUESTIONS.get(f, f"Please provide: {f}") for f in missing]
    details_so_far = _format_details(state["meeting_info"])

    resp = "I need a few more details to schedule your meeting.\n\n"
    if details_so_far:
        resp += f"**So far I have:**\n{details_so_far}\n\n"
    resp += "**Still needed:**\n" + "\n".join(f"• {q}" for q in questions)

    return {"response": resp, "status": "collecting"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: present_confirmation (human-in-the-loop)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def present_confirmation_node(state: AgentState) -> dict:
    details = _format_details(state["meeting_info"])
    resp = (
        "✅ I have all the details! Here's the meeting summary:\n\n"
        f"{details}\n\n"
        "**Shall I go ahead and create this meeting? (yes / no)**"
    )
    return {"response": resp, "status": "confirming"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: handle_confirmation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def handle_confirmation_node(state: AgentState) -> dict:
    # intent already classified as confirmation / denial / modification
    return {}  # routing is handled by edges


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: create_meeting (calls MCP)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def create_meeting_node(state: AgentState) -> dict:
    info = state["meeting_info"]
    log.info("Creating meeting via MCP: %s", info)

    if _mcp_client is None or not _mcp_client.is_connected:
        return {
            "response": "❌ Calendar service is not available. Please try again later.",
            "status": "error",
        }

    try:
        result = await _mcp_client.call_tool("create_meeting", {
            "title": info.get("title", "Meeting"),
            "date": info["date"],
            "start_time": info["start_time"],
            "end_time": info.get("end_time", info["start_time"]),
            "timezone": info.get("timezone", settings.DEFAULT_TIMEZONE),
            "participants": info.get("participants", []),
            "description": info.get("description", ""),
        })

        if "error" in result:
            return {
                "response": f"❌ Failed to create meeting: {result['error']}",
                "status": "error",
            }

        link = result.get("link", "")
        meet_link = result.get("meet_link", "")
        organizer = result.get("organizer", settings.SENDER_EMAIL)

        resp = (
            "🎉 **Meeting created successfully!**\n\n"
            f"{_format_details(info)}\n"
            f"📧 Organizer    : {organizer}\n\n"
        )
        if meet_link:
            resp += f"📹 **Google Meet**: {meet_link}\n"
        if link:
            resp += f"🔗 Calendar link : {link}\n"
        resp += "\nWant to schedule another meeting?"
        return {"response": resp, "status": "created"}

    except Exception as exc:
        log.exception("create_meeting_node failed")
        return {
            "response": f"❌ Error creating meeting: {exc}",
            "status": "error",
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NODE: general_response
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def general_response_node(state: AgentState) -> dict:
    intent = state.get("intent", "general")

    if intent == "denial":
        return {
            "response": "No problem! Meeting cancelled. Let me know whenever you want to schedule something. 😊",
            "status": "idle",
            "meeting_info": {},
        }

    # Natural greeting responses — no raw prompts shown
    last_msg = state["messages"][-1]["content"].strip().lower() if state["messages"] else ""

    greetings = ("hi", "hello", "hey", "hola", "namaste", "hii", "hiii", "yo", "sup")

    if last_msg in greetings or any(last_msg.startswith(g) for g in greetings):
        return {
            "response": "Hey! 👋 I'm your meeting planner. Just tell me what meeting you want — like:\n\n"
                        "\"Schedule a meeting with raj@gmail.com tomorrow at 3 PM about project review\"\n\n"
                        "Or just share details one by one, I'll guide you!",
        }

    # For other general messages, try LLM but with safe fallback
    resp = generate_response(
        status=state.get("status", "idle"),
        situation="User is chatting casually. Respond naturally and remind them you can schedule meetings.",
        details=str(state.get("meeting_info", {})),
    )

    if not resp or "User sent" in resp or len(resp) < 5:
        resp = "I'm here to help schedule meetings! 📅 Just tell me the title, date, time, and participants."

    return {"response": resp}