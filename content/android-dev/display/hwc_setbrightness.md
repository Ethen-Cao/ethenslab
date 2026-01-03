
### 亮度调节失败引发SurfaceFlinger合成策略选择失败的时序图

```plantuml
@startuml
!theme plain
' skinparam MaxMessageSize 300
skinparam participantPadding 10
skinparam boxPadding 10
skinparam defaultFontName Monospaced
autonumber "<b>[0]</b>"

title 亮度设置失败导致合成策略中止的全链路时序图

box "SurfaceFlinger 进程" #lightgreen
    participant "CompositionEngine" as CE
    participant "HWComposer" as SF_HWC
    participant "AidlComposer\n(HAL Client)" as Client
    participant "ComposerClientWriter" as Writer
end box

box "HWC Service 进程 (Guest OS)" #LightGray
    participant "AidlComposerClient\n(CommandEngine)" as Server
    participant "ConcurrencyMgr\n(SettingsIntf)" as CM
    participant "DisplayBuiltIn\n(SDM Logic)" as DBI
    participant "DPUMultiCore\n(Mux)" as Mux
    participant "HWPeripheralDRM\n(DAL)" as HW
end box

box "Kernel / FileSystem" #MistyRose
    participant "/sys/class/backlight" as Sysfs
end box

== 阶段 0: 指令积压 (Client Side Batching) ==
note right of CE: SurfaceFlinger 在之前的逻辑中\n调用了 setDisplayBrightness
CE -> SF_HWC: setDisplayBrightness(...)
SF_HWC -> Client: setDisplayBrightness(...)
Client -> Writer: 写入指令到 Command Queue
note right of Writer: 此时 Command Index 0 缓存了:\n1. OP: SetBrightness\n(尚未发送)

== 阶段 1: 触发策略选择 (Frame Start) ==
CE -> CE: **chooseCompositionStrategy()**
CE -> SF_HWC: getDeviceCompositionChanges()

SF_HWC -> SF_HWC: check canSkipValidate (True)
SF_HWC -> Client: presentOrValidateDisplay()

note right of Writer: 将 Validate 指令追加到 Command Queue (Index 0)\n现在 Index 0 包含: [SetBrightness, PresentOrValidate]

Client -> Server: **executeCommands()** (Binder IPC)
activate Server

== 阶段 2: 服务端执行 (The Root Cause) ==
Server -> Server: 解析 Command Queue\n初始化 mCommandIndex = 0

group #MistyRose HWC 服务端循环 [处理 Index 0]
    ' --- 步骤 A: 亮度设置 ---
    note right of Server: **步骤 A: 优先执行亮度设置**
    Server -> CM: SetDisplayBrightness(level)
    CM -> DBI: SetPanelBrightness(brightness)
    note right of DBI: 转换 float 为 int level
    DBI -> Mux: SetPanelBrightness(level)
    Mux -> HW: SetPanelBrightness(level)
    
    activate HW
    HW -> HW: 检查 enable_brightness_drm_prop
    note right of HW: 属性未开启(false)，走 Sysfs 路径
    
    HW -> Sysfs: open(".../panel0-backlight/brightness")
    Sysfs --> HW: <color:red>❌ 失败 (ENOENT / No such file)</color>
    note right of HW
        **故障点**: 虚拟化环境中 Guest OS
        看不到物理背光节点
    end note
    
    HW --> Mux: 返回 kErrorFileDescriptor
    deactivate HW
    
    Mux --> DBI: 返回 Error
    DBI --> CM: 返回 Error
    CM --> Server: 返回 Error (kErrorBadConfig)
    
    Server -> Server: writeError(Index=0, BadConfig)
    note right of Server: <font color=red><b>[Log 1] W SDM : executeSetDisplayBrightness...</b></font>\n记录错误，但**不中断**循环

    ' --- 步骤 B: 验证 ---
    note right of Server: **步骤 B: 执行合成验证**
    Server -> CM: CommitOrPrepare(...)
    activate CM
    CM --> Server: <font color=green>✅ 成功 (kErrorNone)</font>
    deactivate CM
    
    Server -> Server: setPresentOrValidateResult(Validated)
end

Server --> Client: 返回 Binder Status OK\n数据包包含:\n1. ErrorList: [{Index:0, Err:BadConfig}]\n2. ResultList: [{Index:0, Validated}]
deactivate Server

== 阶段 3: 客户端误判 (The Misjudgment) ==
Client -> Client: 解析返回数据

group 客户端判决逻辑 [AidlComposer::execute]
    Client -> Client: 检查 Index 0
    note right of Client
        **<color:red>致命误判逻辑</color>**:
        1. 发现 Index 0 有 Error (实际源自亮度)
        2. 发现 Index 0 包含 Validate 指令
        3. **判定: 整个 Validate 失败**
    end note
    Client --> SF_HWC: 返回 **Error::BAD_CONFIG**
end

== 阶段 4: 策略中止 (Abort) ==
SF_HWC -> SF_HWC: RETURN_IF_HWC_ERROR_FOR(...)
note right of SF_HWC: <font color=red><b>[Log 2] E HWComposer : getDeviceCompositionChanges... failed...</b></font>

SF_HWC --> CE: 返回 **UNKNOWN_ERROR** (-2147483648)

CE -> CE: if (result != NO_ERROR)
note right of CE: <font color=red><b>[Log 3] E CompositionEngine : chooseCompositionStrategy failed...</b></font>

CE -> CE: return false
note right of CE: **放弃当前帧合成**\n(SurfaceFlinger 丢弃这一帧)

@enduml

```

---

### 详细说明：为什么会失败

#### 1. 根本原因 (Root Cause)

故障发生在 **阶段 2** 的底层 `HWPeripheralDRM` 中。

* **背景**：Android 系统运行在 Hypervisor 之上（Guest OS）。
* **冲突**：物理屏幕的背光控制权在 Host OS（Linux/QNX）手中，Guest OS 的内核中没有加载物理 Panel 驱动，因此 `/sys/class/backlight/panel0-backlight` 节点根本不存在。
* **代码缺陷**：`HWPeripheralDRM::SetPanelBrightness` 代码逻辑是为 Native Android 设计的，它尝试打开这个不存在的文件，导致 `open` 失败，返回错误码。

#### 2. 连锁反应

1. **底层报错**：`HWPeripheralDRM` 返回错误。
2. **上层记录**：`AidlComposerClient` (Server) 捕获到亮度设置错误，将其记录在 `CommandResult` 中。
3. **客户端误判**：`AidlComposer` (Client) 收到结果后，发现同一批次指令（Index 0）中有错误。由于 AIDL 协议将多个指令打包在一个 Index 中，Client 无法区分错误是来自“亮度”还是“验证”。出于安全考虑，它认为既然有错，那“验证”结果不可信，于是向 SurfaceFlinger 报告“验证失败”。
4. **合成中止**：SurfaceFlinger 收到验证失败，认为无法继续合成，放弃当前帧。

### Log开关

```bash
adb root
adb shell setprop vendor.display.enable_verbose_log 1
adb shell stop vendor.qti.hardware.display.composer-service
adb shell start vendor.qti.hardware.display.composer-service
```

参考 `ConcurrencyMgr::Init`:

```cpp
  SDMDebugHandler::Get()->GetProperty(ENABLE_VERBOSE_LOG, &value);
  if (true) {
    SDMDebugHandler::DebugAll(value, value);
  }
```