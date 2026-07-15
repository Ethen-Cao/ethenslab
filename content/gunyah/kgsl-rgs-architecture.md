+++
date = '2026-07-15T10:00:00+08:00'
draft = false
title = 'Qualcomm PVM KGSL/RGS 架构、GPU Hang 检测与 BPMD 落盘'
tags = ["Qualcomm", "Adreno", "KGSL", "RGS", "GPU", "Gunyah", "HAB", "Debug"]
+++

## 1. 概述

本文基于 SA8797 Gen5 工程中的 Yocto 配方、systemd 服务、HAB/vhost 源码、Android 开源 graphics-kernel 头文件，以及 PVM Adreno 预编译库的符号和反汇编结果，梳理 **PVM Linux 中的 KGSL/RGS 图形后端**。

这里最容易产生误解的是“KGSL”这个名称在不同运行环境中指代不同对象：

- Android 非虚拟化驱动中，KGSL 通常指 `msm_kgsl` 内核驱动。
- 本平台 PVM Linux 中，`kgsl@0.service` 启动的是用户态进程 `/usr/bin/kgsl -p 0`。它动态加载 `libGSLKernel.so`，库内部实现 RGS（Remote Graphics Service）设备管理、GMU/HFI、调度、hang recovery 和 snapshot。
- GVM 的图形调用由 `gsl_hab_server` 经 HAB 转入 PVM，再通过 PVM 的 `libgsl.so` 与 RGS 通信。

因此，本文中的 **KGSL/RGS** 默认指第二种：PVM 中的 `kgsl` 守护进程及其加载的 `libGSLKernel.so`，而不是 Android Guest 内核中的 `msm_kgsl.ko`。

### 1.1 核心结论

1. `/usr/bin/kgsl` 是启动壳和 systemd notify 入口，真正的 GPU 后端实现位于闭源 `libGSLKernel.so`。
2. GVM 图形 RPC 经过 `MM_GFX` HAB 通道；virtio-HAB 为 graphics 分配的 device-id 是 `94`。
3. RGS 通过 VFIO、SMMU、IRQ 和 HFI 管理物理 Adreno GPU/GMU。
4. `GMU_GPU_SW_HANG(603)` 表示 **Long IB timeout**；它不天然等于 512ms。512ms 来自本次 RGS 启动时的运行配置。
5. `GMU_CP_GPC_ERROR(609)` 是 GPC 硬件错误，不是 32ms 或 512ms 定时器超时。
6. BPMD 文件由 PVM 的 `libGSLKernel.so:rgs_snapshot_flush()` 创建在 `/tmp`，随后 RGS 触发 QLF `gpuN_fault` 事件尝试归档。

## 2. 源码与二进制基线

| 组件 | 工程路径 | 证据用途 |
|---|---|---|
| Adreno Yocto 配方 | `linux/apps/apps_proc/layers/meta-qti-automotive-prop/recipes-graphics/adreno/adreno_0.1.bb` | 安装包、systemd 实例、依赖关系 |
| RGS 安装逻辑 | `linux/apps/apps_proc/layers/meta-qti-automotive-prop/recipes-graphics/adreno/adreno.bb` | 安装 `kgsl` 和 `libGSLKernel.so` |
| KGSL systemd 服务 | `linux/apps/apps_proc/prebuilt_HY11/sa8797/adreno/usr/lib/systemd/system/kgsl@.service` | `/usr/bin/kgsl -p %i`、VFIO/compute-resmgr 依赖 |
| GVM 图形后端服务 | `linux/apps/apps_proc/prebuilt_HY11/sa8797/adreno/usr/lib/systemd/system/gsl_hab_server.service` | `gsl_hab_server` 在 KGSL 与 vhost-user-gpu 后启动 |
| vhost-user GPU 服务 | `linux/apps/apps_proc/vendor/qcom/opensource/vhost-user/vhost-user-gpu.service` | `/tmp/linux-vm2-ogles-skt`、`/dev/vhost-ogles`、2 个队列 |
| HAB virtio 映射 | `vendor/kernel_platform/soc-repo/drivers/soc/qcom/hab/hab_virtio.c` | `MM_GFX -> HAB_VIRTIO_DEVICE_ID_GRAPHICS(94)` |
| HAB vhost backend | `vendor/kernel_platform/soc-repo/drivers/soc/qcom/hab/hab_vhost.c` | `MM_GFX` 对应 `ogles` vhost 设备 |
| HFI 错误码 | `vendor/vendor/qcom/opensource/graphics-kernel/adreno_hfi.h` | 602/603/609 的协议语义 |
| Gen7 HFI 处理参考 | `vendor/vendor/qcom/opensource/graphics-kernel/adreno_gen7_hwsched_hfi.c` | context-bad 错误解析与 bail-out timer 开关 |
| Android KGSL 恢复参考 | `vendor/vendor/qcom/opensource/graphics-kernel/adreno_hwsched.c` | snapshot、guilty context、reset 的开源参考流程 |
| PVM RGS 实现 | `prebuilt_HY11/sa8797/adreno/usr/lib/libGSLKernel.so` | RGS 真实执行路径，闭源；通过符号、字符串和反汇编分析 |
| PVM GSL RPC backend | `prebuilt_HY11/sa8797/adreno/usr/bin/gsl_hab_server` | HAB RPC、共享内存导入、GVM snapshot 请求 |

需要强调：`adreno_hfi.h` 和 Android graphics-kernel 提供了 HFI 协议语义及一套开源参考实现，但 PVM 运行时实际执行的是 `libGSLKernel.so`。本文不会把 Android 内核中的 2000ms dispatcher timeout 当作 PVM RGS 的 hang timeout。

## 3. 整体架构

下图采用与“vhost-user 与 HAB 的分层关系”相同的布局思路，将 Android Guest、Gunyah、Linux PVM 和 GPU/GMU 硬件分区展示，并区分：

- 蓝色虚线：vhost-user 建链控制面；
- 绿色实线：GVM 图形命令与共享队列数据面；
- 橙色实线：GPU fault、snapshot 与 QLF 落盘链路。

若图未显示，可直接打开 [KGSL/RGS 架构图](/ethenslab/diagrams/kgsl-rgs-architecture.html)。

<iframe src="/ethenslab/diagrams/kgsl-rgs-architecture.html"
        style="width:100%;height:1420px;border:1px solid #30363d;border-radius:12px"
        loading="lazy" title="Qualcomm PVM KGSL/RGS architecture"></iframe>

### 3.1 各层角色

| 层次 | 组件 | 角色 |
|---|---|---|
| Android Guest | Adreno UMD / Guest `libgsl` | 创建 context、分配/导入内存、提交 IB、等待 timestamp |
| Android Guest | Guest HAB frontend | 在 `MM_GFX` 上发送 RPC、导出共享内存、触发 doorbell |
| Gunyah | virtio-HAB device 94 | 跨 VM 传递 vring、共享内存和 virq/doorbell |
| PVM 控制面 | `qcrosvm` + `vhost-user-qti` | 建立 vhost vring、内存表和 eventfd；不解析 GSL RPC 语义 |
| PVM HAB backend | `/dev/vhost-ogles` + Host HAB | 承接 `MM_GFX` virtio-HAB 数据通道 |
| PVM 用户态 backend | `gsl_hab_server` | 将 GVM GSL 请求转换为 PVM `libgsl.so` 调用 |
| PVM 图形核心 | `/usr/bin/kgsl` + `libGSLKernel.so` | RGS 设备初始化、context/内存、HFI 调度、hang 检测、snapshot、reset |
| 硬件/固件 | GMU firmware + Adreno GPU | 执行 HFI 调度和 IB；上报 context-bad、硬件 fault 与性能事件 |

### 3.2 vhost-user 控制面与图形数据面

`vhost-user-gpu.service` 启动：

```ini
ExecStart=/usr/bin/vhost-user-qti \
  -s /tmp/linux-vm2-ogles-skt \
  -d /dev/vhost-ogles \
  -q 2
```

它负责把 VMM 侧的共享内存、vring 和 kick/call eventfd 配置下沉给 `/dev/vhost-ogles`。配置完成后，GVM 的稳态 HAB payload 由 virtqueue 与 Host 内核 backend 处理，不需要每条图形命令都绕回 `vhost-user-qti` 用户态。

HAB 源码中的映射为：

```c
#define HAB_VIRTIO_DEVICE_ID_GRAPHICS 94

{ MM_GFX, HAB_VIRTIO_DEVICE_ID_GRAPHICS, NULL },
```

Host `hab_vhost.c` 又把 `MM_GFX` 区域命名为 `ogles`，与 `/dev/vhost-ogles` 对应。

## 4. PVM KGSL/RGS 的启动与组成

### 4.1 systemd 实例

Gen5 配方声明两个实例：

```bitbake
KGSL_SERVICE:gen5 = "kgsl@.service"
KGSL_CONFIGS_PREF:gen5 = "kgsl@0 kgsl@1"
```

模板服务的关键内容是：

```ini
[Unit]
Requires=mm-vfio-device-probe.service compute-resmgr.service
After=mm-vfio-device-probe.service compute-resmgr.service

[Service]
Environment=GSL_LOG=12
Environment=KGSL_ENABLE_SECURE=1
ExecStartPre=-/sbin/modprobe iommu_faults
ExecStartPre=-/sbin/modprobe qcom_ksync
ExecStart=/usr/bin/kgsl -p %i
Type=notify
```

`-p %i` 选择 GPU index，因此 `kgsl@0.service` 对应 GPU0，`kgsl@1.service` 对应 GPU1。

### 4.2 `kgsl` 与 `libGSLKernel.so` 的职责边界

`/usr/bin/kgsl` 没有在 ELF `DT_NEEDED` 中直接链接 `libGSLKernel.so`。二进制包含 `dlopen()`、`dlsym()` 以及以下字符串：

```text
libGSLKernel.so
kgsl_init
kgsl_deinit
ldd_send_control_command
```

所以它的工作方式是运行时加载 RGS 库并解析入口函数。RGS 库导出的关键符号包括：

```text
kgsl_init / kgsl_deinit
rgs_device_attach / start / stop / reset
rgs_context_create / destroy
rgs_cmdstream_issueib / waittimestamp
rgs_device_set_preemption_check_short_timeout
rgs_device_recovery_start / stop
rgs_device_dumpstate
rgs_snapshot_capture / rgs_snapshot_flush
```

可以把两者理解为：

- `kgsl`：进程外壳、参数解析、信号处理、systemd READY 通知、控制命令入口；
- `libGSLKernel.so`：RGS 图形内核的实际实现。

### 4.3 `gsl_hab_server` 与本机 RGS IPC

`gsl_hab_server` 同时依赖：

```text
libuhab.so
libgsl.so
```

其导入符号包含 `habmm_socket_open/send/recv`、`habmm_export/import` 以及完整的 `gsl_context_*`、`gsl_memory_*`、`gsl_command_issueib*` 接口。它承担 GVM GSL RPC backend 的角色。

PVM `libgsl.so` 再通过 `libkiumd.so` 和本机 IPC 与 `kgsl`/RGS 交互。库中可见 `/tmp/kgsl-unix-domain-socket`、`ioctl_kgsl_*`、IPCQ 和 RGS 状态转换字符串。高频提交还支持 DBCQ/IPCQ 共享队列与 doorbell，从而避免所有 IB 提交都走重型同步 RPC。

## 5. 正常渲染提交路径

以一次 GVM IB 提交为例，路径可概括为：

```text
GVM App / Adreno UMD
  -> Guest libgsl
  -> HAB frontend (MM_GFX)
  -> Gunyah virtio-HAB device 94
  -> Host HAB backend (/dev/vhost-ogles)
  -> gsl_hab_server
  -> PVM libgsl.so / libkiumd.so
  -> kgsl process / libGSLKernel.so (RGS)
  -> HFI queue
  -> GMU firmware
  -> Adreno CP executes IB
```

控制面请求（device open、context create、内存导入等）适合 HAB RPC。context 建立后，双方可以注册 DBCQ/IPCQ 共享队列：GVM/后端写入队列，doorbell 通知 RGS/GMU，timestamp retire 再完成同步对象或 fence。

RGS 中与这条路径对应的符号和日志标签包括：

- `rgs_context_create_hfi()`：创建 context queue、分配 context id、注册 doorbell queue；
- `rgs_cmdstream_hfi_issueib()`：通过 HFI dispatch 模式提交 IB；
- `rgs_cmdstream_hfi_ts_retire()`：处理 timestamp retire；
- `rgs_hfi_bw_perf_vote()`：处理 GMU 返回的性能/带宽 vote，它不是 hang timer 的起点。

## 6. GPU Hang 检测机制

### 6.1 检测位置

PVM RGS 启动时会执行 `rgs_hfi_setup_hang_detection`，把 hang 检测配置交给 GMU/HFI 调度体系。GMU firmware 监控 context、ringbuffer、preemption 和长 IB 执行状态；检测到异常后，通过 HFI context-bad 消息返回 fault context、timestamp 和 error code。RGS 的 GMU bottom-half 处理消息，再调度 `rgs_cmdstream_hfi_hang_recovery()`。

启动日志会明确打印当前有效配置：

```text
sw hang detection enabled,
timeout short 32ms,
long 512ms,
long job detect enabled 1
```

这里的 32ms 与 512ms 是两级运行时配置，不是从 603 这个数字推导出来的。

### 6.2 short timeout：preemption check

RGS 控制接口把 short timeout 描述为：

```text
Set short timeout value in ms of context switch to highest priority level
```

因此 short timeout 主要用于检查向更高优先级 context 切换时，preemption/context switch 是否在预期时间内完成。HFI 协议中相邻的错误类型为：

```c
/* Preemption didn't complete in given time */
#define GMU_GPU_PREEMPT_TIMEOUT 602
```

short timeout 与 602 在机制上对应，但判断某次现场是否走了 short path，仍应以收到的 HFI error code 和 fault payload 为准。

### 6.3 long timeout：Long IB / bail-out timer

HFI 定义明确写明：

```c
/* Fault due to Long IB timeout */
#define GMU_GPU_SW_HANG 603
```

开源 Gen7 驱动通过 `HFI_FEATURE_BAIL_OUT_TIMER` 打开 long IB 检测：

```c
gen7_hfi_send_feature_ctrl(adreno_dev,
    HFI_FEATURE_BAIL_OUT_TIMER, 1, 0);
```

这里仅启用 feature，没有在 `adreno_hfi.h` 中规定 512ms。PVM RGS 的具体 long timeout 来自它自己的运行时配置；本次启动日志显示为 512ms。因此：

> 本次 error 603 对应配置为 512ms 的 Long IB timeout 路径；603 本身不等价于固定 512ms。

### 6.4 `RGS_HANG_TIMEOUT_MS` 确实会被使用

对当前 `libGSLKernel.so` 的 AArch64 反汇编可确认以下调用链：

```text
加载 "RGS_HANG_TIMEOUT_MS"
  -> getenv()
  -> strtol(value, NULL, 10)
  -> 保存为 short timeout
  -> 参与 long timeout 计算
  -> 打印 sw hang detection enabled ...
```

该变量不是一个固定值，而是单位为毫秒的进程环境变量。当前 `kgsl@.service` 没有设置它，所以现场使用初始化默认值 32ms。

对当前构建，反汇编得到的初始化计算可写成下面的等价伪代码：

```c
short_ms = getenv("RGS_HANG_TIMEOUT_MS")
    ? strtol(value, NULL, 10)
    : initialized_default;

if (short_ms == 0)
    short_ms = 32;

if (short_ms > 512)
    long_multiplier = 1;
else
    long_multiplier = 512 / short_ms;

long_ms = short_ms * long_multiplier;
long_job_detect = 1;
```

例如 short 设置为 64ms 时，long 仍为 512ms；设置为 100ms 时，整数除法会使 long 变为 500ms。为了保持 long=512ms，宜选择 512 的因数，如 32、64、128、256。

运行时 setter `rgs_device_set_preemption_check_short_timeout()` 接受的范围是 `1 < value < 10000`，即 2～9999ms。修改后必须以启动日志或控制接口回读结果为准。

### 6.5 609 不是 timeout

HFI 对 609 的定义是：

```c
/* GPU encountered a GPC error */
#define GMU_CP_GPC_ERROR 609
```

开源处理函数把它打印为 `RBBM: GPC error`。这是 GPU 图形处理核心/CP 上报的硬件 fault 类事件，不对应 short 32ms 或 long 512ms 定时器。它也会进入 snapshot 和 reset 流程，所以“产生相同 BPMD”不代表“触发原因相同”。

### 6.6 常见错误码对照

| HFI error | 名称 | 触发语义 | 与本次配置的关系 |
|---:|---|---|---|
| 601 | `GMU_GPU_HW_HANG` | GPU hang interrupt | 硬件 hang 类事件 |
| 602 | `GMU_GPU_PREEMPT_TIMEOUT` | preemption 未及时完成 | 与 short/preemption check 机制相关 |
| 603 | `GMU_GPU_SW_HANG` | Long IB timeout | 本次 long 配置为 512ms |
| 609 | `GMU_CP_GPC_ERROR` | GPC error | 非 32/512ms timeout |

## 7. Fault、Snapshot 与恢复流程

### 7.1 HFI fault 到 hang recovery

现场日志中的入口形态为：

```text
rgs_cmdstream_hfi_hang_recovery():
bad_ctxt_idx: 17,
ft_policy: 0x2,
fault ts: 0x3b4b,
pid: 6291,
name: GVM_ockpit.launcher,
error: 603
```

RGS 得到 bad context 后，大致执行：

1. 冻结或隔离 fault context，记录 pid、context id 和 timestamp；
2. 导出 KGSL API log、内存表和 GMU debug log；
3. 调用 `rgs_snapshot_capture()` 收集 GPU/GMU/RGS 状态；
4. 请求 GVM backend 提供 guest state dump；
5. `rgs_snapshot_flush()` 写出 BPMD；
6. 触发 QLF `gpuN_fault` postmortem；
7. 重新加载 CP microcode、恢复 context/ringbuffer 状态或执行 reset；
8. 输出总恢复耗时。

### 7.2 GVM snapshot 如何并入 PVM BPMD

RGS 库中存在：

```text
GVM dump data is not ready yet
Failed to get valid gvm state dump
RGS_WAIT_GVM_SNAPSHOT_CONDVAR
```

`gsl_hab_server` 同时导入 `gsl_gvm_state_dump()`，并包含：

```text
FAILED dump gvm state
FAILED to dump gvm snapshot into rgs!
```

这表明最终 BPMD 的文件写入者是 PVM RGS，但 snapshot 可以通过 GSL/HAB backend 请求并合并 GVM 侧状态。不能因为文件名带 `GVM_...` 就认为它是 Android Guest 直接写入 `/tmp`。

### 7.3 BPMD 文件命名

RGS 内部格式字符串为：

```text
%sgpu%d_statedump%u_%s.bpmd
```

现场文件：

```text
/tmp/gpu0_statedump0_GVM_ockpit.launcher_6291_c17_t15179.bpmd
```

可以拆解为：

| 字段 | 含义 |
|---|---|
| `/tmp/` | 首选输出目录/前缀 |
| `gpu0` | GPU index |
| `statedump0` | 本进程内 snapshot 序号 |
| `GVM_ockpit.launcher` | fault 来源 VM/进程标签 |
| `6291` | fault 进程 pid |
| `c17` | context id 17 |
| `t15179` | fault timestamp；`0x3b4b = 15179` |
| `.bpmd` | Qualcomm GPU postmortem dump 格式 |

### 7.4 QLF 归档与 EXDEV 失败

RGS 直接依赖 `libqlf-client.so` 并调用 `QLF_TriggerPostMortem()`。GPU0 fault 对应 `gpu0_fault`，QLF 回调目标目录为：

```text
/var/log/qlf_dumps/qlf_gpu0/
```

`ana_filemgr.cfg` 也把 `gpu0_smmu_fault,gpu0_oom,gpu0_fault` 的 source 配置为 `qlf_gpu0`，最终事件目录位于 `/var/log/qlf_dumps/${event}`。

本次日志显示 RGS 使用 `rename()` 从 `/tmp` 移动到 `/var/log/qlf_dumps/qlf_gpu0` 时失败：

```text
rename('/tmp/gpu0_statedump...',
       '/var/log/qlf_dumps/qlf_gpu0/gpu0_statedump...')
FAILED, errno=18 'Invalid cross-device link'
```

`rename()` 不能跨文件系统移动文件，因此 BPMD 保留在 `/tmp`。这不是 snapshot 生成失败：同一现场已经打印 `Snapshot capture COMPLETED, flush successful`。若要修复归档，应让源/目标位于同一文件系统，或把移动实现改成 copy + fsync + unlink。

## 8. 现场时间线与“32ms 还是 512ms”

第一处 error 603 的关键时间线如下：

| 时间 | 事件 |
|---|---|
| 12:06:18.534 | RGS 收到/处理 HFI error 603，fault context 17 |
| 12:06:19.074 | 开始 crash dumper snapshot 阶段 |
| 12:06:20.570 | `rgs_snapshot_flush()` 创建 BPMD |
| 12:06:20.588 | snapshot 完成并触发 QLF |
| 12:06:20.589 | SW reset 恢复完成，总耗时 2054ms |

第二处 error 603 的恢复耗时为 2359ms。

必须区分三个时间概念：

```text
hang 判定阈值       = 本次 Long IB 配置 512ms
收到 fault 到写出文件 = 约 2.0～2.4s 中的一部分
完整 recovery duration = 2054ms / 2359ms
```

日志中的 fault 行是“阈值已经满足后的上报点”，没有打印 Long IB timer 的精确起始时刻。因此不能用 fault 行与 BPMD 创建行相减来反推 512ms，也不能把约 2 秒的 snapshot/recovery 时间当成 hang 检测阈值。

本次判断结论是：

- error 603 证明走的是 Long IB timeout 类型；
- 启动日志证明该实例的 long timeout 配置为 512ms；
- 因而本次 dump 属于 512ms 配置的 long path，而不是 32ms short path；
- 现有日志缺少 timer arm 时间，不能仅靠墙上时间独立测得“恰好经过 512ms”。

## 9. 配置与验证

### 9.1 启动环境变量方式

可以通过 systemd drop-in 把变量传入 `kgsl@N.service`。drop-in 文件不是系统预置文件，需要创建：

```bash
systemctl edit kgsl@.service
```

填入：

```ini
[Service]
Environment=RGS_HANG_TIMEOUT_MS=64
```

systemd 通常会保存为：

```text
/etc/systemd/system/kgsl@.service.d/override.conf
```

然后执行 `systemctl daemon-reload` 并重启目标实例或整机。GPU 服务重启会影响显示和所有 GVM GPU context，量产环境优先选择整机重启窗口。

验证不能只看 `systemctl show`，还必须检查 RGS 启动日志：

```text
sw hang detection enabled, timeout short 64ms, long 512ms, ...
```

### 9.2 镜像固化方式

不要直接修改 Yocto `tmp-glibc/work` 下的 service，它会被重新构建覆盖。应通过产品 layer 的 `.bbappend` 修改 `${D}${systemd_unitdir}/system/kgsl@.service`，或在 Adreno 源包提供的 service 模板中加入：

```ini
Environment=RGS_HANG_TIMEOUT_MS=64
```

重新构建 `adreno` 包和镜像后，再以启动日志验证。

### 9.3 运行时控制接口

RGS 控制命令表中还存在：

```text
gpu_set_preemption_check_short_timeout
gpu_set_preemption_check_short_state
gpu_enable_long_job_detect
gpu_set_long_job_timeout
```

`kgsl` 支持 `-c` 控制入口，`kgsl -c help` 可列出当前构建支持的命令及语法。不同闭源版本的命令编码可能变化，自动化脚本应先在目标版本执行 help 和回读，不应只依赖字符串推断参数分隔格式。

### 9.4 关闭 hang detection

RGS 还读取 `RGS_HANGCHECK_DISABLE`。非零值会关闭软件 hang detection。除专门的稳定性实验外不建议关闭，因为它会把可恢复的单 context 长任务扩大成整机卡死、持续占用 GPU 或后续硬件 watchdog。

## 10. 调试检查清单

### 10.1 启动阶段

```bash
systemctl status kgsl@0.service
systemctl status gsl_hab_server.service
systemctl status vhost-user-gpu.service
systemctl show kgsl@0.service -p Environment
```

检查日志中是否出现：

```text
RGS0 GFX Ready
sw hang detection enabled, timeout short ..., long ...
RGS0 GMU init DONE
```

### 10.2 fault 定位

优先提取：

```text
bad_ctxt_idx
fault ts
pid / process name
error code
ft_policy
Snapshot capture COMPLETED
Hang recovered in ... ms
```

判断原则：

- 602：检查 preemption、ringbuffer 切换和 short timeout；
- 603：检查长 shader/long IB、long timeout 和 fault context 的 IB；
- 609：检查 GPC/RBBM/CP 硬件状态、寄存器和电源/时钟稳定性；
- 不要用 BPMD 创建时间减去 fault 时间来判断是 32ms 还是 512ms。

### 10.3 dump 归档

```bash
find /tmp -maxdepth 1 -name 'gpu*_statedump*.bpmd'
find /var/log/qlf_dumps -name 'gpu*_statedump*.bpmd'
findmnt /tmp /var/log
```

如果日志出现 `errno=18 Invalid cross-device link`，说明 dump 已生成但 QLF 的跨文件系统 rename 失败，应先从 `/tmp` 取证，避免重启后 tmpfs 内容丢失。

## 11. 开源 KGSL 与 PVM RGS 的边界

Android graphics-kernel 中还存在：

```c
unsigned int adreno_drawobj_timeout = 2000;
static unsigned int _fault_timer_interval = 200;
```

它们属于 Android 内核 dispatcher 的另一套 fault detection 路径，不能据此断言 PVM RGS 的 timeout 是 2000ms。同理：

- `adreno_hfi.h` 说明 603 是 Long IB timeout，但没有定义 long timeout 必须为 512ms；
- 512ms 来自 PVM RGS 的运行配置与 `libGSLKernel.so` 实现；
- PVM RGS 的精确默认值、限制和计算规则可能随闭源 Adreno 版本变化，升级库后需要重新检查启动日志或反汇编。

## 12. 总结

SA8797 Gunyah 图形虚拟化中，GVM 不直接控制物理 GPU。GVM 的 GSL 请求通过 `MM_GFX`/virtio-HAB 进入 PVM 的 `gsl_hab_server`，再由 PVM `libgsl` 送入 `kgsl` 进程中的 RGS。RGS 通过 HFI 驱动 GMU 调度 Adreno GPU，同时承担故障恢复和 postmortem snapshot。

发生 error 603 时，含义是 Long IB timeout。对本文现场，RGS 启动配置为 short 32ms、long 512ms，所以本次 BPMD 是 long 512ms 配置路径触发。error 609 则属于 GPC 硬件错误。两类 fault 最终都可能走同一个 `rgs_snapshot_capture()`/`rgs_snapshot_flush()` 和 QLF 归档流程，但触发机制不同。

最终的 `gpu0_statedump...bpmd` 由 PVM `libGSLKernel.so` 创建；GVM 只通过 backend 提供 guest snapshot 数据。现场文件留在 `/tmp` 的直接原因是 QLF 使用 `rename()` 跨文件系统移动失败，而不是 BPMD 生成失败。
