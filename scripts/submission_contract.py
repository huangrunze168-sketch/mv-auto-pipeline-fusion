#!/usr/bin/env python3
"""校验外部视频后端提交包，阻止角色引用静默降级。

核心流水线保持后端中立。本模块只校验外部适配器已经解析出的事实，
不保存凭证、不调用供应商 API，也不猜测任何供应商专属字段。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


MENTION_RE = re.compile(
    r"(?<![\w@])(@(?:图片|视频|音频)\s*\d+|@[\w\-\u3400-\u9fff]+)"
)
SUBJECT_BINDING_KINDS = {
    "library_subject", "structured_mention", "omni_image_reference",
}
SUBJECT_ID_FIELDS = ("subject_id", "asset_id", "mention_id", "url")
OMNI_REFERENCE_MODALITIES = {"image", "video", "audio"}
OMNI_REFERENCE_INTENTS = {
    "character_identity", "wardrobe", "location", "composition", "storyboard",
    "camera_motion", "action_timing", "performance_timing", "voice", "sound",
    "material", "lighting", "style",
}
REQUIRED_REFERENCE_MODE = "omni_reference"


def _structured_mention_names(contract: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in contract.get("structured_mentions", []):
        if isinstance(item, str):
            names.add(item.lstrip("@").strip())
        elif isinstance(item, dict):
            name = str(item.get("name", "")).lstrip("@").strip()
            if name:
                names.add(name)
    return names


def _prompt_handles(prompt: str) -> set[str]:
    return {match.group(1).replace(" ", "") for match in MENTION_RE.finditer(prompt)}


def _binding_handle(binding: dict[str, Any]) -> str:
    return str(binding.get("handle", "")).strip().replace(" ", "")


def _has_asset_locator(binding: dict[str, Any]) -> bool:
    source = binding.get("source") or {}
    return any(str(source.get(key, "")).strip() for key in ("asset_id", "url"))


def validate_submission_contract(contract: dict[str, Any]) -> list[str]:
    """返回提交包错误；空列表表示可以交给外部适配器提交。"""

    errors: list[str] = []
    prompt = str(contract.get("prompt", ""))
    reference_mode = contract.get("reference_mode")
    if reference_mode != REQUIRED_REFERENCE_MODE:
        errors.append(
            "正式视频提交必须使用 reference_mode=omni_reference；"
            "更换供应商不能降级为文生视频、单首帧图生视频或仅角色库模式"
        )
    literal_mentions = _prompt_handles(prompt)
    bound_mentions = {f"@{name}" for name in _structured_mention_names(contract)}
    bound_mentions.update(
        _binding_handle(item) for item in contract.get("reference_bindings", [])
        if isinstance(item, dict) and _binding_handle(item)
    )

    for name in sorted(literal_mentions - bound_mentions):
        errors.append(
            f"{name} 只是提示词文本，未绑定真实参考素材；禁止让模型自行猜测"
        )

    subject = contract.get("subject_reference") or {}
    if subject.get("required"):
        binding = subject.get("binding") or {}
        kind = binding.get("kind")
        status = binding.get("review_status")
        identity = next((binding.get(key) for key in SUBJECT_ID_FIELDS if binding.get(key)), None)

        if kind not in SUBJECT_BINDING_KINDS:
            errors.append(
                "人物一致性镜头缺少可追溯绑定；须使用角色库标识或全能参考图片资产"
            )
        if kind in {"library_subject", "structured_mention"} and status != "approved":
            errors.append("角色资产尚未明确标记为 approved")
        if not identity:
            errors.append("角色绑定缺少 subject_id、asset_id、mention_id 或托管 URL")

        expected_handle = str(subject.get("handle") or subject.get("name", "")).strip()
        if expected_handle and not expected_handle.startswith("@"):
            expected_handle = "@" + expected_handle
        if expected_handle and expected_handle.replace(" ", "") not in bound_mentions:
            errors.append(f"角色 {expected_handle} 未绑定到提示词引用")

    audio = contract.get("audio_reference") or {}
    request = contract.get("request") or {}
    if audio.get("condition_only") and request.get("generate_audio") is not False:
        errors.append(
            "参考音频声明为仅驱动表演/口型时，generate_audio 必须显式为 false；"
            "最终成片应重贴原始母带"
        )

    bindings = contract.get("reference_bindings") or []
    capabilities = contract.get("backend_capabilities") or {}
    if reference_mode == REQUIRED_REFERENCE_MODE:
        if capabilities.get("verified") is not True:
            errors.append("全能参考模式缺少已核验的后端能力回执")
        if capabilities.get("omni_reference") is not True:
            errors.append("所选后端未声明支持多模态全能参考")
        if not bindings:
            errors.append("全能参考模式至少需要一个真实参考素材")

        seen_handles: set[str] = set()
        counts = {key: 0 for key in OMNI_REFERENCE_MODALITIES}
        for binding in bindings:
            if not isinstance(binding, dict):
                errors.append("reference_bindings 必须是对象列表")
                continue
            handle = _binding_handle(binding)
            modality = str(binding.get("modality", "")).strip()
            intents = set(binding.get("intents") or [])
            if not handle or not handle.startswith("@"):
                errors.append("全能参考素材缺少可在提示词中点名的 handle")
            elif handle in seen_handles:
                errors.append(f"全能参考 handle 重复: {handle}")
            else:
                seen_handles.add(handle)
            if modality not in OMNI_REFERENCE_MODALITIES:
                errors.append(f"{handle or '未命名素材'} 的 modality 无效: {modality}")
            else:
                counts[modality] += 1
            if not _has_asset_locator(binding):
                errors.append(f"{handle or '未命名素材'} 缺少 asset_id 或 Lovart 托管 URL")
            if not intents:
                errors.append(f"{handle or '未命名素材'} 未声明参考意图")
            unknown = sorted(intents - OMNI_REFERENCE_INTENTS)
            if unknown:
                errors.append(f"{handle or '未命名素材'} 包含未知参考意图: {','.join(unknown)}")
            if handle and handle.replace(" ", "") not in literal_mentions:
                errors.append(f"{handle} 已上传但未在提示词中点名其参考职责")

        limits = capabilities.get("reference_limits") or {}
        for modality, count in counts.items():
            limit = limits.get(modality)
            if isinstance(limit, int) and count > limit:
                errors.append(f"{modality} 参考数量 {count} 超过后端上限 {limit}")

    edit_shots = contract.get("edit_shots") or []
    if len(edit_shots) > 1:
        if capabilities.get("multi_shot") is not True:
            errors.append("多镜生成包所选后端未核验 multi_shot 能力")
        if capabilities.get("timestamp_control") is not True:
            errors.append("多镜生成包所选后端未核验 timestamp_control 能力")
        for shot in edit_shots[:-1]:
            if not str(shot.get("cut_relation", "")).strip():
                errors.append(f"{shot.get('id', 'unknown')} 缺少 cut_relation")

    if contract.get("director_cut_status") != "approved":
        errors.append("提交前必须通过导演剪辑门禁 director_cut_status=approved")

    return errors


def require_submission_contract(contract: dict[str, Any]) -> None:
    errors = validate_submission_contract(contract)
    if errors:
        raise ValueError("后端提交包未通过：" + "；".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="校验外部视频后端提交契约")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = validate_submission_contract(contract)
    print(json.dumps({"pass": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
