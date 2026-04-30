+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = 'Android InputFlinger'
+++

# Android InputFlinger

## 架构图

```mermaid
flowchart TD
    %% 样式定义
    classDef kernel fill:#d5e8d4,stroke:#333,stroke-width:1px;
    classDef sysjava fill:#ffe6cc,stroke:#333,stroke-width:1px;
    classDef sysnative fill:#dae8fc,stroke:#333,stroke-width:1px;
    classDef sf fill:#f8cecc,stroke:#333,stroke-width:1px;
    classDef app fill:#e1d5e7,stroke:#333,stroke-width:1px;

    subgraph KernelSpace [Kernel Space]
        Driver[Touch Driver]:::kernel
        DevNode([/dev/input/event*]):::kernel
    end

    subgraph SystemServerJava [System Server Java]
        WMS[WindowManagerService]:::sysjava
        IMS[InputManagerService]:::sysjava
    end

    subgraph SurfaceFlingerSpace [SurfaceFlinger Process]
        SF[SurfaceFlinger]:::sf
    end

    subgraph SystemServerNative [System Server Native InputFlinger]
        subgraph ReaderThread [InputReader Thread]
            EventHub[EventHub]:::sysnative
            InputReader[InputReader]:::sysnative
            Mapper[MultiTouchInputMapper
解析 Slot/TrackingID]:::sysnative
        end

        subgraph Pipeline [Processing Chain - Listener]
            Blocker[UnwantedInteractionBlocker
掌误触抑制]:::sysnative
            Choreo[PointerChoreographer
光标/坐标转换]:::sysnative
            Processor[InputProcessor]:::sysnative
            Filter[InputFilter]:::sysnative
        end

        subgraph DispatcherThread [InputDispatcher Thread]
            Dispatcher[InputDispatcher]:::sysnative
            InQueue[(InboundQueue)]:::sysnative
            OutQueue[(OutboundQueue)]:::sysnative
        end
    end

    subgraph AppSpace [App Process]
        ClientChannel[InputChannel Client]:::app
        ViewRoot[ViewRootImpl]:::app
    end

    %% --- 事件流 (Event Flow) ---
    Driver --> DevNode
    DevNode -- "read()" --> EventHub
    EventHub -- "RawEvents" --> InputReader
    InputReader <-->|"process() / Cooked Data"| Mapper
    
    InputReader -- "notifyMotion()" --> Blocker
    Blocker -- "notifyMotion()" --> Choreo
    Choreo -- "notifyMotion()" --> Processor
    Processor -- "notifyMotion()" --> Filter
    Filter -- "notifyMotion()" --> Dispatcher

    Dispatcher -- "enqueue" --> InQueue
    InQueue -- "dispatch" --> OutQueue
    OutQueue -. "SocketPair (InputChannel)" .-> ClientChannel
    ClientChannel -- "onInputEvent()" --> ViewRoot

    %% --- 控制流 (Control Flow - Window & Config) ---
    WMS -. "1. 同步焦点与拦截规则" .-> IMS
    IMS == "2. JNI 下发配置 (DisplayViewport等)" ==> InputReader
    WMS == "3. WindowHandle (SurfaceControl Transaction)" ==> SF
    SF == "4. 跨进程更新可见窗口列表 (setInputWindows)" ==> Dispatcher
```


## 关键逻辑的实现与作用

在上述架构图中，Android Input 框架通过职责分离，将复杂的输入事件处理拆解为多个核心阶段。为了确保事件准确、安全、低延迟地送达 App，系统服务（WMS、IMS、SurfaceFlinger）与 Native Input 进行了深度的协同。以下是关键逻辑的实现细节与作用：

### 1. 事件读取与初步加工 (InputReader & Mapper)
*   **作用：** 负责监听底层 Linux 驱动（`/dev/input/event*`），将原始的、基于时间的散乱硬件中断信号（如 `EV_ABS`, `EV_SYN`），聚合为一个具有完整逻辑意义的 Android 输入事件（如一次完整的触摸滑动）。
*   **实现：** 
    *   **`EventHub`** 使用 `epoll` 机制死循环监听所有输入设备节点。
    *   **`MultiTouchInputMapper`** 是处理触摸屏的核心。它负责解析 Linux 驱动上报的多点触控协议（Protocol B），通过 `TrackingID` 和 `Slot` 追踪多根手指的按下、移动、抬起状态，最终将这些状态打包为统一的 `NotifyMotionArgs` 结构体。
    *   **IMS 交互：** InputManagerService 会通过 JNI 将设备的配置参数（如 `DisplayViewport`，即屏幕物理映射关系、旋转角度）传递给 Reader，用于基础的坐标边界转换。

### 2. 事件加工责任链 (Listener Pipeline)
*   **作用：** 在事件送达分发器之前，进行一系列拦截、过滤和坐标变换。由于采用了反向注入的责任链模式（Listener Pipeline），使得 InputFlinger 能够灵活插拔新的过滤规则。
*   **实现：** 
    *   **`UnwantedInteractionBlocker` (掌误触抑制)：** 调用 `PalmFilterImplementation` 评估触摸面积和轨迹，如果判定为手掌大面积误触（Palm Rejection），则会中途阻断该事件或发送 `ACTION_CANCEL`。
    *   **`PointerChoreographer` (指针编排器)：** 统一处理鼠标、触控板、手写笔的指针逻辑。它负责光标图标的绘制状态控制，并将鼠标的**相对移动坐标**转换为屏幕上的**绝对坐标**。
    *   **`InputFilter` (输入过滤)：** 将事件回调给 Java 层的 IMS，供无障碍服务（Accessibility）消费。如果开启了辅助功能，事件会在这里被拦截处理后再决定是否放行。

### 3. 跨进程窗口状态同步 (SurfaceFlinger -> InputDispatcher)
*   **作用：** 解决经典的“幽灵点击”和“焦点穿透”问题（Tapjacking）。这是现代 Android Input 架构中最重要的一次重构，确保了 InputDispatcher 决策时的窗口层级（Z-Order）和可见性，与用户在屏幕上真实看到的渲染画面绝对一致。
*   **实现：** 
    *   **WMS 赋权：** WindowManagerService 在管理窗口时，不再直接把窗口坐标传递给 Input。而是通过 `SurfaceControl.Transaction` 将包含了 `InputWindowHandle` 信息的属性附着在渲染图层上，提交给 **SurfaceFlinger**。
    *   **SF 裁决：** SurfaceFlinger 在完成所有图层的混合计算后，精准知道哪些图层在最顶端、哪些被完全遮挡（Occlusion）。
    *   **Binder 同步：** SurfaceFlinger 计算出最终真实的“屏幕可见窗口列表”，跨进程调用 `InputDispatcher::setInputWindows()`，将这份拥有绝对真实坐标和层级的列表交给 Input，Dispatcher 将其缓存为决策依据。

### 4. 坐标匹配与跨进程分发 (InputDispatcher & InputChannel)
*   **作用：** 根据触摸坐标或当前系统的焦点（由 WMS 指定），找到应该接收该事件的 App 窗口，并将其安全、无阻塞地跨进程发送过去。
*   **实现：**
    *   **目标寻找：** Dispatcher 遍历 SF 传来的可见窗口列表（从 Z 轴由高到低）。通过检查 `InputWindowInfo` 的 `TouchableRegion`（可触摸区域），找到第一个包含该坐标且状态为 `Touchable` 的窗口。
    *   **异步发送：** 找到目标后，将事件包装送入该连接的 `OutboundQueue`。Dispatcher 使用非阻塞的 Unix Domain Socket (`socketpair`) 通过 `InputPublisher` 将事件跨进程 `send()` 写入底层的 Socket 缓冲区。
    *   **App 消费与 ANR 机制：** App 进程的主线程 `ViewRootImpl` 监听到 Socket 的可读事件，解析出事件并沿 View 树（ViewGroup -> View）分发。**重点在于闭环：** App 消费完成后，必须调用 Java 层的 `finishInputEvent()`，进而向 Socket 回写一个 `FINISHED` 信号，Dispatcher 侧由 `handleReceiveCallback()` 接收并调用 `finishDispatchCycleLocked()` 清除追踪记录。如果 Dispatcher 将事件发出后，在预设时间（通常是 5 秒）内没有收到 App 的 finish 响应，就会触发 **ANR (Application Not Responding)**。

## 关键时序

```mermaid
sequenceDiagram
    autonumber
    participant Kernel as Linux Kernel
    
    box LightBlue System Server (InputReader Thread)
    participant EH as EventHub
    participant Reader as InputReader
    participant Mapper as MultiTouch<br>InputMapper
    participant Chain as Listener Chain<br>(Blocker/Choreo/...)
    end
    
    box LightYellow System Server (InputDispatcher Thread)
    participant Disp as InputDispatcher
    end
    
    participant App as App Window<br>(UI Thread)

    %% --- 1. 物理层 & 驱动层 ---
    rect rgb(240, 240, 240)
    Note over Kernel: 1. 物理层 & 驱动层
    Kernel ->> Kernel: Interrupt & ISR
    Kernel ->> EH: 写入 /dev/input/eventX (EV_ABS/SYN)
    end

    %% --- 2. 读取与解码 ---
    rect rgb(240, 240, 240)
    Note over EH, Mapper: 2. 读取与解码 (Reader Thread)
    EH ->> EH: epoll_wait 唤醒
    Reader ->> Reader: loopOnce()
    Reader ->> EH: getEvents()
    EH -->> Reader: RawEvent;
    
    Reader ->> Reader: processEventsLocked()
    Reader ->> Mapper: process(RawEvent)
    activate Mapper
    Mapper ->> Mapper: syncTouch() - 解析 Slot/TrackingID
    Mapper ->> Mapper: cookPointerData() - 转换坐标
    Mapper -->> Reader: Cooked Data
    deactivate Mapper
    end

    %% --- 3. 责任链处理 ---
    rect rgb(240, 240, 240)
    Note over Reader, Chain: 3. 责任链处理 (Reader Thread)
    Reader ->> Chain: notifyMotion(args)
    activate Chain
    Note right of Chain: 依次经过:<br/>1. UnwantedInteractionBlocker<br/>2. PointerChoreographer<br/>3. InputProcessor<br/>4. InputFilter
    Chain ->> Chain: Apply policy (e.g. palm check)
    Chain ->> Disp: notifyMotion(args)
    deactivate Chain
    end

    %% --- 4. 分发排队 ---
    rect rgb(240, 240, 240)
    Note over Chain, Disp: 4. 分发排队 (Reader Thread 交接给 Dispatcher Thread)
    activate Disp
    Disp ->> Disp: enqueueInboundEventLocked()
    Disp ->> Disp: mLooper->wake() // 唤醒分发线程
    deactivate Disp
    end

    %% --- 5. 发送给应用 ---
    rect rgb(240, 240, 240)
    Note over Disp, App: 5. 命中测试与跨进程发送 (Dispatcher Thread)
    Disp ->> Disp: dispatchOnce() -> dispatchOnceInnerLocked()
    Note right of Disp: 【核心修正】<br>触摸事件: findTouchedWindowTargets() 查坐标<br>按键事件: findFocusedWindowTargetLocked() 查焦点
    Disp ->> Disp: 寻找目标 (Hit Testing / Focus)
    Disp ->> App: publishMotionEvent() <br> (Unix Domain Socket send)
    end

    %% --- 6. 应用消费 ---
    rect rgb(240, 240, 240)
    Note over App: 6. 应用消费与闭环 (App UI Thread)
    App ->> App: Looper 唤醒读取 Socket
    App ->> App: InputEventReceiver.dispatchInputEvent()
    App ->> App: ViewRootImpl.processPointerEvent()
    App ->> App: Activity.dispatchTouchEvent()
    App ->> App: finishInputEvent() (App Java API)
    App -->> Disp: Socket write (FINISHED 信号)
    Disp ->> Disp: handleReceiveCallback()
    Disp ->> Disp: finishDispatchCycleLocked() <br> (清除 ANR 倒计时)
    end
```

### 时序流程深度源码解析

上面的时序图详细描绘了从手指触摸屏幕到应用处理完毕的完整生命周期，以下是结合 AOSP 源码对各个关键阶段的深度解析：

#### 1. 物理层与驱动层 (Kernel)
触摸屏硬件产生中断后，Linux 内核的 Input 子系统响应该中断，并将触控 IC 传来的坐标和压力等信息转化为标准的 Linux Input 协议（如 `EV_ABS`, `EV_SYN`），写入到对应的设备节点（如 `/dev/input/event2`）中。

#### 2. 读取与解码 (InputReader Thread)
*   **驱动轮询：** `InputReader` 线程的核心是一个名为 `loopOnce()` 的死循环。它首先调用 `EventHub::getEvents()`，该方法底层通过 `epoll_wait` 阻塞监听所有的 `/dev/input/event*` 节点。一旦有数据可读，内核唤醒该线程，并返回原始的 `RawEvent` 数组。
*   **解析组装：** Reader 调用 `processEventsLocked()` 将事件分发给对应的设备 Mapper。对于触摸屏，起作用的是 `MultiTouchInputMapper`。Mapper 的 `syncTouch()` 方法负责解析 Linux 的 Slot 协议和 Tracking ID，随后 `cookPointerData()` 将驱动的原始数据（Raw Data）转换为带有 Android 绝对坐标和逻辑的 `NotifyMotionArgs` 结构体。

#### 3. 责任链处理 (Listener Pipeline)
当 Mapper 将数据“煮熟 (cooked)”后，`InputReader` 会调用 `notifyMotion(args)` 启动责任链。正如架构图所示，事件在到达 Dispatcher 之前，会依次穿过一系列的 Listener：
1.  **UnwantedInteractionBlocker**：执行防误触策略（如掌托过滤 Palm Rejection）。
2.  **PointerChoreographer**：处理鼠标等指针设备的坐标和光标转换。
3.  **InputProcessor**：进行坐标的仿射变换（如处理屏幕旋转、折叠屏坐标映射）。
4.  **InputFilter**：拦截供无障碍服务 (Accessibility) 使用的事件。
最终，过滤后的纯净事件通过 `InputDispatcher::notifyMotion(args)` 交接给分发器。

#### 4. 线程交接与分发排队 (Reader -> Dispatcher)
*   **入队：** `InputDispatcher` 在自己的线程中运行。当它被 Reader 线程调用 `notifyMotion()` 时，会将事件包装为 `EventEntry`，并放入自己的 `InboundQueue` 中。
*   **唤醒：** 为了不阻塞 Reader 线程继续读取下一个硬件中断，入队后会立刻调用 `mLooper->wake()` 唤醒处于休眠状态的 Dispatcher 线程，Reader 线程随即返回。

#### 5. 命中测试与跨进程发送 (InputDispatcher Thread)
*   **目标寻找 (Hit Testing)：** Dispatcher 线程被唤醒后执行 `dispatchOnceInnerLocked()`。对于触摸事件（Touch），它调用 `findTouchedWindowTargets()`，利用 SurfaceFlinger 传来的可见窗口树，根据触控点的 X/Y 坐标进行从上到下的 Z 轴命中测试；而对于按键事件（Key），则调用 `findFocusedWindowTargetLocked()` 直接寻找拥有焦点的窗口。
*   **异步发送：** 找到目标后，Dispatcher 调用 `InputPublisher::publishMotionEvent()`。底层通过非阻塞的 Unix Domain Socket (`send` / `write`) 将事件序列化后发送给目标 App 进程。同时，Dispatcher 开始为该事件倒数 5 秒的 ANR 计时器。

#### 6. 应用消费与闭环 (App -> Dispatcher)
*   **应用处理：** App 进程的主线程 `Looper` 监听到 Socket 有数据可读，被唤醒后通过 `InputEventReceiver` 读取事件，随后一路向下分发至 `ViewRootImpl` 和 `Activity` 的 `onTouchEvent`。
*   **ANR 闭环 (核心)：** App 消费完事件后，无论结果如何，框架都会自动调用 Java 层的 `finishInputEvent()`。该方法会通过 JNI 和 Socket 向 Dispatcher 回写一个 `FINISHED` 信号。Dispatcher 线程在 `handleReceiveCallback()` 中监听到该信号，调用 `finishDispatchCycleLocked()`，将这笔交易的追踪记录删除，并**撤销该事件的 5 秒 ANR 倒计时**。至此，整个输入分发生命周期安全结束。


## 案例分析：Linux Raw 事件到 Android MotionEvent 的演化

为了深入理解 `InputReader` 和 `MultiTouchInputMapper` 的工作原理，我们通过抓取 `/dev/input/event2` 节点的真实驱动日志，分析一次“单指按下、轻微滑动、抬起”的完整生命周期。同时，我们将引入现代 Android 多点触控最核心的 **`Tracking_ID` 与 `Slot` 机制**。

### 核心概念：Tracking_ID 与 Slot 机制
在现代 Android 采用的 **Linux Multi-Touch Protocol B (Slot 协议)** 中，屏幕上的每一根独立手指都会被分配一个独一无二的 **`Tracking_ID`**。
* **Slot (槽位)**：驱动维护的容器，表示当前硬件支持的并发触控点（例如 10 指触控就有 10 个 Slot）。
* **Tracking_ID (生命周期ID)**：一旦手指接触屏幕，硬件就会在某个空闲的 Slot 中为其生成一个大于 0 的唯一 `Tracking_ID`。这个 ID 会伴随手指从按下、移动，一直到抬起（抬起时发送特殊的 `Tracking_ID = -1` 宣告死亡）。这是解决多指滑动轨迹混淆（鬼影问题）的物理基石。

### 手指按下 (ACTION_DOWN)
```txt
/dev/input/event2: EV_KEY       BTN_TOUCH            DOWN                
/dev/input/event2: EV_ABS       ABS_MT_TRACKING_ID   00000005            
/dev/input/event2: EV_ABS       ABS_MT_POSITION_X    000002b3            
/dev/input/event2: EV_ABS       ABS_MT_POSITION_Y    00000373            
/dev/input/event2: EV_ABS       ABS_MT_TOUCH_MAJOR   00000004            
/dev/input/event2: EV_ABS       ABS_MT_TOUCH_MINOR   00000003            
/dev/input/event2: EV_ABS       ABS_MT_PRESSURE      00000015            
/dev/input/event2: EV_SYN       SYN_REPORT           00000000            
```
*   **驱动上报**：Linux 内核采用 **“状态差分 (State Delta)”** 的方式上报数据。当手指刚接触屏幕时，驱动发送了接触状态 (`BTN_TOUCH DOWN`)、新分配的手指生命周期 ID (`ABS_MT_TRACKING_ID: 5`)、X/Y 坐标、接触面积 (`TOUCH_MAJOR/MINOR`) 以及压力值 (`PRESSURE`)。
*   **同步界限**：极度关键的 `EV_SYN / SYN_REPORT` 标志着**一帧数据组合的结束**。
*   **Mapper 处理**：`MultiTouchInputMapper` 的累加器收到 `SYN_REPORT` 后，会和上一帧（空状态）进行比对。发现新增了一个 `Tracking_ID` (5)，于是为这根手指分配一个 Android 框架层级的 `PointerId`（通常为 0），生成一个 **`ACTION_DOWN`** 发送给责任链。

### 手指微动/压力变化 (ACTION_MOVE)
```txt
/dev/input/event2: EV_ABS       ABS_MT_PRESSURE      00000016            
/dev/input/event2: EV_SYN       SYN_REPORT           00000000            
... 
/dev/input/event2: EV_ABS       ABS_MT_TOUCH_MAJOR   00000002            
/dev/input/event2: EV_ABS       ABS_MT_TOUCH_MINOR   00000002            
/dev/input/event2: EV_ABS       ABS_MT_PRESSURE      00000013            
/dev/input/event2: EV_SYN       SYN_REPORT           00000000            
```
*   **驱动上报**：在手指滑动和按压的过程中，内核**只发送改变的值**。比如紧接着的一帧只发了 `PRESSURE`，没发 `POSITION_X/Y`，说明坐标没动但压力变了。随后的帧中 `TOUCH_MAJOR` 和 `PRESSURE` 都在微调。
*   **Mapper 处理**：`InputReader` 将这些差分数据叠加更新到对应 `Slot` 的状态机上。每次遇到 `SYN_REPORT`，只要发现当前激活手指的属性（坐标、压力、面积等）发生了改变，就会生成一个 **`ACTION_MOVE`** 事件。为了性能，高频的微小 MOVE 事件后续可能会被 `InputDispatcher` 自动合并 (Batching)。

### 手指抬起 (ACTION_UP)
```txt
/dev/input/event2: EV_ABS       ABS_MT_PRESSURE      00000000            
/dev/input/event2: EV_ABS       ABS_MT_TRACKING_ID   ffffffff            
/dev/input/event2: EV_KEY       BTN_TOUCH            UP                  
/dev/input/event2: EV_SYN       SYN_REPORT           00000000
```
*   **特殊销毁信号**：驱动发送了 `PRESSURE = 0`，最关键的是发送了 **`ABS_MT_TRACKING_ID = ffffffff (-1)`**。在 Slot 协议中，`-1` 意味着这个槽位中手指的生命周期彻底结束。
*   **Mapper 处理**：`MultiTouchInputMapper` 读到 `Tracking_ID` 变为 `-1` 且收到 `SYN_REPORT` 时进行状态比对，确认屏幕上的触控点从 1 个变成了 0 个。此时：
    1. 生成 **`ACTION_UP`** 事件分发至 App。
    2. 释放内部绑定的 `PointerId` (归还 0)，重置该 Slot 槽位。
    3. 至此，完成了一次单指触摸手势的完整状态机闭环。


## 智能座舱多屏架构支持 (Multi-Display Input)

在智能座舱（Android Automotive OS, AAOS）或多屏互联场景中，车机通常包含中控屏 (Center Information Display, CID)、副驾屏 (Passenger Display)、甚至后排娱乐屏 (Rear Seat Entertainment, RSE)。`InputFlinger` 必须能够准确识别多个物理触摸设备，并将其产生的事件精准派发到对应屏幕的独立应用窗口中。

Android 的输入子系统通过一套严密的 **“设备绑定”** 与 **“分区路由”** 机制实现了多屏触控支持。

### 1. 设备的发现与物理屏幕绑定 (InputReader 层)
当一个新的触摸屏硬件（如通过 USB、I2C 或 GMSL 桥接的 I2C）接入时，内核会在 `/dev/input/` 下生成一个新的 `eventX` 节点。`InputReader` 的 `EventHub` 发现设备后，面临的核心问题是：**“这个触摸屏对应的是车里的哪一块屏幕？”**

*   **IDC 配置文件 (Input Device Configuration)：** 系统集成商通常会为每个触摸屏硬件提供一个 `.idc` 配置文件（通过 Vendor ID 和 Product ID 匹配）。在文件中可以声明：
    *   `touch.deviceType = touchScreen`（表明这是直接贴合在屏幕上的触摸层，而非远端触控板 `pointer`）。
*   **物理端口映射 (sysfs / Location)：** 车机系统可以通过读取设备的硬件连接拓扑（例如固定的 I2C 总线地址或 USB 端口物理路径 `location`）来区分中控触摸框和副驾触摸框。
*   **Viewport 注入与匹配：** WindowManager / DisplayManager 获知系统中点亮了多个屏幕后，会将所有屏幕的 `DisplayViewport`（包含逻辑显示器 ID、物理尺寸、对应的物理端口 `uniqueId`）下发给 Native 层的 `InputReader`。`InputReader` 会将物理触摸设备的 `location` 与 `DisplayViewport` 的 `uniqueId` 进行字符串匹配。
*   **打上标签 (Stamping)：** 匹配成功后，该 InputDevice 就会和具体的 `displayId`（如中控是 0，副驾是 2）绑定。当这块屏幕被触摸时，`MultiTouchInputMapper` 产出的每一个 `NotifyMotionArgs` 都会被**强制打上 `displayId` 标签**。

### 2. 多屏独立的可见窗口树 (SurfaceFlinger 层)
如前文架构图所述，SurfaceFlinger 负责向 `InputDispatcher` 同步真实的可见窗口列表。
在多屏环境下，SurfaceFlinger 会为**每一个物理显示器 (DisplayId)** 构建并混合一棵独立的 Layer 渲染树。当它通过 `setInputWindows()` 跨进程调用将窗口列表传递给 Input 层时，每一个 `InputWindowInfo` 数据结构中都严格包含着它所渲染在的 `displayId`。

### 3. 精准的跨屏派发隔离 (InputDispatcher 层)
当 `InputDispatcher` 收到一个带有屏幕标签（例如 `displayId = 2`，副驾屏）的 `MotionEvent` 时：
*   **分区命中测试 (Hit Testing)：** Dispatcher 在执行 `findTouchedWindowTargets()` 时，**只会遍历那些属于 `displayId == 2` 的可见窗口列表**，从 Z 轴顶层开始寻找可触摸区域 (`TouchableRegion`) 包含落点的窗口。
*   **绝对坐标隔离：** 即使中控屏（`displayId = 0`）上有一个设置了 `FLAG_SYSTEM_ERROR` 极高层级的全屏遮罩弹窗，只要触摸事件是副驾硬件产生的（携带 `displayId=2`），InputDispatcher 也绝对不会将事件误派发给中控屏的弹窗。坐标系（0,0）永远是相对于当前 `displayId` 对应屏幕的左上角。
*   **多屏多焦点管理 (Per-Display Focus)：** Android 10 之后引入了多屏独立焦点支持。`InputDispatcher` 内部不再维护唯一的全局焦点，而是维护一个映射表（针对不同的显示器维护各自的 Focused Window）。这意味着：驾驶员可以通过方向盘的实体按键控制中控屏的焦点并确认，而此时副驾乘客在副驾屏幕上输入文本（拥有副驾屏的输入焦点），两者在底层的事件路由管道上是完全平行、互不干扰的。

## 核心纽带：InputChannel 的跨进程通信机制

在 Android 窗口管理与输入系统中，`InputChannel` 是连接 System Server (InputDispatcher) 和 App 进程的核心桥梁。不管是常规的触摸窗口，还是用于焦点监控的 `FocusInputMonitor`，底层都是通过 `InputChannel::openInputChannelPair` 创建的一对 **Unix Domain Socket (socketpair)** 来实现全双工的跨进程通信。

下面通过 Mermaid 序列图结合 `createFocusInputMonitor` 等源码流程，详细展示 WMS、InputDispatcher 与 App 之间如何通过 `InputChannel` 建立通信纽带：

```mermaid
sequenceDiagram
    participant WMS as WindowManagerService<br>(System Server Java)
    participant Disp as InputDispatcher<br>(System Server Native)
    participant ConnMgr as ConnectionManager<br>(Dispatcher 内部)
    participant App as App Process<br>(ViewRootImpl)

    Note over WMS, App: 1. 创建通信对 (Channel Pair)
    WMS ->> Disp: 请求创建 InputChannel<br>(如 createInputChannel / createFocusInputMonitor)
    activate Disp
    Disp ->> Disp: openInputChannelPair()<br>底层调用 socketpair(AF_UNIX)
    Note right of Disp: 产生一对 Socket FD:<br>1. serverChannel<br>2. clientChannel
    
    Note over Disp, ConnMgr: 2. Server 侧监听 (Dispatcher)
    Disp ->> ConnMgr: 传递 serverChannel<br>(携带 handleReceiveCallback)
    activate ConnMgr
    ConnMgr ->> ConnMgr: 封装为 Connection 对象
    ConnMgr ->> ConnMgr: Looper->addFd(serverChannel的fd)<br>监听 EPOLLIN 读取 App 的 FINISHED 信号
    deactivate ConnMgr

    Disp -->> WMS: 返回 clientChannel
    deactivate Disp

    Note over WMS, App: 3. 跨进程传递与 App 侧监听
    WMS ->> App: 通过 Binder 传递 clientChannel<br>(实现 Parcelable)
    activate App
    App ->> App: 提取 clientChannel 的 fd
    App ->> App: 构造 WindowInputEventReceiver
    App ->> App: UI Thread Looper->addFd(clientChannel的fd)<br>监听 EPOLLIN 读取 Dispatcher 发来的事件
    
    Note over Disp, App: 4. 全双工异步通信建立完成
    Disp ->> App: publishMotionEvent()<br>向 serverChannel 写入事件
    App ->> Disp: finishInputEvent()<br>向 clientChannel 回写消费完毕信号
    deactivate App
```

### 核心机制解析：

1. **`socketpair` 机制：** `InputChannel` 的底层不是 Binder，而是 `socketpair`。这是因为 Input 事件具有极高的实时性和高频性（如 120Hz 屏幕每秒产生 120 个 Move 事件），传统的 Binder 通信会因频繁的序列化和内存拷贝带来极高延迟，而 Unix Domain Socket 提供了基于内核内存直接映射的高效双向字节流通道。
2. **分离与交接：** 
    * **Dispatcher 侧：** 永远持有 `serverChannel`。在 `createFocusInputMonitor` 或常规窗口注册时，Dispatcher 会将 `serverChannel` 的文件描述符 (FD) 注册到自己的 `Looper` 中，设置回调函数为 `handleReceiveCallback`。这主要是为了监听 App 回写的 `FINISHED` 信号，从而终止 5 秒的 ANR 倒计时。
    * **WMS 侧：** 充当“媒人”。它向 InputManager 请求创建 Channel，拿到 `clientChannel` 后，不作保留，直接通过跨进程的 Binder（如 `IWindowSession.add()` 或焦点监听的回调）将其塞给 App 进程。
    * **App 侧：** 接手 `clientChannel` 后，将其绑定到 UI 线程（Main Thread）的 `MessageQueue/Looper` 中。底层对应的 C++ 类是 `NativeInputEventReceiver`。一旦 Dispatcher 通过 Socket 写入了触摸事件，App 的 `epoll_wait` 就会被唤醒，随即通过 Java 层的回调分发给视图树。
3. **安全与隔离：** 由于每一个窗口（或 Monitor）都拥有自己独立的 `InputChannel` pair，这就保证了极高的隔离性。Dispatcher 只会把事件精确 `send()` 给命中测试目标窗口所在的那个 Socket，其他进程绝不可能通过抓包或监听窃取到该窗口的触摸事件流。

## Input 性能监控与端到端延迟追踪 (Latency Tracking)

在现代 Android 系统（特别是高刷屏和车机等对流畅度要求极高的场景）中，单纯将事件派发给 App 并且不发生 ANR 是远远不够的。系统需要精确度量 **“跟手性”** ——即从用户手指接触屏幕（硬件中断），到最终画面在物理屏幕上产生相应变化（光子级响应）的 **端到端延迟 (End-to-End Latency)** 。

`InputDispatcher` 通过复用 `InputChannel` (Socket) 建立了一套严密的性能监控闭环。

### 1. 双重回调机制：Finished 与 Timeline
当 `InputDispatcher` 监听 App 端的 Socket 返回数据时，`handleReceiveCallback` 核心处理逻辑会解析两种完全不同的信号结构体：

```cpp
if (std::holds_alternative<InputPublisher::Finished>(*result)) {
    // 【分支 1：生命周期闭环】
    const InputPublisher::Finished& finish = std::get<InputPublisher::Finished>(*result);
    finishDispatchCycleLocked(currentTime, connection, finish.seq, finish.handled,
                              finish.consumeTime);
} else if (std::holds_alternative<InputPublisher::Timeline>(*result)) {
    // 【分支 2：渲染时间线追踪】
    if (shouldReportMetricsForConnection(*connection)) {
        const InputPublisher::Timeline& timeline = std::get<InputPublisher::Timeline>(*result);
        mLatencyTracker.trackGraphicsLatency(timeline.inputEventId,
                                             connection->getToken(),
                                             std::move(timeline.graphicsTimeline));
    }
}
```

#### 分支 1：`Finished` 信号 (ANR 防线)
*   **触发时机：** App 进程主线程执行完 `onTouchEvent` 等逻辑后，立即向 Socket 写入 `Finished` 结构体。
*   **作用：** `Dispatcher` 收到后，调用 `finishDispatchCycleLocked()`，携带序列号 (`seq`) 找到对应的分发记录并将其移除，**最重要的是撤销该事件的 5 秒 ANR 倒计时**。它只代表“代码执行完了”，并不代表“画面画出来了”。

#### 分支 2：`Timeline` 信号 (跟手性监控核心)
*   **触发时机：** App 消费完输入事件后，通常会触发 UI 树重绘（`Choreographer::doFrame`）。当 App 的渲染线程（RenderThread）将包含此次 UI 变更的图形缓冲区（Graphic Buffer）提交给 SurfaceFlinger，并且 SurfaceFlinger 最终将其**送显到物理屏幕 (Present)** 后，图形管道会向底层的 `InputChannel` 补发一条 `Timeline` 类型的消息。
*   **作用：** `Dispatcher` 将这条包含精准时间戳的消息交给 `mLatencyTracker`（延迟追踪器）。

### 2. LatencyTracker：拼接端到端时间线
`LatencyTracker` 负责将散落在系统各个角落的时间戳通过唯一的 `inputEventId` 拼接成一条完整的故事线：

1.  **内核读取时间 (ReadTime)：** `EventHub` 从 `/dev/input` 读到硬件中断的时间。
2.  **派发时间 (DispatchTime)：** `InputDispatcher` 将事件写入 Socket 的时间。
3.  **App 消费时间 (ConsumeTime)：** App 主线程开始处理该事件的时间。
4.  **送显时间 (GraphicsTimeline / PresentTime)：** GPU 完成渲染并由 Display Controller 点亮屏幕的时间（由 `Timeline` 信号带回）。

通过计算 **`PresentTime - ReadTime`**，系统就能得出精确到纳秒级的端到端触控延迟。如果该延迟频繁超过阈值（如 30ms-50ms，导致用户感觉“不跟手”或“掉帧”），系统底层（如 Perfetto/Systrace 埋点）就会将其记录为 Jank（卡顿）指标，供系统开发者进行图形栈或输入栈的性能调优。

### 3. Finished 与 Timeline 信号双轨时序图及埋点上报

为了更直观地展现从事件分发到“取消 ANR”，再到“计算端到端延迟”乃至“触发底层埋点上报”的全过程，我们绘制了如下的时序图。图中明确区分了 App 的 **UI 主线程**和 **RenderThread 渲染线程**，同时揭示了一个极其精妙的设计：**当前事件的最终耗时清算，往往是由下一个新事件的到来（作为时钟驱动）触发的**。

```mermaid
sequenceDiagram
    autonumber
    
    box LightYellow System Server
    participant Disp as InputDispatcher
    participant Tracker as LatencyTracker
    participant Aggregator as LatencyAggregator
    end
    
    box LightBlue App Process (JNI & UI)
    participant Receiver as NativeInput<br>EventReceiver
    participant UI as ViewRootImpl<br>(UI Thread)
    end
    
    box LightGreen App Process (Render)
    participant HWUI as HWUI /<br>RenderThread
    end
    
    participant SF as SurfaceFlinger
    participant StatsD as StatsD 服务

    %% --- 1. 事件分发与 ANR 倒计时 ---
    rect rgb(240, 240, 240)
    Note over Disp, Receiver: 1. 事件分发与 ANR 防线
    Disp ->> Disp: 开启 5s ANR 倒计时
    Disp ->> Receiver: Socket write (MotionEvent)
    Receiver ->> UI: JNI call: dispatchInputEvent()
    UI ->> UI: 遍历 View 树 (onTouchEvent等)
    UI -->> Receiver: JNI call: finishInputEvent(handled)
    Receiver ->> Disp: Socket write (Type::FINISHED)
    Disp ->> Disp: handleReceiveCallback()
    Note right of Disp: 调用 finishDispatchCycleLocked()<br>撤销 5s ANR 倒计时
    end

    %% --- 2. 渲染流水线与送显 (Present) ---
    rect rgb(240, 240, 240)
    Note over UI, SF: 2. 渲染流水线与送显 (Present)
    UI ->> HWUI: Choreographer::doFrame() 提交渲染树
    HWUI ->> HWUI: GPU 光栅化绘制 (GpuCompletedTime)
    HWUI ->> SF: 提交 Graphic Buffer (queueBuffer)
    SF -->> HWUI: Vsync 通知物理屏幕已送显 (PresentTime)
    end

    %% --- 3. Timeline 延迟信号回传 ---
    rect rgb(240, 240, 240)
    Note over Disp, HWUI: 3. Timeline 延迟信号回传
    HWUI ->> Receiver: InputFrameMetricsObserver::notify()
    Note right of Receiver: 提取 inputEventId,<br>gpuCompletedTime, presentTime
    Receiver ->> Receiver: enqueueTimeline()
    Receiver ->> Disp: Socket write (Type::TIMELINE)
    Disp ->> Disp: handleReceiveCallback()
    Disp ->> Tracker: trackGraphicsLatency()
    Note right of Tracker: 保存 PresentTime，完善当前事件的 Timeline
    end

    %% --- 4. 结算与埋点上报 (由下一个事件驱动) ---
    rect rgb(240, 240, 240)
    Note over Disp, StatsD: 4. 结算与埋点上报 (由下一个新事件驱动)
    Disp ->> Tracker: 收到下一个新事件: notifyMotion() / notifyKey() -> trackListener()
    Tracker ->> Tracker: reportAndPruneMatureRecords()
    Note right of Tracker: 检查老事件的 Timeline 是否成熟(已收集齐全或超时)
    Tracker ->> Aggregator: processTimeline()
    Aggregator ->> Aggregator: processStatistics()<br>计算并记录 7 段切片耗时
    Aggregator ->> Aggregator: processSlowEvent()<br>检查端到端延迟是否超标
    opt 超过 sSlowEventThreshold 且满足汇报间隔
        Aggregator ->> StatsD: stats_write(SLOW_INPUT_EVENT_REPORTED)
    end
    end
```

### 4. 关键疑问：是不是所有的 Touch 事件都会触发 TIMELINE？
**答案是：绝对不会。** 

`Timeline` 信号的本质是 **“UI 渲染流水线的反馈”**，只有当这个 Input 事件真实地导致了屏幕画面的改变**时，才会产生 `Timeline`。以下几种情况，App 只会回写 `Finished`，但**永远不会回写 `Timeline`：

1.  **没有触发 UI 重绘 (No Invalidation)：** 比如你在一个已经滑到底部的列表继续往下划，或者点击了一个没有任何点击效果的空白区域。App 的 `onTouchEvent` 会正常消费事件并返回 `Finished`，但由于没有调用 `invalidate()` 或 `requestLayout()`，`Choreographer` 不会安排新一帧的绘制，RenderThread 也就不会向 SurfaceFlinger 提交 Graphic Buffer，自然就没有 `Timeline` 回调。
2.  **事件被积攒合并 (Batching)：** 屏幕的报点率（如 120Hz）往往高于屏幕的刷新率（如 60Hz）。在两次 Vsync 信号之间，App 可能会收到多个 `ACTION_MOVE`。出于性能考虑，系统会将这些微小的 Move 事件合并。只有在这批合并事件的最后，UI 决定重绘时，才会对应产生一次 `Timeline`。
3.  **事件未被消费 (Unhandled)：** 如果所有的 View 都不拦截处理这个事件，它最终被抛弃或交由系统的 Fallback 逻辑处理，当前 App 的渲染管道根本不会介入，因此也不会有 `Timeline`。

这也是为什么在 Systrace/Perfetto 性能抓取分析中，我们只关心那些 **“有效触发了重绘的 Input 事件”** 的端到端延迟。`LatencyTracker` 在底层也会维护一个清理机制（如通过队列长度或时间过期淘汰），防止那些永远等不到 `Timeline` 的孤儿事件造成内存泄漏。

### 3. 延迟切片计算与埋点输出 (LatencyAggregator)
`LatencyTracker` 收集齐一帧完整的时间线后，会交由 `LatencyAggregator`（或 Android 14 引入的带有直方图的 `LatencyAggregatorWithHistograms`）进行处理。这是系统真正进行“耗时算账”的核心现场。在 `processStatistics` 方法中，系统会对整个链路进行**剥洋葱式的切片计算**，精准查出到底是哪一层导致了不跟手：

*   **硬件层耗时 (`eventToRead`)：** 内核读到驱动中断，距离事件实际发生的时间。
*   **系统输入框架耗时 (`readToDeliver`)：** Dispatcher 把事件发给 App，距离读到中断的时间。
*   **App 调度耗时 (`deliverToConsume`)：** App 主线程开始处理事件，距离 Dispatcher 发给它的时间。
*   **App 主线程逻辑耗时 (`consumeToFinish`)：** App 执行 `onTouchEvent` 等逻辑耗费的时间。
*   **App 渲染引擎耗时 (`consumeToGpuComplete`)：** HWUI/RenderThread 绘制完一帧画面提交给 GPU 的耗时。
*   **系统显示框架耗时 (`gpuCompleteToPresent`)：** SurfaceFlinger 图层合成并最终点亮物理屏幕 (Present) 的耗时。
*   **端到端延迟 (`endToEnd`)：** 屏幕真正点亮，距离用户最初按下的总耗时。

计算完成后，为了不影响性能，这些切片数据会被聚合进统计草图 (Sketches) 或直方图 (Histograms) 中，并通过 **StatsD** 服务批量上报为 `INPUT_EVENT_LATENCY_SKETCH` 原子指标。
同时，如果计算出的端到端延迟 (`endToEndLatency`) 超过了系统规定的阈值，`processSlowEvent` 方法会单独触发一次名为 `SLOW_INPUT_EVENT_REPORTED` 的高优埋点记录。

### 4. 如何查看 Input 延迟监控指标？

这些底层的性能埋点数据，是供开发者分析卡顿 (Jank) 和跟手性的核心资产。获取它们的方法主要分为命令行排查和代码级订阅两种：

#### 方式一：使用 dumpsys statsd 或 Perfetto (排查与分析)
系统会将收集到的原子指标 (Atoms) 存储在底层 statsd 服务中。你可以通过命令行快速查看：

```bash
# 查看所有被 statsd 记录的缓慢输入事件 (SLOW_INPUT_EVENT_REPORTED)
adb shell cmd stats print-stats | grep -i SLOW_INPUT_EVENT_REPORTED

# 获取 statsd 服务的详细状态和配置
adb shell dumpsys statsd
```

> **专家建议：** 纯文本的 StatsD 数据难以直观分析。Google 官方强推使用 **Perfetto (ui.perfetto.dev)** 抓取系统 Trace。当你在 Perfetto 中勾选了 `Input` 和 `Graphics` 数据源后，Perfetto 会在后台自动提取上述埋点，并在时间轴的 Input 轨道上直接将这些“延迟切片”以可视化的红绿块展示出来，让你一眼看出是哪一层的耗时导致了掉帧。

#### 方式二：通过代码编程订阅 (StatsManager API)
如果你正在开发性能监控 SDK、车机诊断工具或自动化压测框架，可以通过 Android 提供的 `StatsManager` API 编程订阅这些底层的 C++ 指标：

1. **Pull 方式拉取聚合草图 (`INPUT_EVENT_LATENCY_SKETCH`)：**
   由于聚合数据是积攒的，可以在系统级应用中注册 `OnPullAtomCallback` 定期拉取：
   ```java
   StatsManager statsManager = context.getSystemService(StatsManager.class);
   statsManager.setPullAtomCallback(
       FrameworkStatsLog.INPUT_EVENT_LATENCY_SKETCH,
       null, // metadata
       Executors.newSingleThreadExecutor(),
       (atomTag, data) -> {
           // data 列表中包含拉取到的序列化直方图/草图字节流
           // 解析返回的聚合草图数据，评估过去一段时间的整体跟手性
           return StatsManager.PULL_SUCCESS;
       }
   );
   ```

2. **Push 方式监听慢事件 (`SLOW_INPUT_EVENT_REPORTED`)：**
   慢事件属于即时触发的 Push 型指标。你需要通过 `StatsManager.addConfig()` 向 statsd 下发一个包含了匹配规则（Matcher）的 `StatsdConfig`（通常是 protobuf 格式），并注册一个 `PendingIntent`。
   当底层 `LatencyAggregator` 抛出 `SLOW_INPUT_EVENT_REPORTED` 时，statsd 会匹配规则，并通过 Broadcast 或 Service 唤醒你的 `PendingIntent`，你就能在代码里实时捕获到这次慢事件在“分发、消费、渲染、上屏”各个阶段的具体耗时数值了。


> **补充说明：按键事件的延迟追踪**
> 值得注意的是，除了触摸事件 (`notifyMotion`) 之外，`InputDispatcher::notifyKey()` 同样接入了这套延迟追踪体系。在源码中，如果开启了单设备输入延迟指标特性（`mPerDeviceInputLatencyMetricsFlag`），从实体按键（如音量键、电源键或外接键盘）产生的 `KeyEvent` 也会经过 `trackListener(args)`，参与端到端延迟的计算与打点。这对于车机方向盘按键或游戏手柄的响应调优同样至关重要。

### 5. 影响 Latency Tracking 的关键配置开关

在 `InputDispatcher` 的核心埋点代码中，有两个极其关键的变量会直接决定一个输入事件是否会被纳入端到端延迟的计算体系：`mInputFilterEnabled` 和 `mPerDeviceInputLatencyMetricsFlag`。

#### `mInputFilterEnabled` 与 `Source` 的联合守卫 (&&)
*   **作用：** 决定一个事件是否有资格进入端到端延迟追踪（`LatencyTracker`）。在 `InputDispatcher.cpp` 的入口处，系统通过一个极其严苛的联合条件来放行：
    `IdGenerator::getSource(args.id) == Source::INPUT_READER && !mInputFilterEnabled`
    
    这两道守卫是 **逻辑与 (&&)** 的关系，**任何一个不满足，都会跳过打点**：
    1. **`!mInputFilterEnabled`：** 只要挂载了无障碍过滤器，直接放弃测速。因为跨进程去 Java 服务旅游一圈会导致生命周期极其失真。
    2. **`Source::INPUT_READER`：** 只有从底层硬件节点真实读上来的物理事件才配测速。像我们前面说的被 Filter 重新 `injectInputEvent` 进来的事件，由于 Source 变成了 `OTHER`，即使第一道守卫放行，也会被这第二道守卫无情拦截。
*   **默认值与触发：** 默认为 `false`。只有当用户在系统设置中手动开启了需要接管全局事件的无障碍功能时，Java 层的 `InputManagerService` 才会向下跨进程将其置为 `true`。

#### `mPerDeviceInputLatencyMetricsFlag` (精细化外设延迟监控开关)
*   **作用：** 这是 Android 14/15 引入的一个极具价值的性能诊断特性。在过去的版本中，系统的输入延迟埋点是“一锅炖”的（屏幕滑动的延迟和外接蓝牙手柄的延迟被混在一起算平均值，导致难以排查）。而当这个 Flag 开启后，系统底层会执行两项重大改变：
    1.  **全面纳入按键事件：** 不仅追踪屏幕触摸事件（`notifyMotion`），还会额外把所有实体按键事件（`notifyKey`，如音量键、车机旋钮、游戏手柄按键）也一并纳入延迟追踪的生命周期。
    2.  **启用直方图与设备隔离：** 处理器会从旧版的普通聚合器切换为带有直方图且按厂商 ID (Vendor ID) / 产品 ID (Product ID) 区分的高精度统计类（`LatencyAggregatorWithHistograms`）。这对于智能座舱中多外设并发的精准调优极其关键。
*   **默认值与设置方法：** 
    该变量由 AOSP 的 `aconfig` 特性框架控制（定义在 `input_flags.aconfig` 的 `enable_per_device_input_latency_metrics` 标志中）。根据 aconfig 约定，其默认状态通常为 `DISABLED`（即 `false`），是否启用由各 Release Config 或产品决定（在部分高配机型或如上述调查报告中的 H47A 车机上，该选项实际被启用了）。
    
    > **⚠️ 源码不对称陷阱：** 在 `InputDispatcher.cpp` 的原生源码中，`notifyKey` 路径的 `trackListener` 被包裹在这个 `mPerDeviceInputLatencyMetricsFlag` 的条件判断中；但在早期的 AOSP `notifyMotion` 路径中却**没有**包裹这层 Flag。这个不对称的坑曾经误导了大量开发者。
    **如何在工程机上强行开启：** 测试人员或开发者可以通过 ADB 动态修改 `device_config` 命名空间来开启这个特性，以便在压测时抓取精细化数据：
    ```bash
    # 开启精细化按设备区分的输入延迟监控
    adb shell device_config put input_native_boot enable_per_device_input_latency_metrics true
    # 重启 Android Framework 服务生效
    adb shell stop && adb shell start
    ```

### 6. 专家级调试技巧：动态调整 SLOW_EVENT 判定阈值

在上文提到的 `SLOW_INPUT_EVENT_REPORTED` 慢事件埋点中，系统底层默认有两个硬编码的限制：

1. **触发阈值 (Threshold)：默认 200ms**
   只有当一个触摸事件的端到端总延迟 (`endToEndLatency`) 大于 200 毫秒时，系统才认为这是一次“严重卡顿 (Jank)”并触发埋点。
2. **上报冷却时间 (Reporting Interval)：默认 60000ms (1 分钟)**
   为了防止某个 App 突然抽风导致底层疯狂打埋点拖垮性能，系统做了一个“1分钟漏斗”。如果距离上一次上报还不到 1 分钟，后续即使再出现超过 200ms 的慢事件，系统也会静默跳过。

**如何在压测时打破这些限制？**

这两个硬编码的默认值其实是由 Android 的 `Device Config` (server_configurable_flags) 机制包裹的。这意味着我们可以**不修改 C++ 源码、不重新编译系统**，直接通过 ADB 动态调整这些底层参数！

如果你正在进行极其严格的跟手性压测（例如想把所有超过 50ms 的轻微掉帧事件全抓出来），并且希望每次卡顿必定上报（关闭 1 分钟冷却期），你只需要在终端执行以下命令：

```bash
# 1. 把阈值从默认的 200ms 降为 50ms（极其严格的跟手性测试！）
adb shell device_config put input_native_boot slow_event_min_reporting_latency_millis 50

# 2. 把上报冷却时间从 1分钟 (60000) 降为 0（关掉冷却，有卡必报）
adb shell device_config put input_native_boot slow_event_min_reporting_interval_millis 0

# 3. 强制重启 Android Framework 让参数立即生效
adb shell stop && adb shell start
```

结合我们在底层源码（`LatencyAggregator.cpp`）中自行添加的 `ALOGW` 蜗牛报警日志，修改这两个参数后，你就能在 `logcat` 中极其敏锐、无遗漏地抓出所有掉帧窗口和耗时明细，是智能座舱与高刷手机性能调优的终极利器！

## InputDispatcher 事件入队与拦截过滤时序 (Inbound Flow)

`InputDispatcher` 不仅负责将事件派发给具体的 App 窗口，它还是系统级按键拦截（如电源键亮屏）和无障碍辅助服务（Accessibility）截获事件的核心关卡。

不论事件是由底层的 `InputReader` 读取产生的（`notifyKey`, `notifyMotion`），还是来自上层组件的软件模拟注入（`injectInputEvent`），它们在真正进入 `InboundQueue` 之前，都必须经过极其严密的拦截与过滤流程。

### 1. 按键事件 (notifyKey) 入队与拦截时序图

按键事件（如电源键、音量键、物理键盘）具有极高的特权要求，必须在入队排队前进行系统级的拦截判定，以确保诸如“长按电源键关机”等核心交互不被前台卡顿的 App 阻塞。

```mermaid
sequenceDiagram
    autonumber
    
    box LightCyan InputReader Thread (Native)
    participant Reader as InputReader<br>及 Listener Chain
    end
    
    box LightYellow System Server (Dispatcher Thread)
    participant Disp as InputDispatcher
    participant Policy as NativeInputManager
    participant PWM as PhoneWindowManager<br>(Java)
    end
    
    box LightPink App / System Components
    participant JavaFilter as InputFilter<br>(Accessibility 等)
    end
    
    participant Queue as InboundQueue

    Note over Reader, PWM: 1. 硬件读取与 PhoneWindowManager 特权拦截
    Reader ->> Disp: notifyKey()
    Note right of Disp: 此时无锁 (No mLock)，防止阻塞 Reader 线程
    Disp ->> Policy: interceptKeyBeforeQueueing()
    Policy ->> PWM: JNI: interceptKeyBeforeQueueing()
    Note right of PWM: 处理特权按键<br>(如电源键亮屏、音量键调节)
    PWM -->> Policy: 返回 policyFlags
    Policy -->> Disp: 决定是否放行或转为虚拟键

    %% --- 2. 无障碍拦截与过滤 (InputFilter) ---
    rect rgb(240, 240, 240)
    Note over Disp, JavaFilter: 2. 检查全局输入过滤器 (mInputFilterEnabled)
    Disp ->> Disp: mLock.lock()
    alt 启用了全局无障碍过滤器
        Disp ->> Disp: shouldSendKeyToInputFilterLocked() == true
        Disp ->> Disp: mLock.unlock() // 【防死锁释放】
        Disp ->> Policy: filterInputEvent()
        Policy ->> JavaFilter: 跨进程 Java 过滤
        JavaFilter -->> Policy: return true(放行) 或 false(拦截)
        Policy -->> Disp: boolean result
        Disp ->> Disp: mLock.lock() // 【重新上锁】
        Note right of Disp: 若被拦截，提前 return 吞噬事件
    end
    end

    %% --- 3. 入队排队 ---
    Note over Disp, Queue: 3. 延迟打点与排队
    Disp ->> Disp: mLatencyTracker.trackListener()
    Note right of Disp: 仅开启 mPerDeviceInputLatencyMetricsFlag 且未被过滤时统计
    Disp ->> Queue: enqueueInboundEventLocked()
    Disp ->> Disp: mLooper->wake()
    Note right of Disp: 唤醒 Dispatcher Thread 分发
    Disp ->> Disp: mLock.unlock()
```

### 2. 触摸与注入事件 (notifyMotion & injectInputEvent) 时序图

触摸事件（Motion）与按键事件最大的区别在于：它不需要经过 `PhoneWindowManager` 的 `interceptKeyBeforeQueueing` 特权拦截，但它依然需要接受无障碍服务的过滤。同时，无障碍服务或测试框架经常会通过 `injectInputEvent` 软件注入来模拟触摸。

```mermaid
sequenceDiagram
    autonumber
    
    box LightCyan Native Threads
    participant Reader as InputReader<br>Thread
    participant Injector as Injector Thread<br>(Binder IPC)
    end
    
    box LightYellow System Server (Dispatcher)
    participant Disp as InputDispatcher
    participant Policy as NativeInputManager
    end
    
    box LightPink App / System Components
    participant JavaFilter as InputFilter<br>(Accessibility 等)
    participant A11y as AccessibilityService
    end
    
    participant Queue as InboundQueue

    %% --- 1. 硬件触摸事件入口 ---
    Note over Reader, Disp: 1. 硬件触摸事件入口 (无 BeforeQueueing)
    Reader ->> Disp: notifyMotion()
    
    %% --- 2. 无障碍拦截与重注入闭环 ---
    rect rgb(240, 240, 240)
    Note over Disp, JavaFilter: 2. 无障碍拦截与全局手势识别
    Disp ->> Disp: mLock.lock()
    alt 启用了全局无障碍过滤器 (TalkBack等)
        Disp ->> Disp: shouldSendMotionToInputFilterLocked() == true
        Disp ->> Disp: mLock.unlock() // 【防死锁释放】
        Disp ->> Policy: filterInputEvent()
        Policy ->> JavaFilter: 跨进程 Java 过滤
        
        alt 判定为无障碍手势 (如三指滑动)
            JavaFilter -->> Policy: return false (拦截)
            Policy -->> Disp: return false
            Note over Disp: 物理事件在底层被彻底吞噬！
            
            %% 闭环：重新注入
            JavaFilter ->> A11y: 触发相应的 Accessibility 业务逻辑
            Note over A11y, Injector: 服务处理完毕后，可能生成新事件接管系统输入
            A11y ->> Injector: injectInputEvent() (Java API)
        else 普通滑动放行
            JavaFilter -->> Policy: return true (放行)
            Policy -->> Disp: return true
            Disp ->> Disp: mLock.lock() // 【重新上锁】
        end
    end
    end

    %% --- 3. 软件注入入口 (Injection) ---
    Note over Injector, Disp: 3. 软件注入入口 (绕过 Reader 和 Filter)
    Injector ->> Disp: injectInputEvent() (Binder IPC)
    Note right of Disp: 携带 targetUid, syncMode 等<br>来自 Monkey、自动化测试或 A11y
    Disp ->> Disp: mLock.lock()

    %% --- 4. 延迟追踪与入队 ---
    Note over Disp, Queue: 4. 延迟打点与排队
    Disp ->> Disp: mLatencyTracker.trackListener(args)
    Note right of Disp: 【注意】Inject事件无资格打点 (需 Source::INPUT_READER)
    Disp ->> Queue: enqueueInboundEventLocked()
    Disp ->> Disp: mLooper->wake()
    Disp ->> Disp: mLock.unlock()
```

### 3. 核心审查机制解析

#### A. 发送源头纠正：硬件并不是直接调用 Dispatcher
在真实的架构中，硬件驱动产生中断后，并不是直接调用 `notifyKey`。而是由我们前文提到的 `InputReader` 的死循环提取事件，并途经 `UnwantedInteractionBlocker`、`InputProcessor` 等多道工序的 Listener 责任链后，由**责任链的最后一环**（即 `InputDispatcher` 实现的 Listener 接口）接收到加工好的 `NotifyArgs`。

#### B. 为什么要有 `interceptKeyBeforeQueueing` 与 `PhoneWindowManager`？
对于按键事件（尤其是电源键、音量键或 Home 键），系统需要做到**“即时响应”**。如果将电源键放入 `InboundQueue` 中，万一此时队列前方积压了大量导致应用卡顿的滑动事件，系统就会出现“按下电源键却迟迟不亮屏”的致命体验。
因此，`InputDispatcher::notifyKey` 在**获取 `mLock` 之前**（即无锁、不会被阻塞的极早期阶段），会率先通过 `mPolicy` 调用 Java 层的 `PhoneWindowManager::interceptKeyBeforeQueueing`。在这里，Android 框架会最优先执行唤醒屏幕、特权系统按键截获的逻辑，从而实现了按键的最高优处理。

#### C. `filterInputEvent` 拦截与再次 `inject` 回溯闭环
`InputFilter` 是专为无障碍服务（如 TalkBack 盲人模式）设计的。当开启 TalkBack 时，你滑动的轨迹并不是直接发给桌面的，而是必须经过 Java 层的 `InputFilter` 过滤。
*   **跨进程防死锁锁避让：** `filterInputEvent` 会跨进程调用 Java 层的代码。如果 `InputDispatcher` 握着全局的 `mLock` 去调用它，一旦 Java 层卡顿，整个 C++ 层的触控线程池将瞬间死锁。因此，源码在调用前执行了神级的 `mLock.unlock()`，等 Java 层判定完毕返回后再重新 `mLock.lock()`。
*   **消费与再次注入：** 如果 TalkBack 判定这是一个需要拦截的手势，它会返回 `false`，导致 `notifyMotion` 直接 `return`（也就是**事件在底层被吞噬了**）。随后，无障碍服务在完成自身的业务逻辑（例如将三指滑动转义为某项操作）后，**它可能会主动调用框架层的 API，通过 `injectInputEvent` 将一个新的（或修改过的）事件强行注入回 `InputDispatcher`，以此来接管整个系统的输入流。**

#### D. 软件注入后门 (`injectInputEvent`)
不仅是无障碍服务，当你使用 `adb shell input tap x y`、自动化测试框架 (`Instrumentation`) 或者是自动化压测工具 (Monkey) 时，事件根本不会经过底层的硬件驱动读取。它们通过 Binder IPC 直接调用 `InputDispatcher::injectInputEvent`。
在注入方法内部，系统会跳过 `interceptKeyBeforeQueueing` 和 `filterInputEvent` 的拦截，构造一个带有特殊 `policyFlags` 的 `InjectionState` 并直接塞进 `InboundQueue`。这也就是为什么我们在上一节的 Latency Tracking 源码中看到：**只有 `Source::INPUT_READER` 来源的事件才有资格被计入端到端延迟统计**，而这类 Inject 注入的事件则不配拥有测量性能的资格。

### 4. 深度调查案例：车机环境下 Touch 事件被全部 Filter 拦截的现象与影响

在部分定制化 Android 系统（特别是 Android Automotive 车机系统）中，可能会出现一种极端现象：**所有的真实触摸事件均被 `InputFilter` 拦截处理，随后又通过软件注入（`injectInputEvent`）的方式重新派发。**

此现象导致了系统输入性能监控的失效，使得 `SLOW_INPUT_EVENT_REPORTED` 埋点无法正常采集数据。

#### 现象还原 (基于 dumpsys input 调查)
通过观察 `dumpsys input`，可以发现以下非预期状态：
1. **`InputFilterEnabled: true`**：系统持续开启全局辅助输入过滤器。
2. **`RecentQueue` 中的事件 PolicyFlags 异常**：
   ```text
   MotionEvent(deviceId=2, ... policyFlags=0x67000000, ...)
   ```
   其中 `0x67000000` 包含了 `POLICY_FLAG_INJECTED` 标志。这表明当前 `Dispatcher` 正在分发的并非 `InputReader` 直接读取的原始硬件事件，而是经过 Java 层重定向并重新注入的事件。

#### 业务场景诱因
在多屏车机环境（如主驾与副驾独立交互）中，OEM 厂商为快速实现复杂的业务策略，常常选择在全局 `InputFilter` 中集中处理逻辑：
1. **驾驶安全策略限制（Driver Distraction Mitigation）：** 行驶中需要动态屏蔽部分屏幕（如中控特定交互区）的触摸输入。
2. **座舱多屏动态路由：** 需根据副驾乘员状态及应用层叠关系，动态修改事件所属的逻辑屏幕 ID (DisplayId)。
3. **全局手势与防误触：** 譬如三指滑动控制空调、方向盘物理按键的全局重映射等。

基于 AOSP 现有架构，OEM 的 `InputManagerService` (IMS) 通常会注册一个底层 `IInputFilter`。当底层的真实事件抵达 `notifyMotion` 时，针对**每个** `ACTION_MOVE` 都会触发 `filterInputEvent()` 并回调至 Java 层；Java 层在完成业务判定后将原事件标记为已消费（导致底层 `return`），随后修改其坐标或显示器 ID，并调用 `injectInputEvent` 将其重新推入 C++ 派发管线。

#### 此架构设计的技术影响

这种“全局拦截与重新注入”的模式虽能迅速满足业务需求，却在底层框架层面上引发了显著的性能与观测问题：

1. **跨语言调用的隐性开销（实测附加延迟 < 2ms）：** 触摸滑动操作每秒可产生逾 120 个中断数据包。原本完全在 C++ 层内完成的派发流水线，现在被迫对每个事件包执行 JNI 回调与 Java 层对象分配。需要客观指出的是：**根据车机实测压测数据，这种 `filter + inject` 路径引入的绝对耗时极短（通常不到 2ms）**，并不会直接导致肉眼可见的物理掉帧。然而，它毫无必要地增加了 System Server 的 GC 压力、对象分配频率以及线程唤醒开销。
2. **`inputEventId` 关联断裂与监控失效：** 原始硬件中断的生命周期（ID 记为 A）在被 Filter 拦截时即告终止。随后注入的新事件（ID 记为 B）其 `Source` 属性变为 `OTHER`，且与事件 A 失去任何逻辑关联。这种割裂导致 `LatencyTracker` 无法闭环端到端时间线，**致使系统的触控性能大盘（包括 `SLOW_INPUT_EVENT_REPORTED`）彻底失效，成为性能调优时的盲区。**
3. **`eventTime` 精度损失：** 注入事件的 `eventTime` 变为注入动作发生的时间点，而非手指真实接触屏幕的硬件时间。这会使得依赖高精度时间差的框架层算法（如 `VelocityTracker` 的滑动速度计算、Compose 的运动预测渲染）产生误差。

#### 架构重构建议

针对上述问题，建议在系统架构审查与迭代时考虑以下重构方案：

1. **方案 A（监控层修复）：在注入时回传原始 ID 链条**
   修改 Java 层的 InputFilter 框架及 `injectInputEvent` 的 JNI 入口。当服务重新注入事件时，**强制继承原始的 `inputEventId` 与原生 `eventTime`**，并在底层的注入入口处显式触发一次 `mLatencyTracker.trackListener()`，以此弥补链路断层，恢复端到端性能统计。
2. **方案 B（架构层优化）：Native Hook 与按需拦截 (推荐)**
   *   **基础策略下沉：** 将“事件丢弃”或“屏幕路由”等轻量级判定逻辑，直接以 C++ 实现在 `NativeInputManager::interceptMotionBeforeQueueing` 中。
   *   **按需拦截机制 (Short-circuit)：** 优化 Java 层判定逻辑，使其仅在极少数特定条件（如特定车速与特定触摸区域）下返回 `false` 予以拦截。对于占绝大比例的正常 UI 交互，**应以极低延迟返回 `true`（放行）**，确保原生物理事件正常经过 C++ 派发管线。

### 5. 源码剖析：InputFilter 开启与 LatencyTracker 失效的根因

根据前文分析，只要 `mInputFilterEnabled` 状态为 `true`，底层的 `LatencyTracker` 即停止追踪。通过追溯 `frameworks/base` 的源码实现，我们可以明确触发该状态的业务源头。

在 Android 框架中，全局 `InputFilter` 的合法持有者与调用源仅为一个：**`AccessibilityManagerService` (无障碍管理器服务)**。

#### 追踪调用链 (Call Stack)
从 C++ 层的 `NativeInputManager::setInputFilterEnabled` 向上追溯至 Java 层，调用关系如下：
1. `InputManagerService.java` -> `setInputFilter(IInputFilter filter)`
2. `WindowManagerService.java` -> `setInputFilter(IInputFilter filter)`
3. **唯一触发端：** `AccessibilityManagerService.java` -> `updateInputFilter(AccessibilityUserState userState)`

#### `updateInputFilter` 的触发逻辑
在 `AccessibilityManagerService.java` 中，系统会汇集所有的无障碍权限状态标志 (flags)。只要当前运行的任何一个无障碍服务（Accessibility Service）申请了以下**任意权限**，系统即会实例化并挂载全局 `InputFilter`：

```java
int flags = 0;
// 1. 启用了屏幕放大功能 (单指三击 / 双指三击)
if (userState.isMagnificationSingleFingerTripleTapEnabledLocked()) {
    flags |= AccessibilityInputFilter.FLAG_FEATURE_MAGNIFICATION_SINGLE_FINGER_TRIPLE_TAP;
}
// 2. 启用了“触摸浏览”模式 (TalkBack 核心功能)
if (userState.isHandlingAccessibilityEventsLocked() && userState.isTouchExplorationEnabledLocked()) {
    flags |= AccessibilityInputFilter.FLAG_FEATURE_TOUCH_EXPLORATION;
}
// 3. 申请了按键事件拦截权限
if (userState.isFilterKeyEventsEnabledLocked()) {
    flags |= AccessibilityInputFilter.FLAG_FEATURE_FILTER_KEY_EVENTS;
}
// 4. 申请了全局手势执行与注入权限
if (userState.isPerformGesturesEnabledLocked()) {
    flags |= AccessibilityInputFilter.FLAG_FEATURE_INJECT_MOTION_EVENTS;
}

// 若 flags 不为 0，则注册并挂载 InputFilter
if (flags != 0) {
    if (!mHasInputFilter) {
        mHasInputFilter = true;
        mInputFilter = new AccessibilityInputFilter(mContext, AccessibilityManagerService.this);
        setInputFilter = true;
    }
}
// 跨进程通知 C++ 层的 InputDispatcher，将 mInputFilterEnabled 置为 true
if (setInputFilter) {
    mWindowManagerService.setInputFilter(inputFilter); 
}
```

#### 在车机系统 (AAOS) 中的普遍性
在标准移动设备上，普通用户极少长期开启 TalkBack 等服务，因此 `mInputFilterEnabled` 通常为 `false`，`LatencyTracker` 运行处于正常状态。

然而，在智能座舱开发中，OEM 开发人员往往需要实现超越单个应用生命周期的全局级交互，例如：
*   **方向盘硬按键接管：** 拦截特定物理按键并转换为系统级别的指令广播。
*   **全局手势识别：** 监听三指滑动以实时调节空调或音量。
*   **输入隔离策略：** 根据特定业务状态屏蔽副驾显示器的输入。

为满足上述需求，系统级应用（如 SystemUI 或定制化后台服务）通常会注册一个**开机自启动且对用户透明的 Accessibility Service**，并在 `AndroidManifest.xml` 中声明 `<accessibility-flags>flagRequestFilterKeyEvents</accessibility-flags>` 权限。

**结论：**
正是由于此类常驻无障碍服务的存在，导致 `AccessibilityManagerService` 长期将全局 `InputFilter` 挂载，进而使得 `InputDispatcher` 的 `mInputFilterEnabled` 变量被置为 `true`。这就导致了所有由硬件产生的原始中断事件，在 `trackListener` 处理逻辑中因条件不满足而无法进入延迟统计环节，导致了整车端到端输入延迟监控机制的停滞。


#### 实战排查：如何定位触发 InputFilter 的无障碍服务？

在线上排查 `SLOW_INPUT_EVENT_REPORTED` 埋点失效，或是发现 `dumpsys input` 中 `InputFilterEnabled` 为 `true` 时，可以通过以下系统级 ADB 命令，直接追踪到是哪一个后台应用或系统服务申请了特权，从而锁定了底层监控瘫痪的真正元凶：

1. **查看系统激活的无障碍服务名单 (Settings Provider)：**
   ```bash
   adb shell settings get secure enabled_accessibility_services
   ```
   *输出示例：`com.crystal.h37.arservice/.MyA11yService:com.voyah.cockpit/.CockpitService`*
   （冒号分隔的即为当前处于激活状态的无障碍服务包名与类名组合）。

2. **查看当前绑定的无障碍服务及其权限详情：**
   ```bash
   adb shell dumpsys accessibility | grep -i -A 20 "Bound services"
   ```
   在此输出结果中，重点观察 `capabilities` 和 `flags` 字段。如果看到 `capabilities` 包含了 `CAPABILITY_CAN_PERFORM_GESTURES` (允许执行手势)，或者 `flags` 包含了 `FLAG_REQUEST_FILTER_KEY_EVENTS` (请求按键过滤)，即可实锤正是该服务在底层强制要求 `AccessibilityManagerService` 挂载了 `InputFilter`。


### 5.5. 深度解剖：InputFilter 与无障碍服务架构图

为了清晰展现事件是如何从底层的 C++ 管线“逃逸”到 Java 层，又如何经过复杂的业务链条被评估甚至篡改的，我们绘制了如下的 **InputFilter 核心架构图**。

这幅架构图涵盖了从 Native C++ 到 Java 框架层，再到第三方 App 的完整拓扑结构，以及著名的 `EventStreamTransformation` 事件流转换加工链。

```mermaid
flowchart LR
    %% 样式定义
    classDef native fill:#dae8fc,stroke:#333,stroke-width:1px;
    classDef java fill:#ffe6cc,stroke:#333,stroke-width:1px;
    classDef a11y fill:#e1d5e7,stroke:#333,stroke-width:1px;
    classDef jni fill:#f8cecc,stroke:#333,stroke-width:1px;

    subgraph NativeSpace [Native C++ 层 System Server]
        Reader[InputReader\n驱动读取]:::native
        Dispatcher[InputDispatcher\n事件分发器]:::native
        NativeIMS[NativeInputManager]:::native
    end

    subgraph JNISpace [JNI 跨语言边界]
        JNI_Filter[JNI: filterInputEvent]:::jni
        JNI_Inject[JNI: injectInputEvent]:::jni
    end

    subgraph JavaSpace [Java 框架层 System Server]
        IMS[InputManagerService]:::java
        
        subgraph FilterChain [AccessibilityInputFilter 责任链 EventStreamTransformation]
            direction TB
            A11yFilter[AccessibilityInputFilter]:::java
            Keyboard[KeyboardInterceptor\n按键拦截]:::java
            TouchExp[TouchExplorer\n触摸与全局手势]:::java
            Gesture[MagnificationGestureHandler\n屏幕放大]:::java
            Host[InputFilterHost\n链条终点]:::java
        end
        
        AMS[AccessibilityManagerService]:::java
    end

    subgraph AppSpace [用户进程域]
        TargetApp[前台焦点应用]:::a11y
        A11yService[AccessibilityService\n如 TalkBack, 车机防误触App]:::a11y
        
    end

    %% 流程关系
    Reader -- "1. notifyMotion" --> Dispatcher
    Dispatcher -- "2. 被锁定并移交" --> NativeIMS
    NativeIMS -- "3. 跨进程调用" --> JNI_Filter
    JNI_Filter --> IMS
    IMS -- "4. 无条件 return false\n(原生分发死亡)" --> NativeIMS
    NativeIMS -. "断开分发流" .-> Dispatcher

    IMS -- "5. 丢给 Filter 加工链" --> A11yFilter
    A11yFilter --> Keyboard
    Keyboard --> TouchExp
    TouchExp --> Gesture
    
    TouchExp -- "6. 广播事件给订阅者" --> AMS
    AMS -- "7. Binder IPC 实时推送" --> A11yService
    
    Gesture -- "8. 判定为正常滑动则放行" --> Host
    Host -- "9. 携带 FLAG_FILTERED\n强行重注入" --> JNI_Inject
    JNI_Inject --> NativeIMS
    NativeIMS -- "10. 变成新克隆事件入队" --> Dispatcher
    Dispatcher -- "11. 跨进程分发" --> TargetApp
```

#### 架构图核心组件解析

1. **NativeIMS (NativeInputManager)：** 它是 C++ 层与 Java 层沟通的桥梁。无论是向上汇报需要过滤的事件（`filterInputEvent`），还是接收 Java 层下达的注入命令（`injectInputEvent`），都要通过这道 JNI 关卡。
2. **FilterChain (EventStreamTransformation 责任链)：** 当事件进入 `AccessibilityInputFilter` 时，并不是用一个臃肿的方法处理完所有逻辑。Android 采用了一套名为 `EventStreamTransformation` 的流水线模式（Pipeline）。事件会依次穿过按键拦截器、触摸流探测器和放大手势处理器。任何一个环节觉得“这个操作我包了”（例如识别到了单指双击），就可以直接终止整条流水线（即“消费” Consumed）。
3. **AMS (AccessibilityManagerService) 的广播：** 责任链中的处理器（如 `TouchExplorer`）在分析轨迹的同时，会调用 AMS 的 `sendMotionEventToListeningServices`。AMS 会遍历所有已绑定的无障碍服务（比如车机 OEM 写的那个 `arservice`），通过 Binder 将坐标源源不断地推给它们，供它们执行上层的业务。
4. **Host (InputFilterHost)：** 这是流水线的终点。如果一个事件极其幸运，没有被任何拦截器判定为特殊手势，它最终会流到 `Host` 节点。`Host` 的唯一使命就是调用 JNI，将这个经历了九死一生的事件，作为“外部软件注入请求”重新塞回 `InputDispatcher`。

### 6. 机制推演：AccessibilityManagerService 的拦截与重注入时序

为了让你对上述的“架构骨刺”有一个最直观的体感，我们通过追踪 `frameworks/base` 和 JNI 的源码，精确绘制了当存在无障碍服务时，一个物理触控事件是如何经过 **C++ 拦截 -> Java 层责任链过滤 -> 分发至无障碍 App -> 再次通过 Binder 注入回 C++ 底层** 的完整生命周期。

这也完美解释了你在 `dumpsys input` 中看到所有事件均带有 `policyFlags=0x67000000` (包含 `INJECTED`, `FILTERED`) 的源码级真相。

```mermaid
sequenceDiagram
    autonumber
    
    box LightCyan Native 层 (C++)
    participant Disp as InputDispatcher
    participant NativeIMS as NativeInputManager
    end
    
    box LightYellow System Server (Java)
    participant IMS as InputManagerService
    participant A11yFilter as Accessibility<br>InputFilter
    participant Host as InputFilterHost
    participant AMS as Accessibility<br>ManagerService
    end
    
    box LightPink App Process
    participant A11yApp as AccessibilityService<br>(第三方/车机服务)
    participant App as 前台焦点 App
    end

    %% --- 1. C++ 层的拦截与强行掐断 ---
    rect rgb(255, 230, 230)
    Note over Disp, A11yFilter: 1. 物理管线的无条件阻断
    Disp ->> Disp: notifyMotion(args)
    Note right of Disp: 携带原始 inputEventId (A)<br>Source = INPUT_READER
    Disp ->> Disp: mLock.unlock()
    Disp ->> NativeIMS: filterInputEvent(event, policyFlags)
    NativeIMS ->> IMS: JNI: filterInputEvent()
    
    IMS ->> A11yFilter: mInputFilter.filterInputEvent()
    Note right of IMS: 关键源码揭秘：<br>只要挂载了 mInputFilter，<br>IMS 会在此立刻强制 return false！
    IMS -->> NativeIMS: return false
    NativeIMS -->> Disp: return false
    Note left of Disp: C++ 分发流程终止！<br>原始事件 (A) 的 LatencyTracker 追踪链彻底断裂。
    end

    %% --- 2. Java 层加工与评估阶段 ---
    rect rgb(240, 240, 240)
    Note over A11yFilter, AMS: 2. Java 层事件评估流水线 (EventStreamTransformation)
    A11yFilter ->> A11yFilter: 进入内部判定链 (TouchExplorer 等)
    
    alt 分发给注册了的无障碍应用
        A11yFilter ->> AMS: sendMotionEventToListeningServices(event)
        AMS ->> A11yApp: Binder Call: onMotionEvent()
        Note right of AMS: 车机的拦截 App (如 arservice) 此时收到了触摸坐标
    end

    A11yApp ->> A11yApp: 执行业务逻辑 (如防误触、手势识别)
    
    alt 判定为需要拦截的手势
        Note right of A11yFilter: 判定链终止，丢弃该事件，<br>不再向下调用 super.onInputEvent()
    end
    end

    %% --- 3. 重注入与“狸猫换太子” ---
    rect rgb(230, 255, 230)
    Note over A11yFilter, App: 3. 正常事件的重注入与“狸猫换太子” (Re-Injection)
    alt 判定为正常触摸 (放行)
        A11yFilter ->> Host: 判定链走到底，调用 super.onInputEvent()<br>触发 mHost.sendInputEvent(event, policyFlags)
        Host ->> NativeIMS: JNI: mNative.injectInputEvent(...)
        Note right of Host: 注入时强制追加标志位：<br>policyFlags | FLAG_FILTERED
        
        NativeIMS ->> Disp: injectInputEvent()
        Note right of Disp: 【致命身份转换】<br>1. 分配全新的 inputEventId (B)<br>2. 底层自动追加 POLICY_FLAG_INJECTED<br>3. Source 沦为 OTHER
        Disp ->> Disp: enqueueInboundEventLocked()
        Disp ->> App: 最终跨进程 Socket 派发给前台应用
        Note over App: 前台 App 顺利消费，但事件已是携带<br> INJECTED 和 FILTERED 标志的克隆体。
    end
    end
```

#### 从这幅时序图得出的残酷真相

1. **为什么无论是否拦截，原生事件必死？**
   在 `InputManagerService.java` 的源码实现中，它的 `filterInputEvent` 方法极其简单粗暴：只要 `mInputFilter != null`，它在把事件丢给 `mInputFilter.filterInputEvent()` 后，**会无条件直接 `return false;`**。
   这意味着不管上层无障碍服务最终要不要放行这个事件，原生的 C++ `notifyMotion` 管线在第一步就被强行掐断了。
2. **“放行”的本质其实是“重新注入”**
   如果 `AccessibilityInputFilter`（A11y的事件评估流水线）决定**放行**这次点击，它的做法并不是通知 C++ 恢复执行，而是走到流水线的尽头调用 `super.onInputEvent()`。
   这最终会调回 JNI 的 `injectInputEvent()`，把事件作为“外部软件注入请求”重新塞进 `InputDispatcher` 的 `InboundQueue` 中。**在 Android 架构下，经过 InputFilter 的事件，没有“生还者”，只有“克隆体”。**
3. **`0x67000000` 标志位的破译与性能陷阱**
   通过追踪图中第 3 步的重注入，你的 dump 日志中的十六进制标志位得到了完美解释：
   *   `0x40000000` = `POLICY_FLAG_PASS_TO_USER` (初始硬件层判定)
   *   `0x20000000` = `POLICY_FLAG_INTERACTIVE` (初始硬件层判定)
   *   `0x04000000` = `POLICY_FLAG_FILTERED` (由注入层 `InputFilterHost` 强制追加)
   *   `0x02000000` = `POLICY_FLAG_TRUSTED` (默认可信事件)
   *   `0x01000000` = `POLICY_FLAG_INJECTED` (底层发现是外部 `inject` 调用自动追加)
   相加恰好为 **`0x67000000`**。而正是由于它是通过 `injectInputEvent` 注入的，系统会为其分配**全新的 `inputEventId` (B)** 且来源不再是 `INPUT_READER`。这两点彻底剥夺了该事件进入 `LatencyTracker` 性能白名单的资格。
#### 时序机制的核心推论

1.  **原生事件管线的终止原因**
    查阅 `InputManagerService.java` 的源码可以发现，`filterInputEvent` 方法的实现逻辑为：当存在 `mInputFilter != null` 时，向其传递事件后**将无条件返回 `false`**。此设计意味着不论上层无障碍服务最终是否放行事件，原生的 C++ `notifyMotion` 分发流在调用该 JNI 方法后即被中断。
2.  **`0x67000000` 标志位的组合逻辑**
    通过分析时序图第 3 阶段的注入流程，该十六进制值系由以下标志位按位或 (Bitwise OR) 组合而成：
    *   `0x40000000` = `POLICY_FLAG_PASS_TO_USER` (初始硬件层判定产生)
    *   `0x20000000` = `POLICY_FLAG_INTERACTIVE` (初始硬件层判定产生)
    *   `0x04000000` = `POLICY_FLAG_FILTERED` (由注入过程的 `InputFilterHost` 追加)
    *   `0x02000000` = `POLICY_FLAG_TRUSTED` (默认可信事件标志)
    *   `0x01000000` = `POLICY_FLAG_INJECTED` (在底层的 `injectInputEvent` 内部自动追加)
    上述标志位的总和精确等于 `0x67000000`，与 `dumpsys` 的输出完全一致。
3.  **性能统计失效的技术背景**
    在重新注入时，由于事件被视作由外部框架调用的请求，系统会重新分配 **`inputEventId`** 并将其 `Source` 定义变更为非 `INPUT_READER`。基于这两项变化，底层监控框架将判定该事件不再是原始的物理输入行为，进而主动从 `LatencyTracker` 的考量范畴中将其剔除。


> **名词解释：什么是 A11y / A11yInputFilter？**
> 
> 在前文的 dumpsys 报告和源码分析中，我们多次看到了 `A11yInputFilter` 和 `A11y` 这个词。
> *   **A11y** 是业界对 **Accessibility (无障碍/辅助功能)** 的标准缩写。因为从首字母 `A` 到尾字母 `y` 之间刚好有 11 个字母。
> *   **`A11yInputFilter`** 则是 `dumpsys accessibility` 命令在输出日志时，对底层核心类 `AccessibilityInputFilter` 的简写。它代表的正是那个由于语音助手申请了特权，而在底层被强行挂载、导致物理触控事件被全局拦截和重注入的 Java 层“事件加工流水线”。

### 8. 实战排查案例：基于 Dumpsys 解析被劫持的底层管线

当你怀疑系统的输入管线被异常劫持，或者 `SLOW_INPUT_EVENT_REPORTED` 日志打不出来时，通过对 `adb shell dumpsys accessibility` 输出日志的解析，往往能直接锁定“元凶”。

以下是对一台真实车机（`h47a`）实车 dump 结果的专业级调查报告。

#### 1. 抓获幕后元凶：到底是谁注册了无障碍服务？
在 dumpsys 输出中，找到 `User state` 节点下的 `Enabled services` 和 `Bound services` 字段：

```text
Enabled services:{ {com.voyah.ai.voice/com.voyah.ai.business.viewcmd.accessibility.VoiceAccessibilityService} }
Bound services:{ Service[label=智能助手, feedbackType[FEEDBACK_GENERIC], capabilities=33, ...] }
```
**解析：** 
这就是导致整个 InputFlinger C++ 底层测速瘫痪的“元凶”！车机上的 **智能助手（语音助手）应用 `com.voyah.ai.voice`**，长期在后台静默注册并绑定了一个名为 `VoiceAccessibilityService` 的无障碍服务。

#### 2. 罪证确凿：它到底申请了什么特权？
我们继续看 `Bound services` 里面的 `capabilities` 字段：
```text
capabilities=33 (即二进制的 100001)
```
在 Android 源码 (`AccessibilityServiceInfo.java`) 中，capabilities 是按位或组合的：
*   `CAPABILITY_CAN_RETRIEVE_WINDOW_CONTENT = 1`（允许获取窗口内容，如节点文字）
*   `CAPABILITY_CAN_PERFORM_GESTURES = 32`（**允许执行和注入手势**）

**解析：**
这证明了该语音助手不仅申请了读取屏幕文字的权限，更**申请了注入触摸事件（`FLAG_FEATURE_INJECT_MOTION_EVENTS`）的特权**。
正如我们上一节源码推演的，只要存在这个 `INJECT_MOTION_EVENTS` 权限，`AccessibilityManagerService` 就会立刻实例化一个 `InputFilter`，强行将底层 `InputDispatcher` 的 `mInputFilterEnabled` 置为 `true`！

#### 3. A11yInputFilter 的生效证据
在 dump 的尾部，有一段 `A11yInputFilter Info` 的输出，这简直就是给系统底层盖棺定论的判决书：
```text
A11yInputFilter Info : 
Enabled features of Display [0] = [MotionEventInjector]
Enabled features of Display [2] = [MotionEventInjector]
Enabled features of Display [3] = [MotionEventInjector]
```
**解析：**
这表明：在系统的这三块屏幕（0号中控屏、2号副驾屏、3号某个应用屏）上，由于语音助手申请了注入权限，`MotionEventInjector` 这个事件加工拦截器已经被全局挂载。
所有的触摸事件，都会无差别地被迫跨越 JNI，跑去询问这个加工器。

#### 4. 架构反思：既然车机没有改原生流程，他们为什么要注册这个？
这是一个极具代表性的 Android 架构妥协。

车机的“智能语音助手”有一个极其核心的功能：**“可见即可说”**。
也就是你在屏幕上看到一个按钮写着“打开空调”，你直接用嘴喊“打开空调”，系统就会自动帮你点击那个按钮。

**为了实现“可见即可说”，语音助手必须做到两件事：**
1. **获取屏幕上所有的 View 树结构和文字：** 它需要知道屏幕上画了什么。这就是为什么它申请了 `capabilities` 里的 `1` (获取窗口内容)。
2. **模拟用户的手指去点击那个坐标：** 当你说出指令后，它需要跨进程去点击那个 View。这就是为什么它申请了 `capabilities` 里的 `32` (执行和注入手势)。它利用的就是无障碍框架提供的 `dispatchGesture` API。

**代价与悲剧：**
车机开发团队非常“偷懒”地使用了 Android 标准的 Accessibility 接口来实现“可见即可说”。但他们可能并没有意识到，这个 `32`（注入手势）权限申请下去，系统框架就会为了“配合你可能要注入手势的动作”，粗暴地把底层 C++ 原生输入管线的监控网（LatencyTracker）全部拆除了。

这就是为什么哪怕车机没有改一行底层 C++ 源码，原生的触摸测速埋点依然全盘崩溃的根本原因。这也是我们在进行车机底层性能调优时，必须要跨界具备 Java Framework 甚至上层业务理解能力的最佳反面教材。


#### 关于非盲人模式下手势未达应用的溯源分析

在上述机制推演中，存在一个核心疑问：当无障碍服务仅申请了 `CAPABILITY_CAN_PERFORM_GESTURES` (注入手势) 权限，而并未申请接管物理触摸 (如 `TouchExploration`) 时，**真实的物理触摸事件是否会通过 Binder 跨进程派发至该无障碍应用？**

**结论：不会。** 在此特定配置下，物理事件仅在 System Server 进程的 Java 框架层空转，并不会实际触达无障碍服务的应用进程。其底层逻辑链条如下：

1. **触发 `InputFilter` 挂载的充要条件：**
   通过分析 `AccessibilityManagerService.updateInputFilter`，只需应用声明 `isPerformGesturesEnabledLocked`，系统即会强制实例化 `AccessibilityInputFilter` 并将底层 `mInputFilterEnabled` 置为 `true`。这是导致原生 C++ 管线中断的第一因。
2. **`EventStreamTransformation` 责任链的极简状态：**
   由于应用未申请盲人模式或按键拦截，此时组装的责任链中仅包含唯一的处理器：**`MotionEventInjector`**。
3. **空转放行的源码实现：**
   当底层物理滑动事件经由 JNI 传递至 `MotionEventInjector` 的 `onMotionEvent` 方法时，该处理器仅用于处理由辅助功能发起的模拟手势。对于来源为硬件的真实触摸事件，源码实现如下：
   ```java
   // 源码路径：frameworks/base/services/accessibility/java/com/android/server/accessibility/MotionEventInjector.java
   @Override
   public void onMotionEvent(MotionEvent event, MotionEvent rawEvent, int policyFlags) {
       // ... 略过辅助工具防干扰逻辑 ...
       
       // 对于真实的物理触摸事件，不作任何处理，直接向下传递至责任链末端
       super.onMotionEvent(event, rawEvent, policyFlags);
   }
   ```
4. **系统资源的无效消耗：**
   事件直接流至链条末端的 `InputFilterHost`，随后调用 `injectInputEvent` 重新排队。这意味着，无障碍服务本身对这些物理滑动**零感知、零消费**。系统仅仅为了维持“随时可能发起注入”的能力框架，付出了每次滑动事件均需经历 `Native -> JNI -> Java -> JNI -> Native` 完整跨语言调用的高昂性能代价，并不可逆地破坏了事件的原始溯源 ID。

此现象进一步印证了在车机架构中，采用全局系统特权权限 (`INJECT_EVENTS`) 替代无障碍服务执行模拟点击的技术必要性。

### 9. 架构重构指南：如何优雅实现车机“可见即可说”？

在明确了 `AccessibilityService`（无障碍服务）会为了“可见即可说”功能而挂载全局 `InputFilter`，进而毁灭整个系统的输入测速埋点（`SLOW_INPUT_EVENT_REPORTED`）之后，摆在车机架构师面前的灵魂拷问是：**不使用无障碍服务，如何正确实现“可见即可说”？**

“可见即可说”包含两个核心技术动作：**“可见”**（获取屏幕 View 树）和 **“即可说”** （触发目标 View 的点击）。
在车机（AAOS）环境下，最佳的架构实践应当完全规避 `Accessibility` 框架，采用以下两套解耦方案：

#### 核心思路：放弃全局过滤，改用“按需提取”与“直接注入”

**错误的做法（当前痛点）：** 
语音助手为了能“随时模拟点击”，长期注册了无障碍服务的 `CAPABILITY_CAN_PERFORM_GESTURES` 特权。这导致底层的 `AccessibilityManagerService` 认定系统中随时会有无障碍手势产生，从而**永久挂载**了 `InputFilter`，把 99.9% 正常的手指滑动也给拦截和重注入了。

**正确的做法：系统级 `INJECT_EVENTS` 权限直调**
语音助手作为车机的核心 System App，完全有资格在 `AndroidManifest.xml` 中申请系统级签名权限 `android.permission.INJECT_EVENTS`。
当用户通过语音下达指令（如“打开空调”），语音助手只需计算出空调按钮的屏幕坐标 `(x, y)`，然后直接调用：
```java
InputManager.getInstance().injectInputEvent(motionEvent, InputManager.INJECT_INPUT_EVENT_MODE_ASYNC);
```
**这种做法的架构优势：**
它**不需要**向系统注册任何无障碍服务！`InputManager.injectInputEvent()` 是一个独立的后门 API。当你调用它时，系统只会把这一个由语音生成的模拟点击打上 `INJECTED` 标签塞进队列，而**绝不会触发全局的 `mInputFilterEnabled = true`**。
这样，用户用手指在屏幕上滑动的物理事件，依然会走最纯粹的 C++ 原生分发管线，完美保留在 `LatencyTracker` 的端到端测速大盘中。

#### 方案一：采用官方的 VoiceInteractionService (Assist API)
如果你想要获取屏幕上的按钮文字（“可见”），不需要用 Accessibility 去遍历节点。Android 官方为语音助手提供了专门的 **Assist API**：
1. 语音助手继承并实现 `VoiceInteractionService` 和 `VoiceInteractionSession`。
2. 当用户唤醒语音时，调用 `onHandleAssist(Bundle data, AssistStructure structure, ...)`。
3. `AssistStructure` 是由底层的 `ViewRootImpl` 瞬间快照生成的一棵极度轻量级的屏幕 View 树（包含了文字、坐标、ContentDescription）。
4. 语音助手通过这棵树找到目标按钮的坐标，然后用 `INJECT_EVENTS` 权限直接注入点击事件。

#### 方案二：OEM 深度定制 ViewRootImpl (车厂常见魔改)
如果你觉得 Assist API 每次生成全屏快照太重，OEM 完全可以在 Framework 层做极低侵入的定制：
1. **自动上报：** 在 `frameworks/base/core/java/android/view/View.java` 的重绘或布局逻辑中，只要 View 包含文字且 `isClickable() == true`，就通过一条专属的 Binder 通道，将其哈希值、文字和屏幕绝对坐标异步推送给“语音分发系统服务 (VoiceDispatcherService)”。
2. **精准制导：** 当语音助手识别到“打开空调”时，去 VoiceDispatcherService 的缓存里查到坐标，然后执行 `InputManager.injectInputEvent()`。

### 总结
**Accessibility（无障碍服务）在 Android 架构设计中的初衷，是为残障人士提供接管设备输入输出的“兜底后门”，它在性能和事件溯源上做出了极大的妥协。**

智能座舱中的“语音可见即可说”是一项高频、核心的商业功能。**用低频的兜底后门（Accessibility）去承载高频的商业级交互，必然会遭到系统底层架构的“反噬”**。虽然实测数据显示 JNI 跨语言与注入带来的绝对性能延迟微乎其微（< 2ms），但它所导致的 `inputEventId` 链条断裂与端到端性能可观测性（LatencyTracker）的全面崩溃，对于渴望追求极致跟手性调优的架构团队而言，是无法接受的监控灾难。

将“获取屏幕内容”和“模拟点击屏幕”解耦，使用 `Assist API` / 定制 `ViewRootImpl` 负责前者，使用系统级 `INJECT_EVENTS` 权限负责后者，这才是真正符合系统级输入输出架构（InputFlinger）美学的“最佳实践”。

### 10. 扩展分析：除了无障碍，还有谁会触发全局 InputFilter？

在原生的 Android 框架（AOSP）中，`InputDispatcher` 的 `mInputFilterEnabled` 是一个极具杀伤力的系统级变量。一旦它变为 `true`，底层的物理事件监控管线就会彻底瘫痪。

通过前文的深入追踪，我们已经证实了**唯一合法的挂载入口是 `AccessibilityManagerService` (AMS)**。但在系统运行的生命周期中，除了车机上“伪装成辅助功能”的语音助手，究竟还有哪些原生功能会激活这个过滤器？

#### AOSP 原生触发条件一览
通过彻底解剖 AMS 的 `updateInputFilter()` 方法，我们梳理出了导致 `InputFilter` 被挂载的 **10 个充要条件**（只要触发其中任何一个，Filter 就会挂载）：

1. **屏幕放大相关 (Magnification)**
   - `isMagnificationSingleFingerTripleTapEnabledLocked`（单指三击放大屏幕）
   - `isMagnificationTwoFingerTripleTapEnabledLocked`（双指三击放大屏幕，Android 14+）
   - `isShortcutMagnificationEnabledLocked`（通过快捷键触发屏幕放大器）
   - `userHasMagnificationServicesLocked`（存在注册了控制放大器特权的服务）
2. **触摸与手势接管相关 (Touch Exploration & Gestures)**
   - `isTouchExplorationEnabledLocked`（开启了 TalkBack 的触摸浏览模式）
   - `isPerformGesturesEnabledLocked`（服务声明了注入执行全局手势的权限 `CAPABILITY_CAN_PERFORM_GESTURES`）
   - `isSendMotionEventsEnabled` (允许服务观察物理触摸事件)
3. **物理按键拦截相关 (Key Filtering)**
   - `isFilterKeyEventsEnabledLocked`（服务声明了拦截物理按键的权限 `FLAG_REQUEST_FILTER_KEY_EVENTS`）
4. **悬停与通用输入相关 (Generic/Hover Events)**
   - `combinedGenericMotionEventSources != 0`（服务申请拦截或监听鼠标、摇杆等通用输入设备的事件）
5. **辅助外设相关 (Hardware Accessibility)**
   - `isAutoclickEnabledLocked`（开启了鼠标停止移动后自动点击的辅助功能）
   - `isMouseKeysEnabled`（开启了小键盘模拟鼠标移动的功能）
   
*(注：以上列出了 AOSP `AccessibilityManagerService.java` 中导致 `InputFilter` 挂载的完整 10 余条触发条件分支，详见源码。)*

#### 全局手势检测会导致 Filter 触发吗？
许多开发者会混淆 Android 内部的两套手势机制。这里必须澄清一个常见的误区：**普通系统的全局手势检测（如边缘滑动返回、三指截屏）绝对不会导致 `InputFilter` 被挂载！**

*   **真正的系统全局手势（System Gestures）：**
    在 AOSP 原生实现中，像状态栏下拉、边缘滑动返回（Back Gesture）、三指截屏等系统手势，是由 `WindowManagerService` 内部的 **`SystemGesturesPointerEventListener`** 和 **`DisplayPolicy`** 处理的。
    它们通过在底层注册一个 `InputChannel` 成为一个“监视者窗口 (`SPY_WINDOW`)”或者是“触摸前置窃听器 (`PointerEventListener`)”。这种方式是完全原生且合法的，事件依然走纯净的 C++ 派发管线，**绝不会触发 `InputFilter`，也完全不会影响端到端延迟统计 (`LatencyTracker`)。**
*   **冒牌的系统手势（通过 Accessibility 伪装）：**
    只有当开发者（或者 OEM 厂商）不想去修改底层的 `WindowManagerService` 源码，为了图省事，用一个上层的 App 去注册 `AccessibilityService`，并要求其代为执行手势或监听输入时，才会触发上述的这 10 个条件，进而招致架构灾难。

**总结：** `InputFilter` 是一个专门且仅为残疾人辅助设施（Accessibility）设立的隔离舱。如果你不是在做盲人模式或者轮椅用户辅助工具，绝不要让你的系统级 App 触碰到那 10 个危险的触发开关。

### 11. 架构纵深：原生系统全局手势 (System Gestures) 的窃听与派发时序

在前文的分析中，我们明确了使用 `AccessibilityService` 拦截输入来实现业务逻辑会导致原生派发管线的异常。那么，Android 官方系统自身是如何实现诸如“边缘滑动返回 (Back Gesture)”、“状态栏下拉”、“三指截屏”等全局系统手势的呢？

Android 框架并未采用高侵入性的 `InputFilter`，而是设计了一套极具解耦性与高性能的**“间谍窗口 (SPY Window)”机制**。系统在不阻断原始 C++ 派发管线的前提下，实现了对触摸事件的无损窃听与竞争。

#### 1. SPY Window (间谍窗口) 机制原理
在 `WindowManagerService` 中，类似 `SystemGesturesPointerEventListener` 这类需要全局监听触摸的模块，在向输入系统注册时，并不会拦截整个系统通道，而是会向 `SurfaceFlinger` 申请一个带有特殊属性 `InputConfig::SPY` 的隐形窗口（在 dumpsys 中常命名为 `[Gesture Monitor] ...`）。
*   **非独占性：** 当 `InputDispatcher` 在 Z 轴从上到下执行坐标命中测试 (`Hit Testing`) 时，如果命中的是一个 `SPY` 窗口，Dispatcher **不会停止寻找**。它会将该 `SPY` 窗口加入目标列表，并继续向下贯穿，直至找到真正的实体交互窗口（如桌面或前台 App）。
*   **一发多派：** 最终，Dispatcher 会将同一个硬件滑动事件，通过各自独立的 `InputChannel` (Unix Domain Socket)，**并发、同时**发送给 `SPY` 窗口与前台 App。
*   **截胡机制 (Pilfering)：** 既然前台 App 和系统手势模块同时收到了滑动事件，如果用户确实是在执行“边缘返回”，App 界面岂不是也会跟着滑动？为了解决竞争，如果手势模块判定该手势成立，它会向 Dispatcher 发送一个 **`pilferPointers`（剥夺指针）**的 Binder 请求。Dispatcher 收到后，会立刻向前台 App 发送一个 `ACTION_CANCEL` 事件，强制终止 App 对该手势的响应，由系统手势模块独占接管。

#### 2. 原生系统手势派发与竞争时序图

下面的时序图详细推演了由 `InputReader` 产生真实硬件中断后，系统级手势如何与前台应用公平竞争，并完成合法的延迟统计：

```mermaid
sequenceDiagram
    autonumber
    
    box LightCyan InputReader Thread (Native)
    participant Reader as InputReader
    end
    
    box LightYellow System Server (Dispatcher Thread)
    participant Disp as InputDispatcher
    participant Monitor as Gesture Monitor<br>(SPY Window / WMS)
    end
    
    box LightPink App Process (UI Thread)
    participant App as 前台焦点 App
    end
    
    participant Latency as LatencyTracker

    %% --- 1. 硬件入口与入队 ---
    Note over Reader, Disp: 1. 硬件入口与合规的延迟追踪
    Reader ->> Disp: notifyMotion(args)
    Note right of Disp: 此时无全局 InputFilter 拦截
    Disp ->> Disp: mLock.lock()
    Disp ->> Latency: trackListener(args)
    Note right of Latency: 成功记录原始 eventTime，开始端到端性能统计
    Disp ->> Disp: enqueueInboundEventLocked()
    Disp ->> Disp: mLooper->wake()
    Disp ->> Disp: mLock.unlock()

    %% --- 2. 穿透式命中测试 (Hit Testing) ---
    rect rgb(240, 240, 240)
    Note over Disp, App: 2. 穿透式的 SPY Window 命中测试
    Disp ->> Disp: dispatchOnceInnerLocked()
    Disp ->> Disp: findTouchedSpyWindowsAt()
    Note right of Disp: 从上至下遍历，命中 SPY 属性的手势监视窗口，<br>将其加入 target 列表，但【继续向下查找】
    Disp ->> Disp: 命中下层非 SPY 属性的前台实体窗口，<br>作为主 target 加入列表
    end

    %% --- 3. 并发派发与应用消费 ---
    rect rgb(230, 255, 230)
    Note over Disp, App: 3. 并发派发机制
    Disp ->> Monitor: Socket send: publishMotionEvent()
    Disp ->> App: Socket send: publishMotionEvent()
    Note over Monitor, App: 此时，系统手势监听器与前台应用【同时】收到触摸事件
    
    Monitor ->> Monitor: 判定手势轨迹 (如边缘滑入)<br>SystemGesturesPointerEventListener
    App ->> App: 开始滑动处理 (如列表滚动)<br>onTouchEvent()
    end

    %% --- 4. 手势截胡 (Pilfer Pointers) ---
    rect rgb(255, 240, 240)
    Note over Monitor, App: 4. 合法的事件竞争与剥夺 (Pilfering)
    alt 系统手势成立 (System Gesture Detected)
        Monitor ->> Disp: Binder: pilferPointers(inputChannelToken)
        Note right of Disp: 收到系统剥夺请求，中止其余接收者的分发
        Disp ->> App: 强行发送 ACTION_CANCEL 事件
        Note right of App: App 列表停止滚动，放弃当前手势上下文
        App -->> Disp: Socket: FINISHED
        Monitor -->> Disp: Socket: FINISHED (手势执行完毕)
    else 非系统手势 (Normal App Touch)
        Monitor -->> Disp: Socket: FINISHED (不关心该事件)
        App ->> App: 继续执行常规滑动与渲染 UI
        App -->> Disp: Socket: FINISHED
        App -->> Disp: Socket: TIMELINE (正常触发跟手性监控)
    end
    end
```

#### 架构设计的优越性总结
通过 `SPY Window` 机制与 `pilferPointers` 剥夺指令的配合，AOSP 官方手势系统实现了三个核心架构诉求：
1. **零性能惩罚：** 手势判定模块与 App 处于同级的接收端（Receiver），Dispatcher 仅通过底层的 Socket 广播，没有引入任何同步的阻塞调用与锁竞争。
2. **极佳的监控透明度：** 由于未拦截底层的入队与分发流程，事件始终保持最原始的硬件属性（`Source=INPUT_READER`），完美保留在 `LatencyTracker` 的端到端卡顿监控雷达中。
3. **平滑的业务降级：** 即使处理系统手势的进程由于负载极高发生严重卡顿，因为 Socket 是全双工异步非阻塞的，前台焦点应用的正常触摸交互与界面渲染**绝对不会**因此受到牵连。这正是系统架构设计中容错性（Resilience）的典范。

### 7. inputEventId 视角的事件生命周期对照图

> **修订说明（2026-04-29 实证修正）：**
> 早期版本的本节曾推测：Java 层 InputFilter 拦截原始事件 A 并通过 `MotionEvent.obtain(...)` 重新组装事件 B 注入时，Native 层会**分配全新的 `inputEventId`**，从而造成 LatencyTracker 在两个不同 ID 之间永远凑不齐 timeline。
>
> 通过 adb logcat 实际抓取车机上 `notifyMotion` 与 `injectInputEvent` 的对应日志后证伪了该推测：
>
> ```text
> InputDispatcher: notifyMotion - id=7031abe   eventTime=1782412215000ns ... action=MOVE ...
> InputDispatcher: notifyMotion - id=194e7f53  eventTime=1782437144000ns ... action=UP   ...
> InputDispatcher: injectInputEvent: ... event=MotionEvent { action=MOVE, ... eventId=0x7031abe }
> InputDispatcher: injectInputEvent: ... event=MotionEvent { action=UP,   ... eventId=0x194e7f53 }
> ```
>
> 同一笔触摸的 `notifyMotion id` 与 `injectInputEvent eventId` **完全一致**（MOVE 都是 `0x7031abe`，UP 都是 `0x194e7f53`）。说明车机上的 InputFilter 实现是把原 `MotionEvent` 直接透传/拷贝（保留 id），而不是 `obtain` 一个全新事件。**ID 错位假说不成立，timeline 不闭环必须从别处找原因。**

#### 修订后的真相：trackListener 的调用点被短路

在挂了 InputFilter 的车机上，原始事件 A 与注入事件其实是**同一个 `inputEventId`**，但 `LatencyTracker::trackListener(...)` 仍然没机会建档。原因不在 ID 错位，而在调用点：

- `trackListener(...)` 是在 `InputDispatcher::notifyMotion(...)` 函数体的**下半段**才被调用的；
- 而 `notifyMotion(...)` 在上半段就会通过 `shouldSendMotionToInputFilterLocked()` + `mPolicy.filterInputEvent(...)` 把事件交给 Java 侧 InputFilter，一旦后者返回 `false`（消费），函数立即 `return`，**下半段（含 `trackListener`）永远不会执行**；
- Java 侧再以 `injectInputEvent(...)` 把事件喂回来时，走的是 `InputDispatcher::injectInputEvent(...)` 这条独立的代码路径，它直接构造 `MotionEntry` 入队，**根本不经过 `notifyMotion`**，自然也没有 `trackListener` 调用。

结果：尽管原始事件和注入事件 ID 一致，`mTimelines` 这张表里压根没有这条 id 的档案；App 后续 `Finished` / `Timeline` 回包时 `mTimelines.find(id)` 一律 miss，timeline 永远不可能 `isComplete()`，`SLOW_INPUT_EVENT_REPORTED` 的 ALOGW 与 StatsD 打点也就永远触发不了。

```mermaid
sequenceDiagram
    autonumber

    participant Hardware as Touch Panel

    box LightCyan LatencyTracker (性能测速大盘)
    participant Tracker as mTimelines<br>[字典集合]
    end

    box LightYellow System Server (Native)
    participant Reader as InputReader
    participant Disp as InputDispatcher
    end

    box LightPink System Server (Java)
    participant JavaFilter as A11y InputFilter / OEM 输入策略
    end

    participant App as 前台焦点 App

    %% --- 1. 事件诞生 ---
    Note over Hardware, Disp: 1. 原始事件诞生 (ID = X)
    Hardware ->> Reader: 物理中断
    Reader ->> Disp: notifyMotion(args, id=X)
    Note right of Reader: Source: INPUT_READER

    %% --- 2. notifyMotion 上半段：被 Filter 短路 ---
    rect rgb(255, 230, 230)
    Note over Disp, JavaFilter: 2. notifyMotion 上半段：filterInputEvent 拦截后 return
    Disp ->> JavaFilter: mPolicy.filterInputEvent(event=X)
    JavaFilter -->> Disp: return false (消费)
    Note right of Disp: 函数体直接 return，<br>下半段的 trackListener(X) 永远不会执行！<br>mTimelines 中没有 id=X 的档案。
    end

    %% --- 3. Java 侧重新注入，ID 保持为 X ---
    rect rgb(230, 255, 230)
    Note over JavaFilter, Disp: 3. Java 侧 inject，ID 仍然是 X
    JavaFilter ->> Disp: injectInputEvent(event=X) [policyFlags |= INJECTED]
    Note right of Disp: 走的是 injectInputEvent() 路径，<br>不经过 notifyMotion，也不调用 trackListener。<br>直接构造 MotionEntry 入队。
    Disp ->> App: Socket 派发 (id=X)
    end

    %% --- 4. 结账时找不到档案 ---
    rect rgb(240, 240, 240)
    Note over App, Tracker: 4. 结账失败：mTimelines 里压根没建过 X 的档
    App ->> App: 渲染送显
    App -->> Disp: Socket: Finished (id=X)
    App -->> Disp: Socket: Timeline (id=X, presentTime)

    Disp ->> Tracker: trackFinishedEvent(X) / trackGraphicsLatency(X)
    Tracker ->> Tracker: mTimelines.find(X) → miss
    Note right of Tracker: 找不到档案，直接 return。<br>没有任何 timeline 进入 isComplete 状态，<br>processSlowEvent 也无从触发 ALOGW / StatsD。
    end
```

#### 断案结论（修订版）

车机上 `SLOW_INPUT_EVENT_REPORTED` 日志缺失的真正机制不是"ID 错位"，而是 **trackListener 调用点被 InputFilter 消费提前短路**：

1. `InputFilterEnabled=true` 的目标上，每一笔触摸都会被 `filterInputEvent` 消费，使 `notifyMotion` 在调用 `trackListener` 之前 return；
2. 走 `injectInputEvent` 重新进入的事件虽然保留了原始 `inputEventId`，但这条代码路径没有任何 `trackListener` 钩子；
3. 两条路径都不建档，于是 App 后续回写的 `Finished/Timeline` 永远找不到对应 entry，`mTimelines` 里没有任何条目能 `isComplete()`，慢事件上报路径整体哑火。

排查"timeline 不完整 / `connectionName` 为空 / SLOW 日志看不到"问题时，应当**首先确认 `InputFilterEnabled` 与 filter+inject 路径是否启用**，而不是去怀疑 ID 是否被改写。要让 LatencyTracker 在这类目标上重新工作，可选方案是把 `trackListener` 同时挂到 `injectInputEvent` 路径上，或在 InputFilter 拦截前提早建档。
