import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

from scripts.gate_checks import REF_DUTIES, check_storyboard
from scripts.chapter_plan_build import group_shots
from scripts.chapter_audio_build import build_audio_segments
from scripts.render_preview import resolve_visual_asset


def write_wav(path: Path, duration: float, silence: bool = False) -> None:
    sample_rate = 16000
    samples = []
    for i in range(int(duration * sample_rate)):
        if silence:
            value = 0
        else:
            block = i // 400
            amplitude = 0.15 + 0.70 * random.Random(block).random()
            value = int(26000 * amplitude * math.sin(2 * math.pi * 220 * i / sample_rate))
        samples.append(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(v.to_bytes(2, "little", signed=True) for v in samples))


class PipelineTests(unittest.TestCase):
    def run_script(self, name: str, *args: object) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

    def test_zy_cinematic_vendor_keeps_license_and_mv_boundary(self):
        vendor = ROOT / "vendor" / "zy-cinematic-realism"
        self.assertTrue((vendor / "SKILL.md").is_file())
        self.assertIn("CC BY-NC 4.0", (vendor / "LICENSE").read_text(encoding="utf-8"))
        self.assertIn("popopo-99", (vendor / "NOTICE.md").read_text(encoding="utf-8"))
        integration = (ROOT / "references" / "zy-cinematic-integration.md").read_text(
            encoding="utf-8")
        for protected_field in ("window", "lyric_text", "lip_sync", "audio_policy"):
            self.assertIn(protected_field, integration)

    def test_character_reference_can_lock_wardrobe(self):
        self.assertIn("wardrobe", REF_DUTIES)
        framework = (ROOT / "references" / "prompt-framework.md").read_text(encoding="utf-8")
        self.assertIn("likeness + wardrobe", framework)

    def test_preview_distributes_scene_assets_by_chapter(self):
        scenes = [Path(f"scene_{i}.png") for i in range(4)]
        selected = [resolve_visual_asset(Path("."), {}, i, 8, scenes, None).name
                    for i in range(8)]
        self.assertEqual(selected, ["scene_0.png", "scene_0.png", "scene_1.png",
                                    "scene_1.png", "scene_2.png", "scene_2.png",
                                    "scene_3.png", "scene_3.png"])

    def test_chapter_plan_respects_model_duration(self):
        shots = [
            {"id": "SH001", "window": {"start": 0.0, "end": 6.0}},
            {"id": "SH002", "window": {"start": 6.0, "end": 13.0}},
            {"id": "SH003", "window": {"start": 13.0, "end": 20.0}},
        ]
        groups = group_shots(shots, 15.0)
        self.assertEqual([[s["id"] for s in group] for group in groups],
                         [["SH001", "SH002"], ["SH003"]])

    def test_chapter_plan_prefers_story_breaks(self):
        shots = [
            {"id": "SH001", "window": {"start": 0.0, "end": 4.0}},
            {"id": "SH002", "window": {"start": 4.0, "end": 8.0}},
            {"id": "SH003", "window": {"start": 8.0, "end": 12.0}},
        ]
        groups = group_shots(shots, 15.0, {"SH002"})
        self.assertEqual([[s["id"] for s in group] for group in groups],
                         [["SH001", "SH002"], ["SH003"]])

    def test_chapter_audio_build_records_h3_audio_list_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "input").mkdir()
            (project / "state").mkdir()
            write_wav(project / "input" / "song.wav", 1.0)
            (project / "state" / "timeline.json").write_text(json.dumps({
                "source_audio": "input/song.wav", "duration_sec": 1.0,
            }), encoding="utf-8")
            (project / "state" / "chapter_plan.json").write_text(json.dumps({
                "chapters": [{
                    "id": "CH01", "window": {"start": 0.0, "end": 1.0},
                    "duration_sec": 1.0, "shot_deltas": [{"lip_sync": True}],
                }],
            }), encoding="utf-8")
            build_audio_segments(project, sample_rate=16000)
            updated = json.loads((project / "state" / "chapter_plan.json")
                                 .read_text(encoding="utf-8"))
            drive = updated["chapters"][0]["audio_drive"]
            self.assertEqual("reference-to-video", drive["h3_mode"])
            self.assertEqual("audio_list", drive["h3_param"])
            self.assertTrue(drive["required"])
            self.assertTrue((project / drive["local_path"]).is_file())

    def test_fallback_keeps_many_lyrics_inside_short_silent_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            wav_path = project / "input" / "short.wav"
            lyrics_path = project / "input" / "lyrics.txt"
            timeline_path = project / "state" / "timeline.json"
            write_wav(wav_path, 1.0, silence=True)
            lyrics_path.write_text("\n".join(f"第{i}行" for i in range(10)), encoding="utf-8")

            result = self.run_script("timeline_fallback.py", wav_path, lyrics_path, timeline_path)
            self.assertEqual(result.returncode, 0, result.stderr)
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            self.assertEqual(timeline["source_audio"], "input/short.wav")
            self.assertTrue(timeline.get("no_interlude"))
            self.assertTrue(all(0 <= row["start"] < row["end"] <= 1.0
                                for row in timeline["lines"]))

            storyboard = self.run_script("storyboard_build.py", project, "--fps", 24)
            self.assertEqual(storyboard.returncode, 0, storyboard.stderr)

    def test_gate6_rejects_contiguous_windows_shifted_off_song(self):
        timeline = {"duration_sec": 10.0, "lines": [
            {"index": 1, "type": "vocal", "start": 0.0, "end": 5.0},
            {"index": 2, "type": "vocal", "start": 5.0, "end": 10.0},
        ]}
        storyboard = {"shots": [
            {"id": "SH001", "window": {"start": 1.0, "end": 6.0},
             "lip_sync": True, "shot_type": "特写"},
            {"id": "SH002", "window": {"start": 6.0, "end": 11.0},
             "lip_sync": False, "shot_type": "空镜"},
        ]}
        checks = check_storyboard(storyboard, timeline)
        endpoint_check = next(c for c in checks if c["item"].startswith("窗口首尾相接"))
        self.assertFalse(endpoint_check["pass"])

    @unittest.skipUnless(shutil.which("ffprobe"), "需要 ffprobe")
    def test_gate1_compares_declared_duration_with_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "state").mkdir()
            wav_path = project / "input" / "song.wav"
            write_wav(wav_path, 1.0)
            (project / "input" / "lyrics.txt").write_text("甲", encoding="utf-8")
            timeline = {
                "duration_sec": 2.0, "source_audio": "input/song.wav",
                "lyrics_source": "official", "asr_engine": "test", "no_interlude": True,
                "pending_review": [], "lines": [
                    {"index": 1, "type": "vocal", "text": "甲", "start": 0.0,
                     "end": 1.0, "confidence": 1.0},
                ],
            }
            (project / "state" / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            result = self.run_script("gate_checks.py", "gate1", project)
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            duration_check = next(c for c in report["checks"] if c["item"].startswith("全曲时长"))
            self.assertFalse(duration_check["pass"])

    def test_gate5_rejects_missing_prompt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "state").mkdir()
            (project / "input").mkdir()
            (project / "prompts").mkdir()
            timeline = {"duration_sec": 2.0, "lines": [
                {"index": 1, "type": "vocal", "text": "甲", "start": 0.0, "end": 1.0},
                {"index": 2, "type": "vocal", "text": "乙", "start": 1.0, "end": 2.0},
            ]}
            shots = [
                {"id": "SH001", "window": {"start": 0.0, "end": 1.0},
                 "shot_type": "特写", "lip_sync": True},
                {"id": "SH002", "window": {"start": 1.0, "end": 2.0},
                 "shot_type": "空镜", "lip_sync": False},
            ]
            (project / "state" / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            (project / "state" / "style.json").write_text(
                json.dumps({"fingerprint": "sha256:style"}), encoding="utf-8")
            (project / "state" / "storyboard.json").write_text(
                json.dumps({"shots": shots}), encoding="utf-8")
            prompt = {
                "meta": {"shot_id": "SH001", "window": shots[0]["window"],
                         "duration_sec": 1.0, "shot_type": "特写", "lip_sync": True,
                         "lyric_line": 1, "lyric_text": "甲",
                         "style_fingerprint": "sha256:style", "reference_duties": ["none"]},
                "style": "风格", "scene": "场景", "subject": "人物",
                "performance": "人物抬头凝望\n甲", "camera": "缓慢推近",
                "audio_policy": "人声驱动口型", "negative_prompt": "水印",
            }
            (project / "prompts" / "SH001.json").write_text(json.dumps(prompt), encoding="utf-8")

            result = self.run_script("gate_checks.py", "gate5", project)
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertFalse(report["checks"][0]["pass"])

    def test_prompt_build_rejects_timing_only_storyboard(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            project = Path(tmp)
            (project / "state").mkdir()
            (project / "input").mkdir()
            (project / "state" / "timeline.json").write_text(
                json.dumps({"duration_sec": 1.0, "lines": []}), encoding="utf-8")
            (project / "state" / "style.json").write_text(
                json.dumps({"fingerprint": "sha256:style"}), encoding="utf-8")
            (project / "state" / "storyboard.json").write_text(
                json.dumps({"story_mode": "timing_only", "shots": []}), encoding="utf-8")

            result = self.run_script("prompt_build.py", project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ZY Cinematic Realism", result.stderr)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要 ffmpeg")
    def test_duration_fit_copy_path_removes_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mp4"
            output = Path(tmp) / "nested" / "fitted.mp4"
            make = subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=64x64:r=24:d=1", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=16000:duration=1", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], capture_output=True, text=True)
            self.assertEqual(make.returncode, 0, make.stderr)

            result = self.run_script("duration_fit.py", source, output, 1.0, "--fps", 24)
            self.assertEqual(result.returncode, 0, result.stderr)
            info = json.loads(result.stdout)
            self.assertEqual(info["mode"], "copy")
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(probe.stdout.strip(), "")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要 ffmpeg")
    def test_preview_supports_wav_and_no_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "state").mkdir()
            wav_path = project / "input" / "master.wav"
            write_wav(wav_path, 1.0)
            timeline = {"duration_sec": 1.0, "source_audio": "input/master.wav", "lines": [
                {"index": 1, "type": "vocal", "text": "甲", "start": 0.0, "end": 0.5},
                {"index": 2, "type": "vocal", "text": "乙", "start": 0.5, "end": 1.0},
            ]}
            storyboard = {"shots": [
                {"id": "SH001", "window": {"start": 0.0, "end": 0.5},
                 "shot_type": "特写", "lip_sync": True},
                {"id": "SH002", "window": {"start": 0.5, "end": 1.0},
                 "shot_type": "空镜", "lip_sync": False},
            ]}
            (project / "state" / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            (project / "state" / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")

            result = self.run_script("render_preview.py", project, "--width", 64, "--height", 64)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout.splitlines()[-1])
            self.assertTrue(Path(output["final"]).is_file())
            self.assertEqual(output["verification"], "PASS")
            report_path = Path(output["verification_report"])
            self.assertTrue(report_path.is_file())
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["mode"], "candidate")


if __name__ == "__main__":
    unittest.main()
