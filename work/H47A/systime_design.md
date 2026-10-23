# systime 模块原理与设计实现

## 1. 概述

`systime` 是 Voyah 智能座舱 Linux 侧的系统时间管理服务，负责从多个时间源获取准确时间、设置 Linux 内核系统时钟（`CLOCK_REALTIME`）、管理时区配置、以及向 MCU / Android 等外部系统同步时间。

**源码路径：** `voyah-cluster/systime/`
**编译产物：** `/usr/bin/systime`（Yocto recipe: `systime_00.01.01.bb`）

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                        systime 进程                                   │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │ systime_mgr  │  │  systime_tz  │  │ monotime     │                │
│  │ _thread      │  │  _thread     │  │ _thread      │                │
│  │ (核心时间逻辑)│  │  (时区管理)   │  │ (ADCU 对时)  │                │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                │
│         │                 │                 │                         │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐                │
│  │ systime_hab  │  │ tboxGptp    │  │  ipcMgr      │                │
│  │ _thread      │  │ _thread     │  │  (主循环线程) │                │
│  │ (Android RTC)│  │ (TBox PTP)  │  │               │                │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                │
│         │                 │                 │                         │
│         │                 │          ┌──────┴───────┐                │
│         │                 │          │  CClientMgr  │                │
│         │                 │          │  ┌─────────┐ │                │
│         │                 │          │  │ rpcd     │ │── CAN 0x4105  │
│         │                 │          │  │ client   │ │   → MCU       │
│         │                 │          │  ├─────────┤ │                │
│         │                 │          │  │ VoyahIPC │ │── MQTT Topic  │
│         │                 │          │  │ client   │ │   → Android   │
│         │                 │          │  └─────────┘ │                │
│         │                 │          └──────────────┘                │
└─────────┼─────────────────┼─────────────────┼────────────────────────┘
          │                 │                 │
    ┌─────┴─────┐    ┌──────┴──────┐   ┌─────┴──────┐
    │ Android   │    │ TBox gPTP   │   │ Linux      │
    │ (HAB)     │    │ /dev/ptp2   │   │ CLOCK_REAL │
    └───────────┘    └─────────────┘   └────────────┘
```

进程启动后共创建 **6 个线程**：

| 线程 | 入口函数 | 职责 |
|---|---|---|
| main | `ipcMgr::main_loop()` | IPC 消息主循环，处理 rpcd 和 VoyahIPC 消息 |
| systime_mgr | `systime_mgr::systime_mgr_thread()` | 核心时间管理：备份恢复 → 设置时钟 → RTC 同步 → 定时备份 |
| systime_hab | `systime_mgr::systime_hab_thread()` | 通过 HAB 与 Android RTC 驱动通信 |
| systime_timezone | `systime_mgr::systime_timezone_thread()` | 启动时读取/应用时区配置 |
| ADCU_time_sync | `systime_monotime::ADCUTimeSyncThread()` | 监控 ADCU 与本地 monotonic 时钟差异 |
| TBox_gPTP | `systime_tboxGptp::TboxGptpReportThread()` | 从 /dev/ptp2 读取 TBox gPTP 时间并上报 |

---

## 3. 时间源与优先级

systime 管理 **多个时间源**，按优先级从高到低排列：

### 3.1 优先级定义

```
SYSTIME_TIME_SOURCE_SERVER  (最高)  — 网络/服务端时间
SYSTIME_TIME_SOURCE_RTC              — MCU RTC 时间
SYSTIME_TIME_SOURCE_INVALID (最低)  — 无效/默认
```

`systime_common::systime_update_time_source()` 保证：**一旦有过 SERVER 级别的时间源，就不再被低优先级源覆盖。**

### 3.2 时间源详解

#### a) 备份文件（启动初始化）

- 路径：`/data/backup_systime`
- 每 60 秒将当前 `CLOCK_REALTIME` 写入此文件
- 启动时优先读取，避免断电后时间倒退
- 若文件不存在，使用编译期默认值 `1735660800`（2025-01-01 Asia/Shanghai）

#### b) MCU RTC 时间

- 通过 rpcd 发送 CAN 帧 `0x4105` 向 MCU 请求 RTC 时间
- MCU 回复后，若 RTC 时间 > 当前系统时间，则更新系统时钟
- 最多重试 10 次，每次超时 200ms
- 来源标记：`SYSTIME_TIME_SOURCE_RTC`

#### c) Voyah IPC — UTC 时间同步（服务端时间）

- Topic：`systime/TimeUTCSyncRsp/Set`
- 收到 `TOPIC_TIME_UTC_SYNC` 消息后直接调用 `clock_settime(CLOCK_REALTIME, ...)` 更新系统时间
- 时间格式：毫秒级 UTC 时间戳
- 来源标记：`SYSTIME_TIME_SOURCE_SERVER`（最高优先级）
- 设置后会同步时间到 MCU（发送 0x4105，dlc=4，含完整时间戳）

#### d) ADCU PTP 时钟

- 设备路径：`/dev/ptp1`
- 通过 `clock_gettime()` 读取 PTP 硬件时钟
- 与本地 `CLOCK_MONOTONIC` 比较，计算 ADCU 延迟（delayDiff）
- 当延迟变化超过 ±5ms 时，将延迟值写入 vcore Env（`timesync.ADCU_delay`）
- 轮询间隔：2 秒

#### e) TBox gPTP 时钟

- 设备路径：`/dev/ptp2`
- 通过 `clock_gettime()` 读取 PTP 硬件时钟
- 每 1 秒通过 Voyah IPC Topic `systime/TBoxGptpTimeRsp` 上报给 Android

#### f) Android HAB RTC（当前已禁用）

- Android 通过 HAB 写入时间 → `SYSTIME_HAB_MSG_OPCODE_WR_RTC_TIME`
- 实际调用的核心代码被 `#if 0` 注释，但保留了消息日志
- Android 读取时间 ← `SYSTIME_HAB_MSG_OPCODE_RD_RTC_TIME`，返回当前的 `CLOCK_REALTIME`

---

## 4. 启动流程

```
main()
  │
  ├─ systime_common::systimeInit()
  │     └─ 初始化配置:
  │          default_systime = 1735660800 (2025-01-01)
  │          default_timezone = "Asia/Shanghai"
  │          send_time_to_mcu = true
  │          send_time_to_mcu_interval = 500ms
  │
  ├─ systime_mgr::systime_mgr_start()        → 创建 systime_mgr 线程
  ├─ systime_mgr::systime_hab_start()         → 创建 HAB 线程 (Android RTC)
  ├─ systime_mgr::systime_tz_start()          → 创建时区管理线程
  ├─ systime_monotime::init()                 → 创建 ADCU 时钟监控线程
  ├─ ipcMgr::init()                           → 创建 CClientMgr (rpcd + VoyahIPC)
  ├─ systime_tboxGptp::init()                 → 创建 TBox gPTP 上报线程
  │
  └─ ipcMgr::main_loop()                      → 进入 IPC 消息主循环 (阻塞)
```

---

## 5. 核心时间设置流程

### 5.1 systime_mgr_thread 主逻辑

```
systime_mgr_thread()
  │
  ├─ 1. 读取 /data/backup_systime 获取上次保存的时间
  │     失败则使用 default_systime (2025-01-01)
  │
  ├─ 2. clock_settime(CLOCK_REALTIME, ts)
  │     将 Linux 系统时间设置为备份时间
  │     日志: "Update system time to: ..."
  │           "Set system time success."
  │
  ├─ 3. 读取当前系统时间验证
  │     日志: "Current system time is ..."
  │
  ├─ 4. 向 MCU 请求 RTC 时间 (帧 0x4105, dlc=0)
  │     最多重试 10 次，每次超时 200ms
  │     日志: "send 4105 rpcd data 00 00 00 00"
  │
  │     ┌─ 收到 RTC 回复:
  │     │  rtcTime = frame_bytes[0..3] (big-endian uint32)
  │     │  if (rtcTime > current_system_time):
  │     │      clock_settime(CLOCK_REALTIME, rtcTime)
  │     │      → 日志: "use rtc time ... directly."
  │     └─ 超时:
  │        → 日志: "recv rpcd rtc timeout, retry N"
  │
  └─ 5. 循环 (每 60 秒):
        systime_backup_time()
        → 将当前 CLOCK_REALTIME 写入 /data/backup_systime
```

### 5.2 动态时间更新 (Voyah IPC)

```
onVoyahIpcMsgRecv(msg)
  │
  ├─ TOPIC_TIME_ZONE_SYNC (0x0109):
  │     接收时区字符串 → systime_timezone_update() → 写文件
  │
  ├─ TOPIC_TIME_UTC_SYNC (0x010C):
  │     接收 UTC 毫秒时间戳
  │     → clock_settime(CLOCK_REALTIME, utc/1000)
  │     → 同步到 MCU (帧 0x4105, dlc=4, 含完整 4 字节时间)
  │     → 转发给 Android (TOPIC_TO_ANDROID_TIME_SYNC)
  │
  ├─ TOPIC_BOOT_TIME_SYNC_REQ (0x010D):
  │     处理开机时间同步请求 (GVM/PVM uptime 对齐)
  │
  └─ TOPIC_TBOX_GPTP_TIME_REQ (0x010F):
       Android 主动请求 gPTP 时间
       → 读取 /dev/ptp2 → 返回 TOPIC_TBOX_GPTP_TIME_RSP
```

---

## 6. 时区管理

### 6.1 数据文件

| 路径 | 用途 |
|---|---|
| `/data/timezone` | 时区名称文本文件（如 `Asia/Shanghai`） |
| `/data/localtime` | 指向 `/usr/share/zoneinfo/<tz>` 的软链接 |
| `/usr/share/zoneinfo/` | IANA 时区数据库目录 |

### 6.2 时区应用流程

```
systime_timezone_thread()
  │
  ├─ 1. 从 /data/timezone 读取时区名称
  │     日志: "timezone read from file '/data/timezone' is 'Asia/Shanghai'"
  │
  ├─ 2. 检查 /usr/share/zoneinfo/<tz> 是否存在
  │
  ├─ 3. unlink("/data/localtime")
  │
  ├─ 4. symlink("/usr/share/zoneinfo/<tz>", "/data/localtime")
  │     日志: "[TZ] Symlink /data/localtime -> /usr/share/zoneinfo/Asia/Shanghai created"
  │
  └─ 5. 日志: "tz_info read from file: Asia/Shanghai"
```

时区也可通过 Voyah IPC Topic `systime/TimeZoneSync/Set` 动态更新，更新时会同时调用 `systime_timezone_update()`（更新软链接）和 `systime_timezone_write_to_file()`（更新持久化文件）。

---

## 7. RTC 同步（SoC ↔ MCU）

### 7.1 协议

使用 rpcd（Remote Procedure Call Daemon）通过 CAN 总线与 MCU 通信：

| 方向 | CAN 帧 ID | DLC | 数据内容 |
|---|---|---|---|
| SoC → MCU（请求） | `0x4105` | 0 | 空（请求 RTC 时间） |
| MCU → SoC（回复） | `0x4105` | 4 | 4 字节 big-endian UTC 时间戳 |
| SoC → MCU（设置） | `0x4105` | 4 | 4 字节 big-endian UTC 时间戳 |

### 7.2 时间戳字节序

```cpp
// 接收: 4 字节 big-endian → uint32
rtcTime = frame_bytes[3] | (frame_bytes[2] << 8) 
        | (frame_bytes[1] << 16) | (frame_bytes[0] << 24);

// 发送: uint32 → 4 字节 big-endian
for (int i = 0; i < 4; i++)
    frame_bytes[i] = (time_sec >> (24 - i * 8)) & 0xFF;
```

---

## 8. HAB 接口（与 Android 通信）

HAB（Hardware Abstraction Bridge）用于 SoC Linux 侧与 Android VM 之间的 RTC 时间交互。

### 8.1 连接建立

- HAB MMID：`HAB_MMID_CREATE(MM_MISC, 0x21)`
- 支持 Android VM 重启后自动重连

### 8.2 消息协议

```cpp
typedef struct {
    int32_t op_code;   // 操作码: RD_RTC_TIME / WR_RTC_TIME
    time_t  time;      // 时间值
} systime_hab_msg_t;
```

| 操作码 | 方向 | 说明 |
|---|---|---|
| `RD_RTC_TIME` | Android → Linux | Android 读取当前系统时间 |
| `WR_RTC_TIME` | Linux → Android | Android 写入 RTC 时间（当前 `#if 0` 禁用） |

---

## 9. Voyah IPC Topic 接口

### 9.1 接收 Topic（Android/外部 → systime）

| Topic 字符串 | 内部 ID | 用途 |
|---|---|---|
| `systime/TimeZoneSync/Set` | `0x0109` | 设置时区 |
| `systime/TimeUTCSyncRsp/Set` | `0x010C` | UTC 时间同步 |
| `systime/BootTimeSyncReq/Set` | `0x010D` | 开机时间同步请求 |
| `systime/TBoxGptpTimeReq` | `0x010F` | 请求 TBox gPTP 时间 |

### 9.2 发送 Topic（systime → Android/外部）

| Topic 字符串 | 内部 ID | 用途 |
|---|---|---|
| `systime/TimeUTCSyncRsp` | `0x8108` | 向 Android 转发 UTC 时间 |
| `systime/BootTimeSyncRsp` | `0x8109` | 开机时间同步响应 |
| `systime/TBoxGptpTimeRsp` | `0x810B` | TBox gPTP 时间上报 |

---

## 10. ADCU 时钟监控

`systime_monotime` 负责监控 ADCU（Autonomous Driving Control Unit）的 PTP 时钟与本地 monotonic 时钟之间的偏差。

### 10.1 工作原理

```
每 2 秒:
  ├─ clock_gettime(ptp1_fd, &adcuTime)    // ADCU PTP 时间
  ├─ clock_gettime(CLOCK_MONOTONIC, &localTime)  // 本地 monotonic 时间
  │
  └─ adcuDelay = (adcuTime.tv_sec - localTime.tv_sec) * 1000
                + (adcuTime.tv_nsec - localTime.tv_nsec) / 1000000
     │
     └─ 若 delay 变化超过 ±5ms:
        写入 vcore Env: "timesync.ADCU_delay" = adcuDelay
```

### 10.2 PTP 设备

```
/dev/ptp1  — ADCU PTP 时钟
/dev/ptp2  — TBox PTP 时钟
```

通过 Linux PTP 子系统 `FD_TO_CLOCKID(fd)` 将文件描述符转换为 `clockid_t`，然后调用标准 `clock_gettime()` 读取。

---

## 11. 备份机制

### 11.1 目的

防止系统断电或重启后时间回退到默认值（2025-01-01），确保时间单调递增。

### 11.2 实现

```
每 60 秒 (systime_mgr_thread 主循环):
  systime_backup_time()
    ├─ clock_gettime(CLOCK_REALTIME, &ts)
    ├─ lseek(fd, 0, SEEK_SET)     // 定位到文件开头
    ├─ write(fd, &ts.tv_sec, sizeof(time_t))  // 写入 time_t (4 字节)
    └─ fsync(fd)                   // 确保落盘
```

备份文件：`/data/backup_systime`

### 11.3 恢复

```
启动时:
  systime_mgr_get_backup_time()
    ├─ access("/data/backup_systime", F_OK)
    ├─ open + read(fd, &time, sizeof(time_t))
    └─ 返回 time_t 值
```

---

## 12. 关键数据结构

### 12.1 systime_conf_t

```cpp
typedef struct {
    systime_rtc_info_t  rtc_info;           // RTC 设备信息
    char                default_timezone[256];// 默认时区
    int64_t             default_systime;     // 默认系统时间 (time_t)
    bool                support_pps;         // 是否支持 PPS
    int32_t             pps_int_io_idx;      // PPS IO 索引
    bool                send_time_to_mcu;    // 是否向 MCU 同步时间
    int32_t             send_time_to_mcu_interval;// MCU 同步间隔 (ms)
    systime_time_source_e time_source;      // 当前时间源类型
} systime_conf_t;
```

### 12.2 时间源枚举

```cpp
typedef enum {
    SYSTIME_TIME_SOURCE_INVALID = 0,  // 无效/未初始化
    SYSTIME_TIME_SOURCE_SERVER,       // 网络服务器时间 (最高优先级)
    SYSTIME_TIME_SOURCE_RTC,          // MCU RTC 时间
} systime_time_source_e;
```

### 12.3 类关系（单例模式）

```
systime_mgr       — 核心时间管理 (Singleton)
systime_common    — 公共工具函数 (Singleton)
systime_monotime  — ADCU 时钟监控 (Singleton)
systime_tboxGptp  — TBox gPTP 管理 (Singleton)
ipcMgr            — IPC 客户端管理 (Singleton)
CClientMgr        — 具体客户端容器 (rpcd + VoyahIPC)
```

---

## 13. 模块依赖

### 13.1 链接库

| 库 | 说明 |
|---|---|
| `librpcif.so` | rpcd IPC 通信库（提供 `rpcif_update_clusterstate()`） |
| `libvcore.so` | Voyah 核心库（Env 环境变量、日志流） |
| `libhabmm.so` | HAB 硬件抽象桥内存映射库 |
| `libpthread` | POSIX 线程 |

### 13.2 编译依赖

- `systime` recipe 依赖 `rpcd`、`voyahipc`、`tzdata`
- `rpcd` recipe 编译 `librpcif.so` + `rpcd` 守护进程 + `testrpcd`
- `systime` 链接 `librpcif.so`，共享同一进程空间执行 rpcif 代码

---

## 14. 日志系统

### 14.1 日志标签

```cpp
// systime 模块
#define LOG_HANDLE "CLS"
#define LOG_SPICE "-"
#define LOG_MODULE_NAME "systime"
// 输出: <CLS-systime>

// rpcd 模块 (librpcif.so)
// 输出: <rpcd>
```

### 14.2 日志格式

```
<timestamp> <level> <pid>(<tag>): <CLS-systime> [file:line] <tid>message
```

示例：
```
2026-08-08 10:48:30.000 4485 I 4637(systime): <CLS-systime> [systime_mgr.cpp:130] <4649>Update system time to: 1786157310, Sat Aug  8 10:48:30 2026
```

### 14.3 宏体系

| 宏 | 用途 |
|---|---|
| `IC_LOG_INFO(fmt, ...)` | 普通信息日志 |
| `IC_LOG_ERROR(fmt, ...)` | 错误日志 |
| `IC_LOG_WARNING(fmt, ...)` | 警告日志 |
| `VLOGI(cat)` | 流式信息日志 |
| `VLOGD_EVERY(n)` | 限频日志（每 n 次） |
| `VLOGE_INTERVAL(ms)` | 限频日志（按时间间隔） |

---

## 15. 典型日志时序

以一次正常启动为例：

```
1. [systime_mgr.cpp:130] Update system time to: 1786157310    ← 从备份文件恢复
2. [systime_mgr_tz.cpp:49] timezone read from file '/data/timezone' is 'Asia/Shanghai'
3. [systime_mgr_tz.cpp:178] tz_info read from file: Asia/Shanghai
4. [systime_mgr_tz.cpp:155] [TZ] Symlink /data/localtime -> /usr/share/zoneinfo/Asia/Shanghai created
5. [systime_mgr.cpp:139] Set system time success.            ← clock_settime 成功
6. [systime_mgr.cpp:78] Current system time is 1786157310     ← 验证读取
7. [systime_clientRpcd.cpp:173] send 4105 rpcd data 00 00 00 00  ← 请求 MCU RTC 时间
8. [rpcif.c:162] ipcif_on_connect_notice in                   ← rpcd 连接建立
9. [rpcif.c:315] rpcif_init out                               ← rpcd 初始化完成
```

---

## 16. 设计要点总结

1. **多层时间源兜底**：备份文件 → RTC → UTC 服务端，逐级提升精度，即使无网络也能从断电前的备份恢复合理时间
2. **优先级不可降级**：一旦获得过高精度时间源（SERVER），不会被低精度源（RTC）覆盖
3. **启动即可用**：不等待网络或 RTC 响应，先用备份/默认时间设置时钟，后续异步更新
4. **SoC ↔ MCU 双向同步**：SoC 从 MCU 获取 RTC 初始时间，收到网络时间后回写给 MCU
5. **多时钟域监控**：同时监控 ADCU PTP、TBox gPTP、本地 monotonic 三个时钟域，检测偏差
6. **Android 解耦**：通过 HAB（底层共享内存）和 Voyah IPC（MQTT Topic）两个独立通道与 Android 交互
7. **持久化防退化**：每 60 秒备份当前时间到文件，`fsync` 确保落盘，防止断电后时间回退
