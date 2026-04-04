+++
date = '2026-03-29T20:00:00+08:00'
draft = false
title = 'Android Guest 显示数据通道深度解析 (virtio-HAB)'
tags = ["Android", "Display", "Virtualization", "Gunyah", "Qualcomm", "HAB", "DRM"]
+++

## 1. 概述

本文档详细描述了 Qualcomm SA8797 (Gen5) 智能座舱平台中，Android Guest VM 的 **显示（Display）数据通道** 完整时序。

在该平台中，Android Guest 的 HWC/DRM 子系统通过 **HAB (Hypervisor ABstraction)** 框架与 Linux Host 上的 **display-be (VirtIOGPU2DBackendService)** 通信，后者将 virtio-gpu 协议翻译为 **OpenWFD** 协议，最终由 **openwfd_server** 驱动物理 DPU 硬件完成显示输出。

HAB 的底层传输使用 **virtio virtqueue**，通过 vhost 机制在 Guest 内核与 Host 内核之间高效传递消息。

### 源码基线

| 组件 | 源码路径 |
|------|---------|
| Guest DRM 驱动 (virtgpu_vq.c, virtio_kms.c) | `vendor/qcom/opensource/display-drivers/msm/hyp/virtio/` |
| Guest HAB virtio 传输 (hab_virtio.c) | `kernel_platform/soc-repo/drivers/soc/qcom/hab/` |
| Host vhost-user 桥接 (main.c, vhost_user.c, vhost_kernel.c) | `vendor/qcom/opensource/vhost-user/` |
| Host HAB vhost 驱动 (hab_vhost.c) | `vendor/qcom/opensource/mmhab-drv/hypervisor/virtio/` |
| Host HAB 框架 (hab.c, hab_mimex.c 等) | `vendor/qcom/opensource/mmhab-drv/` |
| Host display-be 配置 | `prebuilt_HY11/sa8797/display-be/usr/bin/config.xml` |
| OpenWFD wire_format | `prebuilt_HY11/sa8797-fts/openwfd-client/usr/include/WF/wire_format.h` |
| systemd 服务定义 | `vhost-user-disp.service`, `display-be.service`, `qcrosvm_sa8797.service` |

## 2. 参与组件

### Android Guest (内核态)

| 组件 | 说明 |
|------|------|
| **HWC / DRM (virtio-kms / virtgpu-vq)** | Guest 内核的 DRM 驱动。负责 scanout 属性查询、DPU 上电、帧提交等。所有显示命令通过 `virtio_hab_send_and_recv()` 发送 |
| **Guest HAB 内核驱动 (hab_virtio.c)** | HAB 框架的 virtio 传输层。将 HAB 消息封装为 virtio vring 描述符，通过 `virtqueue_add_outbuf` + `virtqueue_kick` 发送 |

### Host 控制面 (建链与生命周期控制)

| 组件 | 说明 |
|------|------|
| **qcrosvm** | Gunyah VMM。通过 `--vhost-user-hab` 作为 vhost-user frontend 连接 Unix socket，完成 vring / 内存 / eventfd 协商；稳态显示数据不经过 qcrosvm 用户态 |
| **vhost-user-qti (vhost-user-disp)** | vhost-user backend 桥接服务。常驻监听 `/tmp/linux-vm2-disp-skt`，接收 qcrosvm 的控制消息，并转换为 `/dev/vhost-disp` 的 `VHOST_*` ioctl。它保活以处理重连/复位/停机，但**不转发显示 payload** |

### Host 内核态

| 组件 | 说明 |
|------|------|
| **Host HAB vhost (hab_vhost.c)** | 数据通道的核心中转。`tx_worker()` 从 TX vring 读取 Guest 发来的 HAB 消息并投递到 HAB 框架；`rx_worker()` 将 Host 回复写入 RX vring 并通过 irqfd 触发 KVM 向 Guest 注入中断 |

### Host 用户态 Backend

| 组件 | 说明 |
|------|------|
| **VirtIOGPU2DBackendService (display-be)** | 协议翻译器。通过 **libuhab** 从 HAB 框架接收 virtio-gpu 命令，翻译为 OpenWFD 协议 (如 `DEVICE_COMMIT_EXT`)，发送给 openwfd_server |

### Host OS & HW

| 组件 | 说明 |
|------|------|
| **openwfd_server** | 物理显示控制服务。接管 SDE (Smart Display Engine) 硬件，执行 DPU 合成、DP 输出、面板控制。通过 `bridgechip_server` 驱动 DP bridge 和面板 |

## 3. 时序图

```plantuml
@startuml
!theme plain
scale 1024 width
autonumber "[0]"

box "Android Guest (内核态)"
participant "HWC / DRM\n(virtio-kms / virtgpu-vq)" as guest_drm
participant "Guest HAB 内核驱动\n(hab_virtio.c)" as guest_hab
end box

box "Host 控制面 (建链与生命周期控制)"
participant "qcrosvm" as vmm
participant "vhost-user-qti\n(vhost-user-disp)" as vhost_qti
end box

box "Host 内核态"
participant "Host HAB vhost\n(hab_vhost.c)" as host_vhost
end box

box "Host 用户态 Backend"
participant "VirtIOGPU2DBackendService\n(display-be, via libuhab)" as be_service
end box

box "Host OS & HW"
participant "openwfd_server\n(DPU HW)" as openwfd
end box

== 阶段 1: 宿主机服务初始化 ==
openwfd -> openwfd : 启动并接管物理显示硬件 (SDE)
vhost_qti -> vhost_qti : 启动, 监听 Unix socket\n(/tmp/linux-vm2-disp-skt)\n打开 /dev/vhost-disp (-q 10)
be_service -> be_service : 解析 config.xml\n(Packet=301, Event=303, Buffer=301)
note right of be_service
  display-be.service
  Requires=vhost-user-disp.service
  After=openwfd_server_@0/1.service
end note

== 阶段 2: 虚拟机启动与 vhost-user 通道建立 (控制面) ==
vmm -> vhost_qti : 连接 socket /tmp/linux-vm2-disp-skt\n(--vhost-user-hab, device-id=93, queue-num=10)
vmm -> vhost_qti : vhost-user 协议协商\n(set_vring_num/addr/base/kick/call)
vhost_qti -> host_vhost : 通过 /dev/vhost-disp ioctl\n配置 vring, ioeventfd, irqfd
note over vmm, vhost_qti
  控制面完成后, qcrosvm 与 vhost-user-qti
  **不在显示消息热路径上**
  vhost-user-qti 进程仍常驻
  用于处理重连/复位等控制事件
  数据通道: Guest HAB 内核 <-> vring <-> Host HAB vhost 内核
end note

== 阶段 2b: Guest HAB 通道建立 ==
guest_drm -> guest_hab : habmm_socket_open(MM_DISP_1=301)\n[命令通道 CHANNEL_CMD]
guest_drm -> guest_hab : habmm_socket_open(MM_DISP_3=303)\n[事件通道 CHANNEL_EVENTS]
guest_hab -> host_vhost : 通过 virtio vring 触发通道建立
host_vhost -> be_service : HAB 框架分配 vchan->id (VCID)\n通过 libuhab 唤醒 display-be
host_vhost --> guest_hab : ACK 返回 VCID (通过 vring)

== 阶段 3: Buffer 共享 (HAB 内存导出/导入) ==
guest_drm -> guest_hab : habmm_export(buffer_handle)
guest_hab -> host_vhost : habmem_hyp_grant() (通过 vring)
guest_hab <-- host_vhost : 返回 exportid

== 阶段 4: 渲染提交与协议翻译 (virtio_hab_send_and_recv 机制) ==
note over guest_drm
  封装 virtio-gpu 命令
  进入 virtio_hab_send_and_recv()
  (virtgpu_vq.c:62)
end note

guest_drm -[#red]> guest_hab : habmm_socket_send(req, **flags=0 阻塞**)\n[注: 仅 EVENT_CONTROL 用 NON_BLOCKING/spinlock]
guest_hab -[#red]> host_vhost : virtqueue_add_outbuf + virtqueue_kick\n(hab_virtio.c, ioeventfd 通知 host)

host_vhost -> host_vhost : tx_worker() 从 TX vring 读取消息\n(hab_vhost.c:165)
host_vhost -> be_service : HAB 框架投递 (libuhab habmm_socket_recv)
be_service -> be_service : habmm_import(exportid)\n-> habmem_imp_hyp_map()\n返回 dma_buf fd
be_service -> be_service : 协议翻译:\nvirtio-gpu CMD -> OpenWFD DEVICE_COMMIT_EXT
be_service -> openwfd : 发送 OpenWFD commit 请求\n(携带 dma_buf fd 和图层属性)
openwfd -> openwfd : 编程底层 DPU 完成合成与刷屏

openwfd --> be_service : 硬件执行完毕 (ACK)
be_service -> host_vhost : habmm_socket_send (Command Response)\n通过 libuhab -> HAB 框架
host_vhost -> host_vhost : rx_worker() 写入 RX vring\n(hab_vhost.c:157)\n信号 irqfd -> KVM 注入中断
host_vhost -> guest_hab : Guest 收到中断, 从 vring 读取响应

loop 最多 10 次重试 (MAX_SEND_RECV_PACKET_RETRY=10)
    guest_drm -[#red]> guest_hab : habmm_socket_recv(NON_BLOCKING)
    note right of guest_drm
      内层 do...while 循环:
      在 HZ/4 (250ms) 窗口内
      紧凑轮询 habmm_socket_recv
    end note
    alt 窗口内仍为 -EAGAIN
        guest_drm -[#red]> guest_drm : 250ms 窗口耗尽\n打印 "recv packet retry N"\n重置 delay, 进入下一轮
    else 收到有效响应
        guest_hab --[#red]> guest_drm : 成功获取 resp 数据
        break
    end
end
note right of guest_drm
  共 11 次轮询窗口 (1 次初始 + 10 次重试)
  若全部耗尽 (约 2.75 秒) 仍为 -EAGAIN
  函数返回 -1, 导致 DRM 流程断裂
end note

== 阶段 5: VSync / 事件回传 (长轮询模式) ==
note over guest_drm
  Guest 事件内核线程 virtio_gpu_event_kthread
  在 while(!kms->stop) 循环中主动发起
  使用 **事件通道** (CHANNEL_EVENTS, MM_DISP_3=303)
end note

guest_drm -> guest_hab : habmm_socket_send(VIRTIO_GPU_CMD_WAIT_EVENTS)\n[阻塞发送, 通过事件通道]
guest_hab -> host_vhost : 请求通过 vring 到达 Host
host_vhost -> be_service : HAB 框架投递 WAIT_EVENTS 请求

be_service -> be_service : 阻塞等待 OpenWFD 事件
openwfd -> be_service : OpenWFD 事件\n(DISP_VSYNC / EVENT_NOTIFICATION)
be_service -> be_service : 协议翻译:\nOpenWFD Event -> virtio_gpu_resp_event
be_service -> host_vhost : habmm_socket_send(Event Response)\n通过 libuhab -> HAB 框架
host_vhost -> host_vhost : rx_worker() 写 RX vring + 信号 irqfd
host_vhost -> guest_hab : KVM 注入中断, Guest 从 vring 读取

note over guest_drm
  使用 virtio_hab_send_and_recv_timeout()
  recv: HABMM_SOCKET_RECV_FLAGS_TIMEOUT, timeout=2500ms
  (与命令通道的 NON_BLOCKING 轮询机制不同)
end note

guest_hab -> guest_drm : 解析 resp_event:\nvsync_count / commit_count / hpd_count\n分别触发 virtio_kms_event_handler

note over guest_drm
  循环回到 WAIT_EVENTS, 持续长轮询
end note
@enduml
```

## 4. 关键机制详解

### 4.1 控制面与数据面分离

这是理解此架构最重要的一点。

**控制面 (Control Plane)** 包含 qcrosvm 和 vhost-user-qti，主要在 VM 启动建链、设备 reset 和停机阶段参与：

```
qcrosvm --vhost-user-hab "/tmp/linux-vm2-disp-skt",label=3C,device-id=93,queue-num=10
```

qcrosvm 通过 vhost-user 协议将 virtio 设备的 vring 配置（内存布局、ioeventfd、irqfd）传递给 vhost-user-qti。后者通过 `/dev/vhost-disp` ioctl 将配置注入 Host 内核的 vhost HAB 驱动。`vhost-user-qti` 是一个**常驻控制服务**，不是一次性的初始化脚本。

**数据面 (Data Plane)** 完全在内核态完成：

```
Guest HAB 内核 (hab_virtio.c)
    |
    | virtio vring (共享内存 + ioeventfd/irqfd)
    |
Host HAB vhost 内核 (hab_vhost.c)
    |
    | HAB 框架内部投递
    |
/dev/hab -> libuhab -> display-be (用户态)
```

控制面完成后，qcrosvm 和 vhost-user-qti **不在显示数据热路径上**。ioeventfd 由 Host 内核 vhost worker 直接监听，irqfd 由 KVM 直接响应并注入中断到 Guest，无需经过 VMM 用户态；但 `vhost-user-qti` 进程仍保活，用于处理控制面生命周期消息。

### 4.2 vhost-user 与 HAB 的分层关系

从抽象上看，vhost-user 是一种将 virtio **frontend** 与 **backend** 解耦的控制协议：

- frontend 位于 VMM (`qcrosvm`)，负责向 Guest 暴露 virtio 设备并管理 Guest 侧内存描述
- backend 位于另一个进程或内核对象，负责接收 vring、共享内存和 eventfd 配置，之后执行真正的数据收发

在很多标准 virtio 场景里，vhost-user backend 本身就是稳态数据面的执行者；而在本文的显示链路里，`vhost-user-qti` 的角色更窄，它只是一个**用户态控制桥**。真正承接 steady-state 显示消息的是 Host 内核中的 `hab_vhost.c`。

下图同时展示了 **vhost-user** 与 **HAB** 两个层次上的 frontend/backend 角色定义：

- `qcrosvm` 是 **vhost-user frontend**
- `vhost-user-qti` 是 **vhost-user backend**，但它只是控制桥，不是 display-be
- Android Guest 内核里的 `msm_hab.ko` 是 **HAB frontend**
- Linux Host 内核里的 `msm_hab.ko`/`hab_vhost.o` 是 **HAB backend**

图中的软件构件均采用源码树里的真实目标名或真实模块名：Guest DRM 为 `virtio-gpu.o`，Guest/Host HAB 为 `msm_hab.ko`，Host 用户态对应 `qcrosvm`、`vhost-user-qti`、`libuhab.so`、`VirtIOGPU2DBackendService` 和 `openwfd_server`。

```plantuml
@startuml
!theme plain

skinparam Shadowing false
skinparam defaultTextAlignment center

rectangle "Android Guest" {
  rectangle "virtio-gpu.o\n(DRM virtio display frontend)\nvirtgpu_vq.c / virtgpu_kms.c" as guest_gpu
  rectangle "msm_hab.ko\n(HAB frontend)\nkhab.c / hab.c / hab_virtio.c" as guest_hab
  rectangle "MM_DISP_1 = 301\nMM_DISP_3 = 303" as guest_mmid

  guest_gpu --> guest_mmid : habmm_socket_open()\nhabmm_socket_send()/recv()
  guest_mmid --> guest_hab : Guest kernel HAB API
}

rectangle "Hypervisor" {
  rectangle "Gunyah\nshared memory + doorbell / virq" as gh
}

rectangle "Linux Host" {
  rectangle "qcrosvm\n(bin)\n--vhost-user-hab ...\ndevice-id=93, queue-num=10\n[vhost-user frontend]" as qcrosvm
  rectangle "/tmp/linux-vm2-disp-skt\n(AF_UNIX socket)" as sock
  rectangle "vhost-user-qti\n(bin)\n[vhost-user backend]\ncontrol bridge only" as vhostu
  rectangle "/dev/vhost-disp\n(vhost ioctl ABI)" as vdev
  rectangle "msm_hab.ko\n(HAB backend)\ncontains hab_vhost.o" as host_hab
  rectangle "libuhab.so\n(user-space HAB wrapper)" as libuhab
  rectangle "VirtIOGPU2DBackendService\n(display-be bin)" as display_be
  rectangle "openwfd_server\n(bin)" as openwfd

  qcrosvm --> sock : connect
  sock --> vhostu : accept / dispatch
  vhostu --> vdev : VHOST_SET_* / GET_* ioctl
  vdev --> host_hab : configure vring + kick/call eventfd

  display_be --> libuhab : habmm_socket_open()\nhabmm_socket_send()/recv()
  libuhab --> host_hab : IOCTL_HAB_VC_OPEN /\nSEND / RECV
  display_be --> openwfd : OpenWFD commands
}

guest_hab <--> gh : virtio-hab transport\n(device-id = 93)
gh <--> host_hab : vring / shared memory / virq
@enduml
```

从架构分层看，这张图表达的是：

- `qcrosvm <-> vhost-user-qti` 这一层只负责 **vhost-user 控制面**
- `Guest msm_hab.ko <-> Host msm_hab.ko` 才是 **HAB frontend/backend**
- `display-be` 通过 `libuhab.so` 调用 Host HAB backend；它不是 vhost-user backend
- `vhost-user-qti` 会一直保活，但 steady-state 下显示 payload 并不穿过 `/tmp/linux-vm2-disp-skt`

对于 `habmm_socket_open()` 这条调用链，FE/BE 角色是在 HAB 层确定的，而不是在 vhost-user 层确定的。Guest kernel 的 `habmm_socket_open()` 只是 `khab.c` 里的薄封装，直接进入 `hab_vchan_open()`；后者再根据本端 `pchan->is_be` 选择走 `frontend_open()` 或 `backend_listen()`。以 display-be 的 Packet channel `MM_DISP_1=301` 为例，Guest 侧对应 FE，Host 侧对应 BE，握手时序如下：

```plantuml
@startuml
!theme plain
scale 1024 width
skinparam Shadowing false
autonumber

box "Android Guest"
participant GDRV as "virtio-gpu.o"
participant GFE as "msm_hab.ko\nkhab.c -> hab_vchan_open()\nfrontend_open()"
end box

box "Hypervisor"
participant GH as "Gunyah\nvirtio transport + virq"
end box

box "Linux Host"
participant DBE as "VirtIOGPU2DBackendService\n(display-be)"
participant UHAB as "libuhab.so"
participant HBE as "msm_hab.ko\nhab_vchan_open()\nbackend_listen()"
end box

note over GFE,HBE
hab.c open handshake:
FE: send(INIT) -> wait(INIT_ACK) -> send(INIT_DONE)
BE: wait(INIT) -> send(INIT_ACK) -> wait(INIT_DONE)
end note

note over GFE,HBE
`vcid` is local to each side.
Guest and Host each allocate their own `vchan->id`,
then exchange it as `otherend_id` during INIT / INIT_ACK.
end note

DBE -> UHAB : habmm_socket_open(MM_DISP_1 = 301)
UHAB -> HBE : IOCTL_HAB_VC_OPEN
activate HBE
HBE -> HBE : pchan->is_be == true\nselect backend_listen()
HBE -> HBE : wait(INIT)

GDRV -> GFE : habmm_socket_open(MM_DISP_1 = 301)
activate GFE
GFE -> GFE : khab.c thin wrapper\nhab_vchan_open()
GFE -> GFE : pchan->is_be == false\nselect frontend_open()
GFE -> GFE : hab_vchan_alloc()\nallocate local guest vcid
GFE -> GH : send INIT\nxdata.vchan_id = guest vcid
GH -> HBE : deliver INIT
HBE -> HBE : hab_vchan_alloc()\nallocate local host vcid
HBE -> GH : send INIT_ACK\nxdata.vchan_id = host vcid
GH -> GFE : deliver INIT_ACK
GFE -> GFE : wait(INIT_ACK) satisfied\nset otherend_id = host vcid
GFE -> GH : send INIT_DONE
GFE --> GDRV : return local guest vcid
deactivate GFE
GH -> HBE : deliver INIT_DONE
HBE -> HBE : wait(INIT_DONE) satisfied
HBE --> UHAB : return local host vcid
UHAB --> DBE : `*handle = arg.vcid`
deactivate HBE
@enduml
```

在该时序中，`vcid` 表示各侧本地生成的虚拟通道句柄，并不是跨 Guest/Host 共享的全局统一句柄。

- Guest FE 在 `frontend_open()` 中先执行 `hab_vchan_alloc()`，生成本地 Guest `vchan->id`，再将其放入 `INIT.xdata.vchan_id`
- Host BE 在收到 `INIT` 后执行自己的 `hab_vchan_alloc()`，生成本地 Host `vchan->id`，并写入 `INIT_ACK.xdata.vchan_id`
- Guest 收到 `INIT_ACK` 后，将 `recv_request->xdata.vchan_id` 保存到本地 `vchan->otherend_id`
- Host 在收到 `INIT_DONE` 后从 `backend_listen()` 返回；随后 `hab_vchan_open()` 将本地 `vchan->id` 写回 `*vcid`
- Host 用户态 `libuhab.so` 再将 `arg.vcid` 赋给 `*handle`

因此，在本节后续描述中：

- **frontend** 若未额外说明，指的是 Android Guest 内核中的 `msm_hab.ko/frontend_open()`
- **backend** 若未额外说明，指的是 Linux Host 内核中的 `msm_hab.ko/backend_listen()`
- `qcrosvm` 对应的是 vhost-user frontend 角色，不参与这段 HAB open 握手的 FE 角色判定
- `vhost-user-qti` 对应的是 vhost-user backend 角色，也不是 `habmm_socket_open()` 阻塞等待的直接对端

在本设计中，vhost-user 的工作流可以分为 5 步：

1. `vhost-user-disp.service` 启动 `/usr/bin/vhost-user-qti -s /tmp/linux-vm2-disp-skt -d /dev/vhost-disp -q 10`，创建 Unix socket，打开 `/dev/vhost-disp`，完成 `listen()` 后通过 `sd_notify("READY=1")` 告知 systemd 服务已就绪。
2. `qcrosvm` 作为 vhost-user frontend 连接该 socket，并发送 `SET_OWNER`、`SET_MEM_TABLE`、`SET_VRING_NUM`、`SET_VRING_ADDR`、`SET_VRING_BASE`、`SET_VRING_KICK`、`SET_VRING_CALL` 等控制消息。
3. `vhost-user-qti` 在用户态接收这些消息。对于 `SET_MEM_TABLE`，它会 `mmap()` qcrosvm 传入的共享内存 fd；对于 `SET_VRING_ADDR`，它会把 frontend 视角的 ring 地址转换为自身地址空间中的有效地址。
4. 完成地址转换后，`vhost-user-qti` 把配置翻译成 `/dev/vhost-disp` 的 `VHOST_SET_MEM_TABLE`、`VHOST_SET_VRING_ADDR`、`VHOST_SET_VRING_KICK`、`VHOST_SET_VRING_CALL` 等 ioctl，交给 Host 内核中的 `hab_vhost.c`。
5. 一旦内核 backend 获得 vring 地址和 kick/call eventfd，后续 Guest `virtqueue_kick` 会直接唤醒 Host 内核 worker；Host 回包也直接通过 irqfd / KVM 注入 Guest 中断。此后 `vhost-user-qti` 只在 reset、停机、重连等生命周期事件里继续处理控制消息。

这就是为什么 `/tmp/linux-vm2-disp-skt` 只承载**设备建链和生命周期控制消息**，而不承载每一帧显示命令 payload。稳态显示数据的热路径仍然是：

```text
Guest HAB 内核 -> virtio vring -> Host HAB vhost 内核 -> HAB 框架 -> display-be
```

### 4.3 HAB 通道与 MMID 映射

Guest DRM 驱动在 `virtio_kms_probe()` 中打开两条 HAB 通道：

```c
// virtio_kms.c:3458-3459
kms->mmid_cmd   = MM_DISP_1;   // 301 - 命令通道
kms->mmid_event = MM_DISP_3;   // 303 - 事件通道
```

HAB virtio 传输层将 MMID 映射到 virtio device ID：

```c
// hab_virtio.c:47
{ MM_DISP_1, HAB_VIRTIO_DEVICE_ID_DISPLAY, NULL },  // device-id=93
```

display-be 的 `config.xml` 中对应配置：

```xml
<HABChannel>
    <Packet><ID> 301 </ID></Packet>    <!-- 命令通道, 对应 MM_DISP_1 -->
    <Event><ID> 303 </ID></Event>      <!-- 事件通道, 对应 MM_DISP_3 -->
    <Buffer><ID> 301 </ID></Buffer>    <!-- 缓冲区共享, 复用命令通道 -->
</HABChannel>
```

### 4.4 命令通道: virtio_hab_send_and_recv()

这是显示命令路径的核心函数 (`virtgpu_vq.c:62`)。所有 DRM 命令（scanout 属性查询、DPU 上电、帧提交等）都通过此函数同步收发。

#### 发送阶段

```c
// virtgpu_vq.c:83-84
rc = habmm_socket_send(hab_socket, req, req_size,
    (lock_flag == SPIN_LOCK_CHANNEL ?
        HABMM_SOCKET_SEND_FLAGS_NON_BLOCKING : 0x00));
```

- **绝大多数调用** (约 30 个调用点中的 29 个) 使用 `NO_SPIN_LOCK_CHANNEL`，即 **flags=0 (阻塞发送)**
- **唯一例外**: `VIRTIO_GPU_CMD_EVENT_CONTROL` (VSync 使能/禁止) 使用 `SPIN_LOCK_CHANNEL`，因为上层 `drm_vblank_enable` 持有 spinlock，不能再获取 mutex

#### 接收阶段 (NON_BLOCKING 轮询 + 重试)

```c
// virtgpu_vq.c:98-134
retry_times = 0;
retry_recv_packet:
    delay = jiffies + (HZ / 4);          // 250ms 窗口
    do {
        rc = habmm_socket_recv(hab_socket, resp, &size,
            HAB_NO_TIMEOUT_VAL,
            HABMM_SOCKET_RECV_FLAGS_NON_BLOCKING);
    } while (time_before(jiffies, delay) && (-EAGAIN == rc) && (size == 0));

    if (rc) {
        if ((rc == -EAGAIN) && (retry_times < MAX_SEND_RECV_PACKET_RETRY)) {
            retry_times++;
            VIRTGPU_VQ_WARN("recv packet retry %d", retry_times);
            goto retry_recv_packet;      // 重新开始 250ms 窗口
        }
        rc = -1;                          // 全部重试耗尽
        goto end;
    }
```

**超时计算**: 1 次初始轮询 + 10 次重试 = **11 个 250ms 窗口 = 约 2.75 秒**。

日志中的典型表现：

```
08:00:48.563 [drm:virtgpu-vq:virtio_hab_send_and_recv:129] recv packet retry 1
...
08:00:50.795 [drm:virtgpu-vq:virtio_hab_send_and_recv:129] recv packet retry 10
08:00:51.043 [drm:virtgpu-vq:virtio_gpu_cmd_get_scanout_hw_attributes:2316]
    send_and_recv failed for SCANOUT_HW_ATTRIBUTE -1
```

### 4.5 事件通道: 长轮询模式

事件通道与命令通道的机制**完全不同**。

Guest 内核线程 `virtio_gpu_event_kthread` (`virtgpu_vq.c:2446`) 在循环中主动发送 `VIRTIO_GPU_CMD_WAIT_EVENTS`，使用的是 `virtio_hab_send_and_recv_timeout()` (`virtgpu_vq.c:150`)：

```c
// virtgpu_vq.c:174-193
rc = habmm_socket_recv(hab_socket, resp, &size,
    2500,                                 // 2500ms 超时
    HABMM_SOCKET_RECV_FLAGS_TIMEOUT);     // 超时阻塞模式
if (rc && max_retries) {
    max_retries--;
    goto retry;                           // 重试时重新发送请求
} else if (rc && !max_retries) {
    rc = habmm_socket_recv(..., (uint32_t)-1, 0);  // 最终: 无限等待
}
```

| 对比项 | 命令通道 | 事件通道 |
|--------|---------|---------|
| 函数 | `virtio_hab_send_and_recv()` | `virtio_hab_send_and_recv_timeout()` |
| HAB MMID | MM_DISP_1 (301) | MM_DISP_3 (303) |
| 发送模式 | 阻塞 (flags=0) | 阻塞 (flags=0) |
| 接收模式 | NON_BLOCKING 紧凑轮询 | TIMEOUT 阻塞 (2500ms) |
| 超时策略 | 250ms 窗口 x 11 = ~2.75s | 2500ms x 10 + 最终无限等待 |
| 调用模式 | 同步请求/响应 | 长轮询 (loop { send + block_recv }) |

收到事件后，Guest 内核线程解析 `virtio_gpu_resp_event` 结构，分别处理三类事件：

```c
// virtgpu_vq.c:2487-2497
if (vsync_count)  virtio_kms_event_handler(kms, i, num, VIRTIO_VSYNC);
if (commit_count) virtio_kms_event_handler(kms, i, num, VIRTIO_COMMIT_COMPLETE);
if (hpd_count)    virtio_kms_event_handler(kms, i, num, VIRTIO_HPD);
```

### 4.6 协议翻译: virtio-gpu -> OpenWFD

display-be (VirtIOGPU2DBackendService) 负责将 Guest 的 virtio-gpu 命令翻译为 OpenWFD 有线协议。关键映射包括：

| virtio-gpu 命令 | OpenWFD 命令 | 说明 |
|----------------|-------------|------|
| 帧提交 (commit) | `DEVICE_COMMIT_EXT` | 携带 dma_buf fd 和图层属性 |
| 事件等待 | 由 `DISP_VSYNC` / `EVENT_NOTIFICATION` 响应 | VSync、热插拔等 |
| scanout 属性查询 | 对应 OpenWFD device/port 查询 | 分辨率、刷新率等 |
| DPU power | 对应 OpenWFD device power 控制 | 上电/下电 |

这些命令名均在 `wire_format.h` 中定义。

### 4.7 Host HAB vhost 内核驱动

`hab_vhost.c` 是数据通道的关键枢纽，每个 HAB physical channel (pchan) 有一对 virtqueue：

```c
// hab_vhost.c:57-61
enum {
    VHOST_HAB_PCHAN_TX_VQ = 0,  // 从 GVM 接收数据
    VHOST_HAB_PCHAN_RX_VQ,      // 向 GVM 发送数据
    VHOST_HAB_PCHAN_VQ_MAX,
};
```

- **TX 路径** (`tx_worker`, `:165`): 调用 `vhost_get_vq_desc` 从 TX vring 获取 Guest 发来的 HAB 消息，通过 `iov_iter` 读取 payload，投递到 HAB 框架
- **RX 路径** (`rx_worker`, `:157`): 将 HAB 框架的回复消息写入 RX vring，调用 `vhost_signal` 触发 irqfd，KVM 直接向 Guest 注入中断

queue-num=10 意味着 5 个 physical channel，每个有 TX+RX 一对 virtqueue。

## 5. vhost-user-disp.service 与 systemd 依赖

```
openwfd_server_@0.service  openwfd_server_@1.service
           |                       |
           +----------+------------+
                      |
            vhost-user-disp.service
            (vhost-user-qti, 监听 socket)
                      |
             display-be.service
             (VirtIOGPU2DBackendService)
                      |
              qcrosvm.service
              (启动 Android GVM)
```

`vhost-user-disp.service` 的关键配置可概括为：

```ini
[Service]
ExecStart = /usr/bin/vhost-user-qti -s /tmp/linux-vm2-disp-skt -d /dev/vhost-disp -q 10
Type=notify
```

- `-s /tmp/linux-vm2-disp-skt`: 创建供 `qcrosvm --vhost-user-hab` 连接的 Unix domain socket
- `-d /dev/vhost-disp`: 指向 Host 内核 display vhost 设备，所有 `VHOST_SET_*` / `VHOST_GET_*` ioctl 都打到这里
- `-q 10`: 暴露 10 条 virtqueue；结合 `hab_vhost.c` 中 TX/RX 成对的设计，对应 5 个 physical channel
- `Type=notify`: 只有当 `vhost-user-qti` 完成 `bind()` / `listen()` 并显式通知 `READY=1` 后，systemd 才认为服务 ready，从而避免 `qcrosvm` 提前连接 socket 失败

从 systemd 角色分工看，`vhost-user-disp.service` 的作用有三层：

- **建链前置条件**: 在 Guest 启动前准备好 vhost-user socket 和 `/dev/vhost-disp` 控制桥，保证 qcrosvm 能顺利完成 virtio display 设备初始化
- **协议适配层**: 把通用的 vhost-user frontend 协议转换成 Qualcomm 私有的 display vhost 内核 ioctl ABI
- **生命周期守护进程**: 在 VM reset、停机或重新连接时继续保活，处理 `GET_VRING_BASE`、`RESET_OWNER` 等控制事件；但它不是 steady-state 帧数据的转发进程

关键依赖关系 (从 systemd unit 文件提取)：

- `display-be.service`: `Requires=vhost-user-disp.service`, `After=openwfd_server_@0/1.service vhost-user-disp.service`
- `qcrosvm_sa8797.service`: `Requires=vhost-user-disp.service`, `After=display-be.service`

## 6. 故障模式: recv 重试耗尽导致黑屏

当 Host 侧 display-be 或 openwfd_server 未能及时响应时，Guest 侧 `virtio_hab_send_and_recv()` 的重试机制会耗尽，导致级联失败：

```
virtio_hab_send_and_recv() 返回 -1
    -> virtio_gpu_cmd_get_scanout_hw_attributes() 失败
    -> virtio_kms_scanout_init() 失败
    -> _virtio_kms_hw_init() 失败
    -> virtio_kms_probe() 失败
    -> DRM 设备未创建 (无 "Initialized msm_drm")
    -> SDM HAL DRMMaster instance 0 获取失败
    -> CoreInterface 创建失败
    -> HWC 注册 binder 但内部指针为 null
    -> SurfaceFlinger registerCallback 触发 SIGSEGV
    -> 无限 crash 循环 (~5秒/次)
```
