# RECOVERABLE_FROM_BUFFER_STUFFING 机制详解

## 一、什么是 Buffer Stuffing

**Buffer Stuffing**（缓冲区拥堵）是 Android 图形系统中一种特定的 Jank 类型（`JankType::BufferStuffing = 0x40`）。

### 1.1 定义

> 如果一帧原本预期在某个 vsync 上送出（present），但因为**前一帧占用了它的预期 vsync 槽位**而被迫延迟到下一个 vsync 才送出，这一帧就被称为被 "stuffed"（拥堵）。这通常发生在一帧意外耗时过长，导致后续所有缓冲帧都进入拥堵状态。

—— `frameworks/native/libs/gui/include/gui/JankInfo.h:38-42`

### 1.2 直观理解

**三缓冲的 BufferQueue 状态机（回顾）**

每个 buffer slot 有三种状态：`FREE`（可分配）→ `DEQUEUED`（App 渲染中）→ `QUEUED`（等待 SF 消费）→ `ACQUIRED`（SF 持有，正在显示）→ `FREE`（SF 释放）。

`dequeueBuffer()` 的分配条件：只要 slot 状态为 `FREE`，即可分配——**与 release fence 是否 signaled 无关**。fence 作为出参返回给 App，由 GPU 侧异步等待。

三缓冲管线在正常情况下以 vsync 节奏运行，始终有 0~1 帧在排队：

```
                    Normal Pipeline (Triple Buffer, 60fps)

Vsync:            V0         V1         V2         V3         V4
                  |          |          |          |          |
App:          [==A==]   [==B==]   [==C==]   [==D==]   [==E==]
                  |          |          |          |          |
SF latch:         A          B          C          D          E
                  |          |          |          |          |
SF present:       A          B          C          D          E

Slot trace (S=Slot, *=in use, .=free):

  V0->V1:  S0=[A SF-acquired*]  S1=.free     S2=.free  -> depth=0
  V1->V2:  S0=.free (A released)  S1=[B SF-acquired*]  S2=.free  -> depth=0
  V2->V3:  S0=.free  S1=.free (B released)  S2=[C SF-acquired*]  -> depth=0
           ^ free slot always available for dequeue
```

当某一帧（Frame B）渲染耗时异常长（例如 25ms，远超 16.67ms 的 vsync 周期）时：

```
                       Buffer Stuffing Occurs

Vsync:            V0         V1         V2         V3         V4         V5
                  |          |          |          |          |          |
App:          [==A==]  [====B====]  [==C==]   [==D==]   [==E==]   [==F==]
                  |     B overtime  |          |          |          |
                  |      25ms       |          |          |          |
                  |          |      |          |          |          |
SF latch:         A        (none)     B          C          D          E
                  |          |        |          |          |          |
SF present:       A         A'        B          C          D          E
                 V0         V1       V2         V3         V4         V5
                                    expected   expected   expected
                                     V1!        V2!        V3!

Note: A' means no new buffer at V1, SF re-uses previously latched frame A.

Slot trace:

 After V0:
    S0=[A, SF-acquired*]    S1=.free              S2=.free
    ^ App dequeues S1, starts rendering B

 At V1 (B still rendering, ~16ms elapsed):
    S0=[A, SF-acquired*]    S1=[B, rendering]     S2=.free
    ^ Queue empty, SF has nothing new to latch -> re-uses A
    ^ App cannot start next frame yet: RenderThread still busy with B
      (S2 is FREE and instantly available if App were to call dequeueBuffer,
      but the serial render thread hasn't finished B's draw calls yet)

 V1->V2 (~t=25ms):
    B finishes -> App queueBuffer(B)
    App dequeues S2 -> starts rendering C

 Before V2 latch:
    S0=[A, SF-acquired*]    S1=[B, QUEUED]        S2=[C, rendering]
    ^ B waiting in queue for SF

 V2 latch: SF latches B, S0 immediately transitions ACQUIRED->FREE
    S0=.free (just released) S1=[B, SF-acquired*] S2=[C, rendering]
    ^ S0 is FREE! App can dequeue it immediately

 V2->V3:
    C finishes -> App queueBuffer(C)
    App dequeues S0 -> starts rendering D
    S0=[D, rendering]       S1=[B, SF-acquired*]  S2=[C, QUEUED]
    ^ 3 slots in use: SF*1 + QUEUED*1 + RENDERING*1
    ^ If App finishes D and tries to dequeue again before SF latches C:
      tooManyBuffers -> brief block in waitForBufferRelease()
      This is the transient blocking that signals "buffer stuffing" to Choreographer.

 V3 latch: SF latches C, S1 -> FREE. Pipeline flowing but 1 vsync behind.
 V4 latch: SF latches D, S2 -> FREE. Still behind.
 V5 latch: SF latches E, S0 -> FREE. Still behind.
 ...all subsequent frames permanently shifted by +1 vsync.

Key insight: The pipeline does NOT deadlock.
  * Throughput = full vsync rate (App and SF both keep up)
  * Latency = permanently inflated by 1 vsync period
  * B stole C's V2 → C stole D's V3 → D stole E's V4 → cascading shift
  * Every frame from C onward is presented 1 vsync later than intended

The transient dequeue blocking (tooManyBuffers):
  * Occurs when App momentarily gets ahead of SF in a stuffed pipeline
  * Triggers BLASTBufferQueue::onWaitForBufferRelease() callback
  * Choreographer marks isStuffed=true if wait > half frame interval
  * This is the signal that starts the RECOVERY process
```

### 1.3 BufferStuffing 与 SurfaceFlingerStuffing 的对比

| 类型 | 值 | 本质 | 成因 |
|------|-----|------|------|
| `BufferStuffing` | `0x40` | 管线延迟膨胀 | 一帧超时 → 后续帧整体位移 1 vsync → 队列深度 +1 → 输入延迟永久增加 → 短暂 `tooManyBuffers` 触发 recovery |
| `SurfaceFlingerStuffing` | `0x100` | SF 占用槽位 | SF 自身合成超时 → 当前帧被推到下一 vsync |
| **Pipeline Stall** | — | 管线失速/死锁 | 双缓冲限制或 HWC 卡死 → App 无法 dequeue → 帧率归零 |

Buffer Stuffing 不等于死锁。管线仍在全速运行，只是画面传递的延迟被永久推高了 1 个 vsync 周期。`RECOVERABLE_FROM_BUFFER_STUFFING` 机制的目标就是检测并消除这 1 帧的膨胀延迟。

---

## 二、RECOVERABLE_FROM_BUFFER_STUFFING 标志

### 2.1 是什么

`RECOVERABLE_FROM_BUFFER_STUFFING` 是一个 **layer flag**，值为 `0x2000`，定义在三个层次：

| 层次 | 文件 | 定义 |
|------|------|------|
| Java | `SurfaceControl.java:862` | `public static final int RECOVERABLE_FROM_BUFFER_STUFFING = 0x00002000` |
| Native | `LayerState.h:199` | `eRecoverableFromBufferStuffing = 0x2000` |
| Flicker | `Flag.kt:30` | `RECOVERABLE_FROM_BUFFER_STUFFING(0x2000)` |

### 2.2 标记对象

**只有 `ViewRootImpl` 的根 SurfaceControl 会被打上此标记：**

```java
// ViewRootImpl.java:2873-2874
// Since the SurfaceControl is a VRI, indicate that it can recover from buffer stuffing.
mTransaction.setRecoverableFromBufferStuffing(mSurfaceControl).applyAsyncUnsafe();
```

### 2.3 传递路径

```
ViewRootImpl
  +-- setRecoverableFromBufferStuffing(mSurfaceControl)
       +-- nativeSetFlags(RECOVERABLE_FROM_BUFFER_STUFFING,
       |                  RECOVERABLE_FROM_BUFFER_STUFFING)
       +-- SurfaceComposerClient::Transaction::setFlags()
            +-- LayerState::flags |= eRecoverableFromBufferStuffing
                 +-- SurfaceFlinger applies flag to Layer
```

---

## 三、整体架构

### 3.1 系统分层图

```
+------------------------------------------------------------------+
|                    JAVA (App Process)                            |
|                                                                  |
|  +--------------+  setRecoverableFromBufferStuffing()            |
|  | ViewRootImpl |-------------------------------------> Layer   |
|  +------+-------+                                                |
|         |                                                        |
|  +------+--------------+  setWaitForBufferReleaseCallback()     |
|  |  BLASTBufferQueue   |--------------------------->            |
|  |  (Java Wrapper)     |        Choreographer                   |
|  +---------+-----------+                                        |
|            |                                                     |
|  +---------+-----------+  onWaitForBufferRelease(durationNanos) |
|  |    Choreographer     |<------------------------------------- |
|  |  BufferStuffingState |                                       |
|  |  +================+  |       isStuffed = true                |
|  |  | Recovery State |  |                                       |
|  |  | Machine        |  |  doFrame() -> updateBufferStuffingState|
|  |  +================+  |     DELAY_FRAME / OFFSET / NONE       |
|  +----------------------+                                       |
|                                                                  |
+------------------------------------------------------------------+
|                 Binder (Transaction + BufferQueue IPC)           |
+------------------------------------------------------------------+
|                 NATIVE (SurfaceFlinger Process)                  |
|                                                                  |
|  +----------------------+                                       |
|  | BufferQueueProducer  |  dequeueBuffer() -> waitForBufferRelease|
|  |  (mDequeueCondition) |  CV wait for buffer release            |
|  +----------+-----------+                                        |
|             |                                                     |
|  +----------+-----------+  readBlocking() wait for SF release   |
|  |  BLASTBufferQueue    |  compute durationNanos = now - start   |
|  |  (Native)            |  invoke mWaitForBufferReleaseCallback()|
|  +----------+-----------+                                        |
|             |                                                     |
|  +----------+-----------+                                        |
|  |     FrameTimeline    |  classifyJankLocked()                  |
|  |  +----------------+  |    readyBeforePreviousLatch?           |
|  |  | SurfaceFrame   |  |    dueLastFrame?                       |
|  |  | mJankType      |  |    -> mJankType |= BufferStuffing      |
|  |  | + None         |  |    -> Perfetto Trace                   |
|  |  | + DisplayHAL   |  |    -> statsd Telemetry                 |
|  |  | + AppDeadline  |  |                                        |
|  |  | + Prediction   |  |                                        |
|  |  | + SF_Scheduling|  |                                        |
|  |  | + BufferStuff  |<-+                                        |
|  |  | + Unknown      |  |                                        |
|  |  | + SF_Stuffing  |  |                                        |
|  |  | + Dropped      |  |                                        |
|  |  +----------------+  |                                        |
|  +----------------------+                                        |
|                                                                  |
|  +----------------------+                                        |
|  |      TimeStats       |  totalAppBufferStuffing++             |
|  |  summary atoms       |  -> SurfaceFlingerPuller -> statsd    |
|  +----------------------+                                        |
+------------------------------------------------------------------+
```

### 3.2 两条独立的路径

RECOVERABLE_FROM_BUFFER_STUFFING 机制由**两条独立路径**协作完成：

| 路径 | 方向 | 作用 |
|------|------|------|
| **Detection（检测）** | SF → Perfetto/statsd | FrameTimeline 分析帧时序，判定 `JankType::BufferStuffing`，上报 trace & telemetry |
| **Recovery（恢复）** | BLASTBufferQueue → Choreographer | dequeue 阻塞时回调通知 Choreographer，Choreographer 执行跳帧+偏移恢复 |

两条路径的纽带是 **`BLASTBufferQueue::waitForBufferRelease()`**：
- 当 stuffed 管线中 App 短暂领先于 SF 消费速度时，`tooManyBuffers` 条件触发 `dequeueBuffer` 在 `waitForBufferRelease` 上短暂阻塞
- 阻塞结束后，将 `durationNanos` 通过 `mWaitForBufferReleaseCallback` 回调给 Choreographer
- Choreographer 判断 `durationNanos > frameInterval/2` 则标记 `isStuffed = true`

---

## 四、完整时序

### 4.1 端到端时序图

```
Time ----------------------------------------------------------------------------->

Vsync:     V0         V1         V2         V3         V4         V5         V6
           |          |          |          |          |          |          |

App:    [==A==]  [====B====]  [==C==]   [==D==]   [==E==]    [==F==]  [==G==]
           |     B overtime  |          |  |       |  |       |          |
           |       25ms      |          |  |       |  |       |          |
           |          |      |          |  |       |  |       |          |

SF:    latch:A    latch:    latch:B    latch:C    latch:D    latch:E    latch:F
           |     (nothing)     |          |          |          |          |
      present:A  present:A' present:B  present:C  present:D  present:E  present:F
          V0        V1        V2         V3         V4         V5         V6
                              expected   expected   expected   expected
                               V1!        V2!        V3!        V4!
                              late 1v    pushed 1v  pushed 2v  pushed 3v

A' = SF re-uses previously latched frame (no new buffer at V1).

Buffer slot states (S0/S1/S2):

 V0->V1:  S0=[A SF-acquired*]  S1=.free          S2=.free             depth=0
 V1->V2:  S0=[A SF-acquired*]  S1=[B rendering]  S2=.free             depth=0
          ^ B still rendering at V1, queue empty, SF re-uses A

 Pre V2:  S0=[A SF-acquired*]  S1=[B QUEUED]     S2=[C rendering]     depth=1
          ^ B finally finished, queued. App dequeued S2 for C.

 V2:      SF latches B -> S0 transitions ACQUIRED->FREE immediately
 V2->V3:  S0=.free             S1=[B SF-acquired*] S2=[C QUEUED]     depth=1
          ^ S0 IS FREE. App dequeues S0 for D, starts rendering.
          ^ Pipeline already shifted: C presented at V3 instead of V2.

 V3->V4:  S0=[D QUEUED]        S1=.free            S2=[C SF-acquired*] depth=1
          ^ After V3 latch (C), S1 freed. App dequeues S1 for E.
          ^ Queue depth = 1 (inflated from normal 0). Latency permanently +1vsync.

 V4->V5:  S0=[D SF-acquired*]  S1=[E QUEUED]       S2=.free            depth=1
          ^ Stuffed-but-flowing: 1 slot free each cycle, App never permanently blocked.

 Steady "stuffed" state (V4+):
   Every frame is presented 1 vsync later than intended.
   Throughput = full vsync rate. No deadlock. Latency inflated by ~16.67ms.

Transient dequeue blocking (tooManyBuffers):
  When queue depth briefly reaches 2 (App produces ahead of SF's latch pace),
  App hits max buffer count (3/3: 1 acquired + 2 queued).
  -> dequeueBuffer() -> waitForBufferRelease() -> brief CV block.
  -> onWaitForBufferRelease(durationNanos) fires with wait duration.
  -> The block shifts App's render start relative to vsync (gap in App row above).

BBQ callback trigger (transient):
           |          |          |          |<- tooManyBuffers ->|     |
           |          |          |          | waitForBufferRelease     |
           |          |          |          |          |              |
                     onWaitForBufferRelease(durationNanos)            |
                                    |                                 |
                         durationNanos > frameInterval/2?             |
                                    |                                 |
                              isStuffed = true                        |

Choreo recovery state machine trace:
  (mLastNoOffset = last frameTimeNanos where NONE or OFFSET was taken)

 V2:   action=NONE        -> mLastNoOffset = V2, recovering=false
 V3:   isStuffed=true
       -> action=DELAY_FRAME -> numberWaitsForNextVsync=1, scheduleVsyncLocked()
       -> return EARLY (line 1048, BEFORE line 1066)
       -> mLastNoOffset STAYS at V2  (not updated during DELAY_FRAME)

 V4:   isStuffed=false, recovering=true
       totalFrameDelays = numberWaitsForNextVsync + 1 = 2
       vsyncsSinceLastCallback = (V4.frameTime - V2.frameTime) / interval = 2
       -> 2 > 2 ? NO -> OFFSET
       -> line 1066: mLastNoOffset = V4   <-- UPDATED

 V5:   totalFrameDelays = 2
       vsyncsSinceLastCallback = (V5.frameTime - V4.frameTime) / interval = 1
       -> 1 > 2 ? NO -> OFFSET (continues)
       -> line 1066: mLastNoOffset = V5

 V6..VN:  OFFSET continues every vsync while doFrame is called.
          Recovery only ends via idle detection:
          when animation pauses (several vsyncs with no doFrame callback),
          vsyncsSinceLastCallback grows large enough -> reset() -> NONE.

  Simplified timeline:
           |          |          |          |          |          |          |
  Action:            NONE       NONE    DELAY_FRAME   OFFSET     OFFSET   OFFSET
           |          |          |          |          |          |     ...
           |          |          |          |skip V3    | offset   | offset
           |          |          |          |frame      | V4       | V5
                                                       |          |
                                              mLastNoOffset=V4  mLastNoOffset=V5
           |          |          |          |          |          |          |
           ^ Recovery drains the stuffed queue:
             DELAY_FRAME: skips 1 app frame -> queue depth shrinks
             OFFSET: negative offset on animation timeline each frame
             OFFSET continues until animation goes idle -> reset()

Code key (Choreographer.java):
  DELAY_FRAME: return at line 1048 (before line 1066 mLastNoOffset update)
  OFFSET:      reaches line 1066, mLastNoOffset IS updated
  Result:      OFFSET continues every vsync during active animation,
               never terminating from vsyncSinceLastCallback alone.
               Termination comes from idle (gap between doFrame calls).

FT (FrameTimeline):
  At V3 present (C is late):
      readyBeforePreviousLatch? -> YES (C.endTime <= B.latchTime)
      dueLastFrame?             -> YES (C.expectedPresent < B.expectedPresent)
      -> mJankType |= JankType::BufferStuffing
      -> adjustedDeadline = B.latchTime + 1 vsync
      -> C re-evaluated: OnTimeFinish in stuffed context
           |          |          |          |          |          |          |

Stats:                                            totalAppBufferStuffing++
```

### 4.2 Recovery 状态机

```
                          +--------------+
                          |    IDLE      |
                          | isRecovering |
                          |    = false   |
                          +------+-------+
                                 |
                    onWaitForBufferRelease()
                    durationNanos > frameInterval/2
                                 |
                          isStuffed = true
                                 |
                    +------------v-----------+
                    |   DELAY_FRAME          |
                    |   (Recovery Start)     |
                    |                        |
                    | isRecovering = true    |
                    | isStuffed    = false   |
                    | numberWaitsForNextVsync++|
                    | scheduleVsyncLocked()  |
                    | return (skip frame)    |
                    +------------+-----------+
                                 |
                          next doFrame()
                                 |
                    +------------v-----------+
                    |      OFFSET            |
                    |  (Recovery Ongoing)    |
                    |                        |
                    | offsetFrameTimeNanos = |
                    |   frameTimeNanos       |
                    |   - frameIntervalNanos |
                    |                        |
                    | Negative offset to     |
                    | animation timeline     |
                    +------------+-----------+
                                 |
                    +------------v-----------+
                    |  Check Idle            |
                    |                        |
                    | vsyncsSinceLastCallback|
                    | > totalFrameDelays?    |
                    |                        |
                    | NO --> continue OFFSET |
                    | YES -> reset()         |
                    |         return NONE    |
                    +------------------------+
```

### 4.3 Multi-Recovery 对比

```
Single Recovery (bufferStuffingRecovery):
  --- DELAY_FRAME --- OFFSET --- OFFSET --- idle --- END
       (once only)    (continuous)             (cannot re-trigger)

Multi Recovery (bufferStuffingMultiRecovery):
  --- DELAY_FRAME --- OFFSET --- DELAY_FRAME --- OFFSET --- idle --- END
       (1st)                       (2nd, isStuffed set again)
```

---

## 五、核心代码分析

### 5.1 BufferStuffingState 状态结构

```java
// Choreographer.java:236-270
private static class BufferStuffingState {
    enum RecoveryAction {
        NONE,        // No recovery
        OFFSET,      // Apply negative offset to animation timeline
        DELAY_FRAME  // Skip frame to free a buffer slot
    }

    // true when dequeue blocked for more than half a frame interval
    public AtomicBoolean isStuffed = new AtomicBoolean(false);

    // whether recovery has started
    public boolean isRecovering = false;

    // accumulated frame skips during recovery
    // (+ 1 expected vsync delay from natural scheduling)
    public int numberWaitsForNextVsync = 0;

    public void reset() {
        isStuffed.set(false);
        isRecovering = false;
        numberWaitsForNextVsync = 0;
    }
}
```

### 5.2 dequeue 阻塞触发

```java
// Choreographer.java:280-283
public void onWaitForBufferRelease(long durationNanos) {
    if (durationNanos > mLastFrameIntervalNanos / 2) {
        // Blocked for > half frame interval -> buffer stuffing detected
        mBufferStuffingState.isStuffed.set(true);
    }
}
```

### 5.3 SurfaceFlinger 侧检测

```cpp
// FrameTimeline.cpp:650-672
// classifyJankLocked() -- BufferStuffing classification branch

// FramePresentMetadata::LatePresent:
// Frame was presented late

const bool readyBeforePreviousLatch =
    mLastFrameTimestamps.latchTime != 0 &&
    mPredictions.endTime <= mLastFrameTimestamps.latchTime;
// Condition: frame finished before previous frame's latch time
// Meaning: this frame was ready early, but stuck waiting in queue

const bool dueLastFrame =
    !FlagManager::getInstance().buffer_stuffing_fix() ||
    (mLastFrameTimestamps.expectedPresentTime != 0 &&
     mPredictions.presentTime - presentThreshold <
         mLastFrameTimestamps.expectedPresentTime);
// Condition: current frame's expected present time < previous frame's
// Meaning: previous frame stole this frame's vsync slot

if (readyBeforePreviousLatch && dueLastFrame) {
    // Classified as Buffer Stuffing
    mJankType |= JankType::BufferStuffing;

    // Use adjusted deadline to re-evaluate if app finished on time
    // In stuffed state, frame may be delayed by dequeue wait.
    // Use previous latch time + 1 vsync period as the adjusted deadline.
    nsecs_t adjustedDeadline =
        mLastFrameTimestamps.latchTime + displayFrameRenderRate.getPeriodNsecs();

    if (adjustedDeadline > mActuals.endTime) {
        mFrameReadyMetadata = FrameReadyMetadata::OnTimeFinish;
    } else {
        mFrameReadyMetadata = FrameReadyMetadata::LateFinish;
    }
}
```

### 5.4 Recovery 决策逻辑

```java
// Choreographer.java:942-1019
BufferStuffingState.RecoveryAction updateBufferStuffingState(
        long frameTimeNanos,
        DisplayEventReceiver.VsyncEventData vsyncEventData) {

    if (bufferStuffingMultiRecovery()) {
        // --- Multi-Recovery Mode ---
        if (mBufferStuffingState.isStuffed.getAndSet(false)) {
            // isStuffed == true -> start a new recovery round
            if (!mBufferStuffingState.isRecovering) {
                // First entry into recovery, record trace
                Trace.asyncTraceForTrackBegin(
                    TRACE_TAG_VIEW, "Buffer stuffing recovery",
                    "Thread " + Process.myTid() + ", recover frame", 0);
                mBufferStuffingState.isRecovering = true;
            }
            return BufferStuffingState.RecoveryAction.DELAY_FRAME;

        } else if (!mBufferStuffingState.isRecovering) {
            // Neither stuffed nor recovering -> normal path
            return BufferStuffingState.RecoveryAction.NONE;
        }
    } else {
        // --- Single-Recovery Mode ---
        if (!mBufferStuffingState.isRecovering) {
            if (!mBufferStuffingState.isStuffed.getAndSet(false)) {
                return BufferStuffingState.RecoveryAction.NONE;
            }
            mBufferStuffingState.isRecovering = true;
            // Only ONE DELAY_FRAME allowed at recovery start
            return BufferStuffingState.RecoveryAction.DELAY_FRAME;
        }
    }

    // --- Recovery In Progress ---
    // Check if we have entered idle state
    final int totalFrameDelays = mBufferStuffingState.numberWaitsForNextVsync + 1;
    final long vsyncsSinceLastCallback = mLastFrameIntervalNanos > 0
            ? (frameTimeNanos - mLastNoOffsetFrameTimeNanos)
                / mLastFrameIntervalNanos
            : 0;

    // Idle detection: vsyncs elapsed since last callback > total frame delays
    if (vsyncsSinceLastCallback > totalFrameDelays) {
        // Recovery ends
        Trace.asyncTraceForTrackEnd(TRACE_TAG_VIEW, "Buffer stuffing recovery", 0);
        mBufferStuffingState.reset();
        return BufferStuffingState.RecoveryAction.NONE;
    }

    // Continue recovery: apply negative offset
    return BufferStuffingState.RecoveryAction.OFFSET;
}
```

### 5.5 doFrame 中的恢复执行

```java
// Choreographer.java:1033-1051
switch (updateBufferStuffingState(frameTimeNanos, vsyncEventData)) {
    case NONE:
        // Normal path, offsetFrameTimeNanos = frameTimeNanos
        break;

    case OFFSET:
        // Shift animation timeline back by one frame
        // Purpose: compensate for the frame lost during stuffing
        offsetFrameTimeNanos = frameTimeNanos - frameIntervalNanos;
        break;

    case DELAY_FRAME:
        // Intentional frame skip
        // Purpose: reduce buffer queue depth, unblock dequeue
        mBufferStuffingState.numberWaitsForNextVsync++;
        scheduleVsyncLocked();
        return;  // <-- Skip ALL callbacks for this frame
}
```

---

## 六、Feature Flags

| Flag | 定义文件 | 说明 |
|------|---------|------|
| `buffer_stuffing_recovery` | `view_flags.aconfig` | 启用 Buffer Stuffing 恢复功能 |
| `buffer_stuffing_multi_recovery` | `view_flags.aconfig` | 允许同一动画内多次触发恢复 |
| `buffer_stuffing_fix` | `FlagManager.cpp:313` | FrameTimeline 侧修复：增加 `dueLastFrame` 的 `expectedPresentTime` 校验 |

---

## 七、Telemetry 与 Trace

### 7.1 Perfetto Trace

BufferStuffing 被映射为 `JANK_BUFFER_STUFFING (128)`，在 Perfetto FrameTimeline 面板中显示为 **"Buffer Stuffing"**。

```
FrameTimeline::classifyJankLocked()
    |
    +--> mJankType |= JankType::BufferStuffing (0x40)
    |
    +--> toProto()
         +--> FrameTimelineEvent::JANK_BUFFER_STUFFING (128)
              +--> Perfetto: "Buffer Stuffing"
```

### 7.2 statsd 统计

```cpp
// TimeStats.cpp
if (reasons & JankType::BufferStuffing) {
    t.jankPayload.totalAppBufferStuffing++;
}
```

statsd atom: `total_jank_frames_app_buffer_stuffing`

用于 Android 性能面板和系统健康度监控。

### 7.3 Choreographer Trace

```
Buffer stuffing recovery  --- begin ---
  Thread 42, recover frame             |
                          "buffer stuffed"  instant
                          "Negative offset of 16666666 ns"  instant
                          "Negative offset of 16666666 ns"  instant
                          ... (OFFSET repeats each vsync while animating)
                          offset
                          offset
                          idle detected (vsync gap -> reset)
Buffer stuffing recovery  --- end -----

Note: DELAY_FRAME (1x) + OFFSET (repeats every doFrame during active animation).
OFFSET only stops when animation goes idle (no doFrame call for several vsyncs).
```

---

## 八、源代码索引

| 文件 | 关键内容 |
|------|---------|
| `frameworks/native/libs/gui/include/gui/JankInfo.h:42` | `BufferStuffing = 0x40` 枚举定义 |
| `frameworks/native/libs/gui/include/gui/LayerState.h:199` | `eRecoverableFromBufferStuffing = 0x2000` 标志 |
| `frameworks/base/core/java/android/view/SurfaceControl.java:862` | Java 层 flag 常量 |
| `frameworks/base/core/java/android/view/SurfaceControl.java:5533` | `setRecoverableFromBufferStuffing()` API |
| `frameworks/base/core/java/android/view/ViewRootImpl.java:2865` | 注册 `onWaitForBufferRelease` 回调 |
| `frameworks/base/core/java/android/view/ViewRootImpl.java:2874` | 设置 `eRecoverableFromBufferStuffing` 标志 |
| `frameworks/base/core/java/android/view/Choreographer.java:236-270` | `BufferStuffingState` 内部类 |
| `frameworks/base/core/java/android/view/Choreographer.java:280-283` | `onWaitForBufferRelease()` |
| `frameworks/base/core/java/android/view/Choreographer.java:942-1019` | `updateBufferStuffingState()` 恢复状态机 |
| `frameworks/base/core/java/android/view/Choreographer.java:1033-1051` | `doFrame()` 中的恢复执行 |
| `frameworks/native/libs/gui/BLASTBufferQueue.cpp:1245-1283` | Native 层 wait 回调与 duration 计算 |
| `frameworks/native/libs/gui/BufferQueueProducer.cpp:425-446` | `dequeueBuffer` 阻塞等待 |
| `frameworks/native/services/surfaceflinger/Scheduler/FrameTimeline.cpp:650-672` | BufferStuffing 检测核心逻辑 |
| `frameworks/native/services/surfaceflinger/Scheduler/FrameTimeline.cpp:262-264` | 转换到 Perfetto proto |
| `frameworks/native/services/surfaceflinger/Scheduler/FrameTimeline.h:291-294` | `LastFrameTimestamps` 用于检测 |
| `frameworks/native/services/surfaceflinger/TimeStats/TimeStats.cpp:126,226` | statsd 统计 |
| `frameworks/native/services/surfaceflinger/common/FlagManager.cpp:313` | `buffer_stuffing_fix` 标志 |
| `frameworks/base/core/java/android/view/flags/view_flags.aconfig` | `buffer_stuffing_recovery` / `multi_recovery` |

---

## 九、总结

**RECOVERABLE_FROM_BUFFER_STUFFING** 是 Android 图形系统对 **Buffer Stuffing 卡顿的端到端解决方案**，由三层协作完成：

| 层 | 职责 |
|----|------|
| **FrameTimeline (SF)** | 事后检测：分析帧时序，识别 JANK_BUFFER_STUFFING |
| **BLASTBufferQueue** | 事件传递：dequeue 阻塞时通知 Choreographer |
| **Choreographer** | 主动恢复：跳帧释放缓冲 + 时间轴偏移补偿动画 |

其核心思路是：**当检测到管线拥堵时，不要让 App 被动等待。主动跳帧释放一个缓冲槽位，同时用时间轴偏移让动画计算平滑过渡，最后通过空闲检测优雅退出恢复状态。**
