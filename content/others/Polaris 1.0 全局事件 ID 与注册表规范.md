+++
date = '2025-12-24T17:17:50+08:00'
draft = true
title = 'Polaris 1.0 全局事件 ID 与注册表规范'
+++

# Polaris 1.0 全局事件 ID 与注册表规范

**Global Event ID & Registry Specification**

## 版本历史

| 文档版本 | 修改日期 | 修改人 | 说明 |
| --- | --- | --- | --- |
| V1.0 | 2025-12-XX | [xxx名字] | 初始发布 |

## 概述

为了支撑 Polaris 1.0 实现“端云一体”的性能与稳定性监控，解决跨 SoC（Android/Linux）与 MCU 的异构数据治理难题，并适配车云 SDK 的接口限制，本项目采用 **“注册制 + 扁平化 ID”** 的管理模式。

**核心原则：**

1. **ID 去语义化**：EventID 仅作为唯一索引（Key），不再承载复杂的业务含义。
2. **定义元数据化**：所有的业务属性（模块、等级、日志策略）统一在《全局注册表》中维护。
3. **文档即代码**：注册表是唯一可信来源，模版代码以及常量由注册表自动生成。

## 事件 ID 编码规范

Polaris 事件 ID 采用 **10 位纯数字** 格式，分为三个物理段。

### ID 结构公式

`[Prefix (3位)]` + `[Scope (1位)]` + `[Sequence (6位)]`

### 字段定义

| 字段 | 位数 | 说明 | 取值定义 |
| --- | --- | --- | --- |
| Prefix | 3 | 物理系统归属 (硬性约束） | 666: Android 系统; 668: Linux Host 系统; 685: MCU 子系统 |
| Scope | 1 | 管理域 (ID 分配权隔离） | 0: 平台/系统维护; 1: 业务/应用维护 |
| Sequence | 6 | 流水号 (全局唯一） | 000001 ~ 999999 按申请顺序递增，不分类，不回退。 |

## 全局事件注册表模版

本注册表建议使用 **Git 托管的 CSV 文件** 或 **在线协作表格** 维护。它是生成 SDK 代码的唯一依据。

### 核心字段定义

| 分类 | 列名 | 说明 | 示例 |
| --- | --- | --- | --- |
| Identity | EventID | 10位唯一码 | `6660000001` |
|  | EventName | 代码常量名 | `GVM_SYS_FW_RESET` |
| Logic | Logical_Module | 逻辑归属模块 (用于云端分类) | `Framework`, `Audio`, `Map` |
|  | Owner | 责任团队 (用于自动派单) | `System-Team`, `BSP-Team` |
| SDK | SDK_Type | 映射车云 SDK type (1=Info, 2=Exc, 3=Err) | `3` |
|  | SDK_Level | 映射车云 SDK elevel (0=Biz, 1=Sys) | `1` |
| Policy | Log_Source_Path | 大文件源路径目录 (不含文件名)<br>用于云端拉取时拼接 Base Path | `/log/perflog/anr/`; `/log/perflog/tombstones/` |
|  | Desc_Schema | 业务专属字段定义<br>格式：`key:type` (支持 int, long, string, float, bool) | `reason:string` |
| Meta | Status | 状态: `Active`, `Deprecated` | `Active` |
|  | Trigger_Condition | QA 测试验收标准 (文档用) | `Main thread blocked > 60s` |

> **注意：** `Desc_Schema` 仅定义业务特有的字段。以下 **5 个 Common 字段** 为系统保留字段，由 SDK 自动注入或通过专用接口设置，**严禁**出现在 `Desc_Schema` 中：

| 字段 | 类型 | 说明 | 来源/处理逻辑 |
| --- | --- | --- | --- |
| **tid** | string | **Trace ID**。全链路追踪 ID。用于串联跨端/跨进程调用。 | 自动获取 |
| **pid** | int | **Process ID**。定位具体进程实例。 | 自动获取 / 代上报时覆写 |
| **proc** | string | **Process Name**。明确责任进程（如 `com.map.app`）。 | 自动获取 / 代上报时覆写 |
| **ver** | string | **Version**。业务模块版本号（如 `1.2.0`）。 | 自动获取 / 代上报时覆写 |
| **logf** | string | **Log Filename**。大文件文件名（不含路径）。 | 手动设置 (`setLogRef`)，默认为空 |

**语法说明：**
`Desc_Schema` 支持可选参数标记 `?`。

* **示例**：`reason:string?`
* **解释**：表示除了系统自动注入的 `tid`, `pid` 等字段外，该事件还包含一个**可选**的业务字段 `reason`（即构造函数中不强制要求传入 `reason`）。

### 表格内容示例

| EventID | EventName | Logical_Module | Owner | SDK_Type | SDK_Level | Log_Source_Path | Desc_Schema (JSON Fields) | Status | Trigger_Condition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `6660000001` | `GVM_SYS_FW_RESET` | Framework | System Team | 3 | 1 | `/data/anr/` | `reason:string` | Active | SystemServer Watchdog |
| `6660000002` | `GVM_APP_CRASH` | AppManager | System Team | 3 | 1 | `/data/tombstones/` | `signal:int; exception:string?` | Active | Any Java/Native Crash |
| `6660000003` | `GVM_APP_ANR` | AppManager | System Team | 2 | 1 | `/data/anr/` | `activity:string?` | Active | Any App Main Thread Block |
| `6661000099` | `GVM_MUSIC_LAUNCH_SLOW` | MusicApp | Music Team | 1 | 0 | `NONE` | `dur:long; stage:string` | Active | Cold Start > 2000ms |
| `6850000001` | `MCU_BATT_VOLT_LOW` | Power Team | Power | 1 | 1 | `NONE` | `vol:float; current:float` | Active | Vol < 9V |


### 注册表变更与 Schema 演进规则

为了保证端侧代码（Old Version）与云端解析（New Config）的兼容性，注册表变更必须遵循 "Copy-On-Write" (写时复制) 原则。

**规则 1：Schema 变更即新事件**
如果一个已发布的 Active 事件需要修改 Desc_Schema（无论是删除字段、修改字段类型，还是增加必填字段），**严禁直接修改原行**。

* 操作步骤：
1. 将原 EventID 的状态标记为 Deprecated。
2. 申请一个新的 EventID。
3. EventName 建议增加后缀 `_V2`, `_V3` 以示区分。


**规则 2：非破坏性变更**
仅修改 Owner、Trigger_Condition、Log_Source_Path、Status 等不影响代码编译和数据解析的字段，允许直接修改原行。

**规则 3：弃用流程**
标记为 Deprecated 的事件：

1. 代码生成：生成的代码会添加 `@Deprecated` 注解，提示开发者迁移。
2. 运行时：Polaris Agent 依然允许上报该 ID，保证旧版本车机的兼容性。
3. 云端：云端应将此类数据标记为“遗留数据”。

## 6. 常量命名规范 (Naming Convention)

为了保证代码可读性，注册表中的 `EventName` 必须遵循以下命名标准。

**SCOPE_MODULE_[LAYER/OBJECT]_CONDITION**

| 字段 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| SCOPE | ✅ | 物理/虚拟域，界定事件发生的系统边界。 | `GVM`, `PVM`, `MCU` |
| MODULE | ✅ | 业务模块，界定事件所属的功能集合。 | `AUDIO`, `MAP`, `POWER` |
| LAYER / OBJECT | ⚪ | 层级或对象，进一步细化定位。 | `FW`, `HAL`, `SRV`, `ACT` |
| CONDITION | ✅ | 状态/结果，标准化的后缀 | `CRASH`, `TIMEOUT`, `ANR` |

* **CONDITION (必须使用标准后缀)**:

1. **致命异常类**

| 后缀 | 含义 | WBS 对应场景 | 示例 EventName |
| --- | --- | --- | --- |
| _CRASH | 进程崩溃/退出 | Top Crash 榜单、核心进程 Crash | `GVM_APP_MAP_CRASH`; `GVM_SYS_SURFACE_CRASH` |
| _ANR | 应用无响应 | Top ANR 榜单 | `GVM_APP_MUSIC_ANR` |
| _RESET | 系统/服务复位 | SystemServer 重启、系统重启 | `GVM_SYS_FW_RESET`; `PVM_HOST_OS_RESET` |
| _OOM | 内存溢出 (Java) | 应用 OOM 事件 | `GVM_APP_MAP_OOM` |
| _KILLED | 被强制杀死 | LMK 杀进程、资源枯竭导致被杀 | `GVM_APP_TIKTOK_KILLED`; `GVM_SYS_PROC_LMK_KILLED` |
| _BLANK | 黑屏/无显示 | 行驶中黑屏 (安全) | `GVM_DISP_SCREEN_BLANK` |

2. **性能与体验类**

| 后缀 | 含义 | WBS 对应场景 | 示例 EventName |
| --- | --- | --- | --- |
| _SLOW | 速度慢/耗时久 | Activity 启动速度 | `GVM_APP_MAP_LAUNCH_SLOW` |
| _BLOCK | 线程阻塞 | 主线程拥堵 (未达ANR但超过阈值) | `GVM_APP_UI_THREAD_BLOCK` |
| _JANK | 掉帧/卡顿 | 界面掉帧监控 | `GVM_APP_LIST_SCROLL_JANK` |
| _TIMEOUT | 通信/等待超时 | Binder 异常通信 | `GVM_SYS_BINDER_TX_TIMEOUT` |
| _BUSY | 繁忙/缓冲区满 | Binder 缓冲区满、CPU 满载 | `GVM_SYS_BINDER_BUSY` |

3. **资源泄漏与越限类**

| 后缀 | 含义 | WBS 对应场景 | 示例 EventName |
| --- | --- | --- | --- |
| _LEAK | 资源泄漏 | 文件句柄(FD)泄漏 | `GVM_APP_MAP_FD_LEAK` |
| _HIGH | 占用过高 | CPU/内存趋势过高 | `GVM_SYS_CPU_LOAD_HIGH`; `GVM_APP_MEM_USAGE_HIGH` |
| _LOW | 资源不足 | 磁盘空间不足 | `GVM_SYS_STORAGE_LOW` |

4. **链路与管控类**

| 后缀 | 含义 | WBS 对应场景 | 示例 EventName |
| --- | --- | --- | --- |
| _LOST | 连接丢失/断链 | 仪表通信丢失 | `MCU_IC_CONN_LOST` |
| _REJECT | 策略拒绝 | 遥测命令白名单拦截、行车态禁止 | `GVM_RMT_CMD_REJECT` |
| _FAIL | 执行失败 | 遥测命令执行出错 | `GVM_RMT_CMD_EXEC_FAIL` |

> **注意**：代码生成器必须对上述 14 个后缀进行 **Whitelist** 校验，严禁使用非标准后缀。

## 7. 注册表管理与自动化流程

严禁开发人员手动修改代码中的 ID 常量，必须遵循以下流程：

### 7.1 维护流程

1. **申请**：开发人员在《注册表》中新增一行，申请新的 ID (使用 `MAX_ID + 1`)。
2. **评审**：Polaris项目组评审 `EventName` 是否规范、`SDK_Type` 是否准确。
3. **提交**：将更新后的 CSV/Excel 提交至 `polaris-protocol` Git 仓库。
4. **生成**：CI 流水线自动触发 `polaris-codegen` 脚本。

## 8. 车云 SDK 接口定义

```java
public native int sendWcLog(long evid, byte etype, short elevel, long eTime, String edesc);

```

### 8.1 功能描述

向车云 Native 进程发送维测流日志，车云 Native 进程最终负责将这些事件上传云端。

### 8.2 参数说明

| 参数名 | 类型 | 描述 | 备注 |
| --- | --- | --- | --- |
| evid | long | 事件 ID | 必填 |
| etype | byte | 事件类型 | 必填 |
| elevel | short | 事件等级 | 必填 |
| eTime | long | 事件时间戳（毫秒） | 必填 |
| edesc | String | 事件描述信息 (JSON) | 必填; 限制 1000 字节 |

### 8.3 edesc 字段组成

`edesc` 是一个 JSON 字符串，由 **Common 字段** 和 **Desc_Schema 字段** 组合而成。

| 字段 | 类型 | 字节估算 | 说明 |
| --- | --- | --- | --- |
| tid | string | ~32 bytes | Trace ID。全链路追踪 ID。用于串联跨端/跨进程调用。 |
| pid | int | ~4 bytes | Process ID。结合 logcat/tombstone 时定位具体进程实例。 |
| proc | string | ~20 bytes | Process Name。明确是谁出的事（如 `com.map.app`）。 |
| ver | string | ~10 bytes | Version。应用/模块自身的版本号（如 `1.2.0`）。 |
| logf | string | ~20 bytes | Log Filename。大文件文件名（不含路径）；默认为空，手动设置。 |
| ... | ... | ... | 注册表 `Desc_Schema` 中定义的其他业务字段。 |