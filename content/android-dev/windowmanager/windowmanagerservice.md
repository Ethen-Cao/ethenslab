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

#### DisplayArea的创建

DisplayAreaPolicy 在 Android 窗口管理系统中的作用，是作为一个 **“显示区域布局策略”的总设计师**。

简单来说，它就是一份 **“建筑蓝图”，负责定义一个显示设备（如手机屏幕）内部，所有 DisplayArea 应该如何被组织、嵌套和排序**。WindowManagerService (WMS) 会严格依照这份蓝图来构建窗口的容器层级。

#### DisplayAreaPolicy 的主要职责
1. 定义 Feature (功能区)
    DisplayAreaPolicy 的首要职责是定义系统需要支持哪些全局性的 Feature (功能特性)，以及这些 Feature 之间的层级关系。这包括：

    * 画中画 (FEATURE_PICTURE_IN_PICTURE)
    * 单手模式 (FEATURE_ONE_HANDED)
    * 隐藏刘海 (FEATURE_HIDE_DISPLAY_CUTOUT)
    * 放大功能 (...MAGNIFICATION)
    * 输入法占位符 (FEATURE_IME_PLACEHOLDER)

    它会决定当这些功能启用时，对应的 DisplayArea 应该被创建在层级树的哪个位置，以及它们应该包裹哪些其他的 DisplayArea。

2. 映射窗口类型到层级 (Mapping Window Types to Layers)
    这是它的另一个核心职责。DisplayAreaPolicy 内部包含了将各种 WindowManager.LayoutParams.type（如 TYPE_APPLICATION, TYPE_STATUS_BAR）映射到一个具体整数层级值 (Window Layer) 的核心逻辑。getWindowLayerLw(WindowState win) 这个关键方法就由它实现，确保状态栏的 Layer 值永远高于应用程序，而壁纸的 Layer 值永远低于应用程序。它还定义了层级的上限 getMaxWindowLayer()，划定了整个 Z-order 的范围。

3. 提供 DisplayArea 层级结构的构建器
    DisplayAreaPolicy 会初始化并配置一个 DisplayAreaPolicyBuilder。这个 Builder 内部存储了所有根据上述策略分析出的布局规则。
    当 WMS 需要为一个新的显示设备（DisplayContent）构建窗口容器树时，它会向 DisplayAreaPolicy 索要这个预先配置好的 Builder，然后调用 Builder.build() 方法，一次性地、自动地生成复杂而精确的 DisplayArea 嵌套结构。

4. 提供设备定制化的入口 (Entry-point for Customization)
    Android 是一个高度可定制化的系统。不同的硬件设备（如手机、平板、折叠屏、电视）对窗口的组织方式有不同的需求。

DisplayAreaPolicy 通过 DisplayAreaPolicy.Provider 这个机制，允许设备制造商 (OEM/Vendor) 替换掉 AOSP 默认的策略实现（PhoneDisplayAreaPolicy）。
制造商可以提供自己的 DisplayAreaPolicy 实现，来创建特殊的 DisplayArea（例如，为折叠屏的副屏幕或手写笔窗口创建专属区域），或者调整不同窗口类型的层级关系，以适配其独特的硬件功能。

在WMS构造方法中会创建 DisplayAreaPolicy.Provider:

```java
mDisplayAreaPolicyProvider = DisplayAreaPolicy.Provider.fromResources(
        mContext.getResources());
```
Provider的实现如下：
```java

static Provider fromResources(Resources res) {
    String name = res.getString(
            com.android.internal.R.string.config_deviceSpecificDisplayAreaPolicyProvider);
    if (TextUtils.isEmpty(name)) {
        return new DisplayAreaPolicy.DefaultProvider();
    }
    try {
        return (Provider) Class.forName(name).newInstance();
    } catch (ReflectiveOperationException | ClassCastException e) {
        ……
    }
}
    
```

如果资源配置项 **config_deviceSpecificDisplayAreaPolicyProvider** 为空，就构造默认的Provider: DisplayAreaPolicy.DefaultProvider()。这里给OEM/Vendor留下了定制化的空间，他们可以自定义Provider，构造特有的DisplayAreaPolicy，再由DisplayAreaPolicy构造特定规则的DisplayArea。

DisplayAreaPolicy.Provider 的实现如下，它会构建HierarchyBuilder，初始化 Features：

```java
static final class DefaultProvider implements DisplayAreaPolicy.Provider {
            private void configureTrustedHierarchyBuilder(HierarchyBuilder rootHierarchy,
                WindowManagerService wmService, DisplayContent content) {
            // WindowedMagnification should be on the top so that there is only one surface
            // to be magnified.
            rootHierarchy.addFeature(new Feature.Builder(wmService.mPolicy, "WindowedMagnification",
                    FEATURE_WINDOWED_MAGNIFICATION)
                    .upTo(TYPE_ACCESSIBILITY_MAGNIFICATION_OVERLAY)
                    .except(TYPE_ACCESSIBILITY_MAGNIFICATION_OVERLAY)
                    // Make the DA dimmable so that the magnify window also mirrors the dim layer.
                    .setNewDisplayAreaSupplier(DisplayArea.Dimmable::new)
                    .build());
            if (content.isDefaultDisplay) {
                // Only default display can have cutout.
                // See LocalDisplayAdapter.LocalDisplayDevice#getDisplayDeviceInfoLocked.
                rootHierarchy.addFeature(new Feature.Builder(wmService.mPolicy, "HideDisplayCutout",
                        FEATURE_HIDE_DISPLAY_CUTOUT)
                        .all()
                        .except(TYPE_NAVIGATION_BAR, TYPE_NAVIGATION_BAR_PANEL, TYPE_STATUS_BAR,
                                TYPE_NOTIFICATION_SHADE)
                        .build())
                        .addFeature(new Feature.Builder(wmService.mPolicy, "OneHanded",
                                FEATURE_ONE_HANDED)
                                .all()
                                .except(TYPE_NAVIGATION_BAR, TYPE_NAVIGATION_BAR_PANEL,
                                        TYPE_SECURE_SYSTEM_OVERLAY)
                                .build());
            }
            rootHierarchy
                    .addFeature(new Feature.Builder(wmService.mPolicy, "FullscreenMagnification",
                            FEATURE_FULLSCREEN_MAGNIFICATION)
                            .all()
                            .except(TYPE_ACCESSIBILITY_MAGNIFICATION_OVERLAY, TYPE_INPUT_METHOD,
                                    TYPE_INPUT_METHOD_DIALOG, TYPE_MAGNIFICATION_OVERLAY,
                                    TYPE_NAVIGATION_BAR, TYPE_NAVIGATION_BAR_PANEL)
                            .build())
                    .addFeature(new Feature.Builder(wmService.mPolicy, "ImePlaceholder",
                            FEATURE_IME_PLACEHOLDER)
                            .and(TYPE_INPUT_METHOD, TYPE_INPUT_METHOD_DIALOG)
                            .build());
        }
}
```

![Window Type到Feature的映射关系表](/ethenslab/images/windowtype-2-feature.png)

#### HierarchyBuilder.build 方法构建逻辑详解
1. 宏观目标与设计哲学
build 方法是 Android 窗口管理系统中的“创世”引擎。其宏观目标是将一个高层、抽象的策略（由 Feature 特性表定义）转化为一个具体的、物理的、严格有序的 WindowContainer 层级树。
这个过程必须遵循并实现以下设计原则（源自代码注释）：
* 特性归属 (Feature Containment)：任何一个窗口，都必须被正确地放置在负责管辖它的那个 Feature 对应的 DisplayArea 容器之内。
* Z-order 完整性 (Z-Order Integrity)：任意两个并列（兄弟关系）的 DisplayArea，它们所管辖的窗口层级区间不能有任何重叠。位于下方的 DisplayArea 的最高层级，必须小于或等于位于上方的 DisplayArea 的最低层级。

为了实现这个复杂目标，算法采用了一种 **“蓝图-施工”** 的模式：先构建一个轻量级的、完整的 PendingArea 树（蓝图），然后再根据这个蓝图一次性地创建出所有真实的 DisplayArea 对象（施工）。

2. 核心数据结构与“建筑材料”
在施工开始前，我们先了解一下几样关键的“建筑材料”：

* Feature (特性)：高级别的“功能区规划”，例如“画中画区”、“单手模式影响区”等。它定义了自己对哪些窗口层级 (Layer) 生效。
* Layer (层级)：Z-order 的基本单位，从 0 到 36 的整数。可以理解为建筑的“楼层”。
* PendingArea (蓝图节点)：构建过程中的核心数据结构，一个临时的、代表最终 DisplayArea 的规划草稿。它包含了父子关系、所属特性、以及管辖的 Layer 区间等所有必要信息。
* areaForLayer[] (施工辅助线/脚手架)：一个大小为 37 的 PendingArea 数组。它是一个动态指针数组，在构建过程的任意时刻，areaForLayer[i] 都指向第 i 层“当前最内层的父容器”，用来指导新节点应该挂载到哪里。

3. 算法执行流程详解
build 方法的执行可以清晰地分为三个阶段：

阶段一：构建特性框架 (Building the Feature Framework)

* 这是第一个核心 for 循环，它的目标是根据 Feature 的定义，搭建出整个 DisplayArea 树的宏观结构和嵌套关系。
* 按序遍历特性: 算法按照 mFeatures 列表的预定顺序，逐一处理每一个 Feature。这个顺序至关重要，先被处理的 Feature 会成为更外层的容器。
* 遍历所有楼层: 对于每一个 Feature，算法会从第 0 层到第 36 层进行扫描，检查该 Feature 是否适用于当前楼层（查阅策略表中的 Y/N）。
* 创建/复用决策:
    * 当算法在某一层 L 发现需要应用 Feature F 时，它会检查是否可以复用上一个楼层为 F 创建的 PendingArea。
    * 如果不行（例如，这是 F 遇到的第一个楼层，或者 L 层的父容器规划与 L-1 层不同，意味着连续性被“打断”），算法就必须创建一个新的 PendingArea，并将其作为 areaForLayer[L] 所指向的那个“当前父容器”的子节点。
    * 更新“脚手架”: 在创建或复用 PendingArea 之后，算法会立刻更新 areaForLayer[L]，使其指向刚刚处理过的、更深一层的这个 PendingArea。这保证了下一个 Feature 在处理 L 层时，会被正确地嵌套在 F 的内部。

这个阶段结束后，一个由 PendingArea 组成的、反映了所有 Feature 之间复杂嵌套和并列关系的“建筑框架”就搭建完成了。
参考如下：
```text
RootDisplayArea (根)
 ├─ PendingArea (Layers 36) [Leaf/Tokens]
 ├─ PendingArea (Feature: HideDisplayCutout) [Layers 32-35]
 │   └─ PendingArea (Feature: OneHanded) [Layers 34-35]
 │       └─ PendingArea (Feature: FullscreenMagnification) [Layers 34-35]
 │           └─ PendingArea (Layers 34-35) [Leaf/Tokens]
 │   └─ PendingArea (Feature: FullscreenMagnification) [Layer 33]
 │       └─ PendingArea (Layers 33) [Leaf/Tokens]
 │   └─ PendingArea (Feature: OneHanded) [Layer 32]
 │       └─ PendingArea (Layers 32) [Leaf/Tokens]
 └─ PendingArea (Feature: WindowedMagnification) [Layers 0-31]
     ├─ PendingArea (Feature: HideDisplayCutout) [Layers 26-31]
     │   └─ PendingArea (Feature: OneHanded) [Layers 26-31]
     │       └─ PendingArea (Feature: FullscreenMagnification) [Layers 29-31]
     │       │   └─ PendingArea (Layers 29-31) [Leaf/Tokens]
     │       ├─ PendingArea (Layers 28) [Leaf/Tokens for MagnificationOverlay]
     │       └─ PendingArea (Feature: FullscreenMagnification) [Layers 26-27]
     │           └─ PendingArea (Layers 26-27) [Leaf/Tokens]
     ├─ PendingArea (Layers 24-25) [Leaf/Tokens for NavigationBar]
     ├─ PendingArea (Feature: HideDisplayCutout) [Layers 18-23]
     │   └─ PendingArea (Feature: OneHanded) [Layers 18-23]
     │       └─ PendingArea (Feature: FullscreenMagnification) [Layers 18-23]
     │           └─ PendingArea (Layers 18-23) [Leaf/Tokens]
     ├─ PendingArea (Feature: OneHanded) [Layer 17]
     │   └─ PendingArea (Feature: FullscreenMagnification) [Layer 17]
     │       └─ PendingArea (Layers 17) [Leaf/Tokens for NotificationShade]
     ├─ PendingArea (Feature: HideDisplayCutout) [Layer 16]
     │   └─ PendingArea (Feature: OneHanded) [Layer 16]
     │       └─ PendingArea (Feature: FullscreenMagnification) [Layer 16]
     │           └─ PendingArea (Layers 16) [Leaf/Tokens]
     ├─ PendingArea (Feature: OneHanded) [Layer 15]
     │   └─ PendingArea (Feature: FullscreenMagnification) [Layer 15]
     │       └─ PendingArea (Layers 15) [Leaf/Tokens for StatusBar]
     └─ PendingArea (Feature: HideDisplayCutout) [Layers 0-14]
         └─ PendingArea (Feature: OneHanded) [Layers 0-14]
             ├─ PendingArea (Feature: FullscreenMagnification) [Layers 0-12]
             │   ├─ PendingArea (Layers 3-12) [Leaf/Tokens]
             │   ├─ PendingArea (Layers 2) [Leaf: TaskDisplayArea]
             │   └─ PendingArea (Layers 0-1) [Leaf/Tokens for Wallpaper]
             └─ PendingArea (Feature: ImePlaceholder) [Layers 13-14]
                 └─ PendingArea (Layers 13-14) [Leaf: ImeContainer]
```

阶段二：填充叶子容器 (Populating the Leaf Containers)
这是第二个核心 for 循环。如果说第一阶段是搭建“功能区”，那这个阶段就是为每个功能区的每一层楼划分出最终的“房间”，这些“房间”将直接用来容纳 WindowState。

1. 遍历所有楼层: 算法再次从第 0 层到第 36 层进行扫描。
2. 确定房间类型: 在每一层，算法会通过 typeOfLayer() 查询策略，确定这一层需要什么类型的“房间”——是普通的 DisplayArea.Tokens，还是特殊的 TaskDisplayArea 或 ImeContainer。
3. 创建/复用决策:
* 与阶段一类似，算法会检查是否可以和上一层共用一个“叶子房间”(leafArea)。
* 如果不行（例如，父容器的特性框架变了，或者房间类型变了），就必须创建一个新的 PendingArea 作为叶子容器，并将其挂载到 areaForLayer[layer] 所指向的那个“最内层框架”之下。
4. 处理特殊房间:
* 当遇到应用层 (LEAF_TYPE_TASK_CONTAINERS) 或输入法层 (LEAF_TYPE_IME_CONTAINERS) 时，算法不会创建新的 Tokens 房间，而是会将预先准备好的 TaskDisplayArea 或 ImeContainer 挂载到蓝图的正确位置。
5. 确定管辖范围: 在复用 leafArea 的过程中，算法会不断更新 leafArea.mMaxLayer，以此来记录这个“房间”所跨越的连续楼层的范围。

这个阶段结束后，整个建筑蓝图就画完了。每一个楼层都被精确地规划到了一个最终的叶子容器中。

阶段三：实例化与收尾 (Instantiation and Finalization)
蓝图已经完美，现在开始“施工”。

1. root.instantiateChildren(...): 这是收尾的关键。此方法会递归遍历整个 PendingArea 蓝图树（从 root 节点开始）。
2. 创建真实对象: 在遍历过程中，它会 new DisplayArea(...) 和 new DisplayArea.Tokens(...)，创建出所有真实的 DisplayArea 对象。
3. 建立父子关系: 根据蓝图中的父子链接，调用 parent.addChild(child)，将这些真实的 DisplayArea 对象组装成一棵与蓝图完全一致的、可供 WMS 使用的 WindowContainer 树。
4. mRoot.onHierarchyBuilt(...): 通知 RootDisplayArea，层级树已经构建完毕，可以缓存相关信息并投入使用了。

总结
build 方法是一个高度确定性和逻辑严谨的算法。它通过两个核心阶段——先构建宏观的特性框架，再填充微观的叶子容器——将一份高层的、二维的策略表，精确地转换成了一棵复杂的、多维的、严格遵守 Z-order 的窗口容器树。这种“先规划蓝图，再统一施工”的设计，优雅地解决了 Android 窗口系统中极为复杂的层级布局问题。


我们也可以通过 adb shell dumpsys window containers查看实际的DisplayContent层次结构：

```text
ROOT type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
  #0 Display 0 name="Built-in Screen" type=undefined mode=fullscreen override-mode=fullscreen requested-bounds=[0,0][1080,2340] bounds=[0,0][1080,2340]
   #2 Leaf:36:36 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #1 WindowToken{988c232 type=2024 android.os.BinderProxy@ccb9f01} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 5bc2d39 ScreenDecorOverlayBottom type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #0 WindowToken{263aed type=2024 android.os.BinderProxy@ee97504} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 a2005b8 ScreenDecorOverlay type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
   #1 HideDisplayCutout:32:35 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #2 OneHanded:34:35 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 FullscreenMagnification:34:35 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 Leaf:34:35 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #1 FullscreenMagnification:33:33 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 Leaf:33:33 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #0 OneHanded:32:32 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 Leaf:32:32 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
   #0 WindowedMagnification:0:31 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #6 HideDisplayCutout:26:31 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 OneHanded:26:31 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #2 FullscreenMagnification:29:31 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 Leaf:29:31 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #1 Leaf:28:28 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 FullscreenMagnification:26:27 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 Leaf:26:27 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #5 Leaf:24:25 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 WindowToken{237c785 type=2019 android.os.BinderProxy@cb621ef} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 668a9da NavigationBar0 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #4 HideDisplayCutout:18:23 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 OneHanded:18:23 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 FullscreenMagnification:18:23 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 Leaf:18:23 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #3 OneHanded:17:17 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 FullscreenMagnification:17:17 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 Leaf:17:17 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 WindowToken{8431992 type=2040 android.os.BinderProxy@c8c3ff4} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #0 f488f63 NotificationShade type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #2 HideDisplayCutout:16:16 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 OneHanded:16:16 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 FullscreenMagnification:16:16 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 Leaf:16:16 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #1 OneHanded:15:15 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 FullscreenMagnification:15:15 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 Leaf:15:15 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 WindowToken{faabebf type=2000 android.os.BinderProxy@1867419} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #0 88b998c StatusBar type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
    #0 HideDisplayCutout:0:14 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
     #0 OneHanded:0:14 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #1 ImePlaceholder:13:14 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 ImeContainer type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #0 WindowToken{d89974 type=2011 android.os.Binder@39dad47} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
         #0 7eb5b27 InputMethod type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
      #0 FullscreenMagnification:0:12 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #2 Leaf:3:12 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #2 WindowToken{7f09984 type=2038 android.os.BinderProxy@c073d88} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
         #0 42d8e16 com.android.fakeoemfeatures:background type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #1 WindowToken{90c3cba type=2038 android.os.BinderProxy@5c38480} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
         #0 bbea429 com.android.fakeoemfeatures type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #0 WindowToken{107a05c type=2038 android.os.BinderProxy@578b017} type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
         #0 39e71a9 ShellDropTarget type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #1 DefaultTaskDisplayArea type=undefined mode=fullscreen override-mode=fullscreen requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #1 Task=1 type=home mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
         #0 Task=15 type=home mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
          #0 ActivityRecord{a2ee9c4 u0 com.android.launcher3/.uioverrides.QuickstepLauncher t15} type=home mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
           #0 a09fbef com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher type=home mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #0 Task=2 type=undefined mode=fullscreen override-mode=fullscreen requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
         #1 Task=4 type=undefined mode=multi-window override-mode=multi-window requested-bounds=[0,2340][1080,3510] bounds=[0,2340][1080,3510]
         #0 Task=3 type=undefined mode=multi-window override-mode=multi-window requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
       #0 Leaf:0:1 type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
        #0 WallpaperWindowToken{8c049ee token=android.os.Binder@5304b69} type=undefined mode=fullscreen override-mode=fullscreen requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
         #0 992d414 com.android.systemui.wallpapers.ImageWallpaper type=undefined mode=fullscreen override-mode=undefined requested-bounds=[0,0][0,0] bounds=[0,0][1080,2340]
 
Window{5bc2d39 u0 ScreenDecorOverlayBottom}
Window{a2005b8 u0 ScreenDecorOverlay}
Window{668a9da u0 NavigationBar0}
Window{f488f63 u0 NotificationShade}
Window{88b998c u0 StatusBar}
Window{7eb5b27 u0 InputMethod}
Window{42d8e16 u0 com.android.fakeoemfeatures:background}
Window{bbea429 u0 com.android.fakeoemfeatures}
Window{39e71a9 u0 ShellDropTarget}
Window{a09fbef u0 com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher}
Window{992d414 u0 com.android.systemui.wallpapers.ImageWallpaper}
```

WindowContainer类图结构参考如下：

![WindowContainer结构图](/ethenslab/images/Window-hierarchy.png)

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


### 分屏模式

![Android 14+ 分屏启动时序图](/ethenslab/images/seq-split-screen-start.png)

流程解说
1. 用户发起操作: 用户在最近任务界面（由 SystemUI 实现）发起分屏请求。

2. 请求进入分屏: SystemUI 通知 ActivityTaskManagerService (ATMS) 准备进入分屏模式，并告知第一个应用是谁。

3. 创建父任务: ATMS 作为响应，创建一个新的、特殊的 Task。这个 Task 在逻辑上代表了这个“分屏应用对”。

4. 创建 TaskFragment: 在这个父 Task 内部，ATMS 预先创建好两个“窗格”——TaskFragment A 和 TaskFragment B。

5. 安置第一个应用: ATMS 命令 WindowManagerService (WMS) 执行窗口容器的“移花接木”操作，将应用 A 的 ActivityRecord 放入 TaskFragment A 中。

6. 显示选择器: 此时，上半屏已经显示应用 A，下半屏由 SystemUI 继续显示其他应用的列表，供用户选择。

7. 用户选择第二个应用: 用户从列表中点选应用 B。

8. 安置第二个应用: SystemUI 将用户的选择通知 ATMS。

9. ATMS 再次命令 WMS，将应用 B 的 ActivityRecord 放入 TaskFragment B 中。

10. 完成布局: 所有应用都就位后，ATMS 提交最终的窗口布局，隐藏选择器界面，让包含两个 TaskFragment 的父 Task 完整地显示在屏幕上。