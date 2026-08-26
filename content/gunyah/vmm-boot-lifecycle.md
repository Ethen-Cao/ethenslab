+++
date = '2026-08-26T16:30:00+08:00'
draft = false
title = 'VMM Boot Lifecycle Manager'
description = 'GVM 首次启动、启动成功握手、重试及 recovery 管理机制'
categories = ['Qualcomm', 'Gunyah', '虚拟化']
tags = ['VMM', 'Boot LCM', 'GVM', 'recovery', 'qcrosvm']
+++

本文说明 `vmm-boot-lcm` 如何管理 GVM 的首次启动、运行状态确认、自动重启和 recovery 入口。

## 1. 组件职责

`vmm-boot-lcm` 是 VMM Service 的 `LEVEL_0` 客户端。其职责包括：

- 启动启用了 LCM 的 GVM。
- 监听 VM up/down 及 shutdown 类事件。
- 根据 `la_misc` 中的启动成功状态维护 retry counter。
- 连续启动未成功时写入 recovery BCB。
- 在 VM down 后重新发起 START 请求。

VM 是否由 LCM 管理由 `/etc/vm_config.xml` 中的 `vmm_boot_lcm_enable` 决定。

## 2. 初始化流程

```text
vmm_boot_lcm_init()
  -> libabctl_getBootSlot()
  -> vm_config_init()
  -> load enabled VM contexts
  -> vmm_client_connect("vmm-boot-lcm")
  -> subscribe lifecycle events
  -> create one event-loop thread per managed VM
```

LCM 订阅以下事件：

```c
GVM_SHUTDOWN_LEVEL_0 |
GVM_SHUTDOWN_LEVEL_1 |
GVM_EVENT_UP |
GVM_EVENT_DOWN |
GVM_EVENT_FATAL_ERROR
```

## 3. VM 上下文

每个受管 VM 保存以下信息：

| 数据 | 来源 | 用途 |
|------|------|------|
| `vmid`、`vm_name` | `vm_config.xml` | 标识 VM |
| `retry_cnt` | `lcm_retry_count` | 当前剩余重试次数 |
| `misc_partition_path` | `misc_partition` | 读取启动状态、写 recovery BCB |
| `slot_switch_config` | `slot_switch_config` | Slot 模式 |
| `host_boot_slot` | `libabctl_getBootSlot()` | 记录 PVM 当前 slot |
| `lcm_socket_fd` | VMM subscription | 接收 VM 生命周期事件 |

## 4. 启动控制

`control_vm(START_GUEST)` 在发送 START 前调用 `check_gvm_boot_slot_info()`：

```c
struct boot_slot_info {
    int  recovery_flag;
    char current_slot;
    char target_slot;
    char bootable_status;
};
```

其中 `bootable_status` 对应 `bootloader_message.reserved[2]`，是 LCM 启动判定实际使用的字段：

| 值 | LCM 行为 |
|----|----------|
| `'y'` | 上次启动成功，恢复 `retry_cnt` 为配置值 |
| 其他 | 上次启动尚未确认成功，递减 `retry_cnt` |

`current_slot`、`target_slot` 和 `recovery_flag` 在当前 START 分支中用于状态记录，不参与 START 请求决策。

VMM 控制消息只包含 VM ID 和命令：

```c
typedef struct vmm_vm_ctrl_msg {
    uint32_t vmid;
    vm_state_ctrl_t vm_cmd;
} vmm_vm_ctrl_msg_t;
```

Slot 不通过 VMM IPC 传递。qcrosvm 的磁盘参数和 GVM firmware 共同完成启动分区选择。

## 5. Retry 与 Recovery

```text
START_GUEST
  -> read reserved[2]
  -> 'y'     : reset retry counter
  -> not 'y' : decrement retry counter
       -> counter > 0 : send VM_CONTROL_START
       -> counter = 0 : write recovery BCB
                        send VM_CONTROL_START
```

retry counter 耗尽时，`do_failure_recovery()` 调用 `set_gvm_recovery_cmd("recovery")`，向 `la_misc` 写入：

```text
command  = "boot-recovery"
recovery = "recovery"
```

GVM ABL 的 `RecoveryInit()` 检查 `command`。匹配 `boot-recovery` 后设置 recovery 启动模式；普通 recovery 入口不要求 `recovery` 字段包含 wipe 参数。

## 6. 事件循环

```text
vmm_lcm_event_loop
  -> control_vm(START_GUEST)
  -> wait for lifecycle event
  -> GVM_EVENT_DOWN
       -> control_vm(START_GUEST)
  -> repeat
```

LCM 负责“何时重新启动”，`vmm-drv` 状态机负责“如何执行 START/STOP/RESTART 并通知其他客户端”。

## 7. 启动成功握手

GVM userspace 的 QTI boot control HAL 在 `mark_boot_successful()` 中写入：

- `reserved[2]='y'`：供 Boot LCM 判断启动成功。
- Slot A 使用 `reserved[3]='y'`。
- Slot B 使用 `reserved[5]='y'`。

下一次 LCM 启动检查读到 `reserved[2]='y'` 后恢复 retry counter。

## 8. 相关文档

- [VMM Service 架构总览](vmm-service-architecture.md)
- [VMM Service IPC](vmm-service-ipc.md)
- [GVM Slot 管理](gvm-slot-management.md)
- [la_misc 接口](la-misc-interface.md)
