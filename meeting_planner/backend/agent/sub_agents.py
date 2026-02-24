from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from backend.config import settings
from backend.utils.logger import get_logger

log = get_logger("agent.sub_agents")

# ── HF Inference Client singleton ─────────────────────
_hf_client = None


def _get_hf_client():
    global _hf_client
    if _hf_client is None:
        try:
            from huggingface_hub import InferenceClient
            _hf_client = InferenceClient(
                model=settings.HF_MODEL,
                token=settings.HF_TOKEN,
            )
            log.info("HuggingFace InferenceClient ready: %s", settings.HF_MODEL)
        except Exception as exc:
            log.error("Failed to create HF client: %s", exc)
            _hf_client = None
    return _hf_client


def _call_llm(prompt: str) -> str:
    """Call HuggingFace model. Tries chat first, then text_generation."""
    client = _get_hf_client()
    if client is None:
        return ""

    # Method 1: Try chat_completion (works for most modern models)
    try:
        response = client.chat_completion(
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=512,
            temperature=0.1,
        )
        text = response.choices[0].message.content
        log.debug("HF chat response: %s", text[:200])
        return text.strip() if text else ""
    except Exception as exc1:
        log.debug("HF chat failed (%s), trying text_generation", exc1)

    # Method 2: Try text_generation
    try:
        response = client.text_generation(
            prompt,
            max_new_tokens=512,
            temperature=0.1,
        )
        return response.strip() if response else ""
    except Exception as exc2:
        log.warning("HF LLM all methods failed: %s", exc2)
        return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REGEX FALLBACK PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _regex_extract(text: str) -> dict:
    """
    Best-effort regex extraction from casual user text.
    Handles Hindi+English mixed, any format dates, times, emails.
    """
    result = {}
    lower = text.lower()

    # ── emails ──
    emails = re.findall(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', text)
    if emails:
        result["participants"] = emails

    # ── date: DD/MM/YYYY or DD-MM-YYYY ──
    date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text)
    if date_match:
        d, m, y = date_match.groups()
        try:
            dt = datetime(int(y), int(m), int(d))
            result["date"] = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # ── date: YYYY-MM-DD ──
    if "date" not in result:
        iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if iso_match:
            result["date"] = iso_match.group(0)

    # ── date: tomorrow/today/kal/aaj ──
    if "date" not in result:
        if any(w in lower for w in ("tomorrow", "kal", "tmrw")):
            result["date"] = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        elif any(w in lower for w in ("today", "aaj", "abhi")):
            result["date"] = datetime.now().strftime("%Y-%m-%d")
        elif "parso" in lower or "day after" in lower:
            result["date"] = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    # ── time: "3 PM", "3PM", "15:00", "3:30 pm", "3 baje" ──
    time_match = re.search(
        r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM|baje|बजे)?',
        text
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        period = (time_match.group(3) or "").lower()

        if period in ("pm",) and hour < 12:
            hour += 12
        elif period in ("am",) and hour == 12:
            hour = 0
        elif period in ("baje", "बजे") and hour < 7:
            hour += 12

        if 0 <= hour <= 23:
            result["start_time"] = f"{hour:02d}:{minute:02d}"

    # ── title extraction ──
    title_text = text
    title_text = re.sub(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', '', title_text)
    title_text = re.sub(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', '', title_text)
    title_text = re.sub(r'\d{4}-\d{2}-\d{2}', '', title_text)
    title_text = re.sub(r'\d{1,2}(:\d{2})?\s*(am|pm|AM|PM|baje|बजे)?', '', title_text)

    remove_words = [
        "schedule", "meeting", "set", "up", "a", "with", "on", "at",
        "for", "about", "the", "please", "create", "book", "rakho",
        "rakh", "do", "karo", "ek", "ka", "ki", "ke", "ko", "me",
        "mein", "hai", "hain", "tomorrow", "today", "kal", "aaj",
        "title", "mail", "id", "email", "time", "date", "parso",
        "interview", "se", "-", ",", ".", "baje", "—", "–", "and"
    ]

    title_text = re.sub(r'[,\-\.\:\—\–]+', ' ', title_text)
    words = title_text.split()
    title_words = [
        w for w in words
        if w.lower().strip() not in remove_words and len(w.strip()) > 0
    ]

    if title_words:
        quoted = re.search(r'["\'](.+?)["\']', text)
        if quoted:
            result["title"] = quoted.group(1).strip()
        else:
            title_pattern = re.search(
                r'title\s*[\-:]\s*(.+?)(?:\s+on\s|\s+at\s|\s+with\s|\s+mail|\s+email|\s+time|\s+date|\d|$)',
                text, re.IGNORECASE
            )
            if title_pattern:
                t = title_pattern.group(1).strip().rstrip(',').rstrip('-').strip()
                if t:
                    result["title"] = t
            else:
                meaningful = ' '.join(title_words).strip()
                meaningful = re.sub(r'^[\—\-\–\s]+', '', meaningful)
                meaningful = re.sub(r'[\—\-\–\s]+$', '', meaningful)
                meaningful = meaningful.strip()
                if len(meaningful) > 2:
                    result["title"] = meaningful

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PARSER SUB-AGENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_parser_prompt(message: str, history: list[dict]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    history_str = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in history[-6:]
    )

    return f"""<|system|>
You are a meeting-detail extractor. Extract info from user message.
Today: {today}, Tomorrow: {tomorrow}, Default TZ: {settings.DEFAULT_TIMEZONE}
</s>
<|user|>
Conversation: {history_str or '(none)'}
Message: "{message}"

Return ONLY valid JSON:
{{"title": "string or null", "date": "YYYY-MM-DD or null", "start_time": "HH:MM or null", "end_time": "HH:MM or null", "timezone": "{settings.DEFAULT_TIMEZONE}", "participants": ["email"], "description": "string or null"}}
</s>
<|assistant|>
"""


def _sanitise_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def parse_meeting_details(message: str, history: list[dict]) -> dict:
    """
    Call LLM to extract meeting details.
    Falls back to regex if LLM returns empty/garbage.
    """
    llm_result = {}

    try:
        prompt = _build_parser_prompt(message, history)
        raw = _call_llm(prompt)
        if raw:
            log.debug("Parser LLM raw: %s", raw[:300])
            llm_result = _sanitise_json(raw)
    except Exception as exc:
        log.exception("ParserAgent failed, using regex only")

    # ALWAYS run regex
    regex_result = _regex_extract(message)
    log.debug("Regex extracted: %s", regex_result)

    # merge: regex fills gaps LLM missed
    final = {}
    for key in ("title", "date", "start_time", "end_time", "timezone", "participants", "description"):
        llm_val = llm_result.get(key)
        regex_val = regex_result.get(key)

        if llm_val is not None and llm_val != "" and llm_val != []:
            final[key] = llm_val
        elif regex_val is not None and regex_val != "" and regex_val != []:
            final[key] = regex_val

    log.info("Final parsed: %s", final)
    return final


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INTENT CLASSIFIER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_CONFIRM_WORDS = {
    "yes", "yep", "yeah", "sure", "ok", "okay", "confirm",
    "go ahead", "haan", "ha", "yes please", "theek hai",
    "thik hai", "kar do", "kardo", "done", "agreed"
}

_DENY_WORDS = {
    "no", "nope", "cancel", "stop", "nahi", "nah",
    "don't", "dont", "mat karo", "band karo", "ruko", "cancel karo"
}

_MEETING_KEYWORDS = {
    "schedule", "meeting", "book", "create", "set up", "setup",
    "interview", "rakho", "rakh", "karo", "banao", "bana",
    "calendar", "appointment", "call", "sync", "standup",
    "plan", "arrange"
}


def classify_intent(message: str, status: str) -> str:
    """Hybrid: rule-based fast-path + LLM fallback."""
    lower = message.strip().lower()

    # confirming phase
    if status == "confirming":
        if lower in _CONFIRM_WORDS or any(w in lower for w in _CONFIRM_WORDS):
            return "confirmation"
        if lower in _DENY_WORDS or any(w in lower for w in _DENY_WORDS):
            return "denial"

    # meeting keywords
    has_meeting_keyword = any(kw in lower for kw in _MEETING_KEYWORDS)
    has_email = bool(re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', message))
    has_date = bool(re.search(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', message)) or \
               any(w in lower for w in ("tomorrow", "kal", "today", "aaj", "parso"))
    has_time = bool(re.search(r'\d{1,2}\s*(am|pm|baje|:)', lower))

    if has_meeting_keyword:
        return "new_request"
    if has_email and (has_date or has_time):
        return "new_request"
    if has_date and has_time:
        return "new_request"

    # collecting phase — user answering questions
    if status == "collecting":
        if has_email or has_date or has_time:
            return "new_request"
        if len(lower.split()) <= 8 and not any(w in lower for w in ("hi", "hello", "hey", "kya", "kaisa")):
            return "new_request"

    # LLM fallback
    prompt = f"""<|system|>
Classify message into: new_request, confirmation, denial, modification, general
Status: {status}
</s>
<|user|>
"{message}"
Reply with ONLY the category name.
</s>
<|assistant|>
"""
    raw = _call_llm(prompt).strip().lower()
    for cat in ("new_request", "confirmation", "denial", "modification", "general"):
        if cat in raw:
            return cat

    return "general"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RESPONSE GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_response(status: str, situation: str, details: str) -> str:
    prompt = f"""<|system|>
You are a friendly meeting assistant. Reply in 1-2 sentences. Be natural.
</s>
<|user|>
Status: {status}
Situation: {situation}
Details: {details}
</s>
<|assistant|>
"""
    resp = _call_llm(prompt)

    if not resp or "User sent" in resp or len(resp) < 5:
        return "Hey! I'm here to help schedule meetings. Tell me the title, date, time, and participants! 📅"

    return resp