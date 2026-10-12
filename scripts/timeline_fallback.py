#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
timeline_fallback.py — 无 ASR key 时的降级对齐器（均匀分布）

机制：以首/末能量起始点为活动区间，官方歌词逐行均匀铺满，全部行标
  confidence=0.30 + pending_review（用户是词作者时可肉眼微调后点头）。
  首尾剩余区间标 interlude（intro/outro）。

这不是权威对齐——产出的时间轴只能用于流程试跑与静帧预览成片；
口型驱动的正式成片必须换回 ASR 通路重跑关 1。

用法:
  python timeline_fallback.py <song_16k.wav> <lyrics.txt> <out_timeline.json> [--intro 2.0] [--outro 2.0]
"""
import argparse
import json
import math
import wave
from pathlib import Path

SR = 16000
HOP = 400
ONSET_RMS = 0.35   # 相对峰值rms的起始判定阈值


def active_span(wav_path: str) -> tuple:
    with wave.open(wav_path) as w:
        data = w.readframes(w.getnframes())
    n = len(data) // 2                                # 帧数=字节数/2（16bit单声道）
    x = [int.from_bytes(data[2 * i:2 * i + 2], "little", signed=True) for i in range(n)]
    frames = [math.sqrt(sum(v * v for v in x[i:i + HOP]) / HOP) / 32768
              for i in range(0, n - HOP, HOP)]
    peak = max(frames)
    thr = peak * ONSET_RMS
    dur = n / SR
    first = next((i * HOP / SR for i, e in enumerate(frames) if e > thr), 0.0)
    last_idx = max(i for i, e in enumerate(frames) if e > thr)
    last = last_idx * HOP / SR
    return round(first, 3), round(min(last + HOP / SR, dur), 3), dur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song_wav")
    ap.add_argument("lyrics_txt")
    ap.add_argument("out_json")
    ap.add_argument("--intro", type=float, default=2.0)
    ap.add_argument("--outro", type=float, default=2.0)
    ap.add_argument("--song", default="song")
    a = ap.parse_args()

    first, last, dur = active_span(a.song_wav)
    lines = [ln.strip() for ln in Path(a.lyrics_txt).read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    span0 = min(first + a.intro, dur / 2)
    span1 = max(last - a.outro, span0 + len(lines))
    step = (span1 - span0) / len(lines)

    tl = {"song": a.song, "source_audio": "input/song.mp3", "duration_sec": round(dur, 3),
          "fps_assumed": 24, "asr_engine": "uniform_fallback",
          "lyrics_source": "official", "lines": [], "segments": [], "pending_review": []}
    tl["lines"].append({"index": 0, "type": "interlude", "text": "",
                        "start": 0.0, "end": round(span0, 3),
                        "confidence": 1.0, "corrected": False})
    for k, text in enumerate(lines):
        s, e = span0 + k * step, span0 + (k + 1) * step
        tl["lines"].append({"index": k + 1, "type": "vocal", "text": text,
                            "start": round(s, 3), "end": round(e, 3),
                            "confidence": 0.30, "corrected": False})
        tl["pending_review"].append(k + 1)
    tl["lines"].append({"index": len(lines) + 1, "type": "interlude", "text": "",
                        "start": round(span1, 3), "end": round(dur, 3),
                        "confidence": 1.0, "corrected": False})

    Path(a.out_json).write_text(json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")
    lrc = "\n".join(f"[{int(ln['start']//60):02d}:{ln['start']%60:05.2f}]{ln['text']}"
                    for ln in tl["lines"] if ln["type"] != "interlude")
    Path(a.out_json).with_suffix(".lrc").write_text(lrc + "\n", encoding="utf-8")
    print(json.dumps({"engine": "uniform_fallback", "lines": len(lines),
                      "active_span": [span0, span1], "duration_sec": round(dur, 3),
                      "pending_review": len(tl["pending_review"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
