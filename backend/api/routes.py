from __future__ import annotations

import uuid
from typing import Dict

from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    ChatRequest,
    ChatResponse,
    MeetingDetailsOut,
    SessionOut,
    MessageItem,
    HealthResponse,
    MeetingsListResponse,
    MeetingEvent,
)
from backend.agent.state import AgentState, MeetingInfo
from backend.utils.logger import get_logger

log = get_logger("api.routes")

router = APIRouter(prefix="/api", tags=["meeting-planner"])

# ── in-memory session store ───────────────────────────
_sessions: Dict[str, dict] = {}

# these are injected at startup from main.py
_agent_graph = None
_mcp_client = None


def inject_dependencies(agent_graph, mcp_client):
    global _agent_graph, _mcp_client
    _agent_graph = agent_graph
    _mcp_client = mcp_client


def _get_or_create_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "messages": [],
            "meeting_info": {},
            "status": "idle",
        }
    return _sessions[session_id]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST /api/chat — main conversational endpoint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to the planning agent and get a response."""
    log.info("POST /api/chat  session=%s  msg=%s", req.session_id, req.message[:80])

    if _agent_graph is None:
        raise HTTPException(status_code=503, detail="Agent not initialised yet")

    session = _get_or_create_session(req.session_id)

    # append user message
    session["messages"].append({"role": "user", "content": req.message})

    # build graph input state
    graph_input: AgentState = {
        "messages": session["messages"],
        "meeting_info": session.get("meeting_info", {}),
        "status": session.get("status", "idle"),
        "response": "",
        "intent": "",
    }

    try:
        result = await _agent_graph.ainvoke(graph_input)
    except Exception as exc:
        log.exception("Agent graph invocation failed")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    # update session
    agent_reply = result.get("response", "I'm sorry, something went wrong.")
    session["status"] = result.get("status", session["status"])
    session["meeting_info"] = result.get("meeting_info", session.get("meeting_info", {}))
    session["messages"].append({"role": "assistant", "content": agent_reply})

    # reset if created or error → ready for new request
    if session["status"] in ("created",):
        session["meeting_info"] = {}
        session["status"] = "idle"

    meeting_out = None
    info = result.get("meeting_info") or session.get("meeting_info")
    if info and any(info.get(k) for k in ("title", "date", "start_time")):
        meeting_out = MeetingDetailsOut(**{
            k: info.get(k) for k in MeetingDetailsOut.model_fields
        })

    return ChatResponse(
        session_id=req.session_id,
        response=agent_reply,
        meeting_details=meeting_out,
        status=result.get("status", "idle"),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GET /api/session/{session_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/session/{session_id}", response_model=SessionOut)
async def get_session(session_id: str):
    """Retrieve current session state."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    s = _sessions[session_id]
    return SessionOut(
        session_id=session_id,
        messages=[MessageItem(**m) for m in s["messages"]],
        meeting_details=MeetingDetailsOut(**s["meeting_info"]) if s["meeting_info"] else None,
        status=s["status"],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DELETE /api/session/{session_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Clear a conversation session."""
    _sessions.pop(session_id, None)
    log.info("Session %s cleared", session_id)
    return {"message": "Session cleared"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GET /api/meetings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/meetings", response_model=MeetingsListResponse)
async def list_meetings():
    """List upcoming calendar meetings via MCP."""
    if _mcp_client is None or not _mcp_client.is_connected:
        raise HTTPException(status_code=503, detail="Calendar service unavailable")

    try:
        result = await _mcp_client.call_tool("list_meetings", {"max_results": 10})
        if isinstance(result, list):
            events = [MeetingEvent(**e) for e in result]
        else:
            events = []
        return MeetingsListResponse(events=events)
    except Exception as exc:
        log.exception("list_meetings failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GET /api/health
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/health", response_model=HealthResponse)
async def health():
    mcp_status = "connected" if (_mcp_client and _mcp_client.is_connected) else "disconnected"
    cal_status = "mock" if __import__("backend.config", fromlist=["settings"]).settings.MOCK_CALENDAR else "live"
    return HealthResponse(status="ok", mcp_server=mcp_status, calendar=cal_status)