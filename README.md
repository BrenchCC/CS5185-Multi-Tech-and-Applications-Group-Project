# CS5185 Adaptive Encoding Lab

[中文 README](README_ZH.md) · [中文使用指南](docs/guidance/usage_zh.md)

An English terminal interface for content-adaptive H.264 encoding under strict file-size budgets. The default schedule is **rule, rule, LLM**. Rule-only and LLM-only schedules use their respective controller for up to three slots. The first valid output ends the task. To enable Ark, copy `.env.example` to `.env` and configure your key and endpoint. Ark receives numerical summaries and selects only the preset and AQ mode.

## Installation and launch

Use Python 3.10 and a separately installed FFmpeg/ffprobe build with libx264. The tested environment and exact versions are saved in each run's `manifest.json`.

Run the commands below from the repository root.

```bash
pip install -r requirements.txt
python main.py
```

The terminal opens an interactive application. Use Tab/Shift+Tab to move focus, arrow keys to choose options, Enter to activate controls, and the mouse to click. F1 opens task setup, F2 opens the monitor, and F3 opens results. Ctrl+C requests exit; active work is stopped and cleaned up after confirmation. A larger terminal (approximately 110 columns by 42 rows) provides the clearest view; smaller windows scroll.

1. Open **Environment & Data** and run **Check environment**. The course dataset must be available locally under `CS5185_Project_Video_Dataset/`, including its metadata. Source media and licenses are not redistributed with the code.
2. Open **Task Setup**. Choose a development video, a 5% or 2% target, and a fixed baseline to test the pipeline immediately.
3. Select **Calibrate rules** to run the four parameter combinations on the development set (48 configuration tasks). The resulting frozen policy is saved to `runs/policy.json` and inside the calibration run.
4. Select **Run selected** with the rule strategy, or **Validate dev set** for the 36 independent comparison tasks.
5. Open **Results**, load a run folder, select rows to inspect decisions, and export CSV. Feature charts and aligned frame comparisons are saved under the run's `evidence/` directory.

Calibration and validation can take tens of minutes on a laptop. Jobs execute sequentially with two encoder threads. Cancel preserves completed results and marks interrupted work explicitly. There is no automatic resume; a new launch creates a new run directory.

## Method and evidence

Read [Method and evaluation](docs/adaptive_encoding_method.md) for feature definitions, the rule-search objective, dataset isolation, metric settings, and retry behavior. Each run saves its evidence under the configured output directory.

The decision space is deliberately small: preset `medium` or `slow`, and AQ mode 1 or 2. Two fixed baselines use `medium/AQ 1` and `slow/AQ 1`. Budget control and evaluation are identical across strategies. All successful outputs preserve resolution, frame rate, frame count and presentation timing. Neither cropping nor frame dropping is used to meet a budget.

## Reproducible automation

The UI is the default entry point. Optional commands use the same services:

```bash
python main.py check
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02 --strategy baseline_medium
python main.py calibrate
python main.py batch --policy runs/policy.json
python main.py summarize --folder runs/EXISTING_RUN_DIRECTORY
```

Replace `EXISTING_RUN_DIRECTORY` with a real run name. `--dataset` and `--output` set local directories. `--policy` selects a frozen rule file; calibrating a different output directory does not change the CLI's default policy path, so pass it explicitly. The default batch operates only on development IDs 01, 02, 03, 04, 07 and 08. The single-video automation command accepts an explicit path, so callers must preserve the reserved-set boundary themselves.

## Output layout

```text
runs/
  policy.json
  TIMESTAMP_calibration/
    manifest.json
    policy.json
    queue.json
    summary.csv
    VIDEO_RATIO_PRESET_AQ/
      features.json
      task.json
      attempt_1/
        output.mp4
        pass_1.log
        pass_2.log
        attempt.json
    evidence/
  TIMESTAMP_validation/
    manifest.json
    policy.json
    summary.csv
    ...
```

Each attempt has a unique x264 pass-log prefix. Files are retained locally under ignored `runs/`; no output overwrites an input. JSON includes exact byte counts, hashes, commands, status, quality, timing and decision evidence. CSV uses `infinity` for a perfect PSNR match; strict JSON uses `psnr_y_db: null` with `psnr_infinite: true`. Video-packet bitrate and whole-file bitrate are separate fields.

## Tests

```bash
pip install pytest==9.0.3
python -m pytest -q
```

Tests cover integer budgets, invalid decisions, rule boundaries, missing frames and timestamp errors, oversized retries, failed passes, cancellation and terminal interactions. Actual dataset runs are documented separately; mock tests are not presented as encoding evidence.

For the slower, opt-in checks using real course media:

```bash
python tests/verify_real_pipeline.py
```

This records reference-to-self metrics and deliberately triples the initial bitrate to verify a real oversize correction. Debug evidence is saved separately from calibration and validation results.

## Boundaries

The first release is a local terminal application, not a web or desktop GUI. It does not upload video, modify x264, train a model, or claim that adaptive choices always improve quality. Development-set validation is not a held-out test conclusion. Keep the original dataset license and source information with any shared materials.
