import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.storyboard_build import build, build_visual_shots, REQUIRED_STORY_FIELDS
from scripts.visual_development import validate, fingerprint, VENDOR
from scripts.visual_assets import register, require_keyframe
from scripts.prompt_build import compile_director_method
from scripts.chapter_prompt_build import build as build_chapters
from scripts.edit_assemble import compile_selection
from scripts.edit_assemble import build as render_edit
from scripts.visual_revision import check_remix, check_repair
from scripts.director_review_gate import initial_review, validate_review

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fixture(project):
    timeline = {"duration_sec": 4.0, "source_audio": "input/song.wav", "lines": [
        {"index": 1, "type": "vocal", "text": "第一句", "start": 0.0, "end": 3.0},
        {"index": 2, "type": "vocal", "text": "第二句", "start": 3.0, "end": 4.0},
    ]}
    music = {"cues": [{"id": "accent", "time_sec": 2.0,
                       "kind": "accent", "evidence": "测试音乐重音"}]}
    edit = {"shots": [
        {"id": "SH001", "scene_id": "gate", "start_ref": "song:start", "end_ref": "cue:accent",
         "shot_type": "全景", "lip_sync": False, "cut_reason": "重音时人物停下"},
        {"id": "SH002", "scene_id": "gate", "start_ref": "cue:accent", "end_ref": "song:end",
         "shot_type": "近景", "lip_sync": True, "cut_reason": "人物完成决定"},
    ]}
    bible = {key: "保持已确认的事实" for key in
             ("character_lock", "wardrobe_lock", "prop_lock", "location_topology", "lighting_bible")}
    stories = []
    for index in range(2):
        story = {key: "人物握住信纸，随后将信收入袖内" for key in REQUIRED_STORY_FIELDS}
        story.update(id=f"SH00{index + 1}", scene_id="gate", source_beat="B1",
                     state_before={"phase": index}, state_after={"phase": index + 1},
                     motion_design={"start_state": "手持信纸", "action": "收信",
                                    "physics": "接触后收拢", "camera_motion": "固定",
                                    "end_state": "信入袖内"})
        stories.append(story)
    development = {
        "treatment": {"concept": "等待后出关", "form": "叙事与演唱",
                      "emotional_arc": "犹豫到决定", "visual_motif": "门槛",
                      "climax": "跨门槛", "performance_rationale": "决定时演唱", "status": "proposed"},
        "sources": [{"id": "song", "locator": "input/lyrics.txt", "read_scope": "全部两行"}],
        "source_ledger": [{"id": "B1", "kind": "proposal", "source_id": "song",
                           "description": "把等待解释为出关前停顿", "status": "proposed"}],
        "scenes": [{"id": "gate", "source_beat": "B1", "topology": "门内连接道路",
                    "light_map": "门外天光", "material_rules": "布与石分别受光", "master_prompt": "可通行的城门"}],
        "references": [], "visual_rules": [],
    }
    style = {"style_name": "写实", "fingerprint": "sha256:style", "aspect_ratio": "16:9"}
    for name, data in (("timeline", timeline), ("music_structure", music), ("visual_edit_plan", edit),
                       ("development", development), ("style", style),
                       ("story_plan", {"method": "zy_story_visual_development",
                                       "continuity_bible": bible, "shots": stories})):
        write(project / "state" / f"{name}.json", data)
    return timeline, music, edit, development, style


class VisualWorkflowTests(unittest.TestCase):
    def test_narrative_sample_can_mark_lipsync_not_applicable_but_not_other_checks(self):
        plan = {"production_policy": {"prototype_chapter": "CH01"},
                "chapters": [{"id": "CH01", "shot_deltas": [{"lip_sync": False}]}]}
        review = initial_review(plan)
        review["director_checks"]["lip_sync"] = {"status": "not_applicable", "evidence": "本段无演唱，检查自然闭口"}
        errors = validate_review(review, plan)
        self.assertFalse(any("导演维度未通过: lip_sync" == e for e in errors))
        self.assertTrue(any("导演维度未通过: performance" == e for e in errors))
        plan["chapters"][0]["shot_deltas"][0]["lip_sync"] = True
        self.assertTrue(any("导演维度未通过: lip_sync" == e for e in validate_review(review, plan)))
    def test_remix_blocks_identity_and_multiple_axis_changes(self):
        base = {"scene_id": "gate", "character_lock": "same face", "wardrobe_lock": "white",
                "camera_witness": "门内", "light": "天光"}
        candidate = {**base, "camera_witness": "门侧"}
        self.assertEqual(check_remix(base, candidate, "camera"), [])
        candidate["light"] = "烛光"
        self.assertTrue(check_remix(base, candidate, "camera"))
        candidate["character_lock"] = "another face"
        self.assertTrue(any("用户锁" in e for e in check_remix(base, candidate, "camera")))

    def test_repair_requires_actual_drift_and_structural_return(self):
        plan = {"dominant_failures": [{"dimension": "space", "classification": "actual_drift",
                                       "evidence": "门的位置变化", "cause": "空间布局重新设计"}],
                "structural_failure": True, "action": "surgical_repair", "preserve_exactly": ["人物"]}
        self.assertTrue(check_repair(plan))
        plan["action"] = "rebuild_scene_master"
        self.assertEqual(check_repair(plan), [])
        plan["dominant_failures"][0]["classification"] = "valid_adaptation"
        self.assertTrue(check_repair(plan))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要 ffmpeg")
    def test_local_render_cuts_long_material_to_target_frames(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            fixture(project)
            sb = build(project)
            source = project / "source.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            "color=s=64x64:r=24:d=5", "-c:v", "libx264", str(source)],
                           check=True, capture_output=True)
            write(project / "state/generated_clips.json", {"clips": {"C1": {
                "path": "source.mp4", "sha256": fingerprint(source), "fps": 24,
                "frame_count": 120, "scene_id": "gate", "status": "reviewed", "evidence": "测试素材"}}})
            write(project / "state/edit_selection.json", {"selections": [
                {"shot_id": shot["id"], "clip_id": "C1", "in_frame": 12, "out_frame": 60,
                 "edit_reason": "测试两秒动作", "state_check": "连续"} for shot in sb["shots"]]})
            assembly = render_edit(project, render=True)
            self.assertEqual(assembly["status"], "rendered")
            for entry in assembly["entries"]:
                info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                       "-count_frames", "-show_entries", "stream=nb_read_frames",
                                       "-of", "csv=p=0", str(project / entry["target_path"])],
                                      check=True, capture_output=True, text=True)
                self.assertEqual(int(info.stdout.strip()), 48)

    def test_visual_cuts_can_split_and_span_lyrics_without_rewriting_audio(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            timeline, music, edit, _, _ = fixture(project)
            old = copy.deepcopy(timeline)
            shots = build_visual_shots(timeline, music, edit, 24)
            self.assertEqual(shots[0]["lyric_lines"], [1])
            self.assertEqual(shots[1]["lyric_lines"], [1, 2])
            self.assertEqual(timeline, old)
            self.assertEqual(shots[0]["shot_type"], "全景")

    def test_unknown_music_cut_and_collapsed_frame_are_blocked(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            tl, music, edit, _, _ = fixture(Path(tmp))
            edit["shots"][0]["end_ref"] = "cue:invented"
            with self.assertRaises(ValueError):
                build_visual_shots(tl, music, edit, 24)
            edit["shots"][0]["end_ref"] = "cue:accent"
            music["cues"][0]["time_sec"] = 0.001
            with self.assertRaises(ValueError):
                build_visual_shots(tl, music, edit, 24)

    def test_no_edit_plan_produces_skeleton_without_fake_lipsync(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            fixture(project)
            (project / "state" / "visual_edit_plan.json").unlink()
            result = build(project)
            self.assertEqual(result["shots"], [])
            self.assertEqual(result["story_mode"], "timing_only")

    def test_director_name_without_routed_method_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "逐镜路由"):
            compile_director_method({"director_ref": {"name": "张艺谋"}}, {})

    def test_continuity_reset_and_character_style_leak_are_detected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            _, _, _, dev, style = fixture(project)
            sb = build(project)
            self.assertEqual(validate(dev, sb, style), [])
            sb["shots"][1]["state_before"] = {"phase": 0}
            dev["references"] = [{"id": "person", "kind": "character",
                                  "roles": ["likeness", "wardrobe", "lighting"], "observed_scope": "图"}]
            errors = validate(dev, sb, style)
            self.assertTrue(any("静默重置" in e for e in errors))
            self.assertTrue(any("只能控制" in e for e in errors))

    def test_subtle_director_preserves_inactive_axes_and_requires_real_source(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            _, _, _, dev, style = fixture(project)
            sb = build(project)
            style["director_ref"] = {"name": "胡金铨", "intensity": "轻微"}
            dev["director"] = {"name": "胡金铨", "strength": "轻微", "active_axes": ["composition_space"],
                               "active_traits": ["门槛组织空间"], "rationale": "人物决定跨门槛",
                               "source_file": "references/directors/king-hu.md",
                               "source_sha256": fingerprint(VENDOR / "references/directors/king-hu.md")}
            for shot in sb["shots"]:
                shot["director_decisions"] = {"composition_space": {
                    "instruction": "门柱、人物与道路层次可读", "reason": "决定是否出关",
                    "observable_check": "观众能读懂门内外关系"}}
            self.assertEqual(validate(dev, sb, style), [])
            style["director_ref"].update(active_axes=["composition_space"], active_traits=["门槛"])
            method = compile_director_method(style, sb["shots"][0])
            self.assertEqual(method["axis_status"]["light_contrast"], "preserved")
            dev["director"]["source_sha256"] = "old"
            self.assertTrue(any("指纹" in e for e in validate(dev, sb, style)))

    def test_changed_scene_master_invalidates_only_dependent_keyframe(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            fixture(project)
            sb = build(project)
            master, frame = project / "master.png", project / "frame.png"
            master.write_bytes(b"test master asset")
            frame.write_bytes(b"test keyframe asset")
            register(project, "M1", "scene_master", "gate", master, "测试批准记录")
            register(project, "SH001", "keyframe", "gate", frame, "测试批准记录", "M1")
            registry = json.loads((project / "state" / "visual_assets.json").read_text(encoding="utf-8"))
            self.assertEqual(require_keyframe(project, sb["shots"][0], registry)["status"], "approved")
            master.write_bytes(b"changed master asset")
            with self.assertRaisesRegex(ValueError, "复核"):
                require_keyframe(project, sb["shots"][0], registry)

    def test_unrelated_scene_change_does_not_invalidate_other_master(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            _, _, _, dev, _ = fixture(project)
            dev["scenes"].append({**dev["scenes"][0], "id": "road"})
            write(project / "state/development.json", dev)
            sb = build(project)
            asset = project / "asset.png"
            asset.write_bytes(b"test asset")
            register(project, "M1", "scene_master", "gate", asset, "观察记录")
            register(project, "SH001", "keyframe", "gate", asset, "观察记录", "M1")
            dev["scenes"][1]["master_prompt"] = "只修改道路地点"
            write(project / "state/development.json", dev)
            registry = json.loads((project / "state/visual_assets.json").read_text(encoding="utf-8"))
            self.assertEqual(require_keyframe(project, sb["shots"][0], registry)["status"], "approved")

    def test_full_compilation_carries_multiline_lyrics_and_keeps_backend_unselected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            fixture(project)
            sb = build(project)
            def run(script, *args):
                completed = subprocess.run([sys.executable, str(ROOT / "scripts" / script),
                                            str(project), *args], capture_output=True,
                                           encoding="utf-8")
                self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            run("prompt_build.py")
            for gate in ("gate5", "gate6"):
                completed = subprocess.run([sys.executable, str(ROOT / "scripts/gate_checks.py"),
                                            gate, str(project)], capture_output=True, encoding="utf-8")
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            sb = json.loads((project / "state" / "storyboard.json").read_text(encoding="utf-8"))
            p2 = json.loads((project / "prompts/SH002.json").read_text(encoding="utf-8"))
            self.assertEqual(p2["meta"]["lyric_text"], "第一句\n第二句")
            run("chapter_plan_build.py", "--max-duration", "4")
            asset = project / "master.png"
            asset.write_bytes(b"test visual asset")
            register(project, "M1", "scene_master", "gate", asset, "测试观察")
            for shot in sb["shots"]:
                register(project, shot["id"], "keyframe", "gate", asset, "测试观察", "M1")
            result = build_chapters(project)
            self.assertFalse(result["submission_ready"])
            package = json.loads((project / "prompts/chapters/CH01.json").read_text(encoding="utf-8"))
            self.assertEqual(len(package["keyframe_references"]), 2)
            self.assertIn("动作起止与过程", package["prompt"])
            # 修改上游后不能用旧批准资产或旧机检报告继续编译。
            dev = json.loads((project / "state/development.json").read_text(encoding="utf-8"))
            dev["treatment"]["concept"] = "改变故事"
            write(project / "state/development.json", dev)
            with self.assertRaises(ValueError):
                build_chapters(project)

    def test_edit_uses_selected_frames_not_whole_generated_clip(self):
        sb = {"fps": 24, "shots": [{"id": "SH001", "scene_id": "gate",
                                      "window": {"start": 0, "end": 2}}]}
        clips = {"C1": {"status": "reviewed", "evidence": "实际看过", "frame_count": 360,
                         "fps": 24, "scene_id": "gate", "path": "clips/C1.mp4", "sha256": "test"}}
        selected = [{"shot_id": "SH001", "clip_id": "C1", "in_frame": 24, "out_frame": 72,
                     "edit_reason": "只使用完整动作", "state_check": "状态连续"}]
        result = compile_selection(sb, clips, selected)
        self.assertEqual(result[0]["frames"], 48)
        selected[0]["out_frame"] = 360
        with self.assertRaises(ValueError):
            compile_selection(sb, clips, selected)


if __name__ == "__main__":
    unittest.main()
