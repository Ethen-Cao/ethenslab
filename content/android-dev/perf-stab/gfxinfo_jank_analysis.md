+++
date = '2025-09-29T11:36:11+08:00'
draft = false
title = '如何分析 dumpsys gfxinfo 卡顿数据'
+++

`adb shell dumpsys gfxinfo <package>` 是 Android 分析 UI 卡顿的第一手数据来源。它输出的统计看起来简单，但里面埋了不少反直觉的坑 —— 最典型的就是「P50=15ms 明明在 16.67ms 帧预算之内，为什么 Janky frames 却高达 97%」。本文用一个真实 Launcher 样本，把这些字段逐一拆开。

## 1. 样本数据

以下是 `dumpsys gfxinfo com.voyah.cockpit.launcher` 的一段实测输出（节选）：

```
UID: 1000
Package: com.voyah.cockpit.launcher
Total frames rendered: 29205
Janky frames: 28441 (97.38%)
50th percentile: 15ms
90th percentile: 16ms
95th percentile: 17ms
99th percentile: 18ms
Number Missed Vsync: 2
Number High input latency: 17
Number Slow UI thread: 2
Number Slow bitmap uploads: 0
Number Slow issue draw commands: 28355
Number Frame deadline missed: 28441
HISTOGRAM: ... 14ms=9672 15ms=10787 16ms=3795 17ms=1125 18ms=560 ...
```

从表面看：
- 总帧数 29205，卡顿帧 28441，**卡顿率 97.38%**
- 但分位数全部压在 15-18ms 之间，看起来「没有长帧」
- 唯一异常的归因是 `Slow issue draw commands: 28355`（与 Janky frames 几乎 1:1 对应）

## 2. 分位数（Percentile）到底是什么

`50th / 90th / 95th / 99th percentile` 是对**每帧耗时分布**的分位统计，而不是平均值：

| 分位数 | 含义                                       | 本例取值 |
|--------|--------------------------------------------|----------|
| P50    | 50% 的帧耗时 ≤ 该值（中位数）              | 15ms     |
| P90    | 90% 的帧耗时 ≤ 该值，只有 10% 的帧更差     | 16ms     |
| P95    | 95% 的帧耗时 ≤ 该值，只有 5% 的帧更差      | 17ms     |
| P99    | 99% 的帧耗时 ≤ 该值，只有 1% 的帧更差      | 18ms     |

**为什么用分位数而不是平均值？**

平均值会被极少数的离群帧严重拉偏 —— 只要有一两帧 650ms 的冻屏，平均数就失去参考意义。分位数能更真实地反映「绝大多数用户实际感受到的体验」，同时 P99/P99.9 又能单独暴露长尾问题。

记住这个阅读顺序：
- **P50 → 典型帧耗时**
- **P90/P95 → 日常最差体验**
- **P99 → 长尾 / 冻屏风险**

## 3. 反直觉现象：P50=15ms 为什么还是 97% Jank

60Hz 屏的 vsync 周期是 16.67ms，P50=15ms 听起来「刚好卡在预算内」，怎么会 97% 都被判为 jank？

根本原因在于 **Android 的 jank 判定规则不是「帧总耗时 > 16.67ms」，而是「是否错过了 deadline」**。

### 3.1 渲染流水线的预算切分

一个 vsync 周期里，**不是整个 16.67ms 都给 App 渲染**。它要在整条流水线上分摊：

```
App UI 线程  →  RenderThread  →  SurfaceFlinger 合成  →  扫描输出显示
     (a)             (b)                 (c)                (d)
```

SurfaceFlinger 必须在下一个 vsync 到来之前拿到合成好的 buffer，所以留给 App 侧（a+b）的**实际预算通常只有 ~11-13ms**，剩下 3-5ms 必须留给合成器和扫描输出。

### 3.2 Janky frames == Frame deadline missed

样本里这两个字段的值完全相等（都是 28441）：

```
Janky frames: 28441 (97.38%)
Number Frame deadline missed: 28441
```

这不是巧合 —— `Janky frames` 在 gfxinfo 里的定义就是「错过了预期 present 时间的帧」。错过 deadline ≠ 总耗时 > 一个完整 vsync，只要 App 侧那一棒跑超了分配给它的那部分预算，就算没满 16.67ms 也会被判 jank。

### 3.3 用「接力赛」直观理解

把一帧渲染想象成 4 x 4ms 的接力：
- 你第一棒（UI+RenderThread）跑了 15ms
- 合成器需要你在 ~11ms 内交棒
- 虽然你总耗时还没满 16.67ms，但**下一棒已经被迫迟到**
- 这一帧就会被标记成 jank

这就是本例 97% 卡顿帧的真相：**不是偶发长帧，而是持续超预算**。

## 4. HISTOGRAM 告诉你什么

HISTOGRAM 列出每个毫秒桶里有多少帧，信息密度比分位数更大：

```
... 12ms=368 13ms=2627 14ms=9672 15ms=10787 16ms=3795 17ms=1125 18ms=560 ...
```

本例 **14-16ms 三个桶合计约 24254 帧（~83%）**，典型的「vsync 边缘对齐」形态：

- 系统在等 vsync 信号释放下一帧，大量帧会「对齐」到 vsync 周期边缘
- 长尾极短（P99=18ms），没有灾难性长帧
- 同时 HISTOGRAM 末尾还有 `650ms=1` 级别的离群点 —— 这是真正需要单独追查的冻屏

**看 HISTOGRAM 的三个切入点：**
1. **主峰位置**：落在 8-10ms 说明管线健康，落在 14-16ms 是边缘踩线，落在 >16ms 是直接掉帧
2. **长尾分布**：关注 >32ms 的桶，这是用户会主观感知到「一顿」的帧
3. **离群点**：>100ms 的单帧都要单独排查，往往对应 ANR、GC、磁盘同步等阻塞事件

## 5. 归因字段怎么读

gfxinfo 会把 jank 进一步拆成几个 Number 字段，**这些字段不互斥，一帧可以命中多个桶**，但通过对比可以快速定位瓶颈环节：

| 字段                              | 触发条件                                       | 常见根因                             |
|-----------------------------------|------------------------------------------------|--------------------------------------|
| `Number Missed Vsync`             | UI 线程没赶上 vsync 触发点                     | 主线程阻塞、消息泵堆积               |
| `Number High input latency`       | 输入事件从到达到被处理的延迟过大               | 输入分发链路慢、焦点窗口切换开销     |
| `Number Slow UI thread`           | UI 线程本身 `doFrame` 太慢                     | 复杂布局 measure/layout、过度绘制    |
| `Number Slow bitmap uploads`      | 位图上传 GPU 纹理太慢                          | 大图、频繁纹理重建、texture cache 抖动 |
| `Number Slow issue draw commands` | RenderThread 下发 GPU 命令太慢                 | display list 过大、overdraw、复杂 shader |
| `Number Frame deadline missed`    | 总 deadline 未达成（几乎等同于 Janky frames）  | 上面任何一个子项累加的结果           |

本例中 `Slow issue draw commands = 28355`，和 Janky frames 28441 几乎 1:1，说明瓶颈**集中在 RenderThread 的 GPU 命令下发阶段**。UI 线程本身（Slow UI thread = 2）和位图上传（Slow bitmap uploads = 0）都是健康的，问题不在 measure/layout，也不在纹理管理。

## 6. 综合诊断结论

把上面所有观察串起来：

- **不是偶发掉帧**：P99=18ms，长尾极短，没有剧烈抖动
- **而是系统性踩线**：P50=15ms 持续逼近预算上限，97% 的帧都错过 deadline
- **归因明确**：`Slow issue draw commands` 独占绝大多数 jank（28355/28441 ≈ 99.7%）

一句话描述：**Launcher 的每一帧 RenderThread 在 GPU 命令下发阶段都跑超了分配给 App 的那段预算，虽然没满一个完整 vsync，但挤压了合成器的时间窗口，触发系统性 jank**。

## 7. 下一步排查工具链

gfxinfo 只能告诉你「哪一棒有问题」，不能告诉你「哪一行代码有问题」。进一步定位需要配合其他工具：

### 7.1 量化合成器延迟

```bash
adb shell dumpsys SurfaceFlinger --latency <window_name>
```

输出 128 帧的 `desiredPresentTime / actualPresentTime / frameReadyTime`，可以精确看到每一棒在流水线上的实际耗时，印证 gfxinfo 的归因。

### 7.2 可视化 overdraw 与 dirty region

```bash
adb shell setprop debug.hwui.overdraw show
adb shell setprop debug.hwui.show_dirty_regions true
```

开启后屏幕会用颜色叠加显示过度绘制（overdraw）和脏区范围。如果 Slow issue draw commands 高，绝大多数情况是 overdraw 超过 3x 或无效重绘全屏。

### 7.3 Perfetto / Systrace 抓帧级 trace

```bash
adb shell perfetto -o /data/misc/perfetto-traces/trace -t 10s \
    -b 32mb sched freq gfx view wm am input
```

抓一段 10 秒的 trace，导入 ui.perfetto.dev，在 RenderThread 的 `DrawFrame` slice 里逐帧展开 GPU 命令，找到耗时最长的那个 `issueDraw` 调用点。这是从 gfxinfo 的「统计归因」走到「代码级根因」的最关键一步。

### 7.4 GPU profiling（可选）

```bash
adb shell setprop debug.hwui.profile true
```

会在屏幕底部绘制每帧的 GPU 耗时条形图，绿色是 measure/layout、蓝色是 draw、红色是 GPU execute。可用于现场快速判断瓶颈在 CPU 端还是 GPU 端。

## 8. 速查表

| 现象                              | 最可能的根因                              | 下一步工具                  |
|-----------------------------------|-------------------------------------------|-----------------------------|
| P50 < 10ms, Jank < 5%             | 健康                                       | —                           |
| P50=14-16ms, Jank > 80%           | 系统性踩线，Slow issue draw 归因主导       | overdraw 检查 + Perfetto    |
| P50 正常但 P99 > 100ms            | 长尾冻屏（GC / IO / ANR）                  | Systrace 看主线程阻塞       |
| Slow UI thread 占多数             | measure/layout 过重或主线程 IO             | TraceView / Perfetto CPU    |
| Missed Vsync 占多数               | Choreographer 消息堆积                     | 主线程消息泵 trace          |
| Slow bitmap uploads 占多数        | 大图 / 纹理抖动                            | HWUI texture cache dump     |

## 9. 关键陷阱

最后回到本文开头那个问题 —— **分位数看起来健康时，绝对不能直接下结论说「流畅」**。一定要同时看：

1. `Janky frames` 百分比（最终结论指标）
2. `Number Frame deadline missed` 与 Janky frames 的一致性（确认 jank 定义）
3. 具体的 `Number Slow *` 归因字段（定位瓶颈环节）
4. `HISTOGRAM` 的主峰位置（验证是否贴着 vsync 边缘）

只看 P50/P90 会让你错过「**看似流畅但持续卡顿**」这类最隐蔽也最常见的性能病 —— 它不会在任何单帧上显得特别糟糕，但用户长时间使用会觉得「就是不跟手」。这类问题在车机 Launcher、桌面启动器、全局动画密集的 UI 上尤其常见。
