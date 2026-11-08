# DM Paraformer ASR — 离线中文语音转文字（ComfyUI 节点）

> **78 MB 小模型、纯 CPU、不联网、不占显存**，3~4 秒音频约 **0.03~0.1 秒**。
> 附带一个「收款金额抽取」节点：中文数字 `一点二八元` → **1.28**（不会变成 1.8）。

作者：**DSH / DM**（2026-11-08）· License: MIT · 模型: [paraformer-zh-small](https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-small-2024-03-09)（Apache-2.0）

---

## 节点一览（全部 `DM` 前缀）

| 节点 | 输入 → 输出 | 用途 |
|---|---|---|
| 🎙️ **DM ASR 语音转文字** `DMASRTranscribe` | `AUDIO` → `STRING text`, `STRING info` | 接 `LoadAudio` 的输出；长音频自动按 25 秒切块 |
| 📁 **DM ASR 文件转写** `DMASRFile` | `STRING file_path` → `STRING text`, `STRING info` | 直接给磁盘路径（wav/flac 用标准库，其它格式走 ComfyUI 自带 `av`） |
| 💰 **DM 收款金额抽取** `DMASRPayAmount` | `STRING text` → `FLOAT amount`, `INT cents`, `STRING keyword`, `BOOLEAN hit`, `STRING snippet` | 从识别文本里抠金额（微信/支付宝关键词表 + 中文数字解析） |
| ℹ️ **DM ASR 状态** `DMASRInfo` | — → `STRING info`, `BOOLEAN ready` | 模型在哪、是否就绪、线程数；排错先看这个 |

## 安装

**A. 复制到 custom_nodes（推荐）**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/dxyliwei520/comfyui-dm-paraformer-asr.git
cd comfyui-dm-paraformer-asr
pip install -r requirements.txt      # 只有 sherpa-onnx==1.10.46（2 MB）
```

> ⚠️ **版本必须锁 1.10.46**。`2.0.x / 1.12.x / 1.13.x` 的 Windows 轮子内置 ORT 1.17.1，
> 加载本模型会报 `The requested API version [24] is not available, only [1, 17] ...`（实测）。

**B. ComfyUI Manager**：搜索 `DM Paraformer ASR`（本仓库的 `custom-node-list.json` 就是给 Manager 用的清单）。

## 模型放哪

```
ComfyUI/models/ASR/paraformer-zh-small/
    model.int8.onnx      (~78 MB)
    tokens.txt
    am.mvn
```

三种来源任选：
1. 首次运行**自动下载**（hf-mirror；设 `DM_ASR_NO_DOWNLOAD=1` 可禁用）；
2. 手动下载上面三个文件放进去（模型仓库：`csukuangfj/sherpa-onnx-paraformer-zh-small-2024-03-09`）；
3. 用环境变量 `DM_ASR_DIR=/你的/目录` 指过去。

## 最小用法

```
LoadAudio ──AUDIO──▶ 🎙️ DM ASR 语音转文字 ──text──▶ 💰 DM 收款金额抽取 ──amount──▶ 你的下游
```

- 做**字幕/素材整理**：`📁 DM ASR 文件转写` 直接填路径，批量跑；
- 做**语音驱动提示词**：把 `text` 接到 `CLIPTextEncode`；
- 做**收款核对**：`amount` + `hit` 拿去比对订单（`hit=false` 就拒绝，宁可漏不可错）。

## 实测数据（RTX 5070 Ti 机器上，纯 CPU）

| 项 | 数值 |
|---|---|
| 模型加载 | **1.5 s**（只加载一次，之后常驻） |
| 3.76 秒音频识别 | **0.029 s** |
| 4.04 秒音频识别 | **0.028 s** |
| 识别结果 | `微信支付收款一点二八元` → 金额 **1.28** ✅ |
| 对照：vosk-small-cn | 同一句听成「一点八元」→ **1.8** ❌（差 0.52 元） |

## 排错

| 现象 | 原因 / 解法 |
|---|---|
| `requested API version [24/28] ... Current ORT Version 1.17.1` | sherpa-onnx 版本不对 → `pip install sherpa-onnx==1.10.46` |
| `找不到模型` | 看 `ℹ️ DM ASR 状态` 输出的 `candidates`，把模型放进其中任一目录 |
| 识别结果为空 | 音频太短（<0.05 s）或全是静音；先用 `LoadAudio` 确认能听到声音 |
| 中文长音频断句怪 | 把 `max_chunk_sec` 调小（如 15）让它按更短的块切 |

## 许可

- 本仓库代码：**MIT**
- 模型 paraformer-zh-small：**Apache-2.0**（阿里达摩院 FunASR 系列，sherpa-onnx 提供 onnx 导出）
- 运行时 sherpa-onnx：**Apache-2.0**
