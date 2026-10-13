---
name: mv-auto-pipeline-fusion
description: >
  一首歌 + 一张图 → 一支口型对得上的音乐 MV。
  十二步全链流程：从歌词时间轴到成片对齐验收，八道关机检兜底。
  触发词：做 MV、音乐视频、口型对齐、MV 流水线、给这首歌出画面。
---

# MV-AUTO-PIPELINE-FUSION · 音乐 MV 全自动生成 SOP（V1.4.0）

> 一句话需求：**给一首歌和一张图，出来一支完整的、口型对得上的音乐 MV。**
> 技术基线：全 API（无需 GPU）· 运行形态：Agent Skill。
> V1.4.0：ZY 故事、参考视觉、导演/摄影方法三链协同；音乐窗口与视觉分镜分离；场景母版 → 分镜关键帧 → 动作制作包 → 素材选段 → 段落审片。原始母带保持独立，生成后端由用户选择。

## 输入 / 输出

**你给它**

- 一首歌（必需）：mp3 / wav / flac / m4a
- 官方歌词（强烈建议）：没有也能跑，但 ASR 必有错字，歌词待核行需要你点头
- 主人公图（可选）：默认只锁 `likeness + wardrobe`（五官、发型、耳饰、服装），不继承构图、背景或灯光；不给走无主角模式

**它还你**

- 成片两条：逐段内嵌音乐版（交叉验证用）+ 画面轨重贴母带版（交付首选）
- 分镜表 storyboard.json：逐段窗口 / 口型 / 景别 / 画面构想
- 歌词时间轴 timeline.json + 权威 lrc，逐行带置信度
- 对齐验收报告 verification_report.json

## 人物参考图设定（全流程生效）

用户提供的人物图片只作为同一人物的身份与服装依据，参考职责固定为 `likeness + wardrobe`：

- **五官一致**：保持脸型、眼形与眼距、眉形、鼻形、唇形及五官比例；保持发型、发色和耳饰等身份特征。不同景别、角度和表情仍须可辨认为同一人物。
- **服装一致**：保持服装颜色、版型、领口、袖型、面料、纹样、刺绣、层次与配饰。人物参考中的服装作为默认锁定事实，风格或导演方法不得擅自改衣；只有用户明确要求换装时才更新锁。
- **分镜独立设计**：背景、场景、构图、机位、景别、光源、姿势和动作由 Story Visual Development 与 Scene Master 决定，不从人物图继承。参考图中的其他人物、道具和文字不自动进入故事。
- **允许真实表演**：表情、视线、姿态、走位、衣料运动及受光变化随剧情自然变化；人物一致性不要求所有镜头复用同一姿势或构图。
- **持续携带与验收**：步骤 3 登记参考图指纹和职责；步骤 4 把身份与服装写入 Continuity Bible；步骤 5 的逐镜与章节制作包保留这些锁；步骤 7/9/10 审片核对身份和服装漂移，修复时保留其余已成功事实。提示词中的一致性要求需实际审片验证，不能当作模型已经实现的保证。

逐镜提示词统一声明：`仅参考图中人物的五官、发型、耳饰与服装；跨镜保持同一人物和同一套服装。场景、构图、光线及动作服从本镜 Scene Master。`

## 项目目录（每个 MV 一个 project dir，全部状态落盘，可断点续跑）

```
project/
├── input/            # 原曲母带、官方歌词、主人公图
├── state/            # timeline.json / style.json / storyboard.json / ledger.jsonl
├── prompts/          # SHxxx.json（六段式提示词）
├── clips/            # 逐段生成视频 + 时长贴合后版本
├── output/           # 成片 + 验收报告
└── gates/            # 八道关 HTML 页面
```

## 十二步 · 八道关

| 步 | 内容 | 关 | 硬门禁 |
|---|---|---|---|
| 1 | 歌词提取与强制对齐：ASR API 只给时间，文本用官方歌词校正 → timeline.json（权威时间基准诞生地） | 关 1 | |
| 2 | 音乐结构、全片导演提案与视觉目标；风格先于场景资产，但人物图服装锁优先于系统风格补全 | 关 2 | |
| 3 | Reference Roles 与人物锁；需要参考视觉分析时调用 Medium Router / Dream Decode，记录实际观察范围 | 关 3 | |
| 4 | Story Visual Development + Source Ledger + 导演路由 + Continuity Bible；用音乐引用设计 visual_edit_plan，再合并 story_plan | 关 4 | |
| 5 | ZY 契约检查；分开编译场景母版、分镜关键帧与视频运动提示词；20 项逐镜检查及来源/依赖检查全过 | 关 5 | ⛔ 硬 |
| 6 | 音乐窗口与口型核对：窗口首尾相接、合计=全曲长、口型与景别一致，**任何环节不许手写秒数** | 关 6 | ⛔ 硬 |
| 7 | 场景母版候选比较、Remix 单轴变体与关键帧审查；资产批准后，用户所选后端按真实契约生成代表样片并完成动态/段落审片 | | |
| 8 | 批量生成：多路并发、断点续跑、在途任务救回；每 10–15 分钟主动汇报 | | |
| 9 | Decode Repair / Result Repair：合理适配不报漂移；最多三项主因；局部修复保护成功事实，结构失败返回 Scene Master；上游变化使依赖资产需复核 | | |
| 10 | 已审素材选段与本地剪辑；段落节奏/情绪/镜头关系检查，再重贴原始母带及对齐验收 | 关 7 / 8 | |
| 11 | 交付打包：成片 ×2 + 分镜表 + lrc + 验收报告 | | |
| 12 | 项目复盘（不是可选项）：复盘三问，沉淀落到代码 / 文档 / 自检清单三处，发版 | | |

**结构机检使用 `gate_checks.py` 与 `visual_development.py`。** 机器检查验证契约、引用和指纹，不能证明审美通过。图片须实际观察，运动与表演须动态审片；用户说「全自动」不豁免机检，也不能把联系表当成完整观看。

## 六条铁律（写死在流程里，除非用户明确要求修改）

- **A 音乐是唯一时间基准**：音频歌词窗口不随画面设计改变；视觉镜头引用歌词边界或有分析依据的音乐切点，可拆分一句或跨多句。音乐结构未知时标为 pending，不把后半段猜成副歌。歌词一行不能少，间奏显式标注。
- **B 中近景承载口型**：大特写 / 特写 / 近景 / 中景允许口型；其他景别不对口型。景别与演唱分配由导演方案决定，不轮换；口型占比与连续上限在项目 performance_policy 中显式配置，不再强加全项目 45% 或连续三镜配额。
- **C 唱歌不是说台词**：发声行走唱歌框架，一句歌词独立成行；禁止「说某某话」写法。不对口型段强制注入「嘴唇自然闭合、不跟随人声开合」声明 + 负面提示压口型。字段名 / 标签英文，叙述 / 歌词中文。
- **D 不猜、不烧冤枉钱**：先拉真实节点表体检再提交；共享模板去参考化；母带与参考图指纹缓存全片只传一次；失败任务回挖真实原因。账号降级、双池并行、真钱封顶是三个独立开关。
- **E 八道关 + 对齐三验**：任一验不过，不许说「做完了」。
- **F 会自己长本事**：每支 MV 收尾必复盘，沉淀三处缺一不算修好，改完必须发版（全量自检 + 快照 + 标签），回退前先备份。

## 关键机制

- **ZY 开发契约**（`scripts/visual_development.py`）：检查 treatment、已读来源、事实/解释/提案、参考职责、视觉规律、实际导演文件指纹、逐镜激活轴与观察依据、连续性前后状态及动作起止。指定导演而无路由决策时阻断，未激活轴保留，不自动“增强”强度。
- **资产依赖**（`scripts/visual_assets.py`）：场景母版与关键帧分别登记，批准须带实际观察证据；关键帧引用同场景母版版本。母版/人物/上游记录改变后，受影响资产必须复核。登记工具记录审查，不替人看图。
- **单轴比较与修复**（`scripts/visual_revision.py`）：Remix 检查一个主要变量及允许后果；修复计划必须提供主因、实际漂移证据、CHANGE ONLY / PRESERVE EXACTLY。工具不代替视觉判断，也不提交生成任务。
- **素材剪辑**（`scripts/edit_assemble.py`）：从 generated_clips 与 edit_selection 按帧选取已审素材；生成片段长度不等于剪辑镜头长度。只在显式 --render 时本地裁切，校验长度/帧率/指纹，不自动变速；正式合成消费已完成剪辑产物。

- **交付音质保护**（`scripts/audio_master.py`）：`timeline.master_audio` 指向用户原始母带；分析用 16 kHz 单声道副本只供 ASR/对齐，禁止作为交付母带。支持的原始音频流直接复制，不再统一压成 AAC 192 kbps；PCM/FLAC 使用 ALAC 无损交付。章节资产默认保留母带采样率与声道，后端要求的转换只作用于其输入资产。对齐报告不能证明音质保真。

- **降级对齐**（`scripts/timeline_fallback.py`）：无 ASR key 时按能量起点 + 均匀分布生成试跑时间轴，全行 pending_review 待用户点头；**不可用于口型正式成片**。
- **分镜构建**（`scripts/storyboard_build.py`）：visual_edit_plan 使用音乐引用安排任意数量镜头，窗口吸附到帧网格，自动记录覆盖的歌词行。无视觉编辑方案时只输出空镜头时间骨架，不分配景别/口型或编造剧情。
- **故事编译**（`scripts/prompt_build.py`）：强制要求 `story_mode=zy_story_visual_development`，从因果链、连续性与 Shot Delta 构造提示词，不再使用歌词动作模板。
- **多场景预览成片**（`scripts/render_preview.py`）：优先把 `input/scene_*.png` 按歌曲章节分配给各镜；只有没有场景关键帧时才回退人物图。静帧仍只验证剪辑结构，口型与真实运动需走视频 API。
- **时长贴合**（`scripts/duration_fit.py`）：帧网格对齐（护栏 1e-4），帧数已合时流复制跳过重编码；计量用 nb_frames/fps，不信容器时长。
- **对齐三验**（`scripts/align_verify.py`）：包络 + 局部搜索，纯标准库：① 各段时长合计 = 原曲长 ② 逐段波形最优滞后 ≈ 0 且相关度达标 ③ 对口型段人声能量非空。
- **成本台账**（`scripts/ledger.py`）：币与真钱分列，调度动作全留痕；总览三数——成片多少秒、机器跑了多久、花了多少。
- **电影化提示词构造**（`references/zy-cinematic-integration.md`）：使用 `vendor/zy-cinematic-realism/` 的 Scene Master、Creative Grammar、连续性与局部修复方法；只负责视觉构造，不得改写 timeline 窗口、歌词、口型、音频策略或后端契约。
- **长视频章节**（`scripts/chapter_plan_build.py`）：模型最大时长是硬上限，ZY 故事断点优先；每章继续携带 Continuity Bible 与逐镜 Shot Deltas。
- **章节音频资产**（`scripts/chapter_audio_build.py`）：只按章节窗口裁出 WAV 并记录来源与 SHA-256；不假设后端支持音频，也不发明音频参数名。用户选定后端后由外部适配层决定是否以及如何绑定。
- **模型中立章节包**（`scripts/chapter_prompt_build.py`）：禁止把逐镜 Scene Master 压成剧情摘要。按时间轴保留故事变化、演员动作、空间调度、物理机位、声画意图和切镜理由，但不写任何平台、模型、模式或 API 字段。
- **样片优先与段落审片**（`scripts/director_review_gate.py`）：选择有代表性与生成难点的一章；记录九项动态维度，以及音乐节奏、情绪推进、切镜关系、视觉语法四项段落证据。审片绑定样片与制作依赖指纹，上游变化需复核；新难点另做针对性检查，单章通过不等于全片通过。
- **章节成片**（`scripts/stitch_chapters.py`）：接收用户所选后端产出的已贴合章节，统一到交付画布并重贴母带；不检查任何平台专属字段。
- **口型边界**：只有用户所选后端的真实提交回执能证明“生成时接收了音频”；没有权威 ASR/音素级验收时，不得声称“逐字口型 PASS”。
- **后端门限**：视频生成后端（普通镜头 / 口型镜头）一律由用户提供，skill 只提问（后端名称、凭证、并发、真钱封顶），**不内置任何后端适配代码与默认值**；未提供后端时交付物止于关 1–6 + 静帧预览成片。
- **凭证四级读取**：会话级 → 项目级 → 用户级 → 环境变量，用户级跨项目永久生效，永远不再问用户要 key。

## 首句启动

用户只需说：「用这首歌做一支 MV，主人公图在附件里。」
然后一次性问清六件事：歌曲、主人公图、比例分辨率、审核模式、算力与并发、**视频生成后端（由用户提供：名称 / 凭证 / 真钱封顶）**。缺图必问一句，不替用户做决定；后端未提供则止步于静帧预览。

## 详细规格（references/）

- `references/visual-workflow-contract.md` — V1.4 数据、执行顺序、迁移与命令
- `references/mv-visual-development-plan.md` — 深度视觉开发设计依据

## ZY 分支调用顺序

1. 按 `vendor/zy-cinematic-realism/SKILL.md` 选择当前任务分支；只做分析时停在分析，不自动生成。
2. 多场景故事读取 Story Visual Development + Source Ledger；逐镜区分来源事实、解释和未接受的视觉提案。
3. 人物图按 likeness + wardrobe 路由；视觉风格参考才进入 Reference Role Router → Medium Router → Dream Decode → Core Visual Rules → Transfer Scope。记录完整 5–8 条规律，每镜选 3–5 条；无视觉参考不制造 Decode Card。
4. 用户要求导演方法时读取 Director Routing、Index、候选矩阵及选中的文件。默认一个导演；明确混合时次要导演只负责一个轴。轻微激活 1–2 个兼容特征，逐镜把方法转成画面决定。
5. 按需调用 Style / Cinematography Cards，解决尚未确定的世界、材质、摄影/光线问题；已经由导演或参考决定的轴不重复叠加卡片。
6. Continuity Bible → Scene Master → 场景母版 → 关键帧 Shot Deltas；多次生成选优遵守预算，使用 Remix 保留成功部分、一次比较一个主要变量。
7. Compiler Priority Gate 保护用户锁与参考职责，分开编译母版、关键帧和视频运动制作包。静帧适配器只管静帧；视频字段由用户所选后端实时契约决定。
8. Prompt Check → 实际图片观察 → 动态/段落审片 → Decode Repair / Result Repair；结构失败返回 Scene Master，其他情况最小修复。换模型只用 Transcode，不重写已锁定场景。

- `references/architecture.md` — 四层架构与数据流
- `references/data-schemas.md` — timeline / storyboard / prompt / ledger 全 schema
- `references/gates-spec.md` — 八道关逐项机检规格
- `references/prompt-framework.md` — 六段式提示词框架与 20 项机检
- `references/zy-cinematic-integration.md` — ZY Cinematic Realism → MV 六段式提示词适配与优先级
- `references/api-backends.md` — 全 API 依赖清单与成本模型
- `vendor/zy-cinematic-realism/` — 造梦师 v2.5.0 原名上游组件（步骤 5 按需加载；CC BY-NC 4.0，作者 ZY / popopo-99，详见目录内 `LICENSE` / `NOTICE.md`）
