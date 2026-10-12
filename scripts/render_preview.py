#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_preview.py — 静帧预览成片（无视频生成 API 时的全链产出）

每镜：主人公图 Ken Burns 运镜（zoompan 按窗口帧数渲染，画面轨无音轨）
  → duration_fit 贴合窗口长 → concat 拼接 → 原曲母带重贴音轨。
窗口已帧吸附（storyboard_build），故贴合步为恒等操作，合计严格=全曲长。

这不是正式成片：口型镜在预览里同样无口型，仅用于验证时间轴/分镜/对齐链路。
正式成片仍需步8接视频生成 API。

用法:
  python render_preview.py <project_dir> [--fps 24] [--width 720] [--height 1280]
产出: output/mv_preview.mp4 + output/verification_report.json
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

PRESETS = [  # Ken Burns 预设轮转: (zoom表达式模板, x, y)
    ("1+0.10*on/{D}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"),          # 推近
    ("1.10-0.10*on/{D}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"),       # 拉远
    ("1.08", "(iw-iw/zoom)*on/{D}", "(ih-ih/zoom)/2"),              # 左→右
    ("1.08", "(iw-iw/zoom)/2", "(ih-ih/zoom)*on/{D}"),              # 上→下
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}):\n  CMD: {subprocess.list2cmdline(cmd)}\n"
                           f"  ERR: {r.stderr.strip()[-400:]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--fps", type=float, default=24)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    a = ap.parse_args()
    proj = Path(a.project_dir)
    sb = json.loads((proj / "state" / "storyboard.json").read_text(encoding="utf-8"))
    # BUG-15 修法：全曲通常不是整数帧（48.848958s×24=1172.375），末镜按 ceil 会多出
    # 0.375 帧。改为末镜吸收残差：D_last = ⌊全曲×fps⌋ − Σ(前面各镜 D)，总帧数=⌊全曲×fps⌋
    song_dur = sb["shots"][-1]["window"]["end"]
    total_frames = int(math.floor(song_dur * a.fps))
    Ds = [int(math.ceil((s["window"]["end"] - s["window"]["start"]) * a.fps - 1e-4))
          for s in sb["shots"][:-1]]
    Ds.append(max(1, total_frames - sum(Ds)))
    img = next((proj / "input").glob("protagonist.*"))
    clips = proj / "clips"
    out_dir = proj / "output"
    out_dir.mkdir(exist_ok=True)

    report = []
    for i, s in enumerate(sb["shots"]):
        w = s["window"]
        dur = w["end"] - w["start"]
        D = Ds[i]
        zt, xt, yt = PRESETS[i % len(PRESETS)]
        print(f"[render] {s['id']} D={D} preset={i % len(PRESETS)}", flush=True)
        # BUG-10 修法：三个表达式都要做 {D} 替换（此前只替换了 z，x/y 的 {D} 原样进 ffmpeg）
        zt, xt, yt = (e.format(D=D) for e in (zt, xt, yt))
        vf = (f"scale={a.width * 2}:{a.height * 2},"
              f"zoompan=z='{zt}':x='{xt}':y='{yt}':"
              f"d={D}:s={a.width}x{a.height}:fps={a.fps}")
        raw = clips / f"{s['id']}_raw.mp4"
        fit = clips / f"{s['id']}.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(img),
             "-vf", vf, "-frames:v", str(D), "-c:v", "libx264", "-preset", "fast",
             "-crf", "20", "-pix_fmt", "yuv420p", str(raw)])
        # 时长贴合：以帧数换算的目标秒传入（D 帧精确），窗口已帧吸附时走 copy 快路径
        r = subprocess.run([sys.executable, str(Path(__file__).parent / "duration_fit.py"),
                            str(raw), str(fit), f"{D / a.fps:.9f}", "--fps", str(a.fps)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"duration_fit failed for {s['id']}: {r.stderr}")
        info = json.loads(r.stdout)
        report.append({"shot_id": s["id"], "target": round(dur, 3), **info})

    # concat
    lst = clips / "concat.txt"
    lst.write_text("".join(f"file '{(clips / (s['id'] + '.mp4')).as_posix()}'\n"
                           for s in sb["shots"]), encoding="utf-8")
    silent = out_dir / "mv_preview_silent.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(silent)])
    # 母带重贴
    final = out_dir / "mv_preview.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(proj / "input" / "song.mp3"),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(final)])

    total = sum(r["actual"] for r in report)
    print(json.dumps({"final": str(final), "clips": len(report),
                      "sum_actual": round(total, 3),
                      "max_delta": round(max(abs(r["delta"]) for r in report), 4)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
