"""Run opt-in checks against real course media; not part of the quick pytest suite."""

import os
import sys
import time
import logging
from pathlib import Path
from unittest.mock import patch



sys.path.append(os.getcwd())

from adaptive_encoding import core
from adaptive_encoding.experiments import create_run

logger = logging.getLogger(__name__)


def main():
    """Record native-Y identity and a deliberately oversized real encoding experiment."""
    source = Path("CS5185_Project_Video_Dataset/01_FourPeople.mp4")
    folder = create_run("runs", "integration_checks")
    started = time.perf_counter()
    reference = core.probe(source)
    metrics = core.evaluate(
        source,
        source,
        reference,
        core.Context(),
    )
    assert metrics["psnr_infinite"] and metrics["psnr_y_db"] is None
    assert abs(metrics["ms_ssim"] - 1) < 1e-6
    core.save_json(folder / "self_comparison.json", {
        "source": str(source),
        "metrics": metrics,
        "time_s": time.perf_counter() - started,
    })
    original_budget = core.budget

    def oversized_budget(source_bytes, ratio, duration_s):
        """Triple only the initial rate for source_bytes, ratio and duration_s; keep target bytes."""
        target, bitrate = original_budget(source_bytes, ratio, duration_s)
        return target, bitrate * 3

    # 主动制造超限以验证真实反馈 / Inject oversize to verify actual bitrate correction.
    with patch.object(core, "budget", oversized_budget):
        result = core.run_task(
            source,
            0.02,
            "baseline_medium",
            folder / "forced_oversize"
        )
    assert result["status"] == "success", result["failure_reason"]
    assert result["attempts"][0]["status"] == "oversized"
    assert len(result["attempts"]) >= 2
    core.save_json(folder / "verification.json", {
        "self_comparison": "passed",
        "forced_oversize": "passed",
        "injected_condition": "Initial bitrate deliberately multiplied by 3; byte target and retry controller unchanged",
        "selected_attempt": result["selected_attempt"],
        "input_unchanged": core.sha256(source) == result["input_sha256"],
    })
    print(folder)


if __name__ == "__main__":
    logging.basicConfig(
        level = logging.INFO,
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers = [logging.StreamHandler()]
    )
    main()
