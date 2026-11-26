# CS5185 Content-Adaptive Video Encoding

This project encodes a complete course video as an H.264 MP4 under a file-size limit of 5% or 2% of the original. The example below uses the supplied frozen rule and runs locally without API credentials. Run every command from the **project root**, the directory containing `main.py` and `requirements.txt`.

## 1. Set up the environment

The following versions were recorded on the local machine on 27 November 2026. Python package versions were read from the active project environment. The libx264 revision comes from the FourPeople encoding log.

| Component | Installed version |
| --- | --- |
| Operating system | macOS 26.2 (build 25C56), arm64 |
| Environment and runtime | Conda 25.5.1, Python 3.10.0, pip 26.0.1 |
| Encoding and inspection | FFmpeg 9.1, ffprobe 9.1 |
| FFmpeg build compiler | Apple clang 21.0.0 (clang-2100.4.1.1) |
| H.264 encoder | libx264 core 165, revision 3222 (b35605a) |
| Feature extraction | numpy 1.26.4, opencv-python-headless 4.10.0.84 |
| Quality evaluation | torch 2.12.1, pytorch-msssim 1.0.0 |
| Interface, plots and progress | textual 1.0.0, matplotlib 3.9.0, tqdm 4.66.4 |
| Ark integration | python-dotenv 1.2.2, volcengine-python-sdk 5.0.25 |

Install FFmpeg and ffprobe on your PATH using an FFmpeg build with `--enable-libx264`. Activate a Python 3.10 environment and run:

```bash
python --version
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -h encoder=libx264
pip install -r requirements.txt
```

The encoder query should list `Encoder libx264` and its supported options. The installed versions of all nine direct Python dependencies matched the pins in `requirements.txt`.

## 2. Prepare and check the inputs

Use the 12 original MP4s from the prepared course dataset, numbered 01 through 12. Place them directly in `CS5185_Project_Video_Dataset/`. Each video must have a JSON file with the same stem under `metadata/`. For example:

```text
CS5185_Project_Video_Dataset/
  01_FourPeople.mp4
  ...
  12_ControlledBurn.mp4
  metadata/
    01_FourPeople.json
    ...
    12_ControlledBurn.json
```

The course clips contain 30 fps, 8-bit YUV 4:2:0 video without audio. Keep the original filenames and bytes. The preflight checks each source against its supplied SHA-256, byte count, dimensions, frame count and duration. Run it before encoding:

```bash
python main.py check
```

A successful check prints the run directory containing `input_check.json`. If a hash or size fails, restore the matching course MP4 and metadata before continuing.

## 3. Encode one video

The following command encodes FourPeople at 2% using the policy included with the submission:

```bash
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02 --strategy rule --policy experiments/full_exps/policy.json
```

Use `--ratio 0.05` for the 5% target. The command prints a new `runs/<timestamp>_single/` directory. A successful task returns exit code zero. To launch the interactive terminal interface instead, run `python main.py` from the same directory.

## 4. Locate and verify the output

Open `task/task.json` inside the printed run directory. Check that `status` is `success` and `actual_bytes` is at most `target_bytes`. **The playable MP4 is the file named by `output_path`.** The field `selected_attempt` identifies the accepted round. Earlier attempts can leave playable files that exceed the budget.

| FourPeople reference run | Observed value |
| --- | --- |
| Target size at 2% | 1,277,999 bytes |
| Selected parameters | medium preset, AQ mode 1 |
| Accepted output | Attempt 1, 1,253,795 bytes |
| Preserved content | 150 frames, 5.0 seconds, 1280 × 720 at 30 fps |
| Quality on the decoded Y plane | PSNR 41.6065 dB, five-scale MS-SSIM 0.994855 |

The evaluator checks frame count, dimensions, frame rate, relative presentation timestamps and duration before comparing the complete decoded sequences. The run contains `task/features.json` for the measured input features, `summary.csv` for results and timings, and `manifest.json` for software versions. For a failed task, start with `failure_reason` in `task/task.json`.

## 5. How FFmpeg is called

The program reads stream metadata and frame timestamps with ffprobe. It measures frame-to-frame differences and edge density on 320 × 180 analysis frames. The frozen policy uses these features and the available bits per pixel per frame to choose the preset and AQ mode. Both encoding passes read the original video at its original resolution.

The size limit is rounded down to whole bytes. The initial video bitrate is `floor(0.98 × 8 × target_bytes / duration_seconds)` bits per second. Python passes an argument list directly to FFmpeg for each pass. The templates below show the macOS invocation. The application supplies the input path, selected parameters, bitrate and per-attempt paths.

```bash
ffmpeg -hide_banner -nostdin -y -threads 2 -i "$INPUT" -map 0:v:0 -an -sn -dn \
  -c:v libx264 -threads 2 -preset "$PRESET" -pix_fmt yuv420p -aq-mode "$AQ" \
  -b:v "$BITRATE" -fps_mode passthrough -pass 1 -passlogfile "$PREFIX" \
  -progress pipe:1 -nostats -f null /dev/null

ffmpeg -hide_banner -nostdin -y -threads 2 -i "$INPUT" -map 0:v:0 -an -sn -dn \
  -c:v libx264 -threads 2 -preset "$PRESET" -pix_fmt yuv420p -aq-mode "$AQ" \
  -b:v "$BITRATE" -fps_mode passthrough -pass 2 -passlogfile "$PREFIX" \
  -progress pipe:1 -nostats -movflags +faststart "$OUTPUT"
```

Pass one writes x264 statistics. Pass two uses the same statistics prefix to produce the MP4. If the complete file exceeds the budget, the program reduces the bitrate in proportion to the measured overshoot, applies a 2% margin and retries from the source. It stops at the first valid output or after three attempts. The exact commands, return codes and measured size are recorded in `task/attempt_N/attempt.json`; FFmpeg diagnostics are in the adjacent `pass_1.log` and `pass_2.log`.

## Reproduce the full comparison

After the single-video check, use the following commands to reproduce the course comparison. The first verifies the frozen policy, inputs and task matrix. The second runs 12 videos at two budgets with three strategies: fixed medium/AQ 1, fixed slow/AQ 1 and the frozen adaptive rule.

```bash
python experiments/full_exps/run.py
python experiments/full_exps/run.py --execute
```

The runner prints a separate `runs/<timestamp>_full_exps/` directory. Its `queue.json` records the status of all 72 tasks, `summary.csv` contains their measurements, and each successful task's `task.json` identifies its accepted MP4.
