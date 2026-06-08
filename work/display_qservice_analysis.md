# display.qservice 源码分析

## 概述

`display.qservice` 是 Qualcomm Snapdragon Display Manager (SDM) 在 AOSP16 中提供的 Binder 服务，运行于 Hardware Composer (HWC) 进程内。通过 `vndservice call display.qservice CODE [参数]` 可以直接与显示子系统交互，实现亮度控制、色彩模式切换、刷新率配置、面板特性设置等功能。

---

## 调用链

```
vndservice call display.qservice CODE [参数]
  │
  ├─ BnQService::onTransact()         [权限检查: AID_ROOT/AID_GRAPHICS/AID_SYSTEM 等]
  │   └─ QService::dispatch()         [转发 command + parcel 到 HWC 客户端]
  │       └─ QServiceBackend::notifyCallback()  [HWC 侧桥接，转换 Parcel 类型]
  │           └─ ConcurrencyMgr::NotifyCallback()  [委托给 services_]
  │               └─ SDMServices::notifyCallback()  [按命令码查表分发]
  │                   ├─ vnd_handlers_set_[]  → Set 类操作（无需返回值）
  │                   └─ vnd_handlers_get_[]  → Get 类操作（写入 output parcel）
```

---

## 关键源文件

### 1. Binder 接口定义层

| 文件 | 说明 |
|------|------|
| `vendor/hardware/qcom/display/libqservice/IQService.h` | 定义 `IQService` 接口，声明所有命令码（COMMAND_LIST 枚举，值 2-64）和相关枚举类型（Debug 标签、TUI 状态等） |
| `vendor/hardware/qcom/display/libqservice/IQService.cpp` | `BpQService`（代理端）和 `BnQService::onTransact()`（服务端）实现。onTransact 做权限校验，仅允许 AID_MEDIA/AID_GRAPHICS/AID_ROOT/AID_CAMERASERVER/AID_AUDIO/AID_SYSTEM/AID_MEDIA_CODEC |
| `vendor/hardware/qcom/display/libqservice/IQClient.cpp` | `IQClient`/`BpQClient`/`BnQClient` 实现，定义 `notifyCallback()` binder 调用 |
| `vendor/hardware/qcom/display/libqservice/QService.h` | `QService` 类声明，继承 `BnQService`，持有 `mClient`(IQClient) 和 `mHDMIClient`(IQHDMIClient) 引用 |
| `vendor/hardware/qcom/display/libqservice/QService.cpp` | `QService::dispatch()` 将命令和数据通过 `mClient->notifyCallback()` 转发给 HWC 客户端处理 |
| `vendor/hardware/qcom/display/libqservice/QServiceUtils.h` | 便捷封装函数：`screenRefresh()`、`toggleScreenUpdate()`、`setCameraLaunchStatus()`、`displayBWTransactionPending()` 等 |

### 2. HWC Composer 桥接层

| 文件 | 说明 |
|------|------|
| `vendor/hardware/qcom/display/composer/QServiceBackend.cpp` | `QServiceBackend::notifyCallback()` 将 Android Parcel 转换为 SDM 的 `HWCParcel`，调用 `sideband_->NotifyCallback()` |
| `vendor/hardware/qcom/display/composer/QServiceBackend.h` | `QServiceBackend` 类声明，继承 `qClient::IQClient` |

### 3. SDM 侧边带接口

| 文件 | 说明 |
|------|------|
| `vendor/vendor/qcom/opensource/display-intf/sdmclient/sdm_display_intf_sideband.h` | 定义 `SDMDisplaySideBandIntf` 纯虚接口，声明 `NotifyCallback()` 及所有侧边带操作 |
| `vendor/vendor/qcom/opensource/display-intf/sdmclient/sdm_compositor_sideband_cb_intf.h` | 定义 compositor 侧边带回调接口 |

### 4. SDM 实现层（核心）

| 文件 | 说明 |
|------|------|
| `vendor/vendor/qcom/opensource/display-core/sdmclient/concurrency_mgr.h` | `ConcurrencyMgr` 类声明，多重继承 `SDMDisplaySideBandIntf` 等 10+ 接口，是所有显示操作的调度中心 |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/concurrency_mgr.cpp` | `ConcurrencyMgr::NotifyCallback()` 实现 (`:1145`)，直接委托给 `services_->notifyCallback()` |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.h` | `SDMServices` 类声明，包含命令码枚举 (`:56-111`) 和两张处理器注册表 (`:322-379`) |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.cpp` | `SDMServices::notifyCallback()` 实现 (`:81-107`)，通过 `vnd_handlers_set_`/`vnd_handlers_get_` 两张 map 分发到具体处理函数 |

---

## 命令码定义来源

命令码在 **两个文件** 中同步定义（数值完全对应）：

- `vendor/hardware/qcom/display/libqservice/IQService.h:85-141` — Binder 接口层枚举
- `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.h:56-111` — SDM 实现层枚举

### 所有命令一览

#### 亮度相关

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 2 | `GET_PANEL_BRIGHTNESS` | `GetDisplayBrightness()` | sdm_services.h:57, :364 |
| 3 | `SET_PANEL_BRIGHTNESS` | `SetDisplayBrightness()` | sdm_services.h:58, :365 |
| 47 | `SET_PANEL_LUMINANCE` | `SetPanelLuminanceAttributes()` | sdm_services.h:94, :343 |
| 48 | `SET_BRIGHTNESS_SCALE` | `ProcessDisplayBrightnessScale()` | sdm_services.h:95, :346 |
| 54 | `SET_DIMMING_ENABLE` | `SetDimmingEnable()` | sdm_services.h:101, :373 |
| 55 | `SET_DIMMING_MIN_BL` | `SetDimmingMinBl()` | sdm_services.h:102, :374 |

#### 色彩/显示模式

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 24 | `QDCM_SVC_CMDS` | `QdcmCMDHandler()` | sdm_services.h:71, :358 |
| 34 | `SET_COLOR_MODE` | `SetColorModeOverride()` | sdm_services.h:81, :334 |
| 36 | `SET_COLOR_MODE_BY_ID` | `SetColorModeById()` | sdm_services.h:82, :337 |
| 39 | `SET_COLOR_MODE_WITH_RENDER_INTENT` | `SetColorModeWithRenderIntent()` | sdm_services.h:86, :335 |
| 45 | `SET_COLOR_MODE_FROM_CLIENT` | `SetColorModeFromClient()` | sdm_services.h:92, :344 |
| 49 | `SET_COLOR_SAMPLING_ENABLED` | `setColorSamplingEnabled()` | sdm_services.h:96, :339 |

#### 刷新率/同步

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 5 | `SCREEN_REFRESH` | `RefreshScreen()` | sdm_services.h:60, :324 |
| 18 | `CONFIGURE_DYN_REFRESH_RATE` | `ConfigureRefreshRate()` | sdm_services.h:66, :329 |
| 38 | `SET_QSYNC_MODE` | `SetQSyncMode()` | sdm_services.h:85, :338 |
| 46 | `SET_FRAME_TRIGGER_MODE` | `SetFrameTriggerMode()` | sdm_services.h:93, :345 |

#### Display 配置

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 25 | `SET_ACTIVE_CONFIG` | `SetActiveConfigIndex()` | sdm_services.h:72, :331 |
| 26 | `GET_ACTIVE_CONFIG` | `GetActiveConfigIndex()` | sdm_services.h:73, :361 |
| 27 | `GET_CONFIG_COUNT` | `GetConfigCount()` | sdm_services.h:74, :362 |
| 28 | `GET_DISPLAY_ATTRIBUTES_FOR_CONFIG` | `GetDisplayAttributesForConfig()` | sdm_services.h:75, :363 |
| 29 | `SET_DISPLAY_MODE` | `SetDisplayMode()` | sdm_services.h:76, :328 |

#### DSI 时钟

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 42 | `SET_DSI_CLK` | `SetDsiClk()` | sdm_services.h:89, :342 |
| 43 | `GET_DSI_CLK` | `GetDsiClk()` | sdm_services.h:90, :369 |
| 44 | `GET_SUPPORTED_DSI_CLK` | `GetSupportedDsiClk()` | sdm_services.h:91, :370 |

#### 面板特性

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 19 | `CONTROL_PARTIAL_UPDATE` | `ControlPartialUpdate()` | sdm_services.h:67, :360 |
| 60 | `SET_DEMURA_STATE` | `SetDemuraState()` | sdm_services.h:107, :376 |
| 61 | `SET_DEMURA_CONFIG` | `SetDemuraConfig()` | sdm_services.h:108, :377 |
| 62 | `SET_BPP_MODE` | `SetBppMode()` | sdm_services.h:109, :352 |
| 63 | `PERFORM_CAC_CONFIG` | `PerformCacConfig()` | sdm_services.h:110, :351 |
| 64 | `SET_PANEL_FEATURE_CONFIG` | `SetPanelFeatureConfig()` | sdm_services.h:111, :379 |

#### 电源管理

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 16 | `SET_IDLE_TIMEOUT` | `SetIdleTimeout()` | IQService.h:95, sdm_services.cpp:178 |
| 40 | `SET_IDLE_PC` | `SetIdlePC()` | sdm_services.h:87, :340 |
| 50 | `SET_VSYNC_STATE` | `SetVSyncState()` | sdm_services.h:97, :371 |

#### 多屏/外部显示

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 12 | `SET_SECONDARY_DISPLAY_STATUS` | `SetDisplayStatus()` | sdm_services.h:62, :356 |
| 52 | `GET_DISPLAY_PORT_ID` | `GetDisplayPortId()` | sdm_services.h:99, :378 |
| 33 | `SET_LAYER_MIXER_RESOLUTION` | `SetMixerResolution()` | sdm_services.h:80, :333 |

#### 安全/TUI/HDCP

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 31 | `MIN_HDCP_ENCRYPTION_LEVEL_CHANGED` | `MinHdcpEncryptionLevelChanged()` | sdm_services.h:78, :359 |
| 51 | `NOTIFY_TUI_TRANSITION` | `HandleTUITransition()` | sdm_services.h:98, :372 |

#### 调试/杂项

| 命令码 | 枚举名 | 处理函数 | 源文件行号 |
|--------|--------|----------|-----------|
| 15 | `DYNAMIC_DEBUG` | `DynamicDebug()` | IQService.h:94 |
| 20 | `TOGGLE_SCREEN_UPDATES` | `ToggleScreenUpdate()` | sdm_services.h:68, :357 |
| 21 | `SET_FRAME_DUMP_CONFIG` | `SetFrameDumpConfig()` | sdm_services.h:69, :326 |
| 30 | `SET_CAMERA_STATUS` | `SetCameraLaunchStatus()` | sdm_services.h:77, :332 |
| 32 | `GET_BW_TRANSACTION_STATUS` | `DisplayBWTransactionPending()` | sdm_services.h:79, :367 |
| 37 | `GET_COMPOSER_STATUS` | `GetComposerStatus()` | sdm_services.h:83, :368 |
| 53 | `SET_NOISE_PLUGIN_OVERRIDE` | `SetNoisePlugInOverride()` | sdm_services.h:100, :330 |
| 56 | `DUMP_CODE_COVERAGE` | `DumpCodeCoverage()` | sdm_services.h:103, :348 |
| 57 | `UPDATE_TRANSFER_TIME` | `UpdateTransferTime()` | sdm_services.h:104, :350 |
| 58 | `SET_JITTER_CONFIG` | `SetJitterConfig()` | sdm_services.h:105 |
| 59 | `RETRIEVE_DEMURATN_FILES` | `RetrieveDemuraTnFiles()` | sdm_services.h:106, :375 |

---

## 权限控制

定义在 `vendor/hardware/qcom/display/libqservice/IQService.cpp:92-101`：

```cpp
const bool permission = (callerUid == AID_MEDIA ||
        callerUid == AID_GRAPHICS ||
        callerUid == AID_ROOT ||
        callerUid == AID_CAMERASERVER ||
        callerUid == AID_AUDIO ||
        callerUid == AID_SYSTEM ||
        callerUid == AID_MEDIA_CODEC);
```

- `CONNECT_HWC_CLIENT`（命令码 4）：仅允许 `AID_GRAPHICS`
- `CONNECT_HDMI_CLIENT`（命令码 23）：仅允许 `AID_SYSTEM` / `AID_ROOT`
- 其他命令（COMMAND_LIST_START ~ COMMAND_LIST_END）：允许上述 7 个 UID 之一

---

## Debug 标签枚举

定义在 `vendor/hardware/qcom/display/libqservice/IQService.h:149-165`：

| 值 | 标签 | 含义 |
|----|------|------|
| 0 | `DEBUG_ALL` | 所有模块 |
| 1 | `DEBUG_MDPCOMP` | MDP 合成策略 |
| 2 | `DEBUG_VSYNC` | Vsync 调试 |
| 3 | `DEBUG_VD` | 虚拟显示 |
| 4 | `DEBUG_PIPE_LIFECYCLE` | Pipe 生命周期 |
| 5 | `DEBUG_DRIVER_CONFIG` | 驱动配置 |
| 6 | `DEBUG_ROTATOR` | 旋转器 |
| 7 | `DEBUG_QDCM` | QDCM 色彩管理 |
| 8 | `DEBUG_SCALAR` | 缩放器 |
| 9 | `DEBUG_CLIENT` | 客户端 |
| 10 | `DEBUG_DISPLAY` | 显示 |
| 11 | `DEBUG_IWE` | IWE |
| 12 | `DEBUG_WB_USAGE` | Writeback 使用 |

对应处理逻辑在 `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.cpp:109-168`。

---

## 使用示例

```bash
# 验证服务存在
vndservice check display.qservice

# 获取面板亮度
vndservice call display.qservice 2

# 设置面板亮度
vndservice call display.qservice 3 f 0.8

# 获取当前 display config index
vndservice call display.qservice 26

# 获取支持的 config 数量
vndservice call display.qservice 27

# 获取 composer 初始化状态
vndservice call display.qservice 37

# 设置色彩模式（需先查支持的 mode ID）
vndservice call display.qservice 34 i32 <mode_id>

# 设置 QSync 为 continuous 模式
vndservice call display.qservice 38 i32 1

# 设置 DSI 时钟（单位 Hz）
vndservice call display.qservice 42 i64 1200000000

# 获取当前 DSI 时钟
vndservice call display.qservice 43

# 获取支持的 DSI 时钟列表
vndservice call display.qservice 44

# 设置 BPP 模式（24 或 30）
vndservice call display.qservice 62 i32 30

# 开关 display dimming
vndservice call display.qservice 54 i32 1   # 启用
vndservice call display.qservice 54 i32 0   # 禁用

# 启用/禁用 Vsync
vndservice call display.qservice 50 i32 1   # 启用
vndservice call display.qservice 50 i32 0   # 禁用

# 通知摄像头状态
vndservice call display.qservice 30 i32 1   # 摄像头开启
vndservice call display.qservice 30 i32 0   # 摄像头关闭

# 启用/禁用 idle power collapse
vndservice call display.qservice 40 i32 1   # 启用
vndservice call display.qservice 40 i32 0   # 禁用

# 刷新屏幕
vndservice call display.qservice 5

# 开关局部刷新
vndservice call display.qservice 19 i32 1   # 启用
vndservice call display.qservice 19 i32 0   # 禁用

# 动态调试（例如开启 QDCM debug）
vndservice call display.qservice 15 i32 7 i32 1 i32 5
# 参数: type=7(DEBUG_QDCM), enable=1, verbose_level=5
```

---

## 架构图

```
┌─────────────────────────────────────────────────────┐
│ vndservice call display.qservice CODE ...            │
└──────────────────────┬──────────────────────────────┘
                       │ binder call
                       ▼
┌─────────────────────────────────────────────────────┐
│ BnQService::onTransact()                            │
│   - 权限检查 (UID)                                   │
│   - CHECK_INTERFACE(IQService)                       │
│   - 路由: CONNECT_HWC_CLIENT / CONNECT_HDMI_CLIENT   │
│           / COMMAND_LIST_START~END dispatch()        │
│ 文件: IQService.cpp:86-137                           │
└──────────────────────┬──────────────────────────────┘
                       │ dispatch()
                       ▼
┌─────────────────────────────────────────────────────┐
│ QService::dispatch()                                │
│   - 检查是否同进程 (sameProcess)                      │
│   - mClient->notifyCallback(command, parcel)         │
│ 文件: QService.cpp:62-78                             │
└──────────────────────┬──────────────────────────────┘
                       │ IQClient::notifyCallback()
                       ▼
┌─────────────────────────────────────────────────────┐
│ QServiceBackend::notifyCallback()                    │
│   - Android Parcel → HWCParcel (SDM Parcel)          │
│   - sideband_->NotifyCallback()                      │
│ 文件: QServiceBackend.cpp:43-62                      │
└──────────────────────┬──────────────────────────────┘
                       │ SDMDisplaySideBandIntf::NotifyCallback()
                       ▼
┌─────────────────────────────────────────────────────┐
│ ConcurrencyMgr::NotifyCallback()                     │
│   - services_->notifyCallback()                      │
│ 文件: concurrency_mgr.cpp:1145-1151                  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│ SDMServices::notifyCallback()                        │
│   - vnd_handlers_set_[command] → Set 类操作          │
│   - vnd_handlers_get_[command] → Get 类操作          │
│ 文件: sdm_services.cpp:81-107                        │
│ 注册: sdm_services.h:322-379                         │
└─────────────────────────────────────────────────────┘
```

---

## HWC Frame Dump

通过命令码 **21** (`SET_FRAME_DUMP_CONFIG`) 可以 dump HWC 合成前后的帧数据到文件。

### 命令格式

```
vndservice call display.qservice 21 i32 <frame_count> i32 <display_type_mask> i32 <layer_type_mask> \
    [i32 format] [i32 tap_point] [i32 cwb_flags] \
    [i32 roi_left] [i32 roi_top] [i32 roi_right] [i32 roi_bottom]
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `frame_count` | i32 | 是 | 要 dump 的帧数。设为 `0` 停止 dump |
| `display_type_mask` | i32 | 是 | 目标 display 的 bitmask。`1`=主屏, `2`=外接屏1, `4`=虚拟屏1, `8`=内置屏2, `16`=外接屏2, `32`=虚拟屏2 |
| `layer_type_mask` | i32 | 是 | dump 类型 bitmask。`1`=输入图层(合成前), `2`=输出帧(合成后CWB回读), `3`=两者 |
| `format` | i32 | 否 | 输出像素格式（HAL Pixel Format），默认 `RGB_888` (=1) |
| `tap_point` | i32 | 否 | CWB 输出 tap 点：`0`=LM (Layer Mixer), `1`=DSPP, `2`=Demura。仅 layer_type_mask 含 output 时有效 |
| `cwb_flags` | i32 | 否 | CWB 标志 bitmask：bit0=PU as CWB ROI, bit1=Avoid extra refresh |
| `roi_left` — `roi_bottom` | i32 | 否 | CWB ROI 区域，四个值需同时提供 |

### Display Type Mask 详细

来源：`vendor/vendor/qcom/opensource/display-core/sdm/include/core/sdm_types.h:587-601`

| Mask 值 | 对应 Display | 说明 |
|---------|-------------|------|
| `1` (1<<0) | `DISPLAY_PRIMARY` | 主屏 |
| `2` (1<<1) | `DISPLAY_EXTERNAL` | 外接屏 1 |
| `4` (1<<2) | `DISPLAY_VIRTUAL` | 虚拟屏 1 |
| `8` (1<<3) | `DISPLAY_BUILTIN_2` | 内置屏 2 |
| `16` (1<<4) | `DISPLAY_EXTERNAL_2` | 外接屏 2 |
| `32` (1<<5) | `DISPLAY_VIRTUAL_2` | 虚拟屏 2 |
| `64` (1<<6) | `DISPLAY_EXTERNAL_3` | 外接屏 3 |

`layer_type_mask` 来源：`vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_display.h:59-60`

| Mask 值 | 枚举名 | 说明 |
|---------|-------|------|
| `1` | `INPUT_LAYER_DUMP` | dump 输入图层（合成前的各 layer buffer） |
| `2` | `OUTPUT_LAYER_DUMP` | dump 输出帧（合成后的帧，通过 CWB 回读） |

### Dump 输出路径

来源：`vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_display.cpp:2057`

```
/data/vendor/display/frame_dump_disp_id_XX_YYYY-MM-DD_HH-MM-SS/
```

每个 dump session 在该目录下生成带时间戳的子目录。

### 使用示例

```bash
# Dump 主屏 1 帧的输入图层
vndservice call display.qservice 21 i32 1 i32 1 i32 1

# Dump 主屏 3 帧的输出帧（合成后结果），DSPP tap point
vndservice call display.qservice 21 i32 3 i32 1 i32 2 i32 1 i32 1

# Dump 主屏 5 帧，同时 dump 输入图层和输出帧
vndservice call display.qservice 21 i32 5 i32 1 i32 3

# Dump 外接屏 3 帧输入图层
vndservice call display.qservice 21 i32 3 i32 2 i32 1

# Dump 主屏 2 帧输出，指定 RGBA_8888 格式(2)，LM tap point(0)
vndservice call display.qservice 21 i32 2 i32 1 i32 2 i32 2 i32 0

# Dump 主屏 5 帧输出，带 ROI 区域 (0,0)-(1920,1080)
vndservice call display.qservice 21 i32 5 i32 1 i32 2 i32 1 i32 0 i32 0 i32 0 i32 0 i32 1920 i32 1080

# 停止 frame dump
vndservice call display.qservice 21 i32 0
```

### 关键源文件（Frame Dump）

| 文件 | 行号 | 说明 |
|------|------|------|
| `vendor/hardware/qcom/display/libqservice/IQService.h` | 99 | `SET_FRAME_DUMP_CONFIG = 21` 命令码定义 |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.h` | 69, 326 | 命令注册到 `vnd_handlers_set_` 映射表 |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.cpp` | 1259-1327 | `SetFrameDumpConfig()` 参数解析（parcel 读取） |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.cpp` | 1197-1257 | `ValidateFrameDumpConfig()` 参数校验（frame count 非零、display/layer mask 非零、CWB 可用性） |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_services.cpp` | 193-227 | 底层 `SetFrameDumpConfig()` 调用 SDMDisplay |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_display.cpp` | 1408-1424 | `SDMDisplay::SetFrameDumpConfig()` 存储配置（count, bit_mask_layer_type） |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_display.cpp` | 1426-1510 | CWB 输出帧 buffer 分配、mmap、SetReadbackBuffer |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_display.cpp` | 3833-3900 | `HandleFrameDump()` 实际帧数据写出到文件 |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_display.cpp` | 3396-3420 | `ReleaseFrameDumpResources()` — 释放 dump 资源（munmap、free buffer） |
| `vendor/vendor/qcom/opensource/display-core/sdmclient/sdm_display.h` | 59-60 | `INPUT_LAYER_DUMP` / `OUTPUT_LAYER_DUMP` 枚举 |
| `vendor/vendor/qcom/opensource/display-core/sdm/include/core/sdm_types.h` | 587-601 | `qdutilsDisplayType` 枚举（DISPLAY_PRIMARY 等） |

### Frame Dump 调用链

```
vndservice call display.qservice 21 i32 <count> i32 <disp_mask> i32 <layer_mask> [...]
  └─ SDMServices::SetFrameDumpConfig(input_parcel)         [sdm_services.cpp:1259]
       ├─ 读取 parcel: frame_dump_count, bit_mask_display_type, bit_mask_layer_type
       ├─ 可选参数: output_format, tap_point, cwb_flags, cwb_roi
       ├─ ValidateFrameDumpConfig()                         [sdm_services.cpp:1197]
       │    ├─ 校验 frame_count != 0, display_mask != 0, layer_mask != 0
       │    └─ 检查 CWB 可用性 (虚拟显示占用 WB 块数)
       └─ SetFrameDumpConfig(frame_dump_count, ...)         [sdm_services.cpp:193]
            └─ SDMDisplay::SetFrameDumpConfig(count, ...)   [sdm_display.cpp:1426]
                 ├─ 若 OUTPUT_LAYER_DUMP: 分配 buffer, mmap
                 └─ SetReadbackBuffer(handle, ..., kCWBClientFrameDump)
                      后续每帧 commit 后 HandleFrameDump() 写文件
```

---

## 实机验证

### 测试环境

| 项目 | 详情 |
|------|------|
| 设备 | SA8397 平台 (himalayas) |
| ADB | `adb -s d7df5883` |
| HWC 进程 | `vendor.qti.hardware.display.composer-service` (PID 1227) |
| 主屏 (Display 0) | DP, 5120×1600, "DP0S078151", HWC pacesetter |
| 副屏 (Display 1) | DP, 1920×480, "DP3S078152", HWC follower |
| 副屏 (Display 2) | DP, "DP3S178153", HWC follower |
| 虚拟屏 | 2 个 (CrystalNaviMapVirtualDisplay, CrystalRoadBigMapVirtualDisplay) |

### 前提确认

```bash
# 服务存在
adb -s d7df5883 shell "vndservice check display.qservice"
# → Service display.qservice: found

# Composer 已初始化
adb -s d7df5883 shell "vndservice call display.qservice 37"
# → Result: Parcel(00000001)  # true

# 主屏 config
adb -s d7df5883 shell "vndservice call display.qservice 27"
# → Result: Parcel(00000001)  # 1 个 config

adb -s d7df5883 shell "vndservice call display.qservice 26"
# → Result: Parcel(00000000)  # active config index = 0
```

### 测试步骤

每次测试采用 **before/after 计数法**（因台架时钟与 PC 不一致，`find -newer` 不可靠）：

```bash
# 1. 记录当前文件数
adb -s d7df5883 shell "find /data/vendor/display -name '*.raw' | wc -l"

# 2. 发送 frame dump 命令
adb -s d7df5883 shell "vndservice call display.qservice 21 i32 <count> i32 <mask> i32 <type>"

# 3. 触发屏幕刷新（让 HWC commit 周期执行 dump）
adb -s d7df5883 shell "vndservice call display.qservice 5"

# 4. 等待 2 秒
sleep 2

# 5. 再次检查文件数
adb -s d7df5883 shell "find /data/vendor/display -name '*.raw' | wc -l"
```

### 测试结果

#### Display 0 (主屏 5120×1600) — Input Layer Dump

| 命令 | frame_count | display_mask | layer_mask | 文件数变化 | 结果 |
|------|-------------|--------------|------------|-----------|------|
| `21 i32 3 i32 1 i32 1` | 3 | 1 (PRIMARY) | 1 (INPUT) | 61→67 | ✅ +6 (3帧 × ~2层) |

生成的文件示例（`/data/vendor/display/frame_dump_disp_id_00_pluggable/`）：

```
input_layer0_5120x1600_RGBA_8888_UBWC_frame2.raw     (32 MB)
input_layer1_3200x1632_RGBA_8888_UBWC_frame2.raw     (21 MB)
input_layer2_2560x112_RGBA_8888_UBWC_frame2.raw      (1.1 MB)
input_layer3_2560x112_RGBA_8888_UBWC_frame2.raw      (1.1 MB)
input_layer4_2560x144_RGBA_8888_UBWC_frame2.raw      (1.4 MB)
input_layer5_2560x144_RGBA_8888_UBWC_frame2.raw      (1.4 MB)
input_layer6_2624x1600_RGBA_8888_UBWC_frame2.raw     (16 MB)
input_layer7_5120x1600_A8_frame2.raw                 (8.2 MB)
input_layer8_5120x1600_RGBA_8888_UBWC_frame2.raw     (32 MB)
```

#### Display 1 (副屏 1920×480) — Input Layer Dump

| 命令 | frame_count | display_mask | layer_mask | 文件数变化 | 结果 |
|------|-------------|--------------|------------|-----------|------|
| `21 i32 2 i32 2 i32 1` | 2 | 2 (EXTERNAL) | 1 (INPUT) | 67→75 | ✅ +8 (2帧 × 4层) |

#### Output Layer Dump

| 命令 | frame_count | display_mask | layer_mask | 文件数变化 | 结果 |
|------|-------------|--------------|------------|-----------|------|
| `21 i32 2 i32 1 i32 3` | 2 | 1 (PRIMARY) | 3 (IN+OUT) | 67→67 | ⚠️ 未生成 |

Output dump 需要空闲的 CWB (Concurrent WriteBack) 硬件块。当有虚拟屏在运行时，WB 块被占用，`ValidateFrameDumpConfig()` 校验失败静默返回。

#### 其他已验证的命令

以下命令也通过 binder 层正常路由，返回符合预期（Set 类返回 NULL，Get 类返回数据）：

| 命令码 | 命令 | 测试参数 | 返回值 |
|--------|------|---------|--------|
| 25 | `SET_ACTIVE_CONFIG` | `i32 0 i32 0` | Parcel(NULL) ✅ |
| 40 | `SET_IDLE_PC` | `i32 0` | Parcel(NULL) ✅ |
| 45 | `SET_COLOR_MODE_FROM_CLIENT` | `i32 0 i32 2` | Parcel(NULL) ✅ |
| 50 | `SET_VSYNC_STATE` | `i32 0 i32 1` | Parcel(NULL) ✅ |
| 54 | `SET_DIMMING_ENABLE` | `i32 0 i32 1` | Parcel(NULL) ✅ |
| 63 | `PERFORM_CAC_CONFIG` | `i32 0 i32 0 i32 0` | Parcel(NULL) ✅ |

### 注意事项

1. **台架时钟偏差**：设备时钟可能与 PC 不一致，不要依赖 `find -newer` 或文件时间戳做增量检测，用文件计数法（before/after `wc -l`）更可靠
2. **Output dump 依赖 CWB**：`OUTPUT_LAYER_DUMP` 需要 Concurrent WriteBack 硬件块空闲，在虚拟屏运行时可能不可用。推荐日常调试仅用 `INPUT_LAYER_DUMP`
3. **需触发 commit**：设置 dump 配置后，HWC 不会立即 dump，需等待下一次帧提交。可以通过触摸屏幕或 `SCREEN_REFRESH` (命令 5) 触发
4. **权限**：所有 `display.qservice` 调用需要 root 权限（`adb root`）
5. **文件命名**：格式为 `input_layer<N>_<width>x<height>_<format>_<compression>_frame<M>.raw`，UBWC 表示带压缩，A8 表示 alpha-only 图层
