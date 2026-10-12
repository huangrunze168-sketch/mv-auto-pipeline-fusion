#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
storyboard_build.py — 步骤4工具：从 timeline 推导分镜（窗口/口型节奏/景别）

修 BUG-04：所有内部切点先吸附到帧网格（round(t*fps)/fps），末镜终点=全曲长原值。
  于是 duration_fit 的向上取整成为零操作，各段合计严格=全曲长，不会累积漂移。

口型节奏（铁律 B）：目标占比 45%，副歌优先，连续 ≤3 段；
景别：口型镜 ∈ {特写,近景,中景} 轮转，非口型镜 ∈ {全景,空镜,远景,背影} 轮转。

用法:
  python storyboard_build.py <project_dir> [--fps 24]
产出: state/storyboard.json（若存在 state/story_plan.json，则合并 ZY 故事分镜）
"""
import argparse
import json
import hashlib
from pathlib import Path

FPS_DEFAULT = 24
LIP_TARGET = 0.45
LIP_SHOTS = ["特写", "近景", "中景"]
NONLIP_SHOTS = ["全景", "空镜", "远景", "背影"]
CONCEPTS_LIP = ["人物近景承接歌词情绪，光线来自场景母版光源",
                "人物动作与歌词动词呼应，唇形随歌词开合",
                "人物与歌词意象同框，情绪落点清晰"]
CONCEPTS_NONLIP = ["环境空镜承接段落呼吸，不入人声口型",
                   "场景细节特写：母版道具承载叙事",
                   "远景交代人物与空间关系",
                   "背影跟拍，选择性可见"]

REQUIRED_STORY_FIELDS = {
    "story_beat", "narrative_before", "current_action", "implied_next",
    "space", "blocking", "props", "light", "camera_witness", "shot_delta",
    "visual_center", "information_hierarchy", "gaze_target", "action_physics",
    "material_response", "edit_trigger",
}


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def apply_story_plan(proj: Path, shots: list) -> tuple[str, dict, str | None]:
    """合并 Agent 按 ZY Story Visual Development 编写的故事方案。

    时间窗、歌词、口型、景别和生成职责仍由 MV 层掌管；故事方案只能补充叙事与
    Scene Master，不能覆盖这些硬事实。
    """
    path = proj / "state" / "story_plan.json"
    if not path.exists():
        for shot in shots:
            shot["story_status"] = "missing"
            shot["status"] = "pending_story"
        return "timing_only", {}, None

    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("method") != "zy_story_visual_development":
        raise ValueError("story_plan.method 必须为 zy_story_visual_development")
    plan_shots = {item.get("id"): item for item in plan.get("shots", [])}
    if set(plan_shots) != {shot["id"] for shot in shots}:
        raise ValueError("story_plan.shots 必须与 storyboard 镜头 ID 完整一致")

    for shot in shots:
        item = plan_shots[shot["id"]]
        missing = sorted(REQUIRED_STORY_FIELDS - set(item))
        if missing:
            raise ValueError(f"{shot['id']} 故事字段缺失: {','.join(missing)}")
        if item.get("lyric_line") != shot.get("lyric_line"):
            raise ValueError(f"{shot['id']} lyric_line 与时间轴不一致")
        # 明确白名单，避免故事层改写 MV 硬事实。
        for key in REQUIRED_STORY_FIELDS | {"purpose", "knowledge_state", "prop_state"}:
            if key in item:
                shot[key] = item[key]
        shot["visual_concept"] = item["story_beat"]
        shot["story_status"] = "ready"
        shot["status"] = "pending"

    continuity = plan.get("continuity_bible", {})
    return "zy_story_visual_development", continuity, sha256_file(path)


def snap(t: float, fps: float) -> float:
    # BUG-14 修法：存 10 位小数——6 位会让 46.791667*24=1123.000008，
    # 配合 duration_fit 的 1e-6 护栏失守，个别窗口被 ceil 顶高一帧
    return round(round(t * fps) / fps, 10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--fps", type=float, default=FPS_DEFAULT)
    a = ap.parse_args()
    proj = Path(a.project_dir)
    tl = json.loads((proj / "state" / "timeline.json").read_text(encoding="utf-8"))
    dur = float(tl["duration_sec"])
    fps = a.fps
    if fps <= 0:
        raise ValueError("--fps 必须大于 0")
    if dur <= 0:
        raise ValueError("timeline.duration_sec 必须大于 0")

    lines = tl["lines"]
    if not lines:
        raise ValueError("timeline.lines 不能为空")
    previous_start = -1.0
    for ln in lines:
        start, end = float(ln["start"]), float(ln["end"])
        if not (0 <= start < end <= dur + 0.001):
            raise ValueError(f"非法时间轴窗口: index={ln.get('index')} start={start} end={end}")
        if start < previous_start:
            raise ValueError("timeline.lines 必须按 start 单调递增")
        previous_start = start
    # BUG-08 修法：边界数组法——每个内部边界吸附一次、两侧行共享同一值，保证首尾相接
    bounds = [0.0] + [snap(ln["start"], fps) for ln in lines[1:]] + [round(dur, 6)]
    for i, ln in enumerate(lines):
        ln["start"], ln["end"] = bounds[i], bounds[i + 1]

    vocal = [ln for ln in lines if ln["type"] != "interlude"]
    # BUG-07 修法：间奏也建镜（空镜/远景），否则窗口合计≠全曲长，gate6 必拦
    n_total = len(lines)
    quota = round(LIP_TARGET * n_total)

    # 口型分配：第一遍副歌/后半段优先，第二遍补足配额；连续≤3
    order = sorted(range(len(vocal)), key=lambda i: (i < len(vocal) // 2, i))
    lip_flags = [False] * len(vocal)
    assigned = 0

    def run_ending_at(k, flags):
        r = 0
        j = k
        while j >= 0 and flags[j]:
            r += 1
            j -= 1
        return r

    for pass_limit in (1, 2):
        if assigned >= quota:
            break
        for k in order:
            if assigned >= quota and pass_limit == 1:
                break
            if pass_limit == 2 and lip_flags[k]:
                continue
            if pass_limit == 1 and lip_flags[k]:
                continue
            # 全局连续约束：看前后邻位
            prev_run = run_ending_at(k - 1, lip_flags) if k > 0 else 0
            nxt_run = 0
            j = k + 1
            while j < len(vocal) and lip_flags[j]:
                nxt_run += 1
                j += 1
            if prev_run + 1 + nxt_run > 3:
                continue
            lip_flags[k] = True
            assigned += 1
            if pass_limit == 1 and assigned >= quota:
                break

    shots = []
    li = ni = 0
    vocal_pos = {id(ln): i for i, ln in enumerate(vocal)}   # 重复文本行也能正确映射
    for k, ln in enumerate(lines):
        w_start = ln["start"] if k > 0 else lines[0]["start"]
        w_end = ln["end"]
        if ln["type"] == "interlude":
            shot_type = NONLIP_SHOTS[ni % len(NONLIP_SHOTS)]; ni += 1
            concept = CONCEPTS_NONLIP[ni % len(CONCEPTS_NONLIP)]
            shots.append({
                "id": f"SH{len(shots)+1:03d}", "segment": "S00",
                "lyric_line": None,
                "window": {"start": w_start, "end": w_end},
                "shot_type": shot_type, "lip_sync": False,
                "role": "insert",
                "visual_concept": f"间奏镜：{concept}",
                "camera": "缓慢横移",
                "generation_role": "narrative",
                "prompt_file": f"prompts/SH{len(shots)+1:03d}.json",
                "prompt_fingerprint": None,
                "repair": {"mode": "none", "problems": []},
                "status": "pending",
            })
            continue
        lip = lip_flags[vocal_pos[id(ln)]]
        if lip:
            shot_type = LIP_SHOTS[li % len(LIP_SHOTS)]; li += 1
            concept = CONCEPTS_LIP[li % len(CONCEPTS_LIP)]
        else:
            shot_type = NONLIP_SHOTS[ni % len(NONLIP_SHOTS)]; ni += 1
            concept = CONCEPTS_NONLIP[ni % len(CONCEPTS_NONLIP)]
        shots.append({
            "id": f"SH{k+1:03d}", "segment": "S01",
            "lyric_line": ln["index"],
            "window": {"start": ln["start"], "end": ln["end"]},
            "shot_type": shot_type, "lip_sync": lip,
            "role": "perform" if lip else "narrative",
            "visual_concept": f"「{ln['text']}」：{concept}",
            "camera": "缓慢推近" if lip else "固定镜头",
            "generation_role": "lip_sync" if lip else "narrative",
            "prompt_file": f"prompts/SH{k+1:03d}.json",
            "prompt_fingerprint": None,
            "repair": {"mode": "none", "problems": []},
            "status": "pending",
        })
    story_mode, continuity, story_fp = apply_story_plan(proj, shots)
    sb = {"shots": shots, "lip_ratio_target": LIP_TARGET,
          "consecutive_lip_limit": 3, "fps": fps,
          "frame_snapped": True,
          "story_mode": story_mode,
          "story_plan_fingerprint": story_fp,
          "continuity_bible": continuity}
    (proj / "state").mkdir(parents=True, exist_ok=True)
    (proj / "state" / "storyboard.json").write_text(
        json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    lip_n = sum(1 for s in shots if s["lip_sync"])
    total = sum(s["window"]["end"] - s["window"]["start"] for s in shots)
    print(json.dumps({"shots": len(shots), "lip": lip_n,
                      "ratio": round(lip_n / len(shots), 3),
                      "windows_sum": round(total, 3), "song": dur}, ensure_ascii=False))


if __name__ == "__main__":
    main()
