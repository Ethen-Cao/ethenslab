+++
date = '2026-08-26T10:00:00+08:00'
draft = false
title = '虚拟化 Camera 架构设计'
categories = ['Gunyah', 'Camera', '虚拟化']
tags = ['Camera', 'PVM', 'GVM', 'Gunyah', 'HAB', 'QCarCam', 'EVS', 'V4L2', 'DMA-BUF']
+++

> 本文描述 AVM Camera 在 PVM、GVM、Hypervisor 和 Camera Hardware 之间的分层架构、组件职责、接口契约、数据路径及 Buffer 生命周期。文中的产品、项目、车辆及设备唯一标识均使用通用角色名。

## 1. 设计目标与范围

### 1.1 设计目标

虚拟化 Camera 架构需要在保持 Camera Hardware 由 PVM 统一管理的前提下，向 Android GVM 提供符合 V4L2 和 Automotive EVS 模型的 Camera stream。架构设计目标包括：

- 明确 PVM、GVM、Hypervisor 与 Camera Hardware 的职责边界；
- 将 Camera 生命周期控制与大容量图像数据传输分离；
- 通过共享 Buffer 避免跨 VM 逐帧复制完整图像；
- 通过显式 Buffer ownership 保证生产者和消费者不会并发改写同一 Buffer；
- 保持 GVM 上层符合 Android Car EVS 的标准分层和接口模型。

### 1.2 设计范围

本文覆盖前、后、左、右四路 Camera 从物理采集、PVM 四路聚合、HAB 跨 VM 共享、GVM V4L2/EVS 消费到 Android 客户端的完整架构。

本文不展开 Sensor 寄存器、SerDes 板级连接、ISP tuning 参数，也不把 PVM 的 2×2 图像载荷封装等同于最终鸟瞰算法。标定、畸变校正、几何投影、接缝融合和车模叠加属于独立的 AVM 算法或渲染域。

### 1.3 架构原则

| 原则 | 设计含义 |
| --- | --- |
| Hardware 单一所有者 | Camera Hardware 及 QCarCam stream 由 PVM 管理，GVM 不直接访问物理 Camera |
| 控制面与数据面分离 | HAB 消息传递生命周期、帧索引和归还事件；共享内存承载图像像素 |
| GVM 分配、PVM 写入 | GVM 创建 GraphicBuffer 并导出，PVM 导入后作为跨 VM 输出池 |
| 显式所有权转移 | `GET_FRAME(index)` 把 Buffer 交给 GVM，`RELEASE_FRAME(index)` 把所有权归还 PVM |
| Android 标准分层 | GVM 通过 V4L2、EVS HAL、CarEvsService 和 CarEvsManager 向应用提供 Camera stream |

## 2. Camera 总体架构

<iframe id="camera-virtualization-architecture" src="../../diagrams/camera-virtualization-architecture.html" title="Camera 虚拟化架构" loading="lazy" style="display:block;box-sizing:border-box;width:100%;height:900px;border:1px solid #dadce0;border-radius:8px;overflow:hidden;"></iframe>

<script>
(() => {
  const frame = document.getElementById('camera-virtualization-architecture');
  window.addEventListener('message', (event) => {
    if (event.source !== frame.contentWindow ||
        event.origin !== new URL(frame.src, document.baseURI).origin ||
        event.data?.type !== 'camera-virtualization-architecture-height') return;
    const height = event.data.height;
    if (!Number.isFinite(height) || height <= 0) return;
    frame.style.height = Math.min(2400, Math.ceil(height) + 2) + 'px';
  });
})();
</script>

[独立打开架构图](../../diagrams/camera-virtualization-architecture.html)

## 3. 分层组件设计

### 3.1 PVM Camera 子系统

| 层级 | 组件 | 架构职责 |
| --- | --- | --- |
| 应用/服务 | `v4q_be_server` | 接收 GVM 的 Camera 生命周期请求，创建 HAB 通道并管理跨 VM Camera 实例 |
| Framework/Middleware | `hyp_camera::cV4qCamera` | 管理 Camera 实例、设备状态、输入输出 Buffer 与事件回调 |
| Framework/Middleware | `v4q::v4q_QcarcamOneframe` | 管理前、后、左、右四路输入，选择有效帧并生成四合一输出 |
| Platform Camera API | `libqcxclient.so` | 提供 QCarCam API，由后端内的 `qcarcam_wrap_*` 函数调用，完成 input 配置、Buffer 注册、stream 控制和帧回调 |
| Platform Camera Service | `qcxserver` | 独立进程，管理 ISP use case、Camera request、硬件错误与恢复事件 |
| 虚拟化后端 | `hyp_camera::cHabConnect` | 通过 `libuhab.so` 导入 GVM Buffer、发送帧通知并接收 Buffer 归还事件 |
| 虚拟化后端管理 | `vhost-user-qti` | 由 `vhost-user-cam.service` 启动，通过 `/dev/vhost-cam` 配置 Camera VirtIO 后端队列 |
| Linux Kernel / Camera | `/dev/kiumd` · `kiumd.ko`；`/dev/vfio/*` · VFIO；`/dev/scmi_camera` · `qcom_uscmi.ko` | 支撑 QCX 的 SMMU 映射、Camera 寄存器访问与资源控制；Camera 平台设备由 `vfio-platform` 绑定 |
| Linux Kernel / HAB | `/dev/hab`、`/dev/vhost-cam` · `msm_hab.ko` | 分别提供 HAB 用户接口和 Camera VirtIO 后端管理接口，支撑共享页与消息通道 |

PVM 是 Camera 数据生产侧，也是物理 Camera 的唯一所有者。`cV4qCamera`、`v4q_QcarcamOneframe` 和 `cHabConnect` 位于 `v4q_be_server` 内；`qcarcam_wrap_*` 是该程序内的接口封装函数。`cHabConnect` 经 `libuhab.so` 使用 `/dev/hab`，而 `/dev/vhost-cam` 由 `vhost-user-qti` 配置。四路输入和跨 VM 输出均由 PVM Camera 子系统统一调度。

### 3.2 GVM Camera 子系统

| Android 层级 | 组件 | 架构职责 |
| --- | --- | --- |
| Applications | AVM/EVS Client | 请求 surround-view stream、消费并归还 EVS Buffer |
| Application Framework | `CarEvsManager`、`CarEvsService` | 提供应用 API、访问仲裁和 Camera service 状态机 |
| Native Service | `evsmanagerd_v4q` | 向 CarService 提供 `IEvsEnumerator/v4q`，连接下层 `IEvsEnumerator/hw/0` 并转发 stream 与 Buffer 交付/归还 |
| Native/HAL | `android.hardware.automotive.evs-v4q`：`EvsEnumerator`、`EvsV4lCamera` | 枚举虚拟 Camera，管理 EVS stream 和客户端 GraphicBuffer；在 `EvsV4lCamera` 中完成格式转换/复制 |
| Native/HAL | `VideoCapture` | 从 V4L2 取得帧 index 和映射地址，消费后重新入队 |
| Vendor Service | `ais_v4l2_proxy_qcc6`：`cFeCamera`、`cHabConnect` | 分配并导出共享 Buffer，把 HAB 帧事件转换为 V4L2 queue 操作 |
| Android Kernel / V4L2 | `/dev/video61` · `ais-v4l2loopback.ko` | 当前 4AVM 的虚拟 Camera 节点，接收 Proxy 提交并向 EVS HAL 提供帧 |
| Android Kernel / HAB | `/dev/hab-cam` · `msm_hab.ko` | Camera HAB 用户接口；`libuhab.so` 在节点不存在或访问被拒绝时可回退到 `/dev/hab` |

GVM 是 Camera 数据消费侧。物理 Camera 的差异被收敛在 V4L2 Proxy 以下，上层保持 Android Automotive EVS 的标准接口模型。

### 3.3 Hypervisor Layer

Hypervisor 层提供 VM 隔离、共享页映射、doorbell/虚拟中断以及 HAB 通信基础。它只承载 Camera 控制消息、帧元数据和共享内存映射，不执行四路同步、像素拼接或颜色格式转换。

### 3.4 Hardware Layer

Hardware 层由 Camera Sensor、Serializer/Deserializer、MIPI CSI-2、ISP/IFE、Camera DMA 和 DDR 组成。图像由 Camera DMA 写入 PVM 可访问的输入 Buffer，随后进入 PVM Camera 软件栈。DDR 中的 QCarCam 输入池、跨 VM UYVY 输出池和 EVS 客户端输出池分别由采集、聚合和转换阶段写入。

## 4. Camera 生命周期与时序设计

### 4.1 启动与 Buffer 建立

1. GVM 应用经 `CarEvsManager`、`CarEvsService` 和 `evsmanagerd_v4q` 请求 EVS Camera stream。
2. GVM Camera HAL 打开 V4L2 节点并申请 capture Buffer。
3. GVM Camera Proxy 分配 GraphicBuffer，并通过 HAB 导出共享内存句柄和 `exportId`。
4. PVM `cV4qCamera` 通过 `cHabConnect` 导入并映射这些 Buffer，把它们登记为跨 VM 输出池；四路 QCarCam 各自注册独立的采集输入池。
5. PVM Camera 后端创建帧通知通道和归还通道，再启动四路物理 Camera stream。

### 4.2 稳态帧传输

1. Camera Hardware 经 ISP/IFE 和 DMA 产生多路图像。
2. PVM `v4q_QcarcamOneframe` 获取各路输入，按 ready bitmap 和最近有效帧执行 2×2 聚合。
3. PVM 将结果写入 GVM 导出的共享 Buffer，然后发送 `WORK_GET_FRAME(index, frameId, timestamp)`。
4. GVM Camera Proxy 根据 index 向 V4L2 loopback capture 路径执行 `QBUF`，EVS HAL 再通过 `DQBUF` 取帧。
5. EVS HAL 将图像转换或复制到应用 Buffer，并把底层 V4L2 Buffer 重新入队。
6. GVM Camera Proxy 收到 Buffer 可回收事件后发送 `WORK_RELEASE_FRAME(index)`。
7. PVM 将对应 index 放回输出空闲队列。

### 4.3 停止与释放

停止顺序应与启动相反：先停止上层消费和新帧提交，再等待在途 Buffer 返回，最后解除 HAB export/import、V4L2 Buffer 和 QCarCam stream。若先解除共享内存而仍有 frame callback 或 release event 在途，会产生越界访问、重复归还或关闭超时。

## 5. PVM 采集架构

### 5.1 数据源

AVM 的原始画面来自前、后、左、右四路车外 Camera。配置把四路 QCarCam input id 分别绑定到四个方向；每一路先经 SerDes 和 CSI 进入 ISP/IFE，再由 QCarCam 输出到 PVM 内存。因此，数据生产者是 PVM 所拥有的物理 Camera 子系统，Android GVM 只是共享帧的消费者。

PVM Camera 输入契约从 ISP 输出开始，格式定义为 UYVY。Sensor 在线缆上的信号格式、SerDes 虚拟通道编排和 ISP 内部 pipeline 参数属于 Hardware/Platform Camera 的下层配置，不进入本架构接口。

### 5.2 PVM 采集

`v4q::v4q_QcarcamOneframe` 打开四个 input，每路配置为最终输出宽、高的一半，即 `1920×1536`。它通过 `qcarcam_wrap_*` 调用 `libqcxclient.so` 的 QCarCam API，为每一路注册一组输入 Buffer 后启动 stream；frame callback 通过返回的 Buffer index 和 timestamp 标记对应方向的新帧已经到达。

四路输入共用一个合成线程。该线程不要求所有方向在同一个回调中同时到达，而是维护四方向的 ready bitmap 和最近一次有效 Buffer index，再决定是否生成下一帧四合一载荷。

## 6. 数据格式契约

| 链路位置 | 分辨率 | 格式 | 单帧有效载荷 | 说明 |
| --- | ---: | --- | ---: | --- |
| PVM 单路 QCarCam 输出 | `1920×1536` | UYVY 4:2:2 packed，16 bit/pixel | `5,898,240` byte，约 `5.625 MiB` | 前、后、左、右四路相同 |
| PVM 四合一输出 | `3840×3072` | UYVY 4:2:2 packed，16 bit/pixel | `23,592,960` byte，约 `22.5 MiB` | 2×2 载荷；默认配置 5 个输出 Buffer |
| PVM/GVM 共享 Buffer | `3840×3072` | UYVY | 约 `22.5 MiB` | HAB 消息不携带像素，像素留在共享页中 |
| GVM V4L2 capture | `3840×3072` | `V4L2_PIX_FMT_UYVY` | 约 `22.5 MiB` | 部署配置对应 `/dev/video61`；架构上应视为 `/dev/videoX` |
| GVM EVS 客户端 Buffer | `3840×3072` | `YCrCb 4:2:0 Semi-Planar` | 有效像素约 `16.875 MiB` | `fillNV21FromUYVY` 或 C2D 路径完成 UYVY 到 NV21 兼容布局的转换 |

UYVY 每两个像素按 `U0 Y0 V0 Y1` 排列，stride 为 `width × 2`。PVM 四合一输出每行 `7680` byte。5 个原始输出 Buffer 的像素存储约为 `112.5 MiB`，还不包括四路输入池、GraphicBuffer 对齐、元数据和 EVS 客户端输出池。

## 7. 多路 Camera 聚合设计

### 7.1 四合一载荷布局

PVM `v4q_QcarcamOneframe::StitchingThread` 将四路矩形图像组织为 2×2 载荷。每个象限通过逐行 `memcpy` 写入目标 UYVY Buffer，布局固定如下：

<div class="camera-pack-layout" role="img" aria-label="四路 Camera 的二乘二 UYVY 载荷布局，上方从左到右是前视和左视，下方从左到右是右视和后视。">
<style>
.camera-pack-layout {
display: grid;
grid-template-columns: repeat(2, minmax(180px, 1fr));
max-width: 720px;
margin: 1.2rem auto 1.5rem;
overflow: hidden;
color: #172033;
border: 2px solid #087f75;
border-radius: 12px;
background: #ffffff;
font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}
.camera-pack-layout > div {
display: flex;
min-height: 118px;
flex-direction: column;
align-items: center;
justify-content: center;
padding: 14px;
border: 1px solid #8bcfc7;
background: #e8f7f4;
text-align: center;
}
.camera-pack-layout strong { color: #075f58; font-size: 16px; }
.camera-pack-layout small { margin-top: 7px; color: #5d6879; font-size: 11px; }
.dark .camera-pack-layout { color: #e6edf7; border-color: #2db8aa; background: #1a2230; }
.dark .camera-pack-layout > div { border-color: #247d74; background: #123b39; }
.dark .camera-pack-layout strong { color: #9be4dc; }
.dark .camera-pack-layout small { color: #aeb9c9; }
</style>
<div><strong>Front</strong><small>x: 0–1919 · y: 0–1535</small></div>
<div><strong>Left</strong><small>x: 1920–3839 · y: 0–1535</small></div>
<div><strong>Right</strong><small>x: 0–1919 · y: 1536–3071</small></div>
<div><strong>Rear</strong><small>x: 1920–3839 · y: 1536–3071</small></div>
</div>

这一步没有读取标定参数，也没有调用几何投影、鱼眼畸变校正、曝光补偿、接缝查找或融合算法。因此，`3840×3072 UYVY` 是四路画面的承载格式，不应直接称为最终鸟瞰图。若量产界面存在俯视投影、车模叠加或无缝融合，这部分实现位于当前提供源码之外的 AVM 应用或专有渲染模块中。

### 7.2 同步与缺帧策略

- 启动后的前 5 次检查要求 ready bitmap 为 `0x0F`，即四路均有新帧；否则跳过输出。
- 进入稳态后，只要至少一路产生新帧，缺失方向可以复用该方向最近一次有效 Buffer index。
- 输出事件中的 bit 0、1、2、3 分别表示前、后、左、右方向在本次输出中是否有新帧。
- 复用缓存让整条 stream 在单路短时缺帧时继续运行，但用户可能看到某一个象限冻结，而其他象限仍更新。
- 如果四路都不再产生回调，合成线程没有新的触发源，四合一输出也会停止更新。

## 8. 跨 VM 接口设计

### 8.1 控制协议

Camera 前后端通过 HAB 建立控制通道。协议命令包括 `OPEN`、`CLOSE`、`START`、`STOP` 和 `ALLOCBUFS`。控制请求采用请求/应答模式；当前连接封装的同步接收超时为 3000 ms。

`START` 阶段还会建立两条单向工作通道：PVM 到 GVM 的帧通知通道，以及 GVM 到 PVM 的 Buffer 归还通道。把通知与归还拆开，可避免生产者和消费者在同一消息队列上互相阻塞。

### 8.2 数据协议

跨 VM 不逐帧复制约 22.5 MiB 的像素到 HAB 消息。数据面采用一次建立、多次复用的共享 Buffer：

1. GVM 的 `cFeCamera` 分配 GraphicBuffer，取得 DMA-BUF fd。
2. GVM 调用 HAB export，得到每个 Buffer 的 `exportId`，通过 `ALLOCBUFS` 发给 PVM。
3. PVM `cV4qCamera` 调用 `cHabConnect::habImport` 并映射同一组物理页，再通过 `SetOutputBuffers` 登记输出 Buffer。
4. PVM 把四合一 UYVY 像素直接写入目标共享 Buffer。
5. PVM 发送 `WORK_GET_FRAME`，消息只包含 `idx`、`frameId` 和 `timestamp`。
6. GVM 用同一个 `idx` 向 V4L2 capture 队列提交 Buffer。
7. V4L2/EVS 完成消费后，GVM 发送 `WORK_RELEASE_FRAME(idx)`。
8. PVM 只有在收到归还后，才应把该 index 放回可写队列。

### 8.3 Hypervisor 的职责边界

Gunyah 和 HAB 负责 VM 隔离、共享页映射、doorbell/虚拟中断和消息搬运，不参与四路同步、像素拼接或 UYVY 到 NV21 的颜色格式转换。图像算法分别运行在 PVM Camera 中间件和 GVM EVS HAL/应用侧。

## 9. GVM Android Camera 架构

GVM 的消费链路遵循 Android Automotive EVS 分层：

1. AVM 或 EVS 客户端通过 `CarEvsManager` 请求 `SERVICE_TYPE_SURROUNDVIEW`。
2. `CarEvsService` 负责访问仲裁和状态机；其 JNI `EvsServiceContext` 对 `/dev/video*` 请求选择 `IEvsEnumerator/v4q`。
3. `evsmanagerd_v4q` 提供该管理实例，并连接 `android.hardware.automotive.evs-v4q` 提供的 `IEvsEnumerator/hw/0`。
4. HAL 内的 `EvsEnumerator` 根据配置枚举虚拟 V4L2 Camera，并创建 `EvsV4lCamera`。
5. `VideoCapture` 打开 `/dev/video61`，使用 MMAP/DMA-BUF 和 `VIDIOC_STREAMON`、`DQBUF`、`QBUF` 驱动采集循环。
6. `EvsV4lCamera` 把 UYVY 共享帧转换或复制到 EVS 客户端 GraphicBuffer；目标为 `YCRCB_420_SP` 时选择 UYVY 到 NV21 的转换函数，也可以走 C2D 加速路径。
7. HAL 通过 AIDL `deliverFrame` 交付 `BufferDesc`，经 `evsmanagerd_v4q` 到 CarService；JNI 从 native handle 构建 `HardwareBuffer`，Java 状态机再将 `CarEvsBufferDescriptor` 回调给应用。该过程传递句柄和元数据，不通过 Binder 复制完整像素。
8. 应用显示完成后调用 `CarEvsManager.returnFrameBuffer`，归还经 CarService 和 `evsmanagerd_v4q` 向下传递，最终由 HAL 的 `doneWithFrame` 回收 EVS 输出 Buffer。

这里有两套不同的 Buffer 生命周期：底层跨 VM UYVY Buffer 在 EVS 完成转换后即可归还 PVM；上层 EVS 输出 GraphicBuffer 由应用持有，直到应用显式归还。不能把两者的 index 或所有权混为一谈。

## 10. Buffer Ownership 设计

| 状态 | 所有者 | 允许操作 | 状态迁移 |
| --- | --- | --- | --- |
| Exported | GVM 分配，双方已映射 | 尚未写入 | `ALLOCBUFS` 完成后进入 PVM free queue |
| PVM Free | PVM | 可选择为下一帧目标 | 合成线程 dequeue 后进入 PVM Writing |
| PVM Writing | PVM | 仅 PVM 写 UYVY 像素 | 写完并发送 `WORK_GET_FRAME` 后进入 GVM In-flight |
| GVM In-flight | GVM | V4L2/EVS 只读和转换；PVM 不应覆盖 | GVM 发送 `WORK_RELEASE_FRAME` 后回到 PVM Free |
| EVS Client In-flight | Android 应用 | 显示或处理 EVS 输出 Buffer | 应用 `returnFrameBuffer` 经 EVS 管理链触发 HAL `doneWithFrame`，回到 EVS HAL 空闲池 |

实现定义了默认 300 ms 的输出 Buffer watchdog。当 GVM 超时未归还时，watchdog 可以把对应 index 重新放回 PVM 输出队列；迟到的归还事件按 stale event 处理。该状态迁移属于异常恢复覆盖，不改变正常路径必须由 `WORK_RELEASE_FRAME` 归还所有权的接口契约。

## 11. 部署架构与接口映射

### 11.1 运行组件

| VM | 运行组件 | 配置/设备入口 | 架构角色 |
| --- | --- | --- | --- |
| PVM | `v4q_be_server` | 逻辑设备 `/dev/v4q/hyp_camera/4avm` | Camera 后端、四路聚合、HAB producer |
| PVM | `qcxserver` | `qcx_server.service` | 物理 Camera request、ISP 配置与采集管理 |
| PVM | `vhost-user-qti` | `/dev/vhost-cam` | Camera VirtIO 后端队列配置 |
| GVM | `ais_v4l2_proxy_qcc6` | `/dev/video61` | HAB consumer、V4L2 虚拟 Camera Proxy |
| GVM | `android.hardware.automotive.evs-v4q` | `IEvsEnumerator/hw/0` | V4L2 capture、格式转换、EVS Buffer 管理 |
| GVM | `evsmanagerd_v4q` | `IEvsEnumerator/v4q` | 连接 CarService 与硬件 HAL，转发 stream 和 Buffer 生命周期 |
| GVM | `CarEvsService` | Car Service Binder API | Camera service 仲裁与应用接口 |

### 11.2 HAB 通道映射

| 通道 | PVM 方向 | GVM 方向 | 传递内容 |
| --- | --- | --- | --- |
| Command `91` | request/response | request/response | `OPEN`、`CLOSE`、`START`、`STOP`、`ALLOCBUFS` |
| Work `92` | send | receive | `WORK_GET_FRAME(index, frameId, timestamp)` |
| Work `93` | receive | send | `WORK_RELEASE_FRAME(index)` |

### 11.3 4AVM 部署参数

| 参数 | 配置值 | 架构含义 |
| --- | --- | --- |
| Physical inputs | Front `8`、Rear `9`、Left `10`、Right `11` | 四路 QCarCam input |
| Single input | `1920×1536 UYVY` | ISP 后单路输入格式 |
| Aggregated output | `3840×3072 UYVY` | PVM 四合一共享载荷 |
| Shared output buffers | `5` | PVM/GVM 跨 VM Buffer 池 |
| OneFrame type | `4` | 2×2 四路布局 |
| GVM EVS output | `3840×3072 YCRCB_420_SP` | Android 客户端目标格式 |

## 12. 接口契约与设计约束

### 12.1 Camera 控制契约

| 命令 | 发起方 | 接收方 | 作用 |
| --- | --- | --- | --- |
| `OPEN` | GVM | PVM | 创建后端 Camera 实例并打开 V4Q 设备 |
| `ALLOCBUFS` | GVM | PVM | 传递 export id、Buffer 数量、大小和对齐信息 |
| `START` | GVM | PVM | 建立帧通知/归还通道并启动四路 QCarCam stream |
| `STOP` | GVM | PVM | 停止新帧生产和跨 VM 提交 |
| `CLOSE` | GVM | PVM | 解除 Buffer import/export 并销毁 Camera 实例 |

### 12.2 帧传输契约

| 消息 | 必要字段 | 所有权变化 |
| --- | --- | --- |
| `WORK_GET_FRAME` | `idx`、`frameId`、`timestamp` | PVM → GVM |
| `WORK_RELEASE_FRAME` | `idx` | GVM → PVM |

图像像素不进入上述消息体。消息中的 `idx` 指向初始化阶段建立的共享 Buffer 池，双方必须对 Buffer 数量、大小、格式和 index 范围保持一致。

### 12.3 架构不变量

- 当前 4AVM 跨 VM Buffer 池固定为 5 个，`nExport` 和所有 Buffer index 必须落在协议容量内。
- PVM 只能写处于 `PVM Free` 或 `PVM Writing` 状态的共享 Buffer。
- GVM 收到 `WORK_GET_FRAME` 后只读该共享 Buffer，并在底层 V4L2/EVS 消费完成后归还。
- PVM 四合一 UYVY Buffer 与 EVS 客户端 GraphicBuffer 是两个独立的 Buffer domain，具有不同的 index 和生命周期。
- `3840×3072 UYVY` 是四路图像载荷容器，不代表已经完成鸟瞰几何合成。
- 停止时必须先阻止新帧进入，再回收在途 Buffer，最后解除 HAB 映射和 Camera stream。

### 12.4 异常与恢复边界

- 单路暂时缺帧时，聚合器可以使用该方向最近一次有效帧维持四合一输出。
- 四路均无新帧时，聚合器不产生新的共享输出帧。
- GVM 未及时归还 Buffer 时，PVM 输出池会逐步耗尽；实现中的输出 Buffer watchdog 属于超时恢复路径，不属于正常所有权转移流程。
- EVS 客户端持有全部输出 Buffer 时，EVS HAL 可以跳过新帧，以保持服务线程不被应用永久阻塞。

## 13. 源码实现映射

为避免记录本机绝对路径，以下使用 `PVM Tree`、`GVM Tree`、`GVM Kernel Source`、`PVM Camera Source` 和 `GVM Camera Source` 作为目录别名。

| 架构组件 | 实现位置 |
| --- | --- |
| PVM 部署配置与后端程序 | `PVM Tree/<camera-recipe>/files/` |
| 四路 Camera 配置 | `PVM Tree/<camera-recipe>/files/configfile/v4q/avm4OneFrame.xml` |
| PVM HAB 通道配置 | `PVM Tree/<camera-recipe>/files/configfile/v4q_be_server.xml` |
| `v4q::v4q_QcarcamOneframe` | `PVM Camera Source/v4q/v4q_Components/v4q_QcarcamOneframe/` |
| `hyp_camera::cV4qCamera` | `PVM Camera Source/camera_fe/hyp_camera/v4q_be_server/src/cV4qCamera.cpp` |
| `hyp_camera::cHabConnect` | `PVM Camera Source/camera_fe/hyp_common/hab_connect/cHabConnect.cpp` |
| `qcarcam_wrap_*` | `PVM Camera Source/qcarcamwrap/src/qcarcam_wrap.cpp` |
| `libqcxclient.so`、`qcxserver` | `PVM Tree/vendor/qcom/proprietary/qcx/build/lrh/qcx/`、`PVM Tree/vendor/qcom/proprietary/qcx/servicefiles/qcx_server.service` |
| PVM Camera 硬件访问 | `PVM Tree/vendor/qcom/proprietary/qcx/platformmanager/linux_lrh/src/`、`PVM Tree/vendor/qcom/opensource/safelinux-cfg-modules/safelinux-modules/Kbuild` |
| PVM `msm_hab.ko`、`vhost-user-qti` | `PVM Tree/vendor/qcom/opensource/mmhab-drv/`、`PVM Tree/vendor/qcom/opensource/vhost-user/vhost-user-cam.service` |
| HAB 公共协议 | `PVM Camera Source/camera_fe/hyp_common/`、`GVM Camera Source/camcorder_fe/hyp_common/` |
| GVM V4L2 Proxy 配置与程序 | `GVM Tree/<camera-vendor>/v4qhal/` |
| GVM Camera HAB Front-end | `GVM Camera Source/camcorder_fe/hyp_camera/v4q_v4l2_proxy/` |
| GVM EVS V4L2 HAL | `GVM Camera Source/camcorder_fe/v4qhal/` |
| `evsmanagerd_v4q` | `GVM Tree/packages/services/Car/cpp/evs/manager/aidl_v4q/` |
| GVM `ais-v4l2loopback.ko` | `GVM Kernel Source/common/drivers/ais-v4l2loopback/` |
| GVM `msm_hab.ko` | `GVM Kernel Source/soc-repo/drivers/soc/qcom/hab/` |
| Android Car EVS Framework | `GVM Tree/packages/services/Car/car-lib/`、`GVM Tree/packages/services/Car/service/` |

正式树中的部署配置和运行二进制定义实际部署边界；配套 Camera 源码用于展开组件内部控制流。本文的架构边界、接口和数据格式均以正式部署配置为准。
