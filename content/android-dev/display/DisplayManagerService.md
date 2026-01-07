+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = 'DisplayManagerService设计'
+++

## LogicalDisplay的创建过程

这个时序图展示了从底层物理屏幕发现到上层窗口管理容器创建的完整链路。

![](../../../static/images/android-13-LogicalDisplay-creating-sequence.png)

1.  **初始化阶段**:

      * `DisplayManagerService` 启动，在 `onStart` 方法中发送 `MSG_REGISTER_DEFAULT_DISPLAY_ADAPTERS` 消息。
      * `DisplayManagerService` 的 Handler 处理该消息，调用 `registerDefaultDisplayAdapters`。
      * 在 `registerDefaultDisplayAdapters` 中，创建 `LocalDisplayAdapter` 实例并注册。

2.  **LocalDisplayAdapter 发现设备**:

      * `LocalDisplayAdapter` 初始化时会从 `SurfaceControl` 获取物理屏幕信息（通过 `SurfaceControlProxy`）。
      * 发现物理屏幕后，创建 `LocalDisplayDevice`。
      * 调用 `sendDisplayDeviceEventLocked` 发送 `DISPLAY_DEVICE_EVENT_ADDED` 事件。

3.  **DisplayDeviceRepository 处理事件**:

      * `DisplayAdapter` 将事件发送给 `DisplayDeviceRepository`。
      * `DisplayDeviceRepository` 将 `LocalDisplayDevice` 添加到列表，并通知监听者，即 `LogicalDisplayMapper`。

4.  **LogicalDisplayMapper 创建 LogicalDisplay**:

      * `LogicalDisplayMapper` 收到 `DISPLAY_DEVICE_EVENT_ADDED`。
      * 如果是默认屏幕，先进行初始化配置。
      * 调用 `createNewLogicalDisplayLocked` 创建 `LogicalDisplay` 对象。
      * 调用 `applyLayoutLocked` 来根据设备状态配置布局。
      * 最后调用 `updateLogicalDisplaysLocked` 来更新整个系统的显示状态。

5.  **通知系统和 WMS**:

      * `updateLogicalDisplaysLocked` 中，`LogicalDisplayMapper` 通知 `DisplayManagerService` (通过 `Listener`) `LOGICAL_DISPLAY_EVENT_ADDED`。
      * `DisplayManagerService` 收到事件，调用 `handleLogicalDisplayAddedLocked`。
      * `DisplayManagerService` 发送 `DisplayManagerGlobal.EVENT_DISPLAY_ADDED` 到 Handler。
      * Handler 处理消息，调用 `deliverDisplayEvent` 通知所有注册的 `IDisplayManagerCallback`。
      * **关键点**: `WindowManagerService` 在初始化时通过 `DisplayManagerInternal` 获取了 `DisplayManager` 的回调或直接监听。但在代码中，WMS 实际上是通过 `DisplayManagerInternal.registerDisplayTransactionListener` 或直接轮询/监听来感知的。
      * 更具体的路径是：`DisplayManagerService` 在 `handleLogicalDisplayAddedLocked` 中会配置显示属性，并最终触发 `DisplayTransactionListener` 或发送广播。
      * 在 `WindowManagerService` 中，通常通过 `DisplayManager` 的回调 `onDisplayAdded` 感知，然后调用 `mRoot.createDisplayContent`。在提供的代码中，`DisplayManagerService` 拥有 `mDisplayTransactionListeners`。
      * `DisplayManagerService` 的 `handleLogicalDisplayAddedLocked` 会调用 `sendDisplayEventLocked`，进而触发回调。

    *补充：`WindowManagerService` 如何创建 `DisplayContent`*

      * `WindowManagerService` 监听 `DisplayManager` 的事件。当 `DisplayManager` 发布新屏幕时，`WindowManagerService.onDisplayAdded` 被调用。
      * `WindowManagerService` 调用 `mRoot.getDisplayContentOrCreate(displayId)`，进而创建 `DisplayContent`。

### 详细说明

1.  **SystemServer 启动 DMS**: `SystemServer` 调用 `DisplayManagerService.onStart()`。
2.  **注册 Adapter**: `DisplayManagerService` 通过 Handler 发送消息来注册默认的 Display Adapter（主要是 `LocalDisplayAdapter`，用于处理内置屏幕和 HDMI 屏幕）。
3.  **发现设备**: `LocalDisplayAdapter` 在注册时会扫描物理屏幕 (`SurfaceControl.getPhysicalDisplayIds`)，为每个发现的屏幕创建 `LocalDisplayDevice`。
4.  **发送设备添加事件**: `LocalDisplayAdapter` 通过 `sendDisplayDeviceEventLocked` 将 `DISPLAY_DEVICE_EVENT_ADDED` 事件发送给 `DisplayDeviceRepository`。
5.  **事件传递**: `DisplayDeviceRepository` 将此事件转发给监听者 `LogicalDisplayMapper`。
6.  **创建逻辑显示**: `LogicalDisplayMapper` 收到事件后，调用 `createNewLogicalDisplayLocked` 创建 `LogicalDisplay` 对象，将其与物理设备绑定。
7.  **更新逻辑显示**: `LogicalDisplayMapper` 调用 `updateLogicalDisplaysLocked`，这会计算出哪些逻辑显示是新增的，并回调 `DisplayManagerService` 的 `onLogicalDisplayEventLocked`，事件类型为 `LOGICAL_DISPLAY_EVENT_ADDED`。
8.  **DMS 处理逻辑显示添加**: `DisplayManagerService` 收到逻辑显示添加事件后，发送内部消息 `MSG_DELIVER_DISPLAY_EVENT`。
9.  **通知 WMS**: `DisplayManagerService` 处理该消息，通过 `IDisplayManagerCallback` 机制（或 `DisplayManagerInternal` 的监听器）通知 `WindowManagerService` 有新屏幕添加。
10. **创建 DisplayContent**: `WindowManagerService` 收到通知后，调用 `onDisplayAdded`，进而调用 `mRoot.getDisplayContentOrCreate`，最终创建 `DisplayContent` 对象来管理该屏幕上的窗口层级结构。


### Layout的作用
每个 device state 对应一个 `Layout` 实例。`Layout` 类本身是一个容器，它描述了在特定设备状态下，系统中的物理显示设备（DisplayDevice）应该如何映射到逻辑显示（LogicalDisplay）。

**1. 每个 Layout 里面包含什么？**

`Layout` 类的核心是一个 `Display` 对象列表 (`mDisplays`)。这个列表定义了当前布局中有哪些显示屏被激活，以及它们的配置信息。

具体来说，`Layout` 包含以下关键信息：

* **显示设备列表 (`mDisplays`)**: 这是一个 `Layout.Display` 对象的列表。每一个 `Layout.Display` 对象代表布局中的一个显示配置项，它包含：
    * **物理地址 (`mAddress`)**: 对应物理显示设备 (`DisplayDevice`) 的唯一地址 (`DisplayAddress`)。这是将配置与实际硬件连接起来的关键。
    * **逻辑显示 ID (`mLogicalDisplayId`)**: 这个物理屏幕应该被映射到的逻辑显示器的 ID。如果是默认屏幕（主屏），这个 ID 通常是 0 (`DEFAULT_DISPLAY`)。
    * **是否启用 (`mIsEnabled`)**: 一个布尔值，指示在当前布局（即当前设备状态）下，这个显示设备是否应该是开启（ON）还是关闭（OFF）状态。

**简单来说：** 一个 `Layout` 对象就像一张蓝图，告诉系统：“在当前的设备状态下（比如折叠状态），地址为 X 的屏幕应该作为逻辑显示屏 A 并开启，地址为 Y 的屏幕应该作为逻辑显示屏 B 并关闭。”

**2. 这么设计的目的是什么？**

这种设计的主要目的是为了**灵活地支持多种设备形态和状态**，特别是针对折叠屏、多屏设备以及可变形态设备。

* **状态驱动的显示配置**: 设备可能有多种物理状态（展开、折叠、半折叠、帐篷模式等）。不同状态下，用户期望使用的屏幕组合和排列方式是不同的。
    * *例子*: 这是一个折叠屏手机。
        * *展开状态 (State A)*: 内部大屏 (`Device 1`) 开启并作为主屏 (`ID 0`)，外部小屏 (`Device 2`) 关闭。
        * *折叠状态 (State B)*: 内部大屏 (`Device 1`) 关闭，外部小屏 (`Device 2`) 开启并作为主屏 (`ID 0`)。
* **解耦物理设备与逻辑显示**: Android 应用层通常只关心逻辑显示（Display ID）。通过 `Layout`，系统可以在底层物理设备发生变化（如开/关、切换主从）时，动态地将物理设备“插拔”到对应的逻辑显示 ID 上。这使得应用不需要感知复杂的底层硬件切换逻辑。
* **统一管理**: `LogicalDisplayMapper` 可以通过加载配置文件（通常是 XML），预先定义好所有可能的设备状态及其对应的 `Layout`。当 `DeviceStateManager` 报告状态变化时，`LogicalDisplayMapper` 只需要查表找到对应的 `Layout`，然后应用这个布局 (`applyLayoutLocked`)，即可完成复杂的屏幕切换操作。

**总结**

`Layout` 是设备状态（Device State）到屏幕配置的映射表。每个 `Layout` 定义了一组物理屏幕及其属性（是否开启、绑定哪个逻辑 ID）。这种设计使得系统能够根据设备的物理形态变化，平滑、灵活地重组显示资源，适配各种复杂的多屏场景。


## DisplayGroup

在 Android 的多屏架构（Multi-Display Architecture）中，**`DisplayGroup`（显示组）** 是一个位于 `LogicalDisplay` 之上的逻辑容器。

简单来说，它是用来**将一个或多个逻辑屏幕（LogicalDisplay）打包在一起，以便进行统一管理和隔离**的机制。

它的核心设计目的主要有两个：**逻辑隔离** 和 **多用户支持**（特别是在车载场景下）。

### 1\. 为什么需要 DisplayGroup？

在早期的 Android（如 Android 9 之前），所有的屏幕都是“平铺”的。只要应用愿意，它可以在屏幕 A 启动，然后跳到屏幕 B。

随着 **Android Automotive（车载）** 和 **Desktop Mode（桌面模式）** 的出现，这种“大锅饭”模式不够用了：

1.  **隔离性（Isolation）**：

      * **场景**：副驾正在看电影（副驾屏），主驾正在看导航（中控屏）。
      * **需求**：你绝对不希望副驾的一个弹窗（Activity）突然跳到主驾的屏幕上遮挡导航。
      * **解决**：将主驾屏放入 `DisplayGroup 0`，副驾屏放入 `DisplayGroup 1`。默认情况下，Activity 不能跨组启动或移动。

2.  **多用户并发（Multi-User / User Separation）**：

      * **场景**：主驾是“车主账号”，后座是“孩子账号”在玩游戏。
      * **需求**：Android 系统通常是单用户的（同一时间只有一个人登录）。但车载需要支持“多用户并发登录”（Concurrent Multi-User）。
      * **解决**：`DisplayGroup` 与 Android 的 `UserId` 绑定。
          * DisplayGroup 0 -\> 绑定 User 0 (System/Driver)
          * DisplayGroup 1 -\> 绑定 User 10 (Passenger)
      * 这样，每个组运行一套独立的 SystemUI、Launcher 和应用进程。

### 2\. 层级关系

为了理解它在架构中的位置，我们可以看这个层级图：

```text
DisplayManagerService (全局管理者)
    |
    +-- DisplayGroup 0 (主显示组，默认组)
    |     |
    |     +-- LogicalDisplay 0 (中控屏 - Default Display)
    |     |
    |     +-- LogicalDisplay 2 (仪表屏 - Cluster)
    |
    +-- DisplayGroup 1 (副驾显示组)
          |
          +-- LogicalDisplay 1 (副驾屏 - Passenger)
```

  * **PhysicalDisplay (Port 129)**: 硬件层面的屏幕。
  * **LogicalDisplay (ID 0)**: 软件层面的屏幕对象，映射到一个物理屏幕。
  * **DisplayGroup (ID 0)**: 包含 ID 0 和 ID 2 的容器。

### 3\. 关键特性

1.  **默认显示组（Default Display Group）**：

      * ID 通常为 0。
      * 包含默认显示屏（Display 0）。
      * 通常对应主用户（Driver）和关键系统组件。

2.  **Activity 堆栈限制**：

      * 在 `WindowManagerService` (WMS) 层面，`RootWindowContainer` 下面有多个 `DisplayContent`。
      * WMS 会利用 DisplayGroup 来限制 `Activity` 的启动目标。如果一个 Activity 属于 Group 1 的用户，它就不能在 Group 0 的屏幕上显示。

3.  **资源共享与独立**：

      * 同一个 Group 内的屏幕通常共享一些上下文（Context）或交互逻辑。
      * 不同 Group 之间通常是隔离的，甚至可能有独立的 Input 焦点。

### 总结

**DisplayGroup 是 Android 用来“划地盘”的。**

它在逻辑上把一堆屏幕圈起来，告诉系统：“这几块屏幕是一伙的（属于同一个用户或场景），其他的屏幕是外人，别随便串门。”这对于保证车载系统的**安全性**（主驾不被干扰）和**功能性**（副驾独立娱乐）至关重要。


### 应用场景

通过定义“座位（Occupant）”和“屏幕”的关系，CarService 会自动为你划分 DisplayGroup。

修改配置文件 (config.xml) 在 packages/services/Car/service/res/values/config.xml (或你的 Overlay 目录) 中配置 config_occupant_display_mapping。

```xml
<string-array name="config_occupant_display_mapping">
    <item>displayPort=129:type=DRIVER:seat=0</item>

    <item>displayPort=130:type=PASSENGER:seat=1</item>

    <item>displayPort=131:type=PASSENGER:seat=2</item>
</string-array>
```
CarService 的工作流程

1. 系统启动时，CarOccupantZoneService 读取这个配置。
2. 它会为副驾（Seat 1）创建一个新的 Android User（例如 User 10）。
3. 它调用 WindowManager 的 API，将 Port 130 的屏幕 分配给 User 10。

结果：WMS 自动创建一个新的 DisplayGroup，专门服务于 User 10，并将 Display 130 放入其中。


## DisplayPowerState

`DisplayPowerState` 类的核心作用是 **作为 `DisplayPowerController` 的一部分，管理和应用显示屏的电源状态（开、关、休眠）、亮度和颜色渐变效果，并确保这些状态以一致且同步的方式传递到底层硬件。**

### **工作原理分析**

`DisplayPowerState` 的工作原理可以总结为 **状态缓存 + 异步更新 + 动画协调**。

**1. 状态管理与缓存 (State Holder)**

* `DisplayPowerState` 维护了显示屏当前的几个关键属性：
    * `mScreenState` (int): 屏幕的电源状态（如 `STATE_ON`, `STATE_OFF`, `STATE_DOZE`）。
    * `mScreenBrightness` (float): 屏幕的亮度值（0.0 - 1.0）。
    * `mSdrScreenBrightness` (float): 针对 SDR 内容的屏幕亮度值。
    * `mColorFadeLevel` (float): 颜色渐变的级别（0.0 表示完全黑屏/关闭，1.0 表示完全显示）。

* 当 `DisplayPowerController` 调用 `setScreenState`、`setScreenBrightness` 或 `setColorFadeLevel` 等方法时，`DisplayPowerState` 首先会更新这些成员变量。这相当于在 Java 层缓存了期望的显示状态。

**2. 异步更新机制 (PhotonicModulator)**

* 为了避免在主线程（Handler 线程）中执行耗时的显示硬件操作导致阻塞，`DisplayPowerState` 使用了一个名为 `PhotonicModulator` 的内部线程。
* **触发更新:** 当上述状态发生变化时（例如亮度改变），`DisplayPowerState` 会调用 `scheduleScreenUpdate()`。这会向 `mHandler` 发送一个 `mScreenUpdateRunnable`。
* **提交给 Modulator:** `mScreenUpdateRunnable` 会调用 `mPhotonicModulator.setState()`，将最新的状态（`mScreenState`, `mScreenBrightness` 等）传递给 `PhotonicModulator` 线程。
* **后台执行:** `PhotonicModulator` 线程在一个无限循环中运行。当它收到新的状态时，会调用 `mBlanker.requestDisplayState()`。
    * `mBlanker` 是 `DisplayBlanker` 接口的实例，通常由 `DisplayManagerService` 实现。
    * `requestDisplayState` 最终会通过 JNI 调用到底层 SurfaceFlinger 或 HAL 层，执行实际的硬件操作（如设置背光亮度、开关屏幕电源）。

**3. 动画与过渡效果 (ColorFade)**

* **ColorFade:** `DisplayPowerState` 管理着一个 `ColorFade` 对象（在代码中看到相关逻辑）。这是一个用于屏幕开关机动画的组件（例如旧版本的 CRT 关机动画或简单的淡入淡出）。
* **协调:** 当屏幕状态改变时（例如从 OFF 变到 ON），`DisplayPowerState` 会协调 `ColorFade` 的绘制和屏幕电源状态的切换。
    * 它可能会先使用 `ColorFade` 绘制一个黑色遮罩。
    * 然后请求底层打开屏幕电源（此时屏幕显示内容被遮罩挡住）。
    * 最后通过动画逐渐改变 `mColorFadeLevel`（从 0 到 1），移除遮罩，从而实现平滑的亮屏效果。
* **Choreographer:** `DisplayPowerState` 使用 `Choreographer` 来调度 `ColorFade` 的绘制（`scheduleColorFadeDraw`），确保动画与屏幕刷新率同步。

**4. 状态同步与回调 (Clean Listener)**

* `DisplayPowerState` 提供了一个 `waitUntilClean(Runnable listener)` 方法。
* `DisplayPowerController` 使用这个方法来等待屏幕状态完全应用。
* 当 `PhotonicModulator` 完成硬件状态更新（`mScreenReady = true`）**且** `ColorFade` 动画也处于就绪状态（`mColorFadeReady = true`）时，`DisplayPowerState` 会执行回调通知 `DisplayPowerController`。这确保了上层逻辑知道何时显示屏真正完成了状态转换。

### **总结**

简单来说，`DisplayPowerState` 是一个中间层：
1.  **接收指令：** 从 `DisplayPowerController` 接收“我要把屏幕亮度设为 0.5”或“我要关屏”的指令。
2.  **解耦：** 将这些指令缓存起来，并通过 `PhotonicModulator` 线程异步执行，防止卡顿。
3.  **美化：** 管理 `ColorFade` 动画，让屏幕开关过程更平滑。
4.  **反馈：** 当硬件操作真正完成后，通知上层。

它确保了显示策略（Controller）与显示硬件执行（Blanker/HAL）之间的平滑、非阻塞交互。

## SurfaceFlinger中屏幕的检测

![](/ethenslab/images/android-13-surfaceflinger-display-add.png)