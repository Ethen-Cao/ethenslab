+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = 'Insets animation flow'
+++

Insets 动画 API 的核心价值在于**消除系统 UI 动画和应用 UI 动画之间的“割裂感”**，将两者融合成一个平滑、无缝的整体。

以下是一些典型的应用场景，从最常见到更高级的交互：

### 1. 核心场景：键盘的显示与隐藏 (Messaging & Input)

这是最经典、最能体现其价值的场景。

* **传统体验 (问题所在):**
    * 在一个聊天应用里，你点击底部的输入框。
    * 键盘从底部滑出，这个动画是系统负责的。
    * 在键盘动画的同时，应用收到一个“可用空间变小了”的通知。
    * 应用为了防止输入框被键盘遮挡，只能**跳变式地**将整个聊天列表和输入框向上移动。
    * **结果：** 用户会感觉键盘和聊天界面是两个独立的东西在动，体验很生硬。

* **使用 Insets 动画 (解决方案):**
    * 点击输入框。
    * 应用接管键盘的动画控制权。
    * 在键盘从底部向上滑出的每一帧，应用都精确地计算出键盘的当前高度，并**同步地、等速地**将自己的聊天列表和输入框也向上推。
    * **结果：** 在用户看来，整个过程是一个连贯的动画：**仿佛是键盘“推”着聊天内容向上移动**，非常自然、流畅。

| 场景 | 传统方式的问题 | Insets 动画的效果 |
| :--- | :--- | :--- |
| 聊天应用 | 键盘动画与内容移动分离，内容**跳变** | 键盘**平滑推起**内容，动画无缝衔接 |

### 2. 沉浸式模式的过渡 (Video & Photo Apps)

当应用进入或退出全屏（沉浸式）模式时，状态栏和导航栏会显示或隐藏。

* **传统体验 (问题所在):**
    * 你在一个相册应用中全屏查看一张图片。你点击屏幕，希望退出全屏。
    * 系统状态栏和导航栏**突然出现**或**淡入**。
    * 应用内容区域（图片）为了适应变小的空间，**突然缩放或移动**。
    * **结果：** 动画不协调，感觉像是系统 UI 粗暴地“覆盖”在了内容上。

* **使用 Insets 动画 (解决方案):**
    * 点击屏幕。
    * 应用接管状态栏和导航栏的动画。
    * 当状态栏从顶部滑入、导航栏从底部滑入的每一帧，应用都**同步地、平滑地**将图片进行缩放和平移，使其正好填充在两个系统栏之间的新空间里。
    * **结果：** 整个过渡非常优雅，感觉像是**画面和系统栏一起构成了一场精心编排的转场动画**。

### 3. 高级交互场景：手势控制动画

这是 Insets 动画 API 强大灵活性的体现，允许开发者创造更丰富的交互。

* **场景描述：可拖拽的键盘**
    * 想象在一个笔记应用中，键盘已经弹出。你突然想看看被键盘挡住的文字，但又不想完全收起键盘。
    * **实现方式：** 应用可以监听屏幕上的向下拖拽手势。
    * 当用户手指向下滑动时，应用利用 Insets 动画控制器，**实时地将键盘的位置与用户手指的位置绑定**。
    * 用户向下滑动 100 像素，键盘就跟着下降 100 像素，同时笔记内容也跟着向下移动 100 像素。
    * 当用户松手时，应用可以判断是应该让键盘弹回原位，还是完全收起。
    * **结果：** 键盘不再是一个简单的“开/关”状态，而是变成了一个**可以被用户自由拖拽、控制的“物理”对象**，提供了“预览”、“窥探”等高级交互可能性。

### 4. 复杂布局的协调动画

* **场景描述：带输入框的底部工作表 (BottomSheet)**
    * 一个地图应用，你点击某个地点，底部弹出一个包含评论输入框的 BottomSheet。
    * 当你点击评论框时，需要同时弹出键盘。
    * **传统体验 (问题所在):** BottomSheet 弹出的动画和键盘弹出的动画很难协调，经常会发生一个先动、一个后动，或者位置计算错误导致界面抖动的问题。
    * **使用 Insets 动画 (解决方案):** 应用可以完全控制键盘的动画。当 BottomSheet 向上滑动时，应用可以**精确地让键盘以同样的速度或一个协调的曲线**跟随 BottomSheet 一起向上滑动，实现两个组件天衣无缝的组合动画。

### 总结

| 类别 | 场景举例 | 核心价值 |
| :--- | :--- | :--- |
| **基础体验优化** | 聊天/输入框 | 消除键盘与内容移动的**割裂感**，实现平滑过渡 |
| **视觉效果增强** | 视频/图片全屏 | 优雅地处理系统 UI 的显隐，实现**沉浸式**的转场 |
| **高级交互创新** | 手势拖拽键盘 | 将系统 UI 动画变为**可交互**的，响应用户手势 |
| **复杂布局协调** | 底部面板与键盘联动 | 精确同步多个运动组件，避免**动画冲突和抖动** |

总而言之，Insets 动画 API 将原本属于系统“黑盒”的 UI 动画控制权开放给了应用，让开发者能够打造出体验更统一、交互更丰富的界面。

### 时序图

![](/ethenslab/images/Insets_animation_flow.png)

![](/ethenslab/images/inputmethod_inset_animation.png)

### StatusBar的Inset动画调用堆栈

```txt
09-30 18:21:07.769  4336  4655 D SurfaceControl: Surface(name=78b05bb StatusBar)/@0x8e6b5fe - animation-leash of insets_animation setMatrix: dsdx = 1.0, dtdx = 0.0, dtdy = 0.0, dsdy = 1.0
09-30 18:21:07.769  4336  4655 D SurfaceControl: java.lang.Throwable
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.SurfaceControl$Transaction.setMatrix(SurfaceControl.java:3081)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.SurfaceControl$Transaction.setMatrix(SurfaceControl.java:3100)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.SyncRtSurfaceTransactionApplier.applyParams(SyncRtSurfaceTransactionApplier.java:108)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsAnimationThreadControlRunner$1.applySurfaceParams(InsetsAnimationThreadControlRunner.java:90)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsAnimationControlImpl.applyChangeInsets(InsetsAnimationControlImpl.java:298)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsAnimationThreadControlRunner$1.scheduleApplyChangeInsets(InsetsAnimationThreadControlRunner.java:70)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsAnimationControlImpl.setInsetsAndAlpha(InsetsAnimationControlImpl.java:270)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsAnimationControlImpl.finish(InsetsAnimationControlImpl.java:331)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController$InternalAnimationControlListener.onAnimationFinish(InsetsController.java:539)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController$InternalAnimationControlListener$2.onAnimationEnd(InsetsController.java:462)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.Animator$AnimatorListener.onAnimationEnd(Animator.java:711)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.Animator$AnimatorCaller$$ExternalSyntheticLambda1.call(Unknown Source:4)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.Animator.callOnList(Animator.java:669)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.Animator.notifyListeners(Animator.java:608)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.Animator.notifyEndListeners(Animator.java:633)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.ValueAnimator.endAnimation(ValueAnimator.java:1306)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.ValueAnimator.doAnimationFrame(ValueAnimator.java:1566)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.AnimationHandler.doAnimationFrame(AnimationHandler.java:328)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.AnimationHandler.-$$Nest$mdoAnimationFrame(Unknown Source:0)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.animation.AnimationHandler$1.doFrame(AnimationHandler.java:86)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer$CallbackRecord.run(Choreographer.java:1337)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer$CallbackRecord.run(Choreographer.java:1348)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer.doCallbacks(Choreographer.java:952)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer.doFrame(Choreographer.java:878)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer$FrameDisplayEventReceiver.run(Choreographer.java:1322)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Handler.handleCallback(Handler.java:958)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Handler.dispatchMessage(Handler.java:99)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Looper.loopOnce(Looper.java:205)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Looper.loop(Looper.java:294)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.HandlerThread.run(HandlerThread.java:67)
09-30 18:21:07.769  4336  4655 D SurfaceControl: Created from: java.lang.Throwable
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.SurfaceControl.<init>(SurfaceControl.java:1267)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsSourceControl.<init>(InsetsSourceControl.java:71)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController.collectSourceControls(InsetsController.java:1498)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController.controlAnimationUncheckedInner(InsetsController.java:1349)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController.controlAnimationUnchecked(InsetsController.java:1280)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController.applyAnimation(InsetsController.java:1769)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController.applyAnimation(InsetsController.java:1745)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController.show(InsetsController.java:1140)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.InsetsController.show(InsetsController.java:1068)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.ViewRootImpl.controlInsetsForCompatibility(ViewRootImpl.java:2693)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.ViewRootImpl.performTraversals(ViewRootImpl.java:3179)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.ViewRootImpl.doTraversal(ViewRootImpl.java:2465)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.ViewRootImpl$TraversalRunnable.run(ViewRootImpl.java:9305)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer$CallbackRecord.run(Choreographer.java:1339)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer$CallbackRecord.run(Choreographer.java:1348)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer.doCallbacks(Choreographer.java:952)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer.doFrame(Choreographer.java:882)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.view.Choreographer$FrameDisplayEventReceiver.run(Choreographer.java:1322)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Handler.handleCallback(Handler.java:958)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Handler.dispatchMessage(Handler.java:99)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Looper.loopOnce(Looper.java:205)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.os.Looper.loop(Looper.java:294)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at android.app.ActivityThread.main(ActivityThread.java:8177)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at java.lang.reflect.Method.invoke(Native Method)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:552)
09-30 18:21:07.769  4336  4655 D SurfaceControl: 	at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:971)

```

![](/ethenslab/images/statusbar_inset_animation.png)

#### 流程图总览

该流程图详细描绘了一个现代 Android 系统中非常强大且高效的动画机制：**由第三方应用临时接管并驱动系统级 UI（如此处的状态栏）动画的全过程**。

核心思想是，为了实现应用内容与系统 UI (如状态栏、导航栏、键盘) 之间天衣无缝的过渡动画，系统 (WMS) 可以选择将系统 UI 对应图层 (Surface) 的动画控制权，临时**授权**给当前的应用。应用在获得授权后，负责计算动画的每一帧，并通过 `RenderThread` 直接将变换指令提交给系统的最终合成器 `SurfaceFlinger`。

这套机制彻底解决了过去因应用和系统动画不同步而导致的“跳变”或“割裂感”问题，创造出极致平滑的视觉体验。

#### 分步时序详解

整个流程可以分为三个主要阶段：

##### 阶段一：动画授权与准备 (Authorization & Preparation)

这个阶段是整个协作的“握手”和“授权”环节。

1.  **应用发起请求**: 故事始于您的应用 `com.UCMobile` (App) 向 `WindowManagerService` (WMS) 发起一个将导致界面 Insets 变化的请求，最常见的例子就是请求进入全屏模式。
2.  **WMS 决策与授权**: WMS 作为系统窗口的“总管”，接收到请求。它判断需要隐藏状态栏，并且发现 `com.UCMobile` 应用具备处理并监听了此类动画的能力。因此，WMS 决定**不亲自播放**系统默认的隐藏动画，而是将这个任务**委托**出去。
3.  **移交控制权**: WMS 通知 `SystemUI` 进程准备好状态栏，但不要播放动画。同时，WMS 创建一个 `InsetsSourceControl` 对象，它包含了一个关键的凭证——状态栏 Surface 的 Leash (一个可以被跨进程操作的“遥控器”)。WMS 随后通过 Binder 调用 `controlWindowInsetsAnimation`，将这个“遥控器”发送给 `com.UCMobile` 应用。
4.  **应用准备就绪**: 应用的主线程 (`AppMain`) 收到授权后，在其内部创建 `InsetsController` 等管理类，为即将到来的动画做好准备。

##### 阶段二：App 执行动画帧 (App Executes Animation Frames)

这是流程的核心，应用开始真正地“导演”这场动画。

1.  **启动并委托动画**: 应用主线程启动动画逻辑，但为了不阻塞主线程影响流畅性（这是一个关键的性能优化），它将计算和驱动动画的任务交给了另一个专用的**动画线程 (`AppAnim`)**。
2.  **VSYNC 驱动循环**: 动画线程上的 `Choreographer` 与系统的显示刷新信号 (VSYNC) 同步。每当 VSYNC 信号到来时（例如每秒 60 或 120 次），`Choreographer` 就会触发一次 `doFrame` 回调，驱动动画向前“走”一帧。
3.  **计算并调度**: 在 `doFrame` 回调中，`ValueAnimator` 等动画类会计算出当前帧状态栏应该处于的位置、透明度等属性。然后，动画线程并**不直接操作视图**，而是调用 `applyParams` 方法，将这些计算出的变换参数（如 Matrix 矩阵）**调度**给更为底层的**渲染线程 (`AppRT`)**。
4.  **提交渲染指令**: 应用的 `RenderThread` 是一个专门与 GPU 和 `SurfaceFlinger` 打交道的线程。它接收到参数后，会创建一个 `SurfaceControl.Transaction` 对象（一个原子性的变更指令集），并将变换矩阵设置到它所持有的状态栏 Leash 上。最后，它调用 `transaction.apply()` 将这个指令集直接发送给 `SurfaceFlinger`。这个提交动作非常轻量，只是“发出命令”而已。

##### 阶段三：动画结束 (Animation Ends)

1.  **动画结束回调**: 由于动画是由应用内部的 `ValueAnimator` 驱动的，当它播放完毕时，会触发 `onAnimationEnd` 回调。
2.  **通知 WMS**: 应用的动画线程通知主线程动画已结束。主线程随即调用 `onAnimationFinish()` 通知 WMS，表示“我已经完成了动画，现在可以将控制权交还了”。这标志着授权的结束。
3.  **SurfaceFlinger 最终合成**: 在整个动画过程中，`SurfaceFlinger` 不断地接收来自 `com.UCMobile` 的 `Transaction`。在每个 VSYNC 时刻，`SurfaceFlinger` 会将收集到的所有 `Transaction`（无论来自哪个进程）一次性地、原子性地应用，然后将屏幕上所有图层（应用窗口、状态栏 Leash、导航栏等）合成为最终的一帧画面并显示在屏幕上。这保证了所有元素的运动都是完美同步的。

#### 总结

这份流程图揭示了 Android UI 系统的一个精妙设计：通过**授权**和**责任分离**，实现了极致的性能和流畅度。应用负责**计算**动画逻辑，`RenderThread` 负责**提交**指令，`SurfaceFlinger` 负责最终**合成**。整个过程高效、解耦，是打造现代、流畅 Android 应用体验的关键所在。