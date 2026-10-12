#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼接任意用户所选后端产出的 CH*_fitted.mp4，规范到交付画布并重贴母带。"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from .director_review_gate import approved
except ImportError:  # 直接执行脚本时兼容
    from director_review_gate import approved


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


def resolve_canvas(project: Path, width: int | None, height: int | None) -> tuple[int, int]:
    if (width is None) != (height is None):
        raise ValueError("--width 与 --height 必须同时提供")
    if width is not None and height is not None:
        if width <= 0 or height <= 0:
            raise ValueError("交付画布尺寸必须大于 0")
        return width, height
    style = json.loads((project / "state" / "style.json").read_text(encoding="utf-8"))
    raw = str(style.get("resolution", "")).lower().replace("×", "x")
    try:
        parsed_width, parsed_height = (int(value.strip()) for value in raw.split("x", 1))
    except (ValueError, TypeError):
        raise ValueError("style.resolution 必须为 WIDTHxHEIGHT，或显式传入 --width/--height")
    if parsed_width <= 0 or parsed_height <= 0:
        raise ValueError("style.resolution 必须为正整数画布")
    return parsed_width, parsed_height


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--output-name", default="final_mv.mp4")
    ap.add_argument("--allow-unreviewed-preview", action="store_true",
                    help="仅输出技术预览；不会被认定为正式成片")
    args = ap.parse_args()
    project = Path(args.project_dir).resolve()
    width, height = resolve_canvas(project, args.width, args.height)
    review_ok, review_errors = approved(project)
    if not review_ok and not args.allow_unreviewed_preview:
        raise ValueError("导演样片审片未通过，禁止合成为正式成片: " + "; ".join(review_errors))
    if not review_ok and "preview" not in args.output_name.lower():
        raise ValueError("未审片产物的 output-name 必须包含 preview")
    plan = json.loads((project / "state" / "chapter_plan.json").read_text(encoding="utf-8"))
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
        # 各后端可能返回非严格目标比例，统一中心裁切到用户要求的交付画布。
        run(["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-i", str(audio),
             "-filter:v", (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                           f"crop={width}:{height}"),
             "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.6f}",
             "-r", "24", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])

    actual = probe_duration(output)
    print(json.dumps({"output": str(output), "chapters": len(clips),
                      "target_duration": duration, "actual_duration": round(actual, 6),
                      "canvas": f"{width}x{height}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
