# Polaris Monitor — FD 泄漏检测方案（最终设计）

| 项目         | 内容                                               |
| ---------- | ------------------------------------------------ |
| **模块归属**   | polaris-monitor（Android Guest / GVM 侧 vendor 进程） |
| **新增 plugin** | `src/monitors/fdleak/`                           |
| **平台**     | Qualcomm SA8397 Cockpit / Gunyah GVM (Android)   |
| **状态**     | Final Design                                     |
| **日期**     | 2026-04-23                                       |

> 本方案是 dma-buf 单一类型 fd 泄漏方案（旧档 `DMABUF_MONITOR_FINAL_DESIGN.md`）的泛化升级：dma-buf 不再独立成模块，而是作为本方案的一个 fd **class**。其它 class（socket、regular_file、anon_inode、pipe）使用同一套白名单 / identity / 滑动窗口 / 触发判定 / 取证调度框架，仅在 classifier 规则、去重维度、forensic 命令集上各自专属。
>
> 方案评估与备选路径见 `DMABUF_MONITOR_DESIGN.md`（历史档）。本文只保留最终选定的实施设计。

---

## 1. 需求

### 1.1 要监测的泄漏类型

座舱域 Android Guest 上常见的 OOM / 资源耗尽 / 卡顿 / 帧丢失 / 网络异常，绝大多数可归因为**用户态 fd 未及时释放**。本方案统一监控指定进程的 fd 泄漏，按 fd 类型（class）分别配置阈值与取证手段：

| Class | 典型泄漏场景 |
|---|---|
| `dmabuf` | App 忘记 `close(HardwareBuffer.fd)` / `ImageReader.acquireLatestImage` 未 close；SF / HWC layer cache 异常；codec2 buffer pool 未归还；跨 VM 通道 backend 释放异常 |
| `socket` | TCP/UDS 连接未关、`accept()` 后未 close、HAL 客户端未释放；伴随 ESTABLISHED 堆积 |
| `regular_file` | 日志 / 配置文件未 close、临时文件 fd 累积、mmap 后未 munmap 但 fd 也未释放 |
| `anon_inode` | `eventfd` / `[eventpoll]` / `timerfd` 等事件循环对象泄漏（典型：epoll fd 持续上涨） |
| `pipe` | 父子进程 IPC 管道未 close、popen 流未 fclose |

现有覆盖盲区：

- `resource` plugin 只采集 `meminfo` / `loadavg` 宏观量，**抓不到 fd 类泄漏**
- `process` plugin 给出进程 fd 总数，**无分类、无趋势判定、无取证**
- 各 class 物理资源既可能计入 `Shmem` / `Slab` / `KernelStack` / sock_alloc 不一，从宏观面无法定位泄漏源头

### 1.2 设计约束

| # | 约束 | 含义 |
|---|---|---|
| C1 | **系统改动最小** | 不新增驱动、不改内核、不改 framework |
| C2 | **性能稳定性影响最小** | 稳态 CPU 近 0；单次采样 < 50 ms；任何失败静默不拖垮 daemon |
| C3 | **机制稳定** | 稳态路径只用 AOSP / Linux 公开 ABI；私有 debugfs / vendor hook 不作为必需项 |
| C4 | **可降级** | 量产镜像裁掉 debugfs 时自动退化，不中断主流程 |
| C5 | **加 class 不改核心** | 新 class = 加 classifier 配置 + 加 forensic_tasks 配置（必要时加一个去重函数），不改 scanner / 主循环 / executor |

### 1.3 明确的覆盖边界

本方案主打**用户态 fd 持有型泄漏**的监测与定位，显式不覆盖：

- **Kernel-only 资源泄漏**（GPU firmware 驻留池、VIDC 内部池、kernel-only dma-buf、内核 socket 缓冲膨胀）——没进任何用户态 fd，依赖 `resource` plugin 的宏观趋势侧面捕获
- **PVM 侧泄漏**——需 PVM 上独立部署同类 monitor
- **非白名单进程的偶发泄漏**——通过云端 incident 汇聚反推，再扩容白名单
- **瞬时泄漏峰值后自愈**——滑动窗口天然过滤，设计如此

---

## 2. 总体设计：两阶段 × 多 class

**核心思想**：稳态零开销只盯白名单进程的 per-class fd 数；触发后只对触发的那个 class 付详细取证代价。每轮 `/proc/<pid>/fd` 扫描**只走一次**，按 classifier 规则一次分流到所有 class 的窗口。

```
     ┌──────────────── Stage 1 (Always-on) ────────────────┐
     │ 每 interval_sec：                                     │
     │   1. ResolvePids(whitelist rules)                    │
     │   2. InstanceRegistry.Reconcile（PID 生命周期）        │
     │   3. FdScanner.Scan(pid, classes)                    │
     │      → readdir + readlink 一次，按 class 分流          │
     │      → 每 class 按其 dedup_by 去重（ino / fd / dev+ino）│
     │   4. 每 class 推入各自滑动窗口                          │
     │   5. TriggerPolicy.Evaluate（per-class 配置驱动）      │
     │        ├─ 未触发 → 继续轮询                             │
     │        └─ 触发   → Stage 2（携带 class_id）            │
     └──────────────────────────────────────────────────────┘
                               ▼
     ┌──────────────── Stage 2 (On-trigger) ───────────────┐
     │ 创建 /log/perf/fd_monitor/<ts>_<proc>_<pid>_<class>/  │
     │ 并发度受控地执行该 class 的 forensic_tasks（数组）：     │
     │   • dmabuf class:      dmabuf_dump / dumpsys SF       │
     │   • socket class:      ss -anpe / cat /proc/<pid>/net │
     │   • regular_file:      ls -l /proc/<pid>/fd           │
     │   • anon_inode/pipe:   ls -l + 简单聚合统计            │
     │   • 通用 task：         /proc/<pid>/{status,maps},     │
     │                        /proc/meminfo                   │
     │ 上报 polarisd 事件 + 按 (identity, class) 冷却         │
     └──────────────────────────────────────────────────────┘
```

**关键取舍**：

- 单次 `/proc/<pid>/fd` 遍历完成全 class 分流——加 class 不加 syscall 数
- `libdmabufinfo` / `dmabuf_dump` 等 class 专属工具只在该 class Stage 2 best-effort 使用，不进入稳态依赖
- Stage 2 任何 task 失败都落盘不中断主流程——满足 C2

---

## 3. 模块拆分

```
src/monitors/fdleak/
├── FdLeakMonitor.h/.cpp        # 主循环：reconcile → scan → evaluate → trigger
├── FdScanner.h/.cpp            # /proc/<pid>/fd 单次遍历 + per-class 分流去重
├── FdClassifier.h/.cpp         # readlink 串 → class_id（有序 regex 匹配）
├── InstanceRegistry.h/.cpp     # identity ↔ pid 映射；per-class 窗口集
├── TriggerPolicy.h/.cpp        # 纯函数规则评估（per-class）
├── ForensicCollector.h/.cpp    # Stage 2 调度：并发控制、超时、落盘、轮转
├── DumpTask.h/.cpp             # 单个取证任务 = {argv, out, timeout, condition}
└── classes/                    # 每 class 一份元数据 + 默认 forensic 模板
    ├── DmaBufClass.h           # dedup_by=fdinfo_ino, collect_bytes=true
    ├── SocketClass.h           # dedup_by=fd
    ├── RegularFileClass.h      # dedup_by=fdinfo_dev_ino
    ├── AnonInodeClass.h        # 二级 sub-tag（eventfd / [eventpoll] / timerfd）
    └── PipeClass.h
```

**职责约束**：

- `FdScanner` 无状态：(PID, classes config) in → `map<class_id, FdCountResult>` out；PID 消失返回错误给上层
- `FdClassifier` 走有序 regex 表，第一命中即归类；未命中归 `other`（默认不监控、不计数）
- `TriggerPolicy::Evaluate()` 纯函数：输入 (registry 快照, classes 配置) → 输出 `[{identity, class_id, reason, suspects}]`
- 所有 PID 生命周期副作用全部收敛到 `InstanceRegistry::Reconcile()`
- Config → 代码单向：加 class、调阈值、加白名单、加取证命令、开关规则、改冷却/限额，全部改 JSON 不改 C++（C5）

---

## 4. Stage 1：稳态采样

### 4.1 采样主循环（伪代码）

```cpp
for (const MatchRule& rule : cfg_.whitelist) {
    auto fresh_pids = ResolvePids(rule);
    registry_.Reconcile(rule.identity, fresh_pids);
}
for (auto& inst : registry_.All()) {
    auto class_results = FdScanner::Scan(inst.pid, cfg_.classes);  // §4.2
    for (auto& [class_id, r] : class_results) {
        inst.windows[class_id].push(now, r.distinct, r.bytes);
    }
}
auto decisions = TriggerPolicy::Evaluate(registry_, cfg_.classes);
for (const auto& s : decisions.suspects) {
    CooldownKey key{s.identity, s.class_id};
    if (cooldown_.Hit(key, now)) continue;                          // §4.6
    ForensicCollector::Capture(s, cfg_.classes.at(s.class_id).forensic);
    cooldown_.Set(key, now + cfg_.classes.at(s.class_id).forensic.cooldown_sec);
}
```

### 4.2 `FdScanner`：单次遍历 × per-class 分流去重

稳态数据源**仅**两处：

1. `readdir("/proc/<pid>/fd")` + `readlink`：每个 fd 拿到符号链接目标字符串
2. `/proc/<pid>/fdinfo/<fd>`：仅当对应 class 声明 `collect_bytes=true` 或 `dedup_by` 涉及 inode 时才读

```cpp
struct FdCountResult {
    uint32_t distinct;     // 按 class.dedup_by 去重后的对象数
    uint64_t total_bytes;  // 仅 class.collect_bytes=true 时填充
};
using ClassResults = std::map<std::string /*class_id*/, FdCountResult>;
```

**`dedup_by` 三种语义**：

| 取值 | 语义 | 适用 class |
|---|---|---|
| `fd` | 按 fd 编号去重（即 fd 计数） | socket / pipe / anon_inode |
| `fdinfo_ino` | 按 `fdinfo.ino`（buffer/inode）去重 | dmabuf |
| `fdinfo_dev_ino` | 按 `(major,minor):ino` 去重 | regular_file |

**为什么不用全局统一维度**：dma-buf 的 `dup` / 跨组件共享导致同 buffer 多 fd（必须 ino 去重，否则 layer 交换频繁时假阳性）；socket 一般每 fd 一会话（直接数 fd 即可，强行读 fdinfo 反而徒增 syscall）；regular file 跨进程共享通过 `dev+ino` 才能去重。统一框架，每 class 自定。

单进程单次遍历实测 < 2 ms（含全 class 分流，多读 fdinfo 仅对声明需要的 class 进行）；8 进程白名单单轮 < 25 ms。

### 4.3 身份模型与生命周期管理

**前提**：Android 上被监控进程 PID 不稳定——app 冷启动变 PID，service crash 重拉换 PID。**身份必须与 PID 解耦**。

**身份模型**：

- `whitelist` 是 `exact / prefix / package` 三种匹配规则，不是 PID 列表
- 每轮开头 `ResolvePids(rule)` 扫 `/proc` 用 `comm` / `cmdline` 匹配
- 同一 identity 可命中多 PID（多实例、isolated_process）
- **`package` 匹配结果加 TTL 缓存**（默认 10 s），避免每轮全量扫 `/proc/*/cmdline`

**数据结构**：

```cpp
struct TrackedInstance {
    std::string identity;
    pid_t       pid;
    uint64_t    pid_start_clk;                           // /proc/<pid>/stat 第 22 列
    std::map<std::string, SlidingWindow> windows;        // 每 class 一条窗口
    TimePoint   attached_at;
};
std::map<pid_t, TrackedInstance>          tracked_;
std::map<CooldownKey, Cooldown>           cooldown_;     // 键 = (identity, class_id)
```

**`pid_start_clk` 的作用**：即使内核快速回收复用 PID 号，`starttime` 也不同，可**可靠区分新旧实例**。

**每轮四态判定**：

| 状态 | 检查 | 处理 |
|---|---|---|
| 正常 | stat 可读、starttime 不变、comm 匹配 | 继续累加各 class 窗口 |
| 消失 | stat 不可读 | 丢全部 class 窗口，从 tracked_ 移除 |
| PID 复用 | starttime 变化 | 丢全部 class 窗口，视作旧实例结束 |
| 进程替身 | comm 不匹配 identity | 同 PID 复用 |

处理完 diff，再把 `ResolvePids()` 返回的新 PID 加入，全部 class 窗口清零、`attached_at = now`。

### 4.4 Warmup 宽限期（per-class）

新进程启动时不同 class 的天然爆发不同：dma-buf 建 layer / pipeline 需要 ~120 s 平稳；socket 通常 30 s 内即稳；regular_file 配置加载完即稳（60 s）。warmup 在 class 维度配置：

```cpp
auto& cls = cfg_.classes.at(class_id);
if (now - inst.attached_at < cls.warmup_sec) continue;
```

### 4.5 Crash-loop 自保

若同一 identity 的 PID 在 `crash_loop_guard.window_sec` 内变化超过 `max_restarts` 次，进程本身有问题，任何 class 的 fd 误报都无意义：

1. 上报 `process_crash_loop` 事件（与具体 class 的 `*_leak_suspect` 区别）
2. 暂停该 identity **全部 class** 的触发判定 `pause_monitor_sec` 秒（仍采样）
3. 暂停期间新 PID 的 warmup 照常生效

**关键配置关系**：`pause_monitor_sec >= 2 × max(class.forensic.cooldown_sec)`，否则暂停窗口短于最长冷却窗口，crash-loop 自保失效。

### 4.6 冷却键的选择

冷却键用 **(identity, class_id) 组合** 而非 PID。原因：

- 跨 PID 有效（crash-重启后 PID 变了，按 identity 仍生效，杜绝 crash 绕冷却）
- 跨 class 解耦（同进程的 dma-buf 触发不应抑制同进程的 socket 触发）

### 4.7 触发规则（per-class，配置驱动，纯函数）

每 class 独立的 `trigger.rules[]` 与 `combine`。规则类型：

| type | 语义 | 关键字段 |
|---|---|---|
| `slope` | 滑动窗口斜率超阈值 | `window_sec`, `threshold`, `min_samples` |
| `monotonic` | 连续 N 次单调增且每次 ≥ min_delta | `consecutive`, `min_delta` |

`metric` 在 class 内可选 `distinct_count` 或 `bytes_mb`（仅 `collect_bytes=true` 的 class 支持后者）。多规则通过 `combine: any | all` 组合。

---

## 5. Stage 2：取证落盘

### 5.1 任务配置化（per-class）

每 class 自带 `forensic.tasks` 数组。代码里只有一个通用 executor。

**dmabuf class 示例**：

```json
"tasks": [
  {"name": "dmabuf_dump_full",        "cmd": ["/system/bin/dmabuf_dump", "-a", "-o", "csv"], "out": "dmabuf_dump_full.csv", "timeout_ms": 3000, "condition": "always"},
  {"name": "dmabuf_dump_per_buffer",  "cmd": ["/system/bin/dmabuf_dump", "-b"],              "out": "dmabuf_per_buffer.txt", "timeout_ms": 3000, "condition": "always"},
  {"name": "dmabuf_dump_suspect_pid", "cmd": ["/system/bin/dmabuf_dump", "${SUSPECT_PID}"],  "out": "dmabuf_dump_pid.txt",   "timeout_ms": 3000, "condition": "always"},
  {"name": "dumpsys_sf_dmabuf",       "cmd": ["/system/bin/dumpsys", "SurfaceFlinger", "--dmabuf"], "out": "dumpsys_sf_dmabuf.txt", "timeout_ms": 5000,
                                       "condition": "proc_in:surfaceflinger,system_server",
                                       "__note__": "子命令 --dmabuf 需在目标 AOSP 分支 grep frameworks/native/services/surfaceflinger 确认存在；不存在则删除此 task"},
  {"name": "dumpsys_meminfo_pkg",     "cmd": ["/system/bin/dumpsys", "meminfo", "${SUSPECT_PROC}"], "out": "dumpsys_meminfo_pkg.txt", "timeout_ms": 5000, "condition": "proc_is_app"},
  {"name": "bufinfo",                 "cmd": ["/system/bin/cat", "/sys/kernel/debug/dma_buf/bufinfo"], "out": "bufinfo.txt", "timeout_ms": 2000, "condition": "path_readable:/sys/kernel/debug/dma_buf/bufinfo"}
]
```

**socket class 示例**：

```json
"tasks": [
  {"name": "ss_full",         "cmd": ["/system/bin/ss", "-anpe"], "out": "ss.txt",       "timeout_ms": 3000, "condition": "always"},
  {"name": "proc_net_tcp",    "cmd": ["/system/bin/cat", "/proc/${SUSPECT_PID}/net/tcp"],  "out": "net_tcp.txt",  "timeout_ms": 1000, "condition": "always"},
  {"name": "proc_net_tcp6",   "cmd": ["/system/bin/cat", "/proc/${SUSPECT_PID}/net/tcp6"], "out": "net_tcp6.txt", "timeout_ms": 1000, "condition": "always"},
  {"name": "proc_net_udp",    "cmd": ["/system/bin/cat", "/proc/${SUSPECT_PID}/net/udp"],  "out": "net_udp.txt",  "timeout_ms": 1000, "condition": "always"},
  {"name": "proc_net_unix",   "cmd": ["/system/bin/cat", "/proc/${SUSPECT_PID}/net/unix"], "out": "net_unix.txt", "timeout_ms": 1000, "condition": "always"}
]
```

**regular_file / anon_inode / pipe class 示例**（轻量取证，按 fd 列表聚合即可）：

```json
"tasks": [
  {"name": "fd_listing", "cmd": ["/system/bin/ls", "-l", "/proc/${SUSPECT_PID}/fd"], "out": "fd_listing.txt", "timeout_ms": 2000, "condition": "always"}
]
```

**通用 task（所有 class 触发都建议附带）**：

```json
"tasks": [
  {"name": "proc_status",  "cmd": ["/system/bin/cat", "/proc/${SUSPECT_PID}/status"], "out": "proc_status.txt", "timeout_ms": 1000, "condition": "always"},
  {"name": "meminfo",      "cmd": ["/system/bin/cat", "/proc/meminfo"],               "out": "meminfo.txt",     "timeout_ms": 1000, "condition": "always"}
]
```

可在 schema 顶层 `global_forensic.common_tasks` 声明一次，每 class 触发时自动追加，避免重复。

**重要事项**：

- 二进制路径用 **`/system/bin/cat`** / `/system/bin/ls` / `/system/bin/ss` 等（Android 不存在 `/bin/`）
- `dumpsys SurfaceFlinger --dmabuf` 子命令版本差异，**P0 前必须在目标 AOSP 分支核实**
- `ss` 在 SA8397 镜像中是否存在需 P0 验证；缺失则降级为 `cat /proc/<pid>/net/*`

### 5.2 执行方式

- **复用 `polarisd::ChildProcess`（`native/polarisd/execution/ChildProcess.{h,cpp}`）**：fork + execve + CLOEXEC 错误管道 + 固定 argv + stdout/stderr 管道；**不走 shell，不做字符串拼接**，杜绝注入。不自行实现 `posix_spawn`——Android 上 `posix_spawn` 带隐式信号掩码问题，且现有 `ChildProcess` 已经处理了 SIGTERM→SIGKILL 升级、输出截断落盘、execve 失败诊断。monitor Android.bp 把 `ChildProcess.cpp` 作为源码加入并追加 `../polarisd/execution` 到 `local_include_dirs`，避免把 polarisd 的执行层改动成动态库
- `${SUSPECT_PID}` / `${SUSPECT_PROC}` 在 argv 展开前进行**白名单正则校验**（`[A-Za-z0-9._-]+`），防止被恶意 comm 污染 argv
- 每个 task 独立 `timeout_ms`，超时 `SIGKILL` 子进程
- 子进程 spawn 前 `ioprio_set(IOPRIO_CLASS_IDLE)`，避开关键路径 IO
- **并发上限 `max_concurrent_tasks`（默认 3）**：跨 class 共享同一个并发槽，防止两 class 同时触发把 servicemanager / SF 顶住

### 5.3 冷却与节流

- `class.forensic.cooldown_sec`：(identity, class) 维度的冷却（默认 600 s）
- `global_forensic.global_min_interval_sec`：全局最小间隔（默认 60 s），防多 (identity, class) 同时触发刷盘
- `crash_loop_guard.pause_monitor_sec >= 2 × max(class.forensic.cooldown_sec)`

### 5.4 落盘目录与轮转

```
/log/perf/fd_monitor/
├── incidents.log                                       # 每次触发追加一行 JSON 索引（含 class）
├── 20260423_143012_surfaceflinger_1240_dmabuf/
│   ├── meta.json                                       # 触发原因、窗口数据、版本号、class
│   ├── dmabuf_dump_full.csv
│   ├── dmabuf_per_buffer.txt
│   ├── ...
│   ├── proc_status.txt
│   └── meminfo.txt
├── 20260423_152744_system_server_1024_socket/
│   ├── meta.json
│   ├── ss.txt
│   ├── net_tcp.txt
│   └── ...
└── 20260423_160218_com.voyah.launcher_2413_anon_inode/
    └── ...
```

- 目录名后缀 `_<class>`，便于按 class 切片分析
- `global_forensic.max_total_mb`（默认 200）：目录总量上限，LRU 轮转
- `global_forensic.max_incidents`（默认 50）：保留最近 N 个 incident 目录

### 5.5 上报 schema（polarisd 事件）

Stage 2 落盘完成后，通过现有 `PolarisReporter::Report(event_id, params_json, log_path)` 上报一条事件。三个参数语义：

#### 5.5.1 `event_id`

每 class 一个常量，定义在 `polaris/EventId.h`，与 `classes[].report_event_type` 字符串名一一对应。建议常量命名：

| 来源 | report_event_type | event_id 常量（草案） |
|---|---|---|
| dmabuf class       | `dmabuf_leak_suspect`        | `EventId::GVM_DMABUF_LEAK_SUSPECT` |
| socket class       | `socket_leak_suspect`        | `EventId::GVM_SOCKET_LEAK_SUSPECT` |
| regular_file class | `regular_file_leak_suspect`  | `EventId::GVM_REGULAR_FILE_LEAK_SUSPECT` |
| anon_inode class   | `anon_inode_leak_suspect`    | `EventId::GVM_ANON_INODE_LEAK_SUSPECT` |
| pipe class         | `pipe_leak_suspect`          | `EventId::GVM_PIPE_LEAK_SUSPECT` |
| crash_loop_guard   | `process_crash_loop`         | `EventId::GVM_PROCESS_CRASH_LOOP` |

具体数值与 polarisd 服务端事件库对齐，P7 阶段定稿。

#### 5.5.2 `params_json`

紧凑编码，遵循现有 `ResourceCollector` / `LogEvent` 风格（短键名 + 栈缓冲 `snprintf`，硬上限 ≤ **726 B**，超限整事件丢弃 + LOGW，**绝不截断上报**）。

`*_leak_suspect` 系事件示例：

```json
{
  "ts": 1745399412,
  "cls": "dmabuf",
  "id":  "surfaceflinger",
  "pid": 1240,
  "psc": 12345678,
  "rule": "slope_count",
  "metric": "distinct_count",
  "win": 600,
  "n0":  32, "n1":  87,
  "rate": 5.5,
  "by0": 12, "by1": 38
}
```

字段说明：

| 字段 | 含义 | 备注 |
|---|---|---|
| `ts` | 触发时间戳（秒，unix epoch） | |
| `cls` | class name | 即 `classes[].name` |
| `id` | identity | 白名单命中的 value |
| `pid` | 触发时 PID | |
| `psc` | pid_start_clk | 用于服务端跨 PID 去重 / 关联 |
| `rule` | 命中的规则 name | 即 `trigger.rules[].name` |
| `metric` | 命中规则的度量 | `distinct_count` / `bytes_mb` |
| `win` | 滑动窗口长度（秒） | |
| `n0` / `n1` | 窗口起 / 终的 distinct 计数 | |
| `rate` | 增长率（distinct / min） | 仅 `slope` 规则填充 |
| `by0` / `by1` | 窗口起 / 终的字节数（MB） | 仅 `collect_bytes=true` 的 class 填充 |

典型 size ~140 B，远在 726 B 上限内。

`process_crash_loop` 事件示例（无 forensic 目录、`log_path` 传 nullptr）：

```json
{"ts":1745399412,"id":"surfaceflinger","pid":1240,"psc":12345678,"restarts":4,"win_sec":300}
```

#### 5.5.3 `log_path`

**取本次触发的 incident 目录路径**，即 §5.4 描述的：

```
/log/perf/fd_monitor/<YYYYMMDD>_<HHMMSS>_<proc>_<pid>_<class>
```

实例：

```
/log/perf/fd_monitor/20260423_143012_surfaceflinger_1240_dmabuf
```

**这里传的是目录路径而非单个文件路径**——polarisd 端按目录递归抓取该次触发的全部产物（`meta.json` + 各 task 输出 + 通用 `proc_status.txt` / `meminfo.txt`）。`process_crash_loop` 事件无取证目录，`log_path` 传 `nullptr`。

#### 5.5.4 `meta.json`（incident 目录内）

服务端拿到 `log_path` 后第一份读的文件，承载本次触发的完整元数据（不计入 726 B 上报上限）：

```json
{
  "ts": 1745399412,
  "cls": "dmabuf",
  "identity": "surfaceflinger",
  "pid": 1240,
  "pid_start_clk": 12345678,
  "trigger": {
    "rule": "slope_count",
    "metric": "distinct_count",
    "window_sec": 600,
    "samples": [
      {"t": 1745398812, "v": 32, "by": 12},
      {"t": 1745398872, "v": 41, "by": 16},
      {"t": 1745399412, "v": 87, "by": 38}
    ]
  },
  "tasks": [
    {"name": "dmabuf_dump_full",       "exit": 0, "duration_ms":  820, "out_bytes": 15234},
    {"name": "dmabuf_dump_per_buffer", "exit": 0, "duration_ms":  640, "out_bytes":  9821},
    {"name": "dmabuf_dump_suspect_pid","exit": 0, "duration_ms":  410, "out_bytes":  3142},
    {"name": "dumpsys_sf_dmabuf",      "exit": 0, "duration_ms": 3120, "out_bytes": 48210},
    {"name": "bufinfo",                "skipped": "path_not_readable"}
  ],
  "monitor_version": "1.x"
}
```

#### 5.5.5 `incidents.log`

`/log/perf/fd_monitor/incidents.log` 每次触发追加一行 JSON（与 §5.5.2 上报 `params_json` 同字段，多一个 `dir` 字段指向 incident 目录名），用于：

- polarisd 不可达时本地保留触发历史
- 服务端恢复后 `polaris_client` 重传补齐
- 端侧人工排查的入口

```json
{"ts":1745399412,"cls":"dmabuf","id":"surfaceflinger","pid":1240,"rule":"slope_count","dir":"20260423_143012_surfaceflinger_1240_dmabuf"}
```

---

## 6. 完整配置 Schema

### 6.1 fd_leak 子对象（纯 JSON）

> `classes[].forensic.tasks` 数组的内容详见 §5.1，下例为节省篇幅省略具体 task。各字段语义已在 §4 / §5 中分章说明。

```json
{
  "fd_leak": {
    "enable": true,
    "interval_sec": 30,

    "whitelist": [
      {"match": "exact",   "value": "surfaceflinger"},
      {"match": "exact",   "value": "cameraserver"},
      {"match": "exact",   "value": "system_server"},
      {"match": "prefix",  "value": "media."},
      {"match": "prefix",  "value": "hwcomposer-"},
      {"match": "package", "value": "com.voyah.launcher"},
      {"match": "package", "value": "com.voyah.ai.voice"}
    ],

    "crash_loop_guard": {
      "enable": true,
      "max_restarts": 3,
      "window_sec": 300,
      "pause_monitor_sec": 1800,
      "report_event_type": "process_crash_loop"
    },

    "global_forensic": {
      "enable": true,
      "output_dir": "/log/perf/fd_monitor",
      "global_min_interval_sec": 60,
      "max_concurrent_tasks": 3,
      "io_priority_idle": true,
      "max_total_mb": 200,
      "max_incidents": 50,
      "common_tasks": []
    },

    "report": {
      "always_report_samples": false,
      "report_on_trigger": true
    },

    "classes": [
      {
        "name": "dmabuf",
        "enable": true,
        "match_link_regex": "^(anon_inode:dmabuf|/dmabuf:.*)$",
        "dedup_by": "fdinfo_ino",
        "collect_bytes": true,
        "warmup_sec": 120,
        "trigger": {
          "rules": [
            {"name": "slope_count", "type": "slope", "metric": "distinct_count", "window_sec": 600, "threshold": 50, "min_samples": 10},
            {"name": "monotonic",   "type": "monotonic", "metric": "distinct_count", "consecutive": 6, "min_delta": 2},
            {"name": "slope_bytes", "type": "slope", "metric": "bytes_mb", "window_sec": 600, "threshold": 20, "min_samples": 10}
          ],
          "combine": "any"
        },
        "forensic": {"cooldown_sec": 600, "tasks": []},
        "report_event_type": "dmabuf_leak_suspect"
      },
      {
        "name": "socket",
        "enable": true,
        "match_link_regex": "^socket:\\[[0-9]+\\]$",
        "dedup_by": "fd",
        "collect_bytes": false,
        "warmup_sec": 30,
        "trigger": {
          "rules": [
            {"name": "slope_count", "type": "slope", "metric": "distinct_count", "window_sec": 600, "threshold": 80, "min_samples": 10},
            {"name": "monotonic",   "type": "monotonic", "metric": "distinct_count", "consecutive": 6, "min_delta": 3}
          ],
          "combine": "any"
        },
        "forensic": {"cooldown_sec": 600, "tasks": []},
        "report_event_type": "socket_leak_suspect"
      },
      {
        "name": "regular_file",
        "enable": true,
        "match_link_regex": "^/(?!dmabuf:).*",
        "dedup_by": "fdinfo_dev_ino",
        "collect_bytes": false,
        "warmup_sec": 60,
        "trigger": {
          "rules": [
            {"name": "slope_count", "type": "slope", "metric": "distinct_count", "window_sec": 600, "threshold": 60, "min_samples": 10},
            {"name": "monotonic",   "type": "monotonic", "metric": "distinct_count", "consecutive": 6, "min_delta": 2}
          ],
          "combine": "any"
        },
        "forensic": {"cooldown_sec": 600, "tasks": []},
        "report_event_type": "regular_file_leak_suspect"
      },
      {
        "name": "anon_inode",
        "enable": true,
        "match_link_regex": "^anon_inode:(?!dmabuf$).*",
        "dedup_by": "fd",
        "collect_bytes": false,
        "warmup_sec": 60,
        "trigger": {
          "rules": [
            {"name": "slope_count", "type": "slope", "metric": "distinct_count", "window_sec": 600, "threshold": 40, "min_samples": 10},
            {"name": "monotonic",   "type": "monotonic", "metric": "distinct_count", "consecutive": 6, "min_delta": 2}
          ],
          "combine": "any"
        },
        "forensic": {"cooldown_sec": 600, "tasks": []},
        "report_event_type": "anon_inode_leak_suspect"
      },
      {
        "name": "pipe",
        "enable": true,
        "match_link_regex": "^pipe:\\[[0-9]+\\]$",
        "dedup_by": "fd",
        "collect_bytes": false,
        "warmup_sec": 30,
        "trigger": {
          "rules": [
            {"name": "slope_count", "type": "slope", "metric": "distinct_count", "window_sec": 600, "threshold": 30, "min_samples": 10},
            {"name": "monotonic",   "type": "monotonic", "metric": "distinct_count", "consecutive": 6, "min_delta": 2}
          ],
          "combine": "any"
        },
        "forensic": {"cooldown_sec": 600, "tasks": []},
        "report_event_type": "pipe_leak_suspect"
      }
    ]
  }
}
```

**字段单位与约束提示**（schema 本身不便表达，集中说明）：

- `classes[].dedup_by`：参见 §4.2 表格
- `classes[].collect_bytes`：仅 `dmabuf` 默认 true；其它 class 字节统计意义不大，关闭以省一次 fdinfo 读
- `classes[].match_link_regex`：classifier 按 `classes` 数组顺序匹配，第一命中即归类。**因此 `dmabuf` 必须排在 `anon_inode` / `regular_file` 之前**，否则会被通配规则吸走
- `classes[].warmup_sec`：详 §4.4
- `crash_loop_guard.pause_monitor_sec ≥ 2 × max(classes[].forensic.cooldown_sec)`：详 §4.5
- `classes[].forensic.cooldown_sec`：按 (identity, class) 冷却（详 §4.6）
- `global_forensic.max_concurrent_tasks` / `io_priority_idle`：跨 class 共享并发槽 + IDLE 调度（详 §5.2）

**配置即行为**：加 class、调阈值、加白名单、加取证命令、开关子规则、改冷却/限额，全部改 JSON 不改 C++。

### 6.2 与现有 Config 聚合方式

`fd_leak` 是 `/etc/polaris/monitor.json` 顶层的一个**平级子对象**，与既有的 `resource` / `process` / `log_event` 同级。`monitor.json` 整体形态：

```json
{
  "resource":  { "...": "..." },
  "process":   { "...": "..." },
  "log_event": { "...": "..." },
  "fd_leak":   { "...": "见 §6.1" }
}
```

C++ 侧对应改动：

- 新增 `src/monitors/fdleak/FdLeakConfig.h`，定义 `FdLeakConfig` 及其子结构（`MatchRule` / `ClassConfig` / `TriggerRule` / `ForensicTask` / `CrashLoopGuard` / `ReportConfig` 等），**不污染** `core/Config.h`——后者只追加一个字段：

  ```cpp
  // src/core/Config.h
  #include "monitors/fdleak/FdLeakConfig.h"

  struct Config {
      std::string    config_path;
      ResourceConfig resource;
      ProcessConfig  process;
      LogEventConfig log_event;
      FdLeakConfig   fd_leak;       // 新增
      bool Load(const std::string& path);
  };
  ```

- `Config::Load()`（当前为 TODO 桩）在落地 JSON 解析时，挂一个 `fdleak::ParseConfig(j.value("fd_leak", json::object()), cfg.fd_leak)` 子入口；任一子段缺失走 struct 默认值，整段解析异常则保守 `cfg.fd_leak.enable = false`，主流程不中断（与现有 `Load()` 失败语义一致）
- `FdLeakMonitor::Init(const Config& cfg, ...)` 走和 `LogEventMonitor::Init` 同样的签名（`IMonitor`），从 `cfg.fd_leak` 取参数；`enable=false` 时直接 `return true` 不启线程

**对 JSON 注释的处理**：本设计文档示例为纯 JSON。建议 `Config::Load()` 在引入 JSON 解析器时统一开启 ignore-comments（如 nlohmann::json `parse(text, nullptr, true, /*ignore_comments=*/true)`），允许部署现场的 `monitor.json` 携带 `//` 行注释用于运维标注。该开关一次性作用于全部子段，并非 `fd_leak` 专属能力。

### 6.3 运维指南：如何修改 `monitor.json`

> 本节针对 `vendor/voyah/system/polaris/native/monitor/monitor.json`（生产配置，编译进
> `/system/etc/polaris/monitor.json`），告诉维护者**改什么、怎么改、改完怎么验证**。
> 字段语义本身参见 §6.1。

#### 6.3.1 部署链路

```
源文件                   构建模块              设备落地
monitor.json     ──→  prebuilt_etc          /system/etc/polaris/monitor.json
                  (polaris_monitor_json)    （/etc 是 /system/etc 的 symlink）
```

- 源文件路径：`vendor/voyah/system/polaris/native/monitor/monitor.json`
- 构建配置：`vendor/voyah/system/polaris/native/monitor/Android.bp` 的 `prebuilt_etc { name: "polaris_monitor_json", sub_dir: "polaris" }`
- 入包：`device/voyah/qssi_common/voyah_qssi.mk` 的 `PRODUCT_PACKAGES += polaris_monitor_json`
- 加载时机：**`polaris-monitor` 进程启动时一次性解析**（`main.cpp::Config::Load()`）。运行中改文件**不会**被读到，必须 `stop polaris-monitor && start polaris-monitor`。
- 失败行为：JSON 语法错或 `fd_leak.enable=false` → 整个 FdLeakMonitor 静默关闭，仅 logcat 一行 WARN。其它模块（resource / log_event）不受影响。

#### 6.3.2 常见修改场景

| 想做什么 | 改哪里 | 注意事项 |
|---|---|---|
| **加监控进程** | `whitelist[]` 末尾追加一条 | 选 `match` 类型见下方"匹配类型选择" |
| **删监控进程** | 注释或删除对应条目 | 该 identity 对应的 tracked 实例下次 Reconcile 自动清掉 |
| **某 class 误报太多** | 对应 `classes[N].trigger.rules` 调高 `threshold`、加大 `window_sec` 或 `min_samples`；或 `classes[N].forensic.cooldown_sec` 调长 | 不要直接 `enable: false` 整个 class——会丢掉所有该类 fd 监测 |
| **某 class 漏报** | 调小 `threshold`、`min_samples`、`warmup_sec` | warmup 太短会被启动期天然分配淹没（详 §4.4） |
| **加一个取证命令** | `classes[N].forensic.tasks[]` 或 `global_forensic.common_tasks[]` 末尾加一条 | argv[0] 必须是 `/system/bin/...` 或 `/vendor/bin/...` 的绝对路径；用 `${SUSPECT_PID}` / `${SUSPECT_PROC}` 占位符；condition 见 §5.1 |
| **取证执行的命令需要新文件 / 网络权限** | **同时改 SELinux**（详 §7） | 否则 ChildProcess 会 spawn 成功但被 AVC 拒绝，只见 `meta.json` 里 `exit != 0` |
| **关掉所有取证落盘**（紧急止损磁盘） | `global_forensic.enable: false` | **触发事件仍会上报到 polarisd**，只是没有 incident 目录。详 §6.3.3 |
| **磁盘上限调整** | `global_forensic.max_total_mb` / `max_incidents` | 两条上限并存：先按数量裁，再按容量裁（详 §5.4）；任一为 0 = 该维度不限制 |
| **crash-loop 太敏感** | `crash_loop_guard.max_restarts` 调大、`window_sec` 调小 | `pause_monitor_sec ≥ 2 × max(class.cooldown_sec)`，否则被 `SanityClampConfig` 自动 clamp + LOGW |
| **临时全关 fd_leak 监测** | `fd_leak.enable: false` | 仅停 fd_leak 一个模块，其它 monitor 继续 |

#### 6.3.3 匹配类型选择（`whitelist[].match`）

| 选哪个 | 适用对象 | 例子 | 注意 |
|---|---|---|---|
| `exact` | comm 短且未被 binder 线程池覆盖的原生服务 | `surfaceflinger` / `cameraserver` / `mediaserver` / `system_server` | comm 限 15 字符；超长会被截断；HAL 服务 comm 常被改成 `binder:PID_N`，不能用 |
| `prefix` | comm 有公共前缀的同类进程 | （当前未用，可考虑 `media.` 系列） | 仅匹配 comm 前缀；同样受 15 字符截断影响 |
| `package` | 所有匹配 cmdline argv[0] 的场景 | Android app `com.voyah.cockpit.media`；HAL 服务 `/vendor/bin/hw/...` | 命中 `argv[0] == value` 或 `argv[0] == value + ":..."`（自动覆盖 Android 子进程，如 `:remote` / `:service`） |

**判断方法**：在车机上 `adb shell "cat /proc/<pid>/comm; echo --; head -c 256 /proc/<pid>/cmdline | tr '\0' '\n' | head -1"` 就能看到 comm 和 argv[0]，按上表挑。

#### 6.3.4 易踩坑

1. **`classes[]` 顺序敏感**：classifier 是有序匹配（详 §3 / §4.2），第一命中即归类。**`dmabuf` 必须排在 `anon_inode` / `regular_file` 之前**，否则 `anon_inode:dmabuf` 会被 `anon_inode:` 通配规则吸走，dmabuf 类永远 0 计数。**`regular_file` 必须排最后**，因为它的 `match_link` 是 `"starts_with": "/"`，会兜底所有 `/` 开头的 readlink。
2. **改了 `forensic.tasks[]` 用了新二进制 / 新路径** → 必改 `device/voyah/common/sepolicy/system_ext/private/polaris_monitor.te`：
   - 新二进制在 `/system/bin/` → `system_file:file execute_no_trans` 已覆盖
   - 新二进制在 `/vendor/bin/` → 需要加 vendor 域 execute 权限
   - 读新路径文件 → 加 `<label>:file r_file_perms`
   - 写新输出目录（不是 `/log/perf/`）→ 加新 label 的写权限
3. **改完不重启不生效**：当前没有 SIGHUP reload，`adb shell setprop` 也不触发重读。流程必须是 `adb push monitor.json /system/etc/polaris/ && adb shell stop polaris-monitor && adb shell start polaris-monitor`。
4. **JSON 语法错=静默失监**：jsoncpp 解析失败时 `Config::Load()` 返回 false → 整个 fd_leak 段走 struct 默认值（`enable=false`） → 监控不启动，logcat 只有一行 `Config::Load: JSON parse failed; falling back to defaults`。**改完务必看 logcat 里的** `FdLeakMonitor: initialized (interval=Xs, classes=Y, whitelist=Z)`，Y/Z 数字必须和你的配置对得上。
5. **`global_forensic.enable: false` 不停 fd_leak 检测**：detection 仍跑、上报仍发，只是 incident 目录不落盘、log_path 字段为 nullptr。要彻底停才用 `fd_leak.enable: false`。
6. **白名单加了但 logcat 看不到对应进程被监控**：8 成是 comm 被 binder 线程池盖了。改用 `package` + 全路径 argv[0] 即可（参见 §6.3.3 判断方法）。

#### 6.3.5 改完如何验证

```bash
# 1. 推到设备 + 重启
adb push monitor.json /system/etc/polaris/monitor.json
adb shell stop polaris-monitor && adb shell start polaris-monitor

# 2. 看启动日志，确认配置被解析
adb logcat -d -s polaris-monitor:V | grep -E "Config::Load|FdLeakMonitor:|SanityClampConfig"
# 期望看到：
#   Config::Load: fd_leak loaded (enable=1, classes=5, whitelist=39, interval=30s)
#   FdLeakMonitor: initialized (interval=30s, classes=5, whitelist=39)
# 数字与你的修改要对得上；clamp 警告也会在这里出

# 3. 确认是否落到目标进程（用 adas 举例）
PID=$(adb shell pgrep -f com.voyah.cockpit.adas | head -1)
# 等 1 个 interval_sec 后再查
adb shell ls /log/perf/fd_monitor/ | grep $PID  # 触发后会有 incident 目录

# 4. 观察 5~10 分钟有没有误报
adb shell tail -f /log/perf/fd_monitor/incidents.log
```

测试 / 调参场景请用 `native/tests/fdleak_tester/sample_monitor.json`（已含 polaris-fdtest 白名单 + 调小的 threshold/warmup），临时覆盖 `/system/etc/polaris/monitor.json` 即可（验证完记得 push 回生产版本）。

---

## 7. SELinux 与权限

### 7.1 `polaris_monitor.te` 增量

```te
# --- 读白名单进程的 /proc ---
# 说明：vendor 域跨读 appdomain /proc 通常撞 neverallow，采用分域精确放行；
#      app 侧覆盖通过 dumpsys meminfo 间接观测。
allow polaris_monitor surfaceflinger:dir  r_dir_perms;
allow polaris_monitor surfaceflinger:file r_file_perms;
allow polaris_monitor cameraserver:dir    r_dir_perms;
allow polaris_monitor cameraserver:file   r_file_perms;
allow polaris_monitor mediaserver:dir     r_dir_perms;
allow polaris_monitor mediaserver:file    r_file_perms;
allow polaris_monitor system_server:dir   r_dir_perms;
allow polaris_monitor system_server:file  r_file_perms;
allow polaris_monitor hal_graphics_composer_server:dir  r_dir_perms;
allow polaris_monitor hal_graphics_composer_server:file r_file_perms;

allow polaris_monitor self:global_capability_class_set { dac_read_search };

# --- 执行取证命令 ---
allow polaris_monitor dumpsys_exec:file { getattr execute execute_no_trans };
allow polaris_monitor system_file:file  { getattr execute execute_no_trans };

# --- 写 /log/perf/fd_monitor ---
# 实测车机 /log/perf 的实际 label 是 log_file（与 polarisd /log/perf/cmd_results 同源）
# 不是 perf_log_file；以目标设备 file_contexts 为准
allow polaris_monitor log_file:dir  { search getattr read open create write add_name remove_name };
allow polaris_monitor log_file:file { create write open getattr read setattr unlink };

# --- dmabuf class Stage 2 best-effort：debugfs bufinfo（可选；缺失不影响主路径）---
allow polaris_monitor debugfs_dma_buf:dir  r_dir_perms;
allow polaris_monitor debugfs_dma_buf:file r_file_perms;

# --- socket class Stage 2：ss / net diag 读取需要 ---
allow polaris_monitor self:netlink_inet_diag_socket { create_socket_perms_no_ioctl nlmsg_read };
allow polaris_monitor self:netlink_unix_diag_socket { create_socket_perms_no_ioctl nlmsg_read };
```

**适配注意**：

- 上述精确域名（`hal_graphics_composer_server` 等）以目标平台 sepolicy 中实际 type 为准，P4 阶段用 `seinfo -t | grep hal_` 核实
- `r_dir_file(polaris_monitor, appdomain)` **不要使用**，vendor 域跨读 app /proc 在 AOSP sepolicy 有 neverallow 命中风险；app 覆盖通过 `dumpsys meminfo <pkg>` 间接达成
- `netlink_*_diag_socket` 仅在选用 `ss -anpe` 时需要；若 socket class 全走 `cat /proc/<pid>/net/*` 路径则可省

### 7.2 `init.rc` 增量

```
group polaris_monitor readproc inet net_admin net_raw
```

`inet` / `net_admin` / `net_raw` 仅 socket class 取证需要；不启用 socket class 可不加。

### 7.3 `file_contexts`

`/log/perf` 在本工程的 `device/voyah/common/sepolicy/system_ext/private/file_contexts`
里实际 label 是 `log_file`（与 polarisd 写 `/log/perf/cmd_results/` 共用同一 label）。
P4 阶段 `restorecon -Rv /log/perf` 验证首次写盘成功。

---

## 8. 资源预算

| 项 | 目标 | 备注 |
|---|---|---|
| Stage 1 采样间隔 | 30 s（可配） | |
| Stage 1 单轮 CPU 时间 | < 25 ms (P99) | 8 进程白名单，5 个 class 同时分流；多 class 不增加 readdir 次数 |
| Stage 2 单次落盘耗时 | < 8 s | `max_concurrent_tasks=3` + per-task timeout |
| Stage 2 单次磁盘写入 | < 2 MB | 典型 incident |
| 常驻 RSS | < 1.5 MB | 窗口数据 × class 数 + 配置 |
| 稳态 CPU | < 0.05% | |
| 磁盘峰值占用 | ≤ max_total_mb（200 MB 默认） | LRU 轮转 |
| 告警延迟 | < interval_sec × min_samples | 默认最多 5 min |

---

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| 白名单进程频繁 fork/exec | `exact/prefix/package` 三种匹配；`package` 走 TTL cache |
| 被监控进程 crash 导致 PID 变化 | identity ≠ pid；`{pid, pid_start_clk}` 校验；消失/复用/替身立即丢全 class 窗口重建 |
| PID 复用（快速回收） | 必须叠加 `pid_start_clk`；不一致即视为新实例 |
| 同 buffer 多 fd 造成 dma-buf 假斜率 | `dedup_by=fdinfo_ino`（class 配置） |
| 同文件跨进程共享造成 regular_file 假斜率 | `dedup_by=fdinfo_dev_ino` |
| 新实例启动瞬间大量分配触发误报 | per-class `warmup_sec`（dmabuf 120 s / socket 30 s 等） |
| 进程 crash-loop 被反复判为泄漏 | `crash_loop_guard` 检测后改报 `process_crash_loop`，暂停**全部 class** 触发判定 `pause_monitor_sec` |
| 冷却被 crash-重启绕过 | 冷却键 = (identity, class)，跨 PID 生效 |
| 跨 class 误抑制 | 冷却键带 class 维度，dma-buf 触发不抑制同进程的 socket 触发 |
| crash 暂停窗口短于冷却 | 约束 `pause_monitor_sec >= 2 × max(class.cooldown_sec)` |
| 误报刷爆磁盘 | per-(identity, class) `cooldown_sec` + `global_min_interval_sec` + `max_total_mb` + LRU |
| Stage 2 并发冲顶 servicemanager / SF | 跨 class 共享 `max_concurrent_tasks`（默认 3）+ 每 task `ioprio_set IDLE` |
| 取证命令 hang | 每 task 独立 `timeout_ms`，超时 `SIGKILL` 子进程 |
| `dumpsys` 递归采自己导致死锁 | whitelist 显式排除 `polaris-monitor` 自身 |
| `${SUSPECT_PROC}` 被污染 | argv 展开前白名单正则 `[A-Za-z0-9._-]+` 校验 |
| `dumpsys SurfaceFlinger --dmabuf` 子命令版本差异 | P0 前核实目标 AOSP 分支；不存在则删除该 task |
| `ss` 二进制在量产镜像缺失 | socket class fallback 到 `cat /proc/<pid>/net/*` |
| `/bin/cat` 不存在 | 统一用 `/system/bin/cat` |
| debugfs 未挂载 | dmabuf class 的 `bufinfo` task `condition=path_readable` 自动跳过 |
| classifier regex 顺序错排 | dmabuf 必须在 anon_inode / regular_file 之前；P0 加单测确保 |
| 新增 class 引入未知大对象 | 默认 `enable: false` 进灰度，观察 N 天后开 |
| 配置文件损坏 | 加载失败时保守默认（`enable=false`），不影响 daemon 主流程 |
| polarisd 不可达 | 事件落本地 `incidents.log`，恢复后重传（走现有 polaris_client） |

---

## 10. 典型场景覆盖

### 10.1 dmabuf class

| 场景 | 现象 | 捕获路径 |
|---|---|---|
| App `HardwareBuffer` 未 close | SF/app distinct buffer 缓慢上涨 | Stage 1 → Stage 2 `dumpsys SurfaceFlinger --dmabuf` + `dmabuf_dump <pid>` |
| `SurfaceTexture` / `ImageReader` 漏 close | app distinct buffer 持续增加 | 同上 |
| SF layer cache 清理异常 | `surfaceflinger` distinct buffer 持续抬升 | Stage 1 直接命中 |
| HWC 持有过多 buffer | `hwcomposer-*` distinct buffer 异常 | Stage 1 |
| codec2 buffer pool 未归还 | `media.codec` / `mediaserver` distinct buffer 上涨 | Stage 1；可加 `dumpsys media.codec` |
| Camera HAL buffer queue 未释放 | `cameraserver` distinct buffer 上涨 | Stage 1；可加 `dumpsys media.camera` |
| HAB 会话未 `habmm_socket_close`（dma-buf 维度） | HAB daemon distinct buffer 缓慢上涨 | Stage 1 |
| virtio backend PVM 侧释放异常 → GVM 残留 | `qcom,system` heap 字节级上涨，distinct 数可能正常 | dmabuf class `bytes_mb` 规则 + Stage 2 `bufinfo` best-effort；fd 路径覆盖不到的属已知局限（§1.3） |

### 10.2 socket class

| 场景 | 现象 | 捕获路径 |
|---|---|---|
| HTTP/gRPC 客户端连接未 close | `ESTABLISHED` 累积 | Stage 1 fd 数 + Stage 2 `ss -anpe` 看对端分布 |
| `accept()` 后未 close | 服务端 fd 上涨 | Stage 2 `proc/<pid>/net/tcp` 看 LISTEN/ACCEPT |
| HAL 客户端未释放 binder/UDS | UDS fd 累积 | Stage 2 `proc/<pid>/net/unix` |

### 10.3 regular_file class

| 场景 | 现象 | 捕获路径 |
|---|---|---|
| 日志/配置文件未 close | distinct (dev,ino) 缓慢上涨 | Stage 1；Stage 2 `ls -l /proc/<pid>/fd` 取文件名分布 |
| 临时文件 fd 累积 | 同上 | 同上 |

### 10.4 anon_inode class

| 场景 | 现象 | 捕获路径 |
|---|---|---|
| `epoll_create` 未 close | `[eventpoll]` fd 上涨 | Stage 1；Stage 2 `ls -l /proc/<pid>/fd` 看 anon_inode sub-tag 分布 |
| `eventfd` / `timerfd` 泄漏 | 对应 anon_inode tag 上涨 | 同上 |

### 10.5 pipe class

| 场景 | 现象 | 捕获路径 |
|---|---|---|
| `popen()` 未 `pclose` | pipe fd 累积 | Stage 1；Stage 2 `ls -l /proc/<pid>/fd` |
| 父子进程 pipe 写端未关 | 同上 | 同上 |

---

## 11. 与其它监控的协同

- **resource plugin**：继续提供宏观 `MemAvailable` / `Shmem` / `CmaFree` / `Slab` 趋势，是 kernel-only 泄漏的唯一抓手；两者在 polarisd 侧做时间相关性分析
- **process plugin**：`fd count` 总数与本方案的各 class 计数对比；总数涨而本方案各 class 都未触发 → 提示有未识别 class（扩 classifier 规则）
- **PVM 侧 polaris-monitor**：同款设计部署到 PVM，捕获 backend 进程泄漏
- **开发取证**：若某次 incident 数据不足，打调试镜像复跑，debugfs 挂载后 `bufinfo.txt` 自动补齐

---

## 12. 开发路线图

| 阶段 | 内容 | 预计工时 |
|---|---|---|
| P0 | Plugin 框架 + `FdScanner`（多 class 分流 + 多种 dedup）+ `FdClassifier`（有序 regex）+ 白名单解析 + classifier 顺序单测 | 2.5d |
| P1 | `InstanceRegistry`（starttime 校验、Reconcile、per-class 窗口）+ `TriggerPolicy`（per-class slope/monotonic 配置驱动） | 2d |
| P2 | `ForensicCollector` + `DumpTask` executor（复用 `polarisd::ChildProcess` + timeout + 跨 class 共享并发上限 + ioprio_set） | 2d |
| P3 | dmabuf class forensic_tasks 落地 + `dumpsys SF --dmabuf` 子命令核实 | 1d |
| P4 | socket / regular_file / anon_inode / pipe class forensic_tasks 落地 + `ss` / `ls` 可用性核实 | 1.5d |
| P5 | `/log/perf/fd_monitor` 目录管理 + LRU 轮转 + incidents.log（带 class 索引） | 1d |
| P6 | SELinux 策略联调（精确域放行 + netlink_diag socket + `file_contexts` `restorecon`）+ `init.rc` | 2d |
| P7 | 上报 schema 与 polarisd 对齐（per-class event_type） | 1d |
| P8 | 性能 / 稳定性压测（每 class 各跑一组故障注入，连续 72h） | 3d |

**合计**：~16 人日。

---

## 13. 上线验证目标

P8 阶段 72 小时压测需满足：

1. 稳态 CPU ≤ 0.1%，RSS 增长 ≤ 100 KB/h
2. **每个启用的 class** 各注入「每分钟泄漏 5 个对象」故障，≤ 10 min 内触发各自告警并落盘
3. **每个启用的 class** 各注入「每分钟泄漏 500 个对象」故障，≤ 2 min 内触发
4. 连续 72h 磁盘占用 ≤ 200 MB（验证跨 class 共享 LRU 轮转）
5. 随机 kill 白名单进程，daemon 不崩；下次重生后全 class 窗口自动重建
6. 取证命令人为 hang，executor 在 `timeout_ms` 后 `SIGKILL`，主循环不阻塞
7. dmabuf class：伪造同一进程对同 buffer `dup` 10 次，`distinct` = 1（验证 `fdinfo_ino` 去重）
8. regular_file class：伪造跨进程共享同文件 5 次，每进程 distinct = 1（验证 `fdinfo_dev_ino` 去重）
9. socket class：伪造 ESTABLISHED 累积，触发后 `ss.txt` 落盘且对端分布可读
10. 同进程同时触发 dmabuf 与 socket 两个 class，互不抑制（验证 (identity, class) 冷却键）
11. 伪造进程短时 4 次 crash-restart，触发 `process_crash_loop` 事件而非任何 `*_leak_suspect`，且暂停期内全部 class 不再告警
12. classifier 规则顺序错排（dmabuf 放最后）能被单测捕获

---

## 14. 参考

- AOSP: `system/memory/libmeminfo/libdmabufinfo/`
- AOSP: `system/memory/libmeminfo/libdmabufinfo/tools/dmabuf_dump.cpp`
- AOSP: `system/core/libutils/`（fd 操作约定）
- iproute2: `ss(8)` man / netlink inet_diag 协议
- Kernel doc: `Documentation/driver-api/dma-buf.rst`
- Kernel doc: `Documentation/filesystems/proc.rst`（`/proc/<pid>/fd`、`fdinfo`）
- 内部 wiki: `gunyah/android-guest-dma-buf-memory.md`
- polaris-monitor: `README.md`（本目录）
- 历史评估档：`DMABUF_MONITOR_DESIGN.md`（dma-buf 单一类型方案 A/B/C/D 对比、取舍过程）
