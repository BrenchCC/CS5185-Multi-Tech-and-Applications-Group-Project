"""Shared encoding services for the terminal UI and automation."""

import os
import sys
import csv
import json
import math
import time
import queue
import hashlib
import logging
import platform
import threading
import subprocess
from pathlib import Path
from fractions import Fraction
from importlib.metadata import version
from datetime import datetime, timezone

import cv2
import torch
import numpy as np
from pytorch_msssim import ms_ssim

sys.path.append(os.getcwd())

from adaptive_encoding.llm import llm_decision

logger = logging.getLogger(__name__)

ATTEMPT_STRATEGIES = {
    "hybrid": ("rule", "rule", "llm"),
    "llm": ("llm", "llm", "llm"),
    "rule": ("rule", "rule", "rule"),
}

DEV_IDS = (
    "01",
    "02",
    "03",
    "04",
    "07",
    "08",
)
CANDIDATES = (
    ("medium", 1),
    ("medium", 2),
    ("slow", 1),
    ("slow", 2),
)
GROUPS = ("baseline_medium", "baseline_slow", "rule")
FEATURE_VERSION = "gray-mad-canny-100-200-320x180-v1"
THREADS = 2
METRIC_CONFIG = {
    "implementation": "pytorch-msssim",
    "version": version("pytorch-msssim"),
    "channel": "decoded native Y plane",
    "data_range": 255,
    "scales": 5,
    "win_size": 11,
    "win_sigma": 1.5,
    "weights": [
        0.0448,
        0.2856,
        0.3001,
        0.2363,
        0.1333,
    ],
    "temporal_aggregation": "arithmetic mean of per-frame MS-SSIM",
    "psnr_aggregation": "all-frame pixel SSE before logarithm",
}


class Cancelled(RuntimeError):
    """Indicate a user-requested cancellation."""


class Context:
    """Manage progress and cancellation; callback receives event dictionaries."""

    def __init__(self, callback = None, cancel = None):
        """Initialize callback and optional threading.Event cancellation token."""
        self.callback = callback or (lambda event: None)
        self.cancel = cancel or threading.Event()

    def check(self):
        """Raise when the shared cancellation token is set."""
        if self.cancel.is_set():
            raise Cancelled("Cancelled by user")

    def emit(self, stage, **values):
        """Send stage and associated values to the progress consumer."""
        self.callback({"stage": stage, **values})


def save_json(path, data):
    """Atomically save data to path as strict JSON without NaN or Infinity."""
    path = Path(path)
    path.parent.mkdir(parents = True, exist_ok = True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent = 2, allow_nan = False) + "\n")
    temporary.replace(path)


def sha256(path):
    """Return the SHA-256 digest of the file at path."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture(command, context = None):
    """Run command arguments with cancellable output capture using context."""
    context = context or Context()
    context.check()
    process = subprocess.Popen(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout = 0.2)
                break
            except subprocess.TimeoutExpired:
                context.check()
        if process.returncode:
            raise RuntimeError(stderr.decode(errors = "replace")[-4000:])
        return stdout.decode()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout = 3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def probe(path, context = None):
    """Inspect all decoded frame timestamps and video properties of path."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_streams",
        "-show_frames",
        "-show_packets",
        "-show_entries",
        "stream=width,height,pix_fmt,avg_frame_rate,time_base,duration:frame=best_effort_timestamp_time,duration_time:packet=size",
        "-of",
        "json",
        str(path),
    ]
    data = json.loads(capture(command, context))
    stream = data["streams"][0]
    # 部分 ffprobe 版本合并帧与包 / Some versions interleave frames and packets.
    entries = data.get("packets_and_frames", [])
    frames = data.get("frames", []) or [
        entry for entry in entries if entry.get("type") == "frame"
    ]
    packets = data.get("packets", []) or [
        entry for entry in entries if entry.get("type") == "packet"
    ]
    pts = [float(frame["best_effort_timestamp_time"]) for frame in frames]
    if not pts or any(b <= a for a, b in zip(pts, pts[1:])):
        raise ValueError("Missing or non-increasing presentation timestamps")
    fps = Fraction(stream["avg_frame_rate"])
    if fps <= 0:
        raise ValueError("Invalid frame rate")
    duration = pts[-1] - pts[0] + float(frames[-1].get("duration_time", 1 / float(fps)))
    return {
        "path": str(Path(path).resolve()),
        "bytes": Path(path).stat().st_size,
        "width": stream["width"],
        "height": stream["height"],
        "pix_fmt": stream["pix_fmt"],
        "fps": str(fps),
        "time_base": stream["time_base"],
        "duration_s": duration,
        "frame_count": len(pts),
        "pts": pts,
        "video_packet_bytes": sum(int(packet["size"]) for packet in packets),
    }


def check_alignment(reference, output):
    """Reject output if its dimensions, frame sequence or timing differ from reference."""
    for field in (
        "width",
        "height",
        "fps",
        "frame_count",
    ):
        if reference[field] != output[field]:
            raise ValueError(f"Integrity mismatch: {field}")
    tolerance = max(
        float(Fraction(reference["time_base"])), float(Fraction(output["time_base"]))
    )
    ref_pts = np.array(reference["pts"]) - reference["pts"][0]
    out_pts = np.array(output["pts"]) - output["pts"][0]
    if np.max(np.abs(ref_pts - out_pts)) > tolerance + 1e-6:
        raise ValueError("Integrity mismatch: presentation timestamps")
    if abs(reference["duration_s"] - output["duration_s"]) > tolerance + 1e-6:
        raise ValueError("Integrity mismatch: duration")


def check_environment(dataset, context = None):
    """Verify software and dataset files under dataset without encoding test videos."""
    context = context or Context()
    encoder = capture([
        "ffmpeg",
        "-hide_banner",
        "-h",
        "encoder=libx264",
    ], context)
    if "libx264" not in encoder:
        raise RuntimeError("FFmpeg libx264 encoder is unavailable")
    records = []
    for path in sorted(Path(dataset).glob("*.mp4")):
        context.check()
        context.emit("Checking input", video = path.name)
        info = probe(path, context)
        info["sha256"] = sha256(path)
        metadata = json.loads(
            (Path(dataset) / "metadata" / (path.stem + ".json")).read_text()
        )
        if info["sha256"] != metadata["sha256"] or info["bytes"] != metadata["bytes"]:
            raise ValueError(f"Input hash or size mismatch: {path.name}")
        for field in ("width", "height"):
            if info[field] != metadata[field]:
                raise ValueError(f"Input {field} mismatch: {path.name}")
        if info["fps"] != "30" or info["pix_fmt"] != "yuv420p":
            raise ValueError(f"Unsupported input format: {path.name}")
        expected_frames = round(metadata["duration"] * metadata["fps"])
        if info["frame_count"] != expected_frames:
            raise ValueError(f"Input frame count mismatch: {path.name}")
        if abs(info["duration_s"] - metadata["duration"]) > float(Fraction(info["time_base"])) + 1e-6:
            raise ValueError(f"Input duration mismatch: {path.name}")
        audio = json.loads(capture([
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(path),
        ], context))
        if audio.get("streams"):
            raise ValueError(f"Audio is not supported in the course dataset: {path.name}")
        records.append(info)
    if len(records) != 12:
        raise ValueError(f"Expected 12 videos, found {len(records)}")
    return {"environment": environment(), "inputs": records}


def environment():
    """Return reproducibility metadata without reading credentials or environment secrets."""
    packages = {}
    for name in (
        "numpy",
        "opencv-python-headless",
        "torch",
        "pytorch-msssim",
        "textual",
        "matplotlib",
    ):
        packages[name] = version(name)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "python": sys.version,
        "packages": packages,
        "ffmpeg": capture(["ffmpeg", "-version"]),
        "ffprobe": capture(["ffprobe", "-version"]),
        "git_head": capture(["git", "rev-parse", "HEAD"]).strip(),
        "git_status": capture(["git", "status", "--short"]),
        "threads": THREADS,
        "cache_policy": "Features recomputed per task; no encoded candidate reuse in validation",
        "metrics": METRIC_CONFIG,
    }


def features(path, info, context):
    """Compute measured frame features for path using info and cancellation context."""
    video = cv2.VideoCapture(str(path))
    previous = None
    rows = []
    try:
        while True:
            context.check()
            ok, frame = video.read()
            if not ok:
                break
            gray = cv2.cvtColor(
                cv2.resize(frame, (320, 180), interpolation = cv2.INTER_AREA),
                cv2.COLOR_BGR2GRAY,
            )
            motion = (
                None
                if previous is None
                else float(np.abs(gray.astype(np.float32) - previous).mean() / 255)
            )
            rows.append(
                {
                    "frame": len(rows),
                    "time_s": info["pts"][len(rows)] - info["pts"][0],
                    "motion": motion,
                    "edge": float(
                        np.count_nonzero(cv2.Canny(gray, 100, 200)) / gray.size
                    ),
                }
            )
            previous = gray.astype(np.float32)
    finally:
        video.release()
    if len(rows) != info["frame_count"]:
        raise ValueError("Feature decoding did not produce the complete input")
    motion_values = [row["motion"] for row in rows[1:]]
    edge_values = [row["edge"] for row in rows]
    return {
        "version": FEATURE_VERSION,
        "motion_mean": float(np.mean(motion_values)),
        "motion_p90": float(np.percentile(motion_values, 90)),
        "edge_mean": float(np.mean(edge_values)),
        "edge_p90": float(np.percentile(edge_values, 90)),
        "timeline": rows,
    }


def budget(source_bytes, ratio, duration_s):
    """Compute integer target bytes and initial bitrate for ratio and duration_s."""
    if str(ratio) not in ("0.05", "0.02"):
        raise ValueError("Only 0.05 and 0.02 target ratios are supported")
    target = source_bytes * (5 if float(ratio) == 0.05 else 2) // 100
    return target, math.floor(0.98 * 8 * target / duration_s)


def next_bitrate(bitrate, target_bytes, actual_bytes):
    """Return a strictly lower bitrate after an oversized actual_bytes result."""
    return max(
        1, min(bitrate - 1, math.floor(bitrate * target_bytes / actual_bytes * 0.98))
    )


def stump_value(stump, values):
    """Evaluate a constant or threshold stump on the measured values dictionary."""
    if stump["feature"] is None:
        return stump["low"]
    return (
        stump["low"]
        if values[stump["feature"]] <= stump["threshold"]
        else stump["high"]
    )


def validate_decision(decision):
    """Reject decisions outside the preset and integer AQ white list."""
    if decision["preset"] not in ("medium", "slow"):
        raise ValueError("Invalid preset")
    if type(decision["aq_mode"]) is not int or decision["aq_mode"] not in (1, 2):
        raise ValueError("Invalid AQ mode")
    if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
        raise ValueError("Missing decision reason")
    return decision


def decide(values, strategy, policy = None):
    """Select parameters from measured values with strategy and optional frozen policy."""
    if strategy in ("baseline_medium", "baseline_slow"):
        preset = strategy.removeprefix("baseline_")
        return validate_decision(
            {
                "preset": preset,
                "aq_mode": 1,
                "reason": f"Fixed baseline: {preset}, AQ 1 for every input.",
                "method": strategy,
                "policy_version": "fixed-v1",
            }
        )
    if strategy != "rule" or policy is None:
        raise ValueError("A calibrated policy is required for the rule strategy")
    if policy["feature_version"] != FEATURE_VERSION:
        raise ValueError("Policy feature version does not match this implementation")
    reasons = []
    choices = {}
    for name in ("preset", "aq_mode"):
        stump = policy[name]
        choices[name] = stump_value(stump, values)
        if stump["feature"] is None:
            reasons.append(
                f"{name}: constant {choices[name]} selected by development calibration"
            )
        else:
            value = values[stump["feature"]]
            direction = "<=" if value <= stump["threshold"] else ">"
            reasons.append(
                f"{name}: {stump['feature']}={value:.8f} {direction} {stump['threshold']:.8f}, selecting {choices[name]}"
            )
    return validate_decision(
        {
            **choices,
            "reason": "; ".join(reasons),
            "method": "calibrated-threshold-rule",
            "policy_version": policy["policy_version"],
        }
    )


def encode_command(
    source,
    output,
    passlog,
    decision,
    bitrate,
    pass_number
):
    """Build FFmpeg arguments for source, output, passlog, decision, bitrate and pass_number."""
    validate_decision(decision)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        "-threads",
        str(THREADS),
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-c:v",
        "libx264",
        "-threads",
        str(THREADS),
        "-preset",
        decision["preset"],
        "-pix_fmt",
        "yuv420p",
        "-aq-mode",
        str(decision["aq_mode"]),
        "-b:v",
        str(bitrate),
        "-fps_mode",
        "passthrough",
        "-pass",
        str(pass_number),
        "-passlogfile",
        str(passlog),
        "-progress",
        "pipe:1",
        "-nostats",
    ]
    if pass_number == 1:
        command += ["-f", "null", os.devnull]
    else:
        command += ["-movflags", "+faststart", str(output)]
    return command


def run_encode(
    command,
    log_path,
    duration_s,
    context,
    pass_number
):
    """Run command, log stderr to log_path, and publish progress using duration_s and context."""
    context.check()
    messages = queue.Queue()
    with Path(log_path).open("wb") as log:
        process = subprocess.Popen(
            command,
            stdout = subprocess.PIPE,
            stderr = log,
            text = True,
        )

        def reader():
            """Forward FFmpeg progress lines to the supervising thread."""
            for line in process.stdout:
                messages.put(line.strip())

        thread = threading.Thread(target = reader, daemon = True)
        thread.start()
        try:
            while process.poll() is None or not messages.empty():
                context.check()
                try:
                    line = messages.get(timeout = 0.1)
                except queue.Empty:
                    continue
                if line.startswith("out_time_us="):
                    try:
                        progress = min(
                            1.0, max(0.0, int(line.split("=", 1)[1]) / 1e6 / duration_s)
                        )
                        context.emit(
                            "Encoding", pass_number = pass_number, progress = progress
                        )
                    except ValueError:
                        pass
            thread.join(timeout = 2)
            if process.returncode:
                raise subprocess.CalledProcessError(
                    process.returncode, command, stderr = f"See {log_path}"
                )
            return process.returncode
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout = 3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()


def raw_reader(path):
    """Start a native decoded Y-plane stream from video path."""
    return subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-threads",
            str(THREADS),
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-vf",
            "extractplanes=y",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ],
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
    )


def evaluate(
    source,
    output,
    reference,
    context
):
    """Measure complete aligned source and output against reference metadata using context."""
    output_info = probe(output, context)
    check_alignment(reference, output_info)
    capture(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-nostdin",
            "-threads",
            str(THREADS),
            "-i",
            str(output),
            "-map",
            "0:v:0",
            "-f",
            "null",
            os.devnull,
        ],
        context,
    )
    torch.set_num_threads(THREADS)
    readers = [raw_reader(source), raw_reader(output)]
    frame_size = reference["width"] * reference["height"]
    total_sse = 0.0
    scores = []
    try:
        with torch.inference_mode():
            for index in range(reference["frame_count"]):
                context.check()
                frames = [reader.stdout.read(frame_size) for reader in readers]
                if any(len(frame) != frame_size for frame in frames):
                    raise ValueError("Incomplete raw Y-plane sequence")
                arrays = [
                    np.frombuffer(frame, dtype = np.uint8)
                    .reshape(reference["height"], reference["width"])
                    .astype(np.float32)
                    for frame in frames
                ]
                difference = arrays[0].astype(np.float64) - arrays[1]
                total_sse += float(np.square(difference).sum())
                tensors = [torch.from_numpy(array)[None, None] for array in arrays]
                score = ms_ssim(
                    tensors[0],
                    tensors[1],
                    data_range = 255,
                    size_average = True,
                    win_size = 11,
                    win_sigma = 1.5,
                    weights = METRIC_CONFIG["weights"],
                ).item()
                if not math.isfinite(score):
                    raise ValueError("Non-finite MS-SSIM")
                scores.append(score)
                if index % 10 == 0:
                    context.emit(
                        "Evaluating", progress = (index + 1) / reference["frame_count"]
                    )
        for reader in readers:
            if reader.stdout.read(1):
                raise ValueError("Unexpected extra decoded frame data")
            stderr = reader.stderr.read().decode(errors = "replace")
            if reader.wait() or stderr.strip():
                raise RuntimeError(f"Raw decode failed: {stderr}")
    finally:
        for reader in readers:
            if reader.poll() is None:
                reader.terminate()
                try:
                    reader.wait(timeout = 3)
                except subprocess.TimeoutExpired:
                    reader.kill()
                    reader.wait()
            reader.stdout.close()
            reader.stderr.close()
    mse = total_sse / (frame_size * reference["frame_count"])
    return {
        "psnr_y_db": None if mse == 0 else 10 * math.log10(255**2 / mse),
        "psnr_infinite": mse == 0,
        "ms_ssim": float(np.mean(scores)),
        "per_frame_ms_ssim": scores,
        "decode_ok": True,
        "frame_count": output_info["frame_count"],
        "duration_s": output_info["duration_s"],
        "file_bitrate_bps": 8 * output_info["bytes"] / output_info["duration_s"],
        "video_bitrate_bps": 8
        * output_info["video_packet_bytes"]
        / output_info["duration_s"],
    }


def run_task(
    source,
    ratio,
    strategy,
    folder,
    context = None,
    policy = None,
    candidate = None,
    max_attempts = 3,
):
    """Encode source at ratio with strategy into folder, using context for progress,
    policy for rule selection, candidate for calibration and max_attempts as the round cap.
    """
    if type(max_attempts) is not int or max_attempts not in (1, 2, 3):
        raise ValueError("max_attempts must be an integer between 1 and 3")
    context = context or Context()
    started = time.perf_counter()
    folder = Path(folder)
    folder.mkdir(parents = True, exist_ok = False)
    record = {
        "video_id": Path(source).stem,
        "source_path": str(Path(source).resolve()),
        "target_ratio": ratio,
        "strategy": strategy,
        "status": "running",
        "attempts": [],
        "encode_time_s": 0.0,
        "eval_time_s": 0.0,
        "agent_time_s": 0.0,
        "decision_time_s": 0.0,
        "output_path": None,
        "metrics": None,
        "failure_reason": None,
    }
    try:
        context.check()
        context.emit("Reading input", video = Path(source).name)
        info = probe(source, context)
        record["input"] = info
        record["input_sha256"] = sha256(source)
        record["target_bytes"], bitrate = budget(
            info["bytes"], ratio, info["duration_s"]
        )
        record["initial_video_bps"] = bitrate
        context.emit("Analyzing content")
        feature_started = time.perf_counter()
        measured = features(source, info, context)
        record["feature_time_s"] = time.perf_counter() - feature_started
        save_json(folder / "features.json", measured)
        values = {key: measured[key] for key in ("motion_mean", "edge_mean")}
        values["bpp"] = bitrate / (
            info["width"] * info["height"] * float(Fraction(info["fps"]))
        )
        record["decision_inputs"] = values
        schedule = ATTEMPT_STRATEGIES.get(strategy, (strategy,) * 3)
        for attempt_number, controller in enumerate(schedule[:max_attempts], 1):
            context.check()
            attempt_dir = folder / f"attempt_{attempt_number}"
            attempt_dir.mkdir()
            output = attempt_dir / "output.mp4"
            attempt = {
                "number": attempt_number,
                "controller": controller,
                "bitrate_bps": bitrate,
                "commands": [],
                "return_codes": [],
                "status": "running",
            }
            attempt_started = time.perf_counter()
            attempt["pass_times_s"] = []
            attempt["eval_time_s"] = 0.0
            record["attempts"].append(attempt)
            try:
                decision_started = time.perf_counter()
                try:
                    if candidate:
                        decision = {
                            "preset": candidate[0],
                            "aq_mode": candidate[1],
                            "reason": "Exhaustive development-only candidate calibration",
                            "method": "calibration-search",
                            "policy_version": "calibration-v1",
                        }
                    elif controller == "llm":
                        context.emit("Requesting model decision", attempt = attempt_number)
                        audit = attempt["llm"] = {"validated": False}
                        payload = {
                            "features": {**values, **{key: measured.get(key) for key in ("motion_p90", "edge_p90")}},
                            "target_bytes": record["target_bytes"],
                            "current_video_bps": bitrate,
                            "attempt": attempt_number,
                            "previous_attempts": [
                                {
                                    "number": prior["number"],
                                    "status": prior["status"],
                                    "bitrate_bps": prior["bitrate_bps"],
                                    "actual_bytes": prior.get("actual_bytes"),
                                    "preset": prior.get("decision", {}).get("preset"),
                                    "aq_mode": prior.get("decision", {}).get("aq_mode"),
                                    "psnr_y_db": (prior.get("metrics") or {}).get("psnr_y_db"),
                                    "ms_ssim": (prior.get("metrics") or {}).get("ms_ssim"),
                                }
                                for prior in record["attempts"][:-1]
                            ],
                        }
                        if policy is not None:
                            reference = decide(values, "rule", policy)
                            payload["rule_reference"] = {key: reference[key] for key in ("preset", "aq_mode")}
                        try:
                            decision = validate_decision(llm_decision(payload, audit))
                            context.check()
                        except ValueError as error:
                            context.check()
                            attempt.update({"status": "decision_failed", "failure_reason": str(error)})
                            context.emit("Decision failed", attempt = attempt_number, reason = str(error))
                            continue
                        finally:
                            record["agent_time_s"] += audit.get("elapsed_s", 0.0)
                    else:
                        decision = decide(values, controller, policy)
                    attempt["decision"] = record["decision"] = validate_decision(decision)
                finally:
                    record["decision_time_s"] += time.perf_counter() - decision_started
                context.emit("Encoding", attempt = attempt_number, controller = controller, decision = decision["reason"])
                for pass_number in (1, 2):
                    command = encode_command(
                        source,
                        output,
                        attempt_dir / "pass",
                        decision,
                        bitrate,
                        pass_number,
                    )
                    attempt["commands"].append(command)
                    pass_started = time.perf_counter()
                    try:
                        code = run_encode(
                            command,
                            attempt_dir / f"pass_{pass_number}.log",
                            info["duration_s"],
                            context,
                            pass_number,
                        )
                        attempt["return_codes"].append(code)
                    except Exception as error:
                        attempt["return_codes"].append(
                            getattr(error, "returncode", None)
                        )
                        raise
                    finally:
                        elapsed = time.perf_counter() - pass_started
                        record["encode_time_s"] += elapsed
                        attempt["pass_times_s"].append(elapsed)
                attempt["actual_bytes"] = output.stat().st_size
                evaluation_started = time.perf_counter()
                try:
                    attempt["metrics"] = evaluate(
                        source,
                        output,
                        info,
                        context,
                    )
                finally:
                    elapsed = time.perf_counter() - evaluation_started
                    record["eval_time_s"] += elapsed
                    attempt["eval_time_s"] = elapsed
                if attempt["actual_bytes"] <= record["target_bytes"]:
                    attempt["status"] = "success"
                    record.update(
                        {
                            "status": "success",
                            "selected_attempt": attempt_number,
                            "actual_bytes": attempt["actual_bytes"],
                            "output_path": str(output.resolve()),
                            "output_sha256": sha256(output),
                            "metrics": attempt["metrics"],
                        }
                    )
                    break
                attempt["status"] = "oversized"
                context.emit("Output oversized", attempt = attempt_number, actual_bytes = attempt["actual_bytes"], target_bytes = record["target_bytes"])
                next_rate = next_bitrate(
                    bitrate, record["target_bytes"], attempt["actual_bytes"]
                )
                attempt["adjustment_reason"] = (
                    "Output exceeded full MP4 byte budget; reduce bitrate by measured ratio with 2% margin"
                )
                attempt["next_bitrate_bps"] = next_rate
                bitrate = next_rate
            except Cancelled:
                attempt["status"] = "cancelled"
                raise
            except Exception as error:
                attempt["status"] = "failed"
                attempt["failure_reason"] = str(error)
                # 硬错误停止任务 / A hard process or integrity error stops this task.
                raise
            finally:
                attempt["total_time_s"] = time.perf_counter() - attempt_started
                save_json(attempt_dir / "attempt.json", attempt)
                save_json(folder / "task.json", record)
        if record["status"] != "success":
            record["status"] = "failed"
            last_error = record["attempts"][-1].get("failure_reason")
            limit = {1: "one attempt", 2: "two attempts", 3: "three attempts"}[max_attempts]
            record["failure_reason"] = f"No valid output within {limit}"
            if last_error:
                record["failure_reason"] += f": {last_error}"
    except Cancelled as error:
        record["status"] = "cancelled"
        record["failure_reason"] = str(error)
    except Exception as error:
        record["status"] = "failed"
        record["failure_reason"] = str(error)
    finally:
        # 日志耗时单独记录 / Include the measured first final-log write in total time.
        record["total_time_s"] = time.perf_counter() - started
        save_json(folder / "task.json", record)
        record["total_time_s"] = time.perf_counter() - started
        save_json(folder / "task.json", record)
    context.emit("Task complete", status = record["status"], result = record)
    return record


def summarize(folder):
    """Create an English summary CSV from all task records under folder."""
    folder = Path(folder)
    records = [
        json.loads(path.read_text()) for path in sorted(folder.rglob("task.json"))
    ]
    columns = [
        "video_id",
        "target_ratio",
        "strategy",
        "status",
        "target_bytes",
        "actual_bytes",
        "preset",
        "aq_mode",
        "psnr_y_db",
        "ms_ssim",
        "file_bitrate_bps",
        "video_bitrate_bps",
        "encode_time_s",
        "agent_time_s",
        "eval_time_s",
        "total_time_s",
        "attempts",
        "reason",
        "failure_reason",
        "output_path",
    ]
    with (folder / "summary.csv").open("w", newline = "") as handle:
        writer = csv.DictWriter(handle, fieldnames = columns)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key) for key in columns}
            row.update(
                {
                    key: record.get("decision", {}).get(key)
                    for key in ("preset", "aq_mode", "reason")
                }
            )
            row.update(
                {
                    key: (record.get("metrics") or {}).get(key)
                    for key in (
                        "psnr_y_db",
                        "ms_ssim",
                        "file_bitrate_bps",
                        "video_bitrate_bps",
                    )
                }
            )
            if (record.get("metrics") or {}).get("psnr_infinite"):
                row["psnr_y_db"] = "infinity"
            row["attempts"] = len(record["attempts"])
            # 防止模型理由在表格软件中成为公式 / Keep model rationale as spreadsheet text.
            if (row["reason"] or "").lstrip().startswith(("=", "+", "-", "@")):
                row["reason"] = "'" + row["reason"]
            writer.writerow(row)
    return records
