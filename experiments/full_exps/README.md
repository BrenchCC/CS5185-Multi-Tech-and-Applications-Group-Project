# 12 个完整视频的全量编码实验

2026-11-27 完成全部 72 项本地编码，55 项首轮达标、17 项第二轮达标。每份最终输出均在完整 MP4 字节预算内并通过全片对齐检查。逐片结果、保留集配对差值、同帧图及重试分析见[中文实验报告](report_analysis_zh.md)。

[预登记清单](matrix.csv)列出 12 个原片、每片 5% 和 2% 两档完整 MP4 字节预算，以及固定 medium/AQ 1、固定 slow/AQ 1、冻结规则三组，共 72 个配置。每组 24 项。按编号串行处理完整视频，每个配置重新读取原片、计算特征和执行 libx264 双遍编码，最多三次尝试，首次达标停止。三组均在本地执行，API 请求数为零。

## 运行

在仓库根目录、已安装项目依赖的环境中运行。第一条命令核对 12 个输入的哈希、字节数、格式和时间信息，逐行验证预算、划分及策略，并检查[冻结规则](policy.json)摘要。第二条命令通过相同预检后启动正式编码。

```bash
python experiments/full_exps/run.py
python experiments/full_exps/run.py --execute
```

## 结果与验收

正式运行会打印独立的 `runs/<时间戳>_full_exps/` 目录。用 `queue.json` 检查 72 个任务的结束状态，用 `summary.csv` 比较实际文件大小、视频与封装码率、Y-PSNR、五尺度 Y-MS-SSIM、累计编码及总耗时。各任务的 `features.json`、`task.json` 和每轮的 `attempt.json` 保存内容特征、参数理由、完整性检查、FFmpeg 命令、码率修正及停止依据。全部成功时，`evidence/` 包含 12 张特征曲线和 24 张同帧对照图。

撰写报告时按清单的 `split` 分组。开发视频 01、02、03、04、07、08 参与过规则校准；其余六个视频用于评价冻结策略。其中 05、06、09 已有[首批实验](../heldout_pilot/README.md)，本批为独立重跑。比较两批结果时，重复视频只计作一个样本。每组达标率以预定的 24 项为分母，画质比较使用同视频、同预算下均通过检查的配对，注明有效配对数。

正式运行目录为 `runs/20261126T165657151328Z_full_exps/`。每个成功任务的 `task.json` 中，`output_path` 指向可播放的最终文件。[任务数据](tasks.csv)覆盖 72 项配置，[逐轮数据](attempts.csv)覆盖 89 次双遍尝试。[记录包](records.zip)保留两批运行的源码、环境、命令、日志和结果，视频留在本地运行目录。

主对照结束后，另对 Stockholm、Sintel、ControlledBurn 各执行 2% Ark 案例。原三次请求解析失败后，以 2048 token 上限各重试一次；三次均获得有效决策并完成双遍编码，Stockholm 达标，Sintel 和 ControlledBurn 超出预算。详见[重试调用记录](ark_cases.json)及[实验分析](report_analysis_zh.md)。原始失败记录保留在 `runs/20261126T172426232743Z_full_ark_cases/`。
