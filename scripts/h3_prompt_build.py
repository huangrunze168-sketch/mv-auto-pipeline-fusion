#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ZY Scene Master / Continuity / Shot Deltas 编译为 MiniMax H3 章节导演提示词。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


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


def compile_chapter(chapter: dict, prompt_map: dict[str, dict], style: dict) -> dict:
    chapter_start = float(chapter["window"]["start"])
    shots = [prompt_map[sid] for sid in chapter["shot_ids"]]
    continuity = chapter.get("continuity_lock", {})
    beats = []
    for shot in shots:
        meta = shot["meta"]
        direction = shot.get("direction", {})
        method = direction.get("method", {})
        missing_axes = [key for key in
                        ("light_contrast", "color_exposure", "lens_camera", "composition_space")
                        if not str(method.get(key, "")).strip()]
        if missing_axes or not str(direction.get("edit_trigger", "")).strip():
            raise ValueError(
                f"{meta.get('shot_id')} 未通过导演编译：missing_axes={missing_axes} "
                f"edit_trigger={bool(direction.get('edit_trigger'))}"
            )
        lip = bool(meta.get("lip_sync"))
        mouth = (f"音频驱动歌唱口型；只唱这一行：{meta.get('lyric_text', '')}"
                 if lip else "非演唱镜头；嘴唇自然闭合，不跟随人声开合")
        beats.append({
            "time": relative_window(shot, chapter_start),
            "shot_id": meta["shot_id"],
            "story_change": shot["story"]["shot_delta"],
            "current_action": shot["performance"].splitlines()[0],
            "space_and_blocking": shot["scene"],
            "camera_witness": shot["camera"],
            "director_axes": method,
            "motion_physics": direction.get("anti_ai", {}).get("motion_rule", ""),
            "mouth": mouth,
            "cut_reason": direction["edit_trigger"],
        })

    director = [
        "机位：摄影机必须能在空间平面图中落位；每镜最多一个主要运动，且由人物位移、视线或道具状态变化触发。",
        "调度：动作包含准备、受力、完成与余波；手、脚、视线和道具关系连续，不向镜头展示服装或美貌。",
        "光色：颜色附着于真实物体和实际光源；保留建筑遮挡造成的暗部，皮肤服从环境曝光。",
        "空间：前中后景信息有主次；稳定轴线中的一次人物偏离承担叙事，红袖只作状态证据，不作全局滤镜。",
        "剪辑：只按各镜 edit_trigger 切换；禁止广告蒙太奇、无因果溶解、变形转场和连续推脸。",
    ]
    anti_ai = [
        "画面不是写真、海报、游戏 CG 或服装广告；人物不持续正面居中，不用慢动作甩袖和无意义回眸展示美貌。",
        "皮肤保留细小纹理、局部泛红与受光差异，禁止蜡像皮、磨皮、对称脸和始终明亮的眼神光。",
        "普通木、布、纸、石与金属允许暗、钝、旧和局部不可读；只让一到两个叙事区域清楚，禁止全画面 HDR、统一锐利和纹理堆砌。",
        "风只作用于迎风面，衣袖、头发、尘沙和马具按重量、惯性、阻力与遮挡分别运动；人物脚步必须承重，手指接触道具后才改变道具状态。",
        "禁止无来源轮廓光、装饰性雾、光束、镜头光斑、假景深、漂浮布料、随机手势、背景群众同步动作和静态图数字推拉。",
    ]
    lines = [
        "MiniMax H3 参考生视频；16:9 写实叙事音乐 MV。输入 image_list 只负责人物身份、服装和本章场景依据；输入 audio_list 是唯一演唱与节奏驱动。",
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
        "【导演执行逻辑】",
        *[f"- {rule}" for rule in director],
        "",
        "【按音频时间执行的镜头】",
    ]
    for beat in beats:
        lines.extend([
            f"[{beat['time']}] {beat['shot_id']}",
            f"- 变化：{beat['story_change']}",
            f"- 表演：{beat['current_action']}",
            f"- 空间：{beat['space_and_blocking']}",
            f"- 观看：{beat['camera_witness']}",
            f"- 物理：{beat['motion_physics']}",
            f"- 口型：{beat['mouth']}",
            f"- 切点：{beat['cut_reason']}",
        ])
    lines.extend(["", "【去 AI 化成片约束】", *[f"- {rule}" for rule in anti_ai]])
    prompt = "\n".join(lines).strip() + "\n"
    return {
        "chapter_id": chapter["id"],
        "model": "minimax/minimax-h3",
        "mode": "reference-to-video",
        "director_name_in_prompt": False,
        "timeline_source": "storyboard windows relative to chapter start",
        "beats": beats,
        "prompt": prompt,
        "prompt_sha256": digest(prompt),
    }


def build(project: Path) -> dict:
    plan_path = project / "state" / "chapter_plan.json"
    plan = load(plan_path)
    style = load(project / "state" / "style.json")
    prompt_map = {path.stem: load(path) for path in (project / "prompts").glob("SH*.json")}
    out_dir = project / "prompts" / "h3_chapters"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for chapter in plan.get("chapters", []):
        missing = [sid for sid in chapter.get("shot_ids", []) if sid not in prompt_map]
        if missing:
            raise FileNotFoundError("缺少逐镜提示词: " + ", ".join(missing))
        compiled = compile_chapter(chapter, prompt_map, style)
        json_path = out_dir / f"{chapter['id']}.json"
        text_path = out_dir / f"{chapter['id']}.txt"
        json_path.write_text(json.dumps(compiled, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        text_path.write_text(compiled["prompt"], encoding="utf-8")
        chapter["h3_prompt"] = {
            "path": str(text_path.relative_to(project)).replace("\\", "/"),
            "sha256": compiled["prompt_sha256"],
            "compiler": "zy_scene_master_to_h3_director_v1",
        }
        outputs.append(str(text_path))
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    policy = plan.get("production_policy", {})
    prototype = policy.get("prototype_chapter")
    generation_plan = {
        "status": "prototype_only",
        "model": "minimax/minimax-h3",
        "generation_mode": "reference-to-video",
        "required_inputs": ["image_list", "audio_list"],
        "allowed_now": [prototype] if prototype else [],
        "blocked_until_director_review": [
            chapter["id"] for chapter in plan.get("chapters", [])
            if chapter["id"] != prototype
        ],
        "unlock_condition": "director_review_gate.py check 返回 approved",
        "warning": "只允许先生成代表样片；不得用联系表、首帧或技术 PASS 代替完整动态审片",
    }
    generation_path = project / "state" / "generation_plan.json"
    generation_path.write_text(json.dumps(generation_plan, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    return {"chapters": len(outputs), "outputs": outputs,
            "generation_plan": str(generation_path), "allowed_now": generation_plan["allowed_now"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    print(json.dumps(build(Path(args.project_dir).resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()
