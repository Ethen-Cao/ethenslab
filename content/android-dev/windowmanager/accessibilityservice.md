## 简介

## 架构

Android 无障碍系统的整体架构采用了典型的 **Hub-and-Spoke (星型/中介)** 拓扑结构。在这个架构中，无论是目标应用还是无障碍服务，都不会进行点对点的直接通信，所有的跨进程交互（IPC）必须经过 SystemServer 进程中的系统服务进行安全校验和路由转发。

整个架构可以清晰地划分为三个核心域（Block）：**target应用**、**SystemServer** 和 **AccessibilityService**。

### 核心组件关系图

```mermaid
graph TD
    %% 定义样式
    classDef app fill:#e1f5fe,stroke:#4fc3f7,stroke-width:2px,color:#01579b;
    classDef system fill:#fff3e0,stroke:#ffb74d,stroke-width:2px,color:#e65100;
    classDef service fill:#e8f5e9,stroke:#81c784,stroke-width:2px,color:#1b5e20;

    subgraph TargetApp ["1. target应用 (Client Process)"]
        direction TB
        ViewTree["View Tree / UI层次结构"]
        VRI["ViewRootImpl<br>(窗口根视图)"]
        AIC_App["AccessibilityInteractionConnection<br>(响应系统转发的节点查询)"]
        
        ViewTree --- VRI
        VRI -->|挂载时注册| AIC_App
    end

    subgraph SystemServer ["2. SystemServer (System Process)"]
        direction TB
        ID["InputDispatcher<br>(Native: 拦截底层输入事件)"]
        AIF["AccessibilityInputFilter<br>(拦截事件与手势识别)"]
        AMS["AccessibilityManagerService<br>(中枢路由与权限校验)"]
        AWM["AccessibilityWindowManager<br>(Window与全系统连接管理)"]
        
        ID -->|"InputEvent"| AIF
        AIF -->|"上报特征事件/手势"| AMS
        AMS --- AWM
    end

    subgraph AccService ["3. AccessibilityService (Service Process)"]
        direction TB
        AS_Dev["开发者自定义的<br>AccessibilityService"]
        AIC_Client["AccessibilityInteractionClient<br>(缓存池与主动查询代理)"]
        ASC_Wrapper["IAccessibilityServiceClientWrapper<br>(接收系统下行推送)"]
        
        AIC_Client <-- "调用 API" --> AS_Dev
        ASC_Wrapper -->|"回调 onAccessibilityEvent 等"| AS_Dev
    end

    %% 跨进程通信 IPC 连线
    AIC_App <==>|"IPC (注册与返回结果)"| AWM
    AMS ==>|"IPC: 下行通道 (推送事件/手势)"| ASC_Wrapper
    AIC_Client ==>|"IPC: 上行通道 (主动拉取节点/执行Action)"| AMS

    %% 应用样式
    class TargetApp app;
    class SystemServer system;
    class AccService service;
```

### 架构域功能解析

1. **target应用 (被操作的目标 App)**
   - 目标应用在它的 UI 挂载（`ViewRootImpl` 创建）时，会主动向系统注册一个 `AccessibilityInteractionConnection`（AIDL 的 Binder 对象）。
   - 它的职责是被动的：只有当收到系统转发来的查询指令时，它才会在自己的主线程或专用线程中遍历 `View Tree`，将真实的 View 转换为跨进程安全的扁平结构 `AccessibilityNodeInfo`，然后打包返回。

2. **SystemServer (安全与路由中枢)**
   - **底层的事件拦截**：`InputDispatcher` 将硬件事件拦截，并交给 `AccessibilityInputFilter` 进行分析（例如区分普通点击和双指滑动探索手势）。
   - **`AccessibilityManagerService` (AMS)**：它是整个架构的大脑。它负责启动和绑定无障碍服务、校验所有请求的权限。
   - **`AccessibilityWindowManager` (AWM)**：掌管着全系统所有目标应用的 Window 映射表。它是实现“隔山打牛”的关键，能够精确地将 `AccessibilityService` 发出的请求路由到具体的 `target应用`。

3. **AccessibilityService (无障碍服务提供方)**
   - **下行通道接受者 (`IAccessibilityServiceClientWrapper`)**：它是一个被动接收器，用于接收 AMS 推送过来的屏幕焦点变化、窗口状态改变或用户手势等事件。
   - **上行查询代理 (`AccessibilityInteractionClient`)**：当开发者在代码中调用 `getRootInActiveWindow()` 时，实际上是通过这个类代理发起跨进程的 IPC 请求。它内部自带了节点缓存池（Node Cache），并在缓存未命中时向 AMS 发出查询指令。

## AccessibilityService实现详解

以下类图深入展示了这三个架构域内部核心类之间的组合、接口实现以及基于 Binder 的跨进程交互关系，它精准还原了事件查询与回调的底层闭环：

```mermaid
classDiagram

    %% ==========================================
    %% 1. Target App (Client) Domain
    %% ==========================================
    class ViewRootImpl {
        +AccessibilityInteractionConnectionManager
        +ensureConnection()
    }
    class AccessibilityInteractionConnection {
        +findAccessibilityNodeInfosByXXX()
        +findFocus()
    }
    class IAccessibilityInteractionConnection {
        <<interface>>
    }

    ViewRootImpl *-- AccessibilityInteractionConnection : 内部实例化与持有
    AccessibilityInteractionConnection ..|> IAccessibilityInteractionConnection : 实现 (Stub)

    %% ==========================================
    %% 2. System Server Domain
    %% ==========================================
    class AccessibilityManager {
        <<proxy>>
        +addAccessibilityInteractionConnection()
    }
    class AccessibilityManagerService {
        +bindLocked()
    }
    class AccessibilityWindowManager
    class RemoteAccessibilityConnection {
        -IBinder mLeashToken
        -int mWindowId
    }
    class AccessibilityServiceConnection {
        +onMotionEvent()
    }
    class IAccessibilityServiceConnection {
        <<interface>>
    }

    ViewRootImpl ..> AccessibilityManager : 调用跨进程注册
    AccessibilityManager ..> AccessibilityManagerService : IPC (Binder Call)
    AccessibilityManagerService --> AccessibilityWindowManager : 委托管理 Window 连接
    AccessibilityWindowManager *-- RemoteAccessibilityConnection : 包装并分配 windowId
    RemoteAccessibilityConnection --> IAccessibilityInteractionConnection : 持有TargetApp的查询代理
    AccessibilityManagerService *-- AccessibilityServiceConnection : 绑定时创建并持有
    AccessibilityServiceConnection ..|> IAccessibilityServiceConnection : 实现 (Stub)

    %% ==========================================
    %% 3. Accessibility Service Domain
    %% ==========================================
    class AccessibilityService
    class AccessibilityInteractionClient {
        <<Singleton>>
        -SparseArray sConnectionCache
        +getInstance()
        +addConnection()
    }
    class IAccessibilityServiceClientWrapper
    class IAccessibilityServiceClient {
        <<interface>>
    }
    class IAccessibilityInteractionConnectionCallback {
        <<interface>>
        +setFindAccessibilityNodeInfosResult()
    }

    AccessibilityService *-- IAccessibilityServiceClientWrapper : onBind 时创建
    IAccessibilityServiceClientWrapper ..|> IAccessibilityServiceClient : 实现 (Stub)
    AccessibilityServiceConnection --> IAccessibilityServiceClient : 持有服务的回调代理 (下行)
    
    AccessibilityService ..> AccessibilityInteractionClient : 主动请求 API
    AccessibilityInteractionClient --> IAccessibilityServiceConnection : 从缓存提取并调用 (上行)
    
    %% --- 跨进程查询与回调闭环 ---
    AccessibilityInteractionClient ..> IAccessibilityInteractionConnectionCallback : 查询时附带 Callback 实体
    AccessibilityInteractionConnection ..> IAccessibilityInteractionConnectionCallback : 遍历完成 IPC 返回结果
```

## 关键流程

### AccessibilityService的启动与连接建立

无障碍服务（AccessibilityService）本质上是一个标准的 Android `Service`。它的生命周期由系统严格控制，主要经过“状态监听 -> 绑定服务 -> 双向握手 -> 连接回调”四个阶段。

#### 1. 启动时序图

以下是用户从“设置”中手动开启无障碍服务时，系统拉起该服务并建立双向通信通道的时序图：

```mermaid
sequenceDiagram
    participant User as 用户 (Settings App)
    participant Setting as Settings.Secure
    participant AMS as AccessibilityManagerService
    participant ASC as AccessibilityServiceConnection
    participant ActMS as ActivityManagerService
    participant AS as AccessibilityService (App进程)
    participant AIC as AccessibilityInteractionClient

    %% 1. 触发与监听
    rect rgb(240, 248, 255)
    Note over User, AMS: 1. 开启服务与状态监听
    User->>Setting: 打开开关，写入 ENABLED_ACCESSIBILITY_SERVICES
    Setting-->>AMS: 触发 ContentObserver 监听变化
    AMS->>AMS: 解析白名单，决定启动目标服务
    end

    %% 2. 绑定服务
    rect rgb(255, 250, 240)
    Note over AMS, ActMS: 2. 发起绑定请求
    AMS->>ASC: 实例化并调用 bindLocked()
    ASC->>ActMS: bindServiceAsUser(Intent)
    ActMS->>AS: 跨进程拉起 App 并创建 Service
    end

    %% 3. 建立下行通道 (System -> App)
    rect rgb(245, 255, 245)
    Note over ActMS, AS: 3. onBind 返回下行通道句柄
    AS->>AS: 执行 onBind() (被框架 final 修饰)
    AS->>AS: 创建 IAccessibilityServiceClientWrapper
    AS-->>ActMS: 返回 Binder (IAccessibilityServiceClient)
    ActMS-->>ASC: onServiceConnected回调，获得下行句柄
    end

    %% 4. 双向握手与初始化
    rect rgb(255, 245, 245)
    Note over ASC, AS: 4. 双向握手与服务回调
    ASC->>AS: init(IAccessibilityServiceConnection, windowToken)
    Note right of ASC: AMS 将自己包装的上行通道<br/>(IAccessibilityServiceConnection) 传给 App
    AS->>AIC: 将上行句柄配置到 AccessibilityInteractionClient 的缓存中
    AS->>AS: 内部派发 dispatchServiceConnected()
    AS->>AS: 回调开发者覆写的 onServiceConnected()
    Note right of AS: 此时双向通信建立完毕，<br/>开发者可开始正常调用 API
    end
```

#### 2. 启动流程核心解析

**触发时机**
除了用户在“设置”中手动开启外，以下场景也会触发 `AccessibilityManagerService` (AMS) 对服务的 `bindService`：
- 设备开机或用户解锁（User Unlocked）后，AMS 会重新拉起记录在设置白名单中的服务。
- 已经开启的无障碍应用被覆盖安装（更新）或崩溃后，AMS 会尝试重新绑定（Rebind）。

**强管控的 `onBind` 与双向通信架构**
在 `AccessibilityService` 源码中，`onBind(Intent)` 方法是被标记为 `final` 的，开发者**无法重写它**。这是因为 Android 框架需要在这个阶段插入极其关键的双向 IPC（跨进程通信）逻辑：
1. **下行通道（System -> App）**：框架在 `onBind` 中实例化一个内部类 `IAccessibilityServiceClientWrapper` 并将其 Binder 句柄返回给 AMS。这是系统将屏幕事件（如焦点变化、手势）**推送（Push）**给 App 的通道。
2. **上行通道（App -> System）**：AMS 在拿到下行句柄后，会立刻调用它的 `init()` 方法，并将 AMS 侧生成的 `IAccessibilityServiceConnection` 作为参数传回给 App。
3. **中央路由管理**：App 收到上行通道句柄后，会将其保存在 `AccessibilityInteractionClient` 中（`sConnectionCache`）。之后当 App 想要主动请求节点数据（如 `getRootInActiveWindow()`）或下发点击指令时，就会使用这个上行通道。

当这套双向“握手”流程在框架层暗中全部执行完毕后，系统才会通过内部的 Handler 回调通知开发者重写的 `onServiceConnected()` 方法。因此，开发者执行服务初始化的正确入口点永远是 `onServiceConnected()`。

### InputEvent事件的处理

当系统开启无障碍服务（尤其是触摸浏览 Touch Exploration 或屏幕阅读器功能）时，`InputEvent` 会被 `AccessibilityInputFilter` 拦截并处理，以决定事件是应该被消费、修改还是放行。整体流程跨越了 Native 层（InputDispatcher）、JNI 层以及 Java 层的多项服务。

#### 1. 核心流程概述

事件处理主要分为四个关键阶段：
1. **事件拦截 (Interception)**：底层硬件产生的输入事件在 `InputDispatcher` 分发前，会通过策略方法层层上调，最终到达 `AccessibilityInputFilter`。
2. **异步分发 (Asynchronous Dispatch)**：为了不阻塞 Native 的输入管线，`AccessibilityInputFilter` 会将事件通过 Handler ( `MSG_INPUT_EVENT` ) 放入消息队列异步处理。
3. **特征处理 (Feature Processing)**：诸如 `TouchExplorer` 等模块接收并解析手势，根据用户的操作将相应的事件报告给 `AccessibilityManagerService`。
4. **事件回传与注入 (Injection/Dispatching)**：对于需要传递给应用层消费的事件（例如经过无障碍系统确认的正常点击或修改后的事件），会被重新注入到底层 `InputDispatcher` 中进行常规分发。

#### 2. 事件处理时序图

以下是完整的系统调用时序，展现了从事件拦截到无障碍系统处理，最终回传注入的代码执行路径：

```mermaid
sequenceDiagram
    participant ID as InputDispatcher<br>(Native)
    participant NIM as NativeInputManager<br>(JNI)
    participant IMS as InputManagerService<br>(Java)
    participant AIF as AccessibilityInputFilter<br>(Java)
    participant TE as TouchExplorer<br>(Java)
    participant AMS as AccessibilityManagerService<br>(Java)

    %% 1. 事件拦截阶段
    rect rgb(240, 248, 255)
    Note over ID, AIF: 1. 事件拦截阶段
    ID->>NIM: filterInputEvent()
    NIM->>IMS: filterInputEvent() (JNI调用)
    IMS->>AIF: filterInputEvent() (InputFilter实现)
    AIF->>AIF: 包装事件并发送 MSG_INPUT_EVENT
    AIF-->>IMS: 返回 false (表示需要拦截/异步处理)
    IMS-->>NIM: 返回 false
    NIM-->>ID: 返回 false (Native层放弃常规分发)
    end

    %% 2. 异步处理阶段
    rect rgb(245, 255, 245)
    Note over AIF, TE: 2. 异步事件处理阶段 (Handler)
    AIF->>AIF: handleMessage(MSG_INPUT_EVENT)
    AIF->>AIF: onInputEvent()
    AIF->>AIF: onInputEventInternal()
    AIF->>AIF: processMotionEvent()
    AIF->>TE: onMotionEvent()
    end

    %% 3 & 4. 路由与分发 (条件分支)
    rect rgb(255, 250, 240)
    Note over ID, AMS: 3 & 4. 路由与分发 (基于事件类型的条件分支)
    alt 事件作为无障碍手势或动作被消费 (例如滑动探索)
        %% 3. 无障碍服务分发阶段
        Note over TE, AMS: 3. 向无障碍服务发送事件
        TE->>AMS: sendMotionEventToListeningServices()
        AMS->>AMS: scheduleNotifyMotionEvent() (通知监听的服务)
    else 事件透传或被转化为普通点击 (例如双击屏幕)
        %% 4. 事件回传与注入阶段
        Note over ID, AIF: 4. 事件回传与注入
        AIF->>AIF: sendInputEvent() (父类 InputFilter 方法)
        AIF->>IMS: InputFilterHost.sendInputEvent()
        IMS->>NIM: NativeInputManagerService.injectInputEvent()
        NIM->>ID: injectInputEvent() (JNI转Native)
        Note right of ID: 事件回到 InputDispatcher 继续常规分发逻辑
    end
    end
```

#### 3. 核心源码逻辑解析

- **Native层的拦截钩子**：
  在 `InputDispatcher` 的派发流程中，会调用 `mPolicy.filterInputEvent`（实际指向 `NativeInputManager`）。`NativeInputManager` 通过 JNI 获取 Java 层 `InputManagerService` 对象的 `filterInputEvent` 方法，从而将判断逻辑转移到 Java 层。

- **AccessibilityInputFilter 的异步化**：
  Java 层 `InputManagerService.filterInputEvent` 会调用注册在其中的 `InputFilter` (即 `AccessibilityInputFilter`)。
  当 `AccessibilityInputFilter.filterInputEvent` 被调用时，为了避免 JNI 调用阻塞底层的输入事件处理循环，它会将当前的 `InputEvent` 复制并封装进一个 `Message` (标识为 `MSG_INPUT_EVENT`)，发送给自带的 `Handler`，然后直接向底层返回 `false`。
  底层收到 `false` 后会丢弃此次常规派发，将控制权完全交给无障碍系统处理。

- **条件分支：处理与消费 vs 回传与注入**：
  在 Handler 触发 `processMotionEvent` 并进入 `TouchExplorer` 等模块后，针对单一事件，处理逻辑在第3步和第4步之间呈现 **条件分支 (alt)** 的关系：
  - **路径 A (对应步骤 3)**：如果事件属于无障碍手势的一部分（如单指触摸探索、多指滑动），它会被无障碍系统**消费**。系统会调用 `AccessibilityManagerService.sendMotionEventToListeningServices`，将事件转化为反馈信息（如让 TalkBack 播报焦点）发送给监听的无障碍服务。此时，这个事件**不会**被注入回 View 树。
  - **路径 B (对应步骤 4)**：如果事件判定为无关手势的纯透传事件（如悬停外围），或者是由无障碍手势转化而来的普通操作（例如，连续双击被识别为一次普通的 Click），那么无障碍系统会放行（或重新构造）该事件。调用链路会走向 `super.onInputEvent`，通过 JNI 的 `injectInputEvent` 将事件重新注入 `InputDispatcher`。此时，事件重新进入正常的 View 树分发流程。

### AccessibilityInteractionConnection的注册流程

为了让无障碍系统（Accessibility System）能够查询和操作应用的 UI 节点，应用在创建 Window 时需要主动向系统注册其 `AccessibilityInteractionConnection`。这个注册过程紧随 Activity 的生命周期，并在 View 树挂载到 Window 时触发，同时也受到全局无障碍状态的动态控制。

#### 1. 注册的触发时机与动态管理

注册的发起点在应用进程的 `ViewRootImpl` 中。为了避免在未开启无障碍服务时产生额外的跨进程通信开销，Android 采用了**懒加载与动态监听**的机制。

其核心类是 `ViewRootImpl` 的内部类 `AccessibilityInteractionConnectionManager`，它实现了 `AccessibilityStateChangeListener` 接口。注册的触发通常有两个入口：

1. **Window 首次挂载时触发**：
   在 `ActivityThread.handleResumeActivity` 阶段，Activity 即将变为可见状态。系统通过 `WindowManagerGlobal.addView` 将 `DecorView` 添加到 Window 中，此时会创建并初始化 `ViewRootImpl`。在 `ViewRootImpl.setView()` 方法内部，系统会检查当前的全局无障碍状态，若已开启则直接注册：
   ```java
   if (mAccessibilityManager.isEnabled()) {
       mAccessibilityInteractionConnectionManager.ensureConnection();
   }
   ```

2. **全局无障碍状态动态变更时触发**：
   如果应用启动时并未开启无障碍服务，之后用户在系统设置中打开了服务。由于 `AccessibilityInteractionConnectionManager` 监听了状态变化，它的 `onAccessibilityStateChanged(boolean enabled)` 会被回调：
   ```java
   public void onAccessibilityStateChanged(boolean enabled) {
       if (enabled) {
           ensureConnection();
           // ...
       } else {
           ensureNoConnection(); // 动态解绑，防止资源泄漏
       }
   }
   ```

#### 2. 跨进程注册与 mLeashToken 的缝合机制

当 `ensureConnection()` 被调用时，应用内部会实例化一个 `AccessibilityInteractionConnection`（这是一个实现了 AIDL 接口的 Binder 本地对象，专门负责处理系统下发的无障碍查询指令）。

接着，它会通过 `AccessibilityManager.addAccessibilityInteractionConnection()` 跨进程调用 System Server 端的 `AccessibilityManagerService`。在这个跨进程调用中，传递了几个极其关键的参数：
- `mWindow`: 当前 Window 的跨进程 Token (`IWindow`)。
- `connection`: 刚刚实例化的用来接收查询指令的 Binder 句柄。
- `mLeashToken`: `ViewRootImpl` 的匿名身份凭证。

**重点解析 `mLeashToken` 的作用：**
`mLeashToken` 是在 `ViewRootImpl` 创建时初始化的一个匿名 `Binder` 对象。它的核心作用是**标识并缝合跨 Window 的嵌入式视图层级（Embedded View Hierarchy）**。
- 从 Android 11 开始，应用可以使用 `SurfaceControlViewHost` 将一个 View 树渲染到独立的 `SurfaceControl` 上，并将其嵌入到其他宿主（Host）Window 中。
- 在底层的图形渲染层，它们是拼接在一起的，但在无障碍系统的逻辑视角里，宿主和嵌入视图属于两个断裂的 Window。
- **缝合机制**：宿主会将自己的 Token 传递给嵌入方的 `ViewRootImpl`。嵌入方收到后，会调用 AMS，将其 `mLeashToken`（作为身份凭证）与宿主的 Token 进行绑定（`associateEmbeddedHierarchy`）。当读屏软件（如 TalkBack）遍历宿主节点并请求其子节点时，底层通过这个映射关系，利用 `mLeashToken` 找到嵌入层 `ViewRootImpl`，从而将两棵断裂的节点树“无缝缝合”成一棵完整的树。

#### 3. System Server 端的集中管理：AccessibilityWindowManager

注册请求最终会交由 System Server 端的 `AccessibilityWindowManager` 集中管理。它是全局所有跨进程无障碍交互连接的“大管家”。

**核心机制：**
- **连接包装与死亡监听**：它收到 App 传来的 `IAccessibilityInteractionConnection` Binder 句柄后，会将其包装成一个 `RemoteAccessibilityConnection` 对象，并向该 Binder 注册死亡监听（DeathRecipient）。如果目标 App 进程崩溃，系统能立即感知并清理失效的连接，防止内存泄漏或产生无效的查询路由。
- **WindowId 的分配与路由**：每次注册成功，`AccessibilityWindowManager` 都会为这个连接分配一个全局递增的 `windowId`。之后无障碍服务（如 TalkBack）只需提供这个 `windowId`，AMS 就能精确路由到对应的 App Window 并发起节点查询。
- **多用户与全局状态隔离**：它内部维护了多套映射表。跨用户的系统 Window（如 SystemUI）被分配在全局映射表（`mGlobalInteractionConnections`）中，而普通 App Window 则是按 userId 隔离，存放于各自的映射表（`mInteractionConnections`）中。

**AccessibilityWindowManager 机制类图：**

```mermaid
classDiagram
    class AccessibilityWindowManager {
        -int sNextWindowId
        -SparseArray~IBinder~ mWindowIdMap
        -SparseArray~RemoteAccessibilityConnection~ mGlobalInteractionConnections
        -SparseArray~SparseArray<RemoteAccessibilityConnection>~ mInteractionConnections
        -ArrayMap~IBinder, IBinder~ mHostEmbeddedMap
        +addAccessibilityInteractionConnection(...)
        +getConnectionLocked(userId, windowId)
        +registerIdLocked(leashToken, windowId)
        +associateEmbeddedHierarchyLocked(host, embedded)
    }

    class RemoteAccessibilityConnection {
        -int mWindowId
        -int mUid
        -String mPackageName
        -IAccessibilityInteractionConnection mConnection
        +linkToDeath()
        +binderDied()
    }

    class IAccessibilityInteractionConnection {
        <<interface>>
        +findAccessibilityNodeInfoByAccessibilityId(...)
        +findAccessibilityNodeInfosByText(...)
        +performAccessibilityAction(...)
    }

    AccessibilityWindowManager --> "0..*" RemoteAccessibilityConnection : 管理并路由
    RemoteAccessibilityConnection *-- IAccessibilityInteractionConnection : 包装App端通信句柄
    AccessibilityWindowManager ..> IAccessibilityInteractionConnection : 接收并保存
```

#### 4. 跨进程获取 View 树的 Hub-and-Spoke 模型

目标应用（App）与无障碍服务（AccessibilityService）之间**不会进行点对点（P2P）直连**。所有的跨进程节点查询通信必须经过 System Server 进程中的 `AccessibilityManagerService` (AMS) 作为安全中介进行路由。

整个交互过程通过回调和事件转发实现，时序图及详细步骤如下：

```mermaid
sequenceDiagram
    participant AS as AccessibilityService<br>(Service)
    participant AIC as AccessibilityInteractionClient<br>(Service)
    participant AMS as AccessibilityManagerService<br>(System)
    participant AWM as AccessibilityWindowManager<br>(System)
    participant App as 目标应用 ViewRootImpl<br>(App)
    participant AppConn as AccessibilityInteractionConnection<br>(App)

    %% 1. App注册阶段
    rect rgb(240, 248, 255)
    Note over App, AWM: 1. 目标应用向系统注册连接
    App->>App: ensureConnection()
    App->>AppConn: 实例化 Binder 对象
    App->>AMS: addAccessibilityInteractionConnection(Binder Proxy)
    AMS->>AWM: 保存到内部映射表(以 windowId 为 Key)
    Note right of AMS: AMS 掌握了全系统所有 App Window 的控制句柄，<br/>但具体的 AccessibilityService 对此一无所知。
    end

    %% 2. 发起查询阶段
    rect rgb(255, 250, 240)
    Note over AS, AMS: 2. AccessibilityService 发起查询请求
    AS->>AIC: getRootInActiveWindow()
    AIC->>AIC: 查找当前的 Active Window ID
    AIC->>AMS: findAccessibilityNodeInfoByAccessibilityId(windowId, Callback)
    Note right of AIC: 使用上行通道 IAccessibilityServiceConnection，<br/>带上目标 windowId 和接收结果的 Callback
    end

    %% 3. AMS路由阶段
    rect rgb(255, 245, 245)
    Note over AMS, AppConn: 3. AMS 校验并路由请求
    AMS->>AMS: 严格权限校验 (如 canRetrieveWindowContent)
    AMS->>AWM: 根据 windowId 查找 AppConn 句柄
    AWM-->>AMS: 返回 IAccessibilityInteractionConnection 句柄
    AMS->>AppConn: 转发查询指令和 Callback
    end

    %% 4. 数据打包回调阶段
    rect rgb(245, 255, 245)
    Note over AppConn, AIC: 4. 目标应用打包数据并异步返回
    AppConn->>AppConn: 遍历 View 树
    AppConn->>AppConn: 转换为 AccessibilityNodeInfo 扁平结构
    AppConn->>AIC: callback.setFindAccessibilityNodeInfosResult(infos)
    Note right of AppConn: 直接或经路由跨进程异步返回给 Callback
    AIC-->>AS: 返回最终的节点数据
    end
```

1. **目标应用向系统“注册”连接 (App -> AMS)**
   当系统开启了无障碍服务后，目标应用在创建 Window（即 `ViewRootImpl` 实例化）时，会执行 `ensureConnection()`：
   - 目标应用内部实例化一个 `AccessibilityInteractionConnection`（这是一个实现了 AIDL 接口的 Binder 本地对象）。
   - 目标应用调用 `mAccessibilityManager.addAccessibilityInteractionConnection(...)` 将这个 Binder 的跨进程句柄（Proxy）发送给了 AMS。
   - AMS 收到后，会将其保存在 `AccessibilityWindowManager` 的内部映射表中（以 `windowId` 为 Key）。
   > **此时：** AMS 掌握了全系统所有 App Window 的控制句柄，但具体的 `AccessibilityService` 对此一无所知。

2. **AccessibilityService 发起查询请求 (Service -> AMS)**
   当你的 `AccessibilityService` 想要获取当前屏幕的 View 树（例如调用了 `getRootInActiveWindow()`）：
   - `AccessibilityInteractionClient` 会查找到当前的 Active Window ID。
   - 它通过自己持有的 `IAccessibilityServiceConnection`（上行通道），向 AMS 发起一个查询请求，比如 `findAccessibilityNodeInfoByAccessibilityId`。
   - 在这个请求中，它会带上目标窗口的 `windowId`，并传入一个用于接收结果的回调接口（`IAccessibilityInteractionConnectionCallback`）。

3. **AMS 校验并路由请求 (AMS -> App)**
   - AMS 收到查询请求后，首先进行严格的权限校验（比如该 Service 是否声明了获取窗口内容的权限 `canRetrieveWindowContent`）。
   - 校验通过后，AMS 根据请求里的 `windowId`，从自己的映射表中找出第一步里目标应用注册的那个 `IAccessibilityInteractionConnection` 句柄。
   - AMS 将查询指令以及接收结果的 Callback，通过这个句柄转发（Forward）给目标应用。

4. **目标应用打包数据并异步返回 (App -> Service)**
   - 目标应用的 `AccessibilityInteractionConnection` 收到了来自 AMS 转发的指令。
   - 它会在自己的 UI 线程（或者专门的无障碍处理线程）中遍历自己的 View 树，将真实的 View 对象转换、拷贝成一个个扁平的、跨进程安全的数据结构：`AccessibilityNodeInfo`。
   - 打包完成后，目标应用利用第 2 步中一路传过来的 Callback 句柄，调用 `callback.setFindAccessibilityNodeInfosResult(infos)`。
   - 由于这个 Callback Binder 是在 `AccessibilityService` 进程中创建的，这一步的数据会跨进程直接或经 AMS 路由返回给 `AccessibilityService` 的 `AccessibilityInteractionClient`。

### 5. onAccessibilityEvent的生成与下发流程

当目标应用的 UI 发生变化（例如窗口切换、控件点击、列表滚动）时，它是如何将这些状态变化通知给无障碍服务的？这个过程与主动查询（Hub-and-Spoke 模型）方向相反，是目标应用主动“上报”，System Server 再“广播下发”给各无障碍服务的过程。

#### 5.1 事件流转时序图

以下展示了从目标 App 发生点击事件，直到 `AccessibilityService.onAccessibilityEvent()` 被回调的完整跨进程链路：

```mermaid
sequenceDiagram
    participant View as View / ViewRootImpl<br>(Target App)
    participant AM as AccessibilityManager<br>(Target App)
    participant AMS as AccessibilityManagerService<br>(System Server)
    participant ASC as AccessibilityServiceConnection<br>(System Server)
    participant AS as AccessibilityService<br>(Service Process)

    %% 1. 事件生成与上报阶段
    rect rgb(240, 248, 255)
    Note over View, AMS: 1. 目标应用主动上报事件
    View->>View: 发生交互 (如 performClick)
    View->>View: sendAccessibilityEvent()
    View->>AM: 构建 AccessibilityEvent 并发送
    AM->>AMS: IPC: sendAccessibilityEvent(event, userId)
    end

    %% 2. 系统校验与广播阶段
    rect rgb(255, 250, 240)
    Note over AMS, ASC: 2. AMS 校验过滤与广播
    AMS->>AMS: 检查无障碍总开关与用户状态
    AMS->>AMS: 遍历当前活动的所有 ASC
    AMS->>ASC: notifyAccessibilityEvent(event)
    Note right of ASC: 每个已连接的服务（如TalkBack、语音助手）<br/>都有一个对应的 ASC 代理
    end

    %% 3. IPC 下发与服务接收阶段
    rect rgb(245, 255, 245)
    Note over ASC, AS: 3. 下行推送与业务分发
    ASC->>ASC: 检查服务配置 (EventTypes, PackageNames)
    Note right of ASC: 根据你在 xml 中配置的过滤条件决定是否放行
    ASC->>AS: IPC: onAccessibilityEvent(event)<br>via IAccessibilityServiceClient
    AS->>AS: Handler 切回主线程
    AS->>AS: 回调开发者覆写的 onAccessibilityEvent()
    end
```

#### 5.2 流程与配置解析

1. **事件的源头 (App -> AMS)**：
   Android 框架中的原生 UI 组件（如 `Button`, `TextView`, `RecyclerView`）在它们的核心状态发生改变时（如点击、内容变化、滑动），内部都会调用 `sendAccessibilityEvent()`。该方法会实例化一个 `AccessibilityEvent` 对象，装载包名、类名、文本内容等快照信息，并通过进程内的 `AccessibilityManager` (单例) 跨进程发送给 System Server 的 `AMS`。

2. **按需下发 (AMS 的过滤机制)**：
   System Server 并不是把所有事件都无脑广播给每一个 `AccessibilityService`。在 `AccessibilityServiceConnection.notifyAccessibilityEvent` 中，系统会严格比对该服务在 `accessibility-service.xml` 中声明的过滤配置：
   - **`accessibilityEventTypes`**：服务只关心配置中声明的事件（如只关心 `typeWindowContentChanged` 或 `typeViewClicked`）。
   - **`packageNames`**：如果配置了特定的包名，只有来自这些包的事件才会被放行；如果不配置，则接收全局事件。

3. **下行通道推送 (AMS -> Service)**：
   过滤通过后，AMS 使用建立连接时保存的下行通道（`IAccessibilityServiceClient`），单向且异步地将事件推送到无障碍服务进程，最终回调到开发者熟悉的 `onAccessibilityEvent(AccessibilityEvent event)` 方法中。

#### 5.3 常见 AccessibilityEvent 类型解析

在 `onAccessibilityEvent` 的回调中，包含了一个巨大的数据包 `AccessibilityEvent`。根据 `event.getEventType()`，开发者可以截获并分析不同维度的全局状态：

| 常用的 Event Type | 触发场景与业务意义 |
| :--- | :--- |
| **`TYPE_WINDOW_STATE_CHANGED`** | **最常用于判断前台应用切换或弹窗出现**。当 Activity 切换、Dialog 弹出、PopupWindow 显示时触发。它代表了宏观视窗焦点的绝对转移。 |
| **`TYPE_WINDOWS_CHANGED`** | 系统中全局 Window 集合发生变化（增加、移除、层级变化）。这比 state changed 更底层，常用于监控悬浮窗或系统级 UI 变动。 |
| **`TYPE_VIEW_CLICKED` / `TYPE_VIEW_LONG_CLICKED`** | 用户在屏幕上**点击/长按**了某个具体的 View（不仅是本应用，也包括其他应用的控件）。常用于自动化埋点或劫持特定操作。 |
| **`TYPE_VIEW_FOCUSED`** | 某个 UI 控件获取了焦点。对于非触摸设备（如车机旋钮、外接键盘）的交互逻辑适配至关重要。 |
| **`TYPE_WINDOW_CONTENT_CHANGED`** | **高频事件**。当界面上的 View 发生添加、移除、文本改变、可见性变化时高频触发。由于触发太频繁，通常需要在 xml 中谨慎配置，并在代码中配合 `DELAY_MILLISECONDS` 进行限流或消抖（Debounce）处理。 |
| **`TYPE_VIEW_SCROLLED`** | 列表（如 RecyclerView、ScrollView）发生滚动时触发。常用于“可见即可说”功能中判断当前列表是否已翻页，从而触发新的屏幕控件树抓取。 |


