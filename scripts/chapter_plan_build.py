#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已通过 ZY 门禁的逐镜分镜聚合为视频模型可接受的长章节。"""
import argparse
import json
import sys
from pathlib import Path

try:
    from .visual_development import fingerprint
except ImportError:
    from visual_development import fingerprint


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def group_shots(shots: list, max_duration: float, break_after: set[str] | None = None) -> list[list]:
    if max_duration <= 0:
        raise ValueError("--max-duration 必须大于 0")
    groups, current = [], []
    break_after = break_after or set()
    for shot in shots:
        duration = float(shot["window"]["end"]) - float(shot["window"]["start"])
        if duration > max_duration + 1e-6:
            raise ValueError(f"{shot['id']} 单镜时长超过模型上限 {max_duration}")
        candidate = current + [shot]
        candidate_duration = (float(candidate[-1]["window"]["end"]) -
                              float(candidate[0]["window"]["start"]))
        if current and candidate_duration > max_duration + 1e-6:
            groups.append(current)
            current = [shot]
        else:
            current = candidate
        if current and shot["id"] in break_after:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def select_prototype(chapters: list[dict]) -> str:
    """优先选择口型与叙事变化最多的一章做样片，禁止直接全量试错。"""
    if not chapters:
        raise ValueError("chapters 不能为空")
    ranked = sorted(
        chapters,
        key=lambda chapter: (
            sum(len(shot.get("risk_tags", [])) for shot in chapter.get("shot_deltas", [])),
            sum(bool(shot.get("lip_sync")) for shot in chapter.get("shot_deltas", [])),
            len(chapter.get("shot_deltas", [])),
            float(chapter.get("duration_sec", 0)),
        ),
        reverse=True,
    )
    return ranked[0]["id"]


def require_production_timing(timeline: dict, shots: list[dict]) -> None:
    """临时/待核时间轴可做视觉设计，但不得进入正式口型视频准备。"""
    if not any(bool(shot.get("lip_sync")) for shot in shots):
        return
    authority = str(timeline.get("authority", "")).lower()
    problems = []
    if timeline.get("production_timing_verified") is not True:
        problems.append("production_timing_verified 不是 true")
    if timeline.get("pending_review"):
        problems.append("仍有 pending_review 歌词行")
    if timeline.get("simulation_only") is True:
        problems.append("timeline 标记为 simulation_only")
    if any(word in authority for word in ("provisional", "pending", "diagnostic", "fallback")):
        problems.append(f"authority={timeline.get('authority')}")
    if problems:
        raise ValueError("口型章节禁止使用临时或待核时间轴: " + "; ".join(problems))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--max-duration", type=float, required=True,
                    help="用户选定后端并核验契约后提供的单次生成时长上限")
    args = ap.parse_args()
    project = Path(args.project_dir)
    storyboard = load(project / "state" / "storyboard.json")
    story_plan = load(project / "state" / "story_plan.json")
    style = load(project / "state" / "style.json")
    timeline = load(project / "state" / "timeline.json")
    aspect_ratio = str(style.get("aspect_ratio", "")).strip()
    if not aspect_ratio:
        raise ValueError("style.aspect_ratio 不能为空")
    if storyboard.get("story_mode") != "zy_story_visual_development":
        raise ValueError("只有通过 ZY Story Visual Development 的分镜才能聚合章节")

    shots = storyboard.get("shots", [])
    if not shots:
        raise ValueError("storyboard.shots 不能为空")
    require_production_timing(timeline, shots)
    chapter_break_after = set(story_plan.get("chapter_break_after", []))
    chapter_break_after.update(a["id"] for a, b in zip(shots, shots[1:])
                               if a.get("scene_id") != b.get("scene_id"))
    groups = group_shots(shots, args.max_duration, chapter_break_after)
    continuity = storyboard.get("continuity_bible", {})
    chapters = []
    for index, group in enumerate(groups, 1):
        start = float(group[0]["window"]["start"])
        end = float(group[-1]["window"]["end"])
        chapter = {
            "id": f"CH{index:02d}",
            "window": {"start": start, "end": end},
            "duration_sec": round(end - start, 10),
            "shot_ids": [shot["id"] for shot in group],
            "reference_role": "人物身份与服装；不继承参考图构图、背景或灯光",
            "continuity_lock": continuity,
            "shot_deltas": [{key: value for key, value in shot.items()
                             if key not in {"prompt_fingerprint", "status", "repair"}}
                            for shot in group],
            "delivery": {
                "aspect_ratio": aspect_ratio,
                "backend": None,
                "adapter": None,
                "contract_status": "awaiting_user_selection",
                "motion_rule": "人物、衣料、道具、环境与摄影机分别产生因果明确的真实运动；禁止静态图缩放或平移冒充视频",
            },
        }
        chapters.append(chapter)

    prototype_id = select_prototype(chapters)
    plan = {
        "method": "zy_story_visual_development_to_video_chapters",
        "source_story_plan_fingerprint": storyboard.get("story_plan_fingerprint"),
        "source_storyboard_fingerprint": fingerprint(project / "state" / "storyboard.json"),
        "max_duration_sec": args.max_duration,
        "backend": None,
        "backend_contract_status": "awaiting_user_selection",
        "chapter_break_after": sorted(chapter_break_after),
        "production_policy": {
            "mode": "prototype_first",
            "prototype_chapter": prototype_id,
            "allowed_before_director_review": [prototype_id],
            "batch_generation_requires": "state/director_review.json decision=approve",
            "technical_pass_is_not_director_pass": True,
        },
        "chapters": chapters,
    }
    out = project / "state" / "chapter_plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"chapters": len(chapters),
                      "durations": [c["duration_sec"] for c in chapters],
                      "output": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
