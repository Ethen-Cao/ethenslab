+++
date = '2026-05-09T10:00:00+08:00'
draft = false
title = 'Android 黑屏检测方法对比'
+++

「黑屏」在车机 / 平板 / 智能终端上是一类高优先级故障，但它并不是一个单一根因——可能是 SurfaceFlinger 卡死、HWC HAL 异常、GPU hang、Window 层级错乱、KeyEvent / Display 状态被异常切到 OFF，也可能只是上层应用确实在画一帧黑色。检测方案的好坏，关键不在「能不能拿到一张图判断它是黑的」，而在**能否在最早的症状链上、用尽量低的代价、覆盖尽量多的真异常并排除尽量多的真黑场景**。

本文整理一套从「症状最早 / 成本最低」到「症状最末 / 成本最高」的检测方法，分别说明每种方法**检测的是什么**、**能识别哪些黑屏类型**、**会漏报哪些**、以及**典型实现成本**。

## 0. 先把「黑屏」分类

不要把所有「屏幕变黑」都当成异常。常见类别：

| 类别 | 是否异常 | 典型场景 |
| --- | --- | --- |
| **A. 渲染流水线停摆** | 是 | SurfaceFlinger 死锁 / GPU hang / HWC HAL crash |
| **B. Window 系统异常** | 是 | system_server WMS 死锁、focus window 丢失、Activity stack 错乱 |
| **C. 主屏 Display 异常** | 是 | DisplayManager 异常 OFF、底层 DPU/DSI 链路掉电、HDMI/LVDS 链路丢失 |
| **D. 应用主动绘黑** | 否 | 启动 splash、夜间模式、隐私遮罩、转场过渡 |
| **E. 受保护内容截屏** | 否 | DRM / Widevine 视频帧在 screenshot 路径返回黑 |
| **F. 用户主动息屏** | 否 | `Display.STATE_OFF` / DOZE |
| **G. 全屏黑色业务内容** | 否 | 黑底视频、电影开场、黑色启动画面 |

任何一个检测方案都要回答两个问题：「能识别 A/B/C 吗？」「能区分 D/E/F/G 吗？」

---

## 1. Choreographer 帧节拍监控（推荐主信号）

### 检测的是什么
应用进程内 UI 线程是否还在按 VSYNC 节拍获得 `doFrame` 回调。在 `Choreographer.FrameCallback#doFrame(long frameTimeNanos)` 内记录上一帧时间戳，超过阈值（如 1 秒）未回调即异常。

### 能识别 / 不能识别
- 能识别：A 类（SurfaceFlinger 不再下发 VSYNC 或 UI 线程被卡死）、B 类的一部分（焦点窗口所在进程的 UI 卡死）。
- 不能识别：C 类（Display 链路异常但帧节拍仍在）、D/E/G（业务正常）。
- 误报极少：DOZE / 息屏期间系统会暂停 VSYNC，需要前置过滤 `Display.getState()`。

### 实现成本
- 单次回调开销 < 1μs。
- 不调用任何 hidden API，不需要系统签名。
- 不会唤醒 SurfaceFlinger 渲染流水线（自身就是渲染回调的一部分）。

### 局限
- **只能检测自己进程**。要做全系统监测，需要在 Launcher / SystemUI / 关键车机应用中各埋一个，或者作为 Library 注入。
- 无法识别「帧节拍正常但所有帧都画了纯黑」的极少数场景。

---

## 2. SurfaceFlinger 帧统计（系统级帧节拍）

### 检测的是什么
通过 `dumpsys SurfaceFlinger --latency <window>` 或 `dumpsys SurfaceFlinger --list` 配合 `--latency-clear`，定期取出某 layer 的 frameNumber / present timestamp，判断其是否在递增。

也可以读 `/sys/class/drm/card0/device/.../vblank_counter` 这种 vendor 暴露的 sysfs 节点（如可用）。

### 能识别 / 不能识别
- 能识别：A 类（合成停摆）、C 类的一部分（vblank 不再到来）。
- 不能识别：B 类的纯 WMS/AMS 死锁（合成可能仍在按缓存帧出）；D/E/G 不报。

### 实现成本
- `dumpsys SurfaceFlinger --latency` 单次调用 1–5ms。
- 5–10 秒一次的轮询完全可接受。
- 需要 `DUMP` 权限（系统应用 / shell 用户）。

### 局限
- 解析文本不稳定，不同 Android 版本字段格式略有差异。
- vendor 定制（如直显 / DPU bypass）可能让 frameNumber 不再增长但屏幕实际显示正常。

---

## 3. DisplayManager / PowerManager 状态监听

### 检测的是什么
注册 `DisplayManager.DisplayListener.onDisplayChanged` 与 `PowerManager` 的息屏广播（`ACTION_SCREEN_OFF` / `ACTION_SCREEN_ON`），把 `Display.getState()` 与 UI 应该显示的状态做交叉。

### 能识别 / 不能识别
- 能识别：C 类（Display 状态被异常切到 OFF / UNKNOWN，例如 DPU 链路掉电）。
- 主要作用是**前置过滤**：在所有截屏 / 像素判断方案前先确认 `STATE_ON`，否则全部跳过。
- 不能单独判定「黑屏异常」：因为很多 A/B 类故障下 Display 仍报告 STATE_ON。

### 实现成本
- 事件驱动，零轮询开销。
- 公开 API，无需特殊权限。

### 局限
- 单独使用价值有限，是配套手段而非主探测。

---

## 4. WindowManager / Activity 焦点窗口检查

### 检测的是什么
周期性 `dumpsys window` / `dumpsys activity top`，确认：
- `mFocusedWindow` 不为空
- 顶层 Activity 处于 `RESUMED` 状态
- focused window 的 frame 是否覆盖整个 Display

### 能识别 / 不能识别
- 能识别：B 类（focus 丢失、所有 Window 都不可见、ActivityStack 错乱）。
- 不能识别：A/C 类（窗口结构正常但渲染或显示异常）。

### 实现成本
- `dumpsys` 单次几毫秒。
- 10–30 秒一次轮询足够。

### 局限
- 文本解析脆弱，跨 Android 版本需要适配。
- 黑屏可能在窗口拓扑完全正常的情况下发生。

---

## 5. SurfaceFlinger / system_server Watchdog 事件订阅

### 检测的是什么
Android 平台自身在 `system_server` 与 `SurfaceFlinger` 中已经有 `Watchdog` 线程，监控关键线程的 looper 心跳，超时（默认 60 秒）会主动重启 system_server。

vendor 通常也在 HWC / DPU HAL 中埋了类似 watchdog。

可以通过：
- 监听 `dropbox` 中 `system_server_watchdog` / `system_app_anr` / `SYSTEM_TOMBSTONE` 事件
- 解析 `/data/anr/` 目录新增文件
- vendor 自定义 binder 接口

### 能识别 / 不能识别
- 能识别：A/B 类的最终态（已经触发平台自救）。
- 触发时机偏晚：watchdog 默认 60 秒才报，"秒级检测"指标达不到。

### 实现成本
- 几乎为零（被动接收）。
- 需要系统签名 / shell。

### 局限
- 是「事后告警」而非「早期检测」，作为最终兜底信号使用。

---

## 6. 像素截图判定（兜底，不建议作为主信号）

### 检测的是什么
通过 `SurfaceControl.captureDisplay(...)` / `SurfaceControl.screenshot(...)`（Android 11+ 用 `ScreenCaptureListener` 异步形式）拿一张主屏帧，下采样后逐像素判断「亮度方差 < ε 且大部分像素接近 RGB(0,0,0)」。

### 能识别 / 不能识别
- 能识别：A/B/C 类中**最终表现为画面全黑**的情形。
- **天然漏报**：冻屏（最后一帧定格）、灰屏、单色非黑屏、花屏、局部黑——全黑像素比例打不到 99% 阈值。
- **天然误报**：D（splash 黑底、夜间模式）、E（DRM 内容截屏被强制黑）、F（息屏）、G（黑底视频内容）。
- 必须配合：Display state 过滤 + DRM / 媒体播放状态过滤 + 冻屏检测（与上一帧像素差全 0 也异常） + 单色检测（亮度方差 < ε）。

### 实现成本（被低估的点）
- **目标分辨率不影响合成成本**。SurfaceFlinger 仍要按源分辨率合成所有 layer，目标 100×30 只影响最后一次缩放写出。中端 SoC 单次 30–80ms。
- **会把 SurfaceFlinger 从 idle 唤醒**。车机静止 UI 下 HWC 常走「layer 不变直接复用前一帧」的快速路径，深度 idle；强制截屏会持续把它拽出 idle，**功耗与温度上升**。
- 每 2 秒一次 = 每天 43 200 次 GraphicBuffer 分配 + 跨进程传递。不是「零压力」。
- `SurfaceControl` 是 `@hide`，反射调用受 hidden API blocklist 限制（Android 9+），需要系统签名 + `system/priv-app` 安装才稳定。
- API 签名跨版本不一致：Android 7 / 8–10 / 11+ 三套，反射方案维护成本高且失效是静默的。

### 推荐用法
**降级兜底**而非常态轮询：

```
帧节拍正常        → 不动作（99.9% 时间）
帧节拍停摆 > 2 秒 → 一次性截屏验证
                   ├─ 全黑/单色/冻屏 → 升级告警
                   └─ 内容正常       → 算误报，仅记录
```

判据上不要只看「RGB=0 占比 > 99%」：
1. 取屏幕固定 16~32 个网格采样点而非全像素遍历。
2. 加「亮度方差 < ε」识别灰屏/单色屏。
3. 加「与上一帧像素差 = 0」识别冻屏。
4. 前置 `PowerManager.isInteractive() && Display.getState()==STATE_ON`，并避开 DRM / 媒体播放期。

---

## 7. Perfetto / atrace 长 trace 离线分析

### 检测的是什么
线下抓 Perfetto trace，关注 `gfx`、`view`、`sf`、`hwc`、`sched`、`binder` category，看 SurfaceFlinger commit / present 是否停止、UI 线程是否被长时间阻塞、Binder 调用栈在哪个进程卡死。

### 能识别 / 不能识别
- 几乎所有黑屏类故障都能在 trace 中重现根因。
- 但是**线下 / 复现工具**，不能做线上实时检测。

### 实现成本
- 离线分析，单次 trace 5–30 秒，几十 MB。
- 详见本目录 [Perfetto](perfetto.md) 一文。

### 局限
- 不是线上探测方案。作为发生黑屏后定位根因的工具。

---

## 方案矩阵

| 方法 | 类别覆盖 | 单次开销 | 检测延迟 | 误报 | 漏报 | 推荐角色 |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Choreographer 帧节拍 | A,部分 B | < 1μs | 秒级 | 极低 | 部分 C | **主信号** |
| 2. SurfaceFlinger 帧统计 | A,部分 C | 1–5ms | 秒级 | 低 | B 部分 | **主信号（系统级）** |
| 3. DisplayManager 状态 | C | 0（事件） | 即时 | 0 | A,B | **前置过滤** |
| 4. Window 焦点检查 | B | 几 ms | 10–30s | 低 | A,C | 辅助 |
| 5. 平台 Watchdog 订阅 | A,B 终态 | 0 | 60s+ | 0 | C | 兜底告警 |
| 6. 像素截图判定 | A,B,C 全黑表现 | 30–80ms + idle 唤醒 | 秒级 | **高** | 灰/冻/单色屏 | **降级二次确认** |
| 7. Perfetto trace | 全部 | 离线 | — | — | — | 根因定位 |

---

## 推荐组合（线上方案）

```text
[前置]
  DisplayManager 状态监听  ── STATE_OFF / DOZE → 全链路跳过
  KeyguardManager / 媒体播放状态 ── DRM / 全屏视频 → 截屏链路跳过

[主探测]
  Choreographer 帧节拍（关键应用：Launcher / SystemUI / 仪表）
  SurfaceFlinger frameNumber 轮询（系统级，5–10s/次）

[二次确认]
  上述任一停摆 ≥ 阈值时间 → 触发一次截屏 + 多元判据（黑/灰/冻/单色）

[兜底告警]
  订阅 system_server / SurfaceFlinger Watchdog dropbox 事件

[根因定位]
  Perfetto trace 现场或 ringbuffer 模式常驻
```

这样的组合在 99.9% 的时间里**几乎零开销**，只在已经有可疑信号时才付出截屏成本，秒级检出延迟可达成，且对系统功耗 / SurfaceFlinger idle 路径基本无侵扰。

---

## 一句话总结

> 「黑屏检测」的难点不是拿到一张黑图，而是在**渲染症状链最早的一段**用最低代价捕捉异常、并排除大量正常的全黑场景。**主探测放在帧节拍信号、截屏只做二次确认**，是成本与覆盖率最优的折中。
