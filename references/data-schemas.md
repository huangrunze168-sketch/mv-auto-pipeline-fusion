# 数据 Schema 规格

> 所有状态文件 JSON，UTF-8，字段名英文（铁律 C 语言分层）。时间单位一律秒（float），禁止字符串时间码进状态层。

V1.4 以 `visual-workflow-contract.md` 为新增视觉开发/资产/剪辑数据契约。下面的旧示例仅说明通用字段；新项目使用 schema_version=2、timing_mode=music_referenced_visual_edit、timing_refs、lyric_lines、scene_id 与显式 performance_policy。

## 1. state/timeline.json —— 权威时间基准（关 1 产物）

```json
{
  "song": "demo_song",
  "source_audio": "input/demo_song.mp3",
  "master_audio": "input/demo_song.mp3", // 用户原始母带；source_audio 可为分析副本，交付只读 master_audio
  "duration_sec": 245.32,
  "fps_assumed": 24,
  "asr_engine": "volc-audio-align",
  "lines": [
    {
      "index": 1,
      "type": "vocal",            // vocal | harmony | bridge | interlude
      "text": "画不完的圆",
      "start": 12.40,             // ASR 给时间
      "end": 16.08,
      "confidence": 0.97,         // ASR 置信度；官方歌词校正后标记 corrected
      "corrected": true           // 是否被官方歌词改写过
    },
    {
      "index": 2,
      "type": "interlude",        // 间奏显式标出（铁律 A：间奏决定分镜切点）
      "text": "",
      "start": 16.08,
      "end": 24.50,
      "confidence": 1.0,
      "corrected": false
    }
  ],
  "segments": [                    // 歌曲结构段（verse|chorus|bridge|intro|outro）
    { "id": "S01", "role": "verse", "line_indexes": [1, 2], "start": 12.40, "end": 45.10 }
  ],
  "lyrics_source": "official",     // official | asr_only
  "pending_review": []             // 待核行：confidence < 0.85 的行，需用户点头
}
```

导出规则：`.lrc` 由 lines 生成，`[mm:ss.xx]text`；interlude 行不写文本。

## 2. state/style.json —— 风格锁定（关 2 产物，先于资产）

```json
{
  "style_name": "东方器物 · 电影化",
  "visual_keywords": ["水墨质感", "低饱和", "侧逆光"],
  "palette": { "primary": "#1a1a1a", "accent": "#c8a86b" },
  "wardrobe": "素色棉麻长衫",
  "aspect_ratio": "9:16",
  "resolution": "1080x1920",
  "scene_master": {                 // 跨镜场景事实锁（可选，锁定后关5机检#13生效）
    "locked": true,
    "space": ["昏暗书房", "木格窗"],
    "light_sources": ["铜灯烛火", "窗纸月色"],
    "props": ["黄铜罗盘", "翻开的案卷"],
    "palette_locked": true
  },
  "director_ref": {
    "name": "用户选择的导演参考",
    "intensity": "轻微",
    "axes": {
      "light_contrast": "由所选导演文件推导的场景级决策",
      "color_exposure": "由所选导演文件推导的场景级决策",
      "lens_camera": "由所选导演文件推导的场景级决策",
      "composition_space": "由所选导演文件推导的场景级决策"
    },
    "active_traits": ["只保留与本场景兼容的可执行特征"]
  },
  "fingerprint": "sha256:...",    // 锁定后指纹化；提示词派生必须引用同一指纹
  "locked": true
}
```

## 3. state/storyboard.json —— 分镜表（关 4 产物）

```json
{
  "shots": [
    {
      "id": "SH001",
      "segment": "S01",
      "lyric_line": 1,             // 对应 timeline.lines.index；间奏镜可为 null
      "window": { "start": 12.40, "end": 16.08 },  // 从歌词边界或有证据的音乐切点引用推导
      "shot_type": "特写",          // 大特写|特写|近景|中景|中远景|全景|远景|空镜|背影|群像
      "lip_sync": true,            // 只有前四类允许 true（铁律 B）
      "role": "perform",           // perform | narrative | insert
      "visual_concept": "主人公垂眸看手中罗盘，烛光晃动",
      "camera": "缓慢推近",
      "generation_role": "lip_sync", // lip_sync | narrative；不是后端名称
      "prompt_file": "prompts/SH001.json",
      "prompt_fingerprint": null,  // 关5通过后写入；重抽卡时比对失效则退回
      "repair": {                  // 局部修复判定：重抽前先判能否局部修
        "mode": "none",            // none | partial | full_reroll
        "problems": []             // 最多 3 个主导问题，每项 {"field": "...", "desc": "..."}
      },
      "status": "pending"          // pending|generated|fitted|verified|failed
    }
  ],
  "performance_policy": {}         // 比例与连续上限仅在项目明确指定时启用
}
```

## 4. prompts/SHxxx.json —— 六段式提示词（关 5 校验对象）

```json
{
  "meta": {
    "shot_id": "SH001",
    "window": { "start": 12.40, "end": 16.08 },
    "duration_sec": 3.68,
    "shot_type": "特写",
    "lip_sync": true,
    "generation_role": "lip_sync",
    "lyric_line": 1,
    "lyric_text": "画不完的圆",
    "style_fingerprint": "sha256:...",
    "character_fingerprint": "sha256:...",
    "reference_duties": ["likeness", "wardrobe"]  // 人物图仅锁五官/发型/服装，不继承构图背景灯光
  },
  "style": "低饱和水墨质感，侧逆光，东方器物美学",
  "scene": "昏暗书房，烛火在铜灯里摇曳，窗纸透出月色",
  "subject": "素色棉麻长衫的年轻女子，眉眼低垂",
  "performance": "女子缓缓抬手抚过罗盘边缘，唇形随歌词开合\n画不完的圆",
  "camera": "中近景，缓慢推近，浅景深",
  "audio_policy": "人声驱动口型，逐字对齐歌词「画不完的圆」",
  "negative_prompt": "念白, 字幕, 水印, 多人, 面部变形"
}
```

**派生顺序硬规矩**：style→scene→subject→performance 先成立，camera 最后派生——先让画面成为故事中的具体瞬间，再考虑镜头与胶片词。

**不对口型段的 audio_policy 必须含**：「嘴唇自然闭合、不跟随人声开合」，且 negative_prompt 必须含口型类词（`张嘴说话|对口型|lip movement`）——机检第 5 项。

## 5. state/ledger.jsonl —— 成本台账（追加制）

```json
{"ts": "2026-10-12T14:00:00", "action": "submit", "shot_id": "SH001", "backend": "user-selected-provider", "coins": 0, "cash_cny": 1.20, "note": "首镜试产"}
```

字段固定 8 个：`ts / action / shot_id / backend / coins / cash_cny / duration_sec / note`。`action ∈ submit|retry|salvage|fail_refund|fit|concat`。汇总口径见 `scripts/ledger.py`。

## 6. output/verification_report.json —— 对齐三验报告（关 7/8）

```json
{
  "check1_total_duration": { "clips_sum": 245.31, "song": 245.32, "diff": 0.01, "pass": true },
  "check2_waveform_lag": [
    { "shot_id": "SH001", "expected_start": 12.40, "best_lag": 0.02, "correlation": 0.83, "pass": true }
  ],
  "check3_vocal_energy": [
    { "shot_id": "SH001", "lip_sync": true, "energy": 0.117, "pass": true }
  ],
  "overall": "PASS"
}
```

阈值：check2 `|lag| < 0.15s` 且 `correlation > 0.6`；check3 `energy > 0.05`（全混代理，可按曲调参）。
