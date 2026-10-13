# CHANGELOG · mv-auto-pipeline-fusion

## V1.3.8 · 2026-10-13 · 人物参考图一致性设定

- Skill 新增全流程人物参考设定：只参考人物身份和服装，细化五官、发型、耳饰与服装颜色/版型/纹样/层次锁。
- 场景、构图、机位、灯光及动作由分镜独立设计，身份与服装约束贯穿 Continuity Bible、提示词与动态审片。
- 逐镜主体声明移除固定的“年轻女子”假设；人物参考服装优先于系统补全服装，换装须来自用户明确要求。

## V1.3.7 · 2026-10-13 · 修复合成音质损失

- 修复真实项目把 16 kHz 单声道分析副本当成交付母带的错误；新增独立 `master_audio` 字段与共享母带解析器。
- 合成与预览不再统一有损转码 AAC 192 kbps；MP3/AAC 等原音频流直接复制，PCM/FLAC 转 ALAC 无损音轨，保持采样率和声道。
- 章节音频资产从原始母带裁切，默认保留采样率与声道，后端专用重采样需显式指定。
- 降级对齐器支持 `--master-audio`；未经显式母带声明的低采样率分析音频拒绝用于交付。

## V1.3.6 · 2026-10-12 · 恢复模型中立的完整 Skill 流程

- 修复把一次 MiniMax H3 试产方案写死进核心流程的问题；删除 H3 专属章节编译器，改为模型中立 `chapter_prompt_build.py`。
- `storyboard` 的 `backend` 改为 `generation_role`，只表达口型/叙事职责，不替用户选择服务商。
- 章节计划不再默认模型或 15 秒；时长上限必须来自用户选定后端的已核验契约并显式传入。
- 章节音频只生成可审计资产，不假设后端支持音频，也不发明 `audio_list` 等平台字段。
- `generation_manifest.json` 默认 `submission_ready=false`；后端名称、schema、音频绑定、并发和真钱封顶全部留给用户决定与外部适配层。
- 通用拼接器移除平台专属门禁，并修复作为 Python 包导入时的相对导入错误。
- 删除核心编译器中的单一导演姓名分支；导演路由由上游 ZY Skill 完成，核心只消费已选四轴。
- 修复章节文本遗漏导演四轴的问题；导演审核现在同时要求技术 PASS 与有效时间码观察记录。

## V1.3.5 · 2026-10-12 · H3 章节导演提示词编译

- 修复逐镜 Scene Master 在章节生成阶段被压缩成剧情摘要的问题，新增 `h3_prompt_build.py`。
- 将导演标签展开为机位、演员调度、光色、空间和剪辑五个可执行轴，最终提示词不再依赖导演姓名或“电影感”形容词。
- 每章按时间轴编入 Story Beat、Shot Delta、物理见证位置、口型状态和因果切点。
- 去 AI 化从负面词升级为成片行为约束：动作重量与惯性、材质信息层级、受光差异、非广告构图、禁止数字推拉和变形转场。
- Scene Master 新增强制字段：视觉中心、信息层级、视线目标、动作物理、材质响应和切镜触发。
- 新增样片优先策略与 `director_review_gate.py`；未经完整动态审片，批量生成与正式成片合成均被阻断。
- 新增 `references/dialogue-bug-review.md`，归档本次对话暴露的产品与工作流缺陷。

## V1.3.4 · 2026-10-12 · 修复 MiniMax H3 音频驱动模式

- 修正能力判断：MiniMax H3 支持 `audio_list`，但该参数属于 `reference-to-video`；`start-frame-to-video` 模式会排除音频输入。
- 新增 `chapter_audio_build.py`，严格按章节窗口裁切母带并记录 SHA-256，避免“生成时没传音频、合成时才覆盖音轨”的假口型通过。
- 章节计划明确写入 `generation_mode=reference-to-video` 与 `audio_input=audio_list`；合成前强制检查音频驱动证据。
- 验收措辞分层：已传人声可称“音频驱动口型”，只有通过权威 ASR/音素级验收后才能称“逐字口型 PASS”。

## V1.3.3 · 2026-10-12 · MiniMax H3 长章节自动成片

- 用 ZY Story Visual Development 的故事断点把 14 镜聚合为 4 个不超过 15 秒的章节；模型时长上限不再替代叙事边界。
- 使用 Lovart skill + MiniMax H3 真实生成四章视频，并支持超时状态下继续查询、增量下载和旧产物去重。
- 修复 H3 时长量化偏差：逐章经 `duration_fit.py` 回贴故事窗口。
- 修复 H3 “768P”实际返回 1344×768、并非严格 16:9：`stitch_chapters.py` 统一中心裁切到 1280×720。
- 拼接后重新贴回 48.849 秒母带；对齐三验 PASS。
- 明确 H3 叙事视频与音频驱动口型的能力边界，禁止把母带对齐误报为逐字口型通过。

## V1.3.2 · 2026-10-12 · 多场景 MV 预演

- 修复只声明接入 ZY Cinematic Realism、实际仍按歌词套通用动作模板的问题：新增 `story_plan.json` 契约，覆盖来源台账、叙事弧、Continuity Bible、逐镜 Scene Master 与 Shot Delta。
- `storyboard_build.py` 缺少故事方案时明确标记 `timing_only`；`prompt_build.py` 阻断模板化降级；Gate 5/6 增加故事结构与指纹检查。
- 新增 `chapter_plan_build.py`，按模型最大时长在歌词边界聚合故事镜头，供 MiniMax H3 等长视频模型批量生成。
- 新增 `stitch_chapters.py`，处理 MiniMax H3 768P 实际 1344×768 的非严格 16:9 输出，中心裁切到 1280×720 后重贴母带。
- 真实复盘确认“单张人物图全片 Ken Burns”只能算技术预览，不能称为 MV 视觉产出。
- `render_preview.py` 优先读取 `input/scene_*.png`，按歌曲时间章节分配到不同分镜；支持逐镜 `visual_asset` 覆盖与自定义输出文件名。
- 人物参考图仅用于生成场景关键帧时锁定 `likeness + wardrobe`，不再直接充当所有镜头。
- 新增多场景章节分配回归测试。

## V1.3.1 · 2026-10-12 · 16:9 人物参考真实试产修复

以 48.85 秒母带、12 行官方歌词和竖幅人物参考图真实生成 1280×720 预览，反推并修复：

- 新增 `scripts/prompt_build.py`，补齐步骤 5 从 storyboard 到 14 镜六段式提示词的可执行断点。
- 人物参考职责由单一 `likeness` 扩为 `likeness + wardrobe`，锁定五官、发型、耳饰、服装版型/纹样/层次，并明确禁止继承参考图构图、背景与灯光。
- 修复竖图直接缩放到横屏导致人物五官和身形变形：预览改为等比前景 + 同图模糊填充。
- `gate_checks.py` 自动落盘 `gates/gate*.json` 和零依赖 HTML；关 5 通过后回写逐镜提示词指纹。
- Windows 命令行统一使用 UTF-8，测试子进程显式按 UTF-8 解码。
- 真实样片关 1 为 6/6、关 5 为 197/197、关 6 为 8/8，对齐三验 PASS。

## V1.3.0 · 2026-10-12 · ZY Cinematic Realism 提示词构造层

### 新增

- 内置上游 `ZY Cinematic Realism / 造梦师 v2.5.0`（提交 `9a3b36d1fb6a980ae9e21f74c86dd56bae443a4d`），以原名放置于 `vendor/zy-cinematic-realism/`。
- 新增 `references/zy-cinematic-integration.md`，定义 Scene Master、Creative Grammar、连续性与结果修复到 MV 六段式字段的映射。
- 新增第三方许可声明与回归测试，确保上游 `CC BY-NC 4.0`、作者署名、来源和 MV 权限边界持续存在。

### 调整

- 步骤 5 改为：冻结时间轴与口型硬事实 → 构造 Scene Master → 应用必要的 Creative Grammar → 映射六段式 → 14 项门禁。
- 静帧模型适配器仅用于参考帧；视频提示词在获得真实后端契约前保持模型中立。
- 将旧的同源改名副本 `vendor/cinematic-frame-craft/` 替换为可追溯的上游原名目录，并恢复缺失的 `LICENSE`、`NOTICE.md` 与文件级版权头。

## V1.2.0 · 2026-10-12 · mv-test-01 实跑复盘发版

第一支真实产出（48.85s 歌曲 + 真主人公图），从成片反推出 8 项修复。铁律 F 首次闭环。

### 新增

- `scripts/timeline_fallback.py` — 无 ASR key 的降级对齐器（BUG-02）：均匀分布 + 全行 pending_review，明确声明不可冒充权威对齐。
- `scripts/storyboard_build.py` — 步骤 4 推导工具：窗口帧吸附 + 口型节奏（副歌优先/连续≤3/目标45%）+ 景别轮转（BUG-03/04）。
- `scripts/render_preview.py` — 静帧预览成片：无视频 API 时的全链产出通路（Ken Burns + 母带重贴）。
- `gate_checks.py gate1` 子命令 — 关 1 时间轴机检 6 项（BUG-05）。

### 修复（全部由真实产出反推）

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| BUG-05 | 关 1 无机检 | SKILL.md 承诺每关机检，只有关 5/6 有脚本 | gate_checks.py 增 gate1（6 项） |
| BUG-06 | gate1 崩溃 | main() 无条件加载 style.json，但关 1 跑在关 2 之前 | style 缺失时空处理 |
| BUG-07 | gate6 拦下窗口合计≠全曲长 | 分镜工具只给歌词行建窗，漏间奏窗 | 间奏生成 insert 镜 |
| BUG-08 | 窗口相邻性差 ±1 帧 | 逐行各自 snap，边界两侧取值不一致 | 边界数组法：每边界吸附一次两侧行共享 |
| BUG-09 | 间奏镜假阳性 | 空字典.get("text") 返回 None 而非 ""，None=="" 为假 | 机检 #2 语义重写：间奏镜不得携带歌词 |
| BUG-10 | SH003 渲染炸 -22 | `{D}` 占位符只对 zoom 表达式做了替换，x/y 原样进 ffmpeg | 三个表达式统一 format |
| BUG-11/14 | 单镜 +1 帧、累加漂移 0.19s | ceil 无浮点护栏 + 6 位小数存储误差(1.2e-5帧) > 1e-6 护栏 | snap 存 10 位；护栏放大至 1e-4（<半帧 0.021s） |
| BUG-12/13 | 台账 sum_actual 虚高 | ffprobe 容器时长对末帧多报 1 帧；重编码 fps+tpad+-t 又塞 1 帧 | 计量改用 nb_frames/fps；帧数已合时直接流复制 |
| BUG-15 | 末镜多 0.375 帧 | 全曲 48.848958s×24=1172.375 非整数帧 | 末镜吸收残差：总帧数=⌊全曲×fps⌋ |

（BUG-01 为分析 harness 自身帧/字节混淆，skill 脚本无误，记入复盘不进修复表。）

### 沉淀的规矩（帧网格全链纪律）

1. 边界吸附一次、两侧共享（边界数组法），存 10 位小数。
2. ceil 护栏取 1e-4：大于存储噪声、小于半帧。
3. 末镜吸收全曲非整数帧残差。
4. 时长贴合优先「验证+流复制」，重编码是兜底不是默认。
5. 时长计量用 `nb_frames/fps`，不信容器 format duration。

### 已知限制

- uniform_fallback 时间轴只可用于流程试跑与静帧预览；口型正式成片必须走 ASR 通路。
- 静帧预览成片无口型（口型镜同普通镜渲染），仅验证时间轴/分镜/对齐链路。
- 末镜吸收残差后视频比音频短 ≤1 帧，由 mux -shortest 收口（尾部 ≤42ms，落在外拍淡出区）。

## V1.1.0 · 2026-10-12 · 提示词构造层升级

- 具体瞬间优先（camera 段最后派生）、场景母版（跨镜事实锁）、导演参考轴、参考职责分离、局部修复判定（重抽前置层）。
- 关 5 机检 11 → 14 项。

## V1.0.0 · 2026-10-12 · 首版

- 十二步八道关骨架 + 六铁律 + 三脚本（gate_checks / duration_fit / align_verify / ledger）+ 五份规格文档。
