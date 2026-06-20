# QNX 系统资源监控方案

## 1. 目标

在 QNX Host 侧实现一个常驻后台进程 `polaris-monitor`，用于低开销监控系统 CPU、Memory、IO、Network、Thermal 资源状态，并在资源异常时打印本地预警日志，辅助定位系统卡顿、内存耗尽、IO 异常和进程资源泄漏问题。

核心约束：

- 进程常驻后台运行，由 SLM 或启动脚本拉起并守护。
- 默认常态 CPU 设计目标小于单核 2%，异常诊断 10s 平均不超过单核 3%，硬性保护阈值小于单核 5%。
- 常驻内存硬性上限小于 150 MB，设计目标小于 80 MB。
- 常态打印低频 heartbeat 本地日志，异常时打印详细本地预警日志，均不要求默认上传云端（节奏见 9.4）。
- 常态采样轻量化；重型诊断只在异常触发、低频、限流条件下执行。

## 2. QNX 可用基础接口

QNX 不能按 Linux `/proc/meminfo`、`/proc/stat`、`/proc/diskstats` 的方式直接复用现有 Linux monitor。建议新增 QNX backend，使用 QNX 原生接口：

- 进程/线程信息：`/proc/<pid>/as` + `devctl()`。
- 进程 CPU/内存：`DCMD_PROC_INFO`，字段包括 `utime`、`stime`、`private_mem`、`num_threads`。
- 线程状态：`DCMD_PROC_TIDSTATUS`，字段包括 `sutime`、`state`、`last_cpu`、`nsec_since_block`。
- 进程地址空间：`DCMD_PROC_ASINFO`，字段包括 `rss`、`map_private`、`map_shared`、`map_count`。
- 系统静态内存布局：syspage `asinfo` 或 `walk_asinfo()`。
- 系统可用内存：`posix_typed_mem_open(TYPEMEM_SYSRAM)` + `posix_typed_mem_get_info()`。
- crash/系统日志：`slogger2`、`slog2info`、`dumper`、`/var/log/coredump`。
- 存储健康信息：UFS/NVMe/SDMMC 相关 `devctl()` 或平台工具，具体依赖当前镜像是否暴露对应节点。
- 网络接口状态和统计：优先使用 socket ioctl、`getifaddrs()`、io-pkt 暴露的接口统计或平台网络服务接口；常态路径不周期调用 `ifconfig`、`netstat` 等外部命令。
- 温度和热管理：优先使用平台 thermal service、sensor 节点、BSP `devctl()` 或 QNX/Qualcomm 暴露的热管理接口；如果目标镜像未暴露，则明确标记为 unavailable。

## 3. 总体架构

建议拆成四层：

1. Scheduler
   负责固定周期采样、异常触发采样、退避和限流。

2. Collectors
   包括 `CpuCollector`、`MemCollector`、`IoCollector`、`NetworkCollector`、`ThermalCollector`、`CrashCollector`、`ProcessCollector`。每个 collector 只返回结构化样本，不直接做复杂判断。

3. Detector
   对样本做阈值判断、斜率判断、持续时间判断和去抖，生成预警事件。

4. Logger
   按各事件的独立格式输出本地日志，支持速率限制和异常上下文快照。

后台进程默认以低优先级运行，避免与业务进程竞争：

- 调度优先级低于关键业务进程。
- 常态轻量采样周期 5s 到 10s。
- 进程全量扫描周期默认 10s 到 30s，优先保证低 CPU 开销。
- 异常发生时允许短时间提高采样密度，但必须设置冷却时间、扫描上限和自降级阈值。

## 4. CPU 监控指标

### 4.1 系统 CPU 使用率

指标：

- `cpu_total_pct`
- `cpu_user_pct`
- `cpu_system_pct`
- `cpu_per_core_estimate_pct`，可选

实现方式：

- PID 发现只遍历 `/proc` 下的数字目录，得到进程级 pid 列表。
- 对每个 pid 打开 `/proc/<pid>/as`，只调用一次进程级 `DCMD_PROC_INFO`。
- 不把 `/proc/<pid>/as` 下的线程条目当作进程重复累计，避免同一进程 runtime 被多次计数。
- 读取 `utime + stime`，与上一次成功采样做 delta。
- 新发现的进程只建立 baseline，下一次采样才计入 delta，避免进程刚出现时因缺少上一帧数据导致 CPU 估算偏高。
- 系统 CPU 使用率按所有进程 delta runtime 之和估算：

```text
cpu_total_pct = sum(delta(utime + stime)) / (sample_interval_ns * cpu_count) * 100
```

说明：

- 该方式低开销、实现简单，适合常态监控。
- 它不等价于 Linux `/proc/stat`，对中断、idle、微内核自身开销和部分内核活动的表达可能不完全一致。
- 由于无法覆盖所有内核路径，在高负载场景下观测上限可能低于 100%，例如 85% 到 95%；阈值必须基于目标板实测标定。
- 若后续需要更精确的内核级 CPU 统计，可增加 QNX trace 或平台私有接口，但不建议放入常态路径。

### 4.2 进程 CPU TopN

指标：

- `top_cpu_processes`
- 每项包括 `pid`、`name`、`cpu_pct`、`utime_delta_ms`、`stime_delta_ms`、`threads`

实现方式：

- 复用系统 CPU 采样时获取的 `DCMD_PROC_INFO`。
- 对进程 runtime delta 排序。
- 默认只打印 Top5。
- 只有 CPU 异常时打印 Top10 或 Top20。

异常判断建议：

- Warning：系统 CPU 连续 3 次超过 80%。
- Critical：系统 CPU 连续 3 次超过 90%，或单个进程持续超过单核 80%。
- 恢复：Critical → Warning 连续 3 次低于 70%（`exit_critical_pct`）；Warning → Normal 连续 5 次低于 60%（`exit_warning_pct`）。
- Spike：单次超过 95% 但未持续，只打印一次低频提示。

### 4.3 线程状态和阻塞信息

指标：

- `thread_count`
- `running_threads`
- `ready_threads`
- `blocked_threads`
- `long_blocked_threads`
- Top process 的线程 `state`、`last_cpu`、`nsec_since_block`

实现方式：

- 常态不全量扫描所有线程，避免开销过高。
- CPU Critical 或进程 CPU 异常时，只对 TopN 进程做线程枚举。
- 线程枚举流程：打开 `/proc/<pid>/as`，枚举线程条目并过滤出 tid，对每个 tid 调用 `DCMD_PROC_TIDSTATUS`。
- 设置线程扫描上限，例如全局最多 64 个线程、单进程最多 16 个线程；超过上限时设置 `scan_limited=true`。
- 线程快照必须设置单轮时间预算，例如 10ms；超时则停止本轮线程扫描并保留已采集结果。
- 打印长时间阻塞线程、长时间 ready 线程和热点线程。

异常判断建议：

- 单进程线程数超过阈值，例如 512 或配置值。
- 大量线程处于 ready/running，且系统 CPU 高。
- 关键进程线程长时间 blocked，持续超过 10s 或配置值。


### 4.4 进程发现和缓存策略

PID 发现：

- 使用 `readdir("/proc")` 获取数字 pid，不依赖外部 `pidin` 命令。
- 每轮采样先生成当前 pid 集合，再按 pid 打开 `/proc/<pid>/as`。
- CPU 和 Memory 采样共享同一轮 pid 列表，避免重复遍历 `/proc`。

缓存策略：

- 不能只以 pid 作为进程身份计算连续 delta；pid 复用会导致上一进程的 `utime/stime` 污染新进程。
- 进程缓存 key 优先使用 `pid + process_start_time`、`pid + creation_tick` 或 `pid + generation_id`。
- 如果平台能提供进程启动时间或唯一 generation id，必须一起纳入 key，避免 pid 复用导致 delta 错算。
- 缓存内容包括上一轮 `utime`、`stime`、进程名、线程数和进程身份字段。
- 新发现的进程第一帧只建立 baseline，不参与 CPU delta，不进入本轮 CPU TopN。
- 如果没有启动时间或 generation id，使用保守 fallback：发现 `utime + stime` 小于缓存值、进程名变化、或 `devctl()` 返回的基础身份信息明显变化时，认为疑似 pid reuse，丢弃旧缓存并重新 baseline。
- 疑似 pid reuse 的这一帧不参与系统 CPU 汇总和 TopN，避免异常尖峰或负 delta 污染判断。
- 对进程内存趋势同样按进程身份建 key；pid reuse 或疑似 reuse 时清空该 pid 的历史趋势窗口。
- 采样中途进程退出时，`open()` 或 `devctl()` 失败计入 `scan_failed`，不作为资源异常；连续多轮失败才打印低频 warning。
- 进程退出后从缓存中移除，避免缓存无限增长。
- 每轮记录 `rebaseline_count`，表示新进程或疑似 pid reuse 导致本轮只建立 baseline 的进程数量。

## 5. Memory 监控指标

### 5.1 系统总内存和可用内存

指标：

- `mem_total_mb`
- `mem_available_mb`
- `mem_used_pct`
- `sysram_free_mb`
- `sysram_total_mb`

实现方式：

- `mem_total_mb` 从 syspage `asinfo` 中的 RAM 区间累计。
- `mem_available_mb` 使用 typed memory：

```text
fd = posix_typed_mem_open(TYPEMEM_SYSRAM, O_RDONLY, POSIX_TYPED_MEM_ALLOCATE)
posix_typed_mem_get_info(fd, &info)   /* info.posix_tmi_length = /sysram 可分配量 */
```

说明：

- `TYPEMEM_SYSRAM` 是 `<sys/mman.h>` 标准宏，展开为 `"/sysram"`（QNX SDP 7.1 已核实）。
- 第三参数 `tflag` 必须传 `POSIX_TYPED_MEM_ALLOCATE`，否则 `posix_tmi_length` 不代表可分配（空闲）量。传 `0` 取到的不是 `sysram_free`，这是常见误用。
- QNX 没有 Linux `MemAvailable` 的完全等价字段。
- 方案中的 `mem_available_mb` 应定义为 QNX `/sysram` 可分配内存，不直接和 Linux 数值对齐。

异常判断建议：

- Warning：可用内存低于 15%，持续 3 次。
- Critical：可用内存低于 8%，持续 3 次。
- 恢复：Critical → Warning 连续 3 次可用内存高于 10%（`exit_critical_avail_pct`）；Warning → Normal 连续 5 次高于 25%（`exit_warning_avail_pct`）。

### 5.2 进程内存 TopN

指标：

- `top_mem_processes`
- 每项包括 `pid`、`name`、`rss_mb`、`private_mb`、`shared_mb`、`map_count`、`threads`

实现方式：

- 对进程调用 `DCMD_PROC_ASINFO`，读取 `rss`、`map_private`、`map_shared`、`map_count`。
- 对进程调用 `DCMD_PROC_INFO`，读取 `private_mem`、`num_threads`。
- 常态每 30s 扫描一次，与 CPU 进程列表复用。
- 低内存异常时立即扫描一次，但设置冷却时间，例如 60s。
- `DCMD_PROC_ASINFO` 返回当前值，不保证捕获短时间内存峰值；如果平台没有 peak RSS 接口，只能记录采样窗口内已观测最大值。

异常判断建议：

- 单进程 RSS 超过配置阈值。
- 单进程 private 内存持续增长。
- 系统可用内存下降，但 TopN 进程内存无明显增长时，打印系统级分类提示，提示可能是共享内存、typed memory、图形/媒体缓冲、QVM/pmem 或驱动侧占用。
- 如果平台暴露 QVM、pmem、graphics buffer 或媒体缓冲统计接口，第二阶段接入为独立分类；如果未暴露，只能输出 `suspect=memory_non_process`，表示疑似非进程私有内存增长，而不是根因结论。

### 5.3 内存趋势

指标：

- `mem_available_slope_mb_per_min`
- `top_proc_rss_slope_mb_per_min`
- `top_proc_private_slope_mb_per_min`

实现方式：

- 维护 5 分钟滑动窗口。
- 对 `mem_available_mb`、TopN 进程 RSS/private 做线性斜率。
- 斜率只用于辅助判断，不单独作为泄漏根因。

异常判断建议：

- 可用内存持续下降，且 R2 大于 0.8，打印趋势预警。
- 某进程 private 内存持续上升，打印疑似进程内存泄漏。
- 系统可用内存下降但进程 TopN 无增长，打印疑似非进程私有内存占用。

### 5.4 内存池监控（非进程内存泄漏 / dmabuf 等价问题）

背景：

- QNX 侧没有 Linux `dma-buf`/ION 子系统，但等价的"大块共享/物理连续缓冲泄漏、却不计入泄漏进程 RSS"的问题同样存在。载体包括：QNX Screen 图形缓冲（window/pixmap/framebuffer）、typed memory `/device` 池（`mman.h` 注释即标注用于 video buffers）、厂商 GPU/camera/video/display 的 pmem carveout 池、QVM 跨 VM 共享缓冲、`shm_open`/MAP_SHARED 共享内存。
- 只监控 `/sysram`（5.1）存在盲区：如果泄漏发生在启动期预留的独立 carveout 池内，`sysram_free` 不会下降，状态机会一直 Normal，直到池耗尽、客户端 alloc 失败。这恰是 GPU/视频缓冲泄漏最常见的形态。本节通过逐池枚举来覆盖这一盲区。

指标：

- 逐池 `pool_name`、`pool_total_mb`、`pool_free_mb`、`pool_used_mb`、`pool_used_pct`
- `pool_free_contig_mb`（最大连续可分配量）
- `pool_used_slope_mb_per_min`

实现方式（必须缓存，避免每轮重复枚举）：

- 启动时 `walk_asinfo()`（`sys/asinfo.h`）枚举系统内存层级，得到各池名与总量。该数据来自已映射的 syspage，是启动期静态布局，无消息传递、无内核调用，运行时不变，只做一次。
- 启动时对每个池各 open 一次并缓存 fd：用 `posix_typed_mem_open(name, O_RDONLY, POSIX_TYPED_MEM_ALLOCATE)` 取总可分配量，再用 `POSIX_TYPED_MEM_ALLOCATE_CONTIG` 取最大连续可分配量。两种语义都要采：碎片化时连续量会远小于总量，连续分配先失败，连续量骤降本身就是泄漏/碎片化信号。
- 常态采样循环只对缓存的 fd 调 `posix_typed_mem_get_info()` 取 `posix_tmi_length`，算每池 used/free、连续量与趋势斜率。
- 默认周期 30s（泄漏检测变化慢，无需高频）。

异常判断建议：

- 单个池 `pool_used_pct` 持续升高、`pool_used_slope` 持续为正且 R2 大，或 `pool_free_contig_mb` 持续走低，打印疑似该池内存泄漏/碎片化，并在 Memory 事件中带上 `suspect=memory_non_process` 及具体 `pool_name`。
- 结合 5.2/5.3：进程 TopN 无增长但某池持续上涨，则归因从"非进程内存"细化到具体池。

平台实证（8295 / lemans，已查源码确认）：

- 厂商 pmem 池**是带名字的 QNX typed memory 对象**，可直接用 `posix_typed_mem_get_info` 查询——`pmem` 守护进程自身就用这两种 `POSIX_TYPED_MEM_ALLOCATE[_CONTIG]` 语义记录池空闲量（`AMSS/.../pmem_client/base/pmem_debug.c: pmem_log_tymem_info()`）。因此上面通用机制对 GPU/视频/相机/显示/DMA 等 carveout 池直接适用，**这些不是盲区**。
- 池清单见 `AMSS/inc/amss/pmem_id.h`（`GRAPHICS_FRAMEBUFFER/VIDEO/MDP/CAMERA/DMA/DSP/CVP/EVA/CV/QAIC/AUDIO` 等）；池的地址与大小由设备树（FDT）在启动时绑定，`pmem` 守护进程（`AMSS/platform/services/daemons/pmem/pmem_handle.c`）解析 FDT 并用内部 `pool` 分配器管理，resmgr 节点 `/dev/pmem_server`。
- 需在目标镜像实测落实：各池 typed-mem 对象的真实名字与总量（启动后 `walk_asinfo` 枚举得到，源码里是变量、字符串来自 FDT）；以及 `posix_tmi_length` 是否精确反映池内已分配的补集（建一两个 buffer 验证增减）。

客户端级归因（低频 / 按需，不进常态高频路径）：

- pmem 暴露每客户端可读节点 `/dev/pmem/<progname>`，`read()` 返回逐分配的文本转储（`pmem_debug.c: io_read → pmem_buffer_dump()`，无分配时返回 `"No PMEM allocations"`）。可在某池被判定为疑似泄漏时按需读取一次，定位到具体客户端进程，但因是文本转储，只允许低频/异常 snapshot 使用。
- 更细可用 `_DCMD_PMEM_GET_RGN_TBL`（`AMSS/inc/pmem_devctl.h`）取 region 表 / `dump_pool_tbl()`，更重，仅诊断用。

边界与平台依赖：

- 安全池（`PMEM_SECMEM_CP_*`，TZ/secure）普通 monitor 大概率不可见，标 `pool_available=false`，不伪造数值。
- 如 Screen 暴露 per-context/per-window buffer 统计接口，可进一步把池增长归因到具体客户端；否则只到池级或借上面 `/dev/pmem/*` 节点。
- 本能力列入第二阶段；接口不可用的池标记 `pool_available=false`。

开销：缓存 fd 后稳态仅 N 个池 ×（最多两次小 `get_info`），N 通常 5–15，30s 周期折算 ≤ 0.03% 单核，属噪声级（见 11.1 预算表）。`/dev/pmem/*` 文本转储不计入此预算，仅按需触发。

## 6. IO 监控指标

IO 监控只做存储设备健康一类。

范围说明：

- 不做文件系统容量监控：日志等磁盘由平台轮转机制管理，盘满风险不在本 monitor 职责内。
- 不做 IO 性能统计（IOPS、吞吐、延迟、队列深度）：依赖 io-blk/devb 暴露统计，目标镜像多半不可读，价值低。
- 不做进程级 IO 归因：QNX 默认没有 Linux `/proc/<pid>/io` 这种通用接口，需要业务库埋点、文件系统层 hook、驱动统计或 trace 辅助，不放入常态监控。
- 不做"线程被 IO 阻塞"检测：QNX 上该现象表现为线程 REPLY/WAITPAGE 阻塞在 IO 服务进程上（详见线程态分析的边界），本版本暂不实现。

### 6.1 存储设备健康

指标：

- `storage_health_status`
- `ufs_error_count`
- `ufs_reset_count`
- `nvme_smart_status`
- `io_error_count`

实现方式：

- 如果平台暴露 UFS/NVMe/SDMMC `devctl()`，优先走结构化接口。
- 如果只有平台工具，例如 `nvme_util`，不建议常态周期调用；只在异常时低频调用。
- 若驱动没有暴露统计，则只能记录工具不可用，不伪造指标。

异常判断建议：

- 设备 health 非正常。
- I/O error count 增长。
- UFS reset 或 SCSI I/O error 增长。


## 7. Network 监控指标

Network 监控只做低开销基础指标，默认不做抓包、不周期调用外部命令，不承诺进程级网络归因。

### 7.1 网络接口状态和流量

指标：

- `if_name`
- `admin_up`
- `link_up`
- `speed_mbps`，如果平台可获取
- `mtu`
- `rx_bytes_delta`、`tx_bytes_delta`
- `rx_packets_delta`、`tx_packets_delta`
- `rx_errors_delta`、`tx_errors_delta`
- `rx_drops_delta`
- `tx_drops_delta`，受平台限制，见下方说明

实现方式：

- 第一优先级使用结构化接口，例如 socket ioctl、`getifaddrs()` 中的接口统计、io-pkt 暴露的统计或平台网络服务接口。
- `getifaddrs()` 的 `AF_LINK` 项 `ifa_data` 指向 `struct if_data`，可取 `ifi_ibytes/ifi_obytes/ifi_ierrors/ifi_oerrors/ifi_iqdrops`（QNX SDP 7.1 `net/if.h` 已核实）。
- QNX SDP 7.1 的 `if_data` 只有输入丢包 `ifi_iqdrops`，没有输出丢包字段（无 `ifi_oqdrops`）。`tx_drops_delta` 在本镜像上默认无法从 `if_data` 取得，应按 `*_available:false` 处理或省略，不要填 0 伪装成无丢包。
- 常态路径不调用 `ifconfig`、`netstat` 等外部命令；外部命令只允许人工调试或异常低频 snapshot。
- 对配置的关键接口维护 60s 滑动窗口，按 delta 判断错误和丢包增长。
- 如果目标镜像不暴露接口统计，只上报链路状态，并设置 `stats_available=false`。

异常判断建议：

- 关键接口 `link_up=false` 持续 3 次，进入 Warning 或 Critical。
- `rx_errors_delta`、`tx_errors_delta`、`rx_drops_delta`、`tx_drops_delta` 持续增长，打印 warning。
- 关键接口长时间无收发包但业务期望有心跳时，需要业务侧提供 heartbeat 适配，不由通用 monitor 推断。

### 7.2 Socket 和协议栈状态

可选指标：

- socket buffer 使用率，如果平台暴露。
- TCP retransmit、reset、listen backlog，如果平台暴露。
- SOME/IP、DDS、CAN 等业务网络状态，如果业务或中间件提供结构化接口。

实现策略：

- 第一阶段不承诺 socket buffer 和协议级状态。
- 如果 QNX 网络栈未暴露通用接口，在方案中明确标记为已知盲区。
- CAN、SOME/IP、DDS 更适合作为平台 adapter 或业务 heartbeat 接入，避免 monitor 周期解析大日志。

## 8. Thermal 监控指标

温度监控作为低频关联信号，用于辅助解释 CPU 降频、性能抖动、设备异常和热保护事件。

### 8.1 温度传感器

指标：

- `zone_name`
- `temp_c`
- `warning_c`
- `critical_c`
- `sensor_available`
- `sample_age_ms`

实现方式：

- 优先使用平台 thermal service、sensor 节点、BSP `devctl()` 或 SoC vendor 暴露的结构化接口。
- 配置中显式列出需要监控的 sensor 或 thermal zone，例如 SoC、PMIC、UFS、board。
- 常态周期默认 60s，异常周期 30s（见 12 章与配置 `thermal.sample_ms/abnormal_sample_ms`）。
- 常态路径不调用高开销外部命令；如果只存在外部工具，则默认不上常态采集。

异常判断建议：

- 单个 zone 超过 warning 阈值并持续 3 次，进入 Warning。
- 单个 zone 超过 critical 阈值，进入 Critical。
- 温度快速上升时打印趋势 warning，例如 1 分钟上升超过配置阈值。

### 8.2 热限频和热保护

指标：

- `throttling_active`，如果平台可获取
- `cooling_state`，如果平台可获取
- `thermal_shutdown_risk`，如果平台可获取

实现策略：

- 第一阶段只要求温度值和阈值判断。
- 第二阶段适配平台热管理接口，补充 throttling/cooling 状态。
- 如果接口不可用，上报 `throttling_available=false`，不要推断或伪造限频状态。

## 9. 异常预警策略

### 9.1 状态机

每个资源模块使用四类状态：

- Normal
- Warning
- Critical
- Unknown

状态切换需要去抖：

- 进入 Warning：连续 3 次超过 Warning 阈值。
- 进入 Critical：连续 3 次超过 Critical 阈值。
- Critical → Warning：连续 `exit_critical_count`（默认 3）次回落到 exit_critical 迟滞阈值的正常侧（CPU 低于 `exit_critical_pct`，Memory 可用率高于 `exit_critical_avail_pct`）。
- Warning → Normal：连续 `clear_count`（默认 5）次回落到 exit_warning 迟滞阈值的正常侧（CPU 低于 `exit_warning_pct`，Memory 可用率高于 `exit_warning_avail_pct`）。
- 单次采样失败不重置超阈值计数和恢复计数，只标记本次样本无效。
- 连续采样失败达到配置阈值，例如 3 次，进入 Unknown 并打印 `collector_unavailable` warning。
- 从 Unknown 恢复时，需要连续 2 次采样成功后再恢复正常状态机判断。
- `scan_failed` 只表示本轮部分对象读取失败，例如进程退出或权限不足；只有失败比例持续过高时才触发 collector 异常。

### 9.2 限流

日志必须限流，避免异常时反复刷屏：

- 同类 Warning 日志最小间隔 30s。
- 同类 Critical 日志最小间隔 10s。
- 完整 TopN 快照最小间隔 60s。
- 同一周期内多个不同事件同时触发时，先输出一条 summary，再按严重级别输出有限条 detail，避免 distinct 事件绕过限流。
- 启动后前 30s 不做 Critical 判断，只采集 baseline。

### 9.3 异常上下文

CPU 异常打印：

```text
polaris-monitor: cpu critical total=92.5% top=[qvm(123):145.2%, app(456):72.1%] ready=31 blocked=102
```

Memory 异常打印：

```text
polaris-monitor: mem critical available=420MB total=8192MB used=94.9% top=[qvm(123):rss=1300MB/private=900MB, media(456):rss=820MB/private=600MB]
```

IO 异常打印：

```text
polaris-monitor: storage warning device=ufs error_count_delta=3 reset_count_delta=1
```

Network 异常打印：

```text
polaris-monitor: network warning if=en0 link=up rx_errors_delta=12 rx_drops_delta=3 window=60s
```

Thermal 异常打印：

```text
polaris-monitor: thermal critical zone=soc temp=106.5C critical=105C throttling=true
```

恢复日志：

```text
polaris-monitor: mem recovered available=1800MB used=78.0% duration=124s
```

### 9.4 上报与本地日志节奏

事件上报节奏（reason 语义见 15.2，与 8397/Linux 侧一致）：

- `enter`：状态切换（进入 Warning/Critical 或异常级别变化）时**立即上报**。
- `clear`：恢复 Normal 时**立即上报**。
- `summary`：Normal 稳态每 `normal_report_sec` 上报一次；Warning/Critical 稳态每 `alert_report_sec` 心跳上报一次。
- 上报周期为显式配置，默认 CPU `normal_report_sec=alert_report_sec=120`、Memory `=300`；与上报 JSON 的 `window_ms` 一致（CPU 120000、Memory 300000）。
- 每次上报后清窗，下一聚合周期从零开始；常态上报为小包，TopN/线程/趋势只在异常或 snapshot 携带。

本地日志节奏（slog2，独立于上报，不影响云端）：

- Normal 稳态：每 `normal_sample_log_sec` 落一行 INFO heartbeat，打印当前关键值（如 CPU `usage/user/sys`、Memory `sysram_free/used_pct`），用于现场确认进程存活与实时读数。默认 **CPU 10s**（与常态采样周期一致，每次采样一行）、**Memory 60s**（采样仍 10s，日志限频以降低 slog2 噪声）。设为 0 表示每次采样都打印。
- 异常态：按 9.2 限流，Warning 同类日志最小间隔 30s、Critical 最小间隔 10s、完整 TopN 快照最小间隔 60s。
- 状态切换各打印一行（如 `Normal -> Warning`），与 `enter`/`clear` 上报对应。
- 说明：常态 heartbeat 是低频存活/观测信号；slog2 为环形缓冲，CPU 用 10s 便于实时观察、Memory 用 60s 控制噪声，可按现场需要再调整，均不影响上报。

## 10. 自监控和降级

监控进程必须监控自身资源消耗，避免在系统异常时成为新的压力源。

自监控指标：

- `self_cpu_pct`
- `self_rss_mb`
- `self_thread_count`
- `collector_duration_ms`
- `collector_timeout_count`
- `event_queue_depth`

降级策略：

- 自身 CPU 连续 3 次超过单核 2%，打印 warning，并把非关键 collector 的采样周期放大 2 倍。
- 自身 RSS 超过 80 MB，打印 warning，清理非必要缓存和历史窗口。
- 自身 CPU 连续 3 次超过单核 3%，进入 CPU 强降级，只保留 Self、低频 CPU/Memory、Crash、关键 FS、关键 Network/Thermal。
- 自身 CPU 单次超过单核 5%，立即跳过所有可选诊断 collector，并把下一轮全量扫描延后。
- 自身 RSS 超过 120 MB，进入强降级，只保留 CPU、Memory、Crash、关键 FS、关键 Network/Thermal 低频采样。
- 单个 collector 超过 5s 未返回，判定为 hang，本轮丢弃结果并进入该 collector 的退避周期；主循环不能被阻塞。
- 连续超时的 collector 进入 Unknown 状态，直到连续 2 次采样成功。

Scheduler 策略：

- 使用 monotonic clock 固定周期调度，不做追赶式补采。
- 如果某轮采集耗时超过周期，下一轮跳过可选 collector，而不是立即连续执行多轮采样。
- Collector 优先级建议为：Self、CPU/Process、Memory、Crash、FS、Network、Thermal、Storage health、可选诊断。
- 每个 collector 必须有独立时间预算，超预算时保留已完成结果并设置 `scan_limited=true` 或 `collector_timeout=true`。

## 11. 资源开销控制

### 11.1 CPU 控制

目标：默认常态平均 CPU 小于单核 2%。8295 是 8 核且 QNX 与 Android 共用算力，polaris-monitor 不能按“空闲核心”假设设计；2% 单核等价于每秒最多消耗约 20ms CPU time。

控制策略：

- 默认使用 low-overhead mode，而不是高频诊断模式。
- 常态全量进程 runtime 扫描周期不小于 10s；只有关键进程 allowlist 可以 2s 到 5s 轻量扫描。
- CPU/Mem 进程全量扫描合并执行，避免重复遍历 `/proc`。
- 常态只扫进程级 `DCMD_PROC_INFO`，Memory TopN 的 `DCMD_PROC_ASINFO` 降低到 60s 周期或低内存触发。
- 线程级扫描只在异常时对 TopN 进程执行，并设置全局最多 64 个线程、单进程最多 16 个线程。
- IO 设备健康检查默认 300s 一次，异常时最低 60s。
- Network 基础接口状态默认 30s，流量统计默认 60s，失败时退避。
- Thermal 默认 60s，异常 30s，失败时退避。
- 外部命令默认不在常态路径调用。
- 常态单轮 wall-time 预算建议 20ms 到 30ms，且必须用自身 CPU time 校验真实 CPU 消耗；预算超限时跳过可选 collector。
- 异常线程快照、存储健康、slog2 补充扫描等诊断项必须有独立子预算和冷却时间。

CPU 预算粗算：

| 项目 | 默认周期 | 单次目标 CPU time | 折算单核占用 |
| --- | ---: | ---: | ---: |
| 全量进程 `DCMD_PROC_INFO` 扫描 | 10s | <= 80ms | <= 0.8% |
| 系统 memory typed memory 查询 | 10s | <= 2ms | <= 0.02% |
| 内存池逐池 `get_info`（缓存 fd，含 contig/non-contig 两种语义，二阶段） | 30s | <= 10ms | <= 0.03% |
| Memory TopN `DCMD_PROC_ASINFO` | 60s | <= 80ms | <= 0.13% |
| 存储设备健康 `devctl()` | 300s | <= 10ms | <= 0.01% |
| Network 接口统计 | 30s/60s | <= 5ms | <= 0.02% |
| Thermal sensor 查询 | 60s | <= 5ms | <= 0.02% |
| Crash 目录扫描 | 10s | <= 5ms | <= 0.05% |
| Scheduler/Detector/Logger | 1s | <= 2ms | <= 0.2% |
| 预留 | - | - | 约 0.7% |
| 常态合计目标 | - | - | <= 2.0% |

说明：

- 上表是设计预算，不是保证值；实际值取决于 QNX `devctl()` 延迟、进程数、线程数和目标镜像接口实现。
- 如果进程数接近 1000，2s 全量扫描很容易突破 2% 单核目标，因此默认不采用 2s 全量扫描。
- 如果全量进程扫描单次超过 80ms，自动把扫描周期从 10s 退避到 15s 或 30s，并设置 `scan_limited=true`。
- 异常触发快照允许短时尖峰，但 10s 平均目标小于单核 3%；超过 3% 必须降级，超过 5% 立即停止可选诊断。

验收标准：

- 空闲场景运行 30 分钟，`polaris-monitor` 平均 CPU 小于单核 1%。
- 常规座舱负载运行 30 分钟，`polaris-monitor` 平均 CPU 小于单核 2%，p95 小于单核 3%。
- 压力场景运行 30 分钟，`polaris-monitor` 平均 CPU 小于单核 2.5%。
- 异常触发快照时允许短时尖峰，但 10s 平均小于单核 3%，且不得连续触发高开销诊断。

### 11.2 内存控制

目标：常驻内存设计目标小于 80 MB，硬性上限小于 150 MB。

措施：

- 不缓存全量历史明细，只保留滑动窗口聚合值。
- TopN 使用固定容量数组或 bounded vector。
- 每个模块保留最近 5 到 10 分钟趋势窗口。
- 日志字符串按需构造，不保存大文本。
- 不把 coredump、slog 大文本读入内存。
- 配置为编译期常量，无 JSON 解析、无运行期配置缓冲。

建议内存预算：

| 模块 | 预算 |
| --- | ---: |
| 主进程和调度框架 | 5 MB |
| CPU/进程采样缓存 | 8 MB |
| Memory 采样缓存 | 8 MB |
| IO/FS/Network/Thermal 采样缓存 | 6 MB |
| 日志与事件缓冲 | 8 MB |
| 配置、状态机和临时对象 | 5 MB |
| 预留 | 20 MB |
| 合计设计目标 | 60 MB |
| 硬性上限 | 150 MB |

说明：

- 150 MB 是绝对上限，不应作为常态占用目标。
- 常态应以 50 MB 到 80 MB 为工程验收目标。
- 所有 TopN、趋势窗口、日志缓冲必须使用固定容量容器。

## 12. 采样周期建议

| 模块 | 常态周期 | 异常周期 | 说明 |
| --- | ---: | ---: | --- |
| 系统 CPU | 10s | 5s | 全量进程 runtime delta，优先低开销 |
| 进程 CPU TopN | 10s | 5s | 与 CPU 全量扫描复用，关键进程可单独 2s 轻量扫描 |
| 系统 Memory | 10s | 5s | typed memory 查询 |
| 内存池监控 | 30s | 30s | 二阶段，逐池 `get_info`，缓存 fd，检测非进程/dmabuf 等价泄漏 |
| 进程 Memory TopN | 60s | 30s | 低内存时触发，常态低频 |
| 线程状态 | 不常态扫描 | 30s | 只扫 TopN 进程，最多 64 线程 |
| 存储健康 | 300s | 60s | UFS/NVMe error/reset 计数，取决于平台接口 |
| Crash 目录 | 10s | 10s | 监控 coredump 新文件 |
| Network 基础状态 | 30s | 10s | 关键接口链路和错误计数 |
| Network 流量统计 | 60s | 30s | bytes/packets/errors/drops delta |
| Thermal 温度 | 60s | 30s | SoC/PMIC/UFS/board 等关键 sensor |
| Self monitor | 5s | 2s | 监控进程自身 CPU/RSS/超时 |

## 13. 配置项

为简化实现，配置不使用外部文件，直接以编译期常量内置在代码中：

- 不读取 `/etc/polaris-monitor/config.json`，不引入 JSON 解析依赖，启动即用内置默认值。
- 没有运行期配置加载、校验和热更新；修改配置需改代码并重新编译发布。
- 不存在"配置文件缺失/解析失败"的失败路径，省去相关容错逻辑。
- 建议把全部参数集中在一个 `config.h`/`config struct` 的常量初始化中，结构与下面 JSON 一一对应，便于阅读和评审。

下面用 JSON 表达内置默认值，仅作为参数清单和默认值文档，运行时不解析：

```json
{
  "scheduler": {
    "collector_timeout_ms": 5000,
    "normal_budget_ms": 30,
    "normal_cpu_budget_pct": 2.0,
    "abnormal_cpu_budget_pct": 3.0,
    "hard_cpu_budget_pct": 5.0,
    "overrun_policy": "skip_optional",
    "catch_up": false
  },
  "cpu": {
    "sample_ms": 10000,
    "abnormal_sample_ms": 5000,
    "process_scan_ms": 10000,
    "abnormal_process_scan_ms": 5000,
    "critical_process_sample_ms": 2000,
    "normal_report_sec": 120,
    "alert_report_sec": 120,
    "normal_sample_log_sec": 10,
    "warning_pct": 80,
    "critical_pct": 90,
    "exit_warning_pct": 60,
    "exit_critical_pct": 70,
    "topn": 5,
    "abnormal_topn": 5,
    "thread_count_warning": 512,
    "ready_thread_warning": 64,
    "blocked_ms_threshold": 10000,
    "thread_scan_interval_ms": 30000,
    "thread_scan_max": 64,
    "per_process_thread_scan_max": 16,
    "thread_snapshot_budget_ms": 10,
    "scan_cpu_time_budget_ms": 80,
    "scan_backoff_ms": 30000
  },
  "memory": {
    "sample_ms": 10000,
    "abnormal_sample_ms": 5000,
    "process_scan_ms": 60000,
    "abnormal_process_scan_ms": 30000,
    "pool_sample_ms": 30000,
    "normal_report_sec": 300,
    "alert_report_sec": 300,
    "normal_sample_log_sec": 60,
    "warning_available_pct": 15,
    "critical_available_pct": 8,
    "exit_warning_avail_pct": 25,
    "exit_critical_avail_pct": 10,
    "topn": 5,
    "abnormal_topn": 5,
    "trend_window_sec": 300,
    "trend_min_r2": 0.8
  },
  "io": {
    "storage_health_ms": 300000,
    "abnormal_storage_health_ms": 60000
  },
  "crash": {
    "poll_ms": 10000,
    "coredump_dir": "/var/log/coredump",
    "slog2_excerpt_max_bytes": 512
  },
  "network": {
    "interface_sample_ms": 30000,
    "abnormal_interface_sample_ms": 10000,
    "traffic_sample_ms": 60000,
    "abnormal_traffic_sample_ms": 30000,
    "interfaces": ["en0", "en1"],
    "critical_interfaces": ["en0"],
    "error_delta_warning": 10,
    "drop_delta_warning": 100
  },
  "thermal": {
    "sample_ms": 60000,
    "abnormal_sample_ms": 30000,
    "zones": [
      {"name": "soc", "warning_c": 90, "critical_c": 105},
      {"name": "pmic", "warning_c": 95, "critical_c": 115},
      {"name": "ufs", "warning_c": 85, "critical_c": 100}
    ]
  },
  "state_machine": {
    "enter_count": 3,
    "exit_critical_count": 3,
    "clear_count": 5,
    "unknown_fail_count": 3,
    "unknown_recover_count": 2
  },
  "self_monitor": {
    "sample_ms": 5000,
    "abnormal_sample_ms": 2000,
    "warning_cpu_pct": 2.0,
    "degrade_cpu_pct": 3.0,
    "hard_cpu_pct": 5.0,
    "warning_rss_mb": 80,
    "degrade_rss_mb": 120
  },
  "log": {
    "target": "slog2",
    "file_path": "/var/log/polaris-monitor.log",
    "warning_interval_ms": 30000,
    "critical_interval_ms": 10000,
    "snapshot_interval_ms": 60000,
    "max_line_bytes": 4096
  }
}
```

## 14. 部署方式

建议工程目录：

```text
qnx/mega/apps/polaris_monitor
```

建议运行方式：

- 由 SLM 拉起，配置为后台常驻。
- 如果启用了 secpol，需要单独定义 `mega.polaris_monitor.txt`。
- 日志写 slog2 或本地 rolling file，优先使用系统统一日志路径。
- coredump 目录默认监控 `/var/log/coredump`。

建议进程名：

```text
polaris-monitor
```

## 15. QNX 专属上报格式

### 15.1 总体原则

QNX 侧不复用 Linux 上报字段，也不设计统一外层 envelope。CPU、Memory、IO、Network、Thermal、Crash 仍然保持独立事件、独立 event id、独立 JSON。事件类型由 event id 区分，JSON 内不需要 `schema` 字段。

格式原则：

- CPU、Memory、IO、Network、Thermal、Crash 分别定义自己的顶层字段。
- 不设置统一 `payload`、`state`、`source_status`、`self` 外层。
- 字段命名直接表达 QNX 语义，数值字段尽量带单位后缀，例如 `_pct`、`_mb`、`_ms`、`_count`。
- 无法获取的指标不要填 0 伪装成正常值；使用 `*_available:false` 或省略该字段。
- TopN、线程快照、趋势分析只在异常或 snapshot 时携带；常态周期上报保持小包。
- 单包大小建议：常态小于 8 KB，异常快照小于 32 KB。

### 15.2 通用状态字段

每类事件只保留少量通用状态字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ts_ms` | uint64 | Unix epoch 毫秒 |
| `level` | string | 当前状态，取值 `normal`、`warning`、`critical`、`unknown` |
| `reason` | string | 上报原因，CPU/MEM 建议与 Linux 保持一致 |
| `trigger` | string | QNX 具体触发原因，异常时携带 |
| `window_ms` | uint32 | 本次统计窗口长度 |
| `sample_count` | uint32 | 本次窗口内有效样本数 |

CPU 和 Memory 的 `reason` 取值保持与当前 Linux 侧一致；Network 和 Thermal 作为状态类资源事件，也建议复用相同取值：

| reason | 含义 |
| --- | --- |
| `summary` | 稳态周期上报 |
| `enter` | 进入 Warning/Critical，或异常级别发生切换 |
| `clear` | 恢复 Normal |

QNX 专属触发原因放入 `trigger`，不要扩展 `reason`。例如：

| trigger | 适用事件 | 含义 |
| --- | --- | --- |
| `high_total_cpu` | CPU | 系统总 CPU 超阈值 |
| `hot_process` | CPU | 单进程 CPU 超阈值 |
| `too_many_ready_threads` | CPU | ready 线程数异常 |
| `sysram_low` | Memory | `/sysram` 可分配内存过低 |
| `process_private_growth` | Memory | 进程 private 内存持续增长 |
| `non_process_memory_growth` | Memory | 非进程私有内存疑似增长 |
| `storage_device_error` | IO | 存储设备错误计数增长 |
| `network_link_down` | Network | 关键网络接口 link down |
| `network_error_growth` | Network | 网络接口错误计数增长 |
| `network_drop_growth` | Network | 网络接口丢包计数增长 |
| `thermal_high` | Thermal | 温度超过 warning 阈值 |
| `thermal_critical` | Thermal | 温度超过 critical 阈值 |
| `thermal_throttling` | Thermal | 平台报告热限频或热保护 |
| `collector_unavailable` | 通用 | collector 连续采样失败 |
| `core_created` | Crash | dumper 生成 core 文件 |
| `slog2_crash` | Crash | slog2 中发现 crash 记录 |

### 15.3 CPU 上报格式

事件：QNX CPU 资源事件。

常态周期上报示例：

```json
{
  "ts_ms": 1781863200123,
  "level": "normal",
  "reason": "summary",
  "window_ms": 120000,
  "sample_count": 12,
  "cpu_count": 8,
  "total_pct": 34.5,
  "user_pct": 20.1,
  "system_pct": 14.4,
  "max_process_pct": 55.2,
  "avg_pct": 32.1,
  "p95_pct": 45.6,
  "process_count": 186,
  "thread_count": 742,
  "ready_thread_count": 6,
  "running_thread_count": 3,
  "blocked_thread_count": 88,
  "long_blocked_thread_count": 0,
  "scan_total": 186,
  "scan_failed": 2,
  "rebaseline_count": 4,
  "scan_limited": false
}
```

异常上报示例：

```json
{
  "ts_ms": 1781863200123,
  "level": "critical",
  "reason": "enter",
  "trigger": "high_total_cpu",
  "window_ms": 120000,
  "sample_count": 12,
  "cpu_count": 8,
  "total_pct": 92.4,
  "user_pct": 58.1,
  "system_pct": 34.3,
  "max_process_pct": 145.2,
  "avg_pct": 88.0,
  "p95_pct": 94.5,
  "process_count": 186,
  "thread_count": 742,
  "ready_thread_count": 31,
  "running_thread_count": 8,
  "blocked_thread_count": 102,
  "long_blocked_thread_count": 4,
  "top_processes": [
    {
      "pid": 123,
      "name": "qvm",
      "cpu_pct": 145.2,
      "user_delta_ms": 1800,
      "system_delta_ms": 1100,
      "thread_count": 38,
      "priority": 10,
      "critical_process": false
    }
  ],
  "top_threads": [
    {
      "pid": 123,
      "tid": 7,
      "process": "qvm",
      "cpu_pct": 82.4,
      "state": "running",
      "last_cpu": 3,
      "priority": 10,
      "blocked_ms": 0
    }
  ],
  "scan_total": 186,
  "scan_failed": 3,
  "rebaseline_count": 1,
  "scan_limited": false
}
```

CPU 字段说明：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `cpu_count` | count | 在线 CPU 核数 |
| `total_pct` | percent | 系统总 CPU 使用率，按进程 runtime delta 估算 |
| `user_pct` | percent | 所有进程 user runtime 占比 |
| `system_pct` | percent | 所有进程 system runtime 占比 |
| `max_process_pct` | percent | 单进程最高 CPU，占多核时可超过 100 |
| `avg_pct` | percent | 窗口内平均 CPU |
| `p95_pct` | percent | 窗口内 p95 CPU |
| `ready_thread_count` | count | ready 线程数量 |
| `long_blocked_thread_count` | count | 阻塞超过配置阈值的线程数量 |
| `top_processes` | array | CPU TopN，常态可省略，异常携带 |
| `top_threads` | array | 热点线程，仅异常或 snapshot 携带 |
| `rebaseline_count` | count | 新进程或疑似 pid reuse 导致只建立 baseline 的进程数量 |
| `scan_limited` | bool | 是否达到扫描上限 |

采集语义：

- `total_pct/user_pct/system_pct` 来自 `DCMD_PROC_INFO.utime/stime` 的窗口 delta。
- 计算 delta 前必须确认进程身份没有变化；新进程或疑似 pid reuse 只做 baseline，不计入本轮 CPU。
- `rebaseline_count` 只表示本轮跳过 delta 的进程数，不代表异常。
- `top_threads` 来自 `DCMD_PROC_TIDSTATUS`，常态不全量采集。
- 如果线程状态权限不足，省略 `top_threads`，并通过本地 log 打印低频 warning。

### 15.4 Memory 上报格式

事件：QNX Memory 资源事件。

常态周期上报示例：

```json
{
  "ts_ms": 1781863200123,
  "level": "normal",
  "reason": "summary",
  "window_ms": 300000,
  "sample_count": 30,
  "ram_total_mb": 8192,
  "sysram_total_mb": 6144,
  "sysram_free_mb": 1800,
  "sysram_used_mb": 4344,
  "sysram_free_pct": 29.3,
  "sysram_used_pct": 70.7,
  "process_count": 186,
  "scan_total": 186,
  "scan_failed": 2,
  "scan_limited": false
}
```

异常上报示例：

```json
{
  "ts_ms": 1781863200123,
  "level": "critical",
  "reason": "enter",
  "trigger": "sysram_low",
  "suspect": "memory_process_private",
  "window_ms": 300000,
  "sample_count": 30,
  "ram_total_mb": 8192,
  "sysram_total_mb": 6144,
  "sysram_free_mb": 420,
  "sysram_used_mb": 5724,
  "sysram_free_pct": 6.8,
  "sysram_used_pct": 93.2,
  "process_count": 186,
  "top_processes": [
    {
      "pid": 123,
      "name": "qvm",
      "rss_mb": 1300,
      "private_mb": 900,
      "shared_mb": 400,
      "map_count": 320,
      "thread_count": 38
    }
  ],
  "trend": {
    "window_sec": 300,
    "sysram_free_slope_mb_per_min": -120.5,
    "sysram_free_r2": 0.86,
    "top_private_slope_mb_per_min": 35.2
  },
  "scan_total": 186,
  "scan_failed": 3,
  "scan_limited": false
}
```

Memory 字段说明：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `ram_total_mb` | MB | syspage `asinfo` 统计的 RAM 总量 |
| `sysram_total_mb` | MB | QNX typed memory `/sysram` 总量 |
| `sysram_free_mb` | MB | `/sysram` 当前可分配量 |
| `sysram_used_mb` | MB | `sysram_total_mb - sysram_free_mb` |
| `sysram_free_pct` | percent | `/sysram` 可分配比例 |
| `sysram_used_pct` | percent | `/sysram` 使用比例 |
| `top_processes[].rss_mb` | MB | `DCMD_PROC_ASINFO.rss` |
| `top_processes[].private_mb` | MB | `DCMD_PROC_ASINFO.map_private`，不可用时用 `DCMD_PROC_INFO.private_mem` |
| `top_processes[].shared_mb` | MB | `DCMD_PROC_ASINFO.map_shared` |
| `trend` | object | 仅异常或配置开启时携带 |

`suspect` 建议枚举：

| suspect | 说明 |
| --- | --- |
| `memory_process_private` | 进程 private 内存增长 |
| `memory_process_rss` | 进程 RSS 增长 |
| `memory_non_process` | 非进程私有内存增长，例如 typed memory、pmem、驱动缓冲 |
| `unknown` | 暂无法归因 |

采集语义：

- `sysram_free_mb` 是 QNX `/sysram` 可分配内存，不等价于 Linux `MemAvailable`。
- TopN 进程内存扫描只在低内存异常或低频周期执行，避免常态开销过高。
- 趋势字段用于辅助定位，不单独作为泄漏根因结论。
- 二阶段内存池监控（5.4）命中时，可携带可选 `pools` 数组（每项 `name/total_mb/free_mb/free_contig_mb/used_pct/used_slope_mb_per_min/available`）；当某池被判定为疑似泄漏，`suspect=memory_non_process` 并带 `suspect_pool=<name>`。接口不可用的池设 `available=false`，不伪造数值。

### 15.5 IO 上报格式

事件：QNX IO 资源事件。

```json
{
  "ts_ms": 1781863200123,
  "level": "warning",
  "reason": "enter",
  "trigger": "storage_device_error",
  "window_ms": 60000,
  "storage_devices": [
    {
      "name": "ufs0",
      "type": "ufs",
      "health_available": true,
      "health": "warning",
      "io_error_count": 3,
      "reset_count": 1,
      "last_error": "scsi io error"
    }
  ]
}
```

IO 字段说明：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `storage_devices[].health_available` | bool | 平台是否暴露该设备健康接口，不可用时为 `false` 且不伪造其余字段 |
| `storage_devices[].health` | string | `ok`、`warning`、`critical`、`unknown` |
| `storage_devices[].io_error_count` | count | 设备错误累计计数，如果平台接口支持 |
| `storage_devices[].reset_count` | count | 设备 reset 累计计数，如果平台接口支持 |
| `storage_devices[].last_error` | string | 最近一次错误的简短描述，限长 |

说明：

- `storage_devices` 依赖目标板 UFS/NVMe/SDMMC 实际接口；接口不可用时设置 `health_available:false`，不伪造计数。
- 本版本 IO 事件只覆盖存储设备健康，不含文件系统容量、IO 性能和进程级 IO（见第 6 章范围说明）。


### 15.6 Network 上报格式

事件：QNX Network 资源事件。

```json
{
  "ts_ms": 1781863200123,
  "level": "warning",
  "reason": "enter",
  "trigger": "network_error_growth",
  "window_ms": 60000,
  "interfaces": [
    {
      "name": "en0",
      "admin_up": true,
      "link_up": true,
      "speed_mbps": 1000,
      "mtu": 1500,
      "stats_available": true,
      "rx_bytes_delta": 10485760,
      "tx_bytes_delta": 2097152,
      "rx_packets_delta": 8120,
      "tx_packets_delta": 2400,
      "rx_errors_delta": 12,
      "tx_errors_delta": 0,
      "rx_drops_delta": 3,
      "tx_drops_available": false
    }
  ],
  "socket_stats_available": false,
  "socket_stats_error": "not_supported"
}
```

Network 字段说明：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `interfaces[].admin_up` | bool | 接口管理状态 |
| `interfaces[].link_up` | bool | 物理或逻辑链路状态 |
| `interfaces[].speed_mbps` | Mbps | 链路速率，不可获取时省略 |
| `interfaces[].stats_available` | bool | 是否支持接口统计 |
| `rx_bytes_delta` / `tx_bytes_delta` | bytes | 窗口内收发字节增量，来自 `if_data.ifi_ibytes/ifi_obytes` |
| `rx_errors_delta` / `tx_errors_delta` | count | 窗口内错误计数增量，来自 `if_data.ifi_ierrors/ifi_oerrors` |
| `rx_drops_delta` | count | 窗口内输入丢包增量，来自 `if_data.ifi_iqdrops` |
| `tx_drops_available` | bool | QNX SDP 7.1 `if_data` 无输出丢包字段，默认 `false`，不上报伪造的 `tx_drops_delta` |
| `socket_stats_available` | bool | 是否支持 socket/协议栈统计 |

说明：

- 常态只上报关键接口摘要；异常时可携带所有配置接口。
- 如果接口统计不可用，保留 `link_up`，并设置 `stats_available=false`。
- 不上报抓包内容，不周期解析大日志。

### 15.7 Thermal 上报格式

事件：QNX Thermal 资源事件。

```json
{
  "ts_ms": 1781863200123,
  "level": "critical",
  "reason": "enter",
  "trigger": "thermal_critical",
  "window_ms": 30000,
  "max_temp_c": 106.5,
  "zones": [
    {
      "name": "soc",
      "sensor_available": true,
      "temp_c": 106.5,
      "warning_c": 90,
      "critical_c": 105,
      "sample_age_ms": 120,
      "throttling_available": true,
      "throttling_active": true,
      "cooling_state": "level2"
    }
  ],
  "trend": {
    "window_sec": 60,
    "max_temp_slope_c_per_min": 8.4
  }
}
```

Thermal 字段说明：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `max_temp_c` | Celsius | 本次样本中最高温度 |
| `zones[].sensor_available` | bool | sensor 是否可用 |
| `zones[].temp_c` | Celsius | 当前温度 |
| `zones[].warning_c` | Celsius | warning 阈值 |
| `zones[].critical_c` | Celsius | critical 阈值 |
| `zones[].sample_age_ms` | ms | 样本年龄 |
| `zones[].throttling_available` | bool | 是否支持热限频状态 |
| `zones[].throttling_active` | bool | 是否正在热限频 |
| `zones[].cooling_state` | string | 平台 cooling 状态，不可获取时省略 |

说明：

- 温度作为系统资源异常的关联信号，默认低频采集。
- 如果目标镜像没有 sensor 接口，打印低频 warning，并上报 `sensor_available=false`。
- 不通过 CPU 降频现象反推温度或 throttling 状态。

### 15.8 Crash 上报格式

事件：QNX Process Crash 事件。

```json
{
  "ts_ms": 1781863205123,
  "level": "critical",
  "reason": "core_created",
  "pid": 456,
  "process": "media_service",
  "signal": "SIGSEGV",
  "core_path": "/var/log/coredump/media_service.456.core.gz",
  "core_size_mb": 32,
  "detected_by": "dumper_dir_scan",
  "slog2_excerpt": "process media_service faulted at ...",
  "duplicate": false
}
```

Crash 字段说明：

| 字段 | 说明 |
| --- | --- |
| `reason` | Crash 事件原因，可取 `core_created`、`slog2_crash`、`manual_report` |
| `pid` | 崩溃进程 pid，无法解析时可省略 |
| `process` | 崩溃进程名 |
| `signal` | 崩溃信号，例如 `SIGSEGV`、`SIGABRT` |
| `core_path` | core 文件路径，只上报路径，不读取完整 core |
| `core_size_mb` | core 文件大小 |
| `detected_by` | 检测来源，例如 `dumper_dir_scan`、`slog2_scan` |
| `slog2_excerpt` | 限长日志摘要，建议不超过 512 字节 |
| `duplicate` | 是否为重复事件 |

Crash 检测策略：

- QNX 默认没有 Linux inotify，coredump 目录采用低频 polling，默认 10s。
- 只扫描目录项、mtime 和文件大小，不读取完整 core 内容。
- 如果系统存在自动清理脚本，需要保证 core 文件保留时间大于两倍 polling 周期，否则可能出现 crash 已生成但被清理后漏检。
- slog2 crash 记录作为目录 polling 的补充信号；优先使用结构化 reader/API，如果只能调用 `slog2info`，则只允许低频或异常 snapshot 使用。
- 对同一路径、同一 pid、同一进程名的重复 crash 做去重，避免持续上报。

### 15.9 格式演进规则

- 每类事件通过 event id 区分，不在 JSON 内增加 `schema`。
- 字段演进只追加，不重命名旧字段。
- 如果字段语义变化，新增字段承载新语义，旧字段保留到消费端完成迁移。
- 常态周期上报不携带大数组；异常上报可携带 TopN，但 TopN 默认不超过 5，snapshot 不超过 20。
- 大文本字段必须限长，禁止上报完整 slog 或 core 内容。

## 16. 分阶段实现

### 第一阶段：低风险基础监控

实现：

- 系统 CPU。
- 进程 CPU TopN。
- 系统 Memory。
- 进程 Memory TopN。
- 基础 Network 接口状态和错误计数。
- 基础 Thermal 温度采样。
- coredump 新文件检测。
- QNX 专属上报格式。
- 本地日志和限流。

不实现：

- 文件系统容量监控（磁盘由平台轮转管理）。
- IO 性能统计（IOPS、吞吐、延迟、队列深度）。
- 进程级 IO 归因。
- 线程被 IO 阻塞检测。
- socket buffer、SOME/IP、DDS、CAN 等协议级网络归因。
- 热限频根因分析。
- 全线程常态扫描。
- 依赖外部命令的周期采样。

### 第二阶段：QNX 平台增强

实现：

- TopN 进程线程状态快照。
- Memory 趋势和斜率判断。
- UFS/NVMe/SDMMC 健康接口适配。
- Network socket/协议栈统计适配，如果平台接口可用。
- Thermal throttling/cooling 状态适配，如果平台接口可用。
- QVM/pmem 相关内存分类，如果平台接口可用。

### 第三阶段：异常诊断增强

实现：

- 异常时自动打印更完整上下文。
- 与 dump collector 或诊断系统联动。
- 可选 trace 触发，但必须默认关闭，并设置时间预算。

## 17. 风险和边界

- QNX 的 CPU/Memory 语义与 Linux 不完全一致，阈值需要实车标定。
- IO 监控只覆盖存储设备健康，依赖平台驱动暴露 UFS/NVMe/SDMMC 接口；不做文件系统容量、IO 性能、进程级 IO 和线程 IO 阻塞检测。
- 线程被 IO 阻塞在 QNX 上表现为 REPLY/WAITPAGE 阻塞在 IO 服务进程上，CPU 阈值无法捕捉；本版本不实现，后续如需要应作为线程态分析的独立 detector。
- 异常时不要启动高开销外部命令循环采样。
- 低内存时不要读大文件、不要扫描全量 dump、不要解析大日志。
- 所有异常快照必须有冷却时间，防止监控进程自身加剧系统压力。
- QNX 上报格式不再兼容 Linux，但 CPU/MEM 的 `reason` 取值仍保持 `summary`、`enter`、`clear`。
- Network 统计依赖 QNX 网络栈和目标镜像暴露能力，第一阶段只承诺关键接口基础状态和错误计数。
- Thermal 统计依赖平台 sensor/thermal service，接口不可用时只能标记 unavailable。
- CPU 使用率基于进程 runtime delta 估算，不覆盖所有微内核和中断开销；阈值必须按目标板标定。

## 18. 验收标准

功能验收：

- 能持续打印周期性健康摘要，默认低频。
- CPU 高压时能打印系统 CPU 和进程 TopN。
- 内存不足时能打印可用内存、进程内存 TopN 和趋势。
- 存储设备 health 异常或 error/reset 计数增长时能打印设备名和 delta。
- 关键网络接口 link down、错误计数或丢包计数增长时能打印接口名和 delta。
- 温度超过阈值时能打印 sensor、温度和阈值。
- 新 coredump 出现时能打印进程名、文件路径、时间戳。
- CPU、Memory、IO、Network、Thermal、Crash 六类独立上报格式符合第 15 章定义。

性能验收：

- 常态平均 CPU 小于单核 2%，p95 小于单核 3%。
- 空闲场景平均 CPU 小于单核 1%。
- 压力场景平均 CPU 小于单核 2.5%。
- 异常触发后 10s 平均 CPU 小于单核 3%；超过单核 5% 时必须立即停止可选诊断并退避。
- 常态 RSS 设计目标小于 80 MB，硬性上限小于 150 MB。
- 日志限流生效，异常持续时不会刷屏。

可靠性验收：

- 监控进程崩溃后可被 SLM 拉起。
- 单个 collector 失败、超时或进入 Unknown 不影响主进程。
- QNX 接口返回错误时打印低频 warning，并继续运行。
- 配置为编译期内置常量，启动不依赖任何外部配置文件。

## 19. 附录：接口核实（QNX SDP 7.1）

本节基于本地 QNX SDP 7.1 SDK 头文件（`sdk/qnx710/target/qnx7/usr/include`）逐条核实方案中使用的接口与结构体字段，作为实现前的依据。结论：方案所列 QNX 接口在 7.1 上均真实存在，字段名与语义吻合；仅有两处需按平台能力修正（typed memory 的 `tflag`、网络输出丢包字段）。

### 19.1 procfs / devctl

| 用途 | devctl / 结构体 | 出处 | 关键字段 |
| --- | --- | --- | --- |
| 进程 CPU/基础信息 | `DCMD_PROC_INFO` → `procfs_info`(`debug_process_t`) | `sys/procfs.h:156,47`；`sys/debug.h:210` | `utime`、`stime`(`debug.h:235-236`)、`start_time`(`234`)、`num_threads`(`232`)、`private_mem`(`246`)、`priority`(`239`)、`crit_proc`(`240`) |
| 进程地址空间聚合 | `DCMD_PROC_ASINFO` → `procfs_asinfo`(`debug_aspace_t`) | `sys/procfs.h:391,67`；`sys/debug.h:603-611` | `rss`、`map_private`、`map_shared`、`map_count`、`as_size`、`as_used`（单次定长返回，**无需遍历 MAPINFO**） |
| 线程状态 | `DCMD_PROC_TIDSTATUS` → `procfs_status`(`debug_thread_t`) | `sys/procfs.h:237,50`；`sys/debug.h:252/318` | `state`(`267`)、`last_cpu`(`269`)、`sutime`(`311`)、`start_time`(`310`)、`nsec_since_block`(`313`，注释明确为"已阻塞时长，READY/RUNNING 为 0，ms 分辨率") |
| 逐段内存映射（备用/诊断） | `DCMD_PROC_MAPINFO` → `procfs_mapinfo` | `sys/procfs.h:166,76` | 仅做精细诊断时使用；常态内存 TopN 用 ASINFO 即可 |
| procfs 访问能力 | `PROCFS_ABLE_*` / `DCMD_PROC_ABILITIES` | `sys/procfs.h:110-141,429` | 证实跨进程读 procfs 受 ability 模型管控，部署需授权 |

要点：

- 进程身份缓存 key 用 `pid + start_time` 成立（`start_time` 真实存在）。
- 进程内存 TopN 每进程仅 `DCMD_PROC_INFO` + `DCMD_PROC_ASINFO` 两次定长 devctl，与 CPU 扫描同量级，第 11.1 节内存预算成立。
- `crit_proc` 字段可直接支撑上报中的 `critical_process` 标记。

### 19.2 typed memory（系统可用内存）

- `posix_typed_mem_open(const char*, int, int)`(`sys/mman.h:264`)、`posix_typed_mem_get_info()`(`mman.h:298`)、`posix_typed_mem_info.posix_tmi_length`(`mman.h:272-291`) 均真实存在。
- `TYPEMEM_SYSRAM` 是标准宏，展开为 `"/sysram"`(`mman.h:369`)。
- **修正项**：`tflag` 须传 `POSIX_TYPED_MEM_ALLOCATE`(`mman.h:261`)，否则 `posix_tmi_length` 不表示可分配（空闲）量。已在第 5.1 节修正。

### 19.3 网络 / 日志

- `getifaddrs()`(`ifaddrs.h:56`)、QNX 扩展 `getifaddrs_fib()`(`ifaddrs.h:58`)；`struct if_data`(`net/if.h:216`) 含 `ifi_ibytes/ifi_obytes/ifi_ierrors/ifi_oerrors/ifi_iqdrops`(`227-235`)。
- **修正项**：7.1 `if_data` 仅有输入丢包 `ifi_iqdrops`，无输出丢包字段（无 `ifi_oqdrops`），`tx_drops_delta` 默认不可得。已在第 7.1、15.6 节修正为 `tx_drops_available:false`。
- 结构化日志：`sys/slog2.h` 存在，支持优先用结构化 reader 而非 `slog2info` 命令。

注：文件系统容量监控已从方案中移除（磁盘由平台轮转管理），`statvfs()` 相关核实不再适用。

### 19.4 仍需在目标镜像（而非 SDK 头文件）确认的项

以下依赖 BSP/驱动在运行镜像中的实际暴露，头文件无法证明，须在目标板实测：

- ~~Thermal sensor / thermal zone 节点与 throttling/cooling 状态接口。~~ → 已确认：`sysprofiler` 的 `thermal::THERMAL_MON` 经 `/dev/thermalmgr` 提供 sensor 名称和温度值，见 19.5.9。
- UFS/NVMe/SDMMC 存储健康与 io-blk/devb 性能统计接口。
- socket buffer、TCP retransmit、SOME/IP、DDS、CAN 等协议级统计。
- polaris-monitor 在 secpol 下读取其他进程 procfs 所需的 ability 授权（见第 14 节 `mega.polaris_monitor.txt`）。

### 19.5 sysprofiler — Qualcomm 平台监控库（8295 已部署）

Qualcomm 为 SA8295P 平台提供了预编译的 `sysprofiler` 库，封装了 CPU、GPU、Memory、Thermal、Network、DiskIO、DDR、Process、Thread 的硬件级采样接口。该库在 `health_monitor`（`qnx/mega/apps/health_monitor/gpu-src/`）中已被集成并验证可用，polaris-monitor 可复用以大幅降低开发量和采样的硬件耦合度。

**头文件位置**：`qnx/hlos_dev_qnx/apps/qnx_ap/prebuilt/usr/include/sysprofiler.h`

**预编译二进制**：`qnx/hlos_dev_qnx/apps/qnx_ap/prebuilt/aarch64le/bin/sysprofiler_app`

**接口性质**：

- C++ 库，使用 Pimpl 模式（`std::unique_ptr<XXX_MON_INTERFACE>`），所有实现细节隐藏在闭源 `.so` 中。
- 每个 namespace 对应一个资源类别，提供独立的 `XXX_MON` 类。
- `thermal` 的后端设备节点为 `/dev/thermalmgr`（`sysprofiler.h:17`）。
- GPU 后端依赖 `/dev/kgsl-control`（见 19.5.3 和现有 `health_monitor/gpu-src/gpu.c` 中的 `waitfor("/dev/kgsl-control")`）。

**与 polaris-monitor 的关系**：

- `sysprofiler` 为闭源库，不可修改、不可调试内部行为，不能作为通用的方案。
- 使用 `sysprofiler` 时，polaris-monitor 需要链接 C++ 标准库（`libcpp`），且 Collector 层需用 `extern "C"` 包装 C++ 调用（参考 `health_monitor/gpu-src/gpu_util.cpp`）。

#### 19.5.1 gpu::GPU_MON — GPU 利用率与频率

```cpp
namespace gpu {
    class GPU_MON {
    public:
        GPU_MON();
        void sysprofiler_setForcedMaxGPUFrequency(int);  // 强制设置 GPU 最高频率，参数单位 MHz
        int  sysprofiler_getGPUSample();                  // 触发一次采样，返回 -1 表示失败
        float sysprofiler_getGPUFrequency();              // GPU 当前频率 (MHz)，需先 getGPUSample()
        float sysprofiler_getGPUUtilization();            // GPU 利用率百分比 (0~100)，需先 getGPUSample()
        float sysprofiler_gpuBusBusy();                   // GPU 总线繁忙百分比
        float sysprofiler_getReadBandwidth();             // GPU 读带宽
        float sysprofiler_getWriteBandwidth();            // GPU 写带宽
        std::vector<std::string> sysprofiler_getGPUHeaders(); // 监控指标名称列表
        ~GPU_MON();
    };
}
```

调用顺序：先 `sysprofiler_getGPUSample()` → 若返回值 ≠ -1，再取 `getGPUFrequency()` / `getGPUUtilization()`。

对应 polaris-monitor 模块：可新增 `GpuCollector`，常态 60s 采样，异常最低 30s，指标按 GPU 专属格式上报（需新增 event id）。

#### 19.5.2 cpu::CPU_MON — 系统 CPU 负载与频率

```cpp
namespace cpu {
    class CPU_MON {
    public:
        CPU_MON();
        double*  sysprofiler_getPerCoreUsage();           // 每核 CPU 使用率数组
        double   sysprofiler_getTotalCPULoad();           // 系统总 CPU 负载百分比
        long int* sysprofiler_getCPUFrequency();          // 每核 CPU 频率数组 (KHz)
        char**   sysprofiler_getClockNames();             // 每核时钟域名称
        void     sysprofiler_setSamplingTime(int);        // 设置采样间隔 (ms)
        ~CPU_MON();
    };
}
```

对应 polaris-monitor 的 4.1 节（系统 CPU 使用率）。`getTotalCPULoad()` 直接给出整系统 CPU%，比手动遍历 `/proc` + `DCMD_PROC_INFO` 累加 delta 更简单，且能覆盖中断、idle、内核路径（弥补 raw procfs 方案的已知盲区）。局限性：采样精度取决于闭源实现，不支持按进程拆分。

#### 19.5.3 KGSL GPU 性能等级（补充）

```c
// 头文件: qnx/hlos_dev_qnx/apps/qnx_ap/AMSS/inc/gfx_gmu_perf_table.h
#define MAX_SUPPORTED_PERF_LEVELS 16
#define DCMD_KGSL_GET_PERF_LEVELS_INFO  __DIOTF(_DCMD_MISC, 0, kgsl_get_perf_level_info_t)

typedef struct _kgsl_get_perf_level_info_t {
    unsigned int num_levels;
    unsigned int perf_level[MAX_SUPPORTED_PERF_LEVELS];  // 各档频率值
} kgsl_get_perf_level_info_t;
```

设备节点 `/dev/kgsl-control`，通过 `open(O_RDWR)` + `devctl(DCMD_KGSL_GET_PERF_LEVELS_INFO)` 获取 GPU 可用频率档位表；通过 `write("gpu_gfx_core_clock_level N ")` 设置频率。此接口只提供频率表，**不提供 GPU 利用率**。利用率必须通过 `gpu::GPU_MON` 获取。

#### 19.5.4 process::PROCESS_MON — 进程 CPU 使用率

```cpp
namespace process {
    struct resultProcInfo {
        int pid;
        char processName[64];
        double systemTime;
        double userTime;
        double totalTime;
        double cpuUsage;          // 进程 CPU 使用率百分比
    };

    class PROCESS_MON {
    public:
        int num_cpus;
        PROCESS_MON();
        PROCESS_MON(std::vector<int>);  // 传入关注的 pid 列表
        std::vector<struct resultProcInfo> sysprofiler_getProcessStats();
        std::vector<struct resultProcInfo> sysprofiler_getProcessStats(std::vector<int>);
        void sysprofiler_setSamplingTime(int);
        ~PROCESS_MON();
    };
}
```

对应 4.2 节（进程 CPU TopN）。可直接拿到每个进程的 `cpuUsage` 和 `processName`，无需手动计算 delta 或处理 pid reuse。可配合 pid 过滤降低开销。

#### 19.5.5 thread::THREAD_MON — 线程 CPU 使用率

```cpp
namespace thread {
    struct finalThreadInfo {
        int pid;
        std::string pname;
        int tid;
        int sutime;              // 线程系统态时间
        float cpuUsage;          // 线程 CPU 使用率百分比
    };

    class THREAD_MON {
    public:
        int num_cpus;
        THREAD_MON();
        std::vector<struct finalThreadInfo> sysprofiler_getThreadStats();
        void sysprofiler_setSamplingTime(int);
        ~THREAD_MON();
    };
}
```

对应 4.3 节（线程状态和阻塞信息）。注意 `finalThreadInfo` 不含线程状态字段（`state`/`last_cpu`/`nsec_since_block`），线程阻塞分析仍需 raw `DCMD_PROC_TIDSTATUS` 补充。

#### 19.5.6 procmem::PROCMEM_MON — 进程内存详情

```cpp
namespace procmem {
    struct processMemoryMap {
        int pid;
        char procName[64];
        unsigned int heap;
        unsigned int stack;
        unsigned int data;
        unsigned int code;
        size_t address_space;
        unsigned int total;
    };

    class PROCMEM_MON {
    public:
        PROCMEM_MON();
        std::vector<struct processMemoryMap> sysprofiler_getPerProcessMemStats();
        std::vector<struct processMemoryMap> sysprofiler_getPerProcessMemStats(std::vector<int>);
        ~PROCMEM_MON();
    };
}
```

对应 5.2 节（进程内存 TopN）。按 heap/stack/data/code 拆分，比 raw `DCMD_PROC_ASINFO` 的 `rss/map_private/map_shared` 更细粒度。但无 `private_mem`、`shared_mem` 字段，如需兼容文档 5.2 节中的 `private_mb`/`shared_mb` 字段，仍需 `DCMD_PROC_ASINFO` 补充。

#### 19.5.7 memory::MEMORY_MON — 系统内存分区信息

```cpp
namespace memory {
    struct memStats {
        std::string asName;      // 分区名称
        long int freeMem;
        long int usedMem;
        long int totalMem;
    };

    class MEMORY_MON {
    public:
        int partitionsProfiled;
        MEMORY_MON();
        struct memory::memStats* sysprofiler_getMemStats();
        ~MEMORY_MON();
    };
}
```

对应 5.1 节（系统可用内存）。提供按地址空间（as）分区的内存统计。需实测确认 `asName` 的返回值是否包含 `/sysram` 等价信息，以及数值是否与 `posix_typed_mem_get_info()` 对齐。

#### 19.5.8 net::NET_MON — 网络接口流量

```cpp
namespace net {
    struct netStats {
        std::string interfaceName;
        unsigned long long int rxBytes;
        unsigned long long int txBytes;
        double rxBandwidth;
        double txBandwidth;
    };

    class NET_MON {
    public:
        NET_MON();
        std::vector<struct netStats> sysprofiler_getNetstats();
        void sysprofiler_setSamplingTime(int);
        ~NET_MON();
    };
}
```

对应 7.1 节（网络接口状态和流量）。提供 rxBytes/txBytes 和带宽，但**不提供** error/drops 计数、link 状态、admin 状态。链路状态和错误计数仍需 `getifaddrs()` + `struct if_data` 补充。

#### 19.5.9 thermal::THERMAL_MON — 温度传感器

```cpp
namespace thermal {
    class THERMAL_MON {
    public:
        bool initStatus;
        THERMAL_MON();
        std::vector<std::string> sysprofiler_getSensorNames();  // sensor 名称列表
        std::vector<int> sysprofiler_getThermalStats();         // 对应温度值（单位需实测确认）
        int sysprofiler_getNumSensors();                        // sensor 数量
        ~THERMAL_MON();
    };
}
```

设备节点：`/dev/thermalmgr`（`sysprofiler.h:17` 定义）。

对应 8.1 节（温度传感器）。提供 sensor 名称和温度值列表，但**不提供** warning/critical 阈值和 throttling 状态（这些需平台 thermal service 或 BSP devctl 补充）。注意返回值是 `std::vector<int>`，单位需在目标板实测确认（预计为 millidegree Celsius 或 degree Celsius）。

#### 19.5.10 diskio::DISKIO_MON — 磁盘 IO 统计

```cpp
namespace diskio {
    struct iostats_t {
        char name[16];
        unsigned long physicalReads;
        unsigned long physicalWrites;
        unsigned long cacheReads;
        unsigned long cacheWrites;
        unsigned long ioRequests;
    };

    class DISKIO_MON {
    public:
        int numberOfParams;
        DISKIO_MON();
        std::vector<struct diskio::iostats_t> sysprofiler_getIOStats(char*);     // 两次采样差值
        std::vector<struct diskio::iostats_t> sysprofiler_getRawIOStats(char*);  // 原始累计值
        void sysprofiler_setSamplingTime(int);
        ~DISKIO_MON();
    };
}
```

提供块设备的读写和 IO 请求计数。注意 `iostats_t` 不含 IOPS、吞吐、延迟、队列深度等性能指标，且不提供设备健康状态（对应 6.1 节存储健康仍需 UFS/NVMe devctl）。

#### 19.5.11 ddr::DDR_MON — DDR 带宽与频率

```cpp
namespace ddr {
    class DDR_MON {
    public:
        int numStats;
        DDR_MON(int enabledIPs);
        uint64_t* sysprofiler_getDDRStats();        // DDR 带宽统计
        long sysprofiler_getDDRClockFrequency();    // DDR 时钟频率
        void sysprofiler_setSamplingTime(int);
        bool sysprofiler_getMachineName();
        ~DDR_MON();
    };
}
```

DDR 带宽是内存压力的重要关联信号。polaris-monitor 可在 Memory 异常时携带 DDR 带宽作为辅助上下文，帮助区分"应用内存泄漏"和"DDR 带宽瓶颈导致的卡顿"。

#### 19.5.12 cpu_pmu::CPU_PMU_MON — CPU PMU 事件计数

```cpp
namespace cpu_pmu {
    struct cpu_pmu_data_profiler {
        char coreType[4];
        int coreID;
        int* eventID;
        unsigned long int* value;
    };

    class CPU_PMU_MON {
    public:
        CPU_PMU_MON();
        int sysprofiler_cpu_pmu_get_nevents();
        int sysprofiler_cpu_pmu_init(int*, int);
        int sysprofiler_cpu_pmu_start_profiling();
        int sysprofiler_cpu_pmu_stop_profiling();
        int sysprofiler_cpu_pmu_get_data(struct cpu_pmu_data_profiler*);
        int sysprofiler_cpu_pmu_deinit();
        int sysprofiler_getCPUNum();
        ~CPU_PMU_MON();
    };
}
```

提供 CPU 硬件性能计数器（cache miss、branch mispredict、IPC 等），用于深度性能诊断。polaris-monitor 不建议常态启用（PMU 配置和采样有额外开销），可作为第三阶段异常诊断增强的可选项。

#### 19.5.13 cpu_ddr_bwmon::CPU_DDR_BWMON — CPU-DDR 带宽

```cpp
namespace cpu_ddr_bwmon {
    class CPU_DDR_BWMON {
    public:
        CPU_DDR_BWMON();
        double sysprofiler_getcpuddrBW();
        void sysprofiler_setSamplingTime(int);
        ~CPU_DDR_BWMON();
    };
}
```

#### 19.5.14 库级工具函数

```cpp
// 版本信息
void printLibraryVersion();
std::string getLibraryVersion();

// slog2 日志宏（sysprofiler 内部使用的 slog2 封装）
#define slog_info(slog2_buffer, fmt, ...) ...
#define slog_error(slog2_buffer, fmt, ...) ...

// DSP 标识符（用于 DSP_MON 构造参数）
#define ADSP_ID  0
#define CDSP_ID  1
#define NPU_ID   2
#define CDSP1_ID 3
#define GDSP0_ID 4
#define GDSP1_ID 5
```

#### 19.5.15 sysprofiler 与 raw QNX 接口的覆盖对比

| 监控模块 | raw QNX 接口（方案第 2 节） | sysprofiler 替代 | 覆盖度 | 备注 |
| --- | --- | --- | --- | --- |
| 系统 CPU | `DCMD_PROC_INFO` 遍历累加 | `cpu::CPU_MON::getTotalCPULoad()` | ✅ 可替代 | sysprofiler 覆盖中断/idle/内核，更准确；但不透传进程明细 |
| 进程 CPU TopN | `DCMD_PROC_INFO` 排序 | `process::PROCESS_MON::getProcessStats()` | ✅ 可替代 | 直接给 `cpuUsage`，免手动 delta 计算和 pid reuse 处理 |
| 线程 CPU | `DCMD_PROC_TIDSTATUS` | `thread::THREAD_MON::getThreadStats()` | ⚠️ 部分 | 缺 `state`/`last_cpu`/`nsec_since_block`，阻塞分析需 raw 接口 |
| 系统 Memory | `posix_typed_mem_get_info()` | `memory::MEMORY_MON::getMemStats()` | ⚠️ 部分 | 需实测验证 as 分区是否含 `/sysram` |
| 进程 Memory | `DCMD_PROC_ASINFO` | `procmem::PROCMEM_MON::getPerProcessMemStats()` | ⚠️ 部分 | 有 heap/stack/code/data 拆分，缺 `private_mb`/`shared_mb` |
| GPU | 无标准接口 | `gpu::GPU_MON` | ✅ 唯一方案 | raw KGSL devctl 只能拿频率表，无利用率 |
| Network 流量 | `getifaddrs()` → `if_data` | `net::NET_MON::getNetstats()` | ⚠️ 部分 | 无 error/drops/link 状态，需 `if_data` 补充 |
| Thermal | 无标准接口（原标 unknown） | `thermal::THERMAL_MON` | ✅ 可替代 | 经 `/dev/thermalmgr`，单位需实测 |
| Disk IO | 无（原标依赖平台工具） | `diskio::DISKIO_MON` | ⚠️ 部分 | 只给读写计数，无设备 health 状态 |
| DDR 带宽 | 无 | `ddr::DDR_MON` | ✅ 唯一方案 | 辅助 Memory 异常诊断 |
| CPU PMU | 无 | `cpu_pmu::CPU_PMU_MON` | — | 仅第三阶段诊断用 |
| Crash | slog2/dumper 目录扫描 | — | ❌ 无覆盖 | 仍需 raw slog2 reader + coredump polling |
| 存储健康 | UFS/NVMe devctl | — | ❌ 无覆盖 | 仍需平台驱动接口 |

#### 19.5.16 集成注意事项

1. **C++ 链接**：polaris-monitor 若主体用 C，需将 sysprofiler 调用封装在 `extern "C"` 的 `.cpp` 翻译单元中，参考 `health_monitor/gpu-src/gpu_util.cpp`。
2. **设备节点依赖**：GPU 依赖 `/dev/kgsl-control`，Thermal 依赖 `/dev/thermalmgr`。启动时需 `waitfor()` 等待节点就绪。
3. **闭源风险**：sysprofiler 的采样精度、CPU 开销、内存分配行为无法审计。polaris-monitor 的自监控（第 10 节）需覆盖 sysprofiler 调用耗时，若单次采样超过预算应退避到 raw 接口。
4. **安全策略**：`/dev/kgsl-control` 和 `/dev/thermalmgr` 可能需要 secpol ability 授权（与 `mega.polaris_monitor.txt` 一并评估）。
5. **版本耦合**：sysprofiler 随 Qualcomm BSP 发布，平台升级时接口可能变化。建议在 `config.h` 中增加 `POLARIS_USE_SYSPROFILER` 编译开关，以便快速切回 raw 接口。
