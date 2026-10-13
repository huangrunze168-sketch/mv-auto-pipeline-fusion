#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ZY Scene Master / Continuity / Shot Deltas 编译为模型中立章节制作包。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    from .visual_development import require as require_development, fingerprint, shot_fingerprint
    from .visual_assets import require_keyframe
    from .gate_checks import check_storyboard, check_prompt
except ImportError:
    from visual_development import require as require_development, fingerprint, shot_fingerprint
    from visual_assets import require_keyframe
    from gate_checks import check_storyboard, check_prompt


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def relative_window(shot: dict, chapter_start: float) -> str:
    start = float(shot["meta"]["window"]["start"]) - chapter_start
    end = float(shot["meta"]["window"]["end"]) - chapter_start
    return f"{start:05.2f}-{end:05.2f}"


def compile_chapter(chapter: dict, prompt_map: dict[str, dict], aspect_ratio: str) -> dict:
    chapter_start = float(chapter["window"]["start"])
    shots = [prompt_map[sid] for sid in chapter["shot_ids"]]
    continuity = chapter.get("continuity_lock", {})
    beats = []
    for shot in shots:
        meta = shot["meta"]
        direction = shot.get("direction", {})
        method = direction.get("method", {})
        missing_axes = [key for key in (
            "light_contrast", "color_exposure", "lens_camera", "composition_space"
        ) if not str(method.get(key, "")).strip()]
        if missing_axes or not str(direction.get("edit_trigger", "")).strip():
            raise ValueError(
                f"{meta.get('shot_id')} 未通过导演编译：missing_axes={missing_axes} "
                f"edit_trigger={bool(direction.get('edit_trigger'))}"
            )
        lip = bool(meta.get("lip_sync"))
        beats.append({
            "time": relative_window(shot, chapter_start),
            "shot_id": meta["shot_id"],
            "story_change": shot["story"]["shot_delta"],
            "current_action": shot["performance"].splitlines()[0],
            "space_and_blocking": shot["scene"],
            "character_and_wardrobe": shot.get("subject", ""),
            "camera_witness": shot["camera"],
            "director_axes": method,
            "motion_physics": direction.get("anti_ai", {}).get("motion_rule", ""),
            "performance_audio_intent": (
                f"需要演唱口型；完整行歌词仅作上下文：{meta.get('lyric_text', '')}；实际口型服从本镜音频窗口，禁止重唱被裁掉的部分" if lip
                else "非演唱镜头；嘴唇自然闭合，不跟随人声开合"
            ),
            "cut_reason": direction["edit_trigger"],
            "motion_design": shot.get("motion_design", {}),
            "visual_rules": shot.get("visual_rules", []),
            "continuity": shot.get("continuity", {}),
        })

    lines = [
        f"模型中立的 {aspect_ratio} 写实叙事音乐 MV 章节制作包。参考图只负责已声明的身份、服装或场景职责；不得继承未授权的构图、背景或灯光。",
        "后端名称、请求模式、参数字段和音频绑定方式均由用户选定后，再由外部适配层按实测契约编译；本提示词不假设任何平台能力。",
        "",
        "【本章叙事弧】",
        f"开始状态：{shots[0]['story']['before']}",
        f"本章变化：{'；'.join(shot['story']['shot_delta'] for shot in shots)}",
        f"结束指向：{shots[-1]['story']['next']}",
        "",
        "【连续性硬锁】",
        f"人物：{continuity.get('character_lock', '')}",
        f"服装：{continuity.get('wardrobe_lock', '')}",
        f"道具：{continuity.get('prop_lock', '')}",
        f"地理与方向轴：{continuity.get('location_topology', '')}",
        f"光源连续性：{continuity.get('lighting_bible', '')}",
        "",
        "【按时间执行的镜头】",
    ]
    for beat in beats:
        lines.extend([
            f"[{beat['time']}] {beat['shot_id']}",
            f"- 变化：{beat['story_change']}",
            f"- 表演：{beat['current_action']}",
            f"- 空间：{beat['space_and_blocking']}",
            f"- 人物与服装锁：{beat['character_and_wardrobe']}",
            f"- 观看：{beat['camera_witness']}",
            "- 导演四轴：" + "；".join(
                str(beat["director_axes"].get(key, "")) for key in
                ("light_contrast", "color_exposure", "lens_camera", "composition_space")
            ),
            "- 已选视觉特征：" + "；".join(
                str(item) for item in beat["director_axes"].get("active_traits", [])
            ),
            f"- 物理：{beat['motion_physics']}",
            f"- 声画意图：{beat['performance_audio_intent']}",
            f"- 切点：{beat['cut_reason']}",
            "- 动作起止与过程：" + json.dumps(beat["motion_design"], ensure_ascii=False),
            "- 连续性变化：" + json.dumps(beat["continuity"], ensure_ascii=False),
            "- 相关参考视觉规律：" + "；".join(beat["visual_rules"]),
        ])
    lines.extend([
        "", "【去 AI 化成片约束】",
        "- 不做写真、海报、游戏 CG 或服装广告；人物动作服务叙事，不持续正面居中展示美貌。",
        "- 皮肤、布、木、纸、石与金属保留真实受光差异；只让一到两个叙事区域清楚。",
        "- 身体、衣料、头发、尘沙与道具分别服从重量、惯性、阻力、遮挡和接触关系。",
        "- 禁止无来源轮廓光、装饰雾、静态图数字推拉、无因果溶解和变形转场。",
    ])
    prompt = "\n".join(lines).strip() + "\n"
    return {
        "chapter_id": chapter["id"],
        "format": "model-neutral",
        "backend": None,
        "beats": beats,
        "prompt": prompt,
        "prompt_sha256": digest(prompt),
    }


def build(project: Path) -> dict:
    plan_path = project / "state" / "chapter_plan.json"
    plan = load(plan_path)
    style = load(project / "state" / "style.json")
    storyboard = load(project / "state" / "storyboard.json")
    if plan.get("source_storyboard_fingerprint") != fingerprint(project / "state" / "storyboard.json"):
        raise ValueError("章节计划依赖旧分镜，请重建章节计划")
    require_development(project, storyboard, style)
    timeline = load(project / "state" / "timeline.json")
    if not all(item["pass"] for item in check_storyboard(storyboard, timeline)):
        raise ValueError("章节编译前必须通过关6")
    gate = load(project / "gates" / "gate5.json")
    if not gate.get("summary", {}).get("pass"):
        raise ValueError("章节编译前必须通过关5")
    recorded = {item["file"]: item["fingerprint"] for item in gate.get("shots", [])}
    for shot in storyboard["shots"]:
        path = project / "prompts" / f"{shot['id']}.json"
        if recorded.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"{shot['id']} 提示词已变动，重新运行关5")
        prompt = load(path)
        checks = check_prompt(prompt, timeline, style, any((project / "input").glob("protagonist.*")), shot)
        if (not all(item["pass"] for item in checks)
                or prompt["meta"].get("development_fingerprint") != fingerprint(project / "state/development.json")
                or prompt["meta"].get("shot_design_fingerprint") != shot_fingerprint(shot)):
            raise ValueError(f"{shot['id']} 制作包对应旧设计，重新编译并运行关5")
    registry = load(project / "state" / "visual_assets.json")
    frames = {shot["id"]: require_keyframe(project, shot, registry) for shot in storyboard["shots"]}
    aspect_ratio = str(style.get("aspect_ratio", "")).strip()
    if not aspect_ratio:
        raise ValueError("style.aspect_ratio 不能为空")
    prompt_map = {path.stem: load(path) for path in (project / "prompts").glob("SH*.json")}
    out_dir = project / "prompts" / "chapters"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for chapter in plan.get("chapters", []):
        missing = [sid for sid in chapter.get("shot_ids", []) if sid not in prompt_map]
        if missing:
            raise FileNotFoundError("缺少逐镜提示词: " + ", ".join(missing))
        compiled = compile_chapter(chapter, prompt_map, aspect_ratio)
        compiled["keyframe_references"] = {
            sid: {"path": frames[sid]["path"], "sha256": frames[sid]["sha256"],
                  "roles": ["likeness", "wardrobe", "location", "composition"]}
            for sid in chapter["shot_ids"]}
        json_path = out_dir / f"{chapter['id']}.json"
        text_path = out_dir / f"{chapter['id']}.txt"
        json_path.write_text(json.dumps(compiled, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        text_path.write_text(compiled["prompt"], encoding="utf-8")
        chapter["chapter_prompt"] = {
            "path": str(text_path.relative_to(project)).replace("\\", "/"),
            "sha256": compiled["prompt_sha256"],
            "compiler": "zy_scene_master_to_model_neutral_chapter_v1",
        }
        outputs.append(str(text_path))
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prototype = plan.get("production_policy", {}).get("prototype_chapter")
    manifest = {
        "status": "awaiting_user_backend",
        "submission_ready": False,
        "backend": None,
        "prototype_chapter": prototype,
        "chapter_packages": outputs,
        "required_user_decisions": [
            "backend_name_and_access", "verified_schema", "duration_and_resolution_tiers",
            "audio_capability_and_binding", "concurrency", "cash_limit_cny",
        ],
        "warning": "核心流程不提交生成任务；用户选定后端并核验真实契约后，才由外部适配层编译和提交代表样片",
    }
    manifest_path = project / "state" / "generation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return {"chapters": len(outputs), "outputs": outputs,
            "generation_manifest": str(manifest_path), "submission_ready": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    print(json.dumps(build(Path(args.project_dir).resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()
