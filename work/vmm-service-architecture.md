# VMM Service 软件架构文档

> **版本**: 基于 Jira IVI8397-3583 patch (2026-06-11)
> **平台**: Qualcomm SA8797 (IVI8397)
> **版权**: Qualcomm Technologies, Inc. / PATEO

---

## 1. 概述

### 1.1 什么是 VMM Service

VMM (Virtual Machine Manager) Service 是 Qualcomm 平台上用于管理 **Guest VM (GVM)** 生命周期的核心系统服务。它通过 qcrosvm/svm 管理虚拟机的启动、停止、监控和故障恢复，负责协调 Guest OS（如 Android Automotive）与 Host OS 之间的交互。

### 1.2 核心职责

- **VM 生命周期管理**: 启动、停止、重启 Guest VM
- **健康状态监控**: 监控 VM 运行状态（正常/崩溃/挂起/看门狗等）
- **事件通知分发**: 将 VM 状态变化事件通知给已订阅的客户端
- **Ramdump 收集**: VM 异常退出时收集内存 dump 信息
- **与 systemd 集成**: 通过 sd-bus 监控 systemd container service 状态
- **关机时序管理**: 确保关机时服务正确清理

---

## 2. 系统架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VMM Service 架构                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        VMM Clients (客户端)                           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │vmm-boot  │ │  vmm-    │ │  QC-PM   │ │  vhost-  │ │ voyahpm- │   │   │
│  │  │  -lcm    │ │ ramdump  │ │          │ │  user-q  │ │   bsp    │   │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘   │   │
│  └───────┼────────────┼────────────┼────────────┼────────────┼──────────┘   │
│          │            │            │            │            │              │
│          │   Unix Domain Socket + SCM_RIGHTS (fd 传递)                      │
│          │            │            │            │            │              │
│  ┌───────┴────────────┴────────────┴────────────┴────────────┴──────────┐   │
│  │                     vmm_client_lib (vmm-lib)                          │   │
│  │   提供 vmm_client_connect / subscribe / unsubscribe / vm_ctrl API    │   │
│  └───────────────────────────────┬──────────────────────────────────────┘   │
│                                  │                                          │
│  ┌───────────────────────────────┴──────────────────────────────────────┐   │
│  │                     VMM Service Daemon (vmm-drv)                      │   │
│  │                                                                       │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │   │
│  │  │ Message Server  │  │  State Machine  │  │  sd-bus Monitor     │   │   │
│  │  │    Thread       │  │  (FSM) Thread   │  │     Thread          │   │   │
│  │  │ (epoll + Unix   │  │ (per VM state   │  │ (systemd container  │   │   │
│  │  │  Domain Socket) │  │  transitions)   │  │  service 监控)      │   │   │
│  │  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘   │   │
│  │           │                    │                       │              │   │
│  │  ┌────────┴────────────────────┴───────────────────────┴──────────┐   │   │
│  │  │                    gvm_context_t (per-VM)                       │   │   │
│  │  │  - 事件通知链表 (按优先级 LEVEL_0 ~ LEVEL_4)                    │   │   │
│  │  │  - VM 状态追踪    - defer add/del 延迟队列处理                  │   │   │
│  │  └──────────────────────────────┬──────────────────────────────────┘   │   │
│  │                                 │                                      │   │
│  │  ┌─────────────────┐  ┌────────┴────────┐                             │   │
│  │  │  udev Monitor   │  │  Defer List     │                             │   │
│  │  │     Thread      │  │  Process Thread │                             │   │
│  │  │ (Gunyah hyper-  │  │ (延迟添加/删除  │                             │   │
│  │  │  visor uevent)  │  │  通知订阅者)    │                             │   │
│  │  └─────────────────┘  └─────────────────┘                             │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│  ┌───────────────────────────────┴──────────────────────────────────────┐   │
│  │                      外部依赖 / 事件源                                 │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐     │   │
│  │  │ systemd  │  │ Gunyah   │  │ debugfs  │  │  vm_config.xml   │     │   │
│  │  │ sd-bus   │  │ hypervisor│ │ ramdump  │  │  (VM 配置)       │     │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 模块划分

VMM Service 代码仓库位于 `vendor/qcom/proprietary/vmm-service-noship/`，分为以下模块：

```
vmm-service-noship/
├── vmm-drv/                    # VMM 服务守护进程 (vmm_drv)
│   ├── include/
│   │   ├── vmm_drv.h           # 核心数据结构 (gvm_context, vmm_client, event_subscription)
│   │   ├── vmm_fsm.h           # 状态机定义 (事件/状态/转换)
│   │   ├── vmm_sd_bus.h        # systemd sd-bus 接口定义
│   │   ├── vmm_guestos_event.h # Guest OS 退出原因枚举
│   │   ├── vmm_udev.h          # udev monitor 接口
│   │   └── vmm_util.h          # 双向链表、哈希表工具
│   ├── src/
│   │   ├── vmm_drv.c           # 主程序：消息服务器、客户端管理、事件分发
│   │   ├── vmm_fsm.c           # VM 状态机实现
│   │   ├── vmm_sd_bus.c        # systemd sd-bus 监控实现
│   │   ├── vmm_udev.c          # Gunyah hypervisor uevent 监控
│   │   └── vmm_util.c          # 链表/哈希表工具实现
│   └── vmm_drv.service         # systemd service unit
│
├── vmm-lib/                    # VMM 客户端库 (vmm_clib)
│   ├── include/
│   │   ├── vmm_clib.h          # 客户端 API 声明
│   │   ├── vmm_clt_cfg.h       # 客户端优先级定义
│   │   ├── vmm_common.h        # 公共数据结构、消息类型、常量
│   │   ├── vmm_events.h        # GVM 事件类型定义
│   │   ├── vmm_log.h           # 日志宏 (syslog)
│   │   ├── vmm_vmctrl.h        # VM 控制 API 声明
│   │   └── vm_config.h         # VM XML 配置读取接口
│   ├── vmm-client/
│   │   └── vmm_clib.c          # 客户端库核心实现
│   └── vmm-utils/
│       └── vm_config.c         # VM XML 配置解析
│
├── vmm-ramdump/                # Ramdump 收集服务
│   ├── src/
│   │   └── vmm-ramdump.c       # ramdump 收集实现
│   └── vmm-ramdump.service     # systemd service unit
│
└── vmm-test/                   # 测试工具
    └── test.c                  # VMM 功能测试应用
```

### 3.1 外部组件

| 组件 | 路径 | 角色 |
|------|------|------|
| **vmm-boot-lcm** | `vendor/qcom/opensource/vmm-boot-lcm/` | Boot Lifecycle Manager — VM 启动恢复策略 |
| **vhost-user-q** | `vendor/qcom/opensource/vhost-user/` | vhost-user 后端，通过 HAB 注册 VMM 事件 |
| **vmm-pwr-key** | `vendor/qcom/proprietary/virtual-power-key/` | 虚拟电源键管理服务 |
| **qc-pm** | `vendor/qcom/proprietary/platform_utils/qc-pm/` | Qualcomm 平台电源管理 |
| **voyahpm-bsp** | `voyah-bsp/voyahpm-bsp/` | Voyah 自定义电源管理 (挂起/恢复/关机/重启) |

### 3.2 VM 配置文件 (`/etc/vm_config.xml`)

#### 3.2.1 生成方式

`vm_config.xml` **不是动态生成的**，而是从源码目录中的 XML 模板在 Yocto 构建时直接复制到目标系统。

**源码模板位置**：`vendor/qcom/opensource/crosvm-gunyah/vm_config_xml/`，共 3 个变体：

| 模板文件 | 选择条件 | VM 数量 | 差异 |
|----------|---------|--------|------|
| `vm_config_la.xml` | 默认（非 `user` 变体、非多 VM 平台）| 1 | 标准 LA VM |
| `vm_config_la_user.xml` | `VARIANT=user` | 1 | 增加 `<ramdump_type>` 元素 |
| `vm_config_lalv.xml` | `sa8255-ivi`, `sa7255-ivi`, `sa8775-flex` | 2 | LA VM + LV VM，LV 的 LCM 关闭 |

**Yocto 配方选择逻辑**（`layers/meta-qti-automotive/recipes-virt/qcrosvm/qcrosvm_git.bb:40-48`）：

```python
# 根据 VARIANT 和机器类型选择模板
VM_CONFIG_XML ?= "${@bb.utils.contains('VARIANT', 'user',
                      'vm_config_la_user.xml', 'vm_config_la.xml', d)}"
VM_CONFIG_XML:sa8255-ivi = "vm_config_lalv.xml"
VM_CONFIG_XML:sa7255-ivi = "vm_config_lalv.xml"
VM_CONFIG_XML:sa8775-flex = "vm_config_lalv.xml"

do_install:append() {
    install -d ${D}${sysconfdir}
    install -m 0644 ${S}/vm_config_xml/${VM_CONFIG_XML} \
        ${D}${sysconfdir}/vm_config.xml
}
```

最终安装为 **`/etc/vm_config.xml`**，解析代码中硬编码此路径（`vm_config.c:42`）：

```c
static const char* VM_CONFIG_FILE = "/etc/vm_config.xml";
```

#### 3.2.2 XML 结构定义

```xml
<?xml version="1.0" encoding="utf-8"?>
<vm_config NUM_VMS="1">                     <!-- 根元素，NUM_VMS 属性定义 VM 总数 -->
  <vm>                                       <!-- 每个 VM 一个 <vm> 块，数量必须与 NUM_VMS 一致 -->
    <vm_name>autoghgvm</vm_name>             <!-- VM 名称，对应 debugfs 路径和日志标识 -->
    <vmid>52</vmid>                          <!-- VM ID，Gunyah hypervisor 使用的 VM 标识符 -->
    <systemd_service>qcrosvm.service</systemd_service>
                                             <!-- 启动该 VM 的 systemd container service 名称 -->
    <vmm_boot_lcm_enable>1</vmm_boot_lcm_enable>
                                             <!-- 1=由 LCM 管理启动/重启; 0=由 vmm-drv 默认启动 -->
    <lcm_retry_count>7</lcm_retry_count>     <!-- 连续启动失败多少次后触发 recovery -->
    <misc_partition>la_misc</misc_partition> <!-- misc 分区 GPT partlabel，用于 slot 状态通信 -->
    <slot_switch_config>1</slot_switch_config>
                                             <!-- 1=SYMMETRIC(对称, GVM 跟随 Host slot) -->
                                             <!-- 2=ASYMMETRIC(非对称, GVM 独立切换 slot) -->
    <ramdump_type>minidump</ramdump_type>    <!-- (可选) full / minidump / disable -->
  </vm>
</vm_config>
```

**元素与解析代码的对应关系**（`vm_config.c:119-142`，`process_content()` 函数按元素名称精确匹配）：

```
XML 元素名               → C 结构体字段
────────────────────────────────────────────
vm_name                 → vm_cfg->vm_name
vmid                    → vm_cfg->vmid
systemd_service         → vm_cfg->systemd_service
vmm_boot_lcm_enable     → vm_cfg->vmm_boot_lcm_enable
lcm_retry_count         → vm_cfg->vmm_boot_lcm_retry_count
misc_partition          → vm_cfg->misc_partition_name
slot_switch_config      → vm_cfg->slot_switch_config
ramdump_type            → vm_cfg->ramdump_type
```

#### 3.2.3 所有消费者及使用的字段

解析库 `vm_config.c` 编译为 `libvmm_utils.so`，提供 `vm_config_init()` 和一系列 `vm_config_get_*()` API。**7 个组件** 调用此库，各自读取不同字段：

```
┌──────────────────────────────────────────────────────────────────────┐
│                      /etc/vm_config.xml                              │
│                            │                                         │
│                      vm_config_init()                                │
│                      (libvmm_utils.so)                               │
│                            │                                         │
│       ┌────────┬────────┬─┴──┬────────┬────────┬────────┐           │
│       ▼        ▼        ▼    ▼        ▼        ▼        ▼           │
│   vmm-boot  vmm-drv  vmm-  vmm-    qc-pm   voyahpm-  disk_        │
│    -lcm             ramdump pwr-key           -bsp   symlink        │
│                                                                      │
│  各消费者及其读取的 vm_config_get_*() API:                            │
│                                                                      │
│  ┌──────────────┬──────────────────────────────────────────────┐     │
│  │ 消费者        │ 读取的字段                                    │     │
│  ├──────────────┼──────────────────────────────────────────────┤     │
│  │ vmm-boot-lcm │ num_vms, vmid, vm_name, vmm_boot_lcm_enable, │     │
│  │              │ lcm_retry_count, slot_switch_config,         │     │
│  │              │ misc_partition                               │     │
│  ├──────────────┼──────────────────────────────────────────────┤     │
│  │ vmm-drv      │ num_vms, vmid, vm_name,                     │     │
│  │              │ vmm_boot_lcm_enable, systemd_service         │     │
│  ├──────────────┼──────────────────────────────────────────────┤     │
│  │ vmm-ramdump  │ num_vms, vmid, vm_name, ramdump_type        │     │
│  ├──────────────┼──────────────────────────────────────────────┤     │
│  │ vmm-pwr-key  │ num_vms, vmid, vm_name                      │     │
│  ├──────────────┼──────────────────────────────────────────────┤     │
│  │ qc-pm        │ num_vms, vmids[] (数组)                      │     │
│  ├──────────────┼──────────────────────────────────────────────┤     │
│  │ voyahpm-bsp  │ num_vms, vmids[] (数组)                      │     │
│  ├──────────────┼──────────────────────────────────────────────┤     │
│  │ disk_symlink │ vmid, slot_switch_config                     │     │
│  └──────────────┴──────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

**关键字段的消费逻辑**：

- **`systemd_service`** — 仅 `vmm-drv` 使用。vmm-drv 通过此名称关联 systemd container service，从而用 sd-bus 监控 VM 的实际运行状态（ActiveState / SubState / Result）。

- **`vmm_boot_lcm_enable`** — `vmm-drv` 和 `vmm-boot-lcm` 使用。当值为 1 时，`vmm-drv` 跳过该 VM 的默认启动（`vmm_drv.c:1124-1129`），交由 LCM 管理生命周期；LCM 也只为此标记为 1 的 VM 创建事件循环线程。

- **`misc_partition`** — `vmm-boot-lcm` 使用。拼接为 `/dev/disk/by-partlabel/<misc_partition>` 作为 GVM 状态通信的共享分区。`disk_symlink` 也有读取 misc slot 的能力，但只在 `slot_switch_config==2` 时生效；当前 `slot_switch_config=1` 配置下仍使用 PVM 的 `androidboot.slot_suffix`。

- **`ramdump_type`** — 仅 `vmm-ramdump` 使用。决定 ramdump 收集策略：`full`（完整 dump）、`minidump`（最小 dump）、`disable`（跳过该 VM）。

---

## 4. 核心数据结构

### 4.1 VM 上下文 (`gvm_context_t`)

每个 Guest VM 由一个 `gvm_context_t` 实例管理，包含 VM 的所有运行时状态：

```c
typedef struct gvm_context {
    // VM 标识
    uint32_t vmid;                          // VM ID
    char vm_name[GVM_NAME_LEN];             // VM 名称
    char systemd_service[NAME_MAX];         // 对应 systemd service 名称

    // 状态管理
    vm_state_t gvm_state;                   // 当前 VM 状态
    vm_state_t pre_gvm_state;               // 前一个 VM 状态
    vmm_sm_event_t sm_event;                // 状态机事件
    vmm_sm_state_t sm_state;                // 状态机状态 (READY/BUSY)

    // 线程句柄
    pthread_t sdbus_thread;                 // sd-bus 监控线程
    pthread_t uevent_thread;                // udev 监控线程
    pthread_t sm_thread;                    // 状态机线程
    pthread_t def_list_thread;              // 延迟处理列表线程

    // 同步原语
    pthread_mutex_t sdbus_update_mutex;     // sd-bus 更新锁
    pthread_cond_t  sdbus_update_condvar;
    pthread_mutex_t uevent_mutex;
    pthread_cond_t wait_on_vm_exited;
    pthread_mutex_t vmm_sm_mutex;
    pthread_cond_t wait_on_event_cond;
    pthread_mutex_t sm_busy_mutex;
    pthread_cond_t wait_on_sm_state;
    pthread_mutex_t vm_mutex;
    pthread_cond_t launch_gvm_cond;
    pthread_barrier_t threads_barrier;      // 线程同步屏障 (3 线程)

    // 事件通知链表 (按优先级)
    vmm_dlist_node_t notify_client_heads[MAX_LEVEL];  // LEVEL_0 ~ LEVEL_4
    pthread_mutex_t notify_list_lock;

    // 延迟处理 (defer add/delete)
    vmm_dlist_node_t def_add_head;
    vmm_dlist_node_t def_del_head;
    pthread_mutex_t def_list_mutex;
    sem_t def_sem;

    // Lifecycle Manager socket
    int lcm_socket_fd;                      // 与 boot-lcm 通信的 fd

    // Container 状态
    gvm_container_status_t gvm_container_status;
    container_unit_load_state_t load_state;
    container_unit_active_state_t active_state;
    container_service_state_t sub_state;
    container_service_result_t service_result;

    // 启动配置
    int32_t vm_starts_by_default;
    int32_t vmm_boot_lcm_enable;            // 是否启用 boot-lcm 管理
    int32_t vm_client_timeout;
} gvm_context_t;
```

### 4.2 事件订阅 (`event_subscription_t`)

```c
typedef struct event_subscription {
    vmm_dlist_node_t notify_node;           // 通知链表节点
    int socket_fd;                          // 与客户端通信的 socket fd
    char name[MAX_VMM_CLIENT_NAME_SIZE];    // 客户端名称
    volatile bool notif_send;               // 通知是否已发送（等待 ACK）
    uint32_t level;                         // 优先级 LEVEL_0~4
    uint32_t vmid;                          // 订阅的 VM ID
    uint32_t eventmsk;                      // 订阅的事件掩码

    gvm_context_t *owner_gvm;               // 所属 GVM
    vmm_dlist_node_t client_node;           // 客户端链表节点
    vmm_dlist_node_t def_del_node;          // 延迟删除节点
    vmm_dlist_node_t def_add_node;          // 延迟添加节点
} event_subscription_t;
```

### 4.3 全局驱动数据 (`vmm_drv_data_t`)

```c
typedef struct vmm_drv_data {
    uint32_t num_gvms;                      // VM 总数
    int32_t server_socket_fd;               // 服务端监听 socket
    vmm_hash_table *hash_table;             // client_sfd -> vmm_client_t 映射
    pthread_barrier_t message_server_barrier; // 启动同步屏障
    vmm_dlist_node_t gvm_ctx_head;          // GVM 上下文链表头
} vmm_drv_data_t;
```

### 4.4 消息封装 (`vmm_msg_wrapper_t`)

```c
typedef struct vmm_msg_wrapper {
    vmm_cmd_msg_t msg;                      // 协议消息体
    union extra_data_t {
        vmm_sub_event_extra_data_t sub_event_extra_data;  // 订阅时携带的 fd
    } extra_data;
} vmm_msg_wrapper_t;

typedef struct vmm_sub_event_extra_data {
    int fdv[MAX_VMM_NUM_VMIDS];             // 客户端传入的 event fd 数组
    int nfds;                               // fd 数量
} vmm_sub_event_extra_data_t;
```

---

## 5. 通信协议

### 5.1 消息格式

VMM Service 使用 **Unix Domain Socket (SOCK_STREAM)** 进行 IPC 通信：

- **服务端 socket**: `/tmp/vmm_service_server`
- **电源管理 socket**: `/tmp/vmm_pwr_mgr_server`
- **客户端 bind 前缀**: `/tmp/vmmcb_`
- **客户端 socket 前缀**: `/tmp/vmmc_`

#### 请求消息 (`vmm_cmd_msg_t`)

```c
typedef struct vmm_cmd_msg {
    struct { vmm_cmd_t msg_type; } hdr;     // 消息类型
    union msg_t {
        vmm_sub_event_msg_t sub_event_msg;  // 订阅事件
        vmm_unsub_event_msg_t unsub_event_msg; // 取消订阅
        vmm_vm_ctrl_msg_t ctrl_msg;         // VM 控制命令
        vmm_pwr_key_msg_t pwr_key_msg;      // 电源键命令
    } data;
} vmm_cmd_msg_t;
```

#### 响应消息 (`vmm_cmd_resp_t`)

```c
typedef struct vmm_cmd_rsp {
    int32_t ret;                            // 返回码 (0=成功, 负值=错误)
} vmm_cmd_resp_t;
```

#### 事件通知消息 (`vmm_client_msg_t`)

```c
typedef struct vmm_client_msg {
    struct { vmm_cmd_t msg_type; } hdr;     // NOTIF_MSG / NOTIF_ACK_MSG
    uint32_t vmid;                          // 事件来源 VM ID
    uint32_t event;                         // 事件类型
} vmm_client_msg_t;
```

### 5.2 消息类型

| 类型 | 值 | 方向 | 说明 |
|------|-----|------|------|
| `SUBSCRIBE_EVENT_MSG` | 0x01 | Client → Server | 订阅 VM 事件通知 |
| `UNSUBSCRIBE_EVENT_MSG` | 0x02 | Client → Server | 取消订阅 |
| `NOTIF_MSG` | 0x03 | Server → Client | 事件通知 |
| `NOTIF_ACK_MSG` | 0x04 | Client → Server | 事件通知确认 |
| `CTRL_CMD_MSG` | 0x05 | Client → Server | VM 控制命令 |
| `PWR_KEY_CMD_MSG` | 0x06 | Client → Server | 电源键命令 |

### 5.3 事件订阅流程（关键变更）

> **重要**: 这是 IVI8397-3583 patch 的核心变更 — 通过 `SCM_RIGHTS` 传递 fd 替代了原来的反向 socket 连接。

```
  Client (vmm-lib)                          Server (vmm-drv)
  ────────────────                          ────────────────
  1. socketpair(AF_UNIX, SOCK_STREAM)
     → socket_pair[0] (保留用于接收事件)
     → socket_pair[1] (发送给 server)

  2. vmm_client_send_with_fds_sync()
     sendmsg(sock, msg + SCM_RIGHTS{fds=socket_pair[1]})
     ──────────────────────────────────────→
                                            3. vmm_recv_wrap_client_msg()
                                               recvmsg() 接收消息 + fd

                                            4. vmm_handle_sub_event_req()
                                               将 socket_pair[1] 保存为
                                               event_sub->socket_fd

  5. vmm_recv_from_server()
     等待响应
     ←──────────────────────────────────────
                                            6. vmm_send_to_client()
                                               返回订阅结果

  后续事件通知:
                                            7. vmm_send_to_client()
     vmm_recv_from_server()                   通过 socket_pair[1]
     ←──────────────────────────────────────  发送 NOTIF_MSG

  8. vmm_send_to_server()
     发送 NOTIF_ACK_MSG
     ──────────────────────────────────────→
```

### 5.4 可靠 I/O 封装

VMM 封装了带 `EINTR` 重试的收发函数：

```c
// 发送（带 EINTR 重试）
int vmm_send_to_client(int sock, const void *data, size_t len);

// 接收消息（带 EINTR 重试 + MSG_TRUNC/MSG_CTRUNC 检测）
int vmm_recvmsg_from_client(int sockfd, struct msghdr *msg, size_t data_len);

// 客户端发送（带 fd 传递的 sendmsg）
static int vmm_send_to_server_with_fds(int sock, const void *buf, size_t len,
                                        const int *fdv, size_t nfd);

// 客户端接收（带长度校验的 recv）
static int vmm_recv_from_server(int sock, void *buf, size_t len);
```

---

## 6. 状态机 (FSM)

### 6.1 VM 状态 (`vm_state_t`)

```
                              ┌───────────────────┐
                              │    VM_STOPPED      │ ← 初始状态 / 已停止
                              └────────┬──────────┘
                                       │ CTRL_START_GVM (handle_start)
                              ┌────────▼──────────┐
                              │  VM_PRE_RESTART    │ ← 准备重启
                              └────────┬──────────┘
                                       │ handle_up_and_running
                              ┌────────▼──────────┐
                   ┌──────────│    VM_HEALTHY      │──────────┐
                   │          └────────┬──────────┘          │
                   │                   │                      │
        WDOG_BITE │    ┌──────────────┼──────────────┐       │ CTRL_STOP_GVM
                  │    │              │              │       │ / SHUTDOWN_SELF
         ┌────────▼──┐ │  ┌───────────▼──┐ ┌────────▼──┐ ┌──▼──────────┐
         │VM_CRASHED │ │  │  VM_HANDLED  │ │  VM_HANG   │ │ VM_STOPPED  │
         │_CONTAINER │ │  │_CONTAINER_CRASH│ │            │ │  (terminal) │
         └─────┬─────┘ │  └──────┬───────┘ └─────┬──────┘ └─────────────┘
               │       │         │               │
               │       │         │    handle_restart (所有这三个状态)
               │       │         │         │
               └───────┴─────────┴─────────┘
                                │
                                ▼
                        VM_PRE_RESTART  (循环回到重启流程)

  异常路径 (vm_client_timeout 导致):
    VM_PRE_RESTART → handle_up_and_running → VM_INVALID_STATE (timeout时)

> **注**：`handle_container_crash()` 返回 `VM_CRASHED_CONTAINER`（非 `VM_IRRECOVERABLE_STATE`），后续事件触发 `handle_restart()` 回到 `VM_PRE_RESTART`。`VM_IRRECOVERABLE_STATE` 在源码过渡表中未注册 handler，属于终态。
```

> **注**: `VM_CRASHED_CONTAINER` 和 `VM_HANDLED_CONTAINER_CRASH` 是从 `VM_HEALTHY` 出发的**两个并行分支**，而非串行转换。两者都通过 `handle_restart` 回到 `VM_PRE_RESTART`。`VM_SUSPEND` 和 `VM_IRRECOVERABLE_STATE` 在源码过渡表中未注册 handler，属于终态。

### 6.2 状态机事件 (`vmm_sm_event_t`)

| 事件 | 来源 | 说明 |
|------|------|------|
| `VMM_SM_EVENT_QCROSVM_CONTAINER_CRASH` | systemd sd-bus | Container 崩溃 |
| `VMM_SM_EVENT_HANDLED_CONTAINER_CRASH` | systemd sd-bus | 已处理的 Container 崩溃 |
| `VMM_SM_EVENT_GVM_SHUTDOWN_SELF` | Gunyah uevent | GVM 主动关机 |
| `VMM_SM_EVENT_GVM_RESTART_SELF` | Gunyah uevent | GVM 主动重启 |
| `VMM_SM_EVENT_GVM_WDOG_BITE` | Gunyah uevent | GVM 看门狗超时 |
| `VMM_SM_EVENT_GUNYA_HYP_ERR` | Gunyah uevent | Hypervisor 错误 |
| `VMM_SM_EVENT_CTRL_RESTART_GVM` | Client 控制 | 客户端请求重启 |
| `VMM_SM_EVENT_CTRL_STOP_GVM` | Client 控制 | 客户端请求停止 |
| `VMM_SM_EVENT_CTRL_START_GVM` | Client 控制 | 客户端请求启动 |

### 6.3 状态机处理函数

```c
// 每个 VM 状态 + 事件组合对应一个处理函数指针
typedef vm_state_t (*event_action_in_state_t)(gvm_context_t *ctx, vmm_sm_event_t *ev);

static vm_state_t handle_wdog_bite(...);              // 看门狗处理
static vm_state_t handle_restart(...);                // 自身重启处理
static vm_state_t handle_restart_ctrl(...);           // 外部控制重启
static vm_state_t handle_terminate(...);              // 自身终止处理
static vm_state_t handle_terminate_ctrl(...);         // 外部控制终止
static vm_state_t handle_container_crash(...);        // Container 崩溃处理
static vm_state_t handle_handled_container_crash(...);// 已处理崩溃
static vm_state_t handle_up_and_running(...);         // 正常运行处理
static vm_state_t handle_start(...);                  // 启动处理
```

### 6.4 状态机线程主循环

```
vmm_state_machine_thread()
  │
  ├─ pthread_barrier_wait(&threads_barrier)  // 等待所有线程就绪
  │
  └─ while(true):
       ├─ pthread_cond_wait(&wait_on_event_cond)  // 等待事件
       ├─ transition_lookup(current_state, event) // 查表获取处理函数
       ├─ state_fn(ctx, &ev)                      // 执行状态转换
       │    └─ 各 state_fn 内部调用 vmm_send_notif_rcv_ack() 通知已订阅客户端
       │       按优先级遍历 notify_client_heads[0..4]
       │        └─ vmm_send_to_client(fd, &notif_msg)
       └─ vmm_send_event_to_lcm_sync()             // 通知 LCM
```

> **注**：客户端通知 (`vmm_send_notif_rcv_ack`) 在**每个状态处理函数内部**调用，而非在主循环中统一调用。`vmm_send_event_to_lcm_sync` 在主循环中调用，用于通知 vmm-boot-lcm。源码中不存在名为 `vmm_send_notif_to_clients` 的函数。

---

## 7. 线程模型

VMM Service 采用 **每 VM 多线程** 架构：

```
vmm_service (主进程)
│
├─ vmm_service_message_process_thread (全局 1 个)
│   └─ epoll 事件循环: accept 新连接, 处理客户端消息
│
└─ 每个 GVM 创建以下线程:
    ├─ vmm_state_machine_thread     (状态机主循环)
    ├─ vmm_sdb_monitor_thread       (systemd sd-bus 监控)
    ├─ vmm_udev_monitor_thrd        (Gunyah hypervisor uevent)
    └─ vmm_defer_process_list_thread (延迟添加/删除订阅者)
```

**线程同步**:
- `pthread_barrier_wait(&threads_barrier)` — 确保状态机/sd-bus/udev 三个线程就绪（count=3）；延迟处理线程使用独立的 `message_server_barrier`
- `pthread_cond_wait/signal` — 事件驱动，避免忙等待
- `pthread_mutex_lock` — 保护共享数据结构

---

## 8. 外部事件源

### 8.1 systemd sd-bus 监控 (`vmm_sd_bus.c`)

```
systemd (PID 1)
    │
    │ sd-bus PropertiesChanged 信号
    ▼
vmm_sdb_monitor_thread()
    │
    ├─ 监控 container service unit 的:
    │   ├─ ActiveState   (active/inactive/failed/activating...)
    │   ├─ SubState      (running/exited/dead/failed...)
    │   └─ Result        (success/exit-code/signal/core-dump...)
    │
    ├─ 读取 udev 线程已解析的 guestos_exit_reason
    │
    └─ 转换为 VMM 内部事件:
        └─ vmm_convert_vm_exit_reason_to_sm_event(reason)
             └─ post_event_or_ctrl(ctx, sm_event)
```

> **注**: sd-bus 线程不直接解析 GVM 退出原因。退出原因由 udev 线程从 Gunyah uevent 中提取并写入 `gvm_ctx->guestos_exit_reason`，sd-bus 线程在 container 状态变化时读取并转发给状态机。

### 8.2 Gunyah uevent 监控 (`vmm_udev.c`)

```
Gunyah Hypervisor (/dev/gunyah)
    │
    │ NETLINK_KOBJECT_UEVENT
    ▼
vmm_udev_monitor_thrd()
    │
    ├─ 解析 uevent 环境变量, 写入 guestos_exit_reason:
    │   ├─ shutdown → GUESTOS_EXIT_CAUSE_SHUTDOWN
    │   ├─ restart  → GUESTOS_EXIT_CAUSE_RESTART
    │   ├─ panic    → GUESTOS_EXIT_CAUSE_PANIC     (默认→CONTAINER_CRASH)
    │   ├─ nswd     → GUESTOS_EXIT_CAUSE_NSWD      (→WDOG_BITE)
    │   └─ hperr    → GUESTOS_EXIT_CAUSE_HYP_ERR
    │
    └─ guestos_exit_reason → SM 事件转换 (vmm_convert_vm_exit_reason_to_sm_event):
        ├─ SHUTDOWN → VMM_SM_EVENT_GVM_SHUTDOWN_SELF
        ├─ RESTART  → VMM_SM_EVENT_GVM_RESTART_SELF
        ├─ NSWD     → VMM_SM_EVENT_GVM_WDOG_BITE
        ├─ HYP_ERR  → VMM_SM_EVENT_GUNYA_HYP_ERR
        └─ 其他     → VMM_SM_EVENT_QCROSVM_CONTAINER_CRASH (默认)
```

---

## 9. 客户端模型

### 9.1 客户端优先级

客户端通知按优先级顺序发送，`LEVEL_0` 最先收到通知：

```c
typedef enum vmm_cprior_lvl_typ {
    LEVEL_0 = 0U,   // 最高优先级 (如 vmm-boot-lcm)
    LEVEL_1,
    LEVEL_2,
    LEVEL_3,
    LEVEL_4,        // 最低优先级
    MAX_LEVEL
} vmm_cprior_lvl;
```

### 9.2 客户端列表

| Client | 服务端 | 优先级 | 同步模式 | 角色 |
|--------|--------|--------|----------|------|
| `vmm-boot-lcm` | SERVICE | LEVEL_0 | async | Boot 生命周期管理，自动重启 VM |
| `gunyah-vm{N}-hab-*` | SERVICE | LEVEL_0 | async | vhost-user HAB 通道 |
| `vmm-ramdump` | SERVICE | LEVEL_0 | **sync** | Ramdump 收集 |
| `QC-PM` | SERVICE | LEVEL_0 | async | 平台电源管理 |
| `gvm_susp_service` | SERVICE | LEVEL_0 | async | Voyah GVM 挂起 |
| `gvm_resume_service` | SERVICE | LEVEL_0 | async | Voyah GVM 恢复 |
| `gvm_shutdown_service` | SERVICE | LEVEL_0 | async | Voyah GVM 关机 |
| (电源键管理器们) | PWR_MGR | N/A | N/A | GVM 电源键控制 |

### 9.3 同步 vs 异步订阅

```c
typedef struct vmm_subscribe_attr {
    event_cb event_cb_func;
    uint32_t event_mask;
    vmm_cprior_lvl level;
    void *priv_data;
    bool sync;    // true = 同步等待订阅结果; false = 异步
} vmm_subscribe_attr_t;
```

- **异步模式** (默认): `vmm-boot-lcm` 使用，不阻塞启动流程（boot KPI 要求）
- **同步模式**: `vmm-ramdump` 使用，需要确保订阅成功

---

## 10. VM 事件类型

```c
typedef enum vmm_event_type {
    GVM_WDOG_BITE              = (1 << 0),   // 看门狗咬死
    GVM_CONTAINER_CRASH        = (1 << 1),   // Container 崩溃
    GVM_SHUTDOWN               = (1 << 2),   // GVM 主动关机
    GVM_STOPPED                = (1 << 3),   // GVM 已停止
    GVM_HANDLED_CONTAINER_CRASH= (1 << 4),   // 已处理的崩溃
    GVM_BAD_STATE              = (1 << 5),   // 异常状态

    // 组合事件掩码
    GVM_SHUTDOWN_LEVEL_0 = GVM_WDOG_BITE | GVM_CONTAINER_CRASH
                         | GVM_HANDLED_CONTAINER_CRASH,
    GVM_SHUTDOWN_LEVEL_1 = GVM_SHUTDOWN | GVM_STOPPED | GVM_BAD_STATE,
    GVM_SHUTDOWN_LEVEL_2 = (1 << 6),

    GVM_UP_AND_RUNNING         = (1 << 7),   // 正常运行
    GVM_EVENT_LPM_SUSPEND_SUCCESS = (1 << 8),// 低功耗挂起成功
    GVM_EVENT_LPM_RESUME_SUCCESS  = (1 << 9),// 低功耗恢复成功

    GVM_EVENT_FATAL_ERROR      = (1 << 11),  // 致命错误 (仅 LCM)
    GVM_EVENT_UP               = (1 << 12),  // VM 启动 (仅 LCM)
    GVM_EVENT_DOWN             = (1 << 13),  // VM 关闭 (仅 LCM)
} vmm_event_t;

// 不需要 ACK 的事件 (LPM 事件)
#define VMM_EVENT_NO_ACK (GVM_EVENT_LPM_SUSPEND_SUCCESS | GVM_EVENT_LPM_RESUME_SUCCESS)
```

**ACK 机制**: 除 LPM 事件外，客户端收到事件通知后必须回复 `NOTIF_ACK_MSG`。VMM 服务端通过 `vmm_recvmsg_from_client()` 阻塞等待 ACK（无超时，依赖客户端行为或连接断开来终止等待）。

---

## 11. Boot Lifecycle Manager 集成

`vmm-boot-lcm` 是 VMM Service 最重要的客户端，负责 VM 启动失败后的恢复策略：

```
vmm-boot-lcm 启动流程:
  │
  ├─ libabctl_getBootSlot()         // 获取 Host 启动槽位
  ├─ vm_config_init()               // 读取 VM 配置
  ├─ vmm_client_connect("vmm-boot-lcm", VMM_SERVICE_SERVER)
  ├─ vmm_subscribe_event_notification()
  │   订阅事件: GVM_SHUTDOWN_LEVEL_0 | GVM_SHUTDOWN_LEVEL_1
  │            | GVM_EVENT_UP | GVM_EVENT_DOWN
  │            | GVM_EVENT_FATAL_ERROR
  │
  └─ 每个启用 LCM 的 VM 创建 vmm_lcm_event_loop 线程:
       │
       ├─ control_vm(START_GUEST)   // 首次启动
       │    ├─ check_gvm_boot_slot_info()  // 检查 misc 分区 boot slot
       │    ├─ bootable_status='y' → 重置 retry_cnt
       │    └─ bootable_status!='y' → retry_cnt--
       │         └─ retry_cnt==0 → do_failure_recovery()
       │              └─ set_gvm_recovery_cmd("recovery")
       │
       └─ while(true):
            ├─ pthread_cond_wait(GVM_EVENT_DOWN)
            └─ control_vm(START_GUEST)  // 重启 VM
```

**恢复策略**:
- 正常启动 → `bootable_status='y'` → 重置重试计数
- 启动失败 → `retry_cnt--` → 重试启动
- 重试次数耗尽 → 写入 `boot-recovery` 命令到 misc 分区 → 下次启动进入 recovery 模式

### 11.1 Slot 机制详解

#### 11.1.1 Slot 值的数据结构与获取来源

vmm-boot-lcm 涉及三层 slot 相关数据：

**`host_boot_slot`** — vmm-boot-lcm 内存中（`vmm_boot_lcm_t` 结构体）

```c
// 获取方式: vmm_boot_lcm_init() 中调用 libabctl_getBootSlot()
// libabctl 通过读取 /proc/cmdline 中的 androidboot.slot_suffix=_a/_b 来判断
vmm_boot_lcm->host_boot_slot = ret ? 'b' : 'a';  // 0→'a', 1→'b'
```

**`slot_switch_config`** — 从 `/etc/vm_config.xml` 解析

```c
// vm_config.c 解析 <slot_switch_config> XML 元素
#define SYMMETRIC_SLOT_SWITCH       1   // GVM slot 与 Host 同步切换
#define ASYMMETRIC_SLOT_SWITCH      2   // GVM slot 可独立于 Host 切换

// 当前配置值: 1 (SYMMETRIC)
// <slot_switch_config>1<!--SYMMETRIC_SLOT_SWITCH:1 ASYMMETRIC_SLOT_SWITCH:2--></slot_switch_config>
```

**`boot_slot_info`** — 从 GVM 的 misc 分区读取（启动 GVM 时的核心数据源）

```c
// check_gvm_boot_slot_info() 从 misc 分区读取 bootloader_message 结构体
struct boot_slot_info {
    int  recovery_flag;       // 是否需要进入 recovery 模式
    char current_slot;        // misc 分区 reserved[0] — 当前活跃 slot
    char target_slot;         // misc 分区 reserved[1] — 目标启动 slot
    char bootable_status;     // misc 分区 reserved[2] — 是否成功启动过
};
```

#### 11.1.2 Slot 值的传递机制与 la_misc 的真正作用

**关键结论：vmm-boot-lcm 不通过 VMM API 将 slot 值传递给 GVM 启动流程。**

`vmm_request_contrl_vm()` 的消息结构体中**没有 slot 字段**：

```c
typedef struct vmm_vm_ctrl_msg {
    uint32_t vmid;
    vm_state_ctrl_t vm_cmd;   // 仅 VM_CONTROL_START / STOP / RESTART
} vmm_vm_ctrl_msg_t;
```

GVM 的启动源（磁盘镜像/分区）由 systemd service（`qcrosvm.service`，定义在 `vm_config.xml` 的 `<systemd_service>` 中）在启动 qcrosvm 时通过参数指定。`vmm-boot-lcm` 不通过 VMM API 向 qcrosvm 传 slot；但 GVM 自己的 bootloader/ABL 仍可能通过 qcrosvm 暴露的 `la_misc`（label=32）读取 guest slot，并在 qcrosvm 提供的 logical A/B label 之间选择启动镜像。

因此，`la_misc` 既是 **Host ↔ GVM 之间的状态通信通道**，也是 **GVM 内部 logical A/B 选择的输入之一**。它不决定 PVM 侧 `/dev/disk/by-partlabel/la_init_boot`、`la_boot`、`la_vbmeta` 等 current/bak 软链接指向；这些软链接由 PVM slot 决定。

> **注意**：GVM 内部的 bootloader/userspace 代码不在此仓库中。以下 GVM 侧的行为基于 Android A/B 标准架构推断，非本仓库源码直接证明。标注 `[推断]` 的部分表示无法从本仓库源码验证。

```
┌──────────────────────────────────────────────────────────────────────┐
│                 la_misc 的作用：状态通信 + GVM logical A/B 输入        │
│                                                                      │
│  方向            字段                  用途                           │
│  ────            ────                  ────                           │
│  GVM → Host      reserved[2]           GVM 报告启动结果：             │
│  [推断]          (bootable_status)     成功='y' → LCM 重置重试计数    │
│                                       失败≠'y' → LCM 递减重试计数    │
│                                       注：本仓库中未找到写入 'y' 的   │
│                                       代码，推断为 GVM userspace 写入 │
│                                                                      │
│  Host → ?        command[32]           vmm-boot-lcm 写入              │
│                  recovery[768]         "boot-recovery" / "recovery"   │
│                                       读取者不明：                     │
│                                        - recovery.c 不匹配此格式       │
│                                        - 推断为 GVM bootloader 读取   │
│                                        - 本仓库中无法确认读取者       │
│                                                                      │
│  GVM 自用/Host   reserved[0]           GVM ABL 可读取 logical slot；    │
│  条件自用        (current_slot)        disk_symlink 仅在非对称模式下    │
│                                       读取，决定 bootloader 软链接     │
│                                                                      │
│  (预留)          reserved[1]           set_gvm_taget_slot() 可写入    │
│                  (target_slot)         但当前代码中未被调用            │
│                                                                      │
│  Host/Recovery   param_hdr 区域         PATEO OTA/恢复系统使用        │
│                  (offset ≥ 0x400)      (params.c, recovery.c)        │
│                                        updatemgr 当前不写物理 la_misc │
└──────────────────────────────────────────────────────────────────────┘
```

**vmm-boot-lcm 实际使用的字段**（源码 `control_vm()` START_GUEST 分支）：

```c
// vmm-boot-lcm.cpp:430-457
ret = check_gvm_boot_slot_info(gvm_ctx->misc_partition_path, &slot_info);
// slot_info.current_slot   → 仅日志输出，未参与决策
// slot_info.target_slot    → 仅日志输出，未参与决策
// slot_info.recovery_flag  → 仅日志输出，未参与决策
switch (slot_info.bootable_status) {  // ← 唯一参与决策的字段
case 'y':   // GVM 报告上次启动成功 → 重置重试计数
    break;
default:    // GVM 未报告成功 → 递减计数，耗尽则写 recovery 命令
    break;
}
// 然后调用 vmm_request_contrl_vm(vmid, VM_CONTROL_START)
// ↑ 只传 vmid，不传任何 slot 信息
```

#### 11.1.3 la_misc 分区详细布局

`la_misc` 是一个物理 GPT 分区，同时被 Host 和 GVM 访问。当前源码中存在两套结构体视图，需要按组件区分，不能把其中一套当作全局唯一布局：

```
la_misc 分区布局 (offset 从 0x00 开始):
┌──────────────────────────────────────────────────────────────────┐
│ 视图 A: Android bootloader_message，vmm-boot-lcm / disk_symlink 使用 │
│   command[32]    @0x000   "boot-recovery" 或空                   │
│   status[32]     @0x020                                         │
│   recovery[768]  @0x040   recovery 命令参数                       │
│   stage[32]      @0x340                                         │
│   reserved[1184] @0x360                                         │
│     reserved[0]  @0x360 ← current_slot ('a' 或 'b')             │
│     reserved[1]  @0x361 ← target_slot  ('a' 或 'b')             │
│     reserved[2]  @0x362 ← bootable_status ('y' 或 'n')          │
│                                                                  │
│ 视图 B: PATEO param_hdr，recovery/params 使用                     │
│   bootloader_message_1k @0x000 ~ 0x3FF                           │
│   type[32]       @0x400   系统类型 ("SYSTEMA" / "SYSTEMB")       │
│   version[100]   @0x420   系统版本 (A_ver + B_ver 各 50 bytes)   │
│   cmd_line[256]  @0x484   recovery 命令行                        │
│   boot_status    @0x584   boot 状态标志位                        │
│   update_status  @0x588   OTA 更新状态                           │
│   reserved[84]   @0x58C                                         │
│   system_type[32]@0x5E0                                          │
│   content[512]   @0x600                                          │
└──────────────────────────────────────────────────────────────────┘
```

#### 11.1.4 物理 la_misc 的写入者

这里的“物理 `la_misc`”特指 `/dev/disk/by-partlabel/la_misc` 块设备，不包括 updatemgr 当前使用的本地状态文件。

**Host (PVM) 侧，源码可确认会写物理块设备的路径：**

| 写入者 | 代码位置 | 写入内容 | 写入字段 |
|--------|---------|---------|---------|
| **vmm-boot-lcm** | `vendor/qcom/opensource/vmm-boot-lcm/src/vmm-boot-lcm.cpp:93` `set_gvm_recovery_cmd()` | retry 耗尽后写 `"boot-recovery"` → `command`，`"recovery"` → `recovery` | offset 0x00, 0x40；函数读出 2KiB `bootloader_message` 后整体写回 |
| **vmm-boot-lcm** | `同上:172` `set_gvm_taget_slot()` | `'a'` 或 `'b'` | `reserved[1]` (0x361)，**有写函数但当前源码未找到调用点** |
| **vmm-boot-lcm** | `同上:226` `set_bootable_status()` | `'y'` 或 `'n'` | `reserved[2]` (0x362)，**有写函数但 START_GUEST 调用点被注释** |
| **pvm_reboot.sh** | `layers/meta-voyah-bsp/recipes-products/vsock-misc/files/pvm_reboot.sh:63` | `"boot-recovery"` + recovery 参数; 或全零清除 | 整个前 4KB block |
| **recovery.c** | `layers/meta-voyah-bsp/recipes-products/recovery/files/recovery.c:1592` | factory reset 时 `dd if=/dev/zero ... bs=1024k count=1` | 前 1MiB |
| **params.c** | `layers/meta-voyah-bsp/recipes-products/recovery/files/params.c` | `qg_ota_set_recovery_cmd()` / `qg_ota_set_boot_status()` / `qg_ota_set_update_status()` / `qg_ota_set_system_version()` / `qg_ota_clear_recovery_cmd()` | `cmd_line`(0x484), `boot_status`(0x584), `update_status`(0x588), `version`(0x420) |
| **disk_symlink** | `system/core/disksymlink/disk_symlink.cpp:201` `get_from_miscpart()` | **只读** — 在 `slot_switch_config==2` 时读 `reserved[0]` 决定 bootloader 分区软链接目标 | 只读 |

**不是物理 `la_misc` 写入者：**

| 组件 | 说明 |
|------|------|
| **updatemgr `set_misc_flag()` / `obtain_misc_flag()`** | 当前实现读写 `/<DEFAULT_UPD_FOLDER>/upd_data/%d/misc` 本地文件；虽然头文件保留 `BLK_DEV "/dev/disk/la_misc"` 和 `param_hdr` 定义，但 `set_misc_flag()` 没有写物理 `la_misc` 块设备 |
| **vsock_misc / vm_factoryAutoTest** | 不直接写块设备；通过执行 `pvm_reboot.sh recovery/recoverywipe` 间接触发 `pvm_reboot.sh` 写物理 `la_misc` |

**GVM (Guest VM) 侧**（代码不在本仓库中，以下为基于 Android A/B 标准架构的推断，标注 `[推断]`）：

| 写入者 | 写入内容 | 说明 |
|--------|---------|------|
| **GVM userspace** `[推断]` | 系统成功启动后写 `bootable_status='y'` 到 `reserved[2]` (0x362) | 本仓库中未找到写入 'y' 的代码，但 LCM 的逻辑依赖此字段从非 'y' 变为 'y' 来判断启动成功 |
| **GVM bootloader** `[推断]` | 读取 `command` 字段判断是否进入 recovery；可能写 `current_slot` 到 `reserved[0]` | 本仓库中无法确认；recovery.c 的 `parse_misc_command()` 检查的格式与 vmm-boot-lcm 写入的 "recovery" 不匹配 |

**源码可确认的事实**：

1. vmm-boot-lcm 的 `do_failure_recovery()` 写入 `command="boot-recovery"`, `recovery="recovery"` → 但本仓库中**找不到读取者**
2. `recovery.c` 的 `parse_misc_command()` 检查的是 `boot.recovery` 包含 `"prompt_and_wipe_data"` 或 `"recovery\n--wipe_data"`，以及 `cmd_line` 包含 `"--bootwatchcmd="` 等 —— 与 vmm-boot-lcm 写入的格式均不匹配
3. `pvm_reboot.sh` 写入 `command="boot-recovery"`, `recovery="recovery\n--wipe_data\n..."` → 此格式**能**被 `recovery.c` 匹配（包含 `"recovery\n--wipe_data"`），但 pvm_reboot.sh 写入后立即执行 `reboot -f`，此时是 Host recovery 系统来处理
4. `params.c` 的 `qg_ota_set_recovery_cmd()` 写入 `cmd_line="RECOVERY..."` → 可被 `recovery.c` 匹配（通过 `strstr(head.cmd_line, ...)`）

#### 11.1.5 Slot 完整工作流

```
首次启动 (冷启动):
  la_misc 初始状态 (由分区镜像预置):
    command[32]   = ""            (空)
    reserved[0]   = 'a' 或 'b'   (GVM logical slot；disk_symlink 仅在非对称模式使用)
    reserved[2]   = '\0'         (非 'y'，表示尚未成功启动过)

  vmm-boot-lcm:
    └─ check_gvm_boot_slot_info()
         ├─ bootable_status != 'y' → retry_cnt = 7 → retry_cnt = 6
         └─ vmm_request_contrl_vm(START) → vmm-drv FSM → systemd 启动
             qcrosvm.service（service 参数提供 current/bak 两组候选块设备）
             GVM ABL 读取 la_misc 后在 logical A/B label 间选择

  GVM 启动 [推断]:
    └─ GVM 系统启动成功
         └─ bootctl mark-boot-successful → 写入 reserved[2] = 'y'
            （本仓库中未找到此代码，但 LCM 依赖此逻辑判断启动成功）

正常重启 (GVM crash 后 LCM 重新拉起):
  vmm-boot-lcm:
    ├─ 收到 GVM_EVENT_DOWN
    └─ control_vm(START_GUEST)
         ├─ check_gvm_boot_slot_info()
         │    └─ bootable_status = 'y' → retry_cnt = 7 (重置!)
         └─ vmm_request_contrl_vm(START) → 重新拉起 GVM

连续启动失败 (恢复流程):
  vmm-boot-lcm:
    ├─ 第1次: bootable_status != 'y' → retry_cnt = 6
    ├─ 第2次: bootable_status != 'y' → retry_cnt = 5
    ├─ ...
    ├─ 第7次: bootable_status != 'y' → retry_cnt = 0
    │    └─ do_failure_recovery()
    │         └─ set_gvm_recovery_cmd("recovery")
    │              ├─ 写入 command = "boot-recovery"
    │              └─ 写入 recovery = "recovery"
    │
    └─ 注意：vmm-boot-lcm 写入的 command="boot-recovery"
         recovery="recovery" 格式与 recovery.c 的 parse_misc_command()
         检查条件不匹配。本仓库中无法确认此命令的读取者。
        [推断] GVM bootloader 读取此字段进入 recovery 模式。
```

#### 11.1.6 GVM 启动分区的装配机制：谁决定了 GVM 从哪个 slot 启动

**核心结论：在当前 `slot_switch_config=1` (SYMMETRIC) 配置下，PVM 侧 current/bak 软链接由 PVM slot 决定，`la_misc` 不参与 PVM 侧软链接生成；但 GVM ABL 仍可能读取 `la_misc`，并在 qcrosvm 暴露给 GVM 的 logical A/B label 之间选择启动镜像。**

##### 证据一：`disk_symlink` 静态配置表

`system/core/disksymlink/disk_symlink.cpp:29-48`，`g_disk_symlink[]` 表定义了每个软链接对应的 `misc_partname`：

```c
static disk_symlink_t g_disk_symlink[] = {
   {"",           "dsp_",              "/dev/disk/by-partlabel/dsp"          },
   {"",           "modem_",            "/dev/disk/by-partlabel/modem"        },
   {"",           "bluetooth_",        "/dev/disk/by-partlabel/bluetooth"    },
   {"",           "keymaster_",        "/dev/disk/by-partlabel/keymaster"    },
   {"lv_misc",    "lv_bootloader_",    "/dev/disk/by-partlabel/lv_bootloader"}, // misc_partname 非空
   {"la_misc",    "la_bootloader_",    "/dev/disk/by-partlabel/la_bootloader"}, // misc_partname 非空
   {"",           "la_init_boot_",     "/dev/disk/by-partlabel/la_init_boot" }, // "" = 空！
   {"",           "la_vendor_boot_",   "/dev/disk/by-partlabel/la_vendor_boot"}, // "" = 空！
   {"",           "la_dtbo_",          "/dev/disk/by-partlabel/la_dtbo"      }, // "" = 空！
   {"",           "la_boot_",          "/dev/disk/by-partlabel/la_boot"      }, // "" = 空！
   {"",           "la_super_",         "/dev/disk/by-partlabel/la_super"     }, // "" = 空！
   {"",           "la_vbmeta_",        "/dev/disk/by-partlabel/la_vbmeta"    }, // "" = 空！
   {"",           "la_v_boot_",        "/dev/disk/by-partlabel/la_v_boot"    },
   {"",           "la_vb_sys_",        "/dev/disk/by-partlabel/la_vb_sys"    },
   {"",           "lv_dtbo_",          "/dev/disk/by-partlabel/lv_dtbo"      },
   {"",           "lv_boot_",          "/dev/disk/by-partlabel/lv_boot"      },
   {"",           "lv_vbmeta_",        "/dev/disk/by-partlabel/lv_vbmeta"    },
   {"",           "lv_system_",        "/dev/disk/by-partlabel/lv_system"    },
};

第一个字段 `misc_partname` 决定该软链接从何处获取 slot suffix。**`la_init_boot_`、`la_boot_`、`la_vbmeta_`、`la_super_` 等关键启动分区的 `misc_partname` 全部为空字符串 `""`**。只有 `la_bootloader_` 填了 `"la_misc"`。

##### 证据二：`get_partname_with_slot()` — slot suffix 选择逻辑

`disk_symlink.cpp:220-235`：

```c
static int get_partname_with_slot(char *misc_partname, char *part_prefix,
                                   char *partname_slot, size_t buf_size)
{
   if (0 == strlen(misc_partname)) {                       // ← 分支1: misc_partname 为空
      // 直接使用 PVM 的 androidboot.slot_suffix
      snprintf(partname_slot, buf_size-1, "%s%c", part_prefix, g_slot_suffix);
   } else {
      if (2 == g_slot_switch_config) {                     // ← 分支2: ASYMMETRIC 模式
         // 从 la_misc 读取 GVM 自己的 current_slot
         ret = get_from_miscpart(misc_partname, part_prefix,
                                  partname_slot, buf_size);
      } else {                                             // ← 分支3: SYMMETRIC 模式
         // 仍然用 PVM slot suffix
         snprintf(partname_slot, buf_size-1, "%s%c", part_prefix, g_slot_suffix);
      }
   }
}
```

`g_slot_suffix` 由 `get_slot_suffix_from_cmdline()`（第 117-174 行）从 PVM 的 `/proc/cmdline` 中解析 `androidboot.slot_suffix=_a` 或 `_b` 得到。

**对于 `la_init_boot`/`la_boot`/`la_vbmeta`/`la_super`：**
- `misc_partname` 为空 → 进入**分支1**
- `partname_slot = "la_init_boot_" + PVM_slot_suffix`
- PVM 在 slot A → `la_init_boot_a`；PVM 在 slot B → `la_init_boot_b`
- **在 `disk_symlink` 这个 PVM 侧软链接生成路径中，`la_misc` 不被读取**

**对于 `la_bootloader`：**
- `misc_partname = "la_misc"` → 非空
- `slot_switch_config = 1` (SYMMETRIC) → 进入**分支3** → 仍然用 PVM slot suffix
- **仅当 `slot_switch_config = 2` (ASYMMETRIC) 时**，才会进入分支2，读 `la_misc` 的 `reserved[0]`

##### 证据三：udev 规则做同样的映射

`vendor/qcom/opensource/kiumd/dspfirmware-mount/99-persist-storage-ab.rules:3-15`：

```udev
IMPORT{cmdline}="androidboot.slot_suffix"

# PVM 在 slot A:
ENV{androidboot.slot_suffix}=="_a", ENV{ID_PART_ENTRY_NAME}=="la_init_boot_a", SYMLINK+="la_init_boot"
ENV{androidboot.slot_suffix}=="_a", ENV{ID_PART_ENTRY_NAME}=="la_boot_a",      SYMLINK+="la_boot"
ENV{androidboot.slot_suffix}=="_a", ENV{ID_PART_ENTRY_NAME}=="la_vbmeta_a",    SYMLINK+="la_vbmeta"

# PVM 在 slot B:
ENV{androidboot.slot_suffix}=="_b", ENV{ID_PART_ENTRY_NAME}=="la_init_boot_b", SYMLINK+="la_init_boot"
ENV{androidboot.slot_suffix}=="_b", ENV{ID_PART_ENTRY_NAME}=="la_boot_b",      SYMLINK+="la_boot"
ENV{androidboot.slot_suffix}=="_b", ENV{ID_PART_ENTRY_NAME}=="la_vbmeta_b",    SYMLINK+="la_vbmeta"
```

规则完全根据 **PVM 的 `androidboot.slot_suffix`** 决定软链接目标，不涉及 `la_misc`。

##### 证据四：`qcrosvm_sa8797.service` 传给 GVM 的是 current/bak 两组软链接

`vendor/qcom/opensource/crosvm-gunyah/qcrosvm_sa8797.service:33-48`：

```ini
--disk=/dev/disk/by-partlabel/la_init_boot,label=22,rw=true       ← 主槽
--disk=/dev/disk/by-partlabel/la_init_boot_bak,label=23,rw=true   ← 备槽
--disk=/dev/disk/by-partlabel/la_boot,label=2A,rw=true             ← 主槽
--disk=/dev/disk/by-partlabel/la_boot_bak,label=2B,rw=true         ← 备槽
--disk=/dev/disk/by-partlabel/la_vbmeta,label=30,rw=true           ← 主槽
--disk=/dev/disk/by-partlabel/la_vbmeta_bak,label=31,rw=true       ← 备槽
```

qcrosvm 传入的是 `la_init_boot`/`la_boot`/`la_vbmeta`（current 组，label 22/2A/30）和 `la_init_boot_bak`/`la_boot_bak`/`la_vbmeta_bak`（bak 组，label 23/2B/31）。GVM ABL 读 `la_misc` 得到 `aayy` 时选择 logical A，也就是 label 22/2A/30；如果 GVM misc 选择 logical B，则会选择 label 23/2B/31。current/bak 软链接分别指向 PVM 当前活跃 slot 和相反 slot 的物理分区。

##### 完整链路总结

```
PVM 用户态:
  /proc/cmdline → androidboot.slot_suffix=_a 或 _b
       │
       ├─→ disk_symlink:  g_slot_suffix = PVM slot
       │     la_init_boot → la_init_boot_{g_slot_suffix}
       │     la_boot      → la_boot_{g_slot_suffix}
       │     la_vbmeta    → la_vbmeta_{g_slot_suffix}
       │
       └─→ udev 规则: 同样的映射逻辑

qcrosvm.service:
  --disk /dev/disk/by-partlabel/la_init_boot,label=22
  --disk /dev/disk/by-partlabel/la_init_boot_bak,label=23
  --disk /dev/disk/by-partlabel/la_boot,label=2A
  --disk /dev/disk/by-partlabel/la_boot_bak,label=2B
  --disk /dev/disk/by-partlabel/la_vbmeta,label=30
  --disk /dev/disk/by-partlabel/la_vbmeta_bak,label=31
  --disk /dev/disk/by-partlabel/la_misc,label=32
       │
       ▼  GVM 内部
GVM ABL:
  读 la_misc(label=32)
      ├─ logical A → label 22/2A/30 → PVM current 物理分区
      └─ logical B → label 23/2B/31 → PVM bak 物理分区

┌──────────────────────────────────────────────────────────────┐
│  结论:                                                       │
│  1. PVM 侧 current/bak 软链接由 PVM slot 决定                 │
│  2. la_misc 的 reserved[0]/[1] 不影响 PVM 侧软链接生成        │
│  3. la_misc 仍可能影响 GVM ABL 在 logical A/B label 间选择    │
│  4. read_misc=aayy 时 GVM 选择 current 组，因此 PVM 在 B      │
│     时会加载 la_init_boot_b/la_boot_b/la_vbmeta_b             │
│  5. OTA 后 GVM 启动失败需继续看 current 组镜像/AVB/kernel 日志│
└──────────────────────────────────────────────────────────────┘
```

#### 11.1.7 PVM Slot 机制：存储、读取与切换

##### PVM Slot 的存储位置

PVM 不使用 `la_misc` 分区来存储 slot 信息。PVM 的 slot 状态存储在 **每个 A/B 分区的 GPT 分区表项属性位** 中。

`layers/meta-qti-automotive-prop/recipes-bsp/abctl/files/abctl/src/libabctl.cpp:42-59`：

```c
// GPT 分区表 entry 的 attribute_flags 字段 (64 bits)，按位定义：
#define PARTITION_ATTRIBUTE_PRIORITY_BIT_POS      (48)   // 优先级 (2 bits: 0~3)
#define PARTITION_ATTRIBUTE_ACTIVE_BIT_POS        (50)   // 活跃标记 (1 bit)
#define PARTITION_ATTRIBUTE_MAX_RETRY_BIT_POS     (51)   // 最大重试次数 (3 bits: 0~7)
#define PARTITION_ATTRIBUTE_SUCCESS_BIT_POS       (54)   // 启动成功标记 (1 bit)
#define PARTITION_ATTRIBUTE_UNBOOTABLE_BIT_POS    (55)   // 不可启动标记 (1 bit)
```

每个 slot 的 `boot` 分区（`boot_a`、`boot_b`）在 GPT 表中都有一套独立的属性。PVM slot 状态由这些 attribute bits 共同决定。

##### 启动时谁读取 PVM Slot

Qualcomm 启动链：**PBL → XBL → ABL → Linux Kernel**。

```
芯片 ROM (PBL - Primary Boot Loader)
  │
  └─→ XBL (eXtensible Boot Loader) — 第一阶段固件
        │  读取 GPT 分区表
        │  比较 boot_a 和 boot_b 的 attribute_flags:
        │    - 选择 PRIORITY 更高且 ACTIVE=1 的 slot
        │    - UNBOOTABLE=1 → 跳过此 slot
        │    - SUCCESS=0 → 递减 retry_count
        │
        └─→ ABL (Android Boot Loader) — 第二阶段固件
              │  加载选定 slot 的 boot.img / vendor_boot.img
              │  设置 androidboot.slot_suffix=_a 或 _b 到 kernel cmdline
              │
              └─→ Linux Kernel
                    /proc/cmdline 包含 androidboot.slot_suffix=_a 或 _b
```

> **注**：XBL 和 ABL 是 Qualcomm 闭源固件，源码不在本仓库中，但 `libabctl` 中的 GPT 属性操作逻辑反向印证了固件的 slot 选择策略。

##### 用户态如何获取当前 Slot

`libabctl.cpp:647-698`，**直接从 `/proc/cmdline` 读取**，不是读 GPT 属性：

```c
int libabctl_getBootSlot()
{
    fd = open("/proc/cmdline", O_RDONLY);
    // 解析 androidboot.slot_suffix=_a → return 0 (slot A)
    // 解析 androidboot.slot_suffix=_b → return 1 (slot B)
    // 任何其他情况 → return -1
}
```

`androidboot.slot_suffix` 是 ABL 写入的。对用户态程序来说，只需读 `/proc/cmdline` 就能知道自己运行在哪个 slot。

`vmm-boot-lcm.cpp:648-654` 正是调用此 API 获取 PVM slot：

```c
ret = libabctl_getBootSlot();
vmm_boot_lcm->host_boot_slot = ret ? 'b' : 'a';
```

##### Slot 切换机制

`libabctl.cpp:764-850`，OTA 升级完成后调用 `abctl --set_active <slot>`。在 gen5 编译配置中，`abctl_1.0.bb` 定义了 `SUPPORT_ENABLE_LV_ATOMIC_AB`，因此 Type GUID 交换分支不会编译进去；GUID swap 只属于 legacy non-atomic A/B 路径。

```c
int libabctl_setActive(unsigned int slot)
{
    // 1. 修改 boot 分区的 GPT 属性 (第 805/811 行)
    //    新活跃 slot: ACTIVE=1, PRIORITY=max(3), RETRY=max(7), 清 SUCCESS, 清 UNBOOTABLE
    //    旧活跃 slot: PRIORITY=min(1)
    update_partition_attr(active_partition, 1);
    update_partition_attr(non_active_partition, 0);

    // 2. legacy non-atomic A/B 才交换两个 slot 所有分区的 Type GUID
#ifndef SUPPORT_ENABLE_LV_ATOMIC_AB
    libgpt_setTypeGUID(active_part, &non_active_typeguid);
    libgpt_setTypeGUID(non_active_part, &active_typeguid);
#endif

    // 3. UFS 设备切换 Boot LUN (第 838-845 行)
    //    通过 SCSI 命令让 UFS 芯片从新 slot 的 XBL 分区启动
    set_xbl_boot_partition(slot);
}
```

##### 标记启动成功

`libabctl.cpp:700-732`，系统启动成功后调用 `abctl --set_success`：

```c
int libabctl_SetBootSuccess()
{
    // 在当前 boot 分区 GPT 属性中:
    //   SUCCESS = 1 → 告诉 XBL "此 slot 已验证可启动"
    //   UNBOOTABLE = 0 → 清除不可启动标记
    e.attribute_flags |= PARTITION_ATTRIBUTE_SUCCESSFUL_VAL;
    e.attribute_flags &= PARTITION_ATTRIBUTE_UNBOOTABLE_CLR;
}
```

##### PVM vs GVM Slot 机制对比

```
                    PVM (Linux Host)              GVM (Android Guest)
                    ──────────────                ──────────────────
Slot 存储位置:       GPT 分区表 attribute_flags    la_misc 分区 reserved[0..2]
                    (每个 boot_x 分区各一套)        (存储在块设备文件中)

启动时谁读:          XBL/ABL (芯片固件)            ABL (GVM 内部 UEFI)
                    → 读 GPT 表                  → 读 la_misc 块设备

内核获知方式:        cmdline                      不适用
                    androidboot.slot_suffix       (GVM 内核由 qcrosvm
                    =_a 或 _b                     直接传入块设备)

用户态读取:          libabctl_getBootSlot()        vmm-boot-lcm
                    → 读 /proc/cmdline             → 读 la_misc 块设备

切 slot 方式:        libabctl_setActive()          GVM ABL 读 la_misc 后
                    → 写 boot GPT 属性            在 qcrosvm 提供的
                    → 切换 UFS Boot LUN           logical A/B label 中选择
                    → GUID swap 仅 legacy 路径     物理目标由 PVM current/bak 决定

标记启动成功:        libabctl_SetBootSuccess()     GVM bootctl (推断)
                    → 写 GPT SUCCESS 位            → 写 la_misc reserved[2]

恢复机制:           XBL 选另一个 slot             vmm-boot-lcm 写
                    (GPT 属性自动退化)             boot-recovery 到 la_misc
```

---

## 12. Ramdump 服务

`vmm-ramdump` 监听 `GVM_WDOG_BITE` 事件，在 VM 崩溃时收集内存 dump：

```
vmm-ramdump 架构:
  │
  ├─ vmm_client_connect("vmm-ramdump", VMM_SERVICE_SERVER)
  ├─ vmm_subscribe_event_notification(sync=true)  // 同步模式
  │
  ├─ 兼容三种 ramdump 类型:
  │   ├─ RAMDUMP_TYPE_FULLDUMP (默认) → gvm_ramdump_*.tar.gz
  │   ├─ RAMDUMP_TYPE_MINIDUMP       → gvm_minidump_*.tar.gz
  │   └─ RAMDUMP_TYPE_DISABLE        → 跳过，不订阅事件
  │
  ├─ dump 来源: /sys/kernel/debug/${GVM_NAME}/ (目录遍历，读取所有文件条目)
  │
  └─ 使用 libarchive 压缩 dump 文件为 tar.gz
```

**配置示例** (vm_config.xml):
```xml
<vm>
    <vmid>1</vmid>
    <ramdump_type>minidump</ramdump_type>  <!-- full/minidump/disable -->
</vm>
```

---

## 13. Systemd Service 集成

### 13.1 vmm_drv.service

```ini
[Unit]
Description=Launch VMM-Service
After=systemd-modules-load.service tmp.mount
Conflicts=shutdown.target        # 关机时冲突
Before=shutdown.target           # 在 shutdown.target 之前停止
DefaultDependencies=no           # 不依赖默认的 sysinit.target

[Service]
Type=notify                      # 使用 sd_notify("READY=1") 通知就绪
NotifyAccess=main                # 仅主进程发送通知
ExecStart=/usr/bin/vmm_service

[Install]
WantedBy=multi-user.target
```

### 13.2 启动时序

```
systemd-modules-load.service  ─┐
tmp.mount                     ─┤
                               ├──→ vmm_drv.service  ──→ vmm-ramdump.service
                               │         │
                               │    sd_notify("READY=1")
                               │         │
                               └──→ vmm-boot-lcm.service (客户端连接)
```

### 13.3 关机时序

```
shutdown.target
    │
    ├─ Conflicts/Before 确保 vmm_drv 在 shutdown.target 之前停止
    │
    ├─ SIGTERM → vmm_service_sig_hndl()
    │   └─ (VMM_DRV_RESTART_ENABLE 条件下) close(server_socket_fd)
    │   └─ (VMM_DRV_RESTART_ENABLE 条件下) unlink(VMM_SERVICE_SOCKET_PATH)
    │   └─ _exit(0)
    │
    └─ 客户端检测到连接断开 (EPOLLRDHUP)
         └─ (VMM_DRV_RESTART_ENABLE 条件下) vmm_client_reconnect() 尝试重连
```

---

## 14. 客户端重连机制

> **编译条件**：重连机制由 `VMM_DRV_RESTART_ENABLE` 宏控制（在 `vmm-drv/CMakeLists.txt` 中定义）。若未定义该宏，客户端仅初始连接一次，不会自动重连。

当 VMM Service 重启时，客户端会自动重新连接并重新订阅：

```
vmm_client_reconnect() 线程:
  │
  ├─ connect_server()                    // 连接服务端
  │   ├─ socket(AF_UNIX, SOCK_STREAM)
  │   ├─ connect(VMM_SERVICE_SOCKET_PATH)
  │   ├─ 失败 → 指数退避重试 (50ms → 100ms → 200ms → ... → 1s max)
  │   └─ 成功 → connect_stage = VMM_CLIENT_SERVER_CONNECTED
  │
  └─ epoll 监控 server_fd:
       ├─ EPOLLRDHUP | EPOLLHUP | EPOLLERR → 服务端断开
       ├─ connect_server() 重新连接
       └─ 重新订阅事件:
            └─ vmm_subscribe_event_notification()
```

---

## 15. 关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `VMM_SERVICE_SOCKET_PATH` | `/tmp/vmm_service_server` | 服务端监听 socket |
| `VMM_POWER_MANAGER_SOCKET_PATH` | `/tmp/vmm_pwr_mgr_server` | 电源管理 socket |
| `MAX_VMM_NUM_VMIDS` | 16 | 最大 VM 数量 |
| `MAX_VMM_CLIENT_NAME_SIZE` | 64 | 客户端名称最大长度 |
| `GVM_NAME_LEN` | 16 | VM 名称最大长度 |
| `VMM_SERVER_CONNECT_TIMEOUT_MS` | 20000 | 连接服务端超时 (20s) |
| `VMM_SUBSCRIBE_EVENT_TIMEOUT` | 25 | 订阅事件超时 (25s) |
| `VMM_NOTIF_ACK_TIMOUT` | 25 | 通知 ACK 超时 (秒，定义但当前代码中未使用，ACK 接收使用无限阻塞模式) |
| `MAX_EVENTS` | 10 (服务端) / 2 (客户端重连) | epoll 最大事件数 |

---

## 16. 错误处理

### 返回值约定

- `EOK` (0) — 成功
- 负值 (`-errno`) — 失败，使用标准 errno 语义：
  - `-EINVAL` — 无效参数
  - `-ENOMEM` — 内存分配失败
  - `-ECONNRESET` — 连接重置
  - `-EPROTO` — 协议错误（消息长度不匹配）
  - `-EMSGSIZE` — 消息过大（MSG_TRUNC / MSG_CTRUNC）
  - `-ETIMEDOUT` — 超时
  - `-EBADF` / `-ENOTCONN` — 连接状态错误

### EINTR 处理

所有 socket I/O 操作都封装了 `EINTR` 重试逻辑，避免被信号中断导致操作失败。

---

## 17. 编译与构建

使用 CMake 构建系统：

```
vmm-service-noship/
├── vmm-drv/CMakeLists.txt       → vmm_service 可执行文件
├── vmm-lib/CMakeLists.txt       → libvmm_client.so + libvmm_utils.so
├── vmm-ramdump/CMakeLists.txt   → vmm-ramdump 可执行文件
└── vmm-test/CMakeLists.txt      → vmm_test 测试程序
```

**依赖库**:
- `glib-2.0` (vmm-drv 必选, vmm-lib/vmm-ramdump 仅在缺 strlcpy/strlcat 时有条件使用) — 哈希表 (GHashTable), strlcpy/strlcat 兼容
- `systemd` (链接名) — sd-bus, sd-event, sd_notify
- `udev` (链接名) — Gunyah hypervisor uevent 监控
- `libxml-2.0` (vmm-lib/vmm_utils 目标) — VM XML 配置解析
- `archive` (链接名, vmm-ramdump) — ramdump 压缩
- `pthread`, `rt` — 多线程与实时扩展
- `abctl` (链接名, vmm-boot-lcm) — boot slot 检测
- `bootkpi-logging` — 启动性能日志
- `vmm_utils` (vmm-drv 依赖) — VM 配置读取库

---

## 18. 安全考量

1. **Unix Domain Socket 权限**: 服务端 socket 位于 `/tmp/`，依赖文件系统权限控制
2. **fd 传递校验**: `vmm_recv_wrap_client_msg()` 校验传递的 fd 数量不超过 `MAX_VMM_NUM_VMIDS`，且不允许空 SCM_RIGHTS 消息
3. **消息完整性**: 严格校验 `recvmsg()` 返回长度，防止部分读取
4. **资源清理**: 错误路径统一关闭已接收的 fd，防止 fd 泄漏
5. **SIGTERM 处理**: 关机时清理 socket 文件，防止残留

---

## 19. 代码约定

- 函数命名: `vmm_<模块>_<动作>()`
- 宏命名: `VMM_<类别>_<描述>`
- 日志: 默认使用 syslog（通过 `VMM_USING_SYSLOG=1` 控制）；`vmm-ramdump` 通过 CMake 覆盖为 `VMM_USING_SYSLOG=0`，使用 stderr
- 日志级别: `VMM_LOG_LEVEL_DBG` / `VMM_LOG_LEVEL_INFO` / `VMM_LOG_LEVEL_WARN` / `VMM_LOG_LEVEL_ERR` / `VMM_LOG_LEVEL_NONE`
- 链表: 自定义双向链表 `vmm_dlist_*`，类似 Linux kernel list_head
- 错误处理: goto-based cleanup pattern（常用标签: `goto __failed` / `goto done` / `goto exit` / `goto __out`）

---

## 附录 A: 文件清单

| 文件 | 行数(约) | 说明 |
|------|----------|------|
| `vmm-drv/src/vmm_drv.c` | ~1277 | 消息服务器、客户端管理、事件分发主逻辑 |
| `vmm-drv/src/vmm_fsm.c` | ~500 | VM 状态机实现 |
| `vmm-drv/src/vmm_sd_bus.c` | ~828 | systemd sd-bus 监控 |
| `vmm-drv/src/vmm_udev.c` | ~200 | Gunyah uevent 监控 |
| `vmm-drv/src/vmm_util.c` | ~66 | 链表/哈希表工具 |
| `vmm-lib/vmm-client/vmm_clib.c` | ~1000 | 客户端库核心实现 |
| `vmm-lib/vmm-utils/vm_config.c` | ~400 | VM XML 配置解析 |
| `vmm-ramdump/src/vmm-ramdump.c` | ~550 | Ramdump 收集服务 |
| `vmm-test/test.c` | ~303 | 测试工具 |

## 附录 B: 术语表

| 术语 | 全称 | 说明 |
|------|------|------|
| VMM | Virtual Machine Manager | 虚拟机管理器 |
| GVM | Guest Virtual Machine | 客户虚拟机 |
| LCM | Lifecycle Manager | 生命周期管理器 |
| FSM | Finite State Machine | 有限状态机 |
| HAB | Hardware Abstraction Bridge | 硬件抽象桥 |
| SCM_RIGHTS | - | Unix socket 传递 fd 的机制 |
| qcrosvm | Qualcomm Rust OS Virtual Machine | Qualcomm 的 Rust VMM |
| svm | Secure Virtual Machine | 安全虚拟机 |
| sd-bus | systemd D-Bus | systemd 的 D-Bus 实现 |
| KPI | Key Performance Indicator | 关键性能指标 |
