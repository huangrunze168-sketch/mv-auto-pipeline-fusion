# 后端无关的本地转场

## dissolve：已接入选段和合成

在出镜镜头crew.editing中指定transition_type=dissolve和正整数transition_duration_frames。edit_assemble保留选段out_frame后的真实后延帧，下一镜音乐窗口不移动；stitch_chapters调用transition_render.join_picture从切点起叠化。后延不足、末镜叠化、叠化超过下一镜窗口拒绝，不自动补冻结帧或缩短音乐时间轴。修改分镜或清单仍须重新审片。

## J_cut/L_cut：已实现独立声音轨，未接入正式母带混音

命令：python scripts/transition_render.py audio_plan.json diegetic.wav。

audio_plan包括fps、sample_rate、channels以及entries。每个entry要求frames、audio_in_frame、audio_path、audio_sha256；出镜audio_transition可声明type=J_cut或L_cut及duration_frames。J_cut提前下一镜声音、L_cut延续上一镜声音，读取真实前/后延声音，不改变总时长。输出为独立PCM24同期声/音效轨，拒绝覆盖现存文件。

这不是修改演唱口型驱动音频或音乐母带。正式MV自动混音及交付载荷验收尚未接入该轨，因此现有正式入口对J_cut/L_cut保持阻断，不能宣称全链路声音转场完成。独立声音轨可供技术审片或外部剪辑使用。

真实本地测试验证红/蓝混合帧、96帧时间轴、440/880Hz声音提前/延后、前延不足及旧文件保护；不证明艺术设计或供应商效果。
