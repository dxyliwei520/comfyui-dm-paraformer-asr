# -*- coding: utf-8 -*-
"""
asr.py —— 离线语音识别核心（sherpa-onnx + Paraformer 中文小模型，纯 CPU）

模型：paraformer-zh-small（int8 ONNX，约 78 MB，Apache-2.0）
    文件：model.int8.onnx + tokens.txt (+ am.mvn 由 sherpa 内部按需使用)
    速度：3~4 秒音频 20~110 ms（CPU，2 线程），不占显存、不联网

模型放在哪（按顺序找，找到第一个就用）：
    1. 环境变量 DM_ASR_DIR 指向的目录
    2. <ComfyUI>/models/ASR/paraformer-zh-small/
    3. 本节点目录/models/paraformer-zh-small/
    4. 都没有 → 自动从 hf-mirror 下载到 2（设 DM_ASR_NO_DOWNLOAD=1 可禁止）

作者：DSH（2026-11-08）
"""
from __future__ import annotations

import os
import threading
import time

SAMPLE_RATE = 16000
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_SUBDIR = os.path.join("ASR", "paraformer-zh-small")
FILES = ("model.int8.onnx", "tokens.txt", "am.mvn")
HF_BASE = "https://hf-mirror.com/csukuangfj/sherpa-onnx-paraformer-zh-small-2024-03-09/resolve/main"

_load_lock = threading.Lock()
_rec_lock = threading.Lock()
_state = {"rec": None, "err": "", "dir": "", "threads": 0}


# ----------------------------------------------------------------- 模型位置
def _comfy_models_dir():
    try:
        import folder_paths
        base = getattr(folder_paths, "models_dir", "")
        if base and os.path.isdir(base):
            return base
        # 旧版本：folder_paths 模块位于 ComfyUI 根目录
        root = os.path.dirname(os.path.dirname(os.path.abspath(folder_paths.__file__)))
        cand = os.path.join(root, "models")
        if os.path.isdir(cand):
            return cand
    except Exception:
        pass
    return ""


def candidate_dirs():
    out = []
    env = os.environ.get("DM_ASR_DIR", "").strip()
    if env:
        out.append(env)
    cm = _comfy_models_dir()
    if cm:
        out.append(os.path.join(cm, MODEL_SUBDIR))
        out.append(os.path.join(cm, "ASR"))
    out.append(os.path.join(HERE, "models", "paraformer-zh-small"))
    out.append(os.path.join(HERE, "models"))
    # 去重保序
    seen, uniq = set(), []
    for d in out:
        k = os.path.normcase(d)
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


def find_model():
    """→ (目录, model 路径, tokens 路径) 或 (None, None, None)"""
    for d in candidate_dirs():
        m = os.path.join(d, "model.int8.onnx")
        t = os.path.join(d, "tokens.txt")
        if os.path.isfile(m) and os.path.isfile(t):
            return d, m, t
    return None, None, None


def download_model(verbose=True):
    """从 hf-mirror 拉模型到 <ComfyUI>/models/ASR/paraformer-zh-small（返回目录或 None）"""
    if os.environ.get("DM_ASR_NO_DOWNLOAD", "").strip() in ("1", "true", "True"):
        return None
    cm = _comfy_models_dir() or os.path.join(HERE, "models")
    dst = os.path.join(cm, MODEL_SUBDIR)
    os.makedirs(dst, exist_ok=True)
    try:
        import urllib.request
        for fn in FILES:
            p = os.path.join(dst, fn)
            if os.path.isfile(p) and os.path.getsize(p) > 1000:
                continue
            if verbose:
                print("[DM-ASR] 下载模型 %s ..." % fn)
            urllib.request.urlretrieve(HF_BASE + "/" + fn, p)
        d, m, t = find_model()
        return d
    except Exception as e:
        print("[DM-ASR] 模型自动下载失败：%r（可手动把 model.int8.onnx/tokens.txt/am.mvn "
              "放到 models/ASR/paraformer-zh-small/）" % (e,))
        return None


# ----------------------------------------------------------------- 识别器
def get_recognizer(num_threads=2, auto_download=True):
    if _state["rec"] is not None:
        return _state["rec"]
    with _load_lock:
        if _state["rec"] is not None:
            return _state["rec"]
        try:
            import sherpa_onnx
        except Exception as e:
            _state["err"] = "sherpa-onnx 未安装（pip install sherpa-onnx）：%r" % (e,)
            return None
        d, m, t = find_model()
        if d is None and auto_download:
            d = download_model()
            if d:
                d, m, t = find_model()
        if d is None:
            _state["err"] = "找不到模型（应该是 models/ASR/paraformer-zh-small/model.int8.onnx）"
            return None
        try:
            t0 = time.time()
            n = max(1, min(8, int(num_threads or 2)))
            rec = sherpa_onnx.OfflineRecognizer.from_paraformer(
                paraformer=m, tokens=t, num_threads=n,
                sample_rate=SAMPLE_RATE, feature_dim=80,
                decoding_method="greedy_search")
            _state.update({"rec": rec, "err": "", "dir": d, "threads": n})
            print("[DM-ASR] paraformer 就绪：%s（%d 线程，加载 %.1fs）" % (d, n, time.time() - t0))
            return rec
        except Exception as e:
            _state["err"] = "paraformer 初始化失败：%r" % (e,)
            return None


def status():
    d, m, t = find_model()
    return {
        "ready": _state["rec"] is not None,
        "model_dir": d or "",
        "model_file": m or "",
        "threads": _state["threads"],
        "error": _state["err"],
        "candidates": candidate_dirs(),
    }


# ----------------------------------------------------------------- 音频转换
def _to_mono_numpy(waveform):
    """torch 张量 [B,C,T] / [C,T] / [T] → 1D float32 numpy（单声道）"""
    try:
        import numpy as np
    except Exception as e:
        raise RuntimeError("需要 numpy：%r" % (e,))
    x = waveform
    try:
        if hasattr(x, "dim"):
            if x.dim() == 3:
                x = x[0]
            if x.dim() == 2:
                x = x.mean(dim=0)
            x = x.detach().float().cpu().numpy()
    except Exception:
        pass
    arr = np.asarray(x, dtype="float32").reshape(-1)
    return arr


def _resample(arr, sr_in, sr_out=SAMPLE_RATE):
    import numpy as np
    if int(sr_in) == int(sr_out) or arr.size == 0:
        return arr.astype("float32")
    try:
        import torch
        import torchaudio.functional as F  # noqa: F401
        t = torch.from_numpy(arr).unsqueeze(0)
        out = torchaudio.functional.resample(t, int(sr_in), int(sr_out))
        return out.squeeze(0).numpy().astype("float32")
    except Exception:
        n_out = max(1, int(round(arr.size * float(sr_out) / float(sr_in))))
        idx = np.linspace(0, arr.size - 1, n_out, dtype="float64")
        return np.interp(idx, np.arange(arr.size), arr).astype("float32")


def audio_to_16k(audio):
    """ComfyUI 的 AUDIO dict → 16k 单声道 float32 numpy"""
    if not isinstance(audio, dict):
        raise RuntimeError("AUDIO 输入格式不对（应该是 LoadAudio 输出的 AUDIO）")
    wav = audio.get("waveform")
    sr = int(audio.get("sample_rate") or SAMPLE_RATE)
    if wav is None:
        raise RuntimeError("AUDIO 里没有 waveform")
    arr = _to_mono_numpy(wav)
    # 归一化：整数 PCM（如 LoadAudio 有时给 int16 量级）→ [-1,1]
    peak = float(abs(arr).max()) if arr.size else 0.0
    if peak > 1.5:
        arr = arr / 32768.0
    arr = _resample(arr, sr)
    if arr.size:
        arr = arr - float(arr.mean())            # 去直流
    return arr


# ----------------------------------------------------------------- 转写
def _decode(rec, samples):
    st = rec.create_stream()
    st.accept_waveform(SAMPLE_RATE, samples)
    rec.decode_stream(st)
    return (st.result.text or "").strip()


def transcribe_samples(samples, num_threads=2, max_chunk_sec=25.0, overlap_sec=0.2):
    """任意长度 → (text, info)"""
    rec = get_recognizer(num_threads)
    if rec is None:
        raise RuntimeError(_state["err"] or "ASR 引擎不可用")
    import numpy as np
    n = int(samples.size)
    dur = n / float(SAMPLE_RATE)
    if n < int(0.05 * SAMPLE_RATE):
        return "", {"duration": round(dur, 3), "chunks": 0, "elapsed": 0.0,
                    "engine": "paraformer-zh-small", "model": _state["dir"],
                    "note": "音频太短（<0.05s），跳过"}
    step = max(1, int(max_chunk_sec * SAMPLE_RATE))
    ov = max(0, int(overlap_sec * SAMPLE_RATE))
    t0 = time.time()
    parts, chunks = [], 0
    with _rec_lock:
        i = 0
        while i < n:
            seg = samples[i: i + step]
            if seg.size:
                txt = _decode(rec, np.ascontiguousarray(seg, dtype="float32"))
                if txt:
                    parts.append(txt)
                chunks += 1
            i += max(1, step - ov)
    text = "".join(parts).replace(" ", "")
    return text, {"duration": round(dur, 3), "chunks": chunks,
                  "elapsed": round(time.time() - t0, 3),
                  "engine": "paraformer-zh-small", "model": _state["dir"]}


# ----------------------------------------------------------------- 文件直读
def transcribe_file(path, num_threads=2, max_chunk_sec=25.0):
    """直接读音频文件（wav/flac 用标准库；其它交给 av 解码）"""
    if not path or not os.path.isfile(path):
        raise RuntimeError("文件不存在：%s" % path)
    ext = os.path.splitext(path)[1].lower()
    import numpy as np
    if ext in (".wav", ".flac"):
        try:
            import wave as _w
            with _w.open(path, "rb") as f:
                sr = f.getframerate()
                ch = f.getnchannels()
                sw = f.getsampwidth()
                raw = f.readframes(f.getnframes())
            if sw == 2:
                arr = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
            elif sw == 1:
                arr = (np.frombuffer(raw, dtype="<u1").astype("float32") - 128.0) / 128.0
            elif sw == 4:
                arr = np.frombuffer(raw, dtype="<i4").astype("float32") / 2147483648.0
            else:
                raise RuntimeError("不支持的位深：%s bit" % (sw * 8))
            if ch > 1:
                arr = arr.reshape(-1, ch).mean(axis=1)
            return transcribe_samples(_resample(arr.astype("float32"), sr), num_threads, max_chunk_sec)
        except Exception as e:
            if ext == ".wav":
                raise RuntimeError("读 wav 失败：%r" % (e,))
    try:
        import av  # ComfyUI 自带
        container = av.open(path)
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
        chunks = []
        for frame in container.decode(stream):
            for f in resampler.resample(frame):
                chunks.append(np.frombuffer(f.to_ndarray().tobytes(), dtype="float32"))
        if not chunks:
            raise RuntimeError("没解出音频")
        return transcribe_samples(np.concatenate(chunks).astype("float32"), num_threads, max_chunk_sec)
    except Exception as e:
        raise RuntimeError("解码失败（%s）：%r" % (ext, e))
