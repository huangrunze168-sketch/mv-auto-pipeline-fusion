#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_checks.py — 关5/关6 硬门禁机检器（纯标准库）

用法:
  python gate_checks.py gate1 <project_dir>            # 校验 timeline.json（关1）
  python gate_checks.py gate5 <project_dir>            # 校验 prompts/*.json，14 项机检（11 基础 + 3 扩展项）
  python gate_checks.py gate6 <project_dir>            # 校验 storyboard.json 窗口与口型

退出码: 0 = 全绿放行; 1 = 存在失败项（硬门禁阻断）
输出:   JSON 报告到 stdout；同时返回逐项明细供 HTML 关页渲染
"""
import json
import re
import sys
import hashlib
from pathlib import Path

LIPSYNC_WHITELIST = {"大特写", "特写", "近景", "中景"}
SIX_SECTIONS = ["style", "scene", "subject", "performance", "camera", "audio_policy"]
SING_MARK_RE = re.compile(r"唱|开口唱|歌声")
SPEECH_RE = re.compile(r"说.{0,4}[「\"'‘“]|说.{0,6}话")
SECONDS_RE = re.compile(r"\d+(\.\d+)?\s*秒")
LIP_NEG_RE = re.compile(r"lip|mouth|嘴|口型", re.I)
CLOSED_LIP_DECL = "嘴唇自然闭合"

# 扩展项 #12：具体动作词表（非穷举，覆盖常见叙事动作）
ACTION_WORDS = ["抬", "握", "拿", "放", "坐", "站", "走", "跑", "跪", "靠", "推",
                "拉", "翻", "合", "转", "低头", "抬头", "回", "垂", "抱", "递",
                "拨", "点", "写", "穿", "脱", "擦", "点", "迈", "俯", "仰"]
REF_DUTIES = {"composition", "color", "lighting", "material", "likeness", "none"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------- 关1 · 时间轴机检 ----------------

def check_timeline(tl: dict, lyrics_text: str) -> list:
    checks = []

    def add(name, ok, evidence=""):
        checks.append({"item": name, "pass": bool(ok), "evidence": str(evidence)[:200]})

    vocal = [ln for ln in tl.get("lines", []) if ln["type"] != "interlude"]
    interludes = [ln for ln in tl.get("lines", []) if ln["type"] == "interlude"]

    # ① 行数与官方歌词一致（非空行）
    official_lines = [ln.strip() for ln in lyrics_text.splitlines() if ln.strip()]
    add("歌词一行不能少", len(vocal) == len(official_lines),
        f"timeline={len(vocal)} official={len(official_lines)}")

    # ② 时间单调递增无重叠
    seq = tl.get("lines", [])
    bad = [(a["index"], b["index"]) for a, b in zip(seq, seq[1:])
           if float(b["start"]) < float(a["end"]) - 0.001]
    add("时间单调无重叠", not bad, str(bad[:3]))

    # ③ 全曲时长字段有效
    add("时长字段有效", float(tl.get("duration_sec", -1)) > 0, tl.get("duration_sec"))

    # ④ 间奏显式标注（至少一个 interlude，或显式声明无间奏）
    add("间奏显式标注", len(interludes) >= 1 or tl.get("no_interlude") is True,
        f"interludes={len(interludes)}")

    # ⑤ 待核清单：confidence < 0.85 的行必须全部登记 pending_review
    low = [ln["index"] for ln in vocal if float(ln.get("confidence", 1)) < 0.85]
    pend = tl.get("pending_review", [])
    add("待核行已登记", set(low) <= set(pend),
        f"low_conf={low[:5]} pending={pend[:5]}")

    # ⑥ 对齐引擎必须显式声明（uniform_fallback 不可冒充权威对齐）
    eng = tl.get("asr_engine", "")
    add("对齐引擎已声明", bool(eng), f"engine={eng}")
    return checks


# ---------------- 关5 · 11 项机检 ----------------

def check_prompt(pr: dict, timeline: dict, style: dict, has_protagonist: bool) -> list:
    meta = pr.get("meta", {})
    checks = []

    def add(idx, name, ok, evidence=""):
        checks.append({"shot_id": meta.get("shot_id"), "idx": idx, "item": name,
                       "pass": bool(ok), "evidence": str(evidence)[:120]})

    song_dur = timeline.get("duration_sec", 0)
    line_map = {ln["index"]: ln for ln in timeline.get("lines", [])}
    perf = pr.get("performance", "")
    audio = pr.get("audio_policy", "")
    neg = pr.get("negative_prompt", "")
    lip = bool(meta.get("lip_sync"))
    w = meta.get("window", {})
    wlen = float(w.get("end", 0)) - float(w.get("start", 0))

    # 1 六段齐全
    missing = [k for k in SIX_SECTIONS if not str(pr.get(k, "")).strip()]
    add(1, "六段齐全", not missing, "missing=" + ",".join(missing))

    # 2 语言分层：歌词文本与 timeline 对应行逐字一致
    # BUG-09 修法：间奏镜(lyric_line=None或对应interlude行)不得携带歌词文本；
    # 空字典.get("text")返回None而非""，直接比较有假阳性
    li = meta.get("lyric_line")
    ln = line_map.get(li) if li is not None else None
    if ln is None or ln.get("type") == "interlude":
        lyric_ok = not (meta.get("lyric_text") or "").strip()
    else:
        lyric_ok = ln.get("text", "") == (meta.get("lyric_text") or "")
    add(2, "歌词与时间轴逐字一致", lyric_ok,
        f"timeline='{(ln or {}).get('text','')}' vs meta='{meta.get('lyric_text','')}'")

    # 3 唱歌格式：口型段 performance 含歌词独立行
    add(3, "口型段歌词独立成行", (not lip) or (meta.get("lyric_text", "") in perf.splitlines()),
        "lyric_in_performance_lines")

    # 4 念白禁令
    full_text = " ".join(str(pr.get(k, "")) for k in SIX_SECTIONS)
    add(4, "无念白句式", not SPEECH_RE.search(full_text), SPEECH_RE.search(full_text))

    # 5 非口型闭口声明
    ok5 = True
    if not lip:
        ok5 = (CLOSED_LIP_DECL in audio) and bool(LIP_NEG_RE.search(neg))
    add(5, "非口型段闭口声明+负面压口型", ok5,
        f"decl={CLOSED_LIP_DECL in audio} neg_has_lip={bool(LIP_NEG_RE.search(neg))}")

    # 6 非口型段无唱歌标记
    add(6, "非口型段无唱歌标记", lip or not SING_MARK_RE.search(perf + audio),
        SING_MARK_RE.search(perf + audio))

    # 7 景别白名单
    add(7, "口型段景别白名单", (not lip) or meta.get("shot_type") in LIPSYNC_WHITELIST,
        meta.get("shot_type"))

    # 8 禁手写秒数
    add(8, "正文无手写秒数", not SECONDS_RE.search(full_text), SECONDS_RE.search(full_text))

    # 9 时长一致
    dur = float(meta.get("duration_sec", -1))
    add(9, "duration_sec与窗口一致", abs(dur - wlen) < 0.05, f"meta={dur} window={wlen:.3f}")

    # 10 窗口合法
    ok10 = 0 <= float(w.get("start", -1)) < float(w.get("end", -1)) <= song_dur + 0.05
    add(10, "窗口合法", ok10, f"{w} song={song_dur}")

    # 11 指纹一致
    fp_ok = meta.get("style_fingerprint") == style.get("fingerprint")
    char_ok = (meta.get("character_fingerprint") not in (None, "", "REF")) if has_protagonist else True
    add(11, "风格/人物指纹一致", fp_ok and char_ok,
        f"style_ok={fp_ok} char_ok={char_ok}")

    # ---- 扩展项 #12-#14（具体瞬间/场景母版/参考职责）----

    # 12 具体瞬间：performance 含具体动作词
    hit = [w for w in ACTION_WORDS if w in perf]
    add(12, "具体瞬间（含动作词）", len(perf.strip()) >= 10 and bool(hit),
        f"actions={hit[:3]} len={len(perf.strip())}")

    # 13 场景母版一致：scene 命中锁定关键词
    sm = style.get("scene_master", {})
    if sm.get("locked"):
        locked_words = sum((sm.get(k, []) for k in ("space", "light_sources", "props")), [])
        hit13 = [w for w in locked_words if w in pr.get("scene", "")]
        add(13, "场景母版一致", bool(hit13), f"hit={hit13[:2]} locked={locked_words[:4]}")
    else:
        add(13, "场景母版一致", True, "scene_master未锁定，跳过")

    # 14 参考职责声明
    duties = meta.get("reference_duties", [])
    enum_ok = all(d in REF_DUTIES for d in duties)
    likeness_ok = (not has_protagonist) or ("likeness" in duties)
    add(14, "参考职责声明", enum_ok and likeness_ok,
        f"duties={duties} enum_ok={enum_ok} likeness_ok={likeness_ok}")

    return checks


# ---------------- 关6 · 窗口与口型 ----------------

def check_storyboard(sb: dict, timeline: dict) -> list:
    shots = sorted(sb.get("shots", []), key=lambda s: s["window"]["start"])
    song_dur = float(timeline.get("duration_sec", 0))
    checks = []

    def add(name, ok, evidence=""):
        checks.append({"item": name, "pass": bool(ok), "evidence": str(evidence)[:200]})

    # ① 首尾相接
    gaps = []
    for a, b in zip(shots, shots[1:]):
        d = float(b["window"]["start"]) - float(a["window"]["end"])
        if abs(d) > 0.001:
            gaps.append(f"{a['id']}->{b['id']}:{d:+.3f}")
    add("窗口首尾相接", not gaps, ";".join(gaps))

    # ② 合计=全曲长
    total = sum(float(s["window"]["end"]) - float(s["window"]["start"]) for s in shots)
    add("合计等于全曲长", abs(total - song_dur) < 0.05, f"sum={total:.3f} song={song_dur}")

    # ③ 口型景别白名单
    bad = [s["id"] for s in shots if s.get("lip_sync") and s.get("shot_type") not in LIPSYNC_WHITELIST]
    add("口型景别白名单", not bad, ",".join(bad))

    # ④ 口型占比 45%±10%
    lip_n = sum(1 for s in shots if s.get("lip_sync"))
    ratio = lip_n / len(shots) if shots else 0
    add("口型占比∈[0.35,0.55]目标0.45", 0.35 <= ratio <= 0.55, f"ratio={ratio:.2f}")

    # ⑤ 连续口型≤3
    run = mx = 0
    for s in shots:
        run = run + 1 if s.get("lip_sync") else 0
        mx = max(mx, run)
    add("连续口型≤3段", mx <= int(sb.get("consecutive_lip_limit", 3)), f"max_run={mx}")

    # ⑥ 无手写秒数（分镜自由文本字段）
    sec_hits = [s["id"] for s in shots
                if SECONDS_RE.search(str(s.get("visual_concept", "")) + str(s.get("camera", "")))]
    add("分镜无手写秒数", not sec_hits, ",".join(sec_hits))

    # ⑦ 切点落在歌词行边界，或间奏/无歌词区间内部（间奏决定分镜切点，铁律 A）
    boundaries = sorted({round(float(ln[k]), 2) for ln in timeline.get("lines", [])
                         for k in ("start", "end")} | {0.0, round(song_dur, 2)})
    interludes = [(float(ln["start"]), float(ln["end"]))
                  for ln in timeline.get("lines", []) if ln["type"] == "interlude"]
    # 时间轴未覆盖的尾部（如尾奏）视同间奏
    last_end = max((float(ln["end"]) for ln in timeline.get("lines", [])), default=0.0)
    if last_end < song_dur:
        interludes.append((last_end, song_dur))
    bad_cuts = []
    for s in shots[:-1]:
        e = float(s["window"]["end"])
        near_boundary = any(abs(round(e, 2) - b) < 0.2 for b in boundaries)
        in_interlude = any(st + 0.2 < e < en - 0.2 for st, en in interludes)
        if not (near_boundary or in_interlude):
            bad_cuts.append(f"{s['id']}@{round(e, 2)}")
    add("切点在歌词行边界或间奏内", not bad_cuts, ";".join(bad_cuts))

    # ⑧ 歌词行全覆盖（几何判定：行中点落入某窗口即算覆盖——兼容一窗多行，BUG-05 修法）
    vocal_lines = [ln for ln in timeline.get("lines", []) if ln["type"] != "interlude"]
    missing = []
    for ln in vocal_lines:
        mid = (float(ln["start"]) + float(ln["end"])) / 2
        if not any(float(s["window"]["start"]) <= mid <= float(s["window"]["end"])
                   for s in shots):
            missing.append(ln["index"])
    add("歌词行全覆盖(几何)", not missing, str(missing))

    return checks


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("gate1", "gate5", "gate6"):
        print(__doc__)
        sys.exit(2)
    proj = Path(sys.argv[2])
    timeline = load(proj / "state" / "timeline.json")
    # BUG-06 修法：style.json 在关2才产出，关1不得依赖它
    style = load(proj / "state" / "style.json") if (proj / "state" / "style.json").exists() else {}
    has_protagonist = any((proj / "input").glob("protagonist.*"))

    if sys.argv[1] == "gate1":
        lyrics = (proj / "input" / "lyrics.txt").read_text(encoding="utf-8") \
            if (proj / "input" / "lyrics.txt").exists() else ""
        checks = check_timeline(timeline, lyrics)
        report = {"gate": 1, "checks": checks}
        all_ok = all(c["pass"] for c in checks)
        n_pass, n_total = sum(1 for c in checks if c["pass"]), len(checks)
        print(json.dumps({**report, "summary": {"pass": all_ok, "passed": n_pass,
                                                "total": n_total}},
                         ensure_ascii=False, indent=2))
        sys.exit(0 if all_ok else 1)

    if sys.argv[1] == "gate5":
        report = {"gate": 5, "shots": []}
        all_ok = True
        for pf in sorted((proj / "prompts").glob("SH*.json")):
            checks = check_prompt(load(pf), timeline, style, has_protagonist)
            report["shots"].append({"file": pf.name, "checks": checks,
                                    "fingerprint": sha256_file(pf)})
            all_ok &= all(c["pass"] for c in checks)
        if not report["shots"]:
            all_ok = False  # 没有任何提示词 = 不可能放行
    else:
        sb = load(proj / "state" / "storyboard.json")
        checks = check_storyboard(sb, timeline)
        report = {"gate": 6, "checks": checks}
        all_ok = all(c["pass"] for c in checks)

    if sys.argv[1] == "gate6":
        n_pass = sum(1 for c in report["checks"] if c["pass"])
        n_total = len(report["checks"])
    else:
        n_pass = sum(1 for s in report["shots"] for c in s["checks"] if c["pass"])
        n_total = sum(len(s["checks"]) for s in report["shots"])
    report["summary"] = {"pass": all_ok, "passed": n_pass, "total": n_total}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
