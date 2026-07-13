# Monkey dmabuf and black screen monitor design

## 背景

现场黑屏发生在长时间 Monkey 压测过程中。已有日志显示，黑屏前后存在以下特征：

- `com.android.systemui`、`surfaceflinger` 持有大量 dmabuf 引用。
- `surfaceflinger` 同时出现大量 `sync_file` fd。
- 系统出现低内存、低 swap、LMK、Binder `No space left on device`、large transaction。
- AMS/WMS 认为前台 Activity 和窗口可见，但 SurfaceFlinger 最终合成列表没有有效应用层，屏幕截图为黑屏。

本设计目标是写一个 Python 复现控制脚本：启动 Monkey 后持续轻量采样；一旦满足明确异常条件，先抓关键现场，再停止 Monkey；不采集 bugreport，不采集 perfetto。

## 目标

1. 启动并管理 Monkey，完整记录 Monkey 命令、seed、开始时间、停止原因。
2. 每秒监控 `system_server`、`com.android.systemui`、`surfaceflinger` 的 dmabuf/fd/sync_file 状态。
3. 每秒监控系统总 dmabuf、内存、swap、CMA、LMK/Binder/图形错误日志。
4. 每 10 秒判断 Android 是否进入“AMS/WMS 可见但 SF 无有效应用层”的黑屏状态。
5. 触发停止条件后，停止 Monkey 前后各抓一轮轻量现场。
6. 避免 `kill -6` 这类会制造额外 tombstone 的停止方式。

## 非目标

1. 不抓 bugreport。
2. 不抓 perfetto。
3. 不直接判定代码级 root cause；脚本负责保存可证明现场。
4. 不用一次性重 dump 做每秒采样，避免采样本身放大系统压力。

## 进程范围

固定监控以下进程：

- `system_server`
- `com.android.systemui`
- `surfaceflinger`

每秒根据进程名重新确认 pid。若 pid 发生变化，必须记录事件，并立即抓一次现场快照。特别是 `com.android.systemui` pid 变化，是判断 dmabuf 是否由 SystemUI 引用释放的重要证据。

## 采样数据

### 常规每秒采样

每秒采集并写入结构化日志，例如 JSONL：

- 时间戳，建议同时记录 host 时间和 device 时间。
- Monkey pid 和 Monkey 是否仍在运行。
- 三个目标进程：
  - pid
  - total fd count
  - dmabuf fd count
  - dmabuf bytes
  - sync_file fd count
  - fd 上限或 `FDSize`
  - pid 是否发生变化
- 系统：
  - total dmabuf bytes
  - `MemAvailable`
  - `SwapFree`
  - `CmaFree`
  - memory pressure 可选
- Android 状态：
  - resumed activity
  - focused activity/window
  - visible window 列表摘要
  - display power state
  - brightness
  - 最近一次 screencap black ratio
  - 最近一次黑屏采样是否命中
  - SurfaceFlinger 有效可见应用 layer 数
  - SurfaceFlinger hidden/invisible 应用 layer 数
- 最近 1 秒关键 logcat 命中计数：
  - Binder 异常
  - LMK
  - gralloc/BufferQueue/EGL 分配失败
  - SystemUI/Shell transition 异常

### 黑屏每 10 秒采样

黑屏检测单独按 10 秒周期执行，避免每秒 `screencap` 增加设备压力。

每次黑屏采样同时采集：

- screencap black ratio、平均亮度、最大亮度。
- display power state 和 brightness。
- AMS resumed activity。
- WMS visible/focused window。
- SurfaceFlinger 有效可见应用 layer。

常规每秒采样记录最近一次黑屏采样结果，但 A3 停止条件必须按真实的 10 秒采样次数计算，不能把同一次 screencap 结果重复计为多次命中。

### dmabuf 口径

进程 dmabuf 是“该进程持有的 dmabuf 引用总量”，不是独占物理内存。同一个 dmabuf 可能同时被 SystemUI、SurfaceFlinger、system_server 计入。

推荐采样优先级：

1. 优先读取目标 pid 的 `/proc/<pid>/fd` 和 `/proc/<pid>/fdinfo`，按 dmabuf inode 去重统计 size。
2. 如果 fdinfo 不提供 size，再使用设备上的 dmabuf 统计接口，例如 `dmabuf_dump <pid>` 或目标版本实际支持的按 pid 参数格式。
3. 系统总 dmabuf 用全局 dmabuf 统计或 `dmabuf_dump` 的 total。
4. 系统总 dmabuf 可以按采样周期运行 `dmabuf_dump` 并只解析 total；完整 full dump 文本只在触发时保存。如果目标版本 `dmabuf_dump` 开销过大，应把系统总 dmabuf 采样周期做成可配置项。

## Monkey 管理

### 启动

脚本负责生成并记录完整 Monkey 命令。建议参数包含：

- 固定 `--seed`，便于复跑。
- `--throttle 300`，贴近现场日志。
- `--ignore-crashes`
- `--ignore-timeouts`
- `--ignore-security-exceptions`
- 保留 app switch、navigation、rotation、touch 等事件。
- 不限制到单一 package，至少覆盖音乐、地图、浏览器、launcher、SystemUI panel 相关入口。

### 停止

停止 Monkey 的顺序：

1. 标记停止原因和触发快照编号。
2. 先抓停止前现场。
3. 对 Monkey 进程发送正常终止信号，例如 `SIGTERM`。
4. 等待短时间，例如 3 秒。
5. 若仍未退出，再使用 `SIGKILL`。
6. 不使用 `kill -6`，避免人为制造 tombstone 干扰判断。
7. Monkey 停止后再抓一次现场，用于比较停止前后资源是否释放。

## 停止 Monkey 条件

停止条件分为两类：

- A 类：必须停止 Monkey。
- C 类：只抓现场，不停止 Monkey。

脚本实现时应记录具体命中的 rule id、连续命中次数、关键数值和最近 10 秒采样窗口。

### A 类：必须停止 Monkey（A1-A4、A6-A7）

#### A1. 单进程 dmabuf 持续超过 1.8 GiB

目标进程中任意一个满足：

- `dmabuf_bytes >= 1.8 GiB`
- 连续命中 `N` 次

建议默认：

- `N = 5`，即连续 5 秒。
- 若需要更敏感，可配置为 `N = 3`。

适用进程：

- `system_server`
- `com.android.systemui`
- `surfaceflinger`

误判规避：

- 脚本启动时记录 baseline。
- 如果某进程启动时已经超过 1.8 GiB，不应立即停止；改用 `baseline + 512 MiB` 或增长斜率判断。
- 如果采样失败，不计入连续命中，也不清空历史；记录 `sample_error`。

触发后必须抓：

- 三个目标进程的 fd/fdinfo/status。
- dmabuf 按 pid 统计。
- dmabuf full dump。
- `dumpsys SurfaceFlinger`。
- `dumpsys window`。
- `dumpsys activity activities`。
- screencap。

#### A2. 系统总 dmabuf 超过 20 GiB

满足任一条件：

- `total_dmabuf >= 20 GiB` 连续 2 秒。
- `total_dmabuf >= 22 GiB` 单次命中。

触发理由：

- 系统总 dmabuf 过高会导致图形分配失败、CMA 紧张、低内存和 Binder 状态同步异常。
- 该条件比单进程条件更接近系统级风险。

误判规避：

- 如果 total dmabuf 采样来自文本解析，解析失败时不能使用上一次值。
- 单次大于 22 GiB 可以直接停止，因为现场已经足够异常。

#### A3. 连续 6 次黑屏采样命中，且 AMS/WMS/SF 状态错位

每 10 秒执行一次黑屏采样。连续 6 次采样均满足以下所有条件时，停止 Monkey：

1. screencap 黑屏：
   - `black_ratio >= 0.98`，建议默认。
   - 更严格可配置为 `0.995`。
2. Display 仍然是正常亮屏状态：
   - display power 为 `ON` 或等价状态。
   - brightness 不为 0。
3. AMS 有 resumed activity：
   - 能解析到 `topResumedActivity` 或 `mResumedActivity`。
4. WMS 有 visible/focused 窗口：
   - 至少存在一个应用窗口 visible。
   - focused window 或当前 task window 不为空。
5. SurfaceFlinger 没有有效可见应用 layer：
   - 物理屏最终合成列表中没有 app layer；或
   - app layer 都是 hidden、`visibleRegion` 为空、`hidden by parent or layer flag`；或
   - 只有 `ScreenDecor`、overlay、wallpaper、decor 等非应用层。

这个条件判断的是“系统认为有前台内容，但 SF 没有可合成的应用内容”。这比单纯 screencap 黑屏更准确。默认 6 次连续命中约等于 60 秒确认窗口。

不应触发 A3 的情况：

- display 已关闭或亮度为 0。
- AMS 没有 resumed activity。
- WMS 没有 visible app window。
- SurfaceFlinger 有有效可见 app layer，但 app 自己绘制了黑色内容。这类应另记为 `app_content_black`，可以抓现场，但不归类为本问题的核心黑屏错位。

#### A4. 目标进程 fd 接近上限

任意目标进程满足：

- total fd count 连续 3 秒超过 `0.85 * fd_absolute_limit`；或
- total fd count >= `fd_absolute_limit`；或
- dmabuf fd count/sync_file fd count 在 60 秒内增长超过 3000。

触发理由：

- 本问题中 `surfaceflinger` 的 `sync_file` fd 数很高。
- 只看 dmabuf bytes 可能漏掉 fence/sync_file 泄露。

#### A6. SystemUI pid 变化，同时资源异常

满足：

- `com.android.systemui` pid 发生变化。
- 且变化前 60 秒内 SystemUI dmabuf、sync_file、fd 或 Binder 异常命中过阈值。

触发理由：

- SystemUI 重启可能已经释放了关键 dmabuf 引用。
- 继续跑 Monkey 会覆盖 SystemUI 重启前后的关键对比现场。

#### A7. 连续 LMK 且 swap/CMA 紧张

满足以下任一组合：

- 30 秒内 LMK kill >= 5 次，且 `SwapFree < 64 MiB`。
- `CmaFree < 16 MiB` 连续 5 秒，且有 gralloc/BufferQueue 分配失败。
- `MemAvailable < 512 MiB` 连续 10 秒，且目标进程 dmabuf 或 fd 正在增长。

触发理由：

- 这说明 dmabuf 或图形资源压力已经影响系统进程存活和图形分配。
- 继续压测会让第一异常现场被后续 LMK 覆盖。

#### A9. SystemUI/Shell transition 异常高频出现，并伴随资源或黑屏异常（只抓现场，不停止 Monkey）

当前脚本中 A9 只抓现场，不停止 Monkey。触发快照受 `c_snapshot_cooldown_sec` 限制。

最近 30 秒内以下关键字出现 >= 10 次：

- `transition is null`
- `AutoTaskStackController`
- `PanelAutoTaskStackTransitionHandler`
- `startMultiProfileAppWithDisplayId`
- `pauseBackTasks`
- `Transition timeout`

同时满足以下任一条件：

- 出现连续 2 次以上黑屏采样命中。
- 任意目标进程 dmabuf 超过 1.2 GiB。
- 系统总 dmabuf 超过 18 GiB。
- 出现 Binder ENOSPC 或 large transaction 高频异常。

### 其他 C 类：只抓现场，不停止 Monkey

这些条件单独出现时先抓现场，继续跑 Monkey：

- 黑屏采样命中，但少于连续 6 次。
- 单次 dmabuf 超过 1.8 GiB，但没有连续命中。
- 单次 large transaction。
- SystemUI/Shell transition 异常少量出现。
- 单独出现 LMK，但没有 swap/CMA 紧张。
- 单独出现图形分配失败，但没有 dmabuf、Binder 或黑屏异常。
- 单独出现 SystemUI pid 变化，但变化前没有资源或 Binder 异常。
- Monkey 切换到 launcher、空白页面、启动动画等可能导致短暂黑屏的场景。

只抓现场的目的：

- 保存异常前兆。
- 避免过早停止导致复现不充分。
- 让最终停止时能回看异常演化过程。

## 黑屏检测设计

### screencap 判断

每 10 秒执行一次轻量 screencap，并计算黑色像素比例。

建议：

- 采样可以缩放后计算，减少 host 开销。
- 黑色阈值可配置，例如 RGB 每通道 <= 8 认为黑。
- 同时记录平均亮度和最大亮度，避免深色 UI 被误判。

黑屏判定默认：

- `black_ratio >= 0.98`
- `avg_luma <= 8`

### AMS 判断

从 `dumpsys activity activities` 中解析：

- `topResumedActivity`
- `mResumedActivity`
- focused root task
- task id、user id、display id、windowing mode

要求至少能解析到一个 resumed activity。

### WMS 判断

从 `dumpsys window` 中解析：

- focused window
- visible app windows
- window token
- display id
- layer 或 surface created 状态

要求至少存在一个 visible 应用窗口。

### SurfaceFlinger 判断

从 `dumpsys SurfaceFlinger` 中解析：

- physical display 最终合成列表。
- app layer 列表。
- hidden/invisible layer 及 reason。
- `visibleRegion` 是否为空。
- 是否只有 decor、overlay、wallpaper。

有效可见应用 layer 的判断建议：

- layer 名包含 Activity、Task、app package、Splash Screen 等应用相关标识。
- layer 没有 hidden reason。
- `visibleRegion` 非空。
- 出现在目标 physical display 的合成路径中。

如果 WMS 有 visible app window，但 SF 没有有效可见应用 layer，计入黑屏错位连续秒数。

## 触发时抓现场

触发 A 类停止前先抓 `pre_stop`，Monkey 停止后抓 `post_stop`。

每次现场目录建议：

```text
<pc_output_root>/run-YYYYmmdd-HHMMSS/
  config.json
  monkey.cmd
  monitor.jsonl
  events.jsonl
  logcat/
    all.log
  triggers/
    0001_pre_stop/
    0001_post_stop/
```

每个 trigger 目录保存：

```text
reason.json
dumpsys_activity.txt
dumpsys_window.txt
dumpsys_surfaceflinger.txt
screencap.png
dmabuf_total.txt
dmabuf_by_pid.txt
dmabuf_full.txt
system_server/
  status.txt
  fd.txt
  fdinfo/
com.android.systemui/
  status.txt
  fd.txt
  fdinfo/
surfaceflinger/
  status.txt
  fd.txt
  fdinfo/
```

其中 `<pc_output_root>` 是 PC 本地目录，不是设备目录。默认可以使用脚本当前工作目录下的 `runs/`，例如：

```text
./runs/run-20260709-190000/logcat/all.log
```

`reason.json` 必须包含：

- rule id。
- rule name。
- stop action。
- 连续命中次数。
- 当前值。
- baseline。
- 最近 10 秒采样摘要。
- Monkey 命令和 seed。

## logcat 实时匹配

后台持续保存到 PC 本地 run 目录：

```bash
adb logcat -b all -v threadtime > <pc_output_root>/run-YYYYmmdd-HHMMSS/logcat/all.log
```

实时匹配关键字并写入事件流。

实现要求：

- logcat 保存文件必须位于 PC 本地目录，例如 `./runs/<run_id>/logcat/all.log`。
- 启动 Monkey 前先创建 run 目录和 `logcat/` 子目录。
- 启动 Monkey 前先启动 `adb logcat -c` 可选，用于清空旧 ring buffer；是否清空必须写入 `config.json`。
- 用 `subprocess.Popen` 后台启动 `adb logcat -b all -v threadtime`，stdout 直接写 PC 本地 `all.log`。
- 监控线程可以同时读取同一个 logcat 子进程输出并做关键字匹配；也可以单独启动一个匹配线程 tail 本地 `all.log`。
- 停止 Monkey 后再延迟 3 到 5 秒停止 logcat，确保 Monkey 停止后的系统状态日志也被保存。
- 停止脚本时必须关闭 logcat 子进程并 flush/close 本地文件句柄。

### Binder

- `Binder transaction failure`
- `No space left on device`
- `FAILED BINDER TRANSACTION`
- `Large outgoing transaction`
- `Large data transaction`

### 图形

- `SurfaceFlinger`
- `BufferQueue`
- `GraphicBufferAllocator`
- `dequeueBuffer failed`
- `EGL_BAD_ALLOC`
- `gralloc`
- `dmabuf`
- `ion`
- `kgsl`
- `hwcomposer`
- `DPU`

### 内存

- `lowmemorykiller`
- `lmkd`
- `Low on memory`
- `kswapd`
- `CMA`

### SystemUI/Shell

- `StateManager`
- `transition is null`
- `AutoTaskStackController`
- `PanelAutoTaskStackTransitionHandler`
- `startMultiProfileAppWithDisplayId`
- `pauseBackTasks`
- `Transition timeout`

## 配置建议

默认配置：

```json
{
  "sample_interval_sec": 1,
  "process_dmabuf_limit_bytes": 1932735283,
  "process_dmabuf_consecutive_sec": 5,
  "total_dmabuf_soft_limit_bytes": 21474836480,
  "total_dmabuf_soft_consecutive_sec": 2,
  "total_dmabuf_hard_limit_bytes": 23622320128,
  "screencap_interval_sec": 10,
  "black_ratio_threshold": 0.98,
  "black_screen_consecutive_samples": 6,
  "fd_limit_ratio": 0.85,
  "fd_absolute_limit": 8192,
  "sync_file_growth_limit_per_60s": 3000,
  "lmk_limit_per_30s": 5,
  "swapfree_low_bytes": 67108864,
  "cmafree_low_bytes": 16777216,
  "memavailable_low_bytes": 536870912,
  "systemui_pid_change_prior_window_sec": 60,
  "graphics_error_limit_per_10s": 5,
  "transition_error_limit_per_30s": 10,
  "weak_black_screen_consecutive_samples": 2,
  "process_dmabuf_weak_limit_bytes": 1288490189,
  "total_dmabuf_weak_limit_bytes": 19327352832
}
```

## 实机台架依赖信息清单

脚本实现前需要从实机台架确认以下信息。所有命令、路径、输出格式必须以目标车机实际版本为准，不能只按通用 Android 行为假设。

### ADB 和权限

需要确认：

- 设备是否需要指定 `adb -s <serial>`。
- 是否支持 `adb root`。
- `adb shell` 默认用户是否有权限读取 `/proc/<pid>/fd`、`/proc/<pid>/fdinfo`。
- 是否能读取 debugfs 或 vendor dmabuf 统计节点。
- 是否允许执行 `dumpsys SurfaceFlinger`、`dumpsys window`、`dumpsys activity activities`。
- 是否允许执行 `screencap`。
- 是否允许终止 Monkey 进程。
- 设备端是否有 `pidof`、`ps`、`readlink`、`stat`、`timeout`、`toybox` 等基础工具。

需要保存样例：

```bash
adb shell id
adb shell getprop ro.build.fingerprint
adb shell getprop ro.build.version.release
adb shell getprop ro.debuggable
adb shell which screencap
adb shell which dumpsys
adb shell which pidof
adb shell which ps
```

### 目标进程名和 pid 获取

需要确认目标进程精确名称：

- `system_server`
- `surfaceflinger`
- SystemUI 实际进程名，例如 `com.android.systemui` 或定制进程名。

需要确认 pid 获取命令和输出格式：

```bash
adb shell pidof system_server
adb shell pidof surfaceflinger
adb shell pidof com.android.systemui
adb shell ps -A | grep -E 'system_server|surfaceflinger|systemui'
```

如果 SystemUI 有多个进程，必须明确哪个进程负责自定义 Shell、Panel、TaskView、AutoTaskStack 逻辑。

### dmabuf 统计来源

需要确认至少一种系统总 dmabuf 统计来源：

```bash
adb shell cat /sys/kernel/debug/dma_buf/bufinfo
adb shell cat /d/dma_buf/bufinfo
adb shell dmabuf_dump
```

需要确认至少一种按 pid 统计 dmabuf 的方式：

```bash
adb shell dmabuf_dump <pid>
adb shell ls -l /proc/<pid>/fd
adb shell cat /proc/<pid>/fdinfo/<fd>
```

需要从台架保存以下样例：

- `dmabuf_dump` full dump 样例。
- `dmabuf_dump <pid>` 或目标版本实际按 pid dump 命令的样例。
- `/proc/<pid>/fd` 中 dmabuf fd 的 `ls -l` 样例。
- `/proc/<pid>/fdinfo/<fd>` 中 dmabuf fd 的样例。
- `/proc/<pid>/fdinfo/<fd>` 中 `sync_file` fd 的样例。

必须确认字段含义：

- dmabuf size 字段单位是 byte、kB 还是 page。
- full dump 中每个进程列的含义。
- 按 pid total 是引用总量、RSS、PSS 还是 unique memory。
- 同一 dmabuf 被多个进程引用时是否会重复计入进程总量。
- `sync_file` 是否能从 `/proc/<pid>/fd` symlink 名称稳定识别。

如果目标版本没有可用的 per-fd size，脚本必须退化为目标版本实际支持的按 pid dmabuf dump 命令；如果按 pid dump 开销太大，则只能降低采样频率或只使用 fd count 和 full dump 触发快照。

### 截屏命令和显示屏选择

需要确认实际可用的截屏命令：

```bash
adb exec-out screencap -p
adb shell screencap -p
adb shell screencap -p /data/local/tmp/screen.png
adb pull /data/local/tmp/screen.png <pc_output_root>/
```

如果车机有多屏，必须确认中控屏对应的 display id，以及 `screencap` 是否支持指定 display：

```bash
adb shell screencap -h
adb shell dumpsys display
adb shell dumpsys SurfaceFlinger --display-id
```

需要保存样例：

- 正常中控画面的 screencap。
- 黑屏状态的 screencap。
- 截屏文件格式，是 PNG 还是 raw framebuffer。
- 截屏分辨率，例如是否为 `6400x1800`。
- 黑屏时是否仍包含状态栏、导航栏、ScreenDecor 或 overlay。

必须确认黑屏判定参数：

- RGB 每通道低于多少算黑色像素。
- `black_ratio >= 0.98` 是否适合该屏幕。
- 是否需要排除固定 overlay 区域。
- 截屏命令单次耗时，必须低于 10 秒采样周期。

### AMS dump 格式

需要保存目标版本 `dumpsys activity activities` 样例：

```bash
adb shell dumpsys activity activities
```

必须确认可解析字段：

- `topResumedActivity`
- `mResumedActivity`
- resumed activity 所属 user id。
- resumed activity 所属 display id。
- task id。
- windowing mode。
- bounds。

如果目标版本字段名不同，需要提供正常前台应用和黑屏现场各一份样例，脚本按实际格式适配。

### WMS dump 格式

需要保存目标版本 `dumpsys window` 样例：

```bash
adb shell dumpsys window
```

必须确认可解析字段：

- focused window。
- visible app window。
- 窗口是否有 surface。
- display id。
- package/activity 名。
- layer 或 token 信息。

需要明确哪些窗口应算应用窗口，哪些应排除：

- SystemUI overlay。
- ScreenDecor。
- wallpaper。
- input method。
- toast。
- navigation/status/decor layer。

### SurfaceFlinger dump 格式

需要保存目标版本 `dumpsys SurfaceFlinger` 样例：

```bash
adb shell dumpsys SurfaceFlinger
adb shell dumpsys SurfaceFlinger --list
adb shell dumpsys SurfaceFlinger --displays
```

必须确认可解析字段：

- physical display 列表和中控屏 display id。
- 最终合成列表或 layer tree。
- app layer 名称格式。
- hidden/invisible reason 格式。
- `visibleRegion` 字段格式。
- layer 所属 pid、uid、package 是否可见。
- `ScreenDecor`、wallpaper、overlay 等非应用层名称。

需要保存样例：

- 正常前台应用可见时的 SF dump。
- 黑屏但 AMS/WMS 仍认为有前台窗口时的 SF dump。
- app layer 被 `hidden by parent or layer flag` 隐藏时的 SF dump。

### logcat 保存和匹配

需要确认 `logcat -b all` 在目标版本上可用：

```bash
adb logcat -b all -v threadtime
adb logcat -b all -g
adb logcat -b all -c
```

必须确认：

- 是否允许清空 logcat ring buffer。
- 是否需要保留旧日志。
- device 时间和 PC 时间是否同步。
- threadtime 时间戳是否包含日期。
- `logcat -b all` 是否包含 kernel、events、system、main、crash。

logcat 文件保存到 PC 本地目录：

```text
<pc_output_root>/run-YYYYmmdd-HHMMSS/logcat/all.log
```

### Monkey 命令和停止方式

需要确认最终 Monkey 命令模板，包括：

- seed。
- throttle。
- event count。
- package allowlist 或 blacklist。
- 各事件百分比。
- 是否跨 user/profile。
- 是否允许 rotation。
- 是否允许启动设置、电话、地图、音乐、浏览器、launcher 等应用。

需要确认 Monkey 进程识别和停止命令：

```bash
adb shell pidof com.android.commands.monkey
adb shell ps -A | grep monkey
adb shell kill -TERM <monkey_pid>
adb shell kill -KILL <monkey_pid>
```

禁止使用：

```bash
adb shell kill -6 <monkey_pid>
```

### 内存和系统压力节点

需要确认以下节点是否可读：

```bash
adb shell cat /proc/meminfo
adb shell cat /proc/pressure/memory
adb shell dumpsys meminfo
adb shell dumpsys meminfo --dmabuf
```

必须确认字段：

- `MemAvailable`
- `SwapFree`
- `CmaFree`
- `CmaTotal`
- 是否有 zram/swap。

### 输出目录和存储空间

需要确认 PC 本地输出目录：

```text
<pc_output_root>
```

需要确认：

- 目录可写。
- 可用空间足够保存长时间 logcat、screencap 和触发 dump。
- 单次测试最大运行时长。
- 是否需要按 run id 自动归档。
- 是否需要压缩旧 run。

## 当前台架已验证结果

本次已连接实机台架并保存样例到：

```text
bench_probe/
runs/probe-oneshot3/
```

已验证结果如下：

- 设备型号：`SA8397_Cockpit`。
- build：`Voyah/himalayas/himalayas:16/BP4A.251205.006/22.d.230-20260709013005:userdebug/test-keys`。
- `ro.debuggable=1`。
- `adb root` 可用；执行后设备序列号从 `6c7ac077` 变为 `6de0ff8`。
- `adb shell id` 为 root，但未执行 `adb root` 前读取 `/proc/<pid>/fd` 会 `Permission denied`。
- 脚本正式运行前应执行或确认 `adb root`，否则 fd/dmabuf/sync_file 采样不可用。

工具路径：

```text
/system/bin/screencap
/system/bin/dumpsys
/system/bin/pidof
/system/bin/ps
/system/bin/dmabuf_dump
```

目标进程当前样例：

```text
system_server pid=1883
surfaceflinger pid=1286
com.android.systemui pid=3112
```

注意：脚本不能固定这些 pid，必须运行时动态获取。

dmabuf 相关验证：

- `/sys/kernel/debug/dma_buf/bufinfo` 不存在。
- `/sys/kernel/dmabuf/buffers` 存在，但不适合作为脚本主数据源。
- `dumpsys meminfo --dmabuf` 不支持，会输出 `Unknown argument: --dmabuf` 并退化为普通 meminfo。
- 当前版本 `dmabuf_dump` 不支持 `-p` 参数。
- 当前版本按 pid dump 的正确格式是：

```bash
adb shell dmabuf_dump <pid>
```

例如：

```bash
adb shell dmabuf_dump 1286
adb shell dmabuf_dump 3112
```

`dmabuf_dump` full dump 末尾有系统总量：

```text
dmabuf total: <kB> kB kernel_rss: <kB> kB userspace_rss: <kB> kB userspace_pss: <kB> kB
```

`dmabuf_dump <pid>` 末尾有进程引用总量：

```text
PROCESS TOTAL <rss_kB> kB <pss_kB> kB
dmabuf total: ... userspace_rss: ...
```

`/proc/<pid>/fd` 中 dmabuf/sync_file 格式：

```text
100 -> /dmabuf:qcom,system
1000 -> anon_inode:sync_file
```

`/proc/<pid>/fdinfo/<fd>` 中 dmabuf 有 size 字段：

```text
ino:    168
size:   11522048
count:  8
exp_name: qcom,system
name: qcom,system
```

每秒采样采用：

- `ls -l /proc/<pid>/fd` 一次性读取 fd symlink target，并在 PC 端统计 total fd、dmabuf fd、sync_file fd。
- `dmabuf_dump <pid>` 统计进程 dmabuf bytes。
- `dmabuf_dump` 统计系统总 dmabuf bytes。

不采用逐 fdinfo 或逐 fd `readlink` 作为每秒主路径，因为 SurfaceFlinger fd 多时会超过 10 秒；实测 `ls -l /proc/<pid>/fd` 可把三大进程 fd 统计降到 0.1 秒级。

当前基线样例：

```text
surfaceflinger: total_fd=1491 dmabuf_fd=232 sync_file_fd=1124 dmabuf_bytes=510304256
com.android.systemui: total_fd=528 dmabuf_fd=56 sync_file_fd=95 dmabuf_bytes=69992448
system_server: total_fd=758 dmabuf_fd=0 sync_file_fd=0 dmabuf_bytes=0
system total dmabuf_bytes=4529242112
```

替换为 `ls -l /proc/<pid>/fd` 后，`runs/probe-lsfd-oneshot/monitor.jsonl` 实测常规采样开始到黑屏采样开始约 `1.68s`。

fd 停止规则使用配置里的 `fd_absolute_limit=8192` 作为上限；`/proc/<pid>/status` 中的 `FDSize` 只是 fd table 当前容量，不作为停止阈值。

截屏相关验证：

- 台架是多屏，未指定 display id 时，`screencap` 会先输出警告，导致 stdout 文件不是有效 PNG/raw。
- 中控屏物理 display id：

```text
4630946510463134225
```

- 中控屏分辨率：

```text
6400x1800
```

- 正确 PNG 截屏命令：

```bash
adb exec-out screencap -p -d 4630946510463134225 > <pc_output_root>/screen.png
```

- 正确 raw 截屏命令：

```bash
adb exec-out screencap -d 4630946510463134225 > <pc_output_root>/screen.raw
```

- raw 截屏头部为 4 个 little-endian u32：

```text
width=6400 height=1800 format=1 colorspace=1
```

- raw 数据大小约为 `16 + 6400 * 1800 * 4` bytes。
- 脚本使用 raw 截屏计算 black ratio，触发现场另保存 PNG。

AMS/WMS/SurfaceFlinger 验证：

- `dumpsys activity activities` 中 display 0 有：

```text
topResumedActivity=ActivityRecord{... com.voyah.cockpit.launcher/.LauncherVCOS ...}
```

- `dumpsys window` 中 display 0 有 visible window 列表：

```text
Display #0: [...]
```

- `dumpsys SurfaceFlinger --displays` 可解析中控屏：

```text
Display 4630946510463134225
activeMode={... resolution=6400x1800 ...}
powerMode=On
```

- `dumpsys SurfaceFlinger` 中中控屏 physical display 有 `Output Layer` 段，可解析有效 app layer：

```text
Display 4630946510463134225 (physical, "DP0S078151")
  - Output Layer ...(com.voyah.cockpit.launcher/com.voyah.cockpit.launcher.LauncherVCOS#229)
```

logcat 验证：

- `adb logcat -b all -v threadtime` 可用。
- logcat 保存到 PC 本地 `runs/<run_id>/logcat/all.log`。
- 不清空 logcat 时会先输出历史 ring buffer；脚本保存完整日志，但实时触发计数只统计脚本启动之后的 threadtime 日志，避免历史日志污染 10 秒/30 秒窗口。

## 实现注意事项

1. 所有阈值都必须可配置。
2. 所有连续条件必须按“成功采样次数”计算，采样失败不能伪造通过。
3. 触发停止后，不要立即杀 Monkey；先抓 `pre_stop`。
4. 停止 Monkey 后必须抓 `post_stop`，用于判断资源是否释放。
5. 采样命令要设置 timeout，避免 `dumpsys` 卡住导致主循环停摆。
6. 采样和 logcat 读取应分线程或异步执行。
7. `dmabuf_full.txt` 只在触发时保存；常规采样只记录解析后的 total，不每秒保存完整 full dump 文本。
8. 解析失败要写入 `events.jsonl`，不能静默忽略。
9. 进程 pid 变化时，旧 pid 的最后一次 fd/fdinfo 应尽量保存；如果已经消失，也要记录。
10. Monkey 停止原因只能有一个 primary reason，但可以记录多个 secondary reasons。
11. 本任务不分阶段交付；Monkey 启停、logcat 本地保存、常规采样、黑屏采样、A/C 类规则、触发前后抓现场必须一次完成。
