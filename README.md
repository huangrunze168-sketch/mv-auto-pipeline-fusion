# mv-auto-pipeline-fusion

一首歌 + 一张图 → 一支口型对得上的音乐 MV。音乐 MV 全自动生成 SOP（Agent Skill）。

十二步全链：从歌词时间轴到成片对齐验收，八道关机检兜底。

## 快速开始

主定义与完整流程见 [SKILL.md](SKILL.md)，版本历史见 [CHANGELOG.md](CHANGELOG.md)。

```bash
# 1. 降级对齐（无 ASR key 的试跑时间轴；正式口型成片需接 ASR 通路）
python scripts/timeline_fallback.py input/song.wav input/lyrics.txt state/timeline.json

# 2. 分镜推导（帧吸附 + 口型节奏 + 景别轮转）
python scripts/storyboard_build.py <project_dir> --fps 24

# 3. 六段式提示词派生（人物图仅锁五官/发型/服装）
python scripts/prompt_build.py <project_dir>

# 4. 硬门禁机检（关1/关5/关6，同时写 gates/*.json + gates/*.html）
python scripts/gate_checks.py gate5 <project_dir>

# 5. 静帧预览成片（无视频 API 通路；参考图保持比例）
python scripts/render_preview.py <project_dir>

# 6. 对齐三验（建议同时传入从成片提取的候选音轨，避免把母带与自身比较）
python scripts/align_verify.py input/song_16k.wav state/storyboard.json state/timeline.json \
  --candidate-wav output/final_16k.wav --out output/verification_report.json

# 7. 运行回归测试
python -m unittest discover -s tests -v
```

## 组件

| 脚本 | 职责 |
|---|---|
| gate_checks.py | 关1/关5(14项)/关6(8项) 硬门禁机检 |
| timeline_fallback.py | 无 ASR key 降级对齐 |
| storyboard_build.py | 分镜推导（帧吸附+口型节奏） |
| prompt_build.py | 六段式提示词派生（人物五官/服装职责锁） |
| duration_fit.py | 时长贴合（帧网格+流复制快路径） |
| align_verify.py | 对齐三验（纯标准库） |
| render_preview.py | 静帧预览成片（等比参考图+模糊填充+Ken Burns+母带重贴） |
| ledger.py | 成本台账（币与真钱分列） |

提示词构造层内置 [ZY Cinematic Realism](vendor/zy-cinematic-realism/SKILL.md) v2.5.0，
通过 [MV 适配规范](references/zy-cinematic-integration.md) 接入 Scene Master、Creative Grammar、连续性与局部修复流程。

## 环境依赖

Python 3.10+（纯标准库）、ffmpeg/ffprobe。**视频生成后端由用户提供，skill 只提问不内置**——未提供后端时流程止步于关 6 + 静帧预览成片（见 `references/api-backends.md` 后端门限）。

## License

本仓库自有代码按 MIT 使用。`vendor/zy-cinematic-realism/` 为 ZY / popopo-99 的第三方作品，采用 **CC BY-NC 4.0**，包含非商业限制；再分发和使用时须保留署名、来源与许可证。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
