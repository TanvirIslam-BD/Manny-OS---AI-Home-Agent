"""Turn a spoken reminder request into a title and a due time.

Deliberately small and explicit rather than a general date library: the device
only needs the handful of forms people actually say out loud, and a parser that
returns nothing when it is unsure is safer than one that guesses a time and
silently schedules the wrong thing.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, tzinfo

_RELATIVE = re.compile(
    r"\bin\s+(?P<count>\d{1,3})\s*(?P<unit>minute|minutes|min|mins|hour|hours|hr|hrs|day|days)\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"\bat\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<meridiem>a\.?\s?m\.?|p\.?\s?m\.?)?",
    re.IGNORECASE,
)
_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_TONIGHT = re.compile(r"\btonight\b", re.IGNORECASE)
_LEAD = re.compile(
    r"^\s*(please\s+)?(can\s+you\s+)?"
    r"(add|create|set|make|put)?\s*(a|an|the)?\s*(new\s+)?reminder\s*"
    r"(for|to|about|that)?\s*|^\s*(please\s+)?remind\s+me\s*(to|about|that)?\s*",
    re.IGNORECASE,
)
_TRAILING = re.compile(r"[\s,.;:!-]+$")


def parse_due(text: str, *, now: datetime, timezone: tzinfo) -> datetime | None:
    """Resolve a due time, or None when the request does not state one."""
    local = now.astimezone(timezone)

    relative = _RELATIVE.search(text)
    if relative:
        count = int(relative.group("count"))
        unit = relative.group("unit").lower()
        if unit.startswith("day"):
            delta = timedelta(days=count)
        elif unit.startswith(("hour", "hr")):
            delta = timedelta(hours=count)
        else:
            delta = timedelta(minutes=count)
        return (local + delta).astimezone(now.tzinfo)

    clock = _CLOCK.search(text)
    if clock:
        hour = int(clock.group("hour"))
        minute = int(clock.group("minute") or 0)
        meridiem = (clock.group("meridiem") or "").replace(".", "").replace(" ", "").lower()
        if hour > 23 or minute > 59:
            return None
        if meridiem.startswith("p") and hour < 12:
            hour += 12
        elif meridiem.startswith("a") and hour == 12:
            hour = 0
        elif not meridiem and _TONIGHT.search(text) and hour < 12:
            hour += 12
        due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if _TOMORROW.search(text):
            due += timedelta(days=1)
        elif due <= local:
            # A time already past today means the next one.
            due += timedelta(days=1)
        return due.astimezone(now.tzinfo)

    if _TOMORROW.search(text):
        due = (local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return due.astimezone(now.tzinfo)

    return None


def parse_title(text: str) -> str:
    """Strip the request wrapper and the time phrase, leaving the thing to do."""
    title = _LEAD.sub("", text.strip())
    title = _RELATIVE.sub(" ", title)
    title = _CLOCK.sub(" ", title)
    title = _TOMORROW.sub(" ", title)
    title = _TONIGHT.sub(" ", title)
    title = _LEAD.sub("", title)
    title = re.sub(r"^\s*(to|that|about)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip()
    title = _TRAILING.sub("", title)
    return title[:160] or "Reminder"
