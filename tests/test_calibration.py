"""Development isolation and deterministic threshold search tests."""

import os
import sys



sys.path.append(os.getcwd())

from adaptive_encoding.core import CANDIDATES
from adaptive_encoding.experiments import choose_rules, fit_policy

def fake_records():
    """Return a small candidate matrix with opposing preferences across feature levels."""
    records = []
    for video, motion in (("01_example", 0.01), ("02_example", 0.1), ("03_example", 0.2)):
        for ratio in (0.05, 0.02):
            for preset, aq in CANDIDATES:
                preferred = (preset == "slow") == (motion > 0.05)
                records.append({
                    "video_id": video,
                    "target_ratio": ratio,
                    "decision_inputs": {"motion_mean": motion, "edge_mean": 0.1, "bpp": ratio},
                    "decision": {"preset": preset, "aq_mode": aq},
                    "status": "success",
                    "metrics": {"ms_ssim": 0.99 if preferred else 0.9, "psnr_y_db": 40 if preferred else 30, "psnr_infinite": False},
                    "encode_time_s": 1 if aq == 1 else 2,
                    "input_sha256": "synthetic-test-only",
                })
    return records


def test_rule_calibration_explains_measured_preference():
    """The selected rule uses measured motion rather than synthetic video identifiers."""
    policy = fit_policy(fake_records())
    assert policy["preset"]["feature"] == "motion_mean"
    assert policy["preset"]["low"] == "medium"
    assert policy["preset"]["high"] == "slow"
    assert policy["aq_mode"]["feature"] is None
    assert policy["aq_mode"]["low"] == 1
    assert len(policy["held_out"]) == 6
    assert policy == fit_policy(fake_records())
    for fold in policy["held_out"]:
        # Thresholds are midpoints computed without either budget of the held-out video.
        remaining = [record for record in fake_records() if record["video_id"] != fold["video_id"]]
        recomputed = fit_fold(remaining)
        assert fold["preset_rule"] == recomputed["preset"]
        assert fold["aq_rule"] == recomputed["aq_mode"]


def fit_fold(records):
    """Fit one search fold directly from candidate records without recursive validation."""
    from adaptive_encoding.experiments import calibration_samples
    return choose_rules(calibration_samples(records))
