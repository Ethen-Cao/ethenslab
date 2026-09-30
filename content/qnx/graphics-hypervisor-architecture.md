+++
date = '2026-09-21T00:00:00+08:00'
draft = false
title = 'Graphics Hypervisor Architecture：从 Guest 图形内存到 QNX 黑屏与 PMEM 排查'
description = '理解 HGSL、HAB、KGSL 与 SMMU 的协作，区分 Guest buffer 和 Host GPU context 内存，并通过一次黑屏与 pmemtbl 快照建立完整排查方法。'
tags = ['QNX', 'Hypervisor', 'GPU', 'HGSL', 'KGSL', 'PMEM', 'Android', '故障分析']
ShowToc = true
TocOpen = true
+++

在 QNX Host 与 Android Guest 共用 GPU 的座舱系统架构中，Android 侧出现的界面黑屏，其根因未必源于 Android 自身的内存枯竭。尽管像素 Buffer 的物理存储可能完全分配在 Guest 侧，但只要触发创建新的 GPU 渲染上下文 (Context)，就必然依赖 Host 侧的底层资源。一旦 Host 侧某个关键的专用内存池耗尽，这种资源匮乏就会沿着跨虚拟机的调用链向上传递，最终导致 Android 渲染进程异常退出。

本文旨在系统性地剖析 Graphics Hypervisor Architecture 的内存与控制链路，通过还原一次真实的桌面黑屏故障，并结合 `pmemtbl_control.txt` 快照，建立一套标准化的资源溯源与占用分析方法。

> [!NOTE]
> **适用范围声明**：本文解析基于 Qualcomm GPU 虚拟化架构及特定软件版本的实现。常规、非受保护且无特殊 Heap 属性的 Android Buffer 遵循 Guest 默认分配路径；涉及安全内存 (Secure Memory)、特殊 Heap、以及 Camera/Video 的外部 Buffer，必须独立查证。

## 1. 核心架构：GPU 虚拟化与职责划分

该虚拟化架构的核心思想是：将 Android 侧 (Guest) 的 GPU 前端请求，通过 HAB (Hypervisor Access Bus) 安全可靠地透传给 QNX 侧 (Host) 的 GPU 后端执行。理解这套架构的切入点，在于明确以下三大职责的归属：

1. **物理存储分配**：由谁提供真实的物理页面？可能是 Guest 的页分配器，也可能是 QNX 侧的 PMEM 分配器。
2. **GPU 映射与访问控制**：由谁建立 GPU 对这些物理页的访问权限？QNX GPU 后端及相关的 SMMU 驱动负责地址的映射管理。
3. **命令提交与执行同步**：由谁负责发起和等待完成？Guest 前端与 Host 后端协作，最终将指令投递至底层的同一块物理 GPU。

> [!IMPORTANT]
> “Host 后端能看到一个 Buffer”仅仅意味着 Host 参与了该 Buffer 的映射或管理，**不能直接等同于该 Buffer 的物理存储是由 Host 侧内存池分配的**。

### 1.1 架构拓扑

<style>
.gha-figure{width:min(1600px,calc(100vw - 48px));position:relative;left:50%;transform:translateX(-50%);margin:28px 0}.gha-figure iframe{display:block;width:100%;height:auto;aspect-ratio:2048/1120;border:1px solid #cbd5e1;border-radius:8px;background:white}.gha-figure figcaption{font-size:14px;line-height:1.7;color:var(--secondary);margin-top:10px;text-align:center}@media(max-width:720px){.gha-figure{width:100%;left:auto;transform:none}.gha-figure iframe{aspect-ratio:auto;height:330px}}
</style>

<figure class="gha-figure">
<iframe src="../../../static/diagrams/graphics-hypervisor-architecture.html" title="Graphics Hypervisor Architecture 架构图" loading="lazy"></iframe>
<figcaption>路径 1：Guest 分配；路径 1.1：跨虚拟机导出与映射；路径 2：Host 分配。</figcaption>
</figure>

[在独立页面查看完整架构图](../../static/diagrams/graphics-hypervisor-architecture.html)

图中展示了 GPU 虚拟化环境下的逻辑交互关系，并非完整的显示合成流。需注意，图中的 KGSL 模块并非直接运行在 QNX 微内核空间，现场实际存在独立的 `kgsl` 用户态服务进程。

### 1.2 核心模块职责矩阵

| 模块组件 | 架构职责 |
|---|---|
| **LA GVM** | Linux/Android Guest 系统，承载 Launcher、SystemUI、App 及其图形渲染前端。 |
| **QNX PVM** | Host 侧特权执行环境，不仅运行本地图形客户端，还承载着共享 GPU 的后端核心服务。 |
| **OpenGL ES / EGL** | GL 负责渲染状态与绘图命令的管理；EGL 负责 Context 与 Surface 的平台原生连接。 |
| **GSL Client / HGSL** | Guest 侧图形系统层及虚拟化前端，负责封装 GPU 操作、内存导出协议和 Context 请求。 |
| **KHAB / HAB / UHAB** | 跨虚拟机通信与内存共享的基础设施，负责高速传输请求、句柄及附带数据。 |
| **GSL HAB Server** | 运行于 Host 上接收 Guest 图形 RPC 的服务端代理，负责将请求路由给后端。 |
| **GSL / KGSL (RGS)** | GPU 后端资源核心管理者，掌控上下文、内存描述符、SMMU 映射、命令提交与时序同步。 |
| **Kernel / SMMU** | 负责建立和约束设备侧 (GPU) 的地址访问视图。 |

> [!WARNING]
> Guest sysram、QNX `/sysram` 与 QNX `/mm_dma` 是截然不同的内存归属对象。虽然它们在硬件层面都位于同一块物理 DDR 内，但在架构排查时，绝不能混淆统计口径。

## 2. 内存与控制路径解析

### 2.1 路径 1：Guest 分配普通图形内存

对于常规的 Android `GraphicBuffer`，Gralloc 通常将其标记为 `qcom,system`（Legacy 分支映射至 `ION_SYSTEM_HEAP_ID`）。这种 System Heap 优先消耗 Guest 系统本身的页池，当资源不足时才会向下调用 Android 内核的 `alloc_pages()`。

```text
Android GraphicBuffer / Gralloc
    → 选用 qcom,system / ION_SYSTEM_HEAP_ID
    → 消耗 Guest System Heap 页池 / 调用 alloc_pages()
    → 返回 DMA-BUF / fd
```

HGSL 自行分配普通图形内存时，同样遵循 Guest 分配路径：
```text
hgsl_ioctl_mem_alloc()
    → hgsl_sharedmem_alloc()
    → hgsl_alloc_pages() / alloc_pages()
    → hgsl_hyp_mem_map_smmu()
```
在此路径下，物理页面完全从属于 **LA Guest OS memory**。

### 2.2 路径 1.1：内存导出与 GPU 访问映射

Guest 虽然分配了物理内存，但这块内存要被底层物理 GPU 访问，必须通过 Host 后端在 SMMU 中建立映射。该路径的核心是将已有 Buffer 的描述信息（fd, size, offset）通过 HAB 总线导出。

```text
Guest 已持有 DMA-BUF / fd
    → HGSL 封装导出请求
    → habmm_export() 发起跨域共享
    → KHAB → Hypervisor → Host HAB / GSL HAB Server 接收请求
    → RPC_MEMORY_MAP_EXT_FD_PURE
    → Host 后端指令 SMMU 建立 GPU 虚拟地址映射
```
这里传递的仅仅是**共享与映射关系**，Host 端绝不会为此再申请一份同等大小的像素存储。这就解释了排查中的两个核心现象：
1. Android 的 Buffer 记录会出现在 Host 后端的客户端明细中，但这绝对不代表它是由 QNX `/mm_dma` 分配的。
2. 同一份物理内存可能被 SurfaceFlinger、Launcher 甚至硬件合成器同时引用。若简单相加各个客户端的视角大小，必然导致统计严重失真。

### 2.3 路径 2：Host 本地 PMEM 分配

对于 QNX 本地的图形客户端，以及 GPU 后端（KGSL）在管理工作时自身必需的资源，分配请求将走向 Host 侧路径：

```text
QNX 侧本地客户端 / GPU 后端内部需求
    → GSL / KGSL
    → PMEM Allocator 模块
    → 依据 PMEM ID、Flags、VMID 与平台配置解析策略
    → 从 Typed Memory / 普通物理页 / Carveout 提取内存
```

> [!TIP]
> **概念澄清**：PMEM 是一种分配与管理机制，而 `/mm_dma` 仅仅是该平台上存在的一个具体内存池。不能将所有的 PMEM 请求或所有的后端记录一概而论。在实际故障分析中，必须查阅日志明确当前失败申请的目标对象。

### 2.4 Context 创建、命令提交与同步

除了像素数据 Buffer 外，GPU 还需要维持一份上下文状态 (Context)、命令队列及同步对象。当 Android 层发起 EGL Context 创建时，驱动会向 Host 侧发起跨域请求：

```text
eglCreateContext()
    → Guest 侧 EGL / GSL 驱动打包请求
    → HGSL_IOCTL_CTXT_CREATE
    → hgsl_hyp_ctxt_create_v1() (或 legacy 路径)
    → RPC_CONTEXT_CREATE
    → Host 侧执行 rgs_context_create_common()
    → 后端从本地池分配 Context 所需资源
```

Context 建立完毕后，Guest 的渲染命令及其资源引用进入提交流水线，由 Host GPU 后端统筹调度执行。

## 3. 跨域资源依赖与耗尽连锁反应

基于上述架构，我们就能理解：一次成功的跨域渲染操作，往往强依赖于多个完全独立的资源域。

| 资源类别 | 架构归属 | 是否属于像素存储范畴 |
|---|---|---|
| 常规 GraphicBuffer / HGSL 内存 | LA Guest 分配器 | 是（承载实际画面像素） |
| 跨域导出、导入及 GPU 地址映射 | Guest 与 Host 协同维护 | 否（仅代表访问权限与映射表） |
| GPU 后端 Context Records | QNX 侧 `/mm_dma` 内存池 | 否（属于后端管理上下文资源） |
| Context 队列、时间戳缓冲管理 | 按具体 FE/BE 分支策略分配 | 否（需要独立核算） |

因此，**哪怕 Guest 端拥有充沛的空闲内存页面，哪怕旧有的纹理完全可以正常访问，只要新建 Context 时宿主侧 (Host) 的专属管理池资源耗尽，该次渲染启动依然会遭遇滑铁卢**。

### 3.1 Context 的真实存储开销

在一次典型的分配失败现场中，日志清晰地指明了 QNX 后端的 Context Records 路径正试图请求 **`0x30000 (192 KiB)`** 的空间。

提取本地 `GSLKernel.so` 的机器码进行逆向印证：
```asm
0x1883c: mov  x0, #196608    // 预装入此次分配的大小参数 (192 KiB)
0x18844: bl   0x339c8        // 跳转进入 PMEM 分配器封装
0x1884c: cbnz w0, 0x188f0    // 捕获非零返回码，跳转错误分支
```

而 Android HGSL 的源码侧还揭示了其他潜在开销（如 Shadow Timestamp 缓冲、Context Doorbell Queue 等）。这警示我们，Context 的开销并不是一个静态常量，不同驱动版本和队列模型下的资源消耗存在波动，且各部分的内存池归属也不尽相同。

### 3.2 区分全局空闲与池级空闲

排查内存耗尽时，必须区分整机 RAM 剩余量与专属内存池的剩余量。即使系统级统计显示尚有 1.5 GiB 的空闲，但特定的 `/mm_dma` 内存池在连续或非连续块上的可分配余量极有可能已经归零。
因此，`mmap64(sz=0x30000, non-contig)` 宣告失败并抛出池容量枯竭是完全合理的底层行为，不能用“系统还有很多内存”来轻易否定。

## 4. 故障还原：黑屏链路与错误传播机制

在一场真实的桌面黑屏故障中，一条完整的因果错误链被清晰地记录了下来：

```text
QNX /mm_dma 内存池无可用额度
    ↓
GPU 后端试图申请 192 KiB Context Records 遭拒
    ↓
RPC_CONTEXT_CREATE 跨域应答失败
    ↓
Android EGL 返回 EGL_BAD_ALLOC 错误
    ↓
Android HWUI 触发致命异常 (Fatal / Abort)
    ↓
com.tuanjie.voyahrenderservice 渲染进程非正常退出
    ↓
Launcher 监听到渲染服务断连、SurfaceTexture 被强制销毁
    ↓
桌面 UI 组件丢失画面载体，陷入黑屏
```

### 4.1 QNX：物理资源分配防线的崩溃

提取关键的 QNX 侧现场日志：
```text
15:15:27.063 PMEM: mmap64(sz=0x30000,non-contig)
             id=PMEM_GRAPHICS_FRAMEBUFFER_ID
             fd=13("/mm_dma"), err=Not enough memory
15:15:27.063 Free memory: 1599740 KB
15:15:27.063 info(/mm_dma): contig len=0 KB
15:15:27.063 info(/mm_dma): non-contig len=0 KB
15:15:27.063 rgs_context_create_common[785]:
             alloc_user_ctxt_records() FAILED, status=-4
15:15:27.066 [ahrenderservice|7069846|2]:
             RPC Fn 21 ('rpc_context_create') failed ret -1
```
日志证明：池名匹配 (`/mm_dma`)、分配尺寸匹配 (`0x30000`)、连续与非连续碎片耗尽。此处的 `7069846` 是后端侧虚拟化客户端 ID，绝非 Android 侧真实的 PID。

### 4.2 Android：从分配异常到进程自杀

接收到跨域的失败应答后，Android 侧随即发生雪崩：
```text
15:15:27.072 3383 31702 Adreno-GSL_RPC:
             HGSL_IOCTL_CTXT_CREATE failed
15:15:27.073 3383 31702 OpenGLRenderer:
             Failed to create context, error = EGL_BAD_ALLOC
15:15:27.424 3383 31702 libc:
             Fatal signal 6 (SIGABRT), tid 31702 (RenderThread)
```

审查 HWUI 中的 `EglManager::createContext()` 机制，其对 EGL 失败配置了刚性的拦截策略：
```cpp
LOG_ALWAYS_FATAL_IF(
        mEglContext == EGL_NO_CONTEXT,
        "Failed to create context, error = %s",
        eglErrorString());
```
这表明，并非“EGL 报错本身会杀进程”，而是高层框架 HWUI 判定 Context 缺失属于无法挽回的重症，主动通过 abort 终止了整个渲染进程。

## 5. PMEM 资源溯源与快照分析方法

确认了 `/mm_dma` 发生 OOM，下一步则是精准定位资源的“持仓大户”。对于 GPU 资源，QNX 标准的系统内存分析工具只能将账目粗略算在 `kgsl` 进程名下，此时必须依赖驱动级的内部调试表盘 `pmemtbl`。

### 5.1 捕获排查快照

在拥有较高系统权限的 QNX 控制台中触发快照转储：
```bash
echo pmemtbl > /dev/kgsl-control
```
快照文件将安全落地至 QNX 文件系统：`/var/log/pmemtbl_control.txt`。

为了构建绝对严谨的时间横断面证据链，建议执行以下标准作业组合指令：
```bash
# 1. 抓取 QNX 侧各内存池的物理映射范围与当前水位
pidin syspage=asinfo
showmem -t mm_dma

# 2. 强制触发 GPU 后端客户端明细落盘
echo pmemtbl > /dev/kgsl-control
```

### 5.2 多维统计口径辨析

快照文件的顶部记录了总览信息：
```text
pmem table dump: total entries=21914,
 total size alloc'd=997956712(0x3b7b9c68), time=172026640.00ms
RGS release: 0x74725000, GMU FW release: 0x30020006
```

随后输出按客户端聚合的宏观账单：
```text
index process name       host pid   total size(bytes) peak size(bytes)
34    ClusterLVGL        979677219   943304784         943304784
21    ahrenderservice     11387026   621998160         623046736
```

在阅读此报告时，必须牢记三者不可混用：
* **`showmem` 池级统计**：提供指定 `/mm_dma` 的确切物理容量使用率。
* **全局头部 `total size alloc'd`**：表征底层驱动在该统计口径下的账面划拨总量。
* **客户端明细相加总和**：该数值通常会大大多于全局 Alloc 量，这是因为其包含了大量从 Guest 映射过来的、甚至在多客户端间被重复引用的共享 Buffer。**决不能将某客户端持有的总量直接等价于其对 `/mm_dma` 的独占消耗**。

### 5.3 快照字段释义与高阶过滤

在快照的最底层明细中，包含了单笔资源的具体信息：

| 关键字段 | 排查价值与应用禁忌 |
|---|---|
| `tbl[index]` | 直接关联至前文的客户端宏观账单，比短缺的进程名更精确可靠。 |
| `size` | 当前记录在案的字节数，请注意一笔记录不绝对对应上层的一个完整的纹理对象。 |
| `va` / `uva` | 位于不同域的虚拟地址游标，不具备推导物理池归属的证据效力。 |
| `pa` | **物理地址字段**。当 PA 为 0 时并非意味着没有物理内存，而是该层级暂未记录。**但通过非零 PA 的筛选，配合 `asinfo` 地址区间过滤，是逼近物理归属真相的最强手段。** |
| `da` | 设备地址视图，专供 GPU 侧定位，不应与 CPU 物理地址混淆。 |
| `pid` | GPU 后端内部的逻辑追踪号。 |
| `usage` / `info` | 提供资源分类的黄金线索，如 `TEXTUR` (纹理)、`COMMAND` (指令环)、`ARRAY` 等。 |

**排查总结**：要证实某进程掏空了特定的 `/mm_dma`，单凭一份表格是不够的。必须将调用栈、运行时的 `asinfo` 物理段范围、池级水位监控以及非零 PA 的精确过滤数据形成证据闭环。
