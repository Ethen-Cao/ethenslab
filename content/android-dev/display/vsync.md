+++
title = "AOSP 16 VSync 实现机制"
date = 2026-05-16
+++

本文档基于 AOSP 16（Baklava）源码，自底向上详细剖析 VSync 的完整实现机制。

---

## 架构总览

VSync 在 AOSP 16 中分为 **八个层次**，数据流自底向上：

```
HWC HAL  →  VsyncSchedule  →  VSyncReactor  →  VSyncPredictor  →  VSyncDispatchTimerQueue  →  EventThread  →  App (Choreographer)
                ↑                   ↑                  ↑                    ↑                        ↑
          每显示器的总控     处理&确认期        线性回归预测          定时器触发回调           跨进程事件分发

                          FrameTargeter  →  Scheduler (onFrameSignal)
                                ↑                    ↑
                          帧目标规划        Pacesetter 驱动 + Follower 对齐
```

核心调度器组件位于以下路径：
- `frameworks/native/services/surfaceflinger/Scheduler/`
- `frameworks/native/libs/gui/`
- `hardware/interfaces/graphics/composer/aidl/android/hardware/graphics/composer3/IComposerCallback.aidl`

---

## 第一层：HWC 硬件 VSync 事件源

### AIDL 接口定义

硬件 Composer HAL 通过 AIDL 回调向 SurfaceFlinger 报告 VSync 事件。接口定义在 `IComposerCallback.aidl`：

```java
// hardware/interfaces/graphics/composer/aidl/android/hardware/graphics/composer3/IComposerCallback.aidl
oneway void onVsync(long display, long timestamp, int vsyncPeriodNanos);
oneway void onVsyncPeriodTimingChanged(long display, in VsyncPeriodChangeTimeline updatedTimeline);
oneway void onVsyncIdle(long display);
```

### AidlComposerHal 的回调桥接

`AidlComposerHal.cpp:192-196` 中的 `AidlIComposerCallbackWrapper::onVsync` 接收 AIDL 回调后，立即转发给 `ComposerCallback::onComposerHalVsync`：

```cpp
::ndk::ScopedAStatus onVsync(int64_t in_display, int64_t in_timestamp,
                             int32_t in_vsyncPeriodNanos) override {
    mCallback.onComposerHalVsync(translate<Display>(in_display), in_timestamp,
                                 static_cast<uint32_t>(in_vsyncPeriodNanos));
    return ::ndk::ScopedAStatus::ok();
}
```

注意 HWC 回调线程被设置为 `SCHED_FIFO` 调度策略，优先级为 2（`AidlComposerHal.cpp:358`）：

```cpp
AIBinder_setMinSchedulerPolicy(binder.get(), SCHED_FIFO, 2);
```

VSync 的开关由 `setVsyncEnabled` 控制（`AidlComposerHal.cpp:837-846`）：

```cpp
Error AidlComposer::setVsyncEnabled(Display display, IComposerClient::Vsync enabled) {
    const bool enableVsync = enabled == IComposerClient::Vsync::ENABLE;
    const auto status = mAidlComposerClient->setVsyncEnabled(
            translate<int64_t>(display), enableVsync);
    ...
}
```

### SurfaceFlinger::onComposerHalVsync

SurfaceFlinger 收到回调后（`SurfaceFlinger.cpp:2452-2465`），完成两个动作：

1. 调用 `HWComposer::onVsync` 验证 HW 显示 ID 并过滤重复 VSync
2. 调用 `Scheduler::addResyncSample` 将时间戳送入 VSyncReactor

```cpp
void SurfaceFlinger::onComposerHalVsync(hal::HWDisplayId hwcDisplayId, int64_t timestamp,
                                        std::optional<hal::VsyncPeriodNanos> vsyncPeriod) {
    Mutex::Autolock lock(mStateLock);
    if (const auto displayIdOpt = getHwComposer().onVsync(hwcDisplayId, timestamp)) {
        if (mScheduler->addResyncSample(*displayIdOpt, timestamp, vsyncPeriod)) {
            mScheduler->modulateVsync(displayIdOpt, &VsyncModulator::onRefreshRateChangeCompleted);
        }
    }
}
```

`HWComposer::onVsync`（`HWComposer.cpp:157-188`）验证 display ID，过滤重复时间戳，并返回 `PhysicalDisplayId`：

```cpp
std::optional<PhysicalDisplayId> HWComposer::onVsync(hal::HWDisplayId hwcDisplayId,
                                                     nsecs_t timestamp) {
    // 过滤重复 VSYNC（HWC 在开关屏时可能产生）
    if (timestamp == displayData.lastPresentTimestamp) {
        ALOGW("Ignoring duplicate VSYNC event for display %s (t=%" PRId64 ")",
              to_string(*displayIdOpt).c_str(), timestamp);
        return {};
    }
    displayData.lastPresentTimestamp = timestamp;
    return displayIdOpt;
}
```

---

## 第二层：VsyncSchedule — 每显示器调度总控

`VsyncSchedule`（`VsyncSchedule.h`）是一个物理显示器上 VSync 的调度总控类，它持有三件核心组件：

```cpp
class VsyncSchedule final : public IVsyncSource {
    const TrackerPtr mTracker;   // VSyncPredictor：预测未来 VSync 时间
    const DispatchPtr mDispatch; // VSyncDispatchTimerQueue：定时器回调分发
    const ControllerPtr mController; // VSyncReactor：处理原始 HW VSync 事件
};
```

### 硬件 VSync 的启用/禁用

`VsyncSchedule` 维护了一个三状态的状态机（`VsyncSchedule.h:139-153`）：

```cpp
enum class HwVsyncState {
    Enabled,     // 硬件 VSync 开启中
    Disabled,    // 硬件 VSync 已关闭（可以被重新启用）
    Disallowed,  // 硬件 VSync 不允许开启（如显示关闭时）
};
```

`enableHardwareVsyncLocked`（`VsyncSchedule.cpp:181-192`）在启用时会 `resetModel` 清除旧的模型数据，然后调用 `mRequestHardwareVsync(mId, true)` 最终调到 `setVsyncEnabled` 开启 HWC 侧 VSync 信号。

### 创建工厂方法

`VsyncSchedule::createTracker` 和 `createDispatch` 定义了关键参数（`VsyncSchedule.cpp:114-134`）：

```cpp
static TrackerPtr createTracker(...) {
    constexpr size_t kHistorySize = 20;           // 保留最近 20 个 vsync 样本
    constexpr size_t kMinSamplesForPrediction = 6;// 最少 6 个样本才能开始预测
    constexpr uint32_t kDiscardOutlierPercent = 20;// 偏离预期超过 20% 的样本视为异常
    return std::make_unique<VSyncPredictor>(...);
}

static DispatchPtr createDispatch(TrackerPtr tracker) {
    constexpr std::chrono::nanoseconds kGroupDispatchWithin = 500us;  // 500μs 内的回调合并
    constexpr std::chrono::nanoseconds kSnapToSameVsyncWithin = 3ms;  // 3ms 内的 VSync 视为同一个
    return std::make_unique<VSyncDispatchTimerQueue>(...);
}
```

---

## 第三层：VSyncReactor — 硬件 VSync 事件处理

`VSyncReactor` 实现 `VsyncController` 接口（`VsyncController.h`），负责：

### 核心职责

1. **处理 HW VSync 时间戳**（`addHwVsyncTimestamp`）
2. **处理 Present Fence 作为 VSync 信号**（`addPresentFence`）
3. **显示模式切换时的周期校准**（`onDisplayModeChanged`）
4. **周期确认**（`periodConfirmed`）

### addHwVsyncTimestamp 的完整逻辑

`VSyncReactor.cpp:197-242` — 这是 VSync 处理的核心：

```cpp
bool VSyncReactor::addHwVsyncTimestamp(nsecs_t timestamp,
                                       std::optional<nsecs_t> hwcVsyncPeriod,
                                       bool* periodFlushed) {
    std::lock_guard lock(mMutex);

    if (periodConfirmed(timestamp, hwcVsyncPeriod)) {
        // 1) 周期已确认 → 写入新显示模式到 Tracker
        // 2) 将上一个 HW vsync 和当前时间戳都加入 Tracker 模型
        // 3) 结束周期切换
        mTracker.setDisplayModePtr(...);
        mTracker.addVsyncTimestamp(*mLastHwVsync.get());
        mTracker.addVsyncTimestamp(timestamp);
        endPeriodTransition();
        mMoreSamplesNeeded = mTracker.needsMoreSamples();
    } else if (mPeriodConfirmationInProgress) {
        // 周期正在确认中 → 暂存当前 timestamp 为 mLastHwVsync
        mLastHwVsync.set(timestamp);
        mMoreSamplesNeeded = true;
    } else {
        // 正常状态 → 直接加入 Tracker
        mTracker.addVsyncTimestamp(timestamp);
        mMoreSamplesNeeded = mTracker.needsMoreSamples();
    }

    if (!mMoreSamplesNeeded) {
        setIgnorePresentFencesInternal(false); // 停止忽略 Present Fence
    }
    return mMoreSamplesNeeded; // 返回 true 则继续开启 HW VSync
}
```

### periodConfirmed — 周期确认算法

`VSyncReactor.cpp:162-195` 决定新刷新率何时确认生效：

```cpp
bool VSyncReactor::periodConfirmed(nsecs_t vsync_timestamp,
                                   std::optional<nsecs_t> hwcVsyncPeriod) {
    // 如果 HWC 提供了 vsync 周期
    if (hwcVsyncPeriod) {
        return std::abs(*hwcVsyncPeriod - period) < allowance;
    }
    // 否则通过相邻两个 HW VSync 的间距来验证
    auto const distance = vsync_timestamp - *mLastHwVsync.get();
    return std::abs(distance - period) < allowance;
}
```

allowance 为 `period * 10%`，即允许 10% 的误差。

---

## 第四层：VSyncPredictor — 线性回归预测引擎

`VSyncPredictor`（`VSyncPredictor.cpp`）是核心预测引擎，使用**简单线性回归**对 VSync 时间戳建模。

### 数据结构

```cpp
class VSyncPredictor : public VSyncTracker {
    std::vector<nsecs_t> mTimestamps; // 环形缓冲区，最多 20 个样本
    std::unordered_map<nsecs_t, Model> mRateMap; // 每个刷新率的模型: {slope, intercept}
    std::deque<VsyncTimeline> mTimelines; // 时间线队列（处理帧率切换）
};
```

其中 `Model` 结构体为：
```cpp
struct Model {
    nsecs_t slope;     // 计算出的 vsync 周期（ns）
    nsecs_t intercept; // 截距偏移（ns）
};
```

### addVsyncTimestamp — 线性回归计算

`VSyncPredictor.cpp:150-290` — 每次收到新的 VSync 时间戳时：

1. **验证** — `validate()` 检查新时间戳是否与已有模型对齐（偏差在 `kOutlierTolerancePercent` 即 20% 以内），否则丢弃
2. **缓存** — 写入环形缓冲区 `mTimestamps`
3. **线性回归** — 当样本数 ≥ `kMinimumSamplesForPrediction`（6 个）时，执行计算：

```cpp
// 简单线性回归公式:
// slope = Sigma_i( (X_i - mean(X)) * (Y_i - mean(Y) ) / Sigma_i ( (X_i - mean(X))^2 )
// intercept = mean(Y) - slope * mean(X)
// 其中 Y = vsync 时间戳, X = vsync 序号

nsecs_t const anticipatedPeriod = top * kScalingFactor / bottom;
nsecs_t const intercept = meanTS - (anticipatedPeriod * meanOrdinal / kScalingFactor);

// 如果计算出的周期偏离理想周期超过 20%，回退到理想周期
if (percent >= kOutlierTolerancePercent) {
    it->second = {idealPeriod(), 0};
    clearTimestamps(true);
    return false;
}
```

### nextAnticipatedVSyncTimeFrom — 预测下一个 VSync

`VSyncPredictor.cpp:372-412` — 使用 `snapToVsync` 计算时间点，然后通过 `VsyncTimeline` 调整帧率对齐：

```cpp
nsecs_t VSyncPredictor::nextAnticipatedVSyncTimeFrom(nsecs_t timePoint, ...) {
    // 遍历所有 timeline，找到第一个能返回有效 vsync 的 timeline
    for (auto& timeline : mTimelines) {
        vsyncOpt = timeline.nextAnticipatedVSyncTimeFrom(model, minFramePeriodOpt,
                                                         snapToVsync(timePoint), ...);
        if (vsyncOpt) break;
    }
    return vsyncOpt->ns();
}
```

`snapToVsync`（`VSyncPredictor.cpp:292-329`）计算下一个 VSync 边界：

```cpp
nsecs_t VSyncPredictor::snapToVsync(nsecs_t timePoint) const {
    auto const [slope, intercept] = getVSyncPredictionModelLocked();
    auto const zeroPoint = oldest + intercept;
    auto const ordinalRequest = (timePoint - zeroPoint + slope) / slope;
    auto const prediction = (ordinalRequest * slope) + intercept + oldest;
    return prediction;
}
```

### VsyncTimeline — 多帧率时间线

`VsyncPredictor` 内部使用 `VsyncTimeline` 管理帧率切换。每次 `setRenderRate`（设置新的渲染帧率）时，旧的 timeline 会被 `freeze`（冻结有效期），新的 timeline 被追加到队尾（`VSyncPredictor.cpp:446-477`）。过期的 timeline 在 `purgeTimelines` 中清理。

---

## 第五层：VSyncDispatchTimerQueue — 定时器队列回调分发

`VSyncDispatchTimerQueue` 实现 `VSyncDispatch` 接口，核心功能是**在预测的 VSync 时间之前触发回调**。

### ScheduleTiming 参数

`VSyncDispatch.h:102-113` — 每个回调的调度参数：

```cpp
struct ScheduleTiming {
    nsecs_t workDuration = 0;  // 客户端需要的工作时间
    nsecs_t readyDuration = 0; // 客户端完成后，剩余的 ready 时间（给 SF 处理 buffer）
    nsecs_t lastVsync = 0;     // 目标 VSync 的最早基准时间
    std::optional<nsecs_t> committedVsyncOpt; // 已承诺的 VSync 时间
};
```

**回调在 `workDuration + readyDuration` 纳秒前触发**，公式为：

```
wakeupTime = predictedVsyncTime - workDuration - readyDuration
```

### 调度逻辑

`VSyncDispatchTimerQueueEntry::schedule`（`VSyncDispatchTimerQueue.cpp:90-118`）：

```cpp
ScheduleResult VSyncDispatchTimerQueueEntry::schedule(ScheduleTiming timing,
                                                      VSyncTracker& tracker, nsecs_t now) {
    // 计算目标 VSync 时间
    auto nextVsyncTime = tracker.nextAnticipatedVSyncTimeFrom(
            std::max(timing.lastVsync, now + timing.workDuration + timing.readyDuration),
            timing.committedVsyncOpt.value_or(timing.lastVsync));
    // 计算唤醒时间
    auto nextWakeupTime = nextVsyncTime - timing.workDuration - timing.readyDuration;
    // 检测是否会跳过一个目标 VSync
    bool wouldSkipAVsyncTarget = mArmedInfo &&
            (nextVsyncTime > (mArmedInfo->mActualVsyncTime + mMinVsyncDistance));
    // 调整以避免重复分发
    nextVsyncTime = adjustVsyncIfNeeded(tracker, nextVsyncTime);
    ...
}
```

`adjustVsyncIfNeeded`（`VSyncDispatchTimerQueue.cpp:132-153`）确保不会为同一个 VSync 事件多次分发回调，也不会在两个 VSync 事件之间插入多余的唤醒。

### 定时器机制

`VSyncDispatchTimerQueue::timerCallback`（`VSyncDispatchTimerQueue.cpp:334-379`）在定时器触发时：

1. 遍历所有已注册的回调
2. 对于 `wakeupTime` 在 `intendedWakeupTime + timerSlack` 范围内的回调，调用 `executing()` 转移到 running 状态
3. 解锁后，逐一调用 `callback(vsyncTimestamp, wakeupTimestamp, deadlineTimestamp)`
4. 重新 `rearmTimer` 为下一个最近的唤醒时间设置定时器

---

## 第六层：EventThread — 客户端 VSync 事件分发

`EventThread`（`EventThread.h`）向所有连接的客户端进程分发 VSync 事件。

### 事件的分发机制

`EventThread::threadMain`（`EventThread.cpp:532-637`）运行在自己的线程上（`SCHED_FIFO`，优先级 2），使用状态机：

```cpp
enum class State {
    Idle,           // 空闲，等待事件或客户端请求
    Quit,           // 退出
    SyntheticVSync, // 合成 VSync（屏幕关闭时，15ms 间隔）
    VSync,          // 正常 VSync（通过 VSyncDispatch 调度）
};
```

核心循环逻辑：

1. 检查 `mPendingEvents` 队列，将事件分发给匹配的客户端
2. 检查是否有客户端请求 VSync（`VSyncRequest != None`）
3. 如果有 VSync 请求：
   - 正常情况：`schedule` VSync 回调到 `VSyncDispatch`
   - 屏幕关闭且 omission 启用：进入 Idle 状态，等待 `screen on`
   - 合成 VSync：进入 SyntheticVSync 状态，60Hz 伪 VSync
4. 等待新事件或新连接请求
5. **超时保护**：如果 1000ms 内没有收到 VSync（驱动卡死），生成假的 VSync 事件

```cpp
// 超时保护：驱动卡死时生成假 VSync
const std::chrono::nanoseconds timeout = mState == State::SyntheticVSync ? 16ms : 1000ms;
if (mCondition.wait_for(lock, timeout) == std::cv_status::timeout) {
    if (mState == State::VSync) {
        ALOGW("Faking VSYNC due to driver stall for thread %s", mThreadName);
    }
    // 生成假 VSync 事件
}
```

### VSync 请求类型

客户端可以设置不同的 VSync 请求模式（`EventThread.h:61-69`）：

```cpp
enum class VSyncRequest {
    None = -2,                    // 不请求 VSync
    Single = -1,                  // 下一个两帧都触发（避免调度开销）
    SingleSuppressCallback = 0,   // 只触发下一帧，抑制回调
    Periodic = 1,                 // 每帧都触发
    // 后续值表示每 N 帧触发
};
```

### shouldConsumeEvent — 事件过滤

`EventThread.cpp:639-703` 对每个客户端决定是否消费事件：

```cpp
case DisplayEventType::DISPLAY_EVENT_VSYNC:
    switch (connection->vsyncRequest) {
        case VSyncRequest::None:
            return false;
        case VSyncRequest::Single:
            if (throttleVsync()) return false; // 帧率节流
            connection->vsyncRequest = VSyncRequest::SingleSuppressCallback;
            return true;
        case VSyncRequest::Periodic:
            if (throttleVsync()) return false;
            return true;
        default:
            // 自定义帧率：每 N 个 VSync 触发一次
            return event.vsync.count % vsyncPeriod(connection->vsyncRequest) == 0;
    }
```

### throttleVsync — VSync 节流

节流检查在 `shouldConsumeEvent`（第 641-652 行）中：

```cpp
const auto throttleVsync = [&]() REQUIRES(mMutex) {
    if (connection->frameRate.isValid()) {
        // 如果 Choreographer 设置了特定帧率，检查 VSync 相位
        return !mVsyncSchedule->getTracker()
                        .isVSyncInPhase(vsyncData.preferredExpectedPresentationTime(),
                                       connection->frameRate);
    }
    // 否则使用 Scheduler 的全局节流
    return mCallback.throttleVsync(expectedPresentTime, connection->mOwnerUid);
};
```

### FrameTimeline 生成

`EventThread::generateFrameTimeline`（`EventThread.cpp:714-769`）为每个 VSync 事件生成多个 FrameTimeline 选项（最多 16 个），每个对应一个可能的帧间隔倍数。这些选项被编码到 `VsyncEventData` 中发送给客户端，实现**多帧率兼容**。

---

## 第七层：客户端 — DisplayEventReceiver 和 Choreographer

### DisplayEventReceiver

`DisplayEventReceiver`（`DisplayEventReceiver.cpp`）是客户端侧的 VSync 事件接收器：

1. **构造**时通过 `ISurfaceComposer.createDisplayEventConnection` 与 SurfaceFlinger 建立连接
2. 使用 `BitTube`（Unix socket 对）作为跨进程通信通道
3. `getFd()` 返回文件描述符，客户端可将其添加到 Looper 中 epoll 监听
4. 调用 `setVsyncRate(count)` 请求每 `count` 个 VSync 接收一次事件
5. 调用 `requestNextVsync()` 请求下一次 VSync 事件

### Choreographer

`Choreographer`（`Choreographer.h`）继承 `DisplayEventDispatcher`，是应用层与 VSync 交互的主入口：

```cpp
class Choreographer : public DisplayEventDispatcher, public MessageHandler {
    void dispatchVsync(nsecs_t timestamp, PhysicalDisplayId displayId, uint32_t count,
                       VsyncEventData vsyncEventData) override;
    void postFrameCallbackDelayed(...);  // 注册帧回调
    void registerRefreshRateCallback(...); // 注册刷新率回调
};
```

Choreographer 内部有一个优先队列 `mFrameCallbacks`，当收到 VSync 事件时，`dispatchVsync` 将 `mFrameCallbacks` 中 `dueTime <= timestamp` 的回调提取出来并执行。

---

## 第八层：相位偏移 — VsyncConfigSet 和 VsyncModulator

### VsyncConfigSet

`VsyncConfig.h` 定义了三种 VSync 相位模式：

```cpp
struct VsyncConfigSet {
    VsyncConfig late;  // 默认延迟相位
    VsyncConfig early; // 早期相位（事务触发）
    VsyncConfig earlyGpu; // GPU 早期相位（GPU 合成触发）
};
```

每个 `VsyncConfig` 包含：
- `sfOffset` — SurfaceFlinger 的 VSync 偏移
- `appOffset` — 应用的 VSync 偏移

### WorkDuration 相位计算

`WorkDuration`（`VsyncConfiguration.h:144-169`）将相位定义为**工作时间**：

| 参数 | 用途 |
|------|------|
| `mSfDuration` | SF 完成合成的预计时间 |
| `mAppDuration` | App 完成渲染的预计时间 |
| `mSfEarlyDuration` | Early 模式下的 SF 时间 |
| `mAppEarlyDuration` | Early 模式下的 App 时间 |
| `mSfEarlyGpuDuration` | GPU 合成 Early 模式下的 SF 时间 |
| `mAppEarlyGpuDuration` | GPU 合成 Early 模式下的 App 时间 |

### VsyncModulator 动态相位调制

`VsyncModulator`（`VsyncModulator.h`）在运行时动态调整 VSync 相位：

```cpp
class VsyncModulator {
    std::atomic<Schedule> mTransactionSchedule;
    std::atomic<int> mEarlyTransactionFrames; // 剩余 early 帧数（默认 2）
    std::atomic<int> mEarlyGpuFrames;          // 剩余 early GPU 帧数（默认 2）
    std::atomic<bool> mRefreshRateChangePending;
};
```

触发 early 相位的条件：
- `setTransactionSchedule(Early)` — 检测到早期事务
- `onRefreshRateChangeInitiated()` — 刷新率切换开始
- `onDisplayRefresh(true)` — 使用了 GPU 合成

early 相位持续 `MIN_EARLY_TRANSACTION_FRAMES`（2 帧），起到**低通滤波**作用，防止在后续帧延迟或合成策略交替时出现抖动。

---

## 第八点五层：FrameTargeter — SurfaceFlinger 帧目标规划

VSync 触发后，SurfaceFlinger 并不直接把所有内容提交到硬件。`FrameTargeter`（`FrameTargeter.h` / `FrameTargeter.cpp`）接收 VSync 信息，**计算本帧的 `expectedPresentTime`（预计送显时间），并判断是否存在背压（Backpressure）或丢帧（Missed Frame）**。它是连接 VSync 调度和实际合成的核心枢纽。

### 数据结构

`FrameTarget` 是 `FrameTargeter` 内部计算出的**只读帧指标**：

```cpp
// FrameTargeter.h:44-122
class FrameTarget {
    VsyncId mVsyncId;
    TimePoint mFrameBeginTime;         // 帧实际开始时间
    TimePoint mExpectedPresentTime;    // 预计送显时间（帧的核心目标）
    std::optional<TimePoint> mEarliestPresentTime;
    bool mFramePending;                // 上一帧的 Fence 仍未 signal?
    bool mWouldBackpressureHwc;        // 本帧是否会导致 HWC 背压?
    bool mFrameMissed;                 // 是否丢帧?
    bool mHwcFrameMissed;              // HWC 层面是否丢帧?
    bool mGpuFrameMissed;              // GPU 层面是否丢帧?
    ui::RingBuffer<PresentFence, 5> mPresentFences; // 最近 5 帧的 Present Fence
};
```

### beginFrame — 帧生命周期入口

`Scheduler::onFrameSignal` 调用 `FrameTargeter::beginFrame`（`FrameTargeter.cpp:95-185`），核心逻辑：

**1. 计算 `mExpectedPresentTime`**（第 101-124 行）：

```cpp
void FrameTargeter::beginFrame(const BeginFrameArgs& args, const IVsyncSource& vsyncSource) {
    mFrameBeginTime = args.frameBeginTime;
    mScheduledPresentTime = args.expectedVsyncTime;

    const Period vsyncPeriod = vsyncSource.period();

    // 关键判断：调度时的 expectedVsyncTime 是否仍在未来
    if (args.expectedVsyncTime >= args.frameBeginTime) {
        // 正常路径：VSync 预测值仍在未来 → 直接使用
        mExpectedPresentTime = args.expectedVsyncTime;
    } else {
        // 延迟路径：VSync 预测已过期 → 重新计算下一个 VSync 截止点
        mExpectedPresentTime = vsyncSource.vsyncDeadlineAfter(args.frameBeginTime);
        // 如果 sfWorkDuration 超出一个 VSync 周期，目标下一个周期
        if (args.sfWorkDuration > vsyncPeriod) {
            mExpectedPresentTime += vsyncPeriod;
        }
    }
}
```

**2. 背压检测** — `expectedSignaledPresentFence`（`FrameTargeter.cpp:32-63`）：

```cpp
// 遍历最近 5 个 Present Fence，找到"应该已经 signal"的那一个
// 如果该 fence 的 expectedPresentTime 与当前帧的 expectedPresentTime 太过接近
// → wouldBackpressure = true
auto FrameTarget::expectedSignaledPresentFence(Period vsyncPeriod, Period minFramePeriod) {
    bool wouldBackpressure = true;
    for (size_t i = mPresentFences.size(); i != 0; --i) {
        const auto& fence = mPresentFences[i - 1];
        if (fence.expectedPresentTime + minFramePeriod < expectedPresentTime - vsyncPeriod / 2) {
            wouldBackpressure = false;  // 够远，不会背压
        }
        if (fence.expectedPresentTime <= mFrameBeginTime) {
            return {wouldBackpressure, fence};  // 找到目标 fence
        }
    }
}
```

**3. 丢帧判定**（第 162-183 行）：

```cpp
// 条件 1: 上一帧的 Present Fence 仍 pending
mFramePending = isFencePending(fence.fenceTime, graceTimeForPresentFenceMs);
// 条件 2: Fence 已 signal，但 signal 时间晚于调度时间 + slop（半个周期）
mFrameMissed = mFramePending ||
    (lastScheduledPresentTime.ns() < pastPresentTime - frameMissedSlop);
```

丢帧时会递增 `mFrameMissedCount`、`mHwcFrameMissedCount`、`mGpuFrameMissedCount`，供 dump 输出。

**4. Present Early 判定** — `wouldPresentEarly`（`FrameTargeter.cpp:65-76`）：

```cpp
bool FrameTarget::wouldPresentEarly(Period vsyncPeriod, Period minFramePeriod) const {
    // 如果跑了 3 个 VSync 以上（超前太多），直接认为 early
    if (targetsVsyncsAhead<3>(minFramePeriod)) return true;
    // 否则检查：没有背压 或 上一帧 fence 已 signal → 可以提早呈现
    return !wouldBackpressure ||
           (fence.fenceTime->isValid() &&
            fence.fenceTime->getSignalTime() != Fence::SIGNAL_TIME_PENDING);
}
```

### FrameTargeter 在 onFrameSignal 中的位置

```
MessageQueue::vsyncCallback
  → dispatchFrame(vsyncId, expectedVsyncTime)
  → Scheduler::onFrameSignal
      │
      ├─① beginFrameArgs 组装（注入 sfWorkDuration、hwcMinWorkDuration）
      │
      ├─② FrameTargeter::beginFrame(beginFrameArgs, vsyncSchedule)
      │     → 计算 mExpectedPresentTime
      │     → 检测 mFramePending / mWouldBackpressureHwc / mFrameMissed
      │
      ├─③ compositor.commit（验证层栈，必要时 fallback 到 GPU 合成）
      │
      ├─④ compositor.composite（实际执行合成）
      │
      └─⑤ FrameTargeter::endFrame(compositeResult)
            → 记录合成覆盖范围（Hwc / Gpu）
```

这样，每一帧都有明确的生命周期边界：从 `beginFrame` 确定的 `expectedPresentTime`，到 `endFrame` 记录的合成结果。后续帧通过 Present Fence 的回传来判断前序帧是否按时完成。

---

## 第九层：Scheduler — 全局调度器集成

`Scheduler`（`Scheduler.h`）继承 `IEventThreadCallback` 和 `impl::MessageQueue`，是 VSync 系统的最高层协调者。

### Pacesetter Display 机制

Scheduler 支持多显示器，但**只有一个显示器（pacesetter）发出 VSync 节奏**（`Scheduler.h:625`）：

```cpp
ftl::Optional<PhysicalDisplayId> mPacesetterDisplayId GUARDED_BY(mDisplayLock);
```

`selectPacesetterDisplayLocked` 按优先级选择 pacesetter：

1. 如果有强制指定的 pacesetter（`mForcedPacesetterDisplayId`）
2. 否则选择请求的 pacesetter
3. 否则选择已上电且刷新率最高的显示器
4. **迟滞保护**：若当前 pacesetter 仍在且刷新率差距 < 0.1f，保留不动避免频繁切换

### Follower Display 同步对齐

当 Pacesetter 触发 `onFrameSignal` 时，**Follower（从屏）不会独立被自己的 VSync 唤醒**。Scheduler 在 Pacesetter 的合成循环中同时处理所有 Follower（`Scheduler.cpp:432-473`）：

```cpp
void Scheduler::onFrameSignal(ICompositor& compositor, VsyncId vsyncId,
                              TimePoint expectedVsyncTime) {
    // ① Pacesetter 先执行 beginFrame，确立 expectedPresentTime
    ftl::NonNull<const Display*> pacesetterPtr = pacesetterPtrLocked();
    pacesetterPtr->targeterPtr->beginFrame(beginFrameArgs, *pacesetterPtr->schedulePtr);

    // ② expectedVsyncTime 被更新为 Pacesetter 的 expectedPresentTime
    expectedVsyncTime = pacesetterPtr->targeterPtr->target().expectedPresentTime();

    // ③ 遍历所有 Follower，基于 Pacesetter 的 expectedPresentTime 对齐
    for (const auto& [id, display] : mDisplays) {
        if (id == pacesetterPtr->displayId) continue;

        auto followerBeginFrameArgs = beginFrameArgs;
        // ★ 核心：Follower 以 Pacesetter 的 expectedPresentTime 为基准，
        //    查找自己下一个 VSync 截止点
        const TimePoint nextFollowerVsync =
                display.schedulePtr->vsyncDeadlineAfter(expectedVsyncTime);
        followerBeginFrameArgs.expectedVsyncTime = nextFollowerVsync;

        // Backpressure 保护（flag 控制）
        if (followerDisplayBackpressure) {
            const size_t pendingFenceCount =
                    targeter.countPresentFencesPendingAt(beginFrameArgs.frameBeginTime);
            const TimePoint nextFollowerVsyncForBackpressure =
                    display.schedulePtr->vsyncDeadlineAfter(beginFrameArgs.frameBeginTime);
            if (pendingFenceCount > 0 &&
                !(pendingFenceCount == 1 &&
                  nextFollowerVsyncForBackpressure < expectedVsyncTime)) {
                continue; // 跳过此帧，避免 Follower 产生背压
            }
        }

        targeter.beginFrame(followerBeginFrameArgs, *display.schedulePtr);
        targets.try_emplace(id, &targeter.target());
        presentableDisplays.push_back(id);
    }

    // ④ 统一提交：一次 commit 处理所有显示器的层栈
    compositor.commit(pacesetterPtr->displayId, targets);
    // ⑤ 统一合成：一次 composite 处理所有可呈现的显示器
    const auto resultsPerDisplay = compositor.composite(pacesetterPtr->displayId, targeters);
}
```

#### Follower 对齐机制如何防止拍频效应

以 90Hz（Pacesetter，11.1ms）和 60Hz（Follower，16.6ms）为例：

```
Pacesetter (90Hz):  |--11.1ms--|--11.1ms--|--11.1ms--|--11.1ms--|--11.1ms--|
                     VSYNC0     VSYNC1     VSYNC2     VSYNC3     VSYNC4

SF 主循环心跳:        ↑          ↑          ↑          ↑          ↑
                   Frame0     Frame1     Frame2     Frame3     Frame4

Follower 每帧对齐结果:
  Frame0: expectedPresentTime(T0) → follower 找 > T0 的第一个 60Hz 边界
  Frame1: expectedPresentTime(T1) → 仍在同一个 60Hz 周期内
  Frame2: expectedPresentTime(T2) → 下一个 60Hz 边界
  ...
```

`vsyncDeadlineAfter` 调用 `VSyncPredictor::nextAnticipatedVSyncTimeFrom`——**逐帧动态地将 Follower 的 `expectedPresentTime` 对齐到自身 VSync 边界中第一个晚于 Pacesetter `expectedPresentTime` 的那一个**。

这消除了"拍频效应"的核心原因是：**不再有多套独立的硬件 VSync 各自触发合成**，Follower 的帧节奏被"夹带"在 Pacesetter 的单一调度心跳中。Follower 不会每 16.6ms 独立唤醒 SF，而是在 Pacesetter 的每 11.1ms 心跳中自然地找到自己的呈现时机。

### 案例：90Hz Pacesetter + 60Hz Follower 全链路时序

以下基于 `Scheduler.cpp:416-515` 的实际代码逻辑，追踪 90Hz 主导 + 60Hz 跟随的帧级时序。**关键结论：SF 不会"跳过" Follower，而是每帧都提交；60Hz 的均匀性由 `vsyncDeadlineAfter` 的数学性质 + HWC 的硬件节拍共同保证。**

#### 默认路径（`follower_display_backpressure` 关闭）

此 flag 关闭时（当前默认行为），`Scheduler.cpp:439-441` 中 Follower 直接使用 Pacesetter 的 `expectedPresentTime` 做对齐基准，**无背压跳过逻辑，Follower 每帧无条件参与 commit**：

```cpp
if (!followerDisplayBackpressure) {
    expectedVsyncTime = pacesetterPtr->targeterPtr->target().expectedPresentTime();
}
// ...
targeter.beginFrame(followerBeginFrameArgs, *display.schedulePtr); // 无条件执行
targets.try_emplace(id, &targeter.target());
presentableDisplays.push_back(id);  // Follower 每帧都在 presentable 列表中
```

#### 逐帧时序追踪

```
Pacesetter (90Hz) 心跳:  |--11.1--|--11.1--|--11.1--|--11.1--|--11.1--|
                          ↑        ↑        ↑        ↑        ↑
SF onFrameSignal:       T≈0     T≈11.1   T≈22.2   T≈33.3   T≈44.4

Follower (60Hz) HW VSync:
                    |------16.6------|------16.6------|------16.6------|
                    ↑                ↑                ↑                ↑
                   HW0              HW1              HW2              HW3
```

**Heartbeat 1 (T≈0)**：
- Pacesetter: `expectedVsyncTime`=11.1 → `beginFrame` → `expectedPresentTime`=11.1
- `expectedVsyncTime` 更新为 11.1（Pacesetter 的 `expectedPresentTime`）
- Follower: `vsyncDeadlineAfter(11.1)` → 以 follower 自身的 60Hz VSyncPredictor 计算
  - `snapToVsync(11.1)`：ordinal=(11.1-0+16.6)/16.6=1，prediction=1×16.6=**16.6**
- commit → HWC 收到 D2 TPT=**16.6**

**Heartbeat 2 (T≈11.1)**：
- Pacesetter: `expectedVsyncTime`=22.2 → `beginFrame` → `expectedPresentTime`=22.2
- `expectedVsyncTime` 更新为 22.2
- Follower: `vsyncDeadlineAfter(22.2)` → `snapToVsync(22.2)`
  - ordinal=(22.2-0+16.6)/16.6=2，prediction=2×16.6=**33.3**
- commit → HWC 收到 D2 TPT=**33.3**
- **此处未被跳过，而是正常提交，TPT 自然推进到下一个 60Hz 边界**

**Heartbeat 3 (T≈22.2)**：
- Pacesetter: `expectedVsyncTime`=33.3 → `beginFrame` → `expectedPresentTime`=33.3
- `expectedVsyncTime` 更新为 33.3
- Follower: `vsyncDeadlineAfter(33.3)` → `snapToVsync(33.3)`
  - ordinal=(33.3-0+16.6)/16.6=3，prediction=3×16.6=**50.0**
- commit → HWC 收到 D2 TPT=**50.0**

**Heartbeat 4 (T≈33.3)**：
- Pacesetter: `expectedVsyncTime`=44.4 → `beginFrame` → `expectedPresentTime`=44.4
- `expectedVsyncTime` 更新为 44.4
- Follower: `vsyncDeadlineAfter(44.4)` → `snapToVsync(44.4)`
  - ordinal=(44.4-0+16.6)/16.6=3 (int)，prediction=3×16.6=**50.0**
- commit → HWC 收到 D2 TPT=**50.0**（与 Heartbeat 3 相同目标）

#### HWC 队列与物理上屏

```
SF commit 序列:
  T≈0:     TPT=16.6 ─┐
  T≈11.1:  TPT=33.3 ─┤  HWC 内部队列
  T≈22.2:  TPT=50.0 ─┤
  T≈33.3:  TPT=50.0 ─┘

60Hz 物理 VSync 到来时:
  HW0 (16.6ms): 取 TPT=16.6 帧 → 【上屏】  ← 均匀间隔
  HW1 (33.3ms): 取 TPT=33.3 帧 → 【上屏】  ← 16.7ms
  HW2 (50.0ms): 取 TPT=50.0 帧 → 【上屏】  ← 16.7ms
```

**60Hz 屏幕物理上屏间隔恒为 16.6ms**，帧间隔的均匀性由 HWC 按硬件 VSync 节拍控制，而非 SF 的软件调度。

#### 两种路径对比

| 维度 | 默认路径（flag 关闭） | Backpressure 路径（flag 开启） |
|------|---------------------|-------------------------------|
| Follower 是否每帧 commit | **是，无条件** | 仅在 `pendingFenceCount==0` 或容忍条件满足时 |
| 跳过机制 | **无** | `Scheduler.cpp:459-466` 显式 `continue` |
| 60Hz 均匀性保证 | `vsyncDeadlineAfter` 数学性质 + HWC | 同左 + 额外背压保护 |
| 代码路径 | `Scheduler.cpp:439-441, 470-472` | `Scheduler.cpp:452-468` |

#### App 侧 VSync 到达模式

连接到 90Hz Pacesetter EventThread 的 60fps App，通过 `isVSyncInPhase`（`VSyncPredictor.cpp:845-861`）节流：

```
90Hz VSync 序列号:  0    1    2    3    4    5    6
                    ↓         ↓         ↓         ↓
投递到 60fps App:   ✓         ✓         ✓         ✓
实际间隔:           11.1ms    22.2ms    11.1ms    22.2ms  (交替，平均 16.6ms)
```

App VSync 到达间隔不是均匀的 16.6ms，而是在 11.1ms 和 22.2ms 之间交替。Choreographer 通过优先队列 + `dueTime` 容忍此抖动，并不要求 App 回调间隔严格均匀。

#### 常见误解澄清

| 误解 | 实际 |
|------|------|
| 60Hz 屏变成 22.2ms 刷新 | **不**，物理刷新率仍为 60Hz (16.6ms) |
| SF "跳过" Follower 以保证节奏 | **不**，默认路径每帧都 commit，不跳过 |
| Follower TPT 被强制对齐到公倍数 33.3ms | **不**，TPT 是逐帧自然快照到自身边界的结果 |
| `mWouldBackpressureHwc` 导致跳过 | **不**，该字段仅用于合成策略决策，不控制 commit 与否 |
| App 以均匀 16.6ms 收 VSync | **不**，交替 11.1/22.2ms，平均 16.6ms |

### VSync 回调链路

`Scheduler::addResyncSample` 将 HW VSync 时间戳送入 pacesetter 的 `VsyncSchedule`，然后 `addHwVsyncTimestamp` → `VSyncReactor` → `VSyncPredictor`。`VSyncDispatch` 触发后通过 `EventThread::onVsync` 生成事件，分发给所有连接的客户端。

### 关键配置参数汇总

| 参数 | 值 | 含义 | 源码位置 |
|------|----|------|----------|
| `kHistorySize` | 20 | VSync 预测模型保留的样本数 | `VsyncSchedule.cpp:116` |
| `kMinSamplesForPrediction` | 6 | 开始预测所需的最小样本数 | `VsyncSchedule.cpp:117` |
| `kDiscardOutlierPercent` | 20% | 超过此偏差的样本被视为异常 | `VsyncSchedule.cpp:118` |
| `kGroupDispatchWithin` | 500μs | 此窗口内的回调合并到同一唤醒 | `VsyncSchedule.cpp:128` |
| `kSnapToSameVsyncWithin` | 3ms | 此窗口内的 VSync 视为同一个 | `VsyncSchedule.cpp:129` |
| `kMaxPendingFences` | 20 | 最大未决 Present Fence 数 | `VsyncSchedule.cpp:140` |
| `MIN_EARLY_TRANSACTION_FRAMES` | 2 | Early 相位持续时间（帧数） | `VsyncModulator.h:44` |
| `MIN_EARLY_GPU_FRAMES` | 2 | GPU Early 相位持续时间（帧数） | `VsyncModulator.h:45` |
| `periodConfirmed allowance` | 10% | 周期确认的容差 | `VSyncReactor.cpp:187` |
| VSync stall timeout | 1000ms | 驱动卡死后生成假 VSync 的超时 | `EventThread.cpp:619` |
| Synthetic VSync period | 16ms (~60Hz) | 屏幕关闭时的合成 VSync 间隔 | `EventThread.cpp:619` |

---

## 完整数据流总结

```
DispSync/DDR 驱动
       │
       ▼ (硬件信号)
IComposerCallback.onVsync(display, timestamp, vsyncPeriodNanos)  ← AIDL
       │
       ▼ (AidlIComposerCallbackWrapper)
ComposerCallback::onComposerHalVsync(display, timestamp, period)
       │
       ▼ (SurfaceFlinger)
HWComposer::onVsync(hwcDisplayId, timestamp)
       │ 过滤重复、验证 display ID
       ▼
Scheduler::addResyncSample(PhysicalDisplayId, timestamp, period)
       │
       ▼
VsyncSchedule::addResyncSample(timestamp, period) ─→ enable/disableHardwareVsync
       │
       ▼
VSyncReactor::addHwVsyncTimestamp(timestamp, period, &periodFlushed)
       │
       ├─ periodConfirmed? ─→ setDisplayModePtr ─→ endPeriodTransition()
       │
       ▼
VSyncPredictor::addVsyncTimestamp(timestamp)  ← 简单线性回归建模
       │
       ▼ (定时器触发)
VSyncDispatchTimerQueue::timerCallback()
       │
       ├──→ MessageQueue::vsyncCallback(vsyncTime, wakeupTime, readyTime)
       │     │
       │     ▼ (SF 主线程 — Looper)
       │   Scheduler::onFrameSignal(compositor, vsyncId, expectedVsyncTime)
       │     │
       │     ├─ ① Pacesetter: FrameTargeter::beginFrame → expectedPresentTime
       │     ├─ ② Follower: vsyncDeadlineAfter(expectedPresentTime) → beginFrame
       │     ├─ ③ compositor.commit(所有显示器层栈验证)
       │     ├─ ④ compositor.composite(所有显示器合成)
       │     └─ ⑤ FrameTargeter::endFrame(记录合成覆盖范围)
       │
       ├──→ EventThread::onVsync(vsyncTime, wakeupTime, readyTime)
       │     │
       │     ├─ makeVSync(displayId, wakeupTime, count, vsyncTime, readyTime)
       │     ├─ 生成 FrameTimeline (多个帧率选项)
       │     ├─ shouldConsumeEvent() — 节流、VSyncRequest 匹配
       │     │
       │     ▼
       │   EventThreadConnection::postEvent(event)
       │     │
       │     ▼ (BitTube / Unix socket)
       │   DisplayEventReceiver::getEvents() ─→ Choreographer::dispatchVsync()
       │     │
       │     ▼
       │   App FrameCallbacks 执行
```

## HW VSync 生命周期

1. **开** — `enableHardwareVsync()` → `resetModel()` → `setVsyncEnabled(ENABLE)`
2. **采样** — HW VSync 回调到达，`addHwVsyncTimestamp()` 更新线性回归模型
3. **稳定** — `needsMoreSamples() == false` → `setIgnorePresentFences(false)` → Present Fence 成为额外 VSync 信号源
4. **关** — `disableHardwareVsync(disallow=false)` → `setVsyncEnabled(DISABLE)` → 依靠 Present Fence 维持模型
5. **屏关** — `disableHardwareVsync(disallow=true)` → 进入 `HwVsyncState::Disallowed`，之后无法再开启
