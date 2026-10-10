+++
date = '2026-07-29T00:00:00+08:00'
draft = false
title = 'PVM 图形栈架构（SA8797 / Gunyah）'
tags = ["Qualcomm", "SA8797", "Graphics", "Weston", "Wayland", "OpenWFD", "VirtIO-GPU", "Gunyah", "PVM"]
+++

本文描述 SA8797 座舱平台 Primary VM（PVM）的显示架构、OpenWFD 资源划分、LA-GVM（Android Guest）显示通路以及抓帧边界。结论由 PVM 源码、镜像配置与台架运行态交叉验证。

> 核验基线：设备 `e8cc24da`，`auto-oem_a 202607262327`，Linux `6.6.110-rt61-debug`（PREEMPT_RT，aarch64），Weston `13.0.1`。  
> 运行态采集日期：2026-07-29。VFIO group 编号、PID 等动态标识不作为固定接口。

## 1. 架构总览

PVM 上存在两条相互独立的显示提交路径：

- PVM 原生应用通过 Wayland 向 Weston 提交 surface。Weston 使用 SDM 选择 GPU 合成或 overlay，再经 DRM Front End（DRM-FE）和 OpenWFD 客户端协议提交。
- LA-GVM 的显示帧经 VirtIO/HAB 到达 `VirtIOGPU2DBackendService`，由该进程以独立 OpenWFD 客户端身份提交，不进入 Weston 的 scene graph。

两条路径最终由 `openwfd_server -i 0/1` 按静态配置的 Port、Pipeline 和 z-order 汇合。OpenWFD Server 直接持有 KIUMD、VFIO 与 SCMI MDSS 设备，是 PVM 中面向 DPU 硬件的服务端。

<iframe id="pvm-graphics-architecture" src="../../diagrams/pvm-graphics-stack-architecture.html" title="SA8797 PVM 图形栈：软件分层、依赖关系与数据流" loading="lazy" style="display:block;box-sizing:border-box;width:100%;height:900px;min-height:560px;border:1px solid #dadce0;border-radius:8px;overflow:hidden;"></iframe>
<script>
(() => {
  const frame = document.getElementById('pvm-graphics-architecture');
  if (!frame) return;
  const frameOrigin = new URL(frame.src, document.baseURI).origin;
  window.addEventListener('message', event => {
    if (event.source !== frame.contentWindow || event.origin !== frameOrigin || event.data?.type !== 'pvm-graphics-architecture-height') return;
    const height = event.data.height;
    if (Number.isFinite(height) && height > 0) {
      frame.style.height = Math.max(560, Math.min(2400, Math.ceil(height) + 2)) + 'px';
    }
  });
})();
</script>

[独立打开架构图](../../diagrams/pvm-graphics-stack-architecture.html)

主图自上而下按应用、图形框架与帧管理、客户端适配、用户态显示服务、内核接口和硬件分层；横向区分 PVM 与 LA-GVM。Weston 和 Guest 显示后端是并列进程，各自内嵌 OpenWFD 客户端库，依赖下方两个 OpenWFD Server；Server 再通过内核接口访问 DPU。粗横线区分用户态与内核态，缓冲区集中在下方独立的数据区。

色块表示组件来源：蓝色为 OEM 应用，绿色为通用／开源组件，黄色为平台实现，灰色为硬件与内存。默认“软件分层”视图突出蓝色调用／提交依赖；选择“叠加数据流”或“像素流”查看 GPU 读写与 DPU 取图，灰色虚线仅表示静态配置。LA-GVM 显示路径绕过 Weston。独立图支持缩放、平移、主题切换和节点关系高亮。

### 1.1 分层职责

| 层 | 关键组件 | 职责与边界 |
|---|---|---|
| 内容源 | PVM Wayland clients；LA-GVM SurfaceFlinger/HWC | 生成图形缓冲区。PVM surface 属于 Weston scene graph；LA-GVM 帧不属于该 scene graph |
| PVM 合成 | `weston`、`ivi-shell.so`、`ivi-controller.so`、`gl-renderer.so`、`sdm-service.so` | 管理 Wayland/IVI 对象；构建 SDM LayerStack；在 GPU 合成与硬件 overlay 之间分配 Weston view |
| DRM 兼容前端 | patched `libdrm.so`、`lib_drm_fe.so` | 保留 Weston DRM backend 所需的 DRM API 形态，将 `drmOpen`、`drmIoctl`、`drmClose` 转发到用户态显示前端 |
| Guest 显示后端 | `vhost-user-qti`、HAB、`VirtIOGPU2DBackendService` | 接收 LA-GVM 的 `disp` 通道请求，以 OpenWFD Client `0x7815` 提交至预留 Pipeline |
| OpenWFD 服务 | `libopenwfd.so`、`libwire_user.so`、LRMC、`openwfd_server -i 0/1` | 管理 WFD Device/Port/Pipeline、跨客户端 z-order、提交与显示事件；两个实例分别面向 DPU 0 和 DPU 1 |
| 硬件访问 | KIUMD、VFIO、SCMI MDSS | 为用户态 OpenWFD Server 提供 MMIO、中断、IOMMU/VFIO 与显示电源控制接口 |
| 显示硬件 | DPU 0/1、DP/MST、bridge、panel | 执行硬件取图、缩放、混合、DSC 和物理链路输出 |

## 2. 运行基线与核心组件

### 2.1 平台信息

| 项目 | 台架值 |
|---|---|
| SoC / BSP | Qualcomm SA8797，`oryon-1` |
| 虚拟化 | Gunyah；PVM 运行 `qcrosvm --vm=autoghgvm` 承载 LA-GVM |
| PVM OS | `auto-oem_a 202607262327` |
| Kernel | `6.6.110-rt61-debug`，PREEMPT_RT，aarch64 |
| Weston | `13.0.1` |
| Renderer | EGL `1.5`，OpenGL ES `3.2`，Adreno 753 |
| 显示配置选择 | `/usr/bin/display_cfg.ini` 中 `qcdisplaycfgName = qcdisplaycfg_project_a_296` |

### 2.2 Weston

`weston.service` 的运行命令为：

```text
weston --idle-time=0 --socket=wayland-0 \
  --modules=systemd-notify.so,compositor-pm-ds-snservice.so \
  --log=/tmp/weston.log --debug
```

- 用户与 slice：`root`，`pvm.slice`
- Wayland socket：`/run/user/0/wayland-0`
- 日志：`/tmp/weston.log`
- `--idle-time=0` 为命令行参数，覆盖配置文件中的空闲超时设置

`/etc/xdg/weston/weston.ini`：

```ini
[core]
require-input=false
shell=ivi-shell.so
modules=ivi-controller.so
idle-time=99999999
repaint-window=15

[shell]
locking=true
```

本次启动日志实际加载的显示相关模块如下：

| 模块 | 运行时职责 |
|---|---|
| `drm-backend.so` | 提供 Weston output/head、mode 与原子提交所需的 DRM 兼容模型 |
| `sdm-service.so` | 创建 SDM Core；对 Weston LayerStack 执行 `Prepare`、`Commit`、`Flush` 与 VSync 控制 |
| `gl-renderer.so` | 处理 SDM 判定为 GPU composition 的 Weston view，并提供 renderer 抓帧回退 |
| `screen-capture.so` | 提供 Qualcomm `screen_capture` Wayland global；范围限定见第 6 节 |
| `ivi-shell.so` / `ivi-controller.so` | 管理 IVI surface、layer、screen 及其布局 |
| `systemd-notify.so` | 向 systemd 上报 compositor 就绪状态 |
| `compositor-pm-ds-snservice.so` | 接入平台显示电源管理通知 |

`sdm-service.so` 并非位于 OpenWFD Server 之后的独立硬件层。它运行在 Weston 进程内：`assign_planes()` 从 `paint_node_z_order_list` 创建 SDM layer，`Prepare()` 标记 GPU 或 overlay composition，随后 `Commit()` 进入 DRM-FE/OpenWFD 客户端路径。

### 2.3 DRM-FE 与 OpenWFD

本平台的 `libdrm` 在构建时启用 `DRM_FE`。其调用链为：

```text
Weston drm-backend / SDM
  → patched libdrm.so
  → lib_drm_fe.so
  → libopenwfd.so + libwire_user.so
  → LRMC
  → openwfd_server -i 0 / -i 1
```

`libdrm` 补丁通过 `dlopen("/usr/lib/lib_drm_fe.so")` 获取 `drm_interface_fe`，并将 `drmOpen`、`drmIoctl`、`drmClose` 分派到前端实现。因此，日志中的 `DRM connector`、`drm-backend.so` 与 `atomic commit` 是 Weston 侧的兼容抽象，不表示存在 `msm_drm` 的 `/dev/dri/card*` 内核 KMS 路径。

运行态文件描述符进一步确认了边界：

| 进程 | 关键设备或映射 |
|---|---|
| `weston` | 映射 `lib_drm_fe.so`、`libopenwfd.so`、`libwire_user.so`、`libsdmcore.so`、`libsdmdal.so`；打开 LRMC 共享内存、DMA heap、`/dev/ksync` 和 `/dev/dmabuf_share`；未打开 `/dev/dri/*` 或 DPU VFIO 设备 |
| `openwfd_server -i 0` | 打开 `/dev/kiumd`、VFIO container/group、`/dev/scmi_mdss0` |
| `openwfd_server -i 1` | 打开 `/dev/kiumd`、VFIO container/group、`/dev/scmi_mdss1` |
| `VirtIOGPU2DBackendService` | 打开 `/dev/hab`、DMA heap 与通向两个 OpenWFD Server 的 LRMC 共享内存；映射 OpenWFD 客户端库 |

`/dev/mqueue/openwfd_server_0` 与 `/dev/mqueue/openwfd_server_1` 是 Server 发布的就绪端点，`wait-openwfd.service` 轮询二者后结束。运行态客户端通信使用 LRMC 共享内存；不能仅依据 mqueue 文件将 OpenWFD IPC 等同为 POSIX 消息队列数据通路。

### 2.4 OpenWFD 对象模型

| 对象 | 本平台含义 |
|---|---|
| WFD Client | 一个具有固定 Client ID、类型与 VM ID 的提交者 |
| WFD Port | 映射到 `(QDI Device ID, QDI Display ID)` 的客户端输出端点，并拥有固定 z-order 区间 |
| WFD Pipeline | 客户端可枚举的 layer 提交端点；在 XML 中静态绑定到 `DMAx` 或 `VIGx` QDI Layer ID |
| Pipeline source/buffer | Pipeline 当前提交的图像源及其属性；来源受所属 Client 和 Port 约束 |

Pipeline 是对已分配 QDI layer 的 OpenWFD 抽象，不等同于任意一个 DPU Layer Mixer 输入，也不与每个 `wl_surface` 一一对应。Weston 可先将多个 view 合成为 framebuffer target，也可将符合条件的 view 作为 overlay 提交；实际数量受 SDM 策略及为 Client 预留的 Pipeline 限制。

## 3. OpenWFD 资源分配

`/usr/bin/display_cfg.ini` 通过 `qcdisplaycfgName` 选择显示配置集：

```ini
qcdisplaycfgName = qcdisplaycfg_project_a_296
```

对应的 `qcdisplaycfg_project_a_296.xml` 定义 Client 身份、Port 与 DPU/display 的映射、Pipeline 与 QDI layer 的绑定及 z-order 分配。INI 负责选择配置集，XML 描述具体资源约束。

运行中的 `/usr/bin/display_parse --wfd` 与源码配置 `qcdisplaycfg_project_a_296.xml` 一致。

### 3.1 Client、Port 与 Pipeline

| Client | 类型 / VM | QDI Device / Display | Port z-order 区间 | Pipeline → QDI Layer / z-order |
|---|---|---|---|---|
| `0x7812` | `TELLTALE` (`0x3`) / Host (`1`) | DPU 0 / display 3 | `10..10` | P1 → `VIG3` / `z10` |
| `0x78FF` | `SCREEN` 保留 ID，类型 `CLUSTER` (`0x1`) / Host (`1`) | DPU 0 / display 3 | `4..5` | P1 → `DMA0` / `z4`；P2 → `VIG0` / `z5` |
| `0x78FF` | 同上 | DPU 1 / display 8 | `4..4` | P3 → `DMA1` / `z4` |
| `0x7815` | `LA_GVM` (`0x5`) / GVM1 (`2`) | DPU 0 / display 3 | `0..3` | P1 → `DMA2` / `z0`；P2 → `VIG2` / `z1` |
| `0x7815` | 同上 | DPU 1 / display 8 | `0..1` | P3 → `DMA3` / `z0` |
| `0x7815` | 同上 | DPU 1 / display 9 | `0..1` | P4 → `DMA4` / `z0` |

`0x7815` 启用 MultiRect。DPU 0/display 3 的两个物理 Pipeline 因此预留四个 z-order 位置；DPU 1/display 8 和 display 9 各为单 Pipeline 预留两个位置。

在 display 3 上，LA-GVM 位于 `z0/z1`，Weston/SCREEN 位于 `z4/z5`，TELLTALE 位于 `z10`。该静态分配决定跨客户端的最终叠放顺序，并保证各客户端不能占用未授权的 QDI layer。

架构图中 TELLTALE 的虚线边框表示 Client `0x7812` 的静态资源预留，与 SCREEN Client `0x78FF` 分开分配资源；不表示已确认存在同名进程、共享库或活动画面。

### 3.2 显示拓扑

| DPU / QDI display | Panel 配置 | Bridge | 配置时序 | Weston 运行态 |
|---|---|---|---|---|
| DPU 0 / display 3 | `DP0_COMMON_MST1_OEM` | `MAX96855A_SST_CENTRAL_296` | `6400×1800 @ 60 Hz`；DSC 启用，压缩比 3:1，slice `1600×1800` | `DP0S078FF1`，connector `16780217`，connected |
| DPU 1 / display 8 | `DP3_COMMON_MST1_OEM` | `DS90UB983_MST_CLUS888_HUD47` | `1920×480 @ 60 Hz` | `DP3S078FF2`，connector `16780218`，connected |
| DPU 1 / display 9 | `DP3_COMMON_MST2_OEM` | `NATIVE` | `1280×640 @ 60 Hz` | 配置并分配给 LA-GVM；本次 Weston 日志未枚举对应 head |

Weston 本次运行只启用了 `DP0S078FF1` 和 `DP3S078FF2` 两个 output。静态 XML 中存在 display 9 不能据此推导其物理链路在当前台架处于 active 状态。

## 4. 图形数据流

### 4.1 PVM 原生内容

1. Wayland client 将 buffer 关联到 `wl_surface`，Weston/IVI Shell 将其组织为 output 的 paint-node 列表。
2. `sdm-service.so` 为可见 view 创建 SDM layer，并调用 `Prepare()`。
3. SDM 标记为 `SDM_COMPOSITION_GPU` 的 view 进入 `gl-renderer`；可由显示硬件处理的 view 保持为 overlay。
4. GPU 合成结果和 overlay layer 由 `Commit()` 提交，经 DRM-FE 转换为 OpenWFD 客户端操作。
5. Client `0x78FF` 只能使用配置给 SCREEN 的 Port/Pipeline；TELLTALE 使用独立 Client `0x7812`。
6. OpenWFD Server 将各 Client 的 buffer、属性与同步信息应用到对应 DPU/QDI layer。

### 4.2 LA-GVM 内容

LA-GVM 显示通路如下：

```text
Android display frontend
  → qcrosvm --vhost-user-hab /tmp/linux-vm2-disp-skt
       (label 0x3C, device-id 93, queue-num 10)
  → vhost-user-qti -s /tmp/linux-vm2-disp-skt
       -d /dev/vhost-disp -q 10
  → HAB
  → VirtIOGPU2DBackendService
  → OpenWFD Client 0x7815
  → 预留 Port/Pipeline
  → openwfd_server
  → DPU
```

`queue-num=10` 表示该 VirtIO/HAB 设备配置的队列数量，不表示帧缓冲深度。

Client `0x7815` 与 Weston/SCREEN Client `0x78FF` 使用不同的 Pipeline。LA-GVM buffer 因此不经过 Weston，也不出现在 `wl_surface`、IVI layer 或 Weston paint-node 列表中；它仍会按照 OpenWFD 配置的 z-order 参与同一物理显示的最终 DPU 合成。

### 4.3 GL 渲染通路

LA-GVM 的 OpenGL ES 通路由另一个 vhost-user/HAB 设备承载：

```text
/tmp/linux-vm2-ogles-skt
  label 0x39
  device-id 94
  queue-num 2
  host device /dev/vhost-ogles
```

该通路连接 KGSL/Adreno 虚拟化栈，与 `VirtIOGPU2DBackendService` 的 `disp` 提交通路分离。`VirtIOGPU2DBackendService` 负责 2D 显示后端和 OpenWFD 提交，不处理 Guest GL 命令。

## 5. systemd 服务拓扑

systemd 的 `Requires=`、`After=` 和 `PartOf=` 具有不同语义。当前镜像中的关系如下：

| Unit | 约束 | 运行命令 / 身份 |
|---|---|---|
| `display_hw_combo.service` | 在 module 与 VFIO probe 之后启动；OpenWFD Server 对其仅声明 `After=` | `/usr/bin/display_hw_combo`，root，`system.slice` |
| `openwfd_server_@0.service` / `@1` | `After=display_hw_combo.service` | `/usr/bin/openwfd_server -i %i`，display，`pvm.slice` |
| `wait-openwfd.service` | `weston.service` 对其声明 `Requires=` 和 `After=`；轮询两个 Server mqueue 端点 | oneshot，root，`system.slice` |
| `vhost-user-disp.service` | `display-be.service` 对其声明 `Requires=` 和 `After=` | `vhost-user-qti ... /dev/vhost-disp -q 10`，root，`gvm.slice` |
| `display-be.service` | `After=` 两个 OpenWFD Server；`PartOf=` 两个 Server；与 Weston 无依赖关系 | `VirtIOGPU2DBackendService /usr/bin/config.xml`，display，`gvm.slice` |
| `weston.service` | `Requires=` 两个 OpenWFD Server、`wait-openwfd.service` 和 `systemd-user-sessions.service` | `weston ...`，root，`pvm.slice` |
| `display_diag.service` | 独立 `Requires=`/`After=` 两个 OpenWFD Server；`ExecStartPre=/bin/sleep 60` | `/usr/bin/display_diag`，root，`system.slice` |

由此得到的启动约束为：

```text
display_hw_combo --After--> openwfd_server -i 0 / -i 1

openwfd_server readiness mqueues --> wait-openwfd --> weston

vhost-user-disp ------------------------------┐
openwfd_server -i 0 / -i 1 --After----------->├─ display-be
                                               └─ PartOf openwfd servers

openwfd_server -i 0 / -i 1 --> display_diag (延迟 60 s)
```

`weston.service` 与 `display-be.service` 是 OpenWFD Server 之上的并列客户端服务，不存在 `display-be → weston` 的启动或数据依赖。

## 6. 抓帧与显示诊断边界

### 6.1 Weston 抓帧接口

| 接口 | 实现 | 捕获对象 | 当前约束 |
|---|---|---|---|
| `weston_capture_v1` | Weston `libweston/output-capture.c`；客户端 `weston-screenshooter` | 指定 Weston output；客户端选择 `FRAMEBUFFER` source | 协议需要 screenshot authority。当前 Weston 使用 `--debug`，主程序安装 allow-all authority |
| `ivi_wm_screen.screenshot` | `ivi-controller.so` | 指定 IVI screen 对应的 Weston output | 临时增加 `disable_planes`，在下一帧通过 renderer `read_pixels()` 返回共享内存 FD |
| `ivi_wm.surface_screenshot` | `ivi-controller.so` | 单个 IVI/Weston surface | 调用 `weston_surface_copy_content()`，返回匿名运行时文件 FD |
| Qualcomm `screen_capture` | `screen-capture.so`、`compositor-sdm.c` | 指定 Weston output 的 paint-node 列表 | 仅接受带 screen-capture flag 的 GBM buffer；实现要求同一时刻只有一个 active capture instance |

Qualcomm `screen_capture` 保留了 mirror/virtual-output 和 WB2 fence 处理框架，但当前实现对 virtual output 调用 `assign_planes(..., true)` 时不执行 SDM `Prepare()`。新建 layer 保持默认的 `SDM_COMPOSITION_GPU`，非空场景随即设置 `fallback_gpu=true`，实际抓帧分支调用 renderer `capture_screen()`。因此，不能仅根据源码中的 WB2 注释将该接口归类为当前可用的 DPU writeback 通路。

该模块的输入来自 Weston paint-node 列表，不包含 Client `0x7815` 的独立 LA-GVM Pipeline。`bind_screen_capture()` 也未实现基于凭据或 authority 的授权检查；访问控制应由 socket 权限、进程部署策略或额外的 compositor 策略承担。

因此，上述 Weston/IVI 抓帧接口只能捕获 Weston 管理的内容。屏幕上由 OpenWFD 在 Weston 之外叠加的 LA-GVM 或 TELLTALE Pipeline 不属于其捕获域。若需要完整物理输出，抓帧位置必须位于汇合所有 WFD Client 之后，并使用平台明确提供的 DPU/post-blend writeback 或等效接口。

### 6.2 `display_diag`

`display_diag` 是链路诊断服务，不是画面抓取服务。其源码行为包括：

- 从 `display_cfg.ini` 读取各屏 `Diag_display_*` 使能项；
- 动态加载 bridge 驱动库，调用面板对应的 cable/link 诊断函数；
- 在 DP 电源开启且 trigger inactive 时轮询诊断状态；
- 将 16 字节诊断消息发送到 VSOCK port `10001`；
- 响应平台低功耗进入/退出通知。

该服务没有读取 Weston surface、OpenWFD Pipeline buffer 或写入 surface dump 文件的实现。它对 `openwfd_server_@0/1.service` 的 systemd 依赖只构成启动约束。

## 7. 核验方法

以下命令用于区分静态配置、Weston 视图和硬件资源：

```bash
# 平台与进程
adb -s e8cc24da shell 'cat /etc/os-release; uname -a; weston --version'
adb -s e8cc24da shell \
  'ps -eo user,pid,ppid,args | grep -E "weston|openwfd|VirtIOGPU|vhost-user-qti|qcrosvm|kgsl"'

# 当前 panel 配置与 WFD 资源
adb -s e8cc24da shell '/usr/bin/display_parse --show'
adb -s e8cc24da shell '/usr/bin/display_parse --wfd'

# Weston 实际枚举的 output、mode、renderer 和模块
adb -s e8cc24da shell \
  'grep -E "head .* found|mode .*current|Loading module|EGL version|GL version|GL renderer" /tmp/weston.log'

# 服务依赖的真实语义
adb -s e8cc24da shell \
  'systemctl show weston.service display-be.service display_diag.service \
     -p Requires -p After -p PartOf -p User -p Group -p Slice -p ExecStart'

# 硬件所有权；先按进程名取得 PID，再检查文件描述符
adb -s e8cc24da shell \
  'for p in $(pidof openwfd_server); do echo "PID=$p"; ls -l /proc/$p/fd; done'
```

主要源码与配置位置：

| 主题 | PVM 源码根目录下的路径 |
|---|---|
| 生效 WFD/panel 配置 | `layers/meta-oem_a-bsp/recipes-products/owfds-misc/files/display/config/PROJECT_A/qcdisplaycfg_project_a_296.xml` |
| WFD 配置字段定义 | `vendor/qcom/proprietary/owfds-ship/boards/adp_star_sda8797/qcdisplaycfg-readme.txt` |
| DRM-FE 的 libdrm 分派补丁 | `layers/meta-qti-automotive/recipes-graphics/drm/libdrm-2.4.120/0001-DRM-front-end-display-DRM-front-end.patch` |
| Weston SDM/抓帧实现 | `vendor/qcom/opensource/display/weston-sdm-extension/sdm-backend/` |
| IVI screenshot 实现 | `vendor/qcom/opensource/display/wayland-ivi-extension/weston-ivi-shell/src/ivi-controller.c` |
| Guest display backend 配方 | `layers/meta-qti-automotive-prop/recipes-graphics/display-be/display-be.bb` |
| OEM_A 显示服务与诊断 | `layers/meta-oem_a-bsp/recipes-products/owfds-misc/files/` |

## 8. 缩写

| 缩写 | 含义 |
|---|---|
| DPU | Display Processing Unit |
| DRM-FE | DRM Front End；本平台将 libdrm API 转换为用户态显示服务调用的兼容前端 |
| GVM | Guest Virtual Machine |
| HAB | Hypervisor Abstraction；Guest 与 Host/PVM 之间的通信机制 |
| IVI | In-Vehicle Infotainment |
| KIUMD | Kernel Interface for Usermode Driver；为用户态驱动提供 MMIO、中断与内核服务接口 |
| OpenWFD | OpenWF Display API；本平台用作多客户端显示资源与提交模型 |
| PVM | Primary Virtual Machine |
| QDI | 平台显示配置中的 Device、Display 与 Layer 标识体系；本文保留源码使用的缩写，不扩展其名称 |
| SDM | Software Display Module |
| WFD | OpenWF Display 对象/API 的前缀 |
