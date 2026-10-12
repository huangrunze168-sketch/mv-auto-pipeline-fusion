#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已通过 ZY 门禁的逐镜分镜聚合为视频模型可接受的长章节。"""
import argparse
import json
import sys
from pathlib import Path


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
            sum(bool(shot.get("lip_sync")) for shot in chapter.get("shot_deltas", [])),
            len(chapter.get("shot_deltas", [])),
            float(chapter.get("duration_sec", 0)),
        ),
        reverse=True,
    )
    return ranked[0]["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--max-duration", type=float, default=15.0)
    ap.add_argument("--model", default="MiniMax H3")
    args = ap.parse_args()
    project = Path(args.project_dir)
    storyboard = load(project / "state" / "storyboard.json")
    story_plan = load(project / "state" / "story_plan.json")
    if storyboard.get("story_mode") != "zy_story_visual_development":
        raise ValueError("只有通过 ZY Story Visual Development 的分镜才能聚合章节")

    shots = storyboard.get("shots", [])
    if not shots:
        raise ValueError("storyboard.shots 不能为空")
    chapter_break_after = set(story_plan.get("chapter_break_after", []))
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
            "shot_deltas": [{
                "id": shot["id"],
                "story_beat": shot["story_beat"],
                "current_action": shot["current_action"],
                "space": shot["space"],
                "blocking": shot["blocking"],
                "props": shot["props"],
                "light": shot["light"],
                "camera_witness": shot["camera_witness"],
                "shot_delta": shot["shot_delta"],
                "lyric_line": shot.get("lyric_line"),
                "lip_sync": bool(shot.get("lip_sync")),
            } for shot in group],
            "delivery": {
                "aspect_ratio": "16:9",
                "model": args.model,
                "generation_mode": "reference-to-video",
                "audio_input": "audio_list",
                "motion_rule": "人物、衣料、道具、环境与摄影机分别产生因果明确的真实运动；禁止静态图缩放或平移冒充视频",
            },
        }
        chapters.append(chapter)

    prototype_id = select_prototype(chapters)
    plan = {
        "method": "zy_story_visual_development_to_video_chapters",
        "source_story_plan_fingerprint": storyboard.get("story_plan_fingerprint"),
        "max_duration_sec": args.max_duration,
        "model": args.model,
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
