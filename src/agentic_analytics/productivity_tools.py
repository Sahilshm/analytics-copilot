from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from .domain import ToolOutput, WorkflowContext
from .productivity_store import ProductivityStore
from .tools import MCPTool, ToolSpec


class CreateTaskTool(MCPTool):
    spec = ToolSpec(
        name="create_task",
        description="Create a task in the local task store.",
        required_fields=("title",),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        task = self.store.create_task(str(payload["title"]), payload.get("due_at"), str(payload.get("priority", "medium")))
        return ToolOutput(payload={"task": task}, summary=f"Created task '{task['title']}'.")


class ListTasksTool(MCPTool):
    spec = ToolSpec(
        name="list_tasks",
        description="List tasks from the local task store.",
        required_fields=(),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        tasks = self.store.list_tasks(status=payload.get("status"), limit=int(payload.get("limit", 10)))
        return ToolOutput(payload={"tasks": tasks}, summary=f"Loaded {len(tasks)} task records.")


class CreateCalendarEventTool(MCPTool):
    spec = ToolSpec(
        name="create_calendar_event",
        description="Create a calendar event in the local event store.",
        required_fields=("title", "start_time"),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        event = self.store.create_calendar_event(
            title=str(payload["title"]),
            start_time=str(payload["start_time"]),
            end_time=payload.get("end_time"),
            location=payload.get("location"),
            details=payload.get("details"),
        )
        return ToolOutput(payload={"event": event}, summary=f"Created calendar event '{event['title']}'.")


class ListCalendarEventsTool(MCPTool):
    spec = ToolSpec(
        name="list_calendar_events",
        description="List calendar events from the local event store.",
        required_fields=(),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        events = self.store.list_calendar_events(limit=int(payload.get("limit", 10)))
        return ToolOutput(payload={"events": events}, summary=f"Loaded {len(events)} calendar events.")


class SearchCalendarEventsTool(MCPTool):
    spec = ToolSpec(
        name="search_calendar_events",
        description="Search calendar events from the local event store.",
        required_fields=("query",),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        events = self.store.search_calendar_events(str(payload["query"]), limit=int(payload.get("limit", 10)))
        return ToolOutput(payload={"events": events}, summary=f"Found {len(events)} matching calendar events.")


class CreateNoteTool(MCPTool):
    spec = ToolSpec(
        name="create_note",
        description="Create a note in the local note store.",
        required_fields=("title", "content"),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        note = self.store.create_note(str(payload["title"]), str(payload["content"]), payload.get("tags"))
        return ToolOutput(payload={"note": note}, summary=f"Saved note '{note['title']}'.")


class SearchNotesTool(MCPTool):
    spec = ToolSpec(
        name="search_notes",
        description="Search notes from the local note store.",
        required_fields=("query",),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        notes = self.store.search_notes(str(payload["query"]), limit=int(payload.get("limit", 10)))
        return ToolOutput(payload={"notes": notes}, summary=f"Found {len(notes)} matching notes.")


class ListNotesTool(MCPTool):
    spec = ToolSpec(
        name="list_notes",
        description="List the most recent notes from the local note store.",
        required_fields=(),
    )

    def __init__(self, store: ProductivityStore) -> None:
        self.store = store

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        notes = self.store.search_notes("", limit=int(payload.get("limit", 10)))
        return ToolOutput(payload={"notes": notes}, summary=f"Loaded {len(notes)} recent notes.")


def parse_datetime_text(prompt: str) -> tuple[str, str | None]:
    lowered = prompt.lower()
    base_date = date.today()
    if "tomorrow" in lowered:
        target_date = base_date + timedelta(days=1)
    elif "next week" in lowered:
        target_date = base_date + timedelta(days=7)
    else:
        iso_match = re.search(r"(20\d{2}-\d{2}-\d{2})", prompt)
        target_date = date.fromisoformat(iso_match.group(1)) if iso_match else base_date

    time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", lowered)
    end_match = re.search(r"from\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+to\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", lowered)

    if end_match:
        start_dt = _build_datetime(target_date, end_match.group(1), end_match.group(2), end_match.group(3))
        end_dt = _build_datetime(target_date, end_match.group(4), end_match.group(5), end_match.group(6))
        return start_dt.isoformat(), end_dt.isoformat()

    if time_match:
        start_dt = _build_datetime(target_date, time_match.group(1), time_match.group(2), time_match.group(3))
    else:
        start_dt = datetime.combine(target_date, time(hour=9, minute=0))
    end_dt = start_dt + timedelta(hours=1)
    return start_dt.isoformat(), end_dt.isoformat()


def extract_task_title(prompt: str) -> str:
    patterns = [
        r"(?:task to|todo to|to-do to|remind me to)\s+(.+)",
        r"(?:create a task for|add a task for)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return _clean_fragment(match.group(1))
    return _clean_fragment(prompt)


def extract_note_content(prompt: str) -> tuple[str, str]:
    patterns = [
        r"(?:save a note(?: that)?|create a note(?: that)?|note that|remember that)\s+(.+)",
        r"(?:note|remember)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            content = _clean_fragment(match.group(1))
            return _title_from_text(content), content
    content = _clean_fragment(prompt)
    return _title_from_text(content), content


def extract_note_query(prompt: str) -> str:
    patterns = [
        r"(?:search notes for|search notes about|find notes about|find note about|notes about)\s+(.+)",
        r"(?:search notes|find notes|find note|retrieve notes|retrieve old notes|show notes about)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return _clean_fragment(match.group(1))
    if any(token in prompt.lower() for token in ["old notes", "all notes", "recent notes", "show notes", "list notes"]):
        return ""
    return _clean_fragment(prompt)


def extract_event_title(prompt: str) -> str:
    match = re.search(
        r"(?:schedule|add|create)\s+(?:a\s+)?(?:meeting|event|calendar event)?\s*(.+?)(?:\s+(?:tomorrow|today|next week|on|at|from)\b|$)",
        prompt,
        flags=re.IGNORECASE,
    )
    if match:
        title = _clean_fragment(match.group(1))
        if title:
            return title
    return "Scheduled event"


def extract_event_query(prompt: str) -> str:
    patterns = [
        r"(?:find events about|find event about|search calendar for|search calendar about|calendar events about|events about)\s+(.+)",
        r"(?:show schedule for|show calendar for|show events for|find meeting about)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return _clean_fragment(match.group(1))
    if any(token in prompt.lower() for token in ["show calendar", "show schedule", "upcoming events", "calendar events", "recent events"]):
        return ""
    return _clean_fragment(prompt)


def extract_slack_message(prompt: str) -> str:
    patterns = [
        r"(?:send (?:a )?slack message(?: that)?|send to slack(?: that)?|post to slack(?: that)?|notify the team(?: that)?|send message(?: that)?)\s+(.+)",
        r"(?:slack(?: that)?|message the team(?: that)?)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return _clean_fragment(match.group(1))
    return _clean_fragment(prompt)


def productivity_intent(prompt: str) -> dict[str, bool]:
    lowered = prompt.lower()
    return {
        "create_task": any(token in lowered for token in ["task", "todo", "to-do", "remind me to"]),
        "list_tasks": any(token in lowered for token in ["show tasks", "list tasks", "open tasks", "todo list"]),
        "create_event": any(token in lowered for token in ["schedule", "calendar", "meeting", "appointment"]),
        "list_events": any(
            token in lowered
            for token in [
                "show calendar",
                "show schedule",
                "upcoming events",
                "calendar events",
                "recent events",
                "find event",
                "find events",
                "search calendar",
                "show events",
                "retrieve events",
            ]
        ),
        "create_note": any(token in lowered for token in ["save a note", "create a note", "note that", "remember that"]),
        "search_notes": any(
            token in lowered
            for token in [
                "search notes",
                "find note",
                "find notes",
                "show notes",
                "list notes",
                "recent notes",
                "old notes",
                "retrieve notes",
                "retrieve old notes",
                "notes about",
            ]
        ),
        "send_message": any(
            token in lowered
            for token in [
                "slack message",
                "send to slack",
                "post to slack",
                "notify the team",
                "message the team",
                "send message",
            ]
        ),
    }


def _build_datetime(target_date: date, hour_text: str, minute_text: str | None, meridiem: str) -> datetime:
    hour = int(hour_text)
    minute = int(minute_text or "0")
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return datetime.combine(target_date, time(hour=hour, minute=minute))


def _clean_fragment(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,")


def _title_from_text(value: str) -> str:
    words = value.split()
    return " ".join(words[:6]) if words else "Quick note"
