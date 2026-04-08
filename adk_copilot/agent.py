from __future__ import annotations

import base64
import os
import re

from dotenv import load_dotenv

load_dotenv()

try:
    from google.adk.agents import LlmAgent, SequentialAgent
    from google.adk.tools.tool_context import ToolContext
    from google.genai import types as genai_types
except ImportError as exc:  # pragma: no cover - optional dependency
    raise RuntimeError("Install ADK support with `pip install -e \".[adk]\"`.") from exc

from agentic_analytics.config import Settings
from agentic_analytics.service import build_service

MODEL_NAME = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
SERVICE = build_service(Settings.from_env())


def analytics_question(question: str, tool_context: ToolContext) -> str:
    """Run the analytics workflow; saves the chart as an ADK artifact and returns formatted text."""
    result = SERVICE.ask(question)

    chart = result.get("chart", {})
    if chart.get("base64_data") and chart.get("mime_type"):
        image_bytes = base64.b64decode(chart["base64_data"])
        tool_context.save_artifact(
            "chart.png",
            genai_types.Part(inline_data=genai_types.Blob(mime_type=chart["mime_type"], data=image_bytes)),
        )

    # Strip the embedded base64 chart — chart rendering coming soon
    return re.sub(r'\n\n## Chart\n\n!\[Chart\]\(data:[^)]+\)', '', result["formatted_response"])


def create_task(title: str, due_at: str = "") -> dict:
    """Create a task entry in the productivity database."""
    suffix = f" due {due_at}" if due_at else ""
    result = SERVICE.copilot(f"create a task for {title}{suffix}")
    return result.get("productivity", {})


def save_note(title: str, content: str) -> dict:
    """Save a note directly to the productivity store."""
    from uuid import uuid4
    from agentic_analytics.domain import WorkflowContext
    context = WorkflowContext(
        request_id=str(uuid4()),
        question="save_note",
        schema_context="",
        alert_threshold_percent=0.0,
    )
    payload = SERVICE.registry.invoke("create_note", {"title": title, "content": content}, context)
    return {"note": payload["note"]}


def retrieve_notes(query: str = "") -> dict:
    """Retrieve old notes or search notes from the productivity database."""
    prompt = f"find notes about {query}" if query else "show recent notes"
    return SERVICE.copilot(prompt).get("productivity", {})


def retrieve_calendar_events(query: str = "") -> dict:
    """Retrieve calendar events or search the schedule from the productivity database."""
    prompt = f"find events about {query}" if query else "show upcoming events"
    return SERVICE.copilot(prompt).get("productivity", {})


def send_slack_message(message: str) -> dict:
    """Send a message directly through the configured Slack notifier."""
    from uuid import uuid4
    from agentic_analytics.domain import WorkflowContext
    context = WorkflowContext(
        request_id=str(uuid4()),
        question="send_slack_message",
        schema_context="",
        alert_threshold_percent=0.0,
    )
    payload = SERVICE.registry.invoke("send_slack_message", {"message": message}, context)
    return {"delivered": payload["delivered"], "message_length": len(message)}


def create_calendar_event(title: str, start_time: str, end_time: str = "") -> dict:
    """Create a calendar event entry in the productivity database."""
    return SERVICE.copilot(f"schedule {title} at {start_time} {end_time}".strip()).get("productivity", {})


planner_agent = LlmAgent(
    name="PlannerAgent",
    model=MODEL_NAME,
    description="Plans whether the request needs analytics, tasking, scheduling, or notes.",
    instruction=(
        "You are an internal routing agent. Do NOT greet the user, explain your reasoning, or output anything conversational. "
        "Output ONLY a single concise sentence describing which tools the execution agent should call and in what order. "
        "Example: 'Call analytics_question to get top products, then call send_slack_message with the result.' "
        "If the user is greeting or making small talk, output: 'No tools needed, respond conversationally.'"
    ),
    output_key="workflow_plan",
)

execution_agent = LlmAgent(
    name="ExecutionAgent",
    model=MODEL_NAME,
    description="Executes user workflows using analytics and productivity tools.",
    instruction=(
        "You execute the user's request using the available tools. "
        "Follow the plan in {workflow_plan}. "
        "For multi-step tasks, call each tool in sequence: complete the first tool call and use its result before calling the next. "
        "Use analytics_question for revenue, SQL, or data analysis questions. "
        "Use send_slack_message to send analysis results or messages to Slack — pass the full analysis text as the message. "
        "Use create_task, create_calendar_event, save_note, retrieve_notes, retrieve_calendar_events for productivity tasks. "
        "If no tools are needed (e.g. greeting), respond directly to the user. "
        "When analytics_question returns a result, output it EXACTLY as returned — do not paraphrase, summarize, or omit any part. "
        "This includes the full markdown, data tables, SQL code blocks, and chart image data. "
        "If asked to save an analytics result as a note: extract the question/title from the user's request, then call save_note(title=<extracted_title>, content=<FULL_ANALYTICS_RESULT_WITH_ALL_MARKDOWN>). "
        "CRITICAL: When passing analytics data to save_note, use the COMPLETE formatted response including all markdown (# headings, ## sections, | tables |, ```sql blocks```) — do not truncate or summarize. "
        "After completing all steps, append a one-line confirmation of any productivity actions taken (e.g. Slack sent)."
    ),
    tools=[analytics_question, create_task, save_note, retrieve_notes, retrieve_calendar_events, send_slack_message, create_calendar_event],
)

root_agent = SequentialAgent(
    name="root_agent",
    description="Coordinates planning and execution for analytics plus productivity workflows.",
    sub_agents=[planner_agent, execution_agent],
)
