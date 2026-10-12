#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已锁定的 timeline/style/ZY 故事分镜派生六段式视频提示词。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


REQUIRED_STORY_FIELDS = (
    "story_beat", "narrative_before", "current_action", "implied_next",
    "space", "blocking", "props", "light", "camera_witness", "shot_delta",
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    a = ap.parse_args()
    project = Path(a.project_dir)
    timeline = load(project / "state" / "timeline.json")
    style = load(project / "state" / "style.json")
    storyboard_path = project / "state" / "storyboard.json"
    storyboard = load(storyboard_path)
    if storyboard.get("story_mode") != "zy_story_visual_development":
        raise ValueError(
            "缺少 ZY Cinematic Realism 故事分镜：请先生成 state/story_plan.json，"
            "再重新运行 storyboard_build.py"
        )
    prompts_dir = project / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    protagonist = next(iter(sorted((project / "input").glob("protagonist.*"))), None)
    character_fp = sha256_file(protagonist) if protagonist else "none"
    line_map = {line["index"]: line for line in timeline.get("lines", [])}
    keywords = "，".join(style.get("visual_keywords", []))
    director = style.get("director_ref", {})
    director_text = (f"，{director.get('name')}式克制构图" if director.get("name") else "")

    built = []
    for shot in storyboard.get("shots", []):
        missing = [key for key in REQUIRED_STORY_FIELDS if not shot.get(key)]
        if missing:
            raise ValueError(f"{shot.get('id')} 缺少故事字段: {','.join(missing)}")
        line = line_map.get(shot.get("lyric_line"))
        lyric = line.get("text", "") if line else ""
        lip = bool(shot.get("lip_sync"))
        scene = (f"{shot['space']}；道具与状态：{shot['props']}；"
                 f"实际光源：{shot['light']}；空间与人物调度：{shot['blocking']}")
        subject = (f"参考图只负责人物身份与服装：参考图中的年轻女子，{style.get('wardrobe', '')}；"
                   "跨镜保持五官比例、发型、耳饰、衣料纹样与层次完全一致，不继承参考图构图、背景或灯光"
                   if protagonist else "风沙中的边关环境与被岁月磨损的器物")
        base_action = shot["current_action"]
        if lip:
            performance = f"{base_action}，唇形随歌词自然开合\n{lyric}"
            audio_policy = f"人声驱动口型，逐字对齐歌词「{lyric}」"
            negative = "字幕, 水印, 念白, 面部变形, 多余人物, 夸张表情"
        else:
            performance = base_action
            audio_policy = "嘴唇自然闭合，不跟随人声开合；母带只负责剪辑节奏"
            negative = "字幕, 水印, 念白, lip movement, talking, singing mouth, 面部变形"
        window = shot["window"]
        prompt = {
            "meta": {
                "shot_id": shot["id"],
                "window": window,
                "duration_sec": round(float(window["end"]) - float(window["start"]), 10),
                "shot_type": shot["shot_type"],
                "lip_sync": lip,
                "backend": shot["backend"],
                "lyric_line": shot.get("lyric_line"),
                "lyric_text": lyric,
                "style_fingerprint": style.get("fingerprint"),
                "character_fingerprint": character_fp,
                "reference_duties": ["likeness", "wardrobe"] if protagonist else ["none"],
                "story_plan_fingerprint": storyboard.get("story_plan_fingerprint"),
            },
            "story": {
                "beat": shot["story_beat"],
                "before": shot["narrative_before"],
                "next": shot["implied_next"],
                "shot_delta": shot["shot_delta"],
            },
            "style": f"{style.get('style_name', '')}，{keywords}{director_text}",
            "scene": scene,
            "subject": subject,
            "performance": performance,
            "camera": f"{shot['shot_type']}，{shot['camera_witness']}，{shot.get('camera', '固定镜头')}，真实透视按空间关系自然变化",
            "audio_policy": audio_policy,
            "negative_prompt": negative,
        }
        out = prompts_dir / f"{shot['id']}.json"
        out.write_text(json.dumps(prompt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        built.append(out.name)

    print(json.dumps({"prompts": len(built), "character_fingerprint": character_fp,
                      "files": built}, ensure_ascii=False))


if __name__ == "__main__":
    main()
