"""Headless terminal interaction tests using Textual Pilot."""

import os
import sys
import asyncio

from textual.widgets import TabbedContent, Button

sys.path.append(os.getcwd())

from adaptive_encoding.tui import EncoderApp, JobDone, JobEvent

def test_navigation_resize_and_policy_validation(tmp_path):
    """Navigation and missing-policy validation remain functional in small terminals."""

    async def scenario():
        """Exercise keyboard-driven navigation without starting encoding."""
        app = EncoderApp(output = str(tmp_path))
        async with app.run_test(size = (110, 42)) as pilot:
            await pilot.press("f2")
            assert app.query_one(TabbedContent).active == "monitor"
            await pilot.press("f3")
            assert app.query_one(TabbedContent).active == "results"
            await pilot.press("f1")
            await pilot.click("#run")
            await pilot.pause()
            assert not app.busy
            await pilot.resize_terminal(80, 24)
            await pilot.press("f2")
            assert app.query_one(TabbedContent).active == "monitor"

    asyncio.run(scenario())


def test_running_controls_progress_and_cancellation(tmp_path):
    """Busy controls reject duplicates, accept cancellation and restore after completion."""

    async def scenario():
        """Send worker messages through the real UI event loop."""
        app = EncoderApp(output = str(tmp_path))
        async with app.run_test(size = (110, 42)) as pilot:
            app.set_busy(True)
            assert app.query_one("#run", Button).disabled
            app.post_message(
                JobEvent(
                    {
                        "stage": "Encoding",
                        "progress": 0.5,
                        "pass_number": 2,
                        "attempt": 1,
                    }
                )
            )
            await pilot.press("f2")
            await pilot.pause()
            await pilot.click("#cancel")
            assert app.cancel_token.is_set()
            app.post_message(JobDone(None))
            await pilot.pause()
            assert not app.busy
            assert app.query_one("#cancel", Button).disabled
            await pilot.press("q")

    asyncio.run(scenario())


def test_blank_history_is_read_only(tmp_path):
    """Loading an empty history path must not create a CSV in the working directory."""
    async def scenario():
        """Exercise the empty-history error path through an actual button."""
        app = EncoderApp(output = str(tmp_path))
        async with app.run_test(size = (110, 42)) as pilot:
            await pilot.press("f3")
            await pilot.click("#load")
            await pilot.pause()
            assert not app.result_records
            assert not (tmp_path / "summary.csv").exists()
    asyncio.run(scenario())


def test_environment_details_are_visible(tmp_path):
    """Environment results expose package versions and actual input properties in English."""
    async def scenario():
        """Render a completed check message without invoking another full input scan."""
        from textual.widgets import Static
        app = EncoderApp(output = str(tmp_path))
        async with app.run_test(size = (110, 42)) as pilot:
            report = {
                "environment": {"ffmpeg": "ffmpeg test build", "packages": {"numpy": "test-version"}},
                "inputs": [{
                    "path": "/example/01_FourPeople.mp4",
                    "bytes": 100,
                    "frame_count": 150,
                    "width": 1280,
                    "height": 720,
                    "fps": "30",
                    "sha256": "abc123",
                }],
            }
            app.post_message(JobEvent({"stage": "Check passed", "inputs": 1, "report": report}))
            await pilot.pause()
            rendered = str(app.query_one("#checks", Static).render())
            assert "numpy test-version" in rendered
            assert "150 frames" in rendered
            assert "abc123" in rendered
    asyncio.run(scenario())
