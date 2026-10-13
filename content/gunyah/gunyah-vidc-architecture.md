+++
date = '2026-10-13T00:00:00+08:00'
draft = false
title = 'Gunyah 下 VIDC 架构与实现原理'
description = '解析 SA8397 平台 Android GVM 与 Linux PVM 的 VIDC 软件架构、Codec2 调用链、跨虚拟机会话管理、HFI 队列及缓冲区机制。'
categories = ['Gunyah']
tags = ['Gunyah', 'Qualcomm', 'SA8397', 'VIDC', 'Codec2', 'V4L2', 'HFI', 'Virtualization']
+++

Qualcomm SA8397 平台的 VIDC 子系统采用硬件虚拟化编解码架构：Linux PVM 管理物理 VPU 的公共资源、固件和跨 VM 会话，Android GVM 通过 Codec2 与本地 VIDC 内核驱动使用编解码能力。Guest 注册与会话创建经过跨 VM 后端，正常运行期间的 HFI 命令和响应由各 VM 的队列直接与固件交互，码流与图像数据由 VPU 通过 DMA 访问。

以下内容对应 BSP 标识为 `sa8797` 的 Android GVM 与 Linux PVM 实现，主要说明非安全视频通路。安全解码的内存授权、固件认证和显示保护不在本节范围内。

## 架构总览

[查看原尺寸架构图](../../static/diagrams/gunyah-vidc-architecture.png) · [下载可编辑 draw.io 源文件](../../static/diagrams/gunyah-vidc-architecture.drawio)

架构图按原始像素显示，图内可横向和纵向滚动。

<div role="region" aria-label="Scrollable VideoCore software architecture" tabindex="0" style="width:100%;max-height:900px;overflow:auto;border:1px solid #dadce0;border-radius:8px;background:#fff;">
  <img src="../../diagrams/gunyah-vidc-architecture.png" alt="VideoCore software architecture across Linux PVM and Android GVM" width="4591" height="5462" loading="lazy" style="display:block;width:4591px;max-width:none;height:auto;margin:0;">
</div>

图中 Application、Java API Framework 和 Native 表示 Android 逻辑分层；其中的客户端库均可运行在同一个应用进程内。`media.hwcodec`、`media.swcodec`、PVM `videoCore` 和 `hyp_video_be` 分别具有独立的进程边界。`MediaCode App` 是应用的匿名示例，`libpag.so` 表示其 Native 解码入口。

| 部署位置 | 主要组件 | 职责 |
|---|---|---|
| Android 应用进程 | Java MediaCodec、JNI、NDK、MediaCodec、CCodec、Codec2Client | 管理 API 状态、选择编解码组件、提交任务并接收回调 |
| Android 硬件编解码服务 | `media.hwcodec`、QTI Codec2 库 | 实现硬件 Codec2 组件，将请求转换为 V4L2 操作 |
| Android 内核 | `msm_vidc`、`msm_virtio_video`、`venus_hfi` | 管理 Guest 会话、缓冲区、HFI 队列及中断 |
| PVM 本地客户端 | `v4q_be_server`、`libvidc_client.so` | 使用 PVM 原生编解码接口 |
| PVM 跨 VM 后端 | `hyp_video_be` | 将 Guest 会话管理请求接入 PVM VIDC 服务，并转发事件 |
| PVM 编解码服务 | `videoCore`、VIDC Client Server、`libvidc.so` | 管理本地与 Guest 会话、固件、设备状态及公共硬件资源 |
| PVM 内核接口 | VFIO、KIUMD | 为用户态驱动提供设备访问、中断及内存映射能力 |
| 共享硬件 | Iris36 VPU、视频固件、DMA 缓冲区 | 执行编解码任务，访问码流和图像内存 |

Gunyah 提供 VM 隔离及资源授权基础。图中的编解码协议、会话状态机与 HFI 处理由 Qualcomm 平台软件和视频固件实现；`qcrosvm` 是 PVM 中承载 Guest 的用户态 VMM，不属于逐帧编解码处理链。

## Android 编解码调用链

### 应用入口与进程边界

应用可通过 Java API 或 NDK API 创建 MediaCodec，两种入口汇合至应用进程内的 Native MediaCodec：

```text
Java android.media.MediaCodec
  → libmedia_jni.so / JMediaCodec
  → Native MediaCodec

libpag.so
  → libmediandk.so / AMediaCodec
  → Native MediaCodec
```

NDK MediaCodec 是 `libmediandk.so` 提供的 API 封装，不是独立服务。Native MediaCodec 根据组件名称选择实现；当前 `c2.*` 路径使用 `CCodec`，后者通过 `Codec2Client` 获取组件存储服务并创建组件。

```text
应用进程
  MediaCodec → CCodec → Codec2Client
                         │ AIDL Binder
                         ▼
media.hwcodec
  libcodec2_aidl.so → libqcodec2_core.so → libqcodec2_v4l2codec.so
                                                   │ open / ioctl / poll
                                                   ▼
GVM 内核
  /dev/video32 或 /dev/video33 → msm_vidc / msm_video.ko
```

台架上的 QTI 硬件服务运行名为 `media.hwcodec`，启动文件为 `vendor.qti.media.c2@1.0-service`，VINTF 声明的 AIDL 实例为 `android.hardware.media.c2.IComponentStore/default`。旧版 OMX 的 `media.codec` 不是此 Codec2 硬件路径的中转服务；`mediaserver` 也不承担应用到该 HAL 的必经转发。编解码器列表查询与组件控制属于不同操作，不能依据列表查询过程判断组件调用的进程归属。

硬件组件与软件组件分别由不同服务承载：

| 服务进程 | AIDL 实例 | 执行方式 |
|---|---|---|
| `media.hwcodec` | `IComponentStore/default` | QTI 硬件组件，经 V4L2 使用 VIDC/VPU |
| `media.swcodec` | `IComponentStore/software` | AOSP 软件组件，在 CPU 上执行相应编解码算法 |

服务选择取决于组件选择和服务发现。软件组件的存在不表示硬件故障后必然自动切换至软件解码。

### Codec2 与 V4L2 的任务转换

`CCodec` 将 MediaCodec 操作适配为 Codec2 的组件生命周期、参数配置和工作任务。`Codec2Client` 跨 Binder 提交任务；服务端 AIDL 适配器将请求交给内部 `C2Component`，任务完成后再通过工作完成回调返回客户端。

QTI Codec2 实现进一步管理输入输出缓冲区、驱动参数以及 V4L2 队列。当前驱动注册 `/dev/video32` 为解码入口、`/dev/video33` 为编码入口；`msm_vidc` 和 `venus_hfi` 编入 `msm_video.ko`，两者不是按图中 Block 数量划分的独立内核模块。

在解码场景中，V4L2 `OUTPUT` 队列接收压缩码流，`CAPTURE` 队列承载解码图像；编码场景则由 `OUTPUT` 接收原始图像、`CAPTURE` 返回压缩码流。`QBUF` 提交缓冲区，`DQBUF` 返回已完成缓冲区，`poll` 用于等待可用数据或事件。

## PVM 服务与用户态驱动

### 客户端与服务端

`video-driver.service` 在 PVM 启动 `/usr/bin/videoCore`。该进程包含 VIDC Client Server 和 `libvidc.so`：前者处理客户端连接及请求，后者实现设备、会话、固件协议和平台适配。

PVM 本地客户端在自身进程中加载 `libvidc_client.so`，调用 `device_open()`、`device_ioctl()` 和 `device_close()`。这些函数通过 POSIX 消息队列与 `videoCore` 通信；服务端按客户端建立处理上下文，调用内部 VIDC API，并分别返回操作结果和异步事件。命令应答与编解码完成回调具有不同语义，接口返回成功不等于对应帧已完成。

`v4q_be_server` 是本地客户端示例，可使用 VIDC 解码压缩视频源。`hyp_video_be` 则是 Guest 会话管理的独立后端进程，同样通过客户端接口接入 `videoCore`。因此，本地业务客户端与跨 VM 后端共享底层 VIDC 设备服务，但不属于同一进程。

### 用户态硬件访问

`libvidc.so` 中的会话管理层维护客户端和 VM 归属，Venus HFI 层组织固件命令与响应，Iris36 平台层处理硬件寄存器、电源及 Linux 适配。PVM 编解码驱动的主要逻辑位于用户态服务内，内核提供其所需的访问机制。

| 接口 | 在 VIDC 中的作用 |
|---|---|
| VFIO | 设备与 MMIO 访问、中断接入及关联的 IOMMU 管理 |
| KIUMD | DMA-BUF 的设备映射、映射解除及相关内存操作 |
| DMA-BUF | 以文件描述符标识可共享的缓冲区 |
| SMMU | 将设备可见的 IOVA 映射至实际内存，并按上下文限制访问 |

这些机制服务于寄存器、通知和内存访问，视频内容仍由 VPU 的 DMA 数据通路读取或写入。

## 跨 VM 会话管理与 HFI 通路

### 会话管理

GVM `msm_vidc` 保留 V4L2 驱动接口，并通过 `msm_virtio_video` 发起需要 PVM 协调的操作。`virtio-video` 在此表示管理协议，跨域消息通过 HAB 传输，由 PVM `hyp_video_be` 接收并接入 `videoCore`。

跨 VM 管理包括 Guest 设备与 VM 上下文的打开和关闭、会话创建、暂停与恢复以及错误通知。正常的单个 Guest 会话关闭通过 `HFI_CMD_CLOSE` 交给固件，PVM 根据固件通知清理其会话上下文；该过程与管理协议中的 `CLOSE_GVM` 不同。

PVM 负责公共硬件状态，Guest 则维护本地 V4L2 实例和运行状态。硬件虚拟化模式下，GVM 初始化自身 HFI 队列，但跳过本地固件加载和启动，由 PVM 负责公共固件生命周期。

### 每 VM 的固件队列

HFI（Host Firmware Interface）定义主机侧驱动与视频固件的通信格式。当前配置为 PVM 和 Android GVM 分别设置 VM0、VM1 队列；队列按 VM 组织，队列中的会话标识进一步区分具体编解码实例。

| 队列 | 写入方 | 读取方 | 内容 |
|---|---|---|---|
| CMDQ | 对应 VM 的驱动 | 视频固件 | 会话命令、参数及缓冲区描述 |
| MSGQ | 视频固件 | 对应 VM 的驱动 | 命令响应、缓冲区完成与错误事件 |
| DBGQ | 视频固件 | 主机侧驱动，取决于平台实现 | 调试消息 |

GVM 分配并映射自己的 HFI 队列内存；PVM 在启动固件前，依据平台配置设置各 VM 的固件可见队列地址及大小。队列地址属于设备地址域，不能直接等同于 CPU 物理地址。Guest 实际映射与 PVM 登记的队列窗口必须一致，该配置并非通过 HAB 动态传递队列地址。

正常运行时，GVM `venus_hfi` 将命令写入 Guest CMDQ，更新队列索引，并在需要时通过 MMIO 通知固件。固件处理命令后写入 Guest MSGQ，驱动在中断处理路径读取响应，完成缓冲区或会话事件。PVM 本地任务通过自己的 HFI 队列执行相同类型的交互。

当前 GVM 硬件虚拟化实现的中断处理跳过本地 DBGQ 清理，稳态响应主要通过 MSGQ 返回。DBGQ 的处理方式不能直接从非虚拟化驱动推及当前 Guest。

HFI 队列保存命令和描述信息，码流及像素数据位于独立缓冲区中。因而，Guest 逐帧任务不需要经 `hyp_video_be` 和 `videoCore` 用户态逐项转发，HAB 消息也不代表完整图像在该通道中复制。固件依据各 VM 的队列和会话状态使用同一物理 VPU；具体调度策略属于固件实现。

## 缓冲区与异步完成

DMA-BUF 文件描述符标识共享内存对象；CPU 虚拟地址用于软件访问，IOVA 则是 VPU 使用的设备地址。CPU 虚拟地址与 IOVA 属于不同地址域，缓冲区所有权和映射生命周期也需分别管理。GVM 驱动将 DMA-BUF 映射至适用的 SMMU 上下文后，HFI 命令以设备地址及长度等字段描述缓冲区。

PVM 原生客户端使用的图像和码流同样存放在 DMA-BUF 中。`videoCore` 按客户端的 PID 和文件描述符导入缓冲区，并建立 VPU 所需的设备映射；POSIX 消息队列传递控制信息和缓冲区元数据。PVM 与 GVM 分别管理各自的缓冲区集合，图中的缓冲区区域不表示两侧业务共用同一个池。

V4L2 的 DMA-BUF 模式通过文件描述符导入缓冲区，并使用 `QBUF`、`DQBUF` 和流控制接口管理使用过程。这一机制定义了驱动与缓冲区之间的接口，不保证应用的整个视频链路没有复制。[Linux V4L2 DMA-BUF 文档](https://docs.kernel.org/userspace-api/media/v4l/dmabuf.html)

一次硬件解码任务的主要过程如下：

1. 应用提交压缩码流；Codec2 组件准备码流缓冲区和可用的输出图像缓冲区。
2. GVM 驱动映射缓冲区，并向 CMDQ 提交包含会话标识和设备地址的 HFI 命令。
3. 固件控制 VPU 读取码流、执行解码并写入输出图像。
4. 固件写入完成响应；GVM 驱动读取 MSGQ，更新缓冲区状态并唤醒等待方。
5. QTI Codec2 接收 V4L2 完成结果，经工作完成回调交还应用；硬件及后续消费者结束使用并满足同步条件后，缓冲区才能复用。

MediaCodec 的创建、配置和启动属于生命周期操作，输出缓冲区返回才表示相应处理结果可用。使用 Surface 输出时，图像通过原生缓冲区交付消费者；ByteBuffer 模式、码流准备和后处理仍可能引入 CPU 复制。[Android MediaCodec 文档](https://developer.android.google.cn/reference/android/media/MediaCodec)

调用成功、命令提交、固件应答和业务帧消费是不同阶段。缓冲区仍由硬件或消费者持有时，提前复用、解除映射或释放可能破坏后续处理；超时处理也必须同步收敛任务、回调和缓冲区的生命周期。

## 故障通知与恢复

PVM 将公共 VIDC 设备判定为 fatal 时，错误处理路径先记录状态并通知 Guest 和本地客户端，再启动异步设备清理与复位。设备错误、固件响应超时等均可能进入该路径。

`GVM_SSR` 载荷区分设备不可用与驱动不可用：设备状态位按设备编号组织，driver-down 使用独立标志；HAB 断连也可在 Guest 侧合成 driver-down 事件。GVM 收到 SSR 后强制反初始化设备并将实例置为错误状态，driver-down 还会关闭 Guest 管理通道。因此，SSR 事件不能直接等同于物理硬件故障，也不能按载荷位值识别某个应用或会话。

`GVM_SSR` 表示故障状态传播，不表示固件已重载，也不表示应用会话已经恢复。恢复需要依次满足公共设备和固件可用、VM 队列重新就绪、会话及缓冲区状态重建、业务重新提交并获得有效输出等条件。PVM 和 GVM 共享物理 VPU，因此公共设备故障可以同时影响两侧业务，而各客户端的重建进度可能不同。

故障定位应覆盖三个边界：应用到 Codec2 服务的 Binder 调用、Guest 到 PVM 的会话管理，以及驱动到固件的 HFI 交互。Binder 未返回只能确定客户端等待服务响应；HFI 超时只能确定相应固件响应未及时完成。进一步归因需要结合服务端线程栈、两侧驱动状态、HAB 事件和固件记录。

## 关键实现位置

下列路径均相对于工程代码根目录，标识当前实现中的入口和边界。QTI Codec2 核心、`hyp_video_be` 和视频固件的部分实现以预编译形式交付，其内部线程、锁和调度策略应以对应版本的源码或符号为准。

### Android 框架与 HAL

- `qssi/frameworks/base/media/jni/android_media_MediaCodec.cpp`：`JMediaCodec` 和 Java 到 Native 的调用入口。
- `qssi/frameworks/av/media/ndk/NdkMediaCodec.cpp`：`AMediaCodec` 的 Native 封装。
- `qssi/frameworks/av/media/libstagefright/MediaCodec.cpp`：Native 生命周期和 CodecBase 选择。
- `qssi/frameworks/av/media/codec2/sfplugin/CCodec.cpp`：Codec2 组件创建及 MediaCodec 适配。
- `qssi/frameworks/av/media/codec2/hal/client/client.cpp`：组件存储服务发现、组件调用和完成回调。
- `qssi/frameworks/av/media/codec2/hal/aidl/Component.cpp`：AIDL 请求到内部 `C2Component` 的服务端适配。
- `vendor/vendor/qcom/proprietary/prebuilt_HY11/target/product/gen5_gvm/vendor/etc/vintf/manifest/c2_manifest_vendor_aidl.xml`：QTI Codec2 AIDL 服务实例声明。

### GVM 内核

源码根目录为 `vendor/vendor/qcom/opensource/video-driver/`：

- `driver/vidc/src/msm_vidc_probe.c`、`msm_vidc_v4l2.c`：设备注册与 V4L2 接口。
- `driver/vidc/src/msm_vidc_driver.c`：Guest 会话与设备错误处理。
- `driver/vidc/src/venus_hfi.c`、`venus_hfi_queue.c`：HFI 队列初始化、命令提交和固件交互。
- `driver/vidc/src/msm_vidc_memory.c`：DMA-BUF 导入和设备地址映射。

跨 VM 前端位于 `vendor/vendor/qcom/opensource/virtio-video/driver/`，其中 `virtio_video_msm_hab.c` 实现 HAB 命令和事件通道，`virtio_video_msm_hw_virt.c` 实现硬件虚拟化管理操作。

### PVM 服务

源码根目录为 `linux/apps/apps_proc/vendor/qcom/proprietary/video-driver/`：

- `video-driver.service`：`videoCore` 的 PVM 服务启动定义。
- `client-server/client/vidc_client.c`：客户端请求、应答及异步事件接口。
- `client-server/server/vidc_server.c`：客户端上下文、消息处理与服务端分派。
- `drivers/codec/vidc/src/vidc_api.c`、`vidc_session.c`、`vidc_vm.c`：设备、会话和 VM 管理。
- `drivers/codec/vidc/src/vidc_hfi.c`、`vidc_hfi_interrupt_handler.c`：HFI 命令和响应处理。
- `drivers/codec/platform/iris36/`：Iris36 硬件平台实现。
- `drivers/codec/os/lv/vidc_os_buffer_lv.c`、`vidc_os_smmu_lv.c`：PVM 缓冲区导入和 SMMU 适配。

跨 VM 后端的构建入口为 `linux/apps/apps_proc/layers/meta-qti-automotive-prop/recipes-multimedia/hyp-video/hyp-video-be_git.bb`；同级 `video-driver/video-driver_git.bb` 负责 PVM VIDC 服务及平台配置的安装。
