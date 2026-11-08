# DM Paraformer ASR（中文完整说明）

> 一句话：**把「一句话里抠数字」这件事，做成 ComfyUI 里的一个本地节点** —— 78 MB 小模型、纯 CPU、不联网、不占显存，3~4 秒音频 0.03~0.1 秒出结果。

- 作者：DSH / DM（2026-11-08）
- 仓库：`https://github.com/dxyliwei520/comfyui-dm-paraformer-asr`
- 许可：代码 MIT；模型 Apache-2.0；运行时 Apache-2.0

---

## 一、为什么做这个

这台机器上的「DM 支付监听」链路里，服务端已经有成熟的窄域 ASR：`sherpa-onnx + paraformer-zh-small`，实测把「微信支付收款一点二八元」听成 `1.28`，而 `vosk-model-small-cn` 会听成「一点八元」（**1.28 → 1.8，差 0.52 元**）。

把它搬进 ComfyUI 之后，能力就变成可编排的了：

| 想做的事 | 怎么接 |
|---|---|
| 语音 → 提示词 | `LoadAudio → 🎙️空 DM ASR → CLIPTextEncode` |
| 语音 → 字幕/素材库 | `📁 DM ASR 文件转写` 批量跑，`info` 里有耗时/时长 |
| 收款核对 | `🎙️ ASR → 💰 收款金额抽取 → 比对订单`（`hit=false` 直接拒绝） |
| 任何"从一句话里抠一个关键词"的活 | 同一套：先识别，再交给 `💰` 或自己的正则 |

## 二、节点清单

| 节点 ID | 显示名 | 输入 | 输出 |
|---|---|---|---|
| `DMASRTranscribe` | 🎙️ DM ASR 语音转文字 | `AUDIO`（+线程数/切块长度/保留空格） | `text`, `info`(JSON) |
| `DMASRFile` | 📁 DM ASR 文件转写 | `file_path`（绝对路径或 `input/` 下相对名） | `text`, `info` |
| `DMASRPayAmount` | 💰 DM 收款金额抽取 | `text`（+宽松模式/额外关键词） | `amount`, `cents`, `keyword`, `hit`, `snippet` |
| `DMASRInfo` | ℹ️ DM ASR 状态 | — | `info`(JSON), `ready` |

输出 `info` 里固定有：`duration`（音频秒数）、`chunks`（切了几块）、`elapsed`（识别耗时）、`engine`、`model`（模型目录）。排错先看它。

## 三、安装

### 3.1 装依赖（只有 2 MB）

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/dxyliwei520/comfyui-dm-paraformer-asr.git  dm_paraformer_asr
cd dm_paraformer_asr
<你的 python> -m pip install -r requirements.txt
```

⚠️ **必须锁 `sherpa-onnx==1.10.46`**。实测：`2.0.1 / 1.13.8 / 1.12.40 / 1.12.30` 的 Windows 轮子内置 ORT 1.17.1，加载本模型直接报

```
The requested API version [24] is not available, only API versions [1, 17] are supported in this build.
Current ORT Version is: 1.17.1
```

（Linux 轮子没这个问题 —— 所以云端 `2.0.1` 能跑、Windows 不行。这就是为什么这里要锁版本。）

### 3.2 放模型（三选一）

```
ComfyUI/models/ASR/paraformer-zh-small/
    model.int8.onnx      81828675 字节
    tokens.txt               75352 字节
    am.mvn                   11203 字节
```

1. **自动下载**：首次识别时自动从 `hf-mirror.com/csukuangfj/sherpa-onnx-paraformer-zh-small-2024-03-09` 拉；禁用：设 `DM_ASR_NO_DOWNLOAD=1`。
2. **手动**：把上面三个文件下载后放进去（国内建议 hf-mirror，直连 huggingface 基本不通）。
3. **指路**：`export DM_ASR_DIR=D:/models/paraformer-zh-small`。

## 四、实测（这台机器，D 盘 ComfyUI 0.42.1 / Python 3.13 / 纯 CPU 2 线程）

```
[DM-ASR] paraformer 就绪：…\models\ASR\paraformer-zh-small（2 线程，加载 1.5s）
voice-test-1-28.wav   3.76s → 识别 0.029s   「微信支付收款一点二八元」→ 金额 1.28 ✅
voice-test-35-80.wav  4.04s → 识别 0.028s   「微信支付收款三十五点八元」→ 金额 35.8 ✅
```

中文数字解析自测：

| 输入 | 抽到的金额 |
|---|---|
| 微信支付收款一点二八元 | **1.28** |
| 微信支付收款三十五点零七元 | **35.07** |
| 微信收款到账一百二十三点四五元 | **123.45** |
| 微信收看五元（ASR 变体） | **5.0** |
| 无关的一句话，今天天气不错 | `None`（不误报） |

## 五、金额抽取的两级策略（为什么不会乱发卡）

1. **严格**：命中收款关键词（含 ASR 常见变体「微信收看」）→ 取关键词后第一个数字；
2. **宽松**：没命中关键词，但有「微信/收款/到账…」线索词，且出现「X元/X块」→ 也交出金额。

会不会误判？由**账本**兜底：待确认订单的应付金额都带随机尾数（1~90 分），随便一句话里的整数金额几乎不可能精确命中。识别层只负责"别把真播报漏掉"，**宁可漏、不可错**。

## 六、常见问题

| 现象 | 处理 |
|---|---|
| 节点列表里看不到 | 重启 ComfyUI；看启动日志有没有 `IMPORT FAILED ... dm_paraformer_asr` |
| `找不到模型` | 跑一次 `ℹ️ DM ASR 状态`，看 `candidates` 列表，把模型放进任一目录 |
| 识别为空 | 音频 <0.05 s、或全静音；先 `LoadAudio` 确认有声音 |
| 长音频断句难看 | `max_chunk_sec` 调到 15 试试 |
| 想换更强的模型 | 同接口可换 SenseVoice-small（228 MB，自带标点，约 0.3 s），改 `asr.py` 的 `from_paraformer` 为 `from_sense_voice` 即可 |

## 七、文件结构

```
dm_paraformer_asr/
├── __init__.py            # 4 个节点 + 注册表（DM 前缀）
├── asr.py                 # 引擎：模型发现/自动下载/重采样/长音频切块/文件直读
├── amount.py              # 中文数字 + 收款关键词 + 金额抽取（移植自生产 voiceasr.py）
├── requirements.txt       # sherpa-onnx==1.10.46（锁版本原因见上）
├── pyproject.toml         # 含 [tool.comfy]（发 Registry 用）
├── custom-node-list.json  # ComfyUI Manager 清单
├── examples/              # 最小工作流
└── LICENSE / README.md
```
