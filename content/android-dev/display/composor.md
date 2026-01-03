HWC 服务启动到底层 Display 对象创建完成的完整时序,这个过程主要分为三个阶段：

1. **服务启动与依赖注入**：`service.cpp` 启动进程，创建 AIDL 服务实体。
2. **SDM 环境初始化**：`ConcurrencyMgr` 初始化，加载 Core 层和硬件信息。
3. **Display 对象构建**：`DisplayBuilder` 根据硬件信息创建具体的 `DisplayBuiltIn` 和 `HWPeripheralDRM`。

### Qualcomm HWC 启动与 Display 创建全流程

```plantuml
@startuml
!theme plain
skinparam MaxMessageSize 200
skinparam participantPadding 10
skinparam boxPadding 10
skinparam defaultFontName Monospaced
autonumber "<b>[Boot-0]</b>"

title HWC Service Startup & Display Creation Sequence (Final Fix)

box "Service Process Entry" #White
    participant "Main (service.cpp)" as Main
    participant "AidlComposer\n(BnComposer)" as AC
end box

box "SDM Client Layer" #LightYellow
    participant "SDMInterfaceFactory" as Factory
    participant "ConcurrencyMgr" as CM
    participant "SDMDisplayBuilder" as Builder
end box

box "SDM Core Layer" #LightGreen
    participant "CoreInterface" as CoreStatic
    participant "CoreImpl" as Core
    participant "DisplayBuiltIn" as DBI
    participant "DPUMultiCore\n(Mux)" as Mux
end box

box "Device Abstraction Layer (DAL)" #LightGray
    participant "HWInfoInterface" as HWInfo
    participant "HWInterface\n(Factory)" as HWFactory
    participant "HWPeripheralDRM" as HW
end box

== 阶段 1: 服务启动与接口绑定 ==
Main -> Main: setpriority / sched_setscheduler
create AC
Main -> AC: **new AidlComposer()**
activate AC

    ' 1.1 创建核心管理对象 ConcurrencyMgr
    AC -> Factory: CreateLifeCycleIntf() / CreateSettingsIntf() ...
    activate Factory
    Factory -> CM: **GetInstance()** (Singleton)
    activate CM
    CM --> Factory: instance
    deactivate CM
    Factory --> AC: shared_ptr<ConcurrencyMgr>
    deactivate Factory

    ' 1.2 初始化 ConcurrencyMgr
    AC -> CM: **Init(buffer_allocator, ...)**
    activate CM

== 阶段 2: SDM 核心环境初始化 ==
        CM -> CM: InitSubModules()
        
        ' 2.1 创建 CoreImpl
        CM -> CoreStatic: **CreateCore(...)**
        activate CoreStatic
        create Core
        CoreStatic -> Core: new CoreImpl(...)
        Core -> Core: Init()
        
        ' 2.2 加载硬件信息 (DRM Capability)
        Core -> HWInfo: Create(&hw_info_intf)
        activate HWInfo
        HWInfo -> HWInfo: Open DRM / Get Caps
        HWInfo --> Core: Success
        deactivate HWInfo
        
        Core --> CoreStatic: Success
        CoreStatic --> CM: core_intf_
        deactivate CoreStatic

        ' 2.3 创建 Builder
        create Builder
        CM -> Builder: new SDMDisplayBuilder(core_intf_, ...)
        CM -> Builder: Init()

== 阶段 3: 创建主显示设备 (Primary Display) ==
        CM -> CM: CreatePrimaryDisplay()
        CM -> Builder: **CreatePrimaryDisplay()**
        activate Builder
        
        ' 3.1 查询连接状态
        Builder -> Core: GetDisplaysStatus()
        Core -> HWInfo: GetDisplaysStatus()
        HWInfo --> Core: HWDisplaysInfo (is_connected=true, type=BuiltIn)
        Core --> Builder: HWDisplaysInfo
        
        ' 3.2 发现 Primary BuiltIn Display，开始构建
        create DBI
        Builder -> DBI: **Create(...)**
        activate DBI
        
        DBI -> DBI: Init()
        
            ' 3.3 创建 DPU Mux (处理多核/Split)
            ' [修复点] create Mux 必须紧邻发送给 Mux 的消息
            create Mux
            DBI -> Mux: **DPUCoreFactory::Create(...)**
            activate Mux
            
            Mux -> Mux: Init()
            
                ' 3.4 创建底层 HW Interface
                loop For Each DPU Core
                    Mux -> HWFactory: **HWInterface::Create(type=kBuiltIn)**
                    activate HWFactory
                    
                    create HW
                    HWFactory -> HW: **new HWPeripheralDRM(...)**
                    activate HW
                    HWFactory -> HW: Init()
                    
                    ' 3.5 HW 初始化 (DRM Session)
                    HW -> HW: HWDeviceDRM::Init() (Register Display)
                    HW -> HW: PopulateHWPanelInfo() (Read Max Brightness)
                    
                    HW --> HWFactory: Success
                    deactivate HW
                    
                    HWFactory --> Mux: HWInterface*
                    deactivate HWFactory
                end
            
            Mux --> DBI: Success
            deactivate Mux
            
        DBI --> Builder: Display*
        deactivate DBI
        
        ' 3.6 注册回 ConcurrencyMgr
        Builder -> CM: SetDisplayByClientId(Primary, DBI*)
        note right of CM: sdm_display_[0] = DBI
        
        Builder --> CM: Success
        deactivate Builder
        
    CM --> AC: Success
    deactivate CM

AC --> Main: Created
deactivate AC

Main -> Main: AServiceManager_addService(AidlComposer)
note right of Main: 服务就绪，等待 SurfaceFlinger 连接

@enduml

```

### 关键步骤解析

#### 1. 唯一入口：`service.cpp`

这是 HWC 进程的起点。它并没有直接去操作硬件，而是先创建了 `AidlComposer`。这符合 Android VINTF 架构，将 AIDL 接口作为服务的门面。

#### 2. 隐藏的单例：`ConcurrencyMgr`

`AidlComposer` 在构造时通过 `SDMInterfaceFactory` 获取了一堆接口（`LifeCycle`, `Settings` 等）。
**关键点**：这些接口的实现者全是同一个对象——**`ConcurrencyMgr`**。它是 SDM Client 层的“上帝对象”，如果不初始化它，整个显示系统就不会启动。

#### 3. 硬件扫描：`HWInfoInterface`

在创建任何 Display 对象之前，SDM 必须先知道底层有什么。
`CoreImpl` 初始化时会调用 `HWInfoInterface` 去扫描 DRM 节点（`/dev/dri/card0`），获取连接器列表、面板信息（是否有内屏、是否支持 HDR 等）。

#### 4. 工厂流水线：`DisplayBuilder` -> `DisplayBuiltIn` -> `HWPeripheralDRM`

这是对象创建的核心链条：

* **Builder**: 拿到硬件列表，发现有一个主屏（Primary），于是决定造一个 `DisplayBuiltIn`。
* **Logic (BuiltIn)**: `DisplayBuiltIn` 初始化时，发现可能需要控制多个 DPU 核心（例如左右分屏），于是创建 `DPUMultiCore`。
* **Hardware (DAL)**: `DPUMultiCore` 最终请求创建一个硬件接口。因为类型是 `kBuiltIn`，工厂方法（`hw_interface.cpp`）毫不犹豫地创建了 **`HWPeripheralDRM`**。

#### 5. 最终状态

当 `service.cpp` 执行到 `addService` 时：

* 内存中已经存在了 `HWPeripheralDRM` 实例。
* 该实例已经尝试读取了 `/sys/class/backlight/...`（在 `PopulateHWPanelInfo` 阶段）。
* 如果是在虚拟化环境且没有适配，此时 `brightness_base_path_` 可能已经包含了错误的路径，或者 max brightness 为 0，为后续的 `BadConfig` 埋下了伏笔。