+++
date = '2025-08-08T11:36:11+08:00'
draft = false
title = 'Android MediaSession 管理与路由机制'
+++

## 1. 概述

在 Android 系统中，**MediaSessionService** 负责管理所有的媒体会话，并决定哪个应用应当接收媒体按键事件（如耳机线控的播放/暂停）。这一决策机制并非仅仅依赖应用自身的状态上报，而是深度结合了 **AudioService** 的物理发声状态，实现了“所听即所得”的控制体验。

## 2. 核心组件交互

  * **AudioService & AudioPlayerStateMonitor (APSM)**:
      * 作为“事实的来源”。APSM 监听底层 `AudioTrack` 的状态。
      * 维护一个 **UID 历史队列 (`mSortedAudioPlaybackClientUids`)**。这个队列按照“最后开始播放的时间”倒序排列。即使应用暂停播放，只要它未被后续应用挤出或被清理，它依然保留在队列中。
  * **MediaSessionService (MSS)**:
      * 作为系统服务的中枢，协调 Audio 和 Media 组件。
  * **MediaSessionStack**:
      * 作为“决策大脑”。它根据 APSM 提供的 UID 队列，在已注册的 Session 中查找匹配项，确定 **MediaButtonSession**。

## 3. MediaButtonSession 的选择逻辑

系统通过 `MediaSessionStack.updateMediaButtonSessionIfNeeded()` 方法选择接收按键的目标。选择优先级如下：

1.  **Audio 驱动 (最高优先级)**:
      * 系统优先查看 APSM 提供的音频 UID 列表。
      * **正在发声的应用**: 如果列表首位的应用正在发声 (`isActive=true`)，且拥有 Session，它直接成为 MediaButtonSession。
      * **历史活跃的应用 (粘性机制)**: 如果列表首位的应用暂停了 (`isActive=false`)，但它是列表中仅存的或最新的记录，且拥有 Session，它依然保持为 MediaButtonSession。这确保了用户暂停音乐后，按耳机键能恢复该应用的播放。
2.  **Stack 历史兜底 (低优先级)**:
      * 只有当 APSM 的音频列表为空（所有记录都被清理）时，Stack 才会根据 Session 自身的 `PlaybackState` 或 `Active` 状态来选择最近的会话。

## 4. 典型场景流程解析

以下流程描述了用户从 App A 切换到 App B 并进行播放控制的完整生命周期。
![](/ethenslab/images/android-MediaSessionService-updateMediaSession.png)
### 阶段 1: App A 启动与播放

  * App A 创建 Session 并 `setActive(true)`。
  * App A 获取焦点并调用 `AudioTrack.play()`。
  * **关键点**: APSM 检测到 A 发声，将 A 置于列表 `[A]`。Stack 锁定 A 为 MediaButtonSession。

### 阶段 2: 切换到 App B (焦点抢占)

  * App B 申请焦点。系统通知 App A 失去焦点 (Loss)，同时授权 App B。
  * App B 立即调用 `AudioTrack.play()`。
  * **关键点**: APSM 更新列表为 `[B, A]`。Stack 扫描列表，首位是 B，因此 MediaButtonSession **瞬间切换**至 App B。此时 App A 可能还在执行暂停逻辑，但控制权已移交。

### 阶段 3: App A 响应暂停

  * App A 收到焦点丢失回调，执行 `AudioTrack.pause()`。
  * **关键点**: APSM 检测到 A 停止发声。Stack 指示 APSM 执行清理 (`cleanUpAudioPlaybackUids`)。由于 B 是当前的 MediaButtonSession，排在 B 之后且不活跃的 A 会被从音频列表中移除。列表变为 `[B]`。

### 阶段 4: App B 暂停 (粘性保持)

  * App B 用户点击暂停，调用 `AudioTrack.pause()`。
  * **关键点**:
      * 虽然 B 停止了发声，但在 APSM 中，B 依然是“最后活跃的 UID”，因此列表 `[B]` **不会被清空**。
      * Stack 更新时，获取到列表 `[B]`，发现 B 有 Session。尽管 B 处于静音状态，Stack 依然判定 B 为 MediaButtonSession。
      * 这就是为什么音乐暂停后，耳机线控依然有效的底层原因。
