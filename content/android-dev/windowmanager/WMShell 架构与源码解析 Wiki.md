# WMShell 架构与源码解析 Wiki

本文档库旨在深入剖析 Android WMShell 的系统架构、核心机制与关键业务源码。内容编排由浅入深，涵盖基础架构、跨进程渲染同步机制以及车载环境下的定制化扩展。

---

## 目录结构

### [1. WMShell 宏观定位与设计初衷](01-wmshell-architecture-and-positioning.md)
* **Android 窗口架构演进**
  * 为什么需要引入 WMShell 架构
* **进程边界划分**
  * `system_server` (WM Core)：维护全局容器树、Z 轴层级、状态机与安全策略
  * `SystemUI` (WMShell)：承接用户交互、视觉呈现与复杂动画逻辑
* **WMShell 在车载 OS 中的位置**
  * 标准 Phone UI 与 CarSystemUI 在 WMShell 接入与初始化上的差异

### [2. WMShell 典型业务场景](02-wmshell-typical-scenarios.md)
* **分屏模式 (Split Screen)**
* **画中画 (Picture-in-Picture / PiP)**
* **自由窗口与桌面模式 (Freeform / Desktop Mode)**
* **气泡与多任务概览 (Bubbles & Recents)**
* **系统级窗口动画 (Back Animation, Starting Window)**

### [3. WMShell 核心技术原理](03-wmshell-core-mechanisms.md)
* **任务管理基础设施**
  * `TaskOrganizer`：Task 状态变更的事件总线与系统接管机制
  * `WindowOrganizer` 与 `WindowContainerTransaction` (WCT)：跨进程窗口事务的构建与提交
* **跨进程动画与渲染同步底座（核心难点）**
  * `Transitions` 框架：动画播放权的移交链路与责任链分发
  * **BLAST Sync 机制**：SurfaceFlinger 如何保障 WMShell 动画与 App 绘制帧的级联同步（必读）
* **输入与事件处理**
  * 基于 `InputMonitor` 的全局手势拦截
  * 焦点转移与 IME (输入法) 的跨容器层级协同

### [4. WMShell 内部架构与生命周期](04-wmshell-initialization-process.md)
* **初始化链路**
  * Dagger 与 `WMComponent` 子图：内部依赖注入、作用域隔离与实例管理
  * `ShellInit`：各业务控制器的按序启动与回调注册
* **内外通信模型**
  * 对内协作：`ShellController` 处理系统配置、Keyguard 状态、用户切换事件
  * 对外暴露：通过 Binder 接口（如 `ISplitScreen`）向 Launcher 等外部进程导出控制能力

### [5. 深度案例剖析：以 SplitScreen 为例](05-wmshell-splitscreen-case-study.md)
* **核心类图与职责域**
  * 门面模式 `SplitScreenController` 与总协调者 `StageCoordinator`
* **容器构建**
  * Root Task 与 Stage Task (Main/Side) 的创建及挂载时序
* **状态机运转（三阶段解析）**
  * 进入分屏：WCT 构造、`EnterTransition` 拦截与动画播放
  * 动态交互：拖动 Divider 时的纯 `SurfaceControl` 形变处理（不经 WM Core）
  * 定稿与退出：Snap 吸附算法计算与 Dismiss 逻辑的事务提交

### [6. 系统调试与座舱客制化实践](06-wmshell-debug-and-customization.md)
* **排查工具集**
  * `dumpsys activity service SystemUIService WMShell` 状态树分析
  * `protolog` 在 WMShell 中的使用规范与动态开关
  * 使用 `Winscope` 抓取并分析 WMShell 动画异常（Transaction Trace）
* **座舱扩展场景探讨（架构级）**
  * 多屏互动：WMShell 如何应对副驾/后排的 `DisplayArea` 跨屏 Task 拖拽与接力
  * 多用户并发：MUMD (Multi-User Multi-Display) 架构下，WMShell 的实例隔离与事件路由策略

---
