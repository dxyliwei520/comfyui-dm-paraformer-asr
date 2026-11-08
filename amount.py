# -*- coding: utf-8 -*-
r"""
amount.py —— 「收款播报」金额抽取（从 text 里抠出金额 + 判断是不是收款）

来源：这台机器上 DM 支付监听（dm-paylistener）云端 /opt/manualpay/voiceasr.py 的生产逻辑，
原样搬进节点，保证「同一句话在节点里和在生产里得到同一个金额」。

为什么不用通用做法（直接正则 \d+\.\d+）：
    微信/支付宝的播报是**中文数字**：「微信支付收款三十五点零七元」
    ASR 出来的也可能是「35.07元」或「三十五点零七元」两种形态，必须都能解析。
    并且 ASR 会把「微信支付收款」听成「微信收看」等变体 —— 关键词表里要把变体收全。

作者：DSH（2026-11-08）
"""
from __future__ import annotations

import re

CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "壹": 1, "二": 2, "贰": 2, "两": 2,
    "三": 3, "叁": 3, "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6, "陆": 6,
    "七": 7, "柒": 7, "八": 8, "捌": 8, "九": 9, "玖": 9,
}
CN_UNITS = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000, "万": 10000}


def cn_int(s: str) -> int:
    """中文整数 → int（支持 十/百/千/万）"""
    total = section = number = 0
    for ch in s:
        if ch in CN_DIGITS:
            number = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            u = CN_UNITS[ch]
            if u == 10000:
                section = (section + number) * u
                total += section
                section = number = 0
            else:
                if number == 0:
                    number = 1          # 「十五」= 15
                section += number * u
                number = 0
    return total + section + number


def cn_number(s: str):
    """中文数字（可带「点」）→ float；解析不出返回 None"""
    s = (s or "").strip()
    if not s:
        return None
    if "点" in s:
        a, b = s.split("点", 1)
        ip = cn_int(a) if a else 0
        dp = ""
        for ch in b:
            if ch in CN_DIGITS:
                dp += str(CN_DIGITS[ch])
            else:
                break
        if not dp:
            return float(ip)
        return round(ip + float("0." + dp), 2)
    return float(cn_int(s))


# 收款播报关键词（含 ASR 常见变体，实测踩过「微信收看」）
KEYWORDS = (
    "微信支付收款到账", "微信支付收款", "微信支付到账", "微信支付成功收款",
    "微信收款到账", "微信收款", "微信收看", "微信支付", "微信到账",
    "支付宝成功收款", "支付宝收款", "支付宝到账", "支付宝",
    "二维码收款", "收款到账", "收款成功", "收款", "已收款", "收钱", "收看",
    "到账", "已到账", "收到一笔", "入账", "转账", "付款",
)

# 宽松兜底线索词：句子里有「钱味」且出现「X元/X块」也收（是否成交由账本决定）
LOOSE_HINTS = ("微信", "支付宝", "收款", "收看", "收钱", "到账", "入账",
               "转账", "付款", "支付", "二维码", "老板", "收到")

_RE_ARABIC = re.compile(r"([0-9]{1,7}(?:\.[0-9]{1,2})?)")
_RE_CN = re.compile(r"([零〇一二两三四五六七八九十百千万点]{1,14})")
_RE_YUAN = re.compile(r"([0-9]{1,7}(?:\.[0-9]{1,2})?|[零〇一二两三四五六七八九十百千万点]{1,14})\s*[元块]")


def _first_amount(seg: str):
    m = _RE_ARABIC.search(seg)
    n = _RE_CN.search(seg)
    cands = []
    if m:
        cands.append((m.start(), float(m.group(1))))
    if n:
        v = cn_number(n.group(1))
        if v is not None:
            cands.append((n.start(), v))
    cands.sort()
    for _, v in cands:
        if 0.0 < v <= 100000.0:
            return round(v, 2)
    return None


def normalize(text: str) -> str:
    t = (text or "").replace(" ", "").replace("\u3000", "")
    for a, b in (("￥", "¥"), ("，", ""), ("。", ""), ("、", ""), (",", ""), ("！", ""), ("!", "")):
        t = t.replace(a, b)
    return t


def extract_amount(text: str, keywords=KEYWORDS, loose: bool = True):
    """→ (amount|None, 命中关键词, 片段)

    两级判定：
      ① 严格：命中收款关键词 → 取关键词之后第一个数字
      ② 宽松：没命中关键词，但有线索词且出现「X元/X块」→ 也交出去
    拿不到返回 None —— 调用方据此拒绝（宁可漏，不可错）。
    """
    t = normalize(text)
    if not t:
        return None, "", ""
    for kw in keywords:
        i = t.find(kw)
        if i < 0:
            continue
        seg = t[i + len(kw): i + len(kw) + 18]
        amt = _first_amount(seg)
        if amt is not None:
            return amt, kw, seg
    if loose:
        hit = next((h for h in LOOSE_HINTS if h in t), "")
        if hit:
            m = _RE_YUAN.search(t)
            if m:
                raw = m.group(1)
                v = None
                if re.match(r"^[0-9]", raw):
                    try:
                        v = round(float(raw), 2)
                    except Exception:
                        v = None
                else:
                    v = cn_number(raw)
                if v is not None and 0.0 < v <= 100000.0:
                    return round(v, 2), "loose:" + hit, t[max(0, m.start() - 6):m.end() + 2]
    return None, "", t[:40]
