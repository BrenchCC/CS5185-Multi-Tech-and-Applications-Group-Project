# 课程提交打包指南

本指南生成一个不含 PPT 的提交包，包含可运行代码、英文提交说明和项目与实验报告。压缩包保留项目相对路径，解压后从项目根目录按照 `docs/submission/README.md` 操作。

## 一、打包内容

| 内容 | 路径 | 用途 |
| --- | --- | --- |
| 程序入口与依赖 | `main.py`、`requirements.txt` | 启动 CLI、终端界面和安装依赖 |
| 编码系统 | `adaptive_encoding/*.py` | 编码、特征测量、评价、规则决策和界面 |
| 模型响应处理 | `utils/__init__.py`、`utils/json_extract.py` | 解析模型返回的 JSON |
| 模型提示词 | `prompts/encoding_decision_zh.md` | Ark 决策及运行时源码快照 |
| 完整实验入口 | `experiments/full_exps/run.py` | 执行提交说明中的全量实验命令 |
| 实验配置 | `experiments/full_exps/policy.json`、`matrix.csv` | 提供冻结规则和 72 项实验清单 |
| 数据集元数据 | `CS5185_Project_Video_Dataset/metadata/*.json` | 检查 12 个原视频的信息和哈希 |
| 代码许可 | `LICENSE` | 项目代码许可 |
| 提交说明 | `docs/submission/README.md` | 安装、输入约束、运行命令和结果检查 |
| 项目报告 | `reports/project_report/project_report.pdf` | 英文项目报告 |
| 实验报告 | `reports/exp_report/experiment_report.pdf` | 英文实验报告 |

报告以 PDF 形式提交，无需将 LaTeX 源码和生成报告使用的图片另行放入此包。报告中的截图和曲线已经嵌入 PDF。

## 二、创建压缩包

在仓库根目录执行以下命令。命令只列入第一节中的文件，不会将本指南自身、PPT、密钥或运行缓存放进压缩包。

```bash
zip -q CS5185_submission.zip \
  main.py requirements.txt LICENSE \
  adaptive_encoding/*.py \
  utils/__init__.py utils/json_extract.py \
  prompts/encoding_decision_zh.md \
  experiments/full_exps/run.py \
  experiments/full_exps/policy.json experiments/full_exps/matrix.csv \
  CS5185_Project_Video_Dataset/metadata/*.json \
  docs/submission/README.md \
  reports/project_report/project_report.pdf \
  reports/exp_report/experiment_report.pdf
```

如果根目录已有同名压缩包，应先移走或删除旧包，再执行命令；`zip` 更新已有压缩包时不会自动移除旧条目。

## 三、视频与外部依赖

此包不包含课程提供的 12 个原视频。接收者运行前需要将原始 MP4 放入解压后的 `CS5185_Project_Video_Dataset/`，并与包内 `metadata/` 的文件名和哈希对应。课程视频及其来源许可应按课程提供方式获取；如提交要求提供视频，需另按课程规定提供，不能把这份代码包当成视频交付。

Python 依赖通过提交说明中的 `pip install -r requirements.txt` 安装；FFmpeg、ffprobe 和 libx264 需要在运行环境中另行安装。冻结规则示例无需 API 密钥；如使用 Ark，接收者应自行配置环境变量，禁止打包本机 `.env` 或其他密钥。

## 四、提交前检查

1. 使用 `unzip -l CS5185_submission.zip` 核对文件清单，确认两份英文 PDF、英文提交说明、策略与矩阵均在包内，且没有 `.env`、PPT、缓存和 `runs/`。
2. 将压缩包解压到新的空目录，确认 `docs/submission/README.md` 中的相对路径存在。
3. 在解压目录安装依赖，补齐课程原视频后，按提交说明运行 `python main.py check`，再执行单视频示例。完整 72 项实验耗时较长，应按实际需要运行。
4. 单独确认课程要求的可播放解码视频及展示材料如何提交。本压缩包中的报告包含实验结果和代表画面，但不包含可播放的编码输出。
