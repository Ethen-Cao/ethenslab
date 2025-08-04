+++
date = '2025-07-29T10:22:54+08:00'
draft = false
title = 'WindowManagerService 解析'
+++

##  WindowManagerService 概述
WindowManagerService（简称WMS）是Android系统中负责窗口（Window）管理的核心系统服务。它是屏幕上所有可见元素的“总管家”，决定了所有窗口的外观、行为和交互方式。

作为Android框架层（Framework Layer）的关键部分，WMS随系统启动，并稳定运行在权限极高的 system_server 进程中。这个位置赋予了它管理所有应用窗口和系统窗口的最高权限。

WMS的角色像一个“总指挥”，它并不亲自执行所有底层操作，而是协调系统中的多个组件来共同完成对窗口的生命周期管理。其核心作用包括：

* 窗口的创建与管理 (Creation & Management): 与 ActivityManagerService (AMS) 协同工作。当AMS决定要显示某个Activity时，WMS负责为其创建和管理对应的窗口实例（WindowState）。

* 布局与计算 (Layout & Calculation): 通过自顶向下的遍历，精确计算出每个窗口在屏幕上的最终位置和尺寸（Frame），从而适配不同尺寸的屏幕以及分屏、小窗等各种显示模式。

* 层级与Z序 (Layer & Z-Order): 维护所有窗口的前后堆叠顺序（Z-Order），决定哪个窗口显示在最上层，哪个窗口被遮挡，确保界面元素以正确的次序呈现。

* 绘制与合成 (Drawing & Composition): WMS自身不负责绘制窗口内容。它管理窗口的绘图表面（Surface），并将所有窗口的元数据（位置、层级、透明度等）统一提交给 SurfaceFlinger，由后者完成最终的画面合成。

* 窗口动画 (Window Animation): 负责实现窗口切换、应用启动/退出、调整大小等过程中的过渡动画，为用户提供流畅的视觉体验。

* 输入事件分发 (Input Event Dispatching): 作为输入系统的关键一环，WMS接收原始的触摸、按键等事件，准确判断事件应该由哪个窗口接收，并交由 InputDispatcher 进行精确投递。

## 窗口的创建与管理
窗口的创建请求总是由应用进程发起的，WMS 则是请求的响应者和执行者。

![WindowState 创建时序示意图](/ethenslab/images/windowstate-creation.png)

**触发流程**：

* 应用层调用：当一个 Activity 的 onResume() 回调被触发，准备变得可见时，其内部的 PhoneWindow 会通过 WindowManager.addView() 方法将它的根视图（DecorView）添加到窗口中。这个调用是应用请求显示UI的起点。
* ViewRootImpl 的桥梁作用：addView() 的调用会创建一个名为 ViewRootImpl 的关键对象。ViewRootImpl 充当了应用UI和WMS之间的“信使”和“桥梁”。
* Binder IPC 调用：ViewRootImpl 通过一个名为 IWindowSession 的 Binder 接口，向 WMS 发起一个远程调用，通常是 addToDisplay()。这个调用会携带两个核心信息：
    * Window Token: 一个唯一的 Binder 令牌，用于将这个窗口与 AMS 中的 ActivityRecord 关联起来，WMS据此知道这个窗口属于哪个Activity。
    ![WindowToken创建与使用示意图](/ethenslab/images/windowtoken-creation-transport.png)
    * WindowManager.LayoutParams: 一个包含了窗口所有期望属性的参数集，如窗口的类型（应用窗口、系统窗口）、尺寸（MATCH_PARENT等）、标志（FLAG_NOT_FOCUSABLE等）和 gravity。

**WMS 的响应动作**：

* 权限验证：WMS 首先会检查调用者是否有权限添加所请求类型的窗口。例如，应用不能随意添加系统警报窗口（TYPE_APPLICATION_OVERLAY），这需要特殊权限。
* 创建 WindowState 实例：验证通过后，WMS 会 new WindowState(...)，创建一个新的 WindowState 对象。这个对象会保存所有从 LayoutParams 传递过来的属性。
* 创建绘图表面 (SurfaceControl)：紧接着，WMS 会为这个新的 WindowState 创建一个对应的 SurfaceControl。这是一个指向 SurfaceFlinger 中一个图层（Layer）的句柄，是窗口能够被看见和渲染的基础。
* 加入层级树：WMS 根据 Window Token 找到其归属的 Task 和 TaskFragment，然后将新创建的 WindowState 添加到这个容器的子节点列表中，完成了其在窗口层级树中的“注册”。
* 返回结果给应用：WMS 将 SurfaceControl 的信息以及其他必要的配置返回给应用进程的 ViewRootImpl。ViewRootImpl 收到后，就可以创建出应用侧的 Surface 对象，并开始组织第一次绘制。
* 调度布局：由于新窗口的加入改变了屏幕的整体布局，WMS 会将布局状态标记为“待定”（dirty），并在下一个合适的时机触发一次 WindowSurfacePlacer 的布局遍历。

一旦 WindowState 被创建并加入到层级树中，它就进入了被 WMS 持续管理的“活动”状态。管理主要体现在以下几个方面：
* 状态追踪：WindowState 内部维护了大量的状态标志，如是否可见、是否拥有焦点、是否正在播放动画、是否可以接收触摸事件等。WMS 会根据用户交互和系统事件不断更新这些状态。
* 布局与定位：在每一次 WindowSurfacePlacer 的布局遍历中，WMS 都会访问每一个 WindowState，读取其 LayoutParams，并结合其父容器的约束，计算出它最终的 Frame（位置和尺寸）。计算结果会通过 SurfaceControl 的事务（Transaction）更新到 SurfaceFlinger。
* 层级（Z-Order）调整：WMS 维护着一个所有窗口的Z序列表。当用户触摸某个窗口使其获得焦点时，WMS 会调整这个列表，将该窗口及其所属的 Task 提升到更高的层级，以确保它显示在最前面。
* 响应属性更新：应用可以通过 WindowManager.updateViewLayout() 方法在运行时修改窗口的 LayoutParams。这个请求会通过 Binder 发送到 WMS，WMS 会更新对应的 WindowState 对象的属性，并再次调度布局以应用变更。
* 输入事件路由：当触摸事件发生时，WMS（与 InputDispatcher 协同）会从Z序最高的窗口开始检查，判断触摸点是否落在该 WindowState 的 Frame 内，以及该窗口是否可以接收输入。一旦找到合适的目标，输入事件就会被派发给该窗口。

### Feature ID 
1. 什么是 Feature？
在 Android 窗口管理中，一个 "Feature" 通常指一项特定的、可以独立开关或管理的窗口功能。最典型的例子就是画中画（Picture-in-Picture）和分屏（Split-screen）。每个这样的功能都会在系统内部注册，并被分配一个唯一的整数ID，这个ID就是 mFeatureId。

2. 为什么需要 mFeatureId？
DisplayArea 是窗口的容器，它可以嵌套组织。当一个特殊功能（如画中画）需要一个专属的区域来管理它的窗口时，系统就会创建一个 DisplayArea。mFeatureId 在这里起到了关键的识别作用：

    * 唯一识别：系统可以通过这个 ID 快速找到由特定功能（比如画中-画）创建的根 DisplayArea。例如，当系统需要管理所有画中画窗口时，它就可以通过查找 featureId 为 FEATURE_PICTURE_IN_PICTURE 的 DisplayArea 来定位到它们的容器。

    * 功能归属：它明确了这个 DisplayArea 的“主人”是谁。这片区域内的窗口布局、行为和逻辑都应该遵循其所属功能的规则。

    * 逻辑隔离：通过这种方式，不同功能的窗口管理逻辑被清晰地隔离在各自的 DisplayArea 中，使得整个窗口管理体系（WindowContainer 树）更加清晰和模块化。

3. 示例：当用户开启一个画中画窗口时，系统会创建一个专门用于承载这个小窗口的 DisplayArea，并将其 mFeatureId 设置为 WindowManager.FEATURE_PICTURE_IN_PICTURE。在分屏模式下，主要和次要任务所在的区域也可能由带有特定 featureId 的 DisplayArea 来管理。

总之，mFeatureId 是一个内部标识，它将一个 DisplayArea 容器与创建它的特定窗口功能（如画中画）绑定在一起，方便系统进行识别、查找和管理。

系统预定义的 mFeatureId 主要定义在 android.window.DisplayAreaOrganizer 这个类中。这些ID代表了不同的、需要独立容器（DisplayArea）来管理的系统级窗口功能。

以下是系统当前主要的 mFeatureId 类型及其作用：

```java
    /**
     * The value in display area indicating that no value has been set.
     */
    public static final int FEATURE_UNDEFINED = -1;

    /**
     * The Root display area on a display
     */
    public static final int FEATURE_SYSTEM_FIRST = 0;

    /**
     * The Root display area on a display
     */
    public static final int FEATURE_ROOT = FEATURE_SYSTEM_FIRST;

    /**
     * Display area hosting the default task container.
     */
    public static final int FEATURE_DEFAULT_TASK_CONTAINER = FEATURE_SYSTEM_FIRST + 1;

    /**
     * Display area hosting non-activity window tokens.
     */
    public static final int FEATURE_WINDOW_TOKENS = FEATURE_SYSTEM_FIRST + 2;

    /**
     * Display area for one handed feature
     */
    public static final int FEATURE_ONE_HANDED = FEATURE_SYSTEM_FIRST + 3;

    /**
     * Display area that can be magnified in
     * {@link Settings.Secure.ACCESSIBILITY_MAGNIFICATION_MODE_WINDOW}. It contains all windows
     * below {@link WindowManager.LayoutParams#TYPE_ACCESSIBILITY_MAGNIFICATION_OVERLAY}.
     */
    public static final int FEATURE_WINDOWED_MAGNIFICATION = FEATURE_SYSTEM_FIRST + 4;

    /**
     * Display area that can be magnified in
     * {@link Settings.Secure.ACCESSIBILITY_MAGNIFICATION_MODE_FULLSCREEN}. This is different from
     * {@link #FEATURE_WINDOWED_MAGNIFICATION} that the whole display will be magnified.
     * @hide
     */
    public static final int FEATURE_FULLSCREEN_MAGNIFICATION = FEATURE_SYSTEM_FIRST + 5;

    /**
     * Display area for hiding display cutout feature
     * @hide
     */
    public static final int FEATURE_HIDE_DISPLAY_CUTOUT = FEATURE_SYSTEM_FIRST + 6;

    /**
     * Display area that the IME container can be placed in. Should be enabled on every root
     * hierarchy if IME container may be reparented to that hierarchy when the IME target changed.
     * @hide
     */
    public static final int FEATURE_IME_PLACEHOLDER = FEATURE_SYSTEM_FIRST + 7;

    /**
     * Display area hosting IME window tokens (@see ImeContainer). By default, IMEs are parented
     * to FEATURE_IME_PLACEHOLDER but can be reparented under other RootDisplayArea.
     *
     * This feature can register organizers in order to disable the reparenting logic and manage
     * the position and settings of the container manually. This is useful for foldable devices
     * which require custom UX rules for the IME position (e.g. IME on one screen and the focused
     * app on another screen).
     */
    public static final int FEATURE_IME = FEATURE_SYSTEM_FIRST + 8;

    /**
     * The last boundary of display area for system features
     */
    public static final int FEATURE_SYSTEM_LAST = 10_000;

    /**
     * Vendor specific display area definition can start with this value.
     */
    public static final int FEATURE_VENDOR_FIRST = FEATURE_SYSTEM_LAST + 1;

    /**
     * Last possible vendor specific display area id.
     * @hide
     */
    public static final int FEATURE_VENDOR_LAST = FEATURE_VENDOR_FIRST + 10_000;

    /**
     * Task display areas that can be created at runtime start with this value.
     * @see #createTaskDisplayArea(int, int, String)
     * @hide
     */
    public static final int FEATURE_RUNTIME_TASK_CONTAINER_FIRST = FEATURE_VENDOR_LAST + 1;
```

### WindowContainer层级管理

![WindowContainer层级管理](/ethenslab/images/DisplayContent.Token.png)

| 区域                                       | 说明                                          |
| ---------------------------------------- | ------------------------------------------- |
| **DisplayArea.Tokens (Wallpaper)**       | 管理 `WallpaperWindowToken`（壁纸窗口），Z-order 最低。 |
| **TaskDisplayArea (Default)**            | 管理普通应用任务（Activity 所在 Task）。                 |
| **DisplayArea (Split-screen)**           | 管理分屏模式窗口，包括主副屏的两个 TaskDisplayArea。          |
| **DisplayArea (PIP)**                    | 管理画中画窗口，Z-order 较高。系统动态决定其是否显示。             |
| **DisplayArea.Tokens (InputMethod)**     | 输入法专用窗口区域，显示时通常被置于较高层级。                     |
| **DisplayArea.Tokens (System Overlays)** | 管理弹窗、提示（如 Toast、Dialog、PopupWindow）。        |
| **DisplayArea.Tokens (StatusBar)**       | 通常为最顶层，用于状态栏、导航栏、系统通知等 SystemUI 组件。         |

### PictureInPicture 原理

![PiP创建流程](/ethenslab/images/pip.png)

流程文字说明
1. 触发 (用户按下 Home 键)

    用户在视频播放界面按下 Home 键。系统判断该 Activity 即将进入后台 (onUserLeaveHint())。

2. 系统检查与决策 (ATMS)

    ActivityTaskManagerService (ATMS) 截获这一事件，并检查该 Activity 是否满足自动进入 PiP 的所有条件（例如，在清单中声明支持、当前正处于特定状态等）。

3. 核心控制器介入 (PipTaskOrganizer)

    在现代 Android 中，PiP 的具体管理逻辑由一个名为 PipTaskOrganizer 的控制器负责。

4. ATMS 通知 PipTaskOrganizer：“这个 Task 准备进入 PiP 模式”。

    PipTaskOrganizer 会向应用请求详细的动画参数 (PictureInPictureParams)，其中最重要的就是 sourceRectHint，它告诉系统动画应该从屏幕的哪个区域开始，这保证了流畅的过渡效果。

5. 创建/获取 PiP 的 DisplayArea (WMS)

    这是流程的核心所在。PipTaskOrganizer 会向 WindowManagerService (WMS) 发出请求，确保一个用于 PiP 的专属容器存在。

6. WMS 会查找 featureId = FEATURE_PICTURE_IN_PICTURE 的 DisplayArea。

    如果该 DisplayArea 不存在（例如，这是系统开机后第一次进入 PiP），WMS 就会根据 DisplayAreaPolicy 的策略，在 DisplayContent 的子节点中创建一个新的 DisplayArea。这个 DisplayArea 的 Z-order 被设定得非常高，以确保它能浮在所有常规应用之上。如果已存在，则直接复用。

7. 任务重组 (Task Reparenting)

    一旦 PiP DisplayArea 准备就绪，WMS 会执行一个关键操作：将正在播放视频的应用所在的整个 Task，从它原来的父容器（通常是 TaskDisplayArea (Default)）中移除，然后添加为 PiP DisplayArea 的子节点。

    这个“移花接木”的操作，瞬间改变了该应用所有窗口的层级和管理策略。
    当视频从全屏切换到小窗口时，SurfaceFlinger 的工作流程是这样的：

    * 接收高清画布：SurfaceFlinger 持续从应用那里接收到 1920x1080 的高清视频帧，这些帧被绘制在 Surface（画布）上。

    * 收到变换指令：当 PiP 切换发生时，WMS 会通过 SurfaceControl.Transaction 给 SurfaceFlinger 下达一个新指令：“请将这个窗口显示在一个 320x180 的区域内”。

    * GPU 实时缩放：SurfaceFlinger 并不会告诉应用“请给我一个 320x180 的小画布”。相反，它会利用 GPU 的强大能力，在每一帧的合成阶段（大约每秒 60 次），将那个 1920x1080 的高清“画布”实时地、动态地缩小，然后绘制到屏幕上那个 320x180 的小区域里。

8. 动画与状态更新

    WMS 根据应用提供的 sourceRectHint 和目标位置，计算并执行一个平滑的过渡动画，将窗口从原始大小缩小并移动到屏幕角落。

    动画完成后，ATMS 会通过 Binder 回调通知应用，调用其 onPictureInPictureModeChanged(true) 方法，告知它已经成功进入 PiP 模式。应用可以在此回调中隐藏不需要的 UI 元素。

    同时，WMS 会通知 SystemUI PiP 状态已更新。

9. 用户交互 (SystemUI)

    SystemUI 会接管 PiP 窗口的“外壳”，在其上绘制关闭、设置、全屏等控制按钮。

    当用户拖动、缩放或点击 PiP 窗口上的按钮时，所有这些操作都由 SystemUI 首先捕获，然后再通知 WMS/ATMS 去执行具体的位置更新或关闭流程。