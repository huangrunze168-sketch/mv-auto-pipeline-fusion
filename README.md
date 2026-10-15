# mv-auto-pipeline-fusion

音乐 MV 的设计、提示词编译、门禁与本地剪辑工作流（Agent Skill）。后端由用户选择，动态审美与口型需要真实审片，不保证无人参与自动产出合格成片。

当前验证范围和未完成项见[当前验收状态](references/current-validation-status.md)。本地契约/媒体测试不是电影感证明；本轮用户否定的生成与返剪实验不作为成功范例。运行媒体、凭证和具体项目设计不随代码发布。

十二步业务流程，机器/人工/外部职责见 [生产契约](references/production-hardening.md)，真实门禁入口见 [registry](references/gate-registry.json)。`gate_checks.py` 实际提供gate1/gate5/gate6，检查数从报告读取。

## 快速开始

主定义与完整流程见 [SKILL.md](SKILL.md)，版本历史见 [CHANGELOG.md](CHANGELOG.md)。

V1.4.1 的数据填写、完整执行顺序与旧项目迁移见 [视觉开发执行契约](references/visual-workflow-contract.md)。逐镜导演构造见 [导演级 Scene Master 契约](references/director-scene-master.md)。先完成 ZY 的故事、导演、参考视觉和连续性记录，再生成场景母版、关键帧与视频；后端由用户选择。

```bash
# 1. 降级对齐（无 ASR key 的试跑时间轴；正式口型成片需接 ASR 通路）
python scripts/timeline_fallback.py input/song_16k.wav input/lyrics.txt state/timeline.json --master-audio input/song.mp3

# 2. 无视觉编辑方案时只输出时间骨架，不自动配景别与口型
python scripts/storyboard_build.py <project_dir> --fps 24

# 3. 调用 ZY 编写 development.json、visual_edit_plan.json、story_plan.json
python scripts/storyboard_build.py <project_dir> --fps 24
python scripts/visual_development.py <project_dir>
python scripts/crew_pipeline.py <project_dir>
# 可选：用合法标注构建的电影语法画像做统计审计（不下载正片）
python scripts/film_grammar_corpus.py audit <project_dir> <profile.json>
python scripts/prompt_build.py <project_dir>

# 4. 硬门禁机检（关1/关5/关6，同时写 gates/*.json + gates/*.html）
python scripts/gate_checks.py gate5 <project_dir>
python scripts/gate_checks.py gate6 <project_dir>

# 5. 多场景关键帧预览成片（优先 input/scene_*.png；无场景图才回退人物参考图）
# 用户未选择视频后端时，正式流程在这里停止。
python scripts/render_preview.py <project_dir>

# 用户所选静帧后端产出图片后，实际审查并用 visual_assets.py 登记母版/关键帧。
# visual_revision.py 用于 Remix 单变量比较与局部修复契约检查，详见执行契约。

# 6. 用户选定视频后端并核验真实契约后，显式传入该后端的时长上限
python scripts/chapter_plan_build.py <project_dir> --max-duration <backend_limit>

# 7. 准备模型中立章节资产、全能参考蓝图与导演制作包；generation_manifest.json 默认不可提交
python scripts/chapter_audio_build.py <project_dir>
python scripts/chapter_prompt_build.py <project_dir>

# 首次视频生成前：生成完整音乐分镜预演，完整观看并填写四维度/时间码证据
python scripts/animatic_review.py init <project_dir> --media output/mv_preview.mp4
python scripts/animatic_review.py check <project_dir>
# 若设计/预演改变：先撤销，重做预演，再刷新待审记录并完整重审
# python scripts/animatic_review.py invalidate <project_dir>
# python scripts/animatic_review.py refresh <project_dir> --media output/mv_preview.mp4

# 8. 外部适配层按真实 schema 只提交代表样片；完整观看后填写并检查审片记录
python scripts/director_review_gate.py init <project_dir>
python scripts/director_review_gate.py check <project_dir>
python scripts/submission_contract.py <submission.json> --project-dir <project_dir>

# 9. 审片批准后，外部适配层才可生成其余章节；每章先执行 duration_fit.py

# 10. 先逐章审批所选的真实素材版本，再做正式选段渲染
# 每章分别初始化并完成动态审片；init不自动批准
python scripts/director_review_gate.py init <project_dir> --chapter CH01
python scripts/director_review_gate.py check <project_dir> --chapter CH01
python scripts/edit_assemble.py <project_dir> --render
# 正式选段已渲染；输出全片候选预览，不重写edit_assembly
python scripts/stitch_chapters.py <project_dir> --allow-unreviewed-preview \
  --output-name sequence_preview.mp4 --width 1280 --height 720
# 完整观看该候选，再填写并检查全序列审片；批准后剪辑清单冻结
python scripts/director_review_gate.py init <project_dir> --chapter full_sequence
python scripts/director_review_gate.py check <project_dir> --chapter full_sequence
python scripts/stitch_chapters.py <project_dir> --width 1280 --height 720
python scripts/delivery_state.py check <project_dir> --output-name final_mv.mp4

# 如需修改已批准剪辑，显式撤销后修改，刷新待审记录并重新完整审片
# python scripts/director_review_gate.py invalidate <project_dir> --chapter full_sequence
# python scripts/edit_assemble.py <project_dir> --render
# python scripts/director_review_gate.py refresh <project_dir> --chapter full_sequence

# 未审片只能显式输出技术预览，且文件名必须包含 preview
python scripts/edit_assemble.py <project_dir> --render --technical-preview
python scripts/stitch_chapters.py <project_dir> --allow-unreviewed-preview \
  --output-name technical_preview.mp4

# 11. 对齐三验（建议同时传入从成片提取的候选音轨，避免把母带与自身比较）
python scripts/align_verify.py input/song_16k.wav state/storyboard.json state/timeline.json \
  --candidate-wav output/final_16k.wav --candidate-video output/final_mv.mp4 \
  --out output/verification_report.json

# 12. 运行回归测试
python -m unittest discover -s tests -v
```

## 组件

| 脚本 | 职责 |
|---|---|
| gate_checks.py | 关1/关5/关6机检，检查数由报告给出；关1区分结构通过与production |
| timeline_fallback.py | 无 ASR key 降级对齐 |
| storyboard_build.py | 音乐引用驱动的视觉分镜；无方案只输出时间骨架，不猜副歌或轮换景别 |
| prompt_build.py | 从 ZY Scene Master / Continuity Bible 编译提示词；缺少故事方案时阻断 |
| chapter_plan_build.py | 按视频模型最长时长聚合连续镜头，保留 Continuity Bible 与 Shot Deltas |
| chapter_audio_build.py | 按章节窗口裁出模型中立音频资产，记录来源窗口与 SHA-256，不假设后端字段 |
| chapter_prompt_build.py | 将 ZY Scene Master、Continuity Bible、Shot Deltas 编译为模型中立章节制作包 |
| omni_reference.py | 构建并机检人物/关键帧/音频的全能参考职责、保留/排除项与逐镜时间轴；不调用后端 |
| director_review_gate.py | 强制完整观看单章动态样片并分别记录技术检查与九项导演检查；批准前阻断批量生成/正式合成 |
| animatic_review.py | 视频提交前的完整音乐分镜预演批准；不批准运动、表演或口型 |
| review_dependencies.py | 公共锁＋本章直接依赖的审片投影；全片绑定整条序列 |
| chapter_admission.py | 正式选段前核对素材章节/镜头归属、批准版本与实际审片文件；禁止仅reviewed字符串准入 |
| stitch_chapters.py | 拼接任意用户所选后端的章节产物、修正交付画布并贴回同源母带 |
| delivery_state.py | 独立记录已输出、技术验收、可交付及版本失效；不自动登记用户接收 |
| edit_assemble.py | 先在独立版本目录生成全部选段，核验输入/审批版本后发布清单；失败保留旧成功片段 |
| duration_fit.py | 时长贴合（帧网格+流复制快路径） |
| align_verify.py | 对齐三验（纯标准库） |
| render_preview.py | 多场景关键帧预览（章节分配+等比画面+Ken Burns+母带重贴） |
| ledger.py | 成本台账（币与真钱分列） |
| audio_master.py | 分离原始母带与分析副本，保留音轨采样率和声道，选择流复制或无损编码 |
| restore_master_audio.py | 复用已有视频，另存原始母带音轨版本，并校验音频与画面载荷 SHA-256 |
| visual_development.py | 故事来源、导演路由、参考权限、连续性和动作设计契约检查 |
| crew_pipeline.py | 八部门剧组交接与视听语言审计：重复机位、30/180度、动线、地理、节奏、美术和灯光 |
| film_grammar_corpus.py | 将合法电影镜头标注聚合为匿名统计画像，并审计平均镜长、景别转移和运镜变化；不保存电影画面 |
| visual_assets.py | 场景母版和分镜关键帧登记、版本与依赖失效检查 |
| visual_revision.py | Remix 单轴变化与 Result Repair 定向修复契约检查 |

提示词构造层内置 [ZY Cinematic Realism](vendor/zy-cinematic-realism/SKILL.md) v2.5.0，
通过 [MV 适配规范](references/zy-cinematic-integration.md) 接入 Story Visual Development、Story Source Ledger、
Scene Master、Continuity Bible、Shot Delta 与局部修复流程。缺少 `state/story_plan.json` 时只保留
`timing_only` 时间骨架，禁止静默退化成歌词动作模板。

## 环境依赖

交付音轨必须来自 `timeline.master_audio` 的用户原始母带。`source_audio` 可为 ASR/对齐用的 16 kHz 副本，但不得用于交付。合成直接复制可承载的原始 MP3/AAC 音频流；PCM/FLAC 等转为 ALAC 无损音轨。原采样率和声道保留，生成片段音轨不进入母带重贴版。音轨对齐 PASS 仅代表时间一致，不代表音质一致。

Python 3.10+（纯标准库）、ffmpeg/ffprobe。**视频生成后端由用户提供，skill 只提问不内置**；但所选模型必须通过多模态全能参考能力门禁，普通文生视频、单首帧图生视频和仅角色库模式均不可用于正式生成。未提供合格后端时流程止步于关 6 + 静帧预览成片（见 `references/api-backends.md` 后端门限）。

## License

本仓库自有代码按 MIT 使用。`vendor/zy-cinematic-realism/` 为 ZY / popopo-99 的第三方作品，采用 **CC BY-NC 4.0**，包含非商业限制；再分发和使用时须保留署名、来源与许可证。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
