+++
date = '2026-08-26T16:30:00+08:00'
draft = false
title = 'la_misc 分区接口与 BCB 机制'
description = 'la_misc 分区布局、Slot 元数据、启动成功握手及 recovery BCB 接口'
categories = ['Qualcomm', 'Gunyah', '虚拟化']
tags = ['la_misc', 'BCB', 'bootloader_message', 'boot control', 'recovery']
+++

本文定义 PVM 与 GVM 共享的 `la_misc` 分区布局、字段语义、读写组件以及 recovery BCB 行为。

## 1. 接口定位

qcrosvm 以 label `32` 将 `/dev/disk/by-partlabel/la_misc` 暴露给 GVM。该分区承担三类功能：

1. GVM A/B slot 元数据。
2. GVM 启动成功状态与 Boot LCM retry 握手。
3. Bootloader Control Block（BCB）及 OEM recovery/OTA 参数。

`la_misc` 不决定 SYMMETRIC 模式下 PVM current/bak 软链接的目标。

## 2. Android BCB 视图

```text
Offset   Field
------   --------------------------------------------------
0x000    command[32]
0x020    status[32]
0x040    recovery[768]
0x340    stage[32]
0x360    reserved[1184]
```

GVM slot 字段位于 `reserved[]` 起始位置：

| 字段 | 绝对偏移 | 含义 |
|------|----------|------|
| `reserved[0]` | `0x360` | current slot，`'a'` 或 `'b'` |
| `reserved[1]` | `0x361` | target slot，`'a'` 或 `'b'` |
| `reserved[2]` | `0x362` | 全局 boot-success handshake |
| `reserved[3]` | `0x363` | Slot A successful |
| `reserved[4]` | `0x364` | Slot A unbootable |
| `reserved[5]` | `0x365` | Slot B successful |
| `reserved[6]` | `0x366` | Slot B unbootable |

## 3. OEM 参数视图

部分 Host recovery/OTA 组件在 BCB 之后使用扩展参数区：

```text
0x000 - 0x3FF   bootloader_message_1k
0x400           type[32]
0x420           version[100]
0x484           cmd_line[256]
0x584           boot_status
0x588           update_status
0x58C           reserved[84]
0x5E0           system_type[32]
0x600           content[512]
```

两套视图由不同组件使用，不能将 OEM 参数结构替代 Android `bootloader_message`。

## 4. 访问组件

| 组件 | 方向 | 使用内容 |
|------|------|----------|
| PVM `vmm-boot-lcm` | 读写 | 读 `[0..2]`；retry 耗尽时写 `command`/`recovery` |
| GVM boot control HAL | 读写 | 维护 `[0..6]` |
| GVM ABL `RecoveryInit()` | 读 | 根据 `command` 选择 recovery |
| GVM ABL `IsCurrentSlotBootable()` | 读 | 检查 `[3]`/`[5]` |
| GVM Android recovery | 读写 | 读取、重写和清理 BCB |
| PVM `disk_symlink` | 条件只读 | ASYMMETRIC 模式读取 `[0]` |
| Host recovery/OTA | 读写 | OEM 参数区与 wipe/recovery 命令 |

updatemgr 的 `set_misc_flag()`/`obtain_misc_flag()` 当前使用本地状态文件，不直接写物理 `la_misc`。

## 5. GVM Boot Control 操作

GVM 产品启用 `ro.vendor.bootctrl.enable=true` 后，QTI boot control HAL 使用 misc 分支。

### 5.1 标记启动成功

`mark_boot_successful()`：

- 将 `[0]` 和 `[1]` 更新为当前 `ro.boot.slot_suffix`。
- 写 `[2]='y'`。
- Slot A 写 `[3]='y'`；Slot B 写 `[5]='y'`。

### 5.2 设置 Active Slot

`set_active_boot_slot(slot)`：

- `[0]` 保存当前运行 slot。
- `[1]` 写目标 slot。
- 清除 `[2]`。
- 清除目标 slot 的 successful 和 unbootable 标志。

### 5.3 标记不可启动

`set_slot_as_unbootable()`：

- Slot A 写 `[4]='y'`。
- Slot B 写 `[6]='y'`。

`is_slot_bootable()` 读取 `[4]`/`[6]`；`is_slot_marked_successful()` 同时检查 `[2]` 与 `[3]`/`[5]`。

## 6. Boot LCM 握手

Boot LCM 的 `check_gvm_boot_slot_info()` 读取 `[0]`、`[1]` 和 `[2]`。当前 START 流程只使用 `[2]`：

```text
reserved[2] == 'y'  -> reset retry counter
reserved[2] != 'y'  -> decrement retry counter
```

Boot LCM 提供写 `[1]` 和 `[2]` 的辅助函数，但当前主启动流程未调用这些写接口。

## 7. Recovery BCB

Boot LCM 触发 recovery 时写入：

```text
command  = "boot-recovery"
recovery = "recovery"
```

GVM ABL `RecoveryInit()` 从 misc 读取 `RecoveryMessage`，比较 `command` 与 `boot-recovery`。匹配后进入 recovery。

普通 recovery 入口只依赖 `command`。`DetectFDR()` 对 factory data reset 使用更完整的 recovery 参数，例如 wipe data 和 reason；两者是独立语义。

## 8. BCB 清理

Android recovery 的 `clear_bootloader_message()` 创建全零 BCB 并写回 misc。

`update_reserved_bit_in_struct()` 根据 `ro.vendor.asymmetric_support` 决定是否保留 slot 元数据：

| 属性 | 清理行为 |
|------|----------|
| `true` | 从旧 BCB 复制 `reserved[]`，仅清理 BCB 命令区 |
| `false` 或未设置 | 写入全零结构，`reserved[0..6]` 同时被清零 |

需要在 recovery 后保留独立 GVM slot 状态时，应启用该属性或在 BCB 清理实现中显式保留 `reserved[]`。

## 9. 实现位置

| 功能 | 路径 |
|------|------|
| Boot LCM misc 访问 | `vendor/qcom/opensource/vmm-boot-lcm/src/vmm-boot-lcm.cpp` |
| GVM boot control | `vendor/hardware/qcom/bootctrl/1.1/libboot_control_qti/libboot_control_qti.cpp` |
| GVM ABL recovery | `vendor/kernel_platform/bootable/bootloader/edk2/QcomModulePkg/Library/BootLib/Recovery.c` |
| GVM ABL slot | `vendor/kernel_platform/bootable/bootloader/edk2/QcomModulePkg/Library/BootLib/PartitionTableUpdate.c` |
| Android recovery BCB | `vendor/bootable/recovery/bootloader_message/bootloader_message.cpp` |

## 10. 相关文档

- [Boot Lifecycle Manager](vmm-boot-lifecycle.md)
- [GVM Slot 管理](gvm-slot-management.md)
- [VMM Service 配置](vmm-service-configuration.md)
