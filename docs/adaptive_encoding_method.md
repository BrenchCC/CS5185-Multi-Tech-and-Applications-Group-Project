# Adaptive Encoding Method and Evaluation

The encoder supports development-calibrated rules and Ark text decisions. Both controllers select a preset and AQ mode and provide a rationale. The program controls the budget, process arguments, bitrate correction and validation.

## Features and budget

Content analysis decodes every source frame with OpenCV, resizes it to 320 × 180 using area interpolation, converts BGR to grayscale, and measures:

- **Temporal change:** mean absolute grayscale difference between consecutive frames divided by 255. The first frame has no predecessor and is excluded from aggregation.
- **Spatial detail:** the proportion of nonzero Canny edge pixels, using thresholds 100 and 200, aperture 3 and the default L1 gradient.
- **Budget pressure:** initial video bits per second divided by original width, height and frames per second, expressed as bits per pixel per frame.

Feature files retain every measurement plus the mean and 90th percentile. Only the two means and budget pressure enter the first rule search. Resizing applies only to feature analysis; encoding and quality measurement use the original 1280 × 720 resolution.

Frame differences also respond to camera motion, noise and lighting. Edge density depends on the chosen scale and thresholds. These signals describe measured frame changes and edges.

Budgets use source file bytes, with exact integer percentages:

```math
B = \left\lfloor \frac{S p}{100} \right\rfloor, \qquad p \in \{2,5\}
```

```math
R_0 = \left\lfloor \frac{0.98 \times 8 B}{T} \right\rfloor
```

For an oversized result of A bytes:

```math
R_{n+1} = \min\left(R_n - 1,\left\lfloor R_n \frac{B}{A} \times 0.98 \right\rfloor\right)
```

The rate is bounded below by 1 bit/s. The 2% margin is an initial engineering allowance for container overhead; only the measured full MP4 size determines compliance. Units are decimal bits/s and bytes.

## Candidate search and frozen rules

Development IDs are **01, 02, 03, 04, 07, 08**. IDs **05, 06, 09, 10, 11, 12** remain reserved. Metadata and hash checks may inspect all inputs, but reserved-video content features and output quality do not participate in calibration.

Calibration runs all four combinations of `medium/slow × AQ 1/2` for each of the 12 development video-budget pairs: **48 configuration tasks**. Each candidate gets the same budget formula, independent two-pass attempts, at most three attempts, identical encoder thread count and unchanged nonselected options. Failed candidates remain recorded and cannot count as valid outputs.

Each selected parameter uses a one-threshold rule: choose one of the three measured inputs, compare it to a threshold, and return one of two values. Thresholds are adjacent distinct calibration-value midpoints; both directions and constant rules are included. The search evaluates preset/AQ rule pairs jointly against actual candidate outcomes. Each branch can be inspected directly and traced to measured candidate results.

The objective is ordered:

1. Maximize the number of valid selected outputs.
2. Retain rules within 0.0001 of the highest mean MS-SSIM.
3. Among those rules, retain those within 0.01 dB of the highest mean PSNR.
4. Minimize total measured encoding time; if equal, minimize the number of nonconstant rules, then use deterministic enumeration order.

Means use successful selected outputs after the valid-count comparison. Perfect-match PSNR is represented as 1000 dB only for the internal ranking sentinel; exported measurements retain the explicit infinite flag. The tolerance values are engineering choices, not perceptual-equivalence guarantees. Speed breaks quality ties; it is not assigned an arbitrary combined quality weight.

Leave-one-video-out validation recalibrates thresholds on five videos, then evaluates both budgets of the sixth. This prevents the same video's other budget leaking into its calibration fold. It records selected combinations and MS-SSIM regret against the valid four-candidate best for that target. This oracle is an analysis reference, not the runtime controller.

Finally the complete development set determines the frozen rule. Its feature version, source hashes, selection objective, held-out analysis and content-derived policy identifier are saved. A rule may be constant if the search evidence favors it; the program does not force content-dependent branching to create a desired narrative.

**Independent validation** then runs the frozen rule and the two fixed baselines, totaling **36 new configuration tasks**. It does not reuse calibration encodes or timings. Since these are the same six development videos, this remains development evidence. Held-out test conclusions require a later frozen-policy experiment on the reserved set.

## Encoding and failure behavior

All encoding and muxing use FFmpeg/libx264. The runner passes argument arrays, never generated command text. Both passes use the selected preset, AQ mode and target bitrate; FFmpeg's default fast-first-pass behavior is preserved consistently. Output is yuv420p MP4 with faststart, no audio, no subtitles and passthrough frame timing. Two encoder threads are fixed for every group. Other x264 parameters retain preset defaults.

Single-video schedules are rule–rule–LLM, all-LLM and all-rule. Each reached slot selects parameters once. Following an oversized output, the program lowers the bitrate and reopens the original source. An invalid or failed Ark decision consumes its slot before encoding. A valid result ends the task and a hard process, integrity or metric error stops the task. Two passes count as one encoding attempt.

Attempt directories and pass-log prefixes are unique. Cancellation terminates the active child process, keeps completed artifacts and records interrupted work. If a synchronous Ark request is active, cancellation takes effect after the request returns or times out.

## Integrity and quality

Before quality comparison, ffprobe examines the complete displayed frame sequence. Output width, height, frame rate and frame count must match. Relative presentation timestamps and full duration must agree within the larger input/output time-base tick, with a 1 microsecond allowance for decimal timestamp serialization. A complete FFmpeg decode with `-xerror` must also succeed. Comparisons never silently use only a shared prefix.

The quality reader uses FFmpeg `extractplanes=y` to obtain native decoded 8-bit Y values without RGB conversion, spatial scaling or range expansion. All 150 frames (75 for ShakeNDry in future reserved-set evaluation) are compared.

PSNR first sums squared errors over every corresponding Y pixel and frame, divides by the total pixel count, then computes:

```math
\mathrm{PSNR}_Y = 10\log_{10}\left(\frac{255^2}{\mathrm{MSE}_Y}\right)
```

A zero MSE is infinite PSNR. MS-SSIM uses `pytorch-msssim` 1.0.0, one Y channel, data range255, Gaussian window11, sigma1.5, K=(0.01,0.03), and five weights [0.0448, 0.2856, 0.3001, 0.2363, 0.1333]. Each frame is evaluated at full resolution; the video score is their arithmetic mean. Ordinary FFmpeg SSIM is not substituted for MS-SSIM.

Whole-file bitrate includes MP4 overhead. Video bitrate uses ffprobe's sum of video packet bytes. Both divide by the validated presentation duration. Encoding, feature extraction, decision, evaluation and total wall times are recorded separately. Model decision time is recorded when an Ark slot is reached. Calibration cost is reported separately from runtime decision cost.

## Interface, provenance and limitations

Textual runs background work in a thread; worker messages update the UI on the main event loop. FFmpeg progress drives encoding progress, while indeterminate phases show activity rather than an invented percentage. Cancellation is cooperative and waits for subprocess cleanup before an approved exit.

Each run records the environment, package versions, FFmpeg builds, code revision/worktree status, thread count and feature-cache policy. Source snapshots accompany the delivered experiments. Every task retains input/output hashes, decision inputs, English rationale, command arrays, logs and metrics. The calibrated feature algorithm is versioned so incompatible policy files are rejected.

Six short development videos provide limited evidence for threshold selection. Runtime measurements vary with host activity; there are no repeated timing trials or significance claims. Quality scores can disagree with visible detail, and AQ mode choices can trade PSNR against structural quality. Screenshots support inspection rather than proving universal perceptual superiority.

## Primary references

- [FFmpeg libx264 options](https://ffmpeg.org/ffmpeg-codecs.html#libx264_002c-libx264rgb)
- [FFmpeg progress and frame-rate behavior](https://ffmpeg.org/ffmpeg.html)
- [ffprobe frame, packet and stream inspection](https://ffmpeg.org/ffprobe.html)
- [pytorch-msssim implementation](https://github.com/VainF/pytorch-msssim)
- [Textual background workers](https://textual.textualize.io/guide/workers/)
- [Textual interaction testing](https://textual.textualize.io/guide/testing/)
