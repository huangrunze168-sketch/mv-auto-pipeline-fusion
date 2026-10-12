#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导演样片审片门禁：技术通过不等于艺术通过。"""
import argparse
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DIMENSIONS = (
    "story_readability", "performance", "blocking_and_gaze", "camera_witness",
    "motion_physics", "source_light_and_material", "continuity", "editing",
    "lip_sync",
)


def initial_review(plan: dict) -> dict:
    prototype = plan.get("production_policy", {}).get("prototype_chapter")
    if not prototype:
        raise ValueError("chapter_plan 缺少 production_policy.prototype_chapter")
    return {
        "schema_version": 1,
        "prototype_chapter": prototype,
        "reviewed_media": "",
        "watched_full_duration": False,
        "technical_checks": {
            "container_and_duration": "pending",
            "audio_alignment": "pending",
            "note": "技术检查与导演检查必须分开记录",
        },
        "director_checks": {
            name: {"status": "pending", "evidence": ""} for name in DIMENSIONS
        },
        "timecoded_findings": [],
        "decision": "pending",
        "batch_generation_allowed": False,
    }


def validate_review(review: dict, plan: dict) -> list[str]:
    errors = []
    expected = plan.get("production_policy", {}).get("prototype_chapter")
    if review.get("prototype_chapter") != expected:
        errors.append("样片章节与 chapter_plan 不一致")
    if not review.get("reviewed_media"):
        errors.append("缺少 reviewed_media")
    elif Path(str(review["reviewed_media"])).suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        errors.append("reviewed_media 必须是动态视频，联系表或图片不可作为审片对象")
    if review.get("watched_full_duration") is not True:
        errors.append("必须完整观看动态样片，联系表或首帧不能替代")
    technical = review.get("technical_checks", {})
    for name in ("container_and_duration", "audio_alignment"):
        if technical.get(name) != "pass":
            errors.append(f"技术检查未通过: {name}")
    checks = review.get("director_checks", {})
    for name in DIMENSIONS:
        item = checks.get(name, {})
        if item.get("status") != "pass":
            errors.append(f"导演维度未通过: {name}")
        if not str(item.get("evidence", "")).strip():
            errors.append(f"导演维度缺少可观察证据: {name}")
    findings = review.get("timecoded_findings", [])
    if not findings:
        errors.append("至少需要一条 timecoded_findings，证明审片基于动态时间线")
    for index, finding in enumerate(findings, 1):
        try:
            start = float(finding.get("start_sec"))
            end = float(finding.get("end_sec", start))
        except (TypeError, ValueError):
            errors.append(f"timecoded_findings[{index}] 时间码无效")
            continue
        if start < 0 or end < start:
            errors.append(f"timecoded_findings[{index}] 时间范围无效")
        if finding.get("dimension") not in DIMENSIONS:
            errors.append(f"timecoded_findings[{index}] dimension 无效")
        if not str(finding.get("observation", "")).strip():
            errors.append(f"timecoded_findings[{index}] 缺少 observation")
    if review.get("decision") != "approve":
        errors.append("decision 必须为 approve")
    if review.get("batch_generation_allowed") is not True:
        errors.append("batch_generation_allowed 必须为 true")
    return errors


def approved(project: Path) -> tuple[bool, list[str]]:
    plan = json.loads((project / "state" / "chapter_plan.json").read_text(encoding="utf-8"))
    path = project / "state" / "director_review.json"
    if not path.is_file():
        return False, ["缺少 state/director_review.json"]
    review = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_review(review, plan)
    return not errors, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("init", "check"))
    parser.add_argument("project_dir")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    plan = json.loads((project / "state" / "chapter_plan.json").read_text(encoding="utf-8"))
    path = project / "state" / "director_review.json"
    if args.action == "init":
        if path.exists():
            raise FileExistsError(f"审片记录已存在，拒绝覆盖: {path}")
        path.write_text(json.dumps(initial_review(plan), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(json.dumps({"status": "pending", "output": str(path)}, ensure_ascii=False))
        return
    ok, errors = approved(project)
    print(json.dumps({"status": "approved" if ok else "blocked", "errors": errors},
                     ensure_ascii=False))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
