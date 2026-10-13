#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 chapter_plan.json 的窗口切出模型中立音频资产并记录可审计摘要。"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    from .audio_master import resolve_master, probe_audio
except ImportError:
    from audio_master import resolve_master, probe_audio


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "ffmpeg 执行失败")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_audio_segments(project: Path, *, sample_rate: int | None = None) -> dict:
    plan_path = project / "state" / "chapter_plan.json"
    timeline_path = project / "state" / "timeline.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    source = resolve_master(project, timeline)
    source_info = probe_audio(source)
    if sample_rate is not None and sample_rate <= 0:
        raise ValueError("sample_rate 必须大于 0")
    rate_args = ["-ar", str(sample_rate)] if sample_rate is not None else []

    target_dir = project / "input" / "chapter_audio"
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "mode": "model_neutral_chapter_audio_assets",
        "source_audio": str(source),
        "source_sample_rate": int(source_info["sample_rate"]),
        "source_channels": int(source_info["channels"]),
        "source_sha256": sha256(source),
        "segments": [],
    }
    for chapter in plan.get("chapters", []):
        start = float(chapter["window"]["start"])
        duration = float(chapter["duration_sec"])
        output = target_dir / f"{chapter['id']}.wav"
        run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{start:.10f}",
            "-t", f"{duration:.10f}", "-i", str(source), "-vn", *rate_args,
            "-c:a", "pcm_s24le", str(output),
        ])
        chapter["audio_asset"] = {
            "contains_lip_sync_shots": any(bool(item.get("lip_sync"))
                                            for item in chapter.get("shot_deltas", [])),
            "local_path": str(output.relative_to(project)).replace("\\", "/"),
            "sha256": sha256(output),
            "source_window": {"start": start, "end": float(chapter["window"]["end"])},
            "binding": "由用户选定后端的适配层决定；核心流程不假设字段名或音频能力",
        }
        manifest["segments"].append({"chapter_id": chapter["id"], **chapter["audio_asset"]})

    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    manifest_path = project / "state" / "chapter_audio_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return {"chapters": len(manifest["segments"]), "output": str(manifest_path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--sample-rate", type=int, default=None,
                        help="仅在用户所选后端要求时重采样；默认保持母带采样率与声道")
    args = parser.parse_args()
    result = build_audio_segments(Path(args.project_dir).resolve(), sample_rate=args.sample_rate)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
