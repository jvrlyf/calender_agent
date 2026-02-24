from __future__ import annotations
from typing import TypedDict, Optional, Annotated
from operator import add


class MeetingInfo(TypedDict, total=False):
    title: Optional[str]
    date: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    timezone: str
    participants: list[str]
    description: Optional[str]


class AgentState(TypedDict):
    messages: list[dict]         # [{role, content}, ...]
    meeting_info: MeetingInfo
    status: str                  # idle | collecting | confirming | created | error
    response: str                # final reply to user
    intent: str                  # new_request | confirmation | denial | modification | general