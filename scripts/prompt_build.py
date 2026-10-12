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
    "visual_center", "information_hierarchy", "gaze_target", "action_physics",
    "material_response", "edit_trigger",
)


def compile_director_method(style: dict, shot: dict) -> dict:
    """将上游导演路由展开成可执行决策，禁止只把导演姓名发给模型。"""
    ref = style.get("director_ref", {})
    name = ref.get("name", "")
    intensity = ref.get("intensity", "明确")
    method = {
        "strength": intensity,
        "light_contrast": f"沿用实际光源：{shot['light']}；保留建筑遮挡形成的暗部，不为脸补装饰性轮廓光",
        "color_exposure": "颜色必须附着在真实物体和光源上；皮肤服从环境曝光，不单独美容提亮",
        "lens_camera": f"{shot['camera_witness']}；每镜最多一个主要摄影机动作，运动由人物位移、视线或道具状态改变触发",
        "composition_space": f"视觉中心是{shot['visual_center']}；信息顺序为{shot['information_hierarchy']}；人物调度：{shot['blocking']}",
    }
    if name == "张艺谋":
        # 轻微强度只启用两个兼容特征：物体承载颜色、稳定轴线中的一次偏离。
        method["active_traits"] = [
            "主导色必须来自红袖、旗帜、土墙或火光等真实物体，禁止全局红色滤镜",
            "在稳定空间轴和重复秩序中，只让当前人物动作形成一次明确偏离；禁止为图案而堆群众",
        ]
    else:
        method["active_traits"] = ["导演标签不进入最终提示词；仅保留上述可执行四轴"]
    return method


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

    built = []
    for shot in storyboard.get("shots", []):
        missing = [key for key in REQUIRED_STORY_FIELDS if not shot.get(key)]
        if missing:
            raise ValueError(f"{shot.get('id')} 缺少故事字段: {','.join(missing)}")
        line = line_map.get(shot.get("lyric_line"))
        lyric = line.get("text", "") if line else ""
        lip = bool(shot.get("lip_sync"))
        scene = (f"{shot['space']}；视觉中心：{shot['visual_center']}；"
                 f"信息层级：{shot['information_hierarchy']}；道具与状态：{shot['props']}；"
                 f"实际光源：{shot['light']}；材质受光与磨损：{shot['material_response']}；"
                 f"空间与人物调度：{shot['blocking']}")
        subject = (f"参考图只负责人物身份与服装：参考图中的年轻女子，{style.get('wardrobe', '')}；"
                   "跨镜保持五官比例、发型、耳饰、衣料纹样与层次完全一致，不继承参考图构图、背景或灯光"
                   if protagonist else "风沙中的边关环境与被岁月磨损的器物")
        base_action = (f"{shot['current_action']}；视线目标：{shot['gaze_target']}；"
                       f"动作物理：{shot['action_physics']}")
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
            "style": f"{style.get('style_name', '')}，{keywords}",
            "scene": scene,
            "subject": subject,
            "performance": performance,
            "camera": f"{shot['shot_type']}，{shot['camera_witness']}，{shot.get('camera', '固定镜头')}，真实透视按空间关系自然变化",
            "audio_policy": audio_policy,
            "negative_prompt": negative,
            "direction": {
                "method": compile_director_method(style, shot),
                "edit_trigger": shot["edit_trigger"],
                "anti_ai": {
                    "clarity_budget": "仅一到两个叙事区域完整清楚，其余按距离、遮挡和实际光照自然退让",
                    "motion_rule": "身体、衣料、头发、尘沙与道具分别服从重量、惯性、阻力和接触关系",
                    "reject": "写真摆拍、服装广告、蜡像皮、全局HDR、均匀锐利、无来源雾光、静态图数字推拉、变形转场",
                },
            },
        }
        out = prompts_dir / f"{shot['id']}.json"
        out.write_text(json.dumps(prompt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        built.append(out.name)

    print(json.dumps({"prompts": len(built), "character_fingerprint": character_fp,
                      "files": built}, ensure_ascii=False))


if __name__ == "__main__":
    main()
