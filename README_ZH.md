# CS5185 内容自适应视频编码实验台

[English README](README.md) · [中文使用指南](docs/guidance/usage_zh.md)

本项目在原视频大小 5% 或 2% 的预算内生成 H.264 MP4。程序测量帧间变化和边缘密度，按所选策略决定 x264 preset 与 AQ 模式，再通过 FFmpeg 双遍编码、文件大小反馈、完整性检查和亮度质量评价，筛出可交付输出。

## 一、快速启动

在仓库根目录执行。开发环境使用 Python 3.10，系统需要可执行的 `ffmpeg`、`ffprobe` 以及 `libx264` 编码器。

```bash
pip install -r requirements.txt
python main.py
```

英文终端界面提供环境检查、任务配置、运行监控和结果查看。课程数据请放入 `CS5185_Project_Video_Dataset/`。首次使用默认或规则策略时，先在界面选择 **Calibrate rules** 生成规则文件。想先编码一条视频，可选固定基线快速检查工具链。

## 二、选择策略

| 策略 | 第 1 轮 | 第 2 轮 | 第 3 轮 |
| --- | --- | --- | --- |
| 默认 `hybrid` | 规则 | 规则 | LLM |
| `llm` | LLM | LLM | LLM |
| `rule` | 规则 | 规则 | 规则 |

每个任务最多执行三轮，首次达标即结束。规则读取开发集校准结果，LLM 根据实测特征和先前轮次的数值摘要选择参数。输出超预算时，下一轮码率由程序按实际大小下调。模型输出由 [JSON 提取工具](utils/json_extract.py)解析并验证。模型只可选择 `medium` 或 `slow`，以及 AQ 1 或 2。

需要调用模型时，把 [配置模板](.env.example)复制为本地 `.env`，填写火山方舟密钥、接入点和 API 地址。默认策略若前两轮达标，实际调用次数为零。详细配置和可复制命令见[中文使用指南](docs/guidance/usage_zh.md)。

## 三、代码和资料

| 路径 | 内容 |
| --- | --- |
| [main.py](main.py) | 终端界面与自动化入口 |
| [adaptive_encoding/](adaptive_encoding/) | 编码、评价、实验编排、模型接入与终端界面 |
| [prompts/](prompts/) | 中文模型提示词 |
| [utils/](utils/) | JSON 提取工具和已有 API 辅助代码 |
| [docs/guidance/](docs/guidance/) | 使用、观测与排查指南 |
| [docs/project_description/](docs/project_description/) | 课程要求与数据集说明 |
| [tests/](tests/) | 自动测试与真实媒体验证脚本 |

每次运行写入独立目录，默认位于 `runs/`，其中 `summary.csv` 用于比较，`task.json` 和 `attempt.json` 用于追溯决策、大小、画质与错误。开发集对照仍使用固定 medium、固定 slow 与规则三组。首批三个保留视频的实测数据、反馈案例和对照图见[实验记录](experiments/heldout_pilot/README.md)。
