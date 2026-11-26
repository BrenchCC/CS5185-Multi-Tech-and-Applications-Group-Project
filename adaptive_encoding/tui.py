"""English Textual interface for the content-adaptive encoding laboratory."""

import os
import sys
import json
import logging
import threading
from pathlib import Path

from textual import work
from textual.message import Message
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Static, Input, Select, Button, Label
from textual.widgets import DataTable, ProgressBar, RichLog, TabbedContent, TabPane, Tabs

sys.path.append(os.getcwd())

from adaptive_encoding.experiments import create_run, calibrate, batch
from adaptive_encoding.core import DEV_IDS, Context, check_environment, run_task, save_json, summarize

logger = logging.getLogger(__name__)


class ExitPrompt(ModalScreen):
    """Confirm cancellation before leaving an active encoding run."""

    def compose(self) -> ComposeResult:
        """Yield the exit confirmation dialog."""
        with Vertical(id = "exit-dialog"):
            yield Label("A job is running. Stop it and exit?")
            with Horizontal():
                yield Button("Keep running", id = "keep", variant = "primary")
                yield Button("Stop and exit", id = "stop", variant = "error")

    def on_button_pressed(self, event: Button.Pressed):
        """Dismiss the dialog with the choice from event."""
        self.dismiss(event.button.id == "stop")


class JobEvent(Message):
    """Carry a background event dictionary to the UI event loop."""

    def __init__(self, payload):
        """Initialize the background payload."""
        super().__init__()
        self.payload = payload


class JobDone(Message):
    """Carry a completed job folder or error to the UI event loop."""

    def __init__(self, folder, error = None):
        """Initialize folder and optional error text."""
        super().__init__()
        self.folder = folder
        self.error = error


class EncoderApp(App):
    """Interactive terminal laboratory; dataset and output identify local directories."""

    TITLE = "CS5185 Adaptive Encoding Lab"
    SUB_TITLE = "Content-adaptive x264 · Rule and Ark decisions"
    BINDINGS = [
        Binding("q", "request_quit", "Quit"),
        Binding(
            "ctrl+c",
            "request_quit",
            "Quit",
            priority = True,
        ),
        Binding(
            "f1",
            "setup",
            "Task setup",
            priority = True,
        ),
        Binding(
            "f2",
            "monitor",
            "Monitor",
            priority = True,
        ),
        Binding(
            "f3",
            "results",
            "Results",
            priority = True,
        ),
    ]
    CSS = """
    Screen { background: #101820; color: #e5edf3; }
    Header { background: #19323f; }
    TabPane { padding: 1 2; }
    .intro { color: #83d9bd; margin-bottom: 1; }
    .field { margin-top: 1; color: #b7c9d5; }
    Input, Select { margin-bottom: 1; }
    .actions { height: auto; layout: horizontal; margin: 1 0; }
    .actions Button { margin-right: 1; min-width: 14; }
    #status { border: solid #428b82; padding: 1; height: auto; min-height: 5; }
    #queue { height: auto; margin: 1 0; }
    #log { height: 1fr; min-height: 10; border: solid #304956; }
    #results-table { height: 16; }
    #details { height: auto; min-height: 8; border: solid #304956; padding: 1; }
    #checks { height: auto; min-height: 10; border: solid #304956; padding: 1; }
    ProgressBar { margin: 1 0; }
    ExitPrompt { align: center middle; background: #00000080; }
    #exit-dialog { width: 60; height: 10; border: thick #428b82; background: #19323f; padding: 1 2; }
    #exit-dialog Horizontal { margin-top: 1; }
    #exit-dialog Button { margin-right: 2; }
    """

    def __init__(self, dataset = "CS5185_Project_Video_Dataset", output = "runs"):
        """Initialize dataset and output defaults without starting any jobs."""
        super().__init__()
        self.dataset = str(dataset)
        self.output = str(output)
        self.busy = False
        self.cancel_token = threading.Event()
        self.exit_when_done = False
        self.current_folder = None
        self.result_records = []
        self.phase = "Idle"
        self.video_name = "—"
        self.attempt_number = "—"
        self.pass_number = "—"

    def compose(self) -> ComposeResult:
        """Build four English pages and shared keyboard help."""
        yield Header()
        with TabbedContent(initial = "setup"):
            with TabPane("Environment & Data", id = "environment"):
                with VerticalScroll():
                    yield Static(
                        "PREFLIGHT / Verify tools and all 12 source hashes",
                        classes = "intro",
                    )
                    yield Label("Dataset directory", classes = "field")
                    yield Input(self.dataset, id = "dataset")
                    yield Button("Check environment", id = "check", variant = "primary")
                    yield Static(
                        "Not checked yet. This check does not encode reserved test videos.",
                        id = "checks",
                        markup = False,
                    )
            with TabPane("Task Setup", id = "setup"):
                with VerticalScroll():
                    yield Static(
                        "CONFIGURE / Analyze → decide → encode → verify",
                        classes = "intro",
                    )
                    yield Label("Video (development set)", classes = "field")
                    paths = sorted(
                        path
                        for path in Path(self.dataset).glob("*.mp4")
                        if path.name[:2] in DEV_IDS
                    )
                    yield Select(
                        [(path.name, str(path)) for path in paths],
                        value = str(paths[0]) if paths else Select.BLANK,
                        id = "video",
                    )
                    yield Label("Target file size")
                    yield Select(
                        [("5% of source bytes", 0.05), ("2% of source bytes", 0.02)],
                        value = 0.05,
                        allow_blank = False,
                        id = "ratio",
                    )
                    yield Label("Decision strategy")
                    yield Select(
                        [
                            ("Default: Rule → Rule → LLM", "hybrid"),
                            ("LLM only: three LLM slots", "llm"),
                            ("Rule only: three rule slots", "rule"),
                            ("Fixed medium / AQ 1", "baseline_medium"),
                            ("Fixed slow / AQ 1", "baseline_slow"),
                        ],
                        value = "hybrid",
                        allow_blank = False,
                        id = "strategy",
                    )
                    yield Static(
                        "The first valid output ends the run. Ark receives numeric summaries when an LLM slot is reached.",
                        classes = "intro",
                    )
                    yield Label("Output directory")
                    yield Input(self.output, id = "output")
                    yield Label(
                        "Frozen policy file (required for default, rule-only and validation)"
                    )
                    yield Input(str(Path(self.output) / "policy.json"), id = "policy")
                    with Horizontal(classes = "actions"):
                        yield Button("Run selected", id = "run", variant = "primary")
                        yield Button("Calibrate rules", id = "calibrate")
                    with Horizontal(classes = "actions"):
                        yield Button("Validate dev set", id = "batch", variant = "success")
                    yield Static(
                        "Calibration: 48 candidate tasks. Validation: 36 independent tasks.\nEach configuration allows at most 3 two-pass attempts. Reserved test videos are excluded.",
                        markup = False,
                    )
            with TabPane("Run Monitor", id = "monitor"):
                yield Static("IDLE / Ready for a task", id = "status", markup = False)
                yield Static("Queue: —", id = "queue", markup = False)
                yield ProgressBar(total = 100, show_eta = False, id = "progress")
                yield Button(
                    "Cancel run",
                    id = "cancel",
                    variant = "error",
                    disabled = True,
                )
                yield RichLog(
                    id = "log",
                    wrap = True,
                    markup = False,
                    max_lines = 1000,
                )
            with TabPane("Results", id = "results"):
                with VerticalScroll():
                    yield Static(
                        "INSPECT / Results and reproducible evidence", classes = "intro"
                    )
                    yield Input(
                        placeholder = "Existing run folder, e.g. runs/2026…_validation",
                        id = "history",
                    )
                    with Horizontal(classes = "actions"):
                        yield Button("Load results", id = "load")
                        yield Button("Export CSV", id = "export")
                    yield DataTable(id = "results-table", cursor_type = "row")
                    yield Static(
                        "Select a row to inspect parameters and the measured decision rationale.",
                        id = "details",
                        markup = False,
                    )
        yield Footer()

    def on_mount(self):
        """Initialize the results table after widgets are mounted."""
        self.query_one("#results-table", DataTable).add_columns(
            "Video",
            "Target",
            "Strategy",
            "Status",
            "Bytes",
            "PSNR Y",
            "MS-SSIM",
            "Encode (s)",
        )

    def on_input_changed(self, event: Input.Changed):
        """Refresh development-video choices when event changes the dataset directory."""
        if event.input.id == "dataset" and self.is_mounted and not self.busy:
            paths = sorted(
                path
                for path in Path(event.value).expanduser().glob("*.mp4")
                if path.name[:2] in DEV_IDS
            )
            self.query_one("#video", Select).set_options(
                [(path.name, str(path)) for path in paths]
            )
            self.query_one("#video", Select).value = (
                str(paths[0]) if paths else Select.BLANK
            )

    def action_setup(self):
        """Switch to task configuration."""
        self.switch_page("setup")

    def action_monitor(self):
        """Switch to running task progress."""
        self.switch_page("monitor")

    def action_results(self):
        """Switch to saved results."""
        self.switch_page("results")

    def switch_page(self, page):
        """Switch to page and move focus out of the previously active pane."""
        tabs = self.query_one(TabbedContent)
        self.screen.set_focus(tabs.query_one(Tabs))
        tabs.active = page

    def action_request_quit(self):
        """Exit immediately when idle, otherwise confirm stopping active work."""
        if self.busy:
            self.push_screen(ExitPrompt(), self.confirm_exit)
        else:
            self.exit()

    def confirm_exit(self, confirmed):
        """Stop work and wait for subprocess cleanup if confirmed is true."""
        if confirmed:
            self.exit_when_done = True
            self.cancel_token.set()
            self.query_one("#status", Static).update(
                "Stopping active work before exit…"
            )

    def set_busy(self, busy):
        """Apply busy state to controls so duplicate starts cannot occur."""
        self.busy = busy
        for identifier in (
            "check",
            "run",
            "calibrate",
            "batch",
            "load",
            "export",
        ):
            self.query_one(f"#{identifier}", Button).disabled = busy
        self.query_one("#cancel", Button).disabled = not busy

    def on_button_pressed(self, event: Button.Pressed):
        """Handle the requested action carried by event."""
        action = event.button.id
        if action == "cancel":
            self.cancel_token.set()
            self.query_one("#status", Static).update(
                "Cancellation requested. Cleaning up the active subprocess…"
            )
            return
        if action in ("load", "export"):
            try:
                value = self.query_one("#history", Input).value.strip()
                if not value:
                    raise ValueError("Enter an existing run folder first")
                folder = Path(value).expanduser()
                if not folder.is_dir():
                    raise ValueError("Choose an existing run folder")
                self.load_results(folder)
                if action == "export":
                    summarize(folder)
                    self.notify(f"CSV saved: {folder / 'summary.csv'}")
            except Exception as error:
                self.notify(str(error), severity = "error", timeout = 10)
            return
        if self.busy:
            return
        try:
            config = {
                "dataset": Path(self.query_one("#dataset", Input).value).expanduser(),
                "output": Path(self.query_one("#output", Input).value).expanduser(),
                "policy": Path(self.query_one("#policy", Input).value).expanduser(),
                "source": self.query_one("#video", Select).value,
                "ratio": self.query_one("#ratio", Select).value,
                "strategy": self.query_one("#strategy", Select).value,
            }
            if not config["dataset"].is_dir():
                raise ValueError("Dataset directory does not exist")
            if action == "run" and (
                config["source"] is Select.BLANK or not Path(config["source"]).is_file()
            ):
                raise ValueError("Select an existing development video")
            needs_policy = action == "batch" or (
                action == "run" and config["strategy"] in ("rule", "hybrid")
            )
            if needs_policy and not config["policy"].is_file():
                raise ValueError(
                    "Calibrate rules first, or choose an existing frozen policy file"
                )
            self.cancel_token = threading.Event()
            self.set_busy(True)
            self.phase = "Starting"
            self.query_one("#log", RichLog).clear()
            self.query_one("#log", RichLog).write(
                f"Starting {action}. Output root: {config['output']}"
            )
            self.action_monitor()
            self.execute(action, config)
        except Exception as error:
            self.notify(str(error), severity = "error", timeout = 10)

    @work(thread = True, exit_on_error = False)
    def execute(self, action, config):
        """Run action with config in a background worker; update UI only via messages."""
        context = Context(
            lambda payload: self.post_message(JobEvent(payload)), self.cancel_token
        )
        folder = None
        try:
            if action == "check":
                result = check_environment(config["dataset"], context)
                folder = create_run(config["output"], "check")
                save_json(folder / "input_check.json", result)
                context.emit("Check passed", inputs = len(result["inputs"]), report = result)
            elif action == "calibrate":
                folder = calibrate(config["dataset"], config["output"], context)
            elif action == "batch":
                folder = batch(
                    config["dataset"],
                    config["output"],
                    config["policy"],
                    context,
                )
            elif action == "run":
                policy = (
                    json.loads(config["policy"].read_text())
                    if config["strategy"] in ("rule", "hybrid")
                    else None
                )
                folder = create_run(config["output"], "single")
                context.emit("Run created", folder = str(folder.resolve()))
                run_task(
                    config["source"],
                    config["ratio"],
                    config["strategy"],
                    folder / "task",
                    context,
                    policy,
                )
                summarize(folder)
            self.post_message(JobDone(folder))
        except Exception as error:
            self.post_message(JobDone(folder, str(error)))

    def on_job_event(self, event: JobEvent):
        """Render background progress and results from event on the UI thread."""
        payload = event.payload
        self.phase = payload["stage"]
        self.video_name = payload.get("video", self.video_name)
        if self.phase in ("Reading input", "Requesting model decision") or (
            self.phase == "Encoding" and "controller" in payload
        ):
            self.pass_number = "—"
        self.attempt_number = payload.get("attempt", self.attempt_number)
        self.pass_number = payload.get("pass_number", self.pass_number)
        self.query_one("#status", Static).update(
            f"{self.phase.upper()}\nVideo: {self.video_name} | Attempt: {self.attempt_number} | Pass: {self.pass_number}"
        )
        if "progress" in payload:
            self.query_one("#progress", ProgressBar).update(
                total = 100, progress = payload["progress"] * 100
            )
        else:
            self.query_one("#progress", ProgressBar).update(total = None)
        if "total" in payload:
            self.query_one("#queue", Static).update(
                f"Queue: {payload['completed']} / {payload['total']} tasks completed"
            )
        if "folder" in payload:
            self.current_folder = Path(payload["folder"])
            self.query_one("#history", Input).value = payload["folder"]
        if payload["stage"] == "Check passed":
            report = payload["report"]
            lines = [
                f"PASS — verified {payload['inputs']} complete inputs and SHA-256 hashes.",
                report["environment"]["ffmpeg"].splitlines()[0],
                "Encoder: libx264 | Threads: 2 | Source pixel format: yuv420p",
                "Packages: " + ", ".join(f"{name} {value}" for name, value in report["environment"]["packages"].items()),
                "",
                "INPUTS / Actual bytes, frames, dimensions, frame rate, SHA-256 prefix",
            ]
            for info in report["inputs"]:
                lines.append(f"{Path(info['path']).name}: {info['bytes']} B | {info['frame_count']} frames | {info['width']}x{info['height']} | {info['fps']} fps | {info['sha256'][:16]}")
            self.query_one("#checks", Static).update("\n".join(lines))
        if "progress" not in payload:
            brief = {key: value for key, value in payload.items() if key not in ("result", "report")}
            self.query_one("#log", RichLog).write(str(brief))
        if "result" in payload:
            result = payload["result"]
            self.query_one("#log", RichLog).write(
                f"{result['status'].upper()} | bytes={result.get('actual_bytes', '—')} | {result.get('failure_reason') or result.get('decision', {}).get('reason', 'No decision')}"
            )

    def on_job_done(self, event: JobDone):
        """Restore controls and load results after worker completion reported by event."""
        self.set_busy(False)
        if event.folder:
            self.current_folder = Path(event.folder)
            self.query_one("#history", Input).value = str(event.folder)
            self.load_results(event.folder)
        outcome = (
            "FAILED"
            if event.error
            else ("CANCELLED" if self.cancel_token.is_set() else "FINISHED")
        )
        if (
            not event.error
            and not self.cancel_token.is_set()
            and any(record["status"] == "failed" for record in self.result_records)
        ):
            outcome = "COMPLETED WITH FAILURES"
        self.query_one("#status", Static).update(
            f"{outcome}\n{event.error or 'Review saved task records in Results.'}"
        )
        self.query_one("#progress", ProgressBar).update(
            total = 100, progress = 0 if event.error or self.cancel_token.is_set() else 100
        )
        if event.error:
            self.query_one("#log", RichLog).write(event.error)
            self.query_one("#checks", Static).update(
                f"Last operation failed: {event.error}"
            )
            self.notify(event.error, severity = "error", timeout = 10)
        if self.exit_when_done:
            self.exit()

    def load_results(self, folder):
        """Load all saved task records from folder and refresh the results table."""
        self.result_records = [json.loads(path.read_text()) for path in sorted(Path(folder).rglob("task.json"))]
        table = self.query_one("#results-table", DataTable)
        table.clear()
        for index, record in enumerate(self.result_records):
            metrics = record.get("metrics") or {}
            psnr = (
                "inf"
                if metrics.get("psnr_infinite")
                else f"{metrics['psnr_y_db']:.3f}"
                if metrics.get("psnr_y_db") is not None
                else "—"
            )
            ms = f"{metrics['ms_ssim']:.6f}" if "ms_ssim" in metrics else "—"
            table.add_row(
                record["video_id"],
                f"{record['target_ratio']:.0%}",
                record["strategy"],
                record["status"],
                str(record.get("actual_bytes", "—")),
                psnr,
                ms,
                f"{record['encode_time_s']:.2f}",
                key = str(index),
            )
        self.query_one("#details", Static).update(
            f"Loaded {len(self.result_records)} task records.\nCSV: {Path(folder) / 'summary.csv'}"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Display a selected task's traceable details from event."""
        record = self.result_records[int(event.row_key.value)]
        decision = record.get("decision", {})
        attempts = "\n".join(
            f"Attempt {item['number']} | {item.get('controller', record['strategy'])} | "
            f"{item['status']} | {item.get('actual_bytes', '—')} bytes"
            for item in record["attempts"]
        )
        self.query_one("#details", Static).update(
            f"{record['video_id']} | {record['target_ratio']:.0%} | {record['status']}\n"
            f"Parameters: {decision.get('preset', '—')} / AQ {decision.get('aq_mode', '—')}\n"
            f"Reason: {decision.get('reason', '—')}\n"
            f"Budget: {record.get('target_bytes', '—')} bytes | Actual: {record.get('actual_bytes', '—')} bytes\n"
            f"Output: {record.get('output_path') or '—'}\n"
            f"Failure: {record.get('failure_reason') or 'None'}\n"
            f"LLM decision time: {record.get('agent_time_s', 0):.2f} s\n{attempts}"
        )
