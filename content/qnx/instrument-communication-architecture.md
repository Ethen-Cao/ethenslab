+++
date = '2026-09-16T00:00:00+08:00'
draft = false
title = '通用仪表通信架构：QNX、Android 与外域 ECU 的信号链路'
description = '从进程、动态库、操作系统与域控制器边界出发，介绍仪表应用、通信服务、SOME/IP、MCU 通信服务，以及 Android VHAL、CarService 和 App 的协作关系。'
tags = ['QNX', 'Android', 'Instrument Cluster', 'SOME/IP', 'DDS', 'VHAL']
ShowToc = true
TocOpen = false
+++

仪表上的车速、挡位、电量和故障提示，通常不是应用直接从总线读取的结果。车辆信号需要经过域间通信、协议处理、信号适配和进程间分发，最终才进入应用的数据模型与界面。

本文以 **QNX 承载仪表和通信服务、Android 承载座舱应用** 的双系统方案为例，介绍一套去除项目专用命名的参考架构。

> **适用范围**：这是通用化的架构示例，不是所有车型必须采用的标准拓扑。DDS、共享内存、SOME/IP、VSOCK、SPI，以及服务拆分方式都可以按产品替换；图中的名称表示组件职责，不表示固定的可执行文件名、进程数或线程号。
>
> **边界约定**：本文以“座舱域控制器”为系统边界。QNX、Android 和板内 MCU 属于域内；其他域控制器、ECU 属于外域。MCU 不运行在 QNX 进程空间中。若某产品的 MCU 位于域控制器之外，应将其移入外域框，不能仅凭“MCU”这一名称判断归属。

## 1. 总体架构

图从上到下排列应用、通信服务、协议与硬件接口、外域信号源。**实线箭头表示主要的信号上报方向**；为保持清晰，订阅请求、应答、服务发现和反向控制没有全部展开。仪表应用和 Android App 是并行消费者，不是前后串联的关系。

<figure id="instrument-communication-architecture" aria-labelledby="ica-caption">
<style>
#instrument-communication-architecture { margin: 24px 0; }
@media (min-width: 1200px) { #instrument-communication-architecture { width: 1120px; margin-left: calc(50% - 560px); } }
#instrument-communication-architecture .ica-scroll { overflow-x: auto; border: 1px solid #cbd5e1; border-radius: 10px; background: #fff; }
#instrument-communication-architecture svg { display: block; width: 100%; min-width: 1000px; height: auto; background: #fff; }
#instrument-communication-architecture text { fill: #172b45; font-family: system-ui, -apple-system, "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; }
#instrument-communication-architecture .ica-title { font-size: 23px; font-weight: 700; }
#instrument-communication-architecture .ica-head { font-size: 19px; font-weight: 700; }
#instrument-communication-architecture .ica-name { font-size: 17px; font-weight: 600; }
#instrument-communication-architecture .ica-detail { font-size: 14px; fill: #40546b; }
#instrument-communication-architecture .ica-label { font-size: 14px; fill: #1d4e78; }
#instrument-communication-architecture .ica-domain { fill: #f8fafc; stroke: #385e83; stroke-width: 2; }
#instrument-communication-architecture .ica-os { fill: #eff6ff; stroke: #a9bfd5; stroke-width: 1.4; }
#instrument-communication-architecture .ica-android { fill: #f0f9f4; stroke: #aacdb8; stroke-width: 1.4; }
#instrument-communication-architecture .ica-process { fill: #fff; stroke: #7088a1; stroke-width: 1.4; }
#instrument-communication-architecture .ica-library { fill: #fff5e7; stroke: #d6b783; stroke-width: 1; }
#instrument-communication-architecture .ica-module { fill: #f1f5f9; stroke: #c5d0dc; stroke-width: 1; }
#instrument-communication-architecture .ica-external { fill: #fff8f0; stroke: #92734c; stroke-width: 2; }
#instrument-communication-architecture .ica-flow { fill: none; stroke: #245d8d; stroke-width: 2; marker-end: url(#ica-arrow); }
#instrument-communication-architecture .ica-call { fill: none; stroke: #7f632d; stroke-width: 1.6; stroke-dasharray: 5 4; marker-end: url(#ica-call-arrow); }
#instrument-communication-architecture figcaption { margin-top: 10px; font-size: 14px; line-height: 1.7; }
</style>
<div class="ica-scroll" role="region" aria-label="通用仪表通信架构图，窄屏可横向滚动" tabindex="0">
<svg viewBox="0 0 1120 1450" width="1120" height="1450" role="img" aria-labelledby="ica-title ica-desc" xmlns="http://www.w3.org/2000/svg">
<title id="ica-title">通用仪表通信架构与系统边界</title>
<desc id="ica-desc">上方座舱域控制器框包含 QNX、Android 和板内 MCU。QNX 仪表应用进程包含业务模块和通信中间件动态库，通信服务进程经 DDS 共享内存向仪表分发数据，并经跨系统通道向 Android VHAL 分发数据，再由 CarService 向 App 分发。下方外域 ECU 经以太网连接 SOME/IP 服务，或经 CAN 连接板内 MCU。MCU 经 SPI 等接口连接 QNX MCU 通信服务。</desc>
<defs>
<marker id="ica-arrow" viewBox="0 0 10 10" markerWidth="7" markerHeight="7" refX="9" refY="5" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="#245d8d"/></marker>
<marker id="ica-call-arrow" viewBox="0 0 10 10" markerWidth="7" markerHeight="7" refX="9" refY="5" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="#7f632d"/></marker>
</defs>
<text class="ica-title" x="30" y="34">通用仪表通信架构</text>
<text class="ica-detail" x="650" y="32">实线：信号上报　虚线：进程内订阅调用</text>

<!-- 座舱域与 OS 边界 -->
<rect class="ica-domain" x="20" y="60" width="1080" height="1140" rx="12"/>
<text class="ica-head" x="40" y="91">域内：座舱域控制器</text>
<text class="ica-detail" x="715" y="90">同一域内不等于同一 OS 或同一进程</text>
<rect class="ica-os" x="40" y="115" width="630" height="940" rx="9"/>
<text class="ica-head" x="60" y="148">QNX · 仪表与车辆通信</text>
<rect class="ica-android" x="720" y="115" width="360" height="720" rx="9"/>
<text class="ica-head" x="740" y="148">Android · 座舱应用</text>

<!-- 仪表进程：动态库嵌套在进程框内 -->
<rect class="ica-process" x="60" y="170" width="590" height="255" rx="8"/>
<text class="ica-name" x="80" y="198">仪表应用进程（ClusterApp）</text>
<rect class="ica-module" x="80" y="215" width="550" height="70" rx="5"/>
<text class="ica-name" x="355" y="243" text-anchor="middle">仪表界面与业务模块</text>
<text class="ica-detail" x="355" y="266" text-anchor="middle">信号绑定、状态管理、界面更新</text>
<rect class="ica-library" x="80" y="340" width="550" height="65" rx="5"/>
<text class="ica-name" x="355" y="365" text-anchor="middle">通信中间件动态库</text>
<text class="ica-detail" x="355" y="389" text-anchor="middle">订阅 API / DDS · 加载并运行在仪表应用进程内</text>
<path class="ica-flow" d="M175 340 V285"/>
<text class="ica-label" x="190" y="319">数据回调</text>
<path class="ica-call" d="M505 285 V340"/>
<text class="ica-detail" x="520" y="319">订阅</text>

<!-- 通信服务进程 -->
<rect class="ica-process" x="60" y="510" width="590" height="240" rx="8"/>
<text class="ica-name" x="80" y="538">通信服务进程</text>
<rect class="ica-library" x="80" y="555" width="550" height="65" rx="5"/>
<text class="ica-name" x="355" y="580" text-anchor="middle">通信中间件动态库</text>
<text class="ica-detail" x="355" y="604" text-anchor="middle">发布 API / DDS · 运行在通信服务进程内</text>
<path class="ica-flow" d="M355 555 V405"/>
<text class="ica-label" x="370" y="473">DDS / SHM 共享内存 · 跨进程</text>
<rect class="ica-module" x="80" y="665" width="550" height="65" rx="5"/>
<text class="ica-name" x="355" y="691" text-anchor="middle">信号适配与分发</text>
<text class="ica-detail" x="355" y="715" text-anchor="middle">解析、有效性、超时、派生信号、属性映射</text>
<path class="ica-flow" d="M355 665 V620"/>
<text class="ica-label" x="370" y="648">发布数据</text>

<!-- Android 应用链：独立于仪表消费数据 -->
<rect class="ica-process" x="740" y="170" width="320" height="90" rx="6"/>
<text class="ica-name" x="900" y="202" text-anchor="middle">App · Android 应用进程</text>
<text class="ica-detail" x="900" y="229" text-anchor="middle">Car API / CarPropertyManager</text>
<rect class="ica-process" x="740" y="330" width="320" height="90" rx="6"/>
<text class="ica-name" x="900" y="362" text-anchor="middle">CarService · 服务进程</text>
<text class="ica-detail" x="900" y="389" text-anchor="middle">属性服务、权限检查与事件分发</text>
<path class="ica-flow" d="M900 330 V260"/>
<text class="ica-label" x="912" y="300">Binder</text>
<rect class="ica-process" x="740" y="510" width="320" height="100" rx="6"/>
<text class="ica-name" x="900" y="540" text-anchor="middle">VHAL · 车辆 HAL 服务</text>
<text class="ica-detail" x="900" y="565" text-anchor="middle">OEM 后端接入车辆信号</text>
<text class="ica-detail" x="900" y="589" text-anchor="middle">对上提供 Vehicle Property 接口</text>
<path class="ica-flow" d="M900 510 V420"/>
<text class="ica-label" x="912" y="460">AIDL / HIDL</text>
<text class="ica-detail" x="912" y="482">按平台版本</text>
<path class="ica-flow" d="M630 698 H900 V610"/>
<text class="ica-label" x="755" y="747">跨系统通道：VSOCK 等</text>
<text class="ica-detail" x="755" y="772">连接通信服务与 VHAL 后端</text>
<text class="ica-detail" x="755" y="797">是传输适配，不要求另设进程</text>

<!-- 协议服务与网络栈 -->
<rect class="ica-process" x="60" y="820" width="275" height="90" rx="6"/>
<text class="ica-name" x="197" y="850" text-anchor="middle">SOME/IP 服务（someipd）</text>
<text class="ica-detail" x="197" y="874" text-anchor="middle">服务发现、事件订阅与报文收发</text>
<text class="ica-detail" x="197" y="896" text-anchor="middle">VLAN X · 按需部署服务实例</text>
<rect class="ica-process" x="370" y="820" width="280" height="90" rx="6"/>
<text class="ica-name" x="510" y="852" text-anchor="middle">MCU 通信服务</text>
<text class="ica-detail" x="510" y="880" text-anchor="middle">链路管理、帧解析与分发</text>
<path class="ica-flow" d="M197 820 V730"/>
<text class="ica-label" x="208" y="788">本机客户端接口</text>
<path class="ica-flow" d="M510 820 V730"/>
<text class="ica-label" x="521" y="788">帧回调 / IPC</text>
<rect class="ica-process" x="60" y="970" width="275" height="65" rx="6"/>
<text class="ica-name" x="197" y="997" text-anchor="middle">网络协议栈与网卡驱动</text>
<text class="ica-detail" x="197" y="1020" text-anchor="middle">VLAN / UDP / TCP</text>
<path class="ica-flow" d="M197 970 V910"/>
<text class="ica-label" x="208" y="946">SOME/IP 报文</text>

<!-- MCU 位于域控内，但不在 QNX OS 内 -->
<rect class="ica-process" x="370" y="1100" width="280" height="75" rx="6"/>
<text class="ica-name" x="510" y="1130" text-anchor="middle">板内 MCU</text>
<text class="ica-detail" x="510" y="1155" text-anchor="middle">独立固件 / RTOS · 总线信号接入</text>
<path class="ica-flow" d="M510 1100 V910"/>
<text class="ica-label" x="523" y="994">SPI / UART 等</text>
<text class="ica-detail" x="740" y="891">边界层级</text>
<text class="ica-detail" x="740" y="921">域控制器 → OS → 进程 → 动态库</text>
<text class="ica-detail" x="740" y="960">QNX 与 Android 可通过</text>
<text class="ica-detail" x="740" y="986">Hypervisor 等方案隔离。</text>
<text class="ica-detail" x="740" y="1025">板内 MCU 属于同一座舱域，</text>
<text class="ica-detail" x="740" y="1051">但不属于 QNX / Android 进程。</text>

<!-- 外域边界与跨域接口 -->
<rect class="ica-external" x="20" y="1290" width="1080" height="140" rx="12"/>
<text class="ica-head" x="740" y="1320">外域：其他域控制器与 ECU</text>
<rect class="ica-process" x="60" y="1340" width="275" height="65" rx="6"/>
<text class="ica-name" x="197" y="1367" text-anchor="middle">外域 ECU / 域控制器</text>
<text class="ica-detail" x="197" y="1390" text-anchor="middle">SOME/IP 服务端</text>
<rect class="ica-process" x="370" y="1340" width="280" height="65" rx="6"/>
<text class="ica-name" x="510" y="1367" text-anchor="middle">外域 ECU / 网关</text>
<text class="ica-detail" x="510" y="1390" text-anchor="middle">CAN / CAN FD 等总线节点</text>
<text class="ica-detail" x="740" y="1367">示例：车身、底盘、动力等车辆域</text>
<text class="ica-detail" x="740" y="1390">信号源归属按实际整车拓扑确定</text>
<path class="ica-flow" d="M197 1340 V1035"/>
<text class="ica-label" x="210" y="1244">车载以太网</text>
<path class="ica-flow" d="M510 1340 V1175"/>
<text class="ica-label" x="523" y="1244">CAN / CAN FD</text>
</svg>
</div>
<figcaption id="ica-caption">大框区分座舱域内与外域；域内进一步区分 QNX、Android 和 MCU。橙色模块是进程内动态库，不是独立转发进程。图中传输与服务拆分是参考实现，可按平台替换。</figcaption>
</figure>

## 2. 先分清四种边界

| 边界 | 图中示例 | 含义 |
| --- | --- | --- |
| 域控制器边界 | 座舱域与外域 ECU | 通过车载以太网、CAN 等链路交换数据；需要考虑域间协议、网关与信号契约 |
| OS / 执行环境边界 | QNX、Android、MCU 固件 | 需要跨系统或硬件链路适配，不能直接把另一侧的函数当作本进程函数调用 |
| 进程边界 | 仪表应用、通信服务、SOME/IP 服务 | 各自具有进程地址空间，通过 IPC、共享内存等机制协作 |
| 库与业务模块边界 | 仪表进程中的通信中间件动态库 | 库代码运行在调用者所在进程内；函数调用、锁等待和库内部线程都属于该进程 |

**动态库不是额外的一跳服务。** 仪表加载一份通信库，通信服务也加载一份通信库；两端借助底层传输通信，并不意味着二者之间还存在一个名为“通信中间件”的中央代理进程。是否需要代理、发现服务或桥接进程，应以具体部署为准。

图中的 DDS / SHM 表示一种本机进程间发布订阅方案。DDS 是通信模型与协议体系，SHM 是这里选用的本机数据传输方式，两者不是两个必须独立部署的服务。

## 3. 各组件负责什么

### 3.1 仪表应用进程

仪表应用将接收到的车辆状态转换成界面状态，例如挡位、电量、车速和告警图标。通信中间件动态库嵌在该进程内，向业务提供订阅和回调接口。

应用启动时可以注册多个 topic，但以下三个动作不能混为一谈：

1. **本地订阅 API 返回**：订阅对象或接收端已经建立到什么程度，取决于接口契约。
2. **接收到首个有效样本**：需要发布者、连接、数据有效性和缓存策略共同满足条件。
3. **首帧显示更新**：还需要数据绑定、业务队列、UI 调度和渲染链路完成。

因此，“订阅完成”不是“全部信号已经显示”。某个信号没有变化，也不一定意味着订阅尚未建立。

### 3.2 通信服务进程

通信服务位于协议接入与业务消费者之间，典型职责包括：

- 接收 SOME/IP 服务、MCU 通信服务提供的报文或信号。
- 按信号定义解码，处理有效位、超时、默认值和必要的派生计算。
- 将数据发布为 QNX 侧业务 topic。
- 将 Android 需要的数据经跨系统通道提供给 VHAL 后端。

“信号适配”是职责层，不要求所有解码、缓存和属性映射都集中在一个进程中。实际实现可能把部分工作放在协议服务、适配库或 VHAL 后端中。

通信服务通常不是车辆信号的最初生产者；它是域内的接入、转换和分发节点。其他 QNX 应用也可以消费相应 topic，仪表不是唯一消费者。反过来，仪表的所有 topic 也不一定都由这一进程发布。

### 3.3 SOME/IP 服务与网络协议栈

SOME/IP 服务负责面向以太网服务的通信，包括服务发现、事件订阅以及请求、响应和事件报文的收发。QNX 网络协议栈与网卡驱动负责下层网络传输。

图中的 `VLAN X` 是占位表示，**不是要求所有业务共享同一个 VLAN，也不是固定部署若干进程**。一个进程可以处理多项服务，多个实例也可以按网络或业务隔离，取决于中间件实现和项目配置。

仪表订阅本机 topic 与 SOME/IP 订阅外域事件是两个不同层次。它们之间可能有固定配置、缓存、按需订阅或聚合关系，不能直接认为“一个仪表 topic 就对应一次外域订阅请求”。

### 3.4 MCU 通信服务与板内 MCU

MCU 通信服务是运行在 QNX 上的软件进程；板内 MCU 是另一执行环境。前者通过 SPI、UART 等平台链路与后者交换帧，再向通信服务提供数据。

MCU 可以接入 CAN 等车辆总线，也可能处理本地 IO、电源状态或其他板级信号。职责和硬件接口因产品而异。图中的两条输入支路并不意味着同一信号一定同时经以太网和 MCU 重复上报。

### 3.5 Android VHAL、CarService 与 App

Android 的车辆信号消费路径与 QNX 仪表并行：

**通信服务 → 跨系统通道 → VHAL → CarService → App。**

- **VHAL**：OEM 后端把平台信号接入 Android 车辆属性接口；对上提供属性的读取、写入和订阅能力。VSOCK 只是后端传输的一个选项，不是 VHAL 标准接口的硬性要求。
- **CarService**：在 Android 侧提供车辆相关服务，进行权限检查和事件分发；图中只展开与车辆属性相关的路径。
- **App**：通过 Car API（例如 `CarPropertyManager`）访问获准使用的车辆属性，而不是直接订阅外域 SOME/IP 事件。

VHAL 对上接口应按系统版本与实际部署选择 AIDL 或 HIDL，不能将跨系统传输协议与 VHAL 接口混为一谈。相关接口边界见 [AOSP VHAL 概述](https://source.android.com/docs/automotive/vhal)；应用属性访问与回调接口见 [CarPropertyManager 文档](https://developer.android.com/reference/android/car/hardware/property/CarPropertyManager)。

## 4. 三条主要数据路径

### 路径 A：外域以太网信号进入仪表

外域 ECU 产生数据 → 车载以太网 → QNX 网络协议栈 → SOME/IP 服务 → 通信服务处理信号 → 本机发布订阅传输 → 仪表进程内通信库回调 → 业务模型 → UI 更新。

### 路径 B：车辆总线信号经 MCU 进入仪表

外域 ECU / 网关 → CAN 等车辆总线 → 板内 MCU → SPI 等板级链路 → QNX MCU 通信服务 → 通信服务 → 仪表应用。

### 路径 C：同一车辆状态进入 Android

通信服务 → 跨系统适配 → Android VHAL 后端 → Vehicle Property 事件 → CarService → App 回调 → Android UI 更新。

三条路径可以共享部分上游数据，但订阅时机、缓存、有效性处理、更新策略和 UI 调度可能不同。因此 Android 正常显示某个值，只能说明它对应的路径可用，**不能单独证明仪表路径也已完成初始化**。

反向控制则由获授权的应用发起，经服务校验和协议转换到达目标 ECU。它不一定机械地沿上报路径完全反向执行，仍应以控制信号契约和安全策略为准。

## 5. 用这张图定位“订阅慢”与“显示慢”

不要只记录一个“订阅开始到结束”的总时间。建议把一次数据可见过程拆成几个观察点：

| 观察点 | 建议记录内容 | 能回答的问题 |
| --- | --- | --- |
| 应用启动与订阅 | 单调时钟、进程/线程标识、topic、调用开始/结束、返回值 | 慢在批量循环，还是某个订阅调用？ |
| 中间件连接 | 发布者匹配、端点创建、IPC/锁等待、重连 | 本地接收端是否就绪？卡在何种等待？ |
| 上游协议输入 | SOME/IP 事件或 MCU 帧、序号、到达时间 | 外部数据是否已经进入域内？ |
| 通信服务输出 | topic、有效性、样本时间、发布序号 | 服务收到数据后是否及时发布？ |
| 消费端回调 | 接收序号、排队时间、处理开始/结束 | 数据是否已经到达应用但还在队列里？ |
| 界面更新 | 数据模型变更、UI 任务、帧提交/呈现 | 慢在通信、业务处理还是绘制？ |

时间开销优先使用同一系统的单调时钟计算；跨 QNX、Android 和 MCU 对齐时，需要时钟关联或序号，不要直接相减未经同步的时间戳。

### 为什么总 CPU 高不足以解释全部问题？

高负载可能延长执行时间，但要证明它是某次等待的原因，还需要关键线程的运行态和调度证据：

- 线程已经就绪却长时间得不到运行，才直接支持“调度资源不足”的解释。
- 线程在等锁、信号量、IPC 应答或连接就绪，需要继续确认等待对象与负责推进它的线程。
- 两类问题可以叠加：持锁线程或服务线程得不到运行，也会放大其他线程的阻塞。

不同信号可能使用不同的服务实例、队列、更新模式、超时策略和 UI 任务，所以负载问题不要求所有信号同时异常；同样，局部异常也不能反向证明 CPU 一定无关。

### 重启的结果如何解释？

重启某个通信服务后恢复，只能说明重启改变了有关状态，例如连接、缓存、队列或锁的生命周期。它是定位线索，不是根因证明。应先保留问题现场，再比较各边界的输入、输出和等待状态，不宜把网络栈、全部通信服务和仪表一起重启后，就认定其中某个组件有问题。

## 6. 通用化时保留什么，去掉什么

- 保留职责、进程归属、OS 边界和跨域链路。
- 不把某次运行的线程号、PID、订阅数量或耗时写成架构常量。
- 使用“通信中间件动态库”“通信服务进程”“MCU 通信服务”等职责名称，避免依赖项目内部命名。
- 用 `VLAN X`、SPI / UART、VSOCK 等示例表达可替换的部署选择。
- 将动态库画进调用者的进程框，而不是伪装成独立服务。
- 对每个产品重新核对 MCU 的硬件归属、QNX / Android 的部署方式，以及是否存在额外网关、桥接或安全处理通路。

这张图最重要的用途，是把“谁产生数据、谁转换数据、谁传输数据、谁订阅并显示数据”分开，并让每一步都能对应到可检查的边界。
