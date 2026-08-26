+++
date = '2026-08-26T16:30:00+08:00'
draft = false
title = 'VMM Service 架构总览'
description = 'VMM Service 的系统边界、核心组件、主要数据流及专题 Wiki 导航'
categories = ['Qualcomm', 'Gunyah', '虚拟化']
tags = ['VMM', 'Gunyah', 'qcrosvm', 'PVM', 'GVM']
+++

VMM Service 是 Qualcomm Gunyah 平台上的 Guest VM 生命周期管理服务。本页说明系统边界、核心组件和主要数据流，并作为各专题 Wiki 的入口。

## 1. 核心职责

- 启动、停止和重启 Guest VM。
- 监控 qcrosvm systemd unit 与 Gunyah VM 事件。
- 通过状态机维护 VM 运行状态。
- 向 Boot LCM、Ramdump 和电源管理组件分发事件。
- 协调启动重试、recovery 入口及 ramdump 收集。
- 管理客户端连接、事件订阅和 ACK。

## 2. 系统架构

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           VMM Clients                                   │
│  vmm-boot-lcm   vmm-ramdump   QC-PM   vhost-user-q   OEM PM services    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                  Unix Domain Socket + SCM_RIGHTS
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                         vmm-lib                                         │
│        connect | subscribe | unsubscribe | VM control | event ACK       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                         vmm-drv                                         │
│                                                                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────────────┐   │
│  │ Message Server │  │ VM State       │  │ Deferred Subscription    │   │
│  │ epoll + socket │  │ Machine        │  │ Worker                   │   │
│  └────────────────┘  └────────────────┘  └──────────────────────────┘   │
│                                                                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────────────┐   │
│  │ systemd sd-bus │  │ Gunyah uevent  │  │ Per-VM Context           │   │
│  │ Monitor        │  │ Monitor        │  │ state + subscribers      │   │
│  └────────────────┘  └────────────────┘  └──────────────────────────┘   │
└───────────────┬───────────────────┬───────────────────┬─────────────────┘
                │                   │                   │
        ┌───────▼──────┐    ┌───────▼──────┐    ┌───────▼────────┐
        │ systemd      │    │ Gunyah       │    │ vm_config.xml  │
        │ qcrosvm unit │    │ hypervisor   │    │ la_misc        │
        └──────────────┘    └──────────────┘    └────────────────┘
```

## 3. 核心组件

### 3.1 VMM Service

| 组件 | 作用 |
|------|------|
| `vmm-drv` | 服务端守护进程，管理 VM 状态、客户端和事件分发 |
| `vmm-lib` | 客户端 API、消息协议和配置解析 |
| `vmm-ramdump` | 订阅 watchdog 事件并归档 Gunyah dump |
| `vmm-test` | VMM API 测试工具 |

代码目录：

```text
vendor/qcom/proprietary/vmm-service-noship/
  +-- vmm-drv/
  +-- vmm-lib/
  +-- vmm-ramdump/
  +-- vmm-test/
```

### 3.2 外部组件

| 组件 | 作用 |
|------|------|
| `vmm-boot-lcm` | VM 首次启动、retry 和 recovery 管理 |
| `qcrosvm` | 创建并承载 GVM |
| `vhost-user-q` | HAB/vhost-user 通道 |
| `QC-PM` | 平台电源管理 |
| `oem-pm-bsp` | OEM suspend、resume 和 shutdown 协调 |
| GVM boot control HAL | 维护 GVM A/B slot 状态 |
| GVM ABL | 选择启动 slot 和 recovery 模式 |

## 4. 控制面与事件面

VMM Service 的 IPC 分为两个逻辑通道：

| 通道 | 用途 | 传输方式 |
|------|------|----------|
| 控制通道 | connect、subscribe、VM control | 服务端 Unix Domain Socket |
| 事件通道 | VM event、ACK | `socketpair()`，通过 `SCM_RIGHTS` 传 fd |

客户端使用 `vmm-lib` 建立连接。服务端将每个订阅保存到对应 VM 的优先级链表中，并在状态转换时按 `LEVEL_0`～`LEVEL_4` 发送通知。

详见 [VMM Service IPC 与客户端模型](vmm-service-ipc.md)。

## 5. VM 运行时

每个 VM 对应一个 `gvm_context_t`，包含：

- VM ID、名称和 qcrosvm systemd unit。
- 当前状态、前一状态和待处理事件。
- 状态机、sd-bus、udev 和延迟订阅线程。
- 按优先级组织的事件订阅者。
- systemd container 状态与 Guest 退出原因。

运行时事件链：

```text
Gunyah uevent
  -> parse guest exit reason
  -> store in per-VM context

systemd PropertiesChanged
  -> read container state and guest exit reason
  -> create state-machine event
  -> execute state transition
  -> notify subscribed clients
```

详见 [VMM Service 运行时架构](vmm-service-runtime.md)。

## 6. VM 启动链路

启用了 `vmm_boot_lcm_enable` 的 VM 由 Boot LCM 管理：

```text
vmm-boot-lcm
  -> read vm_config.xml
  -> read la_misc boot-success handshake
  -> request VM_CONTROL_START
  -> vmm-drv state machine
  -> systemd starts qcrosvm.service
  -> qcrosvm exposes boot/current/backup/misc disks
  -> GVM firmware selects slot and boot mode
```

连续启动未确认成功时，Boot LCM 递减 retry counter；counter 耗尽后向 `la_misc` 写入 `boot-recovery`，由 GVM ABL 在下一次启动中进入 recovery。

相关专题：

- [VMM Boot Lifecycle Manager](vmm-boot-lifecycle.md)
- [GVM Slot 管理](gvm-slot-management.md)
- [la_misc 接口](la-misc-interface.md)

## 7. 配置边界

`/etc/vm_config.xml` 定义：

- VM 数量、名称和 VM ID。
- qcrosvm systemd service。
- Boot LCM 开关和 retry count。
- `la_misc` partlabel。
- Slot 对称/非对称模式。
- Ramdump 类型。

配置由多个组件共享，详见 [VMM Service 配置](vmm-service-configuration.md)。

## 8. Ramdump

`vmm-ramdump` 同步订阅 `GVM_WDOG_BITE`，从 `/sys/kernel/debug/${GVM_NAME}/` 读取 dump，并通过 libarchive 生成 full dump 或 minidump 压缩包。

详见 [VMM Ramdump 服务](vmm-ramdump-service.md)。

## 9. Wiki 导航

| 文档 | 主要内容 |
|------|----------|
| [VMM Service 配置](vmm-service-configuration.md) | `vm_config.xml`、字段语义和消费者 |
| [VMM Service 运行时架构](vmm-service-runtime.md) | 数据结构、线程、FSM、sd-bus、udev、systemd |
| [VMM Service IPC 与客户端模型](vmm-service-ipc.md) | 消息协议、订阅、事件、ACK 和重连 |
| [VMM Boot Lifecycle Manager](vmm-boot-lifecycle.md) | 首次启动、retry、VM down 重启和 recovery |
| [GVM Slot 管理](gvm-slot-management.md) | PVM/GVM A/B、current/bak 装配和 `ActiveSlot` |
| [la_misc 接口](la-misc-interface.md) | BCB、`reserved[0..6]`、读写组件和清理语义 |
| [VMM Ramdump 服务](vmm-ramdump-service.md) | watchdog 订阅、dump 采集和归档 |
