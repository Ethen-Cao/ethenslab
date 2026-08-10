+++
date = '2026-06-07T22:30:00+08:00'
draft = false
title = 'Android Low Memory Killer Daemon (LMKD) 源码机制与策略分析'
+++


## 简介
Android 系统的 Low Memory Killer Daemon (lmkd) 是一个运行在用户空间的守护进程，主要负责监控 Android 系统的内存状态。当系统内存压力较高时，lmkd 会根据一定的策略杀死最不重要的进程，以保证系统能够维持在可接受的性能水平。

在 Linux Kernel 4.12 之前，该工作通常由内核态的 `lowmemorykiller` 驱动完成。随着内核的发展，该内核驱动被移除，相关的逻辑被完全迁移到了用户空间的 `lmkd` 守护进程中。

AOSP 源码路径：`system/memory/lmkd`

---

## 核心机制与架构

lmkd 的工作流程可以分为以下几个核心环节：**初始化与配置解析**、**内存压力监控**、**受害者选择策略**以及**进程击杀执行**。

```mermaid
graph TD
    subgraph Initialization ["1. 初始化与配置"]
        A[解析 lmkd.rc 属性配置] --> B[建立 AMS 通信 Socket]
        B --> C[设置 SCHED_FIFO 实时优先级]
        C --> D[初始化 epoll 与 Reaper 线程池]
    end

    subgraph Monitoring ["2. 内存压力监控"]
        D --> E{内核支持 PSI?}
        E -- Yes --> F[注册 PSI 压力事件监听]
        E -- No --> G[注册 vmpressure 压力事件监听]
        F --> H((epoll_wait 等待唤醒))
        G --> H
    end

    subgraph Strategy ["3. 杀进程策略与决策"]
        H -- 触发内存压力事件 --> I[评估可用内存 / Swap / Thrashing]
        I --> J[从 OOM_SCORE_ADJ_MAX 向下遍历 procadjslot_list]
        J --> K{开启 kill_heaviest_task <br> 或 为感知级进程?}
        K -- Yes --> L[选择当前 score 下占用内存最多的进程]
        K -- No --> M[选择链表尾部最旧的进程]
    end

    subgraph Execution ["4. 击杀执行与清理"]
        L --> N[epoll 注册 pidfd 等待进程死亡]
        M --> N
        N --> O[将击杀任务投递给 Reaper 异步线程池]
        O --> P[Reaper 线程调用 pidfd_send_signal SIGKILL]
        P --> Q[process_mrelease 回收内存]
        Q --> R[更新状态、记录日志并上报 statsd]
        R --> H
    end
```

### 1. 初始化与配置 (Initialization)

- **启动方式**: lmkd 通过 `lmkd.rc` 配置文件被 `init` 进程启动，具有较高的权限（`DAC_OVERRIDE KILL IPC_LOCK SYS_NICE SYS_RESOURCE`），并设置为了 `critical` 服务（`class core`）。其中 `SYS_NICE` 用于设置 `SCHED_FIFO`，`IPC_LOCK` 用于 `mlockall` 锁定内存，`KILL` 用于发送信号，`DAC_OVERRIDE` 用于绕过文件权限检查，`SYS_RESOURCE` 用于提升资源限制。
- **调度优先级**: 为了保证即使在系统极度卡顿、资源耗尽时也能优先响应并进行杀进程释放内存，lmkd 在不使用内核态 lowmemorykiller 接口时（`use_inkernel_interface == false`），会通过 `sched_setscheduler(0, SCHED_FIFO, &param)` 将自身调度策略设为 `SCHED_FIFO` 实时优先级（priority = 1）。若内核 lowmemorykiller 可用（`use_inkernel_interface == true`，默认值），则不会设置实时优先级。
- **通信套接字**: 初始化期间通过 `android_get_control_socket("lmkd")` 获取到 `ActivityManagerService` (AMS) 用来与其通信的 Unix Domain Socket (`/dev/socket/lmkd`)。AMS 会通过此套接字更新各个进程的 `oom_score_adj`。

### 2. 内存压力监控 (Memory Pressure Monitoring)

lmkd 使用 `epoll` 来监听内存压力事件。当前 lmkd 支持两种主要的内存压力监测方式：

#### 2.1 PSI (Pressure Stall Information) - 推荐 & 默认
在支持 PSI 的较新内核上，lmkd 优先使用 PSI 进行监控。在 `init_monitors()` 函数中，如果系统属性允许且内核支持，会调用 `init_psi_monitors()`。
- PSI 通过 `/proc/pressure/memory` 暴露系统因为内存不足而导致进程停顿（Stall）的时间比例。
- lmkd 针对不同压力级别配置了不同的阈值（partial stall 与 complete stall 的时长），利用 PSI 的 epoll 触发机制来实时唤醒 lmkd。默认阈值：partial stall（MEDIUM 级别）为 **70ms**（低 RAM 设备为 200ms），complete stall（CRITICAL 级别）为 **700ms**，监控窗口为 **1000ms**。可通过 `ro.lmk.psi_partial_stall_ms`、`ro.lmk.psi_complete_stall_ms`、`ro.lmk.psi_window_size_ms` 属性覆盖。
- PSI 相比于旧的机制更加精准，能够直接反映出“内存不足对 CPU 执行造成的延迟影响”。

**关于 `/proc/pressure/memory` 的输出字段含义：**
PSI 节点输出的数据通常如下所示：
```text
some avg10=0.00 avg60=0.00 avg300=0.00 total=0
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
```
- **`some` (部分阻塞)**: 表示系统中**至少有一个**非空闲进程因为等待内存资源而被阻塞。即使有其他进程还在运行，这也反映了系统由于内存不足而产生的总体延迟成本。
- **`full` (完全阻塞)**: 表示系统中**所有**非空闲进程都在同一时刻因为等待内存资源而被阻塞。这是一种严重状态，此时 CPU 完全闲置，等待内存操作完成，这是对用户体验产生直接卡顿影响的核心指标。
- **`avg10`, `avg60`, `avg300`**: 分别表示在过去 10 秒、60 秒、300 秒内，系统处于对应阻塞状态的时间百分比（范围 0-100）。例如 `avg10=5.00` 意味着过去 10 秒中有 5% 的时间处于阻塞状态。
- **`total`**: 记录了系统自启动以来，处于该阻塞状态的累计总时间（单位：微秒）。
*注：LMKD 通过向该接口写入特定的阈值配置（如 `ro.lmk.psi_partial_stall_ms`），并通过 `epoll` 等待内核的自动唤醒通知，从而避免了不断轮询带来的额外 CPU 开销。*

#### 2.2 vmpressure (基于 Cgroup V1 的回退机制)
当不支持 PSI 时，lmkd 会回退使用旧的 `vmpressure` 机制。
- 依赖于 cgroup v1 的 `memory.pressure_level` 接口。
- 分为 `LOW`, `MEDIUM`, `CRITICAL` 三个级别。

### 3. 杀进程策略与决策 (Kill Strategy & Decision Making)

当 lmkd 接收到内存压力事件后，会评估当前系统的可用内存、Swap 使用情况、Thrashing（抖动）状态，然后决定是否需要杀进程以及杀死哪个进程。

核心寻找受害者的逻辑在 `find_and_kill_process()` 函数中：
1. **遍历 `oom_score_adj`**: lmkd 内部维护了 `procadjslot_list`——一个长度为 2001 的双向链表**数组**（通过宏 `ADJTOSLOT(adj) = adj + 1000` 将 oom_score_adj（范围 -1000 ~ 1000）映射到数组下标）。每个 oom_score_adj 值对应一个独立的链表槽位，存储着该 adj 级别的所有进程。当需要杀进程时，循环会从 `OOM_SCORE_ADJ_MAX` (1000，即优先级最低的后台缓存进程) 开始向下遍历各个槽位，直到当前的 `min_score_adj` 阈值。
2. **挑选受害者 (`choose_heaviest_task`)**: 
    - 如果配置了 `ro.lmk.kill_heaviest_task=true`，lmkd 会在当前 score 级别下挑选占用内存最多（heaviest）的进程 `proc_get_heaviest(i)`。该函数遍历该槽位的链表，通过读取每个进程的 `/proc/<pid>/statm` 获取 RSS 页数，选择 RSS 最大的进程，从而用最小的击杀代价释放最多的内存。
    - 否则，通过 `proc_adj_tail(i)` 返回链表尾部的进程（即最早插入该槽位的进程，因 lmkd 在进程注册时通过 `adjslot_insert` 将新进程插入链表头部，故尾部为驻留最久的进程）。
    - *优化*: 即便 `kill_heaviest_task` 未开启，当遍历到用户可感知级别的进程（`i <= PERCEPTIBLE_APP_ADJ`，即 oom_score_adj ≤ 200）时，lmkd 也会强制切换为挑选 heaviest task，因为误杀可见进程代价很大，尽可能一次释放足够多的内存以减少总体受害者数量。

### 4. 击杀执行与 Reaper (Execution & Reaper)

挑选到受害者后，流程进入 `kill_one_process()` 函数执行真正的击杀：

1. **防止 PID 复用 (PID Reuse)**: lmkd 引入了 `pidfd` (如果内核支持)。在进程注册时（AMS 通过 socket 发送 `PROCPRIO` 命令），lmkd 会调用 `pidfd_open(pid, 0)` 获取该进程的 pidfd 并保存在 `struct proc` 中。传统的 `kill(pid, SIGKILL)` 存在竞态条件（在发出信号前，原进程可能已经退出，PID 被一个重要系统进程复用）。通过 `pidfd_send_signal` 向已持有的 pidfd 发送信号，lmkd 能够保证 100% 安全地杀死目标进程。
2. **异步清理 (Reaper Thread Pool)**: 实际的击杀系统调用通过 `reaper.kill()` 封装。
    - lmkd 拥有一个 Reaper 线程池（通过 `init_reaper()` 初始化），包含固定 **2 个线程**（`THREAD_POOL_SIZE = 2`），线程名称为 `lmkd_reaper0` 和 `lmkd_reaper1`。
    - 杀进程和等待进程彻底死亡并释放内存可能耗时，为了不阻塞 lmkd 主线程继续响应其他内存压力，击杀请求 (target_proc) 会被投递到 Reaper 线程池进行异步处理 (`async_kill`)。
    - `reaper.kill()` 内部流程：先尝试异步投递（`async_kill`），若线程池有空闲线程则将请求入队；若线程池已满（两个线程均忙），则**回退到同步模式**，在主线程直接调用 `pidfd_send_signal`。Reaper 线程执行完 SIGKILL 后，还会调用 `process_mrelease(pidfd, 0)` 主动回收目标进程的内存。
3. **状态日志与上报**: 杀死进程后，lmkd 会记录内核的剩余内存等信息，打印出类似 `Kill 'app_name' (pid), uid, oom_score_adj...` 的日志，并通过 socket 更新内部状态，并且会上报 statsd 用于系统稳定性分析。

---

## 5. 车机实际运行状态调研 (实车验证)

通过对车机实车环境的在线排查，我们验证了 `lmkd` 在实际生产环境中的工作机制与配置属性：

### 5.1 内存压力监控机制：PSI 验证
通过 `adb shell` 连接车机，并提取 `lmkd` 进程（PID: 581）打开的文件描述符，我们发现它持有 `/proc/pressure/memory` 的文件句柄：
```bash
l-wx------ 1 lmkd lmkd 64 2026-04-17 14:24 5 -> /proc/pressure/memory
l-wx------ 1 lmkd lmkd 64 2026-04-17 14:24 6 -> /proc/pressure/memory
```
**结论**：车机当前处于激活支持 PSI (Pressure Stall Information) 监控机制的状态，这是 LMKD 首选和推荐的精准压力监控方式，而非旧版的 `vmpressure`。

同时，我们还能在 `lmkd` 的打开句柄中看到大量如下条目：
```bash
lrwx------ 1 lmkd lmkd 64 2026-04-17 14:42 100 -> anon_inode:[pidfd]
```
这也证实了上文源码分析中的观点：`lmkd` 在进程注册时即获取 `pidfd` 并持久化保存，在生产环境中广泛运用了 `pidfd` 的特性，从而避免 PID 复用导致的误杀。

### 5.2 车机中与 LMKD 相关的核心属性配置
车机配置了诸多影响 lmkd 策略的 `ro.lmk.*` 属性，以下是车机内抓取到的相关属性及其技术含义解析：

| 属性名 (Property) | 设定值 | 含义解析 |
| --- | --- | --- |
| **`ro.lmk.kill_heaviest_task`** | `true` | **核心策略配置**。设为 true 意味着 LMKD 会优先杀掉同一个 oom_score_adj 级别下占用内存最多的进程（通过 `proc_get_heaviest` 遍历该槽位链表选择 RSS 最大的进程），而不是杀掉该槽位链表尾部最早注册的进程。通过牺牲微小的查询时间，换取以最少击杀次数释放最大的内存量。AOSP 默认值为 `false`。 |
| **`ro.lmk.kill_timeout_ms`** | `15` | **防止连杀抖动**。在执行一次击杀动作后，lmkd 暂停继续击杀的超时时间（毫秒）。车机配置为 15ms，说明允许较高频率的连杀操作。AOSP 默认值为 **100ms**。 |
| **`sys.lmk.minfree_levels`** | `18432:0, 23040:100, 27648:200, 32256:250, 55296:900, 80640:950` | **由 lmkd 发布的属性**（非读取）。lmkd 接收来自 AMS（ActivityManagerService）通过 socket 发来的 `LMK_TARGET` 命令后，将内存阈值（以 Page 为单位，通常 1 Page = 4KB）与对应的 oom_score_adj 分数的映射发布为此属性，供外部观察者使用（如调试、监控）。lmkd 内部的杀进程决策直接使用 AMS 传入的 `lowmem_minfree[]`/`lowmem_adj[]` 数组。 |
| **`sys.lmk.reportkills`** | `1` | 允许 LMKD 向客户端及 `statsd` 广播与上报进程被杀死的事件日志。 |

> **注意**: `ro.lmk.enable_adaptive_lmk`、`ro.lmk.enhance_batch_kill`、`ro.lmk.vmpressure_file_min` 等属性在车机上可能存在，但它们**不属于 AOSP lmkd 源码** (`system/memory/lmkd/`) 实现的属性，而是特定厂商/OEM 对 lmkd 进行私有修改后引入的自研特性。

## 总结

从 AOSP 的 `system/memory/lmkd` 源码中可以看出，现代的 Android Low Memory Killer 已经进化为了一个高度复杂的用户态守护进程。其核心数据结构 `procadjslot_list` 是一个包含 2001 个槽位的链表数组（每个 oom_score_adj 值一个槽位），杀进程策略从 `OOM_SCORE_ADJ_MAX` (1000) 向下遍历，支持 `kill_heaviest_task` 和感知级进程强制 heaviest 选择的优化。结合针对车机的实车调研，我们不仅证实了其对最新 `PSI` 特性（默认 partial=70ms/complete=700ms/window=1000ms）及 `pidfd` 防误杀功能（在进程注册时获取，非杀进程时才获取）的应用，还解析了当前系统调优策略的核心思路：通过 `kill_heaviest_task` 精准打击。需要注意，部分车机属性（如 `enable_adaptive_lmk`、`enhance_batch_kill`）为厂商私有修改，不属于 AOSP lmkd 源码范畴。

> **参考文件**:
> - `system/memory/lmkd/lmkd.cpp`: 主控制循环与逻辑判断
> - `system/memory/lmkd/reaper.cpp`: 异步击杀执行器
> - `system/memory/lmkd/README.md`: 属性配置参考
> - `system/memory/lmkd/lmkd.rc`: 启动配置文件