+++
date = '2026-09-21T00:00:00+08:00'
draft = false
title = 'Graphics Hypervisor Architecture：从 Guest 图形内存到 QNX 黑屏与 PMEM 排查'
description = '理解 HGSL、HAB、KGSL 与 SMMU 的协作，区分 Guest buffer 和 Host GPU context 内存，并通过一次黑屏与 pmemtbl 快照建立完整排查方法。'
tags = ['QNX', 'Hypervisor', 'GPU', 'HGSL', 'KGSL', 'PMEM', 'Android', '故障分析']
ShowToc = true
TocOpen = true
+++

在 QNX Host 与 Android Guest 共用 GPU 的座舱系统中，Android 界面黑屏并不一定源于 Android 自己的内存不足。即使像素 buffer 分配在 Guest 内存中，创建新的 GPU 渲染上下文仍可能依赖 Host 的资源；Host 侧一个专用内存池耗尽，就可能沿着跨虚拟机调用链让 Android 渲染进程退出。

本文先解释 Graphics Hypervisor Architecture 的内存与控制路径，再还原一次 09-17 15:15 的桌面黑屏，最后用一份 `pmemtbl_control.txt` 快照说明如何从“分配失败”继续追查“资源由谁持有”。

> **适用范围**：以本工程 Qualcomm GPU 虚拟化实现及所核对的软件版本为例。普通、非受保护、无特殊 heap usage 的 Android buffer 使用 Guest 默认分配路径；安全内存、特殊 heap、摄像头/视频外部 buffer 必须单独确认。后文 09-20 的 PMEM 快照用于说明占用分析方法，并非 09-17 黑屏瞬间的快照。

## 1. 架构：一块 GPU，两个执行环境，三种不同职责

这套架构将 Android 侧的 GPU 前端请求，通过 HAB 传给 QNX 侧的 GPU 后端。理解它的关键，是把三个问题分别回答清楚：

- **谁分配物理存储？** 可能是 Guest 页分配器，也可能是 QNX PMEM 分配器。
- **谁建立 GPU 可访问的映射？** QNX GPU 后端及 SMMU 相关逻辑参与地址映射与访问管理。
- **谁提交命令、管理上下文并等待完成？** Guest 前端与 Host 后端协作完成，最终交给同一块 GPU 执行。

“后端能看到一个 buffer”只能说明它参与了管理或映射，不能直接推出“buffer 的物理存储来自后端内存池”。

### 1.1 架构图

图保留参考图的空间布局：左侧 DDR，中间 QNX PVM，右侧 LA GVM，底部 GPU Hardware，最右侧为缩写说明。模块、连线和 HMI 示意均使用 HTML/CSS 绘制。

<style>
.gha-figure{width:min(1600px,calc(100vw - 48px));position:relative;left:50%;transform:translateX(-50%);margin:28px 0}.gha-figure iframe{display:block;width:100%;height:auto;aspect-ratio:2048/1120;border:1px solid #cbd5e1;border-radius:8px;background:white}.gha-figure figcaption{font-size:14px;line-height:1.7;color:var(--secondary);margin-top:10px;text-align:center}@media(max-width:720px){.gha-figure{width:100%;left:auto;transform:none}.gha-figure iframe{aspect-ratio:auto;height:330px}}
</style>
<figure class="gha-figure">
<iframe src="../../diagrams/graphics-hypervisor-architecture.html" title="Graphics Hypervisor Architecture 架构图" loading="lazy"></iframe>
<figcaption>蓝色 1：Guest 分配；蓝色 1.1：跨虚拟机导出与映射；黄色 2：Host 分配。窄屏可点“放大查看”后拖动浏览。</figcaption>
</figure>

[在独立页面查看完整架构图](../../diagrams/graphics-hypervisor-architecture.html)

图展示的是 GPU 虚拟化的逻辑交互关系，不是完整的显示合成与面板扫描输出流程。KGSL 方框也不应直接理解成 QNX 微内核的执行空间：现场可见独立的 `kgsl` 服务进程。

### 1.2 主要模块做什么

| 模块 | 职责 |
|---|---|
| LA GVM | Linux/Android Guest，运行 Launcher、SystemUI、应用与图形前端 |
| QNX PVM | Host 侧执行环境，运行本地图形客户端以及共享 GPU 的后端服务 |
| OpenGL ES / EGL | GL 管理渲染状态与命令；EGL 负责 context、surface 等原生平台连接 |
| GSL Client / HGSL | Guest 图形系统层及虚拟化前端，处理 GPU 操作、内存导出和 context 请求 |
| KHAB / HAB / UHAB | 跨虚拟机通信和共享内存的不同侧接口；传输请求、句柄及相关数据 |
| GSL HAB Server | Host 上接收 Guest 图形 RPC 的服务端，将请求交给后端处理 |
| GSL / KGSL（RGS） | GPU 后端资源管理：上下文、内存描述、映射、命令提交与同步等 |
| Kernel / SMMU | 配合建立和约束设备侧地址访问；地址映射不等于重新分配全部像素数据 |
| GPU / RB high、mid、low | 共享 GPU 及不同优先级的命令环示意；不是三个物理 GPU |

Guest sysram、QNX `/sysram`、QNX `/mm_dma` 是不同的内存归属或分配对象。它们最终都可能位于 DDR，但不能因为属于同一块 DDR 就混用统计口径。

## 2. 实现原理：沿着三条路径读图

### 2.1 蓝色 1：Guest 分配普通图形内存

对普通 Android GraphicBuffer，本工程 gralloc 默认选择 `qcom,system`；legacy 分支默认映射到 `ION_SYSTEM_HEAP_ID`。system heap 先使用 Guest 页池，不足时调用 Android 内核的 `alloc_pages()`。

```text
Android GraphicBuffer / gralloc
    → 选择 qcom,system / ION_SYSTEM_HEAP_ID
    → Guest system heap 页池 / alloc_pages()
    → DMA-BUF / fd
```

HGSL 自行分配普通图形内存时，也可以走 Guest 页分配器：

```text
hgsl_ioctl_mem_alloc()
    → hgsl_sharedmem_alloc()
    → hgsl_alloc_pages() / alloc_pages()
    → hgsl_hyp_mem_map_smmu()
```

这里的物理页面属于 **LA Guest OS memory**。图中的蓝色箭头 1 指向的正是这块内存，并非 QNX Host 的 `/sysram` 或 `/mm_dma`。

### 2.2 蓝色 1.1：导出已有内存，让 GPU 能访问

Guest 已经分配好的 buffer，需要让 Host 后端建立 GPU 访问关系。已有 buffer 的导入路径接收 fd、size、offset 等信息，再通过 HAB 导出共享内存。

```text
Guest 已有 DMA-BUF / fd
    → HGSL
    → habmm_export()
    → KHAB → Hypervisor → Host HAB / GSL HAB Server
    → RPC_MEMORY_MAP_EXT_FD_PURE
    → Host 后端建立 GPU / SMMU 映射
```

这里传递的是共享与映射关系，不是要求 Host 再申请一份同等大小的像素存储。CPU 虚拟地址、物理页地址和 GPU 设备地址是不同层次；同一个物理 buffer 可以拥有多个映射和使用者。

这解释了两个常见现象：

1. Android buffer 能出现在 Host 后端的客户端表中，但不一定由 `/mm_dma` 分配。
2. SurfaceFlinger、Launcher、渲染服务可能同时持有相关资源的引用；把客户端可见大小逐个相加，不能直接得到唯一物理内存占用。

释放也需要区分层次：GPU 使用完成后解除映射、撤销共享并释放相应引用，最终由实际分配者回收页面。只解除某一侧的映射，不代表所有引用都已释放。

### 2.3 黄色 2：Host 本地分配 PMEM

QNX 本地 GL 客户端，以及 GPU 后端自身所需的部分资源，会进入 Host 分配路径：

```text
QNX 本地客户端 / GPU 后端内部需求
    → GSL / KGSL
    → PMEM allocator
    → 依据 PMEM ID、flags、VMID 与平台配置选择内存对象
    → typed memory / 普通页面 / carveout
```

**PMEM 是分配与管理机制，`/mm_dma` 是本平台的一个具体内存池**。不能把所有 PMEM ID、所有 VMID、所有后端记录都视为同一个池。

在本次故障中，运行日志明确给出了目标对象：

```text
id=PMEM_GRAPHICS_FRAMEBUFFER_ID
fd=13("/mm_dma")
```

因此这笔失败申请的池归属是明确的。对其他条目，则仍需检查分配路径和实际运行配置。

### 2.4 Context 创建、命令提交与同步

除了保存像素的 buffer，GPU 还需要上下文状态、记录、队列和同步相关资源。Android 创建 EGL context 时，驱动可以把 context 请求发送给 Host：

```text
eglCreateContext()
    → Guest EGL / GSL 驱动
    → HGSL_IOCTL_CTXT_CREATE
    → hgsl_hyp_ctxt_create_v1() 或 legacy 路径
    → RPC_CONTEXT_CREATE
    → Host rgs_context_create_common()
    → 后端分配 context 所需资源
```

context 建立后，Guest 的渲染命令和相关资源引用进入提交链路，Host GPU 后端协调执行。timestamp、fence 或相应队列机制用于判断工作是否完成；具体采用 RPC 还是 doorbell queue，取决于驱动版本与能力协商。图中的 IPC 箭头不应被理解为每一个 OpenGL API 都单独跨虚拟机调用一次。

## 3. 为什么 Guest buffer 来自 Guest，仍会被 Host 内存耗尽拖垮

一个成功的渲染操作可能同时依赖多个资源域：

| 资源 | 典型归属 | 是否等同于普通 GraphicBuffer 的像素存储 |
|---|---|---|
| 普通 GraphicBuffer / 普通 HGSL 图形内存 | LA Guest 页分配器 | 是 buffer 数据路径的一部分 |
| 导出、导入及 GPU 地址映射 | Guest 与 Host 协作 | 否，是共享和访问关系 |
| GPU 后端 context records | 本次走 QNX `/mm_dma` | 否，是上下文建立所需的后端资源 |
| context 队列、时间戳缓冲及管理对象 | 按具体 FE / BE 分支分配 | 否，需分别核算 |
| QNX 摄像头、视频、仪表等本地 buffer | 按各自 allocator 和池配置 | 不能套用 Guest 默认路径 |

因此，即使 Guest 还有空闲页面、已有纹理也能访问，**只要新建 context 必须申请的 Host 资源失败，该次 context 创建仍会失败**。

### 3.1 Context 到底占多少空间

本次可确认的是：QNX 后端的 context records 路径请求了 **`0x30000 = 196608 bytes = 192 KiB`**。

日志首先证明这笔大小；本地 `GSLKernel.so` 的机器码又给出独立印证：

```asm
0x1883c: mov  x0, #196608    // 此次分配的大小参数
0x18844: bl   0x339c8       // 进入内存分配封装
0x1884c: cbnz w0, 0x188f0   // 返回失败，进入错误分支
```

错误分支引用 `rgs_context_create_common`、`alloc_user_ctxt_records() FAILED` 和源行号 785，与故障日志一致。这里是预编译库反汇编证据，并非取得了后端完整 C 源码；地址仅适用于该库版本，且该分配前存在条件分支。

Android HGSL 的可读源码还给出其他项目：

| 项目 | 申请量 | 适用条件 |
|---|---|---|
| shadow timestamp 缓冲 | `PAGE_SIZE` | v1 创建路径；后续有 FE / BE 处理 |
| context doorbell queue | `PAGE_ALIGN(256 × 4 + 48)` | 后端支持并启用相应队列路径 |
| Guest 管理对象 | `sizeof(struct hgsl_context)` | 随目标内核配置、ABI 变化 |

在 4 KiB 页配置下，前两项各自对应 4 KiB 的申请。但是它们的路径、归属、保留条件不同，**不能机械相加成“每个 context 固定 200 KiB”**。192 KiB 同样只是本次失败的一项后端分配，而非 context 的全部成本，也不包含其使用的全部纹理和 GraphicBuffer。

### 3.2 空闲内存和专用池空闲必须分开看

本次分配失败时，日志仍显示普通可用内存约 1.5 GiB，但 `/mm_dma` 的连续与非连续可分配量都是 0。

QNX typed memory 的查询结果与打开方式有关：非连续分配模式关注可分配总量，连续模式关注最大连续块。排查时应同时核对这两个指标以及请求是否要求连续内存。[QNX：posix_typed_mem_get_info()](https://qnx.com/developers/docs/7.1/com.qnx.doc.neutrino.lib_ref/topic/p/posix_typed_mem_get_info.html)

这次 `mmap64(..., non-contig)` 也失败，且池的非连续空闲为 0，证据指向池容量耗尽；仅凭整机 RAM 尚有余量，不能否定该失败。

## 4. 实战一：09-17 15:15 桌面为什么黑了

### 4.1 按错误传播方向还原现场

已确认的因果链是：

```text
QNX /mm_dma 无可用内存
    ↓
GPU 后端申请 192 KiB context records 失败
    ↓
RPC_CONTEXT_CREATE 失败
    ↓
Android EGL context 创建失败，EGL_BAD_ALLOC
    ↓
HWUI 触发 fatal / abort
    ↓
com.tuanjie.voyahrenderservice 进程退出
    ↓
Launcher 收到渲染服务断开、SurfaceTexture 销毁
    ↓
依赖该服务的桌面渲染画面丢失
```

关键时序如下，时间为日志本地时间，崩溃记录标明 UTC+08:00。

| 时间 | 事件 | 技术含义 |
|---|---|---|
| 15:03:27 | `/mm_dma` 已记录 used=1280MB、free=0MB | 池在黑屏前就已满；这不是认定其首次耗尽时刻 |
| 15:13:50.255 | 通知中心 context 创建失败并开始反复退出 | Host 资源不足已影响其他图形客户端 |
| 15:15:27.024–.030 | 团结服务准备显示“新视角已保存成功”提示 | 紧邻随后 HWUI 初始化失败的操作 |
| 15:15:27.063 | QNX 申请 `0x30000` 失败 | 具体失败点在 Host `/mm_dma` |
| 15:15:27.066 | `rpc_context_create` 返回错误 | 错误经后端返回对应渲染服务客户端 |
| 15:15:27.073 | OpenGLRenderer 报 `EGL_BAD_ALLOC` | Android 无法建立该渲染上下文 |
| 15:15:27.424 | RenderThread 收到 `SIGABRT` | 整个团结渲染进程退出 |
| 15:15:27.775–.777 | Launcher 服务断开、画面载体销毁 | 与桌面中团结渲染内容黑屏吻合 |

### 4.2 QNX：先有物理资源申请失败

以下保留相关字段，省略无关前缀：

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

要点是同一时间的申请大小、明确的池名、失败函数和客户端归属相互对应。`7069846` 是后端侧客户端标识，Android 崩溃进程 PID 为 `3383`；不能要求跨环境 PID 数字相同，或直接把后端标识交给 Android `kill`。

### 4.3 Android：创建失败为什么会终止进程

现场接着出现：

```text
15:15:27.072 3383 31702 Adreno-GSL_RPC:
             HGSL_IOCTL_CTXT_CREATE failed
15:15:27.073 3383 31702 OpenGLRenderer:
             Failed to create context, error = EGL_BAD_ALLOC
15:15:27.424 3383 31702 libc:
             Fatal signal 6 (SIGABRT), tid 31702 (RenderThread)
```

本工程 HWUI 的 `EglManager::createContext()` 在失败时执行 fatal 检查：

```cpp
mEglContext = eglCreateContext(
        mEglDisplay,
        EglExtensions.noConfigContext ? nullptr : mEglConfig,
        EGL_NO_CONTEXT,
        contextAttributes.data());

LOG_ALWAYS_FATAL_IF(
        mEglContext == EGL_NO_CONTEXT,
        "Failed to create context, error = %s",
        eglErrorString());
```

`eglCreateContext()` 失败本身与上层如何处理失败是两个环节。本次是 HWUI 的 fatal 策略将失败升级成进程 abort；不能把它表述为“任何 EGL 错误都会自动杀死进程”。

### 4.4 为什么已有画面能运行，却在保存视角后黑屏

已有 context 与已有 buffer 不需要在每一帧重新分配全部资源。池子耗尽后，它们可能暂时继续工作，直到下一次需要新分配的操作暴露问题。

本次“保存成功”提示紧邻 HWUI RenderThread 创建 context 失败，时序和调用栈支持“提示框触发了新 context 创建”的解释。这是依据现场作出的触发关系推断，不代表已通过复现完整证明，也不能据此认定保存视角操作耗尽了池子。

故障窗口内，Launcher 本身继续处理触摸和重连；确认退出的是它依赖的团结渲染服务。约 49 秒内可见 197 条该服务的 `am_proc_died`，说明简单重启没有立即解决资源不足。死亡事件数不等于同样数量的独立 native crash 文件，也不能直接当作精确黑屏时长。

15:16:17 之后出现重新连接，15:16:27 池中出现约 6 MB 空闲。连接成功只能说明通信恢复，具体画面何时恢复还需要首帧提交、呈现或视频证据。

## 5. 实战二：用 pmemtbl 追查资源持有者

知道“哪个池无法分配”，还需要找出“哪些客户端持有大量相关资源”。仅看 QNX 进程内存时，大量分配可能记在 `kgsl` 后端名下；`pmemtbl` 则提供进一步的客户端与条目视角。

### 5.1 在 QNX 触发并取回快照

在具备设备节点写权限的 QNX 控制台执行：

```sh
echo pmemtbl > /dev/kgsl-control
```

然后从 **QNX** 取回文件：

```text
/var/log/pmemtbl_control.txt
```

若设备开启 SSH/SCP，可在分析主机上执行下面的示例命令；将 `QNX_IP` 替换为实际设备地址，并使用设备允许的账号：

```sh
scp root@QNX_IP:/var/log/pmemtbl_control.txt ./pmemtbl_control.txt
```

若项目通过调试桥或文件服务传输，则使用相应渠道。这个路径属于 QNX，不能默认用 Android 的 `adb pull` 直接读取。触发后确认输出文件已更新、大小稳定，再保存快照，避免读取仍在生成的文件。

为了将客户端记录与具体内存池对应，建议在同一时间窗口保存：

```sh
# QNX：核对内存池的物理范围与当前用量
pidin syspage=asinfo
showmem -t mm_dma

# QNX：触发 GPU 后端客户端表
echo pmemtbl > /dev/kgsl-control
```

`showmem` 选项以目标镜像版本为准。`pmemtbl` 是本 BSP 的驱动调试接口，不是所有 QNX 系统都具备的标准命令。

### 5.2 读懂三个不同的统计口径

该样本的头部为：

```text
pmem table dump: total entries=21914,
 total size alloc'd=997956712(0x3b7b9c68), time=172026640.00ms
RGS release: 0x74725000, GMU FW release: 0x30020006
```

随后先列客户端摘要，再列条目明细：

```text
index process name       host pid   total size(bytes) peak size(bytes)
34    ClusterLVGL        979677219   943304784         943304784
21    ahrenderservice     11387026   621998160         623046736
```

| 层次 | 可以回答的问题 | 不能直接得出的结论 |
|---|---|---|
| 池级统计：`showmem` / typed memory | `/mm_dma` 总量、空闲、连续可用量 | 哪个应用持有全部资源 |
| 全局头部：`total size alloc'd` | 驱动该统计口径的 allocated 量 | 自动等于某个单独池的已用量 |
| 客户端摘要与条目 | 谁持有多少记录、大小和资源类型 | 客户端总量全部来自 `/mm_dma` |

本样本全部客户端明细相加为 **2,769,503,568 bytes，约 2641.204 MiB**，而头部 allocated 约 **951.726 MiB**。两者显然不是可以直接相加、互相替代的同一口径。

### 5.3 条目字段怎么用

| 字段 | 排查用途与限制 |
|---|---|
| `tbl[index]` | 与客户端摘要关联；比仅用截断进程名更可靠 |
| `size` | 当前记录的大小；不保证每条记录等于一个上层纹理对象 |
| `va`、`va_base`、`uva` | 不同侧的虚拟地址信息；不是物理内存池归属证据 |
| `pa` | 可用于地址核对的物理地址字段；0 不能解释为“没有物理内存” |
| `da` | 设备地址字段，不能当作 CPU 物理地址 |
| `pthandle` | 页表/地址空间相关关联信息，辅助识别映射范围 |
| `pid` / `host pid` | 后端客户端归属线索；Guest 客户端标识不一定等于 Android PID |
| `flags`、`refCnt` | 驱动状态与引用信息；没有对应版本定义时，不武断解释私有 bit |
| `usage`、`metadata info` | 资源类别线索，如 TEXTUR、ARRAY、COMMAND |
| `time` | 用于观察现存条目分布；须确认时钟与字段语义后才能换算绝对时间 |

**精确确认 `/mm_dma` 归属需要证据组合**：分配调用及所选对象、运行态 `asinfo` 物理范围、完整物理页/段信息和池级统计。若 buffer 非连续，仅凭一个 `pa` 和 `size` 不能保证覆盖所有真实物理段。可以用非零 PA 筛选和地址区间做初步定位，但不能将这一步冒充完整的物理归属证明。

### 5.4 样本复算：优先追查 ClusterLVGL

这份样本的文件列表时间为 09-20 14:44。逐行复算得到 21,914 条明细，18 个客户端的明细和均与摘要一致。以下单位均为 **MiB = 1024² bytes**。

| 客户端 | 条目数 | 总条目大小 MiB | 非零 PA 条目大小 MiB |
|---|---:|---:|---:|
| **ClusterLVGL** | **18,667** | **899.606** | **888.809** |
| ahrenderservice | 2,065 | 593.184 | 0.383 |
| camcorder_be_server | 159 | 281.137 | 26.254 |
| surfaceflinger | 262 | 273.902 | 0.387 |
| ockpit.launcher | 167 | 139.133 | 0.383 |
| vendor.voyah.ca | 25 | 84.254 | 0.191 |
| system_server | 24 | 72.242 | 0.383 |
| screen | 71 | 66.211 | 7.805 |
| vehiclesettings | 66 | 52.750 | 0.383 |
| launcher:remote | 35 | 45.524 | 0.383 |
| kpit.voyahmusic | 208 | 41.629 | 0.574 |
| ah.cockpit.adas | 25 | 37.043 | 0.574 |
| ndroid.systemui | 82 | 24.320 | 0.383 |
| kgsl | 34 | 15.066 | 15.066 |
| secure memory | 2 | 8.438 | 8.438 |
| ckpit.edgeslide | 12 | 5.250 | 0.383 |
| ais_server | 5 | 0.758 | 0.758 |
| android.hardwar | 5 | 0.758 | 0.191 |

客户端名称按 dump 原样保留，部分已截断。非零 PA 列只是一种筛选统计，不是“每个客户端的完整物理占用”。

ClusterLVGL 的 18,663 条非零 PA 记录合计约 888.809 MiB，是头部 allocated 量的约 93.39%。这是非常突出的量级线索，应优先检查该客户端；这个比例不是已经验证的 `/mm_dma` 精确份额。

团结渲染服务虽然持有约 593.184 MiB 的记录，但不能据此说它从 `/mm_dma` 申请了 593 MiB。普通 Android buffer 的 Guest 分配路径与此表中的后端映射记录可以同时成立。

### 5.5 从大户继续追到资源类型与尺寸分布

本工程 KGSL 头文件定义：

```c
#define KGSL_MEMTYPE_MASK     0x0000FF00
#define KGSL_MEMTYPE_SHIFT    8
#define KGSL_MEMTYPE_TEXTURE  6
```

以该定义解码 `usage`，并用 dump 中的 `TEXTUR` 等元数据交叉核对，ClusterLVGL 的非零 PA 记录中：

- **14,798 条**落在 texture 类型，合计 **867.840 MiB**。
- 占其非零 PA 条目大小的约 **97.64%**。
- 说明排查重心应放在纹理、图像缓存与其生命周期，而不是仅盯着几笔 context records。

下面按所有非零 PA 记录的大小分组，列出主要尺寸；并非只统计 texture 类别：

| 单条大小 | 条目数 | 合计 MiB |
|---|---:|---:|
| 4 KiB | 9,285 | 36.270 |
| 32 KiB | 3,695 | 115.469 |
| 128 KiB | 5,667 | 708.375 |
| 256 KiB | 3 | 0.750 |
| 5440 KiB | 3 | 15.938 |

128 KiB 条目贡献最大，且小块数量很多。下一步可将这些尺寸与纹理格式、对齐、图像缩放结果、缓存策略和页面切换操作对照。**块大小不能唯一反推图像分辨率**，也不能把 PMEM 条目数直接当作 OpenGL texture 对象数。

### 5.6 单次快照能提示规律，不能证明持续泄漏

ClusterLVGL 大量现存条目的 `time` 集中在约 4,508,238～5,458,705.5 ms。按分钟分组，多个完整分钟恰好保留 **1,200 条、54.84375 MiB**。

这提示某种周期性创建或持有行为，值得检查。但这是一张快照中“仍存在的条目按 time 分桶”的结果，**不是连续采样得到的净增长曲线**。尤其头部时间为 172,026,640 ms，与这些条目的时间相差很大；没有确认驱动时间语义前，不应直接说“当前每分钟泄漏 54.84 MiB”。

要证明泄漏，应在同一启动周期、同一业务操作下采集多个快照，比较条目集合与总量，并确认操作结束、引用释放或缓存清理后是否仍持续增长。地址可能被复用，应结合客户端、大小、地址、时间及其他可用标识判断。

### 5.7 一个可复算摘要的离线脚本

下面脚本只做统计核对，**不会把非零 PA 自动判定为 `/mm_dma`**。将它保存为 `summarize_pmem.py`，在分析主机运行 `python3 summarize_pmem.py pmemtbl_control.txt`。

```python
import re
import sys
from collections import defaultdict
from pathlib import Path

text = Path(sys.argv[1]).read_text(errors="replace")
clients = {}
stats = defaultdict(lambda: [0, 0, 0])  # 条目数、总字节、非零 PA 字节
header = re.search(r"total entries=(\d+)", text)
for line in text.splitlines():
    # 进程名可以有空格，例如 secure memory。
    m = re.match(r"^(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", line)
    if m:
        clients[int(m[1])] = (m[2], int(m[4]))
    m = re.match(r"^tbl\[\s*(\d+)\]:\s+(.+)", line)
    if not m:
        continue
    fields = m[2].split()
    size, pa = int(fields[0], 16), int(fields[3], 16)
    item = stats[int(m[1])]
    item[0] += 1
    item[1] += size
    item[2] += size if pa else 0

count = sum(v[0] for v in stats.values())
if not header or count != int(header[1]) or set(stats) != set(clients):
    raise ValueError("快照不完整，或格式与本脚本不匹配")
print("client,count,total_MiB,nonzero_PA_MiB")
for idx in sorted(stats, key=lambda i: stats[i][1], reverse=True):
    count, total, nonzero_pa = stats[idx]
    name, expected = clients[idx]
    if total != expected:
        raise ValueError(f"客户端 {idx} 明细与摘要不一致")
    print(f"{name},{count},{total / 2**20:.3f},{nonzero_pa / 2**20:.3f}")
```
