+++
date = '2026-08-01T00:00:00+08:00'
draft = false
title = 'QNX OpenWFD OEM Secure Port 安全日志分析'
+++

## 问题背景

QNX 系统中出现如下 WARNING 日志：

```
[22][wfdBindSourceToPipeline:3302] DISPLAY_WARNING The source is secure, but the port 4 is not secure.The content is blocked
```

该日志表明：某个 WFD 客户端尝试将**安全源（secure source）**绑定到一个
`eDisplayID=4` 的有效 port，但该 port 当时的 `bOEMSecure` 为 `WFD_FALSE`。
OpenWFD 因而将本次 source 改成无效句柄，使 pipeline 不再接收该安全内容。

这里的 `port 4` 是日志参数 `pPort->eDisplayID`，不是 XML 中客户端私有的
`<WFDPort ID='4'>`。单凭这条日志也无法确定具体客户端和本地 WFDPort ID。

---

## 一、日志打印模块定位

### 1.1 日志来源

| 项目 | 详情 |
|------|------|
| **模块** | OpenWFD (`MDSS_MODULE_SW_WFD`) |
| **源文件** | `AMSS/multimedia/display/Hoya/openwfd/src/pipeline.c` |
| **函数** | `wfdBindSourceToPipeline` (定义于第 3178 行) |
| **打印行号** | 第 3300–3302 行 |

模块声明在 `pipeline.c:30`：

```c
DISP_OSAL_DEBUG_MODULE(WFD);  // → gDispOsalDebugModuleId = MDSS_MODULE_SW_WFD
```

### 1.2 日志格式解析

```
[22][wfdBindSourceToPipeline:3302] DISPLAY_WARNING The source is secure, but the port 4 is not secure.The content is blocked
 │    │                       │         │
 │    │                       │         └── 日志消息正文
 │    │                       └── 日志级别标签 (来自 DISP_OSAL_LOG_WARNING 宏)
 │    └── 函数名 : 行号
 └── 线程 ID（pthread_self()）
```

`DISP_OSAL_LOG_WARNING` 定义在 `openwfd/inc/wfd_osal.h:508-509`：

```c
#define DISP_OSAL_LOG_WARNING(fmt, ...) \
  MDSS_LOG_MESSAGE(gDispOsalDebugModuleId, MDSS_LOG_WARNING_INFO_TYPE, " DISPLAY_WARNING " fmt, ##__VA_ARGS__)
```

最终 SLOG2 前缀来自 `mdss_log_manager.h:264-265`：

```c
#define MDSS_Log(eModuleId, eLogType, eSeverity, pLogString, ...) \
  MDSS_Log_Manager_Log_Print(eModuleId, eLogType, eSeverity, \
      "[%d][%s:%d]" pLogString, pthread_self(), __FUNCTION__, __LINE__, ##__VA_ARGS__)
```

因此 `[22]` 是线程 ID，不是 MDSS 模块 ID。该日志属于 OpenWFD，是由
`pipeline.c` 中的 `DISP_OSAL_DEBUG_MODULE(WFD)` 确定的；模块 ID 作为独立参数
传给日志管理器，并未显示在这段前缀中。本源码的 `MDSS_MODULE_SW_WFD` 枚举值为 19，
也不是 22。

### 1.3 安全校验逻辑

`pipeline.c:3287-3303`：

```c
if(pSource->bSecure)                               // ① source 是安全内容
{
    if(WFD_INVALID_HANDLE != pPipeline->hPort)
    {
        pPort = (WFD_PortType *)(pPipeline->hPort);
        WFD_VALIDATE_PORT(pPort, eError);
        if(WFD_ERROR_NONE == eError)
        {
            if (!(pPort->bOEMSecure))              // ② port 的 OEM 安全标志未开启
            {
                source        = WFD_INVALID_HANDLE; // ③ 将 source 置为无效
                hServerSource = WFD_INVALID_HANDLE;
                pSource       = WFD_INVALID_HANDLE;
                DISP_OSAL_LOG_WARNING("The source is secure, but the port %d is "
                                      "not secure.The content is blocked",
                                      pPort->eDisplayID);
            }
        }
    }
}
```

`pSource->bSecure` 在 source 创建时由 `WFD_SOURCE_TRANSLATION_SECURED` 设置。
上述分支不会直接设置新的 WFD error，而是将客户端和服务端 source 句柄清零；
后续校验将其按 NULL source 处理。因此更精确的描述是：
**安全 source + 有效 port 的 `bOEMSecure==FALSE` → 清空本次 source 绑定并打印 WARNING**。

---

## 二、配置链路

### 2.1 端口安全策略的三层架构

```
┌──────────────────────────────────────────────────────────────┐
│ TEE 侧 (TrustZone)                                            │
│   ops_au_oem_config.xml                                       │
│     构建时编入 DevCfg，定义 DSI/DP/eDP 的 OPS 输出类型          │
│     OPS 根据配置及运行时输出保护状态形成通知/状态               │
├──────────────────────────────────────────────────────────────┤
│ HLOS 侧 (QNX) — qseecom_daemon::ops_service（预编译）          │
│   接收 OPS 命令，将物理显示端口状态翻译成 OpenWFD 位掩码        │
│   以内部客户端 0x7901 创建 WFD device                         │
│   调用 wfdSetDeviceAttribi(device,                            │
│         WFD_DEVICE_OEM_SECURE, iValue)                        │
├──────────────────────────────────────────────────────────────┤
│ HLOS 侧 (QNX) — OpenWFD                                      │
│   device.c         → 鉴权（必须是 WFD_CLIENT_TYPE_OPS）        │
│   wfd_clientmgr.c  → 按 iValue 位掩码设置已有 port 的           │
│                       bOEMSecure                              │
│   pipeline.c       → 安全源绑定时校验 bOEMSecure               │
└──────────────────────────────────────────────────────────────┘
```

HLOS 侧不直接解析 `ops_au_oem_config.xml`。当前源码树没有
`ops_service.c` 源码，但安装镜像中的 `qseecom_daemon` 包含
`ops_service.c`、`/ifs/lib64/libopenwfd.so`、`wfdSetDeviceAttribi` 和
`update_display_with_oem_config` 等字符串，可用于确认上述二进制调用链。

### 2.2 关键代码文件

| 文件 | 行号 | 作用 |
|------|:----:|------|
| `openwfd/src/pipeline.c` | 3287–3303 | 安全源绑定校验，打印 WARNING |
| `openwfd/src/wfd_clientmgr.c` | 3247–3368 | `WFD_ClientMgr_SetOEMSecure()`: 遍历 port, 按位掩码设 bOEMSecure |
| `openwfd/src/wfd_clientmgr.c` | 39 | `WFD_PORT_IS_OEM_SECURE(value, offset)` 位提取宏 |
| `openwfd/src/device.c` | 1557–1657 | `wfdSetDeviceAttribi()` 入口及 OPS 鉴权 |
| `openwfd/src/source.c` | 718–757 | 根据 translation mode 设置 `pSource->bSecure` |
| `openwfd/src/port.c` | 1001 | `bOEMSecure` 默认初始化为 `WFD_FALSE` |
| `openwfd/inc/wfd_resource.h` | 510 | `WFD_PortType.bOEMSecure` 字段定义 |
| `openwfd/src/wfd_catalog.c` | 1683–1693 | 创建内部 OPS 客户端 `0x7901` |
| `common/shim_utility/protected/mdss_log_manager.h` | 260–265 | SLOG2 日志前缀格式 |

---

## 三、HBEZ 的 Display 配置

### 3.1 WFDConfig: Port → QDI Display ID 映射

配置文件：`boards/display/adp_star_sda8295/config/qcdisplaycfg_HBEZ.xml`

`WFDClient ID='0x78FF'`、`eWFDClientType='0x1'` 是 **Cluster 客户端**，
不是 OPS 客户端。`WFDClientType` 枚举中 `0x1` 对应
`WFD_CLIENT_TYPE_CLUSTER`，`WFD_CLIENT_TYPE_OPS` 的值为 `0x8`。

OpenWFD 在读取 XML 客户端后，会另外追加内部 OPS 客户端：

```text
WFDClient ID = 0x7901
WFDClientType = WFD_CLIENT_TYPE_OPS (8)
iNumOfPorts = 0
```

虽然内部 OPS 客户端没有自己的 port 列表，但 Client Manager 仍为它提供一个
WFD device；通过鉴权后，`WFD_ClientMgr_SetOEMSecure()` 会遍历服务端已经创建的 port。

下面是 XML 中 **Cluster 客户端 0x78FF** 的资源映射：

| WFDPort<br>ID | eQDIDisplayID | QDI 枚举 | 全局接口 / DPU 局部接口 | XML 注释中的功能 |
|:---:|:---:|---|------|---|
| 1 | **1** | PRIMARY | DSI0, MDSS_0 | CLUSTER (仪表) |
| 2 | **3** | THIRD | DP2 / MDSS_1 局部 DP0 | IVI touch (中控触摸) |
| **3** | **4** | **EXTERNAL** | **DP2 / MDSS_1 局部 DP0 (MST)** | **PASSENGER touch (副驾触摸)** |
| 4 | **8** | EXTERNAL4 | eDP0 / MDSS_0 局部 DP2 | CEILING touch (后排顶棚触摸) |
| 5 | **3** | THIRD | DP2 / MDSS_1 局部 DP0 | IVI fflush |
| **6** | **4** | **EXTERNAL** | **DP2 / MDSS_1 局部 DP0 (MST)** | **PASSENGER fflush** |
| 7 | **8** | EXTERNAL4 | eDP0 / MDSS_0 局部 DP2 | CEILING fflush |
| 8 | **2** | SECONDARY | DSI1, MDSS_0 | HUD fflush |
| 9 | **1** | PRIMARY | DSI0, MDSS_0 | CLUSTER fflush |

> **编号说明：** `<WFDConfig>` 注释采用 SoC 全局接口编号，例如
> `DP2 dpu1`；PanelLibrary 名称采用对应 DPU 内的局部控制器编号，例如
> `DP0_COMMON_QC`。因此本文写成“DP2 / MDSS_1 局部 DP0”，避免在 OPS 配置中
> 误查成 `ops_DP_0_*`。

### 3.2 Display 段（物理面板与 QDI Display ID 的对应）

`qcdisplaycfg_HBEZ.xml` 中 `<Display>` 段定义了各 QDI display ID 对应的物理面板：

| Display ID | MDSS 设备 | 面板驱动 | 全局接口 / DPU 局部接口 | HBEZ 对应屏幕 |
|:---:|:---:|---|---|---|
| 1 | 0 | `DSI_COMMON_QC_0` | DSI0 | CLUSTER |
| 2 | 0 | `DSI_COMMON_QC_1` | DSI1 | HUD |
| 3 | 1 | `DP0_COMMON_QC` | DP2 / 局部 DP0 | IVI |
| 4 | 1 | `DP0_COMMON_MST_QC` | DP2 / 局部 DP0 (MST) | PASSENGER |
| 8 | 0 | `DP2_COMMON_QC` | eDP0 / 局部 DP2 | CEILING |

> 日志中的 **"port 4"** 是 `QDI_DISPLAY_EXTERNAL = 4`，对应
> **PASSENGER 副驾屏**（SoC 全局 DP2、MDSS_1 局部 DP0 的 MST 显示）。
> 它不是上表中的 WFDPort ID 4；同一个 `eQDIDisplayID` 还可能出现在其他
> WFDClient 的资源映射中，所以该日志不能单独识别调用者。

### 3.3 Port Type 说明

WFD PortAttribs 中的 `ePortType` 不是物理接口类型，而是 **WFD 协议层对外暴露的端口类型**：

| ePortType 值 | WFD 宏 | 含义 |
|:---:|---|---|
| 0x7660 | `WFD_PORT_TYPE_INTERNAL` | 内部端口 |
| 0x7668 | `WFD_PORT_TYPE_DISPLAYPORT` | DisplayPort 类型 |
| 0x766A | `WFD_PORT_TYPE_DSI` | DSI 类型 |

该字段用于 WFD 客户端接口，不直接影响 OEM Secure 策略。

---

## 四、bOEMSecure 的位掩码映射

### 4.1 QDI Display ID 枚举

定义于 `qdi_types.h:493-503`：

```c
QDI_DISPLAY_NONE      = 0,
QDI_DISPLAY_PRIMARY   = 1,
QDI_DISPLAY_SECONDARY = 2,
QDI_DISPLAY_THIRD     = 3,
QDI_DISPLAY_EXTERNAL  = 4,
QDI_DISPLAY_EXTERNAL2 = 5,
QDI_DISPLAY_EXTERNAL3 = 6,
QDI_DISPLAY_FRAMEBUFFER = 7,
QDI_DISPLAY_EXTERNAL4 = 8,
QDI_DISPLAY_EXTERNAL5 = 9,
QDI_DISPLAY_EXTERNAL6 = 10,
```

### 4.2 位提取宏

`wfd_clientmgr.c:39`：

```c
#define WFD_PORT_IS_OEM_SECURE(value, offset) \
    (WFDboolean)(((value & (1 << offset)) >> offset))
```

该宏从 OPS Client 传入的 `iValue` 中提取指定位。

### 4.3 ⚠️ 关键: eDisplayID → bit offset 的版本映射

`WFD_ClientMgr_SetOEMSecure()` 根据 `eDeviceVersion` 走两种不同映射。代码在 `wfd_clientmgr.c:3281-3359`。

`mdp_main.c:343-355` 明确给出了平台对应关系：

- Makena、MDP 8.0.0 → `QDI_DEVICE_VERSION_11_99`
- Lemans、MDP 8.4.0 → `QDI_DEVICE_VERSION_11_99_A`

HBEZ 使用 SA8295/Makena 配置，因此实际应分析
`QDI_DEVICE_VERSION_11_99` 分支；`11_99_A` 仅作为其他平台的对照。

**HBEZ/Makena: `QDI_DEVICE_VERSION_11_99`** (`wfd_clientmgr.c:3283-3322`)

| eDisplayID | 实际检查的 bit | 备注 |
|:---:|:---:|---|
| 1 (PRIMARY) | **bit 1** | 直查自身 |
| 2 (SECONDARY) | **bit 2** | 直查自身 |
| 3 (THIRD) | **bit 3** | 直查自身 |
| **4 (EXTERNAL)** | **bit 3 (THIRD)** ⚠️ | **重映射! 不查 bit 4** |
| 5 (EXTERNAL2) | **bit 5** | 直查自身 |
| 6 (EXTERNAL3) | **bit 5 (EXTERNAL2)** ⚠️ | **重映射! 不查 bit 6** |
| 8 (EXTERNAL4) | **bit 8** | 直查自身 |
| 9 (EXTERNAL5) | **bit 8 (EXTERNAL4)** ⚠️ | **重映射! 不查 bit 9** |
| 10 (EXTERNAL6) | **bit 10** | 直查自身 |

**Lemans 对照: `QDI_DEVICE_VERSION_11_99_A`** (`wfd_clientmgr.c:3323-3359`)

| eDisplayID | 实际检查的 bit | 备注 |
|:---:|:---:|---|
| 1 (PRIMARY) | **bit 1** | 直查自身 |
| 2 (SECONDARY) | **bit 2** | 直查自身 |
| 3 (THIRD) | **bit 3** | 直查自身 |
| **4 (EXTERNAL)** | **bit 3 (THIRD)** ⚠️ | **重映射!** |
| **5 (EXTERNAL2)** | **bit 3 (THIRD)** ⚠️ | **重映射! 与 A 不同!** |
| **6 (EXTERNAL3)** | **bit 3 (THIRD)** ⚠️ | **重映射! 与 A 不同!** |
| 8 (EXTERNAL4) | **bit 8** | 直查自身 |
| 9 (EXTERNAL5) | **bit 6 (EXTERNAL3)** ⚠️ | **重映射! 与 A 不同!** |

### 4.4 核心结论

HBEZ 的 `QDI_DISPLAY_EXTERNAL`（日志中的 port 4）由 `iValue` 的
bit 3（`QDI_DISPLAY_THIRD`）控制，而非 bit 4。对照的 `11_99_A`
分支在这一点上也相同。

```
iValue  bit map:
  bit 0   bit 1    bit 2    bit 3         bit 4    bit 5    bit 6    bit 7   bit 8
  (N/A)   PRIMARY  SECOND   THIRD         (N/A)    EXT2     EXT3     (N/A)   EXT4
                              ↑
                            控制 port 4 (QDI_DISPLAY_EXTERNAL)
```

HBEZ 五个屏对应的 bit：

| 屏幕 | eDisplayID | 需要的 iValue bit |
|---|---|---|
| CLUSTER 仪表 | 1 (PRIMARY) | **bit 1** |
| HUD | 2 (SECONDARY) | **bit 2** |
| IVI 中控 | 3 (THIRD) | **bit 3** |
| **PASSENGER 副驾** | **4 (EXTERNAL)** | **bit 3** (与 IVI 共用!) |
| CEILING 后排顶棚 | 8 (EXTERNAL4) | **bit 8** |

> 注意：在当前 OpenWFD 映射层，IVI（THIRD）和 PASSENGER（EXTERNAL）
> **共用 bit 3**，不能通过这个 `iValue` 位掩码把两者设置为不同的
> `bOEMSecure` 状态。

---

## 五、根因分析

### 5.1 这条日志能够直接证明什么

`bOEMSecure` 在 port 创建时默认为 `WFD_FALSE`（`port.c:1001`）。
只有通过 OPS 类型鉴权的客户端调用：

```c
wfdSetDeviceAttribi(device, WFD_DEVICE_OEM_SECURE, iValue);
```

才会进入 `WFD_ClientMgr_SetOEMSecure()`，按位更新当时已经创建的服务端 port。

因此该 WARNING 能够直接证明的只有：

1. 本次 source 的 `bSecure` 为 `WFD_TRUE`；
2. pipeline 已经绑定了有效 port，且该 port 的 `eDisplayID` 为 4；
3. 校验发生时，该 port 的 `bOEMSecure` 为 `WFD_FALSE`；
4. OpenWFD 将本次 source 替换为无效/NULL source，从而阻止安全内容输出。

它**不能单独证明** OPS 从未调用 API、传入值的 bit 3 一定为 0，
也不能直接认定故障位于 TZ → HLOS 桥接层。

### 5.2 可能原因

| 原因 | 源码层面的解释 |
|---|---|
| **qseecom_daemon/OPS 服务没有完成更新** | OPS 命令未收到、服务未启动、动态加载 OpenWFD 失败，或调用链在到达 setter 前失败 |
| **iValue 的 bit 3 为 0** | 在 HBEZ `11_99` 映射中，display 4 读取 bit 3；判断式为 `(iValue & 0x8) != 0` |
| **OPS 类型鉴权失败** | `device.c` 只接受 `WFD_CLIENT_TYPE_OPS`；XML 中的 `0x78FF/type 1` 无权设置该属性 |
| **QDI device 信息获取失败** | `QDI_Device_GetInfo()` 失败时不会进入版本映射，已有 port 保持原状态 |
| **设备版本不受支持** | 非 `QDI_DEVICE_VERSION_11_99/11_99_A` 会落入 `bad soc id` 分支，不更新 port |
| **更新时序早于 port 创建** | setter 只更新当时非 NULL 的 `hWfdPort`；若日志中出现 `server port not found`，后来创建的 port 仍从 `WFD_FALSE` 开始 |
| **物理端口映射或运行时保护状态异常** | HBEZ 的 IVI/PASSENGER 是 SoC 全局 DP2；需核对 `ops_DP_2_*`、OPS 上报值及 HDCP/链路状态 |

“PASSENGER 未连接，所以 port 未创建”不能直接解释这条 WARNING：
告警打印前 `pPipeline->hPort` 已非空且 `WFD_VALIDATE_PORT()` 已通过。
如果更新发生在 port 创建之前，应归类为初始化时序问题，而不是告警发生时 port 不存在。

另有一个值得注意的错误传播问题：`WFD_ClientMgr_SetOEMSecure()` 在
`QDI_Device_GetInfo()` 失败时设置的是 `eError`，但函数末尾返回的是锁操作状态
`eStatus`。默认的 `bad soc id` 分支也只打印日志。因此上层可能观察到调用完成，
而 port 实际没有被更新，排查时不能只依赖 API 返回状态。

### 5.3 TZ 侧静态配置的含义

文件：`tz/.../qsee/mink/oem/config/makena/ops_au_oem_config.xml`

当前所有 `ops_DP_*_type` 和 `ops_eDP_*_type` 都是 `0x0`，其注释定义为
`Secure_output_external`。这表示接口被配置为可承载安全视频的外部输出，
但同一注释同时说明显示保护级别取决于 **HDCP negotiation**。

对于 IVI/PASSENGER 所在的 SoC 全局 DP2，静态值为：

```text
ops_DP_2_type           = 0x0  (Secure_output_external)
ops_DP_2_security_level = 0x0  (HDCP_NONE)
```

此外，HBEZ 的 display 3 和 display 4 都配置了 `bSkipHDCP='1'`。
这些静态值不能直接推出运行时送到 OpenWFD 的 bit 3 必然为 1；仍需检查
TZ/OPS 的实际状态、通知内容和 HLOS 更新时序。因此不能仅凭当前 XML 将问题
定位为预编译桥接二进制故障。

### 5.4 建议排查顺序

1. 检查 `qseecom_daemon` 是否运行，并搜索其 OPS 路径日志：

   ```text
   OPS Received command id =
   update_display_with_oem_config
   wfdSetDeviceAttribi failed
   ```

2. 在 OpenWFD 日志中搜索 setter 入口，确认是否收到更新及其时间顺序：

   ```text
   WFD_ClientMgr_SetOEMSecure with iValue=
   ```

3. 对 HBEZ 检查 `(iValue & 0x8) != 0`。bit 3 为 1 是 display 4 被设为
   `bOEMSecure=TRUE` 的必要条件，但还要求 setter 成功并且对应 port 已创建。

4. 搜索每个 port 的更新结果：

   ```text
   eDisplayID=4 bOEMSecure=
   ```

5. 同时搜索容易被返回值掩盖的内部错误：

   ```text
   QDI_Device_GetInfo
   bad soc id
   server port not found
   is not authorized for this query
   ```

6. 对照 port 创建日志和 setter 日志的时间，确认 OPS 更新是否早于
   display 4 的 `wfdCreatePort()`。

7. 在 TZ/OPS 侧核对 SoC 全局 `DP2` 的运行时状态，而不是只按
   `DP0_COMMON_*` 面板库名称检查 `ops_DP_0_*`。

---

## 六、相关文件索引

| 文件路径 | 说明 |
|---|---|
| `AMSS/multimedia/display/Hoya/openwfd/src/pipeline.c` | 安全校验，打印 WARNING (L3287-3303) |
| `AMSS/multimedia/display/Hoya/openwfd/src/wfd_clientmgr.c` | 位掩码设置 bOEMSecure (L3247-3368) |
| `AMSS/multimedia/display/Hoya/openwfd/src/device.c` | `wfdSetDeviceAttribi()` 与 OPS 鉴权 (L1557-1657) |
| `AMSS/multimedia/display/Hoya/openwfd/src/source.c` | secure source 标志来源 (L718-757) |
| `AMSS/multimedia/display/Hoya/openwfd/src/port.c` | bOEMSecure 初始化为 FALSE (L1001) |
| `AMSS/multimedia/display/Hoya/openwfd/src/wfd_catalog.c` | 内部 OPS 客户端 0x7901 (L1683-1693) |
| `AMSS/multimedia/display/Hoya/openwfd/inc/wfd_osal.h` | DISP_OSAL_LOG_WARNING 宏 (L508-509) |
| `AMSS/multimedia/display/Hoya/openwfd/inc/wfd_resource.h` | WFD_PortType 结构体 (L510) |
| `AMSS/multimedia/display/common/shim_utility/protected/mdss_log_manager.h` | 日志线程 ID 前缀 (L260-265) |
| `AMSS/multimedia/display/common/qdi_shim/public/.../qdi_types.h` | QDI Display ID 枚举 (L493-503) |
| `AMSS/multimedia/display/Hoya/qdidriver/source/coredriver/mdp/mdp_main.c` | Makena/Lemans 的 QDI device version 映射 (L343-355) |
| `boards/display/adp_star_sda8295/config/qcdisplaycfg_HBEZ.xml` | **HBEZ OpenWFD Display 配置** |
| `boards/display/adp_star_sda8295/config/graphics_HBEZ.conf` | HBEZ QNX Screen 配置 |
| `tz/.../qsee/mink/oem/config/makena/ops_au_oem_config.xml` | **TZ OPS 安全策略配置** |
| `install/usr/include/WF/wfdext2.h` | WFD client type 与 WFD_DEVICE_OEM_SECURE 定义 |
| `install/usr/include/WF/wfd.h` | WFD API 与 port type 枚举定义 |
| `install/aarch64le/bin/qseecom_daemon` | 包含预编译的 HLOS OPS service |
