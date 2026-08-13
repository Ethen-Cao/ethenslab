+++
date = '2026-06-07T22:30:00+08:00'
draft = false
title = 'Android Low Memory Killer Daemon (LMKD) 源码机制与策略分析'
+++


## 简介

Android 系统的 Low Memory Killer Daemon（lmkd）是一个用户空间守护进程。它接收内核内存压力信号，结合 zone watermark、Swap、page-cache refault、reclaim 状态和进程 `oom_score_adj`，在系统进入不可接受的内存回收延迟前终止相对不重要的进程。

在 Linux Kernel 4.12 之前，该工作通常由内核态的 `lowmemorykiller` 驱动完成。随着内核的发展，该内核驱动被移除，相关的逻辑被完全迁移到了用户空间的 `lmkd` 守护进程中。

AOSP 源码路径：`system/memory/lmkd`。本文的实现细节以 8397 QSSI 中该仓库的 `6591d1e` 版本为基准；其他 Android 分支可能在属性、memevent 或厂商 hook 上存在差异。

---

## 核心机制与架构

lmkd 的工作流程可以分为四个环节：初始化、压力监控、决策与受害者选择、进程终止与回收。现代内核上的主路径是 PSI 驱动的新策略；vmpressure 和 minfree 属于兼容路径，不能与新策略混为一谈。

```mermaid
flowchart TD
    A[init 根据 lmkd.rc 启动服务] --> B[update_props 读取配置]
    B --> C[初始化 epoll 与控制 Socket]
    C --> D{存在可写的内核 LMK 接口?}
    D -- 是 --> E[使用内核 LMK 接口]
    D -- 否 --> F{PSI 已启用且初始化成功?}
    F -- 新 PSI 策略 --> G[mp_event_psi → __mp_event_psi]
    F -- PSI 旧策略 --> H[mp_event_common]
    F -- 否，回退 vmpressure --> H
    G --> I[每次评估至多选择一个受害者]
    H --> I
    I --> J[注册 pidfd 死亡等待并调用 reaper.kill]
    J --> K[主线程记录结果并通知订阅客户端]
    J -. 线程池可用 .-> L[Reaper: SIGKILL → process_mrelease]
    J -. 线程池忙或不支持异步 .-> M[主线程同步发送 SIGKILL]
    L --> N[pidfd 事件或 /proc 轮询确认进程死亡]
    M --> N
    K --> O[继续 epoll 或 PSI 窗口轮询]
    N --> O
```

### 1. 初始化与配置 (Initialization)

- **服务启动**：`init` 解析 `lmkd.rc` 并启动 lmkd；lmkd 本身不解析 rc 文件。服务属于 `class core`，被标记为 `critical`，并获得 `DAC_OVERRIDE KILL IPC_LOCK SYS_NICE SYS_RESOURCE` capabilities。
- **属性读取**：`update_props()` 读取 `ro.lmk.<name>`。若存在 `persist.device_config.lmkd_native.<name>`，后者优先，用于运行时实验和重新初始化监控器。
- **控制通道**：`init` 预先创建 `/dev/socket/lmkd`。lmkd 通过 `android_get_control_socket("lmkd")` 取得监听 socket，AMS 等客户端连接后发送 `LMK_TARGET`、`LMK_PROCPRIO`、订阅和属性更新命令。
- **内核接口探测**：`use_inkernel_interface` 虽然在静态初始化时为 `true`，但运行时会根据内核 lowmemorykiller 的 `minfree` 节点是否可写重新赋值。因此它不是现代设备的实际默认工作模式。
- **调度与锁页**：未使用内核 LMK 接口时，主线程调用 `mlockall(MCL_CURRENT | MCL_FUTURE | MCL_ONFAULT)`，并设置为 `SCHED_FIFO`、实时优先级 1，以降低严重内存压力下的调度延迟。Reaper 工作线程随后被显式设置为 `SCHED_OTHER`。
- **事件循环**：控制 socket、压力监控 FD、pidfd、Reaper 通信管道和 memevent ring buffer 都注册到同一个 epoll 实例。Reaper、watchdog 初始化完成后，主线程进入 `mainloop()`。

### 2. 内存压力监控 (Memory Pressure Monitoring)

lmkd 使用 `epoll` 监听压力事件。PSI 和 vmpressure 是两种互斥的主压力触发器，BPF memevent 则补充 reclaim 状态、厂商事件和 watermark 更新通知。

#### 2.1 PSI（Pressure Stall Information）

`init_monitors()` 默认优先初始化 PSI。新策略关闭 LOW 级别触发器，注册两个 `/proc/pressure/memory` 触发器：

- MEDIUM：`PSI_SOME`，默认在 1000 ms 窗口内累计 stall 70 ms；低 RAM 设备默认 200 ms。
- CRITICAL：`PSI_FULL`，默认在 1000 ms 窗口内累计 stall 700 ms。

对应属性为 `ro.lmk.psi_partial_stall_ms`、`ro.lmk.psi_complete_stall_ms` 和 `ro.lmk.psi_window_size_ms`。lmkd 将换算后的触发表达式写入 PSI FD，而不是把属性名直接写入 `/proc/pressure/memory`。

**关于 `/proc/pressure/memory` 的输出字段含义：**
PSI 节点输出的数据通常如下所示：
```text
some avg10=0.00 avg60=0.00 avg300=0.00 total=0
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
```
- **`some`（部分阻塞）**：测量范围内至少有一个非空闲任务因内存压力而停顿，其他任务仍可能继续执行。
- **`full`（完全阻塞）**：测量范围内所有非空闲任务同时因内存压力而停顿。它表示该工作负载没有任务能够向前推进，但不等价于所有 CPU 硬件完全空闲；内核回收线程、中断或范围外任务仍可能运行。
- **`avg10`, `avg60`, `avg300`**: 分别表示在过去 10 秒、60 秒、300 秒内，系统处于对应阻塞状态的时间百分比（范围 0-100）。例如 `avg10=5.00` 意味着过去 10 秒中有 5% 的时间处于阻塞状态。
- **`total`**: 记录了系统自启动以来，处于该阻塞状态的累计总时间（单位：微秒）。

PSI 触发事件在一个窗口内会被限频。收到事件后，lmkd 会启动主动轮询：通常每 100 ms 一次，在刚完成击杀或 Swap 低时缩短为 10 ms。轮询通常在 `psi_window_size_ms` 后停止，但新的 PSI 事件、一次成功击杀或持续 direct reclaim 可以重新开始或延长该阶段。因此 PSI 避免了常驻高频轮询，但一次 PSI 事件仍可能派生多次评估。

#### 2.2 vmpressure（Cgroup v1 回退机制）

当 `ro.lmk.use_psi=false` 或 PSI 初始化失败时，lmkd 尝试注册 cgroup v1 的 `memory.pressure_level`，级别分为 LOW、MEDIUM、CRITICAL。vmpressure 以及 PSI 的旧策略都进入 `mp_event_common()`；它们不会进入 `__mp_event_psi()`。该兼容路径依赖 memcg v1，在纯 cgroup v2 系统上不可用。

#### 2.3 BPF memevent 与 vmstat 回退

启动完成后，lmkd 尝试使用 `MemEventListener` 订阅以下 BPF memevent：

- `DIRECT_RECLAIM_BEGIN/END`：精确维护 direct reclaim 状态和开始时间；
- `KSWAPD_WAKE/SLEEP`：维护 kswapd reclaim 状态；
- `VENDOR_LMK_KILL`：接收厂商定义的击杀请求；
- `UPDATE_ZONEINFO`：在内核参数变化后刷新聚合 watermark。

若 memevent 不可用，lmkd 通过 `/proc/vmstat` 中 `pgscan_direct`、`pgscan_kswapd` 和 `pgrefill` 的变化推断 reclaim 活动。该回退只能判断活动状态，不能可靠计算 direct reclaim 的起止时长；因此源码会把 `direct_reclaim_threshold_ms` 置 0，禁用 `DIRECT_RECL_STUCK`。

### 3. 杀进程策略与决策 (Kill Strategy & Decision Making)

用户空间 lmkd 存在两套决策路径：

- **新 PSI 策略**：`mp_event_psi()` 调用 `__mp_event_psi()`，依据 zone watermark、有效 Swap、page-cache thrashing 和 reclaim 状态决策。`use_new_strategy` 的默认值为 `low_ram_device || !use_minfree_levels`。
- **兼容策略**：`mp_event_common()` 处理 vmpressure，或处理显式启用的 PSI 旧策略。它可以使用 minfree 阈值，也可以按 vmpressure level 的 `oom_score_adj` 阈值击杀。

后续 §3.1～§3.4 主要描述新 PSI 策略；兼容策略单独在 §3.5 说明。

#### 3.1 前置条件检查

在评估是否杀进程之前，lmkd 先执行以下检查：

- **等待前一个受害者退出**：只有前一次击杀仍处于 pending 状态，并且 `kill_timeout_ms=0`（无限等待）或尚未超过超时时间时，才跳过本次评估。若 pidfd 已通知进程死亡，可在超时前继续评估；若进程到达超时仍未退出，lmkd 停止等待并允许选择下一个受害者。
- **刷新内存状态**：读取 `/proc/vmstat` 和 `/proc/meminfo`，计算有效 Swap、reclaim 类型、thrashing 及 watermark。
- **无 reclaim、无 refault 时提前退出**：仅对 PSI 事件源生效。若既不在 direct reclaim/kswapd reclaim 中，`workingset_refault_file` 也未增加，则本轮不击杀。reclaim 状态优先由 memevent 给出，memevent 不可用时才根据 vmstat 计数器变化推断。

#### 3.2 核心指标采集

lmkd 通过读取以下内核接口采集决策所需的各项指标：

| 指标 | 来源与计算 | 决策含义 |
|------|------------|----------|
| **Zone watermark** | `/proc/zoneinfo`；先聚合各 zone 的 `min/low/high + max_protection`，再用 `nr_free_pages - cma_free` 比较 | 判断非 CMA free 是否跌破内核保留水位 |
| **File thrashing** | `/proc/vmstat` 的 `workingset_refault_file` 增量，相对于窗口开始时的 `active_file + inactive_file` | 衡量文件页刚被回收又立即重新访问的比例 |
| **有效 Swap 余量** | `get_free_swap()`；启用压缩比估算时取 `min(SwapFree, easy_available × ratio / div)` | 避免把没有足够 RAM 支撑的 zram 空闲槽位视为真正可用 Swap |
| **Swap utilization** | `swap_used / (active_anon + inactive_anon + shmem + swap_used)`，其中 `swap_used = SwapTotal - get_free_swap()` | 使用“有效 Swap”反推已用量，衡量可换出匿名工作集已有多少进入 Swap；它不是 `/proc/meminfo` 中原始的 `(SwapTotal - SwapFree) / SwapTotal` |
| **Reclaim 类型** | 优先使用 BPF memevent；不可用时观察 `pgscan_direct`、`pgscan_kswapd`、`pgrefill` | 区分会阻塞分配者的 direct reclaim 与后台 kswapd reclaim |
| **Direct reclaim 时长** | 仅在 memevent 能提供 BEGIN/END 时可靠计算 | 超过 `direct_reclaim_threshold_ms` 时可触发 `DIRECT_RECL_STUCK`；默认 0，禁用 |
| **PSI full avg10** | `/proc/pressure/memory` 的 `full avg10` | 若严格大于 `stall_limit_critical`，最终把 `min_score_adj` 覆盖为 0 |

默认 `easy_available = nr_free_pages + inactive_file`。设置 `relaxed_available_memory=true` 后，计算会纳入 active file、扣除 dirty，并按配置的压缩比估算匿名页换出后可释放的 RAM。`swap_is_low` 比较的是上述 `get_free_swap()` 结果与 `SwapTotal × swap_free_low_percentage / 100`，不是无条件使用 `/proc/meminfo` 的原始 `SwapFree`。

`get_lowest_watermark()` 返回的是“当前被突破的最低 watermark”，枚举值及含义如下：

| 返回值 | 有效 free 的范围 | 含义 |
|--------|------------------|------|
| `WMARK_MIN` | `< min` | min、low、high 均已突破，压力最严重 |
| `WMARK_LOW` | `[min, low)` | low、high 已突破 |
| `WMARK_HIGH` | `[low, high)` | 仅 high 已突破 |
| `WMARK_NONE` | `>= high` | 未突破 watermark |

因此源码中的枚举比较需要结合上述顺序理解：

- `wmark < WMARK_LOW` 只可能是 `WMARK_MIN`，表示有效 free 已低于 **min**。
- `wmark < WMARK_HIGH` 可能是 `WMARK_MIN` 或 `WMARK_LOW`，表示有效 free 已低于 **low**，而不是仅仅低于 high。

Thrashing 以 1000 ms 为重置周期。窗口内的基本计算为：

```text
thrashing = refault_file_delta × 100 / (base_file_lru + 1)
           + prev_thrash_growth
```

`base_file_lru` 是窗口开始、初始化或完成击杀后记录的 file LRU 大小，并非每次读取时的瞬时值。跨窗口时，旧增长量通常按经过的窗口数右移衰减；若仅跨一个窗口且上一窗口仍超过阈值，代码会暂时保留该值，以便新受害者出现后重试。因 thrashing 成功击杀后，动态 `thrashing_limit` 按当前值乘以 `(100 - decay_pct) / 100` 继续降低；进入新的重置窗口时恢复为基础阈值。

`critical_stall` 使用严格的 `full.avg10 > stall_limit_critical`。默认 `stall_limit_critical=100`，而 PSI 百分比正常范围最大为 100，因此默认配置实际上禁用了该覆盖；只有把阈值配置为小于 100 时才可能生效。

#### 3.3 杀进程决策树 (Kill Reason Decision Tree)

在 `__mp_event_psi()` 中，以下条件按优先级从高到低依次检查，**命中任意条件即决定杀进程**：

| 优先级 | Kill Reason | 触发条件 | 含义 |
|--------|-------------|----------|------|
| 1 | **VENDOR** | 收到 `MEM_EVENT_VENDOR_LMK_KILL` | 使用厂商事件携带的 reason 和 `min_oom_score_adj` |
| 2 | **PRESSURE_AFTER_KILL** | `cycle_after_kill && wmark < WMARK_LOW` | 上一轮已选中受害者并成功发起击杀后的下一评估中，有效 free 仍低于 **min** watermark，说明释放速度或释放量不足 |
| 3 | **NOT_RESPONDING** | 收到真实的 PSI CRITICAL 事件，即 `level == CRITICAL && events != 0` | `PSI_FULL` 在监控窗口内超过 complete-stall 触发阈值；轮询调用不会命中该分支 |
| 4 | **LOW_SWAP_AND_THRASHING** | `swap_is_low && thrashing > thrashing_limit_pct` | 有效 Swap 低且文件页 refault 超过基础阈值 |
| 5 | **LOW_MEM_AND_SWAP** | `swap_is_low && wmark < WMARK_HIGH` | 有效 free 低于 **low** watermark，同时有效 Swap 低 |
| 6 | **LOW_MEM_AND_SWAP_UTIL** | `wmark < WMARK_HIGH && swap_util_max < 100 && swap_util > swap_util_max` | 有效 free 低于 low，匿名可换出工作集的 Swap 利用率过高；默认 `swap_util_max=100`，该分支禁用 |
| 7 | **LOW_MEM_AND_THRASHING** | `wmark < WMARK_HIGH && thrashing > thrashing_limit` | 有效 free 低于 low，且 refault 超过当前动态阈值 |
| 8 | **DIRECT_RECL_AND_THRASHING** | `reclaim == DIRECT_RECLAIM && thrashing > thrashing_limit` | 分配者在 direct reclaim 中，同时文件页持续 refault |
| 9 | **DIRECT_RECL_STUCK** | direct reclaim 持续时间超过非零阈值 | memevent 显示 direct reclaim 长时间未结束；默认禁用 |
| 10 | **LOW_FILECACHE_AFTER_THRASHING** | `check_filecache && file_lru_kb < filecache_min_kb` | thrashing 分支置位后，在后续评估中确认 file LRU 仍低；默认 `filecache_min_kb=0`，该分支禁用 |
| 11 | **LOW_MEM** | 其他分支均未命中，且 `wmark < WMARK_HIGH` | 有效 free 低于 low 的兜底分支，使用 `lowmem_min_oom_score`；将其配置为 1001 可禁用 |

`min_score_adj` 是受害者搜索的最低 `oom_score_adj`。各分支的取值并不相同：

| Kill Reason | `min_score_adj` |
|-------------|-----------------|
| VENDOR | 事件携带的 `min_oom_score_adj` |
| PRESSURE_AFTER_KILL | `pressure_after_kill_min_score`，默认 0 |
| NOT_RESPONDING | 0 |
| LOW_SWAP_AND_THRASHING / LOW_MEM_AND_SWAP | 当 min watermark 未突破且 thrashing 未到 critical 时为 201，否则为 0 |
| LOW_MEM_AND_SWAP_UTIL | 0 |
| LOW_MEM_AND_THRASHING / DIRECT_RECL_AND_THRASHING | thrashing 未到 critical 时为 201，否则为 0 |
| DIRECT_RECL_STUCK | 0 |
| LOW_FILECACHE_AFTER_THRASHING | 201 |
| LOW_MEM | `lowmem_min_oom_score`，默认 701，最小允许值被限制为 201 |

完成 kill reason 判定后，如果 `critical_stall` 为真，lmkd 会把上述结果统一覆盖为 0。该覆盖包括 VENDOR 分支，但如前所述，默认 `stall_limit_critical=100` 时实际上不会触发。

#### 3.4 受害者选择 (Victim Selection)

确定需要杀进程后，进入 `find_and_kill_process()` 函数选择具体受害者：

1. **遍历 `oom_score_adj`**: lmkd 内部维护了 `procadjslot_list`——一个长度为 2001 的双向链表**数组**（通过宏 `ADJTOSLOT(adj) = adj + 1000` 将 oom_score_adj（范围 -1000 ~ 1000）映射到数组下标）。每个 oom_score_adj 值对应一个独立的链表槽位，存储着该 adj 级别的所有进程。循环从 `OOM_SCORE_ADJ_MAX` (1000，即优先级最低的后台缓存进程) 开始**向下**遍历各个槽位，直到 `min_score_adj` 阈值（由上述决策树确定）。
2. **挑选受害者 (`choose_heaviest_task`)**: 
    - 如果配置了 `ro.lmk.kill_heaviest_task=true`，lmkd 会在当前 score 级别下调用 `proc_get_heaviest(i)`。该函数遍历槽位链表，读取 `/proc/<pid>/statm` 的 RSS 页数，选择估算 RSS 最大的进程。RSS 包含共享页，因此“heaviest”不保证实际净释放量一定最大。
    - 否则，`proc_adj_tail(i)` 返回链表尾部，即最早插入或最后一次移动到当前 adj 槽位的进程。进程的 adj 更新会将其重新插入链表头部，所以链表尾部不等同于系统中创建时间最早的进程。
    - *优化*: 即便 `kill_heaviest_task` 未开启，当遍历到用户可感知级别的进程（`i <= PERCEPTIBLE_APP_ADJ`，即 oom_score_adj ≤ 200）时，lmkd 也会强制切换为挑选 heaviest task，因为误杀可见进程代价很大，尽可能一次释放足够多的内存以减少总体受害者数量。
3. 每次调用 `find_and_kill_process()` 至多成功击杀一个进程。一次 PSI 触发会启动窗口轮询，窗口内可以多次调用该函数，因此“一次 PSI 事件”可能产生多个受害者；每次选择之间仍会重新读取内存状态，并受 pidfd 等待和 `kill_timeout_ms` 约束。

#### 3.5 兼容策略与 minfree

`mp_event_common()` 用于 vmpressure 或 PSI 旧策略。启用 `ro.lmk.use_minfree_levels=true` 时，它按以下方式模拟历史内核 lowmemorykiller：

```text
other_free = nr_free_pages - totalreserve_pages
other_file = max(0, nr_file_pages - shmem - unevictable - swap_cached)
```

随后从 AMS 下发的 `lowmem_minfree[]` / `lowmem_adj[]` 中找到第一个同时满足 `other_free < minfree` 和 `other_file < minfree` 的档位，并以对应 adj 作为 `min_score_adj`。

`LMK_TARGET` 无论当前是否使用 minfree 策略，都会保存这两组数组并发布 `sys.lmk.minfree_levels`。所以该属性只能证明 AMS 已下发阈值，不能单独证明当前决策正在使用它。只有兼容路径启用 `use_minfree_levels`，或使用内核 LMK 接口时，这些阈值才直接参与击杀条件。属性中的 minfree 单位是 page，换算时必须使用设备实际页大小，不能固定假设为 4 KiB。

### 4. 击杀执行与 Reaper (Execution & Reaper)

挑选到受害者后，流程进入 `kill_one_process()` 函数执行真正的击杀：

#### 4.1 pidfd 的生命周期

内核支持 `pidfd_open()` 时，lmkd 在客户端第一次发送 `LMK_PROCPRIO`、创建 `struct proc` 记录时就取得 pidfd，而不是等到准备击杀时才获取。后续 `pidfd_send_signal()` 作用于该文件描述符代表的进程对象，避免“目标退出、PID 被复用后信号误发给新进程”的竞态。若内核不支持 pidfd，记录中的 `pidfd=-1`，lmkd 回退到传统 `kill(pid, SIGKILL)` 和 `/proc/<pid>` 轮询。

在发信号前，`kill_one_process()` 还会读取 `/proc/<pid>/status`，检查 `Tgid == pid`，并取得进程名称、RSS 和 Swap。该检查可以发现部分 PID 复用或记录失效情形，但 pidfd 才是后续信号目标稳定性的核心保证。

#### 4.2 异步与同步击杀路径

`start_wait_for_proc_kill()` 先保存目标 PID 或 pidfd；有 pidfd 时还会把它注册到 epoll，等待退出通知。随后调用 `reaper.kill()`：

1. **异步路径**：仅当目标有 pidfd、Reaper 已初始化且活动请求数小于线程数时使用。`async_kill()` 复制 pidfd 并把请求放入队列，然后立即返回主线程。
2. **Reaper 工作线程**：`THREAD_POOL_SIZE=2`，初始化最多创建两个线程；若某次 `pthread_create()` 失败，实际线程数可以少于两个。工作线程调用 `pidfd_send_signal(SIGKILL)`，调整目标进程组的 task profile 和优先级，随后调用 `process_mrelease(pidfd, 0)`，尝试尽早回收正在退出进程的地址空间。
3. **同步回退**：线程池已满、Reaper 不可用或调用方要求同步时，主线程直接调用 `pidfd_send_signal()`；该路径不会调用 `process_mrelease()`。没有 pidfd 时则使用传统 `kill()`。

`process_mrelease()` 是对正在退出进程进行主动内存回收的尝试，不是主线程等待进程死亡的机制。目标可能已完成退出，因此该调用允许失败。真正的死亡状态由主线程通过 pidfd epoll 事件或 `/proc` 轮询维护。

#### 4.3 主线程与 Reaper 的并发时序

异步请求成功入队后，`reaper.kill()` 假定后续信号能够成功并立即返回 0。主线程随即更新时间、kill counter，写入 killinfo，构造统计包并通知订阅客户端；这些操作与 Reaper 的 SIGKILL、`process_mrelease()` 并行，不存在“先完成 mrelease，再记录日志”的串行保证。若工作线程随后发送信号失败，它会通过 Reaper 通信管道异步通知主线程。

`kill_timeout_ms` 只限制“等待上一受害者退出”的时间：

- 进程提前退出时，pidfd 通知会立即解除等待；
- 超时后即使目标仍未退出，lmkd 也会停止等待并允许下一次选择；
- 配置为 0 表示只要目标仍 pending 就无限等待，而不是禁用等待。

`sys.lmk.reportkills=1` 是 lmkd 发布的能力标志，表示实现支持 kill/stat 异步通知；它不是控制是否写日志或是否上报 statsd 的开关。客户端必须先通过 `LMK_SUBSCRIBE` 订阅相应事件，统计包再由 AMS 等客户端转发。

---

## 5. 属性语义与配置边界

### 5.1 属性优先级和主要默认值

除 `ro.config.*` 等少数属性外，源码通过 `GET_LMK_PROPERTY()` 读取配置：

```text
persist.device_config.lmkd_native.<name>
        优先于
ro.lmk.<name>
        优先于
源码默认值
```

主要属性如下：

| 属性 | 默认值 | 作用 |
|------|--------|------|
| `ro.config.low_ram` | `false` | 选择低 RAM 设备默认参数 |
| `ro.lmk.use_psi` | `true` | 优先启用 PSI 监控 |
| `ro.lmk.use_new_strategy` | `low_ram || !use_minfree_levels` | 选择 `__mp_event_psi()` 新策略 |
| `ro.lmk.use_minfree_levels` | `false` | 在兼容路径中使用 free/file-cache 阈值 |
| `ro.lmk.kill_heaviest_task` | `false` | 在同一 adj 槽位选择最大 RSS，而不是链表尾部 |
| `ro.lmk.kill_timeout_ms` | `100` | 上一个受害者仍 pending 时的最长等待时间；0 表示无限等待 |
| `ro.lmk.swap_free_low_percentage` | `10` | 有效 Swap 低阈值，占 `SwapTotal` 的百分比 |
| `ro.lmk.thrashing_limit` | 高性能设备 100，低 RAM 设备 30 | page-cache refault 基础阈值 |
| `ro.lmk.thrashing_limit_decay` | 高性能设备 10，低 RAM 设备 50 | thrashing 击杀后动态阈值的降低百分比 |
| `ro.lmk.thrashing_limit_critical` | `thrashing_limit × 3` | 允许突破感知进程保护的 critical thrashing 阈值 |
| `ro.lmk.swap_util_max` | `100` | Swap utilization 阈值；100 表示禁用对应分支 |
| `ro.lmk.filecache_min_kb` | `0` | thrashing 后的 file LRU 下限；0 表示禁用 |
| `ro.lmk.direct_reclaim_threshold_ms` | `0` | direct reclaim 卡住阈值；0 表示禁用 |
| `ro.lmk.lowmem_min_oom_score` | `701` | `LOW_MEM` 分支的最低 adj；最小限制为 201，1001 可禁用 |
| `ro.lmk.pressure_after_kill_min_score` | `0` | `PRESSURE_AFTER_KILL` 分支的最低 adj |
| `ro.lmk.stall_limit_critical` | `100` | `full.avg10` 覆盖阈值；因使用严格大于比较，默认实际禁用 |

对于 `lmkd.rc` 明确列出的 `persist.device_config.lmkd_native.*` 实验属性，属性变化会触发 `lmkd.reinit`；辅助进程连接正在运行的 lmkd 并发送 `LMK_UPDATE_PROPS`，使其重新读取属性，必要时重建压力监控器。未在 rc 中列出的属性不会自动触发这一流程。不是所有 `ro.lmk.*` 名称都自动生效；只有源码或已启用 hook 明确读取的属性才有作用。

### 5.2 lmkd 发布的系统属性

- **`sys.lmk.minfree_levels`**：`LMK_TARGET` 最近一次下发的 `minfree:oom_adj_score` 列表，主要用于能力观察和兼容路径。它不是新 PSI 策略的 watermark 配置。
- **`sys.lmk.reportkills`**：表示 lmkd 支持向订阅客户端发送进程击杀和统计事件，不是日志或 statsd 的启停开关。

### 5.3 8397 产品配置的实现边界

8397 产品配置设置了：

```text
ro.lmk.kill_heaviest_task=true
ro.lmk.kill_timeout_ms=15
ro.lmk.enhance_batch_kill=true
ro.lmk.enable_adaptive_lmk=true
ro.lmk.vmpressure_file_min=80640
```

当前 `system/memory/lmkd` 明确读取前两个属性，因此它们分别改变同 adj 受害者选择方式和 pending 进程等待上限。

当前给定的 qssi 源码中没有找到后三个属性的读取点，也没有找到为本产品启用 `liblmkdhooks` 的配置。它们可能是遗留配置或供其他实现使用；仅凭属性存在不能认定 batch kill、adaptive LMK 或 `vmpressure_file_min` 已在当前 lmkd 中生效。

产品配置没有显式设置 `use_minfree_levels`，所以在没有 DeviceConfig 覆盖时使用默认值 `false`，新 PSI 策略不会直接使用 `sys.lmk.minfree_levels` 决策。

## 6. 内存指标之间的关系

### 6.1 Free、Cached 与 file LRU

新 PSI 策略进行 watermark 比较时使用：

```text
effective_free = nr_free_pages - cma_free
```

它不使用 `/proc/meminfo` 的 `MemAvailable`，也不会把全部 Cached 直接加到 free。新策略另外观察 PSI stall、reclaim 状态和 workingset refault，以判断回收是否已经影响系统前进速度；它不会预先假定 Cached 都能立即、无代价地回收。

lmkd 根据 `/proc/meminfo` 重建内部 `nr_file_pages`：

```text
nr_file_pages = Cached + SwapCached + Buffers
```

而 `Active(file)`、`Inactive(file)` 是文件 LRU 上按活跃程度划分的页。它们与 Cached 大量重叠，但统计边界不同，不是另一份独立内存，因此不能执行：

```text
Cached + Active(file) + Inactive(file)
```

来计算文件内存总量。两者不完全相等还可能来自 shmem/swap-backed 页、unevictable 页、buffer accounting 以及读取时刻的计数差异。

- 新策略用 `Active(file) + Inactive(file)` 作为 thrashing 分母，并在启用时检查 `filecache_min_kb`。
- minfree 兼容策略从 `nr_file_pages` 中扣除 `shmem`、`unevictable` 和 `swap_cached`，得到 `other_file`。
- `Inactive(file)` 表示更可能成为回收候选，不代表其中每一页都能无代价、立即释放；脏页、正在使用的映射和并发访问都会影响实际回收速度。

### 6.2 RSS 与实际释放量

`proc_get_heaviest()` 使用 `/proc/<pid>/statm` 的 RSS 选择受害者，`kill_one_process()` 使用 `/proc/<pid>/status` 的 RSS/Swap 记录统计。这些值包含共享页，是受害者规模估计，不等于进程退出后系统 free 的净增量。实际释放还受共享映射、页缓存、内核对象、异步退出速度和同期分配影响。

## 总结

现代 lmkd 的核心不是一组固定的 minfree 档位，而是“压力触发 + 状态复核 + 优先级选择”的闭环：PSI 负责暴露回收造成的停顿，新策略用非 CMA free 与 zone watermark 判断紧迫程度，再结合有效 Swap、file refault 和 reclaim 状态确定 kill reason 与 `min_score_adj`。受害者按 `oom_score_adj` 从 1000 向下搜索，每次评估最多击杀一个，但 PSI 窗口轮询可以产生连续评估。

pidfd 将进程身份、死亡通知和信号发送绑定到稳定的内核对象；Reaper 线程池负责异步 SIGKILL 与 `process_mrelease()`，主线程则保持 epoll 响应并并行完成记录和客户端通知。理解新 PSI 策略、minfree 兼容路径及 Reaper 并发时序的边界，是正确分析 lmkd 行为的关键。

> **参考文件**：
> - `system/memory/lmkd/lmkd.cpp`：主事件循环、策略判断与受害者选择
> - `system/memory/lmkd/reaper.cpp`：异步信号发送与 `process_mrelease()`
> - `system/memory/lmkd/statslog.h`：kill reason 枚举和统计结构
> - `system/memory/lmkd/event.logtags`：killinfo 字段定义
> - `system/memory/lmkd/README.md`：AOSP 属性说明
> - `system/memory/lmkd/lmkd.rc`：服务和属性重初始化触发器
