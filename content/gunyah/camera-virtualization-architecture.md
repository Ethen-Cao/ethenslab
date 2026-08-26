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

<div class="camera-arch-scroll">
<style>
.camera-arch-scroll {
max-width: 100%;
margin: 1.4rem 0 1.8rem;
overflow-x: auto;
padding: 0.25rem 0 0.75rem;
}
.camera-arch-template {
--cat-ink: #172033;
--cat-muted: #5d6879;
--cat-line: #d7dee8;
--cat-surface: #ffffff;
--cat-canvas: #f6f8fb;
--cat-pvm: #087f75;
--cat-pvm-soft: #e8f7f4;
--cat-gvm: #2563b8;
--cat-gvm-soft: #edf4ff;
--cat-hv: #7551b7;
--cat-hv-soft: #f3effb;
--cat-hw: #b56816;
--cat-hw-soft: #fff5e7;
--cat-data: #0d9488;
--cat-control: #64748b;
box-sizing: border-box;
min-width: 980px;
padding: 22px;
color: var(--cat-ink);
border: 1px solid var(--cat-line);
border-radius: 16px;
background:
linear-gradient(180deg, rgba(255,255,255,0.92), rgba(246,248,251,0.96)),
repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(148,163,184,0.08) 32px);
box-shadow: 0 14px 36px rgba(23, 32, 51, 0.08);
font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}
.camera-arch-template *,
.camera-arch-template *::before,
.camera-arch-template *::after {
box-sizing: border-box;
}
.cat-titlebar {
display: flex;
align-items: flex-end;
justify-content: space-between;
gap: 24px;
margin-bottom: 18px;
padding: 0 4px;
}
.cat-titlebar h3 {
margin: 0;
color: var(--cat-ink);
font-size: 22px;
line-height: 1.25;
}
.cat-titlebar p {
margin: 5px 0 0;
color: var(--cat-muted);
font-size: 12px;
}
.cat-legend {
display: flex;
flex-wrap: wrap;
justify-content: flex-end;
gap: 12px;
color: var(--cat-muted);
font-size: 11px;
white-space: nowrap;
}
.cat-legend-item {
display: inline-flex;
align-items: center;
gap: 6px;
}
.cat-legend-line {
display: inline-block;
width: 26px;
border-top: 3px solid var(--cat-data);
}
.cat-legend-line.control {
border-top: 2px dashed var(--cat-control);
}
.cat-layer {
position: relative;
padding: 18px;
border: 2px solid var(--cat-line);
border-radius: 13px;
background: var(--cat-surface);
}
.cat-layer.vm {
border-color: #aab7c8;
}
.cat-layer.hypervisor {
border-color: var(--cat-hv);
background: var(--cat-hv-soft);
}
.cat-layer.hardware {
border-color: var(--cat-hw);
background: var(--cat-hw-soft);
}
.cat-layer-heading {
display: flex;
align-items: center;
gap: 11px;
margin-bottom: 14px;
}
.cat-layer-heading strong {
display: block;
font-size: 16px;
line-height: 1.2;
}
.cat-layer-heading small {
display: block;
margin-top: 3px;
color: var(--cat-muted);
font-size: 11px;
font-weight: 500;
}
.cat-vm-grid {
display: grid;
grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
gap: 18px;
}
.cat-vm {
overflow: hidden;
border: 2px solid;
border-radius: 12px;
background: var(--cat-surface);
}
.cat-vm.pvm {
border-color: var(--cat-pvm);
}
.cat-vm.gvm {
border-color: var(--cat-gvm);
}
.cat-vm-header {
display: flex;
align-items: center;
justify-content: space-between;
gap: 12px;
min-height: 58px;
padding: 12px 15px;
}
.cat-vm.pvm .cat-vm-header {
color: #075f58;
background: var(--cat-pvm-soft);
}
.cat-vm.gvm .cat-vm-header {
color: #174a8b;
background: var(--cat-gvm-soft);
}
.cat-vm-name {
font-size: 18px;
font-weight: 800;
}
.cat-vm-subtitle {
display: block;
margin-top: 2px;
font-size: 10px;
font-weight: 600;
opacity: 0.78;
}
.cat-vm-role {
padding: 4px 8px;
border: 1px solid currentColor;
border-radius: 999px;
font-size: 10px;
font-weight: 700;
}
.cat-stack {
padding: 13px;
}
.cat-tier {
display: grid;
grid-template-columns: 118px minmax(0, 1fr);
min-height: 68px;
overflow: hidden;
border: 1px solid var(--cat-line);
border-radius: 9px;
background: #ffffff;
}
.cat-tier-label {
display: flex;
flex-direction: column;
justify-content: center;
padding: 10px 11px;
color: var(--cat-ink);
border-right: 1px solid var(--cat-line);
background: #f3f6f9;
font-size: 11px;
font-weight: 800;
line-height: 1.3;
}
.cat-tier-label small {
margin-top: 3px;
color: var(--cat-muted);
font-size: 9px;
font-weight: 600;
}
.cat-tier-nodes {
display: flex;
flex-wrap: wrap;
align-content: center;
align-items: center;
gap: 7px;
padding: 9px;
}
.cat-node {
min-width: 116px;
flex: 1 1 116px;
padding: 7px 8px;
color: var(--cat-ink);
border: 1px solid var(--cat-line);
border-radius: 7px;
background: #ffffff;
font-size: 10px;
font-weight: 700;
line-height: 1.28;
text-align: center;
}
.cat-node small {
display: block;
margin-top: 3px;
color: var(--cat-muted);
font-size: 8.7px;
font-weight: 500;
}
.cat-vm.pvm .cat-node.emphasis {
color: #075f58;
border-color: #8bcfc7;
background: var(--cat-pvm-soft);
}
.cat-vm.gvm .cat-node.emphasis {
color: #174a8b;
border-color: #9bbce6;
background: var(--cat-gvm-soft);
}
.cat-flow-down {
position: relative;
height: 20px;
color: var(--cat-control);
font-size: 9px;
line-height: 20px;
text-align: center;
}
.cat-flow-down::before {
content: "";
position: absolute;
top: 0;
bottom: 4px;
left: 50%;
border-left: 2px solid #9aa7b8;
}
.cat-flow-down::after {
content: "";
position: absolute;
bottom: 1px;
left: calc(50% - 4px);
width: 8px;
height: 8px;
border-right: 2px solid #9aa7b8;
border-bottom: 2px solid #9aa7b8;
transform: rotate(45deg);
}
.cat-boundary {
margin-top: 16px;
padding: 12px;
border: 1px dashed #8b9aab;
border-radius: 10px;
background: #f8fafc;
}
.cat-boundary-title {
margin-bottom: 9px;
color: var(--cat-muted);
font-size: 10px;
font-weight: 800;
letter-spacing: 0.08em;
text-align: center;
text-transform: uppercase;
}
.cat-boundary-grid {
display: grid;
grid-template-columns: 1fr 1.25fr 1fr;
align-items: stretch;
gap: 10px;
}
.cat-boundary-end,
.cat-boundary-contract {
display: flex;
min-height: 58px;
flex-direction: column;
align-items: center;
justify-content: center;
padding: 9px;
border-radius: 8px;
font-size: 10px;
font-weight: 800;
line-height: 1.35;
text-align: center;
}
.cat-boundary-end.pvm {
color: #075f58;
border: 1px solid #8bcfc7;
background: var(--cat-pvm-soft);
}
.cat-boundary-end.gvm {
color: #174a8b;
border: 1px solid #9bbce6;
background: var(--cat-gvm-soft);
}
.cat-boundary-contract {
position: relative;
color: #4b3a72;
border: 1px solid #b9a6dd;
background: var(--cat-hv-soft);
}
.cat-boundary-contract::before,
.cat-boundary-contract::after {
content: "↔";
position: absolute;
top: 50%;
color: var(--cat-hv);
font-size: 17px;
transform: translateY(-50%);
}
.cat-boundary-contract::before {
left: -16px;
}
.cat-boundary-contract::after {
right: -16px;
}
.cat-boundary-end small,
.cat-boundary-contract small {
display: block;
margin-top: 3px;
color: var(--cat-muted);
font-size: 8.8px;
font-weight: 500;
}
.cat-layer-connector {
position: relative;
display: grid;
height: 54px;
place-items: center;
}
.cat-layer-connector::before {
content: "";
position: absolute;
top: 0;
bottom: 9px;
left: 50%;
border-left: 3px solid #8795a7;
}
.cat-layer-connector::after {
content: "";
position: absolute;
bottom: 6px;
left: calc(50% - 6px);
width: 12px;
height: 12px;
border-right: 3px solid #8795a7;
border-bottom: 3px solid #8795a7;
transform: rotate(45deg);
}
.cat-layer-connector span {
z-index: 1;
padding: 3px 9px;
color: var(--cat-muted);
border: 1px solid var(--cat-line);
border-radius: 999px;
background: var(--cat-canvas);
font-size: 9px;
font-weight: 700;
}
.cat-hv-grid {
display: grid;
grid-template-columns: repeat(3, minmax(0, 1fr));
gap: 12px;
}
.cat-hv-box {
min-height: 105px;
padding: 13px;
border: 1px solid #b9a6dd;
border-radius: 9px;
background: rgba(255,255,255,0.82);
}
.cat-hv-box strong {
display: block;
margin-bottom: 7px;
color: #55398a;
font-size: 12px;
}
.cat-hv-box ul {
margin: 0;
padding-left: 17px;
color: var(--cat-muted);
font-size: 9.5px;
line-height: 1.55;
}
.cat-hw-flow {
display: grid;
grid-template-columns: 1fr 34px 1fr 34px 1fr 34px 1fr;
align-items: center;
gap: 4px;
}
.cat-hw-box {
display: flex;
min-height: 92px;
flex-direction: column;
align-items: center;
justify-content: center;
padding: 12px;
border: 1px solid #e0b06d;
border-radius: 9px;
background: rgba(255,255,255,0.88);
text-align: center;
}
.cat-hw-box strong {
color: #8d4d0d;
font-size: 12px;
}
.cat-hw-box small {
margin-top: 5px;
color: var(--cat-muted);
font-size: 9px;
line-height: 1.35;
}
.cat-hw-arrow {
color: var(--cat-hw);
font-size: 22px;
font-weight: 800;
text-align: center;
}
.cat-footnote {
margin: 14px 3px 0;
color: var(--cat-muted);
font-size: 9px;
line-height: 1.45;
}
.dark .camera-arch-template {
--cat-ink: #e6edf7;
--cat-muted: #aeb9c9;
--cat-line: #445064;
--cat-surface: #1a2230;
--cat-canvas: #141b27;
--cat-pvm-soft: #123b39;
--cat-gvm-soft: #172f52;
--cat-hv-soft: #2d2444;
--cat-hw-soft: #3b2a18;
background: #111827;
box-shadow: none;
}
.dark .camera-arch-template .cat-tier,
.dark .camera-arch-template .cat-node,
.dark .camera-arch-template .cat-hv-box,
.dark .camera-arch-template .cat-hw-box {
background: #1d2735;
}
.dark .camera-arch-template .cat-tier-label,
.dark .camera-arch-template .cat-boundary {
background: #222d3d;
}
.dark .camera-arch-template .cat-vm.pvm .cat-vm-header,
.dark .camera-arch-template .cat-vm.pvm .cat-node.emphasis,
.dark .camera-arch-template .cat-boundary-end.pvm {
color: #9be4dc;
}
.dark .camera-arch-template .cat-vm.gvm .cat-vm-header,
.dark .camera-arch-template .cat-vm.gvm .cat-node.emphasis,
.dark .camera-arch-template .cat-boundary-end.gvm {
color: #a9cbf5;
}
</style>

<div class="camera-arch-template" role="img" aria-label="虚拟化 Camera 三层架构图：VM 层包含左侧 PVM 和右侧 Android GVM，中间是 Hypervisor 层，底部是 Camera Hardware 层。">
<div class="cat-titlebar">
<div>
<h3>Virtualized Camera Architecture</h3>
<p>Application → Framework / Service → Virtualization → Hypervisor → Hardware</p>
</div>
<div class="cat-legend" aria-label="连线图例">
<span class="cat-legend-item"><i class="cat-legend-line"></i>图像数据 / Buffer</span>
<span class="cat-legend-item"><i class="cat-legend-line control"></i>控制 / 事件 / 所有权</span>
</div>
</div>

<section class="cat-layer vm">
<div class="cat-layer-heading">
<div>
<strong>VM Layer</strong>
<small>PVM 位于左侧，GVM 位于右侧；两个 VM 内部均按应用到内核的顺序排列</small>
</div>
</div>

<div class="cat-vm-grid">
<article class="cat-vm pvm">
<header class="cat-vm-header">
<div>
<span class="cat-vm-name">PVM</span>
<span class="cat-vm-subtitle">Linux Primary Virtual Machine</span>
</div>
<span class="cat-vm-role">设备与 Camera 数据生产侧</span>
</header>

<div class="cat-stack">
<div class="cat-tier">
<div class="cat-tier-label">应用 / 服务层<small>Applications & Services</small></div>
<div class="cat-tier-nodes">
<div class="cat-node emphasis">v4q_be_server<small>OPEN / ALLOC / START / STOP</small></div>
<div class="cat-node">Camera Diagnostics<small>链路、帧率与健康监控</small></div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">Camera Framework<small>Middleware</small></div>
<div class="cat-tier-nodes">
<div class="cat-node">V4Q Device Model<small>节点、状态与生命周期</small></div>
<div class="cat-node emphasis">QCarCam OneFrame<small>四路收帧与 2×2 组合</small></div>
<div class="cat-node">Output Buffer Pool<small>index 与所有权管理</small></div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">平台中间件<small>Platform Camera</small></div>
<div class="cat-tier-nodes">
<div class="cat-node emphasis">QCarCam Wrapper / API<small>四路 stream 与 frame callback</small></div>
<div class="cat-node">QCX Camera Service<small>ISP use case、request 与恢复</small></div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">虚拟化后端<small>Back-end Service</small></div>
<div class="cat-tier-nodes">
<div class="cat-node emphasis">Camera HAB Back-end<small>command / frame / release channel</small></div>
<div class="cat-node">Imported Shared Buffers<small>写入 GVM 导出的 GraphicBuffer</small></div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">Linux 内核<small>Kernel & Drivers</small></div>
<div class="cat-tier-nodes">
<div class="cat-node">Sensor / CSI / IFE Driver</div>
<div class="cat-node">HABMM / DMA-BUF / IOMMU</div>
</div>
</div>
</div>
</article>

<article class="cat-vm gvm">
<header class="cat-vm-header">
<div>
<span class="cat-vm-name">GVM</span>
<span class="cat-vm-subtitle">Android Guest Virtual Machine</span>
</div>
<span class="cat-vm-role">Android Camera 数据消费侧</span>
</header>

<div class="cat-stack">
<div class="cat-tier">
<div class="cat-tier-label">应用层<small>Applications</small></div>
<div class="cat-tier-nodes">
<div class="cat-node emphasis">AVM / EVS Client<small>预览、交互与显示</small></div>
<div class="cat-node">CarEvsGLSurfaceView<small>Buffer 消费与归还示例</small></div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">应用框架层<small>Application Framework</small></div>
<div class="cat-tier-nodes">
<div class="cat-node emphasis">CarEvsManager / CarEvsService<small>Surround-view 类型与访问仲裁</small></div>
<div class="cat-node">Binder / AIDL Contract<small>配置、stream 与 buffer callback</small></div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">Native / HAL<small>System Services</small></div>
<div class="cat-tier-nodes">
<div class="cat-node">EvsEnumerator</div>
<div class="cat-node emphasis">EvsV4lCamera<small>V4L2 capture 与 UYVY 转换</small></div>
<div class="cat-node">VideoCapture / Gralloc</div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">Vendor Service<small>Virtual Camera Proxy</small></div>
<div class="cat-tier-nodes">
<div class="cat-node emphasis">v4q_v4l2_proxy<small>HAB event ↔ VIDIOC_QBUF/DQBUF</small></div>
<div class="cat-node">cFeCamera / HAB Front-end<small>export buffer / receive frame</small></div>
</div>
</div>
<div class="cat-flow-down" aria-hidden="true"></div>

<div class="cat-tier">
<div class="cat-tier-label">Android 内核<small>Linux Kernel</small></div>
<div class="cat-tier-nodes">
<div class="cat-node">/dev/videoX · V4L2 Loopback</div>
<div class="cat-node">HAB Front-end · DMA-BUF / IOMMU</div>
</div>
</div>
</div>
</article>
</div>

<div class="cat-boundary">
<div class="cat-boundary-title">Cross-VM Camera Contract</div>
<div class="cat-boundary-grid">
<div class="cat-boundary-end pvm">PVM Producer<small>写共享 Buffer，发送 frame-ready index</small></div>
<div class="cat-boundary-contract">HAB + Shared DMA-BUF<small>消息传元数据；共享内存承载图像；显式归还所有权</small></div>
<div class="cat-boundary-end gvm">GVM Consumer<small>V4L2 入队、EVS 消费，再发送 release index</small></div>
</div>
</div>
</section>

<div class="cat-layer-connector"><span>虚拟通道 · 共享内存 · 中断注入</span></div>

<section class="cat-layer hypervisor">
<div class="cat-layer-heading">
<div>
<strong>Hypervisor Layer</strong>
<small>Gunyah 提供 VM 隔离、内存映射与虚拟设备基础；HAB 承载 Camera 跨 VM 协议</small>
</div>
</div>

<div class="cat-hv-grid">
<div class="cat-hv-box">
<strong>控制面与帧通知</strong>
<ul>
<li>OPEN / CLOSE / START / STOP / ALLOC</li>
<li>GET_FRAME(index, timestamp)</li>
<li>RELEASE_FRAME(index)</li>
</ul>
</div>
<div class="cat-hv-box">
<strong>共享内存数据面</strong>
<ul>
<li>GVM 导出 GraphicBuffer / DMA-BUF</li>
<li>PVM 导入并映射同一组物理页</li>
<li>像素不放入逐帧 HAB 消息</li>
</ul>
</div>
<div class="cat-hv-box">
<strong>隔离与资源管理</strong>
<ul>
<li>Stage-2 地址空间与 IOMMU 映射</li>
<li>VM 中断、Doorbell 与共享页权限</li>
<li>Camera 设备、内存和带宽资源分区</li>
</ul>
</div>
</div>
</section>

<div class="cat-layer-connector"><span>设备访问 · DMA · IRQ · IOMMU</span></div>

<section class="cat-layer hardware">
<div class="cat-layer-heading">
<div>
<strong>Hardware Layer</strong>
<small>图像从 Sensor 经串行链路、CSI 与 ISP 进入系统内存，再由 PVM Camera 栈接管</small>
</div>
</div>

<div class="cat-hw-flow">
<div class="cat-hw-box">
<strong>Camera Sensors</strong>
<small>Front · Rear · Left · Right<br>RAW / YUV source</small>
</div>
<div class="cat-hw-arrow">→</div>
<div class="cat-hw-box">
<strong>SerDes + MIPI CSI-2</strong>
<small>远距离视频链路<br>同步、聚合与传输</small>
</div>
<div class="cat-hw-arrow">→</div>
<div class="cat-hw-box">
<strong>ISP / IFE + Camera DMA</strong>
<small>采集、格式化、时间戳<br>写入 Camera Buffer</small>
</div>
<div class="cat-hw-arrow">→</div>
<div class="cat-hw-box">
<strong>DDR / IOMMU / IRQ</strong>
<small>共享物理页、地址转换<br>与完成中断</small>
</div>
</div>
</section>

<p class="cat-footnote">主图只展示稳定边界和职责；部署相关的通道号、设备节点、Buffer 数量、格式和性能阈值在正文中说明。</p>
</div>
</div>

## 3. 分层组件设计

### 3.1 PVM Camera 子系统

| 层级 | 组件 | 架构职责 |
| --- | --- | --- |
| 应用/服务 | `v4q_be_server` | 接收 GVM 的 Camera 生命周期请求，创建 HAB 通道并管理跨 VM Camera 实例 |
| Framework/Middleware | V4Q Device Model | 抽象 Camera 节点、设备状态、输入输出 Buffer 与事件回调 |
| Framework/Middleware | QCarCam OneFrame | 管理前、后、左、右四路输入，选择有效帧并生成四合一输出 |
| Platform Camera | QCarCam Wrapper | 配置 QCarCam input、注册 Buffer、启动 stream 并取得 frame index/timestamp |
| Platform Camera | QCX Camera Service | 管理 ISP use case、Camera request、硬件错误与恢复事件 |
| 虚拟化后端 | Camera HAB Back-end | 导入 GVM Buffer，发送帧通知并接收 Buffer 归还事件 |
| Linux Kernel | HABMM、DMA-BUF、IOMMU、Camera Driver | 提供共享内存映射、地址转换、Camera DMA 与设备访问 |

PVM 是 Camera 数据生产侧，也是物理 Camera 的唯一所有者。四路输入和跨 VM 输出均由 PVM Camera 子系统统一调度。

### 3.2 GVM Camera 子系统

| Android 层级 | 组件 | 架构职责 |
| --- | --- | --- |
| Applications | AVM/EVS Client | 请求 surround-view stream、消费并归还 EVS Buffer |
| Application Framework | `CarEvsManager`、`CarEvsService` | 提供应用 API、访问仲裁和 Camera service 状态机 |
| Native/HAL | `EvsEnumerator`、`EvsV4lCamera` | 枚举虚拟 Camera，管理 EVS stream 和客户端 GraphicBuffer |
| Native/HAL | `VideoCapture`、C2D/Buffer Copy | 从 V4L2 取帧并完成 UYVY 到客户端格式的转换 |
| Vendor Service | V4L2 Proxy、`cFeCamera` | 分配并导出共享 Buffer，把 HAB 帧事件转换为 V4L2 queue 操作 |
| Android Kernel | V4L2 Loopback、HAB Front-end | 向 EVS HAL 暴露 `/dev/videoX`，连接跨 VM 共享 Buffer 数据面 |

GVM 是 Camera 数据消费侧。物理 Camera 的差异被收敛在 V4L2 Proxy 以下，上层保持 Android Automotive EVS 的标准接口模型。

### 3.3 Hypervisor Layer

Hypervisor 层提供 VM 隔离、共享页映射、doorbell/虚拟中断以及 HAB 通信基础。它只承载 Camera 控制消息、帧元数据和共享内存映射，不执行四路同步、像素拼接或颜色格式转换。

### 3.4 Hardware Layer

Hardware 层由 Camera Sensor、Serializer/Deserializer、MIPI CSI-2、ISP/IFE、Camera DMA 和 DDR 组成。图像由 Camera DMA 写入 PVM 可访问的输入 Buffer，随后进入 PVM Camera 软件栈。

## 4. Camera 生命周期与时序设计

### 4.1 启动与 Buffer 建立

1. GVM 应用通过 EVS 请求 Camera stream。
2. GVM Camera HAL 打开 V4L2 节点并申请 capture Buffer。
3. GVM Camera Proxy 分配 GraphicBuffer，并通过 HAB 导出共享内存句柄和 `exportId`。
4. PVM Camera 后端导入并映射这些 Buffer，把它们登记为跨 VM 输出池；4 路 QCarCam 输入也使用共享分配的输入池。
5. PVM Camera 后端创建帧通知通道和归还通道，再启动四路物理 Camera stream。

### 4.2 稳态帧传输

1. Camera Hardware 经 ISP/IFE 和 DMA 产生多路图像。
2. PVM Camera Framework 获取各路输入；多 Camera 场景可先完成同步、布局或合成。
3. PVM 将结果写入 GVM 导出的共享 Buffer，然后发送 `GET_FRAME(index, timestamp)`。
4. GVM Camera Proxy 根据 index 向 V4L2 loopback capture 路径执行 `QBUF`，EVS HAL 再通过 `DQBUF` 取帧。
5. EVS HAL 将图像转换或复制到应用 Buffer，并把底层 V4L2 Buffer 重新入队。
6. GVM Camera Proxy收到 Buffer 可回收事件后发送 `RELEASE_FRAME(index)`。
7. PVM 将对应 index 放回输出空闲队列。

### 4.3 停止与释放

停止顺序应与启动相反：先停止上层消费和新帧提交，再等待在途 Buffer 返回，最后解除 HAB export/import、V4L2 Buffer 和 QCarCam stream。若先解除共享内存而仍有 frame callback 或 release event 在途，会产生越界访问、重复归还或关闭超时。

## 5. PVM 采集架构

### 5.1 数据源

AVM 的原始画面来自前、后、左、右四路车外 Camera。配置把四路 QCarCam input id 分别绑定到四个方向；每一路先经 SerDes 和 CSI 进入 ISP/IFE，再由 QCarCam 输出到 PVM 内存。因此，数据生产者是 PVM 所拥有的物理 Camera 子系统，Android GVM 只是共享帧的消费者。

PVM Camera 输入契约从 ISP 输出开始，格式定义为 UYVY。Sensor 在线缆上的信号格式、SerDes 虚拟通道编排和 ISP 内部 pipeline 参数属于 Hardware/Platform Camera 的下层配置，不进入本架构接口。

### 5.2 PVM 采集

`QCarCam OneFrame` 打开四个 input，每路配置为最终输出宽、高的一半，即 `1920×1536`。`QCarCam Wrapper` 为每一路建立一组输入 Buffer，向 QCarCam 注册后启动 stream；frame callback 通过返回的 Buffer index 和 timestamp 标记对应方向的新帧已经到达。

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

PVM `StitchingThread` 将四路矩形图像组织为 2×2 载荷。每个象限通过逐行 `memcpy` 写入目标 UYVY Buffer，布局固定如下：

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
3. PVM 调用 HAB import，将同一组物理页映射进 PVM 地址空间，并把这些地址注册为 V4Q 输出 Buffer。
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
2. `CarEvsService` 负责访问仲裁、状态机以及 EVS service 的 Binder/AIDL 连接。
3. `EvsEnumerator` 根据配置枚举虚拟 V4L2 Camera，并创建 `EvsV4lCamera`。
4. `VideoCapture` 打开 V4L2 节点，使用 MMAP/DMA-BUF 和 `VIDIOC_STREAMON`、`DQBUF`、`QBUF` 驱动采集循环。
5. `EvsV4lCamera` 把 UYVY 共享帧转换或复制到 EVS 客户端 GraphicBuffer；目标为 `YCRCB_420_SP` 时选择 UYVY 到 NV21 的转换函数，也可以走 C2D 加速路径。
6. EVS 通过 AIDL `deliverFrame` 把 BufferDescriptor 交给客户端；客户端显示完成后调用 `returnFrameBuffer`/`doneWithFrame` 归还 EVS 输出 Buffer。

这里有两套不同的 Buffer 生命周期：底层跨 VM UYVY Buffer 在 EVS 完成转换后即可归还 PVM；上层 EVS 输出 GraphicBuffer 由应用持有，直到应用显式归还。不能把两者的 index 或所有权混为一谈。

## 10. Buffer Ownership 设计

| 状态 | 所有者 | 允许操作 | 状态迁移 |
| --- | --- | --- | --- |
| Exported | GVM 分配，双方已映射 | 尚未写入 | `ALLOCBUFS` 完成后进入 PVM free queue |
| PVM Free | PVM | 可选择为下一帧目标 | 合成线程 dequeue 后进入 PVM Writing |
| PVM Writing | PVM | 仅 PVM 写 UYVY 像素 | 写完并发送 `WORK_GET_FRAME` 后进入 GVM In-flight |
| GVM In-flight | GVM | V4L2/EVS 只读和转换；PVM 不应覆盖 | GVM 发送 `WORK_RELEASE_FRAME` 后回到 PVM Free |
| EVS Client In-flight | Android 应用 | 显示或处理 EVS 输出 Buffer | 应用 `doneWithFrame` 后回到 EVS HAL 空闲池 |

实现定义了默认 300 ms 的输出 Buffer watchdog。当 GVM 超时未归还时，watchdog 可以把对应 index 重新放回 PVM 输出队列；迟到的归还事件按 stale event 处理。该状态迁移属于异常恢复覆盖，不改变正常路径必须由 `WORK_RELEASE_FRAME` 归还所有权的接口契约。

## 11. 部署架构与接口映射

### 11.1 运行组件

| VM | 运行组件 | 配置/设备入口 | 架构角色 |
| --- | --- | --- | --- |
| PVM | `v4q_be_server` | `/dev/v4q/hyp_camera/4avm` | Camera 后端、四路聚合、HAB producer |
| GVM | `ais_v4l2_proxy_qcc6` | `/dev/video61` | HAB consumer、V4L2 虚拟 Camera Proxy |
| GVM | `android.hardware.automotive.evs-v4q` | EVS AIDL service | V4L2 capture、格式转换、EVS Buffer 管理 |
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

为避免记录本机绝对路径，以下使用 `PVM Tree`、`GVM Tree`、`PVM Camera Source` 和 `GVM Camera Source` 作为目录别名。

| 架构组件 | 实现位置 |
| --- | --- |
| PVM 部署配置与后端程序 | `PVM Tree/<camera-recipe>/files/` |
| 四路 Camera 配置 | `PVM Tree/<camera-recipe>/files/configfile/v4q/avm4OneFrame.xml` |
| PVM HAB 通道配置 | `PVM Tree/<camera-recipe>/files/configfile/v4q_be_server.xml` |
| QCarCam OneFrame | `PVM Camera Source/v4q/v4q_Components/v4q_QcarcamOneframe/` |
| PVM Camera HAB Back-end | `PVM Camera Source/camera_fe/hyp_camera/v4q_be_server/` |
| HAB 公共协议 | `PVM Camera Source/camera_fe/hyp_common/`、`GVM Camera Source/camcorder_fe/hyp_common/` |
| GVM V4L2 Proxy 配置与程序 | `GVM Tree/<camera-vendor>/v4qhal/` |
| GVM Camera HAB Front-end | `GVM Camera Source/camcorder_fe/hyp_camera/v4q_v4l2_proxy/` |
| GVM EVS V4L2 HAL | `GVM Camera Source/camcorder_fe/v4qhal/` |
| Android Car EVS Framework | `GVM Tree/packages/services/Car/car-lib/`、`GVM Tree/packages/services/Car/service/` |

正式树中的部署配置和运行二进制定义实际部署边界；配套 Camera 源码用于展开组件内部控制流。本文的架构边界、接口和数据格式均以正式部署配置为准。
