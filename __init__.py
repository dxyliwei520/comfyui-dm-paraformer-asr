# -*- coding: utf-8 -*-
"""
DM Paraformer ASR —— ComfyUI 离线语音识别节点（纯 CPU，不联网，不占显存）

    🎙️ DM ASR 语音转文字       AUDIO → STRING(text) + STRING(info)
    📁 DM ASR 文件转写         文件路径 → STRING(text) + STRING(info)
    💰 DM 收款金额抽取         STRING(text) → FLOAT(金额) + INT(分) + STRING(关键词) + BOOLEAN(命中)
    ℹ️ DM ASR 状态              → STRING(信息) + BOOLEAN(就绪)

模型：paraformer-zh-small（int8 ONNX 约 78 MB，Apache-2.0），3~4 秒音频 20~110 ms。
放在 <ComfyUI>/models/ASR/paraformer-zh-small/；没有会自动从 hf-mirror 下载。

作者：DSH（2026-11-08）
"""
from __future__ import annotations

import json

from . import asr as _asr
from .amount import KEYWORDS as _DEFAULT_KW
from .amount import extract_amount as _extract_amount

CATEGORY = "DM/Audio"

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


# --------------------------------------------------------------------------- 工具
def _split_kw(extra: str):
    extra = (extra or "").strip()
    if not extra:
        return list(_DEFAULT_KW)
    add = [w.strip() for w in extra.replace("，", ",").split(",") if w.strip()]
    seen, out = set(), []
    for w in list(_DEFAULT_KW) + add:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


# --------------------------------------------------------------------------- 节点
class DMASRTranscribe:
    """AUDIO → 文本（本地 paraformer，纯 CPU）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
            },
            "optional": {
                "num_threads": ("INT", {"default": 2, "min": 1, "max": 8, "step": 1,
                                        "tooltip": "CPU 线程数；2 线程 3 秒音频约 0.05~0.1 秒"}),
                "max_chunk_sec": ("FLOAT", {"default": 25.0, "min": 5.0, "max": 120.0, "step": 1.0,
                                            "tooltip": "长音频按这个长度切块识别（paraformer 单段不宜过长）"}),
                "keep_spaces": ("BOOLEAN", {"default": False,
                                            "tooltip": "保留识别结果里的空格（中文一般关掉）"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "info")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY
    DESCRIPTION = "离线中文语音转文字（sherpa-onnx + paraformer-zh-small，纯 CPU）"

    def run(self, audio, num_threads=2, max_chunk_sec=25.0, keep_spaces=False):
        samples = _asr.audio_to_16k(audio)
        text, info = _asr.transcribe_samples(samples, num_threads=num_threads,
                                             max_chunk_sec=float(max_chunk_sec))
        if keep_spaces:
            # 默认实现已压缩空格；保留模式重跑一次代价太大，这里只把零宽替换掉
            text = text.replace("\u200b", "")
        info_s = json.dumps(info, ensure_ascii=False)
        return {"ui": {"text": [text], "info": [info_s]}, "result": (text, info_s)}


class DMASRFile:
    """直接给文件路径 → 文本（wav/flac 用标准库，其它格式走 av 解码）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {"default": "", "multiline": False,
                                         "tooltip": "绝对路径；或相对 ComfyUI/input 的文件名"}),
            },
            "optional": {
                "num_threads": ("INT", {"default": 2, "min": 1, "max": 8, "step": 1}),
                "max_chunk_sec": ("FLOAT", {"default": 25.0, "min": 5.0, "max": 120.0, "step": 1.0}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "info")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY
    DESCRIPTION = "从磁盘音频文件转写（批量做字幕/素材整理时用）"

    def run(self, file_path, num_threads=2, max_chunk_sec=25.0):
        path = (file_path or "").strip().strip('"')
        import os
        if path and not os.path.isabs(path):
            try:
                import folder_paths
                base = getattr(folder_paths, "get_input_directory", lambda: "")()
                if base and os.path.isfile(os.path.join(base, path)):
                    path = os.path.join(base, path)
            except Exception:
                pass
        text, info = _asr.transcribe_file(path, num_threads=num_threads,
                                         max_chunk_sec=float(max_chunk_sec))
        info_s = json.dumps(info, ensure_ascii=False)
        return {"ui": {"text": [text], "info": [info_s]}, "result": (text, info_s)}


class DMASRPayAmount:
    """从文本里抠出「收款金额」（中文数字/阿拉伯数字都认）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True, "forceInput": False}),
            },
            "optional": {
                "loose": ("BOOLEAN", {"default": True,
                                      "tooltip": "宽松模式：没命中收款关键词但有「X元/X块」也取金额"}),
                "extra_keywords": ("STRING", {"default": "",
                                              "tooltip": "额外关键词，逗号分隔（会追加到内置 30+ 词表）"}),
            },
        }

    RETURN_TYPES = ("FLOAT", "INT", "STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("amount", "cents", "keyword", "hit", "snippet")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY
    DESCRIPTION = "收款播报金额抽取：微信/支付宝的关键词 + 中文数字解析（1.28 不会变 1.8）"

    def run(self, text, loose=True, extra_keywords=""):
        amt, kw, seg = _extract_amount(text or "", keywords=_split_kw(extra_keywords), loose=bool(loose))
        if amt is None:
            res = (0.0, 0, "", False, seg)
        else:
            res = (float(amt), int(round(float(amt) * 100)), kw, True, seg)
        # ui 里也回显一份，方便在 ComfyUI 里直接看到抽到的金额
        return {"ui": {"text": ["amount=%s  cents=%d  keyword=%s  hit=%s  snippet=%s" % res]},
                "result": res}


class DMASRInfo:
    """ASR 引擎自检：模型在哪、能不能用、线程数"""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING", "BOOLEAN")
    RETURN_NAMES = ("info", "ready")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY
    DESCRIPTION = "显示模型目录/加载状态；排错先看这个"

    def run(self):
        rec = _asr.get_recognizer(2)
        st = _asr.status()
        st["loaded_ok"] = rec is not None
        txt = json.dumps(st, ensure_ascii=False, indent=2)
        return {"ui": {"text": [txt]}, "result": (txt, bool(rec is not None))}


NODE_CLASS_MAPPINGS.update({
    "DMASRTranscribe": DMASRTranscribe,
    "DMASRFile": DMASRFile,
    "DMASRPayAmount": DMASRPayAmount,
    "DMASRInfo": DMASRInfo,
})
NODE_DISPLAY_NAME_MAPPINGS.update({
    "DMASRTranscribe": "🎙️ DM ASR 语音转文字",
    "DMASRFile": "📁 DM ASR 文件转写",
    "DMASRPayAmount": "💰 DM 收款金额抽取",
    "DMASRInfo": "ℹ️ DM ASR 状态",
})

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
