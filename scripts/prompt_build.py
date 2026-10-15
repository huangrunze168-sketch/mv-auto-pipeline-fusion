#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已锁定的 timeline/style/ZY 故事分镜派生六段式视频提示词。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
try:
    from .crew_execution import execution_lines, scene_execution, cut_rehearsal
except ImportError:
    from crew_execution import execution_lines, scene_execution, cut_rehearsal

try:
    from .visual_development import require as require_development, AXES, shot_fingerprint
except ImportError:
    from visual_development import require as require_development, AXES, shot_fingerprint


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


REQUIRED_STORY_FIELDS = (
    "story_beat", "narrative_before", "current_action", "implied_next",
    "space", "blocking", "props", "light", "camera_witness", "shot_delta",
    "visual_center", "information_hierarchy", "gaze_target", "action_physics",
    "material_response", "edit_trigger",
    "story_intent", "obstacle", "keyframe_moment", "audience_information",
    "shooting_station", "frame_boundary", "visual_acceptance",
)


def keyframe_moment(shot: dict) -> str:
    """明确静帧时刻优先于整段视频动作；兼容尚未提供该字段的旧项目。"""
    moment = shot.get("keyframe_moment", shot.get("current_action"))
    if not isinstance(moment, str) or not moment.strip():
        raise ValueError(f"{shot.get('id')} 关键帧当前瞬间不能为空")
    return moment


def compile_director_method(style: dict, shot: dict) -> dict:
    """将上游导演路由展开成可执行决策，禁止只把导演姓名发给模型。"""
    ref = style.get("director_ref", {})
    intensity = ref.get("intensity", "明确")
    routed_axes = shot.get("director_decisions", {})
    active_axes = ref.get("active_axes", [])
    if ref.get("name") and (not active_axes or any(
            not routed_axes.get(axis, {}).get("instruction") for axis in active_axes)):
        raise ValueError("指定导演缺少逐镜路由决策，禁止用通用四轴补齐")
    method = {
        "strength": intensity,
        "light_contrast": shot["light"],
        "color_exposure": "保留当前场景物体颜色与来源光线的曝光关系",
        "lens_camera": shot["camera_witness"],
        "composition_space": f"{shot['visual_center']}；{shot['information_hierarchy']}；{shot['blocking']}",
        "axis_status": {axis: "active" if axis in active_axes else "preserved" for axis in AXES},
        "active_traits": [str(item).strip() for item in ref.get("active_traits", [])
                          if str(item).strip()],
    }
    for axis in active_axes:
        method[axis] = routed_axes[axis]["instruction"]
    if not method["active_traits"]:
        method["active_traits"] = ["不使用导演姓名或片名代替可执行的画面决策"]
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
    try:
        from .pipeline_contracts import atomic_batch
    except ImportError:
        from pipeline_contracts import atomic_batch
    updates = {}
    expected = {}
    def stage(path, text):
        if path not in expected:
            expected[path] = sha256_file(path) if path.is_file() else None
        updates[path] = text
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    a = ap.parse_args()
    project = Path(a.project_dir).resolve()
    for name in ('timeline', 'style', 'storyboard', 'development', 'story_plan', 'visual_edit_plan', 'music_structure'):
        path = project / 'state' / f'{name}.json'
        expected[path] = sha256_file(path) if path.is_file() else None
    director_index = Path(__file__).resolve().parents[1]/'vendor/zy-cinematic-realism/references/directors/index.md'
    expected[director_index] = sha256_file(director_index)
    timeline = load(project / "state" / "timeline.json")
    style = load(project / "state" / "style.json")
    storyboard_path = project / "state" / "storyboard.json"
    storyboard = load(storyboard_path)
    if storyboard.get("story_mode") != "zy_story_visual_development":
        raise ValueError(
            "缺少 ZY Cinematic Realism 故事分镜：请先生成 state/story_plan.json，"
            "再重新运行 storyboard_build.py"
        )
    try:
        from .crew_rehearsal import require_before_prompts
    except ImportError:
        from crew_rehearsal import require_before_prompts
    require_before_prompts(project)
    development = require_development(project, storyboard, style)
    if style.get('director_ref', {}).get('name'):
        try:
            from .visual_development import VENDOR
        except ImportError:
            from visual_development import VENDOR
        expected[(VENDOR/development['director']['source_file']).resolve()] = development['director']['source_sha256']
    if development.get('grammar_reference'):
        binding = development['grammar_reference']
        expected[(project/binding['profile_path']).resolve()] = binding['profile_sha256']
    if style.get("director_ref", {}).get("name"):
        style["director_ref"]["active_axes"] = development["director"]["active_axes"]
        style["director_ref"]["active_traits"] = development["director"].get("active_traits", [])
    if storyboard.get("schema_version") != 2:
        raise ValueError("旧分镜需先按 visual_edit_plan 重新构建；不静默沿用歌词模板")
    for name, key in (("timeline.json", "timeline_fingerprint"),
                      ("visual_edit_plan.json", "visual_edit_fingerprint"),
                      ("story_plan.json", "story_plan_fingerprint")):
        if storyboard.get(key) != sha256_file(project / "state" / name):
            raise ValueError(f"分镜依赖过期: {name}，先重建 storyboard")
    music_path = project / "state" / "music_structure.json"
    if storyboard.get("music_structure_fingerprint") != (sha256_file(music_path) if music_path.is_file() else None):
        raise ValueError("音乐结构依赖过期，先重建 storyboard")
    prompts_dir = project / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for folder in ("scenes", "keyframes", "motion"):
        (prompts_dir / folder).mkdir(exist_ok=True)
    for master in development["scenes"]:
        stage(prompts_dir / "scenes" / f"{master['id']}.json", json.dumps({
            "scene_id": master["id"], "format": "model-neutral", "prompt": scene_execution(master),
            "topology": master["topology"], "light_map": master["light_map"],
            "material_rules": master["material_rules"],
            "art_direction": master.get("art_direction", {}),
            "lighting_plan": master.get("lighting_plan", {}),
            "crew_handoff": "场景美术和灯光先锁定空间、材质与来源光，导演风格只能在此基础上取舍",
        }, ensure_ascii=False, indent=2))

    protagonist = next(iter(sorted((project / "input").glob("protagonist.*"))), None)
    character_fp = sha256_file(protagonist) if protagonist else "none"
    if protagonist: expected[protagonist] = character_fp
    line_map = {line["index"]: line for line in timeline.get("lines", [])}
    keywords = "，".join(style.get("visual_keywords", []))

    built = []
    for shot in storyboard.get("shots", []):
        missing = [key for key in REQUIRED_STORY_FIELDS if not shot.get(key)]
        if missing:
            raise ValueError(f"{shot.get('id')} 缺少故事字段: {','.join(missing)}")
        referenced_lines = [line_map[index] for index in shot.get("lyric_lines", [])]
        lyric = "\n".join(line.get("text", "") for line in referenced_lines)
        lip = bool(shot.get("lip_sync"))
        scene = (f"{shot['space']}；视觉中心：{shot['visual_center']}；"
                 f"信息层级：{shot['information_hierarchy']}；道具与状态：{shot['props']}；"
                 f"实际光源：{shot['light']}；材质受光与磨损：{shot['material_response']}；"
                 f"空间与人物调度：{shot['blocking']}")
        subject = ("仅参考图中人物的五官、发型、耳饰与服装；"
                   "跨镜保持同一人物的脸型、眼形与眼距、眉形、鼻形、唇形及五官比例，"
                   "保持同一套服装的颜色、版型、领口、袖型、面料、纹样、刺绣、层次与配饰；"
                   "仅在用户明确要求换装时更新服装锁；"
                   "场景、构图、光线及动作服从本镜 Scene Master，"
                   "表情、姿态、衣料运动与受光自然变化，不继承参考图姿势、构图、背景或灯光"
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
        if lip:
            audio_policy += "；歌词是完整行文本上下文，实际发声与口型只服从本镜窗口裁切的人声音频，不重唱被切掉的前后部分"
        window = shot["window"]
        prompt = {
            "meta": {
                "shot_id": shot["id"],
                "window": window,
                "duration_sec": round(float(window["end"]) - float(window["start"]), 10),
                "shot_type": shot["shot_type"],
                "lip_sync": lip,
                "generation_role": shot["generation_role"],
                "lyric_line": shot.get("lyric_line"),
                "lyric_lines": shot.get("lyric_lines", []),
                "lyric_windows": [{"index": line["index"], "text": line["text"],
                                   "start": max(float(line["start"]), float(shot["window"]["start"])),
                                   "end": min(float(line["end"]), float(shot["window"]["end"]))}
                                  for line in referenced_lines],
                "scene_id": shot["scene_id"],
                "shot_design_fingerprint": shot_fingerprint(shot),
                "timing_refs": shot["timing_refs"],
                "lyric_text": lyric,
                "style_fingerprint": style.get("fingerprint"),
                "character_fingerprint": character_fp,
                "reference_duties": ["likeness", "wardrobe"] if protagonist else ["none"],
                "story_plan_fingerprint": storyboard.get("story_plan_fingerprint"),
                "development_fingerprint": sha256_file(project / "state" / "development.json"),
            },
            "story": {
                "beat": shot["story_beat"],
                "before": shot["narrative_before"],
                "next": shot["implied_next"],
                "shot_delta": shot["shot_delta"],
            },
            "visual_rules": [rule["instruction"] for rule in development.get("visual_rules", [])
                             if rule["id"] in shot.get("active_rule_ids", [])],
            "continuity": {"before": shot["state_before"], "after": shot["state_after"]},
            "motion_design": shot["motion_design"],
            "style": f"{style.get('style_name', '')}，{keywords}",
            "scene": scene,
            "subject": subject,
            "performance": performance,
            "camera": f"{shot['shot_type']}；摄影执行：" + json.dumps(shot['crew']['cinematography'], ensure_ascii=False),
            "audio_policy": audio_policy,
            "negative_prompt": negative,
            "direction": {
                "sequence_direction": shot.get('sequence_direction'),
                "method": compile_director_method(style, shot),
                "crew_execution": execution_lines(shot.get('crew', {})),
                "crew": shot.get("crew", {}),
                "edit_trigger": shot["edit_trigger"],
                "scene_master": {
                    "current_action": shot["current_action"],
                    "keyframe_moment": keyframe_moment(shot),
                    "story_intent": shot["story_intent"],
                    "obstacle": shot["obstacle"],
                    "audience_information": shot["audience_information"],
                    "shooting_station": shot["shooting_station"],
                    "frame_boundary": shot["frame_boundary"],
                    "visual_acceptance": shot["visual_acceptance"],
                },
                "anti_ai": {
                    "clarity_budget": "仅一到两个叙事区域完整清楚，其余按距离、遮挡和实际光照自然退让",
                    "motion_rule": "身体、衣料、头发、尘沙与道具分别服从重量、惯性、阻力和接触关系",
                    "reject": "写真摆拍、服装广告、蜡像皮、全局HDR、均匀锐利、无来源雾光、静态图数字推拉、变形转场",
                },
            },
        }
        out = prompts_dir / f"{shot['id']}.json"
        stage(out, json.dumps(prompt, ensure_ascii=False, indent=2) + "\n")
        source_hash = "sha256:" + hashlib.sha256(updates[out].encode("utf-8")).hexdigest()
        stage(prompts_dir / "keyframes" / out.name, json.dumps({
            "shot_id": shot["id"], "scene_id": shot["scene_id"], "format": "model-neutral",
            "scene": scene, "subject": subject, "current_moment": keyframe_moment(shot),
            "continuity": {"before": shot["state_before"], "after": shot["state_after"]},
            "prop_state": shot["props"],
            "reference_exclusions": shot.get("reference_exclusions", []),
            "camera": prompt["camera"], "visual_rules": prompt["visual_rules"],
            "direction": prompt["direction"], "aspect_ratio": style.get("aspect_ratio"),
            "crew": shot.get("crew", {}),
            "shooting_station": shot["shooting_station"],
            "frame_boundary": shot["frame_boundary"],
            "visual_acceptance": shot["visual_acceptance"],
            "source_prompt_sha256": source_hash,
        }, ensure_ascii=False, indent=2))
        stage(prompts_dir / "motion" / out.name, json.dumps({
            "shot_id": shot["id"], "format": "model-neutral", "subject_lock": subject,
            "motion_design": shot["motion_design"], "audio_policy": audio_policy,
            "window": window, "cut_reason": shot["cut_reason"],
            "crew": shot.get("crew", {}),
            "crew_execution": execution_lines(shot.get('crew', {})),
            "director_method": prompt['direction']['method'],
            "sequence_direction": shot.get('sequence_direction'),
            "scene_master": prompt['direction']['scene_master'],
            "continuity": prompt['continuity'],
            "visual_rules": prompt['visual_rules'],
            "source_prompt_sha256": source_hash,
        }, ensure_ascii=False, indent=2))
        built.append(out.name)

    stage(prompts_dir / 'cut_rehearsal.json', json.dumps({
        'schema_version': 1, 'scope': 'design_rehearsal_not_approval',
        'storyboard_sha256': sha256_file(storyboard_path),
        'cuts': cut_rehearsal(storyboard['shots']),
        'dynamic_review_required': True}, ensure_ascii=False, indent=2)+'\n')
    atomic_batch(updates, expected=expected)
    print(json.dumps({"prompts": len(built), "character_fingerprint": character_fp,
                      "files": built}, ensure_ascii=False))


if __name__ == "__main__":
    main()
