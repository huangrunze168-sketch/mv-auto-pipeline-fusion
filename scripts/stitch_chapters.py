#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼接音频驱动的 CH*_fitted.mp4，规范到 16:9，并贴回同源无损时间基准。"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "ffmpeg 执行失败")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return float(result.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--output-name", default="final_minimax_h3_mv.mp4")
    args = ap.parse_args()
    project = Path(args.project_dir).resolve()
    plan = json.loads((project / "state" / "chapter_plan.json").read_text(encoding="utf-8"))
    missing_audio_drive = [chapter.get("id", "?") for chapter in plan.get("chapters", [])
                           if chapter.get("audio_drive", {}).get("h3_param") != "audio_list"]
    if missing_audio_drive:
        raise ValueError("章节未经过 audio_list 音频驱动准备: " + ", ".join(missing_audio_drive))
    clips = [project / "clips" / f"{chapter['id']}_fitted.mp4"
             for chapter in plan.get("chapters", [])]
    missing = [str(path) for path in clips if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少章节视频: " + ", ".join(missing))

    timeline = json.loads((project / "state" / "timeline.json").read_text(encoding="utf-8"))
    duration = float(timeline["duration_sec"])
    audio = project / timeline["source_audio"]
    if not audio.is_file():
        raise FileNotFoundError(f"母带不存在: {audio}")
    output = project / "output" / args.output_name
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=project / "output") as tmp:
        tmp_path = Path(tmp)
        concat_file = tmp_path / "chapters.txt"
        concat_file.write_text("\n".join(
            "file '" + str(path).replace("'", "'\\''") + "'" for path in clips
        ) + "\n", encoding="utf-8")
        joined = tmp_path / "joined.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(concat_file), "-an", "-c:v", "copy", str(joined)])
        # MiniMax H3 的 768P 实测为 1344×768（并非严格 16:9），统一中心裁切到交付画布。
        run(["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-i", str(audio),
             "-filter:v", (f"scale={args.width}:{args.height}:force_original_aspect_ratio=increase,"
                           f"crop={args.width}:{args.height}"),
             "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.6f}",
             "-r", "24", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])

    actual = probe_duration(output)
    print(json.dumps({"output": str(output), "chapters": len(clips),
                      "target_duration": duration, "actual_duration": round(actual, 6),
                      "canvas": f"{args.width}x{args.height}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
