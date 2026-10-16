# 本地有声审片工作台

真实本地播放器支持原曲、对标与候选片，歌词跳转、逐行起止和演唱者复核、带时间码的逐镜观察、设计及导演序列草稿编辑。播放一个媒体时暂停其他播放器，避免串音。视频保持自身原音，不为无声片伪造原生音轨。

此功能补齐听看和记录入口，不赋予语言模型听觉或完整动态理解能力。加载成功、播放事件、观察声明不能证明完整审片，也不自动认证时间、口型、艺术或交付。

## 使用

```powershell
python scripts/review_workbench.py build PROJECT NEW_BUNDLE --media CANDIDATE.mp4 --reference BENCHMARK.mp4
python scripts/review_workbench.py serve NEW_BUNDLE --port 8765
```

打开 `http://127.0.0.1:8765/`。服务只监听本机，只读，无写入、审批或后端调用接口。支持单区间 HTTP Range 以便拖动和跳转，不列目录、不跟随目录外链接。编码不被浏览器支持时显示错误，不能据此批准。原曲和视频时间分别显示，未实现自动同步对齐。

构建复制实际媒体，绑定原文件和副本 SHA，不转码、不变速、不覆盖正式项目。必须使用新目录保留旧会话。包内含原媒体与本地路径，仅本地使用，不自动上传。

逐行修改候选时间、演唱者和边界观察。逐镜可记录主唱口型、DJ搓碟声画、群众反应及镜长、正反打轴线、运镜路径、光色美术和情绪推进。

设计编辑器读取已有正式文件，缺失时给未填草稿，不按镜数或时长制造创作：

- development：导演提案、来源、参考职责、空间、物理灯光与材质、ZY路由。
- story_plan：八部门逐镜交接及 Continuity Bible。
- sequence_direction：来源、窗口、信息、机位、人物路径、切点、光色、美术、表演。
- music_structure：真实听辨的段落、cue和情绪；能量不等于音乐语义。
- style：用户风格锁；草稿不能擅自转成 accepted。

导出按钮下载全部歌词、观察、播放事件和设计的待核 JSON。离开前先导出；当前无浏览器持久保存，不自动写项目。随后运行：

```powershell
python scripts/review_workbench.py import-draft PROJECT NEW_BUNDLE EXPORTED_DRAFT.json
```

导入核验项目、会话、输入版本、媒体副本、歌词身份及有限且位于原曲内的时间；原子落盘前再次比较版本。原项目新增或改变设计使旧会话失效。新记录保存到 `state/review_workbench/`，独立随机文件名保留历史。

外层始终 `decision=pending`、`agent_inspected=false`、`dynamic_verified=false`、`artistic_approval=false`。此入口拒绝 approve，不写正式 timeline、development、sequence_direction 或 director_review，不修改既有审批。采纳草稿须走原正式重建、执行和重审入口，禁止直接改名冒充生产文件。
