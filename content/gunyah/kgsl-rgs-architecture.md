+++
date = '2026-07-15T10:00:00+08:00'
draft = true
title = 'Qualcomm PVM KGSL/RGS 架构、GPU Hang 检测与 BPMD 落盘'
tags = ["Qualcomm", "Adreno", "KGSL", "RGS", "GPU", "Gunyah", "HAB", "Debug"]
+++

## 1. 范围与结论

本文基于 SA8797 Gen5 工程源码、PVM 预编译 Adreno 库、2026-07-13 复现日志和 Perfetto/Davey 数据，说明 Gunyah 图形虚拟化中的提交、完成、hang 检测和 state dump 路径。

这里有两个名称容易混淆：

- Android Guest 使用 Qualcomm UMD、Guest `libgsl.so` 和内核 `graphics-hgsl` 驱动（`/dev/hgsl`），不是直接访问物理 GPU。
- PVM 中 `kgsl@N.service` 启动的 `/usr/bin/kgsl -p N` 是用户态进程；它加载 `libGSLKernel.so`，其中实现 RGS（Remote Graphics Service）、GMU/HFI、故障恢复和 snapshot。它不是 Android 非虚拟化场景中的 `msm_kgsl.ko`。

本次核验后的核心结论是：

1. HAB 是 Guest 与 PVM 之间的控制、资源和回退 RPC 路径；context 完成 DBCQ 注册后，正常 IB 提交可以由 Guest HGSL 直接写 DBCQ 并通知 GMU，**不会每帧都经过 `gsl_hab_server`、PVM `libgsl` 和 RGS 用户态**。
2. DBCQ 与 IPCQ 不是同一条队列。DBCQ 是 Guest HGSL 到 GMU 的 per-context 提交快路径；当前 Guest IPCQ 协议证据只显示 `GSL_IPCQ_SNAPSHOT_DUMP`，不能把 IPCQ 写成普通 IB 的高频提交队列。
3. `GMU_GPU_SW_HANG(603)` 的协议语义是 Long IB timeout。本次实例打印的有效 long 参数是 512ms，但 603 本身不编码 512ms，也不能证明 shader 连续执行了恰好 512ms。
4. 启动日志中的 short 32ms 属于当前 RGS 二进制的 HB/long-job 检测配置。它不是 `rgs_device_set_preemption_check_short_timeout()`；后者是另一套 context-switch/preemption 检查，对应 602。
5. 本次 `kgsl-1571.log` 只有两次真实 HFI fault，均为 `error: 603`。日志中的 `rgs_hwl_determine_feature_support()[ 609]` 里 `[609]` 是源码行号，不是 error 609。
6. 两次 fault 都归属 Launcher 的 PVM GPU context 17，但这只证明 Launcher 的提交未在 long-job 窗口内 retire。现有日志不能单独证明根因是动态背景模糊、过度绘制、非法 Vulkan 指令或硬件损坏。
7. 第一次 fault 到 BPMD 创建约 2.036s、到 snapshot 完成约 2.054s；第二次分别约 2.338s 和 2.357s。这些是 fault 上报后的 dump/recovery 时间，不是 hang 判定阈值。

## 2. 证据基线

| 组件或数据 | 路径 | 用途 |
|---|---|---|
| Guest HGSL 驱动 | `vendor/vendor/qcom/opensource/graphics-hgsl/hgsl.c` | `/dev/hgsl` ioctl、DBCQ 提交、HAB 回退、timestamp wait |
| Guest HGSL 同步 | `vendor/vendor/qcom/opensource/graphics-hgsl/{hgsl.h,hgsl_sync.c,hgsl_gmugos.c}` | shadow timestamp、retire IRQ、dma-fence、Guest snapshot |
| HAB virtio 映射 | `vendor/kernel_platform/soc-repo/drivers/soc/qcom/hab/hab_virtio.c` | `MM_GFX -> device-id 94` |
| HAB vhost backend | `vendor/kernel_platform/soc-repo/drivers/soc/qcom/hab/hab_vhost.c` | `MM_GFX` 对应 `ogles` vhost 设备 |
| PVM vhost-user GPU 服务 | `linux/apps/apps_proc/vendor/qcom/opensource/vhost-user/vhost-user-gpu.service` | socket、`/dev/vhost-ogles`、queue 数量 |
| PVM KGSL/RGS 服务 | `linux/apps/apps_proc/prebuilt_HY11/sa8797/adreno/usr/lib/systemd/system/kgsl@.service` | `/usr/bin/kgsl -p %i`、依赖和环境 |
| PVM RGS 实现 | `linux/apps/apps_proc/prebuilt_HY11/sa8797/adreno/usr/lib/libGSLKernel.so` | 当前闭源实现的符号、字符串和反汇编 |
| HFI 协议 | `vendor/vendor/qcom/opensource/graphics-kernel/adreno_hfi.h` | ISSUE_CMD、TS_RETIRE、601/602/603/609 定义 |
| 复现 RGS 日志 | `reproduced_again/tmp-kgsl/kgsl-1571.log` | 实际配置、fault context、snapshot 和 recovery |
| 本地时区 syslog | `reproduced_again/20-06和20-08日志/linux_log/syslog/` | 把 RGS 原始 UTC 时间对齐到 CST |
| FenceMonitor | `qssi/frameworks/base/libs/gui/{Surface.cpp,FenceMonitor.cpp}` | GPU completion/HWC release thread、序号和 wait slice 语义 |

开源 `graphics-kernel` 可以解释同代 HFI 协议和处理方式，但 PVM 实际运行的是闭源 `libGSLKernel.so`。除非有 PVM 二进制反汇编或现场日志支持，不能把 Android `msm_kgsl` 的 2000ms dispatcher timeout、恢复步骤或默认值直接套到 RGS。

## 3. 正确的分层架构

下图把控制/回退、DBCQ 稳态提交、timestamp retire 和 fault snapshot 分成四条路径。若图未显示，可直接打开 [KGSL/RGS 架构图](/ethenslab/diagrams/kgsl-rgs-architecture.html)。

<iframe src="/ethenslab/diagrams/kgsl-rgs-architecture.html"
        style="width:100%;height:1380px;border:1px solid #30363d;border-radius:12px"
        loading="lazy" title="Qualcomm PVM KGSL/RGS architecture"></iframe>

### 3.1 从 Android 图形栈看 GSL

下图复用 [Android 图形渲染架构详解](./graphics.md#2-整体架构图) 中的总览图，用来补足应用、RenderThread、OpenGL ES/Vulkan、Qualcomm UMD 与 Guest GSL/HGSL 之间的关系。

![](../../static/images/gunyah-graphics.png)

这张图中的 GSL 原理可以概括为：

1. `libhwui`/Skia 经 OpenGL ES 或 Vulkan loader 调用 Qualcomm UMD；UMD 负责 shader 编译、状态组织，并把绘制或计算命令编码为 Adreno IB。
2. Guest `libgsl.so` 是 UMD 下方的统一设备抽象和内核 ABI 封装层。GL 与 Vulkan 最终都通过它完成 device/context、GPU 内存、IB 提交、timestamp 和同步操作；它本身不执行 shader，也不直接调度 GPU。
3. `libgsl.so` 把操作转换为 `/dev/hgsl` ioctl。Guest `graphics-hgsl` 内核驱动依据操作类型和 context 能力选择传输路径：控制、资源管理及回退提交经 `hgsl_hyp -> HAB -> PVM RGS`；稳态 `ISSUE_IB` 优先写入 per-context DBCQ，并通过 doorbell 通知 GMU。
4. PVM RGS 是物理 GPU 的资源与调度服务端，负责 context/memory 映射、HFI、hang detection 和 recovery；GMU/CP/GPU 执行完成后，通过 timestamp retire、IRQ 和 dma-fence 把完成状态返回 Guest。

因此，GSL 不是一个单独的“渲染器”，而是一组贯穿 UMD、Guest HGSL 和 PVM RGS 的 Qualcomm 图形服务接口。需要特别区分三个对象：

| 名称 | 所在位置 | 主要职责 |
|---|---|---|
| Guest `libgsl.so` | Android 用户态 | 向 UMD 提供统一 GSL API，封装 `/dev/hgsl` ioctl |
| Guest HGSL（`/dev/hgsl`） | Android Guest 内核 | 管理 Guest context/memory/timestamp，选择 HAB 控制路径或 DBCQ 提交快路径 |
| PVM `/usr/bin/kgsl` + `libGSLKernel.so`（RGS） | Linux PVM 用户态 | 管理物理 GPU、GMU/HFI、hang 检测、snapshot 和恢复 |

总览图把高频通道抽象成“Shared Memory + Doorbell”。对本文所分析的 SA8797 构建，更精确的说法是：IB 正文位于 GPU 可寻址内存，Guest HGSL 把包含 context、timestamp、IB GPU 地址和长度的 HFI `ISSUE_CMD` 写入 DBCQ，再更新 write index 并 ring doorbell。它不是把每帧 IB payload 都作为 HAB RPC 发送，也不是把像素数据跨 VM 拷贝到 PVM。

### 3.2 Android Guest 前端

Android 应用并不直接调用 Guest HAB：

```text
Android App / SurfaceFlinger / HWUI
  -> Android EGL/Vulkan loader
  -> Qualcomm UMD
     (vulkan.adreno.so 或 GLES driver)
  -> Guest libgsl.so
  -> /dev/hgsl
  -> Guest graphics-hgsl kernel driver
```

现场 Android 日志加载的是 `/vendor/lib64/hw/vulkan.adreno.so`。该 UMD 依赖 `libgsl.so`，Guest `libgsl` 再通过 `/dev/hgsl` ioctl 创建 context、管理内存、提交 IB 和等待 timestamp。因此架构必须包含 `/dev/hgsl`，不能把用户态 UMD 直接画到 HAB 上。

### 3.3 HAB 控制与回退路径

设备打开、context 创建、内存 export/import、DBCQ query/register，以及 DBCQ 不可用时的 `issueib` 回退会走 HGSL/HAB：

```text
Guest HGSL hgsl_hyp
  -> Guest HAB / MM_GFX
  -> Gunyah virtio-HAB device 94
  -> Host HAB / /dev/vhost-ogles
  -> gsl_hab_server
  -> PVM libgsl.so / libkiumd.so
  -> /usr/bin/kgsl + libGSLKernel.so (RGS)
```

`vhost-user-qti` 的职责是建立 vring、内存表和 kick/call eventfd。完成建链后，稳态 HAB payload 由 virtqueue 与 Host backend 传输，不需要每条消息回到 `vhost-user-qti` 用户态解析。

对应服务参数为：

```ini
ExecStart=/usr/bin/vhost-user-qti \
  -s /tmp/linux-vm2-ogles-skt \
  -d /dev/vhost-ogles \
  -q 2
```

### 3.4 DBCQ 提交快路径

Guest context 注册 DBCQ 后，`hgsl_ioctl_issueib()` 优先调用 `hgsl_db_issueib()`；只有快路径不可用时才调用 `hgsl_hyp_issueib()`。正常快路径是：

```text
Guest UMD / libgsl
  -> /dev/hgsl issueib ioctl
  -> Guest HGSL 构造 HFI ISSUE_CMD
     {context id, timestamp, IB GPU address, IB size}
  -> 写入该 context 的 DBCQ
  -> memory barrier + 更新 write index
  -> GMUGOS/TCSR/local GMU doorbell
  -> GMU 调度 context
  -> Adreno CP/SQE 取出并解析 IB
  -> shader/graphics execution units 执行工作负载
```

代码证据位于 `hgsl.c`：

- `hgsl_ioctl_issueib()`：约 3329～3380 行，优先 DBCQ，随后 HAB fallback；
- `hgsl_db_issueib()`：约 3201～3280 行，整理 IB descriptor；
- DBCQ HFI command：约 1381～1410 行；
- 写 DBCQ 和 ring doorbell：约 583～647 行。

因此，不能把所有 GVM 渲染提交写成线性的 `HAB -> gsl_hab_server -> RGS -> GMU`。这条线只适用于控制/资源操作和回退提交。

### 3.5 DBCQ 与 IPCQ

| 通道 | 两端 | 已证实用途 |
|---|---|---|
| DBCQ | Guest HGSL ↔ GMU | per-context HFI 命令提交快路径 |
| Guest IPCQ | PVM RGS → Guest HGSL | 当前协议枚举和现场只证实 `GSL_IPCQ_SNAPSHOT_DUMP` 请求；dump buffer 经 HAB RPC 返回 |
| PVM local IPC/socket | PVM `libgsl/libkiumd` ↔ 本机 `kgsl/RGS` | 本机 API/控制通信；不能仅凭二进制字符串断言其普通提交协议就是 Guest IPCQ |

这些通道的端点、生命周期和协议不同，不能写成“DBCQ/IPCQ 是同一个跨 VM 提交队列”。现场 `kgsl-1571.log` 也只在 snapshot 阶段出现 `rgs_hyp_ipcq_send_msg`。

### 3.6 GMU、CP/SQE 与执行单元的职责

- GMU firmware 接收 HFI，负责调度、优先级、preemption、context queue、功耗及 fault 上报。
- CP/SQE 从 GPU 地址取 IB，解析命令流并把绘制/计算工作派发给图形和 shader 执行单元。
- shader core、texture、raster、ROP 等执行单元实际执行 shader 和图形工作。

因此“GMU 执行 IB”或“CP 执行 shader”都不准确。`rgs_hfi_bw_perf_vote()` 的方向也应写成 Host/RGS 向 GMU firmware 发送 bandwidth/performance vote；HFI 编号 `H2F_MSG_GX_BW_PERF_VOTE` 已明确它是 Host-to-Firmware 消息，它不是 hang timer 起点。

## 4. 提交完成、timestamp 与 fence

### 4.1 timestamp retire

HGSL timestamp 是每个 context 内的提交序号，不是全局帧号。提交完成路径使共享 `shadow_ts.eop` 前移，GMUGOS/TCSR retire IRQ 再促使 Guest HGSL 检查 retired timestamp 并唤醒 waiter。PVM/RGS 还会处理 HFI `F2H_MSG_TS_RETIRE` 做调度和记账，但它不是 Guest fence 唯一的完成通知路径。

```text
GPU 完成提交
  -> context shadow_ts.eop 前移
  -> retire notification / IRQ
  -> Guest HGSL 检查 timestamp
  -> 唤醒 wait_timestamp
  -> 如该 timestamp 绑定 dma_fence，再 signal timeline/fence
```

以下几个编号属于不同命名空间，不能互相直接替换：

- Vulkan `VkFence`：应用/UMD API 对象；
- Linux `dma_fence` / `sync_file` fd：内核同步对象；
- HGSL context timestamp：context 内提交序号；
- Perfetto 的 `GPU completion fence 4549`：进程内 `FenceMonitor` 的本地递增序号。

`Surface::queueBuffer()` 会把 GPU completion fence 排入静态 `FenceMonitor("GPU completion")`。调用线程短暂打印 `Trace GPU completion fence 4549`；`FenceMonitor` 构造时创建并 detach 的专用线程再按 FIFO 打印 `waiting for GPU completion 4549` 并调用 `waitForever()`。因此长 slice 是监控线程的 fence wait，不是 RenderThread 连续执行或亲自等待了 2.15s；`4549` 也不是 fence fd、HGSL timestamp 或 RGS fault timestamp。

### 4.2 `gsl_rpc_plat_hgsl_wait_timestamp ret(110)`

```text
hgsl wait ts failed: ret(110), ts(1), ctxt(80)
```

其准确含义是：Guest 用户态等待 context 80 的 timestamp 1，在调用者给定的等待期限内没有观察到 retire，返回 `ETIMEDOUT(110)`。

函数名和 tag 中虽然包含 `RPC`，但不能据此认定这次 wait 正在跨 HAB。`hgsl_ioctl_wait_timestamp()` 在 DBCQ + shadow timestamp 可用时会在 Guest 内核本地 wait queue 上等待；只有 remote channel 或缺少 shadow/DBQ 时才回退到 `hgsl_hyp_wait_timestamp()`。

这条日志与 RGS hang 的边界是：

- 它是 Guest wait API 超时，不是 RGS hang detector；
- 它本身不会触发 603、BPMD 或 GPU reset；
- GPU hang、丢失 retire 通知、异常/旧 context 或上层重复短超时轮询都可能产生它；
- 只有时间、Guest PID/context/timestamp 与 PVM fault owner 能对齐时，才能把它作为同一故障的伴随证据。

本次复现中 PVM 20:06/20:08 的 603 owner 是 Launcher `pid 6291 / context 17`；20:09 Android 日志中高频 `ret(110)` 是 `pid 3183 / context 25 / ts 1`。没有额外 context 映射证据时，不能把后者直接写成 Launcher context 17 的同一条 fence。

## 5. PVM KGSL/RGS

### 5.1 进程与库边界

`kgsl@.service` 启动：

```ini
[Unit]
Requires=mm-vfio-device-probe.service compute-resmgr.service
After=mm-vfio-device-probe.service compute-resmgr.service

[Service]
Environment=GSL_LOG=12
Environment=KGSL_ENABLE_SECURE=1
ExecStart=/usr/bin/kgsl -p %i
Type=notify
```

`/usr/bin/kgsl` 通过 `dlopen()` 加载 `libGSLKernel.so` 并解析 `kgsl_init/ kgsl_deinit`。可把职责概括为：

- `/usr/bin/kgsl`：进程外壳、参数、信号、systemd notify 和控制命令入口；
- `libGSLKernel.so`：RGS device/context/memory、HFI、hang detection、snapshot 和 reset；
- `gsl_hab_server`：HAB RPC backend，把 Guest 控制请求转换成 PVM `libgsl` 调用。

RGS 通过 VFIO/SMMU/IRQ 和 compute resource manager 管理物理 GPU 资源，再通过 HFI 与 GMU firmware 交互。

### 5.2 32ms、512ms 与 603

本次启动日志为：

```text
sw hang detection enabled,
timeout short 32ms,
long 512ms,
long job detect enabled 1
```

对当前 `libGSLKernel.so` 的反汇编显示，`RGS_HANG_TIMEOUT_MS` 被读入 HB/long-job 配置。未设置或取 0 时 base 为 32ms；当前版本用 base 和 multiplier 生成打印的 long 值：

```c
base_ms = env_or_default("RGS_HANG_TIMEOUT_MS");
if (base_ms == 0)
    base_ms = 32;

multiplier = base_ms > 512 ? 1 : 512 / base_ms;
effective_long_ms = base_ms * multiplier;
```

这是**当前闭源构建**的实现，不是 HFI 协议保证。比如 base=100 时整数除法会得到 500ms；修改配置后必须看启动日志或运行时回读值，不能假设 long 恒为 512ms。

HFI 协议定义：

```c
/* Fault due to Long IB timeout */
#define GMU_GPU_SW_HANG 603
```

所以本次能证明的是：RGS 在有效 long 参数为 512ms 的实例上收到 Long IB timeout 类型的 603。日志没有 timer arm 时间，因此不能独立测量“从哪一纳秒开始计时”，也不能证明 GPU ALU 在整个 512ms 内持续繁忙。

### 5.3 preemption timeout 是独立机制

short 32ms 不能解释成 `rgs_device_set_preemption_check_short_timeout()`。反汇编显示两者使用不同字段和 HFI value：

- HB/long-job base：默认 32ms，由 `RGS_HANG_TIMEOUT_MS` 和 HB 控制项影响；
- preemption check short timeout：当前构建默认 6ms，setter 接受 2～9999ms，并以独立 HFI value 下发；
- `GMU_GPU_PREEMPT_TIMEOUT(602)`：preemption 在规定时间内未完成；
- `GMU_GPU_SW_HANG(603)`：Long IB timeout。

本次现场没有 602，不能用 32ms preemption path 解释这两次 dump。

### 5.4 当前构建的运行时控制名

二进制中的实际命令字符串是：

```text
gpu_set_HB_timer_enable
gpu_set_HB_timer_timeout
gpu_set_HB_fault_on_timeout
gpu_enable_long_job_reset
gpu_long_job_timeout
gpu_set_preemption_check_short_timeout
gpu_set_preemption_check_short_state
```

`gpu_enable_long_job_detect` 和 `gpu_set_long_job_timeout` 不存在于当前库。`kgsl -c help` 可核对目标版本的语法；闭源库升级后应重新检查，不能只依赖本文字符串。

### 5.5 609 的正确解释

HFI 协议确实定义：

```c
/* GPU encountered a GPC error */
#define GMU_CP_GPC_ERROR 609
```

但本次日志中：

```text
[rgs_hwl_determine_feature_support()][ 609]
```

方括号中的 `609` 是该函数的源码行号，与其他日志末尾的 `[ 644]`、`[ 705]` 相同。只有 payload 明确出现 `error: 609` 才是 HFI GPC error。本次 `kgsl-1571.log` 的实际 fault 只有第 2675、2835 行两条 `error: 603`。

即使将来真实出现 609，它也只表示 GPU 报告 GPC error event，仍不能自动推导为芯片物理损坏；命令流/状态编程错误、固件/驱动问题和硬件问题都需要结合寄存器、BPMD 和可重复性判断。

### 5.6 HFI error 对照

| error | 名称 | 协议语义 | 本次是否出现 |
|---:|---|---|---|
| 601 | `GMU_GPU_HW_HANG` | GPU hang interrupt | 否 |
| 602 | `GMU_GPU_PREEMPT_TIMEOUT` | preemption 未及时完成 | 否 |
| 603 | `GMU_GPU_SW_HANG` | Long IB timeout | 是，两次 |
| 604 | `GMU_CP_OPCODE_ERROR` | CP bad opcode | 否 |
| 606 | `GMU_CP_ILLEGAL_INST_ERROR` | CP illegal instruction | 否 |
| 609 | `GMU_CP_GPC_ERROR` | GPC error event | 否 |

## 6. 2026-07-13 复现时间线

### 6.1 先统一时区和 boot session

`reproduced_again/tmp-kgsl/kgsl-1571.log` 的 fault 时间 `[12:06:18.534]`、`[12:08:52.499]` 使用 UTC；归档 syslog 的本地墙钟分别是 `20:06:18.534`、`20:08:52.500`（Asia/Shanghai）。本文以下统一使用本地时间。

跨分片分析时必须以：

```text
Booting Linux on physical CPU ...
```

作为 cold-boot 硬边界。一个 log 文件可能同时包含前一个 boot session 的尾部和新 session 的开头，不能按文件名直接串联 context 或 PID。

本文时间和计算可直接回查以下证据：

- `reproduced_again/tmp-kgsl/kgsl-1571.log:103`：short 32ms / long 512ms；
- 同文件 `:2675`、`:2746-2760`：第一次 603、BPMD、snapshot complete、recovery；
- 同文件 `:2835`、`:2906-2920`：第二次对应事件；
- `reproduced_again/20-06和20-08日志/linux_log/syslog/003_20250530_024852.log:242904,247760,247773`：第一次本地墙钟；
- `reproduced_again/20-06和20-08日志/linux_log/syslog/004_20260713_200807.log:73064,78864,78881`：第二次本地墙钟；
- `reproduced_again/20-06和20-08日志/log/android/012_20260713_200700.logcat.log.gz:99694` 与 `015_20260713_200929.logcat.log.gz:21933`：两条完整 Davey 字段；
- `20260713_192509_trace_0.perfetto` 的 `slice[1908791]`、`slice[1910289]`：4549 GPU completion wait 与 4550 HWC release wait。
- `1925-360/new/linux_log/syslog/030_20250530_024852.log:295758,298567`：1925 数据集的 603 与 2053ms recovery。

### 6.2 第一次 Launcher 603

| 本地时间 | 事件 | 证据与含义 |
|---|---|---|
| 20:06:18.534 | `error:603` | context 17、pid 6291、`GVM_ockpit.launcher`、fault ts `0x3b4b` |
| 20:06:18.535～.538 | 打开 API log、mem table、GMU debug log | fault 后开始收集状态 |
| 20:06:18.567 | 发送 Guest snapshot IPCQ 请求并设置 `snapshot reg_type=0xEFF` | Guest dump 与寄存器 snapshot 开始并入本次 capture |
| 20:06:19.074 | `Crash Dumper is Enabled` | crash dumper 子阶段开始，不是整个 dump 起点 |
| 20:06:20.570 | 创建 BPMD | fault 后 2.036s |
| 20:06:20.588 | `Snapshot capture COMPLETED` | fault 后 2.054s |
| 20:06:20.591 | `Hang recovered in 2054 ms` | SW reset/recovery 完成；日志内部打印 2054ms |

关键原始日志：

```text
bad_ctxt_idx: 17, ft_policy: 0x2, fault ts: 0x3b4b,
pid: 6291, name: GVM_ockpit.launcher, error: 603

file '/tmp/gpu0_statedump0_GVM_ockpit.launcher_6291_c17_t15179.bpmd'
created for snapshot

Snapshot capture COMPLETED, flush successful
Reset mode[SW] - Hang recovered in 2054 ms
```

### 6.3 第二次 Launcher 603

| 本地时间 | 事件 | 相对 fault（按 RGS raw clock） |
|---|---|---:|
| 20:08:52.500（raw 12:08:52.499） | context 17 再次 `error:603`，fault ts `0x8683` | 0 |
| 20:08:53.156 | `Crash Dumper is Enabled` | +0.657s |
| 20:08:54.837 | 创建第二个 BPMD | +2.338s |
| 20:08:54.856 | snapshot 完成 | +2.357s |
| 20:08:54.857 | `Hang recovered in 2359 ms` | 约 +2.359s |

syslog 包装时间把首行显示为 `.500`，RGS 原始日志为 `.499`，所以上表相对值统一按原始 RGS 时间计算。两次都命中 Launcher 的 context 17，说明故障对同一进程/context 可重复；它仍不足以确定 context 17 内究竟是哪一条 draw、dispatch、shader 或同步依赖导致不 retire。

### 6.4 512ms、约 2 秒与 GPU 执行时间

必须分开四个时间：

```text
Long IB 配置阈值          512ms（fault 发生前）
fault -> BPMD created     2.036s / 2.338s
fault -> capture complete 2.054s / 2.357s
完整 recovery log         2054ms / 2359ms
```

Davey 字段中第一次 `CommandSubmissionCompleted -> GpuCompleted` 为 2.144134426s，第二次为 2.452431041s。这段包含 hang detection、snapshot/reset 和 fence wait 最终返回，不能当作 GPU 连续渲染时间。

```text
第一次：116563203391 - 114419068965 = 2144134426ns
第二次：270831509582 - 268379078541 = 2452431041ns
```

另一份 `20260713_192509_trace_0.perfetto` 中：

- 专用 `GPU completion` FenceMonitor 线程上的 `waiting for GPU completion 4549` 为 2.150692291s；
- `waiting for HWC release 4550` 为 2.124022030s；
- 对应 RGS 内部打印的 recovery duration 为 2.053s，syslog 墙钟差约 2.054s。

即使假设跨 VM 时间完全对齐且 recovery 区间全部包含在 GPU completion wait 内，用 RGS 内部值相减是 `2.150692 - 2.053 ≈ 97.692ms`，用 syslog 墙钟相减约 96.692ms。这个约 96.7～97.7ms 只是在强假设下对“fault 检测前后、排队和 fence wait 解除/返回等 recovery 之外区间总量”的宽松上界，**不是 GPU 实际运行时间**。timer arm 之前已经执行了多久、期间是否一直 active，现有 trace/log 都没有直接给出。

### 6.5 Perfetto slice 的正确读法

- `DrawFrames 189427` 的 14.342ms 是 RenderThread 上 trace slice 的墙钟跨度，其中 Sleeping 约 12.831ms、Running 约 1.447ms；它既不是 CPU 连续运行时间，也不是 GPU 执行时间。
- `DrawFrames 189534` 的 2.182s 中 99.90% 为 Sleeping，表示线程大部分时间在等待；它不是 CPU 连续运行 2.182s。
- 本例两个 `DrawFrames 189427` 都在同一 RenderThread（tid 5104）、同一 depth，分别对应 `VRI[LauncherVCOS]#1` frame 4201 和 `VRI[]#7` frame 10。重复名称来自同一 vsync id 下的不同 surface，必须用 start time、SQL ID 和 frame track 区分。
- `Trace GPU completion fence` 是调用线程把 fence 排入监控队列的短 trace；`waiting for GPU completion` 是专用 FenceMonitor 线程对 GPU completion fence 的等待。GPU command 已提交不等于 GPU 已执行完成。
- `waiting for HWC release` 是另一个 monitor 对下游 buffer release fence 的等待；本例 4550 属于下一帧 `DrawFrames 189484`，不能与 4549 当作同一个 GPU 任务。
- 本次 20:06/20:08 的 Perfetto 分片在 stall 中间存在 gap，完整的 2.1s/2.45s 数值来自 Davey 字段，不能写成 Perfetto 直接完整覆盖并测得。

## 7. 能证明和不能证明的 Launcher 根因

### 7.1 已证明

- PVM RGS 两次收到 context 17、pid 6291、Launcher 的 `error:603`；
- 该 RGS 实例启动配置是 short 32ms、long 512ms、long-job detect enabled；
- Android Davey 的 `GpuCompleted/FrameCompleted` 与 FenceMonitor 的完成报告都延迟到 PVM recovery 时间窗附近；跨 VM 对齐证明的是强时间相关性，不是共享 fence id；
- snapshot 成功生成，随后以 SW reset 恢复；
- aggregate GPU utilization 不高并不否定单 context/单 engine 无进展。利用率是时间窗口平均值，hang 检测关注的是特定提交是否 retire。

### 7.2 尚未证明

- **动态背景模糊是根因**：模糊会增加 offscreen pass、采样和带宽，可能放大负载，但当前日志没有把 fault IB 反解到 blur pass。
- **1925 trace 已把 4549 归因到 blur**：4549 位于第二个 `DrawFrames 189427`（`VRI[]#7` / CellItem）内，而 LiquidGlass/blur 痕迹位于前一个 LauncherVCOS surface；相邻发生不构成 fault IB 与 blur pass 的映射。
- **Launcher 过度绘制或布局不合理**：frame CPU slice 和全局利用率不能证明 overdraw，需要帧捕获、draw/pass 数量和像素覆盖计数。
- **系统不支持某条 Vulkan 指令**：SPIR-V 通常先由 UMD 编译。HFI 604/606 针对 CP/SQE 命令流或微码层的 bad opcode/illegal instruction，不是 SPIR-V 或 shader ISA 的校验器；本次未出现 604/606 不能排除 shader compiler/ISA 问题。compiler/driver 缺陷仍可能最终表现为 timeout，必须通过 shader/IB/BPMD 解码确认，603 本身没有“unsupported instruction”语义。
- **GPU 持续绘制了 512ms 或 2秒**：603 表示未在 long window 内 retire；fault 后约 2秒主要是 snapshot/recovery，活跃执行区间未知。
- **GPU 硬件损坏**：现场没有真实 609，也没有仅凭 603 可以支持的硬件损坏证据。

### 7.3 要把根因推进到具体 draw/shader，需要补什么

1. 用 Qualcomm 内部 BPMD/IB 解码器解析 `gpu0_statedump*.bpmd`，定位 context 17 的 fault IB、CP opcode、shader/dispatch 和寄存器状态。
2. 在 Launcher debug 构建中给 render pass、blur pass、draw/dispatch 和提交批次加唯一 marker，并记录 context timestamp。
3. 采集每个提交的 GPU timestamp query，而不是用 RenderThread CPU slice 或 fence 总等待时间代替 GPU duration。
4. 量化 draw/dispatch 数、render pass 数、IB dword、primitive 数、目标像素数、overdraw 层数、blur radius/sample 数、shader static/dynamic instruction 数和显存带宽。
5. 做单变量 A/B：禁用 blur、降低分辨率、减少 layer/pass/sample、替换 shader，并比较 603 的复现概率和 fault IB。

只有“marker/timestamp -> fault IB -> shader/pass”三者闭环后，才能把根因写成 Launcher 的某个具体操作。

## 8. Fault、Guest state dump 与恢复

从现场可以直接观察到的流程是：

1. RGS 收到 HFI context-bad `error:603`；
2. 打开 API log、memory table 和 GMU debug log，开始硬件 snapshot；
3. RGS 通过 IPCQ 请求 Guest snapshot；
4. Guest `hgsl_gmugos.c` 处理 `GSL_IPCQ_SNAPSHOT_DUMP`，整理 Guest IB/state；
5. Guest 通过 HAB `RPC_GVM_STATE_DUMP` 把数据交给 PVM；
6. RGS `rgs_snapshot_flush()` 创建 BPMD；
7. snapshot 完成并触发 QLF `gpu0_fault`；QLF callback 异步执行，可能与后续恢复重叠；
8. RGS 执行 SW reset/CP 恢复并打印 recovery duration。

这比笼统写成“Guest 直接生成 `/tmp` BPMD”更准确：Guest 只提供合并进 snapshot 的数据，最终文件由 PVM `libGSLKernel.so` 写出。闭源实现没有公开完整步骤时，也不应把 Android 开源驱动的 guilty-context 隔离/重放顺序当作本次 RGS 已证实行为。

## 9. BPMD 与 QLF 归档

RGS 格式字符串为：

```text
%sgpu%d_statedump%u_%s.bpmd
```

现场文件：

```text
/tmp/gpu0_statedump0_GVM_ockpit.launcher_6291_c17_t15179.bpmd
```

可确定的字段是 GPU index、来源标签、pid、context 17 和十进制 timestamp 15179（`0x3b4b`）。`statedump0` 是 dump 序号，但日志不足以证明它在进程、GPU 还是某次服务生命周期中的精确作用域。

snapshot 本身成功，失败的是后续归档：

```text
rename('/tmp/gpu0_statedump...',
       '/var/log/qlf_dumps/qlf_gpu0/gpu0_statedump...')
FAILED, errno=18 'Invalid cross-device link'
```

`rename()` 不能跨文件系统，因此文件保留在 `/tmp`。修复应使用同一文件系统，或把移动改成 copy + fsync + atomic publish + unlink；不能把 `EXDEV` 解释成 GPU snapshot 失败。

## 10. 配置、检查与复现量化

### 10.1 配置验证

如需实验性修改当前构建的 base timeout，可通过 systemd drop-in 注入：

```ini
[Service]
Environment=RGS_HANG_TIMEOUT_MS=64
```

重启会破坏所有 GPU context，应安排在测试窗口。必须以 RGS 启动日志验证实际 short/long 值；`systemctl show` 只能证明变量传入，不能证明闭源库最终采用了什么值。

`RGS_HANGCHECK_DISABLE` 会关闭软件 hang detection，不建议在量产环境使用，否则可能把可恢复故障扩大为长时间系统卡顿。

### 10.2 fault 检查

```bash
rg "sw hang detection enabled|rgs_cmdstream_hfi_hang_recovery|error:" kgsl-*.log
rg "Snapshot capture COMPLETED|Hang recovered|statedump|Invalid cross-device" kgsl-*.log
```

读取日志时按字段而不是裸数字判断：

- `error: 603` 是实际 HFI error；
- 函数名后的 `[ 603]` 或 `[ 609]` 是源码行号；
- `fault ts` 是 context timestamp；
- `Hang recovered in ... ms` 是 fault 后恢复耗时，不是 Long IB threshold。

### 10.3 可控复现程序的量化变量

若要写程序复现 603，不应只追求“GPU 总利用率高”，而应构造单个不可抢占或长期不 retire 的提交，并记录：

```text
提交级 GPU timestamp duration
IB 数量与 dword 数
draw / dispatch / primitive 数
render target 尺寸与 overdraw 层数
blur radius、sample 数、pass 数
shader 静态指令与循环次数
显存读写字节和 cache miss
context priority 与依赖 fence
```

逐级增加一个变量，直到单次提交越过当前 effective long threshold；同时保留 marker、timestamp 和 BPMD。仅在 fragment shader 中增加循环可能被编译器优化，实际测试应使用运行时输入和可观测输出，并用 GPU timestamp query 校验执行时间。

## 11. 总结

SA8797 的 GVM 图形路径不是“所有帧都经 HAB 和 PVM 用户态”的单链模型。HAB/RGS 完成设备、context、内存和 DBCQ 建立后，稳态 IB 可以从 Guest HGSL 直接写 context DBCQ、ring GMU doorbell，再由 GMU 调度、CP/SQE 解释、GPU 执行单元运行；完成通过 context timestamp retire 和 fence 链返回 Guest。

2026-07-13 现场能确认的是 Launcher context 17 两次触发 603 Long IB timeout，当前 long 配置为 512ms，随后 PVM 用约 2.1～2.4s 完成 snapshot/reset。现场没有真实 609；`gsl_rpc_plat_hgsl_wait_timestamp ret(110)` 也是独立的 Guest wait 超时，不能不做 context 映射就与 Launcher fault 等同。

当前证据把问题定位到了 Launcher 的 GPU 提交/context，但还没有定位到动态模糊、某个 Vulkan command 或某个 shader。最终根因必须依靠 fault IB/BPMD 解码、提交 marker 和 GPU timestamp 三类证据闭环。
