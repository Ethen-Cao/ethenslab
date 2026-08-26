+++
date = '2026-08-26T16:30:00+08:00'
draft = false
title = 'VMM Service 运行时架构'
description = 'VMM Service 的运行时数据结构、线程模型、状态机及事件源'
categories = ['Qualcomm', 'Gunyah', '虚拟化']
tags = ['VMM', 'FSM', 'systemd', 'sd-bus', 'uevent']
+++

本文说明 `vmm-drv` 的运行时数据、线程模型、状态机、外部事件源以及 systemd 集成。

## 1. 运行时组件

`vmm-drv` 为每个 GVM 创建独立的运行上下文和状态机，同时使用一个全局消息线程处理客户端连接。

```text
vmm_service
  |
  +-- message_process_thread
  |     +-- accept clients
  |     +-- epoll message dispatch
  |
  +-- per-VM runtime
        +-- state_machine_thread
        +-- sd_bus_monitor_thread
        +-- udev_monitor_thread
        +-- deferred_list_thread
```

## 2. 核心数据结构

### 2.1 `gvm_context_t`

每个 GVM 对应一个 `gvm_context_t`，主要包含：

| 类别 | 关键字段 | 作用 |
|------|----------|------|
| 标识 | `vmid`、`vm_name`、`systemd_service` | 关联 Gunyah VM 与 qcrosvm unit |
| 状态 | `gvm_state`、`pre_gvm_state`、`sm_event`、`sm_state` | 保存状态机上下文 |
| 线程 | `sdbus_thread`、`uevent_thread`、`sm_thread`、`def_list_thread` | 每 VM 工作线程 |
| 同步 | mutex、condition variable、barrier | 协调事件源和状态转换 |
| 订阅 | `notify_client_heads[MAX_LEVEL]` | 按优先级保存事件订阅者 |
| 延迟操作 | `def_add_head`、`def_del_head`、`def_sem` | 延迟添加或删除订阅者 |
| LCM | `lcm_socket_fd`、`vmm_boot_lcm_enable` | 与 Boot LCM 协作 |
| Container | `active_state`、`sub_state`、`service_result` | 保存 systemd unit 状态 |

### 2.2 `event_subscription_t`

一个订阅实例表示“某客户端对某 VM 的一组事件订阅”：

```c
typedef struct event_subscription {
    int socket_fd;
    char name[MAX_VMM_CLIENT_NAME_SIZE];
    volatile bool notif_send;
    uint32_t level;
    uint32_t vmid;
    uint32_t eventmsk;
    gvm_context_t *owner_gvm;
    vmm_dlist_node_t notify_node;
    vmm_dlist_node_t def_add_node;
    vmm_dlist_node_t def_del_node;
} event_subscription_t;
```

### 2.3 `vmm_drv_data_t`

`vmm_drv_data_t` 保存进程级资源：VM 数量、监听 socket、客户端哈希表、启动 barrier 和 GVM 上下文链表。

## 3. 线程模型

| 线程 | 数量 | 职责 |
|------|------|------|
| `vmm_service_message_process_thread` | 全局 1 个 | 接收连接、处理 IPC 请求 |
| `vmm_state_machine_thread` | 每 VM 1 个 | 消费内部事件并执行状态转换 |
| `vmm_sdb_monitor_thread` | 每 VM 1 个 | 监控 qcrosvm systemd unit |
| `vmm_udev_monitor_thrd` | 每 VM 1 个 | 解析 Gunyah uevent |
| `vmm_defer_process_list_thread` | 每 VM 1 个 | 处理订阅者延迟增删 |

主要同步机制：

- `threads_barrier` 等待状态机、sd-bus 和 udev 线程就绪。
- condition variable 用于事件到达、VM 退出和状态机空闲通知。
- mutex 保护 VM 状态、订阅链表和延迟操作链表。
- semaphore 唤醒延迟操作线程。

## 4. VM 状态机

### 4.1 状态

```text
VM_STOPPED
    |
    | CTRL_START_GVM
    v
VM_PRE_RESTART
    |
    | UP_AND_RUNNING
    v
VM_HEALTHY
    |
    +-- WDOG_BITE ------------> VM_CRASHED_CONTAINER --+
    +-- CONTAINER_CRASH ------> VM_HANDLED_CONTAINER_CRASH --+
    +-- HYPERVISOR_ERROR -----> VM_HANG -----------------+
    +-- CTRL_STOP / SHUTDOWN -> VM_STOPPED               |
                                                          |
                         RESTART <-------------------------+
                            |
                            v
                      VM_PRE_RESTART
```

`VM_CRASHED_CONTAINER` 与 `VM_HANDLED_CONTAINER_CRASH` 是从 `VM_HEALTHY` 出发的并行分支。`VM_SUSPEND` 和 `VM_IRRECOVERABLE_STATE` 没有注册转换处理函数，属于终态。

### 4.2 状态机事件

| 事件 | 来源 | 含义 |
|------|------|------|
| `VMM_SM_EVENT_QCROSVM_CONTAINER_CRASH` | sd-bus | Container 退出 |
| `VMM_SM_EVENT_HANDLED_CONTAINER_CRASH` | sd-bus | 已由上层处理的 Container 退出 |
| `VMM_SM_EVENT_GVM_SHUTDOWN_SELF` | Gunyah uevent | Guest 主动关机 |
| `VMM_SM_EVENT_GVM_RESTART_SELF` | Gunyah uevent | Guest 主动重启 |
| `VMM_SM_EVENT_GVM_WDOG_BITE` | Gunyah uevent | Guest watchdog |
| `VMM_SM_EVENT_GUNYA_HYP_ERR` | Gunyah uevent | Hypervisor 错误 |
| `VMM_SM_EVENT_CTRL_RESTART_GVM` | IPC client | 外部重启命令 |
| `VMM_SM_EVENT_CTRL_STOP_GVM` | IPC client | 外部停止命令 |
| `VMM_SM_EVENT_CTRL_START_GVM` | IPC client | 外部启动命令 |

### 4.3 主循环

```text
wait_on_event_cond
  -> transition_lookup(current_state, event)
  -> state_handler(context, event)
  -> notify subscribed clients by priority
  -> notify Boot LCM
  -> wait for next event
```

客户端通知由各状态处理函数调用 `vmm_send_notif_rcv_ack()` 完成；Boot LCM 通知由状态机主循环调用 `vmm_send_event_to_lcm_sync()` 完成。

## 5. 外部事件源

### 5.1 systemd sd-bus

`vmm_sdb_monitor_thread()` 监听 qcrosvm unit 的 `PropertiesChanged`：

| 属性 | 用途 |
|------|------|
| `ActiveState` | 判断 unit 是否 active、inactive 或 failed |
| `SubState` | 判断进程处于 running、exited、dead 等状态 |
| `Result` | 获取退出结果，如 success、exit-code、signal |

sd-bus 线程读取由 udev 线程保存的 `guestos_exit_reason`，再通过 `vmm_convert_vm_exit_reason_to_sm_event()` 生成状态机事件。

### 5.2 Gunyah uevent

`vmm_udev_monitor_thrd()` 通过 `NETLINK_KOBJECT_UEVENT` 接收 Gunyah 事件：

| uevent 值 | 内部退出原因 | 状态机事件 |
|-----------|--------------|------------|
| `shutdown` | `GUESTOS_EXIT_CAUSE_SHUTDOWN` | `GVM_SHUTDOWN_SELF` |
| `restart` | `GUESTOS_EXIT_CAUSE_RESTART` | `GVM_RESTART_SELF` |
| `nswd` | `GUESTOS_EXIT_CAUSE_NSWD` | `GVM_WDOG_BITE` |
| `hperr` | `GUESTOS_EXIT_CAUSE_HYP_ERR` | `GUNYA_HYP_ERR` |
| `panic` 或其他 | `GUESTOS_EXIT_CAUSE_PANIC` | `QCROSVM_CONTAINER_CRASH` |

udev 负责解释 Guest 退出原因；sd-bus 负责确认承载 VM 的 systemd unit 状态，两者共同构成状态机输入。

## 6. systemd 集成

`vmm_drv.service` 使用 `Type=notify`，主进程完成初始化后调用 `sd_notify("READY=1")`。

```ini
[Unit]
After=systemd-modules-load.service tmp.mount
Conflicts=shutdown.target
Before=shutdown.target
DefaultDependencies=no

[Service]
Type=notify
NotifyAccess=main
ExecStart=/usr/bin/vmm_service
```

启动关系：

```text
systemd-modules-load.service + tmp.mount
  -> vmm_drv.service
       -> sd_notify(READY=1)
       -> VMM clients connect and subscribe
```

关机时，systemd 在进入 `shutdown.target` 前停止 `vmm_drv`。服务关闭监听 socket 并移除 Unix socket 路径；启用重连功能的客户端在连接断开后重新连接。

## 7. 相关文档

- [VMM Service 架构总览](vmm-service-architecture.md)
- [VMM Service 配置](vmm-service-configuration.md)
- [VMM Service IPC](vmm-service-ipc.md)
- [Boot Lifecycle Manager](vmm-boot-lifecycle.md)
