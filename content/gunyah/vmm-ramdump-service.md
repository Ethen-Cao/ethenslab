+++
date = '2026-08-26T16:30:00+08:00'
draft = false
title = 'VMM Ramdump 服务'
description = 'GVM watchdog 事件订阅、Ramdump 采集及归档流程'
categories = ['Qualcomm', 'Gunyah', '虚拟化']
tags = ['VMM', 'Ramdump', 'Minidump', 'Gunyah', 'debugfs', 'watchdog']
+++

本文说明 `vmm-ramdump` 的订阅、采集和归档流程。

## 1. 组件职责

`vmm-ramdump` 是 VMM Service 的同步订阅客户端。它监听 `GVM_WDOG_BITE`，并从 Gunyah debugfs 收集 VM dump。

## 2. 初始化

```text
vm_config_init()
  -> read vm_name, vmid and ramdump_type
  -> vmm_client_connect("vmm-ramdump")
  -> subscribe GVM_WDOG_BITE with sync=true
  -> wait for notification
```

同步订阅确保服务进入等待状态前，服务端已经建立事件通道。

## 3. Ramdump 类型

| 配置值 | 内部类型 | 输出 |
|--------|----------|------|
| `full` | `RAMDUMP_TYPE_FULLDUMP` | `gvm_ramdump_*.tar.gz` |
| `minidump` | `RAMDUMP_TYPE_MINIDUMP` | `gvm_minidump_*.tar.gz` |
| `disable` | `RAMDUMP_TYPE_DISABLE` | 不订阅、不采集 |

未配置时使用 full dump。

## 4. 采集流程

```text
GVM_WDOG_BITE
  -> event callback
  -> enumerate /sys/kernel/debug/${GVM_NAME}/
  -> read dump entries
  -> package files with libarchive
  -> create tar.gz archive
  -> send NOTIF_ACK_MSG
```

dump 数据来自：

```text
/sys/kernel/debug/${GVM_NAME}/
```

服务遍历该目录下的文件条目，并使用 libarchive 生成 gzip 压缩的 tar 包。

## 5. 配置

```xml
<vm>
  <vm_name>autoghgvm</vm_name>
  <vmid>52</vmid>
  <ramdump_type>minidump</ramdump_type>
</vm>
```

配置来自 `/etc/vm_config.xml`。详见 [VMM Service 配置](vmm-service-configuration.md)。

## 6. 服务依赖

`vmm-ramdump.service` 在 `vmm_drv.service` 就绪后启动，连接 `/tmp/vmm_service_server` 并完成同步订阅。

Ramdump 回调属于需要 ACK 的事件路径。归档处理结束后必须回复 ACK，避免阻塞服务端后续通知。

## 7. 相关文档

- [VMM Service 架构总览](vmm-service-architecture.md)
- [VMM Service IPC](vmm-service-ipc.md)
- [VMM Service 运行时架构](vmm-service-runtime.md)
