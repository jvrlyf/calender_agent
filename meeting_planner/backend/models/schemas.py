"""
Pydantic v2 request / response models for every endpoint.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


# ── Chat ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="UUID session identifier")
    message: str = Field(..., min_length=1, description="User message text")


class MeetingDetailsOut(BaseModel):
    title: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    participants: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    meeting_details: Optional[MeetingDetailsOut] = None
    status: str = "idle"  # idle | collecting | confirming | created | error


# ── Session ───────────────────────────────────────────
class MessageItem(BaseModel):
    role: str  # user | assistant
    content: str


class SessionOut(BaseModel):
    session_id: str
    messages: list[MessageItem] = Field(default_factory=list)
    meeting_details: Optional[MeetingDetailsOut] = None
    status: str = "idle"


# ── Health ────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str = "ok"
    mcp_server: str = "unknown"
    calendar: str = "unknown"


# ── Meeting list ──────────────────────────────────────
class MeetingEvent(BaseModel):
    id: str
    title: str
    start: str
    end: str
    participants: list[str] = Field(default_factory=list)
    link: Optional[str] = None


class MeetingsListResponse(BaseModel):
    events: list[MeetingEvent] = Field(default_factory=list)