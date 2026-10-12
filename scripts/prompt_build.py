#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已锁定的 timeline/style/storyboard 派生六段式视频提示词。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PERFORMANCES = {
    1: "女子站在战鼓旁抬眼望向关外，指尖缓缓握紧鼓槌，克制的担忧落在眼底",
    2: "女子坐在木案前翻开家书又轻轻合上，视线停在空白纸面",
    3: "女子低头握住掌心的胭脂扣，拇指擦过磨旧的金属边缘",
    4: "女子垂眼把红色丝结放回木案，另一只手缓慢收回袖中",
    5: "女子站在城楼门内抱紧红袖，长风把衣摆推向关外",
    6: "女子坐在铜镜前抬手整理发簪，目光越过镜面落向远处",
    7: "女子迈上城楼石阶，迎着风沙握住栏杆望向落霞",
    8: "女子坐在驿站檐下拨动琵琶弦，余光追随远处饮马的剪影",
    9: "女子抬头望向城楼上方的月牙，眼底映出清冷月色",
    10: "女子转身迎向卷过城门的狂沙，抬袖遮住眼睛仍不后退",
    11: "女子靠在残破门柱旁回望驿道，手中家书被夜风吹动",
    12: "女子站直身体握住褪色红袖，望向漠北尽头后缓缓抬头",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def pick(items, index, fallback):
    return items[index % len(items)] if items else fallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    a = ap.parse_args()
    project = Path(a.project_dir)
    timeline = load(project / "state" / "timeline.json")
    style = load(project / "state" / "style.json")
    storyboard_path = project / "state" / "storyboard.json"
    storyboard = load(storyboard_path)
    prompts_dir = project / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    protagonist = next(iter(sorted((project / "input").glob("protagonist.*"))), None)
    character_fp = sha256_file(protagonist) if protagonist else "none"
    line_map = {line["index"]: line for line in timeline.get("lines", [])}
    master = style.get("scene_master", {})
    spaces = master.get("space", [])
    lights = master.get("light_sources", [])
    props = master.get("props", [])
    keywords = "，".join(style.get("visual_keywords", []))
    director = style.get("director_ref", {})
    director_text = (f"，{director.get('name')}式克制构图" if director.get("name") else "")

    built = []
    for index, shot in enumerate(storyboard.get("shots", [])):
        line = line_map.get(shot.get("lyric_line"))
        lyric = line.get("text", "") if line else ""
        lip = bool(shot.get("lip_sync"))
        space = pick(spaces, index, "边关空间")
        light = pick(lights, index, "自然光")
        prop = pick(props, index, "旧物")
        scene = f"{space}内外相连，{light}从侧后方照亮石墙与风沙，前景放着{prop}，远处保留关外纵深"
        subject = (f"参考图只负责人物身份与服装：参考图中的年轻女子，{style.get('wardrobe', '')}；"
                   "跨镜保持五官比例、发型、耳饰、衣料纹样与层次完全一致，不继承参考图构图、背景或灯光"
                   if protagonist else "风沙中的边关环境与被岁月磨损的器物")
        base_action = PERFORMANCES.get(shot.get("lyric_line"))
        if not base_action:
            base_action = ("女子背对镜头走向残破城楼，抬手扶过冰冷石墙"
                           if protagonist else "火把在风中摆动，沙尘掠过残破城楼")
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
            },
            "style": f"{style.get('style_name', '')}，{keywords}{director_text}",
            "scene": scene,
            "subject": subject,
            "performance": performance,
            "camera": f"{shot['shot_type']}，{shot.get('camera', '固定镜头')}，真实透视与浅景深按空间关系自然变化",
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
