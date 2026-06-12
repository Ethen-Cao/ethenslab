# USB OTA 失败根因分析：la_super 分区软链接缺失问题

## 1. 问题概述

### 1.1 现象

2026-06-11 15:48，通过 USB 对智能座舱 H47A 平台执行全量 OTA 升级时失败。OTA 由 Android (GVM) 发起，在 Linux (PVM) 中执行，升级进度停留在 47%，最终报错 `FIRMWARE_UPDATE_FAILED=[234]`。

### 1.2 直接原因

SOC 固件升级过程中 `patn6` 阶段失败——`mkfs.ext4` 格式化 `/dev/disk/by-partlabel/la_super_b` 时，设备节点不存在，格式化命令返回错误码 1。

### 1.3 根因

`disk_symlink` 程序在创建 `/dev/disk/by-partlabel/` 下的分区软链接时，遗漏了 `la_super_a` 和 `la_super_b` 两个条目，同时 udev 规则也被修改为不再自动创建 `la_*` 分区的软链接。两者叠加导致这两个设备节点不存在。

---

## 2. 技术背景

### 2.1 智能座舱系统架构 (PVM + GVM)

```
┌──────────────────────────────────────────────┐
│                  H47A 智能座舱                  │
│                                              │
│  ┌──────────────┐   ┌──────────────────────┐ │
│  │  PVM (Linux) │   │     GVM (Android)    │ │
│  │  SA8797 SoC  │◄──┤   guest VM on PVM    │ │
│  │              │   │                      │ │
│  │  - 底层硬件访问 │   │  - HMI 交互           │ │
│  │  - OTA 执行   │   │  - OTA 发起           │ │
│  │  - 分区管理   │   │  - 用户界面            │ │
│  └──────────────┘   └──────────────────────┘ │
│                                              │
│  USB OTA 流程: Android(HMI) 发起 → PVM 执行    │
└──────────────────────────────────────────────┘
```

- **PVM** (Primary Virtual Machine): 运行 Linux，直接管理 UFS 存储、GPT 分区表、文件系统。OTA 的实际执行——包括解压固件包、格式化分区、应用 patch——全部在 PVM 中完成。
- **GVM** (Guest Virtual Machine): 运行 Android，负责 HMI 交互。用户通过 Android 界面选择 U 盘中的 `update.zip` 并点击"升级"，请求通过 IPC 发送到 PVM 执行。
- **通信机制**: PVM 和 GVM 之间通过 `voyahipc` (基于 virtio) 通信，OTA 进度和结果通过 `IVCD` (Inter-VM Communication Daemon) 消息传递。

### 2.2 A/B 分区机制 (Seamless Update)

Android/Linux 系统使用 A/B 分区机制实现无缝升级：

```
┌─────────────────────────────────────────────┐
│              UFS 存储 (sda)                   │
│                                              │
│  A 槽 (当前运行)         B 槽 (待升级)          │
│  ┌─────────────────┐  ┌─────────────────────┐│
│  │ la_boot_a  sda26│  │ la_boot_b     sdg11 ││
│  │ la_super_a sda34│  │ la_super_b    sda35 ││
│  │ la_dtbo_a  sda28│  │ la_dtbo_b     sdg13 ││
│  │ la_vbmeta_a sda29│  │ la_vbmeta_b   sdg14 ││
│  │ ...             │  │ ...                 ││
│  └─────────────────┘  └─────────────────────┘│
│                                              │
│  当前从 A 槽启动 (androidboot.slot_suffix=_a)  │
│  OTA 升级到 B 槽，下次启动切换到 B 槽            │
└─────────────────────────────────────────────┘
```

- **A 槽** (`_a` 后缀): 当前正在运行的分区集合，OTA 时不被修改
- **B 槽** (`_b` 后缀): 空闲分区集合，OTA 时被写入新固件
- **slot_suffix**: 内核启动参数 `androidboot.slot_suffix=_a` 标识当前运行槽位
- **super 分区** (`la_super`): 动态分区元数据，包含 `system`、`vendor`、`product` 等逻辑分区的信息。大小约 20GB，是整个系统中最大的分区之一

### 2.3 GPT 分区表与 PARTLABEL

GPT (GUID Partition Table) 是 UEFI 规范的磁盘分区表格式，每个分区除了 UUID 外还有一个可读的 **PARTLABEL**（分区标签）：

```
$ blkid /dev/sda34 /dev/sda35
/dev/sda34: PARTLABEL="la_super_a" PARTUUID="74426df4-..."
/dev/sda35: PARTLABEL="la_super_b" PARTUUID="1c4c086a-..."
```

PARTLABEL 是固件烧录时写入的分区名称，存储在 GPT 表头中。它是唯一且不可变的（除非重新分区）。

#### H47A GPT 分区表（la_ 和 lv_ 分区）

| 分区标签 | 块设备 | 大小 | 用途 |
|----------|--------|------|------|
| `la_boot_a` | sda26 | 96MB | LA boot image A 槽 |
| `la_boot_b` | sdg11 | 96MB | LA boot image B 槽 |
| `la_super_a` | sda34 | 20GB | LA super 动态分区 A 槽 |
| `la_super_b` | sda35 | 20GB | LA super 动态分区 B 槽 |
| `la_dtbo_a` | sda28 | 8MB | LA DTBO A 槽 |
| `la_dtbo_b` | sdg13 | 8MB | LA DTBO B 槽 |
| `lv_system_a` | sda18 | 6GB | LV system A 槽 |
| `lv_boot_a` | sda17 | 256MB | LV boot A 槽 |
| ... | ... | ... | ... |

---

## 3. udev 与 by-partlabel 机制

### 3.1 udev 简介

**udev** (userspace device manager) 是 Linux 的设备管理器，运行在用户空间。它的核心职责：

1. **动态设备节点管理**: 当内核检测到新设备（插入 U 盘、加载驱动、发现分区），udev 在 `/dev/` 下创建设备节点
2. **持久化设备命名**: 根据设备属性（序列号、分区标签、文件系统 UUID）创建稳定的符号链接
3. **规则触发**: 匹配设备属性并执行自定义操作（设置权限、加载驱动、启动服务）

```
内核 uevent ──► systemd-udevd ──► 匹配 udev 规则 ──► 创建设备节点/软链接
                  │
                  ├── /dev/sda34 (块设备节点)
                  ├── /dev/disk/by-partlabel/la_super_a (软链接)
                  ├── /dev/disk/by-partlabel/la_super_bak (软链接)
                  └── /dev/disk/by-uuid/74426df4-... (软链接)
```

### 3.2 by-partlabel 软链接的创建

`/dev/disk/by-partlabel/` 目录下的软链接由 **`60-persistent-storage.rules`** 这个 udev 规则文件负责创建。

**原始规则** (systemd 内置):

```udev
# 为所有具有 PARTLABEL 的 GPT 分区创建 by-partlabel 软链接
ENV{ID_PART_ENTRY_SCHEME}=="gpt", \
ENV{ID_PART_ENTRY_NAME}=="?*", \
SYMLINK+="disk/by-partlabel/$env{ID_PART_ENTRY_NAME}"
```

规则含义：
- `ENV{ID_PART_ENTRY_SCHEME}=="gpt"` — 仅匹配 GPT 分区表的分区
- `ENV{ID_PART_ENTRY_NAME}=="?*"` — 分区必须有 PARTLABEL（非空）
- `SYMLINK+=` — 创建以 PARTLABEL 命名的软链接

执行效果：
```
sda34 PARTLABEL="la_super_a" → /dev/disk/by-partlabel/la_super_a → ../../sda34
sda35 PARTLABEL="la_super_b" → /dev/disk/by-partlabel/la_super_b → ../../sda35
sda26 PARTLABEL="la_boot_a"  → /dev/disk/by-partlabel/la_boot_a  → ../../sda26
sdg11 PARTLABEL="la_boot_b"  → /dev/disk/by-partlabel/la_boot_b  → ../../sdg11
...（对所有 GPT 分区生效）
```

### 3.3 A/B 槽位软链接的槽位感知需求

在 A/B 分区系统中，除了原始 PARTLABEL 软链接（`la_super_a`、`la_super_b`），还需要**与槽位无关的别名**。

例如，OTA 脚本和系统服务希望引用"当前的 super 分区"而不是硬编码 `_a` 或 `_b`：

```
# 槽位相关 (始终指向固定分区)
la_super_a → sda34    # 始终是物理 A 槽
la_super_b → sda35    # 始终是物理 B 槽

# 槽位无关 (根据当前启动槽位动态决定)
la_super → sda34      # 当前活跃的 super 分区 (如果从 A 启动)
la_super_bak → sda35  # 非活跃的 super 分区 (如果从 A 启动)
```

为了实现这个需求，系统引入了两套机制：

**1. udev 规则 `99-persist-storage-ab.rules`** — 创建 `_bak` 别名:

```udev
# 当从 A 槽启动时，B 槽分区改名为 _bak
ENV{androidboot.slot_suffix}=="_a", \
ENV{ID_PART_ENTRY_NAME}=="la_super_b", \
SYMLINK+="disk/by-partlabel/la_super_bak"

# 当从 A 槽启动时，A 槽分区改名为无后缀（活跃槽）
ENV{androidboot.slot_suffix}=="_a", \
ENV{ID_PART_ENTRY_NAME}=="la_super_a", \
SYMLINK+="disk/by-partlabel/la_super"
```

**2. `disk_symlink` 程序** — 创建精确的 `_a`/`_b` 软链接（替代 udev 自动创建）。

---

## 4. disk_symlink 程序

### 4.1 为什么引入 disk_symlink

原始的 udev 规则 `60-persistent-storage.rules` 会为**所有** GPT 分区创建 by-partlabel 软链接。在引入 A/B 槽位切换支持后，需要对 `la_*`、`lv_*` 等分区进行**槽位感知**的软链接管理。

`disk_symlink` 是一个 C++ 编写的 **oneshot systemd 服务**，在系统启动早期 (`sysinit.target`) 运行一次，负责：

1. 从 `/proc/cmdline` 读取 `androidboot.slot_suffix` 确定当前槽位
2. 读取 misc 分区获取槽位切换配置
3. 根据槽位信息创建精确的分区软链接

### 4.2 disk_symlink 服务的启动

```ini
# disksymlink.service
[Unit]
Description=Disk Partition Symlink
DefaultDependencies=no
Before=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/disksymlink-service

[Install]
WantedBy=sysinit.target
```

`sysinit.target` 确保它在系统初始化的早期阶段运行，在任何需要访问分区软链接的服务之前完成。

### 4.3 disk_symlink.cpp 核心逻辑

```cpp
// 1. 无需槽位的固定分区软链接（直接按 PARTLABEL 查找并创建）
static disk_symlink_no_slot_t g_disk_symlink_no_slot[] = {
   {"la_boot_a",          "/dev/disk/by-partlabel/la_boot_a"      },
   {"la_boot_b",          "/dev/disk/by-partlabel/la_boot_b"      },
   {"la_vbmeta_a",        "/dev/disk/by-partlabel/la_vbmeta_a"    },
   {"la_vbmeta_b",        "/dev/disk/by-partlabel/la_vbmeta_b"    },
   // ... 其他 _a/_b 分区
   {"la_super",           "/dev/disk/by-partlabel/la_super"       },
   // ❌ 缺失: la_super_a, la_super_b
};

// 2. 需要槽位感知的软链接（根据当前 slot 动态生成）
static disk_symlink_t g_disk_symlink[] = {
   {"",           "la_boot_",          "/dev/disk/by-partlabel/la_boot"      },
   {"",           "la_vbmeta_",        "/dev/disk/by-partlabel/la_vbmeta"    },
   // ... 通过 misc 分区或 cmdline 确定 slot suffix
   // ❌ 缺失: la_super_ 条目
};
```

程序流程：

```
main()
  │
  ├── mkdir /dev/disk/by-partlabel
  ├── 遍历 g_disk_symlink_no_slot[]
  │     └── get_dev_by_partname() → 查找 GPT PARTLABEL → symlink()
  │
  ├── 读取 slot_suffix (从 /proc/cmdline)
  ├── 读取 slot_switch_config (从 misc 分区)
  │
  └── 遍历 g_disk_symlink[]
        └── get_partname_with_slot() → 拼接 "_a" 或 "_b"
              └── get_dev_by_partname() → symlink()
```

### 4.4 与 udev 规则的配合

`systemd_%.bbappend` 中的 sed 命令修改了 udev 规则：

```
原始:
  SYMLINK+="disk/by-partlabel/$env{ID_PART_ENTRY_NAME}"

修改后:
  ENV{ID_PART_ENTRY_NAME}!="la_*",
  ENV{ID_PART_ENTRY_NAME}!="lv_*",
  ENV{ID_PART_ENTRY_NAME}!="bluetooth*",
  ENV{ID_PART_ENTRY_NAME}!="modem*",
  ENV{ID_PART_ENTRY_NAME}!="dsp*",
  SYMLINK+="disk/by-partlabel/$env{ID_PART_ENTRY_NAME}"
```

**职责划分**：

| 分区类型 | by-partlabel 软链接由谁创建 |
|----------|---------------------------|
| `la_*`, `lv_*` | **disk_symlink**（udev 不再创建） |
| `bluetooth*`, `modem*`, `dsp*` | **disk_symlink**（udev 不再创建） |
| `xbl_*`, `tz_*`, `hyp_*`, `uefi_*`, `boot_*` 等 | **udev** (`60-persistent-storage.rules`) |

---

## 5. OTA 升级流程

### 5.1 整体流程

```
┌──────────────────────────────────────────────────────────────┐
│                    USB OTA 升级流程                            │
│                                                              │
│  GVM (Android)              PVM (Linux)          MCU         │
│  ─────────────              ───────────          ───         │
│                                                              │
│  1. 用户选择U盘升级包 ──IPC──► 2. updatemgr 接收请求            │
│     /ota/android/usb/         updateSource=USB               │
│     update.zip                updateDev=SOC+MCU              │
│                                                              │
│                            3. 启动 updatemgr_script_0(SOC)    │
│                               启动 updatemgr_script_1(MCU)    │
│                                                              │
│                            4. 解压 update.zip                │
│                               ├── firmware/  (SOC固件)        │
│                               ├── android/   (系统镜像)        │
│                               ├── pvm/       (PVM镜像)        │
│                               ├── MCU/       (MCU固件) ──IPC──► MCU升级 │
│                               └── peripheral/ (外设固件)       │
│                                                              │
│                            5. 分区操作                        │
│  ◄── IPC: 进度45% ──          ├── patn1: system_b zstd解压    │
│                               ├── patn2: vendor_b hpatchz     │
│                               ├── ...                        │
│                               ├── patn6: la_super_b ← 在此失败  │
│                               │    mkfs.ext4 格式化            │
│                               │    写入 super 分区元数据        │
│                               └── patn0: firmware 分区         │
│                                                              │
│  ◄── IPC: FAILED[234] ──    6. 上报失败                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 patn6 阶段详情

`patn6` 负责升级 `la_super` 分区的 B 槽。super 分区是 Android 动态分区系统的核心，包含：

```
la_super (20GB)
├── system_a / system_b    (系统镜像)
├── vendor_a / vendor_b    (供应商镜像)
├── product_a / product_b  (产品镜像)
└── ... (其他动态分区)
```

升级步骤：

```
patn6 流程:
  1. unzip la_super.patch0~79 (80个patch文件)
  2. 格式化 la_super_b 分区:
     /usr/sbin/mkfs.ext4 -F -q /dev/disk/by-partlabel/la_super_b
     ↑                                                      ↑
     └── 此处失败: 设备节点 /dev/disk/by-partlabel/la_super_b 不存在
  3. 应用 patch (未执行)
  4. 校验 (未执行)
```

### 5.3 错误码传递链

```
mkfs.ext4 返回 1 (设备不存在)
  → process_script_format_cmd ret=[-1]
    → format_partition_start_updfs_func error
      → format mainfs error
        → patn6 process_patn_update_end_func result=[-1]
          → devid0 update finish err_code=[234]
            → IVCD_CLIENT_MSG_ID_FIRMWARE_UPDATE_FAILED=[234]
              → GVM 显示"升级失败"
```

---

## 6. 根因分析

### 6.1 变更时间线

```
0609 版本                          0612 版本
─────────                         ─────────
udev 规则:                         udev 规则:
  为所有 GPT 分区创建                  la_* 被排除, 不再创建
  by-partlabel 软链接                 by-partlabel 软链接
  ✅ la_super_a                     ❌ la_super_a
  ✅ la_super_b                     ❌ la_super_b

disk_symlink:                       disk_symlink:
  (不存在)                            只创建列表中明确指定的分区
                                    ✅ la_boot_a, la_boot_b ...
                                    ❌ la_super_a, la_super_b (遗漏)
```

**变更的代码**：`layers/meta-qti-automotive/recipes-core/systemd/systemd_%.bbappend`

```diff
+ # Create by-partlabel symlink for la/lv/bluetooth/modem/dsp devices
+ # in disksymlink-service service, remove these operations from plain udev rules
+ sed -i 's#...SYMLINK+="disk/by-partlabel/$env{ID_PART_ENTRY_NAME}"#
+          ...ENV{ID_PART_ENTRY_NAME}!="la_*",
+             ENV{ID_PART_ENTRY_NAME}!="lv_*",
+             ...SYMLINK+="disk/by-partlabel/$env{ID_PART_ENTRY_NAME}"#'
```

**提交信息**：

| 项目 | 内容 |
|------|------|
| **Jira** | IVI8397-3231 |
| **提交者** | xuejihuang `<xuejihuang@pateo.com.cn>` |
| **时间** | 2026-05-21 (disk_symlink), 2026-06-02 (udev sed) |
| **主题** | MST36 update — 引入 disk_symlink 替代 udev 管理 la_/lv_ 分区软链接 |

### 6.2 遗漏分析

`disk_symlink.cpp` 的 `g_disk_symlink_no_slot[]` 数组中，其他 la_ 分区都有完整的 `_a`/`_b` 条目：

```cpp
// ✅ 有完整 _a/_b
{"la_boot_a",          "/dev/disk/by-partlabel/la_boot_a"      },  // line 60
{"la_boot_b",          "/dev/disk/by-partlabel/la_boot_b"      },  // line 77
{"la_vbmeta_a",        "/dev/disk/by-partlabel/la_vbmeta_a"    },  // line 61
{"la_vbmeta_b",        "/dev/disk/by-partlabel/la_vbmeta_b"    },  // line 78
{"la_init_boot_a",     "/dev/disk/by-partlabel/la_init_boot_a" },  // line 57
{"la_init_boot_b",     "/dev/disk/by-partlabel/la_init_boot_b" },  // line 74
{"la_vendor_boot_a",   "/dev/disk/by-partlabel/la_vendor_boot_a"}, // line 58
{"la_vendor_boot_b",   "/dev/disk/by-partlabel/la_vendor_boot_b"}, // line 75
{"la_dtbo_a",          "/dev/disk/by-partlabel/la_dtbo_a"      },  // line 59
{"la_dtbo_b",          "/dev/disk/by-partlabel/la_dtbo_b"      },  // line 76

// ✅ 有基础名称
{"la_super",           "/dev/disk/by-partlabel/la_super"       },  // line 93

// ❌ 缺失!
{"la_super_a",         "/dev/disk/by-partlabel/la_super_a"       },  // 应添加
{"la_super_b",         "/dev/disk/by-partlabel/la_super_b"       },  // 应添加
```

**为什么 `la_super` 与其他分区不同？**

`la_super` 不像 `la_boot`/`la_vbmeta` 等在 `g_disk_symlink[]`（槽位感知数组）中有 `la_super_` 前缀条目。这是因为 `la_super` 分区的命名比较特殊——它直接使用了基础名称 `la_super` 而不是 `la_super_` 作为前缀。但 `g_disk_symlink_no_slot[]` 中添加 `la_super_a`/`la_super_b` 仍然是必要的，因为 OTA 脚本硬编码引用了这两个精确名称。

### 6.3 为什么 OTA 脚本必须用 `_a`/`_b` 精确名称

OTA 脚本 `updatemgr_script_run_cfg.h` 中硬编码了分区路径：

```c
#define UPDATE_LA_SUPER_A_UFS_BLOCK_PATH  "/dev/disk/by-partlabel/la_super_a"
#define UPDATE_LA_SUPER_B_UFS_BLOCK_PATH  "/dev/disk/by-partlabel/la_super_b"
```

OTA 升级时必须明确指定是 A 槽还是 B 槽，不能使用槽位无关的别名（如 `la_super`），因为：

1. **A/B 升级语义**: OTA 总是升级到**非活跃槽位**（当前从 A 启动，则升级 B 槽）
2. **避免误操作**: 使用精确分区名可以防止意外覆盖当前运行的系统分区
3. **交叉升级支持**: 某些场景下可能需要强制升级特定槽位

---

## 7. 设计缺陷总结

### 7.1 架构问题

```
                ┌──────────────┐
                │   GPT 分区表   │  ← 权威数据源: PARTLABEL="la_super_b"
                └──────┬───────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │  udev    │ │  disk_   │ │   OTA    │
   │  rules   │ │  symlink │ │  scripts │
   └──────────┘ └──────────┘ └──────────┘
   创建:        创建:        期望:
   la_super_bak la_super    la_super_a
   (非活跃槽)    (活跃槽)     la_super_b
                              (精确槽位)

   三套命名体系不一致：
   - GPT PARTLABEL:   la_super_a, la_super_b
   - udev 规则:       la_super (活跃), la_super_bak (非活跃)
   - disk_symlink:    la_super (活跃), ❌缺失 _a/_b
   - OTA 脚本:        la_super_a, la_super_b ← 硬编码
```

核心问题是**缺乏单一权威的命名映射表**。`la_super_a`/`la_super_b` 这两个软链接本应由 `disk_symlink` 创建（因为 udev 已不再创建），但 `disk_symlink` 的静态列表中遗漏了它们。

### 7.2 流程缺陷

1. **无自动化校验**: 没有在构建时或启动时验证 `disk_symlink` 的静态列表是否覆盖了所有 OTA 脚本引用的分区
2. **手动维护映射表**: `disk_symlink.cpp` 中的分区列表是硬编码的 C 数组，新增分区需要手动更新代码
3. **变更影响分析不足**: 将 `la_*` 分区从 udev 迁移到 `disk_symlink` 时，没有全量对比原始 udev 创建的分区列表和 `disk_symlink` 创建的分区列表

---

## 8. 修复方案

### 8.1 代码修复

在 `system/core/disksymlink/disk_symlink.cpp` 中添加缺失条目：

```cpp
// g_disk_symlink_no_slot[] 中添加 (约 line 93 后):
{"la_super_a",         "/dev/disk/by-partlabel/la_super_a"       },
{"la_super_b",         "/dev/disk/by-partlabel/la_super_b"       },
```

同时在 `g_disk_symlink[]` 中添加槽位感知条目（约 line 42 后）:

```cpp
{"la_misc",    "la_super_",          "/dev/disk/by-partlabel/la_super"      },
```

### 8.2 临时修复（设备上）

在 PVM 上手动创建软链接：

```bash
ln -sf ../../sda34 /dev/disk/by-partlabel/la_super_a
ln -sf ../../sda35 /dev/disk/by-partlabel/la_super_b
```

### 8.3 预防措施

1. **构建时校验**: 添加脚本对比 OTA 脚本中引用的分区路径与 `disk_symlink.cpp` 中的条目
2. **启动时自检**: `disk_symlink` 添加 verbose 日志，列出所有已创建和失败的软链接
3. **测试用例**: 添加 `la_super_a`/`la_super_b` 存在性检查到 OTA 前置条件验证中
4. **代码 review checklist**: 修改 `disk_symlink.cpp` 的分区列表时，需同步检查 OTA 分区路径定义

---

## 9. 相关文件索引

| 文件 | 作用 |
|------|------|
| `system/core/disksymlink/disk_symlink.cpp` | disk_symlink 主程序，定义分区到软链接的映射表 |
| `system/core/disksymlink/disksymlink.service` | systemd oneshot 服务定义 |
| `layers/meta-qti-automotive/recipes-core/systemd/systemd_%.bbappend` | 修改 udev 规则排除 la_/lv_ 分区 |
| `vendor/qcom/opensource/kiumd/dspfirmware-mount/99-persist-storage-ab.rules` | A/B 槽位 `_bak` 别名 udev 规则 |
| `voyah-cluster/updatemgr/inc_script/updatemgr_script_run_cfg.h` | OTA 分区路径宏定义 |
| `voyah-cluster/updatemgr/inc_script/updatemgr_common.h` | OTA 错误码定义 (`FW_UPDATE_RST_UPDATE_LA_SUPER_FMT_ERR`) |

---

## 10. 总结

本次 USB OTA 失败的根因是 **`disk_symlink.cpp` 在替代 udev 管理 `la_*` 分区软链接时，遗漏了 `la_super_a` 和 `la_super_b` 两个条目**。这是一个典型的**手动迁移遗漏**问题——将功能从旧机制（udev 自动创建）迁移到新机制（disk_symlink 静态列表）时，静态列表未能覆盖所有原有条目。

根本原因是缺乏从"代码引用的分区路径"到"软链接创建逻辑"的端到端可追溯性。OTA 脚本硬编码的分区路径、GPT 分区标签、udev 规则、disk_symlink 映射表这四个环节应当保持一致，但当前没有任何自动化机制来保证这一点。
