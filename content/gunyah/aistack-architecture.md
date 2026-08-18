+++
date = '2026-08-18T10:00:00+08:00'
draft = false
title = 'AI Stack 架构解析（SA8397 双虚拟机平台实测）'
categories = ['Qualcomm', 'AI', 'QNN', 'FastRPC', '虚拟化']
tags = ['SA8397', 'QNN', 'FastRPC', 'HTP', 'NPU', 'qcrosvm', 'GVM', 'PVM', 'debug']
+++

# AI Stack 架构解析（SA8397 双虚拟机平台实测）

> 本文所有内容来自真机实测：Android GVM（`adb -s d7df5883 shell`，`SA8397 Cockpit`）与 Linux PVM（`adb -s e66b06ea shell`，`Linux sa8797 6.6.110-rt61-debug PREEMPT_RT`）。组件名、路径、进程参数均为实采值；涉及 OEM 的组件名已脱敏。

## 1. 软件架构总图

图中实线箭头为**请求数据流**（自上而下），虚线箭头为**应答/控制流**（自下而上）。

<div style="max-width:100%;overflow-x:auto;">
<svg viewBox="0 0 1240 940" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="aistack-architecture-title" style="display:block;width:100%;height:auto;min-width:900px;font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
  <title id="aistack-architecture-title">SA8397 双虚拟机 AI Stack 架构图</title>
  <rect width="1240" height="940" fill="#ffffff"/>
  <defs>
    <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#374151"/>
    </marker>
    <marker id="arrDash" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#9ca3af"/>
    </marker>
    <marker id="arrBlue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#1d4ed8"/>
    </marker>
  </defs>
  <!-- ===== 列标题 ===== -->
  <text x="150" y="34" text-anchor="middle" font-size="16" font-weight="bold" fill="#0f6b43">PVM · Linux 6.6.110-rt61 PREEMPT_RT（sa8797）</text>
  <text x="1090" y="34" text-anchor="middle" font-size="16" font-weight="bold" fill="#1d4ed8">GVM · Android 16（SA8397 Cockpit）</text>
  <!-- ===== PVM 左子列 ===== -->
  <g>
    <rect x="30" y="52" width="250" height="66" rx="6" fill="#e8f7ef" stroke="#0f6b43" stroke-width="1.5"/>
    <text x="155" y="72" text-anchor="middle" font-size="13" font-weight="bold" fill="#0f6b43">AI 服务层（本地推理）</text>
    <text x="155" y="90" text-anchor="middle" font-size="11" fill="#374151">qcxserver / oms_main / AIService</text>
    <text x="155" y="105" text-anchor="middle" font-size="11" fill="#374151">libarcsoft_qnnhtp.so</text>
    <rect x="30" y="146" width="250" height="56" rx="6" fill="#ffffff" stroke="#0f6b43" stroke-width="1.2"/>
    <text x="155" y="166" text-anchor="middle" font-size="12" font-weight="bold">QNN 库 / FastRPC 客户端</text>
    <text x="155" y="184" text-anchor="middle" font-size="11" fill="#374151">/usr/lib/libQnnHtp.so · libcdsprpc.so</text>
    <rect x="30" y="230" width="250" height="56" rx="6" fill="#ffffff" stroke="#0f6b43" stroke-width="1.2"/>
    <text x="155" y="250" text-anchor="middle" font-size="12" font-weight="bold">LRM 消息队列</text>
    <text x="155" y="268" text-anchor="middle" font-size="11" fill="#374151">/dev/shm/lrmc_rq_* / lrmc_sq_*</text>
  </g>
  <!-- ===== PVM 右子列 ===== -->
  <g>
    <rect x="310" y="52" width="250" height="66" rx="6" fill="#e8f7ef" stroke="#0f6b43" stroke-width="1.5"/>
    <text x="435" y="72" text-anchor="middle" font-size="13" font-weight="bold" fill="#0f6b43">vhost-user-frpc（GVM 后端）</text>
    <text x="435" y="90" text-anchor="middle" font-size="11" fill="#374151">/usr/bin/vhost-user-frpc</text>
    <text x="435" y="105" text-anchor="middle" font-size="11" fill="#374151">-s /tmp/sock_file_frpc</text>
    <rect x="310" y="146" width="250" height="56" rx="6" fill="#ffffff" stroke="#0f6b43" stroke-width="1.2"/>
    <text x="435" y="166" text-anchor="middle" font-size="12" font-weight="bold">fastrpc-rm（资源管理）</text>
    <text x="435" y="184" text-anchor="middle" font-size="11" fill="#374151">PD 注册/反注册 · 上下文 · 在途 RPC 跟踪</text>
  </g>
  <!-- ===== PVM 共享下层 ===== -->
  <g>
    <rect x="30" y="330" width="530" height="56" rx="6" fill="#ffffff" stroke="#0f6b43" stroke-width="1.5"/>
    <text x="295" y="350" text-anchor="middle" font-size="13" font-weight="bold">glink_service_lrm（GLink 传输）</text>
    <text x="295" y="368" text-anchor="middle" font-size="11" fill="#374151">-s adsp0/cdsp0/cdsp1/adsp1/adsp2/cdsp2/cdsp3（7 子系统）</text>
    <rect x="30" y="414" width="530" height="56" rx="6" fill="#f3f4f6" stroke="#0f6b43" stroke-width="1.2"/>
    <text x="295" y="434" text-anchor="middle" font-size="13" font-weight="bold">PVM 内核驱动</text>
    <text x="295" y="452" text-anchor="middle" font-size="11" fill="#374151">umd_glink（irq/352-357）· scmi_nsp0~3 · umd_nsp_drv · nsp_sysmon</text>
  </g>
  <!-- ===== GVM 列 ===== -->
  <g>
    <rect x="660" y="52" width="560" height="66" rx="6" fill="#eaf1fd" stroke="#1d4ed8" stroke-width="1.5"/>
    <text x="940" y="72" text-anchor="middle" font-size="13" font-weight="bold" fill="#1d4ed8">AI 应用层</text>
    <text x="940" y="90" text-anchor="middle" font-size="11" fill="#374151">语音 AI 应用（ASR/NLU 多模型并发）· ADAS 感知应用</text>
    <text x="940" y="105" text-anchor="middle" font-size="11" fill="#374151">libasr_inference.so · libfaiss.so 等（包名/库名已脱敏）</text>
    <rect x="660" y="146" width="560" height="56" rx="6" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.5"/>
    <text x="940" y="166" text-anchor="middle" font-size="12" font-weight="bold">qnnx · QNN 执行引擎</text>
    <text x="940" y="184" text-anchor="middle" font-size="11" fill="#374151">/vendor/bin/qnn · libQnnHtp.so · libQnnHtpV81Stub.so · libQnnHtpPrepare.so</text>
    <rect x="660" y="230" width="560" height="56" rx="6" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.2"/>
    <text x="940" y="250" text-anchor="middle" font-size="12" font-weight="bold">FastRPC 客户端</text>
    <text x="940" y="268" text-anchor="middle" font-size="11" fill="#374151">libcdsprpc.so（remote_handle64_invoke / ioctl_invoke）</text>
    <rect x="660" y="314" width="560" height="56" rx="6" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.2"/>
    <text x="940" y="334" text-anchor="middle" font-size="12" font-weight="bold">FastRPC 设备节点</text>
    <text x="940" y="352" text-anchor="middle" font-size="11" fill="#374151">/dev/fastrpc-nsp1000 ~ nsp1003（4×NPU）· /dev/fastrpc-cdsp[1]</text>
    <rect x="660" y="398" width="560" height="50" rx="6" fill="#f3f4f6" stroke="#1d4ed8" stroke-width="1.2"/>
    <text x="940" y="418" text-anchor="middle" font-size="12" font-weight="bold">hfastrpc 驱动（platform + misc）</text>
    <text x="940" y="435" text-anchor="middle" font-size="11" fill="#374151">/sys/class/misc/hfastrpc</text>
    <rect x="660" y="476" width="560" height="50" rx="6" fill="#fef3c7" stroke="#b45309" stroke-width="1.2"/>
    <text x="940" y="496" text-anchor="middle" font-size="12" font-weight="bold">virtio9 → hfastrpc（vhost-user-frpc 虚拟设备）</text>
    <text x="940" y="512" text-anchor="middle" font-size="11" fill="#92400e">FastRPC 请求的虚拟化出口</text>
  </g>
  <!-- ===== Hypervisor ===== -->
  <rect x="30" y="620" width="1190" height="66" rx="6" fill="#f6f2ff" stroke="#7c3aed" stroke-width="2"/>
  <text x="625" y="642" text-anchor="middle" font-size="14" font-weight="bold" fill="#7c3aed">Hypervisor · qcrosvm（--vm=autoghgvm）</text>
  <text x="625" y="662" text-anchor="middle" font-size="11" fill="#4b5563">--vhost-user-frpc /tmp/sock_file_frpc,label=45 ｜ --vhost-user-glinkpassthrough ｜ --vhost-user-hab（disp/aud/vid/cam…）｜ --vhost-user-scmi ｜ --vsock cid=100</text>
  <!-- ===== Hardware ===== -->
  <rect x="30" y="736" width="1190" height="120" rx="6" fill="#fffbf2" stroke="#d97706" stroke-width="2"/>
  <text x="625" y="758" text-anchor="middle" font-size="14" font-weight="bold" fill="#d97706">Hardware · Qualcomm SA8397（sa8797）</text>
  <rect x="60" y="772" width="360" height="68" rx="5" fill="#ffffff" stroke="#d97706"/>
  <text x="240" y="794" text-anchor="middle" font-size="12" font-weight="bold" fill="#b45309">4 × NPU（NSP0~NSP3，HTP V81）</text>
  <text x="240" y="812" text-anchor="middle" font-size="11" fill="#6b7280">scmi_nsp0~3 电源/配置 · nsp_sysmon 监控</text>
  <rect x="450" y="772" width="360" height="68" rx="5" fill="#ffffff" stroke="#d97706"/>
  <text x="630" y="794" text-anchor="middle" font-size="12" font-weight="bold" fill="#b45309">DSP 子系统（7 个）</text>
  <text x="630" y="812" text-anchor="middle" font-size="11" fill="#6b7280">adsp0/1/2（音频）· cdsp0/1/2/3（计算）</text>
  <rect x="840" y="772" width="350" height="68" rx="5" fill="#ffffff" stroke="#d97706"/>
  <text x="1015" y="794" text-anchor="middle" font-size="12" font-weight="bold" fill="#b45309">互连</text>
  <text x="1015" y="812" text-anchor="middle" font-size="11" fill="#6b7280">GLink / SMEM · SAIL mailbox</text>
  <!-- ===== GVM 请求流（实线向下） ===== -->
  <line x1="940" y1="118" x2="940" y2="146" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrBlue)"/>
  <line x1="940" y1="202" x2="940" y2="230" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrBlue)"/>
  <line x1="940" y1="286" x2="940" y2="314" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrBlue)"/>
  <line x1="940" y1="370" x2="940" y2="398" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrBlue)"/>
  <line x1="940" y1="448" x2="940" y2="476" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrBlue)"/>
  <!-- ===== GVM virtio9 → Hypervisor ===== -->
  <line x1="940" y1="526" x2="940" y2="620" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrBlue)"/>
  <text x="952" y="578" font-size="11" fill="#1d4ed8">virtio 请求 ▼</text>
  <!-- ===== Hypervisor → PVM vhost-user-frpc ===== -->
  <path d="M 600 620 L 600 85 L 560 85" fill="none" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrBlue)"/>
  <text x="612" y="380" font-size="11" fill="#1d4ed8" transform="rotate(90 612 380)">vhost-user socket</text>
  <text x="626" y="380" font-size="11" fill="#1d4ed8" transform="rotate(90 626 380)">/tmp/sock_file_frpc</text>
  <!-- ===== PVM frpc 路径 ===== -->
  <line x1="435" y1="118" x2="435" y2="146" stroke="#0f6b43" stroke-width="2" marker-end="url(#arr)"/>
  <line x1="435" y1="202" x2="435" y2="330" stroke="#0f6b43" stroke-width="2" marker-end="url(#arr)"/>
  <line x1="435" y1="386" x2="435" y2="414" stroke="#0f6b43" stroke-width="2" marker-end="url(#arr)"/>
  <!-- ===== PVM 本地路径 ===== -->
  <line x1="155" y1="118" x2="155" y2="146" stroke="#0f6b43" stroke-width="2" marker-end="url(#arr)"/>
  <line x1="155" y1="202" x2="155" y2="230" stroke="#0f6b43" stroke-width="2" marker-end="url(#arr)"/>
  <path d="M 155 286 L 155 310 L 295 310 L 295 330" fill="none" stroke="#0f6b43" stroke-width="2" marker-end="url(#arr)"/>
  <!-- ===== PVM 内核 → DSP 子系统 ===== -->
  <path d="M 390 470 L 390 708 L 630 708 L 630 772" fill="none" stroke="#0f6b43" stroke-width="2" marker-end="url(#arr)"/>
  <text x="407" y="520" font-size="11" fill="#0f6b43" transform="rotate(90 407 520)">GLink / SMEM</text>
  <!-- ===== 应答流（虚线向上，右缘） ===== -->
  <line x1="1195" y1="620" x2="1195" y2="52" stroke="#9ca3af" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrDash)"/>
  <text x="1206" y="340" font-size="11" fill="#6b7280" transform="rotate(90 1206 340)">应答/回调（signal · notification）</text>
  <!-- ===== 控制流（虚线） ===== -->
  <line x1="560" y1="414" x2="560" y2="772" stroke="#9ca3af" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrDash)"/>
  <text x="572" y="600" font-size="11" fill="#6b7280">SCMI 电源管理（nsp0~3）</text>
  <line x1="610" y1="202" x2="630" y2="202" stroke="#9ca3af" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrDash)"/>
  <text x="618" y="194" font-size="11" fill="#6b7280">PD 生命周期协作</text>
</svg>
</div>

## 2. 数据流总览

**一次 NPU 推理的完整往返**（按真机组件、设备节点和进程边界整理）：

```text
[请求] GVM 应用 → libQnnHtp.so → libQnnHtpV81Stub.so → libcdsprpc.so
       → ioctl(/dev/fastrpc-nsp100X) → hfastrpc 驱动 → virtio9
       → qcrosvm（vhost-user-frpc 设备，label 45）
       → PVM vhost-user-frpc 守护 → fastrpc-rm → glink_service_lrm
       → umd_glink 驱动 → GLink/SMEM → NSP（HTP）执行
[应答] NSP 结果经 GLink 原路返回，GVM 侧由 callback 线程收包
       （dspsignal_wait / notif_fastrpc_thread）
```

**PVM 本地推理路径**（不经过 GVM）：`qcxserver 等 → libQnnHtp/libcdsprpc → LRM 消息队列（/dev/shm/lrmc_*）→ glink_service_lrm → umd_glink → DSP`。

**资源释放路径**：应用释放 QNN graph/context → `libcdsprpc.so` 销毁 FastRPC context/domain → GVM `hfastrpc` 经 virtio 通知 PVM `vhost-user-frpc` → `fastrpc-rm` 反注册 PD 和上下文 → `glink_service_lrm` 通知 DSP 回收远端资源。释放路径与请求路径方向相反，并需要两侧共同确认完成。

## 3. 组件工作原理

### 3.1 qnnx · QNN 执行引擎（GVM）

- **作用**：模型的加载、编译与执行调度。应用层把 ONNX/自研模型交给 QNN，QNN 把图编译为 HTP 可执行二进制并调度到 NPU。
- **工作原理**：
  - 应用通过 QNN API 或上层模型封装创建 backend、device、context 和 graph，并提交输入/输出 tensor；
  - `libQnnHtp.so` 负责 HTP 后端管理（图编译、上下文、profiling），`libQnnHtpV81Stub.so` 是与 DSP 通信的桩，最终所有 RPC 经 `libcdsprpc.so` 发出；
  - 设备选择最终落到 FastRPC domain：一个进程可以同时连接 `/dev/fastrpc-nsp1000~1003`，但 graph 如何分配到四颗 NSP 由应用配置、QNN backend 策略和平台资源策略共同决定；
  - 另有 `libQnnHtpPrepare.so`（离线编译）、`libQnnHtpProfilingReader.so`（性能采集），以及备用的 CPU/GPU/DSP/HTA 后端库。

### 3.2 libcdsprpc.so（GVM/PVM 两侧均有）

- **作用**：FastRPC 客户端库，应用与 DSP 之间所有 RPC 的统一入口。
- **工作原理**：QNN stub 将远端函数调用编码为 FastRPC invoke，`libcdsprpc.so` 负责句柄、参数封送、设备 ioctl、应答和异步事件分发。一个 domain 中常见三类运行时线程：
  - **Listener/reverse-RPC 线程**：处理 DSP 主动发回的服务请求；
  - **Notification 线程**：接收 PD 状态等异步通知；
  - **Signal/callback 线程**：等待 DSP signal，并唤醒上层队列或回调。
- graph execute、context 管理和 listener 循环都可能经过通用 invoke 入口。基础设施线程负责通信控制面，不代表对应 NSP 正在执行多少个 graph，也不能用线程数量衡量 NPU 负载。

#### 3.2.1 四颗 NSP 与 FastRPC 通道的映射

SA8397 提供四个 HTP/NSP 计算实例。GVM 将它们暴露为四个独立的 FastRPC 设备节点，PVM 则通过对应的 SCMI 节点管理每颗 NSP 的电源、时钟和配置：

| 计算实例 | GVM FastRPC 节点 | PVM 控制节点 | 运行时含义 |
|---|---|---|---|
| NSP0 | `/dev/fastrpc-nsp1000` | `/dev/scmi_nsp0` | 独立的 FastRPC domain、QNN context 和执行资源 |
| NSP1 | `/dev/fastrpc-nsp1001` | `/dev/scmi_nsp1` | 独立的 FastRPC domain、QNN context 和执行资源 |
| NSP2 | `/dev/fastrpc-nsp1002` | `/dev/scmi_nsp2` | 独立的 FastRPC domain、QNN context 和执行资源 |
| NSP3 | `/dev/fastrpc-nsp1003` | `/dev/scmi_nsp3` | 独立的 FastRPC domain、QNN context 和执行资源 |

四颗 NSP 提供的是四条可独立建立 context、提交 graph 和回收资源的执行通道，并不等于系统会自动做全局负载均衡。应用或平台需要明确模型放置、并发上限、优先级和失败隔离策略；QNN/FastRPC 的 listener、notification、signal 线程只是每条通道的通信配套线程。

### 3.3 hfastrpc 驱动（GVM 内核）

- **作用**：GVM 内的 FastRPC 虚拟设备驱动。应用打开的 `/dev/fastrpc-*` 节点由它实现，RPC 请求打包后经 virtio（virtio9）送出 GVM。
- **工作原理**：GVM 看不到真实 DSP——context 创建/销毁、PD 注册、invoke 和 signal 等 FastRPC 语义都被编码为 virtio 消息交给 Hypervisor。context 销毁或 fd 关闭时，驱动还要与 PVM 后端协同完成 domain 释放，因此这里也是 GVM 与 PVM 生命周期同步的边界。

### 3.4 vhost-user-frpc（PVM）

- **作用**：GVM FastRPC 虚拟设备在 PVM 侧的后端，在虚拟机边界两侧转换 virtio 请求与 PVM FastRPC 操作。
- **工作原理**：上游监听 `/tmp/sock_file_frpc`，由 qcrosvm 以 `label=45` 接入；下游把 invoke、context 和 domain 生命周期请求交给 `fastrpc-rm`，并将处理结果沿 vhost-user socket 返回 GVM。它不直接执行模型，也不直接访问 NSP。

### 3.5 fastrpc-rm（PVM）

- **作用**：FastRPC 资源管理器。管理 Protection Domain（PD）、元数据上下文（mdctx）、在途 RPC 应答。
- **工作原理**：日志前缀 `[FRPC_RM]`。关键动作：`frpc_deregister`（PD 反注册）、`reset_pd_info`（等待在途 RPC 应答后重置）、`frpc_mdctx_remove`（移除元数据上下文并回执 err 码）。

### 3.6 glink_service_lrm（PVM）

- **作用**：GLink 传输服务，PVM 与 7 个 DSP 子系统（adsp0/1/2、cdsp0/1/2/3）之间的唯一通信管道。
- **工作原理**：启动参数 `-s adsp0_0_0_0 -s cdsp0_0_0_0 -s cdsp1_0_0_0 ...` 逐个子系统建立 GLink 通道；向下通过 `umd_glink` 设备与 SMEM 硬件邮箱收发数据；向上同时服务两类客户端——PVM 本地（经 `/dev/shm/lrmc_rq_*` 消息队列）与 GVM（经 vhost-user-frpc）。向 DSP 发信通过 `glink_os_send_interrupt intr(N)` 触发中断。

### 3.7 PVM 本地 AI 服务

- **qcxserver（相机服务）**：进程 fd 实测持有 `/dev/shm/lrmc_rq_*`/`lrmc_sq_*` 消息队列与 `/dev/kiumd`，maps 中加载 `libarcsoft_qnnhtp.so`——相机管线中的 AI 推理（如人脸/场景识别）走 PVM 本地的 QNN→FastRPC→GLink 路径，不经 GVM。
- **oms_main**：乘员监控服务，日志高频输出 ArcSoft 驾驶 AI SDK 推理结果。
- **AIService**（名称已脱敏）：PVM 侧 AI 服务进程。
- **nspconfig_service / nsp_drv**：NPU 配置服务与驱动工具（`nsp_drv` 是唯一持有 `/dev/umd_nsp_drv` 的进程）。

### 3.8 NPU 的电源与配置管理（PVM 内核）

- 4 颗 NPU 通过 SCMI 管理：设备树节点 `scmi_nsp0~scmi_nsp3`，用户态设备 `/dev/scmi_nsp0~3`——电源/时钟/频率控制走 SCMI 通道；
- `nsp_sysmon` 负责 NPU 子系统健康监控（subsystem monitor）；
- `umd_nsp_drv`（10,111）为 NSP 用户态驱动接口。

### 3.9 qcrosvm（Hypervisor）

- **作用**：承载 GVM（`--vm=autoghgvm`）的虚拟机管理器，为 GVM 提供全部虚拟设备。
- **工作原理**：AI 栈相关的是 `--vhost-user-frpc`（FastRPC 虚拟化，label 45）与 `--vhost-user-glinkpassthrough`（GLink 直通）；其余 `--vhost-user-hab`（显示/音频/视频/相机等外设）、`--vhost-user-scmi`（电源管理）、`--vhost-user-ssr`（子系统重启事件）与 AI 栈共同构成完整座舱虚拟化环境。

## 4. 运行观察与调试

### 4.1 分层观察模型

一次推理跨越多个进程、虚拟机和处理器，排查时应沿固定层次定位：

```text
① 应用/模型层（GVM）      model、graph、tensor
② QNN 引擎层（GVM）       backend、context、graph 生命周期
③ FastRPC 用户态（GVM）   remote handle、invoke、signal/notif
④ hfastrpc 驱动（GVM）    设备节点、virtio queue、completion
⑤ Hypervisor（qcrosvm）   vhost-user-frpc 虚拟设备
⑥ FastRPC 后端（PVM）     vhost-user-frpc、fastrpc-rm、PD/domain
⑦ GLink 传输（PVM）       glink_service_lrm、umd_glink
⑧ DSP/NPU（硬件）         HTP 执行、NSP 状态、电源与时钟
```

### 4.2 一次请求如何跨层关联

排查的关键不是先搜索某个错误字符串，而是确认同一次 graph execute 走到了哪一层、在哪个边界失去应答：

| 层次 | 主要关联对象 | 观察内容 |
|---|---|---|
| 应用/QNN | model、graph、context、backend | graph 创建是否成功，execute 是否提交，输入输出 tensor 是否匹配 |
| FastRPC 用户态 | remote handle、domain、设备 fd | 请求落到哪个 `/dev/fastrpc-nsp100X`，invoke 是否发出并收到应答 |
| GVM 驱动 | context、invoke id、virtio queue | ioctl 是否进入 hfastrpc，virtio 请求与 completion 是否配对 |
| Hypervisor/PVM 后端 | vhost-user 连接、context/domain | `/tmp/sock_file_frpc` 是否连通，请求是否到达 `vhost-user-frpc` 和 `fastrpc-rm` |
| GLink/DSP | 子系统名、PD、远端消息 | GLink 通道是否在线，DSP 是否接收请求并返回 completion |
| 电源管理 | `scmi_nsp0~3`、频率和电源状态 | 目标 NSP 是否上电，时钟与性能档位是否符合预期 |

关联时优先使用 context/domain、目标 NSP 和时间窗口。用户态 fd 号与线程号只在单次采样中有效，不应作为跨进程或跨启动的长期标识。

### 4.3 常见问题的分层定位

1. **graph 创建或执行失败**：先检查模型格式、backend 配置和 tensor，再确认 QNN 是否成功创建 context/graph；只有请求已进入 `libcdsprpc.so` 才继续向 FastRPC 层排查。
2. **invoke 延迟异常或无应答**：依次核对 GVM ioctl、virtio queue、`vhost-user-frpc`、`fastrpc-rm` 和 GLink 的请求/完成事件，找出最后一个“请求已到达”的边界。
3. **某颗 NSP 不可用**：确认 graph 实际绑定的 `/dev/fastrpc-nsp100X`，再检查对应 `scmi_nspX` 的电源状态、PD 状态和远端 completion；不要用线程数量推断 NPU 负载。
4. **初始化或释放耗时过长**：分别观察 QNN context、FastRPC domain、PD 和 GLink endpoint 的生命周期，确认创建/销毁操作在 GVM 与 PVM 两侧是否成对完成。
5. **PVM 本地 AI 与 GVM AI 相互影响**：两条路径在 PVM 的 GLink/NSP 资源层汇合，需要同时观察本地 `/dev/shm/lrmc_*` 客户端与 GVM vhost-user 客户端的并发和优先级。

### 4.4 排查命令

```bash
# GVM
adb -s <gvm-serial> shell "ls -l /proc/<pid>/fd | grep fastrpc"  # graph 进程连接了哪些 NSP
adb -s <gvm-serial> shell "cat /proc/<pid>/maps | grep QnnHtp"   # QNN HTP backend/stub 是否加载
adb -s <gvm-serial> shell "ps -T -p <pid>"                       # FastRPC listener/notif/signal 线程
adb -s <gvm-serial> shell "cat /proc/interrupts | grep -i frpc"  # GVM FastRPC/virtio 中断活动

# PVM
adb -s <pvm-serial> shell "ps -ef | grep -E 'frpc|glink|nsp'"   # 后端、资源管理和传输服务
adb -s <pvm-serial> shell "ls -l /proc/<pid>/fd | grep lrmc"    # PVM 本地 AI 的 LRM 队列
adb -s <pvm-serial> shell "ls -l /dev/scmi_nsp*"                # 四颗 NSP 的控制节点
adb -s <pvm-serial> shell "journalctl --since 'HH:MM' | grep -E 'FRPC|glink|nsp'"
```

### 4.5 AI Stack 可靠性设计原则

- **明确资源归属**：model、graph、QNN context、FastRPC domain 和 PD 的创建者同时负责销毁；跨线程或跨进程共享时必须定义所有权和释放顺序。
- **有界等待**：graph execute、context teardown、domain deinit 和远端 completion 都应有 deadline、超时状态和上报路径，避免上层只能无限等待。
- **按 NSP 隔离**：为每颗 NSP 维护独立的健康状态、并发配额和熔断状态。某条 FastRPC domain 异常时，停止向其提交新任务，并按业务等级切换到其他 NSP 或 CPU/GPU 后端。
- **统一资源调度**：GVM AI 与 PVM 本地 AI 最终共享 NSP、GLink 和电源预算；模型放置、优先级和带宽不能只由单个应用决定，应由平台资源策略统一协调。
- **分层恢复**：恢复动作从 graph/context 重建、PD/domain reset、GLink endpoint 重建到虚拟机或整机恢复逐级升级，并明确每一级对其他 AI 业务的影响。
- **端到端可观测性**：至少记录 graph/context 标识、目标 NSP、invoke 开始/完成、vhost-user context、PD/domain 和 GLink 子系统，使一次请求能够跨 GVM、PVM 和 DSP 关联。

## 5. 关键组件速查表

| 组件 | 位置 | 角色 |
|---|---|---|
| qnnx（QNN 执行引擎） | GVM `/vendor/bin/qnn` + `/vendor/lib64/libQnnHtp*` | 模型执行、HTP 后端调度 |
| libcdsprpc.so | GVM `/vendor/lib64/`、PVM `/usr/lib/` | FastRPC 客户端（invoke/signal/notif） |
| hfastrpc 驱动 | GVM 内核（platform + misc，virtio9） | FastRPC 虚拟设备驱动 |
| vhost-user-frpc | PVM `/usr/bin/` | FastRPC vhost-user 后端（domain/context 生命周期） |
| fastrpc-rm | PVM `/usr/bin/` | FastRPC 资源管理（PD/上下文） |
| glink_service_lrm | PVM `/usr/bin/` | GLink 传输（7 个 DSP 子系统） |
| umd_glink / sail-mailbox | PVM 内核 | GLink 与 SAIL 邮箱中断 |
| umd_nsp_drv / scmi_nsp0~3 | PVM 内核 + `/dev` | NPU 驱动与 SCMI 电源/配置 |
| qcrosvm | PVM `/usr/bin/` | Hypervisor（vhost-user-frpc / glinkpassthrough / hab / scmi） |
