
### TransitionHandler

`TransitionHandler` 是一个**接口 (Interface)**，它为 Shell 动画系统定义了一个**“动画处理器”**的标准或**契约**。

可以把它想象成一个**专家岗位说明书** 📜。任何一个类，只要实现了 `TransitionHandler` 接口，就意味着它具备了处理一类特定窗口过渡动画的专业能力，并可以被 `Transitions` （动画总调度室）统一管理和调度。

#### 核心职责

一个 `TransitionHandler` 实现类，其核心职责主要有两个：

##### 1. 认领任务 (Claim the Job) - 通过 `handleRequest` 方法

这是 `TransitionHandler` **最关键**的职责。当 `Transitions.requestStartTransition` 方法收到一个来自系统的动画请求时，它会遍历其内部的 `Handler` 列表，并调用每个 `Handler` 的 `handleRequest` 方法。

* **“这是我的活儿吗？”**: 在 `handleRequest` 方法内部，`Handler` 会检查传入的 `TransitionRequestInfo`（动画请求信息），根据动画的类型 (`type`)、触发任务 (`triggerTask`)、窗口模式等信息，来判断这是否是自己应该处理的动画场景。
    * 例如，`RecentsTransitionHandler` 会检查动画类型是否与“最近任务”相关。
    * `UnfoldTransitionHandler` 会检查设备是否正在折叠/展开。

* **如何认领**:
    * 如果 `Handler` 决定处理这个请求，它会返回一个 `WindowContainerTransaction` 对象（即使这个对象是空的）。这就像举手说：“这个我来处理！”
    * 如果 `Handler` 认为这个请求不归自己管，它会返回 `null`。`Transitions` 看到 `null` 后，就会继续去问下一个 `Handler`。

##### 2. 执行动画 (Execute the Animation)

一旦一个 `Handler` 通过返回非 `null` 的 `WCT` 成功“认领”了一个 `Transition`，它就**全权负责**这个 `Transition` 的动画实现。

* **准备与执行**: 当 `TransitionController` 完成所有准备工作，并通过 `onTransitionReady` 将包含完整信息的 `TransitionInfo` 发送回 Shell 后，`Transitions` 总调度室会确保将这个 `TransitionInfo` 交给当初认领了它的那个 `Handler`。
* **具体的动画逻辑**: `Handler` 内部会包含具体的动画代码。它会解析 `TransitionInfo`，获取需要操作的窗口图层（Leashes），然后使用 `SurfaceControl.Transaction` 来实现平移、缩放、透明度变化等一系列视觉效果，最终构成一个完整的动画。

#### 设计模式与优势

这个设计采用了经典的**责任链模式 (Chain of Responsibility)** 或**策略模式 (Strategy Pattern)**。

* **模块化 (Modularity)**: 将不同场景的动画逻辑**隔离**在各自独立的 `Handler` 类中。`RecentsTransitionHandler` 只关心“最近任务”，`PipTransitionController` 只关心画中画，它们互不干扰。
* **可扩展性 (Extensibility)**: 这个架构非常容易扩展。如果未来 Android 增加了一种新的窗口模式（比如“迷你模式”），开发者只需要：
    1.  创建一个新的 `MiniModeTransitionHandler` 类，并实现 `TransitionHandler` 接口。
    2.  在新类中编写进入/退出“迷你模式”的动画逻辑。
    3.  将这个新的 `Handler` 注册到 `Transitions` 的 `Handler` 列表中。
    整个动画系统就能自动支持这种新的动画，而无需修改任何现有的核心代码。
* **优先级 (Prioritization)**: `Transitions` 内部的 `Handler` 列表是有顺序的。这允许系统定义处理的**优先级**。比如，`UnfoldTransitionHandler`（折叠屏专家）的优先级会高于 `DefaultTransitionHandler`（通用专家），确保在折叠屏设备上，优先执行专门为折叠屏优化的动画。

#### 总结

`TransitionHandler` 接口是 Shell 动画系统的**基石**。它定义了一个标准，让各种**动画专家**能够“即插即用”地加入到动画系统中，使得整个系统**职责清晰、高度模块化且易于扩展**。

#### TransitionHandler的实现者

```txt
frameworks/base/libs/WindowManager$ jgrep -nrE "implements.*TransitionHandler"
./Shell/src/com/android/wm/shell/transition/OneShotRemoteHandler.java:40:public class OneShotRemoteHandler implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/transition/DefaultMixedHandler.java:65:public class DefaultMixedHandler implements Transitions.TransitionHandler,
./Shell/src/com/android/wm/shell/transition/SleepHandler.java:36:class SleepHandler implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/transition/RemoteTransitionHandler.java:50:public class RemoteTransitionHandler implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/transition/DefaultTransitionHandler.java:120:public class DefaultTransitionHandler implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/unfold/UnfoldTransitionHandler.java:54:public class UnfoldTransitionHandler implements TransitionHandler, UnfoldListener {
./Shell/src/com/android/wm/shell/freeform/FreeformTaskTransitionHandler.java:46:        implements Transitions.TransitionHandler, FreeformTaskTransitionStarter {
./Shell/src/com/android/wm/shell/desktopmode/ExitDesktopTaskTransitionHandler.java:53:public class ExitDesktopTaskTransitionHandler implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/desktopmode/EnterDesktopTaskTransitionHandler.java:49:public class EnterDesktopTaskTransitionHandler implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/taskview/TaskViewTransitions.java:49:public class TaskViewTransitions implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/activityembedding/ActivityEmbeddingController.java:49:public class ActivityEmbeddingController implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/pip/PipTransitionController.java:52:public abstract class PipTransitionController implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/keyguard/KeyguardTransitionHandler.java:58:public class KeyguardTransitionHandler implements Transitions.TransitionHandler {
./Shell/src/com/android/wm/shell/recents/RecentsTransitionHandler.java:67:public class RecentsTransitionHandler implements Transitions.TransitionHandler {
```