+++
date = '2026-08-26T16:30:00+08:00'
draft = false
title = 'VMM Service 配置机制'
description = 'vm_config.xml 的生成方式、字段语义及组件消费关系'
categories = ['Qualcomm', 'Gunyah', '虚拟化']
tags = ['VMM', 'vm_config.xml', 'qcrosvm', 'Yocto', 'GVM']
+++

本文说明 `/etc/vm_config.xml` 的生成方式、字段语义及各组件的消费关系。

## 1. 配置文件生成

`vm_config.xml` 由 Yocto 在构建阶段从 qcrosvm 的 XML 模板安装，不在运行时动态生成。

模板目录：

```text
vendor/qcom/opensource/crosvm-gunyah/vm_config_xml/
```

常用模板：

| 模板 | 选择条件 | VM 数量 | 说明 |
|------|----------|---------|------|
| `vm_config_la.xml` | 默认 | 1 | 标准 GVM 配置 |
| `vm_config_la_user.xml` | `VARIANT=user` | 1 | 包含 `ramdump_type` |
| `vm_config_lalv.xml` | 多 VM 平台 | 2 | LA VM 与 LV VM |

Yocto 配方通过 `VM_CONFIG_XML` 选择模板，并将其安装为：

```text
/etc/vm_config.xml
```

解析库 `libvmm_utils.so` 中的 `vm_config.c` 使用固定路径加载该文件。

## 2. XML 结构

```xml
<?xml version="1.0" encoding="utf-8"?>
<vm_config NUM_VMS="1">
  <vm>
    <vm_name>autoghgvm</vm_name>
    <vmid>52</vmid>
    <systemd_service>qcrosvm.service</systemd_service>
    <vmm_boot_lcm_enable>1</vmm_boot_lcm_enable>
    <lcm_retry_count>7</lcm_retry_count>
    <misc_partition>la_misc</misc_partition>
    <slot_switch_config>1</slot_switch_config>
    <ramdump_type>minidump</ramdump_type>
  </vm>
</vm_config>
```

根元素的 `NUM_VMS` 表示 VM 数量，每个 VM 对应一个 `<vm>` 节点。

## 3. 字段定义

| XML 字段 | C 结构字段 | 说明 |
|----------|------------|------|
| `vm_name` | `vm_cfg->vm_name` | VM 名称，同时用于日志和 debugfs 路径 |
| `vmid` | `vm_cfg->vmid` | Gunyah VM 标识符 |
| `systemd_service` | `vm_cfg->systemd_service` | 承载 VM 的 qcrosvm systemd unit |
| `vmm_boot_lcm_enable` | `vm_cfg->vmm_boot_lcm_enable` | 是否由 Boot LCM 管理启动和重启 |
| `lcm_retry_count` | `vm_cfg->vmm_boot_lcm_retry_count` | Boot LCM 连续启动重试上限 |
| `misc_partition` | `vm_cfg->misc_partition_name` | GVM BCB/slot 状态分区的 GPT partlabel |
| `slot_switch_config` | `vm_cfg->slot_switch_config` | Slot 对称或非对称模式 |
| `ramdump_type` | `vm_cfg->ramdump_type` | `full`、`minidump` 或 `disable` |

`process_content()` 按 XML 元素名称精确匹配字段，因此字段名不能随意改变。

## 4. Slot 模式

```c
#define SYMMETRIC_SLOT_SWITCH   1
#define ASYMMETRIC_SLOT_SWITCH  2
```

| 模式 | PVM 分区软链接 | GVM Slot 特征 |
|------|----------------|---------------|
| `SYMMETRIC` | 根据 PVM `androidboot.slot_suffix` 生成 | GVM current/bak 物理映射跟随 PVM |
| `ASYMMETRIC` | 部分组件可读取 misc 的 guest slot | GVM 可维护独立的 slot 状态 |

当前配置采用 `SYMMETRIC_SLOT_SWITCH`。详细机制见 [GVM Slot 管理](gvm-slot-management.md)。

## 5. 配置消费者

`vm_config.c` 提供 `vm_config_init()` 和 `vm_config_get_*()` API。各组件读取的字段如下：

| 组件 | 使用字段 |
|------|----------|
| `vmm-boot-lcm` | `num_vms`、`vmid`、`vm_name`、`vmm_boot_lcm_enable`、`lcm_retry_count`、`slot_switch_config`、`misc_partition` |
| `vmm-drv` | `num_vms`、`vmid`、`vm_name`、`vmm_boot_lcm_enable`、`systemd_service` |
| `vmm-ramdump` | `num_vms`、`vmid`、`vm_name`、`ramdump_type` |
| `vmm-pwr-key` | `num_vms`、`vmid`、`vm_name` |
| `qc-pm` | `num_vms`、`vmids[]` |
| `oem-pm-bsp` | `num_vms`、`vmids[]` |
| `disk_symlink` | `vmid`、`slot_switch_config` |

## 6. 启动所有权

`vmm_boot_lcm_enable` 决定 VM 的启动所有权：

- 值为 `1`：`vmm-drv` 跳过默认启动，由 `vmm-boot-lcm` 创建事件循环并管理重启。
- 值为 `0`：VM 由 `vmm-drv` 的默认流程启动。

`systemd_service` 由 `vmm-drv` 用于关联 qcrosvm unit，并通过 sd-bus 读取 `ActiveState`、`SubState` 和 `Result`。

## 7. 相关文档

- [VMM Service 架构总览](vmm-service-architecture.md)
- [VMM Service 运行时架构](vmm-service-runtime.md)
- [Boot Lifecycle Manager](vmm-boot-lifecycle.md)
- [la_misc 接口](la-misc-interface.md)
- [VMM Ramdump 服务](vmm-ramdump-service.md)
