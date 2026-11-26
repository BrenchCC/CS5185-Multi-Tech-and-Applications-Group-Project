# 内容自适应视频编码实验台使用指南

程序为每条视频设定严格的 MP4 字节预算，最多执行三轮双遍编码。正常交付的输出同时满足大小预算、完整解码、帧数、分辨率、帧率和时间对齐检查。英文终端界面适合交互使用，自动化命令使用同一套服务。

## 一、准备环境和数据

1. 准备 Python 3.10 与可从 PATH 调用的 FFmpeg、ffprobe。使用 `ffmpeg -hide_banner -h encoder=libx264` 核对编码器。
2. 将课程原始视频和配套 metadata 放入仓库根目录的 `CS5185_Project_Video_Dataset/`。不要手动修改原视频或元数据。
3. 在仓库根目录安装依赖并启动。

```bash
pip install -r requirements.txt
python main.py
```

在 **Environment & Data** 点击 **Check environment**，检查 12 个输入的文件大小、帧数、时长、尺寸、帧率、音轨约束及哈希。预检会读取保留集的文件和元数据，校准与开发集验证只编码 01、02、03、04、07、08。

需要 Ark 时，从 `.env.example` 创建本地 `.env`，填写 `LLM_API_KEY`、`LLM_ENDPOINT` 和 `LLM_API_BASE_URL`。后两项分别对应模型接入点与兼容的 API 根地址。已有同名环境变量优先于文件配置。模型接收数值特征、当前预算和前轮指标，不接收视频、图片、源路径或密钥。可在 [中文提示词](../../prompts/encoding_decision_zh.md)检查发送给模型的决策约束。

## 二、运行编码任务

### 2.1 终端界面

在 **Task Setup** 选择开发视频、5% 或 2% 预算和策略。默认策略与纯规则策略需要冻结规则文件，默认路径为 `runs/policy.json`。已有文件可以直接选择，首次可点击 **Calibrate rules** 在开发集运行 48 个候选任务并生成规则。纯 LLM 无需校准。

| 界面选项 | 轮次顺序 | 何时请求 Ark |
| --- | --- | --- |
| **Default: Rule → Rule → LLM** | 前两轮规则，最后一轮模型 | 前两轮均未达标并进入第三轮时 |
| **LLM only: three LLM slots** | 每轮都由模型选择 | 每个执行到的轮次各请求一次 |
| **Rule only: three rule slots** | 每轮都由冻结规则选择 | 无 |
| **Fixed medium / AQ 1** 或 **Fixed slow / AQ 1** | 每轮固定编码参数 | 无 |

点击 **Run selected** 启动。F1、F2、F3 分别打开配置、监控与结果，Tab 或鼠标切换控件。**Validate dev set** 用于运行原三组开发集对照，共 36 个配置。它不随单视频策略下拉框切换，也不会触发 Ark 请求。

### 2.2 自动化命令

```bash
python main.py check
python main.py calibrate
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02 --strategy llm
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02 --strategy rule
python main.py batch --policy runs/policy.json
```

`--output` 指定运行目录根路径，`--policy` 指定冻结规则文件。使用其他输出根目录校准后，需要显式指定对应的 policy。单条命令接受文件路径，运行正式实验时请遵守课程的数据划分。

### 2.3 轮次和停止条件

一轮包含一次参数决策和最多一组双遍编码。5% 和 2% 均按原文件大小向下取整。若完整输出超限，程序按实测字节数下调下一轮目标码率并重新读取原视频。规则根据同一套冻结条件选择 preset 和 AQ，因此规则轮之间通常只改变码率。LLM 轮还可以根据此前的实测结果选择不同的 preset 或 AQ。

首个达标输出立即结束任务。请求失败或 JSON 校验失败会消耗当前 LLM 轮，记录为 `decision_failed`，如还有剩余轮则继续按原顺序执行。SDK 不额外重试。硬性编码、完整性或评价错误会结束当前任务。点击 **Cancel run** 后，编码子进程会被清理，已发送的 Ark 请求等待返回或超时，由程序在再次编码前检查取消状态。

## 三、观测执行和核对结果

### 3.1 运行中

在 **Run Monitor** 查看当前视频、轮次、双遍进度和日志。看到 **Requesting model decision** 表示已进入模型决策阶段，看到 **Decision failed** 表示该轮在编码前结束。**Output oversized** 会显示完整 MP4 的实际字节数与上限。每次校准或批次仍按顺序运行。

### 3.2 完成后

在 **Results** 选择任务行，查看最终参数、英文理由、失败原因和逐轮状态。也可填写已有运行目录并点击 **Load results**。**Export CSV** 会生成汇总。自动化导出命令如下，将目录名替换为实际运行生成的名称。

```bash
python main.py summarize --folder runs/EXISTING_RUN_DIRECTORY
```

| 文件 | 核对内容 |
| --- | --- |
| `summary.csv` | 策略、任务状态、大小、PSNR、MS-SSIM、编码与模型决策耗时 |
| `task.json` | `target_bytes`、`selected_attempt`、`output_path`、所有轮次记录和失败原因 |
| `attempt_N/attempt.json` | `controller`、实际参数、码率、FFmpeg 参数数组、返回码和调整原因 |
| `attempt_N/attempt.json` 的 `llm` | 提示词哈希、模型接入点、请求摘要、用量、耗时和校验结果。请求失败时部分字段可能缺失 |
| `attempt_N/pass_1.log` 和 `pass_2.log` | 编码器输出，决策失败的轮次不会生成 |
| `features.json` | 逐帧特征时间线、均值和第 90 百分位 |
| `manifest.json` 和 `source/` | 软件版本、运行环境及关键代码和提示词快照 |

以 `task.json` 中 `status = success`、`selected_attempt` 和 `output_path` 判定交付文件。检查 `actual_bytes` 不超过 `target_bytes`，再看亮度 PSNR 和 MS-SSIM。失败轮也可能留下 MP4，尤其是超预算轮次。开发集验证还会输出特征曲线及同帧对比图。

## 四、排查常见问题

- 找不到规则文件时，先运行校准，或者选择现有文件。纯 LLM 和固定基线无需规则文件。
- 遇到 `Ark request failed` 时，通过错误类别排查密钥、接入点、网络或限流。对外分享日志前避免附带本地 `.env`。
- 遇到 `ArkAPIConnectionError` 或 `ArkAPITimeoutError` 时，查看每轮的 `llm.api_error_type`、`llm.api_error_causes` 和 `elapsed_s`。旧记录只保存顶层异常。可以从同一终端对配置地址的 `/models` 发起只读 GET，比较直连与代理路径；匿名请求返回 HTTP 401 表明已收到 HTTP 响应，验证指定推理接入点仍需实际模型调用。
- 遇到 JSON 校验失败时，检查模型是否只返回一个对象、AQ 是否为整数、字段是否严格限于 `preset`、`aq_mode`、`reason`。解析器接受裸 JSON 或单个 JSON 围栏，拒绝混入解释段落、多对象、重复键、非法数字与超长响应。
- 默认策略显示零调用是正常结果。打开前两轮的状态，确认是否已达到预算并通过完整性检查。
- 需要复现实验时，保存同一份规则、提示词、输入哈希、软件版本和任务结果。Ark 服务端模型可能发生变化，记录中的接入点和用量用于追溯每次调用。
