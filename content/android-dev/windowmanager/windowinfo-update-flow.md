+++
date = '2026-06-07T10:22:54+08:00'
draft = false
title = 'Android 13 WindowInfos Update Flow — 架构、Bug 分析与 Backpressure 修复'
+++

## 1. 概述

WindowInfos Update Flow 是 Android 图形与输入系统协同工作的核心机制。SurfaceFlinger (SF) 每帧合成后将最新窗口属性（`WindowInfo`：几何位置、Z-Order、触摸区域、输入标志、变换矩阵）通过 oneway Binder 实时同步给消费者进程。

**主要消费者**：

- **InputDispatcher** (system_server 进程)：根据窗口信息计算触摸事件的目标窗口（Hit Testing）。
- **PointerController** (system_server 进程)：处理鼠标/触控笔指针的显示与坐标映射。
- **AccessibilityWindowsPopulator** (system_server 进程)：为无障碍服务（A11y）构建屏幕窗口节点树。

该机制的高频跨进程特性（每 16ms 一次）使其成为 Binder 缓冲区耗尽的高发区。本文档描述了 8295/AOSP13 中该流程的原始实现、一个导致 system_server 冻屏的 bug 的完整根因分析，以及基于 backpressure 的修复方案。

## 2. 核心架构

### 2.1 注册链：三个调用者，一条 Binder 通道

所有消费者都调用 `SurfaceComposerClient::addWindowInfosListener()`，该函数路由到本进程的 `WindowInfosListenerReporter` 单例。Reporter 只在第一个本地 listener 注册时向 SF 建立 Binder 通道。Android 10 起 Input 栈（`libinputservice`、`libinputdispatcher`）编译进 system_server，因此所有三个消费者均在 system_server 进程内，共享同一个 Reporter 单例。

```
                     SurfaceFlinger
                          │
                          │ oneway binder (唯一)
                          ▼
              system_server 的
              WindowInfosListenerReporter (单例)
              ┌──────────────────────────────┐
              │ InputDispatcher (local cb)   │
              │ PointerController (local cb) │
              │ A11yPop JNI (local cb)       │
              └──────────────────────────────┘
```

从 SF 的 `WindowInfosListenerInvoker::mWindowInfosListeners` 视角，只看到 **1 个** binder 级 listener：system_server 的 Reporter。本机日志验证：全部 28996 条 `"Recorded window infos message ... for 1 listener(s)"`。

### 2.2 各消费者注册原因与流程

#### 为什么需要 WindowInfo？

三个消费者对窗口信息的需求各不相同，但都**只能从 SurfaceFlinger 获取**——SF 是唯一拥有合成后窗口实际几何状态（变换矩阵、裁剪区域、Z-Order）的组件：

- **InputDispatcher**：需要窗口的 Z-Order 和触摸区域来做点击测试（Hit Testing），确定触摸事件分发给哪个窗口。
- **PointerController**：需要 display 的变换矩阵来正确映射鼠标/触控笔坐标。
- **AccessibilityWindowsPopulator**：需要**屏幕上每个窗口的完整信息**（位置、大小、层级、触摸区域、是否可见、是否被遮挡），为无障碍服务（如 TalkBack）构建窗口节点树。视障用户依赖这些信息来理解屏幕内容和进行代理操作。

#### 无障碍注册触发时机

无障碍的 `WindowInfosListener` 注册并非开机即完成，而是**按需注册**。调用链如下：

```
AccessibilityManagerService
  → accessibilityWindowManager.startTrackingWindows(displayId)
  → WindowManagerService.setWindowsForAccessibilityCallback(displayId, ...)
  → AccessibilityWindowsPopulator.setWindowsNotification(true)
      → register()                                    // 行 221
      → nativeRegister()                              // JNI → android_window_WindowInfosListener.cpp:140
      → SurfaceComposerClient::addWindowInfosListener(listener)
      → WindowInfosListenerReporter::addWindowInfosListener(listener, ...)
      → if (mWindowInfosListeners.empty()) {
            surfaceComposer->addWindowInfosListener(this);  // Reporter 向 SF 注册自身
        }
      → mWindowInfosListeners.insert(listener)        // 本地 listener 加入集合
```

触发时机：
- 系统启动完毕（`BOOT_COMPLETED`）
- 用户开启无障碍服务（TalkBack、放大镜等）
- 显示器插拔（`onDisplayAdded`）

当所有无障碍服务关闭时，调用 `setWindowsNotification(false)` → `unregister()` → 从 Reporter 的本地集合中移除 listener。如果这是最后一个本地 listener，Reporter 还会从 SF 注销，**关闭 Binder 通道**。

#### `IWindowInfosReportedListener`：修复前后不变的基础设施

`IWindowInfosReportedListener` 和 `IWindowInfosReportedListener` 创建于 2020 年（AOSP 11 引入）：

```aidl
// IWindowInfosListener.aidl (修复前后不变)
oneway interface IWindowInfosListener {
    void onWindowInfosChanged(
        in WindowInfo[] windowInfos,
        in DisplayInfo[] displayInfos,
        in @nullable IWindowInfosReportedListener windowInfosReportedListener  // ← 一直存在
    );
}

// IWindowInfosReportedListener.aidl (修复前后不变)
oneway interface IWindowInfosReportedListener {
    void onWindowInfosReported();
}
```

Reporter 收到回调后，在进程内同步分发完所有本地 listener 后，如果 `windowInfosReportedListener` 非 null，就回调它：

```cpp
// WindowInfosListenerReporter.cpp:97-102 (修复前后不变)
for (auto listener : windowInfosListeners) {
    listener->onWindowInfosChanged(windowInfos, displayInfos);
}
if (windowInfosReportedListener) {
    windowInfosReportedListener->onWindowInfosReported();  // ack
}
```

| | 修复前 | 修复后 |
|----|--------|--------|
| 何时传 non-null | 仅 `shouldSync=true`（syncInputWindows） | **每次更新都传递** |
| 传递什么对象 | 同一个 `mWindowInfosReportedListener` | **每消息新建** `WindowInfosReportedListener(messageId, targetListener)` |
| 用途 | 计数归零 → 通知 sync 事务完成 | **per-message ack 追踪** → backpressure 的控制通道 |

修复不改变 AIDL 协议，只改变 SF 侧**何时传、传什么对象**——把原本只用于 sync 事务的 ack 通道扩展为通用的 flow-control 通道。

### 2.3 关键类和调用关系

| 层级 | 类/方法 | 进程 | 角色 |
|------|---------|------|------|
| 发送 | `SurfaceFlinger::updateInputFlinger()` | SF | 每帧入口 |
| 发送 | `SurfaceFlinger::buildWindowInfos()` | SF | 图层→WindowInfo 转换 |
| 发送 | `WindowInfosListenerInvoker::windowInfosChanged()` | SF | 遍历 listener 发送 |
| 协议 | `IWindowInfosListener.onWindowInfosChanged()` | AIDL | **oneway** |
| 接收 | `WindowInfosListenerReporter::onWindowInfosChanged()` | system_server | Binder stub |
| 消费 | `InputDispatcher::onWindowInfosChanged()` | system_server | 同步持锁处理 |
| 消费 | `PointerController::DisplayInfoListener::onWindowInfosChanged()` | system_server | 同步持锁处理 |
| 消费 | JNI `WindowInfosListener::onWindowInfosChanged()` | system_server | 弱引用解包→Java |
| 消费 | `AccessibilityWindowsPopulator.onWindowInfosChanged()` | system_server | `mHandler.post()` 异步 |
| ack | `IWindowInfosReportedListener.onWindowInfosReported()` | AIDL | **oneway**，仅 sync 时非空 |
| ack | `WindowInfosListenerInvoker::onListenerReported()` | SF | 新增：处理 ack |

## 3. Bug 分析

### 3.1 现象

在 CPU 压力场景（6 个 `yes` 进程占满 CPU0-5）下，system_server 出现约 1.78 秒的冻屏，Perfetto trace 记录如下：

```
slice: onWindowInfosChanged
  process: system_server [1475]
  thread:  binder:1475_1D [3807]
  duration: 1,777,357 μs (≈1.78s)
  nested slice: "Contending for pthread mutex, mutex owner: 1612" → 1,776,669 μs (99.96%)
```

同时 `logcat` 中密集出现：

```
oneway spamming  →  每份 log 出现 11-40 次
binder_alloc_buf failed to map pages in userspace, no vma
setTransactionState timed out!
```

### 3.2 时序

```
时刻 T0: SF updateInputFlinger() 发送 oneway onWindowInfosChanged
        → system_server Binder 线程收到 → JNI → 路径上访问 ART 全局引用锁
        → 该锁被 android.bg (tid 1612) 持有
        → android.bg 正在 UsageStatsService.H.handleMessage() 内
        → android.bg 优先级 130，低于 yes 的 120 → 几乎得不到 CPU

T0+16ms: SF 下一帧 → 再发一条 oneway onWindowInfosChanged
T0+32ms: 又一条
...
T0+1.78s: 共 ~111 条 oneway 消息堆积在 system_server 的 async binder buffer
         → binder buffer 耗尽 → binder_alloc_buf failed → 冻屏
T0+1.78s: android.bg 终于得到 CPU → 释放锁
         → binder 线程获取锁 → 处理堆积的 111 条消息 (无意义，仅最新状态有用)
```

### 3.3 根因

**SF 侧无 sender-side backpressure。** 核心链路有三重因素共同导致：

1. **`oneway` 语义**：`IWindowInfosListener.onWindowInfosChanged()` 定义为 `oneway`。调用方 `transact()` 即时返回，不等待远端处理。SF 可以 16ms/次无限制发送，不感知远端是否拥堵。

2. **`BackgroundExecutor` 异步投递**：`SurfaceFlinger::updateInputFlinger()` 将发送逻辑打包为 lambda 投递给 `BackgroundExecutor`。每帧一个 lambda，阻塞发生时 lambda 持续堆积排队。

   ```cpp
   // SurfaceFlinger.cpp:3265-3283 (修复前)
   BackgroundExecutor::getInstance().sendCallbacks({[...]() {
       mWindowInfosListenerInvoker->windowInfosChanged(
           windowInfos, displayInfos,
           inputWindowCommands.syncInputWindows);  // shouldSync
   }});
   ```

3. **`WindowInfosListenerInvoker::windowInfosChanged()` 无条件全量发送**：修复前实现简单遍历所有 listener，无条件调用 oneway Binder：

   ```cpp
   // WindowInfosListenerInvoker.cpp (修复前)
   void WindowInfosListenerInvoker::windowInfosChanged(...) {
       mCallbacksPending = windowInfosListeners.size();
       for (const auto& listener : windowInfosListeners) {
           listener->onWindowInfosChanged(windowInfos, displayInfos,
               shouldSync ? mWindowInfosReportedListener : nullptr);
       }
   }
   ```

   `mCallbacksPending` 仅用于 sync 事务的计数（当所有 listener ack 后触发 `mFlinger.windowInfosReported()`），**不是发送侧限流条件**。

### 3.4 阻塞点定位：两个 listener 都会阻塞，但原因不同

Reporter 在 Binder 线程中**同步串行**调用所有本地 listener。一旦某个 listener 阻塞，后续 listener 根本不会被调用到：

```cpp
// WindowInfosListenerReporter.cpp:97-99 (修复前后逻辑相同)
for (auto listener : windowInfosListeners) {
    listener->onWindowInfosChanged(windowInfos, displayInfos);  // 同步，逐个调用
}
```

在 Reporter 中添加计时代码后的复现日志证实**两个 listener 都有超时**：

| 地址 | 注册时间 | 身份 | 总调用 | 超时(>16ms) | 最大超时 | 平均 |
|------|---------|------|--------|------------|---------|------|
| `0xb4000072ecf4df00` | 05:12:28.256 | InputDispatcher | 601 | 10 次 | **96ms** | 1.1ms |
| `0xb4000072ecf19820` | 05:12:36.711 | JNI A11yPop | 435 | 8 次 | 31ms | 1.4ms |

注册时间戳排除了歧义：`0xb4000072ecf4df00` 在 05:12:28.256 注册，早于 `AccessibilityManagerService` 启动（05:12:28.432），必定是 `InputDispatcher`（`inputManager.start()` 内构造函数注册）。`0xb4000072ecf19820` 在 8 秒后注册，是 JNI A11yPop。

同一线程、同一时间戳的两条日志揭示了 `unordered_set` 的遍历顺序：

```
05:12:36.901  TID 1669  listener 0xb4000072ecf19820 took 0 ms   ← 先调用 (JNI A11yPop)
05:12:36.901  TID 1669  listener 0xb4000072ecf4df00 took 0 ms   ← 后调用 (InputDispatcher)
```

两个 listener 的阻塞原因**不同**：

#### InputDispatcher —— 被自身 looper 线程阻塞（mLock 竞争）

`InputDispatcher.cpp:6346-6363`：

```cpp
void InputDispatcher::onWindowInfosChanged(...) {
    // 行 6340-6344: 纯本地堆操作，无共享锁
    std::scoped_lock _l(mLock);   // ← 唯一获取的锁
    setInputWindowsLocked(handles, displayId);
    mLooper->wake();
}
```

`mLock` 定义在 `InputDispatcher.h:171`：`std::mutex mLock`。**这把锁不是只有 Binder 线程获取**——InputDispatcher 的 looper 线程在 `dispatchOnceInnerLocked()` 分发输入事件时也需要持有 `mLock`。如果 looper 线程在处理大量积压的输入事件（持锁数十 ms），Binder 线程的 `onWindowInfosChanged` 就会在 `mLock` 上阻塞。

`android.bg`（tid 1612）确实**不会**持有 `InputDispatcher::mLock`。但 **InputDispatcher 自己的 looper 线程会**。日志中 96ms 的峰值就是 looper 线程持锁分发事件时 Binder 线程等待的结果。

#### JNI 路径 —— 被任意 JNI 线程阻塞（ART VM 全局锁竞争）

`android_window_WindowInfosListener.cpp:96-121`：

```cpp
void onWindowInfosChanged(...) override {
    JNIEnv* env = AndroidRuntime::getJNIEnv();
    ScopedLocalFrame localFrame(env);
    jobject listener = env->NewGlobalRef(mListener);  // ← 行 103: 需要 VM 级锁
    ...
}
```

`NewGlobalRef(mListener)` 中 `mListener` 是 `jweak`——弱全局引用。调用链：

```
jni_internal.cc:851  NewGlobalRef(env, obj)
  → ScopedObjectAccess soa(env)
  → Decode<Object>(obj)              // 解析 weak ref: 访问 indirect reference table
  → AddGlobalRef(self, decoded)      // java_vm_ext.cc:692
      → WriterMutexLock mu(self, *Locks::jni_globals_lock_);   // 行 700: VM 级锁
      → globals_.Add(...)
```

`Locks::jni_globals_lock_` 是 **ART VM 级的 ReaderWriterMutex**（`art/runtime/base/locks.cc:147-148`）。`android.bg`（tid 1612）执行 `UsageStatsService.H.handleMessage()` → `FrameworkStatsLog.write()` → JNI → native 层时可能持有该锁。在 CPU 饥饿下（6 个 `yes` 进程抢占 CPU0-5），`android.bg` 得不到调度释放锁 → Binder 线程的 `NewGlobalRef` 等待该锁。

#### 两条阻塞路径对比

| 锁 | 被谁持有 | 阻塞对象 | 严重程度 |
|----|---------|---------|---------|
| `InputDispatcher::mLock` | **InputDispatcher looper 线程**（分发事件） | InputDispatcher Binder 回调 | 数十 ms（96ms 峰值） |
| `Locks::jni_globals_lock_` | **任意 JNI 线程**（android.bg 等） | JNI Binder 回调 | 数十 ms 到秒级（原 trace 1.78s） |

**这两个阻塞独立发生且可叠加**：在 Reporter 的同步循环中，InputDispatcher 阻塞 96ms + JNI 阻塞 31ms = 总延迟 >127ms，远超过 16ms 帧间隔。

### 3.5 关键代码路径上的锁汇总

| 锁 | 位置 | 作用域 | 持有者 | 与 onWindowInfosChanged 交集 |
|----|------|--------|--------|---------------------------|
| `InputDispatcher::mLock` | `setInputWindowsLocked()` | InputDispatcher 对象 | **InputDispatcher looper 线程** | ✅ Binder 线程等待 looper 释放 |
| `Locks::jni_globals_lock_` | `AddGlobalRef()` → `NewGlobalRef()` | **ART VM 全局** | 任何 JNI 线程（android.bg 等） | ✅ Binder JNI 线程等待其他 JNI 线程 |
| `Locks::jni_weak_globals_lock_` | weak global ref 解引用 | **ART VM 全局** | 任何 JNI 线程 | ✅ 同上 |
| `BinderProxy.sProxyMap` | `javaObjectForIBinder()` | Java 静态对象 | 任何 Binder 调用者 | ✅ 窗口 token 转换 |
| `DisplayInfoListener::mLock` | `onDisplayInfosChangedLocked()` | DisplayInfoListener 对象 | PointerController 自身 | ⚠️ 仅在 pointer 生命周期变更时短暂持锁 |
| WMS `mGlobalLock` | `getWindowsTransformMatrix()` | WMS 全局 | WMS 线程 | ⚠️ A11yPop 异步处理时 |

这些锁本身持有时间极短（μs 级），但在 CPU 饥饿下，锁持有者得不到调度，等待被放大到百毫秒甚至秒级。

## 4. 修复：Sender-side Backpressure

### 4.1 核心思想

复用旧协议中已有但仅用于 sync 的 `IWindowInfosReportedListener.onWindowInfosReported()` 回调，不改 AIDL 接口。

- **普通更新**：最多 1 个 in-flight 消息，后续帧合并为一份 latest-wins 延迟更新
- **强制更新**（可见窗口变化 / 焦点切换）：允许穿透，但受 `kMaxInFlightMessages` 硬上限限制
- **Sync 更新**：永远立即发送（调用方阻塞等待，不可 defer）

### 4.2 新增状态

```cpp
// WindowInfosListenerInvoker.h
std::mutex mMessagesMutex;           // 保护 flow-control 状态
uint64_t mNextMessageId = 1;

struct UnackedMessage {
    bool shouldSync;
    std::vector<wp<IBinder>> unackedListeners;   // 尚欠 ack 的 listener
    std::vector<sp<IWindowInfosReportedListener>> reportedListeners; // strong ref
};
std::unordered_map<uint64_t, UnackedMessage> mUnackedMessages;

bool mHasDelayedUpdate = false;
std::vector<WindowInfo> mDelayedWindowInfos;     // 合并后的最新更新
std::vector<DisplayInfo> mDelayedDisplayInfos;
uint32_t mDelayedCount = 0;

static constexpr size_t kMaxInFlightMessages = 4; // 硬上限
```

### 4.3 `WindowInfosReportedListener`：Binder 对象编码标识

旧 AIDL 中 `onWindowInfosReported()` 无参数。通过在 Binder 对象自身携带 `(messageId, targetListener)` 来支持多 in-flight 消息追踪，不改 AIDL：

```cpp
struct WindowInfosListenerInvoker::WindowInfosReportedListener
      : gui::BnWindowInfosReportedListener {
    WindowInfosListenerInvoker& mInvoker;
    const uint64_t mMessageId;
    const wp<IBinder> mTargetListener;   // 哪个 listener 发的 ack

    binder::Status onWindowInfosReported() override {
        mInvoker.onListenerReported(mMessageId, mTargetListener, false);
        return binder::Status::ok();
    }
};
```

### 4.4 发送路径

```cpp
void WindowInfosListenerInvoker::windowInfosChanged(...) {
    std::scoped_lock lock(mMessagesMutex);

    // 背压决策
    const bool atCapacity = mUnackedMessages.size() >= kMaxInFlightMessages;
    const bool deferUpdate = !shouldSync && !mUnackedMessages.empty() &&
            (!forceImmediateCall || atCapacity);

    if (deferUpdate) {
        // latest-wins: 只保留最新一份
        mDelayedWindowInfos = windowInfos;
        mDelayedDisplayInfos = displayInfos;
        mHasDelayedUpdate = true;
        mDelayedCount++;
        return;  // 不发送
    }

    // force 更新淘汰旧的 delayed 数据 (携带更新状态)
    if (mHasDelayedUpdate) {
        mHasDelayedUpdate = false;
        mDelayedCount = 0;
    }

    // 注册消息 + 快照 listener + 分配 messageId
    dispatchList = recordMessageLocked(shouldSync, &messageId);
    dispatchWindowInfos(messageId, dispatchList, windowInfos, displayInfos);
}
```

### 4.5 ack 路径

```
Reporter 处理完所有本地 listener
  → if (windowInfosReportedListener) onWindowInfosReported()  // oneway 回 SF
  → WindowInfosReportedListener::onWindowInfosReported()
  → WindowInfosListenerInvoker::onListenerReported(messageId, target, false)
      {
          scoped_lock(mMessagesMutex);
          找到消息 → 移除 target → 若 unacked 为空 → erase 消息
          若 shouldSync → syncCompletions++
          若 mUnackedMessages 为空 且 mHasDelayedUpdate → 准备 flush
      }
      mFlinger.windowInfosReported() × syncCompletions
      若 flush → dispatchWindowInfos(delayed)
```

### 4.6 `SurfaceFlinger.cpp` 调用点变化

```cpp
// 修复前
mWindowInfosListenerInvoker->windowInfosChanged(
    windowInfos, displayInfos, syncInputWindows);

// 修复后
const bool forceImmediateCall = visibleWindowsChanged ||
        inputWindowCommands.syncInputWindows ||
        !inputWindowCommands.focusRequests.empty();
mWindowInfosListenerInvoker->windowInfosChanged(
    windowInfos, displayInfos, syncInputWindows, forceImmediateCall);
```

新增 `visibleWindowsChanged` 检测：通过对比相邻帧的可见窗口 ID set（`mVisibleWindowIds`），识别窗口出现/消失（稀疏事件，不会被 backpressure spam）。

## 5. 时序图

### 5.1 正常流程 (无背压)

```plantuml
@startuml
!theme plain
autonumber
scale 1080 width
title WindowInfos 正常更新流程 (无背压)

box "SurfaceFlinger" #E3F2FD
    participant "updateInputFlinger()" as UIF
    participant "BackgroundExecutor" as BE
    participant "WindowInfosListenerInvoker" as Invoker
end box

box "Kernel" #F5F5F5
    participant "Binder Driver" as Binder
end box

box "system_server" #FFF3E0
    participant "WindowInfosListenerReporter\n(onWindowInfosChanged)" as Reporter
end box

box "system_server (Java)" #FFE0B2
    participant "WindowInfosListener\n(JNI → Java)" as JNI
    participant "AccessibilityWindowsPopulator\n(onWindowInfosChanged)" as A11y
end box

== 每帧触发 (Vsync, ~16ms) ==
UIF -> UIF: buildWindowInfos(windowInfos, displayInfos)
UIF -> BE: sendCallbacks(lambda)
BE -> Invoker: windowInfosChanged(windowInfos, displayInfos,\n  shouldSync=false, forceImmediateCall=false)

Invoker -> Invoker: lock mMessagesMutex
Invoker -> Invoker: mUnackedMessages.empty() → 发送
Invoker -> Invoker: recordMessageLocked(shouldSync=false)

group 快照 listeners
    Invoker -> Invoker: lock mListenersMutex
    Invoker -> Invoker: 遍历 mWindowInfosListeners
    Invoker -> Invoker: unlock mListenersMutex
end

Invoker -> Invoker: new messageId, UnackedMessage\{shouldSync=false\}
Invoker -> Invoker: create WindowInfosReportedListener(messageId, listenerBinder)
Invoker -> Invoker: unlock mMessagesMutex

Invoker -> Binder: listener->onWindowInfosChanged(data, reported) **oneway**
Binder -> Reporter: onWindowInfosChanged(windowInfos, displayInfos, reported)

Reporter -> Reporter: lock mListenersMutex\n复制本地 listener 集合
Reporter -> JNI: listener->onWindowInfosChanged(windowInfos, displayInfos)
JNI -> A11y: onWindowInfosChanged(windowHandles, displayInfos)
A11y -> A11y: mHandler.post(→ onWindowInfosChangedInternal)
JNI <-- A11y: return
Reporter <-- JNI: return

Reporter -> Binder: reported->onWindowInfosReported() **oneway**

Binder -> Invoker: onListenerReported(messageId, listener, false)
Invoker -> Invoker: lock mMessagesMutex\n移除 listener → 消息 fully acked → erase
Invoker -> Invoker: mUnackedMessages 为空 → 无 delayed → 无 flush
Invoker -> Invoker: unlock mMessagesMutex

@enduml
```

### 5.2 system_server 阻塞时的背压流程

```plantuml
@startuml
!theme plain
autonumber

title system_server 阻塞时的 Backpressure 流程

box "SurfaceFlinger" #E3F2FD
    participant "Vsync (~16ms)" as VSYNC
    participant "WindowInfosListenerInvoker" as Invoker
end box

box "system_server" #FFCDD2
    participant "Reporter" as Reporter
end box

== Frame N: 首次发送 ==
VSYNC -> Invoker: windowInfosChanged(A, forceImmediateCall=false)
Invoker -> Invoker: mUnackedMessages 为空 → 发送
Invoker -> Reporter: **oneway** onWindowInfosChanged(A, reported_msg1)
note right #FFB3B3: 消息 1 进入 system_server binder buffer\n但 system_server 阻塞，Reporter 未被调度

== Frame N+1 (~16ms later): 背压介入 ==
VSYNC -> Invoker: windowInfosChanged(B, forceImmediateCall=false)
Invoker -> Invoker: mUnackedMessages = {1} → 非空
Invoker -> Invoker: mDelayedWindowInfos = B (latest-wins)
Invoker -> Invoker: mHasDelayedUpdate = true, mDelayedCount = 1
Invoker -> Invoker: **return** (不发送)

== Frame N+2: 继续合并 ==
VSYNC -> Invoker: windowInfosChanged(C, forceImmediateCall=false)
Invoker -> Invoker: mDelayedWindowInfos = C (覆盖 B)
Invoker -> Invoker: mDelayedCount = 2
Invoker -> Invoker: **return**

== Frame N+3: forceImmediateCall=true (焦点切换) ==
VSYNC -> Invoker: windowInfosChanged(D, forceImmediateCall=true)
Invoker -> Invoker: atCapacity = false (1/4)\n→ 背压不生效 → 发送
Invoker -> Reporter: **oneway** onWindowInfosChanged(D, reported_msg2)

== (system_server 恢复) ==
Reporter -> Reporter: **处理 msg1** → A11y → ...
Reporter -> Invoker: **oneway** reported_msg1->onWindowInfosReported()
Invoker -> Invoker: onListenerReported(1, reporter):\n移除 reporter → msg1 还剩 0 listener → erase msg1\n→ mUnackedMessages = {2} → 未空 → 不 flush

Reporter -> Reporter: **处理 msg2** → A11y → ...
Reporter -> Invoker: **oneway** reported_msg2->onWindowInfosReported()
Invoker -> Invoker: onListenerReported(2, reporter):\n移除 reporter → msg2 还剩 0 listener → erase msg2\n→ mUnackedMessages 为空 → mHasDelayedUpdate=true

Invoker -> Invoker: **flush delayed**: mDelayedWindowInfos (= C, 合并自2帧)
Invoker -> Reporter: **oneway** onWindowInfosChanged(C, reported_msg3)

Reporter -> Reporter: **处理 msg3** → A11y 获得最新状态 C
Reporter -> Invoker: reported_msg3->onWindowInfosReported()

@enduml
```

### 5.3 force 更新达到硬上限

```plantuml
@startuml
!theme plain
autonumber

title forceImmediateCall 达到 kMaxInFlightMessages 时的背压

box "SurfaceFlinger" #E3F2FD
    participant "WindowInfosListenerInvoker" as Invoker
end box

== 前置条件: 4 条 force update 已发出，全部未 ack ==
note over Invoker: mUnackedMessages.size() == 4\n(atCapacity == true)

== 第 5 条 force update ==
Invoker -> Invoker: windowInfosChanged(E, forceImmediateCall=true)
Invoker -> Invoker: !shouldSync && !mUnackedMessages.empty()\n&& (!forceImmediateCall || atCapacity)\n= true && true && (false || true) = true
Invoker -> Invoker: **DEFER** — 即使 force 也被 coalesce!
note right: 硬上限防止 force update 自身\n成为 oneway spam 来源

@enduml
```

## 6. 完整注册与更新流程 (PlantUML 长图)

```plantuml
@startuml
!theme plain
autonumber "<b>[0]"
scale 1080 width
title WindowInfos: 注册到更新的完整流程 (修复后)

box "SurfaceFlinger Process" #E3F2FD
    participant "SurfaceFlinger\nupdateInputFlinger()" as SF
    participant "BackgroundExecutor" as BE
    participant "WindowInfosListenerInvoker" as Invoker
end box

box "Kernel" #F5F5F5
    participant "Binder Driver" as Binder
end box

box "system_server Process (Native)" #FFF3E0
    participant "WindowInfosListenerReporter\n(Singleton, BnWindowInfosListener)" as Reporter
    participant "InputDispatcher\nonWindowInfosChanged()" as InputDisp
    participant "PointerController\nDisplayInfoListener" as PointerCtrl
end box

box "system_server Process (JNI)" #FFECB3
    participant "WindowInfosListener\n(JNI bridge)" as JNI
end box

box "system_server Process (Java)" #FFE0B2
    participant "AccessibilityWindowsPopulator\nonWindowInfosChanged()" as A11yPop
    participant "WMS Handler" as WMS_H
end box

== 0. 注册阶段 ==

note over InputDisp, Reporter
  **system_server 内**: InputDispatcher 注册 DispatcherWindowListener
  **system_server 内**: PointerController 注册 DisplayInfoListener
  **system_server 内**: A11yPop 注册 JNI WindowInfosListener
  三者均通过 SurfaceComposerClient::addWindowInfosListener()
  → WindowInfosListenerReporter::addWindowInfosListener()
  → 首次时 Reporter 向 SF 注册自身 (BnWindowInfosListener)
  三个本地 listener 共享同一个 Reporter 单例 → SF 只看到 1 个 proxy
end note

== 1. 帧触发 ==

SF -> SF: buildWindowInfos(windowInfos, displayInfos)
SF -> SF: 检测 visibleWindowsChanged (对比 mVisibleWindowIds)
SF -> BE: sendCallbacks(lambda)

== 2. 发送决策 (Backpressure) ==

BE -> Invoker: windowInfosChanged(windowInfos, displayInfos,\n  shouldSync, forceImmediateCall)

Invoker -> Invoker: lock mMessagesMutex
alt 背压 (mUnackedMessages 非空 且 !forceImmediateCall)
    Invoker -> Invoker: latest-wins 合并到 mDelayedWindowInfos
    Invoker -> Invoker: return (不发送)
else 背压 + force + atCapacity
    Invoker -> Invoker: 同样合并 (硬上限)
else 发送
    Invoker -> Invoker: recordMessageLocked(shouldSync)
    Invoker -> Invoker: 快照 mWindowInfosListeners
    Invoker -> Invoker: new UnackedMessage{shouldSync, unackedListeners}
    Invoker -> Invoker: new WindowInfosReportedListener(messageId, listenerBinder)
    Invoker -> Invoker: unlock mMessagesMutex
    Invoker -> Invoker: dispatchWindowInfos(messageId, dispatchList, ...)
end

== 3. 跨进程分发 ==

Invoker -> Binder: listener->onWindowInfosChanged(data, reported) **oneway**

Binder -> Reporter: onWindowInfosChanged(windowInfos, displayInfos, reported)
Reporter -> Reporter: lock mListenersMutex, 快照本地 listeners

par 本地 listener: InputDispatcher
    Reporter -> InputDisp: onWindowInfosChanged(windowInfos, displayInfos)
    InputDisp -> InputDisp: std::scoped_lock _l(mLock)
    InputDisp -> InputDisp: setInputWindowsLocked(...)
end

par 本地 listener: PointerController
    Reporter -> PointerCtrl: onWindowInfosChanged(windowInfos, displayInfos)
    PointerCtrl -> PointerCtrl: std::scoped_lock lock(mLock)\nonDisplayInfosChangedLocked(...)
end

par 本地 listener: JNI → A11yPop
    Reporter -> JNI: onWindowInfosChanged(windowInfos, displayInfos)
    JNI -> JNI: NewGlobalRef(mListener)
    JNI -> JNI: fromWindowInfos(env, windowInfos)
    JNI -> JNI: CallVoidMethod → Java onWindowInfosChanged(...)
    JNI -> A11yPop: onWindowInfosChanged(windowHandles, displayInfos)
    A11yPop -> A11yPop: mHandler.post(→ onWindowInfosChangedInternal)
end

Reporter -> Binder: **if (reported)** reported->onWindowInfosReported() **oneway**

== 4. ack 处理 ==

Binder -> Invoker: onListenerReported(messageId, targetListener, false)
Invoker -> Invoker: lock mMessagesMutex
Invoker -> Invoker: 找到 message → 移除 targetListener
Invoker -> Invoker: unacked 为空 → erase message
alt shouldSync
    Invoker --> SF: mFlinger.windowInfosReported()
end
alt mUnackedMessages 为空 且 mHasDelayedUpdate
    Invoker -> Invoker: move delayedWindowInfos → recordMessageLocked
    Invoker -> Invoker: unlock mMessagesMutex
    Invoker -> Invoker: dispatchWindowInfos(delayed...)
end

@enduml
```

## 7. 修复效果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| "oneway spamming" | 11-40 次/份日志 | **0** |
| `binder_alloc_buf failed` | 密集出现 | 与 WindowInfo 路径无关的其他 binder 错误 |
| SF transact failed | N/A | **0** |
| listener died | N/A | **0** |
| Recorded ≈ fully acked | 无追踪 | **完全匹配** (消息生命周期健康) |
| 背压 coalesce 率 | 无 | 50-57% (正常负载下拦截一半以上) |

## 8. 附录

### 8.1 `SurfaceFlinger::updateInputFlinger()` 调用上下文

```
VSYNC Signal
  ↓
MessageQueue::handleMessage()
  ↓
SurfaceFlinger::commit()
  ├── commitTransactions()        ← 应用窗口属性变更
  ├── updateLayerGeometry()       ← 计算可见区域
  ├── updateInputFlinger()        ← [本文主角] 窗口信息同步
  │     ├── buildWindowInfos()
  │     ├── 检测 visibleWindowsChanged
  │     └── BackgroundExecutor::sendCallbacks(lambda)
  │           └── WindowInfosListenerInvoker::windowInfosChanged()
  │                 ├── [背压决策] defer / send
  │                 ├── recordMessageLocked()
  │                 └── dispatchWindowInfos()
  │                       └── listener->onWindowInfosChanged() oneway Binder
  └── composite()                ← GPU/HWC 合成上屏
```

### 8.2 线程模型

| 线程 | 进程 | 职责 |
|------|------|------|
| SF Main Thread | surfaceflinger | `updateInputFlinger()` 入口 |
| BackgroundExecutor | surfaceflinger | 执行 lambda (发送 Binder) |
| Binder threads | surfaceflinger | 接收 `onWindowInfosReported()` ack |
| Binder threads | system_server | 接收 `onWindowInfosChanged()` → Reporter 同步分发到 InputDispatcher/PointerCtrl/JNI |
| WMS Handler | system_server | `onWindowInfosChangedInternal()` 异步处理 |
