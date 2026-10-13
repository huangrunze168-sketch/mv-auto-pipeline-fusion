"""按视觉镜头选取生成素材；素材时长与最终剪辑时长分离。"""
import argparse
import json
import math
import subprocess
from pathlib import Path

try:
    from .visual_development import fingerprint, load
except ImportError:
    from visual_development import fingerprint, load


def compile_selection(storyboard: dict, clips: dict, selections: list) -> list:
    fps = float(storyboard["fps"])
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps 无效")
    if not storyboard.get("shots"):
        raise ValueError("视觉分镜不能为空")
    by_shot = {item["shot_id"]: item for item in selections}
    if len(by_shot) != len(selections) or set(by_shot) != {s["id"] for s in storyboard["shots"]}:
        raise ValueError("选段必须唯一且完整覆盖视觉分镜")
    result, assigned_frames = [], 0
    total_frames = int(math.floor(storyboard["shots"][-1]["window"]["end"] * fps))
    for index, shot in enumerate(storyboard["shots"]):
        selection = by_shot[shot["id"]]
        clip = clips.get(selection.get("clip_id"), {})
        start, end = selection["in_frame"], selection["out_frame"]
        if type(start) is not int or type(end) is not int:
            raise ValueError("素材选段必须使用整数帧，不得静默截断")
        expected_frames = round((shot["window"]["end"] - shot["window"]["start"]) * fps)
        if index == len(storyboard["shots"]) - 1:
            expected_frames = total_frames - assigned_frames
        if (not clip or clip.get("status") != "reviewed" or not clip.get("evidence")
                or not selection.get("edit_reason") or not selection.get("state_check")):
            raise ValueError(f"{shot['id']} 缺少已审素材、剪辑理由或状态衔接检查")
        if (start < 0 or end <= start or end > int(clip.get("frame_count", 0))
                or end - start != expected_frames or float(clip.get("fps", 0)) != fps):
            raise ValueError(f"{shot['id']} 选段帧数/帧率不符合音乐窗口，不自动变速")
        if clip.get("scene_id") != shot["scene_id"]:
            raise ValueError(f"{shot['id']} 素材场景与分镜不一致")
        result.append({**selection, "source_path": clip["path"], "source_sha256": clip["sha256"],
                       "target_path": f"clips/edit/{shot['id']}_fitted.mp4",
                       "window": shot["window"], "fps": fps, "frames": expected_frames})
        assigned_frames += expected_frames
    return result


def build(project: Path, render: bool = False) -> dict:
    storyboard = load(project / "state" / "storyboard.json")
    clips = load(project / "state" / "generated_clips.json")["clips"]
    selections = load(project / "state" / "edit_selection.json")["selections"]
    entries = compile_selection(storyboard, clips, selections)
    for entry in entries:
        source = project / entry["source_path"]
        if not source.is_file() or fingerprint(source) != entry["source_sha256"]:
            raise ValueError(f"素材不存在或已改变: {source}")
        if render:
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                "-show_entries", "stream=avg_frame_rate,nb_read_frames", "-of", "json", str(source),
            ], capture_output=True, text=True, check=True)
            stream = json.loads(probe.stdout)["streams"][0]
            n, d = map(int, stream["avg_frame_rate"].split("/"))
            if abs(n / d - entry["fps"]) > 1e-6 or int(stream["nb_read_frames"]) < entry["out_frame"]:
                raise ValueError("素材帧率/长度与选段记录不一致")
            target = project / entry["target_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-i", str(source),
                "-vf", f"trim=start_frame={entry['in_frame']}:end_frame={entry['out_frame']},setpts=PTS-STARTPTS",
                "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(target),
            ], check=True, capture_output=True)
            entry["output_sha256"] = fingerprint(target)
    result = {"status": "rendered" if render else "planned", "entries": entries,
              "storyboard_sha256": fingerprint(project / "state" / "storyboard.json"),
              "selection_sha256": fingerprint(project / "state" / "edit_selection.json")}
    (project / "state" / "edit_assembly.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--render", action="store_true", help="仅本地剪辑已存在素材，不调用生成后端")
    args = parser.parse_args()
    print(json.dumps(build(Path(args.project_dir).resolve(), args.render), ensure_ascii=False))
