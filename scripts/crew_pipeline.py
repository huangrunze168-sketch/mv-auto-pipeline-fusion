#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""剧组部门契约与视听语言审计。

先保证编剧、导演、摄影、灯光、场景美术、人物美术、演员调度和剪辑能够
互相交接，再允许叠加导演风格。该模块只检查设计数据，不生成媒体。
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from .film_grammar_corpus import audit_binding
    from .pipeline_contracts import SHOT_SIZES, number
except ImportError:
    from film_grammar_corpus import audit_binding
    from pipeline_contracts import SHOT_SIZES, number


DEPARTMENT_FIELDS = {
    "screenwriting": ("dramatic_question", "conflict_progression", "reveal_plan"),
    "directing": ("scene_objective", "performance_arc", "staging_principle",
                  "style_application_order"),
    "cinematography": ("coverage_strategy", "coverage_requirements", "lens_strategy", "axis_policy"),
    "lighting": ("motivated_source_strategy", "contrast_arc", "exposure_priority",
                 "continuity_strategy"),
    "production_design": ("set_story", "depth_layers", "material_palette",
                          "hero_prop_strategy"),
    "character_design": ("silhouette_rule", "wardrobe_arc", "wear_continuity"),
    "blocking": ("geography_rule", "movement_axis", "entrance_exit_logic"),
    "editing": ("rhythm_map", "hook_strategy", "cut_pattern", "pacing_policy",
                "sound_image_strategy"),
}

REQUIRED_HANDOFFS = {
    ("screenwriting", "directing"), ("directing", "blocking"),
    ("production_design", "blocking"), ("character_design", "blocking"),
    ("blocking", "cinematography"), ("lighting", "cinematography"),
    ("production_design", "cinematography"), ("cinematography", "editing"),
    ("directing", "editing"),
}

SHOT_DEPARTMENT_FIELDS = {
    "screenwriting": ("objective", "obstacle", "turn", "audience_gain"),
    "directing": ("performance_beat", "subtext", "staging_intent"),
    "cinematography": (
        "viewpoint_id", "shot_size", "camera_position", "camera_height",
        "camera_side", "angle_deg", "lens_behavior", "camera_movement",
        "movement_motivation", "axis_id", "focal_length_mm", "focus_target",
        "subject_placement", "headroom", "look_room", "depth_strategy", "frame_purpose",
    ),
    "lighting": (
        "source_used", "exposure_target", "face_priority", "shadow_behavior",
        "key_direction", "key_quality", "fill_strategy", "practicals",
        "color_temp_k", "continuity_anchor",
    ),
    "production_design": (
        "foreground_story", "midground_story", "background_story",
        "hero_prop_state", "visual_hook", "set_dressing", "material_response",
        "color_accent", "atmospheric_layer", "continuity_anchor",
    ),
    "character_design": ("silhouette_state", "wardrobe_state", "grooming_state"),
    "blocking": (
        "start_mark", "end_mark", "entry_direction", "exit_direction",
        "gaze_target", "screen_direction", "body_orientation", "action_path",
        "eyeline_vector", "crossing_rule",
    ),
    "editing": (
        "editorial_role", "incoming_relation", "outgoing_relation", "rhythm_class",
        "music_cue", "novelty_axis", "visual_change", "geography_status", "hook",
        "coverage_role", "transition_type", "cut_motivation", "audio_transition",
        "duration_intent",
    ),
}

SCENE_ART_FIELDS = (
    "foreground", "midground", "background", "scenic_action", "hero_prop",
    "negative_space", "material_contrast", "set_history", "color_script",
    "scale_cue", "background_activity",
)
SCENE_LIGHT_FIELDS = (
    "primary_source", "secondary_source", "shadow_zones", "exposure_priority",
    "color_temperature_relation", "cue_changes", "key_direction", "key_quality",
    "fill_strategy", "practicals", "continuity_anchor",
)
SIDES = {"left", "right", "center"}
DIRECTIONS = {"left_to_right", "right_to_left", "toward_camera", "away_camera", "static", "none"}
TRANSITIONS = {"hard_cut", "match_cut", "dissolve", "fade", "wipe", "whip", "black_frame"}
AUDIO_TRANSITIONS = {"straight", "J_cut", "L_cut", "music_hit", "silence_bridge", "sound_bridge"}


def _missing(data: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if data.get(field) in (None, "", [], {})]


def _positive_number(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _max_run(values: list[Any], predicate) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if predicate(value) else 0
        best = max(best, current)
    return best


def _shot_duration(shot: dict[str, Any]) -> float:
    window = shot.get("window") or {}
    return float(window.get("end", 0)) - float(window.get("start", 0))


def validate_crew_pipeline(development: dict[str, Any], storyboard: dict[str, Any]) -> list[str]:
    """返回结构与视听语言错误；空列表表示可以进入导演风格编译。"""

    errors: list[str] = []
    bible = development.get("crew_bible") or {}
    if bible.get("schema_version") != 2:
        errors.append("crew_bible.schema_version 必须为 2")
    for department, fields in DEPARTMENT_FIELDS.items():
        data = bible.get(department) or {}
        missing = _missing(data, fields)
        if missing:
            errors.append(f"剧组部门 {department} 缺少交接物: {','.join(missing)}")
    if (bible.get("directing") or {}).get("style_application_order") != "after_film_grammar":
        errors.append("导演风格只能在基础视听语言通过后应用: style_application_order=after_film_grammar")
    handoffs = bible.get("handoffs") or []
    actual_handoffs: set[tuple[str, str]] = set()
    for handoff in handoffs:
        source, target = handoff.get("from"), handoff.get("to")
        if source and target:
            actual_handoffs.add((str(source), str(target)))
        if not handoff.get("deliverable") or not handoff.get("acceptance"):
            errors.append(f"部门交接 {source}->{target} 缺少 deliverable/acceptance")
    missing_handoffs = REQUIRED_HANDOFFS - actual_handoffs
    if missing_handoffs:
        errors.append("缺少部门交接: " + ",".join(
            f"{source}->{target}" for source, target in sorted(missing_handoffs)
        ))

    for scene in development.get("scenes", []):
        scene_id = scene.get("id", "unknown")
        missing_art = _missing(scene.get("art_direction") or {}, SCENE_ART_FIELDS)
        missing_light = _missing(scene.get("lighting_plan") or {}, SCENE_LIGHT_FIELDS)
        if missing_art:
            errors.append(f"场景 {scene_id} 美术设计缺少: {','.join(missing_art)}")
        if missing_light:
            errors.append(f"场景 {scene_id} 灯光设计缺少: {','.join(missing_light)}")
        if scene.get("kind") not in {"narrative", "performance", "montage", "oner"}:
            errors.append(f"场景 {scene_id} 必须声明kind")
        requirements = scene.get("coverage_requirements")
        roles = {(s.get("crew", {}).get("editing") or {}).get("coverage_role")
                 for s in storyboard.get("shots", []) if s.get("scene_id") == scene_id}
        if not isinstance(requirements, list) or not requirements or not set(requirements) <= roles:
            errors.append(f"场景 {scene_id} coverage_requirements未被正式镜头兑现")
        axes = scene.get("axes") or {}
        if not isinstance(axes, dict) or not axes:
            errors.append(f"场景 {scene_id} 缺少轴线注册表axes")
            continue
        seen_geometry = set()
        for aid, axis in axes.items():
            try:
                a, b = axis["start"], axis["end"]
                geometry = tuple(sorted((tuple(map(number, a)), tuple(map(number, b)))))
                if len(a) != 2 or len(b) != 2 or a == b or geometry in seen_geometry:
                    raise ValueError
                seen_geometry.add(geometry)
            except (ValueError, KeyError, TypeError):
                errors.append(f"场景 {scene_id} 轴线{aid}无效或同几何重复命名")

    shots = storyboard.get("shots") or []
    for shot in shots:
        sid = shot.get("id", "unknown")
        crew = shot.get("crew") or {}
        for department, fields in SHOT_DEPARTMENT_FIELDS.items():
            missing = _missing(crew.get(department) or {}, fields)
            if missing:
                errors.append(f"{sid} / {department} 缺少: {','.join(missing)}")
        camera = crew.get("cinematography") or {}
        try:
            from .pipeline_contracts import CAMERA_MOVEMENTS
        except ImportError:
            from pipeline_contracts import CAMERA_MOVEMENTS
        motion_camera = (shot.get('motion_design') or {}).get('camera_motion')
        if motion_camera and CAMERA_MOVEMENTS.get(motion_camera, motion_camera) != CAMERA_MOVEMENTS.get(
                camera.get('camera_movement'), camera.get('camera_movement')):
            errors.append(f"{sid} 运镜事实源冲突: motion_design/crew.camera_movement")
        if SHOT_SIZES.get(shot.get("shot_type"), shot.get("shot_type")) != SHOT_SIZES.get(
                camera.get("shot_size"), camera.get("shot_size")):
            errors.append(f"{sid} 景别事实源冲突: shot_type/crew.shot_size")
        scene = next((s for s in development.get("scenes", []) if s.get("id") == shot.get("scene_id")), {})
        try:
            axis = scene["axes"][camera["axis_id"]]
            x, y = map(number, camera["position_xy"])
            ax, ay = map(number, axis["start"])
            bx, by = map(number, axis["end"])
            cross = (bx-ax)*(y-ay)-(by-ay)*(x-ax)
            side = "center" if abs(cross) < 1e-6 else "left" if cross > 0 else "right"
            if side != camera.get("camera_side"):
                errors.append(f"{sid} 摄影机几何轴侧与camera_side不一致")
        except (KeyError, TypeError, ValueError):
            errors.append(f"{sid} 轴线ID未注册或position_xy无效")
        if camera.get("camera_side") not in SIDES:
            errors.append(f"{sid} camera_side 必须是 left/right/center")
        try:
            angle = float(camera.get("angle_deg"))
            if not math.isfinite(angle) or not -180 <= angle <= 180:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{sid} angle_deg 必须是 -180..180 的实数")
        for field in ("headroom", "look_room"):
            try:
                value = float(camera.get(field))
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"{sid} {field} 必须是 0..1 的画幅比例")
        focal_length = _positive_number(camera.get("focal_length_mm"))
        if focal_length is None:
            errors.append(f"{sid} focal_length_mm 必须为正数")
        lighting = crew.get("lighting") or {}
        try:
            color_temp = float(lighting.get("color_temp_k"))
            if not math.isfinite(color_temp) or not 1000 <= color_temp <= 20000:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{sid} color_temp_k 必须是 1000..20000K")
        blocking = crew.get("blocking") or {}
        for field in ("entry_direction", "exit_direction", "screen_direction"):
            if blocking.get(field) not in DIRECTIONS:
                errors.append(f"{sid} {field} 方向值无效")
        editing = crew.get("editing") or {}
        if type(editing.get("hook")) is not bool:
            errors.append(f"{sid} hook必须为布尔值")
        for field in ("entry_edge", "exit_edge"):
            if blocking.get(field) not in {"left", "right", "top", "bottom", "none"}:
                errors.append(f"{sid} {field}须独立声明画框边缘")
        if editing.get("transition_type") not in TRANSITIONS:
            errors.append(f"{sid} transition_type 不在受控词表")
        if editing.get("audio_transition") not in AUDIO_TRANSITIONS:
            errors.append(f"{sid} audio_transition 不在受控词表")

    errors.extend(validate_sequence_language(shots, bible.get("editing") or {}))
    return errors


def validate_sequence_language(shots: list[dict[str, Any]], editing_bible: dict[str, Any]) -> list[str]:
    """检查轴线、动线、重复机位、30 度规则、空间建立与节奏。"""

    errors: list[str] = []
    if not shots:
        return ["剧组审计没有镜头"]

    policy = editing_bible.get("pacing_policy") or {}
    required_policy = (
        "max_average_shot_sec", "slow_shot_threshold_sec", "max_consecutive_slow_shots",
        "max_consecutive_same_rhythm", "hook_deadline_sec", "max_hook_gap_sec",
        "max_visual_stasis_sec", "min_shot_size_variety_per_scene",
    )
    missing_policy = _missing(policy, required_policy)
    if missing_policy:
        errors.append("剪辑节奏策略缺少: " + ",".join(missing_policy))
    numeric = {key: _positive_number(policy.get(key)) for key in required_policy}
    for key in ("max_consecutive_slow_shots", "max_consecutive_same_rhythm", "min_shot_size_variety_per_scene"):
        if type(policy.get(key)) is not int:
            numeric[key] = None
            errors.append(f"{key}必须为正整数，拒绝布尔值与小数")
    invalid = [key for key, value in numeric.items() if value is None]
    if invalid and not missing_policy:
        errors.append("剪辑节奏策略必须是正数: " + ",".join(invalid))

    durations = [_shot_duration(shot) for shot in shots]
    if any(not math.isfinite(value) or value <= 0 for value in durations):
        errors.append("所有剪辑镜头必须有正向有限时长")
        return errors
    if not invalid:
        average = sum(durations) / len(durations)
        if average > numeric["max_average_shot_sec"] + 1e-6:
            errors.append(
                f"平均镜头时长 {average:.2f}s 超过节奏策略 {numeric['max_average_shot_sec']:.2f}s"
            )
        slow_run = _max_run(
            durations, lambda value: value > numeric["slow_shot_threshold_sec"] + 1e-6
        )
        if slow_run > int(numeric["max_consecutive_slow_shots"]):
            errors.append(f"连续慢镜头达到 {slow_run} 个，节奏拖沓")

        rhythm = [(shot.get("crew") or {}).get("editing", {}).get("rhythm_class") for shot in shots]
        for start in range(len(rhythm)):
            run = 1
            while start + run < len(rhythm) and rhythm[start + run] == rhythm[start]:
                run += 1
            if run > int(numeric["max_consecutive_same_rhythm"]):
                errors.append(f"从 {shots[start].get('id')} 起连续 {run} 镜节奏类型相同")
                break

        hook_deadline = numeric["hook_deadline_sec"]
        if not any(
            ((shot.get("crew") or {}).get("editing", {}).get("hook")) is True
            and float((shot.get("window") or {}).get("start", 0)) <= hook_deadline
            for shot in shots
        ):
            errors.append(f"前 {hook_deadline:.2f}s 内缺少明确视觉/叙事钩子")

        hook_times = [
            float((shot.get("window") or {}).get("start", 0)) for shot in shots
            if ((shot.get("crew") or {}).get("editing", {}).get("hook")) is True
        ]
        timeline_end = max(float((shot.get("window") or {}).get("end", 0)) for shot in shots)
        checkpoints = [0.0] + hook_times + [timeline_end]
        if any(right - left > numeric["max_hook_gap_sec"] + 1e-6
               for left, right in zip(checkpoints, checkpoints[1:])):
            errors.append(f"视觉/叙事钩子间隔超过 {numeric['max_hook_gap_sec']:.2f}s")

    scene_established: set[str] = set()
    signatures: list[tuple[Any, ...]] = []
    for index, shot in enumerate(shots):
        sid = shot.get("id", "unknown")
        crew = shot.get("crew") or {}
        camera = crew.get("cinematography") or {}
        blocking = crew.get("blocking") or {}
        editing = crew.get("editing") or {}
        if type(editing.get("hook")) is not bool:
            errors.append(f"{sid} hook必须为布尔值")
        scene_id = shot.get("scene_id")
        geography = editing.get("geography_status")
        if scene_id not in scene_established:
            if geography not in {"establish", "established_from_previous"}:
                errors.append(f"{sid} 在碎切前没有建立场景地理")
            else:
                scene_established.add(scene_id)

        signature = (
            scene_id, camera.get("viewpoint_id"), camera.get("shot_size"),
            camera.get("camera_height"), camera.get("camera_side"), camera.get("lens_behavior"),
        )
        signatures.append(signature)
        if index >= 2 and signatures[index - 2] == signatures[index - 1] == signature:
            errors.append(f"{sid} 与前两镜重复同一机位/景别/高度，禁止连续三个同角度")

        if index == 0:
            continue
        previous = shots[index - 1]
        pcrew = previous.get("crew") or {}
        pcamera = pcrew.get("cinematography") or {}
        pblocking = pcrew.get("blocking") or {}
        relation = editing.get("time_relation", "continuous")
        if relation not in {"continuous", "ellipsis", "flashback", "parallel"}:
            errors.append(f"{sid} time_relation无效")
        same_scene = previous.get("scene_id") == scene_id and relation == "continuous"
        bridge = editing.get("axis_bridge") or {}
        reset = False
        if editing.get("axis_reset") is True:
            bridge_shot = next((s for s in shots[:index+1] if s.get("id") == bridge.get("shot_id")), None)
            try:
                duration = _shot_duration(bridge_shot or {})
                start, end = number(bridge["start_sec"]), number(bridge["end_sec"])
                bridge_crew = (bridge_shot or {}).get("crew", {})
                reset = (bridge_shot is not None and bridge_shot["id"] in {sid, previous["id"]}
                         and 0 <= start < end <= duration and bool(bridge.get("evidence"))
                         and ((bridge.get("type") == "neutral" and bridge_crew.get("cinematography", {}).get("camera_side") == "center")
                              or (bridge.get("type") == "reestablish" and bridge_crew.get("editing", {}).get("geography_status") == "establish")))
            except (ValueError, KeyError, TypeError):
                pass
            if not reset:
                errors.append(f"{sid} axis_reset缺少可核验的相邻桥接镜与时间码")
        if same_scene and pcamera.get("axis_id") != camera.get("axis_id") and not reset:
            errors.append(f"{sid} 更换axis_id须有明确空间重建证据")
        deliberate = editing.get("deliberate_jump_cut") is True and bool(
            editing.get("jump_cut_justification")
        )
        same_scene_axis = (
            same_scene
            and pcamera.get("axis_id") == camera.get("axis_id")
        )
        if same_scene_axis:
            if (pcamera.get("camera_side") in {"left", "right"}
                    and camera.get("camera_side") in {"left", "right"}
                    and pcamera.get("camera_side") != camera.get("camera_side")
                    and not reset):
                errors.append(f"{sid} 未用中性/建立镜重置就跨越 180 度轴线")
            try:
                angle_delta = abs((float(camera.get("angle_deg")) -
                                   float(pcamera.get("angle_deg")) + 180.0) % 360.0 - 180.0)
            except (TypeError, ValueError):
                angle_delta = 999.0
            if (pcamera.get("camera_side") == camera.get("camera_side")
                    and pcamera.get("shot_size") == camera.get("shot_size")
                    and angle_delta < 30.0 and not deliberate):
                errors.append(f"{sid} 与上一镜同景别且机位变化仅 {angle_delta:.1f}°，不满足 30 度变化")

        exit_direction = pblocking.get("exit_direction")
        entry_direction = blocking.get("entry_direction")
        continuous = relation == "continuous" and (same_scene or (bool(blocking.get("continuity_group")) and
                                   blocking.get("continuity_group") == pblocking.get("continuity_group")))
        if (continuous and exit_direction not in {None, "", "none", "static"}
                and entry_direction not in {None, "", "none", "static"}
                and exit_direction != entry_direction
                and not reset):
            errors.append(f"{sid} 入画方向与上一镜出画方向冲突，人物动线跳变")
        if continuous and pblocking.get("exit_edge") in {"left", "right"}:
            expected_edge = "left" if pblocking["exit_edge"] == "right" else "right"
            if blocking.get("entry_edge") not in {"none", expected_edge} and not reset:
                errors.append(f"{sid} 入画边缘未接住上一镜出画边缘")
        if not editing.get("incoming_relation") or not pcrew.get("editing", {}).get("outgoing_relation"):
            errors.append(f"{sid} 与上一镜缺少双向剪辑关系说明")

    visual_changes = [
        (shot.get("crew") or {}).get("editing", {}).get("visual_change") for shot in shots
    ]
    for index in range(2, len(visual_changes)):
        if visual_changes[index - 2] == visual_changes[index - 1] == visual_changes[index]:
            errors.append(f"{shots[index].get('id')} 连续三个镜头没有新的视觉变化")
            break
    if not invalid:
        run_value: Any = object()
        run_duration = 0.0
        max_stasis = 0.0
        for value, duration in zip(visual_changes, durations):
            if value == run_value:
                run_duration += duration
            else:
                run_value, run_duration = value, duration
            max_stasis = max(max_stasis, run_duration)
        if max_stasis > numeric["max_visual_stasis_sec"] + 1e-6:
            errors.append(
                f"相同视觉事件持续 {max_stasis:.2f}s，超过 "
                f"{numeric['max_visual_stasis_sec']:.2f}s"
            )
        minimum_variety = int(numeric["min_shot_size_variety_per_scene"])
        scene_sizes: dict[str, set[Any]] = {}
        scene_roles: dict[str, set[Any]] = {}
        for shot in shots:
            scene_id = str(shot.get("scene_id"))
            crew = shot.get("crew") or {}
            scene_sizes.setdefault(scene_id, set()).add(
                (crew.get("cinematography") or {}).get("shot_size")
            )
            scene_roles.setdefault(scene_id, set()).add(
                (crew.get("editing") or {}).get("coverage_role")
            )
        for scene_id, sizes in scene_sizes.items():
            if len(sizes - {None, ""}) < minimum_variety:
                errors.append(f"场景 {scene_id} 景别覆盖不足 {minimum_variety} 种")
    return errors


def build_report(development: dict[str, Any], storyboard: dict[str, Any],
                 project: Path | None = None) -> dict[str, Any]:
    errors = validate_crew_pipeline(development, storyboard)
    warnings: list[str] = []
    grammar_report = audit_binding(development, storyboard, project) if project else None
    if grammar_report:
        errors.extend(f"电影语法画像: {item}" for item in grammar_report["errors"])
        warnings.extend(grammar_report["warnings"])
    shots = storyboard.get("shots") or []
    durations = [_shot_duration(shot) for shot in shots] if shots else []
    camera_rows = [((shot.get("crew") or {}).get("cinematography") or {}) for shot in shots]
    hook_times = sorted(
        float((shot.get("window") or {}).get("start", 0)) for shot in shots
        if ((shot.get("crew") or {}).get("editing") or {}).get("hook") is True
    )
    timeline_end = max((float((shot.get("window") or {}).get("end", 0)) for shot in shots),
                       default=0.0)
    checkpoints = [0.0] + hook_times + [timeline_end]
    scene_coverage: dict[str, dict[str, list[str]]] = {}
    for shot in shots:
        scene_id = str(shot.get("scene_id"))
        crew = shot.get("crew") or {}
        camera = crew.get("cinematography") or {}
        editing = crew.get("editing") or {}
        row = scene_coverage.setdefault(scene_id, {"shot_sizes": [], "viewpoints": [], "roles": []})
        for key, value in (
            ("shot_sizes", camera.get("shot_size")),
            ("viewpoints", camera.get("viewpoint_id")),
            ("roles", editing.get("coverage_role")),
        ):
            if value not in (None, "") and str(value) not in row[key]:
                row[key].append(str(value))
    return {
        "status": "blocked" if errors else "structural_pass",
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "shot_count": len(shots),
            "average_shot_sec": round(sum(durations) / len(durations), 3) if durations else None,
            "department_count": len(DEPARTMENT_FIELDS),
            "handoff_count": len((development.get("crew_bible") or {}).get("handoffs") or []),
            "distinct_shot_sizes": len({row.get("shot_size") for row in camera_rows} - {None, ""}),
            "distinct_viewpoints": len({row.get("viewpoint_id") for row in camera_rows} - {None, ""}),
            "max_hook_gap_sec": round(max((right - left for left, right in
                                            zip(checkpoints, checkpoints[1:])), default=0.0), 3),
            "scene_coverage": scene_coverage,
        },
        "limits": "结构通过不等于成片好看；仍需动态观看和用户审片",
        "film_grammar_reference": grammar_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查八部门交接、连续性与剪辑节奏")
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    project = args.project_dir.resolve()
    development = json.loads((project / "state/development.json").read_text(encoding="utf-8"))
    storyboard = json.loads((project / "state/storyboard.json").read_text(encoding="utf-8"))
    report = build_report(development, storyboard, project)
    gate = project / "gates/crew_pipeline.json"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
