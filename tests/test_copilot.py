from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_analytics.config import Settings
from agentic_analytics.service import build_service


class CopilotTests(TestCase):
    def test_copilot_can_chain_task_calendar_and_note_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(
                llm_backend="rule_based",
                warehouse_backend="demo",
                notifier_backend="log",
                sqlite_db_path=os.path.join(tmp_dir, "copilot.db"),
                demo_anchor_date="2026-04-06",
            )
            service = build_service(settings)
            result = service.copilot(
                "Schedule demo rehearsal tomorrow at 5pm and create a task to finalize slides and save a note that the BigQuery demo tables are ready"
            )
            self.assertIn("productivity", result["domains"])
            productivity = result["productivity"]
            self.assertEqual(len(productivity["actions"]), 3)
            self.assertEqual(len(productivity["snapshot"]["tasks"]), 1)
            self.assertEqual(len(productivity["snapshot"]["calendar_events"]), 1)
            self.assertEqual(len(productivity["snapshot"]["notes"]), 1)

    def test_copilot_can_combine_analytics_and_productivity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            result = service.copilot(
                "Compare this week vs last week revenue by country and create a task to share the findings tomorrow at 9am"
            )
            self.assertIn("analytics", result["domains"])
            self.assertIn("productivity", result["domains"])
            self.assertIsNotNone(result["analytics"])
            self.assertIsNotNone(result["productivity"])
            self.assertGreater(len(result["steps"]), 0)

    def test_copilot_can_retrieve_old_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            service.copilot("save a note that the client prefers country-level revenue summaries")
            result = service.copilot("find notes about country-level revenue")
            self.assertIn("productivity", result["domains"])
            productivity = result["productivity"]
            self.assertEqual(productivity["actions"][0]["type"], "note_search")
            self.assertGreaterEqual(len(productivity["actions"][0]["result"]), 1)
            self.assertIn("country-level revenue", productivity["actions"][0]["result"][0]["content"])

    def test_copilot_can_show_recent_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            service.copilot("save a note that the BigQuery demo tables are ready")
            service.copilot("save a note that the ADK UI is deployed")
            result = service.copilot("show recent notes")
            productivity = result["productivity"]
            self.assertEqual(productivity["actions"][0]["type"], "note_search")
            self.assertGreaterEqual(len(productivity["actions"][0]["result"]), 2)

    def test_note_lookup_does_not_trigger_analytics_just_for_note_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            service.copilot("save a note that the client prefers country-level revenue summaries")
            result = service.copilot("find notes about country-level revenue")
            self.assertNotIn("analytics", result["domains"])
            self.assertIn("productivity", result["domains"])

    def test_copilot_can_retrieve_calendar_events_by_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            service.copilot("Schedule demo rehearsal tomorrow at 5pm")
            result = service.copilot("find events about demo rehearsal")
            productivity = result["productivity"]
            self.assertEqual(productivity["actions"][0]["type"], "calendar_list")
            self.assertGreaterEqual(len(productivity["actions"][0]["result"]), 1)
            self.assertIn("demo rehearsal", productivity["actions"][0]["result"][0]["title"].lower())

    def test_copilot_can_show_upcoming_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            service.copilot("Schedule demo rehearsal tomorrow at 5pm")
            service.copilot("Schedule client check-in next week at 3pm")
            result = service.copilot("show upcoming events")
            productivity = result["productivity"]
            self.assertEqual(productivity["actions"][0]["type"], "calendar_list")
            self.assertGreaterEqual(len(productivity["actions"][0]["result"]), 2)

    def test_calendar_lookup_does_not_trigger_analytics_just_for_event_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            service.copilot("Schedule revenue review tomorrow at 4pm")
            result = service.copilot("find events about revenue review")
            self.assertNotIn("analytics", result["domains"])
            self.assertIn("productivity", result["domains"])

    def test_copilot_can_send_slack_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            result = service.copilot("send a slack message that the demo environment is ready")
            productivity = result["productivity"]
            self.assertEqual(productivity["actions"][0]["type"], "slack_message")
            self.assertTrue(productivity["actions"][0]["result"]["delivered"])
            self.assertIn("demo environment is ready", productivity["actions"][0]["result"]["message"])

    def test_slack_message_does_not_trigger_analytics_for_message_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(sqlite_db_path=os.path.join(tmp_dir, "copilot.db"), demo_anchor_date="2026-04-06")
            service = build_service(settings)
            result = service.copilot("notify the team that revenue review is moved to tomorrow")
            self.assertNotIn("analytics", result["domains"])
            self.assertIn("productivity", result["domains"])
