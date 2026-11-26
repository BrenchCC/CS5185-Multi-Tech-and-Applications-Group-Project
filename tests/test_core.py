"""Budget, integrity and subprocess failure regression tests."""

import os
import sys
import json
import threading
from pathlib import Path

import pytest

sys.path.append(os.getcwd())

from adaptive_encoding import core
from adaptive_encoding.core import decide, validate_decision, run_task, save_json
from adaptive_encoding.core import Context, Cancelled, budget, next_bitrate, check_alignment

def test_integer_budget_and_rate():
    """Budget flooring must match exact integer arithmetic at both ratios."""
    assert budget(63899977, 0.05, 5) == (3194998, 5009756)
    assert budget(41183285, 0.02, 2.5)[0] == 823665
    assert next_bitrate(1000, 100, 120) == 816
    with pytest.raises(ValueError):
        budget(1000, 0.1, 5)


def test_decision_boundary_and_invalid_aq():
    """Threshold equality selects the low branch and LLM never invokes a provider."""
    policy = {
        "feature_version": core.FEATURE_VERSION,
        "policy_version": "test",
        "preset": {
            "feature": "bpp",
            "threshold": 0.1,
            "low": "slow",
            "high": "medium",
        },
        "aq_mode": {"feature": None, "low": 1},
    }
    assert decide({"bpp": 0.1}, "rule", policy)["preset"] == "slow"
    assert decide({"bpp": 0.1001}, "rule", policy)["preset"] == "medium"
    with pytest.raises(ValueError, match = "AQ"):
        validate_decision({"preset": "medium", "aq_mode": True, "reason": "test"})


def test_alignment_rejects_missing_frames_and_shift():
    """A shared prefix cannot hide missing frames or incorrect timestamps."""
    reference = {
        "width": 1280,
        "height": 720,
        "fps": "30",
        "frame_count": 3,
        "time_base": "1/15360",
        "pts": [0, 1 / 30, 2 / 30],
        "duration_s": 0.1,
    }
    check_alignment(reference, dict(reference))
    with pytest.raises(ValueError, match = "frame_count"):
        check_alignment(reference, {**reference, "frame_count": 2})
    with pytest.raises(ValueError, match = "timestamps"):
        check_alignment(reference, {**reference, "pts": [0, 1 / 30, 0.08]})
    with pytest.raises(ValueError, match = "duration"):
        check_alignment(reference, {**reference, "duration_s": 0.2})


def configure_fake_task(monkeypatch):
    """Configure monkeypatch with a minimal source and deterministic feature extraction."""
    monkeypatch.setattr(
        core,
        "probe",
        lambda *_: {
            "bytes": 10000,
            "duration_s": 5,
            "width": 1280,
            "height": 720,
            "fps": "30",
        },
    )
    monkeypatch.setattr(core, "sha256", lambda *_: "test-hash")
    monkeypatch.setattr(
        core, "features", lambda *_: {"motion_mean": 0.01, "edge_mean": 0.1}
    )
    monkeypatch.setattr(
        core,
        "evaluate",
        lambda *_: {"ms_ssim": 0.99, "psnr_y_db": 40, "psnr_infinite": False},
    )


def test_oversize_retry_and_valid_candidate_preservation(tmp_path, monkeypatch):
    """An oversized output retries; the first valid output stops later attempts."""
    configure_fake_task(monkeypatch)
    commands = []

    def fake_encode(command, *_):
        """Write oversized first and valid second candidate using command output path."""
        commands.append(command)
        if command[-1].endswith("output.mp4"):
            Path(command[-1]).write_bytes(
                b"x" * (600 if "attempt_1" in command[-1] else 400)
            )
        return 0

    monkeypatch.setattr(core, "run_encode", fake_encode)
    result = run_task(
        "source.mp4",
        0.05,
        "baseline_medium",
        tmp_path / "task",
    )
    assert result["status"] == "success"
    assert result["selected_attempt"] == 2
    assert len(commands) == 4
    assert (
        len({command[command.index("-passlogfile") + 1] for command in commands}) == 2
    )
    assert result["attempts"][1]["bitrate_bps"] < result["attempts"][0]["bitrate_bps"]
    assert Path(result["output_path"]).stat().st_size == 400


def test_three_attempt_exhaustion(tmp_path, monkeypatch):
    """A persistently oversized task fails after exactly three double passes."""
    configure_fake_task(monkeypatch)

    def fake_encode(command, *_):
        """Write a fixed oversized candidate from command."""
        if command[-1].endswith("output.mp4"):
            Path(command[-1]).write_bytes(b"x" * 600)
        return 0

    monkeypatch.setattr(core, "run_encode", fake_encode)
    result = run_task(
        "source.mp4",
        0.05,
        "baseline_medium",
        tmp_path / "task",
    )
    assert result["status"] == "failed"
    assert len(result["attempts"]) == 3
    assert result["output_path"] is None


def test_failed_pass_and_precancel(tmp_path, monkeypatch):
    """Failed passes and cancelled work never produce success records."""
    configure_fake_task(monkeypatch)

    def fail(*_):
        """Simulate an FFmpeg process failure."""
        raise RuntimeError("Injected pass failure")

    monkeypatch.setattr(core, "run_encode", fail)
    result = run_task(
        "source.mp4",
        0.05,
        "baseline_medium",
        tmp_path / "failed",
    )
    assert result["status"] == "failed"
    assert result["attempts"][0]["return_codes"] == [None]
    cancel = threading.Event()
    cancel.set()
    context = Context(cancel = cancel)
    result = run_task(
        "source.mp4",
        0.05,
        "baseline_medium",
        tmp_path / "cancelled",
        context,
    )
    assert result["status"] == "cancelled"
    assert not result["attempts"]


def test_strict_json_infinite_representation(tmp_path):
    """Infinity is represented by an explicit flag with a null numeric value."""
    path = tmp_path / "metric.json"
    save_json(path, {"psnr_y_db": None, "psnr_infinite": True})
    assert json.loads(path.read_text())["psnr_infinite"] is True
    with pytest.raises(ValueError):
        save_json(path, {"value": float("inf")})


def test_real_process_cancellation(tmp_path):
    """Cancellation terminates a live subprocess even when it emits no progress."""
    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set)
    timer.start()
    with pytest.raises(Cancelled):
        core.run_encode(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            tmp_path / "stderr.log",
            1,
            Context(cancel = cancel),
            1,
        )
    timer.join()


@pytest.mark.parametrize("strategy,controllers", [
    ("hybrid", ["rule", "rule", "llm"]),
    ("llm", ["llm", "llm", "llm"]),
    ("rule", ["rule", "rule", "rule"]),
])
def test_attempt_controller_order(strategy, controllers, tmp_path, monkeypatch):
    """Exercise all three strategy orders with oversized outputs and mock model decisions."""
    configure_fake_task(monkeypatch)
    policy = {
        "feature_version": core.FEATURE_VERSION,
        "policy_version": "test",
        "preset": {"feature": None, "low": "medium"},
        "aq_mode": {"feature": None, "low": 1},
    }
    calls = []

    def fake_llm(payload, audit):
        """Record payload and create a whitelisted decision with audit timing."""
        calls.append(payload)
        audit["elapsed_s"] = 0.1
        return {"preset": "slow", "aq_mode": 2, "reason": "Measured edge density", "method": "llm"}

    def oversized(command, *_):
        """Produce an oversized output at the path at the end of command."""
        if command[-1].endswith("output.mp4"):
            Path(command[-1]).write_bytes(b"x" * 600)
        return 0

    monkeypatch.setattr(core, "llm_decision", fake_llm)
    monkeypatch.setattr(core, "run_encode", oversized)
    result = run_task("source.mp4", 0.05, strategy, tmp_path / "task", policy = policy)
    assert [item["controller"] for item in result["attempts"]] == controllers
    assert [item["attempt"] for item in calls] == [index for index, value in enumerate(controllers, 1) if value == "llm"]
    for call in calls:
        assert len(call["previous_attempts"]) == call["attempt"] - 1
        assert "source_path" not in call
    assert result["status"] == "failed"


def test_llm_errors_consume_slots_without_encoding(tmp_path, monkeypatch):
    """Reject each invalid model decision without encoding or switching controller."""
    configure_fake_task(monkeypatch)

    def fail(payload, audit):
        """Represent a rejected payload's model response."""
        raise ValueError("Invalid model JSON")

    monkeypatch.setattr(core, "llm_decision", fail)
    result = run_task("source.mp4", 0.05, "llm", tmp_path / "task")
    assert [item["status"] for item in result["attempts"]] == ["decision_failed"] * 3
    assert all(not item["commands"] for item in result["attempts"])
    assert result["status"] == "failed"
