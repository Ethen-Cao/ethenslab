+++
date = '2026-08-26T16:30:00+08:00'
draft = false
title = 'GVM A/B Slot 管理机制'
description = 'PVM 与 GVM 的 A/B Slot、current/bak 分区装配及 ActiveSlot 机制'
categories = ['Qualcomm', 'Gunyah', '虚拟化']
tags = ['GVM', 'PVM', 'A/B Slot', 'ABL', 'ActiveSlot']
+++

本文说明 PVM 与 GVM 的 A/B Slot 状态、current/bak 分区装配以及 GVM firmware 的 logical slot 选择。

## 1. 两套 Slot 状态

PVM 与 GVM 使用不同的 slot 元数据：

| 项目 | PVM | GVM |
|------|-----|-----|
| 持久化位置 | boot A/B 分区的 GPT attributes | `la_misc` 的 `reserved[0..6]` |
| 当前 slot 来源 | `androidboot.slot_suffix` | `ro.boot.slot_suffix` 与 firmware `ActiveSlot` |
| 用户态组件 | `libabctl` | QTI boot control HAL |
| 启动固件 | XBL/ABL 读取 GPT | AUTO_VIRT_ABL 读取 UEFI `ActiveSlot` |
| 启动成功 | GPT successful bit | `reserved[2]` 与 `[3]`/`[5]` |

## 2. PVM Slot

PVM slot 状态保存在 `boot_a`、`boot_b` 的 GPT attribute bits：

```c
#define PARTITION_ATTRIBUTE_PRIORITY_BIT_POS   48
#define PARTITION_ATTRIBUTE_ACTIVE_BIT_POS     50
#define PARTITION_ATTRIBUTE_MAX_RETRY_BIT_POS  51
#define PARTITION_ATTRIBUTE_SUCCESS_BIT_POS    54
#define PARTITION_ATTRIBUTE_UNBOOTABLE_BIT_POS 55
```

`libabctl_getBootSlot()` 从 `/proc/cmdline` 的 `androidboot.slot_suffix=_a/_b` 获取当前 slot。`libabctl_setActive()` 更新 GPT attributes 和 UFS boot LUN；`libabctl_SetBootSuccess()` 设置 successful 并清除 unbootable。

## 3. GVM Slot 数据

Boot LCM 读取的简化视图：

```c
struct boot_slot_info {
    int  recovery_flag;
    char current_slot;        // reserved[0]
    char target_slot;         // reserved[1]
    char bootable_status;     // reserved[2]
};
```

GVM boot control HAL 使用完整的 `reserved[0..6]`：

| 字段 | 含义 |
|------|------|
| `[0]` | current slot |
| `[1]` | target slot |
| `[2]` | 全局启动成功握手 |
| `[3]` | Slot A successful |
| `[4]` | Slot A unbootable |
| `[5]` | Slot B successful |
| `[6]` | Slot B unbootable |

详细读写规则见 [la_misc 接口](la-misc-interface.md)。

## 4. Slot 模式

```c
#define SYMMETRIC_SLOT_SWITCH   1
#define ASYMMETRIC_SLOT_SWITCH  2
```

当前系统使用 `SYMMETRIC_SLOT_SWITCH`：PVM current/bak 软链接根据 PVM slot 生成，GVM 看到的 current 组随 PVM slot 改变。

在 `ASYMMETRIC_SLOT_SWITCH` 下，`disk_symlink` 可针对带 `misc_partname` 的条目读取 misc 的 `reserved[0]`。

## 5. PVM current/bak 软链接

`disk_symlink` 的关键配置关系：

| Logical link | Slot 来源 |
|--------------|-----------|
| `la_init_boot` | PVM `androidboot.slot_suffix` |
| `la_boot` | PVM `androidboot.slot_suffix` |
| `la_vbmeta` | PVM `androidboot.slot_suffix` |
| `la_super` | PVM `androidboot.slot_suffix` |
| `la_bootloader` | SYMMETRIC 时使用 PVM slot；ASYMMETRIC 时可读 `la_misc` |

对于 `la_init_boot`、`la_boot`、`la_vbmeta` 和 `la_super`，`misc_partname` 为空，因此直接拼接 PVM slot suffix：

```text
PVM slot A:
  la_boot      -> la_boot_a
  la_boot_bak  -> la_boot_b

PVM slot B:
  la_boot      -> la_boot_b
  la_boot_bak  -> la_boot_a
```

udev 规则使用相同的 `androidboot.slot_suffix` 建立 current 链接。

## 6. qcrosvm 磁盘装配

qcrosvm 同时向 GVM 暴露 current 和 backup 两组分区：

```ini
--disk=/dev/disk/by-partlabel/la_init_boot,label=22,rw=true
--disk=/dev/disk/by-partlabel/la_init_boot_bak,label=23,rw=true
--disk=/dev/disk/by-partlabel/la_boot,label=2A,rw=true
--disk=/dev/disk/by-partlabel/la_boot_bak,label=2B,rw=true
--disk=/dev/disk/by-partlabel/la_vbmeta,label=30,rw=true
--disk=/dev/disk/by-partlabel/la_vbmeta_bak,label=31,rw=true
--disk=/dev/disk/by-partlabel/la_misc,label=32,rw=true
```

| Logical group | Labels | PVM 物理映射 |
|---------------|--------|--------------|
| current | `22`、`2A`、`30` | PVM 当前活跃 slot |
| backup | `23`、`2B`、`31` | PVM 另一个 slot |

## 7. GVM Firmware Slot 选择

GVM ABL 构建启用 `AUTO_VIRT_ABL`。该分支中：

- `GetActiveSlot()` 通过 UEFI Runtime Service 读取变量 `ActiveSlot`。
- `FindBootableSlot()` 获得 `_a` 或 `_b` 后直接返回，不走普通物理 GPT 的 priority/retry 选择。
- ABL 根据 suffix 选择 `init_boot_<slot>`、`boot_<slot>` 和 `vbmeta_<slot>`。

平台 pre-ABL firmware 负责建立 `ActiveSlot`。当前可见 ABL 源码只包含 getter，不包含 `ActiveSlot` setter，因此该变量的生成属于前级 firmware 接口。

```text
PVM slot
  -> current/bak symlinks
  -> qcrosvm disk labels

GVM firmware ActiveSlot
  -> AUTO_VIRT_ABL GetActiveSlot()
  -> logical _a or _b group
```

## 8. Recovery 与 Slot

Recovery BCB 改变的是启动模式，不等同于切换 logical slot。ABL 进入 recovery 时仍使用当前 `ActiveSlot` 对应的 `init_boot_<slot>` 和 `boot_<slot>`。

Slot 切换由 GVM boot control HAL 更新 misc 元数据，并由前级 firmware 在后续启动中转换为 `ActiveSlot`。

## 9. 相关文档

- [VMM Service 配置](vmm-service-configuration.md)
- [Boot Lifecycle Manager](vmm-boot-lifecycle.md)
- [la_misc 接口](la-misc-interface.md)
