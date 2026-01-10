# Android Subsystem Wiki: WindowInfos Update Flow


## 1. 概述 (Overview)

**WindowInfos Update Flow** 是 Android 图形与输入系统协同工作的核心机制。它负责将 SurfaceFlinger (SF) 合成过程中产生的最新窗口属性（WindowInfo，如几何位置、Z-Order、透明度、触摸区域、焦点及其变换矩阵）实时同步给 SystemServer 进程。

主要消费者包括：

* **InputDispatcher (Native)**: 负责根据窗口信息计算触摸事件的目标窗口（Hit Testing）。
* **AccessibilityWindowsPopulator (Java)**: 负责为无障碍服务（A11y）构建屏幕内容的窗口节点树。

该机制的高效性直接决定了触摸响应的延迟和窗口焦点的准确性。由于涉及高频跨进程通信（IPC）和大数据量传输，它是系统稳定性问题（如 `DeadSystemException`、Binder 缓冲区耗尽）的高发区。

## 2. 核心架构与组件 (Architecture)

数据流向遵循 **Producer-Consumer** 模型，并通过 **WindowInfosListenerReporter** 实现多路复用。

### 2.1 发送端 (Producer: SurfaceFlinger)

* **触发源**: 每一帧合成（Vsync）后，若检测到图层属性变化 (`mVisibleRegionsDirty` 或 `mInputInfoChanged`)，触发更新。
* **异步发送**: 通过 `BackgroundExecutor` 线程发送，避免阻塞主渲染线程。
* **通信接口**: `IWindowInfosListener.onWindowInfosChanged` (AIDL)，定义为 `oneway`（非阻塞），允许极高的发送频率。

### 2.2 中转与分发 (Transport & Dispatch: SystemServer)

* **WindowInfosListenerReporter (Native)**:
* **角色**: SystemServer 进程内的单例 Binder Stub (`BnWindowInfosListener`)。
* **职责**: 它是 SystemServer 与 SurfaceFlinger 之间**唯一**的 Binder 通道。负责接收跨进程数据，并**同步**分发给进程内注册的所有监听器。



### 2.3 接收端 (Consumers)

1. **InputDispatcher (Native)**:
* **行为**: **同步阻塞**。在回调中必须获取全局锁 `mLock` 以更新窗口状态。这是性能瓶颈所在。


2. **AccessibilityWindowsPopulator (Java)**:
* **行为**: **异步非阻塞**。通过 JNI 接收回调后，立即通过 `Handler.post` 将繁重逻辑转移至 WMS 线程，不占用 Binder 线程。



## 3. 详细时序流程 (Sequence Diagram)

下图展示了从 InputDispatcher 注册监听，到 SurfaceFlinger 分发数据，再到不同消费者处理数据的完整时序。

```plantuml
@startuml
@startuml
!theme plain
autonumber "<b>[0]"

title SystemServer: Registration & WindowInfos Update Flow (Complete)

box "SurfaceFlinger Process" #E3F2FD
    participant "SurfaceFlinger" as SF
end box

box "Kernel Space" #F5F5F5
    participant "Binder Driver" as Kernel
end box

box "SystemServer Process (Native)" #FFF3E0
    participant "IPCThreadState" as IPC
    participant "BnWindowInfosListener\n(Stub)" as Stub
    participant "WindowInfosListenerReporter\n(Singleton)" as Reporter
    participant "SurfaceComposerClient" as SCC
    participant "InputDispatcher" as Dispatcher
    participant "DispatcherWindowListener" as Listener
end box

box "SystemServer Process (Java)" #FFE0B2
    participant "AccessibilityWindowsPopulator\n(A11yPop)" as A11yPop
    participant "WMS Handler Thread" as WMS_Thread
    participant "WindowManagerService" as WMS
    participant "AccessibilityWindowManager" as AWM
    participant "AccessibilityManagerService" as AMS
end box

== 0.1 InputDispatcher 注册流程 (Native) ==

Dispatcher -> Dispatcher: new DispatcherWindowListener(*this)
activate Dispatcher
note right: 创建本地监听器

Dispatcher -> SCC: addWindowInfosListener(listener)
activate SCC
SCC -> Reporter: getInstance()
SCC -> Reporter: addWindowInfosListener(listener, ...)
activate Reporter

Reporter -> Reporter: check mWindowInfosListeners.empty()

alt #LightGreen <color:green><b>首次注册 (First Time)</b></color>
    note right of Reporter
        集合为空，说明 Reporter 尚未连接 SF。
        将 Reporter (this) 注册到远程。
    end note
    Reporter -> SF: IWindowInfosListener.addWindowInfosListener(this)
    activate SF
    SF -> SF: 保存 Reporter 句柄
    SF --> Reporter: status
    deactivate SF
else <color:gray>后续注册 (Re-use)</color>
    note right of Reporter
        集合不为空，通道已建立。
        直接复用，不发起 Binder 调用。
    end note
end

Reporter -> Reporter: mWindowInfosListeners.insert(listener)
note right: 将 InputDispatcher 加入本地集合

Reporter --> SCC: status
deactivate Reporter
SCC --> Dispatcher: status
deactivate SCC
deactivate Dispatcher

== 0.2 Accessibility 注册流程 (Java Stack) ==

note right of AMS
  <b>触发时机:</b>
  1. 系统启动完毕
  2. 开启无障碍服务 (TalkBack等)
  3. 显示器插拔 (onDisplayAdded)
end note

AMS -> AWM: startTrackingWindows()
activate AMS
AWM -> WMS: setWindowsForAccessibilityCallback()
activate AWM
WMS -> A11yPop: setWindowsNotification(true)
activate WMS
activate A11yPop

A11yPop -> A11yPop: register()
A11yPop -> SCC: nativeRegister() [JNI]
activate SCC

SCC -> Reporter: addWindowInfosListener(listener)
activate Reporter
note right of Reporter
  检测到 InputDispatcher 已注册，
  这里直接复用现有通道，
  将 A11yPop 加入本地集合。
end note
Reporter -> Reporter: mWindowInfosListeners.insert(A11yPop)

Reporter --> SCC: status
deactivate Reporter
SCC --> A11yPop: status
deactivate SCC
A11yPop --> WMS: void
deactivate A11yPop
WMS --> AWM: void
deactivate WMS
AWM --> AMS: void
deactivate AWM
deactivate AMS

|||

== 1. 跨进程接收 (Binder Thread) ==

SF -> Kernel: onWindowInfosChanged(data) (Oneway)
note left: SF 生产 46KB 数据\n疯狂发送

Kernel -> IPC: ioctl(BR_TRANSACTION)
activate IPC
note left: Binder 线程被唤醒

IPC -> Stub: onTransact(...)
activate Stub
note right: <color:red><b>反序列化 (Unmarshalling)</b></color>\n解析 Parcel -> vector<WindowInfo>

Stub -> Reporter: onWindowInfosChanged(windowInfos, ...)
deactivate Stub
activate Reporter

== 2. 进程内分发 (Reporter Loop) ==

note right of Reporter
    <color:red><b>同步循环 (Synchronous Loop)</b></color>
    运行在 Binder 线程中。
    必须等所有 Listener 处理完才能返回。
end note

loop foreach listener in mWindowInfosListeners

    alt #MistyRose Listener == InputDispatcher (Native)
        Reporter -> Listener: onWindowInfosChanged(windowInfos)
        activate Listener
        
        == 3. 业务处理 (InputDispatcher) ==
        
        Listener -> Dispatcher: setInputWindows(windowInfos)
        activate Dispatcher
        
        Dispatcher -> Dispatcher: <color:red>std::scoped_lock _l(mLock)</color>
        note right
            <color:red><b>关键阻塞点 (Critical Block)</b></color>
            InputDispatcher 持锁处理。
            如果有 Input 事件积压，这里会卡住。
            <b>这是导致 Oneway Spamming 的主要原因。</b>
        end note
        
        Dispatcher -> Dispatcher: setInputWindowsLocked(...)
        
        Dispatcher --> Listener: void
        deactivate Dispatcher
        
        Listener --> Reporter: void
        deactivate Listener

    else #AliceBlue Listener == AccessibilityWindowsPopulator (Java)
        Reporter -> A11yPop: onWindowInfosChanged(windowHandles, ...) [JNI]
        activate A11yPop
        
        == 3.1 业务处理 (A11yPopulator) ==
        
        A11yPop -> A11yPop: mHandler.post(...)
        note right
            <color:green><b>异步非阻塞 (Async)</b></color>
            源码: mHandler.post(() -> onWindowInfosChangedInternal)
            立即返回，不占用 Binder 线程时间。
        end note
        
        A11yPop --> Reporter: void
        deactivate A11yPop
        
        A11yPop -[#blue]> WMS_Thread: onWindowInfosChangedInternal(...)
        activate WMS_Thread
        note right
           <b>延迟处理:</b>
           繁重的矩阵计算(Matrix)和
           遍历逻辑在此线程执行。
        end note
        deactivate WMS_Thread
    end
end

Reporter --> Stub: void
deactivate Reporter

Stub --> IPC: void
IPC -> Kernel: ioctl(BC_FREE_BUFFER)
note left: 只有执行到这里，\n内核缓冲区才会被释放。
deactivate IPC

@enduml
```
